"""Offline tests of the Legal MC retrieval test (openspec change diagnostic-legal-retrieval). No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_legal_retrieval
"""
from __future__ import annotations

import json
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from code_benchmark import analyze_legal_retrieval as alr
from code_benchmark import diagnostic_legal_oracle as lo
from code_benchmark import diagnostic_legal_retrieval as lr
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_legal_retrieval as rlr
from code_benchmark import vi_multimodel as v1

SITE = "https://hethongphapluat.com/"
HAS_DATA = all((lo.ROOT / path).is_file() for path in lo.load_protocol()["selection"]["sources"].values())
BUILT = HAS_DATA and lr.EVIDENCE_PATH.is_file() and (lr.CORPUS_DIR / "corpus.jsonl").is_file()

DECISION = ("<html><body><dieu><p>Điều 1. Ban hành kèm theo Quyết định này Quy chế.</p></dieu>"
            "<dieu><p>Điều 2. Quyết định này có hiệu lực.</p></dieu>"
            "<p>QUY CHẾ</p><p>Chương I</p><p>QUY ĐỊNH CHUNG</p><p>Điều 1. Phạm vi</p><p>Nội dung một.</p>"
            "<p>Phụ lục kèm theo Quy chế này quy định mẫu.</p>"
            "<p>Điều 2. Cơ cấu</p><p>1. Khoản một.</p><p>Chương II</p><p>CHỦ TỊCH HỘI ĐỒNG</p>"
            "<p>Điều 3. Chủ tịch</p><p>Chủ tịch do Thủ tướng bổ nhiệm.</p><p>Văn bản liên quan cùng nội dung</p>"
            "<p>1Thông tư khác</p><p>Điều 1. Ban hành kèm theo Quyết định này Quy chế.</p></body></html>")


def mc_item(item_id: str, question: str, options: list[str], gold: str = "A") -> v1.EvalItem:
    body = question + "\n\n" + "\n".join(f"{letter}. {text}" for letter, text in zip("ABCD", options, strict=False))
    return v1.EvalItem(dataset_id=lr.DATASET, source_dataset="legal-slm", item_id=item_id, replicate_id="main-000",
                       task="multiple_choice", stratum="legal", question=question, passage_id="legal",
                       prompt=dp.MC_HEAD + body + dp.MC_TAIL, gold_answer=gold)


def listing(batch: int, items: list[dict], distractors: list[dict] | None = None) -> dict:
    return {"batch": batch, "items": items, "distractors": distractors or []}


def doc(slug: str, doc_id: str, role: str = "topical", **extra) -> dict:
    return {"url": f"{SITE}{slug}.html", "doc_id": doc_id, "title": f"Văn bản {doc_id}", "role": role, **extra}


class TestReader(unittest.TestCase):
    def test_footnote_heading_and_broken_last_element(self):
        page = ("<dieu><p>Điều 15[15]. Tên</p><p>1. Một.</p></dieu><dieu><p>Điều 16. Khác</p></dieu>"
                "<dieu><p>Điều 17. Hỏng</p>")
        self.assertEqual([number for number, _ in lr.parse_articles_v1(page)], ["15", "16"])
        with self.assertRaises(SystemExit):
            lr.parse_articles_v1("<p>Không có điều nào</p>")

    def test_attached_text_stops_at_sections_site_blocks_and_repeated_numbers(self):
        articles = dict(lr.attached_articles(DECISION, "QUY CHẾ"))
        self.assertEqual(list(articles), ["1", "2", "3"])
        self.assertIn("Phụ lục kèm theo Quy chế này quy định mẫu.", articles["1"])  # a sentence, not an annex
        self.assertNotIn("Chương II", articles["2"])
        self.assertNotIn("CHỦ TỊCH HỘI ĐỒNG", articles["2"])
        self.assertEqual(articles["3"], "Điều 3. Chủ tịch\nChủ tịch do Thủ tướng bổ nhiệm.")
        signed = DECISION.replace("<p>Văn bản liên quan cùng nội dung</p>", "<p>KT. BỘ TRƯỞNG</p>")
        self.assertEqual(dict(lr.attached_articles(signed, "QUY CHẾ"))["3"], articles["3"])
        annexed = DECISION.replace("<p>Văn bản liên quan cùng nội dung</p>", "<p>DANH MỤC PHỤ LỤC, MẪU BIỂU</p>")
        self.assertEqual(dict(lr.attached_articles(annexed, "QUY CHẾ"))["3"], articles["3"])
        with self.assertRaises(SystemExit):
            lr.attached_articles(DECISION, "QUY ĐỊNH")

    def test_long_articles_split_at_lines_and_every_part_keeps_the_heading(self):
        text = "Điều 9. Dài\n" + "\n".join(f"{n}. " + "x" * 500 for n in range(1, 30))
        parts = lr.split_text(text, 6000)
        self.assertGreater(len(parts), 2)
        self.assertTrue(all(part.startswith("Điều 9. Dài\n") and len(part) <= 6000 for part in parts))
        self.assertEqual([line for part in parts for line in part.split("\n")[1:]], text.split("\n")[1:])
        self.assertEqual(lr.split_text("Điều 1. Ngắn\nNội dung.", 6000), ["Điều 1. Ngắn\nNội dung."])

    def test_units_carry_unique_ids_and_locators(self):
        document = {"doc_id": "05/2025/QĐ-TTg", "title": "Quyết định 05/2025", "url": f"{SITE}qd.html", "part": "QUY CHẾ"}
        units = lr.document_units(document, DECISION, 6000)
        self.assertEqual([unit["chunk_id"].split("#")[1] for unit in units],
                         ["dieu-1", "dieu-2", "kem-dieu-1", "kem-dieu-2", "kem-dieu-3"])
        self.assertEqual(units[-1]["locator"], "Quy chế kèm theo, Điều 3")
        self.assertTrue(all(set(unit) == set(lo.dr.CHUNK_KEYS) for unit in units))
        long_page = "<dieu><p>Điều 4. Dài</p>" + "".join(f"<p>{n}. {'y' * 900}</p>" for n in range(1, 12)) + "</dieu>"
        split = lr.document_units({"doc_id": "1/2020/TT", "title": "t", "url": f"{SITE}t.html"}, long_page, 6000)
        self.assertEqual([unit["chunk_id"] for unit in split], ["1/2020/TT#dieu-4-p1", "1/2020/TT#dieu-4-p2"])
        self.assertEqual(split[1]["locator"], "Điều 4 (phần 2/2)")


class TestSources(unittest.TestCase):
    def setUp(self):
        self.protocol = lr.load_protocol()
        self.pool = ["LG-0001", "LG-0002", "LG-0003"]

    def lists(self):
        return [listing(1, [{"item_id": "LG-0001", "documents": [doc("luat-a", "1/2020/QH14"),
                                                               doc("luat-a-cu", "2/2010/QH12", "predecessor",
                                                                   predecessor_of="1/2020/QH14")]},
                            {"item_id": "LG-0002", "documents": []}],
                        [doc("nd-b", "3/2021/NĐ-CP")]),
                listing(2, [{"item_id": "LG-0003", "documents": [doc("nd-b", "3/2021/NĐ-CP"), doc("luat-a", "1/2020/QH14")]}])]

    def test_merge_is_deterministic_and_role_priority_holds(self):
        merged = lr.merge_sources(self.lists(), self.pool, self.protocol)
        shuffled = self.lists()[::-1]
        random.Random(1).shuffle(shuffled)
        self.assertEqual(lr.merge_sources(shuffled, self.pool, self.protocol), merged)
        by_url = {entry["url"]: entry for entry in merged["documents"]}
        self.assertEqual(by_url[f"{SITE}nd-b.html"]["role"], "topical")  # topical beats distractor
        self.assertEqual(by_url[f"{SITE}luat-a.html"]["items"], ["LG-0001", "LG-0003"])
        self.assertEqual(by_url[f"{SITE}luat-a-cu.html"]["predecessor_of"], ["1/2020/QH14"])
        self.assertEqual(merged["uncovered"], ["LG-0002"])
        self.assertEqual([entry["url"] for entry in merged["documents"]], sorted(by_url))

    def test_merge_fails_closed(self):
        bad = self.lists()
        bad[0]["items"][0]["documents"] = [doc(f"x{n}", f"{n}/2020/QH14") for n in range(4)]
        with self.assertRaises(SystemExit):  # more than 3 topical documents
            lr.merge_sources(bad, self.pool, self.protocol)
        bad = self.lists()
        bad[0]["items"][0]["documents"][1]["predecessor_of"] = "9/1999/QH10"
        with self.assertRaises(SystemExit):  # a predecessor of nothing listed
            lr.merge_sources(bad, self.pool, self.protocol)
        bad = self.lists()
        bad[1]["items"][0]["documents"][0]["url"] = "https://thuvienphapluat.vn/nd-b.html"
        with self.assertRaises(SystemExit):  # another site
            lr.merge_sources(bad, self.pool, self.protocol)
        with self.assertRaises(SystemExit):  # a pool item missing
            lr.merge_sources(self.lists(), self.pool + ["LG-0004"], self.protocol)
        bad = self.lists()
        bad[1]["items"][0]["documents"].append(doc("luat-a-hop-nhat", "1/2020/QH14"))
        with self.assertRaises(SystemExit):  # one document number on two pages
            lr.merge_sources(bad, self.pool, self.protocol)

    def test_a_consolidated_number_reused_in_another_year_is_qualified_by_its_year(self):
        lists = self.lists()
        lists[0]["items"][1]["documents"] = [{**doc("vbhn-dau-tu", "09/VBHN-VPQH"),
                                              "title": "Văn bản hợp nhất 09/VBHN-VPQH năm 2025 hợp nhất Luật Đầu tư"}]
        lists[1]["items"][0]["documents"].append({**doc("vbhn-thads", "09/VBHN-VPQH"),
                                                  "title": "Văn bản hợp nhất 09/VBHN-VPQH năm 2022 hợp nhất Luật THADS"})
        merged = lr.merge_sources(lists, self.pool, self.protocol)
        self.assertEqual(sorted(entry["doc_id"] for entry in merged["documents"] if "VBHN" in entry["doc_id"]),
                         ["09/VBHN-VPQH (2022)", "09/VBHN-VPQH (2025)"])
        self.assertEqual(len(merged["renamed"]), 2)
        same_year = json.loads(json.dumps(lists, ensure_ascii=False).replace("năm 2022", "năm 2025"))
        with self.assertRaises(SystemExit):  # same year: a real clash
            lr.merge_sources(same_year, self.pool, self.protocol)


class TestCorpusAndRetrieval(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.corpus_dir = self.tmp / "corpus"
        (self.corpus_dir / "raw").mkdir(parents=True)
        pages = {
            "thue": ("<dieu><p>Điều 35. Sử dụng mã số thuế</p><p>1. Người nộp thuế phải ghi mã số thuế vào hóa đơn."
                     "</p></dieu><dieu><p>Điều 36. Thay đổi thông tin</p><p>1. Thông báo thay đổi trong 10 ngày.</p>"
                     "</dieu>"),
            "giao-thong": ("<dieu><p>Điều 6. Xử phạt người điều khiển xe mô tô</p><p>1. Phạt tiền vượt đèn đỏ.</p>"
                           "</dieu><dieu><p>Điều 7. Xử phạt người điều khiển xe ô tô</p>"
                           "<p>1. Phạt tiền khi không thắt dây an toàn.</p></dieu>"),
        }
        log = []
        for slug, page in pages.items():
            raw = page.encode("utf-8")
            (self.corpus_dir / "raw" / f"{slug}.html").write_bytes(raw)
            log.append({"url": f"{SITE}{slug}.html", "file": f"{slug}.html", "sha256": v1.sha256_bytes(raw)})
        (self.corpus_dir / "fetch_log.jsonl").write_text("".join(json.dumps(row) + "\n" for row in log))
        self.sources = {"corpus_id": "vi-legal-corpus-lmc-v1", "documents": [
            {"doc_id": "38/2019/QH14", "title": "Luật Quản lý thuế 2019", "url": f"{SITE}thue.html", "role": "topical"},
            {"doc_id": "168/2024/NĐ-CP", "title": "Nghị định 168/2024", "url": f"{SITE}giao-thong.html",
             "role": "distractor"},
            {"doc_id": "1/2000/QH10", "title": "Thiếu", "url": f"{SITE}missing.html", "role": "predecessor"}]}
        self.items = [mc_item("LG-0001", "Người nộp thuế phải ghi mã số thuế ở đâu?",
                              ["Trên hóa đơn", "Trên hợp đồng", "Không cần ghi", "Tùy chọn"]),
                      mc_item("LG-0002", "Xe mô tô vượt đèn đỏ bị phạt thế nào?",
                              ["Phạt tiền", "Cảnh cáo", "Tịch thu xe", "Không phạt"])]
        self.config = self.tmp / "retrieval.json"
        shutil.copyfile(lr.RETRIEVAL_PATH, self.config)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self):
        return lr.build_corpus(self.sources, self.items, 6000, "0" * 64, self.corpus_dir)

    def test_corpus_lists_omitted_documents_and_fails_on_a_copied_question(self):
        units, manifest, leak = self.build()
        self.assertEqual(len(units), 4)
        self.assertEqual([row["doc_id"] for row in manifest["omitted"]], ["1/2000/QH10"])
        self.assertTrue(leak["passed"])
        leaky = self.items + [mc_item("LG-0003", "Người nộp thuế phải ghi mã số thuế vào hóa đơn",
                                      ["A1", "B1", "C1", "D1"])]
        with self.assertRaises(SystemExit):
            lr.build_corpus(self.sources, leaky, 6000, "0" * 64, self.corpus_dir)

    def test_k_evidence_ties_units_to_the_corpus_and_rejects_a_swap(self):
        self.build()
        index = lr.load_index(self.corpus_dir, self.config)
        records = [lr.k_record(index, item) for item in self.items]
        self.assertEqual(records[0]["provisions"][0]["locator"], "Điều 35")
        self.assertEqual(records[1]["provisions"][0]["doc_id"], "168/2024/NĐ-CP")
        path = self.tmp / "k.jsonl"
        v1.write_jsonl_atomic(path, records)
        self.assertEqual(set(lr.load_k_evidence(path, ["LG-0001", "LG-0002"], index)), {"LG-0001", "LG-0002"})
        traces = lr.retrieval_traces({"pool": ["LG-0001", "LG-0002"]}, path)
        self.assertEqual(set(traces), {f"{lr.DATASET}:LG-0001", f"{lr.DATASET}:LG-0002"})
        self.assertEqual([entry["chunk_id"] for entry in traces[f"{lr.DATASET}:LG-0001"]["ranking"]],
                         [entry["chunk_id"] for entry in records[0]["ranking"][:2]])
        swapped = json.loads(json.dumps(records))
        swapped[0]["provisions"][0], swapped[1]["provisions"][0] = records[1]["provisions"][0], records[0]["provisions"][0]
        v1.write_jsonl_atomic(path, swapped)
        with self.assertRaises(SystemExit):
            lr.load_k_evidence(path, ["LG-0001", "LG-0002"], index)
        stale = [{**record, "corpus_sha256": "f" * 64} for record in records]
        v1.write_jsonl_atomic(path, stale)
        with self.assertRaises(SystemExit):
            lr.load_k_evidence(path, ["LG-0001", "LG-0002"], index)

    def test_hits_match_document_number_article_and_attached_part(self):
        self.assertEqual(lr.doc_key(" 168/2024/NĐ-CP "), lr.doc_key("168/2024/nd-cp"))
        self.assertEqual(lr.unit_target("38/2019/QH14#dieu-35-p2"), (lr.doc_key("38/2019/QH14"), "", "35"))
        self.assertEqual(lr.unit_target("05/2025/QĐ-TTg#kem-dieu-3"), (lr.doc_key("05/2025/QĐ-TTg"), "kem", "3"))
        self.build()
        index = lr.load_index(self.corpus_dir, self.config)
        records = {item.item_id: lr.k_record(index, item) for item in self.items}
        oracle = {"LG-0001": {"provisions": [{"doc_id": "38/2019/QH14", "locator": "Điều 35, khoản 1"}]},
                  "LG-0002": {"provisions": [{"doc_id": "168/2024/NĐ-CP", "locator": "Quy chế kèm theo, Điều 6"}]},
                  "LG-0009": {"provisions": []}}
        report = lr.hit_report(records, oracle, index)
        self.assertEqual((report["items"], report["hit_at_1"], report["hit_at_3"]), (2, 1, 1))
        self.assertEqual(report["oracle_documents_in_corpus"], 2)


@unittest.skipUnless(HAS_DATA, "needs the MC-90 and MC-91 score files")
class TestStems(unittest.TestCase):
    def test_stems_have_no_options_and_cover_the_pool_in_batches(self):
        protocol = lr.load_protocol()
        pool = lr.pool_ids(protocol)
        batches = lr.stem_batches(pool, lo.legal_items(), 4)
        self.assertEqual([len(batch) for batch in batches], [34, 34, 33, 33])
        rows = [row for batch in batches for row in batch]
        self.assertEqual([row["item_id"] for row in rows], pool)
        self.assertFalse(any(re.search(r"(?m)^[A-E]\.\s", row["stem"]) or "Đáp án" in row["stem"] for row in rows))


@unittest.skipUnless(BUILT, "needs the built corpus and the K evidence")
class TestManifest(unittest.TestCase):
    def test_prompts_and_counts(self):
        manifest, rebuilt = lr.build_manifest()
        frozen = lo.legal_items()
        mc100 = {dp.run_key(ref): ref["prompt_sha256"] for ref in lo.load_frozen_manifest()["items"]}
        templates = dp.load_templates()
        records = {json.loads(line)["item_id"]: json.loads(line)
                   for line in lr.EVIDENCE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}
        for key, item in rebuilt.items():
            arm, base = dp.arm_of_replicate(item.replicate_id), frozen[item.item_id]
            if arm == "B":
                self.assertEqual(item.prompt, base.prompt)
            elif arm == "K":
                self.assertEqual(item.prompt, dp.render_evidence_block(records[item.item_id]["provisions"], templates)
                                 + base.prompt)
            else:
                self.assertEqual(v1.sha256_bytes(item.prompt.encode("utf-8")), mc100[key])
            self.assertNotIn(f"Đáp án: {base.gold_answer}", item.prompt)
        self.assertEqual(manifest["arm_counts"]["B"], 268)
        self.assertEqual(manifest["arm_counts"]["K"], 268)


class TestAnalysis(unittest.TestCase):
    @staticmethod
    def cell(**arms: tuple[int, int]) -> dict:
        return {f"{arm}{draw}": {"correct": value[index], "prediction": "A" if value[index] else "B", "gold_answer": "A"}
                for arm, value in arms.items() for index, draw in enumerate(alr.DRAWS)}

    def test_reading_rule_both_ways_and_strata(self):
        cells = {f"i{n}": self.cell(B=(0, 0), K=(1, 1), O=(1, 1)) for n in range(12)}
        cells.update({f"j{n}": self.cell(B=(1, 1), K=(1, 1)) for n in range(12)})
        primary = alr.compare(sorted(cells), cells, "K", "B")
        self.assertEqual(primary["K_versus_B"]["mean_points"], 50.0)
        self.assertEqual(alr.reading_rule(primary, 0.05)["legal_mc_route"], "K")
        flat = {key: self.cell(B=(1, 0), K=(1, 0)) for key in cells}
        self.assertEqual(alr.reading_rule(alr.compare(sorted(flat), flat, "K", "B"), 0.05)["legal_mc_route"], "B")
        strata = {"wrong": [f"i{n}" for n in range(12)], "right": [f"j{n}" for n in range(12)]}
        support = {item: "supports_gold" for items in strata.values() for item in items}
        blocks = alr.stratum_blocks(strata, support, cells)
        self.assertEqual(blocks["wrong"]["share_of_O_gain_kept_by_K"], 1.0)
        self.assertEqual(blocks["right"]["O_vs_B"], {"n": 0})

    def test_hit_split_and_gold_check(self):
        cells = {"h": self.cell(B=(0, 0), K=(1, 1), O=(1, 1)), "m": self.cell(B=(0, 0), K=(0, 0), O=(1, 0))}
        hits = {"per_item": [{"item_id": "h", "first_hit_rank": 2}, {"item_id": "m", "first_hit_rank": 3}]}
        split = alr.hit_split(hits, cells)
        self.assertEqual((split["hit_at_2"]["K"], split["miss_at_2"]["K"], split["miss_at_2"]["O"]), (100.0, 0.0, 50.0))
        check = alr.gold_check(cells, {"m": "contradicts_gold", "h": "supports_gold"}, {"m": "B"})
        self.assertEqual(check["picks"]["K"], {"answers": 2, "gold_option": 0, "owner_option": 2, "other": 0})
        self.assertEqual(check["picks"]["O"], {"answers": 2, "gold_option": 1, "owner_option": 1, "other": 0})

    def test_every_manifest_attempt_needs_a_scored_row(self):
        with self.assertRaises(SystemExit):
            alr.load_cells([], {"items": [{"dataset_id": lr.DATASET, "item_id": "LG-0001", "replicate_id": "K-r1"}]})


class TestRunnerGates(unittest.TestCase):
    def test_gates(self):
        campaign = {"model": {"endpoint_host": "gateway.example", "endpoint_path": "/v1", "requested_id": "qwen"}}
        manifest = {name: "x" for name in rlr.FROZEN_KEYS}
        registration = {"card_ids": {lr.PHASE: "MC-101"}, "card_files": {lr.PHASE: "missing.md"},
                        "frozen": {**manifest, "corpus_sha256": "y"}}
        env = {"OPENAI_BASE_URL": "https://gateway.example/v1", "OPENAI_MODEL": "qwen", "OPENAI_API_KEY": "k"}
        gates = {gate.name: gate.ok for gate in rlr.evaluate_gates(campaign, manifest, registration, env,
                                                                    card_text="## MC-101 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": False,
                                 "endpoint_identity": True})


if __name__ == "__main__":
    unittest.main()
