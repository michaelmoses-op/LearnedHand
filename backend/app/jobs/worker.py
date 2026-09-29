"""Worker entrypoint. Phase 0: connects to the DB, logs, idles, drains on SIGTERM.

The job queue itself arrives with ingestion (see docs/adr/0002).
"""

import asyncio
import signal

from app.core.config import get_settings
from app.core.db import make_engine, ping
from app.core.logging import configure_logging, get_logger

HEARTBEAT_SECONDS = 30


async def run(stop: asyncio.Event) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("worker")
    engine = make_engine(settings)
    try:
        log.info("worker_started", database_ok=await ping(engine))
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                log.info("worker_heartbeat", database_ok=await ping(engine))
    finally:
        await engine.dispose()
        log.info("worker_stopped")


def main() -> None:
    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await run(stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
