"""Run the matched Qwen IEC condition registered as MC-70.

The frozen V2 manifest/profile registry remains unchanged. This phase-scoped
override matches the OpenCode Go profiles' effective temperature and thinking
mode while preserving the same VMLU prompts, no-tools setup, and item manifest.
Run from the repository root; the campaign wrapper may add --resume.
"""
from __future__ import annotations

import copy

try:
    from code_benchmark import run_vi_multimodel_expansion as runner
except ImportError:
    import run_vi_multimodel_expansion as runner

PROFILE_ID = "qwen3-5-9b-65k"
_load_profiles = runner.load_profiles


def _load_matched_profiles() -> dict[str, dict]:
    profiles = _load_profiles()
    profile = copy.deepcopy(profiles[PROFILE_ID])
    profile["omp_options"] = {"temperature": 1.0}
    profile["omp_reasoning"] = True
    profile["omp_thinking"] = "auto"
    profile["temperature_effective"] = 1.0
    profile["temperature_policy"] = "explicit 1.0; matched to V2 Go provider effective temperature"
    profile["send_seed"] = False
    profile["seed_policy"] = "omitted to match OpenCode Go provider profiles"
    profile["measurement_card_ids_v2"] = {
        **profile["measurement_card_ids_v2"],
        "vmlu": "MC-70",
    }
    profiles[PROFILE_ID] = profile
    return profiles


def main() -> None:
    runner.load_profiles = _load_matched_profiles
    print(
        "condition=MC-70 temperature=1.0 reasoning=true thinking=auto "
        "seed=omitted tools=none",
        flush=True,
    )
    runner.main()


if __name__ == "__main__":
    main()
