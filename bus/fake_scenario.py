"""Scripted demo run: three overlapping incidents (or one staged take) published to the bus, no models needed.

Each incident follows one route of four cameras: crime spot -> junction -> real exit, plus a decoy
exit next to the junction. The junction agent relays to both exits; the real exit answers "match",
the decoy answers "no_match". Walking times come from cameras.json, so the script matches the map.
Every event has source="fake_scenario" so the dashboard can label it as scripted. Event text names cameras
only by their cameras.json names, which are neutral ("Route 1: west door"); roles never appear in it.

--ground-truth replaces the three placeholder incidents with one staged take on its real site, timed by
the take's ground truth (data/ground_truth/take<N>.json, already in run-clock seconds). It publishes what
camera agents would: the crime detection, then at each later camera a sighting, a "match" verdict and a
relay on. It never scripts a dispatch: start a real dispatcher (python -m dispatcher.run) first.

Run from the repo root (bus running, started with the same CLARITY_CAMERAS):
    python -m bus.fake_scenario --speed 5
    python -m bus.fake_scenario --out runs/fake/events.jsonl   # write a log instead of publishing
    python -m bus.fake_scenario --no-dispatch                  # scripted perception only; a real
                                                               # dispatcher (python -m dispatcher.run) decides
    python -m bus.fake_scenario --ground-truth data/ground_truth/take1.json --cameras data/sites/annex/cameras.json
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
# Priorities match the real dispatcher (dispatcher/rules.py: fistfight medium, purse_snatch low).
INCIDENTS = [
    {"n": 1, "start": 0.0, "activity": "fistfight", "priority": "medium",
     "crime": "cam_01", "junction": "cam_02", "exit": "cam_03", "decoy": "cam_04",
     "appearance": "male, red hoodie, blue jeans",
     "summary": "Punched another person repeatedly near the corner, then walked off fast."},
    {"n": 2, "start": 10.0, "activity": "purse_snatch", "priority": "low",
     "crime": "cam_05", "junction": "cam_06", "exit": "cam_07", "decoy": "cam_08",
     "appearance": "female, yellow jacket, black pants",
     "summary": "Pulled a bag off a person's shoulder and ran."},
    {"n": 3, "start": 20.0, "activity": "purse_snatch", "priority": "low",
     "crime": "cam_09", "junction": "cam_10", "exit": "cam_11", "decoy": "cam_12",
     "appearance": "male, black cap, grey backpack",
     "summary": "Grabbed a phone out of a person's hand and ran."},
]

# --ground-truth mode. What the crime camera's agent says happened (relay summary and the spotter's
# what_happened), per activity.
SCENES = {
    "purse_snatch": "Snatched something from a person's hand and ran off.",
    "fistfight": "Punched another person repeatedly, then walked off fast.",
    "stabbing": "Attacked another person with stabbing motions, then ran off.",
}
VERDICT_AFTER_S = 0.5  # a camera agent answers a relay this long after the suspect walks into view


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


def load_ground_truth(path: str, cameras_path: str, cams: dict[str, dict]) -> dict:
    """A take's ground truth, checked against the cameras file (which must be the one the bus serves)."""
    gt = json.loads(Path(path).read_text(encoding="utf-8"))
    site_id = json.loads(Path(cameras_path).read_text(encoding="utf-8")).get("site_id")
    if gt.get("site_id") != site_id:
        raise ValueError(f"{path} is for site {gt.get('site_id')!r} but {cameras_path} is site {site_id!r}; pass "
                         "--cameras with that site's cameras.json (the bus's CLARITY_CAMERAS)")
    missing = [s["camera_id"] for s in gt["path"] if s["camera_id"] not in cams]
    if missing:
        raise ValueError(f"{', '.join(missing)} from {path} not in {cameras_path}")
    if len(gt["path"]) < 2:
        raise ValueError(f"{path}: the path needs 2+ cameras, or nothing gets relayed")
    if gt.get("decoy_camera_id"):
        print(f"note: decoy {gt['decoy_camera_id']} is not scripted in --ground-truth mode")
    return gt


def take_events(gt: dict, cams: dict[str, dict], run_id: str) -> list[dict]:
    """One staged take as its camera agents would publish it, at the ground truth's run-clock times.

    The crime camera detects the crime as the suspect walks into view and relays to the next camera as they
    leave it (expected there after the cameras.json travel time). Each later camera sees them walk in, answers
    the relay with "match" and relays on. No dispatch: a real dispatcher decides.
    """
    tag, subj, activity, look = (gt["incident_id"].removeprefix("inc_"), gt["subject_id"], gt["activity"],
                                 gt["appearance"])
    scene = SCENES.get(activity, f"{activity.replace('_', ' ').capitalize()}, then ran off.")
    common = {"schema_version": "0.1", "run_id": run_id, "source": SOURCE}
    steps, out = gt["path"], []

    def ev(type_, event_id, ts, **fields):
        out.append({"type": type_, "event_id": event_id, "ts": round(ts, 3), **common, **fields})
        return event_id

    relay_in = None  # the relay that sent the suspect to the current camera
    for i, step in enumerate(steps):
        cam = step["camera_id"]
        nxt = steps[i + 1]["camera_id"] if i + 1 < len(steps) else None
        onward = link(cams, cam, nxt) if nxt else None
        heading = onward["direction"] if onward else relay_in["direction"]
        crime = relay_in is None
        # on_screen / what_happened: the spotter's extra fields, which the real detection adapter copies too.
        det = ev("detection", f"det_{tag}_{i + 1}", step["t_enter"], camera_id=cam, track_id=f"trk_{cam}_{tag}",
                 label="person", confidence=0.9, bbox=None, activity=activity if crime else "none",
                 activity_confidence=0.8 if crime else 0.95, direction=heading, appearance=look,
                 on_screen="crime" if crime else "fleeing",
                 what_happened=scene if crime else "Someone runs past, as if escaping.")
        cause = det
        if relay_in:
            gap = step["t_enter"] - relay_in["ts"]
            cause = ev("agent_verdict", f"ver_{tag}_{i}", step["t_enter"] + VERDICT_AFTER_S, agent_id=f"agent_{cam}",
                       camera_id=cam, subject_id=subj, decision="match", confidence=0.88,
                       reason=f"{look} matches the relay from {relay_in['from_camera']}; seen {gap:.1f} s after it "
                              f"(expected {relay_in['expected_arrival_s']:.1f} s), moving {heading}.",
                       evidence_event_ids=[relay_in["event_id"], det])
        if onward:
            ev("relay", f"rel_{tag}_{i + 1}", max(step["t_exit"], out[-1]["ts"]), from_camera=cam, to_camera=nxt,
               subject_id=subj, summary=scene, direction=onward["direction"], activity=activity, confidence=0.85,
               expected_arrival_s=onward["travel_time_s"], evidence_event_ids=[cause], appearance=look)
            relay_in = out[-1]
    return out


def camera_status_events(cams: dict[str, dict], run_id: str) -> list[dict]:
    return [{"type": "camera_status", "schema_version": "0.1", "event_id": f"cst_{cam_id}_0", "ts": 0.0,
             "run_id": run_id, "source": SOURCE, "camera_id": cam_id, "status": "online", "fps": 1.0,
             "source_kind": "replay"} for cam_id in cams]


def build(cameras_path: str, run_id: str, ground_truth: str | None = None) -> list[dict]:
    cams = load_cameras(cameras_path)
    if ground_truth:
        script = take_events(load_ground_truth(ground_truth, cameras_path, cams), cams, run_id)
    else:
        script = [e for inc in INCIDENTS for e in incident_events(inc, cams, run_id)]
    events = camera_status_events(cams, run_id) + script
    return sorted(events, key=lambda e: e["ts"])  # stable sort keeps causal order at equal ts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cameras", default=os.environ.get("CLARITY_CAMERAS", DEFAULT_CAMERAS))
    p.add_argument("--speed", type=float, default=1.0, help="2 = twice as fast as real time")
    p.add_argument("--out", help="write events to this .jsonl file instead of publishing")
    p.add_argument("--no-dispatch", action="store_true",
                   help="leave out the scripted dispatch events so a real dispatcher makes the decisions")
    p.add_argument("--ground-truth", metavar="TAKE_JSON",
                   help="one staged take on its real site instead of the placeholder incidents, timed by its ground "
                        "truth (e.g. data/ground_truth/take1.json); never scripts a dispatch")
    args = p.parse_args()
    if args.speed <= 0:
        p.error("--speed must be greater than 0")

    events = build(args.cameras, os.environ.get("CLARITY_RUN_ID", "run_fake"), args.ground_truth)
    if args.no_dispatch:
        events = [e for e in events if e["type"] != "dispatch"]
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
