// Map label layout check without a browser. Node 24 runs this .ts file directly.
//
//   npm run check:labels                               placeholder cameras.json, default fit, 3 sizes
//   npm run check:labels -- path/to/cameras.json       any site
//
// Reproduces Leaflet's default fit (FIT_OPTIONS padding, zoomSnap .25, Web Mercator) for the map
// column at 1920x1080 (full screen and in a browser window), estimates label widths twice (generous:
// ~0.5 em per character; measured: ~0.4 em, Barlow Semi Condensed 500 from its font file), then runs
// the real placement code. Narrower labels can land side by side, which is how two names nearly touched.
// Passes when no label covers another marker, label or map control, labels keep LABEL_TUNING.labelGap
// apart, every label stays in view, no label sits between its camera and another one (unless a leader
// line ties it to its own camera), and every camera's verdict badge has a clear spot in view.
// Also prints a denser synthetic layout (same site at 1/2 and 1/3 scale) to show the 13 px and
// leader-line fallbacks; those are informational.
// Exit code 0 = all checks passed.

import placeholderSite from '../../data/sites/annex_placeholder/cameras.json' with { type: 'json' };
import type { Camera, CamerasConfig } from '../src/lib/types.ts';
import { awayFromNeighbors, badgeRect, layoutLabels, chooseSmall, placeBadges, LABEL_TUNING } from '../src/map/labels.ts';
import type { LabelBox, LabelInput, LabelLayout, Rect, Vec } from '../src/map/labels.ts';

declare const process: { argv: string[]; cwd(): string; exit(code?: number): never };

// Mirrors of the map constants (CameraMarker.tsx LABEL_FONT / MARKER_PX, FitToCameras.tsx FIT_OPTIONS).
const MARKER_R = 9;
const ALERT_R = 16;
const FONT = { namePx: 15, nameSmallPx: 13, subPx: 13, lineHeight: 1.15 };
const PAD_TL: Vec = [170, 56];
const PAD_BR: Vec = [170, 64];
const ZOOM_SNAP = 0.25;
const MAX_ZOOM = 19;
/** Label width estimates, em per character: generous, and measured from the Barlow Semi Condensed font file. */
const WIDTHS = [['generous', 0.5], ['measured', 0.4]] as const;
let EM_PER_CHAR = 0.5;
/** Badge: the wider of "✕ no match" / "? uncertain" at 14 px (sizes.ts BADGE), padding 8 + border 1 a side. */
const badgeBox = (): LabelBox => ({ w: textW('? uncertain', 14) + 18, h: 22 });

/** A cameras.json path from the command line as a file URL (relative to the current folder). */
function fileUrl(path: string): URL {
  const slashed = path.replaceAll('\\', '/');
  if (/^[A-Za-z]:\//.test(slashed)) return new URL(`file:///${slashed}`);
  const cwd = process.cwd().replaceAll('\\', '/').replace(/^\/+/, '');
  return new URL(slashed, `file:///${cwd}/`);
}
const arg = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : null;
const site = (arg
  ? (await import(fileUrl(arg).href, { with: { type: 'json' } })).default
  : placeholderSite) as CamerasConfig;

const failures: string[] = [];
function check(ok: boolean, what: string): void {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${what}`);
  if (!ok) failures.push(what);
}

function project(lat: number, lon: number, z: number): Vec {
  const scale = 256 * 2 ** z;
  const phi = (lat * Math.PI) / 180;
  return [scale * (lon + 180) / 360, scale * (1 - Math.log(Math.tan(phi) + 1 / Math.cos(phi)) / Math.PI) / 2];
}

function fitZoom(cams: readonly Camera[], w: number, h: number): number {
  const lats = cams.map((c) => c.position!.lat), lons = cams.map((c) => c.position!.lon);
  const nw = project(Math.max(...lats), Math.min(...lons), 0);
  const se = project(Math.min(...lats), Math.max(...lons), 0);
  const sx = (w - PAD_TL[0] - PAD_BR[0]) / Math.max(se[0] - nw[0], 1e-12);
  const sy = (h - PAD_TL[1] - PAD_BR[1]) / Math.max(se[1] - nw[1], 1e-12);
  let z = Math.log2(Math.min(sx, sy));
  z = Math.round(z / (ZOOM_SNAP / 100)) * (ZOOM_SNAP / 100);
  z = Math.floor(z / ZOOM_SNAP) * ZOOM_SNAP;
  return Math.min(z, MAX_ZOOM);
}

function textW(s: string, px: number): number {
  return Math.ceil(s.length * px * EM_PER_CHAR) + 2;
}

function screenPositions(cams: readonly Camera[], w: number, h: number): { z: number; pos: Map<string, Vec> } {
  const z = fitZoom(cams, w, h);
  const lats = cams.map((c) => c.position!.lat), lons = cams.map((c) => c.position!.lon);
  const nw = project(Math.max(...lats), Math.min(...lons), z);
  const se = project(Math.min(...lats), Math.max(...lons), z);
  // fitBounds centers the padded box: offset by (paddingBR - paddingTL) / 2.
  const cx = (nw[0] + se[0]) / 2 + (PAD_BR[0] - PAD_TL[0]) / 2;
  const cy = (nw[1] + se[1]) / 2 + (PAD_BR[1] - PAD_TL[1]) / 2;
  const pos = new Map<string, Vec>();
  for (const c of cams) {
    const p = project(c.position!.lat, c.position!.lon, z);
    pos.set(c.camera_id, [p[0] - cx + w / 2, p[1] - cy + h / 2]);
  }
  return { z, pos };
}

function inputs(cams: readonly Camera[], pos: Map<string, Vec>, alerts: ReadonlySet<string>, withSub: boolean): LabelInput[] {
  return cams.map((c) => {
    const name = (c.name ?? '').trim() || c.camera_id;
    const sub = withSub && alerts.has(c.camera_id) ? ['Purse snatch'] : [];
    const subW = Math.max(0, ...sub.map((s) => textW(s, FONT.subPx)));
    const subH = sub.length * FONT.subPx * FONT.lineHeight;
    const [x, y] = pos.get(c.camera_id)!;
    return {
      id: c.camera_id, x, y,
      big: { w: Math.max(textW(name, FONT.namePx), subW), h: Math.ceil(FONT.namePx * FONT.lineHeight + subH) },
      small: { w: Math.max(textW(name, FONT.nameSmallPx), subW), h: Math.ceil(FONT.nameSmallPx * FONT.lineHeight + subH) },
      away: awayFromNeighbors(c, (id) => pos.get(id) ?? null),
      markerR: withSub && alerts.has(c.camera_id) ? ALERT_R : MARKER_R,
    };
  });
}

function labelRect(item: LabelInput, layout: LabelLayout): Rect {
  const p = layout.byId.get(item.id)!;
  const box = layout.small ? item.small : item.big;
  const x0 = item.x + p.ax - p.fx * box.w, y0 = item.y + p.ay - p.fy * box.h;
  return { x0, y0, x1: x0 + box.w, y1: y0 + box.h };
}

function run(label: string, cams: readonly Camera[], w: number, h: number, alerts: ReadonlySet<string>, strict: boolean): void {
  const { z, pos } = screenPositions(cams, w, h);
  const view: Rect = { x0: 2, y0: 2, x1: w - 2, y1: h - 2 };
  const blocked: Rect[] = [
    { x0: 10, y0: h - 10 - 58, x1: 40, y1: h - 10 },   // zoom control, bottom left
    { x0: w - 190, y0: h - 18, x1: w, y1: h },          // attribution, bottom right
  ];
  const opts = { view, blocked };
  const small = chooseSmall(inputs(cams, pos, alerts, false), opts);
  const items = inputs(cams, pos, alerts, true);
  const layout = layoutLabels(items, small, opts);
  const out = items.filter((it) => {
    const r = labelRect(it, layout);
    return r.x0 < view.x0 || r.y0 < view.y0 || r.x1 > view.x1 || r.y1 > view.y1;
  }).map((it) => it.id);
  const sides = items.map((it) => `${it.id}:${layout.byId.get(it.id)!.side}${layout.byId.get(it.id)!.leader ? '+leader' : ''}`);
  let minGap = Infinity, closest = '';
  items.forEach((a, i) => items.slice(i + 1).forEach((b) => {
    const g = gap(labelRect(a, layout), labelRect(b, layout));
    if (g < minGap) { minGap = g; closest = `${a.id}/${b.id}`; }
  }));
  // Badges: every camera gets a side; its box must clear every label and other marker, and stay in view.
  const bBox = badgeBox();
  const neighbors = new Map(cams.map((c) => [c.camera_id, (c.neighbors ?? []).map((n) => n.camera_id)]));
  const badges = placeBadges(items, layout, bBox, opts, neighbors);
  const onLine = items.filter((it) => {
    const r = badgeRect(it, badges.get(it.id)!, bBox);
    return (neighbors.get(it.id) ?? []).some((id) => {
      const n = items.find((o) => o.id === id);
      return n && segmentCrosses(it.x, it.y, n.x, n.y, r);
    });
  }).map((it) => `${it.id}:${badges.get(it.id)}`);
  const badBadges = items.filter((it) => {
    const r = badgeRect(it, badges.get(it.id)!, bBox);
    const inView = r.x0 >= view.x0 && r.y0 >= view.y0 && r.x1 <= view.x1 && r.y1 <= view.y1;
    return !inView || blocked.some((b) => overlaps(r, b)) || items.some((o) => overlaps(r, labelRect(o, layout))
      || (o !== it && hitsCircle(r, o.x, o.y, o.markerR)));
  }).map((it) => `${it.id}:${badges.get(it.id)}`);
  console.log(`\n${label}  ${w}x${h}  ${EM_PER_CHAR} em  zoom ${z}  names ${layout.small ? '13' : '15'} px  collisions ${layout.collisions}  leaders ${layout.leaders}  between ${layout.ambiguous}  out of view ${out.length}  min label gap ${minGap.toFixed(1)} (${closest})`);
  console.log(`      ${sides.join('  ')}`);
  console.log(`      badges ${items.map((it) => `${it.id}:${badges.get(it.id)}`).join('  ')}  (on a neighbor line: ${onLine.join(', ') || 'none'})`);
  const untied = layoutLabels(items, small, { ...opts, tie: false });
  console.log(`      (without the between-cameras rule: ${untied.ambiguous} label(s) would sit between two cameras)`);
  if (strict) {
    check(layout.collisions === 0, `${label} ${w}x${h}: no label covers a marker, label or control`);
    check(out.length === 0, `${label} ${w}x${h}: every label inside the map${out.length ? ` (out: ${out.join(', ')})` : ''}`);
    check(layout.ambiguous === 0, `${label} ${w}x${h}: no label sits between its camera and another (or it has a leader)`);
    check(minGap >= LABEL_TUNING.labelGap,
      `${label} ${w}x${h}: labels at least ${LABEL_TUNING.labelGap}px apart (closest ${minGap.toFixed(1)}px, ${closest})`);
    check(badBadges.length === 0,
      `${label} ${w}x${h}: every verdict badge clear of labels, markers and controls, in view${badBadges.length ? ` (bad: ${badBadges.join(', ')})` : ''}`);
  }
}

function gap(a: Rect, b: Rect): number {
  return Math.hypot(Math.max(0, a.x0 - b.x1, b.x0 - a.x1), Math.max(0, a.y0 - b.y1, b.y0 - a.y1));
}

function overlaps(a: Rect, b: Rect): boolean {
  return Math.min(a.x1, b.x1) > Math.max(a.x0, b.x0) && Math.min(a.y1, b.y1) > Math.max(a.y0, b.y0);
}

/** Does the segment cross the rectangle? (sampled; fine for a report line) */
function segmentCrosses(ax: number, ay: number, bx: number, by: number, r: Rect): boolean {
  for (let i = 0; i <= 200; i++) {
    const x = ax + ((bx - ax) * i) / 200, y = ay + ((by - ay) * i) / 200;
    if (x > r.x0 && x < r.x1 && y > r.y0 && y < r.y1) return true;
  }
  return false;
}

function hitsCircle(r: Rect, x: number, y: number, radius: number): boolean {
  const nx = Math.max(r.x0, Math.min(x, r.x1)), ny = Math.max(r.y0, Math.min(y, r.y1));
  return Math.hypot(x - nx, y - ny) < radius;
}

function scaled(cams: readonly Camera[], k: number): Camera[] {
  const lat0 = cams[0].position!.lat, lon0 = cams[0].position!.lon;
  return cams.map((c) => ({
    ...c,
    position: { lat: lat0 + (c.position!.lat - lat0) * k, lon: lon0 + (c.position!.lon - lon0) * k },
  }));
}

const cams = site.cameras.filter((c) => c.position && Number.isFinite(c.position.lat) && Number.isFinite(c.position.lon));
console.log(`${site.site_id}: ${cams.length} cameras with lat/lon; halo ${LABEL_TUNING.halo}px, label gap ${LABEL_TUNING.labelGap}px`);

// Map column = 60% of 1920 = 1152 px wide; height = viewport - 48 px header (- ~38 px banner).
const sizes: [number, number][] = [[1152, 1032], [1152, 896], [1152, 858]];
const alertIds = new Set(cams.slice(0, 3).map((c) => c.camera_id).concat(cams.length > 6 ? [cams[5].camera_id] : []));
// The fake scenario's three crime cameras (the first camera of each route on the placeholder site).
const crimeIds = new Set([0, 4, 8].filter((i) => i < cams.length).map((i) => cams[i].camera_id));
for (const [widthName, em] of WIDTHS) {
  EM_PER_CHAR = em;
  console.log(`\n===== ${widthName} label widths (${em} em per character)`);
  for (const [w, h] of sizes) {
    run('names only', cams, w, h, new Set(), true);
    run(`alerts at ${[...alertIds].join(',')}`, cams, w, h, alertIds, true);
    run(`alerts at ${[...crimeIds].join(',')}`, cams, w, h, crimeIds, true);
  }

  // Unnamed cameras fall back to their camera_id.
  const unnamed = cams.map((c, i) => (i % 3 === 0 ? { ...c, name: '' } : c));
  run('every 3rd camera unnamed', unnamed, 1152, 896, new Set(), true);

  // Denser synthetic layouts (informational): the fallbacks kick in.
  for (const k of [0.5, 0.33]) run(`synthetic ${k}x scale`, scaled(cams, k), 1152, 896, alertIds, false);
}

console.log(failures.length ? `\n${failures.length} check(s) failed` : '\nAll label checks passed');
process.exit(failures.length ? 1 : 0);
