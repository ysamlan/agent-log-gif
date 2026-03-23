"""Video output backends using ffmpeg (MP4 and AVIF).

Converts a sequence of (Image, duration_ms) frames into video files
by piping raw RGB frames to ffmpeg. Streams frames inline to avoid
holding all expanded frames in memory.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from PIL import Image

from agent_log_gif.backends import check_ffmpeg
from agent_log_gif.frame_store import FrameStore


def _preferred_av1_encoders() -> list[str]:
    """Return AV1 encoders in preference order for AVIF output."""
    return ["libsvtav1", "libaom-av1"]


@lru_cache(maxsize=1)
def _available_ffmpeg_encoders() -> set[str]:
    """Return the set of encoder names reported by ffmpeg."""
    check_ffmpeg()
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    )
    encoders = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    return encoders


def _select_av1_encoder(encoders: set[str] | None = None) -> str | None:
    """Choose the AV1 encoder to use for AVIF output."""
    available = encoders if encoders is not None else _available_ffmpeg_encoders()
    for encoder in _preferred_av1_encoders():
        if encoder in available:
            return encoder
    return None


def _avif_codec_args(encoder: str, cpu_count: int | None = None) -> list[str]:
    """Return AVIF codec args tuned for screen-content quality.

    Uses 10-bit color to reduce banding on dark backgrounds, screen-content
    mode (``scm=1``) for palette + intra-block-copy tools, and perceptual
    tuning (``tune=0``) to prioritise text sharpness over PSNR.
    """
    if encoder == "libsvtav1":
        return [
            "-c:v",
            "libsvtav1",
            "-preset",
            "6",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p10le",
            "-svtav1-params",
            "tune=0:scm=1:film-grain=0:enable-overlays=1",
        ]
    if cpu_count is None:
        threads = max(1, os.cpu_count() or 1)
    else:
        threads = max(1, cpu_count)
    if threads <= 4:
        cpu_used = 8
    elif threads <= 8:
        cpu_used = 7
    else:
        cpu_used = 6

    return [
        "-c:v",
        "libaom-av1",
        "-cpu-used",
        str(cpu_used),
        "-row-mt",
        "1",
        "-threads",
        str(threads),
        "-crf",
        "30",
        "-b:v",
        "0",
        "-pix_fmt",
        "yuv420p10le",
    ]


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
    use_raw = isinstance(frames, FrameStore)
    if use_raw:
        if len(frames) == 0:
            raise ValueError("Cannot create video from empty frame list")
        width, height = frames.image_size
    else:
        # Peek at first frame for dimensions
        import itertools

        frame_iter = iter(frames)
        try:
            first_img, first_dur = next(frame_iter)
        except StopIteration:
            raise ValueError("Cannot create video from empty frame list")
        width, height = first_img.size
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

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    # Stream frames inline: expand variable durations to fixed fps on the fly
    # Use raw_iter for FrameStore to skip PIL round-trip (zlib → raw bytes directly)
    frame_source = frames.raw_iter() if use_raw else frames
    for raw_or_img, duration_ms in frame_source:
        count = max(1, round(duration_ms / ms_per_frame))
        raw = raw_or_img if use_raw else raw_or_img.tobytes()
        for _ in range(count):
            proc.stdin.write(raw)

    proc.stdin.close()
    proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed")

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
    fps: int = 10,
) -> Path:
    """Save frames as an animated AVIF via ffmpeg.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .avif file.
        fps: Target frames per second.

    Returns:
        Path to the written AVIF file.
    """
    encoder = _select_av1_encoder()
    if encoder is None:
        raise RuntimeError(
            "AVIF output requires an ffmpeg build with an AV1 encoder. "
            "Install or use a build that includes libsvtav1 or libaom-av1."
        )
    codec_args = _avif_codec_args(encoder)
    return _encode_video(frames, output_path, fps, codec_args)
