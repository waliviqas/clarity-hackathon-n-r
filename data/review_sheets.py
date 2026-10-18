"""Full-frame review sheets for staged clips, for a bystander check before a clip is shown or published: whole frames,
2 per second, 4 per row, each with its frame index and time (the same sheets as publish_clip8.py --sheets).

    python data/review_sheets.py data/raw/staged/take3
    python data/review_sheets.py data/raw/staged/take3 --out data/raw/review/take3 --fps 2

Writes <clip>_full_frames.png for every .mp4 in the folder to --out (default data/raw/review/<folder name>;
data/raw/ is gitignored, so sheets never land in git). Needs ffmpeg and ffprobe on PATH. Stdlib only.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from publish_clip8 import full_sheet  # same folder (run as python data/review_sheets.py)

REVIEW_ROOT = Path("data/raw/review")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clips", type=Path, help="folder with the clips (.mp4), e.g. data/raw/staged/take3")
    parser.add_argument("--out", type=Path, help=f"where the sheets go (default {REVIEW_ROOT}/<folder name>)")
    parser.add_argument("--fps", type=float, default=2.0, help="frames per second on each sheet (default 2)")
    args = parser.parse_args()
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("ERROR: ffmpeg/ffprobe not on PATH (Brev: sudo apt-get install -y ffmpeg)", file=sys.stderr)
        return 2
    if not args.fps > 0:
        parser.error("--fps must be greater than 0")
    clips = sorted(args.clips.glob("*.mp4"))
    if not clips:
        print(f"ERROR: no .mp4 clips in {args.clips}", file=sys.stderr)
        return 2
    out = args.out or REVIEW_ROOT / args.clips.name
    for clip in clips:
        png = out / f"{clip.stem}_full_frames.png"
        png.unlink(missing_ok=True)  # a failed run never leaves the last run's sheet looking current
        full_sheet(clip, args.fps, png)
        print(f"review sheet: {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
