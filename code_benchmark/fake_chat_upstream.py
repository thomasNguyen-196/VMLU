"""A scripted Chat Completions server on loopback, for MC-112's offline tests and end-to-end check (no model).

Request i gets step i of the script: `{"tool": name, "arguments": {...}}` streams one tool call, `{"text": "..."}`
streams text, `{"status": 503}` answers with that status. Responses are SSE in llama.cpp's shape: a role chunk,
deltas, a finish chunk, a usage chunk and `[DONE]`. Every request body is kept in `requests`.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeUpstream:
    def __init__(self, script: list[dict[str, Any]], model: str = "fake-model.gguf"):
        self.script = list(script)
        self.model = model
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                with fake._lock:  # noqa: SLF001
                    fake.requests.append(body)
                    fake.headers.append({key.lower(): value for key, value in self.headers.items()})
                    index = len(fake.requests) - 1
                step = fake.script[index] if index < len(fake.script) else {"text": "Đáp án: A"}
                if "status" in step:
                    payload = json.dumps({"error": {"message": "scripted failure"}}).encode()
                    self.send_response(int(step["status"]))
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for event in fake.events(step, index):
                    data = f"data: {event}\n\n".encode()
                    self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def events(self, step: dict[str, Any], index: int) -> list[str]:
        def chunk(delta: dict[str, Any], finish: str | None = None) -> str:
            return json.dumps({"id": f"chatcmpl-{index}", "object": "chat.completion.chunk", "model": self.model,
                               "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]},
                              ensure_ascii=False)
        out = [chunk({"role": "assistant", "content": None})]
        if "tool" in step:
            arguments = json.dumps(step["arguments"], ensure_ascii=False)
            out.append(chunk({"tool_calls": [{"index": 0, "id": f"call_{index}", "type": "function",
                                              "function": {"name": step["tool"], "arguments": ""}}]}))
            out.append(chunk({"tool_calls": [{"index": 0, "function": {"arguments": arguments}}]}))
            out.append(chunk({}, "tool_calls"))
        else:
            out.extend(chunk({"content": piece}) for piece in (step["text"][:5], step["text"][5:]) if piece)
            out.append(chunk({}, "stop"))
        out.append(json.dumps({"id": f"chatcmpl-{index}", "object": "chat.completion.chunk", "model": self.model,
                               "choices": [], "usage": {"prompt_tokens": 100 + index, "completion_tokens": 5,
                                                        "total_tokens": 105 + index}}))
        out.append("[DONE]")
        return out

    def __enter__(self) -> FakeUpstream:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
