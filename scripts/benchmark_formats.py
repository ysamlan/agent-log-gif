#!/usr/bin/env python3
"""Benchmark encoding speed and output size across GIF, WebP, and AVIF.

Generates realistic terminal frames at multiple session sizes and
encodes each to every supported format, printing a comparison table.

Usage:
    python scripts/benchmark_formats.py [--turns 3,10,20]
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from agent_log_gif.animator import generate_frames
from agent_log_gif.backends.gif import save_gif
from agent_log_gif.backends.webp import save_webp
from agent_log_gif.renderer import TerminalRenderer
from agent_log_gif.theme import TerminalTheme
from agent_log_gif.timeline import EventType, ReplayEvent


def _synthetic_events(num_turns: int) -> list[ReplayEvent]:
    """Generate synthetic ReplayEvent list with the given number of turns."""
    events: list[ReplayEvent] = []
    for i in range(num_turns):
        user_text = f"Turn {i + 1}: Can you help me with task number {i + 1}? " * 2
        assistant_text = (
            f"Sure, I'll help with task {i + 1}. Here's what I found: "
            + "The quick brown fox jumps over the lazy dog. " * 8
        )
        events.append(ReplayEvent(type=EventType.USER_MESSAGE, text=user_text))
        events.append(
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text=assistant_text)
        )
    return events


def _fmt_size(size_bytes: int) -> str:
    """Format file size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    kb = size_bytes / 1024
    if kb < 1024:
        return f"{kb:.0f} KB"
    return f"{kb / 1024:.1f} MB"


def _try_avif():
    """Return save_avif if ffmpeg + AV1 encoder available, else None."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        from agent_log_gif.backends.video import _select_av1_encoder, save_avif

        if _select_av1_encoder() is None:
            return None
        return save_avif
    except Exception:
        return None


def _try_mp4():
    """Return save_mp4 if ffmpeg available, else None."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        from agent_log_gif.backends.video import save_mp4

        return save_mp4
    except Exception:
        return None


def _benchmark_one(save_fn, frames, output_path) -> tuple[float, int]:
    """Encode frames and return (elapsed_seconds, file_size_bytes)."""
    t0 = time.perf_counter()
    save_fn(frames, output_path)
    elapsed = time.perf_counter() - t0
    size = output_path.stat().st_size
    return elapsed, size


def main():
    parser = argparse.ArgumentParser(description="Benchmark format encoding")
    parser.add_argument(
        "--turns",
        default="3,10,20",
        help="Comma-separated turn counts (default: 3,10,20)",
    )
    args = parser.parse_args()

    turn_counts = [int(t.strip()) for t in args.turns.split(",")]

    # Discover available formats
    save_avif = _try_avif()
    save_mp4 = _try_mp4()

    formats: list[tuple[str, object, dict]] = [
        ("GIF", save_gif, {"gifsicle": bool(shutil.which("gifsicle"))}),
        ("WebP", save_webp, {}),
    ]
    if save_mp4:
        formats.append(("MP4", save_mp4, {}))
    if save_avif:
        formats.append(("AVIF", save_avif, {}))

    print(f"Formats: {', '.join(name for name, _, _ in formats)}")
    print(f"Turn counts: {turn_counts}\n")

    theme = TerminalTheme()
    renderer = TerminalRenderer(theme)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        for num_turns in turn_counts:
            # Generate frames once for this tier
            events = _synthetic_events(num_turns)
            print(f"Generating frames for {num_turns} turns...", end=" ", flush=True)
            t0 = time.perf_counter()
            frames = generate_frames(
                events, renderer=renderer, speed=2.0, spinner_time=0.5
            )
            gen_time = time.perf_counter() - t0
            frame_size = frames.image_size
            print(
                f"{len(frames)} frames ({frame_size[0]}x{frame_size[1]}) "
                f"in {gen_time:.1f}s"
            )

            # Encode to each format
            results = []
            for name, save_fn, kwargs in formats:
                ext = name.lower()
                output = tmp / f"{num_turns}t.{ext}"
                elapsed, size = _benchmark_one(
                    lambda f, o, fn=save_fn, kw=kwargs: fn(f, o, **kw),
                    frames,
                    output,
                )
                results.append((name, elapsed, size))

            # Print table
            print(f"\n  {'Format':<8} {'Size':>10} {'Time(s)':>9} {'vs GIF size':>12}")
            print(f"  {'-' * 8} {'-' * 10} {'-' * 9} {'-' * 12}")
            gif_size = results[0][2]  # GIF is always first
            for name, elapsed, size in results:
                ratio = size / gif_size if gif_size else 0
                print(
                    f"  {name:<8} {_fmt_size(size):>10} {elapsed:>9.2f} {ratio:>11.1%}"
                )
            print()


if __name__ == "__main__":
    main()
