# ADR 0011 — Server-side token revocation with a per-user `token_version`

**Status:** accepted · **Code:** `User.token_version`, `deps._check_token_version`, `POST /auth/logout`, `reset_password`, WebSocket auth, migration `007`

## Context

JWTs were valid for their full 120 minutes no matter what. Logout only cleared
browser storage, and a password reset left every stolen token working. The
120-minute lifetime is deliberate (exams are long), which makes the exposure
window large.

## Options

1. **Short access token + refresh token** — the standard answer. It adds a refresh endpoint, refresh-token storage and rotation, and client retry logic, and the refresh token still needs revocation.
2. **`jti` denylist in Redis** (TTL = token's remaining life) — revokes a single device's token; costs a Redis lookup per request, and if Redis loses the key the revocation is gone (fail-open), unless you fail closed and make Redis a hard dependency for auth.
3. **Per-user `token_version`** *(chosen)* — each JWT carries the version current at login (`tv`); bumping the column invalidates every older token.

## Decision

- `users.token_version INT NOT NULL DEFAULT 0`; login puts `tv` in the JWT.
- `get_current_user` compares the claim with the user's version. The user record
  is already fetched (or cached) on every request, so the check adds no extra lookup.
  The WebSocket handshake checks it too.
- `POST /auth/logout` and password reset do `token_version = token_version + 1`
  (atomic, in SQL) and invalidate the user cache, so the next request is rejected
  even on a cache hit.
- Tokens issued before this change have no `tv` claim and are read as 0, so the
  deploy logs nobody out.

## Consequences

- Revocation is durable (it lives in Postgres, the source of truth) and needs no
  extra storage or expiry.
- The cost: **logout ends every session of that user** (laptop and phone).
  Per-device logout would need option 2 as well. For an exam platform,
  "log out everywhere" on logout or password reset is acceptable, and arguably
  the right default.
- Combined with the 60 s user cache: invalidation on bump makes revocation
  immediate for the flows that bump; a change made directly in the DB takes ≤ 60 s.
- Tests: `TestTokenRevocation` (logout kills the token and every other session;
  re-login works; tokens without `tv` still work; revocation beats the cache).
