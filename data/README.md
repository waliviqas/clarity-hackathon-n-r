# Data

Owner: Mina. Status: final for the submission, Sun Oct 18. **Licenses below were checked on each source's own page on Oct 17–18; re-check before relying on one.**

Raw downloads and all video go in `data/raw/` (gitignored); clips are published only through a dataset link. Only small derived files (camera maps, ground truth, manifests, clip logs, labels, link lists) are committed.

## What we use

1. **Our staged clips (the main open data).** On Oct 17 the team filmed 13 staged incidents (clips 1 to 13, 34 camera views) in downtown Raleigh, near the Red Hat Annex. Wali's `labels.csv` (repo root) labels every view and splits them for the spotter fine-tune: clips 1, 3, 4, 7, 8, 12 and 13 are test clips (18 views, never used for training); clips 2, 5, 6, 9, 10 and 11 are training clips (16 views).
   - **Clip 8** (test; a phone snatch, 3 cameras) is **published** with its method: https://huggingface.co/datasets/WilwilMina/clarity-clip8 (method: [`staged/README.md`](staged/README.md)). The earlier scripted fallback run, `runs/run_1018-0028_r2s`, is on clip 8's site.
   - **Clip 1** (test; a mimed stabbing, 4 cameras) is the **live demo** (`data/sites/annex_clip1/`). Both people on screen agreed to be filmed. It is **published** as [WilwilMina/clarity-clip1](https://huggingface.co/datasets/WilwilMina/clarity-clip1) (CC BY 4.0): a frame-by-frame look found no recognizable bystanders, and a teammate checked the same sheets before upload.
   - **Clips 4, 11 and 12 are not published** (clip 11 is a training clip).
2. **Public clips**, filmed elsewhere:
   - an **external check set** (CAVIAR and MEVA example clips) that tests the spotter on footage from outside our site;
   - **public training clips** (AIRTLab, Mixkit and MEVA cuts), which went only into the spotter versions v4 and v5. Both scored lower than v3 and were rejected.
3. **The final spotter, v3,** was trained on our training clips, on the crime fields only (whether there is a crime, and its type). Whether it also trained on the 11 external clips is an **open question for Wali** (see [External check clips](#external-check-clips-caviar-and-meva)).
4. **OpenStreetMap** for the dashboard map.

## Sources

| Source | What it gives us | License / terms | How we use it | Status |
|---|---|---|---|---|
| **Our staged clips** ([`staged/README.md`](staged/README.md)) | 13 staged incidents, 34 camera views, filmed by the team on Oct 17; labels in `labels.csv` | Clips 8 and 1: **CC BY 4.0** | Spotter fine-tune (training clips) and its test (test clips); the two demo sites | **Used.** Clips 8 and 1 published; clip 1 is the live demo |
| **MEVA** (Multiview Extended Video with Activities), mevadata.org | ~100 consenting actors, scripted activities, indoor + outdoor cameras with overlapping and non-overlapping views; geo-registered outdoor cameras; actor GPS logs; 37 annotated activities incl. threat-based `person_steals_object` and `person_abandons_package`. Collected under IRB approval. | **CC BY 4.0** (attribution required) | Cut training clips (thefts, hugs, hand contact); example clips in the external check | **Used.** The training cuts went only into the rejected v4 and v5. ex007 and ex050 are in the external check (ex085 dropped); like CAVIAR's, they were in v2's training data, and whether v3 trained on them is open |
| **MEVA drop-4 subset on Hugging Face** (`Voxel51/extended_video_activities_drop_4`) | 201 clips of MEVA Known Facility 1; the MeVID re-ID benchmark annotates the same people across cameras on this footage | CC BY 4.0 (videos from mevadata.org) | — | **Not used** |
| **AIRTLab violence dataset** (github.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos) | 350 staged clips by non-professional actors (230 violent, 120 non-violent such as hugs and high-fives), filmed from **2 viewpoints** | "Freely released for research and educational purposes" (no formal license file) | Public training clips: stabbings, assaults and hard negatives; link only, never re-hosted | **Used only in the rejected v4 and v5**; v3 doesn't use it |
| **Mixkit** (mixkit.co) | Hand-picked stock clips: thefts, one fleeing clip, normal scenes | Mixkit Stock Video Free License, checked on each clip page (Oct 18); its Acceptable Use Policy is unread | Public training clips; link only, never re-hosted | **Used only in the rejected v4 and v5** |
| **CAVIAR** (INRIA lobby), homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/ | Clips acted by the CAVIAR team in an entrance lobby, one high wide-angle camera (384×288): fights, walking, meeting, browsing | **CC BY-SA** (version not stated; adaptations stay CC BY-SA) | External check: 4 `fistfight`, 4 `none` | **External check.** Also in v2's training data; whether v3 trained on them is open |
| UCF-Crime | 13 anomaly classes incl. Fighting, Robbery, Stealing, Assault, Shoplifting; real surveillance footage | No license stated on the pages checked; real victims | — | **Not used** (unclear license, real people) |
| RWF-2000 | 2,000 fight/non-fight surveillance clips | Videos **not available for download** due to privacy; no redistribution without lab approval | — | **Not used** (can't download) |
| **OpenStreetMap** via Leaflet | Map tiles around the Red Hat Annex (190 Davie St, Raleigh) | **ODbL**; show "© OpenStreetMap contributors" on the map | Dashboard base map | **Used** (also open data) |

### Stabbing: mimed, never with a prop

We found no openly licensed stabbing footage we could re-host. AIRTLab's acted stabbings are research and education only (link only), and they went only into the rejected v4 and v5. So our stabbings are mimed with empty hands, never with a knife or anything that looks like one. Test clip 1, the live demo, is one of them: the suspect mimes a stabbing (no prop), the person falls and the suspect runs off. In the recorded answers of the final system on clip 1 (`data/answers/clip1_system_v3_checker.json`), the spotter calls it an assault in all 3 runs, so the camera agents report a `fistfight` at `cam_07`.

## Staged footage (our own synthetic data)

The hackathon counts staged clips as open data only if we **publish the clips and the method** (method: [`staged/README.md`](staged/README.md)). How we filmed:
- Everyone who acts in a scene agreed to be filmed. Passers-by appear in some clips, so every clip gets a bystander check before publishing, and nothing we publish shows a recognizable bystander (clip 8's passers-by are blurred).
- No weapons and no props that look like weapons; stabbings are mimed with empty hands.
- Each take is logged: cameras, positions, who did what, at what time. That log is the ground truth; the logs of the two demo sites are committed with `phone_owner` blank (`data/staged/clip_log_take1.csv`, `clip_log_take3.csv`).
- Published: clip 8 with the method. Clip 1 (the live demo) with the same method: [WilwilMina/clarity-clip1](https://huggingface.co/datasets/WilwilMina/clarity-clip1). Clips 4, 11 and 12 are not published.

## Building the demo sites from the clip logs

Two sites are built from the committed clip logs (`phone_owner` blank), each with its own cameras:
- `data/sites/annex_clip1/`: take 3, **test clip 1, the live demo** (a mimed stabbing, `cam_07` to `cam_10`), from `data/staged/clip_log_take3.csv`. The bus serves it unless `CLARITY_CAMERAS` names another file. Method: [`staged/README.md`](staged/README.md#clip-1-the-live-demo-site).
- `data/sites/annex/`: take 1, **test clip 8, the published clip** (`cam_01` to `cam_03`), from `data/staged/clip_log_take1.csv`; the earlier scripted fallback run uses it. Method: [`staged/README.md`](staged/README.md).

In both takes one phone filmed the views one after another, with no clock in view, so the runs between cameras are distance-based estimates (`travel_s`). From the repo root:

```
python data/convert_clips.py "<folder with the original clips>" --out data/raw/staged/take3   # 720p, constant 10 fps, H.264, audio stripped
python data/build_site.py data/staged/clip_log_take3.csv --site annex_clip1 --site-name "Red Hat Annex (staged clip 1)" --run-offset 0 --check-clips data/raw/staged
python contracts/validate.py data/sites/annex_clip1/cameras.json
python -m feeds.replay --cameras data/sites/annex_clip1/cameras.json --check      # before every real run
python data/review_sheets.py data/raw/staged/take3     # whole frames, 2 per second, for the bystander check (data/raw/review/take3/)

python data/convert_clips.py "<folder with the original clips>" --out data/raw/staged/take1
python data/build_site.py data/staged/clip_log_take1.csv --check-clips data/raw/staged      # clip 8: site annex
python contracts/validate.py data/sites/annex/cameras.json
python -m feeds.replay --cameras data/sites/annex/cameras.json --check

python data/check_build_site.py          # after changing build_site.py or a log: also checks both committed logs rebuild their site files
```

Clip 7 is converted and its timing is in the team's local log (`data/staged/clip_log.csv`, gitignored because it names phone owners), but it is not built. For new takes, fill in a copy of `data/staged/clip_log_template.csv` (one row per camera) and commit a copy with `phone_owner` blank.

- **Convert first** (`data/convert_clips.py`, needs `ffmpeg`: `sudo apt-get install -y ffmpeg`). It writes a `.mp4` copy next to each clip; point the log's `clip_file` cells at the `.mp4` names. Originals that are already `.mp4` need `--out` (e.g. `data/raw/wali_clips/take1 --out data/raw/staged/take1`). Audio is dropped for privacy, and a constant frame rate keeps feeds' clock exact.
- **Routes:** list each take's route rows in route order: an optional `approach` (the suspect is seen before the crime), the `crime`, any number of `path` cameras (`junction` is the older name), and the `exit` last. An optional `decoy` (an empty path, filmed separately) branches off the camera before the exit. Consecutive route cameras are linked both ways, with directions from lat/lon.
- **Alignment:** each take is lined up on its crime: the crime row's `suspect_enter` plays at run-clock 5 / 15 / 25 s (takes 1/2/3). `--run-offset S` puts every take built at S + 5 s instead; the clip-1 site uses `--run-offset 0`, so its crime plays at 5 s like clip 8's. The other clips follow by one of two rules, so a clip may start before 0 (feeds skips those frames):
  - **Clock** (the clips show a seconds clock): clips are synced by the clock. A link's travel time is the next camera's `suspect_enter` minus the previous camera's `suspect_exit` (0 if the views overlap).
  - **No clock** (no clock cells in the take's route rows): a link's travel time is the later camera's `travel_s`, else the straight-line lat/lon distance at `--run-speed` (default 4 m/s). After the crime, each camera's `suspect_enter` = the previous camera's `suspect_exit` + travel; the approach's `suspect_exit` = the crime's `suspect_enter` − travel. These run-clock times are derived, not measured.
  - Decoy clips ignore their clock and start with the camera they branch off. The decoy link is the logged walk (its `travel_s`, or `stopwatch s: N` in its notes).
- **Directions:** a warning flags any camera with two neighbors in the same 8-way direction, because the graph can't tell them apart.
- **Positions** are the log's `lat`/`lon`. They start from the GPS in each clip's metadata (via Wali's `video-data/custom-clips/camera_positions.csv`). Take 1's fixes are accurate to only ±14–28 m, more than the 11–22 m between its cameras, and put the cameras out of route order (from `cam_02`, both neighbors came out `north`, and the build warned). So take 1's cameras are placed by hand in route order on a straight line heading north, within that error: `cam_01` at its fix, `cam_02` 11 m north, `cam_03` 22 m further north. Take 3's fixes (±5–25 m) are already in route order, 24 m and 21 m apart (the sheet's distances), so `cam_07` to `cam_09` stay at their fixes; `cam_10` shares `cam_09`'s rounded fix, so it is placed about 10 m further on, continuing southeast (an estimate, like its 3 s `travel_s`). The log keeps the raw GPS in three extra columns, `gps_lat`, `gps_lon` and `gps_accuracy_m`; `build_site.py` ignores columns it doesn't read. Raw vs placed, and why: [`staged/README.md`](staged/README.md#raw-gps-vs-placed-positions).
- **Neutral camera names:** `Route <N>: <spot_description>` (or `Route <N>: camera <k>`). Names never say approach / crime / junction / exit / decoy, because models may see them; a `spot_description` that does is an error. Roles live only in `data/ground_truth/take<N>.json` (`camera_roles`); its `path` lists every route camera in order, the approach included.
- Optional columns `heading_deg` (compass direction the phone faces, 0–360, goes into `cameras.json`) and `travel_s`. Older logs without them build to byte-identical outputs: `data/check_build_site.py` compares against the golden files in `data/staged/build_site_golden/`.
- `--check-clips DIR` fails, listing every `clip_file` not found as `DIR/take<N>/<clip_file>` with the exact upper/lower case (the Brev box is Linux). `feeds.replay --check` opens every clip and prints resolution, fps, frame count, duration and codec; exit code 1 if any is missing or unreadable.

`build_site.py` writes `data/sites/<site>/cameras.json`, `data/ground_truth/take<N>.json` and `data/manifests/<site>.json`, where `<site>` is `--site` (default `annex`) (stdlib only). Any blank or malformed cell stops the build with the row and column named; nothing is written until the whole log is clean. `phone_owner` is never copied into the outputs.

## External check clips (CAVIAR and MEVA)

Eleven public clips filmed elsewhere: 8 from CAVIAR and 3 MEVA example clips. They were collected as training candidates, then became the external check set, which tests the spotter on footage from outside our site. ex085 was dropped from the check on Oct 18 because of its burned-in labels, so 10 remain. The base model's results on all 11 are in `results/before_external.json` (repo root).

**Open question for Wali: did these clips train v3?** Wali's draft labels for them, `labels_external.csv` (repo root), mark all 11 `split=train`, and they trained v2 ("+ 11 public clips" in the model card, `hf_model/README.md`). Whether v3, the final spotter, also trained on them is not recorded. Until Wali answers, the external check may overlap training (hard rule 6: training and test clips stay separate).

Both label files are kept:
- `labels_external.csv` (repo root, Wali): the draft labels, all `split=train`, used to train v2. Its `check` column marks the crime rows' outfits as low confidence (drafted from tiny overhead frames) and the other rows as dataset labels not checked frame by frame.
- `data/training/labels_external_filled.csv` (Mina): the same 11 clips labeled from frames, every field checked on a second frame, in the same format (identical header, `split=external`). `data/training/staged_clips.csv` holds these labels one row per person (23 rows); `data/training/SOURCES.md` has the license research.

Videos and frames live in `data/raw/training/` (gitignored).

- **CAVIAR** (8 clips): Fight_RunAway1, Fight_RunAway2, Fight_OneManDown, Fight_Chase, Walk1, Walk2, Meet_WalkTogether1, Browse1. Source: EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/. License: CC BY-SA. We modified the clips (frame extraction, labels).
- **MEVA** (3 example clips): ex085-theft, ex007-embrace-interaction, ex050-people-talking. "Multiview Extended Video with Activities" (MEVA) dataset by Kitware Inc., https://mevadata.org. License: CC BY 4.0 (https://mevadata.org/resources/MEVA-data-license.txt). We modified the clips (frame extraction, labels).
  - These example videos have MEVA's activity labels burned in (red boxes and text such as "Theft:1"), so a model trained on them can learn the overlay. The overlay also names the clean source file (ex085: `2018-03-15.15-10-00.15-15-00.bus.G331`, frame ~6383), which is in MEVA's public bucket.
  - ex085 shows a bag lifted from the bench beside its seated owner, not grabbed from a person, so `purse_snatch` is questionable for it.

```
python data/scripts/fetch_staged_clips.py data/training/staged_clips.csv --fps 2 --local-dir data/videos   # frames + contact sheets for review
python data/scripts/check_staged_clips.py data/training/staged_clips.csv                                   # label checks (needs pandas)
```

## Public training clips (only in the rejected v4 and v5)

Prepared as `split=train` clips for the spotter fine-tune; links, cuts and labels in `data/training/` (`public_clips_candidates.csv`: 115 camera files; `labels_public.csv`: 32 labeled here; details in `training/SOURCES.md`). The clips are rebuilt from the links with `data/scripts/fetch_public_clips.py` and never re-hosted. **They trained only v4 and v5** ("+ 113 public clips" in `hf_model/README.md`), which scored lower than v3 and were rejected (every version's scores: `results/history.csv`). v3 doesn't use them.
- **AIRTLab**: stabbing, assault and non-violent IDs, cam1 + cam2. Research and education only (no LICENSE file); team decision: link only, don't re-host. Any model version trained on these clips must say so on its model card.
- **Mixkit**: hand-picked thefts, one fleeing clip and normals, each page checked for the Stock Video Free License ("Restricted" items skipped); link only. Its Acceptable Use Policy is still unread.
- **MEVA** (drops-123-r13): 10–15 s cuts around annotated thefts and hugs, CC BY 4.0; we cut and re-encoded them. The clean source video behind ex085 (`2018-03-15.15-10-00.15-15-00.bus.G331`) is never cut.
- **Michael's MEVA batch:** `scripts/meva_training_clips.py` (repo root, Michael) picks hugs, hand-to-hand interactions and thefts from MEVA's annotations, cuts each into a 5–15 s clip (720p H.264, no audio) on the GPU box, and writes `labels_meva.csv` in Wali's format (`split=train`). His batch (68 clips by his count) stays on the Brev box, not in git.

## Files we commit

| File | Contents | Consumers |
|---|---|---|
| `data/sites/<site>/cameras.json` (`annex_clip1`: clip 1, the live demo and the bus default; `annex`: clip 8; `annex_placeholder`: made-up cameras for scripted runs) | Camera graph per `contracts/schemas/cameras.schema.json` | Graph, feeds, bus, dashboard |
| `data/ground_truth/take<N>.json` (take 1: clip 8; take 3: clip 1) | Per incident: subject, activity, ordered `[{camera_id, t_enter, t_exit}]` on the run clock, camera roles | NeMo Gym tasks, eval, `bus.fake_scenario --ground-truth` |
| `data/manifests/<site>.json` | Which clip maps to which camera and its start time | Feeds |
| `data/staged/clip_log_take1.csv`, `clip_log_take3.csv` | The clip logs the two sites are built from (`phone_owner` blank) | `data/build_site.py` |
| `data/answers/*.json` | Recorded model answers on our test clips, text only, converted from Wali's NeMo Gym results by `data/gym_answers.py` (e.g. `clip1_system_v3_checker.json`: his final system on clip 1, 3 runs per camera) | Camera agents: `python -m agents.run --answers` (replays without a GPU) |
| `data/training/` | Public clips: links, cuts, licenses and labels, incl. `labels_external_filled.csv` (frame-checked external labels) | Spotter fine-tune, external check |
| `labels.csv` (repo root, Wali) | Labels for our 13 staged clips, one row per camera view (34), with the train/test `split` | Fine-tune (`src/make_train_data.py`), eval, NeMo Gym tasks |
| `labels_external.csv` (repo root, Wali) | Draft labels for the 11 external clips, all `split=train`; used to train v2 (v3: open question, see above) | Fine-tune, external check |
| `results/` (repo root, Wali) | Scores: `history.csv` (every spotter version and the checker), `before.json` and `before_external.json` (base model), `nemo_gym/` (NeMo Gym runs), `vllm_bench.json` | README tables, `data/gym_answers.py` |
| `hf_model/README.md` (repo root, Wali) | Model card of the fine-tuned spotter v3, with every version's scores | Hugging Face model page |
| `scripts/meva_training_clips.py` (repo root, Michael) | Plans and cuts MEVA training clips, writes `labels_meva.csv` (his batch stays on the Brev box) | Spotter training clips |

## Attribution text (put in the README and the video credits)

- MEVA (training clips and the external check): Corona, K., Osterdahl, K., Collins, R., Hoogs, A. "MEVA: A Large-Scale Multiview, Multimodal Video Dataset for Activity Detection." WACV 2021. Data from mevadata.org, CC BY 4.0.
- CAVIAR (external-check clips): EC Funded CAVIAR project/IST 2001 37540, http://homepages.inf.ed.ac.uk/rbf/CAVIAR/. CC BY-SA.
- Map data © OpenStreetMap contributors, ODbL.
- AIRTLab (training clips): M. Bianculli, N. Falcionelli, P. Sernani, S. Tomassini, P. Contardo, M. Lombardi, A.F. Dragoni, "A dataset for automatic violence detection in videos," Data in Brief 33 (2020), doi:10.1016/j.dib.2020.106587 (citation as given in the dataset's readme).
- Mixkit (training clips): stock videos from mixkit.co under the Mixkit Stock Video Free License; clip pages listed in `training/public_clips_candidates.csv`.
