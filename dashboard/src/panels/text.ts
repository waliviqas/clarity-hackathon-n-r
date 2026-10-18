// Readable coordinator text for the incident cards and the receipts log. Pure: no React and no runtime
// imports, so plain Node runs it (npm run check:text). Display only: events are never changed.
//
// The real dispatcher (dispatcher/rules.py + guidance.py) names cameras with their codes, starts an
// answer it couldn't verify with "Operator review needed." and appends a fixed procedure line:
//   recommendation  Operator review needed. Send officer to Route 1: north corner (cam_03); fistfight at
//                   Route 1: south walkway (cam_01) Procedure: separate the parties, check for injuries, …
//   reason          fistfight detected (conf 0.80); subject confirmed at 3 camera(s)
// which reads
//   card            Send officer to Route 1: north corner; fistfight at Route 1: south walkway.
//                   Procedure: separate the parties, check for injuries, request EMS if needed.
//   meta / detail   Fistfight detected (80% confidence); subject confirmed at 3 cameras.
// Scripted text (bus/fake_scenario.py) has no codes, prefix or procedure, so it comes out unchanged.

import type { Dispatch } from '../lib';

/** On-screen name for a camera_id: its cameras.json name, or the id itself when it has none. */
export type CameraNamer = (cameraId: string) => string;

const CAMERA_ID = /\bcam_[A-Za-z0-9_-]+/g;
/** " (cam_03)": a code in brackets, with the spaces before it. */
const BRACKETED_ID = /\s*\((cam_[A-Za-z0-9_-]+)\)/g;
/** "cam_03 (…)": a code followed by an aside in brackets. */
const ID_THEN_ASIDE = /\b(cam_[A-Za-z0-9_-]+)\s*\(([^()]*)\)/g;
/** The dispatcher's prefix for an answer it couldn't verify. */
const REVIEW = /^operator review needed\s*(?:[.!:]\s*|$)/i;
/** "Procedure:" starting a word (the dispatcher appends one fixed procedure line at the end). */
const PROCEDURE = /(?:^|\s)Procedure:/g;
const PROCEDURE_LABEL = 'Procedure:';
/** "conf 0.80", "confidence: 0.8": a 0-1 confidence after the word. */
const CONFIDENCE = /\bconf(?:idence)?\b\s*[:=]?\s*(1(?:\.0+)?|0?\.\d+|0)(?!\d)(?!\.\d)/gi;
/** "3 camera(s)" */
const PLURAL = /\b(\d+)\s+([A-Za-z]+)\(s\)/g;

const PRIORITY_LABEL: Readonly<Record<string, string>> = {
  high: 'High priority',
  medium: 'Medium priority',
  low: 'Low priority',
};

/** A table's own entry, never an inherited one (a junk value like "constructor" gets undefined). */
function own(table: Readonly<Record<string, string>>, key: unknown): string | undefined {
  return typeof key === 'string' && Object.hasOwn(table, key) ? table[key] : undefined;
}

export function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Ends a fragment with a full stop unless it already ends a sentence ('' stays ''). */
export function sentence(s: string): string {
  const t = s.trim();
  return !t || /[.!?]$/.test(t) ? t : `${t}.`;
}

function norm(s: string): string {
  return s.replace(/\s+/g, ' ').trim().toLowerCase();
}

/** Does `head` end with `name` (case and spacing aside), as whole words? */
function endsWithName(head: string, name: string): boolean {
  const h = norm(head);
  const n = norm(name);
  if (!n || !h.endsWith(n)) return false;
  const before = h.charAt(h.length - n.length - 1);
  return !before || !/[\p{L}\p{N}_]/u.test(before);
}

/**
 * Camera codes in free text become camera names: "cam_03" -> "Route 1: north corner". A bracketed
 * code or name that only repeats the camera next to it is dropped, so "Route 1: north corner (cam_03)"
 * and "cam_03 (Route 1: north corner)" both read "Route 1: north corner". Unknown codes stay as they are.
 */
export function withCameraNames(text: unknown, cameraName: CameraNamer): string {
  if (typeof text !== 'string') return '';
  if (!text.includes('cam_')) return text;
  const name = (id: string) => cameraName(id) || id;
  return text
    .replace(BRACKETED_ID, (all: string, id: string, at: number, whole: string) => {
      const head = whole.slice(0, at);
      return endsWithName(head, name(id)) || endsWithName(head, id) ? '' : all;
    })
    .replace(ID_THEN_ASIDE, (all: string, id: string, aside: string) =>
      (norm(aside) === norm(name(id)) || norm(aside) === norm(id) ? id : all))
    .replace(CAMERA_ID, (id) => name(id));
}

export interface Recommendation {
  /** What to do, cameras by name ('' for an empty recommendation). */
  text: string;
  /** The trailing "Procedure: …" guidance without its label ('' when there is none). */
  procedure: string;
}

/**
 * A dispatch recommendation, cameras by name, with the trailing "Procedure: …" split off.
 * dropReview: also drop a leading "Operator review needed." (where the screen already asks for a
 * decision); a recommendation that says nothing else keeps it.
 */
export function splitRecommendation(reco: unknown, cameraName: CameraNamer, dropReview = false): Recommendation {
  let text = withCameraNames(reco, cameraName).trim();
  let procedure = '';
  let at = -1;
  for (const m of text.matchAll(PROCEDURE)) at = m.index + m[0].length - PROCEDURE_LABEL.length;
  if (at > 0) {
    procedure = text.slice(at + PROCEDURE_LABEL.length).trim();
    text = text.slice(0, at).trim();
  }
  if (dropReview) {
    const rest = text.replace(REVIEW, '');
    if (rest && rest !== text) text = capitalize(rest);
  }
  return { text, procedure };
}

/**
 * A dispatch reason as a sentence start: cameras by name, "(conf 0.80)" as "(80% confidence)",
 * "3 camera(s)" as "3 cameras", first letter capitalized. No full stop added.
 */
export function reasonText(reason: unknown, cameraName: CameraNamer): string {
  const t = withCameraNames(reason, cameraName).trim()
    .replace(CONFIDENCE, (_all: string, x: string) => `${Math.round(Number(x) * 100)}% confidence`)
    .replace(PLURAL, (_all: string, n: string, word: string) => `${n} ${word}${Number(n) === 1 ? '' : 's'}`);
  return capitalize(t);
}

export interface CardText {
  /** The recommendation as a sentence, without "Operator review needed." or the procedure. */
  reco: string;
  /** The procedure guidance as a sentence, without its "Procedure:" label ('' when there is none). */
  procedure: string;
  /** One muted line: "High priority. Suspect: …. <Reason>." */
  meta: string;
  /** Recommendation + "Procedure: …", for the hover title. */
  title: string;
}

/** What an incident card says about its latest dispatch. */
export function cardText(
  d: Pick<Dispatch, 'recommendation' | 'reason' | 'priority' | 'subject_appearance'>,
  cameraName: CameraNamer,
): CardText {
  const said = splitRecommendation(d.recommendation, cameraName, true);
  const reco = sentence(said.text);
  const procedure = sentence(said.procedure);
  const parts: string[] = [];
  const priority = own(PRIORITY_LABEL, d.priority);
  if (priority) parts.push(sentence(priority));
  const look = typeof d.subject_appearance === 'string' ? d.subject_appearance.trim().replace(/\.+$/, '') : '';
  if (look) parts.push(sentence(`Suspect: ${look}`));
  const reason = reasonText(d.reason, cameraName);
  if (reason) parts.push(sentence(reason));
  return {
    reco,
    procedure,
    meta: parts.join(' '),
    title: [reco, procedure ? `${PROCEDURE_LABEL} ${procedure}` : ''].filter(Boolean).join(' '),
  };
}
