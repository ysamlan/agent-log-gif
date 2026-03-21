"""GIF output backend using Pillow.

Assembles animated GIF from a sequence of (Image, duration_ms) frames.
Uses frame differencing (transparent unchanged pixels) to minimize LZW
encoding work and GIF file size. Optionally post-processes with gifsicle.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import click
from PIL import Image, ImageChops

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
    size_limit_mb: int = 200,
    colors: int | None = None,
    palette_seeds: list[tuple[int, int, int]] | None = None,
    gifsicle: bool = True,
) -> Path:
    """Save frames as an animated GIF with frame differencing.

    Uses a global palette derived from the first frame (plus optional seed
    colors). Subsequent frames encode only changed pixels via transparency,
    producing much smaller files and faster LZW encoding.

    When gifsicle is available and enabled, post-processes with
    ``gifsicle -O2 --lossy=80`` for further compression.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .gif file.
        size_limit_mb: Skip gifsicle for files larger than this (default 200).
        colors: Palette size, 2-256 (default: 256). One slot is reserved
                for transparency, so effective max is 255. None means 256.
        palette_seeds: RGB tuples to guarantee in the palette.
        gifsicle: Whether to post-process with gifsicle (default True).

    Returns:
        Path to the written GIF file.

    Raises:
        ValueError: If frames is empty.
    """
    # Reserve one palette slot for the transparent index
    colors = min((colors or 256), 255)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Materialize durations and frame iterator
    if isinstance(frames, FrameStore):
        if len(frames) == 0:
            raise ValueError("Cannot create GIF from empty frame list")
        durations = [max(d, 20) for d in frames.durations()]
        frame_iter = iter(frames)
    else:
        frame_list = list(frames)
        if not frame_list:
            raise ValueError("Cannot create GIF from empty frame list")
        durations = [max(d, 20) for _, d in frame_list]
        frame_iter = iter(frame_list)

    # Build global palette from first frame + seed colors
    first_img, _ = next(frame_iter)
    palette_ref = _build_palette(first_img, colors=colors, palette_seeds=palette_seeds)
    first_q = first_img.quantize(palette=palette_ref, dither=Image.Dither.NONE)

    # The transparent color index — quantized to `colors` colors, so
    # index `colors` is the first free slot
    transparent_idx = colors

    # Get the palette bytes for reuse
    palette_bytes = first_q.getpalette()

    # Previous frame pixel data for diffing (as flat bytes for speed)
    prev_data = first_q.tobytes()
    width, height = first_q.size

    def _make_diff_frames():
        """Yield diff frames: only changed pixels, rest transparent.

        Uses Pillow's C-level ImageChops to compute the diff mask (~0.6 ms
        per 740x650 frame). Both frames share the same global palette, so
        comparing raw P-mode byte values (palette indices) is correct.
        """
        nonlocal prev_data

        # Reusable transparent fill image
        trans_l = Image.new("L", (width, height), transparent_idx)
        # Precomputed LUT: 0->0, nonzero->255 (avoids per-frame lambda)
        change_lut = [0] + [255] * 255

        for img, _ in frame_iter:
            curr_q = img.quantize(palette=palette_ref, dither=Image.Dither.NONE)
            curr_data = curr_q.tobytes()

            # Treat P-mode index bytes as L-mode for C-speed comparison
            prev_l = Image.frombytes("L", (width, height), prev_data)
            curr_l = Image.frombytes("L", (width, height), curr_data)

            # difference(): 0 where same, nonzero where different
            diff_l = ImageChops.difference(prev_l, curr_l)
            # Binary mask: 0 where unchanged, 255 where changed
            mask = diff_l.point(change_lut)

            # composite: changed pixels from curr, unchanged from transparent
            result_l = Image.composite(curr_l, trans_l, mask)

            # Wrap as P-mode with the global palette
            diff_img = Image.frombytes("P", (width, height), result_l.tobytes())
            diff_img.putpalette(palette_bytes)
            diff_img.info["transparency"] = transparent_idx
            yield diff_img

            prev_data = curr_data

    # Set transparency on first frame (fully opaque, but Pillow needs
    # the GCE block for consistency)
    first_q.info["transparency"] = transparent_idx

    first_q.save(
        str(output_path),
        save_all=True,
        append_images=_make_diff_frames(),
        duration=durations,
        loop=0,
        disposal=1,  # do not dispose — previous frame stays visible
        transparency=transparent_idx,
    )

    if gifsicle:
        _optimize_with_gifsicle(
            output_path, size_limit_mb=size_limit_mb, colors=colors
        )

    return output_path


def _optimize_with_gifsicle(
    gif_path: Path, size_limit_mb: int = 200, colors: int = 256
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
            "-O2",
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
