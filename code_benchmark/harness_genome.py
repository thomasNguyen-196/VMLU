#!/usr/bin/env python3
"""Harness genome — the declarative form of a benchmark condition (thesis P0).

`docs/harness-evolution-thesis-plan.md` §4 defines a closed set of harness genes
around a frozen model. Until now those genes only existed as long CLI invocations
(`--tools none --system-prompt minimal ...`), which cannot be hashed, recombined,
or checked against the frozen surface — so RQ2 (evolution) had nothing to mutate
and RQ4's "a mutation touching the scorer disqualifies the lineage" had nothing to
disqualify. This module makes a condition a **value**.

Two things it deliberately does NOT do:

- **It does not execute anything.** A genome is validated and stored; mapping a
  gene onto a runner flag is P1's job (`tasks.md` §4.2). Keeping this module free
  of runners is what stops the genome from becoming a second way to spell a
  measurement and drifting from the CLI.
- **It does not loosen a frozen contract.** It *reports* the frozen surface
  (`frozen_fingerprints`) so a lineage that edited the parser is detectable, and
  it caps the token budget per prompt template so the cheapest reward-hack route
  — let an MC model write a rationale whose last letter the byte-frozen parser
  then reads — fails fast at validation time.

stdlib-only (no endpoint, no dotenv), so the guard is testable offline and CI can
enforce it by running the suite.

    from code_benchmark.harness_genome import validate, baseline_genome
    g = validate({"elicitation": "zero_shot_minimal", ...})
    print(g.genome_id, g.required_declarations())
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import shutil
import subprocess  # nosec B404 — only use is `git diff` on a caller-supplied ref (see _git_diff)
from dataclasses import dataclass
from pathlib import Path

# ── Closed enums, each citing the plan line it encodes ──────────────────────
ELICITATIONS = ("zero_shot_minimal", "zero_shot_detailed", "cot", "fewshot_k")  # §4
FEWSHOT_SELECTIONS = ("random", "same_domain", "hardest_wrong")               # §4
OPTION_ORDERS = ("as_is", "seed_shuffle")                                     # §4
RAG_MODES = ("off", "bm25", "dense", "hybrid")                               # §4
RAG_CORPORA = ("viwiki", "vbpl", "mixed")                                     # §4
RAG_MERGES = ("none", "concat", "auto")                                      # §4
TOOL_MENU = ("none", "calculator", "date_arith", "enum_verbatim_lookup")     # §4 + §7
GENE_GROUPS = ("elicitation", "fewshot", "option_order", "answer_format",
               "rag", "tools", "resources", "agentic_extra")                  # §4, all eight

# The outer bound on any gene's token budget: the plan's own §4 default
# (`resources.max_tokens: 512`). Per-template ceilings below are tighter where a
# byte-frozen contract makes the budget part of the measurement.
MAX_TOKENS_HARD_CAP = 512

# The closed registry of prompt builders (§3.1: the scorer's prompt is frozen).
# `max_tokens_ceiling` is cited to the runner that owns the budget — NOT invented:
#   4   run_mc_eval.add_endpoint_args(max_tokens_default=4)      → MC letter budget
#   48  run_reading_eval.add_endpoint_args(max_tokens_default=48)
#   64  run_vbench_eval.py:864 (the guided-ask budget)
#   512 run_vbench_eval.py:701 (agentic default)
# `None` means the budget is a resource gene for that track, not a frozen number.
TEMPLATE_IDS: dict[str, dict] = {
    "mc_frozen":        {"builder": "code_benchmark.run_mc_eval:build_prompt",
                        "max_tokens_ceiling": 4},
    "legal_frozen":     {"builder": "code_benchmark.run_harness_eval:_legal_manifest",
                        "max_tokens_ceiling": 4},
    "reading_frozen":   {"builder": "code_benchmark.run_reading_eval:build_reading_prompt",
                        "max_tokens_ceiling": 48},
    "vbench_mc":        {"builder": "code_benchmark.run_vbench_eval:prepare_prompt[minimal]",
                        "max_tokens_ceiling": 64},
    "vbench_agentic":   {"builder": "code_benchmark.run_vbench_eval:prepare_prompt[detailed]",
                        "max_tokens_ceiling": None},
}

# Second net behind TEMPLATE_IDS (design D3): these keys may never appear, because
# each one names something outside the genome — the scorer, the gold, the split.
DENY_KEYS = frozenset({
    "scorer", "gold", "gold_answer", "answer_key", "key", "splits", "split",
    "dataset", "items", "subset", "parse", "parser", "extract_answer",
    "build_prompt", "validate_call", "postprocess", "repair_text",
})
# A config value is a config value: no paths, no newlines, no code fragments.
_VALUE_SHAPE = re.compile(r"[/\\\n\r]|\b(def|import|lambda|exec|eval|__)\b")

# The byte-frozen surface whose sha256 goes into every evidence bundle (§3.1/§3.2).
FROZEN_FUNCTIONS = (
    ("code_benchmark.run_mc_eval", "build_prompt"),
    ("code_benchmark.run_mc_eval", "extract_answer"),
    ("code_benchmark.run_vbench_eval", "_validate_call"),
)


def _fail(message: str) -> None:
    raise SystemExit(f"Error: {message}")


@dataclass(frozen=True)
class Genome:
    """One harness condition as a value. Frozen: a genome is not edited in place,
    it is replaced — so a candidate's identity always matches its contents."""

    elicitation: str
    fewshot_k: int
    fewshot_selection: str
    option_order: str
    shuffle_seed: int | None
    template_id: str
    retries: int
    repair_syntax_only: bool
    rag_mode: str
    rag_corpus: str
    rag_top_k: int
    rag_merge: str
    tools: tuple[str, ...]
    max_tokens: int
    temperature: float
    samples_per_item: int
    guided_fallback: bool

    # ── serialization ────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """The plan's §4 nested JSON — the on-disk contract for evidence bundles."""
        return {
            "elicitation": self.elicitation,
            "fewshot": {"k": self.fewshot_k, "selection": self.fewshot_selection},
            "option_order": self.option_order,
            "answer_format": {"template_id": self.template_id, "retries": self.retries,
                              "repair_syntax_only": self.repair_syntax_only},
            "rag": {"mode": self.rag_mode, "corpus": self.rag_corpus,
                    "top_k": self.rag_top_k, "merge": self.rag_merge},
            "tools": list(self.tools),
            "resources": {"max_tokens": self.max_tokens, "temperature": self.temperature,
                          "samples_per_item": self.samples_per_item},
            "agentic_extra": {"guided_fallback": self.guided_fallback},
            # `shuffle_seed` lives beside option_order: an unreproducible shuffle is
            # uninterpretable (MC-36 measured option order as a variance source).
            **({"shuffle_seed": self.shuffle_seed} if self.shuffle_seed is not None else {}),
        }

    def canonical_json(self) -> str:
        """Stable bytes: sorted keys, no whitespace. The genome_id's only input."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)

    @property
    def genome_id(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:16]

    # ── the honesty surface ──────────────────────────────────────────────────
    def required_declarations(self) -> list[str]:
        """Pre-registration text this condition MUST carry in its card.

        These are not warnings. Each one is a case where the genome is valid but
        the run measures something *other than* a plain single answer — pooling it
        with the plain arms would be a category error, not a rounding difference.
        """
        out = []
        if self.guided_fallback:
            out.append("guided_fallback=true: đây là **điều kiện elicitation thứ ba**; "
                       "không được gộp chung với arm hỏi trực tiếp và arm guided")
        if self.temperature != 0:
            out.append(f"temperature={self.temperature}: run **không tất định**, cần một "
                       f"repeatability floor riêng (MC-44 đo được biên ±1–2 câu ở temp 0)")
        if self.samples_per_item > 1:
            out.append(f"samples_per_item={self.samples_per_item}: báo cáo là **kết quả bầu**, "
                       f"không phải một câu trả lời — không so trực tiếp với arm 1 mẫu")
        if self.option_order == "seed_shuffle":
            out.append(f"option_order=seed_shuffle (seed={self.shuffle_seed}): thứ tự lựa chọn "
                       f"là một nguồn biến động (MC-36), seed phải được ghi lại")
        if self.retries > 0:
            out.append(f"answer_format.retries={self.retries}: hỏi lại là một lần elicitation "
                       f"thêm; các lần hỏi phải được giữ trong ledger, không gộp")
        if len(self.tools) > 1:
            out.append(f"tools={list(self.tools)}: menu nhiều tool — bảng phân rã phải tách từng "
                       f"tách biệt của tool, không gộp thành một điều kiện")
        return out


# ── validation ──────────────────────────────────────────────────────────────
def validate(spec: dict) -> Genome:
    """Fail-fast validation. Never coerces, never defaults, never drops a field:
    a silent default is how a mutation becomes an unnoticed condition change."""
    if not isinstance(spec, dict):
        _fail(f"genome must be a dict, got {type(spec).__name__}")
    unknown = set(spec) - set(GENE_GROUPS) - {"shuffle_seed"}
    if unknown:
        _fail(f"unknown gene group(s) {sorted(unknown)} — a genome declares exactly "
              f"{list(GENE_GROUPS)}; an extra group is an escape hatch, not a default")

    # ── deny-list + value-shape, walked over the whole structure ─────────────
    for group, value in spec.items():
        if group in DENY_KEYS:
            _fail(f"gene group {group!r} names something outside the genome "
                  f"(scorer / gold / split) — those are frozen by §3.1")
        for text in _strings_in(value):
            if _VALUE_SHAPE.search(text):
                _fail(f"gene group {group!r} carries a value that looks like a path or a "
                      f"code fragment: {text!r} — a config value is a config value")

    elicitation = _enum(spec, "elicitation", ELICITATIONS)
    option_order = _enum(spec, "option_order", OPTION_ORDERS)

    fewshot = _sub(spec, "fewshot", {"k", "selection"})
    k = fewshot["k"]
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        _fail(f"fewshot.k must be a non-negative int, got {k!r}")
    selection = _enum(fewshot, "selection", FEWSHOT_SELECTIONS, where="fewshot")
    if elicitation == "fewshot_k" and k == 0:
        _fail("elicitation=fewshot_k requires fewshot.k > 0")
    if elicitation != "fewshot_k" and k != 0:
        _fail(f"elicitation={elicitation} contradicts fewshot.k={k} "
              f"(few-shot examples need elicitation=fewshot_k)")

    fmt = _sub(spec, "answer_format", {"template_id", "retries", "repair_syntax_only"})
    template_id = fmt["template_id"]
    if template_id not in TEMPLATE_IDS:
        _fail(f"template_id={template_id!r} is not in the closed registry {sorted(TEMPLATE_IDS)} "
              f"— a prompt builder outside §3.1's frozen set is a scorer change in disguise")
    if fmt["repair_syntax_only"] is not True:
        _fail("answer_format.repair_syntax_only must be True: the harness may re-ask but "
              "must never edit an answer (§3.2)")
    retries = fmt["retries"]
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        _fail(f"answer_format.retries must be a non-negative int, got {retries!r}")

    rag = _sub(spec, "rag", {"mode", "corpus", "top_k", "merge"})
    rag_mode = _enum(rag, "mode", RAG_MODES, where="rag")
    rag_corpus = _enum(rag, "corpus", RAG_CORPORA, where="rag")
    rag_merge = _enum(rag, "merge", RAG_MERGES, where="rag")
    top_k = rag["top_k"]
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 0:
        _fail(f"rag.top_k must be a non-negative int, got {top_k!r}")
    if rag_mode == "off" and (rag_corpus != "viwiki" or top_k != 0 or rag_merge != "none"):
        _fail(f"rag.mode=off contradicts the rest of the rag group "
              f"(corpus={rag_corpus!r}, top_k={top_k}, merge={rag_merge!r}) — "
              f"a disabled retrieval group must be inert, not half-set")

    tools = spec.get("tools")
    if (not isinstance(tools, list) or not tools
            or not all(isinstance(t, str) for t in tools)):
        _fail(f"tools must be a non-empty list of strings, got {tools!r}")
    illegal = sorted(set(tools) - set(TOOL_MENU))
    if illegal:
        _fail(f"tools {illegal} are not in the pre-written reviewed menu {list(TOOL_MENU)} — "
              f"synthesis of tools is P4 and needs the sandbox (§7)")
    if len(set(tools)) != len(tools):
        _fail(f"tools has duplicates: {tools}")
    if "none" in tools and len(tools) > 1:
        _fail(f"tools={tools} is contradictory: 'none' means no tools, so it must be alone "
              f"— otherwise the run's tool condition depends on resolution order")

    resources = _sub(spec, "resources", {"max_tokens", "temperature", "samples_per_item"})
    max_tokens = resources["max_tokens"]
    temperature = resources["temperature"]
    samples = resources["samples_per_item"]
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        _fail(f"resources.max_tokens must be a positive int, got {max_tokens!r}")
    if max_tokens > MAX_TOKENS_HARD_CAP:
        _fail(f"resources.max_tokens={max_tokens} exceeds the hard cap {MAX_TOKENS_HARD_CAP} "
              f"(the plan's own §4 default)")
    ceiling = TEMPLATE_IDS[template_id]["max_tokens_ceiling"]
    if ceiling is not None and max_tokens > ceiling:
        _fail(f"max_tokens={max_tokens} exceeds the frozen ceiling {ceiling} for template "
              f"{template_id!r} ({TEMPLATE_IDS[template_id]['builder']}) — a larger budget "
              f"lets the model write a rationale whose last letter the byte-frozen parser "
              f"could then read: score up, capability flat")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) \
            or not (0.0 <= float(temperature) <= 2.0):
        _fail(f"resources.temperature must be a number in [0, 2], got {temperature!r}")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 1:
        _fail(f"resources.samples_per_item must be a positive int, got {samples!r}")

    agentic = _sub(spec, "agentic_extra", {"guided_fallback"})
    if not isinstance(agentic["guided_fallback"], bool):
        _fail(f"agentic_extra.guided_fallback must be a bool, got {agentic['guided_fallback']!r}")

    shuffle_seed = spec.get("shuffle_seed")
    if option_order == "seed_shuffle":
        if not isinstance(shuffle_seed, int) or isinstance(shuffle_seed, bool):
            _fail("option_order=seed_shuffle requires an explicit integer shuffle_seed — "
                  "MC-36 measured option order as a variance source, so an unreproducible "
                  "shuffle is uninterpretable")
    elif shuffle_seed is not None:
        _fail(f"option_order={option_order} contradicts shuffle_seed={shuffle_seed!r} "
              f"(the seed belongs to seed_shuffle only)")

    return Genome(
        elicitation=elicitation, fewshot_k=k, fewshot_selection=selection,
        option_order=option_order, shuffle_seed=shuffle_seed,
        template_id=template_id, retries=retries, repair_syntax_only=True,
        rag_mode=rag_mode, rag_corpus=rag_corpus, rag_top_k=top_k, rag_merge=rag_merge,
        tools=tuple(tools), max_tokens=max_tokens, temperature=float(temperature),
        samples_per_item=samples, guided_fallback=agentic["guided_fallback"],
    )


def _strings_in(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings_in(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings_in(v)]
    return []


def _enum(group: dict, key: str, allowed: tuple, *, where: str = "") -> str:
    value = group.get(key)
    if value not in allowed:
        label = f"{where}.{key}" if where else key
        _fail(f"{label}={value!r} is outside the closed set {list(allowed)} — the genome "
              f"grammar is closed by design (thesis §4); never coerced")
    return value


def _sub(group: dict, key: str, keys: set) -> dict:
    value = group.get(key)
    if not isinstance(value, dict):
        _fail(f"gene group {key!r} must be an object with keys {sorted(keys)}, got {value!r}")
    if set(value) != keys:
        _fail(f"gene group {key!r} must declare exactly {sorted(keys)}, got {sorted(value)}")
    return value


# ── seeds (§6 step 1: "hand-encode current repo state as baseline") ───────────
def minimal_genome(*, template_id: str = "mc_frozen", max_tokens: int = 4) -> Genome:
    """The `zero_shot_minimal` seed: the byte-frozen prompt, no scaffold, no tools,
    no retrieval, one deterministic sample. This is the plan's minimal arm — the
    `minimal/detailed` pair §6 seeds with, which today only exists inside the
    V-Bench runner on the 28K node, not for the model under test."""
    return validate({
        "elicitation": "zero_shot_minimal",
        "fewshot": {"k": 0, "selection": "random"},
        "option_order": "as_is",
        "answer_format": {"template_id": template_id, "retries": 0,
                          "repair_syntax_only": True},
        "rag": {"mode": "off", "corpus": "viwiki", "top_k": 0, "merge": "none"},
        "tools": ["none"],
        "resources": {"max_tokens": max_tokens, "temperature": 0.0,
                      "samples_per_item": 1},
        "agentic_extra": {"guided_fallback": False},
    })


def baseline_genome(*, template_id: str = "mc_frozen", max_tokens: int = 4,
                    tools: tuple[str, ...] = ("calculator", "enum_verbatim_lookup")) -> Genome:
    """The repo's current measured state as one genome: frozen prompt + the two
    tool genes the plan motivates from measured error clusters (Vi-DROP arithmetic,
    near-miss enums) + a small retrieval group. §6 calls this the baseline the
    mutants must beat."""
    return validate({
        "elicitation": "zero_shot_detailed",
        "fewshot": {"k": 0, "selection": "same_domain"},
        "option_order": "as_is",
        "answer_format": {"template_id": template_id, "retries": 0,
                          "repair_syntax_only": True},
        "rag": {"mode": "bm25", "corpus": "mixed", "top_k": 3, "merge": "concat"},
        "tools": list(tools),
        "resources": {"max_tokens": max_tokens, "temperature": 0.0,
                      "samples_per_item": 1},
        "agentic_extra": {"guided_fallback": False},
    })


def baseline_genome_vs_direct(genome: Genome) -> Genome:
    """One targeted mutation of the baseline: drop the scaffold's tools and go back
    to the frozen minimal prompt. Used as the ablation seed that separates
    'harness gene' from 'prompt gene' — the decomposition RQ1 is built on."""
    return validate({**genome.to_dict(), "elicitation": "zero_shot_minimal",
                     "tools": ["none"]})


# ── the frozen surface, made checkable (§3.1 / §3.4) ────────────────────────
def frozen_fingerprints() -> dict[str, str]:
    """sha256 of the source of each byte-frozen function, so a lineage that edited
    the parser is detectable from its own evidence bundle instead of merely
    forbidden. Hashed over function source, not file source, so unrelated edits in
    the same module do not churn the fingerprint — the diff is the signal."""
    out: dict[str, str] = {}
    for module_name, func_name in FROZEN_FUNCTIONS:
        try:
            module = __import__(module_name, fromlist=[func_name])
            source = inspect.getsource(getattr(module, func_name))
        except Exception as e:                       # pragma: no cover - env problem
            _fail(f"cannot fingerprint frozen function {module_name}.{func_name}: {e}")
        out[f"{module_name}:{func_name}"] = hashlib.sha256(
            source.encode("utf-8")).hexdigest()[:16]
    return out


# ── evidence bundles (§3.4: "every candidate ships an evidence folder") ──────
EVIDENCE_ROOT = Path("all_res/evidence")


def _git_diff(git_ref: str) -> str:
    """`git diff <ref> -- code_benchmark`, with git resolved to an absolute path.

    The ref is a caller-supplied string used as one argv element (no shell), which
    is why this is safe enough for the CI security gate; `shutil.which` is still
    resolved first so the child process cannot pick up a `git` from PATH that
    someone else wrote."""
    git = shutil.which("git")
    if git is None:
        _fail("git not found on PATH — an evidence bundle cannot state whether the "
              "harness code changed, which is part of what the bundle is for")
    # No shell, git resolved above, and the only caller-controlled value is one argv
    # element — `git diff` reads a ref, it does not execute it.
    proc = subprocess.run([git, "diff", git_ref, "--", "code_benchmark"],
                          capture_output=True, text=True, check=False)  # nosec B603
    return proc.stdout


def collect_evidence(genome: Genome, *, slug: str, dataset: str, results: Path,
                     ledger: Path, budget: dict, root: Path = EVIDENCE_ROOT,
                     git_ref: str | None = None) -> Path:
    """Write one candidate's evidence folder. **References** the arm's CSVs by path
    instead of copying them: results stay in `all_res/ollama_result/<slug>/`
    (gitignored, per-model), because a copied second copy is a second source of
    truth — the exact failure the repo already hit with the review blob vs the
    static fallback."""
    for label, path in (("results", results), ("ledger", ledger)):
        if not Path(path).exists():
            _fail(f"evidence bundle for {slug} names a {label} file that does not exist: "
                  f"{path} — a bundle that points at nothing is worse than no bundle")
    out = Path(root) / genome.genome_id
    out.mkdir(parents=True, exist_ok=True)

    (out / "genome.json").write_text(
        json.dumps(genome.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (out / "frozen_fingerprints.json").write_text(
        json.dumps(frozen_fingerprints(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "budget.json").write_text(
        json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # A config-only mutation must produce an honest empty diff, not a fake one.
    diff = _git_diff(git_ref) if git_ref else ""
    (out / "harness.diff").write_text(diff, encoding="utf-8")

    manifest = {
        "genome_id": genome.genome_id,
        "slug": slug,
        "dataset": dataset,
        "code_changed": bool(diff.strip()),
        "results_csv": str(results),
        "ledger_csv": str(ledger),
        "budget": budget,
        "frozen_fingerprints": frozen_fingerprints(),
        "required_declarations": genome.required_declarations(),
        "reproduce": (f"python code_benchmark/run_harness_eval.py run --dataset {dataset} "
                      f"--label {slug}   # then re-run this bundle's writer"),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (out / "README.md").write_text(
        f"# Evidence {genome.genome_id}\n\n"
        f"- slug: `{slug}`\n- dataset: `{dataset}`\n"
        f"- code changed by this candidate: **{bool(diff.strip())}**\n"
        f"- results: `{results}`\n- ledger: `{ledger}`\n\n"
        + "".join(f"- REQUIRED DECLARATION: {d}\n"
                  for d in genome.required_declarations())
        + ("\nNo declaration required: a plain single deterministic answer.\n"
           if not genome.required_declarations() else ""),
        encoding="utf-8")
    return out


def prune_evidence(keep: int = 50, root: Path = EVIDENCE_ROOT) -> list[str]:
    """Keep the `keep` newest evidence folders; report what was removed. Bundles are
    cheap but not free, and an unbounded archive is how a repo loses track of which
    candidate produced a published number."""
    if not Path(root).exists():
        return []
    folders = sorted((p for p in Path(root).iterdir() if p.is_dir()),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for stale in folders[keep:]:
        shutil.rmtree(stale)
        removed.append(stale.name)
    return removed