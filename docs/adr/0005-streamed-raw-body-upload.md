# 5. Uploads are a streamed raw request body, not multipart

Status: accepted

Starlette/FastAPI multipart parsing spools the whole file to a temp file before the handler
runs, so a size cap cannot abort the transfer early. `POST /api/v1/documents` therefore takes the
file bytes as the raw body (name in `X-Filename`, display-only). The handler reads
`request.stream()`, enforces the cap while streaming, checks magic bytes on the first bytes,
hashes as it goes, and writes to storage via `put_stream` (temp file + atomic rename). Nothing
is left behind on failure. A future S3 implementation would use presigned uploads instead.
Identical content re-uploaded by the same user returns the existing document (200), which
doubles as idempotency for retries (`Idempotency-Key` is accepted).
