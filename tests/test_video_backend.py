"""Tests for the video output backends (MP4, AVIF)."""

import shutil

import pytest
from PIL import Image

from agent_log_gif.backends.video import (
    _frames_to_fixed_fps,
    save_avif,
    save_mp4,
)
from agent_log_gif.frame_store import FrameStore


def _make_frame(color, duration_ms=100):
    """Helper: create a solid-color 100x100 frame."""
    img = Image.new("RGB", (100, 100), color)
    return (img, duration_ms)


class TestFramesToFixedFps:
    def test_short_duration_produces_one_frame(self):
        frames = _frames_to_fixed_fps([_make_frame("red", 50)], fps=15)
        assert len(frames) == 1

    def test_long_duration_repeats_frames(self):
        frames = _frames_to_fixed_fps([_make_frame("red", 1000)], fps=15)
        assert len(frames) == 15  # 1000ms at 15fps = 15 frames

    def test_multiple_frames(self):
        input_frames = [_make_frame("red", 200), _make_frame("blue", 400)]
        frames = _frames_to_fixed_fps(input_frames, fps=10)
        # 200ms at 10fps = 2 frames, 400ms at 10fps = 4 frames
        assert len(frames) == 6


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
class TestSaveMp4:
    def test_creates_mp4_file(self, tmp_path):
        frames = [_make_frame("red"), _make_frame("blue"), _make_frame("green")]
        output = tmp_path / "test.mp4"
        result = save_mp4(frames, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

    def test_empty_frames_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            save_mp4([], tmp_path / "test.mp4")

    def test_creates_parent_dirs(self, tmp_path):
        output = tmp_path / "sub" / "dir" / "test.mp4"
        frames = [_make_frame("red", 200)]
        save_mp4(frames, output)
        assert output.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
class TestSaveMp4FrameStore:
    def test_accepts_frame_store(self, tmp_path):
        store = FrameStore()
        store.append(Image.new("RGB", (100, 100), "red"), 100)
        store.append(Image.new("RGB", (100, 100), "blue"), 200)
        output = tmp_path / "test.mp4"
        result = save_mp4(store, output)
        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
class TestSaveAvif:
    def test_creates_avif_file(self, tmp_path):
        frames = [_make_frame("red"), _make_frame("blue"), _make_frame("green")]
        output = tmp_path / "test.avif"
        result = save_avif(frames, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

    def test_empty_frames_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            save_avif([], tmp_path / "test.avif")
