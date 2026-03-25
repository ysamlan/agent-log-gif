#!/usr/bin/env python3
"""Benchmark MP4 encoding settings for screen content.

Generates frames from the demo session, then encodes with different
x264 configurations to find the best settings for terminal content.

Usage:
    uv run python scripts/bench_mp4_encoding.py
"""

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION = ROOT / "scripts" / "demo_session.jsonl"
OUT_DIR = ROOT / "tmp" / "mp4-bench"


def generate_frames():
    """Render the demo session into a FrameStore."""
    from agent_log_gif.animator import generate_frames as gen
    from agent_log_gif.parsers import parse_session_file
    from agent_log_gif.timeline import loglines_to_timeline, visible_events

    data = parse_session_file(str(SESSION))
    loglines = data.get("loglines", [])
    events = loglines_to_timeline(loglines)
    events = visible_events(events)

    return gen(events)


# Each config: (name, codec_args)
CONFIGS = [
    (
        "baseline",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "tune-animation",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "aq3",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "tune+aq3",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "23",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "tune+aq3+deblock-1",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "23",
            "-aq-mode",
            "3",
            "-x264-params",
            "deblock=-1,-1",
            "-movflags",
            "+faststart",
        ],
    ),
    # CRF sweep with tune+aq3
    (
        "tune+aq3 crf=20",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "20",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "tune+aq3 crf=26",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "26",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "tune+aq3 crf=28",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "28",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    # Preset sweep with tune+aq3
    (
        "tune+aq3 preset=fast",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            "-tune",
            "animation",
            "-crf",
            "23",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    (
        "tune+aq3 preset=slow",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "slow",
            "-tune",
            "animation",
            "-crf",
            "23",
            "-aq-mode",
            "3",
            "-movflags",
            "+faststart",
        ],
    ),
    # tune-animation alone CRF sweep
    (
        "tune crf=26",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-tune",
            "animation",
            "-crf",
            "26",
            "-movflags",
            "+faststart",
        ],
    ),
    # Extract sample frames for visual comparison
    (
        "baseline crf=26",
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "26",
            "-movflags",
            "+faststart",
        ],
    ),
]


def bench_config(name, codec_args, frames, fps=15):
    """Encode frames with the given codec_args, return (time_s, size_kb)."""
    from agent_log_gif.backends.video import _encode_video

    out = OUT_DIR / f"{name.replace(' ', '_').replace('+', '_')}.mp4"

    t0 = time.perf_counter()
    _encode_video(frames, out, fps, codec_args)
    elapsed = time.perf_counter() - t0

    size_kb = out.stat().st_size / 1024
    return elapsed, size_kb


def get_video_info(name):
    """Get codec profile info via ffprobe."""
    out = OUT_DIR / f"{name.replace(' ', '_').replace('+', '_')}.mp4"
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "stream=profile,pix_fmt",
            "-of",
            "csv=p=0",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating frames from demo session...", flush=True)
    frames = generate_frames()
    print(f"  {len(frames)} frames ready\n", flush=True)

    results = []
    for name, codec_args in CONFIGS:
        print(f"  Encoding: {name}...", end="", flush=True)
        elapsed, size_kb = bench_config(name, codec_args, frames)
        info = get_video_info(name)
        results.append((name, elapsed, size_kb, info))
        print(f" {elapsed:.2f}s, {size_kb:.0f} KB ({info})")

    # Print markdown table
    print("\n## Results\n")
    print(f"| {'Config':<30} | {'Time (s)':>8} | {'Size (KB)':>9} | {'Profile':<20} |")
    print(f"|{'-' * 32}|{'-' * 10}|{'-' * 11}|{'-' * 22}|")
    baseline_size = results[0][2]
    for name, elapsed, size_kb, info in results:
        delta = ((size_kb - baseline_size) / baseline_size) * 100
        sign = "+" if delta > 0 else ""
        print(
            f"| {name:<30} | {elapsed:>8.2f} | {size_kb:>9.0f} | {info:<20} | {sign}{delta:.1f}%"
        )


def extract_frames():
    """Extract frame 50 from key configs for visual comparison."""
    configs_to_compare = ["baseline", "tune_animation", "tune_aq3"]
    for name in configs_to_compare:
        mp4 = OUT_DIR / f"{name}.mp4"
        png = OUT_DIR / f"{name}_frame50.png"
        if mp4.exists():
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(mp4),
                    "-vf",
                    "select=eq(n\\,50)",
                    "-vframes",
                    "1",
                    str(png),
                ],
                capture_output=True,
            )
            if png.exists():
                print(f"  Extracted {png.name} ({png.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
    print("\n## Visual comparison frames")
    extract_frames()
