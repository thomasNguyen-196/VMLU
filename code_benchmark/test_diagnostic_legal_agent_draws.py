"""Offline tests for MC-115's manifest (diagnostic_legal_agent_draws). Run from the repo root:
  .venv/bin/python -m unittest code_benchmark.test_diagnostic_legal_agent_draws
"""
from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from code_benchmark import diagnostic_legal_agent_draws as ld
from code_benchmark import diagnostic_prospective as dp
from code_benchmark import vi_multimodel as v1

PROTOCOL = {"corpora": {"v1": {"datasets": [ld.LEGAL_MC]}, "v2": {"datasets": "other"}}}


def item(dataset: str, item_id: str, replicate: str, prompt: str, task: str = "multiple_choice") -> v1.EvalItem:
    return v1.EvalItem(dataset_id=dataset, source_dataset=dataset, item_id=item_id, replicate_id=replicate, task=task,
                       stratum="s", question="q", passage_id="p", prompt=prompt, gold_answer="A")


def rebuilt_of(items: list[v1.EvalItem]) -> dict[str, v1.EvalItem]:
    return {i.run_key: i for i in items}


def fake_sources() -> tuple[dict[str, dict[str, v1.EvalItem]], dict[str, v1.EvalItem]]:
    """One Legal MC item, one Part M VMLU item and one Part S item, each arm at draws 1-2."""
    mc112 = rebuilt_of([item(ld.LEGAL_MC, "LG-1", f"{arm}-r{d}", f"{arm}-task") for d in (1, 2) for arm in ("DSH", "DSHF")])
    mc113 = rebuilt_of([item(ld.LEGAL_MC, "LG-1", f"OMPF-r{d}", "DSHF-task") for d in (1, 2)])
    mc114 = rebuilt_of([
        *(item("vmlu-mqa-dev", "37-1", f"{arm}-r{d}", f"m-{arm}") for d in (1, 2) for arm in ("DSH", "DSHF", "OMPF", "B")),
        *(item("bidlqa-train", "T-1", f"{arm}-r{d}", f"s-{arm}", "reading") for d in (1, 2)
          for arm in ("DSH", "DSHF", "OMPF", "C", "O")),
    ])
    legal = {"LG-1": item(ld.LEGAL_MC, "LG-1", "base", "frozen-mc-prompt")}
    return {"mc112": mc112, "mc113": mc113, "mc114": mc114}, legal


class Folders(unittest.TestCase):
    def test_legal_mc_runs_on_corpus_v1_and_the_rest_on_v2(self):
        self.assertEqual(ld.corpus_of(PROTOCOL, ld.LEGAL_MC), "v1")
        self.assertEqual(ld.corpus_of(PROTOCOL, "bidlqa-train"), "v2")

    def test_a_dataset_under_two_corpora_fails(self):
        protocol = {"corpora": {"v1": {"datasets": ["x"]}, "v2": {"datasets": ["x"]}}}
        with self.assertRaises(SystemExit):
            ld.corpus_of(protocol, "x")


class Manifest(unittest.TestCase):
    def test_copies_only_change_the_replicate_id(self):
        sources, legal = fake_sources()
        with mock.patch.dict(ld.PART_SIZES, {"M": 2, "S": 1}):
            parts = ld.base_items(sources, legal)
        items = ld.expand(parts)
        self.assertEqual(len(items), (2 * 3 + 1 * 3) * 2)
        self.assertEqual({dp.arm_of_replicate(i.replicate_id) for i in items}, {"DSHF", "OMPF", "B", "C"})
        self.assertEqual({i.replicate_id[-2:] for i in items}, {"r3", "r4"})
        by_key = {i.run_key: i for i in items}
        self.assertEqual(by_key[f"{ld.LEGAL_MC}:LG-1:OMPF-r3"].prompt, "DSHF-task")
        self.assertEqual(by_key[f"{ld.LEGAL_MC}:LG-1:B-r4"].prompt, "frozen-mc-prompt")
        self.assertEqual(by_key["vmlu-mqa-dev:37-1:B-r3"].prompt, "m-B")
        self.assertEqual(by_key["bidlqa-train:T-1:C-r4"].prompt, "s-C")
        source = sources["mc114"]["bidlqa-train:T-1:DSHF-r1"]
        self.assertEqual(dataclasses.replace(by_key["bidlqa-train:T-1:DSHF-r3"], replicate_id="DSHF-r1"), source)

    def test_order_is_item_major_draw_then_arm(self):
        sources, legal = fake_sources()
        with mock.patch.dict(ld.PART_SIZES, {"M": 2, "S": 1}):
            items = ld.expand(ld.base_items(sources, legal))
        self.assertEqual([i.replicate_id for i in items[:6]], ["DSHF-r3", "OMPF-r3", "B-r3", "DSHF-r4", "OMPF-r4", "B-r4"])
        self.assertEqual(items[0].dataset_id, ld.LEGAL_MC)
        self.assertEqual(items[-1].dataset_id, "bidlqa-train")

    def test_draws_that_sent_different_tasks_fail(self):
        sources, legal = fake_sources()
        key = "vmlu-mqa-dev:37-1:DSHF-r2"
        sources["mc114"][key] = dataclasses.replace(sources["mc114"][key], prompt="changed")
        with mock.patch.dict(ld.PART_SIZES, {"M": 2, "S": 1}), self.assertRaises(SystemExit):
            ld.base_items(sources, legal)

    def test_omp_task_must_equal_mc112s_dshf_task(self):
        sources, legal = fake_sources()
        for d in (1, 2):
            key = f"{ld.LEGAL_MC}:LG-1:OMPF-r{d}"
            sources["mc113"][key] = dataclasses.replace(sources["mc113"][key], prompt="other")
        with mock.patch.dict(ld.PART_SIZES, {"M": 2, "S": 1}), self.assertRaises(SystemExit):
            ld.base_items(sources, legal)

    def test_wrong_part_size_fails(self):
        sources, legal = fake_sources()
        with self.assertRaises(SystemExit):
            ld.base_items(sources, legal)

    def test_a_drifted_source_manifest_fails(self):
        protocol = {"sources": {"mc112": {"manifest_file_sha256": "x"}}}
        builders = {"mc112": (lambda: ({"a": 1}, {}), lambda: {"a": 2}, ld.la.MANIFEST_PATH)}
        with mock.patch.object(ld, "_sha_checked"), self.assertRaises(SystemExit):
            ld.source_manifests(protocol, builders)


class RealManifest(unittest.TestCase):
    """Offline, on the frozen inputs on disk (needs the earlier cards' data files)."""

    def test_counts_and_folders(self):
        manifest, rebuilt = ld.build_manifest()
        self.assertEqual(manifest["n"], 3876)
        self.assertEqual(manifest["arm_counts"], {"B": 492, "C": 800, "DSHF": 1292, "OMPF": 1292})
        self.assertEqual({len(keys) for keys in manifest["parts"].values()}, {246, 400})
        self.assertEqual(sum(v == "v1" for v in manifest["corpus_of"].values()), 134)
        self.assertEqual(len(rebuilt), 3876)


if __name__ == "__main__":
    unittest.main()
