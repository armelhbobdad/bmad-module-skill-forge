#!/usr/bin/env python3
"""Tests for skf-detect-workspaces.py.

The detector is pure — it parses a payload (tree + manifests) and returns
a result envelope. Tests build payloads inline and call detect() directly,
plus a few subprocess-level CLI tests for stdin/argv/exit-code wiring.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-detect-workspaces.py"
)
SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "schemas"
    / "workspace-detection.v1.json"
)

spec = importlib.util.spec_from_file_location("skf_detect_workspaces", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Schema conformance helper (no jsonschema dep — assert structural shape)
# --------------------------------------------------------------------------


def assert_envelope_shape(out: dict) -> None:
    """Sanity-check every result against the schema's required fields."""
    assert set(out.keys()) == {"is_monorepo", "manifest_kind", "workspaces", "warnings"}, out.keys()
    assert isinstance(out["is_monorepo"], bool)
    assert out["manifest_kind"] is None or out["manifest_kind"] in {
        "npm-workspaces",
        "pnpm-workspaces",
        "lerna",
        "cargo-workspace",
        "python-multi-package",
        "generic-folders",
    }
    assert isinstance(out["workspaces"], list)
    for ws in out["workspaces"]:
        assert set(ws.keys()) == {"name", "path", "manifest"}
        assert isinstance(ws["name"], str) and ws["name"]
        assert isinstance(ws["path"], str) and ws["path"]
        assert isinstance(ws["manifest"], str) and ws["manifest"]
    assert isinstance(out["warnings"], list)


# --------------------------------------------------------------------------
# Single-package (non-monorepo) cases
# --------------------------------------------------------------------------


class TestSinglePackage:
    def test_empty_tree_no_monorepo(self):
        out = mod.detect({"tree": [], "manifests": {}})
        assert out["is_monorepo"] is False
        assert out["manifest_kind"] is None
        assert out["workspaces"] == []
        assert_envelope_shape(out)

    def test_plain_package_json_no_workspaces(self):
        out = mod.detect(
            {
                "tree": ["package.json", "src/index.ts", "README.md"],
                "manifests": {"package.json": json.dumps({"name": "marked"})},
            }
        )
        assert out["is_monorepo"] is False
        assert out["manifest_kind"] is None
        assert_envelope_shape(out)

    def test_plain_cargo_no_workspace(self):
        out = mod.detect(
            {
                "tree": ["Cargo.toml", "src/lib.rs"],
                "manifests": {"Cargo.toml": '[package]\nname = "ripgrep"\nversion = "0.1.0"\n'},
            }
        )
        assert out["is_monorepo"] is False
        assert_envelope_shape(out)

    def test_plain_pyproject_no_subpackages(self):
        out = mod.detect(
            {
                "tree": ["pyproject.toml", "src/foo/__init__.py"],
                "manifests": {"pyproject.toml": '[project]\nname = "foo"\n'},
            }
        )
        assert out["is_monorepo"] is False
        assert_envelope_shape(out)


# --------------------------------------------------------------------------
# npm workspaces
# --------------------------------------------------------------------------


class TestNpmWorkspaces:
    def test_array_form(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "packages/foo/package.json",
                    "packages/foo/src/index.js",
                    "packages/bar/package.json",
                    "packages/bar/src/index.js",
                ],
                "manifests": {
                    "package.json": json.dumps(
                        {"name": "root", "private": True, "workspaces": ["packages/*"]}
                    ),
                    "packages/foo/package.json": json.dumps({"name": "@org/foo"}),
                    "packages/bar/package.json": json.dumps({"name": "@org/bar"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "npm-workspaces"
        assert {ws["path"] for ws in out["workspaces"]} == {"packages/foo", "packages/bar"}
        names = {ws["name"] for ws in out["workspaces"]}
        assert names == {"@org/foo", "@org/bar"}
        assert_envelope_shape(out)

    def test_object_form_packages_field(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "packages/foo/package.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": {"packages": ["packages/*"]}}),
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "npm-workspaces"
        assert len(out["workspaces"]) == 1

    def test_multiple_globs(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "apps/web/package.json",
                    "apps/api/package.json",
                    "packages/lib/package.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["apps/*", "packages/*"]}),
                    "apps/web/package.json": json.dumps({"name": "web"}),
                    "apps/api/package.json": json.dumps({"name": "api"}),
                    "packages/lib/package.json": json.dumps({"name": "lib"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert {ws["path"] for ws in out["workspaces"]} == {
            "apps/web",
            "apps/api",
            "packages/lib",
        }

    def test_workspace_dirs_without_manifest_dropped(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "packages/foo/package.json",
                    "packages/empty/README.md",  # no manifest under it
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert {ws["path"] for ws in out["workspaces"]} == {"packages/foo"}

    def test_empty_workspaces_array_falls_through(self):
        out = mod.detect(
            {
                "tree": ["package.json"],
                "manifests": {"package.json": json.dumps({"workspaces": []})},
            }
        )
        assert out["is_monorepo"] is False

    def test_malformed_package_json_emits_warning_and_falls_through(self):
        out = mod.detect(
            {
                "tree": ["package.json"],
                "manifests": {"package.json": "{ this is not json"},
            }
        )
        assert out["is_monorepo"] is False
        assert any("package.json" in w for w in out["warnings"])

    def test_workspace_name_falls_back_to_dir_basename_when_manifest_missing(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "packages/foo/package.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    # packages/foo/package.json content NOT included in manifests dict
                },
            }
        )
        assert out["workspaces"][0]["name"] == "foo"


# --------------------------------------------------------------------------
# pnpm workspaces
# --------------------------------------------------------------------------


class TestPnpmWorkspaces:
    def test_basic(self):
        yaml_content = "packages:\n  - 'apps/*'\n  - 'packages/*'\n"
        out = mod.detect(
            {
                "tree": [
                    "pnpm-workspace.yaml",
                    "apps/web/package.json",
                    "packages/lib/package.json",
                ],
                "manifests": {
                    "pnpm-workspace.yaml": yaml_content,
                    "apps/web/package.json": json.dumps({"name": "web"}),
                    "packages/lib/package.json": json.dumps({"name": "lib"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "pnpm-workspaces"
        assert {ws["path"] for ws in out["workspaces"]} == {"apps/web", "packages/lib"}

    def test_exclusion_pattern(self):
        yaml_content = "packages:\n  - 'packages/*'\n  - '!packages/excluded'\n"
        out = mod.detect(
            {
                "tree": [
                    "pnpm-workspace.yaml",
                    "packages/foo/package.json",
                    "packages/excluded/package.json",
                ],
                "manifests": {
                    "pnpm-workspace.yaml": yaml_content,
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                    "packages/excluded/package.json": json.dumps({"name": "excluded"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert {ws["path"] for ws in out["workspaces"]} == {"packages/foo"}

    def test_npm_takes_priority_over_pnpm_when_both_present(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "pnpm-workspace.yaml",
                    "packages/foo/package.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert out["manifest_kind"] == "npm-workspaces"


# --------------------------------------------------------------------------
# lerna
# --------------------------------------------------------------------------


class TestLerna:
    def test_explicit_packages(self):
        out = mod.detect(
            {
                "tree": [
                    "lerna.json",
                    "packages/foo/package.json",
                    "packages/bar/package.json",
                ],
                "manifests": {
                    "lerna.json": json.dumps({"packages": ["packages/*"], "version": "1.0.0"}),
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                    "packages/bar/package.json": json.dumps({"name": "bar"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "lerna"
        assert len(out["workspaces"]) == 2

    def test_absent_packages_field_falls_through_to_npm_detector(self):
        # lerna v5+ delegates to package-manager workspaces when `packages` is absent.
        # The lerna detector must NOT inject a default and silently claim monorepo on
        # any repo that happens to have a packages/ dir — npm/pnpm should win first.
        out = mod.detect(
            {
                "tree": [
                    "lerna.json",
                    "package.json",
                    "packages/foo/package.json",
                ],
                "manifests": {
                    "lerna.json": json.dumps({"version": "5.0.0"}),  # no packages field
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "npm-workspaces"

    def test_absent_packages_field_no_npm_workspaces_falls_through(self):
        # Pure Nx-managed lerna v5+ repo: no packages field, no npm workspaces. The lerna
        # detector must fall through; downstream falls to generic-folders if the layout warrants.
        out = mod.detect(
            {
                "tree": [
                    "lerna.json",
                    "packages/foo/package.json",
                ],
                "manifests": {
                    "lerna.json": json.dumps({"version": "5.0.0"}),
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        # Only one packages/* child means generic-folders also falls through; result is single-package
        assert out["is_monorepo"] is False
        assert out["manifest_kind"] is None


# --------------------------------------------------------------------------
# Cargo workspaces
# --------------------------------------------------------------------------


class TestCargoWorkspace:
    def test_basic(self):
        cargo = (
            "[workspace]\n"
            'members = ["crates/*"]\n'
            "\n"
            "[workspace.package]\n"
            'version = "0.1.0"\n'
        )
        out = mod.detect(
            {
                "tree": [
                    "Cargo.toml",
                    "crates/core/Cargo.toml",
                    "crates/cli/Cargo.toml",
                ],
                "manifests": {
                    "Cargo.toml": cargo,
                    "crates/core/Cargo.toml": '[package]\nname = "core"\nversion = "0.1.0"\n',
                    "crates/cli/Cargo.toml": '[package]\nname = "cli"\nversion = "0.1.0"\n',
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "cargo-workspace"
        assert {ws["name"] for ws in out["workspaces"]} == {"core", "cli"}

    def test_exclude_field(self):
        cargo = (
            "[workspace]\n"
            'members = ["crates/*"]\n'
            'exclude = ["crates/dropped"]\n'
        )
        out = mod.detect(
            {
                "tree": [
                    "Cargo.toml",
                    "crates/keep/Cargo.toml",
                    "crates/dropped/Cargo.toml",
                ],
                "manifests": {
                    "Cargo.toml": cargo,
                    "crates/keep/Cargo.toml": '[package]\nname = "keep"\n',
                    "crates/dropped/Cargo.toml": '[package]\nname = "dropped"\n',
                },
            }
        )
        assert {ws["path"] for ws in out["workspaces"]} == {"crates/keep"}

    def test_empty_members_falls_through(self):
        out = mod.detect(
            {
                "tree": ["Cargo.toml"],
                "manifests": {"Cargo.toml": "[workspace]\nmembers = []\n"},
            }
        )
        assert out["is_monorepo"] is False

    def test_malformed_cargo_warns(self):
        out = mod.detect(
            {
                "tree": ["Cargo.toml"],
                "manifests": {"Cargo.toml": "[workspace\nmembers ="},  # syntactically broken
            }
        )
        assert out["is_monorepo"] is False
        assert any("Cargo.toml" in w for w in out["warnings"])


# --------------------------------------------------------------------------
# Python multi-package
# --------------------------------------------------------------------------


class TestPythonMultiPackage:
    def test_packages_layout(self):
        out = mod.detect(
            {
                "tree": [
                    "packages/foo/pyproject.toml",
                    "packages/bar/pyproject.toml",
                    "README.md",
                ],
                "manifests": {
                    "packages/foo/pyproject.toml": '[project]\nname = "foo"\n',
                    "packages/bar/pyproject.toml": '[project]\nname = "bar"\n',
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "python-multi-package"
        assert {ws["name"] for ws in out["workspaces"]} == {"foo", "bar"}

    def test_apps_layout(self):
        out = mod.detect(
            {
                "tree": [
                    "apps/svc1/pyproject.toml",
                    "apps/svc2/pyproject.toml",
                ],
                "manifests": {
                    "apps/svc1/pyproject.toml": '[project]\nname = "svc1"\n',
                    "apps/svc2/pyproject.toml": '[project]\nname = "svc2"\n',
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "python-multi-package"

    def test_libs_layout(self):
        out = mod.detect(
            {
                "tree": [
                    "libs/core/pyproject.toml",
                    "libs/utils/pyproject.toml",
                ],
                "manifests": {
                    "libs/core/pyproject.toml": '[project]\nname = "core"\n',
                    "libs/utils/pyproject.toml": '[project]\nname = "utils"\n',
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "python-multi-package"

    def test_cross_prefix_layout_one_packages_one_apps(self):
        # 1 under packages/ + 1 under apps/ should still detect as python-multi-package
        out = mod.detect(
            {
                "tree": [
                    "packages/lib/pyproject.toml",
                    "apps/cli/pyproject.toml",
                ],
                "manifests": {
                    "packages/lib/pyproject.toml": '[project]\nname = "lib"\n',
                    "apps/cli/pyproject.toml": '[project]\nname = "cli"\n',
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "python-multi-package"

    def test_single_subpackage_falls_through(self):
        out = mod.detect(
            {
                "tree": ["packages/only/pyproject.toml"],
                "manifests": {"packages/only/pyproject.toml": '[project]\nname = "only"\n'},
            }
        )
        assert out["is_monorepo"] is False

    def test_nested_pyproject_does_not_count(self):
        out = mod.detect(
            {
                "tree": [
                    "packages/foo/inner/pyproject.toml",
                    "packages/bar/inner/pyproject.toml",
                ],
                "manifests": {},
            }
        )
        assert out["is_monorepo"] is False


# --------------------------------------------------------------------------
# Generic folders fallback
# --------------------------------------------------------------------------


class TestGenericFolders:
    def test_two_packages_under_packages_dir_no_root_manifest(self):
        out = mod.detect(
            {
                "tree": [
                    "packages/a/package.json",
                    "packages/b/package.json",
                ],
                "manifests": {
                    "packages/a/package.json": json.dumps({"name": "a"}),
                    "packages/b/package.json": json.dumps({"name": "b"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "generic-folders"

    def test_single_child_in_generic_dir_falls_through(self):
        out = mod.detect(
            {
                "tree": ["packages/lonely/package.json"],
                "manifests": {"packages/lonely/package.json": json.dumps({"name": "lonely"})},
            }
        )
        assert out["is_monorepo"] is False

    def test_generic_dir_with_no_manifests_falls_through(self):
        out = mod.detect(
            {
                "tree": [
                    "packages/a/README.md",
                    "packages/b/README.md",
                ],
                "manifests": {},
            }
        )
        assert out["is_monorepo"] is False

    def test_cross_parent_accumulation_one_apps_one_packages(self):
        # 1 manifested child under apps/ + 1 under packages/ → generic-folders fires
        out = mod.detect(
            {
                "tree": [
                    "apps/web/package.json",
                    "packages/lib/package.json",
                ],
                "manifests": {
                    "apps/web/package.json": json.dumps({"name": "web"}),
                    "packages/lib/package.json": json.dumps({"name": "lib"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "generic-folders"
        assert {ws["path"] for ws in out["workspaces"]} == {"apps/web", "packages/lib"}

    def test_npm_workspaces_take_priority_over_generic(self):
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "packages/a/package.json",
                    "packages/b/package.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "packages/a/package.json": json.dumps({"name": "a"}),
                    "packages/b/package.json": json.dumps({"name": "b"}),
                },
            }
        )
        assert out["manifest_kind"] == "npm-workspaces"


# --------------------------------------------------------------------------
# Cross-ecosystem secondary-manifest warning
# --------------------------------------------------------------------------


class TestCrossEcosystemWarning:
    # tauri-style repo: a root pnpm workspace (JS) co-located with a root
    # `Cargo.toml [workspace]` (Rust). pnpm wins by priority; the cargo
    # workspace must not vanish silently.
    DUAL = {
        "tree": [
            "pnpm-workspace.yaml",
            "packages/api/package.json",
            "packages/cli/package.json",
            "Cargo.toml",
            "crates/tauri/Cargo.toml",
            "crates/tauri-runtime/Cargo.toml",
        ],
        "manifests": {
            "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
            "packages/api/package.json": json.dumps({"name": "api"}),
            "packages/cli/package.json": json.dumps({"name": "cli"}),
            "Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n',
            "crates/tauri/Cargo.toml": '[package]\nname = "tauri"\nversion = "2.11.2"\n',
            "crates/tauri-runtime/Cargo.toml": '[package]\nname = "tauri-runtime"\n',
        },
    }

    def test_pnpm_wins_but_cargo_workspace_is_flagged_not_dropped(self):
        out = mod.detect(self.DUAL)
        # Surfaced result is unchanged (non-breaking): pnpm still wins.
        assert out["manifest_kind"] == "pnpm-workspaces"
        assert {ws["path"] for ws in out["workspaces"]} == {"packages/api", "packages/cli"}
        # ...but the ignored cargo workspace now surfaces as a warning.
        cargo_warns = [w for w in out["warnings"] if "cargo-workspace" in w]
        assert len(cargo_warns) == 1, out["warnings"]
        assert "Cargo.toml" in cargo_warns[0]
        assert "2 member" in cargo_warns[0]
        assert_envelope_shape(out)

    def test_cargo_wins_flags_co_located_python_workspace(self):
        # Inverse direction: a JS root workspace always wins by priority over
        # cargo, so the reachable inverse is cargo (priority 4) winning over a
        # co-located python-multi-package layout (priority 5), which must be
        # flagged rather than silently dropped.
        out = mod.detect(
            {
                "tree": [
                    "Cargo.toml",
                    "crates/core/Cargo.toml",
                    "crates/cli/Cargo.toml",
                    "packages/svc-a/pyproject.toml",
                    "packages/svc-b/pyproject.toml",
                ],
                "manifests": {
                    "Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n',
                    "crates/core/Cargo.toml": '[package]\nname = "core"\n',
                    "crates/cli/Cargo.toml": '[package]\nname = "cli"\n',
                    "packages/svc-a/pyproject.toml": '[project]\nname = "svc-a"\n',
                    "packages/svc-b/pyproject.toml": '[project]\nname = "svc-b"\n',
                },
            }
        )
        assert out["manifest_kind"] == "cargo-workspace"
        assert any("python-multi-package" in w for w in out["warnings"]), out["warnings"]

    def test_same_ecosystem_npm_and_pnpm_do_not_warn(self):
        # npm + pnpm are both JS — the priority pick is expected, not a
        # cross-ecosystem drop, so no warning should fire.
        out = mod.detect(
            {
                "tree": [
                    "package.json",
                    "pnpm-workspace.yaml",
                    "packages/foo/package.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert out["manifest_kind"] == "npm-workspaces"
        assert not any("cross-ecosystem" in w for w in out["warnings"]), out["warnings"]

    def test_single_ecosystem_repo_emits_no_cross_ecosystem_warning(self):
        out = mod.detect(
            {
                "tree": ["pnpm-workspace.yaml", "packages/foo/package.json"],
                "manifests": {
                    "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert not any("cross-ecosystem" in w for w in out["warnings"]), out["warnings"]

    def test_malformed_secondary_manifest_does_not_leak_into_warnings(self):
        # A broken Cargo.toml alongside the winning pnpm workspace must not
        # surface a "Cargo.toml parse error" — the secondary detector's parse
        # warnings go to a throwaway sink.
        out = mod.detect(
            {
                "tree": ["pnpm-workspace.yaml", "packages/foo/package.json", "Cargo.toml"],
                "manifests": {
                    "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                    "Cargo.toml": "[workspace\nmembers =",  # broken
                },
            }
        )
        assert out["manifest_kind"] == "pnpm-workspaces"
        assert not any("parse error" in w for w in out["warnings"]), out["warnings"]


# --------------------------------------------------------------------------
# CLI / I/O
# --------------------------------------------------------------------------


class TestCli:
    def _run(self, payload: dict | str, stdin: bool = True) -> tuple[int, str, str]:
        body = json.dumps(payload) if isinstance(payload, dict) else payload
        if stdin:
            cmd = [sys.executable, str(SCRIPT_PATH)]
            proc = subprocess.run(cmd, input=body, capture_output=True, text=True, timeout=10)
        else:
            cmd = [sys.executable, str(SCRIPT_PATH), "--json", body]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return proc.returncode, proc.stdout, proc.stderr

    def test_stdin_happy_path_exit_0(self):
        rc, out, err = self._run(
            {
                "tree": ["package.json", "packages/foo/package.json"],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "packages/foo/package.json": json.dumps({"name": "foo"}),
                },
            }
        )
        assert rc == 0, f"stderr={err}"
        result = json.loads(out)
        assert result["is_monorepo"] is True

    def test_argv_json_flag(self):
        rc, out, _ = self._run(
            {"tree": [], "manifests": {}},
            stdin=False,
        )
        assert rc == 0
        result = json.loads(out)
        assert result["is_monorepo"] is False

    def test_empty_input_exits_2(self):
        rc, _, err = self._run("", stdin=True)
        assert rc == 2
        assert "empty input" in err

    def test_invalid_json_exits_2(self):
        rc, _, err = self._run("{ not valid", stdin=True)
        assert rc == 2
        assert "json decode error" in err

    def test_payload_missing_tree_exits_1(self):
        rc, _, err = self._run({"manifests": {}}, stdin=True)
        assert rc == 1
        assert "tree" in err

    def test_payload_missing_manifests_exits_1(self):
        rc, _, err = self._run({"tree": []}, stdin=True)
        assert rc == 1
        assert "manifests" in err


# --------------------------------------------------------------------------
# Schema artifact
# --------------------------------------------------------------------------


class TestSchemaArtifact:
    def test_schema_file_exists_and_is_valid_json(self):
        with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)
        assert schema["$schema"].startswith("https://json-schema.org/")
        assert schema["title"]
        # Required result envelope properties
        assert set(schema["required"]) == {"is_monorepo", "manifest_kind", "workspaces", "warnings"}
