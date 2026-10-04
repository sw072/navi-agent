from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from navi_agent.events import RuntimeEvent
from navi_agent.runtime import SQLiteSessionStore
from navi_agent.telemetry import (
    ModelCallTrace,
    RuntimeTrace,
    SQLiteRuntimeEventStore,
    SQLiteTraceStore,
    ToolExecutionTrace,
)


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    SQLiteSessionStore(path)
    return path


def test_sqlite_event_store_records_filters_and_orders_events(tmp_path: Path) -> None:
    store = SQLiteRuntimeEventStore(_database(tmp_path))
    for sequence in (2, 1):
        store.record(
            RuntimeEvent(
                event_id=f"event-{sequence}",
                session_id="session-1",
                user_id="user-1",
                run_id="run-1",
                sequence=sequence,
                kind="observation",
                source="runtime",
                name="runtime.completed" if sequence == 2 else "runtime.started",
                metadata={"sequence": sequence},
                timestamp=f"2026-10-04T00:00:0{sequence}+00:00",
            )
        )

    events = store.list_events(session_id="session-1", run_id="run-1")

    assert [event.sequence for event in events] == [1, 2]
    assert events[1].metadata == {"sequence": 2}


def test_sqlite_event_store_supports_parallel_writers(tmp_path: Path) -> None:
    path = _database(tmp_path)
    store = SQLiteRuntimeEventStore(path)

    def record(index: int) -> None:
        store.record(
            RuntimeEvent(
                event_id=f"event-{index}",
                session_id=f"session-{index}",
                user_id="user-1",
                run_id=f"run-{index}",
                sequence=1,
                kind="observation",
                source="runtime",
                name="runtime.completed",
            )
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(record, range(30)))

    assert len(store.list_events()) == 30


def test_sqlite_trace_store_supports_indexed_queries(tmp_path: Path) -> None:
    store = SQLiteTraceStore(_database(tmp_path))
    store.record(
        RuntimeTrace(
            trace_id="trace-1",
            session_id="session-1",
            user_id="user-1",
            user_message="first",
            final_response="ok",
            status="success",
            completed_at="2026-10-04T00:00:01+00:00",
            model_calls=[ModelCallTrace(iteration=1, response_content="ok")],
            tool_executions=[
                ToolExecutionTrace(
                    iteration=1,
                    tool_call_id="call-1",
                    tool_name="read_file",
                    status="success",
                )
            ],
        )
    )
    store.record(
        RuntimeTrace(
            trace_id="trace-2",
            session_id="session-2",
            user_id="user-1",
            user_message="second",
            final_response="failed",
            status="failed",
            completed_at="2026-10-04T00:00:02+00:00",
        )
    )

    assert store.get_trace("trace-1").tool_executions[0].tool_name == "read_file"
    assert [trace.trace_id for trace in store.list_traces(user_id="user-1", limit=1)] == [
        "trace-2"
    ]
    assert store.get_latest_trace(session_id="session-1").trace_id == "trace-1"
    assert store.list_recent_session_ids(limit=1) == ["session-2"]


def test_sqlite_trace_store_upserts_a_completed_trace(tmp_path: Path) -> None:
    store = SQLiteTraceStore(_database(tmp_path))
    initial = RuntimeTrace(
        trace_id="trace-1",
        session_id="session-1",
        user_id="user-1",
        user_message="hello",
        final_response="",
        status="running",
    )
    store.record(initial)
    initial.status = "success"
    initial.final_response = "done"
    store.record(initial)

    traces = store.list_traces()

    assert len(traces) == 1
    assert traces[0].status == "success"
    assert traces[0].final_response == "done"
