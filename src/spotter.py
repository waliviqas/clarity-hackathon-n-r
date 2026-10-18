import base64
import json
import os
import sys

from openai import OpenAI

try:
    from .frames import sample_frames  # imported as src.spotter
except ImportError:
    from frames import sample_frames  # run as a script from src/

MODEL = os.getenv("SPOTTER_MODEL", "Qwen/Qwen3-VL-2B-Instruct")
client = OpenAI(
    base_url=os.getenv("SPOTTER_URL", "http://localhost:8001/v1"),
    api_key="none",
    timeout=60,  # fail fast if the Brev tunnel drops instead of hanging for 10 minutes
    max_retries=1,
)

# vLLM forces the reply to match this schema, so the output always has these fields.
# what_happened comes first so the model describes the scene before it classifies it.
SCHEMA = {
    "type": "object",
    "properties": {
        "what_happened": {"type": "string"},
        "on_screen": {"type": "string", "enum": ["crime", "fleeing", "none"]},
        "crime": {"type": "string", "enum": ["stabbing", "assault", "stealing", "none"]},
        "build": {"type": "string", "enum": ["slim", "average", "heavy", "unknown"]},
        "height": {"type": "string", "enum": ["short", "average", "tall", "unknown"]},
        "shirt": {"type": "string"},
        "pants": {"type": "string"},
        "shoes": {"type": "string"},
        "glasses": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "headwear": {"type": "string"},
        "hair": {"type": "string"},
        "bag": {"type": "string"},
        "weapon": {"type": "string"},
        "vehicle": {"type": "string"},
    },
    "required": ["what_happened", "on_screen", "crime", "build", "height", "shirt", "pants",
                 "shoes", "glasses", "headwear", "hair", "bag", "weapon", "vehicle"],
}

PROMPT = """These are frames from one security camera, in time order.

First, describe what happens in one or two short sentences ("what_happened").

Then decide what is on screen:
- "crime": a crime happens in these frames: stabbing, assault (hitting, punching, shoving), or stealing (taking someone's property, including pickpocketing, snatching, or stealing a vehicle)
- "fleeing": no crime happens here, but someone is running away as if escaping
- "none": nothing suspicious

"crime" is the type of crime you see. If someone is fleeing, use the crime they appear to be escaping from if you can tell, otherwise "none".

The suspect is the person committing the crime or running away, not the victim (the person who gets hurt, falls, or loses something). Describe only the suspect. Use "unknown" for anything you cannot see clearly. For headwear, bag, weapon and vehicle, use "none" if the suspect clearly has none. If there is no suspect, use "unknown" for build, height and glasses, and "none" for the other description fields."""


def spot(video_path: str, count: int = 4) -> dict:
    """Ask the spotter model what happens in one camera clip."""
    return spot_frames(sample_frames(video_path, count), str(video_path))


def spot_frames(frames: list[bytes], source: str = "frames") -> dict:
    """Ask the spotter model what happens in already-extracted JPEG frames."""
    images = [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(f).decode()}}
        for f in frames
    ]
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": [*images, {"type": "text", "text": PROMPT}]}],
        response_format={"type": "json_schema", "json_schema": {"name": "detection", "schema": SCHEMA}},
        temperature=0,
        max_tokens=800,
    )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise RuntimeError(f"Spotter reply was cut off or empty (finish_reason={choice.finish_reason}) for {source}")
    try:
        return json.loads(choice.message.content)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Spotter returned invalid JSON for {source}: {choice.message.content[:200]}") from error


if __name__ == "__main__":
    print(json.dumps(spot(sys.argv[1]), indent=2))
