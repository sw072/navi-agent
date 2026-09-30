from inspect_ai import Task
from inspect_ai.dataset import Sample

from evals.inspect.terminal_bench import (
    TERMINAL_BENCH_REF,
    _terminal_bench_task,
    navi_terminal_bench_2_1,
)


def test_builds_terminal_bench_from_inspect_harbor(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_terminal_bench_2_1(**kwargs):
        calls.update(kwargs)
        return Task(dataset=[Sample(id="smoke", input="Complete the task.")])

    monkeypatch.setattr(
        "inspect_harbor.terminal_bench_2_1",
        fake_terminal_bench_2_1,
    )
    monkeypatch.setenv("NAVI_EVAL_SANDBOX", "modal")

    task = _terminal_bench_task(n_tasks=1)

    assert len(task.dataset) == 1
    assert calls == {
        "ref": TERMINAL_BENCH_REF,
        "n_tasks": 1,
        "dataset_task_names": None,
        "sandbox_env_name": "modal",
    }


def test_adds_navi_solver_and_runtime_scorer(monkeypatch) -> None:
    def fake_terminal_bench_2_1(**kwargs):
        return Task(dataset=[Sample(id="smoke", input="Complete the task.")])

    monkeypatch.setattr(
        "inspect_harbor.terminal_bench_2_1",
        fake_terminal_bench_2_1,
    )

    task = navi_terminal_bench_2_1(runner=object(), n_tasks=1)

    assert len(task.scorer) == 1
    assert task.metadata["agent"] == "navi-agent"
    assert task.metadata["dataset_ref"] == TERMINAL_BENCH_REF
