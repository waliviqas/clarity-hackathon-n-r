"""Write small synthetic clips + a cameras.json, so feeds (and perception plumbing) run before real clips exist.

Run from the repo root, into a folder outside the repo (clips never go in git):
    python -m feeds.fake_clips "<temp dir>" --cameras 3 --seconds 10
    python -m feeds.base "<temp dir>/cameras.json" --fps 1

Each frame shows its camera and frame number in text, plus the frame number as a row of black/white
squares that survives compression (read it back with read_frame_code). Camera k starts at run-clock
(k-1) * --offset s (default 10: +0/+10/+20 like the three staged takes). No people, nothing sensitive.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

CODE_BITS = 12          # frame numbers up to 4095
CELL = 20               # square size in pixels
WIDTH, HEIGHT = 320, 240


def draw_frame(camera_id: str, idx: int) -> np.ndarray:
    img = np.full((HEIGHT, WIDTH, 3), 90, np.uint8)
    for bit in range(CODE_BITS):
        img[0:CELL, bit * CELL:(bit + 1) * CELL] = 255 if idx >> bit & 1 else 0
    cv2.putText(img, camera_id, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    cv2.putText(img, f"frame {idx}", (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 2)
    return img


def read_frame_code(image: np.ndarray) -> int:
    centers = image[CELL // 2, CELL // 2::CELL][:CODE_BITS].mean(axis=1)
    return sum(1 << bit for bit, v in enumerate(centers) if v > 127)


def write_clip(path: Path, camera_id: str, seconds: float, fps: float) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise SystemExit(f"ERROR: OpenCV can't write {path}")
    for idx in range(round(seconds * fps)):
        writer.write(draw_frame(camera_id, idx))
    writer.release()


def cameras_json(clips: list[tuple[str, Path, float]]) -> dict:
    """A straight line of cameras, each linked to the next both ways."""
    ids = [cam for cam, _, _ in clips]
    cameras = []
    for i, (cam, path, start_ts) in enumerate(clips):
        neighbors = [{"camera_id": ids[j], "travel_time_s": 10, "direction": "east" if j > i else "west"}
                     for j in (i - 1, i + 1) if 0 <= j < len(ids)]
        cameras.append({"camera_id": cam, "name": f"Synthetic {cam}", "position": None,
                        "site_xy": {"x": round((i + 1) / (len(ids) + 1), 3), "y": 0.5}, "heading_deg": None,
                        "neighbors": neighbors,
                        "source": {"kind": "replay", "uri": str(path.resolve()), "start_ts": start_ts}})
    return {"schema_version": "0.1", "site_id": "synthetic", "site_name": "Synthetic test clips",
            "map": {"center": None, "zoom": 18, "site_image": None}, "cameras": cameras}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write synthetic test clips and a cameras.json.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--cameras", type=int, default=3, help="1-12")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--fps", type=float, default=30.0, help="native frame rate of the clips")
    parser.add_argument("--offset", type=float, default=10.0, help="start_ts step between cameras (s)")
    args = parser.parse_args()
    if not 1 <= args.cameras <= 12:
        raise SystemExit("ERROR --cameras: 1 to 12")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for k in range(1, args.cameras + 1):
        cam = f"cam_{k:02d}"
        path = args.out_dir / f"{cam}.mp4"
        write_clip(path, cam, args.seconds, args.fps)
        clips.append((cam, path, args.offset * (k - 1)))
        print(f"wrote {path}")
    out = args.out_dir / "cameras.json"
    out.write_text(json.dumps(cameras_json(clips), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
