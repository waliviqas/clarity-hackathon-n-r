"""Build the Annex site data from the filled clip log (format: data/staged/clip_log_template.csv).

Writes (paths under --root, default the repo root; <site> is --site, default annex):
    data/sites/<site>/cameras.json   camera graph: positions, neighbors, travel times, clip sources
    data/ground_truth/take<N>.json   per incident: subject, activity, outfit, path on the run clock, camera roles
                                     (--site-truth: data/ground_truth/<site>/take<N>.json, so a site that reuses
                                     takes another site has ground truth for leaves those files alone)
    data/manifests/<site>.json       camera_id -> clip file + start_ts, for feeds/
Several logs build one site from all their takes (each take in one log only).

Routes: one row per camera, each take's route rows in route order. Roles: an optional `approach` (the suspect is
seen before the crime), the `crime`, any number of `path` cameras (`junction` is the older name for one), the
`exit` (last), and an optional `decoy`: an empty path, filmed separately, that branches off the camera before the
exit. Consecutive route cameras are linked, and so are the decoy and the camera it branches off.

Run clock: each take is lined up on its crime: the crime row's suspect_enter is run-clock take offset + 5 s
(5 / 15 / 25 s for takes 1/2/3), so the three separately filmed takes replay overlapped with their crimes 10 s
apart. --run-offset S gives every take built the offset S instead (a one-take demo site uses 0, so its crime
plays at 5 s like take 1's); --run-offset 3=0,2=7 sets it per take (a take not named keeps its default), e.g.
take 2's crime 7 s after take 3's. The other route clips follow by one of two rules, so a clip may start before
run-clock 0 (feeds skips frames with ts < 0):
  clock     the clips show a seconds clock. At clip second `clock_shown_at_s` it reads `clock_reading_hhmmss`, so
            clip second t is wall time reading + (t - clock_shown_at_s). A link's travel time is the next camera's
            suspect_enter minus the previous camera's suspect_exit on the run clock (0 if the views overlap).
  no clock  none of the take's route rows has a clock cell. A link's travel time is the later camera's `travel_s`,
            else the straight-line distance between the two cameras' lat/lon at --run-speed (default 4 m/s).
            After the crime, a camera's suspect_enter = the previous camera's suspect_exit + travel; before it,
            the approach's suspect_exit = the crime's suspect_enter - travel.
Decoy clips ignore their clock and start with the camera they branch off; their link is the logged walk (the
decoy row's travel_s, or "stopwatch s: N" in its notes). Directions come from lat/lon (8-way compass). Every link
is written both ways. A warning flags any camera with two neighbors in the same 8-way direction (e.g. a split's
exit and decoy, or GPS error larger than the gap between cameras), because the graph can't tell them apart.

Camera names are neutral, because models and prompts may see them: "Route <N>: <spot_description>", or
"Route <N>: camera <k>" (k = 1, 2, ... in camera_id order within the take) when spot_description is blank. Roles
are written only to ground truth, never to cameras.json or the manifest, and a spot_description that names a role
or a crime is an error.

Accepted cell formats:
    lat / lon            35.77531 and -78.63702, or iPhone Compass style 35°46'31"N and 78°38'13"W
                         (spaces work instead of the symbols: 35 46 31 N)
    heading_deg          optional column: compass direction the phone faces, 0-360 (0 = north, 90 = east)
    travel_s             optional column: seconds from the previous route camera to this one (no-clock takes),
                         or from the split to the decoy
    clip seconds         23.5, or m:ss like 0:23.5
    clock_reading        HH:MM:SS (or HHMMSS); one clock per take, 12 h or 24 h
    file encoding        UTF-8 (with or without BOM), or Windows-1252 (Excel "CSV (Comma delimited)")
phone_owner, spot_description, heading_deg, travel_s, the decoy rows' clock cells and the clock cells of a take
without a clock are optional (spot_description goes into the camera name; phone_owner is never copied into the
outputs). Every other blank cell is an error. Logs made before the heading_deg and travel_s columns existed still
build, to the same outputs.

Run from the repo root (stdlib only):
    python data/build_site.py data/staged/clip_log.csv
    python data/build_site.py data/staged/clip_log.csv --takes 1      # only take 1 is logged so far
    python data/build_site.py data/staged/clip_log.csv --check-clips data/raw/staged
        (also checks that every clip_file exists in data/raw/staged/take<N>/ with the exact upper/lower case;
         the Brev box runs Linux, where IMG_0001.MOV and img_0001.mov are different files)
    python data/build_site.py data/staged/clip_log_take3.csv --site annex_clip1 \\
        --site-name "Red Hat Annex (clip 1)" --run-offset 0      # a one-take site of its own (clip 1)
    python data/build_site.py data/staged/clip_log_take2.csv data/staged/clip_log_take3.csv --site annex_multi \\
        --site-name "Red Hat Annex (staged clips 1 and 7)" --run-offset 3=0,2=7 --site-truth
        (two takes on one map, clip 7's crime 7 s after clip 1's; ground truth in data/ground_truth/annex_multi/)
Then check: python contracts/validate.py data/sites/annex/cameras.json
Tests (fixture logs in a temp folder): python data/check_build_site.py
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SITE_ID = "annex"  # default --site
SITE_NAME = "Red Hat Annex (staged takes)"  # default --site-name
SITE_ID_FORMAT = re.compile(r"^[a-z0-9_]+$")  # a folder name and a file name: data/sites/<site>/, <site>.json
ROUTE_ROLES = ("approach", "crime", "path", "junction", "exit")  # route order; junction = path (older name)
ROLES = ROUTE_ROLES + ("decoy",)
ROUTE_RANK = {"approach": 0, "crime": 1, "path": 2, "junction": 2, "exit": 3}  # path rows keep their row order
ONE_PER_TAKE = ("approach", "crime", "exit", "decoy")
TAKE_OFFSETS = {1: 0.0, 2: 10.0, 3: 20.0}
CRIME_AT_S = 5.0  # a take's crime (crime row's suspect_enter) plays at run-clock offset + this: 5 / 15 / 25 s
RUN_SPEED_M_S = 4.0  # default --run-speed: escape pace for no-clock links without travel_s
ACTIVITIES = ("stabbing", "fistfight", "purse_snatch")
COLUMNS = ("take", "activity", "role", "camera_id", "phone_owner", "spot_description", "lat", "lon",
           "clip_file", "clock_shown_at_s", "clock_reading_hhmmss", "suspect_enter_s",
           "suspect_exit_s", "notes")
OPTIONAL_COLUMNS = ("heading_deg", "travel_s")  # added later; older logs without them still build
CLOCK_COLUMNS = ("clock_shown_at_s", "clock_reading_hhmmss")
CAMERA_ID = re.compile(r"^cam_(0[1-9]|1[0-2])$")
# Decimal degrees, or degrees-minutes-seconds with symbols or spaces: 35°46'31"N, 35 46 31 N
COORD = re.compile(r"""^(-?\d+(?:\.\d+)?)(?:\s*°\s*|\s+)?(?:(\d+(?:\.\d+)?)(?:\s*['′]\s*|\s+)?)?"""
                   r"""(?:(\d+(?:\.\d+)?)\s*(?:"|″|'')?\s*)?([NSEW])?$""", re.IGNORECASE)
COORD_EXAMPLE = {"lat": "35.77531 or 35°46'31\"N", "lon": "-78.63702 or 78°38'13\"W"}
OUTFIT = re.compile(r"suspect outfit:\s*([^;]*)", re.IGNORECASE)
STOPWATCH = re.compile(r"stopwatch s:\s*([0-9:.]*)", re.IGNORECASE)
# Words that would tell a model a camera's role or the crime if they reached a camera name or clip path.
# Whole words only ("stable yard" is fine): no letter may touch either end, so "_decoy.mov" still counts.
ROLE_WORDS = re.compile(r"(?<![a-z])(?:crimes?|decoys?|junctions?|exits?|approach(?:es|ed|ing)?|suspects?|victims?|(?:fist)?fights?|"
                        r"fighting|snatch(?:es|ed|ing|ers?)?|stab(?:s|bed|bing)?|robber(?:s|y)?|robbing|thefts?|"
                        r"thief|thieves)(?![a-z])", re.IGNORECASE)
COMPASS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")
EARTH_RADIUS_M = 6_371_000
ANNEX_REF = {"lat": 35.7753, "lon": -78.6370}   # rough Red Hat Annex location, a sanity anchor only
MAX_FROM_ANNEX_M = 1500  # every camera rings one building; farther means a sign or format slip
MAX_CLOCK_GAP_S = 3600   # clips of one take start minutes apart, not hours (catches 12 h wraps)
MIN_SEPARATION_M = 1.0


class Problems(list):
    """Collects every error so Mina fixes the whole log in one pass instead of one cell at a time."""

    def cell(self, row: dict, col: str, parse, required: bool = True):
        raw = row.get(col, "")
        if not raw:
            if required:
                self.append(f"{where(row)}, column '{col}': missing")
            return None
        try:
            return parse(raw)
        except ValueError as e:
            self.append(f"{where(row)}, column '{col}': {e}{got(raw, e)}")
            return None


def got(raw: str, error: ValueError) -> str:
    """' (got 'x')' unless the message already quotes the value."""
    return "" if repr(raw) in str(error) else f" (got {raw!r})"


def where(row: dict) -> str:
    return f"row {row['_line']} (take {row.get('take') or '?'}, {row.get('role') or '?'})"


def parse_seconds(text: str) -> float:
    parts = text.split(":")
    try:
        if len(parts) > 2:
            raise ValueError
        value = float(parts[-1]) + (60 * int(parts[0]) if len(parts) == 2 else 0)
    except ValueError:
        raise ValueError(f"{text!r} is not a time; use seconds like 23 or 0:23") from None
    if not math.isfinite(value) or value < 0:
        raise ValueError("must be a number >= 0")
    return value


def parse_clock(text: str) -> float:
    """Wall time as seconds since midnight."""
    for fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H%M%S"):
        try:
            t = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6
    raise ValueError("expected a clock reading like 15:40:05")


def parse_coord(text: str, axis: str) -> float:
    m = COORD.match(text)
    if not m:
        raise ValueError(f"expected something like {COORD_EXAMPLE[axis]}")
    deg, minutes, seconds, hemi = m.groups()
    value = abs(float(deg)) + float(minutes or 0) / 60 + float(seconds or 0) / 3600
    if hemi:
        hemi = hemi.upper()
        if hemi not in ("NS" if axis == "lat" else "EW"):
            raise ValueError(f"hemisphere {hemi} doesn't belong in {axis}")
        if deg.startswith("-"):
            raise ValueError("use either a minus sign or a hemisphere letter, not both")
        if hemi in "SW":
            value = -value
    elif deg.startswith("-"):
        value = -value
    elif minutes or seconds:
        raise ValueError("degrees-minutes-seconds needs a hemisphere letter (N/S/E/W)")
    if abs(value) > (90 if axis == "lat" else 180):
        raise ValueError(f"out of range for {axis}")
    return value


def offset_m(a: dict, b: dict) -> tuple[float, float]:
    """(east, north) metres from a to b; flat-earth is plenty at building scale."""
    mean_lat = math.radians((a["lat"] + b["lat"]) / 2)
    east = math.radians(b["lon"] - a["lon"]) * math.cos(mean_lat) * EARTH_RADIUS_M
    north = math.radians(b["lat"] - a["lat"]) * EARTH_RADIUS_M
    return east, north


def compass(a: dict, b: dict) -> str:
    east, north = offset_m(a, b)
    bearing = math.degrees(math.atan2(east, north)) % 360
    return COMPASS[int((bearing + 22.5) // 45) % 8]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")  # Excel "CSV UTF-8" and Numbers add a byte-order mark
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1252")  # Excel "CSV (Comma delimited)" on Windows, e.g. a ° in a lat
    except UnicodeDecodeError:
        raise SystemExit(f"ERROR {path}: not UTF-8 or Windows-1252 text; re-save it as CSV UTF-8") from None
    print(f"note: {path} is not UTF-8; read it as Windows-1252 (Excel 'CSV (Comma delimited)')")
    return text


def read_rows(path: Path, name_file: bool = False) -> list[dict]:
    """The log's rows; name_file (several logs): messages say 'row 3 of <file>' instead of 'row 3'."""
    reader = csv.DictReader(io.StringIO(read_text(path), newline=""))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(f"ERROR {path}: missing columns {', '.join(missing)} "
                         "(header must match data/staged/clip_log_template.csv)")
    rows = []
    for line, raw in enumerate(reader, 2):
        row = {k: (v or "").strip() for k, v in raw.items() if k}
        if any(row.values()):
            rows.append({**row, "_line": f"{line} of {path.name}" if name_file else line})
    return rows


def parse_row(row: dict, problems: Problems, clocked: bool) -> dict:
    """One CSV row -> typed values (None where the cell was bad; problems says why). clocked: the row's take shows
    a clock, so each of its route rows needs both clock cells."""
    role = row["role"]
    on_route = role in ROUTE_ROLES
    take = problems.cell(row, "take", _take)
    out = {
        "line": row["_line"], "take": take, "role": role, "where": where(row),
        "activity": problems.cell(row, "activity", lambda s: _choice(s, ACTIVITIES, "activity")),
        "camera_id": problems.cell(row, "camera_id", _camera_id),
        "spot": row.get("spot_description", ""),
        "lat": problems.cell(row, "lat", lambda s: parse_coord(s, "lat")),
        "lon": problems.cell(row, "lon", lambda s: parse_coord(s, "lon")),
        "heading": problems.cell(row, "heading_deg", _heading, required=False),
        "clip_file": problems.cell(row, "clip_file", _clip_file),
        # decoy clips start with the camera they branch off, so their clock cells are never read
        "shown_at": problems.cell(row, "clock_shown_at_s", parse_seconds, required=clocked) if on_route else None,
        "clock": problems.cell(row, "clock_reading_hhmmss", parse_clock, required=clocked) if on_route else None,
        "enter": problems.cell(row, "suspect_enter_s", parse_seconds, required=on_route),
        "exit": problems.cell(row, "suspect_exit_s", parse_seconds, required=on_route),
        "travel": problems.cell(row, "travel_s", parse_seconds, required=False),
    }
    if role not in ROLES:
        problems.append(f"{where(row)}, column 'role': must be one of {', '.join(ROLES)}")
    word = ROLE_WORDS.search(out["spot"])
    if word:
        problems.append(f"{where(row)}, column 'spot_description': {word.group(0)!r} gives away the camera's role "
                        "or the crime, and the description becomes the camera name that models see; "
                        "describe the place instead, e.g. 'west door' or 'bike rack'")
    word = ROLE_WORDS.search(out["clip_file"] or "")
    if word:
        print(f"WARNING {where(row)}: clip_file {out['clip_file']!r} contains {word.group(0)!r}; the file name "
              f"goes into cameras.json (source.uri), so consider renaming the clip without {word.group(0)!r}")
    if on_route and out["enter"] is not None and out["exit"] is not None and out["exit"] <= out["enter"]:
        problems.append(f"{where(row)}: suspect_exit_s must be after suspect_enter_s")
    if role == "decoy" and (row.get("suspect_enter_s") or row.get("suspect_exit_s")):
        print(f"WARNING {where(row)}: decoy is an empty path; ignoring its suspect times")
    if role == "crime":
        m = OUTFIT.search(row.get("notes", ""))
        out["outfit"] = m.group(1).strip() if m else ""
        if not out["outfit"]:
            problems.append(f"{where(row)}, column 'notes': missing 'suspect outfit: <description>'")
    if role == "decoy":
        out["stopwatch"] = decoy_walk(row, out["travel"], problems)
    return out


def decoy_walk(row: dict, travel: float | None, problems: Problems) -> float | None:
    """Seconds from the split to the decoy: the decoy row's travel_s, else 'stopwatch s: N' in its notes."""
    if travel is not None:
        if travel > 0:
            return travel
        problems.append(f"{where(row)}, column 'travel_s': must be > 0 (the walk to the decoy)")
        return None
    m = STOPWATCH.search(row.get("notes", ""))
    if not m or not m.group(1):
        problems.append(f"{where(row)}, column 'notes': missing 'stopwatch s: <seconds>' "
                        "(the junction -> decoy walk), or fill travel_s")
        return None
    try:
        return _positive(parse_seconds(m.group(1)))
    except ValueError as e:
        problems.append(f"{where(row)}, column 'notes': stopwatch {e}{got(m.group(1), e)}")
        return None


def _choice(value, allowed, name: str):
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(map(str, allowed))}")
    return value


def _take(text: str) -> int:
    if text not in {str(n) for n in TAKE_OFFSETS}:
        raise ValueError(f"take must be one of {', '.join(map(str, TAKE_OFFSETS))}")
    return int(text)


def parse_run_offset(text: str) -> float | dict[int, float]:
    """--run-offset: seconds for every take built ('0'), or per take ('3=0,2=7')."""
    def seconds(value: str) -> float:
        try:
            s = float(value)
        except ValueError:
            s = math.nan
        if not (math.isfinite(s) and s >= 0):
            raise SystemExit(f"ERROR --run-offset: expected seconds >= 0 (got {value!r})")
        return s

    if "=" not in text:
        return seconds(text.strip())
    offsets = {}
    for part in text.split(","):
        take, sep, value = part.partition("=")
        try:
            n = _take(take.strip())
        except ValueError as e:
            raise SystemExit(f"ERROR --run-offset: {e} (got {take.strip()!r} in {text!r})") from None
        if not sep or n in offsets:
            raise SystemExit(f"ERROR --run-offset: expected TAKE=SECONDS pairs like 3=0,2=7, each take once "
                             f"(got {text!r})")
        offsets[n] = seconds(value.strip())
    return offsets


def take_offset(n: int, run_offset: float | dict[int, float] | None) -> float:
    if isinstance(run_offset, dict):
        return run_offset.get(n, TAKE_OFFSETS[n])
    return TAKE_OFFSETS[n] if run_offset is None else run_offset


def _camera_id(text: str) -> str:
    if not CAMERA_ID.match(text):
        raise ValueError("must be cam_01 ... cam_12")
    return text


def _clip_file(text: str) -> str:
    if "/" in text or "\\" in text:
        raise ValueError("file name only; the take folder is added automatically")
    return text


def _heading(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise ValueError("expected compass degrees 0-360 (0 = north, 90 = east)") from None
    if not (math.isfinite(value) and 0 <= value <= 360):
        raise ValueError("must be compass degrees 0-360 (0 = north, 90 = east)")
    return value


def _positive(value: float) -> float:
    if value <= 0:
        raise ValueError("must be > 0")
    return value


def build_take(n: int, rows: list[dict], problems: Problems, clocked: bool, run_speed: float,
               offset: float) -> dict | None:
    """Put one take's clips on the run clock (its crime at offset + CRIME_AT_S); returns its route, path, links
    and clip start times."""
    first: dict[str, dict] = {}
    for r in rows:
        if r["role"] in ONE_PER_TAKE and r["role"] in first:
            problems.append(f"{r['where']}: take {n} has two '{r['role']}' rows "
                            f"(also row {first[r['role']]['line']})")
        first.setdefault(r["role"], r)
    missing = " or ".join(f"'{role}'" for role in ("crime", "exit") if role not in first)
    if missing:
        problems.append(f"take {n}: no {missing} row (a take needs a crime row and, last on its route, an exit row)")
        return None
    activities = {r["activity"] for r in rows if r["activity"]}
    if len(activities) > 1:
        problems.append(f"take {n}: rows disagree on activity ({', '.join(sorted(activities))})")
    route = sorted((r for r in rows if r["role"] in ROUTE_ROLES), key=lambda r: ROUTE_RANK[r["role"]])
    decoy = first.get("decoy")
    for i, r in enumerate(route):
        if r["travel"] is not None and (clocked or i == 0):
            why = "this take's clock sets its timing" if clocked else "no route camera comes before it"
            print(f"WARNING {r['where']}: ignoring travel_s ({why})")

    hops = None if clocked else [hop_seconds(a, b, run_speed, problems) for a, b in zip(route, route[1:])]
    timing = ("shown_at", "clock", "enter", "exit") if clocked else ("enter", "exit")
    if any(r[k] is None for r in rows for k in ("camera_id", "lat", "lon")) or any(
            r[k] is None for r in route for k in timing) or None in (hops or []):
        return None  # cell errors already recorded
    start_ts = clock_starts(offset, route, problems) if clocked else chained_starts(offset, route, hops)

    path = [{"camera_id": r["camera_id"],
             "t_enter": round(start_ts[r["camera_id"]] + r["enter"], 2),
             "t_exit": round(start_ts[r["camera_id"]] + r["exit"], 2)} for r in route]
    for prev, cur, r in zip(path, path[1:], route[1:]):
        if cur["t_enter"] <= prev["t_enter"]:
            problems.append(f"{r['where']}: suspect enters {cur['camera_id']} at run-clock "
                            f"{cur['t_enter']} s, not after {prev['camera_id']} ({prev['t_enter']} s); "
                            "check the clock and suspect_enter_s cells")
    links = {(a["camera_id"], b["camera_id"]): walk(a, b) for a, b in zip(path, path[1:])}
    if decoy:
        if decoy["stopwatch"] is None:
            return None
        split = route[-2]["camera_id"]
        start_ts[decoy["camera_id"]] = start_ts[split]  # the empty decoy clip plays with the camera it branches off
        links[(split, decoy["camera_id"])] = decoy["stopwatch"]
    return {"take": n, "offset": offset, "route": route, "decoy": decoy, "clocked": clocked, "start_ts": start_ts,
            "path": path, "links": {k: round(v, 1) for k, v in links.items()}}


def clock_starts(offset: float, route: list[dict], problems: Problems) -> dict[str, float]:
    """Run-clock start of each route clip from the clock it shows. The crime clip is placed so the suspect enters
    it at offset + CRIME_AT_S; the other clips keep their clock gap to it."""
    first = {r["camera_id"]: r["clock"] - r["shown_at"] for r in route}  # wall time of each clip's first frame
    crime = next(r for r in route if r["role"] == "crime")
    crime_start = offset + CRIME_AT_S - crime["enter"]
    start_ts = {}
    for r in route:
        gap = first[r["camera_id"]] - first[crime["camera_id"]]
        if abs(gap) > MAX_CLOCK_GAP_S:
            problems.append(f"{r['where']}: clip starts {abs(gap):.0f} s "
                            f"{'after' if gap > 0 else 'before'} the take's crime clip; check "
                            "clock_reading_hhmmss (same clock for the whole take?)")
        start_ts[r["camera_id"]] = round(crime_start + gap, 2)
    return start_ts


def chained_starts(offset: float, route: list[dict], hops: list[float]) -> dict[str, float]:
    """Run-clock start of each route clip without a clock: the crime as in clock_starts; after it, enter = the
    previous camera's exit + the hop; before it (the approach), exit = the next camera's enter - the hop."""
    k = next(i for i, r in enumerate(route) if r["role"] == "crime")
    start_ts = {route[k]["camera_id"]: round(offset + CRIME_AT_S - route[k]["enter"], 2)}
    for i in range(k + 1, len(route)):
        prev, cur = route[i - 1], route[i]
        start_ts[cur["camera_id"]] = round(start_ts[prev["camera_id"]] + prev["exit"] + hops[i - 1] - cur["enter"], 2)
    for i in range(k - 1, -1, -1):
        cur, nxt = route[i], route[i + 1]
        start_ts[cur["camera_id"]] = round(start_ts[nxt["camera_id"]] + nxt["enter"] - hops[i] - cur["exit"], 2)
    return start_ts


def hop_seconds(prev: dict, cur: dict, run_speed: float, problems: Problems) -> float | None:
    """Seconds from prev's view to cur's in a take without a clock: cur's travel_s, else the straight-line
    distance at run_speed. Rounded to 0.1 s (what cameras.json keeps), so ground truth and the graph agree."""
    if cur["travel"] is not None:
        return round(cur["travel"], 1)
    if None in (prev["lat"], prev["lon"], cur["lat"], cur["lon"]):
        problems.append(f"{cur['where']}: no travel_s, and no lat/lon on both {prev['camera_id']} and "
                        f"{cur['camera_id']} to work it out from; fill travel_s (seconds from "
                        f"{prev['camera_id']}) or the lat/lon")
        return None
    return round(math.hypot(*offset_m(prev, cur)) / run_speed, 1)


def walk(prev: dict, cur: dict) -> float:
    """Walking time between two cameras: suspect leaves prev, enters cur (0 when the views overlap)."""
    return max(0.0, cur["t_enter"] - prev["t_exit"])


def check_positions(rows: list[dict], problems: Problems) -> None:
    for r in rows:
        if r["lat"] is None or r["lon"] is None:
            continue
        east, north = offset_m(ANNEX_REF, r)
        km = math.hypot(east, north) / 1000
        if km <= MAX_FROM_ANNEX_M / 1000:
            continue
        cols = [col for col, off in (("lat", north), ("lon", east)) if abs(off) > MAX_FROM_ANNEX_M] or ["lat", "lon"]
        hint = {"lat": "Raleigh lat is positive, e.g. 35.775 (or N, not S)",
                "lon": "Raleigh lon is negative, e.g. -78.637 (or W, not E)"}
        named = f"column{'s' * (len(cols) > 1)} {' and '.join(repr(c) for c in cols)}"
        problems.append(f"{r['where']}, {named}: {r['camera_id']} is {km:,.1f} km from the Red Hat Annex; "
                        f"check the sign and format: {'; '.join(hint[c] for c in cols)}")


def check_links(takes: list[dict], cams: dict[str, dict], problems: Problems) -> None:
    for t in takes:
        for (a, b) in t["links"]:
            if math.hypot(*offset_m(cams[a], cams[b])) < MIN_SEPARATION_M:
                problems.append(f"take {t['take']}: {a} and {b} have the same lat/lon, so there's no "
                                "direction between them; log more precise positions (decimal degrees)")


def warn_same_direction(cameras: list[dict]) -> None:
    """The graph predicts the next camera from the walking direction, so no camera may have two neighbors in the
    same 8-way direction (a split's exit and decoy, or GPS error larger than the gap between cameras)."""
    for cam in cameras:
        by_way: dict[str, list[str]] = {}
        for nb in cam["neighbors"]:
            by_way.setdefault(nb["direction"], []).append(nb["camera_id"])
        for way, ids in by_way.items():
            if len(ids) > 1:
                print(f"WARNING {cam['camera_id']}: its neighbors {' and '.join(ids)} are "
                      f"{'both' if len(ids) == 2 else 'all'} {way} of it, so the graph can't tell them apart by "
                      "direction; re-check their lat/lon (for a decoy: film it on another side of the split)")


def take_cameras(t: dict) -> list[dict]:
    """A take's rows: its route in order, then the decoy if it has one."""
    return t["route"] + ([t["decoy"]] if t["decoy"] else [])


def check_clips(takes: list[dict], clip_dir: Path, problems: Problems) -> None:
    """Every clip_file must exist in clip_dir/take<N>/ with the exact case (Linux file names are case-sensitive)."""
    if not clip_dir.is_dir():
        problems.append(f"--check-clips: folder {clip_dir} not found")
        return
    for t in takes:
        folder = clip_dir / f"take{t['take']}"
        if folder.name not in os.listdir(clip_dir) or not folder.is_dir():
            problems.append(f"take {t['take']}: clip folder {folder} not found (expected exactly 'take{t['take']}')")
            continue
        names = set(os.listdir(folder))
        for r in take_cameras(t):
            if r["clip_file"] in names:
                continue
            near = sorted(x for x in names if x.lower() == r["clip_file"].lower())
            hint = (f"; found {near[0]!r}: the upper/lower case differs, and the Brev box (Linux) treats them as "
                    "different files" if near else "")
            problems.append(f"{r['where']}: clip {r['clip_file']!r} not found in {folder}{hint}")


def mean_center(rows: list[dict]) -> dict:
    return {"lat": round(sum(r["lat"] for r in rows) / len(rows), 6),
            "lon": round(sum(r["lon"] for r in rows) / len(rows), 6)}


def cameras_json(takes: list[dict], cams: dict[str, dict], site_id: str = SITE_ID,
                 site_name: str = SITE_NAME) -> dict:
    neighbors: dict[str, list[dict]] = {cam: [] for cam in cams}
    for t in takes:
        for (a, b), travel in t["links"].items():
            neighbors[a].append({"camera_id": b, "travel_time_s": travel, "direction": compass(cams[a], cams[b])})
            neighbors[b].append({"camera_id": a, "travel_time_s": travel, "direction": compass(cams[b], cams[a])})
    cameras = []
    for t in takes:
        in_take = sorted(r["camera_id"] for r in take_cameras(t))
        for r in take_cameras(t):
            # neutral on purpose: no role words (models may see names); k follows camera_id, not role
            spot = r["spot"] or f"camera {in_take.index(r['camera_id']) + 1}"
            name = f"Route {t['take']}: {spot}"
            cameras.append({
                "camera_id": r["camera_id"], "name": name, "take": t["take"],
                "position": {"lat": round(r["lat"], 7), "lon": round(r["lon"], 7)},
                "site_xy": None, "heading_deg": None if r["heading"] is None else round(r["heading"], 1),
                "neighbors": sorted(neighbors[r["camera_id"]], key=lambda nb: nb["camera_id"]),
                "source": {"kind": "replay", "uri": f"data/raw/staged/take{t['take']}/{r['clip_file']}",
                           "start_ts": t["start_ts"][r["camera_id"]]},
            })
    cameras.sort(key=lambda cam: cam["camera_id"])
    return {"schema_version": "0.1", "site_id": site_id, "site_name": site_name,
            "map": {"center": mean_center(list(cams.values())), "zoom": 18, "site_image": None},
            "cameras": cameras}


def ground_truth(t: dict, site_id: str = SITE_ID) -> dict:
    crime = next(r for r in t["route"] if r["role"] == "crime")
    return {"site_id": site_id, "take": t["take"], "run_offset_s": t["offset"],
            "incident_id": f"inc_take{t['take']}", "subject_id": f"subj_take{t['take']}",
            "activity": crime["activity"], "appearance": crime["outfit"],
            "path": t["path"], "decoy_camera_id": t["decoy"]["camera_id"] if t["decoy"] else None,
            "camera_roles": {r["camera_id"]: r["role"] for r in take_cameras(t)}}


def manifest(takes: list[dict], site_id: str = SITE_ID) -> dict:
    clips = {}
    for t in takes:
        for r in take_cameras(t):
            clips[r["camera_id"]] = {"take": t["take"], "clip_file": r["clip_file"],
                                     "uri": f"data/raw/staged/take{t['take']}/{r['clip_file']}",
                                     "start_ts": t["start_ts"][r["camera_id"]]}
    return {"site_id": site_id, "clips": dict(sorted(clips.items()))}


def build(rows: list[dict], wanted: set[int] | None, clip_dir: Path | None = None,
          run_speed: float = RUN_SPEED_M_S, run_offset: float | dict[int, float] | None = None,
          site_id: str = SITE_ID, site_name: str = SITE_NAME) -> tuple[dict, list[dict], dict]:
    """run_offset: every take's run-clock offset, or {take: offset} (a take not in it, or None: TAKE_OFFSETS, so
    the takes overlap 10 s apart)."""
    problems = Problems()
    if wanted:
        rows = [r for r in rows if r.get("take") in {str(n) for n in wanted}]
    # a take is on the clock if any of its route rows has a clock cell; then every route row needs both
    clocked = {r.get("take") for r in rows
               if r.get("role") in ROUTE_ROLES and any(r.get(col) for col in CLOCK_COLUMNS)}
    parsed = [parse_row(r, problems, r.get("take") in clocked) for r in rows]
    if not parsed:
        raise SystemExit("ERROR: no rows to build (check the log or --takes)")

    seen: dict[str, dict] = {}
    for p in parsed:
        if p["camera_id"] in seen:
            problems.append(f"{p['where']}: {p['camera_id']} already used in row {seen[p['camera_id']]['line']}")
        elif p["camera_id"]:
            seen[p["camera_id"]] = p
    check_positions(parsed, problems)

    takes = []
    for n in sorted({p["take"] for p in parsed if p["take"] is not None}):
        offset = take_offset(n, run_offset)
        t = build_take(n, [p for p in parsed if p["take"] == n], problems, str(n) in clocked, run_speed, offset)
        if t:
            takes.append(t)
    if not problems:
        check_links(takes, seen, problems)
    if clip_dir is not None:
        check_clips(takes, clip_dir, problems)
    if problems:
        print(f"{len(problems)} problem(s) in the clip log; nothing written:", file=sys.stderr)
        for msg in problems:
            print(f"ERROR {msg}", file=sys.stderr)
        raise SystemExit(1)
    cameras = cameras_json(takes, seen, site_id, site_name)
    warn_same_direction(cameras["cameras"])
    return cameras, takes, manifest(takes, site_id)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", type=Path, nargs="+",
                        help="filled clip log CSV; several logs build one site from all their takes")
    parser.add_argument("--takes", default="", help="comma-separated takes to build, e.g. 1 or 1,2 (default: all)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="folder that receives data/... (default: the repo root)")
    parser.add_argument("--check-clips", type=Path, metavar="DIR",
                        help="also check every clip_file exists as DIR/take<N>/<clip_file>, exact case "
                             "(e.g. data/raw/staged)")
    parser.add_argument("--run-speed", type=float, default=RUN_SPEED_M_S, metavar="M_PER_S",
                        help="takes without a clock: escape speed for links without travel_s, used on the "
                             f"straight-line lat/lon distance (default {RUN_SPEED_M_S:g})")
    parser.add_argument("--run-offset", metavar="SECONDS",
                        help="run-clock offset of every take built, so its crime plays at SECONDS + "
                             f"{CRIME_AT_S:g} (default: 0 / 10 / 20 for takes 1/2/3, so they overlap 10 s apart; "
                             "a one-take demo site uses 0); or per take, e.g. 3=0,2=7 (a take not named keeps "
                             "its default)")
    parser.add_argument("--site-truth", action="store_true",
                        help="write ground truth to data/ground_truth/<site>/take<N>.json instead of "
                             "data/ground_truth/take<N>.json (a site that reuses takes another site already has "
                             "ground truth for, e.g. annex_multi)")
    parser.add_argument("--site", default=SITE_ID,
                        help=f"site id: writes data/sites/<site>/cameras.json and data/manifests/<site>.json "
                             f"(default {SITE_ID}; lower-case letters, digits and _)")
    parser.add_argument("--site-name", default=SITE_NAME, help=f"site name on the map (default {SITE_NAME!r})")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):  # a Windows pipe can't print every character in a cell
        stream.reconfigure(errors="replace")
    try:
        wanted = {int(x) for x in args.takes.split(",") if x.strip()} or None
    except ValueError:
        raise SystemExit(f"ERROR --takes: expected numbers like 1,2 (got {args.takes!r})")
    if not (math.isfinite(args.run_speed) and args.run_speed > 0):
        raise SystemExit(f"ERROR --run-speed: expected metres per second > 0 (got {args.run_speed:g})")
    run_offset = None if args.run_offset is None else parse_run_offset(args.run_offset)
    if not SITE_ID_FORMAT.match(args.site):
        raise SystemExit(f"ERROR --site: lower-case letters, digits and _ only, e.g. annex_clip1 (got {args.site!r})")
    if not args.site_name.strip():
        raise SystemExit("ERROR --site-name: must not be blank")

    rows = [row for log in args.log for row in read_rows(log, name_file=len(args.log) > 1)]
    cameras, takes, clips = build(rows, wanted, args.check_clips, args.run_speed, run_offset, args.site,
                                  args.site_name.strip())
    unused = sorted(set(run_offset) - {t["take"] for t in takes}) if isinstance(run_offset, dict) else []
    if unused:
        print(f"WARNING --run-offset: take {', '.join(map(str, unused))} not built, so its offset is unused")
    for t in takes:
        hops = " -> ".join(f"{p['camera_id']}@{p['t_enter']}s" for p in t["path"])
        links = ", ".join(f"{a}-{b} {s}s" for (a, b), s in t["links"].items())
        print(f"take {t['take']}: {hops} | links: {links}")
        if not t["clocked"]:
            print(f"note: take {t['take']} has no clock; its travel times are travel_s cells or the lat/lon "
                  f"distance at {args.run_speed:g} m/s")
        early = [f"{r['camera_id']} at {t['start_ts'][r['camera_id']]} s" for r in take_cameras(t)
                 if t["start_ts"][r["camera_id"]] < 0]
        if early:
            print(f"note: take {t['take']} clip(s) start before run-clock 0 ({', '.join(early)}); "
                  "feeds skips those first seconds")
    if args.check_clips:
        print(f"all {sum(len(take_cameras(t)) for t in takes)} clips found in {args.check_clips}")
    data = args.root / "data"
    truth = data / "ground_truth" / args.site if args.site_truth else data / "ground_truth"
    write_json(data / "sites" / args.site / "cameras.json", cameras)
    for t in takes:
        write_json(truth / f"take{t['take']}.json", ground_truth(t, args.site))
    write_json(data / "manifests" / f"{args.site}.json", clips)
    print(f"next: python contracts/validate.py \"{data / 'sites' / args.site / 'cameras.json'}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
