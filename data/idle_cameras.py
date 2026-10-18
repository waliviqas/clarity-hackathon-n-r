"""Idle camera spots evenly along every sidewalk in an OpenStreetMap extract, for the dashboard's map.

    python data/idle_cameras.py --osm data/osm/annex.osm --cameras data/sites/demo2/cameras.json \\
        --out dashboard/public/idle/demo2.json

They stand for the rest of a city's camera network: drawn as small grey dots, with no video and no agent behind them.
Only the cameras in cameras.json are watched by the models. Spots come from the sidewalks' geometry (OSM
footway=sidewalk), one every --spacing metres, skipping any within --clear metres of a real camera.
"""
import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

K = 111_320.0  # metres per degree of latitude


def sidewalks(path: str) -> list[list[tuple[float, float]]]:
    root = ET.parse(path).getroot()
    nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in root.iter("node")}
    out = []
    for w in root.iter("way"):
        tags = {t.get("k"): t.get("v") for t in w.iter("tag")}
        if tags.get("footway") == "sidewalk" or tags.get("highway") == "footway" and tags.get("footway") == "sidewalk":
            pts = [nodes[nd.get("ref")] for nd in w.iter("nd") if nd.get("ref") in nodes]
            if len(pts) > 1:
                out.append(pts)
    return out


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot((b[0] - a[0]) * K, (b[1] - a[1]) * K * math.cos(math.radians(a[0])))


def evenly(line: list[tuple[float, float]], spacing: float) -> list[tuple[float, float]]:
    """Points every `spacing` metres along a polyline, centred so both ends get the same margin."""
    lengths = [metres(a, b) for a, b in zip(line, line[1:])]
    total = sum(lengths)
    if total < spacing / 2:
        return []
    n = max(1, int(total // spacing))
    targets = [(total - (n - 1) * spacing) / 2 + i * spacing for i in range(n)]
    out, walked, seg = [], 0.0, 0
    for t in targets:
        while seg < len(lengths) - 1 and walked + lengths[seg] < t:
            walked += lengths[seg]
            seg += 1
        f = 0.0 if lengths[seg] == 0 else min(1.0, (t - walked) / lengths[seg])
        a, b = line[seg], line[seg + 1]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--osm", required=True, help="OpenStreetMap XML extract of the area")
    parser.add_argument("--cameras", required=True, help="the site's cameras.json (real cameras are kept clear)")
    parser.add_argument("--out", required=True, help="JSON file the dashboard loads")
    parser.add_argument("--spacing", type=float, default=25, help="metres between idle cameras (default 25)")
    parser.add_argument("--clear", type=float, default=10, help="no idle camera this close to a real one (default 10 m)")
    args = parser.parse_args()
    real = [(c["position"]["lat"], c["position"]["lon"]) for c in json.load(open(args.cameras))["cameras"]]
    spots: list[tuple[float, float]] = []
    for line in sidewalks(args.osm):
        for p in evenly(line, args.spacing):
            if all(metres(p, r) > args.clear for r in real) and all(metres(p, s) > args.spacing / 2 for s in spots):
                spots.append(p)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"idle_cameras": [{"lat": round(a, 6), "lon": round(b, 6)} for a, b in spots]}))
    print(f"{len(spots)} idle camera spots -> {args.out}")


if __name__ == "__main__":
    main()
