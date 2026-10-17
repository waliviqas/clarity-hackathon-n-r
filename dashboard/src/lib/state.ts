// Pure store logic: state shape + reducers. No React, no browser APIs, so plain Node can run it
// (scripts/check-store.ts). Reducers never mutate: each returns a new state, and slices that didn't
// change keep their old reference (so React components that read them don't re-render).

import type {
  BusSnapshot, Camera, CamerasConfig, CameraStatus, ClarityEvent, Dispatch, OperatorAction, OperatorDecision,
} from './types.ts';
import { EVENT_TYPES } from './types.ts';
import { CHASE_COLORS, COLORS, DASHBOARD_SOURCE, SCHEMA_VERSION, SCRIPTED_SOURCE } from './constants.ts';

export type ConnectionState = 'connecting' | 'open' | 'closed';

export interface Connection {
  state: ConnectionState;
  /** Consecutive failed attempts since the last good snapshot (0 when healthy). */
  retries: number;
  /** Date.now() ms of the next reconnect attempt while closed; null otherwise. */
  nextRetryAt: number | null;
  lastError: string | null;
}

export interface CamerasView {
  /** The whole cameras.json (site_id, site_name, map center/zoom), or null before the first load. */
  site: CamerasConfig | null;
  list: readonly Camera[];
  byId: Readonly<Record<string, Camera>>;
}

export interface IncidentView {
  incident_id: string;
  subject_id: string;
  /** Chase color (hex) of the incident's subject. */
  color: string;
  /** 1..5, i.e. CSS var(--chase-N). */
  chase: number;
  /** Latest dispatch for this incident (by ts; ties go to the later arrival). */
  dispatch: Dispatch;
  /** Latest operator_action for this incident, or null if the operator hasn't decided. */
  action: OperatorAction | null;
  /** ts of the first dispatch seen for this incident (cards keep this order). */
  firstTs: number;
  scripted: boolean;
}

export interface StoreState {
  /** The bus's run id (log folder), from bus_snapshot. */
  runId: string | null;
  cameras: CamerasView;
  /** Latest camera_status per camera_id. A camera with no entry has unknown status. */
  cameraStatus: Readonly<Record<string, CameraStatus>>;
  /** Every event, arrival order, de-duplicated by event_id. */
  events: readonly ClarityEvent[];
  eventsById: ReadonlyMap<string, ClarityEvent>;
  /** One per incident_id, in order of first appearance. */
  incidents: readonly IncidentView[];
  dispatches: Readonly<Record<string, Dispatch>>;
  actions: Readonly<Record<string, OperatorAction>>;
  /** subject_id -> chase hex, assigned in order of first appearance. */
  subjectColors: Readonly<Record<string, string>>;
  /** subject_id -> 1..5 (CSS var(--chase-N)). */
  subjectChase: Readonly<Record<string, number>>;
  /** detection event_id -> subject_id, once a relay or a "match" verdict cites the detection. */
  detectionSubjects: Readonly<Record<string, string>>;
  /** Selected event_id (receipt, card, arrow, graph edge), or null. */
  selection: string | null;
  /** The selection plus every id it cites (evidence_event_ids; for a dispatch also its path event_ids). */
  highlighted: ReadonlySet<string>;
  connection: Connection;
  /** Newest event ts seen (run clock), or null before any event. */
  lastTs: number | null;
  /** Date.now() ms when the last live event arrived (to extrapolate the run clock between events). */
  lastEventAt: number | null;
  /** event_id -> Date.now() ms of arrival, for events that arrived live in the last few seconds.
   *  Snapshot events are never "recent": after a (re)connect the screen draws the final state, no animation. */
  recent: ReadonlyMap<string, number>;
  /** How many bus_snapshots were applied. Changes = "state replaced, redraw without animating". */
  snapshots: number;
  /** Messages dropped because they weren't a known event type with event_id + numeric ts. */
  ignored: number;
}

const EMPTY_SET: ReadonlySet<string> = new Set<string>();
const EMPTY_MAP: ReadonlyMap<string, number> = new Map<string, number>();
const KNOWN_TYPES = new Set<string>(EVENT_TYPES);

export const EMPTY_CAMERAS: CamerasView = { site: null, list: [], byId: {} };

export function initialState(): StoreState {
  return {
    runId: null,
    cameras: EMPTY_CAMERAS,
    cameraStatus: {},
    events: [],
    eventsById: new Map(),
    incidents: [],
    dispatches: {},
    actions: {},
    subjectColors: {},
    subjectChase: {},
    detectionSubjects: {},
    selection: null,
    highlighted: EMPTY_SET,
    connection: { state: 'connecting', retries: 0, nextRetryAt: null, lastError: null },
    lastTs: null,
    lastEventAt: null,
    recent: EMPTY_MAP,
    snapshots: 0,
    ignored: 0,
  };
}

// ---------- small helpers (also exported for components) ----------

export function isClarityEvent(x: unknown): x is ClarityEvent {
  if (typeof x !== 'object' || x === null) return false;
  const e = x as Record<string, unknown>;
  return typeof e.type === 'string' && KNOWN_TYPES.has(e.type)
    && typeof e.event_id === 'string' && e.event_id !== ''
    && typeof e.ts === 'number' && Number.isFinite(e.ts);
}

/** The ids an event cites ([] for types without evidence, or a malformed event). */
export function evidenceOf(e: ClarityEvent | undefined | null): readonly string[] {
  if (!e || !('evidence_event_ids' in e) || !Array.isArray(e.evidence_event_ids)) return [];
  return e.evidence_event_ids.filter((id): id is string => typeof id === 'string');
}

/** True for events from bus/fake_scenario (show a "Scripted run" tag). */
export function isScripted(e: { source?: string } | undefined | null): boolean {
  return e?.source === SCRIPTED_SOURCE;
}

/** The camera an event happened at: relay -> from_camera, dispatch -> last path camera. */
export function cameraOf(e: ClarityEvent): string | null {
  switch (e.type) {
    case 'detection':
    case 'agent_verdict':
    case 'camera_status':
      return e.camera_id;
    case 'relay':
      return e.from_camera;
    case 'dispatch':
      return Array.isArray(e.path) && e.path.length ? e.path[e.path.length - 1].camera_id : null;
    case 'operator_action':
      return null;
  }
}

/** subject_id of an event; a detection gets one once a relay or a "match" verdict cites it. */
export function subjectOfEvent(e: ClarityEvent, detectionSubjects: Readonly<Record<string, string>>): string | null {
  switch (e.type) {
    case 'relay':
    case 'agent_verdict':
    case 'dispatch':
      return e.subject_id;
    case 'detection':
      return detectionSubjects[e.event_id] ?? null;
    default:
      return null;
  }
}

export function colorOf(state: StoreState, subjectId: string | null | undefined): string {
  return (subjectId && state.subjectColors[subjectId]) || COLORS.unassigned;
}

export function computeHighlight(id: string | null, byId: ReadonlyMap<string, ClarityEvent>): ReadonlySet<string> {
  if (!id) return EMPTY_SET;
  const set = new Set<string>([id]);
  const e = byId.get(id);
  for (const ref of evidenceOf(e)) set.add(ref);
  if (e?.type === 'dispatch' && Array.isArray(e.path)) {
    for (const step of e.path) if (typeof step?.event_id === 'string') set.add(step.event_id);
  }
  return set;
}

function camerasView(config: CamerasConfig): CamerasView {
  const list = config.cameras.filter((c) => c && typeof c.camera_id === 'string');
  const byId: Record<string, Camera> = {};
  for (const c of list) byId[c.camera_id] = c;
  return { site: config, list, byId };
}

export function isCamerasConfig(x: unknown): x is CamerasConfig {
  return typeof x === 'object' && x !== null && Array.isArray((x as { cameras?: unknown }).cameras);
}

// ---------- reducers ----------

/**
 * Apply a batch of events. `live` = they just arrived over the socket (mark them recent, for
 * animations); false = they're history from a snapshot (no animation). Duplicate event_ids are dropped.
 */
export function applyEvents(state: StoreState, raws: readonly unknown[], live: boolean, now: number): StoreState {
  const events = state.events.slice();
  const byId = new Map(state.eventsById);
  const cameraStatus = { ...state.cameraStatus };
  const dispatches = { ...state.dispatches };
  const actions = { ...state.actions };
  const subjectColors = { ...state.subjectColors };
  const subjectChase = { ...state.subjectChase };
  const detectionSubjects = { ...state.detectionSubjects };
  const recent = new Map(state.recent); // installed only for live batches
  let lastTs = state.lastTs;
  let ignored = state.ignored;
  let added = 0;
  let statusChanged = false;
  let incidentsChanged = false;
  let colorsChanged = false;
  let detectionsChanged = false;

  const assignColor = (subj: unknown) => {
    if (typeof subj !== 'string' || subj in subjectChase) return;
    const n = Object.keys(subjectChase).length % CHASE_COLORS.length;
    subjectChase[subj] = n + 1;
    subjectColors[subj] = CHASE_COLORS[n];
    colorsChanged = true;
  };
  const tagDetections = (ids: readonly string[], subj: string) => {
    for (const id of ids) {
      if (id.startsWith('det_') && !(id in detectionSubjects)) {
        detectionSubjects[id] = subj;
        detectionsChanged = true;
      }
    }
  };

  for (const raw of raws) {
    if (!isClarityEvent(raw)) { ignored++; continue; }
    const e = raw;
    if (byId.has(e.event_id)) continue; // the bus can echo duplicates; consumers de-duplicate
    events.push(e);
    byId.set(e.event_id, e);
    added++;
    if (lastTs === null || e.ts > lastTs) lastTs = e.ts;
    if (live) recent.set(e.event_id, now);

    switch (e.type) {
      case 'camera_status': {
        const prev = cameraStatus[e.camera_id];
        if (!prev || e.ts >= prev.ts) { cameraStatus[e.camera_id] = e; statusChanged = true; }
        break;
      }
      case 'relay':
        assignColor(e.subject_id);
        tagDetections(evidenceOf(e), e.subject_id);
        break;
      case 'agent_verdict':
        assignColor(e.subject_id);
        if (e.decision === 'match') tagDetections(evidenceOf(e), e.subject_id);
        break;
      case 'dispatch': {
        assignColor(e.subject_id);
        const prev = dispatches[e.incident_id];
        if (!prev || e.ts >= prev.ts) { dispatches[e.incident_id] = e; incidentsChanged = true; }
        break;
      }
      case 'operator_action': {
        const prev = actions[e.incident_id];
        if (!prev || e.ts >= prev.ts) { actions[e.incident_id] = e; incidentsChanged = true; }
        break;
      }
      case 'detection':
        break;
    }
  }

  if (added === 0) return ignored === state.ignored ? state : { ...state, ignored };

  const next: StoreState = {
    ...state,
    events,
    eventsById: byId,
    lastTs,
    ignored,
    lastEventAt: live ? now : state.lastEventAt,
    recent: live ? recent : state.recent,
    cameraStatus: statusChanged ? cameraStatus : state.cameraStatus,
    dispatches: incidentsChanged ? dispatches : state.dispatches,
    actions: incidentsChanged ? actions : state.actions,
    subjectColors: colorsChanged ? subjectColors : state.subjectColors,
    subjectChase: colorsChanged ? subjectChase : state.subjectChase,
    detectionSubjects: detectionsChanged ? detectionSubjects : state.detectionSubjects,
  };
  if (incidentsChanged || colorsChanged) next.incidents = buildIncidents(state.incidents, next);
  // The selected event may have arrived only now: recompute what it cites.
  if (state.selection && !state.eventsById.has(state.selection) && byId.has(state.selection)) {
    next.highlighted = computeHighlight(state.selection, byId);
  }
  return next;
}

/** Incident list: keeps the previous order, appends new incidents in arrival order. */
function buildIncidents(prev: readonly IncidentView[], s: StoreState): IncidentView[] {
  const order = prev.map((i) => i.incident_id);
  const firstTs: Record<string, number> = {};
  for (const i of prev) firstTs[i.incident_id] = i.firstTs;
  for (const e of s.events) {
    if (e.type === 'dispatch' && !(e.incident_id in firstTs)) {
      firstTs[e.incident_id] = e.ts;
      order.push(e.incident_id);
    }
  }
  return order.filter((id) => s.dispatches[id]).map((id) => {
    const d = s.dispatches[id];
    const chase = s.subjectChase[d.subject_id] ?? 1;
    const old = prev.find((i) => i.incident_id === id);
    const action = s.actions[id] ?? null;
    if (old && old.dispatch === d && old.action === action && old.chase === chase) return old;
    return {
      incident_id: id,
      subject_id: d.subject_id,
      color: s.subjectColors[d.subject_id] ?? COLORS.unassigned,
      chase,
      dispatch: d,
      action,
      firstTs: firstTs[id],
      scripted: isScripted(d),
    };
  });
}

/** bus_snapshot replaces everything (cameras + events), keeps the connection and the selection. */
export function applySnapshot(state: StoreState, snap: BusSnapshot, now: number): StoreState {
  const base = initialState();
  const fresh: StoreState = {
    ...base,
    runId: typeof snap.run_id === 'string' ? snap.run_id : null,
    // A missing/broken cameras.json on the bus shouldn't blank a map we already have.
    cameras: isCamerasConfig(snap.cameras) ? camerasView(snap.cameras) : state.cameras,
    connection: state.connection,
    selection: state.selection,
    snapshots: state.snapshots + 1,
  };
  const next = applyEvents(fresh, Array.isArray(snap.events) ? snap.events : [], false, now);
  return { ...next, highlighted: computeHighlight(next.selection, next.eventsById) };
}

export function setCameras(state: StoreState, config: unknown): StoreState {
  if (!isCamerasConfig(config) || config === state.cameras.site) return state;
  return { ...state, cameras: camerasView(config) };
}

export function select(state: StoreState, eventId: string | null): StoreState {
  if (eventId === state.selection) return state;
  return { ...state, selection: eventId, highlighted: computeHighlight(eventId, state.eventsById) };
}

export function setConnection(state: StoreState, patch: Partial<Connection>): StoreState {
  const c = state.connection;
  const next = { ...c, ...patch };
  if (next.state === c.state && next.retries === c.retries && next.nextRetryAt === c.nextRetryAt
    && next.lastError === c.lastError) return state;
  return { ...state, connection: next };
}

/** Drop `recent` entries older than windowMs. */
export function pruneRecent(state: StoreState, now: number, windowMs: number): StoreState {
  let expired = false;
  for (const t of state.recent.values()) if (now - t >= windowMs) { expired = true; break; }
  if (!expired) return state;
  const recent = new Map<string, number>();
  for (const [id, t] of state.recent) if (now - t < windowMs) recent.set(id, t);
  return { ...state, recent: recent.size ? recent : EMPTY_MAP };
}

// ---------- operator_action ----------

export function newOperatorActionId(): string {
  const rand = Math.random().toString(36).slice(2, 8).padEnd(6, '0');
  return `op_dash_${Date.now().toString(36)}_${rand}`;
}

/**
 * A schema-valid operator_action: unique op_ id, ts = newest event ts seen (run clock), source
 * "dashboard", run_id copied from the incident's latest dispatch (else the bus run id).
 */
export function buildOperatorAction(
  state: StoreState, incidentId: string, action: OperatorDecision, note?: string | null,
  eventId: string = newOperatorActionId(),
): OperatorAction {
  const event: OperatorAction = {
    type: 'operator_action',
    schema_version: SCHEMA_VERSION,
    event_id: eventId,
    ts: state.lastTs !== null && state.lastTs >= 0 ? state.lastTs : 0,
    source: DASHBOARD_SOURCE,
    incident_id: incidentId,
    action,
  };
  const runId = state.dispatches[incidentId]?.run_id ?? state.runId;
  if (runId) event.run_id = runId;
  if (note !== undefined) event.note = note === null ? null : note.slice(0, 300);
  return event;
}
