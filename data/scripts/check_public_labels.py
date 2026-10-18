#!/usr/bin/env python3
"""QA for a labels file in Wali's format (data/training/labels_public.csv). From the repo root:

    python data/scripts/check_public_labels.py data/training/labels_public.csv [--clips data/raw/training_public/clips]

Checks: header byte-identical to labels_external_filled.csv, enums, split=train, normal rows have blank
description columns, crime rows have a description, video path = video-data/training-clips/videos/<clip>_<cam>.mp4,
no race / skin / face words in any text, and (with --clips) that every video was built locally.
Prints row counts per category against the spec minimums.
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

REF = Path("data/training/labels_external_filled.csv")
ENUMS = {"on_screen": {"crime", "fleeing", "none"}, "crime": {"stabbing", "assault", "stealing", "none"},
         "build": {"slim", "average", "heavy", "unknown"}, "height": {"short", "average", "tall", "unknown"},
         "glasses": {"yes", "no", "unknown"}}
DESC = ["build", "height", "shirt", "pants", "shoes", "glasses", "headwear", "hair", "bag", "weapon", "vehicle"]
BANNED = re.compile(r"\b(race|racial|ethnic\w*|skin\w*|complexion|caucasian|asian|african|hispanic|latin[oa]|arab\w*|"
                    r"face|faces|facial|beard\w*|mustache|moustache|tanned|pale|(black|white|brown|dark|light)[- ]skinned|"
                    r"(black|white|brown) (man|woman|person|guy|girl|boy|male|female))\b", re.I)
MINIMUMS = {"stabbing": 30, "assault": 30, "stealing": 30, "normal": 60, "fleeing only": 30}


def category(r: dict) -> str:
    if r["on_screen"] == "none":
        return "normal"
    return "fleeing only" if r["on_screen"] == "fleeing" else r["crime"]


def main(path: str, clips: str | None) -> int:
    errs = []
    head, ref = open(path, "rb").readline(), open(REF, "rb").readline()
    if head != ref:
        errs.append(f"header differs from {REF}: {head!r}")
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    seen = set()
    for i, r in enumerate(rows, start=2):
        key = (r["clip"], r["cam"])
        if key in seen:
            errs.append(f"line {i}: duplicate {key}")
        seen.add(key)
        if r["split"] != "train":
            errs.append(f"line {i}: split '{r['split']}'")
        for col, ok in ENUMS.items():
            if r[col] not in ok and not (r["on_screen"] == "none" and col in DESC and r[col] == ""):
                errs.append(f"line {i}: {col} '{r[col]}'")
        if r["on_screen"] == "none" and (r["crime"] != "none" or any(r[c] for c in DESC)):
            errs.append(f"line {i}: normal clip must have crime=none and blank description columns")
        if r["on_screen"] != "none" and not all(r[c] for c in DESC):
            errs.append(f"line {i}: crime/fleeing row has a blank description column")
        if not r["what_happened"].strip() or not r["check"].strip():
            errs.append(f"line {i}: empty what_happened or check")
        if r["video"] != f"video-data/training-clips/videos/{r['clip']}_{r['cam']}.mp4":
            errs.append(f"line {i}: video '{r['video']}'")
        for col, text in r.items():
            if BANNED.search(text or ""):
                errs.append(f"line {i}: banned word in {col}: '{BANNED.search(text).group(0)}'")
        if clips and not (Path(clips) / f"{r['clip']}_{r['cam']}.mp4").is_file():
            errs.append(f"line {i}: clip not built: {r['clip']}_{r['cam']}.mp4")

    files, clip_ids = Counter(category(r) for r in rows), {}
    for r in rows:
        clip_ids.setdefault(category(r), set()).add(r["clip"])
    print(f"{'category':14} {'files':>5} {'clips':>5} {'minimum':>7}")
    for cat, need in MINIMUMS.items():
        print(f"{cat:14} {files.get(cat, 0):5} {len(clip_ids.get(cat, ())):5} {need:7}")
    for e in errs:
        print("ERROR", e)
    print("PASS" if not errs else f"FAIL ({len(errs)} issues)")
    return 1 if errs else 0


if __name__ == "__main__":
    clips_dir = sys.argv[sys.argv.index("--clips") + 1] if "--clips" in sys.argv else None
    sys.exit(main(sys.argv[1], clips_dir))
