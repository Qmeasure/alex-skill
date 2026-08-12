from __future__ import annotations

from typing import Any


class PodcastEditorError(Exception):
    """A user-facing failure with a stable API error code."""

    def __init__(self, code: str, message: str, *, details: Any | None = None, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status = status

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


class RevisionConflict(PodcastEditorError):
    def __init__(self, expected: int, actual: int):
        super().__init__(
            "revision_conflict",
            "审核内容已被另一项操作更新，请刷新后重试。",
            details={"expected": expected, "actual": actual},
            status=409,
        )


def raise_if_cancelled(cancel_event: Any | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PodcastEditorError("operation_cancelled", "操作已取消。", status=409)
