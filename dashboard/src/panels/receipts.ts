// Receipts log rows: every bus event as one readable sentence (pure, no React, no runtime imports,
// so plain Node can run it against a real bus log). ReceiptsLog.tsx renders the rows.
//
//   12.0 s  Route 1: west door confirmed the red-hoodie suspect
//   41.0 s  Route 1: courtyard gate saw no match for the red-hoodie suspect
//    2.0 s  Coordinator: watch Route 1: west door; send an officer toward Route 1: south walkway
//    0.0 s  12 cameras online
//
// Cameras are named only by their cameras.json name (never a role). The dispatcher is "coordinator".
// camera_status is noise: repeats are dropped and consecutive reports collapse into one muted line.

import type { ClarityEvent, Dispatch } from '../lib';

export interface Part {
  text: string;
  /** strong = camera names / "Coordinator"; alert = crime words, "needs your decision". */
  tone?: 'strong' | 'alert';
}

export interface ReceiptRow {
  /** React key / scroll anchor: the event_id, or "cst:<first event_id>" for a camera-status line. */
  key: string;
  /** Event this row selects; null for a collapsed camera-status line (not clickable). */
  eventId: string | null;
  ts: number;
  /** Run-clock time as shown, e.g. "12.0 s" (live epoch ts shows as a wall-clock time). */
  time: string;
  /** Chase color key (relay / verdict / dispatch / cited detection / operator_action via its incident). */
  subjectId: string | null;
  kind: 'event' | 'status';
  /** Detection of a crime that no relay cites yet (shown with an alert ring instead of a chase dot). */
  crime: boolean;
  parts: Part[];
  /** The sentence as plain text (title, screen readers). */
  text: string;
  /** Extra sentences shown when the row is selected ('' if there is nothing more to say). */
  detail: string;
}

export interface ReceiptLabels {
  coordinator: string;
  activity: Readonly<Record<string, string>>;
  cameraHealth: Readonly<Record<string, string>>;
}

export interface ReceiptContext {
  /** On-screen camera name (cameras.json name, or the id when it has none). */
  cameraName(cameraId: string): string;
  /** detection event_id -> subject_id, once a relay or a match verdict cites the detection. */
  detectionSubjects: Readonly<Record<string, string>>;
  labels: ReceiptLabels;
}

/** Above this a ts is unix epoch seconds (live run), not run-clock seconds from a replay. */
const EPOCH_TS = 1e9;

export function formatTs(ts: number): string {
  if (!Number.isFinite(ts)) return '';
  if (ts >= EPOCH_TS) {
    return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }
  return `${ts.toFixed(1)} s`;
}

function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function str(x: unknown): string {
  return typeof x === 'string' ? x.trim() : '';
}

/** Ends a fragment with a full stop unless it already ends a sentence. */
function sentence(s: string): string {
  const t = s.trim();
  return !t || /[.!?]$/.test(t) ? t : `${t}.`;
}

function noFullStop(s: string): string {
  return s.trim().replace(/\.+$/, '');
}

// Words that don't tell suspects apart, skipped when picking a short descriptor.
const GENERIC = new Set([
  'male', 'female', 'man', 'woman', 'person', 'adult', 'child', 'kid', 'teen', 'teenager', 'boy', 'girl',
  'unknown', 'young', 'older', 'elderly', 'someone', 'individual', 'tall', 'short', 'slim', 'thin', 'heavy',
  'stocky', 'medium', 'average', 'build', 'height',
]);

// Leading filler stripped from a description part ("a man in a red hoodie" -> "red hoodie").
const FILLER = new Set(['a', 'an', 'the', 'in', 'wearing', 'wears', 'with', 'dressed', 'who', 'is', 'and']);

/**
 * "male, red hoodie, blue jeans" -> "the red-hoodie suspect". Picks the first comma part with two
 * or more non-generic words (else the first non-generic part), cut at "and" / "with". Up to three
 * words are hyphenated; longer reads "the suspect (<phrase>)"; nothing usable -> "the suspect".
 */
export function suspectPhrase(appearance: string | null | undefined): string {
  const cleaned = str(appearance).split(/[,;]/)
    .map((p) => {
      const words = noFullStop(p).toLowerCase().split(/\s+/).filter(Boolean);
      while (words.length && (FILLER.has(words[0]) || GENERIC.has(words[0]))) words.shift();
      const cut = words.findIndex((w) => w === 'and' || w === 'with' || w === 'carrying' || w === 'holding');
      return cut > 0 ? words.slice(0, cut) : words;
    })
    .filter((words) => words.length > 0 && !words.every((w) => GENERIC.has(w)));
  const pick = cleaned.find((words) => words.length >= 2) ?? cleaned[0];
  if (!pick) return 'the suspect';
  if (pick.length <= 3) return `the ${pick.join('-')} suspect`;
  return `the suspect (${pick.join(' ')})`;
}

/** Free text from agents may name cameras by id ("the cam_03 relay"): show their names instead. */
function withCameraNames(text: string, ctx: ReceiptContext): string {
  return text.replace(/\bcam_[A-Za-z0-9_-]+/g, (id) => ctx.cameraName(id) || id);
}

function activityWord(a: unknown, ctx: ReceiptContext): string {
  const key = str(a);
  const known = ctx.labels.activity[key];
  return (known ?? key.replace(/_/g, ' ')).toLowerCase();
}

const DIRECTIONS = new Set(['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest']);

function headingSentence(direction: unknown): string {
  return typeof direction === 'string' && DIRECTIONS.has(direction) ? `Heading ${direction}.` : '';
}

function join(...sentences: string[]): string {
  return sentences.map((s) => s.trim()).filter(Boolean).join(' ');
}

/** Coordinator recommendations start with a verb ("Watch …"): lowercase it after "Coordinator: ". */
function recommendationText(reco: string, ctx: ReceiptContext, cameraNames: readonly string[]): string {
  const t = noFullStop(withCameraNames(reco, ctx));
  if (!t) return t;
  const first = t.split(/\s/, 1)[0];
  if (!/^[A-Z][a-z]+$/.test(first) || cameraNames.some((n) => n && t.startsWith(n))) return t;
  return t.charAt(0).toLowerCase() + t.slice(1);
}

interface StatusGroup {
  firstId: string;
  ts: number;
  /** camera_id -> { status now, status before this group (undefined = first report) } */
  cams: Map<string, { status: string; prev: string | undefined }>;
}

const HEALTH_ORDER = ['online', 'degraded', 'offline'];

function statusRow(g: StatusGroup, ctx: ReceiptContext): ReceiptRow {
  const word = (s: string) => (ctx.labels.cameraHealth[s] ?? s).toLowerCase();
  let parts: Part[];
  if (g.cams.size === 1) {
    const [camId, { status, prev }] = [...g.cams][0];
    const phrase = prev === undefined ? `is ${word(status)}`
      : status === 'online' ? 'is back online'
        : status === 'offline' ? 'went offline'
          : `is ${word(status)}`;
    parts = [{ text: ctx.cameraName(camId), tone: 'strong' }, { text: ` ${phrase}` }];
  } else {
    const counts = new Map<string, number>();
    for (const { status } of g.cams.values()) counts.set(status, (counts.get(status) ?? 0) + 1);
    const order = [...HEALTH_ORDER.filter((s) => counts.has(s)), ...[...counts.keys()].filter((s) => !HEALTH_ORDER.includes(s))];
    const text = order.map((s, i) => {
      const n = counts.get(s)!;
      return i === 0 ? `${n} ${n === 1 ? 'camera' : 'cameras'} ${word(s)}` : `${n} ${word(s)}`;
    }).join(', ');
    parts = [{ text }];
  }
  return {
    key: `cst:${g.firstId}`,
    eventId: null,
    ts: g.ts,
    time: formatTs(g.ts),
    subjectId: null,
    kind: 'status',
    crime: false,
    parts,
    text: parts.map((p) => p.text).join(''),
    detail: '',
  };
}

/**
 * All events as receipt rows, newest first (ts descending; equal ts: later arrival first), at most `max`.
 * `events` is the store's arrival-order list.
 */
export function buildRows(events: readonly ClarityEvent[], ctx: ReceiptContext, max = Infinity): ReceiptRow[] {
  const ordered = events
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => e && typeof e.ts === 'number')
    .sort((a, b) => a.e.ts - b.e.ts || a.i - b.i)
    .map(({ e }) => e);

  // Pass 1: one short descriptor per subject (first appearance seen), latest dispatch per incident.
  const looks = new Map<string, string>();
  const incidents = new Map<string, Dispatch>();
  const cameraNames = new Set<string>();
  for (const e of ordered) {
    if (e.type === 'relay' && str(e.appearance) && !looks.has(e.subject_id)) looks.set(e.subject_id, str(e.appearance));
    if (e.type === 'dispatch') {
      if (str(e.subject_appearance) && !looks.has(e.subject_id)) looks.set(e.subject_id, str(e.subject_appearance));
      incidents.set(e.incident_id, e);
      if (Array.isArray(e.path)) for (const s of e.path) if (s && typeof s.camera_id === 'string') cameraNames.add(ctx.cameraName(s.camera_id));
    }
    if (e.type === 'relay') {
      cameraNames.add(ctx.cameraName(e.from_camera));
      cameraNames.add(ctx.cameraName(e.to_camera));
    }
  }
  const names = [...cameraNames];
  const suspect = (subjectId: string | null | undefined, fallback?: string | null) =>
    suspectPhrase((subjectId && looks.get(subjectId)) || fallback);
  const cam = (id: unknown): Part => ({ text: ctx.cameraName(str(id)) || 'a camera', tone: 'strong' });
  const coordinator = capitalize(ctx.labels.coordinator);

  // Pass 2: sentences, oldest first, collapsing camera_status.
  const out: ReceiptRow[] = [];
  const health = new Map<string, string>();
  let group: StatusGroup | null = null;

  for (const e of ordered) {
    if (e.type === 'camera_status') {
      const status = str(e.status);
      const prev = health.get(e.camera_id);
      if (prev === status) continue; // repeat: nothing changed
      health.set(e.camera_id, status);
      if (group && out[out.length - 1]?.key === `cst:${group.firstId}`) {
        const had = group.cams.get(e.camera_id);
        group.cams.set(e.camera_id, { status, prev: had ? had.prev : prev });
        group.ts = Math.max(group.ts, e.ts);
        out[out.length - 1] = statusRow(group, ctx);
      } else {
        group = { firstId: e.event_id, ts: e.ts, cams: new Map([[e.camera_id, { status, prev }]]) };
        out.push(statusRow(group, ctx));
      }
      continue;
    }

    let parts: Part[] = [];
    let detail = '';
    let subjectId: string | null = null;
    let crime = false;

    switch (e.type) {
      case 'detection': {
        subjectId = ctx.detectionSubjects[e.event_id] ?? null;
        const look = str(e.appearance);
        const isCrime = typeof e.activity === 'string' && e.activity !== 'none' && e.activity in ctx.labels.activity;
        const what = str(e.label) && str(e.label) !== 'person' ? `a ${str(e.label)}` : 'a person';
        parts = isCrime
          ? [cam(e.camera_id), { text: ' saw a ' }, { text: activityWord(e.activity, ctx), tone: 'alert' }]
          : [cam(e.camera_id), { text: ` saw ${what}` }];
        if (look) parts.push({ text: ` (${noFullStop(look)})` });
        crime = isCrime && !subjectId;
        detail = join(look ? sentence(capitalize(look)) : '', headingSentence(e.direction));
        break;
      }
      case 'relay': {
        subjectId = e.subject_id;
        parts = [cam(e.from_camera), { text: ' asked ' }, cam(e.to_camera),
          { text: ` to watch for ${suspect(e.subject_id, e.appearance)}` }];
        const eta = typeof e.expected_arrival_s === 'number' && Number.isFinite(e.expected_arrival_s)
          ? `Expected there in about ${Math.round(e.expected_arrival_s)} s.` : '';
        detail = join(sentence(withCameraNames(str(e.summary), ctx)), headingSentence(e.direction), eta);
        break;
      }
      case 'agent_verdict': {
        subjectId = e.subject_id;
        const who = suspect(e.subject_id);
        const verb = e.decision === 'match' ? ` confirmed ${who}`
          : e.decision === 'no_match' ? ` saw no match for ${who}`
            : ` wasn't sure about ${who}`;
        parts = [cam(e.camera_id), { text: verb }];
        detail = sentence(withCameraNames(str(e.reason), ctx));
        break;
      }
      case 'dispatch': {
        subjectId = e.subject_id;
        const reco = recommendationText(str(e.recommendation), ctx, names);
        const lead: Part[] = e.status === 'alert' && e.requires_human_confirm === true
          ? [{ text: coordinator, tone: 'strong' }, { text: ' ' }, { text: 'needs your decision', tone: 'alert' }, { text: ': ' }]
          : e.status === 'alert'
            ? [{ text: `${coordinator} alert`, tone: 'strong' }, { text: ': ' }]
            : e.status === 'resolved'
              ? [{ text: coordinator, tone: 'strong' }, { text: ' closed the incident: ' }]
              : [{ text: coordinator, tone: 'strong' }, { text: ': ' }];
        parts = reco ? [...lead, { text: reco }]
          : [{ text: coordinator, tone: 'strong' }, { text: ` updated the ${activityWord(e.incident_type, ctx)} incident` }];
        const priority = str(e.priority) ? `${capitalize(str(e.priority))} priority.` : '';
        detail = join(priority, sentence(withCameraNames(str(e.reason), ctx)));
        break;
      }
      case 'operator_action': {
        const d = incidents.get(e.incident_id);
        subjectId = d?.subject_id ?? null;
        const verb = e.action === 'confirm' ? 'confirmed' : e.action === 'dismiss' ? 'dismissed' : `answered (${str(e.action)})`;
        const start = d && Array.isArray(d.path) && d.path.length ? d.path[0].camera_id : null;
        const what = d ? `the ${activityWord(d.incident_type, ctx)}` : 'an incident';
        parts = start
          ? [{ text: `Operator ${verb} ${what} at ` }, cam(start)]
          : [{ text: `Operator ${verb} ${what}` }];
        detail = str(e.note) ? sentence(`Note: ${str(e.note)}`) : '';
        break;
      }
      default:
        continue;
    }

    out.push({
      key: e.event_id,
      eventId: e.event_id,
      ts: e.ts,
      time: formatTs(e.ts),
      subjectId,
      kind: 'event',
      crime,
      parts,
      text: parts.map((p) => p.text).join(''),
      detail,
    });
  }

  out.reverse();
  return out.length > max ? out.slice(0, max) : out;
}
