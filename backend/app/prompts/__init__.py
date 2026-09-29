"""Prompt files live beside this module. Baselines are HUMAN-OWNED; agents must not tune them."""

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """Load `<name>.md` (no path separators allowed)."""
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("invalid prompt name")
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")
