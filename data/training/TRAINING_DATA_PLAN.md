# Spotter training data: what we need and where to get it

For Wali's next fine-tune of the spotter (Qwen3-VL-2B). Status: **researched, nothing downloaded yet**. Sources were checked on Sat Oct 17, about 23:40 to 00:15, by Claude Code's researcher agent in a browser. Licenses were read on each source's own page; the links are below. Anything marked UNVERIFIED wasn't confirmed.

## 1. The ask (spec from the team, Sat Oct 17 ~23:35)

Goal: the spotter should (1) catch the crime, (2) name the type, and (3) describe the **attacker, not the victim**, on footage it has never seen. Today it memorizes people, because our clips show the same 2–3 friends swapping roles.

| Type | Minimum | Ideal |
|---|---|---|
| Stabbing (fake knife or stabbing motion) | 30 | 100+ |
| Assault (punch, shove, fight) | 30 | 100+ |
| Stealing (phone or purse snatch, pickpocket, bag grab, car) | 30 | 100+ |
| Normal scenes (walking, talking, hugging, running for a bus, handshakes, horseplay) | 60 | 200+ |
| Fleeing only (one person running off, nobody else involved) | 30 | 100+ |

- **Variety matters most.** We need 20–30 different attackers. Nobody should always be the attacker or always the victim. Attacker and victim should be dressed differently in every clip. Mix places, day and night, and distances. Use mostly a high CCTV-style angle.
- **Format:** 5–15 s per camera, one angle per file, 720p or 1080p H.264 MP4, landscape. The crime should be in the middle of the clip.
- **Labels:** one row per camera file in Wali's `labels.csv` format: `clip, cam, split, on_screen, crime, what_happened, build, height, shirt, pants, shoes, glasses, headwear, hair, bag, weapon, vehicle, check, video`.
  - Describe the attacker only.
  - Use clothing and build only. No skin color, race or faces.
  - Normal clips: `on_screen=none`, `crime=none`, and the description columns blank.
  - `split=train` always.
- **Rules:**
  - Never touch Wali's 7 test clips (1, 3, 4, 7, 8, 12, 13).
  - Anyone filmed must have consented.
  - No real crimes with identifiable bystanders.
  - Record every public clip's URL, license and attribution in [`SOURCES.md`](SOURCES.md).
  - Hand clips over in `video-data/training-clips/videos/` with a labels CSV.

## 2. Bottom line

- **No public source gives 20–30 different attackers with contrasting outfits.** So staging new clips with new people and clearly different attacker and victim outfits stays priority 1. Public data can't replace it.
- **Available tonight without a login:**
  - **AIRTLab**: acted, 1080p, high room corners. Covers stabbing, assault and hard normals.
  - **CHAD**: a parking lot, CCTV-style. Covers theft, pickpocketing, fights and running.
  - **MEVA**: about 100 consenting actors. Covers hugs and hand contact, plus 4 theft clips.
  - A few acted stock clips (Mixkit, Pexels).
- **Still short of the minimums:** stealing, stabbing, and above all fleeing-only. Fleeing-only is also the easiest to stage: one person running off, in many outfits.

## 3. Sources

| Source | License | Training OK? | Share the clips? | Covers | Angle and people | Verdict |
|---|---|---|---|---|---|---|
| **AIRTLab** ([repo](https://github.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos)) | README: "freely released for research and educational purposes". No LICENSE file. The paper is CC BY 4.0, but that covers the article only. | Research and education only | No, link only | 115 violent actions (stab 15, fight 46, club 36, punch 23, push 22, kick 21, slap 18, choke 13; one clip can hold several) and 60 non-violent (greet 33, hug 16, hand gestures 15, jump 10, high five 6, one friendly punch), each filmed by 2 cameras. No stealing or fleeing. | One room, two high corner cameras (cam2 is a fisheye), 1920×1080, 2–14 s. Non-professional actors with signed consent. Outfit contrast UNVERIFIED. | **Tonight** (`git clone`; files are 1.6–4.3 MB) |
| **CHAD** ([repo](https://github.com/TeCSAR-UNCC/CHAD)) | Repo license Apache-2.0; no separate data license (UNVERIFIED that it covers the data) | Probably | Link only (data is on Google Drive) | 412 videos. Theft, pick-pocketing, fighting, punching, kicking, pushing, chasing, running. No stabbing. Per-class counts UNKNOWN until downloaded. | 4 fixed parking-lot cameras, cam1 high and looking down; Full-HD. 13 actors. | **Tonight**, likely the best CCTV-style source |
| **MEVA** ([mevadata.org](https://mevadata.org), [license](https://mevadata.org/resources/MEVA-data-license.txt)) | CC BY 4.0 | Yes | Yes, with attribution and a modification note | Hug: 345 events in 135 clips. Hand contact: 1,902 events in 257 clips. Theft: 5 events in 4 clips. No stabbing, assault or fleeing. | Fixed CCTV, up to 1080p, 5-minute videos; people are often small. About 100 consenting actors. | **Tonight**, for hard normals and the theft clips |
| **Bus Violence** ([Zenodo](https://zenodo.org/records/7044203)) | CC attribution, non-commercial (version not stated) | Non-commercial research only | Link only | 700 violent (fight, kicking, stealing or tearing an object from someone) and 700 normal clips | Inside a moving bus, 0.6–1.9 s clips, low resolution. 10 actors. 449 MB zip. | Low priority. The non-commercial term clashes with an open model. |
| **UT-Interaction** ([page](http://cvrc.ece.utexas.edu/SDHA2010/Human_Interaction.html)) | None stated; citation requested | UNVERIFIED | Link only | Push, punch, kick, hug, handshake | 720×480, a parking lot and a lawn, people about 200 px tall | Secondary |
| **Mixkit** ([license](https://mixkit.co/license/#videoFree), [terms](https://mixkit.co/terms/)) | Stock Video Free License | No clause against training found; no bulk download | Link only | About 15 usable clips: thefts, one fleeing, arguments, hugs | Mostly cinematic eye-level; one black-and-white CCTV-style clip | Tonight, picked by hand. Check each clip's license, because "Restricted" items differ. |
| **Pexels** ([license](https://www.pexels.com/license/), [terms](https://www.pexels.com/terms-of-service/)) | Pexels License; the terms ban scraping "for machine learning purposes" | By hand only, and a team decision | Link only | Hugs, jogging, one theft. Its "fights" are martial arts. | Eye-level, cinematic | Normals only, after a team decision |
| Pixabay | Terms ban data mining for machine learning | No | — | — | — | **No** |
| Wikimedia Commons | Per file | — | — | Almost no staged crime footage; mostly real-incident news | — | **No** |
| CAVIAR | CC BY-SA | Yes | Yes (stays CC BY-SA) | 4 fights | 384×288 overhead, too small for outfits | Already used for the external check |

**Real people, not actors: excluded by our footage rule** (only public-dataset actors or consenting people), and the licenses don't fit either:
- **Real Life Violence Situations** (Kaggle; "Data files © Original Authors"; needs a sign-in)
- **RWF-2000** (videos "currently not available"; redistribution needs the lab's approval)
- **UCF-Crime** (real CCTV; no license stated)

## 4. Candidate clips

### AIRTLab (46 IDs; research and education only)

The per-clip labels are in `violent-action-classes.csv` and `nonviolent-action-classes.csv` in the repo. Each ID has a cam1 and a cam2 file of the same action, so the two are near-duplicates. URL template, confirmed on `violent/cam1/1.mp4`:
`https://raw.githubusercontent.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos/master/violence-detection-dataset/{violent|non-violent}/{cam1|cam2}/{N}.mp4`

- **Stabbing (violent), 12 IDs:**
  - stab only: 5, 51, 52, 61, 72, 108, 114
  - mixed: 49 (stab, fight, slap); 56 (choke, stab); 62 (stab, push); 82 (punch, stab, fight); 110 (club, stab)
- **Assault (violent), 21 IDs:**
  - punch: 7, 46, 77, 85, 107, 109
  - kick: 48, 58, 65, 79, 99
  - push: 12
  - slap: 1, 2, 22, 39, 40, 41, 74, 102, 103
- **Hard normal (non-violent), 13 IDs:**
  - hug: 6, 28, 38, 44, 47, 49
  - hug and high five: 1
  - friendly punch: 14
  - high five: 11
  - handshake and greet: 57
  - jump: 16, 23, 35
- Left out: IDs with a gunshot (57, 60, 66 in the violent set), because gunshot isn't in our label set.

### MEVA (CC BY 4.0; public S3, no login)

Download one video with:
`aws s3 cp s3://mevadata-public-01/drops-123-r13/<date>/<hh>/<stem>.r13.avi . --no-sign-request`

The annotations are in the [Kitware repo](https://gitlab.kitware.com/meva/meva-data-repo), under `annotation/DIVA-phase-2/MEVA/`. Frame rate is about 30 fps (UNVERIFIED). Cut 5–15 s around each span.

| Stem | Frames | Notes |
|---|---|---|
| 2018-03-15.14-50-00.14-55-00.school.G421 | 6544–6684 and 7748–7880 | 2 thefts |
| 2018-03-05.13-15-01.13-20-01.bus.G331 | 6207–6334 | theft |
| 2018-03-15.14-55-00.15-00-00.bus.G331 | 3434–3582 | theft |
| 2018-03-15.15-10-00.15-15-00.bus.G331 | 6319–6444 | **ex085, our external-check clip: never train on it** |

Hugs, 11 clips, each from a different camera and date (frame spans are the annotation spans, some long):
- 2018-03-12.11-05-01.11-10-01.school.G423, frames 5405–5769
- 2018-03-13.17-30-01.17-35-01.bus.G505, frames 3864–4167
- 2018-03-15.15-45-00.15-50-00.school.G424, frames 4955–5156
- 2018-03-07.17-05-06.17-10-06.school.G339, frames 1174–1324
- 2018-03-11.17-10-01.17-15-01.school.G638, frames 6714–6859
- 2018-03-05.13-20-01.13-25-01.school.G328, frames 3701–3839
- 2018-03-11.17-10-00.17-15-00.school.G299, frames 8449–9007
- 2018-03-13.16-10-00.16-15-00.school.G421, frames 6626–7338
- 2018-03-13.16-10-02.16-15-02.hospital.G436, frames 1705–2210
- 2018-03-07.11-00-01.11-05-01.bus.G506, frames 3904–4629
- 2018-03-13.16-15-03.16-20-03.school.G336, frames 7165–7981

### Stock clips (link only; outfit visibility UNVERIFIED)

Page URLs: `https://mixkit.co/free-stock-video/<slug>/` and `https://www.pexels.com/video/<slug>/`.

- **Stealing, Mixkit:**
  - thief-steals-a-womans-purse-on-the-street-31359 (8 s)
  - a-robbery-in-the-coffee-shop-23252 (16 s)
  - balaclava-assailant-steals-computer-from-car-31363 (16 s)
  - thief-tries-unsuccessfully-to-steal-a-car-tire-31366 (9 s)
  - a-man-stealthily-stealing-artifacts-from-a-house-31377 (13 s)
  - thief-is-surprised-by-the-police-when-stealing-31376 (15 s)
  - two-thieves-recorded-on-a-security-camera-31372 (21 s, black-and-white, CCTV-style)
- **Stealing, Pexels:** thief-stealing-handbag-from-a-car-854221 (9 s)
- **Fleeing, Mixkit:** person-running-away-from-something-in-a-forest-34152 (12 s)
- **Hard normal, Mixkit arguments:** two-men-in-suits-arguing-4605 (8 s); couple-arguing-in-the-park-looking-upset-46513 (30 s)
- **Hard normal, Mixkit hugs:**
  - joyful-lovers-hugging-4643
  - emotional-hug-between-a-couple-42237
  - couple-hug-while-laughing-or-crying-46525
  - urban-couple-hug-at-night-outside-the-telephone-booth-100861
  - happy-mother-giving-a-high-five-and-hug-to-her-49467
  - sad-girl-comforted-by-her-best-friend-4735
- **Hard normal, Pexels hugs:**
  - young-people-greeting-and-hugging-5359620
  - a-man-and-a-woman-hugging-and-saying-hi-8688676
  - a-couple-hugging-on-the-sidewalk-8343772
  - women-hugging-each-other-8343777
  - women-hugging-each-other-5087558
  - man-hugging-a-woman-5734169
- **Normal, Pexels jogging:** a-man-running-in-the-park-7877154; a-man-running-in-the-park-7877144; person-running-at-the-park-4742529
- **Hard normal, Pexels sparring:** men-doing-sparring-6296447
- Skipped: portrait (vertical) Pexels clips, and the Pexels "kleptomaniac stealing" items, which are props and stills.

## 5. Gaps against the minimums

| Type | Minimum | What the public sources give | Gap |
|---|---|---|---|
| Stabbing | 30 | About 12–15 AIRTLab actions; the two camera views are near-duplicates, all in one room | **Short:** stage more |
| Assault | 30 | About 100 AIRTLab actions, plus CHAD and UT-Interaction | Count met. Variety is weak: one room, few actors. |
| Stealing | 30 | 4 MEVA + 7 Mixkit + 1 Pexels; CHAD counts unknown until downloaded | **Short** |
| Normal | 60 | Plenty (MEVA hugs and hand contact, AIRTLab, stock) | Met, after cutting long videos |
| Fleeing only | 30 | No clean source; CHAD "running"/"chasing" unverified; stock running is mostly jogging | **Shortest:** easiest to stage |
| 20–30 different attackers | — | MEVA about 100 actors (no attacks), CHAD 13, Bus Violence 10, AIRTLab unknown | **Not met anywhere** |

## 6. Team decisions needed

1. **AIRTLab is research and education only, with no redistribution.** It would give most of our stabbing and assault clips. Does that fit our open-data rule and a published model? If we use it, we link it and never re-host it.
2. **CHAD's data license** isn't stated apart from the repo's Apache-2.0. Use it as Apache-2.0, or ask the authors?
3. **Stock sites:** may we use hand-picked downloads despite the "no scraping for machine learning" clauses? Pexels also says identifiable people may not appear "in a bad light", so use Pexels for normals only.
4. **Real-incident datasets** stay out (our footage rule).

## 7. Next steps

- **Wali:** pick the sources (decisions above) and say which categories matter most for the next run.
- **Download on the Brev box, not a laptop.** Cut 5–15 s clips with the action in the middle, convert to 720p H.264 MP4, and keep one angle per file.
- **Done (Oct 18, slice D3):** the public clips are listed with their cut in `public_clips_candidates.csv` (115 camera files) and labeled in `labels_public.csv`. One command on the Brev box, from the repo root, rebuilds every clip (720p, 10 fps, H.264, no audio) from the source links; MEVA is cut straight from S3 without downloading the 5-minute video:
  ```bash
  python data/scripts/fetch_public_clips.py data/training/public_clips_candidates.csv --out video-data/training-clips/videos
  ```
  Status, exclusions and what's still unlabeled: [`SOURCES.md`](SOURCES.md#public-training-clips-slice-d3-oct-18).
- **Labels:** Mina's side can label the cut clips from frames in Wali's format, as we did for the 11 external clips (`labels_external_filled.csv`). Every source goes into [`SOURCES.md`](SOURCES.md) and [`../README.md`](../README.md).
- **Stage:** fleeing-only and stealing with new people and contrasting outfits. Our own staged clips remain the only way to reach 20–30 different attackers.
