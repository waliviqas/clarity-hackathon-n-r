# Data

Owner: Mina. Status: v0 research notes, Sat Oct 17. **Licenses below were checked on the source pages on Oct 17; re-check before relying on one.**

Raw downloads go in `data/raw/` (gitignored). Only small derived files (`cameras.json`, ground truth, manifests) are committed.

## What we need

1. **Staged multi-camera clips (primary).** Teammates act out incidents across 3–4 phone cameras around the Red Hat Annex, including **three incidents at once**. Published with the method, they're our main open-data contribution and give exact ground truth for the relay demo and NeMo Gym tasks.
2. **Licensed public footage (optional, not used in the demo).** Would strengthen the "meaningfully uses open data" criterion and give the spotter more examples of `fistfight` and `purse_snatch`.
3. **Train/test split** if the spotter is fine-tuned: test clips never appear in training.
4. **A real-world map** for the dashboard.

**Primary open data:** our staged clips (published with the method, see below) plus OpenStreetMap. Our staged clips are split into training and test clips for the spotter fine-tune (Wali's `labels.csv`, `split` column); the demo uses only test clip 8. Eight CAVIAR clips and three MEVA example clips are an external check set (Wali's `labels_external.csv`, `results/before_external.json`); see "External check clips" below. TODO: Wali to confirm none of them are used in training.

## Sources

| Source | What it gives us | License / terms | Use it for | Verdict |
|---|---|---|---|---|
| **MEVA** (Multiview Extended Video with Activities), mevadata.org | ~100 consenting actors, scripted activities, indoor + outdoor cameras with overlapping and non-overlapping views; geo-registered outdoor cameras; actor GPS logs; 37 annotated activities incl. threat-based `person_steals_object` and `person_abandons_package`. Collected under IRB approval. | **CC BY 4.0** (attribution required) | Multi-camera relay scenarios, ground-truth paths, `purse_snatch`-like events (`person_steals_object`) | **Optional (not used in the demo)** |
| **MEVA drop-4 subset on Hugging Face** (`Voxel51/extended_video_activities_drop_4`) | 201 clips of MEVA Known Facility 1; the MeVID re-ID benchmark annotates the same people across cameras on this footage | CC BY 4.0 (videos from mevadata.org) | Fastest way to start; check how many people appear on 3+ cameras within this subset | **Optional (not used in the demo)** |
| **Airtlab violence dataset** (github.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos) | 350 staged clips by non-professional actors (230 violent, 120 non-violent such as hugs and high-fives), filmed from **2 viewpoints** | "Freely released for research and educational purposes" (no formal license file) | `fistfight` examples and hard negatives for the VLM | Good secondary; note terms in README |
| **CAVIAR** (INRIA lobby), homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/ | Clips acted by the CAVIAR team in an entrance lobby, one high wide-angle camera (384×288): fights, walking, meeting, browsing | **CC BY-SA** (version not stated; adaptations stay CC BY-SA) | Spotter training candidates: 4 `fistfight`, 4 `none` | **Training candidate** |
| UCF-Crime | 13 anomaly classes incl. Fighting, Robbery, Stealing, Assault, Shoplifting; real surveillance footage | No license stated on the pages checked; real victims | Possibly eval only | **Avoid in the demo** (unclear license, real people) |
| RWF-2000 | 2,000 fight/non-fight surveillance clips | Videos **not available for download** due to privacy; no redistribution without lab approval | — | **Can't use** |
| **OpenStreetMap** via Leaflet | Map tiles around the Red Hat Annex (190 Davie St, Raleigh) | **ODbL**; show "© OpenStreetMap contributors" on the map | Dashboard base map | **Use** (also counts as open data) |

### The stabbing gap

No openly licensed dataset with stabbing footage turned up. Options, in order of preference:
1. Keep `stabbing` as a label the VLM can output, but don't build the demo around it.
2. Demo with `purse_snatch` and `fistfight` from our staged clips.
3. **Never** stage a stabbing with any blade or knife prop at the venue.

## Staged footage (our own synthetic data)

We may film teammates acting out a purse snatch or a scuffle across 3–4 phone cameras at the Annex. The rules allow this **only if we publish the clips and the method**. Requirements:
- Only consenting teammates on camera; no bystanders' faces.
- No weapons or props that look like weapons.
- Log each take: cameras used, positions, who did what, at what time. That log is the ground truth.
- Publish the clips (or a link) plus `data/staged/README.md` describing the method.

## Building the Annex site from the clip log

The site is built from the committed clip log `data/staged/clip_log_take1.csv` (take 1, `phone_owner` blank). From the repo root:

```
python data/convert_clips.py "<folder with the original clips>" --out data/raw/staged/take1   # 720p, constant 10 fps, H.264, audio stripped
python data/build_site.py data/staged/clip_log_take1.csv --check-clips data/raw/staged
python contracts/validate.py data/sites/annex/cameras.json
python -m feeds.replay --cameras data/sites/annex/cameras.json --check            # before every real run
python data/check_build_site.py          # after changing build_site.py or the log: also checks the log rebuilds the site files
```

**Current site: take 1 only** (clip 8, method in [`staged/README.md`](staged/README.md)). One phone filmed its three views one after another, with no clock in view, so the runs between cameras are Wali's distance-based estimates (`travel_s` 3 s and 6 s). Clips 7 and 1 are converted and their timing is in the team's local log (`data/staged/clip_log.csv`, gitignored because it names phone owners), but they are not built. For new takes, fill in a copy of `data/staged/clip_log_template.csv` (one row per camera) and commit a copy with `phone_owner` blank.

- **Convert first** (`data/convert_clips.py`, needs `ffmpeg`: `sudo apt-get install -y ffmpeg`). It writes a `.mp4` copy next to each clip; point the log's `clip_file` cells at the `.mp4` names. Originals that are already `.mp4` need `--out` (e.g. `data/raw/wali_clips/take1 --out data/raw/staged/take1`). Audio is dropped for privacy, and a constant frame rate keeps feeds' clock exact.
- **Routes:** list each take's route rows in route order: an optional `approach` (the suspect is seen before the crime), the `crime`, any number of `path` cameras (`junction` is the older name), and the `exit` last. An optional `decoy` (an empty path, filmed separately) branches off the camera before the exit. Consecutive route cameras are linked both ways, with directions from lat/lon.
- **Alignment:** each take is lined up on its crime: the crime row's `suspect_enter` plays at run-clock 5 / 15 / 25 s (takes 1/2/3). The other clips follow by one of two rules, so a clip may start before 0 (feeds skips those frames):
  - **Clock** (the clips show a seconds clock): clips are synced by the clock. A link's travel time is the next camera's `suspect_enter` minus the previous camera's `suspect_exit` (0 if the views overlap).
  - **No clock** (no clock cells in the take's route rows): a link's travel time is the later camera's `travel_s`, else the straight-line lat/lon distance at `--run-speed` (default 4 m/s). After the crime, each camera's `suspect_enter` = the previous camera's `suspect_exit` + travel; the approach's `suspect_exit` = the crime's `suspect_enter` − travel. These run-clock times are derived, not measured.
  - Decoy clips ignore their clock and start with the camera they branch off. The decoy link is the logged walk (its `travel_s`, or `stopwatch s: N` in its notes).
- **Directions:** a warning flags any camera with two neighbors in the same 8-way direction, because the graph can't tell them apart.
- **Positions** are the log's `lat`/`lon`. They start from the GPS in each clip's metadata (via Wali's `video-data/custom-clips/camera_positions.csv`). Take 1's fixes are accurate to only ±14–28 m, more than the 11–22 m between its cameras, and put the cameras out of route order (from `cam_02`, both neighbors came out `north`, and the build warned). So take 1's cameras are placed by hand in route order on a straight line heading north, within that error: `cam_01` at its fix, `cam_02` 11 m north, `cam_03` 22 m further north. The log keeps the raw GPS in three extra columns, `gps_lat`, `gps_lon` and `gps_accuracy_m`; `build_site.py` ignores columns it doesn't read. Raw vs placed, and why: [`staged/README.md`](staged/README.md#raw-gps-vs-placed-positions).
- **Neutral camera names:** `Route <N>: <spot_description>` (or `Route <N>: camera <k>`). Names never say approach / crime / junction / exit / decoy, because models may see them; a `spot_description` that does is an error. Roles live only in `data/ground_truth/take<N>.json` (`camera_roles`); its `path` lists every route camera in order, the approach included.
- Optional columns `heading_deg` (compass direction the phone faces, 0–360, goes into `cameras.json`) and `travel_s`. Older logs without them build to byte-identical outputs: `data/check_build_site.py` compares against the golden files in `data/staged/build_site_golden/`.
- `--check-clips DIR` fails, listing every `clip_file` not found as `DIR/take<N>/<clip_file>` with the exact upper/lower case (the Brev box is Linux). `feeds.replay --check` opens every clip and prints resolution, fps, frame count, duration and codec; exit code 1 if any is missing or unreadable.

`build_site.py` writes `data/sites/annex/cameras.json`, `data/ground_truth/take<N>.json` and `data/manifests/annex.json` (stdlib only). Any blank or malformed cell stops the build with the row and column named; nothing is written until the whole log is clean. `phone_owner` is never copied into the outputs.

## External check clips (CAVIAR and MEVA)

Collected first as training candidates; the spotter is now trained on the train split of our own staged clips, and these 11 public clips serve as an external check set, filmed elsewhere (TODO: Wali to confirm none are used in training; hard rule 6). Videos and frames live in `data/raw/training/` (gitignored). `data/training/staged_clips.csv` holds the labels (one row per person once verified); `data/training/SOURCES.md` has the license research and the shortfall against the 20-clip mix.

- **CAVIAR** (8 clips): Fight_RunAway1, Fight_RunAway2, Fight_OneManDown, Fight_Chase, Walk1, Walk2, Meet_WalkTogether1, Browse1. Source: EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/. License: CC BY-SA. We modified the clips (frame extraction, labels).
- **MEVA** (3 example clips): ex085-theft, ex007-embrace-interaction, ex050-people-talking. "Multiview Extended Video with Activities" (MEVA) dataset by Kitware Inc., https://mevadata.org. License: CC BY 4.0 (https://mevadata.org/resources/MEVA-data-license.txt). We modified the clips (frame extraction, labels).
  - These example videos have MEVA's activity labels burned in (red boxes and text such as "Theft:1"), so a model trained on them can learn the overlay. The overlay also names the clean source file (ex085: `2018-03-15.15-10-00.15-15-00.bus.G331`, frame ~6383), which is in MEVA's public bucket.
  - ex085 shows a bag lifted from the bench beside its seated owner, not grabbed from a person, so `purse_snatch` is questionable for it.

```
python data/scripts/fetch_staged_clips.py data/training/staged_clips.csv --fps 2 --local-dir data/videos   # frames + contact sheets for review
python data/scripts/check_staged_clips.py data/training/staged_clips.csv                                   # label checks (needs pandas)
```

## Public training clips (spotter fine-tune)

Train split only; links, cuts and labels in `data/training/` (`public_clips_candidates.csv`, `labels_public.csv`; details in `training/SOURCES.md`). The clips are rebuilt from the links with `data/scripts/fetch_public_clips.py` and never re-hosted.
- **AIRTLab**: stabbing, assault and non-violent IDs, cam1 + cam2. Research and education only (no LICENSE file); team decision: link only, don't re-host.
- **Mixkit**: hand-picked thefts, one fleeing clip and normals, each page checked for the Stock Video Free License ("Restricted" items skipped); link only.
- **MEVA** (drops-123-r13): 10–15 s cuts around annotated thefts and hugs, CC BY 4.0; we cut and re-encoded them. ex085's video is never used.

## Derived files we commit

| File | Contents | Consumers |
|---|---|---|
| `data/cameras.json` (one per site, e.g. `data/sites/annex/cameras.json`) | Camera graph per `contracts/schemas/cameras.schema.json` | Graph, feeds, bus, dashboard |
| `data/ground_truth/*.json` | Per scenario: subject, activity, ordered `[{camera_id, t_enter, t_exit}]` | NeMo Gym tasks, eval |
| `data/manifests/*.json` | Which clip maps to which camera and its start time | Feeds |

## Attribution text (put in the README and the video credits)

- MEVA (only if used): Corona, K., Osterdahl, K., Collins, R., Hoogs, A. "MEVA: A Large-Scale Multiview, Multimodal Video Dataset for Activity Detection." WACV 2021. Data from mevadata.org, CC BY 4.0.
- CAVIAR (training clips, if used): EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/. CC BY-SA.
- Map data © OpenStreetMap contributors, ODbL.
- AIRTLab (training clips): M. Bianculli, N. Falcionelli, P. Sernani, S. Tomassini, P. Contardo, M. Lombardi, A.F. Dragoni, "A dataset for automatic violence detection in videos," Data in Brief 33 (2020), doi:10.1016/j.dib.2020.106587 (citation as given in the dataset's readme).
- Mixkit (training clips): stock videos from mixkit.co under the Mixkit Stock Video Free License; clip pages listed in `training/public_clips_candidates.csv`.
