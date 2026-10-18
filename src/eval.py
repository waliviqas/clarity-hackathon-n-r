"""Grade the spotter against labels.csv.

Runs every camera in one split (default: test) several times and scores each answer.
Scoring rules, fixed for every run so before/after comparisons are fair:
- on_screen is scored on every camera.
- crime type is scored only on cameras where the crime is visible (on_screen == crime).
- a false alarm is calling "crime" on a camera where nothing happens (on_screen == none).
- suspect descriptions are scored on crime and fleeing cameras, skipping labels that are
  blank or "unknown". Free text counts as a match when at least half the label's words appear.
- a failed request counts as wrong on everything, so crashes can't inflate the score.
"""
import argparse
import csv
import json
import re
import statistics
import time
from pathlib import Path

try:
    from .spotter import MODEL, PROMPT, spot
except ImportError:
    from spotter import MODEL, PROMPT, spot

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


def score_camera(label: dict, answers: list[dict | None]) -> dict:
    """Score every run of one camera. None means the request failed."""
    scores: dict[str, list[bool]] = {"on_screen": [], "crime": [], "false_alarm": []}
    fields: dict[str, list[bool]] = {}
    for answer in answers:
        a = answer or {}
        scores["on_screen"].append(a.get("on_screen") == label["on_screen"])
        if label["on_screen"] == "crime":
            scores["crime"].append(a.get("crime") == label["crime"])
        if label["on_screen"] == "none":
            scores["false_alarm"].append(a.get("on_screen") == "crime")
        if label["on_screen"] in ("crime", "fleeing"):
            for field in EXACT_FIELDS:
                if is_scorable(label[field]):
                    fields.setdefault(field, []).append(a.get(field, "").lower() == label[field].lower())
            for field in TEXT_FIELDS:
                if is_scorable(label[field]):
                    fields.setdefault(field, []).append(text_match(label[field], a.get(field, "")))
    successful = [json.dumps(a, sort_keys=True) for a in answers if a is not None]
    return {
        "scores": {k: v for k, v in scores.items() if v},
        "fields": fields,
        "consistent": len(successful) == len(answers) and len(set(successful)) == 1,
    }


def rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="labels.csv")
    parser.add_argument("--clips", default="video-data/custom-clips")
    parser.add_argument("--split", default="test")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="only score the first N cameras (for quick checks)")
    parser.add_argument("--out", default="results/before.json")
    parser.add_argument("--name", default="", help="label for this run in results/history.csv, e.g. before or after")
    args = parser.parse_args()

    labels = [row for row in csv.DictReader(open(args.labels, newline="")) if row["split"] == args.split]
    if args.limit:
        labels = labels[: args.limit]

    cameras, latencies, errors = [], [], 0
    for label in labels:
        # Rows from outside datasets carry their own file path; our clips follow clipN/camK.mp4.
        video = Path(label["video"]) if label.get("video") else Path(args.clips) / label["clip"] / f"{label['cam']}.mp4"
        answers: list[dict | None] = []
        for _ in range(args.runs):
            start = time.perf_counter()
            try:
                answers.append(spot(str(video)))
                latencies.append(time.perf_counter() - start)
            except Exception as error:
                print(f"  {label['clip']}/{label['cam']} failed: {type(error).__name__}: {str(error)[:120]}")
                answers.append(None)
                errors += 1
        result = score_camera(label, answers)
        cameras.append({"clip": label["clip"], "cam": label["cam"], "label": label, "answers": answers, **result})
        first = answers[0] or {}
        print(f"{label['clip']}/{label['cam']:5} truth={label['on_screen']}/{label['crime']:9} "
              f"said={first.get('on_screen')}/{first.get('crime')}  consistent={result['consistent']}")

    def pooled(key: str) -> list[bool]:
        return [s for c in cameras for s in c["scores"].get(key, [])]

    field_rates = {f: rate([s for c in cameras for s in c["fields"].get(f, [])]) for f in EXACT_FIELDS + TEXT_FIELDS}
    all_fields = [s for c in cameras for v in c["fields"].values() for s in v]
    summary = {
        "on_screen_accuracy": rate(pooled("on_screen")),
        "crime_type_accuracy": rate(pooled("crime")),
        "false_alarm_rate": rate(pooled("false_alarm")),
        "description_accuracy": rate(all_fields),
        "description_accuracy_by_field": field_rates,
        "consistent_cameras": f"{sum(c['consistent'] for c in cameras)}/{len(cameras)}",
        "failed_requests": errors,
        "mean_latency_s": round(statistics.mean(latencies), 3) if latencies else None,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "model": MODEL, "split": args.split, "runs_per_camera": args.runs, "cameras_scored": len(cameras),
        "prompt": PROMPT, "summary": summary, "cameras": cameras,
    }, indent=2))
    record_history(out.parent / "history.csv", args.name or out.stem, MODEL, args.split, len(cameras), summary)
    print(json.dumps(summary, indent=2))
    print(f"Saved {out}")


HISTORY_FIELDS = ["time", "name", "model", "split", "cameras", "on_screen_accuracy", "crime_type_accuracy",
                  "false_alarm_rate", "description_accuracy", "consistent_cameras", "failed_requests", "mean_latency_s"]


def record_history(path: Path, name: str, model: str, split: str, cameras: int, summary: dict) -> None:
    """Append one line per eval run so every before/after score is kept in one table."""
    new_file = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore", lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerow({"time": time.strftime("%Y-%m-%d %H:%M"), "name": name, "model": model,
                         "split": split, "cameras": cameras, **summary})


if __name__ == "__main__":
    main()
