#!/usr/bin/env python3
"""Tests for skf-merge-ccc-exclusions.py.

Highest-value tests:
- Config-value validation refuses every input that would produce a
  malformed or over-broad ccc pattern (empty, absolute, `..`, `!`, glob
  meta, placeholders, single quotes), and values are normalized first.
- Folder patterns are anchored to the project root (`skills`, never
  `**/skills`), and a folder that already holds files SKF did not generate
  is left out (real git, cleaned environment).
- settings.yml states: a missing file is created only by `ccc init`, a file
  lacking the ccc defaults is rebuilt with user entries kept, a failed
  rebuild restores the original bytes, and a leftover backup is recovered.
- Pruning follows the forge-tier.yaml ownership record, never touches
  entries SKF did not add, and is blocked while a folder value is refused;
  the legacy `**/<value>` migration needs a folder-free forge-tier.yaml.
- The collision classifier: one fixture per rule, nested repositories and
  submodules, malformed metadata; git failures warn, non-git is silent.
- The index decision, the .gitignore check, and the no-single-quote
  guarantee for every human-readable string.
- Prose pins on the setup step files that consume the helper output.

No test runs a real `ccc`: subprocess CLI tests always pass --no-ccc-init,
and in-process tests replace `run_ccc_init` with fakes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-merge-ccc-exclusions.py"
CCC_INDEX_STEP = REPO_ROOT / "src" / "skf-setup" / "references" / "ccc-index.md"
REPORT_STEP = REPO_ROOT / "src" / "skf-setup" / "references" / "report.md"

spec = importlib.util.spec_from_file_location("skf_merge_ccc_exclusions", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# The 9 exclude_patterns `ccc init` writes (cocoindex-code 0.2.41).
CCC_DEFAULTS = [
    "**/.*",
    "**/__pycache__",
    "**/node_modules",
    "**/target",
    "**/build/assets",
    "**/dist",
    "**/vendor/*.*/*",
    "**/vendor/*",
    "**/.cocoindex_code",
]
CCC_INCLUDES = ["**/*.py", "**/*.md"]
LEGACY_SKF = list(mod.ALWAYS_INCLUDE) + ["**/skills", "**/_bmad-output/forge-data"]
# What v1 recorded in forge-tier.yaml ccc_index.exclude_patterns: its
# effective_patterns, sorted(set(...)) of the `**/` patterns it merged.
V1_RECORD = sorted(set(LEGACY_SKF))
ANCHORED_SKF = list(mod.ALWAYS_INCLUDE) + ["skills", "_bmad-output/forge-data"]
GITIGNORE_LINES = b"# CocoIndex Code (ccc)\n/.cocoindex_code/\n"
V2_KEYS = {
    "status", "version", "settings_yml_path", "settings_yml_existed", "ccc_init",
    "settings_ready", "not_ready_reason", "patterns_added", "patterns_added_list",
    "patterns_removed", "patterns_removed_list", "patterns_already_present",
    "effective_patterns", "written", "gitignore_updated", "index_action", "warnings",
}


# ─── Fixtures and helpers ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_git_env(monkeypatch, tmp_path):
    """Hermetic git for every test.

    Drops inherited git location variables and stops repo discovery above
    tmp_path's parent, so a non-git fixture never finds an enclosing repo.
    git reads an empty global config and no system config, so a developer's
    safe.directory, init.defaultBranch, hooks path, excludes or signing
    settings never change what a test sees. Commits pass their identity
    with -c (see _git_commit).
    """
    for var in mod.GIT_LOCATION_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    empty_config = tmp_path / "empty-gitconfig"
    empty_config.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # An empty XDG config dir also hides git's default ignore file
    # ($XDG_CONFIG_HOME/git/ignore, else ~/.config/git/ignore).
    empty_xdg = tmp_path / "empty-xdg-config"
    empty_xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(empty_xdg))


@pytest.fixture
def tmp_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    return project


def _settings_path(project: Path) -> Path:
    return project / ".cocoindex_code" / "settings.yml"


def _backup_path(project: Path) -> Path:
    return project / ".cocoindex_code" / "settings.yml.skf-repair"


def _read_settings(project: Path) -> dict:
    path = _settings_path(project)
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_yaml(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(yaml.safe_dump(data, default_flow_style=False, sort_keys=False).encode("utf-8"))
    return path


def _seed_ccc_settings(project: Path, extra_excludes=(), extra_keys=None) -> Path:
    """Write a ccc-shaped settings.yml: the ccc defaults plus extras, and include_patterns."""
    data = {
        "exclude_patterns": CCC_DEFAULTS + list(extra_excludes),
        "include_patterns": list(CCC_INCLUDES),
    }
    data.update(extra_keys or {})
    return _write_yaml(_settings_path(project), data)


def _seed_bare_settings(project: Path, excludes, extra_keys=None) -> Path:
    """Write a settings.yml SKF created before ccc init (no ccc defaults)."""
    data = {"exclude_patterns": list(excludes)}
    data.update(extra_keys or {})
    return _write_yaml(_settings_path(project), data)


def _record(tmp: Path, patterns) -> Path:
    """Write a forge-tier.yaml holding ccc_index.exclude_patterns."""
    return _write_yaml(
        tmp / "forge-tier.yaml",
        {"tier": "Deep", "ccc_index": {"status": "fresh", "exclude_patterns": list(patterns)}},
    )


def _run(project: Path, skills="skills", forge_data="_bmad-output/forge-data", prior=None,
         index_fresh="false", skip_index="false", extra_args=()) -> tuple[int, dict, str]:
    """Run the CLI as a subprocess — always with --no-ccc-init."""
    argv = [sys.executable, str(SCRIPT_PATH),
            "--project-root", str(project),
            "--skills-output-folder", skills,
            "--forge-data-folder", forge_data,
            "--index-fresh", index_fresh,
            "--skip-index", skip_index,
            "--no-ccc-init", *extra_args]
    if prior is not None:
        argv += ["--prior-state-from", str(prior)]
    env = {k: v for k, v in os.environ.items() if k not in mod.GIT_LOCATION_VARS}
    result = subprocess.run(argv, capture_output=True, timeout=60, env=env)
    stdout = result.stdout.decode("utf-8")
    payload = json.loads(stdout) if stdout.strip() else None
    return result.returncode, payload, result.stderr.decode("utf-8", errors="replace")


def _merge(project: Path, skills="skills", forge_data="_bmad-output/forge-data", prior=None,
           index_fresh=False, skip_index=False, allow_ccc_init=False) -> dict:
    """In-process run_merge; ccc init only runs when a fake is installed."""
    return mod.run_merge(project, skills, forge_data, prior_state_from=prior,
                         index_fresh=index_fresh, skip_index=skip_index,
                         allow_ccc_init=allow_ccc_init)


def _warnings_with(payload: dict, needle: str) -> list[str]:
    return [w for w in payload["warnings"] if needle in w]


class _FakeInit:
    """Stand-in for run_ccc_init that mimics `ccc init -f`."""

    def __init__(self, body=None, ok=True, output="Created project settings"):
        self.calls: list[Path] = []
        self.body = body
        self.ok = ok
        self.output = output

    def __call__(self, root):
        root = Path(root)
        self.calls.append(root)
        target = _settings_path(root)
        if target.is_file():
            return True, "Project already initialized."
        if self.body is None:
            data = {"exclude_patterns": list(CCC_DEFAULTS), "include_patterns": list(CCC_INCLUDES)}
        else:
            data = self.body
        _write_yaml(target, data)
        if (root / ".git").is_dir():
            gitignore = root / ".gitignore"
            current = gitignore.read_bytes() if gitignore.is_file() else b""
            if b"/.cocoindex_code/" not in current:
                if current and not current.endswith(b"\n"):
                    current += b"\n"
                gitignore.write_bytes(current + GITIGNORE_LINES)
        return self.ok, self.output


@pytest.fixture
def fake_init(monkeypatch):
    fake = _FakeInit()
    monkeypatch.setattr(mod, "run_ccc_init", fake)
    return fake


@pytest.fixture
def failing_init(monkeypatch):
    calls: list[Path] = []

    def _failing(root):
        calls.append(Path(root))
        return False, "Error: it's broken"

    _failing.calls = calls
    monkeypatch.setattr(mod, "run_ccc_init", _failing)
    return _failing


def _git(cwd: Path, *args: str) -> str:
    """Run git in cwd with the git location variables stripped; skip without git."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    env = {k: v for k, v in os.environ.items() if k not in mod.GIT_LOCATION_VARS}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        env=env,
        check=True,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def _write_files(root: Path, files: dict[str, bytes]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _git_repo(root: Path, files: dict[str, bytes] | None = None, add: bool = True) -> Path:
    """`git init` root, write files, and optionally stage them (no commit)."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    files = files or {}
    _write_files(root, files)
    if add and files:
        _git(root, "--literal-pathspecs", "add", "--", *files.keys())
    return root


def _git_commit(root: Path, message: str = "fixture") -> None:
    """Commit what is staged in root; the identity is passed with -c (no global config)."""
    _git(root, "-c", "user.name=SKF Test", "-c", "user.email=skf-test@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-q", "-m", message)


MODULE_SOURCE = {
    "skills/module.yaml": b"code: my-module\n",
    "skills/my-agent/SKILL.md": b"# My agent\n",
    "skills/my-agent/references/a.md": b"# Reference\n",
}


# ─── validate_config_value ──────────────────────────────────────────────────


@pytest.mark.parametrize("value,is_valid", [
    # Valid — relative paths with no glob meta
    ("skills",                       True),
    ("_bmad-output/forge-data",      True),
    ("nested/path/value",            True),
    ("path-with.dots_and-dashes",    True),
    # Invalid — empty / whitespace / current directory
    ("",                             False),
    ("   ",                          False),
    ("\t",                           False),
    (".",                            False),
    # Invalid — absolute / anchored
    ("/abs/path",                    False),
    ("~/home",                       False),
    ("./rel",                        False),
    ("skills/",                      False),
    ("C:/proj/skills",               False),
    # Invalid — outside the project
    ("../skills",                    False),
    ("a/../b",                       False),
    # Invalid — negation
    ("!skills",                      False),
    # Invalid — glob meta
    ("path/*",                       False),
    ("?ile",                         False),
    ("dir[abc]",                     False),
    ("dir]",                         False),
    ("out\\skills",                  False),
    ("**/wildcard",                  False),
    # Invalid — unresolved {project-root}-style template placeholders
    ("{project-root}/skills",        False),
    ("{project-root}/forge-data",    False),
    ("prefix/{var}/suffix",          False),
    ("trailing}",                    False),
    ("{leading",                     False),
    # Invalid — single quote breaks the setup payloads
    ("bob's",                        False),
])
def test_validate_config_value(value, is_valid):
    cleaned, warning = mod.validate_config_value("skills_output_folder", value)
    if is_valid:
        assert cleaned is not None
        assert warning is None
    else:
        assert cleaned is None
        assert warning is not None
        assert "skills_output_folder" in warning  # Warning names the offending key


def test_validate_warning_messages_are_actionable():
    """Each rejection reason should name (a) the key, (b) the failure mode, (c) where to fix it."""
    _, w = mod.validate_config_value("skills_output_folder", "")
    assert "skills_output_folder" in w
    assert "empty" in w.lower() or "whitespace" in w.lower()
    assert "_bmad/skf/config.yaml" in w  # config file location

    _, w = mod.validate_config_value("forge_data_folder", "/abs")
    assert "forge_data_folder" in w
    assert "absolute" in w.lower() or "anchored" in w.lower()

    _, w = mod.validate_config_value("forge_data_folder", "x*")
    assert "glob meta" in w.lower()

    # Validator backstops a placeholder leak — the merge entry point resolves
    # {project-root}/... before validation, so this path only fires when
    # validate_config_value is invoked directly or with a stray brace.
    _, w = mod.validate_config_value("skills_output_folder", "{stray}/skills")
    assert "skills_output_folder" in w
    assert "placeholder" in w.lower()

    _, w = mod.validate_config_value("skills_output_folder", "!x")
    assert "negation" in w

    _, w = mod.validate_config_value("skills_output_folder", "../x")
    assert ".." in w

    for value in ("", "/abs", "x*", "{stray}", "!x", "../x", "bob's", "a]", "C:/x"):
        _, w = mod.validate_config_value("skills_output_folder", value)
        assert w is not None
        assert "'" not in w, f"single quote in warning for {value!r}: {w}"


@pytest.mark.parametrize("raw,expected", [
    ("skills/",                  "skills"),
    ("./skills",                 "skills"),
    ("out\\skills",              "out/skills"),
    ("a//b",                     "a/b"),
    ("a/./b",                    "a/b"),
    ("{project-root}/skills",    "skills"),
    ("{project-root}\\skills",   "skills"),
    ("{project-root}",           ""),
    ("  skills  ",               "skills"),
    ("/abs",                     "/abs"),
    ("../x",                     "../x"),
])
def test_resolve_repo_relative_normalizes(raw, expected):
    assert mod.resolve_repo_relative(raw, Path("/unused")) == expected


def test_validate_strips_surrounding_whitespace():
    """A value like '  skills  ' should be treated as 'skills', not rejected."""
    cleaned, warning = mod.validate_config_value("skills_output_folder", "  skills  ")
    assert cleaned == "skills"
    assert warning is None


# ─── assemble_patterns ─────────────────────────────────────────────────────


def test_assemble_patterns_always_includes_four_hardcoded():
    patterns, warnings = mod.assemble_patterns("skills", "_bmad-output/forge-data")
    assert "**/_bmad" in patterns
    assert "**/_bmad-output" in patterns
    assert "**/.claude" in patterns
    assert "**/_skf-learn" in patterns
    assert "skills" in patterns
    assert "_bmad-output/forge-data" in patterns
    assert "**/skills" not in patterns
    assert warnings == []


def test_assemble_patterns_skips_rejected_config_values():
    """Config-value rejection MUST NOT disable the 4 always-include patterns."""
    patterns, warnings = mod.assemble_patterns("", "/abs/path")
    # Always-include patterns survive
    for p in mod.ALWAYS_INCLUDE:
        assert p in patterns
    # Bad values DON'T appear as malformed globs
    assert "**/" not in patterns
    assert "**//abs/path" not in patterns
    # Both produce warnings
    assert len(warnings) == 2


def test_assemble_patterns_empty_skills_keeps_forge_data():
    """One bad value doesn't poison the other."""
    patterns, warnings = mod.assemble_patterns("", "_bmad-output/forge-data")
    assert "_bmad-output/forge-data" in patterns
    assert "**/_bmad-output/forge-data" not in patterns
    assert "**/" not in patterns
    assert len(warnings) == 1
    assert "skills_output_folder" in warnings[0]


def test_assemble_patterns_dedupes_equal_folders():
    patterns, warnings = mod.assemble_patterns("out", "out")
    assert patterns.count("out") == 1
    assert warnings == []


# ─── plan_exclusions ────────────────────────────────────────────────────────


def test_plan_exclusions_appends_new():
    result = mod.plan_exclusions(["**/node_modules"], ["**/_bmad", "**/_bmad-output"], set(), True)
    assert result == (
        ["**/node_modules", "**/_bmad", "**/_bmad-output"],
        ["**/_bmad", "**/_bmad-output"],
        [],
    )


def test_plan_exclusions_skips_already_present():
    result = mod.plan_exclusions(
        ["**/node_modules", "**/_bmad"],
        ["**/_bmad", "**/_bmad-output"],
        set(), True,
    )
    assert result == (["**/node_modules", "**/_bmad", "**/_bmad-output"], ["**/_bmad-output"], [])


def test_plan_exclusions_preserves_existing_order():
    result = mod.plan_exclusions(["**/dist", "**/build", "**/node_modules"], ["skills"], set(), True)
    # Existing order preserved, new entry appended
    assert result == (["**/dist", "**/build", "**/node_modules", "skills"], ["skills"], [])


def test_plan_exclusions_idempotent_on_full_overlap():
    """Re-running with all-already-present yields no changes."""
    existing = list(mod.ALWAYS_INCLUDE) + ["skills"]
    produced = list(mod.ALWAYS_INCLUDE) + ["skills"]
    assert mod.plan_exclusions(existing, produced, set(), True) == (existing, [], [])


def test_plan_exclusions_prunes_recorded_pattern_no_longer_produced():
    existing = CCC_DEFAULTS + list(mod.ALWAYS_INCLUDE) + ["skills"]
    produced = list(mod.ALWAYS_INCLUDE) + ["skf-skills"]
    owned = set(mod.ALWAYS_INCLUDE) | {"skills"}
    merged, added, removed = mod.plan_exclusions(existing, produced, owned, True)
    assert removed == ["skills"]
    assert added == ["skf-skills"]
    assert merged == CCC_DEFAULTS + list(mod.ALWAYS_INCLUDE) + ["skf-skills"]


def test_plan_exclusions_never_touches_unowned_entries():
    existing = CCC_DEFAULTS + ["**/my-extra", "skills"]
    owned = {"skills", "old-forge"}
    merged, _added, removed = mod.plan_exclusions(existing, list(mod.ALWAYS_INCLUDE), owned, True)
    assert removed == ["skills"]
    assert "**/my-extra" in merged
    for default in CCC_DEFAULTS:
        assert default in merged


def test_plan_exclusions_never_prunes_always_include():
    existing = list(mod.ALWAYS_INCLUDE)
    owned = set(mod.ALWAYS_INCLUDE)
    merged, added, removed = mod.plan_exclusions(existing, list(mod.ALWAYS_INCLUDE), owned, True)
    assert removed == []
    assert added == []
    assert merged == existing


def test_plan_exclusions_prune_blocked_removes_nothing():
    existing = CCC_DEFAULTS + ["skills"]
    merged, _added, removed = mod.plan_exclusions(existing, list(mod.ALWAYS_INCLUDE), {"skills"}, False)
    assert removed == []
    assert "skills" in merged


# ─── Ownership record ───────────────────────────────────────────────────────


def test_read_owned_record_list(tmp_path):
    path = _record(tmp_path, ["skills", "**/_bmad"])
    warnings: list[str] = []
    assert mod.read_owned_record(path, warnings) == ["skills", "**/_bmad"]
    assert warnings == []


def test_read_owned_record_missing_file_is_empty(tmp_path):
    warnings: list[str] = []
    assert mod.read_owned_record(tmp_path / "absent.yaml", warnings) == []
    assert mod.read_owned_record(None, warnings) == []
    assert warnings == []


def test_read_owned_record_malformed_yaml_warns_and_is_empty(tmp_path):
    path = tmp_path / "forge-tier.yaml"
    path.write_bytes(b"ccc_index: [unclosed\n")
    warnings: list[str] = []
    assert mod.read_owned_record(path, warnings) == []
    assert len(warnings) == 1
    assert "forge-tier.yaml" in warnings[0]


def test_read_owned_record_non_list_is_empty(tmp_path):
    path = _write_yaml(tmp_path / "forge-tier.yaml", {"ccc_index": {"exclude_patterns": "skills"}})
    warnings: list[str] = []
    assert mod.read_owned_record(path, warnings) == []
    assert warnings == []


def test_legacy_double_star_pruned_only_when_record_empty(tmp_path, tmp_project):
    # Non-empty anchored record: a `**/skills` the user added later survives.
    _seed_ccc_settings(tmp_project, extra_excludes=["**/skills"])
    prior = _record(tmp_path, ANCHORED_SKF)
    payload = _merge(tmp_project, prior=prior)
    assert payload["patterns_removed_list"] == []
    assert "**/skills" in _read_settings(tmp_project)["exclude_patterns"]

    # Empty record: the legacy `**/{value}` form counts as owned and migrates.
    _seed_ccc_settings(tmp_project, extra_excludes=["**/skills"])
    empty = _record(tmp_path, [])
    payload = _merge(tmp_project, prior=empty)
    assert payload["patterns_removed_list"] == ["**/skills"]
    excludes = _read_settings(tmp_project)["exclude_patterns"]
    assert "**/skills" not in excludes
    assert "skills" in excludes


def test_no_forge_tier_file_owns_nothing(tmp_path, tmp_project):
    """Without forge-tier.yaml SKF never finished a setup here: a user `**/skills` stays."""
    for prior in (None, tmp_path / "absent" / "forge-tier.yaml"):
        _seed_ccc_settings(tmp_project, extra_excludes=["**/skills"])
        payload = _merge(tmp_project, prior=prior)
        assert payload["patterns_removed_list"] == [], prior
        assert payload["patterns_removed"] == 0
        excludes = _read_settings(tmp_project)["exclude_patterns"]
        assert "**/skills" in excludes
        assert "skills" in excludes


@pytest.mark.parametrize("record", [[], list(mod.ALWAYS_INCLUDE)],
                         ids=["empty-record", "always-include-only"])
def test_folder_free_record_migrates_legacy_double_star(tmp_path, tmp_project, record):
    _seed_ccc_settings(tmp_project, extra_excludes=["**/skills"])
    payload = _merge(tmp_project, prior=_record(tmp_path, record))
    assert payload["patterns_removed_list"] == ["**/skills"]
    excludes = _read_settings(tmp_project)["exclude_patterns"]
    assert "**/skills" not in excludes
    assert "skills" in excludes


# ─── settings.yml states (in process, fake ccc init) ───────────────────────


def test_missing_settings_runs_ccc_init_then_merges(tmp_path, fake_init):
    project = _git_repo(tmp_path / "repo")
    payload = _merge(project, allow_ccc_init=True)
    assert payload["ccc_init"] == "created"
    assert payload["settings_yml_existed"] is False
    assert payload["settings_ready"] is True
    assert payload["written"] is True
    assert payload["index_action"] == "index"
    assert payload["gitignore_updated"] is True
    assert fake_init.calls == [project]
    settings = _read_settings(project)
    for default in CCC_DEFAULTS:
        assert default in settings["exclude_patterns"]
    for pattern in ANCHORED_SKF:
        assert pattern in settings["exclude_patterns"]
    assert settings["include_patterns"] == CCC_INCLUDES
    assert payload["patterns_added"] == 6
    assert payload["effective_patterns"] == sorted(ANCHORED_SKF)


def test_run_ccc_init_uses_force_devnull_scrubbed_env(monkeypatch, tmp_path):
    captured: dict = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout=b"Created project settings\n", stderr=b"")

    monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda command: "/fake/ccc")
    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "other" / ".git" / "index"))

    ok, output = mod.run_ccc_init(tmp_path)
    assert ok is True
    assert output == "Created project settings"
    assert captured["argv"] == ["/fake/ccc", "init", "-f"]
    assert captured["cwd"] == str(tmp_path)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["timeout"] == mod.CCC_INIT_TIMEOUT_SEC
    assert "GIT_INDEX_FILE" not in captured["env"]
    assert captured["env"]["PYTHONUTF8"] == "1"


def test_ccc_init_failure_creates_nothing_and_fails(tmp_project, failing_init):
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert not _settings_path(tmp_project).exists()
    assert payload["settings_ready"] is False
    assert payload["ccc_init"] == "failed"
    assert payload["index_action"] == "fail"
    assert payload["effective_patterns"] is None
    assert payload["written"] is False
    assert payload["not_ready_reason"].startswith("ccc init did not create")
    assert "'" not in payload["not_ready_reason"]


def test_ccc_not_on_path_reports_not_ready(monkeypatch, tmp_project):
    monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda command: None)
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert payload["settings_ready"] is False
    assert payload["index_action"] == "fail"
    assert "not found on PATH" in payload["not_ready_reason"]


def test_bare_skf_settings_rebuilt_on_ccc_defaults(tmp_path, tmp_project, fake_init):
    # A #490-damaged install: v1 wrote the bare file and recorded its patterns.
    _seed_bare_settings(tmp_project, LEGACY_SKF + ["**/my-extra"], extra_keys={"foo": "bar"})
    prior = _record(tmp_path, V1_RECORD)
    payload = _merge(tmp_project, prior=prior, allow_ccc_init=True)
    assert payload["ccc_init"] == "rebuilt"
    assert sorted(payload["patterns_removed_list"]) == ["**/_bmad-output/forge-data", "**/skills"]
    assert payload["written"] is True
    assert payload["settings_yml_existed"] is True
    settings = _read_settings(tmp_project)
    excludes = settings["exclude_patterns"]
    for default in CCC_DEFAULTS:
        assert default in excludes
    assert settings["include_patterns"] == CCC_INCLUDES
    assert "**/my-extra" in excludes
    assert settings["foo"] == "bar"
    assert "skills" in excludes
    assert "_bmad-output/forge-data" in excludes
    assert "**/skills" not in excludes
    assert "**/_bmad-output/forge-data" not in excludes
    assert not _backup_path(tmp_project).exists()
    assert len(_warnings_with(payload, "rebuilt")) == 1


def test_absent_exclude_key_rebuilt_preserving_user_keys(tmp_project, fake_init):
    user_includes = ["src/**/*.rs", "docs/**/*.md"]
    _write_yaml(_settings_path(tmp_project), {"include_patterns": user_includes})
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert payload["ccc_init"] == "rebuilt"
    settings = _read_settings(tmp_project)
    assert settings["include_patterns"] == user_includes
    for pattern in CCC_DEFAULTS + ANCHORED_SKF:
        assert pattern in settings["exclude_patterns"]


def test_empty_settings_file_rebuilt(tmp_project, fake_init):
    target = _settings_path(tmp_project)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert payload["ccc_init"] == "rebuilt"
    settings = _read_settings(tmp_project)
    for pattern in CCC_DEFAULTS + ANCHORED_SKF:
        assert pattern in settings["exclude_patterns"]
    assert settings["include_patterns"] == CCC_INCLUDES


def test_rebuild_failure_restores_original_bytes(tmp_project, failing_init):
    # Non-canonical bytes (a comment, a flow-style list): a re-dump of the
    # parsed data would differ, so only a byte-for-byte restore passes.
    target = _settings_path(tmp_project)
    target.parent.mkdir(parents=True)
    target.write_bytes(
        b"# written by SKF before ccc init ran\n"
        b"exclude_patterns: ['**/_bmad', '**/_bmad-output', '**/.claude', '**/_skf-learn',"
        b" '**/skills',   '**/_bmad-output/forge-data']\n"
    )
    before = target.read_bytes()
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert target.read_bytes() == before
    assert payload["ccc_init"] == "failed"
    assert payload["written"] is False
    assert payload["effective_patterns"] is None
    assert payload["settings_ready"] is True
    assert len(_warnings_with(payload, "could not rebuild")) == 1
    assert not _backup_path(tmp_project).exists()


def test_failed_rebuild_keeps_fresh_index_and_fails_stale_one(tmp_project, failing_init):
    """A #490-damaged file (bare, no include_patterns) whose rebuild fails:
    never build a new index from it, but keep one that is still fresh."""
    target = _seed_bare_settings(tmp_project, LEGACY_SKF)
    before = target.read_bytes()

    stale = _merge(tmp_project, index_fresh=False, allow_ccc_init=True)
    assert stale["ccc_init"] == "failed"
    assert stale["settings_ready"] is True
    assert stale["index_action"] == "fail"
    reason = stale["not_ready_reason"]
    assert reason is not None
    assert "ccc init" in reason and "rebuild" in reason
    assert "'" not in reason
    assert target.read_bytes() == before

    fresh = _merge(tmp_project, index_fresh=True, allow_ccc_init=True)
    assert fresh["ccc_init"] == "failed"
    assert fresh["settings_ready"] is True
    assert fresh["index_action"] == "keep"
    assert fresh["not_ready_reason"] is None
    assert target.read_bytes() == before


def test_rebuild_without_exclude_list_restores_original(tmp_project, fake_init):
    """ccc init writing a file with no exclude_patterns is a failed rebuild."""
    fake_init.body = {"include_patterns": list(CCC_INCLUDES)}
    target = _seed_bare_settings(tmp_project, LEGACY_SKF)
    before = target.read_bytes()
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert fake_init.calls == [tmp_project]
    assert target.read_bytes() == before
    assert payload["ccc_init"] == "failed"
    assert payload["written"] is False
    assert payload["effective_patterns"] is None
    assert not _backup_path(tmp_project).exists()
    assert len(_warnings_with(payload, "could not rebuild")) == 1


def test_rebuild_writes_even_when_patterns_already_present(tmp_project, fake_init):
    """The rebuilt file must be written even with nothing to add: ccc init's
    fresh file lacks the original keys and entries until SKF writes them."""
    _seed_bare_settings(tmp_project, ANCHORED_SKF, extra_keys={"foo": "bar"})
    payload = _merge(tmp_project, index_fresh=True, allow_ccc_init=True)
    assert payload["ccc_init"] == "rebuilt"
    assert payload["written"] is True
    assert payload["index_action"] == "index"
    assert payload["patterns_added"] == 0
    settings = _read_settings(tmp_project)
    assert settings["foo"] == "bar"
    assert settings["include_patterns"] == CCC_INCLUDES
    for pattern in CCC_DEFAULTS + ANCHORED_SKF:
        assert pattern in settings["exclude_patterns"]
    assert not _backup_path(tmp_project).exists()


def test_ccc_shaped_file_is_never_rebuilt(tmp_project, fake_init):
    _seed_ccc_settings(tmp_project)
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert fake_init.calls == []
    assert payload["ccc_init"] == "not_needed"
    assert payload["written"] is True


def test_explicit_empty_exclude_list_with_include_patterns_is_respected(tmp_project, fake_init):
    _write_yaml(_settings_path(tmp_project), {"exclude_patterns": [], "include_patterns": CCC_INCLUDES})
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert fake_init.calls == []
    assert payload["ccc_init"] == "not_needed"
    excludes = _read_settings(tmp_project)["exclude_patterns"]
    assert excludes == ANCHORED_SKF
    for default in CCC_DEFAULTS:
        assert default not in excludes


def test_interrupted_repair_backup_restored_then_redone(tmp_project, fake_init):
    _seed_ccc_settings(tmp_project)  # the fresh file ccc init wrote before the crash
    _write_yaml(_backup_path(tmp_project), {"exclude_patterns": LEGACY_SKF + ["**/user-x"]})
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert len(_warnings_with(payload, "interrupted SKF repair")) == 1
    assert payload["ccc_init"] == "rebuilt"
    excludes = _read_settings(tmp_project)["exclude_patterns"]
    assert "**/user-x" in excludes
    for default in CCC_DEFAULTS:
        assert default in excludes
    assert not _backup_path(tmp_project).exists()


def test_fresh_file_without_exclude_list_left_alone(tmp_project, fake_init):
    fake_init.body = {"include_patterns": CCC_INCLUDES}
    payload = _merge(tmp_project, allow_ccc_init=True)
    assert payload["ccc_init"] == "created"
    assert payload["written"] is True  # ccc init created the file
    assert payload["effective_patterns"] is None
    assert len(_warnings_with(payload, "wrote no exclude_patterns list")) == 1
    assert "exclude_patterns" not in _read_settings(tmp_project)


# ─── End-to-end CLI (subprocess, --no-ccc-init) ─────────────────────────────


def test_cli_first_merge_into_ccc_settings(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, stderr = _run(tmp_project)
    assert rc == 0, f"stderr: {stderr}"
    assert payload["status"] == "ok"
    assert payload["settings_yml_existed"] is True
    assert payload["ccc_init"] == "not_needed"
    assert payload["written"] is True
    assert payload["patterns_added"] == 6  # 4 always + 2 config
    assert payload["warnings"] == []  # not a git repo: no collision or .gitignore check
    settings = _read_settings(tmp_project)
    excludes = settings["exclude_patterns"]
    assert excludes[:len(CCC_DEFAULTS)] == CCC_DEFAULTS
    assert settings["include_patterns"] == CCC_INCLUDES
    for p in ANCHORED_SKF:
        assert p in excludes
    assert "**/skills" not in excludes


def test_cli_re_run_is_no_op_after_first_write(tmp_project):
    _seed_ccc_settings(tmp_project)
    _run(tmp_project)
    settings_path = _settings_path(tmp_project)
    mtime_before = settings_path.stat().st_mtime_ns

    # Second run with identical inputs should be a no-op (no write, no mtime change)
    rc, payload, _ = _run(tmp_project, index_fresh="true")
    assert rc == 0
    assert payload["written"] is False
    assert payload["patterns_added"] == 0
    assert payload["patterns_already_present"] == 6
    assert payload["index_action"] == "keep"
    assert payload["effective_patterns"] == sorted(ANCHORED_SKF)
    assert settings_path.stat().st_mtime_ns == mtime_before


def test_cli_missing_settings_is_never_created(tmp_project):
    rc, payload, stderr = _run(tmp_project)
    assert rc == 0, f"stderr: {stderr}"
    assert not _settings_path(tmp_project).exists()
    assert not (tmp_project / ".cocoindex_code").exists()
    assert payload["settings_ready"] is False
    assert payload["index_action"] == "fail"
    assert payload["not_ready_reason"] == "settings.yml is missing and --no-ccc-init was given"
    assert payload["effective_patterns"] is None


def test_cli_no_ccc_init_skips_rebuild_with_warning(tmp_project):
    target = _seed_bare_settings(tmp_project, LEGACY_SKF)
    before = target.read_bytes()
    rc, payload, stderr = _run(tmp_project)
    assert rc == 0, f"stderr: {stderr}"
    assert target.read_bytes() == before
    assert payload["written"] is False
    assert payload["effective_patterns"] is None
    assert len(_warnings_with(payload, "rebuild skipped because --no-ccc-init was given")) == 1


def test_cli_existing_settings_with_user_customizations_preserved(tmp_project):
    """A pre-existing settings.yml with user excludes must keep them."""
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_bytes(
        b"exclude_patterns:\n"
        b"  - '**/node_modules'\n"
        b"  - '**/dist'\n"
        b"include_patterns:\n"
        b"  - '**/*.py'\n"
        b"other_user_setting: keep_me\n"
    )

    rc, payload, _ = _run(tmp_project)
    assert rc == 0
    assert payload["settings_yml_existed"] is True
    assert payload["written"] is True
    assert payload["patterns_added"] == 6  # All 6 SKF patterns are new

    settings = _read_settings(tmp_project)
    # User customizations preserved
    assert "**/node_modules" in settings["exclude_patterns"]
    assert "**/dist" in settings["exclude_patterns"]
    assert settings["other_user_setting"] == "keep_me"
    assert settings["include_patterns"] == ["**/*.py"]
    # Plus all SKF patterns appended
    for p in mod.ALWAYS_INCLUDE:
        assert p in settings["exclude_patterns"]


def test_cli_partial_overlap_only_adds_missing(tmp_project):
    """Some SKF patterns already present — only the missing ones are added."""
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    # User has manually added two of the four always-include patterns.
    settings_path.write_bytes(
        b"exclude_patterns:\n"
        b"  - '**/_bmad'\n"
        b"  - '**/.claude'\n"
        b"include_patterns:\n"
        b"  - '**/*.md'\n"
    )

    rc, payload, _ = _run(tmp_project)
    assert rc == 0
    assert payload["written"] is True
    # 6 SKF patterns total, 2 already present, 4 newly added
    assert payload["patterns_added"] == 4
    assert payload["patterns_already_present"] == 2
    assert "**/_bmad" not in payload["patterns_added_list"]
    assert "**/.claude" not in payload["patterns_added_list"]


# ─── Config-value incident reproductions ────────────────────────────────────


def test_cli_pr248_empty_skills_folder(tmp_project):
    """skills_output_folder='' in config — refuse, warn, but still write hardcoded patterns."""
    _seed_ccc_settings(tmp_project)
    rc, payload, _ = _run(tmp_project, skills="", forge_data="_bmad-output/forge-data")
    assert rc == 0
    settings = _read_settings(tmp_project)
    assert "**/" not in settings["exclude_patterns"]  # The would-be-malformed glob is NOT present
    assert "" not in settings["exclude_patterns"]
    # Always-include patterns still applied
    for p in mod.ALWAYS_INCLUDE:
        assert p in settings["exclude_patterns"]
    # forge_data_folder still applied (one bad value doesn't poison the other)
    assert "_bmad-output/forge-data" in settings["exclude_patterns"]
    assert "**/_bmad-output/forge-data" not in settings["exclude_patterns"]
    # Warning is surfaced
    assert any("skills_output_folder" in w for w in payload["warnings"])


def test_cli_pr248_absolute_skills_folder(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, _ = _run(tmp_project, skills="/home/u/skills", forge_data="_bmad-output/forge-data")
    assert rc == 0
    settings = _read_settings(tmp_project)
    assert "**//home/u/skills" not in settings["exclude_patterns"]
    assert "/home/u/skills" not in settings["exclude_patterns"]
    assert "_bmad-output/forge-data" in settings["exclude_patterns"]
    assert any("skills_output_folder" in w and ("absolute" in w.lower() or "anchored" in w.lower())
               for w in payload["warnings"])


def test_cli_pr248_glob_meta_in_forge_data_folder(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, _ = _run(tmp_project, skills="skills", forge_data="forge-*")
    assert rc == 0
    settings = _read_settings(tmp_project)
    assert "forge-*" not in settings["exclude_patterns"]
    assert "**/forge-*" not in settings["exclude_patterns"]
    assert "skills" in settings["exclude_patterns"]
    assert any("forge_data_folder" in w and "glob meta" in w.lower() for w in payload["warnings"])


def test_cli_resolves_project_root_prefix(tmp_project):
    """'{project-root}/...' resolves to a repo-relative, root-anchored pattern,
    so step prompts can forward raw config values."""
    _seed_ccc_settings(tmp_project)
    rc, payload, _ = _run(tmp_project, skills="{project-root}/skills",
                          forge_data="{project-root}/forge-data")
    assert rc == 0
    excludes = _read_settings(tmp_project)["exclude_patterns"]
    assert "skills" in excludes
    assert "forge-data" in excludes
    assert "**/skills" not in excludes
    assert "**/forge-data" not in excludes
    assert "{project-root}/skills" not in excludes
    for p in mod.ALWAYS_INCLUDE:
        assert p in excludes
    assert payload["warnings"] == []


def test_cli_prune_only_change_sets_written_and_index(tmp_path, tmp_project):
    _seed_ccc_settings(tmp_project, extra_excludes=list(mod.ALWAYS_INCLUDE)
                       + ["old-skills", "_bmad-output/forge-data"])
    prior = _record(tmp_path, list(mod.ALWAYS_INCLUDE) + ["old-skills", "_bmad-output/forge-data"])
    # The new skills folder is already excluded, so the only change is the prune.
    settings = _read_settings(tmp_project)
    settings["exclude_patterns"].append("skills")
    _write_yaml(_settings_path(tmp_project), settings)

    rc, payload, stderr = _run(tmp_project, prior=prior, index_fresh="true")
    assert rc == 0, f"stderr: {stderr}"
    assert payload["patterns_removed_list"] == ["old-skills"]
    assert payload["patterns_removed"] == 1
    assert payload["patterns_added"] == 0
    assert payload["written"] is True
    assert payload["index_action"] == "index"
    assert "old-skills" not in _read_settings(tmp_project)["exclude_patterns"]


def test_cli_output_has_all_documented_keys(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, _ = _run(tmp_project)
    assert rc == 0
    assert set(payload) == V2_KEYS
    assert payload["version"] == "v2"
    assert payload["index_action"] in mod.INDEX_ACTIONS


def test_cli_written_settings_have_no_crlf(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, _ = _run(tmp_project)
    assert rc == 0 and payload["written"] is True
    assert b"\r\n" not in _settings_path(tmp_project).read_bytes()


def test_non_ascii_values_written_as_ascii_and_round_trip(tmp_project):
    """ccc reads settings.yml with the platform default encoding: SKF writes
    ASCII only (non-ASCII escaped), and the values survive a reload."""
    target = _settings_path(tmp_project)
    target.parent.mkdir(parents=True)
    seed = {"exclude_patterns": CCC_DEFAULTS + ["**/données"], "include_patterns": CCC_INCLUDES}
    target.write_bytes(yaml.safe_dump(seed, default_flow_style=False, sort_keys=False,
                                      allow_unicode=True).encode("utf-8"))
    assert any(b >= 0x80 for b in target.read_bytes())  # the seed itself is raw UTF-8

    payload = _merge(tmp_project, skills="skïlls")
    assert payload["written"] is True
    assert "skïlls" in payload["effective_patterns"]
    raw = target.read_bytes()
    assert all(b < 0x80 for b in raw), raw
    loaded = yaml.safe_load(raw.decode("ascii"))
    assert "skïlls" in loaded["exclude_patterns"]
    assert "**/données" in loaded["exclude_patterns"]


# ─── Error paths ────────────────────────────────────────────────────────────


def test_cli_missing_required_arg():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--skills-output-folder", "skills"],
        capture_output=True, timeout=30,
    )
    assert result.returncode == 2
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert json.loads(stderr)["status"] == "error"
    assert "'" not in stderr


def test_cli_unexpected_error_is_json_exit_2(monkeypatch, capsys, tmp_project):
    """Any unexpected exception ends as stderr JSON with exit 2, never a traceback."""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("it's bad")

    monkeypatch.setattr(mod, "run_merge", _boom)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--project-root", str(tmp_project),
                                      "--no-ccc-init"])
    with pytest.raises(SystemExit) as excinfo:
        mod.main()
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    err = json.loads(captured.err)
    assert err["status"] == "error"
    assert "RuntimeError" in err["message"]
    assert "it`s bad" in err["message"]
    assert "'" not in err["message"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root ignores directory permission bits")
def test_cli_atomic_write_failure_exits_2_with_json(tmp_project):
    target = _seed_ccc_settings(tmp_project)  # needs the 6 SKF patterns: a write is due
    before = target.read_bytes()
    settings_dir = target.parent
    settings_dir.chmod(0o555)
    try:
        rc, payload, stderr = _run(tmp_project)
    finally:
        settings_dir.chmod(0o755)
    assert rc == 2, stderr
    assert payload is None  # nothing on stdout
    err = json.loads(stderr)
    assert err["status"] == "error"
    assert "atomic write failed" in err["message"]
    assert "'" not in stderr
    assert target.read_bytes() == before
    assert not (settings_dir / "settings.yml.skf-tmp").exists()


def test_cli_malformed_existing_settings(tmp_project):
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_bytes(b"exclude_patterns:\n\t- '**/x'\n")
    rc, _, stderr = _run(tmp_project)
    assert rc == 1
    err = json.loads(stderr)
    assert "failed to parse" in err["message"]
    assert "'" not in stderr


def test_cli_non_list_exclude_patterns_dies(tmp_project):
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_bytes(b"exclude_patterns: 42\n")
    rc, _, _ = _run(tmp_project)
    assert rc == 1


def test_cli_non_mapping_top_level_dies(tmp_project):
    settings_path = _settings_path(tmp_project)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_bytes(b"- just\n- a\n- list\n")
    rc, _, _ = _run(tmp_project)
    assert rc == 1


def test_cli_project_root_not_a_directory_exits_1(tmp_path):
    rc, payload, stderr = _run(tmp_path / "does-not-exist")
    assert rc == 1
    assert payload is None
    assert "not a directory" in json.loads(stderr)["message"]


def test_cli_rejects_non_boolean_index_flags(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, stderr = _run(tmp_project, skip_index="{ccc_skip_index}")
    assert rc == 2
    assert payload is None
    assert json.loads(stderr)["status"] == "error"
    assert "'" not in stderr
    rc, payload, stderr = _run(tmp_project, index_fresh="yes")
    assert rc == 2
    assert payload is None
    assert json.loads(stderr)["status"] == "error"
    assert "'" not in stderr
    # Case-insensitive booleans are accepted.
    rc, payload, _ = _run(tmp_project, index_fresh="TRUE", skip_index="False")
    assert rc == 0
    assert payload["index_action"] == "index"


class TestAtomicWriteBinary:
    """_atomic_write persists content verbatim — no CRLF injection on Windows."""

    def test_byte_identity_multiline(self):
        content = "exclude_patterns:\n  - one\n  - two\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "settings.yml"
            mod._atomic_write(target, content)
            assert target.read_bytes() == content.encode("utf-8")
            assert b"\r\n" not in target.read_bytes()


# ─── Index decision ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("ready,skip,written,fresh,expected", [
    (False, False, False, False, "fail"),
    (False, True,  True,  True,  "fail"),
    (False, True,  False, False, "fail"),
    (True,  True,  False, True,  "skip"),
    (True,  True,  True,  False, "skip"),
    (True,  False, True,  True,  "index"),
    (True,  False, False, False, "index"),
    (True,  False, True,  False, "index"),
    (True,  False, False, True,  "keep"),
])
def test_decide_index_action_matrix(ready, skip, written, fresh, expected):
    action = mod.decide_index_action(ready, skip, written, fresh)
    assert action == expected
    assert action in mod.INDEX_ACTIONS


def test_skip_lane_change_warns_index_not_rebuilt(tmp_project):
    _seed_ccc_settings(tmp_project)
    changed = _merge(tmp_project, skip_index=True)
    assert changed["index_action"] == "skip"
    assert changed["written"] is True
    assert len(_warnings_with(changed, "--ccc-skip-index")) == 1

    unchanged = _merge(tmp_project, skip_index=True)
    assert unchanged["index_action"] == "skip"
    assert unchanged["written"] is False
    assert _warnings_with(unchanged, "--ccc-skip-index") == []

    _seed_ccc_settings(tmp_project)
    not_skipped = _merge(tmp_project, skip_index=False)
    assert not_skipped["written"] is True
    assert _warnings_with(not_skipped, "--ccc-skip-index") == []


def test_skip_lane_warning_reports_add_and_prune_counts(tmp_path, tmp_project):
    owned = list(mod.ALWAYS_INCLUDE) + ["old-skills", "_bmad-output/forge-data"]
    _seed_ccc_settings(tmp_project, extra_excludes=owned)
    payload = _merge(tmp_project, prior=_record(tmp_path, owned), skip_index=True)
    assert payload["index_action"] == "skip"
    assert payload["patterns_added_list"] == ["skills"]
    assert payload["patterns_removed_list"] == ["old-skills"]
    [warning] = _warnings_with(payload, "--ccc-skip-index")
    assert "(+1, -1)" in warning


# ─── Collision check (real git, cleaned environment) ───────────────────────


def _collisions(payload: dict, key: str = "skills_output_folder") -> list[str]:
    return [w for w in payload["warnings"] if w.startswith(key + " ") and "SKF did not generate" in w]


def test_module_source_under_skills_refuses_exclusion(tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE)
    _seed_ccc_settings(project)
    payload = _merge(project)
    excludes = _read_settings(project)["exclude_patterns"]
    assert "skills" not in excludes
    assert "skills" not in payload["effective_patterns"]
    assert "_bmad-output/forge-data" in excludes
    assert "_bmad-output/forge-data" in payload["effective_patterns"]
    [warning] = _collisions(payload)
    assert "skills_output_folder" in warning
    assert "my-agent/" in warning
    assert "_bmad/skf/config.yaml" in warning
    assert "2 entries" in warning


def test_collision_prunes_previously_merged_double_star(tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE)
    _seed_ccc_settings(project, extra_excludes=["**/skills"])
    prior = _record(tmp_path, ["**/skills"])
    payload = _merge(project, prior=prior)
    assert payload["patterns_removed_list"] == ["**/skills"]
    excludes = _read_settings(project)["exclude_patterns"]
    assert "**/skills" not in excludes
    assert "skills" not in excludes


def test_versioned_skf_output_is_not_a_collision(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "skills/.gitkeep": b"# This file ensures the directory is tracked by git\n",
        "skills/.export-manifest.json": b'{"exports": {}}\n',
        "skills/export-skill-result-latest.json": b"{}\n",
        "skills/n/active": b"1.0.0",
        "skills/n/rename-skill-result-latest.json": b"{}\n",
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
        "skills/n/1.0.0/n/references/x.md": b"# x\n",
        "skills/_batch/quick-skill-batch-latest.json": b"{}\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]
    assert "skills" in _read_settings(project)["exclude_patterns"]


@pytest.mark.parametrize("metadata", [
    {"generated_by": "quick-skill"},
    {"tool_versions": {"skf": "0.8.0"}},
    {"skill_type": "individual", "forge_tier": "Deep"},
])
def test_flat_legacy_output_marker(tmp_path, metadata):
    project = _git_repo(tmp_path / "repo", {
        "skills/flat/SKILL.md": b"# flat\n",
        "skills/flat/metadata.json": json.dumps(metadata).encode("utf-8"),
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_flat_group_without_marker_is_a_collision(tmp_path):
    project = _git_repo(tmp_path / "repo", {"skills/flat/SKILL.md": b"# flat\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    [warning] = _collisions(payload)
    assert "flat/" in warning
    assert "skills" not in payload["effective_patterns"]


def test_manifest_export_key_counts_as_skf_owned(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "skills/.export-manifest.json": b'{"exports": {"flat": {"version": "1.0.0"}}}\n',
        "skills/flat/SKILL.md": b"# flat\n",
        "skills/flat/references/a.md": b"# a\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_root_notes_tolerated_beside_skf_output(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "skills/NOTES.md": b"# notes\n",
        "skills/scratch.py": b"print(1)\n",
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_root_files_without_skf_output_are_a_collision(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "skills/notes.md": b"# notes\n",
        "skills/module.yaml": b"code: x\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    [warning] = _collisions(payload)
    assert "module.yaml" in warning and "notes.md" in warning

    readme_only = _git_repo(tmp_path / "readme", {"skills/README.md": b"# skills\n"})
    _seed_ccc_settings(readme_only)
    payload = _merge(readme_only)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_untracked_unignored_source_counts(tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE, add=False)
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert len(_collisions(payload)) == 1
    assert "skills" not in payload["effective_patterns"]


def test_gitignored_folder_is_not_a_collision(tmp_path):
    files = dict(MODULE_SOURCE)
    files[".gitignore"] = b"skills/\n"
    project = _git_repo(tmp_path / "repo", files, add=False)
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_forge_data_skf_layout_is_owned(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "forge-data/n/skill-brief.yaml": b"name: n\n",
        "forge-data/n/1.0.0/provenance-map.json": b"{}\n",
        "forge-data/analyze-source-result-latest.json": b"{}\n",
        "forge-data/refine-architecture-result-x.json": b"{}\n",
        "forge-data/refined-architecture-x.md": b"# x\n",
        "forge-data/_campaign/state.yaml": b"a: 1\n",
        "forge-data/improvement-queue/hc-x.md": b"# hc\n",
        "forge-data/scratch.py": b"print(1)\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="forge-data")
    assert _collisions(payload, "forge_data_folder") == []
    assert "forge-data" in payload["effective_patterns"]


def test_forge_data_pointing_at_source_is_refused(tmp_path):
    project = _git_repo(tmp_path / "repo", {"src/pkg/mod.py": b"x = 1\n"})
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="src")
    [warning] = _collisions(payload, "forge_data_folder")
    assert "pkg/" in warning
    assert "src" not in payload["effective_patterns"]
    assert "src" not in _read_settings(project)["exclude_patterns"]


@pytest.mark.parametrize("generated_by", [{"tool": "quick-skill"}, ["quick-skill"]],
                         ids=["dict", "list"])
def test_unhashable_generated_by_is_foreign_not_a_crash(tmp_path, generated_by):
    project = _git_repo(tmp_path / "repo", {
        "skills/g/SKILL.md": b"# g\n",
        "skills/g/metadata.json": json.dumps({"generated_by": generated_by}).encode("utf-8"),
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    [warning] = _collisions(payload)
    assert "g/" in warning
    assert "skills" not in payload["effective_patterns"]


# One fixture per classifier rule, each matching only that rule.
SINGLE_RULE_FIXTURES = {
    "forge-root-report-prefix": ("forge_data_folder", {
        "forge-data/feasibility-report-x.md": b"# report\n",
        "forge-data/scratch.py": b"print(1)\n",
    }),
    "forge-versioned-evidence-report": ("forge_data_folder", {
        "forge-data/n/1.0.0/evidence-report.md": b"# evidence\n",
    }),
    "forge-brief-draft": ("forge_data_folder", {
        "forge-data/n/.brief-draft.json": b"{}\n",
    }),
    "skills-active-pointer": ("skills_output_folder", {
        "skills/n/active": b"1.0.0",
        "skills/n/1.0.0/SKILL.md": b"# n\n",
    }),
    "skf-staging-group": ("skills_output_folder", {
        "skills/.skf-staging/my-agent/SKILL.md": b"# agent\n",
        "skills/.skf-staging/module.yaml": b"code: x\n",
    }),
}


@pytest.mark.parametrize("name", list(SINGLE_RULE_FIXTURES))
def test_each_classifier_rule_alone_marks_skf_output(tmp_path, name):
    key, files = SINGLE_RULE_FIXTURES[name]
    project = _git_repo(tmp_path / "repo", files)
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="forge-data")
    value = "forge-data" if key == "forge_data_folder" else "skills"
    assert _collisions(payload, key) == []
    assert value in payload["effective_patterns"]
    assert value in _read_settings(project)["exclude_patterns"]


NESTED_MODULE = {"module.yaml": b"code: my-module\n", "my-agent/SKILL.md": b"# My agent\n"}


def test_untracked_nested_repo_as_skills_folder_is_classified(tmp_path):
    project = _git_repo(tmp_path / "repo")
    _git_repo(project / "skills", NESTED_MODULE)
    _seed_ccc_settings(project)
    payload = _merge(project)
    [warning] = _collisions(payload)
    assert "my-agent/" in warning
    assert "skills" not in payload["effective_patterns"]
    assert "skills" not in _read_settings(project)["exclude_patterns"]


def test_untracked_nested_repo_with_skf_layout_is_not_a_collision(tmp_path):
    project = _git_repo(tmp_path / "repo")
    _git_repo(project / "skills", {"n/1.0.0/n/SKILL.md": b"# n\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_nested_repo_below_skills_is_its_own_group(tmp_path):
    project = _git_repo(tmp_path / "repo", {"skills/n/1.0.0/n/SKILL.md": b"# n\n"})
    _git_repo(project / "skills" / "lib-src", {"src/core.py": b"x = 1\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    [warning] = _collisions(payload)
    assert "lib-src/" in warning
    assert "skills" not in payload["effective_patterns"]


def test_submodule_as_skills_folder_is_classified(tmp_path):
    source = _git_repo(tmp_path / "module-src", NESTED_MODULE)
    _git_commit(source)
    project = _git_repo(tmp_path / "repo")
    try:
        _git(project, "-c", "protocol.file.allow=always", "submodule", "add", str(source), "skills")
    except subprocess.CalledProcessError as e:
        pytest.skip(f"git submodule add failed: {e.stderr.decode('utf-8', errors='replace')}")
    assert (project / "skills" / "module.yaml").is_file()
    _seed_ccc_settings(project)
    payload = _merge(project)
    [warning] = _collisions(payload)
    assert "my-agent/" in warning
    assert "skills" not in payload["effective_patterns"]


def test_forge_folder_inside_skills_folder_is_not_a_collision(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "skf/n/1.0.0/n/SKILL.md": b"# n\n",
        "skf/forge-data/n/skill-brief.yaml": b"name: n\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project, skills="skf", forge_data="skf/forge-data")
    assert _warnings_with(payload, "SKF did not generate") == []
    assert "skf" in payload["effective_patterns"]
    assert "skf/forge-data" in payload["effective_patterns"]
    excludes = _read_settings(project)["exclude_patterns"]
    assert "skf" in excludes and "skf/forge-data" in excludes


def test_same_folder_for_both_settings_accepts_either_kind(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "out/_campaign/state.yaml": b"a: 1\n",
        "out/n/1.0.0/n/SKILL.md": b"# n\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project, skills="out", forge_data="out")
    assert _warnings_with(payload, "SKF did not generate") == []
    assert payload["effective_patterns"].count("out") == 1
    assert payload["patterns_added_list"].count("out") == 1
    assert _read_settings(project)["exclude_patterns"].count("out") == 1


def test_folder_under_always_excluded_pattern_skips_collision_check(tmp_path):
    project = _git_repo(tmp_path / "repo", {"_bmad-output/forge-data/notes/plan.md": b"# plan\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _warnings_with(payload, "SKF did not generate") == []
    assert "_bmad-output/forge-data" in payload["effective_patterns"]
    assert "_bmad-output/forge-data" in _read_settings(project)["exclude_patterns"]


REAL_RESULT_NAMES = [
    "export-skill-result-latest.json",
    "export-skill-result-20260424T230401Z.json",
    "export-skill-result.json",
    "drop-skill-result-latest.json",
    "rename-skill-result-latest.json",
    "quick-skill-result-latest.json",
    "create-skill-result.json",
    "update-skill-result.json",
    "update-skill-result-2026-04-13-aborted.json",
    "skf-test-skill-result.json",
    "audit-skill-result.json",
    "create-stack-skill-result-latest.json",
    "verify-stack-result-20260424T230401Z-a1b2c3.json",
    "analyze-source-result-latest.json",
]


def test_result_regex_is_narrow():
    assert not mod.RESULT_JSON_RE.match("skf-setup-result-envelope.v1.json")
    assert not mod.RESULT_JSON_RE.match("result.json")
    assert not mod.RESULT_JSON_RE.match("notes-result-draft.json")
    for name in REAL_RESULT_NAMES:
        assert mod.RESULT_JSON_RE.match(name), name


def test_nested_project_paths_relative_to_project_root(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    files = {f"proj/{rel}": content for rel, content in MODULE_SOURCE.items()}
    _write_files(repo, files)
    _git(repo, "--literal-pathspecs", "add", "--", *files.keys())
    project = repo / "proj"
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert len(_collisions(payload)) == 1
    assert "skills" not in payload["effective_patterns"]


def test_non_git_project_skips_collision_check(monkeypatch, tmp_path, tmp_project):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    _write_files(tmp_project, MODULE_SOURCE)
    _seed_ccc_settings(tmp_project)
    payload = _merge(tmp_project)
    assert "skills" in payload["effective_patterns"]
    assert payload["warnings"] == []


def test_git_unavailable_skips_collision_check(monkeypatch, tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE)
    _seed_ccc_settings(project)
    real_resolve = mod._resolve_outside_cwd
    monkeypatch.setattr(mod, "_resolve_outside_cwd",
                        lambda command: None if command == "git" else real_resolve(command))
    payload = _merge(project)
    assert "skills" in payload["effective_patterns"]
    assert payload["warnings"] == []


def test_git_failure_warns_that_collision_check_was_skipped(monkeypatch, tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE)
    _seed_ccc_settings(project)
    # git >= 2.35.2 then refuses the repository as unsafe (dubious ownership).
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    env = {k: v for k, v in os.environ.items() if k not in mod.GIT_LOCATION_VARS}
    probe = subprocess.run(["git", "-C", str(project), "ls-files"], capture_output=True, env=env)
    if probe.returncode == 0:
        pytest.skip("this git does not honour GIT_TEST_ASSUME_DIFFERENT_OWNER")
    payload = _merge(project)
    [warning] = _warnings_with(payload, "git ls-files failed")
    assert "collision check skipped" in warning
    assert "skills_output_folder" in warning
    assert "'" not in warning
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]
    assert "skills" in _read_settings(project)["exclude_patterns"]


def test_non_git_project_skips_silently_in_any_locale(monkeypatch, tmp_path, tmp_project):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("LANGUAGE", "fr")
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    _write_files(tmp_project, MODULE_SOURCE)
    _seed_ccc_settings(tmp_project)
    payload = _merge(tmp_project)
    assert _warnings_with(payload, "collision check skipped") == []
    assert payload["warnings"] == []
    assert "skills" in payload["effective_patterns"]


def test_git_timeout_warns_once_and_keeps_folder(monkeypatch, tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE)
    _seed_ccc_settings(project)
    real_git = mod._git
    ls_files_calls: list[tuple[str, ...]] = []

    def _timing_out(root, *args, literal=False):
        if args and args[0] == "ls-files":
            ls_files_calls.append(args)
            return -1, b"", ""
        return real_git(root, *args, literal=literal)

    monkeypatch.setattr(mod, "_git", _timing_out)
    payload = _merge(project)
    assert ls_files_calls
    expected = "git ls-files timed out for skills_output_folder; collision check skipped"
    assert payload["warnings"].count(expected) == 1
    assert _warnings_with(payload, "timed out") == [expected]
    assert "skills" in payload["effective_patterns"]
    assert "skills" in _read_settings(project)["exclude_patterns"]


def test_missing_folder_is_not_a_collision(tmp_path):
    project = _git_repo(tmp_path / "repo", {"src/app.py": b"x = 1\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_inherited_git_index_file_is_ignored(monkeypatch, tmp_path):
    repo_a = _git_repo(tmp_path / "a", {"a.txt": b"a\n"})
    listed_before = _git(repo_a, "ls-files")
    # B tracks its module source under an ignored skills/ (force-added), so
    # only B's own index lists it: read through A's leaked index, the files
    # would be untracked-and-ignored and the collision would go unseen.
    project = _git_repo(tmp_path / "b", {".gitignore": b"skills/\n", **MODULE_SOURCE}, add=False)
    _git(project, "--literal-pathspecs", "add", "-f", "--", *MODULE_SOURCE.keys())
    _seed_ccc_settings(project)

    monkeypatch.setenv("GIT_INDEX_FILE", str(repo_a / ".git" / "index"))
    payload = _merge(project)

    assert len(_collisions(payload)) == 1
    assert "skills" not in payload["effective_patterns"]
    assert _git(repo_a, "ls-files") == listed_before


@pytest.mark.skipif(sys.platform == "win32", reason="':' is not valid in Windows file names")
def test_colon_prefixed_folder_value_is_literal(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        ":odd/module.yaml": b"code: x\n",
        ":odd/agent/SKILL.md": b"# agent\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project, skills=":odd")
    [warning] = _collisions(payload)
    assert "agent/" in warning
    assert ":odd" not in payload["effective_patterns"]


# ─── .gitignore coverage and pruning ────────────────────────────────────────


GITIGNORE_WARNING = "is not gitignored here"


def test_gitignore_uncovered_warns(tmp_path):
    project = _git_repo(tmp_path / "repo")
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert len(_warnings_with(payload, GITIGNORE_WARNING)) == 1


def test_gitignore_covered_is_silent(tmp_path):
    project = _git_repo(tmp_path / "repo", {".gitignore": GITIGNORE_LINES})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _warnings_with(payload, GITIGNORE_WARNING) == []


def test_gitignore_check_silent_outside_git(tmp_project):
    _seed_ccc_settings(tmp_project)
    payload = _merge(tmp_project)
    assert _warnings_with(payload, GITIGNORE_WARNING) == []


def test_gitignore_updated_reports_ccc_init_change(tmp_path, fake_init):
    project = _git_repo(tmp_path / "repo")
    payload = _merge(project, allow_ccc_init=True)
    assert payload["gitignore_updated"] is True
    assert GITIGNORE_LINES in (project / ".gitignore").read_bytes()
    assert _warnings_with(payload, GITIGNORE_WARNING) == []

    seeded = _git_repo(tmp_path / "seeded", {".gitignore": GITIGNORE_LINES})
    _seed_ccc_settings(seeded, extra_excludes=ANCHORED_SKF)
    payload = _merge(seeded, allow_ccc_init=True)
    assert payload["written"] is False
    assert payload["gitignore_updated"] is False


def test_invalid_folder_value_blocks_pruning_and_keeps_record(tmp_path, tmp_project):
    _seed_ccc_settings(tmp_project, extra_excludes=ANCHORED_SKF)
    prior = _record(tmp_path, ANCHORED_SKF)
    payload = _merge(tmp_project, skills="skills/*", prior=prior)
    assert payload["patterns_removed_list"] == []
    assert "skills" in payload["effective_patterns"]
    assert "skills" in _read_settings(tmp_project)["exclude_patterns"]
    [blocked] = _warnings_with(payload, "kept previously recorded SKF exclusions")
    assert "(skills)" in blocked


def test_refused_value_on_legacy_record_keeps_record_folder_free(tmp_path, tmp_project):
    """A refused value blocks the legacy migration too, and effective_patterns
    is null so the folder-free record survives for the next valid run."""
    _seed_ccc_settings(tmp_project, extra_excludes=["**/forge-data"])
    prior = _record(tmp_path, [])
    payload = _merge(tmp_project, skills="skills/*", forge_data="forge-data", prior=prior)
    assert payload["effective_patterns"] is None
    assert len(_warnings_with(payload, "skills_output_folder contains a glob meta-character")) == 1
    [blocked] = _warnings_with(payload, "kept previously recorded SKF exclusions")
    assert "(**/forge-data)" in blocked
    assert payload["patterns_removed_list"] == []
    excludes = _read_settings(tmp_project)["exclude_patterns"]
    assert "**/forge-data" in excludes
    assert "forge-data" in excludes

    # The record is still folder-free, so the next valid run migrates.
    payload = _merge(tmp_project, skills="skills", forge_data="forge-data", prior=prior)
    assert payload["patterns_removed_list"] == ["**/forge-data"]
    assert "forge-data" in payload["effective_patterns"]


# ─── No single quote in any human-readable output ──────────────────────────


def _assert_no_squote(payload: dict) -> None:
    for warning in payload["warnings"]:
        assert "'" not in warning, warning
    if payload["not_ready_reason"] is not None:
        assert "'" not in payload["not_ready_reason"], payload["not_ready_reason"]


def test_no_single_quote_in_any_warning_or_reason(tmp_path, monkeypatch):
    # W1: a foreign root file whose name carries a quote, in a quoted project path.
    project = _git_repo(tmp_path / "o'brien", {"skills/don't.py": b"x = 1\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert len(_collisions(payload)) == 1
    assert "don`t.py" in _collisions(payload)[0]
    _assert_no_squote(payload)

    # R1 and W2b: ccc init output carrying a quote.
    def _failing(root):
        return False, "Error: it's broken"

    monkeypatch.setattr(mod, "run_ccc_init", _failing)
    missing = tmp_path / "missing"
    missing.mkdir()
    payload = _merge(missing, allow_ccc_init=True)
    assert "it`s broken" in payload["not_ready_reason"]
    _assert_no_squote(payload)

    bare = tmp_path / "bare"
    _seed_bare_settings(bare, LEGACY_SKF)
    payload = _merge(bare, allow_ccc_init=True)
    assert len(_warnings_with(payload, "it`s broken")) == 1
    _assert_no_squote(payload)

    # V7: a folder value carrying a quote.
    quoted = tmp_path / "quoted"
    _seed_ccc_settings(quoted)
    payload = _merge(quoted, skills="bob's")
    assert len(_warnings_with(payload, "single quote")) == 1
    _assert_no_squote(payload)

    # Malformed YAML on the CLI error path.
    broken = tmp_path / "broken"
    broken.mkdir()
    target = _settings_path(broken)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"exclude_patterns:\n\t- '**/x'\n")
    rc, _, stderr = _run(broken)
    assert rc == 1
    assert "'" not in stderr


# ─── Prose pins on the step files that consume the helper output ────────────


CCC_INDEX_BINDINGS = [
    ("ccc_index_action", "index_action"),
    ("settings_yml_written", "written"),
    ("settings_yml_patterns_added", "patterns_added"),
    ("settings_yml_patterns_removed", "patterns_removed"),
    ("gitignore_updated", "gitignore_updated"),
    ("ccc_exclude_patterns", "effective_patterns"),
    ("ccc_exclusion_warnings", "warnings"),
    ("ccc_settings_error", "not_ready_reason"),
]


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)


def test_ccc_index_step_binds_every_consumed_field():
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    for flag, field in CCC_INDEX_BINDINGS:
        binding = f"`{{{flag}}}` ← `{field}`"
        assert binding in text, f"missing binding {binding}"


def test_ccc_index_step_invocation_passes_record_and_index_flags():
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    [invocation] = [b for b in _bash_blocks(text) if "{mergeCccExclusionsHelper}" in b]
    for flag in ("--prior-state-from", "--index-fresh", "--skip-index"):
        assert flag in invocation
    assert "--no-ccc-init" not in invocation


def test_ccc_index_step_never_runs_ccc_init():
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    blocks = _bash_blocks(text)
    assert blocks
    for block in blocks:
        assert "ccc init" not in block


def test_ccc_index_step_lists_every_index_action():
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    for action in mod.INDEX_ACTIONS:
        assert f'`"{action}"`' in text, action


def test_record_kept_when_step_does_not_reconcile():
    lines = [line for line in CCC_INDEX_STEP.read_text(encoding="utf-8").splitlines()
             if "ccc_exclude_patterns:" in line]
    assert len(lines) >= 2
    for line in lines:
        assert "ccc_exclude_patterns: null" in line, line


def test_report_shows_removed_count_notes_and_gitignore():
    text = REPORT_STEP.read_text(encoding="utf-8")
    section_2 = text.split("### 3.", 1)[0]
    assert "{settings_yml_patterns_removed}" in section_2
    assert "ccc_exclusion_warnings" in section_2
    assert "gitignore_updated is true" in section_2
