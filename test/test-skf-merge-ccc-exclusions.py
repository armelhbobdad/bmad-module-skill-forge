#!/usr/bin/env python3
"""Tests for skf-merge-ccc-exclusions.py.

Highest-value tests:
- Config-value validation refuses every input that would produce a
  malformed or over-broad ccc pattern (empty, absolute, `..`, `!`, glob
  meta, placeholders, single quotes), and values are normalized first.
- Folder patterns are anchored to the project root (`skills`, never
  `**/skills`). A folder that also holds content SKF did not generate is
  excluded entry by entry (class-escaped names, fixed entries, result and
  report families, never a `!` or `{folder}/*` pattern), a folder with no
  SKF output is left out, and a folder the user already excluded is left
  alone (real git, cleaned environment).
- settings.yml states: a missing file is created only by `ccc init`, a file
  lacking the ccc defaults is rebuilt with user entries kept, a failed
  rebuild restores the original bytes, and a leftover backup is recovered.
- Pruning follows the forge-tier.yaml ownership record, never touches
  entries SKF did not add, and is blocked while a folder value is refused;
  the legacy `**/<value>` migration needs a folder-free forge-tier.yaml.
- The collision classifier: one fixture per rule, nested repositories and
  submodules, malformed metadata; git failures warn, non-git is silent.
- The index decision, the .gitignore check, and the payload-safety
  guarantee (no `'`, backslash or control character) for every
  human-readable string and every recorded pattern.
- Prose pins on the setup step files that consume the helper output.
- Clone mode (`--clone-root`, create-skill): the standard exclusions and the
  `--include-ext` file types are appended, never replacing a list or
  removing an entry, an include entry that already matches an extension (as
  ccc reads globs) is left to cover it, a bare `- **/x` item an earlier edit
  left is quoted again, and the setup flags are refused.

No test runs a real `ccc`: subprocess CLI tests always pass --no-ccc-init
(and run --build-index only where index_action is fail), and in-process
tests replace `run_ccc_init` and `_run_ccc` with fakes.
"""

from __future__ import annotations

import importlib.util
import itertools
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
# Setup's FORGE STATUS banner is what skf-emit-result-envelope.py's
# render-report prints, so the banner pins below read its output.
EMIT_HELPER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
TIER_RULES = REPO_ROOT / "src" / "skf-setup" / "references" / "tier-rules.md"

spec = importlib.util.spec_from_file_location("skf_merge_ccc_exclusions", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

_emit_spec = importlib.util.spec_from_file_location("skf_emit_result_envelope", EMIT_HELPER)
emit = importlib.util.module_from_spec(_emit_spec)
assert _emit_spec.loader is not None
_emit_spec.loader.exec_module(emit)


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


def _config_path(path: Path) -> str:
    """A path as a quoted git config value, as test/conftest.py writes it.

    Unquoted, a `#` or `;` in the temp path starts a comment and cuts the value.
    """
    text = path.as_posix().replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


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


SKF_MARKER = {"generated_by": "create-skill"}


def _marked(files: dict[str, bytes]) -> dict[str, bytes]:
    """`files` plus an SKF-marked metadata.json beside each `<g>/<v>/<g>/SKILL.md`.

    Only a marked metadata.json makes a skills group SKF output, as in
    skf-skill-inventory.py: the versioned layout alone does not.
    """
    out = dict(files)
    for rel in files:
        parts = rel.split("/")
        if len(parts) >= 4 and parts[-1] == "SKILL.md" and parts[-2] == parts[-4]:
            meta = "/".join(parts[:-1] + ["metadata.json"])
            out.setdefault(meta, json.dumps(dict(SKF_MARKER, name=parts[-2])).encode("utf-8"))
    return out


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
    # Invalid — control character does not survive the setup payloads
    ("tab\tin",                      False),
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

    _, w = mod.validate_config_value("skills_output_folder", "a\x7fb")
    assert "control character" in w

    for value in ("", "/abs", "x*", "{stray}", "!x", "../x", "bob's", "a]", "C:/x", "a\tb"):
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
    # The literal placeholder is intended: setup's banner renders it like its
    # own {project-root} paths, and the envelope keeps it verbatim.
    assert warning.endswith(
        "; run ccc index in {project-root} or re-run /skf-setup without --ccc-skip-index")
    assert tmp_project.as_posix() not in warning


# Each family of warning SKF words itself, with the text that names the root.
ROOT_PLACEHOLDER_WARNINGS = {
    "refused": "fix the value in {project-root}/_bmad/skf/config.yaml",
    "uncovered": "add /.cocoindex_code/ to {project-root}/.gitignore",
    "collision": "set skills_output_folder in {project-root}/_bmad/skf/config.yaml",
    "rebuild": "fix ccc init in {project-root} and re-run /skf-setup",
    "skipped": "run ccc index in {project-root} or re-run /skf-setup",
}


def test_warnings_name_the_project_root_as_the_placeholder(tmp_path, failing_init):
    projects = {name: tmp_path / name for name in ROOT_PLACEHOLDER_WARNINGS}
    payloads = {}
    _seed_ccc_settings(projects["refused"])
    payloads["refused"] = _merge(projects["refused"], skills="/abs")
    _git_repo(projects["uncovered"])
    _seed_ccc_settings(projects["uncovered"])
    payloads["uncovered"] = _merge(projects["uncovered"])
    _git_repo(projects["collision"], MODULE_SOURCE)
    _seed_ccc_settings(projects["collision"])
    payloads["collision"] = _merge(projects["collision"])
    _seed_bare_settings(projects["rebuild"], LEGACY_SKF)
    payloads["rebuild"] = _merge(projects["rebuild"], allow_ccc_init=True)
    _seed_ccc_settings(projects["skipped"])
    payloads["skipped"] = _merge(projects["skipped"], skip_index=True)
    for name, needle in ROOT_PLACEHOLDER_WARNINGS.items():
        [warning] = _warnings_with(payloads[name], needle)
        for form in _root_forms(projects[name]):
            assert form not in warning, (name, warning)
    # not_ready_reason follows the same rule. A failed rebuild and a failed
    # first ccc init each give one.
    projects["uninit"] = tmp_path / "uninit"
    projects["uninit"].mkdir()
    payloads["uninit"] = _merge(projects["uninit"], allow_ccc_init=True)
    for name in ("rebuild", "uninit"):
        assert payloads[name]["not_ready_reason"], name
    for name, payload in payloads.items():
        reason = payload["not_ready_reason"] or ""
        for form in _root_forms(projects[name]):
            assert form not in reason, (name, reason)


def _root_forms(project: Path) -> set[str]:
    # Messages reach setup with `/` (payload safety), and resolve() covers
    # /private/var on macOS and 8.3 short names on Windows.
    return {str(project), project.as_posix(), project.resolve().as_posix()}


def test_placeholder_refusal_names_the_placeholder_not_the_root(tmp_project):
    # The refusal names the placeholder in words, so every `{project-root}`
    # in SKF's own words is the project root, which the banner resolves.
    _seed_ccc_settings(tmp_project)
    payload = _merge(tmp_project, skills="{output_folder}/skills")
    [warning] = _warnings_with(payload, "unresolved template placeholder")
    assert warning.endswith("let this script resolve the project-root placeholder")
    assert "{project-root}" not in warning
    assert f"  - {warning}" in _setup_banner(ccc_exclusion_warnings=[warning])


# ─── Collision check (real git, cleaned environment) ───────────────────────


def _collisions(payload: dict, key: str = "skills_output_folder") -> list[str]:
    """The left-out warnings for `key`: a folder with no SKF output."""
    return [w for w in payload["warnings"] if w.startswith(key + " ") and "so SKF left it out" in w]


def _mixed(payload: dict, key: str = "skills_output_folder") -> list[str]:
    """The notes for `key` whose folder SKF excluded entry by entry."""
    return [w for w in payload["warnings"]
            if w.startswith(key + " ") and "excluded only its own entries" in w]


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
    project = _git_repo(tmp_path / "repo", _marked({
        "skills/.gitkeep": b"# This file ensures the directory is tracked by git\n",
        "skills/.export-manifest.json": b'{"exports": {}}\n',
        "skills/export-skill-result-latest.json": b"{}\n",
        "skills/n/active": b"1.0.0",
        "skills/n/rename-skill-result-latest.json": b"{}\n",
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
        "skills/n/1.0.0/n/references/x.md": b"# x\n",
        "skills/_batch/quick-skill-batch-latest.json": b"{}\n",
    }))
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]
    assert "skills" in _read_settings(project)["exclude_patterns"]


# A module's own skills that an earlier SKF moved into the versioned layout:
# `active` links, version folders, a manifest key and a result file, and no
# SKF marker anywhere. Every workflow calls them not SKF output.
MOVED_MODULE_SKILLS = {
    "skills/module.yaml": b"code: my-module\n",
    "skills/agent-a/active": b"1.0.0",
    "skills/agent-a/1.0.0/agent-a/SKILL.md": b"# agent a\n",
    "skills/agent-a/1.0.0/agent-a/metadata.json": b'{"name": "agent-a", "version": "1.0.0"}\n',
    "skills/agent-b/active": b"1.0.0",
    "skills/agent-b/1.0.0/agent-b/SKILL.md": b"# agent b\n",
    "skills/agent-b/rename-skill-result-latest.json": b"{}\n",
}


def test_module_skills_an_earlier_skf_moved_are_left_out_with_a_warning(tmp_path):
    project = _git_repo(tmp_path / "repo", MOVED_MODULE_SKILLS)
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert "skills" not in payload["effective_patterns"]
    assert _under(payload["effective_patterns"], "skills") == []
    assert "skills" not in _read_settings(project)["exclude_patterns"]
    [warning] = _collisions(payload)
    assert "agent-a/" in warning and "agent-b/" in warning and "module.yaml" in warning


def test_moved_module_skills_beside_skf_output_stay_indexed(tmp_path):
    files = dict(MOVED_MODULE_SKILLS)
    files["skills/.export-manifest.json"] = b'{"exports": {"agent-a": {}, "mylib": {}}}\n'
    files.update(_marked({"skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n"}))
    project = _git_repo(tmp_path / "repo", files)
    _seed_ccc_settings(project)
    payload = _merge(project)
    effective = payload["effective_patterns"]
    assert "skills/mylib" in effective
    assert not [p for p in effective if "agent" in p], effective
    [note] = _mixed(payload)
    assert "agent-a/" in note and "agent-b/" in note


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


def test_manifest_export_key_alone_is_not_skf_output(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "skills/.export-manifest.json": b'{"exports": {"flat": {"version": "1.0.0"}}}\n',
        "skills/flat/SKILL.md": b"# flat\n",
        "skills/flat/references/a.md": b"# a\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    effective = payload["effective_patterns"]
    assert "skills" not in effective and "skills/flat" not in effective
    assert "skills/.export-manifest.json" in effective
    [note] = _mixed(payload)
    assert "flat/" in note


def test_root_notes_tolerated_beside_skf_output(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "skills/NOTES.md": b"# notes\n",
        "skills/scratch.py": b"print(1)\n",
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
    }))
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
    "skills-marked-version": ("skills_output_folder", {
        "skills/n/1.0.0/n/metadata.json": json.dumps(SKF_MARKER).encode("utf-8"),
    }),
    "skf-staging-group": ("skills_output_folder", {
        "skills/.skf-staging/my-agent/SKILL.md": b"# agent\n",
        "skills/.skf-staging/module.yaml": b"code: x\n",
    }),
}


# Structure SKF also writes, which proves nothing on its own: a module skill
# can sit in that layout.
NOT_EVIDENCE_FIXTURES = {
    "versioned-layout": {"skills/n/1.0.0/n/SKILL.md": b"# n\n"},
    "active-pointer": {"skills/n/active": b"1.0.0", "skills/n/1.0.0/SKILL.md": b"# n\n"},
    "result-file": {"skills/n/rename-skill-result-latest.json": b"{}\n",
                    "skills/n/SKILL.md": b"# n\n"},
    "unmarked-metadata": {"skills/n/1.0.0/n/SKILL.md": b"# n\n",
                          "skills/n/1.0.0/n/metadata.json": b'{"name": "n"}\n'},
}


@pytest.mark.parametrize("name", list(NOT_EVIDENCE_FIXTURES))
def test_layout_active_or_result_alone_is_not_skf_output(tmp_path, name):
    project = _git_repo(tmp_path / "repo", NOT_EVIDENCE_FIXTURES[name])
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert "skills" not in payload["effective_patterns"]
    [warning] = _collisions(payload)
    assert "n/" in warning


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need a privilege on Windows")
def test_linked_skill_group_is_not_skf_output(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({"skills/n/1.0.0/n/SKILL.md": b"# n\n"}))
    elsewhere = tmp_path / "elsewhere"
    _write_files(elsewhere, {"linked/SKILL.md": b"# l\n",
                             "linked/metadata.json": json.dumps(SKF_MARKER).encode("utf-8")})
    (project / "skills" / "linked").symlink_to(elsewhere / "linked", target_is_directory=True)
    _seed_ccc_settings(project)
    payload = _merge(project)
    effective = payload["effective_patterns"]
    assert "skills/n" in effective and "skills/linked" not in effective
    [note] = _mixed(payload)
    assert "linked/" in note


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
    _git_repo(project / "skills", _marked({"n/1.0.0/n/SKILL.md": b"# n\n"}))
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    assert "skills" in payload["effective_patterns"]


def test_nested_repo_below_skills_is_its_own_group(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({"skills/n/1.0.0/n/SKILL.md": b"# n\n"}))
    _git_repo(project / "skills" / "lib-src", {"src/core.py": b"x = 1\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _collisions(payload) == []
    [note] = _mixed(payload)
    assert "lib-src/" in note
    effective = payload["effective_patterns"]
    assert "skills" not in effective
    assert "skills/n" in effective
    assert not [p for p in effective if p.startswith("skills/lib-src")]


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
    project = _git_repo(tmp_path / "repo", _marked({
        "skf/n/1.0.0/n/SKILL.md": b"# n\n",
        "skf/forge-data/n/skill-brief.yaml": b"name: n\n",
    }))
    _seed_ccc_settings(project)
    payload = _merge(project, skills="skf", forge_data="skf/forge-data")
    assert _warnings_with(payload, "SKF did not generate") == []
    assert "skf" in payload["effective_patterns"]
    assert "skf/forge-data" in payload["effective_patterns"]
    excludes = _read_settings(project)["exclude_patterns"]
    assert "skf" in excludes and "skf/forge-data" in excludes


def test_same_folder_for_both_settings_accepts_either_kind(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "out/_campaign/state.yaml": b"a: 1\n",
        "out/n/1.0.0/n/SKILL.md": b"# n\n",
    }))
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


# ─── Per-entry exclusion in a mixed folder (real git) ──────────────────────


MIXED_SKILLS = _marked({
    "skills/.export-manifest.json": b'{"exports": {"mylib": {"active_version": "1.0.0"}}}\n',
    "skills/export-skill-result-20260926T120000Z.json": b"{}\n",
    "skills/export-skill-result-latest.json": b"{}\n",
    "skills/drop-skill-result-latest.json": b"{}\n",
    "skills/mylib/active": b"1.0.0",
    "skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n",
    "skills/_batch/quick-skill-batch-latest.json": b"{}\n",
    "skills/vendor-skill/SKILL.md": b"# vendor\n",
    "skills/NOTES.md": b"# notes\n",
    "skills/README.md": b"# readme\n",
})
SKILLS_FIXED_PATTERNS = [
    "skills/.export-manifest.json",
    "skills/_batch",
    "skills/drop-skill-result*.json",
    "skills/export-skill-result*.json",
]
MIXED_SKILLS_PATTERNS = SKILLS_FIXED_PATTERNS + ["skills/mylib"]


def _under(patterns, folder: str) -> list[str]:
    return sorted(p for p in patterns if p.startswith(folder + "/"))


def test_mixed_folder_excludes_only_skf_entries(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project)
    payload = _merge(project)
    effective = payload["effective_patterns"]
    assert _under(effective, "skills") == MIXED_SKILLS_PATTERNS
    assert "skills" not in effective
    assert not [p for p in effective if "vendor" in p or "NOTES" in p or "README" in p]
    assert _read_settings(project)["exclude_patterns"] == (
        CCC_DEFAULTS + list(mod.ALWAYS_INCLUDE) + MIXED_SKILLS_PATTERNS
        + ["_bmad-output/forge-data"])
    assert _collisions(payload) == []
    [note] = _mixed(payload)
    assert "vendor-skill/" in note and "NOTES.md" in note and "2 entries" in note
    assert "README" not in note
    assert "re-run /skf-setup" in note and "twice" in note
    assert "skills/<name>" in note
    assert "folder only SKF uses" not in note
    assert payload["index_action"] == "index"


def test_mixed_folder_emits_fixed_entries_before_they_exist(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n",
        "skills/vendor-skill/SKILL.md": b"# vendor\n",
        "forge-data/n/skill-brief.yaml": b"name: n\n",
        "forge-data/plans/roadmap.md": b"# mine\n",
    }))
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="forge-data")
    effective = payload["effective_patterns"]
    assert _under(effective, "skills") == MIXED_SKILLS_PATTERNS
    assert _under(effective, "forge-data") == sorted(
        ["forge-data/_campaign", "forge-data/improvement-queue", "forge-data/n"]
        + [f"forge-data/{prefix}*" for prefix in mod.FORGE_ROOT_PREFIXES])
    assert "forge-data" not in effective


def test_mixed_folder_record_follows_every_transition(tmp_path):
    files = {k: v for k, v in MIXED_SKILLS.items() if "vendor" not in k}
    project = _git_repo(tmp_path / "repo", files)
    _seed_ccc_settings(project)
    prior = _record(tmp_path, [])

    def run():
        payload = _merge(project, prior=prior)
        _record(tmp_path, payload["effective_patterns"])
        return payload

    first = run()
    assert "skills" in first["effective_patterns"]

    # A vendor skill arrives: the bare value gives way to per-entry patterns.
    _write_files(project, {"skills/vendor-skill/SKILL.md": b"# vendor\n"})
    second = run()
    assert second["patterns_removed_list"] == ["skills"]
    assert sorted(second["patterns_added_list"]) == MIXED_SKILLS_PATTERNS

    # A pattern the user adds by hand is never pruned.
    data = _read_settings(project)
    data["exclude_patterns"].append("skills/vendor-skill")
    _write_yaml(_settings_path(project), data)

    # A dropped skill loses its pattern and a new one gains one.
    shutil.rmtree(project / "skills" / "mylib")
    _git(project, "rm", "-r", "-q", "--cached", "skills/mylib")
    _write_files(project, _marked({"skills/newlib/1.0.0/newlib/SKILL.md": b"# newlib\n"}))
    third = run()
    assert third["patterns_removed_list"] == ["skills/mylib"]
    assert third["patterns_added_list"] == ["skills/newlib"]
    assert "skills/vendor-skill" not in third["effective_patterns"]

    # The vendor skill leaves: back to the bare value.
    shutil.rmtree(project / "skills" / "vendor-skill")
    fourth = run()
    assert fourth["patterns_added_list"] == ["skills"]
    assert sorted(fourth["patterns_removed_list"]) == _under(third["effective_patterns"], "skills")
    assert "skills/vendor-skill" in _read_settings(project)["exclude_patterns"]
    assert _mixed(fourth) == []


def test_mixed_folder_re_run_with_record_is_no_op(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project)
    first = _merge(project)
    prior = _record(tmp_path, first["effective_patterns"])
    settings_path = _settings_path(project)
    mtime_before = settings_path.stat().st_mtime_ns

    second = _merge(project, prior=prior, index_fresh=True)
    assert second["written"] is False
    assert second["patterns_added"] == 0
    assert second["patterns_removed"] == 0
    assert second["index_action"] == "keep"
    assert second["effective_patterns"] == first["effective_patterns"]
    assert settings_path.stat().st_mtime_ns == mtime_before
    assert len(_mixed(second)) == 1


def test_ccc_literal_escapes_with_classes():
    assert mod.ccc_literal("a*b") == "a[*]b"
    assert mod.ccc_literal("a?b") == "a[?]b"
    assert mod.ccc_literal("[x]") == "[[]x[]]"
    assert mod.ccc_literal("a]b") == "a[]]b"
    assert mod.ccc_literal("{a,b}") == "[{]a,b[}]"
    assert mod.ccc_literal("sp ace!") == "sp ace!"
    assert mod.ccc_literal("plain-name_1.0") == "plain-name_1.0"


def test_entry_names_with_glob_characters_are_escaped(tmp_path):
    names = {"[x]": "skills/[[]x[]]", "{a,b}": "skills/[{]a,b[}]"}
    if sys.platform != "win32":
        names["a*b"] = "skills/a[*]b"
    files = {"skills/.export-manifest.json":
             json.dumps({"exports": {name: {} for name in names}}).encode("utf-8"),
             "skills/x/SKILL.md": b"# foreign x\n"}
    for name in names:
        files[f"skills/{name}/SKILL.md"] = b"# skf\n"
        files[f"skills/{name}/metadata.json"] = json.dumps(SKF_MARKER).encode("utf-8")
    project = _git_repo(tmp_path / "repo", files)
    _seed_ccc_settings(project)
    payload = _merge(project)
    effective = payload["effective_patterns"]
    for pattern in names.values():
        assert pattern in effective, pattern
    assert not [p for p in effective if "\\" in p]
    # The patterns survive the settings.yml round trip exactly.
    excludes = _read_settings(project)["exclude_patterns"]
    for pattern in names.values():
        assert pattern in excludes, pattern
    [note] = _mixed(payload)
    assert "x/" in note


def test_entry_pattern_names_follow_the_disk():
    disk = ["mine", "Other", "café", "Mine2"]
    assert mod._on_disk("mine", disk) == ["mine"]
    assert mod._on_disk("other", disk) == ["Other"]
    assert mod._on_disk("café", disk) == ["café"]
    assert mod._on_disk("gone", disk) == []
    assert mod._on_disk("x", None) == ["x"]
    assert mod._on_disk("mine", ["mine", "Mine"]) == ["mine"]
    # A differently cased entry git lists on its own is never borrowed.
    assert mod._on_disk("Mine", ["mine"], frozenset({"Mine", "mine"})) == []


def test_deleted_tracked_entry_never_borrows_a_foreign_name(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "skills/Mine/1.0.0/Mine/SKILL.md": b"# Mine\n",
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
    }))
    shutil.rmtree(project / "skills" / "Mine")
    _write_files(project, {"skills/mine/SKILL.md": b"# foreign\n"})
    if (project / "skills" / "Mine").exists():
        pytest.skip("case-insensitive filesystem")
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _under(payload["effective_patterns"], "skills") == sorted(
        SKILLS_FIXED_PATTERNS + ["skills/n"])
    [note] = _mixed(payload)
    assert "mine/" in note


@pytest.mark.skipif(sys.platform == "win32", reason="quote, backslash and tab names are POSIX only")
def test_unwritable_entry_names_are_skipped_with_warning(tmp_path):
    marker = json.dumps(SKF_MARKER).encode("utf-8")
    project = _git_repo(tmp_path / "repo", {
        "skills/.export-manifest.json": json.dumps(
            {"exports": {"bob's": {}, "back\\slash": {}, "t\tab": {}, "ok": {}}}).encode("utf-8"),
        "skills/bob's/SKILL.md": b"# b\n",
        "skills/bob's/metadata.json": marker,
        "skills/back\\slash/SKILL.md": b"# b\n",
        "skills/back\\slash/metadata.json": marker,
        "skills/t\tab/SKILL.md": b"# t\n",
        "skills/t\tab/metadata.json": marker,
        "skills/ok/SKILL.md": b"# ok\n",
        "skills/ok/metadata.json": marker,
        "skills/vendor/SKILL.md": b"# v\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _under(payload["effective_patterns"], "skills") == sorted(
        SKILLS_FIXED_PATTERNS + ["skills/ok"])
    [skipped] = _warnings_with(payload, "cannot write as a ccc pattern")
    assert "3 SKF entries" in skipped
    assert "bob`s" in skipped and "back?slash" in skipped and "t?ab" in skipped
    _assert_payload_safe(payload)


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="needs a filesystem that stores names as raw bytes")
def test_undecodable_entry_name_is_skipped_not_dropped(tmp_path):
    project = _git_repo(tmp_path / "repo", {"skills/vendor/SKILL.md": b"# v\n"})
    raw = os.fsencode(project / "skills") + b"/bad\xff"
    try:
        os.makedirs(raw + b"/1.0.0/bad\xff")
        with open(raw + b"/1.0.0/bad\xff/SKILL.md", "wb") as fh:
            fh.write(b"# bad\n")
        with open(raw + b"/1.0.0/bad\xff/metadata.json", "wb") as fh:
            fh.write(json.dumps(SKF_MARKER).encode("utf-8"))
    except OSError:
        pytest.skip("filesystem refuses names that are not UTF-8")
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert _under(payload["effective_patterns"], "skills") == SKILLS_FIXED_PATTERNS
    [skipped] = _warnings_with(payload, "cannot write as a ccc pattern")
    assert "1 SKF entry" in skipped and "bad?" in skipped
    _assert_payload_safe(payload)
    json.dumps(payload).encode("ascii")


def test_mixed_forge_folder_uses_prefix_patterns(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "forge-data/n/skill-brief.yaml": b"name: n\n",
        "forge-data/_campaign/state.yaml": b"a: 1\n",
        "forge-data/analyze-source-report-x.md": b"# r\n",
        "forge-data/verify-stack-result-20260424T230401Z-a1b2c3.json": b"{}\n",
        "forge-data/plans/roadmap.md": b"# mine\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="forge-data")
    effective = payload["effective_patterns"]
    for p in ("forge-data/n", "forge-data/_campaign", "forge-data/analyze-source-*",
              "forge-data/verify-stack-result-*"):
        assert p in effective, p
    assert not [p for p in effective if "report-x" in p or "20260424" in p or "plans" in p]
    assert "forge-data" not in effective
    [note] = _mixed(payload, "forge_data_folder")
    assert "plans/" in note
    assert "twice" not in note


def test_forge_evidence_is_read_from_disk_like_the_skills_rule(tmp_path):
    """A brief `.gitignore` hides still proves SKF wrote the forge folder."""
    project = _git_repo(tmp_path / "repo", {
        ".gitignore": b"forge-data/*/skill-brief.yaml\n",
        "forge-data/n/skill-brief.yaml": b"name: n\n",
        "forge-data/n/NOTES.md": b"# mine\n",
    }, add=False)
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="forge-data")
    assert "forge-data" in payload["effective_patterns"]
    assert _collisions(payload, "forge_data_folder") == []


def test_result_file_deeper_than_a_version_folder_is_not_forge_evidence(tmp_path):
    project = _git_repo(tmp_path / "repo", {
        "forge-data/n/skill-brief.yaml": b"name: n\n",
        "forge-data/pkg/a/b/x-result-latest.json": b"{}\n",
    })
    _seed_ccc_settings(project)
    payload = _merge(project, forge_data="forge-data")
    effective = payload["effective_patterns"]
    assert "forge-data/n" in effective and "forge-data" not in effective
    assert not [p for p in effective if p.startswith("forge-data/pkg")]
    [note] = _mixed(payload, "forge_data_folder")
    assert "pkg/" in note


@pytest.mark.parametrize("inner", ["mixed", "left-out"])
def test_nested_folder_defers_to_inner_mixed_folder(tmp_path, inner):
    files = _marked({"skf/n/1.0.0/n/SKILL.md": b"# n\n", "skf/forge-data/notes/a.md": b"# mine\n"})
    if inner == "mixed":
        files["skf/forge-data/n/skill-brief.yaml"] = b"name: n\n"
    project = _git_repo(tmp_path / "repo", files)
    _seed_ccc_settings(project)
    payload = _merge(project, skills="skf", forge_data="skf/forge-data")
    effective = payload["effective_patterns"]
    assert "skf" not in effective and "skf/forge-data" not in effective
    assert "skf/n" in effective
    assert not [p for p in effective if p.startswith("skf/forge-data/notes")]
    # The outer folder has no foreign entry of its own: no note for it.
    assert _mixed(payload) == [] and _collisions(payload) == []
    if inner == "mixed":
        assert "skf/forge-data/n" in effective
        assert len(_mixed(payload, "forge_data_folder")) == 1
    else:
        assert _under(effective, "skf/forge-data") == []
        assert len(_collisions(payload, "forge_data_folder")) == 1


def test_group_holding_the_other_folder_gets_no_entry_pattern(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "skf/n/1.0.0/n/SKILL.md": b"# n\n",
        "skf/vendor/SKILL.md": b"# v\n",
        "skf/forge-data/n/skill-brief.yaml": b"name: n\n",
        "skf/forge-data/plans/x.md": b"# x\n",
    }))
    _seed_ccc_settings(project)
    payload = _merge(project, skills="skf", forge_data="skf/forge-data")
    effective = payload["effective_patterns"]
    assert "skf/n" in effective and "skf/forge-data/n" in effective
    assert "skf/forge-data" not in effective and "skf" not in effective
    assert len(_mixed(payload)) == 1
    assert len(_mixed(payload, "forge_data_folder")) == 1


def test_per_entry_record_does_not_trigger_legacy_migration(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project, extra_excludes=["**/skills"])
    prior = _record(tmp_path, list(mod.ALWAYS_INCLUDE) + ["skills/mylib"])
    payload = _merge(project, prior=prior)
    assert "**/skills" in _read_settings(project)["exclude_patterns"]
    assert payload["patterns_removed_list"] == []


def test_refused_value_keeps_recorded_entry_patterns(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project)
    first = _merge(project)
    prior = _record(tmp_path, first["effective_patterns"])
    payload = _merge(project, skills="skills/*", prior=prior)
    assert payload["patterns_removed_list"] == []
    for p in MIXED_SKILLS_PATTERNS:
        assert p in payload["effective_patterns"], p
        assert p in _read_settings(project)["exclude_patterns"], p
    [blocked] = _warnings_with(payload, "kept previously recorded SKF exclusions")
    assert "skills/.export-manifest.json" in blocked
    assert "and 2 more" in blocked


def test_blocked_warning_samples_long_record(tmp_path, tmp_project):
    recorded = [f"skills/s{i}" for i in range(5)]
    _seed_ccc_settings(tmp_project, extra_excludes=recorded)
    prior = _record(tmp_path, list(mod.ALWAYS_INCLUDE) + recorded)
    payload = _merge(tmp_project, skills="skills/*", prior=prior)
    [blocked] = _warnings_with(payload, "kept previously recorded SKF exclusions")
    assert "(skills/s0, skills/s1, skills/s2 and 2 more)" in blocked
    assert "skills/s3" not in blocked


def test_no_skf_output_warning_keeps_relocation_advice(tmp_path):
    project = _git_repo(tmp_path / "repo", MODULE_SOURCE)
    _seed_ccc_settings(project)
    [warning] = _collisions(_merge(project))
    assert "folder only SKF uses" in warning and "installed from elsewhere" in warning
    assert "SKF did not generate" in warning and "no SKF output" in warning
    forge = _git_repo(tmp_path / "forge", {"src/pkg/mod.py": b"x = 1\n"})
    _seed_ccc_settings(forge)
    [warning] = _collisions(_merge(forge, forge_data="src"), "forge_data_folder")
    assert "folder only SKF uses" in warning
    assert "installed from elsewhere" not in warning


@pytest.mark.skipif(sys.platform == "win32", reason="newline is not valid in Windows names")
def test_foreign_names_are_printable_in_warnings(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({"skills/a\nb/x.md": b"# x\n",
                                                    "skills/n/1.0.0/n/SKILL.md": b"# n\n"}))
    _seed_ccc_settings(project)
    [note] = _mixed(_merge(project))
    assert "a?b/" in note and "\n" not in note


def test_info_exclude_and_global_excludes_do_not_hide_foreign_entries(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({"skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n"}))
    _write_files(project, {
        "skills/ext-a/SKILL.md": b"# a\n",
        "skills/ext-b/SKILL.md": b"# b\n",
        "skills/ext-c/SKILL.md": b"# c\n",
        "skills/.gitignore": b"ext-c/\n",
    })
    (project / ".git" / "info" / "exclude").write_bytes(b"skills/ext-a/\n")
    global_ignore = tmp_path / "global-ignore"
    global_ignore.write_bytes(b"skills/ext-b/\n")
    (tmp_path / "empty-gitconfig").write_bytes(
        f"[core]\n\texcludesFile = {_config_path(global_ignore)}\n".encode("utf-8"))
    ignored = _git(project, "ls-files", "--others", "--exclude-standard", "--", "skills")
    assert "ext-a" not in ignored and "ext-b" not in ignored
    _seed_ccc_settings(project)
    payload = _merge(project)
    effective = payload["effective_patterns"]
    assert "skills" not in effective
    assert "skills/mylib" in effective
    [note] = _mixed(payload)
    # ccc reads only .gitignore files: ext-a and ext-b stay visible to it.
    assert "ext-a/" in note and "ext-b/" in note
    assert "ext-c/" not in note


def test_tracked_but_deleted_entries_are_ignored(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
        "skills/vendor2/SKILL.md": b"# v\n",
    }))
    _git_commit(project)
    shutil.rmtree(project / "skills" / "vendor2")
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert "skills" in payload["effective_patterns"]
    assert _mixed(payload) == [] and _collisions(payload) == []


def _seed_without_dot_default(project: Path, extra_excludes=()) -> None:
    _write_yaml(_settings_path(project), {
        "exclude_patterns": [p for p in CCC_DEFAULTS if p != "**/.*"] + list(extra_excludes),
        "include_patterns": list(CCC_INCLUDES),
    })


def test_hidden_entries_neutral_only_with_ccc_dot_default(tmp_path):
    files = _marked({
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
        "skills/.idea/workspace.xml": b"<x/>\n",
        "skills/.notes.md": b"# notes\n",
    })
    with_default = _git_repo(tmp_path / "with", files)
    _seed_ccc_settings(with_default)
    payload = _merge(with_default)
    assert "skills" in payload["effective_patterns"]
    assert _mixed(payload) == []

    negated = _git_repo(tmp_path / "negated", files)
    _seed_ccc_settings(negated, extra_excludes=["!keep/me.md"])
    payload = _merge(negated)
    assert "skills" not in payload["effective_patterns"]
    [note] = _mixed(payload)
    assert ".idea/" in note

    without = _git_repo(tmp_path / "without", files)
    _seed_without_dot_default(without)
    payload = _merge(without)
    assert "skills" not in payload["effective_patterns"]
    [note] = _mixed(payload)
    assert ".idea/" in note


def test_os_clutter_files_are_neutral(tmp_path):
    clutter = {"skills/.DS_Store": b"x", "skills/Thumbs.db": b"x", "skills/desktop.ini": b"x"}
    only_clutter = _git_repo(tmp_path / "only", clutter)
    _seed_without_dot_default(only_clutter)
    payload = _merge(only_clutter)
    assert "skills" in payload["effective_patterns"]
    assert _warnings_with(payload, "SKF did not generate") == []

    mixed = _git_repo(tmp_path / "mixed", {**clutter, **MIXED_SKILLS})
    _seed_without_dot_default(mixed)
    [note] = _mixed(_merge(mixed))
    assert "2 entries" in note
    for name in ("DS_Store", "Thumbs", "desktop"):
        assert name not in note


def test_user_folder_entry_is_left_alone_across_toggles(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project)
    prior = tmp_path / "forge-tier.yaml"

    def run():
        payload = _merge(project, prior=prior if prior.exists() else None)
        _record(tmp_path, payload["effective_patterns"])
        assert "skills" not in payload["patterns_removed_list"]
        return payload

    first = run()
    assert "skills" not in first["effective_patterns"]

    # The user excludes the whole folder, as the old warning advised.
    data = _read_settings(project)
    data["exclude_patterns"].append("skills")
    _write_yaml(_settings_path(project), data)
    second = run()
    assert sorted(second["patterns_removed_list"]) == MIXED_SKILLS_PATTERNS
    assert second["patterns_added_list"] == []

    shutil.rmtree(project / "skills" / "vendor-skill")
    third = run()
    _write_files(project, {"skills/vendor-skill/SKILL.md": b"# vendor\n"})
    fourth = run()
    for payload in (second, third, fourth):
        assert "skills" not in payload["effective_patterns"]
        assert _under(payload["effective_patterns"], "skills") == []
        assert _mixed(payload) == [] and _collisions(payload) == []
        assert _warnings_with(payload, "no record of adding it") == []
    assert third["patterns_removed_list"] == [] and fourth["patterns_removed_list"] == []
    assert "skills" in _read_settings(project)["exclude_patterns"]


def test_bare_value_written_after_the_last_saved_record_stays_skf_owned(tmp_path):
    """Setup writes settings.yml before it saves the record: a run stopped in
    between must not turn SKF's own bare value into the user's for good."""
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project)

    # Run 1: a mixed folder, per-entry patterns, record saved.
    first = _merge(project)
    prior = _record(tmp_path, first["effective_patterns"])
    assert _under(first["effective_patterns"], "skills") == MIXED_SKILLS_PATTERNS

    # Run 2: the vendor skill leaves; SKF swaps in the bare value, then the
    # run stops before the record is saved.
    shutil.rmtree(project / "skills" / "vendor-skill")
    second = _merge(project, prior=prior)
    assert second["patterns_added_list"] == ["skills"]
    assert sorted(second["patterns_removed_list"]) == MIXED_SKILLS_PATTERNS

    # Run 3: the vendor skill is back; the stale record still names the
    # per-entry patterns, so the bare value is SKF's and gives way again.
    _write_files(project, {"skills/vendor-skill/SKILL.md": b"# vendor\n"})
    third = _merge(project, prior=prior)
    assert third["patterns_removed_list"] == ["skills"]
    assert sorted(third["patterns_added_list"]) == MIXED_SKILLS_PATTERNS
    [note] = _mixed(third)
    assert "vendor-skill/" in note
    excludes = _read_settings(project)["exclude_patterns"]
    assert "skills" not in excludes
    prior = _record(tmp_path, third["effective_patterns"])

    # Run 4: steady state.
    fourth = _merge(project, prior=prior)
    assert fourth["patterns_added_list"] == [] and fourth["patterns_removed_list"] == []
    assert fourth["effective_patterns"] == third["effective_patterns"]


def test_bare_value_added_beside_recorded_entries_stays_the_users(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project)
    first = _merge(project)
    prior = _record(tmp_path, first["effective_patterns"])
    # The recorded per-entry patterns are still there: the user added `skills`.
    data = _read_settings(project)
    data["exclude_patterns"].append("skills")
    _write_yaml(_settings_path(project), data)
    second = _merge(project, prior=prior)
    assert "skills" not in second["effective_patterns"]
    assert "skills" not in second["patterns_removed_list"]
    assert "skills" in _read_settings(project)["exclude_patterns"]
    assert _mixed(second) == []


def test_stale_check_ignores_the_patterns_of_an_inner_folder(tmp_path):
    record = ["skf/forge-data", "skf/forge-data/n"]
    assert mod._stale_bare_values(["skf"], record, ["skf", "skf/forge-data"]) == set()
    assert mod._stale_bare_values(["skf"], record + ["skf/n"], ["skf", "skf/forge-data"]) == {"skf"}
    assert mod._stale_bare_values(["skf", "skf/n"], record + ["skf/n"],
                                  ["skf", "skf/forge-data"]) == set()


def test_unrecorded_folder_entry_warns_once_without_record(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project, extra_excludes=["skills"])
    first = _merge(project)
    [warning] = _warnings_with(first, "no record of adding it")
    assert warning.startswith("skills_output_folder skills ")
    assert "vendor-skill/" in warning
    assert "skills" not in first["effective_patterns"]
    assert _under(first["effective_patterns"], "skills") == []
    assert "skills" in _read_settings(project)["exclude_patterns"]

    prior = _record(tmp_path, first["effective_patterns"])
    second = _merge(project, prior=prior)
    assert _warnings_with(second, "no record of adding it") == []
    assert second["patterns_removed_list"] == [] and second["patterns_added_list"] == []
    assert "skills" in _read_settings(project)["exclude_patterns"]


def test_folder_free_record_without_legacy_forms_is_trusted(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "skills/n/1.0.0/n/SKILL.md": b"# n\n",
        "forge-data/n/skill-brief.yaml": b"name: n\n",
    }))
    _seed_ccc_settings(project, extra_excludes=["skills", "forge-data"])
    prior = _record(tmp_path, list(mod.ALWAYS_INCLUDE))
    for _ in range(3):
        payload = _merge(project, prior=prior, forge_data="forge-data")
        assert payload["effective_patterns"] == sorted(mod.ALWAYS_INCLUDE)
        assert payload["patterns_removed_list"] == []
        prior = _record(tmp_path, payload["effective_patterns"])
    excludes = _read_settings(project)["exclude_patterns"]
    assert "skills" in excludes and "forge-data" in excludes


def test_no_produced_pattern_negates_or_wildcards_folder_root(tmp_path):
    cases = [
        ("skills", "forge-data", MIXED_SKILLS),
        ("skills", "forge-data", {"forge-data/n/skill-brief.yaml": b"name: n\n",
                                  "forge-data/feasibility-report-x.md": b"# r\n",
                                  "forge-data/pkg/a.py": b"x = 1\n"}),
        ("skf", "skf/forge-data", _marked({"skf/n/1.0.0/n/SKILL.md": b"# n\n",
                                           "skf/forge-data/n/skill-brief.yaml": b"name: n\n",
                                           "skf/forge-data/notes/a.md": b"# a\n"})),
    ]
    for i, (skills, forge, files) in enumerate(cases):
        project = _git_repo(tmp_path / f"repo{i}", files)
        _seed_ccc_settings(project)
        effective = _merge(project, skills=skills, forge_data=forge)["effective_patterns"]
        assert effective
        for p in effective:
            assert not p.startswith("!"), p
            for folder in (skills, forge):
                assert not p.startswith(folder + "/*"), p


def test_effective_patterns_json_is_echo_safe(tmp_path):
    marker = json.dumps(SKF_MARKER).encode("utf-8")
    project = _git_repo(tmp_path / "repo", {
        "skills/.export-manifest.json":
            json.dumps({"exports": {"café": {}, "[x]": {}}}).encode("utf-8"),
        "skills/café/SKILL.md": b"# c\n",
        "skills/café/metadata.json": marker,
        "skills/[x]/SKILL.md": b"# x\n",
        "skills/[x]/metadata.json": marker,
        "skills/vendor/SKILL.md": b"# v\n",
    })
    _seed_ccc_settings(project)
    rc, payload, stderr = _run(project)
    assert rc == 0, stderr
    effective = payload["effective_patterns"]
    assert "skills/[[]x[]]" in effective
    assert [p for p in effective if p.startswith("skills/caf")]
    dumped = json.dumps(effective)
    assert re.search(r"\\[^u]", dumped) is None, dumped
    assert "'" not in dumped


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


# ─── Payload safety of every human-readable string ─────────────────────────


def _payload_unsafe(text: str) -> bool:
    return any(ch in "'\\" or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text)


def _assert_payload_safe(payload: dict) -> None:
    """No `'`, backslash or control character in any string the setup payloads embed."""
    strings = list(payload["warnings"]) + list(payload["effective_patterns"] or [])
    if payload["not_ready_reason"] is not None:
        strings.append(payload["not_ready_reason"])
    for text in strings:
        assert not _payload_unsafe(text), text


def test_no_single_quote_in_any_warning_or_reason(tmp_path, monkeypatch):
    # W1: a foreign root file whose name carries a quote, in a quoted project path.
    project = _git_repo(tmp_path / "o'brien", {"skills/don't.py": b"x = 1\n"})
    _seed_ccc_settings(project)
    payload = _merge(project)
    assert len(_collisions(payload)) == 1
    assert "don`t.py" in _collisions(payload)[0]
    _assert_payload_safe(payload)

    # R1 and W2b: ccc init output carrying a quote.
    def _failing(root):
        return False, "Error: it's broken"

    monkeypatch.setattr(mod, "run_ccc_init", _failing)
    missing = tmp_path / "missing"
    missing.mkdir()
    payload = _merge(missing, allow_ccc_init=True)
    assert "it`s broken" in payload["not_ready_reason"]
    _assert_payload_safe(payload)

    bare = tmp_path / "bare"
    _seed_bare_settings(bare, LEGACY_SKF)
    payload = _merge(bare, allow_ccc_init=True)
    assert len(_warnings_with(payload, "it`s broken")) == 1
    _assert_payload_safe(payload)

    # V7: a folder value carrying a quote.
    quoted = tmp_path / "quoted"
    _seed_ccc_settings(quoted)
    payload = _merge(quoted, skills="bob's")
    assert len(_warnings_with(payload, "single quote")) == 1
    _assert_payload_safe(payload)

    # Malformed YAML on the CLI error path.
    broken = tmp_path / "broken"
    broken.mkdir()
    target = _settings_path(broken)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"exclude_patterns:\n\t- '**/x'\n")
    rc, _, stderr = _run(broken)
    assert rc == 1
    assert "'" not in stderr

    # A mixed folder whose foreign entries carry a quote (and, off Windows, a
    # backslash): the note shows them sanitized.
    files = _marked({"skills/n/1.0.0/n/SKILL.md": b"# n\n", "skills/don't/x.md": b"# x\n"})
    if sys.platform != "win32":
        files["skills/a\\b/x.md"] = b"# x\n"
    mixed = _git_repo(tmp_path / "mixed", files)
    _seed_ccc_settings(mixed)
    payload = _merge(mixed)
    [note] = _mixed(payload)
    assert "don`t/" in note
    if sys.platform != "win32":
        assert "a?b/" in note
    _assert_payload_safe(payload)


def test_payload_safe_rewrites_every_unsafe_character():
    assert mod._payload_safe("it's a\\b\tc\nd\x7fe\udcff") == "it`s a/b?c?d?e?"
    assert mod._payload_safe("caf\u00e9 [x]") == "caf\u00e9 [x]"


# ─── A user `!` entry that cancels an SKF folder exclusion ──────────────────
#
# ccc (0.2.41) walks into an excluded directory when a `!` entry matches it,
# matches the one child name ccc probes it with (so a wildcard child), or
# starts with `<dir>/`; everything below that no other pattern excludes is
# then indexed. The two lists are ccc's own verdicts for a bare `skills`
# pattern (PatternFilePathMatcher.is_dir_included, checked when the helper
# was written).

GETTING_STARTED_DOC = REPO_ROOT / "docs" / "getting-started.md"
CCC_BRIDGE_DOC = REPO_ROOT / "src" / "knowledge" / "ccc-bridge.md"
ONLY_SKF_OUTPUT = _marked({"skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n"})

CANCELS_WHOLE_FOLDER = [
    "!skills", "!skills/", "!skills/installed-tool", "!skills/installed-tool/SKILL.md",
    "!skills/installed-tool/**", "!skills/no-such-path", "!skills/**", "!skills/*.md",
    "!skills//x", "!skill*", "!*", "!**", "!**/", "!**/**/", "!**/skills", "!**/skills/**",
    "!{skills,docs}/x", "!sk{ills,x}/y", "!skills/?", "![!x]kills", "!*/*", "!**/skills/*",
    "!skills?*",
]
LEAVES_FOLDER_EXCLUDED = [
    "!**/SKILL.md", "!**/skills/x", "!**/*.md", "!**/.github/**", "!/skills", "!/skills/x",
    "!./skills/x", "!Skills/x", "!skillsfoo/x", "!skills-old", "!src/generated", "![s]kills/x",
    "!s*/x", "!*/x", "!!skills/x", "!", "!**/kills", "!**/ills/x", "!*/SKILL.md",
    "!**/skills/SKILL.md",
]


def _cancel_warnings(payload: dict, key: str = "skills_output_folder") -> list[str]:
    """The warnings for `key` that name a user `!` entry cancelling an SKF pattern."""
    return [w for w in payload["warnings"]
            if w.startswith(key + " ") and "applies a ! entry against every exclusion" in w]


@pytest.mark.parametrize("entry", CANCELS_WHOLE_FOLDER)
def test_negation_forms_ccc_reads_as_re_opening_the_folder(entry):
    assert mod._negation_reopens(entry, "skills")


@pytest.mark.parametrize("entry", LEAVES_FOLDER_EXCLUDED)
def test_negation_forms_ccc_leaves_excluded(entry):
    assert not mod._negation_reopens(entry, "skills")


def test_negation_backslash_is_read_as_ccc_reads_it_on_this_machine():
    # ccc reads settings.yml where the helper runs, and its glob library takes
    # a backslash as `/` on Windows and as an escape elsewhere: `skills\**`
    # re-opens the folder only on Windows.
    assert mod._negation_reopens("!skills\\**", "skills", backslash_is_slash=True)
    assert not mod._negation_reopens("!skills\\**", "skills", backslash_is_slash=False)
    assert not mod._negation_reopens("!skills\\*", "skills", backslash_is_slash=False)
    assert mod._negation_reopens("!**\\skills", "skills", backslash_is_slash=False)
    assert mod.CCC_BACKSLASH_IS_SLASH is (os.name == "nt")
    assert mod._negation_reopens("!skills\\**", "skills") is (os.name == "nt")


def test_negation_with_many_brace_groups_keeps_the_merge_running(tmp_path):
    many = "!" + "{s}" * 1500 + "/x"  # ccc reads it as sss...s/x
    assert not mod._negation_reopens(many, "skills")
    assert mod._negation_reopens("!skills/" + "{x}" * 1500, "skills")
    project = _git_repo(tmp_path / "repo", ONLY_SKF_OUTPUT)
    _seed_ccc_settings(project, extra_excludes=[many, "!skills/installed-tool"])
    rc, payload, stderr = _run(project)
    assert rc == 0, stderr
    [warning] = _cancel_warnings(payload)
    assert "also lists !skills/installed-tool:" in warning


def test_negation_checks_nested_and_per_entry_targets():
    assert mod._negation_reopens("!out/skills/x", "out/skills")
    assert mod._negation_reopens("!o*", "out/skills")
    assert not mod._negation_reopens("!out/x", "out/skills")
    assert mod._negation_reopens("!skills/mylib/references", "skills/mylib")
    assert mod._negation_reopens("!skills/*", "skills/_batch")
    assert not mod._negation_reopens("!skills/vendor-skill", "skills/mylib")


def test_pattern_path_undoes_class_escapes_and_skips_families():
    assert mod._pattern_path("skills") == "skills"
    assert mod._pattern_path("skills/[[]x[]]") == "skills/[x]"
    assert mod._pattern_path("skills/export-skill-result*.json") is None
    assert mod._pattern_path("forge-data/analyze-source-*") is None


def test_negation_under_a_whole_folder_warns_and_is_kept(tmp_path):
    project = _git_repo(tmp_path / "repo", ONLY_SKF_OUTPUT)
    _seed_ccc_settings(project, extra_excludes=["!skills/installed-tool", "!src/generated"])
    payload = _merge(project)
    assert "skills" in payload["effective_patterns"]
    [warning] = _cancel_warnings(payload)
    assert warning.startswith("skills_output_folder skills is excluded from ccc as one folder")
    assert "so all SKF output in skills is indexed again" in warning
    assert "also lists !skills/installed-tool:" in warning and "!src/generated" not in warning
    assert "Remove that entry" in warning and "twice" in warning and "re-run /skf-setup" in warning
    assert _mixed(payload) == [] and _collisions(payload) == []
    excludes = _read_settings(project)["exclude_patterns"]
    assert "!skills/installed-tool" in excludes and "!src/generated" in excludes
    _assert_payload_safe(payload)


def test_negation_under_the_forge_folder_warns(tmp_path):
    project = _git_repo(tmp_path / "repo", {"forge-data/n/skill-brief.yaml": b"name: n\n"})
    _seed_ccc_settings(project, extra_excludes=["!forge-data/n/evidence-report.md"])
    payload = _merge(project, forge_data="forge-data")
    [warning] = _cancel_warnings(payload, "forge_data_folder")
    assert warning.startswith("forge_data_folder forge-data is excluded from ccc as one folder")
    assert "twice" not in warning
    assert _cancel_warnings(payload) == []


def test_negation_warns_again_once_the_folder_goes_back_to_one_pattern(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project, extra_excludes=["!skills/vendor-skill"])
    prior = _record(tmp_path, [])

    def run():
        payload = _merge(project, prior=prior)
        _record(tmp_path, payload["effective_patterns"])
        return payload

    shared = run()
    assert "skills" not in shared["effective_patterns"]
    assert _cancel_warnings(shared) == []  # it only re-includes the vendor skill

    shutil.rmtree(project / "skills" / "vendor-skill")
    _git(project, "rm", "-r", "-q", "--cached", "skills/vendor-skill")
    whole = run()
    assert whole["patterns_added_list"] == ["skills"]
    [warning] = _cancel_warnings(whole)
    assert "!skills/vendor-skill" in warning and "as one folder" in warning
    assert "!skills/vendor-skill" in _read_settings(project)["exclude_patterns"]


def test_negation_cancelling_an_skf_entry_in_a_shared_folder_warns(tmp_path):
    project = _git_repo(tmp_path / "repo", MIXED_SKILLS)
    _seed_ccc_settings(project, extra_excludes=["!skills/vendor-skill",
                                                "!skills/mylib/1.0.0/mylib/references"])
    payload = _merge(project)
    [note] = _mixed(payload)
    [warning] = _cancel_warnings(payload)
    assert "one SKF entry at a time" in warning
    assert "!skills/mylib/1.0.0/mylib/references" in warning
    assert "!skills/vendor-skill" not in warning


@pytest.mark.parametrize("case", ["bare", "no_negation", "left_out", "user"])
def test_negation_warns_only_where_skf_writes_a_folder_pattern(tmp_path, case):
    files = MODULE_SOURCE if case == "left_out" else ONLY_SKF_OUTPUT
    project = _git_repo(tmp_path / "repo", files)
    extra = {"bare": ["!skills/mine"], "no_negation": [], "left_out": ["!skills/my-agent"],
             "user": ["skills", "!skills/mine"]}[case]
    _seed_ccc_settings(project, extra_excludes=extra)
    prior = _record(tmp_path, list(mod.ALWAYS_INCLUDE)) if case == "user" else None
    payload = _merge(project, prior=prior)
    if case == "bare":
        assert len(_cancel_warnings(payload)) == 1
    else:
        assert _cancel_warnings(payload) == []
    if case == "left_out":
        assert len(_collisions(payload)) == 1
    if case == "user":
        assert "skills" not in payload["effective_patterns"]


def test_negation_warning_lists_three_and_counts_the_rest(tmp_path):
    project = _git_repo(tmp_path / "repo", ONLY_SKF_OUTPUT)
    _seed_ccc_settings(project, extra_excludes=[f"!skills/n{i}" for i in range(5)])
    [warning] = _cancel_warnings(_merge(project))
    assert "also lists !skills/n0, !skills/n1, !skills/n2 and 2 more:" in warning
    assert "Remove those entries" in warning


def test_negation_warning_is_payload_safe(tmp_path):
    project = _git_repo(tmp_path / "repo", ONLY_SKF_OUTPUT)
    _seed_ccc_settings(project, extra_excludes=["!skills/don't", "!skills/a\\b"])
    rc, payload, stderr = _run(project)
    assert rc == 0, stderr
    [warning] = _cancel_warnings(payload)
    assert "also lists !skills/don`t, !skills/a?b:" in warning
    _assert_payload_safe(payload)


HIDDEN_SKILLS = _marked({".claude/skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n"})


@pytest.mark.parametrize("skills,extra,warns", [
    ("skills", ["!skills/x"], True),
    # The user's own `skills/*` still keeps every skill out.
    ("skills", ["skills/*", "!skills/x"], False),
    # ccc's `**/.*` still keeps .claude/skills/<skill> out.
    (".claude/skills", ["!.claude/skills/x"], False),
    # .claude itself stays excluded, so ccc never gets to .claude/skills.
    (".claude/skills", ["!**/skills"], False),
    (".claude/skills", ["!.claude/skills/**"], True),
    (".claude/skills", ["!.claude/skills/mylib/**"], True),
    # It re-opens .claude/skills/mylib, but `**/.*` keeps its version folder out.
    (".claude/skills", ["!.claude/skills/mylib"], False),
], ids=["bare", "user-glob-below", "hidden-parent", "parent-not-reopened", "hidden-reopened",
        "skill-reopened", "skill-folder-only"])
def test_negation_warns_only_when_ccc_walks_down_to_skf_output(tmp_path, skills, extra, warns):
    project = _git_repo(tmp_path / "repo", HIDDEN_SKILLS if skills != "skills" else ONLY_SKF_OUTPUT)
    _seed_ccc_settings(project, extra_excludes=extra)
    payload = _merge(project, skills=skills)
    assert skills in payload["effective_patterns"]
    assert len(_cancel_warnings(payload)) == int(warns)


@pytest.mark.parametrize("key,folder,dirs,extra,warns", [
    ("skills_output_folder", "skills", [], ["!skills/x"], True),
    ("skills_output_folder", "skills", ["skills/a/b"], ["!skills/x"], True),
    ("forge_data_folder", "forge-data", [], ["!forge-data/x"], True),
    # The user's own `skills/*` keeps what SKF writes there later out.
    ("skills_output_folder", "skills", [], ["skills/*", "!skills/x"], False),
], ids=["absent", "empty-folders", "forge-absent", "user-glob-below"])
def test_negation_warns_before_skf_writes_any_output(tmp_path, key, folder, dirs, extra, warns):
    # A first setup run: git lists no SKF file below the folder yet, so the
    # check falls back to the child ccc probes an excluded folder with.
    project = _git_repo(tmp_path / "repo")
    for d in dirs:
        (project / d).mkdir(parents=True)
    _seed_ccc_settings(project, extra_excludes=extra)
    kw = {"skills": folder} if key == "skills_output_folder" else {"forge_data": folder}
    payload = _merge(project, **kw)
    assert folder in payload["effective_patterns"]
    got = _cancel_warnings(payload, key)
    assert len(got) == int(warns)
    if warns:
        assert "as one folder" in got[0]


def test_negation_warning_says_all_only_when_every_skf_entry_is_back(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        ".github/skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n",
        ".github/skills/other/1.0.0/other/SKILL.md": b"# other\n",
    }))
    _seed_ccc_settings(project, extra_excludes=["!.github/skills/mylib/**"])
    [warning] = _cancel_warnings(_merge(project, skills=".github/skills"))
    assert "so some SKF output in .github/skills is indexed again" in warning
    assert "put it in a folder of its own there" in warning
    _seed_ccc_settings(project, extra_excludes=["!.github/skills/**"])
    [warning] = _cancel_warnings(_merge(project, skills=".github/skills"))
    assert "so all SKF output in .github/skills is indexed again" in warning


def test_negation_in_an_always_excluded_folder_offers_no_folder_of_its_own(tmp_path):
    project = _git_repo(tmp_path / "repo", _marked({
        "_bmad-output/skills/mylib/1.0.0/mylib/SKILL.md": b"# mylib\n",
        "_bmad-output/skills/mine/notes.md": b"# mine\n",
    }))
    _seed_ccc_settings(project, extra_excludes=["!_bmad-output/skills/mine"])
    for _ in range(2):  # the warning repeats on every run
        payload = _merge(project, skills="_bmad-output/skills")
        assert _mixed(payload) == []
        [warning] = _cancel_warnings(payload)
        assert "as one folder" in warning and "is indexed again" in warning
        assert "SKF always keeps _bmad-output out of ccc" in warning
        assert "a folder of its own" not in warning and "re-run /skf-setup" not in warning


def test_docs_warn_against_negations_in_skf_folders():
    text = GETTING_STARTED_DOC.read_text(encoding="utf-8")
    para = next(p for p in text.split("\n\n") if "Do not add a `!` entry" in p)
    for needle in ("`skills_output_folder`", "`forge_data_folder`", "a folder of its own",
                   "re-run `/skf-setup`", "warns on every run", "a `/*` or `/**` form",
                   "setup always excludes, such as `_bmad-output` or `.claude`"):
        assert needle in para, needle
    bridge = CCC_BRIDGE_DOC.read_text(encoding="utf-8")
    line = next(l for l in bridge.splitlines() if l.startswith("SKF never writes a `!` negation"))
    for needle in ("`{forge_data_folder}`", "matches any name one level inside it",
                   "`*/x` is not one", "no other pattern excludes", "warns on every run",
                   "back to the bare pattern", "`warnings`"):
        assert needle in line, needle
    # `!*/x` matches skills/x, a path one level inside skills, yet ccc keeps skills out.
    assert "a path one level inside it" not in line
    assert "A `!` entry of the user's cancels an SKF pattern the same way" in mod.__doc__
    assert "a path one level inside it" not in " ".join(mod.__doc__.split())


def test_docstring_says_where_the_project_root_placeholder_applies():
    doc = " ".join(mod.__doc__.split())
    for sentence in (
        "when a warning or `not_ready_reason` names the project root in SKF's own words, "
        "it writes the literal `{project-root}` placeholder, never the absolute path.",
        "Setup's step 4 banner renders a warning's placeholder like its own "
        "`{project-root}` paths, and the envelope keeps it verbatim.",
        "The unresolved-placeholder refusal names the placeholder this script resolves in words "
        '("the project-root placeholder"), so a `{project-root}` in SKF\'s own words always means '
        "the project root.",
        "Output and errors quoted from `ccc init` or git can carry paths of their own, "
        "the project root included.",
        "Error messages on stderr name absolute paths.",
    ):
        assert sentence in doc, sentence


# ─── Index build (--build-index) and the result file (--result-to) ─────────


class _FakeCcc:
    """Stand-in for _run_ccc: each `ccc status` call returns the next output."""

    def __init__(self, statuses, index_ok=True, index_output="Index stats:"):
        self.statuses = list(statuses)
        self.index_ok = index_ok
        self.index_output = index_output
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, root, args, timeout):
        self.calls.append(args)
        if args == ("index",):
            return self.index_ok, self.index_output
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return (True, status) if isinstance(status, str) else status


def _status(files: int | None, in_progress=False) -> str:
    lines = ["Project: /p", "Settings: /p/.cocoindex_code/settings.yml"]
    if in_progress:
        lines.append("Indexing in progress: 3 files listed | 3 added, 0 deleted, 0 reprocessed, 0 unchanged, error: 0")
    lines.append("")
    lines += ["Index not created yet."] if files is None else ["Index stats:", "  Chunks: 9", f"  Files:  {files}",
                                                             "  Languages:", "    python: 9 chunks"]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("output,count", [
    (_status(12), 12), (_status(0), 0), (_status(None), None), ("", None),
    ("Index stats:\n  Chunks: 2\n  Files:  2\n", 2),
], ids=["twelve", "zero", "not-created", "empty", "index-output"])
def test_parse_status_file_count(output, count):
    assert mod.parse_status_file_count(output) == count


def test_build_index_runs_ccc_index_and_stamps_the_clock(monkeypatch, tmp_path):
    fake = _FakeCcc([_status(12)])
    monkeypatch.setattr(mod, "_run_ccc", fake)
    before = mod.datetime.now(mod.timezone.utc).replace(microsecond=0)
    warnings: list[str] = []
    index = mod.build_index(tmp_path, "/raw/root/", "index", None, None, warnings)
    assert fake.calls == [("index",), ("status",)]
    assert index["status"] == "created" and index["file_count"] == 12 and index["failed_reason"] is None
    assert index["indexed_path"] == "/raw/root/"
    stamped = mod.datetime.fromisoformat(index["last_indexed"])
    assert stamped.utcoffset().total_seconds() == 0
    assert before <= stamped <= mod.datetime.now(mod.timezone.utc)
    assert warnings == []


def test_build_index_waits_out_a_running_pass(monkeypatch, tmp_path):
    fake = _FakeCcc([_status(5, in_progress=True), _status(7, in_progress=True), _status(9)])
    monkeypatch.setattr(mod, "_run_ccc", fake)
    warnings: list[str] = []
    index = mod.build_index(tmp_path, "/p", "index", None, None, warnings)
    assert fake.calls == [("index",), ("status",), ("index",), ("status",), ("index",), ("status",)]
    assert (index["status"], index["file_count"], warnings) == ("created", 9, [])


def test_build_index_stops_rerunning_after_three_passes(monkeypatch, tmp_path):
    fake = _FakeCcc([_status(5, in_progress=True)])
    monkeypatch.setattr(mod, "_run_ccc", fake)
    warnings: list[str] = []
    index = mod.build_index(tmp_path, "/p", "index", None, None, warnings)
    assert fake.calls.count(("index",)) == 1 + mod.CCC_INDEX_RERUNS
    assert (index["status"], index["file_count"]) == ("created", 5)
    assert warnings and "in progress" in warnings[0]


@pytest.mark.parametrize("fake,reason", [
    (_FakeCcc([_status(3)], index_ok=False, index_output="ccc index exited 1: it's broken"),
     "ccc index exited 1: it`s broken"),
    (_FakeCcc([(False, "ccc status exited 2: daemon down")]), "ccc status exited 2: daemon down"),
    (_FakeCcc([_status(None)]), "ccc index finished, but ccc status shows no index"),
    (_FakeCcc([_status(0)]), "ccc index finished, but ccc status counts no indexed file"),
], ids=["index-fails", "status-fails", "no-index", "zero-files"])
def test_build_index_failures_carry_a_payload_safe_reason(monkeypatch, tmp_path, fake, reason):
    monkeypatch.setattr(mod, "_run_ccc", fake)
    index = mod.build_index(tmp_path, "/p", "index", None, None, [])
    assert index == {"status": "failed", "indexed_path": None, "last_indexed": None, "file_count": None,
                     "failed_reason": reason}


def test_build_index_acts_on_the_other_actions_without_running_ccc(monkeypatch, tmp_path):
    def forbid(*args, **kwargs):
        raise AssertionError("ccc must not run for keep, skip or fail")

    monkeypatch.setattr(mod, "_run_ccc", forbid)
    prior = _write_yaml(tmp_path / "forge-tier.yaml", {"ccc_index": {
        "status": "created", "indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00", "file_count": 42}})
    keep = mod.build_index(tmp_path, "/p", "keep", None, prior, [])
    assert keep == {"status": "fresh", "indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00",
                    "file_count": 42, "failed_reason": None}
    # An unquoted timestamp that YAML reads as a datetime, and a count that is no integer.
    (tmp_path / "forge-tier.yaml").write_text(
        "ccc_index:\n  last_indexed: 2026-10-01 10:00:00+00:00\n  file_count: true\n", encoding="utf-8")
    keep = mod.build_index(tmp_path, "/p", "keep", None, prior, [])
    assert keep["last_indexed"] == "2026-10-01T10:00:00+00:00" and keep["file_count"] is None
    assert mod.build_index(tmp_path, "/p", "keep", None, tmp_path / "missing.yaml", [])["file_count"] is None
    assert mod.build_index(tmp_path, "/p", "skip", None, prior, [])["status"] == "skipped"
    failed = mod.build_index(tmp_path, "/p", "fail", "no settings.yml", prior, [])
    assert (failed["status"], failed["failed_reason"]) == ("failed", "no settings.yml")


def test_cli_build_index_and_result_to_hold_the_same_result(tmp_project, tmp_path):
    """No settings.yml and --no-ccc-init: index_action fail, so no ccc runs."""
    result_to = tmp_path / "run" / "ccc-exclusions.json"
    rc, payload, stderr = _run(tmp_project, extra_args=("--build-index", "--result-to", str(result_to)))
    assert rc == 0, stderr
    assert set(payload) == V2_KEYS | {"index"}
    assert payload["index_action"] == "fail"
    assert payload["index"]["status"] == "failed"
    assert payload["index"]["failed_reason"] == payload["not_ready_reason"]
    assert json.loads(result_to.read_text(encoding="utf-8")) == payload


def test_cli_result_to_holds_the_error_of_a_failed_run(tmp_path):
    result_to = tmp_path / "ccc-exclusions.json"
    rc, payload, stderr = _run(tmp_path / "missing", extra_args=("--build-index", "--result-to", str(result_to)))
    assert rc == 1 and payload is None
    error = json.loads(result_to.read_text(encoding="utf-8"))
    assert error == json.loads(stderr)
    assert error["status"] == "error" and "--project-root is not a directory" in error["message"]


def test_cli_config_reads_both_folder_values(tmp_project, tmp_path):
    config = _write_yaml(tmp_path / "config.yaml", {"skills_output_folder": "{project-root}/skills",
                                                     "forge_data_folder": "{project-root}/forge-data"})
    _seed_ccc_settings(tmp_project)
    argv = [sys.executable, str(SCRIPT_PATH), "--project-root", str(tmp_project), "--config", str(config),
            "--no-ccc-init"]
    result = subprocess.run(argv, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    by_flags = _run(tmp_project, skills="{project-root}/skills", forge_data="{project-root}/forge-data")[1]
    assert payload["effective_patterns"] == by_flags["effective_patterns"]
    assert {"skills", "forge-data"} <= set(payload["effective_patterns"])


@pytest.mark.parametrize("extra,code,needle", [
    (("--config", "{config}", "--skills-output-folder", "skills"), 2, "--config replaces"),
    (("--config", "{missing}"), 1, "--config does not exist"),
    (("--config", "{list}"), 1, "--config is not a YAML mapping"),
], ids=["with-folder-flag", "missing", "not-a-mapping"])
def test_cli_config_errors(tmp_project, tmp_path, extra, code, needle):
    config = _write_yaml(tmp_path / "config.yaml", {"skills_output_folder": "skills"})
    listed = tmp_path / "list.yaml"
    listed.write_text("- skills\n", encoding="utf-8")
    names = {"{config}": str(config), "{missing}": str(tmp_path / "nope.yaml"), "{list}": str(listed)}
    argv = [sys.executable, str(SCRIPT_PATH), "--project-root", str(tmp_project), "--no-ccc-init",
            *(names.get(a, a) for a in extra)]
    result = subprocess.run(argv, capture_output=True, timeout=60)
    assert result.returncode == code
    assert needle in json.loads(result.stderr)["message"]


def test_cli_clone_root_refuses_build_index(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--clone-root", str(clone), "--build-index"],
                            capture_output=True, timeout=60)
    assert result.returncode == 2
    assert "--build-index" in json.loads(result.stderr)["message"]


def test_main_records_the_project_root_as_given(tmp_project, monkeypatch, capsys):
    """skf-detect-tools.py compares the next run's --project-root with the
    recorded indexed_path by exact string, so the value is kept as given."""
    _seed_ccc_settings(tmp_project)
    monkeypatch.setattr(mod, "_run_ccc", _FakeCcc([_status(4)]))
    raw = str(tmp_project) + os.sep
    monkeypatch.setattr(sys, "argv", ["merge", "--project-root", raw, "--skills-output-folder", "skills",
                                      "--forge-data-folder", "forge-data", "--index-fresh", "false",
                                      "--no-ccc-init", "--build-index"])
    mod.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["index_action"] == "index"
    assert payload["index"]["indexed_path"] == raw and payload["index"]["file_count"] == 4


# ─── Prose pins on the step files that consume the helper output ────────────


# What step 1b's result file feeds, and the consumer that reads each field:
# no step binds or re-types any of them (W2 handoff, #592).
RESULT_CONSUMERS = {
    "written": "emit", "patterns_added": "emit", "patterns_removed": "emit", "gitignore_updated": "emit",
    "warnings": "emit", "index": "emit and write-tools", "effective_patterns": "write-tools",
}
FORGE_TIER_RW = REPO_ROOT / "src" / "shared" / "scripts" / "skf-forge-tier-rw.py"
_rw_spec = importlib.util.spec_from_file_location("skf_forge_tier_rw", FORGE_TIER_RW)
forge_tier_rw = importlib.util.module_from_spec(_rw_spec)
assert _rw_spec.loader is not None
_rw_spec.loader.exec_module(forge_tier_rw)


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)


def test_ccc_index_step_stages_every_consumed_field_by_file(tmp_path):
    """Step 1b writes the helper's result to the run folder and binds none of
    its fields; the emitter and write-tools read each one from that file."""
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    assert "\u2190" not in text
    for field in RESULT_CONSUMERS:
        assert f"`{{{field}}}`" not in text and f"← `{field}`" not in text, field
    result = {"status": "ok", "written": True, "patterns_added": 2, "patterns_removed": 1, "gitignore_updated": True,
              "warnings": ["a note"], "effective_patterns": ["**/_bmad", "skills/[[]x[]]"], "index_action": "index",
              "index": {"status": "created", "indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00",
                        "file_count": 7, "failed_reason": None}}
    folded = emit.fold_staged({}, {emit.STAGED_CCC: result})
    assert (folded["settings_yml_written"], folded["settings_yml_patterns_added"],
            folded["settings_yml_patterns_removed"], folded["gitignore_updated"],
            folded["ccc_exclusion_warnings"]) == (True, 2, 1, True, ["a note"])
    assert folded["ccc_index"] == {"status": "created", "indexed_path": "/p", "file_count": 7}
    staged = tmp_path / "ccc-exclusions.json"
    staged.write_text(json.dumps(result), encoding="utf-8")
    ccc_index = forge_tier_rw._staged_ccc_index(staged)
    # The ownership record passes verbatim, character classes included.
    assert ccc_index["exclude_patterns"] == ["**/_bmad", "skills/[[]x[]]"]
    assert (ccc_index["status"], ccc_index["last_indexed"], ccc_index["file_count"]) == (
        "created", "2026-10-01T10:00:00+00:00", 7)


def test_ccc_index_step_invocation_passes_record_and_index_flags():
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    [invocation] = [b for b in _bash_blocks(text) if "{mergeCccExclusionsHelper}" in b]
    for flag in ("--config", "--prior-state-from", "--index-fresh", "--skip-index", "--build-index",
                 '--result-to "{run_dir}/ccc-exclusions.json"'):
        assert flag in invocation, flag
    for gone in ("--no-ccc-init", "--skills-output-folder", "--forge-data-folder"):
        assert gone not in invocation, gone


def test_ccc_index_step_never_runs_ccc_init():
    text = CCC_INDEX_STEP.read_text(encoding="utf-8")
    blocks = _bash_blocks(text)
    assert blocks
    for block in blocks:
        assert "ccc init" not in block


def test_ccc_index_step_runs_no_ccc_command_itself():
    """The helper runs `ccc index`, reads `ccc status` and stamps the time."""
    for block in _bash_blocks(CCC_INDEX_STEP.read_text(encoding="utf-8")):
        assert not re.search(r"(^|&&\s*)ccc ", block, re.MULTILINE), block


def test_index_build_documents_every_index_action():
    doc = mod.__doc__[mod.__doc__.index("Index build (--build-index)"):mod.__doc__.index("Output (single JSON")]
    for action in mod.INDEX_ACTIONS:
        assert re.search(rf"^  {action} ", doc, re.MULTILINE), action


def test_record_kept_when_step_does_not_reconcile():
    """Without ccc the step stages nothing, and write-tools keeps the record:
    the step no longer restates step 2's handling of a missing file."""
    first = CCC_INDEX_STEP.read_text(encoding="utf-8").split("### 1. Check Eligibility", 1)[1]
    assert "step 2 records" not in first.split("###", 1)[0]
    assert forge_tier_rw._staged_ccc_index(None) == {
        "indexed_path": None, "last_indexed": None, "file_count": None, "exclude_patterns": None,
        "status": "none"}
    # With ccc available the helper ran, so a missing file is a failed preparation.
    assert forge_tier_rw._staged_ccc_index(None, True)["status"] == "failed"
    assert forge_tier_rw._staged_ccc_index(None, True)["exclude_patterns"] is None


def test_a_stopped_index_still_leaves_this_runs_record(tmp_project, tmp_path, monkeypatch):
    """settings.yml is rewritten before `ccc index` runs, which can take an
    hour: --result-to already holds this run's record when a host stops the
    call there, so write-tools records the patterns settings.yml now holds,
    and the index as failed."""
    _seed_ccc_settings(tmp_project)
    result_to = tmp_path / "run" / "ccc-exclusions.json"

    def stopped(root, args, timeout):
        if args == ("index",):
            raise KeyboardInterrupt  # the host stops the call during `ccc index`
        raise AssertionError(f"ccc {args} must not run")

    monkeypatch.setattr(mod, "_run_ccc", stopped)
    monkeypatch.setattr(sys, "argv", ["merge", "--project-root", str(tmp_project), "--skills-output-folder",
                                      "skills", "--forge-data-folder", "forge-data", "--index-fresh", "false",
                                      "--no-ccc-init", "--build-index", "--result-to", str(result_to)])
    with pytest.raises(KeyboardInterrupt):
        mod.main()
    staged = json.loads(result_to.read_text(encoding="utf-8"))
    assert staged["status"] == "ok" and staged["index_action"] == "index"
    assert staged["index"] == {"status": "failed", "indexed_path": None, "last_indexed": None,
                               "file_count": None, "failed_reason": mod.INDEX_UNFINISHED}
    patterns = staged["effective_patterns"]
    assert patterns and set(patterns) <= set(yaml.safe_load(_settings_path(tmp_project).read_text(
        encoding="utf-8"))["exclude_patterns"])
    detect = tmp_path / "run" / "detect-tools.json"
    detect.write_text(json.dumps({"tools": {"ccc": {"available": True, "daemon": "healthy"}},
                                  "tier": {"calculated": "Forge+"}}), encoding="utf-8")
    target = tmp_path / "forge-tier.yaml"
    done = subprocess.run([sys.executable, str(FORGE_TIER_RW), "write-tools", "--target", str(target),
                           "--detect-from", str(detect), "--ccc-from", str(result_to)],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    recorded = yaml.safe_load(target.read_text(encoding="utf-8"))["ccc_index"]
    assert (recorded["status"], recorded["exclude_patterns"]) == ("failed", patterns)
    folded = emit.fold_staged({}, {emit.STAGED_CCC: staged})
    assert folded["ccc_index"]["status"] == "failed"
    assert folded["ccc_indexing_failed_reason"] == mod.INDEX_UNFINISHED


def test_a_finished_index_replaces_the_interim_result(tmp_project, tmp_path, monkeypatch, capsys):
    _seed_ccc_settings(tmp_project)
    result_to = tmp_path / "ccc-exclusions.json"
    seen: list[dict] = []
    fake = _FakeCcc([_status(4)])

    def watching(root, args, timeout):
        if args == ("index",):
            seen.append(json.loads(result_to.read_text(encoding="utf-8")))
        return fake(root, args, timeout)

    monkeypatch.setattr(mod, "_run_ccc", watching)
    monkeypatch.setattr(sys, "argv", ["merge", "--project-root", str(tmp_project), "--skills-output-folder",
                                      "skills", "--forge-data-folder", "forge-data", "--index-fresh", "false",
                                      "--no-ccc-init", "--build-index", "--result-to", str(result_to)])
    mod.main()
    assert [s["index"]["failed_reason"] for s in seen] == [mod.INDEX_UNFINISHED]
    final = json.loads(result_to.read_text(encoding="utf-8"))
    assert final == json.loads(capsys.readouterr().out)
    assert (final["index"]["status"], final["index"]["file_count"]) == ("created", 4)
    assert final["effective_patterns"] == seen[0]["effective_patterns"]


def _setup_banner(**over) -> list[str]:
    """Setup's FORGE STATUS banner for a same-tier Forge+ re-run with ccc, as render-report prints it."""
    payload = {
        "project_root": "/p", "config_path": "/p/_bmad/_memory/forger-sidecar/forge-tier.yaml",
        "forge_data_folder": "/p/forge-data", "tier": "Forge+", "previous_tier": "Forge+",
        "tools": {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": {"available": True, "daemon": "healthy"}},
        "previous_tools": {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": True},
        "ccc_index": {"status": "fresh", "indexed_path": "/p", "file_count": 3},
        "settings_yml_written": False,
        "qmd_status": "absent", "hygiene_result": "skipped", "error": None,
    }
    payload.update(over)
    return emit.render_report(payload, emit.load_tier_rules(TIER_RULES))


def _index(status: str) -> dict:
    checked = status in ("fresh", "created")
    return {"status": status, "indexed_path": "/p" if checked else None, "file_count": 3 if checked else None}


INDEX_STATUSES = ("fresh", "created", "skipped", "failed", "none")


def test_report_shows_removed_count_notes_and_gitignore():
    lines = _setup_banner(settings_yml_written=True, settings_yml_patterns_added=3, settings_yml_patterns_removed=2,
                          gitignore_updated=True, ccc_exclusion_warnings=["skills_output_folder note"])
    assert ("  - .cocoindex_code/settings.yml: /p/.cocoindex_code/settings.yml (3 SKF exclusion pattern(s) "
            "merged, 2 stale SKF pattern(s) removed)") in lines
    assert "  CCC exclusion notes:" in lines and "  - skills_output_folder note" in lines
    assert "  - .gitignore: /p/.gitignore (`/.cocoindex_code/` added by `ccc init`)" in lines


# What a same-tier closing line may claim, and the payload value that backs it.
CLOSING_CLAIMS = {
    "ccc settings were left untouched": lambda run: run["settings_yml_written"] is False,
    "the ccc index was already current": lambda run: run["ccc_index"]["status"] == "fresh",
    "the ccc index was not checked (--ccc-skip-index)": lambda run: run["ccc_index"]["status"] == "skipped",
}


def _same_tier_closing_lines(lines: list[str]) -> list[str]:
    """The lines under the same-tier message, up to the blank line that ends its block."""
    same = "  " + emit.load_tier_rules(TIER_RULES)["same"].replace("{current}", "Forge+")
    if same not in lines:
        return []
    start = lines.index(same) + 1
    return lines[start:lines.index("", start)]


@pytest.mark.parametrize("status", INDEX_STATUSES)
@pytest.mark.parametrize("prior_fresh", [True, False], ids=["prior-fresh", "prior-stale"])
def test_report_calls_the_index_current_only_after_checking_it(status, prior_fresh):
    # Only this run's index status backs the claim: the prior record's
    # freshness, which the payload may also carry, never does.
    lines = _setup_banner(ccc_index=_index(status), ccc_index_fresh=prior_fresh,
                          previous_ccc_index_status="fresh" if prior_fresh else "failed")
    claims = [line for line in lines if "already current" in line.lower() or "up to date" in line.lower()]
    assert bool(claims) == (status == "fresh"), claims
    if status == "fresh":
        assert len(claims) == 2, claims


def test_report_same_tier_closing_lines_claim_only_what_they_check():
    shown = set()
    for settings, status in itertools.product((False, True), INDEX_STATUSES):
        run = {"settings_yml_written": settings, "ccc_index": _index(status)}
        closing = _same_tier_closing_lines(_setup_banner(**run))
        for line in closing:
            text = line.lower()
            for claim, backed in CLOSING_CLAIMS.items():
                assert claim not in text or backed(run), (claim, run)
            # The banner can list removed collections, exclusion notes or
            # forge-tier.yaml above this line, so it never sums the run up.
            for summary in ("nothing changed", "you're good"):
                assert summary not in text, line
            if status == "none":
                assert "index" not in text, line
        if closing:
            shown.add(status)
    # Setup never writes preferences.yaml, so no line says it left them alone.
    assert shown == {"fresh", "skipped"}


def test_report_skip_lane_and_exclusion_notes_wording():
    [skipped] = [line for line in _setup_banner(ccc_index=_index("skipped"))
                 if line.startswith("  skipped (--ccc-skip-index)")]
    assert "without --ccc-skip-index to build or refresh the index" in skipped
    refusal = mod.validate_config_value("skills_output_folder", "{output_folder}/skills")[1]
    notes = ["add /.cocoindex_code/ to {project-root}/.gitignore", "ccc init: /elsewhere/x is read-only", refusal]
    lines = _setup_banner(ccc_exclusion_warnings=notes)
    # SKF's own placeholder shows as the project root, like the banner's own paths.
    assert "  - add /.cocoindex_code/ to /p/.gitignore" in lines
    # Text quoted from ccc or git, and the refusal, which names the placeholder in words, as they are.
    assert "  - ccc init: /elsewhere/x is read-only" in lines
    assert f"  - {refusal}" in lines and "{project-root}" not in refusal


def test_report_envelope_forwards_exclusion_warnings_verbatim():
    # The banner resolves an SKF-worded {project-root}; the envelope keeps it.
    # report.md no longer stages the notes: the emitter reads them from step
    # 1b's result file, so no hand copy can resolve or drop the placeholder.
    note = "add /.cocoindex_code/ to {project-root}/.gitignore"
    folded = emit.fold_staged({}, {emit.STAGED_CCC: {"status": "ok", "warnings": [note], "index": {
        "status": "fresh", "indexed_path": "/p", "file_count": 3}}})
    envelope = emit.assemble_envelope({
        "tier": "Forge+", "previous_tier": "Forge+", "config_path": "/p/_bmad/_memory/forger-sidecar/forge-tier.yaml",
        "tools": {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": True}, "error": None, **folded,
    })
    assert note in envelope["skf_setup"]["warnings"]
    text = REPORT_STEP.read_text(encoding="utf-8")
    for gone in ("ccc_exclusion_warnings", "exclusion notes"):
        assert gone not in text, gone


# ─── Clone mode: a workspace clone's settings.yml (create-skill) ────────────

CLONE_KEYS = {
    "status", "version", "settings_yml_path", "settings_yml_existed", "ccc_init",
    "settings_ready", "not_ready_reason", "patterns_added", "patterns_added_list",
    "patterns_already_present", "includes_added_list", "includes_covered_list", "written",
    "warnings",
}


@pytest.fixture
def tmp_clone(tmp_path):
    clone = tmp_path / "ws" / "repos" / "github.com" / "acme" / "lib"
    clone.mkdir(parents=True)
    return clone


def _run_clone(clone: Path, *extra: str, ccc_init: bool = False) -> tuple[int, dict, str]:
    """Run clone mode as a subprocess; with --no-ccc-init unless ccc_init is set."""
    argv = [sys.executable, str(SCRIPT_PATH), "--clone-root", str(clone), *extra]
    if not ccc_init:
        argv.append("--no-ccc-init")
    env = {k: v for k, v in os.environ.items() if k not in mod.GIT_LOCATION_VARS}
    result = subprocess.run(argv, capture_output=True, timeout=60, env=env)
    stdout = result.stdout.decode("utf-8")
    payload = json.loads(stdout) if stdout.strip() else None
    return result.returncode, payload, result.stderr.decode("utf-8", errors="replace")


def test_clone_excludes_use_the_double_star_form():
    """ccc matches `**/build` at any depth; a trailing-slash form such as `build/` matches nothing."""
    assert len(mod.CLONE_EXCLUDES) == len(set(mod.CLONE_EXCLUDES))
    for entry in mod.CLONE_EXCLUDES:
        assert re.fullmatch(r"\*\*/[A-Za-z0-9_.-]+", entry), entry
    assert {"**/build", "**/out", "**/node_modules", "**/.git", "**/.venv"} <= set(mod.CLONE_EXCLUDES)
    assert not set(mod.CLONE_EXCLUDES) & set(mod.ALWAYS_INCLUDE), "SKF's own folders are setup mode's"


def test_clone_merge_appends_missing_exclusions_and_keeps_every_entry(tmp_clone):
    target = _seed_ccc_settings(tmp_clone, extra_excludes=["**/my-own", "**/out"],
                                extra_keys={"language_overrides": {"x": "y"}})
    payload = mod.run_clone_merge(tmp_clone, allow_ccc_init=False)
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    kept = CCC_DEFAULTS + ["**/my-own", "**/out"]
    missing = [p for p in mod.CLONE_EXCLUDES if p not in kept]
    assert data["exclude_patterns"] == kept + missing
    assert data["include_patterns"] == CCC_INCLUDES
    assert data["language_overrides"] == {"x": "y"}
    assert payload["patterns_added_list"] == missing
    assert payload["patterns_added"] == len(missing)
    assert payload["patterns_already_present"] == len(mod.CLONE_EXCLUDES) - len(missing)
    assert (payload["written"], payload["settings_ready"], payload["ccc_init"]) == (True, True, "not_needed")
    assert payload["includes_added_list"] == [] and payload["includes_covered_list"] == []


def test_clone_merge_twice_changes_nothing_the_second_time(tmp_clone):
    target = _seed_ccc_settings(tmp_clone)
    mod.run_clone_merge(tmp_clone, allow_ccc_init=False)
    before = target.read_bytes()
    payload = mod.run_clone_merge(tmp_clone, ["py"], allow_ccc_init=False)
    assert payload["written"] is False
    assert payload["patterns_added_list"] == [] and payload["includes_covered_list"] == ["py"]
    assert target.read_bytes() == before


def test_clone_merge_adds_nothing_to_a_file_without_an_exclude_list(tmp_clone):
    target = _write_yaml(_settings_path(tmp_clone), {"include_patterns": ["**/*.py"]})
    before = target.read_bytes()
    payload = mod.run_clone_merge(tmp_clone, allow_ccc_init=False)
    assert payload["written"] is False and payload["patterns_added_list"] == []
    assert _warnings_with(payload, "no exclude_patterns list")
    assert target.read_bytes() == before


def test_clone_merge_runs_ccc_init_in_the_clone_when_settings_are_missing(tmp_clone, fake_init):
    payload = mod.run_clone_merge(tmp_clone)
    assert fake_init.calls == [tmp_clone]
    assert (payload["ccc_init"], payload["settings_yml_existed"], payload["written"]) == ("created", False, True)
    data = _read_settings(tmp_clone)
    assert data["exclude_patterns"][:len(CCC_DEFAULTS)] == CCC_DEFAULTS
    assert set(mod.CLONE_EXCLUDES) <= set(data["exclude_patterns"])


def test_clone_merge_is_not_ready_when_ccc_init_writes_no_settings(tmp_clone, failing_init):
    payload = mod.run_clone_merge(tmp_clone)
    assert failing_init.calls == [tmp_clone]
    assert (payload["settings_ready"], payload["ccc_init"], payload["written"]) == (False, "failed", False)
    assert "ccc init did not create" in payload["not_ready_reason"]
    assert "'" not in payload["not_ready_reason"]
    assert not _settings_path(tmp_clone).exists()


def test_clone_merge_without_ccc_init_leaves_missing_settings_missing(tmp_clone):
    rc, payload, stderr = _run_clone(tmp_clone)
    assert rc == 0, stderr
    assert (payload["settings_ready"], payload["ccc_init"]) == (False, "not_needed")
    assert "--no-ccc-init" in payload["not_ready_reason"]
    assert not _settings_path(tmp_clone).exists()


def test_clone_include_ext_adds_only_the_extensions_no_entry_matches(tmp_clone):
    target = _write_yaml(_settings_path(tmp_clone), {
        "exclude_patterns": list(CCC_DEFAULTS),
        "include_patterns": ["**/*.py", "**/*.{ex,exs}", "src/*.rs"],
    })
    payload = mod.run_clone_merge(tmp_clone, ["ex", "go", "py", "rs", "go"], allow_ccc_init=False)
    # `src/*.rs` matches no nested file, and a repeated extension is added once.
    assert payload["includes_added_list"] == ["**/*.go", "**/*.rs"]
    assert payload["includes_covered_list"] == ["ex", "py"]
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["include_patterns"] == ["**/*.py", "**/*.{ex,exs}", "src/*.rs", "**/*.go", "**/*.rs"]
    assert "- '**/*.go'" in target.read_text(encoding="utf-8").splitlines()


def test_clone_include_ext_adds_nothing_to_a_file_without_an_include_list(tmp_clone):
    target = _seed_bare_settings(tmp_clone, list(CCC_DEFAULTS) + list(mod.CLONE_EXCLUDES))
    before = target.read_bytes()
    payload = mod.run_clone_merge(tmp_clone, ["ex"], allow_ccc_init=False)
    assert payload["includes_added_list"] == [] and payload["written"] is False
    assert _warnings_with(payload, "no include_patterns list")
    assert target.read_bytes() == before


@pytest.mark.parametrize("pattern, ext, covers", [
    ("**/*.ex", "ex", True),
    ("**/*.{ex,exs}", "exs", True),
    ("*.ex", "ex", True),  # ccc's `*` also matches `/`
    ("**/*.ex", "exs", False),
    ("src/**/*.ex", "ex", False),
    ("**/*.[ce]x", "ex", True),
    (42, "ex", False),
], ids=["star-star", "brace", "star", "other-ext", "folder-only", "class", "not-a-string"])
def test_include_covers_reads_entries_as_ccc_does(pattern, ext, covers):
    assert mod.include_covers(pattern, ext) is covers


def test_clone_merge_quotes_bare_glob_items_an_earlier_edit_left(tmp_clone):
    target = _settings_path(tmp_clone)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"exclude_patterns:\n  - '**/.*'\n  - **/build\n  -   **/out  \ninclude_patterns:\n  - '**/*.py'\n")
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(target.read_text(encoding="utf-8"))
    payload = mod.run_clone_merge(tmp_clone, allow_ccc_init=False)
    assert payload["written"] is True
    assert _warnings_with(payload, "quoted 2 list items")
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["exclude_patterns"][:3] == ["**/.*", "**/build", "**/out"]
    assert set(mod.CLONE_EXCLUDES) <= set(data["exclude_patterns"])


def test_quote_bare_glob_items_leaves_quoted_and_plain_items_alone():
    text = "a:\n- '**/x'\n- \"**/y\"\n- plain\n- **/z\n"
    fixed, count = mod.quote_bare_glob_items(text)
    assert count == 1
    assert fixed == "a:\n- '**/x'\n- \"**/y\"\n- plain\n- '**/z'\n"
    # A trailing comment stays a comment after the closing quote; a `#` inside the value stays in it.
    text = "a:\n- **/build  # generated output\n- **/a#b\n"
    fixed, count = mod.quote_bare_glob_items(text)
    assert count == 2
    assert fixed == "a:\n- '**/build'  # generated output\n- '**/a#b'\n"
    assert yaml.safe_load(fixed) == {"a": ["**/build", "**/a#b"]}


def test_clone_cli_unparseable_settings_exit_1(tmp_clone):
    target = _settings_path(tmp_clone)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"exclude_patterns: [unclosed\n")
    rc, payload, stderr = _run_clone(tmp_clone)
    assert rc == 1 and payload is None
    assert json.loads(stderr)["status"] == "error"
    assert target.read_bytes() == b"exclude_patterns: [unclosed\n"


def test_clone_cli_include_list_that_is_not_a_list_exit_1(tmp_clone):
    _write_yaml(_settings_path(tmp_clone), {"exclude_patterns": [], "include_patterns": "**/*.py"})
    rc, payload, stderr = _run_clone(tmp_clone, "--include-ext", "ex")
    assert rc == 1 and payload is None
    assert "include_patterns" in json.loads(stderr)["message"]


def test_clone_cli_output_has_the_documented_keys(tmp_clone):
    _seed_ccc_settings(tmp_clone)
    rc, payload, stderr = _run_clone(tmp_clone, "--include-ext", ".ex")
    assert rc == 0, stderr
    assert set(payload) == CLONE_KEYS
    assert payload["version"] == "v2"
    assert payload["includes_added_list"] == ["**/*.ex"]
    assert Path(payload["settings_yml_path"]) == _settings_path(tmp_clone)
    assert b"\r\n" not in _settings_path(tmp_clone).read_bytes()


@pytest.mark.parametrize("extra, message", [
    (("--skills-output-folder", "skills"), "--clone-root takes no setup flag (--skills-output-folder)"),
    (("--prior-state-from", "x.yaml", "--skip-index", "true"),
     "--clone-root takes no setup flag (--prior-state-from, --skip-index)"),
    (("--index-fresh", "false"), "--clone-root takes no setup flag (--index-fresh)"),
    (("--skills-output-folder", "", "--skip-index", "false"),
     "--clone-root takes no setup flag (--skills-output-folder, --skip-index)"),
    (("--include-ext", "a*"), "expected a file extension"),
    (("--include-ext", "../x"), "expected a file extension"),
], ids=["folder-flag", "record-and-index-flags", "false-index-flag", "empty-folder-flag", "glob-ext",
        "path-ext"])
def test_clone_cli_usage_errors_exit_2(tmp_clone, extra, message):
    rc, payload, stderr = _run_clone(tmp_clone, *extra)
    assert rc == 2 and payload is None
    err = json.loads(stderr)
    assert err["status"] == "error" and message in err["message"]


def test_cli_include_ext_needs_the_clone_root(tmp_project):
    _seed_ccc_settings(tmp_project)
    rc, payload, stderr = _run(tmp_project, extra_args=("--include-ext", "ex"))
    assert rc == 2 and payload is None
    assert "--include-ext needs --clone-root" in json.loads(stderr)["message"]


def test_cli_takes_exactly_one_root(tmp_project, tmp_clone):
    for argv in ([], ["--project-root", str(tmp_project), "--clone-root", str(tmp_clone)]):
        result = subprocess.run([sys.executable, str(SCRIPT_PATH), *argv, "--no-ccc-init"],
                                capture_output=True, timeout=60)
        assert result.returncode == 2
        assert json.loads(result.stderr.decode("utf-8"))["status"] == "error"


def test_clone_cli_missing_clone_root_exit_1(tmp_path):
    rc, payload, stderr = _run_clone(tmp_path / "missing")
    assert rc == 1 and payload is None
    assert "--clone-root is not a directory" in json.loads(stderr)["message"]


def test_clone_write_goes_through_a_temp_file_of_its_own(tmp_clone, monkeypatch):
    """Two runs merging one clone at once each write a whole file: no shared temp name."""
    target = _seed_ccc_settings(tmp_clone)
    moves = []
    real_replace = os.replace

    def recording_replace(src, dst):
        moves.append((Path(src).name, Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(mod.os, "replace", recording_replace)
    mod.run_clone_merge(tmp_clone, allow_ccc_init=False)
    [(tmp_name, dst)] = moves
    assert dst == target
    assert tmp_name != "settings.yml.skf-tmp" and tmp_name.endswith(".skf-tmp")
    assert sorted(p.name for p in target.parent.iterdir()) == ["settings.yml"]
