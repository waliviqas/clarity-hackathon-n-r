"""Replay a recorded run into the bus, at the pace it originally happened (demo insurance).

Run from the repo root (bus running):
    python -m bus.replay runs/run_demo1/events.jsonl --speed 2

Events are re-published in file order, spaced by their original ts gaps divided by --speed.
Start the bus with a NEW CLARITY_RUN_ID for the replay, so the copy doesn't mix with the original
log and the dashboard doesn't see every event_id twice.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from bus.client import publish


def read_events(path: Path) -> list[dict]:
    events = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if isinstance(event, dict):
            events.append(event)
        else:
            print(f"skipping unreadable line {i}")
    return events


def ts_of(event: dict, default: float | None) -> float | None:
    try:
        ts = float(event["ts"])
    except (KeyError, TypeError, ValueError):
        return default
    return ts if math.isfinite(ts) else default


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("log", help="a recorded runs/<run_id>/events.jsonl")
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast as it happened")
    p.add_argument("--max-gap", type=float, default=10.0,
                   help="longest pause between two events, in original seconds (guards against odd ts jumps)")
    args = p.parse_args()
    if args.speed <= 0:
        p.error("--speed must be greater than 0")
    if args.max_gap < 0:
        p.error("--max-gap must be 0 or more")

    path = Path(args.log)
    if not path.is_file():
        p.error(f"no such file: {path}")
    events = read_events(path)
    if not events:
        print("no events to replay")
        return
    usable = [ts for ts in (ts_of(e, None) for e in events) if ts is not None]
    newest = usable[0] if usable else 0.0  # the clock starts at the first event that has a real ts

    # Replay clock: each gap is measured from the newest ts so far (a late event with an older ts goes
    # out right away without stretching later gaps), capped at --max-gap, then divided by --speed.
    schedule, clock = [], 0.0
    for e in events:
        ts = ts_of(e, newest)  # an event without a usable ts goes out right after the previous one
        clock += min(max(ts - newest, 0.0), args.max_gap)
        newest = max(newest, ts)
        schedule.append((clock / args.speed, ts, e))
    print(f"replaying {len(events)} events over ~{schedule[-1][0]:.0f}s (speed {args.speed}x)")

    start = time.monotonic()
    for at, ts, e in schedule:
        wait = at - (time.monotonic() - start)
        if wait > 0:
            time.sleep(wait)
        publish(e)
        print(f"{ts:9.1f}  {e.get('type', '?'):<14} {e.get('event_id', '?')}")


if __name__ == "__main__":
    main()
