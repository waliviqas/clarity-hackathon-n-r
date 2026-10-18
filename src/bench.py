"""Measure how the vLLM-served spotter handles many cameras at once.

Frames are extracted up front so the timings measure vLLM, not video decoding.
Run it on the same machine as vLLM so network upload time doesn't skew the numbers.
"""
import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from .frames import sample_frames
    from .spotter import MODEL, spot_frames
except ImportError:
    from frames import sample_frames
    from spotter import MODEL, spot_frames


def timed_call(frames: list[bytes], source: str) -> tuple[float, bool]:
    start = time.perf_counter()
    try:
        spot_frames(frames, source)
        ok = True
    except Exception as error:
        print(f"  request failed: {type(error).__name__}: {str(error)[:120]}")
        ok = False
    return time.perf_counter() - start, ok


def run_level(clips: list[tuple[str, list[bytes]]], concurrency: int, requests: int) -> dict:
    jobs = [clips[i % len(clips)] for i in range(requests)]
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda job: timed_call(job[1], job[0]), jobs))
    wall = time.perf_counter() - start

    latencies = sorted(seconds for seconds, ok in results if ok)
    errors = sum(1 for _, ok in results if not ok)
    p95_index = max(0, int(round(0.95 * len(latencies))) - 1)
    return {
        "concurrent_cameras": concurrency,
        "requests": requests,
        "errors": errors,
        "latency_p50_s": round(statistics.median(latencies), 3) if latencies else None,
        "latency_p95_s": round(latencies[p95_index], 3) if latencies else None,
        "latency_mean_s": round(statistics.mean(latencies), 3) if latencies else None,
        "wall_time_s": round(wall, 2),
        "throughput_cameras_per_min": round(len(latencies) / wall * 60, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", default="video-data/custom-clips")
    parser.add_argument("--levels", default="1,2,4,8,16,32")
    parser.add_argument("--requests", type=int, default=32)
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--out", default="results/vllm_bench.json")
    args = parser.parse_args()

    clips = [(str(p), sample_frames(str(p), args.frames)) for p in sorted(Path(args.clips).glob("clip*/cam*.mp4"))]
    print(f"Loaded {len(clips)} camera clips, {args.frames} frames each")

    timed_call(clips[0][1], clips[0][0])  # warm-up so the first level isn't penalised

    levels = []
    for concurrency in (int(n) for n in args.levels.split(",")):
        result = run_level(clips, concurrency, args.requests)
        levels.append(result)
        print(json.dumps(result))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": MODEL, "frames_per_request": args.frames, "levels": levels}, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
