"""Build the publishable open-data package for test clip 1 (Hugging Face dataset, CC BY 4.0).

Writes data/raw/publish/clarity-clip1/ (gitignored): cam1.mp4 to cam4.mp4, plus copies of data/ground_truth/take3.json
and data/staged/clip_log_take3.csv, and the dataset card data/staged/DATASET_CARD_clip1.md as README.md. Upload that
folder's files as they are (steps in the card).

    python data/publish_clip1.py                 # build + check
    python data/publish_clip1.py --src <folder>  # read clip1_cam1.mp4 ... clip1_cam4.mp4 from another folder

The source is the converted clips the demo plays (default data/raw/staged/take3). Clip 1 needs no blur: both people
on screen agreed to be filmed, and the whole-frame review sheets (python data/review_sheets.py data/raw/staged/take3)
show no bystander who could be recognized. So each clip's video stream is copied as is, without re-encoding, into a
new file written without audio, metadata or chapters (iPhone clips can carry GPS, recording time and phone model
there). Each output is then checked three ways: publish_clip8.check() (exactly one video stream with the source's
codec, size, rate and frame count, and no tags beyond the ones ffmpeg writes itself), the same decoded frames as the
source (so the review sheets still hold), and no Apple metadata key or QuickTime location atom anywhere in the file.
Clip 8's script and package are not touched. Needs ffmpeg and ffprobe on PATH. Stdlib only.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from publish_clip8 import check  # same folder (run as python data/publish_clip1.py)

SRC = Path("data/raw/staged/take3")  # the converted clips the demo plays
OUT = Path("data/raw/publish/clarity-clip1")
EXTRA_FILES = {Path("data/ground_truth/take3.json"): "take3.json",
               Path("data/staged/clip_log_take3.csv"): "clip_log_take3.csv",
               Path("data/staged/DATASET_CARD_clip1.md"): "README.md"}  # the card is the dataset's README
NAMES = {f"clip1_cam{i}.mp4": f"cam{i}.mp4" for i in range(1, 5)}
MARK = "Clarity clip 1 publish package (data/publish_clip1.py)"  # comment tag on every output
CLEAN = ["-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", "-metadata", f"comment={MARK}",
         "-movflags", "+faststart"]
# Apple's metadata keys (location, make, model, creation date) and the QuickTime location atom
PHONE_MARKERS = (b"com.apple", b"\xa9xyz", b"ISO6709", b"iPhone")


def frame_hashes(path: Path) -> list[str]:
    """MD5 of every decoded video frame, in order (timestamps left out: only the pictures must match)."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "framemd5", "-"],
                         capture_output=True, text=True, check=True).stdout
    return [line.rsplit(",", 1)[1].strip() for line in out.splitlines() if line and not line.startswith("#")]


def verify(src: Path, dst: Path) -> tuple[str, str]:
    """(problem or '', summary): publish_clip8.check(), then the same frames as src, then no phone metadata."""
    problem, summary = check(src, dst)
    if problem:
        return problem, summary
    if frame_hashes(dst) != frame_hashes(src):
        return "its decoded frames differ from the source's", summary
    found = [m for m in PHONE_MARKERS if m in dst.read_bytes()]
    if found:
        return f"phone metadata left in the file: {found}", summary
    return "", f"{summary}, same frames as the source"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", type=Path, default=SRC, help=f"folder with clip1_cam1-4.mp4 (default {SRC})")
    args = parser.parse_args()
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("ERROR: ffmpeg/ffprobe not on PATH (Brev: sudo apt-get install -y ffmpeg)", file=sys.stderr)
        return 2
    if args.src.resolve().is_relative_to(OUT.resolve()):
        print(f"ERROR: refusing --src {args.src}: it is this script's output folder; use {SRC}", file=sys.stderr)
        return 2
    missing = [str(p) for p in [*(args.src / n for n in NAMES), *EXTRA_FILES] if not p.is_file()]
    if missing:
        print("ERROR: missing input files:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    for path in [*(OUT / n for n in [*NAMES.values(), *EXTRA_FILES.values()]), *OUT.glob("*.partial.mp4")]:
        path.unlink(missing_ok=True)  # so a failed run never leaves the last run's files looking current
    problems = []
    for name, out_name in NAMES.items():
        src, dst = args.src / name, OUT / out_name
        tmp = dst.with_name(dst.stem + ".partial.mp4")
        # nothing to blur: the video stream is copied as is, only the container is rewritten
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-c:v", "copy", *CLEAN,
                        str(tmp)], check=True)
        problem, summary = verify(src, tmp)
        if problem:
            tmp.unlink()
            problems.append(f"{out_name}: {problem}")
        else:
            tmp.replace(dst)
        print(f"{out_name} <- {src}: {'FAIL ' + problem if problem else 'ok'} ({summary})")
    for path, out_name in EXTRA_FILES.items():
        shutil.copyfile(path, OUT / out_name)
        print(f"{out_name} <- {path}")
    print(f"done: {OUT}")
    for line in problems:
        print(f"FAILED {line}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
