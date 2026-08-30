# Section — Scope lock (Step 1)

## Purpose

Resolve the user-provided scope to a concrete file list with line counts. No findings yet.

## How to run

1. If the user provided a `scope` argument, use it. Otherwise, default to `main...dev` if the repo has both branches, else use the entire working tree.
2. If scope is a git diff range, run:
   ```
   git diff --stat <base>..<head>
   ```
   to get files changed. Then for each file, run `wc -l` to get line counts.
3. If scope is a subdirectory, use `find` or `glob` to list files.
4. Print a summary line:
   ```
   Scope: <branch or path> — N files, N lines changed
   ```
5. If the file count exceeds 500, warn: "Large scope. Consider narrowing to a subdirectory or PR diff. Proceed? (Y/n)"

## Output

A file list saved to memory: `{path: string, lines: number, changed_lines: number}`.

## Notes

- Skip `node_modules/`, `.venv/`, `__pycache__/`, vendor directories, generated code, lockfiles.
- Only include source files: `.py`, `.ts`, `.tsx`, `.js`, `.go`, `.rs`, `.java`, `.kt`, `.swift` for logic issues; add `.yaml`, `.yml`, `.json`, `.sql` for config issues.
- Print the list to the user so they can sanity-check the scope before the 10 sub-agents start.
