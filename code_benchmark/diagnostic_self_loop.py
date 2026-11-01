"""The self-improvement loop (openspec change diagnostic-router-loop, decision 11, task 2.6; card MC-104).

The student that is measured answers every round: no answer comes from another model. Two parts, on items no router
has used:

* knowledge: 300 unused ViBidLQA train questions asked as legal knowledge questions, without their own passage. Arms:
  B (the question only), K with the 2 clauses of the registered K2 BM25 ranking, K with the top 5 of the same ranking
  (dataset `bidlqa-closed-book-top5`), and O with the item's own clause, a ceiling.
* multiple choice: the 303 VMLU dev items and 300 unused four-option VM14K items. Arms: B, and S three times. Qwen's
  B is one temperature-0 request with letter log-probabilities (the MC-43 condition), which also gives the confidence
  of its answer; MiMo's route reports no log-probabilities, so MiMo answers B twice.

The loop is replayed offline from the logged answers (`loop_qwen`, `loop_mimo`): round 1 is B; when the student is
unsure, round 2 is S; when S disagrees, round 3 adds two S answers and takes the majority. Qwen's threshold is fixed
in the configuration, before the run, by a registered rule on design data (`threshold_from_design`).

  .venv/bin/python -m code_benchmark.diagnostic_self_loop [--write]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_heldout as dh
    from code_benchmark import diagnostic_heldout_v3 as h3
    from code_benchmark import diagnostic_k2 as k2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_heldout as dh
    import diagnostic_heldout_v3 as h3
    import diagnostic_k2 as k2
    import diagnostic_prospective as dp
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_loop"
CONFIG_PATH = DATA_DIR / "self_loop_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration_self_loop.json"
PROTOCOL_ID = "vmlu-diagnostic-self-loop"
PHASE = "self_loop"
STUDENTS = ("qwen", "mimo")
VMLU, VM14K = "vmlu-mqa-dev", h3.VM14K
KNOW, KNOW5 = "bidlqa-closed-book", "bidlqa-closed-book-top5"
CONFIG_KEYS = ("loop_id", "protocol_id", "protocol_version", "change", "purpose", "items", "arms", "arm_meaning",
               "retrieval", "students", "loop", "threshold_rule", "analysis")
THRESHOLD_GRID = tuple(round(0.50 + 0.05 * step, 2) for step in range(10))


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def manifest_path(student: str) -> Path:
    return DATA_DIR / f"self_loop_manifest_{student}_v1.json"


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the self-loop configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if (config["protocol_id"], config["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported self-loop protocol id or version")
    if set(config["arms"]) != set(STUDENTS) or set(config["students"]) != set(STUDENTS):
        raise _fail(f"the students must be exactly {list(STUDENTS)}")
    for student, arms in config["arms"].items():
        for part in ("mc", "knowledge", "knowledge_top5"):
            for replicate in arms[part]:
                dp.arm_of_replicate(replicate)  # <ARM>-r<k>, a campaign arm
        if [dp.arm_of_replicate(r) for r in arms["knowledge"]] != ["B", "K", "O"] or arms["knowledge_top5"] != ["K-r1"]:
            raise _fail(f"{student}: the knowledge arms must be B, K and O, and K-r1 at top 5")
        if [r for r in arms["mc"] if r.startswith("S-")] != ["S-r1", "S-r2", "S-r3"]:
            raise _fail(f"{student}: the multiple-choice S arms must be S-r1, S-r2 and S-r3")
    if config["arms"]["qwen"]["mc"][:1] != ["B-r1"] or config["arms"]["mimo"]["mc"][:2] != ["B-r1", "B-r2"]:
        raise _fail("Qwen answers B once (the probe), MiMo twice")
    threshold = config["loop"]["qwen"]["threshold"]
    if threshold not in THRESHOLD_GRID or config["threshold_rule"]["result"]["threshold"] != threshold:
        raise _fail("the Qwen threshold must be the registered rule's result, on its grid")
    if config["retrieval"]["top_k"] != [2, 5]:
        raise _fail("the knowledge part compares the top 2 and the top 5 of one BM25 ranking")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        return validate_config(json.loads(raw)), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the self-loop configuration {path}: {exc}") from exc


# ---------------------------------------------------------------- items

def vmlu_items(config: dict[str, Any]) -> list[v1.EvalItem]:
    items = v1._load_vmlu("dev")  # noqa: SLF001 - the frozen VMLU loader, dev split
    if len(items) != config["items"]["vmlu"]["n"] or {item.dataset_id for item in items} != {VMLU}:
        raise _fail(f"VMLU dev has {len(items)} items, not {config['items']['vmlu']['n']}")
    return items


def vm14k_items(config: dict[str, Any]) -> list[v1.EvalItem]:
    used = {row["item_id"] for row in h3.load_frozen_manifest()["items"] if row["dataset_id"] == VM14K}
    pool = [item for item in h3.load_vm14k() if item.item_id not in used]
    spec = config["items"]["vm14k"]
    return dh._ranked(pool, spec["seed"])[:spec["n"]]  # noqa: SLF001 - the registered seeded ranking


def knowledge_items(config: dict[str, Any]) -> list[v1.EvalItem]:
    used = {row["item_id"] for row in k2.load_frozen_manifest()["items"]}
    pool = [dataclasses.replace(item, dataset_id=KNOW) for item in k2.load_pool() if item.item_id not in used]
    spec = config["items"]["knowledge"]
    if len(pool) != spec["pool"]:
        raise _fail(f"the knowledge pool has {len(pool)} items, not {spec['pool']}")
    return dh._ranked(pool, spec["seed"])[:spec["n"]]  # noqa: SLF001 - the registered seeded ranking


def retrieval(items: list[v1.EvalItem]) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    """(per item id: the top-5 clause ids, their scores and the own clause's rank; clause texts; provenance)."""
    config, digest = k2.load_retrieval_config()
    retriever = k2.build_retriever(config, digest)
    text_of = {passage["passage_id"]: passage["text"] for passage in retriever.corpus}
    traces = {}
    for item in items:
        ranked = k2.ranking(retriever, item.question)
        ids = [retriever.corpus[position]["passage_id"] for position, _ in ranked]
        if len(ids) < 5:
            raise _fail(f"{item.item_id}: fewer than 5 clauses share a token with the question")
        traces[item.item_id] = {"top5": ids[:5], "scores": [round(score, 6) for _, score in ranked[:5]],
                                "own_rank": ids.index(item.passage_id) + 1 if item.passage_id in ids else None}
    provenance = {"retrieval_config_sha256": digest, "corpus_sha256": retriever.corpus_sha256,
                  "separator": config["passage_separator"]}
    return traces, text_of, provenance


def request_traces(manifest: dict[str, Any], rebuilt: dict[str, v1.EvalItem]) -> dict[str, dict[str, Any]]:
    """{dataset:item: retrieval trace} the campaign request attaches to every K row, shaped like the MC-93 and MC-96
    traces (corpus, configuration and query hashes, the kept ranking) and read from the frozen manifest."""
    questions = {item.item_id: item.question for item in rebuilt.values() if item.dataset_id == KNOW}
    traces = {}
    for item_id, record in manifest["retrieval"].items():
        for dataset_id, depth in ((KNOW, 2), (KNOW5, 5)):
            traces[dp.item_key(dataset_id, item_id)] = {
                "corpus_sha256": manifest["corpus_sha256"], "retrieval_config_sha256": manifest["retrieval_config_sha256"],
                "query_sha256": v1.sha256_bytes(questions[item_id].encode("utf-8")), "top_k": depth,
                "ranking": [{"passage_id": passage, "score": score}
                            for passage, score in zip(record["top5"][:depth], record["scores"][:depth], strict=True)]}
    return traces


def expand(student: str, config: dict[str, Any], mc: list[v1.EvalItem], knowledge: list[v1.EvalItem],
           traces: dict[str, dict[str, Any]], text_of: dict[str, str], separator: str) -> list[v1.EvalItem]:
    """Item-major attempts of one student; every prompt is built by the frozen campaign or K2 builders."""
    templates, k2_protocol = dp.load_templates(), k2.load_protocol()
    arms = config["arms"][student]
    items: list[v1.EvalItem] = []
    for item in mc:
        prompts = {arm: dp.build_arm_prompt(item, arm, templates) for arm in ("B", "S")}
        items += [dataclasses.replace(item, replicate_id=r, prompt=prompts[dp.arm_of_replicate(r)]) for r in arms["mc"]]
    for item in knowledge:
        clauses = [text_of[passage] for passage in traces[item.item_id]["top5"]]
        top2 = k2.arm_prompts(item, clauses[:2], k2_protocol, templates, separator)
        top5 = k2.arm_prompts(item, clauses, k2_protocol, templates, separator)
        items += [dataclasses.replace(item, replicate_id=r, prompt=top2[dp.arm_of_replicate(r)]) for r in arms["knowledge"]]
        items += [dataclasses.replace(item, dataset_id=KNOW5, replicate_id=r, prompt=top5["K"])
                  for r in arms["knowledge_top5"]]
    return items


def build_manifest(student: str, config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map) of one student, self-hashed like the campaign manifests."""
    if student not in STUDENTS:
        raise _fail(f"unknown student {student!r}")
    config, digest = load_config(config_path)
    mc = vmlu_items(config) + vm14k_items(config)
    knowledge = knowledge_items(config)
    traces, text_of, provenance = retrieval(knowledge)
    items = expand(student, config, mc, knowledge, traces, text_of, provenance["separator"])
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate self-loop run keys")
    base = mc + knowledge
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "student": student,
        "config_sha256": digest,
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "k2_protocol_sha256": v1.sha256_file(k2.PROTOCOL_PATH),
        "retrieval_config_sha256": provenance["retrieval_config_sha256"], "corpus_sha256": provenance["corpus_sha256"],
        "excluded_manifest_sha256": {"MC-95": v1.sha256_file(h3.MANIFEST_PATH), "MC-96": v1.sha256_file(k2.MANIFEST_PATH)},
        "source_sha256": {"vmlu_mqa_v1.5/dev.jsonl": v1.sha256_file(dp.ROOT / "vmlu_mqa_v1.5" / "dev.jsonl"),
                          **{str(path.relative_to(dp.ROOT)): digest for path, digest in h3.PINNED.items()},
                          **k2.source_sha256()},
        "n": len(items), "item_count": len(base),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in base).items())),
        "arm_counts": dict(sorted(Counter(f"{item.dataset_id}:{dp.arm_of_replicate(item.replicate_id)}"
                                          for item in items).items())),
        "retrieval": {item.item_id: traces[item.item_id] for item in knowledge},
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(student: str) -> dict[str, Any]:
    try:
        return json.loads(manifest_path(student).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the frozen self-loop manifest of {student}: {exc}") from exc


# ---------------------------------------------------------------- the loop and its threshold

def majority(answers: list[str]) -> str:
    """The most frequent non-empty answer; a tie goes to the earliest; with no answer, the first (empty) one."""
    votes = Counter(answer for answer in answers if answer)
    if not votes:
        return answers[0] if answers else ""
    top = max(votes.values())
    return next(answer for answer in answers if answer and votes[answer] == top)


def loop_qwen(b: str, confidence: float | None, s: list[str], threshold: float) -> tuple[str, int]:
    """(final answer, rounds used). Round 1 keeps a confident B; round 2 keeps B when S-r1 agrees with it; round 3
    takes the majority of the three S answers."""
    if confidence is not None and confidence >= threshold:
        return b, 1
    if s[0] and s[0] == b:
        return b, 2
    return majority(s), 3


def loop_mimo(b1: str, b2: str, s: list[str]) -> tuple[str, int]:
    """(final answer, rounds used). Round 1 keeps two equal B answers; round 2 keeps S-r1 when it equals one of them;
    round 3 takes the majority of the three S answers."""
    if b1 and b1 == b2:
        return b1, 1
    if s[0] and s[0] in (b1, b2):
        return s[0], 2
    return majority(s), 3


def threshold_from_design(rows: list[tuple[float | None, int, int]], margin: float = 1.0) -> dict[str, float]:
    """The registered rule on design rows (confidence, B correct, S-r1 correct): the smallest grid threshold whose
    two-round loop scores at least always-S minus `margin` points."""
    always_s = 100 * sum(s for _, _, s in rows) / len(rows)
    for threshold in THRESHOLD_GRID:
        unsure = [confidence is None or confidence < threshold for confidence, _, _ in rows]
        loop = 100 * sum(s if u else b for (_, b, s), u in zip(rows, unsure, strict=True)) / len(rows)
        if loop >= always_s - margin:
            return {"threshold": threshold, "escalated_share": round(100 * sum(unsure) / len(rows), 1),
                    "loop_accuracy": round(loop, 2), "always_s_accuracy": round(always_s, 2)}
    raise _fail("no threshold on the grid meets the rule")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the self-loop manifests (offline).")
    ap.add_argument("--write", action="store_true", help="freeze both manifests")
    args = ap.parse_args(argv)
    status = 0
    for student in STUDENTS:
        manifest, _ = build_manifest(student)
        print(f"{student}: manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} "
              f"attempts, datasets {manifest['dataset_counts']}")
        path = manifest_path(student)
        if args.write:
            if path.exists():
                raise _fail(f"{path} is frozen; delete it deliberately to rebuild")
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"  frozen -> {path}")
        elif path.exists():
            same = load_frozen_manifest(student) == manifest
            print(f"  frozen manifest {'matches' if same else 'DIFFERS'}")
            status |= 0 if same else 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
