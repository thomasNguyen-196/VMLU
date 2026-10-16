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
from dataclasses import dataclass

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


def build_client(
    base_url: str,
    api_key: str,
    *,
    sdk_max_retries: int = 2,
    headers_env: str = "OPENAI_EXTRA_HEADERS",
) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key, timeout=60.0,
                  default_headers=extra_headers(headers_env), max_retries=sdk_max_retries)


@dataclass(frozen=True)
class ModelCallResult:
    """Raw response and provider-reported usage for a new measured run."""

    text: str
    response_model: str
    system_fingerprint: str
    service_tier: str
    finish_reason: str
    request_id: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: int | None


def call_model_with_metadata(
    client: OpenAI,
    model: str,
    prompt: str,
    *,
    temperature: float | None,
    seed: int | None,
    max_tokens: int,
    extra_body: dict | None = None,
    token_limit_parameter: str = "max_tokens",
) -> ModelCallResult:
    """Make one direct request and return metering/provenance from the response.

    It intentionally performs no retries and does not inherit
    OPENAI_REASONING_EFFORT. A paid-run caller must record the exact request
    profile and explicitly decide whether an errored item is retried.
    """
    if token_limit_parameter not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError(f"unsupported token limit parameter: {token_limit_parameter}")
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        token_limit_parameter: max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if seed is not None:
        kwargs["seed"] = seed
    if extra_body is not None:
        kwargs["extra_body"] = extra_body
    response = client.chat.completions.create(**kwargs)
    if not response.choices:
        raise ValueError("provider returned no completion choices")
    choice = response.choices[0]
    usage = getattr(response, "usage", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    return ModelCallResult(
        text=str(choice.message.content or ""),
        response_model=str(getattr(response, "model", "") or ""),
        system_fingerprint=str(getattr(response, "system_fingerprint", "") or ""),
        service_tier=str(getattr(response, "service_tier", "") or ""),
        finish_reason=str(getattr(choice, "finish_reason", "") or ""),
        request_id=str(getattr(response, "id", "") or ""),
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
        reasoning_tokens=getattr(completion_details, "reasoning_tokens", None),
    )


def is_fatal_llm_error(err: Exception) -> bool:
    """The fatal-error rule, single-sourced: authentication/permission failures are
    NEVER retried. Factored out of `call_model_with_retry` so the logprobs sibling
    below cannot drift from it (a bad key must fail fast on both paths, not 30×)."""
    if isinstance(err, (AuthenticationError, PermissionDeniedError)):
        return True
    err_str = str(err).lower()
    return any(k in err_str for k in ("unauthorized", "401", "forbidden", "403"))


def call_logprobs_with_retry(client: OpenAI, model: str, prompt: str, temperature: float,
                             seed: int, max_tokens: int, top_logprobs: int,
                             max_retries: int = 30, sleep_sec: int = 30
                             ) -> tuple[str, str, list[dict]]:
    """`call_model_with_retry`'s logprobs sibling — same contract (30×30s generic
    retry, auth fail-fast), but it must hand back the answer-token distribution,
    which the text-only return cannot carry.

    Returns `(content, first_token, top_logprobs)` where `top_logprobs` is the
    FIRST generated token's `[{'token','logprob'}, ...]`. On transport failure that
    outlasts `max_retries` it returns `("", "", [])` — the caller records the item
    as unusable (it stays in the accuracy denominator) instead of inventing a
    probability, mirroring how an unparsed MC answer stays in the denominator.
    """
    messages = [{"role": "user", "content": prompt}]
    kwargs = {"model": model, "messages": messages, "temperature": temperature,
              "max_tokens": max_tokens, "logprobs": True, "top_logprobs": top_logprobs}
    if seed is not None:
        kwargs["seed"] = seed
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content or ""
            lp = getattr(choice, "logprobs", None)
            if lp is None or not lp.content:
                return content, "", []
            first = lp.content[0]
            top = [{"token": t.token, "logprob": t.logprob} for t in (first.top_logprobs or [])]
            return content, first.token, top
        except (AuthenticationError, PermissionDeniedError) as auth_err:
            logging.error(f"Fatal authentication/permission error: {auth_err}")
            raise auth_err
        except Exception as e:
            if is_fatal_llm_error(e):
                logging.error(f"Fatal authentication error detected in response: {e}")
                raise e
            logging.warning(f"Error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(sleep_sec)
            else:
                logging.error(f"Failed after {max_retries} attempts: {prompt[:100]}...")
                return "", "", []
    return "", "", []


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
            if is_fatal_llm_error(e):
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
