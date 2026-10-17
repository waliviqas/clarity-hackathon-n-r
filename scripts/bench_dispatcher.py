"""Load-test the dispatcher model on vLLM with real dispatcher requests.

Sends the exact prompt + JSON schema the dispatcher uses, at increasing concurrency, and reports
latency (p50/p95), requests/s, output tokens/s, and how many answers pass the verifier.

    CLARITY_LLM_BASE_URL=http://localhost:8003/v1 CLARITY_LLM_MODEL=dispatcher \
        python scripts/bench_dispatcher.py [--levels 1 4 8 16] [--per-level 16]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI  # noqa: E402

from dispatcher import CameraGraph, RuleConfig, SubjectCase  # noqa: E402
from dispatcher.demo import CAMERAS, MESSAGES  # noqa: E402
from dispatcher.llm import PROPOSAL_SCHEMA, SYSTEM_PROMPT, build_user_message, intercept_camera  # noqa: E402
from dispatcher.rules import path, predicted_next  # noqa: E402
from dispatcher.verify import verify  # noqa: E402


def demo_case() -> tuple[SubjectCase, list[dict], list[dict]]:
    graph = CameraGraph.from_config(CAMERAS)
    case = SubjectCase("subj_7")
    for m in MESSAGES[:4]:  # the ambiguous purse-snatch incident: the path that actually calls the model
        case.events[m["event_id"]] = m
    cam_path = path(case)
    return case, cam_path, predicted_next(case, cam_path, graph, RuleConfig())


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 4, 8, 16])
    ap.add_argument("--per-level", type=int, default=16, help="requests per concurrency level")
    args = ap.parse_args()

    client = OpenAI(base_url=os.environ.get("CLARITY_LLM_BASE_URL", "http://localhost:8003/v1"),
                    api_key=os.environ.get("CLARITY_LLM_API_KEY", "EMPTY"), timeout=120)
    model = os.environ.get("CLARITY_LLM_MODEL", "dispatcher")
    case, cam_path, pred = demo_case()
    graph = CameraGraph.from_config(CAMERAS)
    user = build_user_message(case, cam_path, pred, graph)
    known = set(graph.cameras)
    rf = {"type": "json_schema", "json_schema": {"name": "dispatch_proposal", "schema": PROPOSAL_SCHEMA, "strict": True}}

    def one(_: int) -> tuple[float, int, bool]:
        t = time.perf_counter()
        r = client.chat.completions.create(
            model=model, temperature=0, max_tokens=400, response_format=rf,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}])
        dt = time.perf_counter() - t
        try:
            ok = not verify(json.loads(r.choices[0].message.content), case, known, intercept_camera(cam_path, pred))
        except Exception:
            ok = False
        return dt, r.usage.completion_tokens, ok

    one(0)  # warm-up
    print(f"model={model}  prompt={len(user)} chars  requests/level={args.per_level}\n")
    print(f"{'concurrency':>11} {'p50 s':>7} {'p95 s':>7} {'req/s':>7} {'out tok/s':>10} {'verified':>9}")
    rows = []
    for c in args.levels:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=c) as pool:
            res = list(pool.map(one, range(args.per_level)))
        wall = time.perf_counter() - t0
        lat = [r[0] for r in res]
        row = {"concurrency": c, "p50_s": round(statistics.median(lat), 2), "p95_s": round(pct(lat, 95), 2),
               "req_per_s": round(len(res) / wall, 2), "out_tok_per_s": round(sum(r[1] for r in res) / wall, 1),
               "verified": f"{sum(r[2] for r in res)}/{len(res)}"}
        rows.append(row)
        print(f"{c:>11} {row['p50_s']:>7} {row['p95_s']:>7} {row['req_per_s']:>7} {row['out_tok_per_s']:>10} "
              f"{row['verified']:>9}")
    print("\n" + json.dumps(rows))


if __name__ == "__main__":
    main()
