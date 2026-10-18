"""How much does vLLM's structured output (JSON schema) matter for the dispatcher model?

Sends the dispatcher's real prompts three ways and counts usable answers:
  A. no schema, prompt as used in production (the prompt never says "JSON": the schema does that)
  B. no schema, prompt plus an explicit "answer with a JSON object with these fields" instruction
  C. JSON schema via vLLM (production)
An answer is usable when it parses as JSON and passes the dispatcher's verifier.

    CLARITY_LLM_BASE_URL=http://localhost:8003/v1 CLARITY_LLM_MODEL=dispatcher \
        python scripts/reliability_dispatcher.py [--repeats 8]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI  # noqa: E402

from dispatcher import CameraGraph, Dispatcher, SubjectCase  # noqa: E402
from dispatcher.demo import CAMERAS, MESSAGES  # noqa: E402
from dispatcher.llm import PROPOSAL_SCHEMA, SYSTEM_PROMPT, build_user_message, intercept_camera  # noqa: E402
from dispatcher.rules import gate, path  # noqa: E402
from dispatcher.verify import verify  # noqa: E402

JSON_HINT = ('\nAnswer with only a JSON object with the fields "status", "priority", "recommendation", '
             '"reason", and "evidence_event_ids", and nothing else.')


def model_cases() -> list[tuple[SubjectCase, list[dict], list[dict]]]:
    """Every point in the demo where the dispatcher would call the model, as (case, path, predicted_next)."""
    graph, cases = CameraGraph.from_config(CAMERAS), []
    d = Dispatcher(graph)
    for msg in sorted(MESSAGES, key=lambda m: m["ts"]):
        if msg["type"] == "operator_action":
            continue
        d.process([msg])
        for case in d.cases.values():
            if msg.get("subject_id") == case.subject_id and gate(case, d.cfg) == "ambiguous":
                snap = SubjectCase(case.subject_id, events=dict(case.events))
                cam_path = path(snap)
                cases.append((snap, cam_path, d._predict(snap, cam_path)))
    return cases


def parse(text: str) -> dict | None:
    """Lenient: accept a JSON object even if wrapped in prose or a code fence (favours variants A and B)."""
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except Exception:
            return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=8)
    args = ap.parse_args()
    client = OpenAI(base_url=os.environ.get("CLARITY_LLM_BASE_URL", "http://localhost:8003/v1"),
                    api_key=os.environ.get("CLARITY_LLM_API_KEY", "EMPTY"), timeout=120)
    model = os.environ.get("CLARITY_LLM_MODEL", "dispatcher")
    graph = CameraGraph.from_config(CAMERAS)
    cases = model_cases()
    rf = {"type": "json_schema", "json_schema": {"name": "dispatch_proposal", "schema": PROPOSAL_SCHEMA, "strict": True}}
    variants = {
        "A: no schema": (SYSTEM_PROMPT, {}),
        "B: no schema + JSON instruction": (SYSTEM_PROMPT + JSON_HINT, {}),
        "C: JSON schema (production)": (SYSTEM_PROMPT, {"response_format": rf}),
    }
    print(f"model={model}  prompts={len(cases)}  repeats={args.repeats}\n")
    rows = []
    for label, (system, extra) in variants.items():
        jobs = [c for c in cases for _ in range(args.repeats)]

        def one(job):
            case, cam_path, pred = job
            t = time.perf_counter()
            r = client.chat.completions.create(
                model=model, temperature=0, max_tokens=400, **extra,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": build_user_message(case, cam_path, pred, graph)}])
            proposal = parse(r.choices[0].message.content)
            ok = proposal is not None and isinstance(proposal, dict) and not verify(
                proposal, case, set(graph.cameras), intercept_camera(cam_path, pred))
            return proposal is not None, ok, time.perf_counter() - t

        with ThreadPoolExecutor(8) as pool:
            res = list(pool.map(one, jobs))
        row = {"variant": label, "calls": len(res), "parsed_json": sum(r[0] for r in res),
               "passed_verifier": sum(r[1] for r in res), "mean_s": round(sum(r[2] for r in res) / len(res), 2)}
        rows.append(row)
        print(f"{label:34s} parsed {row['parsed_json']:>3}/{row['calls']}  usable {row['passed_verifier']:>3}/{row['calls']}"
              f"  mean {row['mean_s']} s")
    print("\n" + json.dumps(rows))


if __name__ == "__main__":
    main()
