# Small Open-Weight Language Models for Vietnamese: A Capability–Efficiency Benchmark

**Research Proposal**

---

## 1. Problem Statement & Research Question

Instead of producing another ordinary leaderboard that simply ranks which model scores highest, this study focuses on a comprehensive evaluation of real-world feasibility and the **Quality**–**Efficiency** trade-off of small open-weight models (≤8B) on Vietnamese.

### Core Research Question

> **"How effective are small open-weight LLMs (≤8B) for Vietnamese language understanding, reasoning, cultural knowledge, and agentic tasks under realistic compute constraints?"**

### Core Contribution

$$\boxed{\text{Vietnam-specific capability} + \text{Dialect robustness} + \text{Tokenization efficiency} + \text{Inference cost}}$$

This study also serves as **Stage 0 (Baseline & Gap Analysis)**: it precisely establishes where current small open-weight models fail before proceeding to tokenizer optimization or continued pretraining of a Vietnamese-specialized model.

---

## 2. Evaluation Model Matrix

### 2.1. Model Groups

| Group | Models | Rationale |
| :--- | :--- | :--- |
| **Qwen scaling** | Qwen3 (0.6B, 1.7B, 4B, 8B) | Controlled scaling study within the same model family; supports 100+ languages. |
| **Google** | Gemma-3 (1B, 4B) | Strong multilingual alternative; verify the capability jump between 1B and 4B. |
| **Meta** | Llama-3.2 (1B, 3B) | Widely used small / edge baseline. |
| **Microsoft** | Phi-4-mini (3.8B) | Strong reasoning baseline (200K vocabulary); does not officially list Vietnamese -> measures cross-lingual transfer. |
| **Mistral** | Ministral-3 (3B, 8B) | Modern edge-oriented models. |
| **Vietnamese / SEA Adapted** | BloomVN (0.5B, 8B), SeaLLM-7B, Vistral-7B | Control group specialized / continued-pretrained for Vietnamese & Southeast Asia. |

### 2.2. Minimal 10-Model Experiment

Optimized to run systematically on a feasible single-GPU setup (e.g., RTX 5090 / A100 class):

1. **Qwen3-0.6B**
2. **Qwen3-1.7B**
3. **Qwen3-4B**
4. **Qwen3-8B**
5. **Gemma-3-1B**
6. **Gemma-3-4B**
7. **Llama-3.2-1B**
8. **Llama-3.2-3B**
9. **Phi-4-mini-3.8B**
10. **BloomVN-8B**

---

## 3. Evaluation Layers (Benchmarks)

| Layer | Benchmark | What It Measures |
| :--- | :--- | :--- |
| **Core** | **VMLU** | Multidisciplinary knowledge (58 subjects) & Vietnamese reasoning. |
| **Vietnam-specific** | **V-Bench** | Indigenous culture, medicine, Vietnam-specific knowledge, safety & agentic tasks (function calling). |
| **Linguistic Robustness** | **VialectBench** | Model robustness to Vietnamese dialects & regional variants. |
| **General NLU** | **ViGLUE** | General reading comprehension & natural language understanding. |
| **Intrinsic (Optional)** | **ViWiki / PPL** | Perplexity on standard Vietnamese text (raw language modeling). |

---

## 4. Detailed Research Questions

### RQ1: Capability Scaling

$$\text{Vietnamese capability} = f(\text{model size})$$

- Verified across the Qwen3 size series: $0.6\text{B} \rightarrow 1.7\text{B} \rightarrow 4\text{B} \rightarrow 8\text{B}$.
- Determine whether gains are approximately monotonic and where diminishing returns begin.

### RQ2: Architecture / Model-Family Effect at ~3–4B

Controlled comparison of parameter count:

$$\text{Qwen3-4B} \quad \text{vs} \quad \text{Gemma-3-4B} \quad \text{vs} \quad \text{Phi-4-mini-3.8B} \quad \text{vs} \quad \text{Llama-3.2-3B} \quad \text{vs} \quad \text{Ministral-3-3B}$$

### RQ3: Generic Multilingual vs. Vietnamese-Adapted Models

$$\text{Generic Multilingual (Qwen / Gemma / Llama)} \quad \longleftrightarrow \quad \text{Vietnamese/SEA Adapted (BloomVN / SeaLLM / Vistral)}$$

- Determine whether new-generation multilingual foundation models have closed or reversed the gap against models explicitly continued-pretrained for Vietnamese.

### RQ4: Quality vs. Deployment Cost

Evaluate Quality $Q$ alongside Cost $C$:

$$Q = \{\text{VMLU, V-Bench, VialectBench, ViGLUE}\}$$
$$C = \{\text{Parameters, Peak VRAM, TTFT (Time to First Token), Tokens/sec, Total Latency, Output Tokens}\}$$

- Plot **Pareto frontiers** illustrating the relationship between **Vietnamese Accuracy** and **GPU Memory / Latency** rather than inventing a weighted "efficiency score."

---

## 5. Tokenizer Efficiency Evaluation

Measure the cost of representing Vietnamese text for each tokenizer:

- **Tokens / Word ratio**: $F = \frac{N_{\text{tokens}}}{N_{\text{words}}}$
- Tokens per 1,000 Vietnamese characters.
- Average characters per token.
- Vietnamese vs. English tokenization ratio (prompt token count comparison).

---

## 6. Evaluation Regimes

1. **Regime A — Capability Baseline**:
   - Precision: BF16 / FP16.
   - Zero-shot (or few-shot standardized per benchmark).
   - Official model chat template.
   - No quantization.

2. **Regime B — Edge Deployment**:
   - Quantization: INT4 / AWQ / GGUF.
   - Batch size = 1.
   - Same serving engine (vLLM / SGLang / Ollama) and consistent hardware configuration.

3. **Regime C — Reasoning Budget**:
   - For reasoning (thinking) models such as Qwen3:
     - Compare `non-thinking` vs. `thinking`.
     - Fixed reasoning token budget: **128 / 512 / 2048 tokens**.

---

## 7. Action Plan

1. **Phase 1**: Standardize the benchmark pipeline (VMLU, V-Bench, VialectBench, ViGLUE) and tooling for tokenization / inference profiling.
2. **Phase 2**: Run Regime A evaluation & tokenizer analysis on the 10 core models.
3. **Phase 3**: Run Regime B (Edge / INT4) and Regime C (reasoning budget) evaluations.
4. **Phase 4**: Aggregate data, draw Pareto frontiers, analyze results, and write the research report.