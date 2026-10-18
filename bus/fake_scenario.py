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
The crime camera comes from the take's camera_roles; its detection fires at the crime itself (t_crime on
that camera's path step, run clock) or, without one, as the suspect leaves its view. Event and subject ids
carry a fresh tag every run, so a rerun into the same bus and dispatcher is a new incident, not duplicates
they drop. Before publishing it checks that the bus (GET /cameras) serves the take's site.

--lookout CAM (with --ground-truth) scripts the take's last path step, CAM, as a far re-sighting instead of a
handoff: CAM is no neighbor of the chase, so the chase runs to the camera before it, the trail goes cold, and
at CAM's t_enter its agent sees someone run past (detection), the last chase camera sends it a lookout relay
(basis "lookout": a description match, no expected arrival) and CAM's agent answers "match".
--max-gap caps every pause between two events (run-clock seconds) while publishing; the events keep their
true ts, so a 38-minute cold trail plays in a few seconds.

Run from the repo root (bus running, started with the same CLARITY_CAMERAS):
    python -m bus.fake_scenario --speed 5
    python -m bus.fake_scenario --out runs/fake/events.jsonl   # write a log instead of publishing
    python -m bus.fake_scenario --no-dispatch                  # scripted perception only; a real
                                                               # dispatcher (python -m dispatcher.run) decides
    python -m bus.fake_scenario --ground-truth data/ground_truth/take1.json --cameras data/sites/annex/cameras.json
    python -m bus.fake_scenario --ground-truth data/ground_truth/annex_lookout/take3.json \\
        --cameras data/sites/annex_lookout/cameras.json --lookout cam_14 --max-gap 5
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from bus.client import _bus_url, publish  # _bus_url: the address publish() posts to

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
RELAY_AFTER_S = 0.5  # ...and relays on no sooner than this after its own detection or verdict
LOOKOUT_AFTER_S = 0.25  # a lookout relay follows the far camera's detection (it is what matched the description)
GT_FIELDS = ("site_id", "incident_id", "subject_id", "activity", "appearance", "path", "camera_roles")


def read_json(path: str, what: str) -> dict:
    """A JSON object from a file. Anything wrong is a ValueError with one readable line."""
    if Path(path).is_dir():  # Windows would only say "Permission denied"
        raise ValueError(f"{what} {path} is a folder; pass the .json file")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{what} {path} not found") from None
    except OSError as e:  # no permission, ...
        raise ValueError(f"can't read {what} {path} ({e.strerror or e})") from None
    except ValueError as e:  # not JSON, or not UTF-8
        raise ValueError(f"{what} {path} is not valid JSON ({e})") from None
    if not isinstance(data, dict):
        raise ValueError(f"{what} {path} is not a JSON object")
    return data


def load_cameras(path: str) -> dict[str, dict]:
    site = read_json(path, "cameras file")
    if not isinstance(site.get("cameras"), list):
        raise ValueError(f"{path} has no 'cameras' list; pass a site's cameras.json")
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


def is_time(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def crime_camera(gt: dict) -> str | None:
    """The take's crime camera, from camera_roles (a path may start with an approach camera); None if not one."""
    roles = gt.get("camera_roles")
    crimes = [cam for cam, role in roles.items() if role == "crime"] if isinstance(roles, dict) else []
    return crimes[0] if len(crimes) == 1 else None


def ground_truth_problem(gt: dict) -> str | None:
    """What makes this unusable as a take's ground truth, or None."""
    missing = [k for k in GT_FIELDS if k not in gt]
    if missing:
        return f"no {', '.join(missing)}; is it a take's ground truth, like data/ground_truth/take1.json?"
    steps = gt["path"]
    if not (isinstance(steps, list) and all(isinstance(s, dict) and isinstance(s.get("camera_id"), str)
                                            and is_time(s.get("t_enter")) and is_time(s.get("t_exit"))
                                            for s in steps)):
        return "path must be a list of {camera_id, t_enter, t_exit}"
    on_path, crime = [s["camera_id"] for s in steps], crime_camera(gt)
    if crime not in on_path:
        return "camera_roles needs exactly one 'crime' camera, and it must be on the path"
    k = on_path.index(crime)
    if k == len(steps) - 1:
        return f"no camera after the crime camera {crime} on the path, so nothing gets relayed"
    t_crime = steps[k].get("t_crime")
    if t_crime is not None and not (is_time(t_crime) and steps[k]["t_enter"] <= t_crime <= steps[k]["t_exit"]):
        return f"t_crime of {crime} must be a run-clock time between its t_enter and t_exit"
    return None


def lookout_problem(gt: dict, lookout: str | None) -> str | None:
    """What makes --lookout unusable with this ground truth, or None. The lookout camera must be the last path
    step, after the crime camera; a camera the ground truth marks "lookout" needs --lookout."""
    marked = [cam for cam, role in gt["camera_roles"].items() if role == "lookout"]
    if lookout is None:
        return f"camera_roles marks {marked[0]} as a far re-sighting; pass --lookout {marked[0]}" if marked else None
    if gt["path"][-1]["camera_id"] != lookout:  # ground_truth_problem: the crime camera is never the last
        return f"--lookout {lookout} must be the last camera on the path"
    return None


def load_ground_truth(path: str, cameras_path: str, cams: dict[str, dict], lookout: str | None = None) -> dict:
    """A take's ground truth, checked against the cameras file (which must be the one the bus serves).
    Anything wrong is a ValueError with one readable line."""
    gt = read_json(path, "ground truth")
    problem = ground_truth_problem(gt) or lookout_problem(gt, lookout)
    if problem:
        raise ValueError(f"{path}: {problem}")
    site_id = read_json(cameras_path, "cameras file").get("site_id")
    if gt["site_id"] != site_id:
        raise ValueError(f"{path} is for site {gt['site_id']!r} but {cameras_path} is site {site_id!r}; pass "
                         "--cameras with that site's cameras.json (the bus's CLARITY_CAMERAS)")
    on_path = [s["camera_id"] for s in gt["path"]]
    missing = [cam for cam in on_path if cam not in cams]
    if missing:
        raise ValueError(f"{', '.join(missing)} from {path} not in {cameras_path}")
    before = on_path[:on_path.index(crime_camera(gt))]
    if before:
        print(f"note: not scripted before the crime (nobody is looking for the suspect yet): {', '.join(before)}")
    if gt.get("decoy_camera_id"):
        print(f"note: decoy {gt['decoy_camera_id']} is not scripted in --ground-truth mode")
    return gt


def check_bus_site(ground_truth: str, cameras_path: str) -> None:
    """The bus must serve the take's site (GET /cameras): the dashboard and the dispatcher take their cameras
    from it. A ValueError with one line if it serves another site or can't be read."""
    want = read_json(cameras_path, "cameras file").get("site_id")  # the take's site (load_ground_truth checked)
    url = f"{_bus_url()}/cameras"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            served = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # the bus answered, but has no readable cameras file
        raise ValueError(f"the bus at {url} serves no cameras (HTTP {e.code}); restart it with "
                         f"CLARITY_CAMERAS={cameras_path}") from None
    except (OSError, ValueError) as e:  # bus down, timeout, not JSON
        raise ValueError(f"can't read the bus's cameras at {url} ({getattr(e, 'reason', e)}); start the bus "
                         f"with CLARITY_CAMERAS={cameras_path}, or write a file with --out") from None
    got = served.get("site_id") if isinstance(served, dict) else None
    if got != want:
        raise ValueError(f"the bus at {_bus_url()} serves site {got!r}, but {ground_truth} is site {want!r}; "
                         f"restart the bus with CLARITY_CAMERAS={cameras_path}")


def crime_moment(step: dict) -> float:
    """When the crime camera's detection fires: at the crime (t_crime), else as the suspect leaves (t_exit);
    never as they walk in, before anything has happened."""
    return step["t_crime"] if step.get("t_crime") is not None else step["t_exit"]


def take_events(gt: dict, cams: dict[str, dict], run_id: str, run_tag: str, lookout: str | None = None) -> list[dict]:
    """One staged take as its camera agents would publish it, at the ground truth's run-clock times.

    The crime camera (camera_roles) detects the crime when it happens (crime_moment), then relays to the next
    camera as the suspect leaves its view (expected there after the cameras.json travel time). Each later camera
    sees the suspect walk in, answers the relay with "match" and relays on. Cameras before the crime (an approach)
    aren't scripted. No dispatch: a real dispatcher decides. run_tag goes into every id, so each run is its own
    incident. With lookout (the path's last camera, checked by lookout_problem) the chase stops one camera
    earlier, and the far re-sighting follows at the lookout camera's t_enter: detection, lookout relay, match.
    """
    tag, subj, activity, look = (f"{gt['incident_id'].removeprefix('inc_')}_{run_tag}",
                                 f"{gt['subject_id']}_{run_tag}", gt["activity"], gt["appearance"])
    scene = SCENES.get(activity, f"{activity.replace('_', ' ').capitalize()}, then ran off.")
    common = {"schema_version": "0.1", "run_id": run_id, "source": SOURCE}
    on_path = [s["camera_id"] for s in gt["path"]]
    steps, out = gt["path"][on_path.index(crime_camera(gt)):], []
    far = steps.pop() if lookout else None

    def ev(type_, event_id, ts, **fields):
        out.append({"type": type_, "event_id": event_id, "ts": round(ts, 3), **common, **fields})
        return event_id

    relay_in = None  # the relay that sent the suspect to the current camera
    for i, step in enumerate(steps):
        cam = step["camera_id"]
        nxt = steps[i + 1]["camera_id"] if i + 1 < len(steps) else None
        onward = link(cams, cam, nxt) if nxt else None
        heading = onward["direction"] if onward else relay_in["direction"] if relay_in else None
        crime = relay_in is None
        seen_at = crime_moment(step) if crime else step["t_enter"]
        # on_screen / what_happened: the spotter's extra fields, which the real detection adapter copies too.
        det = ev("detection", f"det_{tag}_{i + 1}", seen_at, camera_id=cam, track_id=f"trk_{cam}_{tag}",
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
            ev("relay", f"rel_{tag}_{i + 1}", max(step["t_exit"], out[-1]["ts"] + RELAY_AFTER_S),
               from_camera=cam, to_camera=nxt, subject_id=subj, summary=scene, direction=onward["direction"],
               activity=activity, confidence=0.85, expected_arrival_s=onward["travel_time_s"],
               evidence_event_ids=[cause], appearance=look)
            relay_in = out[-1]

    if far:  # the trail went cold at the last chase camera; nobody saw which way they went (direction None)
        n, last, cam = len(steps), steps[-1]["camera_id"], far["camera_id"]
        cold = f"trail cold {(far['t_enter'] - steps[-1]['t_exit']) / 60:.0f} min"
        det = ev("detection", f"det_{tag}_{n + 1}", far["t_enter"], camera_id=cam, track_id=f"trk_{cam}_{tag}",
                 label="person", confidence=0.9, bbox=None, activity="none", activity_confidence=0.95, direction=None,
                 appearance=look, on_screen="fleeing", what_happened="Someone runs past, as if escaping.")
        rel = ev("relay", f"rel_{tag}_{n}", far["t_enter"] + LOOKOUT_AFTER_S, from_camera=last, to_camera=cam,
                 subject_id=subj, summary=f"Lookout: description match, {cold}. {scene} Last seen at {last}.",
                 direction=None, activity=activity, confidence=0.6, expected_arrival_s=None,
                 evidence_event_ids=[cause, det], appearance=look, basis="lookout")
        ev("agent_verdict", f"ver_{tag}_{n}", far["t_enter"] + VERDICT_AFTER_S, agent_id=f"agent_{cam}",
           camera_id=cam, subject_id=subj, decision="match", confidence=0.75,
           reason=f"{look} matches the lookout from {last} ({cold}); description match only, {cam} is not a "
                  f"neighbor of the chase.",
           evidence_event_ids=[rel, det])
    return out


def camera_status_events(cams: dict[str, dict], run_id: str, run_tag: str = "") -> list[dict]:
    n = f"{run_tag}_0" if run_tag else "0"  # cst_<cam>_<tag>_0 when tagged, like feeds/base.py
    return [{"type": "camera_status", "schema_version": "0.1", "event_id": f"cst_{cam_id}_{n}", "ts": 0.0,
             "run_id": run_id, "source": SOURCE, "camera_id": cam_id, "status": "online", "fps": 1.0,
             "source_kind": "replay"} for cam_id in cams]


def build(cameras_path: str, run_id: str, ground_truth: str | None = None, lookout: str | None = None) -> list[dict]:
    cams = load_cameras(cameras_path)
    if ground_truth:
        # A fresh tag per run: the dispatcher and the dashboard drop an event_id they've already seen, and the
        # dispatcher files a known subject_id under its old incident, so a rerun into the same bus would vanish.
        run_tag = uuid.uuid4().hex[:6]
        gt = load_ground_truth(ground_truth, cameras_path, cams, lookout)
        events = camera_status_events(cams, run_id, run_tag) + take_events(gt, cams, run_id, run_tag, lookout)
    else:
        script = [e for inc in INCIDENTS for e in incident_events(inc, cams, run_id)]
        events = camera_status_events(cams, run_id) + script
    return sorted(events, key=lambda e: e["ts"])  # stable sort keeps causal order at equal ts


def send_times(events: list[dict], speed: float, max_gap: float | None = None) -> list[float]:
    """Seconds after the start at which each (ts-sorted) event goes out: its ts / speed, with every pause
    between two events capped at max_gap run-clock seconds first (None = no cap)."""
    times, clock, prev = [], 0.0, 0.0
    for e in events:
        gap = e["ts"] - prev
        clock += gap if max_gap is None else min(gap, max_gap)
        prev = e["ts"]
        times.append(clock / speed)
    return times


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
    p.add_argument("--lookout", metavar="CAMERA_ID",
                   help="with --ground-truth: script the path's last camera (no neighbor of the chase) as a far "
                        "re-sighting after the trail goes cold, e.g. cam_14")
    p.add_argument("--max-gap", type=float, metavar="SECONDS",
                   help="longest pause between two events while publishing, in run-clock seconds; events keep "
                        "their true ts (default: no cap)")
    args = p.parse_args()
    if args.speed <= 0:
        p.error("--speed must be greater than 0")
    if args.max_gap is not None and args.max_gap < 0:
        p.error("--max-gap must be 0 or more")
    if args.lookout and not args.ground_truth:
        p.error("--lookout needs --ground-truth")

    try:
        events = build(args.cameras, os.environ.get("CLARITY_RUN_ID", "run_fake"), args.ground_truth, args.lookout)
        if args.ground_truth and not args.out:
            check_bus_site(args.ground_truth, args.cameras)
    except ValueError as e:
        raise SystemExit(f"error: {e}")  # one line on stderr, exit status 1
    if args.no_dispatch:
        events = [e for e in events if e["type"] != "dispatch"]
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        print(f"wrote {len(events)} events to {args.out}")
        return

    times = send_times(events, args.speed, args.max_gap)
    print(f"publishing {len(events)} events over ~{times[-1]:.0f}s (speed {args.speed}x)")
    start = time.monotonic()
    for at, e in zip(times, events):
        wait = at - (time.monotonic() - start)
        if wait > 0:
            time.sleep(wait)
        publish(e)
        print(f"{e['ts']:7.1f}  {e['type']:<14} {e['event_id']}")


if __name__ == "__main__":
    main()
