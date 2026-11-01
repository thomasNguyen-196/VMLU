## Why

MC-98 stopped the Muse router at the design stage: its grouping scored 66.16 token-F1 on the 591 ViBidLQA design items, against 66.25 for a keyword grouping and 65.88 for always-S. On 2026-10-28 the project owner asked for two things:

- try a second router model, Jev 1.13;
- study the router itself, so that its conclusions do not depend on which model sorts the questions.

**What a router could gain.** An exploratory offline analysis of the existing draws asked whether the per-item benefit of one arm over another repeats across two draws. It used B and S twice each on the wide items, MC-94 and MC-95, and arms K, KS and O on MC-96. Results:

- Per-item benefits repeat only weakly. The correlation between draws of S − B is 0.21 on ViBidLQA, 0.18–0.30 on the other sets, 0.52 on Vi-SQuAD and 0.69 on Vi-DROP.
- The repeatable part is not small, and on reading it runs both ways. On ViBidLQA test, S beats B on both draws for 99 items and B beats S on both draws for 74. On Vi-SQuAD the counts are 5 and 21.
- An oracle that knew each item's repeatable benefit would gain at most 6.6 token-F1 points over always-S on ViBidLQA. This bound uses only the mean and variance of that benefit; a normal approximation gives about 5.
- The routers so far captured much less:
  - Muse +0.28;
  - keywords +0.37;
  - choosing each item's arm on one draw and scoring the other +1.0.

So the earlier reading, that choosing per question had little room left, holds only for the signals tried so far. It is not a ceiling. The limit is the signal the router reads.

**Two kinds of router.**

- A *pre-hoc* router decides from the question and passage before any answer exists. Muse groups, keywords and the dataset rule are pre-hoc.
- A *post-hoc* router lets the cheap arm answer first and looks at that answer before deciding whether to escalate. v2 (two B answers that disagree go to S) and the K→KS cascade are post-hoc, and they gave the largest gains so far: v2 beat always-B by 8.3 points on VMLU.

A post-hoc router can react to the answer that was actually produced, including a bad draw. A pre-hoc router can only predict an item's expected behaviour.

**Jev 1.13.** Jev is a System One model from TypeSafe AI, served free through the OpenCode console endpoint (`jev-1.13-free`) for a limited time.

- It does not generate text. It answers typed questions about a state and returns probabilities: a choice among options, or the probability that a statement is true (noul).
- A non-benchmark probe on 2026-10-28 returned a choice with probabilities at zero cost (`billing_source: free`).
- Its documentation says its primary training language is English, and other languages are accepted with lower accuracy.

## What Changes

- **J1, pre-hoc signals.** Jev reads the passage and question of each of the 967 wide reading items once. It answers the six MC-98 groups as a Choice, with the descriptions translated into English, and seven yes/no questions:
  - asks for a designation;
  - needs computation;
  - asks for a whole list;
  - asks for one part;
  - asks for a condition;
  - answer stated verbatim;
  - passage insufficient.
- **J2, post-hoc signals.** Jev reads the passage, the question and the answer that B actually gave on each of its two wide draws, and gives the probability that the answer is correct, complete, padded with unasked content, and copied verbatim.
- **J3, a post-hoc signal from the student model.** It is offline and sends no request. Qwen's first-token letter probabilities from MC-43/44 (VMLU, temperature 0) are set against the B and S draws of MC-94 and MC-95 on the 660 VMLU items they share.
- **One measurement card, MC-99**, registered before any Jev request on a benchmark item. It covers J1 and J2 (2,901 Jev calls, no student-model request) and the J3 analysis.
- **One analysis plan, fixed before data**, compares every signal on the same footing:
  - cross-fitted routing scores;
  - Qwen tokens;
  - the share of the estimated ideal gain each signal captures.

  A registered reading rule decides which signals go on to a held-out card.

## Capabilities

### New Capabilities
- `diagnostic-router-signals`: router signals from a System One model and from the student model's own confidence, the ceiling estimates, the cross-fitted comparison of pre-hoc and post-hoc policies, and the reading rule that selects policies for held-out evaluation.

### Modified Capabilities
None. MC-90 to MC-98 and their protocols, manifests, rules and analyses stay as registered.

## Non-goals

- No new student-model requests. J1 and J2 reuse the existing B, Q and S draws.
- No held-out evaluation in this change. A promising policy gets its own card later.
- No web search. Its results change over time, and a search could return a benchmark item with its answer.
- No training of any model. The learned rule in J1 is a ridge regression on Jev's probabilities, with fixed settings.
- No gold answer, score or audit field reaches Jev.

## Impact

- New data in `data/diagnostic_router_signals/`: configuration, frozen manifest and registration.
- New code:
  - `diagnostic_router_signals.py` (requests and manifest);
  - `run_router_signals.py` (runner and gates);
  - `analyze_router_signals.py` (plan `diagnostic-router-signals-v1`);
  - tests.
- Outputs go to the ignored `all_res/diagnostic_router_signals/`.
