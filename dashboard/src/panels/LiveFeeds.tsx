import { useEffect, useMemo, useState } from 'react';
import { BUS_URL, cameraName, sendOperatorAction, useCameras, useEvents, useIncidents, useSubjectColors } from '../lib';
import type { IncidentView } from '../lib';
import type { ClarityEvent } from '../lib';
import { clipUrl } from './clips.ts';
import { setFeedProgress } from '../lib/feedProgress.ts';
import './LiveFeeds.css';

const CRIME_WORDS: Readonly<Record<string, string>> = {
  stabbing: 'Stabbing', fistfight: 'Fistfight', purse_snatch: 'Pickpocket',
};

interface Feed {
  subjectId: string;
  activity: string | null;
  /** Run-clock ts when the crime was reported (its first relay). */
  crimeTs: number;
  /** Cameras that saw this subject, in the order they reported (crime camera first). */
  cameras: string[];
  /** Run-clock ts when each camera saw this subject: the crime report for the crime camera, else its verdict. */
  seenAt: Record<string, number>;
}

/** One feed per subject: the crime camera (its first relay) and every camera that matched it, in arrival order. */
function deriveFeeds(events: readonly ClarityEvent[]): Feed[] {
  const feeds = new Map<string, Feed>();
  const verdictTs = new Map<string, number>(); // "<subject>:<camera>" -> ts of that camera's first verdict
  const add = (subjectId: string, cameraId: string, ts: number) => {
    let f = feeds.get(subjectId);
    if (!f) { f = { subjectId, activity: null, crimeTs: Number.NaN, cameras: [], seenAt: {} }; feeds.set(subjectId, f); }
    if (!f.cameras.includes(cameraId)) { f.cameras.push(cameraId); f.seenAt[cameraId] = ts; }
    return f;
  };
  for (const e of events) {
    if (e.type === 'relay') {
      // a relay's camera saw the suspect when it gave its verdict (the crime camera: when it reported the crime)
      const f = add(e.subject_id, e.from_camera, verdictTs.get(`${e.subject_id}:${e.from_camera}`) ?? e.ts);
      if (!f.activity && typeof e.activity === 'string') f.activity = e.activity;
      if (Number.isNaN(f.crimeTs)) f.crimeTs = e.ts;
    } else if (e.type === 'agent_verdict') {
      const key = `${e.subject_id}:${e.camera_id}`;
      if (!verdictTs.has(key)) verdictTs.set(key, e.ts);
      if (e.decision === 'match') add(e.subject_id, e.camera_id, e.ts);
    }
  }
  return [...feeds.values()];
}

/**
 * A sighting's time of day ("4:35:21 PM", Raleigh time). `ts` is run-clock seconds; `baseMs` is the wall-clock time of
 * run-clock 0 (see LiveFeeds). Epoch-second ts (live runs on a wall clock) need no base. No base yet: "".
 */
function timeOfDay(ts: number | undefined, baseMs: number | null): string {
  if (ts === undefined || !Number.isFinite(ts)) return '';
  const ms = ts > 1e9 ? ts * 1000 : baseMs === null ? null : baseMs + ts * 1000;
  return ms === null ? '' : formatTime(ms);
}

function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', second: '2-digit', timeZone: 'America/New_York',
  });
}

export default function LiveFeeds() {
  const events = useEvents();
  const colors = useSubjectColors();
  const { byId, list, site } = useCameras();
  const feeds = useMemo(() => deriveFeeds(events), [events]);
  // Wall-clock time of run-clock 0, for the sighting times: the site's optional clock_start (ISO, e.g. when a replayed
  // clip was really filmed) wins; otherwise run-clock 0 is anchored to when the first event of the run arrived.
  const clockStart = (site as { clock_start?: unknown } | null)?.clock_start;
  const fixedBase = typeof clockStart === 'string' && Number.isFinite(Date.parse(clockStart)) ? Date.parse(clockStart) : null;
  const [arrivalBase, setArrivalBase] = useState<number | null>(null);
  useEffect(() => {
    if (!events.length) { if (arrivalBase !== null) setArrivalBase(null); return; }
    if (arrivalBase === null) setArrivalBase(Date.now() - events[0].ts * 1000);
  }, [events, arrivalBase]);
  // A sighting's time of day: the camera's own clock when cameras.json gives one (recorded_at = when its clip's first
  // frame was filmed, and the sighting is ts - start_ts seconds into the clip), else the run clock's anchor above.
  const when = (camera: string, ts: number | undefined): string => {
    const cam: { recorded_at?: unknown; source?: { start_ts?: number | null } } | undefined = byId[camera];
    const filmed = typeof cam?.recorded_at === 'string' ? Date.parse(cam.recorded_at) : Number.NaN;
    const start = cam?.source?.start_ts;
    if (ts !== undefined && Number.isFinite(ts) && Number.isFinite(filmed) && typeof start === 'number') {
      return formatTime(filmed + Math.max(0, ts - start) * 1000);
    }
    return timeOfDay(ts, fixedBase ?? arrivalBase);
  };
  const incidents = useIncidents();
  const bySubject = useMemo(() => new Map(incidents.map((i) => [i.subject_id, i])), [incidents]);
  const [report, setReport] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) => setExpanded((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  // The camera whose clip each feed shows when the operator picked one; no entry = follow the newest sighting.
  const [picked, setPicked] = useState<Readonly<Record<string, string>>>({});
  const pick = (subjectId: string, camera: string | null) => setPicked((p) => {
    const next = { ...p };
    if (camera === null) delete next[subjectId]; else next[subjectId] = camera;
    return next;
  });

  if (!feeds.length) return <div className="feeds-empty">Watching every camera. A bar appears here when a crime is seen.</div>;

  return (
    <div className="feeds">
      {feeds.map((f) => {
        const color = colors[f.subjectId] ?? '#888';
        const current = f.cameras[f.cameras.length - 1];
        const chosen = picked[f.subjectId];
        const shown = chosen && f.cameras.includes(chosen) ? chosen : current;
        const at = f.cameras.indexOf(shown);
        // picking the newest camera goes back to following new sightings
        const show = (i: number) => pick(f.subjectId, i >= f.cameras.length - 1 ? null : f.cameras[i]);
        const isOpen = expanded.has(f.subjectId);
        return (
          <section key={f.subjectId} className={`feed${isOpen ? ' is-open' : ''}`} style={{ borderColor: color }}>
            {/* the crime bar: click to open / close this incident's CCTV footage */}
            <header className="feed-head" role="button" tabIndex={0} aria-expanded={isOpen}
              onClick={() => toggle(f.subjectId)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(f.subjectId); } }}>
              <span className="feed-dot" style={{ background: color }} />
              <strong style={{ color }}>{f.activity ? CRIME_WORDS[f.activity] ?? f.activity : 'Suspect'}</strong>
              <span className="feed-cam">{f.cameras.length === 1 ? 'Crime camera' : `Camera ${f.cameras.length}`}</span>
              <span className="feed-spacer" />
              <button className={`dispatch-btn${bySubject.has(f.subjectId) ? ' is-ready' : ''}`}
                style={{ ['--c' as string]: color }} disabled={!bySubject.has(f.subjectId)}
                onClick={(e) => { e.stopPropagation(); setReport(report === f.subjectId ? null : f.subjectId); }}>
                Dispatch report
              </button>
              <span className="feed-chevron" aria-hidden="true">{isOpen ? '\u25B4' : '\u25BE'}</span>
            </header>
            {report === f.subjectId && bySubject.has(f.subjectId) && (
              <DispatchReport incident={bySubject.get(f.subjectId)!} color={color} onClose={() => setReport(null)}
                cameraWords={routeWords(f.cameras[0], list)} />
            )}
            {isOpen ? (
              <>
                {/* key = subject + camera: a new camera remounts the player, and every clip plays from its
                    beginning (0:00), the crime camera's too. */}
                <video key={`${f.subjectId}:${shown}`} className="feed-video" src={clipUrl(BUS_URL, shown)}
                  autoPlay muted playsInline
                  onLoadedMetadata={(ev) => { ev.currentTarget.currentTime = 0; }}
                  onTimeUpdate={(ev) => {
                    // share of the newest camera's clip played: drives the map's tracker toward the next camera
                    if (shown !== current) return;
                    const v = ev.currentTarget;
                    if (v.duration > 0) setFeedProgress(f.subjectId, current, Math.min(1, Math.max(0, v.currentTime / v.duration)));
                  }}
                  onEnded={() => { if (shown === current) setFeedProgress(f.subjectId, current, 1); }} />
                {/* an older camera's clip on screen: the newest camera's tracker eases on as if its clip had played */}
                {shown !== current && <ClosedTracker subjectId={f.subjectId} camera={current} />}
                <div className="feed-caption">
                  <button type="button" className="feed-nav" disabled={at <= 0} onClick={() => show(at - 1)}
                    aria-label="Previous camera">{'‹'}</button>
                  <span className="feed-caption-text">
                    {cameraName(byId[shown], shown)}{when(shown, f.seenAt[shown]) ? ` · seen at ${when(shown, f.seenAt[shown])}` : ''}
                  </span>
                  <button type="button" className="feed-nav" disabled={at >= f.cameras.length - 1} onClick={() => show(at + 1)}
                    aria-label="Next camera">{'›'}</button>
                </div>
                <ol className="feed-steps">
                  {f.cameras.map((c, i) => (
                    <li key={c} className={c === shown ? 'now' : ''}
                      style={c === shown ? { background: color, borderColor: color } : { borderColor: color }}>
                      <button type="button" className="feed-step" onClick={() => show(i)} aria-pressed={c === shown}
                        title={`${cameraName(byId[c], c)} · ${when(c, f.seenAt[c])}`}>
                        {i === 0 ? 'Crime' : `Cam ${i + 1}`} {when(c, f.seenAt[c])}
                      </button>
                    </li>
                  ))}
                  <li className="feed-steps-spacer" aria-hidden="true" />
                </ol>
              </>
            ) : <ClosedTracker subjectId={f.subjectId} camera={current} />}
          </section>
        );
      })}
    </div>
  );
}

/** With the footage closed there's no clip playing to pace the map's tracker: treat the clip as done, so the
 *  tracker eases toward the next camera on its own. */
function ClosedTracker({ subjectId, camera }: { subjectId: string; camera: string }) {
  useEffect(() => { setFeedProgress(subjectId, camera, 1); }, [subjectId, camera]);
  return null;
}

/** camera_id -> "the crime scene" / "Camera N", walking the route's neighbor links out from the crime camera. */
function routeWords(crimeCamera: string, cameras: readonly { camera_id: string; neighbors?: { camera_id: string }[] }[]): Map<string, string> {
  const byId = new Map(cameras.map((c) => [c.camera_id, c]));
  const words = new Map<string, string>([[crimeCamera, 'the crime scene']]);
  let frontier = [crimeCamera];
  while (frontier.length) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const n of byId.get(id)?.neighbors ?? []) {
        if (!words.has(n.camera_id)) { words.set(n.camera_id, `Camera ${words.size + 1}`); next.push(n.camera_id); }
      }
    }
    frontier = next;
  }
  return words;
}

const PRIORITY_WORDS: Readonly<Record<string, string>> = { high: 'High priority', medium: 'Medium priority', low: 'Low priority' };

/** The coordinator's latest dispatch for one incident, with the operator's Confirm / Dismiss. */
function DispatchReport({ incident, color, onClose, cameraWords }: {
  incident: IncidentView; color: string; onClose: () => void; cameraWords: Map<string, string>;
}) {
  const { byId } = useCameras();
  const d = incident.dispatch;
  // The dispatcher writes camera ids ("cam_10", or "<name> (cam_10)"): show each camera's own name from cameras.json
  // (where it is, from data/name_cameras.py), falling back to the chip words.
  const word = (id: string) => cameraName(byId[id], '') || cameraWords.get(id) || id;
  const named = d.recommendation
    .replace(/\s*\((cam_\d+)\)/g, '')
    .replace(/Route \d+:[^.;,]*/g, (m) => {
      const hit = Object.values(byId).find((c) => cameraName(c) === m.trim());
      return hit ? word(hit.camera_id) : m;
    })
    .replace(/\bcam_\d+\b/g, word);
  const [action, procedure] = named.split(/\s*Procedure:\s*/);
  const decided = incident.action?.action;
  const [sending, setSending] = useState(false);
  const decide = async (a: 'confirm' | 'dismiss') => {
    setSending(true);
    await sendOperatorAction(incident.incident_id, a);
    setSending(false);
  };
  return (
    <div className="dispatch-report" style={{ ['--c' as string]: color }} role="dialog" aria-label="Dispatch report">
      <header>
        <span className={`dispatch-priority is-${d.priority}`}>{PRIORITY_WORDS[d.priority] ?? d.priority}</span>
        <span className="dispatch-decide">
          {decided ? <span className="dispatch-decided">{decided === 'confirm' ? 'Confirmed' : 'Dismissed'}</span> : (
            <>
              <button disabled={sending} onClick={() => decide('confirm')}>Confirm</button>
              <button disabled={sending} onClick={() => decide('dismiss')}>Dismiss</button>
            </>
          )}
          <button className="dispatch-close" onClick={onClose} aria-label="Close">×</button>
        </span>
      </header>
      <p className="dispatch-action">{action}</p>
      {procedure && <p className="dispatch-procedure">Procedure: {procedure}</p>}
      {d.subject_appearance && <p className="dispatch-suspect">Suspect: {d.subject_appearance}</p>}

    </div>
  );
}
