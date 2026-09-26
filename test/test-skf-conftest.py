#!/usr/bin/env python3
"""Tests for test/conftest.py, the suite-wide git environment scrub, and
for the matching `unset` line in .husky/pre-commit.

- pytest loads test/conftest.py for an explicit file argument, the way
  package.json test:python runs the suite, and drops every listed variable
  before a test starts: checked in a child pytest whose environment carries
  what a git hook exports (CI never sets these, so an in-process check
  alone would prove nothing).
- git children see no system config, and a global config whose ignore and
  attributes files are empty, whatever ~/.config/git holds.
- git discovery stops at pytest's base temp folder: a repository a test
  creates is still found, and a plain folder stays outside any repository,
  checked in a child pytest whose base temp folder sits inside one.
- The scrub list covers `git rev-parse --local-env-vars` of the git on PATH
  and every GIT_LOCATION_VARS copy under src/, and the copies stay identical.
- The hook's `unset` line runs under `sh -e`, as husky runs the hook, and
  clears what git exports. CI never runs the hook itself, so this is what
  checks the line with Git for Windows' sh.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
THIS_FILE = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
CONFTEST_PATH = REPO_ROOT / "test" / "conftest.py"
HOOK_PATH = REPO_ROOT / ".husky" / "pre-commit"
HELPER_COPIES = {
    "src/shared/scripts/skf-check-workspace-drift.py",
    "src/shared/scripts/skf-merge-ccc-exclusions.py",
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


conftest = _load("skf_test_conftest", CONFTEST_PATH)


def _run(argv: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        **kwargs,
    )


def _location_var_copies() -> dict[str, tuple[str, ...]]:
    """Every top-level `GIT_LOCATION_VARS = (...)` under src/, by path."""
    copies = {}
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "GIT_LOCATION_VARS"
                for target in node.targets
            ):
                copies[path.relative_to(REPO_ROOT).as_posix()] = ast.literal_eval(node.value)
    return copies


def test_git_environment_is_hermetic() -> None:
    """Holds in every run; test_conftest_scrubs_a_hook_environment gives it teeth."""
    scrubbed = (*conftest.SCRUBBED_GIT_VARS, *conftest.SCRUBBED_IDENTITY_VARS)
    assert [var for var in scrubbed if var in os.environ] == []
    assert os.environ.get("GIT_CONFIG_NOSYSTEM") == "1"
    assert Path(os.environ["GIT_CONFIG_GLOBAL"]).is_file()


def test_git_ignores_developer_ignore_and_attributes(tmp_path: Path) -> None:
    """The global config only empties git's global ignore and attributes files."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available")
    listing = _run([git, "config", "--global", "--list"], tmp_path, check=True)
    keys = sorted(line.split("=", 1)[0] for line in listing.stdout.splitlines())
    assert keys == ["core.attributesfile", "core.excludesfile"], listing.stdout
    for key in ("core.excludesFile", "core.attributesFile"):
        value = _run([git, "config", "--global", "--get", key], tmp_path, check=True)
        empty = Path(value.stdout.strip())
        assert empty.is_file(), value.stdout
        assert empty.read_bytes() == b""

    repo = tmp_path / "repo"
    _run([git, "init", "-q", str(repo)], tmp_path, check=True)
    (repo / "probe.txt").write_bytes(b"probe\n")
    ignored = _run([git, "check-ignore", "-q", "probe.txt"], repo)
    assert ignored.returncode == 1, ignored.stdout + ignored.stderr
    attributes = _run([git, "check-attr", "-a", "probe.txt"], repo, check=True)
    assert attributes.stdout == ""


def test_conftest_scrubs_a_hook_environment(tmp_path: Path) -> None:
    """A child pytest started with a hook's environment still runs hermetic."""
    leaked = {var: str(tmp_path / "leaked" / var.lower()) for var in conftest.SCRUBBED_GIT_VARS}
    leaked["GIT_CONFIG_PARAMETERS"] = "'commit.gpgsign'='true'"
    leaked["GIT_CONFIG_COUNT"] = "1"
    leaked.update(
        GIT_AUTHOR_NAME="Hook Author",
        GIT_AUTHOR_EMAIL="hook@example.org",
        GIT_AUTHOR_DATE="@1700000000 +0000",
        GIT_COMMITTER_NAME="Hook Committer",
        GIT_COMMITTER_EMAIL="hook@example.org",
        GIT_COMMITTER_DATE="@1700000000 +0000",
    )
    assert set(conftest.SCRUBBED_IDENTITY_VARS) <= set(leaked)
    # A developer's global config and default ignore and attributes files
    # that would ignore and tag every fixture file.
    catch_all = tmp_path / "catch-all"
    catch_all.write_bytes(b"*\n")
    developer_config = tmp_path / "developer-gitconfig"
    developer_config.write_bytes(
        (
            "[commit]\n\tgpgsign = true\n"
            f"[core]\n\texcludesFile = {conftest._config_path(catch_all)}\n"
        ).encode("utf-8")
    )
    xdg = tmp_path / "xdg"
    (xdg / "git").mkdir(parents=True)
    (xdg / "git" / "ignore").write_bytes(b"*\n")
    (xdg / "git" / "attributes").write_bytes(b"* skf-probe\n")
    env = {
        **os.environ,
        **leaked,
        "GIT_CONFIG_GLOBAL": str(developer_config),
        "XDG_CONFIG_HOME": str(xdg),
    }
    env.pop("GIT_CONFIG_NOSYSTEM", None)
    proc = _run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            f"{THIS_FILE}::test_git_environment_is_hermetic",
            f"{THIS_FILE}::test_git_ignores_developer_ignore_and_attributes",
        ],
        REPO_ROOT,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    expected = "2 passed" if shutil.which("git") else "1 passed, 1 skipped"
    assert expected in proc.stdout, proc.stdout


def test_git_discovery_stops_at_the_base_temp_folder(tmp_path: Path, tmp_path_factory) -> None:
    """Holds in every run; test_ceiling_holds_inside_an_enclosing_repository gives it teeth."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available")
    for plain in (tmp_path, tmp_path / "plain"):
        plain.mkdir(exist_ok=True)
        found = _run([git, "-C", str(plain), "rev-parse", "--git-dir"], tmp_path)
        assert found.returncode != 0, f"{plain} resolved to {found.stdout.strip()}"
    # A repository directly below the base temp folder, the shallowest a
    # tmp_path can be, is still found from inside it.
    repo = tmp_path_factory.mktemp("repo")
    _run([git, "init", "-q", str(repo)], tmp_path, check=True)
    (repo / "sub").mkdir()
    top = _run([git, "-C", str(repo / "sub"), "rev-parse", "--show-toplevel"], tmp_path, check=True)
    assert Path(top.stdout.strip()).resolve() == repo.resolve()


def test_ceiling_holds_inside_an_enclosing_repository(tmp_path: Path) -> None:
    """A child pytest whose base temp folder sits inside a git work tree, as
    with a home folder under git or a TMPDIR inside a checkout."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available")
    enclosing = tmp_path / "enclosing"
    _run([git, "init", "-q", str(enclosing)], tmp_path, check=True)
    _run(
        [git, "-C", str(enclosing), "-c", "user.name=SKF Test", "-c", "user.email=skf@example.org",
         "commit", "-q", "--allow-empty", "-m", "enclosing"],
        tmp_path,
        check=True,
    )
    env = dict(os.environ)
    env.pop("GIT_CEILING_DIRECTORIES", None)
    drift = "test/test-skf-check-workspace-drift.py"
    proc = _run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            f"--basetemp={enclosing / 'basetemp'}",
            f"{THIS_FILE}::test_git_discovery_stops_at_the_base_temp_folder",
            f"{drift}::TestSkipped::test_not_a_git_tree_skips",
            f"{drift}::TestCli::test_skipped_not_git_exits_0",
            f"{drift}::TestInheritedGitEnv::test_non_git_folder_still_skips",
        ],
        REPO_ROOT,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "4 passed" in proc.stdout, proc.stdout


def test_scrub_list_covers_git_local_env_vars(tmp_path: Path) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available")
    proc = _run([git, "rev-parse", "--local-env-vars"], tmp_path, check=True)
    local_vars = set(proc.stdout.split())
    assert "GIT_INDEX_FILE" in local_vars, proc.stdout
    missing = sorted(local_vars - set(conftest.SCRUBBED_GIT_VARS))
    assert not missing, (
        f"git on PATH lists {', '.join(missing)} in `git rev-parse --local-env-vars`; "
        "add them to SCRUBBED_GIT_VARS in test/conftest.py"
    )


def test_git_location_var_copies_are_identical_and_scrubbed() -> None:
    copies = _location_var_copies()
    assert HELPER_COPIES <= set(copies), sorted(copies)
    assert len(set(copies.values())) == 1, copies
    unscrubbed = sorted(set(next(iter(copies.values()))) - set(conftest.SCRUBBED_GIT_VARS))
    assert not unscrubbed, (
        f"add {', '.join(unscrubbed)} to SCRUBBED_GIT_VARS in test/conftest.py"
    )


def _hook_unset_line() -> str:
    """The hook's `unset` command, checked to sit between lint-staged and npm test."""
    commands = [
        line.strip()
        for line in HOOK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    unset = [command for command in commands if command.startswith("unset ")]
    assert len(unset) == 1, commands
    assert "$(git rev-parse --local-env-vars)" in unset[0], unset[0]
    position = commands.index(unset[0])
    assert any("lint-staged" in command for command in commands[:position]), commands
    assert "npm test" in commands[position + 1 :], commands
    return unset[0]


def _posix_sh(git: str) -> str | None:
    """sh on PATH, else the one Git for Windows ships beside git."""
    found = shutil.which("sh")
    if found:
        return found
    proc = subprocess.run(
        [git, "--exec-path"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    exec_path = proc.stdout.strip()
    if not exec_path:
        return None
    for base in list(Path(exec_path).parents)[:3]:
        for candidate in (base / "bin" / "sh.exe", base / "usr" / "bin" / "sh.exe"):
            if candidate.is_file():
                return str(candidate)
    return None


def test_pre_commit_hook_clears_the_location_vars(tmp_path: Path) -> None:
    line = _hook_unset_line()
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not available")
    sh = _posix_sh(git)
    if sh is None:
        pytest.skip("no POSIX sh found")
    repo = tmp_path / "repo"
    _run([git, "init", "-q", str(repo)], tmp_path, check=True)
    # What a hook in a linked worktree receives, plus a `git -c` setting.
    exported = {
        "GIT_DIR": str(repo / ".git"),
        "GIT_WORK_TREE": str(repo),
        "GIT_INDEX_FILE": str(repo / ".git" / "index"),
        "GIT_PREFIX": "sub/",
        "GIT_CONFIG_PARAMETERS": "'commit.gpgsign'='true'",
        "GIT_NAMESPACE": "leaked",
    }
    script = tmp_path / "pre-commit"
    script.write_bytes(f"{line}\nenv\n".encode("utf-8"))
    proc = _run(
        [sh, "-e", str(script)],
        repo,
        env={**os.environ, **exported, "SKF_HOOK_PROBE": "kept"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = {entry.split("=", 1)[0] for entry in proc.stdout.splitlines()}
    assert "SKF_HOOK_PROBE" in names, proc.stdout
    assert sorted(names & set(exported)) == []
