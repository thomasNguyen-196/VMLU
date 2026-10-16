---
name: vmlu-review-ops
description: Build or reconcile VMLU human-review workbooks and review exports, or refresh the review UI data after answer changes.
---

# VMLU Human Review Operations

Use this workflow for annotation workbooks, reviewer CSV exports, `review_records/`, review-state data, and the reading review UI.

## Choose the correct review path

- `build` creates the independent blind workbooks. Keep model answers out of this pass.
- `merge` compares the two blind workbooks; `merge-split` combines split-owned review records.
- `review` consumes model-visible UI exports. Its accept/reject semantics differ from blind annotation; read the script's current help and docstring before choosing it.
- `build_review_ui.py export-blob` refreshes the Next.js review app data. `build` creates the standalone HTML fallback.

Use `itemKey` / `dataset:item_id` as the join identity. Preserve reviewer, model, decision, correction, and note provenance. Let duplicate keys, schema drift, unknown items, or incomplete coverage fail visibly; do not guess or silently drop records.

## Applying annotations

Merges without `--apply` produce agreed and adjudication files for inspection. `--apply` writes agreed answers into the tracked pre-registration manifest. Use it only when the user explicitly asks to apply those agreed answers; leave unresolved items for adjudication. Never invent gold answers or apply the model-visible review pass as blind annotation.

Before writing, inspect existing workbooks, review records, and output files so prior human work is preserved. Avoid replacing filled artifacts with freshly generated blank templates. After source answer files used by the review UI change, regenerate `web/data/review-blob.json` through `build_review_ui.py export-blob`.

Keep `review_state/` as local reviewer state and `review_records/` as the shared sync record. Do not commit or push review records unless the user asks for that handoff.

Finish with the selected path, files read/written, counts of agreed/disputed/unset items when available, and whether the manifest was changed.
