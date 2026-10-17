"""Run the camera feeds on their own: play a cameras.json's clips on the run clock and publish camera_status.

Run from the repo root (start the bus first if you want the dashboard to show which cameras are live):
    python -m feeds.replay --cameras data/sites/annex/cameras.json
    python -m feeds.replay --speed 10 --no-status          # cameras from $CLARITY_CAMERAS

Prints one line per second of run clock: the second, how many cameras sent frames in it, how many frames,
and which cameras. Stops at the end of the last clip, or on Ctrl+C (cameras still online are marked offline).
Frames are thrown away here; perception (Wali) reads them through feeds.base.open_feeds instead.

Settings (environment variables):
    CLARITY_CAMERAS     default for --cameras
    CLARITY_BUS_URL     where camera_status events go (see bus/client.py)
    CLARITY_RUN_ID      copied into camera_status events as run_id, when set
    CLARITY_CLIP_ROOT   folder that relative source.uri paths start from (see feeds/base.py)
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from collections import Counter

from feeds.base import open_feeds

MAX_EMPTY_LINES = 10  # a longer gap between clips prints as one line


def second_line(second: int, frames: Counter) -> str:
    cams = " ".join(sorted(frames))
    return f"t={second:6d}s  cameras {len(frames):2d}  frames {sum(frames.values()):3d}  {cams}"


def print_gap(first: int, last: int) -> None:
    """Seconds first..last had no frames."""
    if last - first + 1 > MAX_EMPTY_LINES:
        print(f"t={first:6d}s .. {last}s  no frames")
        return
    for second in range(first, last + 1):
        print(second_line(second, Counter()))


def play(feed) -> int:
    """Consume the feed, printing one line per run-clock second. Returns the number of frames played."""
    totals: Counter = Counter()
    this_second: Counter = Counter()
    second = None
    stopped = "end of clips"
    try:
        for pkt in feed:
            now = math.floor(pkt.ts)
            if second is not None and now > second:
                print(second_line(second, this_second))
                if now > second + 1:
                    print_gap(second + 1, now - 1)
                this_second = Counter()
            second = now
            this_second[pkt.camera_id] += 1
            totals[pkt.camera_id] += 1
    except KeyboardInterrupt:
        stopped = "Ctrl+C"
    finally:
        feed.close()  # releases the clips and marks cameras still online as offline
    if second is not None:
        print(second_line(second, this_second))
    per_camera = ", ".join(f"{cam} {n}" for cam, n in sorted(totals.items())) or "none"
    print(f"stopped ({stopped}): {sum(totals.values())} frames from {len(totals)} cameras ({per_camera})")
    return sum(totals.values())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cameras", default=os.environ.get("CLARITY_CAMERAS"),
                   help="cameras.json to play (default: $CLARITY_CAMERAS)")
    p.add_argument("--fps", type=float, default=1.0, help="frames per second sampled from each camera")
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice real time; 0 = as fast as possible")
    p.add_argument("--max-width", type=int, default=960, help="shrink wider frames to this width; 0 = full size")
    p.add_argument("--no-status", action="store_true", help="don't publish camera_status events to the bus")
    args = p.parse_args()
    if not args.cameras:
        p.error("no cameras.json: pass --cameras PATH or set CLARITY_CAMERAS")
    if not args.fps > 0:
        p.error("--fps must be greater than 0")
    if not args.speed >= 0:
        p.error("--speed must be 0 or more")
    if args.max_width < 0:
        p.error("--max-width must be 0 (full size) or more")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(line_buffering=True)  # one line per second, even when piped to a log file

    status = "off" if args.no_status else f"to {os.environ.get('CLARITY_BUS_URL', 'http://127.0.0.1:8080')}"
    pace = f"speed {args.speed:g}x" if args.speed else "no pacing"
    print(f"playing {args.cameras} at {args.fps:g} fps, {pace}, "
          f"max width {args.max_width or 'full'}, camera status {status}")
    try:
        feed = open_feeds(args.cameras, fps=args.fps, speed=args.speed, max_width=args.max_width or None,
                          publish_status=not args.no_status)
    except (OSError, ValueError) as e:  # missing or malformed cameras.json
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0 if play(feed) else 1  # 1 = nothing played (every clip missing or unreadable)


if __name__ == "__main__":
    sys.exit(main())
