"""Offline tests for MC-112's runner (run_legal_agent) and analysis (analyze_legal_agent). No dsh, no model; the
dsh end-to-end check is `python -m code_benchmark.run_legal_agent --selftest`."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import analyze_legal_agent as ala
from code_benchmark import dsh_proxy as px
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_legal_agent as ra
from code_benchmark import vi_multimodel as v1


def ok(n: int, tool_calls=(), content="", finish="stop", tokens=10) -> dict:
    return {"n": n, "outcome": "ok", "response": {"content": content, "tool_calls": [{"name": t} for t in tool_calls],
                                                 "finish_reason": finish, "usage": {"total_tokens": tokens,
                                                                                    "prompt_tokens": tokens - 2,
                                                                                    "completion_tokens": 2},
                                                 "model": "m.gguf"}}


def result(records, final_text=None, kind="completed", timed_out=False, exit_code=0) -> dict:
    events = [{"type": "final", "reason": {"kind": kind}, "text": final_text}] if final_text is not None else []
    return {"records": records, "events": events, "timed_out": timed_out, "exit_code": exit_code, "wall_s": 1.0}


class Classify(unittest.TestCase):
    def check(self, res, status, outcome, error_type=None, fatal=False):
        verdict = ra.classify(res)
        self.assertEqual((verdict["status"], verdict["outcome"], verdict["error_type"], verdict["fatal"]),
                         (status, outcome, error_type, fatal))
        return verdict

    def test_final_answer(self):
        verdict = self.check(result([ok(1, ["grep"]), ok(2, content="Đáp án: B")], "Đáp án: B"), "complete", "complete")
        self.assertEqual(verdict["raw_response"], "Đáp án: B")

    def test_terminal_outcomes_without_an_answer(self):
        cap = {"n": 31, "outcome": "refused_cap"}
        self.check(result([ok(1, ["glob"]), cap]), "complete", "request_cap")
        self.check(result([ok(1, ["glob"]), {"n": 2, "outcome": "upstream_4xx", "status": 400}]),
                   "complete", "upstream_4xx")
        self.check(result([ok(1, finish="length")]), "complete", "answer_cap")
        self.check(result([ok(1)]), "complete", "harness_end")

    def test_technical_failures_are_resumable(self):
        self.check(result([ok(1, ["grep"]), {"n": 2, "outcome": "network", "error_type": "TimeoutError"}]),
                   "request_error", "technical", "APITimeoutError")
        self.check(result([{"n": 1, "outcome": "network", "error_type": "ConnectionRefusedError"}]),
                   "request_error", "technical", "APIConnectionError")
        self.check(result([{"n": 1, "outcome": "upstream_5xx", "status": 503}]), "request_error", "technical",
                   "upstream_5xx")
        self.check(result([ok(1, ["grep"])], timed_out=True), "request_error", "technical", "wall_clock")

    def test_configuration_drift_and_a_dead_sandbox_pause_the_run(self):
        self.check(result([{"n": 1, "outcome": "refused_temperature"}]), "request_error", "fatal",
                   "refused_temperature", True)
        self.check(result([ok(1, content="x")], "x"), "complete", "complete")
        self.check(result([{**ok(1, content="x"), "outcome": "model_drift"}], "x"), "request_error", "fatal",
                   "model_drift", True)
        self.check(result([], exit_code=97), "request_error", "fatal", "sandbox_start", True)


class Sandbox(unittest.TestCase):
    def test_only_the_pinned_paths_are_visible(self):
        harness = ra.Harness(install=Path("/x/dsh"), node=Path("/x/node"), profile=Path("/x/p.yml"))
        command = ra.sandbox_command(harness, Path("/data/docs"), Path("/out/home"), Path("/sock/s"), "câu hỏi")
        binds = [(command[i], command[i + 1], command[i + 2]) for i, arg in enumerate(command)
                 if arg in ("--bind", "--ro-bind")]
        writable = [(src, dst) for kind, src, dst in binds if kind == "--bind"]
        self.assertEqual(writable, [("/sock/s", "/run/proxy"), ("/out/home", ra.HOME)])
        self.assertIn(("--ro-bind", "/data/docs", ra.WORKDIR), binds)
        self.assertNotIn("/", [src for _, src, _ in binds])
        # from the home directory only the relay script (one file) is visible; here install and node are /x
        self.assertEqual([src for _, src, _ in binds if src.startswith(str(Path.home()))], [str(ra.RELAY)])
        self.assertIn("--unshare-all", command)
        self.assertIn("--clearenv", command)
        self.assertEqual(command[-1], "câu hỏi")
        self.assertEqual(command[command.index("--chdir") + 1], ra.WORKDIR)
        env = {command[i + 1]: command[i + 2] for i, arg in enumerate(command) if arg == "--setenv"}
        self.assertEqual(env["IEC_API_KEY"], px.DUMMY_KEY)
        self.assertNotIn("OPENAI_API_KEY", env)


class Request(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.protocol = {"harness": {"api_protocol": "openai-chat-completions", "max_tokens": 4096}}
        self.context = ra.AttemptContext(
            harness=ra.Harness(Path("/x"), Path("/y"), Path("/z")), docs=Path("/d"), output=self.output,
            wall_clock=60, proxy=px.ProxyConfig(upstream="http://h/v1", api_key="k", model="Qwen3.5-9B-65K",
                                                expected_response_model="m.gguf"))
        self.item = v1.EvalItem(dataset_id="d", source_dataset="s", item_id="LG-0001", replicate_id="DSH-r1",
                                task="multiple_choice", stratum="legal", question="q", passage_id="legal",
                                prompt="p", gold_answer="B")

    def tearDown(self):
        self.tmp.cleanup()

    def run_one(self, res, guard=None):
        guard = guard or pr.BudgetGuard(1000)
        request = ra.make_request(self.protocol, guard, pr.OutageGuard(4), 4)
        with mock.patch.object(ra, "run_sandboxed", return_value=res) as sandboxed:
            row = request(self.context, self.item, 0, 1)
        return row, sandboxed, guard

    def test_a_complete_attempt_row(self):
        row, sandboxed, guard = self.run_one(result([ok(1, ["grep", "read"]), ok(2, content="B")], "B"))
        self.assertEqual((row["status"], row["outcome"], row["raw_response"], row["arm"]), ("complete", "complete", "B",
                                                                                           "DSH"))
        self.assertEqual(row["tool_calls"], {"grep": 1, "read": 1})
        self.assertEqual((row["requests"], row["total_tokens"], row["response_model_id"]), (2, 20, "m.gguf"))
        self.assertEqual(row["attempt_dir"], "attempts/d_LG-0001_DSH-r1/try-1")
        self.assertEqual(sandboxed.call_args.args[3], "p")
        self.assertEqual(guard.used, 20)

    def test_a_spent_budget_sends_nothing(self):
        row, sandboxed, _ = self.run_one(result([]), guard=pr.BudgetGuard(10, 10))
        self.assertEqual((row["status"], row["error_type"], row["fatal"]), ("request_error", "budget_cap", True))
        sandboxed.assert_not_called()


def score_row(arm: str, draw: str, correct: int, prediction: str = "A", gold: str = "A", **extra) -> dict:
    return {"replicate_id": f"{arm}-r{draw}", "correct": correct, "prediction": prediction, "gold_answer": gold,
            **extra}


class Analysis(unittest.TestCase):
    def cells(self, dsh: list[int], dshf: list[int], b: list[int]) -> dict:
        out = {}
        for index, (x, y, z) in enumerate(zip(dsh, dshf, b, strict=True)):
            out[f"LG-{index:04d}"] = {"DSH1": score_row("DSH", "1", x), "DSH2": score_row("DSH", "2", x),
                                      "DSHF1": score_row("DSHF", "1", y), "DSHF2": score_row("DSHF", "2", y),
                                      "B1": score_row("B", "1", z), "B2": score_row("B", "2", z)}
        return out

    def test_margin_rule_against_b(self):
        n = 40
        cells = self.cells([1] * n, [1] * 30 + [0] * 10, [1] * 39 + [0])  # DSH +2.5 over B, DSHF -22.5
        blocks = ala.questions(sorted(cells), cells)
        rules = ala.rules(blocks, 0.05, 2.24)
        self.assertFalse(rules["DSH_vs_B"]["beats_B"])  # +2.5 points but p is far above α
        self.assertTrue(rules["DSHF_vs_B"]["worse_than_B"])
        self.assertEqual(rules["DSHF_vs_DSH"]["reading"], "forcing search hurts")
        self.assertEqual(rules["legal_mc_route"], "B")

    def test_a_large_gain_within_the_margin_is_no_clear_difference(self):
        blocks = {"DSHF_vs_DSH": {"DSHF_versus_DSH": {"mean_points": 0.0, "sign_flip_p": 1.0}},
                  "DSH_vs_B": {"DSH_versus_B": {"mean_points": 2.0, "sign_flip_p": 0.001}},
                  "DSHF_vs_B": {"DSHF_versus_B": {"mean_points": 6.0, "sign_flip_p": 0.001}}}
        rules = ala.rules(blocks, 0.05, 2.24)
        self.assertEqual(rules["DSH_vs_B"]["reading"], "no clear difference between DSH and B")
        self.assertTrue(rules["DSHF_vs_B"]["beats_B"])
        self.assertEqual(rules["legal_mc_route"], "DSHF")

    def test_behaviour_retrieval_and_accuracy_by_retrieval(self):
        cells = self.cells([1, 0], [1, 1], [1, 1])
        for cell in cells.values():
            for key in ("DSH1", "DSH2"):
                cell[key].update(tool_calls={}, requests=1, outcome="complete")
            for key in ("DSHF1", "DSHF2"):
                cell[key].update(tool_calls={"grep": 2, "read": 1}, requests=4, outcome="complete")
        behaviour = ala.behaviour(cells)
        self.assertEqual((behaviour["DSH"]["searched_share"], behaviour["DSHF"]["searched_share"]), (0.0, 1.0))
        self.assertEqual(behaviour["DSHF"]["tool_calls_per_attempt"], {"grep": 2.0, "read": 1.0})
        miss = {"seen": False, "read": False, "opened": False}
        hit = {"seen": True, "read": True, "opened": True}
        hits = {item: {"DSH1": miss, "DSH2": miss, "DSHF1": hit, "DSHF2": hit if item == "LG-0000" else miss}
                for item in cells}
        block = ala.retrieval(sorted(cells), ["LG-0000"], hits)
        self.assertEqual(block["pool"]["DSHF"]["read"], 75.0)
        self.assertEqual(block["mc100_oracle_items"]["DSHF"]["read"], 100.0)
        split = ala.by_retrieval(cells, hits, {"LG-0000": "supports_gold", "LG-0001": "unclear"})
        self.assertEqual(split["DSHF"], {"read": {"attempts": 2, "accuracy": 100.0},
                                         "not_read": {"attempts": 0, "accuracy": None}})


if __name__ == "__main__":
    unittest.main()
