---
name: vmlu-eval-ops
description: Run, resume, compare, or package a VMLU evaluation condition when the user asks to execute a benchmark pipeline or prepare its submission.
---

# VMLU Evaluation Operations

Use this workflow for MC, Reading-400, V-Bench, Harness, and other evaluation arms present in the repository.

## Workflow

1. Identify the exact arm, dataset/split, model tag, condition label, endpoint, and requested artifact. For newer or experimental arms, read that arm's protocol and runner rather than borrowing assumptions from the original MC pipeline.
2. Read the runner's current CLI and input contract. Work from the repository root with `.venv/bin/python` for dependency-using runners. The harness runner also requires a `HOME` override and an absolute `--agent-dir` as documented in `AGENTS.md`.
3. Check the selected inputs and destination before execution. Preserve existing checkpoints and results; use resume/retry options only when the request calls for them. Keep model sanitization separate from reviewer `slug()` values.
4. Run only the requested condition. A request to execute an evaluation authorizes its endpoint calls; do not add extra models, arms, retries, or external uploads. Do not expose endpoint credentials in output.
5. Inspect the produced files for expected coverage, columns, and submission shape. Unparseable answers remain in the denominator. For V-Bench, local outputs are submissions for server-side scoring; they are not locally gold-scored.

## Contract boundaries

- Keep the frozen MC prompt and `build_prompt` / `extract_answer` behavior intact unless the user explicitly requests a protocol change.
- Treat the Reading-400 manifest as pre-registered. Use its existing rows and the documented scoring workflow; do not regenerate the sample as a run preflight.
- Harness conditions use the same item prompts and one condition per label. Do not silently change tools, system prompt, or label while reproducing a condition.
- For any other arm, use its own versioned protocol, manifest, and scorer. Do not assume its metrics or data files match the legacy arms.

Finish by reporting the arm and condition run, the output paths, coverage, and any parsing or scoring limitations visible in the artifacts.
