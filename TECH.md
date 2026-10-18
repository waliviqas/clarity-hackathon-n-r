# Clarity: tech stack (Mina's part)

The tools and libraries behind Mina's part of Clarity (event bus, camera feeds, data, dashboard, camera agents, contracts, published clips, demo runs), built for the NVIDIA x Red Hat Small Models Hack, Oct 17–18, 2026.

Python versions are minimums from each folder's `requirements.txt`; dashboard versions are pinned in `dashboard/package.json`.

## Languages

- **Python 3.10+**: everything that runs on the GPU box (`bus/`, `feeds/`, `agents/`, `data/`, `contracts/validate.py`).
- **TypeScript 7.0.2 + TSX**: the dashboard (`dashboard/src/`, strict mode, `tsc --noEmit`) and its check scripts (`dashboard/scripts/`).
- **CSS**: plain CSS with design tokens as custom properties (`dashboard/src/tokens.css`); no CSS framework.
- **JSON / JSONL / CSV**: events, camera maps and ground truth (JSON), run logs (JSONL), clip logs and training-clip lists (CSV).

## Backend / event bus (`bus/`)

- **FastAPI (>=0.110)**: `bus/server.py`: `POST /events`, `GET /events?type=&since_ts=`, `GET /cameras`, `GET /clips/{camera_id}`, `GET /health`, `WS /ws`; CORS limited to the dashboard origin (port 5173).
- **Starlette (>=0.39)**: `FileResponse` with HTTP Range, so the dashboard's `<video>` can seek in a camera's clip.
- **Uvicorn (>=0.29) + websockets (>=12)**: serves the bus on port 8080 and the WebSocket stream (a `bus_snapshot` first, then one event per message, broadcast with `asyncio`).
- **JSONL run logs**: every accepted event is appended to `runs/<run_id>/events.jsonl`, plus `arrivals.jsonl` (when the bus accepted it).
- **Python standard library only** for `bus/client.py` (`urllib.request`, 1 s timeout, never raises), `bus/fake_scenario.py` (scripted incidents), `bus/replay.py` (re-publish a log with `--speed` / `--max-gap`), `bus/metrics.py` (latencies and overlap into `metrics.json`) and `bus/demo_trio_lookout.py` (scripted far re-sighting).
- **httpx (>=0.27)**: test-only dependency for FastAPI's `TestClient`.

## Video & data processing (`feeds/`, `data/`)

- **OpenCV, `opencv-python-headless` (>=4.9)**: `feeds/base.py` decodes clips, samples all cameras on one run clock (`FramePacket`, `open_feeds`, `FrameBuffer`) and shrinks frames to 960 px wide; `feeds/fake_clips.py` writes synthetic test clips.
- **NumPy (>=1.26)**: frame arrays (H x W x 3, BGR, uint8) in `feeds/`.
- **FFmpeg + ffprobe** (system install): `data/convert_clips.py` (iPhone HEVC to 720p, constant 10 fps, H.264, audio removed); `data/publish_clip8.py` (box blur over passers-by, metadata stripped, ffprobe checks, review contact sheets); `data/publish_clip1.py` (stream copy without audio or metadata, `framemd5` frame check); `data/review_sheets.py`; `data/scripts/fetch_*.py` (cutting public training clips).
- **Python standard library** (`csv`, `json`, `xml.etree.ElementTree`, `subprocess`): `data/build_site.py` (clip log CSV to `cameras.json`, ground truth and manifests), `data/check_build_site.py` (golden-file checks), `data/name_cameras.py` and `data/idle_cameras.py` (parse an OpenStreetMap XML extract).
- **`git show <ref>:<path>`**: `data/gym_answers.py` reads Wali's NeMo Gym results from his branch without checking it out and writes recorded answers to `data/answers/`.
- **pandas** (not in a requirements file): CSV checks in `data/scripts/check_staged_clips.py`.
- **yt-dlp and AWS CLI** (`aws s3 cp --no-sign-request`): optional downloaders in `data/scripts/fetch_staged_clips.py`.

## Camera agents (`agents/`)

- **Plain Python, no model inside the agents**: `network.py` (one inbox per camera, relays, deadlines), `matching.py` (field-by-field description match, noisy-OR, travel-time check), `adapter.py` (spotter answer to `detection` event), `combine.py` (spotter + checker answers merged), `answers.py` (recorded answer files), `run.py` (run clock, CLI).
- **`threading` + `concurrent.futures`**: `agents/run.py` starts model calls per camera in parallel, so vLLM can batch them.
- **openai (>=1.40, <=3.24.0)**: installed for `--live`, where the agents import Wali's `src/spotter.py` and `src/checker.py` unchanged, which call vLLM through it. Capped at a release 2+ weeks old (hackathon rule).
- **OpenCV**: clip lengths for the run clock.
- **unittest**: `agents/tests/` (`python -m unittest discover -s agents/tests -t .`).

## Frontend (dashboard, `dashboard/`)

- **React 19.3.0 + react-dom 19.3.0**: UI (map, agent graph, incident cards, receipts log, live feeds, sighting video pop-up).
- **Vite 8.3.1 + @vitejs/plugin-react 6.1.1**: dev server and build, fixed to `127.0.0.1:5173` (`strictPort`).
- **Leaflet 1.9.4 + react-leaflet 5.0.0** (`@types/leaflet` 1.9.22): camera markers, chase paths, relay arrows, dashed predictions.
- **OpenStreetMap tiles** (`tile.openstreetmap.org`): base map, darkened with a CSS filter, "© OpenStreetMap contributors" shown.
- **@fontsource** Public Sans 5.3.0, Barlow Semi Condensed 5.3.0, Barlow ^5.3.0: self-hosted fonts.
- **Browser APIs**: `WebSocket` (bus stream with auto-reconnect), `fetch` (`GET /cameras`, `POST /events` for `operator_action`), HTML `<video>` (clips from `GET /clips`).
- **Node 24 + npm**: runs the TypeScript check scripts directly (`check:store`, `check:labels`, `check:chase`, `check:text`).
- **Config**: `VITE_BUS_URL`, `VITE_CONTROL_URL` in `dashboard/.env`.

## Contracts & validation (`contracts/`)

- **JSON Schema draft 2020-12**: 7 schemas (`cameras`, `detection`, `relay`, `agent_verdict`, `dispatch`, `operator_action`, `camera_status`) plus one example each in `contracts/examples/`.
- **jsonschema (>=4.18)**, `Draft202012Validator`: `contracts/validate.py` checks JSON and JSONL files from the command line; `bus/server.py` calls its `check()` and rejects invalid events with HTTP 422.
- The examples double as fixtures for the dashboard's `check:store` script.

## Data & open datasets (`data/`)

- **Our staged clips** (13 clips, 34 iPhone camera views, filmed Oct 17): clips 8 and 1 published under **CC BY 4.0** on Hugging Face as `WilwilMina/clarity-clip8` (passers-by blurred) and `WilwilMina/clarity-clip1`, both without audio or file metadata; dataset cards in `data/staged/DATASET_CARD*.md`, method in `data/staged/README.md`.
- **OpenStreetMap** (**ODbL**): dashboard tiles, and the `data/osm/annex.osm` extract (OSM API) used for camera names and idle camera dots.
- **MEVA** (**CC BY 4.0**): example clips in the external check and cut training clips, listed in `data/training/`.
- **CAVIAR** (**CC BY-SA**): external-check clips, listed in `data/training/`.
- **AIRTLab** (research and education only, link only) and **Mixkit** (Mixkit Stock Video Free License, link only): training-clip lists, used only in rejected spotter versions v4 and v5.
- Considered, not used: the Hugging Face MEVA subset `Voxel51/extended_video_activities_drop_4`, UCF-Crime, RWF-2000 (reasons in `data/README.md`).

## Infrastructure & runtime

- **NVIDIA Brev GPU box** (Linux, one A100 80 GB): runs all Python (bus, feeds, camera agents) next to the model servers; Python venv + `pip install -r requirements.txt`; tmux for long-running processes. Runbook: README.md, "Reproduce the demo".
- **Ports**: bus 8080 (bound to `127.0.0.1`), dashboard 5173 on the laptop; model servers 8002 (checker), 8003 (coordinator), 8005 (fine-tuned spotter), 8001 (base spotter, comparison only); demo controls 8090.
- **Laptop to box**: `brev port-forward <instance> --port 8080:8080` for the bus; an SSH tunnel for port 8090.
- **Configuration through environment variables** (`.env.example`): `CLARITY_BUS_URL`, `CLARITY_RUN_ID`, `CLARITY_CAMERAS`, `CLARITY_CLIP_ROOT`, `CLARITY_BUS_STRICT`, `CLARITY_BUS_CORS`, `CLARITY_RUNS_DIR`.
- **Recorded runs** (`runs/`): `events.jsonl`, `arrivals.jsonl`, `metrics.json`, `answers.json` and a `RUN.md` per run, replayable with `python -m bus.replay`.
- **curl**: downloads the published clips from Hugging Face onto the box.

## Integrates with (teammates' parts)

- **vLLM 0.11.0** (Michael, `infra/`; OpenAI-compatible API): the camera agents' `--live` mode reaches the fine-tuned **Qwen3-VL-2B** spotter (`spotter-ft`, port 8005) and the **Nemotron Nano 12B v2 VL** checker (port 8002) through Wali's `src/` clients.
- **Michael's dispatcher** (`dispatcher/`, **Nemotron Nano 9B v2** on port 8003): reads agent events and `operator_action` from the bus and publishes `dispatch` events the dashboard shows.
- **Wali's NeMo Gym results** (`results/`, `nemo_gym/`): converted into recorded answers by `data/gym_answers.py`.
- **Wali's `scripts/demo_control.py`** (port 8090): Run / Stop / Restart behind the dashboard's hidden demo controls.
- **Wali's Hugging Face dataset** `waliviqas/clarity-crime-clips`: source of clip 3's views for the `annex_duo` site.

## Dev tooling

- **Git + GitHub** (`waliviqas/clarity-hackathon-n-r`; branches `Mina`, `Integration`, `main`).
- **Claude Code**: development tool only, for writing and reviewing code and docs; no hosted or closed model runs in Clarity (README, "How we built it").
- **Hugging Face Hub**: dataset upload by web UI or `huggingface-cli upload` (steps in the dataset cards).
- **Checks**: `contracts/validate.py`, `data/check_build_site.py`, `python -m feeds.replay --check`, `agents/tests/`, `npm run build` and the dashboard check scripts.
