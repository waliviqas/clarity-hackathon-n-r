# Best Use of Red Hat vLLM: Clarity

Owner: Michael (spotter details from Wali). Status: draft, numbers measured Sat Oct 17. Items marked **TODO** are still to be filled in.

## What vLLM does in Clarity

Every model Clarity runs is served by vLLM on **one NVIDIA A100 80 GB** (Brev), behind vLLM's OpenAI-compatible API. Nothing runs through a hosted API: the camera pipeline and the dispatcher talk to their own vLLM servers, all on vLLM **0.11.0** (newer releases need a newer GPU driver than the Brev A100 has).

| Model | Role | Params | vLLM endpoint | GPU share |
|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-Nano-9B-v2` | Dispatcher: decides what the operator should do for each incident | 8.89B | `:8003`, served as `dispatcher` | `--gpu-memory-utilization 0.30` (~26.8 GB measured) |
| `Qwen/Qwen3-VL-2B-Instruct` | Spotter, base model (before fine-tuning) | 2.13B | `:8001` | `0.2` (~14.8 GB measured) |
| Wali's fine-tuned spotter v3 (LoRA merged into Qwen3-VL-2B) | Spotter, fine-tuned (the Fine-Tuned track model): crime and crime type | 2.13B | `:8005`, served as `spotter-ft` | `0.2` (~14.8 GB measured) |
| `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16` | Checker: describes the suspect on cameras the spotter flags (`src/checker.py`) | 13.18B | `:8002`, served as `checker` | **TODO** (from Wali) |

Generative parameters in the final system: dispatcher 8.89B + spotter 2.13B + checker 13.18B = **24.20B ≤ 33B** (exact counts from the published safetensors). The base and fine-tuned spotter are the same 2.13B model before and after training; the base is served only for the before/after comparison.

```
cameras ─► spotter (Qwen3-VL-2B, vLLM :8001) ─► camera agents ─► bus ─► dispatcher (Nano 9B v2, vLLM :8003) ─► dashboard
                       one A100 80 GB, models co-located with per-server memory limits
```

## Why vLLM (what it gives us that we measured)

1. **Continuous batching = many cameras and incidents at once.** Clarity's load is many small, concurrent requests (every camera, every open incident). vLLM batches them on the fly: the dispatcher's output throughput rises **~7×** from 1 to 16 concurrent incidents while latency only doubles; the spotter goes from **88 to 993 cameras/min** from 1 to 32 concurrent cameras.
2. **Structured outputs make small models dependable.** Both the dispatcher and the spotter use vLLM's `response_format` JSON schema: the dispatcher's status and priority are enums, the spotter's `on_screen` and `crime` are enums, so answers parse and our code can check them (the dispatcher's verifier checks every claim against the evidence). **TODO:** measured usable-answer rate with vs without the schema (`scripts/reliability_dispatcher.py`).
3. **Several models on one GPU.** `--gpu-memory-utilization` lets the dispatcher (0.30), the base spotter (0.2), and the fine-tuned spotter (0.2) share one A100 without stepping on each other.
4. **One OpenAI-compatible API for every model.** Components only know a base URL and a model name, so the same client code runs against any model, and switching or restarting a model doesn't touch the pipeline.
5. **Day-0 support for a hybrid Mamba model.** Nemotron Nano 9B v2 (Mamba-2 + attention) runs on vLLM 0.11 with `--trust-remote-code` and `--mamba_ssm_cache_dtype float32` per the model card.

## Configuration

Dispatcher ([`infra/serve_dispatcher.sh`](infra/serve_dispatcher.sh), run in a tmux session on the Brev box; vLLM pinned to **0.11.0** because newer releases don't work with this GPU's driver):

```bash
source ~/vllm12/bin/activate
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2 --served-model-name dispatcher --host 127.0.0.1 --port 8003 \
  --gpu-memory-utilization 0.30 --max-model-len 8192 --max-num-seqs 16 \
  --mamba_ssm_cache_dtype float32 --enable-prefix-caching --trust-remote-code
```

| Flag | Why |
|---|---|
| `--host 127.0.0.1` | Only reachable on the box and through the SSH/port-forward tunnel, not from the internet (vLLM's default listens on every interface) |
| `--gpu-memory-utilization 0.30` | Leaves room on the shared A100 for the spotter(s) and checker |
| `--max-model-len 8192` | Dispatcher prompts are ~1.2k characters by design; a short context frees KV/state memory for concurrency |
| `--max-num-seqs 16` | Fits the 0.30 slice; the dispatcher caps its own parallel calls at 8 to stay under it |
| `--mamba_ssm_cache_dtype float32` | Required by the model card for this hybrid Mamba model |
| `--trust-remote-code` | Model card requirement |
| `--enable-prefix-caching` | Set, but measured inactive on 0.11 for this model (see below) |

Client side: `temperature=0`, `max_tokens=400`, `response_format` = JSON schema, one retry on unparseable JSON.

Spotter (Wali), base and fine-tuned, on the same A100 (checker serve command: **TODO** from Wali; client in `src/checker.py`, `CHECKER_BASE_URL=http://localhost:8002/v1`, `CHECKER_MODEL=checker`):

```bash
vllm serve Qwen/Qwen3-VL-2B-Instruct --port 8001 --gpu-memory-utilization 0.2 --max-model-len 16384
vllm serve models/spotter-ft-merged --served-model-name spotter-ft --port 8005 --gpu-memory-utilization 0.2 --max-model-len 16384
```

- `--max-model-len 16384`: each spotter request carries several camera frames as images.
- **Fine-tuned model served as merged weights, not as a LoRA adapter:** LoRA serving (`--enable-lora`) crashes on vLLM 0.11 for Qwen3-VL with image inputs, so the LoRA add-on is merged into the base weights and served as its own model.
- `--host 127.0.0.1` will be added on the next restart, as on the dispatcher.

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

**Spotter** (Wali's `src/bench.py` → `results/vllm_bench.json`, base Qwen3-VL-2B on **0.2 of one A100**, 4 frames per request, 32 requests per level, 0 errors):

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
- **LoRA serving for the fine-tuned spotter:** `--enable-lora` crashes on vLLM 0.11 with Qwen3-VL and images. Workaround: merge the LoRA into the base weights and serve the merged model (`spotter-ft`, `:8005`).

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
- [x] Spotter serve commands and memory shares (Wali)
- [x] Checker is part of the final system (served on :8002 as `checker`, Wali's `src/checker.py`); budget 24.20B
- [ ] Checker serve command and memory share (Wali)
- [ ] Spotter throughput rerun on the fine-tuned model (optional)
- [ ] End-to-end latency with `bus.metrics` (Mina, one full run)
- [ ] Final pass: numbers match the latest runs
