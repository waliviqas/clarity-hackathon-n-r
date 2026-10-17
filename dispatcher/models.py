"""Dispatcher-side types for the team message schema v0.1.

Wire messages (detection, relay, agent_verdict, operator_action in; dispatch out)
stay plain dicts so they match the shared JSON exactly. Swap these constants for
the shared definition module once it lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SCHEMA_VERSION = "0.1"
HEADER = ("type", "schema_version", "event_id", "ts")

Status = Literal["tracking", "alert", "resolved"]
Priority = Literal["low", "medium", "high"]
PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Camera:
    camera_id: str
    name: str
    x: float | None = None
    y: float | None = None


@dataclass
class SubjectCase:
    """Everything the dispatcher knows about one subject, keyed by event_id."""

    subject_id: str
    incident_id: str | None = None
    events: dict[str, dict] = field(default_factory=dict)  # detections, relays, verdicts
    operator_action: str | None = None  # "confirm" | "dismiss"
    last_dispatch: dict | None = None

    def of_type(self, kind: str) -> list[dict]:
        return sorted((m for m in self.events.values() if m["type"] == kind), key=lambda m: m["ts"])
