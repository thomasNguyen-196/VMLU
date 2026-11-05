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




if __name__ == "__main__":
    unittest.main()
