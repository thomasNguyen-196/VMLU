"""The Legal MC retrieval test (openspec change diagnostic-legal-retrieval; card MC-101).

Question: with a corpus built from the Legal MC questions alone and the campaign's BM25, does arm K (the two
retrieved units in the campaign evidence block, then the frozen MC prompt) beat arm B (the frozen prompt) on Legal
MC as a whole, and how much of the MC-100 oracle gain (arm O) does it keep?

* Items (data/diagnostic_legal_retrieval/protocol.json): the 134 Legal MC items of the wide phase, the MC-100 pool.
  MC-100's frozen strata, support labels and oracle provisions are reused, checked against what MC-100 registered.
* Corpus `vi-legal-corpus-lmc-v1`: documents chosen from the question stems alone (no options, no gold), all from
  hethongphapluat.com, each page stored with its SHA-256 (all_res/diagnostic_legal_retrieval/corpus/). Articles
  are read by code (reader v1) and an article over 6,000 characters is split into parts at line boundaries.
* Retrieval: BM25 with the corpus v0 settings; the top 2 units of each item form its frozen K evidence.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval stems --out <dir> [--batches 4]
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval page <url> [--part <heading line>]
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval merge-sources --lists <sources_*.json> [--write]
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval fetch
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval build-corpus
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval retrieve [--write]
  .venv/bin/python -m code_benchmark.diagnostic_legal_retrieval manifest [--write]
"""
from __future__ import annotations

import argparse
import dataclasses
import fcntl
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_oracle as lo
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import vi_multimodel as v1

ROOT = dp.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_retrieval"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
SOURCES_PATH = DATA_DIR / "corpus_sources_v1.json"
RETRIEVAL_PATH = DATA_DIR / "retrieval_v1.json"
EVIDENCE_PATH = DATA_DIR / "retrieved_evidence_v1.jsonl"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_retrieval"
CORPUS_DIR = WORK_ROOT / "corpus"
RETRIEVAL_DIR = WORK_ROOT / "retrieval"
PROTOCOL_ID = "vmlu-diagnostic-legal-retrieval"
PHASE = "legal-retrieval"
DATASET = lo.DATASET
ARMS = ("B", "K", "O")
ROLES = ("topical", "predecessor", "distractor")
SITE = "https://hethongphapluat.com/"
K_KEYS = ("dataset_id", "item_id", "provisions", "ranking", "query_sha256", "corpus_sha256", "retrieval_config_sha256")
FETCH_GAP_SECONDS = 2.0
_HEAD = re.compile(r"^Điều\s+(\d+[a-zđ]?)(?:\s*\[\d+\])?\s*[.:]", re.IGNORECASE)
_SECTION = re.compile(r"^(?:Chương\s+[IVXLC]+\b|Mục\s+\d+\b)", re.IGNORECASE)
_ANNEX = re.compile(r"^(?:DANH MỤC\s+)?PHỤ LỤC\b")  # upper case only: a sentence may open with "Phụ lục"
# Where an attached text ends: the signature block, or the site's own blocks that follow every document.
_END = re.compile(r"^(?:Nơi nhận\s*:|(?:TM|KT|TL|TUQ|Q)\.\s+\S|Văn bản liên quan|HIỆU LỰC VĂN BẢN|MỤC LỤC VĂN BẢN|"
                  r"Số hiệu\s*:|QUAN TRỌNG\b)")
_LOCATOR = re.compile(r"^(?:(?P<part>.+?) kèm theo, )?Điều (?P<number>\d+[a-zđ]?)", re.IGNORECASE)
_TITLE_YEAR = re.compile(r"\bnăm (\d{4})\b", re.IGNORECASE)


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = _read_json(path, "legal-retrieval protocol")
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-retrieval protocol id/version")
    if protocol.get("dataset") != DATASET or set(protocol.get("arms", {})) != set(ARMS) or protocol.get("draws") != 2:
        raise _fail(f"the legal-retrieval protocol runs arms {list(ARMS)} on two draws of {DATASET}")
    return protocol


# ---------------------------------------------------------------- items and MC-100

def pool_ids(protocol: dict[str, Any]) -> list[str]:
    """The MC-100 pool: every Legal MC item of the wide phase with both B draws."""
    pool = sorted(lo.b_outcomes(lo.load_protocol()))
    if len(pool) != protocol["pool"]["size"]:
        raise _fail(f"the pool has {len(pool)} items, not {protocol['pool']['size']}")
    return pool


def mc100_frozen() -> dict[str, Any]:
    """MC-100's strata, support labels and oracle records, each checked against what MC-100 registered."""
    registration = _read_json(lo.REGISTRATION_PATH, "MC-100 registration")
    frozen = registration["frozen"]
    manifest = lo.load_frozen_manifest()
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if (manifest.get("manifest_sha256") != frozen["manifest_sha256"]
            or v1.sha256_bytes(v1.canonical_json(unhashed)) != frozen["manifest_sha256"]):
        raise _fail("the MC-100 manifest differs from its registration")
    if v1.sha256_file(lo.EVIDENCE_PATH) != frozen["evidence_sha256"]:
        raise _fail("the MC-100 oracle evidence differs from its registration")
    if manifest["source_sha256"] != lo.source_sha256(lo.load_protocol()):
        raise _fail("the B draws that defined the MC-100 strata have changed")
    oracle = lo.load_evidence(lo.EVIDENCE_PATH, manifest["strata"])
    return {"registration": registration, "manifest": manifest, "strata": manifest["strata"],
            "support": manifest["support"], "oracle": oracle}


def question_stem(item: v1.EvalItem) -> str:
    """The question text of an MC item, without the instruction, the options and the answer tail."""
    stem, _ = dr.mc_question_and_options(item)
    return stem.strip()


def stem_batches(pool: list[str], items: dict[str, v1.EvalItem], batches: int = 4) -> list[list[dict[str, str]]]:
    """The pool in item-id order, cut into contiguous batches of stems for the corpus agents."""
    rows = [{"item_id": item_id, "stem": question_stem(items[item_id])} for item_id in sorted(pool)]
    size, extra = divmod(len(rows), batches)
    out, start = [], 0
    for index in range(batches):
        end = start + size + (1 if index < extra else 0)
        out.append(rows[start:end])
        start = end
    return out


# ---------------------------------------------------------------- pages

def stored_page(url: str, corpus_dir: Path = CORPUS_DIR) -> str:
    return lo.stored_page(url, corpus_dir)


def store_page(url: str, corpus_dir: Path = CORPUS_DIR, gap: float = FETCH_GAP_SECONDS) -> dict[str, Any]:
    """Fetch and store a page once, under a lock shared by concurrent callers and FETCH_GAP_SECONDS apart."""
    if not url.startswith(SITE):
        raise _fail(f"corpus pages come from {SITE} only: {url}")
    (corpus_dir / "raw").mkdir(parents=True, exist_ok=True)
    log_path = corpus_dir / "fetch_log.jsonl"
    with (corpus_dir / ".fetch.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = _read_jsonl(log_path, "fetch log") if log_path.exists() else []
        for entry in entries:
            if entry["url"] == url:
                return entry
        last = max((entry["fetched_at_epoch"] for entry in entries), default=0.0)
        time.sleep(max(0.0, last + gap - time.time()))
        raw = dr.fetch(url)
        digest = v1.sha256_bytes(raw)
        name = f"{digest[:24]}.html"
        (corpus_dir / "raw" / name).write_bytes(raw)
        entry = {"url": url, "file": name, "sha256": digest, "bytes": len(raw),
                 "fetched_at": datetime.now(timezone.utc).isoformat(), "fetched_at_epoch": time.time()}
        with log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry


# ---------------------------------------------------------------- reader v1 and units

def parse_articles_v1(page: str) -> list[tuple[str, str]]:
    """The page's top-level article elements as (number, text): MC-100's reader, with a heading that carries a
    footnote marker ("Điều 15[15].") read as the heading of Điều 15. Fails closed like corpus v0's reader."""
    page = dr._NON_CONTENT.sub("", page)  # noqa: SLF001 - same package, same page reading
    depth = start = 0
    for match in dr._DIEU_TAG.finditer(page):  # noqa: SLF001
        if match.group(1) != "/":
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
    if depth:  # the last top-level element never closes: keep the articles before it
        page = page[:start]
    articles: list[tuple[str, str]] = []
    depth = start = 0
    for match in dr._DIEU_TAG.finditer(page):  # noqa: SLF001
        if match.group(1) != "/":
            if depth == 0:
                start = match.end()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                text = dr.html_to_text(page[start:match.start()])
                head = _HEAD.match(text)
                if not head:
                    raise _fail(f"an article element does not open with its heading: {text[:60]!r}")
                articles.append((head.group(1).lower(), text))
    if not articles:
        raise _fail("the page has no article elements")
    numbers = [number for number, _ in articles]
    repeated = sorted({number for number in numbers if numbers.count(number) > 1})
    if repeated:
        raise _fail(f"repeated article numbers {repeated[:5]}")
    return articles


def attached_articles(page: str, part: str) -> list[tuple[str, str]]:
    """Every article of the text attached under the heading line `part` (a Quy chế issued by a Quyết định), read
    from the page text. An article runs from its heading line to the next article heading; a chapter, section or
    annex heading ends it, and the attached text ends at a signature or recipients line, at the site's own blocks
    or at a repeated article number."""
    lines = dr.html_to_text(dr._NON_CONTENT.sub("", page)).splitlines()  # noqa: SLF001
    if part not in lines:
        raise _fail(f"no line {part!r} on the stored page")
    articles: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in lines[lines.index(part) + 1:]:
        if _END.match(line):
            break
        head = _HEAD.match(line)
        if head:
            number = head.group(1).lower()
            if number in {seen for seen, _ in articles}:
                break
            current = [line]
            articles.append((number, current))
        elif _SECTION.match(line) or _ANNEX.match(line):
            current = None
        elif current is not None:
            current.append(line)
    if not articles:
        raise _fail(f"no article after the line {part!r}")
    return [(number, "\n".join(text)) for number, text in articles]


def split_text(text: str, max_chars: int) -> list[str]:
    """The article itself, or consecutive parts cut at line boundaries, each part after the first opening with
    the heading line; a part exceeds max_chars only when a single line does."""
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    head, parts, current = lines[0], [], [lines[0]]
    size = len(head)
    for line in lines[1:]:
        if len(current) > 1 and size + 1 + len(line) > max_chars:
            parts.append("\n".join(current))
            current, size = [head], len(head)
        current.append(line)
        size += 1 + len(line)
    parts.append("\n".join(current))
    return parts


def document_units(document: dict[str, Any], page: str, max_chars: int) -> list[dict[str, Any]]:
    """The document's units in page order, shaped like corpus v0 chunks (`diagnostic_retrieval.CHUNK_KEYS`)."""
    part = document.get("part")
    pieces: list[tuple[str, str, str]] = []
    try:
        pieces += [("dieu", number, text) for number, text in parse_articles_v1(page)]
    except SystemExit:
        if not part:
            raise
    if part:
        pieces += [("kem-dieu", number, text) for number, text in attached_articles(page, part)]
    units = []
    for kind, number, text in pieces:
        parts = split_text(text, max_chars)
        prefix = f"{part.capitalize()} kèm theo, " if kind == "kem-dieu" and part else ""
        for index, piece in enumerate(parts, 1):
            several = len(parts) > 1
            units.append({
                "chunk_id": f"{document['doc_id']}#{kind}-{number}" + (f"-p{index}" if several else ""),
                "doc_id": document["doc_id"], "doc_title": document["title"], "article": number,
                "locator": f"{prefix}Điều {number}" + (f" (phần {index}/{len(parts)})" if several else ""),
                "text": piece, "text_sha256": v1.sha256_bytes(piece.encode("utf-8")), "source_ref": document["url"]})
    return units


# ---------------------------------------------------------------- sources

def _role_rank(role: str) -> int:
    return ROLES.index(role)


def merge_sources(lists: list[dict[str, Any]], pool: list[str], protocol: dict[str, Any]) -> dict[str, Any]:
    """One entry per page from the agents' lists, deterministic whatever the list order. Fails closed on a pool
    gap or overlap, an unknown role, a site other than hethongphapluat.com, an over-cap list or a clash of the
    attached-text heading or of a document number between pages."""
    rows: list[tuple[int, str, dict[str, Any]]] = []
    seen_items: Counter[str] = Counter()
    for listing in sorted(lists, key=lambda value: int(value["batch"])):
        batch = int(listing["batch"])
        distractors = listing.get("distractors") or []
        if len(distractors) > 5:
            raise _fail(f"batch {batch}: {len(distractors)} distractors, more than 5")
        for document in distractors:
            rows.append((batch, "", {**document, "role": "distractor"}))
        for item in listing["items"]:
            seen_items[item["item_id"]] += 1
            documents = item.get("documents") or []
            topical = [document for document in documents if document.get("role") == "topical"]
            if len(topical) > 3:
                raise _fail(f"{item['item_id']}: {len(topical)} topical documents, more than 3")
            topical_ids = {document["doc_id"] for document in topical}
            for document in documents:
                if document.get("role") not in ("topical", "predecessor"):
                    raise _fail(f"{item['item_id']}: an item lists topical or predecessor documents only")
                if document["role"] == "predecessor" and document.get("predecessor_of") not in topical_ids:
                    raise _fail(f"{item['item_id']}: predecessor {document.get('doc_id')} names no topical document")
                rows.append((batch, item["item_id"], document))
    if set(seen_items) != set(pool) or any(count != 1 for count in seen_items.values()):
        raise _fail(f"the lists cover {len(seen_items)} items, not each of the {len(pool)} pool items once")
    merged: dict[str, dict[str, Any]] = {}
    for batch, item_id, document in sorted(rows, key=lambda row: (_role_rank(row[2]["role"]), row[0], row[1])):
        url = str(document.get("url") or "").strip()
        if not url.startswith(SITE):
            raise _fail(f"{item_id or f'batch {batch}'}: documents come from {SITE} only: {url!r}")
        if not str(document.get("doc_id") or "").strip() or not str(document.get("title") or "").strip():
            raise _fail(f"{item_id or f'batch {batch}'}: every document needs doc_id and title")
        entry = merged.setdefault(url, {"doc_id": document["doc_id"].strip(), "title": document["title"].strip(),
                                        "url": url, "role": document["role"], "items": [], "predecessor_of": []})
        if document.get("part"):
            if entry.get("part", document["part"]) != document["part"]:
                raise _fail(f"{url}: two attached-text headings {entry['part']!r} and {document['part']!r}")
            entry["part"] = document["part"]
        if item_id and item_id not in entry["items"]:
            entry["items"].append(item_id)
        if document.get("predecessor_of") and document["predecessor_of"] not in entry["predecessor_of"]:
            entry["predecessor_of"].append(document["predecessor_of"])
    documents = []
    for url in sorted(merged):
        entry = merged[url]
        entry["items"].sort()
        entry["predecessor_of"].sort()
        if not entry["predecessor_of"]:
            del entry["predecessor_of"]
        documents.append(entry)
    renamed = qualify_consolidated_numbers(documents)
    numbers = Counter(entry["doc_id"] for entry in documents)
    clashes = sorted(doc_id for doc_id, count in numbers.items() if count > 1)
    if clashes:
        raise _fail(f"one document number on several pages: {clashes[:5]}")
    covered = {item for entry in documents if entry["role"] == "topical" for item in entry["items"]}
    return {"corpus_id": protocol["corpus"]["corpus_id"], "version": 1, "source_site": protocol["corpus"]["source_site"],
            "selection_rule": protocol["corpus"]["chosen_by"], "roles": protocol["corpus"]["roles"],
            "documents": documents, "uncovered": sorted(set(pool) - covered), "renamed": renamed,
            "role_counts": dict(Counter(entry["role"] for entry in documents))}


def qualify_consolidated_numbers(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Consolidated texts (VBHN) are numbered anew each year, so one number can sit on pages of different years.
    Such a number is qualified, in place, by the year its page title prints ("năm 2025" -> "09/VBHN-VPQH (2025)").
    Any other clash is left for the caller to refuse."""
    renamed = []
    for doc_id, count in Counter(entry["doc_id"] for entry in documents).items():
        clashing = [entry for entry in documents if entry["doc_id"] == doc_id]
        years = [_TITLE_YEAR.search(entry["title"]) for entry in clashing]
        if count < 2 or "VBHN" not in doc_id or not all(years):
            continue
        if len({year.group(1) for year in years if year}) != len(clashing):
            continue
        for entry, year in zip(clashing, years, strict=True):
            if year:
                entry["doc_id"] = f"{doc_id} ({year.group(1)})"
                renamed.append({"url": entry["url"], "from": doc_id, "to": entry["doc_id"]})
    return renamed


def load_sources(path: Path = SOURCES_PATH) -> dict[str, Any]:
    sources = _read_json(path, "corpus sources")
    if sources.get("corpus_id") != "vi-legal-corpus-lmc-v1" or not sources.get("documents"):
        raise _fail(f"{path.name}: not the vi-legal-corpus-lmc-v1 source list")
    for entry in sources["documents"]:
        if entry.get("role") not in ROLES or not str(entry.get("url", "")).startswith(SITE):
            raise _fail(f"{path.name}: {entry.get('doc_id')} has an unknown role or another site")
    return sources


# ---------------------------------------------------------------- corpus

def build_corpus(sources: dict[str, Any], items: list[v1.EvalItem], max_chars: int, sources_sha256: str,
                 corpus_dir: Path = CORPUS_DIR) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """(units, manifest, leak report) from the stored pages; a document that yields no unit is omitted, with its
    reason. Fails closed when the leak check fails."""
    units: list[dict[str, Any]] = []
    omitted = []
    for document in sources["documents"]:
        try:
            units += document_units(document, stored_page(document["url"], corpus_dir), max_chars)
        except SystemExit as exc:
            omitted.append({"doc_id": document["doc_id"], "url": document["url"], "role": document["role"],
                            "reason": str(exc).removeprefix("Error: ")})
    ids = Counter(unit["chunk_id"] for unit in units)
    if any(count > 1 for count in ids.values()):
        raise _fail(f"duplicate unit ids {[chunk for chunk, count in ids.items() if count > 1][:5]}")
    leak = dr.leak_report(units, items)
    if not leak["passed"]:
        raise _fail(f"the leak check failed: {leak['questions_in_corpus'][:5]} {leak['answer_key_chunks'][:5]}")
    raw = "".join(json.dumps(unit, ensure_ascii=False) + "\n" for unit in units).encode("utf-8")
    manifest = {"corpus_id": sources["corpus_id"], "version": 1, "unit": "article", "unit_max_chars": max_chars,
                "built_at": datetime.now(timezone.utc).isoformat(), "documents": len(sources["documents"]),
                "documents_with_units": len({unit["doc_id"] for unit in units}), "omitted": omitted,
                "chunks": len(units), "split_parts": sum("-p" in unit["chunk_id"].rsplit("#", 1)[1] for unit in units),
                "chars": sum(len(unit["text"]) for unit in units), "sources_sha256": sources_sha256,
                "leak_check_passed": leak["passed"], "corpus_sha256": v1.sha256_bytes(raw)}
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "corpus.jsonl").write_bytes(raw)
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")
    (corpus_dir / "checks.json").write_text(json.dumps(leak, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return units, manifest, leak


# ---------------------------------------------------------------- retrieval and K evidence

def load_index(corpus_dir: Path = CORPUS_DIR, config_path: Path = RETRIEVAL_PATH) -> dr.Index:
    chunks, manifest = dr.load_corpus(corpus_dir)
    config, digest = dr.load_config(config_path)
    return dr.build_index(chunks, manifest, config, digest)


def k_record(index: dr.Index, item: v1.EvalItem) -> dict[str, Any]:
    """One item's K evidence: the top_k units as provisions, the kept ranking and the hashes that tie them."""
    query = dr.mc_query(item)
    ranked = dr.rank(index, query)[:index.config["ranking_kept"]]
    if len(ranked) < index.config["top_k"]:
        raise _fail(f"{item.item_id}: fewer than {index.config['top_k']} units share a token with the query")
    provisions = [{key: index.chunks[position][key] for key in dp.PROVISION_KEYS}
                  for position, _ in ranked[:index.config["top_k"]]]
    return {"dataset_id": item.dataset_id, "item_id": item.item_id,
            "provisions": dp.validate_provisions(provisions, item.item_id, verbatim_source=True),
            "ranking": [{"chunk_id": index.chunks[position]["chunk_id"], "score": round(score, 6),
                         "text_sha256": index.chunks[position]["text_sha256"]} for position, score in ranked],
            "query_sha256": v1.sha256_bytes(query.encode("utf-8")),
            "corpus_sha256": index.corpus_sha256, "retrieval_config_sha256": index.config_sha256}


def load_k_evidence(path: Path, pool: list[str], index: dr.Index) -> dict[str, dict[str, Any]]:
    """{item_id: record}; fails closed on shape, leakage, a gap, a changed corpus or configuration, or a unit
    that is not the corpus unit its ranking names."""
    by_id = {chunk["chunk_id"]: chunk for chunk in index.chunks}
    top_k = index.config["top_k"]
    result: dict[str, dict[str, Any]] = {}
    for number, record in enumerate(_read_jsonl(path, "K evidence"), 1):
        where = f"{path.name}:{number}"
        if set(record) != set(K_KEYS) or dp.FORBIDDEN_EVIDENCE_KEYS & set(record):
            raise _fail(f"{where}: record must have exactly the keys {list(K_KEYS)}")
        if record["dataset_id"] != DATASET or record["item_id"] in result:
            raise _fail(f"{where}: wrong dataset or a duplicate item")
        if (record["corpus_sha256"], record["retrieval_config_sha256"]) != (index.corpus_sha256, index.config_sha256):
            raise _fail(f"{where}: the corpus or retrieval configuration differs from the built index")
        dp.validate_provisions(record["provisions"], where, verbatim_source=True)
        if len(record["provisions"]) != top_k:
            raise _fail(f"{where}: {len(record['provisions'])} provisions, not {top_k}")
        for provision, entry in zip(record["provisions"], record["ranking"][:top_k], strict=True):
            chunk = by_id.get(entry["chunk_id"])
            if chunk is None or {key: chunk[key] for key in dp.PROVISION_KEYS} != provision:
                raise _fail(f"{where}: a provision is not the corpus unit {entry['chunk_id']}")
        result[record["item_id"]] = record
    if set(result) != set(pool):
        raise _fail(f"the K evidence covers {len(result)} of {len(pool)} pool items")
    return result


def doc_key(doc_id: str) -> str:
    """A document number compared across agents: NFC, case, spaces and Đ/D folded."""
    text = unicodedata.normalize("NFC", doc_id).casefold().replace("đ", "d")
    return re.sub(r"\s+", "", text)


def unit_target(chunk_id: str) -> tuple[str, str, str]:
    doc_id, _, rest = chunk_id.rpartition("#")
    kind, _, number = rest.partition("-dieu-") if rest.startswith("kem-") else ("", "", rest.removeprefix("dieu-"))
    return doc_key(doc_id), "kem" if kind else "", re.sub(r"-p\d+$", "", number)


def oracle_targets(provisions: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    targets = set()
    for provision in provisions:
        match = _LOCATOR.match(provision["locator"])
        if not match:
            raise _fail(f"cannot read an article from the locator {provision['locator']!r}")
        targets.add((doc_key(provision["doc_id"]), "kem" if match.group("part") else "",
                     match.group("number").lower()))
    return targets


def hit_report(records: dict[str, dict[str, Any]], oracle: dict[str, dict[str, Any]], index: dr.Index
               ) -> dict[str, Any]:
    """Whether each item's kept ranking holds an article the MC-100 oracle cited (same document number and
    article, any part counting), at 1, 2 and 3; and which oracle documents the corpus holds at all."""
    corpus_docs = {doc_key(chunk["doc_id"]) for chunk in index.chunks}
    rows = []
    for item_id, record in sorted(oracle.items()):
        if not record["provisions"]:
            continue
        targets = oracle_targets(record["provisions"])
        ranked = [unit_target(entry["chunk_id"]) for entry in records[item_id]["ranking"]]
        rows.append({"item_id": item_id, "targets": sorted("|".join(target) for target in targets),
                     "retrieved": [entry["chunk_id"] for entry in records[item_id]["ranking"]],
                     "first_hit_rank": next((rank for rank, target in enumerate(ranked, 1) if target in targets), None),
                     "oracle_document_in_corpus": any(target[0] in corpus_docs for target in targets)})
    def at(k: int) -> int:
        return sum(row["first_hit_rank"] is not None and row["first_hit_rank"] <= k for row in rows)
    oracle_docs = {target[0] for record in oracle.values() for target in oracle_targets(record["provisions"])}
    return {"items": len(rows), "hit_at_1": at(1), "hit_at_2": at(2), "hit_at_3": at(3),
            "share_at_2": round(at(2) / len(rows), 4) if rows else None,
            "items_with_an_oracle_document_in_corpus": sum(row["oracle_document_in_corpus"] for row in rows),
            "oracle_documents": len(oracle_docs), "oracle_documents_in_corpus": len(oracle_docs & corpus_docs),
            "per_item": rows}


# ---------------------------------------------------------------- manifest

def build_manifest(protocol_path: Path = PROTOCOL_PATH, evidence_path: Path = EVIDENCE_PATH,
                   corpus_dir: Path = CORPUS_DIR) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. Item-major: item, draw, arm; O only where MC-100 has
    provisions."""
    protocol = load_protocol(protocol_path)
    pool = pool_ids(protocol)
    mc100 = mc100_frozen()
    index = load_index(corpus_dir)
    k_evidence = load_k_evidence(evidence_path, pool, index)
    templates = dp.load_templates()
    frozen = lo.legal_items()
    items: list[v1.EvalItem] = []
    for item_id in pool:
        base = frozen[item_id]
        prompts = {"B": base.prompt, "K": dp.build_arm_prompt(base, "K", templates, k_evidence[item_id]["provisions"])}
        oracle = mc100["oracle"].get(item_id)
        if oracle and oracle["provisions"]:
            prompts["O"] = dp.build_arm_prompt(base, "O", templates, oracle["provisions"])
        for draw in range(1, protocol["draws"] + 1):
            for arm in ARMS:
                if arm in prompts:
                    items.append(dataclasses.replace(base, replicate_id=f"{arm}-r{draw}", prompt=prompts[arm]))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate legal-retrieval run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "legal_retrieval_protocol_sha256": v1.sha256_file(protocol_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "sources_sha256": v1.sha256_file(SOURCES_PATH), "corpus_sha256": index.corpus_sha256,
        "retrieval_config_sha256": index.config_sha256, "k_evidence_sha256": v1.sha256_file(evidence_path),
        "oracle_evidence_sha256": v1.sha256_file(lo.EVIDENCE_PATH),
        "mc100_manifest_sha256": mc100["manifest"]["manifest_sha256"], "source_sha256": mc100["manifest"]["source_sha256"],
        "pool": pool, "strata": mc100["strata"], "support": mc100["support"],
        "n": len(items), "item_count": len(pool), "dataset_counts": {DATASET: len(pool)},
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return _read_json(path, "frozen legal-retrieval manifest")


def retrieval_traces(manifest: dict[str, Any], evidence_path: Path = EVIDENCE_PATH) -> dict[str, dict[str, Any]]:
    """{dataset:item: retrieval trace} for the campaign engine, which attaches one to every K row."""
    pool = set(manifest["pool"])
    return {dp.item_key(record["dataset_id"], record["item_id"]): {
                "corpus_sha256": record["corpus_sha256"], "retrieval_config_sha256": record["retrieval_config_sha256"],
                "query_sha256": record["query_sha256"],
                "ranking": [{"chunk_id": entry["chunk_id"], "score": entry["score"]}
                            for entry in record["ranking"][:len(record["provisions"])]]}
            for record in _read_jsonl(evidence_path, "K evidence") if record["item_id"] in pool}


# ---------------------------------------------------------------- CLI

def _page_summary(url: str, part: str | None) -> dict[str, Any]:
    entry = store_page(url)
    page = stored_page(url)
    summary: dict[str, Any] = {"url": url, "file": entry["file"], "sha256": entry["sha256"][:16]}
    try:
        articles = parse_articles_v1(page)
        summary["articles"] = len(articles)
        summary["first_last"] = [articles[0][1].split("\n")[0][:80], articles[-1][1].split("\n")[0][:80]]
    except SystemExit as exc:
        summary["articles"] = 0
        summary["reader"] = str(exc).removeprefix("Error: ")
    lines = dr.html_to_text(dr._NON_CONTENT.sub("", page)).splitlines()  # noqa: SLF001
    summary["heading_lines"] = sorted({line for line in lines if line.isupper() and 3 <= len(line) <= 40
                                       and re.match(r"^(QUY CHẾ|QUY ĐỊNH|ĐIỀU LỆ|QUY TRÌNH|HƯỚNG DẪN)", line)})
    if part:
        try:
            attached = attached_articles(page, part)
            summary["attached_articles"] = len(attached)
            summary["attached_first_last"] = [attached[0][1].split("\n")[0][:80], attached[-1][1].split("\n")[0][:80]]
        except SystemExit as exc:
            summary["attached"] = str(exc).removeprefix("Error: ")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Legal MC retrieval test (offline helpers).")
    sub = ap.add_subparsers(dest="command", required=True)
    stems = sub.add_parser("stems", help="write the question stems of the pool in batches (no options, no gold)")
    stems.add_argument("--out", type=Path, required=True)
    stems.add_argument("--batches", type=int, default=4)
    page = sub.add_parser("page", help="store one page and summarize what the reader finds on it")
    page.add_argument("url")
    page.add_argument("--part", help="the heading line of an attached text, e.g. 'QUY CHẾ'")
    merge = sub.add_parser("merge-sources", help="merge the agents' lists into the corpus source list")
    merge.add_argument("--lists", type=Path, nargs="+", required=True)
    merge.add_argument("--write", action="store_true", help=f"freeze it as {SOURCES_PATH}")
    sub.add_parser("fetch", help="store every page of the frozen source list")
    sub.add_parser("build-corpus", help="build the corpus from the stored pages")
    retrieve = sub.add_parser("retrieve", help="rank the corpus for every pool item and report oracle hits")
    retrieve.add_argument("--write", action="store_true", help=f"freeze the K evidence as {EVIDENCE_PATH}")
    manifest = sub.add_parser("manifest", help="build the manifest and compare it with the frozen one")
    manifest.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    protocol = load_protocol()
    if args.command == "page":
        print(json.dumps(_page_summary(args.url, args.part), ensure_ascii=False, indent=1))
        return 0
    pool = pool_ids(protocol)
    if args.command == "stems":
        args.out.mkdir(parents=True, exist_ok=True)
        for number, rows in enumerate(stem_batches(pool, lo.legal_items(), args.batches), 1):
            (args.out / f"stems_{number}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                                                          encoding="utf-8")
            print(f"stems_{number}.json: {len(rows)} items {rows[0]['item_id']}..{rows[-1]['item_id']}")
    elif args.command == "merge-sources":
        merged = merge_sources([_read_json(path, "source list") for path in args.lists], pool, protocol)
        merged["lists_sha256"] = {path.name: v1.sha256_file(path) for path in sorted(args.lists)}
        print(f"documents={len(merged['documents'])} roles={merged['role_counts']} uncovered={merged['uncovered']}")
        if args.write:
            if SOURCES_PATH.exists():
                raise _fail(f"{SOURCES_PATH} is frozen; delete it deliberately to rebuild")
            SOURCES_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"frozen -> {SOURCES_PATH} sha256={v1.sha256_file(SOURCES_PATH)}")
    elif args.command == "fetch":
        sources = load_sources()
        failed = []
        for document in sources["documents"]:
            try:
                store_page(document["url"])
            except (OSError, SystemExit) as exc:
                failed.append((document["doc_id"], str(exc)[:120]))
        print(f"stored {len(sources['documents']) - len(failed)} of {len(sources['documents'])} pages; failed {failed}")
    elif args.command == "build-corpus":
        items = lo.legal_items()
        _, built, leak = build_corpus(load_sources(), [items[item_id] for item_id in pool],
                                      protocol["corpus"]["unit_max_chars"], v1.sha256_file(SOURCES_PATH))
        print(f"corpus {built['corpus_sha256']}: {built['chunks']} units ({built['split_parts']} split parts) from "
              f"{built['documents_with_units']} of {built['documents']} documents; omitted {len(built['omitted'])}; "
              f"options verbatim {leak['options_verbatim_in_corpus']}")
    elif args.command == "retrieve":
        index = load_index()
        items = lo.legal_items()
        records = {item_id: k_record(index, items[item_id]) for item_id in pool}
        report = hit_report(records, mc100_frozen()["oracle"], index)
        RETRIEVAL_DIR.mkdir(parents=True, exist_ok=True)
        (RETRIEVAL_DIR / "hit_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                      encoding="utf-8")
        print(f"hits on {report['items']} oracle items: @1 {report['hit_at_1']} @2 {report['hit_at_2']} "
              f"@3 {report['hit_at_3']}; oracle documents in corpus {report['oracle_documents_in_corpus']}"
              f"/{report['oracle_documents']}")
        if args.write:
            if EVIDENCE_PATH.exists():
                raise _fail(f"{EVIDENCE_PATH} is frozen; delete it deliberately to rebuild")
            v1.write_jsonl_atomic(EVIDENCE_PATH, [records[item_id] for item_id in pool])
            load_k_evidence(EVIDENCE_PATH, pool, index)
            print(f"frozen -> {EVIDENCE_PATH} sha256={v1.sha256_file(EVIDENCE_PATH)}")
    else:
        built, _ = build_manifest()
        print(f"legal-retrieval manifest {built['manifest_sha256']}: {built['n']} attempts {built['arm_counts']}")
        if args.write:
            if MANIFEST_PATH.exists():
                raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
            MANIFEST_PATH.write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"frozen -> {MANIFEST_PATH}")
        elif MANIFEST_PATH.exists():
            same = load_frozen_manifest() == built
            print(f"frozen manifest {'matches' if same else 'DIFFERS'}")
            return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
