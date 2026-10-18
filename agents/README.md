# Camera agents (`agents/`)

Owner: Mina (a thin layer over Wali's `src/spotter.py` and `src/checker.py`). It turns spotter answers (with
the checker's suspect description on flagged cameras) into the contract events the dispatcher needs:
`detection`, `relay`, `agent_verdict`. Plain Python, no model of its own. Wali's code is imported unchanged
from the repo's `src/`; nothing of it is copied here.

| File | What |
|---|---|
| `adapter.py` | spotter answer → `detection` (name mapping, appearance text) |
| `combine.py` | the spotter's answer + the checker's description, merged as in Wali's `nemo_gym/combine_gym.py` |
| `matching.py` | description comparison, travel-time check, combining weak sightings |
| `network.py` | one `CameraAgent` per camera, each with its own inbox of relays |
| `answers.py` | recorded answer files (stand-in) and Wali's `spot()` / `describe()` (live) |
| `run.py` | `python -m agents.run`: paces everything on the run clock and publishes to the bus |

## Run

From the repo root (Wali's `src/` ships with the repo). The bus must serve the same `cameras.json`
(`CLARITY_CAMERAS`; default `data/sites/annex_clip1/cameras.json`, the live demo site, test clip 1).

```bash
# No GPU: Wali's recorded system answers for clip 1 (spotter-ft v3 + checker, 8 frames; first good run used)
python -m agents.run --answers data/answers/clip1_system_v3_checker.json

# Live: spotter-ft on :8005 on each camera's clip, started when that clip has played, then the checker
# (Nemotron Nano 12B v2 VL) on :8002 on each camera the spotter flags
pip install -r agents/requirements.txt
SPOTTER_URL=http://localhost:8005/v1 SPOTTER_MODEL=spotter-ft \
CHECKER_BASE_URL=http://localhost:8002/v1 CHECKER_MODEL=checker \
  python -m agents.run --live --save-answers "runs/$CLARITY_RUN_ID/answers.json"

# Spotter alone (no checker calls, the behaviour before the checker; it used 4 frames then)
SPOTTER_URL=http://localhost:8005/v1 SPOTTER_MODEL=spotter-ft python -m agents.run --live --no-checker

# Offline check (no bus): every event to a file, then validate it
python -m agents.run --answers data/answers/clip1_system_v3_checker.json --speed 0 --no-publish --out /tmp/a1.jsonl
python contracts/validate.py /tmp/a1.jsonl
```

Options: `--speed 2` (twice as fast, `0` = no waiting), `--cameras`, `--run N` (which recorded run),
`--frames 8` (frames per spotter and checker call; Wali's measured system used 8 for both), `--spot-timeout 90`,
`--check-timeout 90`, `--no-checker`, `--relay-uncertain`, `--tag` (letters, digits, `_`, `-`), `--run-id`.

**`--live` checks first:** it reads `GET {SPOTTER_URL}/models` and `GET {CHECKER_BASE_URL}/models` (the
checker's variable is `CHECKER_BASE_URL`, not `CHECKER_URL`) and stops with one line and exit code 1 if
`SPOTTER_MODEL` or `CHECKER_MODEL` isn't served there (or a server can't be reached, or `src/checker.py` can't
be imported), before any event is published. `--no-checker` skips everything about the checker. Each clip's
spotter call gets `--spot-timeout` seconds (default 90; Wali's client has a 60 s timeout + 1 retry, and the
agents retry a failed call once); past that, one warning line and that camera "can't tell" this time. A flagged
camera's checker call gets `--check-timeout` seconds after its spotter answer (default 90; a cold 12B takes up to
a minute); past that, or on any checker error, one warning line and that camera keeps the spotter's description.
`--save-answers` is written even when the take crashes or is stopped with Ctrl+C.

**`--answers` files are recorded real model output only** (the models' own answers from an earlier run),
never answers built from labels or ground truth: in a demo they stand in for the models, so they must be
what the models said. Accepted formats:
- Wali's eval-results format (`results/before.json`; `data/gym_answers.py` writes it too, e.g.
  `data/answers/clip1_system_v3_checker.json`):
  `{"model": ..., "cameras": [{"clip": "clip1", "cam": "cam1", "answers": [{...}, null, ...]}]}`,
  matched to cameras by clip file name (`source.uri` `.../clip1_cam1.mp4` = `clip1` + `cam1`); `null` is a
  failed run; `--run N` picks one, default the first that didn't fail.
- What `--live --save-answers` writes: `{"model": ..., "checker_model": ..., "source": "agents.run --live",
  "answers": {"cam_01": {...}}}` (`checker_model` only when the checker ran).
- A bare `{"cam_01": {...}, ...}`.

Each answer is one spotter JSON object (Wali's schema: `what_happened`, `on_screen`, `crime`, `build`, `height`,
`shirt`, `pants`, `shoes`, `glasses`, `headwear`, `hair`, `bag`, `weapon`, `vehicle`). Cameras without one stay
silent. A file written by `--save-answers` replays the same run later with `--answers` (demo insurance): the
answers are saved already merged, so the replay gives the same events (only `spotter_mode` says `recorded`).
On a camera the checker was asked about, the answer also carries marks (`combine.py`):
- `description_by`: `checker` (its 11 suspect fields replaced the spotter's) or `spotter` (the checker failed);
- `checker_model`: the checker's model name, on answers it described;
- `checker_error`: the exception's name, when it failed (e.g. `TimeoutError`);
- `spotter_description`: the spotter's own 11 fields (live runs only), so the receipts keep what each model said.

`data/gym_answers.py` writes Wali's recorded NeMo Gym system runs in the eval-results format with the same
`description_by` + `checker_model` marks, so those files replay exactly like a `--save-answers` file.

## What the agents do

**Timing.** Each camera's clip plays on the run clock from its `source.start_ts`. Its spotter answer becomes a
`detection` when the clip has played (`ts` = start_ts + clip length). Agents never read ground truth.

**Checker** (`--live`, unless `--no-checker`). On each camera the spotter flags (`on_screen` `crime` or
`fleeing`), Wali's `describe(clip, 8)` (Nemotron Nano 12B v2 VL) runs right after the spotter answer, in that
camera's thread, so flagged cameras are described in parallel. The merge is the one Wali scored in NeMo Gym
(`nemo_gym/combine_gym.py`; `results/history.csv`: `system_v3_plus_checker_v2_8f`): the spotter keeps
`what_happened`, `on_screen` and `crime` (so `activity` is still the spotter's call), and the checker's 11
suspect fields replace the spotter's (a field it left out counts as unknown). Cameras the spotter didn't flag
keep the spotter's answer. If the checker raises, times out (`--check-timeout`), or replies with something that
isn't a JSON object, that camera keeps the spotter's own fields: one warning line, no crash. (combine_gym scores
that case as wrong; a live run keeps the best description it has.) Note: the two models word things differently,
so a camera that fell back can disagree with descriptions the checker gave elsewhere on the route.

**Adapter** (spotter → `detection`):
- `crime` → `activity`: stabbing → stabbing, assault → fistfight, stealing → purse_snatch, anything else → none.
  Only on the camera where `on_screen` is `crime`; a camera that sees someone run past did not see the crime
  (the dashboard rings every camera whose detection has a crime activity).
- `appearance`: the suspect fields joined into one line (only what was seen); on a camera the checker
  described, they are the checker's.
- `direction: null`, `bbox: null`, no `activity_confidence`: the spotter gives none.
- `confidence`: contract v0.1 requires a number, so it is **0.5 with `confidence_known: false`** (never 0).
  The dispatcher reads `confidence_known: false` as an unknown confidence, so it never gets an incident dropped.
  Since Michael's 56712cc a **stabbing** with unknown confidence alerts at once (rules, no model call) unless the
  evidence argues against it (mixed activities, or an `uncertain` verdict); a **fistfight** or **purse snatch**
  still goes to the dispatcher's model, and becomes an alert once a camera agent confirms a `match` downstream.
- Extra fields: `what_happened`, `on_screen` (the dispatcher's model reads them), `spotter_crime`, `spotter`
  (what the spotter said), `window_ts`, `spotter_model`, `spotter_mode` (`recorded` / `live`). On a camera the
  checker was asked about, also `description_by` (`checker` / `spotter`), and `checker` (its 11 fields) +
  `checker_model`, or `checker_error`. Answers recorded by `data/gym_answers.py` don't hold the spotter's own
  description, so there `spotter` has only `what_happened`, `on_screen` and `crime`.

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

The tests use stand-ins for Wali's `spot()` and `describe()` and never import his real `src/`: the `--live`
subprocess tests run from a folder of stand-ins that comes first on `sys.path`. They pass with or without his
`src/` at the repo root (as in a merged checkout), and without `openai` installed.
