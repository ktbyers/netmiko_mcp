"""Exercise the shared shell entry point without installing packages or contacting devices."""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "tests.sh"
_VERSIONS = ["3.11", "3.12", "3.13", "3.14", "3.15"]
_PLATFORMS = ["linux", "macos", "windows", "wasm32-pyodide2025"]


@pytest.fixture
def fake_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Record uv commands and optionally fail a selected command prefix."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.jsonl"
    failure = tmp_path / "failure.json"
    uv = bin_dir / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        f"failure = Path({str(failure)!r})\n"
        "args = sys.argv[1:]\n"
        "with log.open(mode='a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps({'args': args, 'cwd': str(Path.cwd()), "
        "'live': 'RUN_LIVE_TESTS' in os.environ}) + '\\n')\n"
        "if failure.exists():\n"
        "    prefix = json.loads(failure.read_text(encoding='utf-8'))\n"
        "    if args[:len(prefix)] == prefix:\n"
        "        raise SystemExit(7)\n",
        encoding="utf-8",
    )
    uv.chmod(mode=0o755)
    monkeypatch.setenv(name="PATH", value=f"{bin_dir}{os.pathsep}{os.defpath}")
    return log, failure


def _run(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args=["bash", str(_SCRIPT), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _records(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_default_runs_ci_checks_and_matrices(
    fake_uv: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log, _ = fake_uv
    monkeypatch.setenv(name="RUN_LIVE_TESTS", value="1")
    result = _run(arguments=[], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    records = _records(log=log)
    commands = [record["args"] for record in records]
    assert commands[0] == ["lock", "--check"]
    assert commands[1] == ["sync", "--frozen", "--python", "3.13"]
    checks = [command[5:] for command in commands if command[:2] == ["run", "--frozen"]]
    assert checks[:5] == [
        ["format", "--check", "."],
        ["check", "."],
        ["src", "tests"],
        ["-r", "src/"],
        [],
    ]
    assert [command[4] for command in commands[2:7]] == [
        "ruff",
        "ruff",
        "mypy",
        "bandit",
        "pip-audit",
    ]
    audits = [command for command in commands if command[0] == "audit"]
    assert audits == [
        ["audit", "--frozen", "--python-version", version, "--python-platform", platform]
        for version in _VERSIONS
        for platform in _PLATFORMS
    ]
    tests = [command for command in commands if "pytest" in command]
    assert [command[4] for command in tests] == _VERSIONS
    assert all(command[:4] == ["run", "--frozen", "--isolated", "--python"] for command in tests)
    for command in tests:
        assert ("--cov-fail-under=98" in command) == (command[4] == "3.13")
    assert all(record["cwd"] == str(_ROOT) for record in records)
    assert all(not record["live"] for record in records)


def test_audit_mode_only_audits_lock(fake_uv: tuple[Path, Path], tmp_path: Path) -> None:
    log, _ = fake_uv
    result = _run(arguments=["audit"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    commands = [record["args"] for record in _records(log=log)]
    assert len(commands) == 21
    assert commands[0] == ["lock", "--check"]
    assert all(command[:2] == ["audit", "--frozen"] for command in commands[1:])


@pytest.mark.parametrize("version", _VERSIONS)
def test_single_python_mode(fake_uv: tuple[Path, Path], tmp_path: Path, version: str) -> None:
    log, _ = fake_uv
    result = _run(arguments=["test", version], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    commands = [record["args"] for record in _records(log=log)]
    assert len(commands) == 2
    assert commands[1][:7] == ["run", "--frozen", "--isolated", "--python", version, "pytest", "-v"]
    assert ("--cov-fail-under=98" in commands[1]) == (version == "3.13")


@pytest.mark.parametrize(
    "arguments",
    [
        ["test"],
        ["test", "3.10"],
        ["test", "3.16"],
        ["test", "3.13", "extra"],
        ["audit", "extra"],
        ["unknown"],
    ],
)
def test_invalid_arguments_fail_before_uv(
    fake_uv: tuple[Path, Path], tmp_path: Path, arguments: list[str]
) -> None:
    log, _ = fake_uv
    result = _run(arguments=arguments, cwd=tmp_path)
    assert result.returncode == 2
    assert not _records(log=log)


@pytest.mark.parametrize("prefix", [["lock"], ["run"], ["audit"]])
def test_failures_stop_the_workflow(
    fake_uv: tuple[Path, Path], tmp_path: Path, prefix: list[str]
) -> None:
    log, failure = fake_uv
    failure.write_text(data=json.dumps(prefix), encoding="utf-8")
    result = _run(arguments=[], cwd=tmp_path)
    assert result.returncode == 7
    commands = [record["args"] for record in _records(log=log)]
    assert commands[-1][: len(prefix)] == prefix
    assert not any("pytest" in command for command in commands)


def test_help_does_not_run_uv(fake_uv: tuple[Path, Path], tmp_path: Path) -> None:
    log, _ = fake_uv
    result = _run(arguments=["--help"], cwd=tmp_path)
    assert result.returncode == 0
    assert "audit" in result.stdout
    assert not _records(log=log)


def test_ci_uses_shared_commands_and_supported_python_matrix() -> None:
    workflow = yaml.safe_load(
        (_ROOT / ".github/workflows/main_testing.yaml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]
    assert jobs["unit-tests"]["strategy"]["matrix"]["python-version"] == _VERSIONS
    expected = {
        "checks": "./tests.sh checks",
        "audit": "./tests.sh audit",
        "unit-tests": "./tests.sh test '${{ matrix.python-version }}'",
    }
    for name, command in expected.items():
        assert [step["run"] for step in jobs[name]["steps"] if "run" in step] == [command]
        setup = next(step for step in jobs[name]["steps"] if "setup-uv@" in step.get("uses", ""))
        assert setup["with"]["version"] == "0.13.5"
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    versions = [
        item.rsplit(" ", maxsplit=1)[-1]
        for item in project["project"]["classifiers"]
        if item.startswith("Programming Language :: Python :: 3.")
    ]
    assert versions == _VERSIONS
    assert project["tool"]["uv"]["required-version"] == ">=0.13.5"
