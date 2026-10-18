"""Check data/build_site.py on fixture clip logs, built in a temp folder (stdlib only).

    .venv/Scripts/python.exe data/check_build_site.py

(a) Old format (clock + decoy, 4 rows per take): data/staged/build_site_golden/old_format_log.csv must build to
    exactly the files beside it, which build_site.py wrote before routes and no-clock takes existed. Checked
    again with an empty travel_s column added.
(b) New format (approach + crime + 2 path + exit, no clock, no decoy; plus a no-clock take with a decoy): the
    output passes contracts/validate.py (needs jsonschema in this Python) and has the expected links,
    directions, travel times, run-clock path and clip start times; --run-speed scales only the lat/lon hops.
(c) Errors stop the build and write nothing: a take without an exit, a hop with neither travel_s nor lat/lon,
    and a take whose clock is on only some route rows. A camera with two neighbors in the same 8-way direction
    (clip 8's raw GPS) builds with a warning.
(d) The committed log data/staged/clip_log_take1.csv rebuilds the committed site files exactly.
Exit code 0 if every check passes, 1 if any fails.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "data" / "build_site.py"
VALIDATE = REPO / "contracts" / "validate.py"
GOLDEN = REPO / "data" / "staged" / "build_site_golden"
GOLDEN_FILES = {"cameras.json": "data/sites/annex/cameras.json", "manifest.json": "data/manifests/annex.json",
                "take1.json": "data/ground_truth/take1.json", "take2.json": "data/ground_truth/take2.json",
                "take3.json": "data/ground_truth/take3.json"}
HEADER = ("take,activity,role,camera_id,phone_owner,spot_description,lat,lon,heading_deg,clip_file,"
          "clock_shown_at_s,clock_reading_hhmmss,suspect_enter_s,suspect_exit_s,travel_s,notes")

NEW_LOG = HEADER + """
1,purse_snatch,approach,cam_01,,bus stop,35.77500,-78.63700,,a1.mp4,,,0.5,4.0,,
1,purse_snatch,crime,cam_02,,,35.77520,-78.63700,,a2.mp4,,,2.0,6.0,3,suspect outfit: black hoodie
1,purse_snatch,path,cam_03,,,35.77520,-78.63680,,a3.mp4,,,1.0,3.5,,
1,purse_snatch,path,cam_04,,,35.77490,-78.63680,,a4.mp4,,,0,2.25,,
1,purse_snatch,exit,cam_05,,,35.77490,-78.63650,,a5.mp4,,,1.5,5.0,0,
2,stabbing,crime,cam_06,,,35.77600,-78.63700,,b1.mp4,,,1.0,3.0,,suspect outfit: grey jacket
2,stabbing,path,cam_07,,,35.77600,-78.63720,,b2.mp4,,,0.5,2.0,,
2,stabbing,exit,cam_08,,,35.77620,-78.63720,,b3.mp4,,,1.0,4.0,,
2,stabbing,decoy,cam_09,,,35.77580,-78.63720,,b4.mp4,,,,,12,
"""
# (a, b): (travel_time_s, direction a -> b, direction b -> a). Distances by haversine, run at the default 4 m/s.
LINKS = {
    ("cam_01", "cam_02"): (3.0, "north", "south"),   # travel_s on the crime row: approach -> crime
    ("cam_02", "cam_03"): (4.5, "east", "west"),     # 18.0 m
    ("cam_03", "cam_04"): (8.3, "south", "north"),   # 33.4 m
    ("cam_04", "cam_05"): (0.0, "east", "west"),     # travel_s 0: the views touch
    ("cam_06", "cam_07"): (4.5, "west", "east"),     # 18.0 m
    ("cam_07", "cam_08"): (5.6, "north", "south"),   # 22.2 m
    ("cam_07", "cam_09"): (12.0, "south", "north"),  # decoy travel_s; it branches off the camera before the exit
}
SLOW_LINKS = {**{k: v[0] for k, v in LINKS.items()}, ("cam_02", "cam_03"): 9.0, ("cam_03", "cam_04"): 16.7,
              ("cam_06", "cam_07"): 9.0, ("cam_07", "cam_08"): 11.1}  # --run-speed 2; travel_s links stay
# Run clock: the crime enters at offset + 5 s; after it, enter = previous exit + hop; before it, exit = next
# enter - hop. Take 2's offset is 10 s.
PATHS = {1: [("cam_01", -1.5, 2.0), ("cam_02", 5.0, 9.0), ("cam_03", 13.5, 16.0), ("cam_04", 24.3, 26.55),
             ("cam_05", 26.55, 30.05)],
         2: [("cam_06", 15.0, 17.0), ("cam_07", 21.5, 23.0), ("cam_08", 28.6, 31.6)]}
STARTS = {"cam_01": -2.0, "cam_02": 3.0, "cam_03": 12.5, "cam_04": 24.3, "cam_05": 25.05,
          "cam_06": 14.0, "cam_07": 21.0, "cam_08": 27.6, "cam_09": 21.0}  # the decoy clip starts with cam_07
ROLES = {1: {"cam_01": "approach", "cam_02": "crime", "cam_03": "path", "cam_04": "path", "cam_05": "exit"},
         2: {"cam_06": "crime", "cam_07": "path", "cam_08": "exit", "cam_09": "decoy"}}
DECOYS = {1: None, 2: "cam_09"}

ERROR_LOGS = {  # name: (log, text the error output must contain)
    "take without an exit": (HEADER + """
1,fistfight,crime,cam_01,,,35.77500,-78.63700,,a1.mp4,,,1,2,,suspect outfit: red hoodie
1,fistfight,path,cam_02,,,35.77520,-78.63700,,a2.mp4,,,1,2,,
""", "no 'exit' row"),
    "hop with no travel_s and no lat/lon": (HEADER + """
1,fistfight,crime,cam_01,,,35.77500,-78.63700,,a1.mp4,,,1,2,,suspect outfit: red hoodie
1,fistfight,exit,cam_02,,,,,,a2.mp4,,,1,2,,
""", "no travel_s, and no lat/lon"),
    "clock on only some route rows": (HEADER + """
1,fistfight,crime,cam_01,,,35.77500,-78.63700,,a1.mp4,1,15:40:00,1,2,,suspect outfit: red hoodie
1,fistfight,exit,cam_02,,,35.77520,-78.63700,,a2.mp4,,,1,2,,
""", "column 'clock_shown_at_s': missing"),
}

SAME_WAY_LOG = HEADER + """
1,purse_snatch,crime,cam_01,,,35.7745,-78.6386,,a1.mp4,,,3.25,7.75,,suspect outfit: black hoodie
1,purse_snatch,path,cam_02,,,35.7744,-78.6386,,a2.mp4,,,1.25,2.5,3,
1,purse_snatch,exit,cam_03,,,35.7746,-78.6386,,a3.mp4,,,1.5,4.1,6,
"""  # clip 8's raw GPS: cam_02 is south of both its neighbors
COMMITTED_LOG = REPO / "data" / "staged" / "clip_log_take1.csv"
COMMITTED_FILES = ("data/sites/annex/cameras.json", "data/ground_truth/take1.json", "data/manifests/annex.json")

failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)
        if detail:
            print("    " + detail.strip().replace("\n", "\n    "))
    return ok


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def read_text(path: Path) -> str:
    # git may check the golden files out with CRLF (core.autocrlf); apart from line endings, bytes must match
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def with_travel_column(src: Path, dst: Path) -> Path:
    """Copy of an old-format log with an empty travel_s column before notes."""
    rows = list(csv.reader(io.StringIO(src.read_text(encoding="utf-8"), newline="")))
    at = rows[0].index("notes")
    with dst.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(row[:at] + ["travel_s" if i == 0 else ""] + row[at:] for i, row in enumerate(rows))
    return dst


def links_of(cameras: dict) -> dict:
    """{(a, b): travel_time_s} with a < b, after checking every link is written both ways with one time."""
    out = {}
    for cam in cameras.values():
        for nb in cam["neighbors"]:
            pair = tuple(sorted((cam["camera_id"], nb["camera_id"])))
            if out.setdefault(pair, nb["travel_time_s"]) != nb["travel_time_s"]:
                out[pair] = "asymmetric"
    return out


def check_old_format(tmp: Path) -> None:
    logs = {"old format": GOLDEN / "old_format_log.csv",
            "old format + empty travel_s column": with_travel_column(GOLDEN / "old_format_log.csv", tmp / "old.csv")}
    for i, (name, log) in enumerate(logs.items()):
        root = tmp / f"old{i}"
        result = run(BUILD, log, "--root", root)
        if not check(result.returncode == 0, f"{name}: builds", result.stderr):
            continue
        for golden, out in GOLDEN_FILES.items():
            want, got = read_text(GOLDEN / golden), read_text(root / out)
            diff = "".join(list(difflib.unified_diff(want.splitlines(True), got.splitlines(True), golden, out))[:30])
            check(want == got, f"{name}: {out} identical to the golden {golden}", diff)
        written = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.json"))
        check(written == sorted(GOLDEN_FILES.values()), f"{name}: writes no other files", str(written))


def check_new_format(tmp: Path) -> None:
    log = tmp / "new.csv"
    log.write_text(NEW_LOG, encoding="utf-8")
    root = tmp / "new"
    result = run(BUILD, log, "--root", root)
    if not check(result.returncode == 0, "new format: builds", result.stderr):
        return
    check("WARNING" not in result.stdout, "new format: no warnings", result.stdout)
    cameras_path = root / "data/sites/annex/cameras.json"
    valid = run(VALIDATE, cameras_path)
    check(valid.returncode == 0, "new format: cameras.json passes contracts/validate.py", valid.stdout + valid.stderr)

    cameras = {cam["camera_id"]: cam for cam in read_json(cameras_path)["cameras"]}
    want: dict[str, list] = {cam: [] for cam in STARTS}
    for (a, b), (seconds, a_to_b, b_to_a) in LINKS.items():
        want[a].append((b, seconds, a_to_b))
        want[b].append((a, seconds, b_to_a))
    got = {cam_id: [(nb["camera_id"], nb["travel_time_s"], nb["direction"]) for nb in cam["neighbors"]]
           for cam_id, cam in cameras.items()}
    want = {cam_id: sorted(nbs) for cam_id, nbs in want.items()}
    check(got == want, "new format: links (both ways), directions and travel times",
          "\n".join(f"{c}: got {got.get(c)}, want {want.get(c)}" for c in sorted(set(got) | set(want))
                    if got.get(c) != want.get(c)))
    starts = {cam_id: cam["source"]["start_ts"] for cam_id, cam in cameras.items()}
    check(starts == STARTS, "new format: clip start times in cameras.json", f"got {starts}")
    clips = read_json(root / "data/manifests/annex.json")["clips"]
    check({c: clip["start_ts"] for c, clip in clips.items()} == STARTS, "new format: clip start times in the manifest")
    names = [cam["name"] for cam in cameras.values()]
    check(not [n for n in names if any(role in n.lower() for role in ("approach", "crime", "path", "exit", "decoy"))],
          "new format: camera names carry no roles", str(names))
    for take, path in PATHS.items():
        truth = read_json(root / f"data/ground_truth/take{take}.json")
        got_path = [(hop["camera_id"], hop["t_enter"], hop["t_exit"]) for hop in truth["path"]]
        check(got_path == path, f"new format: take {take} path on the run clock", f"got {got_path}")
        check(truth["camera_roles"] == ROLES[take] and truth["decoy_camera_id"] == DECOYS[take],
              f"new format: take {take} camera roles and decoy", f"got {truth['camera_roles']}, {truth['decoy_camera_id']}")

    slow_root = tmp / "slow"
    slow = run(BUILD, log, "--root", slow_root, "--run-speed", "2")
    if check(slow.returncode == 0, "new format, --run-speed 2: builds", slow.stderr):
        got_links = links_of({c["camera_id"]: c for c in read_json(slow_root / "data/sites/annex/cameras.json")["cameras"]})
        check(got_links == SLOW_LINKS, "new format, --run-speed 2: lat/lon hops take twice as long, travel_s hops stay",
              f"got {got_links}")


def check_errors(tmp: Path) -> None:
    for i, (name, (text, needle)) in enumerate(ERROR_LOGS.items()):
        log = tmp / f"error{i}.csv"
        log.write_text(text, encoding="utf-8")
        root = tmp / f"error{i}"
        result = run(BUILD, log, "--root", root)
        wrote = list(root.rglob("*")) if root.exists() else []
        check(result.returncode == 1 and needle in result.stderr and not wrote,
              f"error, {name}: exit 1, says {needle!r}, writes nothing",
              f"exit {result.returncode}, wrote {len(wrote)} file(s)\n{result.stdout}{result.stderr}")

    log = tmp / "same_way.csv"
    log.write_text(SAME_WAY_LOG, encoding="utf-8")
    result = run(BUILD, log, "--root", tmp / "same_way")
    warned = [line for line in result.stdout.splitlines() if line.startswith("WARNING")]
    check(result.returncode == 0 and len(warned) == 1 and warned[0].startswith("WARNING cam_02:")
          and "cam_01 and cam_03 are both north" in warned[0],
          "warning, two neighbors in the same direction: builds, warns once for cam_02",
          f"exit {result.returncode}\n{result.stdout}{result.stderr}")


def check_committed_log(tmp: Path) -> None:
    root = tmp / "committed"
    result = run(BUILD, COMMITTED_LOG, "--root", root)
    if not check(result.returncode == 0, f"committed log: {COMMITTED_LOG.name} builds", result.stderr):
        return
    for out in COMMITTED_FILES:
        want, got = read_text(REPO / out), read_text(root / out)
        diff = "".join(list(difflib.unified_diff(want.splitlines(True), got.splitlines(True), out, "rebuilt"))[:30])
        check(want == got, f"committed log: rebuilds {out} exactly", diff)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="check_build_site_") as tmp:
        check_old_format(Path(tmp))
        check_new_format(Path(tmp))
        check_errors(Path(tmp))
        check_committed_log(Path(tmp))
    print("all checks passed" if not failures else f"{len(failures)} check(s) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
