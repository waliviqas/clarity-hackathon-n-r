// Event history -> what each graph element shows (pure, no React).
// "Latest" = highest ts, ties go to the later arrival (same rule the store uses for dispatches).

import type { AgentVerdict, ClarityEvent, Detection, Dispatch, Relay } from '../lib';
import { edgeKey } from './layout.ts';
import type { GraphLayout } from './layout.ts';

export interface GraphState {
  /** Undirected camera pair -> latest relay on it (either direction). */
  relayByEdge: ReadonlyMap<string, Relay>;
  /** Undirected camera pair -> every relay id on it (for selection highlight). */
  relayIdsByEdge: ReadonlyMap<string, readonly string[]>;
  /** Relay pairs that aren't neighbors in cameras.json but have both ends drawn (drawn as extra edges). */
  extraEdges: readonly string[];
  verdictByCam: ReadonlyMap<string, AgentVerdict>;
  verdictIdsByCam: ReadonlyMap<string, readonly string[]>;
  /** Latest detection with a crime activity at each camera (persistent alert ring). */
  crimeByCam: ReadonlyMap<string, Detection>;
  /** Cameras with at least one detection. */
  seenCams: ReadonlySet<string>;
  /** Detection + verdict ids per camera (node highlight). */
  nodeIdsByCam: ReadonlyMap<string, readonly string[]>;
  /** Latest detection or verdict per camera (what a node click selects). */
  nodeEventByCam: ReadonlyMap<string, Detection | AgentVerdict>;
  /** Latest subject seen at each camera, with the ts it was seen (node ring color, route chip). */
  subjectByCam: ReadonlyMap<string, { subject: string; ts: number }>;
  dispatch: Dispatch | null;
  dispatchIds: readonly string[];
}

function newer<T extends { ts: number }>(prev: T | undefined, e: T): boolean {
  return !prev || e.ts >= prev.ts;
}

function push(map: Map<string, string[]>, key: string, id: string): void {
  const list = map.get(key);
  if (list) list.push(id);
  else map.set(key, [id]);
}

export function deriveGraphState(
  events: readonly ClarityEvent[],
  layout: GraphLayout,
  detectionSubjects: Readonly<Record<string, string>>,
): GraphState {
  const relayByEdge = new Map<string, Relay>();
  const relayIdsByEdge = new Map<string, string[]>();
  const verdictByCam = new Map<string, AgentVerdict>();
  const verdictIdsByCam = new Map<string, string[]>();
  const crimeByCam = new Map<string, Detection>();
  const seenCams = new Set<string>();
  const nodeIdsByCam = new Map<string, string[]>();
  const nodeEventByCam = new Map<string, Detection | AgentVerdict>();
  const subjectByCam = new Map<string, { subject: string; ts: number }>();
  let dispatch: Dispatch | null = null;
  const dispatchIds: string[] = [];
  const known = new Set(layout.edges);
  const extra = new Set<string>();

  const sawSubject = (cam: string, subject: unknown, ts: number) => {
    if (typeof subject !== 'string' || !layout.byId[cam]) return;
    const prev = subjectByCam.get(cam);
    if (!prev || ts >= prev.ts) subjectByCam.set(cam, { subject, ts });
  };
  const nodeEvent = (cam: string, e: Detection | AgentVerdict) => {
    push(nodeIdsByCam, cam, e.event_id);
    if (newer(nodeEventByCam.get(cam), e)) nodeEventByCam.set(cam, e);
  };

  for (const e of events) {
    switch (e.type) {
      case 'relay': {
        if (typeof e.from_camera !== 'string' || typeof e.to_camera !== 'string') break;
        if (!layout.byId[e.from_camera] || !layout.byId[e.to_camera] || e.from_camera === e.to_camera) break;
        const key = edgeKey(e.from_camera, e.to_camera);
        if (!known.has(key)) extra.add(key);
        push(relayIdsByEdge, key, e.event_id);
        if (newer(relayByEdge.get(key), e)) relayByEdge.set(key, e);
        sawSubject(e.from_camera, e.subject_id, e.ts);
        break;
      }
      case 'agent_verdict': {
        if (typeof e.camera_id !== 'string') break;
        push(verdictIdsByCam, e.camera_id, e.event_id);
        if (newer(verdictByCam.get(e.camera_id), e)) verdictByCam.set(e.camera_id, e);
        nodeEvent(e.camera_id, e);
        if (e.decision === 'match') sawSubject(e.camera_id, e.subject_id, e.ts);
        break;
      }
      case 'detection': {
        if (typeof e.camera_id !== 'string') break;
        seenCams.add(e.camera_id);
        nodeEvent(e.camera_id, e);
        if (e.activity && e.activity !== 'none' && newer(crimeByCam.get(e.camera_id), e)) crimeByCam.set(e.camera_id, e);
        const subj = detectionSubjects[e.event_id];
        if (subj) sawSubject(e.camera_id, subj, e.ts);
        break;
      }
      case 'dispatch':
        dispatchIds.push(e.event_id);
        if (newer(dispatch ?? undefined, e)) dispatch = e;
        break;
      default:
        break;
    }
  }

  return {
    relayByEdge, relayIdsByEdge, extraEdges: [...extra].sort(), verdictByCam, verdictIdsByCam, crimeByCam,
    seenCams, nodeIdsByCam, nodeEventByCam, subjectByCam, dispatch, dispatchIds,
  };
}

/** Subject most recently seen at any of a group's cameras (for the route's incident label). */
export function groupSubject(state: GraphState, layout: GraphLayout, group: number): string | null {
  let best: { subject: string; ts: number } | null = null;
  for (const n of layout.nodes) {
    if (n.group !== group) continue;
    const s = state.subjectByCam.get(n.camera_id);
    if (s && (!best || s.ts >= best.ts)) best = s;
  }
  return best?.subject ?? null;
}
