"""Scripted demo run: three overlapping incidents published to the bus, no models needed.

Each incident follows one route of four cameras: crime spot -> junction -> real exit, plus a decoy
exit next to the junction. The junction agent relays to both exits; the real exit answers "match",
the decoy answers "no_match". Walking times come from cameras.json, so the script matches the map.
Every event has source="fake_scenario" so the dashboard can label it as scripted. Event text names cameras
only by their cameras.json names, which are neutral ("Route 1: west door"); roles never appear in it.

Run from the repo root (bus running, started with the same CLARITY_CAMERAS):
    python -m bus.fake_scenario --speed 5
    python -m bus.fake_scenario --out runs/fake/events.jsonl   # write a log instead of publishing
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from bus.client import publish

DEFAULT_CAMERAS = "data/sites/annex_placeholder/cameras.json"
SOURCE = "fake_scenario"

# One entry per incident. Cameras must be neighbors in cameras.json.
INCIDENTS = [
    {"n": 1, "start": 0.0, "activity": "fistfight", "priority": "high",
     "crime": "cam_01", "junction": "cam_02", "exit": "cam_03", "decoy": "cam_04",
     "appearance": "male, red hoodie, blue jeans",
     "summary": "Punched another person repeatedly near the corner, then walked off fast."},
    {"n": 2, "start": 10.0, "activity": "purse_snatch", "priority": "medium",
     "crime": "cam_05", "junction": "cam_06", "exit": "cam_07", "decoy": "cam_08",
     "appearance": "female, yellow jacket, black pants",
     "summary": "Pulled a bag off a person's shoulder and ran."},
    {"n": 3, "start": 20.0, "activity": "purse_snatch", "priority": "medium",
     "crime": "cam_09", "junction": "cam_10", "exit": "cam_11", "decoy": "cam_12",
     "appearance": "male, black cap, grey backpack",
     "summary": "Grabbed a phone out of a person's hand and ran."},
]


def load_cameras(path: str) -> dict[str, dict]:
    site = json.loads(Path(path).read_text(encoding="utf-8"))
    return {c["camera_id"]: c for c in site["cameras"]}


def link(cams: dict[str, dict], a: str, b: str) -> dict:
    """The neighbor entry a -> b (travel_time_s, direction)."""
    for cam in (a, b):
        if cam not in cams:
            raise ValueError(f"{cam} is not in cameras.json; the scenario needs the 12-camera placeholder layout")
    for nb in cams[a]["neighbors"]:
        if nb["camera_id"] == b:
            return nb
    raise ValueError(f"{b} is not a neighbor of {a} in cameras.json")


def incident_events(inc: dict, cams: dict[str, dict], run_id: str) -> list[dict]:
    n, t0 = inc["n"], inc["start"]
    a, b, c, d = inc["crime"], inc["junction"], inc["exit"], inc["decoy"]
    ab, bc, bd = link(cams, a, b), link(cams, b, c), link(cams, b, d)
    subj, inc_id = f"subj_{n}", f"inc_{n}"
    common = {"schema_version": "0.1", "run_id": run_id, "source": SOURCE}
    look = {"appearance": inc["appearance"]}

    def ev(type_, event_id, ts, **fields):
        return {"type": type_, "event_id": event_id, "ts": round(ts, 1), **common, **fields}

    def detection(i, cam, ts, activity, direction):
        return ev("detection", f"det_i{n}_{i}", ts, camera_id=cam, track_id=f"trk_{cam}_{n}", label="person",
                  confidence=0.9, bbox=None, activity=activity,
                  activity_confidence=0.8 if activity != "none" else 0.95, direction=direction, **look)

    def relay(i, frm, to, ts, nb, evidence):
        return ev("relay", f"rel_i{n}_{i}", ts, from_camera=frm, to_camera=to, subject_id=subj,
                  summary=inc["summary"], direction=nb["direction"], activity=inc["activity"], confidence=0.85,
                  expected_arrival_s=nb["travel_time_s"], evidence_event_ids=evidence, **look)

    def verdict(i, cam, ts, decision, reason, evidence):
        return ev("agent_verdict", f"ver_i{n}_{i}", ts, agent_id=f"agent_{cam}", camera_id=cam, subject_id=subj,
                  decision=decision, confidence=0.88 if decision == "match" else 0.8, reason=reason,
                  evidence_event_ids=evidence)

    def dispatch(i, ts, status, path, predicted, recommendation, reason, evidence, confirm):
        return ev("dispatch", f"dsp_i{n}_{i}", ts, incident_id=inc_id, subject_id=subj,
                  incident_type=inc["activity"], subject_appearance=inc["appearance"], status=status,
                  priority=inc["priority"], path=path, predicted_next=predicted, recommendation=recommendation,
                  reason=reason, evidence_event_ids=evidence, requires_human_confirm=confirm)

    def step(cam, ts, event_id):
        return {"camera_id": cam, "ts": round(ts, 1), "event_id": event_id}

    name = {k: cams[k]["name"] for k in (a, b, c, d)}
    t_b = t0 + ab["travel_time_s"]              # suspect reaches the junction
    t_c = t_b + bc["travel_time_s"]             # ...and the real exit
    t_d_done = t_b + bd["travel_time_s"] + 5    # decoy gives up a bit after it expected them
    t_end = max(t_c + 1, t_d_done) + 1
    crime = inc["activity"].replace("_", " ")

    return [
        detection(1, a, t0, inc["activity"], ab["direction"]),
        relay(1, a, b, t0 + 1, ab, [f"det_i{n}_1"]),
        dispatch(1, t0 + 2, "tracking", [step(a, t0, f"det_i{n}_1")], [{"camera_id": b, "probability": 1.0}],
                 f"Watch {name[b]}; send an officer toward {name[a]}.",
                 f"{crime.capitalize()} at {name[a]}; suspect heading {ab['direction']}.",
                 [f"det_i{n}_1", f"rel_i{n}_1"], False),

        detection(2, b, t_b, "none", bc["direction"]),
        verdict(1, b, t_b + 1, "match",
                f"{inc['appearance']} matches the relay from {a}; arrived on time, moving {bc['direction']}.",
                [f"rel_i{n}_1", f"det_i{n}_2"]),
        relay(2, b, c, t_b + 2, bc, [f"ver_i{n}_1"]),
        relay(3, b, d, t_b + 2, bd, [f"ver_i{n}_1"]),
        dispatch(2, t_b + 3, "tracking", [step(a, t0, f"det_i{n}_1"), step(b, t_b + 1, f"ver_i{n}_1")],
                 [{"camera_id": c, "probability": 0.6}, {"camera_id": d, "probability": 0.4}],
                 f"Suspect passed {name[b]}; officers toward {name[c]} or {name[d]}.",
                 f"Confirmed at {name[b]}, moving {bc['direction']}.",
                 [f"det_i{n}_1", f"rel_i{n}_1", f"ver_i{n}_1"], False),

        detection(3, c, t_c, "none", bc["direction"]),
        verdict(2, c, t_c + 1, "match", f"{inc['appearance']} matches; arrived when expected from {b}.",
                [f"rel_i{n}_2", f"det_i{n}_3"]),
        verdict(3, d, t_d_done, "no_match",
                f"Nobody matching {inc['appearance']} within {bd['travel_time_s']}s of the relay from {b}.",
                [f"rel_i{n}_3"]),
        dispatch(3, t_end, "alert",
                 [step(a, t0, f"det_i{n}_1"), step(b, t_b + 1, f"ver_i{n}_1"), step(c, t_c + 1, f"ver_i{n}_2")],
                 [], f"Send officers to {name[c]}; check on the victim at {name[a]}.",
                 f"Seen at {name[a]}, {name[b]}, then {name[c]}; {name[d]} saw no match.",
                 [f"det_i{n}_1", f"rel_i{n}_1", f"ver_i{n}_1", f"rel_i{n}_2", f"ver_i{n}_2", f"rel_i{n}_3",
                  f"ver_i{n}_3"], True),
    ]


def build(cameras_path: str, run_id: str) -> list[dict]:
    cams = load_cameras(cameras_path)
    status = [{"type": "camera_status", "schema_version": "0.1", "event_id": f"cst_{cam_id}_0", "ts": 0.0,
               "run_id": run_id, "source": SOURCE, "camera_id": cam_id, "status": "online", "fps": 1.0,
               "source_kind": "replay"} for cam_id in cams]
    events = status + [e for inc in INCIDENTS for e in incident_events(inc, cams, run_id)]
    return sorted(events, key=lambda e: e["ts"])  # stable sort keeps causal order at equal ts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cameras", default=os.environ.get("CLARITY_CAMERAS", DEFAULT_CAMERAS))
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast as real time")
    p.add_argument("--out", help="write events to this .jsonl file instead of publishing")
    args = p.parse_args()
    if args.speed <= 0:
        p.error("--speed must be greater than 0")

    events = build(args.cameras, os.environ.get("CLARITY_RUN_ID", "run_fake"))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        print(f"wrote {len(events)} events to {args.out}")
        return

    print(f"publishing {len(events)} events over ~{events[-1]['ts'] / args.speed:.0f}s (speed {args.speed}x)")
    start = time.monotonic()
    for e in events:
        wait = e["ts"] / args.speed - (time.monotonic() - start)
        if wait > 0:
            time.sleep(wait)
        publish(e)
        print(f"{e['ts']:7.1f}  {e['type']:<14} {e['event_id']}")


if __name__ == "__main__":
    main()
