"""Offline tests of the Legal MC "chọn rồi trả lời" test (openspec change diagnostic-legal-select). No endpoint is
called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_legal_select
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_legal_retrieval_misses as misses
from code_benchmark import analyze_legal_select as als
from code_benchmark import diagnostic_legal_oracle as lo
from code_benchmark import diagnostic_legal_retrieval as lr
from code_benchmark import diagnostic_legal_select as ls
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_legal_select as rls
from code_benchmark import vi_multimodel as v1

HAS_DATA = all((lo.ROOT / path).is_file() for path in lo.load_protocol()["selection"]["sources"].values())
BUILT = (HAS_DATA and lr.EVIDENCE_PATH.is_file() and (lr.CORPUS_DIR / "corpus.jsonl").is_file()
         and ls.CANDIDATES_PATH.is_file() and ls.MANIFEST_PATH.is_file())


def mc_item(item_id: str, question: str = "Câu hỏi về thuế?", gold: str = "A") -> v1.EvalItem:
    body = question + "\n\n" + "\n".join(f"{letter}. Lựa chọn {letter}" for letter in "ABCD")
    return v1.EvalItem(dataset_id=ls.DATASET, source_dataset="legal-slm", item_id=item_id, replicate_id="main-000",
                       task="multiple_choice", stratum="legal", question=question, passage_id="legal",
                       prompt=dp.MC_HEAD + body + dp.MC_TAIL, gold_answer=gold)


def unit(doc: str, article: int) -> dict:
    text = f"Điều {article}. Quy định số {article} của văn bản {doc}."
    return {"doc_id": doc, "doc_title": f"Văn bản {doc}", "locator": f"Điều {article}", "text": text,
            "text_sha256": v1.sha256_bytes(text.encode("utf-8")), "source_ref": f"https://example.vn/{doc}"}


def candidates_for(item_id: str) -> dict:
    provisions = [unit("10/2020/QH14", n) for n in range(1, 11)]
    return {"dataset_id": ls.DATASET, "item_id": item_id, "provisions": provisions,
            "ranking": [{"chunk_id": f"10/2020/QH14#dieu-{n}", "score": 10.0 - n,
                         "text_sha256": provisions[n - 1]["text_sha256"]} for n in range(1, 11)],
            "query_sha256": "q", "corpus_sha256": "c", "retrieval_config_sha256": "r"}


def synthetic_inputs(item_ids: list[str]) -> ls.Inputs:
    frozen = {item_id: mc_item(item_id) for item_id in item_ids}
    candidates = {item_id: candidates_for(item_id) for item_id in item_ids}
    k_evidence = {item_id: {"provisions": candidates[item_id]["provisions"][:2], "query_sha256": "q"}
                  for item_id in item_ids}
    return ls.Inputs(protocol={"draws": 2}, pool=item_ids, mc100={}, index=None,  # type: ignore[arg-type]
                     k_evidence=k_evidence, candidates=candidates, templates=dp.load_templates(),
                     template=ls.load_template(), frozen=frozen)


def round1_for(inputs: ls.Inputs) -> dict:
    refs = []
    for item_id in inputs.pool:
        base = inputs.frozen[item_id]
        prompt = ls.render_pick_prompt(base, inputs.candidates[item_id]["provisions"], inputs.template,
                                       inputs.templates)
        for draw in (1, 2):
            refs.append({"dataset_id": ls.DATASET, "item_id": item_id, "replicate_id": f"PICK-r{draw}",
                         "prompt_sha256": v1.sha256_bytes(prompt.encode())})
    return {"manifest_sha256": "round1", **{key: "h" for key in ls.HASH_KEYS}, "items": refs}


def rows_for(round1: dict, responses: dict[str, str]) -> dict:
    return {dp.run_key(ref): {"status": "complete", "prompt_sha256": ref["prompt_sha256"],
                              "raw_response": responses.get(dp.run_key(ref), "Đoạn liên quan: 1")}
            for ref in round1["items"]}


class TestParser(unittest.TestCase):
    def test_numbers_none_and_order(self):
        self.assertEqual(ls.parse_pick("Lý do...\nĐoạn liên quan: 3"), {"status": "picked", "picks": [3]})
        self.assertEqual(ls.parse_pick("Đoạn liên quan: 3, 7")["picks"], [3, 7])
        self.assertEqual(ls.parse_pick("Đoạn liên quan: Không có"), {"status": "none", "picks": []})
        self.assertEqual(ls.parse_pick("Đoạn liên quan: 4, 1, 4, 9")["picks"], [4, 1])

    def test_range_markup_case_and_last_line(self):
        self.assertEqual(ls.parse_pick("Đoạn liên quan: 0, 11"), {"status": "unparsed", "picks": []})
        self.assertEqual(ls.parse_pick("Đoạn liên quan: 11, 3")["picks"], [3])
        self.assertEqual(ls.parse_pick("**Đoạn liên quan:** `[3]` và `[7]`")["picks"], [3, 7])
        self.assertEqual(ls.parse_pick("đoạn liên quan: 2")["picks"], [2])
        self.assertEqual(ls.parse_pick("Đoạn liên quan: 5\nSửa lại.\nĐoạn liên quan: 6")["picks"], [6])

    def test_unparsed_and_number_beats_none(self):
        self.assertEqual(ls.parse_pick("Tôi chọn đoạn 3.")["status"], "unparsed")
        self.assertEqual(ls.parse_pick("")["status"], "unparsed")
        self.assertEqual(ls.parse_pick("Đoạn liên quan: chưa rõ")["status"], "unparsed")
        self.assertEqual(ls.parse_pick("Đoạn liên quan: 2 (không có đoạn khác)"), {"status": "picked", "picks": [2]})

    def test_selection_provisions(self):
        record = candidates_for("LG-1")
        k_record = {"provisions": record["provisions"][:2]}
        picked = ls.selection_provisions({"status": "picked", "picks": [7, 3]}, record, k_record)
        self.assertEqual([p["locator"] for p in picked], ["Điều 7", "Điều 3"])
        self.assertIsNone(ls.selection_provisions({"status": "none", "picks": []}, record, k_record))
        self.assertEqual(ls.selection_provisions({"status": "unparsed", "picks": []}, record, k_record),
                         record["provisions"][:2])


class TestPrompts(unittest.TestCase):
    def test_pick_prompt_shows_numbered_candidates_then_the_question(self):
        inputs = synthetic_inputs(["LG-1"])
        item = inputs.frozen["LG-1"]
        prompt = ls.render_pick_prompt(item, inputs.candidates["LG-1"]["provisions"][:3], inputs.template,
                                       inputs.templates)
        self.assertTrue(prompt.startswith(inputs.template["head"].format(n=3)))
        positions = [prompt.index(f"[{n}] Văn bản 10/2020/QH14 — Điều {n}\n") for n in (1, 2, 3)]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(prompt.endswith(inputs.template["question_header"] + lr.dr.mc_query(item) + "\n"))
        self.assertNotIn("Đáp án:", prompt)
        self.assertNotIn("[4]", prompt)

    def test_template_requires_its_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps({"version": "x", "head": "no count"}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                ls.load_template(path)


class TestRound2(unittest.TestCase):
    def setUp(self):
        self.inputs = synthetic_inputs(["LG-1", "LG-2"])
        self.round1 = round1_for(self.inputs)

    def test_deterministic_and_draw_r_uses_pick_r(self):
        responses = {f"{ls.DATASET}:LG-1:PICK-r1": "Đoạn liên quan: 5",
                     f"{ls.DATASET}:LG-1:PICK-r2": "Đoạn liên quan: Không có",
                     f"{ls.DATASET}:LG-2:PICK-r1": "không trả lời đúng mẫu",
                     f"{ls.DATASET}:LG-2:PICK-r2": "Đoạn liên quan: 2, 9"}
        rows = rows_for(self.round1, responses)
        first, rebuilt = ls.build_round2(self.round1, rows, self.inputs)
        again, _ = ls.build_round2(self.round1, rows, self.inputs)
        self.assertEqual(first, again)
        self.assertEqual(first["n"], 4)
        self.assertEqual(first["selection_counts"], {"none": 1, "picked": 2, "unparsed": 1})
        prompt = {key.rsplit(":", 2)[-2] + ":" + key.rsplit(":", 1)[-1]: item.prompt for key, item in rebuilt.items()}
        base1, base2 = self.inputs.frozen["LG-1"], self.inputs.frozen["LG-2"]
        templates, cands = self.inputs.templates, self.inputs.candidates
        self.assertEqual(prompt["LG-1:SEL-r1"], dp.build_arm_prompt(base1, "K", templates, [cands["LG-1"]["provisions"][4]]))
        self.assertEqual(prompt["LG-1:SEL-r2"], base1.prompt)
        self.assertEqual(prompt["LG-2:SEL-r1"], dp.build_arm_prompt(base2, "K", templates, cands["LG-2"]["provisions"][:2]))
        self.assertEqual(prompt["LG-2:SEL-r2"], dp.build_arm_prompt(
            base2, "K", templates, [cands["LG-2"]["provisions"][1], cands["LG-2"]["provisions"][8]]))
        self.assertEqual(first["round1_manifest_sha256"], "round1")

    def test_an_incomplete_pick_stops_round_2(self):
        rows = rows_for(self.round1, {})
        key = next(iter(rows))
        rows[key] = {**rows[key], "status": "request_error"}
        with self.assertRaises(SystemExit):
            ls.build_round2(self.round1, rows, self.inputs)

    def test_runner_writes_round_2_once_and_refuses_a_different_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows = rows_for(self.round1, {})
            first, _ = rls.round2_manifest(out, self.round1, rows, self.inputs)
            self.assertEqual(json.loads((out / rls.ROUND2_MANIFEST).read_text(encoding="utf-8")), first)
            rls.round2_manifest(out, self.round1, rows, self.inputs)  # same ledger: accepted
            changed = {**rows}
            key = next(iter(changed))
            changed[key] = {**changed[key], "raw_response": "Đoạn liên quan: 9"}
            with self.assertRaises(SystemExit):
                rls.round2_manifest(out, self.round1, changed, self.inputs)

    def test_round_1_ledger_rows_must_be_in_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(rls.round1_complete(out, self.round1), (False, {}))
            rows = rows_for(self.round1, {})
            lines = [json.dumps({"run_key": key, **row}, ensure_ascii=False) for key, row in rows.items()]
            (out / "attempts.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            done, loaded = rls.round1_complete(out, self.round1)
            self.assertTrue(done)
            self.assertEqual(len(loaded), 4)
            (out / "attempts.jsonl").write_text(json.dumps({"run_key": "x:y:PICK-r1", "prompt_sha256": "z"}) + "\n",
                                                encoding="utf-8")
            with self.assertRaises(SystemExit):
                rls.round1_complete(out, self.round1)


class TestAnalysis(unittest.TestCase):
    def test_empty_and_unparsed_selections_are_misses(self):
        record = candidates_for("LG-1")
        targets = {("10/2020/qh14", "", "4")}
        self.assertTrue(als.selection_hit({"status": "picked", "picks": [2, 4]}, record, targets))
        self.assertFalse(als.selection_hit({"status": "picked", "picks": [2]}, record, targets))
        self.assertFalse(als.selection_hit({"status": "none", "picks": []}, record, targets))
        self.assertFalse(als.selection_hit({"status": "unparsed", "picks": []}, record, targets))

    def test_filter_question_against_bm25_top_2(self):
        oracle = {f"LG-{n}": {"provisions": [unit("10/2020/QH14", 4)]} for n in range(1, 4)}
        candidates = {item: candidates_for(item) for item in oracle}
        selections = {"LG-1": {"1": {"status": "picked", "picks": [4]}, "2": {"status": "picked", "picks": [4]}},
                      "LG-2": {"1": {"status": "picked", "picks": [4]}, "2": {"status": "none", "picks": []}},
                      "LG-3": {"1": {"status": "unparsed", "picks": []}, "2": {"status": "picked", "picks": [1]}}}
        block = als.filter_question(sorted(oracle), selections, candidates, oracle)
        self.assertEqual((block["PICK"], block["BM25_top2"]), (50.0, 0.0))
        self.assertEqual(block["PICK_versus_BM25_top2"]["better"], 2)

    def test_rules_both_ways_with_holm(self):
        strong = {"mean_points": 10.0, "sign_flip_p": 0.01}
        weak = {"mean_points": 2.0, "sign_flip_p": 0.04}
        out = als.rules({"PICK_versus_BM25_top2": strong}, {"SEL_versus_B": weak}, 0.05)
        self.assertTrue(out["filter"]["met"])
        self.assertTrue(out["route"]["met"])  # Holm: 0.02 and max(0.02, 0.04) = 0.04 < 0.05
        self.assertEqual(out["route"]["legal_mc_route"], "SEL")
        out = als.rules({"PICK_versus_BM25_top2": {"mean_points": -1.0, "sign_flip_p": 0.04}},
                        {"SEL_versus_B": {"mean_points": 3.0, "sign_flip_p": 0.03}}, 0.05)
        self.assertFalse(out["filter"]["met"])  # negative difference
        self.assertFalse(out["route"]["met"])  # Holm doubles the smaller p: 0.06
        self.assertAlmostEqual(out["route"]["p_holm"], 0.06)
        self.assertEqual(out["route"]["legal_mc_route"], "B")

    def test_group_block_and_share_of_gain(self):
        def cell(**arms):
            return {f"{arm}{draw}": {"correct": value} for arm, value in arms.items() for draw in ("1", "2")}
        cells = {"LG-1": cell(B=0, K=1, K10=0, SEL=1, O=1), "LG-2": cell(B=0, K=0, K10=0, SEL=1, O=1)}
        block = als.group_block(["LG-1", "LG-2"], cells, gain_share=True)
        self.assertEqual((block["B"], block["K"], block["SEL"], block["O"]), (0.0, 50.0, 100.0, 100.0))
        self.assertEqual(block["share_of_O_gain_kept"], {"K": 0.5, "K10": 0.0, "SEL": 1.0})


class TestPreCheck(unittest.TestCase):
    def test_classes_and_document_oracle(self):
        corpus_docs = {"a", "b"}
        corpus_units = {("a", "", "1"), ("a", "", "2"), ("b", "", "5")}
        targets = {("a", "", "2")}
        self.assertEqual(misses.classify(targets, [("a", "", "2"), ("b", "", "5")], corpus_docs, corpus_units)["kind"], "hit")
        same = misses.classify(targets, [("a", "", "1"), ("b", "", "5"), ("a", "", "2")], corpus_docs, corpus_units)
        self.assertEqual((same["kind"], same["unit_rank"], same["doc_oracle_hit_at_2"]), ("same_doc", 3, True))
        other = misses.classify(targets, [("b", "", "5"), ("b", "", "6"), ("a", "", "2")], corpus_docs, corpus_units)
        self.assertEqual((other["kind"], other["doc_rank"], other["doc_oracle_hit_at_2"]), ("other_doc", 3, True))
        self.assertEqual(misses.classify({("z", "", "1")}, [("a", "", "1")], corpus_docs, corpus_units)["kind"],
                         "doc_missing")
        self.assertEqual(misses.classify({("b", "", "9")}, [("a", "", "1")], corpus_docs, corpus_units)["kind"],
                         "unit_missing")


@unittest.skipUnless(BUILT, "needs MC-101's built corpus and K evidence, and the frozen candidates and manifest")
class TestRealFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = ls.load_inputs()
        cls.manifest, cls.rebuilt = ls.build_round1(cls.inputs)

    def test_round_1_matches_the_frozen_manifest_and_counts(self):
        self.assertEqual(self.manifest, ls.load_frozen_round1())
        self.assertEqual(self.manifest["arm_counts"], {"B": 268, "K": 268, "K10": 268, "O": 106, "PICK": 268})

    def test_b_k_and_o_prompts_equal_mc101_and_no_prompt_carries_the_gold(self):
        mc101 = {(r["item_id"], r["replicate_id"]): r["prompt_sha256"] for r in lr.load_frozen_manifest()["items"]}
        for ref in self.manifest["items"]:
            if dp.arm_of_replicate(ref["replicate_id"]) in {"B", "K", "O"}:
                self.assertEqual(ref["prompt_sha256"], mc101[(ref["item_id"], ref["replicate_id"])])
        for item in self.rebuilt.values():
            self.assertIsNone(dp.ANSWER_KEY.search(item.prompt.replace(dp.MC_TAIL, "")), item.run_key)

    def test_candidates_cover_47_oracle_items_and_start_with_mc101_k(self):
        oracle = self.inputs.mc100["oracle"]
        self.assertEqual(ls.oracle_coverage(self.inputs.candidates, oracle, 10), 47)
        self.assertEqual(ls.oracle_coverage(self.inputs.candidates, oracle, 2), 40)

    def test_pre_check_reproduces_its_numbers(self):
        summary = misses.build_report()["summary"]
        self.assertEqual(summary["classes"], {"hit": 40, "doc_missing": 1, "unit_missing": 0, "same_doc": 3,
                                              "other_doc": 9})
        self.assertEqual(summary["document_oracle_hit_at_2"], 45)

    def test_offline_end_to_end_with_synthetic_answers(self):
        """Score round 1, build round 2 from it, score SEL and run the registered analysis, all without a request."""
        rls.pr.base.MODEL = "synthetic"
        responses = ["Đoạn liên quan: 1, 2", "Đoạn liên quan: 3", "Đoạn liên quan: Không có", "?"]

        def row(ref: dict, text: str) -> dict:
            return {"run_key": dp.run_key(ref), "dataset_id": ref["dataset_id"], "item_id": ref["item_id"],
                    "replicate_id": ref["replicate_id"], "arm": dp.arm_of_replicate(ref["replicate_id"]),
                    "status": "complete", "finish_reason": "stop", "raw_response": text,
                    "prompt_sha256": ref["prompt_sha256"], "prompt_tokens": 100, "completion_tokens": 2,
                    "total_tokens": 102}
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "round1").mkdir()
            rows = {}
            for number, ref in enumerate(self.manifest["items"]):
                arm = dp.arm_of_replicate(ref["replicate_id"])
                rows[dp.run_key(ref)] = row(ref, responses[number % 4] if arm == "PICK" else "ABCD"[number % 4])
            rls.score_callback("MC-111", 1)(run / "round1", self.manifest, self.rebuilt, rows, {"condition_sha256": "x"})
            second, rebuilt2 = rls.round2_manifest(run / "round2", self.manifest, rows, self.inputs)
            rows2 = {dp.run_key(ref): row(ref, "ABCD"[number % 4]) for number, ref in enumerate(second["items"])}
            rls.score_callback("MC-111", 2)(run / "round2", second, rebuilt2, rows2, {"condition_sha256": "y"})
            report = als.build_report(run)
        self.assertEqual(report["route"]["n"], 134)
        self.assertEqual(report["filter"]["n"], 53)
        self.assertEqual(report["filter"]["BM25_top2"], round(100 * 40 / 53, 2))
        self.assertEqual(report["selection"]["draws"], 268)
        self.assertEqual(set(report["rules"]), {"alpha", "multiplicity", "filter", "route"})
        self.assertEqual(set(report["mc100_strata"]["wrong"]["share_of_O_gain_kept"]), {"K", "K10", "SEL"})

    def test_gates(self):
        campaign = dp.load_protocol()
        registration = {"card_ids": {ls.PHASE: "MC-111"}, "card_files": {ls.PHASE: "docs/none.md"},
                        "frozen": {key: self.manifest[key] for key in rls.FROZEN_KEYS}}
        env = {"OPENAI_BASE_URL": f"http://{campaign['model']['endpoint_host']}{campaign['model']['endpoint_path']}",
               "OPENAI_MODEL": campaign["model"]["requested_id"], "OPENAI_API_KEY": "k"}
        gates = {g.name: g.ok for g in rls.evaluate_gates(campaign, self.manifest, registration, env,
                                                          card_text="## MC-111 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": True,
                                 "endpoint_identity": True})
        registration["frozen"]["candidates_sha256"] = "0" * 64
        gates = {g.name: g.ok for g in rls.evaluate_gates(campaign, self.manifest, registration, env, card_text="")}
        self.assertFalse(gates["frozen_hashes"])
        self.assertFalse(gates["card_registered"])


if __name__ == "__main__":
    unittest.main()
