"""Cascade dispatcher over the team message schema v0.1.

Consumes detection / relay / agent_verdict / operator_action messages and emits
dispatch messages. Rules handle clear cases, the model handles ambiguous ones,
and every model answer is verified against the evidence before it is emitted.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Iterable

from .graph import CameraGraph
from .llm import PROPOSAL_SCHEMA, SYSTEM_PROMPT, LLMBackend, build_user_message
from .models import HEADER, SCHEMA_VERSION, SubjectCase
from .rules import RuleConfig, gate, path, predicted_next, template
from .verify import verify

# Fields that identify a message instance rather than its content.
_INSTANCE_FIELDS = {"event_id", "ts"}


class Dispatcher:
    def __init__(self, graph: CameraGraph, llm: LLMBackend | None = None,
                 cfg: RuleConfig = RuleConfig(), max_revisions: int = 1):
        self.graph = graph
        self.llm = llm
        self.cfg = cfg
        self.max_revisions = max_revisions
        self.cases: dict[str, SubjectCase] = {}
        self.detections: dict[str, dict] = {}
        self._waiting: dict[str, set[str]] = {}  # detection id cited before it arrived -> subject ids
        self._incident_count = 0
        self._dispatch_count = 0
        self.clock = 0.0  # latest ts seen, on the shared clock
        self.stats: Counter = Counter()
        self.audit: list[dict] = []  # per-dispatch route / model calls / verifier errors, for metrics

    def process(self, messages: Iterable[dict]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            out += self.ingest(m)
        return out

    def ingest(self, msg: dict) -> list[dict]:
        if any(k not in msg for k in HEADER) or msg["schema_version"] != SCHEMA_VERSION:
            self.stats["rejected"] += 1
            return []
        self.clock = max(self.clock, float(msg["ts"]))
        kind = msg["type"]

        if kind == "detection":
            self.detections[msg["event_id"]] = msg
            out = []
            for sid in self._waiting.pop(msg["event_id"], set()):
                self.cases[sid].events[msg["event_id"]] = msg
                out += self._evaluate(self.cases[sid])
            return out

        if kind in ("relay", "agent_verdict"):
            case = self.cases.setdefault(msg["subject_id"], SubjectCase(msg["subject_id"]))
            case.events[msg["event_id"]] = msg
            for ref in msg.get("evidence_event_ids", []):
                if ref in self.detections:
                    case.events[ref] = self.detections[ref]
                elif ref.startswith("det_"):
                    self._waiting.setdefault(ref, set()).add(case.subject_id)
            return self._evaluate(case)

        if kind == "operator_action":
            case = next((c for c in self.cases.values() if c.incident_id == msg["incident_id"]), None)
            if case is None or case.last_dispatch is None:
                self.stats["rejected"] += 1
                return []
            case.operator_action = msg["action"]
            body = {k: case.last_dispatch[k] for k in ("status", "priority", "recommendation", "reason", "evidence_event_ids")}
            body["status"] = "resolved" if msg["action"] == "dismiss" else "alert"
            body["evidence_event_ids"] = body["evidence_event_ids"] + [msg["event_id"]]
            return self._emit(case, body, case.last_dispatch["path"], case.last_dispatch["predicted_next"],
                              route="operator", calls=0, errors=[], t0=time.perf_counter())

        self.stats["ignored"] += 1
        return []

    def _evaluate(self, case: SubjectCase) -> list[dict]:
        if case.operator_action == "dismiss":
            return []
        verdict = gate(case, self.cfg)
        if verdict == "ignore":
            return []

        t0 = time.perf_counter()
        cam_path = path(case)
        pred = predicted_next(case, cam_path, self.graph, self.cfg)
        if verdict == "alert":
            body, route, calls, errors = template(case, cam_path, pred, self.graph), "rules", 0, []
        elif self.llm is None:
            body, route, calls, errors = self._fallback(case, cam_path, pred), "fallback", 0, ["no model configured"]
        else:
            body, route, calls, errors = self._from_model(case, cam_path, pred)

        if case.operator_action == "confirm":
            body["status"] = "alert"
        return self._emit(case, body, cam_path, pred, route, calls, errors, t0)

    def _from_model(self, case: SubjectCase, cam_path: list[dict], pred: list[dict]):
        known = ({p["camera_id"] for p in cam_path} | {p["camera_id"] for p in pred}
                 | {m["camera_id"] for m in case.events.values() if "camera_id" in m}
                 | {m[k] for m in case.of_type("relay") for k in ("from_camera", "to_camera")})
        errors: list[str] = []
        calls = 0
        for _ in range(1 + self.max_revisions):
            calls += 1
            try:
                proposal = self.llm.complete_json(
                    SYSTEM_PROMPT, build_user_message(case, cam_path, pred, self.graph, errors), PROPOSAL_SCHEMA
                )
            except Exception as exc:  # timeout, bad JSON, server down: fail safe
                errors = [f"model call failed: {type(exc).__name__}: {exc}"]
                break
            errors = verify(proposal, case, known)
            if not errors:
                return {k: proposal[k] for k in ("status", "priority", "recommendation", "reason", "evidence_event_ids")}, "model", calls, []
        return self._fallback(case, cam_path, pred), "fallback", calls, errors

    def _fallback(self, case: SubjectCase, cam_path: list[dict], pred: list[dict]) -> dict:
        """Unverified answers never raise an alert; keep tracking and ask the operator."""
        body = template(case, cam_path, pred, self.graph)
        body["status"] = "tracking"
        body["recommendation"] = "Operator review needed. " + body["recommendation"]
        return body

    def _emit(self, case: SubjectCase, body: dict, cam_path: list[dict], pred: list[dict],
              route: str, calls: int, errors: list[str], t0: float) -> list[dict]:
        if case.incident_id is None:
            self._incident_count += 1
            case.incident_id = f"inc_{self._incident_count}"
        msg = {
            "type": "dispatch",
            "schema_version": SCHEMA_VERSION,
            "event_id": f"dsp_{self._dispatch_count + 1:02d}",
            "ts": self.clock,
            "incident_id": case.incident_id,
            "subject_id": case.subject_id,
            "status": body["status"],
            "priority": body["priority"],
            "path": cam_path,
            "predicted_next": pred,
            "recommendation": body["recommendation"],
            "reason": body["reason"],
            "evidence_event_ids": body["evidence_event_ids"],
            "requires_human_confirm": case.operator_action is None,
        }
        self.stats["model_calls"] += calls
        prev = case.last_dispatch
        if prev and {k: v for k, v in prev.items() if k not in _INSTANCE_FIELDS} == \
                {k: v for k, v in msg.items() if k not in _INSTANCE_FIELDS}:
            self.stats["unchanged"] += 1
            return []
        self._dispatch_count += 1
        case.last_dispatch = msg
        self.stats[route] += 1
        self.audit.append({
            "dispatch_event_id": msg["event_id"], "incident_id": case.incident_id, "route": route,
            "model_calls": calls, "verifier_errors": errors,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        })
        return [msg]
