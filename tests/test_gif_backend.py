"""Tests for the GIF output backend."""

import subprocess

import pytest
from conftest import make_frame
from PIL import Image

from agent_log_gif.backends.gif import _optimize_with_gifsicle, save_gif
from agent_log_gif.frame_store import FrameStore


class TestSaveGif:
    def test_creates_gif_file(self, tmp_path):
        """Output file exists and is a GIF."""
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
        output = tmp_path / "test.gif"
        result = save_gif(frames, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

        # Verify it's actually a GIF
        with Image.open(output) as img:
            assert img.format == "GIF"

    def test_gif_is_animated(self, tmp_path):
        """Output GIF has multiple frames."""
        frames = [make_frame("red"), make_frame("blue"), make_frame("green")]
        output = tmp_path / "test.gif"
        save_gif(frames, output)

        with Image.open(output) as img:
            assert img.is_animated
            assert img.n_frames == 3

    def test_single_frame(self, tmp_path):
        """Single frame produces a valid GIF."""
        frames = [make_frame("red")]
        output = tmp_path / "test.gif"
        save_gif(frames, output)

        with Image.open(output) as img:
            assert img.format == "GIF"

    def test_empty_frames_raises(self, tmp_path):
        """Empty frame list raises ValueError."""

        with pytest.raises(ValueError, match="empty"):
            save_gif([], tmp_path / "test.gif")

    def test_creates_parent_dirs(self, tmp_path):
        """Parent directories are created if needed."""
        output = tmp_path / "sub" / "dir" / "test.gif"
        frames = [make_frame("red")]
        save_gif(frames, output)
        assert output.exists()

    def test_durations_preserved(self, tmp_path):
        """Frame durations are set correctly."""
        frames = [
            make_frame("red", 100),
            make_frame("blue", 200),
            make_frame("green", 500),
        ]
        output = tmp_path / "test.gif"
        save_gif(frames, output)

        with Image.open(output) as img:
            # GIF stores duration per frame
            durations = []
            for i in range(img.n_frames):
                img.seek(i)
                durations.append(img.info.get("duration", 0))
            assert durations == [100, 200, 500]

    def test_accepts_frame_store(self, tmp_path):
        """save_gif works with FrameStore input."""
        store = FrameStore()
        store.append(Image.new("RGB", (100, 100), "red"), 100)
        store.append(Image.new("RGB", (100, 100), "blue"), 200)
        output = tmp_path / "test.gif"
        save_gif(store, output)

        with Image.open(output) as img:
            assert img.is_animated
            assert img.n_frames == 2


class TestGifsicleInvocation:
    def test_gifsicle_inherits_stderr(self, monkeypatch, tmp_path):
        gif_path = tmp_path / "test.gif"
        gif_path.write_bytes(b"gif")
        optimized_path = gif_path.with_suffix(".opt.gif")
        optimized_path.write_bytes(b"smaller")
        recorded = {}

        monkeypatch.setattr(
            "agent_log_gif.backends.gif.shutil.which", lambda name: "/usr/bin/gifsicle"
        )

        def fake_run(cmd, check=False, stderr=None):
            recorded["cmd"] = cmd
            recorded["check"] = check
            recorded["stderr"] = stderr
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(subprocess, "run", fake_run)

        _optimize_with_gifsicle(gif_path)

        assert recorded["stderr"] is None
        assert recorded["check"] is True
