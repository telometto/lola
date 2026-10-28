"""Source refresh preserves the content selected during registration."""

import json
from pathlib import Path
import shutil
import subprocess

from click.testing import CliRunner
import pytest

from lola.__main__ import main
from lola.agent_plugins import PLUGIN_SCHEMA
from lola.cli.mod import load_registered_module
from lola.parsers import fetch_module, load_source_info, save_source_info
from lola.parsers import update_module


@pytest.mark.parametrize(
    "selection",
    [
        pytest.param(
            ("plugins/selected", "plugins/selected", False),
            id="nested-content",
        ),
        pytest.param(
            ("plugins/selected", "plugins/selected", True),
            id="nested-plugin",
        ),
        pytest.param(("module", "module", False), id="module-directory"),
        pytest.param(("/", "", False), id="explicit-root"),
        pytest.param((None, "module", False), id="auto-discovery"),
    ],
)
def test_refresh_updates_installed_skill(
    cli_runner: CliRunner,
    mock_lola_home: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    selection: tuple[str | None, str, bool],
) -> None:
    """Original-source changes reach installed skills across source layouts."""
    content_dirname, layout, is_plugin = selection
    tmp_path = mock_lola_home["home"].parent
    monkeypatch.setattr("lola.utils.LOLA_HOME", mock_lola_home["home"])
    monkeypatch.setattr("lola.utils.MODULES_DIR", mock_lola_home["modules"])
    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "repository"
    content = source / layout
    skill = content / "skills" / "review"
    skill.mkdir(parents=True)
    if is_plugin:
        (content / "plugin.json").write_text(
            json.dumps({"$schema": PLUGIN_SCHEMA, "name": "selected"})
        )
    definition = skill / "SKILL.md"
    definition.write_text(
        "---\nname: review\ndescription: Review code\n---\nVersion one\n"
    )
    supporting_file = skill / "guide.txt"
    supporting_file.write_text("Original guide\n")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)

    add_args = ["mod", "add", str(source), "--name", "selected"]
    if content_dirname is not None:
        add_args.extend(["--module-content", content_dirname])
    added = cli_runner.invoke(main, add_args)
    assert added.exit_code == 0, added.output
    registered_path = mock_lola_home["modules"] / "selected"
    source_info = load_source_info(registered_path)
    assert source_info is not None
    assert source_info["source"] == str(source)
    assert source_info.get("content_dirname") == content_dirname
    installed = cli_runner.invoke(
        main,
        ["install", "selected", "-a", "claude-code"],
    )
    assert installed.exit_code == 0, installed.output
    installed_skill = project / ".claude" / "skills" / "review"
    assert (installed_skill / "guide.txt").read_text() == "Original guide\n"

    definition.write_text(
        "---\nname: review\ndescription: Review code\n---\nVersion two\n"
    )
    supporting_file.write_text("Updated guide\n")
    refreshed = cli_runner.invoke(main, ["mod", "update", "selected"])
    assert refreshed.exit_code == 0, refreshed.output
    regenerated = cli_runner.invoke(main, ["update", "selected"])
    assert regenerated.exit_code == 0, regenerated.output

    assert (installed_skill / "guide.txt").read_text() == "Updated guide\n"
    assert (installed_skill / "SKILL.md").read_text() == definition.read_text()
    assert load_source_info(registered_path) == source_info
    registered = load_registered_module(registered_path)
    assert registered is not None
    assert registered.name == "selected"
    assert registered.skills == ["review"]


def test_refresh_preserves_pinned_git_content(tmp_path: Path) -> None:
    """Refreshing a nested Git module keeps its identity, ref, and content."""
    source = tmp_path / "repository.git"
    source.mkdir()
    _git(source, "init", "--initial-branch=main")
    content_dirname = "plugins/selected"
    skill = source / content_dirname / "skills" / "review"
    skill.mkdir(parents=True)
    definition = skill / "SKILL.md"
    definition.write_text("---\ndescription: Pinned review\n---\n")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "Pinned version")
    _git(source, "tag", "v1.0.0")

    modules = tmp_path / "modules"
    modules.mkdir()
    fetched = fetch_module(
        source.as_uri(),
        modules,
        content_dirname,
        ref="v1.0.0",
    )
    registered_path = modules / "selected"
    fetched.rename(registered_path)
    save_source_info(
        registered_path,
        source.as_uri(),
        "git",
        content_dirname,
        "v1.0.0",
    )
    source_info = load_source_info(registered_path)

    definition.write_text("---\ndescription: Latest review\n---\n")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "Latest version")
    update_module(registered_path)

    assert load_source_info(registered_path) == source_info
    registered = load_registered_module(registered_path)
    assert registered is not None
    assert registered.name == "selected"
    assert registered.skills == ["review"]
    cached_skill = registered.content_path / "skills" / "review" / "SKILL.md"
    assert cached_skill.read_text() == "---\ndescription: Pinned review\n---\n"


@pytest.mark.parametrize("archive_format", ["zip", "gztar"])
@pytest.mark.parametrize("remote", [False, True], ids=["local", "url"])
def test_refresh_updates_archive_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    archive_format: str,
    remote: bool,
) -> None:
    """Local and downloaded archives refresh files and retain source info."""
    source = tmp_path / "original"
    skill = source / "skills" / "review"
    skill.mkdir(parents=True)
    definition = skill / "SKILL.md"
    definition.write_text("---\ndescription: Original review\n---\n")
    archive_base = str(tmp_path / "bundle")
    archive = Path(
        shutil.make_archive(
            archive_base,
            archive_format,
            source.parent,
            source.name,
        )
    )
    # Replace the external HTTP response, keeping extraction and fetch real.
    monkeypatch.setattr(
        "lola.parsers.urlopen", lambda *args, **kwargs: archive.open("rb")
    )
    source_url = str(archive)
    source_type = "zip" if archive_format == "zip" else "tar"
    if remote:
        source_url = f"https://example.com/{archive.name}"
        source_type += "url"
    modules = tmp_path / "modules"
    modules.mkdir()
    registered_path = fetch_module(source_url, modules, "/")
    save_source_info(registered_path, source_url, source_type, "/")
    source_info = load_source_info(registered_path)

    definition.write_text("---\ndescription: Updated review\n---\n")
    shutil.make_archive(
        archive_base,
        archive_format,
        source.parent,
        source.name,
    )
    update_module(registered_path)

    assert load_source_info(registered_path) == source_info
    registered = load_registered_module(registered_path)
    assert registered is not None
    assert registered.name == "original"
    cached_skill = registered.content_path / "skills" / "review" / "SKILL.md"
    assert cached_skill.read_text() == "---\ndescription: Updated review\n---\n"


def _git(repository: Path, *args: str) -> None:
    """Run Git locally without inheriting the developer's commit identity."""
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Lola tests",
            "-c",
            "user.email=tests@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
