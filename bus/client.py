"""Tiny client for the Clarity bus. Standard library only, so any part can import it.

    from bus.client import publish, fetch

    publish(event)                              # POST one event; never raises
    fetch("operator_action", since_ts=1790.0)   # past events of one type; [] if the bus is unreachable

Bus address: CLARITY_BUS_URL (default http://127.0.0.1:8080; on Windows, 127.0.0.1 avoids a slow
IPv6 fallback that "localhost" can cause).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("bus.client")

TIMEOUT_S = 1.0
RETRY_AFTER_S = 2.0  # after a failed connection, don't try again for this long (drop instantly instead)
_bus_was_down = False  # warn once when the bus goes away, and once when it's back
_skip_until = 0.0


def _bus_url() -> str:
    return os.environ.get("CLARITY_BUS_URL", "http://127.0.0.1:8080").rstrip("/")


def _note_bus_state(up: bool, why: str = "") -> None:
    global _bus_was_down, _skip_until
    if not up and not _bus_was_down:
        log.warning("bus unreachable at %s (%s); events are being dropped until it's back", _bus_url(), why)
    elif up and _bus_was_down:
        log.warning("bus reachable again at %s", _bus_url())
    _bus_was_down = not up
    # A down bus can take the full timeout per call (on Windows), which would slow the caller;
    # so skip it for a moment and drop instantly instead.
    _skip_until = 0.0 if up else time.monotonic() + RETRY_AFTER_S


def _skipping() -> bool:
    return time.monotonic() < _skip_until


def _label(event) -> str:
    if isinstance(event, dict):
        return f"{event.get('type')} {event.get('event_id')}"
    return repr(event)[:80]


def _error_body(e: urllib.error.HTTPError) -> str:
    try:
        return e.read().decode("utf-8", "replace")
    except Exception:
        return ""


def publish(event: dict) -> None:
    """POST one event to the bus. Times out fast and never raises into the caller."""
    try:
        body = json.dumps(event).encode("utf-8")
    except Exception as e:  # TypeError/ValueError, or RecursionError for absurdly deep events
        log.warning("could not publish %s: not JSON-serializable (%s)", _label(event), e)
        return
    if _skipping():
        return
    try:
        req = urllib.request.Request(f"{_bus_url()}/events", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S):
            pass
        _note_bus_state(up=True)
    except urllib.error.HTTPError as e:  # the bus answered but rejected the event (usually 422)
        _note_bus_state(up=True)
        log.warning("bus rejected %s (HTTP %s): %s", _label(event), e.code, _error_body(e))
    except Exception as e:  # bus down, timeout, ...
        _note_bus_state(up=False, why=str(e))


def fetch(type: str, since_ts: float = 0) -> list[dict]:
    """Past events of one type with ts >= since_ts, oldest first. Returns [] if the bus is unreachable.
    since_ts is inclusive, so de-duplicate by event_id when polling."""
    if _skipping():
        return []
    try:
        query = urllib.parse.urlencode({"type": type, "since_ts": since_ts})
        with urllib.request.urlopen(f"{_bus_url()}/events?{query}", timeout=TIMEOUT_S) as resp:
            events = json.loads(resp.read().decode("utf-8"))
        _note_bus_state(up=True)
        return events if isinstance(events, list) else []
    except urllib.error.HTTPError as e:  # the bus answered with an error (e.g. 422 for a bad since_ts)
        _note_bus_state(up=True)
        log.warning("bus refused fetch(%r, %r) (HTTP %s): %s", type, since_ts, e.code, _error_body(e))
        return []
    except Exception as e:
        _note_bus_state(up=False, why=str(e))
        return []
