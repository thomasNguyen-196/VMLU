# Angle 4 — Cross-table / cross-tenant data leaks

## What to look for

- API endpoints that return rows without filtering by `current_user.id`, `owner_id`, or `campaign_id`
- List endpoints that have no mandatory filter scope, or where the scope can be empty
- Subqueries / UNION ALL queries that are missing a recently-added table
- `is_personal` booleans or flags that let the caller bypass ownership checks
- Endpoints that accept `fb_user_id`, `account_id`, or any foreign key as a query param without verifying the caller owns it

## Grep seeds

```
db\.query\(
select\(
session\.exec
UNION ALL
\.all\(\)
\.first\(\)
\.get_user\(\)
\.list_\(
def list_
def get_
```

## Checklist

1. Check every `GET` endpoint — does it filter by `current_user` or equivalent?
2. Find all `UNION ALL` subqueries — do they include every relevant table (including recently-added ones)?
3. For endpoints that accept a `user_id`, `fb_user_id`, `account_id`, `page_id` query param: does the handler verify the caller owns that resource?
4. Check list endpoints when filter context (`campaign_id`, `group_id`) is `None` — does the query safely return empty or does it return ALL rows?

## Known pattern from 2026-06-30 report

- #6: `personal_posts.py:64` — `/api/personal-posts/stats` accepts `fb_user_id` without ownership check.
- #7: `content_reviews.py:347` — empty filter context returns ALL reviews.
- #11: `campaign.py:91` — UNION ALL subquery missing `personal_posts`, `tiktok_posts`, `linkedin_scraped_posts`.

## Output

Return each leaky endpoint or subquery. Include the file, line, what data is leaked, and who can access it.
