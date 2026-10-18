# bus/: the event bus (owner: Mina)
`python -m bus.server` (FastAPI, default port 8080) checks every event against `contracts/`, appends it to `runs/<run_id>/events.jsonl` and streams it to the dashboard over `/ws`; settings are in the `bus/server.py` docstring.
Also here: `client.py` (`publish`/`fetch`, never raises), `fake_scenario.py` (scripted incidents, no models), `replay.py` (re-publishes a recorded run) and `metrics.py` (counts and timings from a run's logs).
