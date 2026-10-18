// Screen geometry for the chases: arrow shapes and where the "70%" labels go. Pure (screen pixels in,
// screen pixels out), so plain Node can run it.

import type { Rect, Vec } from './labels.ts';
import { ARROW, MARKER_PX } from './sizes.ts';

export interface ArrowShape {
  /** Shaft, start -> end (the end tucks under the arrowhead). */
  line: [Vec, Vec];
  /** Triangle: tip, left corner, right corner. Null when the cameras are too close for a head. */
  head: [Vec, Vec, Vec] | null;
}

/**
 * Arrow from screen point a to b: starts outside the sending marker, the tip stops just outside the
 * receiving one. `offset` shifts it to the right of travel (two arrows going opposite ways stay apart).
 */
export function arrowShape(a: Vec, b: Vec, offset = false): ArrowShape {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len < 1) return { line: [a, b], head: null };
  const ux = dx / len, uy = dy / len;
  // Right of travel on screen (y grows downward).
  const nx = -uy, ny = ux;
  const off = offset ? ARROW.offset : 0;
  const ox = nx * off, oy = ny * off;
  const at = (d: number, side = 0): Vec => [a[0] + ux * d + ox + nx * side, a[1] + uy * d + oy + ny * side];

  if (len < ARROW.startTrim + ARROW.tipTrim + ARROW.headLen + 6) {
    // Too short for a head: a plain line between the dot edges (or centers when they overlap).
    const r = MARKER_PX / 2;
    return len > 2 * r + 2 ? { line: [at(r), at(len - r)], head: null } : { line: [at(0), at(len)], head: null };
  }
  const tipD = len - ARROW.tipTrim;
  const baseD = tipD - ARROW.headLen;
  const half = ARROW.headWidth / 2;
  return {
    line: [at(ARROW.startTrim), at(baseD + 1)],
    head: [at(tipD), at(baseD, -half), at(baseD, half)],
  };
}

export interface ProbLabelInput {
  key: string;
  /** Line ends, screen px (from = last path camera, to = predicted camera). */
  a: Vec;
  b: Vec;
  w: number;
  h: number;
}

export interface Circle {
  x: number;
  y: number;
  r: number;
}

function overlap(a: Rect, b: Rect): number {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return w > 0 && h > 0 ? w * h : 0;
}

function circleHit(r: Rect, c: Circle): number {
  const nx = Math.max(r.x0, Math.min(c.x, r.x1));
  const ny = Math.max(r.y0, Math.min(c.y, r.y1));
  const d = Math.hypot(c.x - nx, c.y - ny);
  return d < c.r ? (c.r - d) * 40 : 0;
}

/** Where along the line a label may sit (fractions from `a`), best first: the middle, then outward. */
const ALONG = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74] as const;

/**
 * Centers for the probability labels: on their line, at the first spot that covers no camera label,
 * marker, map control or other probability label (else the least-covered spot). Labels sit on the line
 * itself (an ink pill), so they never drift away from the line they describe.
 */
export function placeProbLabels(
  items: readonly ProbLabelInput[],
  avoid: { rects: readonly Rect[]; circles: readonly Circle[] },
  view: Rect | null,
): Map<string, Vec> {
  const out = new Map<string, Vec>();
  const placed: Rect[] = [];
  for (const it of items) {
    let best: Vec | null = null, bestCost = Infinity, bestRect: Rect | null = null;
    for (const t of ALONG) {
      const cx = it.a[0] + (it.b[0] - it.a[0]) * t, cy = it.a[1] + (it.b[1] - it.a[1]) * t;
      const r: Rect = { x0: cx - it.w / 2, y0: cy - it.h / 2, x1: cx + it.w / 2, y1: cy + it.h / 2 };
      let cost = 0;
      for (const o of avoid.rects) cost += overlap(r, o);
      for (const o of placed) cost += overlap(r, o) * 2;
      for (const c of avoid.circles) cost += circleHit(r, c);
      if (view) {
        const inside = overlap(r, view);
        cost += (it.w * it.h - inside) * 3;
      }
      cost += Math.abs(t - 0.5) * 4; // prefer the middle when everything else is equal
      if (cost < bestCost) { best = [cx, cy]; bestCost = cost; bestRect = r; }
      if (cost < 1) break;
    }
    if (best && bestRect) { out.set(it.key, best); placed.push(bestRect); }
  }
  return out;
}
