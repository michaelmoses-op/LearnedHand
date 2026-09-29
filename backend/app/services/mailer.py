from typing import Protocol

from app.core.logging import get_logger


class Mailer(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer:
    """Dev mailer: prints the message to stdout (links contain single-use tokens, so this
    is never used outside dev). Non-dev environments log only that a mail was skipped."""

    def __init__(self, environment: str) -> None:
        self.environment = environment

    async def send(self, to: str, subject: str, body: str) -> None:
        if self.environment == "dev":
            print(f"\n--- MAIL to={to} subject={subject}\n{body}\n---", flush=True)  # noqa: T201
        else:
            get_logger("mailer").warning("mail_not_sent_no_provider", subject=subject)
