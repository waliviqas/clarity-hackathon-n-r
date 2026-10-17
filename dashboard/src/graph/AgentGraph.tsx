// Agent graph: the camera agents (grouped by route = connected cameras, see layout.ts) + the coordinator;
// edges are messages.
//   relay          -> that camera-camera edge draws on in the subject's chase color (TIMING.edgeFlashMs)
//   agent_verdict  -> the camera-coordinator line flashes: match solid color, no_match grey dashed, uncertain amber dotted
//   dispatch       -> the coordinator pulses
//   detection      -> the camera node lights (alert ring if the activity is a crime)
// Only events that arrived live animate (useRecent / useLiveDetections). A bus_snapshot draws the final state
// with no animation: edges keep the color of their latest message, nodes the subject last seen there.
// Clicking a node, edge or the coordinator selects its latest event (receipts highlight what it cites).

import { useMemo, useState } from 'react';
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react';
import {
  CHASE_COLORS, COLORS, LABELS, TIMING, isCrimeActivity, useCameras, useCameraStatus, useDetectionSubjects,
  useEvents, useEventsById, useIncidents, useLiveDetections, useRecent, useSelection, useSubjectColors,
} from '../lib';
import type { Activity, ClarityEvent, VerdictDecision } from '../lib';
import { buildLayout, edgePath, NODE_R } from './layout.ts';
import type { GraphLayout } from './layout.ts';
import { deriveGraphState, groupSubject } from './derive.ts';
import './AgentGraph.css';

/** "Uncertain" is amber in the spec; always paired with a dotted line and a "?" so it never relies on color. */
const UNCERTAIN = CHASE_COLORS[0];
const DECISION_WORDS: Record<VerdictDecision, string> = {
  match: 'match', no_match: 'no match', uncertain: 'uncertain',
};

type Fx =
  | { id: string; at: number; kind: 'relay'; d: string; color: string }
  | { id: string; at: number; kind: 'verdict'; d: string; color: string; decision: VerdictDecision }
  | { id: string; at: number; kind: 'dispatch'; color: string };

export default function AgentGraph() {
  const { list } = useCameras();
  const status = useCameraStatus();
  const events = useEvents();
  const byId = useEventsById();
  const recent = useRecent();
  const liveDetections = useLiveDetections();
  const incidents = useIncidents();
  const colors = useSubjectColors();
  const detectionSubjects = useDetectionSubjects();
  const { selection, highlighted, select } = useSelection();

  const layout = useMemo(() => buildLayout(list), [list]);
  const g = useMemo(() => deriveGraphState(events, layout, detectionSubjects), [events, layout, detectionSubjects]);
  const color = (subject: string | null | undefined) => (subject && colors[subject]) || COLORS.unassigned;
  const fx = useMemo(() => liveEffects(recent, byId, layout, colors), [recent, byId, layout, colors]);

  const hasSelection = selection !== null;
  const hl = (ids: readonly string[] | undefined) => !!ids && ids.some((id) => highlighted.has(id));
  const focus = (active: boolean, ids: readonly string[] | undefined) =>
    hasSelection && active ? (hl(ids) ? ' is-hl' : ' is-dim') : '';

  /** Props that make an SVG group a button selecting `eventId` (toggle). Idle elements aren't clickable. */
  const clickable = (eventId: string | undefined, label: string) => {
    if (!eventId) return {};
    const act = () => select(selection === eventId ? null : eventId);
    return {
      role: 'button',
      tabIndex: 0,
      'aria-label': label,
      'aria-pressed': selection === eventId,
      onClick: act,
      onKeyDown: (ev: KeyboardEvent) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); act(); }
      },
    };
  };
  const nameOf = (cam: string) => layout.byId[cam]?.name ?? cam;

  if (layout.nodes.length === 0) {
    return (
      <div className="ag">
        <Header />
        <p className="ag-empty">Waiting for the camera list from the event bus.</p>
      </div>
    );
  }

  const { coordinator: co } = layout;
  const lastDispatch = g.dispatch;
  // The coordinator's outline takes the subject's color while its newest dispatch is still recent (a few
  // seconds), then goes back to neutral: with reduced motion this is the visible change instead of the pulse.
  const recentDispatch = newestRecentDispatch(recent, byId);

  return (
    <div className="ag">
      <Header />
      <div className="ag-body">
        <svg
          className="ag-svg"
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          preserveAspectRatio="xMidYMid meet"
          role="group"
          aria-label={`Agent graph: ${layout.nodes.length} camera agents and the ${LABELS.coordinator}`}
        >
          {/* route titles, with the incident type in the chase color once known */}
          {layout.groups.map((grp, i) => {
            const subject = groupSubject(g, layout, i);
            const inc = subject ? incidents.find((x) => x.subject_id === subject) : undefined;
            return (
              <text key={`grp-${i}`} className="ag-route" x={grp.x} y={22}>
                <tspan>{grp.title}</tspan>
                {inc && <tspan dx={8} fill={inc.color}>{activityWord(inc.dispatch.incident_type)}</tspan>}
              </text>
            );
          })}

          {/* camera -> coordinator lines (bottom layer) */}
          {layout.nodes.map((n) => {
            const v = g.verdictByCam.get(n.camera_id);
            const ids = g.verdictIdsByCam.get(n.camera_id);
            const d = layout.spokes[n.camera_id];
            const stroke = !v ? 'var(--rule)' : v.decision === 'match' ? color(v.subject_id)
              : v.decision === 'uncertain' ? UNCERTAIN : 'var(--muted)';
            const label = v
              ? `${n.name} told the ${LABELS.coordinator}: ${DECISION_WORDS[v.decision] ?? v.decision}`
              : `${n.name} to ${LABELS.coordinator}`;
            return (
              <g key={`sp-${n.camera_id}`}
                className={`ag-spoke${v ? ` is-${v.decision} ag-click` : ''}${focus(!!v, ids)}`}
                {...clickable(v?.event_id, label)}>
                <title>{v ? `${label}. ${v.reason ?? ''}` : label}</title>
                {v && <path className="ag-hit" d={d} />}
                <path className="ag-line" d={d} stroke={stroke} />
                {v?.decision === 'no_match' && <NoMatchMark at={layout.marks[n.camera_id]} />}
                {v?.decision === 'uncertain' && <UncertainMark at={layout.marks[n.camera_id]} />}
              </g>
            );
          })}

          {/* camera -> camera edges (idle from cameras.json neighbors; colored by their latest relay) */}
          {[...layout.edges, ...g.extraEdges].map((key) => {
            const [a, b] = key.split('|');
            const relay = g.relayByEdge.get(key);
            const ids = g.relayIdsByEdge.get(key);
            const d = edgePath(layout, a, b);
            if (!d) return null;
            const stroke = relay ? color(relay.subject_id) : 'var(--rule)';
            const label = relay
              ? `${nameOf(relay.from_camera)} passed the description to ${nameOf(relay.to_camera)}`
              : `${nameOf(a)} and ${nameOf(b)}`;
            return (
              <g key={`ed-${key}`}
                className={`ag-edge${relay ? ' is-on ag-click' : ''}${focus(!!relay, ids)}`}
                {...clickable(relay?.event_id, label)}>
                <title>{relay ? `${label}. ${relay.summary ?? ''}` : label}</title>
                {relay && <path className="ag-hit" d={d} />}
                <path className="ag-line" d={d} stroke={stroke} />
              </g>
            );
          })}

          {/* live flashes (only events that arrived live, never snapshot history) */}
          {fx.map((f) => {
            if (f.kind === 'relay' || (f.kind === 'verdict' && f.decision === 'match')) {
              return <FxPath key={f.id} at={f.at} d={f.d} stroke={f.color} className="ag-fx-draw" draw />;
            }
            if (f.kind === 'verdict') {
              return <FxPath key={f.id} at={f.at} d={f.d} stroke={f.color} className={`ag-fx-blink is-${f.decision}`} />;
            }
            return null;
          })}

          {/* camera agents */}
          {layout.nodes.map((n) => {
            const cam = n.camera_id;
            const health = status[cam]?.status;
            const v = g.verdictByCam.get(cam);
            const seen = g.subjectByCam.get(cam);
            const ids = g.nodeIdsByCam.get(cam);
            const latest = g.nodeEventByCam.get(cam);
            const fill = v?.decision === 'match' ? color(v.subject_id) : 'var(--ink)';
            const stroke = seen ? color(seen.subject) : g.seenCams.has(cam) ? 'var(--text)' : 'var(--muted)';
            const live = liveDetections.get(cam);
            const liveAt = live ? recent.get(live.latest.event_id) : undefined;
            const cls = `ag-node${health && health !== 'online' ? ` is-${health}` : ''}${latest ? ' ag-click' : ''}`;
            const statusWord = health ? LABELS.cameraHealth[health] ?? health : null;
            return (
              <g key={`nd-${cam}`} className={cls}
                {...clickable(latest?.event_id, `${n.name}: latest ${latest ? eventWord(latest) : 'event'}`)}>
                <title>{`${n.name} (${cam})${statusWord ? `, ${statusWord.toLowerCase()}` : ''}`}</title>
                {latest && <circle className="ag-node-hit" cx={n.x} cy={n.y} r={NODE_R + 7} />}
                {hl(ids) && <circle className="ag-halo" cx={n.x} cy={n.y} r={NODE_R + 6} />}
                {g.crimeByCam.has(cam) && <circle className="ag-ring" cx={n.x} cy={n.y} r={NODE_R + 3.5} />}
                <circle className="ag-node-dot" cx={n.x} cy={n.y} r={NODE_R} fill={fill} stroke={stroke} />
                {live && liveAt !== undefined && Date.now() - liveAt < TIMING.detectionPulseMs && (
                  <FxNodeLight key={live.latest.event_id} at={liveAt} x={n.x} y={n.y}
                    crime={isCrimeActivity(live.latest.activity)} />
                )}
                <text className="ag-label" x={n.x} y={n.y - NODE_R - 8}>{n.label}</text>
              </g>
            );
          })}

          {/* coordinator */}
          <g className={`ag-coord${lastDispatch ? ' ag-click' : ''}`}
            {...clickable(lastDispatch?.event_id, `${LABELS.coordinator}: latest recommendation`)}>
            <title>{lastDispatch ? `${LABELS.coordinator}: ${lastDispatch.recommendation}` : LABELS.coordinator}</title>
            {hl(g.dispatchIds) && (
              <rect className="ag-halo" x={co.x - co.w / 2 - 5} y={co.y - co.h / 2 - 5}
                width={co.w + 10} height={co.h + 10} rx={7} />
            )}
            <rect className="ag-coord-box" x={co.x - co.w / 2} y={co.y - co.h / 2} width={co.w} height={co.h} rx={4}
              stroke={recentDispatch ? color(recentDispatch.subject_id) : 'var(--muted)'} />
            {fx.map((f) => f.kind === 'dispatch' && (
              <FxRect key={f.id} at={f.at} x={co.x - co.w / 2} y={co.y - co.h / 2} w={co.w} h={co.h} stroke={f.color} />
            ))}
            <text className="ag-coord-label" x={co.x} y={co.y + 5}>{LABELS.coordinator}</text>
          </g>
        </svg>
      </div>
    </div>
  );
}

function Header() {
  return (
    <div className="ag-head">
      <h2 className="ag-title">Agent graph</h2>
      <ul className="ag-legend" aria-label="Legend">
        <LegendItem label="Match">
          <line x1={2} y1={6} x2={24} y2={6} stroke="var(--text)" strokeWidth={2.5} strokeLinecap="round" />
        </LegendItem>
        <LegendItem label="No match">
          <line x1={1} y1={6} x2={25} y2={6} stroke="var(--muted)" strokeWidth={2} strokeDasharray="5 4" />
        </LegendItem>
        <LegendItem label="Uncertain">
          <line x1={2} y1={6} x2={24} y2={6} stroke={UNCERTAIN} strokeWidth={2.5} strokeDasharray="0.5 4.5"
            strokeLinecap="round" />
        </LegendItem>
      </ul>
    </div>
  );
}

function LegendItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <li>
      <svg width={26} height={12} viewBox="0 0 26 12" aria-hidden="true">{children}</svg>
      {label}
    </li>
  );
}

function NoMatchMark({ at }: { at: { x: number; y: number } | undefined }) {
  if (!at) return null;
  return (
    <g className="ag-mark" transform={`translate(${at.x} ${at.y})`}>
      <circle r={6.5} className="ag-mark-bg" />
      <path d="M -3.2 -3.2 L 3.2 3.2 M 3.2 -3.2 L -3.2 3.2" stroke="var(--muted)" strokeWidth={1.8} strokeLinecap="round" />
    </g>
  );
}

function UncertainMark({ at }: { at: { x: number; y: number } | undefined }) {
  if (!at) return null;
  return (
    <g className="ag-mark" transform={`translate(${at.x} ${at.y})`}>
      <circle r={7} className="ag-mark-bg" />
      <text className="ag-mark-q" y={4.5} fill={UNCERTAIN}>?</text>
    </g>
  );
}

// ---------- live effects ----------

/** Live events still inside their flash window, newest last. Snapshot events are never in `recent`. */
function liveEffects(
  recent: ReadonlyMap<string, number>, byId: ReadonlyMap<string, ClarityEvent>, layout: GraphLayout,
  colors: Readonly<Record<string, string>>,
): Fx[] {
  const now = Date.now();
  const out: Fx[] = [];
  const color = (s: string | undefined) => (s && colors[s]) || COLORS.unassigned;
  for (const [id, at] of recent) {
    if (now - at >= TIMING.edgeFlashMs) continue;
    const e = byId.get(id);
    if (!e) continue;
    if (e.type === 'relay') {
      const d = edgePath(layout, e.from_camera, e.to_camera);
      if (d && e.from_camera !== e.to_camera) out.push({ id, at, kind: 'relay', d, color: color(e.subject_id) });
    } else if (e.type === 'agent_verdict') {
      const d = layout.spokes[e.camera_id];
      if (!d) continue;
      const c = e.decision === 'match' ? color(e.subject_id) : e.decision === 'uncertain' ? UNCERTAIN : COLORS.muted;
      out.push({ id, at, kind: 'verdict', d, color: c, decision: e.decision });
    } else if (e.type === 'dispatch') {
      out.push({ id, at, kind: 'dispatch', color: color(e.subject_id) });
    }
  }
  return out;
}

/**
 * Negative animation-delay so a flash that mounts late (e.g. the panel re-rendered mid-flash) stays in
 * sync with when the event arrived. Captured once on mount: changing it later would jump the animation.
 */
function useAnimationTiming(at: number, ms: number): CSSProperties {
  const [delay] = useState(() => Math.min(0, at - Date.now()));
  return { animationDuration: `${ms}ms`, animationDelay: `${delay}ms` };
}

function FxPath({ at, d, stroke, className, draw }: {
  at: number; d: string; stroke: string; className: string; draw?: boolean;
}) {
  const style = useAnimationTiming(at, TIMING.edgeFlashMs);
  return <path className={`ag-fx ${className}`} d={d} stroke={stroke} pathLength={draw ? 1 : undefined} style={style} />;
}

function FxRect({ at, x, y, w, h, stroke }: { at: number; x: number; y: number; w: number; h: number; stroke: string }) {
  const style = useAnimationTiming(at, TIMING.edgeFlashMs);
  return <rect className="ag-fx ag-fx-pulse" x={x} y={y} width={w} height={h} rx={4} stroke={stroke} style={style} />;
}

function FxNodeLight({ at, x, y, crime }: { at: number; x: number; y: number; crime: boolean }) {
  const style = useAnimationTiming(at, TIMING.detectionPulseMs);
  const c = crime ? 'var(--alert)' : 'var(--text)';
  return (
    <g>
      <circle className="ag-fx ag-fx-light" cx={x} cy={y} r={NODE_R} fill={c} style={style} />
      <circle className="ag-fx ag-fx-ring" cx={x} cy={y} r={NODE_R} stroke={c} style={style} />
    </g>
  );
}

/** Newest dispatch that arrived live in the recent window, or null (never one from a snapshot). */
function newestRecentDispatch(recent: ReadonlyMap<string, number>, byId: ReadonlyMap<string, ClarityEvent>) {
  let found: Extract<ClarityEvent, { type: 'dispatch' }> | null = null;
  for (const id of recent.keys()) { // insertion = arrival order
    const e = byId.get(id);
    if (e?.type === 'dispatch') found = e;
  }
  return found;
}

// ---------- words ----------

function activityWord(a: Activity | string): string {
  return (LABELS.activity as Record<string, string>)[a] ?? String(a).replace(/_/g, ' ');
}

function eventWord(e: ClarityEvent): string {
  if (e.type === 'agent_verdict') return `verdict (${DECISION_WORDS[e.decision] ?? e.decision})`;
  if (e.type === 'detection') return isCrimeActivity(e.activity) ? `detection (${activityWord(e.activity).toLowerCase()})` : 'detection';
  return e.type.replace(/_/g, ' ');
}
