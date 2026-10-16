"""Offline coverage and condition checks for MC-76; run from repo root."""
from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from code_benchmark import run_muse13_free_vbench as new


class TestMuse13FreeVBench(unittest.TestCase):
    def test_exact_model_and_two_fixed_parts_preserve_parent_rows(self):
        c = new.campaign
        parent = c.v2.load_manifest('vbench')
        with ExitStack() as stack:
            for name in ('PROFILE_ID', 'OUTPUT_ROOT', 'CARDS', 'router_profile'):
                stack.enter_context(patch.object(c, name, getattr(c, name)))
            profiles, protocol, manifest = new.inputs()
            profile = profiles[new.PROFILE_ID]
            self.assertEqual(profile['model_id'], 'oc/muse-spark-1.3-contributor-free')
            self.assertEqual(profile['measurement_card_ids_v2']['vbench'], 'MC-76')
            self.assertEqual(profile['temperature'], 1.0)
            self.assertFalse(profile['send_seed'])
            self.assertEqual(profile['omp_thinking'], 'auto')
            self.assertEqual(protocol['workers_per_profile'], 2)
            self.assertEqual(manifest['items'], parent['items'])
            self.assertEqual(manifest['n'], 5141)
            self.assertEqual(manifest['scheduling_policy'], 'fixed-shards')
            parts = c.v2_runner.fixed_shard_batches(manifest['items'], 2)
            self.assertEqual([len(part) for part in parts], [2571, 2570])
            self.assertEqual([row for part in parts for row in part], parent['items'])


if __name__ == '__main__':
    unittest.main()
