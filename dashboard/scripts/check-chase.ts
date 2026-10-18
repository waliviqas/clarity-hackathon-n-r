// Map chase check without a browser: runs the real store reducers + chase derivation + geometry.
// Node 24 runs this .ts file directly.
//
//   npm run check:chase                                    synthetic checks only
//   npm run check:chase -- --events runs/fake/events.jsonl + replay a fake_scenario log through the store
//                                                          at --speed (default 2) and check every chase step
//   npm run check:chase -- --live                          + watch the bus (VITE_BUS_URL default) while
//                                                          `python -m bus.fake_scenario --speed 2` runs
//   ... --timeout 90                                       seconds to wait for the live run (default 90)
//
// Make the log with:  python -m bus.fake_scenario --out runs/fake/events.jsonl
// Exit code 0 = all checks passed.

import { readFileSync } from 'node:fs';
import placeholderSite from '../../data/sites/annex_placeholder/cameras.json' with { type: 'json' };
import type { BusSnapshot, CamerasConfig, ClarityEvent } from '../src/lib/types.ts';
import { COLORS, TIMING } from '../src/lib/constants.ts';
import { applyEvents, applySnapshot, computeHighlight, initialState, pruneRecent, runClockAt } from '../src/lib/state.ts';
import type { StoreState } from '../src/lib/state.ts';
import { deriveChase } from '../src/map/chase.ts';
import type { ChaseView } from '../src/map/chase.ts';
import { arrowShape, placeProbLabels } from '../src/map/chaseGeometry.ts';
import { ARROW } from '../src/map/sizes.ts';

declare const process: { argv: string[]; cwd(): string; exit(code?: number): never };

const failures: string[] = [];
function check(ok: boolean, what: string): void {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${what}`);
  if (!ok) failures.push(what);
}
function arg(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
}
const flag = (name: string) => process.argv.includes(name);

const site = placeholderSite as unknown as CamerasConfig;
const knownIds = new Set(site.cameras.filter((c) => c.position).map((c) => c.camera_id));
const known = (id: string) => knownIds.has(id);

function derive(s: StoreState, nowMs: number): ChaseView {
  return deriveChase({
    events: s.events, liveFrom: s.liveFrom, incidents: s.incidents, subjectColors: s.subjectColors,
    recent: s.recent, highlighted: s.highlighted, known, nowMs, runNow: runClockAt(s, nowMs),
    fallbackColor: COLORS.unassigned,
  });
}

function snapshot(events: readonly unknown[]): BusSnapshot {
  return { type: 'bus_snapshot', run_id: 'run_check', cameras: site, events: [...events] };
}

// ---------------------------------------------------------------- geometry
function geometry(): void {
  console.log('-- geometry');
  const s = arrowShape([0, 0], [200, 0]);
  check(s.head !== null && Math.abs(s.head[0][0] - (200 - ARROW.tipTrim)) < 1e-6 && Math.abs(s.line[0][0] - ARROW.startTrim) < 1e-6,
    'arrow starts outside the sender dot, tip stops just outside the receiver dot');
  check(s.head !== null && Math.abs(Math.abs(s.head[1][1] - s.head[2][1]) - ARROW.headWidth) < 1e-6, 'arrowhead has its full width');
  const o = arrowShape([0, 0], [200, 0], true);
  check(Math.abs(o.line[0][1] - ARROW.offset) < 1e-6, 'offset arrow shifts to the right of travel (east -> +y on screen)');
  check(arrowShape([0, 0], [30, 0]).head === null, 'cameras too close: line without a head');
  const blocker = { x0: 80, y0: -15, x1: 120, y1: 15 };
  const spots = placeProbLabels([{ key: 'p', a: [0, 0], b: [200, 0], w: 36, h: 19 }], { rects: [blocker], circles: [] }, null);
  const at = spots.get('p');
  check(!!at && (at[0] + 18 <= blocker.x0 || at[0] - 18 >= blocker.x1) && at[1] === 0,
    `probability label slides along its line off a camera label (x=${at?.[0].toFixed(1)})`);
  const free = placeProbLabels([{ key: 'p', a: [0, 0], b: [200, 0], w: 36, h: 19 }], { rects: [], circles: [] }, null).get('p');
  check(!!free && free[0] === 100, 'probability label sits mid-line when nothing is in the way');
}

// ---------------------------------------------------------------- synthetic edge cases
function synthetic(): void {
  console.log('-- synthetic');
  const base = { schema_version: '0.1', source: 'fake_scenario' };
  const relay = (id: string, ts: number, from: string, to: string, extra: object = {}) => ({
    ...base, type: 'relay', event_id: id, ts, from_camera: from, to_camera: to, subject_id: 'subj_a', summary: 's',
    appearance: null, direction: null, confidence: 0.9, expected_arrival_s: 20, evidence_event_ids: [], ...extra,
  });
  // A relay nobody answers expires at ts + expected_arrival_s + grace on the run clock.
  let s = applySnapshot(initialState(), snapshot([relay('rel_x', 100, 'cam_01', 'cam_02')]), 0);
  let v = derive(s, 0);
  check(v.arrows.length === 1 && v.arrows[0].state === 'active' && !v.arrows[0].animate,
    'snapshot relay: drawn, but static (no animation on reload)');
  check(v.nextChangeMs !== null && Math.abs(v.nextChangeMs - (20 + TIMING.relayGraceS) * 1000) < 1,
    'next redraw is scheduled for the moment the unanswered arrow expires');
  v = derive(s, (20 + TIMING.relayGraceS + 0.5) * 1000);
  check(v.arrows.length === 0, 'unanswered relay disappears after expected_arrival_s + grace (run clock extrapolated)');
  // Without expected_arrival_s the default applies.
  s = applySnapshot(initialState(), snapshot([relay('rel_y', 0, 'cam_01', 'cam_02', { expected_arrival_s: null })]), 0);
  check(derive(s, (TIMING.relayDefaultArrivalS + TIMING.relayGraceS - 1) * 1000).arrows.length === 1
    && derive(s, (TIMING.relayDefaultArrivalS + TIMING.relayGraceS + 1) * 1000).arrows.length === 0,
  `no expected_arrival_s: assumes ${TIMING.relayDefaultArrivalS} s`);
  // Live relay animates; opposite-direction arrows offset; unknown cameras skipped.
  s = applyEvents(s, [relay('rel_z', 1, 'cam_02', 'cam_01'), relay('rel_w', 1, 'cam_01', 'cam_99')], true, 1000);
  v = derive(s, 1000);
  const z = v.arrows.find((a) => a.relayId === 'rel_z');
  check(!!z && z.animate && z.offset, 'live relay animates; two arrows going opposite ways are offset');
  check(v.arrows.find((a) => a.relayId === 'rel_y')?.offset === true, '...both of them');
  check(!v.arrows.some((a) => a.relayId === 'rel_w'), 'relay to a camera without a map position is skipped');
  // Uncertain verdict fades the arrow and shows "uncertain".
  s = applyEvents(s, [{ ...base, type: 'agent_verdict', event_id: 'ver_u', ts: 2, agent_id: 'a', camera_id: 'cam_01',
    subject_id: 'subj_a', decision: 'uncertain', confidence: 0.5, reason: 'r', evidence_event_ids: ['rel_z'] }], true, 2000);
  v = derive(s, 2100);
  check(v.arrows.find((a) => a.relayId === 'rel_z')?.state === 'fading' && v.cameras.get('cam_01')?.badge?.kind === 'uncertain',
    'uncertain verdict: arrow fades, camera shows "uncertain"');
  check(derive(s, 2000 + TIMING.relayFadeMs + 10).arrows.every((a) => a.relayId !== 'rel_z'), 'faded arrow is removed');
}

// ---------------------------------------------------------------- fake_scenario replay
interface Step {
  wall: number;
  run: number | null;
  view: ChaseView;
  state: StoreState;
}

function loadEvents(path: string): ClarityEvent[] {
  return readFileSync(path, 'utf8').split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l) as ClarityEvent);
}

/** Feed the log into the store as if it arrived live at `speed`, deriving the map every 100 ms (wall). */
function simulate(events: readonly ClarityEvent[], speed: number): Step[] {
  let s = applySnapshot(initialState(), snapshot([]), 0);
  const steps: Step[] = [];
  const end = (Math.max(...events.map((e) => e.ts)) / speed) * 1000 + 8000;
  let i = 0;
  for (let wall = 0; wall <= end; wall += 100) {
    const due: ClarityEvent[] = [];
    while (i < events.length && (events[i].ts / speed) * 1000 <= wall) due.push(events[i++]);
    if (due.length) s = applyEvents(s, due, true, wall);
    s = pruneRecent(s, wall, TIMING.recentWindowMs);
    steps.push({ wall, run: runClockAt(s, wall), view: derive(s, wall), state: s });
  }
  return steps;
}

function scenario(path: string, speed: number): void {
  console.log(`-- fake_scenario replay (${path}, speed ${speed})`);
  const events = loadEvents(path);
  const byId = new Map(events.map((e) => [e.event_id, e]));
  const steps = simulate(events, speed);
  /** First step at or after this event arrived (+ extra wall ms). */
  const after = (id: string, extraMs = 0): Step => {
    const e = byId.get(id)!;
    const wall = (e.ts / speed) * 1000 + extraMs;
    return steps.find((st) => st.wall >= wall) ?? steps[steps.length - 1];
  };
  const last = steps[steps.length - 1];
  const colorOf = (subj: string) => last.state.subjectColors[subj];

  const incidents = [...new Set(events.filter((e) => e.type === 'dispatch').map((e) => (e as { incident_id: string }).incident_id))];
  check(incidents.length === 3, `3 incidents in the log (${incidents.join(', ')})`);
  for (const inc of incidents) {
    const n = inc.replace('inc_', '');
    const id = (k: string) => `${k}_i${n}_`;
    const r1 = byId.get(`${id('rel')}1`) as Extract<ClarityEvent, { type: 'relay' }>;
    const r2 = byId.get(`${id('rel')}2`) as Extract<ClarityEvent, { type: 'relay' }>;
    const r3 = byId.get(`${id('rel')}3`) as Extract<ClarityEvent, { type: 'relay' }>;
    if (!r1 || !r2 || !r3) { check(false, `${inc}: relays rel_i${n}_1..3 present`); continue; }
    const subj = r1.subject_id, color = colorOf(subj);
    const [crime, junction, exit, decoy] = [r1.from_camera, r1.to_camera, r2.to_camera, r3.to_camera];
    const tag = `${inc} (${subj}, ${color})`;

    let st = after(r1.event_id);
    let a = st.view.arrows.find((x) => x.relayId === r1.event_id);
    check(!!a && a.state === 'active' && a.animate && a.color === color, `${tag}: relay ${crime}->${junction} draws a travelling arrow in the chase color`);

    st = after(`${id('dsp')}1`);
    const p1 = st.view.predictions.filter((p) => p.incidentId === inc);
    check(p1.length === 1 && p1[0].from === crime && p1[0].to === junction && p1[0].probability === 1 && p1[0].covered,
      `${tag}: first dispatch predicts ${junction} (100%) on the pair the relay is travelling`);
    check(st.view.arrows.find((x) => x.relayId === r1.event_id)?.offset === true,
      `${tag}: the arrow is drawn beside the dashed prediction (offset), so both show`);
    check(st.view.cameras.get(crime)?.fill === color, `${tag}: crime camera ${crime} fills with the chase color`);

    st = after(`${id('ver')}1`);
    check(!st.view.arrows.some((x) => x.relayId === r1.event_id), `${tag}: match at ${junction} ends the arrow`);
    check(st.view.segments.some((x) => x.kind === 'extension' && x.from === crime && x.to === junction && x.eventId === `${id('ver')}1`),
      `${tag}: match extends the path ${crime}->${junction} before the next dispatch`);
    check(st.view.cameras.get(junction)?.fill === color, `${tag}: ${junction} fills after the match`);

    st = after(`${id('dsp')}2`);
    const segs2 = st.view.segments.filter((x) => x.incidentId === inc);
    check(segs2.length === 1 && segs2[0].kind === 'path' && segs2[0].eventId === `${id('ver')}1`,
      `${tag}: dispatch 2 draws path ${crime}->${junction} (click selects ${id('ver')}1)`);
    const p2 = st.view.predictions.filter((p) => p.incidentId === inc).map((p) => `${p.to}:${p.probability}:${p.covered}`).sort();
    check(p2.join(',') === [`${exit}:0.6:true`, `${decoy}:0.4:true`].sort().join(','),
      `${tag}: predictions from ${junction}: ${p2.join(', ')}`);
    a = st.view.arrows.find((x) => x.relayId === r2.event_id);
    const a3 = st.view.arrows.find((x) => x.relayId === r3.event_id);
    check(!!a && a.animate && !!a3 && a3.animate, `${tag}: both relays from ${junction} travel (${exit}, ${decoy})`);

    st = after(`${id('ver')}2`);
    check(!st.view.arrows.some((x) => x.relayId === r2.event_id)
      && st.view.segments.some((x) => x.kind === 'extension' && x.from === junction && x.to === exit),
    `${tag}: match at ${exit} turns its arrow into a path extension`);

    st = after(`${id('ver')}3`);
    a = st.view.arrows.find((x) => x.relayId === r3.event_id);
    check(a?.state === 'fading' && st.view.cameras.get(decoy)?.badge?.kind === 'no_match',
      `${tag}: no match at ${decoy}: arrow fades, "no match" badge`);
    st = after(`${id('ver')}3`, TIMING.relayFadeMs + 150);
    check(!st.view.arrows.some((x) => x.relayId === r3.event_id), `${tag}: faded arrow gone after ${TIMING.relayFadeMs} ms`);
    st = after(`${id('ver')}3`, TIMING.verdictBadgeMs - 300);
    check(st.view.cameras.get(decoy)?.badge?.kind === 'no_match', `${tag}: badge still up just before ${TIMING.verdictBadgeMs} ms`);
    st = after(`${id('ver')}3`, TIMING.verdictBadgeMs + 150);
    check(!st.view.cameras.get(decoy)?.badge, `${tag}: badge gone after ${TIMING.verdictBadgeMs} ms`);

    const segsEnd = last.view.segments.filter((x) => x.incidentId === inc);
    check(segsEnd.length === 2 && segsEnd.every((x) => x.kind === 'path' && x.color === color)
      && segsEnd[0].from === crime && segsEnd[0].to === junction && segsEnd[1].from === junction && segsEnd[1].to === exit,
    `${tag}: final path ${crime}->${junction}->${exit}, solid, chase color`);
    check(!last.view.predictions.some((p) => p.incidentId === inc), `${tag}: final dispatch has no predictions left`);
    check([crime, junction, exit].every((c) => last.view.cameras.get(c)?.fill === color) && !last.view.cameras.get(decoy)?.fill,
      `${tag}: ${crime}, ${junction}, ${exit} filled; decoy ${decoy} not`);
  }
  check(last.view.arrows.length === 0, 'no arrows left at the end');
  const colors = new Set(incidents.map((inc) => last.state.incidents.find((i) => i.incident_id === inc)?.color));
  check(colors.size === 3, `three distinct chase colors (${[...colors].join(' ')})`);
  const overlap = Math.max(...steps.map((st) => new Set(st.view.arrows.filter((a) => a.state === 'active').map((a) => a.subjectId)).size));
  const allThree = steps.some((st) => {
    const drawn = new Set([...st.view.segments, ...st.view.predictions].map((x) => x.subjectId)
      .concat(st.view.arrows.map((a) => a.subjectId)));
    return drawn.size === 3;
  });
  check(overlap >= 2 && allThree, `chases overlap: up to ${overlap} subjects with live arrows at once; all 3 on the map together`);

  // Reload: the whole log as a snapshot draws the final state, nothing animates.
  console.log('-- reload / snapshot');
  const snapEnd = applySnapshot(initialState(), snapshot(events), 0);
  const vEnd = derive(snapEnd, 0);
  check(vEnd.segments.length === 6 && vEnd.segments.every((x) => x.kind === 'path') && vEnd.arrows.length === 0
    && vEnd.predictions.length === 0 && [...vEnd.cameras.values()].every((c) => !c.badge),
  'snapshot of the finished run: 3 x 2 path segments, no arrows, no predictions, no badges');
  // Mid-run snapshot: pending relays drawn static, current predictions drawn; later live relays animate.
  const cut = 33;
  const snapMid = applySnapshot(initialState(), snapshot(events.filter((e) => e.ts <= cut)), 0);
  const vMid = derive(snapMid, 0);
  check(vMid.arrows.length > 0 && vMid.arrows.every((a) => a.state === 'active' && !a.animate),
    `snapshot at ts ${cut}: ${vMid.arrows.length} pending arrows, all static`);
  check(vMid.predictions.length > 0, `snapshot at ts ${cut}: current predictions drawn (${vMid.predictions.length})`);
  const later = events.filter((e) => e.ts > cut);
  const liveAfter = applyEvents(snapMid, later.slice(0, later.findIndex((e) => e.type === 'relay') + 1), true, 1000);
  check(derive(liveAfter, 1000).arrows.some((a) => a.animate), 'after a snapshot, a relay that arrives live animates');

  // Selection: a dispatch highlights its path and the relays it cites (even ended ones) and dims the rest.
  console.log('-- selection');
  const sel = { ...snapEnd, selection: 'dsp_i1_3', highlighted: computeHighlight('dsp_i1_3', snapEnd.eventsById) };
  const vSel = derive(sel, 0);
  check(vSel.dim && vSel.segments.filter((x) => x.highlighted).every((x) => x.incidentId === 'inc_1')
    && vSel.segments.filter((x) => x.incidentId === 'inc_1').every((x) => x.highlighted),
  'selecting a dispatch highlights its whole path and dims the other chases');
  const receipts = vSel.arrows.filter((a) => a.state === 'receipt').map((a) => a.relayId).sort();
  check(receipts.join(',') === 'rel_i1_1,rel_i1_2,rel_i1_3', `cited relays come back as static receipt arrows (${receipts.join(', ')})`);
  const hlCams = [...vSel.cameras].filter(([, c]) => c.highlighted).map(([id]) => id).sort();
  check(hlCams.join(',') === 'cam_01,cam_02,cam_03,cam_04', `cameras of the cited detections/verdicts get a ring (${hlCams.join(', ')})`);
  const selSeg = { ...snapEnd, selection: 'ver_i2_1', highlighted: computeHighlight('ver_i2_1', snapEnd.eventsById) };
  const vSeg = derive(selSeg, 0);
  check(vSeg.segments.filter((x) => x.highlighted).map((x) => `${x.from}>${x.to}`).join(',') === 'cam_05>cam_06'
    && vSeg.arrows.some((a) => a.relayId === 'rel_i2_1' && a.highlighted),
  'selecting a path segment\'s verdict highlights that hop and the relay it answered');
}

// ---------------------------------------------------------------- live, against the bus
async function live(): Promise<void> {
  const { startBus } = await import('../src/lib/bus.ts');
  const { getState, subscribe } = await import('../src/lib/store.ts');
  const { BUS_WS_URL } = await import('../src/lib/config.ts');
  const timeoutS = Number(arg('--timeout') ?? 90);
  console.log(`-- live against ${BUS_WS_URL} (start python -m bus.fake_scenario --speed 2 now)`);
  const seen = {
    animated: new Set<string>(), fading: new Set<string>(), badges: new Set<string>(),
    maxSubjectsWithArrows: 0, predictionLabels: new Set<string>(), snapshotAnimated: false,
  };
  let lastSnap = 0;
  const sample = () => {
    const s = getState();
    const v = derive(s, Date.now());
    if (s.snapshots !== lastSnap) {
      lastSnap = s.snapshots;
      if (v.arrows.some((a) => a.animate)) seen.snapshotAnimated = true;
      console.log(`   snapshot #${s.snapshots}: ${s.events.length} events, ${v.arrows.length} arrows (static), ${v.segments.length} segments`);
    }
    for (const a of v.arrows) {
      if (a.state === 'active' && a.animate) seen.animated.add(a.relayId);
      if (a.state === 'fading') seen.fading.add(a.relayId);
    }
    for (const [cam, c] of v.cameras) if (c.badge) seen.badges.add(`${cam}:${c.badge.kind}`);
    for (const p of v.predictions) seen.predictionLabels.add(`${p.from}>${p.to} ${Math.round(p.probability * 100)}%`);
    seen.maxSubjectsWithArrows = Math.max(seen.maxSubjectsWithArrows,
      new Set(v.arrows.filter((a) => a.state === 'active').map((a) => a.subjectId)).size);
    return { s, v };
  };
  const unsub = subscribe(() => { sample(); });
  const timer = setInterval(sample, 100);
  const stop = startBus();
  const finished = () => getState().incidents.filter((i) => i.dispatch.status === 'alert').length >= 3;
  const deadline = Date.now() + timeoutS * 1000;
  while (!finished() && Date.now() < deadline) await new Promise((r) => setTimeout(r, 200));
  await new Promise((r) => setTimeout(r, TIMING.relayFadeMs + 400));
  const { s, v } = sample();
  clearInterval(timer);
  unsub();
  stop();

  const relays = s.events.filter((e) => e.type === 'relay' && s.events.indexOf(e) >= s.liveFrom).map((e) => e.event_id);
  console.log(`   ${s.events.length} events, ${s.incidents.length} incidents; live relays ${relays.length}; `
    + `animated ${seen.animated.size}; faded ${[...seen.fading].join(', ') || '-'}; badges ${[...seen.badges].join(', ') || '-'}`);
  console.log(`   predictions seen: ${[...seen.predictionLabels].join(' | ')}`);
  check(finished(), `3 incidents reached "alert" within ${timeoutS}s`);
  check(!seen.snapshotAnimated, 'snapshot state never animates');
  if (relays.length === 0) {
    // Connected after the run finished (a reload): only the final state, drawn from the snapshot.
    console.log('   (no live relays: the run was already over, so this checked a reload)');
    check(seen.animated.size === 0 && seen.badges.size === 0, 'reload after the run: no travelling arrows, no badges');
  } else {
    check(relays.every((id) => seen.animated.has(id)), `every live relay drew a travelling arrow (${seen.animated.size}/${relays.length})`);
    const noMatch = s.events.filter((e) => e.type === 'agent_verdict' && e.decision === 'no_match' && s.events.indexOf(e) >= s.liveFrom);
    check(noMatch.every((e) => e.type === 'agent_verdict' && seen.badges.has(`${e.camera_id}:no_match`)),
      `every live no_match showed a badge (${noMatch.length})`);
    check(seen.fading.size >= noMatch.length, `arrows answered with no_match faded (${seen.fading.size})`);
    check(seen.maxSubjectsWithArrows >= 2, `chases overlapped (up to ${seen.maxSubjectsWithArrows} subjects with live arrows)`);
  }
  const perInc = s.incidents.map((i) => v.segments.filter((x) => x.incidentId === i.incident_id && x.kind === 'path').length);
  check(perInc.length === 3 && perInc.every((n) => n === 2) && v.arrows.length === 0 && v.predictions.length === 0,
    `final map: path segments per incident ${perInc.join('/')}, ${v.arrows.length} arrows, ${v.predictions.length} predictions`);
}

geometry();
synthetic();
const eventsPath = arg('--events');
if (eventsPath) scenario(eventsPath, Number(arg('--speed') ?? 2));
if (flag('--live')) await live();
console.log(failures.length ? `\n${failures.length} check(s) FAILED` : '\nall chase checks passed');
setTimeout(() => process.exit(failures.length ? 1 : 0), 50);
