"""Continue V-Bench via four fixed CMC workers, preserving MC-76/77 answers.

From root: python -m code_benchmark.run_muse13_cmc_vbench_four_workers --execute
"""
from __future__ import annotations

try:
    from code_benchmark import run_muse13_cmc_vbench as continuation
except ImportError:
    import run_muse13_cmc_vbench as continuation


def configure() -> None:
    c = continuation
    c.PROFILE_ID = 'muse-spark-1-3-contributor-cmc-4w'
    c.CARD_ID = 'MC-78'
    c.CARD_PATH = c.ROOT / 'docs/measurement_cards/MC-78-muse13-cmc-vbench-four-workers.md'
    c.OUTPUT_ROOT = c.ROOT / 'all_res/muse13_cmc_vbench_mc78'
    c.WORKERS = 4
    previous = c.ROOT / 'all_res/muse13_cmc_vbench_mc77'
    c.ADDITIONAL_SOURCES = [(previous, previous / 'vbench/muse-spark-1-3-contributor-cmc', 'MC-77', 'cmc/meta/muse-spark-1.3-contributor')]


if __name__ == '__main__':
    configure()
    continuation.main()
