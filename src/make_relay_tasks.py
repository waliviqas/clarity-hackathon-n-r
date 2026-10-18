"""NeMo Gym tasks for the relay check: the checker gets one camera's frames plus the description the previous camera
relayed (the checker's own describe answer there, run 0) and says whether that suspect is present.

Positives: every camera after the first in a clip of --split. Negatives (--negatives): normal-scene cameras from the
given label files, each paired with every first-camera description, to measure false "yes" answers.
"""
import argparse
import base64
import csv
import json
from pathlib import Path

try:
    from .checker_prompt import MATCH_PROMPT, MATCH_SCHEMA, describe_text
    from .frames import sample_frames
    from .make_gym_tasks import LABEL_FIELDS
except ImportError:
    from checker_prompt import MATCH_PROMPT, MATCH_SCHEMA, describe_text
    from frames import sample_frames
    from make_gym_tasks import LABEL_FIELDS


def task(label: dict, video: Path, description: str, frames: int, relay_from: str) -> dict:
    images = [{"type": "input_image", "detail": "auto", "image_url": "data:image/jpeg;base64," + base64.b64encode(fr).decode()}
              for fr in sample_frames(str(video), frames)]
    return {
        "responses_create_params": {
            "input": [{"role": "user", "content": [*images, {"type": "input_text", "text": MATCH_PROMPT.format(description=description)}]}],
            "text": {"format": {"type": "json_schema", "name": "detection", "schema": MATCH_SCHEMA}},
            "temperature": 0,
            "max_output_tokens": 800,
        },
        "clip": label["clip"], "cam": label["cam"], "relay_from": relay_from, "relayed": description,
        "label": {k: label.get(k, "") for k in LABEL_FIELDS},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="labels.csv")
    parser.add_argument("--clips", default="video-data/custom-clips")
    parser.add_argument("--split", default="test")
    parser.add_argument("--describe-tasks", required=True, help="the describe tasks file the rollouts were made from")
    parser.add_argument("--describe-rollouts", required=True, help="checker describe rollouts for the same split")
    parser.add_argument("--negatives", nargs="*", default=[], help="label files whose normal-scene train rows are negatives")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    dtasks = [json.loads(l) for l in open(args.describe_tasks)]
    described = {}
    for r in map(json.loads, open(args.describe_rollouts)):
        if r["_ng_rollout_index"] == 0 and r.get("predicted"):
            t = dtasks[r["_ng_task_index"]]
            described[(t["clip"], t["cam"])] = describe_text(r["predicted"])

    def video_of(label):
        return Path(label["video"]) if label.get("video") else Path(args.clips) / label["clip"] / f"{label['cam']}.mp4"

    rows = [r for r in csv.DictReader(open(args.labels, newline="")) if r["split"] == args.split]
    out = []
    for label in rows:
        n = int(label["cam"][3:])
        prev = (label["clip"], f"cam{n - 1}")
        if n > 1 and prev in described:
            out.append(task(label, video_of(label), described[prev], args.frames, f"{prev[0]}/{prev[1]}"))
    firsts = {k: v for k, v in described.items() if k[1] == "cam1"}
    for path in args.negatives:
        for label in csv.DictReader(open(path, newline="")):
            if label["split"] == "train" and label["on_screen"] == "none" and not label["clip"].startswith("meva_ex"):
                for (clip, cam), description in sorted(firsts.items()):
                    out.append(task(label, video_of(label), description, args.frames, f"{clip}/{cam}"))
    with open(args.out, "w") as f:
        f.writelines(json.dumps(t) + "\n" for t in out)
    print(f"{len(out)} relay tasks -> {args.out}")


if __name__ == "__main__":
    main()
