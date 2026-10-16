"""Compare eval runs as a Markdown table.

python -m evals.compare                     # latest batch
python -m evals.compare baseline hierarchical_hybrid    # latest run of each named config
python -m evals.compare --batch <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import make_engine, make_sessionmaker
from app.models.eval import EvalRun

# (header, summary key, higher_is_better, format)
MAIN_COLUMNS: list[tuple[str, str, bool | None, str]] = [
    ("recall@5", "recall_at_5", True, "{:.2f}"),
    ("recall@10", "recall_at_10", True, "{:.2f}"),
    ("MRR", "mrr", True, "{:.2f}"),
    ("ctx points", "context_point_coverage", True, "{:.2f}"),
    ("answer points (judge)", "answer_point_coverage", True, "{:.2f}"),
    ("citation ok", "citation_validity", True, "{:.2f}"),
    ("p50 ms", "latency_ms_p50", False, "{:.1f}"),
    ("p95 ms", "latency_ms_p95", False, "{:.1f}"),
    ("tokens", "_tokens", False, "{:,.0f}"),
    ("cost $", "cost_usd", False, "{:.4f}"),
]
STAGE_COLUMNS: list[tuple[str, str, bool | None, str]] = [
    ("broad→section", "broad_section_recall", True, "{:.2f}"),
    ("vector pool", "recall_vector", True, "{:.2f}"),
    ("fts pool", "recall_fts", True, "{:.2f}"),
    ("fused pool", "recall_fuse", True, "{:.2f}"),
    ("rerank pool", "recall_rerank", True, "{:.2f}"),
    ("retrieval p50 ms", "retrieval_ms_p50", False, "{:.1f}"),
    ("avg iterations", "iterations", None, "{:.2f}"),
]


def _value(summary: dict[str, Any], key: str) -> float | None:
    if key == "_tokens":
        parts = (summary.get("input_tokens"), summary.get("output_tokens"))
        return None if parts[0] is None else float((parts[0] or 0) + (parts[1] or 0))
    v = summary.get(key)
    return None if v is None else float(v)


def _table(
    runs: list[EvalRun], cols: list[tuple[str, str, bool | None, str]], baseline: str | None
) -> str:
    best: dict[str, float] = {}
    for _h, key, higher, _f in cols:
        vals = [v for r in runs if (v := _value(r.summary, key)) is not None]
        if vals and higher is not None and len(set(vals)) > 1:
            best[key] = max(vals) if higher else min(vals)
    base = next((r for r in runs if r.config_name == baseline), None)
    lines = [
        "| config | " + " | ".join(h for h, *_ in cols) + " |",
        "|---|" + "|".join("---:" for _ in cols) + "|",
    ]
    for r in runs:
        cells: list[str] = []
        for _h, key, _higher, fmt in cols:
            v = _value(r.summary, key)
            if v is None:
                cells.append("—")
                continue
            text = fmt.format(v)
            if key in best and v == best[key]:
                text = f"**{text}**"
            if base is not None and r is not base and (bv := _value(base.summary, key)) is not None:
                delta = v - bv
                if abs(delta) > 1e-9:
                    text += f" ({'+' if delta > 0 else ''}{fmt.format(delta)})"
            cells.append(text)
        name = r.config_name + (" *(baseline)*" if r is base else "")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render(runs: list[EvalRun], baseline: str | None = None) -> str:
    if not runs:
        return "_no eval runs found_"
    if baseline is None:
        baseline = runs[0].config_name
    provider = runs[0].provider
    note = (
        "\n> Provider is `fake`: retrieval numbers reflect a lexical stand-in for embeddings and "
        "answer quality is not measured. Use a real provider for meaningful results."
        if provider == "fake"
        else ""
    )
    return (
        f"### Eval comparison — corpus `{runs[0].corpus}`, provider `{provider}`\n\n"
        f"{_table(runs, MAIN_COLUMNS, baseline)}\n\n"
        f"#### Per-stage recall (share of gold passages present at each stage)\n\n"
        f"{_table(runs, STAGE_COLUMNS, baseline)}\n{note}"
    )


async def render_batch(
    sm: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    batch_id: uuid.UUID,
    baseline: str | None = None,
) -> str:
    from app.core.deps import set_rls_user

    async with sm() as s:
        await set_rls_user(s, user_id)
        rows = (
            await s.execute(
                select(EvalRun).where(EvalRun.batch_id == batch_id).order_by(EvalRun.created_at)
            )
        ).scalars()
        return render(list(rows), baseline)


async def _latest(
    sm: async_sessionmaker[AsyncSession],
    names: list[str],
    batch: uuid.UUID | None,
) -> tuple[uuid.UUID, list[EvalRun]]:
    from app.core.deps import set_rls_user
    from app.models.user import User

    async with sm() as s:
        user = (
            await s.execute(select(User).where(User.email == "eval@learnedhand.invalid"))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit("no eval user yet; run `make eval` first")
        await set_rls_user(s, user.id)
        stmt = select(EvalRun).order_by(EvalRun.created_at.desc())
        if batch is not None:
            stmt = stmt.where(EvalRun.batch_id == batch)
        rows = list((await s.execute(stmt)).scalars())
        if names:
            picked: list[EvalRun] = []
            for name in names:
                match = next((r for r in rows if r.config_name == name), None)
                if match is None:
                    raise SystemExit(f"no run found for config '{name}'")
                picked.append(match)
            return user.id, picked
        if not rows:
            return user.id, []
        latest = rows[0].batch_id
        return user.id, sorted(
            (r for r in rows if r.batch_id == latest), key=lambda r: r.created_at
        )


async def main_async(args: argparse.Namespace) -> int:
    engine = make_engine(get_settings())
    try:
        _uid, runs = await _latest(
            make_sessionmaker(engine), args.names, uuid.UUID(args.batch) if args.batch else None
        )
        print(render(runs, args.names[0] if args.names else None))
        return 0 if runs else 1
    finally:
        await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(description="Compare eval runs.")
    p.add_argument("names", nargs="*", help="config names (first is the baseline)")
    p.add_argument("--batch", default=None, help="batch id (default: latest)")
    raise SystemExit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
