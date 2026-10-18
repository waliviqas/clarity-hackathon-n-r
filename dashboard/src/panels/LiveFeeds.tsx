import { useEffect, useMemo, useState } from 'react';
import { BUS_URL, cameraName, sendOperatorAction, useCameras, useEvents, useIncidents, useSubjectColors } from '../lib';
import type { IncidentView } from '../lib';
import type { ClarityEvent } from '../lib';
import { clipSeek, clipUrl } from './clips.ts';
import { setFeedProgress } from '../lib/feedProgress.ts';
import './LiveFeeds.css';

const CRIME_WORDS: Readonly<Record<string, string>> = {
  stabbing: 'Stabbing', fistfight: 'Fistfight', purse_snatch: 'Purse snatch',
};

interface Feed {
  subjectId: string;
  activity: string | null;
  /** Run-clock ts when the crime was reported (its first relay). */
  crimeTs: number;
  /** Cameras that saw this subject, in the order they reported (crime camera first). */
  cameras: string[];
}

/** One feed per subject: the crime camera (its first relay) and every camera that matched it, in arrival order. */
function deriveFeeds(events: readonly ClarityEvent[]): Feed[] {
  const feeds = new Map<string, Feed>();
  const add = (subjectId: string, cameraId: string) => {
    let f = feeds.get(subjectId);
    if (!f) { f = { subjectId, activity: null, crimeTs: Number.NaN, cameras: [] }; feeds.set(subjectId, f); }
    if (!f.cameras.includes(cameraId)) f.cameras.push(cameraId);
    return f;
  };
  for (const e of events) {
    if (e.type === 'relay') {
      const f = add(e.subject_id, e.from_camera);
      if (!f.activity && typeof e.activity === 'string') f.activity = e.activity;
      if (Number.isNaN(f.crimeTs)) f.crimeTs = e.ts;
    } else if (e.type === 'agent_verdict' && e.decision === 'match') {
      add(e.subject_id, e.camera_id);
    }
  }
  return [...feeds.values()];
}

export default function LiveFeeds() {
  const events = useEvents();
  const colors = useSubjectColors();
  const { byId, list } = useCameras();
  const feeds = useMemo(() => deriveFeeds(events), [events]);
  const incidents = useIncidents();
  const bySubject = useMemo(() => new Map(incidents.map((i) => [i.subject_id, i])), [incidents]);
  const [report, setReport] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) => setExpanded((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  if (!feeds.length) return <div className="feeds-empty">Watching every camera. A bar appears here when a crime is seen.</div>;

  return (
    <div className="feeds">
      {feeds.map((f) => {
        const color = colors[f.subjectId] ?? '#888';
        const current = f.cameras[f.cameras.length - 1];
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
                {/* key = subject + camera: a new camera remounts the player. Later cameras play from the beginning;
                    the crime camera starts a few seconds before the crime was reported, so the crime plays first. */}
                <video key={`${f.subjectId}:${current}`} className="feed-video" src={clipUrl(BUS_URL, current)}
                  autoPlay muted playsInline
                  onLoadedMetadata={(ev) => {
                    const v = ev.currentTarget;
                    v.dataset.from = '0';
                    if (f.cameras.length !== 1) return;
                    v.currentTime = Math.min(clipSeek(f.crimeTs, byId[current]?.source?.start_ts), Math.max(0, v.duration - 0.5));
                    v.dataset.from = String(v.currentTime);
                  }}
                  onTimeUpdate={(ev) => {
                    // share of this clip played since it opened: drives the map's tracker toward the next camera
                    const v = ev.currentTarget;
                    const from = Number(v.dataset.from ?? 0);
                    const span = v.duration - from;
                    if (span > 0) setFeedProgress(f.subjectId, current, Math.min(1, Math.max(0, (v.currentTime - from) / span)));
                  }}
                  onEnded={() => setFeedProgress(f.subjectId, current, 1)} />
                <ol className="feed-steps">
                  {f.cameras.map((c, i) => (
                    <li key={c} className={c === current ? 'now' : ''}
                      style={c === current ? { background: color, borderColor: color } : { borderColor: color }}>
                      {i === 0 ? 'Crime' : `Cam ${i + 1}`}
                    </li>
                  ))}
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
