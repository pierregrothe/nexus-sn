# src/nexus/ui/components/pager.py
# Pager abstraction + pypager-backed implementation.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Page styled text through ``pypager`` with sticky header + search.

The protocol exists so tests can substitute a :class:`FakePager` (see
``tests/fakes/pager.py``) without spawning a subprocess or mocking
``sys.stdout``. The production :class:`PypagerPager` is a thin wrapper
around ``pypager.Pager`` that streams ANSI-styled text into the pager.
"""

from collections.abc import Generator
from typing import Protocol, runtime_checkable

from prompt_toolkit.formatted_text.base import StyleAndTextTuples

__all__ = [
    "PagerProtocol",
    "PypagerPager",
]


@runtime_checkable
class PagerProtocol(Protocol):
    """Renderable-to-pager surface used by :class:`PagedTable`.

    Implementations accept pre-rendered styled text (ANSI-escaped) and
    display it through a scrollable viewer. The caller is responsible
    for capturing Rich output to a string via ``Console.capture()``.
    """

    def page(self, text: str) -> None:
        """Show ``text`` in a scrollable viewer until the user quits.

        Args:
            text: Pre-rendered styled text. May contain ANSI escapes.
        """
        ...


class PypagerPager:
    """Production pager using ``pypager`` for cross-platform paging.

    The pager opens an alternate-screen view supporting sticky header,
    ``/search``, ``q`` to quit, and arrow / PageUp / PageDown keys. It
    only works in terminals that handle VT escape sequences (RICH and
    BASIC profiles). LEGACY callers must not invoke this class.
    """

    def page(self, text: str) -> None:  # pragma: no cover -- requires a real TTY.
        """Display ``text`` via ``pypager.Pager.from_iterable``.

        Args:
            text: Pre-rendered styled text. ANSI escapes are honored.
        """
        from prompt_toolkit.formatted_text import ANSI  # noqa: PLC0415
        from pypager.pager import Pager  # noqa: PLC0415
        from pypager.source import GeneratorSource  # noqa: PLC0415

        formatted: StyleAndTextTuples = ANSI(text).__pt_formatted_text__()

        def _generator() -> Generator[StyleAndTextTuples]:
            yield formatted

        pager = Pager()
        pager.add_source(GeneratorSource(_generator()))
        pager.run()
