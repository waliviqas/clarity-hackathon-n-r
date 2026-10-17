# Data

Owner: Mina. Status: v0 research notes, Sat Oct 17. **Licenses below were checked on the source pages on Oct 17; re-check before relying on one.**

Raw downloads go in `data/raw/` (gitignored). Only small derived files (`cameras.json`, ground truth, manifests) are committed.

## What we need

1. **Staged multi-camera clips (primary).** Teammates act out incidents across 3–4 phone cameras around the Red Hat Annex, including **three incidents at once**. Published with the method, they're our main open-data contribution and give exact ground truth for the relay demo and NeMo Gym tasks.
2. **Licensed public footage (optional, not used in the demo).** Would strengthen the "meaningfully uses open data" criterion and give the spotter more examples of `fistfight` and `purse_snatch`.
3. **Train/test split** if the spotter is fine-tuned: test clips never appear in training.
4. **A real-world map** for the dashboard.

**Primary open data:** our staged clips (published with the method, see below) plus OpenStreetMap. The team decided to skip MEVA; it stays listed below with its license in case we add it later.

## Sources

| Source | What it gives us | License / terms | Use it for | Verdict |
|---|---|---|---|---|
| **MEVA** (Multiview Extended Video with Activities), mevadata.org | ~100 consenting actors, scripted activities, indoor + outdoor cameras with overlapping and non-overlapping views; geo-registered outdoor cameras; actor GPS logs; 37 annotated activities incl. threat-based `person_steals_object` and `person_abandons_package`. Collected under IRB approval. | **CC BY 4.0** (attribution required) | Multi-camera relay scenarios, ground-truth paths, `purse_snatch`-like events (`person_steals_object`) | **Optional (not used in the demo)** |
| **MEVA drop-4 subset on Hugging Face** (`Voxel51/extended_video_activities_drop_4`) | 201 clips of MEVA Known Facility 1; the MeVID re-ID benchmark annotates the same people across cameras on this footage | CC BY 4.0 (videos from mevadata.org) | Fastest way to start; check how many people appear on 3+ cameras within this subset | **Optional (not used in the demo)** |
| **Airtlab violence dataset** (github.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos) | 350 staged clips by non-professional actors (230 violent, 120 non-violent such as hugs and high-fives), filmed from **2 viewpoints** | "Freely released for research and educational purposes" (no formal license file) | `fistfight` examples and hard negatives for the VLM | Good secondary; note terms in README |
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
python data/build_site.py data/staged/clip_log.csv            # add --takes 1 while only take 1 is logged
python contracts/validate.py data/sites/annex/cameras.json
```

It writes `data/sites/annex/cameras.json`, `data/ground_truth/take<N>.json` and `data/manifests/annex.json` (stdlib only). Clips are synced by the clock shown in each clip; each take's earliest crime/junction/exit clip starts at run-clock +0 / +10 / +20 s, so the three takes replay overlapped and nothing starts before 0. Decoy clips (empty path, filmed separately) ignore their clock and start with the junction clip. Travel times are differences of suspect-enter times; the decoy link is the logged stopwatch walk. Any blank or malformed cell stops the build with the row and column named; nothing is written until the whole log is clean. `phone_owner` is never copied into the outputs.

## Derived files we commit

| File | Contents | Consumers |
|---|---|---|
| `data/cameras.json` (one per site, e.g. `data/sites/annex/cameras.json`) | Camera graph per `contracts/schemas/cameras.schema.json` | Graph, feeds, bus, dashboard |
| `data/ground_truth/*.json` | Per scenario: subject, activity, ordered `[{camera_id, t_enter, t_exit}]` | NeMo Gym tasks, eval |
| `data/manifests/*.json` | Which clip maps to which camera and its start time | Feeds |

## Attribution text (put in the README and the video credits)

- MEVA (only if used): Corona, K., Osterdahl, K., Collins, R., Hoogs, A. "MEVA: A Large-Scale Multiview, Multimodal Video Dataset for Activity Detection." WACV 2021. Data from mevadata.org, CC BY 4.0.
- Map data © OpenStreetMap contributors, ODbL.
- Airtlab (if used): "A dataset for automatic violence detection in videos," Data in Brief, 2020 (https://pmc.ncbi.nlm.nih.gov/articles/PMC7725718/). Copy the authors from that page.
