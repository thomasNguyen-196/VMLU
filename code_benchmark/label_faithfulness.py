#!/usr/bin/env python3
"""Local labeling server for the faithfulness validation gate (group 2.2).

Serves the blind sheet in a browser and AUTO-SAVES every click straight into the
labels CSV (atomic write) — no download, no manual export. Re-opening the page
resumes from whatever is already in the file.

    .venv/bin/python code_benchmark/label_faithfulness.py \
        --sheet all_res/ollama_result/Qwen3_5-9B-65K/faithfulness_sheet_Qwen3_5-9B-65K-cite.csv \
        --labels data/faithfulness_labels_Qwen3_5-9B-65K-cite.csv --open

Localhost only, no auth (same trust model as the review app). The labels file
stays a plain committed CSV: the server only ever writes the four contract
columns, in sheet order, so a label run is reproducible and diffable.
"""

from __future__ import annotations

import argparse
import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import read_csv_checked, write_csv_atomic
except ImportError:  # direct run from code_benchmark/
    from common import read_csv_checked, write_csv_atomic

LABEL_COLS = ["dataset", "item_id", "human_supports", "note"]
SHEET_COLS = ["dataset", "item_id", "question", "context", "answer", "citation"]
VALID_VALUES = ("yes", "no")


def load_sheet(path: Path) -> list[dict]:
    return read_csv_checked(path, required=set(SHEET_COLS), label="sheet")


def load_labels(path: Path) -> dict[str, dict]:
    """key 'dataset:item_id' -> {human_supports, note}. Missing file -> empty
    (the committed scaffold may start blank); empty value = not yet labeled."""
    if not path.exists():
        return {}
    store: dict[str, dict] = {}
    for r in read_csv_checked(path, required=set(LABEL_COLS), label="labels"):
        key = f"{r['dataset']}:{r['item_id']}"
        store[key] = {"human_supports": str(r.get("human_supports", "")).strip().lower(),
                      "note": str(r.get("note", ""))}
    return store


def upsert_label(store: dict[str, dict], dataset: str, item_id: str,
                 value: str, note: str) -> None:
    """Validate and record one label. Anything but yes/no is a hard error — the
    gate needs a binary rater, and guessing a label would corrupt the exam."""
    value = str(value).strip().lower()
    if value not in VALID_VALUES:
        raise ValueError(f"human_supports must be yes/no, got {value!r}")
    store[f"{dataset}:{item_id}"] = {"human_supports": value, "note": str(note or "")}


def write_labels(path: Path, store: dict[str, dict], sheet: list[dict]) -> None:
    """Write the four contract columns in SHEET order (stable diff), blank for
    items not yet labeled."""
    rows = []
    for r in sheet:
        key = f"{r['dataset']}:{r['item_id']}"
        lab = store.get(key, {})
        rows.append({"dataset": r["dataset"], "item_id": r["item_id"],
                     "human_supports": lab.get("human_supports", ""),
                     "note": lab.get("note", "")})
    write_csv_atomic(path, rows, LABEL_COLS)


def render_page(sheet: list[dict], store: dict[str, dict]) -> str:
    """The whole UI as one self-contained page. Every sheet string is escaped —
    the sheet is model output and is never trusted as markup."""
    items = []
    for i, r in enumerate(sheet):
        key = f"{r['dataset']}:{r['item_id']}"
        lab = store.get(key, {})
        val = lab.get("human_supports", "")
        note = lab.get("note", "")
        esc = html.escape
        items.append(
            f'<div class="item {"done" if val else ""}" id="i{i}" tabindex="0" '
            f'data-ds="{esc(r["dataset"])}" data-id="{esc(r["item_id"])}">'
            f'<div class="head"><b>{i + 1}. {esc(r["dataset"])} · {esc(r["item_id"])}</b></div>'
            f'<div><b>Câu hỏi:</b> {esc(r["question"])}</div>'
            f'<div class="ctx">{esc(r["context"])}</div>'
            f'<div><b>Trả lời:</b> <span class="a">{esc(r["answer"])}</span></div>'
            f'<div><b>Trích dẫn:</b> <span class="c">{esc(r["citation"])}</span></div>'
            f'<div class="pick">'
            f'<label><input type="radio" name="n{i}" value="yes" {"checked" if val == "yes" else ""}> Có</label>'
            f'<label><input type="radio" name="n{i}" value="no" {"checked" if val == "no" else ""}> Không</label>'
            f'<input class="note" type="text" placeholder="note (không bắt buộc)" value="{esc(note)}">'
            f'</div></div>')
    return _TEMPLATE.replace("__ITEMS__", "\n".join(items)).replace("__N__", str(len(sheet)))


_TEMPLATE = """<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Faithfulness labeling</title>
<style>
:root{color-scheme:light dark}
body{font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:920px;margin:0 auto;padding:0 16px 80px}
header{position:sticky;top:0;background:Canvas;padding:12px 0;border-bottom:1px solid color-mix(in srgb,CanvasText 15%,Canvas);z-index:5}
.bar{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.prog{font-variant-numeric:tabular-nums;font-weight:600}
button{padding:7px 12px;border-radius:8px;border:1px solid color-mix(in srgb,CanvasText 30%,Canvas);background:Canvas;color:CanvasText;cursor:pointer}
button.primary{background:#111;color:#fff;border-color:#111}
@media (prefers-color-scheme:dark){button.primary{background:#eee;color:#111;border-color:#eee}}
.item{border:1px solid color-mix(in srgb,CanvasText 15%,Canvas);border-radius:12px;padding:14px 16px;margin:14px 0}
.item.done{opacity:.55;border-color:#16a34a}
.item:focus{outline:2px solid #2563eb;outline-offset:2px}
.head{font-weight:700;margin-bottom:6px}
.ctx{background:color-mix(in srgb,CanvasText 6%,Canvas);border-radius:8px;padding:10px;white-space:pre-wrap;max-height:240px;overflow:auto;margin:6px 0;font-size:14px}
.a{color:#047857;font-weight:600}.c{color:#1d4ed8}
.pick{margin-top:10px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.pick label{cursor:pointer;font-weight:600}
.note{flex:1;min-width:220px;padding:6px 8px;border-radius:8px;border:1px solid color-mix(in srgb,CanvasText 25%,Canvas);background:Canvas;color:CanvasText}
.saved{font-size:13px;color:#16a34a;min-height:18px}
kbd{font:12px ui-monospace,monospace;border:1px solid color-mix(in srgb,CanvasText 30%,Canvas);border-bottom-width:2px;border-radius:4px;padding:0 4px}
</style>
<header><div class="bar">
  <span class="prog">Đã chấm: <span id="done">0</span>/__N__</span>
  <button class="primary" onclick="nextUnreviewed()">Câu chưa chấm tiếp theo</button>
  <span class="saved" id="saved"></span>
</div>
<div style="font-size:13px;margin-top:6px;color:color-mix(in srgb,CanvasText 65%,Canvas)">
  Chấm: trích dẫn có <b>tự nó chống đỡ</b> câu trả lời không (không chấm đúng/sai).
  Phím tắt: <kbd>1</kbd> Có · <kbd>2</kbd> Không · <kbd>n</kbd> câu tiếp theo. Mỗi lần bấm tự lưu ngay.
</div></header>
<div id="items">__ITEMS__</div>
<script>
const N=__N__;
function countDone(){let c=0;for(let i=0;i<N;i++){if(document.querySelector('input[name="n'+i+'"]:checked'))c++;}document.getElementById('done').textContent=c;}
async function save(i){
  const el=document.getElementById('i'+i);
  const v=document.querySelector('input[name="n'+i+'"]:checked');
  const note=el.querySelector('.note').value;
  const body={dataset:el.dataset.ds,item_id:el.dataset.id,human_supports:v?v.value:'',note:note};
  el.classList.toggle('done',!!v);
  countDone();
  try{
    const r=await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok)throw new Error(await r.text());
    const s=document.getElementById('saved');s.textContent='đã lưu · '+new Date().toLocaleTimeString();
  }catch(e){document.getElementById('saved').textContent='LỖI lưu: '+e.message;}
}
for(let i=0;i<N;i++){
  const el=document.getElementById('i'+i);
  el.querySelectorAll('input[type=radio]').forEach(r=>r.addEventListener('change',()=>save(i)));
  el.querySelector('.note').addEventListener('change',()=>save(i));
  el.addEventListener('keydown',e=>{
    if(e.key==='1'){el.querySelector('input[value=yes]').checked=true;save(i);}
    else if(e.key==='2'){el.querySelector('input[value=no]').checked=true;save(i);}
    else if(e.key==='n'){nextUnreviewed();}
  });
}
function nextUnreviewed(){
  for(let i=0;i<N;i++){const el=document.getElementById('i'+i);
    if(!el.querySelector('input[name="n'+i+'"]:checked')){el.scrollIntoView({behavior:'smooth',block:'start'});el.focus();return;}}
  document.getElementById('saved').textContent='đã chấm hết 60 câu';
}
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT')return;
  if(e.key==='n')nextUnreviewed();
});
countDone();
</script></html>"""


def make_handler(sheet: list[dict], labels_path: Path, store: dict[str, dict],
                 lock: threading.Lock) -> type[BaseHTTPRequestHandler]:
    """The request handler class, built around one shared sheet + label store.
    Extracted so tests can drive the real HTTP surface on an ephemeral port."""
    keys = {f"{r['dataset']}:{r['item_id']}" for r in sheet}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            if self.path not in ("/", "/index.html"):
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            with lock:
                page = render_page(sheet, store)
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/label":
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length) or b"{}")
                key = f"{data['dataset']}:{data['item_id']}"
                if key not in keys:
                    raise ValueError(f"unknown sheet item {key}")
                with lock:
                    upsert_label(store, data["dataset"], data["item_id"],
                                 data.get("human_supports", ""), data.get("note", ""))
                    write_labels(labels_path, store, sheet)
                    done = sum(1 for v in store.values() if v["human_supports"] in VALID_VALUES)
                self._send(200, json.dumps({"saved": done}).encode(), "application/json")
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                self._send(400, str(e).encode("utf-8"), "text/plain; charset=utf-8")

        def log_message(self, *a) -> None:  # keep the terminal quiet
            pass

    return Handler


def serve(sheet: list[dict], labels_path: Path, store: dict[str, dict], port: int) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port),
                              make_handler(sheet, labels_path, store, threading.Lock()))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"labeler: {url}\n  sheet  : {len(sheet)} items\n  labels : {labels_path} (auto-saved)")
    srv.serve_forever()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the browser")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    sheet = load_sheet(args.sheet)
    if not sheet:
        raise SystemExit(f"Error: empty sheet: {args.sheet}")
    store = load_labels(args.labels)
    known = {f"{r['dataset']}:{r['item_id']}" for r in sheet}
    unknown = sorted(set(store) - known)
    if unknown:
        raise SystemExit(f"Error: labels file has rows not in the sheet: {unknown[:5]}")
    args.labels.parent.mkdir(parents=True, exist_ok=True)
    if args.open:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(
            f"http://127.0.0.1:{args.port}/")).start()
    serve(sheet, args.labels, store, args.port)


if __name__ == "__main__":
    main()
