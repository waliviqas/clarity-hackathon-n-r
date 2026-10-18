"""Build the publishable open-data package for test clip 8 (Hugging Face dataset, CC BY 4.0).

Writes data/raw/publish/clarity-clip8/ (gitignored): cam1.mp4, cam2.mp4, cam3.mp4 with every person who is not
one of the actors blurred, plus copies of data/ground_truth/take1.json and data/staged/clip_log_take1.csv, and
the dataset card data/staged/DATASET_CARD.md as README.md. Upload that folder as is (steps in the card).

    python data/publish_clip8.py              # build + check (no audio, same frame count, H.264)
    python data/publish_clip8.py --sheets     # also write review contact sheets to data/raw/publish/review/

Blur boxes are (first_frame, last_frame, x, y, w, h) in pixels of the 1280x720 clips, read from frame contact
sheets. Each box gets a heavy 3-pass box blur for its frames; every other pixel is unchanged. Clips without
boxes are copied byte for byte. Needs ffmpeg and ffprobe on PATH. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("data/raw/staged/take1")
OUT = Path("data/raw/publish/clarity-clip8")
REVIEW = Path("data/raw/publish/review")
EXTRA_FILES = {Path("data/ground_truth/take1.json"): "take1.json",
               Path("data/staged/clip_log_take1.csv"): "clip_log_take1.csv",
               Path("data/staged/DATASET_CARD.md"): "README.md"}  # the card is the dataset's README
NAMES = {"clip8_cam1.mp4": "cam1.mp4", "clip8_cam2.mp4": "cam2.mp4", "clip8_cam3.mp4": "cam3.mp4"}

BLUR = {
    # one passer-by's lower legs at the far top edge, across the street (no face or body in frame), frames 0-44
    "clip8_cam1.mp4": [(0, 30, 300, 0, 144, 48), (31, 44, 200, 0, 170, 24)],
    "clip8_cam2.mp4": [],
    # two passers-by walking away (backs), frames 0-38; hidden behind the pillar after that. The phone pans, so
    # the boxes follow them in steps. Frames 21-22: tight boxes, so the suspect's face (in front of them) stays clear.
    "clip8_cam3.mp4": [
        (0, 3, 140, 94, 330, 402),
        (4, 7, 190, 74, 310, 360),
        (8, 11, 230, 50, 270, 330),
        (12, 15, 274, 46, 226, 300),
        (16, 19, 274, 26, 224, 294),
        (20, 20, 280, 44, 172, 236),
        (21, 21, 330, 70, 112, 190),
        (21, 21, 280, 70, 52, 56),
        (22, 22, 274, 64, 72, 196),
        (23, 25, 260, 50, 130, 206),
        (26, 29, 244, 30, 142, 230),
        (30, 33, 254, 24, 112, 202),
        (34, 38, 260, 20, 92, 132),
    ],
}
ENCODE = ["-an", "-map_metadata", "-1", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
          "-pix_fmt", "yuv420p", "-movflags", "+faststart"]  # crf 18: re-encoding loses little detail
FONTS = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def blur_graph(boxes: list[tuple]) -> tuple[str, str]:
    """ffmpeg filter graph: crop each box, blur it, overlay it back for its frames only."""
    parts = ["[0:v]split=%d[base]%s" % (len(boxes) + 1, "".join(f"[c{i}]" for i in range(len(boxes))))]
    last = "base"
    for i, (first, end, x, y, w, h) in enumerate(boxes):
        luma, chroma = min(30, min(w, h) // 2 - 1), min(15, min(w, h) // 4 - 1)  # boxblur caps radius by size
        parts.append(f"[c{i}]crop={w}:{h}:{x}:{y},boxblur={luma}:3:{chroma}:3[b{i}]")
        parts.append(f"[{last}][b{i}]overlay={x}:{y}:enable='between(n,{first},{end})'[v{i}]")
        last = f"v{i}"
    return ";".join(parts), f"[{last}]"


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                          "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check(src: Path, dst: Path) -> str:
    """'' if dst is a video-only H.264 clip with the same size, rate and frame count as src, else the problem."""
    a, b = probe(src)["streams"], probe(dst)["streams"]
    if [s["codec_type"] for s in b] != ["video"]:
        return f"streams are {[s['codec_type'] for s in b]}, want exactly one video stream (no audio)"
    keys = ("codec_name", "width", "height", "r_frame_rate", "nb_read_frames")
    diff = [k for k in keys if a[0].get(k) != b[0].get(k)]
    return f"differs from the source in {diff}" if diff else ""


def contact_sheet(clip: Path, boxes: list[tuple], png: Path) -> None:
    """Every frame in the blurred range, cropped 1:1 around the boxes (+40 px), labelled with its frame index."""
    x0 = max(0, min(b[2] for b in boxes) - 40) // 2 * 2
    y0 = max(0, min(b[3] for b in boxes) - 40) // 2 * 2
    x1, y1 = min(1280, max(b[2] + b[4] for b in boxes) + 40), min(720, max(b[3] + b[5] for b in boxes) + 40)
    first, last = min(b[0] for b in boxes), max(b[1] for b in boxes) + 1  # one unblurred frame after, to compare
    cols = 8 if x1 - x0 < 250 else 5
    rows = -(-(last - first + 1) // cols)
    font = next((f for f in FONTS if Path(f).is_file()), None)
    label = (f",drawtext=fontfile='{font.replace(':', chr(92) + ':')}':text='%{{n}}':x=4:y=4:fontsize=22:"
             "fontcolor=yellow:box=1:boxcolor=black@0.7") if font else ""
    vf = f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}{label},select='between(n\\,{first}\\,{last})',tile={cols}x{rows}"
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", vf, "-frames:v", "1", str(png)],
                   check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheets", action="store_true", help=f"also write review contact sheets to {REVIEW}")
    args = parser.parse_args()
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("ERROR: ffmpeg/ffprobe not on PATH (Brev: sudo apt-get install -y ffmpeg)", file=sys.stderr)
        return 2
    missing = [str(p) for p in [*(SRC / n for n in NAMES), *EXTRA_FILES] if not p.is_file()]
    if missing:
        print("ERROR: missing input files:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    problems = []
    for name, out_name in NAMES.items():
        src, dst, boxes = SRC / name, OUT / out_name, BLUR[name]
        if boxes:
            graph, final = blur_graph(boxes)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", graph,
                            "-map", final, *ENCODE, str(dst)], check=True)
        else:
            shutil.copyfile(src, dst)
        problem = check(src, dst)
        problems += [f"{out_name}: {problem}"] if problem else []
        print(f"{out_name} <- {name}: {len(boxes)} blur boxes, {'FAIL ' + problem if problem else 'ok'}")
        if args.sheets and boxes:
            contact_sheet(dst, boxes, REVIEW / f"{Path(out_name).stem}_blurred_frames.png")
    for path, out_name in EXTRA_FILES.items():
        shutil.copyfile(path, OUT / out_name)
        print(f"{out_name} <- {path}")
    print(f"done: {OUT}" + (f" (review sheets in {REVIEW})" if args.sheets else ""))
    for line in problems:
        print(f"FAILED {line}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
