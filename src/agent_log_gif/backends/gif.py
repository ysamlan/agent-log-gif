"""GIF output backend using Pillow.

Assembles animated GIF from a sequence of (Image, duration_ms) frames.
Optionally optimizes with gifsicle if available.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

import click
from PIL import Image

if TYPE_CHECKING:
    from agent_log_gif.frame_store import FrameStore


def save_gif(
    frames: FrameStore | Iterable[tuple[Image.Image, int]],
    output_path: str | Path,
    size_limit_mb: int = 50,
) -> Path:
    """Save frames as an animated GIF.

    Streams quantization one frame at a time to avoid holding all frames
    in memory simultaneously. Accepts a FrameStore or any iterable of
    (PIL.Image, duration_ms) tuples.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .gif file.

    Returns:
        Path to the written GIF file.

    Raises:
        ValueError: If frames is empty.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # We need durations up front for Pillow, and the first frame separately.
    # Use FrameStore.durations() if available (avoids decompressing images),
    # otherwise consume the iterable.
    if hasattr(frames, "durations") and hasattr(frames, "__len__"):
        # FrameStore path: extract durations without decompressing
        if len(frames) == 0:
            raise ValueError("Cannot create GIF from empty frame list")
        durations = [max(d, 20) for d in frames.durations()]
        frame_iter = iter(frames)
    else:
        # Generic iterable: materialize to get durations + first frame
        frame_list = list(frames)
        if not frame_list:
            raise ValueError("Cannot create GIF from empty frame list")
        durations = [max(d, 20) for _, d in frame_list]
        frame_iter = iter(frame_list)

    # Quantize and save first frame
    first_img, _ = next(frame_iter)
    first_quantized = first_img.quantize(colors=256, method=2)

    def _quantize_rest():
        """Generator: quantize remaining frames one at a time."""
        for img, _ in frame_iter:
            yield img.quantize(colors=256, method=2)

    first_quantized.save(
        str(output_path),
        save_all=True,
        append_images=_quantize_rest(),
        duration=durations,
        loop=0,
        disposal=2,  # restore to background between frames
    )

    # Try gifsicle optimization if available (skip for very large files)
    _optimize_with_gifsicle(output_path, size_limit_mb=size_limit_mb)

    return output_path


def _optimize_with_gifsicle(gif_path: Path, size_limit_mb: int = 50) -> None:
    """Optimize GIF with gifsicle if available. Modifies file in-place."""
    if not shutil.which("gifsicle"):
        return

    original_size = gif_path.stat().st_size
    original_mb = original_size / (1024 * 1024)
    if original_mb > size_limit_mb:
        click.echo(
            f"GIF is {original_mb:.0f} MB — skipping gifsicle optimization (too large). "
            f"Consider --format mp4 for long sessions.",
            err=True,
        )
        return
    optimized_path = gif_path.with_suffix(".opt.gif")

    try:
        subprocess.run(
            [
                "gifsicle",
                "-O3",
                "--lossy=80",
                str(gif_path),
                "-o",
                str(optimized_path),
            ],
            capture_output=True,
            check=True,
        )

        optimized_size = optimized_path.stat().st_size
        if optimized_size < original_size:
            optimized_path.replace(gif_path)
            reduction = (1 - optimized_size / original_size) * 100
            click.echo(
                f"gifsicle: {original_size:,} → {optimized_size:,} bytes "
                f"({reduction:.0f}% smaller)"
            )
        else:
            optimized_path.unlink()
    except (subprocess.CalledProcessError, OSError):
        # gifsicle failed — keep original
        if optimized_path.exists():
            optimized_path.unlink()
