"""Output backends for GIF, video, and audio."""

import shutil


def check_ffmpeg():
    """Raise if ffmpeg is not available."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is required for video output but was not found on PATH.\n"
            "Install it with: apt install ffmpeg (Linux), brew install ffmpeg (macOS),\n"
            "or download from https://ffmpeg.org/download.html"
        )
