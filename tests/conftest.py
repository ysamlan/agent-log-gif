"""Pytest configuration and fixtures for agent-log-gif tests."""

from PIL import Image


def make_frame(color, duration_ms=100):
    """Helper: create a solid-color 100x100 (Image, duration_ms) frame."""
    img = Image.new("RGB", (100, 100), color)
    return (img, duration_ms)


def make_striped_frame(*colors, duration_ms=100):
    """Helper: create a 100x100 frame with horizontal stripes of given colors.

    Useful as a first frame to seed the global palette with multiple colors.
    """
    from PIL import ImageDraw

    img = Image.new("RGB", (100, 100))
    stripe_height = 100 // len(colors)
    draw = ImageDraw.Draw(img)
    for i, color in enumerate(colors):
        y0 = i * stripe_height
        y1 = (i + 1) * stripe_height
        draw.rectangle([0, y0, 99, y1 - 1], fill=color)
    return (img, duration_ms)
