"""Cut spotter training clips from MEVA (CC BY 4.0) in Wali's labels.csv format.

MEVA: "Multiview Extended Video with Activities", Kitware Inc., mevadata.org, CC BY 4.0
(https://mevadata.org/resources/MEVA-data-license.txt). Scripted activities by consenting actors
(collected under IRB approval), 1080p CCTV-style cameras.

Two steps:

  plan  (anywhere with the annotations; stdlib only)
        python scripts/meva_training_clips.py plan --annotations <meva-data-repo>/annotation/DIVA-phase-2/MEVA \
            --out jobs.json
        Reads the Kitware *.activities.yml files, keeps hugs (person_embraces_person), hand-to-hand
        interactions (hand_interacts_with_person) and thefts (person_steals_object), spreads picks over
        sites/cameras/dates, checks each source video exists in MEVA's public S3 bucket, and writes jobs.json.

  cut   (on the GPU box; needs ffmpeg, e.g. from `pip install imageio-ffmpeg`)
        python scripts/meva_training_clips.py cut --jobs jobs.json --root ~/meva_batch --ffmpeg <ffmpeg>
        Downloads each source video once, cuts every job as a 5-15 s clip with the event in the middle,
        re-encodes to 720p H.264 MP4 (no audio), saves a middle frame for review, deletes the download,
        and writes <root>/video-data/training-clips/labels_meva.csv in labels.csv format (split=train).

Normal clips: on_screen=none, crime=none, description columns blank. Thefts: on_screen=crime,
crime=stealing, description columns left for a human to fill from the clip (check=needs review).
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

BUCKET = "https://mevadata-public-01.s3.amazonaws.com"
DROP = "drops-123-r13"
FPS = 30.0  # MEVA KF1 cameras record at 30 fps; checked on a sample file
ACTIVITIES = {
    "person_embraces_person": ("none", "none", "two people hug; nothing suspicious"),
    "hand_interacts_with_person": ("none", "none", "two people interact hand to hand (handshake or passing an item); nothing suspicious"),
    "person_steals_object": ("crime", "stealing", None),
}
LABEL_FIELDS = ["clip", "cam", "split", "on_screen", "crime", "what_happened", "build", "height", "shirt", "pants",
                "shoes", "glasses", "headwear", "hair", "bag", "weapon", "vehicle", "check", "video"]


def parse_events(ann_root: Path) -> list[dict]:
    events = []
    for path in sorted(ann_root.rglob("*.activities.yml")):
        stem = path.name.removesuffix(".activities.yml")  # 2018-03-07.11-05-00.11-10-00.hospital.G436
        date, hour = path.parent.parent.name, path.parent.name
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "'act2'" not in line or not any(a in line for a in ACTIVITIES):
                continue
            try:
                act = ast.literal_eval(line.lstrip("- ").strip())["act"]
            except (ValueError, SyntaxError, KeyError):
                continue
            name = next(iter(act["act2"]))
            if name not in ACTIVITIES:
                continue
            start, end = act["timespan"][0]["tsr0"]
            site, camera = stem.split(".")[-2], stem.split(".")[-1]
            events.append({"activity": name, "stem": stem, "date": date, "hour": hour, "site": site, "camera": camera,
                           "start": int(start), "end": int(end), "actors": [a["id1"] for a in act.get("actors", [])],
                           "source_annotation": str(path.relative_to(ann_root)).replace(os.sep, "/"),
                           "key": f"{DROP}/{date}/{hour}/{stem}.r13.avi"})
    return events


def exists(key: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{BUCKET}/{key}", method="HEAD"), timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def window(ev: dict) -> tuple[float, float]:
    """5-15 s clip with the event in the middle: event length + 5 s, clamped to 6-12 s."""
    dur_s = (ev["end"] - ev["start"]) / FPS
    length = min(12.0, max(6.0, dur_s + 5.0))
    center = (ev["start"] + ev["end"]) / 2 / FPS
    start = max(0.0, center - length / 2)
    return round(start, 2), round(length, 2)


def plan(args) -> None:
    events = parse_events(Path(args.annotations))
    by_act = Counter(e["activity"] for e in events)
    print("events found:", dict(by_act))
    # dedupe the same event annotated in two folders (kitware and kitware-meva-training)
    seen, unique = set(), []
    for e in events:
        k = (e["stem"], e["activity"], e["start"] // 30)
        if k not in seen:
            seen.add(k)
            unique.append(e)
    if args.only_cameras:  # second pass: only viewpoints where people are big enough to see (from the first review)
        unique = [e for e in unique if e["camera"] in set(args.only_cameras.split(","))]
    quota = {"person_steals_object": 99 if not args.no_thefts else 0,
             "person_embraces_person": args.hugs, "hand_interacts_with_person": args.hands}
    chosen, files, used_windows = [], {}, defaultdict(list)
    for prev in args.skip_jobs or []:  # never re-cut a window from an earlier batch
        for j in json.loads(Path(prev).read_text())["jobs"]:
            used_windows[j["key"]].append((j["clip_start_s"], j["clip_len_s"]))
    combo_count = Counter()
    # thefts first (all of them), then hugs, then hand interactions; prefer sources already being downloaded,
    # then rare site/camera combinations, to spread people and places
    for act in ("person_steals_object", "person_embraces_person", "hand_interacts_with_person"):
        pool = [e for e in unique if e["activity"] == act and (e["end"] - e["start"]) >= args.min_frames]
        taken = 0
        while pool and taken < quota[act]:
            pool.sort(key=lambda e: (e["key"] not in files, combo_count[(e["site"], e["camera"])],
                                     len([c for c in chosen if c["key"] == e["key"]]), e["key"], e["start"]))
            e = pool.pop(0)
            if e["key"] not in files and len(files) >= args.max_files:
                continue
            if len([c for c in chosen if c["key"] == e["key"]]) >= args.per_file:
                continue
            start, length = window(e)
            if any(not (start + length <= s or s + l <= start) for s, l in used_windows[e["key"]]):
                continue  # overlaps a clip already cut from this video
            if e["key"] not in files:
                files[e["key"]] = exists(e["key"])
                if not files[e["key"]]:
                    continue
            used_windows[e["key"]].append((start, length))
            combo_count[(e["site"], e["camera"])] += 1
            chosen.append({**e, "clip_start_s": start, "clip_len_s": length})
            taken += 1
    ok_files = [k for k, v in files.items() if v]
    for i, c in enumerate(chosen, args.start_index):
        tag = {"person_embraces_person": "hug", "hand_interacts_with_person": "hand", "person_steals_object": "theft"}
        c["clip"] = f"meva_{tag[c['activity']]}_{i:03d}"
    Path(args.out).write_text(json.dumps({"bucket": BUCKET, "jobs": chosen}, indent=1))
    print(f"chosen {len(chosen)} clips from {len(ok_files)} source videos:",
          dict(Counter(c["activity"] for c in chosen)), "| sites:", dict(Counter(c["site"] for c in chosen)))


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def cut(args) -> None:
    jobs = json.loads(Path(args.jobs).read_text())["jobs"]
    root = Path(args.root).expanduser()
    out_dir = root / "video-data" / "training-clips" / "videos"
    thumbs, tmp = root / "thumbs", root / "tmp"
    for d in (out_dir, thumbs, tmp):
        d.mkdir(parents=True, exist_ok=True)
    rows, by_key = [], defaultdict(list)
    for j in jobs:
        by_key[j["key"]].append(j)
    for n, (key, group) in enumerate(by_key.items(), 1):
        src = tmp / Path(key).name
        if not all((out_dir / f"{j['clip']}.mp4").exists() for j in group):
            print(f"[{n}/{len(by_key)}] downloading {key}", flush=True)
            urllib.request.urlretrieve(f"{BUCKET}/{key}", src)
        for j in group:
            mp4 = out_dir / f"{j['clip']}.mp4"
            if not mp4.exists():
                run([args.ffmpeg, "-y", "-loglevel", "error", "-ss", str(j["clip_start_s"]), "-i", str(src),
                     "-t", str(j["clip_len_s"]), "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast",
                     "-crf", "23", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(mp4)])
                run([args.ffmpeg, "-y", "-loglevel", "error", "-ss", str(j["clip_len_s"] / 2), "-i", str(mp4),
                     "-frames:v", "1", "-vf", "scale=-2:360", str(thumbs / f"{j['clip']}.jpg")])
            on_screen, crime, what = ACTIVITIES[j["activity"]]
            rows.append({"clip": j["clip"], "cam": "cam1", "split": "train", "on_screen": on_screen, "crime": crime,
                         "what_happened": what or "", "check": "" if crime == "none" else "needs review",
                         "video": f"video-data/training-clips/videos/{j['clip']}.mp4"})
        if src.exists():
            src.unlink()
    with open(root / "video-data" / "training-clips" / "labels_meva.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_FIELDS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LABEL_FIELDS})
    with open(root / "video-data" / "training-clips" / "meva_sources.json", "w") as f:
        json.dump([{k: j[k] for k in ("clip", "activity", "key", "clip_start_s", "clip_len_s", "start", "end",
                                      "site", "camera", "source_annotation")} for j in jobs], f, indent=1)
    print(f"done: {len(rows)} clips in {out_dir}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--annotations", required=True)
    p.add_argument("--out", default="jobs.json")
    p.add_argument("--hugs", type=int, default=45)
    p.add_argument("--hands", type=int, default=15)
    p.add_argument("--max-files", type=int, default=30)
    p.add_argument("--per-file", type=int, default=3)
    p.add_argument("--min-frames", type=int, default=45, help="skip events shorter than this (1.5 s)")
    p.add_argument("--only-cameras", default="", help="comma-separated MEVA camera ids to draw from, e.g. G299,G330")
    p.add_argument("--skip-jobs", nargs="*", help="earlier jobs.json files whose clip windows must not be reused")
    p.add_argument("--start-index", type=int, default=1, help="first clip number (continue an earlier batch)")
    p.add_argument("--no-thefts", action="store_true", help="leave out thefts (already cut in an earlier batch)")
    c = sub.add_parser("cut")
    c.add_argument("--jobs", required=True)
    c.add_argument("--root", default="~/meva_batch")
    c.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()
    {"plan": plan, "cut": cut}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
