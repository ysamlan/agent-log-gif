"""Video output backends using ffmpeg (MP4 and AVIF).

Converts a sequence of (Image, duration_ms) frames into video files
by piping raw RGB frames to ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image


def _check_ffmpeg():
    """Raise if ffmpeg is not available."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is required for video output but was not found on PATH.\n"
            "Install it with: apt install ffmpeg (Linux), brew install ffmpeg (macOS),\n"
            "or download from https://ffmpeg.org/download.html"
        )


def _frames_to_fixed_fps(
    frames: list[tuple[Image.Image, int]], fps: int = 15
) -> list[Image.Image]:
    """Convert variable-duration frames to fixed-fps frame sequence.

    Each source frame is repeated enough times to approximate its duration
    at the target fps.
    """
    ms_per_frame = 1000 / fps
    result = []
    for img, duration_ms in frames:
        count = max(1, round(duration_ms / ms_per_frame))
        result.extend([img] * count)
    return result


def save_mp4(
    frames: list[tuple[Image.Image, int]],
    output_path: str | Path,
    fps: int = 15,
) -> Path:
    """Save frames as an MP4 video via ffmpeg.

    Args:
        frames: List of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .mp4 file.
        fps: Target frames per second.

    Returns:
        Path to the written MP4 file.
    """
    if not frames:
        raise ValueError("Cannot create video from empty frame list")

    _check_ffmpeg()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fixed_frames = _frames_to_fixed_fps(frames, fps)
    width, height = fixed_frames[0].size

    cmd = [
        "ffmpeg",
        "-y",  # overwrite
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    for img in fixed_frames:
        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    _, stderr = proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr.decode()}")

    return output_path


def save_avif(
    frames: list[tuple[Image.Image, int]],
    output_path: str | Path,
    fps: int = 15,
) -> Path:
    """Save frames as an animated AVIF via ffmpeg.

    Args:
        frames: List of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .avif file.
        fps: Target frames per second.

    Returns:
        Path to the written AVIF file.
    """
    if not frames:
        raise ValueError("Cannot create video from empty frame list")

    _check_ffmpeg()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fixed_frames = _frames_to_fixed_fps(frames, fps)
    width, height = fixed_frames[0].size

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-c:v",
        "libaom-av1",
        "-crf",
        "30",
        "-b:v",
        "0",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    for img in fixed_frames:
        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    _, stderr = proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr.decode()}")

    return output_path
