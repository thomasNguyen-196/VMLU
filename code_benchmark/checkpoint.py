"""Per-model checkpoint naming + newest-checkpoint lookup for both runners.

Both pipelines write <prefix><count>_<sanitized_model>.csv checkpoints; the MC
runner (prefix "raw_result_") and the reading runner (prefix "reading_result_")
previously carried two copies of the same "find the highest count for THIS
model" loop — and the reading copy had a latent bug (its count regex hardcoded
"reading_result_" while its glob used the prefix constant, so renaming the
constant silently broke --resume). One function, prefix threaded through.

Policy kept verbatim from both originals: legacy files that carry no model
identity (<prefix><count>.csv) are NEVER picked — guessing could graft a
different model's answers onto this run.
"""
from __future__ import annotations

import re
from pathlib import Path

from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import sanitize_model
except ImportError:
    from common import sanitize_model

load_dotenv()

MC_PREFIX = "raw_result_"        # the MC runner's checkpoint family
READING_PREFIX = "reading_result_"  # the reading runner's (never collides with MC)
VBENCH_PREFIX = "vbench_result_"  # the V-Bench public-test runner's (run_vbench_eval.py)

_COUNT_RE_CACHE: dict[str, re.Pattern] = {}


def checkpoint_name(model: str, count: int, prefix: str = MC_PREFIX) -> str:
    """Per-model checkpoint: <prefix><count>_<slug>.csv. The count alone was a
    shared namespace, so a --resume run with a different model silently reused
    the previous model's answers (these folders mix several models)."""
    return f"{prefix}{count}_{sanitize_model(model)}.csv"


def find_latest_checkpoint(checkpoint_dir: Path, model: str,
                           prefix: str = MC_PREFIX) -> Path | None:
    """Newest model-tagged checkpoint for THIS model (highest embedded count)."""
    slug = sanitize_model(model)
    files = list(checkpoint_dir.glob(f"{prefix}*_{slug}.csv"))
    if not files:
        return None
    count_re = _COUNT_RE_CACHE.setdefault(prefix, re.compile(rf"{re.escape(prefix)}(\d+)_"))

    def get_count(p: Path) -> int:
        m = count_re.search(p.name)
        return int(m.group(1)) if m else 0

    return max(files, key=get_count)
