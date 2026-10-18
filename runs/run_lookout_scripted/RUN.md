# Run run_lookout_scripted: a cold trail, picked up 38 minutes later, far away

**Scripted perception, real footage, an illustrative far camera position, coordinator in rules mode.** No model ran in this run; its timings are the script's pacing, not model latency. Every scripted event has `source: fake_scenario`, so the dashboard labels the run as scripted.

- **When:** Sun Oct 18, 2026, 07:18-07:19 ET, on Mina's laptop (temporary bus on a temporary port and runs folder).
- **Cameras:** `data/sites/annex_lookout/cameras.json`: test clip 1's `cam_07` to `cam_10` (unchanged from `data/sites/annex_clip1/`) plus `cam_14`, which is no neighbor of them.
- **Producers:**
  - `python -m bus.fake_scenario --ground-truth data/ground_truth/annex_lookout/take3.json --cameras data/sites/annex_lookout/cameras.json --lookout cam_14 --speed 1 --max-gap 5`
  - Michael's real dispatcher, `python -m dispatcher.run --no-model` (rules mode), from branch Integration at ded6415.

## What happens (run clock, seconds)
| ts | Event |
|---|---|
| 7.9 | Crime detection at `cam_07` (stabbing, mimed in test clip 1); relay to `cam_08` at 8.4 |
| 15.4 / 23.1 / 31.41 | "match" at `cam_08`, `cam_09`, `cam_10`; the coordinator's dispatches follow each one |
| 31.41-2306.05 | The trail goes cold: no camera next to `cam_10` sees the suspect (37.9 min after they left `cam_10`'s view at 34.8) |
| 2306.05 | `cam_14` sees someone run past (detection, `on_screen: fleeing`, black hoodie, dark grey trousers) |
| 2306.3 | Lookout relay `cam_10` -> `cam_14` (`basis: lookout`, "Lookout: description match, trail cold 38 min", no expected arrival, no direction) |
| 2306.55 | "match" at `cam_14`, citing the lookout relay and the detection |
| 2306.55 | The coordinator updates the same incident: path `cam_07` -> `cam_08` -> `cam_09` -> `cam_10` -> `cam_14`, "Send officer to Hillsborough St sidewalk (illustrative) (cam_14)" |

"Watch last sighting" on that last dispatch plays `cam_14`'s clip, test clip 8's cam2: the sighting is 1.75 s into it (`start_ts` 2304.8), and the suspect is in view from 1.25 to 2.5 s.

## What is real and what is not (say this on screen)
| Part | In this run |
|---|---|
| Camera views | Real: test clip 1's four views (`cam_07`-`cam_10`) and test clip 8's cam2 (`cam_14`). Both clips are published: [WilwilMina/clarity-clip1](https://huggingface.co/datasets/WilwilMina/clarity-clip1), [WilwilMina/clarity-clip8](https://huggingface.co/datasets/WilwilMina/clarity-clip8) |
| `cam_14`'s map position | **Illustrative** (Mina's decision): a public Hillsborough St sidewalk near NC State, 35.7854, -78.6603, 2.37 km from `cam_07` (2.39 km from `cam_10`), about a 30-minute walk. Its footage was **not** filmed there: clip 8's cam2 was filmed 38 min after clip 1 (16:43:28 vs 16:05:04), about 200 m from clip 1's cameras (182-213 m by the phones' GPS) |
| The 38-minute gap | Real: the filming gap between clip 1's cam1 and clip 8's cam2 (2304 s), kept on the run clock (`cam_14`'s `start_ts`) |
| Spotter and camera agents | **Scripted** from the ground truth (`data/ground_truth/annex_lookout/take3.json`); the same actor and outfit appear in both clips |
| Coordinator | Real code, **rules mode** (`--no-model`): 7 dispatches, all one incident |
| Bus | Real |

## Event counts
25 events, all valid (`python contracts/validate.py runs/run_lookout_scripted/events.jsonl`: 25/25).

| Type | Count | | Source | Count |
|---|---|---|---|---|
| camera_status | 5 | | fake_scenario | 18 |
| detection | 5 | | dispatcher | 7 |
| relay | 4 | | | |
| agent_verdict | 4 | | | |
| dispatch | 7 | | | |

No operator action was recorded; Confirm / Dismiss happen live during the replay.

## Pacing
The recording was published with `--max-gap 5`: every pause longer than 5 s (the 38-minute cold trail, and three walks of 6-7.9 s) took 5 s of wall-clock time, so `arrivals.jsonl` (when the bus accepted each event) shows compressed gaps. Every event's `ts` is the true run clock.

## Replay (the demo)
Start the bus with a NEW run id and this site's cameras, don't run a dispatcher, then replay:
```
CLARITY_RUN_ID=<new id> CLARITY_CAMERAS=data/sites/annex_lookout/cameras.json python -m bus.server
python -m bus.replay runs/run_lookout_scripted/events.jsonl --speed 1 --max-gap 5
```
About 32 s: the chase at true times (pauses capped at 5 s), the cold trail shown as a 5-second pause, then the re-sighting. With `--max-gap 8` the chase keeps its exact pace and the cold trail takes 8 s. The dashboard fits the map to all cameras, so with `cam_14` 2.4 km away the four Annex cameras sit close together.
