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
        for a, b, travel_s in edges:
            self._adj.setdefault(a, {})[b] = travel_s
            self._adj.setdefault(b, {})[a] = travel_s

    @classmethod
    def from_config(cls, entries: list[dict]) -> "CameraGraph":
        """Build from the list of camera objects in cameras.json."""
        cameras, edges = [], []
        for c in entries:
            pos = c.get("position") or {}
            cameras.append(Camera(c["camera_id"], c.get("name", c["camera_id"]), pos.get("x"), pos.get("y")))
            edges += [(c["camera_id"], n["camera_id"], float(n.get("travel_time_s", 0))) for n in c.get("neighbors", [])]
        return cls(cameras, edges)

    @classmethod
    def load(cls, path: str | Path) -> "CameraGraph":
        return cls.from_config(json.loads(Path(path).read_text()))

    def name(self, camera_id: str) -> str:
        cam = self.cameras.get(camera_id)
        return cam.name if cam else camera_id

    def neighbors(self, camera_id: str) -> dict[str, float]:
        """neighbor camera_id -> travel_time_s"""
        return dict(self._adj.get(camera_id, {}))
