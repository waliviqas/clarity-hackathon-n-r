"""Compare two eval results, e.g. before vs after fine-tuning.

python src/compare.py results/before.json results/after.json
Prints a table and saves it as markdown next to the second file.
"""
import json
import sys
from pathlib import Path

# (label, key, higher_is_better)
METRICS = [
    ("Crime/fleeing/nothing right", "on_screen_accuracy", True),
    ("Crime type right", "crime_type_accuracy", True),
    ("False alarms", "false_alarm_rate", False),
    ("Suspect description right", "description_accuracy", True),
    ("Same answer every run", "consistent_cameras", True),
    ("Failed requests", "failed_requests", False),
    ("Mean latency (s)", "mean_latency_s", False),
]


def as_number(value) -> float | None:
    if isinstance(value, str) and "/" in value:
        done, total = value.split("/")
        return int(done) / int(total)
    return value


RAW_KEYS = {"failed_requests", "mean_latency_s"}


def fmt(value, key: str) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and key not in RAW_KEYS:
        return f"{value:.0%}"
    return str(value)


def main() -> None:
    before_path, after_path = Path(sys.argv[1]), Path(sys.argv[2])
    before, after = json.loads(before_path.read_text()), json.loads(after_path.read_text())
    if before["split"] != after["split"] or before["prompt"] != after["prompt"]:
        print("WARNING: the two runs used a different split or prompt, so the comparison is not fair.")

    lines = [f"| Metric | {before_path.stem} | {after_path.stem} | Change |", "|---|---|---|---|"]
    for label, key, higher_is_better in METRICS:
        b, a = before["summary"].get(key), after["summary"].get(key)
        nb, na = as_number(b), as_number(a)
        change = ""
        if isinstance(nb, (int, float)) and isinstance(na, (int, float)):
            diff = na - nb
            better = diff > 0 if higher_is_better else diff < 0
            shown = f"{diff:+g}" if key in RAW_KEYS else f"{diff:+.0%}"
            change = f"{shown} {'better' if better else 'worse' if diff else 'same'}"
        lines.append(f"| {label} | {fmt(b, key)} | {fmt(a, key)} | {change} |")

    table = "\n".join(lines)
    print(table)
    out = after_path.with_name(f"compare_{before_path.stem}_vs_{after_path.stem}.md")
    out.write_text(f"Split: {after['split']}, {after['cameras_scored']} cameras x {after['runs_per_camera']} runs\n\n{table}\n")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
