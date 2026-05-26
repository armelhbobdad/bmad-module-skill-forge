"""Tests for skf-preapply.py.

Structural tests for the registry and script existence, plus functional
tests for CLI wiring, fingerprint matching (substring and regex), merge
logic, and exit codes.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-preapply.py"
REGISTRY_PATH = REPO_ROOT / "src" / "shared" / "_known-workarounds.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(*extra_args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *extra_args],
        capture_output=True,
        text=True,
        check=check,
    )


def _write_registry(path: pathlib.Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def _write_md(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Task 3.2 — Registry file exists
# ---------------------------------------------------------------------------


class TestRegistryExists:
    def test_registry_file_exists(self) -> None:
        assert REGISTRY_PATH.is_file(), (
            f"Shared seed registry not found at {REGISTRY_PATH.as_posix()}"
        )


# ---------------------------------------------------------------------------
# Task 3.3 — Registry has version: 1 header
# ---------------------------------------------------------------------------


class TestRegistryVersion:
    @pytest.fixture(scope="class")
    def data(self) -> dict:
        return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_version_is_1(self, data: dict) -> None:
        assert data.get("version") == 1


# ---------------------------------------------------------------------------
# Task 3.4 — Registry has workarounds array with >= 25 entries
# ---------------------------------------------------------------------------


class TestRegistryEntryCount:
    @pytest.fixture(scope="class")
    def data(self) -> dict:
        return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_workarounds_is_list(self, data: dict) -> None:
        assert isinstance(data.get("workarounds"), list)

    def test_at_least_25_entries(self, data: dict) -> None:
        assert len(data["workarounds"]) >= 25


# ---------------------------------------------------------------------------
# Task 3.5 — Each entry has required fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"fingerprint", "fix", "source", "severity", "description"}


class TestRegistryEntrySchema:
    @pytest.fixture(scope="class")
    def entries(self) -> list:
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        return data["workarounds"]

    def test_all_entries_have_required_fields(self, entries: list) -> None:
        for i, entry in enumerate(entries):
            missing = REQUIRED_FIELDS - set(entry.keys())
            assert not missing, (
                f"Entry {i} missing fields: {missing}"
            )


# ---------------------------------------------------------------------------
# Task 3.6 — Severity values in {low, medium, high}
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"low", "medium", "high"}


class TestRegistrySeverityValues:
    @pytest.fixture(scope="class")
    def entries(self) -> list:
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        return data["workarounds"]

    def test_valid_severity_values(self, entries: list) -> None:
        for i, entry in enumerate(entries):
            assert entry["severity"] in VALID_SEVERITIES, (
                f"Entry {i} has invalid severity: {entry['severity']}"
            )


# ---------------------------------------------------------------------------
# Task 3.7 — At least one entry has regex: true
# ---------------------------------------------------------------------------


class TestRegistryRegexEntries:
    @pytest.fixture(scope="class")
    def entries(self) -> list:
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        return data["workarounds"]

    def test_at_least_one_regex_entry(self, entries: list) -> None:
        regex_entries = [e for e in entries if e.get("regex") is True]
        assert len(regex_entries) >= 1, "Registry must have at least one regex entry"


# ---------------------------------------------------------------------------
# Task 3.8 — Script exists
# ---------------------------------------------------------------------------


class TestScriptExists:
    def test_script_file_exists(self) -> None:
        assert SCRIPT_PATH.is_file(), (
            f"skf-preapply.py not found at {SCRIPT_PATH.as_posix()}"
        )


# ---------------------------------------------------------------------------
# Task 3.9 — Script has PEP 723 header with pyyaml dependency
# ---------------------------------------------------------------------------


class TestScriptPEP723:
    @pytest.fixture(scope="class")
    def header(self) -> str:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        start = text.find("# /// script")
        end = text.find("# ///", start + 1)
        return text[start : end + len("# ///")]

    def test_has_pep723_header(self, header: str) -> None:
        assert "# /// script" in header

    def test_requires_python(self, header: str) -> None:
        assert "requires-python" in header

    def test_pyyaml_dependency(self, header: str) -> None:
        assert "pyyaml" in header.lower()


# ---------------------------------------------------------------------------
# Task 3.10 — CLI accepts --target-dir, --registry, --local-registry
# ---------------------------------------------------------------------------


class TestCLIArgs:
    def test_help_mentions_target_dir(self) -> None:
        proc = _run_cli("--help")
        assert "--target-dir" in proc.stdout

    def test_help_mentions_registry(self) -> None:
        proc = _run_cli("--help")
        assert "--registry" in proc.stdout

    def test_help_mentions_local_registry(self) -> None:
        proc = _run_cli("--help")
        assert "--local-registry" in proc.stdout


# ---------------------------------------------------------------------------
# Task 3.11 — JSON stdout schema matches {applied, skipped_count, registry_version}
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_output_has_required_keys(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "dummy.md", "nothing to match here")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {"version": 1, "workarounds": []})

        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(registry),
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert "applied" in data
        assert "skipped_count" in data
        assert "registry_version" in data


# ---------------------------------------------------------------------------
# Task 3.12 — Exit code 0 on valid invocation
# ---------------------------------------------------------------------------


class TestExitCodeSuccess:
    def test_exit_0_no_matches(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "clean content with no workarounds")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {"version": 1, "workarounds": []})

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0

    def test_exit_0_with_matches(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "skill.md", "This has BAD_PATTERN in it")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "BAD_PATTERN",
                "fix": "GOOD_PATTERN",
                "source": "test",
                "severity": "low",
                "description": "test fix",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0


# ---------------------------------------------------------------------------
# Task 3.13 — Exit code 2 on missing target-dir or invalid registry
# ---------------------------------------------------------------------------


class TestExitCodeErrors:
    def test_exit_2_missing_target_dir(self, tmp_path: pathlib.Path) -> None:
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {"version": 1, "workarounds": []})
        missing = tmp_path / "nonexistent"
        proc = _run_cli(
            "--target-dir", str(missing),
            "--registry", str(registry),
        )
        assert proc.returncode == 2

    def test_exit_2_missing_registry(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(tmp_path / "no-such-file.yaml"),
        )
        assert proc.returncode == 2

    def test_exit_2_invalid_yaml(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        bad_reg = tmp_path / "bad.yaml"
        bad_reg.write_text(": : : invalid yaml [[[", encoding="utf-8")
        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(bad_reg),
        )
        assert proc.returncode == 2

    def test_stderr_json_on_error(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(tmp_path / "missing.yaml"),
        )
        err = json.loads(proc.stderr.strip())
        assert "error" in err
        assert "code" in err


# ---------------------------------------------------------------------------
# Task 3.14 — Substring matching applies fix
# ---------------------------------------------------------------------------


class TestSubstringMatching:
    def test_substring_fix_applied(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "The version: 0.9-draft is old")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "version: 0.9-draft",
                "fix": "version: 1",
                "source": "test",
                "severity": "medium",
                "description": "fix version",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 1
        assert data["applied"][0]["fingerprint"] == "version: 0.9-draft"
        updated = (target / "doc.md").read_text(encoding="utf-8")
        assert "version: 1" in updated
        assert "version: 0.9-draft" not in updated


# ---------------------------------------------------------------------------
# Task 3.15 — Regex matching applies fix
# ---------------------------------------------------------------------------


class TestRegexMatching:
    def test_regex_fix_applied(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "confidence: none\nconfidence: n/a\n")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "\\bconfidence:\\s*(?:none|n/a|unset)\\b",
                "fix": "confidence: T1-inferred",
                "source": "test",
                "severity": "medium",
                "description": "normalize confidence",
                "regex": True,
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 1
        updated = (target / "doc.md").read_text(encoding="utf-8")
        assert "confidence: T1-inferred" in updated
        assert "confidence: none" not in updated
        assert "confidence: n/a" not in updated


# ---------------------------------------------------------------------------
# Task 3.16 — Local registry overrides shared seed on fingerprint collision
# ---------------------------------------------------------------------------


class TestLocalRegistryOverride:
    def test_local_wins_on_collision(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "fingerprint-collision-test content here")

        shared_reg = tmp_path / "shared.yaml"
        _write_registry(shared_reg, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "fingerprint-collision-test",
                "fix": "SHARED_FIX",
                "source": "shared",
                "severity": "low",
                "description": "shared version",
            }],
        })

        local_reg = tmp_path / "local.yaml"
        _write_registry(local_reg, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "fingerprint-collision-test",
                "fix": "LOCAL_FIX",
                "source": "local",
                "severity": "high",
                "description": "local override",
            }],
        })

        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(shared_reg),
            "--local-registry", str(local_reg),
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 1
        assert data["applied"][0]["fix"] == "LOCAL_FIX"
        updated = (target / "doc.md").read_text(encoding="utf-8")
        assert "LOCAL_FIX" in updated
        assert "SHARED_FIX" not in updated


# ---------------------------------------------------------------------------
# Task 3.17 — No modifications when no fingerprints match
# ---------------------------------------------------------------------------


class TestNoMatchNoModification:
    def test_no_changes_when_no_match(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        original = "This content has nothing matching any workaround."
        _write_md(target / "clean.md", original)
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "WILL_NOT_MATCH_ANYTHING_HERE",
                "fix": "replacement",
                "source": "test",
                "severity": "low",
                "description": "no match expected",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 0
        assert data["skipped_count"] == 1
        assert (target / "clean.md").read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# E2E gap: --log-dir writes preapply-log.json (AC #1)
# ---------------------------------------------------------------------------


class TestLogDirWritesJson:
    def test_log_file_created(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "BAD_TOKEN here")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "BAD_TOKEN",
                "fix": "GOOD_TOKEN",
                "source": "test",
                "severity": "high",
                "description": "test log",
            }],
        })
        log_dir = tmp_path / "logs"

        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(registry),
            "--log-dir", str(log_dir),
        )
        assert proc.returncode == 0
        log_path = log_dir / "preapply-log.json"
        assert log_path.is_file()
        log_data = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(log_data["applied"]) == 1
        assert log_data["applied"][0]["fingerprint"] == "BAD_TOKEN"
        assert log_data["registry_version"] == 1

    def test_log_dir_created_if_missing(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "no matches")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {"version": 1, "workarounds": []})
        log_dir = tmp_path / "deep" / "nested" / "logs"

        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(registry),
            "--log-dir", str(log_dir),
        )
        assert proc.returncode == 0
        assert (log_dir / "preapply-log.json").is_file()


# ---------------------------------------------------------------------------
# E2E gap: Nested directory scanning (rglob traversal)
# ---------------------------------------------------------------------------


class TestNestedDirectoryScanning:
    def test_finds_md_in_subdirectories(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        sub = target / "sub" / "deep"
        sub.mkdir(parents=True)
        _write_md(sub / "nested.md", "FIX_ME_NESTED content")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "FIX_ME_NESTED",
                "fix": "FIXED_NESTED",
                "source": "test",
                "severity": "low",
                "description": "nested test",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 1
        assert data["applied"][0]["file"] == "sub/deep/nested.md"
        updated = sub / "nested.md"
        assert "FIXED_NESTED" in updated.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# E2E gap: Non-.md files are ignored
# ---------------------------------------------------------------------------


class TestNonMdFilesIgnored:
    def test_txt_and_yaml_not_scanned(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "readme.txt", "MATCH_THIS content")
        (target / "config.yaml").write_text(
            "key: MATCH_THIS", encoding="utf-8"
        )
        _write_md(target / "actual.md", "no match here")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "MATCH_THIS",
                "fix": "REPLACED",
                "source": "test",
                "severity": "low",
                "description": "should not match non-md",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 0
        assert (target / "readme.txt").read_text(encoding="utf-8") == "MATCH_THIS content"
        assert (target / "config.yaml").read_text(encoding="utf-8") == "key: MATCH_THIS"


# ---------------------------------------------------------------------------
# E2E gap: Multiple workarounds applied in one run
# ---------------------------------------------------------------------------


class TestMultipleWorkaroundsApplied:
    def test_batch_apply(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "AAA and BBB and CCC")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [
                {
                    "fingerprint": "AAA",
                    "fix": "aaa-fixed",
                    "source": "test",
                    "severity": "low",
                    "description": "fix A",
                },
                {
                    "fingerprint": "BBB",
                    "fix": "bbb-fixed",
                    "source": "test",
                    "severity": "medium",
                    "description": "fix B",
                },
                {
                    "fingerprint": "NOMATCH",
                    "fix": "n/a",
                    "source": "test",
                    "severity": "high",
                    "description": "should skip",
                },
            ],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 2
        assert data["skipped_count"] == 1
        updated = (target / "doc.md").read_text(encoding="utf-8")
        assert "aaa-fixed" in updated
        assert "bbb-fixed" in updated
        assert "AAA" not in updated
        assert "BBB" not in updated


# ---------------------------------------------------------------------------
# E2E gap: Applied entry has correct field schema
# ---------------------------------------------------------------------------


class TestAppliedEntryFields:
    def test_applied_entry_structure(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "skill.md", "PATTERN_X present")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "PATTERN_X",
                "fix": "REPLACEMENT_X",
                "source": "test",
                "severity": "high",
                "description": "field check",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        data = json.loads(proc.stdout)
        entry = data["applied"][0]
        assert entry["fingerprint"] == "PATTERN_X"
        assert entry["fix"] == "REPLACEMENT_X"
        assert entry["file"] == "skill.md"
        assert entry["severity"] == "high"


# ---------------------------------------------------------------------------
# E2E gap: Empty target directory (no .md files)
# ---------------------------------------------------------------------------


class TestEmptyTargetDirectory:
    def test_no_md_files_exits_0(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "anything",
                "fix": "x",
                "source": "test",
                "severity": "low",
                "description": "no files",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 0
        assert data["skipped_count"] == 1


# ---------------------------------------------------------------------------
# E2E gap: registry_version value correctness
# ---------------------------------------------------------------------------


class TestRegistryVersionOutput:
    def test_version_value_propagated(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "content")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {"version": 1, "workarounds": []})

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        data = json.loads(proc.stdout)
        assert data["registry_version"] == 1


# ---------------------------------------------------------------------------
# E2E gap: Invalid registry format (missing workarounds key)
# ---------------------------------------------------------------------------


class TestInvalidRegistryFormat:
    def test_exit_2_missing_workarounds_key(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        bad_reg = tmp_path / "bad.yaml"
        bad_reg.write_text("version: 1\nsome_key: value\n", encoding="utf-8")

        proc = _run_cli("--target-dir", str(target), "--registry", str(bad_reg))
        assert proc.returncode == 2
        err = json.loads(proc.stderr.strip())
        assert err["code"] == "INVALID_REGISTRY"


# ---------------------------------------------------------------------------
# E2E gap: Specific error codes in stderr
# ---------------------------------------------------------------------------


class TestSpecificErrorCodes:
    def test_target_not_found_code(self, tmp_path: pathlib.Path) -> None:
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {"version": 1, "workarounds": []})
        proc = _run_cli(
            "--target-dir", str(tmp_path / "ghost"),
            "--registry", str(registry),
        )
        assert proc.returncode == 2
        err = json.loads(proc.stderr.strip())
        assert err["code"] == "TARGET_NOT_FOUND"

    def test_invalid_regex_code(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "some content")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "[invalid(regex",
                "fix": "x",
                "source": "test",
                "severity": "low",
                "description": "bad regex",
                "regex": True,
            }],
        })
        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 2
        err = json.loads(proc.stderr.strip())
        assert err["code"] == "INVALID_REGEX"

    def test_registry_not_found_code(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(tmp_path / "nope.yaml"),
        )
        assert proc.returncode == 2
        err = json.loads(proc.stderr.strip())
        assert err["code"] == "REGISTRY_NOT_FOUND"


# ---------------------------------------------------------------------------
# E2E gap: Additive merge (local adds new entries)
# ---------------------------------------------------------------------------


class TestAdditiveMerge:
    def test_local_adds_unique_entries(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "doc.md", "SHARED_ONLY and LOCAL_ONLY present")

        shared_reg = tmp_path / "shared.yaml"
        _write_registry(shared_reg, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "SHARED_ONLY",
                "fix": "SHARED_FIXED",
                "source": "shared",
                "severity": "low",
                "description": "shared entry",
            }],
        })

        local_reg = tmp_path / "local.yaml"
        _write_registry(local_reg, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "LOCAL_ONLY",
                "fix": "LOCAL_FIXED",
                "source": "local",
                "severity": "medium",
                "description": "local-only entry",
            }],
        })

        proc = _run_cli(
            "--target-dir", str(target),
            "--registry", str(shared_reg),
            "--local-registry", str(local_reg),
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 2
        fps = {e["fingerprint"] for e in data["applied"]}
        assert "SHARED_ONLY" in fps
        assert "LOCAL_ONLY" in fps


# ---------------------------------------------------------------------------
# E2E gap: Same workaround matches across multiple files
# ---------------------------------------------------------------------------


class TestMultiFileMatching:
    def test_workaround_applied_to_all_matching_files(
        self, tmp_path: pathlib.Path
    ) -> None:
        target = tmp_path / "target"
        target.mkdir()
        _write_md(target / "a.md", "COMMON_BUG in file A")
        _write_md(target / "b.md", "COMMON_BUG in file B")
        _write_md(target / "clean.md", "no issue here")
        registry = tmp_path / "reg.yaml"
        _write_registry(registry, {
            "version": 1,
            "workarounds": [{
                "fingerprint": "COMMON_BUG",
                "fix": "FIXED_BUG",
                "source": "test",
                "severity": "medium",
                "description": "multi-file match",
            }],
        })

        proc = _run_cli("--target-dir", str(target), "--registry", str(registry))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert len(data["applied"]) == 2
        files = sorted(e["file"] for e in data["applied"])
        assert files == ["a.md", "b.md"]
        for f in ["a.md", "b.md"]:
            content = (target / f).read_text(encoding="utf-8")
            assert "FIXED_BUG" in content
            assert "COMMON_BUG" not in content
