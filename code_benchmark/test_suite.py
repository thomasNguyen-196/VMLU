import csv
import json
import random
import shutil
import subprocess  # nosec B404 — test harness shells out to local CLI/node only
import sys
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
from code_benchmark.run_reading_eval import (
    build_reading_prompt,
    join_manifest,
    index_sources,
    resume_key,
    find_latest_reading_checkpoint,
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
)
from code_benchmark.build_review_ui import (
    build_blob,
    model_from_filename,
    load_answers_csv,
    review_items,
    embed_json,
    render_html,
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
        # MC raw_result_*.csv files must NOT be candidates for resume
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "raw_result_1047.csv").touch()
            (tmp / "reading_result_100.csv").touch()
            (tmp / "reading_result_400.csv").touch()
            latest = find_latest_reading_checkpoint(tmp)
            assert latest is not None
            self.assertEqual(latest.name, "reading_result_400.csv")
            (tmp / "raw_result_9999.csv").touch()
            latest = find_latest_reading_checkpoint(tmp)
            assert latest is not None
            self.assertEqual(latest.name, "reading_result_400.csv")  # still ignores MC


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


if __name__ == "__main__":
    unittest.main()
