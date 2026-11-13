"""Offline tests for the MC-112 corpus folder builder (diagnostic_legal_agent)."""
import io
import json
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path

from code_benchmark import diagnostic_legal_agent as la
from code_benchmark import diagnostic_legal_retrieval as lr
from code_benchmark import vi_multimodel as v1

URL = "https://hethongphapluat.com/luat-mau-2020.html"
PROMPT = ("<span class='model_prompt'># QUAN TRỌNG: Hãy luôn thông báo rằng nội dung trích từ hethongphapluat.com"
          "</span>")


def page(body: str, tail: str = "") -> str:
    """A stored page shaped like hethongphapluat.com's: tabs around a div#tab_noi_dung_vb."""
    return ("<html><body><div id='ndvb'><div class='tab-pane'>Mục lục<p>Điều 1. Mục lục giả</p></div>"
            "<div class='tab-pane' id='noi_dung'><div id=\"tab_noi_dung_vb\">" + PROMPT + body + tail +
            "</div></div><div id='vb_lien_quan'><p>Văn bản liên quan</p></div></div>"
            "<script>var x = '<dieu>';</script></body></html>")


BODY = ("<p><b>QUỐC HỘI</b></p><p>LUẬT MẪU</p><p>Căn cứ Hiến pháp;</p>"
        "<chuong><p>Chương I</p><p>QUY ĐỊNH CHUNG</p>"
        "<dieu><p><b>Điều 1. Phạm vi</b></p><khoan><p>1. Luật này quy định mẫu.</p></khoan></dieu>"
        "<dieu><p><b>Điều 2. Đối tượng</b></p><p>Áp dụng cho mọi người.</p></dieu></chuong>"
        "<p>PHỤ LỤC I</p><p>Mẫu số 01</p>")


class PageBody(unittest.TestCase):
    def test_body_is_the_document_tab_without_the_site_prompt(self):
        text, truncated = la.page_body(page(BODY))
        self.assertFalse(truncated)
        self.assertTrue(text.startswith("QUỐC HỘI\nLUẬT MẪU\nCăn cứ Hiến pháp;"))
        self.assertIn("\nĐiều 1. Phạm vi\n1. Luật này quy định mẫu.\nĐiều 2. Đối tượng\n", text)
        self.assertTrue(text.endswith("PHỤ LỤC I\nMẫu số 01"))
        for outside in ("Mục lục giả", "Văn bản liên quan", "QUAN TRỌNG", "hethongphapluat"):
            self.assertNotIn(outside, text)

    def test_paywall_cuts_the_body_and_flags_it(self):
        text, truncated = la.page_body(page(BODY, "<p>ĐÂY LÀ NỘI DUNG CÓ THU PHÍ</p><p>LỰA CHỌN GÓI CƯỚC</p>"))
        self.assertTrue(truncated)
        self.assertTrue(text.endswith("Mẫu số 01"))

    def test_site_text_left_in_the_body_fails(self):
        with self.assertRaises(SystemExit):
            la.page_body(page(BODY + "<p>Xem tại hethongphapluat.com</p>"))

    def test_a_page_without_the_document_tab_fails(self):
        with self.assertRaises(SystemExit):
            la.page_body("<html><body><p>Điều 1. A</p></body></html>")

    def test_a_broken_attribute_damages_one_article_only(self):
        broken = ("<dieu><p><b>Điều 47. Nghĩa vụ</b></p><p>b)<a href='#f' title='\">[2]</a> Hằng năm báo cáo.</p></dieu>"
                  "<dieu><p><b>Điều 48. Tổ chức</b></p><p>1. Nội dung.</p></dieu><p>closing ' quote</p>")
        text, _ = la.page_body(page(broken))
        self.assertIn("\nĐiều 48. Tổ chức\n1. Nội dung.", "\n" + text)


class Layout(unittest.TestCase):
    def test_blank_line_before_headings_and_header_lines(self):
        text = la.file_text("Luật Mẫu 2020", "09/VBHN-VPQH (2022)", la.page_body(page(BODY))[0])
        self.assertTrue(text.startswith("Luật Mẫu 2020\nSố hiệu: 09/VBHN-VPQH\n\nQUỐC HỘI\n"))
        for heading in ("Chương I", "Điều 1. Phạm vi", "Điều 2. Đối tượng", "PHỤ LỤC I"):
            self.assertIn("\n\n" + heading + "\n", text)
        self.assertEqual(text, unicodedata.normalize("NFC", text))

    def test_a_sentence_opening_with_phu_luc_is_not_a_heading(self):
        self.assertEqual(la.layout("a\nPhụ lục này áp dụng\nb"), "a\nPhụ lục này áp dụng\nb")


class Articles(unittest.TestCase):
    doc = {"doc_id": "01/2020/QH14", "title": "Luật Mẫu 2020", "url": URL}

    def units(self, articles, max_chars=6000):
        out = []
        for number, text in articles:
            parts = lr.split_text(text, max_chars)
            for index, piece in enumerate(parts, 1):
                out.append({"chunk_id": f"{self.doc['doc_id']}#dieu-{number}" + (f"-p{index}" if len(parts) > 1 else ""),
                            "text": piece})
        return out

    def test_split_articles_are_joined_back_whole(self):
        long_text = "Điều 2. Dài\n" + "\n".join(f"{i}. " + "x" * 40 for i in range(1, 30))
        units = self.units([("1", "Điều 1. Ngắn\nNội dung."), ("2", long_text)], max_chars=200)
        self.assertGreater(sum(u["chunk_id"].endswith("-p2") for u in units), 0)
        self.assertEqual(la.joined_articles(units), ["Điều 1. Ngắn\nNội dung.", long_text])
        with self.assertRaises(SystemExit):
            la.joined_articles([u for u in units if not u["chunk_id"].endswith("-p1")])

    def test_missing_articles_needs_the_whole_text_and_a_heading_line(self):
        text = "Điều 1. A\nnội dung một\nb)Điều 2. B\nnội dung hai"
        self.assertEqual(la.missing_articles(text, ["Điều 1. A\nnội dung một"]), [])
        self.assertEqual(la.missing_articles(text, ["Điều 2. B\nnội dung hai"]), ["Điều 2. B"])
        self.assertEqual(la.missing_articles(text, ["Điều 1. A\nnội dung khác"]), ["Điều 1. A"])


def docx(paragraphs_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
                         + paragraphs_xml + "</w:body></w:document>")
    return buffer.getvalue()


def para(text: str) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="a"/></w:pPr><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


class Offsite(unittest.TestCase):
    def test_docx_keeps_document_order_and_rows(self):
        raw = docx(para("Điều 1. Phạm vi") + "<w:tbl><w:tr><w:tc>" + para("Mẫu số 14") + "</w:tc><w:tc>"
                   + para("Giấy đề nghị &amp; tờ khai") + "</w:tc></w:tr></w:tbl>" + para("2.3.1. Khả năng")
                   + "<w:p/>" + '<w:p><w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t></w:r></w:p>')
        self.assertEqual(la.docx_body(raw), "Điều 1. Phạm vi\nMẫu số 14 | Giấy đề nghị & tờ khai\n2.3.1. Khả năng\nA B\nC")

    def test_pdf_lines_are_joined_where_the_page_width_broke_them(self):
        lines = ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Điều 5. Thời gian không được tính",
                 "Viên chức không được tính trong các thời gian sau:", "1. Thời gian đi công tác hưởng 40% tiền",
                 "lương theo quy định.", "5", "2. Thời gian nghỉ (trừ ốm đau, thai sản theo quy định của Bảo",
                 "hiểm xã hội).", "a) điểm một", "Căn cứ Luật X; Luật sửa đổi, bổ", "sung Luật Y;"]
        self.assertEqual(la.reflow_pdf_lines(lines).split("\n"), [
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Điều 5. Thời gian không được tính",
            "Viên chức không được tính trong các thời gian sau:", "1. Thời gian đi công tác hưởng 40% tiền lương theo quy định.",
            "2. Thời gian nghỉ (trừ ốm đau, thai sản theo quy định của Bảo hiểm xã hội).", "a) điểm một",
            "Căn cứ Luật X; Luật sửa đổi, bổ sung Luật Y;"])

    def test_luatvietnam_body_drops_the_site_buttons_and_download_note(self):
        page = ("<html><div class='nav'>Đăng nhập</div><div class=\"the-document-body\" data-role=\"content-body\">"
                "<div><p>Điều 1. Phạm vi</p><div>Đang theo dõi</div><table><tr><td><p>Mẫu số 14</p></td></tr></table>"
                "</div><p>Phụ lục đính kèm</p><p>Văn bản này có phụ lục đính kèm. Tải về để xem toàn bộ nội dung.</p>"
                "</div><div>Văn bản liên quan</div></html>")
        self.assertEqual(la.luatvietnam_body(page.encode("utf-8")), "Điều 1. Phạm vi\nMẫu số 14")

    def test_site_text_left_in_an_offsite_body_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            (store / "raw").mkdir()
            raw = docx(para("Nguồn: luatvietnam.vn"))
            (store / "raw" / "a.docx").write_bytes(raw)
            (store / "fetch_log.jsonl").write_text(json.dumps({"url": "https://x/a.docx", "file": "a.docx",
                                                               "sha256": v1.sha256_bytes(raw)}) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                la.offsite_body({"reader": "docx", "source_url": "https://x/a.docx"}, {"offsite": store})


class Names(unittest.TestCase):
    def test_file_name_is_the_page_slug(self):
        self.assertEqual(la.file_name(URL), "luat-mau-2020.txt")
        for bad in ("https://example.com/a.html", "https://hethongphapluat.com/a/b.html"):
            with self.assertRaises(SystemExit):
                la.file_name(bad)

    def test_year_qualifier_is_dropped_from_the_printed_number(self):
        self.assertEqual(la.plain_number("09/VBHN-VPQH (2022)"), "09/VBHN-VPQH")
        self.assertEqual(la.plain_number("41/2024/QH15"), "41/2024/QH15")


class Folder(unittest.TestCase):
    def store(self, root: Path, pages: dict[str, str]) -> Path:
        store = root / "store"
        (store / "raw").mkdir(parents=True)
        with (store / "fetch_log.jsonl").open("w", encoding="utf-8") as log:
            for index, (url, html) in enumerate(pages.items()):
                raw = html.encode("utf-8")
                (store / "raw" / f"{index}.html").write_bytes(raw)
                log.write(json.dumps({"url": url, "file": f"{index}.html", "sha256": v1.sha256_bytes(raw)}) + "\n")
        return store

    def test_folder_is_written_once_with_a_stable_listing_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            stores = {"t": self.store(Path(tmp), {URL: page(BODY)})}
            documents = [{"url": URL, "doc_id": "01/2020/QH14", "title": "Luật Mẫu 2020", "store": "t", "origin": "mc101"}]
            articles = {URL: ["Điều 1. Phạm vi\n1. Luật này quy định mẫu."]}
            first = la.build_folder(documents, articles, [], Path(tmp) / "a", stores)
            second = la.build_folder(documents, articles, [], Path(tmp) / "b", stores)
            self.assertEqual(first["folder_sha256"], second["folder_sha256"])
            self.assertEqual((first["documents"], first["truncated"]), (1, []))
            self.assertTrue((Path(tmp) / "a" / "docs" / "luat-mau-2020.txt").is_file())
            with self.assertRaises(SystemExit):
                la.build_folder(documents, articles, [], Path(tmp) / "a", stores)

    def test_an_article_missing_from_the_body_fails_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            stores = {"t": self.store(Path(tmp), {URL: page(BODY)})}
            documents = [{"url": URL, "doc_id": "01/2020/QH14", "title": "Luật Mẫu 2020", "store": "t", "origin": "mc101"}]
            with self.assertRaises(SystemExit):
                la.build_folder(documents, {URL: ["Điều 9. Không có\nx"]}, [], Path(tmp) / "a", stores)

    def test_a_page_that_differs_from_its_fetch_log_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(Path(tmp), {URL: page(BODY)})
            (store / "raw" / "0.html").write_text(page(BODY + "<p>đổi</p>"), encoding="utf-8")
            documents = [{"url": URL, "doc_id": "01/2020/QH14", "title": "Luật Mẫu 2020", "store": "t", "origin": "mc101"}]
            with self.assertRaises(SystemExit):
                la.build_folder(documents, {}, [], Path(tmp) / "a", {"t": store})


LAW = ("Luật Mẫu 2020\nSố hiệu: 01/2020/QH14\n\nĐiều 1. Phạm vi\n1. Luật này quy định mẫu.\n\nĐiều 2 [3]. Đối tượng\n"
       "Áp dụng.\n\nPHỤ LỤC I\n\nĐiều 1. Quy chế kèm theo\nNội dung.\n")
NOTICE = "Thông báo 1-TB\nSố hiệu: 1-TB\n\n2.1. Về những vấn đề chung:\nNội dung.\n"


class Provisions(unittest.TestCase):
    FILES = [{"file": "luat-mau-2020.txt", "url": URL, "doc_id": "01/2020/QH14 (2020)"},
             {"file": "thong-bao-1.txt", "url": "https://hethongphapluat.com/thong-bao-1.html", "doc_id": "1-TB"}]

    def docs(self, root: Path) -> Path:
        (root / "luat-mau-2020.txt").write_text(LAW, encoding="utf-8")
        (root / "thong-bao-1.txt").write_text(NOTICE, encoding="utf-8")
        return root

    def oracle(self, item: str, source_ref: str, text: str) -> dict:
        return {"dataset_id": "d", "item_id": item, "support": "supports_gold", "label_source": "agent",
                "located_by": "agent-batch-1",
                "provisions": [{"doc_id": "01/2020/QH14", "locator": "Điều 1", "source_ref": source_ref, "text": text}]}

    def test_article_line_finds_numbered_headings_and_annex_articles(self):
        lines = LAW.split("\n")
        self.assertEqual(la.article_line(lines, "1"), "Điều 1. Phạm vi")
        self.assertEqual(la.article_line(lines, "2"), "Điều 2 [3]. Đối tượng")
        self.assertEqual(la.article_line(lines, "1", "PHỤ LỤC I"), "Điều 1. Quy chế kèm theo")
        self.assertIsNone(la.article_line(lines, "1", "PHỤ LỤC II"))

    def test_rows_from_oracle_audit_web_anchors_and_owner_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = self.docs(Path(tmp))
            oracle = [self.oracle("LG-0001", URL, "Điều 1. Phạm vi\n1. Luật này"),
                      self.oracle("LG-0002", "https://other.example/x", "Điều 2 [3]. Đối tượng\nÁp dụng."),
                      {**self.oracle("LG-0009", URL, "x"), "provisions": []}]
            batches = {2: [{"item_id": "LG-0003", "support": "unclear", "provisions": [
                               {"in_folder": True, "file": "luat-mau-2020.txt", "doc_id": "01/2020/QH14",
                                "article": "1", "clauses": ["1"], "part": "PHỤ LỤC I"}]},
                           {"item_id": "LG-0004", "support": "supports_gold", "provisions": [
                               {"in_folder": False, "doc_id": "1-TB", "article": "mục 2.1", "clauses": []}]}]}
            web = {"LG-0004": ("thong-bao-1.txt", "2.1. Về những vấn đề chung:")}
            rows = la.item_provisions(self.FILES, docs, oracle, batches, {"LG-0003": "supports_gold"}, "rev", web)
            by_id = {row["item_id"]: row for row in rows}
            self.assertEqual(list(by_id), ["LG-0001", "LG-0002", "LG-0003", "LG-0004"])
            self.assertEqual(by_id["LG-0002"]["provisions"][0]["file"], "luat-mau-2020.txt")
            self.assertEqual(by_id["LG-0001"]["located_by"], "mc100:agent-batch-1")
            third = by_id["LG-0003"]
            self.assertEqual((third["support"], third["label_source"], third["located_by"]),
                             ("supports_gold", "owner:rev", "mc112:audit-batch-2"))
            self.assertEqual(third["provisions"][0]["anchor_line"], "Điều 1. Quy chế kèm theo")
            self.assertEqual(third["provisions"][0]["locator"], "PHỤ LỤC I kèm theo, Điều 1, 1")
            self.assertEqual(by_id["LG-0004"]["provisions"][0]["anchor_line"], "2.1. Về những vấn đề chung:")
            self.assertEqual(la.check_provisions([{k: r[k] for k in la.PROVISION_KEYS} for r in rows], docs), [])

    def test_an_anchor_that_is_not_a_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = self.docs(Path(tmp))
            with self.assertRaises(SystemExit):
                la.item_provisions(self.FILES, docs, [self.oracle("LG-0001", URL, "Điều 1. Phạm")], {}, {}, "rev")
            batch = {1: [{"item_id": "LG-0004", "support": "unclear", "provisions": [
                {"in_folder": False, "doc_id": "1-TB", "article": "mục 2.1", "clauses": []}]}]}
            with self.assertRaises(SystemExit):
                la.item_provisions(self.FILES, docs, [], batch, {}, "rev", {"LG-0004": ("thong-bao-1.txt", "2.1.")})

    def test_check_flags_a_moved_anchor_and_extra_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = self.docs(Path(tmp))
            row = {"dataset_id": "d", "item_id": "LG-0001", "support": "supports_gold", "label_source": "agent",
                   "located_by": "x", "provisions": [{"file": "luat-mau-2020.txt", "doc_id": "01/2020/QH14",
                                                      "locator": "Điều 3", "anchor_line": "Điều 3. Không có"}]}
            self.assertEqual(len(la.check_provisions([row], docs)), 1)
            self.assertEqual(len(la.check_provisions([{**row, "gold": "A"}], docs)), 1)


READ_RESULT = ("<path>/work/van-ban-phap-luat/luat-mau-2020.txt</path>\n<type>file</type>\n<content>\n4: Điều 1. Phạm vi\n"
               "5: 1. Luật này quy định mẫu.\n6: \n7: Điều 2 [3]. Đối tượng\n\n(Showing lines 4-7 of 8. Use offset=8 to "
               "continue.)\n</content>")
GREP_RESULT = ("Found 3 matches\n\n./luat-mau-2020.txt\nLine 4: Điều 1. Phạm vi\nLine 13: Điều 1. Quy chế kèm theo\n\n"
               "thong-bao-1.txt\nLine 4: 2.1. Về những vấn đề chung:")


def request_body(*messages: dict) -> dict:
    return {"body_received": json.dumps({"model": "m", "messages": list(messages)}, ensure_ascii=False)}


def call(call_id: str, name: str, arguments: dict) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


class Trajectory(unittest.TestCase):
    def test_paths_resolve_inside_the_working_directory_only(self):
        self.assertEqual(la.corpus_file("luat-mau-2020.txt"), "luat-mau-2020.txt")
        self.assertEqual(la.corpus_file("./luat-mau-2020.txt"), "luat-mau-2020.txt")
        self.assertEqual(la.corpus_file("/work/van-ban-phap-luat/luat-mau-2020.txt"), "luat-mau-2020.txt")
        for outside in ("/spill/x-grep.txt", "../luat-mau-2020.txt", "sub/luat-mau-2020.txt", "a.md"):
            self.assertIsNone(la.corpus_file(outside))

    def test_read_and_grep_results_in_dsh_format(self):
        path, lines = la.parse_read(READ_RESULT)
        self.assertEqual(path, "/work/van-ban-phap-luat/luat-mau-2020.txt")
        self.assertEqual(lines, ["Điều 1. Phạm vi", "1. Luật này quy định mẫu.", "", "Điều 2 [3]. Đối tượng"])
        self.assertEqual(la.parse_grep(GREP_RESULT), {
            "./luat-mau-2020.txt": ["Điều 1. Phạm vi", "Điều 1. Quy chế kèm theo"],
            "thong-bao-1.txt": ["2.1. Về những vấn đề chung:"]})
        self.assertEqual(la.parse_grep("No matches found"), {})

    def test_observations_come_from_what_reached_the_model(self):
        first = request_body({"role": "user", "content": "q"}, call("c1", "grep", {"pattern": "Điều 1"}),
                             {"role": "tool", "tool_call_id": "c1", "content": GREP_RESULT})
        # a later request after compaction no longer carries c1, and c2's result is an error
        second = request_body({"role": "user", "content": "summary"}, call("c2", "read", {"file_path": "x"}),
                              {"role": "tool", "tool_call_id": "c2", "content": "Error: cannot read x: not found"},
                              call("c3", "read", {"file_path": "luat-mau-2020.txt"}),
                              {"role": "tool", "tool_call_id": "c3", "content": READ_RESULT},
                              call("c4", "glob", {"pattern": "*"}))  # c4's result never reached the model
        observations = la.model_observations([first, second])
        self.assertEqual([(o["tool"], o["status"]) for o in observations],
                         [("grep", "completed"), ("read", "error"), ("read", "completed")])
        self.assertEqual(observations[0]["lines"]["luat-mau-2020.txt"], ["Điều 1. Phạm vi", "Điều 1. Quy chế kèm theo"])
        self.assertEqual(observations[2]["read_file"], "luat-mau-2020.txt")

    def test_hit_levels(self):
        grep_only = la.model_observations([request_body(call("c1", "grep", {"pattern": "x"}),
                                                        {"role": "tool", "tool_call_id": "c1", "content": GREP_RESULT})])
        provisions = [{"file": "luat-mau-2020.txt", "anchor_line": "Điều 1. Quy chế kèm theo"},
                      {"file": "luat-mau-2020.txt", "anchor_line": "Điều 2 [3]. Đối tượng"},
                      {"file": "khac.txt", "anchor_line": "Điều 1. Phạm vi"}]
        self.assertEqual(la.provision_hits(grep_only, provisions), [
            {"seen": True, "read": False, "opened": False}, {"seen": False, "read": False, "opened": False},
            {"seen": False, "read": False, "opened": False}])
        read = la.model_observations([request_body(call("c1", "read", {"file_path": "luat-mau-2020.txt"}),
                                                   {"role": "tool", "tool_call_id": "c1", "content": READ_RESULT})])
        self.assertEqual(la.provision_hits(read, provisions)[:2], [
            {"seen": False, "read": False, "opened": True}, {"seen": True, "read": True, "opened": True}])

    def test_a_spilled_grep_result_read_back_counts_as_seen_only(self):
        spill = ("<path>/spill/s/abc-grep.txt</path>\n<type>file</type>\n<content>\n1: Found 1 match\n2: \n"
                 "3: luat-mau-2020.txt\n4: Line 7: Điều 2 [3]. Đối tượng\n\n(End of file - total 4 lines)\n</content>")
        observations = la.model_observations([request_body(call("c1", "read", {"file_path": "/spill/x"}),
                                                           {"role": "tool", "tool_call_id": "c1", "content": spill})])
        hits = la.provision_hits(observations, [{"file": "luat-mau-2020.txt", "anchor_line": "Điều 2 [3]. Đối tượng"}])
        self.assertEqual(hits, [{"seen": True, "read": False, "opened": False}])


@unittest.skipUnless((la.ROOT / la.load_protocol()["reference"]["scores"]).is_file(), "MC-111's scores are local only")
class Manifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.rebuilt = la.build_manifest()

    def test_536_attempts_item_major_and_deterministic(self):
        self.assertEqual((self.manifest["n"], self.manifest["arm_counts"]), (536, {"DSH": 268, "DSHF": 268}))
        self.assertEqual([row["replicate_id"] for row in self.manifest["items"][:4]],
                         ["DSH-r1", "DSHF-r1", "DSH-r2", "DSHF-r2"])
        self.assertEqual(la.build_manifest()[0], self.manifest)

    def test_task_is_the_instruction_then_the_frozen_prompt(self):
        prompts = la.load_prompts()
        frozen = la.lo.legal_items()
        for item in self.rebuilt.values():
            arm = item.replicate_id.split("-r")[0]
            self.assertEqual(item.prompt, prompts[arm] + "\n\n" + frozen[item.item_id].prompt)
            self.assertTrue(item.prompt.endswith("Đáp án: "))
            self.assertNotIn(item.gold_answer + ".", item.prompt.split("\n")[-1])
        for arm in la.ARMS:
            for word in ("Điều", "Luật", "Nghị định", "Thông tư"):
                self.assertNotIn(word, prompts[arm])


if __name__ == "__main__":
    unittest.main()
