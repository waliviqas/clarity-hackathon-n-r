import { useEffect, useMemo, useState } from 'react';
import type { LatLngTuple, Map as LeafletMap } from 'leaflet';
import { useMap, useMapEvents } from 'react-leaflet';
import { cameraName, getState, isCrimeActivity, LABELS, select, useCameraStatus, useLiveDetections } from '../lib';
import type { Camera, CameraHealth } from '../lib';
import { ALERT_RING_R, CameraMarker, LABEL_FONT, MARKER_PX } from './CameraMarker.tsx';
import { BADGE } from './sizes.ts';
import type { ChaseView } from './chase.ts';
import type { Circle } from './chaseGeometry.ts';
import { ChaseLayer } from './ChaseLayer.tsx';
import type { ChaseAvoid } from './ChaseLayer.tsx';
import type { PlacedCamera } from './geo.ts';
import { awayFromNeighbors, chooseSmall, layoutLabels, placeBadges } from './labels.ts';
import type { LabelBox, LabelInput, LabelLayout, LabelSide, Rect, Vec } from './labels.ts';

interface CamLabelSpec {
  camera: Camera;
  lat: number;
  lon: number;
  name: string;
  /** Extra label lines under the name (crime activity, camera health). */
  sub: string[];
  alert: boolean;
}

interface CameraLayerProps {
  placed: readonly PlacedCamera[];
  /** camera_id -> [lat, lon] of the placed cameras. */
  posById: ReadonlyMap<string, LatLngTuple>;
  chase: ChaseView;
}

const NO_AVOID: ChaseAvoid = { rects: [], circles: [] };

/**
 * The cameras and the chases between them: markers with labels placed so they don't cover each
 * other or other markers, then the paths / arrows / predictions underneath (their "70%" labels keep
 * clear of the camera labels). Lives inside <MapContainer> because placement needs the map's zoom and size.
 */
export function CameraLayer({ placed, posById, chase }: CameraLayerProps) {
  const map = useMap();
  const status = useCameraStatus();
  const live = useLiveDetections();
  const viewTick = useMapViewTick(map);
  const fontTick = useFontsTick();
  // A click on the empty map clears the selection (lines and arrows stop their clicks from reaching it).
  useMapEvents({ click: () => { if (getState().selection !== null) select(null); } });

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

  const avoid = layout ? layout.avoid : NO_AVOID;
  return (
    <>
      <ChaseLayer chase={chase} posById={posById} avoid={avoid} viewTick={viewTick} />
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
          label={layout?.layout.byId.get(c.camera.camera_id) ?? null}
          badgeSide={layout?.badges.get(c.camera.camera_id) ?? null}
          small={layout?.layout.small ?? false}
          fill={chase.cameras.get(c.camera.camera_id)?.fill ?? null}
          highlighted={chase.cameras.get(c.camera.camera_id)?.highlighted ?? false}
          badge={chase.cameras.get(c.camera.camera_id)?.badge ?? null}
        />
      ))}
    </>
  );
}

function healthWord(health: CameraHealth | undefined): string {
  return (health && LABELS.cameraHealth[health]) ?? String(health);
}

// ---------- layout ----------

interface CameraLayout {
  layout: LabelLayout;
  /** camera_id -> side of its verdict badge (away from its label, clear of other labels and markers). */
  badges: Map<string, LabelSide>;
  avoid: ChaseAvoid;
}

/** Label layout and badge sides, plus what the chase labels must avoid (label boxes, marker dots, map controls). */
function computeLayout(map: LeafletMap, specs: readonly CamLabelSpec[]): CameraLayout | null {
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
  const items = inputs(true);
  const layout = layoutLabels(items, small, opts);
  const neighbors = new Map(specs.map((s) => [s.camera.camera_id, (s.camera.neighbors ?? []).map((n) => n.camera_id)]));
  const badges = placeBadges(items, layout, badgeBox(), opts, neighbors);

  const rects: Rect[] = [...blocked];
  const circles: Circle[] = [];
  for (const it of items) {
    circles.push({ x: it.x, y: it.y, r: it.markerR + 3 });
    const p = layout.byId.get(it.id);
    if (!p) continue;
    const box = small ? it.small : it.big;
    const x0 = it.x + p.ax - p.fx * box.w, y0 = it.y + p.ay - p.fy * box.h;
    rects.push({ x0: x0 - 3, y0: y0 - 3, x1: x0 + box.w + 3, y1: y0 + box.h + 3 });
  }
  return { layout, badges, avoid: { rects, circles } };
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

/** The widest verdict badge (both kinds share one box, so a badge never changes the layout). */
function badgeBox(): LabelBox {
  const w = Math.max(...Object.values(LABELS.verdictBadge).map((t) => textWidth(t, BADGE.fontWeight, BADGE.fontPx)));
  return { w: Math.ceil(w) + 2 * (BADGE.padX + BADGE.border) + 2, h: BADGE.height };
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
