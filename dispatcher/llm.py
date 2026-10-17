"""Model layer: prompt, output schema, and an OpenAI-compatible client (vLLM).

The system prompt is fixed and all per-incident data goes in the user message,
so vLLM prefix caching reuses the system-prompt KV cache across calls.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from .graph import CameraGraph
from .models import Incident
from .rules import SEVERITY

SYSTEM_PROMPT = """You are the triage agent for a city camera network. You receive one incident:
detections from nearby cameras within a short time window. Decide what happens next.

decision:
- "dispatch": send police now. Only when the events clearly show an active threat to people.
- "monitor": evidence is weak, conflicting, or non-urgent. A human operator keeps watching.
- "dismiss": no meaningful threat.

Rules:
- Use only facts present in the events. Never invent details.
- cited_event_ids must list the event_ids that support your decision.
- incident_type must be the label of at least one cited event.
- location_camera_id must be the camera where the subject was most recently seen.
- priority is 1 (low) to 5 (critical) and must not exceed what the evidence supports.
- summary: one or two plain sentences an officer can read in 3 seconds.
- When unsure, choose "monitor". A false dispatch sends armed officers to the wrong place."""

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["dispatch", "monitor", "dismiss"]},
        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
        "incident_type": {"type": "string", "enum": sorted(SEVERITY)},
        "location_camera_id": {"type": "string"},
        "summary": {"type": "string", "maxLength": 300},
        "cited_event_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "priority", "incident_type", "location_camera_id", "summary", "cited_event_ids"],
    "additionalProperties": False,
}


def build_user_message(incident: Incident, graph: CameraGraph, errors: list[str] | None = None) -> str:
    payload = {
        "incident_id": incident.incident_id,
        "events": [
            {
                "event_id": e.event_id,
                "camera_id": e.camera_id,
                "camera_name": graph.name(e.camera_id),
                "t_offset_s": round(e.timestamp - incident.start, 1),
                "label": e.label,
                "confidence": round(e.confidence, 2),
                "description": e.description,
            }
            for e in sorted(incident.events, key=lambda e: e.timestamp)
        ],
    }
    msg = "Incident:\n" + json.dumps(payload, separators=(",", ":"))
    if errors:
        msg += "\n\nYour previous answer failed verification:\n" + "\n".join(f"- {x}" for x in errors)
        msg += "\nFix these problems and answer again."
    return msg


class LLMBackend(Protocol):
    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...


class OpenAICompatBackend:
    """Talks to any OpenAI-compatible server; in production that's vLLM on Brev."""

    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY",
                 timeout: float = 20.0, max_tokens: int = 400):
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls) -> "OpenAICompatBackend":
        return cls(
            base_url=os.environ.get("CLARITY_LLM_BASE_URL", "http://localhost:8000/v1"),
            model=os.environ["CLARITY_LLM_MODEL"],
            api_key=os.environ.get("CLARITY_LLM_API_KEY", "EMPTY"),
        )

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=self.max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "dispatch_proposal", "schema": schema, "strict": True},
            },
        )
        return json.loads(resp.choices[0].message.content)
