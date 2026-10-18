// Readable coordinator text for the incident cards and the receipts log. Pure: no React, and the only
// runtime import is the import-free lib/constants.ts, so plain Node runs it (npm run check:text).
// Display only: events are never changed.
//
// The real dispatcher (dispatcher/rules.py + guidance.py) names cameras with their codes, starts an
// answer it couldn't verify with "Operator review needed." and appends a fixed procedure line:
//   recommendation  Operator review needed. Send officer to Route 1: north corner (cam_03); fistfight at
//                   Route 1: south walkway (cam_01) Procedure: separate the parties, check for injuries, …
//   reason          fistfight detected (conf 0.80); subject confirmed at 3 camera(s)
//                   (no confidence: "fistfight detected; subject confirmed at 3 camera(s)")
// which reads
//   card title      Fistfight at Route 1: south walkway
//   card            Send officer to Route 1: north corner.          (the clause repeating the title goes)
//                   Procedure: separate the parties, check for injuries, request EMS if needed.
//   card meta       Medium priority. Fistfight (80% confidence), seen at 3 cameras. Suspect: male, red hoodie, …
//                   (no confidence: "Medium priority. Fistfight, seen at 3 cameras. Suspect: …", no made-up 0%)
//   receipt         Send officer to Route 1: north corner; fistfight at Route 1: south walkway   (full text)
//   receipt detail  Medium priority. Fistfight detected (80% confidence); subject confirmed at 3 cameras. …
// Scripted text (bus/fake_scenario.py) has no codes, prefix or procedure, so it comes out unchanged, and
// its card meta keeps its order (suspect before reason).

import type { Dispatch } from '../lib';
import { SCRIPTED_SOURCE } from '../lib/constants.ts';

/** On-screen name for a camera_id: its cameras.json name, or the id itself when it has none. */
export type CameraNamer = (cameraId: string) => string;

// Camera ids are "cam_" + [a-z0-9_] (contracts: no hyphen), so a hyphen ends a code: "cam_01-cam_02"
// is two codes. The guard after the id stops a backtrack to a shorter code ("cam_0" of "cam_01").
const ID = 'cam_[A-Za-z0-9_]+(?![A-Za-z0-9_])';
/** One code, or codes joined by hyphens ("cam_01-cam_02"); not a code inside "cam_01-02". */
const CAMERA_RUN = new RegExp(`\\b${ID}(?:-${ID})*(?!-[A-Za-z0-9])`, 'g');
/** " (cam_03)": a code in brackets, with the spaces before it. */
const BRACKETED_ID = /\s*\((cam_[A-Za-z0-9_]+)\)/g;
/** "cam_03 (…)": a code followed by an aside in brackets. */
const ID_THEN_ASIDE = /\b(cam_[A-Za-z0-9_]+)\s*\(([^()]*)\)/g;
/** Joins the names of hyphen-joined codes (multi-word names read badly with a bare hyphen). */
const RUN_JOINER = ' – ';
/** The dispatcher's prefix for an answer it couldn't verify. */
const REVIEW = /^operator review needed\s*(?:[.!:]\s*|$)/i;
/** "Procedure:" starting a word (the dispatcher appends one fixed procedure line at the end). */
const PROCEDURE = /(?:^|\s)Procedure:/;
const PROCEDURE_LABEL = 'Procedure:';
/** "conf 0.80", "confidence: 0.8": a 0-1 confidence after the word. */
const CONFIDENCE = /\bconf(?:idence)?\b\s*[:=]?\s*(1(?:\.0+)?|0?\.\d+|0)(?!\d)(?!\.\d)/gi;
/** "3 camera(s)" */
const PLURAL = /\b(\d+)\s+([A-Za-z]+)\(s\)/g;
/** The dispatcher's "<what> detected (80% confidence); subject confirmed at 3 cameras" (after reasonText), or
 *  "<what> detected; subject confirmed at 3 cameras" when it has no confidence, shortened on cards to
 *  "<what> (80% confidence), seen at 3 cameras" / "<what>, seen at 3 cameras" so the one-line meta fits at 1920 px. */
const TEMPLATE_REASON = /\s+detected(?: \((\d+% confidence)\))?;\s*subject confirmed at (\d+ cameras?)\b/gi;

const PRIORITY_LABEL: Readonly<Record<string, string>> = {
  high: 'High priority',
  medium: 'Medium priority',
  low: 'Low priority',
};

const TYPE_LABEL: Readonly<Record<string, string>> = {
  stabbing: 'Stabbing',
  fistfight: 'Fistfight',
  purse_snatch: 'Purse snatch',
  none: 'Incident',
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
 * and "cam_03 (Route 1: north corner)" both read "Route 1: north corner". Hyphen-joined codes are named
 * one by one: "cam_01-cam_02" -> "Route 1: south walkway – Route 1: west door". Unknown codes stay as
 * they are (a run of only unknown codes keeps its hyphens).
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
    .replace(CAMERA_RUN, (run: string) => {
      const ids = run.split('-');
      const names = ids.map(name);
      if (ids.length === 1) return names[0];
      return names.every((n, i) => n === ids[i]) ? run : names.join(RUN_JOINER);
    });
}

/** "purse_snatch" -> "Purse snatch"; an unknown type in sentence case; nothing -> "Incident". */
export function incidentTypeLabel(t: unknown): string {
  const known = own(TYPE_LABEL, t);
  if (known) return known;
  const words = String(t ?? '').replace(/_/g, ' ').trim();
  return words ? capitalize(words) : TYPE_LABEL.none;
}

export interface CardHeading {
  /** "Fistfight" */
  type: string;
  /** Camera name of the first path step (where the incident started); null without one. */
  where: string | null;
  /** "Fistfight at Route 1: south walkway", or just the type without a path. */
  title: string;
}

/** An incident card's title, from its latest dispatch. */
export function cardHeading(d: Pick<Dispatch, 'incident_type' | 'path'>, cameraName: CameraNamer): CardHeading {
  const path: unknown = d.path;
  const first: unknown = Array.isArray(path) && path.length ? path[0] : null;
  const id = first && typeof first === 'object' ? (first as { camera_id?: unknown }).camera_id : undefined;
  const where = typeof id === 'string' ? cameraName(id) || id : null;
  const type = incidentTypeLabel(d.incident_type);
  return { type, where, title: where ? `${type} at ${where}` : type };
}

/**
 * Drops a trailing "; <clause>" that only repeats `title` (case, spacing and a full stop aside):
 * "Send officer to Route 1: north corner; fistfight at Route 1: south walkway" with the title
 * "Fistfight at Route 1: south walkway" -> "Send officer to Route 1: north corner". Anything else stays.
 */
export function withoutRepeatedTitle(text: string, title: string): string {
  const cut = text.lastIndexOf(';');
  if (cut < 0 || !norm(title)) return text;
  const head = text.slice(0, cut).trim();
  const tail = text.slice(cut + 1).replace(/[.\s]+$/, '');
  return head && norm(tail) === norm(title) ? head : text;
}

export interface Recommendation {
  /** What to do, cameras by name ('' for an empty recommendation). */
  text: string;
  /** The "Procedure: …" guidance without its label ('' when there is none). */
  procedure: string;
}

/**
 * A dispatch recommendation, cameras by name, with the "Procedure: …" guidance split off at the first
 * "Procedure:" that has something before it (a text that starts with it isn't split, so it never empties).
 * dropReview: also drop a leading "Operator review needed." (where the screen already asks for a
 * decision); a recommendation that says nothing else keeps it.
 */
export function splitRecommendation(reco: unknown, cameraName: CameraNamer, dropReview = false): Recommendation {
  let text = withCameraNames(reco, cameraName).trim();
  let procedure = '';
  const m = PROCEDURE.exec(text);
  const at = m ? m.index + m[0].length - PROCEDURE_LABEL.length : -1;
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

/** A reasonText reason as the card shows it: the dispatcher's template shortened (TEMPLATE_REASON), the
 *  confidence only when it sent one; any other reason unchanged. */
function cardReason(reason: string): string {
  return reason.replace(TEMPLATE_REASON, (_all: string, confidence: string | undefined, cameras: string) =>
    `${confidence ? ` (${confidence})` : ''}, seen at ${cameras}`);
}

export interface CardText {
  /** The card's title ("Fistfight at Route 1: south walkway"), its type and place. */
  heading: CardHeading;
  /** The recommendation as a sentence, without "Operator review needed.", the procedure or a trailing
   *  clause that repeats the title. */
  reco: string;
  /** The procedure guidance as a sentence, without its "Procedure:" label ('' when there is none). */
  procedure: string;
  /** One muted line. Dispatcher: "Medium priority. <Reason>. Suspect: …." (what was detected first,
   *  so the end that may get cut is the description); scripted: "Medium priority. Suspect: …. <Reason>." */
  meta: string;
  /** Recommendation + "Procedure: …", for the hover title. */
  title: string;
}

/** What an incident card says about its latest dispatch. */
export function cardText(
  d: Pick<Dispatch, 'recommendation' | 'reason' | 'priority' | 'subject_appearance' | 'incident_type' | 'path' | 'source'>,
  cameraName: CameraNamer,
): CardText {
  const heading = cardHeading(d, cameraName);
  const said = splitRecommendation(d.recommendation, cameraName, true);
  const reco = sentence(withoutRepeatedTitle(said.text, heading.title));
  const procedure = sentence(said.procedure);
  const priority = own(PRIORITY_LABEL, d.priority);
  const look = typeof d.subject_appearance === 'string' ? d.subject_appearance.trim().replace(/\.+$/, '') : '';
  const suspect = look ? sentence(`Suspect: ${look}`) : '';
  const reason = sentence(cardReason(reasonText(d.reason, cameraName)));
  const parts = d.source === SCRIPTED_SOURCE ? [suspect, reason] : [reason, suspect];
  return {
    heading,
    reco,
    procedure,
    meta: [priority ? sentence(priority) : '', ...parts].filter(Boolean).join(' '),
    title: [reco, procedure ? `${PROCEDURE_LABEL} ${procedure}` : ''].filter(Boolean).join(' '),
  };
}
