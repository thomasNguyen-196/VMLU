#!/usr/bin/env python3
"""Gene → CLI: turn a validated genome into a runnable command (thesis P1 step 1).

`harness_genome.py` makes a condition a **value**. It deliberately does not execute
anything, so the mapping from gene to runner flag lived nowhere — which meant P1's
grid would be 30–50 hand-typed commands, i.e. P0 would have enabled nothing.

This module closes that gap, and its most useful output is not the commands: it is
the **support matrix**, which states per gene whether it can run today, needs an
outside mechanism, or has never been implemented. Several genes in the thesis plan's
§4 grammar have no runner behind them at all. A genome can be perfectly *valid* and
still not be *runnable*, and that gap is exactly where a thesis would otherwise claim
an experiment it never ran.

    .venv/bin/python code_benchmark/genome_to_cli.py --support
    .venv/bin/python code_benchmark/genome_to_cli.py --genome minimal --runner harness \
        --dataset legal_mc --label probe

`plan()` fails fast on any gene the chosen runner cannot express. Silently dropping a
gene would turn a request for few-shot into a zero-shot run under a few-shot label —
the exact class of bug this repo's cards exist to prevent.
"""

from __future__ import annotations

import argparse

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.harness_genome import Genome, minimal_genome, baseline_genome
except ImportError:  # direct run from code_benchmark/
    from harness_genome import Genome, minimal_genome, baseline_genome

# Status vocabulary, strongest claim first.
IMPLEMENTED = "implemented"   # a flag exists and produces the condition
ROUTED = "routed"             # selects which runner/template is used
EXTERNAL = "external"         # needs a mechanism outside the runner (e.g. a pinning proxy)
PIPELINE = "separate-pipeline"  # real, but a different script and its own condition record
UNSUPPORTED = "unsupported"   # nothing in this repo can express it today

# omp's own default menu, captured from MC-31's proxy log (system=690, tools=11).
# The genome grammar's named tools are NOT in it — a named tool gene is currently
# unsupported, and saying so is the whole point of this table.
OMP_DEFAULT_MENU = ("read", "bash", "edit", "eval", "glob", "grep",
                    "task", "hub", "todo", "web_search", "write")

RUNNERS = ("harness", "mc", "reading", "vbench")

# template_id -> (runner, what the runner needs for that template)
TEMPLATE_ROUTES = {
    "mc_frozen": ("mc", "frozen build_prompt, max_tokens 4"),
    "legal_frozen": ("harness", "legal adapters, arm-A prompt parity gate"),
    "reading_frozen": ("reading", "frozen open-book prompt, max_tokens 48"),
    "vbench_mc": ("vbench", "prepare_prompt[minimal], --track mc"),
    "vbench_agentic": ("vbench", "prepare_prompt[detailed], --track agentic"),
}

SUPPORT_COLS = ["gene", "value", "status", "mechanism", "since"]


def support_matrix(genome: Genome | None = None, runner: str | None = None) -> list[dict]:
    """What each gene of a genome can actually do today.

    `genome` narrows the table to the values that genome actually uses; pass None for
    the whole grammar. `runner` makes the status runner-specific where it genuinely
    is — `temperature` is an ordinary flag on the direct runners and an EXTERNAL
    mechanism (a pinning proxy) on the harness, which has no such flag. Derived from
    the runner flags, not from the plan's prose: a gene listed in §4 with no flag
    behind it is reported as unsupported, which is the finding, not a defect.
    """
    rows: list[dict] = []

    def add(gene, value, status, mechanism, since="—"):
        rows.append({"gene": gene, "value": value, "status": status,
                     "mechanism": mechanism, "since": since})

    elicitation = genome.elicitation if genome else None
    for value in ("zero_shot_minimal", "zero_shot_detailed", "cot", "fewshot_k"):
        if elicitation and value != elicitation:
            continue
        if value == "zero_shot_minimal":
            add("elicitation", value, IMPLEMENTED,
                "harness: --system-prompt minimal | direct runners: the frozen prompt is "
                "already minimal, so no flag", "always")
        elif value == "zero_shot_detailed":
            add("elicitation", value, ROUTED,
                "vbench only: --prompt-style detailed. MC/reading/harness have no "
                "detailed template — wiring one is new work", "MC-26 (vbench)")
        elif value == "cot":
            add("elicitation", value, UNSUPPORTED,
                "no runner has a CoT template; the token ceilings would also have to move")
        else:
            add("elicitation", value, UNSUPPORTED,
                "no few-shot assembly exists; --fewshot is not a flag on any runner")

    if not genome or genome.fewshot_k:
        add("fewshot", "k>0 / selection", UNSUPPORTED,
            "no runner takes a demonstration block")

    order = genome.option_order if genome else None
    for value in ("as_is", "seed_shuffle"):
        if order and value != order:
            continue
        if value == "as_is":
            add("option_order", value, IMPLEMENTED, "the default; nothing to pass", "always")
        else:
            add("option_order", value, PIPELINE,
                "make_shuffled_mc_input.py --seed N writes a shuffled input + manifest, "
                "then run_shuffled_mc.py — a separate script and a separate condition "
                "record, MC/legal only", "MC-35/36")

    add("answer_format", "template_id", ROUTED,
        "picks the runner and its frozen prompt builder; a template outside this table "
        "is rejected by the genome guard", "MC-31/32")
    retries = genome.retries if genome else 0
    add("answer_format", f"retries={retries}",
        IMPLEMENTED if retries == 0 else UNSUPPORTED,
        "no runner re-asks a single item in-line. vbench --retry-unparsed re-calls rows "
        "after the fact and is its own condition, not this gene"
        if retries == 0 else
        "no in-line re-ask exists; --retry-unparsed is a post-hoc pass over a finished run")
    add("answer_format", "repair_syntax_only", IMPLEMENTED,
        "forced True by the genome guard — the harness may re-ask, never edit an answer",
        "always")

    mode = genome.rag_mode if genome else None
    for value in ("off", "bm25", "dense", "hybrid"):
        if mode and value != mode:
            continue
        add("rag", f"mode={value}", IMPLEMENTED if value == "off" else UNSUPPORTED,
            "rag off = no flags" if value == "off" else
            "no retrieval in any runner; there is no corpus index to retrieve from")

    tools = set(genome.tools) if genome else set()
    for value in ("none", "all", "calculator", "date_arith", "enum_verbatim_lookup"):
        if tools and value not in tools:
            continue
        if value == "none":
            add("tools", "none", IMPLEMENTED, "--tools none", "MC-20 (H1)")
        elif value == "all":
            add("tools", "all", IMPLEMENTED,
                "--tools all = omp's own default menu, 11 tools (measured in MC-31/47)",
                "MC-31/32")
        else:
            add("tools", value, UNSUPPORTED,
                f"not in omp's menu (measured: {', '.join(OMP_DEFAULT_MENU)}); the "
                f"grammar names it, the agent does not offer it")

    if genome:
        add("resources", f"max_tokens={genome.max_tokens}", IMPLEMENTED,
            "--max-tokens on every runner; the per-template ceiling is guarded")
        on_harness = runner in (None, "harness")
        add("resources", f"temperature={genome.temperature}",
            EXTERNAL if on_harness else IMPLEMENTED,
            "harness: NO --temperature flag — temperature is pinned by a localhost proxy, "
            "so the proxy is part of the condition and a lost proxy silently turns the "
            "arm into a retry storm (MC-31/32, MC-47)"
            if on_harness else "direct runner: --temperature",
            )
        add("resources", f"samples_per_item={genome.samples_per_item}",
            IMPLEMENTED if genome.samples_per_item == 1 else UNSUPPORTED,
            "one sample per item, the default" if genome.samples_per_item == 1 else
            "no self-consistency anywhere: nothing samples k>1 or aggregates a vote")
    else:
        add("resources", "max_tokens", IMPLEMENTED, "--max-tokens")
        add("resources", "temperature",
            EXTERNAL if runner in (None, "harness") else IMPLEMENTED,
            # no "|" in a mechanism: this string lands in a markdown table cell
            "direct runners pass --temperature; the harness has no such flag and is "
            "pinned by a localhost proxy")
        add("resources", "samples_per_item>1", UNSUPPORTED,
            "no vote/majority aggregation exists")

    guided = genome.guided_fallback if genome else None
    if guided is not None:
        add("agentic_extra", f"guided_fallback={guided}",
            IMPLEMENTED if guided else IMPLEMENTED,
            "vbench only: --guided, a numbered interview that is a THIRD elicitation "
            "condition (never pooled with the other two)" if guided else
            "the default: one direct ask per item")

    return rows


def _fail(message: str) -> None:
    raise SystemExit(f"Error: {message}")


def _unsupported(genome: Genome, rows: list[dict], runner: str) -> list[str]:
    """Every gene this genome uses that the chosen runner cannot express AT ALL.

    Only UNSUPPORTED blocks. EXTERNAL does not: temperature pinned through a proxy is
    runnable once the proxy exists, so it is a precondition the caller must satisfy
    and disclose — not a gene with no mechanism. Blocking on it would make every
    harness arm unplannable, which is the opposite of the truth.
    """
    blockers = []
    for row in rows:
        if row["status"] != UNSUPPORTED:
            continue
        if row["gene"] == "resources" and row["value"].startswith("max_tokens"):
            continue                      # expressible on every runner
        if row["gene"] == "elicitation" and runner in ("vbench",):
            continue
        if row["gene"] == "elicitation" and row["value"] == "zero_shot_minimal":
            continue
        if row["gene"] == "agentic_extra" and runner != "vbench":
            continue
        blockers.append(f"{row['gene']}={row['value']} ({row['status']}: {row['mechanism']})")
    return blockers


def plan(genome: Genome, runner: str, *, dataset: str, label: str, workers: int = 4,
         extra: tuple[str, ...] = ()) -> list[str]:
    """The argv for this genome. Fail-fast: an unexpressible gene is an error here,
    never a silently-dropped flag under a label that promises it."""
    if runner not in RUNNERS:
        _fail(f"runner must be one of {list(RUNNERS)}, got {runner!r}")
    rows = support_matrix(genome)
    blockers = _unsupported(genome, rows, runner)
    if blockers:
        _fail("this genome asks for genes the runner cannot express:\n  - "
              + "\n  - ".join(blockers)
              + f"\n  runner={runner}. Either implement the gene or drop it from the "
                f"genome — a run must not be labelled with a condition it did not apply.")

    argv: list[str] = []
    if runner == "harness":
        argv += ["run", "--dataset", dataset, "--label", label,
                 "--workers", str(workers)]
        if genome.elicitation == "zero_shot_minimal":
            argv += ["--system-prompt", "minimal"]
        if genome.tools == ("none",):
            argv += ["--tools", "none"]
        elif genome.tools == ("all",):
            argv += ["--tools", "all"]
    elif runner == "mc":
        argv += ["--folder", dataset, "--max-tokens", str(genome.max_tokens),
                 "--temperature", str(genome.temperature), "--workers", str(workers)]
    elif runner == "reading":
        argv += ["--max-tokens", str(genome.max_tokens),
                 "--temperature", str(genome.temperature), "--workers", str(workers)]
    else:  # vbench
        argv += ["--max-tokens", str(genome.max_tokens),
                 "--temperature", str(genome.temperature), "--workers", str(workers)]
        track = "agentic" if genome.template_id == "vbench_agentic" else "mc"
        argv += ["--track", track]
        argv += ["--prompt-style",
                 "detailed" if genome.template_id == "vbench_agentic" else "minimal"]
        if genome.guided_fallback:
            argv += ["--guided"]
    if genome.option_order == "seed_shuffle":
        _fail("option_order=seed_shuffle is a separate pipeline (make_shuffled_mc_input.py "
              "+ run_shuffled_mc.py) and cannot be a flag on any runner; run it as its own "
              "pre-registered condition")
    argv += list(extra)
    return argv


def _render_support(rows: list[dict]) -> str:
    lines = ["| gene | value | status | cơ chế | có từ |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['gene']} | `{r['value']}` | **{r['status']}** | "
                     f"{r['mechanism']} | {r['since']} |")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return "\n".join(lines) + "\n\n" + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--genome", default="minimal",
                    choices=["minimal", "baseline"], help="a named seed genome")
    ap.add_argument("--runner", default="harness", choices=list(RUNNERS))
    ap.add_argument("--dataset", default="legal_mc")
    ap.add_argument("--label", default="probe")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--script", default=None,
                    help="runner script path (default: the one the runner implies)")
    ap.add_argument("--support", action="store_true",
                    help="print the support matrix for the chosen genome and exit")
    ap.add_argument("--all", action="store_true", help="print the whole grammar's matrix")
    args = ap.parse_args()

    genome = None if args.all else (minimal_genome() if args.genome == "minimal"
                                    else baseline_genome())
    rows = support_matrix(genome)
    if args.support or args.all:
        print(_render_support(rows))
        return

    script = args.script or {
        "harness": "code_benchmark/run_harness_eval.py",
        "mc": "code_benchmark/run_mc_eval.py",
        "reading": "code_benchmark/run_reading_eval.py",
        "vbench": "code_benchmark/run_vbench_eval.py",
    }[args.runner]
    argv = plan(genome, args.runner, dataset=args.dataset, label=args.label,
                workers=args.workers)
    print(f"genome {genome.genome_id} -> {args.runner}")
    print(f"  {script} " + " ".join(argv))
    externals = [r for r in support_matrix(genome, args.runner) if r["status"] == EXTERNAL]
    if externals:
        print("\nĐiều kiện tiên quyết NGOÀI runner (phải dựng trước khi chạy):")
        for r in externals:
            print(f"  - {r['gene']}={r['value']}: {r['mechanism']}")
    decls = genome.required_declarations()
    if decls:
        print("\nKhai báo bắt buộc trong card (từ genome):")
        for d in decls:
            print(f"  - {d}")


if __name__ == "__main__":
    main()