"""Subprocess wrapper for invoking the lola CLI in E2E tests."""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def _find_lola() -> str:
    """Find the lola binary, preferring the active venv."""
    venv_bin = Path(sys.executable).parent / "lola"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("lola")
    if found:
        return found
    raise FileNotFoundError("lola binary not found. Install with: pip install -e .")


_LOLA_BIN = _find_lola()


@dataclass
class LolaResult:
    """Captured output from a lola CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str


class LolaCLI:
    """Run `lola` with isolated registry and user configuration paths."""

    def __init__(self, lola_home: Path, work_dir: Path) -> None:
        """Initialize with the LOLA_HOME path and working directory."""
        user_home = lola_home.parent / "home"
        user_home.mkdir(parents=True, exist_ok=True)
        self.env = {
            **os.environ,
            "LOLA_HOME": str(lola_home),
            "HOME": str(user_home),
            "USERPROFILE": str(user_home),
            "CODEX_HOME": str(user_home / ".codex"),
            "XDG_CONFIG_HOME": str(user_home / ".config"),
        }
        self.work_dir = work_dir

    def run(self, *args: str, timeout: int = 30) -> LolaResult:
        """Run `lola <args>` as a subprocess and return captured output."""
        result = subprocess.run(
            [_LOLA_BIN, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            cwd=self.work_dir,
            env=self.env,
            timeout=timeout,
        )
        return LolaResult(result.returncode, result.stdout, result.stderr)


def resolve_path(context, text: str) -> str:
    """Replace placeholders like {lola_home} and {project} with scenario paths.

    Use {name_path} for a specific module. {module_path} is a shorthand that
    resolves to the most recently added module — use only when the scenario
    has a single module.
    """
    replacements = {
        "{lola_home}": str(context.lola_home),
        "{project}": str(context.project_dir),
        "{home}": context.cli.env["HOME"],
        "{tmp}": str(context.tmp_dir),
    }
    if hasattr(context, "server_url"):
        replacements["{server_url}"] = context.server_url
    for name, path in context.modules.items():
        replacements[f"{{{name}_path}}"] = str(path)
    if context.modules:
        last_module = list(context.modules.values())[-1]
        replacements["{module_path}"] = str(last_module)
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def read_normalized(path: Path) -> str:
    """Read a file and normalize line endings to Unix-style."""
    return path.read_text().replace("\r\n", "\n")
