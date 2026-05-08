from pathlib import Path

class Cache:
    def __init__(
        self,
        directory: str | Path | None = None,
        timeout: float = 60,
        disk: object = ...,
        **settings: object,
    ) -> None: ...
    def get(
        self,
        key: object,
        default: object = None,
        read: bool = False,
        expire_time: bool = False,
        tag: bool = False,
        retry: bool = False,
    ) -> object: ...
    def set(
        self,
        key: object,
        value: object,
        expire: float | int | None = None,
        read: bool = False,
        tag: object = None,
        retry: bool = False,
    ) -> bool: ...
    def delete(self, key: object, retry: bool = False) -> bool: ...
    def clear(self, retry: bool = False) -> int: ...
    def close(self) -> None: ...
    def __enter__(self) -> Cache: ...
    def __exit__(self, *args: object) -> None: ...
