import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
from openai import AuthenticationError

from code_benchmark.test_ollama import (
    call_model_with_retry,
    build_prompt,
    extract_answer,
    find_latest_checkpoint,
    verify_credentials,
    parse_args
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
            self.assertEqual(latest.name, "raw_result_500.csv")

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

if __name__ == "__main__":
    unittest.main()
