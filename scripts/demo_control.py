"""Run / Stop / Restart for the live demo, called by the dashboard's hidden buttons (dashboard/src/shell/DemoControls.tsx).

Runs on the GPU box from the repo root, next to the model servers:
    python scripts/demo_control.py --env .env.demo3            # listens on 127.0.0.1:8090
Reach it from the laptop with an SSH tunnel for port 8090 (like the bus).

  POST /run      new run id -> restart the bus and the coordinator on it -> start the live camera agents
  POST /stop     stop the camera agents (the bus and the coordinator keep what already happened)
  POST /restart  stop, then run
  GET  /status   whether a run is going, and its run id

Each part runs in its own tmux session (<prefix>-bus, -disp, -agents) so its log can be read with tmux attach.
The env file sets CLARITY_BUS_URL, CLARITY_RUN_ID, CLARITY_CAMERAS and the model servers, as in .env.example.
"""
import argparse
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

PYTHON = "/home/ubuntu/vllm12/bin/python"
ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


def tmux_running(name: str) -> bool:
    return subprocess.run(["tmux", "has-session", "-t", name], capture_output=True).returncode == 0


def tmux_start(name: str, command: str) -> None:
    subprocess.run(["tmux", "new-session", "-d", "-s", name, command], check=True)


def tmux_stop(name: str) -> None:
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


class Demo:
    def __init__(self, root: Path, env: Path, prefix: str, speed: float, check_frames: int):
        self.root, self.env, self.prefix, self.speed = root, env, prefix, speed
        self.check_frames = check_frames
        self.lock = Lock()

    def setting(self, key: str) -> str:
        m = re.search(rf"^export {key}=(.*)$", self.env.read_text(), re.M)
        return m.group(1).strip() if m else ""

    def session(self, part: str) -> str:
        return f"{self.prefix}-{part}"

    def launch(self, part: str, module_args: str) -> None:
        tmux_start(self.session(part), f"cd {self.root} && source {self.env} && {PYTHON} -m {module_args} "
                                       f"2>&1 | tee runs_{self.prefix}_{part}.log")

    def wait_for_bus(self, seconds: float = 20) -> bool:
        url = self.setting("CLARITY_BUS_URL") + "/health"
        end = time.time() + seconds
        while time.time() < end:
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if json.load(r).get("ok"):
                        return True
            except OSError:
                pass
            time.sleep(0.5)
        return False

    def run(self) -> tuple[int, str]:
        if tmux_running(self.session("agents")):
            return 409, "A run is already going. Stop or restart it."
        run_id = "run_" + self.prefix + "_" + datetime.now().strftime("%H%M%S")
        text = re.sub(r"^export CLARITY_RUN_ID=.*$", f"export CLARITY_RUN_ID={run_id}", self.env.read_text(), flags=re.M)
        self.env.write_text(text)
        for part in ("disp", "bus"):
            tmux_stop(self.session(part))
        time.sleep(1.5)  # let the bus free its port
        self.launch("bus", "bus.server")
        if not self.wait_for_bus():
            return 500, "The bus didn't come up; see the bus tmux session."
        self.launch("disp", "dispatcher.run")
        time.sleep(4)  # the coordinator warms its model up before it reads the bus
        self.launch("agents", f"agents.run --live --frames 8 --check-frames {self.check_frames} --speed {self.speed:g} --save-answers runs/{run_id}/answers.json")
        return 200, f"Running {run_id}"

    def stop(self) -> tuple[int, str]:
        if not tmux_running(self.session("agents")):
            return 200, "Nothing running."
        tmux_stop(self.session("agents"))
        return 200, "Stopped."

    def status(self) -> tuple[int, dict]:
        return 200, {"running": tmux_running(self.session("agents")), "run_id": self.setting("CLARITY_RUN_ID")}


def handler_for(demo: Demo):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            origin = self.headers.get("Origin", "")
            if origin in ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            origin = self.headers.get("Origin", "")
            if origin in ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.end_headers()

        def do_GET(self):
            if self.path == "/status":
                self.reply(*demo.status())
            else:
                self.reply(404, {"message": "unknown path"})

        def do_POST(self):
            actions = {"/run": demo.run, "/stop": demo.stop}
            if self.path not in (*actions, "/restart"):
                return self.reply(404, {"message": "unknown path"})
            with demo.lock:
                if self.path == "/restart":
                    demo.stop()
                    code, message = demo.run()
                else:
                    code, message = actions[self.path]()
            self.reply(code, {"message": message})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", type=Path, required=True, help="env file for the demo run (e.g. .env.demo3)")
    parser.add_argument("--prefix", default="demo3", help="tmux session and run id prefix (default demo3)")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--speed", type=float, default=0,
                        help="agents.run --speed: 1 = real time, 0 = each camera as soon as the previous is done (default)")
    parser.add_argument("--check-frames", type=int, default=4, help="frames per checker call (default 4: faster)")
    args = parser.parse_args()
    demo = Demo(Path.cwd(), args.env.resolve(), args.prefix, args.speed, args.check_frames)
    print(f"demo control on 127.0.0.1:{args.port} (env {demo.env}, tmux {args.prefix}-bus/-disp/-agents)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(demo)).serve_forever()


if __name__ == "__main__":
    main()
