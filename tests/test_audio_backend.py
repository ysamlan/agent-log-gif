"""Tests for the audio mixing backend."""

import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import make_frame

from agent_log_gif.backends.audio import mix_audio
from agent_log_gif.backends.video import save_mp4


def _make_test_audio(path: Path, duration_secs: float = 5.0):
    """Generate a silent audio file for testing using ffmpeg."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=mono:d={duration_secs}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(path),
        ],
        capture_output=True,
        check=True,
    )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
class TestMixAudio:
    def test_mixes_audio_into_video(self, tmp_path):
        """Audio is mixed into the video file."""
        # Create a short test video
        frames = [make_frame("red", 500)] * 5
        video_path = tmp_path / "video.mp4"
        save_mp4(frames, video_path)

        # Create a test audio file
        audio_path = tmp_path / "music.mp3"
        _make_test_audio(audio_path, duration_secs=3.0)

        # Mix
        output = tmp_path / "output.mp4"
        result = mix_audio(video_path, audio_path, output)

        assert result == output
        assert output.exists()
        assert output.stat().st_size > video_path.stat().st_size

    def test_loop_audio(self, tmp_path):
        """--loop-music doesn't crash when audio is shorter than video."""
        frames = [make_frame("red", 500)] * 10  # ~5 seconds of video
        video_path = tmp_path / "video.mp4"
        save_mp4(frames, video_path)

        audio_path = tmp_path / "music.mp3"
        _make_test_audio(audio_path, duration_secs=1.0)  # shorter than video

        output = tmp_path / "output.mp4"
        mix_audio(video_path, audio_path, output, loop=True)
        assert output.exists()

    def test_missing_video_raises(self, tmp_path):
        audio_path = tmp_path / "music.mp3"
        _make_test_audio(audio_path)
        with pytest.raises(FileNotFoundError, match="Video"):
            mix_audio(tmp_path / "nope.mp4", audio_path, tmp_path / "out.mp4")

    def test_missing_audio_raises(self, tmp_path):
        frames = [make_frame("red")]
        video_path = tmp_path / "video.mp4"
        save_mp4(frames, video_path)
        with pytest.raises(FileNotFoundError, match="Music"):
            mix_audio(video_path, tmp_path / "nope.mp3", tmp_path / "out.mp4")
