# 7. Custom Postgres job queue (`SKIP LOCKED`)

Status: accepted

## Context

ADR-0002 deferred the queue choice until Phase 2, when the job shape is known.
Phase 2 needs a small set of background jobs (document ingest stages). Q&A is
request-time SSE, not a queue job. The worker must set Postgres RLS
(`app.current_user_id`) from each job's `user_id` before touching user data.

## Options

### A. Procrastinate

Mature async Postgres queue (Django-origin, actively maintained). Gives retries,
scheduling, and a CLI. Costs: new dependency; its own connection/schema lifecycle
makes `SET LOCAL app.current_user_id` per job awkward alongside SQLAlchemy 2
sessions; more machinery than we need for one pipeline kind.

### B. Custom `jobs` table + `SELECT … FOR UPDATE SKIP LOCKED`

A single table claimed with `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED)`.
Full control over claim → `AuthContext(job.user_id)` → `set_rls_user` → handler.
No new dependency. Retries and backoff are a few lines we own.

## Decision

Choose **B**. Revisit Procrastinate only if we grow many job kinds, need cron-like
scheduling UI, or multi-queue priorities that hurt to maintain by hand.

## Consequences

- `jobs` is intentionally **not** under FORCE RLS (same rationale as `users` in
  ADR-0006): the worker must claim the next due row across users. Only
  `JobRepository` / `app.jobs.queue` touch this table; user-facing enqueue always
  stamps `user_id` from `AuthContext`. After claim, every user-data access goes
  through `AuthContext` + RLS on payload tables.
- Handlers are registered by `kind` in-process. Ingest stages are idempotent so
  retries are safe.
- No document text, prompts, or tokens in `jobs.error` or worker logs.
