"""Stratified sampler for the 400-question reading-comprehension eval set (issue #3).

Pre-registered plan: 200 Vi-SQuAD + 200 Vi-DROP questions, seed 42, committed
manifest BEFORE any gold annotation (the manifest is the anti-cherry-pick record).

Strata (issue #3 wording):
  * DROP   -> primary reasoning category (comparison/add_sub/selection/count/other;
              tags like "comparison1,add_sub" normalize to their first token) with
              `count` OVERSAMPLED to a pinned 40/200 = 20% (VMLU-paper blind spot);
              the remaining 160 slots go largest-remainder by population.
  * SQuAD  -> context-length bucket (<230 / 230-400 / >400 words — the median/p75
              quoted in the issue) x question kind (direct vs inference cues).
              Inference questions are only ~3% of the population, so the three
              *-infer strata get a pinned floor (5 each = 15/200) — proportional
              would sample 1 long-infer question, too thin to report.
              Selection is passage-capped at 2 questions per context so the 200
              rows spread over as many distinct articles as possible.

Stdlib-only (runs on system python3 too). Output schema:
  dataset,item_id,stratum,passage_id,question,gold_answer
`gold_answer` ships EMPTY for every row — filled by the 2-annotator pass;
`passage_id` (source-order index of the context) lets audits verify the cap.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

SEED = 42
N_PER_DATASET = 200
DROP_PINNED = {"count": 40}          # 20% oversample, per issue #3
SQUAD_LEN_BOUNDS = (230, 400)        # words; T1 < 230 <= T2 <= 400 < T3
PASSAGE_CAP = 2
# Inference strata are ~3% of Vi-SQuAD; proportional sampling would yield
# ~1 question per cell (unreportable). Floor of 5 each = 15/200 = 7.5%,
# a deliberate, pre-registered oversample of the reasoning subset.
SQUAD_INFER_FLOOR = 5
# Vietnamese-first heuristic for inference (How/Why) questions; substring match.
INFERENCE_CUES = ("tại sao", "vì sao", "bằng cách nào", "như thế nào",
                  "thế nào", "làm sao", "why", "how")


def primary_category(cat: str) -> str:
    """'comparison1,add_sub' -> 'comparison' (first token, digits stripped)."""
    head = str(cat).split(",")[0].strip()
    stripped = head.rstrip("0123456789")
    return stripped or head


def squad_stratum(item: dict) -> str:
    w = len(str(item.get("context", "")).split())
    lo, hi = SQUAD_LEN_BOUNDS
    bucket = "short" if w < lo else ("mid" if w <= hi else "long")
    q = str(item.get("question", "")).lower()
    kind = "infer" if any(cue in q for cue in INFERENCE_CUES) else "direct"
    return f"{bucket}-{kind}"


def drop_stratum(item: dict) -> str:
    return primary_category(item["category"])


def group_by(items: list[dict], key_fn) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        g[key_fn(it)].append(it)
    return dict(g)


def passage_ids(items: list[dict]) -> dict[str, int]:
    """Global passage registry per dataset: identical context strings share one
    id, numbered by first appearance in source order."""
    pid: dict[str, int] = {}
    for it in items:
        ctx = str(it.get("context", ""))
        if ctx not in pid:
            pid[ctx] = len(pid)
    return pid


def allocate(weights: dict[str, int], total: int,
             pinned: dict[str, int] | None = None) -> dict[str, int]:
    """Largest-remainder proportional allocation; `pinned` strata keep fixed
    counts and are excluded from redistribution. Deterministic tie-break by
    stratum name so the same input always yields the same quotas (pre-reg)."""
    pinned = dict(pinned or {})
    if any(v < 0 for v in pinned.values()) or sum(pinned.values()) > total:
        raise ValueError(f"pinned quotas {pinned} exceed total {total}")
    quotas = {k: v for k, v in pinned.items() if v > 0}
    free = total - sum(quotas.values())
    if not free:
        return quotas
    ws = {k: v for k, v in weights.items() if k not in quotas and v > 0}
    if not ws:
        raise ValueError("no strata left to allocate after pinned")
    wsum = sum(ws.values())
    raw = {k: v / wsum * free for k, v in ws.items()}
    base = {k: int(r) for k, r in raw.items()}
    rem = free - sum(base.values())
    order = sorted(ws, key=lambda k: (base[k] - raw[k], k))  # most-fractional first
    for k in order[:rem]:
        base[k] += 1
    quotas.update({k: v for k, v in base.items() if v > 0})
    return quotas


def sample_strata(items: list[dict], quotas: dict[str, int], stratum_fn,
                  rng: random.Random, passage_cap: int | None = None,
                  pid: dict[str, int] | None = None) -> list[dict]:
    """Draw exactly sum(quotas) items. Each stratum shuffles its members and
    accepts sequentially while the passage cap allows. A stratum starved by the
    cap is refilled from the unpicked remainder — never exceeding any stratum's
    quota — and the cap is relaxed only as a final resort, so quotas hold
    whenever the population can supply them."""
    by_stratum = group_by(items, stratum_fn)
    missing = sorted(k for k in quotas if k not in by_stratum)
    if missing:
        raise ValueError(f"quota for strata absent from data: {missing}")

    picked: list[dict] = []
    picked_ids: set[int] = set()
    taken: dict[str, int] = {k: 0 for k in quotas}
    per_passage: dict[int, int] = defaultdict(int)

    def pid_of(it: dict) -> int:
        assert pid is not None
        return pid[str(it.get("context", ""))]

    def cap_ok(it: dict) -> bool:
        return passage_cap is None or per_passage[pid_of(it)] < passage_cap

    def take(it: dict) -> None:
        picked.append(it)
        picked_ids.add(id(it))
        taken[stratum_fn(it)] += 1
        if passage_cap is not None:
            per_passage[pid_of(it)] += 1

    for key in sorted(quotas):
        pool = list(by_stratum[key])
        rng.shuffle(pool)
        for it in pool:
            if taken[key] >= quotas[key]:
                break
            if cap_ok(it):
                take(it)

    total = sum(quotas.values())
    if len(picked) < total:
        rest = [it for it in items if id(it) not in picked_ids]
        rng.shuffle(rest)
        for relax_cap in (False, True):  # last pass may break the cap
            for it in rest:
                if len(picked) >= total:
                    break
                k = stratum_fn(it)
                if k not in quotas or taken[k] >= quotas[k]:
                    continue
                if relax_cap or cap_ok(it):
                    take(it)
    return picked


def build_manifest(squad: list[dict], drop: list[dict], seed: int,
                   n_each: int) -> list[dict]:
    sq_pid = passage_ids(squad)
    dr_pid = passage_ids(drop)
    rng = random.Random(seed)

    sq_weights = {k: len(v) for k, v in group_by(squad, squad_stratum).items()}
    sq_pinned = {k: SQUAD_INFER_FLOOR for k in sq_weights if k.endswith("-infer")}
    sq_picked = sample_strata(squad,
                              allocate(sq_weights, n_each, pinned=sq_pinned),
                              squad_stratum, rng,
                              passage_cap=PASSAGE_CAP, pid=sq_pid)
    dr_fn = lambda it: primary_category(it["category"])  # noqa: E731
    dr_picked = sample_strata(drop,
                              allocate({k: len(v) for k, v in group_by(drop, dr_fn).items()},
                                       n_each, pinned=DROP_PINNED),
                              dr_fn, rng)

    rows = []
    for it in sorted(sq_picked, key=lambda x: x["id"]):
        rows.append({"dataset": "squad", "item_id": it["id"],
                     "stratum": squad_stratum(it), "passage_id": sq_pid[str(it["context"])],
                     "question": it["question"], "gold_answer": ""})
    for it in sorted(dr_picked, key=lambda x: x["question_id"]):
        rows.append({"dataset": "drop", "item_id": it["question_id"],
                     "stratum": dr_fn(it), "passage_id": dr_pid[str(it["context"])],
                     "question": it["question"], "gold_answer": ""})
    return rows


def load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    data = obj.get("data", [])
    if not data:
        raise SystemExit(f"Error: no records in {path}")
    return data


def main():
    ap = argparse.ArgumentParser(description="Build the 400-question eval-set manifest (issue #3).")
    ap.add_argument("--squad-file", type=Path,
                    default=Path("vmlu_squad_v1/vi_squad_benchmark_question_only.json"))
    ap.add_argument("--drop-file", type=Path,
                    default=Path("vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json"))
    ap.add_argument("--out", type=Path, default=Path("eval_set_manifest.csv"))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N_PER_DATASET,
                    help="questions per dataset (default 200, per issue #3)")
    args = ap.parse_args()

    rows = build_manifest(load_json(args.squad_file), load_json(args.drop_file),
                          args.seed, args.n)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "item_id", "stratum",
                                          "passage_id", "question", "gold_answer"])
        w.writeheader()
        w.writerows(rows)

    by_ds = group_by(rows, lambda r: r["dataset"])
    print(f"seed={args.seed}  wrote {len(rows)} rows -> {args.out}")
    for ds in sorted(by_ds):
        st = group_by(by_ds[ds], lambda r: r["stratum"])
        print(f"  {ds} ({len(by_ds[ds])}): " +
              "  ".join(f"{k}={len(v)}" for k, v in sorted(st.items())))
        if ds == "squad":
            n_pass = len({r["passage_id"] for r in by_ds[ds]})
            print(f"    distinct passages: {n_pass} (cap {PASSAGE_CAP}/passage)")


if __name__ == "__main__":
    main()
