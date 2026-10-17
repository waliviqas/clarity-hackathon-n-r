"""Deterministic layer: severity, incident grouping, and the cascade gate.

Anything rules can decide confidently never reaches the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .graph import CameraGraph
from .models import Event, Incident

SEVERITY = {
    "weapon": 5,
    "shooting": 5,
    "assault": 4,
    "fight": 4,
    "vehicle_crash": 4,
    "fire": 4,
    "break_in": 3,
    "theft": 3,
    "medical": 3,
    "fall": 3,
    "vandalism": 2,
    "trespass": 2,
    "loitering": 1,
}
UNKNOWN_SEVERITY = 2

Gate = Literal["dispatch", "dismiss", "ambiguous"]


def severity(label: str) -> int:
    return SEVERITY.get(label, UNKNOWN_SEVERITY)


@dataclass(frozen=True)
class RuleConfig:
    group_window_s: float = 60.0  # max gap between events in one incident
    group_max_distance: float = 2.0  # max graph distance between their cameras
    dispatch_min_severity: int = 4
    dispatch_min_confidence: float = 0.85
    dismiss_max_severity: int = 1
    dismiss_max_confidence: float = 0.40


def group_events(events: Iterable[Event], graph: CameraGraph, cfg: RuleConfig) -> list[Incident]:
    """Greedy grouping: an event joins the first incident with a recent event on a nearby camera."""
    incidents: list[Incident] = []
    for ev in sorted(events, key=lambda e: e.timestamp):
        near = graph.distances_from(ev.camera_id)
        for inc in incidents:
            if ev.timestamp - inc.end > cfg.group_window_s:
                continue
            if any(near.get(c, float("inf")) <= cfg.group_max_distance for c in inc.camera_ids):
                inc.events.append(ev)
                break
        else:
            incidents.append(Incident(f"inc-{ev.event_id}", [ev]))
    return incidents


def gate(incident: Incident, cfg: RuleConfig) -> Gate:
    sev = max(severity(label) for label in incident.labels)
    confs = [e.confidence for e in incident.events]

    # High-severity incidents are never auto-dismissed, however weak the detection.
    if sev < cfg.dispatch_min_severity and (
        sev <= cfg.dismiss_max_severity or max(confs) < cfg.dismiss_max_confidence
    ):
        return "dismiss"
    if (
        sev >= cfg.dispatch_min_severity
        and len(incident.labels) == 1
        and min(confs) >= cfg.dispatch_min_confidence
    ):
        return "dispatch"
    return "ambiguous"


def primary_event(incident: Incident) -> Event:
    return max(incident.events, key=lambda e: (severity(e.label), e.confidence))


def template_summary(incident: Incident, graph: CameraGraph) -> str:
    ev = primary_event(incident)
    n, k = len(incident.events), len(incident.camera_ids)
    return (
        f"{ev.label.replace('_', ' ')} detected (conf {ev.confidence:.2f}); "
        f"{n} detection(s) across {k} camera(s) over {incident.end - incident.start:.0f}s; "
        f"last seen at {graph.name(incident.last_seen_camera)}."
    )
