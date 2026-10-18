"""Turn the test cameras in labels.csv into NeMo Gym tasks for the clarity_spotter environment.

Each task is exactly the request spotter.py sends (same frames, same prompt, same JSON format,
temperature 0) plus the hand-made label the environment grades against.
--task describe / crime build the checker's attacker-only or crime-type request instead (checker_prompt.py).
"""
import argparse
import base64
import csv
import json
from pathlib import Path

try:
    from .frames import sample_frames
    from .spotter_prompt import PROMPT, SCHEMA
    from .checker_prompt import CRIME_PROMPT, CRIME_SCHEMA, DESCRIBE_PROMPT, DESCRIBE_PROMPT_V1, DESCRIBE_SCHEMA
except ImportError:
    from frames import sample_frames
    from spotter_prompt import PROMPT, SCHEMA
    from checker_prompt import CRIME_PROMPT, CRIME_SCHEMA, DESCRIBE_PROMPT, DESCRIBE_PROMPT_V1, DESCRIBE_SCHEMA

LABEL_FIELDS = ["on_screen", "crime", "build", "height", "shirt", "pants", "shoes", "glasses",
                "headwear", "hair", "bag", "weapon", "vehicle"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="labels.csv")
    parser.add_argument("--clips", default="video-data/custom-clips")
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", default="nemo_gym/clarity_spotter/data/test.jsonl")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--width", type=int, default=640, help="frame width in pixels (frames are never upscaled)")
    parser.add_argument("--task", choices=["spot", "describe", "describe_v1", "crime"], default="spot")
    args = parser.parse_args()
    prompt, schema = {"spot": (PROMPT, SCHEMA), "describe": (DESCRIBE_PROMPT, DESCRIBE_SCHEMA),
                      "describe_v1": (DESCRIBE_PROMPT_V1, DESCRIBE_SCHEMA),
                      "crime": (CRIME_PROMPT, CRIME_SCHEMA)}[args.task]

    rows = [r for r in csv.DictReader(open(args.labels, newline="")) if r["split"] == args.split]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for label in rows:
            video = Path(label["video"]) if label.get("video") else Path(args.clips) / label["clip"] / f"{label['cam']}.mp4"
            images = [{"type": "input_image", "detail": "auto", "image_url": "data:image/jpeg;base64," + base64.b64encode(fr).decode()}
                      for fr in sample_frames(str(video), args.frames, width=args.width)]
            task = {
                "responses_create_params": {
                    "input": [{"role": "user", "content": [*images, {"type": "input_text", "text": prompt}]}],
                    "text": {"format": {"type": "json_schema", "name": "detection", "schema": schema}},
                    "temperature": 0,
                    "max_output_tokens": 800,
                },
                "clip": label["clip"],
                "cam": label["cam"],
                "label": {k: label.get(k, "") for k in LABEL_FIELDS},
            }
            f.write(json.dumps(task) + "\n")
    print(f"{len(rows)} {args.split} cameras -> {out}")


if __name__ == "__main__":
    main()
