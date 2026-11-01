"""The Legal MC oracle-evidence test (openspec change diagnostic-legal-oracle; card MC-100).

Question: when Qwen3.5-9B is handed the provision that governs a Legal MC question, does it fix the questions it
answers wrongly, and does it break the ones it answers correctly? Arm O puts the item's oracle provisions, in the
campaign's evidence block, before the frozen main-v1 MC prompt; arm B is the frozen prompt alone. A positive answer
justifies building a legal corpus and testing retrieval on Legal MC; a negative one says missing documents are not
what Qwen gets wrong there.

* Items (data/diagnostic_legal_oracle/protocol.json): the Legal MC items of the wide phase, each answered by B on
  two draws (MC-90 B-r1, MC-91 B-r2). Stratum `wrong` holds every item B missed on at least one draw; stratum
  `right` holds a fixed-order sample of the items B answered correctly on both.
* Evidence: agents locate the governing provision (page, article, clauses); the text is extracted here, verbatim,
  from the stored page (all_res/diagnostic_legal_oracle/sources/). The gold is used to locate and label evidence,
  never in a request.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_legal_oracle select [--worklist <path>]
  .venv/bin/python -m code_benchmark.diagnostic_legal_oracle evidence --found <found_*.jsonl> --worklist <path>
  .venv/bin/python -m code_benchmark.diagnostic_legal_oracle freeze-evidence --review <owner_review.json>
  .venv/bin/python -m code_benchmark.diagnostic_legal_oracle manifest [--write]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import vi_multimodel as v1

ROOT = dp.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_oracle"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
EVIDENCE_PATH = DATA_DIR / "oracle_evidence_v1.jsonl"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_oracle"
SOURCES_DIR = WORK_ROOT / "sources"
EVIDENCE_DIR = WORK_ROOT / "evidence"
PROTOCOL_ID = "vmlu-diagnostic-legal-oracle"
PHASE = "legal-oracle"
DATASET = "vi-multimodel-v1-legal-mc-146"
STRATA = ("wrong", "right")
ARMS = ("B", "O")
SAMPLE_SALT = "legal-oracle-v1|"
REVIEW_SALT = "legal-oracle-review|"
SUPPORT = ("supports_gold", "contradicts_gold", "unclear", "not_found")
EVIDENCE_KEYS = ("dataset_id", "item_id", "provisions", "support", "label_source", "located_by")
_CLAUSE = re.compile(r"^(\d+)\.\s")
_PART_STOP = re.compile(r"^(?:Điều\s+\d+[a-zđ]?\s*[.:]|Chương\s+[IVXLC]+\b|Mục\s+\d+\b|Phụ lục\b)", re.IGNORECASE)


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
    protocol = _read_json(path, "legal-oracle protocol")
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-oracle protocol id/version")
    if protocol.get("dataset") != DATASET:
        raise _fail(f"the legal-oracle protocol covers {DATASET} only")
    if set(protocol.get("arms", {})) != set(ARMS) or protocol.get("draws") != 2:
        raise _fail(f"the legal-oracle protocol runs arms {list(ARMS)} on two draws")
    return protocol


# ---------------------------------------------------------------- selection

def b_outcomes(protocol: dict[str, Any]) -> dict[str, tuple[bool, bool]]:
    """{item_id: (B-r1 correct, B-r2 correct)} over the pool; fails closed on a missing or repeated draw."""
    draws: dict[str, dict[str, bool]] = {}
    for replicate, relative in protocol["selection"]["sources"].items():
        for row in _read_jsonl(ROOT / relative, f"{replicate} scores"):
            if row["dataset_id"] != DATASET or row["replicate_id"] != replicate:
                continue
            seen = draws.setdefault(str(row["item_id"]), {})
            if replicate in seen:
                raise _fail(f"two {replicate} rows for {row['item_id']}")
            seen[replicate] = float(row["correct"]) == 1.0
    replicates = list(protocol["selection"]["sources"])
    incomplete = sorted(item for item, seen in draws.items() if set(seen) != set(replicates))
    if incomplete:
        raise _fail(f"{len(incomplete)} pool items lack a B draw, for example {incomplete[:3]}")
    if len(draws) != protocol["selection"]["pool_size"]:
        raise _fail(f"the pool has {len(draws)} items, not {protocol['selection']['pool_size']}")
    return {item: (seen[replicates[0]], seen[replicates[1]]) for item, seen in draws.items()}


def _hash_order(items: list[str], salt: str) -> list[str]:
    return sorted(items, key=lambda item: v1.sha256_bytes(f"{salt}{item}".encode("utf-8")))


def select_items(protocol: dict[str, Any]) -> dict[str, list[str]]:
    """{stratum: [item_id]}: every item B missed on a draw, and the fixed-order sample of items it never missed."""
    outcomes = b_outcomes(protocol)
    wrong = sorted(item for item, (first, second) in outcomes.items() if not (first and second))
    always = [item for item, (first, second) in outcomes.items() if first and second]
    rule = protocol["selection"]["right"]
    if len(always) < rule["size"]:
        raise _fail(f"only {len(always)} items were right on both draws, fewer than {rule['size']}")
    return {"wrong": wrong, "right": sorted(_hash_order(always, SAMPLE_SALT)[:rule["size"]])}


def source_sha256(protocol: dict[str, Any]) -> dict[str, str]:
    return {replicate: v1.sha256_file(ROOT / relative) for replicate, relative in protocol["selection"]["sources"].items()}


def legal_items() -> dict[str, v1.EvalItem]:
    return {item.item_id: item for item in v1.rebuild_items("main").values() if item.dataset_id == DATASET}


# ---------------------------------------------------------------- evidence

def stored_page(url: str, sources_dir: Path = SOURCES_DIR) -> str:
    """The page stored for `url`, checked against the SHA-256 its fetch-log entry recorded."""
    entries = [row for row in _read_jsonl(sources_dir / "fetch_log.jsonl", "fetch log") if row["url"] == url]
    if len(entries) != 1:
        raise _fail(f"{len(entries)} fetch-log entries for {url}, not one")
    raw = (sources_dir / "raw" / entries[0]["file"]).read_bytes()
    if v1.sha256_bytes(raw) != entries[0]["sha256"]:
        raise _fail(f"the stored page of {url} differs from its fetch log")
    return raw.decode("utf-8", errors="replace")


def page_articles(page: str) -> dict[str, str]:
    """{number: text} of the page's top-level articles, as `dr.parse_articles` reads them, except that a page
    breaking off inside its last article element keeps the articles that closed before it (the stored page of
    NĐ 99/2022 never closes Điều 11). An article inside or after the broken element is not on the page."""
    page = dr._NON_CONTENT.sub("", page)  # noqa: SLF001 - same package, same page reading
    depth, start = 0, 0
    for match in dr._DIEU_TAG.finditer(page):  # noqa: SLF001
        if match.group(1) != "/":
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
    return dict(dr.parse_articles(page[:start] if depth else page))


def attached_article(page: str, part: str, number: str) -> str:
    """Điều `number` of a document attached to the page (a Quy chế issued by a Quyết định), whose articles carry no
    <dieu> element: in the page text after the first line reading exactly `part`, from the article's heading line
    up to the next article, chapter, section or annex heading."""
    lines = dr.html_to_text(dr._NON_CONTENT.sub("", page)).splitlines()  # noqa: SLF001
    if part not in lines:
        raise _fail(f"no line {part!r} on the stored page")
    after = lines.index(part) + 1
    heads = [index for index in range(after, len(lines))
             if (head := dr._ARTICLE_HEAD.match(lines[index])) and head.group(1).lower() == number]  # noqa: SLF001
    if not heads:
        raise _fail(f"no Điều {number} after the line {part!r}")
    end = next((index for index in range(heads[0] + 1, len(lines)) if _PART_STOP.match(lines[index])), len(lines))
    return "\n".join(lines[heads[0]:end])


def provision_text(page: str, article: str, clauses: list[str], max_chars: int = 6000,
                   part: str | None = None) -> tuple[str, str]:
    """(locator, verbatim text): the whole article, or, when it exceeds `max_chars`, its heading line and the
    named clauses in page order. Named clauses must exist even in an article within the limit, whose unit is then
    still the whole article: a missing clause means the location points at the wrong article. With `part`, the
    article belongs to the document attached under that heading line."""
    number = str(article).strip().lower().removeprefix("điều").strip()
    if part:
        text, prefix = attached_article(page, part, number), f"{part.capitalize()} kèm theo, "
    else:
        found = page_articles(page)
        if number not in found:
            raise _fail(f"no Điều {number} on the stored page")
        text, prefix = found[number], ""
    if not clauses:
        if len(text) > max_chars:
            raise _fail(f"Điều {number} has {len(text)} characters, over {max_chars}: name its clauses")
        return f"{prefix}Điều {number}", text
    wanted = [str(clause).strip() for clause in clauses]
    lines = text.splitlines()
    blocks: dict[str, list[str]] = {}
    current = None
    for line in lines[1:]:
        match = _CLAUSE.match(line)
        if match:
            current = match.group(1)
            if current in blocks:
                raise _fail(f"Điều {number} repeats clause {current}")
            blocks[current] = []
        if current is not None:
            blocks[current].append(line)
    missing = [clause for clause in wanted if clause not in blocks]
    if missing:
        raise _fail(f"Điều {number} has no clause {missing}")
    if len(text) <= max_chars:
        return f"{prefix}Điều {number}", text
    kept = [clause for clause in blocks if clause in wanted]  # page order
    body = "\n".join(line for clause in kept for line in blocks[clause])
    return f"{prefix}Điều {number}, khoản {', '.join(kept)}", lines[0] + "\n" + body


def build_provisions(found: dict[str, Any], sources_dir: Path = SOURCES_DIR, max_provisions: int = 2,
                     max_chars: int = 6000) -> list[dict[str, Any]]:
    provisions = []
    for located in found["provisions"][:max_provisions + 1]:
        if not located["url"].startswith("https://hethongphapluat.com/"):
            raise _fail(f"{found['item_id']}: provisions come from hethongphapluat.com only")
        locator, text = provision_text(stored_page(located["url"], sources_dir), located["article"],
                                       located.get("clauses") or [], max_chars, located.get("part"))
        provisions.append({"doc_id": str(located["doc_id"]).strip(), "doc_title": str(located["doc_title"]).strip(),
                           "locator": locator, "text": text, "text_sha256": v1.sha256_bytes(text.encode("utf-8")),
                           "source_ref": located["url"]})
    if len(provisions) > max_provisions:
        raise _fail(f"{found['item_id']}: more than {max_provisions} provisions")
    return dp.validate_provisions(provisions, found["item_id"], verbatim_source=True) if provisions else []


def build_evidence(found_rows: list[dict[str, Any]], strata: dict[str, list[str]], *, sources_dir: Path = SOURCES_DIR,
                   max_provisions: int = 2, max_chars: int = 6000) -> list[dict[str, Any]]:
    """Draft evidence records, one per selected item, in item-id order; fails closed on a gap or a duplicate."""
    selected = {item for items in strata.values() for item in items}
    by_item: dict[str, dict[str, Any]] = {}
    for row in found_rows:
        if row["item_id"] in by_item:
            raise _fail(f"two located rows for {row['item_id']}")
        by_item[row["item_id"]] = row
    if set(by_item) != selected:
        raise _fail(f"located rows differ from the selection: missing {sorted(selected - set(by_item))[:5]}, "
                    f"extra {sorted(set(by_item) - selected)[:5]}")
    records = []
    for item_id in sorted(selected):
        row = by_item[item_id]
        if row["support"] not in SUPPORT:
            raise _fail(f"{item_id}: unknown support label {row['support']!r}")
        provisions = build_provisions(row, sources_dir, max_provisions, max_chars)
        if (row["support"] == "not_found") != (not provisions):
            raise _fail(f"{item_id}: not_found goes with no provision, every other label with at least one")
        records.append({"dataset_id": DATASET, "item_id": item_id, "provisions": provisions,
                        "support": row["support"], "label_source": "agent", "located_by": row["located_by"]})
    return records


def review_sample(records: list[dict[str, Any]], size: int) -> list[str]:
    with_provision = [record["item_id"] for record in records if record["provisions"]]
    return sorted(_hash_order(with_provision, REVIEW_SALT)[:size])


def apply_review(records: list[dict[str, Any]], review: dict[str, Any], sample: list[str]) -> list[dict[str, Any]]:
    """The owner's label replaces the agent's on the reviewed items; the review must cover the whole sample."""
    labels = review.get("labels") or {}
    if sorted(labels) != sorted(sample):
        raise _fail(f"the review must label exactly the {len(sample)} sampled items")
    if not str(review.get("reviewer") or "").strip():
        raise _fail("the review names no reviewer")
    final = []
    for record in records:
        label = labels.get(record["item_id"])
        if label is None:
            final.append(record)
            continue
        if label not in SUPPORT or (label == "not_found") != (not record["provisions"]):
            raise _fail(f"{record['item_id']}: review label {label!r} does not fit the record")
        final.append({**record, "support": label, "label_source": f"owner:{review['reviewer']}"})
    return final


def load_evidence(path: Path = EVIDENCE_PATH, strata: dict[str, list[str]] | None = None) -> dict[str, dict[str, Any]]:
    """{item_id: record}; fails closed on shape, leakage, an unselected item or a duplicate."""
    selected = {item for items in (strata or {}).values() for item in items}
    result: dict[str, dict[str, Any]] = {}
    for number, record in enumerate(_read_jsonl(path, "oracle evidence"), 1):
        where = f"{path.name}:{number}"
        if set(record) != set(EVIDENCE_KEYS) or dp.FORBIDDEN_EVIDENCE_KEYS & set(record):
            raise _fail(f"{where}: record must have exactly the keys {list(EVIDENCE_KEYS)}")
        if record["dataset_id"] != DATASET or record["support"] not in SUPPORT:
            raise _fail(f"{where}: wrong dataset or support label")
        if record["item_id"] in result or (selected and record["item_id"] not in selected):
            raise _fail(f"{where}: duplicate or unselected item {record['item_id']}")
        if record["provisions"]:
            dp.validate_provisions(record["provisions"], where, verbatim_source=True)
        elif record["support"] != "not_found":
            raise _fail(f"{where}: a record without provisions must be not_found")
        result[record["item_id"]] = record
    if selected and set(result) != selected:
        raise _fail(f"the evidence file covers {len(result)} of {len(selected)} selected items")
    return result


# ---------------------------------------------------------------- manifest

def build_manifest(protocol_path: Path = PROTOCOL_PATH, evidence_path: Path = EVIDENCE_PATH
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. Item-major: item, draw, arm; O only for items with evidence."""
    protocol = load_protocol(protocol_path)
    strata = select_items(protocol)
    evidence = load_evidence(evidence_path, strata)
    templates = dp.load_templates()
    frozen = legal_items()
    items: list[v1.EvalItem] = []
    for item_id in sorted(evidence):
        base = frozen[item_id]
        provisions = evidence[item_id]["provisions"]
        prompts = {"B": base.prompt}
        if provisions:
            prompts["O"] = dp.build_arm_prompt(base, "O", templates, provisions)
        for draw in range(1, protocol["draws"] + 1):
            for arm in ARMS:
                if arm in prompts:
                    items.append(dataclasses.replace(base, replicate_id=f"{arm}-r{draw}", prompt=prompts[arm]))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate legal-oracle run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "legal_oracle_protocol_sha256": v1.sha256_file(protocol_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "evidence_sha256": v1.sha256_file(evidence_path),
        "source_sha256": source_sha256(protocol),
        "strata": strata,
        "support": {item_id: evidence[item_id]["support"] for item_id in sorted(evidence)},
        "n": len(items), "item_count": len(evidence),
        "dataset_counts": {DATASET: len(evidence)},
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return _read_json(path, "frozen legal-oracle manifest")


# ---------------------------------------------------------------- review sheet

def review_sheet(records: list[dict[str, Any]], sample: list[str], worklist: dict[str, dict[str, Any]],
                 found: dict[str, dict[str, Any]]) -> str:
    lines = ["# Căn cứ pháp lý cho Legal MC: phần chủ đề tài kiểm tra", "",
             "Với mỗi câu, bạn đọc đề, các lựa chọn, đáp án gold và điều luật agent tìm được, rồi chọn một nhãn:",
             "- `supports_gold`: đọc điều luật theo nghĩa thông thường thì đáp án gold đúng và các lựa chọn khác sai;",
             "- `contradicts_gold`: điều luật cho thấy một lựa chọn khác mới đúng;",
             "- `unclear`: điều luật có liên quan nhưng không đủ để chọn ra một đáp án, hoặc không điều chỉnh câu hỏi.",
             "", "Nhãn và ghi chú của agent (tiếng Anh) chỉ để tham khảo. Nhãn của bạn sẽ thay nhãn của agent ở các câu "
             "này. Gửi lại mã câu và nhãn của bạn cho đủ các câu, kèm tên người chấm.", ""]
    by_item = {record["item_id"]: record for record in records}
    for number, item_id in enumerate(sample, 1):
        record, row, located = by_item[item_id], worklist[item_id], found[item_id]
        lines += [f"## {number}. {item_id}", "", "```text", row["prompt"].strip(), "```", "",
                  f"**Đáp án gold:** {row['gold']}  ",
                  f"**Nhãn của agent:** `{record['support']}`. {located.get('rationale', '')}",
                  *([f"**Ghi chú phiên bản (agent):** {located['version_note']}"] if located.get("version_note") else []),
                  ""]
        for index, provision in enumerate(record["provisions"], 1):
            lines += [f"**[{index}] {provision['doc_title']} — {provision['locator']}** ({provision['source_ref']})",
                      "", "```text", provision["text"], "```", ""]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Legal MC oracle-evidence test (offline helpers).")
    sub = ap.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select", help="print the item selection")
    select.add_argument("--worklist", type=Path, help="also write question, prompt and gold of each item here")
    evidence = sub.add_parser("evidence", help="build the draft evidence records and the owner review sheet")
    evidence.add_argument("--found", type=Path, nargs="+", required=True, help="the agents' located rows (jsonl)")
    evidence.add_argument("--worklist", type=Path, required=True, help="the worklist written by `select`")
    freeze = sub.add_parser("freeze-evidence", help="apply the owner review and freeze the evidence file")
    freeze.add_argument("--review", type=Path, required=True, help='{"reviewer": ..., "labels": {item_id: label}}')
    manifest = sub.add_parser("manifest", help="build the manifest and compare it with the frozen one")
    manifest.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    protocol = load_protocol()
    strata = select_items(protocol)
    if args.command == "select":
        print(" ".join(f"{name}={len(items)}" for name, items in strata.items()))
        if args.worklist:
            items = legal_items()
            rows = [{"item_id": item_id, "stratum": name, "question": items[item_id].question,
                     "prompt": items[item_id].prompt, "gold": items[item_id].gold_answer}
                    for name in STRATA for item_id in strata[name]]
            args.worklist.parent.mkdir(parents=True, exist_ok=True)
            args.worklist.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"worklist -> {args.worklist} ({len(rows)} items, with gold: keep it out of the repository)")
    elif args.command == "evidence":
        found_rows = []
        for path in args.found:
            batch = path.stem.rsplit("_", 1)[-1]
            found_rows += [{**row, "located_by": f"agent-batch-{batch}"} for row in _read_jsonl(path, "located rows")]
        records = build_evidence(found_rows, strata, max_provisions=protocol["evidence"]["max_provisions"],
                                 max_chars=protocol["evidence"]["max_article_chars"])
        sample = review_sample(records, protocol["evidence"]["review"]["size"])
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        v1.write_jsonl_atomic(EVIDENCE_DIR / "evidence_draft.jsonl", records)
        worklist = {row["item_id"]: row for row in _read_json(args.worklist, "worklist")}
        found = {row["item_id"]: row for row in found_rows}
        (EVIDENCE_DIR / "review_sheet.md").write_text(review_sheet(records, sample, worklist, found), encoding="utf-8")
        (EVIDENCE_DIR / "review_sample.json").write_text(json.dumps(sample) + "\n", encoding="utf-8")
        print(f"draft records={len(records)} support={dict(Counter(record['support'] for record in records))}")
        print(f"review sample ({len(sample)}): {' '.join(sample)}")
        print(f"sheet -> {EVIDENCE_DIR / 'review_sheet.md'}")
    elif args.command == "freeze-evidence":
        if EVIDENCE_PATH.exists():
            raise _fail(f"{EVIDENCE_PATH} is frozen; delete it deliberately to rebuild")
        records = _read_jsonl(EVIDENCE_DIR / "evidence_draft.jsonl", "evidence draft")
        sample = review_sample(records, protocol["evidence"]["review"]["size"])
        review = _read_json(args.review, "owner review")
        final = apply_review(records, review, sample)
        agent = {record["item_id"]: record["support"] for record in records}
        agreed = sum(agent[item] == label for item, label in review["labels"].items())
        v1.write_jsonl_atomic(EVIDENCE_PATH, final)
        load_evidence(EVIDENCE_PATH, strata)
        print(f"agent-owner agreement {agreed}/{len(sample)}; final support "
              f"{dict(Counter(record['support'] for record in final))}")
        print(f"frozen -> {EVIDENCE_PATH} sha256={v1.sha256_file(EVIDENCE_PATH)}")
        print(f"owner review {args.review} sha256={v1.sha256_file(args.review)}")
    else:
        built, _ = build_manifest()
        print(f"legal-oracle manifest {built['manifest_sha256']}: {built['n']} attempts {built['arm_counts']}")
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
