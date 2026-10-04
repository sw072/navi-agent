from __future__ import annotations

from dataclasses import asdict
from collections.abc import Iterable
import json
from pathlib import Path
import sqlite3

from navi_agent.events import RuntimeEvent

from .models import RuntimeTrace
from .serializer import TraceSerializer


class _SQLiteTelemetryStore:
    _BUSY_TIMEOUT_MS = 5_000

    def __init__(self, path: Path) -> None:
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path,
            timeout=self._BUSY_TIMEOUT_MS / 1_000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._BUSY_TIMEOUT_MS}")
        return connection


class SQLiteRuntimeEventStore(_SQLiteTelemetryStore):
    def record(self, event: RuntimeEvent) -> None:
        with self._connect() as connection:
            self._insert(connection, event)

    def import_events(self, events: Iterable[RuntimeEvent]) -> int:
        count = 0
        with self._connect() as connection:
            for event in events:
                self._insert(connection, event)
                count += 1
        return count

    @staticmethod
    def _insert(connection: sqlite3.Connection, event: RuntimeEvent) -> None:
        connection.execute(
            """
            INSERT INTO runtime_events (
                event_id, session_id, run_id, sequence, timestamp, name, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                event.event_id,
                event.session_id,
                event.run_id,
                event.sequence,
                event.timestamp,
                event.name,
                json.dumps(asdict(event), ensure_ascii=False, sort_keys=True),
            ),
        )

    def list_events(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> list[RuntimeEvent]:
        clauses: list[str] = []
        parameters: list[str] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            parameters.append(session_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            parameters.append(run_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT event_json FROM runtime_events{where} "
                "ORDER BY timestamp, sequence",
                parameters,
            ).fetchall()
        return [RuntimeEvent(**json.loads(str(row["event_json"]))) for row in rows]


class SQLiteTraceStore(_SQLiteTelemetryStore):
    def record(self, trace: RuntimeTrace) -> None:
        with self._connect() as connection:
            self._insert(connection, trace)

    def import_traces(self, traces: Iterable[RuntimeTrace]) -> int:
        count = 0
        with self._connect() as connection:
            for trace in traces:
                self._insert(connection, trace)
                count += 1
        return count

    @staticmethod
    def _insert(connection: sqlite3.Connection, trace: RuntimeTrace) -> None:
        connection.execute(
            """
            INSERT INTO runtime_traces (
                trace_id, session_id, user_id, status,
                started_at, completed_at, trace_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                session_id = excluded.session_id,
                user_id = excluded.user_id,
                status = excluded.status,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                trace_json = excluded.trace_json
            """,
            (
                trace.trace_id,
                trace.session_id,
                trace.user_id,
                trace.status,
                trace.started_at,
                trace.completed_at,
                TraceSerializer.to_json(trace),
            ),
        )

    def list_traces(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[RuntimeTrace]:
        clauses: list[str] = []
        parameters: list[object] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            parameters.append(user_id)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            parameters.append(limit)
        return self._query_traces(
            f"SELECT trace_json FROM runtime_traces{where} "
            f"ORDER BY completed_at DESC, trace_id DESC{limit_sql}",
            parameters,
        )

    def get_trace(self, trace_id: str) -> RuntimeTrace | None:
        traces = self._query_traces(
            "SELECT trace_json FROM runtime_traces WHERE trace_id = ?",
            [trace_id],
        )
        return traces[0] if traces else None

    def get_session_traces(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
    ) -> list[RuntimeTrace]:
        sql = "SELECT trace_json FROM runtime_traces WHERE session_id = ?"
        parameters: list[object] = [session_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            parameters.append(user_id)
        return self._query_traces(
            f"{sql} ORDER BY completed_at, trace_id",
            parameters,
        )

    def get_latest_trace(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> RuntimeTrace | None:
        clauses: list[str] = []
        parameters: list[object] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            parameters.append(session_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            parameters.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        traces = self._query_traces(
            f"SELECT trace_json FROM runtime_traces{where} "
            "ORDER BY completed_at DESC, trace_id DESC LIMIT 1",
            parameters,
        )
        return traces[0] if traces else None

    def list_recent_session_ids(self, *, limit: int) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, MAX(completed_at) AS latest
                FROM runtime_traces
                GROUP BY session_id
                ORDER BY latest DESC, session_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["session_id"]) for row in rows]

    def _query_traces(
        self,
        sql: str,
        parameters: list[object],
    ) -> list[RuntimeTrace]:
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [TraceSerializer.from_json(str(row["trace_json"])) for row in rows]
