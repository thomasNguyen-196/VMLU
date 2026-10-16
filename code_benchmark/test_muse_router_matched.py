"""Offline checks for the isolated Muse router condition; run from repo root."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from code_benchmark import run_muse_router_matched as campaign


class TestMuseRouterCondition(unittest.TestCase):
    def test_all_phases_preserve_parent_prompts_and_expected_coverage(self):
        for phase, expected in (("main", 1299), ("vmlu", 10880), ("vbench", 5141)):
            profiles, _protocol, manifest = campaign.inputs_for(phase)
            contract = campaign.v1 if phase == "main" else campaign.v2
            parent = contract.load_manifest(phase)
            parent_rows = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}": r for r in parent['items']}
            self.assertEqual(manifest['n'], expected)
            self.assertEqual(manifest['parent_manifest_sha256'], parent['manifest_sha256'])
            for row in manifest['items']:
                key = f"{row['dataset_id']}:{row['item_id']}:{row['replicate_id']}"
                self.assertEqual(row, parent_rows[key])
            profile = profiles[campaign.PROFILE_ID]
            self.assertFalse(profile['send_seed'])
            self.assertEqual(profile['omp_thinking'], 'auto')

    def test_frozen_inputs_reject_drift(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(campaign, 'OUTPUT_ROOT', Path(tmp)):
            inputs = ({'profile': 1}, {'protocol': 1}, {'manifest': 1})
            campaign.freeze_inputs('main', inputs)
            campaign.freeze_inputs('main', inputs)
            with self.assertRaises(SystemExit):
                campaign.freeze_inputs('main', ({'profile': 2}, inputs[1], inputs[2]))

    def test_sampling_relay_pins_temperature_and_preserves_other_fields(self):
        captured = []

        class Response:
            status = 200
            headers = {'Content-Type': 'application/json'}
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self): return b'{"choices":[]}'
            def read1(self, _size):
                if getattr(self, 'done', False):
                    return b''
                self.done = True
                return self.read()

        def upstream(request, **_kwargs):
            captured.append(json.loads(request.data))
            return Response()

        def fake_omp(**kwargs):
            request = Request(kwargs['endpoint'] + '/chat/completions', data=json.dumps({
                'model': 'cmc/meta/muse-spark-1.2-contributor',
                'messages': [{'role': 'user', 'content': 'frozen prompt'}],
                'max_completion_tokens': 4096, 'reasoning_effort': 'minimal',
            }).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:  # nosec B310 # fixed loopback test server
                self.assertEqual(response.status, 200)
            return {'status': 'complete'}

        with patch.object(campaign.v1_runner, '_resolve_model', return_value=('http://localhost/v1', 'test', 'model', 'test')), patch.object(campaign, 'BASE_RUN_OMP_REQUEST', fake_omp), patch.object(campaign, 'urlopen', upstream), campaign.sampling_relay():
            campaign.v1_runner._run_omp_request(endpoint='http://localhost/v1')
        self.assertEqual(captured[0]['temperature'], 1.0)
        self.assertNotIn('seed', captured[0])
        self.assertNotIn('tools', captured[0])
        self.assertEqual(captured[0]['max_completion_tokens'], 4096)
        self.assertEqual(captured[0]['reasoning_effort'], 'minimal')
        self.assertEqual(captured[0]['messages'][0]['content'], 'frozen prompt')


if __name__ == '__main__':
    unittest.main()
