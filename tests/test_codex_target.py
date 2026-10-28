"""Codex skill installation through Lola's public interfaces."""

import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from lola import frontmatter
from lola.__main__ import main
from lola.cli.install import install_cmd, uninstall_cmd, update_cmd
from lola.cli.sync import sync_cmd
from lola.models import InstallationRegistry
from lola.targets import get_registry, get_target


@pytest.fixture
def codex_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolate all user destinations and the working project."""
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.chdir(project)
    return home


def test_install_codex_skill(
    cli_runner: CliRunner,
    registered_module: Path,
    mock_lola_home: dict[str, Path],
    tmp_path: Path,
) -> None:
    """A registered legacy skill becomes a discoverable Codex skill."""
    project = tmp_path / "project"
    project.mkdir()
    source = registered_module / "skills" / "skill1" / "SKILL.md"
    original = source.read_bytes()

    result = cli_runner.invoke(
        install_cmd,
        ["sample-module", "-a", "codex", str(project)],
    )

    assert result.exit_code == 0, result.output
    skill = project / ".agents" / "skills" / "skill1" / "SKILL.md"
    metadata, body = frontmatter.parse_file(skill)
    assert metadata == {
        "name": "skill1",
        "description": "A test skill",
    }
    assert "This is a test skill." in body
    assert source.read_bytes() == original
    registry = InstallationRegistry(mock_lola_home["installed"])
    installations = registry.all()
    assert len(installations) == 1
    assert installations[0].assistant == "codex"
    assert installations[0].scope == "project"
    assert installations[0].project_path == str(project)
    assert installations[0].skills == ["skill1"]
    assert installations[0].commands == []
    assert installations[0].agents == []


def test_generate_preserves_native_skill_and_resources(
    tmp_path: Path,
) -> None:
    """Native metadata, nested resources, and script modes survive install."""
    source = tmp_path / "source"
    source.mkdir()
    content = (
        "---\n"
        "name: native-skill\n"
        "description: 'Use this: for testing'\n"
        "metadata: {version: '1.0'}\n"
        "---\n\n"
        "# Native skill\n\nSee ./references/guide.md.\n\n"
    )
    (source / "SKILL.md").write_text(content)
    resources = {
        "agents/openai.yaml": "interface:\n  display_name: Native Skill\n",
        "scripts/helper.sh": "#!/bin/sh\nprintf 'hello\\n'\n",
        "references/nested/guide.md": "Supporting reference\n",
        "assets/example.bin": "example\x00asset",
        "notes.md": "Top-level resource\n",
    }
    for relative, text in resources.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (source / "scripts/helper.sh").chmod(0o751)
    destination = tmp_path / "installed"

    assert get_target("codex").generate_skill(
        source,
        destination,
        "native-skill",
    )

    installed = destination / "native-skill"
    assert (installed / "SKILL.md").read_text() == content
    for relative, text in resources.items():
        assert (installed / relative).read_text() == text
    assert (installed / "scripts/helper.sh").stat().st_mode & 0o777 == 0o751


@pytest.mark.parametrize("scope", ["project", "user"])
def test_codex_skill_lifecycle(
    cli_runner: CliRunner,
    registered_module: Path,
    codex_home: Path,
    scope: str,
) -> None:
    """Persist scope, refresh resources, and remove orphaned skills."""
    project = Path.cwd()
    root = codex_home if scope == "user" else project
    skills = root / ".agents" / "skills"
    source = registered_module / "skills" / "skill1"
    (source / "notes.md").write_text("old notes")
    scripts = source / "scripts"
    scripts.mkdir()
    (scripts / "obsolete.sh").write_text("old script")
    orphan = registered_module / "skills" / "obsolete-skill"
    orphan.mkdir()
    (orphan / "SKILL.md").write_text(
        "---\ndescription: Obsolete skill\n---\nOld skill\n"
    )

    result = cli_runner.invoke(
        install_cmd, ["sample-module", "-a", "codex", "--scope", scope]
    )
    assert result.exit_code == 0, result.output
    assert (skills / "skill1" / "notes.md").read_text() == "old notes"
    assert (skills / "obsolete-skill" / "SKILL.md").is_file()
    installation = get_registry().all()[0]
    assert installation.scope == scope
    expected_project = str(project) if scope == "project" else None
    assert installation.project_path == expected_project

    (source / "notes.md").unlink()
    (scripts / "obsolete.sh").unlink()
    (scripts / "current.sh").write_text("new script")
    shutil.rmtree(orphan)
    result = cli_runner.invoke(update_cmd, ["sample-module", "-a", "codex"])
    assert result.exit_code == 0, result.output
    assert (skills / "skill1/scripts/current.sh").read_text() == "new script"
    assert not (skills / "skill1/scripts/obsolete.sh").exists()
    assert not (skills / "skill1/notes.md").exists()
    assert not (skills / "obsolete-skill").exists()
    installation = get_registry().all()[0]
    assert installation.skills == ["skill1"]
    assert installation.project_path == expected_project
    assert not (project.parent / "codex-home" / "skills").exists()

    unrelated = skills / "unrelated-skill"
    unrelated.mkdir()
    (unrelated / "SKILL.md").write_text("Unmanaged skill")
    result = cli_runner.invoke(
        uninstall_cmd,
        ["sample-module", "-a", "codex", "--scope", scope, "--force"],
    )
    assert result.exit_code == 0, result.output
    assert not (skills / "skill1").exists()
    assert (unrelated / "SKILL.md").read_text() == "Unmanaged skill"
    assert not get_registry().all()
    assert (registered_module / "skills" / "skill1" / "SKILL.md").is_file()


@pytest.mark.parametrize(
    "skill_name", ["", ".", "..", "../escape", "nested/skill", "bad\\name"]
)
def test_generate_rejects_unsafe_install_names(
    tmp_path: Path,
    skill_name: str,
) -> None:
    """Skill names cannot escape the assistant's skill directory."""
    source = tmp_path / "source"
    source.mkdir()
    content = "---\ndescription: Test skill\n---\nTest\n"
    (source / "SKILL.md").write_text(content)
    destination = tmp_path / "installed"

    assert not get_target("codex").generate_skill(
        source,
        destination,
        skill_name,
    )

    assert not destination.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "content",
    [
        None,
        "# Missing frontmatter",
        "---\ndescription: [bad YAML\n---\n",
        "---\nname: test\n---\n",
        "---\ndescription: ' '\n---\n",
        "---\ndescription: 123\n---\n",
    ],
)
def test_invalid_metadata_preserves_existing_skill(
    tmp_path: Path, content: str | None
) -> None:
    """An invalid skill cannot replace a previously installed skill."""
    source = tmp_path / "source"
    source.mkdir()
    if content is not None:
        (source / "SKILL.md").write_text(content)
    destination = tmp_path / "installed"
    existing = destination / "test"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("Existing skill")

    assert not get_target("codex").generate_skill(source, destination, "test")

    assert (existing / "SKILL.md").read_text() == "Existing skill"


@pytest.mark.usefixtures("codex_home", "mock_lola_home")
def test_mixed_module_only_installs_skills(
    cli_runner: CliRunner, sample_module_with_instructions: Path
) -> None:
    """Unsupported module content leaves Codex configuration untouched."""
    project = Path.cwd()
    instructions = project / "AGENTS.md"
    instructions.write_text("Existing project instructions.\n")
    (sample_module_with_instructions / "mcps.json").write_text(
        json.dumps({"mcpServers": {"example": {"command": "example"}}})
    )
    result = cli_runner.invoke(
        main, ["mod", "add", str(sample_module_with_instructions)]
    )
    assert result.exit_code == 0, result.output
    for command in (install_cmd, update_cmd):
        result = cli_runner.invoke(command, ["sample-module", "-a", "codex"])
        assert result.exit_code == 0, result.output
        installation = get_registry().all()[0]
        assert installation.skills == ["skill1"]
        assert installation.commands == []
        assert installation.agents == []
        assert installation.mcps == []
        assert not installation.has_instructions
        assert instructions.read_text() == "Existing project instructions.\n"
        assert not (project / ".codex").exists()


@pytest.mark.usefixtures("codex_home")
def test_conflict_rename_uses_effective_skill_name(
    cli_runner: CliRunner, registered_module: Path
) -> None:
    """Renaming a collision changes Codex's discovered name and lifecycle."""
    other = registered_module.parent / "other-module"
    shutil.copytree(registered_module, other)
    other_skill = other / "skills" / "skill1" / "SKILL.md"
    other_skill.write_text(
        "---\nname: original\ndescription: Other workflow\n---\nOther body\n"
    )
    result = cli_runner.invoke(install_cmd, ["sample-module", "-a", "codex"])
    assert result.exit_code == 0, result.output
    with patch("lola.targets.install.is_interactive", return_value=True):
        result = cli_runner.invoke(
            install_cmd,
            ["other-module", "-a", "codex"],
            input="n\ny\n",
        )
    assert result.exit_code == 0, result.output
    skills = Path.cwd() / ".agents" / "skills"
    renamed = skills / "other-module_skill1" / "SKILL.md"
    assert frontmatter.get_metadata(renamed)["name"] == "other-module_skill1"
    assert frontmatter.get_metadata(other_skill)["name"] == "original"
    result = cli_runner.invoke(update_cmd, ["other-module", "-a", "codex"])
    assert result.exit_code == 0, result.output
    assert frontmatter.get_metadata(renamed)["name"] == "other-module_skill1"
    result = cli_runner.invoke(
        uninstall_cmd, ["other-module", "-a", "codex", "--force"]
    )
    assert result.exit_code == 0, result.output
    assert not renamed.exists()
    assert (skills / "skill1" / "SKILL.md").exists()


@pytest.mark.usefixtures("codex_home")
@pytest.mark.parametrize("selection", ["flag", "fragment", "default"])
def test_sync_selects_codex(
    cli_runner: CliRunner,
    registered_module: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
) -> None:
    """Sync selects Codex explicitly and with the default assistants."""
    monkeypatch.setattr("lola.cli.sync.MODULES_DIR", registered_module.parent)
    line = "sample-module"
    if selection == "fragment":
        line += "#assistant=codex"
    (Path.cwd() / ".lola-req").write_text(line + "\n")
    args = ["-a", "codex"] if selection == "flag" else []
    result = cli_runner.invoke(sync_cmd, args)
    assert result.exit_code == 0, result.output
    skill = Path.cwd() / ".agents" / "skills" / "skill1" / "SKILL.md"
    assert frontmatter.get_metadata(skill)["name"] == "skill1"
    assistants = {inst.assistant for inst in get_registry().all()}
    if selection == "default":
        assert "codex" in assistants
        assert "claude-code" in assistants
    else:
        assert assistants == {"codex"}
    result = cli_runner.invoke(sync_cmd, args)
    assert result.exit_code == 0, result.output
    assert "Skipped:" in result.output


@pytest.mark.usefixtures("codex_home")
def test_implicit_install_includes_codex(
    cli_runner: CliRunner, registered_module: Path
) -> None:
    """Noninteractive installation without -a also generates Codex skills."""
    result = cli_runner.invoke(install_cmd, [registered_module.name])
    assert result.exit_code == 0, result.output
    skill = Path.cwd() / ".agents" / "skills" / "skill1" / "SKILL.md"
    assert frontmatter.get_metadata(skill)["name"] == "skill1"
    assert "codex" in {inst.assistant for inst in get_registry().all()}


@pytest.mark.parametrize("command", ["install", "uninstall", "update", "sync"])
def test_codex_assistant_shell_completion(
    cli_runner: CliRunner,
    command: str,
) -> None:
    """The assistant option advertises Codex through shell completion."""
    result = cli_runner.invoke(
        main,
        [],
        prog_name="lola",
        env={
            "_LOLA_COMPLETE": "bash_complete",
            "COMP_WORDS": f"lola {command} -a co",
            "COMP_CWORD": "3",
        },
    )
    assert result.exit_code == 0, result.output
    assert "plain,codex" in result.output


@pytest.mark.usefixtures("codex_home")
@pytest.mark.parametrize(
    "layout",
    ["single", "module-single", "bundle", "module-bundle", "plugin"],
)
def test_codex_installs_supported_source_layouts(
    cli_runner: CliRunner,
    mock_lola_home: dict[str, Path],
    layout: str,
) -> None:
    """Single skills, wrapped bundles, and nested plugins use shared parsing."""
    project = Path.cwd()
    source = project.parent / "layout-module"
    content = source
    add_args = ["mod", "add", str(source), "--name", "layout-module"]
    if layout.startswith("module-"):
        content = source / "module"
        add_args += ["--module-content", "module"]
    elif layout == "plugin":
        content = source / "packages" / "tools"
        add_args += ["--module-content", "packages/tools"]
    skill = content if layout.endswith("single") else content / "skills/native"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: native\ndescription: Layout test\n---\nRead ./notes.md\n"
    )
    (skill / "notes.md").write_text("Supporting file")
    if layout == "plugin":
        schema = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        (content / "plugin.json").write_text(
            json.dumps(
                {
                    "$schema": schema,
                    "name": "layout-module",
                }
            )
        )
    result = cli_runner.invoke(main, add_args)
    assert result.exit_code == 0, result.output
    result = cli_runner.invoke(install_cmd, ["layout-module", "-a", "codex"])
    assert result.exit_code == 0, result.output
    installed = project / ".agents" / "skills" / "native"
    assert frontmatter.get_metadata(installed / "SKILL.md")["name"] == "native"
    assert (installed / "notes.md").read_text() == "Supporting file"
    cached_skill = (
        mock_lola_home["modules"] / "layout-module" / skill.relative_to(source)
    )
    (cached_skill / "notes.md").write_text("Changed source")
    result = cli_runner.invoke(update_cmd, ["layout-module", "-a", "codex"])
    assert result.exit_code == 0, result.output
    assert (installed / "notes.md").read_text() == "Changed source"
