import sys
from pathlib import Path

import cv2


def sample_frames(video_path: str, count: int = 4, width: int = 640, shift: float = 0.0) -> list[bytes]:
    """Return `count` evenly spaced frames from the video as JPEG bytes.

    `shift` (between -0.5 and 0.5) nudges every sample within its slice; training uses it to get
    several different views of the same clip. Evaluation always uses the default 0.
    """
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count}")

    video = cv2.VideoCapture(video_path)
    if not video.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    total = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        video.release()
        raise ValueError(f"Video reports no frames (live streams aren't supported here): {video_path}")
    # Centre each sample in its slice of the video, e.g. 12.5%, 37.5%, 62.5%, 87.5% for 4.
    positions = [min(total - 1, max(0, int(total * (i + 0.5 + shift) / count))) for i in range(count)]

    frames: list[bytes] = []
    for position in positions:
        video.set(cv2.CAP_PROP_POS_FRAMES, position)
        ok, image = video.read()
        if not ok:
            continue
        if image.shape[1] > width:  # only shrink; never upscale small videos
            height = max(1, int(image.shape[0] * width / image.shape[1]))
            image = cv2.resize(image, (width, height))
        ok, jpeg = cv2.imencode(".jpg", image)
        if ok:
            frames.append(jpeg.tobytes())

    video.release()
    if not frames:
        raise ValueError(f"No frames could be read from: {video_path}")
    return frames


if __name__ == "__main__":
    video_path, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(sample_frames(video_path), 1):
        (out_dir / f"frame{i}.jpg").write_bytes(frame)
    print(f"Saved frames to {out_dir}")
