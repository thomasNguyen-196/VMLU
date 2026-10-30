"""Offline tests of the weakness-map calibration (openspec change diagnostic-router-loop, card MC-103).
No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_diagnostic_weakness_map
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from code_benchmark import analyze_weakness_map as awm
from code_benchmark import diagnostic_heldout_v3 as h3
from code_benchmark import diagnostic_menu as menu
from code_benchmark import diagnostic_weakness_map as wm
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_weakness_map as rwm
from code_benchmark import vi_multimodel as v1

CONFIG, _ = wm.load_config()
STUDENT = CONFIG["student"]
HAS_SOURCES = all(path.is_file() for path in h3.PINNED)


def mc(correct: int, prediction: str) -> dict:
    return {"correct": correct, "prediction": prediction}


def rd(f1: float, prediction: str) -> dict:
    return {"token_f1": f1, "em": float(f1 == 1.0), "prediction": prediction}


class TestMaps(unittest.TestCase):
    def test_point_map_keeps_b_inside_the_tie_margin(self):
        self.assertEqual(wm.point_map({"B": 60.0, "S": 60.9}, 1.0), "B")
        self.assertEqual(wm.point_map({"B": 60.0, "S": 61.0}, 1.0), "S")
        self.assertEqual(wm.point_map({"B": 60.0, "S": 65.0, "Q": 70.0}, 1.0), "Q")
        self.assertEqual(wm.point_map({"B": 70.0, "S": 65.0, "Q": 60.0}, 1.0), "B")

    def test_reliable_map_needs_an_interval_above_zero(self):
        wide = {"mean_points": 8.0, "ci95_points": [-1.0, 17.0]}
        narrow = {"mean_points": 3.0, "ci95_points": [0.5, 6.0]}
        self.assertEqual(wm.reliable_map({"S": wide}), "B")
        self.assertEqual(wm.reliable_map({"S": wide, "Q": narrow}), "Q")
        self.assertEqual(wm.reliable_map({"S": {"mean_points": 8.0, "ci95_points": [1.0, 15.0]}, "Q": narrow}), "S")


class TestModelBlock(unittest.TestCase):
    def test_rescue_damage_noise_and_rule_loop_on_multiple_choice(self):
        rows = [{"B1": mc(0, "A"), "B2": mc(1, "B"), "S1": mc(1, "B")},   # draws disagree -> S, rescued
                {"B1": mc(1, "C"), "B2": mc(1, "C"), "S1": mc(0, "D")},   # draws agree -> B, S damages
                {"B1": mc(0, "A"), "B2": mc(0, "A"), "S1": mc(0, "B")}]   # draws agree -> B, both wrong
        block = awm.model_block(rows, ("S1",), 0.5)
        self.assertEqual(block["task"], "multiple_choice")
        self.assertEqual(block["rescue_damage"]["S"], {"rescued": 1, "damaged": 1})
        self.assertEqual(block["noise"]["b1_b2_agree"], 2)
        self.assertEqual((block["means"]["B1"], block["rule_loop"]), (33.33, 66.67))
        self.assertEqual(awm.maps_of(block, 1.0)["point"], "B")

    def test_reading_counts_right_by_the_token_f1_threshold(self):
        rows = [{"B1": rd(0.4, "a"), "B2": rd(0.4, "a"), "S1": rd(0.6, "b"), "Q1": rd(0.3, "c")}]
        block = awm.model_block(rows, ("S1", "Q1"), 0.5)
        self.assertEqual(block["task"], "reading")
        self.assertEqual(block["rescue_damage"], {"S": {"rescued": 1, "damaged": 0}, "Q": {"rescued": 0, "damaged": 0}})
        self.assertEqual(awm.maps_of(block, 1.0)["point"], "S")


class TestModelPin(unittest.TestCase):
    def test_first_id_is_pinned_and_drift_is_fatal(self):
        pin = rwm.ModelPin("mimo")
        self.assertIsNone(pin.check(None))
        self.assertIsNone(pin.check("mimo-v2.6-flash"))
        self.assertIsNone(pin.check("mimo-v2.6-flash"))
        self.assertEqual(pin.check("mimo-v2.6-flash-0915"), "model_identity_drift")
        self.assertEqual(rwm.ModelPin("mimo").check("gpt-4o"), "unexpected_model")


class FakeError(Exception):
    def __init__(self, status_code):
        super().__init__("upstream text that must not be stored")
        self.status_code = status_code


class FakeClient:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        finish, model, tools = self.outcome
        message = SimpleNamespace(content="Trả lời: B", tool_calls=tools, reasoning_content="nghĩ")
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=3), prompt_tokens_details=None)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=message)], usage=usage,
                               model=model, id="req-1")


class TestRequest(unittest.TestCase):
    item = v1.EvalItem(dataset_id="vm14k-4-options", source_dataset="vm14k", item_id="7", replicate_id="S-r1",
                       task="multiple_choice", stratum="x", question="q", passage_id="x", prompt="p", gold_answer="B")

    def setUp(self):
        self.saved = (rwm.base.MODEL, rwm.base.PROFILE, rwm.base.PROTOCOL)
        rwm.base.MODEL, rwm.base.PROFILE, rwm.base.PROTOCOL = STUDENT["model_id"], STUDENT["profile_id"], wm.PROTOCOL_ID

    def tearDown(self):
        rwm.base.MODEL, rwm.base.PROFILE, rwm.base.PROTOCOL = self.saved

    def send(self, outcome, *, cap: int = 1000, pin: rwm.ModelPin | None = None):
        guard = pr.BudgetGuard(cap)
        client = FakeClient(outcome)
        request = rwm.make_request(STUDENT, "MC-103", guard, pr.OutageGuard(4), pin or rwm.ModelPin("mimo"))
        return request(client, self.item, 0, 0), client, guard

    def test_a_completed_reply_is_recorded_with_its_usage(self):
        row, client, guard = self.send(("stop", "mimo-v2.6-flash", None))
        self.assertEqual((row["status"], row["finish_reason"], row["raw_response"]), ("complete", "stop", "Trả lời: B"))
        self.assertEqual((row["reasoning_tokens"], row["reasoning_chars"], guard.used), (3, 4, 15))
        self.assertEqual(client.kwargs["max_completion_tokens"], STUDENT["max_completion_tokens"])
        self.assertNotIn("temperature", client.kwargs)
        self.assertEqual(client.kwargs["messages"][0], {"role": "system", "content": STUDENT["system_prompt"]})
        self.assertEqual(client.kwargs["extra_headers"], {rwm.SESSION_HEADER: rwm.session_id(self.item.run_key)})
        self.assertNotEqual(rwm.session_id("d:7:B-r1"), rwm.session_id("d:7:B-r2"))

    def test_truncated_tool_calls_errors_and_drift(self):
        self.assertEqual(self.send(("length", "mimo-v2.6-flash", None))[0]["status"], "complete")
        tool = self.send(("tool_calls", "mimo-v2.6-flash", [object()]))[0]
        self.assertEqual((tool["status"], tool["fatal"]), ("request_error", True))
        denied = self.send(FakeError(401))[0]
        self.assertEqual((denied["status"], denied["fatal"]), ("request_error", True))
        self.assertNotIn("upstream", str(denied))
        flaky = self.send(FakeError(None))[0]
        self.assertEqual((flaky["fatal"], flaky["retry_wait_seconds"]), (False, 5))
        pin = rwm.ModelPin("mimo")
        self.send(("stop", "mimo-v2.6-flash", None), pin=pin)
        drift = self.send(("stop", "mimo-v2.7", None), pin=pin)[0]
        self.assertEqual((drift["error_type"], drift["fatal"]), ("model_identity_drift", True))

    def test_an_exhausted_budget_sends_nothing(self):
        row, client, _ = self.send(("stop", "mimo-v2.6-flash", None), cap=0)
        self.assertEqual((row["error_type"], row["fatal"], client.calls), ("budget_cap", True, 0))


@unittest.skipUnless(HAS_SOURCES, "needs the pinned VM14K and ViBidLQA sources")
class TestManifest(unittest.TestCase):
    def test_prompts_match_mc95_and_q_comes_from_the_mc97_builder(self):
        manifest, rebuilt = wm.build_manifest()
        self.assertEqual((manifest["n"], manifest["item_count"], manifest["arm_counts"]),
                         (600, 180, {"B": 360, "Q": 60, "S": 180}))
        source = {f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}": row
                  for row in h3.load_frozen_manifest()["items"]}
        q_protocol = menu.load_protocol()
        for row in manifest["items"]:
            key = f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
            if row["replicate_id"] == "Q-r1":
                base_item = rebuilt[key.replace(":Q-r1", ":B-r1")]
                self.assertEqual(rebuilt[key].prompt, menu.q_prompt(base_item, q_protocol))
            else:
                self.assertEqual(row["prompt_sha256"], source[key]["prompt_sha256"])
        unhashed = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        self.assertEqual(manifest["manifest_sha256"], v1.sha256_bytes(v1.canonical_json(unhashed)))


class TestRunnerGates(unittest.TestCase):
    def test_gates(self):
        manifest = {name: "x" for name in rwm.FROZEN_KEYS}
        registration = {"card_ids": {wm.PHASE: "MC-103"}, "card_files": {wm.PHASE: "missing.md"},
                        "frozen": {**manifest, "manifest_sha256": "y"}}
        gates = {gate.name: gate.ok for gate in rwm.evaluate_gates(
            CONFIG, manifest, registration, ("https://opencode.ai/zen/go/v1", STUDENT["model_id"], True),
            card_text="## MC-103 — test\n")}
        self.assertEqual(gates, {"card_registered": True, "detail_card": False, "frozen_hashes": False,
                                 "route_identity": True})


if __name__ == "__main__":
    unittest.main()
