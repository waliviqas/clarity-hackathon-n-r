"""Run the dispatcher on contract v0.1 messages.

    python -m dispatcher.demo                                   # built-in scenario, scripted model
    python -m dispatcher.demo --live                            # real model via CLARITY_LLM_* env vars (vLLM)
    python -m dispatcher.demo --cameras cameras.json --messages run.jsonl [--live]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .dispatcher import Dispatcher
from .graph import CameraGraph


def _hdr(kind: str, eid: str, ts: float) -> dict:
    return {"type": kind, "schema_version": "0.1", "event_id": eid, "ts": ts}


def _cam(cid: str, name: str, x: float, y: float, neighbors: list[tuple[str, int, str]]) -> dict:
    return {"camera_id": cid, "name": name, "position": None, "site_xy": {"x": x, "y": y},
            "neighbors": [{"camera_id": n, "travel_time_s": t, "direction": d} for n, t, d in neighbors],
            "source": {"kind": "replay", "uri": f"clips/{cid}.mp4", "start_ts": 0}}


# Three routes, each crime spot -> junction -> real exit, with a decoy exit off the junction.
CAMERAS = {
    "schema_version": "0.1", "site_id": "demo_site", "site_name": "Dispatcher demo (synthetic)",
    "cameras": [
        _cam("cam_01", "Route 1: crime spot", 0.2, 0.8, [("cam_02", 30, "north")]),
        _cam("cam_02", "Route 1: junction", 0.2, 0.5, [("cam_01", 30, "south"), ("cam_03", 25, "north"),
                                                      ("cam_04", 30, "east")]),
        _cam("cam_03", "Route 1: exit", 0.2, 0.2, [("cam_02", 25, "south")]),
        _cam("cam_04", "Route 1: decoy exit", 0.4, 0.5, [("cam_02", 30, "west")]),
        _cam("cam_05", "Route 2: crime spot", 0.6, 0.8, [("cam_06", 28, "east")]),
        _cam("cam_06", "Route 2: junction", 0.8, 0.8, [("cam_05", 28, "west"), ("cam_07", 26, "east"),
                                                      ("cam_08", 32, "south")]),
        _cam("cam_07", "Route 2: exit", 0.95, 0.8, [("cam_06", 26, "west")]),
        _cam("cam_08", "Route 2: decoy exit", 0.8, 0.95, [("cam_06", 32, "north")]),
    ],
}


def _det(eid, ts, cam, activity, conf, appearance, direction):
    return {**_hdr("detection", eid, ts), "camera_id": cam, "track_id": f"trk_{eid}", "label": "person",
            "confidence": 0.9, "bbox": None, "activity": activity, "activity_confidence": conf,
            "appearance": appearance, "direction": direction}


def _rel(eid, ts, frm, to, subj, summary, appearance, direction, activity, ev):
    return {**_hdr("relay", eid, ts), "from_camera": frm, "to_camera": to, "subject_id": subj,
            "summary": summary, "appearance": appearance, "direction": direction, "activity": activity,
            "confidence": 0.82, "expected_arrival_s": 30, "evidence_event_ids": ev}


def _ver(eid, ts, cam, subj, decision, conf, reason, ev):
    return {**_hdr("agent_verdict", eid, ts), "agent_id": f"agent_{cam}", "camera_id": cam, "subject_id": subj,
            "decision": decision, "confidence": conf, "reason": reason, "evidence_event_ids": ev}


GREY = "male, grey hoodie, dark pants"
RED = "female, red jacket, black backpack"
MESSAGES = [
    # subj_7, route 1: purse snatch at 0.74 -> ambiguous -> model. Heads north, so exit beats the decoy.
    _det("det_8f2a", 0.0, "cam_01", "purse_snatch", 0.74, GREY, "north"),
    _rel("rel_1c9d", 1.0, "cam_01", "cam_02", "subj_7", "Grabbed a bag from a person and ran north.",
         GREY, "north", "purse_snatch", ["det_8f2a"]),
    _det("det_9e11", 30.5, "cam_02", "none", None, GREY, "north"),
    _ver("ver_44b0", 31.0, "cam_02", "subj_7", "match", 0.88, "Grey hoodie and dark pants match; arrived 30s later.",
         ["rel_1c9d", "det_9e11"]),
    # subj_2, route 2: fistfight at 0.93 -> clear -> rules alert, no model call.
    # (No stabbing in the demo: no open dataset has it, and we don't stage one. See data/README.md.)
    _det("det_a100", 40.0, "cam_05", "fistfight", 0.93, RED, "east"),
    _rel("rel_a101", 41.0, "cam_05", "cam_06", "subj_2", "Punched a person repeatedly, then walked east.",
         RED, "east", "fistfight", ["det_a100"]),
    # Someone just walking -> activity "none" -> no dispatch.
    _det("det_b200", 50.0, "cam_03", "none", None, "male, blue shirt", "south"),
    _rel("rel_b201", 51.0, "cam_03", "cam_02", "subj_4", "Person walking south.", "male, blue shirt", "south",
         "none", ["det_b200"]),
    # Operator confirms the purse-snatch incident.
    {**_hdr("operator_action", "op_01", 60.0), "incident_id": "inc_1", "action": "confirm", "note": None},
]


class ScriptedBackend:
    """Stand-in for vLLM. First answer hallucinates (shows the revision loop); later answers are grounded."""

    def __init__(self):
        self.calls = 0

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        self.calls += 1
        case = json.loads(user.split("\n\n")[0].removeprefix("Case:\n"))
        if self.calls == 1:
            return {"status": "alert", "priority": "high", "recommendation": "Lock down cam_99 plaza; armed robbery",
                    "reason": "Weapon seen", "evidence_event_ids": ["det_zzzz"]}
        nxt = case["predicted_next"][0]["camera_id"] if case["predicted_next"] else case["path"][-1]["camera_id"]
        origin = case["path"][0]["camera_id"]
        return {"status": "tracking", "priority": "low",
                "recommendation": f"Send an officer toward {nxt}; check on the victim near {origin}.",
                "reason": f"Purse snatch at {origin}; subject confirmed across {len(case['path'])} camera(s).",
                "evidence_event_ids": [e["event_id"] for e in case["evidence"]]}


def _load_messages(path: Path) -> list[dict]:
    text = path.read_text().strip()
    return json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use CLARITY_LLM_* env vars instead of the scripted model")
    ap.add_argument("--cameras", type=Path, help="cameras.json (contract v0.1)")
    ap.add_argument("--messages", type=Path, help="JSON array or JSONL of v0.1 messages")
    args = ap.parse_args()

    graph = CameraGraph.load(args.cameras) if args.cameras else CameraGraph.from_config(CAMERAS)
    messages = _load_messages(args.messages) if args.messages else MESSAGES
    if args.live:
        from .llm import OpenAICompatBackend
        llm = OpenAICompatBackend.from_env()
    else:
        llm = ScriptedBackend()

    d = Dispatcher(graph, llm=llm)
    t0 = time.perf_counter()
    for msg in d.process(sorted(messages, key=lambda m: m.get("ts", 0))):
        print(json.dumps(msg))
    print("\naudit:")
    for row in d.audit:
        print(" ", json.dumps(row))
    print(f"\nstats: {dict(d.stats)}  wall={time.perf_counter() - t0:.2f}s")


if __name__ == "__main__":
    main()
