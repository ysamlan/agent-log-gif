"""Video output backends using ffmpeg (MP4 and AVIF).

Converts a sequence of (Image, duration_ms) frames into video files
by piping raw RGB frames to ffmpeg. Streams frames inline to avoid
holding all expanded frames in memory.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from agent_log_gif.backends import check_ffmpeg

if TYPE_CHECKING:
    from agent_log_gif.frame_store import FrameStore


def _frames_to_fixed_fps(
    frames: Iterable[tuple[Image.Image, int]], fps: int = 15
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


def _encode_video(
    frames: FrameStore | Iterable[tuple[Image.Image, int]],
    output_path: str | Path,
    fps: int,
    codec_args: list[str],
) -> Path:
    """Shared encoding pipeline for video backends.

    Streams frames directly to ffmpeg, expanding variable-duration frames
    to fixed-fps inline without building an intermediate list.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the output file.
        fps: Target frames per second.
        codec_args: Codec-specific ffmpeg flags (e.g. libx264 or libaom-av1).

    Returns:
        Path to the written video file.
    """
    # Get image size and validate non-empty
    if hasattr(frames, "image_size") and hasattr(frames, "__len__"):
        if len(frames) == 0:
            raise ValueError("Cannot create video from empty frame list")
        width, height = frames.image_size
    else:
        # Peek at first frame for dimensions
        frame_iter = iter(frames)
        try:
            first_img, first_dur = next(frame_iter)
        except StopIteration:
            raise ValueError("Cannot create video from empty frame list")
        width, height = first_img.size

        # Chain the first frame back in
        import itertools

        frames = itertools.chain([(first_img, first_dur)], frame_iter)

    check_ffmpeg()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ms_per_frame = 1000 / fps

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
        *codec_args,
        str(output_path),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # Stream frames inline: expand variable durations to fixed fps on the fly
    for img, duration_ms in frames:
        count = max(1, round(duration_ms / ms_per_frame))
        raw = img.tobytes()
        for _ in range(count):
            proc.stdin.write(raw)

    proc.stdin.close()
    _, stderr = proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr.decode()}")

    return output_path


def save_mp4(
    frames: FrameStore | Iterable[tuple[Image.Image, int]],
    output_path: str | Path,
    fps: int = 15,
) -> Path:
    """Save frames as an MP4 video via ffmpeg.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .mp4 file.
        fps: Target frames per second.

    Returns:
        Path to the written MP4 file.
    """
    codec_args = [
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
    ]
    return _encode_video(frames, output_path, fps, codec_args)


def save_avif(
    frames: FrameStore | Iterable[tuple[Image.Image, int]],
    output_path: str | Path,
    fps: int = 15,
) -> Path:
    """Save frames as an animated AVIF via ffmpeg.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .avif file.
        fps: Target frames per second.

    Returns:
        Path to the written AVIF file.
    """
    codec_args = [
        "-c:v",
        "libaom-av1",
        "-crf",
        "30",
        "-b:v",
        "0",
        "-pix_fmt",
        "yuv420p",
    ]
    return _encode_video(frames, output_path, fps, codec_args)
