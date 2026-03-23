#!/usr/bin/env python3
"""Benchmark encoding speed, output size, and quality across formats.

Generates realistic terminal frames at multiple session sizes and
encodes each to every supported format/mode, printing comparison tables.

Usage:
    python scripts/benchmark_formats.py [--turns 3,10,20]
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

from agent_log_gif.animator import generate_frames
from agent_log_gif.backends.gif import save_gif
from agent_log_gif.backends.webp import save_webp
from agent_log_gif.frame_store import FrameStore
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


def _psnr_frame(ref: Image.Image, test: Image.Image) -> float:
    """Compute PSNR between two same-size RGB images."""
    ref_data = ref.tobytes()
    test_data = test.tobytes()
    if ref_data == test_data:
        return float("inf")
    n = len(ref_data)
    mse = sum((a - b) ** 2 for a, b in zip(ref_data, test_data)) / n
    if mse == 0:
        return float("inf")
    return 10 * math.log10(255**2 / mse)


def _sample_psnr(
    frames: FrameStore, output_path: Path, fmt: str, sample_indices: list[int]
) -> float:
    """Decode output file and compute avg PSNR across sample frames."""
    psnr_values = []

    if fmt == "webp":
        with Image.open(output_path) as img:
            for idx in sample_indices:
                if idx >= img.n_frames:
                    continue
                img.seek(idx)
                decoded = img.convert("RGB")
                ref_img, _ = frames[idx]
                psnr_values.append(_psnr_frame(ref_img, decoded))
    elif fmt == "gif":
        with Image.open(output_path) as img:
            for idx in sample_indices:
                if idx >= img.n_frames:
                    continue
                img.seek(idx)
                decoded = img.convert("RGB")
                ref_img, _ = frames[idx]
                psnr_values.append(_psnr_frame(ref_img, decoded))
    elif fmt in ("avif", "mp4"):
        # Use ffmpeg to extract sample frames
        for idx in sample_indices:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(output_path),
                "-vf",
                f"select=eq(n\\,{idx})",
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ]
            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0 or not proc.stdout:
                continue
            ref_img, _ = frames[idx]
            w, h = ref_img.size
            expected = w * h * 3
            if len(proc.stdout) != expected:
                continue
            decoded = Image.frombytes("RGB", (w, h), proc.stdout)
            psnr_values.append(_psnr_frame(ref_img, decoded))

    if not psnr_values:
        return float("nan")
    return sum(psnr_values) / len(psnr_values)


def _write_png_frames(frames: FrameStore, tmp_dir: Path) -> list[tuple[Path, int]]:
    """Write all frames as PNG files, return list of (path, duration_ms)."""
    frame_files = []
    for i, (img, duration_ms) in enumerate(frames):
        path = tmp_dir / f"frame_{i:05d}.png"
        img.save(str(path), format="PNG")
        frame_files.append((path, duration_ms))
    return frame_files


def _run_img2webp(
    frame_files: list[tuple[Path, int]],
    output_path: Path,
    extra_args: list[str] | None = None,
    per_frame_args: list[str] | None = None,
) -> tuple[float, int]:
    """Run img2webp and return (elapsed_seconds, file_size_bytes)."""
    cmd = ["img2webp", "-loop", "0"]
    if extra_args:
        cmd.extend(extra_args)

    for path, duration_ms in frame_files:
        if per_frame_args:
            cmd.extend(per_frame_args)
        cmd.extend(["-d", str(duration_ms), str(path)])

    cmd.extend(["-o", str(output_path)])

    t0 = time.perf_counter()
    subprocess.run(cmd, capture_output=True, check=True)
    elapsed = time.perf_counter() - t0
    size = output_path.stat().st_size
    return elapsed, size


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

    has_img2webp = bool(shutil.which("img2webp"))
    save_avif = _try_avif()

    theme = TerminalTheme()
    renderer = TerminalRenderer(theme)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        for num_turns in turn_counts:
            events = _synthetic_events(num_turns)
            print(f"Generating frames for {num_turns} turns...", end=" ", flush=True)
            t0 = time.perf_counter()
            frames = generate_frames(
                events, renderer=renderer, speed=2.0, spinner_time=0.5
            )
            gen_time = time.perf_counter() - t0
            frame_size = frames.image_size
            n_frames = len(frames)
            print(
                f"{n_frames} frames ({frame_size[0]}x{frame_size[1]}) "
                f"in {gen_time:.1f}s"
            )

            # Sample frames for PSNR (first, middle, last)
            sample_indices = [0, n_frames // 4, n_frames // 2, 3 * n_frames // 4]
            sample_indices = [i for i in sample_indices if i < n_frames]

            # Write PNG frames for img2webp (shared across all img2webp configs)
            png_dir = tmp / f"png_{num_turns}"
            png_dir.mkdir(exist_ok=True)

            if has_img2webp:
                print("  Writing PNG frames...", end=" ", flush=True)
                t0 = time.perf_counter()
                frame_files = _write_png_frames(frames, png_dir)
                png_time = time.perf_counter() - t0
                print(f"{len(frame_files)} files in {png_time:.1f}s")

            # ---- Baselines ----
            results: list[tuple[str, float, int, float]] = []  # name, time, size, psnr

            # GIF (gifsicle --lossy=80)
            gif_path = tmp / f"{num_turns}t.gif"
            elapsed, size = _benchmark_one(
                lambda f, o: save_gif(
                    f,
                    o,
                    gifsicle=bool(shutil.which("gifsicle")),
                    lossy=80,
                ),
                frames,
                gif_path,
            )
            psnr = _sample_psnr(frames, gif_path, "gif", sample_indices)
            results.append(("GIF lossy=80", elapsed, size, psnr))
            gif_size = size

            # AVIF
            if save_avif:
                avif_path = tmp / f"{num_turns}t.avif"
                elapsed, size = _benchmark_one(save_avif, frames, avif_path)
                psnr = _sample_psnr(frames, avif_path, "avif", sample_indices)
                results.append(("AVIF crf=30", elapsed, size, psnr))

            # ---- Pillow WebP ----
            webp_ll_path = tmp / f"{num_turns}t_pillow_ll.webp"
            elapsed, size = _benchmark_one(
                lambda f, o: save_webp(f, o, lossless=True),
                frames,
                webp_ll_path,
            )
            psnr = _sample_psnr(frames, webp_ll_path, "webp", sample_indices)
            results.append(("Pillow ll", elapsed, size, psnr))

            # ---- img2webp modes ----
            if has_img2webp:
                # Lossless
                out = tmp / f"{num_turns}t_i2w_lossless.webp"
                elapsed, size = _run_img2webp(
                    frame_files, out, per_frame_args=["-lossless", "-m", "4"]
                )
                psnr = _sample_psnr(frames, out, "webp", sample_indices)
                results.append(("i2w ll", elapsed, size, psnr))

                # Near-lossless sweep
                for nl in [0, 20, 40, 60, 80]:
                    out = tmp / f"{num_turns}t_i2w_nl{nl}.webp"
                    elapsed, size = _run_img2webp(
                        frame_files,
                        out,
                        extra_args=["-near_lossless", str(nl)],
                        per_frame_args=["-m", "4"],
                    )
                    psnr = _sample_psnr(frames, out, "webp", sample_indices)
                    results.append((f"i2w nl={nl}", elapsed, size, psnr))

                # Lossy sweep
                for q in [50, 75, 90]:
                    out = tmp / f"{num_turns}t_i2w_q{q}.webp"
                    elapsed, size = _run_img2webp(
                        frame_files,
                        out,
                        per_frame_args=["-lossy", "-q", str(q), "-m", "4"],
                    )
                    psnr = _sample_psnr(frames, out, "webp", sample_indices)
                    results.append((f"i2w q={q}", elapsed, size, psnr))

            # ---- Print table ----
            print(
                f"\n  {'Config':<16} {'Size':>10} {'Time(s)':>9} "
                f"{'vs GIF':>8} {'PSNR(dB)':>10}"
            )
            print(f"  {'-' * 16} {'-' * 10} {'-' * 9} {'-' * 8} {'-' * 10}")
            for name, elapsed, size, psnr in results:
                ratio = size / gif_size if gif_size else 0
                psnr_str = "inf" if psnr == float("inf") else f"{psnr:.1f}"
                if math.isnan(psnr):
                    psnr_str = "n/a"
                print(
                    f"  {name:<16} {_fmt_size(size):>10} {elapsed:>9.2f} "
                    f"{ratio:>7.0%} {psnr_str:>10}"
                )
            print()


if __name__ == "__main__":
    main()
