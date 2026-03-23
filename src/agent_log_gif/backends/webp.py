"""WebP output backend using Pillow.

Assembles animated WebP from a sequence of (Image, duration_ms) frames.
Uses Pillow's native WebP support — no external tools required.

Defaults to lossless encoding because terminal content (flat-color regions
with sharp text edges) compresses smaller with lossless prediction than
with lossy transforms.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PIL import Image

from agent_log_gif.frame_store import FrameStore


def save_webp(
    frames: FrameStore | Iterable[tuple[Image.Image, int]],
    output_path: str | Path,
    lossless: bool = True,
    quality: int = 80,
    method: int = 4,
) -> Path:
    """Save frames as an animated WebP.

    Args:
        frames: FrameStore or iterable of (PIL.Image, duration_ms) tuples.
        output_path: Path to write the .webp file.
        lossless: Use lossless encoding (default True). Lossless is both
                  bit-perfect and smaller than lossy for terminal content.
        quality: Lossy quality (1-100, default 80) when lossless=False.
                 Ignored in lossless mode.
        method: Encoding method (0-6, default 4). Higher = slower but
                smaller file. Applies to both lossy and lossless modes.

    Returns:
        Path to the written WebP file.

    Raises:
        ValueError: If frames is empty.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(frames, FrameStore):
        if len(frames) == 0:
            raise ValueError("Cannot create WebP from empty frame list")
        durations = frames.durations()
        frame_iter = iter(frames)
    else:
        frame_list = list(frames)
        if not frame_list:
            raise ValueError("Cannot create WebP from empty frame list")
        durations = [d for _, d in frame_list]
        frame_iter = iter(frame_list)

    first_img, _ = next(frame_iter)
    rest = [img for img, _ in frame_iter]

    save_kwargs: dict = {
        "format": "WEBP",
        "save_all": True,
        "append_images": rest,
        "duration": durations,
        "loop": 0,
        "lossless": lossless,
        "method": method,
    }
    if not lossless:
        save_kwargs["quality"] = quality

    first_img.save(str(output_path), **save_kwargs)

    return output_path
