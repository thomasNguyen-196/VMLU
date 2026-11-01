"""The registered analysis of the router-critic's design check on reading items (plan diagnostic-router-critic-v1;
card MC-102).

Run once, after the critic run:
  .venv/bin/python -m code_benchmark.analyze_router_critic --run-dir all_res/diagnostic_router_loop/critic/<profile>

Every student answer is a logged draw-1 attempt of Qwen3.5-9B (B, S, Q of MC-90 to MC-92 and MC-97); the critic's
verdict and prescription choose among them.
* Policies: always-B, always-S, always-Q; the rule loop (B-r1 kept when it agrees with B-r2 under normalized-answer-v1,
  otherwise S-r1); the critic loop (on a `sai` verdict the prescribed arm's draw-1 answer, otherwise B-r1); the variant
  that also treats `khong_chac` as `sai`; Muse alone (MC-80/81 logged answers); the free proxy "Muse's logged answer
  differs from B-r1 -> S-r1"; the per-item bound over B, S and Q on draw 1.
* Primary: the critic loop against the rule loop on per-item token-F1 over the 376 items: mean difference with a
  percentile bootstrap interval (2,000 resamples, seed 7) and a two-sided sign-flip p-value (20,000 resamples, seed 7).
* Reading rule: the critic goes on to held-out reading items when it beats the rule loop by at least 1.0 point with
  p < 0.05; otherwise the reading critic stops at the design stage.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_router as router
    from code_benchmark import diagnostic_router_critic as critic
    from code_benchmark import simulate_router_loop as sim
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_router_labels as arl
    import diagnostic_router as router
    import diagnostic_router_critic as critic
    import simulate_router_loop as sim
    import vi_multimodel as v1

PLAN_ID = "diagnostic-router-critic-v1"
WIDE_GROUP = "wide (MC-90/91/92, MC-97)"
POLICIES = ("always_B", "always_S", "always_Q", "rule_loop", "critic_loop", "critic_unsure_as_wrong", "muse_alone",
            "muse_proxy", "bound")
CORRECT_F1 = 0.5


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def load_critic(run_dir: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in (run_dir / "critic.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return {f"{row['dataset_id']}:{row['item_id']}": row for row in rows}


def chosen_rows(cell: dict[str, dict[str, Any]], judged: dict[str, Any] | None, muse: dict[str, Any] | None,
                fixes: dict[str, str]) -> dict[str, dict[str, Any] | None]:
    """{policy: the selected answer row}; `bound` is filled by the caller (it maximizes per metric)."""
    first, probe = cell["B1"], cell["B2"]
    agree = router.answers_agree(str(first.get("prediction") or ""), str(probe.get("prediction") or ""), "reading")
    verdict = (judged or {}).get("verdict")
    arm = fixes.get((judged or {}).get("fix") or "", "B")
    muse_agrees = muse is not None and router.answers_agree(str(first.get("prediction") or ""),
                                                            str(muse.get("prediction") or ""), "reading")
    return {
        "always_B": first, "always_S": cell["S1"], "always_Q": cell["Q1"],
        "rule_loop": first if agree else cell["S1"],
        "critic_loop": cell[f"{arm}1"] if verdict == "sai" else first,
        "critic_unsure_as_wrong": cell[f"{arm}1"] if verdict in ("sai", "khong_chac") else first,
        "muse_alone": muse, "muse_proxy": first if muse_agrees else cell["S1"],
    }


def build_rows(manifest: dict[str, Any], critic_rows: dict[str, dict[str, Any]], cells: dict[tuple[str, str], Any],
               muse: dict[tuple[str, str], dict[str, Any]], fixes: dict[str, str]) -> list[dict[str, Any]]:
    """One record per manifest item: dataset, the critic row, and per policy the selected row's token-F1 and EM."""
    records = []
    for ref in manifest["items"]:
        key = (ref["dataset_id"], ref["item_id"])
        cell = cells.get(key)
        if cell is None or not all(arm in cell for arm in ("B1", "B2", "S1", "Q1")):
            raise _fail(f"{key}: the logged B, S and Q draws are incomplete")
        judged = critic_rows.get(f"{ref['dataset_id']}:{ref['item_id']}")
        rows = chosen_rows(cell, judged, muse.get(key), fixes)
        scores = {name: (float(row["token_f1"]), float(row["em"])) if row is not None else None
                  for name, row in rows.items()}
        draw1 = [cell[arm] for arm in ("B1", "S1", "Q1")]
        scores["bound"] = (max(float(row["token_f1"]) for row in draw1), max(float(row["em"]) for row in draw1))
        tokens = lambda row: float(row.get("total_tokens") or 0)  # noqa: E731
        agree = router.answers_agree(str(cell["B1"].get("prediction") or ""), str(cell["B2"].get("prediction") or ""),
                                     "reading")
        verdict, arm = (judged or {}).get("verdict"), fixes.get((judged or {}).get("fix") or "", "B")
        records.append({
            "dataset_id": ref["dataset_id"], "item_id": ref["item_id"], "judged": judged, "scores": scores,
            "b1_f1": float(cell["B1"]["token_f1"]), "b1_em": float(cell["B1"]["em"]),
            "fix_f1": float(cell[f"{arm}1"]["token_f1"]) if verdict == "sai" else None,
            "qwen_tokens": {"critic_loop": tokens(cell["B1"]) + (tokens(cell[f"{arm}1"]) if verdict == "sai" and arm != "B" else 0.0),
                            "rule_loop": tokens(cell["B1"]) + tokens(cell["B2"]) + (0.0 if agree else tokens(cell["S1"]))},
        })
    return records


def policy_block(records: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for name in POLICIES:
        present = [record["scores"][name] for record in records if record["scores"][name] is not None]
        if present:
            out[name] = {"n": len(present), "token_f1": round(100 * statistics.fmean(f1 for f1, _ in present), 2),
                         "em": round(100 * statistics.fmean(em for _, em in present), 2)}
    return out


def detector_block(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The critic's verdict against whether B-r1 was right (token-F1 >= 0.5), with exact match beside it."""
    table: Counter[tuple[str, str]] = Counter()
    for record in records:
        verdict = str((record["judged"] or {}).get("verdict"))
        table[(verdict, "right" if record["b1_f1"] >= CORRECT_F1 else "wrong")] += 1
    wrong = sum(count for (_, truth), count in table.items() if truth == "wrong")
    flagged = sum(count for (verdict, _), count in table.items() if verdict == "sai")
    caught = table[("sai", "wrong")]
    return {"table": {f"{verdict}|{truth}": count for (verdict, truth), count in sorted(table.items())},
            "b1_wrong": wrong, "flagged_sai": flagged, "caught": caught,
            "recall": round(caught / wrong, 4) if wrong else None,
            "precision": round(caught / flagged, 4) if flagged else None}


def prescription_block(records: list[dict[str, Any]], fixes: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fix_id in fixes:
        chosen = [record for record in records if (record["judged"] or {}).get("verdict") == "sai"
                  and (record["judged"] or {}).get("fix") == fix_id]
        out[fix_id] = {"n": len(chosen),
                       "rescued": sum(record["fix_f1"] > record["b1_f1"] for record in chosen),
                       "damaged": sum(record["fix_f1"] < record["b1_f1"] for record in chosen)}
    return out


def build_report(run_dir: Path) -> dict[str, Any]:
    config, _ = critic.load_config()
    manifest = critic.load_frozen_manifest()
    critic_path = run_dir / "critic.jsonl"
    critic_rows = load_critic(run_dir)
    paths = [sim.RUNS / directory / sim.PROFILE / "scores.jsonl" for directory in sim.GROUPS[WIDE_GROUP]]
    cells = sim.load_cells(paths)
    fixes = dict(config["prompt"]["fixes"])
    records = build_rows(manifest, critic_rows, cells, sim.load_strong(), fixes)
    critic_loop = [record["scores"]["critic_loop"][0] for record in records]
    rule_loop = [record["scores"]["rule_loop"][0] for record in records]
    primary = arl.difference_block(critic_loop, rule_loop)
    rule = config["analysis"]["reading_rule"]
    passed = primary["mean_points"] >= rule["min_gain_points"] and primary["sign_flip_p"] < rule["alpha"]
    judged = [record["judged"] for record in records if record["judged"] is not None]
    critic_tokens = [float(row.get("total_tokens") or 0) for row in judged]
    return {
        "plan_id": PLAN_ID, "card_id": "MC-102", "manifest_sha256": manifest["manifest_sha256"],
        "critic_sha256": v1.sha256_file(critic_path),
        "primary": {"n": len(records), "critic_loop": round(100 * statistics.fmean(critic_loop), 2),
                    "rule_loop": round(100 * statistics.fmean(rule_loop), 2), "critic_versus_rule": primary},
        "reading_rule": {"min_gain_points": rule["min_gain_points"], "alpha": rule["alpha"],
                         "critic_goes_on": passed},
        "by_dataset": {dataset: policy_block([record for record in records if record["dataset_id"] == dataset])
                       for dataset in sorted({record["dataset_id"] for record in records})} | {"pooled": policy_block(records)},
        "detector": {"pooled": detector_block(records),
                     **{dataset: detector_block([record for record in records if record["dataset_id"] == dataset])
                        for dataset in sorted({record["dataset_id"] for record in records})}},
        "prescription": prescription_block(records, fixes),
        "distributions": {"judged": len(judged), "missing": len(records) - len(judged),
                          "verdict": dict(Counter(str(row.get("verdict")) for row in judged)),
                          "cause": dict(Counter(str(row.get("cause")) for row in judged)),
                          "fix": dict(Counter(str(row.get("fix")) for row in judged)),
                          "format_ok": sum(bool(row.get("format_ok")) for row in judged),
                          "truncated": sum(row.get("incomplete_reason") == "max_output_tokens" for row in judged)},
        "cost": {"critic_tokens_mean": round(statistics.fmean(critic_tokens), 1) if critic_tokens else None,
                 "critic_tokens_total": sum(critic_tokens),
                 "qwen_tokens_mean": {name: round(statistics.fmean(record["qwen_tokens"][name] for record in records), 1)
                                      for name in ("critic_loop", "rule_loop")}},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(critic.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis" / "router_critic_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    primary = report["primary"]
    print(f"critic loop {primary['critic_loop']} vs rule loop {primary['rule_loop']}: "
          f"{primary['critic_versus_rule']['mean_points']} points, p={primary['critic_versus_rule']['sign_flip_p']:.4f}")
    print(f"reading rule: {report['reading_rule']}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
