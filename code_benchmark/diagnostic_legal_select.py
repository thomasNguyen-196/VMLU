"""The Legal MC "chọn rồi trả lời" test (openspec change diagnostic-legal-select; card MC-111).

Question: given BM25's top 10 units of MC-101's corpus for a Legal MC item, does Qwen3.5-9B select the article that
governs the question better than BM25's own top 2 (filter), and does answering from its own selection beat the
closed-book prompt on the pool (route)?

* Items: MC-101's 134-item pool, with MC-100's strata, support labels and oracle provisions. Not held out.
* Candidates (data/diagnostic_legal_select/candidates_v1.jsonl): the top 10 units of MC-101's frozen BM25 ranking,
  in rank order; each record's first two units must equal the item's MC-101 K evidence.
* Arms, two draws each. Round 1: B, K (MC-101's top 2), K10 (all 10), PICK (step 1: the selection prompt) and O
  (MC-100's oracle provisions, 53 items). Round 2: SEL (step 2: the K template with the units PICK selected; the
  frozen prompt when the selection is empty; MC-101's top 2 when it is unparsed), built from the round-1 rows.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_legal_select candidates [--write]
  .venv/bin/python -m code_benchmark.diagnostic_legal_select manifest [--write]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_legal_oracle as lo
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import diagnostic_retrieval as dr
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_oracle as lo
    import diagnostic_legal_retrieval as lr
    import diagnostic_prospective as dp
    import diagnostic_retrieval as dr
    import vi_multimodel as v1

ROOT = dp.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_select"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
TEMPLATE_PATH = DATA_DIR / "select_template_v1.json"
CANDIDATES_PATH = DATA_DIR / "candidates_v1.jsonl"
MANIFEST_PATH = DATA_DIR / "manifest_round1_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_select"
PROTOCOL_ID = "vmlu-diagnostic-legal-select"
PHASE = "legal-select"
DATASET = lo.DATASET
ROUND1_ARMS = ("B", "K", "K10", "PICK", "O")
ROUND2_ARMS = ("SEL",)
DEPTH = 10
MAX_PICKS = 2
CANDIDATE_KEYS = ("dataset_id", "item_id", "provisions", "ranking", "query_sha256", "corpus_sha256",
                  "retrieval_config_sha256")
TEMPLATE_KEYS = ("version", "head", "candidates_header", "question_header", "label")
SELECTION_STATUSES = ("picked", "none", "unparsed")
# The input hashes every manifest carries (and the runner's frozen keys, with manifest_sha256).
HASH_KEYS = ("legal_select_protocol_sha256", "select_template_sha256", "candidates_sha256",
             "campaign_protocol_sha256", "prompt_templates_sha256", "legal_retrieval_protocol_sha256",
             "sources_sha256", "corpus_sha256", "retrieval_config_sha256", "k_evidence_sha256",
             "oracle_evidence_sha256", "mc100_manifest_sha256", "source_sha256")
_LABEL = re.compile(r"^\s*đoạn liên quan\s*:(?P<rest>.*)$", re.IGNORECASE)
_STRIP = re.compile(r"[`*]")


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = _read_json(path, "legal-select protocol")
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-select protocol id/version")
    if protocol.get("dataset") != DATASET or protocol.get("draws") != 2:
        raise _fail(f"the legal-select protocol runs two draws of {DATASET}")
    if (protocol.get("candidates") or {}).get("depth") != DEPTH or \
            (protocol.get("selection") or {}).get("max_picks") != MAX_PICKS:
        raise _fail(f"the legal-select protocol shows {DEPTH} candidates and keeps at most {MAX_PICKS}")
    rounds = protocol.get("rounds") or {}
    if tuple(rounds.get("1") or ()) != ROUND1_ARMS or tuple(rounds.get("2") or ()) != ROUND2_ARMS:
        raise _fail(f"the legal-select rounds must be {list(ROUND1_ARMS)} then {list(ROUND2_ARMS)}")
    if set(protocol.get("arms", {})) != set(ROUND1_ARMS + ROUND2_ARMS):
        raise _fail("the legal-select protocol must describe exactly the arms of its two rounds")
    return protocol


def load_template(path: Path = TEMPLATE_PATH) -> dict[str, str]:
    template = _read_json(path, "selection template")
    if not isinstance(template, dict) or set(template) != set(TEMPLATE_KEYS):
        raise _fail(f"the selection template must have exactly the keys {list(TEMPLATE_KEYS)}")
    if not all(isinstance(template[key], str) and template[key] for key in TEMPLATE_KEYS):
        raise _fail("the selection template has an empty field")
    if "{n}" not in template["head"] or template["label"] not in template["head"]:
        raise _fail("the selection head must name the candidate count {n} and the answer label")
    return template


# ---------------------------------------------------------------- candidates

def candidate_record(index: dr.Index, item: v1.EvalItem, depth: int = DEPTH) -> dict[str, Any]:
    """The item's top `depth` units of MC-101's ranking, as provisions, with the hashes that tie them."""
    query = dr.mc_query(item)
    ranked = dr.rank(index, query)[:depth]
    if len(ranked) < depth:
        raise _fail(f"{item.item_id}: fewer than {depth} units share a token with the query")
    provisions = [{key: index.chunks[position][key] for key in dp.PROVISION_KEYS} for position, _ in ranked]
    return {"dataset_id": item.dataset_id, "item_id": item.item_id,
            "provisions": dp.validate_provisions(provisions, item.item_id, verbatim_source=True),
            "ranking": [{"chunk_id": index.chunks[position]["chunk_id"], "score": round(score, 6),
                         "text_sha256": index.chunks[position]["text_sha256"]} for position, score in ranked],
            "query_sha256": v1.sha256_bytes(query.encode("utf-8")),
            "corpus_sha256": index.corpus_sha256, "retrieval_config_sha256": index.config_sha256}


def load_candidates(path: Path, pool: list[str], index: dr.Index, k_evidence: dict[str, dict[str, Any]]
                    ) -> dict[str, dict[str, Any]]:
    """{item_id: record}; fails closed on shape, leakage, a gap, a changed corpus or configuration, a unit that is
    not the corpus unit its ranking names, or a top 2 that is not MC-101's K evidence."""
    by_id = {chunk["chunk_id"]: chunk for chunk in index.chunks}
    result: dict[str, dict[str, Any]] = {}
    for number, record in enumerate(_read_jsonl(path, "candidates"), 1):
        where = f"{path.name}:{number}"
        if set(record) != set(CANDIDATE_KEYS) or dp.FORBIDDEN_EVIDENCE_KEYS & set(record):
            raise _fail(f"{where}: record must have exactly the keys {list(CANDIDATE_KEYS)}")
        if record["dataset_id"] != DATASET or record["item_id"] in result:
            raise _fail(f"{where}: wrong dataset or a duplicate item")
        if (record["corpus_sha256"], record["retrieval_config_sha256"]) != (index.corpus_sha256, index.config_sha256):
            raise _fail(f"{where}: the corpus or retrieval configuration differs from the built index")
        dp.validate_provisions(record["provisions"], where, verbatim_source=True)
        if len(record["provisions"]) != DEPTH or len(record["ranking"]) != DEPTH:
            raise _fail(f"{where}: {len(record['provisions'])} candidates, not {DEPTH}")
        for provision, entry in zip(record["provisions"], record["ranking"], strict=True):
            chunk = by_id.get(entry["chunk_id"])
            if chunk is None or {key: chunk[key] for key in dp.PROVISION_KEYS} != provision:
                raise _fail(f"{where}: a candidate is not the corpus unit {entry['chunk_id']}")
        k_record = k_evidence.get(record["item_id"])
        if k_record is None or record["provisions"][:2] != k_record["provisions"] \
                or record["query_sha256"] != k_record["query_sha256"]:
            raise _fail(f"{where}: the first two candidates are not the item's MC-101 K evidence")
        result[record["item_id"]] = record
    if set(result) != set(pool):
        raise _fail(f"the candidates cover {len(result)} of {len(pool)} pool items")
    return result


def oracle_coverage(candidates: dict[str, dict[str, Any]], oracle: dict[str, dict[str, Any]], depth: int) -> int:
    """How many items with oracle provisions hold an oracle article among their first `depth` candidates."""
    covered = 0
    for item_id, record in oracle.items():
        if record["provisions"] and item_id in candidates:
            targets = lr.oracle_targets(record["provisions"])
            covered += any(lr.unit_target(entry["chunk_id"]) in targets
                           for entry in candidates[item_id]["ranking"][:depth])
    return covered


# ---------------------------------------------------------------- selection prompt and parser

def render_pick_prompt(item: v1.EvalItem, provisions: list[dict[str, Any]], template: dict[str, str],
                       campaign_templates: dict[str, str]) -> str:
    """Step 1: the head, the numbered candidates in the campaign's evidence-item format, then the question and
    options exactly as the frozen B prompt carries them."""
    if not provisions:
        raise _fail(f"{item.run_key}: a selection prompt needs candidates")
    rendered = [campaign_templates["evidence_item"].format(index=index, doc_title=p["doc_title"],
                                                           locator=p["locator"], text=p["text"])
                for index, p in enumerate(provisions, 1)]
    return (template["head"].format(n=len(provisions)) + template["candidates_header"]
            + campaign_templates["evidence_separator"].join(rendered)
            + template["question_header"] + dr.mc_query(item) + "\n")


def parse_pick(response: str, n: int = DEPTH) -> dict[str, Any]:
    """{"status": "picked" | "none" | "unparsed", "picks": [1-based candidate numbers]} from the last selection
    line; at most MAX_PICKS numbers within 1..n, in the order written, without duplicates."""
    text = _STRIP.sub("", unicodedata.normalize("NFC", str(response or "")))
    line = next((match for match in map(_LABEL.match, reversed(text.splitlines())) if match), None)
    if line is None:
        return {"status": "unparsed", "picks": []}
    rest = line.group("rest")
    picks: list[int] = []
    for token in re.findall(r"\d+", rest):
        number = int(token)
        if 1 <= number <= n and number not in picks:
            picks.append(number)
    if picks:
        return {"status": "picked", "picks": picks[:MAX_PICKS]}
    if "không có" in rest.casefold():
        return {"status": "none", "picks": []}
    return {"status": "unparsed", "picks": []}


def selection_provisions(selection: dict[str, Any], candidates: dict[str, Any], k_record: dict[str, Any]
                         ) -> list[dict[str, Any]] | None:
    """The units step 2 carries: the picked candidates; none for an empty selection; MC-101's top 2 for an
    unparsed one."""
    if selection["status"] == "picked":
        return [candidates["provisions"][number - 1] for number in selection["picks"]]
    if selection["status"] == "none":
        return None
    if selection["status"] == "unparsed":
        return list(k_record["provisions"])
    raise _fail(f"unknown selection status {selection['status']!r}")


# ---------------------------------------------------------------- manifests

@dataclasses.dataclass(frozen=True)
class Inputs:
    protocol: dict[str, Any]
    pool: list[str]
    mc100: dict[str, Any]
    index: dr.Index
    k_evidence: dict[str, dict[str, Any]]
    candidates: dict[str, dict[str, Any]]
    templates: dict[str, str]
    template: dict[str, str]
    frozen: dict[str, v1.EvalItem]


def load_inputs(candidates_path: Path = CANDIDATES_PATH) -> Inputs:
    protocol = load_protocol()
    pool = lr.pool_ids(lr.load_protocol())
    if len(pool) != protocol["pool"]["size"]:
        raise _fail(f"the pool has {len(pool)} items, not {protocol['pool']['size']}")
    index = lr.load_index()
    k_evidence = lr.load_k_evidence(lr.EVIDENCE_PATH, pool, index)
    return Inputs(protocol, pool, lr.mc100_frozen(), index, k_evidence,
                  load_candidates(candidates_path, pool, index, k_evidence), dp.load_templates(), load_template(),
                  lo.legal_items())


def _hashes(inputs: Inputs, candidates_path: Path) -> dict[str, Any]:
    hashes = {
        "legal_select_protocol_sha256": v1.sha256_file(PROTOCOL_PATH),
        "select_template_sha256": v1.sha256_file(TEMPLATE_PATH),
        "candidates_sha256": v1.sha256_file(candidates_path),
        "campaign_protocol_sha256": v1.sha256_file(dp.PROTOCOL_PATH),
        "prompt_templates_sha256": v1.sha256_file(dp.TEMPLATES_PATH),
        "legal_retrieval_protocol_sha256": v1.sha256_file(lr.PROTOCOL_PATH),
        "sources_sha256": v1.sha256_file(lr.SOURCES_PATH), "corpus_sha256": inputs.index.corpus_sha256,
        "retrieval_config_sha256": inputs.index.config_sha256, "k_evidence_sha256": v1.sha256_file(lr.EVIDENCE_PATH),
        "oracle_evidence_sha256": v1.sha256_file(lo.EVIDENCE_PATH),
        "mc100_manifest_sha256": inputs.mc100["manifest"]["manifest_sha256"],
        "source_sha256": inputs.mc100["manifest"]["source_sha256"],
    }
    if tuple(hashes) != HASH_KEYS:
        raise _fail("the manifest hash keys drifted from HASH_KEYS")
    return hashes


def build_round1(inputs: Inputs | None = None, candidates_path: Path = CANDIDATES_PATH
                 ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. Item-major: item, draw, arm; O only where MC-100 has
    provisions."""
    inputs = inputs or load_inputs(candidates_path)
    items: list[v1.EvalItem] = []
    for item_id in inputs.pool:
        base = inputs.frozen[item_id]
        candidates = inputs.candidates[item_id]["provisions"]
        prompts = {"B": base.prompt,
                   "K": dp.build_arm_prompt(base, "K", inputs.templates, inputs.k_evidence[item_id]["provisions"]),
                   "K10": dp.build_arm_prompt(base, "K", inputs.templates, candidates),
                   "PICK": render_pick_prompt(base, candidates, inputs.template, inputs.templates)}
        oracle = inputs.mc100["oracle"].get(item_id)
        if oracle and oracle["provisions"]:
            prompts["O"] = dp.build_arm_prompt(base, "O", inputs.templates, oracle["provisions"])
        for draw in range(1, inputs.protocol["draws"] + 1):
            for arm in ROUND1_ARMS:
                if arm in prompts:
                    items.append(dataclasses.replace(base, replicate_id=f"{arm}-r{draw}", prompt=prompts[arm]))
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate legal-select run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "round": 1,
        **_hashes(inputs, candidates_path),
        "pool": inputs.pool, "strata": inputs.mc100["strata"], "support": inputs.mc100["support"],
        "n": len(items), "item_count": len(inputs.pool), "dataset_counts": {DATASET: len(inputs.pool)},
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_round1(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return _read_json(path, "frozen legal-select round-1 manifest")


def build_round2(round1: dict[str, Any], rows: dict[str, dict[str, Any]], inputs: Inputs | None = None
                 ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map) of SEL, from the round-1 rows {run_key: latest row}. Every PICK attempt
    must be complete; draw r of SEL uses draw r of PICK. Self-hashed; the parsed selections are recorded."""
    inputs = inputs or load_inputs()
    picks = [ref for ref in round1["items"] if dp.arm_of_replicate(ref["replicate_id"]) == "PICK"]
    selections: dict[str, dict[str, Any]] = {}
    items: list[v1.EvalItem] = []
    for ref in picks:
        key = dp.run_key(ref)
        row = rows.get(key)
        if row is None or row.get("status") != "complete" or row.get("prompt_sha256") != ref["prompt_sha256"]:
            raise _fail(f"round 2 needs every PICK attempt complete; {key} is not")
        selection = parse_pick(str(row.get("raw_response") or ""))
        item_id, draw = ref["item_id"], ref["replicate_id"].partition("-r")[2]
        provisions = selection_provisions(selection, inputs.candidates[item_id], inputs.k_evidence[item_id])
        base = inputs.frozen[item_id]
        prompt = dp.build_arm_prompt(base, "K", inputs.templates, provisions) if provisions else base.prompt
        items.append(dataclasses.replace(base, replicate_id=f"SEL-r{draw}", prompt=prompt))
        selections[key] = {**selection, "response_sha256": v1.sha256_bytes(str(row.get("raw_response") or "").encode())}
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items) or len(items) != len(inputs.pool) * inputs.protocol["draws"]:
        raise _fail("round 2 must hold one SEL attempt per pool item and draw")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "round": 2,
        "round1_manifest_sha256": round1["manifest_sha256"],
        **{key: round1[key] for key in HASH_KEYS},
        "pool": inputs.pool, "selections": selections,
        "selection_counts": dict(sorted(Counter(s["status"] for s in selections.values()).items())),
        "n": len(items), "item_count": len(inputs.pool), "dataset_counts": {DATASET: len(inputs.pool)},
        "arm_counts": {"SEL": len(items)},
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Legal MC selection test (offline helpers).")
    sub = ap.add_subparsers(dest="command", required=True)
    candidates = sub.add_parser("candidates", help="rank the corpus for every pool item and keep the top 10")
    candidates.add_argument("--write", action="store_true", help=f"freeze them as {CANDIDATES_PATH}")
    manifest = sub.add_parser("manifest", help="build the round-1 manifest and compare it with the frozen one")
    manifest.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    load_protocol()
    if args.command == "candidates":
        pool = lr.pool_ids(lr.load_protocol())
        index = lr.load_index()
        items = lo.legal_items()
        records = {item_id: candidate_record(index, items[item_id]) for item_id in pool}
        k_evidence = lr.load_k_evidence(lr.EVIDENCE_PATH, pool, index)
        oracle = lr.mc100_frozen()["oracle"]
        with_provisions = sum(bool(record["provisions"]) for record in oracle.values())
        coverage = {depth: oracle_coverage(records, oracle, depth) for depth in (2, 5, DEPTH)}
        chars = [sum(len(p["text"]) for p in record["provisions"]) for record in records.values()]
        print(f"candidates for {len(records)} items; oracle coverage of {with_provisions} items: {coverage}; "
              f"characters mean {round(sum(chars) / len(chars))} max {max(chars)}")
        if args.write:
            if CANDIDATES_PATH.exists():
                raise _fail(f"{CANDIDATES_PATH} is frozen; delete it deliberately to rebuild")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            v1.write_jsonl_atomic(CANDIDATES_PATH, [records[item_id] for item_id in pool])
            load_candidates(CANDIDATES_PATH, pool, index, k_evidence)
            print(f"frozen -> {CANDIDATES_PATH} sha256={v1.sha256_file(CANDIDATES_PATH)}")
    else:
        built, _ = build_round1()
        print(f"legal-select round-1 manifest {built['manifest_sha256']}: {built['n']} attempts {built['arm_counts']}")
        if args.write:
            if MANIFEST_PATH.exists():
                raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
            MANIFEST_PATH.write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"frozen -> {MANIFEST_PATH}")
        elif MANIFEST_PATH.exists():
            same = load_frozen_round1() == built
            print(f"frozen manifest {'matches' if same else 'DIFFERS'}")
            return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
