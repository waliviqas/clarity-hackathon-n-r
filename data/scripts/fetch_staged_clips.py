#!/usr/bin/env python3
"""Download staged training clips and extract frames for manual verification.

Run on Brev (or any machine with ffmpeg + network), from the repo root:

    pip install yt-dlp
    python data/scripts/fetch_staged_clips.py data/training/staged_clips_candidates.csv --fps 2
    # clips already saved under their original file names (e.g. data/videos/Walk1.mpg):
    python data/scripts/fetch_staged_clips.py data/training/staged_clips.csv --fps 2 --local-dir data/videos

Reads a clips CSV (one row per clip_id; columns clip_id, source_url, optional
download_url). For each clip it:
  1. refuses to run unless data/raw/ is gitignored,
  2. puts the video at data/raw/training/<clip_id>.<ext>: keeps one already there;
     else copies <local-dir>/<file name from the URL> (the original stays put);
     else downloads (yt-dlp for pages, plain HTTP for direct file / S3 URLs;
     s3:// uses `aws s3 cp --no-sign-request`),
  3. extracts frames at --fps (default 1) into data/raw/training/frames/<clip_id>/f_%05d.jpg,
     where frame N is at (N-1)/fps seconds (at 2 fps: f_00001 = 0.0 s, f_00002 = 0.5 s,
     f_00021 = 10.0 s),
  4. tiles those same frames into contact_sheet_01.jpg, _02.jpg, ... in the same folder
     (6x5 = 30 frames per sheet, i.e. 15 s at 2 fps) until the clip ends; each tile is
     stamped with its time and frame file,
  5. appends a row to data/training/verification_log.csv with status
     downloaded_frames_ready / failed and the reason.

Contact sheets need a font: set CLARITY_SHEET_FONT to a .ttf if none of the usual
system fonts below exist (Windows ffmpeg builds without fontconfig crash without one).

It never fills in person attributes. A human (or Claude Code looking at the
frames) fills staged_clips.csv from what is actually visible, then flips
verification_status to `verified`.
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

RAW = Path("data/raw/training")
FRAMES = RAW / "frames"
LOG = Path("data/training/verification_log.csv")
LOG_COLS = ["clip_id", "source_url", "status", "local_path", "n_frames", "duration_s", "note", "checked_at_utc"]
FONTS = ("C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
SHEET = "6x5"  # columns x rows per contact sheet


def ensure_gitignored() -> None:
    probe = RAW / "probe.mp4"
    r = subprocess.run(["git", "check-ignore", "-q", str(probe)], capture_output=True)
    if r.returncode != 0:
        sys.exit("ABORT: data/raw/ is not gitignored. Add `data/raw/` to .gitignore first.")


def download(row: dict, local_dir: Path | None = None) -> tuple[Path, str]:
    """Returns (video path, how it got there)."""
    cid, url = row["clip_id"], (row.get("download_url") or row["source_url"]).strip()
    RAW.mkdir(parents=True, exist_ok=True)
    existing = sorted(RAW.glob(f"{cid}.*"))
    if existing:
        return existing[0], "already on disk"
    src = local_dir / Path(url.split("?")[0]).name if local_dir else None
    if src and src.is_file():
        out = RAW / f"{cid}{src.suffix.lower()}"
        shutil.copy2(src, out)
        return out, f"local copy from {src.as_posix()}"
    if url.startswith("s3://"):
        out = RAW / f"{cid}{Path(url).suffix or '.mp4'}"
        subprocess.run(["aws", "s3", "cp", "--no-sign-request", url, str(out)], check=True)
        return out, "downloaded"
    direct = Path(url.split("?")[0]).suffix.lower() in {".mp4", ".avi", ".mov", ".webm", ".mkv", ".ogv", ".mpg"}
    if direct:
        out = RAW / f"{cid}{Path(url.split('?')[0]).suffix.lower()}"
        req = urllib.request.Request(url, headers={"User-Agent": "clarity-dataset-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
            shutil.copyfileobj(r, f)
        return out, "downloaded"
    # Page URL (Pexels, Pixabay, Commons, YouTube CC): let yt-dlp resolve it.
    subprocess.run(
        ["yt-dlp", "-q", "--no-playlist", "-f", "mp4/best", "-o", str(RAW / f"{cid}.%(ext)s"), url],
        check=True,
    )
    return sorted(RAW.glob(f"{cid}.*"))[0], "downloaded"


def probe_duration(path: Path) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return f"{float(r.stdout.strip()):.1f}"
    except ValueError:
        return ""


def font_option() -> str:
    """drawtext font: CLARITY_SHEET_FONT, else a known system font, else fontconfig's default."""
    for font in (os.environ.get("CLARITY_SHEET_FONT"), *FONTS):
        if font and Path(font).is_file():
            # ':' separates drawtext options, so the drive letter's colon is escaped.
            return "fontfile='" + Path(font).as_posix().replace(":", "\\:") + "':"
    return ""


def extract_frames(cid: str, path: Path, fps: float, frames_root: Path = FRAMES) -> tuple[int, int]:
    """Writes frames + contact sheets for one clip; returns (n_frames, n_sheets)."""
    out = frames_root / cid
    out.mkdir(parents=True, exist_ok=True)
    for old in [*out.glob("f_*.jpg"), *out.glob("contact_sheet*.jpg")]:
        old.unlink()  # a rerun at another fps must not leave stale frames or sheets behind
    # Start the clock at 0 so frame N sits at (N-1)/fps, the same time stamped on its tile.
    # eof_action=pass keeps the clip's last partial interval (default drops up to ~0.7 s of the tail).
    sample = f"setpts=PTS-STARTPTS,fps={fps:g}:eof_action=pass"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-vf", sample, "-q:v", "3", str(out / "f_%05d.jpg")],
        check=True,
    )
    stamp = font_option() + "text='%{pts\\:hms}  f_%{eif\\:n+1\\:d\\:5}':x=5:y=5:fontsize=16:fontcolor=yellow:box=1:boxcolor=black"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-vf",
         f"{sample},scale=320:-1,drawtext={stamp},tile={SHEET}", "-q:v", "3", str(out / "contact_sheet_%02d.jpg")],
        check=True,
    )
    return len(list(out.glob("f_*.jpg"))), len(list(out.glob("contact_sheet_*.jpg")))


def main(candidates: str, fps: float = 1.0, local_dir: Path | None = None) -> None:
    ensure_gitignored()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new_log = not LOG.exists()
    with open(candidates, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen = set()
    with open(LOG, "a", newline="", encoding="utf-8") as lf:
        w = csv.DictWriter(lf, fieldnames=LOG_COLS)
        if new_log:
            w.writeheader()
        for row in rows:
            cid = row["clip_id"]
            if cid in seen:
                continue
            seen.add(cid)
            entry = {"clip_id": cid, "source_url": row["source_url"], "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            try:
                path, how = download(row, local_dir)
                n, sheets = extract_frames(cid, path, fps)
                entry.update(status="downloaded_frames_ready", local_path=path.as_posix(), n_frames=n, duration_s=probe_duration(path), note=how)
                print(f"[ok]   {cid}: {n} frames, {sheets} contact sheets -> {FRAMES / cid}")
            except Exception as e:  # keep going; failures stay unverified
                entry.update(status="failed", note=f"{type(e).__name__}: {e}"[:300])
                print(f"[fail] {cid}: {entry['note']}")
            w.writerow(entry)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips_csv", help="CSV with clip_id, source_url (and optional download_url)")
    ap.add_argument("--fps", type=float, default=1.0, help="frames per second to extract (default 1)")
    ap.add_argument("--local-dir", type=Path, help="folder holding clips under their original file names")
    a = ap.parse_args()
    main(a.clips_csv, a.fps, a.local_dir)
