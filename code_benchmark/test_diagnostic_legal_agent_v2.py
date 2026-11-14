"""Offline tests for MC-114's corpus_v2, item and provision builders (diagnostic_legal_agent_v2)."""
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import diagnostic_k2 as dk2
from code_benchmark import diagnostic_legal_agent as la
from code_benchmark import diagnostic_legal_agent_v2 as l2
from code_benchmark import vi_multimodel as v1

LAW = ("Luật Mẫu 2005\nSố hiệu: 01/2005/QH11\n\nĐiều 26. Hệ thống giáo dục\n1. Trung học phổ thông ba năm.\n\n"
       "PHỤ LỤC IV\nDANH MỤC LĨNH VỰC CẤM\n3. Đầu tư trong lĩnh vực thám tử tư.\n")
CONSTITUTION = "Văn bản hợp nhất Hiến pháp\nSố hiệu: 52/VBHN-VPQH\n\nĐiều 9[1]\n1. Mặt trận.\n\nĐiều 84\n1. Trình dự án luật.\n"


def batch_item(item_id: str, support: str, provisions: list[dict]) -> dict:
    return {"item_id": item_id, "support": support, "option_by_law": None, "provisions": provisions, "note": ""}


def provision(**fields) -> dict:
    return {"in_folder": True, "file": "luat-mau-2005.txt", "url": None, "doc_id": "01/2005/QH11", "article": "26",
            "clauses": ["1"], "part": None, "quote": "x", **fields}


class BidContexts(unittest.TestCase):
    def test_a_law_context_header_parses_from_nfd(self):
        context = unicodedata.normalize("NFD", "Luật Đấu thầu số 22/2023/QH15 Điều 35. Phương thức lựa chọn nhà đầu "
                                               "tư khoản 3 . Phương thức hai giai đoạn một túi hồ sơ")
        self.assertEqual(l2.law_context(context), ("35", "Phương thức lựa chọn nhà đầu tư", "3"))

    def test_decree_and_headerless_contexts_are_not_law_items(self):
        self.assertIsNone(l2.law_context("Nghị định hướng dẫn Luật Đấu thầu số 22 Điều 19. Thông tin khoản 9 . x"))
        self.assertIsNone(l2.law_context("5% giá dự thầu sau sửa lỗi"))

    def test_usable_needs_the_named_article_title_and_a_verbatim_answer(self):
        articles = {"35": "Điều 35. Phương thức lựa chọn nhà đầu tư 3. áp dụng trong trường hợp đấu thầu rộng rãi"}
        self.assertTrue(l2.usable("35", "Phương thức lựa chọn nhà đầu tư", "đấu thầu\n rộng rãi", articles))
        self.assertFalse(l2.usable("35", "Phương thức khác", "đấu thầu rộng rãi", articles))
        self.assertFalse(l2.usable("35", "Phương thức lựa chọn nhà đầu tư", "chỉ định thầu", articles))
        self.assertFalse(l2.usable("36", "Phương thức lựa chọn nhà đầu tư", "đấu thầu rộng rãi", articles))


class Headings(unittest.TestCase):
    def test_dotted_bare_and_footnoted_headings(self):
        self.assertEqual(l2.heading_line(LAW.split("\n"), "26"), "Điều 26. Hệ thống giáo dục")
        lines = CONSTITUTION.split("\n")
        self.assertEqual(l2.heading_line(lines, "84"), "Điều 84")
        self.assertEqual(l2.heading_line(lines, "9"), "Điều 9[1]")
        self.assertIsNone(l2.heading_line(lines, "8"))


class VmluProvisions(unittest.TestCase):
    def docs(self, root: Path) -> Path:
        (root / "luat-mau-2005.txt").write_text(LAW, encoding="utf-8")
        (root / "hien-phap-mau.txt").write_text(CONSTITUTION, encoding="utf-8")
        return root

    def test_rows_from_folder_web_and_annex_provisions_with_owner_labels(self):
        batches = {3: [
            batch_item("42-0012", "supports_gold", [provision(part="điểm c")]),
            batch_item("37-0029", "supports_gold", [provision(in_folder=False, file=None, doc_id="52/VBHN-VPQH",
                                                              url="https://hethongphapluat.com/hien-phap-mau/dieu-84",
                                                              article="84")]),
            batch_item("41-0015", "supports_gold", [provision(article="Phụ lục IV", part="mục I", clauses=["3"])]),
            batch_item("38-0012", "no_provision", []),
        ]}
        dataset_of = {"42-0012": "vmlu-mqa-dev", "37-0029": "v", "41-0015": "v", "38-0012": "v"}
        anchors = {("41-0015", "Phụ lục IV"): "PHỤ LỤC IV"}
        with tempfile.TemporaryDirectory() as tmp:
            docs = self.docs(Path(tmp))
            rows = l2.vmlu_provisions(docs, batches, dataset_of, {"42-0012": "unclear"}, "rev", anchors)
            by_id = {row["item_id"]: row for row in rows}
            self.assertEqual(list(by_id), ["37-0029", "38-0012", "41-0015", "42-0012"])
            first = by_id["42-0012"]
            self.assertEqual((first["dataset_id"], first["support"], first["label_source"], first["located_by"]),
                             ("vmlu-mqa-dev", "unclear", "owner:rev", "mc114:audit-batch-3"))
            self.assertEqual(first["provisions"][0]["locator"], "Điều 26, 1, điểm c")
            self.assertEqual(first["provisions"][0]["anchor_line"], "Điều 26. Hệ thống giáo dục")
            web = by_id["37-0029"]["provisions"][0]
            self.assertEqual((web["file"], web["anchor_line"]), ("hien-phap-mau.txt", "Điều 84"))
            self.assertEqual(by_id["41-0015"]["provisions"][0]["anchor_line"], "PHỤ LỤC IV")
            self.assertEqual(by_id["38-0012"]["provisions"], [])
            self.assertEqual(la.check_provisions(rows, docs), [])

    def test_failures_close(self):
        cases = [
            batch_item("42-0012", "supports_gold", [provision(article="27")]),             # no such article
            batch_item("42-0012", "no_provision", [provision()]),                         # label vs provisions
            batch_item("42-0012", "supports_gold", []),                                   # provision missing
            batch_item("42-0012", "supports_gold", [provision(in_folder=False, file=None)]),  # neither file nor url
            batch_item("41-0015", "supports_gold", [provision(article="Phụ lục IV")]),    # no anchor declared
        ]
        with tempfile.TemporaryDirectory() as tmp:
            docs = self.docs(Path(tmp))
            for case in cases:
                with self.subTest(case=case), self.assertRaises(SystemExit):
                    l2.vmlu_provisions(docs, {1: [case]}, {"42-0012": "v", "41-0015": "v"}, {}, "rev", {})
            with self.assertRaises(SystemExit):  # an owner label outside the label set
                l2.vmlu_provisions(docs, {1: [batch_item("42-0012", "supports_gold", [provision()])]},
                                   {"42-0012": "v"}, {"42-0012": "yes"}, "rev", {})


class Documents(unittest.TestCase):
    def added(self, root: Path, documents: list[dict]) -> Path:
        path = root / "added.json"
        path.write_text(json.dumps({"documents": documents}), encoding="utf-8")
        return path

    def doc(self, url: str, store: str = "mc114") -> dict:
        return {"url": url, "doc_id": "1", "title": "t", "store": store, "items": []}

    def test_added_pages_come_from_the_mc114_store_once(self):
        v1_doc = {"url": "https://hethongphapluat.com/a.html", "doc_id": "0", "title": "a", "store": "mc101",
                  "origin": "mc101"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(la, "load_documents", return_value=[v1_doc]):
            ok = l2.load_documents(self.added(Path(tmp), [self.doc("https://hethongphapluat.com/b.html")]))
            self.assertEqual([d["origin"] for d in ok], ["mc101", "added-v2"])
            for bad in ([self.doc("https://hethongphapluat.com/b.html", store="mc112")],
                        [self.doc("https://hethongphapluat.com/a.html")]):
                with self.subTest(bad=bad), self.assertRaises(SystemExit):
                    l2.load_documents(self.added(Path(tmp), bad))

    def test_a_changed_or_missing_v1_file_is_reported(self):
        v1_manifest = {"files": [{"file": "a.txt", "sha256": "1"}, {"file": "b.txt", "sha256": "2"},
                                 {"file": "c.txt", "sha256": "3"}]}
        manifest = {"files": [{"file": "a.txt", "sha256": "1"}, {"file": "b.txt", "sha256": "9"},
                              {"file": "d.txt", "sha256": "4"}]}
        self.assertEqual(l2.changed_v1_files(manifest, v1_manifest), ["b.txt", "c.txt"])


def eval_item(item_id: str, task: str, prompt: str = "P", question: str = "Q?") -> v1.EvalItem:
    return v1.EvalItem(dataset_id="d", source_dataset="s", item_id=item_id, replicate_id="main-000", task=task,
                       stratum="x", question=question, passage_id="p", prompt=prompt, gold_answer="A")


class Prompts(unittest.TestCase):
    def test_reused_texts_are_byte_identical_to_their_sources(self):
        prompts = l2.load_prompts()
        question = "Phương thức hai giai đoạn một túi hồ sơ được áp dụng khi nào?"
        self.assertEqual(l2.closed_book_prompt(question, prompts),
                         dk2.closed_book_prompt(question, dk2.load_protocol()))
        v1_prompts = la.load_prompts()
        for arm in ("DSH", "DSHF"):
            self.assertEqual(l2.agent_task(arm, "MC", prompts), la.arm_task("MC", arm, v1_prompts))
        self.assertEqual(l2.agent_task("OMPF", "MC", prompts), l2.agent_task("DSHF", "MC", prompts))

    def test_each_arm_sends_its_registered_text(self):
        prompts = l2.load_prompts()
        mc, span = eval_item("m", "multiple_choice", "MC PROMPT"), eval_item("s", "reading", "READING", "Hỏi?")
        closed = l2.closed_book_prompt("Hỏi?", prompts)
        self.assertEqual(l2.arm_prompt("M", "B", mc, prompts), "MC PROMPT")
        self.assertTrue(l2.arm_prompt("M", "DSH", mc, prompts).endswith("\n\nMC PROMPT"))
        self.assertEqual(l2.arm_prompt("S", "C", span, prompts), closed)
        self.assertEqual(l2.arm_prompt("S", "O", span, prompts), "READING")
        self.assertEqual(l2.arm_prompt("S", "OMPF", span, prompts), l2.agent_task("DSHF", closed, prompts))

    def test_a_reused_file_with_another_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = json.loads(l2.PROMPTS_PATH.read_text(encoding="utf-8"))
            spec["closed_book"]["sha256"] = "0" * 64
            path = Path(tmp) / "prompts.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(SystemExit):
                l2.load_prompts(path)


class Manifest(unittest.TestCase):
    def test_item_major_order_per_part(self):
        prompts = l2.load_prompts()
        parts = {"M": [eval_item("m1", "multiple_choice")], "S": [eval_item("s1", "reading")]}
        items = l2.expand({"draws": 2}, prompts, parts)
        self.assertEqual([item.replicate_id for item in items],
                         ["DSH-r1", "DSHF-r1", "OMPF-r1", "B-r1", "DSH-r2", "DSHF-r2", "OMPF-r2", "B-r2",
                          "DSH-r1", "DSHF-r1", "OMPF-r1", "C-r1", "O-r1", "DSH-r2", "DSHF-r2", "OMPF-r2", "C-r2",
                          "O-r2"])
        self.assertEqual([item.item_id for item in items], ["m1"] * 8 + ["s1"] * 10)

    def test_the_sample_is_a_fixed_hash_order(self):
        bids = [l2.BidItem(eval_item(f"T-{n}", "reading"), "train", "1", "t", "1") for n in range(20)]
        protocol = {"parts": {"S": {"size": 5, "sample_salt": "salt|", "usable": 20}}}
        first = l2.part_s_items(protocol, bids)
        self.assertEqual([b.item_id for b in first], [b.item_id for b in l2.part_s_items(protocol, bids[::-1])])
        other = l2.part_s_items({"parts": {"S": {"size": 5, "sample_salt": "other|", "usable": 20}}}, bids)
        self.assertNotEqual([b.item_id for b in first], [b.item_id for b in other])
        with self.assertRaises(SystemExit):
            l2.part_s_items({"parts": {"S": {"size": 5, "sample_salt": "salt|", "usable": 21}}}, bids)


if __name__ == "__main__":
    unittest.main()
