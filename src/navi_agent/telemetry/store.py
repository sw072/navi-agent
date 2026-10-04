from __future__ import annotations

from typing import Protocol

from .models import RuntimeTrace


class TraceStore(Protocol):
    def record(self, trace: RuntimeTrace) -> None: ...

    def list_traces(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[RuntimeTrace]: ...

    def get_trace(self, trace_id: str) -> RuntimeTrace | None: ...

    def get_session_traces(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
    ) -> list[RuntimeTrace]: ...

    def get_latest_trace(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> RuntimeTrace | None: ...

    def list_recent_session_ids(self, *, limit: int) -> list[str]: ...
