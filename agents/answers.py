"""Where the camera agents get spotter answers: a recorded file (stand-in) or Wali's spotter + checker (live).

Recorded files, any of:
  - Wali's eval-results format (results/before.json; data/gym_answers.py writes it too, e.g.
    data/answers/clip1_system_v3_checker.json):
        {"model": ..., "cameras": [{"clip": "clip1", "cam": "cam1", "answers": [{...}, null, ...]}, ...]}
    matched to cameras.json by clip file name (source.uri .../clip1_cam1.mp4 <-> clip1 + cam1);
  - what `python -m agents.run --live --save-answers` writes: {"model": ..., "answers": {"cam_01": {...}}}
    (answers on flagged cameras already carry the checker's description, see agents/combine.py);
  - a bare {"cam_01": {...}, ...}.
Live: Wali's spot(video_path, count) from src/spotter.py and describe(video_path, count) from src/checker.py,
imported unchanged from the repo's src/ (run from the repo root); they read SPOTTER_URL / SPOTTER_MODEL and
CHECKER_BASE_URL / CHECKER_MODEL themselves.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def clip_key(camera: dict) -> str | None:
    """'clip8_cam1' for a camera whose source.uri is .../clip8_cam1.mp4."""
    uri = (camera.get("source") or {}).get("uri")
    return Path(str(uri)).stem if uri else None


def _pick(runs: list, run: int | None) -> dict | None:
    """One recorded run: the requested one, or the first that didn't fail (failed runs are null)."""
    if run is not None:
        answer = runs[run] if 0 <= run < len(runs) else None
        return answer if isinstance(answer, dict) else None
    return next((a for a in runs if isinstance(a, dict)), None)


def load_answers(path: str, cameras: list[dict], run: int | None = None) -> tuple[dict[str, dict], str | None]:
    """({camera_id: answer}, spotter model name or None) for the cameras in cameras.json."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = {c["camera_id"] for c in cameras}
    model = data.get("model") if isinstance(data, dict) else None
    if isinstance(data, dict) and isinstance(data.get("cameras"), list):  # Wali's eval results
        by_clip = {clip_key(c): c["camera_id"] for c in cameras if clip_key(c)}
        out = {}
        for row in data["cameras"]:
            camera_id = by_clip.get(f"{row.get('clip')}_{row.get('cam')}")
            answer = _pick(row.get("answers") or [], run) if camera_id else None
            if answer is not None:
                out[camera_id] = answer
        return out, model
    mapping = data.get("answers", data) if isinstance(data, dict) else {}
    return {k: v for k, v in mapping.items() if k in ids and isinstance(v, dict)}, model


def save_answers(path: str, answers: dict[str, dict], model: str | None, checker_model: str | None = None) -> None:
    """The answers as --answers reads them. checker_model (when the checker ran) is also written at the top, as
    data/gym_answers.py does; each answer it described carries description_by + checker_model itself."""
    data = {"model": model, **({"checker_model": checker_model} if checker_model else {}),
            "source": "agents.run --live", "answers": answers}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def live_spotter():
    """(spot, model name, base URL) from Wali's src/spotter.py, unchanged. The URL is the one his client
    calls (it reads SPOTTER_URL), so the startup check looks at the same server."""
    try:
        from src import spotter  # Wali's code, src/ at the repo root
    except ImportError as e:
        raise SystemExit(f"Wali's spotter isn't importable ({e}): run from the repo root; src/ ships with the repo "
                         "(it needs: pip install -r agents/requirements.txt).")
    url = getattr(getattr(spotter, "client", None), "base_url", None) or os.environ.get("SPOTTER_URL")
    model = getattr(spotter, "MODEL", None) or os.environ.get("SPOTTER_MODEL")
    return spotter.spot, model, str(url) if url else None


def live_checker():
    """(describe, model name, base URL) from Wali's src/checker.py, unchanged, loaded like live_spotter(). It
    reads CHECKER_BASE_URL / CHECKER_MODEL itself (note: CHECKER_BASE_URL, while the spotter's is SPOTTER_URL)."""
    try:
        from src import checker  # Wali's code, next to src/spotter.py
    except ImportError as e:
        raise SystemExit(f"Wali's checker isn't importable ({e}): run from the repo root; src/ ships with the repo "
                         "(it needs: pip install -r agents/requirements.txt). Or run the spotter alone with "
                         "--no-checker.")
    url = getattr(getattr(checker, "client", None), "base_url", None) or os.environ.get("CHECKER_BASE_URL")
    model = getattr(checker, "MODEL", None) or os.environ.get("CHECKER_MODEL")
    return checker.describe, model, str(url) if url else None
