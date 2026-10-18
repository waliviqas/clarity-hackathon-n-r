// Shared between the map and the crime bars (tiny module store, like feedProgress.ts):
//   - the focused suspect: the map zooms to that chase and dims the others; null = show every chase
//   - clip requests: the map asks the crime bars to open one suspect's bar on one camera's clip
import { useSyncExternalStore } from 'react';

export interface ClipRequest {
  subjectId: string;
  cameraId: string;
  /** Increases on every request, so asking for the same camera twice still reacts. */
  nonce: number;
}

let focused: string | null = null;
let clipRequest: ClipRequest | null = null;
let nonce = 0;
const listeners = new Set<() => void>();
const notify = () => { for (const l of listeners) l(); };

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Focus one suspect's chase (null clears the focus). */
export function focusSubject(subjectId: string | null): void {
  if (focused === subjectId) return;
  focused = subjectId;
  notify();
}

export function getFocusedSubject(): string | null {
  return focused;
}

export function useFocusedSubject(): string | null {
  return useSyncExternalStore(subscribe, () => focused);
}

/** Map -> crime bars: open this suspect's bar on this camera's clip (and focus that suspect). */
export function requestClip(subjectId: string, cameraId: string): void {
  clipRequest = { subjectId, cameraId, nonce: ++nonce };
  focused = subjectId;
  notify();
}

export function useClipRequest(): ClipRequest | null {
  return useSyncExternalStore(subscribe, () => clipRequest);
}
