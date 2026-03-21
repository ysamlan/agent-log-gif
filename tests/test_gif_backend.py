"""Tests for the GIF output backend."""

import subprocess

import pytest
from conftest import make_frame, make_striped_frame
from PIL import Image

from agent_log_gif.backends.gif import _build_palette, _optimize_with_gifsicle, save_gif
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
        # First frame contains all colors so the global palette includes them
        frames = [
            make_striped_frame((255, 0, 0), (0, 0, 255), (0, 128, 0)),
            make_frame("blue"),
            make_frame("green"),
        ]
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
        # First frame contains all colors so global palette includes them
        frames = [
            (make_striped_frame((255, 0, 0), (0, 0, 255), (0, 128, 0))[0], 100),
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


class TestGlobalPalette:
    def test_global_palette_shared_across_frames(self):
        """All frames quantize to the same palette indices via _build_palette."""
        frame1 = Image.new("RGB", (100, 100), (255, 0, 0))
        frame2 = Image.new("RGB", (100, 100), (0, 0, 255))
        palette_ref = _build_palette(frame1)

        q1 = frame1.quantize(palette=palette_ref, dither=Image.Dither.NONE)
        q2 = frame2.quantize(palette=palette_ref, dither=Image.Dither.NONE)

        # Both should use the same palette object for mapping
        assert q1.getpalette() == q2.getpalette()

        # Frame 1 and 2 should use different indices but from the same palette
        idx1 = set(q1.tobytes())
        idx2 = set(q2.tobytes())
        assert len(idx1) == 1  # solid red → single index
        assert len(idx2) == 1  # solid blue → single index
        assert idx1 != idx2  # different colors → different indices

    def test_no_dithering_produces_clean_quantization(self, tmp_path):
        """Solid-color frame quantizes to a single color (no dither noise)."""
        img = Image.new("RGB", (100, 100), (40, 42, 54))
        frames = [(img, 100)]
        output = tmp_path / "test.gif"
        save_gif(frames, output)

        with Image.open(output) as gif:
            rgb = gif.convert("RGB")
            colors = rgb.getcolors()
            # With no dithering, a solid-color image should have exactly 1 color
            assert len(colors) == 1

    def test_palette_seeds_included(self):
        """Seed colors not in the frame appear in the built palette."""
        frame = Image.new("RGB", (100, 100), (0, 0, 0))
        seeds = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        palette_ref = _build_palette(frame, palette_seeds=seeds)

        palette = palette_ref.getpalette()
        palette_colors = set()
        for i in range(0, len(palette), 3):
            palette_colors.add((palette[i], palette[i + 1], palette[i + 2]))

        for seed in seeds:
            assert seed in palette_colors, f"Seed {seed} not found in palette"

    def test_palette_seeds_survive_quantization(self, tmp_path):
        """Seeded color renders correctly in a frame that uses it."""
        # Frame 1: all red. Frame 2: all green (seeded but not in frame 1).
        frame1 = Image.new("RGB", (100, 100), (255, 0, 0))
        frame2 = Image.new("RGB", (100, 100), (0, 255, 0))
        seeds = [(0, 255, 0)]
        output = tmp_path / "test.gif"
        save_gif([(frame1, 100), (frame2, 100)], output, palette_seeds=seeds)

        with Image.open(output) as gif:
            gif.seek(1)
            rgb = gif.convert("RGB")
            colors = rgb.getcolors()
            # Frame 2 should render as exact green
            assert len(colors) == 1
            assert colors[0][1] == (0, 255, 0)

    def test_colors_parameter(self, tmp_path):
        """save_gif(..., colors=64) produces a valid animated GIF."""
        frames = [make_frame("red"), make_frame("blue")]
        output = tmp_path / "test.gif"
        save_gif(frames, output, colors=64)

        with Image.open(output) as img:
            assert img.format == "GIF"
            assert img.is_animated
            assert img.n_frames == 2

    def test_colors_produces_smaller_file(self, tmp_path):
        """Gradient frames: colors=64 file <= colors=256 file."""

        # Create frames with many colors (gradient)
        def gradient_frame():
            img = Image.new("RGB", (200, 200))
            for x in range(200):
                for y in range(200):
                    img.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
            return (img, 100)

        frames_256 = [gradient_frame(), gradient_frame()]
        frames_64 = [gradient_frame(), gradient_frame()]

        out_256 = tmp_path / "test_256.gif"
        out_64 = tmp_path / "test_64.gif"

        save_gif(frames_256, out_256, colors=256)
        save_gif(frames_64, out_64, colors=64)

        assert out_64.stat().st_size <= out_256.stat().st_size


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
