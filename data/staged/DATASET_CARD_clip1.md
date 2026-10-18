---
license: cc-by-4.0
pretty_name: "Clarity clip 1: a mimed stabbing seen by four cameras"
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

1. Build the package from the repo root (copies the clips without audio or metadata and checks them; also copies
   this card in as README.md):
     python data/publish_clip1.py
   It reads the converted clips the demo plays, data/raw/staged/take3/clip1_cam1.mp4 to clip1_cam4.mp4 (--src picks
   another folder). Nothing is blurred or re-encoded, so running it again is always safe. Every clip must print "ok"
   and "same frames as the source".
2. Bystander check: the whole-frame sheets in data/raw/review/take3/ (python data/review_sheets.py
   data/raw/staged/take3, two frames per second) show the same frames as the published clips. Our coding assistant
   checked them (see "Consent and privacy"). If a teammate also looks at them before upload, add "A teammate checked
   the same sheets before upload." at the end of the "No blur needed" bullet.
3. After any later edit to this card, copy ONLY the card into the package:
     cp data/staged/DATASET_CARD_clip1.md data/raw/publish/clarity-clip1/README.md
   (Running step 1 again does the same.)
4. Upload the seven files in data/raw/publish/clarity-clip1/ (README.md, cam1.mp4, cam2.mp4, cam3.mp4, cam4.mp4,
   clip_log_take3.csv, take3.json). Either:
   a. Web UI, no install: signed in as WilwilMina, open huggingface.co/new-dataset -> Owner WilwilMina, name
      clarity-clip1, license cc-by-4.0, Public -> Create dataset -> Files and versions -> Contribute (older pages:
      Add file) -> Upload files -> drag in the seven files (the files, not the folder) -> Commit changes to main.
   b. CLI (needs `pip install huggingface_hub`, which isn't installed here, plus `huggingface-cli login`
      with a write token; never commit the token):
        huggingface-cli upload WilwilMina/clarity-clip1 data/raw/publish/clarity-clip1 --repo-type dataset
      (newer huggingface_hub versions name the command `hf upload`; same arguments)
5. Put the dataset link into data/staged/README.md (the "Download" line, the clip 1 section and the attribution
   line) and into data/README.md.
6. The GitHub links below point at main, so they only work after the branch is merged to main.
-->

# Clarity clip 1: a mimed stabbing seen by four cameras

Four short videos of one staged street attack, seen from four camera spots along the suspect's escape route. The attack is a stabbing **mimed with an empty hand**: there is no knife, weapon or prop of any kind. The Clarity team filmed it in downtown Raleigh, NC, on Oct 17, 2026, during the NVIDIA x Red Hat Small Models Hack, to test camera-to-camera suspect handoff on real footage. It is the clip Clarity's live demo plays.

The four views are **four separate runs of the same scene**, filmed one after another on one phone. They are not one escape filmed by four cameras at once. Clarity replays them on one clock as if they were (see [Ground truth](#ground-truth-and-timing)).

- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Method (how it was filmed, labeled and processed):** [`data/staged/README.md`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/main/data/staged/README.md) in the Clarity repo; its clip 1 section covers this clip
- **Code:** [github.com/waliviqas/clarity-hackathon-n-r](https://github.com/waliviqas/clarity-hackathon-n-r)
- **Companion dataset:** [WilwilMina/clarity-clip8](https://huggingface.co/datasets/WilwilMina/clarity-clip8), a staged phone snatch filmed the same afternoon, seen by three cameras

## Files

| File | Camera | Spot | Length | Suspect in view (clip seconds) |
|---|---|---|---|---|
| `cam1.mp4` | `cam_07` | sidewalk by street parking: the attack | 8.1 s, 81 frames | 4.2 to 7.1 s; the mimed stab at 5.6 s |
| `cam2.mp4` | `cam_08` | sidewalk by painted parklet | 3.0 s, 30 frames | 0.9 to 2.6 s (runs past) |
| `cam3.mp4` | `cam_09` | crosswalk corner | 5.5 s, 55 frames | 0 s (standing at the curb) to the end (still in view, far off, when the clip ends) |
| `cam4.mp4` | `cam_10` | sidewalk by building column: the exit | 4.2 s, 42 frames | 0.15 s to the end (still in view, down the sidewalk, when the clip ends) |
| `take3.json` | | | | Ground truth: crime type, suspect outfit, and the suspect's path across the four cameras on one run clock |
| `clip_log_take3.csv` | | | | The per-view log the ground truth was built from: spot, position (`lat`, `lon`: placed; `gps_lat`, `gps_lon`, `gps_accuracy_m`: the raw GPS, see [Camera positions](#camera-positions)), clip file, enter/exit seconds, estimated travel time, notes |

All four videos are 1280x720, a constant 10 fps, H.264 (8-bit 4:2:0), with **no audio** and no file metadata about where, when or on which device they were filmed. They were converted from the phone's original clips (`IMG_7352` to `IMG_7355`).

**File names:** the clip log and the Clarity code call the files `clip1_cam1.mp4` to `clip1_cam4.mp4`. To run them through the Clarity pipeline, copy them into `data/raw/staged/take3/` under those names (`cam1.mp4` becomes `clip1_cam1.mp4`, and so on), then follow the method page. Camera IDs are unique across the team's clips, which is why this clip starts at `cam_07` (clip 8 uses `cam_01` to `cam_03`).

**Labels:** the crime is labeled `stabbing`, one of Clarity's four activity labels (`stabbing`, `fistfight`, `purse_snatch`, `none`). The suspect wears a black hoodie and dark grey trousers. Some clip-log columns are blank: `phone_owner` (on purpose), `heading_deg` (the direction each phone faced was not recorded), and `clock_shown_at_s` and `clock_reading_hhmmss` (no clock is in view).

## Ground truth and timing

`take3.json` places the four views on one run clock, as if four cameras saw one escape: the suspect is in `cam_07` from 5.0 to 7.9 s, in `cam_08` from 14.9 to 16.6 s, in `cam_09` from 22.6 to 27.91 s, and in `cam_10` from 30.91 to 34.8 s. A run-clock time is the clip time plus the clip's start on the run clock: 0.8 s for `cam1.mp4`, 14.0 s for `cam2.mp4`, 22.6 s for `cam3.mp4` and 30.76 s for `cam4.mp4`.

The gaps between views (7 s from `cam_07` to `cam_08`, 6 s from `cam_08` to `cam_09`, 3 s from `cam_09` to `cam_10`; `travel_s` in the clip log) are **estimated running times** over the distances between the spots (about 24 m, 21 m and 10 m). They were not measured, because the views come from separate runs and no clock is in view. The last one is the roughest, because its 10 m is itself an estimate (see [Camera positions](#camera-positions)).

In `cam_09` and `cam_10` the suspect is still in view when the clip ends, so their `t_exit` is where the logged sighting stops, just before the clip's last frame, not the moment the suspect leaves. `camera_roles` marks each camera as `crime`, `path` or `exit`, and `decoy_camera_id` is `null` (no decoy). The enter and exit times come from the team's clip log and were read from the video frames.

## Camera positions

| Camera | Spot | Raw GPS (lat, lon) | GPS accuracy | Placed (lat, lon) |
|---|---|---|---|---|
| `cam_07` | sidewalk by street parking | 35.7755, -78.6371 | ±6 m | 35.77550, -78.63710 (its GPS fix) |
| `cam_08` | sidewalk by painted parklet | 35.7757, -78.6370 | ±25 m | 35.77570, -78.63700 (its GPS fix, 24 m from `cam_07`) |
| `cam_09` | crosswalk corner | 35.7756, -78.6368 | ±20 m | 35.77560, -78.63680 (its GPS fix, 21 m from `cam_08`) |
| `cam_10` | sidewalk by building column | 35.7756, -78.6368 | ±5 m | 35.77555, -78.63671 (**estimate**: about 10 m southeast of `cam_09`) |

The raw GPS comes from each clip's metadata, given to 4 decimals (steps of about 10 m), with the phone's stated accuracy. The fixes of `cam_07`, `cam_08` and `cam_09` are already in route order, so those cameras stay at their fixes. The `cam_08` and `cam_09` fixes are coarse (±25 m and ±20 m), so their positions are approximate.

**`cam_10`'s position is an estimate.** Its fix is the same 4-decimal point as `cam_09`'s, so the GPS can't separate the two. It is placed about 10 m past `cam_09`, continuing the heading from `cam_08` to `cam_09` (southeast is an assumption). That puts it about 10 m from its own fix: more than the fix's stated ±5 m accuracy, but within that accuracy plus the rounding to 4 decimals (about ±5 m). In `clip_log_take3.csv`, `lat` and `lon` are the placed positions, and `gps_lat`, `gps_lon` and `gps_accuracy_m` are the raw GPS.

## Consent and privacy

- **People on screen:** two people act the scene, the suspect and the person attacked. Both agreed to be filmed; the team asked them. They are not named here. The attack is mimed: nobody was hurt, and there are no knives, weapons or weapon-like props.
- **No blur needed.** Apart from those two, the only people in view are far in the background: passers-by across the street in `cam1.mp4` and `cam3.mp4` (in `cam3.mp4`, one walks a dog, seen from behind) and far down the sidewalk in `cam4.mp4`, and the driver of a passing minivan in `cam3.mp4`, visible only as a shape behind the glass. None of them can be recognized, so nothing is blurred: the video is exactly what Clarity's demo plays. Our coding assistant (Claude Code) checked whole frames of all four views, two per second, on review sheets. It also zoomed in at full resolution on the background people, the parked cars' licence plates and the name badge the person attacked wears. No bystander's face, no plate and no badge text can be made out.
- **Cars:** parked and passing cars appear in every view. No licence plate is readable, and drivers are visible only as shapes behind glass.
- **No audio:** the conversion removed the sound track, which could carry bystanders' voices.
- **Location on purpose:** the clip log gives each spot's rounded GPS fix (public streets), so the camera map can be rebuilt. The video files themselves carry no location.

## How it was made

The method page, [`data/staged/README.md`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/main/data/staged/README.md), covers how we filmed, labeled, converted and built the ground truth. Its clip 1 section is about this clip.

In short:
1. One handheld iPhone filmed the four spots one after another (`IMG_7352` to `IMG_7355`). The scene was acted once per spot.
2. `data/convert_clips.py` converted each clip to 720p, constant 10 fps, H.264 with no audio.
3. The enter and exit times, positions and estimated running times went into the clip log. `data/build_site.py` turned the log into `take3.json` and the camera map.
4. [`data/publish_clip1.py`](https://github.com/waliviqas/clarity-hackathon-n-r/blob/main/data/publish_clip1.py) built this package. Nothing needed blurring, so each clip's video stream was copied without re-encoding: every decoded frame was compared with the converted clip's and is the same. All four files were written without file metadata, because phone clips can carry the GPS position, recording time and phone model there. ffprobe confirmed one video stream per file, no audio, and no location, date or device tags, and a scan of the file bytes found no Apple metadata and no location atom.

## Limitations

- **Staged and mimed.** The attack is acted with an empty hand, so no weapon is ever visible: the `stabbing` label rests on the motion and the fall. It may look gentler or more obvious than a real attack, and a viewer or a model may read it as a punch.
- **Four runs, not one escape.** Each view is a separate run, so the suspect's moves and the light differ a little between views, and the times between views are estimates, not measurements.
- **Two people.** One suspect and one person attacked. The suspect is played by the same person, in the same outfit, as in clip 8, so the two datasets are not independent. There is little variety in people, outfits and body types.
- **Small.** One incident, four clips, about 21 s of video (208 frames), one street, one afternoon, daylight only.
- **Not a fixed camera.** The phone was handheld, so the view moves a little during the clips.
- **GPS error.** Raw positions are accurate to only ±5 to 25 m, and `cam_10`'s position is an estimate (see [Camera positions](#camera-positions)). The placed positions are approximate.
- **No decoy view.** No clip shows an empty path, so the footage never asks a system to reject a non-match.

## Intended use

- Testing systems that detect a crime in video and pass a suspect's description from camera to camera, like Clarity.
- A small **test** set. Clip 1 is a test clip in Clarity's evaluation and was never used to train Clarity's fine-tuned spotter. If you compare with our numbers, don't train on it.

**Out of scope:** identifying or tracking real people, face recognition, and using the clips as evidence of a real crime.

## How to cite

> Clarity staged incident (clip 1), four camera views (Raleigh, Oct 17, 2026), by the Clarity team, NVIDIA x Red Hat Small Models Hack. CC BY 4.0. https://huggingface.co/datasets/WilwilMina/clarity-clip1

```bibtex
@misc{clarity_clip1_2026,
  title        = {Clarity clip 1: a mimed stabbing seen by four cameras},
  author       = {{The Clarity team}},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/WilwilMina/clarity-clip1}},
  note         = {NVIDIA x Red Hat Small Models Hack, Raleigh, NC. CC BY 4.0}
}
```
