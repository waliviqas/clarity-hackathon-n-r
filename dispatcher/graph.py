"""Minimal weighted camera graph used for grouping and station routing.

The real camera graph is owned by #4; `from_networkx` adapts it.
"""
from __future__ import annotations

import heapq
import math
from typing import Iterable

from .models import Camera


class CameraGraph:
    def __init__(self, cameras: Iterable[Camera], edges: Iterable[tuple[str, str, float]]):
        self.cameras = {c.camera_id: c for c in cameras}
        self._adj: dict[str, dict[str, float]] = {cid: {} for cid in self.cameras}
        for a, b, w in edges:
            self._adj[a][b] = w
            self._adj[b][a] = w

    @classmethod
    def from_networkx(cls, g, weight: str = "weight") -> "CameraGraph":
        cameras = [
            Camera(str(n), d.get("name", str(n)), d.get("lat"), d.get("lon"))
            for n, d in g.nodes(data=True)
        ]
        edges = [(str(a), str(b), float(d.get(weight, 1.0))) for a, b, d in g.edges(data=True)]
        return cls(cameras, edges)

    def name(self, camera_id: str) -> str:
        cam = self.cameras.get(camera_id)
        return cam.name if cam else camera_id

    def distances_from(self, source: str) -> dict[str, float]:
        """Dijkstra from `source`; unreachable nodes are absent."""
        if source not in self._adj:
            return {}
        dist = {source: 0.0}
        heap = [(0.0, source)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]:
                continue
            for nxt, w in self._adj[node].items():
                nd = d + w
                if nd < dist.get(nxt, math.inf):
                    dist[nxt] = nd
                    heapq.heappush(heap, (nd, nxt))
        return dist

    def distance(self, a: str, b: str) -> float:
        return self.distances_from(a).get(b, math.inf)
