#!/usr/bin/env python3
"""Tests for skf-validate-brief-inputs.py.

The validator is pure — it parses a dict and returns a result envelope.
Tests build payloads inline and call validate() directly.
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
    / "skf-validate-brief-inputs.py"
)

spec = importlib.util.spec_from_file_location("skf_validate_brief_inputs", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Required fields
# --------------------------------------------------------------------------


class TestRequiredFields:
    def test_both_required_present_minimal_valid(self):
        out = mod.validate({"target_repo": "https://github.com/foo/bar", "skill_name": "foo-bar"})
        assert out["valid"] is True
        assert out["errors"] == []
        assert out["halt_reason"] is None

    def test_missing_target_repo_halts_input_missing(self):
        out = mod.validate({"skill_name": "foo-bar"})
        assert out["valid"] is False
        assert any(e["field"] == "target_repo" for e in out["errors"])
        assert out["halt_reason"] == "input-missing"

    def test_missing_skill_name_halts_input_missing(self):
        out = mod.validate({"target_repo": "https://github.com/foo/bar"})
        assert out["valid"] is False
        assert any(e["field"] == "skill_name" for e in out["errors"])
        assert out["halt_reason"] == "input-missing"

    def test_both_missing_emits_two_errors(self):
        out = mod.validate({})
        assert out["valid"] is False
        fields = {e["field"] for e in out["errors"]}
        assert {"target_repo", "skill_name"}.issubset(fields)

    def test_both_missing_halt_reason_is_input_missing(self):
        out = mod.validate({})
        assert out["halt_reason"] == "input-missing"

    def test_missing_required_plus_invalid_enum_prefers_input_missing(self):
        # target_repo absent + scope_type invalid — "missing" should dominate
        out = mod.validate({"skill_name": "foo", "scope_type": "not-real"})
        assert out["valid"] is False
        assert out["halt_reason"] == "input-missing"


# --------------------------------------------------------------------------
# skill_name format
# --------------------------------------------------------------------------


class TestSkillNameFormat:
    @pytest.mark.parametrize("name", ["foo", "foo-bar", "foo-bar-baz", "foo123", "a", "a1-b2"])
    def test_valid_kebab(self, name):
        out = mod.validate({"target_repo": "/x", "skill_name": name})
        assert out["valid"] is True

    @pytest.mark.parametrize(
        "name",
        ["FooBar", "foo_bar", "Foo-Bar", "-foo", "foo-", "foo bar", "foo.bar", ""],
    )
    def test_invalid_kebab(self, name):
        out = mod.validate({"target_repo": "/x", "skill_name": name})
        if name == "":
            # Empty string falls under "missing" path, not "format" path
            assert out["valid"] is False
            assert any(e["field"] == "skill_name" for e in out["errors"])
        else:
            assert out["valid"] is False
            assert any(
                e["field"] == "skill_name" and "kebab-case" in e["message"]
                for e in out["errors"]
            )


# --------------------------------------------------------------------------
# source_type / source_authority enums
# --------------------------------------------------------------------------


class TestEnums:
    def test_source_type_default_source(self):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo"})
        assert out["normalized"]["source_type"] == "source"

    def test_source_type_invalid(self):
        out = mod.validate(
            {"target_repo": "/x", "skill_name": "foo", "source_type": "weird"}
        )
        assert out["valid"] is False
        assert any(e["field"] == "source_type" for e in out["errors"])
        assert out["halt_reason"] == "input-invalid"

    def test_source_authority_default_community(self):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo"})
        assert out["normalized"]["source_authority"] == "community"

    def test_source_authority_invalid(self):
        out = mod.validate(
            {
                "target_repo": "/x",
                "skill_name": "foo",
                "source_authority": "rogue",
            }
        )
        assert out["valid"] is False
        assert any(e["field"] == "source_authority" for e in out["errors"])

    def test_scope_type_when_set_must_be_valid(self):
        out = mod.validate(
            {
                "target_repo": "/x",
                "skill_name": "foo",
                "scope_type": "not-a-real-type",
            }
        )
        assert out["valid"] is False
        assert any(e["field"] == "scope_type" for e in out["errors"])

    @pytest.mark.parametrize(
        "scope_type",
        [
            "full-library",
            "specific-modules",
            "public-api",
            "component-library",
            "reference-app",
            "docs-only",
        ],
    )
    def test_scope_type_all_six_valid(self, scope_type):
        out = mod.validate(
            {"target_repo": "/x", "skill_name": "foo", "scope_type": scope_type}
        )
        assert out["valid"] is True


# --------------------------------------------------------------------------
# target_version semver
# --------------------------------------------------------------------------


class TestTargetVersion:
    @pytest.mark.parametrize(
        "v",
        [
            "1.2.3",
            "1.2.3-rc.1",
            "1.2.3+build.5",
            "1.0.0-alpha+001",
            "v1.2.3",
            "1.2.3.dev1",
            "2024.04.01",  # CalVer — three numeric components
        ],
    )
    def test_valid_semver_forms(self, v):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo", "target_version": v})
        assert out["valid"] is True, f"expected {v!r} to validate; got {out['errors']}"

    @pytest.mark.parametrize(
        "v",
        ["1", "1.2", "v2", "latest", "next", "abc", ".1.2", "1.2.x"],
    )
    def test_invalid_semver_forms(self, v):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo", "target_version": v})
        assert out["valid"] is False, f"expected {v!r} to be rejected"
        assert any(e["field"] == "target_version" for e in out["errors"])

    def test_target_version_must_be_string(self):
        out = mod.validate(
            {"target_repo": "/x", "skill_name": "foo", "target_version": 1.2}
        )
        assert out["valid"] is False
        assert any(e["field"] == "target_version" for e in out["errors"])


# --------------------------------------------------------------------------
# docs-only conditional
# --------------------------------------------------------------------------


class TestDocsOnlyConditional:
    def test_docs_only_without_doc_urls_errors(self):
        out = mod.validate(
            {
                "target_repo": "https://docs.example.com",
                "skill_name": "foo",
                "source_type": "docs-only",
            }
        )
        assert out["valid"] is False
        assert any(e["field"] == "doc_urls" for e in out["errors"])
        assert out["halt_reason"] == "input-missing"

    def test_docs_only_with_doc_urls_valid(self):
        out = mod.validate(
            {
                "target_repo": "https://docs.example.com",
                "skill_name": "foo",
                "source_type": "docs-only",
                "doc_urls": ["https://docs.example.com/api"],
            }
        )
        assert out["valid"] is True

    def test_docs_only_forces_community_authority(self):
        out = mod.validate(
            {
                "target_repo": "https://docs.example.com",
                "skill_name": "foo",
                "source_type": "docs-only",
                "doc_urls": ["https://docs.example.com/api"],
                "source_authority": "official",
            }
        )
        assert out["valid"] is True
        assert out["normalized"]["source_authority"] == "community"
        assert any(
            w["field"] == "source_authority" and "forced" in w["message"]
            for w in out["warnings"]
        )


# --------------------------------------------------------------------------
# target_repo shape (warning, not error)
# --------------------------------------------------------------------------


class TestTargetRepoShape:
    @pytest.mark.parametrize(
        "tr",
        [
            "https://github.com/foo/bar",
            "http://example.com",
            "/abs/path/to/repo",
            "./relative/path",
            "~/home/path",
        ],
    )
    def test_recognized_shapes_no_warning(self, tr):
        out = mod.validate({"target_repo": tr, "skill_name": "foo"})
        assert out["valid"] is True
        assert not any(w["field"] == "target_repo" for w in out["warnings"])

    def test_garbage_target_repo_warns_but_passes(self):
        out = mod.validate({"target_repo": "blarg", "skill_name": "foo"})
        # Still valid (HEAD-check is the workflow's job, not the validator's)
        assert out["valid"] is True
        assert any(w["field"] == "target_repo" for w in out["warnings"])


# --------------------------------------------------------------------------
# Defaults applied to normalized output
# --------------------------------------------------------------------------


class TestNormalization:
    def test_defaults_applied(self):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo"})
        n = out["normalized"]
        assert n["source_type"] == "source"
        assert n["source_authority"] == "community"
        assert n["scripts_intent"] == "detect"
        assert n["assets_intent"] == "detect"

    def test_supplied_values_override_defaults(self):
        out = mod.validate(
            {
                "target_repo": "/x",
                "skill_name": "foo",
                "scripts_intent": "none",
                "assets_intent": "templates only",
            }
        )
        n = out["normalized"]
        assert n["scripts_intent"] == "none"
        assert n["assets_intent"] == "templates only"


# --------------------------------------------------------------------------
# Unknown fields
# --------------------------------------------------------------------------


class TestUnknownFields:
    def test_unknown_field_warns_but_passes(self):
        out = mod.validate(
            {
                "target_repo": "/x",
                "skill_name": "foo",
                "totally_unknown_arg": "value",
            }
        )
        assert out["valid"] is True
        assert any(
            w["field"] == "totally_unknown_arg" for w in out["warnings"]
        )


# --------------------------------------------------------------------------
# CLI integration (subprocess)
# --------------------------------------------------------------------------


class TestCLI:
    def _run(self, payload: dict, via_stdin: bool = False) -> tuple[int, dict]:
        if via_stdin:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
            )
        else:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--json", json.dumps(payload)],
                capture_output=True,
                text=True,
            )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc.returncode, out

    def test_cli_exits_0_on_valid(self):
        code, out = self._run({"target_repo": "/x", "skill_name": "foo"})
        assert code == 0
        assert out["valid"] is True

    def test_cli_exits_1_on_invalid(self):
        code, out = self._run({"skill_name": "foo"})
        assert code == 1
        assert out["valid"] is False
        assert out["halt_reason"] == "input-missing"

    def test_cli_exits_2_on_bad_json(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--json", "not-json"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2
        assert "invalid JSON" in proc.stderr

    def test_cli_accepts_stdin(self):
        code, out = self._run(
            {"target_repo": "/x", "skill_name": "foo"}, via_stdin=True
        )
        assert code == 0
        assert out["valid"] is True
