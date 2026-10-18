<!-- Lives in dispatcher/ (not the repo root) so it doesn't clash with teammates' local root CLAUDE.md files. -->
# Dispatcher (Michael): notes for Claude Code

**Ground rules:** `contracts/` (Mina, v0.1) is the source of truth for every message. Don't edit `dispatcher/` from another part without telling Michael. Merging happens on `integration`; `main` only gets the full working pipeline. Check diffs for secrets before pushing.

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
- **Spotter → detection (whoever writes that adapter):** the spotter (`src/spotter.py`) returns per-clip JSON without headers, confidence, direction, or `subject_id`. A contract `detection` needs `type/schema_version/event_id/ts`, `camera_id`, `track_id`, `confidence`, `activity` (map `crime`; contract names, see above), `appearance` (join the suspect fields into one string), and `direction` (or `null`). Please also copy the spotter's `what_happened` and `on_screen` into the detection as extra fields: the dispatcher's model reads them. Omit `activity_confidence` if the spotter has none (don't send `null`). If `confidence` is only a placeholder, send `confidence_known: false` and the dispatcher treats the confidence as unknown. Relays sent onward after an `uncertain` verdict should carry `basis: "possible"`: the dispatcher doesn't count them as confirmed sightings in `path`.
- **Incidents only start from `relay` / `agent_verdict`** (they carry the `subject_id`). Detections alone never create an incident, so the camera agents (or some linker) must publish relays/verdicts for anything to reach the dashboard.
- `detection.direction` = the subject's observed movement. The dispatcher uses it to tell the real exit from a decoy. If no detection has one, it uses the direction of the relay that brought the subject to its latest camera (never relays going out of it, since those go to every neighbor).
- Every `relay` / `agent_verdict` carries the `subject_id` and cites the detections it's based on in `evidence_event_ids`. That's how detections get attached to an incident.
- On a `match`, send the relay to the next cameras *from the matching camera* (as the contract says). Relays from older cameras are treated as stale.
- Optional: a top-level `graph` package exposing `predict_next(camera_id: str, direction: str | None) -> [{"camera_id", "probability"}]`. If importable, `dispatcher.run` uses it automatically; otherwise the dispatcher's built-in prediction is used. It's called from one thread, so it doesn't need to be thread-safe.

**What the dispatcher needs from Mina's bus:** `bus.client.fetch(type, since_ts)` and `publish(event)` exactly as documented in `contracts/README.md`, plus `GET /cameras`. Repeated events from the lookback window are skipped by `event_id`.

**IDs:** each dispatcher process tags its IDs, e.g. `inc_r3fa9_1` / `dsp_r3fa9_01`, so restarts and other producers (like `bus/fake_scenario.py`'s stand-in dispatches) can't collide. Use the `incident_id` from the latest `dispatch` when sending an `operator_action`.

**Priorities (team decision):** stabbing high, fistfight medium, purse_snatch low. A stabbing is alerted by rules immediately, even with unknown confidence (a known low confidence or an `uncertain` verdict sends it to the model instead); fistfight / purse_snatch go to the model (capped at their priority) and become `alert` as soon as a camera agent confirms a `match` downstream, so the operator gets the Confirm/Dismiss decision. A missing `activity_confidence` falls back to the detection's `confidence`; if both are missing the incident goes to the model rather than being dropped. Every recommendation ends with a fixed procedure line for its incident type, written by code (`dispatcher/guidance.py`).

**Verified so far:** with Mina's `bus/server.py` + `bus/fake_scenario.py` (3 overlapping incidents with decoys), the bus accepted every dispatch under strict schema validation, and officers were never sent to a decoy.
