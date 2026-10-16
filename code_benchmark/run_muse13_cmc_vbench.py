"""Continue paused MC-76 V-Bench coverage via the explicitly requested CMC route.

Preserve completed Free-route answers; keep remaining requests as a separate
condition. From root: python -m code_benchmark.run_muse13_cmc_vbench --execute
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from collections import Counter
from pathlib import Path

try:
    from code_benchmark import run_muse_router_matched as campaign
except ImportError:
    import run_muse_router_matched as campaign

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "muse-spark-1-3-contributor-cmc"
CARD_ID = "MC-77"
CARD_PATH = ROOT / 'docs/measurement_cards/MC-77-muse13-cmc-vbench-continuation.md'
OUTPUT_ROOT = ROOT / 'all_res/muse13_cmc_vbench_mc77'
SOURCE_ROOT = ROOT / 'all_res/muse13_free_vbench_mc76'
SOURCE_RUN = SOURCE_ROOT / 'vbench/muse-spark-1-3-contributor-free'
BASE_PROFILE = campaign.router_profile
WORKERS = 2
ADDITIONAL_SOURCES = []


def source_runs() -> list[tuple]:
    return [(SOURCE_ROOT, SOURCE_RUN, 'MC-76', 'oc/muse-spark-1.3-contributor-free'), *ADDITIONAL_SOURCES]


def completed_sources() -> tuple[dict, dict]:
    completed, hashes = {}, {}
    for _root, run, card, route in source_runs():
        ledger = run / 'attempts.jsonl'
        latest = {}
        for line in ledger.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                latest[row['run_key']] = row
        hashes[card] = campaign.v1.sha256_bytes(ledger.read_bytes())
        for key, row in latest.items():
            if row['status'] == 'complete':
                if key in completed:
                    raise SystemExit(f'Error: overlapping completed source item {key}')
                completed[key] = {**row, 'source_condition_id': card, 'source_route': route}
    return completed, hashes


def profile() -> dict:
    result = BASE_PROFILE()
    result.update({
        'profile_id': PROFILE_ID, 'display_name': 'Muse Spark 1.3 Contributor (CMC continuation)',
        'provider': '9ROUTER / CMC', 'model_id': 'cmc/meta/muse-spark-1.3-contributor',
        'model_ref': 'router9/cmc/meta/muse-spark-1.3-contributor',
        'measurement_card_ids_v2': {'vbench': CARD_ID},
    })
    return result


def inputs() -> tuple[dict, dict, dict]:
    campaign.PROFILE_ID = PROFILE_ID
    campaign.OUTPUT_ROOT = OUTPUT_ROOT
    campaign.CARDS = {**campaign.CARDS, 'vbench': CARD_ID}
    campaign.router_profile = profile
    profiles, protocol, manifest = campaign.inputs_for('vbench')
    complete, source_hashes = completed_sources()
    references = {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}": r for r in manifest['items']}
    if set(complete) - set(references):
        raise SystemExit('Error: source results outside frozen V-Bench manifest')
    for key, row in complete.items():
        if row['prompt_sha256'] != references[key]['prompt_sha256']:
            raise SystemExit(f'Error: source prompt mismatch: {key}')
    manifest['items'] = [r for k, r in references.items() if k not in complete]
    manifest['n'] = manifest['item_count'] = len(manifest['items'])
    manifest['dataset_counts'] = dict(Counter(r['dataset_id'] for r in manifest['items']))
    manifest['carried_completed_keys'] = sorted(complete)
    manifest['source_attempts_sha256'] = source_hashes['MC-76']
    if ADDITIONAL_SOURCES:
        manifest['source_attempts_hashes'] = source_hashes
        manifest['carried_counts_by_condition'] = dict(Counter(r['source_condition_id'] for r in complete.values()))
    manifest['source_condition_id'] = 'MC-76'
    manifest['execution_workers'] = WORKERS
    manifest['scheduling_policy'] = 'fixed-shards'
    manifest.pop('manifest_sha256')
    manifest['manifest_sha256'] = campaign.v1.sha256_bytes(campaign.v1.canonical_json(manifest))
    protocol['workers_per_profile'] = WORKERS
    return profiles, protocol, manifest


def combine_results(manifest: dict) -> None:
    """An explicit mixed-route artifact; never label it a homogeneous model run."""
    latest, _hashes = completed_sources()
    for line in (OUTPUT_ROOT / 'vbench' / PROFILE_ID / 'predictions.jsonl').read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            if row['run_key'] in latest or row['status'] != 'complete':
                raise SystemExit('Error: overlapping or incomplete continuation output')
            latest[row['run_key']] = {**row, 'source_condition_id': CARD_ID, 'source_route': 'cmc/meta/muse-spark-1.3-contributor'}
    expected = set(manifest['carried_completed_keys']) | {f"{r['dataset_id']}:{r['item_id']}:{r['replicate_id']}" for r in manifest['items']}
    if set(latest) != expected or len(latest) != 5141:
        raise SystemExit('Error: combined V-Bench coverage differs from 5141 unique items')
    campaign.v1.write_jsonl_atomic(OUTPUT_ROOT / 'combined_predictions_mixed_routes.jsonl', [latest[k] for k in sorted(latest)])
    campaign.v1_runner._atomic_json(OUTPUT_ROOT / 'combined_provenance.json', {
        'mixed_routes': True, 'item_count': 5141,
        'counts_by_route': dict(Counter(row['source_route'] for row in latest.values())),
        'counts_by_condition': dict(Counter(row['source_condition_id'] for row in latest.values())),
        'note': 'Completed source results retained; continuation requests only remaining items. Mixed routes and scheduling conditions are explicit; correctness requires server grading.',
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.resume and not args.execute:
        parser.error('--resume requires --execute')
    os.chdir(ROOT)
    condition = inputs()
    manifest = condition[2]
    print(f"condition={CARD_ID} preserved={len(manifest['carried_completed_keys'])} remaining={manifest['n']} workers={WORKERS} tools=none temperature=1.0 thinking=auto seed=omitted", flush=True)
    print(f"manifest_sha256={manifest['manifest_sha256']}", flush=True)
    base = ['--phase', 'vbench', '--profile', PROFILE_ID]
    run_args = [*base, '--max-cost-usd', '1', '--fixed-shards', '--measurement-card', str(CARD_PATH)]
    if not args.execute:
        campaign.invoke(campaign.v2_runner, 'vbench', run_args, condition)
        return
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    from contextlib import ExitStack
    with ExitStack() as stack:
        try:
            for root, _run, _card, _route in source_runs():
                source_lock = stack.enter_context((root / '.campaign.lock').open('a+'))
                fcntl.flock(source_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock = stack.enter_context((OUTPUT_ROOT / '.campaign.lock').open('a+'))
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit('Error: source or continuation V-Bench campaign already active') from exc
        campaign.freeze_inputs('vbench', condition)
        run_args.append('--execute')
        if args.resume:
            run_args.append('--resume')
        with campaign.sampling_relay():
            campaign.invoke(campaign.v2_runner, 'vbench', run_args, condition)
        campaign.invoke(campaign.v2_scorer, 'vbench', base, condition)
        combine_results(manifest)


if __name__ == '__main__':
    main()
