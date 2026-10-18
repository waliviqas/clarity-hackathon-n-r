"""Run the camera agents on the run clock and publish their events to the bus.

Run from the repo root (bus running, started with the same CLARITY_CAMERAS):
    python -m agents.run --answers results/before.json      # stand-in: recorded spotter answers
    python -m agents.run --live --save-answers runs/answers_ft.json   # Wali's spotter on each camera clip
    python -m agents.run --answers before.json --speed 0 --no-publish --out x.jsonl  # offline check

Each camera's clip (cameras.json source.uri + source.start_ts) plays on the run clock from start_ts, like
feeds.replay. Its spotter answer becomes a detection when the clip has played (ts = start_ts + clip length);
camera agents then relay and answer relays (agents/network.py). --speed 2 runs twice as fast, 0 never waits.
--live first checks that the spotter serves SPOTTER_MODEL (GET {SPOTTER_URL}/models; exits 1 if not), then
starts each spotter call when its clip has played; calls run in parallel, so vLLM batches them. A call with
no answer after --spot-timeout seconds (default 90) counts as failed: that camera "can't tell" this time.
--save-answers keeps those answers, also when the run crashes, so the run can be replayed with --answers.

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
import re
import threading
import time
import urllib.request
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeout  # not the builtin TimeoutError on Python 3.10
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bus.client import publish

from .answers import load_answers, live_spotter, save_answers
from .network import Network

log = logging.getLogger("agents")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAMERAS = "data/sites/annex/cameras.json"
SPOT_TIMEOUT_S = 90.0  # Wali's client: 60 s timeout + 1 retry; past this the clip counts as failed
MODELS_TIMEOUT_S = 5.0
TAG = re.compile(r"[A-Za-z0-9_-]+")  # the contract's id characters (det_<tag>_1)


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


def check_spotter(base_url: str | None, model: str | None, timeout_s: float = MODELS_TIMEOUT_S) -> None:
    """Exit with one clear line unless the spotter at base_url serves `model` (GET {base_url}/models)."""
    if not base_url or not model:
        raise SystemExit("spotter check: no spotter URL or model name (set SPOTTER_URL and SPOTTER_MODEL)")
    url = base_url.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            served = [m.get("id") for m in json.loads(resp.read().decode("utf-8")).get("data", [])]
    except Exception as e:  # down, refused, not JSON: all mean the spotter can't answer
        raise SystemExit(f"spotter check: can't read {url} ({type(e).__name__}: {str(e)[:120]}); is its vLLM up?")
    if model not in served:
        raise SystemExit(f"spotter check: {url} serves {', '.join(map(str, served)) or 'no models'}, "
                         f"not SPOTTER_MODEL={model}")


def ask(spot, clip: Clip, frames: int):
    """One spotter answer for one clip. One retry: a timeout or a cut-off reply is often a one-off."""
    for attempt in (1, 2):
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


def start_live(clips: list[Clip], spot, frames: int, clock: Clock, limit_s: float) -> Callable[[Clip], dict]:
    """One spotter call per clip, each started when its clip has played (in parallel, so vLLM batches them).
    Returns get_answer(clip): the answer, or TimeoutError once that call has run limit_s seconds. Daemon
    threads, so a hung call can't keep the process alive after the run."""
    calls: dict[str, tuple[Future, dict]] = {}

    def call(clip: Clip, future: Future, started: dict) -> None:
        clock.wait_until(clip.window[1])
        started["at"] = time.monotonic()
        try:
            future.set_result(ask(spot, clip, frames))
        except Exception as e:  # handed to get_answer, which logs it
            future.set_exception(e)

    for clip in clips:
        future, started = Future(), {}
        threading.Thread(target=call, args=(clip, future, started), daemon=True,
                         name=f"spotter-{clip.camera_id}").start()
        calls[clip.camera_id] = (future, started)

    def get_answer(clip: Clip) -> dict:
        future, started = calls[clip.camera_id]
        left = started.get("at", time.monotonic()) + limit_s - time.monotonic()
        try:
            return future.result(timeout=max(0.0, left))
        except FuturesTimeout:
            raise TimeoutError(f"no answer within {limit_s:g} s") from None

    return get_answer


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
            if not isinstance(answer, dict):
                raise TypeError(f"answer is {type(answer).__name__}, not a JSON object")
        except Exception as e:  # spotter down, timeout, cut-off or malformed reply: that camera can't tell
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


def id_tag(value: str) -> str:
    if not TAG.fullmatch(value):
        raise argparse.ArgumentTypeError("letters, digits, '_' and '-' only (it goes into every event id)")
    return value


def save_backup(path: str, recorded: dict, model: str | None) -> None:
    try:
        save_answers(path, recorded, model)
        log.info("saved %d answers to %s", len(recorded), path)
    except OSError as e:
        log.error("couldn't save the answers to %s: %s", path, e)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--answers", help="recorded real spotter output (Wali's results JSON, or --save-answers "
                                       "output); never answers built from labels")
    src.add_argument("--live", action="store_true", help="call Wali's spotter on each camera's clip")
    p.add_argument("--cameras", default=os.environ.get("CLARITY_CAMERAS") or DEFAULT_CAMERAS)
    p.add_argument("--run", type=int, help="which recorded run per camera (0-based; default: first that didn't fail)")
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast; 0 = don't wait")
    p.add_argument("--frames", type=int, default=4, help="frames per spotter call (--live; Wali's default 4)")
    p.add_argument("--spot-timeout", type=float, default=SPOT_TIMEOUT_S,
                   help="--live: seconds one clip's spotter call may take before that camera can't tell")
    p.add_argument("--save-answers", help="--live: write the answers here for a later --answers replay")
    p.add_argument("--out", help="also write every event to this .jsonl file")
    p.add_argument("--no-publish", action="store_true", help="don't send events to the bus")
    p.add_argument("--relay-uncertain", action="store_true",
                   help="also relay onward after an uncertain look at someone running (basis: possible), so weak "
                        "sightings can add up (default: relay only after a match, as the contract says)")
    p.add_argument("--follow-matches-only", action="store_true", help=argparse.SUPPRESS)  # now the default
    p.add_argument("--clip-seconds", type=float, default=5.0, help="clip length to assume if a clip can't be read")
    p.add_argument("--tag", type=id_tag, help="id tag (default: random), e.g. det_<tag>_1")
    p.add_argument("--run-id", default=os.environ.get("CLARITY_RUN_ID"), help="copied into every event")
    args = p.parse_args()
    if args.speed < 0:
        p.error("--speed must be 0 or more")
    if args.spot_timeout <= 0:
        p.error("--spot-timeout must be more than 0")
    if args.save_answers and not args.live:
        p.error("--save-answers only works with --live")
    if args.relay_uncertain and args.follow_matches_only:
        p.error("--relay-uncertain and --follow-matches-only contradict each other")
    return args


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    cameras = json.loads(Path(args.cameras).read_text(encoding="utf-8"))["cameras"]
    clips = load_clips(cameras, args.clip_seconds)
    recorded: dict = {}  # live answers, for --save-answers
    if args.live:
        spot, model, url = live_spotter()
        check_spotter(url, model)
        clock = Clock(args.speed)
        get_live = start_live(clips, spot, args.frames, clock, args.spot_timeout)

        def get_answer(clip: Clip) -> dict:
            recorded[clip.camera_id] = get_live(clip)
            return recorded[clip.camera_id]
    else:
        answers, model = load_answers(args.answers, cameras, args.run)
        missing = [c.camera_id for c in clips if c.camera_id not in answers]
        if missing:
            log.warning("no recorded answer for %s; those cameras stay silent", ", ".join(missing))
        clips = [c for c in clips if c.camera_id in answers]
        clock = Clock(args.speed)
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
                  follow_uncertain=args.relay_uncertain)
    log.info("agents up: %d cameras, %d clips, spotter %s (%s), ids det_%s_N, relay after %s", len(cameras),
             len(clips), model, extra["spotter_mode"], net.tag,
             "a match or an uncertain runner" if args.relay_uncertain else "a match only")
    try:
        run_timeline(clips, get_answer, net, clock)
    finally:  # a crashed or interrupted take still leaves its events file and its answers backup
        if out:
            out.close()
        if args.live and args.save_answers:
            save_backup(args.save_answers, recorded, model)
    for line in summary(events):
        print(line)


if __name__ == "__main__":
    main()
