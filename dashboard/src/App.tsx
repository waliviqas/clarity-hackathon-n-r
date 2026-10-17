import { useEffect } from 'react';
import type { ComponentType } from 'react';
import { startBus } from './lib';
import { ConnectionBanner } from './shell/ConnectionBanner.tsx';
import { Header } from './shell/Header.tsx';
import { SlotBoundary } from './shell/SlotBoundary.tsx';
import MapView from './map/MapView.tsx';
import { GraphPlaceholder, IncidentsPlaceholder, RawEventsPlaceholder } from './shell/placeholders.tsx';

// Slots filled by the other builders, picked up automatically when the file exists
// (an eager glob of a missing file is just {}). Each file default-exports a component with no props:
//   src/graph/AgentGraph.tsx      (dashboard-graph)
//   src/panels/IncidentCards.tsx  (dashboard-panels)
//   src/panels/ReceiptsLog.tsx    (dashboard-panels)
type SlotModule = { default?: ComponentType };
function slot(modules: Record<string, SlotModule>, fallback: ComponentType): ComponentType {
  for (const m of Object.values(modules)) if (m.default) return m.default;
  return fallback;
}
const AgentGraph = slot(import.meta.glob<SlotModule>('./graph/AgentGraph.tsx', { eager: true }), GraphPlaceholder);
const IncidentCards = slot(import.meta.glob<SlotModule>('./panels/IncidentCards.tsx', { eager: true }), IncidentsPlaceholder);
const ReceiptsLog = slot(import.meta.glob<SlotModule>('./panels/ReceiptsLog.tsx', { eager: true }), RawEventsPlaceholder);

export default function App() {
  useEffect(() => startBus(), []);

  return (
    <div className="app">
      <Header />
      <ConnectionBanner />
      <main className="layout">
        {/* Each slot has its own error boundary: one panel throwing never blanks the whole screen. */}
        <section className="slot slot-map" aria-label="Map">
          <SlotBoundary name="map"><MapView /></SlotBoundary>
        </section>
        <aside className="right">
          <section className="slot slot-graph" aria-label="Agent graph">
            <SlotBoundary name="agent graph"><AgentGraph /></SlotBoundary>
          </section>
          <section className="slot slot-cards" aria-label="Incidents">
            <SlotBoundary name="incident cards"><IncidentCards /></SlotBoundary>
          </section>
          <section className="slot slot-receipts" aria-label="Receipts">
            <SlotBoundary name="receipts"><ReceiptsLog /></SlotBoundary>
          </section>
        </aside>
      </main>
    </div>
  );
}
