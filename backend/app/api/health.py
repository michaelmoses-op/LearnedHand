from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.db import ping

router = APIRouter(tags=["health"])


class Status(BaseModel):
    status: str


@router.get("/healthz", response_model=Status)
async def healthz() -> Status:
    return Status(status="ok")


@router.get("/readyz", response_model=Status, responses={503: {"model": Status}})
async def readyz(request: Request) -> Status | JSONResponse:
    if await ping(request.app.state.engine):
        return Status(status="ready")
    return JSONResponse({"status": "database_unavailable"}, status_code=503)
