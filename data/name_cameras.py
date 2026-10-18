"""Name each camera after where it is: the closest named street and the closest named place, from OpenStreetMap.

    curl -A clarity -o data/osm/annex.osm "https://api.openstreetmap.org/api/0.6/map?bbox=-78.6395,35.7735,-78.6355,35.7770"
    python data/name_cameras.py data/sites/demo2/cameras.json --osm data/osm/annex.osm            # prints the names
    python data/name_cameras.py data/sites/demo2/cameras.json --osm data/osm/annex.osm --write    # writes them

A camera at 35.7756, -78.6371 becomes e.g. "E Davie St at Sir Walter Coffee". The names come only from the camera's own
lat/lon and the map data, nothing typed by hand, so moving a camera and re-running renames it. The map extract is one
download of the site's area from OpenStreetMap's API (© OpenStreetMap contributors, ODbL).
"""
import argparse
import json
import math
import xml.etree.ElementTree as ET

PLACE_KEYS = ("amenity", "shop", "leisure", "tourism", "office")
SHORT = {"East": "E", "West": "W", "North": "N", "South": "S", "Street": "St", "Avenue": "Ave", "Boulevard": "Blvd"}
K = 111_320.0  # metres per degree of latitude


def load_osm(path: str) -> tuple[list[tuple[str, list[tuple[float, float]]]], list[tuple[str, tuple[float, float]]]]:
    """(named roads as (name, polyline), named places as (name, point)) from an OSM XML extract."""
    root = ET.parse(path).getroot()
    nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in root.iter("node")}
    tags = lambda e: {t.get("k"): t.get("v") for t in e.iter("tag")}  # noqa: E731
    roads, places = [], []
    for w in root.iter("way"):
        t = tags(w)
        pts = [nodes[nd.get("ref")] for nd in w.iter("nd") if nd.get("ref") in nodes]
        if not pts or "name" not in t:
            continue
        if "highway" in t and t["highway"] not in ("footway", "service", "steps", "path"):
            roads.append((t["name"], pts))
        elif any(k in t for k in PLACE_KEYS):
            places.append((t["name"], (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))))
    for n in root.iter("node"):
        t = tags(n)
        if "name" in t and any(k in t for k in PLACE_KEYS):
            places.append((t["name"], nodes[n.get("id")]))
    return roads, places


def to_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metres from p to the segment a-b (flat approximation, fine at street scale)."""
    cos = math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * K * cos, (a[0] - p[0]) * K
    bx, by = (b[1] - p[1]) * K * cos, (b[0] - p[0]) * K
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def short(name: str) -> str:
    return " ".join(SHORT.get(w, w) for w in name.split())


def closest(p, pts):
    """(metres, closest point) on a polyline."""
    best = (1e9, pts[0])
    for a, b in zip(pts, pts[1:]):
        cos = math.cos(math.radians(p[0]))
        ax, ay = (a[1] - p[1]) * K * cos, (a[0] - p[0]) * K
        bx, by = (b[1] - p[1]) * K * cos, (b[0] - p[0]) * K
        dx, dy = bx - ax, by - ay
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
        d = math.hypot(ax + t * dx, ay + t * dy)
        if d < best[0]:
            best = (d, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return best


def compass(frm, to) -> str:
    """'N'/'NE'/... from point frm to point to (8-way), or the 2-letter corner when diagonal."""
    north, east = (to[0] - frm[0]) * K, (to[1] - frm[1]) * K * math.cos(math.radians(frm[0]))
    return ("N" if north > 0 else "S") + ("E" if east > 0 else "W")


def name_for(p: tuple[float, float], roads, places, corner_m: float = 30) -> str:
    """'<street> & <cross street> (<corner> corner)' near an intersection, else '<street> at <place> (<side> side)'."""
    by_road: dict[str, tuple[float, tuple[float, float]]] = {}
    for name, pts in roads:
        if len(pts) > 1:
            d = closest(p, pts)
            if name not in by_road or d[0] < by_road[name][0]:
                by_road[name] = d
    ranked = sorted(by_road.items(), key=lambda kv: kv[1][0])
    if not ranked:
        return f"{p[0]:.5f}, {p[1]:.5f}"
    street, (_, on_street) = ranked[0]
    if len(ranked) > 1 and ranked[1][1][0] <= corner_m:
        cross, (_, on_cross) = ranked[1]
        # the corner: where the camera sits relative to the crossing (north/south of the street, east/west of the cross street)
        corner = compass(on_street, p)[0] + compass(on_cross, p)[1]
        return f"{short(street)} & {short(cross)} ({corner} corner)"
    side = {"N": "north", "S": "south"}[compass(on_street, p)[0]]
    place = min(places, default=None, key=lambda pl: to_segment(p, pl[1], pl[1]))
    spot = place[0] if place and to_segment(p, place[1], place[1]) <= 60 else None
    return f"{short(street)} at {spot} ({side} side)" if spot else f"{short(street)} ({side} side)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cameras", help="a site's cameras.json")
    parser.add_argument("--osm", required=True, help="OpenStreetMap XML extract of the site's area")
    parser.add_argument("--write", action="store_true", help="write the names into cameras.json")
    args = parser.parse_args()
    roads, places = load_osm(args.osm)
    site = json.load(open(args.cameras, encoding="utf-8"))
    for c in site["cameras"]:
        c["name"] = name_for((c["position"]["lat"], c["position"]["lon"]), roads, places)
        print(f'{c["camera_id"]}: {c["name"]}')
    if args.write:
        with open(args.cameras, "w", encoding="utf-8") as f:
            json.dump(site, f, indent=2)
        print(f"wrote {args.cameras}")


if __name__ == "__main__":
    main()
