import './MapLegend.css';

/**
 * Map key, an overlay in the map slot's top-left corner. Each swatch copies the real marker styles
 * (map.css .cam-dot / .cam-alert-ring, IdleCameras.tsx, ChaseLayer.tsx SegmentLine with CHASE_STYLE.pathWeight in sizes.ts), drawn smaller.
 * Never takes clicks (pointer-events: none), so it can't block the map.
 */
export default function MapLegend() {
  return (
    <div className="map-legend" aria-label="Map key">
      <div className="map-legend-row">
        <span className="map-legend-swatch" aria-hidden="true">
          <span className="map-legend-dot is-alert" />
        </span>
        Crime seen
      </div>
      <div className="map-legend-row">
        <span className="map-legend-swatch" aria-hidden="true">
          <span className="map-legend-dot is-chase" />
        </span>
        Suspect followed
      </div>
      <div className="map-legend-row">
        <span className="map-legend-swatch" aria-hidden="true">
          <span className="map-legend-dot is-idle" />
        </span>
        Idle camera
      </div>
      <div className="map-legend-row">
        <span className="map-legend-swatch" aria-hidden="true">
          <svg className="map-legend-line" width="24" height="6" viewBox="0 0 24 6">
            <line x1="2" y1="3" x2="22" y2="3" />
          </svg>
        </span>
        Suspect's path
      </div>
    </div>
  );
}
