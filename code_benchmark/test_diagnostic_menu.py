"""Offline tests for arm Q and the menu design set of the LLM router (openspec change diagnostic-llm-router).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_menu
Synthetic items except where a test says it rebuilds the committed manifest from local sources.
"""
from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_menu_q as am
from code_benchmark import diagnostic_menu as menu
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_menu_q as runner
from code_benchmark import vi_multimodel as v1

PROTOCOL = menu.load_protocol()
HEAD = PROTOCOL["prompts"]["Q"]["head"]
RD_DATASET = "vi-multimodel-v1-bidlqa-test"
PASSAGE = "Điều 27. Hồ sơ dự thầu khoản 2 . Nhà thầu nộp hồ sơ trong thời hạn 7 ngày làm việc."
QUESTION = "Nhà thầu nộp hồ sơ trong thời hạn bao lâu?"


def reading_item(gold: str = "7 ngày làm việc", item_id: str = "T1") -> v1.EvalItem:
    return v1.EvalItem(dataset_id=RD_DATASET, source_dataset="bidlqa", item_id=item_id,
                       replicate_id=dp.MAIN_REPLICATE, task="reading", stratum="all", question=QUESTION,
                       passage_id="p1", prompt=v1.build_reading_prompt(PASSAGE, QUESTION), gold_answer=gold)


def prediction(item: v1.EvalItem, raw: str) -> dict:
    return {"dataset_id": item.dataset_id, "item_id": item.item_id, "replicate_id": item.replicate_id,
            "status": "complete", "finish_reason": "stop", "prompt_sha256": v1.sha256_bytes(item.prompt.encode()),
            "raw_response": raw, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "latency_s": 1.0}


class TestProtocol(unittest.TestCase):
    def test_the_committed_protocol_loads_and_copies_no_inherited_block(self):
        self.assertEqual(PROTOCOL["datasets"], list(menu.DATASETS))
        self.assertEqual(PROTOCOL["phases"], {"menu": {"arms": ["Q"], "replicates": 2}})
        self.assertFalse(set(menu.INHERITED) & set(PROTOCOL))

    def test_out_of_contract_protocols_are_refused(self):
        q = PROTOCOL["prompts"]["Q"]
        bad = [{**PROTOCOL, "model": {}}, {**PROTOCOL, "datasets": list(menu.DATASETS)[:2]},
               {**PROTOCOL, "phases": {"menu": {"arms": ["Q"], "replicates": 3}}},
               {**PROTOCOL, "phases": {"menu": {"arms": ["Q", "B"], "replicates": 2}}},
               {**PROTOCOL, "prompts": {**PROTOCOL["prompts"], "Q": {**q, "question": "\nCâu hỏi: "}}},
               {**PROTOCOL, "prompts": {**PROTOCOL["prompts"], "Q": {**q, "tail": ""}}},
               {**PROTOCOL, "parent": {**PROTOCOL["parent"], "source_manifest": "data/other.json"}},
               {**PROTOCOL, "protocol_version": 2}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "protocol.json"
            for value in bad:
                path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    menu.load_protocol(path)


class TestPrompt(unittest.TestCase):
    def test_q_prompt_is_head_passage_question_label_question_newline(self):
        item = reading_item(gold="zzgoldzz")
        prompt = menu.q_prompt(item, PROTOCOL)
        self.assertEqual(prompt, HEAD + PASSAGE + "\n\nCâu hỏi: " + QUESTION + "\n")
        self.assertNotIn("zzgoldzz", prompt)
        self.assertFalse(prompt.endswith("Trả lời: "))

    def test_multiple_choice_items_and_the_campaign_builder_refuse_q(self):
        mc = dataclasses.replace(reading_item(), task="multiple_choice",
                                 prompt=dp.MC_HEAD + "Câu hỏi?\n\nA. một\nB. hai" + dp.MC_TAIL)
        with self.assertRaises(SystemExit):
            menu.q_prompt(mc, PROTOCOL)
        with self.assertRaises(SystemExit):
            dp.build_arm_prompt(reading_item(), "Q", dp.load_templates())


class TestScoring(unittest.TestCase):
    def score(self, raws, gold="7 ngày làm việc"):
        items = [dataclasses.replace(reading_item(gold, f"T{n}"), replicate_id="Q-r1") for n in range(len(raws))]
        items = [dataclasses.replace(item, prompt=menu.q_prompt(item, PROTOCOL)) for item in items]
        manifest = {"protocol_id": menu.PROTOCOL_ID, "n": len(items), "item_count": len(items),
                    "dataset_counts": {}, "arm_counts": {}, "items": [v1.manifest_item(i) for i in items]}
        manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
        predictions = {item.run_key: prediction(item, raw) for item, raw in zip(items, raws, strict=True)}
        return dp.score_arm_rows(manifest, predictions, {item.run_key: item for item in items})

    def test_q_is_a_replicate_arm_and_the_campaign_protocol_still_loads(self):
        self.assertEqual(dp.arm_of_replicate("Q-r2"), "Q")
        self.assertNotIn("Q", dp.CAMPAIGN_ARMS)
        self.assertEqual(dp.FINAL_LABEL_ARMS, frozenset({"S", "KS", "Q"}))
        self.assertEqual(set(dp.load_protocol()["arms"]), set(dp.CAMPAIGN_ARMS))

    def test_q_is_scored_from_the_final_answer_line_not_the_quote(self):
        raw = "Trích dẫn: Nhà thầu nộp hồ sơ trong thời hạn 7 ngày làm việc.\nTrả lời: 7 ngày làm việc"
        scored, summaries = self.score([raw])
        row = scored[0]
        self.assertEqual((row["prediction"], row["em"], row["token_f1"]), ("7 ngày làm việc", 1, 1.0))
        self.assertEqual((row["arm"], row["scoring_source"], row["format_ok"], row["markdown_final_line"]),
                         ("Q", "raw_last_label", True, False))
        self.assertEqual(row["raw_response"], raw)
        self.assertEqual(summaries["Q"][RD_DATASET]["format_compliance_pct"], 100.0)

    def test_missing_label_and_markdown_are_flagged_and_kept(self):
        scored, summaries = self.score(["7 ngày làm việc kể từ ngày nhận", "Trích dẫn: x\nTrả lời: **7 ngày làm việc**"])
        self.assertEqual((scored[0]["format_ok"], scored[0]["em"]), (False, 0))
        self.assertEqual((scored[1]["markdown_final_line"], scored[1]["em"]), (True, 0))
        summary = summaries["Q"][RD_DATASET]
        self.assertEqual((summary["completed_n"], summary["format_ok_n"], summary["markdown_final_line_n"]), (2, 1, 1))


def cell(**scores: float) -> dict[str, dict]:
    """Six rows from token-F1 values named B1, B2, Q1, Q2, S1, S2."""
    return {name: {"item_id": "T", "token_f1": f1, "em": int(f1 == 1.0), "total_tokens": 100,
                   "prediction": "x", "gold_answer": "x" if f1 == 1.0 else "y"} for name, f1 in scores.items()}


class TestAnalysis(unittest.TestCase):
    # item A: means B 0.5, Q 0.5, S 0.8; draw 1 is won by Q (1.0), draw 2 by S (0.8), so the winner does not repeat;
    # cross = (Q2 0.0 + S1 0.8) / 2 = 0.4; same draws = 0.8. Item C: every draw 1.0, a tie everywhere.
    A = cell(B1=0.5, B2=0.5, Q1=1.0, Q2=0.0, S1=0.8, S2=0.8)
    C = cell(B1=1.0, B2=1.0, Q1=1.0, Q2=1.0, S1=1.0, S2=1.0)

    def test_item_record(self):
        record = am.item_record(self.A)
        self.assertEqual((record["winner"], record["draw1_winner"], record["draw2_winner"], record["repeats"]),
                         ("S", "Q", "S", False))
        self.assertAlmostEqual(record["cross"], 0.4)
        self.assertAlmostEqual(record["same_draws"], 0.8)
        tie = am.item_record(self.C)
        self.assertEqual((tie["winner"], tie["repeats"], tie["cross"]), (None, None, 1.0))

    def test_summary_of_two_items(self):
        # B (0.5+0.5+1+1)/4 = 75, Q (1+0+1+1)/4 = 75, S (0.8+0.8+1+1)/4 = 90; bounds (0.4+1)/2 = 70, (0.8+1)/2 = 90
        summary = am.summarize([self.A, self.C])
        self.assertEqual({arm: summary["arms"][arm]["token_f1"] for arm in am.ARMS}, {"B": 75.0, "Q": 75.0, "S": 90.0})
        self.assertEqual(summary["best_fixed_arm"], "S")
        self.assertEqual(summary["winners"], {"B": 0, "Q": 0, "S": 1, "tie": 1})
        self.assertEqual(summary["repeat"], {"decided_both_draws": 1, "same_winner": 0, "same_winner_pct": 0.0})
        self.assertEqual(summary["bounds"], {"cross": 70.0, "same_draws": 90.0})
        self.assertEqual(summary["pairwise"]["Q_vs_B"], {"better": 0, "worse": 0, "equal": 2, "mean_difference": 0.0})
        self.assertEqual(summary["pairwise"]["Q_vs_S"], {"better": 0, "worse": 1, "equal": 1, "mean_difference": -15.0})

    def test_failure_kinds(self):
        cases = [("7 ngày làm việc", "7 ngày", 0.667, "over"), ("7", "7 ngày", 0.667, "partial"),
                 ("abc", "7 ngày", 0.0, "wrong"), ("Uỷ ban nhân dân", "Ủy ban nhân dân", 0.75, "mixed"),
                 ("ủy ban nhân dân xã", "ủy ban nhân dân", 0.889, "near"), ("x", "x", 1.0, "correct")]
        for prediction_text, gold, f1, kind in cases:
            self.assertEqual(am.failure_kind({"prediction": prediction_text, "gold_answer": gold, "token_f1": f1}),
                             kind, prediction_text)


class TestGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "card.md").write_text("card", encoding="utf-8")
        self.manifest = {name: name[0] * 64 for name in runner.FROZEN_KEYS}
        self.registration = {"card_ids": {"menu": "MC-997"}, "card_files": {"menu": "card.md"},
                             "frozen": dict(self.manifest)}
        campaign = dp.load_protocol()
        self.env = {"OPENAI_BASE_URL": f"http://{campaign['model']['endpoint_host']}{campaign['model']['endpoint_path']}",
                    "OPENAI_MODEL": campaign["model"]["requested_id"], "OPENAI_API_KEY": "k"}

    def gates(self, **overrides):
        args = {"manifest": self.manifest, "registration": self.registration, "env": self.env}
        args.update(overrides)
        return {g.name: g for g in runner.evaluate_gates(dp.load_protocol(), args["manifest"], args["registration"],
                                                          args["env"], card_text="## MC-997 — test\n", root=self.root)}

    def test_every_gate_passes_when_registered_and_fails_on_drift(self):
        self.assertTrue(all(g.ok for g in self.gates().values()), {n: g.detail for n, g in self.gates().items()})
        drifted = self.gates(manifest={**self.manifest, "source_manifest_sha256": "x" * 64})["frozen_hashes"]
        self.assertEqual((drifted.ok, drifted.detail), (False, "differ: ['source_manifest_sha256']"))
        self.assertFalse(self.gates(manifest={**self.manifest, "manifest_sha256": "x" * 64})["frozen_hashes"].ok)
        self.assertFalse(self.gates(registration={**self.registration, "card_ids": {"menu": "MC-998"}})
                         ["card_registered"].ok)
        self.assertFalse(self.gates(registration={**self.registration, "card_files": {"menu": "none.md"}})
                         ["detail_card"].ok)
        self.assertFalse(self.gates(env={**self.env, "OPENAI_MODEL": "other"})["endpoint_identity"].ok)


class TestFrozenManifest(unittest.TestCase):
    """Rebuilds the committed manifest from the local benchmark sources; skipped where they are absent."""

    @classmethod
    def setUpClass(cls):
        if not menu.MANIFEST_PATH.is_file():
            raise unittest.SkipTest("the menu manifest is not frozen yet")
        try:
            cls.manifest, cls.rebuilt = menu.build_manifest()
        except (SystemExit, OSError) as exc:
            raise unittest.SkipTest(f"local benchmark sources unavailable: {exc}") from exc

    def test_it_rebuilds_byte_for_byte(self):
        self.assertEqual(self.manifest, menu.load_frozen_manifest())
        self.assertEqual(len(dp.verify_manifest_rows(self.manifest, self.rebuilt)), 1934)

    def test_counts_and_every_q_prompt(self):
        self.assertEqual((self.manifest["item_count"], self.manifest["n"]), (967, 1934))
        self.assertEqual(self.manifest["dataset_counts"], menu.DATASET_COUNTS)
        self.assertEqual(self.manifest["arm_counts"], {"Q": 1934})
        base = {dp.item_key(item.dataset_id, item.item_id): item for item in menu.design_items()}
        for item in self.rebuilt.values():
            source = base[dp.item_key(item.dataset_id, item.item_id)]
            self.assertEqual(item.prompt, menu.q_prompt(source, PROTOCOL), item.run_key)
            self.assertTrue(item.prompt.startswith(HEAD) and item.prompt.endswith("\n"), item.run_key)


@unittest.skipUnless(menu.REGISTRATION_PATH.is_file(), "MC-97 is not registered yet")
class TestMenuRegistration(unittest.TestCase):
    def test_the_registration_matches_the_frozen_files(self):
        frozen = runner.load_registration()["frozen"]
        self.assertEqual(frozen["menu_protocol_sha256"], v1.sha256_file(menu.PROTOCOL_PATH))
        self.assertEqual(frozen["campaign_protocol_sha256"], v1.sha256_file(dp.PROTOCOL_PATH))
        self.assertEqual(frozen["source_manifest_sha256"], v1.sha256_file(menu.SOURCE_MANIFEST))
        self.assertEqual(frozen["manifest_sha256"], menu.load_frozen_manifest()["manifest_sha256"])

    def test_limits_other_than_the_registered_ones_are_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            runner.main(["--max-in-flight", "8"])
        self.assertIn("differs from the 4 registered for MC-97", err.getvalue())


if __name__ == "__main__":
    unittest.main()
