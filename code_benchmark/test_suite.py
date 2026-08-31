import random
import tempfile
import unittest
from pathlib import Path
from collections import Counter
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
from code_benchmark.make_eval_sample import (
    allocate,
    sample_strata,
    passage_ids,
    primary_category,
    squad_stratum,
    build_manifest,
    DROP_PINNED,
    PASSAGE_CAP,
    SQUAD_INFER_FLOOR,
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
            assert latest is not None  # narrows Path|None for pd.read_csv
            cp_df = pd.read_csv(latest)
            self.assertEqual(len(cp_df), 2)
            self.assertEqual(cp_df.iloc[0]["answer"], "A")
            self.assertEqual(cp_df.iloc[1]["answer"], "B")

class TestSubjectCategoryMap(unittest.TestCase):
    def test_official_numbering_shape(self):
        self.assertEqual(len(SUBJECTS), 58)
        self.assertEqual(set(SUBJECTS), set(range(1, 59)))
        by_cat = {}
        for num, (_subject_name, cat) in SUBJECTS.items():
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


def _synth_squad(n_passages=60, words=100):
    """Synthetic SQuAD-like rows: 2 questions per passage (one direct, one
    inference), context sized so the caller picks the length bucket."""
    rows, rid = [], 0
    for p in range(n_passages):
        ctx = " ".join(f"từ{p}_{i}" for i in range(words))
        rows.append({"id": rid, "question": "Ai là người X?", "context": ctx}); rid += 1
        rows.append({"id": rid, "question": "Tại sao X xảy ra?", "context": ctx}); rid += 1
    return rows


class TestAllocate(unittest.TestCase):
    def test_largest_remainder_sums_to_total(self):
        w = {"a": 1001, "b": 979, "c": 732, "d": 471, "e": 126}
        q = allocate(w, 200)
        self.assertEqual(sum(q.values()), 200)
        # all five strata represented (no silent zero from 126/3309*200~7.6)
        self.assertEqual(set(q), set(w))

    def test_pinned_excluded_from_redistribution(self):
        w = {"count": 471, "add_sub": 979, "comparison": 1001}
        q = allocate(w, 200, pinned=DROP_PINNED)
        self.assertEqual(q["count"], 40)
        self.assertEqual(sum(q.values()), 200)
        # free strata split 160 proportionally to each other
        self.assertEqual(q["comparison"] + q["add_sub"], 160)

    def test_pinned_over_total_raises(self):
        with self.assertRaises(ValueError):
            allocate({"a": 10}, 5, pinned={"b": 6})

    def test_deterministic_tiebreak(self):
        w = {"zz": 10, "aa": 10, "mm": 10}
        self.assertEqual(allocate(w, 7), allocate(w, 7))


class TestStratumFns(unittest.TestCase):
    def test_primary_category_normalizes(self):
        self.assertEqual(primary_category("comparison1,add_sub"), "comparison")
        self.assertEqual(primary_category("add_sub"), "add_sub")
        self.assertEqual(primary_category("count,comparison"), "count")

    def test_squad_stratum_buckets_and_cues(self):
        short_direct = {"context": "x " * 50, "question": "Ai là ai?"}
        long_infer = {"context": "x " * 600, "question": "Tại sao lại như vậy?"}
        self.assertEqual(squad_stratum(short_direct), "short-direct")
        self.assertEqual(squad_stratum(long_infer), "long-infer")


class TestSampleStrata(unittest.TestCase):
    def test_quota_met_and_reproducible(self):
        rows = _synth_squad()  # 100-word contexts -> short bucket only
        pid = passage_ids(rows)
        fn = squad_stratum
        quotas = {"short-direct": 15, "short-infer": 15}
        a = sample_strata(rows, quotas, fn, random.Random(42), passage_cap=PASSAGE_CAP, pid=pid)
        b = sample_strata(rows, quotas, fn, random.Random(42), passage_cap=PASSAGE_CAP, pid=pid)
        self.assertEqual([x["id"] for x in a], [x["id"] for x in b])  # same seed -> same draw
        self.assertEqual(Counter(map(fn, a)), quotas)

    def test_passage_cap_respected_with_two_per_passage_pool(self):
        rows = _synth_squad()  # every passage has exactly 2 questions, both strata differ
        pid = passage_ids(rows)
        quotas = {"short-direct": 20}
        got = sample_strata(rows, quotas, squad_stratum, random.Random(1),
                            passage_cap=1, pid=pid)
        self.assertEqual(len(got), 20)
        self.assertLessEqual(max(Counter(pid[str(r["context"])] for r in got).values()), 1)

    def test_starved_stratum_refilled_without_overshooting(self):
        # 4 short passages (1q each), 1 long (>400 words) passage with 4 questions, cap 2
        big = " ".join(f"w{i}" for i in range(500))
        rows = ([{"id": i, "question": "q", "context": f"w{i}"} for i in range(4)]
                + [{"id": 10 + i, "question": "q", "context": big} for i in range(4)])
        pid = passage_ids(rows)
        quotas = {"short-direct": 2, "long-direct": 2}
        got = sample_strata(rows, quotas, squad_stratum, random.Random(3),
                            passage_cap=PASSAGE_CAP, pid=pid)
        self.assertEqual(Counter(squad_stratum(r) for r in got), quotas)
        self.assertEqual(len({id(r) for r in got}), 4)  # no duplicates

    def test_missing_stratum_raises(self):
        rows = _synth_squad(n_passages=3)
        with self.assertRaises(ValueError):
            sample_strata(rows, {"nope-stratum": 1}, squad_stratum, random.Random(0))


class TestBuildManifest(unittest.TestCase):
    def test_shape_caps_and_empty_gold(self):
        # half short (100w), half long (500w) passages -> 4 strata: short/long x direct/infer
        squad = _synth_squad(n_passages=60, words=100) + _synth_squad(n_passages=60, words=500)
        for i, r in enumerate(squad):  # unique ids across the two halves
            r["id"] = i
        drop = [{"question_id": i, "category": c, "context": f"c{i} text", "question": "q?"}
                for i, c in enumerate(["count", "add_sub", "comparison", "selection", "other"] * 40)]
        rows = build_manifest(squad, drop, seed=42, n_each=60)
        self.assertEqual(len(rows), 120)
        self.assertTrue(all(r["gold_answer"] == "" for r in rows))
        by_ds = Counter(r["dataset"] for r in rows)
        self.assertEqual(by_ds, {"squad": 60, "drop": 60})
        sq = [r for r in rows if r["dataset"] == "squad"]
        self.assertLessEqual(max(Counter(r["passage_id"] for r in sq).values()), PASSAGE_CAP)
        # every infer stratum pinned to the floor (fixture spans 2 infer cells:
        # short-infer + long-infer; no mid contexts in the synthetic data)
        self.assertEqual(sum(1 for r in sq if r["stratum"].endswith("-infer")), 2 * SQUAD_INFER_FLOOR)
        # DROP count oversample survives end-to-end
        dr = [r for r in rows if r["dataset"] == "drop"]
        self.assertEqual(Counter(r["stratum"] for r in dr)["count"],
                         min(DROP_PINNED["count"], len(dr)))

    def test_manifest_reproducible_bytes(self):
        squad = _synth_squad(n_passages=80)
        drop = [{"question_id": i, "category": c, "context": f"c{i}", "question": "q?"}
                for i, c in enumerate(["add_sub", "count"] * 100)]
        a = build_manifest(squad, drop, seed=42, n_each=50)
        b = build_manifest(squad, drop, seed=42, n_each=50)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
