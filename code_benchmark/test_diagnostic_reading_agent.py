"""Offline tests of MC-118's inputs (diagnostic_reading_agent) and the offline parts of its runner."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from code_benchmark import diagnostic_reading_agent as ra
from code_benchmark import run_legal_agent as rla
from code_benchmark import run_legal_agent_omp as rlo
from code_benchmark import run_reading_agent as rr
from code_benchmark import vi_multimodel as v1


class TestCorpus(unittest.TestCase):
    def test_wrap_changes_only_whitespace_and_breaks_sentences(self) -> None:
        text = "Câu một ở đây. Câu hai? " + "rất dài " * 120 + "hết.\nĐoạn mới… Tiếp theo!"
        wrapped = ra.wrap(text)
        self.assertEqual(v1.normalized_key(wrapped), v1.normalized_key(text))
        lines = wrapped.split("\n")
        self.assertEqual(lines[:2], ["Câu một ở đây.", "Câu hai?"])
        self.assertTrue(all(len(line) <= ra.LINE_LIMIT for line in lines))
        self.assertIn("Đoạn mới…", lines)

    def test_layout_line_ranges_hold_their_passages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src.json"
            contexts = [f"Đoạn văn số {i}. Có câu thứ hai.\nVà một dòng nữa." for i in range(7)]
            contexts.append("  " + contexts[0].upper().replace(" ", "   "))  # a duplicate after normalisation
            source.write_text(json.dumps({"data": [{"id": i, "context": c} for i, c in enumerate(contexts)]},
                                         ensure_ascii=False), encoding="utf-8")
            built = ra.build_corpus(Path(tmp) / "out", {"squad": (source, "id")})
            self.assertEqual(built["passages"], 7)
            docs = Path(tmp) / "out" / "docs"
            for entry in built["index"]:
                lines = (docs / entry["file"]).read_text(encoding="utf-8").split("\n")
                self.assertEqual(lines[entry["heading_line"] - 1], ra.HEADING.format(entry["number"]))
                body = "\n".join(lines[entry["first_line"] - 1:entry["last_line"]])
                self.assertEqual(v1.sha256_bytes(v1.normalized_key(body).encode()), entry["passage_id"])
            self.assertEqual(built["folder_sha256"], rla.listing_sha256(docs))

    def test_passage_of_fails_on_a_missing_passage(self) -> None:
        item = v1.EvalItem("d", "squad", "1", "main-000", "reading", "s", "q?", "nope", "p", "g")
        with self.assertRaises(SystemExit):
            ra.passage_of([item], [{"passage_id": "other", "number": 1}])


class TestItems(unittest.TestCase):
    prompts = {"version": ra.PROMPTS_VERSION, "separator": "\n\n", "DSHF": "INSTR",
               "closed_book": {"head": "H\n\n", "question": "Câu hỏi: ", "tail": "\nTrả lời: "}}
    item = v1.EvalItem("vi-multimodel-v1-vi-squad-200", "squad", "5", "main-000", "reading", "short-direct",
                       "Năm nào?", "pid", "FROZEN READING PROMPT", "1916")

    def test_arm_prompts(self) -> None:
        task = "INSTR\n\nH\n\nCâu hỏi: Năm nào?\nTrả lời: "
        for arm in ra.AGENT_ARMS:
            self.assertEqual(ra.arm_prompt(arm, self.item, self.prompts), task)
        self.assertEqual(ra.arm_prompt("C", self.item, self.prompts), "H\n\nCâu hỏi: Năm nào?\nTrả lời: ")
        self.assertEqual(ra.arm_prompt("O", self.item, self.prompts), "FROZEN READING PROMPT")

    def test_arm_order_is_a_seeded_permutation(self) -> None:
        first = ra.arm_order("k", 1)
        self.assertEqual(sorted(first), sorted(ra.ARMS))
        self.assertEqual(first, ra.arm_order("k", 1))
        self.assertTrue(any(ra.arm_order(f"k{i}", 1) != first for i in range(5)))

    def test_expand_counts(self) -> None:
        out = ra.expand([self.item], self.prompts)
        self.assertEqual(len(out), len(ra.ARMS) * len(ra.DRAWS))
        self.assertEqual(sorted({o.replicate_id for o in out}),
                         sorted(f"{a}-r{d}" for a in ra.ARMS for d in ra.DRAWS))
        self.assertTrue(all(o.gold_answer == "1916" for o in out))

    def test_bm25_ranks_the_matching_passage_first(self) -> None:
        ranks = ra.bm25_ranks(["mèo ăn cá", "chó sủa to", "máy bay cất cánh"], ["chó sủa", "máy bay"])
        self.assertEqual([r[0] for r in ranks], [1, 2])

    def test_judge_sample_halves(self) -> None:
        items = [v1.EvalItem("vi-multimodel-v1-vi-squad-200", "squad", str(i), "main-000", "reading", "s", "q", "p",
                             "x", "g") for i in range(200)]
        items += [v1.EvalItem("vi-multimodel-v1-vi-drop-200", "drop", str(i), "main-000", "reading",
                              ("count", "add_sub", "other")[i % 3], "q", "p", "x", "g") for i in range(200)]
        picked = ra.judge_sample(items)
        self.assertEqual(len(picked), 100)
        self.assertEqual(sum(k.startswith("vi-multimodel-v1-vi-squad") for k in picked), 50)
        self.assertEqual(picked, ra.judge_sample(items))


class TestRunner(unittest.TestCase):
    def test_with_cwd_and_workdir(self) -> None:
        self.assertEqual(rr.with_cwd(["omp", "--cwd", "/old", "-p"], "/work/bai-viet"),
                         ["omp", "--cwd", "/work/bai-viet", "-p"])
        with self.assertRaises(SystemExit):
            rr.with_cwd(["omp"], "/x")
        before = rla.WORKDIR
        try:
            rr.set_workdir("/work/bai-viet")
            self.assertEqual((rla.WORKDIR, rlo.WORKDIR, rr.la.WORKDIR), ("/work/bai-viet",) * 3)
        finally:
            rr.set_workdir(before)

    def test_the_pin_ignores_only_the_kernel_lines(self) -> None:
        old = "x\n<workstation>\n- OS: linux 7.0.0-43-generic\n- Kernel: #43-Ubuntu SMP PREEMPT_DYNAMIC Fri Oct 23 " \
              "13:25:25 UTC 2026\n- CPU: c\n</workstation>\ny"
        new = old.replace("7.0.0-43", "7.0.0-44").replace("#43-Ubuntu SMP PREEMPT_DYNAMIC Fri Oct 23 13:25:25",
                                                             "#44-Ubuntu SMP PREEMPT_DYNAMIC Fri Nov  6 02:38:04")
        pin = v1.sha256_bytes(old.encode())
        self.assertEqual(rr.kernel_blind_system_sha256([{"role": "system", "content": new}]), pin)
        self.assertEqual(rr.kernel_blind_system_sha256([{"role": "system", "content": old}]), pin)
        self.assertNotEqual(rr.kernel_blind_system_sha256([{"role": "system", "content": new.replace("CPU: c", "CPU: d")}]),
                            pin)
        self.assertIsNone(rr.kernel_blind_system_sha256([{"role": "user", "content": old}]))

    def test_omps_is_ompf_plus_the_system_prompt(self) -> None:
        protocol = ra.load_protocol()
        for model in ra.MODELS:
            specs = rr.harness_protocols(protocol, model)
            ompf, omps = specs["OMPF"]["harness"]["argv"], specs["OMPS"]["harness"]["argv"]
            self.assertEqual(omps[:len(ompf)], ompf)
            self.assertEqual(omps[len(ompf):], [rr.SYSTEM_PROMPT_FLAG, rr.omps_prompt(protocol, model)])
            self.assertEqual(ompf[ompf.index("--cwd") + 1], ra.WORKDIR)
            self.assertNotIn(rr.LEGAL_WORKDIR, specs["OMPF"]["harness"]["invocation"])

    def test_paging_reads_omp_and_dsh_notes(self) -> None:
        body = {"messages": [{"role": "tool", "content": "x\n[Showing lines 1-300 of 523. Use :301 to continue]"},
                             {"role": "tool", "content": "y\n(Output capped. Showing lines 1-398. Use offset=399 to "
                                                         "continue.)"},
                             {"role": "tool", "content": "z\n[Showing lines 1-108 and 194-300 of 300; 85 middle]"}]}
        out = rr.paging([{"body_received": json.dumps(body)}])
        self.assertTrue(out["omp_paged"])
        self.assertEqual(out["dsh_capped"], [[1, 398]])
        self.assertEqual([p["elided"] for p in out["pages"]], [False, True])
        whole = rr.paging([{"body_received": json.dumps({"messages": [{"role": "tool",
                                                                       "content": "[Showing lines 1-200 of 200]"}]})}])
        self.assertFalse(whole["omp_paged"])

    def test_passage_read_ignores_line_breaks(self) -> None:
        passage = "Câu một của đoạn văn này khá dài để vượt tám mươi ký tự. Câu hai tiếp theo với nhiều chữ hơn nữa."
        body = {"messages": [{"role": "tool", "content": "12: " + ra.wrap(passage).replace("\n", "\n")}]}
        self.assertTrue(rr.passage_read([{"body_received": json.dumps(body)}], ra.wrap(passage)))

    def test_a_blocked_attempt_keeps_its_identity(self) -> None:
        class Guard:
            def exhausted(self) -> bool:
                return True

        class Outage:
            def tripped(self) -> bool:
                return False

        context = rr.AttemptContext(model="qwen", harnesses={}, protocols={}, docs=Path("."), output=Path("."),
                                    proxies={}, session_header=None, profile_id="p", card_id="MC-118")
        item = v1.EvalItem("vi-multimodel-v1-vi-drop-200", "drop", "7", "C-r1", "reading", "count", "q", "p", "x", "g")
        request = rr.make_request("qwen", "MC-118", Guard(), Outage(), 2, rr.rlm.BadRequests(),  # type: ignore[arg-type]
                                  direct=lambda *_: {})
        row = request(context, item, 3, 1)
        self.assertEqual((row["status"], row["error_type"], row["shard"], row["lane"], row["arm"]),
                         ("request_error", "budget_cap", 3, 1, "C"))
        for key in ("run_key", "profile_id", "protocol_id", "measurement_card_id", "phase"):
            self.assertTrue(row[key])

    def test_a_blocked_direct_row_carries_the_model_id(self) -> None:
        context = rr.AttemptContext(model="mimo", harnesses={}, protocols={}, docs=Path("."), output=Path("."),
                                    proxies={}, session_header=None, profile_id="p", card_id="MC-118",
                                    model_id="mimo-v2.6-flash")
        item = v1.EvalItem("vi-multimodel-v1-vi-drop-200", "drop", "7", "C-r1", "reading", "count", "q", "p", "x", "g")
        row = rr.blocked_row(item, context, "C", 0, 0, "budget_cap")
        self.assertEqual((row["model_id"], row["protocol_id"]), ("mimo-v2.6-flash", ra.PROTOCOL_ID))

    def test_budget_amendments_apply_in_order_and_only_raise(self) -> None:
        spec = {"budget_tokens": 85}
        keys = {"id": "a", "rule": "budget_tokens", "date": "d", "basis": "b", "authorized": "o"}
        registration = {"amendments": [{**keys, "budget_tokens": {"mimo": 140}}, {"note": "other"},
                                       {**keys, "budget_tokens": {"mimo": 350}}]}
        self.assertEqual(rr.budget_tokens(spec, registration, "mimo"), 350)
        self.assertEqual(rr.budget_tokens(spec, {"amendments": []}, "mimo"), 85)
        with self.assertRaises(SystemExit):
            rr.budget_tokens(spec, {"amendments": [{**keys, "budget_tokens": {"mimo": 140}},
                                                   {**keys, "budget_tokens": {"mimo": 100}}]}, "mimo")
        self.assertIsInstance(threading.Event(), threading.Event)


if __name__ == "__main__":
    unittest.main()
