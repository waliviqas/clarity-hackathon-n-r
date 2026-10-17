// Event history -> what the chases look like on the map. Pure (no React, no Leaflet, no DOM), so plain
// Node can run it (scripts/check-chase.ts).
//
// Per incident (latest dispatch):
//   path         solid segments between consecutive `path` cameras, in the subject's chase color
//   extension    a "match" verdict newer than that dispatch extends the path right away (from the relay
//                it answers), until the coordinator's next dispatch takes the camera into `path`
//   predictions  dashed lines from the last path camera to each `predicted_next` camera, with "70%"
// Per relay:
//   arrow        from_camera -> to_camera while the subject is on its way: until a verdict for that
//                subject at to_camera (or one citing the relay), or ts + expected_arrival_s + grace on the
//                run clock. A match ends it at once (the path takes over); no_match / uncertain fade it.
//                It travels (animated dash) only if it arrived live; snapshot history is drawn static.
//   receipt      an ended relay that the operator selected (or that a selection cites) is drawn again,
//                static, so the receipts trail is visible on the map.
// Per camera:
//   fill         chase color of the newest subject confirmed there (path step or match verdict)
//   badge        "no match" / "uncertain" for TIMING.verdictBadgeMs after a live verdict
//   highlighted  a selected / cited detection or verdict happened here

import type { AgentVerdict, ClarityEvent, Dispatch, Relay } from '../lib/types.ts';
import type { IncidentView } from '../lib/state.ts';
import { TIMING } from '../lib/constants.ts';

export interface ChaseSegment {
  key: string;
  from: string;
  to: string;
  subjectId: string;
  color: string;
  /** Null for an extension of a subject that has no dispatch yet. */
  incidentId: string | null;
  /** What a click selects: the path step's event (the verdict that confirmed `to`), else the dispatch. */
  eventId: string;
  kind: 'path' | 'extension';
  highlighted: boolean;
}

export interface ChasePrediction {
  key: string;
  from: string;
  to: string;
  /** 0..1 */
  probability: number;
  subjectId: string;
  color: string;
  incidentId: string;
  /** The dispatch that predicted it (what a click selects). */
  eventId: string;
  highlighted: boolean;
  /** A live relay arrow of the same subject runs the same from -> to (it's drawn beside this line). */
  covered: boolean;
}

export type ArrowState = 'active' | 'fading' | 'receipt';

export interface ChaseArrow {
  /** Changes when the state changes, so the drawn layer (and its CSS animation) is rebuilt. */
  key: string;
  relayId: string;
  from: string;
  to: string;
  subjectId: string;
  color: string;
  state: ArrowState;
  /** Travelling dash: only for active relays that arrived live (never snapshot history). */
  animate: boolean;
  highlighted: boolean;
  /**
   * Draw it shifted to the right of travel: another arrow goes the opposite way on the same pair, or a
   * predicted (dashed) line runs on it, so both stay visible side by side.
   */
  offset: boolean;
}

export interface CameraBadge {
  kind: 'no_match' | 'uncertain';
  verdictId: string;
}

export interface CameraChase {
  /** Chase color (hex) of the newest subject confirmed at this camera, or null. */
  fill: string | null;
  highlighted: boolean;
  badge: CameraBadge | null;
}

export interface ChaseView {
  segments: ChaseSegment[];
  predictions: ChasePrediction[];
  arrows: ChaseArrow[];
  cameras: ReadonlyMap<string, CameraChase>;
  /** The selection touches the map: draw everything that isn't highlighted dimmed. */
  dim: boolean;
  /** Date.now() ms when something here changes on its own (an arrow expires or fades, a badge ends); null = never. */
  nextChangeMs: number | null;
}

export interface ChaseInput {
  /** Every event, arrival order (store `events`). */
  events: readonly ClarityEvent[];
  /** events[i] with i >= liveFrom arrived live (store `liveFrom`). */
  liveFrom: number;
  /** Latest dispatch per incident (store `incidents`). */
  incidents: readonly IncidentView[];
  subjectColors: Readonly<Record<string, string>>;
  /** event_id -> Date.now() ms of live arrival, last few seconds (store `recent`). */
  recent: ReadonlyMap<string, number>;
  /** Selection + what it cites (store `highlighted`). */
  highlighted: ReadonlySet<string>;
  /** Cameras that can be drawn (have a map position). */
  known: (cameraId: string) => boolean;
  /** Date.now() ms. */
  nowMs: number;
  /** Run-clock seconds now (store runClock), or null before any event. */
  runNow: number | null;
  /** Fallback color for a subject without one. */
  fallbackColor: string;
}

const isStr = (x: unknown): x is string => typeof x === 'string' && x !== '';
const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);

function evidence(e: { evidence_event_ids?: unknown }): string[] {
  return Array.isArray(e.evidence_event_ids) ? e.evidence_event_ids.filter(isStr) : [];
}

/** Valid path steps of a dispatch whose camera can be drawn, with consecutive repeats collapsed. */
function drawableSteps(d: Dispatch, known: (id: string) => boolean): { camera_id: string; ts: number; event_id?: string }[] {
  const out: { camera_id: string; ts: number; event_id?: string }[] = [];
  if (!Array.isArray(d.path)) return out;
  for (const step of d.path) {
    if (!step || !isStr(step.camera_id) || !known(step.camera_id)) continue;
    const ts = isNum(step.ts) ? step.ts : d.ts;
    const ev = isStr(step.event_id) ? step.event_id : undefined;
    const last = out[out.length - 1];
    if (last && last.camera_id === step.camera_id) { out[out.length - 1] = { camera_id: step.camera_id, ts, event_id: ev ?? last.event_id }; continue; }
    out.push({ camera_id: step.camera_id, ts, event_id: ev });
  }
  return out;
}

export function deriveChase(input: ChaseInput): ChaseView {
  const { events, liveFrom, incidents, subjectColors, recent, highlighted, known, nowMs, runNow } = input;
  const colorOf = (subj: string) => subjectColors[subj] ?? input.fallbackColor;
  let nextChangeMs: number | null = null;
  const wake = (ms: number) => { if (ms > nowMs && (nextChangeMs === null || ms < nextChangeMs)) nextChangeMs = ms; };

  // ---- index ----
  const relays: { r: Relay; live: boolean }[] = [];
  const relayById = new Map<string, Relay>();
  const verdicts: AgentVerdict[] = [];
  const byId = new Map<string, ClarityEvent>();
  events.forEach((e, i) => {
    byId.set(e.event_id, e);
    if (e.type === 'relay') {
      if (!isStr(e.from_camera) || !isStr(e.to_camera) || !isStr(e.subject_id) || e.from_camera === e.to_camera) return;
      relays.push({ r: e, live: i >= liveFrom });
      relayById.set(e.event_id, e);
    } else if (e.type === 'agent_verdict') {
      if (!isStr(e.camera_id) || !isStr(e.subject_id)) return;
      verdicts.push(e);
    }
  });
  // Verdicts that cite a relay, and verdicts per subject@camera (both in arrival order).
  const citing = new Map<string, AgentVerdict[]>();
  const atCamera = new Map<string, AgentVerdict[]>();
  for (const v of verdicts) {
    for (const id of evidence(v)) {
      if (!relayById.has(id)) continue;
      const list = citing.get(id);
      if (list) list.push(v); else citing.set(id, [v]);
    }
    const k = `${v.subject_id}@${v.camera_id}`;
    const list = atCamera.get(k);
    if (list) list.push(v); else atCamera.set(k, [v]);
  }

  // ---- relay arrows ----
  type Pending = Omit<ChaseArrow, 'key' | 'offset'>;
  const pending: Pending[] = [];
  for (const { r, live } of relays) {
    if (!known(r.from_camera) || !known(r.to_camera)) continue;
    const hl = highlighted.has(r.event_id);
    const end = answerOf(r, citing, atCamera);
    let state: ArrowState | null = null;
    if (end === null) {
      const arrival = isNum(r.expected_arrival_s) && r.expected_arrival_s >= 0 ? r.expected_arrival_s : TIMING.relayDefaultArrivalS;
      const expiresAt = r.ts + arrival + TIMING.relayGraceS;
      if (runNow !== null && runNow >= expiresAt) state = null;
      else {
        state = 'active';
        if (runNow !== null) wake(nowMs + (expiresAt - runNow) * 1000);
      }
    } else if (end.decision !== 'match') {
      const arrived = recent.get(end.event_id);
      if (arrived !== undefined && nowMs - arrived < TIMING.relayFadeMs) {
        state = 'fading';
        wake(arrived + TIMING.relayFadeMs);
      }
    }
    if (state === null && hl) state = 'receipt';
    if (state === null) continue;
    pending.push({
      relayId: r.event_id, from: r.from_camera, to: r.to_camera, subjectId: r.subject_id,
      color: colorOf(r.subject_id), state, animate: state === 'active' && live, highlighted: hl,
    });
  }
  // Same subject, same pair: draw only the newest arrow (a re-sent relay replaces the old one).
  const newest = new Map<string, Pending>();
  for (const a of pending) newest.set(`${a.subjectId}|${a.from}|${a.to}`, a);
  const drawn = [...newest.values()];
  const arrowPairs = new Set(drawn.filter((a) => a.state !== 'receipt').map((a) => `${a.subjectId}|${a.from}|${a.to}`));

  // ---- paths, extensions, predictions ----
  const segments: ChaseSegment[] = [];
  const predictions: ChasePrediction[] = [];
  const fills = new Map<string, { ts: number; subject: string }>();
  const fill = (cam: string, ts: number, subject: string) => {
    const prev = fills.get(cam);
    if (!prev || ts >= prev.ts) fills.set(cam, { ts, subject });
  };
  const withDispatch = new Set<string>();

  for (const inc of incidents) {
    const d = inc.dispatch;
    if (!isStr(d.subject_id)) continue;
    withDispatch.add(d.subject_id);
    const color = colorOf(d.subject_id);
    const steps = drawableSteps(d, known);
    const dispatchHl = highlighted.has(d.event_id);
    const inPath = new Set(steps.map((s) => s.camera_id));
    const segPairs = new Set<string>();
    for (const s of steps) fill(s.camera_id, s.ts, d.subject_id);
    for (let i = 1; i < steps.length; i++) {
      const a = steps[i - 1], b = steps[i];
      const eventId = b.event_id ?? d.event_id;
      segPairs.add(`${a.camera_id}|${b.camera_id}`);
      segments.push({
        key: `${inc.incident_id}:${i}:${a.camera_id}>${b.camera_id}`, from: a.camera_id, to: b.camera_id,
        subjectId: d.subject_id, color, incidentId: inc.incident_id, eventId, kind: 'path',
        highlighted: dispatchHl || highlighted.has(eventId),
      });
    }
    const last = steps.length ? steps[steps.length - 1].camera_id : null;

    // Match verdicts the coordinator hasn't answered yet extend the path now.
    for (const v of verdicts) {
      if (v.subject_id !== d.subject_id || v.decision !== 'match' || !(v.ts > d.ts)) continue;
      if (!known(v.camera_id) || inPath.has(v.camera_id)) continue;
      const from = relayFrom(v, relayById, known) ?? last;
      if (!from || from === v.camera_id || segPairs.has(`${from}|${v.camera_id}`)) continue;
      segPairs.add(`${from}|${v.camera_id}`);
      segments.push({
        key: `${inc.incident_id}:ext:${v.event_id}`, from, to: v.camera_id, subjectId: d.subject_id, color,
        incidentId: inc.incident_id, eventId: v.event_id, kind: 'extension', highlighted: highlighted.has(v.event_id),
      });
    }

    if (last && Array.isArray(d.predicted_next)) {
      const seen = new Set<string>();
      for (const p of d.predicted_next) {
        if (!p || !isStr(p.camera_id) || p.camera_id === last || !known(p.camera_id) || seen.has(p.camera_id)) continue;
        seen.add(p.camera_id);
        const probability = isNum(p.probability) ? Math.min(1, Math.max(0, p.probability)) : 0;
        predictions.push({
          key: `${inc.incident_id}:pred:${last}>${p.camera_id}`, from: last, to: p.camera_id, probability,
          subjectId: d.subject_id, color, incidentId: inc.incident_id, eventId: d.event_id, highlighted: dispatchHl,
          covered: arrowPairs.has(`${d.subject_id}|${last}|${p.camera_id}`),
        });
      }
    }
  }
  // Subjects with match verdicts but no dispatch yet: extensions from the relays they answer.
  for (const v of verdicts) {
    if (v.decision !== 'match' || withDispatch.has(v.subject_id) || !known(v.camera_id)) continue;
    const from = relayFrom(v, relayById, known);
    if (!from || from === v.camera_id) continue;
    const key = `${v.subject_id}:ext:${from}>${v.camera_id}`;
    const at = segments.findIndex((s) => s.key === key);
    const seg: ChaseSegment = {
      key, from, to: v.camera_id, subjectId: v.subject_id, color: colorOf(v.subject_id), incidentId: null,
      eventId: v.event_id, kind: 'extension', highlighted: highlighted.has(v.event_id),
    };
    if (at >= 0) segments[at] = seg; else segments.push(seg);
  }
  for (const v of verdicts) if (v.decision === 'match' && known(v.camera_id)) fill(v.camera_id, v.ts, v.subject_id);

  // Arrow offsets: apart from an opposite arrow, and beside a predicted line on the same pair.
  const pairs = new Set(drawn.map((a) => `${a.from}|${a.to}`));
  const predicted = new Set(predictions.map((p) => `${p.from}|${p.to}`));
  const arrows: ChaseArrow[] = drawn.map((a) => ({
    ...a,
    key: `${a.relayId}:${a.state}${a.animate ? ':live' : ''}`,
    offset: pairs.has(`${a.to}|${a.from}`) || predicted.has(`${a.from}|${a.to}`),
  }));

  // ---- cameras: fill, badge, highlight ----
  const cameras = new Map<string, CameraChase>();
  const cam = (id: string): CameraChase => {
    let c = cameras.get(id);
    if (!c) { c = { fill: null, highlighted: false, badge: null }; cameras.set(id, c); }
    return c;
  };
  for (const [id, f] of fills) cam(id).fill = colorOf(f.subject);
  // Badges: the newest live verdict per camera decides (a later match clears an earlier "no match").
  const newestVerdict = new Map<string, { v: AgentVerdict; at: number }>();
  for (const [id, at] of recent) {
    const e = byId.get(id);
    if (!e || e.type !== 'agent_verdict' || !isStr(e.camera_id)) continue;
    if (nowMs - at >= TIMING.verdictBadgeMs) continue;
    newestVerdict.set(e.camera_id, { v: e, at });
  }
  for (const [camId, { v, at }] of newestVerdict) {
    if (v.decision !== 'no_match' && v.decision !== 'uncertain') continue;
    cam(camId).badge = { kind: v.decision, verdictId: v.event_id };
    wake(at + TIMING.verdictBadgeMs);
  }
  for (const id of highlighted) {
    const e = byId.get(id);
    if (e && (e.type === 'detection' || e.type === 'agent_verdict') && isStr(e.camera_id)) cam(e.camera_id).highlighted = true;
  }

  const dim = highlighted.size > 0 && (
    segments.some((s) => s.highlighted) || arrows.some((a) => a.highlighted)
    || predictions.some((p) => p.highlighted) || [...cameras.values()].some((c) => c.highlighted));

  return { segments, predictions, arrows, cameras, dim, nextChangeMs };
}

/**
 * The verdict that answers a relay: the earliest (by ts) that cites it, or that is for the same subject
 * at to_camera and not older than the relay. Null while nobody has answered.
 */
function answerOf(
  r: Relay, citing: ReadonlyMap<string, AgentVerdict[]>, atCamera: ReadonlyMap<string, AgentVerdict[]>,
): AgentVerdict | null {
  let end: AgentVerdict | null = null;
  for (const v of citing.get(r.event_id) ?? []) if (!end || v.ts < end.ts) end = v;
  for (const v of atCamera.get(`${r.subject_id}@${r.to_camera}`) ?? []) {
    if (v.ts >= r.ts && (!end || v.ts < end.ts)) end = v;
  }
  return end;
}

/** from_camera of the relay a verdict answers (cited relay whose to_camera is the verdict's camera). */
function relayFrom(v: AgentVerdict, relayById: ReadonlyMap<string, Relay>, known: (id: string) => boolean): string | null {
  for (const id of evidence(v)) {
    const r = relayById.get(id);
    if (r && r.to_camera === v.camera_id && known(r.from_camera)) return r.from_camera;
  }
  return null;
}
