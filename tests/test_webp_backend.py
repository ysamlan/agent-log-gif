"""Tests for the WebP output backend."""

import pytest
from PIL import Image

from agent_log_gif.backends.webp import save_webp
from agent_log_gif.frame_store import FrameStore
from conftest import make_frame


class TestSaveWebp:
    def test_creates_webp_file(self, tmp_path):
        """Output file exists and is a WebP."""
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
        output = tmp_path / "test.webp"
        result = save_webp(frames, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

        with Image.open(output) as img:
            assert img.format == "WEBP"

    def test_webp_is_animated(self, tmp_path):
        """Output WebP has multiple frames."""
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
        output = tmp_path / "test.webp"
        save_webp(frames, output)

        with Image.open(output) as img:
            assert img.is_animated
            assert img.n_frames == 3

    def test_single_frame(self, tmp_path):
        """Single frame produces a valid WebP."""
        frames = [make_frame("red")]
        output = tmp_path / "test.webp"
        save_webp(frames, output)

        with Image.open(output) as img:
            assert img.format == "WEBP"

    def test_empty_frames_raises(self, tmp_path):
        """Empty frame list raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            save_webp([], tmp_path / "test.webp")

    def test_empty_frame_store_raises(self, tmp_path):
        """Empty FrameStore raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            save_webp(FrameStore(), tmp_path / "test.webp")

    def test_creates_parent_dirs(self, tmp_path):
        """Parent directories are created if needed."""
        output = tmp_path / "sub" / "dir" / "test.webp"
        frames = [make_frame("red")]
        save_webp(frames, output)
        assert output.exists()

    def test_varying_durations_accepted(self, tmp_path):
        """Frames with different durations produce a valid animated WebP."""
        frames = [
            make_frame("red", 100),
            make_frame("blue", 200),
            make_frame("green", 500),
        ]
        output = tmp_path / "test.webp"
        save_webp(frames, output)

        with Image.open(output) as img:
            assert img.is_animated
            assert img.n_frames == 3

    def test_accepts_frame_store(self, tmp_path):
        """save_webp works with FrameStore input."""
        store = FrameStore()
        store.append(Image.new("RGB", (100, 100), "red"), 100)
        store.append(Image.new("RGB", (100, 100), "blue"), 200)
        output = tmp_path / "test.webp"
        save_webp(store, output)

        with Image.open(output) as img:
            assert img.is_animated
            assert img.n_frames == 2

    def test_default_is_lossless(self, tmp_path):
        """Default lossless mode produces bit-perfect roundtrip."""
        frames = [make_frame("red"), make_frame("blue")]
        output = tmp_path / "test.webp"
        save_webp(frames, output)

        with Image.open(output) as img:
            img.seek(0)
            pixel = img.convert("RGB").getpixel((50, 50))
            assert pixel == (255, 0, 0)

    def test_lossy_quality_parameter(self, tmp_path):
        """Lower lossy quality produces smaller files with complex content."""
        import random

        random.seed(42)
        complex_frames = []
        for _ in range(5):
            img = Image.new("RGB", (200, 200))
            pixels = img.load()
            for x in range(200):
                for y in range(200):
                    pixels[x, y] = (
                        random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255),
                    )
            complex_frames.append((img, 100))

        high_q = tmp_path / "high.webp"
        low_q = tmp_path / "low.webp"
        save_webp(complex_frames, high_q, lossless=False, quality=95)
        save_webp(complex_frames, low_q, lossless=False, quality=10)

        assert low_q.stat().st_size < high_q.stat().st_size

    def test_lossless_smaller_than_lossy_for_terminal_content(self, tmp_path):
        """Lossless beats lossy for flat-color terminal-like frames."""
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
        lossless_out = tmp_path / "lossless.webp"
        lossy_out = tmp_path / "lossy.webp"
        save_webp(frames, lossless_out, lossless=True)
        save_webp(frames, lossy_out, lossless=False, quality=80)

        assert lossless_out.stat().st_size <= lossy_out.stat().st_size
