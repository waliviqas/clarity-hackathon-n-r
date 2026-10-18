"""Camera agents end to end, without a bus: relays, verdicts, deadlines, the runner and answer files."""
import json
import tempfile
import unittest
from pathlib import Path

from agents.answers import load_answers
from agents.network import Network
from agents.run import Clip, Clock, run_timeline
from contracts.validate import check


def cam(camera_id, *links, uri=None, start=0.0):
    """links: (neighbor, travel_time_s, direction)."""
    return {"camera_id": camera_id, "name": camera_id,
            "neighbors": [{"camera_id": c, "travel_time_s": t, "direction": d} for c, t, d in links],
            "source": {"kind": "replay", "uri": uri or f"clips/{camera_id}.mp4", "start_ts": start}}


# cam_01 - cam_02 - cam_03, and cam_02 - cam_04 (a second exit), every link symmetric.
SITE = [cam("cam_01", ("cam_02", 3.0, "north")),
        cam("cam_02", ("cam_01", 3.0, "south"), ("cam_03", 6.0, "north"), ("cam_04", 5.0, "east")),
        cam("cam_03", ("cam_02", 6.0, "south")),
        cam("cam_04", ("cam_02", 5.0, "west"))]

LOOK = {"build": "slim", "shirt": "black hoodie", "pants": "dark grey pants", "hair": "curly dark"}
CRIME = {"what_happened": "grabs a phone and runs", "on_screen": "crime", "crime": "stealing", **LOOK}
FLEEING = {"what_happened": "someone runs past", "on_screen": "fleeing", "crime": "none", **LOOK}
NOBODY = {"what_happened": "empty street", "on_screen": "none", "crime": "none"}
STRANGER = {"what_happened": "a man walks by", "on_screen": "none", "crime": "none",
            "shirt": "white t-shirt", "pants": "blue jeans"}


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)

    def of(self, kind):
        return [e for e in self.events if e["type"] == kind]


def network(schedule=None):
    rec = Recorder()
    return Network(SITE, rec, tag="t", run_id="run_test", schedule=schedule), rec


class Relays(unittest.TestCase):
    def test_crime_opens_a_subject_and_relays_to_every_neighbor(self):
        net, rec = network()
        net.on_answer("cam_02", CRIME, (0.0, 8.0))
        det, = rec.of("detection")
        relays = rec.of("relay")
        self.assertEqual(det["activity"], "purse_snatch")
        self.assertEqual(sorted(r["to_camera"] for r in relays), ["cam_01", "cam_03", "cam_04"])
        for r in relays:
            self.assertEqual((r["subject_id"], r["activity"], r["evidence_event_ids"]),
                             ("subj_t_1", "purse_snatch", [det["event_id"]]))
            self.assertIs(r["confidence_known"], False)
        to_03 = next(r for r in relays if r["to_camera"] == "cam_03")
        self.assertEqual((to_03["expected_arrival_s"], to_03["direction"]), (6.0, "north"))

    def test_match_relays_onward_but_not_back(self):
        net, rec = network()
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        net.on_answer("cam_02", FLEEING, (9.0, 12.0))
        verdict, = rec.of("agent_verdict")
        first, *onward = rec.of("relay")
        det_02 = rec.of("detection")[1]
        self.assertEqual(verdict["decision"], "match")
        self.assertEqual(verdict["evidence_event_ids"], [first["event_id"], det_02["event_id"]])
        self.assertEqual(sorted(r["to_camera"] for r in onward), ["cam_03", "cam_04"])
        for r in onward:
            self.assertEqual(r["from_camera"], "cam_02")
            self.assertEqual(r["evidence_event_ids"], [verdict["event_id"], det_02["event_id"]])
            self.assertEqual(r["basis"], "match")

    def test_exit_matches_and_the_other_exit_does_not(self):
        net, rec = network()
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        net.on_answer("cam_02", FLEEING, (9.0, 12.0))
        net.on_answer("cam_03", FLEEING, (16.0, 20.0))
        net.on_answer("cam_04", STRANGER, (15.0, 19.0))
        decisions = {v["camera_id"]: v["decision"] for v in rec.of("agent_verdict")}
        self.assertEqual(decisions, {"cam_02": "match", "cam_03": "match", "cam_04": "no_match"})
        self.assertEqual(len(rec.of("relay")), 3)  # 01->02, 02->03, 02->04; dead ends send nothing

    def test_uncertain_runner_is_followed_unless_matches_only(self):
        runner = {"what_happened": "someone runs past", "on_screen": "fleeing", "crime": "none"}
        for follow, expected in ((True, ["cam_03", "cam_04"]), (False, [])):
            rec = Recorder()
            net = Network(SITE, rec, tag="t", follow_uncertain=follow)
            net.on_answer("cam_01", CRIME, (0.0, 8.0))
            net.on_answer("cam_02", runner, (9.0, 12.0))
            self.assertEqual(rec.of("agent_verdict")[0]["decision"], "uncertain")
            onward = [r for r in rec.of("relay") if r["from_camera"] == "cam_02"]
            self.assertEqual(sorted(r["to_camera"] for r in onward), expected)
            self.assertTrue(all(r["basis"] == "possible" for r in onward))

    def test_only_one_subject_for_one_suspect(self):
        net, rec = network()
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        net.on_answer("cam_02", {**CRIME, "what_happened": "same person, still grabbing"}, (9.0, 12.0))
        self.assertEqual({r["subject_id"] for r in rec.of("relay")}, {"subj_t_1"})

    def test_every_event_is_valid(self):
        net, rec = network()
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        net.on_answer("cam_02", FLEEING, (9.0, 12.0))
        net.on_answer("cam_04", NOBODY, (15.0, 19.0))
        net.expire(1000.0)
        self.assertGreater(len(rec.events), 6)
        for e in rec.events:
            self.assertEqual(check(e), [], e)
        self.assertEqual(len({e["event_id"] for e in rec.events}), len(rec.events))


class Deadlines(unittest.TestCase):
    def test_unanswered_relay_gets_a_no_match(self):
        net, rec = network()
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        deadline = net.next_deadline()
        self.assertEqual(deadline, 8.0 + 3.0 * 3 + 30)  # clip end + 3x the walk + 30 s
        net.expire(deadline - 1)
        self.assertEqual(rec.of("agent_verdict"), [])
        net.expire(deadline)
        verdict, = rec.of("agent_verdict")
        self.assertEqual((verdict["decision"], verdict["ts"]), ("no_match", deadline))
        self.assertIn("Not seen", verdict["reason"])
        self.assertIsNone(net.next_deadline())

    def test_waits_for_a_clip_still_playing(self):
        net, _ = network(schedule={"cam_02": [(20.0, 90.0)]})
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        self.assertEqual(net.next_deadline(), 90.0)

    def test_a_clip_too_early_for_the_walk_leaves_the_relay_open(self):
        net, rec = network()
        net.on_answer("cam_02", CRIME, (0.0, 8.0))
        net.on_answer("cam_04", FLEEING, (1.0, 2.0))  # over before anyone could cover the 5 s link
        self.assertEqual(rec.of("agent_verdict"), [])
        net.on_answer("cam_04", FLEEING, (9.0, 12.0))
        self.assertEqual([(v["camera_id"], v["decision"]) for v in rec.of("agent_verdict")], [("cam_04", "match")])

    def test_sighting_before_the_relay_is_still_checked(self):
        net, rec = network()
        net.on_answer("cam_02", FLEEING, (4.0, 7.0))  # cam_02's clip ends before cam_01's
        net.on_answer("cam_01", CRIME, (0.0, 8.0))
        verdict, = rec.of("agent_verdict")
        self.assertEqual((verdict["camera_id"], verdict["decision"], verdict["ts"]), ("cam_02", "match", 8.0))


class SpotterFailures(unittest.TestCase):
    def test_failed_clip_is_uncertain_not_unseen(self):
        for failure_first in (False, True):
            net, rec = network()
            if failure_first:
                net.on_failure("cam_02", (4.0, 7.0), "TimeoutError")
                net.on_answer("cam_01", CRIME, (0.0, 8.0))
            else:
                net.on_answer("cam_01", CRIME, (0.0, 8.0))
                net.on_failure("cam_02", (9.0, 12.0), "TimeoutError")
            verdict, = rec.of("agent_verdict")
            self.assertEqual((verdict["camera_id"], verdict["decision"]), ("cam_02", "uncertain"))
            self.assertIn("can't tell", verdict["reason"])
            self.assertEqual(check(verdict), [])
            self.assertEqual(len(rec.of("relay")), 1)  # nothing relayed onward from a camera that saw nothing
            self.assertIsNone(net.next_deadline())


class Runner(unittest.TestCase):
    def test_timeline_in_clip_order_with_deadlines(self):
        net, rec = network()
        clips = [Clip("cam_02", Path("x"), (9.0, 12.0)), Clip("cam_01", Path("x"), (0.0, 8.0))]
        answers = {"cam_01": CRIME, "cam_02": NOBODY}
        clips.sort(key=lambda c: c.window[1])
        run_timeline(clips, lambda c: answers[c.camera_id], net, Clock(0))
        kinds = [(e["type"], e.get("camera_id") or e.get("to_camera")) for e in rec.events]
        self.assertEqual(kinds[0], ("detection", "cam_01"))
        self.assertIn(("agent_verdict", "cam_02"), kinds)
        self.assertIsNone(net.next_deadline())  # cam_02 answered no_match; nothing left open

    def test_a_failed_spotter_call_does_not_stop_the_run(self):
        net, rec = network()
        clips = [Clip("cam_01", Path("x"), (0.0, 8.0)), Clip("cam_02", Path("x"), (9.0, 12.0))]

        def get_answer(clip):
            if clip.camera_id == "cam_02":
                raise RuntimeError("Spotter reply was cut off")
            return CRIME

        run_timeline(clips, get_answer, net, Clock(0))
        self.assertEqual([v["decision"] for v in rec.of("agent_verdict")], ["uncertain"])


class AnswerFiles(unittest.TestCase):
    def write(self, data):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, f)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return f.name

    def test_wali_eval_results_by_clip_name(self):
        cams = [cam("cam_01", uri="data/raw/staged/take1/clip8_cam1.mp4"),
                cam("cam_02", uri="data/raw/staged/take1/clip8_cam2.mp4")]
        path = self.write({"model": "base", "cameras": [
            {"clip": "clip8", "cam": "cam1", "answers": [CRIME, CRIME]},
            {"clip": "clip8", "cam": "cam2", "answers": [None, FLEEING]},
            {"clip": "clip1", "cam": "cam1", "answers": [NOBODY]}]})
        answers, model = load_answers(path, cams)
        self.assertEqual((answers, model), ({"cam_01": CRIME, "cam_02": FLEEING}, "base"))
        self.assertEqual(load_answers(path, cams, run=0)[0], {"cam_01": CRIME})  # run 0 failed at cam2

    def test_saved_and_bare_answers(self):
        cams = [cam("cam_01")]
        self.assertEqual(load_answers(self.write({"model": "ft", "answers": {"cam_01": CRIME, "cam_09": CRIME}}),
                                      cams), ({"cam_01": CRIME}, "ft"))
        self.assertEqual(load_answers(self.write({"cam_01": NOBODY}), cams), ({"cam_01": NOBODY}, None))


if __name__ == "__main__":
    unittest.main()
