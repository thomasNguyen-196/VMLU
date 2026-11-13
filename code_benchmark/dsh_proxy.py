"""MC-112: the proxy between an attempt's sandbox and the model endpoint (openspec change diagnostic-legal-agent).

dsh runs in a sandbox with no network; its only way out is this proxy's Unix socket (reached through `dsh_relay`).
For every request the proxy:

* accepts only `POST /v1/chat/completions` carrying the registered model id and the sandbox's dummy credential;
* refuses a body that already carries `temperature` (dsh sends none; one appearing means its behaviour changed);
* adds `"temperature": 1.0`, the only change to the body, and swaps the dummy credential for the endpoint's key;
* adds the campaign's gateway header, as MC-90 to MC-111 sent it, and asks for an uncompressed stream;
* forwards to the registered API root and streams the response back unchanged;
* refuses the attempt's request after the cap (default 30) with HTTP 429;
* records the body as received and as sent, the status, the assembled response (text, reasoning text, tool calls,
  finish reason, usage, response model id) and timings, one JSON line per request.

The endpoint key never enters the sandbox. Outcomes per request: `ok`, `upstream_4xx`, `upstream_5xx`, `network`,
`model_drift` and the refusals `refused_cap`, `refused_temperature`, `refused_model`, `refused_path`,
`refused_credential`, `refused_body`.
"""
from __future__ import annotations

import http.client
import json
import socket
import socketserver
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

CHAT_PATH = "/v1/chat/completions"
DUMMY_KEY = "dsh-sandbox-not-a-key"
TECHNICAL = frozenset({"network", "upstream_5xx"})
FATAL = frozenset({"refused_temperature", "refused_model", "refused_path", "refused_credential", "refused_body",
                   "model_drift"})
_HOP = frozenset({"host", "content-length", "authorization", "accept-encoding", "connection", "keep-alive",
                  "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization", "proxy-connection"})


@dataclass(frozen=True)
class ProxyConfig:
    upstream: str                       # API root, e.g. http://host/v1
    api_key: str
    model: str                          # requested model id
    expected_response_model: str | None  # self-reported id; None skips the check (offline tests)
    temperature: float = 1.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    request_timeout: float = 300.0
    request_cap: int = 30
    dummy_key: str = DUMMY_KEY


def assemble_stream(raw: bytes) -> dict[str, Any]:
    """The response a Chat Completions SSE stream carries: text, reasoning text, tool calls in index order, the last
    finish reason, the usage chunk, the model id and whether `[DONE]` arrived."""
    content: list[str] = []
    reasoning: list[str] = []
    calls: dict[int, dict[str, Any]] = {}
    finish, usage, model, done, chunks = None, None, None, False, 0
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            done = True
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        chunks += 1
        model = chunk.get("model") or model
        if isinstance(chunk.get("usage"), dict):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                content.append(delta["content"])
            for key in ("reasoning_content", "reasoning"):
                if isinstance(delta.get(key), str):
                    reasoning.append(delta[key])
            for call in delta.get("tool_calls") or []:
                slot = calls.setdefault(int(call.get("index", 0)), {"id": None, "name": "", "arguments": ""})
                slot["id"] = call.get("id") or slot["id"]
                function = call.get("function") or {}
                slot["name"] += function.get("name") or ""
                slot["arguments"] += function.get("arguments") or ""
            finish = choice.get("finish_reason") or finish
    return {"content": "".join(content), "reasoning": "".join(reasoning),
            "tool_calls": [calls[index] for index in sorted(calls)], "finish_reason": finish, "usage": usage,
            "model": model, "done": done, "chunks": chunks}


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = False
    block_on_close = True  # server_close() joins every handler, so all records are written before they are read
    proxy: AttemptProxy


class _Handler(BaseHTTPRequestHandler):
    @property
    def proxy(self) -> AttemptProxy:
        return cast(_Server, self.server).proxy

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base class's name
        return

    def _reply(self, status: int, message: str) -> None:
        body = json.dumps({"error": {"message": message, "type": "proxy_refusal"}}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        self.proxy.refuse(self, "refused_path", 405, f"{self.command} {self.path}")

    do_HEAD = do_PUT = do_DELETE = do_PATCH = do_GET  # noqa: N815

    def do_POST(self) -> None:  # noqa: N802
        self.proxy.handle(self)


class AttemptProxy:
    """One attempt's proxy: serves the Unix socket `socket_path` and appends each request to `log_path`. Read
    `records` after `stop()` (or the `with` block): stopping waits for every request in progress to be recorded."""

    def __init__(self, config: ProxyConfig, socket_path: Path, log_path: Path):
        self.config = config
        self.socket_path = Path(socket_path)
        self.log_path = Path(log_path)
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._count = 0
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        target = urlsplit(config.upstream)
        if target.scheme not in {"http", "https"} or not target.hostname:
            raise ValueError("the upstream must be an http(s) API root")
        self._target = target

    def __enter__(self) -> AttemptProxy:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        self.socket_path.unlink(missing_ok=True)
        self._server = _Server(str(self.socket_path), _Handler)
        self._server.proxy = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self.socket_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------ bookkeeping
    def _next(self) -> int:
        with self._lock:
            self._count += 1
            return self._count

    def _record(self, record: dict[str, Any]) -> None:
        with self._lock:
            self.records.append(record)
            with self.log_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps(record, ensure_ascii=False) + "\n")

    def refuse(self, handler: _Handler, outcome: str, status: int, detail: str, n: int | None = None,
               received: str | None = None) -> None:
        self._record({"n": n or self._next(), "at": time.time(), "outcome": outcome, "status": status,
                      "detail": detail, "body_received": received})
        handler._reply(status, f"{outcome}: {detail}")  # noqa: SLF001 - same module

    # ------------------------------------------------------------------ one request
    def handle(self, handler: _Handler) -> None:
        n = self._next()
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        received = raw.decode("utf-8", errors="replace")
        if handler.path != CHAT_PATH:
            return self.refuse(handler, "refused_path", 404, f"POST {handler.path}", n, received)
        if handler.headers.get("Authorization") != f"Bearer {self.config.dummy_key}":
            return self.refuse(handler, "refused_credential", 401, "unexpected credential", n, received)
        if n > self.config.request_cap:
            return self.refuse(handler, "refused_cap", 429, f"request cap {self.config.request_cap} reached", n,
                               received)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self.refuse(handler, "refused_body", 400, "body is not JSON", n, received)
        if not isinstance(body, dict) or body.get("model") != self.config.model:
            return self.refuse(handler, "refused_model", 400, f"model {body.get('model')!r}"
                               if isinstance(body, dict) else "body is not an object", n, received)
        if "temperature" in body:
            return self.refuse(handler, "refused_temperature", 400, f"temperature {body['temperature']!r} sent",
                               n, received)
        sent = {**body, "temperature": self.config.temperature}
        self._forward(handler, n, received, sent)

    def _forward(self, handler: _Handler, n: int, received: str, sent: dict[str, Any]) -> None:
        payload = json.dumps(sent, ensure_ascii=False).encode("utf-8")
        headers = {key: value for key, value in handler.headers.items() if key.lower() not in _HOP}
        headers.update({"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json",
                        "Accept-Encoding": "identity", **self.config.extra_headers})
        record: dict[str, Any] = {"n": n, "at": time.time(), "body_received": received,
                                  "body_sent": payload.decode("utf-8")}
        start = time.monotonic()
        target = self._target
        connection_class = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        connection = connection_class(target.hostname or "", target.port, timeout=self.config.request_timeout)
        streamed = bytearray()
        try:
            try:
                connection.request("POST", target.path.rstrip("/") + "/chat/completions", body=payload,
                                   headers=headers)
                response = connection.getresponse()
            except (OSError, http.client.HTTPException) as exc:
                record.update({"outcome": "network", "error_type": type(exc).__name__, "status": None})
                handler._reply(502, "upstream unreachable")  # noqa: SLF001
                return
            record["status"] = response.status
            if response.status != 200:
                text = response.read(65536)
                record.update({"outcome": "upstream_4xx" if response.status < 500 else "upstream_5xx",
                               "error_body": text.decode("utf-8", errors="replace")})
                handler.send_response(response.status)
                handler.send_header("Content-Type", response.getheader("Content-Type") or "application/json")
                handler.send_header("Content-Length", str(len(text)))
                handler.end_headers()
                handler.wfile.write(text)
                return
            handler.send_response(200)
            handler.send_header("Content-Type", response.getheader("Content-Type") or "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.end_headers()
            try:
                while True:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    streamed.extend(chunk)
                    handler.wfile.write(chunk)
                    handler.wfile.flush()
            except (TimeoutError, socket.timeout, ConnectionResetError, http.client.HTTPException) as exc:
                record.update({"outcome": "network", "error_type": type(exc).__name__})
                return
            except BrokenPipeError:
                record["client_gone"] = True
            assembled = assemble_stream(bytes(streamed))
            record["response"] = assembled
            expected = self.config.expected_response_model
            record["outcome"] = ("model_drift" if expected is not None and assembled["model"] != expected
                                 else "ok" if assembled["done"] or assembled["finish_reason"] else "network")
            if record["outcome"] == "network":
                record["error_type"] = "stream_ended_early"
        finally:
            connection.close()
            record["latency_s"] = round(time.monotonic() - start, 4)
            record["stream_bytes"] = len(streamed)
            self._record(record)


def attempt_outcome(records: list[dict[str, Any]]) -> dict[str, Any]:
    """What the proxy saw over one attempt: request counts, summed usage and the flags the runner classifies by."""
    outcomes = [record.get("outcome") for record in records]
    usage = [((record.get("response") or {}).get("usage") or {}) for record in records]

    def total(key: str) -> int | None:
        values = [u[key] for u in usage if isinstance(u.get(key), int)]
        return sum(values) if values else None

    answered = [record for record in records if record.get("outcome") == "ok"]
    models = sorted({str(record["response"]["model"]) for record in answered if record["response"].get("model")})
    return {
        "requests": len(records), "forwarded": sum(o not in FATAL and not str(o).startswith("refused") for o in outcomes),
        "outcomes": {o: outcomes.count(o) for o in sorted({str(o) for o in outcomes})},
        "technical": any(o in TECHNICAL for o in outcomes), "fatal": [o for o in outcomes if o in FATAL],
        "request_cap": "refused_cap" in outcomes, "upstream_4xx": "upstream_4xx" in outcomes,
        "last_finish_reason": answered[-1]["response"]["finish_reason"] if answered else None,
        "prompt_tokens": total("prompt_tokens"), "completion_tokens": total("completion_tokens"),
        "total_tokens": total("total_tokens"), "response_models": models,
        "tool_calls_requested": sum(len(record["response"]["tool_calls"]) for record in answered),
    }
