import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd

from code_benchmark.test_ollama import (
    call_model_with_retry,
    build_prompt,
    extract_answer,
    find_latest_checkpoint,
    SUBJECTS,
    subject_category,
    detect_scorable,
    score_row,
    build_accuracy_rows,
)

class TestVMLUBenchmark(unittest.TestCase):

    def test_extract_answer_accuracy(self):
        cases = [
            ('A', 'A'),
            ('A.', 'A'),
            ('b)', 'B'),
            ('(C)', 'C'),
            ('**D**', 'D'),
            ('Đáp án là B.', 'B'),
            ('Đáp án: C', 'C'),
            ('Chọn đáp án D', 'D'),
            ('The correct answer is E.', 'E'),
            ('Option A is correct', 'A'),
            ('Câu hỏi này đáp án là B', 'B'),
            ('Kết quả: D', 'D'),
            ('The choice is (C)', 'C'),
            ('Không có đáp án đúng trong các lựa chọn', ''),
            ('Tôi không biết câu trả lời này', ''),
            ('Hãy giải thích chi tiết câu này', ''),
            ('', ''),
        ]
        for raw, expected in cases:
            self.assertEqual(extract_answer(raw), expected, f"Failed for raw input: '{raw}'")

    def test_build_prompt_format(self):
        q = "Thủ đô của Việt Nam là gì?"
        choices = ["A. Hà Nội", "B. TP. Hồ Chí Minh", "C. Đà Nẵng", "D. Hải Phòng"]
        p = build_prompt(q, choices)
        self.assertIn("Chỉ đưa ra chữ cái đứng trước câu trả lời đúng", p)
        self.assertIn("A. Hà Nội\nB. TP. Hồ Chí Minh\nC. Đà Nẵng\nD. Hải Phòng", p)
        self.assertTrue(p.endswith("Đáp án: "))

    def test_call_model_retry_exhaustion(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Transient connection failure")
        res = call_model_with_retry(
            client=mock_client,
            model="test_model",
            prompt="test",
            temperature=0.0,
            seed=42,
            max_tokens=4,
            max_retries=3,
            sleep_sec=0
        )
        self.assertEqual(res, "")
        self.assertEqual(mock_client.chat.completions.create.call_count, 3)

    def test_call_model_fail_fast_auth(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized: Invalid API key")
        with self.assertRaises(Exception) as ctx:
            call_model_with_retry(
                client=mock_client,
                model="test_model",
                prompt="test",
                temperature=0.0,
                seed=42,
                max_tokens=4,
                max_retries=5,
                sleep_sec=0
            )
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)

    def test_find_latest_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "raw_result_100.csv").touch()
            (tmppath / "raw_result_500.csv").touch()
            (tmppath / "raw_result_200.csv").touch()
            latest = find_latest_checkpoint(tmppath)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.name if latest else None, "raw_result_500.csv")

    def test_checkpoint_resume_simulation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            cp_file = tmppath / "raw_result_2.csv"
            df = pd.DataFrame([
                {"id": "01-0001", "question": "Q1", "prompt": "P1", "raw_response": "A", "answer": "A"},
                {"id": "01-0002", "question": "Q2", "prompt": "P2", "raw_response": "B", "answer": "B"},
            ])
            df.to_csv(cp_file, index=False)
            
            latest = find_latest_checkpoint(tmppath)
            self.assertEqual(latest, cp_file)
            cp_df = pd.read_csv(latest)
            self.assertEqual(len(cp_df), 2)
            self.assertEqual(cp_df.iloc[0]["answer"], "A")
            self.assertEqual(cp_df.iloc[1]["answer"], "B")

class TestSubjectCategoryMap(unittest.TestCase):
    def test_official_numbering_shape(self):
        self.assertEqual(len(SUBJECTS), 58)
        self.assertEqual(set(SUBJECTS), set(range(1, 59)))
        by_cat = {}
        for num, (_name, cat) in SUBJECTS.items():
            by_cat.setdefault(cat, []).append(num)
        # official README: 01-21 STEM, 22-31 Social Science, 32-49 Humanity, 50-58 Other
        self.assertEqual(sorted(by_cat), ["Humanity", "Other", "STEM", "Social Science"])
        self.assertEqual(len(by_cat["STEM"]), 21)
        self.assertEqual(len(by_cat["Social Science"]), 10)
        self.assertEqual(len(by_cat["Humanity"]), 18)
        self.assertEqual(len(by_cat["Other"]), 9)

    def test_spot_checks_against_real_records(self):
        # 28-0001 in dev.jsonl is a macroeconomics question; 15-0001 an EE one
        self.assertEqual(subject_category("28-0001"), (28, "Macroeconomics", "Social Science"))
        self.assertEqual(subject_category("15-0001"), (15, "Electrical Engineering", "STEM"))
        self.assertEqual(subject_category("39-0001"), (39, "Civil Law", "Humanity"))
        self.assertEqual(subject_category("51-0001"), (51, "Clinical Pharmacology", "Other"))

    def test_unknown_bucket(self):
        self.assertEqual(subject_category("99-0001"), (99, "unknown", "unknown"))
        self.assertEqual(subject_category("garbage"), (None, "unknown", "unknown"))


class TestDetectScorable(unittest.TestCase):
    def test_all_gold_scorable(self):
        recs = [{"id": "01-0001", "answer": "A"}, {"id": "01-0002", "answer": "b"}]
        ok, gold = detect_scorable(recs)
        self.assertTrue(ok)
        self.assertEqual(gold, {"01-0001": "A", "01-0002": "B"})  # uppercased

    def test_no_gold_non_scorable(self):
        recs = [{"id": "01-0001"}, {"id": "01-0002"}]
        self.assertEqual(detect_scorable(recs), (False, {}))

    def test_mixed_non_scorable(self):
        recs = [{"id": "01-0001", "answer": "A"}, {"id": "01-0002"}]
        self.assertEqual(detect_scorable(recs), (False, {}))

    def test_empty_string_gold_non_scorable(self):
        recs = [{"id": "01-0001", "answer": "A"}, {"id": "01-0002", "answer": "  "}]
        self.assertEqual(detect_scorable(recs), (False, {}))


class TestScoring(unittest.TestCase):
    def test_score_row_match_mismatch_empty(self):
        gold = {"1": "B", "2": "A", "3": "C"}
        self.assertEqual(score_row({"id": "1", "answer": "b"}, gold)["correct"], 1)  # case-insensitive
        self.assertEqual(score_row({"id": "2", "answer": "D"}, gold)["correct"], 0)
        r = score_row({"id": "3", "answer": ""}, gold)
        self.assertEqual(r["correct"], 0)
        self.assertEqual(r["gold_answer"], "C")  # gold kept for audit

    def test_accuracy_partition_sums_to_total(self):
        gold = {f"01-000{i}": "A" for i in range(1, 5)}
        rows = [
            score_row({"id": "01-0001", "answer": "A"}, gold),
            score_row({"id": "01-0002", "answer": "B"}, gold),
            score_row({"id": "28-0001", "answer": "C"}, {**gold, "28-0001": "C"}),
            score_row({"id": "99-0001", "answer": "A"}, {**gold, "99-0001": "A"}),  # unknown subject
        ]
        acc = build_accuracy_rows(rows)
        overall = acc[0]
        # 01-0001 match, 01-0002 mismatch, 28-0001 match, 99-0001 match -> 3/4
        self.assertEqual((overall["level"], overall["n"], overall["correct"]), ("overall", 4, 3))
        cats = {r["name"]: r["n"] for r in acc if r["level"] == "category"}
        self.assertEqual(sum(cats.values()), 4)          # categories partition total
        self.assertEqual(cats.get("unknown"), 1)          # bad prefix not silently dropped
        subjects = [r for r in acc if r["level"] == "subject"]
        self.assertEqual(sum(r["n"] for r in subjects), 4)

    def test_resume_from_pre_scoring_checkpoint(self):
        # checkpoint style written BEFORE scoring existed: no gold_answer/correct columns
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            cp = tmppath / "raw_result_2.csv"
            pd.DataFrame([
                {"id": "01-0001", "question": "Q", "prompt": "P", "raw_response": "A", "answer": "A"},
                {"id": "01-0002", "question": "Q", "prompt": "P", "raw_response": "B", "answer": "B"},
            ]).to_csv(cp, index=False)
            cp_df = pd.read_csv(cp)
            merged = []
            for _, row in cp_df.iterrows():  # resume path in main(): plain dict from checkpoint
                merged.append({"id": str(row["id"]), "question": row.get("question", ""),
                               "prompt": row.get("prompt", ""), "raw_response": row.get("raw_response", ""),
                               "answer": str(row["answer"])})
            merged.append({"id": "01-0003", "question": "Q", "prompt": "P", "raw_response": "C", "answer": "C"})
            gold = {"01-0001": "A", "01-0002": "A", "01-0003": "C"}
            acc = build_accuracy_rows([score_row(r, gold) for r in merged])  # end-of-run recompute
            overall = acc[0]
            self.assertEqual((overall["n"], overall["correct"]), (3, 2))

    def test_build_prompt_and_extract_contract_unchanged(self):
        # scoring change must not touch the frozen prompt contract
        p = build_prompt("Q?", ["A. x", "B. y"])
        self.assertTrue(p.startswith("Chỉ đưa ra chữ cái đứng trước câu trả lời đúng"))
        self.assertTrue(p.endswith("Đáp án: "))
        self.assertEqual(extract_answer("B"), "B")


if __name__ == "__main__":
    unittest.main()
