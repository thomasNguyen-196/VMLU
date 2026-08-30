# Angle 1 — Authn / Authz bypass

## What to look for

- Missing `current_user` / `get_current_user` dependency on API endpoints
- Hardcoded secret fallbacks (JWT secret, API keys)
- Dev-only auth bypasses that were removed or kept
- Endpoints that accept a user ID or resource ID without verifying ownership
- Credential checks that default to "allow" on error

## Grep seeds

```
JWT_SECRET_KEY
dev-secret
get_current_user
Depends(
ProxyUser
# Dev mode auth bypass
ENV=dev
```

## Checklist

1. For every `.py` file in `apis/`, check that each endpoint function has `current_user: CurrentUser` or `Depends(get_current_user)` in its signature.
2. Find all hardcoded secret strings — if any is used as a fallback, flag it.
3. Search for dev-mode bypasses (`ENV=dev`, `dev-bypass-token`, test-only paths) that are reachable at runtime.
4. Check endpoints that accept a `user_id`, `fb_user_id`, `account_id` query param — does the handler verify the caller owns that resource?
5. Check `get_jwt_secret_key()` and similar — do they have a plaintext fallback?

## Known pattern from 2026-06-30 report

- #2: `get_jwt_secret_key()` fallback to hardcoded `'dev-secret-key-change-in-production'` — gated by `_validate_security_settings()`, but the fallback string is still there.
- #8: Dev auth bypass removed from `ENV=dev` path — breaks local development but is a valid security hardening.

## Output

Return candidates where the check fails. Include the file, line, the insecure pattern, and explain why it is insecure.
