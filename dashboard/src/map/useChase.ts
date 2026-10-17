import { useEffect, useMemo, useState } from 'react';
import {
  COLORS, runClock, useEvents, useIncidents, useLastTs, useLiveFrom, useRecent, useSelection, useSubjectColors,
} from '../lib';
import { deriveChase } from './chase.ts';
import type { ChaseView } from './chase.ts';

/**
 * What the chases look like right now (see chase.ts), recomputed when the store changes and again
 * at the moment something ends on its own (an arrow's time runs out, a fade or a badge finishes).
 * `known` = cameras that have a map position.
 */
export function useChase(known: ReadonlySet<string>): ChaseView {
  const events = useEvents();
  const liveFrom = useLiveFrom();
  const incidents = useIncidents();
  const subjectColors = useSubjectColors();
  const recent = useRecent();
  const { highlighted } = useSelection();
  const lastTs = useLastTs();
  const [tick, setTick] = useState(0);

  const view = useMemo(() => {
    const nowMs = Date.now();
    return deriveChase({
      events, liveFrom, incidents, subjectColors, recent, highlighted,
      known: (id) => known.has(id), nowMs, runNow: runClock(nowMs), fallbackColor: COLORS.unassigned,
    });
    // lastTs and tick stand for the clock: recompute when the run clock jumps or a timer fires.
  }, [events, liveFrom, incidents, subjectColors, recent, highlighted, known, lastTs, tick]);

  useEffect(() => {
    if (view.nextChangeMs === null) return;
    const wait = Math.max(30, view.nextChangeMs - Date.now() + 20);
    const timer = setTimeout(() => setTick((t) => t + 1), wait);
    return () => clearTimeout(timer);
  }, [view]);

  return view;
}
