"""Demo only: the scripted cam_14 pickup of Route 2's suspect, about 30 minutes after the crime.

Site: data/sites/annex_trio_lookout (the three-crime map annex_trio plus cam_14 "Hillsborough St sidewalk").
The three crimes come from the real camera agents on recorded model answers:
    python -m agents.run --answers data/answers/trio_system_v3_checker.json
After they finish, this script reads Route 2's subject from the bus (the subject whose crime relay leaves
--crime-camera, cam_05) and publishes three events with source "fake_scenario", so the dashboard labels them
as scripted:
  1. a detection at cam_14 (on_screen fleeing), --after seconds (default 1800) after the crime detection;
  2. a lookout relay cam_06 -> cam_14 (basis "lookout": a description match, no expected arrival, no
     direction) citing cam_06's last verdict and detection of the subject, where the trail went cold;
  3. cam_14's agent_verdict "match", citing the relay and the detection.
A real dispatcher (python -m dispatcher.run) on the same bus then updates Route 2's incident at cam_14.
cam_14 is placed on Hillsborough St for this story and the gap is set for it; its footage is clip 8's cam2
(notes in data/sites/annex_trio_lookout/cameras.json, runs/run_trio_lookout/RUN.md).

Run from the repo root (bus started with CLARITY_CAMERAS=data/sites/annex_trio_lookout/cameras.json, then a
dispatcher, then the camera agents):
    python -m bus.demo_trio_lookout
    python -m bus.demo_trio_lookout --out x.jsonl   # write the events instead of publishing (still reads the bus)

Settings: CLARITY_BUS_URL (bus/client.py), CLARITY_CAMERAS (default the site above), CLARITY_RUN_ID (copied
into every event as run_id, when set).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

from bus.client import _bus_url, fetch, publish  # _bus_url: the address publish() posts to

DEFAULT_CAMERAS = "data/sites/annex_trio_lookout/cameras.json"
SOURCE = "fake_scenario"
IN_VIEW_S = (1.25, 2.5)  # clip 8 cam2: the suspect is in view from 1.25 to 2.5 s (data/staged/clip_log_take1.csv)
RELAY_AFTER_S = 0.25  # the lookout relay follows cam_14's detection (it is what matched the description)
VERDICT_AFTER_S = 0.5  # ...and cam_14's agent answers it


def load_site(path: str) -> dict:
    try:
        site = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"can't read cameras file {path} ({e})") from None
    if not isinstance(site, dict) or not isinstance(site.get("cameras"), list):
        raise ValueError(f"{path} is not a site's cameras.json")
    return site


def check_bus_serves(site: dict, path: str) -> None:
    """The bus must serve this site (GET /cameras): the dispatcher and the dashboard read it from there."""
    url = f"{_bus_url()}/cameras"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            served = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # down, refused, HTTP error, not JSON
        raise ValueError(f"can't read the bus's cameras at {url} ({e}); start the bus with "
                         f"CLARITY_CAMERAS={path}") from None
    got = served.get("site_id") if isinstance(served, dict) else None
    if got != site.get("site_id"):
        raise ValueError(f"the bus at {_bus_url()} serves site {got!r}, not {site.get('site_id')!r}; restart it "
                         f"with CLARITY_CAMERAS={path}")


def route_subject(crime_cam: str, subject: str | None) -> tuple[str, dict]:
    """The subject whose crime relay leaves crime_cam, and that crime detection (from the bus)."""
    crimes = {d["event_id"]: d for d in fetch("detection") if d.get("camera_id") == crime_cam
              and d.get("activity") not in (None, "none")}
    found = {}
    for r in fetch("relay"):
        cited = [crimes[i] for i in r.get("evidence_event_ids", []) if i in crimes]
        if r.get("from_camera") == crime_cam and r.get("basis") == "crime" and cited:
            found[r["subject_id"]] = cited[0]
    if subject:
        if subject not in found:
            raise ValueError(f"subject {subject} has no crime relay from {crime_cam} on the bus at {_bus_url()}")
        return subject, found[subject]
    if len(found) != 1:
        raise ValueError(f"{len(found)} subjects with a crime at {crime_cam} on the bus at {_bus_url()} "
                         f"({', '.join(sorted(found)) or 'none: run the camera agents first'}); pass --subject")
    return next(iter(found.items()))


def last_sighting(subject: str, last: str) -> tuple[dict, dict | None, float]:
    """The subject's newest event at camera `last` (a verdict there, else a relay sent from there), the
    detection at `last` it cites (or None), and the ts of the subject's newest event anywhere."""
    mine = [e for kind in ("relay", "agent_verdict") for e in fetch(kind) if e.get("subject_id") == subject]
    trail = sorted(mine, key=lambda e: e["ts"])
    at_last = ([e for e in trail if e["type"] == "agent_verdict" and e["camera_id"] == last]
               or [e for e in trail if e["type"] == "relay" and e["from_camera"] == last])
    if not at_last:
        raise ValueError(f"subject {subject} was never at {last} (no verdict there, no relay from there)")
    cause, dets = at_last[-1], {d["event_id"]: d for d in fetch("detection")}
    seen = [dets[i] for i in cause.get("evidence_event_ids", []) if i in dets and dets[i].get("camera_id") == last]
    return cause, (seen[-1] if seen else None), trail[-1]["ts"]


def pickup_events(subject: str, crime: dict, cause: dict, seen: dict | None, last: str, cam: str, at: float,
                  appearance: str, run_id: str | None) -> list[dict]:
    """cam's detection at `at`, the lookout relay last -> cam, and cam's "match" verdict."""
    tag = f"lookout_{uuid.uuid4().hex[:6]}"  # fresh per run, so a rerun into the same bus is not a duplicate
    common = {"schema_version": "0.1", "source": SOURCE, **({"run_id": run_id} if run_id else {})}
    det_id, rel_id = f"det_{tag}_1", f"rel_{tag}_1"
    cold = f"trail cold {(at - (seen or cause)['ts']) / 60:.0f} min"
    activity = crime["activity"]
    look = (seen or {}).get("appearance") or cause.get("appearance")  # what `last` saw, relayed on
    return [
        {"type": "detection", "event_id": det_id, "ts": round(at, 3), **common, "camera_id": cam,
         "track_id": f"trk_{cam}_{tag}", "label": "person", "confidence": 0.9, "bbox": None, "activity": "none",
         "activity_confidence": 0.95, "direction": None, "appearance": appearance, "on_screen": "fleeing",
         "what_happened": "Someone runs past, as if escaping."},
        {"type": "relay", "event_id": rel_id, "ts": round(at + RELAY_AFTER_S, 3), **common, "from_camera": last,
         "to_camera": cam, "subject_id": subject,
         "summary": f"Lookout: description match, {cold}. {activity.replace('_', ' ').capitalize()} at "
                    f"{crime['camera_id']}; last seen at {last}.",
         "appearance": look, "direction": None, "activity": activity, "confidence": 0.6, "expected_arrival_s": None,
         "basis": "lookout",
         "evidence_event_ids": [cause["event_id"]] + ([seen["event_id"]] if seen else []) + [det_id]},
        {"type": "agent_verdict", "event_id": f"ver_{tag}_1", "ts": round(at + VERDICT_AFTER_S, 3), **common,
         "agent_id": "agent_" + cam.replace("_", ""), "camera_id": cam, "subject_id": subject, "decision": "match",
         "confidence": 0.75, "reason": f"{appearance} matches the lookout from {last} ({cold}); description match "
                                       f"only, {cam} is not a neighbor of {last}.",
         "evidence_event_ids": [rel_id, det_id]},
    ]


def check_in_view(cams: dict[str, dict], cam: str, at: float) -> None:
    """The detection and the verdict (the dashboard's last sighting) must fall where the suspect is in view."""
    start = (cams[cam].get("source") or {}).get("start_ts")
    if not isinstance(start, (int, float)):
        raise ValueError(f"{cam} has no source.start_ts in the cameras file")
    lo, hi = IN_VIEW_S
    seconds = (at - start, at + VERDICT_AFTER_S - start)
    if not all(lo <= s <= hi for s in seconds):
        raise ValueError(f"{cam}'s clip shows the suspect at {lo}-{hi} s, but the sighting would be at "
                         f"{seconds[0]:.2f}-{seconds[1]:.2f} s (start_ts {start:g}); fix start_ts or --after")
    print(f"{cam}: detection at clip second {seconds[0]:.2f}, verdict at {seconds[1]:.2f} (start_ts {start:g})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cameras", default=os.environ.get("CLARITY_CAMERAS") or DEFAULT_CAMERAS)
    p.add_argument("--crime-camera", default="cam_05", help="Route 2's crime camera (finds the subject)")
    p.add_argument("--subject", help="the subject id, if more than one subject has a crime at --crime-camera")
    p.add_argument("--from", dest="last", default="cam_06", help="where the trail went cold; sends the lookout")
    p.add_argument("--camera", default="cam_14", help="the far camera that picks the suspect up")
    p.add_argument("--after", type=float, default=1800.0, help="seconds from the crime detection to the pickup")
    p.add_argument("--appearance", default="black hoodie, dark grey trousers",
                   help="what the far camera's detection describes (default: clip 8's hand label)")
    p.add_argument("--out", help="write the events to this .jsonl file instead of publishing")
    args = p.parse_args()

    try:
        site = load_site(args.cameras)
        cams = {c["camera_id"]: c for c in site["cameras"]}
        for c in (args.crime_camera, args.last, args.camera):
            if c not in cams:
                raise ValueError(f"{c} is not in {args.cameras}")
        if any(nb["camera_id"] == args.last for nb in cams[args.camera].get("neighbors", [])):
            raise ValueError(f"{args.camera} is a neighbor of {args.last}; a lookout goes to a camera the chase "
                             "can't reach")
        check_bus_serves(site, args.cameras)
        subject, crime = route_subject(args.crime_camera, args.subject)
        cause, seen, newest = last_sighting(subject, args.last)
        at = round(crime["ts"] + args.after, 3)
        if at <= newest:
            raise ValueError(f"the pickup at {at:g} must come after the subject's last event (ts {newest:g})")
        check_in_view(cams, args.camera, at)
    except ValueError as e:
        raise SystemExit(f"error: {e}")  # one line on stderr, exit status 1
    events = pickup_events(subject, crime, cause, seen, args.last, args.camera, at, args.appearance,
                           os.environ.get("CLARITY_RUN_ID"))
    print(f"subject {subject}: crime at {crime['camera_id']} ts {crime['ts']:g}, last seen at {args.last}, "
          f"pickup at {args.camera} ts {at:g}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        print(f"wrote {len(events)} events to {args.out}")
        return
    for i, e in enumerate(events):
        if i:
            time.sleep(e["ts"] - events[i - 1]["ts"])  # real-time pacing, 0.25 s apart
        publish(e)
        print(f"{e['ts']:9.2f}  {e['type']:<14} {e['event_id']}")


if __name__ == "__main__":
    main()
