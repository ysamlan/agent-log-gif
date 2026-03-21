"""GIF output backend using Pillow.

Assembles animated GIF from a sequence of (Image, duration_ms) frames.
Optionally optimizes with gifsicle if available.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import click
from PIL import Image

from agent_log_gif.frame_store import FrameStore


def _build_palette(
    first_frame: Image.Image,
    colors: int = 256,
    palette_seeds: list[tuple[int, int, int]] | None = None,
) -> Image.Image:
    """Build a global palette from the first frame and optional seed colors.

    Creates a composite image by pasting a swatch of seed colors below the
    first frame, then quantizes the composite to produce a palette that
    includes both the antialiased frame content and all seed colors.
    """
    if palette_seeds:
        # Build a 1-row swatch from a flat byte buffer (one pixel per seed),
        # then resize vertically so octree quantization won't merge seeds.
        swatch_h = max(first_frame.height // 10, 2)
        row = b"".join(bytes(rgb) for rgb in palette_seeds)
        swatch = Image.frombytes("RGB", (len(palette_seeds), 1), row)
        swatch = swatch.resize((len(palette_seeds), swatch_h), Image.NEAREST)
        # Paste swatch below the first frame, stretched to frame width
        combined = Image.new("RGB", (first_frame.width, first_frame.height + swatch_h))
        combined.paste(first_frame, (0, 0))
        swatch_resized = swatch.resize((first_frame.width, swatch_h), Image.NEAREST)
        combined.paste(swatch_resized, (0, first_frame.height))
    else:
        combined = first_frame

    return combined.quantize(colors=colors, method=2, dither=Image.Dither.NONE)


def save_gif(
    frames: FrameStore | Iterable[tuple[Image.Image, int]],
    output_path: str | Path,
    size_limit_mb: int = 50,
    colors: int | None = None,
    palette_seeds: list[tuple[int, int, int]] | None = None,
) -> Path:
    """Save frames as an animated GIF.

    Uses a global palette derived from the first frame (plus optional seed
    colors) so all frames share identical palette indices, improving LZW
    compression. Dithering is disabled since terminal content is solid colors.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .gif file.
        size_limit_mb: Skip gifsicle for files larger than this.
        colors: Palette size, 2-256 (default: 256). None means 256.
        palette_seeds: RGB tuples to guarantee in the palette.

    Returns:
        Path to the written GIF file.

    Raises:
        ValueError: If frames is empty.
    """
    colors = colors or 256
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # We need durations up front for Pillow, and the first frame separately.
    # Use FrameStore.durations() if available (avoids decompressing images),
    # otherwise consume the iterable.
    if isinstance(frames, FrameStore):
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

    # Build global palette from first frame + seed colors
    first_img, _ = next(frame_iter)
    palette_ref = _build_palette(first_img, colors=colors, palette_seeds=palette_seeds)
    first_quantized = first_img.quantize(palette=palette_ref, dither=Image.Dither.NONE)

    def _quantize_rest():
        """Generator: quantize remaining frames against the global palette."""
        for img, _ in frame_iter:
            yield img.quantize(palette=palette_ref, dither=Image.Dither.NONE)

    first_quantized.save(
        str(output_path),
        save_all=True,
        append_images=_quantize_rest(),
        duration=durations,
        loop=0,
        disposal=2,  # restore to background between frames
    )

    # Try gifsicle optimization if available (skip for very large files)
    _optimize_with_gifsicle(output_path, size_limit_mb=size_limit_mb, colors=colors)

    return output_path


def _optimize_with_gifsicle(
    gif_path: Path, size_limit_mb: int = 50, colors: int = 256
) -> None:
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
        cmd = [
            "gifsicle",
            "-O3",
            "--lossy=80",
        ]
        if colors < 256:
            cmd += [f"--colors={colors}"]
        cmd += [str(gif_path), "-o", str(optimized_path)]
        subprocess.run(cmd, check=True)

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
