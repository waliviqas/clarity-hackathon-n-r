import { useEffect, useRef } from 'react';
import type { FitBoundsOptions, LatLngBoundsLiteral } from 'leaflet';
import { useMap } from 'react-leaflet';

/**
 * Room around the cameras for their labels, which can sit on any side (labels.ts): ~one label width
 * left and right, two label lines above and below (plus the attribution at the bottom).
 */
export const FIT_OPTIONS: FitBoundsOptions = {
  paddingTopLeft: [170, 56],
  paddingBottomRight: [170, 64],
  maxZoom: 19,
  animate: false,
};

/** Seconds the map takes to fly to a focused suspect (and back). */
const FOCUS_FLY_S = 0.6;

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

/** Keys that pan or zoom a focused Leaflet map. */
const MOVE_KEYS = new Set(['+', '-', '=', '_', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);

/**
 * Keeps all cameras in view: fits when the camera layout changes (fitKey), and again whenever the map
 * area changes size (window resize, disconnected banner, browser zoom) unless the operator has panned
 * or zoomed since. Operator moves are detected from what only a person does (drag, wheel, double-click,
 * the +/- buttons, keyboard, pinch), never from Leaflet's zoom events, which our own fits fire too.
 */
export function FitToCameras({ bounds, fitKey, focusBounds = null, focusKey = '' }: {
  bounds: LatLngBoundsLiteral | null;
  fitKey: string;
  /** The focused suspect's cameras (chase path + predicted next); null = no focus, fit every camera. */
  focusBounds?: LatLngBoundsLiteral | null;
  /** Changes when the focused suspect changes (or is cleared): the map flies there once. */
  focusKey?: string;
}) {
  const map = useMap();
  const boundsRef = useRef(bounds);
  boundsRef.current = focusBounds ?? bounds;
  const userMoved = useRef(false);

  const fitRef = useRef((fly = false) => {
    const b = boundsRef.current;
    const size = map.getSize();
    if (!b || size.x === 0 || size.y === 0) return;
    if (fly && !prefersReducedMotion()) map.flyToBounds(b, { ...FIT_OPTIONS, animate: true, duration: FOCUS_FLY_S });
    else map.fitBounds(b, FIT_OPTIONS);
  });

  // Focus changes (a suspect picked, or cleared): fly to its cameras / back to all of them.
  const lastFocus = useRef(focusKey);
  useEffect(() => {
    if (lastFocus.current === focusKey) return;
    lastFocus.current = focusKey;
    userMoved.current = false;
    fitRef.current(true);
  }, [focusKey]);

  // The focused chase grows: stay put, unless one of its cameras is now outside the view (then a gentle fit).
  const boundsFocus = useRef(focusKey);
  useEffect(() => {
    // A new focus is the fly above's job (calling it again here would restart that flight).
    if (boundsFocus.current !== focusKey) { boundsFocus.current = focusKey; return; }
    if (!focusBounds || userMoved.current) return;
    const size = map.getSize();
    if (size.x === 0 || size.y === 0) return;
    if (!map.getBounds().contains(focusBounds)) fitRef.current(true);
  }, [map, focusBounds, focusKey]);

  // New layout: fit, and forget any earlier pan/zoom.
  useEffect(() => {
    userMoved.current = false;
    fitRef.current();
  }, [fitKey]);

  // Operator pans or zooms: stop auto-fitting on resize (until the camera layout changes).
  useEffect(() => {
    const el = map.getContainer();
    const mark = () => { userMoved.current = true; };
    const onKey = (e: KeyboardEvent) => { if (MOVE_KEYS.has(e.key)) mark(); };
    const onClick = (e: MouseEvent) => {
      if (e.target instanceof Element && e.target.closest('.leaflet-control-zoom')) mark();
    };
    const onTouch = (e: TouchEvent) => { if (e.touches.length > 1) mark(); };
    map.on('dragstart', mark);
    el.addEventListener('wheel', mark, { passive: true });
    el.addEventListener('dblclick', mark);
    el.addEventListener('keydown', onKey);
    el.addEventListener('click', onClick, true);
    el.addEventListener('touchstart', onTouch, { passive: true });
    return () => {
      map.off('dragstart', mark);
      el.removeEventListener('wheel', mark);
      el.removeEventListener('dblclick', mark);
      el.removeEventListener('keydown', onKey);
      el.removeEventListener('click', onClick, true);
      el.removeEventListener('touchstart', onTouch);
    };
  }, [map]);

  // Size changes: Leaflet only watches window resizes, and the map column also changes height when
  // the banner shows. The observer catches both; the window listener is a second path in case the
  // observer's callback lands before Leaflet has re-measured.
  useEffect(() => {
    const el = map.getContainer();
    let frame = 0;
    const refit = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        map.invalidateSize({ animate: false });
        if (!userMoved.current) fitRef.current();
      });
    };
    const observer = new ResizeObserver(refit);
    observer.observe(el);
    window.addEventListener('resize', refit);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('resize', refit);
    };
  }, [map]);

  return null;
}
