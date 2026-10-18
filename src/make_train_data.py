"""Turn the training cameras in labels.csv into training examples ("flashcards").

Each example is the frames from one camera plus the answer the spotter should give, written in
exactly the spotter's output format. Several frame samplings per camera multiply the examples.
Only rows with split == train are used, so test cameras are never seen in training.
"""
import argparse
import csv
import json
from pathlib import Path

try:
    from .frames import sample_frames
    from .spotter_prompt import SCHEMA
except ImportError:
    from frames import sample_frames
    from spotter_prompt import SCHEMA

SHIFTS = [-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4]
UNKNOWN_IF_BLANK = {"build", "height", "glasses"}  # enum fields that have no "none" option


def target_answer(label: dict) -> str:
    """The answer the spotter should give, in the same field order as its schema."""
    answer = {}
    for field, spec in SCHEMA["properties"].items():
        value = label.get(field, "").strip()
        if not value:
            value = "unknown" if field in UNKNOWN_IF_BLANK else "none"
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"{label['clip']}/{label['cam']}: {field}={value!r} is not one of {spec['enum']}")
        answer[field] = value
    return json.dumps(answer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", nargs="+", default=["labels.csv"], help="one or more answer sheets")
    parser.add_argument("--clips", default="video-data/custom-clips")
    parser.add_argument("--out", default="train_data")
    parser.add_argument("--frames", type=int, default=4)
    args = parser.parse_args()

    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    rows = [r for path in args.labels for r in csv.DictReader(open(path, newline="")) if r["split"] == "train"]

    examples = 0
    with open(out / "train.jsonl", "w") as f:
        for label in rows:
            video = Path(label["video"]) if label.get("video") else Path(args.clips) / label["clip"] / f"{label['cam']}.mp4"
            answer = target_answer(label)
            for k, shift in enumerate(SHIFTS):
                paths = []
                for i, frame in enumerate(sample_frames(str(video), args.frames, shift=shift)):
                    path = out / "images" / f"{label['clip']}_{label['cam']}_v{k}_f{i}.jpg"
                    path.write_bytes(frame)
                    paths.append(str(path))
                f.write(json.dumps({"clip": label["clip"], "cam": label["cam"], "images": paths, "answer": answer}) + "\n")
                examples += 1
    print(f"{len(rows)} training cameras -> {examples} examples in {out / 'train.jsonl'}")


if __name__ == "__main__":
    main()
