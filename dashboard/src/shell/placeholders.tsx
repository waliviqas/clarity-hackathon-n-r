// Temporary stand-ins shown until the real map (dashboard-map), agent graph (src/graph/) and
// panels (src/panels/) exist. They double as a quick visual check of the store.

import { useMemo, useState } from 'react';
import {
  cameraOf, chaseVar, isScripted, LABELS, sendOperatorAction, subjectOf, useCameras, useCameraStatus,
  useDetectionSubjects, useEvents, useIncidents, useSelection, useSubjectColors,
} from '../lib';
import type { OperatorDecision } from '../lib';

export function MapPlaceholder() {
  const { site, list } = useCameras();
  const status = useCameraStatus();
  return (
    <div className="placeholder">
      <h2 className="panel-title">Map</h2>
      <p className="placeholder-note">
        {site
          ? `${list.length} cameras at ${site.site_name ?? site.site_id}. The map comes in the next build step.`
          : 'Waiting for the camera list from the event bus.'}
      </p>
      <div className="placeholder-scroll">
        <ul className="cam-list">
          {list.map((c) => (
            <li key={c.camera_id}>
              {c.name} <span className="cam-status">{status[c.camera_id]?.status ?? 'no status yet'}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function GraphPlaceholder() {
  return (
    <div className="placeholder">
      <h2 className="panel-title">Agent graph</h2>
      <p className="placeholder-note">Camera agents and the {LABELS.coordinator} will show here.</p>
    </div>
  );
}

/** Minimal incident list with Confirm / Dismiss, until src/panels/IncidentCards.tsx exists. */
export function IncidentsPlaceholder() {
  const incidents = useIncidents();
  const { selection, select } = useSelection();
  const [sending, setSending] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const decide = async (incidentId: string, action: OperatorDecision) => {
    setSending((s) => ({ ...s, [incidentId]: true }));
    const result = await sendOperatorAction(incidentId, action);
    setSending((s) => ({ ...s, [incidentId]: false }));
    setErrors((e) => ({ ...e, [incidentId]: result.ok ? '' : (result.error ?? 'failed') }));
  };

  return (
    <div className="placeholder">
      <h2 className="panel-title">Incidents</h2>
      <div className="placeholder-scroll">
        {incidents.length === 0 && <p className="placeholder-note">{LABELS.noIncidents}</p>}
        {incidents.map((inc) => {
          const d = inc.dispatch;
          const word = inc.action ? LABELS.status[inc.action.action] : LABELS.status[d.status];
          const cls = inc.action ? `is-${inc.action.action}` : d.status === 'alert' ? 'is-alert' : '';
          return (
            <div
              key={inc.incident_id}
              className="inc-row"
              style={{ borderLeftColor: `var(--chase-${inc.chase})` }}
              onClick={() => select(selection === d.event_id ? null : d.event_id)}
            >
              <div className="inc-main">
                <div>
                  {d.incident_type.replace('_', ' ')} {inc.scripted && <span className="tag">{LABELS.scripted}</span>}
                </div>
                <div className={`inc-status ${cls}`}>{word}</div>
                {errors[inc.incident_id] && <div className="inc-error">{errors[inc.incident_id]}</div>}
              </div>
              <button
                disabled={!!inc.action || sending[inc.incident_id]}
                onClick={(ev) => { ev.stopPropagation(); void decide(inc.incident_id, 'confirm'); }}
              >Confirm</button>
              <button
                disabled={!!inc.action || sending[inc.incident_id]}
                onClick={(ev) => { ev.stopPropagation(); void decide(inc.incident_id, 'dismiss'); }}
              >Dismiss</button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const MAX_ROWS = 300;

/** Raw event list, newest first, until src/panels/ReceiptsLog.tsx exists. Click a row to select it. */
export function RawEventsPlaceholder() {
  const events = useEvents();
  const { selection, highlighted, select } = useSelection();
  useSubjectColors(); // re-render when colors are assigned
  useDetectionSubjects();
  const rows = useMemo(() => events.slice(-MAX_ROWS).reverse(), [events]);

  return (
    <div className="placeholder">
      <h2 className="panel-title">Raw events</h2>
      <div className="placeholder-scroll">
        {rows.length === 0 && <p className="placeholder-note">No events yet.</p>}
        {rows.map((e) => {
          const subject = subjectOf(e);
          const cls = ['raw-row', highlighted.has(e.event_id) ? 'is-highlighted' : '',
            selection === e.event_id ? 'is-selected' : ''].join(' ');
          return (
            <button key={e.event_id} className={cls}
              onClick={() => select(selection === e.event_id ? null : e.event_id)}>
              <span className="raw-ts">{e.ts.toFixed(1)} s</span>
              <span className="raw-type">{e.type.replace('_', ' ')}</span>
              <span className="raw-id" style={subject ? { color: chaseVar(subject) } : undefined}>
                {e.event_id} {cameraOf(e) ?? ''}
              </span>
              {isScripted(e) ? <span className="tag">{LABELS.scripted}</span> : <span />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
