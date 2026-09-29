import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

_REDACT_KEYS = {
    "text",
    "prompt",
    "token",
    "password",
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "secret",
}


def redact(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Never let document text, prompts or credentials reach the logs."""
    for key in list(event_dict):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=level.upper(), force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
