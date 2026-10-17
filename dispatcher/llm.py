"""Model layer: prompt, output schema, and an OpenAI-compatible client (vLLM).

The system prompt is fixed and all per-case data goes in the user message,
so vLLM prefix caching reuses the system-prompt KV cache across calls.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from .graph import CameraGraph
from .models import SubjectCase

SYSTEM_PROMPT = """You are the dispatch agent for a city camera network. Camera agents track one subject
across cameras and send you their evidence: detections (with activity), relays between cameras, and
verdicts (match / no_match / uncertain). You decide what the human operator should do next.

status:
- "alert": the evidence shows an activity that needs an officer now.
- "tracking": keep following the subject; evidence is weak, conflicting, or not urgent.

Rules:
- Use only facts in the evidence. Never invent details.
- evidence_event_ids must list the event_ids that support your recommendation.
- Mention cameras only by camera_ids that appear in the input.
- priority (low / medium / high) must not exceed what the cited activities support.
- recommendation: one concrete action, e.g. where to send an officer and what to secure.
- reason: one sentence explaining why, an operator reads it in 3 seconds.
- A human confirms every recommendation, but a wrong alert still wastes officers. When unsure, use "tracking"."""

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["tracking", "alert"]},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "recommendation": {"type": "string", "maxLength": 200},
        "reason": {"type": "string", "maxLength": 200},
        "evidence_event_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "priority", "recommendation", "reason", "evidence_event_ids"],
    "additionalProperties": False,
}


def _evidence_view(m: dict, graph: CameraGraph, t0: float) -> dict:
    base = {"event_id": m["event_id"], "type": m["type"], "t_offset_s": round(m["ts"] - t0, 1)}
    if m["type"] == "detection":
        base.update(camera_id=m["camera_id"], label=m.get("label"), activity=m.get("activity"),
                    activity_confidence=m.get("activity_confidence"))
    elif m["type"] == "relay":
        base.update(from_camera=m["from_camera"], to_camera=m["to_camera"], summary=m.get("summary"),
                    confidence=m.get("confidence"))
    elif m["type"] == "agent_verdict":
        base.update(camera_id=m["camera_id"], decision=m["decision"], confidence=m.get("confidence"),
                    reason=m.get("reason"))
    return base


def build_user_message(case: SubjectCase, cam_path: list[dict], pred: list[dict],
                       graph: CameraGraph, errors: list[str] | None = None) -> str:
    events = sorted(case.events.values(), key=lambda m: m["ts"])
    t0 = events[0]["ts"]
    cams = {p["camera_id"] for p in cam_path} | {p["camera_id"] for p in pred}
    payload = {
        "subject_id": case.subject_id,
        "cameras": {c: graph.name(c) for c in sorted(cams)},
        "path": [{"camera_id": p["camera_id"], "t_offset_s": round(p["ts"] - t0, 1)} for p in cam_path],
        "predicted_next": pred,
        "evidence": [_evidence_view(m, graph, t0) for m in events],
    }
    msg = "Case:\n" + json.dumps(payload, separators=(",", ":"))
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
