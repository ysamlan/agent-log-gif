"""Tests for the video output backends (MP4, AVIF)."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from agent_log_gif.backends.video import (
    _avif_codec_args,
    _preferred_av1_encoders,
    _select_av1_encoder,
    save_avif,
    save_mp4,
)
from agent_log_gif.frame_store import FrameStore
from conftest import make_frame


class TestEncodeVideoInvocation:
    def test_ffmpeg_inherits_stderr(self, monkeypatch, tmp_path):
        recorded = {}

        class DummyProc:
            def __init__(self):
                self.stdin = self
                self.returncode = 0
                self._written = bytearray()

            def write(self, data):
                self._written.extend(data)

            def communicate(self):
                return (b"", b"")

            def close(self):
                return None

        def fake_popen(cmd, stdin=None, stderr=None):
            recorded["cmd"] = cmd
            recorded["stdin"] = stdin
            recorded["stderr"] = stderr
            output_path = Path(cmd[-1])
            output_path.write_bytes(b"ok")
            return DummyProc()

        monkeypatch.setattr("agent_log_gif.backends.video.check_ffmpeg", lambda: None)
        monkeypatch.setattr(subprocess, "Popen", fake_popen)

        output = tmp_path / "test.mp4"
        save_mp4([make_frame("red")], output)

        assert recorded["stderr"] is None


class TestAvifCodecArgs:
    def test_aom_uses_faster_multithreaded_settings(self):
        args = _avif_codec_args("libaom-av1", cpu_count=14)

        assert args == [
            "-c:v",
            "libaom-av1",
            "-cpu-used",
            "6",
            "-row-mt",
            "1",
            "-threads",
            "14",
            "-crf",
            "36",
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
        ]

    def test_aom_uses_faster_cpu_used_on_lower_core_machines(self):
        args = _avif_codec_args("libaom-av1", cpu_count=4)
        cpu_used_index = args.index("-cpu-used")
        threads_index = args.index("-threads")
        assert args[cpu_used_index + 1] == "8"
        assert args[threads_index + 1] == "4"

    def test_aom_threads_are_clamped_to_at_least_one(self):
        args = _avif_codec_args("libaom-av1", cpu_count=0)
        threads_index = args.index("-threads")
        assert args[threads_index + 1] == "1"

    def test_svt_uses_tuned_preset(self):
        args = _avif_codec_args("libsvtav1", cpu_count=14)

        assert args == [
            "-c:v",
            "libsvtav1",
            "-preset",
            "10",
            "-crf",
            "36",
            "-pix_fmt",
            "yuv420p",
        ]


class TestAvifEncoderSelection:
    def test_prefers_svt_when_available(self):
        encoder = _select_av1_encoder({"libsvtav1", "libaom-av1"})
        assert encoder == "libsvtav1"

    def test_falls_back_to_aom(self):
        assert _select_av1_encoder({"libaom-av1"}) == "libaom-av1"

    def test_returns_none_when_no_supported_encoder(self):
        assert _select_av1_encoder({"h264"}) is None

    def test_preferred_encoder_order_is_explicit(self):
        assert _preferred_av1_encoders() == ["libsvtav1", "libaom-av1"]


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
