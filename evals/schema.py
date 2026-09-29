"""Eval file schemas (questions + configs). Strict: unknown keys are errors, so typos surface."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.retrieval.config import RetrievalConfig


class Progress(BaseModel):
    """Where the reader is when asking. Default: finished the book."""

    model_config = ConfigDict(extra="forbid")

    after_section: int | None = Field(default=None, ge=1)  # 1-based: finished this many sections
    ordinal: int | None = Field(default=None, ge=0)  # or an explicit chunk ordinal


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    question: str = Field(min_length=3, max_length=4000)
    # Gold passages, identified by a case-insensitive text snippet (survives re-chunking).
    expected_chunks: list[str] = Field(default_factory=list)
    # Key facts an answer must contain (judge input; also checked against retrieved context).
    expected_points: list[str] = Field(default_factory=list)
    # Text that must NOT appear in anything retrieved (spoiler check, independent of the gate).
    forbidden_snippets: list[str] = Field(default_factory=list)
    progress: Progress = Field(default_factory=Progress)
    tags: list[str] = Field(default_factory=list)


class CorpusRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demo: bool = False  # built-in synthetic book (no copyrighted material)
    epub: str | None = None  # path to an EPUB you own, relative to the questions file


class QuestionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    corpus: CorpusRef
    questions: list[Question] = Field(min_length=1)


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    description: str = ""
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    # Rerank implementation for this config (`fake` = lexical, CI-safe; `cross_encoder` = real).
    reranker: Literal["none", "fake", "cross_encoder"] = "none"


def load_questions(path: Path) -> QuestionFile:
    return QuestionFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_config(path: Path) -> EvalConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("name", path.stem)
    if isinstance(data.get("retrieval"), dict):
        data["retrieval"].setdefault("name", data["name"])
    return EvalConfig.model_validate(data)
