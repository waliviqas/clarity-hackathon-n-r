"""agents/run.py: the live spotter's time limit, the startup model checks, malformed answers, backups, ids."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agents.combine import merge_answers
from agents.network import Network
from agents.run import Clip, Clock, check_checker, check_spotter, id_tag, main, run_timeline, start_live
from agents.tests.test_network import CRIME, SITE, Recorder, cam
from contracts.validate import check

REPO_ROOT = Path(__file__).resolve().parents[2]

# What the checker (Wali's describe()) might say about a suspect: all 11 suspect fields.
DESC = {"build": "average", "height": "tall", "shirt": "red jacket", "pants": "blue jeans",
        "shoes": "white sneakers", "glasses": "no", "headwear": "none", "hair": "short dark",
        "bag": "black backpack", "weapon": "none", "vehicle": "none"}

# Stand-ins for Wali's src/spotter.py and src/checker.py: same names (spot / describe, MODEL, client.base_url).
FAKE_SPOTTER = '''import os
class _Client:
    base_url = os.environ["SPOTTER_URL"]
client = _Client()
MODEL = os.environ["SPOTTER_MODEL"]
def spot(video_path, count=4):
    return {"what_happened": "grabs a bag", "on_screen": "crime", "crime": "stealing", "shirt": "black hoodie"}
'''
FAKE_CHECKER = f'''import os
class _Client:
    base_url = os.environ.get("CHECKER_BASE_URL", "http://localhost:8002/v1")
client = _Client()
MODEL = os.environ.get("CHECKER_MODEL", "checker")
def describe(video_path, count=8):
    return {DESC!r}
'''


class FakeModels:
    """A fake vLLM answering GET /v1/models with the given model ids, on a free local port."""

    def __init__(self, *ids):
        body = json.dumps({"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                found = self.path == "/v1/models"
                self.send_response(200 if found else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if found:
                    self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def temp_dir(test: unittest.TestCase) -> Path:
    path = Path(tempfile.mkdtemp(prefix="agents_test_"))
    test.addCleanup(shutil.rmtree, path, True)
    return path


def fake_wali_src(test: unittest.TestCase, checker: bool = True) -> Path:
    """A folder holding stand-ins for Wali's src/ (spotter.py, and checker.py unless checker=False) and a
    one-camera cameras.json. Its src/ is a regular package (__init__.py), so a real src/ elsewhere on
    sys.path can't add modules to it."""
    root = temp_dir(test)
    (root / "src").mkdir()
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "spotter.py").write_text(FAKE_SPOTTER, encoding="utf-8")
    if checker:
        (root / "src" / "checker.py").write_text(FAKE_CHECKER, encoding="utf-8")
    (root / "cameras.json").write_text(json.dumps({"cameras": [cam("cam_01")]}), encoding="utf-8")
    return root


def run_agents(fake: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    """`python -m agents.run --live ...` in a fresh process that imports the stand-ins in `fake`, never Wali's
    real src/ (a merged checkout has it at the repo root): the working folder, which -m puts first on sys.path,
    is `fake`, and the repo root only follows it on PYTHONPATH."""
    env = {**os.environ, **env, "PYTHONPATH": os.pathsep.join([str(fake), str(REPO_ROOT)])}
    return subprocess.run([sys.executable, "-m", "agents.run", "--live", "--no-publish", "--speed", "0",
                           "--cameras", str(fake / "cameras.json"), *args],
                          cwd=fake, env=env, capture_output=True, text=True, timeout=60)


def events_in(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


class SpotterCheck(unittest.TestCase):
    def setUp(self):
        self.vllm = FakeModels("spotter-ft")
        self.addCleanup(self.vllm.close)

    def test_served_model_passes(self):
        check_spotter(self.vllm.url, "spotter-ft")
        check_spotter(self.vllm.url + "/", "spotter-ft")  # the openai client's base_url ends in "/"

    def test_model_not_served_exits_with_one_line(self):
        with self.assertRaises(SystemExit) as stop:
            check_spotter(self.vllm.url, "Qwen/Qwen3-VL-2B-Instruct")
        message = str(stop.exception.code)
        self.assertNotIn("\n", message)
        self.assertIn("serves spotter-ft, not SPOTTER_MODEL=Qwen/Qwen3-VL-2B-Instruct", message)

    def test_unreachable_spotter_exits(self):
        free = FakeModels()
        url = free.url
        free.close()  # nothing listens there now
        with self.assertRaises(SystemExit) as stop:
            check_spotter(url, "spotter-ft", timeout_s=2)
        self.assertIn("can't read", str(stop.exception.code))

    def test_live_run_stops_with_exit_1_before_any_event(self):
        fake = fake_wali_src(self)
        checker = FakeModels("checker")
        self.addCleanup(checker.close)
        for model, code in (("Qwen/Qwen3-VL-2B-Instruct", 1), ("spotter-ft", 0)):
            run = run_agents(fake, {"SPOTTER_URL": self.vllm.url, "SPOTTER_MODEL": model,
                                    "CHECKER_BASE_URL": checker.url, "CHECKER_MODEL": "checker"})
            self.assertEqual(run.returncode, code, run.stderr)
            if code:
                self.assertEqual(run.stderr.strip().splitlines()[-1],
                                 f"spotter check: {self.vllm.url}/models serves spotter-ft, not SPOTTER_MODEL={model}")
                self.assertNotIn("detection", run.stdout)
            else:
                self.assertIn("detection", run.stdout)


class CheckerCheck(unittest.TestCase):
    """--live also checks the checker, before anything is published (a fresh process with fakes of Wali's src/)."""

    def setUp(self):
        self.spotter, self.checker = FakeModels("spotter-ft"), FakeModels("checker")
        self.addCleanup(self.spotter.close)
        self.addCleanup(self.checker.close)

    def live(self, fake: Path, *args: str, **env: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        out = fake / "events.jsonl"
        env = {"SPOTTER_URL": self.spotter.url, "SPOTTER_MODEL": "spotter-ft",
               "CHECKER_BASE_URL": self.checker.url, "CHECKER_MODEL": "checker", **env}
        return run_agents(fake, env, "--tag", "t", "--out", str(out), *args), events_in(out)

    def test_checker_not_serving_its_model_stops_the_run_with_exit_1(self):
        run, events = self.live(fake_wali_src(self), CHECKER_MODEL="nemotron-12b")
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual(run.stderr.strip().splitlines()[-1],
                         f"checker check: {self.checker.url}/models serves checker, not CHECKER_MODEL=nemotron-12b "
                         "(or run the spotter alone with --no-checker)")
        self.assertEqual(events, [])
        self.assertNotIn("detection", run.stdout)

    def test_checker_messages_name_its_settings_and_the_way_out(self):
        check_checker(self.checker.url, "checker")
        for url, model, start in ((self.checker.url, "nemotron-12b", "checker check: "),
                                  (self.checker.url[:-3] + "/v2", "checker", "checker check: can't read "),
                                  (None, "checker", "checker check: no checker URL or model name (set "
                                                    "CHECKER_BASE_URL and CHECKER_MODEL)")):
            with self.assertRaises(SystemExit) as stop:
                check_checker(url, model)
            message = str(stop.exception.code)
            self.assertNotIn("\n", message)
            self.assertTrue(message.startswith(start), message)
            self.assertTrue(message.endswith(" (or run the spotter alone with --no-checker)"), message)

    def test_served_checker_describes_the_flagged_camera(self):
        run, events = self.live(fake_wali_src(self))
        self.assertEqual(run.returncode, 0, run.stderr)
        det, = [e for e in events if e["type"] == "detection"]
        self.assertEqual((det["description_by"], det["checker_model"], det["checker"]), ("checker", "checker", DESC))
        self.assertEqual(det["spotter"]["shirt"], "black hoodie")  # what the spotter said stays in the receipts
        self.assertIn("red jacket", det["appearance"])
        self.assertIn("described by the checker", run.stdout)
        self.assertEqual([check(e) for e in events], [[] for _ in events])

    def test_no_checker_runs_the_spotter_alone(self):
        fake = fake_wali_src(self, checker=False)
        run, events = self.live(fake)  # the checker is on by default, and src/checker.py is missing
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn("Wali's checker isn't importable", run.stderr.strip().splitlines()[-1])
        self.assertEqual(events, [])
        run, events = self.live(fake, "--no-checker", CHECKER_BASE_URL="http://127.0.0.1:9/v1")
        self.assertEqual(run.returncode, 0, run.stderr)
        det, = [e for e in events if e["type"] == "detection"]
        self.assertEqual((det["spotter"]["shirt"], det["appearance"]), ("black hoodie", "black hoodie"))
        self.assertFalse({"description_by", "checker", "checker_model"} & det.keys())


class LiveTimeLimit(unittest.TestCase):
    def test_slow_spotter_call_times_out_and_the_run_carries_on(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def spot(path, count):
            if "cam_02" in path:
                release.wait(30)  # a hung vLLM call
                return CRIME
            return CRIME

        clips = [Clip("cam_01", Path("cam_01.mp4"), (0.0, 8.0)), Clip("cam_02", Path("cam_02.mp4"), (9.0, 12.0))]
        rec = Recorder()
        net = Network(SITE, rec, tag="t")
        began = time.monotonic()
        with self.assertLogs("agents", "WARNING") as logs:
            run_timeline(clips, start_live(clips, spot, 4, Clock(0), limit_s=0.3), net, Clock(0))
        self.assertLess(time.monotonic() - began, 5)
        verdict, = rec.of("agent_verdict")
        self.assertEqual((verdict["camera_id"], verdict["decision"]), ("cam_02", "uncertain"))
        self.assertIn("TimeoutError", verdict["reason"])
        self.assertEqual(sum("no spotter answer: TimeoutError" in line for line in logs.output), 1)

    def test_a_failed_call_is_retried_once(self):
        calls = []

        def spot(path, count):
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError("Spotter reply was cut off")
            return CRIME

        clips = [Clip("cam_01", Path("cam_01.mp4"), (0.0, 8.0))]
        with self.assertLogs("agents", "INFO"):
            answer = start_live(clips, spot, 4, Clock(0), limit_s=5)(clips[0])
        self.assertEqual((answer, len(calls)), (CRIME, 2))


class MalformedAnswers(unittest.TestCase):
    def test_answer_that_is_not_a_dict_is_logged_and_skipped(self):
        for bad in (None, "crime", ["crime"]):
            rec = Recorder()
            net = Network(SITE, rec, tag="t")
            clips = [Clip("cam_01", Path("x"), (0.0, 8.0)), Clip("cam_02", Path("x"), (9.0, 12.0))]
            answers = {"cam_01": CRIME, "cam_02": bad}
            with self.assertLogs("agents", "WARNING") as logs:
                run_timeline(clips, lambda c: answers[c.camera_id], net, Clock(0))
            self.assertIn("not a JSON object", logs.output[0])
            self.assertEqual([d["camera_id"] for d in rec.of("detection")], ["cam_01"])
            self.assertEqual([(v["camera_id"], v["decision"]) for v in rec.of("agent_verdict")],
                             [("cam_02", "uncertain")])


class Backups(unittest.TestCase):
    def test_answers_are_saved_when_the_run_crashes(self):
        tmp = temp_dir(self)
        cameras, backup = tmp / "cameras.json", tmp / "answers.json"
        cameras.write_text(json.dumps({"cameras": [cam("cam_01"), cam("cam_02", start=3.0)]}), encoding="utf-8")

        def crash(clips, get_answer, net, clock):
            get_answer(clips[0])
            raise RuntimeError("the take crashed")

        argv = ["agents.run", "--live", "--no-publish", "--speed", "0", "--cameras", str(cameras),
                "--save-answers", str(backup)]
        with patch.object(sys, "argv", argv), patch("agents.run.check_spotter"), patch("agents.run.check_checker"), \
                patch("agents.run.live_spotter", return_value=(lambda path, n: CRIME, "fake", "http://x/v1")), \
                patch("agents.run.live_checker", return_value=(lambda path, n: DESC, "checker", "http://y/v1")), \
                patch("agents.run.run_timeline", crash), self.assertRaises(RuntimeError), \
                self.assertLogs("agents", "INFO"):
            main()
        saved = json.loads(backup.read_text(encoding="utf-8"))
        self.assertEqual((saved["model"], saved["answers"]),
                         ("fake", {"cam_01": merge_answers(CRIME, DESC, "checker")}))


class Tags(unittest.TestCase):
    def test_tag_must_fit_an_event_id(self):
        self.assertEqual(id_tag("take2-b_1"), "take2-b_1")
        for bad in ("", "a b", "x/y", "t.1"):
            with self.assertRaises(argparse.ArgumentTypeError):
                id_tag(bad)


if __name__ == "__main__":
    unittest.main()
