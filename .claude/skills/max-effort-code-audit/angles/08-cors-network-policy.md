# Angle 8 — CORS / origin / network policy

## What to look for

- `ALLOWED_ORIGINS` env does not include the actual production or staging frontend URL
- Hardcoded CORS fallback list is outdated or missing current domains
- CORS middleware allows credentialed requests (`allowCredentials: true`) with wildcard `Access-Control-Allow-Origin: *`
- `OPTIONS` preflight requests are not handled or return wrong status
- Proxy/middleware forwards the `Origin` header to a downstream service that has its own CORS check
- CORS config differs between environments (dev vs prod) in ways that would break in production

## Grep seeds

```
ALLOWED_ORIGINS
allow_origins
Access-Control-Allow-Origin
CORSMiddleware
cors
allowCredentials
options
preflight
```

## Checklist

1. Find the CORS middleware or config in each service (backend, bg-jobs, fb-auto-post-service, etc).
2. Check `ALLOWED_ORIGINS` env value in `.env.cicd` / `.env.example` — does it include the actual dev/prod frontend domains?
3. Check the hardcoded fallback list (if env is empty) — is it up to date?
4. Is `Access-Control-Allow-Origin: *` used alongside `Access-Control-Allow-Credentials: true`? This is invalid and browsers reject it.
5. Check proxy routes that forward `Origin` header to downstream services — does the downstream also have a CORS middleware with the same origins?

## Known pattern from 2026-06-30 report

- CORS finding in marketing-background-jobs: `ALLOWED_ORIGINS` was missing `https://dev.markeeai.com`. Requests from the webapp to `/api/proxy/jobs` returned 403.

## Output

Return each CORS/origin gap. Include the file, line, the current allowed list, the expected actual origin, and whether this affects dev, prod, or both.
