"""Camera graph built from cameras.json (neighbors + travel_time_s)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import Camera


class CameraGraph:
    def __init__(self, cameras: Iterable[Camera], edges: Iterable[tuple[str, str, float]]):
        self.cameras = {c.camera_id: c for c in cameras}
        self._adj: dict[str, dict[str, float]] = {cid: {} for cid in self.cameras}
        self._dir: dict[tuple[str, str], str] = {}  # (from, to) -> compass direction walked
        for a, b, travel_s in edges:
            self._adj.setdefault(a, {})[b] = travel_s
            self._adj.setdefault(b, {})[a] = travel_s

    @classmethod
    def from_config(cls, config: dict | list[dict]) -> "CameraGraph":
        """Build from cameras.json (contract v0.1: {"site_id", "cameras": [...]}); a bare camera list also works."""
        entries = config["cameras"] if isinstance(config, dict) else config
        cameras, edges = [], []
        directions = {}
        for c in entries:
            xy = c.get("site_xy") or {}
            cameras.append(Camera(c["camera_id"], c.get("name", c["camera_id"]), xy.get("x"), xy.get("y")))
            for n in c.get("neighbors", []):
                edges.append((c["camera_id"], n["camera_id"], float(n.get("travel_time_s", 0))))
                if n.get("direction"):
                    directions[(c["camera_id"], n["camera_id"])] = n["direction"]
        graph = cls(cameras, edges)
        graph._dir = directions
        return graph

    @classmethod
    def load(cls, path: str | Path) -> "CameraGraph":
        return cls.from_config(json.loads(Path(path).read_text()))

    def name(self, camera_id: str) -> str:
        cam = self.cameras.get(camera_id)
        return cam.name if cam else camera_id

    def direction(self, a: str, b: str) -> str | None:
        """Compass direction walked from camera a to neighbor b, if cameras.json says."""
        return self._dir.get((a, b))

    def neighbors(self, camera_id: str) -> dict[str, float]:
        """neighbor camera_id -> travel_time_s"""
        return dict(self._adj.get(camera_id, {}))
