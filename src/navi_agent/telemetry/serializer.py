from __future__ import annotations

import json
from dataclasses import asdict

from .models import ModelCallTrace, RuntimeTrace, ToolExecutionTrace


class TraceSerializer:
    SCHEMA_VERSION = "trace.v3"

    @classmethod
    def to_dict(cls, trace: RuntimeTrace) -> dict:
        payload = asdict(trace)
        payload["schema_version"] = cls.SCHEMA_VERSION
        return payload

    @classmethod
    def to_json(cls, trace: RuntimeTrace) -> str:
        return json.dumps(cls.to_dict(trace), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict) -> RuntimeTrace:
        payload = dict(payload)
        payload.pop("schema_version", None)
        payload["model_calls"] = [
            item if isinstance(item, ModelCallTrace) else ModelCallTrace(**item)
            for item in payload.get("model_calls", [])
        ]
        payload["tool_executions"] = [
            item if isinstance(item, ToolExecutionTrace) else ToolExecutionTrace(**item)
            for item in payload.get("tool_executions", [])
        ]
        return RuntimeTrace(**payload)

    @classmethod
    def from_json(cls, payload: str) -> RuntimeTrace:
        return cls.from_dict(json.loads(payload))

    @classmethod
    def traces_to_dicts(cls, traces: list[RuntimeTrace]) -> list[dict]:
        return [cls.to_dict(trace) for trace in traces]

    @classmethod
    def traces_to_json_lines(cls, traces: list[RuntimeTrace]) -> str:
        return "\n".join(cls.to_json(trace) for trace in traces)
