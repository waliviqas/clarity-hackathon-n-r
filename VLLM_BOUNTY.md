# Best Use of Red Hat vLLM: Clarity

Owner: Michael. Status: draft, numbers measured Sat Oct 17. Items marked **TODO** are still to be filled in.

## What vLLM does in Clarity

Every generative model in Clarity is served by vLLM on **one NVIDIA A100 80 GB** (Brev), behind vLLM's OpenAI-compatible API. Nothing runs through a hosted API: the camera pipeline and the dispatcher talk to their own vLLM servers.

| Model | Role | Params | vLLM endpoint | GPU share |
|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-Nano-9B-v2` | Dispatcher: decides what the operator should do for each incident | 8.89B | `:8003`, served as `dispatcher` | `--gpu-memory-utilization 0.30` (~26.8 GB measured) |
| `Qwen/Qwen3-VL-2B-Instruct` (+ Wali's fine-tune) | Spotter: reads frames from each camera and reports what happened | 2.13B | `:8001` | ~14.8 GB per instance (measured) |
| `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16` | Checker | 13.18B | **TODO** (confirm with Wali) | **TODO** |

Total generative parameters: 24.20B (≤ 33B cap; exact counts from the published safetensors).

```
cameras ─► spotter (Qwen3-VL-2B, vLLM :8001) ─► camera agents ─► bus ─► dispatcher (Nano 9B v2, vLLM :8003) ─► dashboard
                       one A100 80 GB, models co-located with per-server memory limits
```

## Why vLLM (what it gives us that we measured)

1. **Continuous batching = many cameras and incidents at once.** Clarity's load is many small, concurrent requests (every camera, every open incident). vLLM batches them on the fly: the dispatcher's output throughput rises **~7×** from 1 to 16 concurrent incidents while latency only doubles; the spotter goes from **88 to 993 cameras/min** from 1 to 32 concurrent cameras.
2. **Structured outputs make a small model dependable.** Every dispatcher answer is constrained to a JSON schema (enums for status and priority), so it always parses and our verifier can check every claim against the evidence. **TODO:** measured usable-answer rate with vs without the schema (`scripts/reliability_dispatcher.py`).
3. **Several models on one GPU.** `--gpu-memory-utilization` lets the dispatcher, the spotter, and the fine-tuned spotter share one A100 without stepping on each other.
4. **One OpenAI-compatible API for every model.** Components only know a base URL and a model name, so the same client code runs against any model, and switching or restarting a model doesn't touch the pipeline.
5. **Day-0 support for a hybrid Mamba model.** Nemotron Nano 9B v2 (Mamba-2 + attention) runs on vLLM 0.11 with `--trust-remote-code` and `--mamba_ssm_cache_dtype float32` per the model card.

## Configuration

Dispatcher (in a tmux session on the Brev box; vLLM pinned to **0.11.0** because newer releases don't work with this GPU's driver):

```bash
source ~/vllm12/bin/activate
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2 --served-model-name dispatcher --port 8003 \
  --gpu-memory-utilization 0.30 --max-model-len 8192 --max-num-seqs 16 \
  --mamba_ssm_cache_dtype float32 --enable-prefix-caching --trust-remote-code
```

| Flag | Why |
|---|---|
| `--gpu-memory-utilization 0.30` | Leaves room on the shared A100 for the spotter(s) and checker |
| `--max-model-len 8192` | Dispatcher prompts are ~1.2k characters by design; a short context frees KV/state memory for concurrency |
| `--max-num-seqs 16` | Fits the 0.30 slice; the dispatcher caps its own parallel calls at 8 to stay under it |
| `--mamba_ssm_cache_dtype float32` | Required by the model card for this hybrid Mamba model |
| `--trust-remote-code` | Model card requirement |
| `--enable-prefix-caching` | Set, but measured inactive on 0.11 for this model (see below) |

Client side: `temperature=0`, `max_tokens=400`, `response_format` = JSON schema, one retry on unparseable JSON.

Spotter serve command: **TODO** (from Wali).

## Optimizations, one change at a time (dispatcher)

Full log with sample sizes and commits: [`dispatcher/IMPROVEMENTS.md`](dispatcher/IMPROVEMENTS.md).

| Change | Before | After |
|---|---|---|
| Removed `maxLength` from the JSON schema (enforced in our verifier instead) | 13.3 s per call, 8 tok/s | **1.6 s per call, ~65 tok/s**, same answer |
| Removed `/no_think` (the schema already prevents a reasoning block) | 0/5 valid, 5.6 s, 400 tokens (runaway whitespace) | **5/5 valid, 1.5 s, 103 tokens** |
| One retry on unparseable JSON | 1 fallback in 15 dispatches | **0 fallbacks** in 36 calls |
| Parallel model calls across incidents + batch per bus poll | slowest poll 3.9 s, 18 model calls | **slowest poll 2.3 s, 15 model calls** |

## Results

**Dispatcher** (`scripts/bench_dispatcher.py`, real dispatcher prompt + JSON schema, 16 requests per level, A100 shared with the spotter):

| Concurrent incidents | p50 latency | p95 latency | Output tok/s | Passed verifier |
|---|---|---|---|---|
| 1 | 1.53–1.55 s | 1.54–1.64 s | 65–68 | 32/32 |
| 4 | 1.85–1.91 s | 1.86–5.56 s | 146–223 | 32/32 |
| 8 | 2.25–2.34 s | 2.34–2.36 s | 350–362 | 32/32 |
| 16 | 3.14–3.39 s | 3.16–3.40 s | **477–514** | 32/32 |

Ranges are two runs. The 5.56 s p95 at concurrency 4 was one outlier on the shared GPU.

**Spotter** (Wali's `src/bench.py` → `results/vllm_bench.json`, 4 frames per request, 32 requests per level, 0 errors):

| Concurrent cameras | p50 latency | Cameras/min |
|---|---|---|
| 1 | 0.67 s | 88 |
| 4 | 0.68 s | 344 |
| 8 | 0.77 s | 579 |
| 16 | 1.07 s | 778 |
| 32 | 1.65 s | **993** |

**End to end:** **TODO.** Per-incident latency from camera event to dashboard dispatch, with Mina's `python -m bus.metrics` on one full run.

**Pipeline correctness on vLLM** (Mina's real bus with strict schema validation + her 3-incident scenario + the dispatcher on vLLM): 61/61 events valid, officers sent to the real exit and never a decoy, 0 fallbacks.

## What didn't work (reported, not claimed)

- **Prefix caching:** enabled, but `vllm:prefix_cache_queries_total` stayed 0; vLLM 0.11 doesn't apply it to this hybrid Mamba model.
- **Per-request `disable_any_whitespace`:** accepted but ignored on vLLM 0.11. The JSON retry covers the occasional runaway whitespace instead.

## Reproduce

```bash
# laptop: brev port-forward clarity --port 8003:8003
export CLARITY_LLM_BASE_URL=http://localhost:8003/v1 CLARITY_LLM_MODEL=dispatcher
python scripts/bench_dispatcher.py --levels 1 4 8 16     # dispatcher throughput
python scripts/reliability_dispatcher.py                  # schema vs no schema
python -m dispatcher.run                                  # live dispatcher on the bus
```

## TODO before submission

- [ ] Reliability numbers (`scripts/reliability_dispatcher.py`), after Wali's GPU evaluation finishes
- [ ] Spotter and checker serve commands and memory shares (Wali)
- [ ] End-to-end latency with `bus.metrics` (Mina, one full run)
- [ ] Final pass: numbers match the latest runs
