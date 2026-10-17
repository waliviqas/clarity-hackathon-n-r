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
    CLARITY_BUS_CORS    browser origins allowed to call the bus (comma-separated),
                        default http://localhost:5173,http://127.0.0.1:5173 (the dashboard dev server)

Polling (GET /events, bus.client.fetch): since_ts is inclusive and results come in arrival order,
not ts order. Poll with a lookback (e.g. since_ts = newest ts seen - 30) and de-duplicate by event_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contracts.validate import check

log = logging.getLogger("bus")

STRICT = os.environ.get("CLARITY_BUS_STRICT", "1") != "0"
RUN_ID = os.environ.get("CLARITY_RUN_ID", "run_dev")
LOG_PATH = Path(os.environ.get("CLARITY_RUNS_DIR", "runs")) / RUN_ID / "events.jsonl"
CAMERAS_PATH = Path(os.environ.get("CLARITY_CAMERAS", "data/cameras.json"))
CORS_ORIGINS = [o.strip() for o in
                os.environ.get("CLARITY_BUS_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
                if o.strip()]

SNAPSHOT_RECENT = 500  # a new dashboard connection gets the last 500 events...
SNAPSHOT_ALWAYS = {"dispatch", "relay", "agent_verdict", "operator_action"}  # ...plus every incident event
SEND_TIMEOUT_S = 0.5  # per client per event; a frozen browser tab gets dropped instead of stalling the bus

counts = {"valid": 0, "invalid": 0, "duplicates": 0}
events: list[dict] = []  # every accepted event this run, in arrival order
seen_ids: set[str] = set()
clients: set[WebSocket] = set()  # open dashboard connections
# Held while logging + broadcasting one event (and while a client joins), so every client
# sees events in the same order as the log, and nobody misses an event between snapshot and stream.
order_lock = asyncio.Lock()

app = FastAPI(title="Clarity bus")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"number {text} is out of range")
    return value


def _no_nan(name: str):
    raise ValueError(f"{name} is not allowed")


def parse_json(text: str | bytes):
    """json.loads that rejects NaN/Infinity: one such number would break GET /events and the dashboard."""
    return json.loads(text, parse_float=_finite_float, parse_constant=_no_nan)


def remember(event: dict) -> None:
    events.append(event)
    if isinstance(event.get("event_id"), str):
        seen_ids.add(event["event_id"])


def load_existing_log() -> None:
    """After a restart, pick up where this run left off so GET /events still has the history."""
    if not LOG_PATH.exists():
        return
    for i, line in enumerate(LOG_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = parse_json(line)
        except ValueError:  # e.g. a line cut short when the bus was killed mid-write
            event = None
        if isinstance(event, dict):
            remember(event)
        else:
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


def read_cameras():
    """The active cameras.json as a dict, or None if it's missing or broken."""
    try:
        return json.loads(CAMERAS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def snapshot_events() -> list[dict]:
    """Every incident event plus the most recent of the rest, in log order."""
    cutoff = len(events) - SNAPSHOT_RECENT
    return [e for i, e in enumerate(events) if i >= cutoff or e.get("type") in SNAPSHOT_ALWAYS]


async def broadcast(event: dict) -> None:
    for ws in list(clients):
        try:
            await asyncio.wait_for(ws.send_json(event), timeout=SEND_TIMEOUT_S)
        except Exception:  # client went away or stopped reading; drop it, keep the rest going
            clients.discard(ws)


@app.post("/events")
async def post_event(request: Request):
    # Requiring application/json makes browsers run the CORS check first, so a random web page
    # can't slip events into the bus with a "simple" text/plain request.
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return JSONResponse({"ok": False, "errors": ["Content-Type must be application/json"]}, status_code=415)
    try:
        event = parse_json(await request.body())
    except (ValueError, UnicodeDecodeError) as e:
        return JSONResponse({"ok": False, "errors": [f"body is not valid JSON: {e}"]}, status_code=422)
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

    async with order_lock:
        if event.get("event_id") in seen_ids:  # accepted anyway, but consumers that dedupe will drop it
            counts["duplicates"] += 1
            log.warning("duplicate event_id %s (%s); producers should use unique ids", event.get("event_id"),
                        event.get("type"))
        append_to_log(event)
        remember(event)
        await broadcast(event)
    return {"ok": True, "event_id": event.get("event_id"), "warnings": errors}


@app.websocket("/ws")
async def ws_stream(websocket: WebSocket):
    """Dashboard stream: one bus_snapshot (cameras + recent events), then every new event as it arrives."""
    await websocket.accept()
    async with order_lock:
        snapshot = {"type": "bus_snapshot", "run_id": RUN_ID, "cameras": read_cameras(), "events": snapshot_events()}
        try:
            await asyncio.wait_for(websocket.send_json(snapshot), timeout=5)
        except Exception:
            return
        clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # the dashboard doesn't send anything; this just notices it leaving
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


@app.get("/events")
async def get_events(type: str | None = None, since_ts: float = 0):
    """Past events, oldest first (arrival order). since_ts is inclusive: de-duplicate by event_id."""
    type = type or None  # ?type= with no value means all types
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
            "cameras": str(CAMERAS_PATH), "cameras_ok": read_cameras() is not None,
            "events": len(events), "clients": len(clients), **counts}


def main() -> None:
    import uvicorn

    port = urlparse(os.environ.get("CLARITY_BUS_URL", "http://localhost:8080")).port or 8080
    host = os.environ.get("CLARITY_BUS_HOST", "127.0.0.1")
    logging.basicConfig(level=logging.INFO)
    if read_cameras() is None:
        log.warning("no readable cameras file at %s: the dashboard map will be empty (set CLARITY_CAMERAS)",
                    CAMERAS_PATH)
    load_existing_log()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
