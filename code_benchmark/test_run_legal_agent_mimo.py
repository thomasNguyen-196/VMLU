"""Offline tests for MC-116's runner (run_legal_agent_mimo): sessions, provider errors, usage, cost and the direct
request against a mocked client. No endpoint is called."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

try:
    from code_benchmark import dsh_proxy as px
    from code_benchmark import run_diagnostic_prospective as pr
    from code_benchmark import run_legal_agent_mimo as rm
    from code_benchmark import run_weakness_map as rwm
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import dsh_proxy as px  # type: ignore[no-redef]
    import run_diagnostic_prospective as pr  # type: ignore[no-redef]
    import run_legal_agent_mimo as rm  # type: ignore[no-redef]
    import run_weakness_map as rwm  # type: ignore[no-redef]
    import vi_multimodel as v1  # type: ignore[no-redef]

PROTOCOL = {"model": {"model_id": "mimo-v2.6-flash"},
            "direct": {"api_protocol": "openai-chat-completions", "system_prompt": "Answer the user's question.",
                       "temperature": 1.0, "max_completion_tokens": 16000}}


def _verdict(outcome="upstream_4xx", status="complete"):
    return {"status": status, "outcome": outcome, "error_type": None, "fatal": False, "raw_response": ""}


def _failed(status, body=""):
    return {"outcome": "upstream_4xx", "status": status, "error_body": body}


class SessionAndRouteTests(unittest.TestCase):
    def test_each_try_gets_its_own_session(self):
        first, second = rm.session_id("k", 1), rm.session_id("k", 2)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("vmlu-mc116-"))
        self.assertNotEqual(rm.session_id("k"), rm.session_id("other"))

    def test_with_session_adds_the_header_and_keeps_the_rest(self):
        config = px.ProxyConfig(upstream="https://x/v1", api_key="k", model="m", expected_response_model=None,
                                extra_headers={"User-Agent": "ua"})
        out = rm.with_session(config, "x-opencode-session", "s1")
        self.assertEqual(out.extra_headers, {"User-Agent": "ua", "x-opencode-session": "s1"})
        self.assertEqual(config.extra_headers, {"User-Agent": "ua"})


class ProviderErrorTests(unittest.TestCase):
    def test_a_429_halts_and_is_technical(self):
        out = rm.provider_verdict(_verdict(), [_failed(429, "GoUsageLimitError")], "k", rm.BadRequests())
        self.assertEqual((out["status"], out["outcome"], out["error_type"], out["fatal"]),
                         ("request_error", "technical", "rate_limited_429", True))

    def test_an_auth_error_halts(self):
        out = rm.provider_verdict(_verdict(), [_failed(401)], "k", rm.BadRequests())
        self.assertTrue(out["fatal"])
        self.assertEqual(out["error_type"], "provider_refused_401")

    def test_a_plain_400_is_technical_until_the_cap(self):
        bad = rm.BadRequests()
        for n in range(rm.MAX_ATTEMPTS_WITH_400):
            out = rm.provider_verdict(_verdict(), [_failed(400, "bad gateway state")], f"k{n}", bad)
            self.assertEqual((out["status"], out["error_type"], out["fatal"]), ("request_error", "provider_400", False))
        out = rm.provider_verdict(_verdict(), [_failed(400)], "one-more", bad)
        self.assertTrue(out["fatal"])

    def test_a_400_naming_a_policy_stays_terminal(self):
        verdict = _verdict()
        out = rm.provider_verdict(verdict, [_failed(400, '{"code": "content_policy_violation"}')], "k", rm.BadRequests())
        self.assertEqual(out, verdict)

    def test_other_outcomes_are_untouched(self):
        for outcome in ("complete", "answer_cap", "request_cap", "technical"):
            verdict = _verdict(outcome)
            self.assertEqual(rm.provider_verdict(verdict, [_failed(429)], "k", rm.BadRequests()), verdict)


class UsageAndCostTests(unittest.TestCase):
    def test_usage_details_sum_answered_requests(self):
        records = [{"outcome": "ok", "response": {"usage": {"completion_tokens": 900,
                                                            "completion_tokens_details": {"reasoning_tokens": 800},
                                                            "prompt_tokens_details": {"cached_tokens": 1000}}}},
                   {"outcome": "ok", "response": {"usage": {"completion_tokens": 300,
                                                            "completion_tokens_details": {"reasoning_tokens": 200}}}},
                   {"outcome": "network"}]
        self.assertEqual(rm.usage_details(records), {"reasoning_tokens": 1000, "cached_prompt_tokens": 1000,
                                                     "max_completion_tokens_used": 900})
        self.assertEqual(rm.usage_details([]), {"reasoning_tokens": None, "cached_prompt_tokens": None,
                                                "max_completion_tokens_used": None})

    def test_cost_prices_cached_and_uncached_input_apart(self):
        rate = {"input": 0.14, "cached_input": 0.0028, "output": 0.28}
        rows = [{"prompt_tokens": 1_000_000, "cached_prompt_tokens": 500_000, "completion_tokens": 100_000}]
        self.assertAlmostEqual(rm.cost_usd(rows, rate), 0.5 * 0.14 + 0.5 * 0.0028 + 0.1 * 0.28, places=4)

    def test_the_registry_holds_mimos_prices(self):
        self.assertEqual(set(rm.prices()), {"input", "cached_input", "output"})


class _StatusError(Exception):
    def __init__(self, status_code, body=None):
        super().__init__("upstream")
        self.status_code, self.body = status_code, body


class _Client:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        finish, text = self.outcome
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150,
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=40),
                                prompt_tokens_details=SimpleNamespace(cached_tokens=0))
        message = SimpleNamespace(content=text, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)], usage=usage,
                               model="mimo-v2.6-flash", id="r1")


class DirectRequestTests(unittest.TestCase):
    def _run(self, outcome, bad=None):
        request = rm.make_direct_request(PROTOCOL, "MC-116", pr.BudgetGuard(10**9, 0), pr.OutageGuard(10**6),
                                         rwm.ModelPin("mimo"), bad or rm.BadRequests(), "x-opencode-session")
        item = v1.EvalItem(dataset_id="d", source_dataset="d", item_id="1", replicate_id="B-r1",
                           task="multiple_choice", stratum="s", question="q", passage_id="", prompt="Câu hỏi",
                           gold_answer="A")
        client = _Client(outcome)
        return request(client, item, 0, 0), client

    def test_a_finished_answer_is_complete_and_sends_the_registered_request(self):
        row, client = self._run(("stop", "Đáp án: A"))
        self.assertEqual((row["status"], row["outcome"], row["raw_response"]), ("complete", "complete", "Đáp án: A"))
        call = client.calls[0]
        self.assertEqual((call["max_completion_tokens"], call["temperature"], call["stream"]), (16000, 1.0, False))
        self.assertEqual(call["messages"][0], {"role": "system", "content": "Answer the user's question."})
        self.assertIn("x-opencode-session", call["extra_headers"])
        self.assertEqual(row["reasoning_tokens"], 40)

    def test_a_cut_answer_is_complete_and_terminal(self):
        row, _ = self._run(("length", ""))
        self.assertEqual((row["status"], row["outcome"]), ("complete", "answer_cap"))

    def test_a_429_halts(self):
        row, _ = self._run(_StatusError(429))
        self.assertEqual((row["status"], row["fatal"]), ("request_error", True))

    def test_a_plain_400_is_technical_and_a_policy_400_terminal(self):
        row, _ = self._run(_StatusError(400, {"code": "bad_request"}))
        self.assertEqual((row["status"], row["error_type"], row["fatal"]), ("request_error", "provider_400", False))
        row, _ = self._run(_StatusError(400, {"code": "content_policy_violation"}))
        self.assertEqual((row["status"], row["outcome"]), ("complete", "upstream_4xx"))


if __name__ == "__main__":
    unittest.main()
