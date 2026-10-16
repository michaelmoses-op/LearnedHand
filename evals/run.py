"""Eval runner.

    make eval                                  # demo book, every config in evals/configs/
    python -m evals.run --config evals/configs/hierarchical_hybrid.yaml --questions ...

Ingests the corpus through the real pipeline (reused when unchanged), then for every config ×
question runs retrieval (with per-stage traces) and generation, computes metrics, and stores
them in `eval_runs` / `eval_results` under the eval user's RLS context. Nothing is pushed to any
network service beyond the configured LLM provider (the fake provider by default).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.deps import AuthContext, set_rls_user
from app.core.logging import configure_logging
from app.generation.ask import build_messages
from app.ingestion.constants import STAGE_VERSIONS
from app.ingestion.pipeline import run_ingest
from app.llm.factory import build_llm
from app.llm.rerank import build_reranker
from app.models.chunk import Chunk
from app.models.eval import EvalResult, EvalRun
from app.models.job import Job
from app.models.user import User
from app.repositories.content import ChunkRepository
from app.repositories.users import UserRepository
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.retrieval.types import RetrievalResult
from app.services.documents import DocumentService
from app.storage.local import LocalFileStorage
from evals import corpus, metrics
from evals.judge import judge_points
from evals.schema import EvalConfig, Question, QuestionFile, load_config, load_questions

EVAL_EMAIL = "eval@learnedhand.invalid"  # reserved TLD: cannot receive mail or log in
EVALS_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def scope(
    sm: async_sessionmaker[AsyncSession], user_id: uuid.UUID | None
) -> AsyncIterator[AsyncSession]:
    """One transaction with the RLS user set; commits on success, rolls back on error."""
    async with sm() as session:
        if user_id is not None:
            await set_rls_user(session, user_id)
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def ensure_eval_user(sm: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with scope(sm, None) as s:
        repo = UserRepository(s)
        user = await repo.get_by_email(EVAL_EMAIL)
        if user is None:
            user = User(email=EVAL_EMAIL, email_verified=True, password_hash=None)
            s.add(user)
            await s.flush()
        return user.id


async def _bytes_stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def ensure_document(
    sm: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    settings: Settings,
    *,
    name: str,
    epub: bytes,
    force: bool,
) -> uuid.UUID:
    """Upload + ingest, or reuse an up-to-date ingest of the identical file."""
    storage = LocalFileStorage(settings.storage_root)
    ctx = AuthContext(user_id)
    async with scope(sm, user_id) as s:
        doc, created = await DocumentService(s, ctx, storage).upload(
            _bytes_stream(epub), f"{name}.epub", max(settings.max_upload_bytes, len(epub))
        )
        if created:  # we ingest inline below; don't leave a queued duplicate for the worker
            await s.execute(delete(Job).where(Job.document_id == doc.id))
        fresh = (
            not created
            and not force
            and doc.status == "ready"
            and dict(doc.stage_versions or {}) == STAGE_VERSIONS
            and await _chunks_current(s, ctx, doc.id, settings)
        )
        if not fresh:
            job = Job(
                user_id=user_id, document_id=doc.id, kind="ingest", stage="pending", payload={}
            )
            print(f"ingesting '{name}' …", flush=True)
            await run_ingest(s, ctx, job, settings, storage)
        else:
            print(f"reusing ingested '{name}'", flush=True)
        return doc.id


async def _chunks_current(
    s: AsyncSession, ctx: AuthContext, doc_id: uuid.UUID, settings: Settings
) -> bool:
    chunks = await ChunkRepository(s, ctx).list_for_document(doc_id)
    return bool(chunks) and all(
        c.embedding_model == settings.embedding_model
        and c.embedding_plain is not None
        and c.embedding is not None
        for c in chunks
    )


def _gold(q: Question, chunks: Sequence[Chunk]) -> set[uuid.UUID]:
    snippets = [s.lower() for s in q.expected_chunks]
    return {c.id for c in chunks if any(sn in c.body.lower() for sn in snippets)}


async def evaluate_config(
    sm: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    settings: Settings,
    doc_id: uuid.UUID,
    cfg: EvalConfig,
    qfile: QuestionFile,
    *,
    batch_id: uuid.UUID,
    judge_model: str | None,
) -> dict[str, Any]:
    ctx = AuthContext(user_id)
    rows: list[dict[str, Any]] = []
    stored: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    async with scope(sm, user_id) as s:
        chunks = await ChunkRepository(s, ctx).list_for_document(doc_id)
        by_id = {c.id: c for c in chunks}
        reranker = build_reranker(settings.model_copy(update={"reranker": cfg.reranker}))
        orchestrator = RetrievalOrchestrator(
            s, ctx, settings, document_id=doc_id, reranker=reranker
        )
        gen_llm = build_llm(settings, s, ctx, document_id=doc_id, stage="generate")
        judge_llm = build_llm(settings, s, ctx, document_id=doc_id, stage="judge")

        for q in qfile.questions:
            gold = _gold(q, chunks)
            if q.expected_chunks and not gold:
                print(f"  ! {q.id}: no gold passage found in the book — skipped", flush=True)
                continue
            result = await orchestrator.run(query=q.question, config=cfg.retrieval, route=cfg.route)
            row, stages = await _score(
                q, result, gold, by_id, cfg, settings, gen_llm, judge_llm, judge_model
            )
            rows.append(row)
            stored.append((q.id, row, stages))

        summary = metrics.summarise(rows)
        run = EvalRun(
            user_id=user_id,
            document_id=doc_id,
            batch_id=batch_id,
            config_name=cfg.name,
            corpus=qfile.name,
            provider=settings.llm_provider,
            config=cfg.model_dump(mode="json"),
            summary=summary,
        )
        s.add(run)
        await s.flush()
        for qid, row, stages in stored:
            s.add(
                EvalResult(
                    user_id=user_id, run_id=run.id, question_id=qid, metrics=row, stages=stages
                )
            )
    return summary


async def _score(
    q: Question,
    result: RetrievalResult,
    gold: set[uuid.UUID],
    by_id: dict[uuid.UUID, Chunk],
    cfg: EvalConfig,
    settings: Settings,
    gen_llm: Any,
    judge_llm: Any,
    judge_model: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    final_ids = [c.chunk_id for c in result.chunks]
    texts = [c.text for c in result.chunks]
    gold_sections = {by_id[g].section_id for g in gold}
    row: dict[str, Any] = {
        "recall_at_5": metrics.recall_at_k(gold, final_ids, 5),
        "recall_at_10": metrics.recall_at_k(gold, final_ids, 10),
        "mrr": metrics.reciprocal_rank(gold, final_ids),
        "context_point_coverage": metrics.point_coverage(q.expected_points, " ".join(texts)),
        "retrieval_ms": result.total_ms,
        "iterations": result.iterations,
    }
    for stage in result.stages:
        if stage.name in ("vector", "fts", "fuse", "rerank"):
            row[f"recall_{stage.name}"] = metrics.recall_at_k(gold, stage.ids)
        if stage.name == "broad":
            row["broad_section_recall"] = metrics.recall_at_k(gold_sections, stage.ids)

    # Generation (same prompt builder as the live ask path).
    t0 = time.perf_counter()
    out = await gen_llm.complete(
        model=settings.llm_model, messages=build_messages(question=q.question, chunks=result.chunks)
    )
    gen_ms = (time.perf_counter() - t0) * 1000.0
    in_tok = out.input_tokens + result.total_tokens
    out_tok = out.output_tokens
    row["generation_ms"] = gen_ms
    row["latency_ms"] = result.total_ms + gen_ms
    row["citation_validity"] = metrics.citation_validity(out.text, len(result.chunks))
    if settings.llm_provider != "fake" and q.expected_points:
        row["answer_point_coverage"] = await judge_points(
            judge_llm,
            model=judge_model or settings.llm_model,
            question=q.question,
            answer=out.text,
            points=q.expected_points,
        )
    row["input_tokens"] = in_tok
    row["output_tokens"] = out_tok
    row["cost_usd"] = metrics.cost_usd(
        in_tok, out_tok, settings.price_input_per_mtok, settings.price_output_per_mtok
    )
    stages = [
        {
            "name": s.name,
            "duration_ms": round(s.duration_ms, 3),
            "count": s.count,
            "tokens": s.tokens,
            "ids": [str(i) for i in s.ids],
            "note": s.note,
        }
        for s in result.stages
    ]
    return row, stages


def _config_files(paths: Sequence[str]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    return sorted((EVALS_DIR / "configs").glob("*.yaml"))


def _question_files(paths: Sequence[str]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    return sorted((EVALS_DIR / "questions").glob("*.yaml"))


def _epub_for(qfile: QuestionFile, qpath: Path) -> bytes | None:
    if qfile.corpus.demo:
        return corpus.demo_epub()
    if qfile.corpus.epub:
        path = (qpath.parent / qfile.corpus.epub).resolve()
        return path.read_bytes() if path.exists() else None
    return None


async def main_async(args: argparse.Namespace) -> int:
    os.environ["STORE_PLAIN_EMBEDDINGS"] = "true"  # needed by the prefix on/off ablation
    os.environ["LOG_LEVEL"] = "INFO" if args.verbose else "WARNING"  # readable results table
    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(settings.log_level)
    configs = [load_config(p) for p in _config_files(args.config)]
    if not configs:
        print("no configs found", file=sys.stderr)
        return 2
    engine = make_engine(settings)
    sm = make_sessionmaker(engine)
    try:
        user_id = await ensure_eval_user(sm)
        batch_id = uuid.uuid4()
        ran = 0
        for qpath in _question_files(args.questions):
            qfile = load_questions(qpath)
            epub = _epub_for(qfile, qpath)
            if epub is None:
                print(f"skip {qpath.name}: EPUB not found ({qfile.corpus.epub})", file=sys.stderr)
                continue
            print(f"== {qfile.name}: {len(qfile.questions)} questions, {len(configs)} configs")
            doc_id = await ensure_document(
                sm, user_id, settings, name=qfile.name, epub=epub, force=args.reingest
            )
            for cfg in configs:
                summary = await evaluate_config(
                    sm,
                    user_id,
                    settings,
                    doc_id,
                    cfg,
                    qfile,
                    batch_id=batch_id,
                    judge_model=args.judge_model,
                )
                ran += 1
                r5 = summary.get("recall_at_5")
                print(f"  {cfg.name:<28} recall@5={_fmt(r5)}")
        if not ran:
            return 2
        from evals.compare import render_batch

        print()
        print(await render_batch(sm, user_id, batch_id, baseline=args.baseline))
        print(f"\nbatch: {batch_id}")
        return 0
    finally:
        await engine.dispose()


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}"


def main() -> None:
    p = argparse.ArgumentParser(description="Run retrieval/generation evals.")
    p.add_argument("--config", action="append", default=[], help="config YAML (repeatable)")
    p.add_argument("--questions", action="append", default=[], help="questions YAML (repeatable)")
    p.add_argument("--baseline", default=None, help="config name to diff against")
    p.add_argument("--judge-model", default=None, help="model for the LLM judge")
    p.add_argument("--verbose", action="store_true", help="show app logs while running")
    p.add_argument("--reingest", action="store_true", help="force re-ingest of the corpus")
    raise SystemExit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
