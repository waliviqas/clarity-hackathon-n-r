"""Dispatcher tests. Fixtures mirror contracts/examples/*.json (v0.1)."""
import json
from pathlib import Path

import pytest

from dispatcher import CameraGraph, Dispatcher, RuleConfig, SubjectCase
from dispatcher.rules import gate, incident_type, path, predicted_next, subject_appearance
from dispatcher.verify import verify

CFG = RuleConfig()

# contracts v0.1 cameras.json shape; cam_05 is a junction with a north exit and an east decoy.
CAMERAS = {
    "schema_version": "0.1", "site_id": "test_site",
    "cameras": [
        {"camera_id": "cam_03", "name": "North hallway", "site_xy": {"x": 0.25, "y": 0.4},
         "neighbors": [{"camera_id": "cam_05", "travel_time_s": 40, "direction": "north"}],
         "source": {"kind": "replay", "uri": "x"}},
        {"camera_id": "cam_05", "name": "Junction", "site_xy": {"x": 0.3, "y": 0.1},
         "neighbors": [{"camera_id": "cam_03", "travel_time_s": 40, "direction": "south"},
                       {"camera_id": "cam_08", "travel_time_s": 30, "direction": "north"},
                       {"camera_id": "cam_06", "travel_time_s": 30, "direction": "east"}],
         "source": {"kind": "replay", "uri": "x"}},
        {"camera_id": "cam_06", "name": "Decoy exit", "neighbors": [], "source": {"kind": "replay", "uri": "x"}},
        {"camera_id": "cam_08", "name": "North exit", "neighbors": [], "source": {"kind": "replay", "uri": "x"}},
    ],
}


@pytest.fixture
def graph():
    return CameraGraph.from_config(CAMERAS)


def hdr(kind, eid, ts):
    return {"type": kind, "schema_version": "0.1", "event_id": eid, "ts": ts}


def det(eid, cam, ts, activity="none", conf=None, appearance="male, grey hoodie, dark pants", direction="north"):
    return {**hdr("detection", eid, ts), "camera_id": cam, "track_id": f"trk_{eid}", "label": "person",
            "confidence": 0.9, "bbox": None, "activity": activity, "activity_confidence": conf,
            "appearance": appearance, "direction": direction}


def rel(eid, ts, frm, to, subj, ev, activity=None, direction="north"):
    m = {**hdr("relay", eid, ts), "from_camera": frm, "to_camera": to, "subject_id": subj, "summary": "s",
         "appearance": "male, grey hoodie, dark pants", "direction": direction, "confidence": 0.82,
         "expected_arrival_s": 40, "evidence_event_ids": ev}
    if activity:
        m["activity"] = activity
    return m


def ver(eid, ts, cam, subj, decision, ev):
    return {**hdr("agent_verdict", eid, ts), "agent_id": f"agent_{cam}", "camera_id": cam, "subject_id": subj,
            "decision": decision, "confidence": 0.88, "reason": "r", "evidence_event_ids": ev}


def op(eid, ts, inc, action):
    return {**hdr("operator_action", eid, ts), "incident_id": inc, "action": action, "note": None}


# The contract's own example flow: purse snatch at 0.74 at cam_03, matched at cam_05.
DOC = [
    det("det_8f2a", "cam_03", 1734.2, "purse_snatch", 0.74),
    rel("rel_1c9d", 1736.0, "cam_03", "cam_05", "subj_7", ["det_8f2a"], activity="purse_snatch"),
    det("det_9e11", "cam_05", 1775.9),
    ver("ver_44b0", 1776.5, "cam_05", "subj_7", "match", ["rel_1c9d", "det_9e11"]),
]

GOOD = {"status": "tracking", "priority": "low",
        "recommendation": "Send a guard toward cam_08; check on the victim near cam_03.",
        "reason": "Purse snatch at cam_03, subject confirmed moving north at cam_05.",
        "evidence_event_ids": ["det_8f2a", "rel_1c9d", "ver_44b0"]}


def case_from(msgs, subj="subj_7"):
    c = SubjectCase(subj)
    for m in msgs:
        c.events[m["event_id"]] = m
    return c


class Fake:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


# --- contract: dispatch v0.1 ------------------------------------------------

DISPATCH_REQUIRED = {"type", "schema_version", "event_id", "ts", "incident_id", "subject_id", "incident_type",
                     "status", "priority", "path", "predicted_next", "recommendation", "reason",
                     "evidence_event_ids", "requires_human_confirm"}
ACTIVITIES = {"stabbing", "fistfight", "purse_snatch", "none"}
SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "schemas" / "dispatch.schema.json"


def assert_dispatch_contract(msg):
    assert DISPATCH_REQUIRED <= set(msg), DISPATCH_REQUIRED - set(msg)
    assert msg["type"] == "dispatch" and msg["schema_version"] == "0.1"
    assert msg["event_id"].startswith("dsp_") and msg["incident_id"].startswith("inc_")
    assert msg["subject_id"].startswith("subj_")
    assert msg["incident_type"] in ACTIVITIES
    assert msg["status"] in {"tracking", "alert", "resolved"} and msg["priority"] in {"low", "medium", "high"}
    assert all({"camera_id", "ts"} <= set(p) for p in msg["path"])
    assert all(0 <= p["probability"] <= 1 for p in msg["predicted_next"])
    assert len(msg["recommendation"]) <= 300 and len(msg["reason"]) <= 500
    assert isinstance(msg["requires_human_confirm"], bool)
    if SCHEMA.exists():  # official schema lands with Mina's contracts on main
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.validate(msg, json.loads(SCHEMA.read_text()))


def test_every_dispatch_meets_contract(graph):
    d = Dispatcher(graph, Fake(GOOD))
    out = d.process(DOC + [op("op_01", 1790.0, "inc_1", "confirm")])
    out += Dispatcher(graph).process([det("det_s1", "cam_03", 10, "stabbing", 0.95),
                                      rel("rel_s1", 11, "cam_03", "cam_05", "subj_2", ["det_s1"])])
    assert out
    for msg in out:
        assert_dispatch_contract(msg)


def test_doc_example_fills_contract_fields(graph):
    last = Dispatcher(graph, Fake(GOOD)).process(DOC)[-1]
    assert last["incident_type"] == "purse_snatch"
    assert last["subject_appearance"] == "male, grey hoodie, dark pants"
    assert last["path"] == [{"camera_id": "cam_03", "ts": 1734.2, "event_id": "det_8f2a"},
                            {"camera_id": "cam_05", "ts": 1776.5, "event_id": "ver_44b0"}]
    assert last["requires_human_confirm"] is True


# --- rules ------------------------------------------------------------------

def test_activity_none_string_is_not_an_incident(graph):
    msgs = [det("det_1", "cam_03", 0, "none", 0.99), rel("rel_1", 1, "cam_03", "cam_05", "subj_1", ["det_1"])]
    assert gate(case_from(msgs, "subj_1"), CFG) == "ignore"
    assert Dispatcher(graph, Fake(GOOD)).process(msgs) == []


def test_gate_clear_alert():
    assert gate(case_from([det("det_1", "cam_03", 0, "stabbing", 0.95)]), CFG) == "alert"


def test_gate_never_ignores_high_severity_even_if_weak():
    assert gate(case_from([det("det_1", "cam_03", 0, "stabbing", 0.2)]), CFG) == "ambiguous"


def test_gate_uncertain_verdict_makes_ambiguous():
    msgs = [det("det_1", "cam_03", 0, "fistfight", 0.95), ver("ver_1", 5, "cam_05", "subj_7", "uncertain", [])]
    assert gate(case_from(msgs), CFG) == "ambiguous"


def test_doc_example_is_ambiguous():
    assert gate(case_from(DOC), CFG) == "ambiguous"


def test_incident_type_prefers_most_severe_and_falls_back_to_relay():
    assert incident_type(case_from([det("det_1", "cam_03", 0, "fistfight", 0.9),
                                    det("det_2", "cam_03", 1, "stabbing", 0.6)])) == "stabbing"
    assert incident_type(case_from([rel("rel_1", 0, "cam_03", "cam_05", "subj_7", [], activity="fistfight")])) \
        == "fistfight"
    assert incident_type(case_from([det("det_1", "cam_03", 0)])) == "none"


def test_subject_appearance_is_latest():
    msgs = [det("det_1", "cam_03", 0, appearance="red jacket"), det("det_2", "cam_05", 5, appearance="red jacket, cap")]
    assert subject_appearance(case_from(msgs)) == "red jacket, cap"


def test_prediction_favors_direction_of_travel_over_decoy(graph):
    c = case_from(DOC)
    pred = predicted_next(c, path(c), graph, CFG)
    assert pred[0]["camera_id"] == "cam_08" and pred[0]["probability"] == 0.75  # north exit, not east decoy


def test_prediction_weights_pending_relay(graph):
    msgs = DOC + [rel("rel_x", 1780.0, "cam_05", "cam_06", "subj_7", ["det_9e11"], direction="east")]
    c = case_from(msgs)
    assert predicted_next(c, path(c), graph, CFG)[0]["camera_id"] == "cam_06"


def test_wali_predict_next_is_used_and_filtered(graph):
    calls = []

    def predict_next(camera_id, direction):
        calls.append((camera_id, direction))
        return [{"camera_id": "cam_06", "probability": 0.6}, {"camera_id": "cam_99", "probability": 0.4}]

    last = Dispatcher(graph, Fake(GOOD), predict_next=predict_next).process(DOC)[-1]
    assert calls[-1] == ("cam_05", "north")
    assert last["predicted_next"] == [{"camera_id": "cam_06", "probability": 0.6}]  # unknown camera dropped


def test_broken_predict_next_falls_back(graph):
    def predict_next(camera_id, direction):
        raise RuntimeError("graph bug")

    d = Dispatcher(graph, Fake(GOOD), predict_next=predict_next)
    assert d.process(DOC)[-1]["predicted_next"][0]["camera_id"] == "cam_08"
    assert d.stats["predict_next_errors"] >= 1


# --- verifier ---------------------------------------------------------------

KNOWN = {"cam_03", "cam_05", "cam_06", "cam_08"}


def test_verify_accepts_grounded():
    assert verify(GOOD, case_from(DOC), KNOWN) == []


@pytest.mark.parametrize("patch,needle", [
    ({"evidence_event_ids": ["det_8f2a", "det_ghost"]}, "not in this subject"),
    ({"evidence_event_ids": []}, "at least one"),
    ({"recommendation": "Send officer to cam_99"}, "cameras not in this case"),
    ({"evidence_event_ids": ["det_8f2a"], "priority": "medium"}, "exceeds"),  # purse_snatch caps at low
    ({"status": "alert", "evidence_event_ids": ["det_9e11"]}, "actual activity"),
])
def test_verify_rejects(patch, needle):
    errs = verify({**GOOD, **patch}, case_from(DOC), KNOWN)
    assert any(needle in e for e in errs), errs


def test_verify_requires_heading_toward_intercept():
    back_to_scene = {**GOOD, "recommendation": "Send an officer to cam_03 to secure the area."}
    errs = verify(back_to_scene, case_from(DOC), KNOWN, intercept="cam_08")
    assert any("send officers to cam_08" in e for e in errs), errs
    assert verify(GOOD, case_from(DOC), KNOWN, intercept="cam_08") == []


def test_verify_enforces_contract_lengths():
    errs = verify({**GOOD, "reason": "x" * 501}, case_from(DOC), KNOWN)
    assert any("reason longer" in e for e in errs), errs


def test_proposal_schema_has_no_string_length_limits():
    from dispatcher.llm import PROPOSAL_SCHEMA  # maxLength made vLLM 0.11 constrained decoding ~8x slower
    assert not any("maxLength" in prop for prop in PROPOSAL_SCHEMA["properties"].values())


def test_verify_follows_relay_to_detection_for_severity():
    assert verify({**GOOD, "evidence_event_ids": ["rel_1c9d"]}, case_from(DOC), KNOWN) == []


# --- dispatcher flow --------------------------------------------------------

def test_team_priorities():
    from dispatcher.rules import activity_severity, priority_for
    assert [priority_for(activity_severity(a)) for a in ("stabbing", "fistfight", "purse_snatch", "none")] ==         ["high", "medium", "low", "low"]


def test_only_stabbing_auto_alerts_by_rules():
    assert gate(case_from([det("det_1", "cam_03", 0, "fistfight", 0.99)]), CFG) == "ambiguous"
    assert gate(case_from([det("det_1", "cam_03", 0, "purse_snatch", 0.99)]), CFG) == "ambiguous"


def test_clear_alert_skips_model(graph):
    llm = Fake(GOOD)
    out = Dispatcher(graph, llm).process([det("det_1", "cam_03", 0, "stabbing", 0.95),
                                          rel("rel_1", 1, "cam_03", "cam_05", "subj_1", ["det_1"])])
    assert out[0]["status"] == "alert" and out[0]["priority"] == "high" and llm.calls == 0


def test_revision_loop_recovers(graph):
    early = {**GOOD, "recommendation": "Send a guard to cam_05; check on the victim near cam_03.",
             "evidence_event_ids": ["det_8f2a", "rel_1c9d"]}
    d = Dispatcher(graph, Fake({**early, "evidence_event_ids": ["det_ghost"]}, early))
    d.process(DOC[:2])
    assert d.audit[0]["route"] == "model" and d.audit[0]["model_calls"] == 2


def test_persistent_hallucination_falls_back(graph):
    d = Dispatcher(graph, Fake({**GOOD, "recommendation": "Go to cam_99"}))
    out = d.process(DOC[:2])
    assert out[0]["status"] == "tracking" and out[0]["recommendation"].startswith("Operator review")
    assert d.audit[0]["route"] == "fallback" and d.audit[0]["verifier_errors"]


def test_invalid_json_is_retried(graph):
    early = {**GOOD, "recommendation": "Send a guard to cam_05.", "evidence_event_ids": ["det_8f2a", "rel_1c9d"]}
    d = Dispatcher(graph, Fake(ValueError("Expecting ',' delimiter"), early))
    d.process(DOC[:2])
    assert d.audit[0]["route"] == "model" and d.audit[0]["model_calls"] == 2


def test_model_exception_falls_back(graph):
    d = Dispatcher(graph, Fake(TimeoutError("slow")))
    d.process(DOC[:2])
    assert d.audit[0]["route"] == "fallback" and "TimeoutError" in d.audit[0]["verifier_errors"][0]


def test_detection_arriving_after_relay_is_attached(graph):
    d = Dispatcher(graph, None)
    out = d.process([DOC[1], DOC[0]])  # relay first, then the detection it cites
    assert out and d.cases["subj_7"].events.get("det_8f2a")


def test_unchanged_state_is_not_re_emitted(graph):
    d = Dispatcher(graph, Fake(GOOD))
    d.process(DOC)
    n = len(d.audit)
    d.ingest(det("det_other", "cam_06", 1800.0))  # unrelated detection
    assert len(d.audit) == n


def test_operator_confirm_and_dismiss(graph):
    d = Dispatcher(graph, Fake(GOOD))
    d.process(DOC)
    conf = d.ingest(op("op_01", 1790.0, "inc_1", "confirm"))[0]
    assert conf["status"] == "alert" and conf["requires_human_confirm"] is False
    dis = d.ingest(op("op_02", 1795.0, "inc_1", "dismiss"))[0]
    assert dis["status"] == "resolved"
    assert d.ingest(ver("ver_9", 1800.0, "cam_08", "subj_7", "match", [])) == []  # dismissed: stays quiet


def test_rejects_wrong_schema_version(graph):
    d = Dispatcher(graph)
    assert d.ingest({**DOC[0], "schema_version": "0.2"}) == [] and d.stats["rejected"] == 1


# --- parallel incidents + bus-style polling ---------------------------------

import threading  # noqa: E402
import time  # noqa: E402


class SlowGrounded:
    """Thread-safe fake model: sleeps, tracks peak concurrency, answers from the prompt so the verifier passes."""

    def __init__(self, delay=0.2, delays=None):
        self.delay, self.delays = delay, delays or {}
        self.lock, self.in_flight, self.peak, self.calls = threading.Lock(), 0, 0, 0

    def complete_json(self, system, user, schema):
        case = json.loads(user.split("\n\n")[0].removeprefix("Case:\n"))
        with self.lock:
            self.in_flight += 1
            self.calls += 1
            self.peak = max(self.peak, self.in_flight)
        time.sleep(self.delays.get(case["subject_id"], self.delay))
        with self.lock:
            self.in_flight -= 1
        return {"status": "tracking", "priority": "low",
                "recommendation": f"Send officers to {case['send_officers_to']}.", "reason": "Moderate evidence.",
                "evidence_event_ids": [e["event_id"] for e in case["evidence"]]}


def three_incidents():
    out = []
    for n, subj in enumerate(["subj_1", "subj_2", "subj_3"], 1):
        out += [det(f"det_{n}", "cam_03", n, "purse_snatch", 0.7),
                rel(f"rel_{n}", n + 0.5, "cam_03", "cam_05", subj, [f"det_{n}"], activity="purse_snatch")]
    return out


def test_overlapping_incidents_call_model_in_parallel(graph):
    llm = SlowGrounded(delay=0.3)
    d = Dispatcher(graph, llm)
    t0 = time.perf_counter()
    out = d.process(three_incidents())
    elapsed = time.perf_counter() - t0
    assert len(out) == 3 and llm.calls == 3
    assert llm.peak == 3 and elapsed < 0.8  # sequential would be >= 0.9 s
    assert all(a["route"] == "model" for a in d.audit)


def test_incident_ids_follow_arrival_not_completion(graph):
    llm = SlowGrounded(delays={"subj_1": 0.3, "subj_2": 0.1, "subj_3": 0.0})  # finish in reverse order
    out = Dispatcher(graph, llm).process(three_incidents())
    assert [(m["subject_id"], m["incident_id"]) for m in out] == \
        [("subj_1", "inc_1"), ("subj_2", "inc_2"), ("subj_3", "inc_3")]


def test_batch_evaluates_each_incident_once(graph):
    llm = SlowGrounded(delay=0)
    Dispatcher(graph, llm).process(DOC)  # relay + verdict for subj_7 in one batch
    assert llm.calls == 1


def test_repolled_events_are_skipped(graph):
    """Mina's fetch() has an inclusive since_ts and is polled with a lookback, so events repeat."""
    llm = SlowGrounded(delay=0)
    d = Dispatcher(graph, llm)
    d.process(DOC[:2])
    calls = llm.calls
    assert d.process(DOC[:2]) == [] and llm.calls == calls and d.stats["duplicate"] == 2
    d.process(DOC)  # lookback window: old + new events
    assert llm.calls == calls + 1


def test_operator_action_in_same_batch_as_first_evidence(graph):
    out = Dispatcher(graph, SlowGrounded(delay=0)).process(DOC + [op("op_01", 1790.0, "inc_1", "confirm")])
    assert out[-1]["status"] == "alert" and out[-1]["requires_human_confirm"] is False


def test_max_parallel_caps_concurrency(graph):
    llm = SlowGrounded(delay=0.1)
    Dispatcher(graph, llm, max_parallel=2).process(three_incidents())
    assert llm.peak == 2
