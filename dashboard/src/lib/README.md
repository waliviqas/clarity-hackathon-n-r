# `src/lib/`: the shared dashboard API

Owner: dashboard-map builder. Graph (`src/graph/`) and panels (`src/panels/`) import **only** from here:

```ts
import { useIncidents, useSelection, colorFor, sendOperatorAction, LABELS } from '../lib';
```

Need something that isn't here? Ask the owner; don't edit `lib/` yourself.

## Where your component goes
`App.tsx` picks these up automatically when the file exists (default export, no props):
`src/graph/AgentGraph.tsx`, `src/panels/IncidentCards.tsx`, `src/panels/ReceiptsLog.tsx`.
Each fills its slot (`height: 100%`, scroll inside yourself). Until then a placeholder shows.

## Hooks (React)
| Hook | Returns |
|---|---|
| `useCameras()` | `{ site, list, byId }` from cameras.json (`site` = whole config or null) |
| `useCameraStatus()` | latest `camera_status` per camera_id (missing = unknown, treat as online) |
| `useEvents()` | every event, arrival order (oldest first), de-duplicated by event_id |
| `useEventsById()` | `Map<event_id, event>` |
| `useIncidents()` | `IncidentView[]`: `{ incident_id, subject_id, color, chase, dispatch, action, firstTs, scripted }`, latest dispatch per incident, first-appearance order; `action` = latest operator_action or null |
| `useConnection()` | `{ state: 'connecting'\|'open'\|'closed', retries, nextRetryAt, lastError }` |
| `useSelection()` | `{ selection, highlighted, select }` (`highlighted` = selection + its `evidence_event_ids`, + path event_ids for a dispatch) |
| `useRecent()` | `Map<event_id, arrivedAtMs>` for events that arrived **live** in the last 6 s (animate only these) |
| `useSnapshotCount()` | bumps on every `bus_snapshot` (state replaced: redraw, don't animate) |
| `useSubjectColors()`, `useDetectionSubjects()`, `useLastTs()`, `useRunId()` | as named |
| `useStore(selector)` | any slice; the selector must return existing state, never a new object |

## Functions
- `select(eventId | null)`: select an event (receipt, card, arrow, edge); null clears.
- `colorFor(subjectId)` → chase hex (`--chase-1..5` in first-appearance order); `chaseVar(subjectId)` → `"var(--chase-N)"`. Unknown subject → `--text`.
- `subjectOf(eventOrId)` → subject_id (a detection gets one once a relay or a match verdict cites it).
- `sendOperatorAction(incidentId, 'confirm' | 'dismiss', note?)` → `Promise<{ ok, event, error? }>`. Never throws. Unique `op_` id, `ts` = newest ts seen, `source: "dashboard"`. The store marks the incident right away on success.
- `evidenceOf(e)`, `cameraOf(e)` (relay → from_camera, dispatch → last path camera), `isScripted(e)`, `getEvent(id)`.

## Constants (`constants.ts`)
`CHASE_COLORS`, `COLORS` (hex mirrors of `src/tokens.css`), `TIMING` (all animation/connection timings), `LABELS` (on-screen words: "coordinator", "Scripted run", status words "Tracking" / "Needs your decision" / "Confirmed" / "Dismissed"). Style with the CSS variables in `src/tokens.css`.

## Files
`types.ts` (mirrors `contracts/schemas/`; no invented fields) · `state.ts` (pure reducers) · `store.ts` (the instance) · `bus.ts` (WS + reconnect, GET /cameras, POST /events) · `hooks.ts` · `config.ts` (`VITE_BUS_URL`). Lib files import each other with `.ts` extensions so plain Node can run them (`npm run check:store`).
