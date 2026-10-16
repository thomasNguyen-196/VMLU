"""Run only the MC-70 Qwen VMLU condition with resume supervision.

Run detached from the repository root. V-Bench remains deliberately excluded.
"""
from __future__ import annotations

import builtins
from pathlib import Path

try:
    from code_benchmark import run_vi_multimodel_go_campaign as campaign
except ImportError:
    import run_vi_multimodel_go_campaign as campaign

campaign.TASKS = (("vmlu", "qwen3-5-9b-65k"),)
campaign.PROFILES = ()
campaign.RUNNER = Path(__file__).resolve().with_name("run_qwen_vmlu_mc70.py")

_original_print = builtins.print


def _campaign_print(*args, **kwargs) -> None:
    if args and args[0] == "OpenCode Go VMLU/V-Bench campaign complete; Qwen was not started.":
        args = ("Qwen MC-70 VMLU-only campaign complete; V-Bench remains deferred.",) + args[1:]
    _original_print(*args, **kwargs)


def main() -> int:
    builtins.print = _campaign_print
    try:
        return campaign.main()
    finally:
        builtins.print = _original_print


if __name__ == "__main__":
    raise SystemExit(main())
