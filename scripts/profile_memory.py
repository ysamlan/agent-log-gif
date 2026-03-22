#!/usr/bin/env python3
"""Profile memory and timing for the animation pipeline.

Generates synthetic multi-turn sessions and measures:
- tracemalloc: Python-level allocation tracking
- resource.getrusage: true RSS including C allocations (Pillow)
- time.perf_counter: wall-clock per phase

Usage:
    python scripts/profile_memory.py [--turns 5,10,15,20]
    python scripts/profile_memory.py --breakdown --turns 10
"""

from __future__ import annotations

import argparse
import resource
import statistics
import time
import tracemalloc

from PIL import Image, ImageDraw

from agent_log_gif.animator import generate_frames
from agent_log_gif.renderer import HIGHLIGHT_MARKER, TerminalRenderer
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


# ---------------------------------------------------------------------------
# Per-operation breakdown instrumentation
# ---------------------------------------------------------------------------


def _render_frame_breakdown(self, lines, cursor_pos=None):
    """Instrumented render_frame that records per-operation timing."""
    timings = _render_frame_breakdown._timings

    # 1. Image.copy (titlebar template)
    t0 = time.perf_counter()
    img = self._titlebar_template.copy()
    t_copy = time.perf_counter() - t0

    draw = ImageDraw.Draw(img)

    # 2. draw.text + draw.rectangle (highlight bands) loop
    visible_lines = lines[-self.theme.rows :]
    num_visible = len(visible_lines)
    empty_rows_above = self.theme.rows - num_visible
    highlight_bg = self.theme.hex_to_rgb(self.theme.selection_color)

    t_text_total = 0.0
    t_rect_total = 0.0

    for row_idx, line in enumerate(visible_lines):
        x = self._ss_padding
        y = (
            self._ss_content_y
            + self._ss_padding
            + (empty_rows_above + row_idx) * self._char_height_ss
        )
        has_highlight = any(seg == HIGHLIGHT_MARKER for seg in line)

        if has_highlight:
            t0 = time.perf_counter()
            draw.rectangle(
                [
                    0,
                    y - self._text_nudge_ss - self._highlight_top_pad_ss,
                    self._ss_width,
                    y
                    + self._char_height_ss
                    - self._text_nudge_ss
                    + self._highlight_bottom_pad_ss,
                ],
                fill=highlight_bg,
            )
            t_rect_total += time.perf_counter() - t0

        text_y = y - self._text_nudge_ss
        if has_highlight:
            text_y -= self._highlight_text_raise_ss
        for seg in line:
            if seg == HIGHLIGHT_MARKER:
                continue
            text, color_hex = seg
            rgb = self.theme.hex_to_rgb(color_hex)
            t0 = time.perf_counter()
            draw.text((x, text_y), text, fill=rgb, font=self._font_ss)
            t_text_total += time.perf_counter() - t0
            x += len(text) * self._char_width_ss

    # 3. Cursor rectangle
    if cursor_pos is not None:
        crow, ccol = cursor_pos
        if 0 <= crow < num_visible:
            cx = self._ss_padding + ccol * self._char_width_ss
            cy = (
                self._ss_content_y
                + self._ss_padding
                + (empty_rows_above + crow) * self._char_height_ss
            )
            cursor_color = self.theme.hex_to_rgb(self.theme.foreground)
            t0 = time.perf_counter()
            draw.rectangle(
                [cx, cy, cx + self._char_width_ss, cy + self._char_height_ss],
                fill=cursor_color,
            )
            t_rect_total += time.perf_counter() - t0

    # 4. LANCZOS resize
    t0 = time.perf_counter()
    result = img.resize((self.image_width, self.image_height), Image.LANCZOS)
    t_resize = time.perf_counter() - t0

    timings.append(
        {
            "copy": t_copy,
            "text": t_text_total,
            "rect": t_rect_total,
            "resize": t_resize,
            "total": t_copy + t_text_total + t_rect_total + t_resize,
        }
    )
    return result


_render_frame_breakdown._timings = []


def _run_breakdown(num_turns: int) -> None:
    """Run render_frame breakdown profiling and print results."""
    from agent_log_gif.renderer import TerminalRenderer as TR

    theme = TerminalTheme()
    renderer = TerminalRenderer(theme)
    events = _synthetic_events(num_turns)

    _render_frame_breakdown._timings = []
    _orig = TR.render_frame
    TR.render_frame = _render_frame_breakdown

    try:
        generate_frames(events, renderer=renderer, speed=2.0, spinner_time=0.5)
    finally:
        TR.render_frame = _orig

    timings = _render_frame_breakdown._timings
    if not timings:
        print("No frames rendered.")
        return

    n = len(timings)
    keys = ["copy", "text", "rect", "resize", "total"]
    sums = {k: sum(t[k] for t in timings) for k in keys}
    avgs = {k: sums[k] / n * 1000 for k in keys}
    p95s = {k: sorted(t[k] for t in timings)[int(n * 0.95)] * 1000 for k in keys}

    total_sum = sums["total"]
    pcts = {k: sums[k] / total_sum * 100 if total_sum > 0 else 0 for k in keys}

    print(f"\nrender_frame() breakdown ({n} frames, {num_turns} turns)")
    print("=" * 72)
    print(
        f"{'Operation':<15} {'Sum(s)':>8} {'Avg(ms)':>9} {'P95(ms)':>9} {'% total':>9}"
    )
    print("-" * 72)
    for k in ["copy", "text", "rect", "resize"]:
        label = {
            "copy": "Image.copy",
            "text": "draw.text",
            "rect": "draw.rect",
            "resize": "resize",
        }[k]
        print(
            f"{label:<15} {sums[k]:8.3f} {avgs[k]:9.3f} {p95s[k]:9.3f} {pcts[k]:8.1f}%"
        )
    print("-" * 72)
    print(
        f"{'TOTAL':<15} {sums['total']:8.3f} {avgs['total']:9.3f} {p95s['total']:9.3f} {pcts['total']:8.1f}%"
    )
    print("=" * 72)

    # Kill criteria check
    resize_pct = pcts["resize"]
    text_pct = pcts["text"]
    print(
        f"\nKill criteria: resize={resize_pct:.1f}% (threshold >60%), "
        f"text={text_pct:.1f}% (threshold <25%)"
    )
    if resize_pct > 60 and text_pct < 25:
        print("KILL: resize dominates — incremental rendering won't help much.")
    else:
        print(
            "PROCEED: draw.text() is a significant cost; incremental rendering viable."
        )


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

    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp_file:
        tmp = Path(tmp_file.name)
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
    parser.add_argument(
        "--breakdown",
        action="store_true",
        help="Run per-operation timing breakdown of render_frame()",
    )
    args = parser.parse_args()

    turn_counts = [int(t.strip()) for t in args.turns.split(",")]

    if args.breakdown:
        _run_breakdown(turn_counts[-1])
        return
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
