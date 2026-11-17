"""Offline tests of the MC-110c recovery: the candidates (timeouts and replies cut by the 20,000-token cap), the reuse of
MC-110b's stopped rows, the overlay, the passes through the real engine with a fake request, the request settings and
the gates. No endpoint is called.

  .venv/bin/python -m unittest code_benchmark.test_retry_vmlu_test_loop_mimo_40k
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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from code_benchmark import diagnostic_vmlu_test_loop as vt
from code_benchmark import retry_vmlu_test_loop_mimo_40k as r40
from code_benchmark import run_vmlu_test_loop as rvt
from code_benchmark import vi_multimodel as v1
from code_benchmark import vi_multimodel_expansion as v2
from code_benchmark.test_run_self_loop import FakeClient
from code_benchmark.test_vmlu_test_loop import MIMO, MIMO_CONFIG, synthetic_items

REGISTRATION = rvt.load_registration(vt.REGISTRATION_PATHS["mimo"])
STUDENT = MIMO_CONFIG["students"]["mimo"]
TIMEOUT = {"status": "request_error", "finish_reason": "error", "error_type": "APITimeoutError", "fatal": False}
# MC-110's attempts: a letter, "T" for an attempt capped after three timeouts, "L" for a reply cut by the cap.
PARENT = {
    "01-0000": {"B-r1": "A", "B-r2": "A"},
    "01-0001": {"B-r1": "L", "B-r2": "B", "S-r1": "B"},
    "01-0002": {"B-r1": "A", "B-r2": "B", "S-r1": "T", "S-r2": "L", "S-r3": "D"},
    "01-0003": {"B-r1": "L", "B-r2": "L", "S-r1": "L", "S-r2": "L", "S-r3": "L"},
    "01-0004": {"B-r1": "A", "B-r2": "B", "S-r1": "L", "S-r2": "B", "S-r3": "B"},
    "01-0005": {"B-r1": "D", "B-r2": "T", "S-r1": "D"},
}
# MC-110b's rows: one stopped below the cap (reused), one cut by it (not reused).
SIBLING = {"01-0002:S-r1": "A", "01-0005:B-r2": "L"}
# This card's replies; None times out every time.
REPLIES = {"01-0001:B-r1": "B", "01-0003:B-r1": "C", "01-0003:B-r2": "C", "01-0004:S-r1": None, "01-0005:B-r2": "A"}


def raw(replicate: str, letter: str) -> str:
    return letter if replicate.startswith("B") else f"Lời giải.\nĐáp án: {letter}"


class Recovery(unittest.TestCase):
    def setUp(self):
        self.saved = (rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL, rvt.base.request)
        rvt.base.MODEL, rvt.base.PROFILE, rvt.base.PROTOCOL = STUDENT["model_id"], STUDENT["profile_id"], vt.PROTOCOL_ID
        self.tmp = tempfile.TemporaryDirectory()
        self.parent = Path(self.tmp.name) / "parent"
        self.sibling = Path(self.tmp.name) / "sibling"
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

    def rows(self, short: str, value: str, card: str) -> list[dict[str, Any]]:
        replicate = short.rsplit(":", 1)[1]
        row = rvt._base_row(self.rebuilt[self.key(short)], card, 0, 0, "fake")  # noqa: SLF001
        if value == "T":
            return [{**row, **TIMEOUT, "latency_s": 300.0}] * 3
        if value == "L":
            return [{**row, "status": "complete", "raw_response": "", "finish_reason": "length", "total_tokens": 20000}]
        return [{**row, "status": "complete", "raw_response": raw(replicate, value), "finish_reason": "stop",
                 "total_tokens": 10}]

    def write(self, folder: Path, rows: list[dict[str, Any]]) -> None:
        folder.mkdir(parents=True)
        (folder / "attempts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    def write_inputs(self, parent: Mapping[str, Mapping[str, str]] = PARENT) -> None:
        self.write(self.parent, [row for item_id, reps in parent.items() for rep, value in reps.items()
                                 for row in self.rows(f"{item_id}:{rep}", value, "MC-110")])
        self.write(self.sibling, [row for short, value in SIBLING.items() for row in self.rows(short, value, "MC-110b")])

    def state(self):
        parent_rows, capped = r40.mc110b.parent_state(self.manifest, REGISTRATION, self.parent)
        cands = r40.candidates(parent_rows, capped)
        reused = r40.reusable(r40.latest_rows(self.sibling, self.manifest), cands)
        return parent_rows, capped, cands, reused

    def parent_loop(self, parent_rows: dict[str, Any]) -> dict[str, Any]:
        view = rvt.with_timeout_terminals(self.parent, parent_rows, rvt.timeout_cap_amendment(REGISTRATION))[0]
        return {s.item_id: {"answer": s.answer, "before": s.predictions.get("B-r1")}
                for s in vt.plan(self.ids, view, None, "mimo")}

    def recover(self, replies: Mapping[str, str | None] = REPLIES):
        parent_rows, _, cands, reused = self.state()
        sent: Counter[str] = Counter()
        lock = threading.Lock()

        def request(client, item, shard, lane):
            short = item.run_key.split(":", 1)[1]
            with lock:
                sent[short] += 1
            row = rvt._base_row(item, r40.CARD_ID, shard, lane, "fake")  # noqa: SLF001
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

        rvt.base.request = request
        callback = r40.writer(self.ids, parent_rows, reused, cands, self.parent_loop(parent_rows))
        with contextlib.redirect_stdout(io.StringIO()):
            status = r40.run_recovery(self.output, self.manifest, self.rebuilt, self.ids, {"runner_sha256": "test"},
                                      None, False, parent_rows=parent_rows, reused=reused, cands=cands,
                                      score_callback=callback)
        return status, sent


class TestCandidates(Recovery):
    def test_timeouts_and_cut_replies_are_candidates_and_only_stopped_mc110b_rows_are_reused(self):
        self.write_inputs()
        parent_rows, capped, cands, reused = self.state()
        self.assertEqual(Counter(cands.values()), {"timeout": 2, "length": 8})
        self.assertEqual(sorted(k.split(":", 1)[1] for k in capped), ["01-0002:S-r1", "01-0005:B-r2"])
        self.assertEqual(list(reused), [self.key("01-0002:S-r1")])
        view, again = r40.recovery_view(parent_rows, reused, {}, Counter(), cands)
        self.assertIs(view[self.key("01-0002:S-r1")], reused[self.key("01-0002:S-r1")])
        self.assertNotIn(self.key("01-0001:B-r1"), view)  # a reply cut by the cap is asked again
        self.assertEqual((again, view[self.key("01-0002:S-r3")]), ([], parent_rows[self.key("01-0002:S-r3")]))
        view, again = r40.recovery_view(parent_rows, reused, {}, Counter({self.key("01-0004:S-r1"): 3}), cands)
        self.assertEqual((again, view[self.key("01-0004:S-r1")]["terminal"]),
                         ([self.key("01-0004:S-r1")], "MC-110c: 3 timeouts at 1800 s"))


class TestPasses(Recovery):
    def test_round_by_round_with_reuse_and_both_parents_untouched(self):
        self.write_inputs()
        hashes = [v1.sha256_file(folder / "attempts.jsonl") for folder in (self.parent, self.sibling)]
        status, sent = self.recover()
        self.assertEqual(status, "complete")
        self.assertEqual(dict(sent), {"01-0001:B-r1": 1, "01-0003:B-r1": 1, "01-0003:B-r2": 1, "01-0004:S-r1": 3,
                                      "01-0005:B-r2": 1})
        self.assertEqual([v1.sha256_file(folder / "attempts.jsonl") for folder in (self.parent, self.sibling)], hashes)
        with (self.output / "submission_loop.csv").open() as handle:
            loop = {row["id"]: row["answer"] for row in csv.DictReader(handle)}
        with (self.output / "submission_before.csv").open() as handle:
            first = {row["id"]: row["answer"] for row in csv.DictReader(handle)}
        self.assertEqual(loop, {"01-0000": "A", "01-0001": "B", "01-0002": "A", "01-0003": "C", "01-0004": "B",
                                "01-0005": "D"})
        self.assertEqual(first, {"01-0000": "A", "01-0001": "B", "01-0002": "A", "01-0003": "C", "01-0004": "A",
                                 "01-0005": "D"})
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual((summary["candidates"], summary["candidates_by_cause"], summary["reused_from_mc110b"]),
                         (10, {"length": 8, "timeout": 2}, 1))
        self.assertEqual((summary["sent"], summary["ledger_rows"], summary["completed"], summary["completed_with_answer"]),
                         (5, 7, 4, 4))
        self.assertEqual(summary["capped_again"], [self.key("01-0004:S-r1")])
        self.assertEqual(summary["never_needed"],
                         [self.key(k) for k in ("01-0002:S-r2", "01-0003:S-r1", "01-0003:S-r2", "01-0003:S-r3")])
        self.assertEqual(summary["changed_from_mc110"], {"before": 2, "loop": 2})  # 01-0002 D -> A, 01-0003 '' -> C
        self.assertEqual((summary["final_items"], summary["empty_final"], summary["rounds"]),
                         (6, 0, {"1": 3, "2": 2, "3": 1}))

    def test_an_attempt_that_is_not_a_candidate_is_never_sent(self):
        self.write_inputs({**PARENT, "01-0000": {"B-r1": "A"}})  # B-r2 has no row in MC-110: the rule would ask for it
        with self.assertRaises(SystemExit):
            self.recover()

    def test_a_pass_that_neither_completes_nor_times_out_stalls(self):
        self.write_inputs()
        status, sent = self.recover(dict.fromkeys(REPLIES, "429"))
        self.assertEqual(status, "stalled")
        self.assertEqual(set(sent.values()), {1})
        self.assertFalse((self.output / "submission_loop.csv").exists())


class TestRequest(Recovery):
    def test_only_the_cap_and_the_gate_change(self):
        settings = r40.request_settings(STUDENT)
        self.assertEqual((settings["max_completion_tokens"], settings["max_in_flight"]), (40_000, 12))
        self.assertEqual({k: v for k, v in settings.items() if k not in ("max_completion_tokens", "max_in_flight")},
                         {k: v for k, v in STUDENT.items() if k not in ("max_completion_tokens", "max_in_flight")})
        request = rvt.make_mimo_request(settings, r40.CARD_ID, rvt.pr.BudgetGuard(10**6), rvt.pr.OutageGuard(4),
                                        rvt.ModelPin(STUDENT["model_identity"]))
        client = FakeClient(("Đáp án: B", STUDENT["model_id"], None))
        item = vt.expand(synthetic_items(1), MIMO)[0]
        row = request(client, item, 0, 0)
        assert client.kwargs is not None
        self.assertEqual((row["status"], row["max_tokens"], client.kwargs["max_completion_tokens"]),
                         ("complete", 40_000, 40_000))
        self.assertEqual(client.kwargs["extra_headers"], {"x-opencode-session": rvt.session_id("MC-110c", item.run_key)})


class TestGates(Recovery):
    def test_the_card_and_both_ledgers(self):
        self.write_inputs()
        _, capped, cands, reused = self.state()
        root = Path(self.tmp.name)
        (root / r40.CARD_FILE).parent.mkdir(parents=True)
        (root / r40.CARD_FILE).write_text("detail")
        gates = {g.name: g.ok for g in r40.evaluate_gates(self.manifest, capped, cands, reused, True, "ok",
                                                          parent=self.parent, sibling=self.sibling,
                                                          card_text="## MC-110c — 40k\n", root=root)}
        self.assertEqual(gates, {"card_registered": True, "detail_card": True, "parent_ledger": False,
                                 "parent_final": False, "retry_candidates": False, "sibling_ledger": False,
                                 "candidates": False, "route_identity": True})


@unittest.skipUnless((r40.PARENT / "attempts.jsonl").is_file() and (r40.SIBLING / "attempts.jsonl").is_file(),
                     "MC-110's and MC-110b's outputs are not on this machine")
class TestRealInputs(unittest.TestCase):
    def test_the_registered_candidates_and_reuse(self):
        saved = (rvt.base.MODEL, rvt.base.PROTOCOL)
        try:
            rvt.base.MODEL, rvt.base.PROTOCOL = STUDENT["model_id"], vt.PROTOCOL_ID
            manifest, _ = vt.build_manifest("mimo")
            parent_rows, capped = r40.mc110b.parent_state(manifest, REGISTRATION)
            cands = r40.candidates(parent_rows, capped)
            reused = r40.reusable(r40.latest_rows(r40.SIBLING, manifest), cands)
            gates = {g.name: g.ok for g in r40.evaluate_gates(manifest, capped, cands, reused, True, "ok")}
        finally:
            rvt.base.MODEL, rvt.base.PROTOCOL = saved
        self.assertEqual((dict(Counter(cands.values())), len(reused)), (r40.CANDIDATES, r40.REUSED))
        self.assertTrue(all(gates[name] for name in ("parent_ledger", "parent_final", "retry_candidates",
                                                     "sibling_ledger", "candidates")))


if __name__ == "__main__":
    unittest.main()
