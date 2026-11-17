"""MC-112: the byte relay that runs inside an attempt's sandbox (stdlib only; started as `python3 -I`).

The sandbox has no network of its own. dsh talks to `127.0.0.1:<port>`; this relay copies every connection's bytes,
unchanged and in both directions, to the proxy's Unix socket, which is bound into the sandbox. It reads nothing and
changes nothing; the proxy outside the sandbox does all the HTTP work.

    python3 -I dsh_relay.py <port> <unix socket path> [<ready file, written once listening>]
"""
from __future__ import annotations

import socket
import sys
import threading


def _pump(source: socket.socket, target: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _serve_one(client: socket.socket, socket_path: str) -> None:
    upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        upstream.connect(socket_path)
    except OSError:
        client.close()
        upstream.close()
        return
    back = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
    back.start()
    _pump(client, upstream)
    back.join()
    client.close()
    upstream.close()


def serve(port: int, socket_path: str, ready_file: str | None = None) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(16)
    if ready_file:
        with open(ready_file, "w", encoding="utf-8") as handle:
            handle.write("ready\n")
    while True:
        client, _ = listener.accept()
        threading.Thread(target=_serve_one, args=(client, socket_path), daemon=True).start()


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: dsh_relay.py <port> <unix socket path> [<ready file>]")
    serve(int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
