# Clarity: notes for Claude Code (team-wide)

Clarity watches multiple cameras, tracks a subject across them, and tells an operator where to send officers. Three parts, three owners:

| Part | Owner | Lives in |
|---|---|---|
| Feeds, message bus, dashboard, contracts, data | Mina | `bus/`, `contracts/`, `data/`, dashboard |
| Spotter (fine-tuned Qwen3-VL-2B), checker, camera agents, camera graph | Wali | his branch (`graph/` provides `predict_next`) |
| Dispatcher (Nemotron Nano 9B v2 on vLLM) | Michael | `dispatcher/`, `scripts/bench_dispatcher.py`, `tests/` |

**Rules for everyone**
- `contracts/` (Mina, v0.1) is the single source of truth for every message. Don't rename or remove fields in your own code; propose changes to the team first.
- Don't edit another owner's folder. If you need a change there, say so and tell the owner.
- Branches: each person pushes to their own branch. Merging happens on `integration`; `main` is only updated once the full pipeline runs, so it always works for recording the demo.
- Before any push: run the tests and check the diff for secrets (keys, tokens, invite links, personal emails or paths). Never commit `data/raw/`.

Add a section for your own part below. Keep it about how others plug into it.

---

## Dispatcher (Michael): how to plug into it

Full details: `dispatcher/README.md`. Change-by-change measurements (vLLM bounty evidence): `dispatcher/IMPROVEMENTS.md`.

**What it reads from the bus:** `detection`, `relay`, `agent_verdict`, `operator_action`. **What it publishes:** `dispatch` (one per incident change; the dashboard keeps the latest per `incident_id`).

**Run it** (from the repo root, once `bus/` and `contracts/` are merged):
```bash
export CLARITY_BUS_URL=http://127.0.0.1:8080
export CLARITY_LLM_BASE_URL=http://localhost:8003/v1 CLARITY_LLM_MODEL=dispatcher   # vLLM on the Brev box
python -m dispatcher.run                 # cameras come from GET /cameras on the bus
python -m dispatcher.run --no-model      # rules only, if the dispatcher model isn't being served
```
The dispatcher model is served by vLLM on port 8003 (serve command in `dispatcher/README.md`). It's currently **stopped** to give Wali's fine-tune the GPU; restart it before an end-to-end run.

**What the dispatcher needs from Wali's agents** (all already in the contract):
- `detection.activity` from the closed enum `stabbing | fistfight | purse_snatch | none`. `"none"` means no incident; anything else starts one. The dispatcher also accepts the spotter's `labels.csv` names (`assault` → `fistfight`, `stealing` → `purse_snatch`), but the bus validates against the contract, so the agents should send contract names until the team renames the enum.
- `camera_id` must match `cameras.json` and the contract pattern (`cam_01`, not the clip folder name `cam1`).
- `detection.direction` = the subject's observed movement. The dispatcher uses it to tell the real exit from a decoy. A `relay.direction` is only used when no detection has one.
- Every `relay` / `agent_verdict` carries the `subject_id` and cites the detections it's based on in `evidence_event_ids`. That's how detections get attached to an incident.
- On a `match`, send the relay to the next cameras *from the matching camera* (as the contract says). Relays from older cameras are treated as stale.
- Optional: a top-level `graph` package exposing `predict_next(camera_id: str, direction: str | None) -> [{"camera_id", "probability"}]`. If importable, `dispatcher.run` uses it automatically; otherwise the dispatcher's built-in prediction is used. It's called from one thread, so it doesn't need to be thread-safe.

**What the dispatcher needs from Mina's bus:** `bus.client.fetch(type, since_ts)` and `publish(event)` exactly as documented in `contracts/README.md`, plus `GET /cameras`. Repeated events from the lookback window are skipped by `event_id`.

**IDs:** each dispatcher process tags its IDs, e.g. `inc_r3fa9_1` / `dsp_r3fa9_01`, so restarts and other producers (like `bus/fake_scenario.py`'s stand-in dispatches) can't collide. Use the `incident_id` from the latest `dispatch` when sending an `operator_action`.

**Priorities (team decision):** stabbing high, fistfight medium, purse_snatch low. Only a stabbing is auto-alerted by rules; everything else goes to the model, capped at its priority. Every recommendation ends with a fixed procedure line for its incident type, written by code (`dispatcher/guidance.py`).

**Verified so far:** with Mina's `bus/server.py` + `bus/fake_scenario.py` (3 overlapping incidents with decoys), the bus accepted every dispatch under strict schema validation, and officers were never sent to a decoy.
