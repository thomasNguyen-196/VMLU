"""Offline checks for route-switch coverage and truthful result provenance."""
from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from code_benchmark import run_muse13_cmc_vbench as continuation


class TestVBenchContinuation(unittest.TestCase):
    def test_four_worker_continuation_preserves_both_completed_sources(self):
        from code_benchmark import run_muse13_cmc_vbench_four_workers as four
        c = continuation.campaign
        with ExitStack() as stack:
            for name in ('PROFILE_ID', 'CARD_ID', 'CARD_PATH', 'OUTPUT_ROOT', 'WORKERS', 'ADDITIONAL_SOURCES'):
                stack.enter_context(patch.object(continuation, name, getattr(continuation, name)))
            for name in ('PROFILE_ID', 'OUTPUT_ROOT', 'CARDS', 'router_profile'):
                stack.enter_context(patch.object(c, name, getattr(c, name)))
            four.configure()
            profiles, protocol, manifest = continuation.inputs()
            self.assertEqual(protocol['workers_per_profile'], 4)
            self.assertEqual(profiles[continuation.PROFILE_ID]['model_id'], 'cmc/meta/muse-spark-1.3-contributor')
            complete, _hashes = continuation.completed_sources()
            self.assertEqual(set(manifest['carried_completed_keys']), set(complete))
            self.assertEqual(set(manifest['carried_counts_by_condition']), {'MC-76', 'MC-77'})
            remaining = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}" for r in manifest['items']}
            self.assertFalse(set(complete) & remaining)
            self.assertEqual(len(set(complete) | remaining), 5141)
            parts = c.v2_runner.fixed_shard_batches(manifest['items'], 4)
            sizes = [len(part) for part in parts]
            self.assertLessEqual(max(sizes) - min(sizes), 1)
            self.assertEqual([row for part in parts for row in part], manifest['items'])

    def test_remaining_scope_excludes_all_completed_answers_and_retains_failed_requests(self):
        c = continuation.campaign
        with ExitStack() as stack:
            for name in ('PROFILE_ID', 'OUTPUT_ROOT', 'CARDS', 'router_profile'):
                stack.enter_context(patch.object(c, name, getattr(c, name)))
            profiles, protocol, manifest = continuation.inputs()
            self.assertEqual(profiles[continuation.PROFILE_ID]['model_id'], 'cmc/meta/muse-spark-1.3-contributor')
            self.assertEqual(protocol['workers_per_profile'], 2)
            carried = set(manifest['carried_completed_keys'])
            remaining = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}" for r in manifest['items']}
            self.assertFalse(carried & remaining)
            self.assertEqual(len(carried | remaining), 5141)
            latest = {}
            for line in (continuation.SOURCE_RUN / 'attempts.jsonl').read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    latest[r['run_key']] = r
            self.assertEqual(carried, {k for k, r in latest.items() if r['status'] == 'complete'})
            self.assertTrue(all(k in remaining for k, r in latest.items() if r['status'] == 'request_error'))
            self.assertTrue(all(k in carried for k, r in latest.items() if r['status'] == 'complete' and not r['raw_response']))
            with tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp)
                run = destination / 'vbench' / continuation.PROFILE_ID
                run.mkdir(parents=True)
                fake_rows = [{'run_key': k, 'status': 'complete', 'raw_response': 'A'} for k in remaining]
                c.v1.write_jsonl_atomic(run / 'predictions.jsonl', fake_rows)
                with patch.object(continuation, 'OUTPUT_ROOT', destination):
                    continuation.combine_results(manifest)
                result = [json.loads(line) for line in (destination / 'combined_predictions_mixed_routes.jsonl').read_text().splitlines()]
                self.assertEqual(len(result), 5141)
                self.assertEqual(len({r['run_key'] for r in result}), 5141)
                provenance = json.loads((destination / 'combined_provenance.json').read_text())
                self.assertTrue(provenance['mixed_routes'])
                self.assertEqual(provenance['counts_by_route']['oc/muse-spark-1.3-contributor-free'], len(carried))
                for row in result:
                    if row['run_key'] in carried:
                        self.assertEqual(row['raw_response'], latest[row['run_key']]['raw_response'])
                        self.assertEqual(row['source_condition_id'], 'MC-76')


if __name__ == '__main__':
    unittest.main()
