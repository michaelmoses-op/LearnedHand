"""Generation package (ask / citations). Callable without HTTP."""

from app.generation.ask import AskEvent, AskService, sanitize_answer_html
from app.generation.citations import Citation, SourceRef, verify_citations

__all__ = [
    "AskEvent",
    "AskService",
    "Citation",
    "SourceRef",
    "sanitize_answer_html",
    "verify_citations",
]
