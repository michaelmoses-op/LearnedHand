"""LLM-as-judge: does an answer state each expected point? Structured output, one repair retry."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.llm.structured import complete_structured

_PROMPT = Path(__file__).parent / "prompts" / "judge.md"


class PointVerdict(BaseModel):
    point: str
    covered: bool


class Verdict(BaseModel):
    points: list[PointVerdict]


async def judge_points(
    llm: AccountingLLM, *, model: str, question: str, answer: str, points: list[str]
) -> float:
    listed = "\n".join(f"- {p}" for p in points)
    user = (
        f"<question>\n{question}\n</question>\n\n<answer>\n{answer}\n</answer>\n\n"
        f"Expected points:\n{listed}\n\nReturn one verdict per expected point."
    )
    verdict = await complete_structured(
        llm,
        model=model,
        messages=[
            ChatMessage("system", _PROMPT.read_text(encoding="utf-8")),
            ChatMessage("user", user),
        ],
        output=Verdict,
    )
    covered = {v.point.strip().lower() for v in verdict.points if v.covered}
    return sum(1 for p in points if p.strip().lower() in covered) / len(points)
