"""Run the frozen Vietnamese multi-model pilot through omp.

One isolated omp process handles each manifest item. All conditions use the
same byte-frozen user prompt, minimal system prompt, no tools and no session
history. Provider settings and the OpenCode Go quota-equivalent cap are recorded
per profile. Run from repo root.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess  # nosec B404 — local OMP runner, argv lists only; never invokes a shell
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

try:
    from code_benchmark.run_harness_eval import MINIMAL_SYSTEM_PROMPT, build_argv, parse_transcript
    from code_benchmark.score_reading_eval import measurement_card_hash
    from code_benchmark.vi_multimodel import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        canonical_json,
        item_from_manifest_row,
        load_manifest,
        load_model_profiles,
        load_protocol,
        rebuild_items,
        sha256_bytes,
        write_jsonl_atomic,
    )
except ImportError:
    from run_harness_eval import MINIMAL_SYSTEM_PROMPT, build_argv, parse_transcript
    from score_reading_eval import measurement_card_hash
    from vi_multimodel import (
        OUTPUT_DIR,
        PROTOCOL_ID,
        canonical_json,
        item_from_manifest_row,
        load_manifest,
        load_model_profiles,
        load_protocol,
        rebuild_items,
        sha256_bytes,
        write_jsonl_atomic,
    )

load_dotenv()

_OMP_GO_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
_OMP_ROLES = ("default", "smol", "slow", "plan", "task", "tiny", "commit", "advisor", "designer", "vision")
_GO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://opencode.ai/",
    "Origin": "https://opencode.ai",
}
_PROBE_MAX_TOKENS = 16


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(canonical_json(value) + b"\n")
    tmp.replace(path)


def _price(profile: dict, field: str) -> float:
    value = profile.get(field)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise SystemExit(f"Error: missing or invalid {field} for {profile['profile_id']}")
    return float(value)


def _request_bound_usd(prompt: str, max_tokens: int, input_rate: float, output_rate: float) -> float:
    # Byte fallback bounds text tokens; 256 tokens reserve wrapper/system framing.
    input_bound = len(prompt.encode("utf-8")) + 256
    return (input_bound * input_rate + max_tokens * output_rate) / 1_000_000


def _resolve_credentials(profile: dict) -> tuple[str, str]:
    key_env = str(profile.get("api_key_env", ""))
    key = os.getenv(key_env) if key_env else None
    if key:
        return key, f"environment:{key_env}"
    auth_provider = str(profile.get("auth_provider", ""))
    if auth_provider and _OMP_GO_AUTH.is_file():
        try:
            auth_data = json.loads(_OMP_GO_AUTH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Error: cannot read OpenCode credential metadata: {type(exc).__name__}") from exc
        entry = auth_data.get(auth_provider, {})
        key = str(entry.get("key", "")) if isinstance(entry, dict) else ""
        if key:
            return key, f"opencode-auth:{auth_provider}"
    raise SystemExit(
        f"Error: credential missing; set {key_env} or authenticate provider {auth_provider or '(none)'}"
    )


def _resolved_endpoint(profile: dict) -> str:
    env_name = str(profile.get("base_url_env", ""))
    endpoint = (os.getenv(env_name) if env_name else None) or profile.get("base_url") or ""
    endpoint = str(endpoint).strip().rstrip("/")
    if not endpoint.startswith(("https://", "http://")):
        raise SystemExit(f"Error: invalid endpoint for {profile['profile_id']}")
    return endpoint


def _run_key_for(item, protocol: dict, phase: str, profile: dict) -> str:
    payload = f"{protocol['protocol_id']}:{phase}:{profile['profile_id']}:{item.run_key}"
    return sha256_bytes(payload.encode("utf-8"))[:32]


def _write_agent_config(
    agent_dir: Path,
    *,
    profile: dict,
    model_id: str,
    endpoint: str,
    max_tokens: int,
    session_id: str,
) -> None:
    provider_name = str(profile.get("omp_provider") or profile["model_ref"].split("/", 1)[0])
    api_protocol = str(profile.get("api_protocol", "openai-completions"))
    if api_protocol not in {"openai-completions", "openai-responses"}:
        raise SystemExit(f"Error: unsupported omp API protocol {api_protocol!r}")
    headers = (
        dict(profile.get("omp_request_headers") or _GO_HEADERS)
        if profile.get("billing_mode") == "opencode-go-subscription"
        else {}
    )
    if headers:
        headers["x-opencode-session"] = session_id
    model: dict = {
        "id": model_id,
        "name": profile["display_name"],
        "reasoning": bool(profile.get("omp_reasoning", True)),
        "input": ["text"],
        "contextWindow": int(profile.get("context_window", 1_048_576)),
        "maxTokens": max_tokens,
    }
    if headers:
        model["headers"] = headers
    options = profile.get("omp_options") or {}
    if options:
        model["options"] = options
    models = {
        "providers": {
            provider_name: {
                "baseUrl": endpoint,
                "apiKey": profile["api_key_env"],
                "api": api_protocol,
                "authHeader": True,
                "disableStrictTools": True,
                "models": [model],
            }
        }
    }
    roles = {role: profile["model_ref"] for role in _OMP_ROLES}
    config = {"modelRoles": roles, "memory": {"backend": "off"}, "setupVersion": 2}
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.yml").write_text(json.dumps(models, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (agent_dir / "config.yml").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (agent_dir / "APPEND_SYSTEM.md").write_text("", encoding="utf-8")


def _reasoning_tokens(events: list[dict]) -> int | None:
    found = []
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage") or {}
        for name in ("reasoning", "reasoningTokens", "reasoning_tokens"):
            value = usage.get(name)
            if isinstance(value, int):
                found.append(value)
                break
    return sum(found) if found else None


def _event_error_detail(events: list[dict]) -> str:
    for event in events:
        message = event.get("message")
        if isinstance(message, dict):
            detail = message.get("errorMessage") or message.get("errorStatus") or message.get("errorId")
            if detail:
                return str(detail)
        if event.get("type") not in {"error", "turn_error", "response.failed"}:
            continue
        error = event.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or error.get("code") or ""
        else:
            detail = error or event.get("message") or ""
        if detail:
            return str(detail)
    return ""


def _run_omp_request(
    *,
    omp_bin: str,
    profile: dict,
    model_id: str,
    endpoint: str,
    prompt: str,
    request_key: str,
    max_tokens: int,
    max_time: int,
    thinking: str,
    tmp_root: Path,
    fake_home: Path,
    api_key: str,
) -> dict:
    session_id = sha256_bytes(request_key.encode("utf-8"))[:32]
    agent_dir = Path(tempfile.mkdtemp(prefix="agent-", dir=tmp_root))
    scratch = Path(tempfile.mkdtemp(prefix="item-", dir=tmp_root))
    _write_agent_config(
        agent_dir, profile=profile, model_id=model_id, endpoint=endpoint,
        max_tokens=max_tokens, session_id=session_id,
    )
    argv = build_argv(
        omp_bin=omp_bin,
        model=profile["model_ref"],
        prompt=prompt,
        workdir=scratch,
        tools="none",
        max_time=max_time,
        thinking=thinking,
        system_prompt=MINIMAL_SYSTEM_PROMPT,
    )
    env = {
        **os.environ,
        str(profile["api_key_env"]): api_key,
        "HOME": str(fake_home),
        "PI_CODING_AGENT_DIR": str(agent_dir.resolve()),
    }
    started = time.perf_counter()
    try:
        try:
            proc = subprocess.run(  # nosec B603 — build_argv constructs fixed flags, shell=False, isolated cwd
                argv, capture_output=True, text=True, timeout=max_time + 60,
                env=env, cwd=scratch, check=False,
            )
            stdout = proc.stdout
            stderr = proc.stderr or ""
            exit_code = proc.returncode
            error_type = "" if exit_code == 0 else f"omp_exit_{exit_code}"
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = "omp hard timeout"
            exit_code = -9
            error_type = "timeout"
        events, response_text, stats = parse_transcript(stdout.splitlines())
        protocol_violation = int(stats["tool_calls"]) > 0
        turn_error = str(stats.get("stop_reason", "")).lower() in {"error", "failed", "aborted"}
        event_error = _event_error_detail(events)
        if protocol_violation:
            error_type = "tools_invoked_despite_no_tools"
        if turn_error and not error_type:
            error_type = "omp_turn_error"
        status = "complete" if exit_code == 0 and not protocol_violation and not turn_error else "request_error"
        prompt_tokens = int(stats["input_tokens"]) + int(stats["cache_read_tokens"])
        assistant_messages = [
            event.get("message", {}) for event in events
            if event.get("type") == "message_end"
            and event.get("message", {}).get("role") == "assistant"
        ]
        response_message = assistant_messages[-1] if assistant_messages else {}
        error_detail = event_error or stderr.strip()
        if api_key:
            error_detail = error_detail.replace(api_key, "[REDACTED]")
        return {
            "status": status,
            "error_type": error_type,
            "error_detail": error_detail[-800:] if status != "complete" else "",
            "raw_response": response_text,
            "response_model_id": str(response_message.get("model") or model_id),
            "request_id": str(response_message.get("id") or ""),
            "finish_reason": str(stats.get("stop_reason") or ""),
            "prompt_tokens": prompt_tokens,
            "cached_prompt_tokens": int(stats["cache_read_tokens"]),
            "completion_tokens": int(stats["output_tokens"]),
            "total_tokens": prompt_tokens + int(stats["output_tokens"]),
            "reasoning_tokens": _reasoning_tokens(events),
            "latency_s": round(time.perf_counter() - started, 4),
            "tool_calls": int(stats["tool_calls"]),
            "session_id": session_id,
            "exit_code": exit_code,
        }
    finally:
        shutil.rmtree(agent_dir, ignore_errors=True)
        shutil.rmtree(scratch, ignore_errors=True)


def _read_checkpoint(
    path: Path,
    *,
    config_hash: str,
    resume: bool,
    expected_keys: set[str],
    config: dict | None = None,
):
    meta_path = path / "run.json"
    predictions_path = path / "predictions.jsonl"
    if not path.exists():
        return {}, {}, []
    if not resume:
        raise SystemExit(f"Error: run directory already exists: {path}; pass --resume")
    if not meta_path.is_file():
        raise SystemExit(f"Error: cannot resume without {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("config_sha256") != config_hash:
        budget_fields = {"worst_case_usage_usd_equivalent", "max_cost_usd"}
        budget_only_change = (
            config is not None
            and meta.get("status") in {"probe_failed", "running"}
            and isinstance(meta.get("max_cost_usd"), (int, float))
            and isinstance(config.get("max_cost_usd"), (int, float))
            and config["max_cost_usd"] >= meta["max_cost_usd"]
            and any(meta.get(key) != config.get(key) for key in budget_fields)
            and all(meta.get(key) == value for key, value in config.items()
                    if key not in budget_fields)
        )
        if not budget_only_change:
            raise SystemExit(f"Error: settings changed since {path}; start a new run")
        for key in budget_fields:
            if meta.get(key) != config.get(key):
                meta[f"previous_{key}"] = meta.get(key)
        meta.update(config)
        meta["previous_config_sha256"] = meta.get("config_sha256")
        meta["config_sha256"] = config_hash
        meta["config_migration"] = "budget reserve/cap updated after zero-token transport failures; item settings unchanged"
        _atomic_json(meta_path, meta)
    rows = [
        json.loads(line) for line in predictions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if predictions_path.exists() else []
    keys = [str(row.get("run_key", "")) for row in rows]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise SystemExit(f"Error: blank or duplicate run key in {predictions_path}")
    unknown = sorted(set(keys) - expected_keys)
    if unknown:
        raise SystemExit(f"Error: checkpoint keys outside frozen manifest: {unknown[:5]}")
    if any(row.get("status") not in {"complete", "request_error"} for row in rows):
        raise SystemExit(f"Error: invalid checkpoint status in {predictions_path}")
    completed = {str(row["run_key"]): row for row in rows if row.get("status") == "complete"}
    return completed, meta, rows


def _resolve_model(profile: dict) -> tuple[str, str, str, str]:
    endpoint = str((os.getenv(str(profile.get("base_url_env", ""))) if profile.get("base_url_env") else None)
                   or profile.get("base_url", "")).strip().rstrip("/")
    if not endpoint.startswith(("http://", "https://")):
        raise SystemExit(f"Error: invalid endpoint for {profile['profile_id']}")
    api_key_env = str(profile["api_key_env"])
    api_key = os.getenv(api_key_env)
    credential_source = f"environment:{api_key_env}" if api_key else ""
    if not api_key and profile.get("auth_provider"):
        auth_file = Path.home() / ".local" / "share" / "opencode" / "auth.json"
        try:
            auth_data = json.loads(auth_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Error: OpenCode Go credential unavailable ({type(exc).__name__})") from exc
        entry = auth_data.get(str(profile["auth_provider"]), {})
        api_key = str(entry.get("key", "")) if isinstance(entry, dict) else ""
        if api_key:
            credential_source = f"opencode-auth:{profile['auth_provider']}"
    if not api_key:
        raise SystemExit(f"Error: credential missing; set {api_key_env}")
    request_model = (os.getenv(str(profile.get("model_id_env", "")))
                     if profile.get("model_id_env") else None) or str(profile["model_id"])
    if profile.get("model_ref"):
        provider = str(profile.get("omp_provider") or profile["model_ref"].split("/", 1)[0])
    else:
        provider = str(profile.get("omp_provider", ""))
    model_ref = f"{provider}/{request_model}"
    return endpoint, api_key, request_model, credential_source or model_ref


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one frozen Vietnamese multi-model phase through omp.")
    parser.add_argument("--phase", choices=("pilot", "pilot_omp", "main"), required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--omp-bin", default="omp")
    parser.add_argument("--execute", action="store_true", help="send omp requests; otherwise preflight only")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-cost-usd", type=float,
                        help="maximum per-run USD or OpenCode Go quota-equivalent; required with --execute")
    args = parser.parse_args()

    profiles = load_model_profiles()
    profile = profiles.get(args.profile)
    if profile is None:
        parser.error(f"unknown profile: {args.profile}")
    protocol = load_protocol()
    if protocol.get("execution_transport") != "omp":
        raise SystemExit("Error: protocol transport is not frozen to omp")
    if int(protocol.get("max_retries", -1)) != 0:
        raise SystemExit("Error: protocol v1 requires zero SDK retries")
    expected_card = protocol[args.phase].get("measurement_card_ids", {}).get(args.profile)
    if profile.get("measurement_card_ids", {}).get(args.phase) != expected_card:
        raise SystemExit(f"Error: measurement card mismatch for {args.profile}/{args.phase}")
    manifest = load_manifest(args.phase)
    rebuilt = rebuild_items(args.phase)
    items = [item_from_manifest_row(row, rebuilt) for row in manifest["items"]]
    mc_cap, reading_cap = _phase_caps(protocol, args.phase)
    workers = int(protocol.get("workers", 0))
    if not 1 <= workers <= 4:
        raise SystemExit("Error: protocol workers must be between 1 and 4")
    input_rate = _price(profile, "input_price_usd_per_million")
    output_rate = _price(profile, "output_price_usd_per_million")
    cached_rate = _price(profile, "cached_input_price_usd_per_million")
    bounds = {
        item.run_key: _request_bound_usd(
            item.prompt,
            mc_cap if item.task == "multiple_choice" else reading_cap,
            input_rate,
            output_rate,
        )
        for item in items
    }
    estimate = sum(bounds.values()) + _request_bound_usd("ping", _PROBE_MAX_TOKENS, input_rate, output_rate)
    print(f"worst_case_usage_usd_equivalent={estimate:.6f}")
    print(
        f"protocol={PROTOCOL_ID} phase={args.phase} profile={args.profile} "
        f"transport=omp items={len(items)} workers={workers} mc_cap={mc_cap} reading_cap={reading_cap}"
    )
    if not args.execute:
        print("preflight only; no model endpoint was called")
        return
    if args.max_cost_usd is None or args.max_cost_usd <= 0 or not math.isfinite(args.max_cost_usd):
        parser.error("--execute requires a positive finite --max-cost-usd")
    if estimate > args.max_cost_usd:
        parser.error(
            f"worst-case usage equivalent {estimate:.6f} USD exceeds cap {args.max_cost_usd:.6f} USD"
        )
    endpoint, api_key, request_model, credential_source = _resolve_model(profile)
    card_id = profile.get("measurement_card_ids", {}).get(args.phase)
    card_path = Path("measurement_card.md")
    if not card_id or not card_path.is_file() or f"| `{card_id}` |" not in card_path.read_text(encoding="utf-8"):
        raise SystemExit(f"Error: preregister measurement card for {args.profile}/{args.phase} before model calls")
    card_hash = measurement_card_hash(card_path)
    version_result = subprocess.run([args.omp_bin, "--version"], capture_output=True, text=True, timeout=15, check=False)  # nosec B603 — operator-selected OMP executable, fixed version flag, no shell
    if version_result.returncode != 0:
        raise SystemExit(f"Error: cannot launch omp ({version_result.returncode})")
    omp_version = (version_result.stdout or version_result.stderr).strip()
    max_time = int(protocol.get("omp_max_time_seconds", 300))
    omp_thinking = str(profile.get("omp_thinking", "auto"))
    output_dir = OUTPUT_DIR / args.phase / args.profile
    config = {
        "protocol_id": PROTOCOL_ID,
        "phase": args.phase,
        "profile_id": args.profile,
        "model_id": profile["model_id"],
        "request_model_id": request_model,
        "model_ref": profile["model_ref"],
        "provider": profile["provider"],
        "provider_tier": profile.get("provider_tier", ""),
        "billing_mode": profile.get("billing_mode", ""),
        "monthly_usage_limit_usd": profile.get("monthly_usage_limit_usd"),
        "credential_source": credential_source,
        "endpoint_host": re.sub(r"^https?://", "", endpoint).split("/", 1)[0],
        "transport": "omp",
        "omp_version": omp_version,
        "omp_mode": protocol["omp_mode"],
        "omp_system_prompt": protocol["omp_system_prompt"],
        "omp_tools": protocol["omp_tools"],
        "omp_max_time_seconds": max_time,
        "measurement_card_id": card_id,
        "measurement_card_hash": card_hash,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": manifest["protocol_sha256"],
        "profile_roster_sha256": manifest["profile_roster_sha256"],
        "temperature_requested": profile.get("temperature", protocol["temperature"]),
        "temperature_effective": profile.get("temperature_effective", profile.get("temperature", protocol["temperature"])),
        "temperature_policy": profile.get("temperature_policy", "profile/model config"),
        "seed_requested": int(protocol["seed"]),
        "seed_sent": bool(profile.get("send_seed", True)),
        "seed_policy": profile.get("seed_policy", "provider/model config"),
        "token_limit_parameter": profile.get("token_limit_parameter", "maxTokens in omp model config"),
        "max_tokens_mc": mc_cap,
        "max_tokens_reading": reading_cap,
        "reasoning_policy": protocol["reasoning_policy"],
        "omp_reasoning": bool(profile.get("omp_reasoning", True)),
        "omp_thinking": omp_thinking,
        "workers": workers,
        "max_retries": int(protocol["max_retries"]),
        "input_price_usd_per_million": input_rate,
        "cached_input_price_usd_per_million": cached_rate,
        "output_price_usd_per_million": output_rate,
        "max_cost_usd": args.max_cost_usd,
        "worst_case_usage_usd_equivalent": estimate,
    }
    config_hash = sha256_bytes(canonical_json(config))
    expected_keys = {item.run_key for item in items}
    completed, old_meta, previous_rows = _read_checkpoint(
        output_dir, config_hash=config_hash, resume=args.resume, expected_keys=expected_keys, config=config,
    )
    remaining = [item for item in items if item.run_key not in completed]
    previous_reserve = sum(float(row.get("reserved_cost_usd", 0.0)) for row in previous_rows)
    probe_reserve = float(old_meta.get("probe_reserved_cost_usd", 0.0))
    one_probe_reserve = _request_bound_usd("ping", _PROBE_MAX_TOKENS, input_rate, output_rate)
    remaining_reserve = sum(bounds[item.run_key] for item in remaining)
    next_probe_reserve = 0.0 if old_meta.get("probe_completed") else one_probe_reserve
    if previous_reserve + probe_reserve + remaining_reserve + next_probe_reserve > args.max_cost_usd:
        parser.error("resume would exceed the cumulative usage-equivalent cap")

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f"vmlu-omp-{args.phase}-{args.profile}-"))
    fake_home = temp_root / "home"
    fake_home.mkdir()
    scratch_root = temp_root / "scratch"
    scratch_root.mkdir()
    agent_root = temp_root / "agents"
    agent_root.mkdir()
    lock = threading.Lock()
    rows_by_key = {str(row["run_key"]): row for row in previous_rows}
    try:
        if not old_meta.get("probe_completed"):
            old_meta = {
                **old_meta,
                **config,
                "config_sha256": config_hash,
                "started_at": old_meta.get("started_at") or datetime.now(timezone.utc).isoformat(),
                "probe_attempt_count": int(old_meta.get("probe_attempt_count", 0)) + 1,
                "probe_max_tokens": _PROBE_MAX_TOKENS,
                "probe_reserved_cost_usd": probe_reserve + next_probe_reserve,
                "status": "probe_pending",
            }
            _atomic_json(output_dir / "run.json", old_meta)
            probe = _run_omp_request(
                omp_bin=args.omp_bin,
                profile=profile,
                model_id=request_model,
                endpoint=endpoint,
                prompt="ping",
                request_key=f"probe:{PROTOCOL_ID}:{args.phase}:{args.profile}",
                max_tokens=_PROBE_MAX_TOKENS,
                max_time=max_time,
                thinking=omp_thinking,
                tmp_root=agent_root,
                fake_home=fake_home,
                api_key=api_key,
            )
            if probe["status"] != "complete":
                old_meta.update({
                    "probe_completed": False,
                    "probe_error_type": probe["error_type"],
                    "probe_error_detail": probe["error_detail"],
                    "status": "probe_failed",
                })
                _atomic_json(output_dir / "run.json", old_meta)
                raise SystemExit(
                    f"Error: omp provider probe failed ({probe['error_type']}): {probe['error_detail']}"
                )
            old_meta.update({
                "probe_completed": True,
                "probe_response_model_id": probe["response_model_id"],
                "probe_request_id": probe["request_id"],
                "probe_prompt_tokens": probe["prompt_tokens"],
                "probe_cached_prompt_tokens": probe["cached_prompt_tokens"],
                "probe_completion_tokens": probe["completion_tokens"],
                "probe_total_tokens": probe["total_tokens"],
                "probe_reasoning_tokens": probe["reasoning_tokens"],
                "probe_reserved_cost_usd": probe_reserve + next_probe_reserve,
                "status": "running",
            })
            _atomic_json(output_dir / "run.json", old_meta)

        def process(item):
            cap = mc_cap if item.task == "multiple_choice" else reading_cap
            prompt_sha = sha256_bytes(item.prompt.encode("utf-8"))
            run_key = item.run_key
            request_key = f"{PROTOCOL_ID}:{args.phase}:{args.profile}:{run_key}"
            result = _run_omp_request(
                omp_bin=args.omp_bin,
                profile=profile,
                model_id=request_model,
                endpoint=endpoint,
                prompt=item.prompt,
                request_key=request_key,
                max_tokens=cap,
                max_time=max_time,
                thinking=omp_thinking,
                tmp_root=agent_root,
                fake_home=fake_home,
                api_key=api_key,
            )
            row = {
                "run_key": run_key,
                "profile_id": args.profile,
                "dataset_id": item.dataset_id,
                "item_id": item.item_id,
                "replicate_id": item.replicate_id,
                "prompt_sha256": prompt_sha,
                "raw_prompt": item.prompt,
                "raw_response": result["raw_response"],
                "response_model_id": result["response_model_id"],
                "system_fingerprint": "",
                "service_tier": "OpenCode Go subscription" if profile.get("billing_mode") == "opencode-go-subscription" else "",
                "request_id": result["request_id"],
                "finish_reason": result["finish_reason"],
                "prompt_tokens": result["prompt_tokens"],
                "cached_prompt_tokens": result["cached_prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["total_tokens"],
                "reasoning_tokens": result["reasoning_tokens"],
                "latency_s": result["latency_s"],
                "tool_calls": result["tool_calls"],
                "omp_session_id": result["session_id"],
                "reserved_cost_usd": bounds[run_key],
                "status": result["status"],
            }
            if result["error_type"]:
                row["error_type"] = result["error_type"]
                row["error_detail"] = result["error_detail"]
            with lock:
                old = rows_by_key.get(run_key)
                row["attempts"] = int(old.get("attempts", 0)) + 1 if old else 1
                row["reserved_cost_usd"] = bounds[run_key] + (
                    float(old.get("reserved_cost_usd", 0.0)) if old else 0.0
                )
                rows_by_key[run_key] = row
                write_jsonl_atomic(output_dir / "predictions.jsonl", list(rows_by_key.values()))
            return row

        failures = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process, item): item for item in remaining}
            for future in tqdm(as_completed(futures), total=len(futures), desc=args.profile):
                row = future.result()
                if row["status"] != "complete":
                    failures.append(row)
        complete_count = sum(row.get("status") == "complete" for row in rows_by_key.values())
        old_meta.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "complete_items": complete_count,
            "failed_items": len(failures),
            "status": "complete" if complete_count == len(items) else "incomplete",
        })
        _atomic_json(output_dir / "run.json", old_meta)
        if failures:
            raise SystemExit(
                f"Error: {len(failures)} omp requests failed; {complete_count}/{len(items)} complete. "
                "Checkpoint saved; retry with --resume and the same usage cap."
            )
        print(f"completed {complete_count}/{len(items)} via omp -> {output_dir / 'predictions.jsonl'}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _phase_caps(protocol: dict, phase: str) -> tuple[int, int]:
    stored = protocol.get(phase, {}).get("max_completion_tokens") or {}
    mc = stored.get("multiple_choice")
    reading = stored.get("reading")
    if (isinstance(mc, bool) or not isinstance(mc, int) or mc <= 0
            or isinstance(reading, bool) or not isinstance(reading, int) or reading <= 0):
        raise SystemExit(f"Error: freeze positive completion token caps for {phase} before model calls")
    return mc, reading


if __name__ == "__main__":
    main()
