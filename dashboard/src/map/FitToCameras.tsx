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

/**
 * Keeps all cameras in view: fits when the camera layout changes (fitKey), and again when the map
 * area resizes (disconnected banner, window) unless the operator has panned or zoomed since.
 */
export function FitToCameras({ bounds, fitKey }: { bounds: LatLngBoundsLiteral | null; fitKey: string }) {
  const map = useMap();
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const userMoved = useRef(false);
  const fitting = useRef(false);

  const fitRef = useRef(() => {
    const b = boundsRef.current;
    const size = map.getSize();
    if (!b || size.x === 0 || size.y === 0) return;
    fitting.current = true;
    try {
      map.fitBounds(b, FIT_OPTIONS);
    } finally {
      fitting.current = false;
    }
  });

  // New layout: fit, and forget any earlier pan/zoom.
  useEffect(() => {
    userMoved.current = false;
    fitRef.current();
  }, [fitKey]);

  // Operator drags or zooms (controls, wheel, double-click): stop auto-fitting on resize.
  useEffect(() => {
    const onUser = () => { if (!fitting.current) userMoved.current = true; };
    map.on('dragstart zoomstart', onUser);
    return () => { map.off('dragstart zoomstart', onUser); };
  }, [map]);

  // Leaflet only watches window resizes; the map column also changes height when the banner shows.
  useEffect(() => {
    const el = map.getContainer();
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
      if (!userMoved.current) fitRef.current();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [map]);

  return null;
}
