"""Turn Wali's NeMo Gym results (one row per test camera and run) into recorded spotter answers for the camera agents
(`python -m agents.run --answers <file>`), so the relay can be checked on a real model's answers without a GPU.

    python data/gym_answers.py --clips clip1 --out data/answers/clip1_system_v3_checker.json

Inputs, each a file path or a git object (<ref>:<path>), read with `git show` so Wali's branch is never checked
out (it holds videos):
    --results  rows {"predicted": {...}, "_ng_task_index", "_ng_rollout_index", "answered", scores...}; default
               Wali's final system: spotter-ft v3 decides crime and type, Nemotron Nano 12B v2 VL describes the
               suspect on the cameras the spotter flags, 8 frames (results/history.csv: system_v3_plus_checker_v2_8f)
    --tasks    the NeMo Gym task list (task i -> clip, cam); only clip, cam and label.on_screen are read, never
               the frames it carries
Each row's scores must fit its task's label (crime_correct only on a crime view, false_alarm only on a "none" view),
so a task list that doesn't belong to the results stops the script.

Writes Wali's eval-results format, which agents/answers.py matches to cameras.json by clip file name
(clip1 + cam1 <-> .../clip1_cam1.mp4): {"model", "checker_model", "source", "cameras": [{"clip", "cam",
"task_index", "answers": [run 0, run 1, ...]}]}. A failed run is null. Only the answer's text fields are copied, plus the marks
agents/combine.py puts on a live system answer: in system rows the checker described every camera the spotter
flagged (on_screen crime or fleeing), so those answers get description_by "checker" and checker_model (--checker;
pass --checker "" for spotter-only results). The spotter's own description isn't in system rows. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = "origin/wali-branch:results/nemo_gym/clarity_system_8f_v2.jsonl"
TASKS = "origin/wali-branch:nemo_gym/clarity_spotter/data/test.jsonl"
MODEL = "spotter-ft v3 (8 frames)"
CHECKER = "Nemotron Nano 12B v2 VL (8 frames)"
# The spotter's answer fields (Wali's src/spotter_prompt.py SCHEMA); nothing else is copied.
ANSWER_FIELDS = ("what_happened", "on_screen", "crime", "build", "height", "shirt", "pants", "shoes", "glasses",
                 "headwear", "hair", "bag", "weapon", "vehicle")
FLAGGED = ("crime", "fleeing")  # combine_gym asks the checker about these cameras only
MAX_TEXT = 1000  # an answer field is a short phrase; anything longer (or a data: URL) is not an answer
GIT_OBJECT = re.compile(r"^([^:\s]{2,}):(.+)$")  # <ref>:<path>; a one-letter "ref" would be a Windows drive


def read_source(spec: str) -> tuple[str, str]:
    """(text, where it came from) for a file path or a git object <ref>:<path>."""
    path = Path(spec)
    if path.is_file():
        return path.read_text(encoding="utf-8"), str(path)
    m = GIT_OBJECT.match(spec)
    if not m:
        raise SystemExit(f"ERROR {spec}: not a file, and not a git object like origin/wali-branch:<path>")
    ref, rel = m.groups()
    git = ["git", "-C", str(REPO)]
    commit = subprocess.run([*git, "rev-parse", "--short", "--verify", "--quiet", f"{ref}^{{commit}}"],
                            capture_output=True, text=True)
    if commit.returncode != 0:
        raise SystemExit(f"ERROR {spec}: git doesn't know {ref!r} (git fetch?)")
    shown = subprocess.run([*git, "show", f"{ref}:{rel}"], capture_output=True)
    if shown.returncode != 0:
        raise SystemExit(f"ERROR {spec}: {shown.stderr.decode('utf-8', 'replace').strip()}")
    return shown.stdout.decode("utf-8"), f"{ref}:{rel} @ {commit.stdout.strip()}"


def jsonl(text: str, what: str) -> list[dict]:
    rows = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as e:
                raise SystemExit(f"ERROR {what} line {i}: not JSON ({e})") from None
    return rows


def task_list(text: str) -> list[dict]:
    """Task index -> {clip, cam, on_screen}; the frames in each task are dropped right here."""
    return [{"clip": t.get("clip"), "cam": t.get("cam"), "on_screen": (t.get("label") or {}).get("on_screen")}
            for t in jsonl(text, "tasks")]


def clean_answer(predicted, where: str, checker: str) -> dict | None:
    """The answer's text fields only, marked as described by `checker` on a flagged camera (if checker is set);
    None for a failed run."""
    if not isinstance(predicted, dict) or not predicted:
        return None
    out = {}
    for field in ANSWER_FIELDS:
        value = predicted.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > MAX_TEXT or value.startswith("data:"):
            print(f"WARNING {where}: dropped {field} (not a short text)", file=sys.stderr)
            continue
        out[field] = value
    if out and checker and out.get("on_screen") in FLAGGED:
        out.update(description_by="checker", checker_model=checker)
    return out or None


def mismatch(row: dict, task: dict) -> str | None:
    """Why this row's scores can't belong to this task's label, or None if they fit."""
    label = task["on_screen"]
    if (row.get("crime_correct") is not None) != (label == "crime"):
        return f"crime_correct is {row.get('crime_correct')!r} but the label says on_screen {label!r}"
    if (row.get("false_alarm") is not None) != (label == "none"):
        return f"false_alarm is {row.get('false_alarm')!r} but the label says on_screen {label!r}"
    return None


def convert(rows: list[dict], tasks: list[dict], clips: set[str] | None, checker: str = "") -> list[dict]:
    cameras: dict[int, dict] = {}
    for row in rows:
        i, run = row.get("_ng_task_index"), row.get("_ng_rollout_index")
        if not (isinstance(i, int) and isinstance(run, int) and 0 <= i < len(tasks) and run >= 0):
            raise SystemExit(f"ERROR results: row with task {i!r}, run {run!r} doesn't fit {len(tasks)} tasks")
        task = tasks[i]
        problem = mismatch(row, task)
        if problem:
            raise SystemExit(f"ERROR task {i} ({task['clip']} {task['cam']}), run {run}: {problem}; "
                             "is --tasks the task list these results were scored on?")
        if clips and task["clip"] not in clips:
            continue
        cam = cameras.setdefault(i, {"clip": task["clip"], "cam": task["cam"], "task_index": i, "runs": {}})
        answered = row.get("answered", True)
        cam["runs"][run] = clean_answer(row.get("predicted"), f"task {i} run {run}", checker) if answered else None
    out = []
    for i in sorted(cameras):
        cam = cameras.pop(i)
        runs = cam.pop("runs")
        out.append({**cam, "answers": [runs.get(r) for r in range(max(runs) + 1)]})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", default=RESULTS, help=f"NeMo Gym results .jsonl (default {RESULTS})")
    parser.add_argument("--tasks", default=TASKS, help=f"NeMo Gym task list .jsonl (default {TASKS})")
    parser.add_argument("--clips", default="", help="comma-separated clips to keep, e.g. clip1 (default: all)")
    parser.add_argument("--model", default=MODEL, help=f"spotter model name to record (default {MODEL!r})")
    parser.add_argument("--checker", default=CHECKER,
                        help=f"checker that described the flagged cameras (default {CHECKER!r}); "
                             "'' for spotter-only results (no marks)")
    parser.add_argument("--out", type=Path, required=True, help="answers file to write (.json)")
    args = parser.parse_args()

    results_text, results_from = read_source(args.results)
    tasks_text, tasks_from = read_source(args.tasks)
    clips = {c.strip() for c in args.clips.split(",") if c.strip()} or None
    checker = args.checker.strip()
    cameras = convert(jsonl(results_text, "results"), task_list(tasks_text), clips, checker)
    if not cameras:
        raise SystemExit(f"ERROR: no rows for {', '.join(sorted(clips or [])) or 'any clip'} in {results_from}")
    data = {"model": args.model, "checker_model": checker or None,
            "source": {"results": results_from, "tasks": tasks_from,
                       "note": "recorded NeMo Gym runs (temperature 0), not live calls"},
            "cameras": cameras}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for cam in cameras:
        looks = [f"{a.get('on_screen')}/{a.get('crime')}/{a.get('shirt')}" if a else "failed" for a in cam["answers"]]
        print(f"{cam['clip']} {cam['cam']} (task {cam['task_index']}): {' | '.join(looks)}")
    print(f"wrote {args.out} ({len(cameras)} cameras) from {results_from}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
