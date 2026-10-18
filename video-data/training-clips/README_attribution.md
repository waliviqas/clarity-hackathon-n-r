## Training data attribution

Training clips in `data/training/staged_clips.csv` are staged (acted) footage. Videos and
frames live in `data/raw/` and are not committed. Paste this into `data/README.md`.

- **CAVIAR.** Clips: Fight_RunAway1, Fight_RunAway2, Fight_OneManDown, Fight_Chase, Walk1,
  Walk2, Meet_WalkTogether1, Browse1. Source: EC Funded CAVIAR project/IST 2001 37540,
  http://homepages.inf.ed.ac.uk/rbf/CAVIAR/. License: CC BY-SA. We modified the clips
  (frame extraction, labels).
- **MEVA.** Clips: ex085-theft, ex007-embrace-interaction, ex050-people-talking.
  "Multiview Extended Video with Activities" (MEVA) dataset by Kitware Inc.,
  https://mevadata.org. License: CC BY 4.0 (https://mevadata.org/resources/MEVA-data-license.txt).
  We modified the clips (frame extraction, labels).

**Note for Wali:** these are TRAINING clips. Our Annex staged clips stay TEST-only. Never
train on them, or the eval numbers mean nothing.
