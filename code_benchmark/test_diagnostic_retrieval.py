"""Offline tests for corpus v0 and lexical retrieval (arms K and KS) of the prospective diagnostic campaign.

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_retrieval
No test fetches a page or contacts an endpoint.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_retrieval as dr
from code_benchmark import vi_multimodel as v1

PROTOCOL = dp.load_protocol()
MC_DATASET = "vi-multimodel-v1-legal-mc-146"
QUESTION = "Biển số xe có ký hiệu CV được cấp cho đối tượng nào theo quy định hiện hành?"
BODY = f"{QUESTION}\n\nA. Xe của cơ quan ngoại giao\nB. Xe quân sự\nC. Xe công an\nD. Xe cá nhân"
PAGE = """<html><head><script>// đợi các <dieu> đã render
var tag = "<dieu>";</script></head><body>
<div id="r-toc"><ul class="dieu-list"><li><a title="Điều 1. Phạm vi">Điều 1. Phạm vi</a></li></ul></div>
<chuong><p><b>Chương I</b></p>
<dieu address="a"><p><b>Điều 1. Biển số xe</b></p><khoan><p>1. Biển số nền trắng&nbsp;có ký hiệu “CV”.</p></khoan></dieu>
<dieu address="b"><p><b>Điều 2. Sửa đổi luật khác</b></p><p>Điều 5 được sửa đổi như sau:</p>
<dieu address="c"><p>“Điều 5. Mức phạt</p><p>Phạt tiền từ 1 triệu đồng.”</p></dieu></dieu>
</chuong><!-- <dieu> in a comment --></body></html>"""


def mc_item(item_id: str = "T1", body: str = BODY) -> v1.EvalItem:
    return v1.EvalItem(dataset_id=MC_DATASET, source_dataset="test", item_id=item_id, replicate_id=dp.MAIN_REPLICATE,
                       task="multiple_choice", stratum="s", question=QUESTION, passage_id="p1",
                       prompt=dp.MC_HEAD + body + dp.MC_TAIL, gold_answer="A")


def chunk(doc_id: str, article: str, text: str) -> dict:
    return {"chunk_id": f"{doc_id}#dieu-{article}", "doc_id": doc_id, "doc_title": f"Văn bản {doc_id}",
            "article": article, "locator": f"Điều {article}", "text": text,
            "text_sha256": v1.sha256_bytes(text.encode("utf-8")), "source_ref": "https://example.test/doc"}


CHUNKS = [chunk("d1", "1", "Điều 1. Biển số xe\nBiển số nền trắng có ký hiệu CV cấp cho xe của cơ quan ngoại giao."),
          chunk("d1", "2", "Điều 2. Đăng ký xe\nXe quân sự đăng ký tại Bộ Quốc phòng."),
          chunk("d2", "7", "Điều 7. Mức lương cơ sở\nMức lương cơ sở là 2.340.000 đồng/tháng.")]
CONFIG = {"corpus_id": "c", "unit": "article", "query": "mc_body", "bigrams": True,
          "bm25": {"k1": 1.2, "b": 0.75}, "top_k": 2}


def index(chunks=CHUNKS, config=CONFIG) -> dr.Index:
    return dr.build_index(list(chunks), {"corpus_id": "c", "corpus_sha256": "c" * 64}, config, "f" * 64)


def load_k(*records, main_items=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "retrieved.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        return dp.load_retrieved_evidence(path, PROTOCOL, main_items or {mc_item().run_key: mc_item()})


class TestArticles(unittest.TestCase):
    def test_top_level_articles_skip_scripts_toc_and_keep_quoted_articles(self):
        articles = dr.parse_articles(PAGE)
        self.assertEqual([number for number, _ in articles], ["1", "2"])
        self.assertEqual(articles[0][1], "Điều 1. Biển số xe\n1. Biển số nền trắng có ký hiệu “CV”.")
        self.assertIn("“Điều 5. Mức phạt\nPhạt tiền từ 1 triệu đồng.”", articles[1][1])

    def test_malformed_pages_fail_closed(self):
        cases = {"no article": "<p>Điều 1. Không có thẻ</p>",
                 "does not open with its heading": "<dieu><p>Nội dung</p></dieu>",
                 "ends inside": "<dieu><p>Điều 1. Mở</p>",
                 "repeated": "<dieu><p>Điều 1. A</p></dieu><dieu><p>Điều 1. B</p></dieu>"}
        for reason, page in cases.items():
            with self.subTest(reason), self.assertRaises(SystemExit) as caught:
                dr.parse_articles(page)
            self.assertIn(reason, str(caught.exception))

    def test_chunks_carry_the_provision_keys_and_their_text_hash(self):
        document = {"doc_id": "79/2024/TT-BCA", "title": "Thông tư thử", "url": "https://example.test/tt"}
        chunks = dr.document_chunks(document, PAGE)
        self.assertEqual([c["chunk_id"] for c in chunks], ["79/2024/TT-BCA#dieu-1", "79/2024/TT-BCA#dieu-2"])
        self.assertEqual(set(chunks[0]), set(dr.CHUNK_KEYS))
        self.assertTrue(set(dp.PROVISION_KEYS) <= set(chunks[0]))
        self.assertEqual(chunks[0]["text_sha256"], v1.sha256_bytes(chunks[0]["text"].encode("utf-8")))


class TestBM25(unittest.TestCase):
    def test_tokens_are_nfc_lower_case_syllables_with_bigrams(self):
        self.assertEqual(dr.tokenize("Biển SỐ xe", True), ["biển", "số", "xe", "biển_số", "số_xe"])
        self.assertEqual(dr.tokenize(unicodedata.normalize("NFD", "Biển số"), False), ["biển", "số"])

    def test_scores_rank_matching_articles_and_ties_keep_corpus_order(self):
        ranked = dr.rank(index(), "ký hiệu CV cơ quan ngoại giao")
        self.assertEqual(ranked[0][0], 0)
        twins = [chunk("d", "1", "Điều 1. Giống nhau"), chunk("d", "2", "Điều 2. Giống nhau")]
        self.assertEqual([p for p, _ in dr.rank(index(twins), "giống nhau")], [0, 1])
        self.assertEqual(dr.rank(index(), "zzz qqq"), [])

    def test_idf_never_goes_negative_for_a_term_in_every_article(self):
        bm25 = dr.BM25([["xe"], ["xe"], ["xe", "biển"]], 1.2, 0.75)
        self.assertTrue(all(score > 0 for score in bm25.scores(["xe"])))


class TestRetrievedEvidence(unittest.TestCase):
    def test_record_holds_the_top_k_articles_and_loads_through_the_runner_loader(self):
        record = dr.retrieved_record(index(), mc_item(), "insufficient")
        self.assertEqual(set(record), set(dp.RETRIEVED_KEYS))
        self.assertEqual(len(record["provisions"]), 2)
        self.assertEqual(record["ranking"][0]["chunk_id"], "d1#dieu-1")
        self.assertEqual(record["query_sha256"], v1.sha256_bytes(BODY.encode("utf-8")))
        loaded, traces = load_k(record)
        key = f"{MC_DATASET}:T1"
        self.assertEqual(loaded[key], record["provisions"])
        self.assertEqual(traces[key]["ranking"], record["ranking"])
        self.assertEqual(traces[key]["corpus_sha256"], "c" * 64)

    def test_loader_rejects_a_swapped_provision_rising_scores_and_mixed_sources(self):
        record = dr.retrieved_record(index(), mc_item(), "insufficient")
        swapped = copy.deepcopy(record)
        swapped["ranking"][0]["text_sha256"] = "0" * 64
        rising = copy.deepcopy(record)
        rising["ranking"][1]["score"] = rising["ranking"][0]["score"] + 1
        other = dr.retrieved_record(index(), mc_item("T2"), "insufficient")
        other["corpus_sha256"] = "d" * 64
        main_items = {mc_item(i).run_key: mc_item(i) for i in ("T1", "T2")}
        for records, reason in (((swapped,), "differs from the ranked chunk"), ((rising,), "non-increasing"),
                                ((record, other), "corpus/configuration pairs")):
            with self.subTest(reason), self.assertRaises(SystemExit) as caught:
                load_k(*records, main_items=main_items)
            self.assertIn(reason, str(caught.exception))

    def test_statute_wording_passes_for_corpus_text_but_answer_keys_never_do(self):
        text = "Điều 3. Giải thích từ ngữ\nTrong Luật này, các từ ngữ dưới đây được hiểu như sau."
        statute = [{"doc_id": "d", "doc_title": "t", "locator": "Điều 3", "text": text,
                    "text_sha256": v1.sha256_bytes(text.encode("utf-8")), "source_ref": "s"}]
        self.assertEqual(dp.validate_provisions(statute, "k", verbatim_source=True), statute)
        with self.assertRaises(SystemExit):
            dp.validate_provisions(statute, "o")
        keyed = copy.deepcopy(statute)
        keyed[0]["text"] = "Đáp án: C"
        keyed[0]["text_sha256"] = v1.sha256_bytes("Đáp án: C".encode("utf-8"))
        with self.assertRaises(SystemExit):
            dp.validate_provisions(keyed, "k", verbatim_source=True)

    def test_hit_report_finds_the_cited_article_and_its_rank(self):
        record = dr.retrieved_record(index(), mc_item(), "insufficient")
        cited = [{"doc_id": "d1", "doc_title": "t", "locator": "Điều 1 khoản 1", "text": "x",
                  "text_sha256": "", "source_ref": "s"}]
        key = f"{MC_DATASET}:T1"
        report = dr.hit_report(index(), [record], {key: cited}, {mc_item().run_key: mc_item()})
        self.assertEqual((report["hits"], report["misses"]), (1, []))
        self.assertEqual(report["per_anchor"][0]["rank_of_cited"], {"d1#dieu-1": 1})
        cited[0]["doc_id"] = "d9"
        missed = dr.hit_report(index(), [record], {key: cited}, {mc_item().run_key: mc_item()})
        self.assertEqual((missed["hits"], missed["misses"]), (0, [key]))
        self.assertIsNone(missed["per_anchor"][0]["rank_of_cited"]["d9#dieu-1"])


class TestCorpusChecks(unittest.TestCase):
    def test_a_copied_question_or_an_answer_key_fails_and_options_are_only_counted(self):
        self.assertTrue(dr.leak_report(CHUNKS, [mc_item()])["passed"])
        copied = CHUNKS + [chunk("d3", "1", f"Điều 1. Hỏi đáp\n{QUESTION}")]
        keyed = CHUNKS + [chunk("d3", "1", "Điều 1. Ôn thi\nĐáp án: A")]
        option = CHUNKS + [chunk("d3", "1", "Điều 1. X\nXe của cơ quan ngoại giao được miễn thuế theo luật riêng")]
        self.assertEqual(dr.leak_report(copied, [mc_item()])["questions_in_corpus"], [f"{MC_DATASET}:T1"])
        self.assertEqual(dr.leak_report(keyed, [mc_item()])["answer_key_chunks"], ["d3#dieu-1"])
        long_option = BODY.replace("A. Xe của cơ quan ngoại giao", "A. Xe của cơ quan ngoại giao được miễn thuế")
        counted = dr.leak_report(option, [mc_item(body=long_option)])
        self.assertTrue(counted["passed"])
        self.assertEqual(counted["options_verbatim_in_corpus"], 1)

    def test_oracle_provisions_are_looked_up_line_by_line_in_their_article(self):
        good = {"doc_id": "d1", "locator": "Điều 1 khoản 1", "text": "Biển số nền trắng có ký hiệu CV"}
        bad = {**good, "text": "Biển số nền trắng có ký hiệu CV\nDòng không có trong luật"}
        self.assertTrue(dr.oracle_crosscheck(CHUNKS, {"k": [good]})["all_found"])
        result = dr.oracle_crosscheck(CHUNKS, {"k": [bad]})
        self.assertFalse(result["all_found"])
        self.assertEqual(result["per_provision"][0]["lines_missing"], 1)


class TestSourcesAndConfig(unittest.TestCase):
    def write(self, value) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "file.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_committed_sources_and_configuration_load_and_agree(self):
        sources, _ = dr.load_sources()
        config, digest = dr.load_config()
        self.assertEqual(sources["corpus_id"], config["corpus_id"])
        self.assertEqual(digest, v1.sha256_file(dr.CONFIG_PATH))
        roles = {document["role"] for document in sources["documents"]}
        self.assertEqual(roles, set(dr.ROLES))

    def test_bad_sources_fail_closed(self):
        cited = {"doc_id": "1/2024/QH15", "role": "cited", "title": "Luật", "url": "https://example.test/a"}
        cases = {"duplicate": [cited, cited],
                 "https only": [{**cited, "url": "http://example.test/a"}],
                 "predecessor_of is required": [cited, {**cited, "doc_id": "2", "role": "predecessor"}],
                 "names no cited document": [cited, {**cited, "doc_id": "2", "role": "predecessor",
                                                     "predecessor_of": "9"}]}
        for reason, documents in cases.items():
            with self.subTest(reason), self.assertRaises(SystemExit) as caught:
                dr.load_sources(self.write({"corpus_id": "c", "documents": documents}))
            self.assertIn(reason, str(caught.exception))

    def test_bad_configuration_fails_closed(self):
        for broken in ({**CONFIG, "top_k": 0}, {**CONFIG, "unit": "clause"}, {**CONFIG, "bm25": {"k1": 1.2}}):
            with self.subTest(broken), self.assertRaises(SystemExit):
                dr.load_config(self.write(broken))


if __name__ == "__main__":
    unittest.main()
