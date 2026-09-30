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
        "rush",
        "nx",
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
# Rush
# --------------------------------------------------------------------------


RUSH_JSON = """{
  // Rush reads JSON with comments
  "rushVersion": "5.120.0",
  /* each project: its package name and folder */
  "projects": [
    { "packageName": "@acme/core", "projectFolder": "libs/core" },
    { "packageName": "@acme/web", "projectFolder": "./apps/web/", },
    { "packageName": "@acme/gone", "projectFolder": "libs/gone" },
    { "packageName": "@acme/url", "projectFolder": "libs/url-//-kept" }
  ],
}
"""


class TestRush:
    def test_projects_from_rush_json(self):
        out = mod.detect(
            {
                "tree": [
                    "rush.json",
                    "libs/core/package.json",
                    "apps/web/package.json",
                    "libs/url-//-kept/package.json",
                ],
                "manifests": {"rush.json": RUSH_JSON},
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "rush"
        # a project folder with no package.json in the tree is dropped
        assert out["workspaces"] == [
            {"name": "@acme/web", "path": "apps/web", "manifest": "apps/web/package.json"},
            {"name": "@acme/core", "path": "libs/core", "manifest": "libs/core/package.json"},
            {"name": "@acme/url", "path": "libs/url-//-kept", "manifest": "libs/url-//-kept/package.json"},
        ]
        assert_envelope_shape(out)

    def test_json_with_comments_keeps_its_strings(self):
        text = '{"a": "x,]y,}", // c\n "b": [1, /* c */ ], "c": "// no", "d": {"e": 1, // last\n },\n}'
        assert json.loads(mod._strip_json_comments(text)) == {"a": "x,]y,}", "b": [1], "c": "// no", "d": {"e": 1}}

    def test_rush_json_content_is_needed(self):
        out = mod.detect({"tree": ["rush.json", "libs/core/package.json"], "manifests": {}})
        assert out["is_monorepo"] is False
        assert any("rush.json" in w and "manifests" in w for w in out["warnings"])

    def test_malformed_rush_json_warns_and_falls_through(self):
        out = mod.detect({"tree": ["rush.json"], "manifests": {"rush.json": "{ projects: ["}})
        assert out["is_monorepo"] is False
        assert any("rush.json" in w for w in out["warnings"])

    def test_npm_workspaces_take_priority_over_rush(self):
        out = mod.detect(
            {
                "tree": ["package.json", "rush.json", "packages/a/package.json", "libs/core/package.json"],
                "manifests": {
                    "package.json": json.dumps({"workspaces": ["packages/*"]}),
                    "rush.json": RUSH_JSON,
                },
            }
        )
        assert out["manifest_kind"] == "npm-workspaces"
        assert not any("cross-ecosystem" in w for w in out["warnings"])


# --------------------------------------------------------------------------
# Nx
# --------------------------------------------------------------------------


class TestNx:
    def test_projects_are_folders_with_project_json(self):
        out = mod.detect(
            {
                "tree": [
                    "nx.json",
                    "package.json",
                    "apps/shop/project.json",
                    "libs/ui/project.json",
                    "libs/ui/src/index.ts",
                    "node_modules/pkg/project.json",
                ],
                "manifests": {
                    "package.json": json.dumps({"name": "root"}),
                    "libs/ui/project.json": json.dumps({"name": "shared-ui"}),
                },
            }
        )
        assert out["is_monorepo"] is True
        assert out["manifest_kind"] == "nx"
        assert out["workspaces"] == [
            {"name": "shop", "path": "apps/shop", "manifest": "apps/shop/project.json"},
            {"name": "shared-ui", "path": "libs/ui", "manifest": "libs/ui/project.json"},
        ]
        assert_envelope_shape(out)

    def test_nx_without_project_json_falls_through(self):
        # an Nx repository that declares its projects as package.json
        # workspaces is found by the npm detector; with neither, no monorepo
        out = mod.detect({"tree": ["nx.json", "package.json"], "manifests": {}})
        assert out["is_monorepo"] is False
        out = mod.detect(
            {
                "tree": ["nx.json", "package.json", "packages/a/package.json"],
                "manifests": {"package.json": json.dumps({"workspaces": ["packages/*"]})},
            }
        )
        assert out["manifest_kind"] == "npm-workspaces"

    def test_a_project_json_without_nx_json_is_not_nx(self):
        out = mod.detect({"tree": ["apps/shop/project.json"], "manifests": {}})
        assert out["is_monorepo"] is False

    def test_nx_wins_over_a_cargo_workspace_and_flags_it(self):
        out = mod.detect(
            {
                "tree": ["nx.json", "apps/shop/project.json", "Cargo.toml", "crates/a/Cargo.toml"],
                "manifests": {"Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n'},
            }
        )
        assert out["manifest_kind"] == "nx"
        assert any("cargo-workspace" in w for w in out["warnings"])


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

    def test_schema_lists_every_detector_kind(self):
        with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)
        (kinds,) = [option["enum"] for option in schema["properties"]["manifest_kind"]["oneOf"] if "enum" in option]
        assert kinds == [kind for kind, _ in mod.DETECTORS]


# --------------------------------------------------------------------------
# Staged inputs (issue #592): --tree-file, --manifest-files, --manifest-dir
# --------------------------------------------------------------------------

RECOMMENDER_PATH = SCRIPT_PATH.parent / "skf-recommend-scope-type.py"
PNPM_REPO = {
    "package.json": json.dumps({"name": "root", "private": True}),
    "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
    "packages/core/package.json": json.dumps({"name": "@acme/core"}),
    "packages/core/src/index.ts": "export const core = 1;\n",
    "packages/ui/package.json": json.dumps({"name": "@acme/ui"}),
    "packages/ui/src/components/registry.ts": "export const registry = [];\n",
    "docs/guide.md": "# guide\n",
    "README.md": "# acme\n",
}


def _files(root: Path, files: dict[str, str]) -> Path:
    """Write `files` (repo path -> text) under `root` as bytes, a folder laid out like the repository."""
    for rel, text in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


def _listing(tmp_path: Path, paths, name: str = "tree.txt") -> Path:
    """A git ls-files style listing of `paths`, one per line."""
    path = tmp_path / name
    path.write_bytes("".join(f"{p}\n" for p in paths).encode("utf-8"))
    return path


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )


def _out(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout.decode("utf-8"))


class TestStagedInputs:
    def test_a_local_checkout_is_read_through_the_tree_file_and_manifest_dir(self, tmp_path):
        repo = _files(tmp_path / "repo", PNPM_REPO)
        out = _out(run_cli("--tree-file", str(_listing(tmp_path, PNPM_REPO)), "--manifest-dir", str(repo)))
        assert_envelope_shape(out)
        assert out["manifest_kind"] == "pnpm-workspaces"
        # each workspace's own manifest, read from the folder, names it
        assert out["workspaces"] == [
            {"name": "@acme/core", "path": "packages/core", "manifest": "packages/core/package.json"},
            {"name": "@acme/ui", "path": "packages/ui", "manifest": "packages/ui/package.json"},
        ]
        assert out["warnings"] == []

    def test_manifest_files_lists_the_root_manifests_a_loop_fetches(self, tmp_path):
        tree = [*PNPM_REPO, "rush.json", "nx.json", "Cargo.toml", "crates/a/Cargo.toml", "sub/lerna.json"]
        proc = run_cli("--tree-file", str(_listing(tmp_path, tree)), "--manifest-files")
        assert proc.returncode == 0, proc.stderr
        # one path per line with LF endings on every platform, in the detectors' order
        assert proc.stdout == b"package.json\npnpm-workspace.yaml\nrush.json\nCargo.toml\n"

    def test_manifest_files_prints_nothing_without_a_root_manifest(self, tmp_path):
        proc = run_cli("--tree-file", str(_listing(tmp_path, ["src/lib.rs", "packages/a/package.json"])),
                       "--manifest-files")
        assert (proc.returncode, proc.stdout) == (0, b"")

    @pytest.mark.parametrize(
        "extra",
        [
            pytest.param([], id="no-tree-file"),
            pytest.param(["--json", "{}"], id="json"),
            pytest.param(["--manifest-dir", "."], id="manifest-dir"),
            pytest.param(["--snapshot"], id="snapshot"),
        ],
    )
    def test_manifest_files_reads_only_the_tree_file(self, tmp_path, extra):
        tree = [] if extra == [] else ["--tree-file", str(_listing(tmp_path, PNPM_REPO))]
        proc = run_cli(*tree, "--manifest-files", *extra)
        assert proc.returncode == 2
        assert b"--manifest-files" in proc.stderr

    def test_the_fetched_root_manifests_find_the_workspaces(self, tmp_path):
        """A remote repository: the loop fetched only the root manifests, so
        the workspaces are named after their folders."""
        tree_file = _listing(tmp_path, PNPM_REPO)
        fetched = _files(tmp_path / "files", {name: PNPM_REPO[name] for name in ("package.json", "pnpm-workspace.yaml")})
        out = _out(run_cli("--tree-file", str(tree_file), "--manifest-dir", str(fetched)))
        assert out["manifest_kind"] == "pnpm-workspaces"
        assert [(ws["name"], ws["path"]) for ws in out["workspaces"]] == [("core", "packages/core"), ("ui", "packages/ui")]

    def test_a_root_manifest_the_folder_lacks_is_named_in_the_warnings(self, tmp_path):
        """A fetch that failed leaves no file: the npm and pnpm detectors
        cannot run, and the warnings say so instead of a silent miss."""
        out = _out(run_cli("--tree-file", str(_listing(tmp_path, PNPM_REPO)), "--manifest-dir", str(tmp_path / "none")))
        assert out["manifest_kind"] == "generic-folders"
        assert sorted(w.split(" ")[0] for w in out["warnings"]) == ["package.json", "pnpm-workspace.yaml"]
        assert all("content was not supplied" in w and "--manifest-dir" in w for w in out["warnings"])

    def test_a_root_manifest_missing_from_a_payload_is_named(self):
        """The payload path warns too: a Cargo workspace whose Cargo.toml
        content was left out is not detected, and the warning says why."""
        out = mod.detect({"tree": ["Cargo.toml", "crates/a/Cargo.toml", "crates/b/Cargo.toml"], "manifests": {}})
        assert out["is_monorepo"] is False
        assert out["warnings"] == [
            "Cargo.toml is in the tree but its content was not supplied: pass it under manifests "
            "(or with --manifest-dir) so the detectors can read it"
        ]

    def test_the_tree_file_alone_warns_of_every_root_manifest_it_lists(self, tmp_path):
        out = _out(run_cli("--tree-file", str(_listing(tmp_path, [*PNPM_REPO, "Cargo.toml"]))))
        assert sorted(w.split(" ")[0] for w in out["warnings"]) == ["Cargo.toml", "package.json", "pnpm-workspace.yaml"]

    def test_tree_file_dash_reads_the_listing_from_stdin(self):
        manifests = {name: PNPM_REPO[name] for name in ("package.json", "pnpm-workspace.yaml")}
        out = _out(run_cli("--tree-file", "-", "--json", json.dumps({"manifests": manifests}),
                           stdin="\n".join(PNPM_REPO)))
        assert out["manifest_kind"] == "pnpm-workspaces"

    def test_the_tree_file_accepts_the_github_probe_output(self, tmp_path):
        probe = tmp_path / "tree.json"
        probe.write_bytes(json.dumps({"status": "ok", "tree": list(PNPM_REPO), "count": len(PNPM_REPO),
                                      "truncated": False}).encode("utf-8"))
        repo = _files(tmp_path / "repo", PNPM_REPO)
        assert _out(run_cli("--tree-file", str(probe), "--manifest-dir", str(repo)))["manifest_kind"] == "pnpm-workspaces"

    def test_a_failed_listing_exits_2(self, tmp_path):
        probe = tmp_path / "tree.json"
        probe.write_bytes(json.dumps({"status": "unavailable", "message": "o/r has no branch named x."}).encode("utf-8"))
        proc = run_cli("--tree-file", str(probe))
        assert proc.returncode == 2
        assert b"o/r has no branch named x." in proc.stderr and proc.stdout == b""

    @pytest.mark.parametrize(
        "args,stdin,message",
        [
            pytest.param(["--json", json.dumps({"tree": ["a"]})], "", "pass the tree once", id="tree-twice"),
            pytest.param(["--json", json.dumps({"manifests": {}}), "--manifest-dir", "."], "",
                         "pass the manifests once", id="manifests-twice"),
            pytest.param(["--root", "packages/a"], "", "--snapshot", id="root-without-snapshot"),
        ],
    )
    def test_conflicting_inputs_exit_2(self, tmp_path, args, stdin, message):
        proc = run_cli("--tree-file", str(_listing(tmp_path, PNPM_REPO)), *args, stdin=stdin)
        assert proc.returncode == 2
        assert message.encode("utf-8") in proc.stderr

    def test_a_payload_on_stdin_can_take_its_manifests_from_a_folder(self, tmp_path):
        repo = _files(tmp_path / "repo", PNPM_REPO)
        out = _out(run_cli("--manifest-dir", str(repo), stdin=json.dumps({"tree": list(PNPM_REPO)})))
        assert [ws["name"] for ws in out["workspaces"]] == ["@acme/core", "@acme/ui"]

    def test_a_tree_past_10000_files_is_read_whole(self, tmp_path):
        """More than 10,000 files: the second workspace's manifest is the
        last path, so a list cut short would drop it with no error."""
        paths = ["package.json", "pnpm-workspace.yaml", "packages/core/package.json"]
        paths += [f"packages/core/src/m{i // 100}/f{i}.ts" for i in range(12000)]
        paths += ["packages/zeta/package.json"]
        manifests = {name: PNPM_REPO[name] for name in ("package.json", "pnpm-workspace.yaml")}
        out = _out(run_cli("--tree-file", str(_listing(tmp_path, paths)), "--json", json.dumps({"manifests": manifests})))
        assert [ws["path"] for ws in out["workspaces"]] == ["packages/core", "packages/zeta"]
        snap = _out(run_cli("--tree-file", str(_listing(tmp_path, paths)), "--snapshot"))
        assert snap["file_count"] == len(paths)


class TestManifestDir:
    def test_reads_the_named_files_that_fit(self, tmp_path):
        folder = _files(tmp_path / "repo", {"package.json": "{}", "big/package.json": "x"})
        (folder / "latin1.json").write_bytes(b"{\"name\": \"caf\xe9\"}")
        (folder / "bom.json").write_bytes("\ufeff{}".encode("utf-8"))
        (folder / "big" / "package.json").write_bytes(b"x" * (mod.MAX_MANIFEST_BYTES + 1))
        out = mod.read_manifest_dir(str(folder), ["package.json", "latin1.json", "bom.json", "big/package.json",
                                                  "missing.json", "../repo/package.json", "/etc/passwd"])
        # not UTF-8, too large, missing or outside the repository: not supplied
        assert out == {"package.json": "{}", "bom.json": "{}"}


# --------------------------------------------------------------------------
# Tree snapshot (issue #592): the facts the prompts counted by hand
# --------------------------------------------------------------------------


# Layouts built from real repositories' trees (pandas-dev/pandas, numpy/numpy,
# django/django, fastapi/fastapi, lodash/lodash): a name-based module rule
# counted LICENSES, ci, web, branding, requirements, docs_src or build
# tooling as modules there.
PANDAS_TREE = [
    "pyproject.toml", "setup.py", "LICENSES/NUMPY_LICENSE", "LICENSES/PSF_LICENSE",
    "asv_bench/benchmarks/algorithms.py", "ci/code_checks.sh", "ci/deps/actions-311.yaml", "doc/source/conf.py",
    "doc/source/index.rst", "pandas/__init__.py", "pandas/core/frame.py", "pandas/core/series.py",
    "pandas/io/parsers.py", "pandas/io/excel/_base.py", "pandas/plotting/_core.py", "pandas/tests/test_frame.py",
    "subprojects/packagefiles/meson.build", "web/pandas/index.html", "web/pandas_web.py", ".github/workflows/ci.yml",
]
NUMPY_TREE = [
    "pyproject.toml", "branding/logo/numpylogo.svg", "meson_cpu/meson.build", "numpy/__init__.py",
    "numpy/_core/numeric.py", "numpy/linalg/_linalg.py", "pixi-packages/default/pixi.toml",
    "requirements/build_requirements.txt", "tools/refguide_check.py",
]
DJANGO_TREE = [
    "pyproject.toml", "django/__init__.py", "django/db/models/base.py", "django/http/request.py",
    "extras/django_bash_completion", "js_tests/admin/core.test.js", "tests/runtests.py", "tests/basic/tests.py",
    "docs/conf.py",
]
FASTAPI_TREE = [
    "pyproject.toml", "fastapi/__init__.py", "fastapi/routing.py", "fastapi/security/oauth2.py",
    "docs_src/first_steps/tutorial001.py", "docs_src/first_steps/tutorial002.py", "docs_src/body/tutorial001.py",
    "docs/en/docs/index.md", "tests/test_routing.py", "scripts/docs.py",
]
LODASH_TREE = [
    "package.json", "lodash.js", "fp.js", "chunk.js", "lib/main/build-dist.js", "lib/fp/build-dist.js",
    "lib/common/file.js", "test/test.js",
]


def _candidates(out: dict) -> dict[str, tuple[int, int]]:
    return {c["path"]: (c["file_count"], c["source_file_count"]) for c in out["module_candidates"]}


class TestSnapshot:
    def test_a_monorepo_root_lists_its_workspaces(self, tmp_path):
        repo = _files(tmp_path / "repo", PNPM_REPO)
        out = _out(run_cli("--tree-file", str(_listing(tmp_path, PNPM_REPO)), "--manifest-dir", str(repo), "--snapshot"))
        assert out == {
            "root": "",
            "truncated": False,
            "file_count": 8,
            "source_file_count": 2,
            # packages, docs, the two workspaces, their src/ and src/components
            "dir_count": 7,
            "top_level_files": ["README.md", "package.json", "pnpm-workspace.yaml"],
            "top_level_dirs": ["docs", "packages"],
            "manifest_kind": "pnpm-workspaces",
            # each workspace's own manifest, read from the folder, names it
            "workspaces": [
                {"name": "@acme/core", "path": "packages/core", "manifest": "packages/core/package.json"},
                {"name": "@acme/ui", "path": "packages/ui", "manifest": "packages/ui/package.json"},
            ],
            "module_root": "",
            "module_candidates": [
                {"path": "docs", "file_count": 1, "source_file_count": 0},
                {"path": "packages", "file_count": 4, "source_file_count": 2},
            ],
            "registry_candidates": ["packages/ui/src/components/registry.ts"],
            "warnings": [],
        }

    def test_a_workspace_root_lists_its_folders(self, tmp_path):
        out = _out(run_cli("--tree-file", str(_listing(tmp_path, PNPM_REPO)), "--snapshot", "--root", "./packages/ui/"))
        assert (out["root"], out["file_count"], out["source_file_count"], out["top_level_files"],
                out["top_level_dirs"]) == ("packages/ui", 2, 1, ["package.json"], ["src"])
        # detection runs at the repository root only
        assert (out["manifest_kind"], out["workspaces"], out["warnings"]) == (None, [], [])
        # a lone src/components/ is a candidate, not a wrapper to follow down
        assert (out["module_root"], _candidates(out)) == ("packages/ui/src", {"packages/ui/src/components": (1, 1)})
        assert out["registry_candidates"] == ["packages/ui/src/components/registry.ts"]

    @pytest.mark.parametrize(
        "tree,module_root,candidates",
        [
            pytest.param(["package.json", "src/index.ts", "src/auth/a.ts", "src/db/b.ts", "src/db/schema.sql",
                          "src/__tests__/t.ts", "src/.cache/x", "test/e2e.ts"],
                         "src", {"src/__tests__": (1, 1), "src/auth": (1, 1), "src/db": (2, 1)}, id="src-folders"),
            pytest.param(["pyproject.toml", "src/acme/__init__.py", "src/acme/core/a.py", "src/acme/io/b.py",
                          "src/acme/tests/t.py", "tests/test_x.py"],
                         "src/acme", {"src/acme/core": (1, 1), "src/acme/io": (1, 1), "src/acme/tests": (1, 1)},
                         id="python-src-layout"),
            pytest.param(["pom.xml", "src/main/java/com/acme/app/web/W.java", "src/main/java/com/acme/app/db/D.java",
                          "src/main/java/com/acme/app/App.java", "src/main/resources/app.yml",
                          "src/test/java/AppTest.java"],
                         "src/main/java/com/acme/app", {"src/main/java/com/acme/app/db": (1, 1),
                                                        "src/main/java/com/acme/app/web": (1, 1)},
                         id="java-package-chain"),
            pytest.param(["package.json", "src/__testUtils__/expectJSON.ts", "src/graphql/language/lexer.ts",
                          "src/graphql/type/schema.ts"],
                         "src/graphql", {"src/graphql/language": (1, 1), "src/graphql/type": (1, 1)},
                         id="a-test-helper-folder-is-no-wrapper"),
            pytest.param(["package.json", "src/website/index.html", "src/Testing/t.ts", "src/core/sub/a.ts"],
                         "src/core", {"src/core/sub": (1, 1)}, id="names-in-any-case"),
            pytest.param(["go.mod", "api.go", "cmd/tool/main.go", "internal/x/x.go", "docs/d.md",
                          ".github/workflows/ci.yml"],
                         "", {"cmd": (1, 1), "docs": (1, 0), "internal": (1, 1)}, id="root-folders"),
            pytest.param(["Cargo.toml", "src/lib.rs", "src/client.rs"], "src", {}, id="no-folder"),
        ],
    )
    def test_the_module_root_and_its_candidates(self, tree, module_root, candidates):
        out = mod.snapshot(tree, {})
        assert (out["module_root"], _candidates(out)) == (module_root, candidates)

    @pytest.mark.parametrize(
        "tree,candidates",
        [
            pytest.param(PANDAS_TREE, {"LICENSES": (2, 0), "asv_bench": (1, 1), "ci": (2, 0), "doc": (2, 1),
                                       "pandas": (7, 7), "subprojects": (1, 0), "web": (2, 1)}, id="pandas"),
            pytest.param(NUMPY_TREE, {"branding": (1, 0), "meson_cpu": (1, 0), "numpy": (3, 3),
                                      "pixi-packages": (1, 0), "requirements": (1, 0), "tools": (1, 1)}, id="numpy"),
            pytest.param(DJANGO_TREE, {"django": (3, 3), "docs": (1, 1), "extras": (1, 0), "js_tests": (1, 1),
                                       "tests": (2, 2)}, id="django"),
            pytest.param(FASTAPI_TREE, {"docs": (1, 0), "docs_src": (3, 3), "fastapi": (3, 3), "scripts": (1, 1),
                                        "tests": (1, 1)}, id="fastapi"),
        ],
    )
    def test_the_snapshot_names_no_module_and_lists_what_each_folder_holds(self, tree, candidates):
        """Which folders are modules is the caller's judgment: the snapshot
        counts no module, so LICENSES, ci, web, branding, requirements or
        docs_src never becomes one by its name, and lists each candidate
        with the files and source files it holds."""
        out = mod.snapshot(tree, {})
        assert not {"module_count", "module_dirs", "module_basis"} & set(out)
        assert (out["module_root"], _candidates(out)) == ("", candidates)

    def test_a_snapshot_of_the_package_folder_lists_its_own_candidates(self):
        """pandas/ holds most of the source files: a snapshot of it lists
        the subpackages a caller picks the modules from."""
        out = mod.snapshot(PANDAS_TREE, {}, "pandas")
        assert (out["file_count"], out["source_file_count"], out["module_root"]) == (7, 7, "pandas")
        assert _candidates(out) == {"pandas/core": (2, 2), "pandas/io": (2, 2), "pandas/plotting": (1, 1),
                                    "pandas/tests": (1, 1)}

    def test_lib_build_tooling_shows_beside_the_root_sources(self):
        """lodash keeps its sources at the root and its build tooling in
        lib/: the counts show it, so the caller does not read lib/ as the
        library's modules."""
        out = mod.snapshot(LODASH_TREE, {})
        assert (out["source_file_count"], out["module_root"]) == (7, "lib")
        assert _candidates(out) == {"lib/common": (1, 1), "lib/fp": (1, 1), "lib/main": (1, 1)}
        assert out["top_level_files"] == ["chunk.js", "fp.js", "lodash.js", "package.json"]

    def test_a_cut_short_listing_is_reported(self, tmp_path):
        probe = tmp_path / "tree.json"
        probe.write_bytes(json.dumps({"status": "ok", "tree": ["README.md", "src/a/x.ts"], "truncated": True}).encode("utf-8"))
        out = _out(run_cli("--tree-file", str(probe), "--snapshot"))
        assert (out["truncated"], out["file_count"], out["dir_count"]) == (True, 2, 2)
        # outside --snapshot, the warnings say the detection may have missed a workspace
        detected = _out(run_cli("--tree-file", str(probe)))
        assert detected["warnings"] == ["the --tree-file listing was cut short (truncated): a workspace whose "
                                        "manifest it does not list is missed"]

    @pytest.mark.parametrize("snapshot", [pytest.param([], id="detect"), pytest.param(["--snapshot"], id="snapshot")])
    @pytest.mark.parametrize(
        "listing",
        [
            pytest.param(json.dumps({"status": "ok", "repo": "o/r", "tree": [], "count": 0, "truncated": False}),
                         id="probe-with-no-path"),
            pytest.param(json.dumps({"sha": "abc", "tree": [{"path": "src", "type": "tree"}]}), id="no-blob"),
            pytest.param("[]", id="empty-list"),
        ],
    )
    def test_a_listing_that_holds_no_path_exits_2(self, tmp_path, listing, snapshot):
        """Counts of 0 would read as facts: a listing with no file is refused."""
        probe = tmp_path / "tree.json"
        probe.write_bytes(listing.encode("utf-8"))
        proc = run_cli("--tree-file", str(probe), *snapshot)
        assert (proc.returncode, proc.stdout) == (2, b"")
        assert b"holds no file path" in proc.stderr

    def test_the_help_says_a_tree_file_leaves_stdin_unread(self):
        help_text = " ".join(run_cli("--help").stdout.decode("utf-8").split())
        assert "With --tree-file <file>, stdin is not read" in help_text

    def test_the_registry_candidates_follow_the_recommender(self):
        spec_ = importlib.util.spec_from_file_location("skf_recommend_scope_type_for_snapshot", RECOMMENDER_PATH)
        recommender = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(recommender)
        tree = ["registry.ts", "src/ui/components.tsx", "src/registry.js", "../outside/registry.ts",
                "a/registry.tsx", "docs/components.md"]
        out = mod.snapshot(tree, {})
        assert out["registry_candidates"] == recommender._find_registry_files(sorted(set(tree) - {"../outside/registry.ts"}))
        assert out["registry_candidates"] == ["a/registry.tsx", "registry.ts", "src/ui/components.tsx"]

    def test_a_root_the_tree_does_not_hold_exits_2(self, tmp_path):
        proc = run_cli("--tree-file", str(_listing(tmp_path, PNPM_REPO)), "--snapshot", "--root", "packages/nope")
        assert proc.returncode == 2
        assert b"no file under --root packages/nope" in proc.stderr

    def test_a_payload_snapshot_needs_the_payload_shape(self):
        proc = run_cli("--snapshot", stdin=json.dumps({"tree": ["a.py"]}))
        assert proc.returncode == 1
        assert b"manifests" in proc.stderr

    def test_the_installed_layout_needs_its_siblings(self, tmp_path):
        """Installed, --tree-file and --snapshot load skf-detect-language.py
        and skf-recommend-scope-type.py from beside the script."""
        scripts = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("skf-detect-workspaces.py", "skf-detect-language.py", "skf-recommend-scope-type.py"):
            (scripts / name).write_bytes((SCRIPT_PATH.parent / name).read_bytes())
        tree_file = _listing(tmp_path, PNPM_REPO)
        installed = [sys.executable, str(scripts / "skf-detect-workspaces.py")]
        proc = subprocess.run([*installed, "--tree-file", str(tree_file), "--snapshot"], capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["registry_candidates"] == ["packages/ui/src/components/registry.ts"]
        (scripts / "skf-detect-language.py").unlink()
        proc = subprocess.run([*installed, "--tree-file", str(tree_file)], capture_output=True, timeout=60)
        assert proc.returncode == 2
        assert b"cannot load skf-detect-language.py" in proc.stderr
        # a payload snapshot counts source files with it too
        payload = json.dumps({"tree": list(PNPM_REPO), "manifests": {}})
        proc = subprocess.run([*installed, "--snapshot", "--json", payload], capture_output=True, timeout=60)
        assert proc.returncode == 2
        assert b"cannot load skf-detect-language.py" in proc.stderr
