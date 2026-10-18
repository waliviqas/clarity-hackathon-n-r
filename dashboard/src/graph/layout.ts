// Fixed agent-graph layout (pure, no React): cameras.json -> node positions, idle edges, spoke paths.
//
// The layout reads only the neighbor graph, never the wording of camera names (names are neutral on purpose):
//   route    = a connected component of the cameras.json neighbor graph, ordered by its lowest camera_id.
//              Titled "Route N" from a "Route N:" name prefix, else numbered in order.
//   junction = the camera with >= 3 neighbors (the most, if several). Its neighbors go in cameras.json
//              order: the first sits left of the junction, the others fork off to the right:
//
//       first ── junction ─┬─ second          (staggered heights so labels never share a line)
//                          └─ third
//
//   no junction -> the route is a simple chain in neighbor order, zigzagging so neighbouring labels sit
//   at different heights. Cameras with no neighbors share "Other cameras" groups, so nothing is dropped.
//
// Every camera's line to the coordinator drops straight down to a shared bend line and then fans into
// the coordinator in left-to-right order, so no line crosses another line.
//
// Labels: the shapes above leave room for LABEL_MAX characters. When a name is longer and the panel has
// room (few cameras, e.g. a 3-camera site), every horizontal distance grows by the same factor, which
// makes room for labels that much longer, up to LABEL_WIDE. Short names or a full panel (the 12-camera
// placeholder) keep factor 1, the layout above as it is.
// Units are SVG viewBox units, sized so that at 1080p (graph panel ~770 x 270 px) 1 unit ~ 1 px.

import type { Camera } from '../lib';

/** Where a camera sits in its group (from the neighbor graph only; says nothing about what happened there). */
export type Slot = 'left' | 'junction' | 'fork' | 'chain' | 'single';

export interface GraphNode {
  camera_id: string;
  /** Full camera name, or the camera_id if it has none (tooltips). */
  name: string;
  /** Short on-screen label: the name without its group's "Route N:" prefix and any "(...)" detail. */
  label: string;
  x: number;
  y: number;
  slot: Slot;
  group: number;
}

export interface GraphGroup {
  /** "Route 1", or "Other cameras" for cameras with no neighbors. */
  title: string;
  /** x of the group's title (left edge). */
  x: number;
}

export interface GraphLayout {
  width: number;
  height: number;
  nodes: readonly GraphNode[];
  byId: Readonly<Record<string, GraphNode>>;
  groups: readonly GraphGroup[];
  /** Undirected idle camera-camera edges from cameras.json neighbors, as edgeKey(a, b). */
  edges: readonly string[];
  coordinator: { x: number; y: number; w: number; h: number };
  /** camera_id -> SVG path from the camera to its port on the coordinator (drawn in that direction). */
  spokes: Readonly<Record<string, string>>;
  /** camera_id -> point on the spoke's straight drop where a "no match" / "uncertain" mark sits. */
  marks: Readonly<Record<string, { x: number; y: number }>>;
}

export const NODE_R = 9;
const W_MIN = 760;
const H = 268;
/** Group's left edge -> its first node (room for that node's label). */
const GROUP_PAD = 44;
/** Group's last node -> its right edge. That label may overhang into the next group's pad, one line lower. */
const GROUP_RIGHT = 20;
/** Narrowest group: room for a title like "Route 3  Purse snatch". */
const GROUP_MIN = 196;
const TITLE_DX = -30;
/** Rough width of the longest group title ("Route 3  Purse snatch", 15px semibold). */
const TITLE_W = 150;
/** Half of a long label (14 characters at 14px measure ~85-105 px), so the outermost labels stay in view (times the spread). */
const LABEL_HALF = 50;
const MARGIN = 4;
/** Where every spoke stops dropping and starts fanning into the coordinator. */
const BEND_Y = 146;
const COORD = { y: 238, w: 140, h: 30 };
const PORT_INSET = 14;

// Junction shape. x offsets run from the group's first node; y is absolute. Labels sit 17 above each node.
/** The junction's first neighbor sits lower than the junction so the two labels don't share a line. */
const LEFT_Y = 104;
const JUNCTION_Y = 84;
const LEFT_TO_JUNCTION = 72;
/** Junction -> first fork camera, then each next fork camera this much further right (staggered). */
const FORK_DX = 58;
const FORK_STEP = 54;
const FORK_Y_PAIR = [56, 120];
const FORK_Y_TOP = 54;
const FORK_Y_BOTTOM = 126;
/** Cameras further along a branch: same height, far enough apart that two full labels fit side by side. */
const DEEP_STEP = 92;
const DEEP_ZIG = 30;
/** Chains and "Other cameras": zigzag between two heights. */
const ZIG_STEP = 60;
const ZIG_Y = [70, 108];
const OTHER_PER_GROUP = 4;
/** Label length the shapes above leave room for (at spread 1). */
const LABEL_MAX = 14;
/** Longest label when there's room to spread out for it; longer names are still cut. */
const LABEL_WIDE = 28;
/** The spread steps down by this much while the graph is wider than the panel. */
const SPREAD_STEP = 0.05;

/** Undirected key for a camera pair. */
export function edgeKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

const ROUTE_RE = /^\s*route\s*(\d+)\s*[:\-–—]\s*(.+)$/i;

/** "Route 2: plaza steps" -> { route: 2, rest: "plaza steps" }; null if no prefix. */
export function parseRouteName(name: string): { route: number; rest: string } | null {
  const m = ROUTE_RE.exec(name);
  return m ? { route: Number(m[1]), rest: m[2].trim() } : null;
}

/** Short label: drop the "(...)" detail, cap the length. */
export function shortLabel(text: string, max = LABEL_MAX): string {
  const main = text.replace(/\s*\(.*$/, '').trim() || text.trim();
  return main.length > max ? `${main.slice(0, max - 1).trimEnd()}…` : main;
}

const ID_ORDER = new Intl.Collator('en', { numeric: true }).compare;

interface Placed { id: string; x: number; y: number; slot: Slot }
interface LocalGroup { title: string; route: number | null; placed: Placed[] }
/** All groups side by side (before centering), and the x range of what's drawn. */
interface Row { nodes: (Placed & { group: number })[]; groups: GraphGroup[]; lo: number; hi: number }

export function buildLayout(cameras: readonly Camera[]): GraphLayout {
  // 1. Cameras (first of a duplicated camera_id wins) and the undirected neighbor graph.
  const cams: Camera[] = [];
  const index = new Map<string, number>();
  for (const cam of cameras) {
    if (!cam || typeof cam.camera_id !== 'string' || index.has(cam.camera_id)) continue;
    index.set(cam.camera_id, cams.length);
    cams.push(cam);
  }
  const adj = neighborGraph(cams, index);

  // 2. Routes = connected components, ordered by their lowest camera_id. Lone cameras go to "Other".
  const routes: string[][] = [];
  const singles: string[] = [];
  const seen = new Set<string>();
  for (const cam of cams) {
    const id = cam.camera_id;
    if (seen.has(id)) continue;
    const comp = dfs(id, adj, seen);
    if (comp.length === 1) singles.push(id);
    else routes.push(comp);
  }
  routes.sort((a, b) => ID_ORDER(lowest(a), lowest(b)));
  const titles = routeTitles(routes, cams, index);

  // 3. Place each group in local coordinates (first node at x = 0), then side by side.
  const local: LocalGroup[] = routes.map((comp, i) => ({
    title: `Route ${titles[i]}`, route: titles[i], placed: placeRoute(comp, adj, index),
  }));
  for (let i = 0; i < singles.length; i += OTHER_PER_GROUP) {
    const placed = zigzag(singles.slice(i, i + OTHER_PER_GROUP), 'single');
    local.push({ title: 'Other cameras', route: null, placed });
  }
  const nameOf = (id: string) => {
    const cam = cams[index.get(id)!];
    return typeof cam.name === 'string' && cam.name.trim() ? cam.name.trim() : cam.camera_id;
  };
  const texts = new Map<string, string>();
  for (const { route, placed } of local) for (const p of placed) texts.set(p.id, labelText(nameOf(p.id), route));

  // Spread for the longest label (see the top of the file); it steps back toward 1 until the graph
  // fits the panel's width, and the labels get as many characters as the spread makes room for.
  const longest = Math.max(LABEL_MAX, ...[...texts.values()].map((t) => Math.min(t.length, LABEL_WIDE)));
  let spread = longest / LABEL_MAX;
  let row = arrange(local, spread);
  while (spread > 1 && row.hi - row.lo + 2 * MARGIN > W_MIN) {
    spread = Math.max(1, spread - SPREAD_STEP);
    row = arrange(local, spread);
  }
  const labelChars = Math.floor(LABEL_MAX * spread + 1e-6);
  const nodes: GraphNode[] = row.nodes.map(({ id, x, y, slot, group }) => ({
    camera_id: id, name: nameOf(id), label: shortLabel(texts.get(id)!, labelChars) || id, x, y, slot, group,
  }));
  const { groups, lo, hi } = row;

  // Fit the viewBox to what's drawn (outermost labels and titles included) and center it.
  const width = Math.max(W_MIN, hi - lo + 2 * MARGIN);
  const shift = Math.round((width - (hi - lo)) / 2 - lo);
  for (const n of nodes) n.x += shift;
  for (const g of groups) g.x += shift;

  const byId: Record<string, GraphNode> = {};
  for (const n of nodes) byId[n.camera_id] = n;

  // 4. Idle camera-camera edges: every neighbor pair in cameras.json (both ends are always drawn).
  const edgeSet = new Set<string>();
  for (const [a, list] of adj) for (const b of list) edgeSet.add(edgeKey(a, b));

  // 5. Spokes: drop to BEND_Y, then a smooth fan into ports spread along the coordinator's top edge,
  //    in left-to-right node order so the fan never crosses itself.
  const coordinator = { x: width / 2, y: COORD.y, w: COORD.w, h: COORD.h };
  const portY = coordinator.y - coordinator.h / 2;
  const span = coordinator.w - 2 * PORT_INSET;
  const ordered = [...nodes].sort((a, b) => a.x - b.x || a.y - b.y);
  const spokes: Record<string, string> = {};
  const marks: Record<string, { x: number; y: number }> = {};
  ordered.forEach((n, i) => {
    const px = ordered.length > 1 ? coordinator.x - span / 2 + (i * span) / (ordered.length - 1) : coordinator.x;
    const bend = Math.max(BEND_Y, n.y + NODE_R + 4);
    const pull = (portY - bend) * 0.6;
    marks[n.camera_id] = { x: n.x, y: r1((n.y + NODE_R + bend) / 2 + 2) };
    spokes[n.camera_id] = `M ${r1(n.x)} ${r1(n.y)} V ${r1(bend)} `
      + `C ${r1(n.x)} ${r1(bend + pull)} ${r1(px)} ${r1(portY - pull)} ${r1(px)} ${r1(portY)}`;
  });

  return { width, height: H, nodes, byId, groups, edges: [...edgeSet].sort(), coordinator, spokes, marks };
}

/** Straight path from camera a to camera b (direction matters for the draw-on flash). */
export function edgePath(layout: GraphLayout, from: string, to: string): string | null {
  const a = layout.byId[from];
  const b = layout.byId[to];
  return a && b ? `M ${r1(a.x)} ${r1(a.y)} L ${r1(b.x)} ${r1(b.y)}` : null;
}

// ---------- graph helpers ----------

/**
 * camera_id -> its neighbors, both ways (a link listed on one side only still counts). Each camera's own
 * list comes first, in its order; then cameras that list it, in cameras.json order. Unknown ids and
 * self-links are ignored.
 */
function neighborGraph(cams: readonly Camera[], index: ReadonlyMap<string, number>): Map<string, string[]> {
  const adj = new Map<string, string[]>(cams.map((c) => [c.camera_id, []]));
  const link = (a: string, b: string) => {
    const list = adj.get(a)!;
    if (!list.includes(b)) list.push(b);
  };
  for (const cam of cams) {
    if (!Array.isArray(cam.neighbors)) continue;
    for (const nb of cam.neighbors) {
      const id = nb && typeof nb === 'object' ? nb.camera_id : undefined;
      if (typeof id === 'string' && index.has(id) && id !== cam.camera_id) link(cam.camera_id, id);
    }
  }
  for (const cam of cams) {
    for (const nb of [...adj.get(cam.camera_id)!]) link(nb, cam.camera_id);
  }
  return adj;
}

/** Depth-first walk from `start` in neighbor order, skipping (and filling) `seen`. Returns visit order. */
function dfs(start: string, adj: ReadonlyMap<string, readonly string[]>, seen: Set<string>): string[] {
  const out: string[] = [];
  const stack = [start];
  while (stack.length) {
    const id = stack.pop()!;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(id);
    const next = adj.get(id) ?? [];
    for (let i = next.length - 1; i >= 0; i--) if (!seen.has(next[i])) stack.push(next[i]);
  }
  return out;
}

function lowest(ids: readonly string[]): string {
  return ids.reduce((lo, id) => (ID_ORDER(id, lo) < 0 ? id : lo));
}

/**
 * Route number per component: the "Route N:" prefix of its first camera (cameras.json order) that has one;
 * components without a prefix take the lowest numbers nobody claimed, in order.
 */
function routeTitles(routes: readonly string[][], cams: readonly Camera[], index: ReadonlyMap<string, number>): number[] {
  const fromName = routes.map((comp) => {
    const ordered = [...comp].sort((a, b) => index.get(a)! - index.get(b)!);
    for (const id of ordered) {
      const name = cams[index.get(id)!].name;
      const parsed = typeof name === 'string' ? parseRouteName(name) : null;
      if (parsed) return parsed.route;
    }
    return null;
  });
  const used = new Set(fromName.filter((n): n is number => n !== null));
  let next = 1;
  return fromName.map((n) => {
    if (n !== null) return n;
    while (used.has(next)) next++;
    used.add(next);
    return next;
  });
}

/** One route's cameras in local coordinates: a junction fork if it has a junction, else a chain. */
function placeRoute(comp: readonly string[], adj: ReadonlyMap<string, readonly string[]>, index: ReadonlyMap<string, number>): Placed[] {
  const byOrder = (a: string, b: string) => index.get(a)! - index.get(b)!;
  const degree = (id: string) => adj.get(id)!.length;

  let junction: string | null = null;
  for (const id of [...comp].sort(byOrder)) {
    if (degree(id) >= 3 && (junction === null || degree(id) > degree(junction))) junction = id;
  }
  if (junction === null) {
    // Chain: start at an end (a camera with one neighbor; first in cameras.json order), or anywhere on a loop.
    const ends = comp.filter((id) => degree(id) <= 1).sort(byOrder);
    const start = ends[0] ?? [...comp].sort(byOrder)[0];
    return zigzag(dfs(start, adj, new Set()), 'chain');
  }

  // Each of the junction's neighbors (cameras.json order) starts a branch: everything reachable from it
  // without passing the junction or an earlier branch. The first branch goes left, the others fork right.
  const seen = new Set<string>([junction]);
  const branches: string[][] = [];
  for (const head of [...adj.get(junction)!].sort(byOrder)) {
    if (!seen.has(head)) branches.push(dfs(head, adj, seen));
  }
  const [leftBranch = [], ...forks] = branches;

  // Cameras further along a branch than its head (only in unusual graphs) each get their own column, and
  // every second one steps DEEP_ZIG toward the middle, so a line that skips a camera doesn't run through it.
  const deepY = (row: number, i: number) => (i > 0 && i % 2 === 0 ? row + (row >= JUNCTION_Y ? -DEEP_ZIG : DEEP_ZIG) : row);

  const placed: Placed[] = [];
  // Left branch: its head right next to the junction, anything further along continues to the left.
  leftBranch.forEach((id, i) => placed.push({ id, x: -i * DEEP_STEP, y: deepY(LEFT_Y, i), slot: 'left' }));
  const jx = LEFT_TO_JUNCTION;
  placed.push({ id: junction, x: jx, y: JUNCTION_Y, slot: 'junction' });

  // (One fork only happens when a loop pulled the junction's other neighbors into an earlier branch.)
  const ys = forks.length <= 2 ? FORK_Y_PAIR
    : forks.map((_, k) => FORK_Y_TOP + (k * (FORK_Y_BOTTOM - FORK_Y_TOP)) / (forks.length - 1));
  const headX = (k: number) => jx + FORK_DX + k * FORK_STEP;
  const lastHead = headX(forks.length - 1);
  let column = 0;
  forks.forEach((branch, k) => {
    // The branch's head on its own staggered row; anything further along goes on that row to the right
    // of every head, so it never lands under another head's label.
    branch.forEach((id, i) => placed.push(i === 0
      ? { id, x: headX(k), y: ys[k], slot: 'fork' }
      : { id, x: lastHead + ++column * DEEP_STEP, y: deepY(ys[k], i), slot: 'fork' }));
  });
  const minX = Math.min(...placed.map((p) => p.x));
  return placed.map((p) => ({ ...p, x: p.x - minX }));
}

/** Cameras in a row, alternating between two heights. */
function zigzag(ids: readonly string[], slot: Slot): Placed[] {
  return ids.map((id, i) => ({ id, x: i * ZIG_STEP, y: ZIG_Y[i % 2], slot }));
}

/**
 * Groups side by side, every horizontal distance (inside a group, its padding and the labels' room)
 * times `spread`. Titles keep their size: GROUP_MIN and TITLE_* don't grow. Spread 1 = the shapes as drawn above.
 */
function arrange(local: readonly LocalGroup[], spread: number): Row {
  const nodes: Row['nodes'] = [];
  const groups: GraphGroup[] = [];
  let groupLeft = 0;
  local.forEach(({ title, placed }, g) => {
    const xs = placed.map((p) => p.x);
    const x0 = groupLeft + spread * GROUP_PAD;
    groups.push({ title, x: Math.round(x0 + TITLE_DX) });
    for (const p of placed) nodes.push({ ...p, x: Math.round(x0 + spread * p.x), group: g });
    groupLeft += Math.max(GROUP_MIN, spread * (Math.max(...xs) - Math.min(...xs) + GROUP_PAD + GROUP_RIGHT));
  });
  if (!nodes.length) return { nodes, groups, lo: 0, hi: 0 };
  const half = spread * LABEL_HALF;
  return {
    nodes,
    groups,
    lo: Math.min(...nodes.map((n) => n.x - half), ...groups.map((g) => g.x)),
    hi: Math.max(...nodes.map((n) => n.x + half), ...groups.map((g) => g.x + TITLE_W)),
  };
}

/** A label before any cut: no "Route N:" prefix when the group's title already says it, no "(...)" detail. */
function labelText(name: string, route: number | null): string {
  const parsed = parseRouteName(name);
  const text = parsed && parsed.route === route ? parsed.rest : name;
  return text.replace(/\s*\(.*$/, '').trim() || text.trim();
}

function r1(v: number): number {
  return Math.round(v * 10) / 10;
}
