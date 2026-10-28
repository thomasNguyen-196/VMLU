"""Offline tests for the campaign ledger adapter (openspec change diagnostic-prospective-campaign, task 8.3).

They read the real campaign outputs under the ignored all_res/, like test_diagnostic.py, and tamper only with
copies in temporary directories. Run from the repo root:
  .venv/bin/python -m unittest code_benchmark.test_diagnostic_campaign_ledger
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from code_benchmark import diagnostic as diag
from code_benchmark import diagnostic_campaign_ledger as campaign

CORE = "qwen-mc93-core"
SUPPLEMENT = "qwen-mc91-wide-b-r2"


def _copy_run(source_id: str, folder: Path) -> dict:
    source = dict(diag._read_registry_source(source_id))
    original = diag._source_paths(source)
    run_dir = folder / "source-run"
    run_dir.mkdir(parents=True)
    for name in ("run", "predictions", "scores", "summary"):
        shutil.copyfile(original[name], run_dir / original[name].name)
    source["run_dir"] = str(run_dir.relative_to(diag.ROOT))
    return source


def _rewrite_jsonl(path: Path, change) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    change(rows)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class CampaignRegistryTests(unittest.TestCase):
    def _load(self, sources: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.json"
            path.write_text(json.dumps({"version": 1, "sources": sources}), encoding="utf-8")
            return diag.load_registry(path)

    def test_registry_declares_the_four_campaign_outputs(self):
        sources = {key: value for key, value in diag.load_registry().items() if value["adapter"] == diag.CAMPAIGN_ADAPTER}
        self.assertEqual({key: value["measurement_card_id"] for key, value in sources.items()},
                         {"qwen-mc90-wide": "MC-90", "qwen-mc91-wide-b-r2": "MC-91",
                          "qwen-mc92-wide-s-r2": "MC-92", "qwen-mc93-core": "MC-93"})
        self.assertEqual(sources[CORE]["evidence"].keys(), {"O", "K"})

    def test_campaign_entries_are_validated(self):
        good = dict(diag._read_registry_source(CORE))
        self.assertIn(CORE, self._load([good]))
        for broken, message in (
                ({**good, "family": "qwen-mc72"}, "goes with family"),
                ({key: value for key, value in good.items() if key != "phase"}, "needs phase"),
                ({key: value for key, value in good.items() if key != "supplement_id"}, "needs phase"),
                ({**good, "evidence": {"KS": "x.jsonl"}}, "evidence paths for O or K only"),
                ({**good, "adapter": "campaign-arms-v2"}, "unsupported source adapter")):
            with self.assertRaisesRegex(diag.DiagnosticError, message):
                self._load([broken])


class CampaignLedgerTests(unittest.TestCase):
    def test_core_ledger_has_every_arm_parity_and_no_endpoint_fields(self):
        rows, provenance = diag.build_source_ledger(diag._read_registry_source(CORE))
        self.assertEqual(len(rows), 432)
        self.assertEqual(provenance["arm_observations"], {"B": 180, "K": 24, "KS": 24, "O": 24, "S": 180})
        self.assertEqual(provenance["ledger_status"], "complete")
        self.assertTrue(provenance["parity"]["item_score_parity"] and provenance["parity"]["summary_parity"])
        self.assertTrue(provenance["campaign"]["manifest_rebuilt_from_frozen_inputs"])
        self.assertEqual(provenance["campaign"]["evidence_sha256"].keys(), {"K", "O"})
        condition = provenance["run_metadata"]["condition"]
        for field in ("endpoint_host", "base_url_sha256", "provider", "execution_history", "api_key"):
            self.assertNotIn(field, condition)
        self.assertEqual({row["arm"] for row in rows if row["retrieval"] is not None}, {"K", "KS"})
        self.assertEqual(sum("at_token_cap" in row["flags"] for row in rows), 2)
        self.assertTrue(all(row["observation_key"].startswith(f"{CORE}|") for row in rows))
        reasoning_mc = next(row for row in rows if row["arm"] == "S" and row["task_mode"] == "multiple_choice")
        self.assertEqual(reasoning_mc["scoring"]["source"], "final_segment")
        self.assertIsNotNone(reasoning_mc["scoring"]["final_segment"])

    def test_supplement_ledger_keeps_its_replicate(self):
        rows, provenance = diag.build_source_ledger(diag._read_registry_source(SUPPLEMENT))
        self.assertEqual(len(rows), 1239)
        self.assertEqual(Counter(row["replicate_id"] for row in rows), Counter({"B-r2": 1239}))
        self.assertEqual(provenance["supplement_id"], "wide-b-r2")
        self.assertTrue(provenance["parity"]["summary_parity"])

    def test_registry_mismatches_fail(self):
        source = dict(diag._read_registry_source(SUPPLEMENT))
        with self.assertRaisesRegex(diag.DiagnosticError, "manifest identity/hash mismatch"):
            diag.build_source_ledger({**source, "expected_manifest_sha256": "0" * 64})
        with self.assertRaisesRegex(diag.DiagnosticError, "phase or supplement differs"):
            diag.build_source_ledger({**source, "supplement_id": None})
        with self.assertRaisesRegex(diag.DiagnosticError, "measurement_card_id differs"):
            diag.build_source_ledger({**source, "measurement_card_id": "MC-90"})

    def test_tampered_run_files_fail(self):
        def first_k(rows):
            return next(row for row in rows if row["replicate_id"].startswith("K-"))

        cases = (
            ("scores.jsonl", lambda rows: rows[0].update(prediction="conflicting-answer"), "prediction scorer parity failure"),
            ("predictions.jsonl", lambda rows: rows[0].update(raw_prompt=rows[0]["raw_prompt"] + " "),
             "does not hash to its manifest prompt"),
            ("predictions.jsonl", lambda rows: first_k(rows)["retrieval"].update(query_sha256="0" * 64),
             "retrieval trace differs"),
        )
        for name, change, message in cases:
            with self.subTest(file=name, message=message), tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
                source = _copy_run(CORE, Path(temp))
                _rewrite_jsonl(diag.ROOT / source["run_dir"] / name, change)
                with self.assertRaisesRegex(diag.DiagnosticError, message):
                    diag.build_source_ledger(source)

    def test_changed_summary_format_metric_fails(self):
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            source = _copy_run(CORE, Path(temp))
            path = diag.ROOT / source["run_dir"] / "summary.json"
            summary = json.loads(path.read_text(encoding="utf-8"))
            summary["arms"]["S"][0]["format_ok_n"] += 1
            path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(diag.DiagnosticError, "format_ok_n summary parity failure"):
                diag.build_source_ledger(source)

    def test_changed_evidence_fails_the_rebuild(self):
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            source = dict(diag._read_registry_source(CORE))
            original = diag.ROOT / source["evidence"]["O"]
            copied = Path(temp) / original.name
            rows = [json.loads(line) for line in original.read_text(encoding="utf-8").splitlines() if line.strip()]
            rows.pop()
            copied.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            source["evidence"] = {**source["evidence"], "O": str(copied.relative_to(diag.ROOT))}
            with self.assertRaises(SystemExit):
                diag.build_source_ledger(source)

    def test_missing_observation_is_kept_and_marks_the_source_incomplete(self):
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            source = _copy_run(CORE, Path(temp))
            run_dir = diag.ROOT / source["run_dir"]
            dropped = json.loads((run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()[-1])["run_key"]
            for name in ("predictions.jsonl", "scores.jsonl"):
                _rewrite_jsonl(run_dir / name, lambda rows: rows.remove(
                    next(row for row in rows if diag._identity(row) == dropped)))
            rows, provenance = diag.build_source_ledger(source)
        self.assertEqual(len(rows), 432)
        missing = next(row for row in rows if row["observation_key"] == f"{CORE}|{dropped}")
        self.assertEqual(missing["execution_status"], "missing_request")
        self.assertEqual(provenance["ledger_status"], "source_incomplete")

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            root = Path(temp) / "sources"
            first = diag.build_ledger(CORE, output_dir=root)
            again = diag.build_ledger(CORE, output_dir=root)
            self.assertEqual(first["ledger_sha256"], again["ledger_sha256"])
            report = json.loads((root / CORE / "parity-report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["item_score_parity"] and report["summary_parity"])
            self.assertEqual(report["ledger_status"], "complete")

    def test_metadata_allowlist_extends_the_v1_one(self):
        self.assertLessEqual(diag.SOURCE_METADATA_ALLOWLIST, campaign.METADATA_ALLOWLIST)
        self.assertFalse({"endpoint_host", "base_url_sha256", "provider"} & campaign.METADATA_ALLOWLIST)


if __name__ == "__main__":
    unittest.main()
