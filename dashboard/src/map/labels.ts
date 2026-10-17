// Camera label placement: puts each label on a free side of its marker so no label covers another
// marker or label at the current zoom. Pure geometry (no DOM, no Leaflet), so plain Node can run it
// (scripts/check-labels.ts).
//
// How: 8 candidate sides per label (E, NE, N, ... SE), each also tried farther out with a short leader
// line. A candidate costs a lot if it overlaps another marker, label or blocked area (map controls),
// some if it leaves the view, and a little for a leader or for pointing toward the camera's neighbors
// (cameras.json neighbor directions; no usable direction = prefer the right side). Greedy, most
// crowded camera first, then two refinement passes. If the 15 px layout still collides or needs a
// leader, the whole map is laid out again with 13 px names and the better of the two wins.

import type { Camera, Direction } from '../lib/types.ts';

export type Vec = readonly [number, number];

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export const LABEL_SIDES = ['e', 'ne', 'n', 'nw', 'w', 'sw', 's', 'se'] as const;
export type LabelSide = (typeof LABEL_SIDES)[number];

const D = Math.SQRT1_2;

/** Screen direction of each side (y grows downward). */
const SIDE_VEC: Record<LabelSide, Vec> = {
  e: [1, 0], ne: [D, -D], n: [0, -1], nw: [-D, -D], w: [-1, 0], sw: [-D, D], s: [0, 1], se: [D, D],
};

/** Which point of the label box sits on the anchor, as fractions of its width / height. */
const SIDE_FRAC: Record<LabelSide, Vec> = {
  e: [0, 0.5], ne: [0, 1], n: [0.5, 1], nw: [1, 1], w: [1, 0.5], sw: [1, 0], s: [0.5, 0], se: [0, 0],
};

/** cameras.json `direction` (to the neighbor) as a screen vector; north is up. */
const DIRECTION_VEC: Partial<Record<Direction, Vec>> = {
  north: [0, -1], northeast: [D, -D], east: [1, 0], southeast: [D, D],
  south: [0, 1], southwest: [-D, D], west: [-1, 0], northwest: [-D, -D],
};

/** Tunables, in screen pixels unless noted. */
export const LABEL_TUNING = {
  /** Gap between the marker (or its alert ring) and a label to its left/right. */
  gapSide: 8,
  /** Gap above/below (line-height already adds air). */
  gapVertical: 3,
  /** Gap to a diagonal corner. */
  gapDiagonal: 4,
  /** Extra distance for a candidate drawn with a leader line. */
  leaderExtra: 22,
  /** Label boxes are grown by this much before overlap tests (the text halo, plus breathing room). */
  halo: 3,
  /** Extra clearance kept around other markers. */
  markerMargin: 3,
  /** Two markers this close count toward "crowded" when ordering. */
  crowdRadius: 160,
  cost: {
    marker: 1000,
    label: 600,
    blocked: 600,
    outOfView: 300,
    leader: 45,
    /** Facing straight at the neighbors costs this; facing away costs 0. */
    towardNeighbors: 60,
    /** Without neighbor directions: pointing left instead of right costs this. */
    notRight: 20,
  },
} as const;

export interface LabelBox {
  w: number;
  h: number;
}

export interface LabelInput {
  id: string;
  /** Marker center, screen px (e.g. Leaflet container point). */
  x: number;
  y: number;
  /** Label size with the regular (15 px) name. */
  big: LabelBox;
  /** Label size with the crowded (13 px) name. */
  small: LabelBox;
  /** Unit vector pointing away from the camera's neighbors, or null for no preference. */
  away: Vec | null;
  /** Clearance radius of the marker: the dot, or the alert ring when it shows. */
  markerR: number;
}

export interface LabelPlacement {
  side: LabelSide;
  /** Anchor relative to the marker center (px). */
  ax: number;
  ay: number;
  /** The label box point on the anchor, as fractions of its size (CSS: translate(-fx*100%, -fy*100%)). */
  fx: number;
  fy: number;
  /** Text alignment inside the label. */
  align: 'start' | 'center' | 'end';
  /** Leader line relative to the marker center, or null when the label sits right beside it. */
  leader: { x1: number; y1: number; x2: number; y2: number } | null;
}

export interface LabelLayout {
  /** true = names at 13 px (crowded). */
  small: boolean;
  byId: Map<string, LabelPlacement>;
  /** Overlaps left over (label-marker, label-label, label-control). 0 is the goal. */
  collisions: number;
  leaders: number;
}

export interface LayoutOptions {
  /** The visible map area; labels leaving it cost extra. */
  view?: Rect | null;
  /** Areas labels must stay off (zoom control, attribution). */
  blocked?: readonly Rect[];
}

interface Candidate {
  placement: LabelPlacement;
  /** Label box in screen px, before the halo. */
  rect: Rect;
  /** Cost that doesn't depend on other labels (direction, leader, view, markers, blocked). */
  base: number;
}

/**
 * Unit vector away from the camera's neighbors, from cameras.json: each neighbor's `direction`, or
 * (when it's "unknown") the on-screen bearing to that neighbor. Null when there's no usable
 * direction or the neighbors cancel out (e.g. one north, one south).
 */
export function awayFromNeighbors(
  camera: Camera, screenOf: (cameraId: string) => Vec | null,
): Vec | null {
  const self = screenOf(camera.camera_id);
  let sx = 0, sy = 0;
  for (const n of camera.neighbors ?? []) {
    let v: Vec | null = DIRECTION_VEC[n.direction] ?? null;
    if (!v && self) {
      const other = screenOf(n.camera_id);
      if (other) {
        const dx = other[0] - self[0], dy = other[1] - self[1];
        const len = Math.hypot(dx, dy);
        if (len > 0) v = [dx / len, dy / len];
      }
    }
    if (v) { sx += v[0]; sy += v[1]; }
  }
  const len = Math.hypot(sx, sy);
  return len < 0.3 ? null : [-sx / len, -sy / len];
}

function candidatesFor(item: LabelInput, box: LabelBox): Omit<Candidate, 'base'>[] {
  const t = LABEL_TUNING;
  const out: Omit<Candidate, 'base'>[] = [];
  for (const withLeader of [false, true]) {
    for (const side of LABEL_SIDES) {
      const [vx, vy] = SIDE_VEC[side];
      const [fx, fy] = SIDE_FRAC[side];
      const gap = vy === 0 ? t.gapSide : vx === 0 ? t.gapVertical : t.gapDiagonal;
      const dist = item.markerR + gap + (withLeader ? t.leaderExtra : 0);
      const ax = vx * dist, ay = vy * dist;
      const x0 = item.x + ax - fx * box.w, y0 = item.y + ay - fy * box.h;
      const leader = withLeader
        ? { x1: vx * (item.markerR + 1), y1: vy * (item.markerR + 1), x2: ax - vx * 2, y2: ay - vy * 2 }
        : null;
      out.push({
        placement: { side, ax, ay, fx, fy, align: fx === 0 ? 'start' : fx === 1 ? 'end' : 'center', leader },
        rect: { x0, y0, x1: x0 + box.w, y1: y0 + box.h },
      });
    }
  }
  return out;
}

function grow(r: Rect, by: number): Rect {
  return { x0: r.x0 - by, y0: r.y0 - by, x1: r.x1 + by, y1: r.y1 + by };
}

function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return w > 0 && h > 0 ? w * h : 0;
}

/** How far a circle reaches into a rectangle (0 = no overlap). */
function circleIntrusion(r: Rect, cx: number, cy: number, radius: number): number {
  const nx = Math.max(r.x0, Math.min(cx, r.x1));
  const ny = Math.max(r.y0, Math.min(cy, r.y1));
  const d = Math.hypot(cx - nx, cy - ny);
  return d < radius ? radius - d : 0;
}

function outsideArea(r: Rect, view: Rect): number {
  const area = (r.x1 - r.x0) * (r.y1 - r.y0);
  return area - overlapArea(r, view);
}

function baseCost(item: LabelInput, c: Omit<Candidate, 'base'>, all: readonly LabelInput[], opts: LayoutOptions): number {
  const t = LABEL_TUNING;
  const r = grow(c.rect, t.halo);
  let cost = 0;
  for (const other of all) {
    if (other === item) continue;
    const hit = circleIntrusion(r, other.x, other.y, other.markerR + t.markerMargin);
    if (hit > 0) cost += t.cost.marker + hit * 20;
  }
  for (const b of opts.blocked ?? []) {
    const a = overlapArea(r, b);
    if (a > 0) cost += t.cost.blocked + a;
  }
  if (opts.view) {
    const out = outsideArea(c.rect, opts.view);
    if (out > 0) cost += t.cost.outOfView + out;
  }
  const [vx, vy] = SIDE_VEC[c.placement.side];
  if (item.away) {
    const dot = vx * item.away[0] + vy * item.away[1];
    cost += (t.cost.towardNeighbors * (1 - dot)) / 2;
  } else {
    cost += (t.cost.notRight * (1 - vx)) / 2;
  }
  if (c.placement.leader) cost += t.cost.leader;
  return cost;
}

function labelCost(rect: Rect, others: Iterable<Rect>): number {
  const r = grow(rect, LABEL_TUNING.halo);
  let cost = 0;
  for (const o of others) {
    const a = overlapArea(r, o);
    if (a > 0) cost += LABEL_TUNING.cost.label + a;
  }
  return cost;
}

/** Lay out every label at one name size (small = 13 px names). */
export function layoutLabels(inputs: readonly LabelInput[], small: boolean, opts: LayoutOptions = {}): LabelLayout {
  const t = LABEL_TUNING;
  const cands = new Map<string, Candidate[]>();
  for (const item of inputs) {
    const box = small ? item.small : item.big;
    cands.set(item.id, candidatesFor(item, box).map((c) => ({ ...c, base: baseCost(item, c, inputs, opts) })));
  }

  // Most crowded first (ties keep input order), so the hardest labels get first pick.
  const crowd = new Map(inputs.map((a) => [a.id,
    inputs.filter((b) => b !== a && Math.hypot(a.x - b.x, a.y - b.y) < t.crowdRadius).length]));
  const order = inputs.map((item, i) => ({ item, i }))
    .sort((a, b) => (crowd.get(b.item.id)! - crowd.get(a.item.id)!) || a.i - b.i)
    .map(({ item }) => item);

  const chosen = new Map<string, Candidate>();
  const pick = (item: LabelInput) => {
    const others: Rect[] = [];
    for (const [id, c] of chosen) if (id !== item.id) others.push(c.rect);
    let best: Candidate | null = null, bestCost = Infinity;
    for (const c of cands.get(item.id)!) {
      if (c.base >= bestCost) continue;
      const cost = c.base + labelCost(c.rect, others);
      if (cost < bestCost) { best = c; bestCost = cost; }
    }
    chosen.set(item.id, best!);
  };
  for (const item of order) pick(item);
  for (let pass = 0; pass < 2; pass++) for (const item of order) pick(item);

  // Count what's left: pairwise label overlaps once, plus label-marker and label-control overlaps.
  let collisions = 0, leaders = 0;
  const list = order.map((item) => ({ item, c: chosen.get(item.id)! }));
  list.forEach(({ item, c }, i) => {
    if (c.placement.leader) leaders++;
    const r = grow(c.rect, t.halo);
    for (const other of inputs) {
      if (other !== item && circleIntrusion(r, other.x, other.y, other.markerR + t.markerMargin) > 0) collisions++;
    }
    for (const b of opts.blocked ?? []) if (overlapArea(r, b) > 0) collisions++;
    for (let j = i + 1; j < list.length; j++) if (overlapArea(r, list[j].c.rect) > 0) collisions++;
  });

  const byId = new Map<string, LabelPlacement>();
  for (const [id, c] of chosen) byId.set(id, c.placement);
  return { small, byId, collisions, leaders };
}

/**
 * Crowded? true when 15 px names can't all be placed without an overlap or a leader line and 13 px
 * does at least as well. The map decides this from the names alone (not the alert lines), so labels
 * don't change size every time an alert comes and goes.
 */
export function chooseSmall(inputs: readonly LabelInput[], opts: LayoutOptions = {}): boolean {
  const big = layoutLabels(inputs, false, opts);
  if (big.collisions === 0 && big.leaders === 0) return false;
  const small = layoutLabels(inputs, true, opts);
  return small.collisions < big.collisions
    || (small.collisions === big.collisions && small.leaders <= big.leaders);
}

/** Both steps in one: pick the name size, then lay out at it. */
export function placeLabels(inputs: readonly LabelInput[], opts: LayoutOptions = {}): LabelLayout {
  return layoutLabels(inputs, chooseSmall(inputs, opts), opts);
}
