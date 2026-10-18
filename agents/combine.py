"""The spotter's answer and the checker's description combined, as in Wali's nemo_gym/combine_gym.py (the system
he scored in NeMo Gym: v3 spotter + checker describe prompt v2, 8 frames each).

  - Only cameras the spotter flagged (on_screen "crime" or "fleeing") get a checker call.
  - The spotter keeps what_happened, on_screen and crime; the checker's 11 suspect fields replace the
    spotter's (a field the checker left out becomes "", which the agents read as unknown). Elsewhere the
    spotter's answer stands, unchanged.
  - If the checker fails on a flagged camera, the spotter's own fields stay (combine_gym scores that case as
    wrong instead; a live run keeps the best description it has).

The combined answer is still one spotter-shaped JSON object, so the agents, --save-answers and --answers replays
handle it like any spotter answer. A few marks say what happened (agents/adapter.py copies them into the
detection): description_by ("checker", or "spotter" when the checker failed), checker_model, checker_error
(the exception's name), spotter_description (the spotter's own 11 fields, so the receipts still show what
each model said).
"""
from __future__ import annotations

# Wali's DESCRIBE_FIELDS (src/checker_prompt.py) = combine_gym's EXACT_FIELDS + TEXT_FIELDS.
DESCRIPTION_FIELDS = ("build", "height", "shirt", "pants", "shoes", "glasses", "headwear", "hair", "bag", "weapon",
                      "vehicle")
FLAGGED = ("crime", "fleeing")
MARKS = ("description_by", "checker_model", "checker_error", "spotter_description")


def flagged(answer: dict) -> bool:
    """The spotter flagged this camera: a crime happens on it, or someone runs away from one."""
    return str(answer.get("on_screen") or "").strip().lower() in FLAGGED


def merge_answers(answer: dict, description: dict, checker_model: str | None = None) -> dict:
    """The spotter's answer with the checker's suspect fields (combine_gym's merge), marked as such."""
    merged = dict(answer)
    merged.update({f: description.get(f, "") for f in DESCRIPTION_FIELDS})
    merged["description_by"] = "checker"
    if checker_model:
        merged["checker_model"] = checker_model
    merged["spotter_description"] = {f: answer[f] for f in DESCRIPTION_FIELDS if f in answer}
    return merged


def spotter_only(answer: dict, error: str) -> dict:
    """The checker failed on this flagged camera (error: the exception's name): the spotter's fields stand."""
    return {**answer, "description_by": "spotter", "checker_error": error}


def split_answer(answer: dict) -> tuple[dict, dict | None]:
    """(what the spotter said, what the checker said or None) from an answer the agents used."""
    spotter = {k: v for k, v in answer.items() if k not in MARKS}
    if answer.get("description_by") != "checker":
        return spotter, None
    checker = {f: answer.get(f, "") for f in DESCRIPTION_FIELDS}
    spotter = {k: v for k, v in spotter.items() if k not in DESCRIPTION_FIELDS}
    own = answer.get("spotter_description")
    spotter.update(own if isinstance(own, dict) else {})
    return spotter, checker
