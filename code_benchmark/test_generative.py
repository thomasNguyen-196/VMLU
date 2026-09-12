import os
import sys
import csv
import json
import time
import re
import argparse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, PermissionDeniedError

load_dotenv()

# --------------------------------------------------------------------------- #
# Robustness constants (llama.cpp host quirks)                                  #
# --------------------------------------------------------------------------- #
# The host (llama.cpp + systemctl, model auto-unloads when idle) is known for:
#   1. 503 "Service start timed out"  — cold start after idle unload (most common)
#   2. 503 "Loading model"            — warm-up in progress
#   3. request timeout/abort on long multi-turn Dialog sessions
#   4. no native reasoning — every reasoning param is ignored, CoT is prompt-based
# Mitigations: patient warm-up probe, progressive-backoff retries, per-request
# timeout, keep-alive pinger, and per-turn Dialog checkpointing.

BACKOFF_BASE_SEC = 10   # first retry waits 10s, then 20s, 40s, capped at 60s
BACKOFF_CAP_SEC = 60

CHECKPOINT_GLOB = "generative_raw_result_*.jsonl"
CHECKPOINT_NAME = "generative_raw_result_latest.jsonl"

# --------------------------------------------------------------------------- #
# CLI                                                                           #
# --------------------------------------------------------------------------- #
def parse_args():
    parser = argparse.ArgumentParser(
        description="Generative inference on VMLU (Vi-SQuAD / Vi-DROP / Vi-Dialog) via Ollama / OpenAI-compatible endpoint."
    )
    parser.add_argument("--task", type=str, required=True, choices=["squad", "drop", "dialog"],
                        help="Which generative benchmark to run.")
    parser.add_argument("--folder", type=str, default="./vmlu_generative",
                        help="Path to data folder containing the task JSON file (default: ./vmlu_generative)")
    parser.add_argument("--file", type=str, default=None,
                        help="JSON filename (default: auto-picked per task)")
    parser.add_argument("--strategy", type=str, default="baseline", choices=["baseline", "cot", "fewshot"],
                        help="Inference strategy: baseline (0-shot), cot (prompt-based CoT, DROP only), fewshot.")
    parser.add_argument("--few-shot-file", type=str, default=None,
                        help="JSON file with few-shot examples (required when --strategy fewshot).")
    parser.add_argument("--run-tag", type=str, default="",
                        help="Suffix for result/log/submission files so different strategies can coexist "
                             "(e.g. --run-tag cot -> all_res/generative_drop_cot, submission_drop_cot.csv).")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature (default: 0.0)")
    parser.add_argument("--seed", type=int, default=42, help="Seed for reproducibility (default: 42)")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="Max new tokens (default: 256, auto-raised to 512 for --strategy cot).")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers (default: 4)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to evaluate (must be > 0)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint (skips completed ids; "
                                                              "Dialog conversations resume mid-way from completed turns).")
    parser.add_argument("--finalize-only", action="store_true",
                        help="Skip inference entirely: rebuild submissions/full_evaluation from checkpoints (offline).")
    parser.add_argument("--max-retries", type=int, default=30,
                        help="Retries per request for transient errors, progressive backoff 10s->60s (default: 30).")
    parser.add_argument("--request-timeout", type=int, default=300,
                        help="Per-request HTTP timeout in seconds (default: 300 — Dialog turns can be slow).")
    parser.add_argument("--warmup-minutes", type=int, default=15,
                        help="Minutes to keep probing at startup until the cold server answers (default: 15).")
    parser.add_argument("--keep-alive-sec", type=int, default=240,
                        help="Seconds between 1-token keep-alive pings so the model is never idled into an "
                             "unload mid-run (0 disables, default: 240).")
    parser.add_argument("--verbose", action="store_true", help="Print per-item / per-turn progress to stdout")
    parser.add_argument("--model", type=str, default=None, help="Model name (overrides OPENAI_MODEL)")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL (overrides OPENAI_BASE_URL)")
    parser.add_argument("--api-key", type=str, default=None, help="API key (overrides OPENAI_API_KEY)")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be an integer greater than 0.")
    if args.limit is not None and args.finalize_only:
        parser.error("--finalize-only ignores --limit (it always finalizes the full dataset).")
    if args.strategy == "fewshot" and not args.few_shot_file:
        parser.error("--strategy fewshot requires --few-shot-file.")
    return args

def effective_max_tokens(strategy: str, requested: int | None) -> int:
    """CoT answers are long ('Bước 1/2/... Kết luận'); 256 would truncate them."""
    if requested is not None:
        return requested
    return 512 if strategy == "cot" else 256

# --------------------------------------------------------------------------- #
# Prompt building                                                              #
# --------------------------------------------------------------------------- #
# Prompts are taken verbatim from the VMLU ACL 2025 paper (Appendix B).
# CoT (chain-of-thought) is prompt-based because the hosted model (Qwen2.5-7B/8B
# Instruct GGUF) has NO native reasoning capability — the host ignores every
# reasoning param (enable_thinking, reasoning, reasoning_format,
# chat_template_kwargs, think) and never returns reasoning_content/<think>.
# The paper's authors use the same prompt-engineering technique.

# Vi-SQuAD — Table 12 (no-CoT, extractive, short answer)
SQUAD_PROMPT = (
    "Hãy trả lời câu hỏi dựa vào nội dung đoạn văn / văn bản. Yêu cầu:\n"
    "- Câu trả lời phải rất ngắn gọn được trích ra từ văn bản. Chỉ sử dụng thông tin trong văn bản được cung cấp.\n"
    "- Với những câu hỏi về số liệu, người, thời gian, ... thì câu trả lời có thể là một từ hoặc cụm từ.\n"
    "- Nếu trong văn bản không có câu trả lời, hoặc nội dung đoạn văn không liên quan thì output 'NO ANSWER'.\n"
    "Văn bản:\n{context}\n"
    "Câu hỏi: {question}\n"
    "Câu trả lời:"
)

# Vi-DROP — Table 14 (no-CoT)
DROP_NO_COT = (
    "#Task:\n"
    "Dựa vào đoạn văn, hãy trả lời câu hỏi sau. Chỉ cung cấp câu trả lời ngắn gọn không giải thích gì thêm.\n"
    "# Input:\n"
    "Đoạn văn:\n"
    "====\n"
    "{context}\n"
    "====\n"
    "Câu hỏi: {question}\n"
    "#Output:"
)

# Vi-DROP — Table 13 (CoT)
DROP_COT = (
    "# Task:\n"
    "Dựa vào đoạn văn, hãy trả lời câu hỏi sau bằng cách đưa ra lời giải thích cụ thể từng bước. "
    "Nếu là so sánh hơn kém, hơn nhất, hãy đưa ra các biểu thức so sánh mới kết luận.\n"
    "# Output format:\n"
    "Bước 1:\n"
    "...\n"
    "Bước 2:\n"
    "...\n"
    "Kết luận:\n"
    "...\n"
    "Đoạn văn:\n"
    "====\n"
    "{context}\n"
    "====\n"
    "Câu hỏi: {question}\n"
    "# Output:"
)

def build_extractive_prompt(item: dict, strategy: str) -> str:
    """Return the prompt for squad/drop according to the paper's template.
    CoT is only defined for DROP in the paper; SQuAD stays no-CoT."""
    ctx = item.get("context", "")
    q = item.get("question", "")
    if item.get("_task") == "drop":
        return DROP_COT.format(context=ctx, question=q) if strategy == "cot" else DROP_NO_COT.format(context=ctx, question=q)
    # squad (and any other extractive task) -> Table 12, always no-CoT
    return SQUAD_PROMPT.format(context=ctx, question=q)

def build_fewshot_messages(examples: list, item: dict, strategy: str) -> list:
    """Prepend a few (context, question, answer) demonstrations as user/assistant pairs."""
    messages = []
    for ex in examples:
        messages.append({"role": "user", "content": build_extractive_prompt(ex, strategy)})
        messages.append({"role": "assistant", "content": str(ex.get("answer", "")).strip()})
    messages.append({"role": "user", "content": build_extractive_prompt(item, strategy)})
    return messages

# --------------------------------------------------------------------------- #
# Model call (with progressive-backoff retry)                                   #
# --------------------------------------------------------------------------- #
def backoff_sleep(attempt: int, base_sec: int = BACKOFF_BASE_SEC, cap_sec: int = BACKOFF_CAP_SEC) -> int:
    """10s, 20s, 40s, then capped at 60s — long enough for a systemctl cold
    restart + model load, short enough not to stall a batch."""
    return min(cap_sec, base_sec * (2 ** (attempt - 1)))

def call_model_with_retry(client: OpenAI, model: str, messages: list, temperature: float,
                          seed: int, max_tokens: int,
                          max_retries: int = 30, base_sec: int = BACKOFF_BASE_SEC,
                          cap_sec: int = BACKOFF_CAP_SEC) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if seed is not None:
                kwargs["seed"] = seed
            if os.getenv("OPENAI_REASONING_EFFORT"):
                kwargs["extra_body"] = {
                    "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT")
                }
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            return content if content is not None else ""
        except (AuthenticationError, PermissionDeniedError) as auth_err:
            logging.error(f"Fatal authentication/permission error: {auth_err}")
            raise auth_err
        except Exception as e:
            err_str = str(e).lower()
            if "unauthorized" in err_str or "401" in err_str or "forbidden" in err_str or "403" in err_str:
                logging.error(f"Fatal authentication error detected: {e}")
                raise e
            # Everything else (503 cold start / loading model, timeouts, aborts,
            # connection resets) is transient on this host -> progressive backoff.
            sleep_sec = backoff_sleep(attempt, base_sec, cap_sec)
            logging.warning(f"Transient error on attempt {attempt}/{max_retries} "
                            f"({type(e).__name__}): {e} — retrying in {sleep_sec}s")
            if attempt < max_retries:
                time.sleep(sleep_sec)
            else:
                logging.error(f"Failed after {max_retries} attempts — returning empty answer.")
                return ""
    return ""

def warm_up_endpoint(client: OpenAI, model: str, minutes: int = 15, probe_every: int = 30) -> None:
    """Probe with 1-token pings until the server actually answers.
    Covers the two cold-start 503s of the llama.cpp host: 'Service start timed
    out' (systemctl restart after idle unload) and 'Loading model' (warm-up).
    Runs at the start of every batch, because 30-minute idle gaps guarantee the
    model has been unloaded."""
    deadline = time.time() + minutes * 60
    attempt = 0
    while True:
        attempt += 1
        try:
            client.chat.completions.create(model=model, messages=[{"role": "user", "content": "ping"}],
                                           max_tokens=1, temperature=0.0)
            logging.info(f"Endpoint is warm (probe {attempt}).")
            return
        except Exception as e:
            logging.warning(f"Warm-up probe {attempt} failed ({type(e).__name__}): {e}")
            if time.time() >= deadline:
                print(f"\n[FATAL] Endpoint still not answering after {minutes} minutes ({attempt} probes).\n"
                      f"Last error: {e}\n"
                      "Check the llama.cpp service (systemctl status) and OPENAI_BASE_URL / OPENAI_MODEL.",
                      file=sys.stderr)
                sys.exit(1)
            time.sleep(probe_every)

class KeepAlivePinger(threading.Thread):
    """1-token ping every `interval` seconds while a batch runs, so the server
    never idles into an unload mid-run (the known cause of Dialog sessions
    dying between turns)."""
    def __init__(self, client: OpenAI, model: str, interval: int):
        super().__init__(daemon=True, name="keep-alive-pinger")
        self.client = client
        self.model = model
        self.interval = interval
        self._stop = Event()

    def run(self):
        while not self._stop.wait(self.interval):
            try:
                self.client.chat.completions.create(model=self.model,
                                                    messages=[{"role": "user", "content": "ping"}],
                                                    max_tokens=1, temperature=0.0)
                logging.debug("Keep-alive ping OK.")
            except Exception as e:
                logging.warning(f"Keep-alive ping failed (worker requests will retry anyway): {e}")

    def stop(self):
        self._stop.set()

# --------------------------------------------------------------------------- #
# Data loading                                                                 #
# --------------------------------------------------------------------------- #
DEFAULT_FILES = {"squad": "vi_squad_benchmark_question_only.json",
                 "drop": "vi_drop_benchmark_3309_question_only.json",
                 "dialog": "vi_dialogue_question_only.json"}

def load_task_items(task: str, folder: Path, file_name: str, limit: int | None) -> list:
    """Returns a list of dicts:
       - squad/drop: {"id", "context", "question", "_task"}
       - dialog:     {"id", "turns": [str, ...], "_task"}
    """
    file_path = folder / file_name
    if not file_path.exists():
        alt = Path("..") / folder / file_name
        file_path = alt if alt.exists() else file_path
    if not file_path.exists():
        print(f"Error: Data file not found at '{folder / file_name}'.", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        blob = json.load(f)

    raw = blob.get("data", blob) if isinstance(blob, dict) else blob
    items = []
    if task in ("squad", "drop"):
        for i, d in enumerate(raw):
            qid = d.get("question_id", d.get("id", i))
            items.append({"id": str(qid), "_task": task,
                          "context": d.get("context", ""), "question": d.get("question", "")})
    else:  # dialog
        for d in raw:
            items.append({"id": str(d.get("id")), "_task": task, "turns": d.get("queries", [])})
    if limit:
        items = items[:limit]
    return items

def normalize_record(task: str, item: dict, rec: dict) -> dict | None:
    """Bring a checkpoint record in line with the current format; None means the
    record is unusable (legacy Dialog rows without 'replies') and the item must
    be re-run."""
    if task == "dialog":
        replies = rec.get("replies")
        if not isinstance(replies, list):
            return None
        replies = [str(r) for r in replies][:len(item["turns"])]
        return {"id": str(item["id"]), "replies": replies,
                "done": bool(rec.get("done")) and len(replies) == len(item["turns"])}
    return {"id": str(item["id"]), "answer": str(rec.get("answer", "")),
            "question": str(rec.get("question", item.get("question", ""))),
            "context": str(rec.get("context", item.get("context", "")))}

# --------------------------------------------------------------------------- #
# Checkpoint (single atomic JSONL — safe for free-form text)                    #
# --------------------------------------------------------------------------- #
def _checkpoint_sort_key(p: Path):
    """Numbered legacy snapshots first (ascending), '_latest' last (it wins)."""
    m = re.search(r"generative_raw_result_(\d+)\.jsonl", p.name)
    return (int(m.group(1)) if m else float("inf"), p.name)

def load_checkpoint(cp_dir: Path) -> dict:
    """Merge every snapshot on disk, keyed by id. All snapshots are full copies,
    so the merge is idempotent; '_latest' (newest) is read last and wins.
    Keeps --resume compatible with the old numbered-snapshot files."""
    done = {}
    for p in sorted(cp_dir.glob(CHECKPOINT_GLOB), key=_checkpoint_sort_key):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        done[str(rec["id"])] = rec
        except (json.JSONDecodeError, OSError) as e:
            logging.warning(f"Skipping unreadable checkpoint {p.name}: {e}")
    return done

def write_checkpoint(cp_dir: Path, records: list) -> Path:
    """Atomic rewrite of the single '_latest' snapshot (tmp file + os.replace),
    so a crash can never leave a half-written checkpoint behind."""
    out = cp_dir / CHECKPOINT_NAME
    tmp = out.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, out)
    return out

# --------------------------------------------------------------------------- #
# Dialog helpers                                                                #
# --------------------------------------------------------------------------- #
def dialog_messages(queries: list, replies: list) -> list:
    """Rebuild the [user, assistant, user, ..., user] message list for the next
    unanswered turn — this is what makes mid-conversation resume possible:
    `replies` holds the assistant turns already completed (and checkpointed)."""
    messages = []
    for i, q in enumerate(queries):
        messages.append({"role": "user", "content": q})
        if i >= len(replies):
            break
        messages.append({"role": "assistant", "content": replies[i]})
    return messages

def extract_cot_final(text: str) -> str:
    """Pull the short final answer out of a DROP CoT response: the first
    non-empty line after the LAST 'Kết luận:' marker; falls back to the last
    non-empty line of the raw output."""
    if "Kết luận:" in text:
        tail = text.rsplit("Kết luận:", 1)[1]
        lines = [l.strip() for l in tail.splitlines() if l.strip()]
        if lines:
            return lines[0]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[-1] if lines else ""

def _write_csv(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["id", "answer"])
        for row in rows:
            w.writerow(row)

def write_final_outputs(task: str, run_suffix: str, strategy: str, result_folder: Path, records: list) -> None:
    write_checkpoint(result_folder, records)
    full_df_path = result_folder / f"full_evaluation_{task}{run_suffix}.jsonl"
    with open(full_df_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if task in ("squad", "drop"):
        sub_path = f"submission_{task}{run_suffix}.csv"
        _write_csv(sub_path, [(r["id"], r["answer"]) for r in records])
        logging.info(f"Submission saved to {sub_path} ({len(records)} rows).")
        if task == "drop" and strategy == "cot":
            extracted_path = f"submission_drop{run_suffix}_extracted.csv"
            _write_csv(extracted_path, [(r["id"], extract_cot_final(r["answer"])) for r in records])
            logging.info(f"CoT-extracted submission saved to {extracted_path} ({len(records)} rows).")
    else:  # dialog
        per_turn, last_reply = [], []
        for r in records:
            replies = r.get("replies", [])
            for t_idx, reply in enumerate(replies, start=1):
                per_turn.append((f"{r['id']}_{t_idx}", reply))
            if r.get("done") and replies:
                last_reply.append((r["id"], replies[-1]))
        _write_csv(f"submission_dialog{run_suffix}.csv", per_turn)
        _write_csv(f"submission_dialog{run_suffix}_last.csv", last_reply)
        logging.info(f"Dialog submissions saved: submission_dialog{run_suffix}.csv "
                     f"({len(per_turn)} turn rows), submission_dialog{run_suffix}_last.csv "
                     f"({len(last_reply)} completed conversations).")

# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or "ollama"
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    model = args.model or os.environ.get("OPENAI_MODEL")
    if not args.finalize_only:
        if not base_url:
            print("Error: OPENAI_BASE_URL is not set.", file=sys.stderr)
            sys.exit(1)
        if not model:
            print("Error: OPENAI_MODEL is not set.", file=sys.stderr)
            sys.exit(1)

    run_suffix = f"_{args.run_tag.strip()}" if args.run_tag.strip() else ""
    file_name = args.file or DEFAULT_FILES[args.task]
    max_tokens = effective_max_tokens(args.strategy, args.max_tokens)
    result_folder = Path(f"all_res/generative_{args.task}{run_suffix}")
    result_folder.mkdir(parents=True, exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/generative_{args.task}{run_suffix}.log"
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s: %(message)s')
    logging.getLogger('').addHandler(logging.StreamHandler())

    items = load_task_items(args.task, Path(args.folder), file_name,
                            None if args.finalize_only else args.limit)
    done = load_checkpoint(result_folder)
    logging.info(f"Loaded {len(items)} items for task={args.task} strategy={args.strategy} "
                 f"max_tokens={max_tokens}; checkpoint has {len(done)} records.")

    if args.finalize_only:
        records, missing = [], 0
        for it in items:
            rec = done.get(str(it["id"]))
            if rec is None:
                missing += 1
                continue
            norm = normalize_record(args.task, it, rec)
            if norm is not None:
                records.append(norm)
        if missing:
            logging.warning(f"Finalize-only: {missing} items have no usable checkpoint record — "
                            f"they are absent from the submissions.")
        write_final_outputs(args.task, run_suffix, args.strategy, result_folder, records)
        logging.info(f"Finalize-only complete: {len(records)} records written (no network access).")
        return

    client = OpenAI(base_url=base_url, api_key=api_key,
                    timeout=args.request_timeout, max_retries=0)
    # NOTE: no native-reasoning params are ever sent — the host ignores them all
    # (enable_thinking, reasoning, reasoning_format, chat_template_kwargs, think).
    # CoT is prompt-based per the paper (DROP only).
    if args.strategy == "cot" and args.task not in ("drop",):
        logging.warning(f"[CoT] Paper only defines prompt-CoT for DROP (Vi-MQA not in this script). "
                        f"Task '{args.task}' will run with its no-CoT template.")
    if args.strategy == "cot":
        logging.info("[CoT] Using paper prompt-based chain-of-thought (no native reasoning on this host).")

    logging.info(f"Warming up endpoint (covers systemctl cold start / 'Loading model' 503s, "
                 f"up to {args.warmup_minutes} min)...")
    warm_up_endpoint(client, model, minutes=args.warmup_minutes)
    logging.info("Endpoint ready.")

    pinger = None
    if args.keep_alive_sec > 0:
        pinger = KeepAlivePinger(client, model, args.keep_alive_sec)
        pinger.start()
        logging.info(f"Keep-alive pinger started (every {args.keep_alive_sec}s).")

    lock = Lock()
    try:
        run_inference(args, client, model, max_tokens, items, done, result_folder, lock)
    finally:
        if pinger:
            pinger.stop()

def run_inference(args, client: OpenAI, model: str, max_tokens: int,
                  items: list, done: dict, result_folder: Path, lock: Lock) -> None:
    run_suffix = f"_{args.run_tag.strip()}" if args.run_tag.strip() else ""
    few_shot_examples = []
    if args.strategy == "fewshot":
        with open(args.few_shot_file, "r", encoding="utf-8") as f:
            few_shot_examples = json.load(f)
        logging.info(f"[Few-shot] Loaded {len(few_shot_examples)} demonstrations.")

    # Seed in-order results from the checkpoint so final outputs always contain
    # every completed item, not just the ones processed in this session.
    results = [None] * len(items)
    for i, it in enumerate(items):
        rec = done.get(str(it["id"]))
        if rec is not None:
            results[i] = normalize_record(args.task, it, rec)

    if args.task == "dialog":
        to_process = [(i, it) for i, it in enumerate(items)
                      if results[i] is None or not results[i]["done"]]
        for i, it in to_process:
            if results[i] is None:
                results[i] = {"id": str(it["id"]), "replies": [], "done": False}
            it["_replies"] = results[i]["replies"]
        units_total = sum(len(it["turns"]) for it in items)
        units_done = sum(len(r["replies"]) for r in results if r)
    else:
        to_process = [(i, it) for i, it in enumerate(items) if results[i] is None]
        units_total = len(items)
        units_done = len(items) - len(to_process)

    if units_done:
        logging.info(f"Resuming: {units_done}/{units_total} units already completed.")
    if not to_process:
        logging.info("All items already resolved from checkpoint.")

    completed = units_done
    last_flush = time.time()
    start = time.time()

    def process_item(index: int, item: dict) -> int:
        nonlocal completed, last_flush
        if args.task == "dialog":
            queries = item["turns"]
            replies = list(item.get("_replies", []))
            if args.verbose:
                logging.info(f"[Dialog {item['id']}] {len(queries)} turns, "
                             f"{len(replies)} already done from checkpoint")
            while len(replies) < len(queries):
                messages = dialog_messages(queries, replies)
                if args.verbose:
                    logging.info(f"[Dialog {item['id']}] -> API call turn {len(replies)+1}/{len(queries)} "
                                 f"(history msgs={len(messages)})")
                reply = call_model_with_retry(client, model, messages, args.temperature,
                                              args.seed, max_tokens, args.max_retries)
                reply = reply.strip()
                if not reply:
                    # Retry window exhausted — keep the completed turns as a
                    # partial checkpoint record and stop this conversation; the
                    # next --resume run picks it up from this exact turn.
                    raise RuntimeError(
                        f"[Dialog {item['id']}] empty reply at turn {len(replies)+1}/{len(queries)} "
                        f"— conversation left partial for resume (server likely down).")
                replies.append(reply)
                with lock:
                    results[index] = {"id": str(item["id"]), "replies": list(replies),
                                      "done": len(replies) == len(queries)}
                    completed += 1
                    # per-turn snapshot: a mid-conversation crash loses nothing
                    write_checkpoint(result_folder, [r for r in results if r])
                if args.verbose:
                    logging.info(f"[Dialog {item['id']}] <- turn {len(replies)} reply ({len(reply)} chars)")
            return len(replies) - len(item.get("_replies", []))

        # squad / drop
        if args.strategy == "fewshot":
            messages = build_fewshot_messages(few_shot_examples, item, args.strategy)
        else:
            messages = [{"role": "user", "content": build_extractive_prompt(item, args.strategy)}]
        if args.verbose:
            logging.info(f"[{args.task} {item['id']}] -> API call (1 msg, {len(messages[0]['content'])} chars prompt)")
        answer = call_model_with_retry(client, model, messages, args.temperature,
                                       args.seed, max_tokens, args.max_retries).strip()
        if args.verbose:
            logging.info(f"[{args.task} {item['id']}] <- reply ({len(answer)} chars)")
        rec = {"id": str(item["id"]), "answer": answer,
               "question": item.get("question", ""), "context": item.get("context", "")}
        with lock:
            results[index] = rec
            completed += 1
            now = time.time()
            # flush on the 100 milestone, at the end, AND at least once a minute —
            # a hard kill (SIGKILL) skips the finally-block, so long gaps between
            # milestone writes would lose completed work
            if completed % 100 == 0 or completed == units_total or now - last_flush >= 60:
                write_checkpoint(result_folder, [r for r in results if r])
                last_flush = now
        return 1

    if to_process:
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(process_item, i, it): i for i, it in to_process}
                with tqdm(total=units_total, initial=units_done,
                          desc=f"{args.task}{run_suffix}/{model}") as pbar:
                    for fut in as_completed(futs):
                        pbar.update(fut.result())
        finally:
            # safety net: persist whatever finished, even on Ctrl+C / abort
            with lock:
                write_checkpoint(result_folder, [r for r in results if r])

    valid = [r for r in results if r]
    if args.task == "dialog":
        incomplete = sum(1 for r in valid if not r["done"])
        if incomplete:
            logging.warning(f"{incomplete} conversation(s) incomplete — rerun with --resume to finish them.")
    write_final_outputs(args.task, run_suffix, args.strategy, result_folder, valid)
    logging.info(f"Done. {len(valid)} records. Time: {time.time()-start:.1f}s")

if __name__ == "__main__":
    main()
