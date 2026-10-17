// The one store instance: holds StoreState, notifies subscribers, batches live events.
// No React here (hooks.ts wraps it), so Node scripts can use it too.

import type { BusSnapshot, ClarityEvent } from './types.ts';
import { TIMING } from './constants.ts';
import {
  applyEvents, applySnapshot, colorOf, initialState, pruneRecent, select as selectReducer,
  setCameras, setConnection, subjectOfEvent,
} from './state.ts';
import type { Connection, StoreState } from './state.ts';

let state: StoreState = initialState();
const listeners = new Set<() => void>();
let pending: unknown[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

export function getState(): StoreState {
  return state;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function commit(next: StoreState): void {
  if (next === state) return;
  state = next;
  for (const l of [...listeners]) l();
}

function flush(): void {
  if (flushTimer !== null) { clearTimeout(flushTimer); flushTimer = null; }
  if (!pending.length) return;
  const batch = pending;
  pending = [];
  commit(applyEvents(state, batch, true, Date.now()));
}

// ---------- written by bus.ts ----------

/** First WS message: replace all state. Live events still queued from an old socket are covered by it. */
export function receiveSnapshot(snap: BusSnapshot): void {
  pending = [];
  if (flushTimer !== null) { clearTimeout(flushTimer); flushTimer = null; }
  commit(applySnapshot(state, snap, Date.now()));
}

/** One live event from the socket (applied within TIMING.flushMs, batched with its neighbours). */
export function receiveEvent(raw: unknown): void {
  pending.push(raw);
  if (flushTimer === null) flushTimer = setTimeout(flush, TIMING.flushMs);
}

/** An event the dashboard itself produced (operator_action after a successful POST). */
export function addLocalEvent(event: ClarityEvent): void {
  flush();
  commit(applyEvents(state, [event], true, Date.now()));
}

export function updateConnection(patch: Partial<Connection>): void {
  commit(setConnection(state, patch));
}

export function updateCameras(config: unknown): void {
  commit(setCameras(state, config));
}

export function expireRecent(now: number = Date.now()): void {
  commit(pruneRecent(state, now, TIMING.recentWindowMs));
}

/** Tests only: back to the empty state. */
export function resetStore(): void {
  pending = [];
  if (flushTimer !== null) { clearTimeout(flushTimer); flushTimer = null; }
  commit(initialState());
}

// ---------- public, for components ----------

/** Select an event (receipt, card, arrow, graph edge); null clears. Highlights it + what it cites. */
export function select(eventId: string | null): void {
  commit(selectReducer(state, eventId));
}

/** Chase color (hex) for a subject; the neutral text color if it has none yet. */
export function colorFor(subjectId: string | null | undefined): string {
  return colorOf(state, subjectId);
}

/** CSS variable for a subject's chase color, e.g. "var(--chase-2)"; "var(--text)" if none yet. */
export function chaseVar(subjectId: string | null | undefined): string {
  const n = subjectId ? state.subjectChase[subjectId] : undefined;
  return n ? `var(--chase-${n})` : 'var(--text)';
}

/** subject_id for an event or event_id (detections get one once a relay/match verdict cites them). */
export function subjectOf(eventOrId: ClarityEvent | string): string | null {
  const e = typeof eventOrId === 'string' ? state.eventsById.get(eventOrId) : eventOrId;
  return e ? subjectOfEvent(e, state.detectionSubjects) : null;
}

/** Look up any event by id (undefined if not seen). */
export function getEvent(eventId: string): ClarityEvent | undefined {
  return state.eventsById.get(eventId);
}
