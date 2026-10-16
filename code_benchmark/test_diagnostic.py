"""Offline contract tests for the VMLU diagnostic preparation workflow."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from code_benchmark import diagnostic as diag


class DiagnosticProtocolTests(unittest.TestCase):
    def test_protocol_taxonomy_and_unresolved_runtime_gates(self):
        protocol, digest = diag.load_protocol()
        self.assertEqual(protocol["protocol_id"], "vmlu-diagnostic-v1")
        self.assertEqual(len(digest), 64)
        self.assertEqual(sum(protocol["pilot"]["dataset_counts"].values()), 60)
        report = diag.readiness_report()
        self.assertFalse(report["inference_ready"])
        self.assertIn("unresolved control: verified_endpoint", report["inference_blockers"])

    def test_unknown_protocol_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            protocol = json.loads(diag.PROTOCOL_PATH.read_text(encoding="utf-8"))
            protocol["protocol_version"] = 99
            path = root / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            shutil.copy(diag.TAXONOMY_PATH, root / "taxonomy.json")
            shutil.copy(diag.REVIEW_SCHEMA_PATH, root / "review_schema.json")
            with self.assertRaisesRegex(diag.DiagnosticError, "unsupported diagnostic protocol"):
                diag.load_protocol(path)

    def test_unknown_registry_source_is_rejected(self):
        with self.assertRaisesRegex(diag.DiagnosticError, "unknown declared source"):
            diag._read_registry_source("not-a-source")


class DiagnosticSourceTests(unittest.TestCase):
    def _copy_source_run(self, source_id: str, folder: Path) -> dict:
        source = dict(diag._read_registry_source(source_id))
        original = diag._source_paths(source)
        run_dir = folder / "source-run"
        run_dir.mkdir(parents=True)
        for name in ("run", "predictions", "scores", "summary"):
            shutil.copyfile(original[name], run_dir / original[name].name)
        source["run_dir"] = str(run_dir.relative_to(diag.ROOT))
        return source

    def test_duplicate_prediction_is_rejected(self):
        source = diag._read_registry_source("qwen-mc72")
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            source = self._copy_source_run("qwen-mc72", Path(temp))
            prediction_path = diag._source_paths(source)["predictions"]
            last = prediction_path.read_text(encoding="utf-8").splitlines()[-1]
            with prediction_path.open("a", encoding="utf-8") as handle:
                handle.write(last + "\n")
            with self.assertRaisesRegex(diag.DiagnosticError, "duplicate row identity"):
                diag.build_source_ledger(source)

    def test_wrong_manifest_identity_is_rejected(self):
        source = diag._read_registry_source("qwen-mc72")
        source["expected_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(diag.DiagnosticError, "manifest identity/hash mismatch"):
            diag.build_source_ledger(source)

    def test_prompt_drift_against_parent_is_rejected(self):
        source = dict(diag._read_registry_source("qwen-mc72"))
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            directory = Path(temp)
            manifest = json.loads((diag.ROOT / source["manifest_path"]).read_text(encoding="utf-8"))
            manifest["items"][0]["prompt_sha256"] = "f" * 64
            unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
            manifest["manifest_sha256"] = diag._sha256_bytes(diag._canonical_json(unhashed))
            manifest_path = directory / "changed-manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            source["manifest_path"] = str(manifest_path)
            source["expected_manifest_sha256"] = manifest["manifest_sha256"]
            with self.assertRaisesRegex(diag.DiagnosticError, "not prompt-identical"):
                diag.build_source_ledger(source)

    def test_conflicting_score_and_unsupported_scorer_are_rejected(self):
        source_id = "qwen-mc72"
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            source = self._copy_source_run(source_id, Path(temp))
            score_path = diag._source_paths(source)["scores"]
            rows = score_path.read_text(encoding="utf-8").splitlines()
            row = json.loads(rows[0])
            row["prediction"] = "conflicting-answer"
            rows[0] = json.dumps(row, ensure_ascii=False)
            score_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(diag.DiagnosticError, "prediction scorer parity failure"):
                diag.build_source_ledger(source)
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            source = self._copy_source_run(source_id, Path(temp))
            summary_path = diag._source_paths(source)["summary"]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            next(row for row in summary["datasets"] if row["dataset_id"].endswith("vi-squad-200"))["scorer_version"] = "invented-scorer"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(diag.DiagnosticError, "unsupported reading scorer"):
                diag.build_source_ledger(source)

    def test_mc72_source_rebuilds_all_items_and_preserves_derived_manifest(self):
        source = diag._read_registry_source("qwen-mc72")
        rows, provenance = diag.build_source_ledger(source)
        self.assertEqual(len(rows), 1299)
        self.assertEqual(provenance["manifest_sha256"], "c364a66e5862bab3ea81eb93e87421aa5bac2ac15203b1a258adebbd8907dcc8")
        self.assertEqual(provenance["parent_manifest_sha256"], "0d413341f1fceea2e131e3a7fe7b73032e31303c8935ce5fba93c5f40b126551")
        self.assertTrue(provenance["parity"]["item_score_parity"])
        self.assertTrue(provenance["parity"]["summary_parity"])

    def test_mimo_source_has_separate_identity_and_condition(self):
        source = diag._read_registry_source("mimo-v2-6-flash-v1-main")
        rows, provenance = diag.build_source_ledger(source)
        self.assertEqual(len(rows), 2043)
        self.assertEqual(provenance["model_identity"], "mimo-v2.6-flash")
        self.assertEqual(provenance["run_metadata"]["measurement_card_id"], "MC-54")
        self.assertTrue(provenance["parity"]["summary_parity"])

    def test_ledger_projection_excludes_credential_and_endpoint_fields(self):
        source = diag._read_registry_source("qwen-mc72")
        rows, provenance = diag.build_source_ledger(source)
        self.assertNotIn("credential_source", provenance["run_metadata"]["condition"])
        self.assertNotIn("endpoint_host", provenance["run_metadata"]["condition"])
        self.assertNotIn("api_key", provenance["run_metadata"]["condition"])
        self.assertTrue(rows[0]["observation_key"].startswith("qwen-mc72|"))
        self.assertIsNone(rows[0]["action_label"])

    def test_incomplete_artifact_retains_expected_missing_row_and_blocks_readiness(self):
        source = diag._read_registry_source("qwen-mc72")
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            copied = Path(temp) / "incomplete-source"
            copied.mkdir()
            original = diag._source_paths(source)
            for name in ("run", "predictions", "scores", "summary"):
                shutil.copyfile(original[name], copied / original[name].name)
            pred = (copied / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
            scores = (copied / "scores.jsonl").read_text(encoding="utf-8").splitlines()
            (copied / "predictions.jsonl").write_text("\n".join(pred[:-1]) + "\n", encoding="utf-8")
            (copied / "scores.jsonl").write_text("\n".join(scores[:-1]) + "\n", encoding="utf-8")
            test_source = dict(source)
            test_source["run_dir"] = str(copied.relative_to(diag.ROOT))
            rows, provenance = diag.build_source_ledger(test_source)
        self.assertEqual(len(rows), 1299)
        self.assertEqual(rows[-1]["execution_status"], "missing_request")
        self.assertEqual(provenance["ledger_status"], "source_incomplete")
        self.assertFalse(provenance["parity"]["summary_parity"])

    def test_changed_complete_summary_metric_fails_publication(self):
        source = diag._read_registry_source("qwen-mc72")
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            copied = Path(temp) / "bad-summary-source"
            copied.mkdir()
            original = diag._source_paths(source)
            for name in ("run", "predictions", "scores", "summary"):
                shutil.copyfile(original[name], copied / original[name].name)
            summary_path = copied / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["datasets"][0]["token_f1"] += 1
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            test_source = dict(source)
            test_source["run_dir"] = str(copied.relative_to(diag.ROOT))
            with self.assertRaisesRegex(diag.DiagnosticError, "summary parity failure"):
                diag.build_source_ledger(test_source)

    def test_build_is_idempotent_and_different_label_isolated(self):
        with tempfile.TemporaryDirectory(dir=diag.OUTPUT_ROOT) as temp:
            root = Path(temp) / "sources"
            first = diag.build_ledger("qwen-mc72", output_dir=root)
            again = diag.build_ledger("qwen-mc72", output_dir=root)
            self.assertEqual(first["ledger_sha256"], again["ledger_sha256"])
            self.assertTrue((root / "qwen-mc72" / "parity-report.json").is_file())

    def test_outputs_inside_source_tree_are_rejected(self):
        source = diag._read_registry_source("qwen-mc72")
        with self.assertRaisesRegex(diag.DiagnosticError, "may not overlap a source"):
            diag.build_ledger("qwen-mc72", output_dir=diag.ROOT / source["run_dir"])


class DiagnosticPilotReviewTests(unittest.TestCase):
    def _pilot(self, temp: str) -> Path:
        protocol, digest = diag.load_protocol()
        rows = []
        for dataset in protocol["pilot"]["dataset_counts"]:
            for index in range(12):
                row = {field: "fixture" for field in diag.REVIEW_IMMUTABLE_COLUMNS if field != "packet_sha256"}
                row.update(observation_key=f"fixture|{dataset}:{index}", item_key=f"{dataset}:{index}", dataset_id=dataset,
                           item_id=str(index), task_mode="open_book_reading", question="Fixture question?", rendered_input="Fixture evidence.",
                           raw_response="Fixture", prediction="Fixture", source_gold="Fixture", source_metrics={"em": 1},
                           protocol_sha256=digest, rubric_version=diag.RUBRIC_VERSION, exposure="development-audit")
                rows.append(row)
        content_digest = diag._sha256_bytes(b"".join(diag._canonical_json(r)+b"\n" for r in rows))
        for row in rows: row["packet_sha256"] = content_digest
        second = [row["observation_key"] for row in rows if int(row["item_id"]) < 3]
        selection = {"protocol_id": protocol["protocol_id"], "protocol_sha256": digest, "annotation_revision": 4,
                     "review_schema_version": diag.REVIEW_SCHEMA_VERSION, "rubric_version": diag.RUBRIC_VERSION,
                     "pilot_content_sha256": content_digest, "source_ledger_sha256": "fixture", "item_count": 60,
                     "second_review_count": 15, "second_review_keys": second,
                     "allocation": {dataset: {"selected": 12, "reasons": {"fixture": 12}} for dataset in protocol["pilot"]["dataset_counts"]}}
        tmp = Path(temp); dest = tmp/"all_res"/"diagnostic_v1"/"fixture"
        with patch.object(diag, "ROOT", tmp): diag._publish_pilot(dest, rows, selection, protocol)
        return dest

    def _packet(self, pilot: Path, name: str, changes: dict | None = None, *, scope="primary-60", fill_all=False) -> Path:
        with (pilot/("review_B_second_subset.csv" if scope == "independent-15" else "review_A.csv")).open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows: row.update(annotator_id=name, review_scope=scope)
        base = dict(review_assistance_mode="human_only", semantic_correctness="correct", gold_validity="valid",
                    input_evidence_sufficiency="sufficient", corpus_evidence_availability="not_assessed", corpus_evidence_reference="",
                    diagnostic_outcome="no_observed_issue", observed_issues="", audit_evidence_kind="input_span",
                    evidence_reference="Fixture passage, sentence 1", diagnostic_labels="", diagnostic_support="[]",
                    rationale="Fixture audit only.", reviewer_attestation=diag.HUMAN_ONLY_ATTESTATION,
                    blind_review_attestation=diag.BLIND_ATTESTATION if scope == "independent-15" else "", review_status="reviewed")
        for row in (rows if fill_all else rows[:1]): row.update(base | (changes or {}))
        path=pilot/f"{name}-packet.csv";diag._write_csv(path,rows,diag.REVIEW_COLUMNS);return path

    def _contrast(self, pilot: Path, *, label="external_evidence_gap", kind="controlled_model_contrast") -> str:
        rows, selection = diag._read_pilot(pilot)
        artifact=pilot/"controlled-evidence.txt";artifact.write_text("Fixture controlled comparison; not a live model result.")
        record=dict(contrast_id="fixture-contrast",kind=kind,label=label,observation_key=rows[0]["observation_key"],
                    pilot_content_sha256=selection["pilot_content_sha256"],baseline_condition_id="fixture-B",intervention_condition_id="fixture-K",
                    evidence_artifact=artifact.name,evidence_artifact_sha256=diag._sha256_file(artifact),reviewer_id="fixture-reviewer",
                    rationale="Fixture same-item controls only.",verified=True,other_conditions_controlled=True,supports_hypothesis=True)
        diag._write_records_jsonl(pilot/"contrasts.jsonl",[record]);return record["contrast_id"]

    def _issue(self, label="external_evidence_gap", status="hypothesis", contrast_id="") -> dict:
        return dict(semantic_correctness="incorrect",diagnostic_outcome="issue_observed",observed_issues="missing_input_evidence",
                    input_evidence_sufficiency="insufficient",diagnostic_labels=label,
                    diagnostic_support=json.dumps([dict(label=label,status=status,evidence_reference="Fixture evidence for this hypothesis",contrast_id=contrast_id)]))

    def test_no_issue_audit_needs_no_causal_tier_and_bom_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);path=self._packet(pilot,"A");path.write_bytes(b"\xef\xbb\xbf"+path.read_bytes())
            result=diag.import_review(pilot,path,annotator_id="A");self.assertEqual(result["reviewed"],1)
            report=diag._read_json(pilot/"audit-report.json");self.assertEqual(report["reviewed_no_issue_control_n"],1)
            self.assertEqual(report["diagnostic_supervision_eligible_n"],0)

    def test_arbitrary_human_signoff_cannot_claim_controlled_support(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);path=self._packet(pilot,"A",self._issue(status="contrast_supported",contrast_id="invented"))
            with self.assertRaisesRegex(diag.DiagnosticError,"matching registered"):diag.import_review(pilot,path,annotator_id="A")

    def test_missing_input_is_eligible_for_matching_external_evidence_contrast(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);identity=self._contrast(pilot)
            path=self._packet(pilot,"A",self._issue(status="contrast_supported",contrast_id=identity))
            diag.import_review(pilot,path,annotator_id="A");report=diag._read_json(pilot/"audit-report.json")
            self.assertEqual(report["diagnostic_supervision_eligible_n"],1)
            self.assertEqual(len(report["diagnostic_supervision_by_label"]["external_evidence_gap"]),1)
            (pilot/"controlled-evidence.txt").write_text("tampered")
            with self.assertRaisesRegex(diag.DiagnosticError,"artifact hash"):diag._write_audit_report(pilot,[])

    def test_reasoning_support_requires_sufficient_premises(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);identity=self._contrast(pilot,label="reasoning_gap")
            path=self._packet(pilot,"A",self._issue("reasoning_gap","contrast_supported",identity))
            with self.assertRaisesRegex(diag.DiagnosticError,"sufficient input"):diag.import_review(pilot,path,annotator_id="A")

    def test_retrieval_support_requires_separate_corpus_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);identity=self._contrast(pilot,label="retrieval_gap")
            changes=self._issue("retrieval_gap","contrast_supported",identity)
            path=self._packet(pilot,"A",changes)
            with self.assertRaisesRegex(diag.DiagnosticError,"corpus evidence present"):diag.import_review(pilot,path,annotator_id="A")
            changes.update(corpus_evidence_availability="present",corpus_evidence_reference="")
            path=self._packet(pilot,"A",changes)
            with self.assertRaisesRegex(diag.DiagnosticError,"scoped evidence reference"):diag.import_review(pilot,path,annotator_id="A")

    def test_parametric_cause_cannot_be_established_by_parser_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);identity=self._contrast(pilot,label="parametric_knowledge_gap",kind="deterministic_replay")
            path=self._packet(pilot,"A",self._issue("parametric_knowledge_gap","contrast_supported",identity))
            with self.assertRaisesRegex(diag.DiagnosticError,"controlled model probes"):diag.import_review(pilot,path,annotator_id="A")

    def test_unknown_cause_is_empty_hypotheses_and_not_a_forced_label(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);changes=self._issue();changes.update(diagnostic_labels="",diagnostic_support="[]")
            path=self._packet(pilot,"A",changes);diag.import_review(pilot,path,annotator_id="A")
            self.assertEqual(diag._read_json(pilot/"audit-report.json")["diagnostic_supervision_eligible_n"],0)

    def test_one_support_per_hypothesis_and_immutable_source_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);changes=self._issue();changes["diagnostic_support"]="[]"
            path=self._packet(pilot,"A",changes)
            with self.assertRaisesRegex(diag.DiagnosticError,"match every"):diag.import_review(pilot,path,annotator_id="A")
            path=self._packet(pilot,"A",dict(question="edited source"))
            with self.assertRaisesRegex(diag.DiagnosticError,"edited immutable"):diag.import_review(pilot,path,annotator_id="A")

    def test_no_issue_rejects_cause_labels_and_unavailable_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp)
            for changes in (dict(diagnostic_labels="reasoning_gap"),dict(audit_evidence_kind="unavailable")):
                path=self._packet(pilot,"A",changes)
                with self.assertRaises(diag.DiagnosticError):diag.import_review(pilot,path,annotator_id="A")

    def test_unresolved_is_deferred_without_forced_issues(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);changes=dict(semantic_correctness="uncertain",diagnostic_outcome="unresolved",audit_evidence_kind="unavailable",review_status="deferred")
            diag.import_review(pilot,self._packet(pilot,"A",changes),annotator_id="A")
            changes["review_status"]="reviewed"
            with self.assertRaisesRegex(diag.DiagnosticError,"unresolved outcome"):diag.import_review(pilot,self._packet(pilot,"B",changes),annotator_id="B")

    def test_independent_packet_rejects_ai_assistance_and_nonblind_review(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp)
            for changes in (dict(review_assistance_mode="ai_assisted",reviewer_attestation=diag.AI_ASSISTED_ATTESTATION),dict(blind_review_attestation="")):
                path=self._packet(pilot,"B",changes,scope="independent-15")
                with self.assertRaisesRegex(diag.DiagnosticError,"human_only and blind"):diag.import_review(pilot,path,annotator_id="B")

    def test_two_primary_ids_do_not_complete_blind_subset(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp)
            for identity in ("A","B"):diag.import_review(pilot,self._packet(pilot,identity,fill_all=True),annotator_id=identity)
            report=diag._read_json(pilot/"audit-report.json");self.assertFalse(report["audit_complete"])
            self.assertEqual(report["independent_subset_paired_n"],0)

    def test_real_scope_pair_reports_ai_assisted_design_and_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp)
            diag.import_review(pilot,self._packet(pilot,"A",dict(review_assistance_mode="ai_assisted",reviewer_attestation=diag.AI_ASSISTED_ATTESTATION),fill_all=True),annotator_id="A")
            diag.import_review(pilot,self._packet(pilot,"B",scope="independent-15",fill_all=True),annotator_id="B")
            report=diag._read_json(pilot/"audit-report.json");self.assertTrue(report["audit_complete"])
            self.assertEqual(report["independent_subset_paired_n"],15);self.assertEqual(report["semantic_correctness_agreement"]["paired_n"],15)
            self.assertEqual(report["paired_review_assistance_modes"],{"ai_assisted|human_only":15})
            self.assertEqual(report["diagnostic_label_agreement"]["paired_n"],0)
            self.assertEqual(report["reviewed_no_issue_control_n"],60)
            self.assertFalse(diag.readiness_report(audit_dir=pilot)["inference_ready"])

    def test_scope_and_identity_are_not_interchangeable(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp)
            diag.import_review(pilot,self._packet(pilot,"A"),annotator_id="A")
            with self.assertRaisesRegex(diag.DiagnosticError,"primary identity"):
                diag.import_review(pilot,self._packet(pilot,"A",scope="independent-15"),annotator_id="A")

    def test_old_schema_is_rejected_without_inferred_judgments(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);path=self._packet(pilot,"A");lines=path.read_text().splitlines();lines[0]=lines[0].replace("audit_evidence_kind","evidence_level");path.write_text("\n".join(lines))
            with self.assertRaisesRegex(diag.DiagnosticError,"diagnostic-review-v4"):diag.import_review(pilot,path,annotator_id="A")

    def test_locked_revision3_snapshot_is_not_resampled_or_mutated(self):
        source=diag.OUTPUT_ROOT/"pilot-review-v3"
        if not source.exists():self.skipTest("local historical snapshot absent")
        before={str(p.relative_to(source)):p.read_bytes() for p in source.rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory() as temp:
            tmp=Path(temp);dest=tmp/"all_res"/"diagnostic_v1"/"revised"
            with patch.object(diag,"ROOT",tmp):selection=diag.revise_pilot_review(source,dest)
            oldrows=diag._read_jsonl(source/"pilot.jsonl")[0];newrows=diag._read_pilot(dest)[0];exclude={"protocol_sha256","rubric_version","packet_sha256"}
            self.assertEqual([{k:v for k,v in r.items() if k not in exclude} for r in oldrows],[{k:v for k,v in r.items() if k not in exclude} for r in newrows])
            self.assertEqual(selection["second_review_keys"],diag._read_json(source/"selection.json")["second_review_keys"])
        self.assertEqual(before,{str(p.relative_to(source)):p.read_bytes() for p in source.rglob("*") if p.is_file()})

    def test_adjudication_is_append_only_and_does_not_change_gold(self):
        with tempfile.TemporaryDirectory() as temp:
            pilot=self._pilot(temp);rows=diag._read_pilot(pilot)[0];before=(pilot/"pilot.jsonl").read_bytes()
            for decision in ("deferred","resolved"):diag.add_adjudication(pilot,observation_key=rows[0]["observation_key"],reviewer_id="fixture-expert",decision=decision,rationale="Fixture only.")
            self.assertEqual([r["decision"] for r in diag._read_records_jsonl(pilot/"adjudications.jsonl")],["deferred","resolved"])
            self.assertEqual(before,(pilot/"pilot.jsonl").read_bytes())


if __name__ == "__main__":
    unittest.main()
