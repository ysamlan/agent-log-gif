"""Tests for the compressed in-memory frame store."""

import pytest
from PIL import Image

from agent_log_gif.frame_store import FrameStore


def _make_img(color="red", size=(100, 100)):
    return Image.new("RGB", size, color)


class TestFrameStore:
    def test_append_and_len(self):
        store = FrameStore()
        assert len(store) == 0
        store.append(_make_img(), 100)
        assert len(store) == 1
        store.append(_make_img("blue"), 200)
        assert len(store) == 2

    def test_bool_empty(self):
        store = FrameStore()
        assert not store

    def test_bool_nonempty(self):
        store = FrameStore()
        store.append(_make_img(), 100)
        assert store

    def test_getitem_positive(self):
        store = FrameStore()
        store.append(_make_img("red"), 100)
        store.append(_make_img("blue"), 200)
        img, dur = store[0]
        assert dur == 100
        assert img.size == (100, 100)
        assert img.getpixel((0, 0)) == (255, 0, 0)

    def test_getitem_negative(self):
        store = FrameStore()
        store.append(_make_img("red"), 100)
        store.append(_make_img("blue"), 200)
        img, dur = store[-1]
        assert dur == 200
        assert img.getpixel((0, 0)) == (0, 0, 255)

    def test_getitem_out_of_range(self):
        store = FrameStore()
        store.append(_make_img(), 100)
        with pytest.raises(IndexError):
            store[5]

    def test_setitem_replaces_frame(self):
        store = FrameStore()
        store.append(_make_img("red"), 100)
        store[-1] = (_make_img("green"), 2000)
        img, dur = store[0]
        assert dur == 2000
        assert img.getpixel((0, 0)) == (0, 128, 0)

    def test_iter_yields_all_frames(self):
        store = FrameStore()
        colors = ["red", "blue", "green"]
        for c in colors:
            store.append(_make_img(c), 100)
        frames = list(store)
        assert len(frames) == 3
        for img, dur in frames:
            assert isinstance(img, Image.Image)
            assert dur == 100

    def test_iter_preserves_pixel_data(self):
        """Round-trip through compress/decompress preserves exact pixels."""
        store = FrameStore()
        orig = _make_img("red")
        store.append(orig, 50)
        recovered, _ = store[0]
        assert orig.tobytes() == recovered.tobytes()

    def test_large_frame_compresses(self):
        """A solid-color frame compresses well (terminal content compresses ~50:1)."""
        import sys

        store = FrameStore()
        img = _make_img("red", size=(800, 600))
        raw_size = len(img.tobytes())  # 800*600*3 = 1,440,000 bytes
        store.append(img, 100)
        # The compressed data should be much smaller than raw
        compressed_size = sys.getsizeof(store._frames[0][0])
        assert compressed_size < raw_size / 10

    def test_durations_returns_all_durations(self):
        store = FrameStore()
        store.append(_make_img(), 100)
        store.append(_make_img(), 200)
        store.append(_make_img(), 500)
        assert store.durations() == [100, 200, 500]

    def test_image_size_stored(self):
        store = FrameStore()
        store.append(_make_img(size=(320, 240)), 100)
        assert store.image_size == (320, 240)

    def test_image_size_none_when_empty(self):
        store = FrameStore()
        assert store.image_size is None

    def test_set_duration_changes_only_duration(self):
        store = FrameStore()
        store.append(_make_img("red"), 100)
        store.set_duration(0, 2000)
        img, dur = store[0]
        assert dur == 2000
        assert img.getpixel((0, 0)) == (255, 0, 0)

    def test_raw_iter_yields_bytes(self):
        store = FrameStore()
        orig = _make_img("red")
        store.append(orig, 100)
        raw_bytes, dur = next(store.raw_iter())
        assert dur == 100
        assert isinstance(raw_bytes, bytes)
        assert raw_bytes == orig.tobytes()
