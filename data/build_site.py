"""Build the Annex site data from the filled clip log (format: data/staged/clip_log_template.csv).

Writes (paths under --root, default the repo root):
    data/sites/annex/cameras.json    camera graph: positions, neighbors, travel times, clip sources
    data/ground_truth/take<N>.json   per incident: subject, activity, outfit, path on the run clock
    data/manifests/annex.json        camera_id -> clip file + start_ts, for feeds/

Clock sync: every clip shows a seconds clock. At clip second `clock_shown_at_s` the clock reads
`clock_reading_hhmmss`, so clip second t is wall time reading + (t - clock_shown_at_s). Within a
take, the earliest first frame among the crime/junction/exit clips is run-clock = take offset
(+0 / +10 / +20 s for takes 1/2/3), which replays the three separately filmed takes overlapped on
one clock with no clip starting before its take's offset. Decoy clips (an empty path, filmed
separately) ignore their clock and start with the junction clip.

Travel times: crime->junction and junction->exit are differences of suspect_enter times on the run
clock; junction->decoy is the logged walk ("stopwatch s: N" in the decoy row's notes). Directions
come from lat/lon (8-way compass). Every link is written both ways.

Accepted cell formats:
    lat / lon            35.77531 and -78.63702, or iPhone Compass style 35°46'31"N and 78°38'13"W
                         (spaces work instead of the symbols: 35 46 31 N)
    clip seconds         23.5, or m:ss like 0:23.5
    clock_reading        HH:MM:SS (or HHMMSS); one clock per take, 12 h or 24 h
    file encoding        UTF-8 (with or without BOM), or Windows-1252 (Excel "CSV (Comma delimited)")
phone_owner, spot_description and the decoy rows' clock cells are optional (spot_description goes into the camera name;
phone_owner is never copied into the outputs). Every other blank cell is an error.

Run from the repo root (stdlib only):
    python data/build_site.py data/staged/clip_log.csv
    python data/build_site.py data/staged/clip_log.csv --takes 1      # only take 1 is logged so far
Then check: python contracts/validate.py data/sites/annex/cameras.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

SITE_ID = "annex"
ROLES = ("crime", "junction", "exit", "decoy")
ROLE_NAMES = {"crime": "crime spot", "junction": "junction", "exit": "exit", "decoy": "decoy exit"}
PATH_ROLES = ("crime", "junction", "exit")
TAKE_OFFSETS = {1: 0.0, 2: 10.0, 3: 20.0}
ACTIVITIES = ("stabbing", "fistfight", "purse_snatch")
COLUMNS = ("take", "activity", "role", "camera_id", "phone_owner", "spot_description", "lat", "lon",
           "clip_file", "clock_shown_at_s", "clock_reading_hhmmss", "suspect_enter_s",
           "suspect_exit_s", "notes")
CAMERA_ID = re.compile(r"^cam_(0[1-9]|1[0-2])$")
# Decimal degrees, or degrees-minutes-seconds with symbols or spaces: 35°46'31"N, 35 46 31 N
COORD = re.compile(r"""^(-?\d+(?:\.\d+)?)(?:\s*°\s*|\s+)?(?:(\d+(?:\.\d+)?)(?:\s*['′]\s*|\s+)?)?"""
                   r"""(?:(\d+(?:\.\d+)?)\s*(?:"|″|'')?\s*)?([NSEW])?$""", re.IGNORECASE)
COORD_EXAMPLE = {"lat": "35.77531 or 35°46'31\"N", "lon": "-78.63702 or 78°38'13\"W"}
OUTFIT = re.compile(r"suspect outfit:\s*([^;]*)", re.IGNORECASE)
STOPWATCH = re.compile(r"stopwatch s:\s*([0-9:.]*)", re.IGNORECASE)
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


def read_rows(path: Path) -> list[dict]:
    reader = csv.DictReader(io.StringIO(read_text(path), newline=""))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(f"ERROR {path}: missing columns {', '.join(missing)} "
                         "(header must match data/staged/clip_log_template.csv)")
    rows = []
    for line, raw in enumerate(reader, 2):
        row = {k: (v or "").strip() for k, v in raw.items() if k}
        if any(row.values()):
            rows.append({**row, "_line": line})
    return rows


def parse_row(row: dict, problems: Problems) -> dict:
    """One CSV row -> typed values (None where the cell was bad; problems says why)."""
    role = row["role"]
    on_path = role in PATH_ROLES
    take = problems.cell(row, "take", _take)
    out = {
        "line": row["_line"], "take": take, "role": role, "where": where(row),
        "activity": problems.cell(row, "activity", lambda s: _choice(s, ACTIVITIES, "activity")),
        "camera_id": problems.cell(row, "camera_id", _camera_id),
        "spot": row.get("spot_description", ""),
        "lat": problems.cell(row, "lat", lambda s: parse_coord(s, "lat")),
        "lon": problems.cell(row, "lon", lambda s: parse_coord(s, "lon")),
        "clip_file": problems.cell(row, "clip_file", _clip_file),
        # decoy clips are aligned to the junction clip, so their clock cells are never read
        "shown_at": problems.cell(row, "clock_shown_at_s", parse_seconds) if on_path else None,
        "clock": problems.cell(row, "clock_reading_hhmmss", parse_clock) if on_path else None,
        "enter": problems.cell(row, "suspect_enter_s", parse_seconds, required=on_path),
        "exit": problems.cell(row, "suspect_exit_s", parse_seconds, required=on_path),
    }
    if role not in ROLES:
        problems.append(f"{where(row)}, column 'role': must be one of {', '.join(ROLES)}")
    if on_path and out["enter"] is not None and out["exit"] is not None and out["exit"] <= out["enter"]:
        problems.append(f"{where(row)}: suspect_exit_s must be after suspect_enter_s")
    if role == "decoy" and (row.get("suspect_enter_s") or row.get("suspect_exit_s")):
        print(f"WARNING {where(row)}: decoy is an empty path; ignoring its suspect times")
    if role == "crime":
        m = OUTFIT.search(row.get("notes", ""))
        out["outfit"] = m.group(1).strip() if m else ""
        if not out["outfit"]:
            problems.append(f"{where(row)}, column 'notes': missing 'suspect outfit: <description>'")
    if role == "decoy":
        m = STOPWATCH.search(row.get("notes", ""))
        out["stopwatch"] = None
        if not m or not m.group(1):
            problems.append(f"{where(row)}, column 'notes': missing 'stopwatch s: <seconds>' "
                            "(the junction -> decoy walk)")
        else:
            try:
                out["stopwatch"] = _positive(parse_seconds(m.group(1)))
            except ValueError as e:
                problems.append(f"{where(row)}, column 'notes': stopwatch {e}{got(m.group(1), e)}")
    return out


def _choice(value, allowed, name: str):
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(map(str, allowed))}")
    return value


def _take(text: str) -> int:
    if text not in {str(n) for n in TAKE_OFFSETS}:
        raise ValueError(f"take must be one of {', '.join(map(str, TAKE_OFFSETS))}")
    return int(text)


def _camera_id(text: str) -> str:
    if not CAMERA_ID.match(text):
        raise ValueError("must be cam_01 ... cam_12")
    return text


def _clip_file(text: str) -> str:
    if "/" in text or "\\" in text:
        raise ValueError("file name only; the take folder is added automatically")
    return text


def _positive(value: float) -> float:
    if value <= 0:
        raise ValueError("must be > 0")
    return value


def build_take(n: int, rows: list[dict], problems: Problems) -> dict | None:
    """Sync one take's clips onto the run clock; returns its path, links and clip start times."""
    by_role: dict[str, dict] = {}
    for r in rows:
        if r["role"] in by_role:
            problems.append(f"{r['where']}: take {n} has two '{r['role']}' rows "
                            f"(also row {by_role[r['role']]['line']})")
        by_role.setdefault(r["role"], r)
    missing = [role for role in ROLES if role not in by_role]
    if missing:
        problems.append(f"take {n}: no row for role(s) {', '.join(missing)}")
        return None
    activities = {r["activity"] for r in rows if r["activity"]}
    if len(activities) > 1:
        problems.append(f"take {n}: rows disagree on activity ({', '.join(sorted(activities))})")
    if any(r[k] is None for r in rows for k in ("camera_id", "lat", "lon")) or any(
            by_role[role][k] is None for role in PATH_ROLES for k in ("shown_at", "clock", "enter", "exit")):
        return None  # cell errors already recorded

    # Wall time of each path clip's first frame; the earliest is run-clock = take offset, so no clip
    # starts before the offset (events need ts >= 0). The empty decoy clip plays with the junction.
    first = {role: by_role[role]["clock"] - by_role[role]["shown_at"] for role in PATH_ROLES}
    earliest = min(first.values())
    start_ts = {}
    for role in PATH_ROLES:
        gap = first[role] - earliest
        if gap > MAX_CLOCK_GAP_S:
            problems.append(f"{by_role[role]['where']}: clip starts {gap:.0f} s after the take's earliest "
                            "clip; check clock_reading_hhmmss (same clock for the whole take?)")
        start_ts[role] = round(TAKE_OFFSETS[n] + gap, 2)
    start_ts["decoy"] = start_ts["junction"]

    path = [{"camera_id": by_role[role]["camera_id"],
             "t_enter": round(start_ts[role] + by_role[role]["enter"], 2),
             "t_exit": round(start_ts[role] + by_role[role]["exit"], 2)} for role in PATH_ROLES]
    for prev, cur, role in zip(path, path[1:], PATH_ROLES[1:]):
        if cur["t_enter"] <= prev["t_enter"]:
            problems.append(f"{by_role[role]['where']}: suspect enters {cur['camera_id']} at run-clock "
                            f"{cur['t_enter']} s, not after {prev['camera_id']} ({prev['t_enter']} s); "
                            "check the clock and suspect_enter_s cells")

    decoy = by_role["decoy"]
    if decoy["stopwatch"] is None:
        return None

    c, j, e = (by_role[role]["camera_id"] for role in PATH_ROLES)
    links = {(c, j): path[1]["t_enter"] - path[0]["t_enter"],
             (j, e): path[2]["t_enter"] - path[1]["t_enter"],
             (j, decoy["camera_id"]): decoy["stopwatch"]}
    return {"take": n, "by_role": by_role, "start_ts": start_ts, "path": path,
            "links": {k: round(v, 1) for k, v in links.items()}}


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


def mean_center(rows: list[dict]) -> dict:
    return {"lat": round(sum(r["lat"] for r in rows) / len(rows), 6),
            "lon": round(sum(r["lon"] for r in rows) / len(rows), 6)}


def cameras_json(takes: list[dict], cams: dict[str, dict]) -> dict:
    neighbors: dict[str, list[dict]] = {cam: [] for cam in cams}
    for t in takes:
        for (a, b), travel in t["links"].items():
            neighbors[a].append({"camera_id": b, "travel_time_s": travel, "direction": compass(cams[a], cams[b])})
            neighbors[b].append({"camera_id": a, "travel_time_s": travel, "direction": compass(cams[b], cams[a])})
    cameras = []
    for t in takes:
        for role in ROLES:
            r = t["by_role"][role]
            name = f"Route {t['take']}: {ROLE_NAMES[role]}" + (f" ({r['spot']})" if r["spot"] else "")
            cameras.append({
                "camera_id": r["camera_id"], "name": name, "take": t["take"], "role": role,
                "position": {"lat": round(r["lat"], 7), "lon": round(r["lon"], 7)},
                "site_xy": None, "heading_deg": None,
                "neighbors": sorted(neighbors[r["camera_id"]], key=lambda nb: nb["camera_id"]),
                "source": {"kind": "replay", "uri": f"data/raw/staged/take{t['take']}/{r['clip_file']}",
                           "start_ts": t["start_ts"][role]},
            })
    cameras.sort(key=lambda cam: cam["camera_id"])
    return {"schema_version": "0.1", "site_id": SITE_ID, "site_name": "Red Hat Annex (staged takes)",
            "map": {"center": mean_center(list(cams.values())), "zoom": 18, "site_image": None},
            "cameras": cameras}


def ground_truth(t: dict) -> dict:
    crime = t["by_role"]["crime"]
    return {"site_id": SITE_ID, "take": t["take"], "run_offset_s": TAKE_OFFSETS[t["take"]],
            "incident_id": f"inc_take{t['take']}", "subject_id": f"subj_take{t['take']}",
            "activity": crime["activity"], "appearance": crime["outfit"],
            "path": t["path"], "decoy_camera_id": t["by_role"]["decoy"]["camera_id"]}


def manifest(takes: list[dict]) -> dict:
    clips = {}
    for t in takes:
        for role in ROLES:
            r = t["by_role"][role]
            clips[r["camera_id"]] = {"take": t["take"], "role": role, "clip_file": r["clip_file"],
                                     "uri": f"data/raw/staged/take{t['take']}/{r['clip_file']}",
                                     "start_ts": t["start_ts"][role]}
    return {"site_id": SITE_ID, "clips": dict(sorted(clips.items()))}


def build(rows: list[dict], wanted: set[int] | None) -> tuple[dict, list[dict], dict]:
    problems = Problems()
    if wanted:
        rows = [r for r in rows if r.get("take") in {str(n) for n in wanted}]
    parsed = [parse_row(r, problems) for r in rows]
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
        t = build_take(n, [p for p in parsed if p["take"] == n], problems)
        if t:
            takes.append(t)
    if not problems:
        check_links(takes, seen, problems)
    if problems:
        print(f"{len(problems)} problem(s) in the clip log; nothing written:", file=sys.stderr)
        for msg in problems:
            print(f"ERROR {msg}", file=sys.stderr)
        raise SystemExit(1)
    return cameras_json(takes, seen), takes, manifest(takes)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", type=Path, help="filled clip log CSV")
    parser.add_argument("--takes", default="", help="comma-separated takes to build, e.g. 1 or 1,2 (default: all)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="folder that receives data/... (default: the repo root)")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):  # a Windows pipe can't print every character in a cell
        stream.reconfigure(errors="replace")
    try:
        wanted = {int(x) for x in args.takes.split(",") if x.strip()} or None
    except ValueError:
        raise SystemExit(f"ERROR --takes: expected numbers like 1,2 (got {args.takes!r})")

    cameras, takes, clips = build(read_rows(args.log), wanted)
    for t in takes:
        hops = " -> ".join(f"{p['camera_id']}@{p['t_enter']}s" for p in t["path"])
        links = ", ".join(f"{a}-{b} {s}s" for (a, b), s in t["links"].items())
        print(f"take {t['take']}: {hops} | links: {links}")
    data = args.root / "data"
    write_json(data / "sites" / SITE_ID / "cameras.json", cameras)
    for t in takes:
        write_json(data / "ground_truth" / f"take{t['take']}.json", ground_truth(t))
    write_json(data / "manifests" / f"{SITE_ID}.json", clips)
    print(f"next: python contracts/validate.py \"{data / 'sites' / SITE_ID / 'cameras.json'}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
