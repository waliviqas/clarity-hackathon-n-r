// Camera positions -> things Leaflet needs. Pure: no React, no Leaflet runtime (type imports only),
// so plain Node can run it.

import type { LatLngBoundsLiteral } from 'leaflet';
import type { Camera } from '../lib';

export interface PlacedCamera {
  camera: Camera;
  lat: number;
  lon: number;
}

function validLatLon(lat: unknown, lon: unknown): boolean {
  return typeof lat === 'number' && typeof lon === 'number' && Number.isFinite(lat) && Number.isFinite(lon)
    && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

/** Cameras with a usable lat/lon (site_xy-only cameras, e.g. a schematic site, are skipped). */
export function placeCameras(list: readonly Camera[]): PlacedCamera[] {
  const out: PlacedCamera[] = [];
  for (const camera of list) {
    const p = camera.position;
    if (p && validLatLon(p.lat, p.lon)) out.push({ camera, lat: p.lat, lon: p.lon });
  }
  return out;
}

/** Changes only when the camera layout does (not when a snapshot re-sends the same cameras.json). */
export function layoutKey(siteId: string | undefined, placed: readonly PlacedCamera[]): string {
  return `${siteId ?? ''}|${placed.map((p) => `${p.camera.camera_id}@${p.lat},${p.lon}`).join(';')}`;
}

/** [[south, west], [north, east]] around every placed camera, or null if none has a position. */
export function boundsOf(placed: readonly PlacedCamera[]): LatLngBoundsLiteral | null {
  if (!placed.length) return null;
  let s = Infinity, w = Infinity, n = -Infinity, e = -Infinity;
  for (const p of placed) {
    s = Math.min(s, p.lat); n = Math.max(n, p.lat);
    w = Math.min(w, p.lon); e = Math.max(e, p.lon);
  }
  return [[s, w], [n, e]];
}
