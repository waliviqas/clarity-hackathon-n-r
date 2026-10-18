"""Measured numbers for one recorded run: latencies, event counts, overlap. Only what the logs show.

Run from the repo root:
    python -m bus.metrics runs/<run_id>

Reads events.jsonl and arrivals.jsonl (when the bus accepted each event; written by bus.server),
prints a summary and writes metrics.json into the same folder. Standard library only.

What the numbers mean:
- wall s: real seconds between the bus accepting two events (recv_wall in arrivals.jsonl).
- run clock s: difference of the events' own ts (the video timeline in replay mode).
- An incident is every dispatch with one incident_id. Its events: those dispatches, everything they cite
  (evidence_event_ids and path event_ids, followed through relays and verdicts), and every relay or
  verdict with the incident's subject_id. operator_action is not counted.
- Its crime detection: the first detection (in arrival order) the dispatches cite, directly or through
  other events, whose activity isn't "none".
- decisions: the incident's relays, verdicts and dispatches, whoever made them (a script, rules or a
  model). The logs don't record whether a model ran, so this is not a count of model calls.
- Overlap: an incident runs from its first to its last event; incidents that only touch count as
  "at once" but add no overlap time.
- Events from bus.fake_scenario make the run "scripted": its timings are the script's pacing, not models.
  A run re-published with bus.replay measures the replay pace, not the pipeline.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

DECISION_TYPES = ("relay", "agent_verdict", "dispatch")
SCRIPTED_SOURCE = "fake_scenario"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:  # e.g. a line cut short when the bus was killed mid-write
            row = None
        if isinstance(row, dict):
            rows.append(row)
        else:
            print(f"skipping unreadable line {i} in {path}", file=sys.stderr)
    return rows


def number(value) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return float(value) if ok else None


def unique_events(rows: list[dict]) -> list[dict]:
    """Log order, first copy of each event_id (the bus accepts duplicates; consumers drop them)."""
    seen, out = set(), []
    for e in rows:
        eid = e.get("event_id")
        if isinstance(eid, str):
            if eid in seen:
                continue
            seen.add(eid)
        out.append(e)
    return out


def cited_ids(event: dict) -> list[str]:
    evidence = event.get("evidence_event_ids")
    ids = [x for x in evidence if isinstance(x, str)] if isinstance(evidence, list) else []
    path = event.get("path")
    for step in path if isinstance(path, list) else []:
        if isinstance(step, dict) and isinstance(step.get("event_id"), str):
            ids.append(step["event_id"])
    return ids


def cited_closure(start: list[str], by_id: dict[str, dict]) -> set[str]:
    """The start events plus everything they cite, transitively (ids missing from the log are skipped)."""
    seen, todo = set(), list(start)
    while todo:
        eid = todo.pop()
        if eid in seen or eid not in by_id:
            continue
        seen.add(eid)
        todo.extend(cited_ids(by_id[eid]))
    return seen


def gap(a: dict | None, b: dict | None, clock) -> float | None:
    """Seconds from event a to event b on the given clock, or None if either is unknown."""
    if a is None or b is None:
        return None
    x, y = clock(a), clock(b)
    return round(y - x, 3) if x is not None and y is not None else None


def span(members: list[dict], clock) -> list[float] | None:
    times = [t for t in map(clock, members) if t is not None]
    return [min(times), max(times)] if times else None


def incident_metrics(key: str, dispatches: list[dict], events: list[dict], by_id: dict[str, dict],
                     wall, run) -> dict:
    subjects = sorted({d["subject_id"] for d in dispatches if isinstance(d.get("subject_id"), str)})
    dispatch_ids = [d["event_id"] for d in dispatches if isinstance(d.get("event_id"), str)]
    cited = cited_closure(dispatch_ids, by_id)
    linked = [e["event_id"] for e in events if e.get("type") in ("relay", "agent_verdict")
              and e.get("subject_id") in subjects and isinstance(e.get("event_id"), str)]
    member_ids = cited_closure(dispatch_ids + linked, by_id)
    members = [e for e in events if e.get("event_id") in member_ids]

    crime = next((e for e in events if e.get("event_id") in cited and e.get("type") == "detection"
                  and e.get("activity") not in (None, "none")), None)
    first = dispatches[0]
    alert = next((d for d in dispatches if d.get("status") == "alert"), None)
    decisions = Counter(e["type"] for e in members if e.get("type") in DECISION_TYPES)
    return {
        "incident_id": key,
        "subject_ids": subjects,
        "incident_type": first.get("incident_type"),
        "crime_detection_id": crime.get("event_id") if crime else None,
        "crime_camera_id": crime.get("camera_id") if crime else None,
        "first_dispatch_id": first.get("event_id"),
        "first_alert_id": alert.get("event_id") if alert else None,
        "to_first_dispatch_wall_s": gap(crime, first, wall),
        "to_first_dispatch_run_s": gap(crime, first, run),
        "to_first_alert_wall_s": gap(crime, alert, wall),
        "to_first_alert_run_s": gap(crime, alert, run),
        "events": len(members),
        "decisions": sum(decisions.values()),
        "decisions_by_type": {t: decisions[t] for t in DECISION_TYPES if decisions[t]},
        "run_span": span(members, run),
        "wall_span": span(members, wall),
    }


def overlap(spans: list[list[float]]) -> tuple[int, list[list[float]]]:
    """(most spans open at one moment, merged windows where 2+ are open). Spans are closed intervals."""
    if not spans:
        return 0, []
    most = max(sum(1 for s2, e2 in spans if s2 <= s <= e2) for s, _ in spans)
    points = sorted({p for sp in spans for p in sp})
    windows: list[list[float]] = []
    for a, b in zip(points, points[1:]):
        if sum(1 for s, e in spans if s <= a and e >= b) >= 2:
            if windows and windows[-1][1] == a:
                windows[-1][1] = b
            else:
                windows.append([a, b])
    return most, windows


def rate_in(windows: list[list[float]], times: list[float]) -> dict:
    seconds = sum(b - a for a, b in windows)
    count = sum(1 for t in times if any(a <= t <= b for a, b in windows))
    return {"seconds": round(seconds, 3), "events": count,
            "events_per_s": round(count / seconds, 2) if seconds > 0 else None}


def scripted_label(by_source: Counter, total: int) -> str:
    scripted = by_source.get(SCRIPTED_SOURCE, 0)
    if total and scripted == total:
        return (f"SCRIPTED: all {total} events come from bus.fake_scenario; "
                "timings are the script's pacing, not model latency.")
    if scripted:
        return (f"MIXED: {scripted} of {total} events come from bus.fake_scenario (scripted); "
                "label any number that includes them as scripted.")
    return ("No fake_scenario events. (If this run was made with bus.replay, wall timings show "
            "the replay pace, not the pipeline.)")


def compute(run_dir: Path) -> dict:
    raw = read_jsonl(run_dir / "events.jsonl")
    arrivals = read_jsonl(run_dir / "arrivals.jsonl")
    events = unique_events(raw)
    by_id = {e["event_id"]: e for e in events if isinstance(e.get("event_id"), str)}
    recv = {}
    for a in arrivals:
        if isinstance(a.get("event_id"), str) and a["event_id"] not in recv:
            recv[a["event_id"]] = number(a.get("recv_wall"))

    def wall(e: dict) -> float | None:
        return recv.get(e.get("event_id"))

    def run(e: dict) -> float | None:
        return number(e.get("ts"))

    groups: dict[str, list[dict]] = {}
    for e in events:
        key = e.get("incident_id") or e.get("subject_id")
        if e.get("type") == "dispatch" and isinstance(key, str):
            groups.setdefault(key, []).append(e)
    incidents = [incident_metrics(k, ds, events, by_id, wall, run) for k, ds in groups.items()]

    most, run_windows = overlap([i["run_span"] for i in incidents if i["run_span"]])
    _, wall_windows = overlap([i["wall_span"] for i in incidents if i["wall_span"]])
    walls = [t for t in map(wall, events) if t is not None]
    by_type = Counter(str(e.get("type")) for e in events)
    by_source = Counter(str(e.get("source")) for e in events)
    run_id = next((e["run_id"] for e in events if isinstance(e.get("run_id"), str)), run_dir.name)
    return {
        "run_dir": run_dir.as_posix(),  # same text on Windows and Linux
        "run_id": run_id,
        "scripted": by_source.get(SCRIPTED_SOURCE, 0) > 0,
        "scripted_events": by_source.get(SCRIPTED_SOURCE, 0),
        "label": scripted_label(by_source, len(events)),
        "events_total": len(events),
        "duplicate_lines": len(raw) - len(events),
        "arrivals_lines": len(arrivals),
        "arrivals_match_log": [a.get("event_id") for a in arrivals] == [e.get("event_id") for e in raw],
        "events_without_arrival": sum(1 for e in events if wall(e) is None),
        "whole_run_wall_s": round(max(walls) - min(walls), 3) if walls else None,
        "by_type": dict(by_type.most_common()),
        "by_source": dict(by_source.most_common()),
        "max_incidents_at_once_run_clock": most,
        "while_overlapping_wall": rate_in(wall_windows, walls),
        "while_overlapping_run_clock": rate_in(run_windows, [t for t in map(run, events) if t is not None]),
        "incidents": incidents,
    }


def seconds(value: float | None, digits: int) -> str:
    return f"{value:.{digits}f} s" if value is not None else "n/a"


def counts_line(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "none"


def rate_text(r: dict) -> str:
    return f"{r['events_per_s']:.2f} events/s" if r["events_per_s"] is not None else "n/a"


def report(m: dict) -> str:
    match = "yes" if m["arrivals_match_log"] else "NO"
    lines = [f"Clarity run metrics: {m['run_dir']}  (run_id {m['run_id']})", m["label"],
             f"Log: {m['events_total']} events, {m['arrivals_lines']} arrival lines"
             + (f" (line up with events.jsonl: {match})" if m["arrivals_lines"] else "")]
    if m["duplicate_lines"]:
        lines.append(f"  {m['duplicate_lines']} duplicate event_id lines ignored")
    if m["events_without_arrival"]:
        lines.append(f"  {m['events_without_arrival']} events have no arrival line: their wall times are n/a")
    lines += ["", "Per incident (seconds from the first crime detection its dispatches cite;",
              "wall = real time at the bus, run clock = difference of event ts):"]
    for i in m["incidents"]:
        crime = (f"crime {i['crime_detection_id']} at {i['crime_camera_id'] or '?'}" if i["crime_detection_id"]
                 else "no crime detection cited")
        about = ", ".join([str(i["incident_type"] or "?")] + i["subject_ids"])
        lines.append(f"  {i['incident_id']} ({about}): {crime}")
        for label, eid, w, r in (("first dispatch", i["first_dispatch_id"], i["to_first_dispatch_wall_s"],
                                  i["to_first_dispatch_run_s"]),
                                 ("first alert", i["first_alert_id"], i["to_first_alert_wall_s"],
                                  i["to_first_alert_run_s"])):
            lines.append(f"      to {label:<15}{str(eid or '-'):<12} wall {seconds(w, 2):>9}"
                         f"   run clock {seconds(r, 1):>8}")
        lines.append(f"      events {i['events']}, decisions {i['decisions']} "
                     f"({counts_line(i['decisions_by_type'])})")
    if not m["incidents"]:
        lines.append("  no dispatches in this run")

    ow, orun = m["while_overlapping_wall"], m["while_overlapping_run_clock"]
    lines += ["", "Overall:",
              f"  events by type:    {counts_line(m['by_type'])}",
              f"  events by source:  {counts_line(m['by_source'])}",
              f"  most incidents at once (run clock): {m['max_incidents_at_once_run_clock']}",
              f"  while 2+ incidents overlapped: {ow['events']} events in {ow['seconds']:.2f} s wall"
              f" = {rate_text(ow)}",
              f"                      run clock: {orun['events']} events in {orun['seconds']:.1f} s"
              f" = {rate_text(orun)}",
              f"  whole run: {m['events_total']} events in {seconds(m['whole_run_wall_s'], 2)} wall"]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run_dir", help="a run folder, e.g. runs/run_demo1 (holds events.jsonl and arrivals.jsonl)")
    args = p.parse_args()
    run_dir = Path(args.run_dir)
    if not (run_dir / "events.jsonl").is_file():
        p.error(f"no events.jsonl in {run_dir}")

    m = compute(run_dir)
    print(report(m))
    if not (run_dir / "arrivals.jsonl").is_file():
        print("\nNo arrivals.jsonl (bus older than B8?): wall numbers are n/a, run clock numbers only.")
    out = run_dir / "metrics.json"
    out.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
