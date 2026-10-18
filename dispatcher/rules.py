"""Deterministic layer: severity, path, next-camera prediction, and the cascade gate.

Anything rules can decide confidently never reaches the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .graph import CameraGraph
from .models import SubjectCase

# Keyed on detection.activity, the closed enum from contracts v0.1 (what Wali's vision model detects).
# Priorities agreed by the team (Sat Oct 17 evening): stabbing high, fistfight (assault) medium, purse_snatch low.
ACTIVITY_SEVERITY = {
    "stabbing": 5,      # -> high; the only activity rules can auto-alert on (alert_min_severity = 4)
    "fistfight": 3,     # -> medium
    "purse_snatch": 2,  # -> low
    "none": 0,
}
NO_ACTIVITY = (None, "", "none")

# Wali's spotter labels (labels.csv: stabbing / assault / stealing / none) -> contract v0.1 names.
# If the team renames the contract enum to Wali's names, invert this mapping (and the keys above).
ACTIVITY_ALIASES = {"assault": "fistfight", "stealing": "purse_snatch"}


def normalize_activity(activity):
    return ACTIVITY_ALIASES.get(activity, activity)
UNKNOWN_SEVERITY = 2  # an activity outside the enum: not trusted for auto-alert, not ignored either

Gate = Literal["alert", "ignore", "ambiguous"]


def activity_severity(activity: str | None) -> int:
    if activity in NO_ACTIVITY:
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
    heading_weight: float = 3.0  # a neighbor in the subject's direction of travel (exit vs decoy)


def concerning(case: SubjectCase) -> list[dict]:
    return [d for d in case.of_type("detection") if d.get("activity") not in NO_ACTIVITY]


def path(case: SubjectCase) -> list[dict]:
    """Cameras the subject was confirmed at: relay origins + `match` verdicts, earliest sighting per camera.

    Each point carries the event_id that proves it (the origin detection, or the verdict).
    """
    first: dict[str, tuple[float, str]] = {}

    def see(cam: str, ts: float, eid: str) -> None:
        if cam not in first or ts < first[cam][0]:
            first[cam] = (ts, eid)

    for r in case.of_type("relay"):
        origin = [case.events[i] for i in r.get("evidence_event_ids", [])
                  if i in case.events and case.events[i]["type"] == "detection"
                  and case.events[i]["camera_id"] == r["from_camera"]]
        first_seen = min(origin, key=lambda d: d["ts"], default=r)
        see(r["from_camera"], first_seen["ts"], first_seen["event_id"])
    for v in case.of_type("agent_verdict"):
        if v["decision"] == "match":
            see(v["camera_id"], v["ts"], v["event_id"])
    return [{"camera_id": c, "ts": ts, "event_id": eid}
            for c, (ts, eid) in sorted(first.items(), key=lambda kv: kv[1][0])]


def incident_type(case: SubjectCase) -> str:
    """Most severe activity seen for the subject; a relay's `activity` covers a detection not received yet."""
    dets = concerning(case)
    if dets:
        return max(dets, key=lambda d: (activity_severity(d["activity"]), d.get("activity_confidence") or 0))["activity"]
    acts = [r["activity"] for r in case.of_type("relay") if r.get("activity") not in NO_ACTIVITY]
    return max(acts, key=activity_severity, default="none")


def _latest(case: SubjectCase, field: str, skip: tuple = (None, "")) -> str | None:
    msgs = [m for m in case.events.values() if m["type"] in ("relay", "detection") and m.get(field) not in skip]
    return max(msgs, key=lambda m: m["ts"])[field] if msgs else None


def subject_appearance(case: SubjectCase) -> str | None:
    return _latest(case, "appearance")


def subject_direction(case: SubjectCase) -> str | None:
    """Observed heading: detections first. A relay's direction is the edge it was sent along, and an agent
    relays to every neighbor (exit and decoy), so relays only count when no detection has a direction."""
    skip = (None, "", "unknown")
    seen = [d for d in case.of_type("detection") if d.get("direction") not in skip]
    if seen:
        return seen[-1]["direction"]
    return _latest(case, "direction", skip)


def predicted_next(case: SubjectCase, cam_path: list[dict], graph: CameraGraph, cfg: RuleConfig) -> list[dict]:
    if not cam_path:
        return []
    visited = {p["camera_id"] for p in cam_path}
    answered = {v["camera_id"] for v in case.of_type("agent_verdict")}
    last, heading = cam_path[-1]["camera_id"], subject_direction(case)
    # Only relays sent from where the subject was last confirmed: once they've moved on, older relays are stale.
    pending = {r["to_camera"] for r in case.of_type("relay") if r["from_camera"] == last} - answered - visited

    weights = {}
    for c in set(graph.neighbors(last)) | pending:
        if c in visited:
            continue
        w = 1.0
        if heading and graph.direction(last, c) == heading:
            w *= cfg.heading_weight  # signals combine: relayed-to AND in the direction of travel beats either alone
        if c in pending:
            w *= cfg.pending_relay_weight
        weights[c] = w
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
