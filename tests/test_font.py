"""Smoke test: Pillow can load the bundled JetBrains Mono font."""

from pathlib import Path

from PIL import ImageFont


def test_bundled_font_loads():
    """Verify the bundled JetBrains Mono TTF is loadable by Pillow."""
    font_path = (
        Path(__file__).parent.parent
        / "src"
        / "agent_log_gif"
        / "fonts"
        / "JetBrainsMono-Regular.ttf"
    )
    assert font_path.exists(), f"Font file not found at {font_path}"

    font = ImageFont.truetype(str(font_path), size=16)
    assert font is not None

    # Verify we can measure text with it
    bbox = font.getbbox("Hello")
    assert bbox[2] > 0  # width > 0
    assert bbox[3] > 0  # height > 0


def test_font_is_monospace():
    """Verify each character has the same width (monospace)."""
    font_path = (
        Path(__file__).parent.parent
        / "src"
        / "agent_log_gif"
        / "fonts"
        / "JetBrainsMono-Regular.ttf"
    )
    font = ImageFont.truetype(str(font_path), size=16)

    widths = set()
    for char in "abcdefghijklmnopqrstuvwxyz0123456789":
        w = font.getlength(char)
        widths.add(round(w, 2))

    assert len(widths) == 1, f"Font is not monospace: widths={widths}"
