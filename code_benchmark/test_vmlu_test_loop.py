"""Offline tests of the VMLU test loop (card MC-109): the manifest, the round-by-round rule and its equivalence with
MC-105's replay, the passes through the real engine with a fake request, the gate and the execution gates.
No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_vmlu_test_loop
"""
from __future__ import annotations

import contextlib
import csv
import dataclasses
import io
import json
import random
import tempfile
import threading
import time
import unittest
from collections import Counter
from pathlib import Path
from typing import Any
from unittest import mock

import httpx2
import openai

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_vmlu_test_loop as vt
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_vmlu_test_loop as rvt
from code_benchmark import vi_multimodel as v1
from code_benchmark import vi_multimodel_expansion as v2
from code_benchmark.test_run_self_loop import FakeClient, logprob

CONFIG, CONFIG_SHA = vt.load_config()
THRESHOLD = CONFIG["loop"]["threshold"]


def b_row(item_id: str, letter: str, confidence: float | None) -> dict:
    return {"item_id": item_id, "replicate_id": "B-r1", "status": "complete", "raw_response": letter,
            "confidence": confidence}


def s_row(item_id: str, replicate: str, letter: str) -> dict:
    return {"item_id": item_id, "replicate_id": replicate, "status": "complete",
            "raw_response": f"Bước 1: đọc đề.\nĐáp án: {letter}" if letter else "Không chắc."}


def synthetic_items(n: int) -> list[v2.ExpandedItem]:
    prompt = v1.build_prompt("Câu hỏi?", ["A. một", "B. hai", "C. ba", "D. bốn"])
    return [v2.ExpandedItem(dataset_id=vt.DATASET, item_id=f"01-{i:04d}", replicate_id="main-000",
                            task="multiple_choice", stratum=(1, "x", "y"), source_split="vmlu_mqa_v1.5/test.jsonl",
                            question=f"Câu hỏi {i}?", prompt=prompt.replace("Câu hỏi?", f"Câu hỏi {i}?"),
                            gold_status="withheld", choices=("A. một", "B. hai", "C. ba", "D. bốn"))
            for i in range(n)]


class TestManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.rebuilt = vt.build_manifest("qwen")

    def test_four_possible_attempts_for_each_of_the_9833_test_items(self):
        self.assertEqual((self.manifest["item_count"], self.manifest["n"]), (9833, 39332))
        self.assertEqual(self.manifest["arm_counts"], {"B": 9833, "S": 29499})
        self.assertEqual(len(vt.verify_rows(self.manifest, self.rebuilt)), 39332)

    def test_b_is_the_frozen_v2_prompt_and_s_the_campaign_template(self):
        frozen = {row["item_id"]: row for row in v2.load_manifest("vmlu")["items"] if row["dataset_id"] == vt.DATASET}
        rows = {dp.run_key(row): row for row in self.manifest["items"]}
        templates = dp.load_templates()
        for item_id in list(frozen)[:200]:
            self.assertEqual(rows[f"{vt.DATASET}:{item_id}:B-r1"]["prompt_sha256"], frozen[item_id]["prompt_sha256"])
            s = self.rebuilt[f"{vt.DATASET}:{item_id}:S-r2"]
            self.assertTrue(s.prompt.startswith(templates["s_mc_head"]))
            self.assertEqual(s.prompt, self.rebuilt[f"{vt.DATASET}:{item_id}:S-r1"].prompt)

    def test_the_configuration_fails_closed(self):
        with self.assertRaises(SystemExit):
            vt.validate_config({**CONFIG, "loop": {**CONFIG["loop"], "threshold": 0.7}})
        with self.assertRaises(SystemExit):
            vt.validate_config({**CONFIG, "arms": {"qwen": ["B-r1", "S-r1"]}})
        with self.assertRaises(SystemExit):
            vt.validate_config({**CONFIG, "schedule": {**CONFIG["schedule"], "max_passes": 2}})


class TestRule(unittest.TestCase):
    def test_round_one_keeps_a_confident_probe_and_asks_nothing_more(self):
        state = vt.item_state("1", {"B-r1": b_row("1", "A", 0.9)}, THRESHOLD)
        self.assertEqual((state.needed, state.final, state.rounds, state.answer), ((), "B-r1", 1, "A"))

    def test_an_unsure_or_unreadable_probe_asks_s_r1(self):
        for confidence in (0.79, None):
            state = vt.item_state("1", {"B-r1": b_row("1", "A", confidence)}, THRESHOLD)
            self.assertEqual((state.needed, state.final), (("S-r1",), None))

    def test_agreement_stops_at_round_two_and_disagreement_asks_two_more(self):
        rows = {"B-r1": b_row("1", "A", 0.5), "S-r1": s_row("1", "S-r1", "A")}
        self.assertEqual(vt.item_state("1", rows, THRESHOLD).rounds, 2)
        rows["S-r1"] = s_row("1", "S-r1", "B")
        self.assertEqual(vt.item_state("1", rows, THRESHOLD).needed, ("S-r2", "S-r3"))
        rows.update({"S-r2": s_row("1", "S-r2", "C"), "S-r3": s_row("1", "S-r3", "C")})
        state = vt.item_state("1", rows, THRESHOLD)
        self.assertEqual((state.final, state.rounds, state.answer), ("S-r2", 3, "C"))

    def test_an_empty_probe_never_agrees(self):
        rows = {"B-r1": b_row("1", "", None), "S-r1": s_row("1", "S-r1", "")}
        self.assertEqual(vt.item_state("1", rows, THRESHOLD).needed, ("S-r2", "S-r3"))

    def test_failed_rows_do_not_count(self):
        rows = {"1:B-r1": {**b_row("1", "A", 0.9), "status": "request_error"}}
        self.assertEqual(vt.plan(["1"], rows, THRESHOLD)[0].needed, ("B-r1",))

    def test_round_by_round_equals_mc105_replay_on_the_same_attempts(self):
        rng = random.Random(7)
        letters = ["A", "B", "C", "D", ""]
        for case in range(3000):
            draw = {r: rng.choice(letters) for r in vt.REPLICATES}
            confidence = rng.choice([None, round(rng.random(), 3), 0.8, 0.79999])
            full = {"B-r1": b_row("x", draw["B-r1"], confidence),
                    **{r: s_row("x", r, draw[r]) for r in vt.REPLICATES[1:]}}
            # ask only what the rule asks for, one round at a time
            asked: dict[str, dict] = {}
            state = vt.item_state("x", asked, THRESHOLD)
            while state.needed:
                asked.update({r: full[r] for r in state.needed})
                state = vt.item_state("x", asked, THRESHOLD)
            expected = vt.final_of(draw, confidence, THRESHOLD)
            self.assertEqual((state.final, state.rounds), expected, f"case {case}: {draw} {confidence}")
            self.assertEqual(state.answer, draw[expected[0]])
            self.assertEqual(vt.item_state("x", full, THRESHOLD).final, expected[0])
            self.assertEqual(len(asked), {1: 1, 2: 2, 3: 4}[expected[1]])


class EngineState(unittest.TestCase):
    def setUp(self):
        self.saved = (rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL, rvt.base.request)
        rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL = "Qwen3.5-9B-65K", "qwen", vt.PROTOCOL_ID
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "out"

    def tearDown(self):
        rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL, rvt.base.request = self.saved
        self.tmp.cleanup()


class TestPasses(EngineState):
    """The real engine (12 lanes) with a fake request: three rounds, a technical failure re-sent, no overlap."""

    def setup_run(self, n: int):
        items = vt.expand(synthetic_items(n))
        manifest: dict[str, Any] = {"items": [v2._item_manifest(item) for item in items]}  # noqa: SLF001
        manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
        rebuilt = {item.run_key: item for item in items}
        ids = [item.item_id for item in items if item.replicate_id == "B-r1"]
        return manifest, rebuilt, ids

    def fake_request(self, *, fail_once: frozenset[str] = frozenset(), fatal: frozenset[str] = frozenset()):
        sent: Counter[str] = Counter()
        lock = threading.Lock()
        in_flight = {"now": 0, "max": 0}

        def request(client, item, shard, lane):
            with lock:
                sent[item.run_key] += 1
                first = sent[item.run_key] == 1
                in_flight["now"] += 1
                in_flight["max"] = max(in_flight["max"], in_flight["now"])
            time.sleep(0.002)
            index = int(item.item_id.split("-")[1])
            row = rvt._base_row(item, "MC-109", shard, lane, "fake")  # noqa: SLF001
            if item.run_key in fatal:
                row.update({"status": "request_error", "finish_reason": "error", "error_type": "AuthenticationError",
                            "fatal": True})
            elif item.run_key in fail_once and first:
                row.update({"status": "request_error", "finish_reason": "error", "error_type": "APITimeoutError",
                            "fatal": False})
            elif item.replicate_id == "B-r1":
                row.update({"status": "complete", "raw_response": "A", "confidence": 0.9 if index % 3 == 0 else 0.5,
                            "total_tokens": 10})
            else:
                letter = {"S-r1": "A" if index % 3 == 1 else "B", "S-r2": "B", "S-r3": "C"}[item.replicate_id]
                row.update({"status": "complete", "raw_response": f"Lời giải.\nĐáp án: {letter}", "total_tokens": 100})
            row.update({"latency_s": 0.002, "finished_at": rvt.base.now()})
            with lock:
                in_flight["now"] -= 1
            return row
        return request, sent, in_flight

    def launch(self, manifest, rebuilt, ids, request, *, max_passes=6):
        rvt.base.request = request
        callback = rvt.loop_callback("qwen", "MC-109", ids, THRESHOLD)
        with contextlib.redirect_stdout(io.StringIO()):
            return rvt.run_passes(self.output, manifest, rebuilt, ids, {"runner_sha256": "test"}, None, False,
                                  max_passes=max_passes, threshold=THRESHOLD, score_callback=callback,
                                  runner_path=Path(rvt.__file__))

    def test_three_rounds_each_attempt_sent_once_and_a_failure_resent_in_the_next_pass(self):
        manifest, rebuilt, ids = self.setup_run(30)
        flaky = f"{vt.DATASET}:01-0001:S-r1"
        request, sent, _ = self.fake_request(fail_once=frozenset({flaky}))
        self.assertEqual(self.launch(manifest, rebuilt, ids, request), "complete")
        self.assertEqual(sent[flaky], 2)
        self.assertEqual({key: count for key, count in sent.items() if key != flaky}, dict.fromkeys(
            [k for k in sent if k != flaky], 1))
        by_replicate = Counter(key.rsplit(":", 1)[1] for key in sent)
        self.assertEqual(by_replicate, {"B-r1": 30, "S-r1": 20, "S-r2": 10, "S-r3": 10})
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["rounds"], {"1": 10, "2": 10, "3": 10})
        self.assertEqual(summary["final_differs_from_before"], 10)
        with (self.output / "submission_loop.csv").open() as handle:
            loop = {row["id"]: row["answer"] for row in csv.DictReader(handle)}
        with (self.output / "submission_before.csv").open() as handle:
            before = {row["id"]: row["answer"] for row in csv.DictReader(handle)}
        self.assertEqual(len(loop), 30)
        self.assertEqual(set(before.values()), {"A"})
        self.assertEqual(Counter(loop.values()), {"A": 20, "B": 10})  # round 3: S-r1 B, S-r2 B, S-r3 C

    def test_lanes_never_overlap_on_one_attempt_even_with_work_stealing(self):
        manifest, rebuilt, ids = self.setup_run(240)
        request, sent, in_flight = self.fake_request()
        self.assertEqual(self.launch(manifest, rebuilt, ids, request), "complete")
        self.assertEqual(set(sent.values()), {1})
        ledger = [json.loads(line) for line in (self.output / "attempts.jsonl").read_text().splitlines()]
        self.assertEqual(len(ledger), len({row["run_key"] for row in ledger}))
        self.assertLessEqual(in_flight["max"], rvt.base.SHARDS * rvt.base.LANES)

    def test_a_pass_never_resends_a_completed_attempt(self):
        manifest, rebuilt, ids = self.setup_run(6)
        request, _, _ = self.fake_request()
        self.launch(manifest, rebuilt, ids, request)
        states = vt.plan(ids, rvt.base.load_rows(self.output, manifest), THRESHOLD)
        self.assertTrue(all(s.final for s in states))
        with mock.patch.object(vt, "plan", return_value=[dataclasses.replace(states[0], needed=("B-r1",))]):
            with self.assertRaisesRegex(SystemExit, "send one attempt twice or re-send a completed one"):
                self.launch(manifest, rebuilt, ids, request)

    def test_a_fatal_row_stops_the_passes(self):
        manifest, rebuilt, ids = self.setup_run(9)
        request, sent, _ = self.fake_request(fatal=frozenset({f"{vt.DATASET}:01-0004:B-r1"}))
        self.assertEqual(self.launch(manifest, rebuilt, ids, request), "paused")
        self.assertFalse(any(key.endswith(("S-r1", "S-r2", "S-r3")) for key in sent))
        self.assertFalse((self.output / "submission_loop.csv").exists())

    def test_a_second_launch_on_the_same_output_is_refused(self):
        manifest, rebuilt, ids = self.setup_run(3)
        self.output.mkdir(parents=True)
        import fcntl
        with (self.output / ".run.lock").open("a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            request, sent, _ = self.fake_request()
            with self.assertRaises(SystemExit):
                self.launch(manifest, rebuilt, ids, request)
        self.assertEqual(sum(sent.values()), 0)


class TestGate(EngineState):
    def test_the_probe_keeps_this_cards_phase_and_the_mc43_condition(self):
        request = rvt.make_probe(CONFIG["students"]["qwen"]["probe"], {"Qwen3.5-9B-65K"}, "MC-109",
                                 pr.BudgetGuard(1000), pr.OutageGuard(4), threading.Event())
        item = vt.expand(synthetic_items(1))[0]
        client = FakeClient(("B", "Qwen3.5-9B-65K", [logprob("B", 0.7), logprob("A", 0.3)]))
        row = request(client, item, 0, 0)
        self.assertEqual((row["status"], row["phase"], row["measurement_card_id"]), ("complete", vt.PHASE, "MC-109"))
        self.assertAlmostEqual(row["confidence"], 0.7, places=5)
        self.assertEqual((client.kwargs["temperature"], client.kwargs["seed"], client.kwargs["max_tokens"]), (0.0, 42, 4))

    def test_at_most_max_in_flight_requests_and_a_fatal_row_halts_the_rest(self):
        lock, state = threading.Lock(), {"now": 0, "max": 0}
        fatal_key = f"{vt.DATASET}:01-0005:S-r1"

        def campaign_factory(protocol, phase, card_id, guard, **kwargs):
            self.assertEqual((phase, kwargs["max_in_flight"]), (vt.PHASE, None))

            def request(client, item, shard, lane):
                with lock:
                    state["now"] += 1
                    state["max"] = max(state["max"], state["now"])
                time.sleep(0.01)
                with lock:
                    state["now"] -= 1
                return {"run_key": item.run_key, "status": "request_error", "fatal": item.run_key == fatal_key}
            return request

        with mock.patch.object(rvt.pr, "make_request", campaign_factory):
            request = rvt.make_qwen_request(CONFIG["students"]["qwen"],
                                            {"model": {"self_reported_id": "x", "requested_id": "Qwen3.5-9B-65K"}},
                                            "MC-109", pr.BudgetGuard(10_000), pr.OutageGuard(0))
        items = [i for i in vt.expand(synthetic_items(40)) if i.replicate_id == "S-r1"]
        rows: list[dict] = []
        threads = [threading.Thread(target=lambda it=it: rows.append(request(None, it, 0, 0))) for it in items[:5]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        threads = [threading.Thread(target=lambda it=it: rows.append(request(None, it, 0, 0))) for it in items[5:]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertLessEqual(state["max"], CONFIG["students"]["qwen"]["max_in_flight"])
        self.assertEqual(CONFIG["students"]["qwen"]["max_in_flight"], 6)
        halted = [row for row in rows if row.get("error_type") == "halted_before_send"]
        self.assertGreater(len(halted), 0)


class TestGates(unittest.TestCase):
    def test_gates(self):
        manifest = {"config_sha256": "c", "manifest_sha256": "m"}
        registration = {"card_ids": {vt.PHASE: "MC-109"}, "card_files": {vt.PHASE: "missing.md"},
                        "frozen": {"config_sha256": "c", "manifest_sha256": {"qwen": "m"}}}
        gates = {g.name: g.ok for g in rvt.evaluate_gates("qwen", manifest, registration, True, "ok",
                                                          card_text="## MC-109 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": True,
                                 "route_identity": True})
        other = {g.name: g.ok for g in rvt.evaluate_gates("qwen", {**manifest, "manifest_sha256": "x"}, registration,
                                                          False, "no", card_text="## MC-108 — other\n")}
        self.assertEqual(other, {"card_registered": False, "detail_card": False, "frozen_hashes": False,
                                 "route_identity": False})


# ---------------------------------------------------------------- MiMo (MC-110)

MIMO_CONFIG, _ = vt.load_config(vt.CONFIG_PATHS["mimo"])
MIMO = vt.REPLICATES_BY_STUDENT["mimo"]


def mb_row(item_id: str, replicate: str, letter: str) -> dict:
    """A MiMo B reply, read by the frozen parser like the probe's."""
    return {"item_id": item_id, "replicate_id": replicate, "status": "complete", "raw_response": letter}


class TestMimoManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.rebuilt = vt.build_manifest("mimo")

    def test_five_possible_attempts_per_item_with_both_b_on_the_frozen_prompt(self):
        self.assertEqual((self.manifest["item_count"], self.manifest["n"]), (9833, 49165))
        self.assertEqual(self.manifest["arm_counts"], {"B": 19666, "S": 29499})
        frozen = {row["item_id"]: row for row in v2.load_manifest("vmlu")["items"] if row["dataset_id"] == vt.DATASET}
        rows = {dp.run_key(row): row for row in self.manifest["items"]}
        for item_id in list(frozen)[:200]:
            for replicate in ("B-r1", "B-r2"):
                self.assertEqual(rows[f"{vt.DATASET}:{item_id}:{replicate}"]["prompt_sha256"],
                                 frozen[item_id]["prompt_sha256"])
        # MiMo's S prompts are byte for byte Qwen's in MC-109.
        qwen, _ = vt.build_manifest("qwen")
        s_prompts = {dp.run_key(row): row["prompt_sha256"] for row in qwen["items"] if row["replicate_id"] != "B-r1"}
        self.assertEqual(len(s_prompts), 29499)
        self.assertTrue(all(rows[key]["prompt_sha256"] == digest for key, digest in s_prompts.items()))

    def test_the_configuration_keeps_mc105s_request_and_fails_closed(self):
        student = MIMO_CONFIG["students"]["mimo"]
        self.assertEqual((student["max_in_flight"], student["budget_tokens"]), (6, 20_000_000))
        for key, value in (("max_completion_tokens", 4096), ("model_id", "other"), ("system_prompt", ""),
                           ("timeout_seconds", 600)):
            with self.assertRaises(SystemExit):
                vt.validate_config({**MIMO_CONFIG, "students": {"mimo": {**student, key: value}}})
        with self.assertRaises(SystemExit):
            vt.validate_config({**MIMO_CONFIG, "arms": {"mimo": ["B-r1", "S-r1", "S-r2", "S-r3"]}})
        with self.assertRaises(SystemExit):
            vt.build_manifest("qwen", vt.CONFIG_PATHS["mimo"])


class TestMimoRule(unittest.TestCase):
    def test_two_b_answers_first_then_s_then_the_vote(self):
        self.assertEqual(vt.item_state("1", {}, None, "mimo").needed, ("B-r1", "B-r2"))
        rows = {"B-r1": mb_row("1", "B-r1", "A")}
        self.assertEqual(vt.item_state("1", rows, None, "mimo").needed, ("B-r2",))
        rows["B-r2"] = mb_row("1", "B-r2", "A")
        state = vt.item_state("1", rows, None, "mimo")
        self.assertEqual((state.needed, state.final, state.rounds, state.answer), ((), "B-r1", 1, "A"))
        rows["B-r2"] = mb_row("1", "B-r2", "B")
        self.assertEqual(vt.item_state("1", rows, None, "mimo").needed, ("S-r1",))
        rows["S-r1"] = s_row("1", "S-r1", "B")  # agrees with B-r2: S-r1 is final
        state = vt.item_state("1", rows, None, "mimo")
        self.assertEqual((state.final, state.rounds, state.answer), ("S-r1", 2, "B"))
        rows["S-r1"] = s_row("1", "S-r1", "C")
        self.assertEqual(vt.item_state("1", rows, None, "mimo").needed, ("S-r2", "S-r3"))
        rows.update({"S-r2": s_row("1", "S-r2", "D"), "S-r3": s_row("1", "S-r3", "D")})
        state = vt.item_state("1", rows, None, "mimo")
        self.assertEqual((state.final, state.rounds, state.answer, state.confidence), ("S-r2", 3, "D", None))

    def test_empty_b_answers_never_agree(self):
        rows = {"B-r1": mb_row("1", "B-r1", ""), "B-r2": mb_row("1", "B-r2", "")}
        self.assertEqual(vt.item_state("1", rows, None, "mimo").needed, ("S-r1",))

    def test_round_by_round_equals_mc105_replay_on_the_same_attempts(self):
        rng = random.Random(11)
        letters = ["A", "B", "C", "D", ""]
        for case in range(3000):
            draw = {r: rng.choice(letters) for r in MIMO}
            full = {**{r: mb_row("x", r, draw[r]) for r in ("B-r1", "B-r2")},
                    **{r: s_row("x", r, draw[r]) for r in ("S-r1", "S-r2", "S-r3")}}
            asked: dict[str, dict] = {}
            state = vt.item_state("x", asked, None, "mimo")
            while state.needed:
                asked.update({r: full[r] for r in state.needed})
                state = vt.item_state("x", asked, None, "mimo")
            expected = vt.final_of(draw, None, None, "mimo")
            self.assertEqual((state.final, state.rounds), expected, f"case {case}: {draw}")
            self.assertEqual(state.answer, draw[expected[0]])
            self.assertEqual(len(asked), {1: 2, 2: 3, 3: 5}[expected[1]])


class TestMimoPasses(EngineState):
    """The real engine with a fake MiMo request: B twice for every item, then S where the rule needs it."""

    def test_three_rounds_and_each_attempt_sent_once(self):
        items = vt.expand(synthetic_items(30), MIMO)
        manifest: dict[str, Any] = {"items": [v2._item_manifest(item) for item in items]}  # noqa: SLF001
        manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
        rebuilt = {item.run_key: item for item in items}
        ids = [item.item_id for item in items if item.replicate_id == "B-r1"]
        sent: Counter[str] = Counter()
        lock = threading.Lock()

        def request(client, item, shard, lane):
            with lock:
                sent[item.run_key] += 1
            index = int(item.item_id.split("-")[1])
            row = rvt._base_row(item, "MC-110", shard, lane, "fake")  # noqa: SLF001
            letter = {"B-r1": "A", "B-r2": "A" if index % 3 == 0 else "B", "S-r1": "B" if index % 3 == 1 else "C",
                      "S-r2": "C", "S-r3": "D"}[item.replicate_id]
            raw = letter if item.replicate_id.startswith("B") else f"Lời giải.\nĐáp án: {letter}"
            row.update({"status": "complete", "raw_response": raw, "total_tokens": 10, "latency_s": 0.001,
                        "finished_at": rvt.base.now()})
            return row

        rvt.base.request = request
        with contextlib.redirect_stdout(io.StringIO()):
            status = rvt.run_passes(self.output, manifest, rebuilt, ids, {"runner_sha256": "test"}, None, False,
                                    max_passes=6, threshold=None, student="mimo",
                                    score_callback=rvt.loop_callback("mimo", "MC-110", ids, None),
                                    runner_path=Path(rvt.__file__))
        self.assertEqual(status, "complete")
        self.assertEqual(set(sent.values()), {1})
        self.assertEqual(Counter(key.rsplit(":", 1)[1] for key in sent),
                         {"B-r1": 30, "B-r2": 30, "S-r1": 20, "S-r2": 10, "S-r3": 10})
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual((summary["rounds"], summary["final_differs_from_before"], summary["confidence_missing"]),
                         ({"1": 10, "2": 10, "3": 10}, 20, None))
        with (self.output / "submission_loop.csv").open() as handle:
            loop = Counter(row["answer"] for row in csv.DictReader(handle))
        with (self.output / "submission_before.csv").open() as handle:
            before = Counter(row["answer"] for row in csv.DictReader(handle))
        self.assertEqual((loop, before), ({"A": 10, "B": 10, "C": 10}, {"A": 30}))


class TestMimoRequest(EngineState):
    def request(self, model: str = "mimo-v2.6-flash"):
        student = MIMO_CONFIG["students"]["mimo"]
        rvt.base.MODEL = student["model_id"]
        request = rvt.make_mimo_request(student, "MC-110", pr.BudgetGuard(10_000), pr.OutageGuard(4),
                                        rvt.ModelPin(student["model_identity"]))
        item = vt.expand(synthetic_items(1), MIMO)[1]
        client = FakeClient(("Đáp án: B", model, None))
        return request(client, item, 0, 0), client, item

    def test_mc105s_request_with_this_cards_rows_and_session(self):
        row, client, item = self.request()
        self.assertEqual((row["status"], row["phase"], row["measurement_card_id"], row["replicate_id"]),
                         ("complete", vt.PHASE, "MC-110", "B-r2"))
        sent = client.kwargs
        assert sent is not None
        self.assertEqual(sent["max_completion_tokens"], 20000)
        self.assertEqual(sent["messages"][0], {"role": "system", "content": "Answer the user's question."})
        self.assertNotIn("temperature", sent)
        self.assertEqual(sent["extra_headers"], {"x-opencode-session": rvt.session_id("MC-110", item.run_key)})
        self.assertTrue(rvt.session_id("MC-110", item.run_key).startswith("vmlu-mc110-"))

    def test_another_model_is_fatal(self):
        row, _, _ = self.request(model="another-model")
        self.assertEqual((row["status"], row["fatal"]), ("request_error", True))


def http_400(code: str | None = None, message: str = "upstream text that must not be kept") -> openai.BadRequestError:
    request = httpx2.Request("POST", "https://opencode.ai/zen/go/v1/chat/completions")
    return openai.BadRequestError(message, response=httpx2.Response(400, request=request),
                                  body={"code": code, "message": message} if code else None)


AMENDMENT = rvt.transient_400_amendment(rvt.load_registration(vt.REGISTRATION_PATHS["mimo"]))


class FlakyClient(FakeClient):
    """Answers B, except that the attempt with session `fail_session` raises `error` on its first `fails` sends."""

    def __init__(self, fail_session: str, error: Exception, fails: int = 1):
        super().__init__(("Đáp án: B", "mimo-v2.6-flash", None))
        self.fail_session, self.error, self.fails, self.failed = fail_session, error, fails, 0
        self.lock = threading.Lock()

    def create(self, **kwargs):
        with self.lock:
            if kwargs["extra_headers"]["x-opencode-session"] == self.fail_session and self.failed < self.fails:
                self.failed += 1
                raise self.error
        return super().create(**kwargs)


class TestMimoBadRequest(EngineState):
    """MC-110 amendment 1: an HTTP 400 is a technical failure unless it names a refusal, repeats on one attempt or
    passes the cap; without the amendment it halts, as registered."""

    def request(self, error: Exception, rule: rvt.BadRequestRule | None):
        student = MIMO_CONFIG["students"]["mimo"]
        rvt.base.MODEL = student["model_id"]
        request = rvt.make_mimo_request(student, "MC-110", pr.BudgetGuard(10_000), pr.OutageGuard(4),
                                        rvt.ModelPin(student["model_identity"]), rule)
        item = vt.expand(synthetic_items(1), MIMO)[1]
        return request(FakeClient(error), item, 0, 0), item

    def test_the_registered_amendment(self):
        assert AMENDMENT is not None
        self.assertEqual((AMENDMENT["id"], AMENDMENT["max_attempts_with_400"]), (1, 10))
        self.assertIsNone(rvt.transient_400_amendment({"amendments": []}))
        for broken in ({**AMENDMENT, "refusal_words": []}, {**AMENDMENT, "max_attempts_with_400": 0},
                       {k: v for k, v in AMENDMENT.items() if k != "text"}):
            with self.assertRaises(SystemExit):
                rvt.transient_400_amendment({"amendments": [broken]})
        with self.assertRaises(SystemExit):
            rvt.transient_400_amendment({"amendments": [AMENDMENT, AMENDMENT]})

    def test_without_the_amendment_any_400_halts(self):
        row, _ = self.request(http_400(), None)
        self.assertEqual((row["status"], row["fatal"], row["fatal_reason"]),
                         ("request_error", True, "registered halt: HTTP 400"))

    def test_a_first_400_is_a_technical_failure_and_its_message_is_never_kept(self):
        row, _ = self.request(http_400(), rvt.BadRequestRule(AMENDMENT))
        self.assertEqual((row["fatal"], row["technical_400"], row["retry_wait_seconds"], row["error_code"]),
                         (False, "amendment 1", rvt.TRANSIENT_400_WAIT_SECONDS, None))
        self.assertNotIn("upstream text", json.dumps(row, ensure_ascii=False))

    def test_a_second_400_on_one_attempt_halts(self):
        item = vt.expand(synthetic_items(1), MIMO)[1]
        row, _ = self.request(http_400(), rvt.BadRequestRule(AMENDMENT, {item.run_key}))
        self.assertEqual((row["fatal"], row["fatal_reason"]), (True, "amendment 1: a second HTTP 400 on this attempt"))

    def test_a_refusal_code_halts_and_is_recorded(self):
        row, _ = self.request(http_400("content_policy_violation"), rvt.BadRequestRule(AMENDMENT))
        self.assertEqual((row["fatal"], row["error_code"]), (True, "content_policy_violation"))
        self.assertIn("names a refusal", row["fatal_reason"])

    def test_the_cap_counts_the_ledgers_attempts(self):
        row, _ = self.request(http_400(), rvt.BadRequestRule(AMENDMENT, {f"x:{i}" for i in range(9)}))
        self.assertFalse(row["fatal"])
        row, _ = self.request(http_400(), rvt.BadRequestRule(AMENDMENT, {f"x:{i}" for i in range(10)}))
        self.assertEqual((row["fatal"], row["fatal_reason"]), (True, "amendment 1: more than 10 attempts had an HTTP 400"))

    def test_attempts_with_400_reads_every_ledger_row(self):
        self.output.mkdir(parents=True)
        rows = [{"run_key": "a", "http_status": 400}, {"run_key": "a", "status": "complete"},
                {"run_key": "b", "http_status": "400"}, {"run_key": "c", "http_status": 500}]
        (self.output / "attempts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(rvt.attempts_with_400(self.output), {"a", "b"})
        self.assertEqual(rvt.attempts_with_400(self.output / "none"), set())

    def test_the_engine_resends_a_technical_400_in_the_next_pass(self):
        items = vt.expand(synthetic_items(30), MIMO)
        manifest: dict[str, Any] = {"items": [v2._item_manifest(item) for item in items]}  # noqa: SLF001
        manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
        rebuilt = {item.run_key: item for item in items}
        ids = [item.item_id for item in items if item.replicate_id == "B-r1"]
        flaky = items[1].run_key
        student = MIMO_CONFIG["students"]["mimo"]
        rvt.base.MODEL = student["model_id"]

        def launch(fails: int) -> tuple[str, FlakyClient]:
            client = FlakyClient(rvt.session_id("MC-110", flaky), http_400(), fails)
            rvt.base.request = rvt.make_mimo_request(
                student, "MC-110", pr.BudgetGuard(10_000_000), pr.OutageGuard(4), rvt.ModelPin(student["model_identity"]),
                rvt.BadRequestRule(AMENDMENT, rvt.attempts_with_400(self.output)))
            with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(rvt, "TRANSIENT_400_WAIT_SECONDS", 0):
                status = rvt.run_passes(self.output, manifest, rebuilt, ids, {"runner_sha256": "test"}, client, False,
                                        max_passes=6, threshold=None, student="mimo",
                                        score_callback=rvt.loop_callback("mimo", "MC-110", ids, None),
                                        runner_path=Path(rvt.__file__))
            return status, client

        status, client = launch(fails=1)
        self.assertEqual((status, client.calls), ("complete", 60))  # 61 sends: the 400 is raised before `calls` counts
        ledger = [json.loads(line) for line in (self.output / "attempts.jsonl").read_text().splitlines()]
        self.assertEqual([(r["status"], r.get("technical_400")) for r in ledger if r["run_key"] == flaky],
                         [("request_error", "amendment 1"), ("complete", None)])
        self.assertTrue((self.output / "submission_loop.csv").is_file())

    def test_the_engine_halts_when_the_same_attempt_gets_a_second_400(self):
        items = vt.expand(synthetic_items(30), MIMO)
        manifest: dict[str, Any] = {"items": [v2._item_manifest(item) for item in items]}  # noqa: SLF001
        manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
        rebuilt = {item.run_key: item for item in items}
        ids = [item.item_id for item in items if item.replicate_id == "B-r1"]
        flaky = items[1].run_key
        student = MIMO_CONFIG["students"]["mimo"]
        rvt.base.MODEL = student["model_id"]
        rvt.base.request = rvt.make_mimo_request(
            student, "MC-110", pr.BudgetGuard(10_000_000), pr.OutageGuard(4), rvt.ModelPin(student["model_identity"]),
            rvt.BadRequestRule(AMENDMENT))
        client = FlakyClient(rvt.session_id("MC-110", flaky), http_400(), fails=2)
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(rvt, "TRANSIENT_400_WAIT_SECONDS", 0):
            status = rvt.run_passes(self.output, manifest, rebuilt, ids, {"runner_sha256": "test"}, client, False,
                                    max_passes=6, threshold=None, student="mimo",
                                    score_callback=rvt.loop_callback("mimo", "MC-110", ids, None),
                                    runner_path=Path(rvt.__file__))
        self.assertEqual(status, "paused")
        ledger = [json.loads(line) for line in (self.output / "attempts.jsonl").read_text().splitlines()]
        self.assertEqual([(r.get("technical_400"), r.get("fatal")) for r in ledger if r["run_key"] == flaky],
                         [("amendment 1", False), (None, True)])


if __name__ == "__main__":
    unittest.main()
