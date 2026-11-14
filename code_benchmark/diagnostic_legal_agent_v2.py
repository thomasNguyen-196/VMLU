"""MC-114 (planned): corpus_v2 and the new items for the legal agent test (dsh and omp searching a legal folder).

corpus_v2 is MC-112's corpus_v1 (310 files, byte for byte) plus the 25 pages of
`data/diagnostic_legal_agent_v2/added_documents_v2.json`: the 23 documents the VMLU law-item coverage audit
(2026-11-14) needed, and Luật Đấu thầu 2023 with its Nghị định 24/2024 for the ViBidLQA items. File layout and
checks are MC-112's (`diagnostic_legal_agent.build_folder`); the build also fails unless every corpus_v1 file comes
out with its corpus_v1 SHA-256.

Items:

* VMLU law items: the 112 gold items of subjects 37–42 and 45 (dev 33 + valid 79), with the frozen MC prompt.
* ViBidLQA closed-book: items whose context is an article of Luật Đấu thầu 22/2023/QH15 and whose question appears
  once across train, val and test, kept when the article the context names exists in the official text with the
  same title and holds the answer verbatim (NFC, whitespace squashed). The decree half is left out: its contexts
  follow a draft whose article numbers and wording differ from the issued Nghị định 24/2024.

Provisions (`item_provisions_v2.jsonl`, MC-112's keys): VMLU items from the audit's four batches, the owner's
spot-check labels replacing the agent's; `no_provision` items have none. ViBidLQA items: the heading line of the
article their context names.

    python -m code_benchmark.diagnostic_legal_agent_v2 items
    python -m code_benchmark.diagnostic_legal_agent_v2 folder --out <dir>
    python -m code_benchmark.diagnostic_legal_agent_v2 provisions --folder <dir>
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_heldout_v3 as dh3
    from code_benchmark import diagnostic_legal_agent as la
    from code_benchmark import diagnostic_legal_retrieval as lr
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # pragma: no cover - run from code_benchmark/
    import diagnostic_heldout_v3 as dh3  # type: ignore[no-redef]
    import diagnostic_legal_agent as la  # type: ignore[no-redef]
    import diagnostic_legal_retrieval as lr  # type: ignore[no-redef]
    import diagnostic_prospective as dp  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

ROOT = la.ROOT
DATA_DIR = ROOT / "data" / "diagnostic_legal_agent_v2"
WORK_ROOT = ROOT / "all_res" / "diagnostic_legal_agent_v2"
ADDED_PATH = DATA_DIR / "added_documents_v2.json"
PROVISIONS_PATH = DATA_DIR / "item_provisions_v2.jsonl"
AUDIT_DIR = WORK_ROOT / "audit"
STORE = "mc114"
STORES = {**la.STORES, STORE: WORK_ROOT / "sources"}
CORPUS_V1 = la.WORK_ROOT / "corpus_v1"
CORPUS_V1_FOLDER_SHA256 = "5f3240a216be2eb48c88fb7873d03076071ff7462a37bb627317b0ca70b4f3f3"

VMLU_LAW_SUBJECTS = (37, 38, 39, 40, 41, 42, 45)
VMLU_LAW_ITEMS = 112
SUPPORT = ("supports_gold", "contradicts_gold", "unclear", "no_provision")
BIDDING_LAW_URL = "https://hethongphapluat.com/luat-dau-thau-2023.html"
BIDDING_LAW_FILE = la.file_name(BIDDING_LAW_URL)
BIDLQA_SPLITS = ("train", "val", "test")
_BIDLQA_LAW_HEAD = re.compile(r"^Luật Đấu thầu số 22/2023/QH15\s+Điều\s+(\d+)\.\s*(.*?)\s+khoản\s+(\S+?)\s*\.\s*(.*)$",
                              re.DOTALL)
_ARTICLE_NUMBER = re.compile(r"\d+[a-zđ]?")
# Audit provisions that are not an article: (item, the audit's `article` field) -> a whole line of the file.
NON_ARTICLE_ANCHORS: dict[tuple[str, str], str] = {
    ("41-0015", "Phụ lục IV"): "PHỤ LỤC IV",  # Nghị định 108/2006: Danh mục lĩnh vực cấm đầu tư
}
# Items left out of the leak check, each because its stem is the law's own wording, not copied benchmark text.
LEAK_EXEMPT = {
    "vmlu-mqa-dev:37-0003": "the stem 'Biện pháp xử lý hành chính khác' (31 characters) is a chapter and article "
                            "heading of Pháp lệnh xử lý vi phạm hành chính 2002 (corpus_v1, Điều 22)",
}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def squash(text: str) -> str:
    return " ".join(la.nfc(text).split())


# ---------------------------------------------------------------- documents and folder

def load_documents(added_path: Path = ADDED_PATH) -> list[dict[str, Any]]:
    """corpus_v1's documents, then the pages added for MC-114 (store mc114): one entry per file."""
    documents = la.load_documents()
    for d in json.loads(added_path.read_text(encoding="utf-8"))["documents"]:
        if d["store"] != STORE:
            raise _fail(f"{d['url']}: an MC-114 page must come from store {STORE}, not {d['store']!r}")
        documents.append({"url": d["url"], "doc_id": d["doc_id"], "title": d["title"], "store": STORE,
                          "origin": "added-v2", "items": d["items"]})
    urls = [d["url"] for d in documents]
    if len(set(urls)) != len(urls):
        raise _fail("a page is listed twice")
    return documents


def changed_v1_files(manifest: dict[str, Any], v1_manifest: dict[str, Any]) -> list[str]:
    """corpus_v1 files missing from a new folder or carrying another SHA-256 there."""
    by_file = {row["file"]: row["sha256"] for row in manifest["files"]}
    return [row["file"] for row in v1_manifest["files"] if by_file.get(row["file"]) != row["sha256"]]


def build_corpus(out_dir: Path) -> dict[str, Any]:
    v1_manifest = json.loads((CORPUS_V1 / "folder_manifest.json").read_text(encoding="utf-8"))
    if v1_manifest["folder_sha256"] != CORPUS_V1_FOLDER_SHA256:
        raise _fail("corpus_v1's folder manifest is not MC-112's")
    checked = [item for item in [*la.pool_items(), *vmlu_items()]
               if f"{item.dataset_id}:{item.item_id}" not in LEAK_EXEMPT]
    manifest = la.build_folder(load_documents(), la.load_mc101_articles(), checked, out_dir, STORES)
    manifest["leak_exempt"] = LEAK_EXEMPT
    changed = changed_v1_files(manifest, v1_manifest)
    if changed:
        raise _fail(f"{len(changed)} corpus_v1 files differ in {out_dir}, e.g. {changed[:3]}; delete it and look")
    corpus = "\n".join(squash((out_dir / "docs" / row["file"]).read_text(encoding="utf-8")).lower()
                       for row in manifest["files"])
    verbatim = [bid.item_id for bid in bidlqa_items() if squash(bid.item.question).lower() in corpus]
    manifest.update(corpus_v1_files_unchanged=len(v1_manifest["files"]),
                    added_v2=sum(row["origin"] == "added-v2" for row in manifest["files"]),
                    bidlqa_questions_verbatim_in_corpus=verbatim)
    return manifest


# ---------------------------------------------------------------- items

def vmlu_items() -> list[v1.EvalItem]:
    items = [item for split in ("dev", "valid") for item in v1._load_vmlu(split)  # noqa: SLF001
             if int(item.item_id.split("-")[0]) in VMLU_LAW_SUBJECTS]
    if len(items) != VMLU_LAW_ITEMS or len({item.item_id for item in items}) != VMLU_LAW_ITEMS:
        raise _fail(f"{len(items)} VMLU law items, not {VMLU_LAW_ITEMS} distinct ones")
    return items


@dataclasses.dataclass(frozen=True)
class BidItem:
    """A usable ViBidLQA item: the project's frozen item (its prompt is the frozen reading prompt with the item's own
    passage, its question the text earlier cards sent) and the article of Luật Đấu thầu 2023 its context names."""
    item: v1.EvalItem
    split: str
    article: str
    title: str
    clause: str

    @property
    def dataset_id(self) -> str:
        return self.item.dataset_id

    @property
    def item_id(self) -> str:
        return self.item.item_id


def law_context(context: str) -> tuple[str, str, str] | None:
    """(article, title, clause) of a Luật Đấu thầu context header, or None for any other context."""
    match = _BIDLQA_LAW_HEAD.match(squash(context))
    return (match.group(1), match.group(2), match.group(3)) if match else None


def usable(article: str, title: str, answer: str, articles: dict[str, str]) -> bool:
    """The named article exists with the same title and holds the answer verbatim."""
    text = articles.get(article)
    return text is not None and text.startswith(f"Điều {article}. {title}") and squash(answer) in text


def _split_rows(split: str) -> tuple[list[tuple[v1.EvalItem, dict[str, Any]]], list[dict[str, Any]]]:
    """((frozen item, source row) per item, every source row) of a split, with the ids and prompts the project
    already uses: main-v1's loader for val and test, MC-95's for train (which drops repeated questions itself)."""
    if split == "train":
        rows = v1.load_bidlqa_source(dh3.BIDLQA_TRAIN_SOURCE, dh3.PINNED[dh3.BIDLQA_TRAIN_SOURCE])
        pairs = [(item, rows[int(item.item_id.removeprefix("BIDLQA-TR-")) - 1]) for item in dh3.load_bidlqa_train()]
        return pairs, rows
    config = v1.bidlqa_split_config(split)
    rows = v1.load_bidlqa_source(ROOT / config["source"], config["sha"])
    return list(zip(v1._load_bidlqa(split), rows, strict=True)), rows  # noqa: SLF001 - manifest ids, source order


def bidlqa_items(articles: dict[str, str] | None = None) -> list[BidItem]:
    if articles is None:
        page = lr.stored_page(BIDDING_LAW_URL, STORES[STORE])
        articles = {number: squash(text) for number, text in lr.parse_articles_v1(page)}
    loaded = {split: _split_rows(split) for split in BIDLQA_SPLITS}
    counts = Counter(v1.normalized_key(str(row["question"])) for split in BIDLQA_SPLITS for row in loaded[split][1])
    out = []
    for split in BIDLQA_SPLITS:
        for item, row in loaded[split][0]:
            if squash(item.question) != squash(str(row["question"])):
                raise _fail(f"{item.item_id}: the frozen item's question is not its source row's")
            head = law_context(str(row["context"]))
            if head is None or counts[v1.normalized_key(str(row["question"]))] != 1:
                continue
            article, title, clause = head
            if usable(article, title, str(row["answer"]), articles):
                out.append(BidItem(item, split, article, title, clause))
    if len({(item.dataset_id, item.item_id) for item in out}) != len(out):
        raise _fail("two ViBidLQA items share a key")
    return out


# ---------------------------------------------------------------- provisions

def heading_line(lines: Sequence[str], article: str) -> str | None:
    """MC-112's article heading line, or a bare one (`Điều 84`, `Điều 9[1]`): a constitution's articles have no
    titles, so a consolidated text prints the number alone."""
    bare = re.compile(rf"^Điều {re.escape(article)}(\[\d+\])?$")
    return la.article_line(lines, article) or next((line for line in lines if bare.match(line)), None)


def _page_url(url: str) -> str:
    """The document page of an audit URL that points at one article (`<slug>/dieu-26`)."""
    return re.sub(r"/dieu-[^/]*$", ".html", url) if "/dieu-" in url else url


def vmlu_provisions(docs_dir: Path, batches: dict[int, list[dict[str, Any]]], dataset_of: dict[str, str],
                    owner_labels: dict[str, str], reviewer: str,
                    non_article: dict[tuple[str, str], str] = NON_ARTICLE_ANCHORS) -> list[dict[str, Any]]:
    """Each VMLU item's provisions as (file, anchor line). The audit's `part` describes a point or paragraph inside
    the article, so it goes into the locator only. Fails closed on an anchor that is not a whole line of its file."""
    cache: dict[str, list[str]] = {}

    def lines(name: str) -> list[str]:
        if name not in cache:
            path = docs_dir / name
            cache[name] = path.read_text(encoding="utf-8").split("\n") if path.is_file() else []
        return cache[name]

    out, errors = [], []
    for number, rows in sorted(batches.items()):
        for x in rows:
            if x["support"] not in SUPPORT or (x["support"] == "no_provision") != (not x["provisions"]):
                errors.append((x["item_id"], "support", x["support"]))
            provisions = []
            for p in x["provisions"]:
                article = str(p.get("article") or "").strip()
                if p.get("in_folder"):
                    name = p["file"]
                elif p.get("url"):
                    name = la.file_name(_page_url(p["url"]))
                else:
                    errors.append((x["item_id"], "no file or url", article))
                    continue
                if _ARTICLE_NUMBER.fullmatch(article):
                    anchor = heading_line(lines(name), article)
                    locator = f"Điều {article}"
                else:
                    anchor = non_article.get((x["item_id"], article))
                    locator = article
                locator = ", ".join(part for part in [locator, *map(str, p.get("clauses") or []), p.get("part")]
                                    if part)
                if not anchor or anchor not in lines(name):
                    errors.append((x["item_id"], name, str(anchor)))
                    continue
                provisions.append({"file": name, "doc_id": p["doc_id"], "locator": locator, "anchor_line": anchor})
            owner = owner_labels.get(x["item_id"])
            if owner is not None and owner not in SUPPORT:
                errors.append((x["item_id"], "owner label", owner))
            out.append({"dataset_id": dataset_of[x["item_id"]], "item_id": x["item_id"], "support": owner or x["support"],
                        "label_source": f"owner:{reviewer}" if owner else "agent",
                        "located_by": f"mc114:audit-batch-{number}", "provisions": provisions})
    ids = [row["item_id"] for row in out]
    if errors or len(set(ids)) != len(ids):
        raise _fail(f"VMLU provisions: {len(errors)} problems {errors[:3]}, {len(ids) - len(set(ids))} items twice")
    return sorted(out, key=lambda row: row["item_id"])


def bidlqa_provisions(docs_dir: Path, items: list[BidItem]) -> list[dict[str, Any]]:
    lines = (docs_dir / BIDDING_LAW_FILE).read_text(encoding="utf-8").split("\n")
    out = []
    for item in items:
        anchor = la.article_line(lines, item.article)
        if not anchor or not anchor.startswith(f"Điều {item.article}. {item.title}"):
            raise _fail(f"{item.item_id}: Điều {item.article} has no heading line {item.title!r} in {BIDDING_LAW_FILE}")
        out.append({"dataset_id": item.dataset_id, "item_id": item.item_id, "support": "supports_gold",
                    "label_source": "dataset", "located_by": "vibidlqa:context-header",
                    "provisions": [{"file": BIDDING_LAW_FILE, "doc_id": "22/2023/QH15",
                                    "locator": f"Điều {item.article}, {item.clause}", "anchor_line": anchor}]})
    return out


def write_provisions(folder: Path, out: Path = PROVISIONS_PATH, audit_dir: Path = AUDIT_DIR) -> list[dict[str, Any]]:
    manifest = json.loads((folder / "folder_manifest.json").read_text(encoding="utf-8"))
    docs_dir = folder / "docs"
    changed = [row["file"] for row in manifest["files"]
               if v1.sha256_bytes((docs_dir / row["file"]).read_bytes()) != row["sha256"]]
    if changed or len(list(docs_dir.iterdir())) != len(manifest["files"]):
        raise _fail(f"{folder} differs from its manifest: {changed[:3]}")
    batches = {n: json.loads((audit_dir / f"located_batch_{n}.json").read_text(encoding="utf-8"))["items"]
               for n in range(1, 5)}
    review_path = audit_dir / "review_labels.json"
    if not review_path.is_file():
        raise _fail(f"{review_path} is missing: the owner's spot-check labels come first")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    owner = {row["item_id"]: row["owner_label"] for row in review["items"]}
    dataset_of = {item.item_id: item.dataset_id for item in vmlu_items()}
    rows = [*vmlu_provisions(docs_dir, batches, dataset_of, owner, review["reviewer"]),
            *bidlqa_provisions(docs_dir, bidlqa_items())]
    problems = la.check_provisions(rows, docs_dir)
    if problems:
        raise _fail(f"provisions: {problems[:3]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps({key: row[key] for key in la.PROVISION_KEYS}, ensure_ascii=False) + "\n"
                           for row in rows), encoding="utf-8")
    return rows


# ---------------------------------------------------------------- protocol, prompts, sample and manifest (MC-114)

PROTOCOL_PATH = DATA_DIR / "protocol.json"
PROMPTS_PATH = DATA_DIR / "agent_prompts_v2.json"
MANIFEST_PATH = DATA_DIR / "manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-legal-agent-v2"
PHASE = "legal-agent-v2"
AGENT_ARMS = ("DSH", "DSHF", "OMPF")
PART_ARMS = {"M": ("DSH", "DSHF", "OMPF", "B"), "S": ("DSH", "DSHF", "OMPF", "C", "O")}
INSTRUCTION_OF = {"DSH": "DSH", "DSHF": "DSHF", "OMPF": "DSHF"}  # OMPF sends DSHF's task, byte for byte


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID or protocol.get("protocol_version") != 1:
        raise _fail("unsupported legal-agent-v2 protocol id or version")
    parts = protocol.get("parts") or {}
    if {name: tuple(spec.get("arms") or ()) for name, spec in parts.items()} != PART_ARMS or protocol.get("draws") != 2:
        raise _fail(f"the legal-agent-v2 protocol must run parts {PART_ARMS} with two draws")
    size = parts["S"].get("size")
    if not isinstance(size, int) or size < 1 or not parts["S"].get("sample_salt"):
        raise _fail("part S needs a positive size and a sample salt")
    return protocol


def _verified(path: Path, sha256: str, label: str) -> bytes:
    raw = path.read_bytes()
    if v1.sha256_bytes(raw) != sha256:
        raise _fail(f"{label} {path} differs from its registered SHA-256")
    return raw


def load_prompts(path: Path = PROMPTS_PATH) -> dict[str, Any]:
    """Prompts v2, resolved: MC-112's instructions and separator, and MC-96's closed-book prompt, each read from its
    own file by registered SHA-256, so they are reused byte for byte rather than copied."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("version") != "diagnostic-legal-agent-prompts-v2" or spec.get("instruction_of") != INSTRUCTION_OF:
        raise _fail("agent_prompts_v2.json must be version diagnostic-legal-agent-prompts-v2 with OMPF on DSHF's task")
    instructions = json.loads(_verified(ROOT / spec["instructions"]["file"], spec["instructions"]["sha256"],
                                        "MC-112's prompt file"))
    closed = json.loads(_verified(ROOT / spec["closed_book"]["file"], spec["closed_book"]["sha256"],
                                  "MC-96's protocol"))["prompts"]["closed_book"]
    if set(closed) != {"head", "question", "tail"}:
        raise _fail("MC-96's closed-book prompt must have head, question and tail")
    return {"version": spec["version"], "separator": instructions["separator"], "DSH": instructions["DSH"],
            "DSHF": instructions["DSHF"], "closed_book": closed, "instruction_of": INSTRUCTION_OF}


def closed_book_prompt(question: str, prompts: dict[str, Any]) -> str:
    """MC-96's closed-book prompt (`diagnostic_k2.closed_book_prompt`), byte for byte."""
    closed = prompts["closed_book"]
    return closed["head"] + closed["question"] + question + closed["tail"]


def agent_task(arm: str, item_prompt: str, prompts: dict[str, Any]) -> str:
    """MC-112's task layout (`diagnostic_legal_agent.arm_task`): the instruction, a blank line, the item prompt."""
    return prompts[prompts["instruction_of"][arm]] + prompts["separator"] + item_prompt


def arm_prompt(part: str, arm: str, item: v1.EvalItem, prompts: dict[str, Any]) -> str:
    """The text an arm sends for an item. Part M: agents get their task around the frozen MC prompt; B sends that
    prompt. Part S: agents get their task around the closed-book prompt; C sends it alone; O sends the item's frozen
    reading prompt with its own passage."""
    if part == "M":
        return agent_task(arm, item.prompt, prompts) if arm in AGENT_ARMS else item.prompt
    closed = closed_book_prompt(item.question, prompts)
    if arm in AGENT_ARMS:
        return agent_task(arm, closed, prompts)
    return closed if arm == "C" else item.prompt


def sample_order(bids: list[BidItem], salt: str) -> list[BidItem]:
    return sorted(bids, key=lambda bid: v1.sha256_bytes(f"{salt}{bid.dataset_id}:{bid.item_id}".encode("utf-8")))


def part_s_items(protocol: dict[str, Any], bids: list[BidItem] | None = None) -> list[BidItem]:
    spec = protocol["parts"]["S"]
    bids = bidlqa_items() if bids is None else bids
    if spec.get("usable") is not None and len(bids) != spec["usable"]:
        raise _fail(f"{len(bids)} usable ViBidLQA items, not the registered {spec['usable']}")
    if len(bids) < spec["size"]:
        raise _fail(f"only {len(bids)} usable ViBidLQA items for a sample of {spec['size']}")
    return sample_order(bids, spec["sample_salt"])[:spec["size"]]


def load_provisions(path: Path = PROVISIONS_PATH) -> dict[str, dict[str, Any]]:
    return la.load_provisions(path)


def expand(protocol: dict[str, Any], prompts: dict[str, Any], parts: dict[str, list[v1.EvalItem]]
           ) -> list[v1.EvalItem]:
    """Item-major: part M, then part S; per item, the part's arms for draw 1, then for draw 2."""
    out = []
    for part in ("M", "S"):
        for item in parts[part]:
            for draw in range(1, protocol["draws"] + 1):
                for arm in PART_ARMS[part]:
                    out.append(dataclasses.replace(item, replicate_id=f"{arm}-r{draw}",
                                                   prompt=arm_prompt(part, arm, item, prompts)))
    return out


def input_hashes(protocol: dict[str, Any]) -> dict[str, str]:
    """SHA-256 of every frozen input the manifest stands on."""
    prompts_spec = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    hashes = {
        "legal_agent_v2_protocol_sha256": v1.sha256_file(PROTOCOL_PATH),
        "agent_prompts_v2_sha256": v1.sha256_file(PROMPTS_PATH),
        "mc112_prompts_sha256": prompts_spec["instructions"]["sha256"],
        "mc96_protocol_sha256": prompts_spec["closed_book"]["sha256"],
        "provisions_sha256": v1.sha256_file(PROVISIONS_PATH),
        "added_documents_v2_sha256": v1.sha256_file(ADDED_PATH),
        "folder_sha256": protocol["corpus"]["folder_sha256"],
        "fetch_log_sha256": v1.sha256_file(STORES[STORE] / "fetch_log.jsonl"),
        "review_labels_sha256": v1.sha256_file(AUDIT_DIR / "review_labels.json"),
        **{f"audit_batch_{n}_sha256": v1.sha256_file(AUDIT_DIR / f"located_batch_{n}.json") for n in range(1, 5)},
    }
    for name, spec in protocol["harnesses"].items():
        for key in ("protocol", "registration"):
            hashes[f"{name}_{key}_sha256"] = _sha_checked(ROOT / spec[key], spec[f"{key}_sha256"], f"{name} {key}")
    for name, spec in protocol["reference"].items():
        hashes[f"{name}_sha256"] = _sha_checked(ROOT / spec["path"], spec["sha256"], name)
    return hashes


def _sha_checked(path: Path, sha256: str, label: str) -> str:
    if not path.is_file() or v1.sha256_file(path) != sha256:
        raise _fail(f"{label} {path} is missing or differs from its registered SHA-256")
    return sha256


def build_manifest(protocol: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    """(manifest, rebuilt run-key map), self-hashed."""
    protocol = protocol or load_protocol()
    prompts = load_prompts()
    vmlu = vmlu_items()
    bids = part_s_items(protocol)
    provisions = load_provisions()
    missing = [item.item_id for item in [*vmlu, *(bid.item for bid in bids)] if item.item_id not in provisions]
    if missing:
        raise _fail(f"{len(missing)} items have no provisions row, e.g. {missing[:3]}")
    parts = {"M": vmlu, "S": [bid.item for bid in bids]}
    items = expand(protocol, prompts, parts)
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate legal-agent-v2 run keys")
    part_of = {f"{item.dataset_id}:{item.item_id}": part for part, rows in parts.items() for item in rows}
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, **input_hashes(protocol),
        "parts": {part: [f"{item.dataset_id}:{item.item_id}" for item in rows] for part, rows in parts.items()},
        "part_s_splits": dict(sorted(Counter(bid.split for bid in bids).items())),
        "part_s_articles": {f"{bid.dataset_id}:{bid.item_id}": bid.article for bid in bids},
        "support": {key: provisions[key.split(":", 1)[1]]["support"] for key in part_of},
        "n": len(items), "item_count": len(part_of),
        "dataset_counts": dict(sorted(Counter(key.split(":", 1)[0] for key in part_of).items())),
        "arm_counts": dict(sorted(Counter(dp.arm_of_replicate(item.replicate_id) for item in items).items())),
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MC-114 inputs, offline: corpus_v2, the new items and their "
                                                 "provisions.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("items", help="count the VMLU law items and the usable ViBidLQA items")
    folder = commands.add_parser("folder", help="write corpus_v2")
    folder.add_argument("--out", type=Path, required=True, help="new directory; the files go to <out>/docs")
    provisions = commands.add_parser("provisions", help="write each new item's provisions with anchor lines")
    provisions.add_argument("--folder", type=Path, required=True, help="a folder written by `folder`")
    provisions.add_argument("--out", type=Path, default=PROVISIONS_PATH)
    manifest_cmd = commands.add_parser("manifest", help="build the manifest and compare it with the frozen one")
    manifest_cmd.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = parser.parse_args(argv)
    if args.command == "items":
        vmlu, bid = vmlu_items(), bidlqa_items()
        sample = part_s_items(load_protocol(), bid) if PROTOCOL_PATH.is_file() else []
        print(f"VMLU law items {len(vmlu)} {dict(Counter(item.dataset_id for item in vmlu))}; ViBidLQA usable "
              f"{len(bid)} {dict(Counter(item.split for item in bid))}, articles {len({i.article for i in bid})}; "
              f"part S sample {len(sample)} {dict(Counter(item.split for item in sample))}")
        return 0
    if args.command == "manifest":
        manifest, _ = build_manifest()
        frozen = load_frozen_manifest() if MANIFEST_PATH.is_file() else None
        print(f"items={manifest['item_count']} attempts={manifest['n']} arms={manifest['arm_counts']} "
              f"datasets={manifest['dataset_counts']} manifest_sha256={manifest['manifest_sha256']} "
              f"frozen={'none' if frozen is None else 'same' if frozen == manifest else 'DIFFERENT'}")
        if args.write:
            if frozen is not None:
                raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
            MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    if args.command == "provisions":
        rows = write_provisions(args.folder, args.out)
        counts = Counter(row["support"] for row in rows)
        print(f"{len(rows)} items, {sum(len(r['provisions']) for r in rows)} provisions; {dict(counts)} -> {args.out}")
        return 0
    manifest = build_corpus(args.out)
    (args.out / "folder_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
    print(f"{manifest['documents']} files ({manifest['added_v2']} added for MC-114), {manifest['chars']:,} characters, "
          f"truncated {manifest['truncated']}; corpus_v1 files unchanged {manifest['corpus_v1_files_unchanged']}; "
          f"ViBidLQA questions verbatim {len(manifest['bidlqa_questions_verbatim_in_corpus'])}; "
          f"folder sha256 {manifest['folder_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
