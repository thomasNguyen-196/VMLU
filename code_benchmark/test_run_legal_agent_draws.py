"""Offline tests for MC-115's runner (run_legal_agent_draws). Run from the repo root:
  .venv/bin/python -m unittest code_benchmark.test_run_legal_agent_draws
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from code_benchmark import diagnostic_legal_agent_draws as ld
from code_benchmark import diagnostic_legal_agent_v2 as l2
from code_benchmark import run_legal_agent_draws as rd
from code_benchmark import vi_multimodel as v1


def item(dataset: str, item_id: str) -> v1.EvalItem:
    return v1.EvalItem(dataset_id=dataset, source_dataset=dataset, item_id=item_id, replicate_id="DSHF-r3",
                       task="multiple_choice", stratum="s", question="q", passage_id="p", prompt="t", gold_answer="A")


class Paths(unittest.TestCase):
    def test_arms(self):
        self.assertEqual([rd.harness_of(a) for a in ("DSHF", "OMPF", "B", "C")], ["dsh", "omp", "direct", "direct"])
        with self.assertRaises(SystemExit):
            rd.harness_of("DSH")

    def test_each_item_gets_its_own_folder(self):
        context = rd.AttemptContext(dsh=None, omp=None, docs={"v1": Path("/a"), "v2": Path("/b")},  # type: ignore[arg-type]
                                    corpus_of={f"{ld.LEGAL_MC}:LG-1": "v1", "bidlqa-train:T-1": "v2"},
                                    output=Path("/o"), dsh_proxy=None, omp_proxy=None,  # type: ignore[arg-type]
                                    dsh_protocol={}, omp_protocol={})
        self.assertEqual(context.docs_for(item(ld.LEGAL_MC, "LG-1")), Path("/a"))
        self.assertEqual(context.docs_for(item("bidlqa-train", "T-1")), Path("/b"))
        with self.assertRaises(SystemExit):
            context.docs_for(item("bidlqa-train", "T-2"))

    def test_folder_with_the_wrong_hash_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "c" / "docs"
            docs.mkdir(parents=True)
            (docs / "a.txt").write_text("x", encoding="utf-8")
            protocol = {"corpora": {"v1": {"folder": "c", "folder_sha256": "0" * 64, "datasets": [ld.LEGAL_MC]}}}
            found, problems = rd.check_folders(protocol, rebuild=False, root=Path(tmp))
            self.assertEqual(found["v1"], docs)
            self.assertEqual(len(problems), 1)


class Smoke(unittest.TestCase):
    def test_registered_questions_and_folders(self):
        loaded = rd.load_smoke(ld.load_protocol())
        self.assertEqual([(q["id"], corpus) for q, corpus in loaded], [("smoke-2", "v1"), ("smoke-s2", "v2")])

    def test_tasks_use_mc112s_layout(self):
        prompts = l2.load_prompts()
        mc = {"id": "m", "prompt": "Câu hỏi?"}
        span = {"id": "s", "kind": "span", "question": "Ai?"}
        self.assertEqual(rd.smoke_task(mc, prompts), prompts["DSHF"] + prompts["separator"] + "Câu hỏi?")
        self.assertEqual(rd.smoke_task(span, prompts),
                         l2.agent_task("DSHF", l2.closed_book_prompt("Ai?", prompts), prompts))

    def test_smoke_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(rd.smoke_problems({"smoke": {"reports": []}}, root), ["no smoke report is registered"])
            rows = [{"id": "s", "harness": "dsh", "status": "complete", "system_prompt_matches_mc113": None},
                    {"id": "s", "harness": "omp", "status": "complete", "system_prompt_matches_mc113": True}]
            path = root / "r.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            good = {"smoke": {"reports": [{"path": "r.json", "sha256": v1.sha256_file(path)}]}}
            self.assertEqual(rd.smoke_problems(good, root), [])
            rows[1]["system_prompt_matches_mc113"] = False
            path.write_text(json.dumps(rows), encoding="utf-8")
            changed = {"smoke": {"reports": [{"path": "r.json", "sha256": v1.sha256_file(path)}]}}
            self.assertEqual(len(rd.smoke_problems(changed, root)), 1)
            self.assertEqual(len(rd.smoke_problems(good, root)), 1)  # the old hash no longer matches


if __name__ == "__main__":
    unittest.main()
