"""MC-112 (planned): the legal corpus folder that Qwen searches inside DeepSeek Harness (dsh).

dsh gives the model `glob`, `grep` and `read` over a working directory. This module writes that directory: one
plain-text file per document, holding the document's whole text as its stored hethongphapluat.com page shows it
(preamble, chapters, articles, signature, annexes, footnotes), not only its articles.

File layout, one document per file:

    <title>
    Số hiệu: <document number>

    <the page's document body, one line per paragraph>

* The file name is the page slug plus `.txt`: ASCII and unique per page.
* The body is the page's `div#tab_noi_dung_vb`. Two things in it are not the document and are removed: the site's
  `model_prompt` span, which tells AI readers to cite the site, and the paywall notice, at which the body is cut
  (the file is then flagged `truncated`). The build fails if site text is left.
* A blank line goes before each heading line (Điều, Chương, Mục, Phần, Phụ lục). Text is NFC.
* Nothing else is added: no role, no item list, no source URL.

Documents: MC-101's 303 (`corpus_sources_v1.json`) plus `data/diagnostic_legal_agent/added_documents_v1.json`.
`offsite_documents_v1.json` replaces the body of a page whose passage hethongphapluat.com withholds, or adds a
document it lacks, with a full text from another site (DOCX, PDF text layer, or a luatvietnam.vn page).
Checks: each of MC-101's articles for a page is in its file whole, with its heading as a line of its own; no
question stem or answer-key line is in the folder (MC-101's leak check).

Provisions (`item_provisions_v1.jsonl`): for each of the 134 items, the provisions that govern it, each as a file of
the folder and an anchor line (the passage's first line, a whole line of that file), so a trajectory can be checked
for whether the model read them. No gold letter is in it. Sources: MC-100's oracle evidence for 53 items, the
gold-aware coverage audit (four agent batches) for the other 81, and the owner's spot-check of 14 of those 81.

    python -m code_benchmark.diagnostic_legal_agent folder --out <dir>
    python -m code_benchmark.diagnostic_legal_agent provisions --folder <dir>
"""
from __future__ import annotations

import dataclasses
import html
import io
import json
import posixpath
import re
import shutil
import subprocess  # nosec B404 — pdftotext only, on a stored file whose SHA-256 was checked
import tempfile
import unicodedata
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # pragma: no cover - run from code_benchmark/
    import diagnostic_legal_oracle as lo  # type: ignore[no-redef]
    import diagnostic_legal_retrieval as lr  # type: ignore[no-redef]
    import diagnostic_retrieval as dr  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_agent"
MC101_SOURCES = ROOT / "data" / "diagnostic_legal_retrieval" / "corpus_sources_v1.json"
MC101_SOURCES_SHA256 = "852286d55e97cd9d5c8226665e7cebfe52607fd8f36a6e76dbd4dd2556479737"
MC101_UNITS = lr.CORPUS_DIR / "corpus.jsonl"
MC101_CORPUS_SHA256 = "66e4a349320420afb83aa6e3af71c478c0f89cd38b063aa46185386074af678a"
ADDED_PATH = ROOT / "data" / "diagnostic_legal_agent" / "added_documents_v1.json"
OFFSITE_PATH = ROOT / "data" / "diagnostic_legal_agent" / "offsite_documents_v1.json"
STORES = {"mc101": lr.CORPUS_DIR, "mc100": lo.SOURCES_DIR, "mc112": WORK_ROOT / "sources",
          "offsite": WORK_ROOT / "offsite"}
SITE = "https://hethongphapluat.com/"
PAYWALL = "ĐÂY LÀ NỘI DUNG CÓ THU PHÍ"

_BODY_OPEN = re.compile(r"<div\b[^>]*\bid=[\"']tab_noi_dung_vb[\"'][^>]*>", re.IGNORECASE)
_DIV = re.compile(r"<(/?)div\b[^>]*>", re.IGNORECASE)
_MODEL_PROMPT = re.compile(r"<(\w+)\b[^>]*\bclass=[\"'][^\"']*model_prompt[^\"']*[\"'][^>]*>.*?</\1\s*>",
                           re.IGNORECASE | re.DOTALL)
_SITE_TEXT = re.compile(r"hethongphapluat|model_prompt", re.IGNORECASE)
_DIEU_EDGE = re.compile(r"</?dieu\b[^>]*>", re.IGNORECASE)
_HEADING = re.compile(r"^(?:Điều\s+\d+[a-zđ]?\s*(?:\[\d+\])?\s*[.:]|(?:Chương|CHƯƠNG)\s+[IVXLC\d]+\b|(?:Mục|MỤC)\s+\d+\b"
                      r"|(?:Phần|PHẦN)\s+(?:[IVXLC]+\b|thứ\b|THỨ\b)|(?:DANH MỤC\s+)?PHỤ LỤC\b)")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def file_name(url: str) -> str:
    if not url.startswith(SITE) or not url.endswith(".html"):
        raise _fail(f"not a hethongphapluat.com page: {url!r}")
    slug = url.removeprefix(SITE).removesuffix(".html")
    if not slug or "/" in slug or not slug.isascii() or len(slug.encode()) > 250:
        raise _fail(f"cannot name a file after {url!r}")
    return slug + ".txt"


def plain_number(doc_id: str) -> str:
    """The printed document number: MC-101 qualifies clashing consolidated numbers by year ("09/VBHN-VPQH (2022)");
    the page title already carries the year, so the file prints the number as issued."""
    head, _, tail = doc_id.rpartition(" (")
    return head if head and tail.rstrip(")").isdigit() else doc_id


# ---------------------------------------------------------------- page body

def page_body(page: str) -> tuple[str, bool]:
    """(text, truncated): the document body of a stored page, without the site's model_prompt span and cut at the
    paywall notice when there is one."""
    page = dr._NON_CONTENT.sub("", page)  # noqa: SLF001 - same package, same page reading
    opening = _BODY_OPEN.search(page)
    if not opening:
        raise _fail("the page has no div#tab_noi_dung_vb")
    depth, end = 0, None
    for tag in _DIV.finditer(page, opening.start()):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            end = tag.start()
            break
    if end is None:
        raise _fail("div#tab_noi_dung_vb never closes")
    inner = _MODEL_PROMPT.sub("", page[opening.end():end])
    # Cut at article tags before parsing, as MC-101's reader does: a broken attribute on the page (13/VBHN-VPQH 2023
    # opens `title='` before the end of Điều 47) then damages one article instead of swallowing the next heading.
    pieces = (dr.html_to_text(piece) for piece in _DIEU_EDGE.split(inner))
    text = "\n".join(piece for piece in pieces if piece)
    truncated = PAYWALL in text
    if truncated:
        text = text[:text.index(PAYWALL)].rstrip()
    left = _SITE_TEXT.search(text)
    if left:
        raise _fail(f"site text left in the body: {left.group(0)!r}")
    if not text:
        raise _fail("the page body is empty")
    return text, truncated


# ---------------------------------------------------------------- off-site texts

_W_PARA = re.compile(r"<w:p\b[^>]*/>|<w:p\b[^>]*>.*?</w:p>", re.DOTALL)
_W_TABLE = re.compile(r"<w:tbl>.*?</w:tbl>", re.DOTALL)
_W_ROW = re.compile(r"<w:tr\b[^>]*>.*?</w:tr>", re.DOTALL)
_W_CELL = re.compile(r"<w:tc\b[^>]*>.*?</w:tc>", re.DOTALL)
_W_RUN = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:tab/>|<w:br\b[^>]*/>|<w:cr/>", re.DOTALL)
_LV_UI = frozenset({"Đang theo dõi"})
_LV_TAIL = "Phụ lục đính kèm"
_PDF_ITEM = re.compile(r"^(?:Điều\s+\d+|Chương\s+[IVXLC]+|Mục\s+\d+|\d+(?:\.\d+)*\.\s|[a-zđ]\)\s|[-+–•]\s|Căn cứ\b)")


def _pdf_block_line(line: str) -> bool:
    """A line that stands alone: a structural item, or a heading in capitals."""
    return bool(_PDF_ITEM.match(line)) or line.isupper()


def _clean_lines(text: str) -> str:
    text = nfc(text).replace("\xa0", " ").replace(chr(0x200E), "").replace(chr(0x200F), "")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def docx_body(raw: bytes) -> str:
    """Paragraph and table text of a DOCX in document order, read with regular expressions (no XML parser on
    downloaded input). A table row is one line, its cells joined by " | "."""
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode("utf-8")

    def paragraph(fragment: str) -> str:
        return "".join(html.unescape(run.group(1)) if run.group(1) is not None
                       else ("\n" if run.group(0).startswith(("<w:br", "<w:cr")) else " ")
                       for run in _W_RUN.finditer(fragment))

    lines, position = [], 0
    for table in _W_TABLE.finditer(xml):
        lines += [paragraph(p.group(0)) for p in _W_PARA.finditer(xml, position, table.start())]
        for row in _W_ROW.finditer(table.group(0)):
            cells = [" ".join(paragraph(p.group(0)) for p in _W_PARA.finditer(cell.group(0))).strip()
                     for cell in _W_CELL.finditer(row.group(0))]
            lines.append(" | ".join(cell for cell in cells if cell))
        position = table.end()
    lines += [paragraph(p.group(0)) for p in _W_PARA.finditer(xml, position)]
    return _clean_lines("\n".join(lines))


def pdf_body(raw: bytes) -> str:
    """The text layer of a PDF (pdftotext), with lines that the page width broke mid-sentence joined back."""
    tool = shutil.which("pdftotext")
    if not tool:
        raise _fail("pdftotext is not installed")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(raw)
        handle.flush()
        out = subprocess.run([tool, "-enc", "UTF-8", handle.name, "-"], capture_output=True,  # nosec B603
                             check=True).stdout.decode("utf-8")
    return reflow_pdf_lines(_clean_lines(out.replace("\f", "\n")).split("\n"))


def reflow_pdf_lines(lines: list[str]) -> str:
    """Drop bare page numbers and join a line to the one before when the page width, not the text, broke it: the
    line before does not end a sentence or clause, is not a heading in capitals or an article heading, and the
    line itself does not open a structural item."""
    lines = [line for line in lines if not re.fullmatch(r"\d{1,3}", line)]
    joined: list[str] = []
    for line in lines:
        if joined and not joined[-1].endswith((".", ":", ";", "?", "!")) and not _pdf_block_line(line) \
                and not joined[-1].isupper() and not re.match(r"Điều\s+\d+", joined[-1]):
            joined[-1] += " " + line
        else:
            joined.append(line)
    return "\n".join(joined)


def luatvietnam_body(raw: bytes) -> str:
    """The document of a luatvietnam.vn page (`div.the-document-body`), without the site's follow buttons and its
    closing download note."""
    page = dr._NON_CONTENT.sub("", raw.decode("utf-8"))  # noqa: SLF001
    opening = re.search(r"<div\b[^>]*\bclass=[\"']the-document-body[\"'][^>]*>", page)
    if not opening:
        raise _fail("the luatvietnam.vn page has no div.the-document-body")
    depth = 0
    for tag in _DIV.finditer(page, opening.start()):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            lines = [line for line in dr.html_to_text(page[opening.end():tag.start()]).split("\n") if line not in _LV_UI]
            if _LV_TAIL in lines:
                lines = lines[:len(lines) - lines[::-1].index(_LV_TAIL) - 1]
            return _clean_lines("\n".join(lines))
    raise _fail("div.the-document-body never closes")


OFFSITE_READERS = {"docx": docx_body, "pdf": pdf_body, "luatvietnam-html": luatvietnam_body}
_OFFSITE_SITE_TEXT = re.compile(r"luatvietnam|thuvienphapluat|Đang theo dõi|Tải về để xem", re.IGNORECASE)


def stored_bytes(url: str, store: Path) -> bytes:
    """A stored off-site file, checked against the SHA-256 of its fetch-log entry."""
    entries = [json.loads(line) for line in (store / "fetch_log.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    entries = [entry for entry in entries if entry["url"] == url]
    if len(entries) != 1:
        raise _fail(f"{len(entries)} fetch-log entries for {url}, not one")
    return _read_verified(store / "raw" / entries[0]["file"], entries[0]["sha256"], "stored file")


def offsite_body(document: dict[str, Any], stores: dict[str, Path]) -> str:
    text = OFFSITE_READERS[document["reader"]](stored_bytes(document["source_url"], stores["offsite"]))
    left = _OFFSITE_SITE_TEXT.search(text)
    if left:
        raise _fail(f"{document['source_url']}: site text left in the body: {left.group(0)!r}")
    if not text:
        raise _fail(f"{document['source_url']}: empty text")
    return text


def layout(body: str) -> str:
    """One line per paragraph, a blank line before each heading line."""
    out: list[str] = []
    for line in body.split("\n"):
        if _HEADING.match(line) and out:
            out.append("")
        out.append(line)
    return "\n".join(out)


def file_text(title: str, doc_id: str, body: str) -> str:
    return nfc(f"{title}\nSố hiệu: {plain_number(doc_id)}\n\n{layout(body)}\n")


# ---------------------------------------------------------------- MC-101 articles, for the containment check

def _unit_key(unit: dict[str, Any]) -> tuple[str, str, int]:
    """(kind, number, part index) from a chunk id such as `X#dieu-12`, `X#dieu-12-p2` or `X#kem-dieu-4`."""
    key = unit["chunk_id"].split("#", 1)[1]
    base, _, part = key.rpartition("-p")
    if base and part.isdigit():
        key, index = base, int(part)
    else:
        index = 1
    kind, _, number = key.rpartition("-")
    return kind, number, index


def joined_articles(units: list[dict[str, Any]]) -> list[str]:
    """MC-101's articles of one page, the parts of a split article joined back whole."""
    articles: list[tuple[str, str, list[str]]] = []
    for unit in units:
        kind, number, index = _unit_key(unit)
        if index == 1:
            articles.append((kind, number, [unit["text"]]))
        elif articles and articles[-1][:2] == (kind, number) and len(articles[-1][2]) == index - 1:
            articles[-1][2].append(unit["text"])
        else:
            raise _fail(f"{unit['chunk_id']}: part {index} is out of order")
    texts = []
    for kind, number, parts in articles:
        head, text = parts[0].split("\n", 1)[0], parts[0]
        for later in parts[1:]:
            first, _, rest = later.partition("\n")
            if first != head:
                raise _fail(f"{kind}-{number}: a later part does not repeat the heading")
            text += "\n" + rest
        texts.append(text)
    return texts


def missing_articles(text: str, articles: list[str]) -> list[str]:
    """Heading lines of the articles that are not in `text` whole, or whose heading is not a line of its own."""
    lines, squashed = set(text.split("\n")), _squash(text)
    return [article.split("\n", 1)[0] for article in articles
            if article.split("\n", 1)[0] not in lines or _squash(article) not in squashed]


# ---------------------------------------------------------------- documents and folder

def _read_verified(path: Path, sha256: str, label: str) -> bytes:
    raw = path.read_bytes()
    if v1.sha256_bytes(raw) != sha256:
        raise _fail(f"{label} {path} is not the registered file")
    return raw


def load_documents(added_path: Path = ADDED_PATH, offsite_path: Path | None = OFFSITE_PATH) -> list[dict[str, Any]]:
    """MC-101's documents (store mc101), the added pages, and the off-site texts: one entry per file."""
    sources = json.loads(_read_verified(MC101_SOURCES, MC101_SOURCES_SHA256, "MC-101 source list"))
    documents = [{"url": d["url"], "doc_id": d["doc_id"], "title": d["title"], "store": "mc101", "origin": "mc101"}
                 for d in sources["documents"]]
    added = json.loads(added_path.read_text(encoding="utf-8"))
    for d in added["documents"]:
        if d["store"] not in STORES or d["store"] == "mc101":
            raise _fail(f"{d['url']}: unknown store {d['store']!r}")
        documents.append({"url": d["url"], "doc_id": d["doc_id"], "title": d["title"], "store": d["store"],
                          "origin": "added", "items": d["items"]})
    urls = [d["url"] for d in documents]
    if len(set(urls)) != len(urls):
        raise _fail("a page is listed twice")
    if offsite_path is None:
        return documents
    by_url = {d["url"]: d for d in documents}
    for entry in json.loads(offsite_path.read_text(encoding="utf-8"))["documents"]:
        if entry["reader"] not in OFFSITE_READERS:
            raise _fail(f"{entry['source_url']}: unknown reader {entry['reader']!r}")
        if entry.get("replaces_url"):
            if entry["replaces_url"] not in by_url or "reader" in by_url[entry["replaces_url"]]:
                raise _fail(f"{entry['replaces_url']}: not a listed page, or replaced twice")
            by_url[entry["replaces_url"]].update(reader=entry["reader"], source_url=entry["source_url"],
                                                 store="offsite", origin=by_url[entry["replaces_url"]]["origin"] + "+offsite")
        else:
            documents.append({"url": entry["source_url"], "file": entry["file"], "doc_id": entry["doc_id"],
                              "title": entry["title"], "reader": entry["reader"], "source_url": entry["source_url"],
                              "store": "offsite", "origin": "offsite", "items": entry["items"]})
    return documents


def load_mc101_articles() -> dict[str, list[str]]:
    raw = _read_verified(MC101_UNITS, MC101_CORPUS_SHA256, "MC-101 corpus")
    by_url: dict[str, list[dict[str, Any]]] = {}
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            unit = json.loads(line)
            by_url.setdefault(unit["source_ref"], []).append(unit)
    return {url: joined_articles(units) for url, units in by_url.items()}


def build_folder(documents: list[dict[str, Any]], articles: dict[str, list[str]], items: list[v1.EvalItem],
                 out_dir: Path, stores: dict[str, Path] = STORES) -> dict[str, Any]:
    """Write `out_dir/docs/` once and return the folder manifest. Fails closed on a missing article, site text
    or a leak."""
    docs_dir = out_dir / "docs"
    if docs_dir.exists():
        raise _fail(f"{docs_dir} exists; a corpus folder is written once")
    names = {d["url"]: d.get("file") or file_name(d["url"]) for d in documents}
    if len(set(names.values())) != len(names) or not all(re.fullmatch(r"[a-z0-9-]+\.txt", n) for n in names.values()):
        raise _fail("two documents map to one file name, or a file name is not a lower-case ASCII slug")
    texts, files = {}, []
    for document in documents:
        if "reader" in document:
            body, truncated = offsite_body(document, stores), False
        else:
            body, truncated = page_body(lo.stored_page(document["url"], stores[document["store"]]))
        text = file_text(document["title"], document["doc_id"], body)
        missing = missing_articles(text, [nfc(a) for a in articles.get(document["url"], [])])
        if missing:
            raise _fail(f"{document['doc_id']}: MC-101 articles missing from the file: {missing[:3]}")
        texts[names[document["url"]]] = text
        files.append({"file": names[document["url"]], "url": document["url"], "doc_id": document["doc_id"],
                      "title": document["title"], "origin": document["origin"], "store": document["store"],
                      "source_url": document.get("source_url", document["url"]), "truncated": truncated,
                      "chars": len(text),
                      "article_lines": sum(1 for line in text.split("\n") if line.startswith("Điều ")),
                      "sha256": v1.sha256_bytes(text.encode("utf-8"))})
    leak = dr.leak_report([{"chunk_id": name, "text": text} for name, text in texts.items()], items)
    if not leak["passed"]:
        raise _fail(f"the leak check failed: {leak['questions_in_corpus'][:5]} {leak['answer_key_chunks'][:5]}")
    docs_dir.mkdir(parents=True)
    for name, text in texts.items():
        (docs_dir / name).write_text(text, encoding="utf-8")
    files.sort(key=lambda row: row["file"])
    listing = "".join(f"{row['sha256']}  {row['file']}\n" for row in files).encode("utf-8")
    return {"documents": len(files), "added": sum(row["origin"] == "added" for row in files),
            "truncated": [row["file"] for row in files if row["truncated"]],
            "chars": sum(row["chars"] for row in files), "folder_sha256": v1.sha256_bytes(listing),
            "leak": leak, "files": files}


# ---------------------------------------------------------------- trajectories (what the model saw)
# dsh's `--json` events carry only a short preview of each tool result; the model receives the full text. Hits are
# therefore read from the tool messages of the request bodies the proxy recorded: what reached the model's context.

WORKDIR = "/work/van-ban-phap-luat"
_READ_PATH = re.compile(r"^<path>(?P<path>.*?)</path>", re.DOTALL)
_READ_LINE = re.compile(r"^(?P<n>\d+): ?(?P<text>.*)$")
_GREP_LINE = re.compile(r"^Line (?P<n>\d+): ?(?P<text>.*)$")
_GREP_NOTE = re.compile(r"^(?:Found \d+|No matches|\(|Error:)")


def corpus_file(path: str) -> str | None:
    """The corpus file a tool path names (relative paths resolve against the working directory), or None."""
    full = posixpath.normpath(path if path.startswith("/") else posixpath.join(WORKDIR, path))
    parent, name = posixpath.split(full)
    return name if parent == WORKDIR and name.endswith(".txt") else None


def parse_read(content: str) -> tuple[str | None, list[str]]:
    """(path, lines) of a `read` result: `<path>…</path>`, then `<content>` with `N: text` lines."""
    match = _READ_PATH.match(content)
    body = content.split("<content>\n", 1)[1] if "<content>\n" in content else ""
    lines = [m.group("text") for m in map(_READ_LINE.match, body.split("\n")) if m]
    return (match.group("path") if match else None), lines


def parse_grep(content: str) -> dict[str, list[str]]:
    """{file: matched lines} of a `grep` result: a file line, then `Line N: text` lines, blocks split by blanks."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in content.split("\n"):
        hit = _GREP_LINE.match(line)
        if hit and current is not None:
            out.setdefault(current, []).append(hit.group("text"))
        elif line.strip() and not hit and not _GREP_NOTE.match(line):
            current = line.strip()
    return out


def model_observations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool call whose result reached the model, in call order: tool, arguments, result status and the corpus
    lines it showed ({file: [lines]}). Collected over all recorded request bodies, so a result later compacted away
    still counts once it was sent."""
    calls: dict[str, dict[str, Any]] = {}
    results: dict[str, str] = {}
    order: list[str] = []
    for record in records:
        try:
            body = json.loads(record.get("body_received") or "")
        except json.JSONDecodeError:
            continue
        for message in body.get("messages") or [] if isinstance(body, dict) else []:
            if message.get("role") == "assistant":
                for call in message.get("tool_calls") or []:
                    if call.get("id") and call["id"] not in calls:
                        function = call.get("function") or {}
                        try:
                            arguments = json.loads(function.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            arguments = {"_unparsed": function.get("arguments")}
                        calls[call["id"]] = {"tool": function.get("name"), "arguments": arguments}
                        order.append(call["id"])
            elif message.get("role") == "tool" and message.get("tool_call_id") not in results:
                content = message.get("content")
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                results[str(message.get("tool_call_id"))] = str(content or "")
    out = []
    for call_id in order:
        if call_id not in results:
            continue
        call, content = calls[call_id], results[call_id]
        lines: dict[str, list[str]] = {}
        read_file = None
        if content.startswith("Error:"):
            status = "error"
        else:
            status = "completed"
            if call["tool"] == "read":
                path, shown = parse_read(content)
                read_file = corpus_file(path) if path else None
                if read_file:
                    lines[read_file] = shown
                elif shown:  # a spilled grep result read back: its lines are grep output
                    for name, matched in parse_grep("\n".join(shown)).items():
                        if corpus_file(name):
                            lines.setdefault(str(corpus_file(name)), []).extend(matched)
            elif call["tool"] == "grep":
                for name, matched in parse_grep(content).items():
                    if corpus_file(name):
                        lines.setdefault(str(corpus_file(name)), []).extend(matched)
        out.append({"call_id": call_id, "tool": call["tool"], "arguments": call["arguments"], "status": status,
                    "read_file": read_file, "lines": lines, "chars": len(content)})
    return out


def provision_hits(observations: list[dict[str, Any]], provisions: list[dict[str, Any]]) -> list[dict[str, bool]]:
    """Per provision: `seen` (a grep or read result from its file showed the anchor line), `read` (a read result
    from its file did) and `opened` (its file was read at all)."""
    out = []
    for p in provisions:
        seen = any(p["anchor_line"] in o["lines"].get(p["file"], []) for o in observations)
        read = any(o["tool"] == "read" and o["read_file"] == p["file"] and p["anchor_line"] in o["lines"][p["file"]]
                   for o in observations)
        opened = any(o["tool"] == "read" and o["read_file"] == p["file"] for o in observations)
        out.append({"seen": seen, "read": read, "opened": opened})
    return out


REVIEW_SALT = "legal-agent-review|"


def review_sample(item_ids: list[str], size: int = 14) -> list[str]:
    """The owner's spot-check of the audit: the first `size` items in SHA-256 order of REVIEW_SALT + item id (MC-100's
    rule with its own salt), returned in item-id order."""
    return sorted(sorted(item_ids, key=lambda item: v1.sha256_bytes(f"{REVIEW_SALT}{item}".encode("utf-8")))[:size])


PROVISIONS_PATH = ROOT / "data" / "diagnostic_legal_agent" / "item_provisions_v1.jsonl"
AUDIT_DIR = WORK_ROOT / "audit"
PROVISION_KEYS = ("dataset_id", "item_id", "support", "label_source", "located_by", "provisions")
_ARTICLE_ANCHOR = re.compile(r"Điều (\d+[a-zđ]?)")
_LG0012 = ("nghi-dinh-151-2025-nd-cp-quy-dinh-ve-phan-dinh-tham-quyen-cua-chinh-quyen-dia-phuong-02-cap-phan-quyen-"
           "phan-cap-trong-linh-vuc-dat-dai.txt",
           "IV. Trình tự, thủ tục thẩm định, phê duyệt quy hoạch sử dụng đất cấp xã/điều chỉnh quy hoạch sử dụng đất "
           "cấp xã")
# Provisions the coverage audit found outside MC-101's folder (or in a part of a page MC-101 did not keep): item ->
# (file, where the passage starts). `Điều N` means that article's heading line; anything else is a whole line.
WEB_ANCHORS: dict[str, tuple[str, str]] = {
    "LG-0007": ("thong-bao-176-tb-vptw-d577f96e495efdd882b29061fab7657f.txt", "2.1. Về những vấn đề chung:"),
    "LG-0012": _LG0012,
    "LG-0013": ("nghi-dinh-68-2025-nd-cp-sua-doi-nghi-dinh-118-2021-nd-cp-huong-dan-luat-xu-ly-vi-pham-hanh-chinh.txt",
                "Điều 1"),
    "LG-0042": ("quyet-dinh-982-qd-ubtdtt-nam-2007-ban-hanh-luat-bong-da-do-bo-truong-chu-nhiem-uy-ban-the-duc-the-"
                "thao-ban-hanh.txt", "LUẬT V. TRỌNG TÀI"),
    "LG-0050": _LG0012,
    "LG-0070": ("du-thao-nghi-dinh-quy-dinh-che-do-phu-cap-uu-dai-theo-nghe-doi-voi-vien-chuc-nguoi-lao-dong-cong-tac-"
                "trong-cac-co-so-giao-duc-cong-lap-2025.txt", "Điều 5"),
    "LG-0095": _LG0012,
    "LG-0096": ("quyet-dinh-04-qd-chq-nam-2025-quy-dinh-chuc-nang-nhiem-vu-quyen-han-va-co-cau-to-chuc-cua-ban-quan-"
                "ly-rui-ro-thuoc-cuc-hai-quan.txt", "Điều 2"),
    "LG-0107": ("quy-chuan-ky-thuat-quoc-gia-qcvn-113-2024-bgtvt-ve-yeu-cau-ky-thuat-va-phuong-phap-thu-vanh-banh-xe-"
                "mo-to-xe-gan-may.txt", "2.3.1. Khả năng chịu tải trọng hướng kính"),
    "LG-0130": ("thong-tu-68-2025-tt-btc-ve-bieu-mau-su-dung-trong-dang-ky-doanh-nghiep-dang-ky-ho-kinh-doanh-do-bo-"
                "truong-bo-tai-chinh-ban-hanh.txt", "Mẫu số 14"),
}


def article_line(lines: Sequence[str], article: str, part: str | None = None) -> str | None:
    """The first heading line of `Điều <article>`, after the line `part` when one is given (an annex's articles)."""
    if part:
        if part not in lines:
            return None
        lines = lines[lines.index(part) + 1:]
    pattern = re.compile(rf"^Điều {re.escape(article)}(\s*\[\d+\])?\s*[.:]")
    return next((line for line in lines if pattern.match(line)), None)


def item_provisions(files: list[dict[str, Any]], docs_dir: Path, oracle_rows: list[dict[str, Any]],
                    batches: dict[int, list[dict[str, Any]]], owner_labels: dict[str, str], reviewer: str,
                    web_anchors: dict[str, tuple[str, str]] = WEB_ANCHORS) -> list[dict[str, Any]]:
    """Each item's governing provisions as (file, anchor line) in the corpus folder, for the trajectory check of
    whether the model read them. MC-100's oracle rows come first; the coverage audit's batches cover the rest. The
    owner's spot-check labels replace the agent's. Fails closed when an anchor is not a whole line of its file."""
    by_url = {row["url"]: row["file"] for row in files}
    by_doc: dict[str, list[str]] = {}
    for row in files:
        by_doc.setdefault(row["doc_id"].split(" (")[0], []).append(row["file"])
    cache: dict[str, list[str]] = {}

    def lines(name: str) -> list[str]:
        if name not in cache:
            cache[name] = (docs_dir / name).read_text(encoding="utf-8").split("\n")
        return cache[name]

    out: list[dict[str, Any]] = []
    errors: list[tuple[str, str, str]] = []
    for row in oracle_rows:
        if not row["provisions"]:
            continue
        provisions = []
        for p in row["provisions"]:
            candidates = [by_url[p["source_ref"]]] if p["source_ref"] in by_url else by_doc.get(p["doc_id"], [])
            head = p["text"].split("\n", 1)[0]
            found = [name for name in candidates if head in lines(name)]
            if not found:
                errors.append((row["item_id"], p["doc_id"], p["locator"]))
                continue
            provisions.append({"file": found[0], "doc_id": p["doc_id"], "locator": p["locator"], "anchor_line": head})
        out.append({"dataset_id": row["dataset_id"], "item_id": row["item_id"], "support": row["support"],
                    "label_source": row["label_source"], "located_by": f"mc100:{row['located_by']}",
                    "provisions": provisions})
    for number, items in sorted(batches.items()):
        for x in items:
            provisions = []
            for p in x["provisions"]:
                article = str(p.get("article") or "")
                locator = f"Điều {article}" if re.fullmatch(r"\d+[a-zđ]?", article) else article
                locator = ", ".join(part for part in [locator, *map(str, p.get("clauses") or [])] if part)
                if p.get("in_folder"):
                    name, anchor = p["file"], article_line(lines(p["file"]), article, p.get("part"))
                    if p.get("part"):
                        locator = f"{p['part']} kèm theo, {locator}"
                else:
                    name, anchor = web_anchors[x["item_id"]]
                    match = _ARTICLE_ANCHOR.fullmatch(anchor)
                    anchor = article_line(lines(name), match.group(1)) if match else anchor
                if not anchor or anchor not in lines(name):
                    errors.append((x["item_id"], name, str(anchor)))
                    continue
                provisions.append({"file": name, "doc_id": p["doc_id"], "locator": locator, "anchor_line": anchor})
            owner = owner_labels.get(x["item_id"])
            out.append({"dataset_id": lo.DATASET, "item_id": x["item_id"], "support": owner or x["support"],
                        "label_source": f"owner:{reviewer}" if owner else "agent",
                        "located_by": f"mc112:audit-batch-{number}", "provisions": provisions})
    ids = [row["item_id"] for row in out]
    if errors or len(set(ids)) != len(ids) or not all(row["provisions"] for row in out):
        raise _fail(f"provisions: {len(errors)} anchors not found {errors[:3]}, {len(ids) - len(set(ids))} items "
                    f"twice, {sum(not row['provisions'] for row in out)} items without a provision")
    return sorted(out, key=lambda row: row["item_id"])


def check_provisions(rows: list[dict[str, Any]], docs_dir: Path) -> list[str]:
    """Problems with a provisions file against a corpus folder: a key set that differs, or an anchor that is not a
    whole line of its file. An empty list means the file can be used."""
    problems, cache = [], {}
    for row in rows:
        if tuple(row) != PROVISION_KEYS:
            problems.append(f"{row.get('item_id')}: keys {tuple(row)}")
            continue
        for p in row["provisions"]:
            path = docs_dir / p["file"]
            if p["file"] not in cache:
                cache[p["file"]] = set(path.read_text(encoding="utf-8").split("\n")) if path.is_file() else set()
            if p["anchor_line"] not in cache[p["file"]]:
                problems.append(f"{row['item_id']}: {p['file']} has no line {p['anchor_line'][:60]!r}")
    return problems


def write_provisions(folder: Path, out: Path = PROVISIONS_PATH, audit_dir: Path = AUDIT_DIR) -> list[dict[str, Any]]:
    """Build the provisions file from a written corpus folder, MC-100's oracle evidence, the audit batches and the
    owner's review. Checks first that every file in the folder still has its manifest SHA-256."""
    manifest = json.loads((folder / "folder_manifest.json").read_text(encoding="utf-8"))
    docs_dir = folder / "docs"
    changed = [row["file"] for row in manifest["files"]
               if v1.sha256_bytes((docs_dir / row["file"]).read_bytes()) != row["sha256"]]
    if changed or len(list(docs_dir.iterdir())) != len(manifest["files"]):
        raise _fail(f"{folder} differs from its manifest: {changed[:3]}")
    oracle_rows = [json.loads(line) for line in lo.EVIDENCE_PATH.read_text(encoding="utf-8").splitlines() if line]
    batches = {n: json.loads((audit_dir / f"located_batch_{n}.json").read_text(encoding="utf-8"))["items"]
               for n in range(1, 5)}
    review = json.loads((audit_dir / "review_labels.json").read_text(encoding="utf-8"))
    owner = {row["item_id"]: row["owner_label"] for row in review["items"]}
    rows = item_provisions(manifest["files"], docs_dir, oracle_rows, batches, owner, review["reviewer"])
    out.write_text("".join(json.dumps({key: row[key] for key in PROVISION_KEYS}, ensure_ascii=False) + "\n"
                           for row in rows), encoding="utf-8")
    return rows


def pool_items() -> list[v1.EvalItem]:
    pool = set(lr.pool_ids(lr.load_protocol()))
    items = [item for item in v1._load_legal(lo.DATASET) if item.item_id in pool]  # noqa: SLF001
    if len(items) != len(pool):
        raise _fail(f"{len(items)} of the {len(pool)} pool items found")
    return items


# ---------------------------------------------------------------- protocol, prompts and manifest (MC-112)

DATA_DIR = ROOT / "data" / "diagnostic_legal_agent"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
PROMPTS_PATH = DATA_DIR / "agent_prompts_v1.json"
PROFILE_PATH = DATA_DIR / "dsh_profile_v1.yml"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-legal-agent"
PHASE = "legal-agent"
ARMS = ("DSH", "DSHF")
HASH_KEYS = ("legal_agent_protocol_sha256", "agent_prompts_sha256", "dsh_profile_sha256", "provisions_sha256",
             "added_documents_sha256", "offsite_documents_sha256", "mc101_sources_sha256", "mc101_corpus_sha256",
             "oracle_evidence_sha256", "folder_sha256", "mc111_scores_sha256", "dsh_lockfile_sha256")


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-agent protocol id or version")
    if tuple(protocol.get("arms") or ()) != ARMS or protocol.get("draws") != 2:
        raise _fail(f"the legal-agent protocol must run {ARMS} with two draws")
    return protocol


def load_prompts(path: Path = PROMPTS_PATH) -> dict[str, str]:
    prompts = json.loads(path.read_text(encoding="utf-8"))
    if set(prompts) != {"version", "separator", *ARMS} or not all(isinstance(v, str) and v for v in prompts.values()):
        raise _fail("the agent prompt file must hold version, separator and one instruction per arm")
    return prompts


def arm_task(base_prompt: str, arm: str, prompts: dict[str, str]) -> str:
    """The task dsh receives: the arm's instruction, a blank line, then the frozen B prompt, byte for byte."""
    return prompts[arm] + prompts["separator"] + base_prompt


def load_provisions(path: Path = PROVISIONS_PATH) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(tuple(row) != PROVISION_KEYS for row in rows) or len({row["item_id"] for row in rows}) != len(rows):
        raise _fail("the provisions file has unexpected keys or a repeated item")
    return {row["item_id"]: row for row in rows}


def load_reference(protocol: dict[str, Any], root: Path = ROOT) -> list[dict[str, Any]]:
    """MC-111's scored rows (B, K, K10, O and the rest), from the file whose SHA-256 the protocol registers."""
    reference = protocol["reference"]
    path = root / reference["scores"]
    if not path.is_file() or v1.sha256_file(path) != reference["scores_sha256"]:
        raise _fail(f"MC-111's score file {path} is missing or differs from its registered SHA-256")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_manifest(protocol: dict[str, Any] | None = None, root: Path = ROOT
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. Item-major: item, draw, arm. Each base prompt must be the
    one MC-111's B sent for that item."""
    protocol = protocol or load_protocol()
    prompts = load_prompts()
    pool = lr.pool_ids(lr.load_protocol())
    if len(pool) != protocol["pool_size"]:
        raise _fail(f"the pool has {len(pool)} items, not {protocol['pool_size']}")
    frozen = lo.legal_items()
    b_prompts = {row["item_id"]: row["prompt_sha256"] for row in load_reference(protocol, root) if row["arm"] == "B"}
    provisions = load_provisions()
    if set(provisions) != set(pool):
        raise _fail("the provisions file must cover exactly the pool")
    items: list[v1.EvalItem] = []
    for item_id in pool:
        base = frozen[item_id]
        if v1.sha256_bytes(base.prompt.encode("utf-8")) != b_prompts.get(item_id):
            raise _fail(f"{item_id}: the frozen prompt differs from the one MC-111's B sent")
        for draw in range(1, protocol["draws"] + 1):
            for arm in ARMS:
                items.append(dataclasses.replace(base, replicate_id=f"{arm}-r{draw}",
                                                 prompt=arm_task(base.prompt, arm, prompts)))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate legal-agent run keys")
    hashes = {
        "legal_agent_protocol_sha256": v1.sha256_file(PROTOCOL_PATH),
        "agent_prompts_sha256": v1.sha256_file(PROMPTS_PATH), "dsh_profile_sha256": v1.sha256_file(PROFILE_PATH),
        "provisions_sha256": v1.sha256_file(PROVISIONS_PATH), "added_documents_sha256": v1.sha256_file(ADDED_PATH),
        "offsite_documents_sha256": v1.sha256_file(OFFSITE_PATH), "mc101_sources_sha256": MC101_SOURCES_SHA256,
        "mc101_corpus_sha256": MC101_CORPUS_SHA256, "oracle_evidence_sha256": v1.sha256_file(lo.EVIDENCE_PATH),
        "folder_sha256": protocol["corpus"]["folder_sha256"],
        "mc111_scores_sha256": protocol["reference"]["scores_sha256"],
        "dsh_lockfile_sha256": protocol["harness"]["lockfile_sha256"],
    }
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, **hashes,
        "pool": pool, "support": {item_id: provisions[item_id]["support"] for item_id in pool},
        "n": len(items), "item_count": len(pool), "dataset_counts": {lo.DATASET: len(pool)},
        "arm_counts": {arm: sum(item.replicate_id.startswith(f"{arm}-r") for item in items) for arm in ARMS},
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MC-112 inputs, offline: the legal corpus folder for dsh and each "
                                                 "item's provisions in it.")
    commands = parser.add_subparsers(dest="command", required=True)
    folder = commands.add_parser("folder", help="write the corpus folder")
    folder.add_argument("--out", type=Path, required=True, help="new directory; the files go to <out>/docs")
    provisions = commands.add_parser("provisions", help="write each item's provisions with anchor lines")
    provisions.add_argument("--folder", type=Path, required=True, help="a folder written by `folder`")
    provisions.add_argument("--out", type=Path, default=PROVISIONS_PATH)
    args = parser.parse_args(argv)
    if args.command == "provisions":
        rows = write_provisions(args.folder, args.out)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["support"]] = counts.get(row["support"], 0) + 1
        print(f"{len(rows)} items, {sum(len(r['provisions']) for r in rows)} provisions; {counts}; "
              f"owner-labelled {sum(r['label_source'].startswith('owner:') for r in rows)} -> {args.out}")
        return 0
    manifest = build_folder(load_documents(), load_mc101_articles(), pool_items(), args.out)
    (args.out / "folder_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
    print(f"{manifest['documents']} files ({manifest['added']} added), {manifest['chars']:,} characters, "
          f"truncated {manifest['truncated']}; folder sha256 {manifest['folder_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
