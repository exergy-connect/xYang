"""Path builder for YANG document validation."""

from typing import Optional


def _json_pointer_token(token: str) -> str:
    """Escape one JSON Pointer reference token (RFC 6901)."""
    if "~" not in token and "/" not in token:
        return token
    return token.replace("~", "~0").replace("/", "~1")


class PathBuilder:
    """Maintain display paths and JSON Pointers as the walker descends."""

    def __init__(self, initial_segments: Optional[list[str]] = None) -> None:
        self._paths: list[str] = [""]
        self._pointers: list[str] = [""]
        for segment in initial_segments or []:
            self.push(segment)

    def push(
        self,
        name: str,
        key: Optional[str] = None,
        *,
        index: Optional[int] = None,
        pointer_name: Optional[str] = None,
    ) -> None:
        segment = f"{name}[{key}]" if key is not None else name
        token = _json_pointer_token(pointer_name if pointer_name is not None else name)
        self._paths.append(self._paths[-1] + "/" + segment)
        pointer = self._pointers[-1] + "/" + token
        self._pointers.append(pointer + (f"/{index}" if index is not None else ""))

    def pop(self) -> None:
        if len(self._paths) == 1:
            raise IndexError("pop from empty path")
        self._paths.pop()
        self._pointers.pop()

    def current(self) -> str:
        return self._paths[-1] or "/"

    def pointer(self) -> str:
        """JSON Pointer for the current node. The document root is ``""``."""
        return self._pointers[-1]

    def child(self, name: str, key: Optional[str] = None) -> str:
        seg = f"{name}[{key}]" if key is not None else name
        parent = self._paths[-1]
        if parent.endswith("/"):
            parent = parent.rstrip("/")
        return parent + "/" + seg

    def child_pointer(self, name: str, index: Optional[int] = None) -> str:
        """JSON Pointer for a child that is not pushed onto the builder."""
        out = f"{self._pointers[-1]}/{_json_pointer_token(name)}"
        if index is not None:
            out = f"{out}/{index}"
        return out
