# Angle 3 — Broad exception catches that swallow + default-permissive

## What to look for

- `except Exception:` that returns success / `True` / `None` / a default-permissive value
- `except (aiohttp.ClientError, Exception):` — the broad pair catches practically everything
- Quota/auth/billing checks that default to "allow" when the backing service is unreachable
- Empty `except:` blocks or blocks that only log without raising
- Catch blocks that silently return `None` or an empty list where the caller expects a real result

## Grep seeds

```
except.*Exception
isAuthorized\s*=\s*True
return.*True
except:
except Exception
except.*ClientError.*Exception
pass
```

## Checklist

1. Find all `except Exception` blocks. For each, check: does it return a permissive default (True, None, empty list, empty dict)?
2. Check quota/billing/auth service calls — if the external service fails, does the code fail open (allow) or fail closed (deny)?
3. For empty `except:` blocks — are they genuinely intentional (e.g., shutdown cleanup) or swallowing errors?
4. For try blocks that wrap a database operation — does a failure silently return stale data?

## Known pattern from 2026-06-30 report

- #4: `user_quota.py:56` — `except (aiohttp.ClientError, Exception)` returns `isAuthorized=True`, granting unlimited LLM access when backoffice is down.

## Output

Return each broad-catch that returns a permissive default. Explain what the caller does with the wrong result and what the real-world impact is.
