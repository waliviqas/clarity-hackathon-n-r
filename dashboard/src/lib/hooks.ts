// React hooks over the store. Each returns a slice that keeps its reference until it changes,
// so components re-render only when their slice does.

import { useMemo, useSyncExternalStore } from 'react';
import type { CameraStatus, ClarityEvent } from './types.ts';
import type { CamerasView, Connection, IncidentView, LiveDetection, StoreState } from './state.ts';
import { liveDetectionsByCamera } from './state.ts';
import { getState, select, subscribe } from './store.ts';

/**
 * Read any slice. The selector must return something already in the state (or a primitive),
 * never a new object/array per call, or React will loop. Derive with useMemo in the component.
 */
export function useStore<T>(selector: (s: StoreState) => T): T {
  return useSyncExternalStore(subscribe, () => selector(getState()));
}

/** cameras.json: { site (whole config or null), list, byId }. */
export function useCameras(): CamerasView {
  return useStore((s) => s.cameras);
}

/** Latest camera_status per camera_id (missing = unknown, treat as online). */
export function useCameraStatus(): Readonly<Record<string, CameraStatus>> {
  return useStore((s) => s.cameraStatus);
}

/** Every event in arrival order (oldest first). */
export function useEvents(): readonly ClarityEvent[] {
  return useStore((s) => s.events);
}

export function useEventsById(): ReadonlyMap<string, ClarityEvent> {
  return useStore((s) => s.eventsById);
}

/** One entry per incident (latest dispatch + operator action + color), first-appearance order. */
export function useIncidents(): readonly IncidentView[] {
  return useStore((s) => s.incidents);
}

/** { state: 'connecting' | 'open' | 'closed', retries, nextRetryAt, lastError } */
export function useConnection(): Connection {
  return useStore((s) => s.connection);
}

/** Current selection, the ids to highlight, and select(eventId | null). */
export function useSelection(): { selection: string | null; highlighted: ReadonlySet<string>; select: typeof select } {
  const selection = useStore((s) => s.selection);
  const highlighted = useStore((s) => s.highlighted);
  return { selection, highlighted, select };
}

/** subject_id -> chase hex. Components that call colorFor() re-render through this. */
export function useSubjectColors(): Readonly<Record<string, string>> {
  return useStore((s) => s.subjectColors);
}

/** detection event_id -> subject_id (white until a relay / match verdict cites the detection). */
export function useDetectionSubjects(): Readonly<Record<string, string>> {
  return useStore((s) => s.detectionSubjects);
}

/** event_id -> Date.now() ms, for events that arrived live in the last TIMING.recentWindowMs. */
export function useRecent(): ReadonlyMap<string, number> {
  return useStore((s) => s.recent);
}

/**
 * camera_id -> { latest, crime } for detections that arrived live in the last TIMING.recentWindowMs.
 * Empty right after a bus_snapshot. Map markers pulse from this; the graph can light camera nodes from it.
 */
export function useLiveDetections(): ReadonlyMap<string, LiveDetection> {
  const recent = useRecent();
  const byId = useEventsById();
  return useMemo(() => liveDetectionsByCamera(recent, byId), [recent, byId]);
}

/** Newest event ts seen (run clock), or null. */
export function useLastTs(): number | null {
  return useStore((s) => s.lastTs);
}

export function useRunId(): string | null {
  return useStore((s) => s.runId);
}

/**
 * Index into useEvents() where live arrivals start: events[i] with i >= this arrived after the latest
 * bus_snapshot (animate those); earlier ones are history (draw the final state, no animation).
 */
export function useLiveFrom(): number {
  return useStore((s) => s.liveFrom);
}

/** Increments on every bus_snapshot (state replaced: draw it without animation). */
export function useSnapshotCount(): number {
  return useStore((s) => s.snapshots);
}
