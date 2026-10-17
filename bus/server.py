"""Clarity event bus: every part POSTs its events here; the bus validates and logs them.

Run from the repo root:
    python -m bus.server

Settings (environment variables):
    CLARITY_BUS_URL     where the bus listens, default http://localhost:8080 (only the port is used)
    CLARITY_BUS_HOST    interface to bind, default 127.0.0.1 (reach it from the laptop via brev port-forward)
    CLARITY_BUS_STRICT  1 = reject invalid events with HTTP 422 (default); 0 = accept them with a warning
    CLARITY_RUN_ID      names the log folder, default run_dev
    CLARITY_RUNS_DIR    where run logs go, default runs
    CLARITY_CAMERAS     the active cameras.json served at GET /cameras, default data/cameras.json
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from contracts.validate import check

log = logging.getLogger("bus")

STRICT = os.environ.get("CLARITY_BUS_STRICT", "1") != "0"
RUN_ID = os.environ.get("CLARITY_RUN_ID", "run_dev")
LOG_PATH = Path(os.environ.get("CLARITY_RUNS_DIR", "runs")) / RUN_ID / "events.jsonl"
CAMERAS_PATH = Path(os.environ.get("CLARITY_CAMERAS", "data/cameras.json"))

counts = {"valid": 0, "invalid": 0}
events: list[dict] = []  # every accepted event this run, in arrival order

app = FastAPI(title="Clarity bus")


def load_existing_log() -> None:
    """After a restart, pick up where this run left off so GET /events still has the history."""
    if not LOG_PATH.exists():
        return
    for i, line in enumerate(LOG_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError:  # e.g. a line cut short when the bus was killed mid-write
            log.warning("skipping unreadable line %d in %s", i, LOG_PATH)
    log.info("loaded %d events from %s", len(events), LOG_PATH)


def event_ts(event: dict) -> float:
    try:
        return float(event.get("ts") or 0)
    except (TypeError, ValueError):
        return 0.0


def append_to_log(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


@app.post("/events")
async def post_event(request: Request):
    try:
        event = await request.json()
    except ValueError:
        return JSONResponse({"ok": False, "errors": ["body is not valid JSON"]}, status_code=422)
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        return JSONResponse({"ok": False, "errors": ["an event must be a JSON object with a string 'type' field"]},
                            status_code=422)

    errors = check(event)
    if errors:
        counts["invalid"] += 1
        if STRICT:
            return JSONResponse({"ok": False, "errors": errors}, status_code=422)
        log.warning("accepting invalid %s %s: %s", event.get("type"), event.get("event_id"), errors)
    else:
        counts["valid"] += 1

    append_to_log(event)
    events.append(event)
    return {"ok": True, "event_id": event.get("event_id"), "warnings": errors}


@app.get("/events")
async def get_events(type: str | None = None, since_ts: float = 0):
    """Past events, oldest first. since_ts is inclusive, so pollers may see their last event again:
    de-duplicate by event_id."""
    return [e for e in events
            if (type is None or e.get("type") == type) and event_ts(e) >= since_ts]


@app.get("/cameras")
async def get_cameras():
    # Read on every request so an edited cameras.json shows up without restarting the bus.
    try:
        return json.loads(CAMERAS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return JSONResponse({"ok": False, "errors": [f"no cameras file at {CAMERAS_PATH} (set CLARITY_CAMERAS)"]},
                            status_code=404)
    except ValueError as e:
        return JSONResponse({"ok": False, "errors": [f"{CAMERAS_PATH} is not valid JSON: {e}"]}, status_code=500)


@app.get("/health")
async def health():
    return {"ok": True, "run_id": RUN_ID, "strict": STRICT, "log": str(LOG_PATH),
            "events": len(events), **counts}


def main() -> None:
    import uvicorn

    port = urlparse(os.environ.get("CLARITY_BUS_URL", "http://localhost:8080")).port or 8080
    host = os.environ.get("CLARITY_BUS_HOST", "127.0.0.1")
    logging.basicConfig(level=logging.INFO)
    load_existing_log()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
