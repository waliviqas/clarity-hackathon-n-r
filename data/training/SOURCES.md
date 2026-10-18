# Staged training clips: sources, licenses, shortfalls (2026-10-17)

Status: **0 of 20 verified.** 11 candidates with confirmed open licenses are in
`staged_clips.csv`, every visual field `Unknown`, status `unverified`. All 11 videos are
now local (copied from `data/videos/`), with frames at 2 fps and contact sheets in
`data/raw/training/frames/<clip_id>/` (gitignored). Labeling from the frames is next.

Findings from the frames (Oct 17 evening):
- The 3 MEVA example videos have the activity labels burned in (red boxes + text such as
  "Theft:1"). Don't train on them as-is. The overlay names the clean source file
  (ex085: `2018-03-15.15-10-00.15-15-00.bus.G331`, frame ~6383); see the S3 command below.
- ex085 is a bag lifted from the bench beside its seated owner, not a grab from a person,
  so `purse_snatch` is questionable.

## Next step (from repo root)

```bash
pip install pandas   # plus yt-dlp / awscli only when downloading
python data/scripts/fetch_staged_clips.py data/training/staged_clips.csv --fps 2 --local-dir data/videos
# review data/raw/training/frames/<clip_id>/contact_sheet_NN.jpg (and the f_*.jpg files), fill
# staged_clips.csv, split each TBD row into P1, P2... per person, set verification_status=verified
python data/scripts/check_staged_clips.py data/training/staged_clips.csv --urls
```

To find more MEVA purse/bag thefts (full-length, multi-camera clips):

```bash
git clone https://gitlab.kitware.com/meva/meva-data-repo.git
grep -rl "person_steals_object" meva-data-repo/annotation/DIVA-phase-2/MEVA | head -40
# same timestamp + different G### camera = same incident, count once
aws s3 cp --no-sign-request s3://mevadata-public-01/drops-123-r13/<date>/<hour>/<file>.r13.avi data/raw/training/
```

## Sources that qualify

| Source | License | Proof | Staged evidence | Gives us |
|---|---|---|---|---|
| CAVIAR (INRIA lobby) | CC BY-SA (version not stated) | https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/ | "acted out by the CAVIAR team members" | 4 fights, walk/browse/meet negatives; 1 camera, high wide-angle |
| MEVA KF1 | CC BY 4.0 | https://mevadata.org/resources/MEVA-data-license.txt | 100+ scripted actors (arXiv 2012.00914) | `person_steals_object`, embrace, talk, handshake; multi-camera CCTV. **No fight class.** |

CAVIAR is share-alike: adaptations of the clips must stay CC BY-SA. Fine for our
training set; flag it if anyone redistributes derived frames.

## Rejected or ambiguous (not counted)

- **Bus Violence** (zenodo.org/records/7044203): license field says CC BY 4.0, description says "non-commercial use". Has staged fights and theft-from-person on 3 bus cameras. Ask the authors or treat as NC.
- **CHAD** (github.com/TeCSAR-UNCC/CHAD): repo is Apache-2.0 but the README doesn't say it covers the videos. Has staged fighting, theft, pick-pocketing, 4 cameras. Ask authors.
- **AIRTLab, BEHAVE, PETS, VIRAT, MNNIT shoplifting:** research-only, no license, or not confirmed.
- **Pexels / Pixabay:** terms ban automated collection "for machine learning purposes" and showing identifiable people "in a bad light". Fails the ML check, and crime labels on actors hit the second clause.
- **Coverr, Videvo/Magnific:** explicitly ban AI training.
- **Mixkit:** Free License allows copy/modify/commercial and says nothing about AI; points to User Terms and an AUP we could not read. **License-pending**, not counted. If the team confirms the AUP allows it, these would fill purse_snatch (ground-level angle, not CCTV):
  - https://mixkit.co/free-stock-video/thief-steals-a-womans-purse-on-the-street-31359/ (Free License confirmed on page, 8 s, file https://assets.mixkit.co/videos/31359/31359-720.mp4)
  - https://mixkit.co/free-stock-video/woman-is-robbed-of-her-cell-phone-by-a-thief-31395/
  - https://mixkit.co/free-stock-video/balaclava-assailant-steals-computer-from-car-31363/
- **Wikimedia Commons, YouTube CC BY:** no staged or training-scenario clips found.

## Shortfall vs the 20-clip mix

| activity | target | candidates (unverified) | gap |
|---|---|---|---|
| fistfight | 6 | 4 (CAVIAR) | 2 |
| purse_snatch | 6 | 1 (MEVA ex085, must confirm it's a grab from a person) | 5 (MEVA grep may close it) |
| stabbing | 2-3 | 0 | none openly licensed; skipped per rule 3 |
| none | 5-6 | 6 | 0 |
| **total** | 20 | 11 | 9 |
