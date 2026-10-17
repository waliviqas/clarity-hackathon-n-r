import pytest

from dispatcher import CameraGraph, Dispatcher, RuleConfig, SubjectCase
from dispatcher.rules import gate, path, predicted_next
from dispatcher.verify import verify

CFG = RuleConfig()

CAMERAS = [
    {"camera_id": "cam_03", "name": "North entrance", "neighbors": [{"camera_id": "cam_05", "travel_time_s": 40}]},
    {"camera_id": "cam_05", "name": "Library", "neighbors": [{"camera_id": "cam_06", "travel_time_s": 30},
                                                             {"camera_id": "cam_08", "travel_time_s": 50}]},
    {"camera_id": "cam_06", "name": "Deck", "neighbors": []},
    {"camera_id": "cam_08", "name": "Gate", "neighbors": []},
]


@pytest.fixture
def graph():
    return CameraGraph.from_config(CAMERAS)


def hdr(kind, eid, ts):
    return {"type": kind, "schema_version": "0.1", "event_id": eid, "ts": ts}


def det(eid, cam, ts, activity=None, conf=None):
    return {**hdr("detection", eid, ts), "camera_id": cam, "track_id": f"trk_{eid}", "label": "person",
            "confidence": 0.9, "bbox": [0, 0, 0.1, 0.1], "activity": activity,
            "activity_confidence": conf, "appearance_id": f"app_{eid}"}


def rel(eid, ts, frm, to, subj, ev):
    return {**hdr("relay", eid, ts), "from_camera": frm, "to_camera": to, "subject_id": subj,
            "summary": "s", "confidence": 0.8, "expected_arrival_s": 40, "evidence_event_ids": ev}


def ver(eid, ts, cam, subj, decision, ev):
    return {**hdr("agent_verdict", eid, ts), "agent_id": f"agent_{cam}", "camera_id": cam, "subject_id": subj,
            "decision": decision, "confidence": 0.88, "reason": "r", "evidence_event_ids": ev}


# The schema doc's own example.
DOC = [
    det("det_8f2a", "cam_03", 1734.2, "abandon_package", 0.74),
    rel("rel_1c9d", 1736.0, "cam_03", "cam_05", "subj_7", ["det_8f2a"]),
    det("det_9e11", "cam_05", 1775.9),
    ver("ver_44b0", 1776.5, "cam_05", "subj_7", "match", ["rel_1c9d", "det_9e11"]),
]

GOOD = {"status": "tracking", "priority": "high", "recommendation": "Send officer to cam_08 area; secure package at cam_03",
        "reason": "Package left, subject moving north", "evidence_event_ids": ["det_8f2a", "rel_1c9d", "ver_44b0"]}


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


# --- path / prediction ------------------------------------------------------

def test_path_matches_doc_example():
    assert path(case_from(DOC)) == [{"camera_id": "cam_03", "ts": 1734.2}, {"camera_id": "cam_05", "ts": 1776.5}]


def test_predicted_next_excludes_visited_and_weights_pending_relay(graph):
    msgs = DOC + [rel("rel_x", 1780.0, "cam_05", "cam_08", "subj_7", ["det_9e11"])]
    c = case_from(msgs)
    pred = predicted_next(c, path(c), graph, CFG)
    assert [p["camera_id"] for p in pred] == ["cam_08", "cam_06"]
    assert pred[0]["probability"] == 0.75


# --- gate -------------------------------------------------------------------

def test_gate_ignores_no_activity():
    assert gate(case_from([det("det_1", "cam_03", 0), rel("rel_1", 1, "cam_03", "cam_05", "s", ["det_1"])]), CFG) == "ignore"


def test_gate_clear_alert():
    assert gate(case_from([det("det_1", "cam_03", 0, "weapon", 0.95)]), CFG) == "alert"


def test_gate_never_ignores_high_severity_even_if_weak():
    assert gate(case_from([det("det_1", "cam_03", 0, "weapon", 0.2)]), CFG) == "ambiguous"


def test_gate_uncertain_verdict_makes_ambiguous():
    msgs = [det("det_1", "cam_03", 0, "weapon", 0.95), ver("ver_1", 5, "cam_05", "s", "uncertain", [])]
    assert gate(case_from(msgs), CFG) == "ambiguous"


def test_doc_example_is_ambiguous():
    assert gate(case_from(DOC), CFG) == "ambiguous"


# --- verifier ---------------------------------------------------------------

KNOWN = {"cam_03", "cam_05", "cam_06", "cam_08"}


def test_verify_accepts_grounded():
    assert verify(GOOD, case_from(DOC), KNOWN) == []


@pytest.mark.parametrize("patch,needle", [
    ({"evidence_event_ids": ["det_8f2a", "det_ghost"]}, "not in this subject"),
    ({"evidence_event_ids": []}, "at least one"),
    ({"recommendation": "Send officer to cam_99"}, "cameras not in this case"),
    ({"evidence_event_ids": ["det_9e11"]}, "exceeds"),
    ({"status": "alert", "priority": "low", "evidence_event_ids": ["det_9e11"]}, "requires cited evidence"),
])
def test_verify_rejects(patch, needle):
    errs = verify({**GOOD, **patch}, case_from(DOC), KNOWN)
    assert any(needle in e for e in errs), errs


def test_verify_follows_relay_to_detection_for_severity():
    assert verify({**GOOD, "evidence_event_ids": ["rel_1c9d"]}, case_from(DOC), KNOWN) == []


# --- dispatcher end to end --------------------------------------------------

def test_doc_example_emits_dispatch_matching_schema(graph):
    d = Dispatcher(graph, Fake(GOOD))
    out = d.process(DOC)
    last = out[-1]
    assert last["type"] == "dispatch" and last["schema_version"] == "0.1"
    assert last["incident_id"] == "inc_1" and last["subject_id"] == "subj_7"
    assert last["path"] == [{"camera_id": "cam_03", "ts": 1734.2}, {"camera_id": "cam_05", "ts": 1776.5}]
    assert {p["camera_id"] for p in last["predicted_next"]} == {"cam_06", "cam_08"}
    assert last["requires_human_confirm"] is True
    assert last["status"] in ("tracking", "alert") and last["priority"] in ("low", "medium", "high")
    assert set(last) == {"type", "schema_version", "event_id", "ts", "incident_id", "subject_id", "status",
                         "priority", "path", "predicted_next", "recommendation", "reason",
                         "evidence_event_ids", "requires_human_confirm"}


def test_clear_alert_skips_model(graph):
    llm = Fake(GOOD)
    out = Dispatcher(graph, llm).process([det("det_1", "cam_03", 0, "weapon", 0.95),
                                          rel("rel_1", 1, "cam_03", "cam_05", "subj_1", ["det_1"])])
    assert out[0]["status"] == "alert" and out[0]["priority"] == "high" and llm.calls == 0


def test_no_activity_emits_nothing(graph):
    out = Dispatcher(graph, Fake(GOOD)).process([det("det_1", "cam_03", 0),
                                                 rel("rel_1", 1, "cam_03", "cam_05", "subj_1", ["det_1"])])
    assert out == []


def test_revision_loop_recovers(graph):
    early = {**GOOD, "recommendation": "Send officer to cam_05; secure package at cam_03",
             "evidence_event_ids": ["det_8f2a", "rel_1c9d"]}
    d = Dispatcher(graph, Fake({**early, "evidence_event_ids": ["det_ghost"]}, early))
    d.process(DOC[:2])
    assert d.audit[0]["route"] == "model" and d.audit[0]["model_calls"] == 2


def test_persistent_hallucination_falls_back(graph):
    bad = {**GOOD, "recommendation": "Go to cam_99"}
    d = Dispatcher(graph, Fake(bad))
    out = d.process(DOC[:2])
    assert out[0]["status"] == "tracking" and out[0]["recommendation"].startswith("Operator review")
    assert d.audit[0]["route"] == "fallback" and d.audit[0]["verifier_errors"]


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
    conf = d.ingest({**hdr("operator_action", "op_01", 1790.0), "incident_id": "inc_1", "action": "confirm"})[0]
    assert conf["status"] == "alert" and conf["requires_human_confirm"] is False
    dis = d.ingest({**hdr("operator_action", "op_02", 1795.0), "incident_id": "inc_1", "action": "dismiss"})[0]
    assert dis["status"] == "resolved"
    assert d.ingest(ver("ver_9", 1800.0, "cam_08", "subj_7", "match", [])) == []  # dismissed: stays quiet


def test_rejects_wrong_schema_version(graph):
    d = Dispatcher(graph)
    assert d.ingest({**DOC[0], "schema_version": "0.2"}) == [] and d.stats["rejected"] == 1
