"""Tests for the layout composition layer.

Pure-data tests — no rendering, no images. Validates viewport budget
calculation, transcript truncation, and spacing policies.
"""

from agent_log_gif.layout import LayoutFrame, commit_with_spacing, compose_lines
from agent_log_gif.renderer import HIGHLIGHT_MARKER, StyledLine


def _line(text: str) -> StyledLine:
    """Helper: create a simple styled line."""
    return [(text, "#ffffff")]


def _lines(n: int) -> list[StyledLine]:
    """Helper: create n distinct styled lines."""
    return [_line(f"line-{i}") for i in range(n)]


class TestComposeLines:
    def test_empty_frame_returns_empty(self):
        frame = LayoutFrame(transcript=[])
        assert compose_lines(frame, viewport_rows=30) == []

    def test_transcript_only(self):
        transcript = _lines(3)
        frame = LayoutFrame(transcript=transcript)
        result = compose_lines(frame, viewport_rows=30)
        assert result == transcript

    def test_composer_always_present(self):
        composer = [_line("prompt")]
        frame = LayoutFrame(transcript=[], composer=composer)
        result = compose_lines(frame, viewport_rows=30)
        assert result == composer

    def test_transcript_plus_composer(self):
        transcript = _lines(3)
        composer = [_line("prompt")]
        frame = LayoutFrame(transcript=transcript, composer=composer)
        result = compose_lines(frame, viewport_rows=30)
        assert result == transcript + composer

    def test_transcript_truncated_to_viewport_budget(self):
        transcript = _lines(10)
        composer = [_line("prompt")]
        # viewport=5, composer=1 line → transcript budget = 4
        result = compose_lines(
            LayoutFrame(transcript=transcript, composer=composer),
            viewport_rows=5,
        )
        assert len(result) == 5
        assert result[:4] == transcript[-4:]  # last 4 transcript lines
        assert result[4:] == composer

    def test_transient_consumes_viewport_budget(self):
        transcript = _lines(10)
        transient = [_line("spinner")]
        composer = [_line("prompt")]
        # viewport=5, transient=1, composer=1 → transcript budget = 3
        result = compose_lines(
            LayoutFrame(transcript=transcript, transient=transient, composer=composer),
            viewport_rows=5,
        )
        assert len(result) == 5
        assert result[:3] == transcript[-3:]
        assert result[3:4] == transient
        assert result[4:] == composer

    def test_composer_never_truncated(self):
        composer = _lines(5)
        # viewport=3 but composer is 5 lines — composer wins
        result = compose_lines(
            LayoutFrame(transcript=_lines(10), composer=composer),
            viewport_rows=3,
        )
        assert result == composer  # no transcript fits, but full composer preserved

    def test_transient_never_truncated(self):
        transient = _lines(3)
        composer = _lines(3)
        # viewport=4 but transient+composer = 6 — both preserved, no transcript
        result = compose_lines(
            LayoutFrame(transcript=_lines(10), transient=transient, composer=composer),
            viewport_rows=4,
        )
        assert result == transient + composer

    def test_short_transcript_not_padded(self):
        transcript = _lines(2)
        composer = [_line("prompt")]
        # viewport=30, transcript=2, composer=1 → only 3 lines, no padding
        result = compose_lines(
            LayoutFrame(transcript=transcript, composer=composer),
            viewport_rows=30,
        )
        assert len(result) == 3
        assert result == transcript + composer

    def test_ordering_is_transcript_transient_composer(self):
        t = [_line("transcript")]
        tr = [_line("transient")]
        c = [_line("composer")]
        result = compose_lines(
            LayoutFrame(transcript=t, transient=tr, composer=c),
            viewport_rows=30,
        )
        assert result == t + tr + c

    def test_user_typing_replaces_composer(self):
        """During user typing, input_lines ARE the composer — no idle prompt."""
        transcript = _lines(5)
        # Simulate: separator + multi-line user input = composer
        input_lines = [
            [],  # separator
            [("❯ ", "#ff0000"), ("hello wor", "#ffffff"), HIGHLIGHT_MARKER],
            [("  ld", "#ffffff"), HIGHLIGHT_MARKER],
        ]
        result = compose_lines(
            LayoutFrame(transcript=transcript, composer=input_lines),
            viewport_rows=10,
        )
        # 10 - 3 (composer) = 7 budget, transcript is 5 → all fit
        assert len(result) == 8  # 5 transcript + 3 composer
        assert result[-3:] == input_lines


class TestCommitWithSpacing:
    def test_appends_lines(self):
        transcript: list[StyledLine] = []
        lines = _lines(2)
        commit_with_spacing(transcript, lines)
        assert transcript == lines

    def test_spacing_after_adds_blanks(self):
        transcript: list[StyledLine] = []
        lines = _lines(1)
        commit_with_spacing(transcript, lines, spacing_after=2)
        assert len(transcript) == 3
        assert transcript[0] == lines[0]
        assert transcript[1] == []
        assert transcript[2] == []

    def test_spacing_after_zero_adds_nothing(self):
        transcript: list[StyledLine] = []
        lines = _lines(1)
        commit_with_spacing(transcript, lines, spacing_after=0)
        assert transcript == lines

    def test_appends_to_existing_transcript(self):
        transcript = _lines(3)
        original_len = len(transcript)
        new_lines = _lines(2)
        commit_with_spacing(transcript, new_lines, spacing_after=1)
        assert len(transcript) == original_len + 2 + 1  # 2 lines + 1 blank
