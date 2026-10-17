"""Validate Clarity messages against contracts/schemas.

Usage (from the repo root):
    python contracts/validate.py contracts/examples/*.json
    python contracts/validate.py runs/run_demo1/events.jsonl data/cameras.json

Picks the schema from each message's "type" field; a file with a top-level
"cameras" key is checked as cameras.json. Exits 1 if anything is invalid.
Needs: pip install jsonschema
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
VALIDATORS = {
    p.name.removesuffix(".schema.json"): jsonschema.Draft202012Validator(json.loads(p.read_text()))
    for p in SCHEMA_DIR.glob("*.schema.json")
}


def schema_name(msg: dict) -> str | None:
    if "cameras" in msg and "type" not in msg:
        return "cameras"
    return msg.get("type")


def check(msg: dict) -> list[str]:
    """Return a list of error strings (empty list = valid)."""
    name = schema_name(msg)
    if name not in VALIDATORS:
        return [f"unknown message type {name!r} (known: {', '.join(sorted(VALIDATORS))})"]
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in VALIDATORS[name].iter_errors(msg)]


def load(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip():
                yield f"{path}:{i}", json.loads(line)
    else:
        yield str(path), json.loads(text)


def main(paths: list[str]) -> int:
    bad = total = 0
    for p in paths:
        for where, msg in load(Path(p)):
            total += 1
            errors = check(msg)
            if errors:
                bad += 1
                print(f"INVALID {where}")
                for err in errors:
                    print(f"   - {err}")
    print(f"{total - bad}/{total} valid")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
