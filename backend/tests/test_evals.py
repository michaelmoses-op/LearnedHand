"""Eval harness: metrics, schemas, demo corpus integrity, and an end-to-end run."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.core.deps import set_rls_user
from app.ingestion.chunking import chunk_sections
from app.ingestion.parse_epub import parse_epub
from app.models.eval import EvalResult, EvalRun
from evals import compare, corpus, metrics
from evals.run import ensure_document, ensure_eval_user, evaluate_config
from evals.schema import EvalConfig, load_config, load_questions

EVALS = Path(__file__).resolve().parents[2] / "evals"


# ---- metrics ---------------------------------------------------------------------------------


def test_recall_and_mrr() -> None:
    gold = {"a", "b"}
    assert metrics.recall_at_k(gold, ["x", "a", "y", "b"], 2) == 0.5
    assert metrics.recall_at_k(gold, ["x", "a", "y", "b"]) == 1.0
    assert metrics.recall_at_k(set(), ["a"]) is None
    assert metrics.reciprocal_rank(gold, ["x", "y", "b"]) == pytest.approx(1 / 3)
    assert metrics.reciprocal_rank(gold, ["x"]) == 0.0
    assert metrics.reciprocal_rank(set(), ["x"]) is None


def test_point_coverage_is_lexical_and_order_free() -> None:
    text = "The Ironmaster, Corwin Hale, fired it in 1748."
    assert metrics.point_coverage(["Corwin Hale", "1748"], text) == 1.0
    assert metrics.point_coverage(["Corwin Hale", "1900"], text) == 0.5
    assert metrics.point_coverage([], text) is None


def test_citation_validity_counts_dangling_markers() -> None:
    assert metrics.citation_validity("as shown [1] and [2] and [9]", 3) == pytest.approx(2 / 3)
    assert metrics.citation_validity("no citations", 3) is None
    assert metrics.citation_validity("bad [0]", 3) == 0.0


def test_contains_any_and_cost_and_percentile() -> None:
    assert metrics.contains_any(["Alpha beta", "gamma"], ["BETA"]) == 1
    assert metrics.cost_usd(1_000_000, 500_000, 2.0, 4.0) == pytest.approx(4.0)
    assert metrics.percentile([10.0, 20.0, 30.0], 50) == 20.0
    assert metrics.percentile([], 50) is None


def test_summarise_sums_tokens_and_takes_percentiles() -> None:
    rows: list[dict[str, Any]] = [
        {"recall_at_5": 1.0, "latency_ms": 10.0, "input_tokens": 5},
        {"recall_at_5": 0.5, "latency_ms": 30.0, "input_tokens": 7},
        {"recall_at_5": None, "latency_ms": 20.0, "input_tokens": 1},
    ]
    s = metrics.summarise(rows)
    assert s["recall_at_5"] == 0.75  # None (no gold) is excluded from the mean
    assert s["input_tokens"] == 13
    assert s["latency_ms_p50"] == 20.0


# ---- schemas ---------------------------------------------------------------------------------


def test_shipped_configs_and_questions_validate() -> None:
    configs = [load_config(p) for p in sorted((EVALS / "configs").glob("*.yaml"))]
    assert len(configs) >= 2  # `make eval` needs at least two to compare
    assert len({c.name for c in configs}) == len(configs)
    for p in (EVALS / "questions").glob("*.yaml"):
        assert load_questions(p).questions


def test_schema_rejects_unknown_keys_and_unsupported_iterations() -> None:
    with pytest.raises(ValidationError):
        EvalConfig.model_validate({"name": "x", "retreival": {}})
    with pytest.raises(ValidationError):
        EvalConfig.model_validate({"name": "x", "retrieval": {"max_iterations": 4}})
    with pytest.raises(ValidationError):
        EvalConfig.model_validate({"name": "bad name!"})


def test_demo_questions_target_text_that_really_exists() -> None:
    """A gold snippet missing from the corpus would make a metric vacuous."""
    book = parse_epub(corpus.demo_epub())
    chunks = chunk_sections(book.sections)
    assert len(chunks) >= 20  # enough distractors for recall@5 to mean something
    full = " ".join(c.text for c in chunks).lower()
    qfile = load_questions(EVALS / "questions" / "demo.yaml")
    for q in qfile.questions:
        for snippet in q.expected_chunks:
            assert snippet.lower() in full, (q.id, snippet)


def test_demo_epub_is_deterministic() -> None:
    assert corpus.demo_epub() == corpus.demo_epub()


# ---- end to end ------------------------------------------------------------------------------


async def test_end_to_end_eval_compares_configs_and_respects_rls(
    app: FastAPI, settings: Settings
) -> None:
    sm = app.state.sessionmaker
    cfg_settings = settings.model_copy(update={"store_plain_embeddings": True})
    user_id = await ensure_eval_user(sm)
    assert await ensure_eval_user(sm) == user_id  # idempotent

    qfile = load_questions(EVALS / "questions" / "demo.yaml")
    doc_id = await ensure_document(
        sm, user_id, cfg_settings, name="demo", epub=corpus.demo_epub(), force=True
    )
    batch = uuid.uuid4()
    summaries = {}
    for name in ("baseline_flat_hybrid", "hierarchical_hybrid", "flat_hybrid_no_prefix"):
        cfg = load_config(EVALS / "configs" / f"{name}.yaml")
        summaries[name] = await evaluate_config(
            sm, user_id, cfg_settings, doc_id, cfg, qfile, batch_id=batch, judge_model=None
        )

    base = summaries["baseline_flat_hybrid"]
    assert base["recall_at_5"] >= 0.9
    assert base["questions"] == len(qfile.questions)
    for s in summaries.values():
        assert s["latency_ms_p50"] > 0 and s["input_tokens"] > 0
    assert "broad_section_recall" in summaries["hierarchical_hybrid"]
    assert "broad_section_recall" not in base

    table = await compare.render_batch(sm, user_id, batch, baseline="baseline_flat_hybrid")
    for name in summaries:
        assert name in table
    assert "recall@5" in table and "| config |" in table

    async with sm() as s:  # results are visible to the eval user only
        await set_rls_user(s, user_id)
        runs = list((await s.execute(select(EvalRun).where(EvalRun.batch_id == batch))).scalars())
        results = list((await s.execute(select(EvalResult))).scalars())
        assert len(runs) == 3 and len(results) >= 3 * len(qfile.questions)
        stage_names = {st["name"] for r in results for st in r.stages}
        assert {"embed_query", "vector", "fts", "fuse", "final", "broad"} <= stage_names
    async with sm() as s:
        await set_rls_user(s, uuid.uuid4())
        assert not list((await s.execute(select(EvalRun))).scalars())
        assert not list((await s.execute(select(EvalResult))).scalars())
