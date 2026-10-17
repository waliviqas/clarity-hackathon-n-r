# Integration: how the three parts plug together

The goal is that **integration is boring**: every part runs alone against fake inputs from the first hour, and real parts replace fakes one at a time.

## Ports and environment

All Python runs on the Brev GPU box. Copy `.env.example` to `.env` and adjust.

| Variable | Default | Used by |
|---|---|---|
| `CLARITY_BUS_URL` | `http://localhost:8080` | Everyone (publish / fetch) |
| `CLARITY_BUS_STRICT` | `1` | Bus: reject invalid events (set `0` for the demo) |
| `CLARITY_RUN_ID` | `run_dev` | Everyone: stamped on events, names the log folder |
| `CLARITY_CAMERAS` | `data/cameras.json` | Feeds, graph, bus, dashboard |
| `DISPATCHER_BASE_URL` | `http://localhost:8000/v1` | Dispatcher (Nemotron Nano 9B v2) |
| `DISPATCHER_MODEL` | `dispatcher` | Dispatcher (`--served-model-name`) |
| `SPOTTER_BASE_URL` | `http://localhost:8001/v1` | Spotter (Qwen3-VL-2B) |
| `SPOTTER_MODEL` | `spotter` | Spotter |
| `CHECKER_BASE_URL` | `http://localhost:8002/v1` | Checker (Nemotron Nano 12B v2 VL) |
| `CHECKER_MODEL` | `checker` | Checker |
| `EMBED_BASE_URL` / `RERANK_BASE_URL` | `http://localhost:8003` / `:8004` | Lookup (RAG) |
| `OPENAI_API_KEY` | `EMPTY` | OpenAI client (vLLM ignores it) |
| `VITE_BUS_URL` | `http://localhost:8080` | Dashboard (laptop) |

## Start order (Brev box)

1. Model servers (Michael, `infra/`): dispatcher :8000, spotter :8001, checker :8002, embed :8003, rerank :8004. Several servers on one GPU means splitting memory with `--gpu-memory-utilization` per server (FP8 checkpoints help). Bind every server to `127.0.0.1` and reach it only through `brev port-forward`; don't create public Brev tunnels for model or bus ports.
2. Bus on :8080 (Mina, `python -m bus.server`).
3. Dispatcher (Michael).
4. Camera agents (Wali).
5. Perception (Wali).
6. Feeds (Mina, `python -m feeds.replay`), which starts the clock.

**Dashboard (Mina's Windows laptop):**
1. `brev port-forward <instance> --port 8080:8080`
2. `cd dashboard && npm run dev`

## Fake modes (every part must have one)

| Part | Fake mode | Lets you test without |
|---|---|---|
| Bus | `python -m bus.fake_scenario`: publishes a scripted incident (detections → relays → verdicts → dispatch) built from `contracts/examples/` | Everyone else |
| Spotter / checker | `--fake`: emits detections from a JSONL script instead of calling the VLMs | GPU / VLMs |
| Relay agents | `--fake`: answers with rules instead of a model | Checker |
| Dispatcher | `--fake`: turns verdicts into dispatches with rules | Nano 9B v2, lookup |
| Dashboard | Connects to any bus; with `bus.fake_scenario` running it shows a full incident | Real pipeline |

## Integration checkpoints

| When | Checkpoint | Done when |
|---|---|---|
| **~1:00 PM Sat** | **CP0: contracts on `main`** | All three have pulled `contracts/`; any objections resolved |
| **~2:30 PM** | **CP1: fakes end-to-end** | Bus running on Brev; `bus.fake_scenario` shows a moving incident on the dashboard; each part publishes valid events in fake mode (`contracts/validate.py` on the run log passes) |
| **~5:00 PM** | **CP2: real pipeline, one scenario** | Real feeds → spotter → checker → relay → dispatcher on one staged scenario |
| **~6:30 PM** | **CP2b: three at once** | Three simultaneous incidents run end-to-end (the parallel-vLLM demo) |
| **~7:15 PM** | **CP3: insurance** | One full run recorded (screen capture + its `runs/<id>/events.jsonl` saved and pushed) before doors close at 8 PM |
| Sun 9:00–10:00 | CP4: final | Final numbers in the README; final demo recording |
| **Sun 10:30 AM** | **Submit** | Form submitted; 30 min buffer before the 11:00 freeze |

## Merging

- Work on your own branch; merge to `main` at each checkpoint.
- Before merging: run your part in fake mode and validate its output with `python contracts/validate.py runs/<run_id>/events.jsonl`.
- Changes to `contracts/` go in their own commit, with team agreement (see `contracts/README.md`).

## Demo-day fallbacks

1. **Pipeline breaks live:** `python -m bus.replay runs/<good_run>/events.jsonl` re-publishes a recorded run; the dashboard looks identical.
2. **Brev or network down:** the pre-recorded demo video is the submission anyway.
3. **A model misbehaves:** fake mode for that part, and say so honestly.
