"""Cascade dispatcher over the team message schema v0.1.

Consumes detection / relay / agent_verdict / operator_action messages and emits
dispatch messages. Rules handle clear cases, the model handles ambiguous ones,
and every model answer is verified against the evidence before it is emitted.
"""
from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from .graph import CameraGraph
from .guidance import guidance_for, with_guidance
from .llm import PROPOSAL_SCHEMA, SYSTEM_PROMPT, LLMBackend, build_user_message, intercept_camera
from .models import HEADER, SCHEMA_VERSION, SubjectCase
from .rules import (ACTIVITY_ALIASES, RuleConfig, confirmed_match, gate, incident_type, normalize_activity, path,
                    predicted_next, subject_appearance, subject_direction, template)
from .verify import MAX_RECOMMENDATION, verify

# Fields that identify a message instance rather than its content.
_INSTANCE_FIELDS = {"event_id", "ts"}

# Wali's graph interface (contracts v0.1): predict_next(camera_id, direction) -> [{"camera_id", "probability"}]
PredictNext = Callable[[str, "str | None"], list[dict]]


class Dispatcher:
    def __init__(self, graph: CameraGraph, llm: LLMBackend | None = None,
                 cfg: RuleConfig = RuleConfig(), max_revisions: int = 1,
                 predict_next: PredictNext | None = None, max_parallel: int = 8, guidance: bool = True,
                 run_tag: str = "", run_id: str | None = None):
        self.graph = graph
        self.llm = llm
        # IDs become inc_<tag>_N / dsp_<tag>_NN so a restart or another producer (e.g. fake_scenario's
        # stand-in dispatches) can't collide with ours on the bus. The runner always sets a tag.
        self._id_prefix = f"{run_tag}_" if run_tag else ""
        self.run_id = run_id
        self.guidance = guidance  # append fixed procedure lines (dispatcher/guidance.py)
        self.predict_next = predict_next  # Wali's graph; falls back to rules.predicted_next when absent
        self.cfg = cfg
        self.max_revisions = max_revisions
        self.max_parallel = max_parallel  # concurrent model calls; keep <= vLLM --max-num-seqs (16)
        self.cases: dict[str, SubjectCase] = {}
        self.detections: dict[str, dict] = {}
        self._waiting: dict[str, set[str]] = {}  # detection id cited before it arrived -> subject ids
        self._dirty: dict[str, None] = {}  # subjects to re-evaluate at the next flush (ordered set)
        self._seen: set[str] = set()  # event_ids already taken in
        self._incident_count = 0
        self._dispatch_count = 0
        self.clock = 0.0  # latest ts seen, on the shared clock
        self.stats: Counter = Counter()
        self.audit: list[dict] = []  # per-dispatch route / model calls / verifier errors, for metrics

    def process(self, messages: Iterable[dict]) -> list[dict]:
        """Take in a batch of messages (e.g. one bus poll), then evaluate every incident it touched once.

        Model calls for different incidents run in parallel so vLLM can batch them; everything else is
        sequential, and dispatches come out in a deterministic order. An operator_action first flushes
        pending evaluations, so it always applies to the latest state of its incident.
        """
        out: list[dict] = []
        for msg in messages:
            if self._accept(msg) == "operator_action":
                out += self._flush()
                out += self._operator(msg)
        return out + self._flush()

    def ingest(self, msg: dict) -> list[dict]:
        return self.process([msg])

    def _accept(self, msg: dict) -> str | None:
        """Validate and store one message; mark the subjects it touches for evaluation. Returns its type."""
        if any(k not in msg for k in HEADER) or msg["schema_version"] != SCHEMA_VERSION:
            self.stats["rejected"] += 1
            return None
        if msg["event_id"] in self._seen:  # the bus is polled with a lookback, so repeats are normal
            self.stats["duplicate"] += 1
            return None
        self._seen.add(msg["event_id"])
        self.clock = max(self.clock, float(msg["ts"]))
        kind = msg["type"]

        if kind in ("detection", "relay") and msg.get("activity") in ACTIVITY_ALIASES:
            msg = {**msg, "activity": normalize_activity(msg["activity"])}  # Wali's label names -> contract's
        if kind == "detection":
            self.detections[msg["event_id"]] = msg
            for sid in self._waiting.pop(msg["event_id"], set()):
                self.cases[sid].events[msg["event_id"]] = msg
                self._dirty[sid] = None
        elif kind in ("relay", "agent_verdict"):
            case = self.cases.setdefault(msg["subject_id"], SubjectCase(msg["subject_id"]))
            case.events[msg["event_id"]] = msg
            for ref in msg.get("evidence_event_ids", []):
                if ref in self.detections:
                    case.events[ref] = self.detections[ref]
                elif ref.startswith("det_"):
                    self._waiting.setdefault(ref, set()).add(case.subject_id)
            self._dirty[case.subject_id] = None
        elif kind != "operator_action":
            self.stats["ignored"] += 1
        return kind

    def _operator(self, msg: dict) -> list[dict]:
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

    def _flush(self) -> list[dict]:
        """Evaluate every subject touched since the last flush; model calls run concurrently."""
        subjects, self._dirty = list(self._dirty), {}
        plans = []
        for sid in subjects:
            case = self.cases[sid]
            if case.operator_action == "dismiss":
                continue
            verdict = gate(case, self.cfg)
            if verdict == "ignore":
                continue
            cam_path = path(case)
            plans.append({"case": case, "verdict": verdict, "path": cam_path,
                          "pred": self._predict(case, cam_path), "t0": time.perf_counter()})

        needs_model = [p for p in plans if p["verdict"] == "ambiguous" and self.llm is not None]
        ask = lambda p: self._from_model(p["case"], p["path"], p["pred"])  # noqa: E731
        if len(needs_model) > 1:
            with ThreadPoolExecutor(max_workers=min(self.max_parallel, len(needs_model))) as pool:
                results = list(pool.map(ask, needs_model))
        else:
            results = [ask(p) for p in needs_model]
        for p, result in zip(needs_model, results):
            p["result"] = result
        self.stats["max_parallel_model_calls"] = max(self.stats["max_parallel_model_calls"], len(needs_model))

        out: list[dict] = []
        for p in plans:
            case, cam_path, pred = p["case"], p["path"], p["pred"]
            if "result" in p:
                body, route, calls, errors = p["result"]
            elif p["verdict"] == "alert":
                body, route, calls, errors = template(case, cam_path, pred, self.graph), "rules", 0, []
            else:
                body, route, calls, errors = self._fallback(case, cam_path, pred), "fallback", 0, ["no model configured"]
            if case.operator_action == "confirm":
                body["status"] = "alert"
            elif body["status"] != "alert" and incident_type(case) != "none" and confirmed_match(case):
                # A camera agent confirmed the subject downstream of a real incident: ask the operator to decide,
                # whatever the route (rules, model, or fallback). Priority stays capped by the activity.
                body["status"] = "alert"
            out += self._emit(case, body, cam_path, pred, route, calls, errors, p["t0"])
        return out

    def _predict(self, case: SubjectCase, cam_path: list[dict]) -> list[dict]:
        if self.predict_next and cam_path:
            try:
                last = cam_path[-1]["camera_id"]
                pred = self.predict_next(last, subject_direction(case, last))
                valid = [{"camera_id": p["camera_id"], "probability": float(p["probability"])}
                         for p in pred if p.get("camera_id") in self.graph.cameras]
                return valid[: self.cfg.max_predictions]
            except Exception:  # graph bug must not stop dispatching
                self.stats["predict_next_errors"] += 1
        return predicted_next(case, cam_path, self.graph, self.cfg)

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
            except ValueError as exc:  # unparseable answer (e.g. cut off at max_tokens): worth one more try
                errors = [f"your previous answer was not valid JSON ({exc}); answer with compact JSON only"]
                continue
            except Exception as exc:  # timeout, server down: fail safe
                errors = [f"model call failed: {type(exc).__name__}: {exc}"]
                break
            room = MAX_RECOMMENDATION - (len(guidance_for(incident_type(case))) + 1 if self.guidance else 0)
            errors = verify(proposal, case, known, intercept_camera(cam_path, pred), max_recommendation=room)
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
            case.incident_id = f"inc_{self._id_prefix}{self._incident_count}"
        recommendation = body["recommendation"]
        if self.guidance and route != "operator":  # operator updates reuse the already-guided text
            recommendation = with_guidance(recommendation, incident_type(case))
        msg = {
            "type": "dispatch",
            "schema_version": SCHEMA_VERSION,
            "event_id": f"dsp_{self._id_prefix}{self._dispatch_count + 1:02d}",
            "ts": self.clock,
            "source": "dispatcher",
            "incident_id": case.incident_id,
            "subject_id": case.subject_id,
            "incident_type": incident_type(case),
            "subject_appearance": subject_appearance(case),
            "status": body["status"],
            "priority": body["priority"],
            "path": cam_path,
            "predicted_next": pred,
            "recommendation": recommendation,
            "reason": body["reason"],
            "evidence_event_ids": body["evidence_event_ids"],
            "requires_human_confirm": case.operator_action is None,
        }
        if self.run_id:
            msg["run_id"] = self.run_id
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
