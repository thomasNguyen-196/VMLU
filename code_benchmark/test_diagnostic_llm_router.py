"""Offline tests for the Muse router's design-stage check (openspec change diagnostic-llm-router; card MC-98).

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_llm_router
Synthetic items and a fake client; nothing is sent. Expected values are worked out by hand in the comments.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import types
import unittest
from pathlib import Path

from openai import APIConnectionError

from code_benchmark import analyze_router_labels as arl
from code_benchmark import diagnostic_llm_router as router
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_router_labels as runner
from code_benchmark import vi_multimodel as v1

CONFIG, _ = router.load_config()
PASSAGE = "Luật Đấu thầu Điều 27. Hồ sơ dự thầu khoản 2 . Nhà thầu nộp hồ sơ trong thời hạn 7 ngày làm việc."
QUESTION = "Nhà thầu nộp hồ sơ trong thời hạn bao lâu?"


def item(gold: str = "zzgoldzz", item_id: str = "T1") -> v1.EvalItem:
    return v1.EvalItem(dataset_id=router.DATASET, source_dataset="bidlqa", item_id=item_id,
                       replicate_id=router.REPLICATE, task="reading", stratum="all", question=QUESTION, passage_id="p",
                       prompt=v1.build_reading_prompt(PASSAGE, QUESTION), gold_answer=gold)


def cell(**scores: float) -> dict[str, dict]:
    return {name: {"item_id": "T", "token_f1": f1} for name, f1 in scores.items()}


def small(min_items: int = 2) -> dict:
    config = copy.deepcopy(CONFIG)
    config["mapping"]["min_group_items"] = min_items
    return config


class TestConfiguration(unittest.TestCase):
    def test_out_of_contract_configurations_are_refused(self):
        bad = []
        for change in (lambda c: c["groups"].append(dict(c["groups"][0])),
                       lambda c: c["prompt"].update(template=c["prompt"]["template"].replace("<<PASSAGE>>", "")),
                       lambda c: c["route"].update(stream=True),
                       lambda c: c["mapping"].update(arms=["S", "Q", "B"]),
                       lambda c: c["mapping"].update(min_group_items=0),
                       lambda c: c["keyword_comparator"]["groups"][0].update(pattern="("),
                       lambda c: c.update(extra=1)):
            config = copy.deepcopy(CONFIG)
            change(config)
            bad.append(config)
        for config in bad:
            with self.assertRaises(SystemExit):
                router.validate_config(config)


class TestPromptAndParsing(unittest.TestCase):
    def test_the_prompt_lists_the_groups_then_the_passage_and_question(self):
        prompt = router.router_prompt(item(), CONFIG)
        lines = [f"- {g['id']}: {g['definition']}" for g in CONFIG["groups"]]
        self.assertIn("\n".join(lines), prompt)
        self.assertIn("Đoạn văn:\n" + PASSAGE + "\n\nCâu hỏi: " + QUESTION, prompt)
        self.assertIn(", ".join(router.group_ids(CONFIG)), prompt)
        self.assertNotIn("zzgoldzz", prompt)
        self.assertFalse(any(token in prompt for token in router.PLACEHOLDERS))
        mc = dataclasses.replace(item(), task="multiple_choice", prompt=dp.MC_HEAD + "Câu?\n\nA. a\nB. b" + dp.MC_TAIL)
        with self.assertRaises(SystemExit):
            router.router_prompt(mc, CONFIG)

    def test_parse_group(self):
        cases = {"Phân tích ngắn.\nNhóm: so_hieu": ("so_hieu", True), "Nhóm: `toan_bo`": ("toan_bo", True),
                 "Nhóm: **TRA_CUU**": ("tra_cuu", True), "Nhóm: khác": (None, True),
                 "Nhóm: mot_phan\nNhóm: dieu_kien": ("dieu_kien", True), "Nhóm: tinh_toan\nGiải thích.": ("tinh_toan", False),
                 "": (None, False), "so_hieu": (None, False)}
        for text, expected in cases.items():
            self.assertEqual(router.parse_group(text, CONFIG), expected, text)

    def test_keyword_groups_in_order(self):
        cases = {"Nội dung này thuộc khoản nào?": "so_dieu_khoan", "Thời hạn là bao nhiêu ngày?": "tinh_dem",
                 "Dự toán mua sắm là gì?": "dinh_nghia", "Những tài liệu nào cần nộp?": "danh_sach",
                 "Được áp dụng trong trường hợp nào?": "dieu_kien", "Cơ quan nào có thẩm quyền?": "chu_the",
                 "Nhà thầu phải làm gì trước?": "khac"}
        for question, expected in cases.items():
            self.assertEqual(router.keyword_group(question, CONFIG), expected, question)


class TestMapping(unittest.TestCase):
    # g1: draw-1 means B 0.8, Q 0.45, S 0.3 -> B; draw-2 means B 0.9, Q 0.45, S 0.4 -> B.
    #     item 1: (B2 0.8 + B1 1.0) / 2 = 0.9; item 2: (B2 1.0 + B1 0.6) / 2 = 0.8.
    # g2: one item, under the minimum of 2 -> S: (S2 0.5 + S1 0.3) / 2 = 0.4. None (unrecognised) -> S: 0.7.
    # g3: Q and S tie on both draws (0.6) -> the more thorough S: 0.6 and 0.6.
    CELLS = [cell(B1=1.0, B2=0.8, Q1=0.5, Q2=0.5, S1=0.0, S2=0.2), cell(B1=0.6, B2=1.0, Q1=0.4, Q2=0.4, S1=0.6, S2=0.6),
             cell(B1=0.9, B2=0.9, Q1=0.9, Q2=0.9, S1=0.3, S2=0.5), cell(B1=1.0, B2=1.0, Q1=0.0, Q2=0.0, S1=0.7, S2=0.7),
             cell(B1=0.0, B2=0.0, Q1=0.6, Q2=0.6, S1=0.6, S2=0.6), cell(B1=0.0, B2=0.0, Q1=0.6, Q2=0.6, S1=0.6, S2=0.6)]
    GROUPS = ["g1", "g1", "g2", None, "g3", "g3"]

    def test_cross_draw_routing(self):
        scores, first, second = router.cross_draw_scores(self.CELLS, self.GROUPS, small())
        self.assertEqual(first, {"g1": "B", "g2": "S", None: "S", "g3": "S"})
        self.assertEqual(second, first)
        for got, expected in zip(scores, [0.9, 0.8, 0.4, 0.7, 0.6, 0.6], strict=True):
            self.assertAlmostEqual(got, expected)

    def test_report_and_reading_rule(self):
        # Muse routing mean = (0.9+0.8+0.4+0.7+0.6+0.6)/6 = 0.6667; always-S = (0.1+0.6+0.4+0.7+0.6+0.6)/6 = 0.5;
        # keywords put everything in one group: draw-1 means B 0.583, Q 0.5, S 0.467 -> B; draw 2 the same -> B
        # = (0.9+0.8+0.9+1.0+0+0)/6 = 0.6. Muse - S = 16.67 points >= 1, Muse > keywords: promising.
        # Per item, Muse - S = 0.8, 0.2, 0, 0, 0, 0: better on 2 items, equal on 4.
        report = arl.evaluate(self.CELLS, self.GROUPS, ["x"] * 6, small())
        self.assertEqual(report["routing"]["muse_grouping"], 66.67)
        self.assertEqual(report["routing"]["always_S"], 50.0)
        self.assertEqual(report["routing"]["keyword_grouping"], 60.0)
        self.assertTrue(report["reading_rule"]["promising"])
        self.assertEqual(report["unrecognised"], 1)
        self.assertEqual((report["muse_minus_always_S"]["better"], report["muse_minus_always_S"]["equal"]), (2, 4))


class FakeResponses:
    def __init__(self, text: str = "Nhóm: so_hieu", model: str = "muse-spark-1.3-contributor", fail: bool = False):
        self.text, self.model, self.fail, self.calls = text, model, fail, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise APIConnectionError(message="down", request=None)  # type: ignore[arg-type]
        usage = types.SimpleNamespace(input_tokens=900, output_tokens=300, total_tokens=1200,
                                      output_tokens_details=types.SimpleNamespace(reasoning_tokens=290))
        return types.SimpleNamespace(output_text=self.text, usage=usage, model=self.model, id="r1", status="completed",
                                     incomplete_details=None)


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "card.md").write_text("card", encoding="utf-8")
        self.manifest = {name: name[0] * 64 for name in runner.FROZEN_KEYS}
        self.registration = {"card_ids": {"labels": "MC-998"}, "card_files": {"labels": "card.md"},
                             "frozen": dict(self.manifest)}
        self.route = ("https://opencode.ai/zen/go/v1", CONFIG["route"]["model_id"], True)

    def gates(self, **overrides):
        args = {"manifest": self.manifest, "registration": self.registration, "route": self.route, **overrides}
        return {g.name: g for g in runner.evaluate_gates(CONFIG, args["manifest"], args["registration"], args["route"],
                                                          card_text="## MC-998 — test\n", root=self.root)}

    def test_every_gate_passes_when_registered_and_fails_on_drift(self):
        self.assertTrue(all(g.ok for g in self.gates().values()), {n: g.detail for n, g in self.gates().items()})
        self.assertFalse(self.gates(manifest={**self.manifest, "manifest_sha256": "x" * 64})["frozen_hashes"].ok)
        self.assertFalse(self.gates(route=("https://other.example/v1", self.route[1], True))["route_identity"].ok)
        self.assertFalse(self.gates(route=(self.route[0], "other-model", True))["route_identity"].ok)
        self.assertFalse(self.gates(route=(self.route[0], self.route[1], False))["route_identity"].ok)

    def test_one_call_records_the_group_usage_and_session(self):
        fake = FakeResponses()
        row = runner.call_router(types.SimpleNamespace(responses=fake), item(), CONFIG, CONFIG["route"]["model_id"])
        self.assertEqual((row["status"], row["group"], row["format_ok"], row["reasoning_tokens"]),
                         ("complete", "so_hieu", True, 290))
        self.assertEqual(fake.calls[0]["extra_headers"], {"x-opencode-session": runner.session_id(item().run_key)})
        self.assertEqual(fake.calls[0]["max_output_tokens"], CONFIG["route"]["max_output_tokens"])
        failed = runner.call_router(types.SimpleNamespace(responses=FakeResponses(fail=True)), item(), CONFIG, "m")
        self.assertEqual(failed["status"], "network_error")

    def test_execute_writes_labels_and_halts_on_a_changed_model_id(self):
        items = [item(item_id=f"T{n}") for n in range(3)]
        summary = runner.execute(self.root, items, CONFIG, types.SimpleNamespace(responses=FakeResponses()),
                                 CONFIG["route"]["model_id"])
        self.assertEqual((summary["status"], summary["complete"], summary["reported_tokens"]), ("complete", 3, 3600))
        labels = [json.loads(line) for line in (self.root / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["group"] for row in labels], ["so_hieu"] * 3)
        other = self.root / "other"
        other.mkdir()
        summary = runner.execute(other, items, CONFIG, types.SimpleNamespace(responses=FakeResponses(model="x")),
                                 CONFIG["route"]["model_id"])
        self.assertEqual(summary["halt_reason"], "model_id_changed")


class TestFrozenManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not router.MANIFEST_PATH.is_file():
            raise unittest.SkipTest("the router-labels manifest is not frozen yet")
        try:
            cls.manifest, cls.rebuilt = router.build_manifest()
        except (SystemExit, OSError) as exc:
            raise unittest.SkipTest(f"local benchmark sources unavailable: {exc}") from exc

    def test_it_rebuilds_byte_for_byte(self):
        self.assertEqual(self.manifest, router.load_frozen_manifest())
        self.assertEqual((self.manifest["n"], len(self.rebuilt)), (591, 591))
        self.assertTrue(all(i.prompt.startswith("Bạn là bộ phân loại câu hỏi đọc hiểu.") for i in self.rebuilt.values()))

    @unittest.skipUnless(router.REGISTRATION_PATH.is_file(), "MC-98 is not registered yet")
    def test_the_registration_matches_the_frozen_files(self):
        frozen = runner.load_registration()["frozen"]
        self.assertEqual(frozen["router_config_sha256"], v1.sha256_file(router.CONFIG_PATH))
        self.assertEqual(frozen["manifest_sha256"], self.manifest["manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
