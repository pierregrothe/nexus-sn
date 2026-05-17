from collections.abc import Generator

from prompt_toolkit.formatted_text.base import StyleAndTextTuples

class Source: ...

class GeneratorSource(Source):
    def __init__(self, generator: Generator[StyleAndTextTuples, None, None]) -> None: ...

__all__ = ["GeneratorSource", "Source"]
