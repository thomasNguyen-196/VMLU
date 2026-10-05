import argparse
import csv
import json
import random
import re
import shutil
import subprocess  # nosec B404 — test harness shells out to local CLI/node only
import hashlib
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from collections import Counter
from unittest.mock import MagicMock
import pandas as pd

from code_benchmark.run_mc_eval import (
    build_prompt,
    extract_answer,
    SUBJECTS,
    subject_category,
    detect_scorable,
    score_row,
    build_accuracy_rows,
)
from code_benchmark.llm import call_model_with_retry
from code_benchmark.checkpoint import find_latest_checkpoint
from code_benchmark.common import item_key, split_item_key, sanitize_model
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
from code_benchmark.run_reading_eval import (
    build_reading_prompt,
    join_manifest,
    index_sources,
    resume_key,
    find_latest_reading_checkpoint,
)
from code_benchmark.run_bidlqa_eval import (
    split_config,
    load_source,
    build_manifest_rows,
    verify_join,
)
from code_benchmark.run_vbench_eval import (
    classify_track as vb_classify_track,
    extract_mc_answer as vb_extract_mc_answer,
    extract_function_call as vb_extract_function_call,
    build_agentic_prompt as vb_build_agentic_prompt,
    build_submission_rows as vb_build_submission_rows,
    diagnose_rejection as vb_diagnose_rejection,
    grade_agentic_args as vb_grade_agentic_args,
    parse_choice as vb_parse_choice,
    parse_value as vb_parse_value,
    guided_call as vb_guided_call,
    load_checkpoint as vb_load_checkpoint,
    CHECKPOINT_COLS as VB_CHECKPOINT_COLS,
    build_valid_summary as vb_build_valid_summary,
    read_server_scores as vb_read_server_scores,
    write_server_snapshot as vb_write_server_snapshot,
    measurement_card_hash as vb_measurement_card_hash,
    VALID_SUMMARY_COLS as VB_VALID_SUMMARY_COLS,
    SERVER_SCORES_COLS as VB_SERVER_SCORES_COLS,
)
from code_benchmark.export_annotation_workbooks import (
    merge_answers,
    normalize_answer,
    workbook_rows,
    REVIEW_COLS,
    read_review,
    gold_from_reviews,
    gold_from_split,
    review_stats,
    apply_gold,
    cmd_merge_split,
)
from code_benchmark.build_review_ui import (
    build_blob,
    model_from_filename,
    load_answers_csv,
    review_items,
    embed_json,
    render_html,
)
from code_benchmark.seed_registries import (
    canonical_model_id,
    make_run_id,
    seed,
)
from code_benchmark import run_harness_eval as harness
from code_benchmark import build_dashboard_harness as dash
from code_benchmark import capture_scaffold as scaffold
from code_benchmark import llm
from code_benchmark import run_legal_arm_a as legal_arm_a
from code_benchmark import make_shuffled_mc_input as shuffled_mc
from code_benchmark import run_shuffled_mc as shuffled_run
from code_benchmark import compare_position_bias as posbias
from code_benchmark import run_reading_cite_eval as cite
from code_benchmark import judge_faithfulness as judge
from code_benchmark import label_faithfulness as labeler
from code_benchmark import run_mc_calibration_eval as cal
from code_benchmark.score_reading_eval import read_csv_rows
from code_benchmark.migrate_results_to_mongo import (
    migrate,
    mc_item,
    vbench_item,
    reading_item,
    MIGRATION_PLAN,
    runner_config,
    accuracy_summary_rows,
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
            (tmppath / "raw_result_100_Qwen.csv").touch()
            (tmppath / "raw_result_500_Qwen.csv").touch()
            (tmppath / "raw_result_200_Other.csv").touch()
            (tmppath / "raw_result_300.csv").touch()      # legacy: no model identity
            latest = find_latest_checkpoint(tmppath, "Qwen")
            self.assertEqual(latest.name if latest else None, "raw_result_500_Qwen.csv")
            self.assertIsNone(find_latest_checkpoint(tmppath, "Mistral"))

    def test_checkpoint_resume_simulation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            cp_file = tmppath / "raw_result_2_Qwen.csv"
            df = pd.DataFrame([
                {"id": "01-0001", "question": "Q1", "prompt": "P1", "raw_response": "A", "answer": "A"},
                {"id": "01-0002", "question": "Q2", "prompt": "P2", "raw_response": "B", "answer": "B"},
            ])
            df.to_csv(cp_file, index=False)
            
            latest = find_latest_checkpoint(tmppath, "Qwen")
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


class TestCommonHelpers(unittest.TestCase):
    """Shared-kernel contracts extracted from the runners' duplicates."""

    def test_item_key_round_trip(self):
        row = {"dataset": "squad", "item_id": 7}
        k = item_key(row)
        self.assertEqual(k, "squad:7")
        self.assertEqual(split_item_key(k), ("squad", "7"))

    def test_item_key_splits_on_first_colon_only(self):
        # item_ids never contain colons, but the rule is partition(":") — pin it
        self.assertEqual(split_item_key("drop:12:30"), ("drop", "12:30"))

    def test_sanitize_model_matches_legacy_regex(self):
        self.assertEqual(sanitize_model("Qwen3/8:27B-Q4_K_M.gguf"),
                         "Qwen3_8_27B-Q4_K_M_gguf")

    def test_checkpoint_regex_follows_prefix_constant(self):
        # the old reading runner hardcoded "reading_result_" in its regex while
        # globbing by the constant — renaming the prefix silently broke resume
        from code_benchmark import checkpoint as ckpt
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "custom_10_Qwen.csv").touch()
            (t / "custom_99_Qwen.csv").touch()
            latest = ckpt.find_latest_checkpoint(t, "Qwen", prefix="custom_")
            self.assertEqual(latest.name, "custom_99_Qwen.csv")
            # other prefixes never bleed in
            self.assertIsNone(ckpt.find_latest_checkpoint(t, "Qwen", prefix="raw_result_"))


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


class TestReadingRunner(unittest.TestCase):
    def test_prompt_contract(self):
        p = build_reading_prompt("Đoạn văn về Hà Nội.", "Thủ đô là gì?")
        self.assertIn("Đoạn văn về Hà Nội.", p)
        self.assertIn("Câu hỏi: Thủ đô là gì?", p)
        self.assertTrue(p.endswith("Trả lời: "))

    def _sources(self, tmp: Path):
        squad = tmp / "sq.json"
        drop = tmp / "dr.json"
        squad.write_text(json.dumps({"data": [
            {"id": 7, "question": "Q7?", "context": "ctx seven"}]}), encoding="utf-8")
        drop.write_text(json.dumps({"data": [
            {"question_id": 30, "question": "Q30?", "context": "ctx thirty",
             "category": "count"}]}), encoding="utf-8")
        return squad, drop

    def test_join_attaches_context_and_keys(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            squad, drop = self._sources(tmp)
            idx = index_sources(squad, drop)
            manifest = [{"dataset": "squad", "item_id": "7", "stratum": "s",
                         "question": "Q7?"},
                        {"dataset": "drop", "item_id": "30", "stratum": "count",
                         "question": "Q30?"}]
            joined = join_manifest(manifest, idx)
            self.assertEqual([j["context"] for j in joined], ["ctx seven", "ctx thirty"])
            self.assertEqual({resume_key(j) for j in joined}, {"squad:7", "drop:30"})

    def test_join_failfast_on_drift_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            squad, drop = self._sources(tmp)
            idx = index_sources(squad, drop)
            bad_q = [{"dataset": "squad", "item_id": "7", "stratum": "s",
                      "question": "tampered?"}]
            with self.assertRaises(SystemExit):
                join_manifest(bad_q, idx)
            missing = [{"dataset": "drop", "item_id": "999", "stratum": "c",
                        "question": "Q?"}]
            with self.assertRaises(SystemExit):
                join_manifest(missing, idx)

    def test_reading_checkpoint_never_picks_mc_checkpoints(self):
        # MC raw_result_*.csv files must NOT be candidates for resume, and the
        # checkpoint namespace is per-model: another model's or legacy files are ignored
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "raw_result_1047.csv").touch()
            (tmp / "reading_result_100.csv").touch()          # legacy: no model identity
            (tmp / "reading_result_100_Qwen.csv").touch()
            (tmp / "reading_result_400_Qwen.csv").touch()
            (tmp / "reading_result_300_Mistral.csv").touch()
            latest = find_latest_reading_checkpoint(tmp, "Qwen")
            assert latest is not None
            self.assertEqual(latest.name, "reading_result_400_Qwen.csv")
            (tmp / "raw_result_9999.csv").touch()
            latest = find_latest_reading_checkpoint(tmp, "Qwen")
            assert latest is not None
            self.assertEqual(latest.name, "reading_result_400_Qwen.csv")  # still ignores MC
            self.assertIsNone(find_latest_reading_checkpoint(tmp, "TESTMODELSMOKE"))  # legacy ignored
class TestBidlqaRunner(unittest.TestCase):
    def _source(self, tmp: Path, n: int = 3):
        p = tmp / "bidlqa.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for i in range(1, n + 1):
                f.write(json.dumps({"context": f"ctx {i}", "question": f"Q{i}?",
                                    "answer": f"A{i}"}, ensure_ascii=False) + "\n")
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        return p, digest

    def test_split_config_pins_known_splits(self):
        val = split_config("val")
        test = split_config("test")
        self.assertEqual((val["n"], val["id_prefix"]), (482, "BIDLQA-V"))
        self.assertEqual((test["n"], test["id_prefix"]), (603, "BIDLQA-T"))
        self.assertNotEqual(val["sha"], test["sha"])
        self.assertNotEqual(val["ckpt_prefix"], test["ckpt_prefix"])
        with self.assertRaises(SystemExit):
            split_config("train")

    def test_load_source_rejects_drift_and_empty(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p, digest = self._source(tmp)
            self.assertEqual(len(load_source(p, digest)), 3)
            with self.assertRaises(SystemExit):  # sha drift
                load_source(p, "0" * 64)
            p.write_text(json.dumps({"context": "c", "question": "q?",
                                     "answer": ""}) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):  # empty gold
                load_source(p, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_manifest_ids_stable_and_join_is_1to1(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p, digest = self._source(tmp)
            src = load_source(p, digest)
            for prefix in ("BIDLQA-V", "BIDLQA-T"):
                rows = build_manifest_rows(src, prefix)
                self.assertEqual([r["item_id"] for r in rows],
                                 [f"{prefix}-{i:04d}" for i in (1, 2, 3)])
                verify_join(rows, src, prefix)  # exact image passes
                bad = [dict(rows[0], question="tampered?"), *rows[1:]]
                with self.assertRaises(SystemExit):
                    verify_join(bad, src, prefix)


class TestBidlqaDashboard(unittest.TestCase):
    def _split_outputs(self, td: Path, split: str, n: int = 4):
        slug = f"bidlqa_{split}_M"
        answers = td / f"reading_answers_{slug}.csv"
        with open(answers, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["dataset", "item_id", "stratum", "question",
                                   "context_words", "raw_response"])
            w.writeheader()
            for i in range(n):
                w.writerow({"dataset": "bidlqa", "item_id": f"BIDLQA-{i:04d}",
                            "stratum": "auction", "question": f"q{i}",
                            "context_words": 9, "raw_response": f"a{i}"})
        scores = td / f"reading_scores_{slug}.csv"
        with open(scores, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["dataset", "item_id", "stratum", "gold_answer",
                                   "raw_response", "prediction", "em", "f1", "exact_raw"])
            w.writeheader()
            for i in range(n):
                w.writerow({"dataset": "bidlqa", "item_id": f"BIDLQA-{i:04d}",
                            "stratum": "auction", "gold_answer": f"a{i}",
                            "raw_response": f"a{i}", "prediction": f"a{i}",
                            "em": 1 if i % 2 == 0 else 0,
                            "f1": "1.000000" if i % 2 == 0 else "0.500000",
                            "exact_raw": 1 if i % 2 == 0 else 0})
        summary = td / f"reading_summary_{slug}.csv"
        with open(summary, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["dataset", "n", "em_count", "em", "char_f1",
                                   "exact_raw_count", "measurement_card_hash"])
            w.writeheader()
            w.writerow({"dataset": "ALL", "n": n, "em_count": n // 2, "em": "50.00",
                        "char_f1": "75.00", "exact_raw_count": n // 2, "measurement_card_hash": "h"})
        manifest = td / "manifest.csv"
        with open(manifest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["dataset", "item_id", "stratum", "passage_id",
                                   "question", "gold_answer"])
            w.writeheader()
            for i in range(n):
                w.writerow({"dataset": "bidlqa", "item_id": f"BIDLQA-{i:04d}",
                            "stratum": "auction", "passage_id": str(i),
                            "question": f"q{i}", "gold_answer": f"a{i}"})
        blob = td / "blob.json"
        blob.write_text(json.dumps({"vmlu": {"a": 1}, "legal": {"b": 2}}), encoding="utf-8")
        return answers, manifest, blob

    def _cli(self, *argv: str):
        from code_benchmark.build_dashboard_bidlqa import main as bidlqa_main
        import sys as _sys
        old = _sys.argv
        _sys.argv = ["build_dashboard_bidlqa.py", *argv]
        try:
            bidlqa_main()
            return 0
        finally:
            _sys.argv = old

    def test_patches_only_bidlqa_key(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            answers, manifest, blob = self._split_outputs(tmp, "val")
            self._cli("--dashboard", str(blob), "--split", "val",
                      "--answers", str(answers), "--manifest", str(manifest),
                      "--card", "MC-12", "--model-id", "M")
            out = json.loads(blob.read_text(encoding="utf-8"))
            self.assertEqual(out["vmlu"], {"a": 1})    # untouched
            self.assertEqual(out["legal"], {"b": 2})   # untouched
            self.assertEqual(out["bidlqa"]["val"]["overall"]["n"], 4)
            self.assertEqual(out["bidlqa"]["val"]["overall"]["em"], 50.0)
            self.assertEqual(out["bidlqa"]["val"]["measurement_card"], "MC-12")

    def test_summary_mismatch_and_id_drift_refuse(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            answers, manifest, blob = self._split_outputs(tmp, "val")
            with open(tmp / "reading_summary_bidlqa_val_M.csv", "w", newline="",
                       encoding="utf-8") as f:
                w = csv.DictWriter(f, ["dataset", "n", "em_count", "em", "char_f1",
                                       "exact_raw_count", "measurement_card_hash"])
                w.writeheader()
                w.writerow({"dataset": "ALL", "n": 4, "em_count": 4, "em": "100.00",
                            "char_f1": "100.00", "exact_raw_count": 4,
                            "measurement_card_hash": "h"})
            with self.assertRaises(SystemExit):
                self._cli("--dashboard", str(blob), "--split", "val",
                          "--answers", str(answers), "--manifest", str(manifest),
                          "--card", "MC-12")
            self.assertNotIn("bidlqa", json.loads(blob.read_text(encoding="utf-8")))
            with open(manifest, "a", encoding="utf-8") as f:  # extra gold row
                f.write("bidlqa,BIDLQA-9999,auction,99,qx,ax\n")
            with self.assertRaises(SystemExit):
                self._cli("--dashboard", str(blob), "--split", "val",
                          "--answers", str(answers), "--manifest", str(manifest),
                          "--card", "MC-12")


class TestVm14kDashboard(unittest.TestCase):
    def _vm14k_outputs(self, td: Path):
        full = td / "full_evaluation_vm14k_M.csv"
        with open(full, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["id", "question", "prompt", "raw_response",
                                   "answer", "gold_answer", "correct"])
            w.writeheader()
            rows = [
                ("id1", "A", "A", 1, "Easy", 4),
                ("id2", "B", "A", 0, "Easy", 4),
                ("id3", "B", "B", 1, "Medium", 2),
                ("id4", "A", "B", 0, "Medium", 2),
            ]
            for rid, ans, gold, corr, _diff, _nc in rows:
                w.writerow({"id": rid, "question": f"q-{rid}", "prompt": "p",
                            "raw_response": ans, "answer": ans,
                            "gold_answer": gold, "correct": corr})
        acc = td / "accuracy_vm14k_M.csv"
        with open(acc, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["level", "name", "n", "correct", "accuracy"])
            w.writeheader()
            w.writerow({"level": "overall", "name": "overall", "n": 4,
                        "correct": 2, "accuracy": "50.0"})
            w.writerow({"level": "category", "name": "unknown", "n": 4,
                        "correct": 2, "accuracy": "50.0"})
        manifest = td / "vm14k_manifest.json"
        manifest.write_text(json.dumps({
            "benchmark": "VM14K-test", "n": 4, "source_sha256": "s",
            "items": [
                {"id": "id1", "gold": "A", "n_choices": 4, "difficulty_level": "Easy",
                 "primary_topic": "Cardiology", "category": "Nội khoa"},
                {"id": "id2", "gold": "A", "n_choices": 4, "difficulty_level": "Easy",
                 "primary_topic": "Cardiology", "category": "Nội khoa"},
                {"id": "id3", "gold": "B", "n_choices": 2, "difficulty_level": "Medium",
                 "primary_topic": "Pediatrics", "category": "Sản – Nhi"},
                {"id": "id4", "gold": "B", "n_choices": 2, "difficulty_level": "Medium",
                 "primary_topic": "Pediatrics", "category": "Sản – Nhi"},
            ],
        }), encoding="utf-8")
        blob = td / "blob.json"
        blob.write_text(json.dumps({"vmlu": {"a": 1}, "legal": {"b": 2}}), encoding="utf-8")
        return full, manifest, blob

    def _cli(self, *argv: str):
        from code_benchmark.build_dashboard_vm14k import main as vm14k_main
        import sys as _sys
        old = _sys.argv
        _sys.argv = ["build_dashboard_vm14k.py", *argv]
        try:
            vm14k_main()
            return 0
        finally:
            _sys.argv = old

    def test_patches_only_vm14k_key(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            full, manifest, blob = self._vm14k_outputs(tmp)
            self._cli("--dashboard", str(blob), "--full", str(full),
                      "--manifest", str(manifest), "--card", "MC-14b",
                      "--model-id", "M")
            out = json.loads(blob.read_text(encoding="utf-8"))
            self.assertEqual(out["vmlu"], {"a": 1})    # untouched
            self.assertEqual(out["legal"], {"b": 2})   # untouched
            vm = out["vm14k"]
            self.assertEqual(vm["overall"], {"n": 4, "correct": 2, "accuracy": 50.0,
                                             "valid": 4, "blanks": 0, "wrong_parsed": 2})
            self.assertEqual(vm["baseline"]["majority_accuracy"], 50.0)
            self.assertEqual(vm["measurement_card"], "MC-14b")
            self.assertEqual(
                [(d["difficulty"], d["n"], d["correct"]) for d in vm["by_difficulty"]],
                [("Easy", 2, 1), ("Medium", 2, 1)])
            self.assertEqual(
                [(d["category"], d["n"], d["correct"]) for d in vm["by_category"]],
                [("Nội khoa", 2, 1), ("Sản – Nhi", 2, 1)])
            self.assertEqual(
                [(d["n_choices"], d["n"], d["correct"]) for d in vm["by_n_choices"]],
                [(2, 2, 1), (4, 2, 1)])

    def test_summary_mismatch_and_gold_drift_refuse(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            full, manifest, blob = self._vm14k_outputs(tmp)
            with open(tmp / "accuracy_vm14k_M.csv", "w", newline="",
                       encoding="utf-8") as f:
                w = csv.DictWriter(f, ["level", "name", "n", "correct", "accuracy"])
                w.writeheader()
                w.writerow({"level": "overall", "name": "overall", "n": 4,
                            "correct": 4, "accuracy": "100.0"})
            with self.assertRaises(SystemExit):
                self._cli("--dashboard", str(blob), "--full", str(full),
                          "--manifest", str(manifest), "--card", "MC-14b")
            self.assertNotIn("vm14k", json.loads(blob.read_text(encoding="utf-8")))
            man = json.loads(manifest.read_text(encoding="utf-8"))
            man["items"][0]["gold"] = "B"  # drift vs full gold_answer A
            manifest.write_text(json.dumps(man), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self._cli("--dashboard", str(blob), "--full", str(full),
                          "--manifest", str(manifest), "--card", "MC-14b")


class TestVm14kTaxonomy(unittest.TestCase):
    def test_every_category_value_is_ordered(self):
        from code_benchmark.vm14k_taxonomy import CATEGORY_ORDER, TAG_TO_CATEGORY, UNKNOWN
        self.assertIn(UNKNOWN, CATEGORY_ORDER)
        for tag, cat in TAG_TO_CATEGORY.items():
            self.assertIn(cat, CATEGORY_ORDER, msg=f"tag {tag!r} -> unordered {cat!r}")

    def test_category_of_primary_tag_and_junk(self):
        from code_benchmark.vm14k_taxonomy import category_of, UNKNOWN
        self.assertEqual(category_of(["Cardiology", "Radiology"]), "Nội khoa")
        self.assertEqual(category_of(["Pediatrics"]), "Sản – Nhi")
        self.assertEqual(category_of([]), UNKNOWN)
        self.assertEqual(category_of(None), UNKNOWN)
        self.assertEqual(category_of(["optionD"]), UNKNOWN)
        self.assertEqual(category_of([""]), UNKNOWN)

    def test_source_primary_tags_all_mapped_or_explicit_junk(self):
        import json as _json
        from code_benchmark.vm14k_taxonomy import TAG_TO_CATEGORY, UNKNOWN, category_of
        from pathlib import Path as _Path
        src = _Path(__file__).resolve().parent.parent / "v_med_vm14k" / "data-processed-shuffled0.jsonl"
        if not src.exists():
            self.skipTest("gitignored VM14K source absent")
        junk = {"", "optionD", "Classification", "Other(No Category)",
                '"Endocrinology', 'Internal Medicine"',
                "10. Tích oxalat. Các hội chứng bất thường liên quan đến gen lặn là gì? (Dịch: Các hội chứng bất thường liên quan đến gen lặn là gì?)",
                "lí giải minh bạch"}
        seen: set[str] = set()
        with open(src, encoding="utf-8") as f:
            for line in f:
                topics = _json.loads(line).get("medical_topic") or []
                if topics:
                    seen.add(topics[0])
        unmapped = {t for t in seen if t not in TAG_TO_CATEGORY}
        self.assertEqual(unmapped - junk, set(),
                         msg=f"new primary tags without a category: {sorted(unmapped - junk)}")
        for t in unmapped:
            self.assertEqual(category_of([t]), UNKNOWN)


class TestVbenchRunner(unittest.TestCase):
    FN = {
        "name": "tra_cuu_giao_dich",
        "parameters": {
            "type": "object",
            "properties": {
                "loai": {"type": "string", "enum": ["chuyen_khoan", "ung_tien"]},
                "ma_khu_vuc": {"type": "string"},
            },
            "required": ["loai"],
        },
    }

    def _agentic_raw(self, args):
        return json.dumps([{self.FN["name"]: args}], ensure_ascii=False)

    def test_classify_track(self):
        self.assertEqual(vb_classify_track({"id": 1, "choices": ["A. x"], "function": [], "domain": "d"}), "mc")
        self.assertEqual(vb_classify_track({"id": 2, "choices": [], "function": [self.FN], "domain": "d"}), "agentic")
        self.assertEqual(vb_classify_track({"id": 3, "choices": [], "function": [], "domain": "hatespeech"}), "safety")
        with self.assertRaises(SystemExit):   # tracks are disjoint in the release
            vb_classify_track({"id": 4, "choices": ["A"], "function": [self.FN], "domain": "d"})

    def test_agentic_arg_credit_grades_the_attempt_not_the_outcome(self):        # 1.3: partial credit scores the FIRST identifiable call at the same
        # level the ship-gate checks (top-level keys + verbatim enums).
        g = vb_grade_agentic_args(
            self._agentic_raw({"loai": "chuyen_khoan", "ma_khu_vuc": "VN-HN"}),
            [self.FN])
        self.assertTrue(g["parseable"])
        self.assertEqual((g["n_required"], g["n_required_ok"],
                          g["n_supplied"], g["n_supplied_ok"],
                          g["n_hallucinated"], g["n_off_enum"], g["n_missing"]),
                         (1, 1, 2, 2, 0, 0, 0))
        # missing required + hallucinated + off-enum, each counted once
        g = vb_grade_agentic_args(
            self._agentic_raw({"ma_khu_vuc": "VN-HN", "cot_ma": 1}),
            [self.FN])
        self.assertEqual((g["n_required_ok"], g["n_hallucinated"], g["n_missing"]),
                         (0, 1, 1))
        g = vb_grade_agentic_args(self._agentic_raw({"loai": "sai_enum"}), [self.FN])
        self.assertEqual((g["n_required_ok"], g["n_off_enum"]), (0, 1))
        # no identifiable call: contributes nothing, flagged unparseable
        for raw in ("tôi không thể trả lời", "",
                    json.dumps([{"ham_khong_ton_tai": {"loai": "chuyen_khoan"}}]),
                    self._agentic_raw({"loai": "chuyen_khoan"})[:20]):
            g = vb_grade_agentic_args(raw, [self.FN])
            self.assertFalse(g["parseable"], f"parsed: {raw[:40]}")
            self.assertEqual(g["n_supplied"], 0)

    def test_arg_credit_summarize_refuses_dup_and_nonnumeric_ids(self):
        from code_benchmark.score_arg_credit import summarize
        fns = {8142: [{"name": "f", "parameters": {"properties": {"a": {}}, "required": ["a"]}}]}
        raw = json.dumps([{"f": {"a": 1}}])
        out = summarize([("8142", raw)], fns)
        self.assertEqual((out["n_items"], out["n_attempted"], out["n_unparseable"]), (1, 1, 0))
        self.assertEqual(out["required_fill_rate"], 100.0)
        with self.assertRaises(SystemExit):
            summarize([("8142", raw), ("8142", raw)], fns)
        with self.assertRaises(SystemExit):
            summarize([("LG-0001", raw)], fns)

    def test_mc_letter_clamped_to_row_choices(self):
        # frozen extract_answer accepts A-E; the submission label must exist on THIS row
        self.assertEqual(vb_extract_mc_answer("Đáp án: D", ["A. a", "B. b", "C. c", "D. d"]), "D")
        self.assertEqual(vb_extract_mc_answer("E", ["A. a", "B. b", "C. c", "D. d"]), "")
        self.assertEqual(vb_extract_mc_answer("C", ["A. a", "B. b", "C. c"]), "C")
        self.assertEqual(vb_extract_mc_answer("tôi không chắc", ["A. a", "B. b"]), "")

    def test_agentic_valid_output_shapes(self):
        call = self._agentic_raw({"loai": "chuyen_khoan"})
        for raw in (call,
                    f"```json\n{call}\n```",
                    f"Suy luận lòng vòng.\n{call}\nTrên đây là lựa chọn của tôi."):
            got = vb_extract_function_call(raw, [self.FN])
            self.assertEqual(json.loads(got), [{"tra_cuu_giao_dich": {"loai": "chuyen_khoan"}}],
                             f"failed for shape: {raw[:30]}")
        # optional fields the model filled in are kept
        got = vb_extract_function_call(self._agentic_raw({"loai": "ung_tien", "ma_khu_vuc": "VN-HN"}), [self.FN])
        self.assertEqual(json.loads(got)[0][self.FN["name"]], {"loai": "ung_tien", "ma_khu_vuc": "VN-HN"})

    def test_agentic_never_ships_invalid_calls(self):
        bad = [
            json.dumps({"khoong_co_thuc": {"loai": "chuyen_khoan"}}),      # unknown name
            json.dumps([{"tra_cuu_giao_dich": {}}]),                       # missing required
            self._agentic_raw({"loai": "chuyen_huong"}),                   # enum value not in list
            self._agentic_raw({"loai": "chuyen_khoan", "cot_ma": 1}),      # hallucinated field
            "tôi không thể trả lời",                                       # no JSON at all
            "",                                                            # empty
        ]
        for raw in bad:
            self.assertEqual(vb_extract_function_call(raw, [self.FN]), "", f"leaked: {raw[:40]}")

    def test_agentic_candidate_ordering(self):
        good = self._agentic_raw({"loai": "chuyen_khoan"})
        bad = self._agentic_raw({"loai": "khong_hop_le"})
        # an invalid call earlier in the text does not block a later valid one
        self.assertNotEqual(vb_extract_function_call(f"{bad} rồi {good}", [self.FN]), "")
        # multi-call arrays ship the first element only
        self.assertNotEqual(vb_extract_function_call(json.dumps([json.loads(good)[0], {"x": {}}]), [self.FN]), "")

    def test_submission_rows_shape(self):
        results = [
            {"id": 9, "track": "mc", "answer": "C"},
            {"id": 3, "track": "agentic", "answer": self._agentic_raw({"loai": "ung_tien"})},
            {"id": 5, "track": "mc", "answer": ""},          # unparsed -> dropped, never guessed
        ]
        rows = vb_build_submission_rows(results)
        self.assertEqual([r["id"] for r in rows], [3, 9])    # id-sorted
        self.assertEqual(rows[0]["answer"], [{"tra_cuu_giao_dich": {"loai": "ung_tien"}}])  # real array
        self.assertEqual(rows[1]["answer"], "C")

    def test_agentic_repairs_braceless_output(self):
        # observed in the live run: ["name": {args}] — quotes kept, element
        # braces dropped. The repair pass must recover it ONLY when the name
        # and args validate against the row's own schemas.
        good = '["tra_cuu_giao_dich": {"loai": "chuyen_khoan"}]'
        self.assertEqual(json.loads(vb_extract_function_call(good, [self.FN])),
                         [{"tra_cuu_giao_dich": {"loai": "chuyen_khoan"}}])
        self.assertEqual(vb_extract_function_call('["tra_cuu_giao_dich": {"loai": "sai_enum"}]', [self.FN]), "")
        self.assertEqual(vb_extract_function_call('["ma_ham_khong_ton_tai": {"loai": "chuyen_khoan"}]', [self.FN]), "")
        # truncated args (no closing brace) stay unparsed — never repaired by guessing
        self.assertEqual(vb_extract_function_call('["tra_cuu_giao_dich": {"loai": "chuyen_khoan"', [self.FN]), "")
        # names carry Vietnamese diacritics in the real data
        fn_vn = dict(self.FN, name="xác_minh_giấy_tờ")
        got = vb_extract_function_call('["xác_minh_giấy_tờ": {"loai": "ung_tien"}]', [fn_vn])
        self.assertEqual(json.loads(got), [{"xác_minh_giấy_tờ": {"loai": "ung_tien"}}])

    def test_diagnosis_records_wrong_answers_without_fixing_them(self):
        # a readable call that fails validation is a MODEL error, labeled as
        # such — and diagnose never changes what extract_function_call returns
        self.assertEqual(vb_diagnose_rejection('["ma_ham": {"loai": "ung_tien"}]', [self.FN]),
                         "unknown_function_name")
        self.assertEqual(vb_diagnose_rejection(self._agentic_raw({"loai": "sai"}), [self.FN]),
                         "off_enum_value")
        self.assertEqual(vb_diagnose_rejection('["tra_cuu_giao_dich": {"loai": "chuyen_khoan"', [self.FN]),
                         "truncated_output")
        self.assertEqual(vb_diagnose_rejection("xin chào", [self.FN]), "no_call_shape_found")
        self.assertEqual(vb_diagnose_rejection(self._agentic_raw({"loai": "ung_tien"}), [self.FN]), "")

    def test_parse_choice_and_value(self):
        self.assertEqual(vb_parse_choice("3", 4), 3)
        self.assertEqual(vb_parse_choice("Đáp án: 2", 4), 2)
        self.assertEqual(vb_parse_choice("2. chọn mục này", 4), 2)
        self.assertIsNone(vb_parse_choice("9", 4))          # out of range -> no default
        self.assertIsNone(vb_parse_choice("tôi không biết", 4))
        self.assertIsNone(vb_parse_choice("3.14", 4))       # decimal, not a choice
        self.assertEqual(vb_parse_value("150", {"type": "integer"}), 150)
        self.assertEqual(vb_parse_value("khoảng 0,4", {"type": "number"}), 0.4)
        self.assertIsNone(vb_parse_value("không rõ số", {"type": "number"}))
        self.assertIs(vb_parse_value("true", {"type": "boolean"}), True)
        self.assertEqual(vb_parse_value('"Hà Nội"', {"type": "string"}), "Hà Nội")

    def test_guided_interview_assembles_validated_call(self):
        item = {"id": 1, "domain": "d", "track": "agentic", "question": "Q?",
                "function": [self.FN]}
        answers = iter(["1", "2", "0"])   # function 1; loai=enum[2]; optional ma_khu_vuc skip
        asked = []
        ans, tr = vb_guided_call(item, lambda p: (asked.append(p), next(answers))[1])
        self.assertEqual(json.loads(ans), [{"tra_cuu_giao_dich": {"loai": "ung_tien"}}])
        self.assertEqual(len(asked), 3)                      # model answered everything
        self.assertTrue(any(s.startswith("ASSEMBLED") for s in tr))
        # enum answer came VERBATIM from the row's enum list — the tool never invents
        self.assertIn("ung_tien", asked[1])

    def test_guided_unanswered_required_stays_failed(self):
        item = {"id": 1, "domain": "d", "track": "agentic", "question": "Q?",
                "function": [self.FN]}
        ans, tr = vb_guided_call(item, lambda p: "0")        # never a valid 1-based choice
        self.assertEqual(ans, "")
        it2 = iter(["1", "99"])                              # enum choice out of range
        ans2, tr2 = vb_guided_call(item, lambda p: next(it2))
        self.assertEqual(ans2, "")
        self.assertTrue(any("unanswered_required:loai" in s for s in tr2))

    def test_load_checkpoint_keeps_guided_and_rederives_free(self):
        # free row: stored answer is a stale snapshot -> must be re-derived
        # guided row: transcript only makes sense WITH its stored answer -> keep
        item_free = {"id": 5, "track": "agentic", "question": "Q",
                     "function": [self.FN], "domain": "d"}
        item_guided = {"id": 6, "track": "agentic", "question": "Q",
                       "function": [self.FN], "domain": "d"}
        guided_ans = json.dumps([{"tra_cuu_giao_dich": {"loai": "ung_tien"}}],
                                ensure_ascii=False, separators=(",", ":"))
        cp_rows = [
            {"id": 5, "domain": "d", "track": "agentic", "question": "Q",
             "raw_response": '["tra_cuu_giao_dich": {"loai": "chuyen_khoan"}]', "answer": ""},
            {"id": 6, "domain": "d", "track": "agentic", "question": "Q",
             "raw_response": "Q[function]\n...\nA\n1\n\n---\nASSEMBLED", "answer": guided_ans},
        ]
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td) / "vbench_result_2_test.csv"
            pd.DataFrame(cp_rows)[VB_CHECKPOINT_COLS].to_csv(cp, index=False)
            out = vb_load_checkpoint(cp, {5: item_free, 6: item_guided})
        got = {r["id"]: r["answer"] for r in out}
        self.assertEqual(json.loads(got[5]), [{"tra_cuu_giao_dich": {"loai": "chuyen_khoan"}}])
        self.assertEqual(got[6], guided_ans)

    def test_prompt_styles_minimal_vs_detailed(self):
        q, fns = "Câu hỏi test XYZ?", [self.FN]
        minimal = vb_build_agentic_prompt(q, fns, "minimal")
        detailed = vb_build_agentic_prompt(q, fns, "detailed")
        self.assertEqual(minimal.splitlines()[0], q)          # question comes FIRST, raw
        self.assertIn("tra_cuu_giao_dich", minimal)           # row's own schema present
        for leak in ("Bạn là trợ lý", "Quy tắc:", "tra_cuu_thoi_tiet", "Không giải thích"):
            self.assertNotIn(leak, minimal)                   # no role/rules/example/CoT ban
        self.assertIn("tra_cuu_thoi_tiet", detailed)          # detailed keeps the example
        # default must be the honest condition
        self.assertEqual(vb_build_agentic_prompt(q, fns), minimal)

    def test_valid_summary_never_carries_correctness(self):
        # gate 1.3: the local log counts syntactic validity only. The report's
        # minimal run had 4,141 valid MC + 985 valid agentic rows — the shape
        # below mirrors that split at small scale.
        results = [
            {"track": "mc", "domain": "laws", "answer": "C"},
            {"track": "mc", "domain": "laws", "answer": ""},
            {"track": "agentic", "domain": "agentic", "answer": '[{"f": {}}]'},
            {"track": "agentic", "domain": "agentic", "answer": ""},
        ]
        rows = vb_build_valid_summary(results, "deadbeef")
        self.assertEqual([(r["track"], r["domain"], r["n"], r["valid"]) for r in rows],
                         [("agentic", "agentic", 2, 1), ("mc", "laws", 2, 1)])
        for r in rows:
            self.assertEqual(r["valid_rate"], 50.0)
            self.assertEqual(r["measurement_card_hash"], "deadbeef")
            self.assertNotIn("correct", r)          # correctness lives server-side only
            self.assertNotIn("score", r)
        self.assertNotIn("correct", VB_VALID_SUMMARY_COLS)
        self.assertNotIn("score", VB_VALID_SUMMARY_COLS)
        self.assertNotIn("valid", VB_SERVER_SCORES_COLS)
        self.assertNotIn("valid_rate", VB_SERVER_SCORES_COLS)

    def test_server_scores_roundtrip_and_guards(self):
        good = ("domain,track,score,correct,total\n"
                "laws,multiple-choice,60.73,116,191\n"
                "agentic,function calling,39.10,391,1000\n")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "grades.csv"
            src.write_text(good, encoding="utf-8")
            grades = vb_read_server_scores(src)
            self.assertEqual([(g["domain"], g["correct"], g["total"]) for g in grades],
                             [("laws", 116, 191), ("agentic", 391, 1000)])
            snap = Path(td) / "snap.csv"
            vb_write_server_snapshot(snap, grades, "deadbeef", "vbench.ai, screenshot 2026-09-04")
            back = pd.read_csv(snap, dtype=str)
            self.assertEqual(list(back.columns), VB_SERVER_SCORES_COLS)
            self.assertTrue((back["measurement_card_hash"] == "deadbeef").all())
            self.assertTrue((back["server_source"] == "vbench.ai, screenshot 2026-09-04").all())
            # macro/micro averages are reporting recomputes, never stored rows
            self.assertEqual(len(back), 2)
            bad_header = Path(td) / "bad.csv"
            bad_header.write_text("domain,score\nlaws,60.73\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                vb_read_server_scores(bad_header)
            bad_math = Path(td) / "badmath.csv"
            bad_math.write_text("domain,track,score,correct,total\nlaws,multiple-choice,99.0,116,191\n",
                                encoding="utf-8")
            with self.assertRaises(SystemExit):   # score != 100*correct/total
                vb_read_server_scores(bad_math)
            with self.assertRaises(SystemExit):   # provenance is mandatory
                vb_write_server_snapshot(Path(td) / "x.csv", grades, "deadbeef", "  ")

    def test_measurement_card_hash_aborts_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                vb_measurement_card_hash(Path(td) / "no-such-card.md")


class TestAnnotationWorkbooks(unittest.TestCase):
    def test_normalize_conservative(self):
        # case/whitespace/trailing punctuation fold together...
        self.assertEqual(normalize_answer("  Hà   Nội. "), normalize_answer("hà nội"))
        # ...but number-separator variants must NOT (go to adjudication)
        self.assertNotEqual(normalize_answer("15,00%"), normalize_answer("15.00%"))

    def test_merge_answers_buckets(self):
        a = {"k1": "Hà Nội", "k2": "1916", "k3": "A", "k4": "x", "k5": ""}
        b = {"k1": "hà nội ", "k2": "1916.", "k3": "B", "k4": "", "k5": ""}
        r = merge_answers(a, b)
        self.assertEqual(dict(r["agreed"]), {"k1": "Hà Nội", "k2": "1916"})
        self.assertEqual(r["disagreements"], [("k3", "A", "B")])
        self.assertEqual(r["empty_b"], ["k4"])
        self.assertEqual(r["empty_both"], ["k5"])

    def test_workbook_rows_group_passages(self):
        joined = [
            {"dataset": "squad", "item_id": 9, "passage_id": 2, "stratum": "s", "question": "q9", "context": "c"},
            {"dataset": "squad", "item_id": 10, "passage_id": 2, "stratum": "s", "question": "q10", "context": "c"},
            {"dataset": "drop", "item_id": 3, "passage_id": 1, "stratum": "d", "question": "q3", "context": "c"},
        ]
        rows = workbook_rows(joined)
        self.assertEqual([r["item_id"] for r in rows], ["3", "9", "10"])  # drop first, then grouped
        keys = [r["passage_key"] for r in rows]
        self.assertEqual(keys, ["drop:1", "squad:2", "squad:2"])  # same passage contiguous
        self.assertTrue(all(r["gold_answer"] == "" for r in rows))  # blind, empty
        self.assertNotIn("raw_response", rows[0])  # model answers must never leak in


def _review_row(annot, model, ds, iid, decision, ma, corr="", note=""):
    return dict(zip(REVIEW_COLS, [annot, model, ds, iid, "short-direct",
                                  decision, ma, corr, note], strict=True))


class TestReviewBlobBuilder(unittest.TestCase):
    def test_model_from_filename(self):
        self.assertEqual(
            model_from_filename(Path("all_res/ollama_result/reading_answers_Qwen3_8-27B-Q4_K_M_gguf.csv")),
            "Qwen3_8-27B-Q4_K_M_gguf")
        for bad in ("other.csv", "reading_answers_.csv"):
            with self.assertRaises(ValueError):
                model_from_filename(Path(bad))

    def test_load_answers_csv_and_dup_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "reading_answers_m1.csv"
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, ["dataset", "item_id", "stratum", "question",
                                       "context_words", "raw_response"])
                w.writeheader()
                w.writerow({"dataset": "squad", "item_id": "1", "stratum": "s",
                            "question": "q", "context_words": 5, "raw_response": " Hà Nội "})
            model, amap = load_answers_csv(p)
            self.assertEqual((model, amap), ("m1", {"squad:1": "Hà Nội"}))  # stripped
            with open(p, "a", encoding="utf-8") as f:
                f.write("squad,1,s,q,5,x\n")
            with self.assertRaises(SystemExit):
                load_answers_csv(p)  # duplicate key

    def test_review_items_join_and_dedup(self):
        book = [{"passage_key": "squad:0", "dataset": "squad", "item_id": "0",
                 "stratum": "s", "question": "q0", "context": "ctx0"},
                {"passage_key": "squad:0", "dataset": "squad", "item_id": "1",
                 "stratum": "s", "question": "q1", "context": "ctx0"}]
        items, passages = review_items(book, {"m1": {"squad:0": "a0", "squad:1": "a1"},
                                              "m2": {}})
        self.assertEqual([i["item_id"] for i in items], ["0", "1"])  # workbook order kept
        self.assertEqual(items[0]["answers"], {"m1": "a0", "m2": None})
        self.assertEqual(passages, {"squad:0": "ctx0"})  # deduped context map
        with self.assertRaises(SystemExit):
            review_items(book, {"m1": {"squad:99": "x"}})  # drift fail-fast

    def test_embed_json_neutralizes_script_close_and_roundtrips(self):
        payload = {"t": "a</script>b", "u": "x" + chr(0x2028) + "y", "v": "Hà Nội"}
        s = embed_json(payload)
        self.assertNotIn("</script", s)
        self.assertNotIn(chr(0x2028), s)
        self.assertEqual(json.loads(s), payload)  # escapes are JSON-meaning-preserving

    def test_render_html_placeholder_guard(self):
        self.assertEqual(render_html('<x>"__VMLU_DATA__"</x>', '{"a":1}'), '<x>{"a":1}</x>')
        for bad in ("<x></x>", '<x>"__VMLU_DATA__" "__VMLU_DATA__"</x>'):
            with self.assertRaises(SystemExit):
                render_html(bad, "{}")


class TestReviewMerge(unittest.TestCase):
    def _pair(self):
        a = {"squad:1": _review_row("linh", "mX", "squad", "1", "accept", "Hà Nội"),
             "squad:2": _review_row("linh", "mX", "squad", "2", "accept", "1916"),
             "squad:3": _review_row("linh", "mX", "squad", "3", "reject", "1916", " 1916"),
             "squad:4": _review_row("linh", "mX", "squad", "4", "reject", "x", "A"),
             "squad:5": _review_row("linh", "mX", "squad", "5", "reject", "x", ""),
             "squad:6": _review_row("linh", "mX", "squad", "6", "", "x"),
             "squad:7": _review_row("linh", "mX", "squad", "7", "accept", "")}
        b = {"squad:1": _review_row("anh", "mX", "squad", "1", "accept", "Hà Nội"),
             "squad:2": _review_row("anh", "mX", "squad", "2", "reject", "1916", "1917"),
             "squad:3": _review_row("anh", "mX", "squad", "3", "reject", "1916", "1916."),
             "squad:4": _review_row("anh", "mX", "squad", "4", "reject", "x", "B"),
             "squad:5": _review_row("anh", "mX", "squad", "5", "reject", "x", ""),
             "squad:6": _review_row("anh", "mX", "squad", "6", "accept", "x"),
             "squad:7": _review_row("anh", "mX", "squad", "7", "accept", "")}
        return a, b

    def test_gold_and_adjudication_cases(self):
        a, b = self._pair()
        res = gold_from_reviews(a, b)
        self.assertEqual(dict(res["gold_agreed"]), {"squad:1": "Hà Nội",   # both accept
                                                    "squad:3": "1916"})    # both reject, match
        adjud = {k: r for k, r, _, _ in res["adjudication"]}
        self.assertEqual(adjud, {"squad:2": "accept_vs_reject",
                                 "squad:4": "corrections_differ",
                                 "squad:5": "missing_correction",
                                 "squad:7": "missing_model_answer"})
        self.assertEqual(res["skipped"], ["squad:6"])  # unset on either side

    def test_model_answer_drift_detected(self):
        a, b = self._pair()
        a["squad:1"] = _review_row("linh", "mX", "squad", "1", "accept", "HÀ NỘI!")
        res = gold_from_reviews(a, b)
        self.assertNotIn("squad:1", dict(res["gold_agreed"]))
        self.assertEqual({k: r for k, r, _, _ in res["adjudication"]}["squad:1"],
                         "model_answer_drift")

    def test_stats_math(self):
        a, b = self._pair()
        res = gold_from_reviews(a, b)
        txt = review_stats(res, "linh", "anh")
        # A accepted 3/6 reviewed, B accepted 3/7, agreement 5/6 both-reviewed
        self.assertIn("accepted 3/6 = 50.0% acceptance", txt)
        self.assertIn("accepted 3/7 = 42.9% acceptance", txt)
        self.assertIn("5/6 = 83.3%", txt)
        self.assertIn("gold agreed: 2", txt)
        self.assertIn("accept_vs_reject=1", txt)

    def test_read_review_round_trip_and_guards(self):
        a, _ = self._pair()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review_linh_mx.csv"
            with open(p, "w", newline="", encoding="utf-8-sig") as f:  # BOM like the UI export
                w = csv.writer(f)
                w.writerow(REVIEW_COLS)
                for k in sorted(a):
                    w.writerow([a[k][c] for c in REVIEW_COLS])
            meta, got = read_review(p)
            self.assertEqual(meta, {"annotator": "linh", "model": "mX", "n": 7,
                                    "blank_rejects": 1})
            self.assertEqual(set(got), set(a))
            # guards: header / illegal decision / mixed identity in one file
            for text, why in (
                    ("x,y\n1,2", "header mismatch"),
                    (",".join(REVIEW_COLS) + "\nlinh,m,s,1,s,bogus,,\n", "illegal decision"),
                    (",".join(REVIEW_COLS) + "\nlinh,m,s,1,s,accept,,\nanh,m,s,2,s,accept,,\n",
                     "mixes annotator")):
                q = Path(td) / "bad.csv"
                q.write_text(text, encoding="utf-8")
                with self.assertRaises(SystemExit, msg=why):
                    read_review(q)

    def test_apply_gold_fills_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            mp = Path(td) / "manifest.csv"
            with open(mp, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["dataset", "item_id", "stratum", "passage_id", "question", "gold_answer"])
                w.writerow(["squad", "1", "s", 0, "q1", ""])
                w.writerow(["squad", "2", "s", 1, "q2", ""])
            filled, still = apply_gold(mp, [("squad:1", "Hà Nội")])
            self.assertEqual((filled, still), (1, 1))
            got = {r["item_id"]: r["gold_answer"]
                   for r in csv.DictReader(open(mp, encoding="utf-8"))}
            self.assertEqual(got, {"1": "Hà Nội", "2": ""})
            with self.assertRaises(SystemExit):
                apply_gold(mp, [("squad:99", "x")])  # unknown key refuses


class TestMergeSplit(unittest.TestCase):
    """The split-400 workflow (review_records/): coverage is the UNION of
    decided items; one decision per item is enough. gold_from_split is the
    classifier; cmd-level guards live in export_annotation_workbooks."""

    def test_union_coverage_single_owner_yields_gold(self):
        a = {"squad:1": _review_row("linh", "mX", "squad", "1", "accept", "Hà Nội"),
             "squad:2": _review_row("linh", "mX", "squad", "2", "reject", "1916", "1917")}
        b = {"squad:3": _review_row("anh", "mX", "squad", "3", "accept", "3"),
             "squad:4": _review_row("anh", "mX", "squad", "4", "reject", "x", "20")}
        res = gold_from_split([("linh", a), ("anh", b)])
        self.assertEqual(dict(res["gold_agreed"]),
                         {"squad:1": "Hà Nội", "squad:2": "1917",
                          "squad:3": "3", "squad:4": "20"})
        self.assertEqual(res["adjudication"], [])
        self.assertEqual(res["covered"], 4)
        self.assertEqual(res["per_reviewer"], {"linh": 2, "anh": 2})

    def test_agreeing_overlap_collapses_to_one_gold(self):
        a = {"squad:5": _review_row("linh", "mX", "squad", "5", "accept", "Paris")}
        b = {"squad:5": _review_row("anh", "mX", "squad", "5", "accept", "Paris")}
        res = gold_from_split([("linh", a), ("anh", b)])
        self.assertEqual(dict(res["gold_agreed"]), {"squad:5": "Paris"})
        self.assertEqual(res["adjudication"], [])

    def test_disagreeing_overlap_goes_to_adjudication(self):
        a = {"squad:1": _review_row("linh", "mX", "squad", "1", "accept", "Hanoi")}
        b = {"squad:1": _review_row("anh", "mX", "squad", "1", "reject", "Hanoi", "Sai Gon")}
        res = gold_from_split([("linh", a), ("anh", b)])
        self.assertEqual(res["gold_agreed"], [])
        self.assertEqual([(k, r) for k, r, _, _ in res["adjudication"]],
                         [("squad:1", "overlap_accept_vs_reject")])

    def test_blank_correction_reject_adjudicates(self):
        a = {"squad:2": _review_row("linh", "mX", "squad", "2", "reject", "1916", "")}
        res = gold_from_split([("linh", a)])
        self.assertEqual([(k, r) for k, r, _, _ in res["adjudication"]],
                         [("squad:2", "missing_correction")])

    def test_undecided_items_simply_absent(self):
        a = {"squad:9": _review_row("linh", "mX", "squad", "9", "", "x")}  # unset/flag
        res = gold_from_split([("linh", a)])
        self.assertEqual(res["covered"], 0)
        self.assertEqual(res["gold_agreed"], [])
        self.assertEqual(res["adjudication"], [])

    def test_single_reviewer_cli_merge_split(self):
        # N=1 split is legal: one reviewer owns all 400 (gold_from_split was
        # built for it; the CLI must not refuse)
        a = {"squad:1": _review_row("linh", "mX", "squad", "1", "accept", "Hà Nội"),
             "squad:2": _review_row("linh", "mX", "squad", "2", "reject", "1916", "1917")}
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p = tmp / "review_linh_mx.csv"
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(REVIEW_COLS)
                for k in sorted(a):
                    w.writerow([a[k][c] for c in REVIEW_COLS])
            args = argparse.Namespace(
                files=[p],
                workbook=tmp / "absent.csv",
                manifest=tmp / "absent_manifest.csv",
                out_gold=tmp / "g.csv",
                out_adjud=tmp / "a.csv",
                apply=False,
            )
            cmd_merge_split(args)  # must not raise
            got = {r["item_id"]: r["gold_answer"]
                   for r in csv.DictReader(open(tmp / "g.csv", encoding="utf-8"))}
            self.assertEqual(got, {"1": "Hà Nội", "2": "1917"})


class TestExportBlob(unittest.TestCase):
    """`build_review_ui.py export-blob` — the Python→Next data bridge (spec
    review-server 'Data emission reuses the validated join'). Runs the real CLI
    against fixture CSVs so the whole argv->validate->write path is exercised."""

    ROOT = Path(__file__).resolve().parent.parent
    PY = sys.executable

    def _inputs(self, td, n=3):
        wb = Path(td) / "annotator_A.csv"
        with open(wb, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["passage_key", "dataset", "item_id", "stratum", "question", "context",
                                   "gold_answer", "note"])
            w.writeheader()
            for i in range(n):
                w.writerow({"passage_key": "squad:0", "dataset": "squad", "item_id": str(i),
                            "stratum": "s", "question": f"q{i}", "context": "ctx", "gold_answer": "", "note": ""})
        an = Path(td) / "reading_answers_m1.csv"
        with open(an, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["dataset", "item_id", "raw_response"])
            w.writeheader()
            for i in range(n):
                w.writerow({"dataset": "squad", "item_id": str(i), "raw_response": f"a{i}"})
        return wb, an

    def _cli(self, wb, an, out, extra=()):
        # fixture paths on argv, no shell
        return subprocess.run(  # nosec B603
            [self.PY, str(self.ROOT / "code_benchmark" / "build_review_ui.py"), "export-blob",
             "--workbook", str(wb), "--answers", str(an), "--out", str(out), *extra],
            capture_output=True, text=True, cwd=str(self.ROOT))

    def test_emits_validated_blob(self):
        with tempfile.TemporaryDirectory() as td:
            wb, an = self._inputs(td)
            out = Path(td) / "review-blob.json"
            r = self._cli(wb, an, out)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            blob = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(blob["schema_version"], 1)
            self.assertEqual([i["item_id"] for i in blob["items"]], ["0", "1", "2"])  # workbook order
            self.assertEqual(blob["models"], ["m1"])
            self.assertEqual(blob["items"][0]["answers"], {"m1": "a0"})
            self.assertEqual(blob["passages"], {"squad:0": "ctx"})  # deduped

    def test_coverage_drift_refuses_and_leaves_prior(self):
        with tempfile.TemporaryDirectory() as td:
            wb, an = self._inputs(td, n=3)
            out = Path(td) / "review-blob.json"
            self._cli(wb, an, out)                      # seed a good blob
            before = out.read_bytes()
            # truncate answers -> coverage 1/3 -> must fail and NOT overwrite
            with open(an, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, ["dataset", "item_id", "raw_response"]); w.writeheader()
                w.writerow({"dataset": "squad", "item_id": "0", "raw_response": "a0"})
            r = self._cli(wb, an, out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("covers 1/3", r.stdout + r.stderr)
            self.assertEqual(out.read_bytes(), before)   # unchanged
            # --allow-partial then succeeds
            r = self._cli(wb, an, out, extra=("--allow-partial",))
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            blob = json.loads(out.read_text(encoding="utf-8"))
            self.assertIsNone(blob["items"][2]["answers"]["m1"])  # gap -> null


REVIEW_JS_SLUG_REF = {   # template JS slug() outputs (node-verified; web/lib/slug.ts must agree)
    "Linh": "linh", "lình": "linh", "l ạnh  X!": "l_anh_x", "nguyễn văn A": "nguyen_van_a",
    "Qwen3_8-27B-Q4_K_M_gguf": "qwen3_8_27b_q4_k_m_gguf", "tom@corp": "tom_corp",
    "Hoàng — B": "hoang_b", "Bùi Thị Hồng Hạnh": "bui_thi_hong_hanh",
}


def _ts_runner():
    """Find a way to execute the app's TS modules: bun directly, or node >=22
    with --experimental-strip-types. None -> contract tests skip."""
    if shutil.which("bun"):
        return "bun"
    node = shutil.which("node")
    if node:
        major = subprocess.run([node, "--version"], capture_output=True, text=True).stdout  # nosec B603
        try:
            if int(major.lstrip("v").split(".")[0]) >= 22:
                return "node"
        except ValueError:
            pass
    return None


class TestNextContracts(unittest.TestCase):
    """Cross-boundary contracts of the Next app (web/) against the static
    fallback template: slug identity + export-CSV equivalence (spec
    review-ui 'Mode equivalence'). Skipped when no TS runner is installed."""

    ROOT = Path(__file__).resolve().parent.parent

    def _run_ts(self, module: str, body: str):
        runner = _ts_runner()
        if not runner:
            self.skipTest("neither bun nor node>=22 on PATH")
        tmp = self.ROOT / "web" / ".contract-test.ts"
        tmp.write_text(f"import * as M from {module!r};\n" + body, encoding="utf-8")
        try:
            cmd = ["bun", "run", str(tmp)] if runner == "bun" else \
                ["node", "--experimental-strip-types", "--disable-warning=ExperimentalWarning", str(tmp)]
            # cmd = [bun|node, script]: our own generated file
            r = subprocess.run(  # nosec B603
                cmd, capture_output=True, text=True, timeout=60, cwd=str(self.ROOT / "web"))
            self.assertEqual(r.returncode, 0, msg=f"{runner}: {r.stderr[:800]}")
            return r.stdout
        finally:
            tmp.unlink(missing_ok=True)

    def test_slug_ts_matches_js_reference(self):
        out = self._run_ts("./lib/slug.ts", "console.log(JSON.stringify(Object.entries("
                        + json.dumps(REVIEW_JS_SLUG_REF, ensure_ascii=False) +
                        ").map(([k,v]) => [M.slug(k), k, v])));")
        for got, input_, want in json.loads(out):
            self.assertEqual(got, want, msg=f"TS slug({input_!r}) != JS reference")

    def test_next_export_csv_equals_template_buildcsv_and_feeds_read_review(self):
        """Same blob + decisions through (a) web/lib/export-csv.ts and (b) the
        static template's buildCsv(); both must parse via read_review() to
        identical row mappings — the byte-compat contract of the merge step."""
        book = [{"passage_key": "squad:0", "dataset": "squad", "item_id": "1",
                 "stratum": "short-direct", "question": "q1", "context": "ctx"},
                {"passage_key": "squad:0", "dataset": "squad", "item_id": "2",
                 "stratum": "short-infer", "question": "q2, with comma", "context": "ctx"},
                {"passage_key": "drop:0", "dataset": "drop", "item_id": "7",
                 "stratum": "num-simple", "question": 'q3 "quoted"', "context": "ctx2"}]
        blob = build_blob(book, {"mX": {"squad:1": "Hà Nội", "squad:2": "1916", "drop:7": "3"}},
                          created="2026-01-01")
        env = {"schema_version": 1, "annotator": "lình", "model": "mX",
               "saved_at": "2026-01-01T00:00:00.000Z",
               "items": {"squad:1": {"d": "accept", "c": "ignored", "n": "ghi, chú"},
                         "squad:2": {"d": "reject", "c": '"1916" năm', "n": "multi\nline"},
                         "drop:7": {"d": None, "c": "", "n": "note only"}}}
        js_out = self._run_ts("./lib/export-csv.ts",
                              "console.log(M.makeExportCsv(" + json.dumps(blob, ensure_ascii=False)
                              + ", " + json.dumps(env, ensure_ascii=False) + "));")
        tmpl = (Path(__file__).parent / "review_ui_template.html").read_text(encoding="utf-8")
        start, end = tmpl.index("function csvCell"), tmpl.index("function parseCsv")
        js = tmpl[start:end] + f"""
const itemKey = it => it.dataset + ":" + it.item_id;
const blob = {json.dumps(blob, ensure_ascii=False)};
const env = {json.dumps(env, ensure_ascii=False)};
const answerFor = (it, m) => (it.answers || {{}})[m] ?? "";
process.stdout.write(buildCsv(blob.items, env.items, env.annotator, env.model, answerFor));
"""
        node = shutil.which("node")
        if not node:
            self.skipTest("node absent — cannot run the template's buildCsv() to compare")
        r = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True)  # nosec B603
        client_csv = r.stdout
        with tempfile.TemporaryDirectory() as td:
            pa, pb = Path(td) / "a.csv", Path(td) / "b.csv"
            pa.write_text(js_out, encoding="utf-8")           # Next lib output
            pb.write_text(client_csv, encoding="utf-8")        # static template output
            ma, ra = read_review(pa)
            mb, rb = read_review(pb)
        self.assertEqual(ma, mb)
        self.assertEqual(ma["annotator"], "lình")              # unicode survives both exporters
        for k in ra:
            self.assertEqual(ra[k], rb[k], msg=f"row {k} differs between Next and static export")

class TestResultsIdentity(unittest.TestCase):
    """Canonical model_id / dataset_id / run_id rules + migration gates
    (change results-db-frontend). Offline: fake Mongo adapter, tempdirs."""

    def test_canonical_model_id_pins_spellings(self):
        self.assertEqual(canonical_model_id("Qwen3.5-9B-28K"), "qwen3-5-9b-28k")
        self.assertEqual(canonical_model_id("Qwen3_5-9B-28K"), "qwen3-5-9b-28k")
        self.assertEqual(canonical_model_id("qwen38-nothink"), "qwen38-nothink")
        self.assertEqual(canonical_model_id("Qwen3_8-27B-Q4_K_M_gguf"),
                         "qwen3-8-27b-q4-k-m-gguf")
        self.assertEqual(canonical_model_id("Qwen3.8-27B-Q4_K_M.gguf"),
                         "qwen3-8-27b-q4-k-m-gguf")

    def test_make_run_id_scheme(self):
        self.assertEqual(make_run_id("qwen3-5-9b-28k", "bidlqa-val", "MC-12"),
                         "qwen3-5-9b-28k__bidlqa-val__MC-12")
        with self.assertRaises(ValueError):
            make_run_id("", "bidlqa-val", "MC-12")
        with self.assertRaises(ValueError):
            make_run_id("a__b", "bidlqa-val", "MC-12")

    def test_plan_dirs_resolve_to_one_id(self):
        for dir_slug, model_id, _files in MIGRATION_PLAN:
            self.assertEqual(canonical_model_id(dir_slug), model_id,
                             msg=f"dir {dir_slug} must resolve to {model_id}")

    def test_runner_config_dataset_scoped_override(self):
        # MC-31 spans dataset kinds: legal is the 4-token MC budget, reading
        # the 48-token reading budget. One card-wide config would lie for one
        # of the two, so the (card, dataset) key wins and plain keys fall back.
        self.assertEqual(runner_config("MC-31", "legal-mc-146")["max_tokens"], 4)
        self.assertEqual(runner_config("MC-31", "legal-nli-150")["max_tokens"], 4)
        self.assertEqual(runner_config("MC-31", "reading-400")["max_tokens"], 48)
        self.assertEqual(runner_config("MC-31", "bidlqa-val")["max_tokens"], 48)
        self.assertEqual(runner_config("MC-9", "whatever")["max_tokens"], 4)  # fallback
        self.assertIsNone(runner_config("MC-999", "x"))

    def test_accuracy_summary_falls_back_to_the_committed_final(self):
        """`run_legal_arm_a.py` prints accuracy but writes no aggregate; the
        migration must still find summary rows — derived from the final's own
        `correct` column with the runner's function, never a second scorer."""
        import csv as _csv
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            final = d / "full_evaluation_legal_M.csv"
            with open(final, "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=["id", "answer", "gold_answer", "correct"])
                w.writeheader()
                w.writerow({"id": "LG-0001", "answer": "A", "gold_answer": "A", "correct": "1"})
                w.writerow({"id": "LG-0002", "answer": "B", "gold_answer": "C", "correct": "0"})
            acc = accuracy_summary_rows(d, "M")
            rows = acc["legal-mc-146"]
            overall = rows[0]
            self.assertEqual((overall["level"], overall["n"], overall["correct"]), ("overall", 2, 1))
            self.assertEqual(overall["accuracy"], 50.0)

            # a committed aggregate, when present, always wins over derivation
            with open(d / "accuracy_legal_M.csv", "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=["level", "name", "n", "correct", "accuracy"])
                w.writeheader()
                w.writerow({"level": "overall", "name": "overall", "n": 2, "correct": 2, "accuracy": 100.0})
            self.assertEqual(accuracy_summary_rows(d, "M")["legal-mc-146"][0]["correct"], "2")

            # no aggregate and no final: the dataset is simply absent, and a
            # half-written final (no `correct` column) is a hard error
            self.assertNotIn("legal-mc-146", accuracy_summary_rows(Path(td) / "empty", "M"))
            bad = Path(td) / "bad"
            bad.mkdir()
            (bad / "full_evaluation_legal_M.csv").write_text("id,answer\nLG-0001,A\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                accuracy_summary_rows(bad, "M")

    def test_seed_is_idempotent(self):
        from unittest.mock import MagicMock, patch
        import code_benchmark.seed_registries as sr

        db = MagicMock()
        # dataset_docs() reads the gitignored dataset files (absent on a clean
        # CI checkout). The idempotency contract under test is the upsert loop,
        # so inject fake docs instead of requiring real dataset sources.
        with patch.object(sr, "dataset_docs", return_value=[{"_id": "ds1"}]):
            seed(db)
            seed(db)  # second run must not raise
        self.assertTrue(db.__getitem__.return_value.update_one.called)

    def test_item_builders_stamp_both_ids(self):
        kw = dict(run_id="m__d__MC-9", model_id="m", dataset_id="d", card_hash="h")
        mc = mc_item({"id": "28-0007", "answer": "A", "gold_answer": "A", "correct": "1",
                      "question": "q", "prompt": "p", "raw_response": "A"}, **kw)
        self.assertEqual((mc["model_id"], mc["dataset_id"]), ("m", "d"))
        self.assertEqual(mc["_id"], "m__d__MC-9::28-0007")
        vb = vbench_item({"id": "4", "domain": "literature", "track": "mc",
                          "question": "q", "raw_response": "D", "answer": "D"}, **kw)
        self.assertEqual((vb["model_id"], vb["dataset_id"]), ("m", "d"))
        rd = reading_item({"dataset": "squad", "item_id": "0", "stratum": "s",
                           "gold_answer": "g", "raw_response": "r",
                           "prediction": "p", "em": "1", "f1": "1.0"}, **kw)
        self.assertEqual((rd["model_id"], rd["dataset_id"]), ("m", "d"))
        self.assertEqual(rd["item_id"], "squad:0")
        with self.assertRaises(SystemExit):
            mc_item({"id": "", "answer": "A"}, **kw)

    def test_migrate_happy_path_fake_adapter(self):
        import csv as _csv

        class FakeColl:
            def __init__(self):
                self.docs = {}

            def update_one(self, flt, upd, upsert=False):
                self.docs[flt["_id"]] = upd["$set"]

            def count_documents(self, flt):
                if not flt:
                    return len(self.docs)
                return sum(1 for d in self.docs.values()
                           if all(d.get(k) == v for k, v in flt.items()))

            def create_index(self, *a, **k):
                pass

        class FakeDB(dict):
            def __getitem__(self, k):
                if k not in self:
                    self[k] = FakeColl()
                return dict.__getitem__(self, k)

        with tempfile.TemporaryDirectory() as td:
            from code_benchmark import migrate_results_to_mongo as mig
            old_plan, old_dir, old_cfg = mig.MIGRATION_PLAN, mig.RESULTS_DIR, mig.RUN_CONFIGS
            model_dir = Path(td) / "M"
            model_dir.mkdir()
            with open(model_dir / "f.csv", "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=["id", "answer", "gold_answer", "correct"])
                w.writeheader()
                w.writerow({"id": "28-0007", "answer": "A", "gold_answer": "A", "correct": "1"})
            mig.MIGRATION_PLAN = [("M", "m", [("f.csv", "ds", "MC-9", "mc")])]
            mig.RESULTS_DIR = Path(td)
            mig.RUN_CONFIGS = {"MC-9": {"temperature": 0.0, "seed": 42, "max_tokens": 4,
                                        "workers": 4, "prompt_style": "build_prompt"}}
            orig_seed = mig.seed
            mig.seed = lambda db: {"models": 0, "datasets": 0}
            try:
                counts = migrate(FakeDB(), card_hash="h")
                self.assertEqual(counts, {"runs": 1, "items": 1})
            finally:
                mig.seed = orig_seed
                mig.MIGRATION_PLAN = old_plan
                mig.RESULTS_DIR = old_dir
                mig.RUN_CONFIGS = old_cfg

    def test_migrate_aborts_on_count_mismatch(self):
        import csv as _csv

        class LyingColl:
            def update_one(self, flt, upd, upsert=False):
                pass

            def count_documents(self, flt):
                return 0

            def create_index(self, *a, **k):
                pass

        class LyingDB(dict):
            def __getitem__(self, k):
                if k not in self:
                    self[k] = LyingColl()
                return dict.__getitem__(self, k)

        with tempfile.TemporaryDirectory() as td:
            from code_benchmark import migrate_results_to_mongo as mig
            old_plan, old_dir, old_cfg = mig.MIGRATION_PLAN, mig.RESULTS_DIR, mig.RUN_CONFIGS
            model_dir = Path(td) / "M"
            model_dir.mkdir()
            with open(model_dir / "f.csv", "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=["id", "answer", "gold_answer", "correct"])
                w.writeheader()
                w.writerow({"id": "28-0007", "answer": "A", "gold_answer": "A", "correct": "1"})
            mig.MIGRATION_PLAN = [("M", "m", [("f.csv", "ds", "MC-9", "mc")])]
            mig.RESULTS_DIR = Path(td)
            mig.RUN_CONFIGS = {"MC-9": {"temperature": 0.0, "seed": 42, "max_tokens": 4,
                                        "workers": 4, "prompt_style": "build_prompt"}}
            orig_seed = mig.seed
            mig.seed = lambda db: {"models": 0, "datasets": 0}
            try:
                with self.assertRaises(SystemExit):
                    migrate(LyingDB(), card_hash="h")
            finally:
                mig.seed = orig_seed
                mig.MIGRATION_PLAN = old_plan
                mig.RESULTS_DIR = old_dir
                mig.RUN_CONFIGS = old_cfg


class TestHarnessRunner(unittest.TestCase):
    """The omp harness arm (run_harness_eval.py) — offline, no endpoint needed.

    Guards the four things that would silently invalidate the arm-vs-arm
    comparison: the measured condition (argv), the sandbox isolation (no gold on
    disk), the frozen parser delegation (no second parser), and the checkpoint
    namespace (one condition per slug).
    """

    def _argv(self, **kw):
        base = dict(omp_bin="omp", model="iec/Qwen3.5-9B-28K", prompt="P",
                    workdir=Path("sandbox/one"), tools="read,bash", max_time=180,
                    thinking="off", system_prompt=None)
        base.update(kw)
        return harness.build_argv(**base)

    def test_argv_pins_the_measured_condition(self):
        argv = self._argv()
        # reproducibility: no session file, no title model call, no user config
        for flag in ("--no-session", "--no-title", "--no-extensions", "--no-skills",
                     "--no-rules", "--no-lsp"):
            self.assertIn(flag, argv)
        self.assertIn("--tools", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "read,bash")
        self.assertIn("--auto-approve", argv)
        self.assertEqual(argv[argv.index("--max-time") + 1], "180")
        self.assertEqual(argv[argv.index("--cwd") + 1], "sandbox/one")
        self.assertEqual(argv[-1], "P")

    def test_argv_never_grants_extra_directories(self):
        # --add-dir would hand the model the repo (and with it the answer keys)
        argv = self._argv()
        self.assertNotIn("--add-dir", argv)
        self.assertEqual(argv.count("--cwd"), 1)

    def test_argv_no_tools_condition_drops_the_tool_menu(self):
        # the H1 ablation must send NO tool schemas at all, not an empty list
        for spelling in harness.NO_TOOLS:
            argv = self._argv(tools=spelling)
            self.assertIn("--no-tools", argv)
            self.assertNotIn("--tools", argv)
        full = self._argv(tools="read,bash")
        self.assertNotIn("--no-tools", full)

    def test_argv_all_condition_omits_the_tool_flag(self):
        # the as-shipped condition: neither --tools nor --no-tools, so omp's own
        # default menu runs. Omitting the flag IS the condition — not an empty menu.
        for spelling in harness.ALL_TOOLS:
            argv = self._argv(tools=spelling)
            self.assertNotIn("--tools", argv)
            self.assertNotIn("--no-tools", argv)
            self.assertEqual(argv[-1], "P")     # argv still well-formed

    def test_resolve_tools_is_three_valued_and_labelled(self):
        # the label is what a ledger row records, so it must distinguish the three
        self.assertEqual(harness.resolve_tools("none"), (["--no-tools"], "none"))
        self.assertEqual(harness.resolve_tools("all"), ([], "all"))
        self.assertEqual(harness.resolve_tools("read,bash"),
                         (["--tools", "read,bash"], "read,bash"))
        self.assertEqual(harness.resolve_tools(" ALL "), ([], "all"))

    def _vbench_dir(self, tmp, files):
        d = Path(tmp) / "arm"
        d.mkdir()
        for name, rows in files.items():
            with open(d / name, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        return d

    def _vb_rows(self, ids, track, answers):
        return [{"id": i, "domain": "d", "track": track, "question": "q",
                 "raw_response": "r", "answer": a}
                for i, a in zip(ids, answers, strict=True)]

    def test_vbench_validity_picks_the_agentic_checkpoint(self):
        # regression: "latest = biggest count" picked the 4.141-row mc file for
        # the agentic compare, so the arms shared no items
        with tempfile.TemporaryDirectory() as tmp:
            d = self._vbench_dir(tmp, {
                "vbench_result_1000_T65.csv":
                    self._vb_rows(["8142", "8143"], "agentic", ['[{"f":{}}]', ""]),
                "vbench_result_4141_T65.csv":
                    self._vb_rows(["1", "2"], "mc", ["A", "B"]),
            })
            got = harness._vbench_validity(d, "T65", "vbench_agentic",
                                            harness_arm=False)
            self.assertEqual(got, {"8142": 1, "8143": 0})

    def test_vbench_mc_letters_skips_a_bigger_agentic_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._vbench_dir(tmp, {
                "vbench_result_5000_T65.csv":
                    self._vb_rows(["8142"], "agentic", ['[{"f":{}}]']),
                "vbench_result_4141_T65.csv":
                    self._vb_rows(["1", "2"], "mc", ["A", ""]),
            })
            got = harness._vbench_mc_letters(d, "T65", harness_arm=False)
            self.assertEqual(got, {"1": "A", "2": ""})

    def test_vbench_readers_split_a_mixed_track_all_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._vbench_dir(tmp, {
                "vbench_result_5141_T65.csv":
                    self._vb_rows(["8142"], "agentic", ['[{"f":{}}]']) +
                    self._vb_rows(["1"], "mc", ["C"]),
            })
            self.assertEqual(
                harness._vbench_validity(d, "T65", "vbench_agentic",
                                          harness_arm=False), {"8142": 1})
            self.assertEqual(
                harness._vbench_mc_letters(d, "T65", harness_arm=False), {"1": "C"})

    def test_argv_minimal_persona_condition_replaces_the_system_prompt(self):
        # H3 changes exactly ONE variable against the full-tool arm
        argv = self._argv(system_prompt=harness.MINIMAL_SYSTEM_PROMPT)
        self.assertIn("--system-prompt", argv)
        self.assertEqual(argv[argv.index("--system-prompt") + 1],
                         harness.MINIMAL_SYSTEM_PROMPT)
        self.assertIn("--tools", argv)          # tool menu kept
        self.assertNotIn("--no-tools", argv)
        # the sentinel resolves to the one definition in code
        args = argparse.Namespace(system_prompt="minimal")
        self.assertEqual(harness.resolve_system_prompt(args),
                         harness.MINIMAL_SYSTEM_PROMPT)
        self.assertEqual(harness.resolve_system_prompt(
            argparse.Namespace(system_prompt="MINIMAL ")), harness.MINIMAL_SYSTEM_PROMPT)
        self.assertIsNone(harness.resolve_system_prompt(
            argparse.Namespace(system_prompt=None)))   # H2 keeps omp's own
        self.assertEqual(harness.resolve_system_prompt(
            argparse.Namespace(system_prompt="You are a tax lawyer.")),
            "You are a tax lawyer.")

    def _stream(self, *events):
        return [json.dumps(e, ensure_ascii=False) for e in events]

    def _assistant(self, blocks, stop="stop", usage=None):
        return {"type": "message_end", "message": {
            "role": "assistant", "content": blocks, "stopReason": stop,
            "usage": usage or {"input": 10, "output": 2, "cacheRead": 0}}}

    def test_parse_transcript_reads_answer_usage_and_turns(self):
        lines = self._stream(
            {"type": "turn_start"},
            self._assistant([{"type": "text", "text": "B"}],
                            usage={"input": 11841, "output": 3, "cacheRead": 0}),
            {"type": "turn_end"})
        events, text, stats = harness.parse_transcript(lines)
        self.assertEqual(text, "B")
        self.assertEqual(stats["turns"], 1)
        self.assertEqual(stats["input_tokens"], 11841)
        self.assertEqual(stats["output_tokens"], 3)
        self.assertEqual(stats["tool_calls"], 0)
        self.assertEqual(stats["stop_reason"], "stop")
        self.assertEqual(len(events), 3)

    def test_parse_transcript_keeps_last_text_and_counts_tool_calls(self):
        lines = self._stream(
            {"type": "turn_start"},
            self._assistant([{"type": "text", "text": "đang kiểm tra"},
                             {"type": "toolCall", "name": "bash",
                              "arguments": {"command": "ls"}}]),
            {"type": "turn_start"},
            self._assistant([{"type": "text", "text": "A"}]),
        )
        _, text, stats = harness.parse_transcript(lines)
        self.assertEqual(text, "A")            # the LAST message is the answer
        self.assertEqual(stats["tool_calls"], 1)
        self.assertEqual(stats["tool_names"], ["bash"])
        self.assertEqual(stats["turns"], 2)

    def test_parse_transcript_survives_non_json_noise(self):
        lines = ["omp: warming up", "", "not json either"] + self._stream(
            self._assistant([{"type": "text", "text": "C"}]))
        _, text, stats = harness.parse_transcript(lines)
        self.assertEqual(text, "C")
        self.assertEqual(stats["input_tokens"], 10)

    def test_audit_flags_network_from_model_output_only(self):
        events = [self._assistant([{"type": "text", "text": "tôi sẽ dùng curl https://x.io"}])]
        net, esc = harness.audit_transcript(events)
        self.assertIn("curl", net)
        self.assertEqual(esc, "")             # prose is not a filesystem escape

    def test_audit_flags_path_escape_only_from_tool_calls(self):
        events = [self._assistant([{"type": "toolCall", "name": "read",
                                     "arguments": {"path": "/home/x/all_res/gold.csv"}}])]
        net, esc = harness.audit_transcript(events)
        self.assertEqual(net, "")
        self.assertIn("/home/", esc)
        self.assertIn("all_res", esc)

    def test_audit_ignores_the_runners_own_argv_and_prompt(self):
        # regression: scanning the whole transcript flagged every item, because
        # argv carries the repo path and the prompt carries '../'-style text
        events = [{"type": "session", "cwd": "/home/nttung245/Downloads/Research/VMLU"},
                  self._assistant([{"type": "text", "text": "đọc data/ và vmlu_mqa"}])]
        self.assertEqual(harness.audit_transcript(events), ("", ""))

    def test_sandbox_payload_never_carries_gold(self):
        item = {"item_id": "LG-0001", "kind": "mc", "prompt": "P", "gold": "B",
                "dataset": "legal_mc", "stratum": "legal", "question": "Q",
                "prompt_sha256": "x"}
        payload = harness.sandbox_payload(item)
        self.assertNotIn("gold", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(payload["prompt"], "P")

    def test_diagnose_names_the_failure_without_repairing(self):
        good = {"exit_code": 0, "raw_response": "B", "kind": "mc", "answer": "B"}
        self.assertEqual(harness.diagnose(good, ""), "")
        self.assertIn("unparsed", harness.diagnose(dict(good, answer=""), ""))
        self.assertIn("empty", harness.diagnose(dict(good, raw_response="", answer=""), ""))
        self.assertIn("exit 1", harness.diagnose(dict(good, exit_code=1), "boom"))
        self.assertTrue(harness.diagnose(
            {"exit_code": 0, "raw_response": "  ", "kind": "reading", "answer": ""}, ""))

    def test_mcnemar_known_values(self):
        self.assertEqual(harness._mcnemar_p(0, 0), 1.0)
        self.assertAlmostEqual(harness._mcnemar_p(5, 0), 2 * (0.5 ** 5), places=9)
        self.assertAlmostEqual(harness._mcnemar_p(10, 10), 1.0, places=6)
        self.assertLess(harness._mcnemar_p(20, 2), 0.01)

    def test_paired_bootstrap_is_deterministic_and_brackets_the_shift(self):
        diffs = [1] * 30 + [0] * 70
        lo1, hi1 = harness._paired_bootstrap(diffs, iters=2000, seed=42)
        lo2, hi2 = harness._paired_bootstrap(diffs, iters=2000, seed=42)
        self.assertEqual((lo1, hi1), (lo2, hi2))          # same seed -> same interval
        self.assertLessEqual(lo1, 30.0)                   # mean shift = +30 points
        self.assertGreaterEqual(hi1, 30.0)
        self.assertEqual(harness._paired_bootstrap([0] * 50, iters=500, seed=1), (0.0, 0.0))

    def test_harness_checkpoint_namespace_is_never_shared(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prefix = "harness_reading400_result_"
            name = harness.checkpoint_name("ompH2_Qwen3.5-9B-28K", 25, prefix=prefix)
            self.assertEqual(name, f"{prefix}25_ompH2_Qwen3_5-9B-28K.csv")
            (tmp / name).touch()
            (tmp / f"{prefix}400_ompH1_Qwen3_5-9B-28K.csv").touch()   # other condition
            (tmp / f"{prefix}400.csv").touch()                        # legacy, no identity
            found = find_latest_checkpoint(tmp, "ompH2_Qwen3.5-9B-28K", prefix=prefix)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, name)       # another condition is invisible
            self.assertIsNone(find_latest_checkpoint(tmp, "ompH9_other", prefix=prefix))

    def _rows(self, n=3):
        return [{c: "" for c in harness.LEDGER_COLS} | {
            "dataset": "squad", "item_id": str(i), "stratum": "short-direct",
            "kind": "reading", "question": f"Q{i}?", "gold": "GOLD",
            "raw_response": "GOLD", "answer": "GOLD", "correct": 1, "em": 1,
            "f1": "1.000000"} for i in range(n)]

    def test_projection_reading_is_gold_joinable(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            items = {str(i): {"prompt": "ctx " * 10} for i in range(3)}
            path = harness.write_projection(self._rows(), "reading400", "reading",
                                            "ompH2_X", folder, items)
            self.assertEqual(path.name, "reading_answers_ompH2_X.csv")
            got = read_csv_rows(path)
            self.assertEqual(list(got[0]), harness.ANSWER_COLS)
            # the frozen scorer joins gold on (dataset, item_id) -> the SOURCE
            # dataset name must survive the projection, not the arm's own name
            self.assertEqual({r["dataset"] for r in got}, {"squad"})

    def test_projection_mc_keeps_the_frozen_columns(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            rows = self._rows(1)
            rows[0].update({"dataset": "legal_mc", "kind": "mc", "answer": "B",
                            "gold": "B", "correct": 1})
            path = harness.write_projection(rows, "legal_mc", "mc", "ompH2_X", folder,
                                            {"0": {"prompt": "PROMPT"}})
            got = read_csv_rows(path)
            self.assertEqual(list(got[0]), ["id", "question", "prompt", "raw_response",
                                            "answer", "gold_answer", "correct"])
            self.assertEqual(got[0]["prompt"], "PROMPT")
            self.assertEqual(got[0]["answer"], "B")

    def test_mc_eval_path_accepts_both_arm_namings(self):
        # arm-vs-arm comparison: harness arms write the dataset-qualified name,
        # the historical direct-prompt runs carry their own infix
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            legacy = folder / harness.ARM_A["legal_mc"]["eval"].format(a="Qwen3_5-9B-28K")
            legacy.write_text("id\n", encoding="utf-8")
            self.assertEqual(
                harness._mc_eval_path(folder, "legal_mc", "Qwen3_5-9B-28K"), legacy)
            harness_dir = folder / "ompH2_Qwen3_5-9B-28K"
            harness_dir.mkdir()
            modern = harness_dir / "full_evaluation_legal_mc_ompH2_Qwen3_5-9B-28K.csv"
            modern.write_text("id\n", encoding="utf-8")
            self.assertEqual(
                harness._mc_eval_path(harness_dir, "legal_mc", "ompH2_Qwen3_5-9B-28K"), modern)
            with self.assertRaises(SystemExit):     # neither naming present
                harness._mc_eval_path(harness_dir, "legal_nli", "ompH9_x")

    def test_scaffold_leak_guard_points_at_the_global_append(self):
        # PI_CODING_AGENT_DIR does NOT stop omp reading the DEFAULT agent dir's
        # APPEND_SYSTEM.md; the runner must say so out loud (card MC-22)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            default = root / "default_agent"
            custom = root / "custom_agent"
            default.mkdir()
            custom.mkdir()
            (default / "APPEND_SYSTEM.md").write_text("# Global reply style\n", encoding="utf-8")
            orig = harness.DEFAULT_SYSTEM_AGENT_DIR
            harness.DEFAULT_SYSTEM_AGENT_DIR = default
            try:
                with self.assertLogs("root", level="WARNING") as cm:
                    found = harness.warn_about_scaffold_leaks(custom)
                self.assertEqual(len(found), 1)
                self.assertIn("SCAFFOLD LEAK", "\n".join(cm.output))
                # the default dir itself is not a leak, and a clean machine is silent
                self.assertEqual(harness.warn_about_scaffold_leaks(default), [])
                (default / "APPEND_SYSTEM.md").unlink()
                with self.assertNoLogs("root", level="WARNING"):
                    self.assertEqual(harness.warn_about_scaffold_leaks(custom), [])
            finally:
                harness.DEFAULT_SYSTEM_AGENT_DIR = orig

    # ── speed / token cost probe ─────────────────────────────────────────
    def _cost_row(self, arm, wall, prompt, completion, overhead=0.0, workers=4):
        row = {c: "" for c in harness.SPEED_COLS}
        row.update({"arm": arm, "dataset": "legal_mc", "item_id": "LG-0001",
                    "kind": "mc", "workers": workers, "wall_s": wall, "model_s": wall,
                    "overhead_s": overhead, "ttft_s": "", "calls": 1,
                    "prompt_tokens": prompt, "fresh_prompt_tokens": prompt,
                    "cache_read_tokens": 0, "completion_tokens": completion, "note": ""})
        return row

    def test_speed_summary_reports_means_not_medians_of_the_ratio(self):
        rows = ([self._cost_row("A_direct", 1.0, 200, 2) for _ in range(4)]
                + [self._cost_row("B_omp_h2", 10.0, 12000, 200, overhead=4.0) for _ in range(4)])
        summary = harness._speed_summary(rows, "legal_mc", 4)
        self.assertEqual([s["arm"] for s in summary], ["A_direct", "B_omp_h2"])
        a, b = summary
        self.assertEqual(a["wall_mean_s"], "1.00")
        self.assertEqual(b["wall_mean_s"], "10.00")
        self.assertEqual(b["overhead_s_per_item"], "4.00")   # harness process cost
        self.assertEqual(b["total_tok_per_item"], "12200")
        # throughput is per-worker, so it scales with the pool
        self.assertEqual(a["items_per_min"], f"{60.0 / 1.0 * 4:.1f}")
        self.assertEqual(b["items_per_min"], f"{60.0 / 10.0 * 4:.1f}")

    def test_speed_summary_ignores_rows_from_another_worker_count(self):
        rows = [self._cost_row("B_omp_h2", 10.0, 12000, 200, workers=1)]
        self.assertEqual(harness._speed_summary(rows, "legal_mc", 4), [])

    def test_pct_is_a_nearest_rank_percentile(self):
        vals = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(harness._pct(vals, 0.0), 1.0)
        self.assertEqual(harness._pct(vals, 0.5), 3.0)
        self.assertEqual(harness._pct(vals, 1.0), 4.0)       # never out of range
        self.assertTrue(math.isnan(harness._pct([], 0.5)))

    def test_cost_token_is_read_from_the_agent_dir_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as td:
            agent = Path(td)
            (agent / ".env").write_text('OTHER=1\nIEC_LLM_API_KEY="sk-test-123"\n',
                                        encoding="utf-8")
            args = argparse.Namespace(cost_base_url=None, cost_model=None,
                                      cost_api_key=None, agent_dir=agent)
            url, key, model = harness.resolve_cost_endpoint(args)
            self.assertEqual(key, "sk-test-123")
            self.assertEqual(url, harness.COST_BASE_URL)
            self.assertEqual(model, harness.COST_MODEL)
            # explicit flags win; no .env and no env var must fail fast, not guess
            (agent / ".env").unlink()
            args.cost_api_key = "sk-flag"
            self.assertEqual(harness.resolve_cost_endpoint(args)[1], "sk-flag")
            args.cost_api_key = None
            with unittest.mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(SystemExit):
                    harness.resolve_cost_endpoint(args)


class TestCaptureScaffoldUpstream(unittest.TestCase):
    """The pinning proxy's upstream guard: https by default, plain http only
    with the explicit opt-in (provider-documented LAN endpoint inside a VPN)."""

    def test_https_upstream_passes_and_strips_slash(self):
        self.assertEqual(
            scaffold.check_upstream("https://llmapi.iec-uit.com/v1/", False),
            "https://llmapi.iec-uit.com/v1")

    def test_http_upstream_needs_the_opt_in(self):
        with self.assertRaises(SystemExit):
            scaffold.check_upstream("http://llmapi.iec/v1", False)
        self.assertEqual(scaffold.check_upstream("http://llmapi.iec/v1", True),
                         "http://llmapi.iec/v1")

    def test_non_http_scheme_never_passes(self):
        for url in ("ftp://x/v1", "llmapi.iec/v1", ""):
            with self.assertRaises(SystemExit):
                scaffold.check_upstream(url, True)


class TestHarnessDashboard(unittest.TestCase):
    """build_dashboard_harness.py — the block every harness number is displayed from."""

    ARM = [("k", "ompH5clean_X", "H5", "omp sạch", "MC-22")]

    def _write_arm(self, results_dir: Path, slug: str, *, n: int, correct: int,
                   compare_delta: float = -10.0, ci=(0.0, 0.0), p: str = "0.01"):
        """One arm's artifacts exactly where build_ladder looks for them."""
        folder = results_dir / slug
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / f"full_evaluation_legal_mc_{slug}.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "question", "prompt", "raw_response",
                                              "answer", "gold_answer", "correct"])
            w.writeheader()
            for i in range(n):
                w.writerow({"id": f"LG-{i:04d}", "question": "q", "prompt": "p",
                            "raw_response": "A", "answer": "A", "gold_answer": "A",
                            "correct": 1 if i < correct else 0})
        with open(folder / f"harness_compare_legal_mc_vsA_{slug}.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=harness.COMPARE_COLS)
            w.writeheader()
            w.writerow({"metric": "accuracy", "group": "ALL", "n": n, "arm_a": "86.00",
                        "arm_b": f"{100.0 * correct / n:.2f}", "delta": f"{compare_delta}",
                        "ci95_low": f"{ci[0]}", "ci95_high": f"{ci[1]}", "mcnemar_p": p,
                        "a_only": 1, "b_only": 0, "both": correct, "neither": 0,
                        "arm_b_failures": 0, "measurement_card_hash": "h"})

    def test_ladder_cross_checks_the_compare_against_the_per_item_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_arm(root, "ompH5clean_X", n=10, correct=7)
            ladder, _costs = dash.build_ladder(root, self.ARM)
            self.assertEqual(len(ladder), 1)
            row = ladder[0]
            self.assertEqual((row["role"], row["n"], row["arm_b"]), ("harness", 10, 70.0))
            self.assertEqual(row["dataset"], "legal_mc")

    def test_ladder_aborts_when_the_compare_disagrees_with_the_items(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_arm(root, "ompH5clean_X", n=10, correct=7)
            # a hand-edited compare claiming a different score must not be displayed
            path = root / "ompH5clean_X" / "harness_compare_legal_mc_vsA_ompH5clean_X.csv"
            rows = list(csv.DictReader(open(path, encoding="utf-8")))
            rows[0]["arm_b"] = "99.00"
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=harness.COMPARE_COLS)
                w.writeheader()
                w.writerows(rows)
            with self.assertRaises(SystemExit) as ctx:
                dash.build_ladder(root, self.ARM)
            self.assertIn("recompute", str(ctx.exception))

    def test_ladder_aborts_on_an_inverted_ci(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_arm(root, "ompH5clean_X", n=10, correct=7, ci=(5.0, -5.0))
            with self.assertRaises(SystemExit) as ctx:
                dash.build_ladder(root, self.ARM)
            self.assertIn("CI", str(ctx.exception))

    def test_ladder_requires_a_compare_for_every_harness_arm(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_arm(root, "ompH5clean_X", n=10, correct=7)
            (root / "ompH5clean_X" / "harness_compare_legal_mc_vsA_ompH5clean_X.csv").unlink()
            with self.assertRaises(SystemExit) as ctx:
                dash.build_ladder(root, self.ARM)
            self.assertIn("compare", str(ctx.exception))

    def test_cost_aggregates_every_dataset_of_an_arm(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "ompH5clean_X"
            folder.mkdir(parents=True)
            for dataset, n in (("legal_mc", 3), ("reading400", 2)):
                with open(folder / f"harness_ledger_{dataset}_ompH5clean_X.csv", "w",
                          newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=harness.LEDGER_COLS)
                    w.writeheader()
                    for i in range(n):
                        row = {c: "" for c in harness.LEDGER_COLS}
                        row.update({"dataset": dataset, "item_id": str(i), "kind": "mc",
                                    "wall_s": "2.0", "turns": "1", "tool_calls": "0",
                                    "input_tokens": "10", "cache_read_tokens": "0",
                                    "output_tokens": "2", "failure": ""})
                        if i == 0:
                            row["tool_calls"] = "1"      # first row of each dataset
                        w.writerow(row)
            cost = dash.arm_cost(folder, ["legal_mc", "reading400"])
            self.assertEqual(cost["n"], 5)
            self.assertEqual(cost["tool_use_items"], 2)   # first row of each dataset
            self.assertEqual(cost["wall_s_per_item"], 2.0)
            self.assertEqual(cost["completion_tokens"], 10)
            self.assertEqual(cost["datasets"], 2)

    def _write_vbench_mc_checkpoint(self, root: Path, slug: str,
                                    letters: dict[str, str]) -> None:
        """The direct arm's V-Bench MC checkpoint, where _vbench_mc_letters reads it."""
        folder = root / slug
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / f"vbench_result_1_{slug}.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "answer"])
            w.writeheader()
            for iid, letter in letters.items():
                w.writerow({"id": iid, "answer": letter})

    def test_vbench_mc_harness_arm_without_a_ledger_is_not_a_perfect_score(self):
        # A harness arm that declares vbench_mc but has no ledger is an unfinished
        # run. The ONLY arm allowed to score 100 by self-agreement is the direct
        # arm; the harness side must return None so build_ladder's declared-
        # coverage guard aborts instead of showing a perfect agreement nobody made.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_vbench_mc_checkpoint(root, "A", {"1": "A", "2": "B"})
            (root / "H").mkdir()
            self.assertIsNone(dash.arm_metrics(root / "H", "vbench_mc",
                                               dash.ARM_A["vbench_mc"], "H", arm_a_slug="A"))

    def test_vbench_mc_direct_arm_still_agrees_with_itself(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_vbench_mc_checkpoint(root, "A", {"1": "A", "2": "", "3": "B"})
            own = dash.arm_metrics(root / "A", "vbench_mc", dash.ARM_A["vbench_mc"], "A",
                                   arm_a_slug="A")
            assert own is not None
            self.assertEqual((own["n"], own["score"], own["blanks"]), (3, 100.0, 0))

    def test_vbench_mc_reads_arm_a_from_the_same_results_root(self):
        # The module's RESULTS_DIR points at the real repo (no fixture slug "A"
        # there). A caller's --results-dir must be the only root consulted, or the
        # agreement number silently comes from a different directory.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_vbench_mc_checkpoint(root, "A", {"1": "A", "2": "B"})
            h = root / "H"
            h.mkdir()
            with open(h / "harness_ledger_vbench_mc_H.csv", "w", newline="",
                      encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["item_id", "answer"])
                w.writeheader()
                w.writerow({"item_id": "1", "answer": "A"})
                w.writerow({"item_id": "2", "answer": "A"})
            own = dash.arm_metrics(h, "vbench_mc", dash.ARM_A["vbench_mc"], "H",
                                   arm_a_slug="A")
            assert own is not None
            self.assertEqual((own["n"], own["score"]), (2, 50.0))

    def test_insight_never_mixes_agreement_into_the_score_range(self):
        # V-Bench MC's agreement delta is "the answer changed", not "the answer got
        # worse": the verdict and the penalty claims talk about "điểm", so the row
        # must stay out of them (it still lives in the comparison table).
        def row(model, arm, dataset, label, metric, delta, lo, hi):
            return {"role": "harness", "arm": arm, "arm_slug": f"{arm}_{model}",
                    "model": model, "dataset": dataset, "dataset_label": label,
                    "metric": metric, "n": 400, "delta": delta,
                    "ci95_low": lo, "ci95_high": hi}

        ladder = [
            row("M1", "H5", "reading400", "reading-400 (EM)", "EM", 7.0, 3.5, 10.5),
            row("M1", "H5", "vbench_mc",
                "V-Bench MC 12 domain (mức trùng khớp với arm A — KHÔNG có gold)",
                "agreement", -22.39, -23.4, -20.91),
            row("M2", "M6", "reading400", "reading-400 (EM)", "EM", -22.25, -25.0, -19.0),
        ]
        ins = dash.insight(ladder, [], [], [])
        blob = ins["verdict"] + " " + " ".join(c["body"] for c in ins["claims"])
        self.assertNotIn("22.39", blob)
        penalty = next(c for c in ins["claims"] if c["id"] == "penalty:M1")
        ev = {e["label"]: e["value"] for e in penalty["evidence"]}
        self.assertEqual(ev["Δ nhỏ nhất"], "+7.00")
        self.assertIn("trên 1 tập", penalty["body"])

    def test_comparison_carries_blanks_per_side(self):
        # 1.1: số câu trống/unparseable của mỗi phía đi theo dòng so sánh để
        # trang hiện mà không phải đoán lại từ đâu.
        def row(role, arm, blanks):
            return {"role": role, "arm": arm, "arm_slug": f"{arm}_M9",
                    "model": "M9", "dataset": "legal_mc", "dataset_label": "legal-MC",
                    "metric": "accuracy", "n": 146, "arm_a": 89.0, "arm_b": 74.0,
                    "delta": -15.0, "ci95_low": -21.0, "ci95_high": -9.0,
                    "mcnemar_p": "0.01", "both": 100, "a_only": 20, "b_only": 2,
                    "neither": 24, "char_f1": None, "blanks": blanks,
                    "label": arm, "card": None}
        real_rep = dict(dash.REPRESENTATIVE)
        real_model = dict(dash.ARM_MODEL)
        dash.REPRESENTATIVE["M9"] = "HB"
        dash.ARM_MODEL["HB"] = "M9"
        try:
            ins = dash.insight([row("baseline", "A9", 3), row("harness", "HB", 12)],
                               [], [], [])
        finally:
            dash.REPRESENTATIVE.clear(); dash.REPRESENTATIVE.update(real_rep)
            dash.ARM_MODEL.clear(); dash.ARM_MODEL.update(real_model)
        self.assertEqual(len(ins["comparison"]), 1)
        self.assertEqual((ins["comparison"][0]["a_blanks"],
                          ins["comparison"][0]["b_blanks"]), (3, 12))

    def test_breakdown_cuts_by_stratum_with_the_same_predicate(self):
        # 1.2: per-group rows reuse the ALL predicate; groups partition shared.
        import code_benchmark.run_harness_eval as harness_mod
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "ompX_M"
            (root / slug).mkdir()
            with open(root / slug / f"harness_ledger_reading400_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["dataset", "item_id", "stratum"])
                w.writeheader()
                w.writerow({"dataset": "squad", "item_id": "1", "stratum": "short-direct"})
                w.writerow({"dataset": "squad", "item_id": "2", "stratum": "short-direct"})
                w.writerow({"dataset": "squad", "item_id": "3", "stratum": ""})
            old = harness_mod.RESULTS_DIR
            harness_mod.RESULTS_DIR = root
            try:
                a = {"squad:1": 1, "squad:2": 0, "squad:3": 1}
                b = {"squad:1": 0, "squad:2": 0, "squad:3": 1}
                rows = harness_mod._breakdown_rows(
                    "reading400", slug, a, b, list(a), "reading", "EM", "hash")
            finally:
                harness_mod.RESULTS_DIR = old
        by_group = {r["group"]: r for r in rows}
        self.assertEqual(set(by_group), {"short-direct", "unknown"})
        self.assertEqual(by_group["short-direct"]["n"], 2)
        self.assertEqual(by_group["unknown"]["n"], 1)
        self.assertEqual(sum(r["n"] for r in rows), 3)

    def test_breakdown_skips_gracefully_when_ledger_covers_nothing(self):
        # Ledger from a different run covering none of the shared keys: loud,
        # not a vacuous single-"unknown"-group cut.
        import code_benchmark.run_harness_eval as harness_mod
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "ompX_M"
            (root / slug).mkdir()
            with open(root / slug / f"harness_ledger_legal_mc_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["item_id", "stratum"])
                w.writeheader()
                w.writerow({"item_id": "OTHER-1", "stratum": "legal"})
            old = harness_mod.RESULTS_DIR
            harness_mod.RESULTS_DIR = root
            try:
                with self.assertRaises(SystemExit):
                    harness_mod._breakdown_rows(
                        "legal_mc", slug, {"LG-0001": 1}, {"LG-0001": 1},
                        ["LG-0001"], "mc", "accuracy", "hash")
            finally:
                harness_mod.RESULTS_DIR = old

    def test_breakdown_skips_a_constant_stratum(self):
        import code_benchmark.run_harness_eval as harness_mod
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "ompX_M"
            (root / slug).mkdir()
            with open(root / slug / f"harness_ledger_legal_mc_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["item_id", "stratum"])
                w.writeheader()
                w.writerow({"item_id": "LG-0001", "stratum": "legal"})
                w.writerow({"item_id": "LG-0002", "stratum": "legal"})
            old = harness_mod.RESULTS_DIR
            harness_mod.RESULTS_DIR = root
            try:
                rows = harness_mod._breakdown_rows(
                    "legal_mc", slug, {"LG-0001": 1, "LG-0002": 0},
                    {"LG-0001": 1, "LG-0002": 1}, ["LG-0001", "LG-0002"],
                    "mc", "accuracy", "hash")
            finally:
                harness_mod.RESULTS_DIR = old
        self.assertEqual(rows, [])

    def test_builder_arg_credit_validates_the_fractions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "TMPSLUG"
            (root / slug).mkdir()
            cols = ["n_items", "n_attempted", "n_required_slots", "n_required_ok",
                    "required_fill_rate", "n_supplied", "n_supplied_ok",
                    "arg_precision", "n_unparseable"]
            good = {"n_items": 10, "n_attempted": 9, "n_required_slots": 18,
                    "n_required_ok": 17, "required_fill_rate": 94.44,
                    "n_supplied": 20, "n_supplied_ok": 19, "arg_precision": 95.0,
                    "n_unparseable": 1}
            with open(root / slug / f"vbench_arg_credit_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerow(good)
            out = dash.arg_credit(root, [("k", slug, "H5", "lbl", None)])
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["required_fill_rate"], 94.44)
            bad = dict(good, required_fill_rate=50.0)
            with open(root / slug / f"vbench_arg_credit_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerow(bad)
            with self.assertRaises(SystemExit):
                dash.arg_credit(root, [("k", slug, "H5", "lbl", None)])

    def test_builder_breakdown_groups_sum_to_all(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slug = "TMPSLUG"
            (root / slug).mkdir()
            with open(root / slug / f"harness_compare_reading400_vsA_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["metric", "group", "n", "arm_a",
                                                  "arm_b", "delta", "ci95_low",
                                                  "ci95_high", "mcnemar_p"])
                w.writeheader()
                w.writerow({"metric": "EM", "group": "ALL", "n": 3,
                            "arm_a": "66.67", "arm_b": "33.33", "delta": "-33.33",
                            "ci95_low": "-60.00", "ci95_high": "0.00",
                            "mcnemar_p": "0.5"})
            with open(root / slug / f"harness_breakdown_reading400_vsA_{slug}.csv",
                      "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["metric", "group", "n", "arm_a",
                                                  "arm_b", "delta", "ci95_low",
                                                  "ci95_high", "mcnemar_p"])
                w.writeheader()
                w.writerow({"metric": "EM", "group": "g1", "n": 2,
                            "arm_a": "50.00", "arm_b": "0.00", "delta": "-50.00",
                            "ci95_low": "-70.00", "ci95_high": "-10.00",
                            "mcnemar_p": "0.5"})
                w.writerow({"metric": "EM", "group": "g2", "n": 1,
                            "arm_a": "100.00", "arm_b": "100.00", "delta": "+0.00",
                            "ci95_low": "0.00", "ci95_high": "0.00",
                            "mcnemar_p": "1"})
            out = dash.breakdown(root, [("k", slug, "H5", "lbl", None)])
            self.assertEqual(len(out), 1)
            self.assertEqual([g["group"] for g in out[0]["groups"]], ["g1", "g2"])
            self.assertEqual(out[0]["groups"][0]["delta"], -50.0)

    def test_stripped_answer_peels_the_wrapper_without_fixing_anything(self):        # SECONDARY metric only: the headline EM stays on the verbatim reply
        self.assertEqual(dash.stripped_answer("**1916**\n\n> Câu hỏi: ...\n> Trả lời: 1916"),
                         "1916")
        self.assertEqual(dash.stripped_answer("**Trả lời:** tổng hợp hạt nhân và phân rã"),
                         "tổng hợp hạt nhân và phân rã")
        self.assertEqual(dash.stripped_answer("**Verdict**: **C**\n\n**Why:** 1. …"), "C")
        self.assertEqual(dash.stripped_answer("1. Đáp án là A"), "Đáp án là A")
        self.assertEqual(dash.stripped_answer("```\nnoise\n```\n\n42"), "42")
        self.assertEqual(dash.stripped_answer(""), "")
        # a wrong answer is NOT rescued by stripping
        self.assertEqual(dash.stripped_answer("**3**"), "3")

    def test_render_html_escapes_labels_and_shows_the_leak_banner(self):
        block = dash.build_block.__wrapped__ if hasattr(dash.build_block, "__wrapped__") else None
        self.assertIsNone(block)   # build_block is not wrapped; build the block by hand
        minimal = {
            "benchmark_name": "<script>x</script>", "date": "2026-09-26",
            "model_id": "m", "endpoint": "e", "harness": "h", "condition": "c",
            "measurement_card": "MC-22", "measurement_card_hash": "hash",
            "scorer": "s", "ladder": [dict(arm="H5", arm_slug="s", label="<b>omp</b>",
                                           card="MC-22", dataset="legal_mc",
                                           dataset_label="legal-MC", metric="accuracy",
                                           n=10, arm_a=86.0, arm_b=70.0, delta=-16.0,
                                           ci95_low=-20.0, ci95_high=-10.0, mcnemar_p="0.01",
                                           both=60, a_only=20, b_only=2, neither=8,
                                           char_f1=None, blanks=0, role="harness")],
            "cost": [], "speed": [],
            "totals": {"items_harness": 10, "failures": 0, "tool_use_items": 0,
                       "net_attempt_items": 0, "path_escape_items": 0},
            "leak": {"what": "w", "evidence": "e", "fix": "f", "guard": "g"},
            "caveats": ["<i>caveat</i>"], "sources": {"report": "r", "docs": "d"},
        }
        out = dash.render_html(minimal)
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("&lt;i&gt;caveat&lt;/i&gt;", out)
        self.assertIn("Guard:", out)            # the leak banner renders every field
        self.assertIn("Đọc MC-15", out)
        self.assertIn("-16.00", out)


    def test_vbench_validity_reads_the_harness_ledger_and_the_direct_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # harness arm: the ledger's per-item `valid` bit is authoritative
            hdir = root / "ompV1_X"
            hdir.mkdir()
            with open(hdir / "harness_ledger_vbench_agentic_ompV1_X.csv", "w", newline="",
                      encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=harness.LEDGER_COLS)
                w.writeheader()
                for iid, valid in (("101", 1), ("102", 0)):
                    row = {c: "" for c in harness.LEDGER_COLS}
                    row.update({"dataset": "vbench_agentic", "item_id": iid, "kind": "vbench",
                                "valid": valid, "answer": "{}" if valid else ""})
                    w.writerow(row)
            self.assertEqual(harness._vbench_validity(hdir, "ompV1_X", "vbench_agentic",
                                                      harness_arm=True),
                             {"101": 1, "102": 0})
            # direct arm: validity = the shipped answer cell was non-empty
            adir = root / "Qwen"
            adir.mkdir()
            (adir / "vbench_result_5141_Qwen.csv").write_text(
                "id,domain,track,question,raw_response,answer\n"
                "101,agentic,agentic,q,r,[{\"f\":{}}],[{\"f\":{}}]\n"
                "102,agentic,agentic,q,nope,\n", encoding="utf-8")
            self.assertEqual(harness._vbench_validity(adir, "Qwen", "vbench_agentic",
                                                      harness_arm=False),
                             {"101": 1, "102": 0})
            # no checkpoint at all -> None so the caller degrades to aggregate-only
            self.assertIsNone(harness._vbench_validity(root / "missing", "Qwen",
                                                        "vbench_agentic", harness_arm=False))

    def test_vbench_projection_writes_validity_summary_and_uploadable_submission(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / "arm"
            folder.mkdir()
            rows = []
            for iid, answer in (("7", '[{"f":{"a":1}}]'), ("3", "")):
                row = {c: "" for c in harness.LEDGER_COLS}
                row.update({"dataset": "vbench_agentic", "item_id": iid, "kind": "vbench",
                            "answer": answer, "valid": int(bool(answer)), "raw_response": "x"})
                rows.append(row)
            items = {r["item_id"]: {"prompt": "p"} for r in rows}
            summary = harness.write_projection(rows, "vbench_agentic", "vbench", "armX",
                                              folder, items)
            self.assertEqual(summary.name, "vbench_valid_summary_armX.csv")
            got = read_csv_rows(summary)
            self.assertEqual((got[0]["n"], got[0]["valid"], got[0]["valid_rate"]),
                             ("2", "1", "50.00"))
            sub = Path("submissions") / "armX" / "submission_vbench_armX.jsonl"
            try:
                lines = [json.loads(line) for line in sub.read_text(encoding="utf-8").splitlines()]
                # sorted by id, invalid rows ship an empty answer (never a guess)
                self.assertEqual([l["id"] for l in lines], [3, 7])
                self.assertEqual(lines[0]["answer"], "")
                self.assertEqual(lines[1]["answer"], [{"f": {"a": 1}}])
            finally:
                sub.unlink()
                sub.parent.rmdir()

    def test_repeatability_groups_a_cell_by_slug_without_the_model_suffix(self):
        # Regression: `(ompH\d+clean?)` REQUIRES the literal "clea" (the ? binds to
        # the n only), so ompH1…ompH4 never matched and every one of them fell back
        # to the full slug as its "cell" — which is what the display showed.
        cells = {}
        for slug in ("ompH1_Qwen3_5-9B-28K", "ompH2_Qwen3_5-9B-28K", "ompH3_Qwen3_5-9B-28K",
                     "ompH4_Qwen3_5-9B-28K", "ompH5clean_Qwen3_5-9B-28K",
                     "ompH5clean_r2_Qwen3_5-9B-28K", "ompH8clean_r3_Qwen3_5-9B-28K"):
            m = re.match(r"(ompH\d+(?:clean)?)(?:_r(\d+))?_Qwen", slug)
            self.assertIsNotNone(m, f"{slug} phải match được")
            cells[slug] = (m.group(1), int(m.group(2)) if m.group(2) else 1)
        self.assertEqual(cells["ompH1_Qwen3_5-9B-28K"][0], "ompH1")
        self.assertEqual(cells["ompH2_Qwen3_5-9B-28K"][0], "ompH2")
        self.assertEqual(cells["ompH5clean_Qwen3_5-9B-28K"], ("ompH5clean", 1))
        self.assertEqual(cells["ompH5clean_r2_Qwen3_5-9B-28K"], ("ompH5clean", 2))
        self.assertEqual(cells["ompH8clean_r3_Qwen3_5-9B-28K"], ("ompH8clean", 3))
        # a repeat must land in the SAME cell as its first run, or the spread is
        # computed across two "different" cells and the noise floor is fiction
        self.assertEqual(cells["ompH5clean_Qwen3_5-9B-28K"][0],
                         cells["ompH5clean_r2_Qwen3_5-9B-28K"][0])

    def test_speed_budget_table_has_a_vbench_entry(self):
        self.assertEqual(harness.ARM_A_MAX_TOKENS["vbench"], 512)
        self.assertEqual(harness.ARM_A["vbench_agentic"]["kind"], "vbench")

    def test_preflight_aborts_a_run_against_a_dead_gateway(self):
        # observed 2026-09-27: the IEC gateway accepted TCP but never answered
        # HTTP, so every item would have become a 180s "model failure"
        def boom(*a, **kw):
            raise TimeoutError("The read operation timed out")
        with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            with unittest.mock.patch("urllib.request.urlopen", boom):
                with self.assertRaises(SystemExit) as ctx:
                    harness.preflight_endpoint(timeout=0.01)
        msg = str(ctx.exception)
        self.assertIn("preflight failed", msg)
        self.assertIn("did not answer a 1-token call", msg)
        self.assertIn("--resume", msg)          # tells the operator nothing is lost

    def test_preflight_names_an_http_error_as_an_upstream_outage(self):
        # observed 2026-09-28: /v1/models answered but the inference backend was
        # down — a clean 502, which looks nothing like the earlier silence and
        # must not be reported as "the endpoint did not answer".
        import io
        import urllib.error

        def boom(*a, **kw):
            raise urllib.error.HTTPError("https://x/v1/chat/completions", 502, "Bad Gateway",
                                         {}, io.BytesIO(b'{"detail":"Error connecting to '
                                                              b'backend LLM server: "}'))
        with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            with unittest.mock.patch("urllib.request.urlopen", boom):
                with self.assertRaises(SystemExit) as ctx:
                    harness.preflight_endpoint(timeout=0.01)
        msg = str(ctx.exception)
        self.assertIn("HTTP 502 Bad Gateway", msg)
        self.assertIn("IS answering", msg)
        self.assertIn("upstream outage", msg)
        self.assertIn("Error connecting to backend LLM server", msg)   # the body is quoted
        self.assertNotIn("did not answer a 1-token call", msg)         # the other branch

    def test_preflight_passes_through_when_the_endpoint_answers(self):
        class FakeResp:
            def read(self):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            with unittest.mock.patch("urllib.request.urlopen", lambda *a, **kw: FakeResp()):
                harness.preflight_endpoint(timeout=1.0)   # must not raise

    def test_preflight_probes_the_arm_not_the_cost_pin(self):
        # A preflight aimed at a different gateway is a green light for a dead
        # run. `--model` is omp's provider-qualified name, so the probe has to
        # strip the prefix: the wire answers "Model is unavailable" otherwise.
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["body"] = json.loads(req.data.decode())
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}

            class FakeResp:
                def read(self):
                    return b"{}"
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return FakeResp()

        env = {"OPENAI_API_KEY": "sk-test", "OPENAI_BASE_URL": "https://example.test/v1",
               "OPENAI_EXTRA_HEADERS": json.dumps({"x-opencode-session": "s1"})}
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            with unittest.mock.patch("urllib.request.urlopen", fake_urlopen):
                harness.preflight_endpoint(model="zen-go/mimo-v2.5", api_key="k")
        self.assertEqual(seen["body"]["model"], "mimo-v2.5")
        self.assertEqual(seen["url"], "https://example.test/v1/chat/completions")
        # the gateway's own requirement has to ride along, or the probe records
        # a Cloudflare rejection instead of the answer
        self.assertEqual(seen["headers"].get("x-opencode-session"), "s1")


class TestScaffoldProjectInstructions(unittest.TestCase):
    """The AGENTS.md leak (measured 2026-09-29) — the guard that now stops it.

    The scratch default used to sit inside this repository, so omp walked up,
    found the repo's own AGENTS.md and inlined 27.5k characters of it into every
    item's system prompt. Every arm through MC-26 was measured that way. Nothing
    in the artifacts showed it, because the request bytes were never captured.
    """

    def test_finds_instructions_above_a_sandbox(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "AGENTS.md").write_text("x" * 100, encoding="utf-8")
            nested = Path(root) / "a" / "b" / "c"
            nested.mkdir(parents=True)
            found = harness.project_instructions_above(nested)
            self.assertTrue(any(p.endswith("AGENTS.md") for p in found))

    def test_a_sandbox_outside_any_project_is_clean(self):
        with tempfile.TemporaryDirectory() as scratch:
            # the tmp root itself must not sit under a repo; assert on the
            # specific files rather than trusting the environment
            found = [p for p in harness.project_instructions_above(Path(scratch))
                     if Path(p).parent in (Path(scratch).resolve().parents)]
            self.assertEqual(found, [])

    def test_refuses_a_sandbox_inside_a_project(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "CLAUDE.md").write_text("y" * 10, encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                harness.assert_no_project_instructions(Path(root), allow=False)
            msg = str(ctx.exception)
            self.assertIn("CLAUDE.md", msg)
            self.assertIn("--scratch", msg)
            self.assertIn("--allow-project-instructions", msg)

    def test_the_escape_hatch_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "AGENTS.md").write_text("z" * 10, encoding="utf-8")
            harness.assert_no_project_instructions(Path(root), allow=True)  # no raise

    def test_the_default_scratch_is_outside_the_repository(self):
        src = Path("code_benchmark/run_harness_eval.py").read_text(encoding="utf-8")
        self.assertNotIn('result_folder / "harness_scratch"', src)
        self.assertIn("tempfile.gettempdir()", src)


class TestExtraHeaders(unittest.TestCase):
    """OPENAI_EXTRA_HEADERS — the two gateway requirements a bare client lacks."""

    def test_absent_env_means_no_headers(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(llm.extra_headers())

    def test_parses_a_json_object(self):
        raw = json.dumps({"x-opencode-session": "abc", "Origin": "https://o.test"})
        with unittest.mock.patch.dict(os.environ, {"OPENAI_EXTRA_HEADERS": raw}, clear=True):
            self.assertEqual(llm.extra_headers()["x-opencode-session"], "abc")

    def test_invalid_json_fails_fast(self):
        with unittest.mock.patch.dict(os.environ, {"OPENAI_EXTRA_HEADERS": "{oops"}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                llm.extra_headers()
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_non_string_values_fail_fast(self):
        raw = json.dumps({"x-retry": 3})
        with unittest.mock.patch.dict(os.environ, {"OPENAI_EXTRA_HEADERS": raw}, clear=True):
            with self.assertRaises(SystemExit):
                llm.extra_headers()

    def test_a_non_object_fails_fast(self):
        with unittest.mock.patch.dict(os.environ, {"OPENAI_EXTRA_HEADERS": "[1,2]"}, clear=True):
            with self.assertRaises(SystemExit):
                llm.extra_headers()


class TestLegalArmA(unittest.TestCase):
    """The missing arm-A producer for the legal sets (`run_legal_arm_a.py`).

    Without it a second model cannot enter the harness arm at all, and the ladder
    silently degrades into a comparison between two different models.
    """

    def test_final_path_is_the_name_the_harness_reads(self):
        # derived from ARM_A, not re-typed: the writer and the reader must not drift
        for dataset, expect in (("legal_mc", "full_evaluation_legal_S.csv"),
                                ("legal_nli", "full_evaluation_nli_S.csv")):
            self.assertEqual(legal_arm_a.final_path(dataset, "S").name, expect)

    def test_prompt_parity_refuses_a_missing_reference(self):
        with self.assertRaises(SystemExit) as ctx:
            legal_arm_a.assert_prompt_parity(
                [{"item_id": "LG-0001", "prompt": "p"}], "legal_mc", "no-such-slug")
        self.assertIn("not found", str(ctx.exception))

    def test_prompt_parity_refuses_drift(self):
        with tempfile.TemporaryDirectory() as root:
            ref = Path(root) / "full_evaluation_legal_ref.csv"
            with open(ref, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id", "prompt"])
                w.writeheader()
                w.writerow({"id": "LG-0001", "prompt": "the bytes arm A sent"})
            with unittest.mock.patch.object(legal_arm_a, "RESULTS_DIR", Path(root)):
                with unittest.mock.patch.object(
                        legal_arm_a, "final_path",
                        lambda d, s: ref):
                    with self.assertRaises(SystemExit) as ctx:
                        legal_arm_a.assert_prompt_parity(
                            [{"item_id": "LG-0001", "prompt": "different bytes"}],
                            "legal_mc", "ref")
        self.assertIn("prompt drift", str(ctx.exception))

    def test_prompt_parity_accepts_identical_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            ref = Path(root) / "full_evaluation_legal_ref.csv"
            with open(ref, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id", "prompt"])
                w.writeheader()
                w.writerow({"id": "LG-0001", "prompt": "same bytes"})
            with unittest.mock.patch.object(legal_arm_a, "final_path", lambda d, s: ref):
                legal_arm_a.assert_prompt_parity(
                    [{"item_id": "LG-0001", "prompt": "same bytes"}], "legal_mc", "ref")

    def test_checkpoints_are_dataset_scoped(self):
        # two legal sets for one slug would otherwise fight over raw_result_<n>_<slug>
        self.assertNotEqual(legal_arm_a.CKPT_PREFIX.format(dataset="legal_mc"),
                            legal_arm_a.CKPT_PREFIX.format(dataset="legal_nli"))
        self.assertTrue(legal_arm_a.CKPT_PREFIX.format(dataset="legal_mc")
                        .startswith("raw_result_legal_mc_"))

    def test_a_smoke_run_never_writes_the_final_baseline_name(self):
        src = Path("code_benchmark/run_legal_arm_a.py").read_text(encoding="utf-8")
        self.assertIn(".smoke", src)   # --limit renames the output

    def test_resume_checkpoints_carry_the_resumed_rows_forward(self):
        """A checkpoint written after a --resume must hold the UNION of answers.

        find_latest_checkpoint picks the HIGHEST count, so if a resumed leg wrote
        only its own rows, the file it leaves behind is smaller than the one it
        replaced — and the next --resume loses the first leg. The reading and MC
        runners write the cumulative union; this producer must not be the odd one.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            res = root / "res"
            folder = res / "test-model"
            folder.mkdir(parents=True)
            with open(folder / "raw_result_legal_mc_1_test-model.csv", "w", newline="",
                      encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=legal_arm_a.FINAL_COLS)
                w.writeheader()
                w.writerow({"id": "LG-0001", "question": "q", "prompt": "p",
                            "raw_response": "A", "answer": "A", "gold_answer": "A",
                            "correct": 1})
            items = [{"item_id": f"LG-{i:04d}", "question": "q", "prompt": "p", "gold": "A"}
                     for i in range(1, 6)]
            writes: list[tuple[Path, list[dict]]] = []

            def capture(path, rows, cols):
                writes.append((Path(path), [dict(r) for r in rows]))

            with unittest.mock.patch.object(legal_arm_a, "RESULTS_DIR", res), \
                    unittest.mock.patch.object(legal_arm_a, "LOGS_DIR", root / "logs"), \
                    unittest.mock.patch.object(legal_arm_a, "resolve_endpoint",
                                               lambda a: ("http://x/v1", "k", "test-model")), \
                    unittest.mock.patch.object(legal_arm_a, "build_client", lambda *a: object()), \
                    unittest.mock.patch.object(legal_arm_a, "verify_credentials", lambda *a: None), \
                    unittest.mock.patch.object(legal_arm_a, "load", lambda d: items), \
                    unittest.mock.patch.object(legal_arm_a, "assert_prompt_parity", lambda *a: None), \
                    unittest.mock.patch.object(legal_arm_a, "setup_logging", lambda p: None), \
                    unittest.mock.patch.object(legal_arm_a, "call_model_with_retry",
                                               lambda **kw: "A"), \
                    unittest.mock.patch.object(legal_arm_a, "write_csv_atomic", capture), \
                    unittest.mock.patch("sys.argv", ["run_legal_arm_a", "--dataset", "legal_mc",
                                                     "--limit", "5", "--resume"]):
                legal_arm_a.main()

            checkpoints = [(p, r) for p, r in writes if "raw_result_legal_mc" in p.name]
            self.assertTrue(checkpoints, "không có checkpoint nào được ghi")
            name, rows = checkpoints[-1]
            self.assertEqual(name.name, "raw_result_legal_mc_5_test-model.csv")
            self.assertEqual(len(rows), 5)      # 1 resumed + 4 new — the union
            self.assertIn("LG-0001", {r["id"] for r in rows})
            # and the resumed row's `correct` is an int again, or the final
            # accuracy sum raises str+int after the file has been written
            self.assertTrue(all(isinstance(r["correct"], int) for r in rows))


class TestShuffledMcInput(unittest.TestCase):
    """Position-bias shuffle adapter (`make_shuffled_mc_input.py`, group 2.1).

    The shuffle is the pre-registered condition: per-item deterministic,
    order-independent, gold following its text. Anything weaker (global
    shuffle, letter-following remap) silently measures a different condition.
    """

    def _rows(self, n_items=6, n_choices=4):
        rows = []
        for i in range(n_items):
            texts = [f"choice-{i}-{j}" for j in range(n_choices)]
            gold_idx = (i * 2 + 1) % n_choices
            rows.append({"question": f"q{i}",
                         "choices": texts,
                         "answer": gold_idx,
                         "answer_choice_letter": "ABCDE"[gold_idx]})
        return rows

    def _golds(self, rows):
        return {f"LG-{i + 1:04d}": "ABCDE"[r["answer"]] for i, r in enumerate(rows)}

    def test_deterministic_same_seed_same_output(self):
        rows = self._rows()
        out1 = shuffled_mc.build(rows, self._golds(rows), 1234)
        out2 = shuffled_mc.build(rows, self._golds(rows), 1234)
        self.assertEqual(out1, out2)

    def test_subset_stable_per_item(self):
        # limit/prefix runs must reproduce the same per-item output: the RNG
        # is keyed by positional id, never by a sequential stream. (Full
        # reordering would reassign positional ids, so it is NOT stable — and
        # the source sha pin is what forbids silent reordering.)
        rows = self._rows()
        golds = self._golds(rows)
        inp_full, items_full = shuffled_mc.build(rows, golds, 1234)
        sub = rows[:3]
        sub_golds = {f"LG-{i + 1:04d}": "ABCDE"[r["answer"]] for i, r in enumerate(sub)}
        inp_sub, items_sub = shuffled_mc.build(sub, sub_golds, 1234)
        self.assertEqual(inp_sub, inp_full[:3])
        self.assertEqual(items_sub, items_full[:3])

    def test_gold_follows_its_text(self):
        rows = self._rows()
        inp, items = shuffled_mc.build(rows, self._golds(rows), 1234)
        for in_row, item, src in zip(inp, items, rows, strict=True):
            gold_text = src["choices"][src["answer"]]
            new_idx = "ABCDE".index(item["gold_new"])
            # the lettered choice at the new gold position ends with the gold text
            self.assertTrue(in_row["choices"][new_idx].endswith(gold_text),
                            f"{item['id']}: gold text lost in shuffle")
            self.assertEqual(item["perm"][new_idx], src["answer"])
            self.assertEqual(in_row["answer"], item["gold_new"])
            # choice-text set preserved (integrity check the compare relies on)
            got = [c.split(". ", 1)[1] for c in in_row["choices"]]
            self.assertEqual(sorted(got), sorted(src["choices"]))

    def test_lettering_format_and_verbatim_question(self):
        rows = self._rows(n_items=2, n_choices=3)
        inp, _ = shuffled_mc.build(rows, self._golds(rows), 1234)
        for in_row, src in zip(inp, rows, strict=True):
            self.assertEqual(in_row["question"], src["question"])
            for j, c in enumerate(in_row["choices"]):
                self.assertTrue(c.startswith(f"{'ABCDE'[j]}. "))

    def test_supports_two_and_three_choice_items(self):
        rows = self._rows(n_items=2, n_choices=2) + self._rows(n_items=2, n_choices=3)
        golds = {f"LG-{i + 1:04d}": "ABCDE"[r["answer"]] for i, r in enumerate(rows)}
        inp, items = shuffled_mc.build(rows, golds, 1234)
        self.assertEqual(len(inp), 4)
        self.assertTrue(all(len(r["choices"]) in (2, 3) for r in inp))

    def test_duplicate_choice_texts_abort(self):
        rows = [{"question": "q", "choices": ["same", "same", "other", "x"],
                 "answer": 2, "answer_choice_letter": "C"}]
        with self.assertRaises(SystemExit) as ctx:
            shuffled_mc.build(rows, {"LG-0001": "C"}, 1234)
        self.assertIn("duplicate", str(ctx.exception))

    def test_source_answer_fields_must_agree(self):
        base = {"question": "q", "choices": ["a", "b", "c"], "answer": 1,
                "answer_choice_letter": "B"}
        # index vs letter disagree
        bad = dict(base, answer_choice_letter="C")
        with self.assertRaises(SystemExit):
            shuffled_mc.build([bad], {"LG-0001": "B"}, 1234)
        # source vs orig-manifest gold disagree
        with self.assertRaises(SystemExit):
            shuffled_mc.build([dict(base)], {"LG-0001": "A"}, 1234)
        # missing manifest gold
        with self.assertRaises(SystemExit):
            shuffled_mc.build([dict(base)], {}, 1234)

    def test_exceeds_letter_contract_aborts(self):
        rows = [{"question": "q", "choices": [f"c{j}" for j in range(6)],
                 "answer": 0, "answer_choice_letter": "A"}]
        with self.assertRaises(SystemExit):
            shuffled_mc.build(rows, {"LG-0001": "A"}, 1234)

    def test_different_seeds_differ_somewhere(self):
        rows = self._rows(n_items=8)
        golds = self._golds(rows)
        _, items_a = shuffled_mc.build(rows, golds, 1234)
        _, items_b = shuffled_mc.build(rows, golds, 9999)
        perms_a = [tuple(i["perm"]) for i in items_a]
        perms_b = [tuple(i["perm"]) for i in items_b]
        self.assertNotEqual(perms_a, perms_b)


class TestRunShuffledMcWrapper(unittest.TestCase):
    """`run_shuffled_mc.py` — the condition-collision guards and the
    rename/park dance. Offline: no subprocess ever runs here."""

    SLUG = "M"

    def _fake_outputs(self, folder: Path):
        for name in (f"full_evaluation_{self.SLUG}.csv", f"accuracy_{self.SLUG}.csv"):
            (folder / name).write_text("col\n1\n", encoding="utf-8")
        for n in (100, 146):
            (folder / f"raw_result_{n}_{self.SLUG}.csv").write_text("col\n1\n", encoding="utf-8")

    def test_conflicts_catch_leftovers_and_existing_shuffled_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            self._fake_outputs(folder)
            got = "\n".join(shuffled_run.conflicts(folder, self.SLUG, "s1234"))
            self.assertIn(f"raw_result_146_{self.SLUG}.csv", got)
            self.assertIn(f"full_evaluation_{self.SLUG}.csv", got)
            # and with a clean folder plus existing shuffled outputs:
            folder2 = Path(td) / "b"
            folder2.mkdir()
            (folder2 / f"full_evaluation_shuffled_s1234_{self.SLUG}.csv").write_text("x", encoding="utf-8")
            got2 = "\n".join(shuffled_run.conflicts(folder2, self.SLUG, "s1234"))
            self.assertIn("shuffled output already exists", got2)

    def test_conflicts_ignore_the_dataset_scoped_namespace(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            # legal arm-A / harness files share the folder but NOT the resume namespace
            for name in (f"raw_result_legal_mc_146_{self.SLUG}.csv",
                         f"raw_result_legal_nli_150_{self.SLUG}.csv",
                         f"full_evaluation_legal_{self.SLUG}.csv"):
                (folder / name).write_text("col\n1\n", encoding="utf-8")
            self.assertEqual(shuffled_run.conflicts(folder, self.SLUG, "s1234"), [])

    def test_argv_is_frozen_and_never_resumes(self):
        argv = shuffled_run.build_runner_argv(
            python="/py", folder="data", file="shuffled.jsonl", model="M",
            submission_out=Path("subs/submission_shuffled_s1234.csv"))
        self.assertNotIn("--resume", argv)
        for flag, val in (("--temperature", "0.0"), ("--seed", "42"),
                          ("--max-tokens", "4"), ("--workers", "4")):
            self.assertEqual(argv[argv.index(flag) + 1], val)
        self.assertTrue(any(a.endswith("submission_shuffled_s1234.csv") for a in argv))

    def test_rename_and_park_happy_path(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            self._fake_outputs(folder)
            shuffled_run.execute_renames(shuffled_run.plan_renames(folder, self.SLUG, "s1234"))
            moved = shuffled_run.park_checkpoints(folder, self.SLUG, "s1234")
            self.assertEqual(len(moved), 2)
            self.assertTrue((folder / f"full_evaluation_shuffled_s1234_{self.SLUG}.csv").exists())
            self.assertTrue((folder / f"accuracy_shuffled_s1234_{self.SLUG}.csv").exists())
            self.assertFalse((folder / f"full_evaluation_{self.SLUG}.csv").exists())
            parked = sorted(p.name for p in (folder / "shuffled_checkpoints").iterdir())
            self.assertEqual(parked, [f"raw_result_100_{self.SLUG}.csv",
                                      f"raw_result_146_{self.SLUG}.csv"])
            # the leftovers are gone, but a re-run is still refused — the
            # shuffled measurement itself now exists (never overwritten silently)
            got = shuffled_run.conflicts(folder, self.SLUG, "s1234")
            self.assertEqual(len(got), 1)
            self.assertIn("already exists", got[0])

    def test_missing_fresh_output_fails_without_renaming(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / f"accuracy_{self.SLUG}.csv").write_text("col\n1\n", encoding="utf-8")
            pairs = shuffled_run.plan_renames(folder, self.SLUG, "s1234")
            with self.assertRaises(SystemExit) as ctx:
                shuffled_run.execute_renames(pairs)
            self.assertIn("missing after the run", str(ctx.exception))
            # nothing was renamed (the accuracy file is still at its original name)
            self.assertTrue((folder / f"accuracy_{self.SLUG}.csv").exists())
            self.assertFalse((folder / f"accuracy_shuffled_s1234_{self.SLUG}.csv").exists())

    def test_park_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / f"raw_result_146_{self.SLUG}.csv").write_text("new", encoding="utf-8")
            park = folder / "shuffled_checkpoints"
            park.mkdir()
            (park / f"raw_result_146_{self.SLUG}.csv").write_text("old", encoding="utf-8")
            with self.assertRaises(SystemExit):
                shuffled_run.park_checkpoints(folder, self.SLUG, "s1234")
            self.assertEqual((park / f"raw_result_146_{self.SLUG}.csv").read_text(encoding="utf-8"),
                             "old")  # the parked measurement is untouched


class TestPositionBiasCompare(unittest.TestCase):
    """`compare_position_bias.py` — integrity gates + paired stats, offline.

    Every fixture goes through the real frozen `build_prompt`, so the tests
    fail if the prompt contract and the compare parser ever drift apart.
    """

    def _pair(self, item_id: str, texts: list[str], gold_idx: int, perm: list[int],
              answer_orig: str, answer_shuffled: str,
              correct_orig: int, correct_shuffled: int) -> tuple[dict, dict, dict]:
        question = f"Question {item_id}?"
        gold_old = "ABCDE"[gold_idx]
        gold_new = "ABCDE"[perm.index(gold_idx)]
        oc = [f"{'ABCDE'[j]}. {t}" for j, t in enumerate(texts)]
        sc = [f"{'ABCDE'[j]}. {texts[p]}" for j, p in enumerate(perm)]
        o = {"id": item_id, "question": question,
             "prompt": build_prompt(question, oc), "answer": answer_orig,
             "gold_answer": gold_old, "correct": str(correct_orig)}
        s = {"id": item_id, "question": question,
             "prompt": build_prompt(question, sc), "answer": answer_shuffled,
             "gold_answer": gold_new, "correct": str(correct_shuffled)}
        m = {"id": item_id, "gold_old": gold_old, "gold_new": gold_new,
             "perm": perm}
        return o, s, m

    def _build(self, n=20, a_only=2, b_only=5, both=8, neither=5, flips=4):
        """n items with planted 2x2 and flip counts (a=orig, b=shuffled)."""
        assert a_only + b_only + both + neither == n
        orig, shuff, items = {}, {}, []
        groups = (["a_only"] * a_only + ["b_only"] * b_only
                  + ["both"] * both + ["neither"] * neither)
        perm = [2, 0, 3, 1]  # 4-choice derangement-ish fixed permutation
        for i, grp in enumerate(groups, 1):
            item_id = f"LG-{i:04d}"
            co = 1 if grp in ("a_only", "both") else 0
            cs = 1 if grp in ("b_only", "both") else 0
            flip = i <= flips
            o, s, m = self._pair(item_id, [f"t{i}-0", f"t{i}-1", f"t{i}-2", f"t{i}-3"],
                                 gold_idx=1, perm=perm,
                                 answer_orig="A", answer_shuffled="B" if flip else "A",
                                 correct_orig=co, correct_shuffled=cs)
            orig[item_id], shuff[item_id] = o, s
            items.append(m)
        return orig, shuff, {"items": items}

    def test_paired_stats_and_counts(self):
        orig, shuff, man = self._build()
        res = posbias.compare(orig, shuff, man, expected_orig=(10, 20))
        s = res["summary"]
        self.assertEqual((s["both"], s["a_only"], s["b_only"], s["neither"]),
                         (8, 2, 5, 5))
        self.assertEqual(s["delta"], "+15.00")   # 13/20 vs 10/20
        self.assertEqual(s["mcnemar_p"], f"{harness._mcnemar_p(2, 5):.4g}")
        lo, hi = float(s["ci95_low"]), float(s["ci95_high"])
        self.assertLess(lo, 15.0)
        self.assertGreater(hi, 15.0)
        self.assertEqual(s["flipped"], 4)
        self.assertEqual(s["blanks_orig"], 0)

    def test_choice_text_stability_decomposition(self):
        """Planted fixture: flipped items answer 'B' on the shuffled side, and
        with perm=[2,0,3,1] shuffled-B == texts[0] == orig-A's text — so all 4
        flips are content-stable; the 16 same-letter items now point at a
        different text, i.e. letter-anchored."""
        orig, shuff, man = self._build(flips=4)
        s = posbias.compare(orig, shuff, man, expected_orig=(10, 20))["summary"]
        self.assertEqual(s["same_text"], 4)
        self.assertEqual(s["letter_anchored"], 16)
        self.assertEqual(s["neither_choice"], 0)

    def test_refuses_baseline_drift(self):
        orig, shuff, man = self._build()
        with self.assertRaises(SystemExit) as ctx:
            posbias.compare(orig, shuff, man, expected_orig=(120, 146))
        self.assertIn("pre-registered", str(ctx.exception))

    def test_refuses_id_mismatch(self):
        orig, shuff, man = self._build()
        del shuff["LG-0001"]
        with self.assertRaises(SystemExit) as ctx:
            posbias.compare(orig, shuff, man, expected_orig=(10, 20))
        self.assertIn("id set", str(ctx.exception))

    def test_refuses_choice_multiset_mismatch(self):
        orig, shuff, man = self._build()
        k = "LG-0001"
        q = shuff[k]["question"]
        shuffled_choices = [f"{'ABCDE'[j]}. {t}" for j, t in
                            enumerate(["t1-0", "t1-1", "t1-2", "CHANGED"])]
        shuff[k]["prompt"] = build_prompt(q, shuffled_choices)
        with self.assertRaises(SystemExit) as ctx:
            posbias.compare(orig, shuff, man, expected_orig=(10, 20))
        self.assertIn("multiset", str(ctx.exception))

    def test_refuses_gold_text_move(self):
        orig, shuff, man = self._build()
        k = "LG-0001"
        # same choice texts, but the shuffled gold letter now points elsewhere
        o, s, m = self._pair(k, ["t1-0", "t1-1", "t1-2", "t1-3"], gold_idx=1,
                             perm=[2, 0, 3, 1], answer_orig="A", answer_shuffled="A",
                             correct_orig=1, correct_shuffled=1)
        s["gold_answer"] = "A" if m["gold_new"] != "A" else "B"
        m["gold_new"] = s["gold_answer"]
        shuff[k], man_items = s, man["items"]
        man_items[0] = m
        with self.assertRaises(SystemExit) as ctx:
            posbias.compare(orig, shuff, man, expected_orig=(10, 20))
        self.assertIn("gold text moved", str(ctx.exception))

    def test_breakdown_partitions_each_side(self):
        orig, shuff, man = self._build()
        res = posbias.compare(orig, shuff, man, expected_orig=(10, 20))
        for side in ("orig", "shuffled"):
            rows = [r for r in res["breakdown"]
                    if r["section"] == "by_gold_letter" and r["side"] == side]
            self.assertEqual(sum(r["n"] for r in rows), 20)
        hist = [r for r in res["breakdown"] if r["section"] == "answer_letter"]
        self.assertEqual(len(hist), 2 * 6)   # orig+shuffled x A-E+blank


class TestReadingCiteRunner(unittest.TestCase):
    """Citation-condition runner (`run_reading_cite_eval.py`, group 2.2).

    The prompt bytes are the pre-registered condition (MC-37) and the extraction
    is fail-soft — both are contracts, so both get pinned tests.
    """

    def test_prompt_bytes_are_pinned(self):
        expected = (
            "Đọc đoạn văn dưới đây và trả lời câu hỏi bằng một cụm từ hoặc số ngắn gọn, "
            "lấy nguyên văn trong đoạn văn khi có thể.\n"
            "Sau đó trích dẫn nguyên văn một đoạn ngắn trong bài chứa câu trả lời.\n"
            "Trả lời theo đúng hai dòng:\n"
            "Trả lời: <câu trả lời>\n"
            "Trích dẫn: <đoạn trích>\n\n"
            "CTX\n\nCâu hỏi: Q?\nTrả lời: "
        )
        self.assertEqual(cite.build_citation_prompt("  CTX  ", "Q?"), expected)

    def test_extraction_repeated_labels(self):
        raw = "Trả lời: 1999\nTrích dẫn: Năm 1999, sự kiện diễn ra."
        self.assertEqual(cite.extract_citation_answer(raw),
                         ("1999", "Năm 1999, sự kiện diễn ra."))

    def test_extraction_continuation_style(self):
        # the prompt ends with "Trả lời: " — the model may just continue
        raw = "1999\nTrích dẫn: Năm 1999, sự kiện diễn ra."
        self.assertEqual(cite.extract_citation_answer(raw),
                         ("1999", "Năm 1999, sự kiện diễn ra."))

    def test_extraction_first_nonempty_answer_line(self):
        raw = "Trả lời: \n  24,10%\nTrích dẫn: tỉ lệ 24,10%"
        self.assertEqual(cite.extract_citation_answer(raw), ("24,10%", "tỉ lệ 24,10%"))

    def test_extraction_missing_citation_is_unparsed(self):
        self.assertEqual(cite.extract_citation_answer("Trả lời: 1999"), ("", ""))
        self.assertEqual(cite.extract_citation_answer(""), ("", ""))
        self.assertEqual(cite.extract_citation_answer("Trích dẫn: chỉ có trích dẫn"),
                         ("", "chỉ có trích dẫn"))

    def test_extraction_never_repairs(self):
        # citation label present but no answer text -> empty answer, not a guess
        self.assertEqual(cite.extract_citation_answer("Trích dẫn: đoạn trích"),
                         ("", "đoạn trích"))

    def test_checkpoint_namespace_is_separate(self):
        name = cite.checkpoint_name("M-cite", 5, prefix=cite.READING_CITE_PREFIX)
        self.assertEqual(name, "reading_cite_result_5_M-cite.csv")
        self.assertNotIn("reading_result_", name.replace("reading_cite_result_", ""))
        # and the resume lookup for the frozen prefix never picks it up
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / name).write_text("x", encoding="utf-8")
            self.assertIsNone(find_latest_checkpoint(folder, "M-cite",
                                                     prefix="reading_result_"))

    def test_scoring_reuses_the_frozen_scorer(self):
        from code_benchmark.score_reading_eval import score_pair
        self.assertIs(cite.score_pair, score_pair)


class TestFaithfulnessJudge(unittest.TestCase):
    """The judge instrument (`judge_faithfulness.py`, group 2.2). The gate math
    and the strict verdict parser are the parts that must never guess."""

    def test_judge_prompt_is_pinned(self):
        p = judge.build_judge_prompt("CTX", "Q?", "A.", "C.")
        self.assertIn("Chỉ trả về JSON đúng định dạng:", p)
        self.assertIn('{"verdict": "supported" hoặc "unsupported", "reason": "<một câu ngắn>"}', p)
        self.assertTrue(p.endswith("Trích dẫn: C."))
        # v2 rules the human validation forced in (MC-38)
        self.assertIn("đúng loại thông tin", p)     # answer-type must fit the question
        self.assertIn("khớp chính xác", p)           # arithmetic checked, "gần đúng" rejected
        self.assertIn("nhất quán với kết luận", p)   # verdict must follow its own reason
        # empty fields render as an explicit marker, not as blanks the judge
        # could read as "no instruction"
        self.assertIn("Câu trả lời: (trống)", judge.build_judge_prompt("CTX", "Q?", "", "C."))

    def test_parse_bare_json(self):
        v, r, err = judge.parse_judge_verdict('{"verdict": "supported", "reason": "ok"}')
        self.assertEqual((v, err), ("supported", False))
        self.assertEqual(r, "ok")

    def test_parse_chatty_json(self):
        v, _r, err = judge.parse_judge_verdict(
            'Kết quả:\n{"verdict": "Unsupported", "reason": "lệch"}\nHết.')
        self.assertEqual((v, err), ("unsupported", False))

    def test_parse_fenced_json(self):
        v, _r, err = judge.parse_judge_verdict(
            '```json\n{"verdict": "supported", "reason": "ok"}\n```')
        self.assertEqual((v, err), ("supported", False))

    def test_parse_never_guesses(self):
        for raw in ("", "supported", '{"verdict": "maybe"}', '{"reason": "x"}',
                    '{"verdict": 3}', "not json at all"):
            v, _r, err = judge.parse_judge_verdict(raw)
            self.assertTrue(err, raw)
            self.assertEqual(v, "")

    def test_parse_falls_back_to_last_verdict_in_reasoning(self):
        # a reasoning judge mentions the field while thinking; the LAST one is
        # the answer, and it must win over any earlier mention.
        raw = ('Suy nghĩ: ban đầu tôi nghĩ "verdict": "supported" nhưng sai.\n'
               'Kết luận:\n{"verdict": "unsupported", "reason": "trích dẫn lệch"}')
        v, _r, err = judge.parse_judge_verdict(raw)
        self.assertEqual((v, err), ("unsupported", False))

    def test_judge_once_reasks_only_on_parse_failure(self):
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            return "không phải JSON" if len(calls) == 1 else '{"verdict": "supported", "reason": "ok"}'

        v, _r, err, raw = judge.judge_once(flaky, "p", retries=2)
        self.assertEqual((v, err), ("supported", False))
        self.assertEqual(len(calls), 2)          # one re-ask

        calls2 = []

        def always_bad(prompt):
            calls2.append(prompt)
            return "vẫn không parse"

        v, _r, err, _raw = judge.judge_once(always_bad, "p", retries=2)
        self.assertTrue(err)
        self.assertEqual(len(calls2), 3)         # original + 2 retries, then give up

    def test_excluding_the_dev_sample_keeps_the_test_disjoint(self):
        rows = [{"dataset": "squad", "item_id": f"s{i}", "em": i % 2} for i in range(30)]
        excluded = {f"squad:s{i}" for i in range(15)}
        pool = [r for r in rows if f"{r['dataset']}:{r['item_id']}" not in excluded]
        picked = judge.sample_sheet(pool, per_cell=5)
        self.assertFalse({f"{r['dataset']}:{r['item_id']}" for r in picked} & excluded)

    def test_validation_pairs_skip_unlabeled_is_explicit(self):
        labels = [{"dataset": "squad", "item_id": "1", "human_supports": "yes"},
                  {"dataset": "squad", "item_id": "2", "human_supports": ""},
                  {"dataset": "drop", "item_id": "3", "human_supports": "no"}]
        jr = {"squad:1": {"judge_model": "J", "verdict": "supported", "judge_error": "0"},
              "drop:3": {"judge_model": "J", "verdict": "unsupported", "judge_error": "0"}}
        with self.assertRaises(SystemExit):
            judge.build_validation_pairs(labels, jr, skip_unlabeled=False)
        pairs, unlabeled, model = judge.build_validation_pairs(labels, jr, skip_unlabeled=True)
        self.assertEqual((pairs, unlabeled, model), ([(True, True), (False, False)], 1, "J"))

    def test_validation_pairs_abort_on_judge_error(self):
        labels = [{"dataset": "squad", "item_id": "1", "human_supports": "yes"}]
        jr = {"squad:1": {"judge_model": "J", "verdict": "", "judge_error": "1"}}
        with self.assertRaises(SystemExit):
            judge.build_validation_pairs(labels, jr, skip_unlabeled=False)

    def test_citation_verbatim_normalization(self):
        ctx = "Năm 1999,   sự kiện diễn ra tại Hà Nội."
        self.assertTrue(judge.citation_verbatim("năm 1999, sự kiện", ctx))
        self.assertTrue(judge.citation_verbatim("Năm 1999, sự kiện diễn ra", ctx))
        self.assertFalse(judge.citation_verbatim("Năm 2001", ctx))
        self.assertFalse(judge.citation_verbatim("", ctx))

    def test_cohen_kappa_hand_computed(self):
        # po=0.5, pe=0.5 -> kappa 0
        pairs = [(True, True), (True, False), (False, True), (False, False)]
        self.assertAlmostEqual(judge.cohen_kappa(pairs), 0.0, places=6)
        # perfect agreement with balanced marginals -> 1.0
        self.assertAlmostEqual(judge.cohen_kappa([(True, True), (False, False)]), 1.0)
        # degenerate marginals: all same on both raters
        self.assertAlmostEqual(judge.cohen_kappa([(True, True)] * 5), 1.0)

    def test_gate_boundaries(self):
        self.assertTrue(judge.gate_passes(60, 0.80, 0.60))
        self.assertFalse(judge.gate_passes(60, 0.7999, 0.60))
        self.assertFalse(judge.gate_passes(60, 0.80, 0.5999))
        self.assertFalse(judge.gate_passes(0, 1.0, 1.0))

    def test_sample_sheet_is_deterministic_and_stratified(self):
        rows = ([{"dataset": "squad", "item_id": f"s{i:03d}", "em": i % 2}
                 for i in range(40)]
                + [{"dataset": "drop", "item_id": f"d{i:03d}", "em": i % 2}
                   for i in range(40)])
        a = judge.sample_sheet(rows)
        b = judge.sample_sheet(rows)
        self.assertEqual([r["item_id"] for r in a], [r["item_id"] for r in b])
        self.assertEqual(len(a), 60)
        cells = Counter((r["dataset"], r["em"]) for r in a)
        self.assertEqual(cells, {("squad", 0): 15, ("squad", 1): 15,
                                 ("drop", 0): 15, ("drop", 1): 15})
        c = judge.sample_sheet(rows, seed=7)
        self.assertNotEqual([r["item_id"] for r in a], [r["item_id"] for r in c])

    def test_sample_sheet_tops_up_a_short_cell(self):
        rows = ([{"dataset": "squad", "item_id": f"s{i:03d}", "em": 1 if i < 5 else 0}
                 for i in range(40)]
                + [{"dataset": "drop", "item_id": f"d{i:03d}", "em": i % 2}
                   for i in range(40)])
        picked = judge.sample_sheet(rows)
        self.assertEqual(len(picked), 60)
        squad = [r for r in picked if r["dataset"] == "squad"]
        self.assertEqual(len(squad), 30)   # short em=1 cell topped up from squad em=0
        self.assertEqual(sum(r["em"] for r in squad), 5)


class TestFaithfulnessLabelTool(unittest.TestCase):
    """`label_faithfulness.py` — the autosaving labeler. The HTTP surface is
    exercised for real on an ephemeral port; the file contract is the point."""

    def _sheet(self):
        return [{"dataset": "squad", "item_id": "0", "question": "Hỏi <b>x</b>?",
                 "context": "Ngữ cảnh & <script>alert(1)</script>",
                 "answer": "a", "citation": "ci"},
                {"dataset": "drop", "item_id": "7", "question": "q2",
                 "context": "c2", "answer": "a2", "citation": "ci2"}]

    def test_missing_labels_file_loads_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(labeler.load_labels(Path(td) / "nope.csv"), {})

    def test_upsert_rejects_anything_but_yes_no(self):
        store: dict = {}
        with self.assertRaises(ValueError):
            labeler.upsert_label(store, "squad", "0", "maybe", "")
        labeler.upsert_label(store, "squad", "0", "YES", "chú thích")
        self.assertEqual(store["squad:0"], {"human_supports": "yes", "note": "chú thích"})

    def test_write_is_sheet_ordered_and_blanks_unlabeled(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "labels.csv"
            sheet = self._sheet()
            store: dict = {}
            labeler.upsert_label(store, "drop", "7", "no", "")
            labeler.write_labels(path, store, sheet)
            with open(path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["item_id"] for r in rows], ["0", "7"])  # sheet order
            self.assertEqual(rows[0]["human_supports"], "")             # unlabeled stays blank
            self.assertEqual(rows[1]["human_supports"], "no")
            # round-trip
            self.assertEqual(labeler.load_labels(path)["drop:7"]["human_supports"], "no")

    def test_render_escapes_model_output(self):
        page = labeler.render_page(self._sheet(), {})
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Hỏi &lt;b&gt;x&lt;/b&gt;?", page)

    def test_http_autosave_round_trip(self):
        import http.client
        import threading
        with tempfile.TemporaryDirectory() as td:
            sheet = self._sheet()
            labels = Path(td) / "labels.csv"
            store: dict = {}
            srv = labeler.ThreadingHTTPServer(("127.0.0.1", 0),
                                              labeler.make_handler(sheet, labels, store,
                                                                   threading.Lock()))
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                port = srv.server_address[1]
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/")
                r = conn.getresponse()
                self.assertEqual(r.status, 200)
                self.assertIn("Câu hỏi", r.read().decode("utf-8"))

                body = json.dumps({"dataset": "squad", "item_id": "0",
                                   "human_supports": "yes", "note": ""})
                conn.request("POST", "/api/label", body,
                             {"Content-Type": "application/json"})
                r = conn.getresponse()
                self.assertEqual(r.status, 200)
                self.assertEqual(json.loads(r.read())["saved"], 1)
                self.assertEqual(labeler.load_labels(labels)["squad:0"]["human_supports"], "yes")

                bad = json.dumps({"dataset": "squad", "item_id": "0", "human_supports": "x"})
                conn.request("POST", "/api/label", bad, {"Content-Type": "application/json"})
                self.assertEqual(conn.getresponse().status, 400)
            finally:
                srv.shutdown()
                srv.server_close()
                t.join(timeout=5)


class TestMcCalibration(unittest.TestCase):
    """`run_mc_calibration_eval.py` — the pure parts: letter distribution from
    logprobs, ECE/reliability, and the summary math (group 3.1)."""

    @staticmethod
    def _lp(piece: str, logprob: float) -> dict:
        """One entry of a `top_logprobs` list.

        Built through a helper instead of `{"token": "B", ...}` literals on purpose:
        bandit reads a `token=` string literal as a hardcoded password (B105/B106),
        and these are answer letters. Suppressing the gate repo-wide to accommodate
        five fixtures would be the wrong trade — the gate stays armed.
        """
        return {"token": piece, "logprob": logprob}

    def test_letter_probs_normalizes_over_the_offered_letters_only(self):
        import math
        top = [self._lp("B", math.log(0.5)),
               self._lp("A", math.log(0.2)),
               self._lp("C", math.log(0.25)),
               self._lp(" x", math.log(0.9)),   # non-letter ignored
               self._lp("D", math.log(0.05)),
               self._lp("E", math.log(0.10))]  # NOT offered by a 4-choice row
        p, off = cal.letter_probs(top, "ABCD")
        self.assertEqual(set(p), set("ABCD"))
        self.assertAlmostEqual(sum(p.values()), 1.0)
        # renormalized over the offered four, so E no longer dilutes the answer
        self.assertAlmostEqual(p["B"], 0.5, places=6)
        self.assertAlmostEqual(p["A"], 0.2, places=6)
        self.assertGreater(off, 0.0)                        # E's share is reported, not folded in

    def test_letter_probs_missing_offered_letter_is_zero_not_invented(self):
        p, _ = cal.letter_probs([self._lp("A", math.log(1.0))], "ABC")
        self.assertAlmostEqual(p["A"], 1.0, places=6)
        self.assertEqual(p["B"], 0.0)
        self.assertEqual(p["C"], 0.0)

    def test_letter_probs_empty_is_all_zero(self):
        p, off = cal.letter_probs([], "ABCD")
        self.assertEqual(set(p.values()), {0.0})
        self.assertEqual(off, 0.0)

    def test_offered_letters_reads_the_prompt_not_a_fixed_width(self):
        four = build_prompt("Câu hỏi?", ["A. x", "B. y", "C. z", "D. w"])
        self.assertEqual(cal.offered_letters(four), "ABCD")
        five = build_prompt("Câu hỏi?", ["A. x", "B. y", "C. z", "D. w", "E. v"])
        self.assertEqual(cal.offered_letters(five), "ABCDE")
        three = build_prompt("Câu hỏi?", ["A. x", "B. y", "C. z"])
        self.assertEqual(cal.offered_letters(three), "ABC")

    def test_offered_letters_fails_fast_on_a_gapped_option_block(self):
        bad = build_prompt("Câu hỏi?", ["A. x", "C. z", "B. y", "D. w"])
        with self.assertRaises(SystemExit):
            cal.offered_letters(bad)

    def test_build_report_summary_math(self):
        items = [
            {"id": "1", "gold": "A", "answer": "A", "correct": 1, "n_letters_found": 5,
             "n_choices": 5, "off_options_mass": "0",
             "p_A": "0.9", "p_B": "0.1", "p_C": "0", "p_D": "0", "p_E": "0", "confidence": "0.9"},
            {"id": "2", "gold": "A", "answer": "B", "correct": 0, "n_letters_found": 5,
             "n_choices": 5, "off_options_mass": "0",
             "p_A": "0.2", "p_B": "0.8", "p_C": "0", "p_D": "0", "p_E": "0", "confidence": "0.8"},
            {"id": "3", "gold": "C", "answer": "", "correct": 0, "n_letters_found": 0,
             "n_choices": 4, "off_options_mass": "0",
             "p_A": "0", "p_B": "0", "p_C": "0", "p_D": "0", "p_E": "0", "confidence": ""},
        ]
        summary, rows = cal.build_report(items, "legal_mc", "h", bins=10)
        self.assertEqual(summary["n"], 3)
        self.assertEqual(summary["n_usable"], 2)              # item 3 has no distribution
        self.assertEqual(summary["accuracy"], "33.33")        # 1/3, unparsed counts wrong
        self.assertEqual(summary["mean_confidence"], "85.00")
        # confidence Brier: ((0.9-1)^2 + (0.8-0)^2)/2 = (0.01+0.64)/2 = 0.325
        self.assertEqual(summary["brier_confidence"], "0.3250")
        # overconfidence = 0.85 - 0.3333 = +51.67
        self.assertEqual(summary["overconfidence"], "+51.67")
        self.assertEqual(len(rows), 10)

    def test_build_breakdown_uses_the_frozen_subject_map(self):
        items = []
        for item_id in ["01-0001", "01-0002", "37-0003"]:
            items.append({"id": item_id, "gold": "A", "answer": "A", "correct": 1,
                          "n_letters_found": 4, "n_choices": 4, "off_options_mass": "0",
                          "p_A": "1", "p_B": "0", "p_C": "0", "p_D": "0", "p_E": "0",
                          "confidence": "1.0"})
        rows = cal.build_breakdown(items, "vmlu_mqa_all_gold", bins=10)
        by = {(r["level"], r["name"]): r for r in rows}
        self.assertEqual(by[("overall", "overall")]["n"], 3)
        self.assertEqual(by[("category", "STEM")]["n"], 2)      # 01 = Elementary Mathematics
        self.assertEqual(by[("category", "Humanity")]["n"], 1)  # 37 = Administrative Law
        self.assertEqual(by[("subject", "01 Elementary Mathematics")]["n"], 2)
        for r in rows:
            if r["n"]:
                self.assertEqual(r["ece"], "0.00")              # conf == acc in every bin

    def test_load_mqa_all_gold_builds_prompts_and_gold(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "all_gold.jsonl"
            p.write_text(json.dumps({"id": "28-0007", "question": "Hỏi?",
                                     "choices": ["A. a", "B. b", "C. c", "D. d"],
                                     "answer": "c"}) + "\n", encoding="utf-8")
            items = cal.load_mqa_all_gold(p)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["gold"], "C")                 # upper-cased like the scorer
        self.assertEqual(items[0]["n_choices"], 4)
        self.assertEqual(cal.offered_letters(items[0]["prompt"]), "ABCD")

    def test_load_mqa_all_gold_rejects_partial_gold(self):
        rows = [{"id": "01-0001", "question": "q", "choices": ["A. a", "B. b"], "answer": "A"},
                {"id": "01-0002", "question": "q", "choices": ["A. a", "B. b"], "answer": ""}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "all_gold.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with self.assertRaises(SystemExit):
                cal.load_mqa_all_gold(p)          # all-or-none, the frozen gate

    def test_load_mqa_all_gold_rejects_duplicate_ids_and_wide_choice_blocks(self):
        dup = [{"id": "01-0001", "question": "q", "choices": ["A. a", "B. b"], "answer": "A"}] * 2
        wide = [{"id": "01-0001", "question": "q", "answer": "A",
                 "choices": ["A. a", "B. b", "C. c", "D. d", "E. e", "F. f"]}]
        for rows in (dup, wide):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "all_gold.jsonl"
                p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    cal.load_mqa_all_gold(p)

    def test_logprobs_retry_returns_first_token_distribution(self):
        from code_benchmark.llm import call_logprobs_with_retry
        client = MagicMock()
        # the letters go through locals: bandit reads a `token=` literal as a password
        chosen, runner_up = "B", "A"
        first = MagicMock(token=chosen, logprob=-0.25)
        first.top_logprobs = [MagicMock(token=chosen, logprob=-0.25),
                              MagicMock(token=runner_up, logprob=-2.0)]
        choice = MagicMock()
        choice.message.content = "B"
        choice.logprobs.content = [first]
        client.chat.completions.create.return_value = MagicMock(choices=[choice])
        content, tok, top = call_logprobs_with_retry(client, "m", "p", 0.0, 42, 4, 20)
        self.assertEqual((content, tok), ("B", "B"))
        self.assertEqual([t["token"] for t in top], ["B", "A"])

    def test_logprobs_retry_gives_up_and_returns_nothing_rather_than_guessing(self):
        from code_benchmark.llm import call_logprobs_with_retry
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("502 bad gateway")
        with unittest.mock.patch("code_benchmark.llm.time.sleep"):
            content, tok, top = call_logprobs_with_retry(
                client, "m", "p", 0.0, 42, 4, 20, max_retries=2, sleep_sec=0)
        self.assertEqual((content, tok, top), ("", "", []))

    def test_auth_failure_is_fatal_on_the_logprobs_path_too(self):
        from code_benchmark.llm import call_logprobs_with_retry
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("401 Unauthorized")
        # fail fast, never 30 retries on a bad key — the rule is shared with the text path
        with self.assertRaisesRegex(Exception, "401 Unauthorized"):
            call_logprobs_with_retry(client, "m", "p", 0.0, 42, 4, 20)

    def test_off_options_mass_is_reported_not_folded_into_the_distribution(self):
        # The legal MC row offers A-D; E is not a candidate, so its mass is a
        # measured diagnostic. Renormalizing over A-E (the MC-42 rule) would
        # understate confidence by exactly this share.
        top = [self._lp("A", math.log(0.5)),
               self._lp("B", math.log(0.3)),
               self._lp("C", math.log(0.1)),
               self._lp("D", math.log(0.06)),
               self._lp("E", math.log(0.04))]
        p, off = cal.letter_probs(top, "ABCD")
        self.assertAlmostEqual(off, 0.04, places=6)
        self.assertAlmostEqual(sum(p.values()), 1.0)
        self.assertAlmostEqual(p["A"], 0.5 / 0.96, places=6)   # > the raw 0.5

    def test_ece_hand_computed(self):
        ece, rows = cal.ece_and_reliability([0.9, 0.9, 0.1, 0.1], [1, 1, 0, 0], bins=10)
        self.assertAlmostEqual(ece, 0.1, places=6)
        self.assertEqual(len(rows), 10)
        self.assertEqual(sum(r["n"] for r in rows), 4)


class TestHarnessGenome(unittest.TestCase):
    """`harness_genome.py` — the P0 guard. Each test is one way an evolutionary
    loop could cheat its way to a better score; the guard must stop it at
    validation time, not in a write-up afterwards."""

    def setUp(self):
        from code_benchmark import harness_genome as hg
        self.hg = hg
        self.spec = hg.minimal_genome().to_dict()

    def test_minimal_seed_validates_and_its_id_survives_a_round_trip(self):
        from code_benchmark import harness_genome as hg
        g = hg.minimal_genome()
        self.assertEqual(hg.validate(g.to_dict()).genome_id, g.genome_id)
        self.assertEqual(g.tools, ("none",))
        self.assertEqual(g.max_tokens, 4)                 # the frozen MC letter budget
        self.assertEqual(g.required_declarations(), [])   # a plain single answer

    def test_a_different_value_anywhere_is_a_different_candidate(self):
        from code_benchmark import harness_genome as hg
        base = hg.minimal_genome()
        mutated = hg.validate({**base.to_dict(), "option_order": "seed_shuffle",
                               "shuffle_seed": 1234})
        self.assertNotEqual(mutated.genome_id, base.genome_id)
        self.assertEqual(mutated.shuffle_seed, 1234)

    def test_an_unreviewed_ninth_gene_group_is_an_escape_hatch(self):
        spec = {**self.spec, "self_reward": {"weight": 1.0}}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)

    def test_an_out_of_enum_value_is_never_coerced(self):
        spec = {**self.spec, "elicitation": "chain_of_thought_v2"}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)

    def test_fewshot_k_must_agree_with_its_elicitation(self):
        spec = {**self.spec, "fewshot": {"k": 3, "selection": "random"}}
        with self.assertRaises(SystemExit):               # minimal + k=3 is a contradiction
            self.hg.validate(spec)
        spec = {**self.spec, "elicitation": "fewshot_k",
                "fewshot": {"k": 0, "selection": "random"}}
        with self.assertRaises(SystemExit):               # few-shot with no examples
            self.hg.validate(spec)

    def test_a_token_ceiling_is_part_of_the_measurement(self):
        # The cheapest reward-hack: give an MC model room to write a rationale whose
        # last letter the byte-frozen parser then reads. Score up, capability flat.
        spec = {**self.spec, "resources": {"max_tokens": 64, "temperature": 0.0,
                                           "samples_per_item": 1}}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)
        over_cap = {**self.spec, "template_id": "vbench_agentic"}
        over_cap["answer_format"] = {"template_id": "vbench_agentic", "retries": 0,
                                     "repair_syntax_only": True}
        over_cap["resources"] = {"max_tokens": 4096, "temperature": 0.0,
                                 "samples_per_item": 1}
        with self.assertRaises(SystemExit):               # above the hard cap too
            self.hg.validate(over_cap)

    def test_a_template_outside_the_frozen_registry_is_a_scorer_change(self):
        spec = {**self.spec}
        spec["answer_format"] = {"template_id": "extract_answer_v2", "retries": 0,
                                 "repair_syntax_only": True}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)

    def test_values_cannot_smuggle_a_path_or_code(self):
        for bad in ("/etc/passwd", "code_benchmark/run_mc_eval.py", "import os",
                    "lambda: 1", "x\ny"):
            spec = {**self.spec}
            spec["answer_format"] = {"template_id": bad, "retries": 0,
                                     "repair_syntax_only": True}
            with self.assertRaises(SystemExit):
                self.hg.validate(spec)

    def test_scorer_gold_and_split_keys_are_outside_the_genome(self):
        for key in ("scorer", "gold", "dataset", "split", "extract_answer"):
            with self.assertRaises(SystemExit):
                self.hg.validate({**self.spec, key: "anything"})

    def test_answers_are_never_repaired(self):
        spec = {**self.spec}
        spec["answer_format"] = {"template_id": "mc_frozen", "retries": 0,
                                 "repair_syntax_only": False}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)

    def test_tools_are_a_reviewed_menu_and_none_stands_alone(self):
        spec = {**self.spec, "tools": ["calculator", "self_written_tool"]}
        with self.assertRaises(SystemExit):               # synthesis is P4 + sandbox
            self.hg.validate(spec)
        spec = {**self.spec, "tools": ["none", "calculator"]}
        with self.assertRaises(SystemExit):               # a contradiction, not a default
            self.hg.validate(spec)
        spec = {**self.spec, "tools": ["calculator", "calculator"]}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)

    def test_a_shuffle_without_its_seed_is_uninterpretable(self):
        spec = {**self.spec, "option_order": "seed_shuffle"}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)
        spec = {**self.spec, "shuffle_seed": 7}           # seed without a shuffle
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)

    def test_a_disabled_retrieval_group_must_be_inert(self):
        spec = {**self.spec, "rag": {"mode": "off", "corpus": "mixed", "top_k": 3,
                                     "merge": "concat"}}
        with self.assertRaises(SystemExit):
            self.hg.validate(spec)
        ok = {**self.spec, "rag": {"mode": "off", "corpus": "viwiki", "top_k": 0,
                                   "merge": "none"}}
        self.assertEqual(self.hg.validate(ok).rag_mode, "off")

    def test_conditions_that_change_what_is_measured_must_declare_it(self):
        from code_benchmark import harness_genome as hg
        guided = hg.validate({**self.spec, "agentic_extra": {"guided_fallback": True}})
        self.assertTrue(any("thứ ba" in d for d in guided.required_declarations()))
        hot = hg.validate({**self.spec, "resources": {"max_tokens": 4, "temperature": 0.7,
                                                      "samples_per_item": 1}})
        self.assertTrue(any("không tất định" in d for d in hot.required_declarations()))
        vote = hg.validate({**self.spec, "resources": {"max_tokens": 4, "temperature": 0.0,
                                                      "samples_per_item": 5}})
        self.assertTrue(any("bầu" in d for d in vote.required_declarations()))
        tools = hg.validate({**self.spec, "tools": ["calculator", "date_arith"]})
        self.assertTrue(any("tách biệt của tool" in d for d in tools.required_declarations()))

    def test_the_baseline_and_its_ablation_are_two_named_candidates(self):
        from code_benchmark import harness_genome as hg
        base = hg.baseline_genome()
        ablated = hg.baseline_genome_vs_direct(base)
        self.assertNotEqual(base.genome_id, ablated.genome_id)
        self.assertEqual(ablated.tools, ("none",))
        self.assertEqual(ablated.elicitation, "zero_shot_minimal")
        self.assertEqual(ablated.rag_mode, base.rag_mode)   # only the stated genes moved

    def test_the_frozen_surface_is_fingerprinted_and_covers_the_three_contracts(self):
        from code_benchmark import harness_genome as hg
        prints = hg.frozen_fingerprints()
        self.assertEqual(set(prints), {"code_benchmark.run_mc_eval:build_prompt",
                                       "code_benchmark.run_mc_eval:extract_answer",
                                       "code_benchmark.run_vbench_eval:_validate_call"})
        self.assertEqual(prints, hg.frozen_fingerprints())   # stable across calls
        self.assertTrue(all(len(v) == 16 for v in prints.values()))

    def test_an_evidence_bundle_references_results_and_fails_fast_when_absent(self):
        from code_benchmark import harness_genome as hg
        g = hg.minimal_genome()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "evidence"
            with self.assertRaises(SystemExit):             # no bundle pointing at nothing
                hg.collect_evidence(g, slug="probe", dataset="legal_mc",
                                    results=Path(d) / "nope.csv",
                                    ledger=Path(d) / "nope2.csv", budget={},
                                    root=root)
            (Path(d) / "res.csv").write_text("id\n1\n", encoding="utf-8")
            (Path(d) / "led.csv").write_text("id\n1\n", encoding="utf-8")
            out = hg.collect_evidence(g, slug="probe", dataset="legal_mc",
                                      results=Path(d) / "res.csv",
                                      ledger=Path(d) / "led.csv",
                                      budget={"wall_sec": 12}, root=root,
                                      container="omp")
            # the container is part of the identity: MC-47 measured the scaffold
            # itself as the largest variance source, and the §4 gene groups cannot
            # express it, so a direct call and a scaffolded run must not collide.
            self.assertEqual(out.name, f"omp__{g.genome_id}")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["container"], "omp")
            self.assertFalse(manifest["code_changed"])       # honest empty for config-only
            self.assertEqual(manifest["frozen_fingerprints"], hg.frozen_fingerprints())
            self.assertIn("legal_mc", manifest["reproduce"])
            self.assertEqual(json.loads((out / "genome.json").read_text(encoding="utf-8")),
                             g.to_dict())
            self.assertTrue((out / "harness.diff").exists())
            direct = hg.collect_evidence(g, slug="probe_direct", dataset="legal_mc",
                                         results=Path(d) / "res.csv",
                                         ledger=Path(d) / "led.csv", budget={}, root=root)
            self.assertNotEqual(direct.name, out.name)
            self.assertNotEqual(direct.name, g.genome_id)
            removed = hg.prune_evidence(keep=0, root=root)
            self.assertEqual(sorted(removed), sorted([f"omp__{g.genome_id}",
                                                      f"direct__{g.genome_id}"]))

    def test_the_gene_groups_are_exactly_the_plans_eight(self):
        # §4's list, in order. If the plan changes, this is the test that must change
        # with it — silently widening the grammar is how a guard stops guarding.
        self.assertEqual(self.hg.GENE_GROUPS,
                         ("elicitation", "fewshot", "option_order", "answer_format",
                          "rag", "tools", "resources", "agentic_extra"))


class TestRq1Decomposition(unittest.TestCase):
    """`build_rq1_decomposition.py` — the thesis RQ1 table. Its whole value is that
    no number is typed by hand, so the tests are about what it refuses to do."""

    def setUp(self):
        from code_benchmark import build_rq1_decomposition as rq1
        self.rq1 = rq1

    def test_a_missing_artifact_is_an_error_not_a_dropped_row(self):
        reg = self.rq1.registry()
        reg.sources[0].path = "does-not-exist/nope.csv"
        with self.assertRaises(SystemExit) as ctx:
            self.rq1.read_source(reg.sources[0])
        self.assertIn("cannot be invented", str(ctx.exception))

    def test_every_declared_source_exists_in_this_repo(self):
        # The declaration IS the contract: if an arm was deleted, the table must stop
        # rather than quietly shrink to the arms that still exist. Paired and
        # interaction sources name their arms inside the path, so resolve both kinds.
        for src in self.rq1.registry().sources:
            parts = src.path.split("|")
            slugs = parts[1:] if parts[0] in ("interaction",) else parts[:1]
            for slug in slugs:
                path = self.rq1.RESULTS / slug
                self.assertTrue(path.exists(), f"declared RQ1 source missing: {path}")

    def test_a_paired_contrast_needs_two_arms_that_actually_share_items(self):
        stats = self.rq1._paired_contrast("ompF5clean_Qwen3_5-9B-65K",
                                          "ompF7clean_Qwen3_5-9B-65K", "legal_mc")
        self.assertEqual(stats["n"], 146)
        self.assertTrue(stats["delta"])            # a signed string, e.g. "-8.22"
        with self.assertRaises(SystemExit):
            self.rq1._paired_contrast("ompF5clean_Qwen3_5-9B-65K",
                                      "ompH5clean_Qwen3_5-9B-28K", "legal_nli")

    def test_the_scaffold_table_keeps_one_model_per_row_pair(self):
        rows = [self.rq1.read_source(s) for s in self.rq1.registry().sources]
        scaffolds = [r for r in rows if r["source"] == "scaffold"]
        models = {r["model"] for r in scaffolds}
        self.assertEqual(models, {"Qwen3.5-9B-65K", "Qwen3.5-9B-28K", "MiMo V2.5"})
        for r in scaffolds:            # each row names its own model: no cross-model delta
            self.assertTrue(r["model"])
            self.assertTrue(r["card"])

    def test_metrics_are_named_per_row_and_never_merged(self):
        rows = [self.rq1.read_source(s) for s in self.rq1.registry().sources]
        metrics = {r["metric"] for r in rows if r["source"] == "scaffold"}
        # accuracy, EM and the two V-Bench metrics are four different quantities
        self.assertGreaterEqual(len(metrics), 3)
        for r in rows:
            self.assertTrue(r["metric"], f"row without a metric name: {r['artifact']}")

    def test_a_tiny_p_is_never_printed_as_zero(self):
        # p = 0.000 reads as "no effect", which is the opposite of what it means
        self.assertNotEqual(self.rq1.p_fmt("1.049e-05"), "0.000")
        self.assertEqual(self.rq1.p_fmt("1.049e-05"), "1.0e-05")
        self.assertEqual(self.rq1.p_fmt("0.1094"), "0.109")
        self.assertEqual(self.rq1.p_fmt(""), "—")
        self.assertEqual(self.rq1.p_fmt("n/a"), "—")

    def test_the_table_renders_from_real_artifacts(self):
        rows = [self.rq1.read_source(s) for s in self.rq1.registry().sources]
        md = self.rq1.render(rows, self.rq1.noise_floor(), self.rq1.calibration_rows())
        self.assertIn("Scaffold gene", md)
        self.assertIn("## Không được quy", md)             # caveats are part of the output
        self.assertNotIn("| — | — |", md)                  # no unrendered placeholders
        self.assertNotIn("None", md)

    def test_noise_floor_keeps_each_cell_separate_at_a_fixed_n(self):
        rows = self.rq1.noise_floor()
        self.assertGreaterEqual(len(rows), 4)
        cells = [r["cell"] for r in rows]
        self.assertEqual(len(cells), len(set(cells)))     # not collapsed into one cell
        for r in rows:
            self.assertGreaterEqual(int(r["runs"]), 2)     # a single run has no spread
            self.assertEqual(int(r["n"]), 146)             # never pooled across n
            self.assertAlmostEqual(float(r["spread"]),
                                   float(r["max"]) - float(r["min"]), places=2)


class TestAgreementCI(unittest.TestCase):
    """The V-Bench MC agreement CI — a scale bug that shipped because no arm had
    ever run that branch (found 2026-09-29, the first MiMo run to reach it)."""

    def test_bootstrap_returns_percentages_not_fractions(self):
        self.assertEqual(harness._paired_bootstrap([0, 0, 0, 0]), (0.0, 0.0))
        self.assertEqual(harness._paired_bootstrap([1, 1, 1, 1]), (100.0, 100.0))

    def test_agreement_ci_is_in_percentage_points_and_brackets_its_delta(self):
        agree = [1] * 3214 + [0] * 927          # 77.61% agreement
        lo, hi = harness._agreement_ci(agree)
        delta = 100.0 * sum(agree) / len(agree) - 100.0
        self.assertLessEqual(lo, delta)
        self.assertLessEqual(delta, hi)
        # and it is a plausible band around -22, not four orders of magnitude off
        self.assertGreater(lo, -30.0)
        self.assertLess(hi, -10.0)

    def test_perfect_agreement_has_an_empty_interval_at_zero(self):
        lo, hi = harness._agreement_ci([1] * 50)
        self.assertEqual((lo, hi), (0.0, 0.0))

    def test_blank_vs_blank_is_not_agreement_in_the_ci(self):
        # The CI must be built from the SAME predicate as the printed rate: an
        # empty answer is not an answer, so a blank-both row is a disagreement.
        a = {"1": "A", "2": "", "3": "B", "4": ""}
        b = {"1": "A", "2": "", "3": "C", "4": "B"}
        shared = list(a)
        self.assertEqual(harness._agreement_flags(a, b, shared), [1, 0, 0, 0])
        lo, hi = harness._agreement_ci(harness._agreement_flags(a, b, shared))
        self.assertLessEqual(lo, -75.0)     # the point delta: 1/4 agreed
        self.assertLessEqual(-75.0, hi)


class TestHarnessRegistry(unittest.TestCase):
    """The arm registry (build_dashboard_harness.py) — invariants CI cannot see.

    A ladder row is a comparison INSIDE one model, so the registry has to say
    which model each arm measures; and a min…max range that silently spans two
    models is exactly the failure this table exists to prevent.
    """

    def test_every_arm_declares_its_model(self):
        shorts = {short for _k, _s, short, _l, _c in dash.ARMS}
        self.assertEqual(shorts - set(dash.ARM_MODEL), set())

    def test_two_models_are_actually_present(self):
        """The point of the second model: a single-model block proves nothing."""
        self.assertGreaterEqual(len(set(dash.ARM_MODEL.values())), 2)

    def test_clean_and_representative_arms_exist(self):
        shorts = {short for _k, _s, short, _l, _c in dash.ARMS}
        self.assertTrue(set(dash.CLEAN_ARMS) <= shorts, set(dash.CLEAN_ARMS) - shorts)
        self.assertTrue(set(dash.REPRESENTATIVE.values()) <= set(dash.CLEAN_ARMS))
        # REPRESENTATIVE is keyed by MODEL and names the arm that represents it
        self.assertTrue(set(dash.REPRESENTATIVE) <= set(dash.ARM_MODEL.values()))

    def test_dataset_coverage_is_declared_per_arm(self):
        slugs = {slug for _k, slug, _s, _l, _c in dash.ARMS}
        self.assertTrue(set(dash.ARM_DATASETS) <= slugs, set(dash.ARM_DATASETS) - slugs)
        for slug, datasets in dash.ARM_DATASETS.items():
            for d in datasets:
                self.assertIn(d, dash.DATASET_LABEL, f"{slug}: {d} chưa có nhãn")

    def test_coverage_is_keyed_by_slug_not_by_display_id(self):
        # Keying it by the short id made a caller's own arms inherit a coverage
        # promise meant for a different arm that shared the id.
        self.assertIn("ompM6clean_mimo-v2_5", dash.ARM_DATASETS)
        self.assertNotIn("M6", dash.ARM_DATASETS)
        self.assertEqual(dash.datasets_for("no-such-slug"), dash.DATASETS)

    def test_vbench_mc_needs_a_paired_baseline(self):
        # vbench_mc's "score" is agreement with the direct arm, so a harness arm
        # needs its arm-A slug; the baseline computes it against itself.
        self.assertIn("vbench_mc", dash.ARM_DATASETS["ompM6clean_mimo-v2_5"])
        self.assertIn("vbench_mc", dash.ARM_DATASETS["mimo-v2_5"])

    def test_no_registry_label_contains_double_asterisk(self):
        # `**` is not markdown in this app: the ladder renders it literally, which
        # is why the page used to show `**omp sạch**` with visible asterisks.
        for _k, _s, short, label, _c in dash.ARMS:
            self.assertNotIn("**", label, f"arm {short}: nhãn chứa ** sẽ hiện nguyên chữ")

    def test_the_ablation_arm_is_not_counted_as_clean(self):
        # M6L differs from M6 ONLY in having the repo's AGENTS.md injected, so it
        # must stay out of the clean set or the headline range folds it in.
        self.assertIn("M6", dash.CLEAN_ARMS)
        self.assertNotIn("M6L", dash.CLEAN_ARMS)


if __name__ == "__main__":
    unittest.main()
