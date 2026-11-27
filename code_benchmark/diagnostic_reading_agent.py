"""MC-118 inputs (openspec change diagnostic-reading-agent), offline: the long-file reading corpus, its passage index,
the prompts, the protocol, the manifest of five arms × two draws on the 400 Reading-400 items, the BM25
retrievability strata, the smoke questions and the judge sample.

The corpus is every distinct passage of the two source files Reading-400 was drawn from (viSQuAD and Vi-DROP),
deduplicated on `vi_multimodel.normalized_key`, ordered by the SHA-256 of that key and written 50 to a file under a
`## Đoạn NNNN` heading, one sentence per line (`wrap`). The agent gets the question without its passage (MC-96's closed-book prompt after the reading
DSHF instruction) and must find the passage in the folder, as the legal agent found its provision.

From the repo root:
  .venv/bin/python -m code_benchmark.diagnostic_reading_agent corpus [--write-index]   # build the folder, print hashes
  .venv/bin/python -m code_benchmark.diagnostic_reading_agent inputs                   # retrievability, smoke, judge files
  .venv/bin/python -m code_benchmark.diagnostic_reading_agent manifest [--write]       # build (and freeze) the manifest
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_legal_agent_v2 as l2
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import run_legal_agent as rla
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_legal_agent_v2 as l2  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import run_legal_agent as rla  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "diagnostic_reading_agent"
WORK_ROOT = ROOT / "all_res" / "diagnostic_reading_agent"
CORPUS_FOLDER = WORK_ROOT / "corpus_v1"
PROTOCOL_PATH = DATA_DIR / "protocol.json"
PROMPTS_PATH = DATA_DIR / "agent_prompts_v1.json"
INDEX_PATH = DATA_DIR / "corpus_index_v1.json"
RETRIEVABILITY_PATH = DATA_DIR / "retrievability_v1.json"
SMOKE_PATH = DATA_DIR / "smoke_questions_v1.json"
JUDGE_SAMPLE_PATH = DATA_DIR / "judge_sample_v1.json"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-reading-agent"
PHASE = "reading-agent"
ARMS = ("DSHF", "OMPF", "OMPS", "C", "O")
AGENT_ARMS = ("DSHF", "OMPF", "OMPS")
DIRECT_ARMS = ("C", "O")
DRAWS = (1, 2)
MODELS = ("qwen", "mimo")
SEED = 7
GROUP_SIZE = 50
WORKDIR = "/work/bai-viet"
FILE_NAME = "bai-viet-{:02d}.txt"
HEADING = "## Đoạn {:04d}"
LINE_LIMIT = 600
SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=\S)")
SOURCES = {"squad": (ROOT / "vmlu_squad_v1/vi_squad_benchmark_question_only.json", "id"),
           "drop": (ROOT / "vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json", "question_id")}
DATASET_OF = {"squad": "vi-multimodel-v1-vi-squad-200", "drop": "vi-multimodel-v1-vi-drop-200"}
PROMPTS_VERSION = "diagnostic-reading-agent-prompts-v1"
PROTOCOL_KEYS = ("protocol_id", "protocol_version", "change", "purpose", "arms", "draws", "items", "sources", "corpus",
                 "workdir", "prompts", "models", "scoring", "operational", "smoke", "judge", "analysis")
MODEL_KEYS = ("model_id", "profile_id", "route_card", "base_protocol", "base_protocol_sha256", "route",
              "omps_prompt_file", "omps_prompt_sha256", "pins", "budget_tokens", "direct")
PIN_KEYS = ("dsh_system_sha256", "ompf_system_sha256", "omps_system_sha256")
JUDGE_ITEMS = 100


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _sha_checked(path: Path, sha256: str, label: str) -> str:
    if not path.is_file() or v1.sha256_file(path) != sha256:
        raise _fail(f"{label} {path} is missing or differs from its registered SHA-256")
    return sha256


def _seeded(*parts: object) -> random.Random:
    return random.Random(int(hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16], 16))


# ---------------------------------------------------------------- the corpus

def load_passages(sources: dict[str, tuple[Path, str]] = SOURCES) -> dict[str, dict[str, Any]]:
    """{normalized key: {text, sources}}: every distinct context of the source files, first spelling kept, outer
    whitespace trimmed, in source order."""
    out: dict[str, dict[str, Any]] = {}
    for name, (path, _) in sources.items():
        for row in json.loads(path.read_text(encoding="utf-8"))["data"]:
            key = v1.normalized_key(row["context"])
            if not key:
                continue
            entry = out.setdefault(key, {"text": str(row["context"]).strip(), "sources": []})
            if name not in entry["sources"]:
                entry["sources"].append(name)
    return out


def wrap(text: str, limit: int = LINE_LIMIT) -> str:
    """One sentence per line, as a law has one clause per line (owner's choice, 2026-11-25): the whitespace after a
    sentence end becomes a line break, and a longer sentence breaks at its last space before `limit` characters. Only
    whitespace changes, so `vi_multimodel.normalized_key` of the result equals that of the source text. No line exceeds
    omp's 768-character line cut or dsh's 2,000."""
    out = []
    for paragraph in text.split("\n"):
        for sentence in SENTENCE.split(paragraph) if paragraph.strip() else [paragraph]:
            while len(sentence) > limit:
                cut = sentence.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                out.append(sentence[:cut])
                sentence = sentence[cut:].lstrip(" ")
            out.append(sentence)
    return "\n".join(out)


def layout(passages: dict[str, dict[str, Any]], group_size: int = GROUP_SIZE) -> list[dict[str, Any]]:
    """The passage index: number, file, heading line, first and last line, passage_id (as `vi_multimodel` computes
    it), text SHA-256 and sources, in the SHA-256 order of the normalized key."""
    order = sorted(passages, key=lambda key: hashlib.sha256(key.encode("utf-8")).hexdigest())
    index, line = [], 1
    for position, key in enumerate(order):
        if position % group_size == 0:
            line = 1
        text = wrap(passages[key]["text"])
        lines = text.count("\n") + 1
        index.append({"number": position + 1, "file": FILE_NAME.format(position // group_size + 1),
                      "heading_line": line, "first_line": line + 1, "last_line": line + lines,
                      "passage_id": v1.sha256_bytes(key.encode("utf-8")),
                      "text_sha256": v1.sha256_bytes(text.encode("utf-8")), "chars": len(text),
                      "sources": passages[key]["sources"]})
        line += lines + 2  # the heading, the passage, then a blank line
    return index


def file_texts(passages: dict[str, dict[str, Any]], index: list[dict[str, Any]]) -> dict[str, str]:
    by_id = {v1.sha256_bytes(key.encode("utf-8")): wrap(entry["text"]) for key, entry in passages.items()}
    files: dict[str, list[str]] = defaultdict(list)
    for entry in index:
        files[entry["file"]].append(f"{HEADING.format(entry['number'])}\n{by_id[entry['passage_id']]}\n\n")
    return {name: "".join(parts) for name, parts in files.items()}


def build_corpus(folder: Path, sources: dict[str, tuple[Path, str]] = SOURCES) -> dict[str, Any]:
    """Write the corpus to `folder`/docs and return {folder_sha256, index, files, passages, chars}."""
    passages = load_passages(sources)
    index = layout(passages)
    docs = folder / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    if any(docs.iterdir()):
        raise _fail(f"{docs} is not empty")
    texts = file_texts(passages, index)
    for name, text in texts.items():
        (docs / name).write_text(text, encoding="utf-8")
    for entry in index:  # every recorded line range must hold its passage
        lines = texts[entry["file"]].split("\n")
        if lines[entry["heading_line"] - 1] != HEADING.format(entry["number"]):
            raise _fail(f"passage {entry['number']}: the heading is not on line {entry['heading_line']}")
        written = "\n".join(lines[entry["first_line"] - 1:entry["last_line"]])
        if v1.sha256_bytes(v1.normalized_key(written).encode("utf-8")) != entry["passage_id"]:
            raise _fail(f"passage {entry['number']}: lines {entry['first_line']}-{entry['last_line']} differ from it")
    return {"folder_sha256": rla.listing_sha256(docs), "index": index, "files": len(texts), "passages": len(index),
            "chars": sum(len(text) for text in texts.values())}


def load_index(path: Path = INDEX_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["passages"]


# ---------------------------------------------------------------- items and prompts

def base_items() -> list[v1.EvalItem]:
    """The 400 Reading-400 items as vi-multimodel v1 builds them (frozen reading prompt, reviewed gold)."""
    items = v1._load_reading400()  # noqa: SLF001 - the registered loader, reused unchanged
    if len(items) != 400:
        raise _fail(f"Reading-400 must hold 400 items, found {len(items)}")
    return items


def passage_of(items: list[v1.EvalItem], index: list[dict[str, Any]]) -> dict[str, int]:
    """{dataset_id:item_id: passage number}; every item must map to exactly one passage."""
    numbers = {entry["passage_id"]: entry["number"] for entry in index}
    out = {}
    for item in items:
        if item.passage_id not in numbers:
            raise _fail(f"{item.dataset_id}:{item.item_id}: its passage is not in the corpus")
        out[f"{item.dataset_id}:{item.item_id}"] = numbers[item.passage_id]
    return out


def load_prompts(path: Path = PROMPTS_PATH, root: Path = ROOT) -> dict[str, Any]:
    """The reading DSHF instruction, MC-112's separator and MC-96's closed-book prompt, the last two read from their
    own files by registered SHA-256."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("version") != PROMPTS_VERSION or not str(spec.get("DSHF") or "").strip():
        raise _fail(f"{path.name} must be version {PROMPTS_VERSION} with a DSHF instruction")
    separator = json.loads(_read_checked(root / spec["separator"]["file"], spec["separator"]["sha256"],
                                         "MC-112's prompt file"))["separator"]
    closed = json.loads(_read_checked(root / spec["closed_book"]["file"], spec["closed_book"]["sha256"],
                                      "MC-96's protocol"))["prompts"]["closed_book"]
    if set(closed) != {"head", "question", "tail"}:
        raise _fail("MC-96's closed-book prompt must have head, question and tail")
    return {"version": spec["version"], "separator": separator, "DSHF": spec["DSHF"], "closed_book": closed}


def _read_checked(path: Path, sha256: str, label: str) -> str:
    _sha_checked(path, sha256, label)
    return path.read_text(encoding="utf-8")


def agent_task(question: str, prompts: dict[str, Any]) -> str:
    """DSHF's task (OMPF and OMPS send it byte for byte): the instruction, a blank line, MC-96's closed-book prompt."""
    return prompts["DSHF"] + prompts["separator"] + l2.closed_book_prompt(question, prompts)


def arm_prompt(arm: str, item: v1.EvalItem, prompts: dict[str, Any]) -> str:
    if arm in AGENT_ARMS:
        return agent_task(item.question, prompts)
    if arm == "C":
        return l2.closed_book_prompt(item.question, prompts)
    if arm == "O":
        return item.prompt
    raise _fail(f"unknown arm {arm!r}")


def arm_order(item_key: str, draw: int) -> list[str]:
    """The five arms in an order permuted by seed 7 for this item and draw."""
    order: list[str] = list(ARMS)
    _seeded(SEED, item_key, draw).shuffle(order)
    return order


def expand(items: list[v1.EvalItem], prompts: dict[str, Any]) -> list[v1.EvalItem]:
    """Item-major: per item, draw 1 then draw 2, the arms in their seeded order."""
    out = []
    for item in items:
        key = f"{item.dataset_id}:{item.item_id}"
        for draw in DRAWS:
            for arm in arm_order(key, draw):
                out.append(dataclasses.replace(item, replicate_id=f"{arm}-r{draw}",
                                               prompt=arm_prompt(arm, item, prompts)))
    return out


# ---------------------------------------------------------------- protocol and manifest

def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict) or set(protocol) != set(PROTOCOL_KEYS):
        raise _fail(f"the reading-agent protocol must have exactly the keys {list(PROTOCOL_KEYS)}")
    if (protocol["protocol_id"], protocol["protocol_version"]) != (PROTOCOL_ID, 1):
        raise _fail("unsupported reading-agent protocol id or version")
    if tuple(protocol["arms"]) != ARMS or tuple(protocol["draws"]) != DRAWS or protocol["workdir"] != WORKDIR:
        raise _fail(f"the protocol must run {ARMS} at draws {DRAWS} in {WORKDIR}")
    if set(protocol["models"]) != set(MODELS) or any(set(spec) != set(MODEL_KEYS) or set(spec["pins"]) != set(PIN_KEYS)
                                                     for spec in protocol["models"].values()):
        raise _fail(f"the protocol must specify {MODELS}, each with the keys {list(MODEL_KEYS)} and pins {PIN_KEYS}")
    return protocol


def model_spec(protocol: dict[str, Any], model: str) -> dict[str, Any]:
    if model not in protocol["models"]:
        raise _fail(f"unknown model {model!r}; expected one of {MODELS}")
    return protocol["models"][model]


def input_hashes(protocol: dict[str, Any], root: Path = ROOT, protocol_path: Path = PROTOCOL_PATH) -> dict[str, str]:
    hashes = {"reading_agent_protocol_sha256": v1.sha256_file(protocol_path),
              "corpus_folder_sha256": protocol["corpus"]["folder_sha256"]}
    for name in ("manifest", "gold"):
        hashes[f"reading400_{name}_sha256"] = _sha_checked(root / protocol["items"][name],
                                                           protocol["items"][f"{name}_sha256"], f"Reading-400 {name}")
    for name, spec in protocol["sources"].items():
        hashes[f"source_{name}_sha256"] = _sha_checked(root / spec["file"], spec["sha256"], f"source {name}")
    hashes["corpus_index_sha256"] = _sha_checked(root / protocol["corpus"]["index"], protocol["corpus"]["index_sha256"],
                                                 "corpus index")
    hashes["prompts_sha256"] = _sha_checked(root / protocol["prompts"]["file"], protocol["prompts"]["sha256"], "prompts")
    for model in MODELS:
        spec = model_spec(protocol, model)
        hashes[f"{model}_base_protocol_sha256"] = _sha_checked(root / spec["base_protocol"], spec["base_protocol_sha256"],
                                                               f"{model} base protocol")
        hashes[f"{model}_omps_prompt_sha256"] = _sha_checked(root / spec["omps_prompt_file"], spec["omps_prompt_sha256"],
                                                             f"{model} OMPS prompt")
    return hashes


def build_manifest(protocol: dict[str, Any] | None = None, root: Path = ROOT,
                   protocol_path: Path = PROTOCOL_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed. One manifest serves both models."""
    protocol = protocol or load_protocol(protocol_path)
    prompts = load_prompts(root / protocol["prompts"]["file"], root)
    items = base_items()
    index = load_index(root / protocol["corpus"]["index"])
    passages = passage_of(items, index)
    expanded = expand(items, prompts)
    out = {item.run_key: item for item in expanded}
    if len(out) != len(expanded) or len(expanded) != len(items) * len(ARMS) * len(DRAWS):
        raise _fail("duplicate or missing reading-agent run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE,
        **input_hashes(protocol, root, protocol_path), "passage_of": passages,
        "n": len(expanded), "item_count": len(items),
        "dataset_counts": dict(sorted(Counter(item.dataset_id for item in items).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in expanded).items())),
        "items": [v1.manifest_item(item) for item in expanded],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, out


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- descriptive inputs fixed before data

def bm25_ranks(passages: list[str], queries: list[str], k1: float = 1.5, b: float = 0.75) -> list[list[int]]:
    """For each query, passage positions sorted by BM25 score (vi-reading tokens), best first; ties by position."""
    docs = [Counter(v1.tokenize_vi(text)) for text in passages]
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / len(lengths)
    frequency = Counter(term for doc in docs for term in doc)
    n = len(docs)
    idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}
    out = []
    for query in queries:
        terms = [t for t in set(v1.tokenize_vi(query)) if t in idf]
        scores = []
        for position, doc in enumerate(docs):
            norm = k1 * (1 - b + b * lengths[position] / average)
            score = sum(idf[t] * doc[t] * (k1 + 1) / (doc[t] + norm) for t in terms if t in doc)
            scores.append((-score, position))
        out.append([position for _, position in sorted(scores)])
    return out


def retrievability(items: list[v1.EvalItem], index: list[dict[str, Any]],
                   passages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_id = {v1.sha256_bytes(key.encode("utf-8")): entry["text"] for key, entry in passages.items()}
    texts = [by_id[entry["passage_id"]] for entry in index]
    position = {entry["passage_id"]: i for i, entry in enumerate(index)}
    ranks = bm25_ranks(texts, [item.question for item in items])
    out = {}
    for item, order in zip(items, ranks, strict=True):
        rank = order.index(position[item.passage_id]) + 1
        out[f"{item.dataset_id}:{item.item_id}"] = {"rank": rank,
                                                    "stratum": "top1" if rank == 1 else "top5" if rank <= 5 else "beyond"}
    return {"method": "BM25 (k1 1.5, b 0.75) over the corpus passages with vi-reading tokens; the question as query",
            "items": out, "counts": dict(sorted(Counter(v["stratum"] for v in out.values()).items()))}


def smoke_questions(items: list[v1.EvalItem], per_source: int = 2) -> list[dict[str, Any]]:
    """Questions outside Reading-400 whose passages no Reading-400 item uses, by seed 7, two per source set."""
    used_items = {(item.source_dataset, item.item_id) for item in items}
    used_passages = {item.passage_id for item in items}
    out = []
    for name, (path, key) in SOURCES.items():
        candidates = []
        for row in json.loads(path.read_text(encoding="utf-8"))["data"]:
            pid = v1.sha256_bytes(v1.normalized_key(row["context"]).encode("utf-8"))
            if (name, str(row[key])) in used_items or pid in used_passages:
                continue
            candidates.append((hashlib.sha256(f"{SEED}:{name}:{row[key]}".encode()).hexdigest(), str(row[key]),
                               str(row["question"]), pid))
        for _, item_id, question, pid in sorted(candidates)[:per_source]:
            out.append({"id": f"smoke-{name}-{item_id}", "source": name, "item_id": item_id, "question": question,
                        "passage_id": pid})
    return out


def judge_sample(items: list[v1.EvalItem], n: int = JUDGE_ITEMS) -> list[str]:
    """100 item keys by seed 7: 50 viSQuAD and 50 Vi-DROP, the Vi-DROP half allocated over its categories by largest
    remainder."""
    rng = random.Random(SEED)
    half = n // 2
    squad = sorted(f"{i.dataset_id}:{i.item_id}" for i in items if i.source_dataset == "squad")
    drop: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if item.source_dataset == "drop":
            drop[item.stratum].append(f"{item.dataset_id}:{item.item_id}")
    total = sum(len(keys) for keys in drop.values())
    quotas = {stratum: half * len(keys) / total for stratum, keys in drop.items()}
    counts = {stratum: int(q) for stratum, q in quotas.items()}
    for stratum in sorted(quotas, key=lambda s: (-(quotas[s] - counts[s]), s))[:half - sum(counts.values())]:
        counts[stratum] += 1
    picked = rng.sample(squad, half)
    for stratum in sorted(drop):
        picked += rng.sample(sorted(drop[stratum]), counts[stratum])
    return sorted(picked)


def write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return v1.sha256_file(path)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MC-118 inputs, offline.")
    commands = parser.add_subparsers(dest="command", required=True)
    corpus = commands.add_parser("corpus", help="build the corpus folder and print its hashes")
    corpus.add_argument("--write-index", action="store_true", help="write corpus_index_v1.json")
    commands.add_parser("inputs", help="write the retrievability, smoke and judge-sample files")
    build = commands.add_parser("manifest", help="build the manifest and print its counts")
    build.add_argument("--write", action="store_true", help="freeze it to manifest_v1.json")
    args = parser.parse_args(argv)
    if args.command == "corpus":
        built = build_corpus(CORPUS_FOLDER)
        print(f"passages={built['passages']} files={built['files']} chars={built['chars']} "
              f"folder_sha256={built['folder_sha256']}")
        if args.write_index:
            sha = write_json(INDEX_PATH, {"version": "reading-corpus-v1", "group_size": GROUP_SIZE, "workdir": WORKDIR,
                                          "folder_sha256": built["folder_sha256"], "passages": built["index"]})
            print(f"wrote {INDEX_PATH} sha256 {sha}")
        return 0
    if args.command == "inputs":
        items, index, passages = base_items(), load_index(), load_passages()
        passage_of(items, index)
        for path, value in ((RETRIEVABILITY_PATH, retrievability(items, index, passages)),
                            (SMOKE_PATH, {"version": "reading-agent-smoke-v1", "questions": smoke_questions(items)}),
                            (JUDGE_SAMPLE_PATH, {"version": "reading-agent-judge-sample-v1", "seed": SEED,
                                                 "items": judge_sample(items)})):
            print(f"wrote {path.name} sha256 {write_json(path, value)}")
        return 0
    protocol = load_protocol()
    manifest, _ = build_manifest(protocol)
    print(f"items={manifest['item_count']} attempts={manifest['n']} arms={manifest['arm_counts']} "
          f"datasets={manifest['dataset_counts']} manifest_sha256={manifest['manifest_sha256']}")
    if args.write:
        if MANIFEST_PATH.is_file() and load_frozen_manifest() != manifest:
            raise _fail(f"{MANIFEST_PATH} exists and differs; a frozen manifest is never overwritten")
        print(f"wrote {MANIFEST_PATH} sha256 {write_json(MANIFEST_PATH, manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
