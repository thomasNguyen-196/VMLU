"""Offline tests for MC-112's proxy (dsh_proxy) and relay (dsh_relay), against a scripted fake upstream."""
import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from code_benchmark import dsh_proxy as px
from code_benchmark import dsh_relay as relay
from code_benchmark import fake_chat_upstream as fu

MODEL = "Qwen3.5-9B-65K"


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: Path):
        super().__init__("localhost", timeout=10)
        self.unix_path = str(path)

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.unix_path)


def post(sock: Path, body: object, key: str = px.DUMMY_KEY, path: str = px.CHAT_PATH) -> tuple[int, bytes]:
    connection = UnixConnection(sock)
    connection.request("POST", path, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                       {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "dsh-test"})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data


def chat(**extra: object) -> dict:
    return {"model": MODEL, "messages": [{"role": "user", "content": "x"}], "stream": True, **extra}


class Proxy(unittest.TestCase):
    def run_proxy(self, script, requests, **config):
        with fu.FakeUpstream(script) as upstream, tempfile.TemporaryDirectory() as tmp:
            settings = {"upstream": upstream.url, "api_key": "REAL-KEY", "model": MODEL,
                        "expected_response_model": "fake-model.gguf",
                        "extra_headers": {"x-9router-token-saver": "off"}, **config}
            log = Path(tmp) / "log.jsonl"
            with px.AttemptProxy(px.ProxyConfig(**settings), Path(tmp) / "p.sock", log) as proxy:
                replies = [post(Path(tmp) / "p.sock", *request) for request in requests]
            records = list(proxy.records)
            logged = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            return replies, records, logged, upstream

    def test_temperature_key_and_gateway_header_are_the_only_changes(self):
        replies, records, logged, upstream = self.run_proxy([{"text": "Đáp án: B"}], [(chat(max_tokens=4096),)])
        self.assertEqual(replies[0][0], 200)
        self.assertEqual(upstream.requests[0], {**chat(max_tokens=4096), "temperature": 1.0})
        headers = upstream.headers[0]
        self.assertEqual(headers["authorization"], "Bearer REAL-KEY")
        self.assertEqual(headers["x-9router-token-saver"], "off")
        self.assertEqual(headers["user-agent"], "dsh-test")
        self.assertNotIn(px.DUMMY_KEY, json.dumps(upstream.headers))
        self.assertEqual(records[0]["outcome"], "ok")
        self.assertEqual(records[0]["response"]["content"], "Đáp án: B")
        self.assertEqual(logged, records)

    def test_stream_passes_through_unchanged(self):
        replies, records, _, upstream = self.run_proxy([{"tool": "grep", "arguments": {"pattern": "Điều 1"}}],
                                                       [(chat(),)])
        expected = "".join(f"data: {event}\n\n" for event in upstream.events({"tool": "grep", "arguments":
                                                                                {"pattern": "Điều 1"}}, 0))
        self.assertEqual(replies[0][1].decode("utf-8"), expected)
        self.assertEqual(records[0]["response"]["tool_calls"],
                         [{"id": "call_0", "name": "grep", "arguments": '{"pattern": "Điều 1"}'}])
        self.assertEqual(records[0]["response"]["usage"]["total_tokens"], 105)

    def test_a_sent_temperature_is_refused_and_never_forwarded(self):
        replies, records, _, upstream = self.run_proxy([], [(chat(temperature=0.7),)])
        self.assertEqual(replies[0][0], 400)
        self.assertEqual(records[0]["outcome"], "refused_temperature")
        self.assertEqual(upstream.requests, [])
        self.assertIn("refused_temperature", px.attempt_outcome(records)["fatal"])

    def test_wrong_model_path_and_credential_are_refused(self):
        replies, records, _, upstream = self.run_proxy(
            [], [({**chat(), "model": "other"},), (chat(), "not-the-dummy"), (chat(), px.DUMMY_KEY, "/v1/responses")])
        self.assertEqual([r[0] for r in replies], [400, 401, 404])
        self.assertEqual([r["outcome"] for r in records], ["refused_model", "refused_credential", "refused_path"])
        self.assertEqual(upstream.requests, [])

    def test_request_cap(self):
        script = [{"text": "a"}] * 3
        replies, records, _, upstream = self.run_proxy(script, [(chat(),)] * 3, request_cap=2)
        self.assertEqual([r[0] for r in replies], [200, 200, 429])
        self.assertEqual(records[-1]["outcome"], "refused_cap")
        self.assertEqual(len(upstream.requests), 2)
        self.assertTrue(px.attempt_outcome(records)["request_cap"])

    def test_gateway_statuses_are_classified(self):
        replies, records, _, _ = self.run_proxy([{"status": 503}, {"status": 400}], [(chat(),), (chat(),)])
        self.assertEqual([r[0] for r in replies], [503, 400])
        self.assertEqual([r["outcome"] for r in records], ["upstream_5xx", "upstream_4xx"])
        seen = px.attempt_outcome(records)
        self.assertTrue(seen["technical"] and seen["upstream_4xx"])

    def test_a_changed_response_model_is_flagged(self):
        _, records, _, _ = self.run_proxy([{"text": "x"}], [(chat(),)], expected_response_model="other.gguf")
        self.assertEqual(records[0]["outcome"], "model_drift")
        self.assertEqual(px.attempt_outcome(records)["fatal"], ["model_drift"])

    def test_an_unreachable_upstream_is_a_network_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = px.ProxyConfig(upstream="http://127.0.0.1:9/v1", api_key="k", model=MODEL,
                                    expected_response_model=None, request_timeout=5)
            with px.AttemptProxy(config, Path(tmp) / "p.sock", Path(tmp) / "log.jsonl") as proxy:
                status, _ = post(Path(tmp) / "p.sock", chat())
            records = list(proxy.records)
        self.assertEqual(status, 502)
        self.assertEqual(records[0]["outcome"], "network")
        self.assertTrue(px.attempt_outcome(records)["technical"])

    def test_assemble_stream_joins_reasoning_and_split_tool_arguments(self):
        lines = [{"model": "m", "choices": [{"delta": {"reasoning_content": "nghĩ "}}]},
                 {"model": "m", "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
                                                                       "function": {"name": "read", "arguments": '{"file_'}}]}}]},
                 {"model": "m", "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'path": "a.txt"}'}}]},
                                             "finish_reason": "tool_calls"}]},
                 {"model": "m", "choices": [], "usage": {"total_tokens": 9}}]
        raw = "".join(f"data: {json.dumps(line)}\n\n" for line in lines) + "data: [DONE]\n\n"
        out = px.assemble_stream(raw.encode())
        self.assertEqual(out["reasoning"], "nghĩ ")
        self.assertEqual(out["tool_calls"], [{"id": "c1", "name": "read", "arguments": '{"file_path": "a.txt"}'}])
        self.assertEqual((out["finish_reason"], out["usage"], out["done"]), ("tool_calls", {"total_tokens": 9}, True))


class Relay(unittest.TestCase):
    def test_relay_copies_bytes_both_ways(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.sock"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            server.listen(1)

            def echo():
                connection, _ = server.accept()
                data = connection.recv(1024)
                connection.sendall(data[::-1])
                connection.close()
            threading.Thread(target=echo, daemon=True).start()
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            ready = Path(tmp) / "ready"
            threading.Thread(target=relay.serve, args=(port, str(path), str(ready)), daemon=True).start()
            for _ in range(100):
                if ready.exists():
                    break
                time.sleep(0.02)
            client = socket.create_connection(("127.0.0.1", port), timeout=5)
            client.sendall(b"abc")
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(client.recv(1024), b"cba")
            client.close()
            server.close()


if __name__ == "__main__":
    unittest.main()
