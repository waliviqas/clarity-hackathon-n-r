# Run run_trio_lookout: three crimes at once, then Route 2's suspect picked up 30 minutes later

**Routes 3 and 4 are real recorded model answers run through the real camera agents. Route 2 and the `cam_14` pickup are scripted from ground truth.** Route 2 (test clip 7) is a pickpocket: the suspect takes the man's phone. The model typed it "assault" (so `fistfight`), so for this demo Route 2 is scripted from its ground truth as `purse_snatch`. The coordinator is Michael's real dispatcher in rules mode. No model ran during this run, so its timings are the run clock's pacing, not model latency. Every scripted event has `source: fake_scenario`, so the dashboard labels it as scripted.

- **When:** Sun Oct 18, 2026, 08:38-08:39 ET, on Mina's laptop (temporary bus on a temporary port and runs folder).
- **Cameras:** `data/sites/annex_trio_lookout/cameras.json`:
  - Route 2 (test clip 7, `cam_04`-`cam_06`): as in `data/sites/annex_trio/`.
  - Route 3 (test clip 1, `cam_07`-`cam_10`): on Wali's aligned spots from his updated take-3 log.
  - Route 4 (test clip 3, `cam_11`-`cam_13`): on Wali's demo3 spots for the same clip files (`data/sites/demo3/cameras.json`: 35.77575,-78.637 / 35.7755,-78.6373 / 35.7756,-78.6371).
  - `cam_14` "Hillsborough St sidewalk": no neighbor of any route.
- **Producers** (repo root, `CLARITY_RUN_ID=run_trio_lookout`, bus started with `CLARITY_CAMERAS=data/sites/annex_trio_lookout/cameras.json`):
  1. `python -m bus.server` (strict validation)
  2. Michael's real dispatcher, `python -m dispatcher.run --no-model` (rules mode), from main at f8c5342
  3. These two started at the same moment, so their run clocks line up:
     - `python -m agents.run --answers data/answers/duo_system_v3_checker.json --cameras data/sites/annex_trio_lookout/cameras.json --speed 1`. Recorded answers exist for clips 1 and 3 only, so the agents of `cam_04`-`cam_06` and `cam_14` stay silent.
     - `python -m bus.fake_scenario --ground-truth runs/run_trio_lookout/take2_ground_truth.json --lookout cam_14 --cameras data/sites/annex_trio_lookout/cameras.json --speed 1 --max-gap 45`

`take2_ground_truth.json` is a copy of `data/ground_truth/annex_trio/take2.json` with two changes, because the unchanged `fake_scenario` refuses the original on this site:
- `site_id` is set to `annex_trio_lookout` (the original is for site `annex_trio`).
- `cam_14` is added as the last path step, role `lookout`, at 1818.3-1819.55 (clip seconds 1.25-2.5). Without it: "--lookout cam_14 must be the last camera on the path".

`--max-gap 45` (not 5) while recording: with 5, `fake_scenario` would also squeeze its first 16 s and publish the pickup (ts 1818) about 13 s into the run, while the agents were still publishing. The dispatcher polls only from its newest ts minus 30 s, so it would then miss every later event of Routes 3 and 4. With 45, Route 2 runs at true run-clock time and the pickup goes out 65 s in, after the agents finished (36 s). The replay still uses `--max-gap 5`.

## What happens (run clock, seconds)
| ts | Event | Ids |
|---|---|---|
| 0 | `camera_status` online for all 11 cameras (scripted) | `cst_cam_04_b8d736_0` ... |
| 8.9 | Route 3: crime detection at `cam_07` (spotter: crime/assault, so `fistfight`), relay to `cam_08`; the coordinator opens `inc_rf545_1` (tracking) | `det_a39ee_1`, `rel_a39ee_1`, `dsp_rf545_01` |
| 13.6 | Route 4: crime detection at `cam_11` (`stabbing`); `inc_rf545_2` opens as an alert at once | `det_a39ee_2`, `dsp_rf545_02` |
| 16.45 | Route 2 (scripted): crime detection at `cam_05` (`purse_snatch`); relay to `cam_06` at 16.95; `inc_rf545_3` opens (tracking) | `det_take2_b8d736_1`, `rel_take2_b8d736_1`, `dsp_rf545_03` |
| 17.0 / 28.1 / 34.96 | Route 3: "match" at `cam_08`, `cam_09`, `cam_10` (alert from 17.0 on) | `ver_a39ee_1`, `_3`, `_5` |
| 19.95 | Route 2 (scripted): "match" at `cam_06`; the incident becomes an alert | `ver_take2_b8d736_1`, `dsp_rf545_05` |
| 24.6 / 33.0 | Route 4: "match" at `cam_12`, `cam_13` | `ver_a39ee_2`, `_4` |
| 23.7-1818.3 | Route 2's trail goes cold (29.9 min after the suspect left `cam_06`'s view) | |
| 1818.3 | **Scripted:** `cam_14` sees someone run past (detection, `on_screen: fleeing`, "black hoodie, dark grey trousers") | `det_take2_b8d736_3` |
| 1818.55 | **Scripted:** lookout relay `cam_06` -> `cam_14` (`basis: lookout`, "Lookout: description match, trail cold 30 min. ...", no expected arrival, no direction); the coordinator predicts `cam_14` | `rel_take2_b8d736_2`, `dsp_rf545_10` |
| 1818.8 | **Scripted:** "match" at `cam_14`. The coordinator updates Route 2's incident (see below) | `ver_take2_b8d736_2`, `dsp_rf545_11` |

Final state:
| Incident | Route | Status | Path |
|---|---|---|---|
| `inc_rf545_1` | 3 | `fistfight` / medium, alert | `cam_07` -> `cam_08` -> `cam_09` -> `cam_10` |
| `inc_rf545_2` | 4 | `stabbing` / high, alert | `cam_11` -> `cam_12` -> `cam_13` |
| `inc_rf545_3` | 2 | `purse_snatch` / low, alert | `cam_05` -> `cam_06` -> `cam_14` |

Route 2's last dispatch (`dsp_rf545_11`): "Operator review needed. Send officer to Hillsborough St sidewalk (cam_14); purse snatch at Route 2: sidewalk by bollard (cam_05) Procedure: take the victim's statement and broadcast the suspect description." Reason: "purse snatch detected (conf 0.80); subject confirmed at 3 camera(s)".

"Watch last sighting" on `dsp_rf545_11` plays `cam_14`'s clip, test clip 8's cam2: the sighting is 1.75 s into it (`start_ts` 1817.05), and the suspect is in view from 1.25 to 2.5 s. The bus serves it at `GET /clips/cam_14`.

## What is real and what is not (say this on screen)
| Part | In this run |
|---|---|
| Camera views | Real: test clips 7, 1 and 3 (`cam_04`-`cam_13`) and test clip 8's cam2 (`cam_14`), all filmed by the team near the Red Hat Annex on Oct 17 |
| Routes 3 and 4 (clips 1 and 3): spotter + checker answers | **Real model output, recorded** (`data/answers/duo_system_v3_checker.json`: fine-tuned spotter v3 + checker Nemotron Nano 12B v2 VL, 8 frames, NeMo Gym runs at temperature 0, not live calls) |
| Routes 3 and 4: camera agents (relays, verdicts) | Real code (`agents/`), run on those answers |
| Route 2 (clip 7): crime, relay, "match" at `cam_06` | **Scripted** from its ground truth (`bus.fake_scenario`). It's a pickpocket (the phone is taken); the model typed it "assault", so this demo doesn't use the model's answer for it. The relay text, "Snatched something from a person's hand and ran off.", is `fake_scenario`'s built-in line for `purse_snatch` |
| The `cam_14` pickup (detection, lookout relay, verdict) | **Scripted** (`bus.fake_scenario --lookout cam_14`) |
| `cam_14`'s map position | Placed on Hillsborough St for this story: 35.7854, -78.6603, a public sidewalk near NC State, 2.27 km from `cam_05` (about a 30-minute walk). Its footage was **not** filmed there: clip 8's cam2 was filmed about 4 min after clip 7 (16:43:28 vs 16:39:30 for clip 7's crime view) about 60 m from clip 7's cameras (56-67 m by the phones' GPS fixes; clip 8 cam2's fix is +/-26 m). Times and fixes: Wali's `camera_positions.csv` |
| The ~30-minute gap | **Set for this story** (`cam_14`'s `start_ts` 1817.05). The same actor, in the same black hoodie, is the suspect in clips 7 and 8 |
| Coordinator | Real code, **rules mode** (`--no-model`): 11 dispatches over three incidents |
| Bus | Real, strict validation |

**Known model error, say it on screen:** clip 1 (Route 3) is a mimed stabbing, but the spotter called it an assault, so that incident is `fistfight` / medium.

## Event counts
46 events, all valid (`python contracts/validate.py runs/run_trio_lookout/events.jsonl`: 46/46).

| Type | Count | | Source | Count |
|---|---|---|---|---|
| camera_status | 11 | | fake_scenario | 18 |
| detection | 10 | | agents | 17 |
| relay | 7 | | dispatcher | 11 |
| agent_verdict | 7 | | | |
| dispatch | 11 | | | |

No operator action was recorded; Confirm / Dismiss happen live during the replay.

## Pacing
Everything up to 35 s ran at real speed. The 30-minute cold trail took 45 s of wall time while recording (`--max-gap 45`), so `arrivals.jsonl` (when the bus accepted each event) shows a 29 s pause after the agents' last event. Every event's `ts` is the true run clock.

## Replay (the demo)
Start the bus with a NEW run id and this site's cameras, don't run a dispatcher, then replay:
```
CLARITY_RUN_ID=<new id> CLARITY_CAMERAS=data/sites/annex_trio_lookout/cameras.json python -m bus.server
python -m bus.replay runs/run_trio_lookout/events.jsonl --speed 1 --max-gap 5
```
About 37 s: the three chases at true times (pauses capped at 5 s), the 30-minute cold trail as a 5-second pause, then the pickup at `cam_14`. Checked onto a fresh temporary bus: 46/46 valid, the replayed log byte-identical to this one, `GET /clips/cam_14` 200 `video/mp4` (Range 206). The dashboard fits the map to all cameras, so with `cam_14` 2.3 km away the Annex cameras sit close together.

## Times shown on the dashboard

The live-feeds panel shows each sighting as a time of day. Every camera in `data/sites/annex_trio_lookout/cameras.json` carries `recorded_at`, the real time its clip started (the team's camera-position sheet). The clips are the full recordings (each file's length matches the sheet's duration within 0.2 s), so a sighting's time is `recorded_at` plus its seconds into the clip (`ts - source.start_ts`): clip 1 from 4:05:12 PM, clip 3 from 4:13:56 PM, Route 2's pickpocket at 4:39:34 PM. The one exception is `cam_14`: its `recorded_at` is set by hand so the Hillsborough St pickup shows exactly 30 minutes after Route 2's crime, 5:09:34 PM (a demo choice; its footage, clip 8 cam2, was really filmed at 4:43:28 PM about 200 m away).
