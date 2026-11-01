"""The registered analysis of the Legal MC oracle test (plan diagnostic-legal-oracle-v1; card MC-100).

Run once, after the run:
  .venv/bin/python -m code_benchmark.analyze_legal_oracle --run-dir all_res/diagnostic_legal_oracle/run/<profile>

* Item score: the mean correctness of an arm over its two draws (0, 0.5 or 1).
* Primary set: items whose final support label is `supports_gold`. Per stratum, O against fresh B: mean per-item
  difference with a percentile bootstrap interval (2,000 resamples, seed 7) and a two-sided sign-flip p-value
  (20,000 resamples, seed 7), plus clear rescues (O right on both draws, B wrong on both) and clear regressions.
* Reading rule: a retrieval study on Legal MC is worth building when O is at least 20 points above B in stratum
  `wrong` and at most 10 points below B in stratum `right`.
* Gold check (descriptive): the owner's option against the gold on the reviewed items, and, on items whose provision
  contradicts the gold, each arm's answers that pick the gold's option, the owner's option or another. The owner's
  review file stays outside the repository; it is read only when it carries the registered SHA-256.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import diagnostic_legal_oracle as lo
    import diagnostic_prospective as dp
    import vi_multimodel as v1

PLAN_ID = "diagnostic-legal-oracle-v1"
DRAWS = ("1", "2")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def load_cells(scores: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{item_id: {"B1": row, "B2": row, "O1": row, "O2": row}}; every manifest attempt must be scored."""
    by_key = {dp.run_key(row): row for row in scores}
    cells: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for ref in manifest["items"]:
        key = dp.run_key(ref)
        if key not in by_key:
            raise _fail(f"no scored row for {key}")
        arm, _, draw = ref["replicate_id"].partition("-r")
        cells[ref["item_id"]][f"{arm}{draw}"] = by_key[key]
    return dict(cells)


def arm_mean(cell: dict[str, dict[str, Any]], arm: str) -> float:
    return statistics.fmean(float(cell[f"{arm}{draw}"]["correct"]) for draw in DRAWS)


def stratum_block(item_ids: list[str], cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    with_o = [item for item in item_ids if "O1" in cells[item]]
    if not with_o:
        return {"n": 0}
    b = [arm_mean(cells[item], "B") for item in with_o]
    o = [arm_mean(cells[item], "O") for item in with_o]
    return {"n": len(with_o), "B": _pct(statistics.fmean(b)), "O": _pct(statistics.fmean(o)),
            "O_versus_B": arl.difference_block(o, b),
            "clear_rescues": sum(oi == 1.0 and bi == 0.0 for oi, bi in zip(o, b, strict=True)),
            "clear_regressions": sum(oi == 0.0 and bi == 1.0 for oi, bi in zip(o, b, strict=True))}


def reading_rule(wrong: dict[str, Any], right: dict[str, Any], rule: dict[str, float]) -> dict[str, Any]:
    gain = wrong["O_versus_B"]["mean_points"] if wrong.get("n") else None
    loss = right["O_versus_B"]["mean_points"] if right.get("n") else None
    fixes = gain is not None and gain >= rule["wrong_min_gain_points"]
    harmless = loss is not None and loss >= -rule["right_max_loss_points"]
    return {"wrong_gain_points": gain, "right_change_points": loss, "fixes_enough": fixes,
            "harmless_enough": harmless, "retrieval_study_worth_building": fixes and harmless}


def owner_answers(registration: dict[str, Any], root: Path = lo.ROOT) -> dict[str, str]:
    """{item_id: option} from the owner's review file, which must carry the SHA-256 the registration records."""
    entry = registration.get("owner_review") or {}
    path = root / str(entry.get("file") or "")
    if not path.is_file() or v1.sha256_file(path) != entry.get("sha256"):
        raise _fail(f"the owner review {path} is missing or differs from its registered SHA-256")
    return dict(json.loads(path.read_text(encoding="utf-8"))["answers"])


def gold_check(cells: dict[str, dict[str, dict[str, Any]]], support: dict[str, str], answers: dict[str, str]
               ) -> dict[str, Any]:
    gold = {item: str(cell["B1"]["gold_answer"]) for item, cell in cells.items()}
    reviewed = sorted(item for item in answers if item in gold)
    contradicted = sorted(item for item, label in support.items() if label == "contradicts_gold")
    picks = {}
    for arm in lo.ARMS:
        rows = [(item, cells[item][f"{arm}{draw}"]) for item in contradicted if item in answers
                for draw in DRAWS if f"{arm}{draw}" in cells[item]]
        chosen = [(str(row.get("prediction") or ""), item) for item, row in rows]
        gold_hits = sum(pick == gold[item] for pick, item in chosen)
        owner_hits = sum(pick == answers[item] for pick, item in chosen)
        picks[arm] = {"answers": len(chosen), "gold_option": gold_hits, "owner_option": owner_hits,
                      "other": len(chosen) - gold_hits - owner_hits}
    return {"reviewed": len(reviewed), "owner_equals_gold": sum(answers[item] == gold[item] for item in reviewed),
            "owner_differs": [item for item in reviewed if answers[item] != gold[item]],
            "contradicts_gold_items": contradicted,
            "contradicts_gold_without_owner_option": [item for item in contradicted if item not in answers],
            "contradicts_gold_picks": picks}


def letter_share(cells: dict[str, dict[str, dict[str, Any]]], arm: str, letter: str = "A") -> float | None:
    rows = [cell[f"{arm}{draw}"] for cell in cells.values() for draw in DRAWS if f"{arm}{draw}" in cell]
    return round(sum(str(row.get("prediction") or "") == letter for row in rows) / len(rows), 4) if rows else None


def token_means(cells: dict[str, dict[str, dict[str, Any]]], arm: str) -> dict[str, float | None]:
    rows = [cell[f"{arm}{draw}"] for cell in cells.values() for draw in DRAWS if f"{arm}{draw}" in cell]

    def mean(field: str) -> float | None:
        values = [row[field] for row in rows if isinstance(row.get(field), int)]
        return round(statistics.fmean(values), 1) if values else None
    return {"prompt": mean("prompt_tokens"), "completion": mean("completion_tokens"), "total": mean("total_tokens")}


def build_report(run_dir: Path) -> dict[str, Any]:
    protocol = lo.load_protocol()
    manifest = lo.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    scores = [json.loads(line) for line in scores_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cells = load_cells(scores, manifest)
    strata, support = manifest["strata"], manifest["support"]
    outcomes = lo.b_outcomes(protocol)
    primary = {name: [item for item in items if support[item] == "supports_gold"] for name, items in strata.items()}
    blocks = {name: stratum_block(items, cells) for name, items in primary.items()}
    missed_both = [item for item in primary["wrong"] if not any(outcomes[item])]
    missed_once = [item for item in primary["wrong"] if any(outcomes[item])]
    others = {label: {name: stratum_block([item for item in items if support[item] == label], cells)
                      for name, items in strata.items()}
              for label in ("contradicts_gold", "unclear")}
    evidence = lo.load_evidence(lo.EVIDENCE_PATH, strata)
    answers = owner_answers(json.loads(lo.REGISTRATION_PATH.read_text(encoding="utf-8")))
    return {
        "plan_id": PLAN_ID, "card_id": "MC-100", "manifest_sha256": manifest["manifest_sha256"],
        "evidence_sha256": manifest["evidence_sha256"], "scores_sha256": v1.sha256_file(scores_path),
        "support_counts": {name: dict(Counter(support[item] for item in items)) for name, items in strata.items()},
        "label_sources": dict(Counter(record["label_source"].split(":")[0] for record in evidence.values())),
        "primary": blocks,
        "reading_rule": reading_rule(blocks["wrong"], blocks["right"], protocol["analysis"]["reading_rule"]),
        "gold_check": gold_check(cells, support, answers),
        "descriptive": {
            "wrong_missed_on_both_earlier_draws": stratum_block(missed_both, cells),
            "wrong_missed_on_one_earlier_draw": stratum_block(missed_once, cells),
            "other_labels": others,
            "share_answering_A": {arm: letter_share(cells, arm) for arm in lo.ARMS},
            "mean_tokens": {arm: token_means(cells, arm) for arm in lo.ARMS},
            "evidence_chars": {
                "mean": round(statistics.fmean(sum(len(p["text"]) for p in record["provisions"])
                                               for record in evidence.values() if record["provisions"]), 1),
                "max": max(sum(len(p["text"]) for p in record["provisions"]) for record in evidence.values()),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(lo.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis" / "legal_oracle_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, block in report["primary"].items():
        if block.get("n"):
            print(f"{name}: n={block['n']} B={block['B']} O={block['O']} "
                  f"O-B={block['O_versus_B']['mean_points']} p={block['O_versus_B']['sign_flip_p']:.4f}")
    print(f"reading rule: {report['reading_rule']}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
