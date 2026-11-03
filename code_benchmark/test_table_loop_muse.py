"""Offline tests of the Muse table loop (card MC-108): the configuration, the manifests against MC-104's and MC-105's
rows, the loop, the Responses API request and the registered analysis on a synthetic run. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_table_loop_muse
"""
from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from code_benchmark import analyze_table_loop_muse as atm
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import diagnostic_self_loop as sl
from code_benchmark import diagnostic_table_loop as tl
from code_benchmark import diagnostic_table_loop_muse as tm
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_table_loop_muse as rtm
from code_benchmark import vi_multimodel as v1

CONFIG, CONFIG_SHA = tm.load_config()
HAS_MANIFESTS = all(tm.manifest_path(student).is_file() for student in tm.STUDENTS)
HAS_REFERENCES = atm.REFERENCE_PATH.is_file() and atm.MC105_REPORT.is_file()
READING = v1.EvalItem(dataset_id="vi-multimodel-v1-vi-squad-200", source_dataset="squad", item_id="7",
                      replicate_id="B-r1", task="reading", stratum="x", question="Ai?", passage_id="p",
                      prompt="Đọc đoạn văn\n\nCâu hỏi: Ai?\nTrả lời: ", gold_answer="An")


def answers(b1: str, b2: str, s: list[str]) -> dict[str, str]:
    return {"B-r1": b1, "B-r2": b2, "S-r1": s[0], "S-r2": s[1], "S-r3": s[2]}


class TestConfig(unittest.TestCase):
    def test_both_students_answer_b_twice_and_s_three_times_on_the_seven_columns(self):
        self.assertEqual(set(CONFIG["students"]), {"muse13", "muse12"})
        for arms in CONFIG["arms"].values():
            self.assertEqual(arms, {"multiple_choice": tm.ARMS, "reading": tm.ARMS})
        self.assertEqual(atm.datasets(CONFIG)[0], tm.VMLU_DEV)
        self.assertEqual(len(atm.datasets(CONFIG)), 7)
        self.assertEqual(sum(CONFIG["items"]["datasets"].values()) + CONFIG["items"]["vmlu_dev"]["n"], 2346)

    def test_a_config_that_drifts_fails_closed(self):
        for change in ({"arms": {**CONFIG["arms"], "muse12": {"multiple_choice": ["B-r1", "S-r1", "S-r2", "S-r3"],
                                                              "reading": tm.ARMS}}},
                       {"students": {**CONFIG["students"], "muse12": {**CONFIG["students"]["muse12"],
                                                                      "model_identity": "muse-spark-1.3"}}},
                       {"loop": {**CONFIG["loop"], "fitted_parameters": "a threshold of 0.8"}}):
            with self.assertRaises(SystemExit):
                tm.validate_config({**CONFIG, **change})

    def test_the_registration_names_this_config_and_card(self):
        registration = rtm.load_registration()
        self.assertEqual(registration["frozen"]["config_sha256"], CONFIG_SHA)
        self.assertEqual(registration["card_ids"][tm.PHASE], "MC-108")


class TestLoop(unittest.TestCase):
    def test_the_loop_is_mc105s_mimo_loop_for_both_tasks(self):
        rng = random.Random(11)
        for task, pool in (("multiple_choice", ["A", "B", "C", ""]), ("reading", ["Hà Nội", "hà nội.", "Huế", ""])):
            for _ in range(1000):
                b1, b2, *s = (rng.choice(pool) for _ in range(5))
                for student in tm.STUDENTS:
                    self.assertEqual(tm.choose(task, student, answers(b1, b2, s)),
                                     tl.choose(task, "mimo", answers(b1, b2, s), None, 0.8))
            letters = ["A", "B", ""]
            b1, b2, *s = (rng.choice(letters) for _ in range(5))
            replicate, rounds = tm.choose("multiple_choice", "muse13", answers(b1, b2, s))
            self.assertEqual((answers(b1, b2, s)[replicate], rounds), sl.loop_mimo(b1, b2, s))
        with self.assertRaises(SystemExit):
            tm.choose("reading", "qwen", answers("a", "a", ["", "", ""]))


@unittest.skipUnless(HAS_MANIFESTS, "needs the frozen Muse table-loop manifests")
class TestManifests(unittest.TestCase):
    def test_the_frozen_manifests_rebuild_and_match_the_registration(self):
        registration = rtm.load_registration()
        for student in tm.STUDENTS:
            manifest, rebuilt = tm.build_manifest(student)
            self.assertEqual(manifest, tm.load_frozen_manifest(student))
            self.assertEqual(registration["frozen"]["manifest_sha256"][student], manifest["manifest_sha256"])
            self.assertEqual((manifest["item_count"], manifest["n"]), (2346, 11730))
            self.assertEqual(len(dp.verify_manifest_rows(manifest, rebuilt)), 11730)

    def test_every_row_is_byte_for_byte_mimos_row_in_mc104_and_mc105(self):
        mine = {dp.run_key(row): row for row in tm.load_frozen_manifest("muse13")["items"]}
        for path, n in ((tl.manifest_path("mimo"), 10215), (sl.manifest_path("mimo"), 1515)):
            theirs = {dp.run_key(row): row for row in json.loads(path.read_text(encoding="utf-8"))["items"]}
            common = set(mine) & set(theirs)
            self.assertEqual(len(common), n)
            self.assertTrue(all(mine[key] == theirs[key] for key in common))
        twin = {dp.run_key(row): row for row in tm.load_frozen_manifest("muse12")["items"]}
        self.assertEqual(mine, twin)


def response(text="Trả lời: An", model="muse-spark-1.3-contributor", status="completed", reason=None, tools=0,
             error=None):
    output = [SimpleNamespace(type="reasoning"),
              SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text)])]
    output += [SimpleNamespace(type="function_call")] * tools
    usage = SimpleNamespace(input_tokens=40, output_tokens=300, total_tokens=340,
                            input_tokens_details=SimpleNamespace(cached_tokens=0),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=280))
    return SimpleNamespace(output=output, status=status, model=model, id="resp_1", usage=usage, error=error,
                           incomplete_details=SimpleNamespace(reason=reason) if reason else None)


class FakeResponses:
    def __init__(self, outcome):
        self.outcome, self.kwargs = outcome, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class EngineState(unittest.TestCase):
    def setUp(self):
        self.saved = (rtm.base.MODEL, rtm.base.PROFILE, rtm.base.PROTOCOL)
        rtm.base.MODEL, rtm.base.PROFILE, rtm.base.PROTOCOL = "muse-spark-1.3-contributor", "muse13", tm.PROTOCOL_ID

    def tearDown(self):
        rtm.base.MODEL, rtm.base.PROFILE, rtm.base.PROTOCOL = self.saved

    def send(self, outcome, student="muse13", item=READING, pin=None):
        config = CONFIG["students"][student]
        request = rtm.make_muse_request(config, "MC-108", pr.BudgetGuard(10_000), pr.OutageGuard(4),
                                        pin or rtm.ModelPin(config["model_identity"]))
        client = SimpleNamespace(responses=FakeResponses(outcome))
        return request(client, item, 0, 0), client.responses.kwargs


class TestRequest(EngineState):
    def test_a_completed_reply_keeps_the_route_and_one_session_per_attempt(self):
        row, kwargs = self.send(response())
        self.assertEqual((row["status"], row["phase"], row["finish_reason"], row["raw_response"]),
                         ("complete", tm.PHASE, "stop", "Trả lời: An"))
        self.assertEqual((row["reasoning_tokens"], row["total_tokens"]), (280, 340))
        self.assertEqual(kwargs["input"], [{"role": "system", "content": "Answer the user's question."},
                                           {"role": "user", "content": READING.prompt}])
        self.assertEqual((kwargs["max_output_tokens"], kwargs["stream"]), (20000, False))
        self.assertNotIn("temperature", kwargs)
        self.assertEqual(kwargs["extra_headers"], {rtm.SESSION_HEADER: rtm.session_id(READING.run_key)})
        self.assertTrue(rtm.session_id(READING.run_key).startswith("vmlu-mc108-"))

    def test_a_reply_cut_at_the_cap_is_complete_and_other_unfinished_replies_are_errors(self):
        row, _ = self.send(response(status="incomplete", reason="max_output_tokens"))
        self.assertEqual((row["status"], row["finish_reason"]), ("complete", "length"))
        row, _ = self.send(response(status="incomplete", reason="content_filter"))
        self.assertEqual((row["status"], row.get("fatal")), ("request_error", False))
        row, _ = self.send(response(tools=1))
        self.assertEqual((row["status"], row["fatal"]), ("request_error", True))
        row, _ = self.send(response(status="failed", error=SimpleNamespace(code="invalid_api_key")))
        self.assertTrue(row["fatal"])

    def test_the_other_muse_version_or_an_auth_error_stops_the_run(self):
        row, _ = self.send(response(model="muse-spark-1.2-contributor"))
        self.assertEqual((row["status"], row["error_type"], row["fatal"]), ("request_error", "unexpected_model", True))
        class Denied(Exception):
            status_code = 401
        row, _ = self.send(Denied("denied"))
        self.assertEqual((row["http_status"], row["fatal"]), (401, True))
        timeout = TimeoutError()
        row, _ = self.send(timeout)
        self.assertEqual((row["status"], row["fatal"], row["retry_wait_seconds"]), ("request_error", False, 5))


class TestGates(unittest.TestCase):
    def test_gates(self):
        manifest = {"config_sha256": "c", "manifest_sha256": "m"}
        registration = {"card_ids": {tm.PHASE: "MC-108"}, "card_files": {tm.PHASE: "missing.md"},
                        "frozen": {"config_sha256": "c", "manifest_sha256": {"muse13": "m", "muse12": "other"}}}
        ok = {g.name: g.ok for g in rtm.evaluate_gates("muse13", manifest, registration, True, "ok",
                                                       card_text="## MC-108 — test\n")}
        self.assertEqual(ok, {"card_registered": True, "detail_card": False, "frozen_hashes": True, "route_identity": True})
        bad = {g.name: g.ok for g in rtm.evaluate_gates("muse12", manifest, registration, False, "no",
                                                        card_text="## MC-1080 — other\n")}
        self.assertEqual(bad, {"card_registered": False, "detail_card": False, "frozen_hashes": False,
                               "route_identity": False})


@unittest.skipUnless(HAS_MANIFESTS and HAS_REFERENCES, "needs the frozen manifests, /table data and the MC-105 report")
class TestAnalysis(unittest.TestCase):
    """The registered analysis on a synthetic complete run: B right on about half the items (the two B answers
    disagree when wrong), S always right, so the loop reaches S's score."""

    def synthetic(self, root: Path) -> None:
        for student in tm.STUDENTS:
            manifest = tm.load_frozen_manifest(student)
            run_dir = root / CONFIG["students"][student]["profile_id"]
            run_dir.mkdir(parents=True)
            rows = []
            for position, ref in enumerate(manifest["items"]):
                right = ref["replicate_id"].startswith("S") or int(v1.sha256_bytes(ref["item_id"].encode())[:2], 16) % 2 == 0
                row = {key: ref[key] for key in ("dataset_id", "item_id", "replicate_id")}
                row.update({"gold_answer": "A", "total_tokens": 100 + position % 3, "prompt_tokens": 60,
                            "completion_tokens": 40 + position % 3, "cached_prompt_tokens": 0})
                if ref["task"] == "multiple_choice":
                    wrong = "B" if ref["replicate_id"] == "B-r1" else "C"  # the two wrong B answers disagree
                    row.update({"prediction": "A" if right else wrong, "correct": int(right)})
                else:
                    row.update({"prediction": "a" if right else ref["replicate_id"],
                                **dict.fromkeys(("token_f1", "em", "token_f1_v2", "em_v2"), 1.0 if right else 0.0)})
                rows.append(row)
            v1.write_jsonl_atomic(run_dir / "scores.jsonl", rows)
            (run_dir / "run.json").write_text(json.dumps({"status": "complete",
                                                          "manifest_sha256": manifest["manifest_sha256"]}))

    def test_the_report_has_the_registered_keys_and_fourteen_primary_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.synthetic(root)
            report = atm.build_report(root)
        self.assertEqual(list(report), rtm.load_registration()["analysis"]["report_keys"])
        self.assertEqual(len(report["primary"]), 14)
        for student in tm.STUDENTS:
            dev = report["datasets"][student][tm.VMLU_DEV]
            self.assertEqual((dev["n"], dev["policies"]["always_S"]["accuracy"], dev["policies"]["loop"]["accuracy"]),
                             (303, 100.0, 100.0))
            self.assertLess(dev["policies"]["always_B"]["accuracy"], 70.0)
            self.assertTrue(report["primary"][f"{student}:{tm.VMLU_DEV}"]["met"])
            self.assertEqual(dev["table_reference"], atm.reference_for(json.loads(atm.REFERENCE_PATH.read_text()),
                                                                      CONFIG, student, tm.VMLU_DEV))
            self.assertEqual(report["cost"][student]["attempts"], 11730)
            self.assertGreater(report["cost"][student]["list_price_usd"], 0)
        self.assertEqual(set(report["beside_mc105"]["students"]), {"qwen", "mimo"})

    def test_a_run_that_stops_short_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.synthetic(root)
            scores = root / CONFIG["students"]["muse12"]["profile_id"] / "scores.jsonl"
            scores.write_text("\n".join(scores.read_text().splitlines()[:-1]) + "\n")
            with self.assertRaises(SystemExit):
                atm.build_report(root)


if __name__ == "__main__":
    unittest.main()
