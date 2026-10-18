---
license: cc-by-4.0
pretty_name: "Clarity clip 8: a staged phone snatch seen by three cameras"
language:
- en
task_categories:
- video-classification
tags:
- video
- multi-camera
- staged
- synthetic
- surveillance
- crime-detection
size_categories:
- n<1K
---

<!--
Clarity team: publishing checklist (HTML comment, so it doesn't show on Hugging Face)

1. Build the package from the repo root (blurs, strips metadata, checks; also copies this card in as README.md):
     python data/publish_clip8.py --sheets
   It reads the UNBLURRED converted clips in data/raw/staged_unblurred/take1/ (--src picks another folder) and
   refuses data/raw/staged/take1/ (the demo plays blurred copies from there) and any clip it already processed, so
   no clip is blurred twice. Every clip must print "ok". Then a teammate checks the sheets in data/raw/publish/review/:
     cam1/cam2/cam3_full_frames.png  whole frames, 2 per second: anyone who isn't an actor must be a blur
     cam1/cam3_blurred_frames.png    every blurred frame, cropped around the boxes: no face, hair or clothing detail
   After the check, replace the "TODO: a teammate confirms this before upload." sentence in "Consent and privacy"
   (for example: "A teammate checked the same sheets before upload.").
2. After any later edit to this card, copy ONLY the card into the package:
     cp data/staged/DATASET_CARD.md data/raw/publish/clarity-clip8/README.md
   (Running step 1 again is also safe: it always starts from the unblurred clips.)
3. Upload the six files in data/raw/publish/clarity-clip8/ (README.md, cam1.mp4, cam2.mp4, cam3.mp4,
   clip_log_take1.csv, take1.json). Either:
   a. Web UI, no install: signed in as WilwilMina, open huggingface.co/new-dataset -> Owner WilwilMina, name
      clarity-clip8, license cc-by-4.0, Public -> Create dataset -> Files and versions -> Add file -> Upload files
      -> drag in the six files (the files, not the folder) -> Commit changes to main.
   b. CLI (needs `pip install huggingface_hub`, which isn't installed here, plus `huggingface-cli login`
      with a write token; never commit the token):
        huggingface-cli upload WilwilMina/clarity-clip8 data/raw/publish/clarity-clip8 --repo-type dataset
      (newer huggingface_hub versions name the command `hf upload`; same arguments)
4. Put the dataset link into data/staged/README.md (the "Download" line and the attribution line).
5. The GitHub links below point at main, so they only work after the branch is merged to main.
-->

# Clarity clip 8: a staged phone snatch seen by three cameras

Three short videos of one staged street crime, a phone snatched from someone's hand at a bus shelter, seen from three camera spots along the suspect's escape route. The Clarity team filmed it in downtown Raleigh, NC, on Oct 17, 2026, during the NVIDIA x Red Hat Small Models Hack, to test camera-to-camera suspect handoff on real footage.

The three views are **three separate runs of the same scene**, filmed one after another on one phone. They are not one escape filmed by three cameras at once. Clarity replays them on one clock as if they were (see [Ground truth](#ground-truth-and-timing)).

- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Method (how it was filmed, labeled and processed):** [`data/staged/README.md`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/main/data/staged/README.md) in the Clarity repo
- **Code:** [github.com/waliviqas/clarity-hackathon-n-r](https://github.com/waliviqas/clarity-hackathon-n-r)

## Files

| File | Camera | Spot | Length | Suspect in view (clip seconds) |
|---|---|---|---|---|
| `cam1.mp4` | `cam_01` | bus shelter: the snatch | 8.5 s, 85 frames | 3.25 to 7.75 s; the snatch at 6.5 s |
| `cam2.mp4` | `cam_02` | sidewalk by a tree grate | 3.3 s, 33 frames | 1.25 to 2.5 s (runs past) |
| `cam3.mp4` | `cam_03` | covered walkway: the exit | 4.3 s, 43 frames | 1.5 s to the end (still in view when the clip ends) |
| `take1.json` | | | | Ground truth: crime type, suspect outfit, and the suspect's path across the three cameras on one run clock |
| `clip_log_take1.csv` | | | | The per-view log the ground truth was built from: spot, position (`lat`, `lon`: placed by hand; `gps_lat`, `gps_lon`, `gps_accuracy_m`: the raw GPS, see [Camera positions](#camera-positions)), clip file, enter/exit seconds, estimated travel time, notes |

All three videos are 1280x720, a constant 10 fps, H.264 (8-bit 4:2:0), with **no audio** and no file metadata about where, when or on which device they were filmed. They were converted from the phone's 1080p, 30 fps originals (`IMG_7380`, `IMG_7381`, `IMG_7382`).

**File names:** the clip log and the Clarity code call the files `clip8_cam1.mp4` to `clip8_cam3.mp4`. To run them through the Clarity pipeline, copy them into `data/raw/staged/take1/` under those names (`cam1.mp4` becomes `clip8_cam1.mp4`, and so on), then follow the method page.

**Labels:** the crime is labeled `purse_snatch`, one of Clarity's four activity labels (`stabbing`, `fistfight`, `purse_snatch`, `none`). The suspect wears a black hoodie and dark grey trousers.

## Ground truth and timing

`take1.json` places the three views on one run clock, as if three cameras saw one escape: the suspect is in `cam_01` from 5.0 to 9.5 s, in `cam_02` from 12.5 to 13.75 s, and in `cam_03` from 19.75 to 22.35 s. The gaps (3 s from `cam_01` to `cam_02`, 6 s from `cam_02` to `cam_03`) are **estimated running times** over the distances between the spots (about 11 m and 22 m). They were not measured, because the views come from separate runs and no clock is in view. `camera_roles` marks each camera as `crime`, `path` or `exit`.

Enter and exit times were read from frame contact sheets in 0.25 s steps by our coding assistant (Claude Code, a development tool that is not part of Clarity); nobody has re-checked them frame by frame yet.

## Camera positions

| Camera | Spot | Raw GPS (lat, lon) | GPS accuracy | Placed (lat, lon) |
|---|---|---|---|---|
| `cam_01` | bus shelter | 35.7745, -78.6386 | ±14 m | 35.77450, -78.63860 (its GPS fix) |
| `cam_02` | sidewalk by a tree grate | 35.7744, -78.6386 | ±26 m | 35.77460, -78.63860 (11 m north of `cam_01`) |
| `cam_03` | covered walkway | 35.7746, -78.6386 | ±28 m | 35.77480, -78.63860 (22 m north of `cam_02`) |

The raw GPS comes from each clip's metadata. Its error (±14 to 28 m) is larger than the distance between the cameras (11 to 22 m), and it puts them out of route order (`cam_02` south of `cam_01`), so the path would double back. The cameras are therefore placed by hand in route order, on a straight line heading north: `cam_01` (the snatch) stays at its fix, the most accurate of the three; `cam_02` is 11 m north of it, and `cam_03` 22 m further north. Those spacings are the distances behind the running-time estimates, and they match the distances between consecutive raw fixes. Each placed position is within its own fix's error. North is an assumption: the exit's fix is north of the snatch's, but the direction of the sidewalk was not recorded, and neither was the direction each phone faced. In `clip_log_take1.csv`, `lat` and `lon` are the placed positions, and `gps_lat`, `gps_lon` and `gps_accuracy_m` are the raw GPS.

## Consent and privacy

- **Actors:** only members of the Clarity team act in the clips, and each agreed to publishing them under CC BY 4.0. The snatch is acted: nobody was robbed, and there are no weapons or weapon-like props.
- **Passers-by are blurred.** Every person who isn't an actor is covered by a heavy blur for every frame they appear in:
  - `cam3.mp4`: two people walking away from the camera (seen from behind), frames 0 to 38 (0 to 3.9 s). The blur boxes follow them as they walk and the phone pans. In frames 21 and 22 the suspect runs past right in front of them, so the boxes there are tight, and one touches the edge of the suspect's head.
  - `cam1.mp4`: the lower legs of one person on the far sidewalk, at the very top edge of the frame, frames 0 to 44 (0 to 4.5 s).
  - `cam2.mp4`: no one but the suspect, so this clip is unchanged.
  
  Our coding assistant (Claude Code) checked every blurred frame on contact sheets at full resolution: no face, hair or clothing detail is left, only soft color patches. It also checked whole frames, two per second, for anyone left unblurred. TODO: a teammate confirms this before upload.
- **Cars:** passing and parked cars appear in the background. No licence plate is readable, and no driver can be recognized.
- **No audio:** the conversion removed the sound track, which could carry bystanders' voices.

## How it was made

The method page, [`data/staged/README.md`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/main/data/staged/README.md), covers how we filmed, labeled, converted and built the ground truth.

In short:
1. One iPhone filmed the three spots one after another. The teammates acted the scene once per spot.
2. `data/convert_clips.py` converted each clip to 720p, constant 10 fps, H.264 with no audio.
3. Enter and exit times were read from contact sheets (by Claude Code, see above) and typed into the clip log. `data/build_site.py` turned the log into `take1.json` and the camera map.
4. [`data/publish_clip8.py`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/main/data/publish_clip8.py) applied the passer-by blur and built this package. It lists every blur box as frames plus a pixel rectangle; each box is cut out, blurred with a 3-pass box blur (radius up to 30 px) and put back for those frames only. `cam1` and `cam3` were re-encoded (H.264, CRF 18). `cam2` has nothing to blur, so its video stream was copied without re-encoding (the same frames as the converted clip). All three files were written without file metadata, because phone clips can carry the GPS position, recording time and phone model there; ffprobe confirmed one video stream per file, no audio, and no location, date or device tags. The script refuses to blur a clip twice.

## Limitations

- **Staged.** The snatch is acted, so it may look gentler or more obvious than a real one.
- **Three runs, not one escape.** Each view is a separate run, so the suspect's moves and the light differ a little between views, and the times between views are estimates, not measurements.
- **Few people.** Two teammates act: the suspect and the person robbed. The same actor, in the same outfit, also plays the suspect in the team's other takes, which are not part of this first release. There is little variety in people, outfits and body types.
- **Small.** One incident, three clips, about 16 s of video, one street, one afternoon, daylight only.
- **Not a fixed camera.** The phone was not on a fixed mount: the view moves during the clips, most visibly in `cam3`.
- **GPS error.** Raw positions are accurate to only ±14 to 28 m, which is coarser than the spacing of the cameras, so the cameras are placed by hand (see [Camera positions](#camera-positions)). The placed positions are within the GPS error but approximate, and the north heading is assumed.
- **No decoy view.** No clip shows an empty path, so the footage never asks a system to reject a non-match.
- **Blur edits.** In `cam1` and `cam3` the blurred regions are edited pixels, and the re-encoding changes the rest of the image slightly. Results on these files may differ a little from runs on the unblurred originals.

## Intended use

- Testing systems that detect a crime in video and pass a suspect's description from camera to camera, like Clarity.
- A small **test** set. Clip 8 is a test clip in Clarity's evaluation; if you compare with our numbers, don't train on it.

**Out of scope:** identifying or tracking real people, face recognition, and using the clips as evidence of a real crime.

## How to cite

> Clarity staged incident, three camera views (Raleigh, Oct 17, 2026), by the Clarity team, NVIDIA x Red Hat Small Models Hack. CC BY 4.0. https://huggingface.co/datasets/WilwilMina/clarity-clip8

```bibtex
@misc{clarity_clip8_2026,
  title        = {Clarity clip 8: a staged phone snatch seen by three cameras},
  author       = {{The Clarity team}},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/WilwilMina/clarity-clip8}},
  note         = {NVIDIA x Red Hat Small Models Hack, Raleigh, NC. CC BY 4.0}
}
```
