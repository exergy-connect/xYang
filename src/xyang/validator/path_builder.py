"""
Path builder for YANG document validation.
"""

from typing import List, Optional


def _json_pointer_token(token: str) -> str:
    """Escape one JSON Pointer reference token (RFC 6901)."""
    return token.replace("~", "~0").replace("/", "~1")


class PathBuilder:
    """
    Maintains the current path string as the walker descends.
    List entries use key predicates: /data-model/entities[name='foo']

    A parallel JSON Pointer uses schema/instance names and list entry indices
    (``/entities/0``), which is what ``validate_detailed`` reports.
    """

    def __init__(self, initial_segments: Optional[List[str]] = None) -> None:
        self._segments: List[str] = list(initial_segments) if initial_segments else []
        self._pointer_tokens: List[str] = [_json_pointer_token(s) for s in self._segments]
        self._pointer_widths: List[int] = [1] * len(self._segments)

    def push(
        self,
        name: str,
        key: Optional[str] = None,
        *,
        index: Optional[int] = None,
        pointer_name: Optional[str] = None,
    ) -> None:
        self._segments.append(f"{name}[{key}]" if key is not None else name)
        self._pointer_tokens.append(_json_pointer_token(pointer_name if pointer_name is not None else name))
        if index is not None:
            self._pointer_tokens.append(str(index))
            self._pointer_widths.append(2)
        else:
            self._pointer_widths.append(1)

    def pop(self) -> None:
        self._segments.pop()
        width = self._pointer_widths.pop()
        del self._pointer_tokens[-width:]

    def current(self) -> str:
        return "/" + "/".join(self._segments) if self._segments else "/"

    def pointer(self) -> str:
        """JSON Pointer for the current node. The document root is ``""``."""
        if not self._pointer_tokens:
            return ""
        return "/" + "/".join(self._pointer_tokens)

    def child(self, name: str, key: Optional[str] = None) -> str:
        seg = f"{name}[{key}]" if key is not None else name
        return self.current().rstrip("/") + "/" + seg

    def child_pointer(self, name: str, index: Optional[int] = None) -> str:
        """JSON Pointer for a child that is not pushed onto the builder."""
        out = f"{self.pointer()}/{_json_pointer_token(name)}"
        if index is not None:
            out = f"{out}/{index}"
        return out
