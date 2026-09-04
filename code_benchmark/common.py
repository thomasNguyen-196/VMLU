"""Shared kernel for the code_benchmark package — STDLIB ONLY.

make_eval_sample.py must keep running on the bare system python3 (no venv
deps), so nothing in this module may import openai/pandas/tqdm/dotenv. The
endpoint helpers (build_client, retry, probe) live in llm.py; checkpoint
naming/lookup in checkpoint.py.

Extracted from the two runners' near-duplicates (env/flag resolution, logging
bootstrap, model filename-slug, CSV column validation, the dataset:item_id
key — once four implementations under three names, mirrored again by
web/lib/types.ts itemKey).
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import re
from pathlib import Path

# ── Shared path defaults (were 3-5 hand-copied literals each) ──────────────
RESULTS_DIR = Path("all_res/ollama_result")
MANIFEST_DEFAULT = Path("eval_set_manifest.csv")
SQUAD_DEFAULT = Path("vmlu_squad_v1/vi_squad_benchmark_question_only.json")
DROP_DEFAULT = Path("vmlu_drop_v1/vi_drop_benchmark_3309_question_only.json")
ANNOTATOR_A_DEFAULT = Path("annotation_workbooks/annotator_A.csv")

# The eval manifest's frozen column order (writer + gold-apply must agree).
MANIFEST_COLS = ["dataset", "item_id", "stratum", "passage_id", "question", "gold_answer"]

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize_model(model: str) -> str:
    """Filename-safe model tag, shared by log files and checkpoints.
    Deliberately NOT the reviewer/model slug of web/lib/slug.ts (lowercase +
    diacritic-stripping) — merging them would break the tracked
    review_records/ filename contract. Two rules, two names."""
    return _SLUG_RE.sub("_", model)


def item_key(row: dict) -> str:
    """Stable identity of one eval item across the whole reading/review
    pipeline: 'dataset:item_id' (mirror of web/lib/types.ts itemKey)."""
    return f"{row['dataset']}:{row['item_id']}"


def split_item_key(key: str) -> tuple[str, str]:
    """Inverse of item_key. Split on the FIRST colon only — item_ids never
    contain colons, dataset names are fixed."""
    ds, _, iid = key.partition(":")
    return ds, iid


def resolve_endpoint(args: argparse.Namespace) -> tuple[str, str, str]:
    """CLI flag > env var resolution of the OpenAI-compatible endpoint triple.
    Returns (base_url, api_key, model); exits 1 with the flag/env hint when a
    required value is missing. (load_dotenv() stays in the callers — this
    module must not import dotenv.)"""
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or "ollama"
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    model = args.model or os.environ.get("OPENAI_MODEL")
    if not base_url:
        raise SystemExit("Error: OPENAI_BASE_URL is not set. "
                         "Please provide --base-url or set OPENAI_BASE_URL in .env")
    if not model:
        raise SystemExit("Error: OPENAI_MODEL is not set. "
                         "Please provide --model or set OPENAI_MODEL in .env")
    return base_url, api_key, model


def add_endpoint_args(parser: argparse.ArgumentParser, *,
                      max_tokens_default: int, max_tokens_help: str,
                      resume_help: str) -> None:
    """The shared inference flag group of both runners (defaults frozen:
    temperature 0.0, seed 42, workers 4; only max-tokens/resume help differ).
    Call parse_endpoint_args() after parse to enforce the --limit guard."""
    parser.add_argument("--model", type=str, default=None,
                        help="Model name (overrides OPENAI_MODEL env var)")
    parser.add_argument("--base-url", type=str, default=None,
                        help="Base URL for OpenAI-compatible endpoint (overrides OPENAI_BASE_URL)")
    parser.add_argument("--api-key", type=str, default=None,
                        help="API key (overrides OPENAI_API_KEY)")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="Sampling temperature (default: 0.0)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed for reproducibility (default: 42)")
    parser.add_argument("--max-tokens", type=int, default=max_tokens_default,
                        help=max_tokens_help)
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of concurrent workers (default: 4)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of questions to evaluate (must be > 0)")
    parser.add_argument("--resume", action="store_true", help=resume_help)


def parse_endpoint_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be an integer greater than 0.")
    return args


def setup_logging(log_path: str | Path) -> None:
    """Console + file INFO logging for a runner (the shared bootstrap the two
    main()s each hand-rolled). Configures the ROOT logger — both runners call
    this exactly once at startup and never run in the same process."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(log_path), level=logging.INFO,
                        format="%(asctime)s - %(levelname)s: %(message)s")
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger("").addHandler(console)


def read_csv_checked(path: Path, *, required: set[str] | None = None,
                     exact: list[str] | None = None, label: str = "",
                     encoding: str = "utf-8") -> list[dict]:
    """csv.DictReader with the repo's fail-fast column contract: non-empty
    rows, and header covering `required` (⊆) or equal to `exact`. Column-set
    drift is always a wrong-file pairing, never something to paper over.
    Raises SystemExit (the runners' CLI error style)."""
    name = f"{label} " if label else ""
    with open(path, encoding=encoding, newline="") as f:
        rdr = csv.DictReader(f)
        header = rdr.fieldnames or []
        rows = list(rdr)
    if not rows:
        raise SystemExit(f"Error: empty {name}{path}")
    if exact is not None:
        if header != exact:
            raise SystemExit(f"Error: {name}{path} header mismatch — expected exactly "
                             f"{exact}, got {header}")
    elif required is not None:
        missing = required - set(header)
        if missing:
            raise SystemExit(f"Error: {name}{path} lacks columns: {sorted(missing)}")
    return rows


def write_csv_atomic(path: str | Path, rows: list[dict], fieldnames: list[str]) -> None:
    """tmp + rename so a crash mid-write never truncates an existing file —
    the pattern build_review_ui pioneered for the blob, now also for the
    TRACKED eval_set_manifest.csv that apply_gold rewrites in place."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
