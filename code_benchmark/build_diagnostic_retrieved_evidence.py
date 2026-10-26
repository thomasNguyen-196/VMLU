#!/usr/bin/env python3
"""Build the arm-K retrieved-evidence records and measure, once, whether the cited articles are retrieved (task 7.3).

    .venv/bin/python -m code_benchmark.build_diagnostic_retrieved_evidence \
        --oracle-evidence all_res/diagnostic_prospective/oracle/oracle_evidence_v1.jsonl

The records cover exactly the anchors of the oracle records, so arms O, K and KS run on the same items. Each
holds the top-k articles of corpus v0 under data/diagnostic_prospective_v1/retrieval_v0.json and the ranking
that produced them; the output is checked with the loader the runner uses for --retrieved-evidence. The hit
report states for each anchor whether an article the reviewer cited is in the top k and where each cited
article ranks overall. The configuration is fixed before the first run; a rerun needs --overwrite and keeps
the earlier report beside the new one.
"""
from __future__ import annotations

import argparse
import json
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

DEFAULT_OUT = dr.RETRIEVAL_DIR / "retrieved_evidence_v1.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the arm-K retrieved-evidence records (offline).")
    ap.add_argument("--oracle-evidence", type=Path, required=True,
                    help="oracle records; their anchors are the anchors that get retrieved evidence")
    ap.add_argument("--corpus", type=Path, default=dr.CORPUS_DIR, help=f"built corpus (default: {dr.CORPUS_DIR})")
    ap.add_argument("--config", type=Path, default=dr.CONFIG_PATH, help="retrieval configuration")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output JSONL (default: {DEFAULT_OUT})")
    ap.add_argument("--overwrite", action="store_true",
                    help="rebuild existing records; only before the core registration binds them")
    args = ap.parse_args()
    report_path = args.out.with_name("hit_at_k.json")
    if (args.out.exists() or report_path.exists()) and not args.overwrite:
        raise SystemExit(f"Error: {args.out} or {report_path.name} exists; pass --overwrite to rebuild")
    config, config_sha256 = dr.load_config(args.config)
    chunks, manifest = dr.load_corpus(args.corpus)
    index = dr.build_index(chunks, manifest, config, config_sha256)
    protocol = dp.load_protocol()
    main_items = v1.rebuild_items(protocol["parent"]["manifest_phase"])
    oracle = dp.load_oracle_evidence(args.oracle_evidence, protocol, main_items)
    required = protocol["evidence"]["required_input_evidence_sufficiency"]
    records = [dr.retrieved_record(index, main_items[f"{key}:{dp.MAIN_REPLICATE}"], required) for key in sorted(oracle)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records),
                   encoding="utf-8")
    loaded, _ = dp.load_retrieved_evidence(tmp, protocol, main_items)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "corpus_id": manifest["corpus_id"],
              "corpus_sha256": index.corpus_sha256, "retrieval_config_sha256": config_sha256,
              "oracle_evidence_sha256": v1.sha256_file(args.oracle_evidence),
              "evidence_sha256_k": dp.evidence_digest(loaded), **dr.hit_report(index, records, oracle, main_items)}
    if report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        stamp = str(previous.get("generated_at", "unknown")).replace(":", "")
        report_path.rename(report_path.with_name(f"hit_at_k.superseded-{stamp}.json"))
    tmp.replace(args.out)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    print(f"{len(loaded)} retrieved-evidence records -> {args.out}")
    print(f"evidence_sha256 (K) {report['evidence_sha256_k']}")
    print(f"corpus_sha256 {index.corpus_sha256} | retrieval_config_sha256 {config_sha256}")
    print(f"cited article in the top {report['top_k']}: {report['hits']}/{report['anchors']} anchors")
    for row in report["per_anchor"]:
        ranks = ", ".join(f"{chunk_id} @{rank}" for chunk_id, rank in row["rank_of_cited"].items())
        print(f"  {'hit ' if row['hit'] else 'MISS'} {row['item_key']}: cited {ranks} | top {row['retrieved']}")


if __name__ == "__main__":
    main()
