"""K2: ViBidLQA questions asked without their passage, BM25 top-2 retrieval from a frozen passage corpus, and the
K2 calibration procedure (openspec change diagnostic-k2-retrieval, specs `diagnostic-k2-retrieval` and
`diagnostic-k2-router`; card MC-96).

* Items: the ViBidLQA train questions that appear once across the splits and are not in MC-95, asked as dataset
  `bidlqa-train-retrieval`. The 360 lowest sha256(seed, dataset:item) ranks form the set and the 60 lowest of them
  are the calibration items.
* Corpus: the unique passages of the three pinned splits (id = SHA-256 of the normalized text, id order). The
  corpus v0 tokenizer with bigrams and its BM25 rank them for the question; the two best are kept.
* Arms, two draws each: B closed book (the protocol's prompt); K, the frozen reading prompt with the two passages in
  the passage slot; KS, the frozen S reading prompt on them; O, the frozen reading prompt with the item's own
  passage (a ceiling, never deployable).
* Procedure: always-B, always-K, the K cascade (K twice; KS when the two answers differ) and always-KS are scored by
  mean token-F1 on the calibration items; a tie goes to the more thorough candidate (the later in the list), and the
  choice becomes a rule of the closed router grammar.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_k2            # build the manifest and compare it with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_k2 --write    # freeze data/diagnostic_k2/heldout_k2.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from code_benchmark import diagnostic_calibration as cal
    from code_benchmark import diagnostic_heldout as dh
    from code_benchmark import diagnostic_heldout_v3 as h3
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import diagnostic_router as router
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_calibration as cal
    import diagnostic_heldout as dh
    import diagnostic_heldout_v3 as h3
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import diagnostic_router as router
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_k2"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
RETRIEVAL_PATH = DATA_DIR / "retrieval_k2.json"
PROCEDURE_PATH = DATA_DIR / "procedure_k2.json"
MANIFEST_PATH = DATA_DIR / "heldout_k2.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
EXCLUDED_MANIFEST = h3.MANIFEST_PATH  # MC-95
PROTOCOL_ID = "vmlu-diagnostic-k2-heldout"
PHASE = "heldout"
DATASET = "bidlqa-train-retrieval"
ARMS = ("B", "K", "KS", "O")
POOL_SIZE = 1488
CORPUS_SIZE = 863
RETRIEVAL_FIXED = {"unit": "passage", "query": "question", "bigrams": True, "top_k": 2, "tie_break": "corpus order",
                   "passage_separator": "\n\n", "bm25": {"k1": 1.2, "b": 0.75}}
PROCEDURE_KEYS = ("procedure_id", "description", "candidates", "calibration_items", "score", "tie", "equal_within",
                  "probe")
CANDIDATES = ("always_B", "always_K", "k_cascade", "always_KS")  # least to most thorough
SCORE = {"reading": "mean_token_f1"}
TIE = ["more_thorough"]
PROBE = {"arm": "K", "samples": 2, "agreement": "normalized-answer-v1"}
K_TARGETS = sorted(router.ADDRESSABLE["K"])
KS_TARGETS = sorted(router.ADDRESSABLE["KS"])


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json_bytes(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


# ---------------------------------------------------------------- frozen configuration

def load_retrieval_config(path: Path = RETRIEVAL_PATH) -> tuple[dict[str, Any], str]:
    """The retrieval configuration and the SHA-256 of its bytes; any other unit, query, top-k or tokenizer fails."""
    config, digest = _read_json_bytes(path, "K2 retrieval configuration")
    if not isinstance(config, dict):
        raise _fail(f"{path.name} must be a JSON object")
    for key, expected in RETRIEVAL_FIXED.items():
        value = config.get(key)
        if key == "bm25":
            value = {name: (value or {}).get(name) for name in expected} if isinstance(value, dict) else None
        if value != expected:
            raise _fail(f"{path.name}: {key} must be {expected!r}, not {config.get(key)!r}")
    return config, digest


def validate_procedure(procedure: Any) -> dict[str, Any]:
    if not isinstance(procedure, dict) or set(procedure) != set(PROCEDURE_KEYS):
        raise _fail(f"the K2 procedure must have exactly the keys {list(PROCEDURE_KEYS)}")
    if not isinstance(procedure["procedure_id"], str) or not procedure["procedure_id"].strip():
        raise _fail("the K2 procedure lacks a procedure_id")
    if not isinstance(procedure["description"], str):
        raise _fail("the K2 procedure description must be text")
    if procedure["candidates"] != list(CANDIDATES):
        raise _fail(f"the candidates must be exactly {list(CANDIDATES)}, least to most thorough")
    size = procedure["calibration_items"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise _fail("calibration_items must be a positive integer")
    if procedure["score"] != SCORE:
        raise _fail(f"the score must be {SCORE}")
    if procedure["tie"] != TIE:
        raise _fail(f"the tie rule must be {TIE}: equal scores go to the more thorough candidate")
    within = procedure["equal_within"]
    if isinstance(within, bool) or not isinstance(within, (int, float)) or not 0 <= within < 1e-6:
        raise _fail("equal_within must be a number in [0, 1e-6)")
    router._check_probe(procedure["probe"])  # noqa: SLF001  # the grammar's own probe check
    if procedure["probe"] != PROBE:
        raise _fail(f"the K cascade probes with {PROBE}")
    return procedure


def load_procedure(path: Path = PROCEDURE_PATH) -> tuple[dict[str, Any], str]:
    """The validated procedure and the SHA-256 of its bytes (the value the registration records)."""
    procedure, digest = _read_json_bytes(path, "K2 calibration procedure")
    return validate_procedure(procedure), digest


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol, _ = _read_json_bytes(path, "K2 protocol")
    if not isinstance(protocol, dict) or protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported K2 protocol id/version")
    campaign = dp.load_protocol()
    differing = [block for block in dh.MIRRORED if protocol.get(block) != campaign.get(block)]
    if differing:
        raise _fail(f"the K2 protocol's {differing} differ from the campaign protocol")
    phase = (protocol.get("phases") or {}).get(PHASE) or {}
    if phase.get("arms") != list(ARMS) or phase.get("replicates") != 2:
        raise _fail(f"the K2 phase runs arms {list(ARMS)} with 2 replicates")
    if protocol.get("datasets") != [DATASET] or set(protocol.get("sampling") or {}) != {DATASET}:
        raise _fail(f"the K2 protocol samples the one dataset {DATASET}")
    spec = protocol["sampling"][DATASET]
    size = load_procedure()[0]["calibration_items"]
    if spec.get("calibration") != size or not spec.get("n", 0) > size or spec.get("strata") != "none":
        raise _fail(f"the K2 sample must hold the procedure's {size} calibration items and test items, unstratified")
    closed = (protocol.get("prompts") or {}).get("closed_book") or {}
    if set(closed) != {"head", "question", "tail"} or not all(isinstance(closed[key], str) and closed[key] for key in closed):
        raise _fail("the K2 protocol needs the closed-book prompt as head, question label and tail")
    return protocol


# ---------------------------------------------------------------- corpus and retrieval

def passage_id(context: str) -> str:
    return v1.sha256_bytes(v1.normalized_key(context).encode("utf-8"))


def _source_rows() -> list[list[dict[str, Any]]]:
    """The pinned ViBidLQA rows in the order train, val, test."""
    splits = [v1.load_bidlqa_source(h3.BIDLQA_TRAIN_SOURCE, h3.PINNED[h3.BIDLQA_TRAIN_SOURCE])]
    for split in ("val", "test"):
        config = v1.bidlqa_split_config(split)
        splits.append(v1.load_bidlqa_source(dp.ROOT / config["source"], config["sha"]))
    return splits


def source_sha256() -> dict[str, str]:
    paths = [h3.BIDLQA_TRAIN_SOURCE, *(dp.ROOT / v1.bidlqa_split_config(split)["source"] for split in ("val", "test"))]
    return {str(Path(path).relative_to(dp.ROOT)): v1.sha256_file(Path(path)) for path in paths}


def load_corpus() -> list[dict[str, str]]:
    """[{passage_id, text}] in id order; a passage's text is its first raw form in the order train, val, test."""
    first: dict[str, str] = {}
    for rows in _source_rows():
        for row in rows:
            first.setdefault(passage_id(str(row["context"])), str(row["context"]))
    if len(first) != CORPUS_SIZE:
        raise _fail(f"the ViBidLQA passage corpus has {len(first)} passages, not {CORPUS_SIZE}")
    return [{"passage_id": key, "text": first[key]} for key in sorted(first)]


@dataclasses.dataclass(frozen=True)
class Retriever:
    corpus: list[dict[str, str]]
    bm25: dr.BM25
    config: dict[str, Any]
    config_sha256: str
    corpus_sha256: str


def build_retriever(config: dict[str, Any] | None = None, config_sha256: str | None = None,
                    corpus: list[dict[str, str]] | None = None) -> Retriever:
    if config is None or config_sha256 is None:
        config, config_sha256 = load_retrieval_config()
    corpus = corpus if corpus is not None else load_corpus()
    bm25 = dr.BM25([dr.tokenize(p["text"], config["bigrams"]) for p in corpus], config["bm25"]["k1"], config["bm25"]["b"])
    return Retriever(corpus, bm25, config, config_sha256, v1.sha256_bytes(v1.canonical_json(corpus)))


def ranking(retriever: Retriever, question: str) -> list[tuple[int, float]]:
    """(corpus position, score) for every passage with a positive score, best first; ties keep corpus order."""
    scores = retriever.bm25.scores(dr.tokenize(question, retriever.config["bigrams"]))
    return sorted(((position, score) for position, score in enumerate(scores) if score > 0),
                  key=lambda pair: (-pair[1], pair[0]))


def retrieval_record(retriever: Retriever, item: v1.EvalItem) -> dict[str, Any]:
    """The kept passages and scores and the rank of the item's own passage (None when it shares no token)."""
    ranked = ranking(retriever, item.question)
    top = ranked[:retriever.config["top_k"]]
    if len(top) < retriever.config["top_k"]:
        raise _fail(f"{item.item_id}: fewer than {retriever.config['top_k']} passages share a token with the question")
    ids = [retriever.corpus[position]["passage_id"] for position, _ in ranked]
    return {"passages": [retriever.corpus[position]["passage_id"] for position, _ in top],
            "scores": [round(score, 6) for _, score in top],
            "own_rank": ids.index(item.passage_id) + 1 if item.passage_id in ids else None}


# ---------------------------------------------------------------- items and prompts

def excluded_keys(path: Path = EXCLUDED_MANIFEST) -> set[str]:
    """The ViBidLQA train item ids of MC-95, from its self-hashed frozen manifest."""
    manifest, _ = _read_json_bytes(path, "MC-95 manifest")
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != v1.sha256_bytes(v1.canonical_json(unhashed)):
        raise _fail(f"{path.name} does not match its own manifest_sha256")
    return {row["item_id"] for row in manifest["items"] if row["dataset_id"] == h3.BIDLQA}


def load_pool() -> list[v1.EvalItem]:
    """The closed-book pool as dataset bidlqa-train-retrieval. Each item's prompt is the frozen reading prompt with
    its own passage (the O prompt); the closed-book and retrieved prompts are built per arm."""
    used = excluded_keys()
    pool = [dataclasses.replace(item, dataset_id=DATASET) for item in h3.load_bidlqa_train() if item.item_id not in used]
    if len(pool) != POOL_SIZE:
        raise _fail(f"the K2 pool has {len(pool)} items, not {POOL_SIZE}")
    return pool


def sample_items(protocol: dict[str, Any]) -> tuple[list[v1.EvalItem], list[str]]:
    """(the sampled items, the calibration item keys): the lowest sha256(seed, dataset:item) ranks."""
    spec = protocol["sampling"][DATASET]
    picked = dh._ranked(load_pool(), spec["seed"])[:spec["n"]]  # noqa: SLF001
    return picked, [dp.item_key(item.dataset_id, item.item_id) for item in picked[:spec["calibration"]]]


def closed_book_prompt(question: str, protocol: dict[str, Any]) -> str:
    closed = protocol["prompts"]["closed_book"]
    return closed["head"] + closed["question"] + question + closed["tail"]


def arm_prompts(item: v1.EvalItem, passages: list[str], protocol: dict[str, Any], templates: dict[str, str],
                separator: str) -> dict[str, str]:
    """{arm: prompt}. K puts the retrieved passages where the frozen reading prompt has its passage, KS is the frozen
    S reading prompt on them, O is the item's own prompt. No prompt carries the gold answer."""
    context = separator.join(text.strip() for text in passages)
    retrieved = dataclasses.replace(item, prompt=v1.build_reading_prompt(context, item.question))
    return {"B": closed_book_prompt(item.question, protocol), "K": retrieved.prompt,
            "KS": dp.build_arm_prompt(retrieved, "S", templates), "O": item.prompt}


def request_item(item: v1.EvalItem, protocol: dict[str, Any]) -> v1.EvalItem:
    """The closed-book request the router reads: dataset, B prompt and question, never a passage."""
    return dataclasses.replace(item, prompt=closed_book_prompt(item.question, protocol))


def request_features(item: v1.EvalItem, protocol: dict[str, Any]) -> router.Features:
    request = request_item(item, protocol)
    return router.Features(request.dataset_id, len(request.prompt), router.fold(request.question))


def build_manifest(protocol: dict[str, Any] | None = None, protocol_path: Path = PROTOCOL_PATH
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed like the campaign manifests. Item-major: item, draw, arm."""
    protocol = protocol or load_protocol(protocol_path)
    config, config_digest = load_retrieval_config()
    templates = dp.load_templates()
    retriever = build_retriever(config, config_digest)
    text_of = {passage["passage_id"]: passage["text"] for passage in retriever.corpus}
    base, calibration = sample_items(protocol)
    items: list[v1.EvalItem] = []
    retrieval: dict[str, dict[str, Any]] = {}
    for item in base:
        key = dp.item_key(item.dataset_id, item.item_id)
        record = retrieval[key] = retrieval_record(retriever, item)
        prompts = arm_prompts(item, [text_of[pid] for pid in record["passages"]], protocol, templates,
                              config["passage_separator"])
        for draw in range(1, protocol["phases"][PHASE]["replicates"] + 1):
            for arm in ARMS:
                items.append(dataclasses.replace(item, replicate_id=f"{arm}-r{draw}", prompt=prompts[arm]))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate K2 run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        "k2_protocol_sha256": v1.sha256_file(protocol_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "retrieval_config_sha256": config_digest,
        "corpus_sha256": retriever.corpus_sha256, "corpus_passages": len(retriever.corpus),
        "excluded_manifest_sha256": v1.sha256_file(EXCLUDED_MANIFEST),
        "source_sha256": source_sha256(),
        "n": len(items), "item_count": len(base),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in base).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "calibration_items": calibration,
        "retrieval": retrieval,
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest, _ = _read_json_bytes(path, "frozen K2 manifest")
    return manifest


def base_items(rebuilt: dict[str, v1.EvalItem]) -> list[v1.EvalItem]:
    """One item per K2 question (its O prompt), in manifest order, from the rebuilt run-key map."""
    seen: dict[str, v1.EvalItem] = {}
    for item in rebuilt.values():
        if item.replicate_id == "O-r1":
            seen[dp.item_key(item.dataset_id, item.item_id)] = dataclasses.replace(item, replicate_id=dp.MAIN_REPLICATE)
    return list(seen.values())


# ---------------------------------------------------------------- the procedure on one rotation

def outcome(candidate: str, b: dict[str, Any], k: dict[str, Any], k2: dict[str, Any], ks: dict[str, Any]
            ) -> tuple[dict[str, Any], int | None]:
    """(the attempt the candidate returns, its reported tokens with the probe) for one item and rotation."""
    if candidate == "always_B":
        return b, cal._tokens(b)  # noqa: SLF001
    if candidate == "always_K":
        return k, cal._tokens(k)  # noqa: SLF001
    if candidate == "always_KS":
        return ks, cal._tokens(ks)  # noqa: SLF001
    if candidate != "k_cascade":
        raise _fail(f"unknown K2 candidate {candidate!r}")
    agree = router.answers_agree(str(k.get("prediction") or ""), str(k2.get("prediction") or ""), "reading")
    return (k, cal._tokens(k, k2)) if agree else (ks, cal._tokens(k, k2, ks))  # noqa: SLF001


def choose(procedure: dict[str, Any], cells: Iterable[tuple[dict[str, Any], ...]]) -> dict[str, Any]:
    """Score the candidates on the calibration cells (b, k, k2, ks per item, one rotation) and choose: the highest
    mean token-F1, equal scores (within equal_within) going to the more thorough candidate."""
    cells = list(cells)
    if len(cells) != procedure["calibration_items"]:
        raise _fail(f"a K2 calibration sample has {procedure['calibration_items']} items, not {len(cells)}")
    scores: dict[str, float] = {}
    tokens: dict[str, float | None] = {}
    for candidate in CANDIDATES:
        returned = [outcome(candidate, *cell) for cell in cells]
        scores[candidate] = statistics.fmean(cal.score_of(row, "reading") for row, _ in returned)
        known = [spent for _, spent in returned if spent is not None]
        tokens[candidate] = statistics.fmean(known) if len(known) == len(returned) else None
    best = max(scores.values())
    tied = [candidate for candidate in CANDIDATES if best - scores[candidate] <= procedure["equal_within"]]
    return {"items": len(cells), "score": SCORE["reading"], "scores": scores, "mean_tokens": tokens,
            "tied": tied, "choice": tied[-1]}


def emit_rule(procedure: dict[str, Any], choice: str, rule_id: str) -> dict[str, Any]:
    """The choice as a rule of the closed grammar on the K2 dataset; the K probe only for the cascade. Default B."""
    when = {"dataset": [DATASET]}
    if choice == "always_B":
        conditions = [{"arm": "B", "targets": [], "when": when, "note": "calibration chose always-B (closed book)"}]
    elif choice == "always_K":
        conditions = [{"arm": "K", "targets": K_TARGETS, "when": when, "note": "calibration chose always-K"}]
    elif choice == "always_KS":
        conditions = [{"arm": "KS", "targets": KS_TARGETS, "when": when, "note": "calibration chose always-KS"}]
    elif choice == "k_cascade":
        conditions = [
            {"arm": "KS", "targets": KS_TARGETS, "when": {**when, "probe": "disagree"},
             "note": "calibration chose the K cascade: the two K answers differ"},
            {"arm": "K", "targets": K_TARGETS, "when": when,
             "note": "calibration chose the K cascade: the two K answers agree"},
        ]
    else:
        raise _fail(f"unknown K2 choice {choice!r}")
    rule: dict[str, Any] = {"router_id": rule_id,
                            "description": f"emitted by {procedure['procedure_id']} from its calibration sample"}
    if choice == "k_cascade":
        rule["probe"] = dict(procedure["probe"])
    rule["conditions"] = conditions
    rule["default"] = {"arm": "B", "targets": []}
    return router.validate_rule(rule, [DATASET])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the K2 manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    calibration = set(manifest["calibration_items"])
    for role, keys in (("calibration", calibration), ("test", set(manifest["retrieval"]) - calibration)):
        ranks = [manifest["retrieval"][key]["own_rank"] for key in keys]
        print(f"{role}: {len(keys)} items, own passage at rank 1 for {sum(rank == 1 for rank in ranks)}, "
              f"in the top 2 for {sum(rank is not None and rank <= 2 for rank in ranks)}")
    print(f"K2 manifest {manifest['manifest_sha256']}: {manifest['item_count']} items, {manifest['n']} attempts, "
          f"arms {manifest['arm_counts']}, corpus {manifest['corpus_passages']} passages {manifest['corpus_sha256'][:12]}…")
    if args.write:
        if MANIFEST_PATH.exists():
            raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"frozen -> {MANIFEST_PATH}")
    elif MANIFEST_PATH.exists():
        same = load_frozen_manifest() == manifest
        print(f"frozen manifest {'matches' if same else 'DIFFERS'}")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
