"""Offline tests for the prospective diagnostic campaign contract and runner.

Run from the repo root: .venv/bin/python -m unittest code_benchmark.test_diagnostic_prospective
No test contacts an endpoint. Tests that need the frozen main-v1 sources or the locked pilot
packet skip themselves when those gitignored artifacts are absent.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_diagnostic_prospective as runner
from code_benchmark import vi_multimodel as v1
from code_benchmark.run_mc_eval import extract_answer
from code_benchmark.score_vi_multimodel import score_rows


def _main_available() -> bool:
    try:
        v1.load_manifest("main")
    except SystemExit:
        return False
    return True


MAIN_OK = _main_available()
PILOT_OK = (dp.ROOT / "all_res/diagnostic_v1/pilot-review-v4/pilot.jsonl").is_file()
DATA_OK = MAIN_OK and PILOT_OK
TEMPLATES = dp.load_templates()
PROTOCOL = dp.load_protocol()
MC_DATASET = "vi-multimodel-v1-legal-mc-146"
RD_DATASET = "vi-multimodel-v1-vi-squad-200"
MC_BODY = "Câu hỏi thử?\n\nA. một\nB. hai\nC. ba\nD. bốn"
MC_PROMPT = dp.MC_HEAD + MC_BODY + dp.MC_TAIL
RD_PASSAGE = "Đoạn văn thử. Thư viện khánh thành năm 1998."
RD_PROMPT = dp.RD_HEAD + RD_PASSAGE + dp.RD_QUESTION + "Năm nào?" + dp.RD_TAIL
EXPECTED_MODEL = PROTOCOL["model"]["self_reported_id"]
USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def make_item(task: str = "multiple_choice", item_id: str = "T1", gold: str | None = None,
              prompt: str | None = None) -> v1.EvalItem:
    is_mc = task == "multiple_choice"
    return v1.EvalItem(
        dataset_id=MC_DATASET if is_mc else RD_DATASET, source_dataset="test", item_id=item_id,
        replicate_id=dp.MAIN_REPLICATE, task=task, stratum="s", question="q", passage_id="p1",
        prompt=prompt or (MC_PROMPT if is_mc else RD_PROMPT), gold_answer=gold or ("C" if is_mc else "1998"))


def synthetic_manifest(entries):
    """entries: (item, arm, replicate number) -> (manifest, rebuilt, items) for the arm-aware contract."""
    items = [dataclasses.replace(item, replicate_id=f"{arm}-r{k}", prompt=dp.build_arm_prompt(item, arm, TEMPLATES))
             for item, arm, k in entries]
    manifest = {"protocol_id": dp.PROTOCOL_ID, "n": len(items), "item_count": len(items),
                "dataset_counts": {}, "arm_counts": {}, "items": [v1.manifest_item(i) for i in items]}
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    return manifest, {i.run_key: i for i in items}, items


def prediction(item, raw: str, status: str = "complete") -> dict:
    return {"dataset_id": item.dataset_id, "item_id": item.item_id, "replicate_id": item.replicate_id,
            "status": status, "finish_reason": "stop", "prompt_sha256": v1.sha256_bytes(item.prompt.encode()),
            "raw_response": raw, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "latency_s": 1.0}


class Stream:
    def __init__(self, events):
        self.events = events

    def __iter__(self):
        yield from self.events

    def close(self):
        pass


def completed(text: str, model: str = EXPECTED_MODEL, usage=USAGE):
    response = {"status": "completed", "model": model, "id": "resp_1",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
    if usage is not None:
        response["usage"] = usage
    return N(model_dump=lambda: {"type": "response.completed", "response": response})


class FakeClient:
    def __init__(self, text_for=lambda _prompt: "C", model: str = EXPECTED_MODEL, usage=USAGE):
        self.calls: list[dict] = []
        self.text_for, self.model, self.usage = text_for, model, usage
        self.responses = N(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["input"][1]["content"]
        return Stream([completed(self.text_for(prompt), self.model, self.usage)])


class APITimeoutError(Exception):
    """Same class name the OpenAI SDK raises: the runner keys on type(exc).__name__."""


class TimeoutClient:
    def __init__(self):
        self.calls = 0
        self.responses = N(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        raise APITimeoutError()


def reply_for(prompt: str) -> str:
    stepwise = "Dòng cuối cùng" in prompt
    if dp.RD_QUESTION in prompt or "Năm nào" in prompt:
        return "Đối chiếu đoạn văn.\nTrả lời: 1998" if stepwise else "1998"
    return "Xét đáp án A: sai. Xét đáp án B: sai.\nĐáp án: C" if stepwise else "C"


@contextlib.contextmanager
def engine_configured(phase: str = "wide", card: str = "MC-901", cap: int = 10 ** 9, **options):
    guard = runner.BudgetGuard(cap)
    with contextlib.ExitStack() as stack:
        for field in ("MODEL", "PROFILE", "PROTOCOL", "CARD_ID", "request"):
            stack.enter_context(patch.object(runner.base, field, getattr(runner.base, field)))
        runner.configure_engine(PROTOCOL, phase, card, guard, **options)
        yield guard


class TestContractFiles(unittest.TestCase):
    def test_protocol_and_templates_load(self):
        self.assertEqual(PROTOCOL["transport"]["max_output_tokens"], 4096)
        self.assertEqual(set(TEMPLATES), set(dp.TEMPLATE_KEYS))

    def test_unknown_arm_or_phase_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mutate, label in ((lambda p: p["arms"].pop("KS"), "arm"), (lambda p: p["phases"].pop("wide"), "phase"),
                                  (lambda p: p["phases"]["core"].update(replicates=0), "replicates")):
                broken = copy.deepcopy(PROTOCOL)
                mutate(broken)
                path = Path(tmp) / f"{label}.json"
                path.write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaises(SystemExit, msg=label):
                    dp.load_protocol(path)

    def test_template_without_placeholder_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = {**TEMPLATES, "evidence_item": "no placeholders here"}
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(SystemExit):
                dp.load_templates(path)

    def test_replicate_id_must_carry_a_known_arm(self):
        self.assertEqual(dp.arm_of_replicate("KS-r12"), "KS")
        for bad in ("main-000", "X-r1", "S-r", "S-1"):
            with self.assertRaises(SystemExit, msg=bad):
                dp.arm_of_replicate(bad)


class TestPromptBuilders(unittest.TestCase):
    def test_baseline_arm_is_the_frozen_prompt(self):
        self.assertEqual(dp.build_arm_prompt(make_item(), "B", TEMPLATES), MC_PROMPT)
        self.assertEqual(dp.build_arm_prompt(make_item("reading"), "B", TEMPLATES), RD_PROMPT)

    def test_stepwise_mc_keeps_the_input_and_drops_the_completion_cue(self):
        prompt = dp.build_arm_prompt(make_item(), "S", TEMPLATES)
        self.assertTrue(prompt.startswith(TEMPLATES["s_mc_head"]))
        self.assertTrue(prompt.endswith(MC_BODY))
        self.assertNotIn(dp.MC_HEAD, prompt)
        self.assertFalse(prompt.endswith(dp.MC_TAIL))

    def test_stepwise_reading_keeps_passage_and_question_once(self):
        prompt = dp.build_arm_prompt(make_item("reading"), "S", TEMPLATES)
        self.assertEqual(prompt.count(RD_PASSAGE), 1)
        self.assertEqual(prompt.count("Năm nào?"), 1)
        self.assertTrue(prompt.endswith("Năm nào?\n"))
        self.assertFalse(prompt.endswith(dp.RD_TAIL))

    def test_evidence_arms_need_evidence_and_the_others_forbid_it(self):
        provisions = [{"doc_title": "Nghị định thử", "locator": "Điều 1", "text": "Nội dung điều khoản."}]
        with self.assertRaises(SystemExit):
            dp.build_arm_prompt(make_item(), "O", TEMPLATES)
        with self.assertRaises(SystemExit):
            dp.build_arm_prompt(make_item(), "B", TEMPLATES, provisions)
        block = dp.render_evidence_block(provisions, TEMPLATES)
        self.assertEqual(dp.build_arm_prompt(make_item(), "O", TEMPLATES, provisions), block + MC_PROMPT)
        self.assertEqual(dp.build_arm_prompt(make_item(), "KS", TEMPLATES, provisions),
                         block + dp.build_arm_prompt(make_item(), "S", TEMPLATES))
        self.assertTrue(block.startswith(TEMPLATES["evidence_header"]))

    def test_unexpected_skeleton_fails_closed_with_the_item_key(self):
        for task in ("multiple_choice", "reading"):
            item = make_item(task, prompt="một prompt lạ")
            with self.assertRaises(SystemExit) as caught:
                dp.build_arm_prompt(item, "S", TEMPLATES)
            self.assertIn(item.run_key, str(caught.exception))

    @unittest.skipUnless(MAIN_OK, "frozen main-v1 sources not available")
    def test_every_frozen_prompt_parses_and_baseline_is_byte_identical(self):
        items = [i for i in v1.rebuild_items("main").values() if i.dataset_id in PROTOCOL["datasets"]]
        self.assertEqual(len(items), 1299)
        for item in items:
            dp.parse_frozen_prompt(item)
            self.assertEqual(dp.build_arm_prompt(item, "B", TEMPLATES), item.prompt)


class TestEvidenceContract(unittest.TestCase):
    def setUp(self):
        self.main_items = {make_item().run_key: make_item()}
        self.text = "Điều 6. Mức phạt tiền được quy định như sau."
        self.record = {
            "dataset_id": MC_DATASET, "item_id": "T1", "reviewer_id": "reviewer-a",
            "review_export_sha256": "a" * 64, "eligibility": {"input_evidence_sufficiency": "insufficient"},
            "provisions": [{"doc_id": "168/2024/NĐ-CP", "doc_title": "Nghị định 168/2024/NĐ-CP",
                            "locator": "Điều 6", "text": self.text,
                            "text_sha256": v1.sha256_bytes(self.text.encode("utf-8")), "source_ref": "test"}],
        }

    def load(self, *records):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oracle.jsonl"
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
            return dp.load_oracle_evidence(path, PROTOCOL, self.main_items)

    def test_valid_record_is_accepted(self):
        loaded = self.load(self.record)
        self.assertEqual(list(loaded), [f"{MC_DATASET}:T1"])

    def test_answer_bearing_keys_text_and_hash_drift_are_rejected(self):
        leaky_key = {**self.record, "gold": "C"}
        leaky_text = copy.deepcopy(self.record)
        leaky_text["provisions"][0]["text"] = "Đáp án: C"
        leaky_text["provisions"][0]["text_sha256"] = v1.sha256_bytes("Đáp án: C".encode("utf-8"))
        drifted = copy.deepcopy(self.record)
        drifted["provisions"][0]["text"] += " (sửa)"
        for record, reason in ((leaky_key, "forbidden"), (leaky_text, "answer or an explanation"),
                               (drifted, "hash mismatch")):
            with self.assertRaises(SystemExit) as caught:
                self.load(record)
            self.assertIn(reason, str(caught.exception))

    def test_ineligible_dataset_unknown_item_and_duplicates_are_rejected(self):
        reading = {**self.record, "dataset_id": RD_DATASET}
        unknown = {**self.record, "item_id": "NOPE"}
        sufficient = {**self.record, "eligibility": {"input_evidence_sufficiency": "sufficient"}}
        for record in (reading, unknown, sufficient):
            with self.assertRaises(SystemExit):
                self.load(record)
        with self.assertRaises(SystemExit):
            self.load(self.record, self.record)


class TestArmScoring(unittest.TestCase):
    def setUp(self):
        self.mc, self.rd = make_item("multiple_choice", "T1", gold="C"), make_item("reading", "T2", gold="1998")

    def score(self, entries_and_raw):
        manifest, rebuilt, items = synthetic_manifest([(item, arm, 1) for item, arm, _ in entries_and_raw])
        predictions = {i.run_key: prediction(i, raw) for i, (_, _, raw) in zip(items, entries_and_raw, strict=True)}
        return dp.score_arm_rows(manifest, predictions, rebuilt), manifest, rebuilt, predictions

    def test_baseline_arm_equals_the_frozen_scorer(self):
        (scored, _), manifest, rebuilt, predictions = self.score([(self.mc, "B", "C"), (self.rd, "B", "1998")])
        frozen, _ = score_rows(manifest, predictions, rebuilt)
        key = lambda rows: [(r["item_id"], r["prediction"], r.get("correct"), r.get("em")) for r in rows]  # noqa: E731
        self.assertEqual(key(scored), key(frozen))
        self.assertTrue(all(r["format_ok"] is None and r["scoring_source"] == "raw" for r in scored))

    def test_reasoning_that_mentions_other_options_is_read_from_the_final_line(self):
        raw = "Xét đáp án A: sai vì thiếu căn cứ.\nXét đáp án B: sai.\nVậy câu đúng là C.\nĐáp án: C"
        self.assertEqual(extract_answer(raw), "A")  # the frozen first-match parser would misread this response
        (scored, _), *_ = self.score([(self.mc, "S", raw)])
        self.assertEqual((scored[0]["prediction"], scored[0]["correct"], scored[0]["format_ok"]), ("C", 1, True))
        self.assertEqual(scored[0]["raw_response"], raw)
        self.assertEqual(scored[0]["scoring_response"], "C")

    def test_missing_label_is_unparsed_and_kept_in_the_denominator(self):
        (scored, summaries), *_ = self.score([(self.mc, "S", "Suy luận dài nên tôi chọn C vì hợp lý.")])
        self.assertEqual((scored[0]["prediction"], scored[0]["correct"], scored[0]["format_ok"]), ("", 0, False))
        summary = summaries["S"][MC_DATASET]
        self.assertEqual((summary["completed_n"], summary["unparsed_n"], summary["format_compliance_pct"]), (1, 1, 0.0))

    def test_bold_final_letter_and_trailing_text_after_the_label_line(self):
        (scored, _), *_ = self.score([(self.mc, "S", "Lập luận.\nĐáp án: **C**\n\nGhi chú thêm.")])
        self.assertEqual((scored[0]["prediction"], scored[0]["correct"]), ("C", 1))

    def test_reading_uses_the_frozen_last_label_and_flags_markdown(self):
        (clean, _), *_ = self.score([(self.rd, "S", "Đối chiếu.\nTrả lời: 1998")])
        self.assertEqual((clean[0]["em"], clean[0]["format_ok"], clean[0]["markdown_final_line"]), (1, True, False))
        (marked, summaries), *_ = self.score([(self.rd, "S", "Đối chiếu.\nTrả lời: **1998**")])
        self.assertEqual((marked[0]["em"], marked[0]["markdown_final_line"]), (0, True))
        self.assertEqual(summaries["S"][RD_DATASET]["markdown_final_line_n"], 1)

    def test_arms_are_never_pooled(self):
        (scored, summaries), *_ = self.score([(self.mc, "B", "C"), (self.mc, "S", "x\nĐáp án: A")])
        self.assertEqual(set(summaries), {"B", "S"})
        self.assertEqual(summaries["B"][MC_DATASET]["correct"], 1)
        self.assertEqual(summaries["S"][MC_DATASET]["correct"], 0)
        self.assertEqual({r["arm"] for r in scored}, {"B", "S"})

    def test_final_segment_never_falls_back_to_the_whole_response(self):
        self.assertEqual(dp.final_segment("không có nhãn"), ("", False))
        self.assertEqual(dp.final_segment("Đáp án:"), ("", True))
        self.assertEqual(dp.final_segment("Đáp án: A\nĐáp án: B\nthêm"), ("B", True))


@unittest.skipUnless(DATA_OK, "frozen main-v1 sources or the locked pilot packet are not available")
class TestManifests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, cls.core_items = dp.build_manifest("core")
        cls.wide, cls.wide_items = dp.build_manifest("wide")

    @staticmethod
    def keys(manifest):
        return {f"{r['dataset_id']}:{r['item_id']}" for r in manifest["items"]}

    def test_core_and_wide_partition_the_mc72_scope(self):
        self.assertFalse(self.keys(self.core) & self.keys(self.wide))
        self.assertEqual(len(self.keys(self.core) | self.keys(self.wide)), 1299)
        self.assertEqual((self.core["item_count"], self.wide["item_count"]), (60, 1239))

    def test_attempt_counts_follow_the_protocol(self):
        self.assertEqual(self.core["arm_counts"], {"B": 180, "S": 180})
        self.assertEqual(self.wide["arm_counts"], {"B": 1239, "S": 1239})
        self.assertEqual({k.split("-v1-")[1]: v for k, v in self.wide["dataset_counts"].items()},
                         {"legal-mc-146": 268, "legal-nli-150": 276, "vi-squad-200": 376,
                          "vi-drop-200": 376, "bidlqa-test": 1182})

    def test_rows_are_item_major_with_unique_run_keys(self):
        first = self.core["items"][:6]
        self.assertEqual({(r["dataset_id"], r["item_id"]) for r in first}, {(first[0]["dataset_id"], first[0]["item_id"])})
        self.assertEqual([r["replicate_id"] for r in first], ["B-r1", "S-r1", "B-r2", "S-r2", "B-r3", "S-r3"])
        keys = [dp.run_key(r) for r in self.core["items"] + self.wide["items"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_baseline_rows_carry_the_frozen_prompt_hash_and_rows_verify(self):
        main_rows = {(r["dataset_id"], r["item_id"]): r for r in v1.load_manifest("main")["items"]}
        for manifest, rebuilt in ((self.core, self.core_items), (self.wide, self.wide_items)):
            dp.verify_manifest_rows(manifest, rebuilt)
            for row in manifest["items"]:
                if row["replicate_id"].startswith("B-"):
                    self.assertEqual(row["prompt_sha256"], main_rows[(row["dataset_id"], row["item_id"])]["prompt_sha256"])

    def test_tampered_row_is_detected(self):
        tampered = copy.deepcopy(self.core)
        tampered["items"][1]["prompt_sha256"] = "0" * 64
        tampered["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(
            {k: v for k, v in tampered.items() if k != "manifest_sha256"}))
        with self.assertRaises(SystemExit):
            dp.verify_manifest_rows(tampered, self.core_items)

    def test_oracle_evidence_adds_arms_only_for_covered_anchors(self):
        anchor = next(r for r in self.core["items"] if r["dataset_id"] == MC_DATASET)
        text = "Điều 6. Quy định thử."
        provisions = [{"doc_id": "d", "doc_title": "Văn bản thử", "locator": "Điều 6", "text": text,
                       "text_sha256": v1.sha256_bytes(text.encode()), "source_ref": "test"}]
        manifest, rebuilt = dp.build_manifest("core", evidence_by_arm={"O": {f"{MC_DATASET}:{anchor['item_id']}": provisions}})
        self.assertEqual(manifest["arm_counts"], {"B": 180, "O": 3, "S": 180})
        oracle = next(i for i in rebuilt.values() if i.replicate_id == "O-r1")
        self.assertTrue(oracle.prompt.startswith(TEMPLATES["evidence_header"]))
        self.assertTrue(oracle.prompt.endswith(dp.MC_TAIL))
        self.assertIn("O", manifest["evidence_sha256"])

    def test_evidence_outside_the_phase_is_rejected(self):
        anchor = next(r for r in self.core["items"] if r["dataset_id"] == MC_DATASET)
        with self.assertRaises(SystemExit):
            dp.build_manifest("wide", evidence_by_arm={"O": {f"{MC_DATASET}:{anchor['item_id']}": [{}]}})


class TestRunner(unittest.TestCase):
    def manifest_stub(self):
        return {"campaign_protocol_sha256": "p" * 64, "prompt_templates_sha256": "t" * 64,
                "manifest_sha256": "m" * 64, "evidence_sha256": {}}

    def registration(self, phase="wide", card_file="measurement_card.md"):
        return {"card_ids": {phase: "MC-901"}, "card_files": {phase: card_file},
                "frozen": {"protocol_sha256": "p" * 64, "prompt_templates_sha256": "t" * 64,
                           "manifest_sha256": {phase: "m" * 64}, "evidence_sha256": {phase: {}}}}

    ENV = {"OPENAI_BASE_URL": "http://llmapi.iec/v1", "OPENAI_MODEL": "Qwen3.5-9B-65K", "OPENAI_API_KEY": "k"}

    def gates(self, phase="wide", **overrides):
        args = dict(card_text="## MC-901 — test\n", readiness=lambda: {"inference_ready": True})
        args.update(overrides)
        manifest = overrides.pop("manifest", None) or self.manifest_stub()
        registration = args.pop("registration", None) or self.registration(phase)
        env = args.pop("env", None) or self.ENV
        args.pop("manifest", None)
        return {g.name: g for g in runner.evaluate_gates(phase, PROTOCOL, manifest, registration, env, **args)}

    def test_all_gates_pass_when_registered(self):
        self.assertTrue(all(g.ok for g in self.gates("wide").values()))
        self.assertTrue(all(g.ok for g in self.gates("core").values()))

    def test_unregistered_card_blocks_execution(self):
        gates = self.gates("wide", card_text="## MC-1 — other\n")
        self.assertFalse(gates["card_registered"].ok)
        self.assertFalse(self.gates("wide", registration={**self.registration(), "card_ids": {"wide": None}})["card_registered"].ok)

    def test_core_waits_for_inference_ready_but_wide_does_not(self):
        pending = lambda: {"inference_ready": False, "inference_blockers": ["unresolved control: verified_endpoint"]}  # noqa: E731
        core = self.gates("core", readiness=pending)
        self.assertFalse(core["inference_ready"].ok)
        self.assertIn("verified_endpoint", core["inference_ready"].detail)
        self.assertNotIn("inference_ready", self.gates("wide", readiness=pending))

    def test_hash_drift_and_wrong_endpoint_block_execution(self):
        drifted = {**self.manifest_stub(), "prompt_templates_sha256": "x" * 64}
        gates = self.gates("wide", manifest=drifted)
        self.assertFalse(gates["frozen_hashes"].ok)
        self.assertIn("prompt_templates", gates["frozen_hashes"].detail)
        self.assertFalse(self.gates("wide", env={**self.ENV, "OPENAI_BASE_URL": "http://other.host/v1"})["endpoint_identity"].ok)
        self.assertFalse(self.gates("wide", env={**self.ENV, "OPENAI_MODEL": "other"})["endpoint_identity"].ok)

    def test_request_shape_row_fields_and_unknown_usage(self):
        item = dataclasses.replace(make_item(), replicate_id="S-r1")
        client = FakeClient(usage=None)
        with engine_configured():
            row = runner.base.request(client, item, 0, 0)
        kwargs = client.calls[0]
        self.assertEqual(set(kwargs), {"model", "input", "temperature", "max_output_tokens", "stream"})
        self.assertEqual((kwargs["model"], kwargs["max_output_tokens"], kwargs["temperature"], kwargs["stream"]),
                         ("Qwen3.5-9B-65K", 4096, 1.0, True))
        self.assertEqual(kwargs["input"][0], {"role": "system", "content": "Answer the user's question."})
        self.assertEqual((row["status"], row["arm"], row["phase"], row["measurement_card_id"]), ("complete", "S", "wide", "MC-901"))
        self.assertIsNone(row["total_tokens"])
        self.assertIsNone(row["reasoning_tokens"])

    def test_model_identity_drift_is_fatal(self):
        with engine_configured():
            row = runner.base.request(FakeClient(model="some/other-model.gguf"), dataclasses.replace(make_item(), replicate_id="B-r1"), 0, 0)
        self.assertEqual((row["status"], row["error_type"], row["fatal"]), ("request_error", "model_identity_drift", True))

    def test_budget_guard_stops_without_calling_the_client(self):
        client = FakeClient()
        with engine_configured(cap=10) as guard:
            guard.add(None)
            self.assertEqual(guard.used, 0)
            guard.add(10)
            row = runner.base.request(client, dataclasses.replace(make_item(), replicate_id="B-r1"), 0, 0)
        self.assertEqual((row["error_type"], row["fatal"], client.calls), ("budget_cap", True, []))

    def test_resume_requires_an_identical_inference_condition(self):
        condition = {"max_tokens": 4096, "runner_sha256": "a", "measurement_card_hash": "c", "wrapper_sha256": "w"}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.assertEqual(runner.reconcile_resume(output, condition, False), condition)
            (output / "condition.json").write_text(json.dumps(condition), encoding="utf-8")
            with self.assertRaises(SystemExit):
                runner.reconcile_resume(output, condition, False)
            with self.assertRaises(SystemExit):
                runner.reconcile_resume(output, {**condition, "max_tokens": 2048}, True)
            moved = {**condition, "runner_sha256": "b"}
            self.assertEqual(runner.reconcile_resume(output, moved, True), condition)

    def test_outage_breaker_counts_only_consecutive_network_failures(self):
        breaker = runner.OutageGuard(3)
        timeout = {"status": "request_error", "error_type": "APITimeoutError"}
        breaker.record(timeout)
        breaker.record(timeout)
        self.assertFalse(breaker.tripped())
        breaker.record({"status": "complete"})  # any success resets the count
        breaker.record(timeout)
        breaker.record({"status": "request_error", "error_type": "model_identity_drift"})  # not a network failure
        breaker.record({"status": "request_error", "error_type": "ReadTimeout"})
        self.assertFalse(breaker.tripped())
        breaker.record(timeout)
        self.assertTrue(breaker.tripped())
        self.assertFalse(runner.OutageGuard(0).tripped())  # disabled unless asked for

    def test_tripped_breaker_makes_the_next_request_fatal_without_sending_it(self):
        client = TimeoutClient()
        items = [dataclasses.replace(make_item(item_id=f"T{i}"), replicate_id="B-r1") for i in range(4)]
        with engine_configured(outage=runner.OutageGuard(2)):
            rows = [runner.base.request(client, item, 0, 0) for item in items]
        self.assertEqual([r["error_type"] for r in rows],
                         ["APITimeoutError", "APITimeoutError", "endpoint_unresponsive", "endpoint_unresponsive"])
        self.assertEqual([bool(r.get("fatal")) for r in rows], [False, False, True, True])
        self.assertEqual(client.calls, 2)

    def test_the_registered_path_has_no_breaker_and_no_cap(self):
        client = TimeoutClient()
        items = [dataclasses.replace(make_item(item_id=f"T{i}"), replicate_id="B-r1") for i in range(5)]
        with engine_configured():
            rows = [runner.base.request(client, item, 0, 0) for item in items]
        self.assertEqual({r["error_type"] for r in rows}, {"APITimeoutError"})
        self.assertFalse(any(r.get("fatal") for r in rows))
        self.assertEqual(client.calls, 5)  # without the options the run never stops on its own

    def test_in_flight_cap_bounds_simultaneous_requests(self):
        lock, state = threading.Lock(), {"now": 0, "peak": 0}

        class SlowClient(FakeClient):
            def _create(self, **kwargs):
                with lock:
                    state["now"] += 1
                    state["peak"] = max(state["peak"], state["now"])
                time.sleep(0.1)
                with lock:
                    state["now"] -= 1
                return super()._create(**kwargs)

        items = [dataclasses.replace(make_item(item_id=f"T{i}"), replicate_id="B-r1") for i in range(12)]

        def peak_with(**options):
            state.update(now=0, peak=0)
            client = SlowClient()
            with engine_configured(**options), ThreadPoolExecutor(12) as pool:
                rows = list(pool.map(lambda item: runner.base.request(client, item, 0, 0), items))
            self.assertEqual({r["status"] for r in rows}, {"complete"})
            return state["peak"]

        self.assertGreater(peak_with(), 3)  # the instrument does see concurrency when nothing limits it
        self.assertLessEqual(peak_with(max_in_flight=3), 3)

    def test_a_fatal_row_stops_lanes_queued_at_the_cap(self):
        client = FakeClient(model="some/other-model.gguf")
        items = [dataclasses.replace(make_item(item_id=f"T{i}"), replicate_id="B-r1") for i in range(3)]
        with engine_configured(max_in_flight=1):
            rows = [runner.base.request(client, item, 0, 0) for item in items]
        self.assertEqual([r["error_type"] for r in rows], ["model_identity_drift", "halted_before_send", "halted_before_send"])
        self.assertEqual(len(client.calls), 1)

    def test_cli_rejects_non_positive_operational_options(self):
        for flag in ("--max-in-flight", "--stop-after-timeouts"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                runner.main(["--phase", "wide", flag, "0"])
            self.assertEqual(caught.exception.code, 2)

    def test_launches_are_recorded_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            runner.record_launch(output, "wide", resume=False, max_in_flight=None, stop_after_timeouts=None, note="", lanes=12)
            runner.record_launch(output, "wide", resume=True, max_in_flight=4, stop_after_timeouts=4,
                                 note="cap after two endpoint stalls", lanes=12)
            events = [json.loads(line) for line in (output / "operator_events.jsonl").read_text().splitlines()]
        self.assertEqual([e["resume"] for e in events], [False, True])
        self.assertEqual((events[0]["max_in_flight"], events[1]["max_in_flight"]), (None, 4))
        self.assertEqual((events[1]["lanes_configured"], events[1]["note"]), (12, "cap after two endpoint stalls"))
        self.assertEqual(events[1]["runner_sha256"], v1.sha256_file(Path(runner.__file__)))

    def test_execute_end_to_end_with_a_fake_transport(self):
        entries = [(make_item("multiple_choice", "T1"), arm, 1) for arm in ("B", "S")] + \
                  [(make_item("reading", "T2"), arm, 1) for arm in ("B", "S")]
        manifest, rebuilt, items = synthetic_manifest(entries)
        condition = {"runner_sha256": "r", "model_id": "Qwen3.5-9B-65K"}
        with tempfile.TemporaryDirectory() as tmp, engine_configured() as guard, contextlib.redirect_stdout(io.StringIO()):
            output = Path(tmp) / "run"
            output.mkdir()
            callback = runner.make_score_callback("wide", "MC-901")
            runner.base.execute(output, manifest, rebuilt, items, condition, FakeClient(reply_for), False,
                                score_callback=callback, runner_path=Path(runner.__file__))
            predictions = [json.loads(line) for line in (output / "predictions.jsonl").read_text().splitlines()]
            scores = [json.loads(line) for line in (output / "scores.jsonl").read_text().splitlines()]
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(len(predictions), 4)
            self.assertTrue(all(p["status"] == "complete" for p in predictions))
            self.assertEqual({s["arm"] for s in scores}, {"B", "S"})
            self.assertTrue(all(s.get("correct", s.get("em")) == 1 for s in scores))
            self.assertEqual(set(summary["arms"]), {"B", "S"})
            self.assertEqual(runner.existing_usage(output), 60)
            self.assertEqual(guard.used, 60)
            idle = FakeClient(reply_for)
            with self.assertRaises(SystemExit):
                runner.base.execute(output, manifest, rebuilt, items, condition, idle, False, runner_path=Path(runner.__file__))
            runner.base.execute(output, manifest, rebuilt, items, condition, idle, True,
                                score_callback=callback, runner_path=Path(runner.__file__))
            self.assertEqual(idle.calls, [])  # completed attempts are never retried

    @unittest.skipUnless(DATA_OK, "frozen main-v1 sources or the locked pilot packet are not available")
    def test_preflight_sends_nothing_and_execute_fails_closed_when_unregistered(self):
        unregistered = {**dp.load_registration(), "card_ids": {"core": None, "wide": None},
                        "card_files": {"core": None, "wide": None}}  # independent of the committed registration
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(runner.base, "execute") as execute, \
                patch.object(runner.dp, "load_registration", return_value=unregistered):
            self.assertEqual(runner.main(["--phase", "wide"]), 0)
            self.assertIn("endpoint_calls=0", out.getvalue())
            self.assertIn("attempts=2478", out.getvalue())
            with self.assertRaises(SystemExit) as caught:
                runner.main(["--phase", "wide", "--execute"])
        self.assertIn("card_registered", str(caught.exception))
        execute.assert_not_called()

    @unittest.skipUnless(DATA_OK, "frozen main-v1 sources or the locked pilot packet are not available")
    def test_committed_wide_registration_matches_its_frozen_artifacts(self):
        """Editing protocol.json, the templates or the manifest after registration must fail here, not at the endpoint."""
        protocol, registration = dp.load_protocol(), dp.load_registration()
        manifest, rebuilt = dp.build_manifest("wide")
        gates = {g.name: g for g in runner.evaluate_gates("wide", protocol, manifest, registration, self.ENV)}
        self.assertEqual({name: g.detail for name, g in gates.items() if not g.ok}, {})
        saved = json.loads((dp.DATA_DIR / "wide_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, manifest)  # the archived frozen file is the manifest the runner rebuilds
        self.assertEqual(len(dp.verify_manifest_rows(saved, rebuilt)), 2478)
        self.assertEqual((manifest["item_count"], manifest["arm_counts"]), (1239, {"B": 1239, "S": 1239}))


SUPPLEMENT_DESIGN = {"base_phase": "wide", "arms": ["B"], "first_replicate": 2, "replicates": 1}


class TestSupplements(unittest.TestCase):
    """A supplement re-runs registered arms under further replicate numbers, with its own card and manifest."""

    def registered(self, **operational):
        """The committed registration plus a supplement whose card is the existing MC-90 one (no MC-91 needed)."""
        manifest, _ = dp.build_manifest("wide", supplement={**SUPPLEMENT_DESIGN, "supplement_id": "wide-b-r2"})
        entry = {**SUPPLEMENT_DESIGN, "card_id": "MC-90", "card_file": "docs/measurement_cards/MC-90-diagnostic-prospective-wide.md",
                 "frozen": {"manifest_sha256": manifest["manifest_sha256"]}, "operational": operational}
        return {**dp.load_registration(), "supplements": {"wide-b-r2": entry}}

    def test_design_is_validated_against_the_registered_phase(self):
        self.assertEqual(dp.validate_supplement("s", dict(SUPPLEMENT_DESIGN), PROTOCOL)["arms"], ["B"])
        for why, change in (("unknown base phase", {"base_phase": "nowhere"}), ("no arm", {"arms": []}),
                            ("arm outside the phase", {"arms": ["O"]}), ("collides with the registered replicate", {"first_replicate": 1}),
                            ("empty", {"replicates": 0}), ("wrong type", {"first_replicate": "2"}),
                            ("evidence arm", {"base_phase": "core", "arms": ["O"], "first_replicate": 4})):
            with self.subTest(why), self.assertRaises(SystemExit):
                dp.validate_supplement("s", {**SUPPLEMENT_DESIGN, **change}, PROTOCOL)
        with self.assertRaises(SystemExit):
            dp.validate_supplement("s", {key: value for key, value in SUPPLEMENT_DESIGN.items() if key != "arms"}, PROTOCOL)

    def test_only_registered_supplements_load(self):
        registration = {"supplements": {"s": dict(SUPPLEMENT_DESIGN)}}
        self.assertEqual(dp.load_supplement(registration, "s", PROTOCOL)["supplement_id"], "s")
        for missing in ({"supplements": {}}, {}):
            with self.assertRaises(SystemExit):
                dp.load_supplement(missing, "s", PROTOCOL)

    @unittest.skipUnless(DATA_OK, "frozen main-v1 sources or the locked pilot packet are not available")
    def test_manifest_reuses_the_baseline_prompts_under_new_replicate_numbers(self):
        registered, _ = dp.build_manifest("wide")
        manifest, rebuilt = dp.build_manifest("wide", supplement={**SUPPLEMENT_DESIGN, "supplement_id": "wide-b-r2"})
        self.assertEqual((manifest["n"], manifest["item_count"], manifest["arm_counts"]), (1239, 1239, {"B": 1239}))
        self.assertEqual({row["replicate_id"] for row in manifest["items"]}, {"B-r2"})
        self.assertEqual((manifest["supplement_id"], manifest["supplement_design"]), ("wide-b-r2", SUPPLEMENT_DESIGN))
        baseline = {(r["dataset_id"], r["item_id"]): r for r in registered["items"] if r["replicate_id"] == "B-r1"}
        for row in manifest["items"]:  # same prompt, same gold, only the replicate label differs
            reference = baseline[(row["dataset_id"], row["item_id"])]
            self.assertEqual([row[k] for k in ("prompt_sha256", "input_sha256", "gold_sha256")],
                             [reference[k] for k in ("prompt_sha256", "input_sha256", "gold_sha256")])
        self.assertFalse({dp.run_key(r) for r in manifest["items"]} & {dp.run_key(r) for r in registered["items"]})
        self.assertNotEqual(manifest["manifest_sha256"], registered["manifest_sha256"])
        self.assertNotIn("supplement_id", registered)  # the registered MC-90 manifest never carries the new keys
        self.assertEqual(len(dp.verify_manifest_rows(manifest, rebuilt)), 1239)
        with self.assertRaises(SystemExit):
            dp.build_manifest("core", supplement={**SUPPLEMENT_DESIGN, "supplement_id": "wide-b-r2"})

    def test_gates_use_the_supplements_own_card_and_manifest_hash(self):
        registration = {"status": "x", "card_ids": {"wide": "MC-90"}, "card_files": {"wide": "a.md"},
                        "frozen": {"protocol_sha256": "p" * 64, "prompt_templates_sha256": "t" * 64,
                                   "manifest_sha256": {"wide": "w" * 64}}}
        supplement = {**SUPPLEMENT_DESIGN, "supplement_id": "s", "card_id": "MC-901", "card_file": "measurement_card.md",
                      "frozen": {"manifest_sha256": "m" * 64}}
        view = runner.supplement_registration_view(registration, supplement, "wide")
        self.assertEqual((view["card_ids"], view["frozen"]["manifest_sha256"]), ({"wide": "MC-901"}, {"wide": "m" * 64}))
        manifest = {"campaign_protocol_sha256": "p" * 64, "prompt_templates_sha256": "t" * 64,
                    "manifest_sha256": "m" * 64, "evidence_sha256": {}}
        gates = lambda m: {g.name: g for g in runner.evaluate_gates(  # noqa: E731
            "wide", PROTOCOL, m, view, TestRunner.ENV, card_text="## MC-901 — test\n")}
        self.assertTrue(all(g.ok for g in gates(manifest).values()))
        self.assertFalse(gates({**manifest, "manifest_sha256": "x" * 64})["frozen_hashes"].ok)

    def test_condition_freezes_the_design_and_the_registered_operational_limits(self):
        manifest = {"manifest_sha256": "m" * 64, "parent_manifest_sha256": "a" * 64, "campaign_protocol_sha256": "p" * 64,
                    "prompt_templates_sha256": "t" * 64, "evidence_sha256": {}, "pilot_content_sha256": "c" * 64,
                    "dataset_counts": {}, "arm_counts": {"B": 1}, "supplement_design": SUPPLEMENT_DESIGN}
        view = {"card_ids": {"wide": "MC-901"}, "card_files": {"wide": "measurement_card.md"}}
        supplement = {**SUPPLEMENT_DESIGN, "supplement_id": "s", "operational": {"max_in_flight": 4, "stop_after_timeouts": 4}}
        args = ("wide", PROTOCOL, manifest, view, "http://llmapi.iec/v1", "v1", Path(runner.__file__))
        plain = runner.build_condition(*args)
        condition = runner.build_condition(*args, supplement=supplement)
        self.assertEqual((condition["supplement_id"], condition["operational"]),
                         ("s", {"max_in_flight": 4, "stop_after_timeouts": 4}))
        self.assertNotIn("supplement_id", plain)  # the registered MC-90 condition is not touched
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "condition.json").write_text(json.dumps(condition), encoding="utf-8")
            self.assertEqual(runner.reconcile_resume(output, condition, True), condition)
            other = runner.build_condition(*args, supplement={**supplement, "operational": {"max_in_flight": 8}})
            with self.assertRaises(SystemExit):  # a resume cannot loosen the registered limits
                runner.reconcile_resume(output, other, True)

    @unittest.skipUnless(DATA_OK, "frozen main-v1 sources or the locked pilot packet are not available")
    def test_cli_runs_a_registered_supplement_and_refuses_inconsistent_requests(self):
        registration = self.registered(max_in_flight=4, stop_after_timeouts=4)
        out = io.StringIO()
        with patch.object(runner.dp, "load_registration", return_value=registration), \
                patch.object(runner.base, "execute") as execute:
            with contextlib.redirect_stdout(out):
                self.assertEqual(runner.main(["--phase", "wide", "--supplement", "wide-b-r2", "--max-in-flight", "4"]), 0)
            self.assertIn("supplement=wide-b-r2", out.getvalue())
            self.assertIn("attempts=1239", out.getvalue())
            self.assertIn("frozen_hashes=PASS", out.getvalue())
            self.assertIn("endpoint_calls=0", out.getvalue())
            for argv in (["--phase", "wide", "--supplement", "wide-b-r2", "--max-in-flight", "2"],   # not the registered 4
                         ["--phase", "core", "--supplement", "wide-b-r2"],                              # wrong phase
                         ["--phase", "wide", "--supplement", "wide-b-r2", "--oracle-evidence", "x.jsonl"]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    runner.main(argv)
                self.assertEqual(caught.exception.code, 2, argv)
            with self.assertRaises(SystemExit):
                runner.main(["--phase", "wide", "--supplement", "not-registered"])
        execute.assert_not_called()

    def test_launch_records_name_the_supplement(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner.record_launch(Path(tmp), "wide", resume=False, max_in_flight=4, stop_after_timeouts=4, note="",
                                 lanes=12, supplement_id="wide-b-r2")
            event = json.loads((Path(tmp) / "operator_events.jsonl").read_text().splitlines()[0])
        self.assertEqual(event["supplement_id"], "wide-b-r2")


if __name__ == "__main__":
    unittest.main()
