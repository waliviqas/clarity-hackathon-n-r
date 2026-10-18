"""Camera agents: one per camera, each with its own inbox of relays (contract: detection, relay, agent_verdict).

    net = Network(site["cameras"], emit=publish)
    net.on_answer("cam_01", spotter_answer, window=(1.75, 10.25))   # window: the clip, on the run clock
    net.expire(now)                                                 # unanswered relays past their deadline

What an agent does with a spotter answer from its own camera:
  1. Publishes it as a `detection` (agents/adapter.py), ts = the end of the clip.
  2. Answers every relay in its inbox: compares the answer with the relayed description and checks the
     travel time (agents/matching.py) -> `agent_verdict` match / no_match / uncertain, citing the relay and
     the detection. On a match it relays onward (the contract: the matching camera relays to the next).
     Opt-in, Network(follow_uncertain=True): it also relays onward when uncertain about someone running
     (basis "possible", citing only the verdict), so weak sightings along a route can add up.
  3. If the answer shows a crime that no relay explains, it opens a subject and relays to every neighbor.
If the spotter fails on a clip, relays that clip could have answered get "uncertain" ("can't tell").
Relays go to the camera's cameras.json neighbors the subject hasn't reached yet (never back to a camera it
was opened at or relayed to, so a loop of cameras can't relay forever), with the link's travel_time_s as
expected_arrival_s and its direction. A relay nobody answers by its deadline (the latest plausible
arrival, later if that camera's clip is still playing then) gets a "no_match".
Agents never read ground truth.
"""
from __future__ import annotations

import secrets
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .adapter import (ACTIVITY_WORDS, SCHEMA_VERSION, SOURCE, UNSCORED_CONFIDENCE, activity_of, appearance_text,
                      is_crime, to_detection)
from .matching import PRIOR, arrival_bounds, check_timing, features, judge, merge

SUMMARY_MAX = 400  # contract maxLength of relay.summary


@dataclass
class Sighting:
    """One spotter answer at one camera, as its agent remembers it."""
    detection_id: str
    window: tuple[float, float]
    answer: dict


@dataclass
class Relay:
    """A relay waiting in an agent's inbox, with what the sender knew when it sent it."""
    event: dict
    features: dict[str, str]                    # the suspect's description so far
    left: tuple[float, float]                   # the sender's clip that saw them (run clock)
    weak: list[tuple[str, float]] = field(default_factory=list)  # uncertain sightings since the last match
    deadline: float = 0.0


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


class CameraAgent:
    def __init__(self, camera: dict, net: "Network"):
        self.camera_id = camera["camera_id"]
        self.agent_id = "agent_" + self.camera_id.replace("_", "")  # agent_cam05, as in the contract example
        self.links = {nb["camera_id"]: nb for nb in camera.get("neighbors", []) if nb.get("camera_id")}
        self.inbox: list[Relay] = []
        self.last: Sighting | None = None
        self.blind: tuple[tuple[float, float], str] | None = None  # last clip the spotter failed on, and why
        self.net = net

    def see(self, answer: dict, window: tuple[float, float]) -> None:
        """A new spotter answer from this camera."""
        det = self.net.detection(self.camera_id, answer, window)
        seen = Sighting(det["event_id"], window, answer)
        self.last = seen
        explained = False
        for relay in list(self.inbox):
            if self.too_soon(relay, window):
                continue  # they can't have got here yet: keep waiting for a later clip
            explained |= self.answer(relay, seen) == "match"
        if is_crime(answer) and not explained:
            self.open_subject(seen, det)

    def failed(self, window: tuple[float, float], why: str) -> None:
        """The spotter gave no answer for this clip: relays it could have answered get "uncertain", not a
        false "not seen"."""
        self.blind = (window, why)
        for relay in [r for r in self.inbox if self.fits(r, window)]:
            self.cannot_tell(relay, window, why)

    def fits(self, relay: Relay, window: tuple[float, float]) -> bool:
        return check_timing(relay.left, window, relay.event["expected_arrival_s"], relay.event["from_camera"])[0]

    @staticmethod
    def too_soon(relay: Relay, window: tuple[float, float]) -> bool:
        return window[1] - relay.left[0] < arrival_bounds(relay.event["expected_arrival_s"])[0]

    def receive(self, relay: Relay) -> None:
        self.inbox.append(relay)
        # Answers are per clip, so the suspect may have passed here before the relay went out.
        if self.last and self.fits(relay, self.last.window):
            self.answer(relay, self.last)
        elif self.blind and self.fits(relay, self.blind[0]):
            self.cannot_tell(relay, *self.blind)

    def cannot_tell(self, relay: Relay, window: tuple[float, float], why: str) -> None:
        self.inbox.remove(relay)
        r = relay.event
        self.net.event("agent_verdict", "ver", max(r["ts"], window[1]), agent_id=self.agent_id,
                       camera_id=self.camera_id, subject_id=r["subject_id"], decision="uncertain",
                       confidence=PRIOR, evidence_event_ids=[r["event_id"]],
                       reason=_short(f"No spotter answer for this clip ({why}); can't tell.", 300))

    def answer(self, relay: Relay, seen: Sighting) -> str:
        r = relay.event
        j = judge(relay.features, seen.answer, relay.left, seen.window, r["expected_arrival_s"],
                  r["from_camera"], relay.weak)
        self.inbox.remove(relay)
        ts = max(r["ts"], seen.window[1])
        verdict = self.net.event("agent_verdict", "ver", ts, agent_id=self.agent_id, camera_id=self.camera_id,
                                 subject_id=r["subject_id"], decision=j.decision, confidence=j.confidence,
                                 reason=j.reason, evidence_event_ids=[r["event_id"], seen.detection_id])
        if j.keep_following and (j.decision == "match" or self.net.follow_uncertain):
            matched = j.decision == "match"
            word = "Confirmed" if matched else "Possibly seen"
            what = seen.answer.get("what_happened") or ""
            # A "possible" relay cites only the verdict: citing the detection would show this camera as a
            # sighting of the subject (the dashboard tags every detection a relay cites).
            self.send(r["subject_id"], r.get("activity", "none"),
                      merge(relay.features, features(seen.answer)) if matched else relay.features,
                      weak=[] if matched else relay.weak + [(self.camera_id, j.sighting)],
                      left=seen.window, ts=ts,
                      evidence=[verdict["event_id"], seen.detection_id] if matched else [verdict["event_id"]],
                      confidence=j.confidence, summary=f"{word} at {self.camera_id}: {what}".strip().rstrip(":"),
                      basis="match" if matched else "possible")
        return j.decision

    def open_subject(self, seen: Sighting, det: dict) -> None:
        activity = activity_of(seen.answer)
        what = seen.answer.get("what_happened") or ""
        self.send(self.net.new_id("subj"), activity, features(seen.answer), weak=[], left=seen.window,
                  ts=det["ts"], evidence=[det["event_id"]], confidence=UNSCORED_CONFIDENCE,
                  summary=f"{ACTIVITY_WORDS[activity]} at {self.camera_id}: {what}".strip().rstrip(":"),
                  basis="crime", confidence_known=False)

    def send(self, subject_id: str, activity: str, feats: dict, *, weak: list, left: tuple[float, float],
             ts: float, evidence: list[str], confidence: float, summary: str, basis: str,
             confidence_known: bool = True) -> None:
        """Relay the subject to every neighbor it hasn't reached yet (so never back where it came from)."""
        reached = self.net.reached.setdefault(subject_id, set())
        reached.add(self.camera_id)
        targets = [to for to in self.links if to in self.net.agents and to not in reached]
        reached.update(targets)  # before any delivery: a delivery can relay onward straight away
        extra = {} if confidence_known else {"confidence_known": False}
        relays = []
        for to in targets:
            link = self.links[to]
            travel = link.get("travel_time_s")
            event = self.net.event("relay", "rel", ts, from_camera=self.camera_id, to_camera=to,
                                   subject_id=subject_id, summary=_short(summary, SUMMARY_MAX),
                                   appearance=appearance_text(feats), direction=link.get("direction"),
                                   activity=activity, confidence=confidence, expected_arrival_s=travel,
                                   evidence_event_ids=evidence, basis=basis, **extra)
            relays.append((to, Relay(event, feats, left, weak, self.net.deadline(to, left, travel))))
        for to, relay in relays:
            self.net.agents[to].receive(relay)

    def expire(self, now: float) -> None:
        for relay in [r for r in self.inbox if r.deadline <= now]:
            self.inbox.remove(relay)
            r = relay.event
            waited = relay.deadline - relay.left[1]
            self.net.event("agent_verdict", "ver", relay.deadline, agent_id=self.agent_id,
                           camera_id=self.camera_id, subject_id=r["subject_id"], decision="no_match",
                           confidence=round(1 - PRIOR, 2), evidence_event_ids=[r["event_id"]],
                           reason=f"Not seen at {self.camera_id} within {waited:.0f} s of {r['from_camera']}.")


class Network:
    """All camera agents of one site; makes their event ids and works out relay deadlines."""

    def __init__(self, cameras: list[dict], emit: Callable[[dict], None], *, tag: str | None = None,
                 run_id: str | None = None, schedule: dict[str, list[tuple[float, float]]] | None = None,
                 detection_extra: dict | None = None, follow_uncertain: bool = False):
        """schedule: each camera's clip windows (run clock), so a relay waits for a clip still playing.
        detection_extra: fields added to every detection (e.g. spotter_model).
        follow_uncertain: opt-in; also relay onward after an uncertain sighting of someone running
        (default: only after a match, as the contract says)."""
        self.emit = emit
        self.follow_uncertain = follow_uncertain
        self.reached: dict[str, set[str]] = {}  # subject_id -> cameras it was opened at or relayed to
        self.tag = tag or "a" + secrets.token_hex(2)  # det_<tag>_1: a restart can't reuse another run's ids
        self.run_id = run_id
        self.schedule = schedule or {}
        self.detection_extra = detection_extra or {}
        self.counts: Counter = Counter()
        self.agents = {c["camera_id"]: CameraAgent(c, self) for c in cameras}

    def new_id(self, prefix: str) -> str:
        self.counts[prefix] += 1
        return f"{prefix}_{self.tag}_{self.counts[prefix]}"

    def event(self, kind: str, prefix: str, ts: float, **fields) -> dict:
        event = {"type": kind, "schema_version": SCHEMA_VERSION, "event_id": self.new_id(prefix),
                 "ts": round(ts, 3)}
        if self.run_id:
            event["run_id"] = self.run_id
        event.update(source=SOURCE, **fields)
        self.emit(event)
        return event

    def detection(self, camera_id: str, answer: dict, window: tuple[float, float]) -> dict:
        n = self.new_id("det")
        event = to_detection(answer, event_id=n, track_id="trk" + n.removeprefix("det"), camera_id=camera_id,
                             ts=window[1], window=window, run_id=self.run_id, extra=self.detection_extra)
        self.emit(event)
        return event

    def deadline(self, camera_id: str, left: tuple[float, float], travel_s: float | None) -> float:
        """Latest plausible arrival; later if a clip of that camera covering the arrival is still to finish."""
        low, high = arrival_bounds(travel_s)
        earliest, latest = left[0] + low, left[1] + high
        ends = [t1 for t0, t1 in self.schedule.get(camera_id, ()) if t0 <= latest and t1 >= earliest]
        return max([latest, *ends])

    def on_answer(self, camera_id: str, answer: dict, window: tuple[float, float]) -> None:
        self.agents[camera_id].see(answer, window)

    def on_failure(self, camera_id: str, window: tuple[float, float], why: str) -> None:
        self.agents[camera_id].failed(window, why)

    def next_deadline(self) -> float | None:
        deadlines = [r.deadline for a in self.agents.values() for r in a.inbox]
        return min(deadlines) if deadlines else None

    def expire(self, now: float) -> None:
        for agent in self.agents.values():
            agent.expire(now)
