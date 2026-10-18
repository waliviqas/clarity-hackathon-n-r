import 'leaflet/dist/leaflet.css';
import './map.css';
import { useMemo } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import type { LatLngTuple } from 'leaflet';
import type { MapContainerProps } from 'react-leaflet';
import { AttributionControl, MapContainer, TileLayer, ZoomControl } from 'react-leaflet';
import { TIMING, useCameras } from '../lib';
import { useFocusedSubject } from '../lib/focus.ts';
import { CameraLayer } from './CameraLayer.tsx';
import { IdleCameras } from './IdleCameras.tsx';
import { FIT_OPTIONS, FitToCameras } from './FitToCameras.tsx';
import { boundsOf, layoutKey, placeCameras } from './geo.ts';
import { useChase } from './useChase.ts';

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
/** OSM's ODbL attribution; must stay visible on the map. Reads "© OpenStreetMap contributors". */
const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors';
const MAP_STYLE = {
  '--pulse-ms': `${TIMING.detectionPulseMs}ms`,
  '--relay-dash-ms': `${TIMING.relayDashMs}ms`,
  '--relay-fade-ms': `${TIMING.relayFadeMs}ms`,
  '--badge-ms': `${TIMING.verdictBadgeMs}ms`,
} as CSSProperties;

/**
 * The map column: OSM (darkened), one marker per camera with a collision-free label, detection pulses,
 * and the chases (incident paths, relay arrows, predicted next cameras).
 */
export default function MapView() {
  const { site, list } = useCameras();

  const placed = useMemo(() => placeCameras(list), [list]);
  const fitKey = layoutKey(site?.site_id, placed);
  const bounds = useMemo(() => boundsOf(placed), [placed]);
  const posById = useMemo(
    () => new Map<string, LatLngTuple>(placed.map((p) => [p.camera.camera_id, [p.lat, p.lon]])),
    [placed],
  );
  const known = useMemo(() => new Set(posById.keys()), [posById]);
  const chase = useChase(known);
  const focused = useFocusedSubject();

  // The focused suspect's cameras: its chase path, relay arrows and predicted next cameras.
  const focusIds = useMemo(() => {
    if (!focused) return [];
    const ids = new Set<string>();
    for (const x of [...chase.segments, ...chase.arrows, ...chase.predictions]) {
      if (x.subjectId === focused) { ids.add(x.from); ids.add(x.to); }
    }
    return [...ids].filter((id) => posById.has(id)).sort();
  }, [focused, chase.segments, chase.arrows, chase.predictions, posById]);
  // A focus with no chase on this map (stale after a bus restart, or unknown) counts as no focus.
  const focus = focused && focusIds.length > 0 ? focused : null;
  // The map flies only when the focus itself changes, not when the focused chase grows.
  const focusKey = focus ?? '';
  const focusIdsKey = focus ? focusIds.join(',') : '';
  const focusBounds = useMemo(
    () => boundsOf(placed.filter((p) => focusIds.includes(p.camera.camera_id))),
    // focusIdsKey stands for focusIds.
    [placed, focusIdsKey],
  );

  if (!site) return <MapNote>Waiting for the camera list from the event bus.</MapNote>;

  // Initial view: fit the cameras; else the site's map center (FitToCameras keeps it fitted after).
  const center = site.map?.center;
  let view: Pick<MapContainerProps, 'bounds' | 'boundsOptions' | 'center' | 'zoom'>;
  if (bounds) view = { bounds, boundsOptions: FIT_OPTIONS };
  else if (center && Number.isFinite(center.lat) && Number.isFinite(center.lon)) {
    view = { center: [center.lat, center.lon], zoom: site.map?.zoom ?? 18 };
  } else {
    return <MapNote>No camera at {site.site_name ?? site.site_id} has a map position (lat/lon).</MapNote>;
  }

  return (
    <MapContainer
      className="clarity-map"
      style={MAP_STYLE}
      {...view}
      zoomControl={false}
      attributionControl={false}
      zoomSnap={0.25}
      zoomDelta={0.5}
      minZoom={3}
      maxZoom={20}
    >
      <TileLayer url={TILE_URL} attribution={OSM_ATTRIBUTION} className="map-tiles" maxNativeZoom={19} maxZoom={20} />
      <AttributionControl position="bottomright" prefix={false} />
      <ZoomControl position="bottomleft" />
      <FitToCameras bounds={bounds} fitKey={fitKey} focusBounds={focus ? focusBounds : null} focusKey={focusKey} />
      <IdleCameras siteId={site.site_id} segments={chase.segments} posById={posById} />
      <CameraLayer placed={placed} posById={posById} chase={chase} focused={focus} />
    </MapContainer>
  );
}

function MapNote({ children }: { children: ReactNode }) {
  return (
    <div className="map-note">
      <p>{children}</p>
    </div>
  );
}
