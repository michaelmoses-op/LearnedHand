# 2. Postgres-backed job queue, deferred

Status: superseded by [0007](0007-job-queue.md)

Jobs will run on Postgres (no Redis/Celery). Phase 0 ships only a worker skeleton
(DB ping, heartbeat, graceful SIGTERM). The queue implementation (`procrastinate` vs. a small
`SELECT ... FOR UPDATE SKIP LOCKED` table) is chosen in Phase 2 when the job shape is known,
to avoid a dependency we may not need. Decision: custom `SKIP LOCKED` table (ADR-0007).
