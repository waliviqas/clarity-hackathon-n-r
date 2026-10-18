"""Spotter answer (Wali's src/spotter.py, one JSON answer per camera clip) -> contract `detection` event.

The spotter answers what_happened, on_screen (crime | fleeing | none), crime (stabbing | assault | stealing |
none) and the suspect's build, height, shirt, pants, shoes, glasses, headwear, hair, bag, weapon, vehicle.
It gives no confidence, direction or box, so the detection says so instead of inventing numbers:
  - activity: the crime renamed to the contract enum (assault -> fistfight, stealing -> purse_snatch),
    only when on_screen is "crime". A camera that only sees someone run past didn't see the crime
    (the dashboard puts a crime ring on every camera whose detection has a crime activity).
  - direction: null (not observed). bbox: null. activity_confidence: left out.
  - confidence: contract v0.1 requires a number here, so it is 0.5 with "confidence_known": false.
    The dispatcher reads confidence_known=false as unknown (Michael's 18efa11): never dropped; a stabbing
    still alerts at once (56712cc), fistfights and purse snatches go to the model. Never 0.
  - extra fields (allowed by the contract): what_happened and on_screen (the dispatcher's model reads
    them), spotter_crime (the spotter's own crime word), spotter (the whole answer), window_ts.
"""
from __future__ import annotations

from .matching import features

SCHEMA_VERSION = "0.1"
SOURCE = "agents"
UNSCORED_CONFIDENCE = 0.5

# Spotter crime word -> contract activity. Contract names pass through as-is; anything else is "none".
CRIME_TO_ACTIVITY = {"stabbing": "stabbing", "assault": "fistfight", "stealing": "purse_snatch",
                     "fistfight": "fistfight", "purse_snatch": "purse_snatch"}
ACTIVITY_WORDS = {"stabbing": "Stabbing", "fistfight": "Fistfight", "purse_snatch": "Purse snatch"}


def crime_to_activity(crime) -> str:
    return CRIME_TO_ACTIVITY.get(str(crime or "").strip().lower(), "none")


def activity_of(answer: dict) -> str:
    """The contract activity this camera saw: the crime, only if the crime happens on this camera."""
    if str(answer.get("on_screen") or "").strip().lower() != "crime":
        return "none"
    return crime_to_activity(answer.get("crime"))


def is_crime(answer: dict) -> bool:
    return activity_of(answer) != "none"


def appearance_text(feats: dict[str, str]) -> str | None:
    """One readable line from features(), e.g. 'slim build, black hoodie, dark grey pants, curly dark hair'.
    Only what was seen; "has none" items are left out. None when nothing was seen."""
    parts = []
    if "build" in feats:
        parts.append(f"{feats['build']} build")
    if "height" in feats:
        parts.append("average height" if feats["height"] == "average" else feats["height"])
    parts += [feats[f] for f in ("shirt", "pants", "shoes") if f in feats]
    if "hair" in feats:
        hair = feats["hair"]
        parts.append(hair if "hair" in hair or "bald" in hair else f"{hair} hair")
    if feats.get("glasses") == "yes":
        parts.append("glasses")
    for field in ("headwear", "bag"):
        if feats.get(field, "none") != "none":
            parts.append(feats[field])
    for field in ("weapon", "vehicle"):
        if feats.get(field, "none") != "none":
            parts.append(f"{field}: {feats[field]}")
    return ", ".join(parts) or None


def to_detection(answer: dict, *, event_id: str, track_id: str, camera_id: str, ts: float,
                 window: tuple[float, float] | None = None, run_id: str | None = None,
                 extra: dict | None = None) -> dict:
    """One spotter answer as a contract `detection` (ts = when the clip finished, on the run clock)."""
    event = {"type": "detection", "schema_version": SCHEMA_VERSION, "event_id": event_id, "ts": round(ts, 3)}
    if run_id:
        event["run_id"] = run_id
    event.update(
        source=SOURCE, camera_id=camera_id, track_id=track_id, label="person",
        confidence=UNSCORED_CONFIDENCE, confidence_known=False, bbox=None,
        activity=activity_of(answer), appearance=appearance_text(features(answer)), direction=None,
        on_screen=answer.get("on_screen"), what_happened=answer.get("what_happened"),
        spotter_crime=answer.get("crime"), spotter=answer,
    )
    if window is not None:
        event["window_ts"] = [round(window[0], 3), round(window[1], 3)]
    event.update(extra or {})
    return event
