"""Capture (and pin) the exact request `omp` sends, so the scaffold is auditable.

WHY
---
Card MC-21 measured that being inside `omp` costs −23 points even with a neutral
system prompt and no tools, and that the persona/tool genes are substitutable.
That leaves one question the factorial cannot answer: is the damage caused by the
scaffold **as text** (a prompt effect any client could reproduce) or by the agent
**as runtime** (the loop, message assembly, stop conditions)?

The first capture run (MC arm, 2026-09-29) answered part of it: `omp` sends a
system message of `PROJECT` + `<critical>` action mandates no matter what
`--system-prompt` says, prepends a dated `<system-reminder>` to the user turn,
and sends **no temperature and no reasoning_effort at all** — so a harness arm
runs at the provider's sampling default while the direct arm runs greedy. Two
knobs, neither reachable from `omp`'s config or CLI (`options:` in models.yml is
silently ignored).

So this tool has two jobs, both on the same localhost read-through hop:
  * capture — write the request body it saw (what it was always for);
  * pin    — `--pin temperature=0 --pin reasoning_effort="none"` forces a field
             before forwarding, which is the only way to hold those two knobs
             equal across the arms. Every pin is written into the capture file,
             so a pinned run can always be audited for what the proxy changed.

`omp --mode json` does not echo the assembled system prompt, so this tool stands a
localhost logging reverse proxy in front of the gateway, sends one item through the
real harness, and writes the request body it saw to a JSON file. The captured
`messages` + `tools` are then replayable by `run_harness_eval.py replay`, which
turns "harness" into "prompt" and lets the two be priced separately.

LOCALHOST ONLY, READ-THROUGH: it binds 127.0.0.1 and forwards upstream unchanged,
except for the explicit `--pin` fields, which are recorded in the capture file.
The token is read from the harness agent dir's .env — never hardcoded, never
printed. One-shot by design for capture; a *measured* arm may leave it running
for the whole run, which is why the SSE pass-through reads in 4 KiB chunks.

  # terminal 1
  .venv/bin/python code_benchmark/capture_scaffold.py --port 8799 \
      --agent-dir .omp-iec --out /tmp/scaffold_h4.json
  # terminal 2 (a throwaway agent dir whose provider points at the proxy)
  PI_CODING_AGENT_DIR=$PWD/.omp-capture omp -p --model iec/Qwen3.5-9B-28K ...

  # a measured arm that needs the two knobs omp cannot send
  .venv/bin/python code_benchmark/capture_scaffold.py --port 8799 \
      --agent-dir .omp-mimo --out /tmp/scaffold_mimo_pinned.json \
      --upstream https://opencode.ai/zen/go/v1 \
      --header x-opencode-session:vmlu --header "User-Agent:Mozilla/5.0 ..." \
      --pin temperature=0 --pin 'reasoning_effort="none"'
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_UPSTREAM = "https://llmapi.iec-uit.com/v1"


def read_agent_token(agent_dir: Path) -> str:
    """The gateway token from the harness's own .env (same rule as the runner)."""
    env = agent_dir / ".env"
    if not env.exists():
        raise SystemExit(f"Error: {env} not found — the proxy needs the same token "
                         "the harness uses")
    for line in env.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip().endswith("_API_KEY") and value.strip():
            return value.strip().strip('"').strip("'")
    raise SystemExit(f"Error: no *_API_KEY in {env}")


class Handler(BaseHTTPRequestHandler):
    token = ""  # nosec B105 — class-level default, never a literal secret
    out: Path | None = None
    captured = 0
    upstream = DEFAULT_UPSTREAM
    # Any extra request header the real gateway needs (a Cloudflare-fronted
    # endpoint answers a bare urllib request with 403 code 1010, and opencode-go
    # also wants x-opencode-session). Without these the capture records a
    # rejection, not the request omp assembles.
    extra_headers: dict[str, str] = {}
    # Request fields to force before forwarding. Needed because some clients
    # cannot express a knob at all: `omp` sends no temperature and no
    # reasoning_effort, so an arm measured through it would otherwise run at the
    # provider's sampling default while the direct arm runs greedy. Forcing them
    # here is what makes "only the elicitation path differs" true. Values are
    # JSON, so `temperature=0` is a number and `reasoning_effort=none` a string.
    pin: dict = {}
    seen = 0

    def log_message(self, fmt, *args):        # noqa: A003 - silence access log noise
        pass

    def _forward(self, path: str, body: bytes | None):
        # The client's baseUrl already carries the /v1 the upstream also carries,
        # so a naive join asked for /v1/v1/chat/completions. Deduped here.
        suffix = path
        if self.upstream.endswith("/v1") and suffix.startswith("/v1/"):
            suffix = suffix[len("/v1"):]
        url = f"{self.upstream}{suffix}"
        if not url.startswith(self.upstream):
            self.send_error(403, "upstream not allowed")
            return
        headers = {"Authorization": f"Bearer {self.token}",
                   "Content-Type": "application/json", **self.extra_headers}
        req = urllib.request.Request(url, data=body, method="POST" if body else "GET",
                                     headers=headers)
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

        pinned_applied: dict = {}
        if Handler.pin and self.path.endswith("/chat/completions"):
            for key, value in Handler.pin.items():
                if parsed.get(key) != value:
                    pinned_applied[key] = {"from": parsed.get(key), "to": value}
                    parsed[key] = value
            if pinned_applied:
                body = json.dumps(parsed).encode()

        # Inventory line for EVERY request, not just the captured one: an agent
        # may make helper calls the ledger never mentions, and a request with a
        # 27 kB system prompt and an empty user turn is exactly the kind of thing
        # that has to be on the record rather than inferred.
        if self.path.endswith("/chat/completions"):
            msgs = parsed.get("messages") or []
            shape = " ".join(f"{m.get('role')}={len(str(m.get('content')))}" for m in msgs)
            print(f"#{Handler.seen + 1} model={parsed.get('model')} "
                  f"msgs={len(msgs)} [{shape}] tools={len(parsed.get('tools') or [])} "
                  f"max_tok={parsed.get('max_tokens') or parsed.get('max_completion_tokens')}",
                  flush=True)
            Handler.seen += 1

        # Capture the FIRST chat completion, then get out of the way.
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
                      "max_tokens": parsed.get("max_tokens") or parsed.get("max_completion_tokens"),
                      "pinned_by_proxy": pinned_applied or None,
                      "pinned_always": Handler.pin or None}
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
            # 4 KiB chunks, not one byte: a byte-at-a-time reader with a flush per
            # byte made a 40-item capture take minutes, which a 5.141-item arm
            # cannot afford. Still transparent — same bytes, same order.
            while True:
                chunk = resp.read(4096)
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
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM,
                    help="https base URL of the gateway the arm is measured against "
                         f"(default: {DEFAULT_UPSTREAM})")
    ap.add_argument("--header", action="append", default=[],
                    metavar="NAME:VALUE",
                    help="extra request header the gateway needs; repeatable")
    ap.add_argument("--pin", action="append", default=[], metavar="KEY=JSON",
                    help="force a request field before forwarding (e.g. --pin "
                         "temperature=0 --pin reasoning_effort=\"none\"); repeatable. "
                         "Only for clients that cannot send the field themselves.")
    args = ap.parse_args()

    pin: dict = {}
    for item in args.pin:
        key, sep, raw = item.partition("=")
        if not sep or not key.strip():
            raise SystemExit(f"Error: --pin must be KEY=JSON, got {item!r}")
        try:
            pin[key.strip()] = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"Error: --pin {key.strip()}: {raw!r} is not JSON: {e}") from e

    if not args.upstream.startswith("https://"):
        raise SystemExit(f"Error: --upstream must be https, got {args.upstream}")
    extra = {}
    for item in args.header:
        name, sep, value = item.partition(":")
        if not sep or not name.strip():
            raise SystemExit(f"Error: --header must be NAME:VALUE, got {item!r}")
        extra[name.strip()] = value.strip()

    Handler.token = read_agent_token(args.agent_dir.resolve())
    Handler.out = args.out
    Handler.upstream = args.upstream.rstrip("/")
    Handler.extra_headers = extra
    Handler.pin = pin
    args.out.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"listening on http://127.0.0.1:{args.port} -> {Handler.upstream} "
          f"(capturing to {args.out}; {len(extra)} extra header(s); "
          f"pinning {pin or '{}'}); Ctrl-C to stop",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
