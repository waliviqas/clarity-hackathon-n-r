import { useEffect, useMemo, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { useMap } from 'react-leaflet';
import { cameraName, isCrimeActivity, LABELS, useCameraStatus, useLiveDetections } from '../lib';
import type { Camera, CameraHealth } from '../lib';
import { ALERT_RING_R, CameraMarker, LABEL_FONT, MARKER_PX } from './CameraMarker.tsx';
import type { PlacedCamera } from './geo.ts';
import { awayFromNeighbors, chooseSmall, layoutLabels } from './labels.ts';
import type { LabelInput, LabelLayout, Rect, Vec } from './labels.ts';

interface CamLabelSpec {
  camera: Camera;
  lat: number;
  lon: number;
  name: string;
  /** Extra label lines under the name (crime activity, camera health). */
  sub: string[];
  alert: boolean;
}

/**
 * All camera markers, with labels placed so they don't cover each other or other markers.
 * Lives inside <MapContainer> because placement needs the map's current zoom and size.
 */
export function CameraLayer({ placed }: { placed: readonly PlacedCamera[] }) {
  const map = useMap();
  const status = useCameraStatus();
  const live = useLiveDetections();
  const viewTick = useMapViewTick(map);
  const fontTick = useFontsTick();

  const cams = placed.map(({ camera, lat, lon }) => {
    const seen = live.get(camera.camera_id);
    const crime = seen?.crime?.activity;
    const health = status[camera.camera_id]?.status;
    return {
      camera, lat, lon, health,
      offline: health !== undefined && health !== 'online',
      crimeActivity: isCrimeActivity(crime) ? crime : null,
      pulseId: seen?.latest.event_id ?? null,
      pulseCrime: isCrimeActivity(seen?.latest.activity),
    };
  });

  // What the labels say: re-layout only when this (or the view) changes, not on every pulse.
  const specs: CamLabelSpec[] = cams.map((c) => ({
    camera: c.camera, lat: c.lat, lon: c.lon,
    name: cameraName(c.camera),
    sub: [
      ...(c.crimeActivity ? [LABELS.activity[c.crimeActivity]] : []),
      ...(c.offline ? [healthWord(c.health)] : []),
    ],
    alert: c.crimeActivity !== null,
  }));
  const specKey = specs.map((s) => {
    const nb = (s.camera.neighbors ?? []).map((n) => `${n.camera_id}:${n.direction}`).join(',');
    return `${s.camera.camera_id}@${s.lat},${s.lon}|${s.name}|${s.sub.join('/')}|${nb}`;
  }).join(';');
  const layout = useMemo(
    () => computeLayout(map, specs),
    // specKey stands for specs (a new array every render).
    [map, specKey, viewTick, fontTick],
  );

  return (
    <>
      {cams.map((c, i) => (
        <CameraMarker
          key={c.camera.camera_id}
          name={specs[i].name}
          lat={c.lat}
          lon={c.lon}
          health={c.health}
          pulseId={c.pulseId}
          pulseCrime={c.pulseCrime}
          crimeActivity={c.crimeActivity}
          label={layout?.byId.get(c.camera.camera_id) ?? null}
          small={layout?.small ?? false}
        />
      ))}
    </>
  );
}

function healthWord(health: CameraHealth | undefined): string {
  return (health && LABELS.cameraHealth[health]) ?? String(health);
}

// ---------- layout ----------

function computeLayout(map: LeafletMap, specs: readonly CamLabelSpec[]): LabelLayout | null {
  const size = map.getSize();
  if (!specs.length || size.x === 0 || size.y === 0) return null;

  const screen = new Map<string, Vec>();
  for (const s of specs) {
    const p = map.latLngToContainerPoint([s.lat, s.lon]);
    screen.set(s.camera.camera_id, [p.x, p.y]);
  }
  const screenOf = (id: string) => screen.get(id) ?? null;

  const view: Rect = { x0: 2, y0: 2, x1: size.x - 2, y1: size.y - 2 };
  const blocked = controlRects(map);
  const opts = { view, blocked };

  const inputs = (withSub: boolean): LabelInput[] => specs.map((s) => {
    const [x, y] = screen.get(s.camera.camera_id)!;
    const sub = withSub ? s.sub : [];
    return {
      id: s.camera.camera_id, x, y,
      big: measureLabel(s.name, sub, false),
      small: measureLabel(s.name, sub, true),
      away: awayFromNeighbors(s.camera, screenOf),
      markerR: withSub && s.alert ? ALERT_RING_R : MARKER_PX / 2,
    };
  });

  // Size from the names alone (stable while alerts come and go), placement from the full labels.
  const small = chooseSmall(inputs(false), opts);
  return layoutLabels(inputs(true), small, opts);
}

/** Map controls (zoom buttons, attribution) in container pixels: labels stay off them. */
function controlRects(map: LeafletMap): Rect[] {
  const container = map.getContainer();
  const box = container.getBoundingClientRect();
  const out: Rect[] = [];
  container.querySelectorAll('.leaflet-control').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      out.push({ x0: r.left - box.left, y0: r.top - box.top, x1: r.right - box.left, y1: r.bottom - box.top });
    }
  });
  return out;
}

// ---------- text measurement (canvas; mirrors .cam-label in map.css) ----------

let ctx: CanvasRenderingContext2D | null | undefined;
let family: string | null = null;

function fontFamily(): string {
  if (family === null) {
    family = getComputedStyle(document.documentElement).getPropertyValue('--font-sign').trim()
      || "'Barlow Semi Condensed', sans-serif";
  }
  return family;
}

function textWidth(text: string, weight: number, px: number): number {
  if (ctx === undefined) ctx = document.createElement('canvas').getContext('2d');
  if (!ctx) return text.length * px * 0.5; // no canvas: rough estimate
  ctx.font = `${weight} ${px}px ${fontFamily()}`;
  return ctx.measureText(text).width;
}

function measureLabel(name: string, sub: readonly string[], small: boolean) {
  const f = LABEL_FONT;
  const namePx = small ? f.nameSmallPx : f.namePx;
  let w = textWidth(name, f.nameWeight, namePx);
  let h = namePx * f.lineHeight;
  for (const line of sub) {
    w = Math.max(w, textWidth(line, f.subWeight, f.subPx));
    h += f.subPx * f.lineHeight;
  }
  return { w: Math.ceil(w) + 2, h: Math.ceil(h) };
}

// ---------- re-layout triggers ----------

/** Bumps after every zoom, pan or resize of the map (and once after mount, when controls exist). */
function useMapViewTick(map: LeafletMap): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const bump = () => setTick((t) => t + 1);
    map.on('zoomend moveend resize viewreset', bump);
    bump();
    return () => { map.off('zoomend moveend resize viewreset', bump); };
  }, [map]);
  return tick;
}

/** Bumps when web fonts finish loading, so labels are measured with the real font. */
function useFontsTick(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const fonts = document.fonts;
    if (!fonts) return;
    let alive = true;
    const bump = () => { if (alive) setTick((t) => t + 1); };
    const f = LABEL_FONT;
    void Promise.all([
      fonts.load(`${f.nameWeight} ${f.namePx}px ${fontFamily()}`),
      fonts.load(`${f.subWeight} ${f.subPx}px ${fontFamily()}`),
    ]).then(bump, () => {});
    fonts.addEventListener('loadingdone', bump);
    return () => { alive = false; fonts.removeEventListener('loadingdone', bump); };
  }, []);
  return tick;
}
