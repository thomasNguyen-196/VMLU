"""Offline tests for MC-113's runner (run_legal_agent_omp) and analysis (analyze_legal_agent_omp). No omp, no model;
the omp end-to-end check is `python -m code_benchmark.run_legal_agent_omp --selftest`."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_benchmark import analyze_legal_agent_omp as alo
from code_benchmark import dsh_proxy as px
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_legal_agent_omp as ro
from code_benchmark import vi_multimodel as v1
from code_benchmark.test_dsh_proxy import MODEL, post

KEYS = frozenset({"chat_template_kwargs", "max_completion_tokens", "messages", "model", "preserve_thinking", "stream",
                  "stream_options", "tool_choice", "tools"})
SYSTEM = "<system-conventions>omp</system-conventions>"
TASK = "Thư mục làm việc hiện tại chứa toàn văn...\n\nCâu hỏi\nĐáp án: "


def ok(n: int, tool_calls=(), content="", finish="stop", tokens=10) -> dict:
    return {"n": n, "outcome": "ok", "response": {"content": content, "tool_calls": [{"name": t} for t in tool_calls],
                                                 "finish_reason": finish, "usage": {"total_tokens": tokens,
                                                                                    "prompt_tokens": tokens - 2,
                                                                                    "completion_tokens": 2},
                                                 "model": "m.gguf"}}


def result(records, text=None, stop="stop", timed_out=False, exit_code=0) -> dict:
    message = {"role": "assistant", "content": [{"type": "text", "text": text}] if text else [], "stopReason": stop}
    events = [{"type": "agent_start"}, {"type": "agent_end", "messages": [{"role": "user", "content": []}, message]}]
    return {"records": records, "events": events, "timed_out": timed_out, "exit_code": exit_code, "wall_s": 1.0}


def main_body(**extra) -> dict:
    return {"model": MODEL, "stream": True, "stream_options": {"include_usage": True}, "max_completion_tokens": 4096,
            "preserve_thinking": True, "chat_template_kwargs": {"preserve_thinking": True}, "tools": [{"x": 1}],
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": [{"type": "text", "text": "<system-reminder>Today</system-reminder>"},
                                                      {"type": "text", "text": TASK}]}], **extra}


class Classify(unittest.TestCase):
    def check(self, res, status, outcome, error_type=None, fatal=False):
        verdict = ro.classify(res)
        self.assertEqual((verdict["status"], verdict["outcome"], verdict["error_type"], verdict["fatal"]),
                         (status, outcome, error_type, fatal))
        return verdict

    def test_final_answer(self):
        verdict = self.check(result([ok(1, ["grep"]), ok(2, content="Đáp án: B")], "Đáp án: B"), "complete", "complete")
        self.assertEqual((verdict["raw_response"], verdict["final_reason"]), ("Đáp án: B", "stop"))

    def test_terminal_outcomes_without_an_answer(self):
        self.check(result([ok(1, ["glob"]), ok(2, ["glob"]), {"n": 3, "outcome": "refused_cap"},
                           {"n": 4, "outcome": "refused_cap"}], stop="error"), "complete", "request_cap")
        self.check(result([{"n": 1, "outcome": "upstream_4xx", "status": 400}], stop="error"), "complete",
                   "upstream_4xx")
        self.check(result([ok(1, finish="length", content="xxx")], "xxx", stop="length"), "complete", "answer_cap")
        self.check(result([ok(1)], stop="stop"), "complete", "harness_end")  # stopped with no text

    def test_technical_failures_are_resumable(self):
        after = {"n": 2, "outcome": ro.AFTER_FAILURE, "status": 503}
        self.check(result([{"n": 1, "outcome": "upstream_5xx", "status": 503}, after], stop="error"),
                   "request_error", "technical", "upstream_5xx")
        self.check(result([ok(1, ["grep"]), {"n": 2, "outcome": "network", "error_type": "TimeoutError"}, after],
                          stop="error"), "request_error", "technical", "APITimeoutError")
        self.check(result([ok(1, ["grep"]), {"n": 2, "outcome": "network", "error_type": "stream_ended_early"}],
                          stop="aborted"), "request_error", "technical", "wall_clock")  # omp's --max-time
        self.check(result([ok(1, ["grep"])], timed_out=True), "request_error", "technical", "wall_clock")

    def test_refusals_and_a_dead_sandbox_pause_the_run(self):
        self.check(result([{"n": 1, "outcome": "refused_body"}], stop="error"), "request_error", "fatal",
                   "refused_body", True)
        self.check(result([{**ok(1, content="x"), "outcome": "model_drift"}], "x"), "request_error", "fatal",
                   "model_drift", True)
        self.check({**result([]), "events": [], "exit_code": 97}, "request_error", "fatal", "sandbox_start", True)


class Shape(unittest.TestCase):
    rules = ro.ShapeRules(KEYS, 4096, system_sha256=v1.sha256_bytes(SYSTEM.encode()), task=TASK)

    def test_the_main_request_passes(self):
        self.assertIsNone(self.rules.problem(1, main_body()))
        self.assertEqual(ro.last_user_text(main_body()["messages"]), TASK)

    def test_compaction_requests_pass(self):
        self.assertIsNone(self.rules.problem(5, main_body(tool_choice="none")))  # handoff
        summary = {key: value for key, value in main_body().items() if key != "tools"}
        summary.update(max_completion_tokens=512, messages=[{"role": "system", "content": "summarize"}])
        self.assertIsNone(self.rules.problem(6, summary))

    def test_a_changed_shape_is_a_problem(self):
        self.assertIn("seed", self.rules.problem(1, main_body(seed=1)) or "")
        self.assertIn("max_completion_tokens", self.rules.problem(2, main_body(max_completion_tokens=8192)) or "")
        self.assertIn("max_completion_tokens", self.rules.problem(2, main_body(max_completion_tokens=512)) or "")
        other = main_body()
        other["messages"][0]["content"] = SYSTEM + "<workstation>other host</workstation>"
        self.assertIn("system prompt", self.rules.problem(1, other) or "")
        self.assertIsNone(self.rules.problem(2, other))  # the first request carries the checks
        changed = main_body()
        changed["messages"][1]["content"][1]["text"] = TASK + " "
        self.assertIn("task", self.rules.problem(1, changed) or "")


class Proxy(unittest.TestCase):
    def run_proxy(self, script, bodies, rules=None):
        with ro.ScriptedUpstream(script) as upstream, tempfile.TemporaryDirectory() as tmp:
            config = px.ProxyConfig(upstream=upstream.url, api_key="REAL-KEY", model=MODEL,
                                    expected_response_model="fake-model.gguf")
            with ro.OmpProxy(config, rules or Shape.rules, Path(tmp) / "p.sock", Path(tmp) / "log.jsonl") as proxy:
                replies = [post(Path(tmp) / "p.sock", body) for body in bodies]
            return replies, list(proxy.records), upstream

    def test_a_refused_shape_is_never_forwarded(self):
        replies, records, upstream = self.run_proxy([{"text": "x"}], [main_body(seed=1)])
        self.assertEqual((replies[0][0], records[0]["outcome"]), (400, "refused_body"))
        self.assertEqual(upstream.requests, [])
        self.assertEqual(px.attempt_outcome(records)["fatal"], ["refused_body"])

    def test_nothing_is_sent_after_a_technical_failure(self):
        replies, records, upstream = self.run_proxy([{"status": 503}, {"text": "x"}], [main_body(), main_body()])
        self.assertEqual([r[0] for r in replies], [503, 503])
        self.assertEqual([r["outcome"] for r in records], ["upstream_5xx", ro.AFTER_FAILURE])
        self.assertEqual(len(upstream.requests), 1)
        self.assertEqual(upstream.requests[0]["temperature"], 1.0)

    def test_scripted_upstream_extras(self):
        _, records, _ = self.run_proxy([{"text": "Đáp án: B", "finish": "length", "prompt_tokens": 57000}],
                                       [main_body()])
        response = records[0]["response"]
        self.assertEqual((response["finish_reason"], response["usage"]["prompt_tokens"]), ("length", 57000))


class Sandbox(unittest.TestCase):
    def test_only_the_pinned_paths_are_visible(self):
        harness = ro.Harness(binary=Path("/x/omp"), config={}, argv=("-p", "--mode", "json"))
        command = ro.sandbox_command(harness, Path("/data/docs"), Path("/out/home"), Path("/sock/s"), "câu hỏi")
        binds = [(command[i], command[i + 1], command[i + 2]) for i, arg in enumerate(command)
                 if arg in ("--bind", "--ro-bind")]
        writable = [(src, dst) for kind, src, dst in binds if kind == "--bind"]
        self.assertEqual(writable, [("/sock/s", "/run/proxy"), ("/out/home", ro.HOME)])
        self.assertIn(("--ro-bind", "/x/omp", "/opt/omp"), binds)
        self.assertIn(("--ro-bind", "/data/docs", ro.WORKDIR), binds)
        self.assertNotIn("/", [src for _, src, _ in binds])
        self.assertEqual([src for _, src, _ in binds if src.startswith(str(Path.home()))], [str(ro.rla.RELAY)])
        self.assertIn("--unshare-all", command)
        self.assertIn("--clearenv", command)
        self.assertEqual(command[-4:], ["-p", "--mode", "json", "câu hỏi"])
        self.assertEqual(command[command.index("--chdir") + 1], ro.WORKDIR)
        env = {command[i + 1]: command[i + 2] for i, arg in enumerate(command) if arg == "--setenv"}
        self.assertEqual((env["IEC_API_KEY"], env["PI_CODING_AGENT_DIR"], env["HOME"]),
                         (px.DUMMY_KEY, ro.AGENT_DIR, ro.HOME))
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_the_home_holds_only_the_registered_files(self):
        config = ro.load_config()
        with tempfile.TemporaryDirectory() as tmp:
            ro.prepare_home(Path(tmp) / "home", config)
            files = sorted(str(p.relative_to(tmp)) for p in Path(tmp).rglob("*") if p.is_file())
            self.assertEqual(files, ["home/.omp/agent/config.yml", "home/.omp/agent/models.yml"])
            written = json.loads((Path(tmp) / "home/.omp/agent/config.yml").read_text(encoding="utf-8"))
        self.assertEqual((written["retry"], written["startup"]), ({"enabled": False}, {"checkUpdate": False}))
        model = config["models.yml"]["providers"]["iec"]["models"][0]
        self.assertEqual((model["id"], model["contextWindow"], model["maxTokens"]), ("Qwen3.5-9B-65K", 65024, 4096))

    def test_the_registered_invocation(self):
        protocol = ro.load_protocol()
        argv = protocol["harness"]["argv"]
        self.assertEqual(argv[argv.index("--tools") + 1], "read,grep,glob")
        self.assertNotIn("--no-session", argv)  # spill read-back needs the session (design §3)
        for flag in ("--no-title", "--no-extensions", "--no-skills", "--no-rules", "--no-lsp", "--auto-approve"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--cwd") + 1], ro.WORKDIR)
        self.assertEqual(set(protocol["harness"]["body_keys"]), KEYS)


@unittest.skipUnless((ro.ROOT / ro.load_protocol()["mc112"]["scores"]).is_file(), "needs MC-112's local outputs")
class Manifest(unittest.TestCase):
    def test_tasks_are_mc112_dshf_tasks(self):
        manifest, rebuilt = ro.build_manifest()
        self.assertEqual((manifest["n"], manifest["item_count"], manifest["arm_counts"]), (268, 134, {"OMPF": 268}))
        order = [(ref["item_id"], ref["replicate_id"]) for ref in manifest["items"]]
        self.assertEqual(order[:4], [(manifest["pool"][0], "OMPF-r1"), (manifest["pool"][0], "OMPF-r2"),
                                     (manifest["pool"][1], "OMPF-r1"), (manifest["pool"][1], "OMPF-r2")])
        mc112 = json.loads((ro.ROOT / "data/diagnostic_legal_agent/manifest_v1.json").read_text(encoding="utf-8"))
        dshf = {ref["item_id"]: ref["prompt_sha256"] for ref in mc112["items"] if ref["replicate_id"] == "DSHF-r2"}
        self.assertTrue(all(ref["prompt_sha256"] == dshf[ref["item_id"]] for ref in manifest["items"]))
        self.assertTrue(all("gold_answer" not in ref and "provisions" not in ref for ref in manifest["items"]))
        anchors = [p["anchor_line"] for row in ro.la.load_provisions().values() for p in row["provisions"]]
        prompts = {item.prompt for item in rebuilt.values()}
        self.assertFalse([a for a in anchors if any(a in prompt for prompt in prompts) and len(a) > 40])
        self.assertEqual(ro.load_frozen_manifest(), manifest)


class Request(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)
        self.protocol = {"harness": {"api_protocol": "openai-chat-completions", "max_completion_tokens": 4096,
                                     "body_keys": sorted(KEYS)},
                         "proxy": {"system_prompt_sha256": "s" * 64}}
        self.context = ro.AttemptContext(
            harness=ro.Harness(Path("/x"), {}, ()), docs=Path("/d"), output=self.output, protocol=self.protocol,
            wall_clock=60, proxy=px.ProxyConfig(upstream="http://h/v1", api_key="k", model="Qwen3.5-9B-65K",
                                                expected_response_model="m.gguf"))
        self.item = v1.EvalItem(dataset_id="d", source_dataset="s", item_id="LG-0001", replicate_id="OMPF-r1",
                                task="multiple_choice", stratum="legal", question="q", passage_id="legal",
                                prompt="p", gold_answer="B")

    def tearDown(self):
        self.tmp.cleanup()

    def run_one(self, res, guard=None):
        guard = guard or pr.BudgetGuard(1000)
        request = ro.make_request(self.protocol, guard, pr.OutageGuard(4), 4)
        with mock.patch.object(ro, "run_sandboxed", return_value=res) as sandboxed:
            row = request(self.context, self.item, 0, 1)
        return row, sandboxed, guard

    def test_a_complete_attempt_row(self):
        records = [ok(1, ["grep", "read"]), {"n": 2, "outcome": "refused_cap"}, ok(3, content="B")]
        row, sandboxed, guard = self.run_one(result(records, "B"))
        self.assertEqual((row["status"], row["outcome"], row["raw_response"], row["arm"]),
                         ("complete", "complete", "B", "OMPF"))
        self.assertEqual(row["tool_calls"], {"grep": 1, "read": 1})
        self.assertEqual((row["requests"], row["requests_forwarded"], row["total_tokens"]), (3, 2, 20))
        self.assertEqual(row["attempt_dir"], "attempts/d_LG-0001_OMPF-r1/try-1")
        args = sandboxed.call_args.args
        self.assertEqual((args[3], args[5].task, args[5].system_sha256), ("p", "p", "s" * 64))
        self.assertEqual(guard.used, 20)

    def test_a_spent_budget_sends_nothing(self):
        row, sandboxed, _ = self.run_one(result([]), guard=pr.BudgetGuard(10, 10))
        self.assertEqual((row["status"], row["error_type"], row["fatal"]), ("request_error", "budget_cap", True))
        sandboxed.assert_not_called()


def score_row(arm: str, draw: str, correct: int, prediction: str = "A", gold: str = "A", **extra) -> dict:
    return {"replicate_id": f"{arm}-r{draw}", "correct": correct, "prediction": prediction, "gold_answer": gold,
            **extra}


class Analysis(unittest.TestCase):
    def cells(self, ompf: list[int], dshf: list[int], b: list[int]) -> dict:
        out = {}
        for index, (x, y, z) in enumerate(zip(ompf, dshf, b, strict=True)):
            out[f"LG-{index:04d}"] = {f"{arm}{d}": score_row(arm, d, v) for arm, v in (("OMPF", x), ("DSHF", y),
                                                                                         ("B", z)) for d in "12"}
        return out

    def test_the_margin_applies_to_both_questions(self):
        n = 40
        cells = self.cells([1] * 30 + [0] * 10, [1] * n, [1] * 30 + [0] * 10)  # OMPF -25 vs DSHF, 0 vs B
        rules = alo.rules(alo.questions(sorted(cells), cells), 0.05, 2.24)
        self.assertTrue(rules["OMPF_vs_DSHF"]["worse"])
        self.assertEqual(rules["OMPF_vs_DSHF"]["reading"], "OMPF is worse than DSHF")
        self.assertEqual(rules["OMPF_vs_B"]["reading"], "no clear difference between OMPF and B")
        self.assertEqual(rules["legal_mc_route"], "B")

    def test_a_significant_gain_within_the_margin_is_no_clear_difference(self):
        blocks = {"OMPF_vs_DSHF": {"OMPF_versus_DSHF": {"mean_points": 2.0, "sign_flip_p": 0.001}},
                  "OMPF_vs_B": {"OMPF_versus_B": {"mean_points": 6.0, "sign_flip_p": 0.001}}}
        rules = alo.rules(blocks, 0.05, 2.24)
        self.assertEqual(rules["OMPF_vs_DSHF"]["reading"], "no clear difference between OMPF and DSHF")
        self.assertTrue(rules["OMPF_vs_B"]["better"])
        self.assertEqual(rules["legal_mc_route"], "OMPF")

    def test_retrieval_beside_dshf_and_accuracy_by_retrieval(self):
        cells = self.cells([1, 0], [1, 1], [1, 1])
        miss = {"seen": False, "read": False, "opened": False}
        hit = {"seen": True, "read": True, "opened": True}
        hits = {"LG-0000": {"OMPF1": hit, "OMPF2": hit, "DSHF1": hit, "DSHF2": miss},
                "LG-0001": {"OMPF1": miss, "OMPF2": miss, "DSHF1": hit, "DSHF2": hit}}
        block = alo.retrieval(sorted(cells), ["LG-0000"], hits)
        self.assertEqual((block["pool"]["OMPF"]["read"], block["pool"]["DSHF"]["read"]), (50.0, 75.0))
        self.assertEqual(block["pool"]["OMPF_minus_DSHF"]["read"]["mean_points"], -25.0)
        self.assertEqual(block["mc100_oracle_items"]["OMPF"]["read"], 100.0)
        split = alo.by_retrieval(cells, hits, {"LG-0000": "supports_gold", "LG-0001": "supports_gold"})
        self.assertEqual(split["OMPF"], {"read": {"attempts": 2, "accuracy": 100.0},
                                         "not_read": {"attempts": 2, "accuracy": 0.0}})

    def test_behaviour_reads_selectors_and_compactions_from_the_attempts(self):
        cells = self.cells([1], [1], [1])
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for d in "12":
                cells["LG-0000"][f"OMPF{d}"].update(tool_calls={"grep": 1, "read": 1}, requests=3,
                                                     requests_forwarded=2, outcome="complete",
                                                     attempt_dir=f"attempts/a{d}/try-1")
                cells["LG-0000"][f"DSHF{d}"].update(tool_calls={"grep": 2}, requests=4, outcome="complete")
                attempt = run_dir / f"attempts/a{d}/try-1"
                attempt.mkdir(parents=True)
                events = [{"type": "auto_compaction_start", "action": "handoff"}] if d == "1" else []
                (attempt / "events.jsonl").write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                                                              for e in events), encoding="utf-8")
            behaviour = alo.behaviour(cells, run_dir)
        self.assertEqual((behaviour["OMPF"]["requests_per_attempt"], behaviour["DSHF"]["requests_per_attempt"]),
                         (2.0, 4.0))
        self.assertEqual(behaviour["OMPF"]["per_attempt"]["compactions"], 0.5)
        self.assertEqual(behaviour["OMPF"]["per_attempt"]["attempts_with_compaction"], 1)


if __name__ == "__main__":
    unittest.main()
