"""Build the publishable open-data package for test clip 8 (Hugging Face dataset, CC BY 4.0).

Writes data/raw/publish/clarity-clip8/ (gitignored): cam1.mp4, cam2.mp4, cam3.mp4 with every person who is not
one of the actors blurred, plus copies of data/ground_truth/take1.json and data/staged/clip_log_take1.csv, and
the dataset card data/staged/DATASET_CARD.md as README.md. Upload that folder as is (steps in the card).

    python data/publish_clip8.py                 # build + check (one video stream, no metadata, same frames)
    python data/publish_clip8.py --sheets        # also write review sheets to data/raw/publish/review/
    python data/publish_clip8.py --src <folder>  # read clip8_cam1.mp4 ... clip8_cam3.mp4 from another folder

--src must hold the UNBLURRED converted clips (default data/raw/staged_unblurred/take1). The script refuses the
demo folder data/raw/staged/take1 (its cam1/cam3 are already blurred), its own output folders, and any clip that
looks already processed, so no clip is ever blurred twice.

Blur boxes are (first_frame, last_frame, x, y, w, h) in pixels of the 1280x720 clips, read from frame contact
sheets. Each box gets a heavy 3-pass box blur for its frames; the filter leaves every other pixel alone (the
re-encode at CRF 18 changes them only slightly). A clip without boxes keeps its video stream as is. Every output
is written without metadata or chapters (iPhone clips can carry GPS, recording time and phone model there), then
probed: exactly one video stream, the source's codec, size, rate and frame count, and no tags beyond the ones
ffmpeg writes itself.

Review sheets (--sheets): <cam>_full_frames.png for every clip (whole frames, 2 per second by default), to check
that no passer-by is left unblurred, and <cam>_blurred_frames.png for clips with boxes (every blurred frame,
cropped around the boxes). Needs ffmpeg and ffprobe on PATH. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("data/raw/staged_unblurred/take1")  # the unblurred converted clips
OUT = Path("data/raw/publish/clarity-clip8")
REVIEW = Path("data/raw/publish/review")
NOT_SOURCES = {Path("data/raw/staged/take1"): "the demo folder, whose cam1/cam3 are already blurred",
               OUT: "this script's output folder", REVIEW: "this script's review folder"}
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
CRF = 18  # re-encoding at 18 loses little detail; convert_clips.py uses 23, so a clip at 18 was blurred here
MARK = "Clarity clip 8 publish package (data/publish_clip8.py)"  # comment tag on every output
CLEAN = ["-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", "-metadata", f"comment={MARK}",
         "-movflags", "+faststart"]
ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF), "-pix_fmt", "yuv420p"]
TAGS_OK = {"major_brand", "minor_version", "compatible_brands", "encoder", "comment",  # container, set by ffmpeg
           "language", "handler_name", "vendor_id"}  # per stream, set by ffmpeg
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
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_format", "-show_streams",
                          "-show_chapters", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def tag_keys(info: dict) -> set[str]:
    """Every metadata key in a probed file: container tags plus each stream's tags."""
    return {*info["format"].get("tags", {}), *(k for s in info["streams"] for k in s.get("tags", {}))}


def processed(clip: Path) -> str:
    """Why clip looks like this script's output already, or '' if it looks like an unblurred original."""
    if probe(clip)["format"].get("tags", {}).get("comment") == MARK:
        return "it carries this script's marker tag"
    # x264 writes its settings into the video stream, and metadata stripping doesn't remove them
    settings = re.search(rb"x264 - core[^\x00]{0,3000}? crf=([\d.]+)", clip.read_bytes())
    if settings and float(settings.group(1)) == CRF:
        return f"it was encoded at CRF {CRF} like this script's blurred clips; convert_clips.py uses 23"
    return ""


def check(src: Path, dst: Path) -> tuple[str, str]:
    """(problem or '', summary): dst must be exactly one video stream with src's codec, size, rate and frame count,
    with no chapters and no tags beyond the ones ffmpeg writes itself (no location, date or device)."""
    a, b = probe(src), probe(dst)
    kinds = [s["codec_type"] for s in b["streams"]]
    summary = f"{b['streams'][0].get('nb_read_frames')} frames, tags {sorted(tag_keys(b))}" if b["streams"] else ""
    if kinds != ["video"]:
        return f"streams are {kinds}, want exactly one video stream (no audio)", summary
    video = next(s for s in a["streams"] if s["codec_type"] == "video")
    keys = ("codec_name", "width", "height", "r_frame_rate", "nb_read_frames")
    diff = [k for k in keys if video.get(k) != b["streams"][0].get(k)]
    if diff:
        return f"differs from the source in {diff}", summary
    extra = sorted(tag_keys(b) - TAGS_OK)
    if extra or b.get("chapters"):
        return f"metadata left: tags {extra}, {len(b.get('chapters', []))} chapters", summary
    return "", summary


def label(text: str, size: int, y: int) -> str:
    """',drawtext=...' writing text at (8, y) (drawtext expands %{n} to the frame index), or '' without a font."""
    font = next((f for f in FONTS if Path(f).is_file()), None)
    return (f",drawtext=fontfile='{font.replace(':', chr(92) + ':')}':text='{text}':x=8:y={y}:fontsize={size}:"
            "fontcolor=yellow:box=1:boxcolor=black@0.7") if font else ""


def sheet(clip: Path, vf: str, png: Path) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", vf, "-frames:v", "1", str(png)],
                   check=True)


def contact_sheet(clip: Path, boxes: list[tuple], png: Path) -> None:
    """Every frame in the blurred range, cropped 1:1 around the boxes (+40 px), labelled with its frame index."""
    x0 = max(0, min(b[2] for b in boxes) - 40) // 2 * 2
    y0 = max(0, min(b[3] for b in boxes) - 40) // 2 * 2
    x1, y1 = min(1280, max(b[2] + b[4] for b in boxes) + 40), min(720, max(b[3] + b[5] for b in boxes) + 40)
    first, last = min(b[0] for b in boxes), max(b[1] for b in boxes) + 1  # one unblurred frame after, to compare
    cols = 8 if x1 - x0 < 250 else 5
    rows = -(-(last - first + 1) // cols)
    text = label("%{n}", 22, 4)
    sheet(clip, f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}{text},select='between(n\\,{first}\\,{last})',"
                f"tile={cols}x{rows}", png)


def full_sheet(clip: Path, fps: float, png: Path) -> None:
    """Whole frames at about fps per second, full size, 4 per row; frame index and time in a strip above each, so
    the label never covers the picture."""
    video = probe(clip)["streams"][0]
    num, den = map(int, video["r_frame_rate"].split("/"))
    step = max(1, round(num / den / fps))
    rows = -(-len(range(0, int(video["nb_read_frames"]), step)) // 4)
    text = label("frame %{n}   %{pts\\:hms}", 26, 7)
    sheet(clip, f"pad=iw:ih+40:0:40{text},select='not(mod(n\\,{step}))',tile=4x{rows}:padding=8:color=gray", png)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", type=Path, default=SRC,
                        help=f"folder with the UNBLURRED clip8_cam1-3.mp4 (default {SRC})")
    parser.add_argument("--sheets", action="store_true", help=f"also write review sheets to {REVIEW}")
    parser.add_argument("--sheet-fps", type=float, default=2.0, help="frames per second on the full-frame sheets")
    args = parser.parse_args()
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("ERROR: ffmpeg/ffprobe not on PATH (Brev: sudo apt-get install -y ffmpeg)", file=sys.stderr)
        return 2
    for folder, what in NOT_SOURCES.items():
        if args.src.resolve().is_relative_to(folder.resolve()):
            print(f"ERROR: refusing --src {args.src}: it is {what}, and a clip must never be blurred twice; "
                  f"use the unblurred originals in {SRC} (the default)", file=sys.stderr)
            return 2
    missing = [str(p) for p in [*(args.src / n for n in NAMES), *EXTRA_FILES] if not p.is_file()]
    if missing:
        print("ERROR: missing input files:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2
    for name in NAMES:
        why = processed(args.src / name)
        if why:
            print(f"ERROR: refusing {args.src / name}: it looks already processed ({why}), and a clip must never "
                  f"be blurred twice; use the unblurred originals in {SRC}", file=sys.stderr)
            return 2

    OUT.mkdir(parents=True, exist_ok=True)
    old = [*(OUT / n for n in [*NAMES.values(), *EXTRA_FILES.values()]), *OUT.glob("*.partial.mp4")]
    for path in old + (list(REVIEW.glob("cam*_frames.png")) if args.sheets else []):
        path.unlink(missing_ok=True)  # so a failed run never leaves the last run's files looking current
    problems, sheets = [], []
    for name, out_name in NAMES.items():
        src, dst, boxes = args.src / name, OUT / out_name, BLUR[name]
        tmp = dst.with_name(dst.stem + ".partial.mp4")
        if boxes:
            graph, final = blur_graph(boxes)
            video = ["-filter_complex", graph, "-map", final, *ENCODE]
        else:  # nothing to blur: the video stream is copied as is, only the container is rewritten
            video = ["-map", "0:v:0", "-c:v", "copy"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *video, *CLEAN, str(tmp)], check=True)
        problem, summary = check(src, tmp)
        if problem:
            tmp.unlink()
            problems.append(f"{out_name}: {problem}")
        else:
            tmp.replace(dst)
        print(f"{out_name} <- {src}: {len(boxes)} blur boxes, {'FAIL ' + problem if problem else 'ok'} ({summary})")
        if args.sheets and not problem:
            stem = Path(out_name).stem
            sheets.append(REVIEW / f"{stem}_full_frames.png")
            full_sheet(dst, args.sheet_fps, sheets[-1])
            if boxes:
                sheets.append(REVIEW / f"{stem}_blurred_frames.png")
                contact_sheet(dst, boxes, sheets[-1])
    for path, out_name in EXTRA_FILES.items():
        shutil.copyfile(path, OUT / out_name)
        print(f"{out_name} <- {path}")
    for path in sheets:
        print(f"review sheet: {path}")
    print(f"done: {OUT}")
    for line in problems:
        print(f"FAILED {line}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
