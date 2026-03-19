"""Audio mixing for video output via ffmpeg.

Attaches a music track to an MP4 video with optional looping and fade-out.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_log_gif.backends import check_ffmpeg


def mix_audio(
    video_path: str | Path,
    music_path: str | Path,
    output_path: str | Path,
    loop: bool = False,
    fade_duration: float = 3.0,
) -> Path:
    """Mix a music track into a video file.

    Args:
        video_path: Path to the input video (MP4).
        music_path: Path to the music file (mp3, wav, etc.).
        output_path: Path for the output video with audio.
        loop: If True, loop the music to cover the full video duration.
              If False and the music is shorter, it stops early.
        fade_duration: Duration of fade-out at the end in seconds.

    Returns:
        Path to the output video with audio.
    """
    check_ffmpeg()

    video_path = Path(video_path)
    music_path = Path(music_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not music_path.exists():
        raise FileNotFoundError(f"Music file not found: {music_path}")

    # Get video duration for fade calculation
    video_duration = _get_duration(video_path)

    # Build ffmpeg command
    cmd = ["ffmpeg", "-y"]

    # Input: video
    cmd.extend(["-i", str(video_path)])

    # Input: audio (with optional loop)
    if loop:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend(["-i", str(music_path)])

    # Map video from first input, audio from second
    cmd.extend(["-map", "0:v", "-map", "1:a"])

    # Copy video codec (no re-encoding), encode audio
    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"])

    # Trim to video length
    cmd.extend(["-shortest"])

    # Apply fade-out at the end
    if video_duration > fade_duration:
        fade_start = video_duration - fade_duration
        cmd.extend(["-af", f"afade=t=out:st={fade_start:.2f}:d={fade_duration:.2f}"])

    cmd.append(str(output_path))

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mixing failed:\n{result.stderr.decode()}")

    return output_path


def _get_duration(video_path: Path) -> float:
    """Get the duration of a video file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0
