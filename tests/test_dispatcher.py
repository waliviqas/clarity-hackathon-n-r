import pytest

from dispatcher import Camera, CameraGraph, Dispatcher, Event, RuleConfig, Station
from dispatcher.rules import gate, group_events
from dispatcher.models import Incident
from dispatcher.verify import verify

CFG = RuleConfig()


@pytest.fixture
def graph():
    cams = [Camera(f"c{i}", f"Cam {i}") for i in range(1, 6)]
    edges = [("c1", "c2", 1), ("c2", "c3", 1), ("c3", "c4", 1), ("c4", "c5", 1)]
    return CameraGraph(cams, edges)


def ev(eid, cam, t, label, conf=0.9):
    return Event(eid, cam, float(t), label, conf)


GOOD = {"decision": "dispatch", "priority": 4, "incident_type": "fight",
        "location_camera_id": "c2", "summary": "Fight.", "cited_event_ids": ["a", "b"]}


class Fake:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


# --- grouping ---------------------------------------------------------------

def test_nearby_events_in_window_merge(graph):
    incs = group_events([ev("a", "c1", 0, "fight"), ev("b", "c2", 30, "fight")], graph, CFG)
    assert len(incs) == 1


def test_far_cameras_stay_separate(graph):
    incs = group_events([ev("a", "c1", 0, "fight"), ev("b", "c5", 10, "fight")], graph, CFG)
    assert len(incs) == 2


def test_time_gap_splits(graph):
    incs = group_events([ev("a", "c1", 0, "fight"), ev("b", "c1", 500, "fight")], graph, CFG)
    assert len(incs) == 2


# --- gate -------------------------------------------------------------------

def test_gate_clear_dispatch():
    assert gate(Incident("i", [ev("a", "c1", 0, "weapon", 0.95)]), CFG) == "dispatch"


def test_gate_dismiss_low_severity():
    assert gate(Incident("i", [ev("a", "c1", 0, "loitering", 0.99)]), CFG) == "dismiss"


def test_gate_never_dismisses_high_severity_even_if_weak():
    assert gate(Incident("i", [ev("a", "c1", 0, "weapon", 0.2)]), CFG) == "ambiguous"


def test_gate_mixed_labels_ambiguous():
    inc = Incident("i", [ev("a", "c1", 0, "fight", 0.95), ev("b", "c2", 5, "fall", 0.95)])
    assert gate(inc, CFG) == "ambiguous"


# --- verifier ---------------------------------------------------------------

INC = Incident("i", [ev("a", "c1", 0, "fight"), ev("b", "c2", 5, "fall")])


def test_verify_accepts_grounded():
    assert verify(GOOD, INC) == []


@pytest.mark.parametrize("patch,needle", [
    ({"cited_event_ids": ["a", "zzz"]}, "not in this incident"),
    ({"location_camera_id": "c9"}, "location_camera_id"),
    ({"incident_type": "weapon"}, "not supported"),
    ({"priority": 5}, "exceeds evidence"),
    ({"cited_event_ids": []}, "at least one"),
])
def test_verify_rejects(patch, needle):
    errs = verify({**GOOD, **patch}, INC)
    assert any(needle in e for e in errs), errs


def test_verify_missing_fields():
    assert "missing fields" in verify({"decision": "dispatch"}, INC)[0]


# --- dispatcher cascade -----------------------------------------------------

AMBIG = [ev("a", "c1", 0, "fight", 0.6), ev("b", "c2", 5, "fall", 0.7)]


def test_clear_case_skips_model(graph):
    llm = Fake()
    out = Dispatcher(graph, llm).process([ev("a", "c1", 0, "weapon", 0.95)])
    assert out[0].route == "rules" and out[0].decision == "dispatch" and llm.calls == 0


def test_revision_loop_recovers(graph):
    bad = {**GOOD, "cited_event_ids": ["ghost"]}
    llm = Fake(bad, GOOD)
    out = Dispatcher(graph, llm).process(AMBIG)[0]
    assert out.route == "model" and out.model_calls == 2 and out.decision == "dispatch"


def test_persistent_hallucination_falls_back_to_review(graph):
    bad = {**GOOD, "incident_type": "weapon"}
    out = Dispatcher(graph, Fake(bad, bad)).process(AMBIG)[0]
    assert out.route == "fallback" and out.decision == "monitor" and out.needs_review
    assert out.verifier_errors


def test_model_exception_falls_back(graph):
    out = Dispatcher(graph, Fake(TimeoutError("slow"))).process(AMBIG)[0]
    assert out.route == "fallback" and "TimeoutError" in out.verifier_errors[0]


def test_no_model_falls_back(graph):
    out = Dispatcher(graph, None).process(AMBIG)[0]
    assert out.route == "fallback" and out.decision == "monitor"


def test_nearest_station_assigned_on_dispatch(graph):
    stations = [Station("near", "c2"), Station("far", "c5")]
    out = Dispatcher(graph, stations=stations).process([ev("a", "c1", 0, "weapon", 0.95)])[0]
    assert out.station_id == "near"
