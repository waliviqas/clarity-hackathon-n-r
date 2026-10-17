// Palette, timings and on-screen words in one place.
// The hex values mirror src/tokens.css (CSS needs them as variables, SVG/canvas needs real hex):
// change both together.

/** --chase-1..5: one per subject, in order of first appearance. */
export const CHASE_COLORS = ['#FFB020', '#46B4F5', '#B48CFF', '#3DD6A3', '#F27BA6'] as const;

export const COLORS = {
  ink: '#0E1A24',
  panel: '#132230',
  rule: '#24384A',
  text: '#E6EDF2',
  muted: '#8EA3B3',
  alert: '#FF6B5A',
  ok: '#46C38A',
  /** agent_verdict "uncertain" (amber; always paired with a "?" so it never relies on color). */
  uncertain: '#FFB020',
  /** Returned by colorFor() for a subject that has no color yet (e.g. a bare detection). */
  unassigned: '#E6EDF2',
} as const;

/** Animation and connection timings (milliseconds unless the name says _s). */
export const TIMING = {
  /** An event stays in `recent` this long after it arrives live (snapshot events never do). */
  recentWindowMs: 6000,
  recentPruneMs: 1000,
  /** Live events are applied in small batches so a fast replay doesn't re-render per event. */
  flushMs: 16,
  detectionPulseMs: 1500,
  edgeFlashMs: 1200,
  verdictBadgeMs: 5000,
  /** A relay arrow stays until a verdict at to_camera, or expected_arrival_s + this many run-clock seconds. */
  relayGraceS: 10,
  /** ...and when the relay has no expected_arrival_s, assume this many run-clock seconds. */
  relayDefaultArrivalS: 30,
  /** A relay arrow fades out over this long after a no_match / uncertain verdict at its target. */
  relayFadeMs: 1200,
  /** One trip of the travelling relay dash along its pattern (the only continuous animation). */
  relayDashMs: 700,
  reconnectMinMs: 500,
  reconnectMaxMs: 5000,
  /** Small text frame so idle tunnels (brev port-forward) don't drop the socket; the bus ignores it. */
  keepaliveMs: 20000,
  postTimeoutMs: 5000,
} as const;

/** On-screen words (sentence case). The dispatcher agent is always "coordinator" on screen. */
export const LABELS = {
  coordinator: 'coordinator',
  scripted: 'Scripted run',
  status: {
    tracking: 'Tracking',
    alert: 'Needs your decision',
    /** dispatch.status "alert" with requires_human_confirm false (no Confirm/Dismiss needed). */
    alertNoConfirm: 'Alert',
    resolved: 'Resolved',
    confirm: 'Confirmed',
    dismiss: 'Dismissed',
  },
  noIncidents: 'No incidents yet.',
  /** Map badge on a camera for 5 s after its agent answers a relay without a match. */
  verdictBadge: {
    no_match: '✕ no match',
    uncertain: '? uncertain',
  },
  /** detection.activity / dispatch.incident_type as words. */
  activity: {
    stabbing: 'Stabbing',
    fistfight: 'Fistfight',
    purse_snatch: 'Purse snatch',
    none: 'No crime seen',
  },
  /** camera_status.status as words. */
  cameraHealth: {
    online: 'Online',
    offline: 'Offline',
    degraded: 'Degraded',
  },
} as const;

/** `source` value that marks a scripted (fake) event. */
export const SCRIPTED_SOURCE = 'fake_scenario';

/** `source` the dashboard puts on its own operator_action events. */
export const DASHBOARD_SOURCE = 'dashboard';

export const SCHEMA_VERSION = '0.1';
