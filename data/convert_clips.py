"""Convert phone clips into one replay-friendly format: 720p, constant 10 fps, H.264 8-bit, no audio.

Why: iPhone clips are HEVC (often 10-bit HDR) at a variable frame rate with audio. OpenCV builds don't all decode
HEVC, a variable frame rate breaks feeds' frame-index clock, and the audio may carry bystanders' voices (privacy).
Each clip gets a converted copy next to it, same name with .mp4:

    ffmpeg -i in -vf "scale=-2:720,format=yuv420p" -r 10 -fps_mode cfr -an -c:v libx264 -preset veryfast -crf 23            -movflags +faststart out.mp4
(+faststart puts the index at the front of the file, so the dashboard's clip pop-up starts playing sooner.)

Run from the repo root, on the Brev box (needs ffmpeg on PATH: sudo apt-get install -y ffmpeg):
    python data/convert_clips.py data/raw/staged          # every clip in every take<N>/ folder below it
    python data/convert_clips.py data/raw/staged/take1    # one take
    python data/convert_clips.py "<folder>" --out "<other folder>" --force

Then point the clip log's clip_file cells at the .mp4 names (take1_cam01.mov -> take1_cam01.mp4) and rebuild.
Copies that already exist are skipped unless --force. .mp4 clips can't be converted in place (the copy would
overwrite the original); pass --out for those. The originals are never changed. Stdlib only.

It never converts its own outputs, even with --out and --force: an .mp4 next to a same-named clip with another
suffix (take1_cam01.mp4 beside take1_cam01.MOV) is taken as an earlier copy and skipped, and so is anything
inside the --out folder. So a real .mp4 original must not share its name with a .mov in the same folder.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
FILTERS = "scale=-2:720,format=yuv420p"  # 720 px tall, width keeps the aspect ratio; 8-bit 4:2:0 plays anywhere
ENCODE = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart"]
PARTIAL = ".partial.mp4"  # ffmpeg writes here first, so a stopped run never leaves a half clip under the real name


def find_clips(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
                  and not p.name.endswith(PARTIAL))


def has_original(clip: Path) -> bool:
    """True if clip is an .mp4 with a same-named clip of another suffix beside it, i.e. our earlier copy."""
    return clip.suffix.lower() == ".mp4" and any(
        p.stem == clip.stem and p.name != clip.name and p.suffix.lower() in VIDEO_SUFFIXES
        for p in clip.parent.iterdir())


def is_our_output(clip: Path, own_dir: Path | None) -> bool:
    """A file this script wrote: a copy next to its original, or anything inside own_dir (an --out folder that
    sits inside the input folder)."""
    return has_original(clip) or (own_dir is not None and own_dir.resolve() in clip.resolve().parents)


def ffmpeg_cmd(ffmpeg: str, src: Path, dst: Path, old_ffmpeg: bool) -> list[str]:
    # ffmpeg < 5.1 (Ubuntu 22.04's apt package is 4.4) has no -fps_mode; -vsync cfr is the same thing there
    cfr = ["-vsync", "cfr"] if old_ffmpeg else ["-fps_mode", "cfr"]
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", FILTERS, "-r", "10",
            *cfr, *ENCODE, str(dst)]


def convert(ffmpeg: str, src: Path, dst: Path, old_ffmpeg: bool) -> tuple[bool, bool, str]:
    """(converted?, old_ffmpeg, error text). Retries once with -vsync if this ffmpeg predates -fps_mode."""
    tmp = dst.with_name(dst.stem + PARTIAL)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(ffmpeg_cmd(ffmpeg, src, tmp, old_ffmpeg), capture_output=True, text=True,
                            errors="replace")
    if result.returncode != 0 and not old_ffmpeg and "fps_mode" in result.stderr:
        old_ffmpeg = True
        result = subprocess.run(ffmpeg_cmd(ffmpeg, src, tmp, old_ffmpeg), capture_output=True, text=True,
                                errors="replace")
    if result.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return False, old_ffmpeg, (result.stderr.strip() or f"ffmpeg exit code {result.returncode}")
    os.replace(tmp, dst)
    return True, old_ffmpeg, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="folder with clips (searched recursively)")
    parser.add_argument("--out", type=Path, help="write the copies here, keeping sub-folders (default: next to "
                                                 "each original)")
    parser.add_argument("--force", action="store_true", help="convert again even if the copy exists")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")

    if not args.folder.is_dir():
        print(f"ERROR: folder not found: {args.folder}", file=sys.stderr)
        return 2
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ERROR: ffmpeg is not on PATH, so nothing was converted.\n"
              "  run this on Brev: sudo apt-get install -y ffmpeg\n"
              "  (then re-run the same command)", file=sys.stderr)
        return 2
    clips = find_clips(args.folder)
    if not clips:
        print(f"no clips ({', '.join(sorted(VIDEO_SUFFIXES))}) in {args.folder}")
        return 1

    if args.out and args.out.resolve() == args.folder.resolve():
        args.out = None  # same as the default: copies next to the originals
    own_dir = args.out if args.out and args.folder.resolve() in args.out.resolve().parents else None

    converted = skipped = ours = 0
    failed: list[str] = []
    old_ffmpeg = False
    for src in clips:
        if is_our_output(src, own_dir):
            ours += 1
            continue  # never re-encode a copy over the copy made from the original
        rel = src.relative_to(args.folder).with_suffix(".mp4")
        dst = (args.out / rel) if args.out else src.with_suffix(".mp4")
        if dst.resolve() == src.resolve():
            print(f"skip {src}: already .mp4; pass --out <folder> to convert it into another folder")
            skipped += 1
            continue
        if dst.exists() and not args.force:
            print(f"skip {src}: {dst.name} exists (--force converts again)")
            skipped += 1
            continue
        print(f"convert {src} -> {dst}", flush=True)
        ok, old_ffmpeg, error = convert(ffmpeg, src, dst, old_ffmpeg)
        if ok:
            converted += 1
        else:
            failed.append(f"{src}: {error.splitlines()[-1] if error else 'failed'}")
            print(f"ERROR {src}:\n{error}", file=sys.stderr)

    print(f"done: {converted} converted, {skipped} skipped, {len(failed)} failed"
          + (f" ({ours} earlier copies left alone)" if ours else ""))
    if converted:
        print("next: point the clip log's clip_file cells at the .mp4 names, then run data/build_site.py "
              "(with --check-clips) and python -m feeds.replay --check")
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
