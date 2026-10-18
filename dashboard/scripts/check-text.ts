// Text check without a browser: the coordinator's words on the incident cards and in the receipts log
// (src/panels/text.ts, used by IncidentCards.tsx and receipts.ts). Node 24 runs this .ts file directly.
//
//   npm run check:text                                          formatter + receipts checks (no bus needed)
//   npm run check:text -- --events ../runs/<id>/events.jsonl    + every dispatch of a recorded run: no camera
//                                                               code or doubled name left, no "Operator review
//                                                               needed." on a card, procedure split off, no card
//                                                               recommendation that repeats its title, every
//                                                               rules.py reason in its short card form
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
import {
  cardHeading, cardText, incidentTypeLabel, reasonText, splitRecommendation, withCameraNames, withoutRepeatedTitle,
} from '../src/panels/text.ts';
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
// dispatcher/rules.py template() (branch Michael, cdac7b5) writes its reason with two f-strings (lines 185, 191):
//   seen = f"{what} detected (conf {conf:.2f})" if conf is not None else f"{what} detected"
//   "reason": f"{seen}; subject confirmed at {len(cam_path)} camera(s)"
// with what = the activity, "_" -> " ". Before cdac7b5 an unknown confidence was written as "conf 0.00".
function rulesReason(activity: string, conf: number | null, cameras: number): string {
  const what = activity.replace(/_/g, ' ');
  const seen = conf !== null ? `${what} detected (conf ${conf.toFixed(2)})` : `${what} detected`;
  return `${seen}; subject confirmed at ${cameras} camera(s)`;
}
const OLD_UNKNOWN_REASON = 'fistfight detected (conf 0.00); subject confirmed at 3 camera(s)';
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
  same(w('cam_01-cam_02'), 'Route 1: south walkway – Route 1: west door', 'hyphen-joined codes: each named, joined by a spaced en dash');
  same(w('Path: cam_01-cam_02-cam_03.'), 'Path: Route 1: south walkway – Route 1: west door – Route 1: north corner.',
    'three hyphen-joined codes');
  same(w('between (cam_01-cam_02)'), 'between (Route 1: south walkway – Route 1: west door)', 'hyphen-joined codes in brackets');
  same(w('cam_01-cam_99'), 'Route 1: south walkway – cam_99', 'hyphen-joined, one unknown: the known one named');
  same(w('cam_98-cam_99'), 'cam_98-cam_99', 'hyphen-joined, all unknown: unchanged');
  same(w('cam_01-02 and cam_03-'), 'cam_01-02 and Route 1: north corner-', '"cam_01-02" is not two codes: left alone');
  same(w('cam_03.'), 'Route 1: north corner.', 'code before a full stop');
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
  check(two.text === 'Send officers to Route 1: north corner.' && two.procedure === 'a. Procedure: b.',
    'two procedures: split at the first (nothing procedural left in the recommendation)');
  const modelProc = splitRecommendation(`Send officer to cam_03. Procedure: approach from the north. ${'Procedure: separate the parties.'}`, nameOf, true);
  check(modelProc.text === 'Send officer to Route 1: north corner.' && modelProc.procedure === 'approach from the north. Procedure: separate the parties.',
    "model's own procedure + guidance: split at the first");
  const leadTwo = splitRecommendation('Procedure: a. Procedure: b.', nameOf, true);
  check(leadTwo.text === 'Procedure: a. Procedure: b.' && leadTwo.procedure === '', 'starts with "Procedure:": not split (never blank)');
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
  // rulesReason gives exactly the strings rules.py sends.
  same(rulesReason('fistfight', 0.8, 3), REAL_REASON, 'rules.py f-string, confidence known: the reason the dispatcher sent');
  same(rulesReason('purse_snatch', null, 1), 'purse snatch detected; subject confirmed at 1 camera(s)', 'rules.py f-string, no confidence');
  same(rulesReason('fistfight', 0, 3), OLD_UNKNOWN_REASON, 'rules.py f-string, a real zero: same text as the old unknown');
  same(r(rulesReason('fistfight', null, 3)), 'Fistfight detected; subject confirmed at 3 cameras', 'no confidence: none invented, plural');
  same(r(rulesReason('purse_snatch', null, 1)), 'Purse snatch detected; subject confirmed at 1 camera', 'no confidence, one camera: singular');
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
  console.log('-- card title');
  const h = cardHeading({ incident_type: 'fistfight', path: [{ camera_id: 'cam_01', ts: 0, event_id: 'det_h' }] }, nameOf);
  check(h.type === 'Fistfight' && h.where === 'Route 1: south walkway' && h.title === 'Fistfight at Route 1: south walkway',
    'title: type at the first path camera');
  same(cardHeading({ incident_type: 'purse_snatch', path: [{ camera_id: 'cam_99', ts: 0, event_id: 'det_h' }] }, nameOf).title,
    'Purse snatch at cam_99', 'unknown camera: its code');
  const noPath = cardHeading({ incident_type: 'stabbing', path: [] }, nameOf);
  check(noPath.title === 'Stabbing' && noPath.where === null, 'no path: just the type');
  same(incidentTypeLabel('car_theft'), 'Car theft', 'unknown type: sentence case');
  check(incidentTypeLabel('none') === 'Incident' && incidentTypeLabel(null) === 'Incident' && incidentTypeLabel('constructor') === 'Constructor',
    'none / null / "constructor": no inherited label');
  same(cardHeading({ incident_type: 7, path: 'x' } as unknown as Dispatch, nameOf).title, '7', 'junk fields: no throw');

  console.log('-- card text');
  // The dispatcher's two alerts, each on an incident that started where the crime was (the card title's place).
  const c1 = cardText(dispatch('dsp_r1', 56, { recommendation: REAL_1, reason: REAL_REASON }), nameOf);
  same(c1.heading.title, 'Fistfight at Route 1: south walkway', 'real #1: card title');
  same(c1.reco, 'Send officer to Route 1: north corner.', 'real #1: recommendation without the clause that repeats the title');
  same(c1.procedure, 'separate the parties, check for injuries, request EMS if needed.', 'real #1: procedure line');
  same(c1.meta, 'Medium priority. Fistfight (80% confidence), seen at 3 cameras. Suspect: male, red hoodie, blue jeans.',
    'real #1: meta line, what was detected first');
  same(c1.title, 'Send officer to Route 1: north corner. Procedure: separate the parties, check for injuries, request EMS if needed.',
    'real #1: hover title has the procedure');
  const c2 = cardText(dispatch('dsp_r2', 86, {
    recommendation: REAL_2, priority: 'low', subject_appearance: 'male, black cap, grey backpack', incident_type: 'purse_snatch',
    path: [{ camera_id: 'cam_09', ts: 70, event_id: 'det_r2' }], reason: 'purse snatch detected (conf 0.80); subject confirmed at 3 camera(s)',
  }), nameOf);
  same(c2.heading.title, 'Purse snatch at Route 3: bike rack', 'real #2: card title');
  same(c2.reco, 'Send officer to Route 3: west sidewalk.', 'real #2: recommendation');
  same(c2.procedure, "take the victim's statement and broadcast the suspect description.", 'real #2: procedure line');
  same(c2.meta, 'Low priority. Purse snatch (80% confidence), seen at 3 cameras. Suspect: male, black cap, grey backpack.',
    'real #2: meta line');

  // The trailing clause goes only when it repeats this card's own title.
  const reco = (fields: Partial<Dispatch>) =>
    cardText(dispatch('dsp_x', 1, { recommendation: REAL_1, reason: REAL_REASON, ...fields }), nameOf).reco;
  const KEPT = 'Send officer to Route 1: north corner; fistfight at Route 1: south walkway.';
  same(reco({ path: [{ camera_id: 'cam_02', ts: 0, event_id: 'det_x' }] }), KEPT, 'title at another camera: clause kept (it says where the fight was)');
  same(reco({ path: [] }), KEPT, 'no path (title is just "Fistfight"): clause kept');
  same(reco({ incident_type: 'stabbing' }), KEPT, 'another incident type in the title: clause kept');
  same(reco({ recommendation: 'Send officer to cam_03;  FISTFIGHT at route 1:  south walkway.' }), 'Send officer to Route 1: north corner.',
    'case, spacing and a full stop aside: dropped');
  same(reco({ recommendation: 'Send officer to cam_03; fistfight at cam_01; check on the victim' }),
    'Send officer to Route 1: north corner; fistfight at Route 1: south walkway; check on the victim.', 'not the last clause: kept');
  same(reco({ recommendation: 'fistfight at cam_01' }), 'fistfight at Route 1: south walkway.', 'nothing before it: kept (never blank)');
  same(reco({ recommendation: 'Send officer to cam_03; fistfight at cam_01 and cam_02' }),
    'Send officer to Route 1: north corner; fistfight at Route 1: south walkway and Route 1: west door.', 'says more than the title: kept');
  same(withoutRepeatedTitle('A; b', ''), 'A; b', 'no title: unchanged');

  // Meta line: the dispatcher's reason first (shortened), the suspect last.
  const meta = (fields: Partial<Dispatch>) =>
    cardText(dispatch('dsp_m', 1, { recommendation: REAL_1, reason: REAL_REASON, ...fields }), nameOf).meta;
  same(meta({ reason: 'fistfight detected (conf 0.80); subject confirmed at 1 camera(s)' }),
    'Medium priority. Fistfight (80% confidence), seen at 1 camera. Suspect: male, red hoodie, blue jeans.', 'one camera: singular');
  same(meta({ subject_appearance: null }), 'Medium priority. Fistfight (80% confidence), seen at 3 cameras.', 'no suspect description');
  same(meta({ reason: '' }), 'Medium priority. Suspect: male, red hoodie, blue jeans.', 'no reason');
  same(meta({ reason: 'fistfight detected (conf 0.80) near cam_01' }),
    'Medium priority. Fistfight detected (80% confidence) near Route 1: south walkway. Suspect: male, red hoodie, blue jeans.',
    'only the exact dispatcher phrase is shortened');
  same(meta({ priority: 'high', reason: 'Two cameras saw cam_01 (Route 1: south walkway) fight; heading north' }),
    'High priority. Two cameras saw Route 1: south walkway fight; heading north. Suspect: male, red hoodie, blue jeans.',
    "a model's own reason: also first, only codes tidied");
  // rules.py's reason with and without a confidence (cdac7b5): every card gets the short form, with the
  // confidence only when the dispatcher sent one.
  const LOOK = ' Suspect: male, red hoodie, blue jeans.';
  same(meta({ reason: rulesReason('fistfight', 0.8, 3) }), `Medium priority. Fistfight (80% confidence), seen at 3 cameras.${LOOK}`,
    'rules.py, confidence known: as before');
  same(meta({ reason: rulesReason('fistfight', 0.8, 1) }), `Medium priority. Fistfight (80% confidence), seen at 1 camera.${LOOK}`,
    'rules.py, confidence known, 1 camera: singular');
  same(meta({ reason: rulesReason('fistfight', null, 3) }), `Medium priority. Fistfight, seen at 3 cameras.${LOOK}`,
    'rules.py, no confidence: short form, no confidence text');
  same(meta({ reason: rulesReason('fistfight', null, 1) }), `Medium priority. Fistfight, seen at 1 camera.${LOOK}`,
    'rules.py, no confidence, 1 camera: singular');
  same(meta({ priority: 'low', incident_type: 'purse_snatch', subject_appearance: null, reason: rulesReason('purse_snatch', null, 2) }),
    'Low priority. Purse snatch, seen at 2 cameras.', 'rules.py, no confidence, two-word activity, no suspect');
  same(meta({ reason: OLD_UNKNOWN_REASON }), `Medium priority. Fistfight (0% confidence), seen at 3 cameras.${LOOK}`,
    'old form "conf 0.00": short form, shown as sent (rules.py now writes 0.00 only for a real zero)');
  const noConf = ['stabbing', 'fistfight', 'purse_snatch', 'car_theft'].flatMap((a) =>
    [1, 2, 3].map((n) => meta({ reason: rulesReason(a, null, n) })));
  const unshortened = noConf.filter((m) => !/, seen at \d cameras?\./.test(m) || /%|conf|detected|\(\s*\)/i.test(m));
  check(unshortened.length === 0, `rules.py, no confidence, 4 activities x 1-3 cameras: short form, no "%", "conf", "detected" or "()"${
    unshortened.length ? `\n        got: ${JSON.stringify(unshortened[0])}` : ''}`);
  same(meta({ reason: 'fistfight detected near cam_01; subject confirmed at 2 camera(s)' }),
    `Medium priority. Fistfight detected near Route 1: south walkway; subject confirmed at 2 cameras.${LOOK}`,
    'no confidence: still only the exact dispatcher phrase is shortened');
  same(meta({ reason: 'fistfight detected; heading north' }), `Medium priority. Fistfight detected; heading north.${LOOK}`,
    '"detected;" without "subject confirmed at": not shortened');
  check(!(c1.meta + c2.meta).includes('·') && /^[A-Z]/.test(c1.meta), 'meta: sentence case, no middle-dot separators');

  // Scripted (bus/fake_scenario.py, source "fake_scenario"): all nine dispatches read exactly as before:
  // title, recommendation and meta (priority, suspect, reason).
  const INC = [
    { type: 'fistfight', start: 'cam_01', priority: 'medium', look: 'male, red hoodie, blue jeans', title: 'Fistfight at Route 1: south walkway' },
    { type: 'purse_snatch', start: 'cam_05', priority: 'low', look: 'female, yellow jacket, black pants', title: 'Purse snatch at Route 2: plaza steps' },
    { type: 'purse_snatch', start: 'cam_09', priority: 'low', look: 'male, black cap, grey backpack', title: 'Purse snatch at Route 3: bike rack' },
  ] as const;
  const SCRIPTED_RUN: [number, string, string][] = [
    [0, SCRIPTED[0], SCRIPTED_REASONS[0]], [0, SCRIPTED[1], SCRIPTED_REASONS[1]], [0, SCRIPTED[2], SCRIPTED_REASONS[2]],
    [1, 'Watch Route 2: side entrance; send an officer toward Route 2: plaza steps.', 'Purse snatch at Route 2: plaza steps; suspect heading east.'],
    [1, 'Suspect passed Route 2: side entrance; officers toward Route 2: east sidewalk or Route 2: loading dock.',
      'Confirmed at Route 2: side entrance, moving east.'],
    [1, 'Send officers to Route 2: east sidewalk; check on the victim at Route 2: plaza steps.',
      'Seen at Route 2: plaza steps, Route 2: side entrance, then Route 2: east sidewalk; Route 2: loading dock saw no match.'],
    [2, 'Watch Route 3: crosswalk; send an officer toward Route 3: bike rack.', 'Purse snatch at Route 3: bike rack; suspect heading west.'],
    [2, 'Suspect passed Route 3: crosswalk; officers toward Route 3: west sidewalk or Route 3: parking lot.',
      'Confirmed at Route 3: crosswalk, moving west.'],
    [2, 'Send officers to Route 3: west sidewalk; check on the victim at Route 3: bike rack.',
      'Seen at Route 3: bike rack, Route 3: crosswalk, then Route 3: west sidewalk; Route 3: parking lot saw no match.'],
  ];
  SCRIPTED_RUN.forEach(([n, r, why], i) => {
    const inc = INC[n];
    const c = cardText(dispatch(`dsp_s${i}`, i, {
      source: 'fake_scenario', incident_type: inc.type, priority: inc.priority, subject_appearance: inc.look, recommendation: r, reason: why,
      path: [{ camera_id: inc.start, ts: 0, event_id: `det_s${i}` }],
    }), nameOf);
    const before = `${inc.priority === 'low' ? 'Low' : 'Medium'} priority. Suspect: ${inc.look}. ${why}`;
    const ok = c.heading.title === inc.title && c.reco === r && c.procedure === '' && c.title === r && c.meta === before;
    check(ok, `scripted dispatch #${i + 1}: unchanged${ok ? '' : `\n        got: ${JSON.stringify([c.heading.title, c.reco, c.meta])}`}`);
  });

  const blank = cardText(dispatch('dsp_b', 1, { recommendation: '', reason: '', subject_appearance: null }), nameOf);
  check(blank.reco === '' && blank.procedure === '' && blank.title === '' && blank.meta === 'Medium priority.', 'empty strings: nothing invented');
  const junk = cardText({ recommendation: 7, reason: null, priority: 'constructor', subject_appearance: 3 } as unknown as Dispatch, nameOf);
  check(junk.reco === '' && junk.meta === '' && junk.procedure === '' && junk.heading.title === 'Incident', 'junk field values: empty, no throw');
  const plain = cardText(dispatch('dsp_p', 1, { recommendation: 'Send officers to cam_03', reason: 'subject seen at cam_03' }), nameOf);
  check(plain.reco === 'Send officers to Route 1: north corner.' && plain.title === plain.reco
    && plain.meta === 'Medium priority. Subject seen at Route 1: north corner. Suspect: male, red hoodie, blue jeans.',
    'no procedure: no procedure line, title = recommendation');
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
      incident_id: 'inc_r2', subject_id: 'subj_r2', incident_type: 'purse_snatch', path: [{ camera_id: 'cam_09', ts: 70, event_id: 'det_r2' }] }),
    { ...BASE, type: 'operator_action', event_id: 'op_1', ts: 90, incident_id: 'inc_r2', action: 'confirm', note: null },
  ];
  const rr = rowsByKey(real);
  same(rr.get('dsp_t1_18')?.text ?? '', 'Coordinator needs your decision: send officer to Route 3: west sidewalk; purse snatch at Route 3: bike rack',
    'real alert: no doubled names, no review prefix, no procedure in the line; keeps the clause the card drops');
  same(cardText(real[1] as Dispatch, nameOf).reco, 'Send officer to Route 3: west sidewalk.', '... while the same dispatch on its card drops it');
  same(rr.get('dsp_t1_18')?.detail ?? '',
    "Low priority. Purse snatch detected (80% confidence); subject confirmed at 3 cameras. Procedure: take the victim's statement and broadcast the suspect description.",
    'real alert: reason tidied, procedure in the detail');
  same(rr.get('dsp_t1_01')?.text ?? '', 'Coordinator: operator review needed. Send officer to Route 1: west door; fistfight at Route 1: south walkway',
    'real tracking: the review request stays (the line does not say "needs your decision")');
  same(rr.get('dsp_t1_01')?.detail ?? '',
    'Medium priority. Fistfight detected (80% confidence); subject confirmed at 1 camera. Procedure: separate the parties, check for injuries, request EMS if needed.',
    'real tracking: detail');
  same(rr.get('op_1')?.text ?? '', 'Operator confirmed the purse snatch at Route 3: bike rack', 'operator_action line unchanged');
  const noConf = rowsByKey([dispatch('dsp_n', 5, { recommendation: REAL_1, reason: rulesReason('fistfight', null, 3) })]);
  same(noConf.get('dsp_n')?.detail ?? '',
    'Medium priority. Fistfight detected; subject confirmed at 3 cameras. Procedure: separate the parties, check for injuries, request EMS if needed.',
    'receipt detail, rules.py with no confidence: the full reason, no confidence invented');
  const hyphen = rowsByKey([dispatch('dsp_h', 5, { recommendation: 'Watch cam_02-cam_03. Procedure: a. Procedure: b.', reason: '' })]);
  same(hyphen.get('dsp_h')?.text ?? '', 'Coordinator needs your decision: watch Route 1: west door – Route 1: north corner',
    'receipt: hyphen-joined codes named, split at the first "Procedure:"');
  same(hyphen.get('dsp_h')?.detail ?? '', 'Medium priority. Procedure: a. Procedure: b.', 'receipt detail: the whole procedure');

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
    if (typeof d.reason === 'string' && /\sdetected(?: \(conf [01]\.\d\d\))?; subject confirmed at \d+ camera\(s\)/i.test(d.reason)
      && !/, seen at \d+ cameras?\b/.test(c.meta)) bad.push(`${d.event_id}: rules.py reason not in its short form on the card`);
    if (c.reco.toLowerCase().replace(/[.\s]+$/, '').endsWith(`; ${c.heading.title.toLowerCase()}`)) {
      bad.push(`${d.event_id}: card recommendation repeats its title`);
    }
  }
  check(dispatches.length > 0, `${dispatches.length} dispatches in the log`);
  check(bad.length === 0, `every dispatch reads cleanly on cards and receipts${bad.length ? `\n        ${bad.slice(0, 10).join('\n        ')}` : ''}`);
  for (const [inc, d] of latest) {
    const c = cardText(d, namer);
    console.log(`   ${inc} [${d.status}${d.requires_human_confirm ? ', asks' : ''}]  ${c.heading.title}`);
    console.log(`        ${c.reco}`);
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
