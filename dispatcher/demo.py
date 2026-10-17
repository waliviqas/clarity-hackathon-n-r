"""Run the dispatcher on a small synthetic scenario.

    python -m dispatcher.demo          # scripted model, no GPU needed
    python -m dispatcher.demo --live   # real model via CLARITY_LLM_* env vars (vLLM)
"""
from __future__ import annotations

import argparse
import json

from .dispatcher import Dispatcher
from .graph import CameraGraph
from .models import Camera, Event, Station

T = 1_760_000_000.0  # arbitrary scenario start

CAMERAS = [
    Camera("cam-1", "Main St & 1st"),
    Camera("cam-2", "Main St & 2nd"),
    Camera("cam-3", "Transit Plaza"),
    Camera("cam-4", "Library Entrance"),
    Camera("cam-5", "Parking Deck B"),
    Camera("cam-6", "North Gate"),
]
EDGES = [("cam-1", "cam-2", 1), ("cam-2", "cam-3", 1), ("cam-3", "cam-4", 1),
         ("cam-4", "cam-5", 1), ("cam-5", "cam-6", 1)]
STATIONS = [Station("precinct-central", "cam-2"), Station("precinct-north", "cam-6")]

EVENTS = [
    # Clear case: consistent high-confidence weapon detections -> rules dispatch.
    Event("e1", "cam-1", T + 0, "weapon", 0.93, "person holding a handgun"),
    Event("e2", "cam-2", T + 12, "weapon", 0.91, "same person moving east"),
    # Clear case: loitering only -> rules dismiss.
    Event("e3", "cam-6", T + 300, "loitering", 0.88, "person standing by gate"),
    # Ambiguous: conflicting labels, mid confidence -> model.
    Event("e4", "cam-4", T + 600, "fight", 0.62, "two people shoving"),
    Event("e5", "cam-5", T + 630, "fall", 0.71, "person on the ground"),
]


class ScriptedBackend:
    """Stand-in for vLLM: first answer hallucinates, second is grounded (shows the revision loop)."""

    def __init__(self):
        self.calls = 0

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"decision": "dispatch", "priority": 5, "incident_type": "weapon",
                    "location_camera_id": "cam-5", "summary": "Armed assault in parking deck.",
                    "cited_event_ids": ["e4", "e9"]}
        return {"decision": "dispatch", "priority": 4, "incident_type": "fight",
                "location_camera_id": "cam-5",
                "summary": "Shoving at Library Entrance, then a person down in Parking Deck B. Possible assault with injury.",
                "cited_event_ids": ["e4", "e5"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use CLARITY_LLM_* env vars instead of the scripted model")
    args = ap.parse_args()

    if args.live:
        from .llm import OpenAICompatBackend
        llm = OpenAICompatBackend.from_env()
    else:
        llm = ScriptedBackend()

    d = Dispatcher(CameraGraph(CAMERAS, EDGES), llm=llm, stations=STATIONS)
    for decision in d.process(EVENTS):
        print(json.dumps(decision.to_dict(), indent=2))
    total = d.stats["rules"] + d.stats["model"] + d.stats["fallback"]
    print(f"\nincidents={total} rules={d.stats['rules']} model={d.stats['model']} "
          f"fallback={d.stats['fallback']} model_calls={d.stats['model_calls']}")


if __name__ == "__main__":
    main()
