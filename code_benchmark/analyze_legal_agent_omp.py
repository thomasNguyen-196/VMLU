"""The registered analysis of MC-113, MC-112's forced-search task inside omp 18.0.0 (plan
diagnostic-legal-agent-omp-v1; openspec change diagnostic-legal-agent-omp).

Run once, after every attempt is final:
  .venv/bin/python -m code_benchmark.analyze_legal_agent_omp --run-dir all_res/diagnostic_legal_agent_omp/run/<profile>

* Item score: the mean correctness over two draws (0, 0.5 or 1). MC-112's DSHF (and DSH, for context) come from
  MC-112's score file, MC-111's B, O, K and K10 from MC-111's round-1 score file, each by registered SHA-256.
* Questions on the 134 items, Holm over the two p-values at α 0.05: (1) OMPF against MC-112's DSHF (the harness);
  (2) OMPF against MC-111's B. Each: the mean per-item difference, a 95% percentile bootstrap (2,000 resamples, seed
  7) and a two-sided paired sign-flip p (20,000 resamples, seed 7).
* Reading rule (both cross cards): OMPF beats (is worse than) the reference only when its mean exceeds (trails) the
  reference's by more than the registered margin (2.24 points) with adjusted p < α; otherwise there is no clear
  difference. B stays the Legal MC route unless OMPF beats B.
* Description: behaviour (tool calls, read selectors, grep pages, requests, compactions, tokens, outcomes, share
  answering A) beside DSHF; retrieval hits `seen`, `read` and `opened` from what reached the model, beside DSHF's on
  the same items, with the per-item paired difference (descriptive, not tested); accuracy when the governing
  provision was read and when it was not; OMPF against MC-111's O; answers on contradicts_gold and unclear items;
  MC-112's and MC-111's arms for context.
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
    from code_benchmark import analyze_legal_agent as ala
    from code_benchmark import analyze_legal_oracle as alo
    from code_benchmark import analyze_legal_retrieval as alr
    from code_benchmark import analyze_router_labels as arl
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import omp_trajectory as ot
    from code_benchmark import run_legal_agent_omp as ro
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import analyze_diagnostic_prospective as adp  # type: ignore[no-redef]
    import analyze_legal_agent as ala  # type: ignore[no-redef]
    import analyze_legal_oracle as alo  # type: ignore[no-redef]
    import analyze_legal_retrieval as alr  # type: ignore[no-redef]
    import analyze_router_labels as arl  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_oracle as lo  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import omp_trajectory as ot  # type: ignore[no-redef]
    import run_legal_agent_omp as ro  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PLAN_ID = "diagnostic-legal-agent-omp-v1"
DRAWS = alr.DRAWS
HITS = ala.HITS
ARM, HARNESS_REFERENCE = ro.ARM, "DSHF"
REPORT_FILE = "legal_agent_omp_report.json"
QUESTIONS = (f"{ARM}_vs_{HARNESS_REFERENCE}", f"{ARM}_vs_B")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _pct(value: float) -> float:
    return round(100 * value, 2)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_mc112(protocol: dict[str, Any], root: Path = ro.ROOT) -> tuple[list[dict[str, Any]], Path]:
    """MC-112's scored rows and its run directory, from the score file whose SHA-256 the protocol registers."""
    spec = protocol["mc112"]
    path = root / spec["scores"]
    if not path.is_file() or v1.sha256_file(path) != spec["scores_sha256"]:
        raise _fail(f"MC-112's score file {path} is missing or differs from its registered SHA-256")
    return _read_jsonl(path), path.parent


def add_mc112(cells: dict[str, dict[str, dict[str, Any]]], rows: list[dict[str, Any]],
              arms: tuple[str, ...] = ("DSHF", "DSH")) -> None:
    """Put MC-112's rows for `arms` into the cells as DSHF1, DSHF2, ... (every pool item must have both DSHF draws)."""
    for row in rows:
        arm, _, draw = str(row["replicate_id"]).partition("-r")
        if arm in arms and row["item_id"] in cells:
            cells[row["item_id"]][f"{arm}{draw}"] = row
    missing = [item for item, cell in cells.items() if not all(f"{HARNESS_REFERENCE}{d}" in cell for d in DRAWS)]
    if missing:
        raise _fail(f"MC-112's DSHF is missing for {missing[:3]}")


def questions(pool: list[str], cells: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    blocks = {name: alr.compare(pool, cells, *name.split("_vs_")) for name in QUESTIONS}
    short = [name for name, block in blocks.items() if block["n"] != len(pool)]
    if short:
        raise _fail(f"the comparisons {short} do not cover all {len(pool)} items")
    return blocks


def rules(blocks: dict[str, dict[str, Any]], alpha: float, margin: float) -> dict[str, Any]:
    """Both questions cross cards, so both use the margin."""
    tests = {name: block[f"{name.split('_vs_')[0]}_versus_{name.split('_vs_')[1]}"] for name, block in blocks.items()}
    adjusted = adp.holm_adjust({name: test["sign_flip_p"] for name, test in tests.items()})
    out: dict[str, Any] = {"alpha": alpha, "multiplicity": "holm", "margin_points": margin}
    for name, test in tests.items():
        reference = name.split("_vs_")[1]
        mean, p = test["mean_points"], adjusted[name]
        better, worse = mean > margin and p < alpha, mean < -margin and p < alpha
        out[name] = {"mean_points": mean, "sign_flip_p": test["sign_flip_p"], "p_holm": round(p, 6),
                     "better": better, "worse": worse,
                     "reading": (f"{ARM} beats {reference}" if better else f"{ARM} is worse than {reference}"
                                 if worse else f"no clear difference between {ARM} and {reference}")}
    out["legal_mc_route"] = ARM if out[f"{ARM}_vs_B"]["better"] else "B"
    return out


def _records(run_dir: Path, row: dict[str, Any]) -> list[dict[str, Any]]:
    return ala.load_attempt_records(run_dir, row)


def attempt_hits(cells: dict[str, dict[str, dict[str, Any]]], provisions: dict[str, dict[str, Any]],
                 run_dir: Path, mc112_dir: Path) -> dict[str, dict[str, dict[str, bool]]]:
    """{item: {"OMPF1": {"seen", "read", "opened"}, ..., "DSHF1": ...}}: any of the item's provisions, per attempt.
    OMPF's from omp's results, DSHF's from MC-112's proxy logs with MC-112's parser."""
    out: dict[str, dict[str, dict[str, bool]]] = {}
    for item, cell in cells.items():
        for arm, folder, parse in ((ARM, run_dir, ot.omp_observations),
                                   (HARNESS_REFERENCE, mc112_dir, la.model_observations)):
            for draw in DRAWS:
                per = la.provision_hits(parse(_records(folder, cell[f"{arm}{draw}"])), provisions[item]["provisions"])
                out.setdefault(item, {})[f"{arm}{draw}"] = {kind: any(p[kind] for p in per) for kind in HITS}
    return out


def _compactions(run_dir: Path, row: dict[str, Any]) -> int:
    path = run_dir / str(row.get("attempt_dir") or "") / "events.jsonl"
    if not row.get("attempt_dir") or not path.is_file():
        return 0
    return path.read_text(encoding="utf-8", errors="replace").count('"type":"auto_compaction_start"')


def behaviour(cells: dict[str, dict[str, dict[str, Any]]], run_dir: Path) -> dict[str, Any]:
    out = {}
    for arm in (ARM, HARNESS_REFERENCE):
        rows = [cell[f"{arm}{draw}"] for cell in cells.values() for draw in DRAWS]
        tools: Counter[str] = Counter()
        for row in rows:
            tools.update(row.get("tool_calls") or {})
        requests = [int(row.get("requests_forwarded", row.get("requests")) or 0) for row in rows]
        out[arm] = {
            "attempts": len(rows), "searched_share": round(statistics.fmean(bool(row.get("tool_calls")) for row in rows), 4),
            "tool_calls_per_attempt": {name: round(count / len(rows), 3) for name, count in sorted(tools.items())},
            "requests_per_attempt": round(statistics.fmean(requests), 3),
            "outcomes": dict(sorted(Counter(str(row.get("outcome")) for row in rows).items())),
            "share_answering_A": alo.letter_share(cells, arm), "mean_tokens": alo.token_means(cells, arm),
        }
    selectors: Counter[str] = Counter()
    compactions = []
    for cell in cells.values():
        for draw in DRAWS:
            row = cell[f"{ARM}{draw}"]
            selectors.update(ot.selectors(ot.omp_observations(_records(run_dir, row))))
            compactions.append(_compactions(run_dir, row))
    attempts = len(compactions)
    out[ARM]["per_attempt"] = {**{name: round(count / attempts, 3) for name, count in sorted(selectors.items())},
                               "compactions": round(statistics.fmean(compactions), 3),
                               "attempts_with_compaction": sum(c > 0 for c in compactions)}
    return out


def retrieval(pool: list[str], oracle_items: list[str], hits: dict[str, dict[str, dict[str, bool]]]) -> dict[str, Any]:
    """Hit rates per arm, and OMPF's per-item paired difference from DSHF (descriptive, not tested)."""
    def item_rate(item: str, arm: str, kind: str) -> float:
        return statistics.fmean(float(hits[item][f"{arm}{draw}"][kind]) for draw in DRAWS)

    out = {}
    for scope, items in (("pool", pool), ("mc100_oracle_items", oracle_items)):
        block: dict[str, Any] = {"n_items": len(items)}
        for arm in (ARM, HARNESS_REFERENCE):
            block[arm] = {kind: _pct(statistics.fmean(item_rate(item, arm, kind) for item in items)) for kind in HITS}
        block[f"{ARM}_minus_{HARNESS_REFERENCE}"] = {
            kind: arl.difference_block([item_rate(item, ARM, kind) for item in items],
                                       [item_rate(item, HARNESS_REFERENCE, kind) for item in items])
            for kind in HITS}
        out[scope] = block
    return out


def by_retrieval(cells: dict[str, dict[str, dict[str, Any]]], hits: dict[str, dict[str, dict[str, bool]]],
                 support: dict[str, str]) -> dict[str, Any]:
    """On supports_gold items: attempt-level accuracy when the governing provision was read and when it was not."""
    out = {}
    for arm in (ARM, HARNESS_REFERENCE):
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
        for arm in (ARM, HARNESS_REFERENCE, "B"):
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
    protocol = ro.load_protocol()
    manifest = ro.load_frozen_manifest()
    scores_path = run_dir / "scores.jsonl"
    scores = _read_jsonl(scores_path)
    by_key = {dp.run_key(row): row for row in scores}
    unfinished = [dp.run_key(ref) for ref in manifest["items"]
                  if (by_key.get(dp.run_key(ref)) or {}).get("status") not in (None, "complete")]
    if unfinished:
        raise _fail(f"{len(unfinished)} attempts are not final, e.g. {unfinished[:3]}; resume the run first")
    cells = alr.load_cells(scores, manifest)
    mc112_rows, mc112_dir = load_mc112(protocol)
    add_mc112(cells, mc112_rows)
    ala.add_reference(cells, la.load_reference(protocol))
    pool, support = manifest["pool"], manifest["support"]
    provisions = la.load_provisions()
    oracle_items = sorted(item for item in pool if provisions[item]["located_by"].startswith("mc100:"))
    blocks = questions(pool, cells)
    analysis = protocol["analysis"]
    hits = attempt_hits(cells, provisions, run_dir, mc112_dir)
    with_o = [item for item in pool if "O1" in cells[item]]
    owner = alo.owner_answers(json.loads(lo.REGISTRATION_PATH.read_text(encoding="utf-8")))

    def pool_mean(arm: str) -> float:
        return _pct(statistics.fmean(alr.arm_mean(cells[item], arm) for item in pool))
    return {
        "plan_id": PLAN_ID, "card_id": ro.CARD_ID, "manifest_sha256": manifest["manifest_sha256"],
        "scores_sha256": v1.sha256_file(scores_path), "reference_scores_sha256": protocol["reference"]["scores_sha256"],
        "mc112_scores_sha256": protocol["mc112"]["scores_sha256"],
        "questions": blocks,
        "rules": rules(blocks, analysis["alpha"], analysis["margin_points"]),
        "behaviour": behaviour(cells, run_dir),
        "retrieval": retrieval(pool, oracle_items, hits),
        "by_retrieval": by_retrieval(cells, hits, support),
        "against_O": alr.compare(with_o, cells, ARM, "O"),
        "gold_check": gold_check(cells, support, owner),
        "context": {"mc112_pool": {arm: pool_mean(arm) for arm in ("DSH", "DSHF")},
                    "mc111_round1_pool": {arm: pool_mean(arm) for arm in ("B", "K", "K10")},
                    "mc111_O_on_its_items": _pct(statistics.fmean(alr.arm_mean(cells[item], "O") for item in with_o))},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    report = build_report(args.run_dir)
    registered = json.loads(ro.REGISTRATION_PATH.read_text(encoding="utf-8"))["analysis"]["report_keys"]
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
