# Data

Owner: Mina. Status: v0 research notes, Sat Oct 17. **Licenses below were checked on the source pages on Oct 17; re-check before relying on one.**

Raw downloads go in `data/raw/` (gitignored). Only small derived files (`cameras.json`, ground truth, manifests) are committed.

## What we need

1. **Staged multi-camera clips (primary).** Teammates act out incidents across 3–4 phone cameras around the Red Hat Annex, including **three incidents at once**. Published with the method, they're our main open-data contribution and give exact ground truth for the relay demo and NeMo Gym tasks.
2. **Licensed public footage (optional, not used in the demo).** Would strengthen the "meaningfully uses open data" criterion and give the spotter more examples of `fistfight` and `purse_snatch`.
3. **Train/test split** if the spotter is fine-tuned: test clips never appear in training.
4. **A real-world map** for the dashboard.

**Primary open data:** our staged clips (published with the method, see below) plus OpenStreetMap. The team decided to skip MEVA for the demo; three MEVA example clips and eight CAVIAR clips are spotter training candidates (see "Training clips" below).

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

Fill in a copy of `data/staged/clip_log_template.csv` (one row per camera, 4 per take), then from the repo root:

```
python data/convert_clips.py data/raw/staged                  # on Brev: 720p, constant 10 fps, H.264, audio stripped
python data/build_site.py data/staged/clip_log.csv --check-clips data/raw/staged   # add --takes 1 while only take 1 is logged
python contracts/validate.py data/sites/annex/cameras.json
python -m feeds.replay --cameras data/sites/annex/cameras.json --check            # before every real run
```

- **Convert first** (`data/convert_clips.py`, needs `ffmpeg`: `sudo apt-get install -y ffmpeg`). It writes a `.mp4` copy next to each clip; point the log's `clip_file` cells at the `.mp4` names. Audio is dropped for privacy, and a constant frame rate keeps feeds' clock exact.
- **Alignment:** clips are synced by the clock shown in each clip. Each take is lined up on its crime: the crime row's `suspect_enter` plays at run-clock 5 / 15 / 25 s (takes 1/2/3); the junction and exit clips follow by the clock, so a clip may start before 0 (feeds skips those frames). Decoy clips (empty path, filmed separately) ignore their clock and start with the junction clip.
- **Travel times** are the walk between cameras: next camera's `suspect_enter` minus the previous camera's `suspect_exit` (0 if the views overlap); the decoy link is the logged stopwatch walk. A warning flags a junction whose two branches point the same 8-way direction.
- **Neutral camera names:** `Route <N>: <spot_description>` (or `Route <N>: camera <k>`). Names never say crime / junction / exit / decoy, because models may see them; a `spot_description` that does is an error. Roles live only in `data/ground_truth/take<N>.json` (`camera_roles`).
- Optional `heading_deg` column (compass direction the phone faces, 0–360) goes into `cameras.json`; older logs without the column still work.
- `--check-clips DIR` fails, listing every `clip_file` not found as `DIR/take<N>/<clip_file>` with the exact upper/lower case (the Brev box is Linux). `feeds.replay --check` opens every clip and prints resolution, fps, frame count, duration and codec; exit code 1 if any is missing or unreadable.

`build_site.py` writes `data/sites/annex/cameras.json`, `data/ground_truth/take<N>.json` and `data/manifests/annex.json` (stdlib only). Any blank or malformed cell stops the build with the row and column named; nothing is written until the whole log is clean. `phone_owner` is never copied into the outputs.

## Training clips (spotter fine-tune candidates)

Only used if the spotter is fine-tuned. These are **training** clips; our Annex staged clips stay **test-only** and are never trained on (hard rule 6). Videos and frames live in `data/raw/training/` (gitignored). `data/training/staged_clips.csv` holds the labels (one row per person once verified); `data/training/SOURCES.md` has the license research and the shortfall against the 20-clip mix.

- **CAVIAR** (8 clips): Fight_RunAway1, Fight_RunAway2, Fight_OneManDown, Fight_Chase, Walk1, Walk2, Meet_WalkTogether1, Browse1. Source: EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/. License: CC BY-SA. We modified the clips (frame extraction, labels).
- **MEVA** (3 example clips): ex085-theft, ex007-embrace-interaction, ex050-people-talking. "Multiview Extended Video with Activities" (MEVA) dataset by Kitware Inc., https://mevadata.org. License: CC BY 4.0 (https://mevadata.org/resources/MEVA-data-license.txt). We modified the clips (frame extraction, labels).
  - These example videos have MEVA's activity labels burned in (red boxes and text such as "Theft:1"), so a model trained on them can learn the overlay. The overlay also names the clean source file (ex085: `2018-03-15.15-10-00.15-15-00.bus.G331`, frame ~6383), which is in MEVA's public bucket.
  - ex085 shows a bag lifted from the bench beside its seated owner, not grabbed from a person, so `purse_snatch` is questionable for it.

```
python data/scripts/fetch_staged_clips.py data/training/staged_clips.csv --fps 2 --local-dir data/videos   # frames + contact sheets for review
python data/scripts/check_staged_clips.py data/training/staged_clips.csv                                   # label checks (needs pandas)
```

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
- Airtlab (if used): "A dataset for automatic violence detection in videos," Data in Brief, 2020 (https://pmc.ncbi.nlm.nih.gov/articles/PMC7725718/). Copy the authors from that page.
