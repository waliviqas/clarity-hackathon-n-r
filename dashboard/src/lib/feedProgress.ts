// How far the clip on screen for each suspect has played (0..1), shared from the clip players to the map, so the
// map's tracker moves with the video instead of ahead of it. Tiny module store, no React state lifting.

type Progress = { camera: string; share: number; endedAt: number | null };
const bySubject = new Map<string, Progress>();
const listeners = new Set<() => void>();

export function setFeedProgress(subjectId: string, camera: string, share: number): void {
  const prev = bySubject.get(subjectId);
  if (prev && prev.camera === camera && Math.abs(prev.share - share) < 0.01) return;
  const endedAt = share >= 1 ? (prev && prev.camera === camera && prev.endedAt !== null ? prev.endedAt : Date.now()) : null;
  bySubject.set(subjectId, { camera, share, endedAt });
  for (const l of listeners) l();
}

export function getFeedProgress(subjectId: string): Progress | undefined {
  return bySubject.get(subjectId);
}

export function subscribeFeedProgress(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
