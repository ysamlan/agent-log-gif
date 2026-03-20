"""Tests for the video output backends (MP4, AVIF)."""

import shutil

import pytest
from conftest import make_frame
from PIL import Image

from agent_log_gif.backends.video import (
    save_avif,
    save_mp4,
)
from agent_log_gif.frame_store import FrameStore


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
class TestSaveMp4:
    def test_creates_mp4_file(self, tmp_path):
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
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
        frames = [make_frame("red", 200)]
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
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
        output = tmp_path / "test.avif"
        result = save_avif(frames, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

    def test_empty_frames_raises(self, tmp_path):
        with pytest.raises(ValueError, match="empty"):
            save_avif([], tmp_path / "test.avif")
