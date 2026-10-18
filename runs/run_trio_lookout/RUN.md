# Run run_trio_lookout: three crimes at once, then Route 2's suspect picked up 30 minutes later

**The three crimes are real recorded model answers run through the real camera agents; only the `cam_14` pickup is scripted.** The camera agents (`agents/`) replayed Wali's recorded final-system answers (fine-tuned spotter v3 + checker Nemotron Nano 12B v2 VL, 8 frames, temperature 0, recorded in NeMo Gym, not live calls). The coordinator is Michael's real dispatcher in rules mode. No model ran during this run, so its timings are the run clock's pacing, not model latency. The 3 scripted events have `source: fake_scenario`, so the dashboard labels them as scripted.

- **When:** Sun Oct 18, 2026, 07:43-07:44 ET, on Mina's laptop (temporary bus on a temporary port and runs folder).
- **Cameras:** `data/sites/annex_trio_lookout/cameras.json`: the ten cameras of `data/sites/annex_trio/` unchanged (Route 2 = test clip 7, `cam_04`-`cam_06`; Route 3 = test clip 1, `cam_07`-`cam_10`; Route 4 = test clip 3, `cam_11`-`cam_13`) plus `cam_14` "Hillsborough St sidewalk", which is no neighbor of any of them.
- **Producers, in start order** (repo root, `CLARITY_RUN_ID=run_trio_lookout`, `CLARITY_CAMERAS=data/sites/annex_trio_lookout/cameras.json`):
  1. `python -m bus.server` (strict validation)
  2. Michael's real dispatcher, `python -m dispatcher.run --no-model` (rules mode), from branch Integration at 49f6ac9
  3. `python -m agents.run --answers data/answers/trio_system_v3_checker.json` (speed 1; `cam_14` has no recorded answer, so its agent stays silent)
  4. after the agents finished: `python -m bus.demo_trio_lookout` (the scripted pickup: reads Route 2's subject from the bus, publishes 3 events)

## What happens (run clock, seconds)
| ts | Event | Ids |
|---|---|---|
| 8.9 | Route 3: crime detection at `cam_07` (spotter: crime/assault, so `fistfight`), relay to `cam_08`; the coordinator opens `inc_r950c_1` (tracking) | `det_addd5_1`, `rel_addd5_1`, `dsp_r950c_01` |
| 13.6 | Route 4: crime detection at `cam_11` (`stabbing`); `inc_r950c_2` opens as an alert at once | `det_addd5_3`, `dsp_r950c_02` |
| 17.0 / 28.1 / 34.96 | Route 3: "match" at `cam_08`, `cam_09`, `cam_10` (alert from 17.0 on) | `ver_addd5_1`, `_4`, `_6` |
| 18.3 | Route 2: crime detection at `cam_05` (spotter: crime/assault, so `fistfight`), relays to `cam_04` and `cam_06`; `inc_r950c_3` opens (tracking) | `det_addd5_5`, `rel_addd5_4`, `rel_addd5_5`, `dsp_r950c_04` |
| 24.6 / 33.0 | Route 4: "match" at `cam_12`, `cam_13` | `ver_addd5_2`, `_5` |
| 25.65 | Route 2: `cam_06` answers "uncertain" ("Hair, shoes, build, height, glasses match; shirt, pants differ"). Route 2's chase ends here | `det_addd5_7`, `ver_addd5_3` |
| 57.3 | Route 2: `cam_04` (the approach view) answers "no_match" | `ver_addd5_7` |
| 57.3-1818.3 | The trail goes cold (29.9 min after `cam_06` saw the runner) | |
| 1818.3 | **Scripted:** `cam_14` sees someone run past (detection, `on_screen: fleeing`, "black hoodie, dark grey trousers") | `det_lookout_708051_1` |
| 1818.55 | **Scripted:** lookout relay `cam_06` -> `cam_14` (`basis: lookout`, "Lookout: description match, trail cold 30 min. Fistfight at cam_05; last seen at cam_06.", no expected arrival, no direction), citing `cam_06`'s verdict and detection; the coordinator predicts `cam_14` | `rel_lookout_708051_1`, `dsp_r950c_11` |
| 1818.8 | **Scripted:** "match" at `cam_14`, citing the relay and the detection. The coordinator updates Route 2's incident: alert, path `cam_05` -> `cam_06` -> `cam_14`, "Operator review needed. Send officer to Hillsborough St sidewalk (cam_14); fistfight at Route 2: sidewalk by bollard (cam_05)" | `ver_lookout_708051_1`, `dsp_r950c_12` |

Final state: Route 3 `inc_r950c_1` alert (path `cam_07`-`cam_10`), Route 4 `inc_r950c_2` alert (path `cam_11`-`cam_13`), Route 2 `inc_r950c_3` alert (path `cam_05`, `cam_06`, `cam_14`).

"Watch last sighting" on `dsp_r950c_12` plays `cam_14`'s clip, test clip 8's cam2: the sighting is 1.75 s into it (`start_ts` 1817.05), and the suspect is in view from 1.25 to 2.5 s. The bus serves it at `GET /clips/cam_14`.

## What is real and what is not (say this on screen)
| Part | In this run |
|---|---|
| Camera views | Real: test clips 7, 1 and 3 (`cam_04`-`cam_13`) and test clip 8's cam2 (`cam_14`), all filmed by the team near the Red Hat Annex on Oct 17 |
| Spotter + checker answers for the three crimes | **Real model output, recorded** (`data/answers/trio_system_v3_checker.json`: NeMo Gym runs at temperature 0, not live calls) |
| Camera agents (relays, verdicts) for the three crimes | Real code (`agents/`), run on those answers |
| The `cam_14` pickup (detection, lookout relay, verdict) | **Scripted** by `bus/demo_trio_lookout.py` (`source: fake_scenario`). Its detection text is the hand label of clip 8 (`data/ground_truth/take1.json`); the lookout relay carries the description `cam_06`'s checker gave |
| `cam_14`'s map position | Placed on Hillsborough St for this story: 35.7854, -78.6603, a public sidewalk near NC State, 2.27 km from `cam_05` (about a 30-minute walk). Its footage was **not** filmed there: clip 8's cam2 was filmed about 4 min after clip 7 (16:43:28 vs 16:39:30 for clip 7's crime view) about 60 m from clip 7's cameras (56-67 m by the phones' GPS fixes; clip 8 cam2's fix is +/-26 m). Times and fixes: Wali's `camera_positions.csv` |
| The ~30-minute gap | **Set for this story** (`cam_14`'s `start_ts` = Route 2's crime detection 18.3 + 1800 - 1.25). The same actor, in the same black hoodie, is the suspect in clips 7 and 8 |
| Coordinator | Real code, **rules mode** (`--no-model`): 12 dispatches over three incidents |
| Bus | Real, strict validation |

**Known model errors, say them on screen:** clip 1 (Route 3) is a mimed stabbing and clip 7 (Route 2) a pickpocket, but the spotter called both an assault, so both incidents are `fistfight` / medium. At Route 2's crime camera the checker described the victim (blue long-sleeve, khaki cargo), so `cam_06`, which saw the runner in a black hoodie, answered "uncertain" and Route 2's incident stayed at "tracking" until the scripted match at `cam_14`. `cam_06` joins Route 2's path only because the scripted lookout relay starts there and cites its detection (the coordinator counts a relay's origin as a sighting).

## Event counts
39 events, all valid (`python contracts/validate.py runs/run_trio_lookout/events.jsonl`: 39/39).

| Type | Count | | Source | Count |
|---|---|---|---|---|
| detection | 11 | | agents | 24 |
| relay | 8 | | dispatcher | 12 |
| agent_verdict | 8 | | fake_scenario | 3 |
| dispatch | 12 | | | |

No camera_status events (the camera agents don't publish them) and no operator action; Confirm / Dismiss happen live during the replay.

## Pacing
The agents ran at real speed (58 s of wall time); the pickup was published 2 s after they finished, so `arrivals.jsonl` (when the bus accepted each event) shows no 30-minute wait. Every event's `ts` is the true run clock.

## Replay (the demo)
Start the bus with a NEW run id and this site's cameras, don't run a dispatcher, then replay:
```
CLARITY_RUN_ID=<new id> CLARITY_CAMERAS=data/sites/annex_trio_lookout/cameras.json python -m bus.server
python -m bus.replay runs/run_trio_lookout/events.jsonl --speed 1 --max-gap 5
```
About 35 s: the three chases at true times (pauses capped at 5 s), a 5-second pause before `cam_04`'s "no_match", the 29-minute cold trail as a 5-second pause, then the pickup at `cam_14`. Checked onto a fresh temporary bus: 39/39 valid, the replayed log byte-identical to this one, `GET /clips/cam_14` 200 `video/mp4` (Range 206). The dashboard fits the map to all cameras, so with `cam_14` 2.3 km away the Annex cameras sit close together.
