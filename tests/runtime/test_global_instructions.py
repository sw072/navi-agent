from pathlib import Path

import pytest

from navi_agent.app.bootstrap import build_runtime
from navi_agent.config import ModelSettings, RuntimeSettings
from navi_agent.runtime import AgentProfile, ModelResponse
from navi_agent.runtime.agent.prompt import PromptBuilder
from navi_agent.runtime.agent.prompt_contributors import GlobalInstructionsContributor
from navi_agent.runtime.agent.prompt_pipeline import PromptContributionError


@pytest.fixture
def navi_home(tmp_path, monkeypatch):
    root = tmp_path / "navi-home"
    root.mkdir()
    monkeypatch.setenv("NAVI_HOME", str(root))
    return root


def render(builder):
    return builder.build_run_system_message(user_id="u1", user_message="hello").content


@pytest.mark.parametrize("content", [None, "", " \n\t"])
def test_missing_or_empty_global_instructions_are_skipped(navi_home, content):
    if content is not None:
        (navi_home / "AGENTS.md").write_text(content, encoding="utf-8")
    builder = PromptBuilder()

    assert "[Global Instructions]" not in render(builder)
    assert "global-instructions" not in builder.last_prompt_sources
    assert builder.last_injected_context_files == []


@pytest.mark.parametrize("project_file", ["AGENTS.md", ".navi.md"])
def test_global_and_project_instructions_are_loaded_together(navi_home, tmp_path, project_file):
    global_path = navi_home / "AGENTS.md"
    global_path.write_text("默认使用中文回答。", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("Use project test commands.", encoding="utf-8")
    if project_file == ".navi.md":
        (project / project_file).write_text("Use Navi project commands.", encoding="utf-8")
    builder = PromptBuilder(project_context_root=project)

    prompt = render(builder)

    assert "默认使用中文回答。" in prompt
    assert prompt.index("[Global Instructions]") < prompt.index("[Project Context]")
    assert "prefer the user's current request, then applicable project instructions, then these global defaults" in prompt
    assert builder.last_injected_context_files == [str(global_path.resolve()), project_file]
    assert builder.last_prompt_sources.index("global-instructions") < builder.last_prompt_sources.index("project-context")
    if project_file == ".navi.md":
        assert "Use Navi project commands." in prompt
        assert "Use project test commands." not in prompt
    else:
        assert "Use project test commands." in prompt


@pytest.mark.parametrize("profile", ["", "work"])
def test_global_instructions_follow_default_home_and_profile(tmp_path, monkeypatch, profile):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("NAVI_HOME", raising=False)
    monkeypatch.setenv("NAVI_PROFILE", profile)
    root = tmp_path / ".navi-agent"
    root.mkdir()
    (root / "AGENTS.md").write_text("Default home instructions.", encoding="utf-8")
    if profile:
        root = root / "profiles" / profile
        root.mkdir(parents=True)
        (root / "AGENTS.md").write_text("Profile instructions.", encoding="utf-8")
    builder = PromptBuilder()

    prompt = render(builder)

    assert builder.last_injected_context_files == [str((root / "AGENTS.md").resolve())]
    if profile:
        assert "Profile instructions." in prompt
        assert "Default home instructions." not in prompt
    else:
        assert "Default home instructions." in prompt


def test_navi_home_overrides_profile(navi_home, monkeypatch):
    monkeypatch.setenv("NAVI_PROFILE", "unused")
    (navi_home / "AGENTS.md").write_text("Custom home instructions.", encoding="utf-8")

    assert "Custom home instructions." in render(PromptBuilder())


def test_runtime_sends_global_and_project_instructions_to_model(navi_home, tmp_path):
    (navi_home / "AGENTS.md").write_text("Global test instruction.", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("Project test instruction.", encoding="utf-8")
    requests = []

    class Transport:
        def generate(self, request):
            requests.append(request)
            return ModelResponse(content="done")

    runtime = build_runtime(
        model_settings=ModelSettings(model="test"),
        runtime_settings=RuntimeSettings(max_iterations=1),
        workspace_root=project,
        primary_profile=AgentProfile(role="primary", max_iterations=1, transport=Transport()),
    )
    try:
        result = runtime.run_conversation(session_id="s1", user_id="u1", user_message="hello")
    finally:
        runtime.close()

    assert result.final_response == "done"
    assert len(requests) == 1
    system = requests[0].messages[0]
    assert system.role == "system"
    assert "Global test instruction." in system.content
    assert "Project test instruction." in system.content
    assert system.content.index("[Global Instructions]") < system.content.index("[Project Context]")


def test_global_instructions_are_reread_for_each_request(navi_home):
    path = navi_home / "AGENTS.md"
    path.write_text("First instructions.", encoding="utf-8")
    builder = PromptBuilder()
    assert "First instructions." in render(builder)

    path.write_text("Updated instructions.", encoding="utf-8")
    prompt = render(builder)
    assert "Updated instructions." in prompt
    assert "First instructions." not in prompt

    path.unlink()
    assert "[Global Instructions]" not in render(builder)
    assert builder.last_injected_context_files == []


@pytest.mark.parametrize("size", [20_000, 20_001])
def test_long_global_instructions_preserve_head_and_tail(navi_home, size):
    content = "H" * 14_000 + "M" * (size - 18_000) + "T" * 4_000
    (navi_home / "AGENTS.md").write_text(content, encoding="utf-8")

    prompt = render(PromptBuilder())

    if size == 20_000:
        assert content in prompt
        assert "truncated" not in prompt
    else:
        assert "H" * 14_000 + "\n[... global instructions truncated ...]\n" + "T" * 4_000 in prompt
        assert "MMM" not in prompt


def test_unreadable_global_instructions_report_the_source(navi_home, monkeypatch):
    path = navi_home / "AGENTS.md"
    path.write_text("Instructions.", encoding="utf-8")
    builder = PromptBuilder(contributors=[GlobalInstructionsContributor(path)])

    def deny_read(*args, **kwargs):
        raise PermissionError("Cannot read global instructions")

    monkeypatch.setattr(Path, "read_text", deny_read)
    with pytest.raises(PromptContributionError, match="global-instructions") as exc:
        render(builder)
    assert isinstance(exc.value.__cause__, PermissionError)
