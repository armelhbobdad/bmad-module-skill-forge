#!/usr/bin/env python3
"""Tests for skf-write-skill-brief.py.

Pure functions (resolve_version, validate_context, assemble_brief,
render_yaml) are exercised inline. The atomic write is exercised
via subprocess against a tempfile target.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-write-skill-brief.py"
)

spec = importlib.util.spec_from_file_location("skf_write_skill_brief", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _baseline_ctx() -> dict:
    return {
        "name": "marked",
        "source_repo": "https://github.com/markedjs/marked",
        "language": "javascript",
        "description": "Render Markdown to HTML using the marked library.",
        "forge_tier": "Quick",
        "created": "2026-05-02",
        "created_by": "armel",
        "scope": {
            "type": "full-library",
            "include": ["src/**/*.ts"],
            "exclude": ["**/*.test.*"],
            "notes": "",
        },
    }


@pytest.fixture
def tmp_target():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "marked" / "skill-brief.yaml"


# --------------------------------------------------------------------------
# resolve_version()
# --------------------------------------------------------------------------


class TestResolveVersion:
    def test_explicit_version_resolved_wins(self):
        assert mod.resolve_version({
            "version_resolved": "9.9.9",
            "target_version": "1.0.0",
            "detected_version": "2.0.0",
        }) == "9.9.9"

    def test_target_version_beats_detected(self):
        assert mod.resolve_version({
            "target_version": "1.0.0",
            "detected_version": "2.0.0",
        }) == "1.0.0"

    def test_detected_used_when_no_target(self):
        assert mod.resolve_version({"detected_version": "2.0.0"}) == "2.0.0"

    def test_default_when_nothing_supplied(self):
        assert mod.resolve_version({}) == "1.0.0"


# --------------------------------------------------------------------------
# validate_context() — happy + sad paths
# --------------------------------------------------------------------------


class TestValidateContextHappy:
    def test_minimal_baseline_passes(self):
        warnings = mod.validate_context(_baseline_ctx())
        assert warnings == []


class TestValidateContextRequiredFields:
    @pytest.mark.parametrize(
        "field",
        ["name", "source_repo", "language", "description", "forge_tier", "created", "created_by"],
    )
    def test_missing_required_field_fails(self, field):
        ctx = _baseline_ctx()
        del ctx[field]
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_missing_scope_fails(self):
        ctx = _baseline_ctx()
        del ctx["scope"]
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_scope_missing_subkey_fails(self):
        ctx = _baseline_ctx()
        del ctx["scope"]["notes"]
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)


class TestValidateContextEnumsAndFormats:
    def test_name_must_be_kebab(self):
        ctx = _baseline_ctx()
        ctx["name"] = "Marked_JS"
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    @pytest.mark.parametrize("tier", ["quick", "DEEP", "Forge2", "weird"])
    def test_forge_tier_invalid(self, tier):
        ctx = _baseline_ctx()
        ctx["forge_tier"] = tier
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    @pytest.mark.parametrize("d", ["2026/05/02", "May 2 2026", "2026-5-2", "20260502"])
    def test_created_must_be_iso(self, d):
        ctx = _baseline_ctx()
        ctx["created"] = d
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    @pytest.mark.parametrize("st", ["src", "binary", "remote"])
    def test_source_type_invalid(self, st):
        ctx = _baseline_ctx()
        ctx["source_type"] = st
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    @pytest.mark.parametrize(
        "scope_type",
        ["full-library", "specific-modules", "public-api", "component-library", "reference-app", "docs-only"],
    )
    def test_scope_type_all_six_valid(self, scope_type):
        ctx = _baseline_ctx()
        ctx["scope"]["type"] = scope_type
        mod.validate_context(ctx)  # should not raise

    def test_scope_type_invalid(self):
        ctx = _baseline_ctx()
        ctx["scope"]["type"] = "made-up"
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)


class TestValidateContextDocsOnlyConditional:
    def test_docs_only_requires_doc_urls(self):
        ctx = _baseline_ctx()
        ctx["source_type"] = "docs-only"
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_docs_only_with_doc_urls_passes(self):
        ctx = _baseline_ctx()
        ctx["source_type"] = "docs-only"
        ctx["doc_urls"] = [{"url": "https://docs.example.com/api", "label": "API"}]
        mod.validate_context(ctx)

    def test_docs_only_warns_when_authority_not_community(self):
        ctx = _baseline_ctx()
        ctx["source_type"] = "docs-only"
        ctx["doc_urls"] = [{"url": "https://docs.example.com/api"}]
        ctx["source_authority"] = "official"
        warnings = mod.validate_context(ctx)
        assert any("forced to 'community'" in w for w in warnings)

    def test_doc_url_must_have_url_field(self):
        ctx = _baseline_ctx()
        ctx["doc_urls"] = [{"label": "missing url"}]
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)


class TestValidateContextTargetVersion:
    @pytest.mark.parametrize("tv", ["1.0.0", "v1.2.3", "1.2.3-rc.1", "1.2.3+build.5"])
    def test_valid_target_version(self, tv):
        ctx = _baseline_ctx()
        ctx["target_version"] = tv
        mod.validate_context(ctx)

    @pytest.mark.parametrize("tv", ["1", "1.2", "v2", "latest", "abc"])
    def test_invalid_target_version_rejected(self, tv):
        ctx = _baseline_ctx()
        ctx["target_version"] = tv
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)


# --------------------------------------------------------------------------
# assemble_brief() — conditional fields and key order
# --------------------------------------------------------------------------


class TestAssembleBrief:
    def test_minimal_brief_canonical_keys(self):
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        # Required keys present in canonical order
        keys = list(brief.keys())
        # Core keys appear in this order at the front
        assert keys[:10] == [
            "name", "version", "source_type", "source_repo", "language",
            "description", "forge_tier", "created", "created_by", "scope",
        ]
        # source_authority is omitted when it equals the default "community"
        assert "source_authority" not in brief

    def test_source_authority_emitted_when_non_default(self):
        ctx = _baseline_ctx()
        ctx["source_authority"] = "official"
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert brief["source_authority"] == "official"
        # Appears after all the other fields
        assert list(brief.keys())[-1] == "source_authority"

    def test_target_version_appears_when_set(self):
        ctx = _baseline_ctx()
        ctx["target_version"] = "2.5.0"
        brief = mod.assemble_brief(ctx, "2.5.0")
        assert brief["target_version"] == "2.5.0"
        assert brief["version"] == "2.5.0"

    def test_target_version_invariant_violation_halts(self):
        ctx = _baseline_ctx()
        ctx["target_version"] = "2.5.0"
        with pytest.raises(SystemExit):
            mod.assemble_brief(ctx, "9.9.9")  # version != target_version

    def test_doc_urls_emitted_with_label_default(self):
        ctx = _baseline_ctx()
        ctx["doc_urls"] = [
            {"url": "https://x.com", "label": "Home"},
            {"url": "https://x.com/api"},  # no label
        ]
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert brief["doc_urls"][0] == {"url": "https://x.com", "label": "Home"}
        assert brief["doc_urls"][1] == {"url": "https://x.com/api", "label": ""}

    def test_scripts_intent_omitted_when_default_detect(self):
        ctx = _baseline_ctx()
        ctx["scripts_intent"] = "detect"
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert "scripts_intent" not in brief

    def test_scripts_intent_emitted_when_non_default(self):
        ctx = _baseline_ctx()
        ctx["scripts_intent"] = "none"
        ctx["assets_intent"] = "JSON schemas in schemas/"
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert brief["scripts_intent"] == "none"
        assert brief["assets_intent"] == "JSON schemas in schemas/"

    def test_default_source_authority_omitted_from_brief(self):
        # Consumers default to "community" when absent; emitting the default
        # value is round-trip noise.
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        assert "source_authority" not in brief

    def test_docs_only_force_community_omits_field(self):
        # docs-only forces source_authority to "community", which is the
        # default — so the field still doesn't appear in the rendered brief.
        ctx = _baseline_ctx()
        ctx["source_type"] = "docs-only"
        ctx["doc_urls"] = [{"url": "https://docs.x.com"}]
        ctx["source_authority"] = "official"  # will be force-overridden
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert "source_authority" not in brief


# --------------------------------------------------------------------------
# render_yaml() — round-trip parse
# --------------------------------------------------------------------------


class TestRenderYaml:
    def test_round_trip_via_yaml_safe_load(self):
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        rendered = mod.render_yaml(brief)
        assert rendered.startswith("---\n")
        # No trailing --- marker — would start a second empty document and break safe_load
        assert not rendered.rstrip().endswith("---")
        parsed = yaml.safe_load(rendered)
        assert parsed["name"] == "marked"
        assert parsed["version"] == "1.0.0"
        assert parsed["scope"]["type"] == "full-library"

    def test_render_is_byte_stable_across_runs(self):
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        a = mod.render_yaml(brief)
        b = mod.render_yaml(brief)
        assert a == b


# --------------------------------------------------------------------------
# CLI: write subcommand (subprocess)
# --------------------------------------------------------------------------


class TestCLIWrite:
    def _write(self, target: Path, ctx: dict) -> tuple[int, dict, str]:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target)],
            input=json.dumps(ctx),
            capture_output=True,
            text=True,
        )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc.returncode, out, proc.stderr

    def test_write_creates_file_and_returns_path(self, tmp_target):
        code, response, _ = self._write(tmp_target, _baseline_ctx())
        assert code == 0
        assert response["status"] == "ok"
        assert response["brief_path"] == str(tmp_target.resolve())
        assert response["version"] == "1.0.0"
        assert response["bytes"] > 0
        assert tmp_target.exists()

    def test_written_yaml_round_trips(self, tmp_target):
        ctx = _baseline_ctx()
        ctx["target_version"] = "2.5.0"
        ctx["doc_urls"] = [{"url": "https://docs.example.com", "label": "Home"}]
        self._write(tmp_target, ctx)
        parsed = yaml.safe_load(tmp_target.read_text())
        assert parsed["target_version"] == "2.5.0"
        assert parsed["version"] == "2.5.0"
        assert parsed["doc_urls"][0]["url"] == "https://docs.example.com"

    def test_write_creates_parent_dirs(self, tmp_target):
        # tmp_target's parent does not exist yet — atomic_write should mkdir -p
        assert not tmp_target.parent.exists()
        code, _, _ = self._write(tmp_target, _baseline_ctx())
        assert code == 0
        assert tmp_target.exists()

    def test_write_rejects_invalid_context(self, tmp_target):
        ctx = _baseline_ctx()
        ctx["forge_tier"] = "InvalidTier"
        code, _, stderr = self._write(tmp_target, ctx)
        assert code == 1
        err = json.loads(stderr.strip())
        assert err["status"] == "error"
        assert err["field"] == "forge_tier"
        assert not tmp_target.exists()  # nothing written

    def test_write_rejects_target_version_invariant_violation(self, tmp_target):
        ctx = _baseline_ctx()
        ctx["version_resolved"] = "9.9.9"  # forces this
        ctx["target_version"] = "1.0.0"  # disagrees
        code, _, stderr = self._write(tmp_target, ctx)
        assert code == 1
        err = json.loads(stderr.strip())
        assert err["field"] == "target_version"
        assert "invariant" in err["message"]

    def test_write_rejects_empty_stdin(self, tmp_target):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(tmp_target)],
            input="", capture_output=True, text=True,
        )
        assert proc.returncode == 1
        err = json.loads(proc.stderr.strip())
        assert "empty stdin" in err["message"]

    def test_write_atomic_on_replace(self, tmp_target):
        # First write
        ctx_a = _baseline_ctx()
        ctx_a["description"] = "Description A"
        self._write(tmp_target, ctx_a)
        first_content = tmp_target.read_text()

        # Second write with different description
        ctx_b = _baseline_ctx()
        ctx_b["description"] = "Description B"
        self._write(tmp_target, ctx_b)
        second_content = tmp_target.read_text()

        # File was replaced cleanly
        assert "Description B" in second_content
        assert "Description A" not in second_content
        assert first_content != second_content
        # No leftover .skf-tmp file
        assert not tmp_target.with_name(tmp_target.name + ".skf-tmp").exists()


# --------------------------------------------------------------------------
# Flat input form (--from-flat)
# --------------------------------------------------------------------------


def _baseline_flat() -> dict:
    """Mirror of _baseline_ctx() but in the flat shape that --from-flat consumes."""
    return {
        "name": "marked",
        "source_repo": "https://github.com/markedjs/marked",
        "language": "javascript",
        "description": "Render Markdown to HTML using the marked library.",
        "forge_tier": "Quick",
        "created": "2026-05-02",
        "created_by": "armel",
        "scope_type": "full-library",
        "scope_include": ["src/**/*.ts"],
        "scope_exclude": ["**/*.test.*"],
        "scope_notes": "",
    }


class TestFlatTranslation:
    """Pure-function tests for flat_to_nested — no subprocess."""

    def test_translates_baseline_flat_to_nested(self):
        nested = mod.flat_to_nested(_baseline_flat())
        assert nested["name"] == "marked"
        assert nested["scope"] == {
            "type": "full-library",
            "include": ["src/**/*.ts"],
            "exclude": ["**/*.test.*"],
            "notes": "",
        }
        # Top-level scope_* keys do not survive into the nested form
        assert "scope_type" not in nested
        assert "scope_include" not in nested

    def test_drops_null_optionals(self):
        flat = _baseline_flat()
        flat["target_version"] = None
        flat["detected_version"] = None
        flat["doc_urls"] = None
        flat["scripts_intent"] = None
        flat["assets_intent"] = None
        flat["source_authority"] = None
        nested = mod.flat_to_nested(flat)
        for key in ("target_version", "detected_version", "doc_urls",
                    "scripts_intent", "assets_intent", "source_authority"):
            assert key not in nested, f"{key} should be dropped when null"

    def test_preserves_non_null_optionals(self):
        flat = _baseline_flat()
        flat["target_version"] = "1.2.3"
        flat["doc_urls"] = [{"url": "https://x", "label": "x"}]
        flat["source_authority"] = "official"
        flat["scripts_intent"] = "none"
        nested = mod.flat_to_nested(flat)
        assert nested["target_version"] == "1.2.3"
        assert nested["doc_urls"] == [{"url": "https://x", "label": "x"}]
        assert nested["source_authority"] == "official"
        assert nested["scripts_intent"] == "none"

    def test_passes_through_unknown_keys(self):
        flat = _baseline_flat()
        flat["future_field"] = "preserved"
        nested = mod.flat_to_nested(flat)
        assert nested["future_field"] == "preserved"

    def test_rejects_non_dict_payload(self):
        with pytest.raises(SystemExit) as exc_info:
            mod.flat_to_nested(["not", "a", "dict"])
        assert exc_info.value.code == 1


class TestCLIWriteFlat:
    """End-to-end CLI tests for --from-flat — same coverage as the nested write."""

    def _write_flat(self, target: Path, flat: dict) -> tuple[int, dict, str]:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target), "--from-flat"],
            input=json.dumps(flat),
            capture_output=True,
            text=True,
        )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc.returncode, out, proc.stderr

    def test_flat_write_produces_identical_yaml_to_nested_write(self, tmp_path):
        nested_target = tmp_path / "nested.yaml"
        flat_target = tmp_path / "flat.yaml"

        # Nested write
        proc_nested = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(nested_target)],
            input=json.dumps(_baseline_ctx()),
            capture_output=True,
            text=True,
        )
        assert proc_nested.returncode == 0, proc_nested.stderr

        # Flat write — same data via the flat shape
        proc_flat = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(flat_target), "--from-flat"],
            input=json.dumps(_baseline_flat()),
            capture_output=True,
            text=True,
        )
        assert proc_flat.returncode == 0, proc_flat.stderr

        # Byte-identical YAML output
        assert nested_target.read_text() == flat_target.read_text()

    def test_flat_write_with_all_optionals_null(self, tmp_target):
        flat = _baseline_flat()
        flat["target_version"] = None
        flat["doc_urls"] = None
        flat["scripts_intent"] = None
        flat["assets_intent"] = None
        flat["source_authority"] = None
        code, response, stderr = self._write_flat(tmp_target, flat)
        assert code == 0, stderr
        assert response["status"] == "ok"
        # YAML should not contain the null-omitted optionals
        body = tmp_target.read_text()
        assert "target_version:" not in body
        assert "doc_urls:" not in body
        assert "source_authority:" not in body
        assert "scripts_intent:" not in body

    def test_flat_write_validates_same_rules_as_nested(self, tmp_target):
        flat = _baseline_flat()
        flat["forge_tier"] = "Bogus"  # invalid enum
        code, _, stderr = self._write_flat(tmp_target, flat)
        assert code == 1
        err = json.loads(stderr.strip())
        assert err["field"] == "forge_tier"

    def test_flat_write_rejects_missing_scope_type(self, tmp_target):
        flat = _baseline_flat()
        del flat["scope_type"]
        code, _, stderr = self._write_flat(tmp_target, flat)
        assert code == 1
        err = json.loads(stderr.strip())
        assert err["field"] == "scope.type"

    def test_flat_write_rejects_target_version_invariant(self, tmp_target):
        flat = _baseline_flat()
        flat["target_version"] = "9.9.9"
        flat["detected_version"] = "1.0.0"  # version resolves to 9.9.9 → matches
        # Force a mismatch by overriding via version_resolved
        flat["version_resolved"] = "1.0.0"
        code, _, stderr = self._write_flat(tmp_target, flat)
        assert code == 1
        err = json.loads(stderr.strip())
        assert err["field"] == "target_version"
        assert "invariant" in err["message"]

    def test_flat_write_handles_docs_only_with_doc_urls(self, tmp_target):
        flat = _baseline_flat()
        flat["source_type"] = "docs-only"
        flat["doc_urls"] = [{"url": "https://docs.example.com", "label": "Main"}]
        code, response, stderr = self._write_flat(tmp_target, flat)
        assert code == 0, stderr
        body = tmp_target.read_text()
        assert "doc_urls:" in body
        assert "https://docs.example.com" in body


# --------------------------------------------------------------------------
# scope.rationale — authoring-time scope-type decision record (optional)
# --------------------------------------------------------------------------


def _rationale(**overrides) -> dict:
    """A complete, valid scope.rationale object (override individual subkeys)."""
    base = {
        "recommended": "full-library",
        "chosen": "public-api",
        "accepted_recommendation": False,
        "heuristic": "narrow-public-api",
        "reason": "user overrode full-library->public-api: only documented API ships",
        "recorded": "2026-05-18",
    }
    base.update(overrides)
    return base


class TestScopeRationaleValidation:
    """validate_context — rationale is optional, but complete when present."""

    def test_absent_rationale_validates(self):
        # Legacy briefs have no scope.rationale and must still pass.
        ctx = _baseline_ctx()
        assert "rationale" not in ctx["scope"]
        mod.validate_context(ctx)  # no raise

    def test_present_valid_rationale_validates(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale()
        mod.validate_context(ctx)  # no raise

    def test_rationale_must_be_object(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = "not-an-object"
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    @pytest.mark.parametrize(
        "missing",
        ["recommended", "chosen", "accepted_recommendation", "heuristic", "reason", "recorded"],
    )
    def test_rationale_missing_subkey_fails(self, missing):
        ctx = _baseline_ctx()
        r = _rationale()
        del r[missing]
        ctx["scope"]["rationale"] = r
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_rationale_accepted_recommendation_must_be_bool(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale(accepted_recommendation="false")
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_rationale_recommended_must_be_valid_scope_type(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale(recommended="bogus-type")
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_rationale_empty_reason_fails(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale(reason="")
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)


class TestScopeRationaleAssembly:
    """assemble_brief — rationale sits after notes; omitted when absent."""

    def test_rationale_absent_when_not_supplied(self):
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        assert "rationale" not in brief["scope"]

    def test_rationale_emitted_after_notes(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale()
        brief = mod.assemble_brief(ctx, "1.0.0")
        scope_keys = list(brief["scope"].keys())
        assert scope_keys == ["type", "include", "exclude", "notes", "rationale"]
        assert brief["scope"]["rationale"]["chosen"] == "public-api"
        # Subkeys emitted in canonical order
        assert list(brief["scope"]["rationale"].keys()) == [
            "recommended", "chosen", "accepted_recommendation",
            "heuristic", "reason", "recorded",
        ]

    def test_rationale_round_trips_through_yaml(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale()
        rendered = mod.render_yaml(mod.assemble_brief(ctx, "1.0.0"))
        parsed = yaml.safe_load(rendered)
        assert parsed["scope"]["rationale"] == _rationale()


class TestScopeRationaleFlatTranslation:
    """flat_to_nested — scope_rationale maps in; null drops out."""

    def test_flat_scope_rationale_mapped_into_scope(self):
        flat = _baseline_flat()
        flat["scope_rationale"] = _rationale()
        nested = mod.flat_to_nested(flat)
        assert nested["scope"]["rationale"] == _rationale()
        # Does not leak as a top-level key
        assert "scope_rationale" not in nested

    def test_flat_scope_rationale_null_drops_key(self):
        flat = _baseline_flat()
        flat["scope_rationale"] = None
        nested = mod.flat_to_nested(flat)
        assert "rationale" not in nested["scope"]
        assert "scope_rationale" not in nested

    def test_flat_scope_rationale_absent_drops_key(self):
        nested = mod.flat_to_nested(_baseline_flat())
        assert "rationale" not in nested["scope"]


class TestCLIWriteFlatScopeRationale:
    """End-to-end flat CLI write with scope_rationale."""

    def _write_flat(self, target: Path, flat: dict):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target), "--from-flat"],
            input=json.dumps(flat),
            capture_output=True,
            text=True,
        )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc.returncode, out, proc.stderr

    def test_flat_write_with_rationale_object(self, tmp_target):
        flat = _baseline_flat()
        flat["scope_rationale"] = _rationale()
        code, response, stderr = self._write_flat(tmp_target, flat)
        assert code == 0, stderr
        parsed = yaml.safe_load(tmp_target.read_text())
        assert parsed["scope"]["rationale"] == _rationale()

    def test_flat_write_with_null_rationale_omits_key(self, tmp_target):
        flat = _baseline_flat()
        flat["scope_rationale"] = None
        code, response, stderr = self._write_flat(tmp_target, flat)
        assert code == 0, stderr
        body = tmp_target.read_text()
        assert "rationale:" not in body
        parsed = yaml.safe_load(body)
        assert "rationale" not in parsed["scope"]
