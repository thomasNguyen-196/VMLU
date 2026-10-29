"""Offline tests of the Legal MC oracle test (openspec change diagnostic-legal-oracle). No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_legal_oracle
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_legal_oracle as alo
from code_benchmark import diagnostic_legal_oracle as lo
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_retrieval as dr
from code_benchmark import run_legal_oracle as rlo
from code_benchmark import vi_multimodel as v1

PAGE = ("<html><body><dieu><p>Điều 5. Nghĩa vụ của người nộp thuế</p><p>1. Khoản một.</p><p>a) Điểm a.</p>"
        "<p>2. Khoản hai.</p><p>3. Khoản ba.</p></dieu>"
        "<dieu><p>Điều 6. Điều khác</p><p>Nội dung.</p></dieu></body></html>")
URL = "https://hethongphapluat.com/luat-mau.html"
HAS_DATA = all((lo.ROOT / path).is_file() for path in lo.load_protocol()["selection"]["sources"].values())


def store(sources: Path, url: str = URL, page: str = PAGE) -> None:
    (sources / "raw").mkdir(parents=True, exist_ok=True)
    raw = page.encode("utf-8")
    (sources / "raw" / "page.html").write_bytes(raw)
    entry = {"url": url, "file": "page.html", "sha256": v1.sha256_bytes(raw)}
    (sources / "fetch_log.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")


def located(item_id: str, support: str = "supports_gold", clauses: list[str] | None = None) -> dict:
    provisions = [] if support == "not_found" else [
        {"url": URL, "doc_id": "38/2019/QH14", "doc_title": "Luật mẫu", "article": "5", "clauses": clauses or []}]
    return {"item_id": item_id, "provisions": provisions, "support": support, "located_by": "agent-batch-1"}


class TestProvisions(unittest.TestCase):
    def test_whole_article_is_verbatim(self):
        locator, text = lo.provision_text(PAGE, "5", [])
        self.assertEqual(locator, "Điều 5")
        self.assertTrue(text.startswith("Điều 5. Nghĩa vụ"))
        self.assertIn("3. Khoản ba.", text)

    def test_named_clauses_keep_the_heading_and_page_order(self):
        locator, text = lo.provision_text(PAGE, "Điều 5", ["3", "1"], max_chars=40)
        self.assertEqual(locator, "Điều 5, khoản 1, 3")
        self.assertEqual(text.splitlines(), ["Điều 5. Nghĩa vụ của người nộp thuế", "1. Khoản một.", "a) Điểm a.",
                                             "3. Khoản ba."])

    def test_an_article_within_the_limit_is_whole_even_with_clauses_named(self):
        self.assertEqual(lo.provision_text(PAGE, "5", ["3"]), lo.provision_text(PAGE, "5", []))

    def test_missing_article_or_clause_and_a_long_article_without_clauses_fail(self):
        with self.assertRaises(SystemExit):
            lo.provision_text(PAGE, "9", [])
        for limit in (40, 6000):  # a missing clause fails whether or not the article is cut
            with self.assertRaises(SystemExit):
                lo.provision_text(PAGE, "5", ["7"], max_chars=limit)
        with self.assertRaises(SystemExit):
            lo.provision_text(PAGE, "6", ["1"])  # an article without clauses
        with self.assertRaises(SystemExit):
            lo.provision_text(PAGE, "5", [], max_chars=40)

    def test_a_page_breaking_off_inside_its_last_article_keeps_the_closed_ones(self):
        self.assertEqual(lo.page_articles(PAGE), dict(dr.parse_articles(PAGE)))
        broken = PAGE.replace("<p>Nội dung.</p></dieu>", "<p>Nội dung.</p><p>Điều 7. Sau</p>")
        with self.assertRaises(SystemExit):
            dr.parse_articles(broken)
        self.assertEqual(lo.page_articles(broken), {"5": dict(dr.parse_articles(PAGE))["5"]})
        with self.assertRaises(SystemExit):
            lo.provision_text(broken, "6", [])

    def test_an_attached_regulation_is_read_after_its_heading_line(self):
        page = ("<html><body><dieu><p>Điều 1. Ban hành kèm theo Quyết định này Quy chế.</p></dieu>"
                "<dieu><p>Điều 2. Quyết định này có hiệu lực.</p></dieu>"
                "<p>QUY CHẾ</p><p>Chương I</p><p>Điều 1. Vị trí</p><p>Nội dung.</p>"
                "<p>Điều 2. Cơ cấu</p><p>1. Khoản một.</p><p>2. Khoản hai.</p><p>Chương II</p>"
                "<p>Điều 3. Khác</p></body></html>")
        self.assertEqual(lo.provision_text(page, "2", ["1"], part="QUY CHẾ"),
                         ("Quy chế kèm theo, Điều 2", "Điều 2. Cơ cấu\n1. Khoản một.\n2. Khoản hai."))
        self.assertEqual(lo.provision_text(page, "2", ["2"], max_chars=10, part="QUY CHẾ"),
                         ("Quy chế kèm theo, Điều 2, khoản 2", "Điều 2. Cơ cấu\n2. Khoản hai."))
        self.assertEqual(lo.provision_text(page, "2", []), ("Điều 2", "Điều 2. Quyết định này có hiệu lực."))
        with self.assertRaises(SystemExit):
            lo.provision_text(page, "2", ["1"])  # the Decision's own Điều 2 has no clause 1
        with self.assertRaises(SystemExit):
            lo.provision_text(page, "2", [], part="QUY ĐỊNH")

    def test_page_must_match_its_fetch_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp)
            store(sources)
            self.assertIn("Điều 5", lo.stored_page(URL, sources))
            (sources / "raw" / "page.html").write_text(PAGE + "<!-- edited -->", encoding="utf-8")
            with self.assertRaises(SystemExit):
                lo.stored_page(URL, sources)


class TestEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sources = Path(self.tmp.name)
        store(self.sources)
        self.strata = {"wrong": ["LG-0002"], "right": ["LG-0001", "LG-0003"]}

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        return [located("LG-0001"), located("LG-0002", "unclear", ["2"]), located("LG-0003", "not_found")]

    def test_records_cover_the_selection_in_item_order(self):
        records = lo.build_evidence(self.rows(), self.strata, sources_dir=self.sources)
        self.assertEqual([record["item_id"] for record in records], ["LG-0001", "LG-0002", "LG-0003"])
        self.assertEqual(records[1]["provisions"][0]["locator"], "Điều 5")  # short article: clause 2 widens
        self.assertEqual(records[2]["provisions"], [])
        self.assertFalse(dp.FORBIDDEN_EVIDENCE_KEYS & set(records[0]))

    def test_gaps_duplicates_and_inconsistent_labels_fail(self):
        with self.assertRaises(SystemExit):
            lo.build_evidence(self.rows()[:2], self.strata, sources_dir=self.sources)
        with self.assertRaises(SystemExit):
            lo.build_evidence(self.rows() + [located("LG-0001")], self.strata, sources_dir=self.sources)
        bad = self.rows()
        bad[2] = {**located("LG-0003"), "support": "not_found"}
        with self.assertRaises(SystemExit):
            lo.build_evidence(bad, self.strata, sources_dir=self.sources)

    def test_owner_review_replaces_the_agent_label_on_the_sample_only(self):
        records = lo.build_evidence(self.rows(), self.strata, sources_dir=self.sources)
        sample = lo.review_sample(records, 1)
        self.assertEqual(len(sample), 1)
        self.assertNotIn("LG-0003", sample)  # no provision, never reviewed
        final = lo.apply_review(records, {"reviewer": "owner", "labels": {sample[0]: "contradicts_gold"}}, sample)
        changed = [record for record in final if record["item_id"] == sample[0]][0]
        self.assertEqual((changed["support"], changed["label_source"]), ("contradicts_gold", "owner:owner"))
        with self.assertRaises(SystemExit):
            lo.apply_review(records, {"reviewer": "owner", "labels": {}}, sample)

    def test_load_evidence_refuses_answer_keys(self):
        records = lo.build_evidence(self.rows(), self.strata, sources_dir=self.sources)
        path = self.sources / "evidence.jsonl"
        v1.write_jsonl_atomic(path, [{**records[0], "gold": "A"}, *records[1:]])
        with self.assertRaises(SystemExit):
            lo.load_evidence(path, self.strata)
        v1.write_jsonl_atomic(path, records)
        self.assertEqual(set(lo.load_evidence(path, self.strata)), {"LG-0001", "LG-0002", "LG-0003"})


@unittest.skipUnless(HAS_DATA, "needs the MC-90 and MC-91 score files")
class TestSelectionAndManifest(unittest.TestCase):
    def test_selection(self):
        protocol = lo.load_protocol()
        strata = lo.select_items(protocol)
        outcomes = lo.b_outcomes(protocol)
        self.assertEqual((len(strata["wrong"]), len(strata["right"])), (28, 28))
        self.assertTrue(all(not all(outcomes[item]) for item in strata["wrong"]))
        self.assertTrue(all(all(outcomes[item]) for item in strata["right"]))
        self.assertEqual(lo.select_items(protocol), strata)

    def test_b_prompts_are_frozen_and_o_adds_only_the_evidence_block(self):
        strata = lo.select_items(lo.load_protocol())
        with tempfile.TemporaryDirectory() as tmp:
            text = "Điều 5. Nghĩa vụ\n1. Khoản một."
            provision = {"doc_id": "38/2019/QH14", "doc_title": "Luật mẫu", "locator": "Điều 5", "text": text,
                         "text_sha256": v1.sha256_bytes(text.encode("utf-8")), "source_ref": URL}
            items = sorted(item for group in strata.values() for item in group)
            records = [{"dataset_id": lo.DATASET, "item_id": item, "provisions": [] if index == 0 else [provision],
                        "support": "not_found" if index == 0 else "supports_gold", "label_source": "agent",
                        "located_by": "test"} for index, item in enumerate(items)]
            path = Path(tmp) / "evidence.jsonl"
            v1.write_jsonl_atomic(path, records)
            manifest, rebuilt = lo.build_manifest(evidence_path=path)
        frozen = lo.legal_items()
        self.assertEqual(manifest["arm_counts"], {"B": 112, "O": 110})  # the not_found item runs B only
        block = dp.render_evidence_block([provision], dp.load_templates())
        for item in rebuilt.values():
            base = frozen[item.item_id]
            arm = dp.arm_of_replicate(item.replicate_id)
            self.assertEqual(item.prompt, base.prompt if arm == "B" else block + base.prompt)
            self.assertNotIn(f"Đáp án: {base.gold_answer}", item.prompt)
        self.assertEqual(manifest["manifest_sha256"],
                         v1.sha256_bytes(v1.canonical_json({k: v for k, v in manifest.items() if k != "manifest_sha256"})))


class TestAnalysis(unittest.TestCase):
    @staticmethod
    def cell(b: tuple[int, int], o: tuple[int, int] | None) -> dict:
        cell = {f"B{d}": {"correct": b[i], "prediction": "A"} for i, d in enumerate(alo.DRAWS)}
        if o is not None:
            cell.update({f"O{d}": {"correct": o[i], "prediction": "B"} for i, d in enumerate(alo.DRAWS)})
        return cell

    def test_strata_and_reading_rule(self):
        cells = {"w1": self.cell((0, 0), (1, 1)), "w2": self.cell((0, 1), (1, 1)), "w3": self.cell((0, 0), None),
                 "r1": self.cell((1, 1), (1, 1)), "r2": self.cell((1, 1), (0, 0))}
        wrong = alo.stratum_block(["w1", "w2", "w3"], cells)
        right = alo.stratum_block(["r1", "r2"], cells)
        self.assertEqual((wrong["n"], wrong["clear_rescues"], wrong["O_versus_B"]["mean_points"]), (2, 1, 75.0))
        self.assertEqual((right["clear_regressions"], right["O_versus_B"]["mean_points"]), (1, -50.0))
        rule = {"wrong_min_gain_points": 20.0, "right_max_loss_points": 10.0}
        verdict = alo.reading_rule(wrong, right, rule)
        self.assertTrue(verdict["fixes_enough"])
        self.assertFalse(verdict["harmless_enough"])
        self.assertFalse(verdict["retrieval_study_worth_building"])
        self.assertTrue(alo.reading_rule(wrong, alo.stratum_block(["r1"], cells), rule)["retrieval_study_worth_building"])
        self.assertEqual(alo.letter_share(cells, "B"), 1.0)

    def test_gold_check_counts_which_option_each_arm_picks_where_the_law_contradicts_the_gold(self):
        def row(prediction: str) -> dict:
            return {"prediction": prediction, "gold_answer": "B", "correct": int(prediction == "B")}
        cells = {"c1": {"B1": row("B"), "B2": row("B"), "O1": row("A"), "O2": row("")},
                 "s1": {"B1": row("B"), "B2": row("C"), "O1": row("B"), "O2": row("B")}}
        check = alo.gold_check(cells, {"c1": "contradicts_gold", "s1": "supports_gold"}, {"c1": "A", "s1": "B"})
        self.assertEqual((check["reviewed"], check["owner_equals_gold"], check["owner_differs"]), (2, 1, ["c1"]))
        self.assertEqual(check["contradicts_gold_picks"]["B"], {"answers": 2, "gold_option": 2, "owner_option": 0,
                                                                "other": 0})
        self.assertEqual(check["contradicts_gold_picks"]["O"], {"answers": 2, "gold_option": 0, "owner_option": 1,
                                                                "other": 1})

    def test_the_owner_review_must_carry_its_registered_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owner_review.json"
            path.write_text(json.dumps({"answers": {"LG-0001": "A"}}), encoding="utf-8")
            entry = {"file": "owner_review.json", "sha256": v1.sha256_file(path)}
            self.assertEqual(alo.owner_answers({"owner_review": entry}, Path(tmp)), {"LG-0001": "A"})
            with self.assertRaises(SystemExit):
                alo.owner_answers({"owner_review": {**entry, "sha256": "0" * 64}}, Path(tmp))

    def test_every_manifest_attempt_needs_a_scored_row(self):
        manifest = {"items": [{"dataset_id": lo.DATASET, "item_id": "LG-0001", "replicate_id": "B-r1"}]}
        with self.assertRaises(SystemExit):
            alo.load_cells([], manifest)


class TestRunnerGates(unittest.TestCase):
    def test_gates(self):
        campaign = {"model": {"endpoint_host": "gateway.example", "endpoint_path": "/v1", "requested_id": "qwen"}}
        manifest = {name: "x" for name in rlo.FROZEN_KEYS}
        registration = {"card_ids": {lo.PHASE: "MC-100"}, "card_files": {lo.PHASE: "missing.md"},
                        "frozen": {**manifest, "evidence_sha256": "y"}}
        env = {"OPENAI_BASE_URL": "https://gateway.example/v1", "OPENAI_MODEL": "qwen", "OPENAI_API_KEY": "k"}
        gates = {gate.name: gate.ok for gate in rlo.evaluate_gates(campaign, manifest, registration, env,
                                                                    card_text="## MC-100 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": False,
                                 "endpoint_identity": True})


if __name__ == "__main__":
    unittest.main()
