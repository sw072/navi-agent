from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import TypeVar

from navi_agent.events import RuntimeEvent

from .serializer import TraceSerializer
from .sqlite import SQLiteRuntimeEventStore, SQLiteTraceStore

logger = logging.getLogger("navi_agent.telemetry.migration")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TelemetryMigrationResult:
    event_count: int = 0
    trace_count: int = 0


def migrate_legacy_jsonl(
    *,
    database_path: Path,
    event_path: Path,
    trace_path: Path,
    event_store: SQLiteRuntimeEventStore,
    trace_store: SQLiteTraceStore,
) -> TelemetryMigrationResult:
    event_count = _import_once(
        database_path,
        source_key=f"runtime-events:{event_path.resolve()}",
        source_path=event_path,
        convert=_event_from_payload,
        import_records=event_store.import_events,
    )
    trace_count = _import_once(
        database_path,
        source_key=f"runtime-traces:{trace_path.resolve()}",
        source_path=trace_path,
        convert=TraceSerializer.from_dict,
        import_records=trace_store.import_traces,
    )
    return TelemetryMigrationResult(event_count=event_count, trace_count=trace_count)


def _import_once(
    database_path: Path,
    *,
    source_key: str,
    source_path: Path,
    convert: Callable[[dict], T],
    import_records: Callable[[Iterable[T]], int],
) -> int:
    if not source_path.exists() or _was_imported(database_path, source_key):
        return 0
    count = import_records(_valid_records(source_path, convert))
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO telemetry_imports (source_key, imported_at, record_count)
            VALUES (?, ?, ?)
            ON CONFLICT(source_key) DO NOTHING
            """,
            (
                source_key,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                count,
            ),
        )
    return count


def _valid_records(source_path: Path, convert: Callable[[dict], T]) -> Iterable[T]:
    with source_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("JSONL record must be an object")
                yield convert(payload)
            except Exception as error:
                logger.warning(
                    "Skipping invalid legacy telemetry record: path=%s line=%s error=%s",
                    source_path,
                    line_number,
                    error,
                )


def _was_imported(database_path: Path, source_key: str) -> bool:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM telemetry_imports WHERE source_key = ?",
            (source_key,),
        ).fetchone()
    return row is not None


def _event_from_payload(payload: dict) -> RuntimeEvent:
    payload = dict(payload)
    if "payload" in payload and "metadata" not in payload:
        payload["metadata"] = payload.pop("payload")
    return RuntimeEvent(**payload)
