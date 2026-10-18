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

try:
    from .spotter_prompt import PROMPT, SCHEMA
except ImportError:
    from spotter_prompt import PROMPT, SCHEMA


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
