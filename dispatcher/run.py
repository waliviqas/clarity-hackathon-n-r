"""Run the dispatcher against Mina's bus: poll events, decide, publish dispatches.

    python -m dispatcher.run                       # model from CLARITY_LLM_* env vars, cameras from the bus
    python -m dispatcher.run --no-model            # rules only (ambiguous incidents -> "Operator review needed")
    python -m dispatcher.run --cameras data/sites/annex_placeholder/cameras.json

Talks to the bus only through the agreed interface in contracts/README.md:
    bus.client.fetch(type, since_ts) -> list[dict]   (inclusive since_ts, arrival order, never raises)
    bus.client.publish(event) -> None                (never raises)
plus GET {CLARITY_BUS_URL}/cameras for the active cameras.json.

Uses Wali's graph.predict_next(camera_id, direction) if the `graph` package is importable,
otherwise the dispatcher's built-in fallback.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import time
import urllib.request
from typing import Callable

from .dispatcher import Dispatcher
from .graph import CameraGraph

log = logging.getLogger("dispatcher.run")

INPUT_TYPES = ("detection", "relay", "agent_verdict", "operator_action")
LOOKBACK_S = 30.0  # contracts/README.md: poll with since_ts = newest seen - 30, de-duplicate by event_id

Fetch = Callable[[str, float], list[dict]]
Publish = Callable[[dict], None]


class Runner:
    """One poll = fetch every input type since (newest ts - lookback), process as one batch, publish results."""

    def __init__(self, dispatcher: Dispatcher, fetch: Fetch, publish: Publish, lookback_s: float = LOOKBACK_S):
        self.dispatcher, self.fetch, self.publish = dispatcher, fetch, publish
        self.lookback_s = lookback_s
        self.newest_ts = 0.0
        self.published = 0

    def poll_once(self) -> list[dict]:
        since = max(0.0, self.newest_ts - self.lookback_s)
        batch: list[dict] = []
        for kind in INPUT_TYPES:
            batch += self.fetch(kind, since)
        batch.sort(key=lambda e: e.get("ts", 0))  # the bus returns arrival order, not ts order
        if batch:
            self.newest_ts = max(self.newest_ts, max(float(e.get("ts", 0)) for e in batch))
        out = self.dispatcher.process(batch)  # repeats from the lookback are skipped by event_id
        for msg in out:
            self.publish(msg)
            self.published += 1
            log.info("%s %s %s/%s %s -> %s", msg["event_id"], msg["incident_id"], msg["incident_type"],
                     msg["priority"], msg["status"], msg["recommendation"][:90])
        return out

    def run_forever(self, poll_s: float = 0.5) -> None:
        while True:
            started = time.monotonic()
            self.poll_once()
            time.sleep(max(0.0, poll_s - (time.monotonic() - started)))


def load_predict_next():
    """Wali's graph.predict_next if it exists (contracts/README.md), else None -> built-in fallback."""
    try:
        from graph import predict_next  # type: ignore[import-not-found]  # owner: Wali
    except ImportError:
        return None
    return predict_next


def check_model(base_url: str, model: str, timeout_s: float = 5.0) -> None:
    """Stop with one line if the dispatcher model isn't served at base_url, before anything is published.
    Without this, every model call fails and each incident quietly becomes "Operator review needed"."""
    url = f"{base_url.rstrip('/')}/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            served = [m.get("id") for m in json.loads(resp.read().decode("utf-8")).get("data", [])]
    except Exception as e:
        raise SystemExit(f"model check: can't read {url} ({type(e).__name__}); start the model "
                         f"(infra/serve_dispatcher.sh) or run with --no-model")
    if model not in served:
        raise SystemExit(f"model check: {url} serves {', '.join(map(str, served)) or 'nothing'}, "
                         f"not CLARITY_LLM_MODEL={model}")


def fetch_cameras(bus_url: str) -> dict:
    with urllib.request.urlopen(f"{bus_url.rstrip('/')}/cameras", timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cameras", help="cameras.json path (default: GET /cameras from the bus)")
    ap.add_argument("--no-model", action="store_true", help="rules only; don't call vLLM")
    ap.add_argument("--no-guidance", action="store_true", help="don't append the fixed procedure lines")
    ap.add_argument("--poll", type=float, default=0.5, help="seconds between polls")
    ap.add_argument("--run-id", default=os.environ.get("CLARITY_RUN_ID"), help="copied into each dispatch's run_id")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    try:
        from bus.client import fetch, publish  # owner: Mina; must be importable (run from the repo root)
    except ImportError as e:
        raise SystemExit(f"bus.client not found ({e}). Run from the repo root once Mina's bus/ is merged.")

    bus_url = os.environ.get("CLARITY_BUS_URL", "http://127.0.0.1:8080")
    if args.cameras:
        graph = CameraGraph.load(args.cameras)
    else:
        try:
            graph = CameraGraph.from_config(fetch_cameras(bus_url))
        except Exception as e:
            raise SystemExit(f"couldn't read cameras from {bus_url}/cameras ({e}); pass --cameras PATH")

    llm = None
    if not args.no_model:
        from .llm import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenAICompatBackend
        check_model(os.environ.get("CLARITY_LLM_BASE_URL", DEFAULT_BASE_URL),
                    os.environ.get("CLARITY_LLM_MODEL", DEFAULT_MODEL))
        llm = OpenAICompatBackend.from_env()

    predict_next = load_predict_next()
    run_tag = "r" + secrets.token_hex(2)  # unique per process: inc_r3fa9_1, dsp_r3fa9_01
    dispatcher = Dispatcher(graph, llm, predict_next=predict_next, guidance=not args.no_guidance,
                            run_tag=run_tag, run_id=args.run_id)
    log.info("dispatcher up: bus=%s cameras=%d model=%s predict_next=%s ids=%s",
             bus_url, len(graph.cameras), "on" if llm else "off",
             "Wali's graph" if predict_next else "built-in fallback", f"inc_{run_tag}_N")
    try:
        Runner(dispatcher, fetch, publish).run_forever(args.poll)
    except KeyboardInterrupt:
        log.info("stopped; stats=%s", dict(dispatcher.stats))


if __name__ == "__main__":
    main()
