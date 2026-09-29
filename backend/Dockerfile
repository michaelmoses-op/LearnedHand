# One image, multiple commands: api (default), worker, migrate.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /app /app
# LocalFileStorage creates STORAGE_ROOT at import; app user must own it.
RUN mkdir -p /app/var/storage && chown -R app:app /app/var
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz')"
# api:     uvicorn app.main:app --host 0.0.0.0 --port 8000
# worker:  python -m app.jobs.worker
# migrate: alembic upgrade head
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
