"""Fixed procedure guidance appended to every dispatch recommendation (team decision, Sat Oct 17).

Written by code, never by the model, so it can't be wrong or invented. Turn it off with
Dispatcher(guidance=False). Keep each line short: it shares the 300-character recommendation limit.
"""
from __future__ import annotations

GUIDANCE = {
    "stabbing": "Procedure: armed suspect, approach with backup; request EMS for the victim.",
    "fistfight": "Procedure: separate the parties, check for injuries, request EMS if needed.",
    "purse_snatch": "Procedure: take the victim's statement and broadcast the suspect description.",
}


def guidance_for(incident_type: str) -> str:
    return GUIDANCE.get(incident_type, "")


def with_guidance(recommendation: str, incident_type: str) -> str:
    line = guidance_for(incident_type)
    return f"{recommendation.rstrip()} {line}" if line else recommendation
