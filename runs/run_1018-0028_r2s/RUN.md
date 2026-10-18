# Run run_1018-0028_r2s: clip-8 insurance recording

- **When:** Sun Oct 18, 2026, 00:28–00:31 ET, on Mina's laptop.
- **Rung:** 2s-real. Scripted perception on the real Annex site, with Michael's real dispatcher deciding.
- **Cameras:** `data/sites/annex/cameras.json`, test clip 8, three camera views placed in route order.
- **Producers:**
  - `python -m bus.fake_scenario --ground-truth data/ground_truth/take1.json --cameras data/sites/annex/cameras.json --speed 1`
  - Michael's `dispatcher.run --no-model` from `origin/Michael` 56712cc, unmerged and run from a `git archive` copy.
  - Dashboard (Vite dev server) on 127.0.0.1:5173.

## What is real and what is not (say this on screen)
| Part | In this run |
|---|---|
| Camera views | Real: test clip 8's three blurred views (shown in the dashboard's Watch last sighting pop-up) |
| Spotter and camera agents | **Scripted**, from clip 8's ground truth (`source: fake_scenario`). The dashboard header shows a **Scripted run** tag. |
| Coordinator | Real code, **rules mode** (`--no-model`; the 9B model was stopped while Wali's fine-tune used the GPU). Label it "coordinator: rules mode". |
| Bus, dashboard, operator Confirm | Real |

## Event counts
16 events, all valid (`python contracts/validate.py runs/run_1018-0028_r2s/events.jsonl`: 16/16).

| Type | Count | | Source | Count |
|---|---|---|---|---|
| camera_status | 3 | | fake_scenario | 10 |
| detection | 3 | | dispatcher | 5 |
| relay | 2 | | dashboard | 1 |
| agent_verdict | 2 | | | |
| dispatch | 5 | | | |
| operator_action | 1 (confirm) | | | |

The dispatcher raised the alert at the first confirmed match (run clock 13.0 s): "Send officer to Route 1: covered walkway (cam_03)". The operator confirmed it from the dashboard.

## Replay
Restart the bus with a NEW run id and the same cameras file, and don't run a dispatcher during the replay. Then:
```
CLARITY_RUN_ID=<new id> CLARITY_CAMERAS=data/sites/annex/cameras.json python -m bus.server
python -m bus.replay runs/run_1018-0028_r2s/events.jsonl --speed 1
```

The screen video of this run is kept off git (Mina's laptop).
