"""agents/run.py: the live spotter's time limit, the startup model check, malformed answers, backups, ids."""
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

from agents.network import Network
from agents.run import Clip, Clock, check_spotter, id_tag, main, run_timeline, start_live
from agents.tests.test_network import CRIME, SITE, Recorder, cam

REPO_ROOT = Path(__file__).resolve().parents[2]

# A stand-in for Wali's src/spotter.py: same names (spot, MODEL, client.base_url), canned answer.
FAKE_SPOTTER = '''import os
class _Client:
    base_url = os.environ["SPOTTER_URL"]
client = _Client()
MODEL = os.environ["SPOTTER_MODEL"]
def spot(video_path, count=4):
    return {"what_happened": "grabs a bag", "on_screen": "crime", "crime": "stealing", "shirt": "black hoodie"}
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
        fake = temp_dir(self)
        (fake / "src").mkdir()
        (fake / "src" / "spotter.py").write_text(FAKE_SPOTTER, encoding="utf-8")
        cameras = fake / "cameras.json"
        cameras.write_text(json.dumps({"cameras": [cam("cam_01")]}), encoding="utf-8")
        for model, code in (("Qwen/Qwen3-VL-2B-Instruct", 1), ("spotter-ft", 0)):
            env = {**os.environ, "PYTHONPATH": str(fake), "SPOTTER_URL": self.vllm.url, "SPOTTER_MODEL": model}
            run = subprocess.run([sys.executable, "-m", "agents.run", "--live", "--no-publish", "--speed", "0",
                                  "--cameras", str(cameras)], cwd=REPO_ROOT, env=env, capture_output=True,
                                 text=True, timeout=60)
            self.assertEqual(run.returncode, code, run.stderr)
            if code:
                self.assertEqual(run.stderr.strip().splitlines()[-1],
                                 f"spotter check: {self.vllm.url}/models serves spotter-ft, not SPOTTER_MODEL={model}")
                self.assertNotIn("detection", run.stdout)
            else:
                self.assertIn("detection", run.stdout)


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
        with patch.object(sys, "argv", argv), patch("agents.run.check_spotter"), \
                patch("agents.run.live_spotter", return_value=(lambda path, n: CRIME, "fake", "http://x/v1")), \
                patch("agents.run.run_timeline", crash), self.assertRaises(RuntimeError), \
                self.assertLogs("agents", "INFO"):
            main()
        saved = json.loads(backup.read_text(encoding="utf-8"))
        self.assertEqual((saved["model"], saved["answers"]), ("fake", {"cam_01": CRIME}))


class Tags(unittest.TestCase):
    def test_tag_must_fit_an_event_id(self):
        self.assertEqual(id_tag("take2-b_1"), "take2-b_1")
        for bad in ("", "a b", "x/y", "t.1"):
            with self.assertRaises(argparse.ArgumentTypeError):
                id_tag(bad)


if __name__ == "__main__":
    unittest.main()
