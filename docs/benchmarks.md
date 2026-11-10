# Benchmarking MIRA

The benchmark script drives the real Ollama API. It measures the full local
pipeline: environment snapshot, optional retrieval, prompt construction, model
generation, and streaming. It does **not** use the deterministic fast path, so
every question exercises the model.

## Running

```bash
python scripts/benchmark.py
python scripts/benchmark.py --json
python scripts/benchmark.py --questions my-questions.txt
python scripts/benchmark.py --no-cheatsheet
python scripts/benchmark.py --explain
python scripts/benchmark.py --model gemma4:e4b-it-q4_K_M
```

`--questions` expects one question per line; blank lines and lines starting
with `#` are ignored.

## Metrics

| Field | Meaning |
|---|---|
| `ttft_ms` | Time from request start to the first streamed content token |
| `total_ms` | Time from request start to the final response chunk |
| `tokens_per_second` | `eval_count / (eval_duration / 1e9)` from Ollama |
| `prompt_tokens` | `prompt_eval_count` from Ollama |
| `completion_tokens` | `eval_count` from Ollama |
| `retrieval_used` | Whether any cheatsheet entry matched |
| `retrieval_matches` | Number of entries injected (up to `retrieval.max_results`) |
| `answer_chars` | Length of the streamed answer text |

Values are never estimated. If Ollama omits a field, the script prints `n/a`.

## Measured result

Environment for this run:

- Fedora Linux 44, kernel 7.2.11, x86_64
- NVIDIA RTX 3050 6 GB Laptop GPU (~810 MiB already in use)
- Ollama 0.40.14
- `gemma4:e4b-it-q4_K_M` (7.5B, Q4_K_M, ~6.58 GB)
- One-shot mode, retrieval enabled, model already loaded (`keep_alive = 5m`)

```text
QUESTION                                       TTFT ms  TOTAL ms    TOK/S  PROMPT   EVAL  RETR
----------------------------------------------------------------------------------------------
Where is Apache's configuration file on F…      1774.6    5633.1    11.40     512     44   yes
How do I restart Apache?                        2148.1    4215.0    10.16     550     21   yes
How do I check listening ports?                 1499.7    7116.4    10.50     427     59   yes
How do I inspect systemd logs?                  1595.0    8222.1     9.96     476     66   yes
How do I allow HTTP through firewalld?          2006.2    5855.9    12.47     559     48   yes
How do I check NVIDIA GPU usage?                1495.1    4790.0     8.19     438     27   yes
How do I see my current Git branch?             1445.9    4238.4     9.67     412     27   yes
How do I find Python files recursively?         1467.2    5020.3     9.57     423     34   yes
How do I check available disk space?            1672.5    4748.3     9.43     500     29   yes
How do I inspect an Ollama service failur…      2004.5    6882.5    10.86     571     53   yes

Model: gemma4:e4b-it-q4_K_M
Questions: 10
Mean TTFT: 1710.88 ms
Mean total: 5672.20 ms
Mean tokens/s: 10.22
```

## Interpreting the numbers

- The model was warm. A cold load adds several seconds to the first request; in
  this environment a cold one-word request took about 13.9 seconds total.
- Throughput is roughly 10 tokens/second on this GPU, which is consistent with
  partial offload on a 6 GB card. Results depend heavily on what else is using
  the GPU.
- TTFT is around 1.4–2.2 seconds even when warm. The environment snapshot and
  retrieval cost a few milliseconds; almost all of TTFT is model prefill.
- The deterministic fast path avoids the model entirely. In a separate check,
  `mira --json "How do I check available disk space?"` answered from the
  cheatsheet in about 12 ms.

Do not compare these numbers with other machines without recording the model,
quantization, context size, GPU, Ollama version, and whether the model was
loaded.
