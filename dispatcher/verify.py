"""Grounding check: every claim in a model proposal must be backed by the subject's evidence."""
from __future__ import annotations

import re

from .models import PRIORITY_RANK, SubjectCase
from .rules import activity_severity, priority_for

REQUIRED = ("status", "priority", "recommendation", "reason", "evidence_event_ids")
CAMERA_REF = re.compile(r"\bcam_\w+")


def supported_severity(cited: list[str], case: SubjectCase) -> int:
    """Max activity severity among cited detections, including detections cited by cited relays/verdicts."""
    seen, stack, sev = set(), list(cited), 0
    while stack:
        eid = stack.pop()
        if eid in seen or eid not in case.events:
            continue
        seen.add(eid)
        msg = case.events[eid]
        if msg["type"] == "detection":
            sev = max(sev, activity_severity(msg.get("activity")))
        stack.extend(msg.get("evidence_event_ids", []))
    return sev


MAX_RECOMMENDATION, MAX_REASON = 300, 500  # dispatch contract v0.1


def verify(proposal: dict, case: SubjectCase, known_cameras: set[str], intercept: str | None = None) -> list[str]:
    missing = [k for k in REQUIRED if k not in proposal]
    if missing:
        return [f"missing fields: {', '.join(missing)}"]

    errors: list[str] = []
    cited = proposal["evidence_event_ids"]
    unknown = [i for i in cited if i not in case.events]
    if unknown:
        errors.append(f"evidence_event_ids not in this subject's evidence: {unknown}")
    if not [i for i in cited if i in case.events]:
        errors.append("must cite at least one valid evidence event")

    mentioned = set(CAMERA_REF.findall(proposal["recommendation"] + " " + proposal["reason"]))
    if mentioned - known_cameras:
        errors.append(f"mentions cameras not in this case: {sorted(mentioned - known_cameras)}")
    if intercept and intercept not in CAMERA_REF.findall(proposal["recommendation"]):
        errors.append(f"recommendation must send officers to {intercept} (send_officers_to)")
    if len(proposal["recommendation"]) > MAX_RECOMMENDATION:
        errors.append(f"recommendation longer than {MAX_RECOMMENDATION} characters")
    if len(proposal["reason"]) > MAX_REASON:
        errors.append(f"reason longer than {MAX_REASON} characters")

    sev = supported_severity(cited, case)
    cap = priority_for(sev)
    if PRIORITY_RANK.get(proposal["priority"], 99) > PRIORITY_RANK[cap]:
        errors.append(f"priority {proposal['priority']!r} exceeds what cited evidence supports ({cap!r})")
    if proposal["status"] == "alert" and sev == 0:
        errors.append("status 'alert' requires citing evidence of an actual activity (not 'none')")
    return errors
