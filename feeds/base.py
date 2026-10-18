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
One frame that won't decode is skipped (warning); a camera stops only after 30 unreadable frames in a row.

Pacing: speed=1 yields frames in real time, speed=2 twice as fast; speed=0 or pace=False never sleeps
(tests, batch runs). By default a slow consumer never loses frames; the feed just falls behind real time.

Optional keyword arguments:
    max_width=960        (default) shrink wider frames to this width, keeping the aspect ratio (INTER_AREA);
                         narrower frames are left alone. None = original size. 12 cameras x 8 buffered 1080p
                         frames is ~600 MB; at 960 wide it's about a quarter of that.
    publish_status=True  publish camera_status events to the bus (bus.client.publish), one per state change:
                         "online" with a camera's first frame, "offline" when its clip ends (or when the feed is
                         closed early), "offline" if its clip is missing, "degraded" if the clip is there but
                         can't be decoded. Mid-clip: "degraded" at an unreadable frame, back to "online" with the
                         next good one, "offline" after 30 unreadable frames in a row. ts is on the run clock; fps
                         is the sampling fps. Default False (publishes nothing).
    drop_late=True       when paced and the consumer is more than one sample interval behind real time, skip the
                         stale samples so the frames it gets are live (logs each camera's skip count once, when
                         the feed ends). Default False: every sample is delivered, late if need be.

cameras.json is checked when open_feeds is called: a missing "cameras" list, a camera without camera_id,
a duplicate camera_id or a non-numeric source.start_ts raises one ValueError that lists every problem.

Settings (environment variables):
    CLARITY_CLIP_ROOT   folder that relative source.uri paths start from, default the repo root
    CLARITY_RUN_ID      copied into camera_status events as run_id, when set
    CLARITY_BUS_URL     where camera_status events go (see bus/client.py)

Quick check from the repo root (prints one line per packet, no sleeping):
    python -m feeds.base data/sites/annex/cameras.json --fps 1 --speed 0
The standalone runner with camera status is `python -m feeds.replay`.
"""
from __future__ import annotations

import argparse
import heapq
import json
import logging
import math
import os
import time
import uuid
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from bus.client import publish

log = logging.getLogger("feeds")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NATIVE_FPS = 30.0  # used when a clip doesn't report its frame rate
DEFAULT_MAX_WIDTH = 960
MAX_BAD_FRAMES = 30  # unreadable frames in a row before a camera is given up on
EPS = 1e-6


@dataclass
class FramePacket:
    camera_id: str          # "cam_03"
    ts: float               # run-clock seconds
    frame_idx: int          # index of this frame in its source clip
    source_kind: str        # "replay" | "live"
    image: np.ndarray = field(repr=False, compare=False)  # H x W x 3, BGR, uint8 (OpenCV default)


@dataclass
class _Status:
    """Marker in the merged stream: a camera changes state at run-clock ts. Never yielded to callers."""
    camera_id: str
    ts: float
    status: str             # "online" | "offline" | "degraded"


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


# ---------- cameras.json ----------

def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _camera_problems(i: int, cam) -> list[str]:
    """What's wrong with one camera entry, as far as feeds cares (the full schema is contracts/validate.py's job)."""
    if not isinstance(cam, dict):
        return [f"cameras[{i}] is not an object"]
    cam_id = cam.get("camera_id")
    if not isinstance(cam_id, str) or not cam_id:
        return [f"cameras[{i}] has no camera_id"]
    source = cam.get("source")
    if source is None:
        return []  # not a replay camera; skipped with a warning later
    if not isinstance(source, dict):
        return [f"{cam_id}: source must be an object, got {source!r}"]
    problems = []
    start_ts = source.get("start_ts")
    if start_ts is not None and not _is_number(start_ts):
        problems.append(f"{cam_id}: source.start_ts must be a number of seconds, got {start_ts!r}")
    uri = source.get("uri")
    if uri is not None and not isinstance(uri, str):
        problems.append(f"{cam_id}: source.uri must be a path string, got {uri!r}")
    return problems


def load_cameras(cameras_json: str | Path) -> list[dict]:
    """The camera list of a cameras.json, checked up front so a bad file fails here, not mid-replay."""
    path = Path(cameras_json)
    with open(path, encoding="utf-8") as f:
        try:
            doc = json.load(f)
        except ValueError as e:
            raise ValueError(f"{path} is not valid JSON: {e}") from None
    cameras = doc.get("cameras") if isinstance(doc, dict) else None
    if not isinstance(cameras, list):
        raise ValueError(f'{path} has no "cameras" list at the top level (is it a cameras.json?)')
    problems = [p for i, cam in enumerate(cameras) for p in _camera_problems(i, cam)]
    ids = [cam.get("camera_id") for cam in cameras if isinstance(cam, dict)]
    dupes = sorted({c for c in ids if isinstance(c, str) and ids.count(c) > 1})
    if dupes:
        problems.append(f"duplicate camera_id: {', '.join(dupes)}")
    if problems:
        raise ValueError(f"{path} has {len(problems)} problem(s):\n  - " + "\n  - ".join(problems))
    return cameras


# ---------- one camera ----------

def _open_clip(cam: dict) -> tuple[cv2.VideoCapture | None, float, str | None]:
    """(capture, native fps, None) when the clip plays; otherwise (None, 0.0, status) with a warning, where
    status is "offline" (clip missing), "degraded" (clip there but unreadable) or None (not a replay source)."""
    cam_id, source = cam["camera_id"], cam.get("source") or {}
    if source.get("kind") != "replay":
        log.warning("%s: source kind %r is not supported yet (replay only); skipping", cam_id, source.get("kind"))
        return None, 0.0, None
    path = clip_root() / source.get("uri", "")
    if not path.is_file():
        log.warning("%s: clip not found at %s; skipping this camera", cam_id, path)
        return None, 0.0, "offline"
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        log.warning("%s: OpenCV can't open %s; skipping this camera", cam_id, path)
        return None, 0.0, "degraded"
    native = cap.get(cv2.CAP_PROP_FPS)
    if not (math.isfinite(native) and 1 <= native <= 1000):
        log.warning("%s: %s reports %r fps; assuming %s", cam_id, path, native, DEFAULT_NATIVE_FPS)
        native = DEFAULT_NATIVE_FPS
    return cap, native, None


def _shrink(image: np.ndarray, max_width: int | None) -> np.ndarray:
    h, w = image.shape[:2]
    if max_width is None or w <= max_width:
        return image
    return cv2.resize(image, (max_width, max(1, round(h * max_width / w))), interpolation=cv2.INTER_AREA)


def _mid_clip(next_idx: int, frame_count: float, native: float) -> bool:
    """True if a failed read at next_idx is a bad frame inside the clip, not its end. frame_count is the
    container's estimate, which can run a little long for variable-frame-rate phone clips, so a failure in the
    last second counts as the end; unknown (<= 0) means the end too."""
    return frame_count > 0 and next_idx < frame_count - max(1.0, native)


def _camera_frames(cam: dict, fps: float, clip: tuple, max_width: int | None) -> Iterator[FramePacket | _Status]:
    """One camera's frames sampled at fps, in ts order, with _Status markers: "degraded" at the first unreadable
    frame of a run, and one at the end for how the camera ended."""
    cap, native, failure = clip
    cam_id = cam["camera_id"]
    start_ts = (cam.get("source") or {}).get("start_ts")
    if start_ts is None:
        log.warning("%s: source.start_ts is missing; starting it at run-clock 0", cam_id)
        start_ts = 0.0
    if cap is None:
        if failure:
            yield _Status(cam_id, max(0.0, start_ts), failure)  # it should have come online here
        return
    # Sample instants sit on the run-clock grid (0, 1/fps, 2/fps, ...) so every camera is sampled
    # at the same moments; each takes the first frame at or after its instant.
    step, idx, sent, bad, gave_up = 1.0 / fps, -1, 0, 0, False
    next_ts = max(0.0, math.ceil(start_ts / step - EPS) * step)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    try:
        # Decode every frame in order (grab is cheap) and convert only the sampled ones;
        # seeking is no faster for phone clips and can land on the wrong frame.
        while True:
            grabbed = cap.grab()
            if not grabbed and not _mid_clip(idx + 1, frame_count, native):
                break  # end of the clip
            idx += 1
            ts = start_ts + idx / native
            image = None
            if grabbed:
                if ts < 0 or ts + EPS < next_ts:
                    bad = 0  # not a sample, but it decoded
                    continue
                ok, image = cap.retrieve()
                if not ok:
                    image = None
            if image is None:
                bad += 1
                if bad == 1:
                    log.warning("%s: couldn't decode frame %d; skipping it", cam_id, idx)
                    yield _Status(cam_id, round(max(0.0, ts), 3), "degraded")
                if bad >= MAX_BAD_FRAMES:
                    log.warning("%s: %d unreadable frames in a row (to frame %d); stopping this camera",
                                cam_id, bad, idx)
                    gave_up = True
                    break
                continue
            if bad:
                log.info("%s: frames readable again from frame %d", cam_id, idx)
            bad = 0
            next_ts = (math.floor(ts / step + EPS) + 1) * step
            sent += 1
            yield FramePacket(cam_id, round(ts, 3), idx, "replay", _shrink(image, max_width))
    finally:
        cap.release()
    ended = "offline"
    if sent == 0 and not gave_up:
        log.warning("%s: no frames (empty clip, or all before run-clock 0)", cam_id)
        ended = "degraded"
    yield _Status(cam_id, round(max(0.0, start_ts + (idx + 1) / native), 3), ended)


# ---------- camera_status ----------

def camera_status_event(event_id: str, camera_id: str, status: str, ts: float, fps: float | None) -> dict:
    """A camera_status event (contracts/schemas/camera_status.schema.json)."""
    event = {"type": "camera_status", "schema_version": "0.1", "event_id": event_id, "ts": round(max(0.0, ts), 3),
             "source": "feeds", "camera_id": camera_id, "status": status, "fps": fps, "source_kind": "replay"}
    if os.environ.get("CLARITY_RUN_ID"):
        event["run_id"] = os.environ["CLARITY_RUN_ID"]
    return event


class _StatusPublisher:
    """Publishes one camera_status per state change of each camera."""

    def __init__(self, fps: float):
        self.fps = fps
        # ids are cst_<cam>_<tag>_<n>: the tag differs per run, because the dashboard drops an event_id
        # it has already seen, so a rerun into the same bus run would otherwise show stale statuses.
        self.tag = uuid.uuid4().hex[:6]
        self.state: dict[str, str] = {}
        self.sent: dict[str, int] = {}
        self.clock = 0.0  # latest run-clock ts seen

    def set(self, camera_id: str, status: str, ts: float) -> None:
        self.clock = max(self.clock, ts)
        if self.state.get(camera_id) == status:
            return
        self.state[camera_id] = status
        n = self.sent[camera_id] = self.sent.get(camera_id, 0) + 1
        log.info("%s %s at ts %.3f", camera_id, status, ts)
        publish(camera_status_event(f"cst_{camera_id}_{self.tag}_{n}", camera_id, status, ts, self.fps))

    def stop(self) -> None:
        """The feed stopped early (consumer broke off, Ctrl+C): cameras still online go offline."""
        for camera_id, status in list(self.state.items()):
            if status == "online":
                self.set(camera_id, "offline", self.clock)


# ---------- all cameras ----------

def open_feeds(cameras_json: str, fps: float = 1.0, speed: float = 1.0, pace: bool = True, *,
               max_width: int | None = DEFAULT_MAX_WIDTH, publish_status: bool = False,
               drop_late: bool = False) -> Iterator[FramePacket]:
    """Yields frames from all cameras interleaved in ts order. Wali samples ~1 fps.
    Bad arguments or a bad cameras.json raise here, at the call, not at the first frame."""
    if not fps > 0:
        raise ValueError(f"fps must be > 0 (got {fps!r})")
    if not speed >= 0:
        raise ValueError(f"speed must be >= 0 (got {speed!r})")
    if max_width is not None and (isinstance(max_width, bool) or not isinstance(max_width, int) or max_width < 1):
        raise ValueError(f"max_width must be a whole number of pixels >= 1, or None (got {max_width!r})")
    cameras = load_cameras(cameras_json)
    return _interleave(cameras, fps, speed if pace else 0.0, max_width, publish_status, drop_late)


def _interleave(cameras: list[dict], fps: float, speed: float, max_width: int | None,
                publish_status: bool, drop_late: bool = False) -> Iterator[FramePacket]:
    status = _StatusPublisher(fps) if publish_status else None
    clips: list[tuple] = []
    streams: list[Iterator] = []
    anchor: tuple[float, float] | None = None  # (wall clock, ts) of the first paced item
    late_after = 1.0 / fps / speed if speed > 0 else math.inf  # one sample interval, in wall-clock seconds
    dropped: dict[str, int] = {}
    try:
        clips = [_open_clip(cam) for cam in cameras]
        if not any(cap is not None for cap, _, _ in clips):
            log.warning("no camera could be opened (%d in cameras.json); check source.uri and CLARITY_CLIP_ROOT (%s)",
                        len(cameras), clip_root())
        streams = [_camera_frames(cam, fps, clip, max_width) for cam, clip in zip(cameras, clips)]
        for item in heapq.merge(*streams, key=lambda p: (p.ts, p.camera_id)):
            is_status = isinstance(item, _Status)
            if is_status and status is None:
                continue  # status markers cost no time when nobody publishes them
            wait = 0.0
            if speed > 0:
                if anchor is None:
                    anchor = (time.monotonic(), item.ts)
                wait = anchor[0] + (item.ts - anchor[1]) / speed - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            if is_status:
                status.set(item.camera_id, item.status, item.ts)
                continue
            if status is not None:
                status.set(item.camera_id, "online", item.ts)
            if drop_late and -wait > late_after:
                dropped[item.camera_id] = dropped.get(item.camera_id, 0) + 1
                continue
            yield item
    finally:
        for camera_id, n in sorted(dropped.items()):
            log.warning("%s: skipped %d late frame(s) to stay live (the consumer fell more than one sample "
                        "behind real time)", camera_id, n)
        for s in streams:  # release every clip even if the consumer stops early
            s.close()
        for cap, _, _ in clips:  # covers streams that never started
            if cap is not None:
                cap.release()
        if status is not None:
            status.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the interleaved packets of a cameras.json.")
    parser.add_argument("cameras_json")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--speed", type=float, default=0.0, help="0 = no sleeping (default)")
    parser.add_argument("--max-width", type=int, default=DEFAULT_MAX_WIDTH, help="0 = full size")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = 0
    for pkt in open_feeds(args.cameras_json, fps=args.fps, speed=args.speed, max_width=args.max_width or None):
        h, w = pkt.image.shape[:2]
        print(f"{pkt.ts:9.3f}  {pkt.camera_id}  frame {pkt.frame_idx:6d}  {w}x{h}  {pkt.source_kind}")
        count += 1
    print(f"{count} packets")


if __name__ == "__main__":
    main()
