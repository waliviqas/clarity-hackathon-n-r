"""Deterministic layer: severity, path, next-camera prediction, and the cascade gate.

Anything rules can decide confidently never reaches the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .graph import CameraGraph
from .models import SubjectCase

# Keyed on detection.activity. Vocabulary to be confirmed with the detector owner.
ACTIVITY_SEVERITY = {
    "weapon": 5,
    "shooting": 5,
    "assault": 4,
    "fight": 4,
    "abandon_package": 4,
    "vehicle_crash": 4,
    "fire": 4,
    "break_in": 3,
    "theft": 3,
    "fall": 3,
    "vandalism": 2,
    "trespass": 2,
    "loitering": 1,
}
UNKNOWN_SEVERITY = 2

Gate = Literal["alert", "ignore", "ambiguous"]


def activity_severity(activity: str | None) -> int:
    if not activity:
        return 0
    return ACTIVITY_SEVERITY.get(activity, UNKNOWN_SEVERITY)


def priority_for(sev: int) -> str:
    return "high" if sev >= 4 else "medium" if sev >= 3 else "low"


@dataclass(frozen=True)
class RuleConfig:
    alert_min_severity: int = 4
    alert_min_confidence: float = 0.85
    ignore_max_severity: int = 1
    ignore_max_confidence: float = 0.40
    max_predictions: int = 3
    pending_relay_weight: float = 3.0  # a camera we already relayed to is the likeliest next stop


def concerning(case: SubjectCase) -> list[dict]:
    return [d for d in case.of_type("detection") if d.get("activity")]


def path(case: SubjectCase) -> list[dict]:
    """Cameras the subject was confirmed at: relay origins + `match` verdicts, earliest ts per camera."""
    first: dict[str, float] = {}
    for r in case.of_type("relay"):
        seen = [case.events[i]["ts"] for i in r.get("evidence_event_ids", [])
                if i in case.events and case.events[i]["type"] == "detection"
                and case.events[i]["camera_id"] == r["from_camera"]]
        ts = min(seen, default=r["ts"])
        first[r["from_camera"]] = min(ts, first.get(r["from_camera"], ts))
    for v in case.of_type("agent_verdict"):
        if v["decision"] == "match":
            first[v["camera_id"]] = min(v["ts"], first.get(v["camera_id"], v["ts"]))
    return [{"camera_id": c, "ts": t} for c, t in sorted(first.items(), key=lambda kv: kv[1])]


def predicted_next(case: SubjectCase, cam_path: list[dict], graph: CameraGraph, cfg: RuleConfig) -> list[dict]:
    if not cam_path:
        return []
    visited = {p["camera_id"] for p in cam_path}
    answered = {v["camera_id"] for v in case.of_type("agent_verdict")}
    pending = {r["to_camera"] for r in case.of_type("relay")} - answered - visited

    weights = {c: 1.0 for c in graph.neighbors(cam_path[-1]["camera_id"]) if c not in visited}
    for c in pending:
        weights[c] = cfg.pending_relay_weight
    total = sum(weights.values())
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))[: cfg.max_predictions]
    return [{"camera_id": c, "probability": round(w / total, 2)} for c, w in ranked]


def gate(case: SubjectCase, cfg: RuleConfig) -> Gate:
    dets = concerning(case)
    if not dets:
        return "ignore"
    sev = max(activity_severity(d["activity"]) for d in dets)
    confs = [d.get("activity_confidence") or 0.0 for d in dets]

    # High-severity activity is never auto-ignored, however weak the detection.
    if sev < cfg.alert_min_severity and (sev <= cfg.ignore_max_severity or max(confs) < cfg.ignore_max_confidence):
        return "ignore"
    uncertain = any(v["decision"] == "uncertain" for v in case.of_type("agent_verdict"))
    if (sev >= cfg.alert_min_severity and len({d["activity"] for d in dets}) == 1
            and min(confs) >= cfg.alert_min_confidence and not uncertain):
        return "alert"
    return "ambiguous"


def template(case: SubjectCase, cam_path: list[dict], pred: list[dict], graph: CameraGraph) -> dict:
    """Rules-written dispatch body for cases that don't need the model."""
    top = max(concerning(case), key=lambda d: (activity_severity(d["activity"]), d.get("activity_confidence") or 0))
    what = top["activity"].replace("_", " ")
    target = pred[0]["camera_id"] if pred else cam_path[-1]["camera_id"] if cam_path else top["camera_id"]
    return {
        "status": "alert",
        "priority": priority_for(activity_severity(top["activity"])),
        "recommendation": f"Send officer to {graph.name(target)} ({target}); {what} at {graph.name(top['camera_id'])} ({top['camera_id']})",
        "reason": f"{what} detected (conf {top.get('activity_confidence') or 0:.2f}); subject confirmed at {len(cam_path)} camera(s)",
        "evidence_event_ids": [m["event_id"] for m in sorted(case.events.values(), key=lambda m: m["ts"])],
    }
