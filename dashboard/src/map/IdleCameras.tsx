import { useEffect, useMemo, useState } from 'react';
import type { LatLngTuple } from 'leaflet';
import type { ChaseSegment } from './chase.ts';
import { CircleMarker, Pane } from 'react-leaflet';

/**
 * The rest of the camera network: idle dots evenly along the sidewalks (public/idle/<site_id>.json, made by
 * data/idle_cameras.py from OpenStreetMap). No video or agent behind them; only cameras.json cameras are watched.
 */
/** Metres from p to segment a-b (flat approximation at street scale). */
function toSegment(p: LatLngTuple, a: LatLngTuple, b: LatLngTuple): number {
  const k = 111_320, cos = Math.cos((p[0] * Math.PI) / 180);
  const ax = (a[1] - p[1]) * k * cos, ay = (a[0] - p[0]) * k, bx = (b[1] - p[1]) * k * cos, by = (b[0] - p[0]) * k;
  const dx = bx - ax, dy = by - ay;
  const t = dx === 0 && dy === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)));
  return Math.hypot(ax + t * dx, ay + t * dy);
}

/** An idle camera this close to a confirmed stretch of a chase lights up in that chase's color. */
const ON_PATH_M = 0; // demo: off (Wali) — set e.g. 6 to light idle dots on a confirmed path

export function IdleCameras({ siteId, segments, posById }: {
  siteId: string; segments: readonly ChaseSegment[]; posById: ReadonlyMap<string, LatLngTuple>;
}) {
  const [spots, setSpots] = useState<{ lat: number; lon: number }[]>([]);
  useEffect(() => {
    let alive = true;
    fetch(`/idle/${encodeURIComponent(siteId)}.json`)
      .then((r) => (r.ok ? r.json() : { idle_cameras: [] }))
      .then((d) => { if (alive) setSpots(Array.isArray(d.idle_cameras) ? d.idle_cameras : []); })
      .catch(() => { if (alive) setSpots([]); });
    return () => { alive = false; };
  }, [siteId]);
  // The suspect passed these: idle cameras on a confirmed path segment take that chase's color.
  const lit = useMemo(() => spots.map((s) => {
    const p: LatLngTuple = [s.lat, s.lon];
    for (const seg of segments) {
      const a = posById.get(seg.from), b = posById.get(seg.to);
      if (ON_PATH_M > 0 && a && b && toSegment(p, a, b) <= ON_PATH_M) return seg.color;
    }
    return null;
  }), [spots, segments, posById]);
  return (
    <Pane name="idle-cameras" style={{ zIndex: 405 }}>
      {spots.map((s, i) => (
        <CircleMarker key={`${i}:${lit[i] ?? ''}`} center={[s.lat, s.lon]} radius={lit[i] ? 7 : 6} interactive={false}
          pathOptions={lit[i]
            ? { color: '#E6EDF2', weight: 2, opacity: 1, fillColor: lit[i]!, fillOpacity: 1 }
            : { color: '#8EA3B3', weight: 1.5, opacity: 0.55, fillColor: '#24384A', fillOpacity: 0.9 }} />
      ))}
    </Pane>
  );
}
