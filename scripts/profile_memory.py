#!/usr/bin/env python3
"""Profile memory and timing for the animation pipeline.

Generates synthetic multi-turn sessions and measures:
- tracemalloc: Python-level allocation tracking
- resource.getrusage: true RSS including C allocations (Pillow)
- time.perf_counter: wall-clock per phase

Usage:
    python scripts/profile_memory.py [--turns 5,10,15,20]
"""

from __future__ import annotations

import argparse
import resource
import statistics
import time
import tracemalloc

from agent_log_gif.animator import generate_frames
from agent_log_gif.renderer import TerminalRenderer
from agent_log_gif.theme import TerminalTheme
from agent_log_gif.timeline import EventType, ReplayEvent


def _rss_mb() -> float:
    """Current max RSS in MB (includes C allocations like Pillow)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


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


def _profile_run(
    num_turns: int,
    renderer: TerminalRenderer,
    render_times: list[float],
) -> dict:
    """Run one profiling pass and return metrics."""
    events = _synthetic_events(num_turns)

    # Monkey-patch render_frame for per-frame timing
    from agent_log_gif.renderer import TerminalRenderer as TR

    _orig = TR.render_frame
    render_times.clear()

    def _timed(self, lines, cursor_pos=None):
        t0 = time.perf_counter()
        r = _orig(self, lines, cursor_pos)
        render_times.append(time.perf_counter() - t0)
        return r

    TR.render_frame = _timed

    # Per-turn tracking
    turn_data: list[dict] = []

    def on_turn(turn: int, total: int) -> None:
        turn_data.append(
            {
                "turn": turn,
                "rss_mb": _rss_mb(),
                "time": time.perf_counter(),
            }
        )

    # Phase 1: Frame generation
    tracemalloc.start()
    rss_before = _rss_mb()
    t_gen_start = time.perf_counter()

    frames = generate_frames(
        events,
        renderer=renderer,
        on_turn=on_turn,
        speed=2.0,
        spinner_time=0.5,
    )

    t_gen_end = time.perf_counter()
    gen_snapshot = tracemalloc.take_snapshot()
    rss_after_gen = _rss_mb()

    # Phase 2: GIF save (to /dev/null equivalent — measure quantization cost)
    import tempfile
    from pathlib import Path

    from agent_log_gif.backends.gif import save_gif

    tmp = Path(tempfile.mktemp(suffix=".gif"))
    t_save_start = time.perf_counter()
    try:
        save_gif(frames, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    t_save_end = time.perf_counter()
    rss_after_save = _rss_mb()

    tracemalloc.stop()

    # Restore original
    TR.render_frame = _orig

    # Compute render_frame stats
    avg_render = statistics.mean(render_times) * 1000 if render_times else 0
    p95_render = (
        sorted(render_times)[int(len(render_times) * 0.95)] * 1000
        if render_times
        else 0
    )

    return {
        "turns": num_turns,
        "frames": len(frames),
        "gen_s": t_gen_end - t_gen_start,
        "save_s": t_save_end - t_save_start,
        "rss_before": rss_before,
        "rss_after_gen": rss_after_gen,
        "rss_after_save": rss_after_save,
        "peak_rss": rss_after_save,
        "avg_render_ms": avg_render,
        "p95_render_ms": p95_render,
        "snapshot": gen_snapshot,
        "turn_data": turn_data,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Profile animation pipeline memory/timing"
    )
    parser.add_argument(
        "--turns",
        default="5,10,15,20",
        help="Comma-separated turn counts to test (default: 5,10,15,20)",
    )
    parser.add_argument(
        "--tracemalloc-top",
        type=int,
        default=10,
        help="Number of top allocation sites to show (default: 10)",
    )
    args = parser.parse_args()

    turn_counts = [int(t.strip()) for t in args.turns.split(",")]
    theme = TerminalTheme()
    renderer = TerminalRenderer(theme)
    render_times: list[float] = []

    results = []
    for n in turn_counts:
        print(f"\n--- Profiling {n} turns ---")
        r = _profile_run(n, renderer, render_times)
        results.append(r)

        # Per-turn detail
        if r["turn_data"]:
            print("\n  Per-turn detail:")
            prev_time = r["turn_data"][0]["time"] if r["turn_data"] else 0
            for td in r["turn_data"]:
                dt = td["time"] - prev_time
                print(
                    f"    Turn {td['turn']:2d}  RSS={td['rss_mb']:.0f}MB  dt={dt:.2f}s"
                )
                prev_time = td["time"]

    # Summary table
    print("\n" + "=" * 85)
    print(
        f"{'Turns':>5}  {'Frames':>6}  {'Gen(s)':>7}  {'Save(s)':>7}  "
        f"{'PeakRSS(MB)':>11}  {'AvgRender(ms)':>13}  {'P95Render(ms)':>13}"
    )
    print("-" * 85)
    for r in results:
        print(
            f"{r['turns']:5d}  {r['frames']:6d}  {r['gen_s']:7.1f}  {r['save_s']:7.1f}  "
            f"{r['peak_rss']:11.0f}  {r['avg_render_ms']:13.1f}  {r['p95_render_ms']:13.1f}"
        )
    print("=" * 85)

    # tracemalloc top-N from the largest run
    last = results[-1]
    print(f"\ntracemalloc top-{args.tracemalloc_top} ({last['turns']} turns):")
    top_stats = last["snapshot"].statistics("lineno")
    for stat in top_stats[: args.tracemalloc_top]:
        print(f"  {stat}")


if __name__ == "__main__":
    main()
