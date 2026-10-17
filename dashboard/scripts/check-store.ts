// Store + bus-connection check without a browser. Node 24 runs this .ts file directly.
//
//   npm run check:store                                   offline reducer checks only (no bus needed)
//   npm run check:store -- --live --expect-incidents 3    + connect to the bus (VITE_BUS_URL default) and wait
//   ... --confirm inc_1      also POST a Confirm for inc_1 through sendOperatorAction
//   ... --expect-reconnect   pass only if the socket dropped and came back (kill/restart the bus meanwhile)
//   ... --timeout 60         seconds to wait for the live conditions (default 60)
//
// Exit code 0 = all checks passed.

import detectionEx from '../../contracts/examples/detection.json' with { type: 'json' };
import relayEx from '../../contracts/examples/relay.json' with { type: 'json' };
import verdictEx from '../../contracts/examples/agent_verdict.json' with { type: 'json' };
import dispatchEx from '../../contracts/examples/dispatch.json' with { type: 'json' };
import cameraStatusEx from '../../contracts/examples/camera_status.json' with { type: 'json' };
import camerasEx from '../../contracts/examples/cameras.json' with { type: 'json' };
import type { BusSnapshot, ClarityEvent } from '../src/lib/types.ts';
import { CHASE_COLORS } from '../src/lib/constants.ts';
import {
  applyEvents, applySnapshot, buildOperatorAction, cameraName, computeHighlight, evidenceOf, initialState, isCrimeActivity,
  liveDetectionsByCamera, pruneRecent,
} from '../src/lib/state.ts';
import type { StoreState } from '../src/lib/state.ts';
import { getState, select, subscribe } from '../src/lib/store.ts';
import { sendOperatorAction, startBus } from '../src/lib/bus.ts';
import { BUS_WS_URL } from '../src/lib/config.ts';

declare const process: { argv: string[]; exit(code?: number): never };

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

// ---------------------------------------------------------------- offline reducer checks
function offline(): void {
  console.log('-- offline reducer checks');
  const examples = [cameraStatusEx, detectionEx, relayEx, verdictEx, dispatchEx] as unknown[];
  let s = applyEvents(initialState(), examples, true, 1000);
  check(s.events.length === 5 && s.ignored === 0, 'all 5 contract examples accepted');
  check(s.incidents.length === 1 && s.incidents[0].incident_id === 'inc_1', 'dispatch example -> one incident');
  check(s.subjectColors['subj_7'] === CHASE_COLORS[0] && s.incidents[0].chase === 1, 'first subject gets --chase-1');
  check(s.detectionSubjects['det_8f2a'] === 'subj_7', 'relay citing a detection gives it the subject');
  check(s.recent.size === 5, 'live events are marked recent');
  check(s.lastTs === 1777.0, 'lastTs = newest ts');

  const again = applyEvents(s, examples, true, 1001);
  check(again.events.length === 5, 'duplicate event_ids are dropped');

  const older = { ...(dispatchEx as object), event_id: 'dsp_old', ts: 1700, status: 'alert' };
  s = applyEvents(s, [older], true, 1002);
  check(s.incidents[0].dispatch.event_id === 'dsp_02', 'an older dispatch does not replace the latest');

  const junk = applyEvents(s, [null, 'x', { type: 'nope', event_id: 'a', ts: 1 }, { type: 'relay', ts: 1 }], true, 1003);
  check(junk.ignored === s.ignored + 4 && junk.events.length === s.events.length, 'malformed messages are ignored');

  const hl = computeHighlight('dsp_02', s.eventsById);
  check(['dsp_02', 'det_8f2a', 'rel_1c9d', 'ver_44b0'].every((id) => hl.has(id)), 'selecting a dispatch highlights its evidence');

  const op = buildOperatorAction(s, 'inc_1', 'confirm');
  check(/^op_[A-Za-z0-9_-]+$/.test(op.event_id) && op.ts === 1777.0 && op.source === 'dashboard'
    && op.schema_version === '0.1' && op.run_id === 'run_demo1', 'operator_action is schema-shaped');
  check(buildOperatorAction(s, 'inc_1', 'confirm').event_id !== op.event_id, 'operator_action ids are unique');
  s = applyEvents(s, [op], true, 1004);
  check(s.incidents[0].action?.action === 'confirm', 'operator_action marks the incident confirmed');

  const snap: BusSnapshot = { type: 'bus_snapshot', run_id: 'run_x', cameras: camerasEx as unknown as BusSnapshot['cameras'],
    events: [detectionEx, relayEx] };
  const replaced = applySnapshot({ ...s, selection: 'rel_1c9d' }, snap, 2000);
  check(replaced.events.length === 2 && replaced.incidents.length === 0 && replaced.cameras.list.length === 3,
    'bus_snapshot replaces events, incidents and cameras');
  check(replaced.recent.size === 0, 'snapshot events are never recent (no animation)');
  check(replaced.highlighted.has('det_8f2a'), 'selection survives a snapshot and re-highlights');
  const noCams = applySnapshot(replaced, { ...snap, cameras: null }, 2001);
  check(noCams.cameras.list.length === 3, 'a snapshot with cameras=null keeps the map we had');

  // live detections per camera (map pulses / alert rings)
  check(liveDetectionsByCamera(replaced.recent, replaced.eventsById).size === 0,
    'snapshot detections never pulse (no live detections after a snapshot)');
  const det = (id: string, cam: string, activity: string) => ({ ...(detectionEx as object), event_id: id, camera_id: cam, activity });
  let ls = applyEvents(replaced, [det('det_a', 'cam_01', 'fistfight')], true, 3000);
  ls = applyEvents(ls, [det('det_b', 'cam_01', 'none'), det('det_c', 'cam_02', 'none'), relayEx], true, 3001);
  const liveDets = liveDetectionsByCamera(ls.recent, ls.eventsById);
  check(liveDets.get('cam_01')?.latest.event_id === 'det_b' && liveDets.get('cam_01')?.crime?.event_id === 'det_a',
    'live detections: newest pulses, an earlier crime keeps the alert');
  check(liveDets.get('cam_02')?.crime === null && liveDets.size === 2, 'live detections: activity "none" is not a crime; non-detections skipped');
  check(isCrimeActivity('purse_snatch') && !isCrimeActivity('none') && !isCrimeActivity(undefined), 'isCrimeActivity');
  {
    const cam = camerasEx.cameras[0] as unknown as Parameters<typeof cameraName>[0] & object;
    check(cameraName({ ...cam, name: 'Front door' }) === 'Front door'
      && cameraName({ ...cam, name: '  ' }) === cam.camera_id
      && cameraName({ ...cam, name: undefined as unknown as string }) === cam.camera_id
      && cameraName(undefined, 'cam_99') === 'cam_99', 'cameraName falls back to camera_id');
  }
  const expired = pruneRecent(ls, 3000 + 6000, 6000);
  check(liveDetectionsByCamera(expired.recent, expired.eventsById).get('cam_01')?.crime === null,
    'live detections: the crime drops out with the recent window');
}

// ---------------------------------------------------------------- live checks against the bus
function summarize(s: StoreState): void {
  const byType: Record<string, number> = {};
  for (const e of s.events) byType[e.type] = (byType[e.type] ?? 0) + 1;
  console.log(`   run ${s.runId}, ${s.cameras.list.length} cameras, ${s.events.length} events`, byType);
  for (const i of s.incidents) {
    console.log(`   ${i.incident_id} ${i.subject_id} chase-${i.chase} ${i.color} ${i.dispatch.status} `
      + `(${i.dispatch.event_id}) action=${i.action?.action ?? '-'} scripted=${i.scripted}`);
  }
  console.log(`   lastTs ${s.lastTs}, recent ${s.recent.size}, snapshots ${s.snapshots}, ignored ${s.ignored}`);
}

async function live(): Promise<void> {
  const expectIncidents = Number(arg('--expect-incidents') ?? 0);
  const confirm = arg('--confirm');
  const expectReconnect = flag('--expect-reconnect');
  const timeoutS = Number(arg('--timeout') ?? 60);
  console.log(`-- live checks against ${BUS_WS_URL}`);

  let lastConn = '';
  let lastSnapshots = 0;
  let snapshotIds = new Set<string>();
  let recentAfterSnapshotOk = true;
  let sawClosed = false;
  subscribe(() => {
    const s = getState();
    const conn = `${s.connection.state}/${s.connection.retries}`;
    if (conn !== lastConn) {
      lastConn = conn;
      if (s.connection.state === 'closed') sawClosed = true;
      console.log(`   connection ${conn}${s.connection.lastError ? ` (${s.connection.lastError})` : ''}`);
    }
    if (s.snapshots !== lastSnapshots) {
      lastSnapshots = s.snapshots;
      snapshotIds = new Set(s.events.map((e) => e.event_id));
      if (s.recent.size !== 0) recentAfterSnapshotOk = false;
      console.log(`   snapshot #${s.snapshots}: ${s.events.length} events, ${s.incidents.length} incidents`);
    }
  });

  const stop = startBus();
  const done = (s: StoreState) => {
    if (s.connection.state !== 'open' || s.snapshots === 0) return false;
    if (expectReconnect && (s.snapshots < 2 || !sawClosed)) return false;
    const finished = s.incidents.filter((i) => i.dispatch.status === 'alert' || i.dispatch.status === 'resolved');
    return finished.length >= expectIncidents;
  };
  const deadline = Date.now() + timeoutS * 1000;
  while (!done(getState()) && Date.now() < deadline) await new Promise((r) => setTimeout(r, 200));
  await new Promise((r) => setTimeout(r, 300)); // let a pending batch flush

  let s = getState();
  summarize(s);
  check(done(s), `live conditions met within ${timeoutS}s (open, snapshot, ${expectIncidents} finished incidents`
    + `${expectReconnect ? ', reconnected' : ''})`);
  check(s.cameras.list.length > 0, 'cameras loaded from the snapshot');
  check(recentAfterSnapshotOk, 'right after each snapshot nothing is marked recent');
  const liveIds = [...s.recent.keys()];
  check(liveIds.every((id) => !snapshotIds.has(id)), 'only live-arrived events are recent');
  check(new Set(s.events.map((e) => e.event_id)).size === s.events.length, 'no duplicate events in the store');
  check(s.ignored === 0, 'no ignored messages');
  check(s.lastTs === Math.max(...s.events.map((e) => e.ts)), 'lastTs = newest ts');

  // latest dispatch per incident, colors in first-appearance order
  const latest: Record<string, ClarityEvent> = {};
  const subjOrder: string[] = [];
  for (const e of s.events) {
    if ('subject_id' in e && !subjOrder.includes(e.subject_id)) subjOrder.push(e.subject_id);
    if (e.type === 'dispatch' && (!latest[e.incident_id] || e.ts >= latest[e.incident_id].ts)) latest[e.incident_id] = e;
  }
  check(s.incidents.every((i) => latest[i.incident_id] === i.dispatch), 'each card holds the latest dispatch for its incident');
  check(subjOrder.every((subj, n) => s.subjectColors[subj] === CHASE_COLORS[n % CHASE_COLORS.length]),
    `subject colors follow first appearance (${subjOrder.join(', ')})`);
  check(new Set(s.incidents.map((i) => i.color)).size === s.incidents.length, 'one distinct color per incident');
  const relayDets = s.events.flatMap((e) => (e.type === 'relay' ? evidenceOf(e).filter((id) => id.startsWith('det_')) : []));
  check(relayDets.every((id) => s.detectionSubjects[id]), 'every detection cited by a relay has a subject');

  const lastDispatch = s.incidents[0]?.dispatch;
  if (lastDispatch) {
    select(lastDispatch.event_id);
    const hl = getState().highlighted;
    check(evidenceOf(lastDispatch).every((id) => hl.has(id)) && hl.has(lastDispatch.event_id),
      `select(${lastDispatch.event_id}) highlights it + ${evidenceOf(lastDispatch).length} evidence ids`);
    select(null);
    check(getState().highlighted.size === 0, 'select(null) clears the highlight');
  }

  if (confirm) {
    const res = await sendOperatorAction(confirm, 'confirm');
    console.log(`   POST operator_action ${res.event.event_id} ts=${res.event.ts} -> ${res.ok ? 'ok' : res.error}`);
    check(res.ok, `bus accepted the Confirm for ${confirm} (schema-valid in strict mode)`);
    await new Promise((r) => setTimeout(r, 800)); // WS echo
    s = getState();
    const inc = s.incidents.find((i) => i.incident_id === confirm);
    check(inc?.action?.event_id === res.event.event_id && inc.action.action === 'confirm', `${confirm} shows Confirmed`);
    check(s.events.filter((e) => e.event_id === res.event.event_id).length === 1, 'the WS echo of our own action is de-duplicated');
  }

  stop();
}

offline();
if (flag('--live')) await live();
console.log(failures.length ? `\n${failures.length} check(s) FAILED` : '\nall checks passed');
setTimeout(() => process.exit(failures.length ? 1 : 0), 50);
