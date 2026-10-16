"""Offline integration checks for fixed expansion worker parts; run from root."""
from __future__ import annotations

import argparse
import json
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from code_benchmark import run_muse_router_matched as campaign
from code_benchmark import run_vi_multimodel_expansion as runner


class TestFixedExpansionShards(unittest.TestCase):
    def test_balanced_parts_cover_manifest_once_and_resume_keeps_ownership(self):
        parts = runner.fixed_shard_batches(list(range(10880)), 4)
        self.assertEqual([len(part) for part in parts], [2720] * 4)
        self.assertEqual([item for part in parts for item in part], list(range(10880)))
        self.assertEqual(runner.fixed_shard_batches(list(range(7)), 4), [[0, 1], [2, 3], [4, 5], [6]])
        self.assertEqual(runner.fixed_shard_batches([0, 1], 4), [[0], [1], [], []])
        with self.assertRaises(ValueError):
            runner.fixed_shard_batches([0], 0)

    def test_actual_runner_gives_each_thread_its_part_and_resume_skips_completed(self):
        profiles, protocol, full_manifest = campaign.inputs_for('vmlu')
        manifest = dict(full_manifest)
        manifest['items'] = full_manifest['items'][:8]
        manifest['n'] = 8
        rebuilt = campaign.v2.rebuild_items('vmlu')
        items = [campaign.v2.item_from_manifest_row(row, rebuilt) for row in manifest['items']]
        calls = []
        call_lock = threading.Lock()

        def fake_request(**kwargs):
            if not kwargs['request_key'].startswith('probe:'):
                with call_lock:
                    calls.append((kwargs['prompt'], threading.current_thread().name))
            return {
                'status': 'complete', 'error_type': '', 'error_detail': '', 'raw_response': 'A',
                'response_model_id': 'test-model', 'request_id': '', 'finish_reason': 'stop',
                'prompt_tokens': 1, 'cached_prompt_tokens': 0, 'completion_tokens': 1, 'total_tokens': 2,
                'reasoning_tokens': None, 'latency_s': 0.01, 'tool_calls': 0, 'session_id': 'test',
            }

        args = argparse.Namespace(execute=True, resume=False, fixed_shards=True, max_cost_usd=1.0, omp_bin='omp')
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            for name, value in {
                'OUTPUT_DIR': Path(tmp), 'load_profiles': lambda: profiles, '_read_protocol': lambda: protocol,
                'load_manifest': lambda _phase: manifest, 'rebuild_items': lambda _phase: rebuilt,
                '_acquire_run_lock': lambda _path: None,
                '_resolve_model': lambda _profile: ('http://localhost/v1', 'test', 'test-model', 'test'),
                '_run_omp_request': fake_request,
            }.items():
                stack.enter_context(patch.object(runner, name, value))
            stack.enter_context(patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='omp/18.0.0', stderr='')))
            runner.run_phase(phase='vmlu', profile_id=campaign.PROFILE_ID, args=args)
            self.assertEqual(len(calls), 8)
            ownership = {item.prompt: f'shard-{index + 1}_0' for index, part in enumerate(runner.fixed_shard_batches(items, 4)) for item in part}
            self.assertTrue(all(thread == ownership[prompt] for prompt, thread in calls))
            output = Path(tmp) / 'vmlu' / campaign.PROFILE_ID
            meta = json.loads((output / 'run.json').read_text())
            self.assertEqual([part['complete'] for part in meta['shards']], [2] * 4)
            rows = [json.loads(line) for line in (output / 'predictions.jsonl').read_text().splitlines()]
            self.assertEqual(len({row['run_key'] for row in rows}), 8)
            self.assertEqual(sorted(row['worker_shard'] for row in rows), [1, 1, 2, 2, 3, 3, 4, 4])
            args.resume = True
            runner.run_phase(phase='vmlu', profile_id=campaign.PROFILE_ID, args=args)
            self.assertEqual(len(calls), 8)
            args.fixed_shards = False
            with self.assertRaises(SystemExit):
                runner.run_phase(phase='vmlu', profile_id=campaign.PROFILE_ID, args=args)


if __name__ == '__main__':
    unittest.main()
