"""Guard against publishing comparisons across unknown controls or withheld gold."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import vi_multimodel as v1
from code_benchmark.build_benchmark_reports import (card_index, comments_for, reading_means, reading_v3_rows,
                                                    redact_hosts, row, signature, validate, vbench_scores)
from code_benchmark.score_vi_multimodel import clustered_mean_interval


class TestReportComparability(unittest.TestCase):
    def controls(self) -> dict:
        return {"omp_version": "omp/18.0.0", "omp_mode": "json", "omp_tools": "none",
                "omp_system_prompt": "Answer the user's question.", "omp_thinking": "auto", "omp_reasoning": True,
                "temperature_effective": 1.0, "workers": 4, "omp_max_time_seconds": 300,
                "omp_session_policy": "one process per item", "sdk_retries": 0, "seed_sent": False,
                "manifest_sha256": "manifest"}

    def test_changed_controls_never_share_signature(self):
        base = self.controls(); caps = {"multiple_choice": 4096}
        expected = signature(base, caps)
        self.assertIsNotNone(expected)
        for key, value in {"omp_thinking": "off", "temperature_effective": 0, "omp_tools": "all",
                           "workers": 6, "omp_session_policy": "persistent", "manifest_sha256": "different"}.items():
            with self.subTest(key=key):
                self.assertNotEqual(expected, signature({**base, key: value}, caps))
        self.assertNotEqual(expected, signature(base, {"multiple_choice": 2048}))

    def test_unknown_controls_do_not_create_comparison(self):
        for key in self.controls():
            control = self.controls(); control.pop(key)
            self.assertIsNone(signature(control, {"multiple_choice": 4096}), key)

    def test_seed_sample_is_not_inference_seed(self):
        base = self.controls(); base["seed_requested"] = 42
        caps = {"multiple_choice": 4096}
        omitted = signature(base, caps)
        self.assertEqual(omitted, signature({**base, "seed_requested": 43}, caps))
        self.assertNotEqual(omitted, signature({**base, "seed_sent": True}, caps))
        self.assertIsNone(signature({**base, "seed_sent": True, "seed_requested": None}, caps))
        self.assertIsNone(signature(base, {}))

    def test_card_table_keys_are_normalized_without_example_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "measurement_card.md").write_text("## MC-1 — run\n| `temperature` / `seed` | 0 / 42 |\n| `example` | distractor | third cell |\n", encoding="utf-8")
            fields = card_index(root)["MC-1"]["fields"]
            self.assertEqual(fields["temperature / seed"], "0 / 42")
            self.assertNotIn("example", fields)

    def report(self, metric: dict) -> dict:
        return {"id": "test", "conditions": [{"id": "c", "model": "m", "comparison_group": None}], "benchmarks": [metric]}

    def test_server_grade_preserves_unknown_counts_and_ci(self):
        metric = row("c", "test", "VMLU Test", "server_accuracy", 63.86, n=9833, gold="withheld")
        validate(self.report(metric))
        self.assertIsNone(metric["correct"])
        self.assertIsNone(metric["ci_low"])
        for key in ("correct", "ci_low", "ci_high"):
            with self.subTest(key=key), self.assertRaises(SystemExit):
                validate(self.report({**metric, key: 1}))

    def test_schema_validity_is_not_semantic_accuracy(self):
        metric = row("c", "agentic", "Agentic", "accuracy", 99, n=1000, gold="withheld")
        with self.assertRaises(SystemExit): validate(self.report(metric))
        diagnostic = row("c", "agentic", "Agentic", "valid_rate", 99, n=1000, gold="none")
        validate(self.report(diagnostic))

    def test_delta_ci_cannot_be_attached_to_point_score(self):
        metric = row("c", "legal", "Legal MC", "accuracy", 73.29, n=146, delta=-15.75, delta_ci=[-22, -9])
        self.assertIsNone(metric["ci_low"])
        self.assertEqual(metric["delta_ci_low"], -22)

    def test_macro_is_not_item_weighted_micro_or_an_accuracy_numerator(self):
        records = [{"track": "mc", "domain": "small", "score": 100, "correct": 1, "total": 1},
                   {"track": "mc", "domain": "large", "score": 0, "correct": 0, "total": 9}]
        scores = vbench_scores("c", "vb", records, "source.csv")
        self.assertEqual(scores[0]["score"], 10)
        self.assertEqual(scores[1]["score"], 50)
        self.assertEqual(scores[1]["metric"], "server_macro")
        self.assertIsNone(scores[1]["n"])
        self.assertIsNone(scores[1]["correct"])

    def test_comments_do_not_compare_singletons_or_unequal_denominators(self):
        conditions = [{"id": "a", "model": "a", "comparison_group": "g"}, {"id": "b", "model": "b", "comparison_group": None}]
        scores = [row("a", "d", "dataset", "accuracy", 80, n=100), row("b", "d", "dataset", "accuracy", 99, n=100)]
        report = {"conditions": conditions, "benchmarks": scores}
        self.assertFalse(any("chênh" in c for c in comments_for(report)))
        conditions[1]["comparison_group"] = "g"; scores[1]["n"] = 200
        self.assertFalse(any("chênh" in c for c in comments_for(report)))


class TestReadingV3Rows(unittest.TestCase):
    """v3 rows sit beside the v2 score they re-score and fail closed on any other file."""

    def scored(self, answer: str, gold: str, item: str) -> dict:
        return {"dataset_id": "d", "item_id": item, "replicate_id": "main-000", "passage_id": f"p{item}",
                "gold_answer": gold, "raw_response": answer, **v1.score_vi_reading(v1.extract_final_answer(answer), gold)}

    def report(self, rows: list[dict], *, n: int | None = None) -> dict:
        means = reading_means(rows)
        ci = clustered_mean_interval(rows, value_key="token_f1", cluster_key="passage_id")
        source = "run/summary.json"
        return {"conditions": [{"id": "c", "sources": [{"path": "run/run.json", "label": "Run metadata"}]}],
                "benchmarks": [row("c", "d", "D", "token_f1", means["token_f1"], n=n or len(rows), ci=list(ci), source_path=source),
                               row("c", "d", "D", "em", means["em"], n=n or len(rows), source_path=source),
                               row("c", "d", "D", "accuracy", 50, n=len(rows), source_path=source)]}

    def test_v3_rows_rescore_bolded_answers_and_keep_v2(self):
        rows = [self.scored("**từ 20% đến 30%**", "từ 20% đến 30%", "1"), self.scored("Hà Nội", "Hà Nội", "2")]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "run").mkdir()
            (Path(tmp) / "run/scores.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
            added = {r["metric"]: r for r in reading_v3_rows(Path(tmp), self.report(rows), {})}
            self.assertEqual(set(added), {"em_v3", "token_f1_v3"})
            self.assertEqual((added["em_v3"]["score"], added["token_f1_v3"]["score"]), (100.0, 100.0))
            self.assertEqual(added["token_f1_v3"]["source"], "run/scores.jsonl")
            with self.assertRaises(SystemExit):
                reading_v3_rows(Path(tmp), self.report(rows, n=3), {})

    def test_scores_without_per_item_rows_get_no_v3(self):
        rows = [self.scored("Hà Nội", "Hà Nội", "1")]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(reading_v3_rows(Path(tmp), self.report(rows), {}), [])


class TestPublishedHosts(unittest.TestCase):
    def test_internal_endpoint_hosts_are_redacted_at_any_depth(self):
        data = {"fields": {"provider": "IEC internal endpoint · openai-completions · llmapi.iec",
                           "history": "Qwen3.5-9B-65K @ https://llmapi.iec-uit.com/v1 — node offline"},
                "notes": ["proxy 127.0.0.1:8799 → llmapi.iec", "9ROUTER / CMC · localhost:20128"], "n": 3}
        self.assertEqual(redact_hosts(data), {
            "fields": {"provider": "IEC internal endpoint · openai-completions · IEC (host ẩn)",
                       "history": "Qwen3.5-9B-65K @ IEC (host ẩn) — node offline"},
            "notes": ["proxy 127.0.0.1:8799 → IEC (host ẩn)", "9ROUTER / CMC · localhost:20128"], "n": 3})


if __name__ == "__main__": unittest.main()
