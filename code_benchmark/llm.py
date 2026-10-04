"""OpenAI-compatible endpoint client: construction, retry, fail-fast probe.

Lifted verbatim out of test_ollama.py, where run_reading_eval.py already
imported these two functions from it — the reading runner has no business
depending on the MC runner's module, so the seam is now explicit.

Retry contract (do not "fix"): generic errors retry 30x at 30s intervals;
authentication/permission errors are NEVER retried — they re-raise so the run
fails fast instead of burning 15 minutes per question on a bad key.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

from openai import OpenAI, AuthenticationError, PermissionDeniedError


def extra_headers(var: str = "OPENAI_EXTRA_HEADERS") -> dict[str, str] | None:
    """Headers every request must carry, from `var` (JSON object).

    Not decoration: a gateway behind Cloudflare answers a bare client with
    `403 error code 1010`, and opencode-go answers without `x-opencode-session`
    with `400 MissingSessionID`. Env-driven (not a CLI flag) so no call site
    changes and the header set travels with the endpoint config, like the key.
    The variable name is a parameter so a second endpoint (the faithfulness
    judge's JUDGE_HEADERS) can carry its own set without leaking into this one.
    """
    raw = os.getenv(var)
    if not raw:
        return None
    try:
        headers = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Error: {var} is not valid JSON: {e}") from e
    if not isinstance(headers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
    ):
        raise SystemExit(f"Error: {var} must be a JSON object "
                         "mapping header names to string values")
    return headers


def build_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key, timeout=60.0,
                  default_headers=extra_headers())


def call_model_with_retry(client: OpenAI, model: str, prompt: str, temperature: float, seed: int, max_tokens: int, max_retries: int = 30, sleep_sec: int = 30, extra_body: dict | None = None) -> str:
    messages = [{"role": "user", "content": prompt}]
    for attempt in range(1, max_retries + 1):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if seed is not None:
                kwargs["seed"] = seed
            if extra_body is not None:
                kwargs["extra_body"] = extra_body
            elif os.getenv("OPENAI_REASONING_EFFORT"):
                kwargs["extra_body"] = {"reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT")}

            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            return content if content is not None else ""
        except (AuthenticationError, PermissionDeniedError) as auth_err:
            logging.error(f"Fatal authentication/permission error: {auth_err}")
            raise auth_err
        except Exception as e:
            err_str = str(e).lower()
            if "unauthorized" in err_str or "401" in err_str or "forbidden" in err_str or "403" in err_str:
                logging.error(f"Fatal authentication error detected in response: {e}")
                raise e
            logging.warning(f"Error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(sleep_sec)
            else:
                logging.error(f"Failed after {max_retries} attempts: {prompt[:100]}...")
                return ""
    return ""


def verify_credentials(client: OpenAI, model: str):
    """Probe endpoint with 1 test token to fail-fast on auth/model errors.
    Raises SystemExit(1) — the caller's CLI error path (run with a try/except
    if embedding this in a library)."""
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0
        )
    except Exception as e:
        print(f"\n[FATAL] Endpoint probe failed for model '{model}'.\nError: {e}\nPlease check OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL.", file=sys.stderr)
        raise SystemExit(1) from e
