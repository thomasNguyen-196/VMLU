"""VMLU multiple-choice evaluation runner (the frozen A-E pipeline).

Formerly test_ollama.py — renamed because it is a runner, not a test file
(the test_ prefix is a pytest landmine; it pairs with run_reading_eval.py).

Consumes vmlu_mqa_v1.5-style JSONL ({id, question, choices[], answer?}) via
any OpenAI-compatible endpoint; writes checkpoints + finals under
all_res/ollama_result/ and submission.csv at the repo root. build_prompt /
extract_answer below are BYTE-FROZEN contracts shared with the legacy scripts
and the standalone parity reference (test_parsing.py) — never "deduplicate"
them against each other.

Run from repo root:
  .venv/bin/python code_benchmark/run_mc_eval.py --folder ./vmlu_mqa_v1.5 --workers 4
"""
import re
import sys
import json
import time
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

try:  # package run (repo root) or direct run (cwd == code_benchmark)
    from code_benchmark.common import (sanitize_model, resolve_endpoint, RESULTS_DIR,
                                       add_endpoint_args, parse_endpoint_args, setup_logging)
    from code_benchmark.checkpoint import checkpoint_name, find_latest_checkpoint
    from code_benchmark.llm import build_client, verify_credentials, call_model_with_retry
except ImportError:
    from common import (sanitize_model, resolve_endpoint, RESULTS_DIR,
                        add_endpoint_args, parse_endpoint_args, setup_logging)
    from checkpoint import checkpoint_name, find_latest_checkpoint
    from llm import build_client, verify_credentials, call_model_with_retry

load_dotenv()

# Official VMLU subject numbering (ZaloAI-Jaist/VMLU README, dataset v1.5):
# id prefix "XX-YYYY" -> (subject name, category). 21 STEM / 10 Social Science /
# 18 Humanity / 9 Other. NOTE: repo-root dataset_stat.csv lists a DIFFERENT
# ordering — the id prefixes follow this table, verified against dev/valid records.
SUBJECTS: dict[int, tuple[str, str]] = {
    # 01-21 STEM
    1: ("Elementary Mathematics", "STEM"), 2: ("Elementary Science", "STEM"),
    3: ("Middle School Biology", "STEM"), 4: ("Middle School Chemistry", "STEM"),
    5: ("Middle School Mathematics", "STEM"), 6: ("Middle School Physics", "STEM"),
    7: ("High School Biology", "STEM"), 8: ("High School Chemistry", "STEM"),
    9: ("High School Mathematics", "STEM"), 10: ("High School Physics", "STEM"),
    11: ("Applied Informatics", "STEM"), 12: ("Computer Architecture", "STEM"),
    13: ("Computer Network", "STEM"), 14: ("Discrete Mathematics", "STEM"),
    15: ("Electrical Engineering", "STEM"), 16: ("Introduction to Chemistry", "STEM"),
    17: ("Introduction to Physics", "STEM"), 18: ("Introduction to Programming", "STEM"),
    19: ("Metrology Engineer", "STEM"), 20: ("Operating System", "STEM"),
    21: ("Statistics and Probability", "STEM"),
    # 22-31 Social Science
    22: ("Middle School Civil Education", "Social Science"), 23: ("Middle School Geography", "Social Science"),
    24: ("High School Civil Education", "Social Science"), 25: ("High School Geography", "Social Science"),
    26: ("Business Administration", "Social Science"), 27: ("Ho Chi Minh Ideology", "Social Science"),
    28: ("Macroeconomics", "Social Science"), 29: ("Microeconomics", "Social Science"),
    30: ("Principles of Marxism and Leninism", "Social Science"), 31: ("Sociology", "Social Science"),
    # 32-49 Humanity
    32: ("Elementary History", "Humanity"), 33: ("Middle School History", "Humanity"),
    34: ("Middle School Literature", "Humanity"), 35: ("High School History", "Humanity"),
    36: ("High School Literature", "Humanity"), 37: ("Administrative Law", "Humanity"),
    38: ("Business Law", "Humanity"), 39: ("Civil Law", "Humanity"),
    40: ("Criminal Law", "Humanity"), 41: ("Economic Law", "Humanity"),
    42: ("Education Law", "Humanity"), 43: ("History of World Civilization", "Humanity"),
    44: ("Idealogical and Moral Cultivation", "Humanity"), 45: ("Introduction to Laws", "Humanity"),
    46: ("Introduction to Vietnam Culture", "Humanity"), 47: ("Logic", "Humanity"),
    48: ("Revolutionary Policy of the Vietnamese Commununist Part", "Humanity"),
    49: ("Vietnamese Language and Literature", "Humanity"),
    # 50-58 Other
    50: ("Accountant", "Other"), 51: ("Clinical Pharmacology", "Other"),
    52: ("Environmental Engineering", "Other"), 53: ("Internal Basic Medicine", "Other"),
    54: ("Preschool Pedagogy", "Other"), 55: ("Tax Accountant", "Other"),
    56: ("Tax Civil Servant", "Other"), 57: ("Civil Servant", "Other"),
    58: ("Driving License Certificate", "Other"),
}
CATEGORIES = ("STEM", "Social Science", "Humanity", "Other")

def subject_category(id_str: str) -> tuple[int | None, str, str]:
    """Map 'XX-YYYY' -> (subject number, subject name, category); unknown bucket for bad prefixes."""
    try:
        num = int(str(id_str).split("-")[0])
    except (ValueError, IndexError):
        return None, "unknown", "unknown"
    name, cat = SUBJECTS.get(num, ("unknown", "unknown"))
    return num, name, cat

def detect_scorable(records: list[dict]) -> tuple[bool, dict[str, str]]:
    """Pure check: scorable only when EVERY record carries a non-empty gold `answer`.
    Returns (scorable, gold_by_id). Mixed inputs -> (False, {}) (caller logs the warning)."""
    if not records:
        return False, {}
    with_gold = [r for r in records if str(r.get("answer", "")).strip()]
    if len(with_gold) == len(records):
        return True, {str(r["id"]): str(r["answer"]).strip().upper() for r in records}
    return False, {}

def score_row(res: dict, gold_by_id: dict[str, str]) -> dict:
    """Idempotently enrich one result row with gold_answer + correct (0/1).
    Unparseable model answer (empty) counts as incorrect but stays in the denominator."""
    gold = gold_by_id.get(str(res.get("id", "")), "")
    correct = 1 if (gold and str(res.get("answer", "")).strip().upper() == gold) else 0
    out = dict(res)
    out["gold_answer"] = gold
    out["correct"] = correct
    return out

def build_accuracy_rows(scored_rows: list[dict]) -> list[dict]:
    """Aggregate scored rows (long format: level, name, n, correct, accuracy).
    Category/subject sums always partition the total (unknown buckets kept explicit)."""
    from collections import defaultdict
    stats: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])  # (level,name) -> [n, correct]

    def add(level: str, name: str, row: dict):
        stats[(level, name)][0] += 1
        stats[(level, name)][1] += int(row.get("correct", 0))

    for row in scored_rows:
        add("overall", "overall", row)
        num, name, cat = subject_category(row.get("id", ""))
        add("category", cat, row)
        add("subject", f"{num:02d} {name}" if num else "unknown", row)

    def emit(level: str, name: str) -> dict:
        n, c = stats[(level, name)]
        return {"level": level, "name": name, "n": n, "correct": c,
                "accuracy": round(100.0 * c / n, 2) if n else 0.0}

    rows = [emit("overall", "overall")]
    seen_cats = {name for (level, name) in stats if level == "category"}
    for cat in CATEGORIES + tuple(("unknown",) if "unknown" in seen_cats else ()):
        if ("category", cat) in stats:
            rows.append(emit("category", cat))
    for (level, name) in sorted(stats):
        if level == "subject":
            rows.append(emit(level, name))
    return rows

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate models via Ollama / OpenAI-compatible endpoint on VMLU benchmark.")
    parser.add_argument("--folder", type=str, default="./vmlu", help="Path to data folder containing test.jsonl (default: ./vmlu)")
    parser.add_argument("--file", type=str, default="test.jsonl", help="JSONL filename (default: test.jsonl)")
    add_endpoint_args(parser, max_tokens_default=4,
                      max_tokens_help="Max new tokens to generate (default: 4)",
                      resume_help="Resume from the newest raw_result_<count>_<model>.csv checkpoint for THIS model in all_res/ollama_result/")
    parser.add_argument("--submission-out", type=str, default="submission.csv",
                        help="Path of the final id,answer submission CSV (default: ./submission.csv)")
    return parse_endpoint_args(parser)

def build_prompt(question: str, choices: list) -> str:
    text_choice = '\n'.join(str(c) for c in choices)
    prompt = (
        "Chỉ đưa ra chữ cái đứng trước câu trả lời đúng (A, B, C, D hoặc E) của câu hỏi trắc nghiệm sau: \n"
        + question
        + "\n\n"
        + text_choice
        + "\n"
        + "Đáp án: "
    )
    return prompt

def extract_answer(raw_text: str) -> str:
    if not raw_text:
        return ""
    raw = raw_text.strip()

    # 1. Exact match / start with single option (e.g. 'A', 'A.', 'A)', '(A)', '**A**')
    m = re.match(r'^(?:\*{1,2}|\()?\s*([A-Ea-e])\s*(?:\*{1,2}|\))?[\.\:\s]*$', raw)
    if m:
        return m.group(1).upper()

    # 2. Key phrases in Vietnamese & English
    m = re.search(r'(?:đáp án|câu trả lời|chọn|kết quả|answer|option|choice)\s*(?:là|đúng|chính xác|là:|:)?\s*[\*\(\[]*\s*([A-Ea-e])\b', raw, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # 3. Standalone uppercase letter A-E (e.g. '... is B ...' or '... (C) ...')
    m = re.search(r'(?<!\w)([A-E])(?!\w)', raw)
    if m:
        return m.group(1).upper()

    # 4. Standalone lowercase letter a-e surrounded by word boundaries
    m = re.search(r'(?<!\w)([a-e])(?!\w)', raw)
    if m:
        return m.group(1).upper()

    return ""

def main():
    args = parse_args()

    base_url, api_key, model = resolve_endpoint(args)

    result_folder = RESULTS_DIR
    result_folder.mkdir(parents=True, exist_ok=True)

    sanitized_model = sanitize_model(model)
    setup_logging(Path("logs") / f"{sanitized_model}.log")

    logging.info(f"Model: {model}")
    logging.info(f"Base URL: {base_url}")
    logging.info(f"Concurrency: {args.workers} workers")

    client = build_client(base_url, api_key)

    # Fail-fast probe
    logging.info("Verifying endpoint connectivity and credentials...")
    verify_credentials(client, model)
    logging.info("Credentials verified successfully.")

    data_dir = Path(args.folder)
    file_path = data_dir / args.file
    if not file_path.exists():
        alt_path = Path("..") / args.folder / args.file
        if alt_path.exists():
            file_path = alt_path
        else:
            print(f"Error: Data file not found at '{file_path}' or '{alt_path}'.", file=sys.stderr)
            sys.exit(1)

    data = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    if not data:
        print(f"Error: No questions found in '{file_path}'. File is empty.", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        data = data[:args.limit]

    total_questions = len(data)
    logging.info(f"Loaded {total_questions} questions from {file_path}")

    scorable, gold_by_id = detect_scorable(data)
    n_gold = sum(1 for r in data if str(r.get("answer", "")).strip())
    if scorable:
        logging.info("Input has gold answers for all questions -> accuracy scoring ENABLED.")
    elif n_gold:
        logging.warning(f"Mixed input ({n_gold}/{total_questions} with gold answers) -> scoring DISABLED (leaderboard-only mode).")

    for doc in data:
        doc["prompt"] = build_prompt(doc["question"], doc.get("choices", []))

    # Checkpoint resume support
    existing_answers = {}
    if args.resume:
        latest_cp = find_latest_checkpoint(result_folder, model)
        if latest_cp:
            logging.info(f"Resuming from checkpoint: {latest_cp}")
            cp_df = pd.read_csv(latest_cp)
            for _, row in cp_df.iterrows():
                if pd.notna(row.get("id")) and pd.notna(row.get("answer")):
                    existing_answers[str(row["id"])] = {
                        "id": str(row["id"]),
                        "question": row.get("question", ""),
                        "prompt": row.get("prompt", ""),
                        "raw_response": row.get("raw_response", ""),
                        "answer": str(row["answer"])
                    }
            logging.info(f"Loaded {len(existing_answers)} pre-existing answers from checkpoint.")
        else:
            others = sorted(result_folder.glob("raw_result_*.csv"))
            if others:
                logging.warning(
                    "No checkpoint found for model '%s' — the raw_result_*.csv files present "
                    "belong to other models or lack any model identity, so none can be resumed "
                    "safely. Starting fresh.", model)

    results: list[dict | None] = [None] * total_questions
    to_process = []

    for idx, item in enumerate(data):
        item_id = str(item["id"])
        if item_id in existing_answers:
            results[idx] = existing_answers[item_id]
        else:
            to_process.append((idx, item))

    logging.info(f"Questions remaining to evaluate: {len(to_process)}/{total_questions}")

    lock = Lock()
    completed_count = len(existing_answers)
    start_time = time.time()

    def process_item(index: int, item: dict):
        nonlocal completed_count
        raw_ans = call_model_with_retry(
            client=client,
            model=model,
            prompt=item["prompt"],
            temperature=args.temperature,
            seed=args.seed,
            max_tokens=args.max_tokens
        )
        parsed_ans = extract_answer(raw_ans)
        res = {
            "id": item["id"],
            "question": item["question"],
            "prompt": item["prompt"],
            "raw_response": raw_ans,
            "answer": parsed_ans
        }

        with lock:
            results[index] = res
            completed_count += 1
            current_completed = completed_count
            if current_completed % 100 == 0 or current_completed == total_questions:
                valid_res = [r for r in results if r is not None]
                pd.DataFrame(valid_res).to_csv(
                    result_folder / checkpoint_name(model, len(valid_res)), index=False)

        return index

    if to_process:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_item, idx, item): idx for idx, item in to_process}
            with tqdm(total=total_questions, initial=len(existing_answers), desc=f"Evaluating {model}") as pbar:
                for future in as_completed(futures):
                    future.result()
                    pbar.update(1)
    else:
        logging.info("All questions already resolved from checkpoint.")

    duration = time.time() - start_time
    logging.info(f"Time taken for running inference: {duration:.2f}s ({duration/60:.2f} mins)")

    df_all = pd.DataFrame(results)

    if scorable:
        scored = [score_row(r, gold_by_id) for r in results if r is not None]
        acc_rows = build_accuracy_rows(scored)
        df_all = pd.DataFrame(scored)
        acc_df = pd.DataFrame(acc_rows)
        acc_path = result_folder / f"accuracy_{sanitized_model}.csv"
        acc_df.to_csv(acc_path, index=False)
        overall = acc_rows[0]
        n_subjects = sum(1 for r in acc_rows if r["level"] == "subject")
        logging.info(f"Accuracy overall: {overall['correct']}/{overall['n']} = {overall['accuracy']:.2f}%")
        logging.info("Accuracy by category:")
        for r in acc_rows:
            if r["level"] == "category":
                logging.info(f"  {r['name']:<15} {r['correct']:>5}/{r['n']:<5} = {r['accuracy']:.2f}%")
        logging.info(f"Per-subject table ({n_subjects} subjects) written to {acc_path}")

    df_all.to_csv(result_folder / f"full_evaluation_{sanitized_model}.csv", index=False)

    submission_df = df_all[["id", "answer"]]
    submission_path = args.submission_out
    submission_df.to_csv(submission_path, index=False)
    logging.info(f"Submission saved to {submission_path}")

if __name__ == "__main__":
    main()
