// Operator keyboard shortcuts:
//   1-9  jump to open crime N (the Nth bar above "Handled", first-seen order), on its newest camera
//   ?    toggle the help card (Esc closes it; Esc on the map already clears the focus)
// Reads the event store only when a key is pressed (getState), so it never re-renders on new events.
import { useEffect, useState } from 'react';
import { getState } from '../lib';
import type { ClarityEvent } from '../lib';
import { requestClip } from '../lib/focus.ts';
import './Shortcuts.css';

interface Crime {
  subjectId: string;
  /** Newest camera: the last of the subject's cameras in first-seen order (the crime bar's last clip). */
  cameraId: string;
}

/** Crimes in crime-bar order, mirroring deriveFeeds in src/panels/LiveFeeds.tsx: a subject's entry is created by
 *  its first relay or match verdict; each relay's from_camera and each match verdict's camera_id is added once. */
function deriveCrimes(events: readonly ClarityEvent[]): Crime[] {
  const cameras = new Map<string, string[]>();
  const add = (subjectId: string, cameraId: string) => {
    let list = cameras.get(subjectId);
    if (!list) { list = []; cameras.set(subjectId, list); }
    if (!list.includes(cameraId)) list.push(cameraId);
  };
  for (const e of events) {
    if (e.type === 'relay') add(e.subject_id, e.from_camera);
    else if (e.type === 'agent_verdict' && e.decision === 'match') add(e.subject_id, e.camera_id);
  }
  return [...cameras].map(([subjectId, list]) => ({ subjectId, cameraId: list[list.length - 1] }));
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export default function Shortcuts() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
      if (isTyping(ev.target)) return;
      if (ev.key === 'Escape') {
        setOpen(false); // don't preventDefault: the map's Esc (clear focus) still runs
        return;
      }
      if (ev.defaultPrevented) return;
      if (ev.key === '?') {
        ev.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (ev.key >= '1' && ev.key <= '9' && ev.key.length === 1) {
        if (ev.repeat) return;
        const { events, incidents } = getState();
        // Open crimes only (the bars above "Handled"): like LiveFeeds, a subject's latest incident in the list
        // decides; it is handled once that incident has an operator_action.
        const latest = new Map(incidents.map((i) => [i.subject_id, i]));
        const open = deriveCrimes(events).filter((c) => !latest.get(c.subjectId)?.action);
        const crime = open[Number(ev.key) - 1];
        if (!crime) return;
        ev.preventDefault();
        requestClip(crime.subjectId, crime.cameraId);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="shortcuts">
      {open && (
        <div className="shortcuts-card" role="dialog" aria-label="Keyboard shortcuts">
          <div className="shortcuts-row"><span className="shortcuts-keys"><kbd>1</kbd>–<kbd>3</kbd></span><span>Jump to an open crime</span></div>
          <div className="shortcuts-row"><span className="shortcuts-keys"><kbd>Esc</kbd></span><span>Show all</span></div>
          <div className="shortcuts-row"><span className="shortcuts-keys"><kbd>Click</kbd> a camera</span><span>Its clip</span></div>
          <div className="shortcuts-row"><span className="shortcuts-keys"><kbd>?</kbd></span><span>This help</span></div>
        </div>
      )}
      <button
        type="button"
        className={`shortcuts-chip${open ? ' is-open' : ''}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <kbd>?</kbd> Shortcuts
      </button>
    </div>
  );
}
