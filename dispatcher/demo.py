"""Run the dispatcher on schema v0.1 messages.

    python -m dispatcher.demo                                   # built-in scenario, scripted model
    python -m dispatcher.demo --live                            # real model via CLARITY_LLM_* env vars (vLLM)
    python -m dispatcher.demo --cameras cameras.json --messages run.jsonl [--live]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dispatcher import Dispatcher
from .graph import CameraGraph


def _hdr(kind: str, eid: str, ts: float) -> dict:
    return {"type": kind, "schema_version": "0.1", "event_id": eid, "ts": ts}


CAMERAS = [
    {"camera_id": "cam_01", "name": "Main St & 1st", "position": {"x": 0.10, "y": 0.80},
     "neighbors": [{"camera_id": "cam_02", "travel_time_s": 30}]},
    {"camera_id": "cam_02", "name": "Main St & 2nd", "position": {"x": 0.25, "y": 0.80},
     "neighbors": [{"camera_id": "cam_03", "travel_time_s": 45}]},
    {"camera_id": "cam_03", "name": "North entrance", "position": {"x": 0.42, "y": 0.18},
     "neighbors": [{"camera_id": "cam_05", "travel_time_s": 40}]},
    {"camera_id": "cam_05", "name": "Library steps", "position": {"x": 0.50, "y": 0.10},
     "neighbors": [{"camera_id": "cam_06", "travel_time_s": 35}, {"camera_id": "cam_08", "travel_time_s": 50}]},
    {"camera_id": "cam_06", "name": "Parking deck B", "position": {"x": 0.70, "y": 0.15}, "neighbors": []},
    {"camera_id": "cam_08", "name": "North gate", "position": {"x": 0.55, "y": 0.02}, "neighbors": []},
]

MESSAGES = [
    # subj_7: the schema doc's example. Package at 0.74 confidence -> ambiguous -> model.
    {**_hdr("detection", "det_8f2a", 1734.2), "camera_id": "cam_03", "track_id": "trk_cam03_12",
     "label": "person", "confidence": 0.91, "bbox": [0.31, 0.22, 0.08, 0.35],
     "activity": "abandon_package", "activity_confidence": 0.74, "appearance_id": "app_8f2a"},
    {**_hdr("relay", "rel_1c9d", 1736.0), "from_camera": "cam_03", "to_camera": "cam_05", "subject_id": "subj_7",
     "summary": "Person in red jacket left package near bench, walking north", "confidence": 0.82,
     "expected_arrival_s": 40, "evidence_event_ids": ["det_8f2a"]},
    {**_hdr("detection", "det_9e11", 1775.9), "camera_id": "cam_05", "track_id": "trk_cam05_3",
     "label": "person", "confidence": 0.88, "bbox": [0.40, 0.30, 0.07, 0.33],
     "activity": None, "activity_confidence": None, "appearance_id": "app_9e11"},
    {**_hdr("agent_verdict", "ver_44b0", 1776.5), "agent_id": "agent_cam05", "camera_id": "cam_05",
     "subject_id": "subj_7", "decision": "match", "confidence": 0.88,
     "reason": "Same jacket and build, arrived 41s after cam_03 relay", "evidence_event_ids": ["rel_1c9d", "det_9e11"]},
    # subj_9: clear high-confidence weapon -> rules alert, no model call.
    {**_hdr("detection", "det_a100", 1800.0), "camera_id": "cam_01", "track_id": "trk_cam01_4",
     "label": "person", "confidence": 0.95, "bbox": [0.5, 0.4, 0.1, 0.3],
     "activity": "weapon", "activity_confidence": 0.93, "appearance_id": "app_a100"},
    {**_hdr("relay", "rel_a101", 1801.0), "from_camera": "cam_01", "to_camera": "cam_02", "subject_id": "subj_9",
     "summary": "Person holding handgun walking east", "confidence": 0.9, "expected_arrival_s": 30,
     "evidence_event_ids": ["det_a100"]},
    # subj_4: just walking -> ignored, no dispatch.
    {**_hdr("detection", "det_b200", 1810.0), "camera_id": "cam_06", "track_id": "trk_cam06_1",
     "label": "person", "confidence": 0.9, "bbox": [0.2, 0.2, 0.1, 0.3],
     "activity": None, "activity_confidence": None, "appearance_id": "app_b200"},
    {**_hdr("relay", "rel_b201", 1811.0), "from_camera": "cam_06", "to_camera": "cam_05", "subject_id": "subj_4",
     "summary": "Person walking west", "confidence": 0.7, "expected_arrival_s": 35, "evidence_event_ids": ["det_b200"]},
    # Operator confirms the subj_7 incident.
    {**_hdr("operator_action", "op_01", 1790.0), "incident_id": "inc_1", "action": "confirm"},
]


class ScriptedBackend:
    """Stand-in for vLLM. First answer hallucinates (shows the revision loop); later answers are grounded."""

    def __init__(self):
        self.calls = 0

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        self.calls += 1
        case = json.loads(user.split("\n\n")[0].removeprefix("Case:\n"))
        if self.calls == 1:
            return {"status": "alert", "priority": "high",
                    "recommendation": "Evacuate cam_99 plaza; bomb confirmed",
                    "reason": "Explosive device seen", "evidence_event_ids": ["det_zzzz"]}
        ids = [e["event_id"] for e in case["evidence"]]
        nxt = case["predicted_next"][0]["camera_id"] if case["predicted_next"] else case["path"][-1]["camera_id"]
        origin = case["path"][0]["camera_id"]
        return {"status": "tracking", "priority": "high",
                "recommendation": f"Send officer to {nxt} area; secure package at {origin}",
                "reason": f"Abandoned package + subject confirmed moving across {len(case['path'])} camera(s)",
                "evidence_event_ids": ids}


def _load_messages(path: Path) -> list[dict]:
    text = path.read_text().strip()
    return json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use CLARITY_LLM_* env vars instead of the scripted model")
    ap.add_argument("--cameras", type=Path, help="cameras.json")
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
    for msg in d.process(sorted(messages, key=lambda m: m.get("ts", 0))):
        print(json.dumps(msg))
    print("\naudit:")
    for row in d.audit:
        print(" ", json.dumps(row))
    print(f"\nstats: {dict(d.stats)}")


if __name__ == "__main__":
    main()
