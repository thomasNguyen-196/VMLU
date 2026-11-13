"""The registered analysis of MC-112, Qwen in DeepSeek Harness over the legal corpus folder (plan
diagnostic-legal-agent-v1; openspec change diagnostic-legal-agent).

Run once, after every attempt is final:
  .venv/bin/python -m code_benchmark.analyze_legal_agent --run-dir all_res/diagnostic_legal_agent/run/<profile>

* Item score: the mean correctness over two draws (0, 0.5 or 1). MC-111's B and O come from its round-1 score file,
  by the SHA-256 the protocol registers.
* Questions on the 134 items, Holm over the three p-values at α 0.05: (1) DSHF against DSH; (2) DSH against MC-111's
  B; (3) DSHF against MC-111's B. Each: the mean per-item difference, a 95% percentile bootstrap (2,000 resamples,
  seed 7) and a two-sided paired sign-flip p (20,000 resamples, seed 7).
* Reading rule: (1) forcing helps (hurts) when DSHF's mean exceeds (trails) DSH's with adjusted p < α. (2), (3) an arm
  beats (is worse than) B only when its mean exceeds (trails) B's by more than the registered margin (2.24 points,
  the gap between MC-101's and MC-111's B) with adjusted p < α; otherwise there is no clear difference and B stays the
  Legal MC route.
* Description: behaviour per arm (searched, tool calls, requests, tokens, outcomes, share answering A); retrieval
  hits `seen`, `read` and `opened` against the frozen provisions, read from what reached the model; accuracy when the
  governing provision was read and when it was not (supports_gold items); each arm against MC-111's O on its items;
  answers on contradicts_gold and unclear items; MC-111's round-1 arms for context.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import analyze_diagnostic_prospective as adp
    from code_benchmark import analyze_legal_oracle as alo
    from code_benchmark import analyze_legal_retrieval as alr
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as adp  # type: ignore[no-redef]
    import analyze_legal_oracle as alo  # type: ignore[no-redef]
    import analyze_legal_retrieval as alr  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_oracle as lo  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-legal-agent-v1"
DRAWS = alr.DRAWS
HITS = ("seen", "read", "opened")
REPORT_FILE = "legal_agent_report.json"


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_reference(cells: dict[str, dict[str, dict[str, Any]]], reference: list[dict[str, Any]],
                  arms: tuple[str, ...] = ("B", "O", "K", "K10")) -> None:
    """Put MC-111's rows for `arms` into the cells as B1, B2, O1, ... (every pool item must have both B draws)."""
    for row in reference:
        arm, _, draw = str(row["replicate_id"]).partition("-r")
        if arm in arms and row["item_id"] in cells:
            cells[row["item_id"]][f"{arm}{draw}"] = row
    missing = [item for item, cell in cells.items() if not all(f"B{draw}" in cell for draw in DRAWS)]
    if missing:
        raise _fail(f"MC-111's B is missing for {missing[:3]}")


def questions(pool: list[str], cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    blocks = {"DSHF_vs_DSH": alr.compare(pool, cells, "DSHF", "DSH"),
              "DSH_vs_B": alr.compare(pool, cells, "DSH", "B"),
              "DSHF_vs_B": alr.compare(pool, cells, "DSHF", "B")}
    short = [name for name, block in blocks.items() if block["n"] != len(pool)]
    if short:
        raise _fail(f"the comparisons {short} do not cover all {len(pool)} items")
    return blocks


def rules(blocks: dict[str, dict[str, Any]], alpha: float, margin: float) -> dict[str, Any]:
    tests = {name: block[f"{name.split('_vs_')[0]}_versus_{name.split('_vs_')[1]}"] for name, block in blocks.items()}
    adjusted = adp.holm_adjust({name: test["sign_flip_p"] for name, test in tests.items()})
    out: dict[str, Any] = {"alpha": alpha, "multiplicity": "holm", "margin_points": margin}
    for name, test in tests.items():
        mean, p = test["mean_points"], adjusted[name]
        entry = {"mean_points": mean, "sign_flip_p": test["sign_flip_p"], "p_holm": round(p, 6)}
        if name == "DSHF_vs_DSH":
            entry["reading"] = ("forcing search helps" if mean > 0 and p < alpha else
                                "forcing search hurts" if mean < 0 and p < alpha else "no clear effect of forcing")
        else:
            arm = name.split("_vs_")[0]
            entry["beats_B"] = mean > margin and p < alpha
            entry["worse_than_B"] = mean < -margin and p < alpha
            entry["reading"] = (f"{arm} beats B" if entry["beats_B"] else f"{arm} is worse than B"
                                if entry["worse_than_B"] else f"no clear difference between {arm} and B")
        out[name] = entry
    out["legal_mc_route"] = next((arm for arm in ("DSHF", "DSH") if out[f"{arm}_vs_B"]["beats_B"]), "B")
    return out


def load_attempt_records(run_dir: Path, row: dict[str, Any]) -> list[dict[str, Any]]:
    path = run_dir / str(row.get("attempt_dir") or "") / "proxy_log.jsonl"
    return _read_jsonl(path) if row.get("attempt_dir") and path.is_file() else []


def attempt_hits(run_dir: Path, cells: dict[str, dict[str, dict[str, Any]]],
                 provisions: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, bool]]]:
    """{item: {"DSH1": {"seen", "read", "opened"}, ...}}: any of the item's provisions, per attempt."""
    out: dict[str, dict[str, dict[str, bool]]] = {}
    for item, cell in cells.items():
        for arm in la.ARMS:
            for draw in DRAWS:
                observations = la.model_observations(load_attempt_records(run_dir, cell[f"{arm}{draw}"]))
                per = la.provision_hits(observations, provisions[item]["provisions"])
                out.setdefault(item, {})[f"{arm}{draw}"] = {kind: any(p[kind] for p in per) for kind in HITS}
    return out


def behaviour(cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    out = {}
    for arm in la.ARMS:
        rows = [cell[f"{arm}{draw}"] for cell in cells.values() for draw in DRAWS]
        tools: Counter[str] = Counter()
        for row in rows:
            tools.update(row.get("tool_calls") or {})
        searched = [bool(row.get("tool_calls")) for row in rows]
        out[arm] = {
            "attempts": len(rows), "searched_share": round(statistics.fmean(searched), 4),
            "tool_calls_per_attempt": {name: round(count / len(rows), 3) for name, count in sorted(tools.items())},
            "requests_per_attempt": round(statistics.fmean(int(row.get("requests") or 0) for row in rows), 3),
            "outcomes": dict(sorted(Counter(str(row.get("outcome")) for row in rows).items())),
            "share_answering_A": alo.letter_share(cells, arm), "mean_tokens": alo.token_means(cells, arm),
        }
    return out


def retrieval(pool: list[str], oracle_items: list[str], hits: dict[str, dict[str, dict[str, bool]]]) -> dict[str, Any]:
    def rate(items: list[str], arm: str, kind: str) -> float:
        return _pct(statistics.fmean(float(hits[item][f"{arm}{draw}"][kind]) for item in items for draw in DRAWS))
    return {scope: {"n_items": len(items),
                    **{arm: {kind: rate(items, arm, kind) for kind in HITS} for arm in la.ARMS}}
            for scope, items in (("pool", pool), ("mc100_oracle_items", oracle_items))}


def by_retrieval(cells: dict[str, dict[str, dict[str, Any]]], hits: dict[str, dict[str, dict[str, bool]]],
                 support: dict[str, str]) -> dict[str, Any]:
    """On supports_gold items: attempt-level accuracy when the governing provision was read and when it was not."""
    out = {}
    for arm in la.ARMS:
        groups: dict[str, list[float]] = {"read": [], "not_read": []}
        for item, cell in cells.items():
            if support[item] != "supports_gold":
                continue
            for draw in DRAWS:
                key = "read" if hits[item][f"{arm}{draw}"]["read"] else "not_read"
                groups[key].append(float(cell[f"{arm}{draw}"]["correct"]))
        out[arm] = {name: {"attempts": len(values), "accuracy": _pct(statistics.fmean(values)) if values else None}
                    for name, values in groups.items()}
    return out


def gold_check(cells: dict[str, dict[str, dict[str, Any]]], support: dict[str, str],
               owner: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label in ("contradicts_gold", "unclear"):
        items = sorted(item for item, value in support.items() if value == label)
        picks = {}
        for arm in (*la.ARMS, "B"):
            chosen = [(str(cells[item][f"{arm}{draw}"].get("prediction") or ""),
                       str(cells[item][f"{arm}{draw}"]["gold_answer"]), owner.get(item))
                      for item in items for draw in DRAWS]
            gold = sum(pick == g for pick, g, _ in chosen)
            own = sum(o is not None and pick == o and pick != g for pick, g, o in chosen)
            picks[arm] = {"answers": len(chosen), "gold_option": gold, "owner_option": own,
                          "other": len(chosen) - gold - own}
        out[label] = {"items": items, "picks": picks}
    return out


def build_report(run_dir: Path) -> dict[str, Any]:
    protocol = la.load_protocol()
    manifest = la.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    scores = _read_jsonl(scores_path)
    by_key = {dp.run_key(row): row for row in scores}
    unfinished = [dp.run_key(ref) for ref in manifest["items"]
                  if (by_key.get(dp.run_key(ref)) or {}).get("status") not in (None, "complete")]
    if unfinished:
        raise _fail(f"{len(unfinished)} attempts are not final, e.g. {unfinished[:3]}; resume the run first")
    cells = alr.load_cells(scores, manifest)
    reference = la.load_reference(protocol)
    add_reference(cells, reference)
    pool, support = manifest["pool"], manifest["support"]
    provisions = la.load_provisions()
    oracle_items = sorted(item for item in pool if provisions[item]["located_by"].startswith("mc100:"))
    blocks = questions(pool, cells)
    analysis = protocol["analysis"]
    hits = attempt_hits(run_dir, cells, provisions)
    with_o = [item for item in pool if "O1" in cells[item]]
    owner = alo.owner_answers(json.loads(lo.REGISTRATION_PATH.read_text(encoding="utf-8")))
    return {
        "plan_id": PLAN_ID, "card_id": "MC-112", "manifest_sha256": manifest["manifest_sha256"],
        "scores_sha256": v1.sha256_file(scores_path), "reference_scores_sha256": protocol["reference"]["scores_sha256"],
        "questions": blocks,
        "rules": rules(blocks, analysis["alpha"], analysis["margin_points"]),
        "behaviour": behaviour(cells),
        "retrieval": retrieval(pool, oracle_items, hits),
        "by_retrieval": by_retrieval(cells, hits, support),
        "against_O": {arm: alr.compare(with_o, cells, arm, "O") for arm in la.ARMS},
        "gold_check": gold_check(cells, support, owner),
        "context": {"mc111_round1_pool": {arm: _pct(statistics.fmean(alr.arm_mean(cells[item], arm) for item in pool))
                                          for arm in ("B", "K", "K10")},
                    "mc111_O_on_its_items": _pct(statistics.fmean(alr.arm_mean(cells[item], "O") for item in with_o))},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(la.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
    if list(report) != registered:
        raise _fail(f"report keys {list(report)} differ from the registered {registered}")
    out = args.run_dir / "analysis" / REPORT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, block in report["questions"].items():
        left, right = name.split("_vs_")
        print(f"{name}: n={block['n']} {left}={block[left]} {right}={block[right]} "
              f"diff={block[f'{left}_versus_{right}']['mean_points']} p={block[f'{left}_versus_{right}']['sign_flip_p']}")
    print(f"rules: {report['rules']}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
