# runs/: recorded runs
The bus writes every accepted event to `runs/<run_id>/events.jsonl` (and when it accepted each to `arrivals.jsonl`); `python -m bus.replay runs/<run_id>/events.jsonl` plays a run back into the dashboard, `python -m bus.metrics runs/<run_id>` measures it.
`run_1018-0028_r2s/` is the earlier scripted clip-8 fallback: scripted perception, dispatcher in rules mode, no model ran, so its timings are not model latency (see its `RUN.md`).
