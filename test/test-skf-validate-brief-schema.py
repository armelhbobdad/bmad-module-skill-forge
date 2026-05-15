#!/usr/bin/env python3
"""Tests for skf-validate-brief-schema.py.

Covers:
  - happy path: valid brief returns valid=true, errors=[], halt_reason=null
  - schema violations: missing required field, bad pattern, bad enum,
    bad type, empty string, empty array
  - conditional rules: docs-only requires doc_urls; docs-only with
    non-community source_authority emits warning
  - version non-empty rule (whitespace-only version)
  - load errors: missing file, malformed YAML, non-mapping YAML
  - CLI: path argument, stdin via `-`, --yaml inline
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-validate-brief-schema.py"

spec = importlib.util.spec_from_file_location("skf_validate_brief_schema", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _valid_brief() -> dict:
    """Minimal valid brief — every required schema field present."""
    return {
        "name": "my-skill",
        "version": "1.0.0",
        "source_repo": "https://github.com/foo/bar",
        "language": "python",
        "description": "Compiles things from sources.",
        "forge_tier": "Forge",
        "created": "2026-05-15",
        "created_by": "armel",
        "scope": {
            "type": "public-api",
            "include": ["src/**"],
            "exclude": ["**/test_*"],
            "notes": "",
        },
    }


# --------------------------------------------------------------------------
# validate_brief — happy path
# --------------------------------------------------------------------------


class TestHappyPath:
    def test_minimal_valid_brief(self) -> None:
        result = mod.validate_brief(_valid_brief())
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_with_optional_fields(self) -> None:
        brief = _valid_brief()
        brief["target_version"] = "1.0.0"
        brief["scripts_intent"] = "detect"
        brief["assets_intent"] = "detect"
        result = mod.validate_brief(brief)
        assert result["valid"] is True


# --------------------------------------------------------------------------
# Schema violations
# --------------------------------------------------------------------------


class TestSchemaViolations:
    def test_missing_required_field_emits_friendly_error(self) -> None:
        brief = _valid_brief()
        del brief["language"]
        result = mod.validate_brief(brief)
        assert result["valid"] is False
        msgs = [e["message"] for e in result["errors"]]
        assert any("missing required field `language`" in m for m in msgs)

    def test_bad_name_pattern(self) -> None:
        brief = _valid_brief()
        brief["name"] = "Bad Skill Name"
        result = mod.validate_brief(brief)
        assert result["valid"] is False
        err = next(e for e in result["errors"] if e["field"] == "name")
        assert "does not match required pattern" in err["message"]
        assert "Bad Skill Name" in err["message"]

    def test_bad_forge_tier_enum(self) -> None:
        brief = _valid_brief()
        brief["forge_tier"] = "Bogus"
        result = mod.validate_brief(brief)
        err = next(e for e in result["errors"] if e["field"] == "forge_tier")
        assert "is not one of" in err["message"]
        assert "Quick" in err["message"]

    def test_bad_scope_type_enum(self) -> None:
        brief = _valid_brief()
        brief["scope"]["type"] = "made-up"
        result = mod.validate_brief(brief)
        assert any(
            e["field"] == "scope.type" and "is not one of" in e["message"]
            for e in result["errors"]
        )

    def test_wrong_field_type(self) -> None:
        brief = _valid_brief()
        brief["language"] = 42
        result = mod.validate_brief(brief)
        err = next(e for e in result["errors"] if e["field"] == "language")
        assert "expected `string`" in err["message"]

    def test_empty_string_min_length(self) -> None:
        brief = _valid_brief()
        brief["source_repo"] = ""
        result = mod.validate_brief(brief)
        assert any(
            e["field"] == "source_repo" and "must be non-empty" in e["message"]
            for e in result["errors"]
        )

    def test_bad_version_pattern(self) -> None:
        brief = _valid_brief()
        brief["version"] = "not-semver"
        result = mod.validate_brief(brief)
        assert any(e["field"] == "version" for e in result["errors"])


# --------------------------------------------------------------------------
# docs-only conditional rules
# --------------------------------------------------------------------------


class TestDocsOnlyRules:
    def test_docs_only_without_doc_urls_errors(self) -> None:
        brief = _valid_brief()
        brief["source_type"] = "docs-only"
        result = mod.validate_brief(brief)
        assert result["valid"] is False
        err = next(e for e in result["errors"] if e["field"] == "doc_urls")
        assert "at least one entry" in err["message"]

    def test_docs_only_empty_doc_urls_errors(self) -> None:
        brief = _valid_brief()
        brief["source_type"] = "docs-only"
        brief["doc_urls"] = []
        result = mod.validate_brief(brief)
        # schema's minItems catches empty array; our docs-only rule also fires.
        # Both errors are surfaced — that's fine, the user fixes one source.
        assert any(e["field"] == "doc_urls" for e in result["errors"])

    def test_docs_only_with_doc_urls_valid(self) -> None:
        brief = _valid_brief()
        brief["source_type"] = "docs-only"
        brief["doc_urls"] = [{"url": "https://example.com/docs"}]
        result = mod.validate_brief(brief)
        # docs-only conditional check passes; remaining schema rules satisfied
        assert result["valid"] is True

    def test_docs_only_non_community_authority_warns(self) -> None:
        brief = _valid_brief()
        brief["source_type"] = "docs-only"
        brief["doc_urls"] = [{"url": "https://example.com/docs"}]
        brief["source_authority"] = "official"
        result = mod.validate_brief(brief)
        assert result["valid"] is True  # warnings don't invalidate
        assert any(
            w["field"] == "source_authority"
            and "treated as `community`" in w["message"]
            for w in result["warnings"]
        )

    def test_non_docs_only_no_conditional_checks(self) -> None:
        # source_type=source (default) doesn't trigger docs-only rules
        brief = _valid_brief()
        brief["source_authority"] = "official"  # would warn under docs-only
        result = mod.validate_brief(brief)
        assert result["warnings"] == []


# --------------------------------------------------------------------------
# Version non-empty rule
# --------------------------------------------------------------------------


class TestVersionNonEmpty:
    def test_whitespace_only_version_errors(self) -> None:
        brief = _valid_brief()
        # whitespace-only string slips past the schema's pattern regex —
        # well, actually the schema rejects it too via pattern, but we surface
        # an explicit friendly message
        brief["version"] = "   "
        result = mod.validate_brief(brief)
        # check our explicit rule fired (skill-friendly message)
        version_errs = [e for e in result["errors"] if e["field"] == "version"]
        # at least one should mention "required and must be non-empty"
        assert any("required and must be non-empty" in e["message"] for e in version_errs)


# --------------------------------------------------------------------------
# load_brief_text
# --------------------------------------------------------------------------


class TestLoadBriefText:
    def test_valid_yaml(self) -> None:
        brief, err = mod.load_brief_text("name: foo\nversion: 1.0.0\n")
        assert err is None
        assert brief == {"name": "foo", "version": "1.0.0"}

    def test_malformed_yaml(self) -> None:
        brief, err = mod.load_brief_text("name: : :\n  bad indent")
        assert brief is None
        assert "not valid YAML" in err

    def test_empty_yaml(self) -> None:
        brief, err = mod.load_brief_text("")
        assert brief is None
        assert "empty" in err

    def test_non_mapping_yaml(self) -> None:
        brief, err = mod.load_brief_text("- just\n- a list\n")
        assert brief is None
        assert "must be a YAML mapping" in err


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _valid_yaml_text() -> str:
    import yaml as _yaml

    return _yaml.safe_dump(_valid_brief(), sort_keys=False)


class TestCli:
    def test_valid_path_exits_0(self, tmp_path: Path) -> None:
        brief_path = tmp_path / "skill-brief.yaml"
        brief_path.write_text(_valid_yaml_text(), encoding="utf-8")
        result = _run_cli(str(brief_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert payload["halt_reason"] is None
        assert payload["brief"]["name"] == "my-skill"

    def test_invalid_path_exits_1(self, tmp_path: Path) -> None:
        brief_path = tmp_path / "skill-brief.yaml"
        bad = _valid_brief()
        bad["name"] = "Bad Name"
        import yaml as _yaml

        brief_path.write_text(_yaml.safe_dump(bad), encoding="utf-8")
        result = _run_cli(str(brief_path))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["valid"] is False
        assert payload["halt_reason"] == "brief-invalid"

    def test_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(str(tmp_path / "nope.yaml"))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["halt_reason"] == "brief-missing"
        assert "Run [BS] Brief Skill" in payload["errors"][0]["message"]

    def test_malformed_yaml_exits_1(self, tmp_path: Path) -> None:
        brief_path = tmp_path / "skill-brief.yaml"
        brief_path.write_text("name: : :\n  bad", encoding="utf-8")
        result = _run_cli(str(brief_path))
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["halt_reason"] == "brief-malformed"

    def test_stdin_dash(self) -> None:
        result = _run_cli("-", stdin=_valid_yaml_text())
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["valid"] is True

    def test_yaml_flag_inline(self) -> None:
        result = _run_cli("--yaml", _valid_yaml_text())
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["valid"] is True

    def test_no_args_exits_2(self) -> None:
        # argparse missing-required exits 2
        result = _run_cli()
        assert result.returncode == 2
