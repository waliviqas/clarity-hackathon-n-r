import { memo, useEffect, useMemo, useState } from 'react';
import { divIcon } from 'leaflet';
import type { LatLngTuple, Map as LeafletMap, PathOptions } from 'leaflet';
import { CircleMarker, Marker, Pane, Polygon, Polyline, useMap } from 'react-leaflet';
import { select, useSelection } from '../lib';
import { getFeedProgress, subscribeFeedProgress } from '../lib/feedProgress.ts';
import type { ChaseArrow, ChasePrediction, ChaseSegment, ChaseView } from './chase.ts';
import { arrowShape, placeProbLabels } from './chaseGeometry.ts';
import type { Circle } from './chaseGeometry.ts';
import type { Rect, Vec } from './labels.ts';
import { CHASE_STYLE, PROB_LABEL } from './sizes.ts';

/** What the "70%" labels must stay off, in container px (camera labels and markers, map controls). */
export interface ChaseAvoid {
  rects: readonly Rect[];
  circles: readonly Circle[];
}

interface Props {
  chase: ChaseView;
  /** camera_id -> [lat, lon] for cameras with a map position. */
  posById: ReadonlyMap<string, LatLngTuple>;
  avoid: ChaseAvoid;
  /** Bumps after zoom / pan / resize (arrow trims and label spots are in screen px). */
  viewTick: number;
}

// Panes keep the drawing order fixed: predictions under paths under arrows under labels, all under
// the camera markers (Leaflet's marker pane is 600).
const PANES = { predict: 410, path: 420, arrow: 430, labels: 450 } as const;

/**
 * The chases on the map: each incident's path (solid, chase color), predicted next cameras (dashed,
 * with probability), and relay arrows (travelling dash while live). Click any of them to select its event.
 */
export function ChaseLayer({ chase, posById, avoid, viewTick }: Props) {
  const map = useMap();
  const { selection } = useSelection();
  const toggle = (id: string) => select(selection === id ? null : id);
  const zoom = map.getZoom();

  // Arrow shapes are trimmed in screen px, so they're rebuilt per zoom level (pan doesn't change them).
  const arrowGeo = useMemo(
    () => new Map(chase.arrows.map((a) => [a.key, arrowLatLngs(map, zoom, posById, a)])),
    [map, zoom, posById, chase.arrows],
  );

  // Probability labels: on their line, clear of camera labels and markers (container px, so per view).
  const probSpots = useMemo(() => {
    const size = map.getSize();
    const items = chase.predictions.flatMap((p) => {
      const a = posById.get(p.from), b = posById.get(p.to);
      if (!a || !b) return [];
      const pa = map.latLngToContainerPoint(a), pb = map.latLngToContainerPoint(b);
      if (Math.hypot(pb.x - pa.x, pb.y - pa.y) < PROB_LABEL.minLine) return [];
      const text = probText(p.probability);
      const w = Math.ceil(text.length * PROB_LABEL.fontPx * 0.56) + 2 * PROB_LABEL.padX + 2;
      return [{ key: p.key, a: [pa.x, pa.y] as Vec, b: [pb.x, pb.y] as Vec, w, h: PROB_LABEL.height }];
    });
    const view: Rect | null = size.x > 0 ? { x0: 2, y0: 2, x1: size.x - 2, y1: size.y - 2 } : null;
    const spots = placeProbLabels(items, avoid, view);
    const out = new Map<string, LatLngTuple>();
    for (const [key, [x, y]] of spots) {
      const ll = map.containerPointToLatLng([x, y]);
      out.set(key, [ll.lat, ll.lng]);
    }
    return out;
    // viewTick: the container point of every camera changes with pan / zoom / resize.
  }, [map, posById, chase.predictions, avoid, viewTick]);

  const dim = chase.dim;
  return (
    <>
      <Pane name="chase-predict" style={{ zIndex: PANES.predict }}>
        {SHOW_PREDICTIONS && chase.predictions.map((p) => (
          <PredictionLine key={p.key} p={p} posById={posById} dim={dim} onSelect={toggle} />
        ))}
      </Pane>
      <Pane name="chase-path" style={{ zIndex: PANES.path }}>
        {chase.segments.map((s) => (
          <SegmentLine key={s.key} s={s} posById={posById} dim={dim} onSelect={toggle} />
        ))}
      </Pane>
      <Pane name="chase-arrow" style={{ zIndex: PANES.arrow }}>
        {chase.arrows.map((a) => {
          const geo = arrowGeo.get(a.key);
          return geo ? <RelayArrow key={a.key} a={a} geo={geo} dim={dim} onSelect={toggle} /> : null;
        })}
      </Pane>
      {/* Demo: no "predicted next" percent badges (SHOW_PROB_LABELS brings them back). */}
      {SHOW_PROB_LABELS && (
      <Pane name="chase-labels" style={{ zIndex: PANES.labels }}>
        {chase.predictions.map((p) => {
          const at = probSpots.get(p.key);
          return at ? (
            <ProbLabel key={p.key} at={at} text={probText(p.probability)} color={p.color}
              highlighted={p.highlighted} dimmed={dim && !p.highlighted} />
          ) : null;
        })}
      </Pane>
      )}
    </>
  );
}

const SHOW_PROB_LABELS = false;
/** Demo: no dashed "predicted next" lines; the filling relay line shows where the suspect is heading. */
const SHOW_PREDICTIONS = false;

function probText(p: number): string {
  return `${Math.round(p * 100)}%`;
}

interface ArrowGeo {
  line: LatLngTuple[];
  head: LatLngTuple[] | null;
}

function arrowLatLngs(map: LeafletMap, zoom: number, posById: ReadonlyMap<string, LatLngTuple>, a: ChaseArrow): ArrowGeo | null {
  const from = posById.get(a.from), to = posById.get(a.to);
  if (!from || !to) return null;
  const pa = map.project(from, zoom), pb = map.project(to, zoom);
  const shape = arrowShape([pa.x, pa.y], [pb.x, pb.y], a.offset);
  const back = (v: Vec): LatLngTuple => {
    const ll = map.unproject([v[0], v[1]], zoom);
    return [ll.lat, ll.lng];
  };
  return { line: shape.line.map(back), head: shape.head ? shape.head.map(back) : null };
}

// ---------- lines ----------

/** A visible line plus a wide invisible one on top that takes the clicks. */
function ClickableLine({ positions, style, className, eventId, onSelect }: {
  positions: LatLngTuple[];
  style: PathOptions;
  className: string;
  eventId: string;
  onSelect: (id: string) => void;
}) {
  const handlers = useMemo(() => ({ click: () => onSelect(eventId) }), [onSelect, eventId]);
  return (
    <>
      <Polyline positions={positions} pathOptions={style} className={className} interactive={false} />
      <Polyline
        positions={positions}
        pathOptions={HIT_STYLE}
        className="chase-hit"
        bubblingMouseEvents={false}
        eventHandlers={handlers}
      />
    </>
  );
}

const HIT_STYLE: PathOptions = { color: '#000', opacity: 0, weight: CHASE_STYLE.hitWeight, lineCap: 'round' };

function opacityFor(base: number, highlighted: boolean, dim: boolean): number {
  if (highlighted) return Math.min(1, base + 0.3);
  return dim ? Math.min(base, CHASE_STYLE.dimOpacity) : base;
}

const SegmentLine = memo(function SegmentLine({ s, posById, dim, onSelect }: {
  s: ChaseSegment; posById: ReadonlyMap<string, LatLngTuple>; dim: boolean; onSelect: (id: string) => void;
}) {
  const a = posById.get(s.from), b = posById.get(s.to);
  const positions = useMemo(() => (a && b ? [a, b] : null), [a, b]);
  if (!positions) return null;
  const style: PathOptions = {
    color: s.color,
    weight: CHASE_STYLE.pathWeight + (s.highlighted ? CHASE_STYLE.highlightExtra : 0),
    opacity: opacityFor(1, s.highlighted, dim),
    lineCap: 'round',
    lineJoin: 'round',
  };
  return <ClickableLine positions={positions} style={style} className="chase-path" eventId={s.eventId} onSelect={onSelect} />;
});

const PredictionLine = memo(function PredictionLine({ p, posById, dim, onSelect }: {
  p: ChasePrediction; posById: ReadonlyMap<string, LatLngTuple>; dim: boolean; onSelect: (id: string) => void;
}) {
  const a = posById.get(p.from), b = posById.get(p.to);
  const positions = useMemo(() => (a && b ? [a, b] : null), [a, b]);
  if (!positions) return null;
  const style: PathOptions = {
    color: p.color,
    weight: CHASE_STYLE.predictWeight + (p.highlighted ? 0.5 : 0),
    opacity: opacityFor(CHASE_STYLE.predictOpacity, p.highlighted, dim),
    dashArray: CHASE_STYLE.predictDash,
    lineCap: 'butt',
  };
  return <ClickableLine positions={positions} style={style} className="chase-predict" eventId={p.eventId} onSelect={onSelect} />;
});

const RelayArrow = memo(function RelayArrow({ a, geo, dim, onSelect }: {
  a: ChaseArrow; geo: ArrowGeo; dim: boolean; onSelect: (id: string) => void;
}) {
  const opacity = opacityFor(1, a.highlighted, dim);
  const weight = CHASE_STYLE.arrowWeight + (a.highlighted ? CHASE_STYLE.highlightExtra * 0.75 : 0);
  // Class names are fixed when Leaflet creates the path; a.key changes with the state, so a new state
  // means a new layer (and a fresh CSS animation).
  const cls = ['chase-arrow', a.animate ? 'is-live' : '', `is-${a.state}`].filter(Boolean).join(' ');
  const line: PathOptions = { color: a.color, weight, opacity, dashArray: CHASE_STYLE.arrowDash, lineCap: 'butt' };
  const head: PathOptions = { color: a.color, fillColor: a.color, fillOpacity: opacity, opacity, weight: 1, lineJoin: 'miter' };
  const handlers = useMemo(() => ({ click: () => onSelect(a.relayId) }), [onSelect, a.relayId]);
  if (FILL_RELAYS && a.state === 'active') return <FillingRelay a={a} geo={geo} weight={weight} opacity={opacity} />;
  return (
    <>
      <ClickableLine positions={geo.line} style={line} className={cls} eventId={a.relayId} onSelect={onSelect} />
      {geo.head && (
        <Polygon
          positions={geo.head}
          pathOptions={head}
          className={cls.replace('chase-arrow', 'chase-arrow-head')}
          bubblingMouseEvents={false}
          eventHandlers={handlers}
        />
      )}
    </>
  );
});

// ---------- probability labels ----------

const ProbLabel = memo(function ProbLabel({ at, text, color, highlighted, dimmed }: {
  at: LatLngTuple; text: string; color: string; highlighted: boolean; dimmed: boolean;
}) {
  const icon = useMemo(() => divIcon({
    className: 'chase-prob-icon',
    // Values are ours (a palette hex and a whole-number percent), never event text.
    html: `<span class="chase-prob${highlighted ? ' is-highlighted' : ''}${dimmed ? ' is-dimmed' : ''}" style="--c:${color}">${text}</span>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  }), [text, color, highlighted, dimmed]);
  return <Marker position={at} icon={icon} interactive={false} keyboard={false} pane="chase-labels" />;
});

/** Demo: relays fill along the route instead of a travelling dash with an arrowhead. */
const FILL_RELAYS = true;
/** The fill never reaches the next camera on its own: that camera's match completes it. */
const FILL_MAX = 0.92;
/** How fast the tracker creeps after the clip ends: ~63% of the remaining way every this many ms. */
const WAIT_EASE_MS = 3500;

function FillingRelay({ a, geo, weight, opacity }: { a: ChaseArrow; geo: ArrowGeo; weight: number; opacity: number }) {
  // Moves with the clip on screen: while the sending camera's clip plays, the tracker crosses toward the next camera;
  // it waits just short of it until that camera confirms the suspect (the feed switches, the path goes solid).
  const [, bump] = useState(0);
  useEffect(() => subscribeFeedProgress(() => bump((n) => n + 1)), []);
  const p = getFeedProgress(a.subjectId);
  // While the clip plays the tracker covers the first half; after it ends it keeps creeping (easing toward
  // FILL_MAX) while the next camera's models work, so map and video arrive together. The match completes it.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!p || p.endedAt === null) return;
    const timer = setInterval(() => tick((n) => n + 1), 100);
    return () => clearInterval(timer);
  }, [p?.endedAt]);
  let share = 0;
  if (p && p.camera === a.from) {
    share = p.endedAt === null
      ? p.share * 0.5
      : 0.5 + (FILL_MAX - 0.5) * (1 - Math.exp(-(Date.now() - p.endedAt) / WAIT_EASE_MS));
  }
  const from = geo.line[0], to = geo.line[geo.line.length - 1];
  const tip: LatLngTuple = [from[0] + (to[0] - from[0]) * share, from[1] + (to[1] - from[1]) * share];
  return (
    <>
      <Polyline positions={[from, to]} interactive={false}
        pathOptions={{ color: a.color, weight, opacity: opacity * 0.25, lineCap: 'round' }} />
      {share > 0 && (
        <Polyline positions={[from, tip]} interactive={false}
          pathOptions={{ color: a.color, weight: weight + 1, opacity, lineCap: 'round' }} />
      )}
      {/* where the suspect is now */}
      <CircleMarker center={tip} radius={7} interactive={false}
        pathOptions={{ color: '#E6EDF2', weight: 2, fillColor: a.color, fillOpacity: 1 }} />
    </>
  );
}
