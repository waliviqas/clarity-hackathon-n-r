// Text check without a browser: the coordinator's words on the incident cards and in the receipts log
// (src/panels/text.ts, used by IncidentCards.tsx and receipts.ts). Node 24 runs this .ts file directly.
//
//   npm run check:text                                          formatter + receipts checks (no bus needed)
//   npm run check:text -- --events ../runs/<id>/events.jsonl    + every dispatch of a recorded run: no camera
//                                                               code or doubled name left, no "Operator review
//                                                               needed." on a card, procedure split off
//   ... --cameras ../data/sites/<site>/cameras.json             cameras for --events (default: placeholder site)
//
// Real dispatcher text (dispatcher/rules.py + guidance.py) gets tidied; scripted text (bus/fake_scenario.py)
// must come out exactly as before. Exit code 0 = all checks passed.

import { readFileSync } from 'node:fs';
import placeholderSite from '../../data/sites/annex_placeholder/cameras.json' with { type: 'json' };
import type { Camera, CamerasConfig, ClarityEvent, Dispatch } from '../src/lib/types.ts';
import { LABELS } from '../src/lib/constants.ts';
import { cameraName } from '../src/lib/state.ts';
import { buildRows } from '../src/panels/receipts.ts';
import type { ReceiptRow } from '../src/panels/receipts.ts';
import { cardText, reasonText, splitRecommendation, withCameraNames } from '../src/panels/text.ts';
import type { CameraNamer } from '../src/panels/text.ts';

declare const process: { argv: string[]; exitCode?: number };

const failures: string[] = [];
function check(ok: boolean, what: string): void {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${what}`);
  if (!ok) failures.push(what);
}
/** Exact string comparison; a failure prints both strings. */
function same(actual: string, expected: string, what: string): void {
  const ok = actual === expected;
  check(ok, ok ? what : `${what}\n        got:      ${JSON.stringify(actual)}\n        expected: ${JSON.stringify(expected)}`);
}
function arg(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function namerFor(site: CamerasConfig): CameraNamer {
  const byId: Record<string, Camera> = Object.fromEntries(site.cameras.map((c) => [c.camera_id, c]));
  return (id) => cameraName(Object.hasOwn(byId, id) ? byId[id] : undefined, id);
}
const site = placeholderSite as unknown as CamerasConfig;
const nameOf = namerFor(site);
const ctx = (namer: CameraNamer) => ({ cameraName: namer, detectionSubjects: {}, labels: LABELS });

// The two recommendations the real dispatcher sent (as in the brief; guidance.py also ends them with ".").
const REAL_1 = 'Operator review needed. Send officer to Route 1: north corner (cam_03); fistfight at Route 1: south walkway (cam_01) Procedure: separate the parties, check for injuries, request EMS if needed';
const REAL_2 = "Operator review needed. Send officer to Route 3: west sidewalk (cam_11); purse snatch at Route 3: bike rack (cam_09) Procedure: take the victim's statement and broadcast the suspect description";
const REAL_REASON = 'fistfight detected (conf 0.80); subject confirmed at 3 camera(s)';
// bus/fake_scenario.py on the placeholder site.
const SCRIPTED = [
  'Watch Route 1: west door; send an officer toward Route 1: south walkway.',
  'Suspect passed Route 1: west door; officers toward Route 1: north corner or Route 1: courtyard gate.',
  'Send officers to Route 1: north corner; check on the victim at Route 1: south walkway.',
];
const SCRIPTED_REASONS = [
  'Fistfight at Route 1: south walkway; suspect heading north.',
  'Confirmed at Route 1: west door, moving north.',
  'Seen at Route 1: south walkway, Route 1: west door, then Route 1: north corner; Route 1: courtyard gate saw no match.',
];

// ---------------------------------------------------------------- camera codes -> names
function cameraCodes(): void {
  console.log('-- camera codes -> names');
  const w = (t: unknown) => withCameraNames(t, nameOf);
  same(w('Send officer to Route 1: north corner (cam_03); fistfight at Route 1: south walkway (cam_01)'),
    'Send officer to Route 1: north corner; fistfight at Route 1: south walkway', '"Name (cam_xx)" drops the code');
  same(w('Send officers to cam_03; check on the victim at cam_01.'),
    'Send officers to Route 1: north corner; check on the victim at Route 1: south walkway.', 'bare codes become names');
  same(w('Next stop cam_03 (Route 1: north corner), then cam_04.'), 'Next stop Route 1: north corner, then Route 1: courtyard gate.',
    '"cam_xx (Name)" drops the repeated name');
  same(w('cam_03 (cam_03) next'), 'Route 1: north corner next', '"cam_xx (cam_xx)" says it once');
  same(w('route 1:  north corner (cam_03)'), 'route 1:  north corner', 'name match ignores case and spacing');
  same(w('Route 1: north corner  (cam_03)'), 'Route 1: north corner', 'spaces before the bracket go too');
  same(w('Send officer to the corner (cam_03)'), 'Send officer to the corner (Route 1: north corner)',
    'a different place before the bracket keeps the camera name in brackets');
  same(w('Route 1: west door (cam_03)'), 'Route 1: west door (Route 1: north corner)', "another camera's name keeps the bracket");
  same(w('cam_02 (Route 1: north corner)'), 'Route 1: west door (Route 1: north corner)', "a bracket naming another camera stays");
  same(w('(cam_03) is next'), '(Route 1: north corner) is next', 'a bracketed code with nothing before it is named');
  same(w('the cam_03 relay'), 'the Route 1: north corner relay', 'a code inside a sentence is named (as before)');
  same(w('male, red hoodie, blue jeans matches the relay from cam_01; arrived on time, moving north.'),
    'male, red hoodie, blue jeans matches the relay from Route 1: south walkway; arrived on time, moving north.',
    'scripted verdict reason: same as before');
  same(w('Send officer to cam_99'), 'Send officer to cam_99', 'unknown code stays as it is');
  same(w('Back gate (cam_99)'), 'Back gate (cam_99)', 'unknown code after a name stays (nothing to check it against)');
  same(w('cam_99 (cam_99)'), 'cam_99', 'unknown code repeated in brackets says it once');
  for (const s of SCRIPTED) same(w(s), s, `no codes: unchanged ("${s.slice(0, 32)}…")`);
  same(w(''), '', 'empty string');
  same(w(null), '', 'null -> empty');
  same(w(undefined), '', 'undefined -> empty');
  same(w(42), '', 'a number -> empty');
  // Whole words only: a one-letter name doesn't match the end of another word.
  const short: CameraNamer = (id) => (id === 'cam_x' ? 'A' : id);
  same(withCameraNames('Zone A (cam_x)', short), 'Zone A', 'short name at a word boundary: dropped');
  same(withCameraNames('ZoneA (cam_x)', short), 'ZoneA (A)', 'short name inside a word: kept');
  same(withCameraNames('Gate (cam_01)', () => ''), 'Gate (cam_01)', 'a namer that returns nothing falls back to the id');
}

// ---------------------------------------------------------------- recommendation: review prefix, procedure
function recommendations(): void {
  console.log('-- recommendation');
  const r1 = splitRecommendation(REAL_1, nameOf, true);
  same(r1.text, 'Send officer to Route 1: north corner; fistfight at Route 1: south walkway', 'real #1: text');
  same(r1.procedure, 'separate the parties, check for injuries, request EMS if needed', 'real #1: procedure split off');
  const r2 = splitRecommendation(REAL_2, nameOf, true);
  same(r2.text, 'Send officer to Route 3: west sidewalk; purse snatch at Route 3: bike rack', 'real #2: text');
  same(r2.procedure, "take the victim's statement and broadcast the suspect description", 'real #2: procedure split off');
  same(splitRecommendation(`${REAL_1}.`, nameOf, true).procedure, 'separate the parties, check for injuries, request EMS if needed.',
    'procedure with its full stop (as guidance.py writes it)');
  const kept = splitRecommendation(REAL_1, nameOf);
  same(kept.text, 'Operator review needed. Send officer to Route 1: north corner; fistfight at Route 1: south walkway',
    'without dropReview the prefix stays');
  const stab = splitRecommendation('Send officer to Route 1: west door (cam_02); stabbing at Route 1: south walkway (cam_01) Procedure: armed suspect, approach with backup; request EMS for the victim.', nameOf, true);
  same(stab.text, 'Send officer to Route 1: west door; stabbing at Route 1: south walkway', 'rules alert (no prefix): text');
  same(stab.procedure, 'armed suspect, approach with backup; request EMS for the victim.', 'rules alert: procedure keeps its ";"');
  same(splitRecommendation('Operator review needed: send officers to cam_03', nameOf, true).text,
    'Send officers to Route 1: north corner', '"Operator review needed:" variant, next word capitalized');
  same(splitRecommendation('Operator review needed for cam_03', nameOf, true).text, 'Operator review needed for Route 1: north corner',
    'not a separate sentence: kept');
  same(splitRecommendation('Operator review needed.', nameOf, true).text, 'Operator review needed.', 'prefix alone: kept (card never blank)');
  const onlyPrefix = splitRecommendation('Operator review needed. Procedure: take a statement.', nameOf, true);
  check(onlyPrefix.text === 'Operator review needed.' && onlyPrefix.procedure === 'take a statement.', 'prefix + procedure only: prefix kept');
  const noProc = splitRecommendation('Send officers to cam_03 (Route 1: north corner).', nameOf, true);
  check(noProc.text === 'Send officers to Route 1: north corner.' && noProc.procedure === '', 'no procedure: procedure is empty');
  const lead = splitRecommendation('Procedure: separate the parties.', nameOf, true);
  check(lead.text === 'Procedure: separate the parties.' && lead.procedure === '', 'nothing before "Procedure:": not split');
  const two = splitRecommendation('Send officers to cam_03. Procedure: a. Procedure: b.', nameOf, true);
  check(two.text === 'Send officers to Route 1: north corner. Procedure: a.' && two.procedure === 'b.', 'two procedures: the trailing one splits');
  same(splitRecommendation('Follow the usual procedure: call it in.', nameOf, true).procedure, '', 'lowercase "procedure:" inside a sentence: not split');
  for (const s of SCRIPTED) {
    const r = splitRecommendation(s, nameOf, true);
    check(r.text === s && r.procedure === '', `scripted: unchanged ("${s.slice(0, 32)}…")`);
  }
  const empty = splitRecommendation('', nameOf, true);
  check(empty.text === '' && empty.procedure === '', 'empty string');
  const junk = splitRecommendation(null, nameOf, true);
  check(junk.text === '' && junk.procedure === '', 'null -> empty');
}

// ---------------------------------------------------------------- reason
function reasons(): void {
  console.log('-- reason');
  const r = (t: unknown) => reasonText(t, nameOf);
  same(r(REAL_REASON), 'Fistfight detected (80% confidence); subject confirmed at 3 cameras', 'real: capitalized, %, plural');
  same(r('purse snatch detected (conf 0.80); subject confirmed at 1 camera(s)'),
    'Purse snatch detected (80% confidence); subject confirmed at 1 camera', 'one camera: singular');
  same(r('stabbing detected (conf 1.00); subject confirmed at 0 camera(s)'),
    'Stabbing detected (100% confidence); subject confirmed at 0 cameras', 'conf 1.00 -> 100%, zero -> plural');
  same(r('seen at cam_01 (Route 1: south walkway), confidence 0.8.'), 'Seen at Route 1: south walkway, 80% confidence.',
    'codes named; "confidence 0.8" -> 80%; full stop kept');
  same(r('conf: 0.65 at cam_09'), '65% confidence at Route 3: bike rack', '"conf: 0.65"');
  same(r('conf 1.5 is not a probability'), 'Conf 1.5 is not a probability', 'not a 0-1 value: left alone');
  same(r('Confirmed at Route 1: west door, moving north.'), 'Confirmed at Route 1: west door, moving north.',
    '"Confirmed" is not "conf"');
  for (const s of SCRIPTED_REASONS) same(r(s), s, `scripted: unchanged ("${s.slice(0, 32)}…")`);
  same(r('  '), '', 'blank -> empty');
  same(r(undefined), '', 'undefined -> empty');
}

// ---------------------------------------------------------------- card text
const BASE = { schema_version: '0.1', run_id: 'run_check', source: 'dispatcher' } as const;
function dispatch(id: string, ts: number, fields: Partial<Dispatch>): Dispatch {
  return {
    ...BASE, type: 'dispatch', event_id: id, ts, incident_id: 'inc_r1', subject_id: 'subj_r1', incident_type: 'fistfight',
    subject_appearance: 'male, red hoodie, blue jeans', status: 'alert', priority: 'medium',
    path: [{ camera_id: 'cam_01', ts: 0, event_id: 'det_r1' }], predicted_next: [], recommendation: '', reason: '',
    evidence_event_ids: [], requires_human_confirm: true, ...fields,
  };
}

function cards(): void {
  console.log('-- card text');
  const c1 = cardText(dispatch('dsp_r1', 56, { recommendation: REAL_1, reason: REAL_REASON }), nameOf);
  same(c1.reco, 'Send officer to Route 1: north corner; fistfight at Route 1: south walkway.', 'real #1: recommendation');
  same(c1.procedure, 'separate the parties, check for injuries, request EMS if needed.', 'real #1: procedure line');
  same(c1.meta, 'Medium priority. Suspect: male, red hoodie, blue jeans. Fistfight detected (80% confidence); subject confirmed at 3 cameras.',
    'real #1: meta line');
  same(c1.title, 'Send officer to Route 1: north corner; fistfight at Route 1: south walkway. Procedure: separate the parties, check for injuries, request EMS if needed.',
    'real #1: hover title has the procedure');
  const c2 = cardText(dispatch('dsp_r2', 86, {
    recommendation: REAL_2, priority: 'low', subject_appearance: 'male, black cap, grey backpack',
    reason: 'purse snatch detected (conf 0.80); subject confirmed at 3 camera(s)',
  }), nameOf);
  same(c2.reco, 'Send officer to Route 3: west sidewalk; purse snatch at Route 3: bike rack.', 'real #2: recommendation');
  same(c2.procedure, "take the victim's statement and broadcast the suspect description.", 'real #2: procedure line');
  same(c2.meta, 'Low priority. Suspect: male, black cap, grey backpack. Purse snatch detected (80% confidence); subject confirmed at 3 cameras.',
    'real #2: meta line');

  // Scripted: exactly the words the cards showed before text.ts (recommendation as sent, meta as before).
  const look = 'male, red hoodie, blue jeans';
  SCRIPTED.forEach((reco, i) => {
    const c = cardText(dispatch(`dsp_s${i}`, i, { recommendation: reco, reason: SCRIPTED_REASONS[i], subject_appearance: look }), nameOf);
    check(c.reco === reco && c.procedure === '' && c.title === reco
      && c.meta === `Medium priority. Suspect: ${look}. ${SCRIPTED_REASONS[i]}`, `scripted card #${i + 1}: unchanged`);
  });

  const blank = cardText(dispatch('dsp_b', 1, { recommendation: '', reason: '', subject_appearance: null }), nameOf);
  check(blank.reco === '' && blank.procedure === '' && blank.title === '' && blank.meta === 'Medium priority.', 'empty strings: nothing invented');
  const junk = cardText({ recommendation: 7, reason: null, priority: 'constructor', subject_appearance: 3 } as unknown as Dispatch, nameOf);
  check(junk.reco === '' && junk.meta === '' && junk.procedure === '', 'junk field values: empty, no throw');
  const plain = cardText(dispatch('dsp_p', 1, { recommendation: 'Send officers to cam_03', reason: 'subject seen at cam_03' }), nameOf);
  check(plain.reco === 'Send officers to Route 1: north corner.' && plain.title === plain.reco
    && plain.meta.endsWith('Subject seen at Route 1: north corner.'), 'no procedure: no procedure line, title = recommendation');
}

// ---------------------------------------------------------------- receipts rows
function rowsByKey(events: readonly unknown[], namer: CameraNamer = nameOf): Map<string, ReceiptRow> {
  return new Map(buildRows(events as readonly ClarityEvent[], ctx(namer)).map((r) => [r.key, r]));
}

function receipts(): void {
  console.log('-- receipts');
  // Scripted incident 1, as bus/fake_scenario.py publishes it (rows as they read before text.ts).
  const s = { schema_version: '0.1', run_id: 'run_fake', source: 'fake_scenario' };
  const look = 'male, red hoodie, blue jeans';
  const scripted = [
    { ...s, type: 'detection', event_id: 'det_i1_1', ts: 0, camera_id: 'cam_01', track_id: 'trk_cam_01_1', label: 'person',
      confidence: 0.9, bbox: null, activity: 'fistfight', activity_confidence: 0.8, direction: 'north', appearance: look },
    { ...s, type: 'relay', event_id: 'rel_i1_1', ts: 1, from_camera: 'cam_01', to_camera: 'cam_02', subject_id: 'subj_1',
      summary: 'Punched another person repeatedly near the corner, then walked off fast.', direction: 'north', activity: 'fistfight',
      confidence: 0.85, expected_arrival_s: 30, evidence_event_ids: ['det_i1_1'], appearance: look },
    { ...dispatch('dsp_i1_1', 2, { recommendation: SCRIPTED[0], reason: SCRIPTED_REASONS[0], status: 'tracking', requires_human_confirm: false }),
      ...s, incident_id: 'inc_1', subject_id: 'subj_1' },
    { ...s, type: 'agent_verdict', event_id: 'ver_i1_1', ts: 31, agent_id: 'agent_cam_02', camera_id: 'cam_02', subject_id: 'subj_1',
      decision: 'match', confidence: 0.88, reason: `${look} matches the relay from cam_01; arrived on time, moving north.`,
      evidence_event_ids: ['rel_i1_1', 'det_i1_2'] },
    { ...dispatch('dsp_i1_3', 66, { recommendation: SCRIPTED[2], reason: SCRIPTED_REASONS[2] }), ...s, incident_id: 'inc_1', subject_id: 'subj_1' },
  ];
  const golden: [string, string, string][] = [
    ['dsp_i1_3', 'Coordinator needs your decision: send officers to Route 1: north corner; check on the victim at Route 1: south walkway',
      'Medium priority. Seen at Route 1: south walkway, Route 1: west door, then Route 1: north corner; Route 1: courtyard gate saw no match.'],
    ['ver_i1_1', 'Route 1: west door confirmed the red-hoodie suspect',
      'male, red hoodie, blue jeans matches the relay from Route 1: south walkway; arrived on time, moving north.'],
    ['dsp_i1_1', 'Coordinator: watch Route 1: west door; send an officer toward Route 1: south walkway',
      'Medium priority. Fistfight at Route 1: south walkway; suspect heading north.'],
    ['rel_i1_1', 'Route 1: south walkway asked Route 1: west door to watch for the red-hoodie suspect',
      'Punched another person repeatedly near the corner, then walked off fast. Heading north. Expected there in about 30 s.'],
    ['det_i1_1', 'Route 1: south walkway saw a fistfight (male, red hoodie, blue jeans)', 'Male, red hoodie, blue jeans. Heading north.'],
  ];
  const sr = rowsByKey(scripted);
  for (const [key, text, detail] of golden) {
    const row = sr.get(key);
    check(!!row && row.text === text && row.detail === detail,
      `scripted ${key}: reads as before${row && (row.text !== text || row.detail !== detail) ? `\n        got: ${JSON.stringify(row.text)} / ${JSON.stringify(row.detail)}` : ''}`);
  }

  // Real dispatcher: a tracking update (asks for review) and the alert that needs a decision.
  const real = [
    dispatch('dsp_t1_01', 1, {
      status: 'tracking', recommendation: REAL_1.replace('north corner (cam_03)', 'west door (cam_02)'),
      reason: 'fistfight detected (conf 0.80); subject confirmed at 1 camera(s)',
    }),
    dispatch('dsp_t1_18', 86, { recommendation: REAL_2, priority: 'low', reason: 'purse snatch detected (conf 0.80); subject confirmed at 3 camera(s)',
      incident_id: 'inc_r2', subject_id: 'subj_r2', incident_type: 'purse_snatch' }),
    { ...BASE, type: 'operator_action', event_id: 'op_1', ts: 90, incident_id: 'inc_r2', action: 'confirm', note: null },
  ];
  const rr = rowsByKey(real);
  same(rr.get('dsp_t1_18')?.text ?? '', 'Coordinator needs your decision: send officer to Route 3: west sidewalk; purse snatch at Route 3: bike rack',
    'real alert: no doubled names, no review prefix, no procedure in the line');
  same(rr.get('dsp_t1_18')?.detail ?? '',
    "Low priority. Purse snatch detected (80% confidence); subject confirmed at 3 cameras. Procedure: take the victim's statement and broadcast the suspect description.",
    'real alert: reason tidied, procedure in the detail');
  same(rr.get('dsp_t1_01')?.text ?? '', 'Coordinator: operator review needed. Send officer to Route 1: west door; fistfight at Route 1: south walkway',
    'real tracking: the review request stays (the line does not say "needs your decision")');
  same(rr.get('dsp_t1_01')?.detail ?? '',
    'Medium priority. Fistfight detected (80% confidence); subject confirmed at 1 camera. Procedure: separate the parties, check for injuries, request EMS if needed.',
    'real tracking: detail');
  same(rr.get('op_1')?.text ?? '', 'Operator confirmed the purse snatch at Route 1: south walkway', 'operator_action line unchanged');

  // Cameras the dashboard doesn't know: codes stay, nothing is doubled.
  const unknown = rowsByKey([dispatch('dsp_u', 5, { recommendation: 'Send officer to Back gate (cam_99); fistfight at cam_98', reason: '' })]);
  same(unknown.get('dsp_u')?.text ?? '', 'Coordinator needs your decision: send officer to Back gate (cam_99); fistfight at cam_98',
    'unknown cameras: codes kept as sent');
  const empty = rowsByKey([dispatch('dsp_e', 5, { recommendation: '', reason: '' })]);
  same(empty.get('dsp_e')?.text ?? '', 'Coordinator updated the fistfight incident', 'empty recommendation: fallback line');
  same(empty.get('dsp_e')?.detail ?? '', 'Medium priority.', 'empty reason: priority only');
}

// ---------------------------------------------------------------- a recorded run (optional)
function recorded(path: string, camerasPath: string | undefined): void {
  console.log(`-- recorded run ${path}`);
  const cams = camerasPath ? JSON.parse(readFileSync(camerasPath, 'utf8')) as CamerasConfig : site;
  const namer = namerFor(cams);
  // Only cameras with a real name: an unnamed camera is shown by its code on purpose.
  const named = cams.cameras.filter((c) => namer(c.camera_id) !== c.camera_id);
  const known = named.map((c) => c.camera_id);
  const names = named.map((c) => namer(c.camera_id));
  const events = readFileSync(path, 'utf8').split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l) as ClarityEvent);
  const dispatches = events.filter((e): e is Dispatch => e.type === 'dispatch');
  const rows = rowsByKey(events, namer);
  const doubled = (t: string) => names.some((n) => t.includes(`${n} (${n})`));
  const codeLeft = (t: string) => known.some((id) => new RegExp(`\\b${id}\\b`).test(t));
  const bad: string[] = [];
  const latest = new Map<string, Dispatch>();
  for (const d of dispatches) {
    latest.set(d.incident_id, d);
    const c = cardText(d, namer);
    const row = rows.get(d.event_id);
    const all = [c.reco, c.procedure, c.meta, row?.text ?? '', row?.detail ?? ''];
    if (all.some(doubled)) bad.push(`${d.event_id}: a camera name doubled`);
    if (all.some(codeLeft)) bad.push(`${d.event_id}: a known camera code left`);
    if (/^operator review needed\s*[.!:]\s*\S/i.test(c.reco)) bad.push(`${d.event_id}: card starts with the review prefix`);
    if (/\sProcedure:/.test(c.reco)) bad.push(`${d.event_id}: procedure left in the card recommendation`);
    if (/\(conf\s|\d\s*\w+\(s\)/i.test(c.meta)) bad.push(`${d.event_id}: raw "conf" or "(s)" in the meta line`);
  }
  check(dispatches.length > 0, `${dispatches.length} dispatches in the log`);
  check(bad.length === 0, `every dispatch reads cleanly on cards and receipts${bad.length ? `\n        ${bad.slice(0, 10).join('\n        ')}` : ''}`);
  for (const [inc, d] of latest) {
    const c = cardText(d, namer);
    console.log(`   ${inc} [${d.status}${d.requires_human_confirm ? ', asks' : ''}]  ${c.reco}`);
    if (c.procedure) console.log(`        Procedure: ${c.procedure}`);
    console.log(`        ${c.meta}`);
  }
}

cameraCodes();
recommendations();
reasons();
cards();
receipts();
const eventsPath = arg('--events');
if (eventsPath) recorded(eventsPath, arg('--cameras'));
console.log(failures.length ? `\n${failures.length} check(s) FAILED` : '\nall text checks passed');
process.exitCode = failures.length ? 1 : 0;
