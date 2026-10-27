"""Blind, AI-assisted semantic review of the reading answers behind the MC-90 exact-match discordance
(openspec change: diagnostic-prospective-campaign, tasks 12.x), reused for the router v2 held-out run (MC-94,
openspec change diagnostic-router-v2): there the packet holds only the items whose exact match differs between B
and S (strata R and G, censuses), as the held-out analysis registered.

Exact match counts a paraphrase or an added qualifier as wrong, so the EM rescues and regressions of S against B can
overstate or understate the real change. This module (1) builds a seeded, blind review packet, (2) reads the labels
two reviewers give and (3) unblinds and estimates semantic rescues, regressions and net change with a stratified
interval. The review is AI-assisted: it must never be reported as a blind human review.

Design, fixed before any label exists:
* reading items only (multiple-choice letters have no semantic ambiguity); one first draw of B and of S per item;
* strata by exact match and token-F1: C both exact (assumed correct under both, never reviewed); R S exact and B not
  (census, the B answer is reviewed); G B exact and S not (census, the S answer is reviewed); W both inexact, split
  by the larger token-F1 of the two answers (W_hi >= 0.5 by dataset, W_lo < 0.5); W_hi:squad and W_hi:drop are taken
  whole, the other W strata are sampled with a fixed seed and both answers are reviewed;
* every unit is one candidate answer with its question and reference answer, shown without arm, direction or stratum,
  in shuffled order.

  .venv/bin/python -m code_benchmark.diagnostic_semantic_review build --run-dir <MC-90 run dir> --out-dir <dir>
  .venv/bin/python -m code_benchmark.diagnostic_semantic_review build --heldout   # MC-94, R and G only
  .venv/bin/python -m code_benchmark.diagnostic_semantic_review aggregate --out-dir <dir> --labels A.jsonl B.jsonl \\
      [--adjudicated C.jsonl]
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_heldout as dh
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_heldout as dh
    import vi_multimodel as v1

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = ROOT / "all_res" / "diagnostic_prospective" / "wide" / "qwen3-5-9b-65k-prospective"
HELDOUT_RUN_DIR = ROOT / "all_res" / "diagnostic_router_v2" / "heldout" / "qwen3-5-9b-65k-prospective"
SEED = 42
F1_SPLIT = 0.5
SAMPLE_SIZES = {"W_hi:bidlqa": 70, "W_lo": 30}  # every other non-C stratum is taken whole
HELDOUT_STRATA = ("R", "G")  # MC-94: the exact-match discordance of the first draw pair, nothing sampled
BATCH_UNITS = 126
CANDIDATE_CHARS = 500
LABELS = ("correct", "partial", "incorrect")
PACKET_FIELDS = ("unit_id", "task_type", "question", "reference_answer", "candidate_answer")
TASK_TYPES = {
    "squad": "viSQuAD: extractive reading-comprehension question",
    "drop": "DROP: reading question that may need counting, arithmetic, comparison or a yes/no",
    "bidlqa": "ViBidLQA: Vietnamese legal free-form question",
}

REVIEWER_INSTRUCTIONS = """\
You are a careful annotator fluent in Vietnamese and English. You receive a JSONL file; each line is one unit with the
fields unit_id, task_type, question, reference_answer and candidate_answer. Decide, for each unit on its own, whether
the candidate answer is semantically correct with respect to the reference answer.

Labels
- correct: the candidate gives the same answer as the reference. It may differ in wording, word order, punctuation,
  abbreviations, units or number formatting (for example "5,4" and "5.4"), and it may add words or context that do not
  contradict the reference, or be a longer span that fully contains the reference fact. When the reference lists
  several parts, every part must be present.
- partial: the candidate contains part of the reference but leaves out a required part, or adds a clearly different
  or contradicting extra fact, or is vague or too broad while compatible with the reference.
- incorrect: a different answer, a contradiction, an unrelated statement, an empty answer or a refusal.

Rules
- The reference answer is the ground truth. Do not replace it with your own knowledge, and do not reward a candidate
  that answers a different question than the one asked.
- Judge each unit independently. The order of the units and their neighbours carry no information; nothing hidden
  is encoded in the file, so do not try to guess where a candidate came from.
- Use only the file you are given. Do not browse, run code or read any other file.

Output
Write one JSON object per input line, in the same order, to the output path you are given:
{"unit_id": "<id>", "label": "correct|partial|incorrect", "reason": "<at most 15 words>"}
Then reply with only: DONE <number of units> <correct> <partial> <incorrect>
"""


# ---------------------------------------------------------------- building the packet

def short_dataset(dataset_id: str) -> str:
    for name in TASK_TYPES:
        if name in dataset_id:
            return name
    raise SystemExit(f"Error: {dataset_id!r} is not a reading dataset of the campaign")


def reading_records(rows: list[dict[str, Any]], items: dict[str, Any]) -> list[dict[str, Any]]:
    """One record per reading item with the first draw of B and of S (exact match, token-F1, answer)."""
    first = {(r["arm"], r["dataset_id"], r["item_id"]): r for r in rows
             if "em" in r and str(r["replicate_id"]).endswith("-r1")}
    records = []
    for dataset_id, item_id in sorted({(d, i) for (_, d, i) in first}):
        b, s = first[("B", dataset_id, item_id)], first[("S", dataset_id, item_id)]
        item = items[f"{dataset_id}:{item_id}:main-000"]
        records.append({
            "item_key": f"{dataset_id}:{item_id}", "dataset": short_dataset(dataset_id), "question": item.question,
            "gold": str(b.get("gold_answer") or item.gold_answer), "b_em": bool(b["em"]), "s_em": bool(s["em"]),
            "b_f1": float(b["token_f1"]), "s_f1": float(s["token_f1"]),
            "b_pred": str(b.get("prediction") or ""), "s_pred": str(s.get("prediction") or "")})
    return records


def stratum_of(record: dict[str, Any]) -> str:
    if record["b_em"] and record["s_em"]:
        return "C"
    if record["s_em"]:
        return "R"
    if record["b_em"]:
        return "G"
    if max(record["b_f1"], record["s_f1"]) < F1_SPLIT:
        return "W_lo"
    return f"W_hi:{record['dataset']}"


def choose(strata: dict[str, list[dict[str, Any]]], seed: int, sizes: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
    """Census where no size is set (or it covers the stratum), otherwise a seeded simple random sample."""
    chosen: dict[str, list[dict[str, Any]]] = {}
    for name in sorted(strata):
        if name == "C":
            continue
        members = sorted(strata[name], key=lambda r: r["item_key"])
        size = sizes.get(name)
        if size is None or size >= len(members):
            chosen[name] = members
        else:
            chosen[name] = sorted(random.Random(f"{seed}:{name}").sample(members, size), key=lambda r: r["item_key"])
    return chosen


def heldout_sizes(records: list[dict[str, Any]]) -> dict[str, int]:
    """Sample size 0 for every stratum outside HELDOUT_STRATA, so only the discordant items are reviewed."""
    return {name: 0 for name in {stratum_of(record) for record in records} if name not in HELDOUT_STRATA}


def candidate_text(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= CANDIDATE_CHARS else text[:CANDIDATE_CHARS].rstrip() + " …"


def build_packet(records: list[dict[str, Any]], *, seed: int = SEED, sizes: dict[str, int] | None = None
                 ) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """(blind units, key, design). Units carry no arm, direction or stratum and are shuffled."""
    sizes = SAMPLE_SIZES if sizes is None else sizes
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        strata[stratum_of(record)].append(record)
    chosen = choose(strata, seed, sizes)
    pending = []
    for name, members in chosen.items():
        for record in members:
            wanted = {"R": ("B",), "G": ("S",)}.get(name, ("B", "S"))
            for arm in wanted:
                pending.append({"stratum": name, "record": record, "arm": arm})
    pending.sort(key=lambda u: (u["record"]["item_key"], u["arm"]))
    random.Random(f"{seed}:order").shuffle(pending)
    units, key = [], []
    for index, unit in enumerate(pending, 1):
        record, arm = unit["record"], unit["arm"]
        unit_id = f"U{index:04d}"
        units.append({"unit_id": unit_id, "task_type": TASK_TYPES[record["dataset"]], "question": record["question"],
                      "reference_answer": record["gold"],
                      "candidate_answer": candidate_text(record["b_pred"] if arm == "B" else record["s_pred"])})
        key.append({"unit_id": unit_id, "item_key": record["item_key"], "arm": arm, "stratum": unit["stratum"]})
    design = {"seed": seed, "f1_split": F1_SPLIT, "sample_sizes": sizes, "candidate_chars": CANDIDATE_CHARS,
              "population": {name: len(members) for name, members in sorted(strata.items())},
              "sampled": {name: len(members) for name, members in chosen.items()},
              "reading_items": len(records), "units": len(units)}
    return units, key, design


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def build(run_dir: Path, out_dir: Path, seed: int = SEED, *, heldout: bool = False) -> dict[str, Any]:
    scores_path = run_dir / "scores.jsonl"
    rows = [json.loads(line) for line in scores_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if heldout:
        records = reading_records(rows, {item.run_key: item for item in dh.sample_items(dh.load_protocol())})
        units, key, design = build_packet(records, seed=seed, sizes=heldout_sizes(records))
    else:
        records = reading_records(rows, v1.rebuild_items("main"))
        units, key, design = build_packet(records, seed=seed)
    design["scores_sha256"] = v1.sha256_file(scores_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "packet.jsonl", units)
    batches = []
    for number, start in enumerate(range(0, len(units), BATCH_UNITS), 1):
        name = f"batch_{number:02d}.jsonl"
        write_jsonl(out_dir / name, units[start:start + BATCH_UNITS])
        batches.append({"file": name, "units": len(units[start:start + BATCH_UNITS])})
    design["batches"] = batches
    (out_dir / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "design.json").write_text(json.dumps(design, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "instructions.md").write_text(REVIEWER_INSTRUCTIONS, encoding="utf-8")
    return design


# ---------------------------------------------------------------- reading the labels and estimating

def read_labels(path: Path, valid_units: set[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        unit, label = row.get("unit_id"), row.get("label")
        if unit not in valid_units or label not in LABELS or unit in labels:
            raise SystemExit(f"Error: {path}:{number} has an unknown unit, an invalid label or a duplicate ({unit!r}, {label!r})")
        labels[unit] = label
    return labels


def cohen_kappa(first: list[str], second: list[str]) -> float | None:
    n = len(first)
    if not n or n != len(second):
        return None
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    ca, cb = Counter(first), Counter(second)
    expected = sum(ca[c] / n * cb[c] / n for c in set(ca) | set(cb))
    return None if expected == 1 else (observed - expected) / (1 - expected)


def agreement(first: dict[str, str], second: dict[str, str], key: list[dict[str, str]]) -> dict[str, Any]:
    units = [k["unit_id"] for k in key]
    a, b = [first[u] for u in units], [second[u] for u in units]
    strict_a, strict_b = [x == "correct" for x in a], [y == "correct" for y in b]
    return {"units": len(units), "raw_agreement": sum(x == y for x, y in zip(a, b, strict=True)) / len(units),
            "kappa_three_class": cohen_kappa(a, b),
            "raw_agreement_strict": sum(x == y for x, y in zip(strict_a, strict_b, strict=True)) / len(units),
            "kappa_strict": cohen_kappa([str(x) for x in strict_a], [str(y) for y in strict_b]),
            "disagreements": sum(x != y for x, y in zip(a, b, strict=True))}


def consensus(first: dict[str, str], second: dict[str, str], adjudicated: dict[str, str],
              key: list[dict[str, str]]) -> dict[str, str]:
    """Agreed label, or the blind adjudication where the two reviewers differ."""
    missing = [k["unit_id"] for k in key if k["unit_id"] not in first or k["unit_id"] not in second]
    if missing:
        raise SystemExit(f"Error: {len(missing)} unit(s) lack a label from a reviewer, e.g. {missing[:3]}")
    labels = {}
    for k in key:
        unit = k["unit_id"]
        if first[unit] == second[unit]:
            labels[unit] = first[unit]
        elif unit in adjudicated:
            labels[unit] = adjudicated[unit]
        else:
            raise SystemExit(f"Error: unit {unit} is a disagreement without an adjudication")
    return labels


def estimate(design: dict[str, Any], key: list[dict[str, str]], labels: dict[str, str], *, strict: bool) -> dict[str, Any]:
    """Semantic rescues, regressions and net change over the reading items. R and G are censuses; only the sampled
    W strata contribute sampling variance (finite-population corrected)."""
    good = (lambda label: label == "correct") if strict else (lambda label: label in ("correct", "partial"))
    by_item: dict[str, dict[str, Any]] = defaultdict(dict)
    for unit in key:
        slot = by_item[unit["item_key"]]
        slot["stratum"] = unit["stratum"]
        slot[unit["arm"]] = good(labels[unit["unit_id"]])
    population = design["population"]
    members: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for slot in by_item.values():  # R: S exact so semantically right; G: B exact so semantically right
        members[slot["stratum"]].append((int(slot.get("B", True)), int(slot.get("S", True))))

    def total(value) -> tuple[float, float]:
        estimate_, variance = 0.0, 0.0
        for name, pairs in members.items():
            values = [value(b, s) for b, s in pairs]
            n, size = len(values), population[name]
            mean = sum(values) / n
            estimate_ += size * mean
            if 1 < n < size:
                variance += size ** 2 * (1 - n / size) * sum((v - mean) ** 2 for v in values) / (n - 1) / n
        return estimate_, variance

    items = design["reading_items"]
    out: dict[str, Any] = {"strict": strict, "reading_items": items}
    for name, value in (("rescues", lambda b, s: int(not b and s)), ("regressions", lambda b, s: int(b and not s)),
                        ("net", lambda b, s: s - b)):
        est, var = total(value)
        out[name] = {"estimate": est, "se": math.sqrt(var), "ci95": [est - 1.96 * math.sqrt(var), est + 1.96 * math.sqrt(var)]}
    both_right = population.get("C", 0)
    b_total, _ = total(lambda b, s: b)
    s_total, _ = total(lambda b, s: s)
    out["semantic_accuracy"] = {"b": (both_right + b_total) / items, "s": (both_right + s_total) / items}
    out["net_points"] = {k: 100 * out["net"][k] / items for k in ("estimate", "se")}
    out["net_points"]["ci95"] = [100 * x / items for x in out["net"]["ci95"]]
    out["em_reference"] = {"rescues": population.get("R", 0), "regressions": population.get("G", 0),
                           "net": population.get("R", 0) - population.get("G", 0)}
    out["by_stratum"] = {name: {"population": population[name], "reviewed_items": len(pairs),
                                "b_semantically_right": sum(b for b, _ in pairs),
                                "s_semantically_right": sum(s for _, s in pairs)}
                         for name, pairs in sorted(members.items())}
    return out


def aggregate(out_dir: Path, label_files: list[Path], adjudicated_path: Path | None) -> dict[str, Any]:
    design = json.loads((out_dir / "design.json").read_text(encoding="utf-8"))
    key = json.loads((out_dir / "key.json").read_text(encoding="utf-8"))
    valid = {k["unit_id"] for k in key}
    first, second = (read_labels(path, valid) for path in label_files)
    adjudicated = read_labels(adjudicated_path, valid) if adjudicated_path else {}
    agree = agreement(first, second, key)
    final = consensus(first, second, adjudicated, key)
    report = {"ai_assisted_not_human": True, "design": {k: design[k] for k in ("seed", "population", "sampled", "units")},
              "agreement": agree, "label_counts_final": dict(Counter(final.values())),
              "label_counts_by_stratum": {name: dict(Counter(final[k["unit_id"]] for k in key if k["stratum"] == name))
                                          for name in sorted({k["stratum"] for k in key})},
              "estimates": {"strict": estimate(design, key, final, strict=True),
                            "lenient": estimate(design, key, final, strict=False)},
              "sensitivity_strict": {"reviewer_a_only": estimate(design, key, first, strict=True)["net"]["estimate"],
                                     "reviewer_b_only": estimate(design, key, second, strict=True)["net"]["estimate"]}}
    return report


def format_report(report: dict[str, Any]) -> str:
    a = report["agreement"]
    lines = ["AI-assisted semantic review (two independent AI reviewers, blind, adjudicated by a third blind read); "
             "not a blind human review",
             f"units {a['units']}  raw agreement {100 * a['raw_agreement']:.1f}%  kappa(3 classes) {a['kappa_three_class']:.2f}  "
             f"strict-binary agreement {100 * a['raw_agreement_strict']:.1f}%  kappa {a['kappa_strict']:.2f}  "
             f"disagreements {a['disagreements']}"]
    for mode in ("strict", "lenient"):
        e = report["estimates"][mode]
        lines.append(f"[{mode}] semantic rescues {e['rescues']['estimate']:.1f} (EM {e['em_reference']['rescues']})  "
                     f"regressions {e['regressions']['estimate']:.1f} (EM {e['em_reference']['regressions']})  "
                     f"net {e['net']['estimate']:+.1f} items = {e['net_points']['estimate']:+.2f} pts "
                     f"CI95 [{e['net_points']['ci95'][0]:+.2f}, {e['net_points']['ci95'][1]:+.2f}] (EM net {e['em_reference']['net']:+d})")
        lines.append(f"         semantic accuracy B {100 * e['semantic_accuracy']['b']:.1f}%  S {100 * e['semantic_accuracy']['s']:.1f}%")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write the blind packet, the key and the batches")
    b.add_argument("--run-dir", type=Path, default=None, help=f"default: {DEFAULT_RUN_DIR} (with --heldout: {HELDOUT_RUN_DIR})")
    b.add_argument("--out-dir", type=Path, default=None)
    b.add_argument("--seed", type=int, default=SEED)
    b.add_argument("--heldout", action="store_true", help="the router v2 held-out run: discordant reading items only")
    a = sub.add_parser("aggregate", help="unblind the labels and estimate the semantic effect")
    a.add_argument("--out-dir", type=Path, required=True)
    a.add_argument("--labels", type=Path, nargs=2, required=True, metavar=("A", "B"))
    a.add_argument("--adjudicated", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == "build":
        run_dir = args.run_dir or (HELDOUT_RUN_DIR if args.heldout else DEFAULT_RUN_DIR)
        design = build(run_dir, args.out_dir or run_dir / "semantic_review", args.seed, heldout=args.heldout)
        print(json.dumps({k: design[k] for k in ("population", "sampled", "units", "batches")}, ensure_ascii=False))
        return 0
    report = aggregate(args.out_dir, args.labels, args.adjudicated)
    (args.out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
