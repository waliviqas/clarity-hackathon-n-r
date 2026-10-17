// Map sizes shared by the React layers and the pure geometry (plain Node can import this file).

/** Marker dot diameter (at least 18px so it reads on video). Keep in sync with .cam-icon sizing in map.css. */
export const MARKER_PX = 18;
/** Outer radius of the alert ring around the dot (map.css .cam-alert-ring: inset -7px, 3px border). */
export const ALERT_RING_R = MARKER_PX / 2 + 7;
/**
 * Label type, mirrored from map.css .cam-label (sizes = --fs-body / --fs-small in tokens.css).
 * The label layout measures text with these, so change both together.
 */
export const LABEL_FONT = {
  namePx: 15,
  nameSmallPx: 13,
  nameWeight: 500,
  subPx: 13,
  subWeight: 600,
  lineHeight: 1.15,
} as const;

/** Chase drawing, in screen pixels (spec: paths 4px, relay arrows 3px, predictions 2px dashed at 60%). */
export const CHASE_STYLE = {
  pathWeight: 4,
  arrowWeight: 3,
  predictWeight: 2,
  predictOpacity: 0.6,
  /** Relay dash pattern: dash, gap. Its period must match the relay-dash keyframes in map.css (18px). */
  arrowDash: '10 8',
  predictDash: '6 6',
  /** Highlighted (selected or cited) lines get this much thicker. */
  highlightExtra: 2,
  /** Opacity of chase lines that aren't part of the selection while something is selected. */
  dimOpacity: 0.28,
  /** Invisible click target around each line. */
  hitWeight: 16,
} as const;

/** Relay arrow geometry, screen px. */
export const ARROW = {
  /** The arrow starts this far from the sending camera's center (outside its dot). */
  startTrim: MARKER_PX / 2 + 4,
  /** The arrowhead tip stops this far from the receiving camera's center (just outside its dot). */
  tipTrim: MARKER_PX / 2 + 5,
  headLen: 12,
  headWidth: 11,
  /** Sideways shift (to the right of travel) beside a predicted line or an opposite arrow on the same pair. */
  offset: 6,
} as const;

/** "70%" labels on predicted lines, screen px. Mirrors .chase-prob in map.css. */
export const PROB_LABEL = {
  fontPx: 13,
  padX: 5,
  height: 19,
  /** Lines shorter than this get no label. */
  minLine: 48,
} as const;
