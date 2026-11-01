#!/usr/bin/env python3
"""Build corpus v0 for arms K and KS of the prospective diagnostic campaign (task 7.2).

    .venv/bin/python -m code_benchmark.build_diagnostic_corpus --fetch \
        --oracle-evidence all_res/diagnostic_prospective/oracle/oracle_evidence_v1.jsonl

Reads the tracked document list (data/diagnostic_prospective_v1/corpus_v0_sources.json). With --fetch, a page
that is not yet under all_res/diagnostic_prospective/corpus_v0/raw/ is downloaded once and logged with its
SHA-256 and retrieval time; a stored page is never fetched again. Every document is chunked by article into
corpus.jsonl, with manifest.json and checks.json beside it. Exits non-zero when a Legal MC question or an
answer-key line occurs in the corpus. With --oracle-evidence, each oracle provision is also looked up in the
article it cites, as a check of the article split.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import vi_multimodel as v1


def _raw_name(doc_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", doc_id).strip("_") + ".html"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def stored_pages(sources: dict, out: Path, fetch: bool) -> dict[str, dict]:
    """{doc_id: {"path", "raw_sha256", "retrieved_at"}}, fetching missing pages only when asked."""
    raw_dir, log_path = out / "raw", out / "fetch_log.jsonl"
    names = {document["doc_id"]: _raw_name(document["doc_id"]) for document in sources["documents"]}
    if len(set(names.values())) != len(names):
        raise SystemExit("Error: two doc_ids map to the same raw file name")
    log = {}
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                log[entry["doc_id"]] = entry
    raw_dir.mkdir(parents=True, exist_ok=True)
    pages = {}
    for document in sources["documents"]:
        path = raw_dir / names[document["doc_id"]]
        if not path.exists():
            if not fetch:
                raise SystemExit(f"Error: no stored page for {document['doc_id']}; pass --fetch")
            body = dr.fetch(document["url"])
            if not body:
                raise SystemExit(f"Error: {document['url']} returned an empty body")
            path.write_bytes(body)
            entry = {"doc_id": document["doc_id"], "url": document["url"], "bytes": len(body),
                     "sha256": v1.sha256_bytes(body), "retrieved_at": datetime.now(timezone.utc).isoformat()}
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            log[document["doc_id"]] = entry
            print(f"  fetched {document['doc_id']}: {len(body)} bytes")
            time.sleep(1.0)
        digest = v1.sha256_file(path)
        if document["doc_id"] not in log or log[document["doc_id"]]["sha256"] != digest:
            raise SystemExit(f"Error: {path.name} differs from its fetch log entry")
        pages[document["doc_id"]] = {"path": path, "raw_sha256": digest,
                                     "retrieved_at": log[document["doc_id"]]["retrieved_at"]}
    return pages


def main() -> None:
    ap = argparse.ArgumentParser(description="Build corpus v0 (fetch once, chunk by article, check for leakage).")
    ap.add_argument("--sources", type=Path, default=dr.SOURCES_PATH, help="tracked document list")
    ap.add_argument("--out", type=Path, default=dr.CORPUS_DIR, help=f"output folder (default: {dr.CORPUS_DIR})")
    ap.add_argument("--fetch", action="store_true", help="download pages that are not stored yet")
    ap.add_argument("--oracle-evidence", type=Path, help="oracle records to look up in the corpus (a check)")
    ap.add_argument("--overwrite", action="store_true",
                    help="rebuild an existing corpus; only before the core registration binds its hash")
    args = ap.parse_args()
    if (args.out / "corpus.jsonl").exists() and not args.overwrite:
        raise SystemExit(f"Error: {args.out / 'corpus.jsonl'} exists; pass --overwrite to rebuild it")
    sources, sources_sha256 = dr.load_sources(args.sources)
    pages = stored_pages(sources, args.out, args.fetch)
    chunks, documents = [], []
    for document in sources["documents"]:
        page = pages[document["doc_id"]]
        doc_chunks = dr.document_chunks(document, page["path"].read_text(encoding="utf-8"))
        chunks += doc_chunks
        documents.append({**document, "raw_file": page["path"].name, "raw_sha256": page["raw_sha256"],
                          "retrieved_at": page["retrieved_at"], "articles": len(doc_chunks),
                          "chars": sum(len(chunk["text"]) for chunk in doc_chunks)})
    if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
        raise SystemExit("Error: duplicate chunk ids across documents")
    corpus_bytes = "".join(json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n" for chunk in chunks).encode()
    protocol = dp.load_protocol()
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    legal = [item for item in main_items.values() if item.dataset_id in protocol["evidence"]["eligible_datasets"]]
    checks = {"leak": dr.leak_report(chunks, legal)}
    if args.oracle_evidence:
        checks["oracle_crosscheck"] = dr.oracle_crosscheck(
            chunks, dp.load_oracle_evidence(args.oracle_evidence, protocol, main_items))
    manifest = {"corpus_id": sources["corpus_id"], "version": sources["version"], "unit": sources["unit"],
                "built_at": datetime.now(timezone.utc).isoformat(), "sources_sha256": sources_sha256,
                "corpus_sha256": v1.sha256_bytes(corpus_bytes), "chunks": len(chunks),
                "chars": sum(len(chunk["text"]) for chunk in chunks), "documents": documents,
                "omitted": sources.get("omitted", []), "leak_check_passed": checks["leak"]["passed"]}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "corpus.jsonl").write_bytes(corpus_bytes)
    _write_json(args.out / "manifest.json", manifest)
    _write_json(args.out / "checks.json", checks)
    for document in documents:
        print(f"  {document['role']:11} {document['doc_id']:16} {document['articles']:4} articles "
              f"{document['chars']:>8} chars")
    print(f"{len(chunks)} articles from {len(documents)} documents -> {args.out}")
    print(f"corpus_sha256 {manifest['corpus_sha256']}")
    leak = checks["leak"]
    print(f"leak check: {'passed' if leak['passed'] else 'FAILED'} ({leak['items_checked']} Legal MC items; "
          f"questions {len(leak['questions_in_corpus'])}, answer-key chunks {len(leak['answer_key_chunks'])}, "
          f"options copied verbatim {leak['options_verbatim_in_corpus']})")
    if "oracle_crosscheck" in checks:
        cross = checks["oracle_crosscheck"]
        print(f"oracle provisions found in their cited articles: {cross['all_found']} ({cross['provisions']})")
    if not leak["passed"]:
        raise SystemExit("Error: benchmark text found in the corpus; see checks.json")


if __name__ == "__main__":
    main()
