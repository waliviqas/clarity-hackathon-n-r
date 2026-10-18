# Clarity dashboard

The operator's screen: map, agent graph, incident cards, receipts. It talks only to the event bus.

## Run (PowerShell, Node 24)
```powershell
cd dashboard
npm install
copy .env.example .env      # set VITE_BUS_URL if the bus isn't on http://127.0.0.1:8080
npm run dev                 # http://localhost:5173 (must stay on 5173: the bus allows CORS only from there)
```

## Check
```powershell
npm run build                                                   # tsc --noEmit + vite build
npm run check:store                                             # store logic, no bus needed
npm run check:store -- --live --expect-incidents 3 --confirm inc_1   # against a running bus + bus.fake_scenario
npm run check:labels                                            # map labels don't collide (placeholder site)
npm run check:labels -- ..\data\sites\<site>\cameras.json       # same for another site
npm run check:chase                                             # chase drawing rules (arrows, paths, predictions), no bus
#   (from the repo root) python -m bus.fake_scenario --out runs\fake\events.jsonl   makes a scripted log, then:
npm run check:chase -- --events ..\runs\fake\events.jsonl       # replay it through the store at 2x and check every step
npm run check:chase -- --live                                   # watch a running bus while bus.fake_scenario --speed 2 runs
```

## Map: what the chases look like
- Path: solid 4 px line in the subject's chase color through the latest dispatch's `path`; a `match` verdict extends it right away (until the next dispatch).
- Relay: 3 px arrow `from_camera` -> `to_camera` with a dash that travels toward the target (live events only; a reload draws it still). It ends at a verdict for that subject at `to_camera`, or after `expected_arrival_s` + 10 s on the run clock. `no_match` fades it and shows "✕ no match" on the camera for 5 s; `uncertain` shows "? uncertain".
- Prediction: 2 px dashed line at 60% from the last path camera, with "70%" on it. A relay arrow on the same pair runs beside it.
- Camera dots fill with the chase color once the subject is confirmed there. Click a line or arrow to select its event; click the empty map to clear.
- Reduced motion: arrows stand still, nothing fades or pulses.

Shared code for the other dashboard parts: `src/lib/README.md`.
