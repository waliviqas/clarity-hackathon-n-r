import { memo, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { divIcon } from 'leaflet';
import type { LatLngTuple } from 'leaflet';
import { Marker } from 'react-leaflet';
import { LABELS } from '../lib';
import type { Activity, CameraHealth } from '../lib';
import type { LabelPlacement } from './labels.ts';

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

const HALF = MARKER_PX / 2;
const ALIGN = { start: 'flex-start', center: 'center', end: 'flex-end' } as const;

export interface CameraMarkerProps {
  /** Text on the map: the camera's name, or its camera_id when it has none. */
  name: string;
  lat: number;
  lon: number;
  /** Latest camera_status; undefined = no status yet (treated as online). */
  health: CameraHealth | undefined;
  /** event_id of the newest live detection here, or null. A new id restarts the ring pulse. */
  pulseId: string | null;
  /** The newest live detection is a crime: pulse in --alert instead of --text. */
  pulseCrime: boolean;
  /** Crime seen here in the recent window: --alert ring + this activity as a label. */
  crimeActivity: Exclude<Activity, 'none'> | null;
  /** Where the label goes (from the label layout); null = right of the marker. */
  label: LabelPlacement | null;
  /** Crowded map: 13 px name instead of 15 px. */
  small: boolean;
}

/**
 * One camera on the map. Leaflet owns the marker element; React renders its contents through a
 * portal into a div handed to L.divIcon (the icon object never changes, so Leaflet never rebuilds it
 * and CSS animations aren't cut short by unrelated re-renders).
 */
export const CameraMarker = memo(function CameraMarker(props: CameraMarkerProps) {
  const { name, lat, lon, health, pulseId, pulseCrime, crimeActivity, label, small } = props;
  const [container] = useState(() => document.createElement('div'));
  const icon = useMemo(() => divIcon({
    html: container,
    className: 'cam-icon',
    iconSize: [MARKER_PX, MARKER_PX],
    iconAnchor: [HALF, HALF],
  }), [container]);
  const position = useMemo<LatLngTuple>(() => [lat, lon], [lat, lon]);

  const offline = health !== undefined && health !== 'online';
  const cls = ['cam', offline ? 'is-offline' : '', crimeActivity ? 'is-alert' : ''].filter(Boolean).join(' ');
  const labelCls = ['cam-label', small ? 'is-small' : ''].filter(Boolean).join(' ');
  const leader = label?.leader;

  return (
    <>
      <Marker
        position={position}
        icon={icon}
        interactive={false}
        keyboard={false}
        zIndexOffset={crimeActivity ? 1000 : 0}
      />
      {createPortal(
        <div className={cls}>
          {crimeActivity && <span className="cam-alert-ring" aria-hidden="true" />}
          <span className="cam-dot" aria-hidden="true" />
          {pulseId && (
            <span key={pulseId} className={`cam-pulse${pulseCrime ? ' is-crime' : ''}`} aria-hidden="true" />
          )}
          {leader && (
            <span
              className="cam-leader"
              aria-hidden="true"
              style={{
                left: HALF + leader.x1,
                top: HALF + leader.y1,
                width: Math.hypot(leader.x2 - leader.x1, leader.y2 - leader.y1),
                transform: `rotate(${Math.atan2(leader.y2 - leader.y1, leader.x2 - leader.x1)}rad)`,
              }}
            />
          )}
          <span className={labelCls} style={labelStyle(label, crimeActivity !== null)}>
            <span className="cam-name">{name}</span>
            {crimeActivity && <span className="cam-activity">{LABELS.activity[crimeActivity]}</span>}
            {offline && <span className="cam-health">{LABELS.cameraHealth[health] ?? String(health)}</span>}
          </span>
        </div>,
        container,
      )}
    </>
  );
});

/** Position the label box so its anchor point (fx, fy) sits on the placement's anchor. */
function labelStyle(label: LabelPlacement | null, alert: boolean): CSSProperties {
  if (!label) {
    // Before the first layout: right of the marker, vertically centered.
    return { left: MARKER_PX + (alert ? ALERT_RING_R - HALF : 0) + 8, top: HALF, transform: 'translateY(-50%)' };
  }
  return {
    left: HALF + label.ax,
    top: HALF + label.ay,
    transform: `translate(${-label.fx * 100}%, ${-label.fy * 100}%)`,
    alignItems: ALIGN[label.align],
    textAlign: label.align === 'start' ? 'left' : label.align === 'end' ? 'right' : 'center',
  };
}
