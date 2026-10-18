#!/usr/bin/env python3
"""QA for data/training/staged_clips.csv. Run from the repo root on Brev:

    python scripts/check_staged_clips.py data/training/staged_clips.csv [--urls]
    python data/scripts/check_staged_clips.py data/training/public_clips.csv --frames data/raw/training_public/frames

Checks: exact header, equal column counts, loads in pandas, activity labels in
the contract set, required fields non-empty, one clip_id -> one source, no
duplicate source URLs across clip_ids, verified rows have frames on disk,
optional HTTP check of every source_url / license_url, and that no video or
frame files are tracked or staged in git.
"""
import csv
import subprocess
import sys
import urllib.request
from pathlib import Path

import pandas as pd

COLS = ("clip_id,person_id,source_title,source_url,license,license_url,attribution,footage_type,activity,"
        "location_type,crime,crime_happens_on_cam,camera_count,timestamps,duration_s,verification_status,"
        "confidence,build,height,shirt,pants,shoes,glasses,headwear,hair,bag,weapon,changes_between_cams,"
        "person_of_interest_notes,local_path").split(",")
ACTIVITIES = {"fistfight", "purse_snatch", "stabbing", "none"}
FOOTAGE = ("staged CCTV", "training simulation", "dataset actors", "other")
STATUS = {"verified", "unverified"}
CONF = {"high", "med", "low", "Unknown"}
MEDIA = (".mp4", ".avi", ".mov", ".webm", ".mkv", ".mpg", ".ogv", ".jpg", ".jpeg", ".png")


def main(path: str, check_urls: bool, frames_root: str = "data/raw/training/frames") -> int:
    errs = []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if rows[0] != COLS:
        errs.append(f"header mismatch: {rows[0]}")
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != len(COLS):
            errs.append(f"line {i}: {len(r)} columns, expected {len(COLS)}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    bad = df[~df.activity.isin(ACTIVITIES)]
    errs += [f"{r.clip_id}/{r.person_id}: activity '{r.activity}' not in contract" for r in bad.itertuples()]
    bad = df[~df.footage_type.str.startswith(FOOTAGE)]
    errs += [f"{r.clip_id}: footage_type '{r.footage_type}'" for r in bad.itertuples()]
    errs += [f"{r.clip_id}: verification_status '{r.verification_status}'" for r in df[~df.verification_status.isin(STATUS)].itertuples()]
    errs += [f"{r.clip_id}: confidence '{r.confidence}'" for r in df[~df.confidence.isin(CONF)].itertuples()]
    for col in ("clip_id", "person_id", "source_url", "license", "license_url", "attribution", "activity", "local_path"):
        for r in df[df[col].str.strip() == ""].itertuples():
            errs.append(f"{r.clip_id}/{r.person_id}: empty {col}")
    for col in ("source_url", "license", "activity"):
        n = df.groupby("clip_id")[col].nunique()
        errs += [f"{cid}: rows disagree on {col}" for cid in n[n > 1].index]
    dup = df.drop_duplicates("clip_id").groupby("source_url").clip_id.apply(list)
    errs += [f"same source in several clips {v}" for v in dup if len(v) > 1]
    if (df.local_path.str.len() > 0).any() and not df.local_path.str.startswith("data/raw/").all():
        errs.append("local_path must point into data/raw/")
    for r in df[df.verification_status == "verified"].drop_duplicates("clip_id").itertuples():
        if not any((Path(frames_root) / r.clip_id).glob("f_*.jpg")):
            errs.append(f"{r.clip_id}: marked verified but no frames on disk")

    if check_urls:
        urls = sorted(set(df.source_url) | set(df.license_url))
        for u in urls:
            if not u.startswith("http"):
                continue
            try:
                req = urllib.request.Request(u, method="GET", headers={"User-Agent": "Mozilla/5.0 clarity-qa"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    if resp.status >= 400:
                        errs.append(f"URL {resp.status}: {u}")
            except Exception as e:
                errs.append(f"URL failed ({type(e).__name__}): {u}")

    # security: nothing heavy tracked or staged
    try:
        tracked = subprocess.run(["git", "ls-files", "--cached"], capture_output=True, text=True, check=True).stdout.split("\n")
        leaked = [p for p in tracked if p.startswith("data/raw/") or p.lower().endswith(MEDIA)]
        errs += [f"git tracks/stages media: {p}" for p in leaked]
    except Exception as e:
        errs.append(f"git check skipped: {e}")

    counts = df.drop_duplicates("clip_id").groupby(["activity", "verification_status"]).size()
    print(counts.to_string())
    print(f"\n{df.clip_id.nunique()} clips, {len(df)} person rows")
    for e in errs:
        print("ERROR", e)
    print("PASS" if not errs else f"FAIL ({len(errs)} issues)")
    return 1 if errs else 0


if __name__ == "__main__":
    frames = sys.argv[sys.argv.index("--frames") + 1] if "--frames" in sys.argv else "data/raw/training/frames"
    sys.exit(main(sys.argv[1], "--urls" in sys.argv, frames))
