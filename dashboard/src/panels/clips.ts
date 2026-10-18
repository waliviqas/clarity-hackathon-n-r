// Camera clips for the "Watch last sighting" pop-up (pure, no React, no runtime imports, so plain Node
// can run it). The bus serves each camera's replay clip:
//   GET {bus}/clips/{camera_id}/info -> { camera_id, start_ts, available, content_type, reason }
//   GET {bus}/clips/{camera_id}      -> the file, with Range support so <video> can seek
// Clip second = run-clock ts - start_ts. The pop-up starts PRE_ROLL_S before the sighting.

/** Seconds of video shown before the sighting itself. */
export const PRE_ROLL_S = 3;

/** How long to wait for /info before calling the bus unreachable. */
const INFO_TIMEOUT_MS = 5000;

export interface ClipInfo {
  camera_id: string;
  /** Run-clock ts of the clip's first frame (null when cameras.json has none: treated as 0). */
  start_ts: number | null;
  available: boolean;
  content_type: string | null;
  /** Why available is false (technical, for the console / a tooltip). */
  reason: string | null;
}

export type ClipLookup =
  | { kind: 'ok'; info: ClipInfo }
  /** The bus answered but has no clip for this camera (unknown camera, bad answer). */
  | { kind: 'missing'; reason: string }
  /** The bus didn't answer (down, timed out, CORS). */
  | { kind: 'network'; reason: string };

export type ClipProblem = 'none' | 'missing' | 'network' | 'codec' | 'stalled';

/** What the operator reads instead of a broken player. */
export const CLIP_MESSAGES: Readonly<Record<Exclude<ClipProblem, 'none'>, string>> = {
  missing: 'No video for this camera yet.',
  network: "Couldn't reach the event bus for this video. Try again when it reconnects.",
  codec: "This clip can't play in the browser; convert it with data/convert_clips.py.",
  stalled: "The video stopped loading. Check the connection to the event bus.",
};

function finite(x: unknown): x is number {
  return typeof x === 'number' && Number.isFinite(x);
}

export function clipUrl(busUrl: string, cameraId: string): string {
  return `${busUrl}/clips/${encodeURIComponent(cameraId)}`;
}

export function clipInfoUrl(busUrl: string, cameraId: string): string {
  return `${clipUrl(busUrl, cameraId)}/info`;
}

/**
 * Where the video starts for a sighting at run-clock `sightingTs`: PRE_ROLL_S before it, never before
 * the clip's start. `startTs` null/junk counts as 0.
 */
export function clipSeek(sightingTs: number, startTs: number | null | undefined, preRoll = PRE_ROLL_S): number {
  if (!finite(sightingTs)) return 0;
  const start = finite(startTs) ? startTs : 0;
  return Math.max(0, sightingTs - start - preRoll);
}

/**
 * The seek clamped to a loaded clip's duration (a sighting after the clip ends shows its last frame).
 * `beyondEnd` = the sighting itself is after the end of the clip.
 */
export function clampSeek(seek: number, duration: number, sightingSecond: number): { at: number; beyondEnd: boolean } {
  if (!finite(duration) || duration <= 0) return { at: Math.max(0, seek), beyondEnd: false };
  return { at: Math.min(Math.max(0, seek), Math.max(0, duration - 0.05)), beyondEnd: sightingSecond > duration };
}

/** The /info answer, or null when it isn't the shape the bus documents. */
export function parseClipInfo(raw: unknown): ClipInfo | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.camera_id !== 'string' || typeof r.available !== 'boolean') return null;
  return {
    camera_id: r.camera_id,
    start_ts: finite(r.start_ts) ? r.start_ts : null,
    available: r.available,
    content_type: typeof r.content_type === 'string' ? r.content_type : null,
    reason: typeof r.reason === 'string' ? r.reason : null,
  };
}

/** GET /clips/{camera_id}/info. Never throws. */
export async function fetchClipInfo(busUrl: string, cameraId: string, signal?: AbortSignal): Promise<ClipLookup> {
  const url = clipInfoUrl(busUrl, cameraId);
  const timeout = AbortSignal.timeout(INFO_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(url, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
  } catch (err) {
    return { kind: 'network', reason: `can't reach ${url}: ${String(err)}` };
  }
  if (!res.ok) return { kind: 'missing', reason: `${url}: HTTP ${res.status}` };
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return { kind: 'missing', reason: `${url}: not JSON` };
  }
  const info = parseClipInfo(body);
  return info ? { kind: 'ok', info } : { kind: 'missing', reason: `${url}: unexpected answer` };
}

/**
 * MediaError code -> problem. 1 = aborted (we switched clips: not a problem), 2 = network,
 * 3 = decode, 4 = source not supported (unknown codec / container, e.g. mp4v in Chrome).
 */
export function problemFromMediaError(code: number | null | undefined): ClipProblem {
  if (code === 2) return 'stalled';
  if (code === 3 || code === 4) return 'codec';
  return 'none';
}
