// Message types, mirrored from contracts/schemas/*.schema.json (v0.1).
// Only fields that exist in the schemas. If the UI needs a field the schema lacks, flag it to the team;
// don't add it here. Optional (`?`) = not in the schema's "required" list.

export type Activity = 'stabbing' | 'fistfight' | 'purse_snatch' | 'none';

export type Direction =
  | 'north' | 'northeast' | 'east' | 'southeast'
  | 'south' | 'southwest' | 'west' | 'northwest' | 'unknown';

/** Fields every runtime event has (contracts/README.md, rule 2). */
export interface BaseEvent {
  type: string;
  schema_version: '0.1';
  event_id: string;
  /** Run-clock seconds (replay: video time; live: unix epoch). */
  ts: number;
  run_id?: string;
  /** Component that emitted it; "fake_scenario" = scripted run. */
  source?: string;
}

/** detection.schema.json (Wali, perception) */
export interface Detection extends BaseEvent {
  type: 'detection';
  camera_id: string;
  track_id: string;
  label?: string;
  confidence: number;
  /** [x, y, w, h] as fractions of the frame. */
  bbox?: number[] | null;
  activity: Activity;
  activity_confidence?: number;
  appearance: string | null;
  direction: Direction | null;
  frame_idx?: number | null;
}

/** relay.schema.json (Wali, agents) */
export interface Relay extends BaseEvent {
  type: 'relay';
  from_camera: string;
  to_camera: string;
  subject_id: string;
  summary: string;
  appearance: string | null;
  direction: Direction | null;
  activity?: Activity;
  confidence: number;
  expected_arrival_s?: number | null;
  evidence_event_ids: string[];
}

export type VerdictDecision = 'match' | 'no_match' | 'uncertain';

/** agent_verdict.schema.json (Wali, agents) */
export interface AgentVerdict extends BaseEvent {
  type: 'agent_verdict';
  agent_id: string;
  camera_id: string;
  subject_id: string;
  decision: VerdictDecision;
  confidence: number;
  reason: string;
  evidence_event_ids: string[];
}

export type IncidentStatus = 'tracking' | 'alert' | 'resolved';
export type Priority = 'low' | 'medium' | 'high';

export interface PathStep {
  camera_id: string;
  ts: number;
  event_id?: string;
}

export interface PredictedNext {
  camera_id: string;
  probability: number;
}

/** dispatch.schema.json (Michael, dispatcher; shown on screen as "coordinator") */
export interface Dispatch extends BaseEvent {
  type: 'dispatch';
  incident_id: string;
  subject_id: string;
  incident_type: Activity;
  subject_appearance?: string | null;
  status: IncidentStatus;
  priority: Priority;
  path: PathStep[];
  predicted_next: PredictedNext[];
  recommendation: string;
  reason: string;
  evidence_event_ids: string[];
  requires_human_confirm: boolean;
}

export type OperatorDecision = 'confirm' | 'dismiss';

/** operator_action.schema.json (Mina, dashboard) */
export interface OperatorAction extends BaseEvent {
  type: 'operator_action';
  incident_id: string;
  action: OperatorDecision;
  note?: string | null;
}

export type CameraHealth = 'online' | 'offline' | 'degraded';
export type SourceKind = 'replay' | 'live';

/** camera_status.schema.json (Mina, feeds) */
export interface CameraStatus extends BaseEvent {
  type: 'camera_status';
  camera_id: string;
  status: CameraHealth;
  fps?: number | null;
  source_kind: SourceKind;
}

export type ClarityEvent = Detection | Relay | AgentVerdict | Dispatch | OperatorAction | CameraStatus;
export type EventType = ClarityEvent['type'];

export const EVENT_TYPES: readonly EventType[] = [
  'detection', 'relay', 'agent_verdict', 'dispatch', 'operator_action', 'camera_status',
];

// ---- cameras.json (cameras.schema.json) ----

export interface LatLon {
  lat: number;
  lon: number;
}

/** 0-1 position on a schematic site image. */
export interface SiteXY {
  x: number;
  y: number;
}

export interface Neighbor {
  camera_id: string;
  travel_time_s: number;
  direction: Direction;
}

export interface CameraSource {
  kind: SourceKind;
  uri: string;
  start_ts?: number | null;
}

export interface Camera {
  camera_id: string;
  name: string;
  position?: LatLon | null;
  site_xy?: SiteXY | null;
  heading_deg?: number | null;
  neighbors: Neighbor[];
  source: CameraSource;
}

export interface SiteMap {
  center?: LatLon | null;
  zoom?: number;
  site_image?: string | null;
}

export interface CamerasConfig {
  schema_version: '0.1';
  site_id: string;
  site_name?: string;
  map?: SiteMap | null;
  cameras: Camera[];
}

// ---- bus-only message (not a contract schema; shape from bus/server.py ws_stream) ----

/** First message on WS /ws. `cameras` is null when the bus can't read its cameras.json. */
export interface BusSnapshot {
  type: 'bus_snapshot';
  run_id: string;
  cameras: CamerasConfig | null;
  events: unknown[];
}
