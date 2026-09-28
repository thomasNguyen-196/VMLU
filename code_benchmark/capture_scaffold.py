"""Capture the exact request `omp` sends, so the scaffold can be replayed offline.

WHY
---
Card MC-21 measured that being inside `omp` costs −23 points even with a neutral
system prompt and no tools, and that the persona/tool genes are substitutable.
That leaves one question the factorial cannot answer: is the damage caused by the
scaffold **as text** (a prompt effect any client could reproduce) or by the agent
**as runtime** (the loop, message assembly, stop conditions)?

`omp --mode json` does not echo the assembled system prompt, so this tool stands a
localhost logging reverse proxy in front of the gateway, sends one item through the
real harness, and writes the request body it saw to a JSON file. The captured
`messages` + `tools` are then replayable by `run_harness_eval.py replay`, which
turns "harness" into "prompt" and lets the two be priced separately.

LOCALHOST ONLY, READ-THROUGH: it binds 127.0.0.1, forwards upstream unchanged and
never modifies the body. The token is read from the harness agent dir's .env —
never hardcoded, never printed. One-shot by design: run it, take the JSON, stop it.

  # terminal 1
  .venv/bin/python code_benchmark/capture_scaffold.py --port 8799 \
      --agent-dir .omp-iec --out /tmp/scaffold_h4.json
  # terminal 2 (a throwaway agent dir whose provider points at the proxy)
  PI_CODING_AGENT_DIR=$PWD/.omp-capture omp -p --model iec/Qwen3.5-9B-28K ...
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "https://llmapi.iec-uit.com/v1"
# The upstream is a fixed https endpoint; SSRF is not reachable from the CLI here.
ALLOWED_PREFIX = "https://llmapi.iec-uit.com/v1"


def read_agent_token(agent_dir: Path) -> str:
    """The gateway token from the harness's own .env (same rule as the runner)."""
    env = agent_dir / ".env"
    if not env.exists():
        raise SystemExit(f"Error: {env} not found — the proxy needs the same token "
                         "the harness uses")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("IEC_LLM_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"Error: IEC_LLM_API_KEY missing from {env}")


class Handler(BaseHTTPRequestHandler):
    token = ""  # nosec B105 — class-level default, never a literal secret
    out: Path | None = None
    captured = 0

    def log_message(self, fmt, *args):        # noqa: A003 - silence access log noise
        pass

    def _forward(self, path: str, body: bytes | None):
        url = f"{UPSTREAM}{path}"
        if not url.startswith(ALLOWED_PREFIX):
            self.send_error(403, "upstream not allowed")
            return
        req = urllib.request.Request(url, data=body, method="POST" if body else "GET",
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        # url is built from a constant upstream plus the client's own path, and the
        # ALLOWED_PREFIX check above rejects anything else.
        return urllib.request.urlopen(req, timeout=300)  # nosec B310

    def do_GET(self):                        # noqa: N802 - http.server API
        try:
            with self._forward(self.path, None) as resp:
                payload = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            self.send_error(502, str(exc))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):                       # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"_unparsed": body[:400].decode("utf-8", "replace")}

        # Capture the FIRST chat completion verbatim, then get out of the way.
        if self.path.endswith("/chat/completions") and Handler.captured == 0 and self.out:
            Handler.captured += 1
            record = {"path": self.path,
                      "messages": parsed.get("messages"),
                      "tools": parsed.get("tools"),
                      "tool_choice": parsed.get("tool_choice"),
                      "other_keys": sorted(k for k in parsed
                                           if k not in ("messages", "tools", "tool_choice")),
                      "stream": parsed.get("stream"),
                      "temperature": parsed.get("temperature"),
                      "max_tokens": parsed.get("max_tokens") or parsed.get("max_completion_tokens")}
            self.out.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            print(f"captured request -> {self.out} "
                  f"({len(record['messages'] or [])} messages, "
                  f"{len(record['tools'] or [])} tools)", flush=True)

        try:
            resp = self._forward(self.path, body)
        except (urllib.error.URLError, OSError) as exc:
            self.send_error(502, str(exc))
            return
        # Streaming pass-through: SSE with connection close (no Content-Length).
        ctype = resp.headers.get("Content-Type", "text/event-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                chunk = resp.read(1)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            resp.close()
        self.close_connection = True


def main() -> None:
    ap = argparse.ArgumentParser(description="Log the exact request omp sends (localhost proxy).")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--agent-dir", type=Path, default=Path(".omp-iec"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    Handler.token = read_agent_token(args.agent_dir.resolve())
    Handler.out = args.out
    args.out.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"listening on http://127.0.0.1:{args.port} -> {UPSTREAM} "
          f"(capturing to {args.out}); Ctrl-C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
