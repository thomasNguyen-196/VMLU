"""The Muse router's design-stage check (openspec change diagnostic-llm-router, spec `diagnostic-llm-router`;
card MC-98).

* Router: Muse Spark 1.3 on the direct OpenCode Go route reads an item's passage and question and returns one group
  from the closed list of data/diagnostic_llm_router/router_v1.json, on a last line `Nhóm: <id>`. It never sees the
  gold answer or any outcome, and it does not answer the question.
* Items: the 591 ViBidLQA test items of the menu set, one router call each (run key `dataset:item:router-1`).
* Mapping (cross-draw): each group gets the arm (B, Q or S) with the best mean token-F1 on one draw of its items and
  is scored on the other draw, both ways, averaged per item. Ties go to the more thorough arm (B < Q < S). Groups under
  the minimum size, and unrecognised router outputs, take the fallback arm S.
* Comparator: the frozen keyword grouping of the question text in the same file, mapped the same way.

Usage (repo root):
  .venv/bin/python -m code_benchmark.diagnostic_llm_router            # build the manifest and compare it with the frozen one
  .venv/bin/python -m code_benchmark.diagnostic_llm_router --write    # freeze data/diagnostic_llm_router/router_labels_v1.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import unicodedata
from collections import defaultdict
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

CONFIG_PATH = menu.DATA_DIR / "router_v1.json"
MANIFEST_PATH = menu.DATA_DIR / "router_labels_v1.json"
REGISTRATION_PATH = menu.DATA_DIR / "registration_labels.json"
PROTOCOL_ID = "vmlu-diagnostic-llm-router-labels"
PHASE = "labels"
DATASET = "vi-multimodel-v1-bidlqa-test"
REPLICATE = "router-1"
ARMS = ("B", "Q", "S")  # least to most thorough
CONFIG_KEYS = ("router_id", "protocol_id", "protocol_version", "change", "purpose", "items", "groups", "prompt", "route",
               "mapping", "keyword_comparator", "analysis")
PLACEHOLDERS = ("<<GROUPS>>", "<<PASSAGE>>", "<<QUESTION>>", "<<GROUP_IDS>>")
_ID = re.compile(r"^[a-z_]+$")
_LABEL = re.compile(r"nhóm\s*[:：]\s*[`*\s]*([A-Za-z_]+)[`*]*", re.IGNORECASE)


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
        raise _fail(f"the router configuration must have exactly the keys {list(CONFIG_KEYS)}")
    if config["protocol_id"] != PROTOCOL_ID or config["protocol_version"] != 1:
        raise _fail("unsupported router configuration id/version")
    if config["items"].get("dataset") != DATASET or config["items"].get("calls_per_item") != 1:
        raise _fail(f"the router labels {DATASET} with one call per item")
    ids = [group.get("id") for group in config["groups"]]
    if not ids or len(ids) != len(set(ids)) or not all(isinstance(i, str) and _ID.match(i) for i in ids):
        raise _fail("router groups need unique lower-case ids")
    if not all(isinstance(group.get("definition"), str) and group["definition"].strip() for group in config["groups"]):
        raise _fail("every router group needs a definition")
    template = config["prompt"].get("template", "")
    if not all(template.count(token) == 1 for token in PLACEHOLDERS):
        raise _fail(f"the router template needs each of {list(PLACEHOLDERS)} once")
    if not all(token in config["prompt"].get("group_line", "") for token in ("<<ID>>", "<<DEFINITION>>")):
        raise _fail("the group line needs <<ID>> and <<DEFINITION>>")
    route = config["route"]
    if route.get("api_protocol") != "openai-responses" or route.get("stream") is not False:
        raise _fail("the router route is the non-streaming OpenAI Responses API")
    for key in ("max_output_tokens", "timeout_seconds", "max_in_flight", "stop_after_timeouts", "budget_tokens"):
        if isinstance(route.get(key), bool) or not isinstance(route.get(key), int) or route[key] < 1:
            raise _fail(f"route {key} must be a positive integer")
    mapping = config["mapping"]
    if mapping.get("arms") != list(ARMS) or mapping.get("fallback_arm") not in ARMS:
        raise _fail(f"the mapping chooses among {list(ARMS)} with a fallback arm among them")
    size = mapping.get("min_group_items")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise _fail("min_group_items must be a positive integer")
    keywords = config["keyword_comparator"]
    for group in keywords.get("groups", []):
        try:
            re.compile(group["pattern"])
        except (KeyError, re.error) as exc:
            raise _fail(f"keyword group {group.get('id')!r} has an invalid pattern: {exc}") from exc
    if not keywords.get("groups") or not isinstance(keywords.get("fallback"), str):
        raise _fail("the keyword comparator needs groups and a fallback id")
    return config


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    """The validated router configuration and the SHA-256 of its bytes."""
    config, digest = _read_json_bytes(path, "router configuration")
    return validate_config(config), digest


def group_ids(config: dict[str, Any]) -> list[str]:
    return [group["id"] for group in config["groups"]]


def router_prompt(item: v1.EvalItem, config: dict[str, Any]) -> str:
    """The router request: the group list, then the passage and question of the item's frozen reading prompt."""
    parts = dp.parse_frozen_prompt(item)
    if parts.kind != "reading":
        raise _fail(f"the router reads reading items; {item.run_key} is {item.task}")
    prompt = config["prompt"]
    lines = [prompt["group_line"].replace("<<ID>>", group["id"]).replace("<<DEFINITION>>", group["definition"])
             for group in config["groups"]]
    text = prompt["template"].replace("<<GROUPS>>", "\n".join(lines))
    text = text.replace("<<GROUP_IDS>>", prompt["group_ids_separator"].join(group_ids(config)))
    return text.replace("<<PASSAGE>>", parts.body.strip()).replace("<<QUESTION>>", parts.question)


def parse_group(text: str, config: dict[str, Any]) -> tuple[str | None, bool]:
    """(group id or None when unrecognised, whether the label sits on the last non-empty line)."""
    body = str(text or "").strip()
    matches = list(_LABEL.finditer(body))
    if not matches:
        return None, False
    group = matches[-1].group(1).lower()
    lines = [line for line in body.splitlines() if line.strip()]
    on_last_line = bool(lines) and _LABEL.search(lines[-1]) is not None and matches[-1].start() >= len(body) - len(lines[-1])
    return (group if group in group_ids(config) else None), on_last_line


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def keyword_group(question: str, config: dict[str, Any]) -> str:
    folded = fold(question)
    for group in config["keyword_comparator"]["groups"]:
        if re.search(group["pattern"], folded):
            return group["id"]
    return config["keyword_comparator"]["fallback"]


def fit_mapping(cells: list[dict[str, dict[str, Any]]], groups: list[str | None], draw: str,
                config: dict[str, Any]) -> dict[str | None, str]:
    """{group: arm} chosen on one draw; ties to the more thorough arm; small groups and None take the fallback."""
    mapping_rule = config["mapping"]
    members: dict[str | None, list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for cell, group in zip(cells, groups, strict=True):
        members[group].append(cell)
    mapping: dict[str | None, str] = {}
    for group, cells_in_group in members.items():
        if group is None or len(cells_in_group) < mapping_rule["min_group_items"]:
            mapping[group] = mapping_rule["fallback_arm"]
            continue
        means = {arm: sum(float(cell[f"{arm}{draw}"]["token_f1"]) for cell in cells_in_group) / len(cells_in_group)
                 for arm in ARMS}
        best = max(means.values())
        mapping[group] = [arm for arm in ARMS if best - means[arm] <= 1e-12][-1]
    return mapping


def cross_draw_scores(cells: list[dict[str, dict[str, Any]]], groups: list[str | None], config: dict[str, Any]
                      ) -> tuple[list[float], dict[str | None, str], dict[str | None, str]]:
    """Per-item routed token-F1: the arm chosen on draw 1 scored on draw 2, averaged with the reverse."""
    first, second = fit_mapping(cells, groups, "1", config), fit_mapping(cells, groups, "2", config)
    scores = [(float(cell[f"{first[group]}2"]["token_f1"]) + float(cell[f"{second[group]}1"]["token_f1"])) / 2
              for cell, group in zip(cells, groups, strict=True)]
    return scores, first, second


def design_items() -> list[v1.EvalItem]:
    """The ViBidLQA items of the menu set, in menu-manifest order."""
    return [item for item in menu.design_items() if item.dataset_id == DATASET]


def build_manifest(config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, v1.EvalItem]]:
    config, digest = load_config(config_path)
    base = design_items()
    items = [dataclasses.replace(item, replicate_id=REPLICATE, prompt=router_prompt(item, config)) for item in base]
    rebuilt = {item.run_key: item for item in items}
    if len(rebuilt) != len(items):
        raise _fail("duplicate router run keys")
    manifest: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID, "protocol_version": 1, "phase": PHASE, "router_id": config["router_id"],
        "router_config_sha256": digest, "menu_manifest_self_sha256": menu.load_frozen_manifest()["manifest_sha256"],
        "n": len(items), "item_count": len(base), "dataset_counts": {DATASET: len(base)},
        "items": [v1.manifest_item(item) for item in items],
    }
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, rebuilt


def load_frozen_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest, _ = _read_json_bytes(path, "frozen router-labels manifest")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the router-labels manifest (offline).")
    ap.add_argument("--write", action="store_true", help=f"freeze it as {MANIFEST_PATH}")
    args = ap.parse_args(argv)
    manifest, _ = build_manifest()
    print(f"router-labels manifest {manifest['manifest_sha256']}: {manifest['n']} router calls")
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
