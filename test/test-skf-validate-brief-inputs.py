#!/usr/bin/env python3
"""Tests for skf-validate-brief-inputs.py.

The validator is pure — it parses a dict and returns a result envelope.
Tests build payloads inline and call validate() directly.
"""

from __future__ import annotations

import importlib.util
import json
import os
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

    def test_source_authority_absent_when_not_supplied_for_source(self):
        # source_authority is intentionally left absent so step 1 §3.3's headless
        # detection branch (gh api user vs repo owner) can run.
        out = mod.validate({"target_repo": "/x", "skill_name": "foo"})
        assert "source_authority" not in out["normalized"]

    def test_source_authority_forced_community_for_docs_only_when_absent(self):
        out = mod.validate(
            {
                "target_repo": "/x",
                "skill_name": "foo",
                "source_type": "docs-only",
                "doc_urls": ["https://docs.example.com"],
            }
        )
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
        # reference-app needs include (TestReferenceAppConditional); every type takes one
        out = mod.validate(
            {"target_repo": "/x", "skill_name": "foo", "scope_type": scope_type, "include": "src/**"}
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

    @pytest.mark.parametrize(
        "v,kind",
        [("18", "a major version"), ("v2", "a major version"), ("4.2", "a major and minor version"),
         ("v1.2", "a major and minor version")],
    )
    def test_a_partial_pin_is_named_as_one(self, v, kind):
        """parse-target hands back `react@18` as '18': the error says what the pin lacks."""
        out = mod.validate({"target_repo": "/x", "skill_name": "foo", "target_version": v})
        [error] = out["errors"]
        assert error["message"] == f"target_version {v!r} is {kind} only: {mod.FULL_FORM}"
        assert out["halt_reason"] == "input-invalid"

    @pytest.mark.parametrize("v", ["latest", "1.2.x", "V1.2.3"])
    def test_a_value_that_is_no_pin_says_so(self, v):
        [error] = mod.validate({"target_repo": "/x", "skill_name": "foo", "target_version": v})["errors"]
        assert error["message"] == f"target_version {v!r} does not look like semver: {mod.FULL_FORM}"


# --------------------------------------------------------------------------
# Field-only mode (--only): one value checked before the rest is known
# --------------------------------------------------------------------------


class TestFieldOnly:
    def test_a_full_version_alone_is_valid(self):
        out = mod.validate_fields({"target_version": "18.3.1"}, ["target_version"])
        assert out == {"valid": True, "errors": [], "warnings": [],
                       "normalized": {"target_version": "18.3.1"}, "halt_reason": None}

    def test_a_partial_pin_alone_is_invalid_and_named(self):
        out = mod.validate_fields({"target_version": "18"}, ["target_version"])
        assert out["valid"] is False and out["halt_reason"] == "input-invalid"
        assert [e["field"] for e in out["errors"]] == ["target_version"]
        assert "'18' is a major version only" in out["errors"][0]["message"]

    def test_the_required_arguments_are_not_checked(self):
        """validate() on the same payload halts input-missing for target_repo and skill_name."""
        payload = {"target_version": "1.2.3"}
        assert mod.validate(payload)["halt_reason"] == "input-missing"
        assert mod.validate_fields(payload, ["target_version"])["valid"] is True

    def test_another_fields_finding_is_left_out(self):
        payload = {"target_version": "1.2.3", "scope_type": "bogus", "extra": 1}
        out = mod.validate_fields(payload, ["target_version"])
        assert out["valid"] is True and out["warnings"] == []
        assert out["normalized"] == {"target_version": "1.2.3"}

    def test_an_absent_field_has_nothing_to_check(self):
        out = mod.validate_fields({}, ["target_version"])
        assert out["valid"] is True and out["normalized"] == {}

    @pytest.mark.parametrize("field", ["target_repo", "skill_name"])
    def test_a_named_required_field_is_still_required(self, field):
        """Only the required checks of fields not named are skipped: naming one keeps validate()'s verdict on it."""
        out = mod.validate_fields({}, [field])
        assert out["valid"] is False and out["halt_reason"] == "input-missing"
        assert [e["field"] for e in out["errors"]] == [field]

    def test_several_fields_are_checked_together(self):
        out = mod.validate_fields({"target_version": "1.2", "skill_name": "Foo"}, ["target_version", "skill_name"])
        assert sorted(e["field"] for e in out["errors"]) == ["skill_name", "target_version"]

    def test_the_check_is_the_one_a_headless_argument_gets(self):
        """One rule for a typed, a pre-filled and a headless version: the field-only verdict is validate()'s."""
        for v in ("1", "1.2", "v2", "latest", "1.2.3", "v1.2.3-rc.1", "2024.04.01", "1.2.3.dev1"):
            full = mod.validate({"target_repo": "/x", "skill_name": "foo", "target_version": v})
            only = mod.validate_fields({"target_version": v}, ["target_version"])
            assert only["valid"] is full["valid"] and only["errors"] == full["errors"], v


# --------------------------------------------------------------------------
# reference-app conditional
# --------------------------------------------------------------------------


class TestReferenceAppConditional:
    """A reference app's pattern surface is the caller's to name: step 3 has no headless boundary
    default for it, so the input gate stops the run before step 2 reads the target."""

    def test_reference_app_without_include_is_input_missing(self):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo", "scope_type": "reference-app"})
        assert out["valid"] is False
        assert [e["field"] for e in out["errors"]] == ["include"]
        assert out["halt_reason"] == "input-missing"

    @pytest.mark.parametrize("include", [pytest.param("", id="empty"), pytest.param(None, id="null")])
    def test_an_empty_include_names_no_pattern_surface(self, include):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo", "scope_type": "reference-app",
                            "include": include})
        assert out["halt_reason"] == "input-missing"

    def test_reference_app_with_include_is_valid(self):
        out = mod.validate({"target_repo": "/x", "skill_name": "foo", "scope_type": "reference-app",
                            "include": "src/main/**,electron.vite.config.ts"})
        assert out["valid"] is True

    def test_the_ratify_route_takes_the_scope_from_the_brief(self):
        out = mod.validate({"from_brief": "/briefs/app", "scope_type": "reference-app"})
        assert out["valid"] is True


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
        # source_authority is NOT defaulted here — see test_source_authority_absent_when_not_supplied_for_source
        assert "source_authority" not in n
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
# from_brief ratify route
# --------------------------------------------------------------------------


class TestFromBrief:
    def test_from_brief_alone_is_valid(self):
        # Ratify route: from_brief is the source of truth; target_repo and
        # skill_name are derived from the brief, so neither is required.
        out = mod.validate({"from_brief": "/forge-data/marked/skill-brief.yaml"})
        assert out["valid"] is True
        assert out["errors"] == []
        assert out["halt_reason"] is None

    def test_from_brief_is_a_known_field(self):
        # Recognized → no unrecognized-field warning.
        out = mod.validate({"from_brief": "/x/skill-brief.yaml"})
        assert not any(w["field"] == "from_brief" for w in out["warnings"])

    def test_from_brief_preserved_in_normalized(self):
        out = mod.validate({"from_brief": "/x/skill-brief.yaml"})
        assert out["normalized"]["from_brief"] == "/x/skill-brief.yaml"

    def test_from_brief_directory_path_is_valid(self):
        # A directory containing skill-brief.yaml is an accepted shape — the
        # GATE resolves <dir>/skill-brief.yaml; the validator only checks shape.
        out = mod.validate({"from_brief": "/forge-data/marked"})
        assert out["valid"] is True

    def test_empty_from_brief_halts_input_missing(self):
        out = mod.validate({"from_brief": ""})
        assert out["valid"] is False
        assert any(e["field"] == "from_brief" for e in out["errors"])
        assert out["halt_reason"] == "input-missing"

    def test_whitespace_from_brief_halts_input_missing(self):
        out = mod.validate({"from_brief": "   "})
        assert out["valid"] is False
        assert any(e["field"] == "from_brief" for e in out["errors"])
        assert out["halt_reason"] == "input-missing"

    def test_non_string_from_brief_halts_input_invalid(self):
        out = mod.validate({"from_brief": 123})
        assert out["valid"] is False
        assert any(e["field"] == "from_brief" for e in out["errors"])
        assert out["halt_reason"] == "input-invalid"

    def test_null_from_brief_treated_as_absent(self):
        # from_brief: null → not a ratify run → derive-route requirements apply.
        out = mod.validate({"from_brief": None})
        assert out["valid"] is False
        fields = {e["field"] for e in out["errors"]}
        assert {"target_repo", "skill_name"}.issubset(fields)
        assert out["halt_reason"] == "input-missing"

    def test_from_brief_precedence_warns_on_target_repo(self):
        out = mod.validate(
            {"from_brief": "/x/skill-brief.yaml", "target_repo": "https://github.com/foo/bar"}
        )
        assert out["valid"] is True
        assert any(
            w["field"] == "target_repo" and "ignored" in w["message"]
            for w in out["warnings"]
        )

    def test_from_brief_precedence_warns_on_skill_name(self):
        out = mod.validate(
            {"from_brief": "/x/skill-brief.yaml", "skill_name": "foo-bar"}
        )
        assert out["valid"] is True
        assert any(
            w["field"] == "skill_name" and "ignored" in w["message"]
            for w in out["warnings"]
        )

    def test_from_brief_ignores_non_kebab_skill_name(self):
        # skill_name is derived from the brief on the ratify route, so a
        # malformed value passed alongside from_brief is ignored, not an error.
        out = mod.validate(
            {"from_brief": "/x/skill-brief.yaml", "skill_name": "Not_Kebab"}
        )
        assert out["valid"] is True
        assert not any(e["field"] == "skill_name" for e in out["errors"])

    def test_from_brief_with_docs_only_arg_does_not_require_doc_urls(self):
        # On the ratify route the brief on disk is the source of truth for
        # source_type/doc_urls — a redundant `source_type: docs-only` arg must
        # not HALT a run whose doc_urls live in the brief, not the args.
        out = mod.validate(
            {"from_brief": "/x/skill-brief.yaml", "source_type": "docs-only"}
        )
        assert out["valid"] is True
        assert not any(e["field"] == "doc_urls" for e in out["errors"])

    def test_from_brief_with_garbage_target_repo_no_shape_warning(self):
        # target_repo is ignored on the ratify route — only the single "ignored"
        # warning fires, not the additional URL/path shape warning.
        out = mod.validate(
            {"from_brief": "/x/skill-brief.yaml", "target_repo": "blarg"}
        )
        assert out["valid"] is True
        tr_warnings = [w for w in out["warnings"] if w["field"] == "target_repo"]
        assert len(tr_warnings) == 1
        assert "ignored" in tr_warnings[0]["message"]


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

    def test_cli_from_brief_exits_0(self):
        code, out = self._run({"from_brief": "/forge-data/marked/skill-brief.yaml"})
        assert code == 0
        assert out["valid"] is True

    def test_cli_empty_from_brief_exits_1(self):
        code, out = self._run({"from_brief": ""})
        assert code == 1
        assert out["valid"] is False
        assert out["halt_reason"] == "input-missing"

    @pytest.mark.parametrize("version,code", [("18", 1), ("4.2", 1), ("18.3.1", 0)])
    def test_cli_only_checks_the_named_field(self, version, code):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--only", "target_version"],
            input=json.dumps({"target_version": version}),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == code, proc.stderr
        out = json.loads(proc.stdout)
        assert out["valid"] is (code == 0)
        assert all(e["field"] == "target_version" for e in out["errors"])

    def test_cli_only_refuses_a_field_it_does_not_know(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--only", "version", "--json", "{}"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2 and "invalid choice" in proc.stderr

    def test_cli_reads_non_ascii_stdin_as_utf8(self):
        """A Windows console leaves stdin as cp1252 (PYTHONIOENCODING stands
        in for it here); the script still reads its UTF-8 JSON as UTF-8."""
        payload = {"target_repo": "/home/zoë/dépôt", "skill_name": "foo",
                   "intent": "Analyse des données, déjà vu: 日本語"}
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )
        assert proc.returncode == 0, proc.stderr
        normalized = json.loads(proc.stdout)["normalized"]
        assert normalized["intent"] == payload["intent"]
        assert normalized["target_repo"] == payload["target_repo"]
