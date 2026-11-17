"""Offline tests of the MC-110b recovery: the overlay of retried attempts on MC-110's rows, the passes through the
real engine with a fake request (round by round, only capped attempts, a second cap after three timeouts), the
outputs, and the gates. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_retry_vmlu_test_loop_mimo_900s
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import tempfile
import threading
import unittest
from collections import Counter
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from code_benchmark import diagnostic_vmlu_test_loop as vt
from code_benchmark import retry_vmlu_test_loop_mimo_900s as rr
from code_benchmark import run_vmlu_test_loop as rvt
from code_benchmark import vi_multimodel as v1
from code_benchmark import vi_multimodel_expansion as v2
from code_benchmark.test_vmlu_test_loop import MIMO, MIMO_CONFIG, synthetic_items

REGISTRATION = rvt.load_registration(vt.REGISTRATION_PATHS["mimo"])
TIMEOUT = {"status": "request_error", "finish_reason": "error", "error_type": "APITimeoutError", "fatal": False}
# MC-110's attempts per item: a letter, or None for an attempt capped after three timeouts at 300 s.
PARENT = {
    "01-0000": {"B-r1": "A", "B-r2": "A"},
    "01-0001": {"B-r1": None, "B-r2": "B", "S-r1": "B"},
    "01-0002": {"B-r1": "A", "B-r2": "B", "S-r1": None, "S-r2": "C", "S-r3": "D"},
    "01-0003": {"B-r1": None, "B-r2": None, "S-r1": None, "S-r2": None, "S-r3": None},
    "01-0004": {"B-r1": "A", "B-r2": "B", "S-r1": None, "S-r2": "B", "S-r3": "B"},
    "01-0005": {"B-r1": "D", "B-r2": None, "S-r1": "D"},
}
# The recovery's replies; None times out every time.
REPLIES = {"01-0001:B-r1": "B", "01-0002:S-r1": "A", "01-0003:B-r1": "C", "01-0003:B-r2": "C", "01-0004:S-r1": None,
           "01-0005:B-r2": "A"}


def raw(replicate: str, letter: str) -> str:
    return letter if replicate.startswith("B") else f"Lời giải.\nĐáp án: {letter}"


class Recovery(unittest.TestCase):
    def setUp(self):
        self.saved = (rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL, rvt.base.request)
        rvt.base.MODEL, rvt.base.PROFILE = MIMO_CONFIG["students"]["mimo"]["model_id"], "mimo-v2-6-flash"
        rvt.base.PROTOCOL = vt.PROTOCOL_ID
        self.tmp = tempfile.TemporaryDirectory()
        self.parent = Path(self.tmp.name) / "parent"
        self.output = Path(self.tmp.name) / "out"
        items = vt.expand(synthetic_items(len(PARENT)), MIMO)
        self.manifest: dict[str, Any] = {"items": [v2._item_manifest(item) for item in items]}  # noqa: SLF001
        self.manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(self.manifest))
        self.rebuilt = {item.run_key: item for item in items}
        self.ids = [item.item_id for item in items if item.replicate_id == "B-r1"]

    def tearDown(self):
        rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL, rvt.base.request = self.saved
        self.tmp.cleanup()

    def key(self, short: str) -> str:
        return f"{vt.DATASET}:{short}"

    def write_parent(self, attempts: dict[str, dict[str, str | None]] = PARENT) -> None:
        rows = []
        for item_id, replicates in attempts.items():
            for replicate, letter in replicates.items():
                row = rvt._base_row(self.rebuilt[self.key(f"{item_id}:{replicate}")], "MC-110", 0, 0, "fake")  # noqa: SLF001
                if letter is None:
                    rows += [{**row, **TIMEOUT, "latency_s": 300.0}] * 3
                else:
                    rows.append({**row, "status": "complete", "raw_response": raw(replicate, letter),
                                 "finish_reason": "stop", "total_tokens": 10, "latency_s": 1.0})
        self.parent.mkdir(parents=True)
        (self.parent / "attempts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    def parent_loop(self, parent_rows: dict[str, Any]) -> dict[str, Any]:
        view = rvt.with_timeout_terminals(self.parent, parent_rows, rvt.timeout_cap_amendment(REGISTRATION))[0]
        return {s.item_id: {"answer": s.answer, "before": s.predictions.get("B-r1")}
                for s in vt.plan(self.ids, view, None, "mimo")}

    def fake_request(self, replies: Mapping[str, str | None]):
        sent: Counter[str] = Counter()
        lock = threading.Lock()

        def request(client, item, shard, lane):
            short = item.run_key.split(":", 1)[1]
            with lock:
                sent[short] += 1
            row = rvt._base_row(item, rr.CARD_ID, shard, lane, "fake")  # noqa: SLF001
            letter = replies[short]
            if letter is None:
                row.update(TIMEOUT)
            elif letter == "429":
                row.update({"status": "request_error", "finish_reason": "error", "error_type": "RateLimitError",
                            "http_status": 429, "fatal": False})
            else:
                row.update({"status": "complete", "raw_response": raw(item.replicate_id, letter),
                            "finish_reason": "stop", "total_tokens": 100})
            row.update({"latency_s": 0.001, "finished_at": rvt.base.now()})
            return row
        return request, sent

    def recover(self, replies: Mapping[str, str | None] = REPLIES, max_passes: int = rr.MAX_PASSES):
        parent_rows, capped = rr.parent_state(self.manifest, REGISTRATION, self.parent)
        request, sent = self.fake_request(replies)
        rvt.base.request = request
        callback = rr.writer(self.ids, parent_rows, capped, self.parent_loop(parent_rows))
        with contextlib.redirect_stdout(io.StringIO()):
            status = rr.run_recovery(self.output, self.manifest, self.rebuilt, self.ids, {"runner_sha256": "test"},
                                     None, False, parent_rows=parent_rows, capped=capped, score_callback=callback,
                                     max_passes=max_passes)
        return status, sent, capped


class TestOverlay(Recovery):
    def test_a_capped_attempt_is_missing_then_answered_or_capped_again(self):
        self.write_parent()
        parent_rows, capped = rr.parent_state(self.manifest, REGISTRATION, self.parent)
        self.assertEqual(len(capped), 9)
        key, other = self.key("01-0001:B-r1"), self.key("01-0002:S-r1")
        view, again = rr.recovery_view(parent_rows, {}, Counter(), frozenset(capped))
        self.assertNotIn(key, view)
        self.assertEqual((again, view[self.key("01-0001:B-r2")]), ([], parent_rows[self.key("01-0001:B-r2")]))
        done = {**parent_rows[key], "status": "complete", "raw_response": "B", "measurement_card_id": rr.CARD_ID}
        view, again = rr.recovery_view(parent_rows, {key: done}, Counter({other: 3}), frozenset(capped))
        self.assertIs(view[key], done)
        self.assertEqual((again, view[other]["status"], view[other]["raw_response"], view[other]["terminal"]),
                         ([other], "complete", "", "MC-110b: 3 timeouts at 900 s"))
        self.assertEqual(parent_rows[other]["status"], "request_error")  # MC-110's rows are not changed
        view, again = rr.recovery_view(parent_rows, {}, Counter({other: 2}), frozenset(capped))
        self.assertNotIn(other, view)


class TestPasses(Recovery):
    def test_round_by_round_only_capped_attempts_and_mc110_untouched(self):
        self.write_parent()
        before = v1.sha256_file(self.parent / "attempts.jsonl")
        status, sent, _ = self.recover()
        self.assertEqual(status, "complete")
        self.assertEqual(dict(sent), {"01-0001:B-r1": 1, "01-0002:S-r1": 1, "01-0003:B-r1": 1, "01-0003:B-r2": 1,
                                      "01-0004:S-r1": 3, "01-0005:B-r2": 1})
        self.assertEqual(v1.sha256_file(self.parent / "attempts.jsonl"), before)
        with (self.output / "submission_loop.csv").open() as handle:
            loop = {row["id"]: row["answer"] for row in csv.DictReader(handle)}
        with (self.output / "submission_before.csv").open() as handle:
            first = {row["id"]: row["answer"] for row in csv.DictReader(handle)}
        self.assertEqual(loop, {"01-0000": "A", "01-0001": "B", "01-0002": "A", "01-0003": "C", "01-0004": "B",
                                "01-0005": "D"})
        self.assertEqual(first, {"01-0000": "A", "01-0001": "B", "01-0002": "A", "01-0003": "C", "01-0004": "A",
                                 "01-0005": "D"})
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual((summary["retry_candidates"], summary["sent"], summary["completed"],
                          summary["completed_with_answer"], summary["ledger_rows"]), (9, 6, 5, 5, 8))
        self.assertEqual(summary["capped_again"], [self.key("01-0004:S-r1")])
        self.assertEqual(summary["never_needed"], [self.key(f"01-0003:S-r{n}") for n in (1, 2, 3)])
        self.assertEqual(summary["changed_from_mc110"], {"before": 2, "loop": 2})  # 01-0002 C -> A, 01-0003 '' -> C
        self.assertEqual((summary["final_items"], summary["empty_final"], summary["rounds"]),
                         (6, 0, {"1": 3, "2": 2, "3": 1}))
        records = {r["item_id"]: r for r in map(json.loads, (self.output / "loop.jsonl").read_text().splitlines())}
        self.assertEqual((records["01-0002"]["mc110_answer"], records["01-0002"]["answer"]), ("C", "A"))

    def test_an_attempt_mc110_did_not_cap_is_never_sent(self):
        attempts = {**PARENT, "01-0000": {"B-r1": "A"}}  # B-r2 has no row in MC-110: the rule would ask for it
        self.write_parent(attempts)
        with self.assertRaises(SystemExit):
            self.recover()

    def test_a_pass_that_neither_completes_nor_times_out_stalls(self):
        self.write_parent()
        status, sent, _ = self.recover(dict.fromkeys(REPLIES, "429") | {f"01-0003:B-r{n}": "429" for n in (1, 2)})
        self.assertEqual(status, "stalled")
        self.assertEqual(set(sent.values()), {1})
        self.assertFalse((self.output / "submission_loop.csv").exists())


class TestGates(Recovery):
    def test_the_card_the_detail_card_and_mc110s_final_ledger(self):
        self.write_parent()
        _, capped = rr.parent_state(self.manifest, REGISTRATION, self.parent)
        root = Path(self.tmp.name)
        (root / rr.CARD_FILE).parent.mkdir(parents=True)
        (root / rr.CARD_FILE).write_text("detail")
        gates = {g.name: g.ok for g in rr.evaluate_gates(self.manifest, capped, True, "ok", parent=self.parent,
                                                         card_text="## MC-110b — recovery\n", root=root)}
        self.assertEqual(gates, {"card_registered": True, "detail_card": True, "parent_ledger": False,
                                 "parent_final": False, "retry_candidates": False, "route_identity": True})
        gates = {g.name: g.ok for g in rr.evaluate_gates(self.manifest, capped, True, "ok", parent=self.parent,
                                                         card_text="## MC-110 — the loop\n## MC-110bc\n", root=self.parent)}
        self.assertEqual((gates["card_registered"], gates["detail_card"]), (False, False))


@unittest.skipUnless((rr.PARENT / "attempts.jsonl").is_file(), "MC-110's outputs are not on this machine")
class TestRealParent(unittest.TestCase):
    def test_mc110s_final_state_passes_its_gates(self):
        saved = (rvt.base.MODEL, rvt.base.PROTOCOL)
        try:
            rvt.base.MODEL, rvt.base.PROTOCOL = MIMO_CONFIG["students"]["mimo"]["model_id"], vt.PROTOCOL_ID
            manifest, _ = vt.build_manifest("mimo")
            _, capped = rr.parent_state(manifest, REGISTRATION)
            gates = {g.name: g.ok for g in rr.evaluate_gates(manifest, capped, True, "ok")}
        finally:
            rvt.base.MODEL, rvt.base.PROTOCOL = saved
        self.assertEqual(len(capped), rr.PARENT_CAPPED)
        self.assertTrue(gates["parent_ledger"] and gates["parent_final"] and gates["retry_candidates"])


if __name__ == "__main__":
    unittest.main()
