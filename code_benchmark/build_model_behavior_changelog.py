"""Compile docs/model-behavior-changelog.md into web/data/model-behavior-changelog.json.

Why: the web app is also served from a container that mounts only `web/`, so the
page cannot read `../docs/` at request time. This keeps the markdown as the
single source of truth and publishes a structured artifact the page can load in
any environment.

From the repository root:
  .venv/bin/python code_benchmark/build_model_behavior_changelog.py
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/model-behavior-changelog.md"
TARGET = ROOT / "web/data/model-behavior-changelog.json"
CATEGORIES = {"model", "provider", "harness", "data", "ops"}
TAG = re.compile(r"^`\[([a-z]+)\]`\s*")


def parse(markdown: str) -> dict:
    doc: dict = {"title": "", "intro": [], "entries": []}
    entry: dict | None = None
    intro: list[str] = []

    def flush_intro() -> None:
        if intro:
            doc["intro"].append(" ".join(intro))
            intro.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip() == "---":
            continue
        if line.startswith("> "):
            intro.append(line[2:].strip())
            continue
        if line.startswith(">"):
            flush_intro()
            continue
        if line.startswith("# "):
            doc["title"] = line[2:].strip()
            continue
        if line.startswith("## "):
            flush_intro()
            entry = {"title": line[3:].strip(), "meta": [], "items": []}
            doc["entries"].append(entry)
            continue
        if entry is None:
            continue
        if line.startswith("- "):
            text = line[2:].strip()
            match = TAG.match(text)
            category = match.group(1) if match and match.group(1) in CATEGORIES else "other"
            if match and category != "other":
                text = text[match.end():]
            entry["items"].append({"category": category, "text": text})
            continue
        entry["meta"].append(line.strip())

    flush_intro()
    return doc


def main() -> None:
    try:
        markdown = SOURCE.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Error: cannot read {SOURCE.relative_to(ROOT)}: {exc}") from exc
    parsed = parse(markdown)
    if not parsed["title"] or not parsed["entries"]:
        raise SystemExit("Error: changelog markdown is missing its title or entries")
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        **parsed,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temporary = TARGET.with_suffix(TARGET.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(TARGET)
    print(
        f"wrote {TARGET.relative_to(ROOT)}: {len(payload['entries'])} entries, "
        f"{sum(len(entry['items']) for entry in payload['entries'])} items"
    )


if __name__ == "__main__":
    sys.exit(main())
