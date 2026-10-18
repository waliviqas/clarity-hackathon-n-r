# Camera agents (`agents/`)

Wali's folder, built by Mina's side with his OK ("build them in agents/ as a thin layer over src/spotter.py;
don't modify my files"). It turns spotter answers into the contract events the dispatcher needs:
`detection`, `relay`, `agent_verdict`. Plain Python, no model of its own. Wali's code is imported unchanged;
nothing of it is copied here.

| File | What |
|---|---|
| `adapter.py` | spotter answer → `detection` (name mapping, appearance text) |
| `matching.py` | description comparison, travel-time check, combining weak sightings |
| `network.py` | one `CameraAgent` per camera, each with its own inbox of relays |
| `answers.py` | recorded answer files (stand-in) and Wali's `spot()` (live) |
| `run.py` | `python -m agents.run`: paces everything on the run clock and publishes to the bus |

## Run

From the repo root. The bus must serve the same `cameras.json` (`CLARITY_CAMERAS`).

```bash
# Stand-in: Wali's recorded base-model answers for clip 8 (3 runs per camera; the first good one is used)
mkdir -p /tmp/wali && git archive origin/wali-branch src results | tar -x -C /tmp/wali
python -m agents.run --answers /tmp/wali/results/before.json

# Live: Wali's spot(video_path) on each camera's clip, started when that clip has played
pip install -r agents/requirements.txt
SPOTTER_URL=http://localhost:8001/v1 SPOTTER_MODEL=Qwen/Qwen3-VL-2B-Instruct PYTHONPATH=/tmp/wali \
  python -m agents.run --live --save-answers "runs/$CLARITY_RUN_ID/spotter_answers.json"

# Offline check (no bus): every event to a file, then validate it
python -m agents.run --answers /tmp/wali/results/before.json --speed 0 --no-publish --out /tmp/a1.jsonl
python contracts/validate.py /tmp/a1.jsonl
```

Options: `--speed 2` (twice as fast, `0` = no waiting), `--cameras`, `--run N` (which recorded run),
`--frames 4` (frames per spotter call, Wali's default), `--spot-timeout 90`, `--relay-uncertain`,
`--tag` (letters, digits, `_`, `-`), `--run-id`.

**`--live` checks first:** it reads `GET {SPOTTER_URL}/models` and stops with one line and exit code 1 if
`SPOTTER_MODEL` isn't served there (or the server can't be reached), before any event is published. Each
clip's spotter call gets `--spot-timeout` seconds (default 90; Wali's client has a 60 s timeout + 1 retry,
and the agents retry a failed call once); past that, one warning line and that camera "can't tell" this
time. `--save-answers` is written even when the take crashes or is stopped with Ctrl+C.

**`--answers` files are recorded real model output only** (the spotter's own answers from an earlier run),
never answers built from labels or ground truth: in a demo they stand in for the model, so they must be
what the model said. Accepted formats:
- Wali's eval results (`results/before.json`, `results/after.json`):
  `{"model": ..., "cameras": [{"clip": "clip8", "cam": "cam1", "answers": [{...}, null, ...]}]}`,
  matched to cameras by clip file name (`source.uri` `.../clip8_cam1.mp4` = `clip8` + `cam1`); `null` is a
  failed run; `--run N` picks one, default the first that didn't fail.
- What `--live --save-answers` writes: `{"model": ..., "source": "agents.run --live", "answers": {"cam_01": {...}}}`.
- A bare `{"cam_01": {...}, ...}`.

Each answer is one spotter JSON object (Wali's schema: `what_happened`, `on_screen`, `crime`, `build`, `height`,
`shirt`, `pants`, `shoes`, `glasses`, `headwear`, `hair`, `bag`, `weapon`, `vehicle`). Cameras without one stay
silent. A file written by `--save-answers` replays the same run later with `--answers` (demo insurance).

## What the agents do

**Timing.** Each camera's clip plays on the run clock from its `source.start_ts`. Its spotter answer becomes a
`detection` when the clip has played (`ts` = start_ts + clip length). Agents never read ground truth.

**Adapter** (spotter → `detection`):
- `crime` → `activity`: stabbing → stabbing, assault → fistfight, stealing → purse_snatch, anything else → none.
  Only on the camera where `on_screen` is `crime`; a camera that sees someone run past did not see the crime
  (the dashboard rings every camera whose detection has a crime activity).
- `appearance`: the suspect fields joined into one line (only what was seen).
- `direction: null`, `bbox: null`, no `activity_confidence`: the spotter gives none.
- `confidence`: contract v0.1 requires a number, so it is **0.5 with `confidence_known: false`** (never 0).
  0.5 sits in the dispatcher's "ambiguous" band, so it behaves like unknown (never dropped, never auto-alerted).
- Extra fields: `what_happened`, `on_screen` (the dispatcher's model reads them), `spotter_crime`, `spotter`
  (the whole answer), `window_ts`, `spotter_model`, `spotter_mode` (`recorded` / `live`).

**Relays.** A crime detection that no relay explains opens a subject and relays to every neighbor in
`cameras.json`. After a **match** the matching camera relays onward (the contract's rule); by default an
uncertain look relays nothing. A subject is never relayed to a camera it was opened at or already relayed to
(so never back where it came from, and a loop of cameras can't relay forever). Each relay carries the
description, the link's `travel_time_s` as `expected_arrival_s`, its `direction`, the `activity`, and `basis`.

**Verdicts.** A camera with a relay in its inbox compares its next spotter answer with the description, field
by field. Fields either side couldn't see are skipped, so unknown never counts against a match.
- Looks + behaviour give a sighting probability: prior 0.3, running or a crime raises it, "nothing suspicious"
  lowers it, every agreeing feature raises it (shirt counts most, vehicle least), every differing one lowers it.
- **≥ 0.6 → match** (relay onward); **0.2–0.6 → uncertain**; below → no_match. A match also needs at least
  one feature that agrees: someone running with no comparable description is uncertain at most.
- **Impossible travel time → no_match**, however good the match: the gap between the two clips must fit
  0.5× to 3× the link's travel time + 30 s (up to 120 s for a link without one). A clip that ended before
  anyone could arrive is skipped and the relay keeps waiting.
- **Weak sightings add up**, opt-in with `--relay-uncertain`: an uncertain look at someone running is relayed
  onward too (`basis: possible`), and the next camera combines its look with them (noisy-OR: two at 50% →
  75%, a match; five at 20% → 67%), but only if its own look has a feature that agrees.
- A relay nobody answers by its deadline gets `no_match` ("Not seen"). If the spotter call failed for that
  clip (one retry first, then the time limit), or its answer wasn't a JSON object, the verdict is
  `uncertain` ("can't tell") instead.
- `confidence` is how sure the agent is of its decision (0.05–0.95).

**What each event cites** (`evidence_event_ids`, the receipts trail):

| Event | Cites |
|---|---|
| relay, `basis: crime` (opens the subject) | the crime detection |
| relay, `basis: match` | the match verdict + that camera's detection |
| relay, `basis: possible` (`--relay-uncertain` only) | the uncertain verdict only, so the dashboard doesn't show that camera as a sighting |
| verdict from a spotter answer (match / no_match / uncertain) | the relay + this camera's detection |
| verdict "can't tell" (spotter failed) | the relay only |
| verdict "Not seen" (deadline passed) | the relay only |

## Tests

```bash
python -m unittest discover -s agents/tests -t .
```
