# 6. Auth, sessions, RLS and rate limiting design

Status: accepted

- Sessions: 15-minute HS256 JWT access cookie + rotating opaque refresh token (only SHA-256
  hashes stored). Reuse of a consumed refresh token revokes the whole family. Cookies are
  httpOnly (`__Host-`/`__Secure-` prefixes when `COOKIE_SECURE=true`).
- Opaque tokens (refresh, email verify, password reset) are `<user_id>.<secret>`. The prefix lets
  us set the RLS user context *before* lookup, so RLS applies without any bypass role or
  SECURITY DEFINER function. The hash of the whole token is stored.
- CSRF: `Origin` allowlist on all state-changing requests plus a double-submit token
  (`X-CSRF-Token` must equal the readable csrf cookie) whenever auth cookies are present.
- RLS: `documents`, `refresh_tokens`, `email_tokens`, `auth_identities` have ENABLE + FORCE RLS
  keyed on `app.current_user_id` (set with `set_config(..., true)` per transaction). The `users`
  table is intentionally outside RLS because login must resolve an email before any user
  context exists; it is only touched by `UserRepository`, never by feature code.
- Rate limiting is an in-process sliding window (no Redis). Correct for a single API process;
  the `RateLimiter.check` seam allows a Postgres/Redis-backed version if we scale out.
- Signup and password-reset requests answer identically whether or not the email exists.
- Email is delivered through a `Mailer` interface; only a dev `ConsoleMailer` exists.
  Email verification is recorded but not yet enforced anywhere.
