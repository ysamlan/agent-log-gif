"""GIF output backend using Pillow.

Assembles animated GIF from a sequence of (Image, duration_ms) frames.
Optionally optimizes with gifsicle if available.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click
from PIL import Image


def save_gif(
    frames: list[tuple[Image.Image, int]],
    output_path: str | Path,
) -> Path:
    """Save frames as an animated GIF.

    Args:
        frames: List of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .gif file.

    Returns:
        Path to the written GIF file.

    Raises:
        ValueError: If frames is empty.
    """
    if not frames:
        raise ValueError("Cannot create GIF from empty frame list")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    images = [f[0] for f in frames]
    durations = [f[1] for f in frames]

    # Pillow requires minimum 20ms per frame (browser limitation)
    durations = [max(d, 20) for d in durations]

    # Convert to palette mode for GIF (reduces file size significantly)
    palette_images = [img.quantize(colors=256, method=2) for img in images]

    palette_images[0].save(
        str(output_path),
        save_all=True,
        append_images=palette_images[1:],
        duration=durations,
        loop=0,
        disposal=2,  # restore to background between frames
    )

    # Try gifsicle optimization if available
    _optimize_with_gifsicle(output_path)

    return output_path


def _optimize_with_gifsicle(gif_path: Path) -> None:
    """Optimize GIF with gifsicle if available. Modifies file in-place."""
    if not shutil.which("gifsicle"):
        return

    original_size = gif_path.stat().st_size
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
