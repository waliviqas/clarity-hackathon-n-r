// Receipts log: every bus event as one readable sentence, newest first (sentences built in receipts.ts).
// Click a line to select its event: it and every event it cites (evidence_event_ids) light up here,
// and the map and graph follow the shared selection. Click again or press Escape to clear.
// Live events: while the list is at the top it follows the newest line; once the operator scrolls
// down it holds still (the line they're reading stays put) and offers a "newer events" button.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  LABELS, cameraName, chaseVar, getState, select, useCameras, useDetectionSubjects, useEvents, useSelection,
  useSubjectColors,
} from '../lib';
import { buildRows } from './receipts.ts';
import type { ReceiptRow } from './receipts.ts';
import './ReceiptsLog.css';

/** Newest lines kept on screen (older ones stay in the store and the bus log). */
const MAX_ROWS = 400;
/** Within this many px of the top counts as "at the top" (follow new lines). */
const TOP_SLACK_PX = 4;

interface Anchor {
  key: string;
  /** Row top minus scrollTop when measured. */
  offset: number;
}

function rowStyle(row: ReceiptRow): CSSProperties | undefined {
  return row.subjectId ? { background: chaseVar(row.subjectId) } : undefined;
}

export default function ReceiptsLog() {
  const events = useEvents();
  const { byId } = useCameras();
  const detectionSubjects = useDetectionSubjects();
  useSubjectColors(); // chase dots re-render when colors are assigned
  const { selection, highlighted } = useSelection();

  const rows = useMemo(
    () => buildRows(events, {
      cameraName: (id) => cameraName(byId[id], id),
      detectionSubjects,
      labels: LABELS,
    }, MAX_ROWS),
    [events, byId, detectionSubjects],
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const anchor = useRef<Anchor | null>(null);
  const rowsRef = useRef(rows);
  /** Key of the newest line when the operator scrolled away from the top (to count newer lines). */
  const [leftTopKey, setLeftTopKey] = useState<string | null>(null);

  useEffect(() => { rowsRef.current = rows; }, [rows]);

  // Remember which line sits at the top of the view, so new lines above it don't move it.
  const measure = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop <= TOP_SLACK_PX) {
      anchor.current = null;
      setLeftTopKey(null);
      return;
    }
    for (const item of el.querySelectorAll<HTMLElement>('[data-key]')) {
      if (item.offsetTop + item.offsetHeight > el.scrollTop) {
        anchor.current = { key: item.dataset.key ?? '', offset: item.offsetTop - el.scrollTop };
        break;
      }
    }
    setLeftTopKey((k) => k ?? rowsRef.current[0]?.key ?? null);
  }, []);

  // After new lines (or a line expanding/collapsing on selection), put the anchored line back in place.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const a = anchor.current;
    if (!el || !a) return;
    const item = el.querySelector<HTMLElement>(`[data-key="${CSS.escape(a.key)}"]`);
    if (!item) return;
    const target = item.offsetTop - a.offset;
    if (Math.abs(el.scrollTop - target) > 0.5) el.scrollTop = target;
  }, [rows, selection]);

  // A selection made elsewhere (card, map arrow, graph edge): bring its line into view if it's hidden.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || !selection) return;
    const item = el.querySelector<HTMLElement>(`[data-key="${CSS.escape(selection)}"]`);
    if (!item) return;
    const top = item.offsetTop;
    const bottom = top + Math.min(item.offsetHeight, el.clientHeight - 16);
    let target: number | null = null;
    if (top < el.scrollTop) target = Math.max(0, top - 8);
    else if (bottom > el.scrollTop + el.clientHeight) target = bottom - el.clientHeight + 8;
    if (target !== null) {
      el.scrollTop = target;
      measure();
    }
  }, [selection, measure]);

  // Escape clears the selection (unless something else, e.g. a dialog, already handled the key).
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key !== 'Escape' || ev.defaultPrevented || getState().selection === null) return;
      select(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const newer = leftTopKey ? Math.max(0, rows.findIndex((r) => r.key === leftTopKey)) : 0;
  const toTop = () => {
    const el = scrollRef.current;
    if (el) el.scrollTop = 0;
    anchor.current = null;
    setLeftTopKey(null);
  };

  const cited = selection ? highlighted.size - (highlighted.has(selection) ? 1 : 0) : 0;
  const hint = selection
    ? `${cited > 0 ? `${cited} cited ${cited === 1 ? 'event' : 'events'} highlighted.` : 'Cites no other events.'} Press Esc to clear.`
    : rows.length ? 'Click a line to see what it cites.' : '';

  return (
    <div className="rc">
      <div className="rc-head">
        <h2 className="rc-title">Receipts</h2>
        <span className="rc-hint" aria-live="polite">{hint}</span>
        {newer > 0 && (
          <button type="button" className="rc-newer" onClick={toTop}>
            {newer} newer {newer === 1 ? 'event' : 'events'}
          </button>
        )}
      </div>
      <div className="rc-scroll" ref={scrollRef} onScroll={measure}>
        {rows.length === 0 ? (
          <p className="rc-empty">No events yet.</p>
        ) : (
          <ol className={`rc-list${selection ? ' has-selection' : ''}`} aria-label="Receipts, newest first">
            {rows.map((row) => {
              const isSelected = row.eventId !== null && row.eventId === selection;
              const isLinked = row.eventId !== null && highlighted.has(row.eventId);
              const cls = [
                'rc-item', `is-${row.kind}`, isSelected ? 'is-selected' : '', isLinked && !isSelected ? 'is-linked' : '',
              ].filter(Boolean).join(' ');
              const body = (
                <>
                  <span className="rc-time">{row.time}</span>
                  <span className={`rc-dot${row.crime ? ' is-crime' : ''}`} style={rowStyle(row)} aria-hidden="true" />
                  <span className="rc-text">
                    {row.parts.map((p, i) => (
                      <span key={i} className={p.tone ? `t-${p.tone}` : undefined}>{p.text}</span>
                    ))}
                  </span>
                  {isSelected && row.detail && <span className="rc-detail">{row.detail}</span>}
                </>
              );
              const title = row.detail ? `${row.text}. ${row.detail}` : row.text;
              return (
                <li key={row.key} data-key={row.key} className={cls}>
                  {row.eventId === null ? (
                    <div className="rc-row" title={title}>{body}</div>
                  ) : (
                    <button
                      type="button"
                      className="rc-row"
                      title={title}
                      aria-pressed={isSelected}
                      onClick={() => select(isSelected ? null : row.eventId)}
                    >{body}</button>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
