"""The router-critic's design check on reading items (openspec change diagnostic-router-loop; card MC-102).

* Critic: Muse Spark 1.3 on the direct OpenCode Go route reads the passage and question of a wide reading item and
  Qwen3.5-9B's first answer (the scored prediction of its MC-90 B-r1 attempt), judges the answer by meaning and
  prescribes a fix, on three closed last lines (`Đánh giá`, `Nguyên nhân`, `Cách sửa`). It never sees the gold or a
  score, and nothing it writes reaches the student.
* Items: the 376 Vi-DROP and Vi-SQuAD items of the menu set (data/diagnostic_llm_router/menu_q_v1.json), one critic
  call each (run key `dataset:item:critic-1`).
* Replay: the loop is scored with Qwen's logged draw-1 answers (B, S, Q of MC-90 to MC-92 and MC-97); no student
  request is sent (analysis: code_benchmark/analyze_router_critic.py).

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_router_critic            # build the manifest, compare with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_router_critic --write    # freeze data/diagnostic_router_loop/critic_manifest_v1.json
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
    from code_benchmark import diagnostic_menu as menu
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_menu as menu
    import diagnostic_prospective as dp
    import vi_multimodel as v1

DATA_DIR = dp.ROOT / "data" / "diagnostic_router_loop"
CONFIG_PATH = DATA_DIR / "critic_v1.json"
MANIFEST_PATH = DATA_DIR / "critic_manifest_v1.json"
REGISTRATION_PATH = DATA_DIR / "registration.json"
PROTOCOL_ID = "vmlu-diagnostic-router-critic"
PHASE = "critic"
REPLICATE = "critic-1"
JUDGED_REPLICATE = "B-r1"
JUDGED_SCORES = dp.ROOT / "all_res" / "diagnostic_prospective" / "wide" / "qwen3-5-9b-65k-prospective" / "scores.jsonl"
CONFIG_KEYS = ("critic_id", "protocol_id", "protocol_version", "change", "purpose", "items", "prompt", "route",
               "replay", "analysis")
PLACEHOLDERS = ("<<PASSAGE>>", "<<QUESTION>>", "<<ANSWER>>")
EMPTY_ANSWER = "(mô hình không đưa ra câu trả lời)"
_LABELS = {"verdict": re.compile(r"danh\s*gia\s*[:：]\s*[`*\s]*([a-z_]+)"),
           "cause": re.compile(r"nguyen\s*nhan\s*[:：]\s*[`*\s]*([a-z_]+)"),
           "fix": re.compile(r"cach\s*sua\s*[:：]\s*[`*\s]*([a-z_]+)")}


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _read_json_bytes(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read the {label} {path}: {exc}") from exc


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != set(CONFIG_KEYS):
        raise _fail(f"the critic configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if config["protocol_id"] != PROTOCOL_ID or config["protocol_version"] != 1:
        raise _fail("unsupported critic configuration id/version")
    items = config["items"]
    if items.get("calls_per_item") != 1 or set(items.get("dataset_counts", {})) != set(items.get("datasets", [])):
        raise _fail("the critic judges each listed dataset's items with one call per item")
    if not set(items["datasets"]) <= set(menu.DATASET_COUNTS):
        raise _fail(f"the critic judges menu-set datasets only: {list(menu.DATASET_COUNTS)}")
    prompt = config["prompt"]
    if not all(prompt.get("template", "").count(token) == 1 for token in PLACEHOLDERS):
        raise _fail(f"the critic template needs each of {list(PLACEHOLDERS)} once")
    if set(prompt.get("fixes", {}).values()) != {"B", "S", "Q"} or not prompt.get("verdicts") or not prompt.get("causes"):
        raise _fail("the critic prescribes B, S or Q and needs verdict and cause lists")
    if not {"sai", "dung"} <= set(prompt["verdicts"]):
        raise _fail("the critic's verdicts include dung and sai")
    route = config["route"]
    if route.get("api_protocol") != "openai-responses" or route.get("stream") is not False:
        raise _fail("the critic route is the non-streaming OpenAI Responses API")
    for key in ("max_output_tokens", "timeout_seconds", "max_in_flight", "stop_after_timeouts", "budget_tokens"):
        if isinstance(route.get(key), bool) or not isinstance(route.get(key), int) or route[key] < 1:
            raise _fail(f"route {key} must be a positive integer")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    """The validated critic configuration and the SHA-256 of its bytes."""
    config, digest = _read_json_bytes(path, "critic configuration")
    return validate_config(config), digest


def fold(text: str) -> str:
    """Case, accents and đ folded, so `Đánh giá` and `DANH GIA` read alike."""
    decomposed = unicodedata.normalize("NFD", str(text))
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def critic_prompt(item: v1.EvalItem, answer: str, config: dict[str, Any]) -> str:
    """The critic request: the template with the passage and question of the item's frozen reading prompt and the
    student's answer. Nothing else is added."""
    parts = dp.parse_frozen_prompt(item)
    if parts.kind != "reading":
        raise _fail(f"the critic judges reading items; {item.run_key} is {item.task}")
    text = config["prompt"]["template"].replace("<<PASSAGE>>", parts.body.strip())
    text = text.replace("<<QUESTION>>", parts.question)
    return text.replace("<<ANSWER>>", str(answer or "").strip() or EMPTY_ANSWER)


def parse_critic(text: str, config: dict[str, Any]) -> dict[str, Any]:
    """{verdict, cause, fix, format_ok}: the last value of each label; an id outside its list is None; format_ok
    when the three labels sit on the last three non-empty lines."""
    lines = [fold(line) for line in str(text or "").splitlines() if line.strip()]
    found: dict[str, str] = {}
    where: dict[str, int] = {}
    for index, line in enumerate(lines):
        for key, pattern in _LABELS.items():
            match = pattern.search(line)
            if match:
                found[key], where[key] = match.group(1), index
    allowed = {"verdict": set(config["prompt"]["verdicts"]), "cause": set(config["prompt"]["causes"]),
               "fix": set(config["prompt"]["fixes"])}
    values = {key: found[key] if found.get(key) in allowed[key] else None for key in _LABELS}
    tail = sorted(where.values()) == list(range(len(lines) - 3, len(lines))) if len(where) == 3 else False
    return {**values, "format_ok": tail and all(value is not None for value in values.values())}


def judged_answers(path: Path = JUDGED_SCORES, datasets: list[str] | None = None) -> dict[str, str]:
    """{dataset:item: scored prediction} of Qwen's B-r1 attempts; a repeated attempt fails closed."""
    answers: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["replicate_id"] != JUDGED_REPLICATE or (datasets and row["dataset_id"] not in datasets):
            continue
        key = dp.item_key(row["dataset_id"], row["item_id"])
        if key in answers:
            raise _fail(f"two {JUDGED_REPLICATE} rows for {key}")
        answers[key] = str(row.get("prediction") or "")
    return answers


def build_manifest(config_path: Path = CONFIG_PATH, scores_path: Path = JUDGED_SCORES
                   ) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    config, digest = load_config(config_path)
    datasets = list(config["items"]["datasets"])
    base = [item for item in menu.design_items() if item.dataset_id in datasets]
    counts = dict(sorted(Counter(item.dataset_id for item in base).items()))
    if counts != dict(sorted(config["items"]["dataset_counts"].items())):
        raise _fail(f"the critic items are {counts}, not {config['items']['dataset_counts']}")
    answers = judged_answers(scores_path, datasets)
    missing = [dp.item_key(item.dataset_id, item.item_id) for item in base
               if dp.item_key(item.dataset_id, item.item_id) not in answers]
    if missing:
        raise _fail(f"{len(missing)} items lack a {JUDGED_REPLICATE} answer, for example {missing[:3]}")
    items = [dataclasses.replace(item, replicate_id=REPLICATE,
                                 prompt=critic_prompt(item, answers[dp.item_key(item.dataset_id, item.item_id)], config))
             for item in base]
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate critic run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "critic_id": config["critic_id"],
        "critic_config_sha256": digest, "menu_manifest_self_sha256": menu.load_frozen_manifest()["manifest_sha256"],
        "judged_scores_sha256": v1.sha256_file(scores_path), "judged_replicate": JUDGED_REPLICATE,
        "n": len(items), "item_count": len(base), "dataset_counts": counts,
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest, _ = _read_json_bytes(path, "frozen critic manifest")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the critic manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"critic manifest {manifest['manifest_sha256']}: {manifest['n']} critic calls {manifest['dataset_counts']}")
    if args.write:
        if MANIFEST_PATH.exists():
            raise _fail(f"{MANIFEST_PATH} is frozen; delete it deliberately to rebuild")
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"frozen -> {MANIFEST_PATH}")
    elif MANIFEST_PATH.exists():
        same = load_frozen_manifest() == manifest
        print(f"frozen manifest {'matches' if same else 'DIFFERS'}")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
