"""Offline tests for the rule-based router, its evaluator and the anchor diagnosis (design Decisions 11 and 12).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_router
Synthetic items and outcomes only: no data, no network. Expected values are worked out in the comments.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from code_benchmark import analyze_diagnostic_router as ar
from code_benchmark import diagnostic
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_router as router
from code_benchmark import vi_multimodel as v1

MC, NLI, SQUAD, DROP, BID = (f"vi-multimodel-v1-{name}" for name in
                             ("legal-mc-146", "legal-nli-150", "vi-squad-200", "vi-drop-200", "bidlqa-test"))
DATASETS = (MC, NLI, SQUAD, DROP, BID)


def make_item(dataset: str, item_id: str, question: str = "Câu hỏi thử?", passage: str = "Đoạn văn thử.",
              options: tuple[str, ...] = ("một", "hai", "ba", "bốn"), gold: str = "A") -> v1.EvalItem:
    if dataset in (MC, NLI):
        body = question + "\n\n" + "\n".join(f"{letter}. {text}" for letter, text in zip("ABCDE", options, strict=False))
        task, prompt = "multiple_choice", dp.MC_HEAD + body + dp.MC_TAIL
    else:
        task, prompt = "reading", dp.RD_HEAD + passage + dp.RD_QUESTION + question + dp.RD_TAIL
    return v1.EvalItem(dataset_id=dataset, source_dataset="test", item_id=item_id, replicate_id=dp.MAIN_REPLICATE,
                       task=task, stratum="s", question=question, passage_id=f"p-{item_id}", prompt=prompt,
                       gold_answer=gold)


def rule(*conditions: dict, default: dict | None = None) -> dict:
    return {"router_id": "test", "conditions": list(conditions), "default": default or {"arm": "B", "targets": []}}


def cond(arm: str, targets: list[str], **when) -> dict:
    return {"arm": arm, "targets": targets, "when": when}


def decide(the_rule: dict, item: v1.EvalItem) -> router.Decision:
    return router.route(router.validate_rule(the_rule, DATASETS), router.features_of(router.request_view(item)))


def all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in all_keys(item)}
    return set()


def raises(test: unittest.TestCase, the_rule: dict, *fragments: str) -> None:
    with test.assertRaises(SystemExit) as caught:
        router.validate_rule(the_rule, DATASETS)
    for fragment in fragments:
        test.assertIn(fragment, str(caught.exception))


class TestGrammar(unittest.TestCase):
    def test_forbidden_feature_fails_and_names_the_key(self):
        raises(self, rule(cond("S", ["reasoning_gap"], gold_validity=["valid"])), "gold_validity", "not a router feature")
        raises(self, rule(cond("S", ["reasoning_gap"], dataset=[DROP], b_outcome=[False])), "b_outcome")

    def test_keys_outside_the_grammar_fail(self):
        raises(self, {**rule(), "weights": {}}, "weights")
        raises(self, rule({**cond("S", ["reasoning_gap"], dataset=[DROP]), "audit": "x"}), "audit")
        raises(self, rule(default={"arm": "B", "targets": [], "note": "x"}), "note")

    def test_oracle_arm_is_not_deployable(self):
        raises(self, rule(cond("O", ["external_evidence_gap"], dataset=[MC])), "arm O is not deployable")
        raises(self, rule(default={"arm": "O", "targets": []}), "arm O is not deployable")
        raises(self, rule(cond("X", [], dataset=[MC])), "'X'")

    def test_an_arm_must_be_able_to_address_its_targets(self):
        raises(self, rule(cond("S", ["external_evidence_gap"], dataset=[MC])), "arm S cannot address",
               "external_evidence_gap")
        raises(self, rule(cond("B", ["reasoning_gap"], dataset=[MC])), "arm B cannot address")
        raises(self, rule(cond("K", [], dataset=[MC])), "arm K must name at least one")
        raises(self, rule(cond("S", ["reasoning_gap", "reasoning_gap"], dataset=[MC])), "distinct")
        router.validate_rule(rule(cond("KS", ["reasoning_gap", "external_evidence_gap"], dataset=[MC])), DATASETS)

    def test_feature_values_are_checked(self):
        raises(self, rule(cond("S", ["reasoning_gap"], dataset=["vmlu"])), "campaign datasets")
        raises(self, rule(cond("S", ["reasoning_gap"], b_prompt_chars={"at_least": 10, "below": 5})), "at_least")
        raises(self, rule(cond("S", ["reasoning_gap"], b_prompt_chars={"max": 5})), "b_prompt_chars")
        raises(self, rule(cond("S", ["reasoning_gap"], b_prompt_chars={"at_least": True})), "b_prompt_chars")
        raises(self, rule(cond("S", ["reasoning_gap"], question_cues=["Bao nhiêu", "bao  nhiêu"])), "repeats a cue")
        raises(self, rule(cond("S", ["reasoning_gap"], question_cues=["  "])), "question_cues")
        raises(self, rule({"arm": "S", "targets": ["reasoning_gap"], "when": {}}), "non-empty")

    def test_addressable_labels_come_from_the_audit_taxonomy(self):
        labels = frozenset().union(*router.ADDRESSABLE.values())
        self.assertTrue(labels <= diagnostic.DIAGNOSTIC_LABELS)
        self.assertNotIn("measurement_gap", labels)  # no arm fixes a scoring problem

    def test_fixed_policies_are_rules_of_the_same_grammar(self):
        for arm in ("B", "S"):
            fixed = router.validate_rule(router.fixed_rule(arm), DATASETS)
            self.assertEqual(decide(fixed, make_item(DROP, "1")).arm, arm)

    def test_load_rule_returns_the_hash_of_the_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rule.json"
            path.write_text(json.dumps(rule(cond("S", ["reasoning_gap"], dataset=[DROP]))), encoding="utf-8")
            loaded, digest = router.load_rule(path, DATASETS)
            self.assertEqual(digest, v1.sha256_bytes(path.read_bytes()))
            self.assertEqual(loaded["conditions"][0]["arm"], "S")


class TestRouting(unittest.TestCase):
    def test_first_matching_condition_decides(self):
        the_rule = rule(cond("K", ["external_evidence_gap"], dataset=[MC]),
                        cond("S", ["reasoning_gap"], question_cues=["bao nhiêu"]),
                        cond("KS", ["reasoning_gap"], dataset=[DROP]))
        decision = decide(the_rule, make_item(DROP, "1", question="Có bao nhiêu người?"))
        self.assertEqual((decision.arm, decision.condition, decision.targets), ("S", 2, ("reasoning_gap",)))
        self.assertEqual(decide(the_rule, make_item(SQUAD, "2")), router.Decision("B", (), None))

    def test_every_feature_of_a_condition_must_hold(self):
        the_rule = rule(cond("S", ["reasoning_gap"], dataset=[DROP], question_cues=["tổng"]))
        self.assertEqual(decide(the_rule, make_item(DROP, "1", question="Ai thắng?")).arm, "B")
        self.assertEqual(decide(the_rule, make_item(SQUAD, "2", question="Tổng là bao nhiêu?")).arm, "B")
        self.assertEqual(decide(the_rule, make_item(DROP, "3", question="Tổng là bao nhiêu?")).arm, "S")

    def test_cues_match_whole_words_whatever_the_case_or_unicode_form(self):
        the_rule = rule(cond("S", ["reasoning_gap"], question_cues=["ai", "bao nhiêu"]))
        self.assertEqual(decide(the_rule, make_item(DROP, "1", question="Đội hai thắng mấy trận?")).arm, "B")
        self.assertEqual(decide(the_rule, make_item(DROP, "2", question="Ai thắng?")).arm, "S")
        decomposed = unicodedata.normalize("NFD", "BAO   NHIÊU người?")
        self.assertEqual(decide(the_rule, make_item(DROP, "3", question=decomposed)).arm, "S")

    def test_cues_are_read_in_the_question_only(self):
        the_rule = rule(cond("S", ["reasoning_gap"], question_cues=["tổng"]))
        self.assertEqual(decide(the_rule, make_item(DROP, "1", passage="Tổng số là 5.", question="Ai?")).arm, "B")
        options = ("tổng hai", "ba", "bốn", "năm")
        self.assertEqual(decide(the_rule, make_item(MC, "2", question="Chọn đáp án?", options=options)).arm, "B")
        self.assertEqual(decide(the_rule, make_item(MC, "3", question="Tổng là gì?")).arm, "S")

    def test_prompt_length_lower_bound_is_inclusive_and_upper_bound_exclusive(self):
        item = make_item(SQUAD, "1")
        size = len(item.prompt)
        self.assertEqual(decide(rule(cond("S", ["reasoning_gap"], b_prompt_chars={"at_least": size})), item).arm, "S")
        self.assertEqual(decide(rule(cond("S", ["reasoning_gap"], b_prompt_chars={"below": size})), item).arm, "B")
        self.assertEqual(router.features_of(router.request_view(item)).b_prompt_chars, size)

    def test_the_router_never_sees_the_gold(self):
        the_rule = rule(cond("S", ["reasoning_gap"], question_cues=["một"]))
        first, second = make_item(MC, "1", gold="A"), make_item(MC, "1", gold="D")
        self.assertEqual(router.features_of(router.request_view(first)), router.features_of(router.request_view(second)))
        self.assertEqual(decide(the_rule, first), decide(the_rule, second))
        self.assertFalse(hasattr(router.request_view(first), "gold_answer"))

    def test_the_router_reads_the_frozen_b_prompt_only(self):
        with self.assertRaises(SystemExit):
            router.request_view(dataclasses.replace(make_item(MC, "1"), replicate_id="S-r1"))


# ---------------------------------------------------------------- evaluator fixtures

def attempt(key: str, arm: str, replicate: int, ok: bool, tokens: int | None = 100) -> dict:
    dataset_id, item_id = key.split(":", 1)
    row = {"dataset_id": dataset_id, "item_id": item_id, "replicate_id": f"{arm}-r{replicate}", "arm": arm,
           "correct": int(ok)}
    if tokens is not None:
        row["total_tokens"] = tokens
    return row


def outcomes_to_rows(spec: dict[str, dict[str, list[bool]]], tokens: dict[str, int] | None = None) -> list[dict]:
    tokens = tokens or {"B": 100, "S": 500, "O": 300, "K": 300, "KS": 700}
    return [attempt(key, arm, n, ok, tokens[arm]) for key, arms in spec.items() for arm, draws in arms.items()
            for n, ok in enumerate(draws, 1)]


def judgment(outcome: str = "no_observed_issue", labels: tuple[str, ...] = (), gold: str = "valid",
             sufficiency: str = "sufficient") -> dict:
    return {"diagnostic_outcome": outcome, "diagnostic_labels": list(labels), "gold_validity": gold,
            "input_evidence_sufficiency": sufficiency, "hypothesis_status": {label: "hypothesis" for label in labels}}


RIGHT, WRONG = [True, True, True], [False, False, False]
DROP_RULE = rule(cond("S", ["reasoning_gap"], dataset=[DROP]))
KS_RULE = rule(cond("KS", ["reasoning_gap", "external_evidence_gap"], dataset=[MC]))


def core_case(the_rule: dict = DROP_RULE):
    """Four anchors. d1, d2 (DROP) go to S under DROP_RULE; m1 (Legal MC, an evidence anchor) and s1 (SQuAD)
    stay on B. B is right on m1 and s1 only; S rescues d1 and d2 and regresses s1."""
    items = [make_item(DROP, "d1"), make_item(DROP, "d2"), make_item(MC, "m1"), make_item(SQUAD, "s1")]
    spec = {f"{DROP}:d1": {"B": WRONG, "S": RIGHT}, f"{DROP}:d2": {"B": WRONG, "S": RIGHT},
            f"{MC}:m1": {"B": RIGHT, "S": RIGHT, "O": RIGHT, "K": WRONG, "KS": RIGHT},
            f"{SQUAD}:s1": {"B": RIGHT, "S": WRONG}}
    arms = {key: set(value) for key, value in spec.items()}
    diagnosis = {f"{DROP}:d1": judgment("issue_observed", ("reasoning_gap",)),
                 f"{DROP}:d2": judgment("issue_observed", ("measurement_gap",), gold="suspect"),
                 f"{MC}:m1": judgment("issue_observed", ("external_evidence_gap",), sufficiency="insufficient"),
                 f"{SQUAD}:s1": judgment()}
    validated = router.validate_rule(copy.deepcopy(the_rule), DATASETS)
    return validated, router.route_items(validated, items), arms, outcomes_to_rows(spec), diagnosis


REGISTERED = {"rule_sha256": "r" * 64, "anchor_diagnosis_sha256": "d" * 64, "best_fixed_arm": "S"}


def run_evaluate(the_rule: dict = DROP_RULE, **overrides):
    validated, decisions, arms, rows, diagnosis = core_case(the_rule)
    arguments = {"rule": validated, "rule_sha256": "r" * 64, "registered": REGISTERED, "decisions": decisions,
                 "manifest_arms": arms, "rows": rows, "diagnosis": diagnosis, "diagnosis_sha256": "d" * 64}
    arguments.update(overrides)
    return ar.evaluate(**arguments)


class TestCoreEvaluation(unittest.TestCase):
    def test_a_changed_rule_or_diagnosis_exits_naming_both_hashes(self):
        with self.assertRaises(SystemExit) as caught:
            run_evaluate(rule_sha256="x" * 64)
        self.assertIn(f"{'x' * 64} differs from the registered {'r' * 64}", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            run_evaluate(diagnosis_sha256="y" * 64)
        self.assertIn(f"{'y' * 64} differs from the registered {'d' * 64}", str(caught.exception))

    def test_policies_tests_and_tokens(self):
        report = run_evaluate()
        self.assertEqual(tuple(report), ar.ROUTER_REPORT_KEYS)
        policies, tests = report["primary"]["policies"], report["primary"]["tests"]
        # router: d1 S ok, d2 S ok, m1 B ok, s1 B ok -> 4/4; always-B 2/4; always-S 3/4 (s1 wrong)
        self.assertEqual([policies[p]["correct"] for p in ("router", "always_B", "always_S", "best_fixed")], [4, 2, 3, 3])
        self.assertEqual((tests["router_vs_always_B"]["rescues"], tests["router_vs_always_B"]["regressions"]), (2, 0))
        self.assertEqual(tests["router_vs_always_B"]["mcnemar_p"], 0.5)        # 2 * (1/2)^2
        self.assertEqual(tests["router_vs_always_S"]["mcnemar_p"], 1.0)        # one discordant item
        self.assertEqual(tests["router_vs_always_B"]["mcnemar_p_holm"], 1.0)   # min(1, 2 * 0.5)
        # router tokens: S 500, S 500, B 100, B 100 -> 300
        self.assertEqual(policies["router"]["mean_total_tokens"], 300)
        self.assertEqual(policies["router"]["tokens_unknown_items"], 0)

    def test_unknown_usage_is_unknown_not_zero(self):
        *_, rows, _ = core_case()
        for row in rows:
            if row["item_id"] == "s1" and row["arm"] == "B" and row["replicate_id"] == "B-r2":
                del row["total_tokens"]
        report = run_evaluate(rows=rows)
        always_b = report["primary"]["policies"]["always_B"]
        self.assertEqual((always_b["mean_total_tokens"], always_b["tokens_unknown_items"]), (100, 1))

    def test_an_evidence_arm_without_evidence_leaves_the_anchor_out_for_every_policy(self):
        _, _, arms, _, _ = core_case(KS_RULE)
        arms[f"{MC}:m1"] = {"B", "S"}
        report = run_evaluate(KS_RULE, manifest_arms=arms)
        self.assertEqual((report["anchors"], report["evaluation_set"]), (4, 3))
        self.assertEqual(report["excluded_anchors"][0]["item_key"], f"{MC}:m1")
        self.assertTrue(all(policy["n"] == 3 for policy in report["primary"]["policies"].values()))

    def test_the_secondary_block_drops_gold_that_is_not_valid(self):
        secondary = run_evaluate()["secondary_valid_gold"]
        self.assertEqual((secondary["removed"], secondary["removed_anchors"]), (1, [f"{DROP}:d2"]))
        self.assertEqual(secondary["policies"]["router"]["n"], 3)

    def test_the_deployable_ceiling_leaves_arm_o_out(self):
        _, _, arms, rows, _ = core_case()
        rows += [attempt(f"{SQUAD}:s1", "O", n, True) for n in (1, 2, 3)]
        arms[f"{SQUAD}:s1"].add("O")
        with_o = run_evaluate(rows=rows, manifest_arms=arms)["deployable_ceiling"]
        self.assertEqual(with_o, run_evaluate()["deployable_ceiling"])

    def test_detection_scores_the_routing_without_steering_it(self):
        validated, decisions, *_ = core_case()
        report = run_evaluate()
        detection = report["detection"]
        self.assertEqual(router.route_items(validated, [make_item(DROP, "d1")])[f"{DROP}:d1"], decisions[f"{DROP}:d1"])
        # d1 reasoning_gap -> S targets it; d2 measurement_gap -> no arm addresses it; m1 external_evidence_gap -> B
        self.assertEqual((detection["anchors_with_hypotheses"], detection["anchors_with_addressable_hypotheses"],
                          detection["detected"]), (3, 2, 1))
        self.assertFalse(detection["per_label"]["measurement_gap"]["addressable_by_a_deployable_arm"])
        self.assertEqual(detection["per_label"]["external_evidence_gap"]["sent_to_a_targeting_arm"], 0)
        self.assertEqual((detection["no_issue_anchors"], detection["no_issue_sent_beyond_B"]), (1, 0))

    def test_detection_counts_no_issue_anchors_sent_beyond_b(self):
        always_s = router.fixed_rule("S")
        detection = run_evaluate(always_s)["detection"]
        self.assertEqual(detection["no_issue_sent_beyond_B"], 1)
        self.assertEqual(detection["detected"], 1)  # d1 only: S does not target external_evidence_gap

    def test_a_missing_attempt_fails_closed(self):
        *_, rows, _ = core_case()
        rows = [row for row in rows if not (row["item_id"] == "d1" and row["arm"] == "S")]
        with self.assertRaises(SystemExit) as caught:
            run_evaluate(rows=rows)
        self.assertIn("no scored attempt", str(caught.exception))


# ---------------------------------------------------------------- wide design fit

def wide_case():
    """Three wide items with two draws per arm. d1 (DROP): B 0/2, S 2/2. s1 (SQuAD): B 2/2, S 1/2. m1 (Legal MC):
    B 1/2, S 1/2. Reading pair 1: d1 is an EM rescue, s1 an EM regression (S-r1 wrong)."""
    items = [make_item(DROP, "d1"), make_item(SQUAD, "s1"), make_item(MC, "m1")]
    rows = []
    for key, draws in ((f"{DROP}:d1", {"B": [0, 0], "S": [1, 1]}), (f"{SQUAD}:s1", {"B": [1, 1], "S": [0, 1]}),
                       (f"{MC}:m1", {"B": [1, 0], "S": [0, 1]})):
        for arm, values in draws.items():
            for n, ok in enumerate(values, 1):
                row = attempt(key, arm, n, bool(ok), 100 if arm == "B" else 500)
                if not key.startswith(MC):
                    row["em"] = row.pop("correct")
                rows.append(row)
    return items, rows


class TestDesignFit(unittest.TestCase):
    def test_design_fit_averages_two_draws_and_carries_no_test_or_interval(self):
        items, rows = wide_case()
        fit = ar.design_fit(router.validate_rule(DROP_RULE, DATASETS), "h" * 64, items, rows)
        # router: d1 S 1.0, s1 B 1.0, m1 B 0.5 -> 2.5/3; always-B (0 + 1 + 0.5)/3; always-S (1 + 0.5 + 0.5)/3
        self.assertAlmostEqual(fit["accuracy"]["router"], 2.5 / 3)
        self.assertAlmostEqual(fit["accuracy"]["always_B"], 1.5 / 3)
        self.assertAlmostEqual(fit["accuracy"]["always_S"], 2.0 / 3)
        self.assertAlmostEqual(fit["accuracy_by_draw_pair"]["1"]["router"], 3 / 3)  # S-r1 d1, B-r1 s1, B-r1 m1
        self.assertTrue(fit["design_fit"])
        self.assertFalse({key for key in all_keys(fit) if "mcnemar" in key or key.endswith("_p") or "ci95" in key})

    def test_items_sent_to_evidence_arms_are_not_measurable_on_wide(self):
        items, rows = wide_case()
        fit = ar.design_fit(router.validate_rule(KS_RULE, DATASETS), "h" * 64, items, rows)
        self.assertEqual((fit["routed"], fit["not_measurable_on_wide"]), ({"B": 2, "KS": 1}, 1))
        self.assertIsNone(fit["by_condition"][0]["router"])

    def test_the_semantic_block_separates_measurement_effects(self):
        items, rows = wide_case()
        semantic = {f"{DROP}:d1": {"direction": "rescue", "loser_right_in_meaning": False},
                    f"{SQUAD}:s1": {"direction": "regression", "loser_right_in_meaning": True}}
        fit = ar.design_fit(router.validate_rule(DROP_RULE, DATASETS), "h" * 64, items, rows, semantic)
        groups = {g["condition"]: g for g in fit["semantic_review"]["groups"]}
        self.assertEqual((groups[1]["em_rescues"], groups[1]["em_rescues_measurement_effect"]), (1, 0))
        self.assertEqual((groups["default"]["em_regressions"], groups["default"]["em_regressions_measurement_effect"]),
                         (1, 1))
        del semantic[f"{SQUAD}:s1"]
        with self.assertRaises(SystemExit):
            ar.design_fit(router.validate_rule(DROP_RULE, DATASETS), "h" * 64, items, rows, semantic)

    def test_best_fixed_arm_uses_both_draws(self):
        _, rows = wide_case()
        best = ar.best_fixed_arm(rows)
        # B: draw 1 2/3, draw 2 1/3 -> 0.5; S: draw 1 1/3, draw 2 3/3 -> 2/3
        self.assertEqual(best["arm"], "S")
        self.assertAlmostEqual(best["mean_accuracy_over_two_draws"]["B"], 0.5)

    def test_a_missing_draw_fails_closed(self):
        items, rows = wide_case()
        rows = [row for row in rows if row["replicate_id"] != "B-r2" or row["item_id"] != "d1"]
        with self.assertRaises(SystemExit):
            ar.design_fit(router.validate_rule(DROP_RULE, DATASETS), "h" * 64, items, rows)


# ---------------------------------------------------------------- anchor diagnosis

FINAL = ("FINAL semantic_correctness=incorrect | gold_validity=valid | input_evidence_sufficiency=sufficient | "
         "corpus_evidence_availability=not_assessed | diagnostic_outcome=issue_observed | "
         "observed_issues=answer_mismatch | diagnostic_labels=reasoning_gap;reading_representation_gap || Lý do: thử")


def review_row(key: str, annotator: str, scope: str, **judged) -> dict:
    row = {"observation_key": f"src|{key}:main-000", "annotator_id": annotator, "review_scope": scope,
           "review_status": "reviewed", "semantic_correctness": "correct", "gold_validity": "valid",
           "input_evidence_sufficiency": "sufficient", "corpus_evidence_availability": "not_assessed",
           "diagnostic_outcome": "no_observed_issue", "observed_issues": [], "diagnostic_labels": [],
           "diagnostic_support": []}
    row.update(judged)
    return row


def write_pilot(root: Path, reviews: dict[str, list[dict]], adjudications: list[dict] | None = None) -> list[str]:
    keys = [f"{DATASETS[n % 5]}:I{n:02d}" for n in range(60)]
    pilot = "".join(json.dumps({"dataset_id": k.split(":")[0], "item_id": k.split(":")[1]}) + "\n" for k in keys)
    (root / "pilot.jsonl").write_text(pilot, encoding="utf-8")
    (root / "selection.json").write_text(json.dumps({"pilot_file_sha256": v1.sha256_bytes(pilot.encode()),
                                                     "pilot_content_sha256": "c" * 64}), encoding="utf-8")
    (root / "reviews").mkdir()
    for name, rows in reviews.items():
        (root / "reviews" / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if adjudications is not None:
        (root / "adjudications.jsonl").write_text("".join(json.dumps(a) + "\n" for a in adjudications), encoding="utf-8")
    return keys


class TestAnchorDiagnosis(unittest.TestCase):
    def test_final_judgment_parses_every_field_and_fails_closed(self):
        vocabulary = dp.judgment_vocabulary()
        judged = dp.final_judgment(FINAL, vocabulary)
        self.assertEqual(judged["diagnostic_labels"], ["reading_representation_gap", "reasoning_gap"])
        self.assertEqual(judged["observed_issues"], ["answer_mismatch"])
        for broken in (FINAL.replace("FINAL ", ""), FINAL.replace(" || Lý do: thử", ""),
                       FINAL.replace("gold_validity=valid", "gold_validity=maybe"),
                       FINAL.replace(" | corpus_evidence_availability=not_assessed", ""),
                       FINAL.replace("reasoning_gap;", "reasoning_gap;reasoning_gap;"),
                       FINAL.replace("gold_validity=valid", "gold_validity=valid | gold_validity=valid")):
            with self.assertRaises(SystemExit):
                dp.final_judgment(broken, vocabulary)

    def test_agreement_single_review_and_adjudication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keys = [f"{DATASETS[n % 5]}:I{n:02d}" for n in range(60)]
            primary = [review_row(k, "p", "primary-60") for k in keys]
            primary[2]["diagnostic_outcome"], primary[2]["observed_issues"] = "issue_observed", ["answer_mismatch"]
            primary[2]["semantic_correctness"] = "incorrect"
            second = [review_row(keys[1], "b", "independent-15"), review_row(keys[2], "b", "independent-15")]
            adjudication = {"observation_key": f"src|{keys[2]}:main-000", "decision": "resolved", "rationale": FINAL}
            write_pilot(root, {"p": primary, "b": second}, [adjudication])
            records, inputs = dp.anchor_diagnosis(root)
            sources = [r["judgment_source"] for r in records[:3]]
            self.assertEqual(sources, ["single_review", "agreed", "adjudicated"])
            self.assertEqual(records[2]["diagnostic_labels"], ["reading_representation_gap", "reasoning_gap"])
            self.assertEqual(records[2]["hypothesis_status"], {"reading_representation_gap": "hypothesis",
                                                               "reasoning_gap": "hypothesis"})
            self.assertEqual(set(inputs), {"reviews/p.jsonl", "reviews/b.jsonl", "adjudications.jsonl"})
            path = root / "diagnosis.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            mapping, digest = dp.load_anchor_diagnosis(path)
            self.assertEqual((len(mapping), digest), (60, v1.sha256_bytes(path.read_bytes())))

    def test_disagreement_without_a_resolved_adjudication_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keys = [f"{DATASETS[n % 5]}:I{n:02d}" for n in range(60)]
            primary = [review_row(k, "p", "primary-60") for k in keys]
            second = [review_row(keys[1], "b", "independent-15", gold_validity="suspect")]
            write_pilot(root, {"p": primary, "b": second},
                        [{"observation_key": f"src|{keys[1]}:main-000", "decision": "deferred", "rationale": "later"}])
            with self.assertRaises(SystemExit) as caught:
                dp.anchor_diagnosis(root)
            self.assertIn("disagree", str(caught.exception))

    def test_an_anchor_without_a_review_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keys = [f"{DATASETS[n % 5]}:I{n:02d}" for n in range(60)]
            write_pilot(root, {"p": [review_row(k, "p", "primary-60") for k in keys[:-1]]})
            with self.assertRaises(SystemExit) as caught:
                dp.anchor_diagnosis(root)
            self.assertIn("no imported review", str(caught.exception))

    def test_the_loader_rejects_values_outside_the_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diagnosis.jsonl"
            record = {"dataset_id": MC, "item_id": "1", "judgment_source": "agreed", "reviewers": ["p"],
                      "semantic_correctness": "correct", "gold_validity": "valid",
                      "input_evidence_sufficiency": "sufficient", "corpus_evidence_availability": "not_assessed",
                      "diagnostic_outcome": "issue_observed", "observed_issues": ["answer_mismatch"],
                      "diagnostic_labels": ["reasoning_gap"], "hypothesis_status": {"reasoning_gap": "hypothesis"}}
            for broken in ({"diagnostic_labels": ["knowledge_gap"], "hypothesis_status": {"knowledge_gap": "hypothesis"}},
                           {"hypothesis_status": {"reasoning_gap": "proven"}}, {"hypothesis_status": {}},
                           {"extra": 1}):
                path.write_text(json.dumps({**record, **broken}) + "\n", encoding="utf-8")
                with self.assertRaises(SystemExit):
                    dp.load_anchor_diagnosis(path)


if __name__ == "__main__":
    unittest.main()
