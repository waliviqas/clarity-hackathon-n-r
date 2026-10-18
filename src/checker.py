import base64
import json
import os
import sys

from openai import OpenAI

try:
    from .frames import sample_frames  # imported as src.checker
    from .checker_prompt import DESCRIBE_PROMPT, DESCRIBE_SCHEMA
except ImportError:
    from frames import sample_frames  # run as a script from src/
    from checker_prompt import DESCRIBE_PROMPT, DESCRIBE_SCHEMA

MODEL = os.getenv("CHECKER_MODEL", "checker")
client = OpenAI(
    base_url=os.getenv("CHECKER_BASE_URL", "http://localhost:8002/v1"),
    api_key="none",
    timeout=120,  # the 12B's first request after startup takes up to a minute
    max_retries=1,
)


def describe(video_path: str, count: int = 8) -> dict:
    """Ask the checker (Nemotron Nano 12B v2 VL) to describe the suspect in one camera clip.
    Returns the spotter's suspect fields (build, height, shirt, ..., vehicle); call it on cameras the spotter flagged."""
    return describe_frames(sample_frames(video_path, count), str(video_path))


def describe_frames(frames: list[bytes], source: str = "frames") -> dict:
    images = [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(f).decode()}}
        for f in frames
    ]
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": [*images, {"type": "text", "text": DESCRIBE_PROMPT}]}],
        response_format={"type": "json_schema", "json_schema": {"name": "detection", "schema": DESCRIBE_SCHEMA}},
        temperature=0,
        max_tokens=800,
    )
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise RuntimeError(f"Checker reply was cut off or empty (finish_reason={choice.finish_reason}) for {source}")
    try:
        return json.loads(choice.message.content)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Checker returned invalid JSON for {source}: {choice.message.content[:200]}") from error


if __name__ == "__main__":
    print(json.dumps(describe(sys.argv[1]), indent=2))
