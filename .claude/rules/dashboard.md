---
paths:
  - "dashboard/**"
---

# Dashboard rules

- Stack: React + TypeScript + Vite, Leaflet for the map (react-leaflet). Keep it to one page.
- The dashboard only talks to the bus: WebSocket `${VITE_BUS_URL}/ws` for events, `GET /cameras` for the camera config, `POST /events` for `operator_action`. It never calls models or other parts directly.
- Types for every message mirror `contracts/schemas/`. If a field is missing from the schema, don't invent it in the UI; flag it.
- Keep the latest `dispatch` per `incident_id`; append everything else to the receipts log.
- Always show the OpenStreetMap attribution ("© OpenStreetMap contributors") on the map.
- Must keep working when the bus is down (show "disconnected", retry) and when replaying a recorded run.
- The developer is on Windows: give PowerShell-friendly commands (`npm run dev`, no `export VAR=`; use `.env` files).
- The root `.gitignore` came from a Python template that ignores `lib/` and `dist/` everywhere. `dashboard/src/lib/` is re-allowed; any other `lib/` folder will be silently ignored, so check `git status` after adding folders.
