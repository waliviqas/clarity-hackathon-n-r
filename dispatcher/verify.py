"""Grounding check: every claim in a model proposal must be backed by the incident's events."""
from __future__ import annotations

from .models import Incident
from .rules import severity

REQUIRED = ("decision", "priority", "incident_type", "location_camera_id", "summary", "cited_event_ids")


def verify(proposal: dict, incident: Incident) -> list[str]:
    missing = [k for k in REQUIRED if k not in proposal]
    if missing:
        return [f"missing fields: {', '.join(missing)}"]

    errors: list[str] = []
    by_id = {e.event_id: e for e in incident.events}
    cited = proposal["cited_event_ids"]

    unknown = [i for i in cited if i not in by_id]
    if unknown:
        errors.append(f"cited event ids not in this incident: {unknown}")
    if proposal["location_camera_id"] not in incident.camera_ids:
        errors.append(
            f"location_camera_id {proposal['location_camera_id']!r} is not one of {incident.camera_ids}"
        )

    if proposal["decision"] == "dispatch":
        cited_events = [by_id[i] for i in cited if i in by_id]
        if not cited_events:
            errors.append("a dispatch must cite at least one valid event")
        else:
            labels = {e.label for e in cited_events}
            if proposal["incident_type"] not in labels:
                errors.append(
                    f"incident_type {proposal['incident_type']!r} not supported by cited events {sorted(labels)}"
                )
            cap = max(severity(lbl) for lbl in labels)
            if proposal["priority"] > cap:
                errors.append(f"priority {proposal['priority']} exceeds evidence severity {cap}")
    return errors
