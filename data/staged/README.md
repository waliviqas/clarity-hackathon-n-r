# Staged footage: data and method

The Clarity team filmed this footage during the NVIDIA x Red Hat Small Models Hack. It is our main open-data contribution. The hackathon counts staged (synthetic) data as open data only if both the clips and the method are published, so this page describes how we filmed, labeled and processed every clip. It is written so anyone can check the data or reuse it.

- **Download:** TODO: dataset link (Hugging Face, pending)
- **License:** CC BY 4.0 (see [License and attribution](#license-and-attribution))

## What it is

There are three staged incidents. The team filmed them outside the Red Hat Annex (190 Davie St, Raleigh, NC) on Oct 17, 2026.

| Take | Label (`activity`) | What happens |
|---|---|---|
| 1 | `fistfight` | A scuffle with staged shoves. No real hits. |
| 2 | `purse_snatch` | A bag is snatched and the suspect walks off. |
| 3 | `purse_snatch` | A phone is grabbed from someone's hand, and the suspect escapes along a different route. |

Each incident has its own **route of 4 phone cameras**:

```
start camera ──► junction ──► exit A   (the suspect goes this way)
                     │
                     └──────► exit B   (filmed as an empty path: nobody comes)
```

The suspect takes one exit. We film the other exit as an empty path, so the camera agents get a real "no match" to reject instead of a made-up one. Across the 3 routes that makes 12 cameras, `cam_01` to `cam_12`.

The footage contains no stabbing. `stabbing` is still a label the models can output, but we found no openly licensed stabbing footage, and we don't stage scenes with knives or anything that looks like one.

## How it was filmed

- **Phones:** iPhones in landscape, propped about 2 m high and angled down, so the view looks like a CCTV camera. The filming checklist also asked for exposure/focus lock and Do Not Disturb. TODO: confirm the recording settings actually used (the plan was 1080p at 30 fps; was HDR on?).
- **One take per incident:** three phones record at the same time, at the start camera, the junction, and the exit the suspect takes. The teammates act out the scene and the escape.
- **The empty exit:** after each take, a phone films about 2 minutes of the other exit with nobody walking through.
- **Clock sync:** the cameras are too far apart for one clap to be seen by all of them. Instead, after recording starts, someone holds a large seconds clock (time.is) up to each camera for about 2 s. The clip log records the clip second where the clock is visible and what it reads. That puts every clip of a take on one wall clock. The iPhone's file creation time is the backup.
- **The unfilmed link:** nobody walks from the junction to the empty exit on camera, so a teammate timed that walk with a stopwatch.
- **Positions:** each camera's latitude and longitude was read from the iPhone Compass app at its spot. The direction the phone faces (`heading_deg`) is optional.
- **Labels:** after filming, the clock reading and the seconds when the suspect enters and leaves each view were read off every clip and typed into the clip log (one row per camera). TODO: state whether this was done by hand or with model help, and who checked it.

## Safety and consent

- **Only consenting teammates are on camera.** Everyone filmed agreed in writing (in the team chat) to publication under CC BY 4.0.
- **No weapons and no weapon-like props.** The fight is staged shoves only.
- **No bystanders.** We filmed outside, away from offices and other hackathon attendees. Any take where a bystander's face could be recognized was re-filmed, or the face is blurred before publishing. TODO: list any clips that needed blurring, and how they were blurred (or write "none").
- **No audio.** The conversion step strips the audio track, because it could carry bystanders' voices.
- **Clip files are never in git.** Raw video lives in `data/raw/` (gitignored). The clips are published only through the dataset link.

## Filmed separately, replayed simultaneously

This is a deliberate method choice, and we disclose it: **the three incidents did not happen at the same time.** Our small cast can't act out three incidents at once, so each take was filmed on its own.

For the demo, the three takes are lined up on one shared run clock so their crimes happen **5 s, 15 s and 25 s** into the run (takes 1, 2, 3). Only the start of each take is shifted. Inside a take, the clock sync keeps the real timing between cameras. Some junction or exit clips therefore start before run-clock 0, and the feeds skip those first frames.

The empty-exit clip was filmed after its take, so its own clock is ignored. It starts at the same moment as that take's junction clip.

This lets us test the system on three overlapping incidents. It does not show three real crimes happening at once.

## Processing pipeline

Run these from the repo root with Python 3.10+. `convert_clips.py` and `build_site.py` use only the standard library. `convert_clips.py` also needs `ffmpeg` on PATH (`sudo apt-get install -y ffmpeg` on the Linux GPU box). The other two steps need `pip install -r contracts/requirements.txt -r feeds/requirements.txt`. If a path contains spaces, quote it.

**Before step 1:**
- Copy the clips to `data/raw/staged/take1/`, `take2/` and `take3/`, named `take<N>_cam<NN>.mov`.
- Copy `data/staged/clip_log_template.csv` to `data/staged/clip_log.csv` and fill it in, one row per camera.
- Point the `clip_file` cells at the `.mp4` names that step 1 writes.

```
python data/convert_clips.py data/raw/staged
python data/build_site.py data/staged/clip_log.csv --check-clips data/raw/staged
python contracts/validate.py data/sites/annex/cameras.json
python -m feeds.replay --cameras data/sites/annex/cameras.json --check
```

1. **Convert** (`data/convert_clips.py`) writes a `.mp4` copy next to each clip and never changes the original. The settings are 720 px tall, a constant 10 fps, H.264 8-bit and no audio:
   `ffmpeg -i in -vf "scale=-2:720,format=yuv420p" -r 10 -fps_mode cfr -an -c:v libx264 -preset veryfast -crf 23 -movflags +faststart out.mp4`
   (ffmpeg older than 5.1 uses `-vsync cfr` instead of `-fps_mode cfr`; the script switches automatically.) iPhone clips are HEVC with a variable frame rate, which some OpenCV builds can't decode and which breaks the frame-index clock. A constant frame rate fixes both.
2. **Build** (`data/build_site.py`) turns the clip log into the three output files below. It stops and names the row and column of every blank or malformed cell, and it writes nothing until the whole log is clean. `--check-clips` also confirms that every `clip_file` exists in `data/raw/staged/take<N>/` with the exact upper/lower case (the GPU box runs Linux, where file names are case-sensitive). Add `--takes 1` to build only the takes logged so far.
3. **Validate** (`contracts/validate.py`) checks `cameras.json` against the team's contract schema.
4. **Check the clips** (`feeds.replay --check`) opens every clip and prints its resolution, fps, frame count, duration and codec. It exits with code 1 if any clip is missing or unreadable.

How `build_site.py` turns the log into numbers:
- **Travel time** between two filmed cameras is the time the suspect walks between them on the run clock: the moment they enter the next camera minus the moment they left the previous one (0 if the views overlap). The junction-to-empty-exit time is the stopwatch walk.
- **Direction** between cameras is computed from their lat/lon as one of 8 compass directions. Every link is written in both directions. A warning flags a junction whose two exits point in the same direction, because then the graph can't tell the exits apart.
- **Camera names stay neutral**, because models and prompts may see them: `Route <N>: <spot description>`, or `Route <N>: camera <k>`. A spot description that names a role or a crime is an error. Camera roles (start camera, junction, exit, empty exit) appear only in the ground truth.

## Output files

| File | Contents |
|---|---|
| `data/sites/annex/cameras.json` | The camera graph, following `contracts/schemas/cameras.schema.json`. For each camera it gives the neutral name, route (`take`), lat/lon, optional `heading_deg` and neighbors (each with `travel_time_s` and `direction`). It also gives the clip source as `uri` (`data/raw/staged/take<N>/<clip_file>`) and `start_ts`, the run-clock second where the clip starts. |
| `data/ground_truth/take<N>.json` | One file per incident: `incident_id`, `subject_id`, `activity`, the suspect's outfit (`appearance`), the take's run-clock offset, and the suspect's `path` as `[{camera_id, t_enter, t_exit}]` on the run clock. It also has `decoy_camera_id` (the empty exit) and `camera_roles`, which maps each of the 4 camera IDs to `crime`, `junction`, `exit` or `decoy`. |
| `data/manifests/annex.json` | Maps each `camera_id` to its take, clip file, `uri` and `start_ts`, for the feeds. |
| Clip log | The filled log, `data/staged/clip_log.csv`, stays local and out of git (gitignored) because its `phone_owner` column names the phone owners. The build never copies that column into the outputs. A sanitized copy with `phone_owner` blank is published so the build can be reproduced. TODO: path or link of the sanitized copy. The columns are listed in `data/staged/clip_log_template.csv`. |

**Reusing the clips:** the `uri` paths are relative to the repo root. Put the downloaded clips in `data/raw/staged/take<N>/`, or set `CLARITY_CLIP_ROOT` to a folder that contains `data/raw/staged/...`.

TODO: if the spotter model is fine-tuned on any of these clips, list here which clips are for training and which are for testing (they must stay separate).

## License and attribution

The clips, ground truth, manifest, camera map and sanitized clip log are licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**: https://creativecommons.org/licenses/by/4.0/

Attribution line:

> Clarity staged multi-camera incidents (Red Hat Annex, Raleigh, Oct 17, 2026), by the Clarity team, NVIDIA x Red Hat Small Models Hack. CC BY 4.0. TODO: dataset link

The processing scripts are code, not data. Their license is set in the repo's main README.

## Known limitations

- **One location, one day, daylight only.** All footage was filmed outside one building, in daylight, on Oct 17, 2026.
- **Three takes, one per incident.** There are no repeat takes of the same incident to average over.
- **Small cast.** Only teammates appear, so there are few distinct people, outfits and body types.
- **Staged acting.** The shoves and snatches are acted, so they may look gentler or more obvious than real incidents.
- **Filmed separately, replayed together.** See the section above.
- **The route grouping leaks.** The `Route <N>:` camera names, the `take` field in `cameras.json` and the `take<N>/` folder in each clip path all reveal which four cameras belong to one incident. The graph also has no links between routes. A system that reads these fields could use them as a shortcut.
- **One empty exit per route.** It was filmed after its take, and its travel time comes from a single stopwatch walk.
- **Phone positions.** Lat/lon come from the iPhone Compass app, so they carry phone GPS error.
- **No stabbing footage** (see [What it is](#what-it-is)).
