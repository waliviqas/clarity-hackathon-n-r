"""NeMo Gym resources server for the Clarity spotter.

Each task is one security-camera clip (4 frames + the spotter prompt). The model must answer in the
spotter's JSON format; verify() grades that answer against the hand-made label with the same rules as
src/eval.py, so NeMo Gym scores and eval.py scores are directly comparable:
- on_screen (crime / fleeing / none) is scored on every camera
- crime type is scored only where the crime is visible (on_screen == crime)
- a false alarm is answering "crime" on a camera where nothing happens
- suspect description fields are scored on crime and fleeing cameras, skipping blank/unknown labels;
  free text matches when at least half the label's words appear
reward = the mean of every check that applies to that camera (1.0 = everything right).
"""
import json
import re
from typing import Dict, Optional

from nemo_gym.base_resources_server import (
    BaseResourcesServerConfig,
    BaseVerifyRequest,
    BaseVerifyResponse,
    SimpleResourcesServer,
)

EXACT_FIELDS = ["build", "height", "glasses"]
TEXT_FIELDS = ["shirt", "pants", "shoes", "headwear", "hair", "bag", "weapon", "vehicle"]
STOPWORDS = {"a", "an", "and", "the", "with", "over", "of", "in", "on", "4-door", "plate", "unknown"}
SYNONYMS = {"gray": "grey", "hooded": "hoodie", "sweatshirt": "hoodie", "denim": "jeans", "sneaker": "sneakers",
            "shoes": "sneakers", "trainers": "sneakers", "joggers": "sweatpants", "no": "none", "n/a": "none",
            "nothing": "none", "tshirt": "t-shirt", "tee": "t-shirt", "dark-haired": "dark"}


def words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9/\-]+", text.lower())
    return {SYNONYMS.get(t, t) for t in tokens} - STOPWORDS


def text_match(label: str, predicted: str) -> bool:
    expected = words(label)
    if not expected:
        return True
    return len(expected & words(predicted)) / len(expected) >= 0.5


def is_scorable(value: str) -> bool:
    return value.strip().lower() not in ("", "unknown")


class ClaritySpotterConfig(BaseResourcesServerConfig):
    pass


class ClaritySpotterVerifyRequest(BaseVerifyRequest):
    clip: str = ""
    cam: str = ""
    label: Dict[str, str] = {}


class ClaritySpotterVerifyResponse(BaseVerifyResponse):
    answered: bool = False
    on_screen_correct: float = 0.0
    crime_correct: Optional[float] = None
    false_alarm: Optional[float] = None
    description_score: Optional[float] = None
    predicted: Dict[str, str] = {}


def answer_text(response) -> str:
    for item in response.output:
        if item.type == "message":
            return "".join(part.text for part in item.content if getattr(part, "type", "") == "output_text")
    return ""


class ClaritySpotterResourcesServer(SimpleResourcesServer):
    config: ClaritySpotterConfig

    async def verify(self, body: ClaritySpotterVerifyRequest) -> ClaritySpotterVerifyResponse:
        label = body.label
        try:
            predicted = json.loads(answer_text(body.response))
            answered = isinstance(predicted, dict)
        except (json.JSONDecodeError, TypeError):
            predicted, answered = {}, False
        if not answered:
            predicted = {}

        checks: list[float] = []
        on_screen_correct = float(predicted.get("on_screen") == label["on_screen"])
        checks.append(on_screen_correct)

        crime_correct = false_alarm = description_score = None
        if label["on_screen"] == "crime":
            crime_correct = float(predicted.get("crime") == label["crime"])
            checks.append(crime_correct)
        if label["on_screen"] == "none":
            false_alarm = float(predicted.get("on_screen") == "crime")
            checks.append(1.0 - false_alarm)
        if label["on_screen"] in ("crime", "fleeing"):
            fields = []
            for field in EXACT_FIELDS:
                if is_scorable(label.get(field, "")):
                    fields.append(float(str(predicted.get(field, "")).lower() == label[field].lower()))
            for field in TEXT_FIELDS:
                if is_scorable(label.get(field, "")):
                    fields.append(float(text_match(label[field], str(predicted.get(field, "")))))
            if fields:
                description_score = sum(fields) / len(fields)
                checks.extend(fields)

        return ClaritySpotterVerifyResponse(
            **body.model_dump(by_alias=True),  # keep "schema" spelled the way the response format expects
            reward=sum(checks) / len(checks),
            answered=answered,
            on_screen_correct=on_screen_correct,
            crime_correct=crime_correct,
            false_alarm=false_alarm,
            description_score=description_score,
            predicted={k: str(v) for k, v in predicted.items()},
        )


if __name__ == "__main__":
    ClaritySpotterResourcesServer.run_webserver()
