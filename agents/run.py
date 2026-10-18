"""Run the camera agents on the run clock and publish their events to the bus.

Run from the repo root (bus running, started with the same CLARITY_CAMERAS):
    python -m agents.run --answers results/before.json      # stand-in: recorded spotter answers
    python -m agents.run --live --save-answers runs/answers_ft.json   # Wali's spotter on each camera clip
    python -m agents.run --answers before.json --speed 0 --no-publish --out x.jsonl  # offline check

Each camera's clip (cameras.json source.uri + source.start_ts) plays on the run clock from start_ts, like
feeds.replay. Its spotter answer becomes a detection when the clip has played (ts = start_ts + clip length);
camera agents then relay and answer relays (agents/network.py). --speed 2 runs twice as fast, 0 never waits.
--live starts each spotter call when its clip has played; calls run in parallel, so vLLM batches them.
--save-answers keeps those answers, so the same run can be replayed later with --answers.

Settings (environment variables):
    CLARITY_BUS_URL     where events go (bus/client.py)
    CLARITY_CAMERAS     cameras.json, default data/sites/annex/cameras.json (use the bus's file)
    CLARITY_CLIP_ROOT   folder that relative source.uri paths start from, default the repo root
    CLARITY_RUN_ID      copied into every event as run_id, when set
    SPOTTER_URL, SPOTTER_MODEL   read by Wali's src/spotter.py (--live)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from bus.client import publish

from .answers import load_answers, live_spotter, save_answers
from .network import Network

log = logging.getLogger("agents")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAMERAS = "data/sites/annex/cameras.json"


@dataclass
class Clip:
    camera_id: str
    path: Path
    window: tuple[float, float]  # run-clock start and end


class Clock:
    """Run-clock seconds -> wall time, scaled by speed (0 = never wait)."""

    def __init__(self, speed: float):
        self.speed = speed
        self.start = time.monotonic()

    def wait_until(self, t: float) -> None:
        if self.speed > 0:
            delay = self.start + t / self.speed - time.monotonic()
            if delay > 0:
                time.sleep(delay)


def clip_path(uri: str) -> Path:
    path = Path(uri)
    return path if path.is_absolute() else Path(os.environ.get("CLARITY_CLIP_ROOT") or REPO_ROOT) / path


def clip_seconds(path: Path) -> float | None:
    """Clip length from its frame count and frame rate; None if it can't be read."""
    try:
        import cv2
    except ImportError:
        return None
    video = cv2.VideoCapture(str(path))
    try:
        frames, fps = video.get(cv2.CAP_PROP_FRAME_COUNT), video.get(cv2.CAP_PROP_FPS)
    finally:
        video.release()
    return frames / fps if frames > 0 and fps > 0 else None


def load_clips(cameras: list[dict], fallback_s: float) -> list[Clip]:
    """Every replay camera's clip window on the run clock, in the order the clips finish."""
    clips = []
    for cam in cameras:
        source = cam.get("source") or {}
        start = source.get("start_ts")
        if not source.get("uri") or not isinstance(start, (int, float)):
            log.warning("%s: no source.uri / start_ts, skipped", cam["camera_id"])
            continue
        path = clip_path(source["uri"])
        length = clip_seconds(path)
        if length is None:
            log.warning("%s: can't read %s; assuming it is %.1f s long", cam["camera_id"], path, fallback_s)
            length = fallback_s
        clips.append(Clip(cam["camera_id"], path, (float(start), float(start) + length)))
    return sorted(clips, key=lambda c: (c.window[1], c.camera_id))


def start_live(clips: list[Clip], frames: int, clock: Clock) -> tuple[dict, str | None, ThreadPoolExecutor]:
    """One spotter call per clip, each started when its clip has played."""
    spot, model = live_spotter()
    pool = ThreadPoolExecutor(max_workers=max(1, len(clips)))

    def call(clip: Clip) -> dict:
        clock.wait_until(clip.window[1])
        for attempt in (1, 2):  # one retry: a timeout or a cut-off reply is often a one-off
            began = time.monotonic()
            try:
                answer = spot(str(clip.path), frames)
            except Exception as e:
                if attempt == 2:
                    raise
                log.warning("%s: spotter call failed (%s), trying once more", clip.camera_id, type(e).__name__)
                continue
            log.info("%s: spotter answered in %.1f s", clip.camera_id, time.monotonic() - began)
            return answer

    return {c.camera_id: pool.submit(call, c) for c in clips}, os.environ.get("SPOTTER_MODEL", model), pool


def run_timeline(clips: list[Clip], get_answer, net: Network, clock: Clock) -> None:
    """Answers in the order their clips finish, with relay deadlines in between, on the run clock.
    get_answer(clip) returns the spotter answer, or raises if the spotter failed on that clip."""
    i = 0
    while True:
        t_answer = clips[i].window[1] if i < len(clips) else math.inf
        deadline = net.next_deadline()
        t_expire = math.inf if deadline is None else deadline
        if math.isinf(t_answer) and math.isinf(t_expire):
            return
        if t_expire < t_answer:
            clock.wait_until(t_expire)
            net.expire(t_expire)
            continue
        clip, i = clips[i], i + 1
        clock.wait_until(t_answer)
        try:
            answer = get_answer(clip)
        except Exception as e:  # spotter down, timeout, cut-off reply: that camera can't tell this time
            log.warning("%s: no spotter answer: %s: %s", clip.camera_id, type(e).__name__, str(e)[:160])
            net.on_failure(clip.camera_id, clip.window, type(e).__name__)
            continue
        net.on_answer(clip.camera_id, answer, clip.window)


def describe(e: dict) -> str:
    """One console line per event."""
    if e["type"] == "detection":
        what = f"{e['camera_id']} {e['activity']} (spotter: {e.get('on_screen')}/{e.get('spotter_crime')})"
    elif e["type"] == "relay":
        what = f"{e['from_camera']} -> {e['to_camera']} {e['subject_id']} ({e['basis']}, {e['confidence']:.2f})"
    else:
        what = f"{e['camera_id']} {e['decision']} {e['confidence']:.2f} {e['subject_id']}"
    return f"{e['ts']:8.2f}  {e['type']:<13} {e['event_id']:<14} {what}"


def summary(events: list[dict]) -> list[str]:
    crimes = [f"{e['camera_id']} {e['activity']}" for e in events
              if e["type"] == "detection" and e["activity"] != "none"]
    verdicts = [f"{e['camera_id']} {e['decision']}" for e in events if e["type"] == "agent_verdict"]
    subjects = sorted({e["subject_id"] for e in events if e["type"] == "relay"})
    return [f"crimes seen: {', '.join(crimes) or 'none'}",
            f"subjects: {', '.join(subjects) or 'none'}",
            f"verdicts: {', '.join(verdicts) or 'none'}"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--answers", help="recorded spotter answers (Wali's results JSON, or --save-answers output)")
    src.add_argument("--live", action="store_true", help="call Wali's spotter on each camera's clip")
    p.add_argument("--cameras", default=os.environ.get("CLARITY_CAMERAS") or DEFAULT_CAMERAS)
    p.add_argument("--run", type=int, help="which recorded run per camera (0-based; default: first that didn't fail)")
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast; 0 = don't wait")
    p.add_argument("--frames", type=int, default=4, help="frames per spotter call (--live; Wali's default 4)")
    p.add_argument("--save-answers", help="--live: write the answers here for a later --answers replay")
    p.add_argument("--out", help="also write every event to this .jsonl file")
    p.add_argument("--no-publish", action="store_true", help="don't send events to the bus")
    p.add_argument("--follow-matches-only", action="store_true",
                   help="relay onward only after a match (default: also after an uncertain look at someone running)")
    p.add_argument("--clip-seconds", type=float, default=5.0, help="clip length to assume if a clip can't be read")
    p.add_argument("--tag", help="id tag (default: random), e.g. det_<tag>_1")
    p.add_argument("--run-id", default=os.environ.get("CLARITY_RUN_ID"), help="copied into every event")
    args = p.parse_args()
    if args.speed < 0:
        p.error("--speed must be 0 or more")
    if args.save_answers and not args.live:
        p.error("--save-answers only works with --live")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    cameras = json.loads(Path(args.cameras).read_text(encoding="utf-8"))["cameras"]
    clips = load_clips(cameras, args.clip_seconds)
    clock = Clock(args.speed)
    pool, recorded = None, {}  # recorded: live answers, for --save-answers
    if args.live:
        futures, model, pool = start_live(clips, args.frames, clock)

        def get_answer(clip: Clip) -> dict:
            recorded[clip.camera_id] = futures[clip.camera_id].result()
            return recorded[clip.camera_id]
    else:
        answers, model = load_answers(args.answers, cameras, args.run)
        missing = [c.camera_id for c in clips if c.camera_id not in answers]
        if missing:
            log.warning("no recorded answer for %s; those cameras stay silent", ", ".join(missing))
        clips = [c for c in clips if c.camera_id in answers]
        get_answer = lambda clip: answers[clip.camera_id]  # noqa: E731

    events: list[dict] = []
    out = open(args.out, "w", encoding="utf-8") if args.out else None

    def emit(event: dict) -> None:
        events.append(event)
        if not args.no_publish:
            publish(event)
        if out:
            out.write(json.dumps(event) + "\n")
            out.flush()
        print(describe(event), flush=True)

    schedule = {c.camera_id: [c.window] for c in clips}
    extra = {"spotter_model": model, "spotter_mode": "live" if args.live else "recorded"}
    net = Network(cameras, emit, tag=args.tag, run_id=args.run_id, schedule=schedule, detection_extra=extra,
                  follow_uncertain=not args.follow_matches_only)
    log.info("agents up: %d cameras, %d clips, spotter %s (%s), ids det_%s_N", len(cameras), len(clips),
             model, extra["spotter_mode"], net.tag)
    try:
        run_timeline(clips, get_answer, net, clock)
    finally:
        if pool:
            pool.shutdown(wait=False, cancel_futures=True)
        if out:
            out.close()
    if args.live and args.save_answers:
        save_answers(args.save_answers, recorded, model)
        log.info("saved %d answers to %s", len(recorded), args.save_answers)
    for line in summary(events):
        print(line)


if __name__ == "__main__":
    main()
