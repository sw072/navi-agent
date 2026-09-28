"""Modal-backed sandbox adapter for SWE-bench evaluation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModalExecResult:
    returncode: int
    stdout: str
    stderr: str


def swe_bench_modal_image(sample_id: str) -> str:
    """Return the amd64 SWE-bench image used by Modal."""

    return f"ghcr.io/epoch-research/swe-bench.eval.{sample_id}:latest"


class ModalSandboxEnvironment:
    """Async adapter exposing the subset of Inspect's sandbox API we use."""

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    @classmethod
    def create(cls, *, sample_id: str, app_name: str) -> "ModalSandboxEnvironment":
        try:
            import modal
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Modal evaluation requires: uv sync --extra cloud"
            ) from exc

        app = modal.App.lookup(app_name, create_if_missing=True)
        image = modal.Image.from_registry(swe_bench_modal_image(sample_id))
        sandbox = modal.Sandbox.create(app=app, image=image)
        return cls(sandbox)

    async def exec(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        timeout: int | None = None,
        timeout_retry: bool = False,
        **_: Any,
    ) -> ModalExecResult:
        del timeout_retry
        if cwd:
            command = ["bash", "--login", "-c", f"cd {quote_shell(cwd)} && {command[-1]}"]
        result = await asyncio.to_thread(self._exec_sync, command, timeout)
        return result

    def _exec_sync(self, command: list[str], timeout: int | None) -> ModalExecResult:
        process = self._sandbox.exec(*command, timeout=timeout)
        process.wait()
        return ModalExecResult(
            returncode=int(process.returncode or 0),
            stdout=str(process.stdout.read() or ""),
            stderr=str(process.stderr.read() or ""),
        )

    async def read_file(self, path: str) -> str:
        return await asyncio.to_thread(self._sandbox.filesystem.read_text, path)

    async def write_file(self, path: str, content: str) -> None:
        await asyncio.to_thread(self._sandbox.filesystem.write_text, content, path)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        try:
            self._sandbox.terminate(wait=True)
        finally:
            self._sandbox.detach()


def quote_shell(value: str) -> str:
    """Quote a path for the remote shell without adding a dependency."""

    return "'" + value.replace("'", "'\\''") + "'"
