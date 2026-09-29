# 3. openapi-typescript + openapi-fetch for the API client

Status: accepted

The client is generated from the app's OpenAPI schema (dumped without a server via
`python -m app.core.openapi_dump`). We chose `openapi-typescript` + `openapi-fetch` over `orval`
for a smaller runtime and types-only generation. CI fails if the committed client is stale.
