from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import RateLimiter
from app.services.mailer import ConsoleMailer
from app.storage.local import LocalFileStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = make_engine(settings)
        app.state.sessionmaker = make_sessionmaker(app.state.engine)
        get_logger(__name__).info("startup", environment=settings.environment)
        yield
        await app.state.engine.dispose()
        get_logger(__name__).info("shutdown")

    app = FastAPI(title="LearnedHand", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.limiter = RateLimiter(enabled=settings.rate_limit_enabled)
    app.state.mailer = ConsoleMailer(settings.environment)
    app.state.storage = LocalFileStorage(settings.storage_root)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit allowlist, never "*" with credentials
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router)
    return app


app = create_app()
