"""Tests for the GIF output backend."""

from PIL import Image

from agent_log_gif.backends.gif import save_gif


def _make_frame(color, duration_ms=100):
    """Helper: create a solid-color 100x100 frame."""
    img = Image.new("RGB", (100, 100), color)
    return (img, duration_ms)


class TestSaveGif:
    def test_creates_gif_file(self, tmp_path):
        """Output file exists and is a GIF."""
        frames = [_make_frame("red"), _make_frame("blue"), _make_frame("green")]
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
        frames = [_make_frame("red"), _make_frame("blue"), _make_frame("green")]
        output = tmp_path / "test.gif"
        save_gif(frames, output)

        with Image.open(output) as img:
            assert img.is_animated
            assert img.n_frames == 3

    def test_single_frame(self, tmp_path):
        """Single frame produces a valid GIF."""
        frames = [_make_frame("red")]
        output = tmp_path / "test.gif"
        save_gif(frames, output)

        with Image.open(output) as img:
            assert img.format == "GIF"

    def test_empty_frames_raises(self, tmp_path):
        """Empty frame list raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="empty"):
            save_gif([], tmp_path / "test.gif")

    def test_creates_parent_dirs(self, tmp_path):
        """Parent directories are created if needed."""
        output = tmp_path / "sub" / "dir" / "test.gif"
        frames = [_make_frame("red")]
        save_gif(frames, output)
        assert output.exists()

    def test_durations_preserved(self, tmp_path):
        """Frame durations are set correctly."""
        frames = [
            _make_frame("red", 100),
            _make_frame("blue", 200),
            _make_frame("green", 500),
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
