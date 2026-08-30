# VMLU (Vietnamese Multitask Language Understanding)

Evaluation benchmark suite for Vietnamese language foundation models across 58 subjects (10,880 multiple-choice questions in STEM, Humanities, Social Sciences, and Other categories).

## Repository Overview

- `code_benchmark/`: Benchmark evaluation scripts
  - `test_ollama.py`: Standardized evaluation using Ollama / OpenAI-compatible endpoints with concurrency, retry, checkpoint snapshots & resume (`--resume`), and answer parsing.
  - `legacy/`: Historical evaluation scripts (`test_gpt.py`, `test_prompt.py`).
- `requirements.txt`: Python runtime dependencies
- `dataset_stat.csv` / `example_submission.csv`: Dataset statistics and submission sample format

## Commands

### Dependencies
```bash
pip install -r requirements.txt
```

### Run Ollama / OpenAI-compatible Benchmark
```bash
cd code_benchmark
python test_ollama.py --folder "./vmlu" --workers 4
```

### Run Legacy Scripts (isolated virtualenv with openai==0.28.0)
```bash
cd code_benchmark/legacy
python test_gpt.py
```

## Data & Formats

- Data format: JSONL files (`dev.jsonl`, `test.jsonl`) with objects containing `id`, `question`, `choices` (list of 4-5 options), and `answer` (A/B/C/D/E).
- Submission format: UTF-8 CSV with `id,answer` columns.
- Outputs & logs are stored in `logs/` or `code_benchmark/all_res/`.

## Code Intelligence

- Code intelligence tool order (mandatory): **CodeGraph first** (`codegraph_explore` MCP or `codegraph explore "<question>"` CLI — one call returns verbatim source + call path + blast radius; don't grep/read first) → context-mode (`ctx_search`/`ctx_execute`) → grep/read/glob last (configs, docs, dataset files, or confirming one detail). Check the staleness banner: files listed there are pending re-index — read those directly.
- `.codegraph/` is gitignored; rebuild the index with `codegraph init` after cloning.
