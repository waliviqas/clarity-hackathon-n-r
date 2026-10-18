# Dispatcher improvement log (bounty evidence)

Every change to the dispatcher's model path, the problem it fixed, and what we measured before and after. One change at a time, same scenario, so each gain is attributable.

**Setup for all measurements:** NVIDIA Nemotron Nano 9B v2 on vLLM 0.11.0, A100 80 GB (0.30 slice, shared with the team's other two models), `temperature=0`, `max_tokens=400`, JSON-schema constrained output. Scenarios are synthetic: the built-in demo incident (`dispatcher/demo.py`) and Mina's `bus/fake_scenario.py` (3 overlapping incidents with decoy exits), replayed as one bus poll per second. Sample sizes are small (noted per row); treat them as engineering measurements, not a benchmark.

## Changes and results

| # | Change | Problem it fixed | Before | After | n | Commit |
|---|---|---|---|---|---|---|
| 1 | Removed `maxLength` from the JSON schema; enforce lengths in the verifier | Schema-constrained decoding was ~8× slower than unconstrained | 13.3 s/call, 8 tok/s | **1.6 s/call, ~65 tok/s** (same 109-token answer) | 2 + 2 calls | `5839e50` |
| 2 | Give the model `send_officers_to` (= `predicted_next[0]`); verifier rejects answers that don't send officers there | Model sent officers back to the crime scene instead of where the subject was heading | 2/2 model dispatches pointed at the crime scene | **2/2** demo, **3/3** Mina incidents point at the real exit (not the decoy) | 2 + 3 incidents | `5839e50` |
| 3 | Refer to cameras by `camera_id` only (no names, no example to copy) | Model copied an example name from the prompt ("North exit") onto the wrong cameras; the verifier only checks ids | 1 of 2 answers had an invented name | 0 invented names | 2 + 2 | `5839e50` |
| 4 | Renamed the payload field `intercept_camera` → `send_officers_to` | Model wrote the internal field name into the officer-facing text | 2/2 answers said "intercept_camera cam_03" | 0/2 | 2 | `5839e50` |
| 5 | Parallel incidents: batch per poll, concurrent model calls, skip duplicate `event_id`s | Overlapping incidents queued behind each other; bus re-polls would re-trigger the model | slowest poll 3.9 s, 18 model calls | **slowest poll 2.3 s, 15 model calls**, 0 fallbacks | 1 run, 3 incidents | `4516134` |
| 6 | Priority cap given to the model as `max_priority` (team priorities: stabbing high, fistfight medium, purse snatch low) | Model chose "high" for purse snatches; verifier would reject | — | model never exceeded the cap; 0 priority rejections | 36 calls | this commit |
| 7 | Retry once on unparseable JSON (was: straight to fallback) | Occasional runaway whitespace until `max_tokens` → cut-off JSON | 1 fallback in 15 dispatches | **0 fallbacks** in 36 calls; 6/36 first attempts needed the retry | 2 runs | this commit |
| 8 | Removed `/no_think` from the system prompt | With the current prompt, `/no_think` made the model trail into whitespace until `max_tokens` | **0/5** valid, 5.6 s, 400 tokens | **5/5** valid, 1.5 s, 103 tokens | 5 + 5 calls | this commit |
| 9 | Fallback prediction: combine heading × relay signals (was: relay weight replaced heading); only count relays from the subject's last confirmed camera; take heading from detections before relays | Running Mina's `fake_scenario` through her real bus, the dispatcher once sent officers to a **decoy** exit: a stale relay from the junction outranked the exit the subject had already reached | 1/13 dispatches → decoy; real exit vs decoy tied 50/50 at the junction | **0/14** → decoy; exit 0.75 vs decoy 0.25 at the junction | 1 end-to-end run, 3 incidents | this commit |

The schema forces the first output token to be `{`, so Nano v2 can't start a reasoning block anyway; dropping `/no_think` costs nothing.

## Serving throughput (final config)

`scripts/bench_dispatcher.py`, real dispatcher prompt + schema, 16 requests per level:

| concurrent requests | p50 latency | p95 latency | requests/s | output tokens/s | passed verifier |
|---|---|---|---|---|---|
| 1 | 1.53 s | 1.54 s | 0.65 | 68 | 16/16 |
| 4 | 1.85 s | 1.86 s | 2.16 | 223 | 16/16 |
| 8 | 2.25 s | 2.34 s | 3.51 | 362 | 16/16 |
| 16 | 3.14 s | 3.16 s | 4.99 | **514** | 16/16 |

7.6× the output throughput at 16 concurrent incidents for 2× the latency (vLLM continuous batching).

**Run-to-run variation.** A repeat run on Sat Oct 17 night (same config, code at `df3a804`, GPU shared with the team's spotter) gave 65 → 477 output tok/s from 1 → 16 concurrent, p50 1.55 → 3.39 s, 64/64 verified, with one slow outlier at concurrency 4 (p95 5.6 s). Report throughput at 16 concurrent as **~477–514 tok/s**, not the best run alone.

## Verification runs (no code changes, Sat Oct 17 night, code at `df3a804`)

| Run | Setup | Result |
|---|---|---|
| Load test | `scripts/bench_dispatcher.py`, 1/4/8/16 concurrent, 16 requests each | 64/64 passed the verifier; 477 tok/s at 16 concurrent |
| Full pipeline | Mina's `bus/server.py` (strict schema validation) + `bus/fake_scenario.py` (3 overlapping incidents with decoys) + `python -m dispatcher.run` with the model | 61/61 bus events valid, 0 invalid, 0 duplicate IDs; 13 dispatches; officers sent junction → real exit for all 3 incidents, **0 to a decoy**; fistfight medium / purse_snatch low; procedure line on every recommendation |
| Spotter-shaped input | Wali's label names (`stabbing` / `stealing` / `assault`), no `activity_confidence`, spotter `what_happened` text, 3 incidents from `labels.csv` | stabbing → high (rules, immediate); stealing → purse_snatch low; assault → fistfight medium; all to the real exit; 0 fallbacks (3 invalid-JSON first attempts recovered by the retry) |

## Tried, didn't help (kept honest)

- **Prefix caching:** `--enable-prefix-caching` is set, but `vllm:prefix_cache_queries_total` stayed 0; vLLM 0.11 doesn't apply it to this hybrid Mamba model. Not claimed.
- **Per-request `structured_outputs.disable_any_whitespace`:** accepted but ignored on vLLM 0.11 (output still has newlines). A server-side structured-outputs setting may work; not tried yet because it needs a server restart. The retry (#7) already removes the fallbacks.
- **Fine-tuning:** not done. After #1–#8 the model passes the verifier on every scenario we have, so there's no failing baseline to train against.

## Reproduce

```bash
# from a laptop: brev port-forward clarity --port 8003:8003
export CLARITY_LLM_BASE_URL=http://localhost:8003/v1 CLARITY_LLM_MODEL=dispatcher
python -m dispatcher.demo --live                       # demo incident (#2, #3, #4, #8)
python scripts/bench_dispatcher.py --levels 1 4 8 16   # throughput table (#1, final config)
python -m pytest -q                                    # every verifier rule and fallback path
```
