# Run run_live_1025: first live run, cold dispatcher model

**Everything live: the fine-tuned spotter, the checker, the camera agents and the dispatcher model all ran on real clip frames.**

- **When:** Sun Oct 18, 2026, ~06:25 ET, on the Brev box, by Michael.
- **Code:** Integration `5d7eb59`.

## Setup
- **Where:** the team's Brev box (one NVIDIA A100 80 GB), vLLM 0.11.0, all models live (nothing scripted, nothing replayed).
- **Models:** spotter-ft v3 (fine-tuned Qwen3-VL-2B, `:8005`, 0.20 of the GPU) + checker Nemotron Nano 12B v2 VL (`:8002`, 0.40; describes the suspect on cameras the spotter flags) + dispatcher Nemotron Nano 9B v2 (`:8003`, 0.30). Base spotter `:8001` off. GPU in use: ~75 of 80 GB.
- **Cameras:** `data/sites/annex_clip1/cameras.json`, test clip 1's four views (`data/raw/staged/take3/clip1_cam1-4.mp4`, from https://huggingface.co/datasets/WilwilMina/clarity-clip1).
- **Commands** (repo root, env from `.env.example` with `CLARITY_CAMERAS=data/sites/annex_clip1/cameras.json`, `SPOTTER_URL=http://localhost:8005/v1`, `SPOTTER_MODEL=spotter-ft`, `CHECKER_BASE_URL=http://localhost:8002/v1`, `CHECKER_MODEL=checker`, `CLARITY_LLM_BASE_URL=http://localhost:8003/v1`, `CLARITY_LLM_MODEL=dispatcher`):
  - `python -m bus.server` (strict schema validation)
  - `python -m dispatcher.run` (model on)
  - `python -m agents.run --live --frames 8 --save-answers runs/<run id>/answers.json`

## What is real
| Part | In this run |
|---|---|
| Camera views | Real: test clip 1 (held out from training) |
| Spotter, checker, camera agents | **Real, live** on the clip frames (8 per camera). `answers.json` = what the models said |
| Coordinator | Real: Nemotron Nano 9B v2 on vLLM, model on |
| Bus | Real, strict validation |
| Operator | No operator action in this run (no dashboard attached) |

**Known model error, say it on screen:** clip 1 is a stabbing, but the spotter called cam 1 an assault, so the incident is `fistfight` / medium. This matches Wali's NeMo Gym results for clip 1 (assault in 3/3 runs; crime-type accuracy 33%).

## Replay
Restart the bus with a NEW run id and the same cameras file, don't run a dispatcher during the replay, then:
`python -m bus.replay runs/run_live_1025/events.jsonl --speed 1`

## Result
- **Chase:** crime at cam_07 (spotter: crime/assault → `fistfight`), suspect matched at cam_08, cam_09, cam_10 (confidence 0.95 each), each camera's suspect described by the checker (black hoodie, black pants/jeans, black sneakers).
- **Dispatches:** alert at the crime camera, then "Send officers to cam_08 / cam_09 / cam_10 to intercept the subject" as the suspect moves, then "Check on the victim at cam_07", each with the fistfight procedure line.
- **Events:** 13 events, all valid: detection 4, relay 3, agent_verdict 3, dispatch 3 (agents 10, dispatcher 3).
- **Timing:** **Crime detection → first alert: 21.9 s wall** (`metrics.json`). The dispatcher model had just started: its first request compiles the JSON grammar and warms up. Fixed afterwards with a warm-up request at `dispatcher.run` startup (see `run_live2_1027`: 1.6 s).

`metrics.json` comes from `python -m bus.metrics runs/run_live_1025`.
