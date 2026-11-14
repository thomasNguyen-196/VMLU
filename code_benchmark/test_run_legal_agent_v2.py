"""Offline tests for MC-114's runner (run_legal_agent_v2) and analysis (analyze_legal_agent_v2). No sandbox, no model:
the harness paths and the campaign request are replaced by stubs."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from code_benchmark import analyze_legal_agent_v2 as ana
from code_benchmark import run_diagnostic_prospective as pr
from code_benchmark import run_legal_agent_v2 as run
from code_benchmark import vi_multimodel as v1


def item(arm: str, task: str = "multiple_choice", draw: int = 1) -> v1.EvalItem:
    return v1.EvalItem(dataset_id="d", source_dataset="s", item_id="i1", replicate_id=f"{arm}-r{draw}", task=task,
                       stratum="x", question="Q?", passage_id="p", prompt="TASK", gold_answer="A")


def context(output: Path) -> SimpleNamespace:
    spec = {"harness": {"api_protocol": "openai-chat-completions", "max_tokens": 4096, "max_completion_tokens": 4096}}
    proxy = SimpleNamespace(model="Qwen3.5-9B-65K", temperature=1.0)
    return SimpleNamespace(dsh_protocol=spec, omp_protocol=spec, dsh_proxy=proxy, omp_proxy=proxy, output=output,
                           client="client")


def verdict(status: str = "complete", outcome: str = "complete", fatal: bool = False, tokens: int = 100) -> dict:
    seen = {"response_models": ["m.gguf"], "requests": 3, "forwarded": 3, "outcomes": {"ok": 3},
            "prompt_tokens": tokens - 10, "completion_tokens": 10, "total_tokens": tokens}
    return {"proxy": seen, "status": status, "outcome": outcome, "raw_response": "Đáp án: A" if outcome == "complete"
            else "", "fatal": fatal, "error_type": "sandbox_start" if fatal else None, "final_reason": None}


class Dispatch(unittest.TestCase):
    def test_paths_by_arm(self):
        self.assertEqual([run.harness_of(a) for a in ("DSH", "DSHF", "OMPF", "B", "C", "O")],
                         ["dsh", "dsh", "omp", "direct", "direct", "direct"])
        with self.assertRaises(SystemExit):
            run.harness_of("K")

    def request(self, tmp: Path, outcomes: list[dict], cap: int = 10_000, direct=None):
        calls = []

        def fake_agent(ctx, it, harness):
            calls.append((it.replicate_id, harness))
            attempt = ctx.output / "attempts" / it.replicate_id / "try-1"
            return {"exit_code": 0, "wall_s": 1.0, "records": []}, outcomes[len(calls) - 1], attempt

        guard, outage = pr.BudgetGuard(cap), pr.OutageGuard(4)
        direct = direct or (lambda client, it, shard, lane: {"run_key": it.run_key, "status": "complete",
                                                              "raw_response": "A", "total_tokens": 7})
        patcher = mock.patch.object(run, "run_agent", side_effect=fake_agent)
        patcher.start()
        self.addCleanup(patcher.stop)
        return run.make_request({}, "MC-114", guard, outage, 4, direct=direct), guard, calls

    def test_agent_rows_count_tokens_and_carry_part_and_harness(self):
        with tempfile.TemporaryDirectory() as tmp:
            request, guard, calls = self.request(Path(tmp), [verdict(tokens=100), verdict(tokens=50)])
            ctx = context(Path(tmp))
            row = request(ctx, item("DSHF"), 0, 0)
            omp = request(ctx, item("OMPF", task="reading"), 0, 1)
            self.assertEqual((row["part"], row["harness"], row["status"], row["outcome"]), ("M", "dsh", "complete", "complete"))
            self.assertEqual((omp["part"], omp["harness"], omp["transport"]), ("S", "omp", "omp-json"))
            self.assertEqual(guard.used, 150)
            self.assertEqual(calls, [("DSHF-r1", "dsh"), ("OMPF-r1", "omp")])

    def test_the_direct_path_counts_its_own_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            request, guard, calls = self.request(Path(tmp), [])
            row = request(context(Path(tmp)), item("C", task="reading"), 0, 0)
            self.assertEqual((row["part"], row["harness"], row["raw_response"]), ("S", "direct", "A"))
            self.assertEqual((guard.used, calls), (0, []))

    def test_a_fatal_attempt_halts_the_next_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            request, _, calls = self.request(Path(tmp), [verdict("request_error", "fatal", fatal=True)])
            ctx = context(Path(tmp))
            first = request(ctx, item("DSH"), 0, 0)
            second = request(ctx, item("DSHF"), 0, 1)
            self.assertTrue(first["fatal"])
            self.assertEqual(second["error_type"], "halted_before_send")
            self.assertEqual(len(calls), 1)

    def test_an_exhausted_budget_sends_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            request, guard, calls = self.request(Path(tmp), [verdict()], cap=10)
            guard.add(10)
            row = request(context(Path(tmp)), item("DSH"), 0, 0)
            self.assertEqual((row["error_type"], calls), ("budget_cap", []))


class Scoring(unittest.TestCase):
    def test_span_rows_get_v3_with_v2_beside(self):
        row = {"token_f1": 0.0, "em": 0, "prediction": "**Trả lời:**", "raw_response": "**Trả lời:**\n100.000 đồng",  # nosec B105 - a score field, not a credential
               "gold_answer": "100.000 đồng"}
        out = run.rescore(row)
        self.assertEqual((out["token_f1"], out["em"], out["token_f1_v2"], out["em_v2"]), (1.0, 1, 0.0, 0))
        self.assertEqual(out["token_recall"], 1.0)
        self.assertEqual(run.rescore({"correct": 1}), {"correct": 1})

    def test_recall_counts_gold_tokens_only(self):
        self.assertEqual(run.token_recall("đấu thầu rộng rãi trong nước và quốc tế", "đấu thầu rộng rãi"), 1.0)
        self.assertEqual(run.token_recall("chỉ định thầu", "đấu thầu rộng rãi"), 0.25)  # "thầu" is shared
        self.assertEqual(run.token_recall("chỉ định", "đấu thầu rộng rãi"), 0.0)

    def test_summary_by_part_and_arm(self):
        rows = [{"part": "M", "arm": "B", "correct": 1}, {"part": "M", "arm": "B", "correct": 0},
                {"part": "S", "arm": "C", "token_f1": 0.5}]  # nosec B105 - a score field, not a credential
        summary = run.summarize(rows)
        self.assertEqual(summary["M:B"]["mean_points"], 50.0)
        self.assertEqual(summary["S:C"]["mean_points"], 50.0)


def cell(scores: dict[str, tuple[float, float]], metric: str = "correct") -> dict:
    return {f"{arm}{draw}": {metric: value} for arm, values in scores.items() for draw, value in zip("12", values, strict=True)}


class Analysis(unittest.TestCase):
    def test_holm_and_the_margin(self):
        cells = {f"k{n}": cell({"OMPF": (0, 0), "DSHF": (1, 1), "DSH": (1, 1)}) for n in range(30)}
        spec = {"M1": ["OMPF", "DSHF"], "M2": ["DSHF", "DSH"]}
        blocks = ana.questions(list(cells), cells, spec, "correct")
        rules = ana.rules(blocks, spec, 0.05, 2.24, ["M1"])
        self.assertTrue(rules["M1"]["left_worse"])
        self.assertEqual(rules["M2"]["reading"], "no clear difference between DSHF and DSH")
        small = {f"k{n}": cell({"OMPF": (1, 1) if n else (0, 1), "DSHF": (1, 1), "DSH": (1, 1)}) for n in range(30)}
        rules = ana.rules(ana.questions(list(small), small, spec, "correct"), spec, 0.05, 2.24, ["M1"])
        self.assertFalse(rules["M1"]["left_worse"])  # a 1.7-point gap stays inside the margin

    def test_a_question_that_misses_items_fails(self):
        cells = {"k1": cell({"OMPF": (1, 1), "DSHF": (1, 1)}), "k2": cell({"DSHF": (1, 1)})}
        with self.assertRaises(SystemExit):
            ana.questions(["k1", "k2"], cells, {"M1": ["OMPF", "DSHF"]}, "correct")

    def test_span_scores_use_token_f1(self):
        cells = {"k1": cell({"DSHF": (1.0, 0.5), "C": (0.0, 0.0)}, "token_f1")}
        block = ana.compare(["k1"], cells, "DSHF", "C", "token_f1")
        self.assertEqual((block["DSHF"], block["C"]), (75.0, 0.0))

    def test_a_changed_reference_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.jsonl"
            path.write_text("{}\n", encoding="utf-8")
            protocol = {"reference": {"mc112_scores": {"card": "MC-112", "path": "scores.jsonl", "sha256": "0" * 64}}}
            with self.assertRaises(SystemExit):
                ana.load_reference(protocol, "mc112_scores", Path(tmp))


if __name__ == "__main__":
    unittest.main()
