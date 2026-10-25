---
name: vmlu-protocols
description: Review or change VMLU evaluation protocols, metrics, prompts, answer extraction, manifests, gold data, or result schemas.
---

# VMLU Protocol and Contract Changes

Use this workflow when a task changes how benchmark items are selected, prompted, scored, identified, or represented. For a code-only bug with no protocol impact, use the normal debugging or review workflow instead.

## Establish the contract

Read the relevant source of truth before editing: `openspec/specs/` (with `eval-scoring/spec.md` authoritative for scoring), the affected runner/scorer, the dataset manifest, `measurement_card.md`, and the corresponding `web/lib/` validator. For versioned or experimental arms, read their versioned protocol and research notes as well. State which contract version and outputs the task affects.

Preserve these boundaries unless the user explicitly requests a protocol revision:

- The original MC prompt and answer-extraction behavior are frozen.
- `data/eval_set_manifest.csv` is a pre-registered item set; do not casually resample or rewrite it. Gold changes go through the documented review/adjudication path.
- V-Bench has no local gold labels and is scored server-side.
- `itemKey=dataset:item_id`, `slug()`, `REVIEW_COLS`, and `SCHEMA_VERSION=1` are shared contracts. Fail fast on drift; never guess a mapping.
- Keep each evaluation arm's metric names, normalization, and denominator tied to its own versioned specification.

## Make a requested revision

When the user explicitly asks to change a contract, make the change traceable across implementation, canonical specification, and affected output validators. Give new protocol or metric behavior a clear version/identifier when old and new results must remain distinguishable. Do not silently backfill historical results, regenerate registered samples, alter unrelated result blocks, or mix gold sources.

When reviewing a proposed change, check item identity and coverage, prompt/extraction parity, score and denominator definitions, serialized column/key order where contractual, and the web validator. Report only concrete drift or a confirmed protocol consequence; separate it from style suggestions.

Finish with the files/contracts affected, compatibility impact on existing artifacts, and the exact verification performed.
