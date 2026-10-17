"""Camera feeds: replay the staged clips as if they were live cameras (contract: "Frame (Mina -> Wali)").

    from feeds.base import open_feeds, FrameBuffer, FramePacket

    buf = FrameBuffer(n=8)
    for pkt in open_feeds("data/sites/annex/cameras.json", fps=1.0, speed=1.0):
        buf.push(pkt)
        frames = buf.last_n(pkt.camera_id, 4)   # oldest first, newest = pkt

Frames from every replay camera come interleaved in ts order (ties: camera_id). A camera's ts is its
source.start_ts plus the frame's time in the clip, so the three takes overlap on one run clock. Every camera
is sampled on the same run-clock grid (0, 1/fps, 2/fps, ...), taking the first frame at or after each instant.
frame_idx is the frame's index in its source clip (0-based), so a packet can be traced to its clip.
Frames with ts < 0 are skipped. A missing or unreadable clip logs a warning and that camera is left out.

Pacing: speed=1 yields frames in real time, speed=2 twice as fast; speed=0 or pace=False never sleeps
(tests, batch runs). A slow consumer never loses frames; the feed just falls behind real time.

Settings (environment variables):
    CLARITY_CLIP_ROOT   folder that relative source.uri paths start from, default the repo root

Quick check from the repo root (prints one line per packet, no sleeping):
    python -m feeds.base data/sites/annex/cameras.json --fps 1 --speed 0
"""
from __future__ import annotations

import argparse
import heapq
import json
import logging
import math
import os
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("feeds")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NATIVE_FPS = 30.0  # used when a clip doesn't report its frame rate
EPS = 1e-6


@dataclass
class FramePacket:
    camera_id: str          # "cam_03"
    ts: float               # run-clock seconds
    frame_idx: int          # index of this frame in its source clip
    source_kind: str        # "replay" | "live"
    image: np.ndarray = field(repr=False, compare=False)  # H x W x 3, BGR, uint8 (OpenCV default)


class FrameBuffer:
    """Keeps the last N frames per camera, because the VLM needs motion (several frames)."""

    def __init__(self, n: int = 8):
        self.n = n
        self._frames: dict[str, deque[FramePacket]] = {}

    def push(self, pkt: FramePacket) -> None:
        self._frames.setdefault(pkt.camera_id, deque(maxlen=self.n)).append(pkt)

    def last_n(self, camera_id: str, n: int) -> list[FramePacket]:
        """Up to n most recent frames of one camera, oldest first; [] for an unknown camera."""
        if n <= 0:
            return []
        return list(self._frames.get(camera_id, ()))[-n:]


def clip_root() -> Path:
    return Path(os.environ.get("CLARITY_CLIP_ROOT") or REPO_ROOT)


def _open_clip(cam: dict) -> tuple[cv2.VideoCapture, float] | None:
    """Open one camera's clip; None (with a warning) if it can't be played."""
    cam_id, source = cam.get("camera_id"), cam.get("source") or {}
    if source.get("kind") != "replay":
        log.warning("%s: source kind %r is not supported yet (replay only); skipping", cam_id, source.get("kind"))
        return None
    path = clip_root() / source.get("uri", "")
    if not path.is_file():
        log.warning("%s: clip not found at %s; skipping this camera", cam_id, path)
        return None
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        log.warning("%s: OpenCV can't open %s; skipping this camera", cam_id, path)
        return None
    native = cap.get(cv2.CAP_PROP_FPS)
    if not (math.isfinite(native) and 1 <= native <= 1000):
        log.warning("%s: %s reports %r fps; assuming %s", cam_id, path, native, DEFAULT_NATIVE_FPS)
        native = DEFAULT_NATIVE_FPS
    return cap, native


def _camera_frames(cam: dict, fps: float) -> Iterator[FramePacket]:
    """One camera's frames sampled at fps, in ts order."""
    opened = _open_clip(cam)
    if opened is None:
        return
    cap, native = opened
    cam_id = cam["camera_id"]
    start_ts = cam["source"].get("start_ts")
    if start_ts is None:
        log.warning("%s: source.start_ts is missing; starting it at run-clock 0", cam_id)
        start_ts = 0.0
    # Sample instants sit on the run-clock grid (0, 1/fps, 2/fps, ...) so every camera is sampled
    # at the same moments; each takes the first frame at or after its instant.
    step, idx, sent = 1.0 / fps, -1, 0
    next_ts = max(0.0, math.ceil(start_ts / step - EPS) * step)
    try:
        # Decode every frame in order (grab is cheap) and convert only the sampled ones;
        # seeking is no faster for phone clips and can land on the wrong frame.
        while cap.grab():
            idx += 1
            ts = start_ts + idx / native
            if ts < 0 or ts + EPS < next_ts:
                continue
            next_ts = (math.floor(ts / step + EPS) + 1) * step
            ok, image = cap.retrieve()
            if not ok or image is None:
                log.warning("%s: couldn't decode frame %d; stopping this camera", cam_id, idx)
                break
            sent += 1
            yield FramePacket(cam_id, round(ts, 3), idx, "replay", image)
    finally:
        cap.release()
    if sent == 0:
        log.warning("%s: no frames (empty clip, or all before run-clock 0)", cam_id)


def load_cameras(cameras_json: str | Path) -> list[dict]:
    with open(cameras_json, encoding="utf-8") as f:
        return json.load(f)["cameras"]


def open_feeds(cameras_json: str, fps: float = 1.0, speed: float = 1.0, pace: bool = True) -> Iterator[FramePacket]:
    """Yields frames from all cameras interleaved in ts order. Wali samples ~1 fps.
    Bad arguments or an unreadable cameras.json raise here, at the call, not at the first frame."""
    if not fps > 0:
        raise ValueError(f"fps must be > 0 (got {fps!r})")
    if not speed >= 0:
        raise ValueError(f"speed must be >= 0 (got {speed!r})")
    return _interleave(load_cameras(cameras_json), fps, speed if pace else 0.0)


def _interleave(cameras: list[dict], fps: float, speed: float) -> Iterator[FramePacket]:
    streams = [_camera_frames(cam, fps) for cam in cameras]
    anchor: tuple[float, float] | None = None  # (wall clock, ts) of the first packet
    try:
        for pkt in heapq.merge(*streams, key=lambda p: (p.ts, p.camera_id)):
            if speed > 0:
                if anchor is None:
                    anchor = (time.monotonic(), pkt.ts)
                wait = anchor[0] + (pkt.ts - anchor[1]) / speed - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            yield pkt
    finally:
        for s in streams:  # release every clip even if the consumer stops early
            s.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the interleaved packets of a cameras.json.")
    parser.add_argument("cameras_json")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--speed", type=float, default=0.0, help="0 = no sleeping (default)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = 0
    for pkt in open_feeds(args.cameras_json, fps=args.fps, speed=args.speed):
        h, w = pkt.image.shape[:2]
        print(f"{pkt.ts:9.3f}  {pkt.camera_id}  frame {pkt.frame_idx:6d}  {w}x{h}  {pkt.source_kind}")
        count += 1
    print(f"{count} packets")


if __name__ == "__main__":
    main()
