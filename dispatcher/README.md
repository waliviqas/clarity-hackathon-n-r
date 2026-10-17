# Dispatcher (#5)

Owner: Michael. Model: **NVIDIA Nemotron Nano 9B v2** served on **vLLM** (port 8003 on the team Brev box).

Reads camera-agent messages (contracts v0.1) and emits one `dispatch` per incident change for the dashboard: what happened, where the subject has been, where they're heading, and where to send officers. Rules handle clear cases; the model handles ambiguous ones; every model answer is checked against the evidence before it goes out. A human confirms every recommendation.

```
detection / relay / agent_verdict ─► per-subject case (keyed by subject_id)
                                          │
                     path + predicted_next (Wali's graph.predict_next, else built-in fallback)
                                          │
                                        gate ──activity "none"──► nothing emitted
                                          │
                                          ├──clear (e.g. stabbing ≥0.85, no uncertain verdicts)──► template dispatch, no model call
                                          │
                                          └──ambiguous──► Nano 9B v2 (JSON schema) ─► verifier ──ok──► dispatch
                                                               ▲                          │
                                                               └──── errors, 1 retry ─────┘
                                                                                          └─still bad──► "tracking" + "Operator review needed."
operator_action ─► confirm: status "alert", requires_human_confirm false · dismiss: "resolved", incident goes quiet
```

## Contract fit (v0.1)

| Direction | type | Fields used |
|---|---|---|
| in | `detection` | `camera_id`, `activity`, `activity_confidence`, `appearance`, `direction` |
| in | `relay` | `subject_id`, `from_camera`, `to_camera`, `summary`, `appearance`, `direction`, `activity`, `evidence_event_ids` |
| in | `agent_verdict` | `subject_id`, `camera_id`, `decision`, `reason`, `evidence_event_ids` |
| in | `operator_action` | `incident_id`, `action` |
| in | `cameras.json` | `cameras[].camera_id`, `name`, `neighbors[].camera_id/travel_time_s/direction` |
| out | `dispatch` | all required fields + `subject_appearance`, `source: "dispatcher"`, `path[].event_id` |

Every emitted dispatch is checked in tests against the v0.1 required fields and enums, and against `contracts/schemas/dispatch.schema.json` once the contracts folder is on `main`.

### How `dispatch` fields are filled

| field | source |
|---|---|
| `incident_type` | most severe `detection.activity` for the subject; falls back to `relay.activity` |
| `subject_appearance` | latest non-null `appearance` from relays/detections |
| `path` | relay origin cameras (at the cited detection) + cameras with a `match` verdict; each point carries the proving `event_id` |
| `predicted_next` | Wali's `predict_next(camera_id, direction)` when passed in (unknown cameras dropped; errors fall back). Fallback: unvisited neighbors of the last camera, 3× weight for the neighbor in the subject's `direction` (exit vs decoy) and for a camera already relayed to |
| `status`, `priority`, `recommendation`, `reason`, `evidence_event_ids` | rules template (clear cases) or the model (ambiguous), always verified |
| `requires_human_confirm` | `true` until an `operator_action` arrives |

Priorities (team decision): `stabbing` → high · `fistfight` (assault) → medium · `purse_snatch` → low · `none` → no incident. Only stabbing can be auto-alerted by rules; the others always get the model, capped at their priority.

## Procedure guidance (hard-coded)

Every recommendation ends with a fixed procedure line for its incident type, appended by code after verification (never written by the model), from `dispatcher/guidance.py`:

| incident_type | appended line |
|---|---|
| stabbing | Procedure: armed suspect, approach with backup; request EMS for the victim. |
| fistfight | Procedure: separate the parties, check for injuries, request EMS if needed. |
| purse_snatch | Procedure: take the victim's statement and broadcast the suspect description. |

The model's part is limited to 300 minus the guidance length, so the total stays within the contract's 300 characters. Turn it off with `Dispatcher(guidance=False)`. This replaces the earlier RAG idea (dropped).

## Batches, parallel incidents, and the bus

`Dispatcher.process(batch)` takes a batch of messages (one bus poll), then evaluates every incident it touched **once**:

- Gate, path, and `predict_next` run sequentially (so Wali's `predict_next` doesn't need to be thread-safe).
- **Model calls for different incidents run in parallel** (`max_parallel`, default 8; keep ≤ vLLM `--max-num-seqs` 16) so vLLM batches them.
- Dispatches are emitted in arrival order, so `inc_N` numbering doesn't depend on which model call finishes first.
- An `operator_action` first flushes pending evaluations, so it applies to the incident's latest state.
- **Duplicate `event_id`s are skipped.** Mina's `fetch()` has an inclusive `since_ts` and is meant to be polled with a lookback, so repeats are normal; without this, each repeat would cost another model call.

Measured on Mina's `fake_scenario` (3 incidents starting 10 s apart, replayed as one poll per second, live model): slowest poll 3.9 s → 2.3 s, model calls 18 → 15 (updates within a poll merge), no fallbacks. Overlap in that scenario peaks at 2 incidents; the gain grows with overlap (see the load test: 16 concurrent requests take 3.4 s, not 16 × 1.6 s).

Planned bus runner (once `bus/` is on `main`): every ~0.5 s, `fetch()` `detection`, `relay`, `agent_verdict`, `operator_action` with `since_ts = newest seen − 30`, sort the merged list by `ts`, `d.process(batch)`, `publish()` each dispatch.

## Verifier (why the model can't send officers somewhere wrong)

A model answer is rejected (one retry with the errors, then fallback) if it:
- cites an event that isn't in the subject's evidence, or cites nothing;
- mentions a camera outside the case;
- doesn't send officers to `send_officers_to` (= `predicted_next[0]`, else last seen camera);
- sets a priority above what the cited activities support, or raises `alert` without a medium+ activity;
- exceeds the contract's text limits (recommendation 300, reason 500 characters).

## Serving (vLLM on Brev)

```bash
# on the Brev box, inside tmux, using the team's pinned vLLM 0.11.0
source ~/vllm12/bin/activate
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2 --served-model-name dispatcher --port 8003 \
  --gpu-memory-utilization 0.30 --max-model-len 8192 --max-num-seqs 16 \
  --mamba_ssm_cache_dtype float32 --enable-prefix-caching --trust-remote-code
```

- No `/no_think`: the JSON schema forces the first token to be `{`, so no reasoning block can start. With `/no_think` the model trailed into whitespace until `max_tokens` (0/5 valid vs 5/5 without).
- **No `maxLength` in the JSON schema.** On vLLM 0.11, string length limits made schema-constrained decoding ~8× slower (13.3 s → 1.6 s per call, 8 → ~65 tokens/s, same output). Lengths are enforced by the verifier instead.
- **Prefix caching is not active.** `--enable-prefix-caching` is set, but vLLM's `prefix_cache_queries_total` metric stayed at 0: vLLM 0.11 doesn't apply it to this hybrid Mamba model. Don't claim it.
- **Change-by-change measurements: see [IMPROVEMENTS.md](IMPROVEMENTS.md).**
- **Throughput from continuous batching** (`scripts/bench_dispatcher.py`; A100, 0.30 slice, shared with the team's other models; real dispatcher prompt + JSON schema; 16 requests per level; final config):

  | concurrent requests | p50 latency | p95 latency | requests/s | output tokens/s | passed verifier |
  |---|---|---|---|---|---|
  | 1 | 1.53 s | 1.54 s | 0.65 | 68 | 16/16 |
  | 4 | 1.85 s | 1.86 s | 2.16 | 223 | 16/16 |
  | 8 | 2.25 s | 2.34 s | 3.51 | 362 | 16/16 |
  | 16 | 3.14 s | 3.16 s | 4.99 | 514 | 16/16 |

  7.6x the output throughput at 16 concurrent incidents for 2x the latency.
- Rules-path dispatches (clear cases) take <1 ms and no GPU.

## Models and the 33B cap (exact counts from the published safetensors)

| Role | Model | Parameters |
|---|---|---|
| Dispatcher | `nvidia/NVIDIA-Nemotron-Nano-9B-v2` | 8,888,227,328 |
| Spotter | `Qwen/Qwen3-VL-2B-Instruct` | 2,127,532,032 |
| Checker | `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16` | 13,181,860,358 |
| **Total generative** | | **24.20B ≤ 33B** |

The verifier is plain code, not a model, so it adds nothing to the budget. Spotter and checker checkpoints: confirm these are the exact ones on the Brev box.

## Running

```bash
pip install -r requirements.txt
python -m pytest -q
python -m dispatcher.demo                                   # built-in scenario, scripted model, no GPU

# against the real model (from a laptop: brev port-forward clarity --port 8003:8003)
CLARITY_LLM_BASE_URL=http://localhost:8003/v1 CLARITY_LLM_MODEL=dispatcher python -m dispatcher.demo --live

python -m dispatcher.demo --cameras cameras.json --messages events.jsonl --live   # replay a recorded run
python scripts/bench_dispatcher.py --levels 1 4 8 16                              # vLLM load test
```

## Not done yet (waiting on others)

- **Bus runner** (`fetch()` relays/verdicts/operator actions, `publish()` dispatches): waits for Mina's bus client to land on `main`.
- **Wali's `predict_next`**: hook is ready (`Dispatcher(..., predict_next=fn)`); plug in when the graph module exists.
