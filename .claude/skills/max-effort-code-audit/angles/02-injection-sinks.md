# Angle 2 — Input → SQL / shell / exec sink

## What to look for

- User-supplied values embedded directly into raw SQL strings
- `literal_column(f"...{var}...")` with user-controlled variables
- `text(f"SELECT ... WHERE x = '{var}'")` — string interpolation into SQL text
- f-strings into `os.system()`, `subprocess.Popen()`, `subprocess.run()`
- `eval()`, `exec()` called with any part of the input derived from user data
- Raw template rendering where user input is part of the template

## Grep seeds

```
literal_column
f"SELECT
f"INSERT
f"UPDATE
f"DELETE
os\.system
subprocess\.
eval\(
exec\(
execute\(.*f"
```

## Checklist

1. For each `literal_column(f"` occurrence: is the variable user-controlled? If yes, flag.
2. For each `text(f"` or `text("...")`: is user data passed through an f-string or concatenated?
3. For any `os.system`, `subprocess.*`: is the argument string built from request data?
4. For `eval()` / `exec()`: is any input derived from an HTTP request or database value?
5. Check parameterized alternatives: does the code `text("... :param")` with `params=` or is it raw interpolation?

## Known pattern from 2026-06-30 report

- #1: `campaign_member_stats.py:258` — `literal_column(f"'{platform_val}'")` where `platform_val` is user-supplied.

## Output

Return each raw-sink usage where the input source is user-controlled. Include file, line, the interpolated expression, and the parameterized fix.
