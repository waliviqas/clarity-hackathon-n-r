// Talks to the bus, and nothing else does: WS /ws (snapshot, then live events), GET /cameras,
// POST /events (operator_action). Reconnects forever with backoff; the store keeps showing the
// last state while disconnected. No React here.

import type { BusSnapshot, OperatorAction, OperatorDecision } from './types.ts';
import { BUS_URL, BUS_WS_URL } from './config.ts';
import { TIMING } from './constants.ts';
import { buildOperatorAction, isCamerasConfig } from './state.ts';
import {
  addLocalEvent, expireRecent, getState, receiveEvent, receiveSnapshot, updateCameras, updateConnection,
} from './store.ts';

let ws: WebSocket | null = null;
let running = false;
let users = 0;
let attempt = 0;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let keepaliveTimer: ReturnType<typeof setInterval> | null = null;
let pruneTimer: ReturnType<typeof setInterval> | null = null;
let teardownTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * Start the bus connection (idempotent, ref-counted). Returns a stop function.
 * Call it from one useEffect (App does). The deferred teardown keeps React StrictMode's
 * mount/unmount/mount from opening and killing a socket in dev.
 */
export function startBus(): () => void {
  users++;
  if (teardownTimer !== null) { clearTimeout(teardownTimer); teardownTimer = null; }
  if (!running) begin();
  let stopped = false;
  return () => {
    if (stopped) return;
    stopped = true;
    users--;
    if (users === 0) teardownTimer = setTimeout(() => { teardownTimer = null; if (users === 0) end(); }, 0);
  };
}

function begin(): void {
  running = true;
  attempt = 0;
  pruneTimer = setInterval(() => expireRecent(), TIMING.recentPruneMs);
  connect();
}

function end(): void {
  running = false;
  if (retryTimer !== null) { clearTimeout(retryTimer); retryTimer = null; }
  if (pruneTimer !== null) { clearInterval(pruneTimer); pruneTimer = null; }
  stopKeepalive();
  const sock = ws;
  ws = null;
  sock?.close();
}

function connect(): void {
  retryTimer = null;
  if (!running) return;
  updateConnection({ state: 'connecting', nextRetryAt: null });
  let sock: WebSocket;
  try {
    sock = new WebSocket(BUS_WS_URL);
  } catch (err) {
    scheduleRetry(`can't open ${BUS_WS_URL}: ${String(err)}`);
    return;
  }
  ws = sock;
  sock.onopen = () => {
    if (ws !== sock) return;
    updateConnection({ state: 'open', nextRetryAt: null, lastError: null });
    startKeepalive(sock);
  };
  sock.onmessage = (msg: MessageEvent) => {
    if (ws !== sock) return;
    handleMessage(msg.data);
  };
  sock.onclose = (ev: CloseEvent) => {
    if (ws !== sock) return;
    ws = null;
    stopKeepalive();
    scheduleRetry(`connection closed (code ${ev.code})`);
  };
  sock.onerror = () => { /* onclose always follows, and carries the code */ };
}

function handleMessage(data: unknown): void {
  if (typeof data !== 'string') return;
  let msg: unknown;
  try {
    msg = JSON.parse(data);
  } catch {
    return;
  }
  if (typeof msg !== 'object' || msg === null) return;
  if ((msg as { type?: unknown }).type === 'bus_snapshot') {
    const snap = msg as BusSnapshot;
    attempt = 0;
    updateConnection({ retries: 0, lastError: null });
    receiveSnapshot(snap);
    if (!isCamerasConfig(snap.cameras) && !getState().cameras.site) void refreshCameras();
    return;
  }
  receiveEvent(msg);
}

function scheduleRetry(reason: string): void {
  if (!running) return;
  attempt++;
  const backoff = Math.min(TIMING.reconnectMaxMs, TIMING.reconnectMinMs * 2 ** (attempt - 1));
  const delay = Math.round(backoff * (0.8 + Math.random() * 0.4));
  updateConnection({ state: 'closed', retries: attempt, lastError: reason, nextRetryAt: Date.now() + delay });
  retryTimer = setTimeout(connect, delay);
}

function startKeepalive(sock: WebSocket): void {
  stopKeepalive();
  keepaliveTimer = setInterval(() => {
    if (sock.readyState === WebSocket.OPEN) sock.send('ping');
  }, TIMING.keepaliveMs);
}

function stopKeepalive(): void {
  if (keepaliveTimer !== null) { clearInterval(keepaliveTimer); keepaliveTimer = null; }
}

/** Re-read GET /cameras into the store (the snapshot normally carries cameras already). */
export async function refreshCameras(): Promise<boolean> {
  try {
    const res = await fetch(`${BUS_URL}/cameras`, { signal: AbortSignal.timeout(TIMING.postTimeoutMs) });
    if (!res.ok) return false;
    const config: unknown = await res.json();
    if (!isCamerasConfig(config)) return false;
    updateCameras(config);
    return true;
  } catch {
    return false;
  }
}

export interface SendResult {
  ok: boolean;
  /** The operator_action that was sent (also when it failed, for display/debugging). */
  event: OperatorAction;
  /** Why it failed (bus validation errors, HTTP status, network error). */
  error?: string;
}

/**
 * POST an operator_action (Confirm / Dismiss) to the bus. Never throws.
 * On success the action is applied to the store right away; the bus's WS echo is de-duplicated.
 */
export async function sendOperatorAction(
  incidentId: string, action: OperatorDecision, note?: string | null,
): Promise<SendResult> {
  const event = buildOperatorAction(getState(), incidentId, action, note);
  try {
    const res = await fetch(`${BUS_URL}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
      signal: AbortSignal.timeout(TIMING.postTimeoutMs),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { errors?: unknown };
        if (Array.isArray(body.errors) && body.errors.length) detail += `: ${body.errors.join('; ')}`;
      } catch { /* not JSON */ }
      return { ok: false, event, error: detail };
    }
    addLocalEvent(event);
    return { ok: true, event };
  } catch (err) {
    return { ok: false, event, error: `can't reach the bus at ${BUS_URL}: ${String(err)}` };
  }
}

// Vite hot reload: close the old socket when this module is replaced.
import.meta.hot?.dispose(() => { users = 0; end(); });
