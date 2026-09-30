from __future__ import annotations

import asyncio
import os

from inspect_ai import Task, task
from inspect_ai.model import ChatMessageAssistant
from inspect_ai.solver import TaskState, solver
from inspect_ai.util import sandbox

from evals.inspect.adapter import navi_runtime_success
from evals.inspect.swe_bench import (
    InspectSandboxBridge,
    SWEBenchInspectRunner,
    build_swe_bench_runner,
)


TERMINAL_BENCH_REF = (
    "sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a"
)
TERMINAL_BENCH_SYSTEM_PROMPT = (
    "Work directly in the provided terminal environment to complete the task. "
    "Inspect the environment first, make the required changes, and run focused "
    "checks before finishing. Do not merely describe commands or a solution: "
    "perform the work in the environment."
)


def _sandbox_env_name() -> str:
    return os.getenv("NAVI_EVAL_SANDBOX", "docker").strip().lower()


@solver
def terminal_bench_solver(runner: SWEBenchInspectRunner):
    async def solve(state: TaskState, generate):
        loop = asyncio.get_running_loop()
        result = await asyncio.to_thread(
            runner.run,
            state.user_prompt.text,
            sample_id=str(state.sample_id),
            sandbox_bridge=InspectSandboxBridge(
                loop=loop,
                environment=sandbox(),
            ),
            suite="terminal-bench-2-1",
            system_prompt=TERMINAL_BENCH_SYSTEM_PROMPT,
        )
        state.messages.append(ChatMessageAssistant(content=result.completion))
        state.output.completion = result.completion
        state.metadata["navi"] = result.metadata()
        return state

    return solve


def _terminal_bench_task(
    *,
    n_tasks: int | None = None,
    dataset_task_names: list[str] | None = None,
) -> Task:
    try:
        from inspect_harbor import terminal_bench_2_1
    except ImportError as exc:
        raise RuntimeError(
            "Terminal-Bench evaluation requires: uv sync --extra terminal-bench"
        ) from exc
    return terminal_bench_2_1(
        ref=TERMINAL_BENCH_REF,
        n_tasks=n_tasks,
        dataset_task_names=dataset_task_names,
        sandbox_env_name=_sandbox_env_name(),
    )


@task
def navi_terminal_bench_2_1(
    runner: SWEBenchInspectRunner | None = None,
    *,
    n_tasks: int | None = None,
    dataset_task_names: list[str] | None = None,
) -> Task:
    benchmark = _terminal_bench_task(
        n_tasks=n_tasks,
        dataset_task_names=dataset_task_names,
    )
    benchmark.solver = terminal_bench_solver(runner or build_swe_bench_runner())
    benchmark.scorer = [
        *(list(benchmark.scorer) if benchmark.scorer else []),
        navi_runtime_success(),
    ]
    benchmark.metadata = {
        **(benchmark.metadata or {}),
        "agent": "navi-agent",
        "dataset": "terminal-bench/terminal-bench-2-1",
        "dataset_ref": TERMINAL_BENCH_REF,
        "sandbox": _sandbox_env_name(),
    }
    return benchmark
