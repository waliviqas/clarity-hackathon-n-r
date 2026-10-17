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
```

Shared code for the other dashboard parts: `src/lib/README.md`.
