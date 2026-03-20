"""Pytest configuration and fixtures for agent-log-gif tests."""

from PIL import Image


def make_frame(color, duration_ms=100):
    """Helper: create a solid-color 100x100 (Image, duration_ms) frame."""
    img = Image.new("RGB", (100, 100), color)
    return (img, duration_ms)
