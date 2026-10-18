"""The checker on cameras the spotter flagged (agents/combine.py, and its part of agents/run.py), with a fake
describe(): called only on flagged cameras, Wali's merge, clean fallbacks, --no-checker is the spotter alone as
before, and --save-answers files replay to the same events."""
import contextlib
import io
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agents.answers import save_answers
from agents.combine import DESCRIPTION_FIELDS, flagged, merge_answers, split_answer, spotter_only
from agents.network import Network
from agents.run import Clip, Clock, load_clips, main, run_timeline, start_live
from agents.tests.test_network import CRIME, FLEEING, NOBODY, SITE, Recorder, cam
from agents.tests.test_run import DESC, temp_dir
from contracts.validate import check

SPOTTED = {"cam_01": CRIME, "cam_02": FLEEING, "cam_03": NOBODY}  # what the fake spotter says per camera


def fake_spot(path, count):
    return SPOTTED[Path(path).stem]


def three_clips():
    return [Clip("cam_01", Path("cam_01.mp4"), (0.0, 8.0)), Clip("cam_02", Path("cam_02.mp4"), (9.0, 12.0)),
            Clip("cam_03", Path("cam_03.mp4"), (14.0, 20.0))]


def run_live(describe, check_limit_s=5.0):
    """The three clips through start_live + run_timeline (spotter answers from SPOTTED) -> recorded events."""
    rec = Recorder()
    clips = three_clips()
    get_answer = start_live(clips, fake_spot, 8, Clock(0), 5.0, describe, check_limit_s, "checker")
    run_timeline(clips, get_answer, Network(SITE, rec, tag="t"), Clock(0))
    return rec


def by_camera(rec):
    return {d["camera_id"]: d for d in rec.of("detection")}


class Merge(unittest.TestCase):
    def test_spotter_keeps_its_verdict_and_the_checker_gives_the_description(self):
        merged = merge_answers(CRIME, DESC, "checker")
        for field in ("what_happened", "on_screen", "crime"):
            self.assertEqual(merged[field], CRIME[field])
        self.assertEqual({f: merged[f] for f in DESCRIPTION_FIELDS}, DESC)
        self.assertEqual((merged["description_by"], merged["checker_model"]), ("checker", "checker"))
        self.assertEqual(merged["spotter_description"], {f: CRIME[f] for f in DESCRIPTION_FIELDS if f in CRIME})

    def test_a_field_the_checker_left_out_is_unknown(self):  # combine_gym: d.get(f, "")
        merged = merge_answers(CRIME, {"shirt": "red jacket"})
        self.assertEqual((merged["shirt"], merged["pants"], merged["build"]), ("red jacket", "", ""))
        self.assertNotIn("checker_model", merged)

    def test_split_gives_back_what_each_model_said(self):
        before = json.dumps(CRIME)
        merged = merge_answers(CRIME, DESC, "checker")
        self.assertEqual(json.dumps(CRIME), before)  # the spotter's answer isn't changed in place
        self.assertEqual(split_answer(merged), (CRIME, DESC))
        self.assertEqual(split_answer(spotter_only(CRIME, "TimeoutError")), (CRIME, None))
        self.assertEqual(split_answer(NOBODY), (NOBODY, None))

    def test_flagged_means_crime_or_fleeing(self):
        self.assertTrue(flagged(CRIME) and flagged(FLEEING) and flagged({"on_screen": " Crime "}))
        for answer in (NOBODY, {}, {"on_screen": None}, {"on_screen": "unknown"}):
            self.assertFalse(flagged(answer), answer)


class LiveChecker(unittest.TestCase):
    def test_describe_runs_only_on_flagged_cameras_with_the_same_frames(self):
        calls, lock = [], threading.Lock()

        def describe(path, count):
            with lock:
                calls.append((Path(path).stem, count))
            return DESC

        clips = three_clips()
        with self.assertLogs("agents", "INFO"):
            get_answer = start_live(clips, fake_spot, 8, Clock(0), 5.0, describe, 5.0, "checker")
            answers = {c.camera_id: get_answer(c) for c in clips}
        self.assertEqual(sorted(calls), [("cam_01", 8), ("cam_02", 8)])
        self.assertEqual(answers["cam_01"], merge_answers(CRIME, DESC, "checker"))
        self.assertEqual(answers["cam_02"], merge_answers(FLEEING, DESC, "checker"))
        self.assertEqual(answers["cam_03"], NOBODY)  # not flagged: the spotter's answer, untouched

    def test_the_checkers_description_reaches_detections_and_relays(self):
        with self.assertLogs("agents", "INFO"):
            rec = run_live(lambda path, count: DESC)
        dets = by_camera(rec)
        crime = dets["cam_01"]
        self.assertEqual((crime["description_by"], crime["checker_model"]), ("checker", "checker"))
        self.assertEqual((crime["spotter"], crime["checker"]), (CRIME, DESC))  # receipts: what each model said
        self.assertIn("red jacket", crime["appearance"])
        self.assertNotIn("black hoodie", crime["appearance"])
        self.assertEqual(crime["activity"], "purse_snatch")  # the spotter's crime
        self.assertEqual(dets["cam_03"]["spotter"], NOBODY)
        self.assertFalse({"description_by", "checker", "checker_model"} & dets["cam_03"].keys())
        first = next(r for r in rec.of("relay") if r["from_camera"] == "cam_01")
        self.assertIn("red jacket", first["appearance"])
        verdict = next(v for v in rec.of("agent_verdict") if v["camera_id"] == "cam_02")
        self.assertEqual(verdict["decision"], "match")  # both flagged cameras described by the checker
        self.assertEqual([check(e) for e in rec.events], [[] for _ in rec.events])

    def test_a_checker_error_keeps_the_spotters_fields_with_one_line(self):
        def describe(path, count):
            if "cam_01" in path:
                raise RuntimeError("Checker reply was cut off or empty (finish_reason=length) for cam_01.mp4")
            return DESC

        with self.assertLogs("agents", "INFO") as logs:
            rec = run_live(describe)
        dets = by_camera(rec)
        failed = dets["cam_01"]
        self.assertEqual((failed["description_by"], failed["checker_error"]), ("spotter", "RuntimeError"))
        self.assertNotIn("checker", failed)
        self.assertEqual(failed["spotter"], CRIME)
        self.assertIn("black hoodie", failed["appearance"])
        self.assertEqual(dets["cam_02"]["description_by"], "checker")  # the other cameras still get it
        lines = [line for line in logs.output if "no checker description" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn("cam_01", lines[0])
        self.assertEqual([check(e) for e in rec.events], [[] for _ in rec.events])

    def test_a_slow_checker_times_out_and_the_run_carries_on(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def describe(path, count):
            if "cam_02" in path:
                release.wait(30)  # a hung vLLM call
            return DESC

        began = time.monotonic()
        with self.assertLogs("agents", "INFO") as logs:
            rec = run_live(describe, check_limit_s=0.3)
        self.assertLess(time.monotonic() - began, 5)
        slow = by_camera(rec)["cam_02"]
        self.assertEqual((slow["description_by"], slow["checker_error"]), ("spotter", "TimeoutError"))
        self.assertEqual(sum("cam_02: no checker description (TimeoutError" in line for line in logs.output), 1)
        self.assertEqual(len(rec.of("detection")), 3)

    def test_a_reply_that_is_not_a_json_object_keeps_the_spotters_fields(self):
        for bad in (None, "red jacket", ["red jacket"]):
            with self.assertLogs("agents", "INFO") as logs:
                rec = run_live(lambda path, count: bad)
            for camera in ("cam_01", "cam_02"):
                det = by_camera(rec)[camera]
                self.assertEqual((det["description_by"], det["checker_error"]), ("spotter", "TypeError"), bad)
            self.assertEqual(sum("not a JSON object" in line for line in logs.output), 2)


def three_cameras(test) -> Path:
    """cam_01 -> cam_02 -> cam_03; clips that don't exist, so each is --clip-seconds (5 s) long."""
    path = temp_dir(test) / "cameras.json"
    cams = [cam("cam_01", ("cam_02", 3.0, "north"), start=0.0),
            cam("cam_02", ("cam_01", 3.0, "south"), ("cam_03", 6.0, "north"), start=6.0),
            cam("cam_03", ("cam_02", 6.0, "south"), start=12.0)]
    path.write_text(json.dumps({"cameras": cams}), encoding="utf-8")
    return path


class Runs(unittest.TestCase):
    """main() in this process, with Wali's code replaced by fakes."""

    def run_main(self, *args, spot=fake_spot, describe=None) -> tuple[list[dict], Mock]:
        """Events of one agents.run; describe=None: the checker must never be loaded."""
        out = temp_dir(self) / "events.jsonl"
        argv = ["agents.run", *args, "--no-publish", "--speed", "0", "--tag", "t", "--run-id", "run_test",
                "--out", str(out)]
        checker = (Mock(return_value=(describe, "checker", "http://checker/v1")) if describe
                   else Mock(side_effect=AssertionError("the checker was loaded")))
        with patch.object(sys, "argv", argv), patch("agents.run.check_spotter"), \
                patch("agents.run.live_spotter", return_value=(spot, "spotter-ft", "http://spotter/v1")), \
                patch("agents.run.live_checker", checker), patch("agents.run.check_checker") as checked, \
                contextlib.redirect_stdout(io.StringIO()), self.assertLogs("agents", "INFO"):
            main()
        if describe is None:
            checked.assert_not_called()
        return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()], checker

    def test_no_checker_is_the_spotter_alone_as_before(self):
        cameras, saved = three_cameras(self), temp_dir(self) / "answers.json"
        events, checker = self.run_main("--live", "--no-checker", "--cameras", str(cameras),
                                        "--save-answers", str(saved))
        checker.assert_not_called()
        # The pipeline before the checker: the spotter's answers straight into the agents.
        rec, cams = Recorder(), json.loads(cameras.read_text(encoding="utf-8"))["cameras"]
        with self.assertLogs("agents", "WARNING"):  # the clips can't be read: 5 s each
            clips = load_clips(cams, 5.0)
        net = Network(cams, rec, tag="t", run_id="run_test", schedule={c.camera_id: [c.window] for c in clips},
                      detection_extra={"spotter_model": "spotter-ft", "spotter_mode": "live"})
        run_timeline(clips, lambda clip: fake_spot(str(clip.path), 8), net, Clock(0))
        self.assertEqual(events, rec.events)
        self.assertEqual(json.loads(saved.read_text(encoding="utf-8")),
                         {"model": "spotter-ft", "source": "agents.run --live", "answers": SPOTTED})

    def test_saved_merged_answers_replay_to_the_same_events(self):
        cameras, saved = three_cameras(self), temp_dir(self) / "answers.json"
        frames, lock = [], threading.Lock()

        def spot(path, count):
            with lock:
                frames.append(("spotter", count))
            return fake_spot(path, count)

        def describe(path, count):
            with lock:
                frames.append(("checker", count))
            if "cam_02" in path:
                raise RuntimeError("Checker reply was cut off")
            return DESC

        live, _ = self.run_main("--live", "--cameras", str(cameras), "--save-answers", str(saved),
                                spot=spot, describe=describe)
        self.assertEqual(sorted(frames), [("checker", 8)] * 2 + [("spotter", 8)] * 3)  # --frames defaults to 8
        file = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual((file["model"], file["checker_model"]), ("spotter-ft", "checker"))
        self.assertEqual(file["answers"], {"cam_01": merge_answers(CRIME, DESC, "checker"),
                                           "cam_02": spotter_only(FLEEING, "RuntimeError"), "cam_03": NOBODY})
        replay, _ = self.run_main("--answers", str(saved), "--cameras", str(cameras))
        mode = lambda events: [e.get("spotter_mode") for e in events if e["type"] == "detection"]  # noqa: E731
        self.assertEqual((mode(live), mode(replay)), (["live"] * 3, ["recorded"] * 3))
        same = lambda events: [{k: v for k, v in e.items() if k != "spotter_mode"} for e in events]  # noqa: E731
        self.assertEqual(same(replay), same(live))
        self.assertEqual(by_camera_events(live)["cam_01"]["description_by"], "checker")
        self.assertEqual([check(e) for e in live], [[] for _ in live])

    def test_a_gym_answers_file_replays_like_a_saved_one(self):
        """data/gym_answers.py writes Wali's eval-results format with the same marks (description_by,
        checker_model) as --save-answers; its system rows carry no spotter_description."""
        cams = [cam("cam_01", ("cam_02", 3.0, "north"), uri="clips/clip1_cam1.mp4", start=0.0),
                cam("cam_02", ("cam_01", 3.0, "south"), uri="clips/clip1_cam2.mp4", start=6.0)]
        cameras = temp_dir(self) / "cameras.json"
        cameras.write_text(json.dumps({"cameras": cams}), encoding="utf-8")
        checker_model = "Nemotron Nano 12B v2 VL (8 frames)"
        said = {name: {k: answer[k] for k in ("what_happened", "on_screen", "crime")}
                for name, answer in (("cam1", CRIME), ("cam2", FLEEING))}
        rows = {name: {**own, **DESC, "description_by": "checker", "checker_model": checker_model}
                for name, own in said.items()}
        gym = temp_dir(self) / "gym.json"
        gym.write_text(json.dumps({"model": "spotter-ft v3 (8 frames)", "checker_model": checker_model,
                                   "source": {"note": "recorded NeMo Gym runs"},
                                   "cameras": [{"clip": "clip1", "cam": name, "task_index": i, "answers": [row]}
                                               for i, (name, row) in enumerate(rows.items())]}), encoding="utf-8")
        saved = temp_dir(self) / "saved.json"
        save_answers(str(saved), {"cam_01": rows["cam1"], "cam_02": rows["cam2"]}, "spotter-ft v3 (8 frames)",
                     checker_model)
        from_gym, _ = self.run_main("--answers", str(gym), "--cameras", str(cameras))
        from_saved, _ = self.run_main("--answers", str(saved), "--cameras", str(cameras))
        self.assertEqual(from_gym, from_saved)
        crime = by_camera_events(from_gym)["cam_01"]
        self.assertEqual((crime["spotter"], crime["checker"]), (said["cam1"], DESC))
        self.assertEqual((crime["description_by"], crime["checker_model"]), ("checker", checker_model))
        verdict, = [e for e in from_gym if e["type"] == "agent_verdict"]
        self.assertEqual((verdict["camera_id"], verdict["decision"]), ("cam_02", "match"))
        self.assertEqual([check(e) for e in from_gym], [[] for _ in from_gym])


def by_camera_events(events):
    return {e["camera_id"]: e for e in events if e["type"] == "detection"}


if __name__ == "__main__":
    unittest.main()
