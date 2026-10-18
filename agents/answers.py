"""Where the camera agents get spotter answers: a recorded file (stand-in) or Wali's spotter (live).

Recorded files, any of:
  - Wali's eval results (results/before.json, results/after.json):
        {"model": ..., "cameras": [{"clip": "clip8", "cam": "cam1", "answers": [{...}, null, ...]}, ...]}
    matched to cameras.json by clip file name (source.uri .../clip8_cam1.mp4 <-> clip8 + cam1);
  - what `python -m agents.run --live --save-answers` writes: {"model": ..., "answers": {"cam_01": {...}}};
  - a bare {"cam_01": {...}, ...}.
Live: Wali's spot(video_path, count) from src/spotter.py, imported unchanged from PYTHONPATH (see README);
it reads SPOTTER_URL / SPOTTER_MODEL itself.
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


def save_answers(path: str, answers: dict[str, dict], model: str | None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"model": model, "source": "agents.run --live", "answers": answers},
                                     indent=2), encoding="utf-8")


def live_spotter():
    """(spot, model name, base URL) from Wali's src/spotter.py, unchanged. The URL is the one his client
    calls (it reads SPOTTER_URL), so the startup check looks at the same server."""
    try:
        from src import spotter  # Wali's code: git archive origin/wali-branch src | tar -x -C <dir>; PYTHONPATH=<dir>
    except ImportError as e:
        raise SystemExit(f"Wali's spotter isn't importable ({e}). Extract it with "
                         "`git archive origin/wali-branch src | tar -x -C <dir>` and set PYTHONPATH=<dir> "
                         "(it needs: pip install -r agents/requirements.txt).")
    url = getattr(getattr(spotter, "client", None), "base_url", None) or os.environ.get("SPOTTER_URL")
    model = getattr(spotter, "MODEL", None) or os.environ.get("SPOTTER_MODEL")
    return spotter.spot, model, str(url) if url else None
