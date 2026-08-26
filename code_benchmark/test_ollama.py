import os
import sys
import json
import time
import re
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, PermissionDeniedError

load_dotenv()

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate models via Ollama / OpenAI-compatible endpoint on VMLU benchmark.")
    parser.add_argument("--folder", type=str, default="./vmlu", help="Path to data folder containing test.jsonl (default: ./vmlu)")
    parser.add_argument("--file", type=str, default="test.jsonl", help="JSONL filename (default: test.jsonl)")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature (default: 0.0)")
    parser.add_argument("--seed", type=int, default=42, help="Seed for reproducibility (default: 42)")
    parser.add_argument("--max-tokens", type=int, default=4, help="Max new tokens to generate (default: 4)")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers (default: 4)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of questions to evaluate (must be > 0)")
    parser.add_argument("--resume", action="store_true", help="Resume from the latest raw_result_*.csv checkpoint in all_res/ollama_result/")
    parser.add_argument("--model", type=str, default=None, help="Model name (overrides OPENAI_MODEL env var)")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL for OpenAI-compatible endpoint (overrides OPENAI_BASE_URL)")
    parser.add_argument("--api-key", type=str, default=None, help="API key (overrides OPENAI_API_KEY)")
    
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be an integer greater than 0.")
    return args

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

def call_model_with_retry(client: OpenAI, model: str, prompt: str, temperature: float, seed: int, max_tokens: int, max_retries: int = 30, sleep_sec: int = 30) -> str:
    messages = [{"role": "user", "content": prompt}]
    for attempt in range(1, max_retries + 1):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if seed is not None:
                kwargs["seed"] = seed

            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            return content if content is not None else ""
        except (AuthenticationError, PermissionDeniedError) as auth_err:
            logging.error(f"Fatal authentication/permission error: {auth_err}")
            raise auth_err
        except Exception as e:
            err_str = str(e).lower()
            if "unauthorized" in err_str or "401" in err_str or "forbidden" in err_str or "403" in err_str:
                logging.error(f"Fatal authentication error detected in response: {e}")
                raise e
            logging.warning(f"Error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(sleep_sec)
            else:
                logging.error(f"Failed after {max_retries} attempts: {prompt[:100]}...")
                return ""
    return ""

def verify_credentials(client: OpenAI, model: str):
    """Probe endpoint with 1 test token to fail-fast on auth/model errors."""
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0
        )
    except Exception as e:
        print(f"\n[FATAL] Endpoint probe failed for model '{model}'.\nError: {e}\nPlease check OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL.", file=sys.stderr)
        sys.exit(1)

def find_latest_checkpoint(checkpoint_dir: Path) -> Path | None:
    files = list(checkpoint_dir.glob("raw_result_*.csv"))
    if not files:
        return None
    def get_count(p: Path):
        m = re.search(r'raw_result_(\d+)\.csv', p.name)
        return int(m.group(1)) if m else 0
    return max(files, key=get_count)

def main():
    args = parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or "ollama"
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    model = args.model or os.environ.get("OPENAI_MODEL")

    if not base_url:
        print("Error: OPENAI_BASE_URL is not set. Please provide --base-url or set OPENAI_BASE_URL in .env", file=sys.stderr)
        sys.exit(1)

    if not model:
        print("Error: OPENAI_MODEL is not set. Please provide --model or set OPENAI_MODEL in .env", file=sys.stderr)
        sys.exit(1)

    os.makedirs("logs", exist_ok=True)
    result_folder = Path("all_res/ollama_result")
    result_folder.mkdir(parents=True, exist_ok=True)

    sanitized_model = re.sub(r'[^a-zA-Z0-9_-]', '_', model)
    log_file = f"logs/{sanitized_model}.log"
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s: %(message)s'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)

    logging.info(f"Model: {model}")
    logging.info(f"Base URL: {base_url}")
    logging.info(f"Concurrency: {args.workers} workers")

    client = OpenAI(base_url=base_url, api_key=api_key)

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

    for doc in data:
        doc["prompt"] = build_prompt(doc["question"], doc.get("choices", []))

    # Checkpoint resume support
    existing_answers = {}
    if args.resume:
        latest_cp = find_latest_checkpoint(result_folder)
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

    results = [None] * total_questions
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
                pd.DataFrame(valid_res).to_csv(result_folder / f"raw_result_{len(valid_res)}.csv", index=False)

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
    df_all.to_csv(result_folder / f"full_evaluation_{sanitized_model}.csv", index=False)

    submission_df = df_all[["id", "answer"]]
    submission_path = "submission.csv"
    submission_df.to_csv(submission_path, index=False)
    logging.info(f"Submission saved to {submission_path}")

if __name__ == "__main__":
    main()
