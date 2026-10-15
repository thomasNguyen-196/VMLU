# Small Open-Weight Language Models for Vietnamese: A Capability–Efficiency Benchmark

**Research Proposal**

---

A strong research question would be:

> How effective are small open-weight LLMs (≤8B) for Vietnamese language understanding, reasoning, cultural knowledge, and agentic tasks under realistic compute constraints?

This is more interesting than just “which model scores highest,” because you can study the quality–efficiency trade-off.

The timing is also reasonable. The public VMLU leaderboard contains older small baselines such as Qwen2.5-7B, Phi-3-small, BloomVN-0.5B, DeepSeek-R1-Distill-Qwen-1.5B and several Vietnamese-adapted 7–8B models, but I do not find Qwen3-4B, Gemma-3-4B, Phi-4-mini, or Ministral-3-3B there.

I would use this model set:

| Group          | Models                                          | Why                                |
| -------------- | ----------------------------------------------- | ---------------------------------- |
| Qwen scaling   | Qwen3-0.6B, 1.7B, 4B, 8B                        | Best controlled scaling experiment |
| Google         | Gemma-3-1B, 4B                                  | Strong multilingual alternative    |
| Meta           | Llama-3.2-1B, 3B                                | Widely used small baseline         |
| Microsoft      | Phi-4-mini 3.8B                                 | Strong reasoning control           |
| Mistral        | Ministral-3-3B, 8B                              | Modern edge-oriented models        |
| Vietnamese/SEA | BloomVN-0.5B, BloomVN-8B, SeaLLM-7B, Vistral-7B | Language-adapted controls          |

Qwen3 is particularly useful because you get a clean size series from 0.6B → 1.7B → 4B → 8B under essentially the same model family. Qwen3 explicitly supports 100+ languages/dialects.

Gemma 3 gives another useful scaling family. Its published multilingual benchmarks already show a substantial jump between 1B and 4B, which makes the Vietnamese-specific comparison interesting.

Phi-4-mini is an especially interesting negative/control case. It is a 3.8B model with a 200K-token vocabulary and strong general reasoning, but Microsoft does not list Vietnamese among its officially supported languages. If it nevertheless performs well on Vietnamese benchmarks, that tells you something important about cross-lingual transfer versus explicitly Vietnamese-oriented pretraining.

For benchmarks, I would not run everything from the previous list. Use four main layers:

| Layer                 | Benchmark    | What it answers                                           |
| --------------------- | ------------ | --------------------------------------------------------- |
| Core                  | VMLU         | Vietnamese knowledge + reasoning                          |
| Vietnam-specific      | V-Bench      | culture, medicine, Vietnamese knowledge, agentic/tool use |
| Linguistic robustness | VialectBench | dialect robustness                                        |
| General NLU           | ViGLUE       | Vietnamese language understanding                         |
| Optional intrinsic    | ViWiki/PPL   | raw Vietnamese language modeling                          |

VMLU is the cleanest primary benchmark. It spans 58 subjects and the broader suite covers knowledge, reading comprehension, reasoning and dialogue.

V-Bench adds something VMLU does not: explicitly Vietnam-centric culture, regional knowledge, health, safety-related content and agentic behavior. The current public release has more than 40,000 questions/tasks; its public scoring currently supports multiple-choice and function-call agentic tasks, while Safety is not currently included in the public score.

I would organize the study around four RQs.

### RQ1 — Capability scaling

$$
\text{Vietnamese capability} = f(\text{model size})
$$

For Qwen3:

```text
0.6B → 1.7B → 4B → 8B
```

Measure whether gains are approximately monotonic, and where diminishing returns start.

### RQ2 — Architecture/model-family effect

```text
~3–4B class

Qwen3-4B
Gemma-3-4B
Phi-4-mini-3.8B
Llama-3.2-3B
Ministral-3-3B
```

This is probably the most informative comparison because parameter count is approximately controlled.

### RQ3 — General multilingual versus Vietnamese-adapted models

```text
Generic multilingual
    Qwen / Gemma / Llama
             ↓
       versus
             ↓
Vietnamese/SEA adapted
    BloomVN / SeaLLM / Vistral
```

The important question is whether explicit Vietnamese adaptation still beats newer general multilingual LLMs.

VMLU already illustrates why this is interesting. For example, its public leaderboard reports roughly 57.5 for Qwen2.5-7B-Instruct, 56.6 for BloomVN-8B-chat, 53.3 for SeaLLM-7B-v2.5 and 50.1 for Vistral-7B-Chat. New multilingual foundation models may have closed or reversed the specialized-model advantage.

### RQ4 — Quality versus deployment cost

Do not define “effective” using accuracy alone. Measure:

$$
Q = \text{benchmark performance}
$$

against

$$
C = \{\text{parameters, VRAM, latency, energy, tokens generated}\}.
$$

For every model record at minimum:

```text
VMLU accuracy
V-Bench score
VialectBench accuracy/F1
ViGLUE aggregate

Parameters
Peak VRAM
TTFT
tokens/sec
total latency/question
input tokens/question
output tokens/question
```

Then plot Pareto frontiers such as:

```text
              Vietnamese accuracy ↑
                          ● 8B
                     ● 4B
                 ● 3B
           ● 1.7B

                    → GPU memory
```

This is much more defensible than inventing a weighted “efficiency score.”

There is another dimension I strongly recommend adding: tokenizer efficiency. For Vietnamese, measure:

$$
F=\frac{N_{\text{tokens}}}{N_{\text{words}}}
$$

plus:

- tokens / 1,000 Vietnamese characters;
- characters / token;
- prompt token count;
- Vietnamese versus English tokenization ratio.

This can explain why two models with similar parameter counts have different inference cost on Vietnamese.

For reasoning models such as Qwen3, you need two separate conditions:

```text
Qwen3-4B non-thinking
Qwen3-4B thinking
```

But thinking mode must have a fixed reasoning budget. Otherwise comparisons become misleading: a 4B model generating 5,000 reasoning tokens is not operating under the same compute budget as a 4B model generating 50 tokens. Qwen itself documents distinct thinking/non-thinking modes and recommends different generation settings.

I would therefore report three evaluation regimes:

```text
Regime A — Capability
BF16
zero-shot
official chat template
fixed max output
no quantization

Regime B — Edge deployment
INT4
batch = 1
same GPU
same serving engine
same benchmark

Regime C — Reasoning budget
128 / 512 / 2048 reasoning tokens
```

This creates a much stronger paper:

> “Small Open-Weight Language Models for Vietnamese: A Capability–Efficiency Benchmark”

rather than merely:

> “Evaluation of Small LLMs on VMLU.”

There is an additional issue worth exploiting. The Qwen3 technical report already reports Vietnamese-specific results on MLogiQA, INCLUDE, MT-AIME24 and PolyMath, and shows a very strong size effect—for example Qwen3-0.6B, 1.7B, 4B and 8B improve substantially as scale increases. So merely showing that “larger Qwen3 performs better in Vietnamese” is not novel.

The stronger contribution is therefore:

$$
\boxed{
\text{Vietnam-specific capability}
+
\text{dialect robustness}
+
\text{tokenization}
+
\text{inference efficiency}
}
$$

under controlled sub-8B deployment.

My preferred minimal experiment would be only 10 models:

```text
Qwen3-0.6B
Qwen3-1.7B
Qwen3-4B
Qwen3-8B

Gemma-3-1B
Gemma-3-4B

Llama-3.2-1B
Llama-3.2-3B

Phi-4-mini-3.8B

BloomVN-8B
```

This is large enough for a meaningful study but small enough to run systematically on one RTX 5090-class GPU.

If the ultimate goal is your earlier idea of developing a Vietnamese tokenizer/open-weight model, this experiment is actually the correct Stage 0: it establishes exactly where current small open-weight models fail before modifying tokenizer or continued pretraining.
