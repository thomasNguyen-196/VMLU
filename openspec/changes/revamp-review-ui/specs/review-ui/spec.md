## Purpose

Defines the reviewer-facing behavior of the acceptance-review tool: how a reviewer navigates the 400 items, records decisions, sees progress, exports results, and retains their existing state across the redesign — in both the server-backed and the offline self-contained modes.

## ADDED Requirements

### Requirement: Always-available sequential navigation
The application SHALL keep primary navigation visible on screen at all item positions without scrolling: Previous and Next item controls, the current position (item n of N), and a jump-to-next-unreviewed control. Reaching the first or last item SHALL disable the corresponding direction rather than wrap silently.

#### Scenario: Next advances one item
- **WHEN** the reviewer activates Next on item 12
- **THEN** the view shows item 13 with its passage, question, and the selected model's answer, and no reviewer state is lost

#### Scenario: Boundary held
- **WHEN** the reviewer is on the last item and activates Next
- **THEN** the view stays on the last item and the Next control indicates it is inactive

### Requirement: Full-set decision overview
The application SHALL render an overview of all items in the eval set where each item's state is visible at a glance (unreviewed / accepted / rejected / rejected-with-missing-correction), grouped so items sharing a passage read as one group and the two datasets are distinguishable, with direct jump-to-item from any cell in the overview.

#### Scenario: Live status update
- **WHEN** the reviewer accepts the current item
- **THEN** that item's cell in the overview changes state without a page reload

#### Scenario: Jump from overview
- **WHEN** the reviewer selects an unreviewed cell in the overview
- **THEN** the main view navigates to that item

### Requirement: Decision recording semantics preserved
The application SHALL keep the existing decision model: exactly one decision (accept / reject / unset) per item per (reviewer, model); reject requires a corrected answer and the item is flagged invalid for export until the correction is non-empty; note is optional; acceptance percentage and reviewed counts (overall, per dataset, per stratum) update live.

#### Scenario: Reject without correction
- **WHEN** the reviewer marks an item reject and leaves the correction empty
- **THEN** the item is visibly flagged, and the overview shows it in the invalid state distinct from a complete reject

### Requirement: Dual-mode persistence with state-schema continuity
The application SHALL run in two modes: the Next app (state autosaved to disk per (reviewer, model) through its API routes, with a visible saved-state indicator), and a self-contained static fallback file (state in browser localStorage under the existing namespaced keys and `schema_version: 1` shape, which it remains after the redesign). State exported in either mode SHALL be importable in both, and a reviewer's pre-existing exported state or localStorage data from the current UI SHALL import without loss after the redesign.

#### Scenario: Static fallback offline
- **WHEN** the self-contained HTML file is opened directly from disk with no network
- **THEN** the full review flow (navigate, decide, autosave to localStorage, export) works with no external requests

#### Scenario: Legacy state import
- **WHEN** a reviewer imports a `state_*.json` file exported by the previous UI version
- **THEN** every decision, correction, and note appears in the new UI under the same reviewer and model

### Requirement: Export contract unchanged
The application SHALL produce review CSVs — whether downloaded from the server or generated client-side in static mode — with the same nine columns, ordering, and row semantics the downstream `review` merge expects, so merged results are identical regardless of which mode produced them.

#### Scenario: Mode equivalence
- **WHEN** the same decisions are recorded in server mode and static mode and both are exported
- **THEN** the two CSVs parse to identical (item → decision, correction, note) mappings

### Requirement: Keyboard review protocol
The application SHALL provide keyboard shortcuts for the full review loop (next/previous item, accept, reject, clear decision, focus correction, focus note, jump to next unreviewed, show shortcut help) that are inert while the reviewer is typing in a text field, and SHALL respect `prefers-reduced-motion` by disabling non-essential animation.

#### Scenario: Typing guard
- **WHEN** focus is inside the note field and the reviewer presses the accept shortcut key
- **THEN** the character is typed into the note and the decision does not change

### Requirement: Reviewer identity gate and blind-protocol copy
The application SHALL require a reviewer name before any review (persisted for return visits), SHALL keep the identity gate, decision, and export labels in Vietnamese-first wording, and SHALL retain the visible reminder that this is the review pass with model answers intentionally visible while the blind 2-annotator gold pass is a separate pipeline.

#### Scenario: Returning reviewer
- **WHEN** a reviewer who previously entered a name reopens the page
- **THEN** review starts without re-asking, and their saved bucket for the selected model is loaded
