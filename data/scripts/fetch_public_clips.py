#!/usr/bin/env python3
"""Rebuild the public training clips (AIRTLab, Mixkit, MEVA) from their source URLs.

One command on the Brev box, from the repo root (needs ffmpeg + network, no login):

    python data/scripts/fetch_public_clips.py data/training/public_clips_candidates.csv --out video-data/training-clips/videos

Reads a candidates CSV (clip_id, source_url, download_url, license, license_url, start_s, end_s;
one row per camera file). For each row it:
  1. refuses to run unless the source cache and --out folder are gitignored,
  2. gets the source: .mp4 files are downloaded once into data/raw/training_public/src/;
     .avi files (MEVA's 5-minute S3 videos) are cut straight from the URL with ffmpeg -ss,
     so the whole file is never downloaded (falls back to a full download if that fails),
  3. cuts start_s..end_s (blank = the whole clip) and writes <out>/<clip_id>.mp4 in the
     encode of data/convert_clips.py: 720p, constant 10 fps, H.264 8-bit, no audio,
  4. with --frames, also writes 2 fps frames + contact sheets of the cut clip for labeling into
     data/raw/training_public/frames/<clip_id>/ (same layout as fetch_staged_clips.py) and
     appends a row to data/training/public_verification_log.csv.

Clips already in --out are kept unless --force. Default --out is data/raw/training_public/clips
(local labeling copies). These sources may not be re-hosted (AIRTLab: research and education
only; Mixkit: link only), so the clips are rebuilt from the links, never committed or uploaded.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# data/ (convert_clips) and data/scripts/ (fetch_staged_clips), so it also runs under python -I
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
import convert_clips  # noqa: E402
import fetch_staged_clips as staged  # noqa: E402  (same folder)

RAW = Path("data/raw/training_public")
SRC = RAW / "src"
FRAMES = RAW / "frames"
LOG = Path("data/training/public_verification_log.csv")
FILTERS = "fps=10," + convert_clips.FILTERS  # the fps filter gives constant 10 fps on any ffmpeg version


def ensure_gitignored(*folders: Path) -> None:
    for folder in folders:
        probe = folder / "probe.mp4"
        if subprocess.run(["git", "check-ignore", "-q", str(probe)], capture_output=True).returncode != 0:
            sys.exit(f"ABORT: {folder} is not gitignored, so clips could be committed. Fix .gitignore first.")


def fetch_source(row: dict) -> Path:
    """Downloaded copy of a direct .mp4 source (cached in SRC)."""
    url = (row.get("download_url") or row["source_url"]).strip()
    out = SRC / f"{row['clip_id']}{Path(url.split('?')[0]).suffix.lower()}"
    if out.is_file() and out.stat().st_size > 0:
        return out
    SRC.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    if url.startswith("s3://"):
        subprocess.run(["aws", "s3", "cp", "--no-sign-request", url, str(tmp)], check=True)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "clarity-dataset-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    os.replace(tmp, out)
    return out


def cut(src: str, dst: Path, start: str, end: str) -> None:
    """ffmpeg cut + encode; writes a .partial.mp4 first so a stopped run leaves no half clip."""
    window = []
    if start.strip():
        window += ["-ss", start.strip()]
    if end.strip():
        window += ["-t", f"{float(end) - float(start or 0):.3f}"]
    tmp = dst.with_name(dst.stem + convert_clips.PARTIAL)
    # -dn -map_metadata -1: one video stream only, no timecode track or source metadata carried over
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *window, "-i", src,
           "-vf", FILTERS, "-dn", "-map_metadata", "-1", *convert_clips.ENCODE, str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError((r.stderr.strip().splitlines() or [f"ffmpeg exit {r.returncode}"])[-1])
    os.replace(tmp, dst)


def build(row: dict, out_dir: Path, force: bool) -> tuple[Path, str]:
    dst = out_dir / f"{row['clip_id']}.mp4"
    if dst.is_file() and not force:
        return dst, "already built"
    url = (row.get("download_url") or row["source_url"]).strip()
    start, end = row.get("start_s", ""), row.get("end_s", "")
    if url.lower().split("?")[0].endswith(".avi") and url.startswith("http"):
        try:
            cut(url, dst, start, end)  # MEVA: seek inside the remote file, no full download
            return dst, f"cut {start}-{end} s straight from the URL"
        except RuntimeError as e:
            print(f"  remote cut failed ({e}); downloading the whole file instead")
    cut(str(fetch_source(row)), dst, start, end)
    return dst, f"cut {start or 0}-{end or 'end'} s from a downloaded copy"


def main(candidates: str, out_dir: Path, force: bool, frames: bool, only: list[str]) -> int:
    ensure_gitignored(SRC, out_dir, FRAMES)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(candidates, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if not only or any(r["clip_id"].startswith(p) for p in only)]
    new_log = not LOG.exists()
    failed = 0
    with open(LOG, "a", newline="", encoding="utf-8") if frames else open(os.devnull, "w") as lf:
        w = csv.DictWriter(lf, fieldnames=staged.LOG_COLS)
        if frames and new_log:
            w.writeheader()
        for row in rows:
            cid = row["clip_id"]
            entry = {"clip_id": cid, "source_url": row["source_url"],
                     "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            try:
                path, how = build(row, out_dir, force)
                n = sheets = 0
                if frames:
                    n, sheets = staged.extract_frames(cid, path, 2.0, FRAMES)
                entry.update(status="downloaded_frames_ready" if frames else "clip_ready", local_path=path.as_posix(),
                             n_frames=n or "", duration_s=staged.probe_duration(path), note=how)
                print(f"[ok]   {cid}: {entry['duration_s']} s -> {path}" + (f" ({n} frames, {sheets} sheets)" if frames else ""))
            except Exception as e:  # keep going; a failed row stays out of training
                failed += 1
                entry.update(status="failed", note=f"{type(e).__name__}: {e}"[:300])
                print(f"[fail] {cid}: {entry['note']}")
            w.writerow(entry)
    print(f"done: {len(rows) - failed} clips in {out_dir}, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates_csv", help="data/training/public_clips_candidates.csv")
    ap.add_argument("--out", type=Path, default=RAW / "clips", help="where the cut clips go (default %(default)s)")
    ap.add_argument("--force", action="store_true", help="rebuild clips that already exist")
    ap.add_argument("--frames", action="store_true", help="also write 2 fps frames + contact sheets for labeling")
    ap.add_argument("--only", nargs="*", default=[], help="only clip_ids starting with these prefixes")
    a = ap.parse_args()
    sys.exit(main(a.candidates_csv, a.out, a.force, a.frames, a.only))
