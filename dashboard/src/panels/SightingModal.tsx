// "Watch last sighting" pop-up: the camera clip of an incident's newest path step, starting PRE_ROLL_S
// before the sighting, with one button per path step to jump between sightings. Opened from an incident
// card (IncidentCards.tsx). A native <dialog> shown with showModal(), portaled to document.body: it sits in
// the top layer above the whole page (the App slots clip their content; this never is), the rest of the page
// is inert, and Tab is kept inside it. Escape, the Close
// button or a click on the backdrop closes it; focus goes back to the button that opened it.
// If the bus has no clip for the camera, or the browser can't play it, a plain sentence replaces the player.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, SyntheticEvent } from 'react';
import { BUS_URL, cameraName, useCameras } from '../lib';
import type { IncidentView, PathStep } from '../lib';
import { CLIP_MESSAGES, PRE_ROLL_S, clampSeek, clipSeek, clipUrl, fetchClipInfo, problemFromMediaError } from './clips.ts';
import type { ClipLookup, ClipProblem } from './clips.ts';
import { formatTs } from './receipts.ts';
import './SightingModal.css';

/** Above this a ts is unix epoch seconds (live run), not run-clock seconds from a replay (as in receipts.ts). */
const EPOCH_TS = 1e9;

const FOCUSABLE = 'button:not([disabled]), [href], video[controls], [tabindex]:not([tabindex="-1"])';

interface Step {
  key: string;
  camera_id: string;
  ts: number;
}

interface Props {
  incident: IncidentView;
  /** Words for the incident type, e.g. "fistfight". */
  typeWord: string;
  onClose(): void;
}

/** Path steps that name a camera and a time, in path order. */
function stepsOf(path: readonly PathStep[] | null | undefined): Step[] {
  if (!Array.isArray(path)) return [];
  const out: Step[] = [];
  for (const s of path as unknown[]) {
    if (!s || typeof s !== 'object') continue;
    const { camera_id, ts } = s as { camera_id?: unknown; ts?: unknown };
    if (typeof camera_id !== 'string' || typeof ts !== 'number' || !Number.isFinite(ts)) continue;
    out.push({ key: `${camera_id}@${ts}`, camera_id, ts });
  }
  return out;
}

function when(ts: number): string {
  const t = formatTs(ts);
  return ts >= EPOCH_TS ? `at ${t}` : `${t} into the run`;
}

export default function SightingModal({ incident, typeWord, onClose }: Props) {
  const { byId } = useCameras();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const downOnBackdrop = useRef(false);

  const steps = stepsOf(incident.dispatch.path);
  // Opens on the newest sighting; stays on the one the operator picked even if the path grows meanwhile.
  const [picked, setPicked] = useState<string | null>(() => steps[steps.length - 1]?.key ?? null);
  const found = steps.findIndex((s) => s.key === picked);
  const index = found >= 0 ? found : steps.length - 1;
  const step: Step | undefined = steps[index];
  const camId = step?.camera_id ?? null;
  const name = camId ? cameraName(byId[camId], camId) : '';

  // /info per camera, fetched once per opening.
  const [lookups, setLookups] = useState<Readonly<Record<string, ClipLookup>>>({});
  const lookup = camId && Object.hasOwn(lookups, camId) ? lookups[camId] : undefined;
  // What each camera's <video> reported: a problem (can't play, stalled) and the clip length once loaded.
  const [mediaProblems, setMediaProblems] = useState<Readonly<Record<string, ClipProblem>>>({});
  const [durations, setDurations] = useState<Readonly<Record<string, number>>>({});
  const mediaProblem = camId && Object.hasOwn(mediaProblems, camId) ? mediaProblems[camId] : 'none';
  const duration = camId && Object.hasOwn(durations, camId) ? durations[camId] : NaN;

  useEffect(() => {
    if (!camId || Object.hasOwn(lookups, camId)) return;
    const ctrl = new AbortController();
    void fetchClipInfo(BUS_URL, camId, ctrl.signal).then((result) => {
      if (ctrl.signal.aborted) return;
      if (result.kind !== 'ok') console.warn(`[clarity clips] ${camId}: ${result.reason}`);
      else if (!result.info.available) console.warn(`[clarity clips] ${camId}: ${result.info.reason ?? 'not available'}`);
      setLookups((prev) => ({ ...prev, [camId]: result }));
    });
    return () => ctrl.abort();
  }, [camId, lookups]);

  // Show as a modal on mount; close and hand focus back on unmount.
  useLayoutEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!d.open) d.showModal();
    closeRef.current?.focus();
    return () => {
      if (d.open) d.close();
      if (opener && opener.isConnected) opener.focus();
    };
  }, []);

  const info = lookup?.kind === 'ok' ? lookup.info : null;
  const seek = step ? clipSeek(step.ts, info?.start_ts) : 0;
  const sightingSecond = step ? clipSeek(step.ts, info?.start_ts, 0) : 0;

  const beyondEnd = clampSeek(seek, duration, sightingSecond).beyondEnd;

  const applySeek = (v: HTMLVideoElement) => {
    const { at } = clampSeek(seek, v.duration, sightingSecond);
    if (Math.abs(v.currentTime - at) > 0.05) v.currentTime = at;
  };

  // Jumping between two sightings on the same camera: same clip, new position.
  // (A different camera remounts the <video>, which seeks in onLoadedMetadata.)
  useEffect(() => {
    const v = videoRef.current;
    if (v && v.readyState >= 1) applySeek(v);
  }, [seek, sightingSecond, camId]); // applySeek only reads these

  const reportProblem = (cam: string, problem: ClipProblem) =>
    setMediaProblems((prev) => (prev[cam] === problem ? prev : { ...prev, [cam]: problem }));

  const onLoadedMetadata = (ev: SyntheticEvent<HTMLVideoElement>) => {
    const v = ev.currentTarget;
    // A clip whose video track the browser can't decode can still load (audio only, or no track): no picture.
    if (!camId) return;
    if (v.videoWidth === 0) {
      console.warn(`[clarity clips] ${camId}: loaded but has no playable video track`);
      reportProblem(camId, 'codec');
      return;
    }
    const length = v.duration;
    if (Number.isFinite(length)) setDurations((prev) => (prev[camId] === length ? prev : { ...prev, [camId]: length }));
    applySeek(v);
  };

  const onVideoError = (ev: SyntheticEvent<HTMLVideoElement>) => {
    const err = ev.currentTarget.error;
    const problem = problemFromMediaError(err?.code);
    if (problem === 'none' || !camId) return;
    console.warn(`[clarity clips] ${camId}: video error ${err?.code}: ${err?.message ?? ''}`);
    reportProblem(camId, problem);
  };

  // ---- closing and focus ----
  const onKeyDown = (ev: ReactKeyboardEvent<HTMLDialogElement>) => {
    if (ev.key === 'Escape') {
      ev.preventDefault(); // also tells the receipts log not to clear the selection
      ev.stopPropagation();
      onClose();
      return;
    }
    if (ev.key !== 'Tab') return;
    const d = dialogRef.current;
    if (!d) return;
    const items = [...d.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.getClientRects().length > 0);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (ev.shiftKey && (active === first || !d.contains(active))) {
      ev.preventDefault();
      last.focus();
    } else if (!ev.shiftKey && (active === last || !d.contains(active))) {
      ev.preventDefault();
      first.focus();
    }
  };
  const onCancel = (ev: SyntheticEvent<HTMLDialogElement>) => {
    ev.preventDefault(); // React state decides when the dialog goes away
    onClose();
  };
  // The dialog box fills the <dialog>, so a click whose target is the <dialog> itself landed on the backdrop.
  const onMouseDown = (ev: ReactMouseEvent<HTMLDialogElement>) => {
    downOnBackdrop.current = ev.target === ev.currentTarget;
  };
  const onClick = (ev: ReactMouseEvent<HTMLDialogElement>) => {
    if (ev.target === ev.currentTarget && downOnBackdrop.current) onClose();
    downOnBackdrop.current = false;
  };

  // ---- what the stage shows ----
  let problem: ClipProblem = 'none';
  let tooltip: string | undefined;
  if (lookup?.kind === 'network') { problem = 'network'; tooltip = lookup.reason; }
  else if (lookup?.kind === 'missing') { problem = 'missing'; tooltip = lookup.reason; }
  else if (info && !info.available) { problem = 'missing'; tooltip = info.reason ?? undefined; }
  else problem = mediaProblem;
  const loading = !!camId && !lookup;
  const playable = !!info && info.available && problem === 'none';

  const isLast = index === steps.length - 1;
  const which = isLast ? 'Last sighting' : `Sighting ${index + 1} of ${steps.length}`;
  const subject = typeWord ? `the ${typeWord} suspect` : 'the suspect';
  const lead = sightingSecond >= PRE_ROLL_S
    ? `The video starts ${PRE_ROLL_S} s before it.`
    : 'The video starts at the beginning of the clip.';
  const sub = step ? `${which} of ${subject}, ${when(step.ts)}. ${lead}` : 'No sightings yet.';

  return createPortal(
    <dialog
      ref={dialogRef}
      className="sm"
      style={{ borderLeftColor: `var(--chase-${incident.chase})` }}
      aria-labelledby="sm-title"
      aria-describedby="sm-sub"
      onKeyDown={onKeyDown}
      onCancel={onCancel}
      onMouseDown={onMouseDown}
      onClick={onClick}
    >
      <div className="sm-box">
        <div className="sm-head">
          <div className="sm-heading">
            <h2 id="sm-title" className="sm-title">{name || 'Last sighting'}</h2>
            <p id="sm-sub" className="sm-sub">{sub}</p>
          </div>
          <button ref={closeRef} type="button" className="sm-close" aria-label="Close video" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="sm-stage">
          {playable && camId && (
            <video
              key={camId}
              ref={videoRef}
              className="sm-video"
              src={clipUrl(BUS_URL, camId)}
              aria-label={`Video from ${name}`}
              controls
              autoPlay
              muted
              playsInline
              preload="auto"
              onLoadedMetadata={onLoadedMetadata}
              onError={onVideoError}
            />
          )}
          {loading && <p className="sm-msg" role="status">Loading video…</p>}
          {!loading && problem !== 'none' && (
            <p className="sm-msg" role="status" title={tooltip}>{CLIP_MESSAGES[problem]}</p>
          )}
        </div>
        {playable && beyondEnd && (
          <p className="sm-note" role="status">This clip ends before the sighting; showing its last frame.</p>
        )}

        {steps.length > 0 && (
          <div className="sm-steps" role="group" aria-label="Sightings, oldest first">
            {steps.map((s, i) => (
              <button
                key={s.key}
                type="button"
                className="sm-step"
                aria-pressed={i === index}
                onClick={() => setPicked(s.key)}
              >
                <span className="sm-step-name">{cameraName(byId[s.camera_id], s.camera_id)}</span>
                <span className="sm-step-time">{formatTs(s.ts)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </dialog>,
    document.body,
  );
}
