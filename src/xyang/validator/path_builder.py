"""
Path builder for YANG document validation.
"""

from typing import List, Optional


class PathBuilder:
    """
    Maintains the current path string as the walker descends.
    List entries use key predicates: /data-model/entities[name='foo']
    """

    def __init__(self, initial_segments: Optional[List[str]] = None) -> None:
        self._segments: List[str] = list(initial_segments) if initial_segments else []

    def push(self, name: str, key: Optional[str] = None) -> None:
        self._segments.append(f"{name}[{key}]" if key is not None else name)

    def pop(self) -> None:
        self._segments.pop()

    def current(self) -> str:
        return "/" + "/".join(self._segments) if self._segments else "/"

    def child(self, name: str, key: Optional[str] = None) -> str:
        seg = f"{name}[{key}]" if key is not None else name
        return self.current().rstrip("/") + "/" + seg
