"""Clarity event bus: every part POSTs its events here; the bus validates and logs them.

Run from the repo root:
    python -m bus.server

Settings (environment variables):
    CLARITY_BUS_URL     where the bus listens, default http://localhost:8080 (only the port is used)
    CLARITY_BUS_HOST    interface to bind, default 127.0.0.1 (reach it from the laptop via brev port-forward)
    CLARITY_BUS_STRICT  1 = reject invalid events with HTTP 422 (default); 0 = accept them with a warning
    CLARITY_RUN_ID      names the log folder, default run_dev
    CLARITY_RUNS_DIR    where run logs go, default runs
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

counts = {"valid": 0, "invalid": 0}

app = FastAPI(title="Clarity bus")


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
    return {"ok": True, "event_id": event.get("event_id"), "warnings": errors}


@app.get("/health")
async def health():
    return {"ok": True, "run_id": RUN_ID, "strict": STRICT, "log": str(LOG_PATH), **counts}


def main() -> None:
    import uvicorn

    port = urlparse(os.environ.get("CLARITY_BUS_URL", "http://localhost:8080")).port or 8080
    host = os.environ.get("CLARITY_BUS_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
