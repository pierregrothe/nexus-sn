# tests/fakes/pager.py
# Test fake for PagerProtocol -- records calls without spawning a subprocess.
# Author: Pierre Grothe
# Date: 2026-05-15

"""FakePager: in-memory PagerProtocol implementation for tests.

The production :class:`PypagerPager` spawns prompt_toolkit which is
unfriendly to non-TTY test environments. FakePager records the text
handed to ``page()`` so assertions can target what *would* have been
paged.
"""

__all__ = ["FakePager"]


class FakePager:
    """Pager that records calls instead of paging.

    Attributes:
        last_text: The most recent ``text`` argument passed to
            :meth:`page`, or ``None`` if never called.
        call_count: Number of times :meth:`page` was invoked.
    """

    def __init__(self) -> None:
        """Initialise an empty recorder."""
        self.last_text: str | None = None
        self.call_count: int = 0

    def page(self, text: str) -> None:
        """Record ``text`` and increment the call count.

        Args:
            text: Text that the production pager would display.
        """
        self.last_text = text
        self.call_count += 1
