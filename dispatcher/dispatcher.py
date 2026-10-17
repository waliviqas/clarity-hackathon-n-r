"""Cascade dispatcher: rules first, model on ambiguous incidents, verifier on every model answer."""
from __future__ import annotations

import time
from collections import Counter
from typing import Iterable

from .graph import CameraGraph
from .llm import PROPOSAL_SCHEMA, SYSTEM_PROMPT, LLMBackend, build_user_message
from .models import DispatchDecision, Event, Incident, Station
from .rules import RuleConfig, gate, group_events, primary_event, severity, template_summary
from .verify import verify


class Dispatcher:
    def __init__(self, graph: CameraGraph, llm: LLMBackend | None = None,
                 stations: Iterable[Station] = (), cfg: RuleConfig = RuleConfig(),
                 max_revisions: int = 1):
        self.graph = graph
        self.llm = llm
        self.stations = list(stations)
        self.cfg = cfg
        self.max_revisions = max_revisions
        self.stats: Counter = Counter()

    def process(self, events: Iterable[Event]) -> list[DispatchDecision]:
        return [self.decide(inc) for inc in group_events(events, self.graph, self.cfg)]

    def decide(self, incident: Incident) -> DispatchDecision:
        t0 = time.perf_counter()
        verdict = gate(incident, self.cfg)
        if verdict != "ambiguous":
            out = self._from_rules(incident, verdict)
        elif self.llm is None:
            out = self._fallback(incident, ["no model configured"], calls=0)
        else:
            out = self._from_model(incident)

        if out.decision == "dispatch":
            out.station_id = self._nearest_station(out.location_camera_id)
        out.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        self.stats[out.route] += 1
        self.stats["model_calls"] += out.model_calls
        return out

    def _from_rules(self, incident: Incident, verdict: str) -> DispatchDecision:
        ev = primary_event(incident)
        loc = incident.last_seen_camera
        return DispatchDecision(
            incident_id=incident.incident_id,
            decision=verdict,
            priority=severity(ev.label),
            incident_type=ev.label,
            location_camera_id=loc,
            location_name=self.graph.name(loc),
            summary=template_summary(incident, self.graph),
            cited_event_ids=[e.event_id for e in incident.events],
            route="rules",
        )

    def _from_model(self, incident: Incident) -> DispatchDecision:
        errors: list[str] = []
        calls = 0
        for _ in range(1 + self.max_revisions):
            calls += 1
            try:
                proposal = self.llm.complete_json(
                    SYSTEM_PROMPT, build_user_message(incident, self.graph, errors), PROPOSAL_SCHEMA
                )
            except Exception as exc:  # timeout, bad JSON, server down: fail safe
                errors = [f"model call failed: {type(exc).__name__}: {exc}"]
                break
            errors = verify(proposal, incident)
            if not errors:
                loc = proposal["location_camera_id"]
                return DispatchDecision(
                    incident_id=incident.incident_id,
                    decision=proposal["decision"],
                    priority=proposal["priority"],
                    incident_type=proposal["incident_type"],
                    location_camera_id=loc,
                    location_name=self.graph.name(loc),
                    summary=proposal["summary"],
                    cited_event_ids=proposal["cited_event_ids"],
                    route="model",
                    model_calls=calls,
                )
        return self._fallback(incident, errors, calls)

    def _fallback(self, incident: Incident, errors: list[str], calls: int) -> DispatchDecision:
        """Unverified answers never trigger a dispatch; a human operator decides."""
        out = self._from_rules(incident, "monitor")
        out.route = "fallback"
        out.needs_review = True
        out.summary = "Needs operator review. " + out.summary
        out.verifier_errors = errors
        out.model_calls = calls
        return out

    def _nearest_station(self, camera_id: str) -> str | None:
        dist = self.graph.distances_from(camera_id)
        reachable = [s for s in self.stations if s.camera_id in dist]
        if not reachable:
            return None
        return min(reachable, key=lambda s: dist[s.camera_id]).station_id
