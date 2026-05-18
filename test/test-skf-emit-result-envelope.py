#!/usr/bin/env python3
"""Tests for skf-emit-result-envelope.py.

The envelope is a public contract that pipelines depend on. Two test
priorities:

1. Output validates against the JSON Schema at
   src/shared/scripts/schemas/skf-setup-result-envelope.v1.json — for
   every input shape the script accepts.
2. Derived fields (tools_added/removed, tier_changed, warnings) match
   the documented step 4 §4 rules exactly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
SCHEMA_PATH = ROOT / "src" / "shared" / "scripts" / "schemas" / "skf-setup-result-envelope.v1.json"

spec = importlib.util.spec_from_file_location("skf_emit_result_envelope", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _baseline_payload() -> dict:
    """Minimal valid payload covering every required envelope field."""
    return {
        "tier": "Deep",
        "previous_tier": None,
        "tools": {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": True},
        "previous_tools": None,
        "config_path": "/abs/path/_bmad/_memory/forger-sidecar/forge-tier.yaml",
        "ccc_index": {"status": "fresh", "indexed_path": "/abs/path", "file_count": 1234},
        "files_written": ["forge-tier.yaml"],
        "tier_override_active": False,
        "tier_override_invalid": False,
        "require_tier_satisfied": None,
        "error": None,
    }


# ─── Schema sanity ───────────────────────────────────────────────────────────


def test_schema_file_exists_and_parses():
    assert SCHEMA_PATH.exists(), f"schema missing: {SCHEMA_PATH}"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["title"].startswith("SKF_SETUP_RESULT_JSON envelope")


# ─── assemble_envelope: derivation rules ────────────────────────────────────


def test_baseline_envelope_assembles_and_validates():
    env = mod.assemble_envelope(_baseline_payload())
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = mod._validate_against_schema(env, schema)
    assert errors == [], f"baseline envelope failed schema: {errors}"


# ─── status derivation ─────────────────────────────────────────────────────


def test_status_success_on_clean_run():
    env = mod.assemble_envelope(_baseline_payload())
    assert env["skf_setup"]["status"] == "success"


def test_status_tier_failure_when_require_tier_not_satisfied():
    p = _baseline_payload()
    p["require_tier_satisfied"] = False
    p["require_tier_failure_missing"] = ["qmd"]
    assert mod.assemble_envelope(p)["skf_setup"]["status"] == "tier_failure"


def test_status_write_failure_when_error_phase_signals_write():
    p = _baseline_payload()
    p["error"] = {"phase": "step 2:write-tools", "path": "/x/forge-tier.yaml", "reason": "permission denied"}
    assert mod.assemble_envelope(p)["skf_setup"]["status"] == "write_failure"


def test_status_blocked_for_non_write_error():
    p = _baseline_payload()
    p["error"] = {"phase": "step 1:foreign-ccc", "path": "/usr/local/bin/ccc", "reason": "identity check failed"}
    assert mod.assemble_envelope(p)["skf_setup"]["status"] == "blocked"


# ─── assemble_blocked_envelope: early-halt envelopes ────────────────────────


def test_blocked_envelope_validates_against_schema():
    env = mod.assemble_blocked_envelope("on-activation:uv-missing", "uv is not installed")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = mod._validate_against_schema(env, schema)
    assert errors == [], f"blocked envelope failed schema: {errors}"


def test_blocked_envelope_carries_status_and_error():
    env = mod.assemble_blocked_envelope(
        "on-activation:config-missing",
        "config.yaml not found",
        path="/abs/_bmad/skf/config.yaml",
    )
    e = env["skf_setup"]
    assert e["status"] == "blocked"
    assert e["error"]["phase"] == "on-activation:config-missing"
    assert e["error"]["path"] == "/abs/_bmad/skf/config.yaml"
    assert e["error"]["reason"] == "config.yaml not found"


def test_blocked_envelope_path_optional():
    env = mod.assemble_blocked_envelope("phase", "reason")
    e = env["skf_setup"]
    assert e["error"]["path"] == "<n/a>"
    assert e["config_path"].startswith("<unknown")


def test_tier_changed_false_on_first_run():
    env = mod.assemble_envelope(_baseline_payload())
    assert env["skf_setup"]["tier_changed"] is False
    assert env["skf_setup"]["previous_tier"] is None


def test_tier_changed_true_on_upgrade():
    p = _baseline_payload()
    p["previous_tier"] = "Forge"  # was Forge, now Deep
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["tier_changed"] is True


def test_tier_changed_false_on_same_tier_rerun():
    p = _baseline_payload()
    p["previous_tier"] = "Deep"  # unchanged
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["tier_changed"] is False


def test_first_run_tools_added_lists_all_available_tools():
    """Per step 4 §4 rule: on first runs, tools_added equals currently-detected tools."""
    p = _baseline_payload()
    p["previous_tools"] = None
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["tools_added"] == sorted(["ast_grep", "gh_cli", "qmd", "ccc"])
    assert env["skf_setup"]["tools_removed"] == []


def test_tools_added_surfaces_newly_installed():
    """User installed ccc on a Deep host — same tier, but tools_added shows ccc."""
    p = _baseline_payload()
    p["previous_tools"] = {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": False}
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["tools_added"] == ["ccc"]
    assert env["skf_setup"]["tools_removed"] == []


def test_tools_removed_surfaces_uninstalled():
    p = _baseline_payload()
    p["tools"] = {"ast_grep": True, "gh_cli": True, "qmd": False, "ccc": False}
    p["previous_tools"] = {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": True}
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["tools_added"] == []
    assert env["skf_setup"]["tools_removed"] == ["ccc", "qmd"]  # sorted


def test_normalize_tools_accepts_detect_tools_output_shape():
    """skf-detect-tools.py emits {key: {available: bool, version: ...}} — must work too."""
    p = _baseline_payload()
    p["tools"] = {
        "ast_grep": {"available": True, "version": "0.39.5"},
        "gh_cli":   {"available": False, "version": None},
        "qmd":      {"available": True, "status": "healthy"},
        "ccc":      {"available": True, "daemon": "healthy"},
    }
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["tools"] == {
        "ast_grep": True, "gh_cli": False, "qmd": True, "ccc": True,
    }


# ─── Warnings assembly (per step 4 §4 documented rules) ────────────────────


def test_warnings_empty_on_clean_run():
    env = mod.assemble_envelope(_baseline_payload())
    assert env["skf_setup"]["warnings"] == []


def test_warnings_includes_tier_override_invalid():
    p = _baseline_payload()
    p["tier_override_invalid"] = True
    p["tier_override_invalid_value"] = "forge+"
    env = mod.assemble_envelope(p)
    assert any("tier_override_invalid: forge+" in w for w in env["skf_setup"]["warnings"])


def test_warnings_includes_tier_override_invalid_suggestion_when_present():
    p = _baseline_payload()
    p["tier_override_invalid"] = True
    p["tier_override_invalid_value"] = "forge+"
    p["tier_override_invalid_suggestion"] = "Forge+"
    env = mod.assemble_envelope(p)
    assert any("tier_override_invalid: forge+ (did you mean Forge+?)" in w
               for w in env["skf_setup"]["warnings"])


def test_warnings_omits_did_you_mean_when_suggestion_null():
    """No suggestion → fall back to the bare warning shape (no parenthetical)."""
    p = _baseline_payload()
    p["tier_override_invalid"] = True
    p["tier_override_invalid_value"] = "xyzzy"
    p["tier_override_invalid_suggestion"] = None
    env = mod.assemble_envelope(p)
    invalid_warnings = [w for w in env["skf_setup"]["warnings"] if "tier_override_invalid" in w]
    assert len(invalid_warnings) == 1
    assert "did you mean" not in invalid_warnings[0]
    assert "tier_override_invalid: xyzzy" in invalid_warnings[0]


def test_warnings_includes_tier_override_unsafe():
    p = _baseline_payload()
    p["tier_override_unsafe"] = True
    p["tier_override_unsafe_missing"] = ["gh", "qmd"]
    env = mod.assemble_envelope(p)
    assert any("tier_override_unsafe: missing gh, qmd" in w for w in env["skf_setup"]["warnings"])


def test_warnings_includes_ccc_exclusion_warnings():
    p = _baseline_payload()
    p["ccc_exclusion_warnings"] = [
        "skills_output_folder is empty; refused for ccc exclusion",
        "forge_data_folder contains glob meta; refused",
    ]
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["warnings"] == [
        "skills_output_folder is empty; refused for ccc exclusion",
        "forge_data_folder contains glob meta; refused",
    ]


def test_warnings_includes_ccc_registry_stale_removed():
    p = _baseline_payload()
    p["ccc_registry_stale_removed"] = ["/repo/old", "/repo/gone"]
    env = mod.assemble_envelope(p)
    assert "ccc_registry_stale_removed: /repo/old" in env["skf_setup"]["warnings"]
    assert "ccc_registry_stale_removed: /repo/gone" in env["skf_setup"]["warnings"]


def test_warnings_includes_qmd_daemon_stopped():
    p = _baseline_payload()
    p["qmd_status"] = "daemon_stopped"
    env = mod.assemble_envelope(p)
    assert "qmd_daemon_stopped" in env["skf_setup"]["warnings"]


def test_warnings_includes_ccc_indexing_failed_reason():
    p = _baseline_payload()
    p["ccc_indexing_failed_reason"] = "out of disk space"
    env = mod.assemble_envelope(p)
    assert "ccc_indexing_failed: out of disk space" in env["skf_setup"]["warnings"]


def test_warnings_includes_require_tier_failure():
    p = _baseline_payload()
    p["require_tier_satisfied"] = False
    p["require_tier_failure_missing"] = ["ccc"]
    env = mod.assemble_envelope(p)
    assert any("require_tier_failed: missing ccc" in w for w in env["skf_setup"]["warnings"])


# ─── files_written normalization ────────────────────────────────────────────


def test_files_written_dict_form_filtered_to_canonical_order():
    p = _baseline_payload()
    p["files_written"] = {
        "ccc_index": True,
        "preferences.yaml": False,  # falsy → excluded
        "forge-tier.yaml": True,
        "settings.yml": True,
        "unknown_key": True,        # not in VALID_FILES → excluded
    }
    env = mod.assemble_envelope(p)
    # Canonical order: forge-tier.yaml, preferences.yaml, settings.yml, ccc_index
    assert env["skf_setup"]["files_written"] == ["forge-tier.yaml", "settings.yml", "ccc_index"]


def test_files_written_list_form_normalized():
    p = _baseline_payload()
    p["files_written"] = ["ccc_index", "forge-tier.yaml"]
    env = mod.assemble_envelope(p)
    # Reordered to canonical order regardless of input order
    assert env["skf_setup"]["files_written"] == ["forge-tier.yaml", "ccc_index"]


def test_files_written_unknown_names_dropped():
    p = _baseline_payload()
    p["files_written"] = ["forge-tier.yaml", "unknown.yaml"]
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["files_written"] == ["forge-tier.yaml"]


# ─── error normalization ────────────────────────────────────────────────────


def test_error_null_serializes_as_null():
    env = mod.assemble_envelope(_baseline_payload())
    assert env["skf_setup"]["error"] is None


def test_error_object_includes_required_fields():
    p = _baseline_payload()
    p["error"] = {"phase": "step 2:write-config", "path": "/x/forge-tier.yaml", "reason": "permission denied"}
    env = mod.assemble_envelope(p)
    err = env["skf_setup"]["error"]
    assert err == {
        "phase": "step 2:write-config",
        "path": "/x/forge-tier.yaml",
        "reason": "permission denied",
    }


def test_error_object_missing_field_is_user_error():
    p = _baseline_payload()
    p["error"] = {"phase": "step 2", "path": "/x"}  # missing 'reason'
    with pytest.raises(SystemExit) as exc:
        mod.assemble_envelope(p)
    assert exc.value.code == 1


# ─── Validation rejects bad inputs ──────────────────────────────────────────


def test_invalid_tier_value_rejected():
    p = _baseline_payload()
    p["tier"] = "Sparkle"
    with pytest.raises(SystemExit):
        mod.assemble_envelope(p)


def test_invalid_previous_tier_value_rejected():
    p = _baseline_payload()
    p["previous_tier"] = "Sparkle"
    with pytest.raises(SystemExit):
        mod.assemble_envelope(p)


def test_invalid_ccc_index_status_rejected():
    p = _baseline_payload()
    p["ccc_index"]["status"] = "exploded"
    with pytest.raises(SystemExit):
        mod.assemble_envelope(p)


def test_empty_config_path_rejected():
    p = _baseline_payload()
    p["config_path"] = ""
    with pytest.raises(SystemExit):
        mod.assemble_envelope(p)


# ─── emit_envelope_line: output shape and determinism ───────────────────────


def test_envelope_line_starts_with_documented_prefix():
    env = mod.assemble_envelope(_baseline_payload())
    line = mod.emit_envelope_line(env)
    assert line.startswith("SKF_SETUP_RESULT_JSON: ")


def test_envelope_line_has_no_embedded_newline():
    env = mod.assemble_envelope(_baseline_payload())
    line = mod.emit_envelope_line(env)
    assert "\n" not in line
    # Body parses as JSON
    body = line[len("SKF_SETUP_RESULT_JSON: "):]
    parsed = json.loads(body)
    assert parsed == env


def test_envelope_line_is_deterministic_byte_for_byte():
    """Same input → byte-identical output (sort_keys=True ensures stability)."""
    p = _baseline_payload()
    line_a = mod.emit_envelope_line(mod.assemble_envelope(p))
    line_b = mod.emit_envelope_line(mod.assemble_envelope(p))
    assert line_a == line_b


# ─── Built-in stdlib JSON Schema validator ──────────────────────────────────


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_validator_accepts_valid_envelope():
    env = mod.assemble_envelope(_baseline_payload())
    assert mod._validate_against_schema(env, _schema()) == []


def test_validator_rejects_missing_required_property():
    env = mod.assemble_envelope(_baseline_payload())
    del env["skf_setup"]["tier"]
    errors = mod._validate_against_schema(env, _schema())
    assert any("missing required property 'tier'" in e for e in errors)


def test_validator_rejects_unexpected_property():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["surprise"] = "yes"
    errors = mod._validate_against_schema(env, _schema())
    assert any("unexpected property 'surprise'" in e for e in errors)


def test_validator_rejects_wrong_enum_value():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["tier"] = "Sparkle"
    errors = mod._validate_against_schema(env, _schema())
    assert any("not in enum" in e for e in errors)


def test_validator_rejects_wrong_type():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["tier_changed"] = "true"  # string, not bool
    errors = mod._validate_against_schema(env, _schema())
    assert any("expected type boolean" in e for e in errors)


def test_validator_rejects_duplicate_array_items():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["tools_added"] = ["ccc", "ccc"]
    errors = mod._validate_against_schema(env, _schema())
    assert any("not unique" in e for e in errors)


def test_validator_accepts_error_object_branch_of_oneOf():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["error"] = {"phase": "x", "path": "y", "reason": "z"}
    assert mod._validate_against_schema(env, _schema()) == []


def test_validator_rejects_error_object_missing_field():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["error"] = {"phase": "x"}
    errors = mod._validate_against_schema(env, _schema())
    # Should NOT match either oneOf branch (null-branch fails type, object-branch fails required)
    assert any("oneOf" in e for e in errors)


# ─── End-to-end CLI subprocess tests ────────────────────────────────────────


def _run_emit(payload: dict) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "emit"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def _run_validate(envelope: dict) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "validate"],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def test_cli_emit_produces_prefixed_one_line_output():
    rc, stdout, stderr = _run_emit(_baseline_payload())
    assert rc == 0, f"stderr: {stderr}"
    lines = stdout.strip().split("\n")
    assert len(lines) == 1
    assert lines[0].startswith(mod.ENVELOPE_PREFIX)
    body = json.loads(lines[0][len(mod.ENVELOPE_PREFIX):])
    assert body["skf_setup"]["tier"] == "Deep"


def test_cli_emit_default_subcommand_is_emit():
    """`skf-emit-result-envelope.py` with no subcommand should default to emit."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],  # no subcommand
        input=json.dumps(_baseline_payload()),
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(mod.ENVELOPE_PREFIX)


def test_cli_emit_rejects_invalid_payload():
    bad = _baseline_payload()
    bad["tier"] = "Sparkle"
    rc, _, stderr = _run_emit(bad)
    assert rc == 1
    err = json.loads(stderr)
    assert "tier" in err["message"]


def test_cli_validate_accepts_well_formed_envelope():
    env = mod.assemble_envelope(_baseline_payload())
    rc, stdout, stderr = _run_validate(env)
    assert rc == 0, f"stderr: {stderr}"
    assert stdout == ""


def test_cli_validate_rejects_malformed_envelope():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["tier"] = "Sparkle"
    rc, _, stderr = _run_validate(env)
    assert rc == 1
    err = json.loads(stderr)
    assert "tier" in err["message"]
