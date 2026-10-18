# Staged footage: data and method

The Clarity team filmed this footage during the NVIDIA x Red Hat Small Models Hack. It is our main open-data contribution. The hackathon counts staged (synthetic) data as open data only if both the clips and the method are published, so this page describes how we filmed, labeled and processed every clip. It is written so anyone can check the data or reuse it.

- **Download (published):** https://huggingface.co/datasets/WilwilMina/clarity-clip8 (Hugging Face: clip 8's three blurred camera views `cam1.mp4` to `cam3.mp4`, the clip log, the ground truth and a dataset card)
- **Download (published), clip 1:** https://huggingface.co/datasets/WilwilMina/clarity-clip1 (Hugging Face: the live demo's four camera views `cam1.mp4` to `cam4.mp4`, the clip log, the ground truth and a dataset card)
- **License:** CC BY 4.0 (see [License and attribution](#license-and-attribution))
- **Status (Sun Oct 18):** clip 8 is published. Test clip 1, the live demo, is published too (see [Clip 1: the live demo site](#clip-1-the-live-demo-site)). We haven't made copies of the other clips.

## What it is

One staged incident, seen from three camera views along the suspect's escape route. Teammates filmed it on a street in downtown Raleigh, NC, near the Red Hat Annex (190 Davie St), on the afternoon of Oct 17, 2026.

| Clip | Label (`activity`) | What happens |
|---|---|---|
| 8 | `purse_snatch` | At a bus shelter, the suspect walks up to a person, snatches something from their hand and runs off. |

The route has **3 cameras**, `cam_01` to `cam_03`:

```
cam_01 bus shelter (the snatch) ──► cam_02 sidewalk by tree grate ──► cam_03 covered walkway (exit)
```

There is no decoy: no camera films an empty path, so the footage never gives the camera agents a real "no match" view.

The published datasets hold test clips 8 and 1. Test clip 1, the live demo, has a site of its own (see [Clip 1: the live demo site](#clip-1-the-live-demo-site)).

Clip 8 (a phone snatch) contains no stabbing. Other clips from the session include mimed stabbings, acted with empty hands: we found no openly licensed stabbing footage, and we never stage scenes with knives or anything that looks like one.

## How it was filmed

- **One phone, three runs.** A single iPhone filmed the three camera views one after another. The teammates acted the scene once per view, and the phone moved to the next spot between runs. So each view shows a separate run of the same scene, not one run seen by three cameras at once. The source files are IMG_7380, IMG_7381 and IMG_7382, recorded at 16:41:45, 16:43:28 and 16:43:50. The gaps between them are setup time, not the suspect's running time.
- **Views:** high-angle views looking down at the sidewalk, like a CCTV camera. The copies we processed are 1080p H.264 at 30 fps, with audio (removed in processing, see below). The phone was handheld, not on a fixed mount, so the view moves a little during the clips (most visibly in `cam_03`).
- **No clock sync.** No clock is in view, and the runs were separate anyway. The time between views comes from **estimated running times** (`travel_s` in the clip log), based on the distance between the spots: 3 s from `cam_01` to `cam_02` (about 11 m) and 6 s from `cam_02` to `cam_03` (about 22 m). They are estimates, not measurements.
- **Positions:** each clip's metadata holds a GPS fix, collected in the team's camera-position sheet (`video-data/custom-clips/camera_positions.csv`, on Wali's branch). Its accuracy is ±14–28 m, which is more than the 11–22 m between the cameras, so the map positions are **placed by hand** in route order (see [Raw GPS vs placed positions](#raw-gps-vs-placed-positions)). The direction the phone faces (`heading_deg`) was not recorded.
- **Labels:** the seconds when the suspect enters and leaves each view were read from frame contact sheets in 0.25 s steps and typed into the clip log: `cam_01` 3.25–7.75 s (the snatch at 6.5 s), `cam_02` 1.25–2.5 s, `cam_03` 1.5–4.1 s (still in view when the clip ends). They were read by our coding assistant (Claude Code, a development tool that is not part of Clarity's runtime) and shown to the team; nobody has re-checked them frame by frame yet.

### Raw GPS vs placed positions

**Raw:** the GPS fix in each clip's metadata, given to 4 decimals (steps of about 10 m) with the phone's stated accuracy. Raw GPS puts the cameras in the order `cam_02`, `cam_01`, `cam_03` from south to north. On the map, the path then doubles back: south from `cam_01` to `cam_02`, then north past `cam_01` to `cam_03`. From `cam_02`, both neighbors point north, so the graph can't tell them apart by direction (`build_site.py` warned about this when the site was built from the raw fixes).

**Placed:** the cameras are placed by hand in route order, on a straight line heading north along the sidewalk:
- `cam_01` (the snatch) stays at its GPS fix, the most accurate of the three (±14 m).
- `cam_02` is 11 m north of `cam_01`, and `cam_03` is 22 m further north. These are the distances in the camera-position sheet, the same ones behind the 3 s and 6 s running times. They match the straight-line distance between consecutive raw fixes, so they are only as precise as the GPS.
- Each placed position is within its own fix's accuracy: `cam_02` is 22 m from its fix (±26 m), and `cam_03` is 22 m from its fix (±28 m).
- North is an assumption: the exit's fix (`cam_03`) is north of the snatch's (`cam_01`), but the direction of the sidewalk was not recorded.

| Camera | Spot | Raw GPS (lat, lon) | GPS accuracy | Placed (lat, lon) |
|---|---|---|---|---|
| `cam_01` | bus shelter | 35.7745, -78.6386 | ±14 m | 35.77450, -78.63860 (its GPS fix) |
| `cam_02` | sidewalk by tree grate | 35.7744, -78.6386 | ±26 m | 35.77460, -78.63860 (11 m north of `cam_01`) |
| `cam_03` | covered walkway | 35.7746, -78.6386 | ±28 m | 35.77480, -78.63860 (22 m north of `cam_02`) |

`cameras.json` uses the placed positions, so the route reads as one run north: from `cam_02`, `cam_01` is south and `cam_03` is north. The clip log keeps both: its `lat` and `lon` columns hold the placed positions, and three extra columns, `gps_lat`, `gps_lon` and `gps_accuracy_m`, hold the raw GPS (`build_site.py` ignores columns it doesn't read). Travel times and ground-truth times come from `travel_s`, not from positions, so the placement changed only the positions, the directions and the map center in `cameras.json`.

## Safety and consent

- **Only consenting teammates are on camera.** Everyone who acts is a member of the team, and all three team members agreed to publication under CC BY 4.0 (confirmed by the team on Oct 17). Clip 8 shows two of them: the suspect and the person robbed.
- **No weapons and no weapon-like props.**
- **Bystanders in our published copies.** In the copies we publish (clips 8 and 1), any bystander whose face could be recognized is blurred. Clip 8: blurred for publishing and for the demo, with `data/publish_clip8.py` (moving boxes, heavy 3-pass box blur, applied once to the unblurred converted clips; the script refuses clips it already blurred. Every blurred frame was checked on full-resolution contact sheets, and whole frames, two per second, for anyone left unblurred):
  - `cam_03`: two passers-by walking away (seen from behind), frames 0–38 (0–3.9 s); at frames 21–22 the suspect runs right past them, and one tight box touches the edge of the suspect's head.
  - `cam_01`: one stranger's lower legs at the top edge, frames 0–44 (0–4.5 s).
  - `cam_02`: nobody but the suspect; unchanged.
- **No audio and no file metadata.** The conversion step strips the audio track, because it could carry bystanders' voices. `data/publish_clip8.py` also writes the published clips without file metadata, because phone clips can carry the GPS position, recording time and phone model there. ffprobe confirms that each published clip has one video stream, no audio, and no location, date or device tags. The rounded GPS fixes are published on purpose, in the clip log (see [Raw GPS vs placed positions](#raw-gps-vs-placed-positions)).
- **Clip files are never in git.** Raw video lives in `data/raw/` (gitignored). The clips are published only through the dataset link.

## Three runs, replayed as one

This is a deliberate method choice, and we disclose it: **the three views come from three separate runs of the scene**, not one continuous escape.

For the demo, the clips are placed on one run clock as if three cameras saw one escape. The suspect enters `cam_01` at run-clock 5 s. `cam_02`'s clip is placed so the suspect enters it 3 s after leaving `cam_01`'s view, and `cam_03`'s so the suspect enters it 6 s after leaving `cam_02`'s view:

| Camera | Suspect in view (run clock) | Clip starts at (run clock) |
|---|---|---|
| `cam_01` | 5.0–9.5 s | 1.75 s |
| `cam_02` | 12.5–13.75 s | 11.25 s |
| `cam_03` | 19.75–22.35 s | 18.25 s |

This lets us test the camera-to-camera handoff on real footage. The times between views are built from the estimates, so they can't be used to measure how well a system predicts travel times.

## Processing pipeline

Run these from the repo root with Python 3.10+. `convert_clips.py` and `build_site.py` use only the standard library. `convert_clips.py` also needs `ffmpeg` on PATH (`sudo apt-get install -y ffmpeg` on the Linux GPU box). The other two steps need `pip install -r contracts/requirements.txt -r feeds/requirements.txt`. If a path contains spaces, quote it.

**Before step 1:** put the original clips in a folder of their own. The committed clip log, `data/staged/clip_log_take1.csv`, already points at the converted names (`clip8_cam1.mp4` to `clip8_cam3.mp4`). The published clips are already converted, so if you download them, put them in `data/raw/staged/take1/` under the names the clip log uses (`cam1.mp4` becomes `clip8_cam1.mp4`, and so on) and start at step 2.

```
python data/convert_clips.py "<folder with the original clips>" --out data/raw/staged/take1
python data/build_site.py data/staged/clip_log_take1.csv --check-clips data/raw/staged
python contracts/validate.py data/sites/annex/cameras.json
python -m feeds.replay --cameras data/sites/annex/cameras.json --check
```

1. **Convert** (`data/convert_clips.py`) writes a `.mp4` copy of each clip and never changes the original. Originals that are already `.mp4` need `--out`. The settings are 720 px tall, a constant 10 fps, H.264 8-bit and no audio:
   `ffmpeg -i in -vf "scale=-2:720,format=yuv420p" -r 10 -fps_mode cfr -an -c:v libx264 -preset veryfast -crf 23 -movflags +faststart out.mp4`
   (ffmpeg older than 5.1 uses `-vsync cfr` instead of `-fps_mode cfr`; the script switches automatically.) Phone clips often have a variable frame rate, which breaks the frame-index clock, and iPhone HEVC clips don't decode in every OpenCV build. A constant frame rate and H.264 fix both.
2. **Build** (`data/build_site.py`) turns the clip log into the three output files below. It stops and names the row and column of every blank or malformed cell, and it writes nothing until the whole log is clean. `--check-clips` also confirms that every `clip_file` exists in `data/raw/staged/take<N>/` with the exact upper/lower case (the GPU box runs Linux, where file names are case-sensitive).
3. **Validate** (`contracts/validate.py`) checks `cameras.json` against the team's contract schema.
4. **Check the clips** (`feeds.replay --check`) opens every clip and prints its resolution, fps, frame count, duration and codec. It exits with code 1 if any clip is missing or unreadable.

How `build_site.py` turns the log into numbers:
- **Travel time** between two cameras: with no clock in view (this footage), it is the logged `travel_s`, or else the straight-line distance between the cameras at a running speed (`--run-speed`, default 4 m/s). The suspect enters the next view `travel_s` after leaving the previous one. Footage that shows a clock is synced by the clock instead, and travel times are then measured.
- **Direction** between cameras is computed from their lat/lon as one of 8 compass directions. Every link is written in both directions. A warning flags any camera with two neighbors in the same direction, because then the graph can't tell them apart.
- **Camera names stay neutral**, because models and prompts may see them: `Route <N>: <spot description>`, or `Route <N>: camera <k>`. A spot description that names a role or a crime is an error. Camera roles (crime, path, exit) appear only in the ground truth.

## Output files

| File | Contents |
|---|---|
| `data/sites/annex/cameras.json` | The camera graph, following `contracts/schemas/cameras.schema.json`. For each camera it gives the neutral name, route (`take`), lat/lon (the placed positions), optional `heading_deg` and neighbors (each with `travel_time_s` and `direction`). It also gives the clip source as `uri` (`data/raw/staged/take<N>/<clip_file>`) and `start_ts`, the run-clock second where the clip starts. |
| `data/ground_truth/take<N>.json` | One file per incident: `incident_id`, `subject_id`, `activity`, the suspect's outfit (`appearance`), the take's run-clock offset, and the suspect's `path` as `[{camera_id, t_enter, t_exit}]` on the run clock. It also has `decoy_camera_id` (`null`: no decoy) and `camera_roles`, which maps each camera ID to its role (`crime`, `path` or `exit`). |
| `data/manifests/annex.json` | Maps each `camera_id` to its take, clip file, `uri` and `start_ts`, for the feeds. |
| `data/staged/clip_log_take1.csv` | The clip log the site is built from, with `phone_owner` blank. It rebuilds the three files above exactly (`python data/check_build_site.py` checks this). The team's working log, `data/staged/clip_log.csv`, stays local and out of git (gitignored) because its `phone_owner` column names the phone owners; the build never copies that column into the outputs. The columns are listed in `data/staged/clip_log_template.csv`; this log adds `gps_lat`, `gps_lon` and `gps_accuracy_m` for the raw GPS, and its `lat`/`lon` are the placed positions. |

**Reusing the clips:** the `uri` paths are relative to the repo root. Put the downloaded clips in `data/raw/staged/take1/`, renamed to `clip8_cam1.mp4` to `clip8_cam3.mp4`, or set `CLARITY_CLIP_ROOT` to a folder that contains `data/raw/staged/...`.

**Training vs test:** clip 8 is a test clip (`split=test` in the team's `labels.csv`), so it stays out of the fine-tuned spotter's training data (training and test clips must stay separate).

## License and attribution

The clips, ground truth, manifest, camera map and clip log are licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**: https://creativecommons.org/licenses/by/4.0/

Attribution line:

> Clarity staged incident, three camera views (Raleigh, Oct 17, 2026), by the Clarity team, NVIDIA x Red Hat Small Models Hack. CC BY 4.0. https://huggingface.co/datasets/WilwilMina/clarity-clip8

The processing scripts are code, not data. Their license is set in the repo's main README.

## Known limitations

- **One incident, one location, one afternoon.** One staged snatch, filmed on one street in daylight on Oct 17, 2026. There are no repeat takes to average over.
- **Three runs, not one escape.** Each view is a separate run of the scene, so the suspect's moves and the light differ slightly between views (see [Three runs, replayed as one](#three-runs-replayed-as-one)).
- **Estimated travel times.** The 3 s and 6 s between views are distance-based estimates. The ground-truth times after the snatch are built from them, so they are not independent measurements.
- **Small cast.** The suspect and the victim are teammates, so there are few distinct people, outfits and body types.
- **Staged acting.** The snatch is acted, so it may look gentler or more obvious than a real one.
- **No decoy.** No camera films an empty path, so this footage never asks an agent to reject a non-match.
- **Phone positions.** Raw GPS is accurate to ±14–28 m, more than the 11–22 m between cameras, and puts the cameras out of route order, so the cameras are placed by hand (see [Raw GPS vs placed positions](#raw-gps-vs-placed-positions)). The placed positions are within that error but approximate: the north heading is assumed, and the 11 m and 22 m spacings are themselves distances between GPS fixes. The 8-way directions between cameras follow from the placement.
- **The route grouping leaks.** The `Route 1:` camera names, the `take` field in `cameras.json` and the `take1/` folder in each clip path all reveal which cameras belong to the incident. A system that reads these fields could use them as a shortcut.
- **No stabbing footage** (see [What it is](#what-it-is)).

## Clip 1: the live demo site

Test clip 1 is another staged incident from the same session and the **live demo**. It has a site of its own (`data/sites/annex_clip1/`, cameras `cam_07` to `cam_10`), which the bus serves by default.

**Published** as [WilwilMina/clarity-clip1](https://huggingface.co/datasets/WilwilMina/clarity-clip1) (CC BY 4.0, uploaded Oct 18; built by `data/publish_clip1.py`: no blur needed, no audio, no file metadata). Both people on screen agreed to be filmed (the team asked them; confirmed Oct 18). Our coding assistant (Claude Code) looked at whole-frame review sheets of the four views (`python data/review_sheets.py data/raw/staged/take3`, two frames per second, written to the gitignored `data/raw/review/take3/`) and found no recognizable bystanders; a teammate checked the same sheets before upload.

- **What happens:** on a sidewalk, the suspect walks up to a person and mimes a stabbing with empty hands (no prop); the person falls and the suspect runs off. Label `stabbing`; suspect outfit: black hoodie, dark grey trousers.
- **Route:** `cam_07` sidewalk by street parking (the attack) ──► `cam_08` sidewalk by painted parklet ──► `cam_09` crosswalk corner ──► `cam_10` sidewalk by building column (exit). No decoy.
- **Filmed** like clip 8: one handheld iPhone, one run of the scene per view (IMG_7352 to IMG_7355, recorded 16:05 to 16:08), converted the same way (720p, constant 10 fps, H.264, no audio).
- **Labels** (clip seconds, from the team's clip log): `cam_07` 4.2–7.1 s (the attack at 5.6 s), `cam_08` 0.9–2.6 s, `cam_09` 0.0–5.31 s (standing at the curb when the clip starts, still in view at its end), `cam_10` 0.15–4.04 s (still in view at the end).
- **Travel times:** 7 s from `cam_07` to `cam_08` (about 24 m) and 6 s from `cam_08` to `cam_09` (about 21 m), from the camera-position sheet. The 3 s from `cam_09` to `cam_10`, over an estimated 10 m, is **our estimate**: the sheet gives 0 m because both views have the same rounded GPS fix.
- **Positions:** the raw fixes of `cam_07` to `cam_09` are already in route order and give the sheet's distances, so they stay. `cam_10`'s fix is the same 4-decimal point as `cam_09`'s, so it is placed about 10 m further on, continuing the `cam_08` → `cam_09` heading (southeast is an assumption). That is 10 m from its own fix: more than its ±5 m accuracy, within that accuracy plus the sheet's rounding to 4 decimals (about ±5 m). From `cam_08`, `cam_07` is south and `cam_09` southeast; from `cam_09`, `cam_08` is northwest and `cam_10` southeast. The clip log `data/staged/clip_log_take3.csv` keeps raw and placed positions the same way as take 1's:

| Camera | Spot | Raw GPS (lat, lon) | GPS accuracy | Placed (lat, lon) |
|---|---|---|---|---|
| `cam_07` | sidewalk by street parking | 35.7755, -78.6371 | ±6 m | 35.77550, -78.63710 (its GPS fix) |
| `cam_08` | sidewalk by painted parklet | 35.7757, -78.6370 | ±25 m | 35.77570, -78.63700 (its GPS fix, 24 m from `cam_07`) |
| `cam_09` | crosswalk corner | 35.7756, -78.6368 | ±20 m | 35.77560, -78.63680 (its GPS fix, 21 m from `cam_08`) |
| `cam_10` | sidewalk by building column | 35.7756, -78.6368 | ±5 m | 35.77555, -78.63671 (about 10 m southeast of `cam_09`, estimate) |

- **Run clock:** built with `--run-offset 0`, so the attack plays at run-clock 5 s like clip 8's snatch. The suspect is in view at 5.0–7.9 s (`cam_07`), 14.9–16.6 s (`cam_08`), 22.6–27.91 s (`cam_09`) and 30.91–34.8 s (`cam_10`). As with clip 8, these are four separate runs of the scene placed on one clock by the estimated travel times.
- **Background people:** distant passers-by and passing drivers appear in some views (for example on the far sidewalk in `cam_09`). None was recognizable in the frame-by-frame look or the teammate's check, so nothing is blurred.
- **Build:** `python data/build_site.py data/staged/clip_log_take3.csv --site annex_clip1 --site-name "Red Hat Annex (staged clip 1)" --run-offset 0 --check-clips data/raw/staged`, then `contracts/validate.py` and `feeds.replay --check` on `data/sites/annex_clip1/cameras.json`. It writes `data/sites/annex_clip1/cameras.json`, `data/ground_truth/take3.json` and `data/manifests/annex_clip1.json`; the clip-8 files are untouched.
- **Recorded model answers:** `data/answers/clip1_system_v3_checker.json` holds the answers of Wali's final system on these four views (the fine-tuned spotter v3 decides crime and type, Nemotron Nano 12B v2 VL describes the suspect; 3 NeMo Gym runs per view, converted by `data/gym_answers.py`). `python -m agents.run --answers data/answers/clip1_system_v3_checker.json --cameras data/sites/annex_clip1/cameras.json` replays the chase from them without a GPU. The spotter calls the attack an assault in all 3 runs, so the camera agents report a `fistfight` at `cam_07`, not a stabbing.
