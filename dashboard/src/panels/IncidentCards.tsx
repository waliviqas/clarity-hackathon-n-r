// Incident cards: one per incident (the latest dispatch per incident_id, from the shared store).
// Order: needs your decision, then tracking, then resolved. Confirm / Dismiss POST an operator_action
// through sendOperatorAction (lib builds the op_ id and the run-clock ts). Clicking a card selects its
// latest dispatch so the map, graph and receipts highlight what it cites.
// Compact so three "needs your decision" cards fit at once (~122 px each: the button group sits beside
// the recommendation); tracking cards ~85 px; resolved cards collapse to one ~44 px line. The title
// wraps to a second line instead of hiding the place name. Clamped text stays in the DOM (screen
// readers get all of it) and is repeated in a title attribute for hover.
// "Watch last sighting" opens SightingModal: the camera clip of the newest path step. It sits in the
// button group after Confirm / Dismiss (or alone there on tracking cards); one-line resolved cards
// have no button group, so it stays on their single line.

import { useEffect, useMemo, useState } from 'react';
import type { MouseEvent } from 'react';
import {
  LABELS, cameraName, select, sendOperatorAction, useCameras, useConnection, useIncidents, useStore,
} from '../lib';
import type { Camera, IncidentView, OperatorDecision } from '../lib';
import SightingModal from './SightingModal.tsx';
import './IncidentCards.css';

const TYPE_LABEL: Record<string, string> = {
  stabbing: 'Stabbing',
  fistfight: 'Fistfight',
  purse_snatch: 'Purse snatch',
  none: 'Incident',
};

const PRIORITY_LABEL: Record<string, string> = {
  high: 'High priority',
  medium: 'Medium priority',
  low: 'Low priority',
};

const MSG_NETWORK = "Couldn't reach the event bus. Try again when it reconnects.";
const MSG_REJECTED = "The event bus didn't accept this decision. Try again.";

type Phase = 'decide' | 'active' | 'done';
const PHASE_RANK: Record<Phase, number> = { decide: 0, active: 1, done: 2 };

type Tone = 'alert' | 'tracking' | 'confirm' | 'dismiss' | 'resolved';

interface SendError {
  message: string;
  /** Technical detail from the lib (shown on hover, logged to the console). */
  detail: string;
  /** Network failure: clears by itself when the bus connection comes back. */
  network: boolean;
}

/** A table's own entry, never an inherited one (a junk value like "constructor" gets undefined). */
function own<T>(table: Readonly<Record<string, T>>, key: unknown): T | undefined {
  return typeof key === 'string' && Object.hasOwn(table, key) ? table[key] : undefined;
}

function sentenceType(t: string): string {
  const known = own(TYPE_LABEL, t);
  if (known) return known;
  const words = String(t ?? '').replace(/_/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : TYPE_LABEL.none;
}

function phaseOf(inc: IncidentView): Phase {
  if (inc.action) return 'done';
  const d = inc.dispatch;
  if (d.status === 'resolved') return 'done';
  if (d.status === 'alert' && d.requires_human_confirm) return 'decide';
  return 'active';
}

function statusOf(inc: IncidentView): { word: string; tone: Tone } {
  if (inc.action) {
    const a = inc.action.action;
    return { word: own<string>(LABELS.status, a) ?? String(a), tone: a === 'confirm' ? 'confirm' : 'dismiss' };
  }
  const d = inc.dispatch;
  if (d.status === 'alert') {
    return d.requires_human_confirm
      ? { word: LABELS.status.alert, tone: 'alert' }
      : { word: LABELS.status.alertNoConfirm, tone: 'alert' };
  }
  if (d.status === 'resolved') return { word: LABELS.status.resolved, tone: 'resolved' };
  return { word: LABELS.status.tracking, tone: 'tracking' };
}

/** Camera name of the first path step (where the incident started), or null. */
function whereOf(inc: IncidentView, byId: Readonly<Record<string, Camera>>): string | null {
  const path = inc.dispatch.path;
  const first = Array.isArray(path) && path.length ? path[0] : null;
  if (!first || typeof first.camera_id !== 'string') return null;
  return cameraName(own(byId, first.camera_id), first.camera_id);
}

/** True when the path has a step with a camera and a time (something to watch). */
function hasSighting(inc: IncidentView): boolean {
  const path: unknown = inc.dispatch.path;
  return Array.isArray(path) && path.some((s: unknown) => !!s && typeof s === 'object'
    && typeof (s as { camera_id?: unknown }).camera_id === 'string'
    && typeof (s as { ts?: unknown }).ts === 'number' && Number.isFinite((s as { ts: number }).ts));
}

/** Ends a fragment with a full stop unless it already ends a sentence. */
function sentence(s: string): string {
  return /[.!?]$/.test(s) ? s : `${s}.`;
}

/** One muted line under the recommendation, as plain sentences: priority, suspect, the coordinator's reason.
    e.g. "High priority. Suspect: male, red hoodie, blue jeans. Seen at Route 1: south walkway, then …" */
function metaLine(inc: IncidentView): string {
  const d = inc.dispatch;
  const parts: string[] = [];
  const priority = own(PRIORITY_LABEL, d.priority);
  if (priority) parts.push(sentence(priority));
  const look = typeof d.subject_appearance === 'string' ? d.subject_appearance.trim().replace(/\.+$/, '') : '';
  if (look) parts.push(sentence(`Suspect: ${look}`));
  const reason = typeof d.reason === 'string' ? d.reason.trim() : '';
  if (reason) parts.push(sentence(reason));
  return parts.join(' ');
}

export default function IncidentCards() {
  const incidents = useIncidents();
  const { byId } = useCameras();
  const connState = useConnection().state;
  const selection = useStore((s) => s.selection);
  const selectedEvent = useStore((s) => (s.selection ? s.eventsById.get(s.selection) : undefined));
  const [sending, setSending] = useState<Readonly<Record<string, OperatorDecision>>>({});
  const [errors, setErrors] = useState<Readonly<Record<string, SendError>>>({});
  /** incident_id whose last sighting is playing in the pop-up, or null. */
  const [watching, setWatching] = useState<string | null>(null);
  const watched = watching ? incidents.find((inc) => inc.incident_id === watching) : undefined;

  // The incident went away (a new bus snapshot replaced the state): close the pop-up for good.
  useEffect(() => {
    if (watching && !watched) setWatching(null);
  }, [watching, watched]);

  // "Couldn't reach the event bus" goes away by itself once the socket is back.
  useEffect(() => {
    if (connState !== 'open') return;
    setErrors((prev) => {
      const keep = Object.entries(prev).filter(([, e]) => !e.network);
      return keep.length === Object.keys(prev).length ? prev : Object.fromEntries(keep);
    });
  }, [connState]);

  const sorted = useMemo(
    () => incidents
      .map((inc, i) => ({ inc, i, rank: PHASE_RANK[phaseOf(inc)] }))
      .sort((a, b) => a.rank - b.rank || a.i - b.i)
      .map((x) => x.inc),
    [incidents],
  );
  const needDecision = sorted.filter((inc) => phaseOf(inc) === 'decide').length;

  // A selected dispatch or operator_action of this incident (e.g. from a receipt) marks its card.
  const selectedIncident = selectedEvent && (selectedEvent.type === 'dispatch' || selectedEvent.type === 'operator_action')
    ? selectedEvent.incident_id
    : null;

  const decide = async (incidentId: string, action: OperatorDecision) => {
    if (own(sending, incidentId)) return;
    setSending((s) => ({ ...s, [incidentId]: action }));
    setErrors((prev) => {
      if (!Object.hasOwn(prev, incidentId)) return prev;
      const next = { ...prev };
      delete next[incidentId];
      return next;
    });
    const result = await sendOperatorAction(incidentId, action);
    setSending((s) => {
      const next = { ...s };
      delete next[incidentId];
      return next;
    });
    if (!result.ok) {
      const detail = result.error ?? 'unknown error';
      const rejected = detail.startsWith('HTTP ');
      console.warn(`operator_action ${result.event.event_id} for ${incidentId} failed: ${detail}`);
      setErrors((prev) => ({
        ...prev,
        [incidentId]: { message: rejected ? MSG_REJECTED : MSG_NETWORK, detail, network: !rejected },
      }));
    }
  };

  const toggleSelect = (dispatchId: string) => select(selection === dispatchId ? null : dispatchId);

  return (
    <div className="ic">
      <div className="ic-head">
        <h2 className="ic-title">Incidents</h2>
        <span className="ic-count" aria-live="polite">
          {needDecision > 0 ? `${needDecision} ${needDecision === 1 ? 'needs' : 'need'} your decision` : ''}
        </span>
      </div>
      <div className="ic-scroll">
        {sorted.length === 0 ? (
          <p className="ic-empty">{LABELS.noIncidents}</p>
        ) : (
          <ul className="ic-list">
            {sorted.map((inc) => {
              const d = inc.dispatch;
              const phase = phaseOf(inc);
              const status = statusOf(inc);
              const where = whereOf(inc, byId);
              const type = sentenceType(d.incident_type);
              const title = where ? `${type} at ${where}` : type;
              const spoken = where ? `${type.toLowerCase()} at ${where}` : `${type.toLowerCase()} ${inc.incident_id}`;
              const showButtons = d.requires_human_confirm === true && !inc.action;
              const busy = own(sending, inc.incident_id);
              const error = inc.action ? undefined : own(errors, inc.incident_id);
              const meta = metaLine(inc);
              const reco = typeof d.recommendation === 'string' ? d.recommendation : '';
              // Resolved cards collapse to one line, unless they somehow still ask for a decision.
              const oneLine = phase === 'done' && !showButtons;
              const isSelected = selection === d.event_id || selectedIncident === inc.incident_id;
              const cls = ['ic-card', `is-${phase}`, oneLine ? 'is-line' : '', isSelected ? 'is-selected' : '']
                .filter(Boolean).join(' ');

              const onButton = (action: OperatorDecision) => (ev: MouseEvent<HTMLButtonElement>) => {
                ev.stopPropagation();
                void decide(inc.incident_id, action);
              };
              const onWatch = (ev: MouseEvent<HTMLButtonElement>) => {
                ev.stopPropagation(); // opening the video doesn't toggle the card's selection
                setWatching(inc.incident_id);
              };
              const watchButton = hasSighting(inc) ? (
                <button
                  type="button"
                  className="ic-watch"
                  aria-haspopup="dialog"
                  aria-label={`Watch last sighting, ${spoken}`}
                  onClick={onWatch}
                >Watch last sighting</button>
              ) : null;

              return (
                <li
                  key={inc.incident_id}
                  className={cls}
                  style={{ borderLeftColor: `var(--chase-${inc.chase})` }}
                  onClick={() => toggleSelect(d.event_id)}
                >
                  <div className="ic-top">
                    {/* The whole card is clickable; this button is the keyboard / screen-reader way in.
                        Its click bubbles to the card, so it has no handler of its own. The inner span
                        carries the 2-line clamp (a button can't be a -webkit-box itself everywhere). */}
                    <button type="button" className="ic-name" title={title} aria-pressed={selection === d.event_id}>
                      <span className="ic-name-text">{title}</span>
                    </button>
                    <span className={`ic-status tone-${status.tone}`}>{status.word}</span>
                    {busy && <span className="ic-sending" role="status">Sending…</span>}
                    {/* Resolved cards are one line: the recommendation shrinks into what's left of it,
                        and "Watch last sighting" stays on that line (they have no button group). */}
                    {oneLine && reco && <span className="ic-reco-inline" title={reco}>{reco}</span>}
                    {oneLine && watchButton}
                    {inc.scripted && <span className="tag">{LABELS.scripted}</span>}
                  </div>
                  {!oneLine && (
                    <div className="ic-body">
                      <p className="ic-reco" title={reco || undefined}>{reco}</p>
                      {(showButtons || watchButton) && (
                        <div className="ic-actions">
                          {showButtons && (
                            <>
                              <button
                                type="button"
                                className="ic-btn ic-btn-confirm"
                                aria-label={`Confirm ${spoken}`}
                                disabled={!!busy}
                                onClick={onButton('confirm')}
                              >Confirm</button>
                              <button
                                type="button"
                                className="ic-btn"
                                aria-label={`Dismiss ${spoken}`}
                                disabled={!!busy}
                                onClick={onButton('dismiss')}
                              >Dismiss</button>
                            </>
                          )}
                          {watchButton}
                        </div>
                      )}
                    </div>
                  )}
                  {!oneLine && meta && <p className="ic-meta" title={meta}>{meta}</p>}
                  {error && <p className="ic-error" role="alert" title={error.detail}>{error.message}</p>}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {/* Outside the cards, so clicks inside the pop-up never reach a card's click handler. */}
      {watched && (
        <SightingModal
          incident={watched}
          typeWord={watched.dispatch.incident_type === 'none' ? '' : sentenceType(watched.dispatch.incident_type).toLowerCase()}
          onClose={() => setWatching(null)}
        />
      )}
    </div>
  );
}
