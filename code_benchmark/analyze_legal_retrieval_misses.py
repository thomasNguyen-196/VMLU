"""Why MC-101's BM25 missed the MC-100 oracle article, and what a better document search could fix.

Post hoc and offline (no requests): the pre-check that turned step 3 of the plan from a web search into the
"chọn rồi trả lời" test (openspec change diagnostic-legal-select). Reads MC-100's frozen oracle evidence, MC-101's
corpus, configuration and scores.

Classes of the items with oracle provisions, by where the oracle article sits against BM25's top 2:
  hit           an oracle article is in the top 2
  doc_missing   no oracle document is in the corpus at all (only a new document source could help)
  unit_missing  the document is in the corpus, the cited article is not
  same_doc      the top 2 holds another article of an oracle document
  other_doc     the top 2 comes from other documents (a document filter could help)
The document-oracle ceiling ranks only the units of the oracle documents, as if a search had found exactly the
right law, and counts the hits at 2.

  .venv/bin/python -m code_benchmark.analyze_legal_retrieval_misses [--out <file.json>]
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_retrieval as dr
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_oracle as lo
    import diagnostic_legal_retrieval as lr
    import diagnostic_retrieval as dr

KINDS = ("hit", "doc_missing", "unit_missing", "same_doc", "other_doc")
SCORES_PATH = lr.WORK_ROOT / "run" / "qwen3-5-9b-65k-prospective" / "scores.jsonl"


def classify(targets: set[tuple[str, str, str]], ranked_units: list[tuple[str, str, str]],
             corpus_docs: set[str], corpus_units: set[tuple[str, str, str]]) -> dict[str, Any]:
    """One item: its class, the rank of its first oracle article and of its first oracle-document unit, and
    whether BM25 restricted to the oracle documents would hit at 2."""
    target_docs = {target[0] for target in targets}
    first_unit = next((rank for rank, unit in enumerate(ranked_units, 1) if unit in targets), None)
    first_doc = next((rank for rank, unit in enumerate(ranked_units, 1) if unit[0] in target_docs), None)
    restricted = [unit for unit in ranked_units if unit[0] in target_docs]
    if first_unit is not None and first_unit <= 2:
        kind = "hit"
    elif not target_docs & corpus_docs:
        kind = "doc_missing"
    elif not targets & corpus_units:
        kind = "unit_missing"
    elif any(unit[0] in target_docs for unit in ranked_units[:2]):
        kind = "same_doc"
    else:
        kind = "other_doc"
    return {"kind": kind, "unit_rank": first_unit, "doc_rank": first_doc,
            "doc_oracle_hit_at_2": any(unit in targets for unit in restricted[:2])}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(group: list[dict[str, Any]], arm: str) -> float | None:
        values = [row[arm] for row in group if row.get(arm) is not None]
        return round(100 * statistics.fmean(values), 1) if values else None
    kinds = Counter(row["kind"] for row in rows)
    gained = [row for row in rows if row["doc_oracle_hit_at_2"] and row["kind"] != "hit"]
    misses = [row for row in rows if row["kind"] != "hit"]
    return {
        "items": len(rows), "classes": {kind: kinds.get(kind, 0) for kind in KINDS},
        "by_class": {kind: {"n": len(group), **{arm: mean(group, arm) for arm in ("B", "K", "O")},
                            "oracle_article_rank_median": statistics.median(ranks) if ranks else None,
                            "within_10": sum(rank <= 10 for rank in ranks), "within_20": sum(rank <= 20 for rank in ranks)}
                     for kind in KINDS
                     for group in [[row for row in rows if row["kind"] == kind]]
                     for ranks in [[row["unit_rank"] for row in group if row["unit_rank"]]] if group},
        "misses_listed_by_corpus_agents": sum(row["agent_listed_target_doc"] for row in misses),
        "document_oracle_hit_at_2": sum(row["doc_oracle_hit_at_2"] for row in rows),
        "bm25_hit_at_2": kinds.get("hit", 0),
        "turned_into_hits_by_document_oracle": {"items": [row["item_id"] for row in gained],
                                                **{arm: mean(gained, arm) for arm in ("K", "O")}},
        "hits": {arm: mean([row for row in rows if row["kind"] == "hit"], arm) for arm in ("B", "K", "O")},
    }


def build_report(scores_path: Path = SCORES_PATH) -> dict[str, Any]:
    index = lr.load_index()
    mc100 = lr.mc100_frozen()
    frozen = lo.legal_items()
    sources = json.loads(lr.SOURCES_PATH.read_text(encoding="utf-8"))["documents"]
    listed_for = {lr.doc_key(document["doc_id"]): set(document.get("items") or []) for document in sources}
    corpus_docs = {lr.doc_key(chunk["doc_id"]) for chunk in index.chunks}
    corpus_units = {lr.unit_target(chunk["chunk_id"]) for chunk in index.chunks}
    accuracy: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for line in scores_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            accuracy[row["item_id"]][row["arm"]].append(float(row["correct"]))
    rows = []
    for item_id, record in sorted(mc100["oracle"].items()):
        if not record["provisions"]:
            continue
        targets = lr.oracle_targets(record["provisions"])
        ranked = [lr.unit_target(index.chunks[position]["chunk_id"])
                  for position, _ in dr.rank(index, dr.mc_query(frozen[item_id]))]
        rows.append({"item_id": item_id, "support": mc100["support"].get(item_id),
                     **classify(targets, ranked, corpus_docs, corpus_units),
                     "agent_listed_target_doc": any(item_id in listed_for.get(target[0], set()) for target in targets),
                     **{arm: (statistics.fmean(accuracy[item_id][arm]) if accuracy[item_id][arm] else None)
                        for arm in ("B", "K", "O")}})
    return {"post_hoc": True, "corpus_sha256": index.corpus_sha256, "summary": summarize(rows), "per_item": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None, help="write the full report as JSON")
    args = ap.parse_args(argv)
    report = build_report()
    summary = report["summary"]
    print(f"items {summary['items']}; classes {summary['classes']}")
    print(f"BM25 hit@2 {summary['bm25_hit_at_2']}; document-oracle hit@2 {summary['document_oracle_hit_at_2']}; "
          f"misses whose document the corpus agents listed for that item {summary['misses_listed_by_corpus_agents']}")
    print(f"turned into hits by a perfect document search: {summary['turned_into_hits_by_document_oracle']}")
    print(f"on hits: {summary['hits']}")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
