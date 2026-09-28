import asyncio
from types import SimpleNamespace

from evals.inspect.modal_sandbox import (
    ModalSandboxEnvironment,
    quote_shell,
    swe_bench_modal_image,
)


def test_uses_amd64_swe_bench_image_name() -> None:
    assert (
        swe_bench_modal_image("django__django-11790")
        == "ghcr.io/epoch-research/swe-bench.eval.django__django-11790:latest"
    )


def test_quote_shell_handles_single_quotes() -> None:
    assert quote_shell("/tmp/it's") == "'/tmp/it'\\''s'"


def test_modal_environment_exec_and_filesystem() -> None:
    class FakeProcess:
        returncode = 0
        stdout = SimpleNamespace(read=lambda: "ok\n")
        stderr = SimpleNamespace(read=lambda: "")

        def wait(self):
            return None

    class FakeFilesystem:
        def __init__(self):
            self.files = {}

        def read_text(self, path):
            return self.files[path]

        def write_text(self, content, path):
            self.files[path] = content

    class FakeSandbox:
        def __init__(self):
            self.filesystem = FakeFilesystem()
            self.commands = []

        def exec(self, *command, timeout=None):
            self.commands.append((command, timeout))
            return FakeProcess()

        def terminate(self, wait=True):
            assert wait is True

        def detach(self):
            return None

    async def run():
        sandbox = FakeSandbox()
        environment = ModalSandboxEnvironment(sandbox)
        result = await environment.exec(
            ["bash", "--login", "-c", "pytest -q"],
            cwd="/testbed",
            timeout=30,
        )
        await environment.write_file("a.txt", "content")
        content = await environment.read_file("a.txt")
        await environment.close()
        return sandbox, result, content

    sandbox, result, content = asyncio.run(run())
    assert result.returncode == 0
    assert result.stdout == "ok\n"
    assert content == "content"
    assert sandbox.commands == [
        (("bash", "--login", "-c", "cd '/testbed' && pytest -q"), 30)
    ]
