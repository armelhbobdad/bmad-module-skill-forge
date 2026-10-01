#!/usr/bin/env python3
"""Tests for skf-write-skill-brief.py.

Pure functions (resolve_version, validate_context, assemble_brief,
render_yaml) are exercised inline. The atomic write is exercised
via subprocess against a tempfile target.
"""

from __future__ import annotations

import importlib.util
import json
import os
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

    def test_doc_urls_source_preserved_when_present(self):
        # issue #432 — per-corpus provenance. When a doc_urls entry carries a
        # `source`, the writer must thread it through so downstream (#431/#430)
        # can distinguish registry-guaranteed corpora from detected docs.
        ctx = _baseline_ctx()
        ctx["doc_urls"] = [
            {"url": "https://doc.rust-lang.org/book/", "label": "Book",
             "source": "language-registry"},
            {"url": "https://docs.rs/x", "label": "Detected",
             "source": "readme-detection"},
        ]
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert brief["doc_urls"][0] == {
            "url": "https://doc.rust-lang.org/book/", "label": "Book",
            "source": "language-registry",
        }
        assert brief["doc_urls"][1]["source"] == "readme-detection"

    def test_doc_urls_no_source_key_injected_when_absent(self):
        # No false drift: an entry without `source` must emit exactly {url,label}
        # (presence-gated emission, mirroring the source_authority null-drop
        # discipline). A legacy brief re-write stays byte-identical.
        ctx = _baseline_ctx()
        ctx["doc_urls"] = [{"url": "https://x.com", "label": "Home"}]
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert set(brief["doc_urls"][0].keys()) == {"url", "label"}

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


# --------------------------------------------------------------------------
# Round-trip fields (issue #385): target_ref / source_ref /
# scope.tier_a_include / scope.amendments must survive a ratify/re-write.
# --------------------------------------------------------------------------


def _amendment() -> dict:
    """A representative auth-doc amendment entry."""
    return {
        "path": "apps/docs/public/llms.txt",
        "action": "promoted",
        "category": "auth-doc",
        "reason": "authoritative AI docs — only source for canonical install command",
        "heuristic": "llms.txt",
        "date": "2026-04-11",
        "workflow": "skf-create-skill",
    }


class TestRoundTripFieldsValidation:
    """validate_context — the four fields are optional but light-checked."""

    def test_tier_a_include_must_be_list(self):
        ctx = _baseline_ctx()
        ctx["scope"]["tier_a_include"] = "code/core/src/**"  # string, not list
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_tier_a_include_entries_must_be_nonempty_strings(self):
        ctx = _baseline_ctx()
        ctx["scope"]["tier_a_include"] = ["ok", ""]
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_valid_tier_a_include_passes(self):
        ctx = _baseline_ctx()
        ctx["scope"]["tier_a_include"] = ["code/core/src/**"]
        assert mod.validate_context(ctx) == []

    def test_amendments_must_be_list(self):
        ctx = _baseline_ctx()
        ctx["scope"]["amendments"] = {"not": "a list"}
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_amendments_entries_must_be_objects(self):
        ctx = _baseline_ctx()
        ctx["scope"]["amendments"] = ["not-an-object"]
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    def test_valid_amendments_pass(self):
        ctx = _baseline_ctx()
        ctx["scope"]["amendments"] = [_amendment()]
        assert mod.validate_context(ctx) == []

    @pytest.mark.parametrize("field", ["target_ref", "source_ref"])
    def test_ref_empty_string_rejected(self, field):
        ctx = _baseline_ctx()
        ctx[field] = ""
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)

    @pytest.mark.parametrize("field", ["target_ref", "source_ref"])
    def test_ref_non_string_rejected(self, field):
        ctx = _baseline_ctx()
        ctx[field] = 123
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)


class TestRoundTripFieldsAssembly:
    """assemble_brief — canonical positions; omitted when absent (no churn)."""

    def test_absent_by_default_no_key_churn(self):
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        assert "tier_a_include" not in brief["scope"]
        assert "amendments" not in brief["scope"]
        assert "target_ref" not in brief
        assert "source_ref" not in brief
        # Existing scope key order is unchanged when the new fields are absent
        assert list(brief["scope"].keys()) == ["type", "include", "exclude", "notes"]

    def test_tier_a_include_sits_between_exclude_and_notes(self):
        ctx = _baseline_ctx()
        ctx["scope"]["tier_a_include"] = ["code/core/src/**"]
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert list(brief["scope"].keys()) == [
            "type", "include", "exclude", "tier_a_include", "notes",
        ]
        assert brief["scope"]["tier_a_include"] == ["code/core/src/**"]

    def test_amendments_after_rationale(self):
        ctx = _baseline_ctx()
        ctx["scope"]["rationale"] = _rationale()
        ctx["scope"]["amendments"] = [_amendment()]
        brief = mod.assemble_brief(ctx, "1.0.0")
        assert list(brief["scope"].keys()) == [
            "type", "include", "exclude", "notes", "rationale", "amendments",
        ]
        assert brief["scope"]["amendments"] == [_amendment()]

    def test_refs_emitted_after_target_version(self):
        ctx = _baseline_ctx()
        ctx["target_version"] = "1.0.0"
        ctx["target_ref"] = "livekit/v0.7.42"
        ctx["source_ref"] = "v0.5.0"
        brief = mod.assemble_brief(ctx, "1.0.0")
        keys = list(brief.keys())
        assert keys.index("target_ref") > keys.index("target_version")
        assert keys.index("source_ref") > keys.index("target_ref")
        assert brief["target_ref"] == "livekit/v0.7.42"
        assert brief["source_ref"] == "v0.5.0"

    def test_all_four_round_trip_through_yaml(self):
        ctx = _baseline_ctx()
        ctx["target_ref"] = "livekit/v0.7.42"
        ctx["source_ref"] = "v0.5.0"
        ctx["scope"]["tier_a_include"] = ["code/core/src/**"]
        ctx["scope"]["amendments"] = [_amendment()]
        parsed = yaml.safe_load(mod.render_yaml(mod.assemble_brief(ctx, "1.0.0")))
        assert parsed["target_ref"] == "livekit/v0.7.42"
        assert parsed["source_ref"] == "v0.5.0"
        assert parsed["scope"]["tier_a_include"] == ["code/core/src/**"]
        assert parsed["scope"]["amendments"] == [_amendment()]


class TestRoundTripFieldsFlatTranslation:
    """flat_to_nested — scope_* map into scope; refs pass through; null drops."""

    def test_flat_scope_fields_mapped(self):
        flat = _baseline_flat()
        flat["scope_tier_a_include"] = ["code/core/src/**"]
        flat["scope_amendments"] = [_amendment()]
        nested = mod.flat_to_nested(flat)
        assert nested["scope"]["tier_a_include"] == ["code/core/src/**"]
        assert nested["scope"]["amendments"] == [_amendment()]
        assert "scope_tier_a_include" not in nested
        assert "scope_amendments" not in nested

    def test_flat_scope_fields_null_dropped(self):
        flat = _baseline_flat()
        flat["scope_tier_a_include"] = None
        flat["scope_amendments"] = None
        nested = mod.flat_to_nested(flat)
        assert "tier_a_include" not in nested["scope"]
        assert "amendments" not in nested["scope"]

    def test_flat_refs_pass_through(self):
        flat = _baseline_flat()
        flat["target_ref"] = "livekit/v0.7.42"
        flat["source_ref"] = "v0.5.0"
        nested = mod.flat_to_nested(flat)
        assert nested["target_ref"] == "livekit/v0.7.42"
        assert nested["source_ref"] == "v0.5.0"

    def test_flat_refs_null_dropped(self):
        flat = _baseline_flat()
        flat["target_ref"] = None
        flat["source_ref"] = None
        nested = mod.flat_to_nested(flat)
        assert "target_ref" not in nested
        assert "source_ref" not in nested


class TestCLIWriteFlatRoundTripFields:
    """End-to-end flat CLI write preserving all four fields (the ratify path)."""

    def _write_flat(self, target: Path, flat: dict):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target), "--from-flat"],
            input=json.dumps(flat),
            capture_output=True,
            text=True,
        )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        return proc.returncode, out, proc.stderr

    def test_flat_write_preserves_all_round_trip_fields(self, tmp_target):
        flat = _baseline_flat()
        flat["target_ref"] = "livekit/v0.7.42"
        flat["source_ref"] = "v0.5.0"
        flat["scope_tier_a_include"] = ["code/core/src/**"]
        flat["scope_amendments"] = [_amendment()]
        code, response, stderr = self._write_flat(tmp_target, flat)
        assert code == 0, stderr
        # Read as UTF-8 explicitly: the writer emits UTF-8 (allow_unicode=True),
        # and the amendment `reason` carries an em-dash. read_text() without an
        # encoding uses the platform default (cp1252 on Windows), which would
        # mojibake the em-dash and fail the comparison — the windows-latest gate.
        parsed = yaml.safe_load(tmp_target.read_text(encoding="utf-8"))
        assert parsed["target_ref"] == "livekit/v0.7.42"
        assert parsed["source_ref"] == "v0.5.0"
        assert parsed["scope"]["tier_a_include"] == ["code/core/src/**"]
        assert parsed["scope"]["amendments"] == [_amendment()]


class TestAtomicWriteBinary:
    """atomic_write persists content verbatim — no CRLF injection on Windows."""

    def test_byte_identity_multiline(self):
        content = "---\nname: x\n---\n\nline1\nline2\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "brief.md"
            mod.atomic_write(target, content)
            assert target.read_bytes() == content.encode("utf-8")
            assert b"\r\n" not in target.read_bytes()


# --------------------------------------------------------------------------
# Component-library fields (#605): create-skill step 3d writes the confirmed
# registry path and demo globs back to the brief, and a brief-skill ratify
# re-write must keep them, with ui_variants, verbatim.
# --------------------------------------------------------------------------

VALIDATE_SCHEMA_PATH = SCRIPT_PATH.parent / "skf-validate-brief-schema.py"


def _component_scope() -> dict:
    return {
        "registry_path": "registry/index.ts",
        "ui_variants": [{"name": "shadcnui", "package": "packages/ui"}, {"name": "baseui"}],
        "demo_patterns": ["**/examples/**", "**/*.stories.*"],
    }


def _write_back_amendment() -> dict:
    return {
        "path": "registry/index.ts",
        "action": "registry-confirmed",
        "category": "demo-and-registry",
        "reason": "user confirmed the detected registry at create-skill step 3d",
        "evidence": "score 8/9, 52 entries",
        "date": "2026-10-01",
        "workflow": "skf-create-skill",
    }


def _component_ctx() -> dict:
    ctx = _baseline_ctx()
    ctx["scope"]["type"] = "component-library"
    ctx["scope"]["amendments"] = [_write_back_amendment()]
    ctx["scope"].update(_component_scope())
    return ctx


class TestComponentLibraryFieldsValidation:
    def test_valid_fields_pass(self):
        assert mod.validate_context(_component_ctx()) == []

    def test_a_variant_needs_no_name(self):
        """The checks mirror skill-brief.v1.json, which only adds the fields."""
        ctx = _component_ctx()
        ctx["scope"]["ui_variants"] = [{"package": "packages/ui"}]
        assert mod.validate_context(ctx) == []

    @pytest.mark.parametrize("field, value", [
        ("registry_path", ""),
        ("registry_path", ["registry/index.ts"]),
        ("demo_patterns", "**/examples/**"),
        ("demo_patterns", ["**/examples/**", ""]),
        ("demo_patterns", [3]),
        ("ui_variants", {"name": "shadcnui"}),
        ("ui_variants", [{"name": ""}]),
        ("ui_variants", [{"name": "shadcnui", "package": ""}]),
        ("ui_variants", ["shadcnui"]),
    ], ids=["path-empty", "path-list", "demo-string", "demo-blank", "demo-number", "variants-object",
            "variant-blank-name", "variant-blank-package", "variant-string"])
    def test_malformed_values_fail(self, field, value, capsys):
        ctx = _component_ctx()
        ctx["scope"][field] = value
        with pytest.raises(SystemExit):
            mod.validate_context(ctx)
        assert json.loads(capsys.readouterr().err)["field"] == f"scope.{field}"


class TestComponentLibraryFieldsAssembly:
    def test_absent_by_default(self):
        brief = mod.assemble_brief(_baseline_ctx(), "1.0.0")
        assert not {"registry_path", "ui_variants", "demo_patterns"} & set(brief["scope"])

    def test_kept_verbatim_after_amendments(self):
        brief = mod.assemble_brief(_component_ctx(), "1.0.0")
        assert list(brief["scope"]) == [
            "type", "include", "exclude", "notes", "amendments", "registry_path", "ui_variants", "demo_patterns",
        ]
        for field, value in _component_scope().items():
            assert brief["scope"][field] == value

    def test_a_ratify_re_write_is_byte_identical(self, tmp_path):
        """Write, read the brief back as gather-intent's ratify hydrates it, write again."""
        first = tmp_path / "first" / "skill-brief.yaml"
        second = tmp_path / "second" / "skill-brief.yaml"
        for target, ctx in ((first, _component_ctx()), (second, None)):
            if ctx is None:
                parsed = yaml.safe_load(first.read_text(encoding="utf-8"))
                ctx = {k: v for k, v in parsed.items() if k != "version"}
                ctx["version_resolved"] = parsed["version"]
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target)],
                input=json.dumps(ctx), capture_output=True, text=True,
            )
            assert proc.returncode == 0, proc.stderr + proc.stdout
        assert first.read_bytes() == second.read_bytes()
        assert yaml.safe_load(second.read_text(encoding="utf-8"))["scope"]["registry_path"] == "registry/index.ts"

    def test_written_brief_validates_against_the_schema(self, tmp_path):
        target = tmp_path / "skill-brief.yaml"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target)],
            input=json.dumps(_component_ctx()), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        checked = subprocess.run(
            [sys.executable, str(VALIDATE_SCHEMA_PATH), str(target)], capture_output=True, text=True,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert json.loads(checked.stdout)["valid"] is True


class TestComponentLibraryFieldsFlat:
    """The flat payload a ratify in brief-skill sends (`--from-flat`)."""

    def test_flat_fields_map_into_scope(self):
        flat = _baseline_flat()
        flat.update({f"scope_{field}": value for field, value in _component_scope().items()})
        nested = mod.flat_to_nested(flat)
        for field, value in _component_scope().items():
            assert nested["scope"][field] == value
            assert f"scope_{field}" not in nested

    def test_flat_nulls_drop(self):
        flat = _baseline_flat()
        flat.update({f"scope_{field}": None for field in _component_scope()})
        nested = mod.flat_to_nested(flat)
        assert not {"registry_path", "ui_variants", "demo_patterns"} & set(nested["scope"])

    def test_flat_write_keeps_the_fields(self, tmp_target):
        flat = _baseline_flat()
        flat["scope_type"] = "component-library"
        flat["scope_amendments"] = [_write_back_amendment()]
        flat.update({f"scope_{field}": value for field, value in _component_scope().items()})
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write", "--target", str(tmp_target), "--from-flat"],
            input=json.dumps(flat), capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        scope = yaml.safe_load(tmp_target.read_text(encoding="utf-8"))["scope"]
        assert scope["amendments"] == [_write_back_amendment()]
        for field, value in _component_scope().items():
            assert scope[field] == value


# --------------------------------------------------------------------------
# amend (#605): create-skill step 3d records its answers in the brief
# without re-typing it.
# --------------------------------------------------------------------------


def _demo_amendment() -> dict:
    return {**_write_back_amendment(), "path": "**/examples/**", "action": "demo-excluded",
            "reason": "user confirmed the demo exclusion at create-skill step 3d", "evidence": "4 files"}


def _answers() -> dict:
    return {"registry_path": "registry/index.ts", "demo_patterns": ["**/examples/**"],
            "amendments": [_demo_amendment(), _write_back_amendment()]}


def _amend(target: Path, payload) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "amend", "--target", str(target)],
        input=payload if isinstance(payload, str) else json.dumps(payload), capture_output=True, text=True,
    )


def _written_brief(target: Path) -> bytes:
    ctx = _baseline_ctx()
    ctx["scope"]["type"] = "component-library"
    ctx["scope"]["amendments"] = [{"path": "llms.txt", "action": "skipped", "category": "auth-doc",
                                   "reason": "r", "heuristic": "llms.txt", "date": "2026-09-30",
                                   "workflow": "skf-create-skill"}]
    ctx["scope"]["ui_variants"] = [{"name": "shadcnui"}]
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target)],
        input=json.dumps(ctx), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return target.read_bytes()


class TestAmend:
    def test_sets_the_fields_and_appends_the_entries(self, tmp_target):
        before = _written_brief(tmp_target)
        proc = _amend(tmp_target, _answers())
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert (result["status"], result["set"], result["appended"]) == ("ok", ["registry_path", "demo_patterns"], 2)
        backup = tmp_target.with_name("skill-brief.yaml.bak")
        assert result["backup"] == str(backup.resolve()) and backup.read_bytes() == before
        old, new = yaml.safe_load(before), yaml.safe_load(tmp_target.read_text(encoding="utf-8"))
        assert new["scope"]["amendments"] == [*old["scope"]["amendments"], _demo_amendment(), _write_back_amendment()]
        assert (new["scope"]["registry_path"], new["scope"]["demo_patterns"]) == ("registry/index.ts", ["**/examples/**"])
        # Every other field keeps its value and its place.
        for key in ("registry_path", "demo_patterns", "amendments"):
            new["scope"].pop(key)
            old["scope"].pop(key, None)
        assert list(new) == list(old) and new == old

    def test_the_amended_brief_validates_against_the_schema(self, tmp_target):
        _written_brief(tmp_target)
        assert _amend(tmp_target, _answers()).returncode == 0
        checked = subprocess.run([sys.executable, str(VALIDATE_SCHEMA_PATH), str(tmp_target)],
                                 capture_output=True, text=True)
        assert checked.returncode == 0, checked.stdout + checked.stderr

    def test_a_hand_written_brief_keeps_its_order(self, tmp_target):
        tmp_target.parent.mkdir(parents=True)
        tmp_target.write_bytes(
            b"# hand written\nname: acme-ui\nversion: '2.1'\nscope:\n  notes: ''\n  type: component-library\n"
            b"  include:\n  - src/**\n  exclude: []\n  registry_path: gone/index.ts\nlanguage: typescript\n"
        )
        payload = {"registry_path": "registry/index.ts",
                   "amendments": [{**_write_back_amendment(),
                                   "reason": "user replaced the unreadable registry path at create-skill step 3d"}]}
        assert _amend(tmp_target, payload).returncode == 0
        new = yaml.safe_load(tmp_target.read_text(encoding="utf-8"))
        assert list(new) == ["name", "version", "scope", "language"] and new["version"] == "2.1"
        assert list(new["scope"]) == ["notes", "type", "include", "exclude", "registry_path", "amendments"]
        assert new["scope"]["registry_path"] == "registry/index.ts"
        assert tmp_target.with_name("skill-brief.yaml.bak").read_bytes().startswith(b"# hand written\n")

    @pytest.mark.parametrize("payload, message", [
        ({}, "nothing to amend"),
        ({"registry_path": "r.ts", "ui_variants": []}, "unknown field"),
        ({"registry_path": ""}, "scope.registry_path must be a non-empty string"),
        ({"demo_patterns": "**/examples/**"}, "scope.demo_patterns must be an array"),
        ({"amendments": [{**_write_back_amendment(), "reason": ""}]}, "amendments[0].reason"),
        ({"amendments": [{**_write_back_amendment(), "date": "1 Oct 2026"}]}, "amendments[0].date"),
        ("[not json", "invalid JSON"),
    ], ids=["empty", "unknown-field", "blank-path", "demo-string", "blank-reason", "bad-date", "bad-json"])
    def test_a_bad_payload_exits_1_and_touches_nothing(self, tmp_target, payload, message):
        before = _written_brief(tmp_target)
        proc = _amend(tmp_target, payload)
        assert proc.returncode == 1 and message in proc.stderr, proc.stderr
        assert tmp_target.read_bytes() == before
        assert not tmp_target.with_name("skill-brief.yaml.bak").exists()

    def test_a_utf8_payload_survives_a_cp1252_console(self, tmp_target):
        """A Windows console pipes stdin as cp1252: the writer reads it as UTF-8."""
        _written_brief(tmp_target)
        reason = "user confirmed the détected registry, café über alles"
        payload = {"registry_path": "registry/index.ts", "amendments": [{**_write_back_amendment(), "reason": reason}]}
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "amend", "--target", str(tmp_target)],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"), capture_output=True,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )
        assert proc.returncode == 0, proc.stderr
        scope = yaml.safe_load(tmp_target.read_text(encoding="utf-8"))["scope"]
        assert scope["amendments"][-1]["reason"] == reason

    def test_a_missing_brief_exits_2(self, tmp_target):
        proc = _amend(tmp_target, _answers())
        assert proc.returncode == 2 and "cannot read" in proc.stderr

    def test_a_brief_without_scope_exits_1(self, tmp_target):
        tmp_target.parent.mkdir(parents=True)
        tmp_target.write_bytes(b"name: acme-ui\n")
        proc = _amend(tmp_target, _answers())
        assert proc.returncode == 1 and "holds no scope mapping" in proc.stderr


# --------------------------------------------------------------------------
# write --base-brief: rewrite a brief on disk without retyping it
# --------------------------------------------------------------------------


def _full_brief_ctx() -> dict:
    """A context carrying every field the writer renders, version pinned by target_version."""
    ctx = _component_ctx()
    ctx["scope"]["tier_a_include"] = ["registry/button.tsx"]
    ctx["scope"]["notes"] = "It's the registry's surface."
    ctx["scope"]["rationale"] = {"recommended": "full-library", "chosen": "component-library",
                                 "accepted_recommendation": False, "heuristic": "component-registry",
                                 "reason": "a registry", "recorded": "2026-09-30"}
    ctx.update(target_version="1.2.3", target_ref="v1.2.3", source_ref="v1.2.3", scripts_intent="none",
               assets_intent="the JSON schemas", source_authority="official",
               doc_urls=[{"url": "https://marked.js.org/", "label": "Docs", "source": "homepage"}])
    return ctx


def _base_write(target: Path, base: Path, *flags: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write", "--target", str(target), "--base-brief", str(base), *flags],
        input=stdin, capture_output=True, text=True, encoding="utf-8",
    )


def _loaded(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestBaseBrief:
    def _base(self, tmp_path: Path) -> Path:
        base = tmp_path / "upstream" / "skill-brief.yaml"
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "write", "--target", str(base)],
                              input=json.dumps(_full_brief_ctx()), capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return base

    def test_a_brief_rewritten_from_itself_is_byte_identical(self, tmp_path):
        base = self._base(tmp_path)
        target = tmp_path / "out" / "skill-brief.yaml"
        proc = _base_write(target, base, stdin="not read")
        assert proc.returncode == 0, proc.stderr
        assert target.read_bytes() == base.read_bytes()
        assert json.loads(proc.stdout)["version"] == "1.2.3"

    def test_the_merged_doc_urls_replace_the_briefs(self, tmp_path):
        base = self._base(tmp_path)
        merged = tmp_path / "doc-urls-merged.json"
        doc_urls = [{"url": "https://marked.js.org/", "label": "Docs", "source": "homepage"},
                    {"url": "https://marked.js.org/api", "label": "API's reference", "source": "readme-detection"}]
        merged.write_bytes(json.dumps({"doc_urls": doc_urls, "suppressed": [{"url": "x", "reason": "y"}]})
                           .encode("utf-8"))
        target = tmp_path / "out" / "skill-brief.yaml"
        proc = _base_write(target, base, "--doc-urls-file", str(merged))
        assert proc.returncode == 0, proc.stderr
        written, before = _loaded(target), _loaded(base)
        assert written["doc_urls"] == doc_urls and "suppressed" not in written
        assert {k: v for k, v in written.items() if k != "doc_urls"} == \
            {k: v for k, v in before.items() if k != "doc_urls"}

    def test_a_patch_changes_only_what_it_names(self, tmp_path):
        base = self._base(tmp_path)
        patch = tmp_path / "edit.json"
        patch.write_bytes(json.dumps({"description": "It's the parser. Use when Markdown needs HTML.",
                                      "scope": {"type": "public-api", "tier_a_include": None},
                                      "version": "1.3.0", "target_version": "1.3.0",
                                      "source_ref": None}).encode("utf-8"))
        proc = _base_write(base, base, "--patch-file", str(patch))
        assert proc.returncode == 0, proc.stderr
        written = _loaded(base)
        assert written["description"] == "It's the parser. Use when Markdown needs HTML."
        assert written["scope"]["type"] == "public-api" and "tier_a_include" not in written["scope"]
        assert written["scope"]["registry_path"] == "registry/index.ts"
        assert written["scope"]["amendments"] == [_write_back_amendment()]
        assert (written["version"], written["target_version"]) == ("1.3.0", "1.3.0")
        assert "source_ref" not in written and written["target_ref"] == "v1.2.3"

    def test_a_version_change_without_target_version_breaks_the_invariant(self, tmp_path):
        base = self._base(tmp_path)
        before = base.read_bytes()
        patch = tmp_path / "edit.json"
        patch.write_bytes(b'{"version": "2.0.0"}')
        proc = _base_write(base, base, "--patch-file", str(patch))
        assert proc.returncode == 1 and json.loads(proc.stderr)["field"] == "target_version"
        assert base.read_bytes() == before

    def test_an_unquoted_date_is_read_as_its_iso_text(self, tmp_path):
        base = tmp_path / "skill-brief.yaml"
        base.write_bytes(b"name: marked\nversion: 2.0.0\nsource_repo: https://github.com/markedjs/marked\n"
                         b"language: javascript\ndescription: Markdown to HTML. Use when rendering Markdown.\n"
                         b"forge_tier: Quick\ncreated: 2026-05-02\ncreated_by: armel\n"
                         b"scope:\n  type: full-library\n  include: [src/**]\n  exclude: []\n  notes: ''\n")
        target = tmp_path / "out.yaml"
        proc = _base_write(target, base)
        assert proc.returncode == 0, proc.stderr
        written = _loaded(target)
        assert (written["created"], written["version"]) == ("2026-05-02", "2.0.0")

    @pytest.mark.parametrize("flags, code, message", [
        pytest.param(["--from-flat"], 1, "exclude each other", id="from-flat"),
        pytest.param(["--doc-urls-file", "{missing}"], 2, "cannot read", id="missing-doc-urls-file"),
        pytest.param(["--patch-file", "{list}"], 1, "must hold a JSON object", id="patch-not-an-object"),
        pytest.param(["--doc-urls-file", "{empty}"], 1, "holds no doc_urls", id="no-doc-urls"),
    ])
    def test_bad_inputs_exit_non_zero_and_write_nothing(self, tmp_path, flags, code, message):
        base = self._base(tmp_path)
        (tmp_path / "list.json").write_bytes(b"[1, 2]")
        (tmp_path / "empty.json").write_bytes(b"{}")
        flags = [f.format(missing=tmp_path / "missing.json", list=tmp_path / "list.json",
                          empty=tmp_path / "empty.json") for f in flags]
        target = tmp_path / "out" / "skill-brief.yaml"
        proc = _base_write(target, base, *flags)
        assert proc.returncode == code and message in proc.stderr
        assert not target.exists()

    def test_a_missing_base_brief_exits_2(self, tmp_path):
        proc = _base_write(tmp_path / "out.yaml", tmp_path / "missing.yaml")
        assert proc.returncode == 2 and "cannot read the base brief" in proc.stderr

    def test_the_change_flags_need_a_base_brief(self, tmp_path):
        proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "write", "--target", str(tmp_path / "x.yaml"),
                               "--patch-file", str(tmp_path / "p.json")],
                              input=json.dumps(_baseline_ctx()), capture_output=True, text=True)
        assert proc.returncode == 1 and "change a --base-brief" in proc.stderr
