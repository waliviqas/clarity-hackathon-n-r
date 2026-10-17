"""Data contracts for the dispatcher.

Input comes from crime detection (#2) as `Event`s; output goes to the
dashboard (#6) / police as `DispatchDecision`s.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Decision = Literal["dispatch", "monitor", "dismiss"]
Route = Literal["rules", "model", "fallback"]


@dataclass(frozen=True)
class Camera:
    camera_id: str
    name: str
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class Station:
    station_id: str
    camera_id: str  # camera node the station sits closest to


@dataclass(frozen=True)
class Event:
    """One detection emitted by the crime-detection stage."""

    event_id: str
    camera_id: str
    timestamp: float  # unix seconds
    label: str  # e.g. "weapon", "fight", "loitering"
    confidence: float  # 0..1
    description: str = ""  # optional caption from the vision model


@dataclass
class Incident:
    """Events grouped as one real-world situation (same time window, nearby cameras)."""

    incident_id: str
    events: list[Event]

    @property
    def camera_ids(self) -> list[str]:
        return list(dict.fromkeys(e.camera_id for e in self.events))

    @property
    def labels(self) -> set[str]:
        return {e.label for e in self.events}

    @property
    def start(self) -> float:
        return min(e.timestamp for e in self.events)

    @property
    def end(self) -> float:
        return max(e.timestamp for e in self.events)

    @property
    def last_seen_camera(self) -> str:
        return max(self.events, key=lambda e: e.timestamp).camera_id


@dataclass
class DispatchDecision:
    incident_id: str
    decision: Decision
    priority: int  # 1 (low) .. 5 (critical)
    incident_type: str
    location_camera_id: str
    location_name: str
    summary: str
    cited_event_ids: list[str]
    route: Route  # who made the call
    needs_review: bool = False
    station_id: str | None = None
    verifier_errors: list[str] = field(default_factory=list)
    model_calls: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
