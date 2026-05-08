# src/nexus/ui/gradient_panel.py
# Rich renderable that draws a panel with a left-to-right gradient border.
# Author: Pierre Grothe
# Date: 2026-05-08
"""GradientPanel: Rich renderable with gradient-colored panel borders.

The top and bottom rules interpolate RGB color from `start` (left) to `end`
(right). The left side bar uses `start`; the right side bar uses `end`.
Works inside Table.grid columns -- respects options.max_width.

Also exports gradient_text() for applying per-character gradient color to
plain text strings, used in banner and status panels.
"""

import rich.box as rich_box
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

__all__ = ["GradientPanel", "gradient_text"]


def _lerp(i: int, n: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> Style:
    """Return an RGB Style interpolated between start and end at position i/n."""
    t = i / max(n - 1, 1)
    r = int(start[0] + (end[0] - start[0]) * t)
    g = int(start[1] + (end[1] - start[1]) * t)
    b = int(start[2] + (end[2] - start[2]) * t)
    return Style(color=f"rgb({r},{g},{b})")


def _gradient_rule(
    chars: list[str], start: tuple[int, int, int], end: tuple[int, int, int]
) -> Text:
    """Build a Text where each character fades from start to end color."""
    text = Text(end="")
    n = len(chars)
    for i, ch in enumerate(chars):
        text.append(ch, style=_lerp(i, n, start, end))
    return text


def gradient_text(
    text: str,
    *,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> Text:
    """Color each character of text with a linear RGB gradient from start to end.

    Args:
        text: The string to colour. Empty input yields an empty Text.
        start: RGB tuple applied to the first character.
        end: RGB tuple applied to the last character.

    Returns:
        A rich.Text whose characters interpolate linearly between start and end.
    """
    if not text:
        return Text()
    out = Text(end="")
    n = len(text)
    for i, ch in enumerate(text):
        out.append(ch, style=_lerp(i, n, start, end))
    return out


class GradientPanel:
    """Rich renderable -- a panel with a left-to-right gradient border.

    Args:
        renderable: Content to render inside the panel.
        title: Optional title text shown near the left of the top border.
        start: RGB tuple for the left-side gradient color.
        end: RGB tuple for the right-side gradient color.
        padding: Horizontal padding in spaces inside the border (default 1).
        min_height: Minimum number of content lines. Shorter content is padded
            with blank lines so equal-height column pairs stay visually flush.
    """

    def __init__(
        self,
        renderable: RenderableType,
        *,
        title: str = "",
        start: tuple[int, int, int],
        end: tuple[int, int, int],
        padding: int = 1,
        min_height: int = 0,
    ) -> None:
        """See class docstring."""
        self._renderable = renderable
        self._title = title
        self._start = start
        self._end = end
        self._padding = padding
        self._min_height = min_height

    def __rich_measure__(self, console: Console, options: ConsoleOptions) -> Measurement:
        """Report minimum and maximum widths so Table.grid can size columns correctly."""
        inner = Measurement.get(console, options, self._renderable)
        pad = self._padding * 2
        return Measurement(inner.minimum + 2 + pad, options.max_width)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Render the panel with gradient borders to the console."""
        box = rich_box.ROUNDED
        width = options.max_width
        inner_width = max(width - 2, 1)

        # Top border with title
        title_str = f" {self._title} " if self._title else ""
        title_len = len(title_str)
        if title_str and title_len < inner_width:
            left_fill = 2
            right_fill = max(inner_width - left_fill - title_len, 0)
            top_chars = (
                [box.top_left]
                + [box.top] * left_fill
                + list(title_str)
                + [box.top] * right_fill
                + [box.top_right]
            )
        else:
            top_chars = [box.top_left] + [box.top] * inner_width + [box.top_right]
        yield _gradient_rule(top_chars, self._start, self._end)
        yield Segment.line()

        # Content lines with gradient side bars; padded to min_height
        pad_seg = Segment(" " * self._padding)
        left_style = _lerp(0, width, self._start, self._end)
        right_style = _lerp(width - 1, width, self._start, self._end)
        content_width = max(inner_width - self._padding * 2, 1)
        inner_opts = options.update_width(content_width)
        content_lines: list[list[Segment]] = list(
            console.render_lines(self._renderable, inner_opts, pad=True)
        )
        blank: list[Segment] = [Segment(" " * content_width)]
        while len(content_lines) < self._min_height:
            content_lines.append(blank)
        for line in content_lines:
            yield Segment(box.mid_left, left_style)
            yield pad_seg
            yield from line
            yield pad_seg
            yield Segment(box.mid_right, right_style)
            yield Segment.line()

        # Bottom border
        bottom_chars = [box.bottom_left] + [box.bottom] * inner_width + [box.bottom_right]
        yield _gradient_rule(bottom_chars, self._start, self._end)
        yield Segment.line()
