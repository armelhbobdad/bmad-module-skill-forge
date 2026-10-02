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
import os
import re
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


# The two step 2 write halts (write-config.md). A write failure has no
# status of its own: it is `blocked`, and error.phase names it.
STEP2_WRITE_ERRORS = [
    {"phase": "step 2:write-tools", "path": "/p/_bmad/_memory/forger-sidecar/forge-tier.yaml",
     "reason": "Permission denied"},
    {"phase": "step 2:forge-data-dir", "path": "/p/forge-data", "reason": "Permission denied"},
]


def _error(phase: str) -> dict:
    return {"phase": phase, "path": "/p/x", "reason": "r"}


@pytest.mark.parametrize("error", STEP2_WRITE_ERRORS, ids=lambda e: e["phase"])
def test_write_failure_phase_is_blocked_through_assemble_envelope(error):
    p = _baseline_payload()
    p["error"] = dict(error)
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["status"] == "blocked"
    assert mod._validate_against_schema(env, _schema()) == []


@pytest.mark.parametrize("phase", ["step 1:detect-tools", "on-activation:uv-missing",
                                   "step 3:overwrite-check", "write-config:forge-tier.yaml"])
def test_status_is_blocked_whatever_the_phase_says(phase):
    p = _baseline_payload()
    p["error"] = _error(phase)
    assert mod.assemble_envelope(p)["skf_setup"]["status"] == "blocked"


def test_error_outranks_a_tier_miss():
    p = _baseline_payload()
    p["error"] = dict(STEP2_WRITE_ERRORS[0])
    p["require_tier_satisfied"] = False
    p["require_tier_failure_missing"] = ["ccc"]
    e = mod.assemble_envelope(p)["skf_setup"]
    assert e["status"] == "blocked"
    assert "require_tier_failed: missing ccc" in e["warnings"]


def test_status_enum_lists_exactly_what_the_helper_emits():
    """Closure both ways: every status either builder can produce is in the
    schema enum, and the enum holds nothing the helper never emits."""
    enum = _schema()["properties"]["skf_setup"]["properties"]["status"]["enum"]
    assert enum == ["success", "tier_failure", "blocked"]
    errors = [None, *STEP2_WRITE_ERRORS, _error("write-config:forge-tier.yaml"),
              _error("Step 3:overwrite-check")]
    produced = {mod._compute_status(e, tier) for e in errors for tier in (None, True, False)}
    produced.add(mod.assemble_blocked_envelope("step 2:forge-data-dir", "r")["skf_setup"]["status"])
    assert produced == set(enum)


def test_schema_documents_the_blocked_envelope_placeholders():
    blocked = mod.assemble_blocked_envelope("on-activation:uv-missing", "r")["skf_setup"]
    props = _schema()["properties"]["skf_setup"]["properties"]
    assert f"'{blocked['tier']}'" in props["tier"]["description"]
    assert f"'{blocked['config_path']}'" in props["config_path"]["description"]
    error_path = props["error"]["oneOf"][1]["properties"]["path"]["description"]
    assert f"'{blocked['error']['path']}'" in error_path
    assert blocked["files_written"] == [] and "empty array" in props["files_written"]["description"]
    assert "exit code" not in json.dumps(_schema())


def test_envelope_helper_and_schema_cite_no_issue_or_pr_numbers():
    for path in (SCRIPT_PATH, SCHEMA_PATH):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"\b(?:PR|issue) #\d+|\bthis PR\b", text) is None, path.name


def test_docstring_lists_every_subcommand():
    subs = re.findall(r'sub\.add_parser\("([a-z-]+)"', SCRIPT_PATH.read_text(encoding="utf-8"))
    assert subs == ["emit", "emit-halt", "emit-blocked", "record", "validate", "render-report"]
    section = mod.__doc__.split("Subcommands:")[1].split("Context payload shape")[0]
    for name in subs:
        assert re.search(rf"^  {re.escape(name)}\b", section, re.M), name


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


def test_warnings_includes_orphan_auto_resolution_remove():
    p = _baseline_payload()
    p["orphan_auto_resolution"] = {
        "action": "remove",
        "count": 2,
        "source": "orphan-action-flag",
    }
    env = mod.assemble_envelope(p)
    assert any(
        "orphan_auto_resolution: remove 2 orphaned collection(s) "
        "(non-interactive, orphan-action-flag)" in w
        for w in env["skf_setup"]["warnings"]
    )


def test_warnings_includes_orphan_auto_resolution_headless_default_keep():
    p = _baseline_payload()
    p["orphan_auto_resolution"] = {
        "action": "keep",
        "count": 1,
        "source": "headless-default",
    }
    env = mod.assemble_envelope(p)
    assert any(
        "orphan_auto_resolution: keep 1 orphaned collection(s) "
        "(non-interactive, headless-default)" in w
        for w in env["skf_setup"]["warnings"]
    )


def test_warnings_includes_orphan_auto_resolution_quiet_default_keep():
    """`--quiet` alone keeps orphans without prompting and records its own source."""
    p = _baseline_payload()
    p["orphan_auto_resolution"] = {
        "action": "keep",
        "count": 3,
        "source": "quiet-default",
    }
    env = mod.assemble_envelope(p)
    assert (
        "orphan_auto_resolution: keep 3 orphaned collection(s) "
        "(non-interactive, quiet-default)"
    ) in env["skf_setup"]["warnings"]
    assert mod._validate_against_schema(env, mod._load_schema()) == []


def test_no_orphan_warning_when_resolution_absent_or_null():
    p = _baseline_payload()
    env = mod.assemble_envelope(p)
    assert not any("orphan_auto_resolution" in w for w in env["skf_setup"]["warnings"])
    p["orphan_auto_resolution"] = None
    env = mod.assemble_envelope(p)
    assert not any("orphan_auto_resolution" in w for w in env["skf_setup"]["warnings"])


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
    p["error"] = {"phase": "step 2:write-tools", "path": "/x/forge-tier.yaml", "reason": "permission denied"}
    env = mod.assemble_envelope(p)
    err = env["skf_setup"]["error"]
    assert err == {
        "phase": "step 2:write-tools",
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


def test_cli_emit_raw_utf8_stdin_survives_cp1252_stdio():
    # Issue #465: raw UTF-8 bytes (emoji NOT ASCII-escaped) on stdin plus
    # non-ASCII envelope output, under a cp1252 console (PYTHONIOENCODING
    # simulates it on any platform). Without the sys.stdin reconfigure the
    # emoji mojibakes and the round-trip assert fails; without the sys.stdout
    # reconfigure the ensure_ascii=False emit crashes with UnicodeEncodeError.
    payload = _baseline_payload()
    payload["config_path"] = "/abs/path \U0001F4CA/forge-tier.yaml"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "emit"],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    line = proc.stdout.decode("utf-8").strip()
    assert line.startswith(mod.ENVELOPE_PREFIX)
    body = json.loads(line[len(mod.ENVELOPE_PREFIX):])
    assert body["skf_setup"]["config_path"] == "/abs/path \U0001F4CA/forge-tier.yaml"


def _run_emit_blocked(payload: dict) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "emit-blocked"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def _envelope_of(stdout: str) -> dict:
    lines = stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith(mod.ENVELOPE_PREFIX), stdout
    return json.loads(lines[0][len(mod.ENVELOPE_PREFIX):])


@pytest.mark.parametrize("error", STEP2_WRITE_ERRORS, ids=lambda e: e["phase"])
def test_cli_emit_and_emit_blocked_agree_on_step2_write_errors(error):
    """The halt emits through emit-blocked; emit, given the same error, must
    not report a status the halt never produces."""
    p = _baseline_payload()
    p["error"] = dict(error)
    rc, stdout, stderr = _run_emit(p)
    assert rc == 0, stderr
    emitted = _envelope_of(stdout)["skf_setup"]
    rc, stdout, stderr = _run_emit_blocked(error)
    assert rc == 0, stderr
    blocked = _envelope_of(stdout)
    assert mod._validate_against_schema(blocked, _schema()) == []
    blocked = blocked["skf_setup"]
    assert emitted["status"] == blocked["status"] == "blocked"
    assert emitted["error"] == blocked["error"] == error
    assert blocked["files_written"] == []


def test_cli_validate_rejects_the_retired_write_failure_status():
    env = mod.assemble_envelope(_baseline_payload())
    env["skf_setup"]["status"] = "write_failure"
    rc, _, stderr = _run_validate(env)
    assert rc == 1
    assert "write_failure" in json.loads(stderr)["message"]


# ─── customization_resolver_unavailable (setup payload key) ─────────────────


def test_warnings_include_customization_resolver_unavailable():
    p = _baseline_payload()
    p["customization_resolver_unavailable"] = "resolve_customization.py exited 3 (Python 3.10)"
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["warnings"] == [
        "customization_resolver_unavailable: resolve_customization.py exited 3 (Python 3.10)"
    ]
    assert mod._validate_against_schema(env, _schema()) == []


@pytest.mark.parametrize("value", [None, "", False])
def test_no_resolver_warning_when_the_resolver_ran(value):
    p = _baseline_payload()
    p["customization_resolver_unavailable"] = value
    assert mod.assemble_envelope(p)["skf_setup"]["warnings"] == []


def test_resolver_warning_without_a_reason_says_unknown():
    p = _baseline_payload()
    p["customization_resolver_unavailable"] = True
    assert mod.assemble_envelope(p)["skf_setup"]["warnings"] == [
        "customization_resolver_unavailable: <unknown>"
    ]


def test_cli_emit_blocked_carries_the_resolver_warning():
    rc, stdout, stderr = _run_emit_blocked({
        "phase": "on-activation:config-missing", "reason": "config.yaml not found",
        "customization_resolver_unavailable": "resolver not installed",
    })
    assert rc == 0, stderr
    env = _envelope_of(stdout)
    assert env["skf_setup"]["warnings"] == ["customization_resolver_unavailable: resolver not installed"]
    assert mod._validate_against_schema(env, _schema()) == []


def test_resolver_payload_key_is_documented():
    doc = mod.__doc__
    assert '"customization_resolver_unavailable": "string|null"' in doc
    props = _schema()["properties"]["skf_setup"]["properties"]
    assert "customization_resolver_unavailable" in props["warnings"]["description"]


# ─── generic emitter: schema lookup ─────────────────────────────────────────


UPDATE_SCHEMA = SCHEMA_PATH.parent / "skf-update-result-envelope.v1.json"
BRIEF_SCHEMA = SCHEMA_PATH.parent / "skf-brief-result-envelope.v1.json"


@pytest.mark.parametrize("name,path", [
    ("skf-setup", SCHEMA_PATH), ("skf-update-skill", UPDATE_SCHEMA), ("skf-update", UPDATE_SCHEMA),
    ("skf-brief-skill", BRIEF_SCHEMA), ("skf-brief", BRIEF_SCHEMA),
])
def test_workflow_resolves_by_folder_name_or_schema_stem(name, path):
    schema, found = mod.load_workflow_schema(name)
    assert found == path
    assert schema == json.loads(path.read_text(encoding="utf-8"))


def test_unknown_workflow_is_a_user_error():
    with pytest.raises(SystemExit) as exc:
        mod.load_workflow_schema("skf-no-such-workflow")
    assert exc.value.code == 1


def test_the_highest_schema_version_wins(tmp_path, monkeypatch):
    for version in (1, 3, 2):
        schema = _demo_schema()
        schema["title"] = f"SKF_DEMO_RESULT_JSON envelope (v{version})"
        (tmp_path / f"skf-demo-result-envelope.v{version}.json").write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setattr(mod, "SCHEMA_DIR", tmp_path)
    schema, path = mod.load_workflow_schema("skf-demo")
    assert path.name == "skf-demo-result-envelope.v3.json"
    assert mod.load_workflow_schema("skf-demo-workflow")[1] == path


# ─── generic emitter: building an envelope ──────────────────────────────────


def _demo_schema() -> dict:
    """A flat envelope that declares every field the emitter stamps or derives."""
    decision = {
        "type": "object", "additionalProperties": False, "required": ["gate", "taken_action"],
        "properties": {"gate": {"type": "string", "minLength": 1}, "taken_action": {"type": "string"}},
    }
    error = {
        "type": "object", "additionalProperties": False, "required": ["code", "message"],
        "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "phase": {"type": "string"}},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SKF_DEMO_RESULT_JSON envelope (v1)",
        "$defs": {mod.META_KEY: {"const": {
            "workflow": "skf-demo-workflow", "prefix": "SKF_DEMO_RESULT_JSON", "wrapper": None,
            "halt_status": "error", "exit_codes": {"input-missing": 2, "write-failed": 4},
            "success_exit_code": 0, "result_file": "demo-result",
        }}},
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "skill_name", "count", "files", "mode", "timestamp", "run_id", "result_path",
                     "exit_code", "halt_reason", "headless_decisions", "warnings", "error"],
        "properties": {
            "status": {"type": "string", "enum": ["success", "error"]},
            "skill_name": {"type": "string", "minLength": 1},
            "count": {"type": "integer", "minimum": 0},
            "files": {"type": "array", "items": {"type": "string"}},
            "mode": {"type": "string", "enum": ["interactive", "auto"], "default": "interactive"},
            "timestamp": {"type": "string", "minLength": 1},
            "run_id": {"type": ["string", "null"]},
            "result_path": {"type": ["string", "null"]},
            "exit_code": {"type": "integer", "enum": [0, 2, 4]},
            "halt_reason": {"type": ["string", "null"], "enum": [None, "input-missing", "write-failed"]},
            "headless_decisions": {"type": "array", "items": decision},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "error": {"oneOf": [{"type": "null"}, error]},
        },
    }


STAMPS = {"timestamp": "2026-09-30T12:00:00Z", "run_id": "RUN42", "result_path": None}


def test_halt_envelope_maps_the_halt_and_fills_placeholders():
    schema = _demo_schema()
    halt = {"phase": "step-2:write", "reason": "disk full", "halt_reason": "write-failed",
            "path": "/p/out", "skill_name": "demo"}
    env = mod.build_envelope(schema, halt, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert env == {
        "status": "error", "skill_name": "demo", "count": 0, "files": [], "mode": "interactive",
        "timestamp": "2026-09-30T12:00:00Z", "run_id": "RUN42", "result_path": None,
        "exit_code": 4, "halt_reason": "write-failed", "headless_decisions": [], "warnings": [],
        "error": {"code": "write-failed", "message": "disk full", "phase": "step-2:write"},
    }
    assert list(env) == list(schema["properties"])
    assert mod.contract_errors(schema, env) == []


def test_halt_details_fill_the_error_object_that_declares_them():
    """A halt stages `details` beside its halt_reason and reason, never a hand-typed `error` object."""
    schema = _demo_schema()
    error = schema["properties"]["error"]["oneOf"][1]
    error["properties"]["details"] = {"description": "phase-specific context"}
    halt = {"phase": "step-2:write", "reason": "Write failed: could not write /p/out.", "halt_reason": "write-failed",
            "skill_name": "demo", "details": {"failed_path": "/p/out", "error": "it's full"}}
    env = mod.build_envelope(schema, halt, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert env["error"] == {"code": "write-failed", "message": "Write failed: could not write /p/out.",
                            "phase": "step-2:write", "details": {"failed_path": "/p/out", "error": "it's full"}}
    assert "details" not in env
    assert mod.contract_errors(schema, env) == []
    # A schema whose error object has no place for details drops them, as any halt key.
    plain = mod.build_envelope(_demo_schema(), halt, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert "details" not in plain and "details" not in plain["error"]
    assert mod.contract_errors(_demo_schema(), plain) == []
    # An error object the payload gives itself stays whole.
    given = {"code": "write-failed", "message": "typed", "details": {"kept": True}}
    env = mod.build_envelope(schema, {**halt, "error": given}, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert env["error"] == given


def test_quick_skill_halt_details_land_in_error_details():
    schema = json.loads((SCHEMA_PATH.parent / "skf-quick-skill-result-envelope.v1.json").read_text(encoding="utf-8"))
    halt = {"phase": "resolve-target", "halt_reason": "resolution-failure", "reason": "Tag 0.5.0 not found in acme/lib.",
            "skill_package": None, "details": {"requested_version": "0.5.0", "available_tags": ["v0.4.0"]}}
    env = mod.build_envelope(schema, halt, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert env["error"] == {"code": "resolution-failure", "message": "Tag 0.5.0 not found in acme/lib.",
                            "details": {"requested_version": "0.5.0", "available_tags": ["v0.4.0"]}}
    assert mod.contract_errors(schema, env) == []


def test_halt_payload_may_name_its_status_and_exit_code():
    schema = _demo_schema()
    schema["properties"]["status"]["enum"].append("halted-for-review")
    halt = {"phase": "p", "reason": "r", "halt_reason": "input-missing", "exit_code": 2,
            "status": "halted-for-review", "skill_name": "demo"}
    env = mod.build_envelope(schema, halt, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert env["status"] == "halted-for-review" and env["exit_code"] == 2


def test_a_halt_never_takes_the_success_exit_code():
    """Quick-skill's shape: exit_code and an error object, no halt_reason field."""
    schema = _demo_schema()
    del schema["properties"]["halt_reason"]
    schema["required"].remove("halt_reason")
    halt = {"phase": "p", "reason": "r", "skill_name": "demo"}
    env = mod.build_envelope(schema, halt, halt=True, stamps=STAMPS, decisions=[], warnings=[])
    assert "exit_code" not in env
    assert "$: missing required property 'exit_code'" in mod.contract_errors(schema, env)
    env = mod.build_envelope(schema, {**halt, "halt_reason": "write-failed"}, halt=True, stamps=STAMPS,
                             decisions=[], warnings=[])
    assert env["exit_code"] == 4 and env["error"]["code"] == "write-failed"
    env = mod.build_envelope(schema, {**halt, "exit_code": 2}, halt=True, stamps=STAMPS,
                             decisions=[], warnings=[])
    assert env["exit_code"] == 2


def test_a_finished_run_gets_no_halt_placeholders():
    schema = _demo_schema()
    ctx = {"status": "success", "skill_name": "demo", "halt_reason": None, "error": None}
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=[])
    assert "count" not in env and "files" not in env
    assert env["exit_code"] == 0 and env["mode"] == "interactive"
    errors = mod.contract_errors(schema, env)
    assert "$: missing required property 'count'" in errors


def test_stamps_replace_what_the_payload_typed():
    schema = _demo_schema()
    ctx = {"status": "success", "skill_name": "demo", "count": 1, "files": [], "halt_reason": None,
           "error": None, "timestamp": "typed by hand", "run_id": "typed", "result_path": "/typed"}
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=[])
    assert (env["timestamp"], env["run_id"], env["result_path"]) == ("2026-09-30T12:00:00Z", "RUN42", None)


def test_optional_lists_stay_out_while_empty():
    schema = _demo_schema()
    schema["required"] = [k for k in schema["required"] if k not in ("headless_decisions", "warnings")]
    ctx = {"status": "success", "skill_name": "demo", "count": 1, "files": [], "halt_reason": None,
           "error": None, "warnings": []}
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=[])
    assert "warnings" not in env and "headless_decisions" not in env
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=["w"])
    assert env["warnings"] == ["w"]


@pytest.mark.parametrize("status,halt_reason,message", [
    ("error", None, "halt_reason must be set when status is 'error'"),
    ("success", "write-failed", "halt_reason must be null when status is 'success'"),
])
def test_status_and_halt_reason_must_agree(status, halt_reason, message):
    schema = _demo_schema()
    ctx = {"status": status, "skill_name": "demo", "count": 1, "files": [], "halt_reason": halt_reason,
           "error": None}
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=[])
    assert any(message in e for e in mod.contract_errors(schema, env))


def test_exit_code_must_match_the_mapping():
    schema = _demo_schema()
    ctx = {"status": "error", "skill_name": "demo", "count": 0, "files": [], "halt_reason": "input-missing",
           "exit_code": 4, "error": None}
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=[])
    [error] = mod.contract_errors(schema, env)
    assert "does not match canonical mapping for halt_reason 'input-missing' (expected 2)" in error


def test_halt_needs_a_phase_and_a_reason():
    with pytest.raises(SystemExit) as exc:
        mod.build_envelope(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), {"phase": "p"}, halt=True)
    assert exc.value.code == 1


def test_a_halt_reason_of_the_wrong_type_is_a_schema_error_not_a_crash():
    schema = _demo_schema()
    ctx = {"status": "error", "skill_name": "demo", "count": 0, "files": [], "halt_reason": ["write-failed"],
           "error": None}
    env = mod.build_envelope(schema, ctx, halt=False, stamps=STAMPS, decisions=[], warnings=[])
    assert "exit_code" not in env
    assert "$.halt_reason: expected type ['string', 'null'], got list" in mod.contract_errors(schema, env)


def test_tolerant_payload_drops_what_the_envelope_cannot_take():
    ctx = {"status": "error", "skill_name": "demo", "halt_reason": "write-failed", "exit_code": 1,
           "reason": "disk full", "customization_resolver_unavailable": "no uv"}
    kept, notes = mod.tolerant_payload(_demo_schema(), ctx)
    assert kept == {"status": "error", "skill_name": "demo", "halt_reason": "write-failed",
                    "customization_resolver_unavailable": "no uv"}
    assert notes == ["payload_key_ignored: reason",
                     "exit_code_overridden: 1 (halt_reason write-failed maps to 4)"]


@pytest.mark.parametrize("extra", [{}, {"exit_code": 4}])
def test_tolerant_payload_is_silent_when_nothing_changes(extra):
    ctx = {"status": "error", "skill_name": "demo", "halt_reason": "write-failed", **extra}
    kept, notes = mod.tolerant_payload(_demo_schema(), ctx)
    assert notes == [] and "exit_code" not in kept


def test_tolerant_payload_keeps_an_exit_code_no_mapping_decides():
    schema = _demo_schema()
    del schema["$defs"][mod.META_KEY]["const"]["exit_codes"]
    kept, notes = mod.tolerant_payload(schema, {"status": "error", "halt_reason": "write-failed", "exit_code": 4})
    assert kept["exit_code"] == 4 and notes == []


# ─── generic emitter: run sink, clock and result files ──────────────────────


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """The demo schema installed as the only envelope schema, and a run folder."""
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "skf-demo-result-envelope.v1.json").write_text(json.dumps(_demo_schema()), encoding="utf-8")
    monkeypatch.setattr(mod, "SCHEMA_DIR", schemas)
    run_dir = tmp_path / ".skf-run" / "skf-demo-workflow-20260930T120000Z-7-beef"
    run_dir.mkdir(parents=True)
    return tmp_path, run_dir


def _run_in_process(monkeypatch, capsys, payload, halt=False, **kwargs):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    mod.run_emit("skf-demo-workflow", halt=halt, label="emit-halt" if halt else "emit", **kwargs)
    out, err = capsys.readouterr()
    [line] = out.splitlines()
    assert line.startswith("SKF_DEMO_RESULT_JSON: ")
    return json.loads(line[len("SKF_DEMO_RESULT_JSON: "):])


def _write_sink(run_dir: Path, decisions: list[str], warnings: list[str]) -> None:
    (run_dir / mod.SINK_DECISIONS).write_text("".join(f"{d}\n" for d in decisions), encoding="utf-8")
    (run_dir / mod.SINK_WARNINGS).write_text("".join(f"{w}\n" for w in warnings), encoding="utf-8")


HALT = {"phase": "step-1:input", "reason": "no target", "halt_reason": "input-missing", "skill_name": "demo"}


def test_halt_folds_the_sink_and_stamps_the_run(demo, monkeypatch, capsys):
    _, run_dir = demo
    _write_sink(run_dir,
                ['{"gate":"g1","taken_action":"C"}', '{"gate":"g1", "taken_action":"C"}',
                 '{"gate":"g2"', '{"gate":"","taken_action":"C"}', '{"gate":"g3","taken_action":"S"}'],
                ['"w1"', '"w1"', "7"])
    env = _run_in_process(monkeypatch, capsys, {**HALT, "headless_decisions": [{"gate": "g0", "taken_action": "C"}]},
                          halt=True, run_dir=str(run_dir))
    assert env["headless_decisions"] == [{"gate": "g0", "taken_action": "C"}, {"gate": "g1", "taken_action": "C"},
                                         {"gate": "g3", "taken_action": "S"}]
    assert env["warnings"][0] == "w1"
    assert f"sink_line_unreadable: {mod.SINK_DECISIONS}:3" in env["warnings"]
    assert f"sink_line_unreadable: {mod.SINK_WARNINGS}:3" in env["warnings"]
    assert any(w.startswith(f"headless_decision_invalid: {mod.SINK_DECISIONS}:4: ") for w in env["warnings"])
    assert env["run_id"] == "20260930T120000Z-7-beef"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", env["timestamp"])
    assert env["result_path"] is None


def test_resolver_payload_key_becomes_a_warning_in_any_workflow(demo, monkeypatch, capsys):
    _, run_dir = demo
    env = _run_in_process(monkeypatch, capsys, {**HALT, "customization_resolver_unavailable": "no uv"},
                          halt=True, run_dir=str(run_dir))
    assert env["warnings"] == ["customization_resolver_unavailable: no uv"]
    assert "customization_resolver_unavailable" not in env


ISO_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


def test_the_timestamp_is_the_system_clock(demo, monkeypatch, capsys):
    _, run_dir = demo
    monkeypatch.setattr(mod.time, "time", lambda: 1790000000.9)
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir))
    assert env["timestamp"] == mod._stamps(1790000000)[0] == "2026-09-21T14:13:20Z"


def test_a_halt_needs_no_run_folder_and_makes_none(demo, monkeypatch, capsys):
    """An early halt can fire before any `record` made the run folder: the
    clock needs no folder, so the call leaves the disk as it found it."""
    tmp_path, _ = demo
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    run_dir = project / "_bmad-output" / ".skf-run" / "skf-demo-workflow-RUN9"
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir))
    assert re.fullmatch(ISO_UTC, env["timestamp"]) and env["run_id"] == "RUN9"
    assert list(project.iterdir()) == []
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True)
    assert re.fullmatch(ISO_UTC, env["timestamp"]) and env["run_id"] is None
    assert list(project.iterdir()) == []


def test_the_clock_no_longer_probes_the_filesystem():
    assert not hasattr(mod, "_clock") and not hasattr(mod, "_clock_fallbacks")
    assert ".skf-emit-clock" not in SCRIPT_PATH.read_text(encoding="utf-8")
    assert "time.time()" in mod.__doc__


def test_result_files_hold_the_envelope_when_no_contract_is_given(demo, monkeypatch, capsys):
    tmp_path, run_dir = demo
    version = tmp_path / "demo" / "1.0.0"
    version.mkdir(parents=True)
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir), result_dir=str(version))
    [per_run] = [p for p in version.glob("demo-result-*.json") if not p.name.endswith("-latest.json")]
    assert re.fullmatch(r"demo-result-\d{8}-\d{6}\.json", per_run.name)
    assert env["result_path"] == per_run.as_posix()
    stamp = per_run.name[len("demo-result-"):-len(".json")]
    assert env["timestamp"] == (f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T"
                                f"{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z")
    record = json.loads(per_run.read_text(encoding="utf-8"))
    assert record == env
    assert (version / "demo-result-latest.json").read_text(encoding="utf-8") == per_run.read_text(encoding="utf-8")
    assert sorted(p.name for p in version.iterdir()) == sorted([per_run.name, "demo-result-latest.json"])


def test_result_contract_gets_the_run_stamps(demo, monkeypatch, capsys):
    tmp_path, run_dir = demo
    version = tmp_path / "v"
    version.mkdir()
    _write_sink(run_dir, ['{"gate":"g1","taken_action":"C"}'], ['"w1"'])
    ctx = {"status": "success", "skill_name": "demo", "count": 2, "files": ["SKILL.md"], "halt_reason": None,
           "error": None, "result_contract": {"skill": "skf-demo-workflow", "status": "success",
                                              "timestamp": "typed", "outputs": [], "summary": {"n": 2}}}
    env = _run_in_process(monkeypatch, capsys, ctx, run_dir=str(run_dir), result_dir=str(version))
    record = json.loads((version / "demo-result-latest.json").read_text(encoding="utf-8"))
    assert record == {"skill": "skf-demo-workflow", "status": "success", "timestamp": env["timestamp"],
                      "outputs": [], "summary": {"n": 2}, "run_id": "20260930T120000Z-7-beef",
                      "headless_decisions": [{"gate": "g1", "taken_action": "C"}], "warnings": ["w1"]}
    assert "result_contract" not in env


def test_result_contract_takes_the_payloads_summary_and_status_when_it_leaves_them_out(demo, monkeypatch, capsys):
    """A workflow lists its summary once: the record defaults to the payload's own."""
    tmp_path, run_dir = demo
    version = tmp_path / "v"
    version.mkdir()
    ctx = {"status": "success", "skill_name": "demo", "count": 2, "files": [], "halt_reason": None, "error": None,
           "summary": {"n": 2, "note": "it's done"},
           "result_contract": {"skill": "skf-demo-workflow", "outputs": [{"type": "skill", "path": "/p/SKILL.md"}]}}
    schema = _demo_schema()
    schema["properties"]["summary"] = {"type": "object"}
    (tmp_path / "schemas" / "skf-demo-result-envelope.v1.json").write_text(json.dumps(schema), encoding="utf-8")
    env = _run_in_process(monkeypatch, capsys, ctx, run_dir=str(run_dir), result_dir=str(version))
    record = json.loads((version / "demo-result-latest.json").read_text(encoding="utf-8"))
    assert record["status"] == "success" and record["summary"] == {"n": 2, "note": "it's done"}
    assert record["outputs"] == [{"type": "skill", "path": "/p/SKILL.md"}]
    assert env["summary"] == record["summary"]
    # A contract's own status and summary win over the payload's.
    ctx["result_contract"] = {**ctx["result_contract"], "status": "partial", "summary": {"n": 1}}
    _run_in_process(monkeypatch, capsys, ctx, run_dir=str(run_dir), result_dir=str(version))
    record = json.loads((version / "demo-result-latest.json").read_text(encoding="utf-8"))
    assert (record["status"], record["summary"]) == ("partial", {"n": 1})


def test_no_result_files_when_the_folder_does_not_exist(demo, monkeypatch, capsys):
    tmp_path, run_dir = demo
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir),
                          result_dir=str(tmp_path / "not-created-yet"))
    assert env["result_path"] is None
    assert not (tmp_path / "not-created-yet").exists()


def test_a_failed_record_write_is_a_warning(demo, monkeypatch, capsys):
    tmp_path, run_dir = demo
    version = tmp_path / "v"
    version.mkdir()

    def refuse(path, value):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(mod, "_write_json_atomic", refuse)
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir), result_dir=str(version))
    assert env["result_path"] is None
    [warning] = env["warnings"]
    assert warning.startswith("result_file_write_failed: ") and warning.endswith(": No space left on device")
    assert list(version.iterdir()) == []


def test_a_result_folder_that_refuses_the_record_is_a_warning(demo, monkeypatch, capsys):
    """The clock no longer probes the folder, so claiming the record is the first write it sees."""
    tmp_path, run_dir = demo
    version = tmp_path / "v"
    version.mkdir()

    def refuse(result_dir, stem, stamp):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(mod, "_claim_result_path", refuse)
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir), result_dir=str(version))
    assert env["result_path"] is None and re.fullmatch(ISO_UTC, env["timestamp"])
    assert env["warnings"] == [f"result_file_write_failed: {version.as_posix()}: Permission denied"]
    assert list(version.iterdir()) == []


def test_a_failed_latest_copy_keeps_the_record(demo, monkeypatch, capsys):
    """The per-run record was written: result_path keeps naming it."""
    tmp_path, run_dir = demo
    version = tmp_path / "v"
    version.mkdir()
    write = mod._write_json_atomic

    def refuse_latest(path, value):
        if path.name.endswith("-latest.json"):
            raise OSError(28, "No space left on device")
        write(path, value)

    monkeypatch.setattr(mod, "_write_json_atomic", refuse_latest)
    env = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir), result_dir=str(version))
    [per_run] = list(version.iterdir())
    assert re.fullmatch(r"demo-result-\d{8}-\d{6}\.json", per_run.name)
    assert env["result_path"] == per_run.as_posix()
    assert env["warnings"] == [f"result_file_write_failed: {(version / 'demo-result-latest.json').as_posix()}: "
                               "No space left on device"]
    record = json.loads(per_run.read_text(encoding="utf-8"))
    assert record["result_path"] == per_run.as_posix() and record["warnings"] == []


@pytest.mark.parametrize("run_name,stamped", [
    ("skf-demo-workflow-20260930-120000", True),
    ("skf-demo-workflow-20260930T120000Z-7-beef", False),
    ("skf-demo-workflow-2026093O-120000", False),
], ids=["run-stamp", "not-a-stamp", "letter-o"])
def test_result_stamp_run_id_names_the_record_after_the_run(demo, monkeypatch, capsys, run_name, stamped):
    """The W3 handoff: with `result_stamp: "run_id"`, the per-run record carries
    the run's own YYYYMMDD-HHmmss stamp, the one its report files carry, and
    keeps the -2 suffix of a name another run took; any other run_id falls
    back to the clock."""
    tmp_path, _ = demo
    schema = _demo_schema()
    schema["$defs"][mod.META_KEY]["const"]["result_stamp"] = "run_id"
    (tmp_path / "schemas" / "skf-demo-result-envelope.v1.json").write_text(json.dumps(schema), encoding="utf-8")
    run_dir = tmp_path / ".skf-run" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    version = tmp_path / "v"
    version.mkdir()
    monkeypatch.setattr(mod.time, "time", lambda: 1790000000)
    first = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir), result_dir=str(version))
    second = _run_in_process(monkeypatch, capsys, HALT, halt=True, run_dir=str(run_dir), result_dir=str(version))
    stamp = "20260930-120000" if stamped else mod._stamps(1790000000)[1]
    assert first["result_path"] == (version / f"demo-result-{stamp}.json").as_posix()
    assert second["result_path"] == (version / f"demo-result-{stamp}-2.json").as_posix()
    # The envelope's own timestamp stays the clock's.
    assert first["timestamp"] == mod._stamps(1790000000)[0]


def test_verify_stack_names_its_record_after_the_run():
    schema, _ = mod.load_workflow_schema("skf-verify-stack")
    assert mod._meta_of(schema)["result_stamp"] == "run_id"
    assert "run's own stamp" in schema["properties"]["result_path"]["description"]


def test_same_second_records_never_share_a_name(tmp_path):
    first = mod._claim_result_path(tmp_path, "demo-result", "20260930-120000")
    second = mod._claim_result_path(tmp_path, "demo-result", "20260930-120000")
    third = mod._claim_result_path(tmp_path, "demo-result", "20260930-120000")
    assert [p.name for p in (first, second, third)] == [
        "demo-result-20260930-120000.json", "demo-result-20260930-120000-2.json",
        "demo-result-20260930-120000-3.json"]


@pytest.mark.parametrize("args,payload,prefix,workflow", [
    (("emit",), _baseline_payload(), "SKF_SETUP_RESULT_JSON: ", "skf-setup"),
    (("emit-halt", "--workflow", "skf-brief-skill"),
     {"phase": "step-1:input", "reason": "no target", "halt_reason": "input-missing", "skill_name": "demo"},
     "SKF_BRIEF_RESULT_JSON: ", "skf-brief-skill"),
])
def test_result_dir_for_a_workflow_without_result_files_is_ignored(tmp_path, args, payload, prefix, workflow):
    """A halt that passes the flag by mistake still reports, and says so."""
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH), *args, "--result-dir", str(tmp_path)],
                          input=json.dumps(payload), capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    env = json.loads(proc.stdout[len(prefix):])
    assert f"result_dir_ignored: {workflow} writes no result file" in env.get("skf_setup", env)["warnings"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("seconds", [0, 951782400, 951868799, 1709164800, 1790000000, 4102444800,
                                     253402300799])
def test_utc_parts_match_the_calendar(seconds):
    from datetime import datetime, timedelta, timezone
    # Epoch arithmetic, not datetime.fromtimestamp: Windows' C runtime
    # rejects timestamps this far out (OSError, errno 22).
    expected = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    assert mod._utc_parts(seconds) == (expected.year, expected.month, expected.day,
                                       expected.hour, expected.minute, expected.second)
    iso, stamp = mod._stamps(seconds)
    assert iso == expected.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert stamp == expected.strftime("%Y%m%d-%H%M%S")


# ─── generic emitter: CLI (record, emit-halt, validate) ─────────────────────


def _cli(*args, payload=None, timeout=10):
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args],
                          input=None if payload is None else json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=timeout)


UPDATE_DECISION = {"gate": "init.update-confirmation", "default_action": "C", "taken_action": "C",
                   "reason": "headless: no user to prompt"}
UPDATE_HALT = {"phase": "merge:new-version-folder", "reason": "the version folder already exists",
               "path": "/p/skills/demo/1.0.1", "status": "halted-for-write-failure",
               "skill_name": "demo", "version": "1.0.1", "previous_version": "1.0.0", "update_mode": "normal"}


def test_cli_record_appends_decisions_and_warnings(tmp_path):
    run_dir = tmp_path / "skf-update-skill-RUN1"
    assert _cli("record", "--workflow", "skf-update-skill", "--run-dir", str(run_dir), "--decision",
                payload=UPDATE_DECISION).returncode == 0
    assert _cli("record", "--run-dir", str(run_dir), "--warning", "  source-not-fetched: offline ").returncode == 0
    assert (run_dir / mod.SINK_DECISIONS).read_text(encoding="utf-8").splitlines() == [
        json.dumps(UPDATE_DECISION, separators=(",", ":"))]
    assert (run_dir / mod.SINK_WARNINGS).read_text(encoding="utf-8") == '"source-not-fetched: offline"\n'


@pytest.mark.parametrize("args,payload", [
    (("--decision", "--workflow", "skf-update-skill"), {"gate": "not.a.gate", "default_action": "C",
                                                          "taken_action": "C", "reason": "r"}),
    (("--decision",), ["not", "an", "object"]),
    (("--decision",), {}),
    (("--warning", "   "), None),
    (("--decision", "--workflow", "skf-brief-skill"), {"gate": "g"}),
])
def test_cli_record_refuses_what_the_sink_cannot_hold(tmp_path, args, payload):
    run_dir = tmp_path / "run"
    proc = _cli("record", "--run-dir", str(run_dir), *args, payload=payload)
    assert proc.returncode == 1, proc.stderr
    assert not (run_dir / mod.SINK_DECISIONS).exists() and not (run_dir / mod.SINK_WARNINGS).exists()


def test_cli_update_halt_carries_the_wrapper_and_the_sink(tmp_path):
    run_dir = tmp_path / "skf-update-skill-RUN1"
    _cli("record", "--run-dir", str(run_dir), "--decision", payload=UPDATE_DECISION)
    _cli("record", "--run-dir", str(run_dir), "--warning", "customization_resolver_unavailable: no uv")
    proc = _cli("emit-halt", "--workflow", "skf-update-skill", "--run-dir", str(run_dir), payload=UPDATE_HALT)
    assert proc.returncode == 0, proc.stderr
    [line] = proc.stdout.splitlines()
    assert line.startswith("SKF_UPDATE_RESULT_JSON: {\"skf_update\":{\"status\":")
    env = json.loads(line[len("SKF_UPDATE_RESULT_JSON: "):])
    assert env == {"skf_update": {
        "status": "halted-for-write-failure", "skill_name": "demo", "version": "1.0.1",
        "previous_version": "1.0.0", "update_mode": "normal", "files_written": [],
        "headless_decisions": [UPDATE_DECISION], "warnings": ["customization_resolver_unavailable: no uv"],
        "error": {"phase": "merge:new-version-folder", "path": "/p/skills/demo/1.0.1",
                  "reason": "the version folder already exists"},
    }}
    assert _cli("validate", "--workflow", "skf-update-skill", payload=env).returncode == 0


# str.splitlines() breaks a line at each of these, and json.dumps leaves them
# raw when it keeps non-ASCII text.
LINE_BREAKS = "one\u2028two\x85three\u2029four"


def test_cli_record_then_halt_keeps_line_breaks_inside_values(tmp_path):
    run_dir = tmp_path / "skf-update-skill-RUN1"
    decision = {**UPDATE_DECISION, "reason": f"headless: {LINE_BREAKS}"}
    assert _cli("record", "--workflow", "skf-update-skill", "--run-dir", str(run_dir), "--decision",
                payload=decision).returncode == 0
    assert _cli("record", "--run-dir", str(run_dir), "--warning", f"w: {LINE_BREAKS}").returncode == 0
    for name in (mod.SINK_DECISIONS, mod.SINK_WARNINGS):
        raw = (run_dir / name).read_bytes()
        assert raw.isascii() and raw.count(b"\n") == 1, name
    proc = _cli("emit-halt", "--workflow", "skf-update-skill", "--run-dir", str(run_dir), payload=UPDATE_HALT)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.isascii()
    [line] = proc.stdout.splitlines()
    env = json.loads(line[len("SKF_UPDATE_RESULT_JSON: "):])["skf_update"]
    assert env["headless_decisions"] == [decision]
    assert env["warnings"] == [f"w: {LINE_BREAKS}"]


def test_a_raw_line_break_in_a_sink_line_stays_in_its_line(tmp_path):
    """A sink line written by hand may hold one raw inside a string."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_sink(run_dir, [json.dumps({"gate": "g", "note": LINE_BREAKS}, ensure_ascii=False)],
                [json.dumps(LINE_BREAKS, ensure_ascii=False)])
    decisions, warnings, problems = mod.read_sink(run_dir)
    assert decisions == [(f"{mod.SINK_DECISIONS}:1", {"gate": "g", "note": LINE_BREAKS})]
    assert warnings == [LINE_BREAKS] and problems == []


def test_workflow_lines_are_ascii_json():
    halt = {**UPDATE_HALT, "skill_name": "d\u00e9mo-\u65e5\u672c"}
    proc = _cli("emit-halt", "--workflow", "skf-update-skill", payload=halt)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.isascii() and "d\\u00e9mo" in proc.stdout
    env = json.loads(proc.stdout[len("SKF_UPDATE_RESULT_JSON: "):])
    assert env["skf_update"]["skill_name"] == "d\u00e9mo-\u65e5\u672c"


def test_setup_line_escapes_only_the_line_breaks():
    p = _baseline_payload()
    p["ccc_exclusion_warnings"] = [f"caf\u00e9 {LINE_BREAKS}"]
    proc = _cli("emit", payload=p)
    assert proc.returncode == 0, proc.stderr
    assert "caf\u00e9 one\\u2028two\\u0085three\\u2029four" in proc.stdout
    assert _envelope_of(proc.stdout)["skf_setup"]["warnings"] == [f"caf\u00e9 {LINE_BREAKS}"]


def test_setup_emit_appends_the_sink_warnings_it_lacks(tmp_path):
    """Setup's own warnings stay as its builders made them, repeats included."""
    run_dir = tmp_path / "skf-setup-RUN1"
    run_dir.mkdir()
    _write_sink(run_dir, [], ['"qmd_daemon_stopped"', '"customization_resolver_unavailable: no uv"'])
    p = _baseline_payload()
    p["qmd_status"] = "daemon_stopped"
    p["ccc_exclusion_warnings"] = ["same", "same"]
    proc = _cli("emit", "--run-dir", str(run_dir), payload=p)
    assert proc.returncode == 0, proc.stderr
    env = _envelope_of(proc.stdout)
    assert env["skf_setup"]["warnings"] == ["same", "same", "qmd_daemon_stopped",
                                            "customization_resolver_unavailable: no uv"]
    assert mod._validate_against_schema(env, _schema()) == []
    proc = _cli("emit", payload=p)
    assert _envelope_of(proc.stdout)["skf_setup"]["warnings"] == ["same", "same", "qmd_daemon_stopped"]


def test_cli_update_halt_defaults_to_blocked():
    halt = {k: v for k, v in UPDATE_HALT.items() if k not in ("status", "path")}
    proc = _cli("emit-halt", "--workflow", "skf-update", payload=halt)
    assert proc.returncode == 0, proc.stderr
    env = json.loads(proc.stdout[len("SKF_UPDATE_RESULT_JSON: "):])["skf_update"]
    assert env["status"] == "blocked"
    assert env["error"] == {"phase": "merge:new-version-folder", "reason": "the version folder already exists"}


def test_cli_validate_rejects_an_unwrapped_update_halt_line():
    unwrapped = {"status": "blocked", "error": {"phase": "init:concurrency", "reason": "another run"}}
    proc = _cli("validate", "--workflow", "skf-update-skill", payload=unwrapped)
    assert proc.returncode == 1
    assert "missing required property 'skf_update'" in json.loads(proc.stderr)["message"]


def test_cli_update_halt_missing_required_fields_is_a_user_error():
    proc = _cli("emit-halt", "--workflow", "skf-update-skill",
                payload={"phase": "init:source-tree", "reason": "no commit"})
    assert proc.returncode == 1 and proc.stdout == ""
    assert "missing required property 'skill_name'" in json.loads(proc.stderr)["message"]


def test_cli_emit_halt_needs_a_workflow():
    proc = _cli("emit-halt", payload={"phase": "p", "reason": "r"})
    assert proc.returncode == 2 and "--workflow" in proc.stderr


def test_cli_setup_halt_through_emit_halt_matches_emit_blocked():
    payload = {"phase": "step 2:write-tools", "path": "/p/forge-tier.yaml", "reason": "Permission denied"}
    halt = _cli("emit-halt", "--workflow", "skf-setup", payload=payload)
    blocked = _cli("emit-blocked", payload=payload)
    assert halt.returncode == blocked.returncode == 0
    assert halt.stdout == blocked.stdout


def test_cli_emit_to_stderr(tmp_path):
    proc = _cli("emit-halt", "--workflow", "skf-brief-skill", "--target", "stderr",
                payload={"phase": "step-1:input", "reason": "no target", "halt_reason": "input-missing",
                         "skill_name": "demo"})
    assert proc.returncode == 0 and proc.stdout == ""
    assert proc.stderr.startswith("SKF_BRIEF_RESULT_JSON: ")


def test_installed_layout_finds_the_sibling_schemas(tmp_path):
    """Installed under _bmad/skf/shared/scripts/, with no src/ tree above it."""
    import shutil
    scripts = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
    shutil.copytree(SCHEMA_PATH.parent, scripts / "schemas")
    shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)
    proc = subprocess.run([sys.executable, str(scripts / SCRIPT_PATH.name), "emit-halt", "--workflow",
                           "skf-update-skill"], input=json.dumps(UPDATE_HALT), capture_output=True,
                          text=True, encoding="utf-8", timeout=10, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("SKF_UPDATE_RESULT_JSON: ")


# ─── the docs describe the emitter and the sink ─────────────────────────────


REFS = ROOT / "src" / "shared" / "references"


def test_headless_gate_convention_describes_the_emitter_and_the_sink():
    text = (REFS / "headless-gate-convention.md").read_text(encoding="utf-8")
    for token in (mod.SINK_DECISIONS, mod.SINK_WARNINGS, "_bmad-output/.skf-run/<workflow>-<run_id>/",
                  " record ", " emit-halt ", "customization_resolver_unavailable", mod.META_KEY):
        assert token in text, token


def test_output_contract_names_what_the_emitter_stamps():
    text = (REFS / "output-contract-schema.md").read_text(encoding="utf-8")
    for token in ("result_contract", "--result-dir", '"run_id"', '"headless_decisions"', '"warnings"',
                  "-2", "result_file_write_failed", "Do not reuse"):
        assert (token in text) == (token != "Do not reuse"), token


def test_docstring_names_every_envelope_block_field_and_sink_file():
    for token in (*mod.META_FIELDS, mod.SINK_DECISIONS, mod.SINK_WARNINGS, *mod.PAYLOAD_ONLY_KEYS):
        assert token in mod.__doc__, token


# ─── skf-setup: orphan removals by name, files_written derived ──────────────


def test_unprompted_orphan_removals_name_each_collection():
    p = _baseline_payload()
    p["orphan_auto_resolution"] = {"action": "remove", "count": 3, "source": "orphan-action-flag",
                                   "removed": ["a-docs", "b-brief"], "failed": ["c-temporal"]}
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["warnings"] == [
        "orphan_auto_resolution: remove 3 orphaned collection(s) (non-interactive, orphan-action-flag)",
        "orphan_removed: a-docs", "orphan_removed: b-brief", "orphan_remove_failed: c-temporal"]
    assert mod._validate_against_schema(env, _schema()) == []


def test_a_kept_orphan_decision_names_no_collection():
    p = _baseline_payload()
    p["orphan_auto_resolution"] = {"action": "keep", "count": 2, "source": "quiet-default"}
    assert mod.assemble_envelope(p)["skf_setup"]["warnings"] == [
        "orphan_auto_resolution: keep 2 orphaned collection(s) (non-interactive, quiet-default)"]


@pytest.mark.parametrize("flags,expected", [
    ({}, ["forge-tier.yaml"]),
    # Setup never writes preferences.yaml: the installer creates it.
    ({"preferences_yaml_created": True}, ["forge-tier.yaml"]),
    ({"settings_yml_written": True, "ccc_index": {"status": "created", "indexed_path": "/p", "file_count": 9}},
     ["forge-tier.yaml", "settings.yml", "ccc_index"]),
    ({"ccc_index": {"status": "fresh", "indexed_path": "/p", "file_count": 9}}, ["forge-tier.yaml"]),
], ids=["minimal", "old-prefs-flag-ignored", "settings-and-new-index", "fresh-index"])
def test_files_written_is_derived_when_the_payload_leaves_it_out(flags, expected):
    p = {k: v for k, v in _baseline_payload().items() if k != "files_written"}
    p.update(flags)
    assert mod.assemble_envelope(p)["skf_setup"]["files_written"] == expected


def test_a_derived_files_written_is_empty_with_an_error():
    p = {k: v for k, v in _baseline_payload().items() if k != "files_written"}
    p["error"] = {"phase": "step 2:write-tools", "path": "/p/x", "reason": "r"}
    assert mod.assemble_envelope(p)["skf_setup"]["files_written"] == []


# ─── skf-setup: staged helper outputs ───────────────────────────────────────


GIT_BELOW = {"tool": "git", "name": "git", "version": "2.10.0", "minimum": "2.15",
             "upgrade": "Install the latest release from https://git-scm.com/downloads", "tier": None}


def _detect_output() -> dict:
    """skf-detect-tools.py's output for a Forge re-run that gained gh, on a git below its minimum."""
    return {
        "status": "ok", "version": "v1",
        "tools": {"ast_grep": {"available": True, "version": "ast-grep 0.45.3"},
                  "gh_cli": {"available": True, "version": "gh version 2.91.0 (2026-04-22)"},
                  "qmd": {"available": False, "status": "absent", "version": None},
                  "ccc": {"available": False, "daemon": None, "version": None},
                  "git": {"available": True, "version": "git version 2.10.0", "minimum": "2.15",
                          "meets_minimum": False, "below_minimum": True},
                  "security_scan": {"available": False}},
        "tools_below_minimum": [GIT_BELOW],
        "tier": {"calculated": "Forge", "detected": "Forge", "override_applied": False, "override_value": None,
                 "override_invalid": True, "override_invalid_value": "deep",
                 "override_invalid_suggestion": "Deep", "override_unsafe": False, "override_unsafe_missing": []},
        "require_tier": {"requested": "Forge+", "satisfied": False, "missing_tools": ["ccc"]},
        "prior": {"previous_tier": "Forge", "previous_detection_date": "2026-09-01T10:00:00Z",
                  "previous_tools": {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": False},
                  "previous_ccc_index_status": None, "previous_ccc_indexed_path": None,
                  "previous_ccc_last_indexed": None, "previous_ccc_staleness_threshold_hours": None,
                  "previous_ccc_file_count": None, "ccc_index_fresh": False},
        "deltas": {"tools_added": ["gh_cli"], "tools_removed": [], "tier_changed": False},
    }


# What report.md section 1 stages (only the values no helper output holds), with
# the paths --project-root, --sidecar-path and --forge-data-folder give.
REPORT_CONTEXT = {
    "project_root": "/p", "config_path": "/p/_bmad/_memory/forger-sidecar/forge-tier.yaml",
    "forge_data_folder": "/p/forge-data", "orphan_auto_resolution": None, "error": None,
}
CLASSIFIED = {"status": "ok", "version": "v1", "live_names": ["a-docs"], "healthy": ["a-docs"],
              "orphaned": [], "orphaned_paths": {}, "stale": [], "foreign_filtered_count": 0,
              "foreign_filtered_sample": []}
# skf-merge-ccc-exclusions.py --build-index's result, as its --result-to file holds it.
CCC_RESULT = {"status": "ok", "version": "v2", "written": True, "patterns_added": 3, "patterns_removed": 1,
              "gitignore_updated": True, "warnings": ["add /.cocoindex_code/ to {project-root}/.gitignore"],
              "effective_patterns": ["**/_bmad", "skills"], "index_action": "index",
              "index": {"status": "created", "indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00",
                        "file_count": 12, "failed_reason": None}}


def _stage(run_dir: Path, detect=None, classify=None, clean_stale=None, ccc=None, remove=None) -> Path:
    """A setup run folder: each helper output given (a string is written as it is) and the payload."""
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, value in ((mod.STAGED_DETECT, detect), (mod.STAGED_CLASSIFY, classify),
                        (mod.STAGED_CLEAN_STALE, clean_stale), (mod.STAGED_CCC, ccc),
                        (mod.STAGED_REMOVE, remove)):
        if value is not None:
            (run_dir / name).write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    (run_dir / "report-context.json").write_text(json.dumps(REPORT_CONTEXT), encoding="utf-8")
    return run_dir


def test_fold_staged_takes_every_detector_field_from_the_file():
    folded = mod.fold_staged({"tier": "Deep", "qmd_status": "healthy", "tools": {}},
                             {mod.STAGED_DETECT: _detect_output()})
    assert (folded["tier"], folded["previous_tier"]) == ("Forge", "Forge")
    assert folded["tools"]["gh_cli"] == {"available": True, "version": "gh version 2.91.0 (2026-04-22)"}
    assert folded["previous_tools"] == {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": False}
    assert (folded["tier_override_invalid"], folded["tier_override_invalid_value"],
            folded["tier_override_invalid_suggestion"]) == (True, "deep", "Deep")
    assert folded["tier_override_active"] is False and folded["tier_override_unsafe"] is False
    assert folded["tier_override_unsafe_missing"] == []
    assert (folded["require_tier_satisfied"], folded["require_tier_failure_missing"]) == (False, ["ccc"])
    assert folded["require_tier"] == "Forge+"
    assert folded["qmd_status"] == "absent"
    assert folded["tools_below_minimum"] == [GIT_BELOW]


def test_a_first_run_detector_output_reads_as_no_previous_tools():
    detect = _detect_output()
    detect["prior"].update(previous_tier=None, previous_tools={})
    folded = mod.fold_staged({}, {mod.STAGED_DETECT: detect})
    assert folded["previous_tier"] is None and folded["previous_tools"] is None


@pytest.mark.parametrize("classify,result,healthy", [
    (CLASSIFIED, "completed", 1),
    ({**CLASSIFIED, "healthy": []}, "completed", 0),
    (None, "qmd_unavailable", 0),
], ids=["classified", "none-healthy", "classifier-failed"])
def test_fold_staged_reads_the_qmd_classification(classify, result, healthy):
    folded = mod.fold_staged({}, {mod.STAGED_CLASSIFY: classify})
    assert (folded["hygiene_result"], folded["hygiene_healthy"]) == (result, healthy)


def test_fold_staged_reads_the_registry_cleanup():
    folded = mod.fold_staged({}, {mod.STAGED_CLEAN_STALE: {"qmd_removed": ["x-docs"],
                                                           "ccc_removed": ["/gone", "/old"], "wrote": True}})
    assert (folded["hygiene_stale_cleaned"], folded["ccc_registry_stale_cleaned"],
            folded["ccc_registry_stale_removed"]) == (1, 2, ["/gone", "/old"])
    failed = mod.fold_staged({}, {mod.STAGED_CLEAN_STALE: None})
    assert (failed["hygiene_stale_cleaned"], failed["ccc_registry_stale_cleaned"],
            failed["ccc_registry_stale_removed"]) == (0, 0, [])


def test_fold_staged_reads_the_ccc_result_and_keeps_its_notes_verbatim():
    """The W2 handoff: the merge helper's result passes by file, so no step
    binds or re-types written, patterns_added, patterns_removed,
    gitignore_updated or warnings, and an SKF-worded {project-root} stays."""
    folded = mod.fold_staged({}, {mod.STAGED_CCC: CCC_RESULT})
    assert (folded["settings_yml_written"], folded["settings_yml_patterns_added"],
            folded["settings_yml_patterns_removed"], folded["gitignore_updated"]) == (True, 3, 1, True)
    assert folded["ccc_exclusion_warnings"] == ["add /.cocoindex_code/ to {project-root}/.gitignore"]
    assert folded["ccc_index"] == {"status": "created", "indexed_path": "/p", "file_count": 12}
    assert folded["ccc_indexing_failed_reason"] is None
    env = mod.assemble_envelope({**_baseline_payload(), **folded})["skf_setup"]
    assert "add /.cocoindex_code/ to {project-root}/.gitignore" in env["warnings"]


@pytest.mark.parametrize("result,reason", [
    ({"status": "error", "message": "settings.yml is not a mapping"}, "settings.yml is not a mapping"),
    (None, "the ccc settings helper returned no result"),
    ({**CCC_RESULT, "index": {"status": "failed", "indexed_path": None, "last_indexed": None,
                              "file_count": None, "failed_reason": "ccc index exited 1: daemon down"}},
     "ccc index exited 1: daemon down"),
], ids=["helper-error", "empty-file", "index-failed"])
def test_fold_staged_reads_a_failed_ccc_preparation(result, reason):
    folded = mod.fold_staged({}, {mod.STAGED_CCC: result})
    assert folded["ccc_index"]["status"] == "failed"
    assert folded["ccc_indexing_failed_reason"] == reason
    env = mod.assemble_envelope({**_baseline_payload(), **folded})["skf_setup"]
    assert f"ccc_indexing_failed: {reason}" in env["warnings"]
    if result is None or result["status"] == "error":
        assert (folded["settings_yml_written"], folded["settings_yml_patterns_added"],
                folded["settings_yml_patterns_removed"], folded["gitignore_updated"],
                folded["ccc_exclusion_warnings"]) == (False, 0, 0, False, [])


def test_no_ccc_result_leaves_the_index_none():
    folded = mod.fold_staged({}, {mod.STAGED_DETECT: _detect_output()})
    assert "ccc_index" not in folded and "settings_yml_written" not in folded
    env = mod.assemble_envelope({**folded, "config_path": "/p/x", "error": None})["skf_setup"]
    assert env["ccc_index"] == {"status": "none", "indexed_path": None, "file_count": None}
    assert env["files_written"] == ["forge-tier.yaml"]


def test_a_missing_ccc_result_with_ccc_available_reads_as_a_failed_index():
    """Step 1b runs the helper whenever ccc is available, so no result file
    means it wrote nothing (a usage error, or a call its host stopped)."""
    detect = _detect_output()
    detect["tools"]["ccc"] = {"available": True, "daemon": "healthy", "version": "0.2.41"}
    folded = mod.fold_staged({}, {mod.STAGED_DETECT: detect})
    assert folded["ccc_index"] == {"status": "failed", "indexed_path": None, "file_count": None}
    assert folded["ccc_indexing_failed_reason"] == mod.CCC_NO_RESULT
    env = mod.assemble_envelope({**folded, "config_path": "/p/x", "error": None})["skf_setup"]
    assert env["ccc_index"]["status"] == "failed"
    assert f"ccc_indexing_failed: {mod.CCC_NO_RESULT}" in env["warnings"]
    assert env["files_written"] == ["forge-tier.yaml"]


ORPHANS = {**CLASSIFIED, "orphaned": ["a-brief", "b-docs", "c-temporal"]}


@pytest.mark.parametrize("staged,removed,kept,trail", [
    ({mod.STAGED_CLASSIFY: ORPHANS}, 0, 3, {"action": "keep", "source": "quiet-default", "count": 3}),
    ({mod.STAGED_CLASSIFY: ORPHANS,
      mod.STAGED_REMOVE: {"status": "ok", "removed": ["a-brief", "b-docs"], "failed": ["c-temporal"], "errors": {}}},
     2, 1, {"action": "remove", "source": "orphan-action-flag", "count": 3, "removed": ["a-brief", "b-docs"],
            "failed": ["c-temporal"]}),
    ({mod.STAGED_CLASSIFY: ORPHANS, mod.STAGED_REMOVE: None}, 0, 3,
     {"action": "remove", "source": "orphan-action-flag", "count": 3, "removed": [],
      "failed": ["a-brief", "b-docs", "c-temporal"]}),
], ids=["kept", "removed", "removal-printed-nothing"])
def test_fold_staged_counts_the_orphans_and_fills_the_audit_trail(staged, removed, kept, trail):
    """remove-orphans stages what it deleted: setup's payload names only the
    decision, and the emitter fills the count and the names."""
    decision = {key: trail[key] for key in ("action", "source")}
    folded = mod.fold_staged({"orphan_auto_resolution": decision}, staged)
    assert (folded["hygiene_orphaned_removed"], folded["hygiene_orphaned_kept"]) == (removed, kept)
    assert folded["orphan_auto_resolution"] == trail


def test_an_interactive_orphan_decision_stays_null():
    folded = mod.fold_staged({"orphan_auto_resolution": None},
                             {mod.STAGED_CLASSIFY: ORPHANS,
                              mod.STAGED_REMOVE: {"status": "ok", "removed": ["a-brief"], "failed": []}})
    assert folded["orphan_auto_resolution"] is None
    assert (folded["hygiene_orphaned_removed"], folded["hygiene_orphaned_kept"]) == (1, 0)


def test_read_staged_tells_a_failed_helper_from_one_that_never_ran(tmp_path):
    _stage(tmp_path / "run", detect=_detect_output(), classify="")
    staged = mod.read_staged(tmp_path / "run")
    assert staged[mod.STAGED_DETECT]["tier"]["calculated"] == "Forge"
    assert staged[mod.STAGED_CLASSIFY] is None
    assert mod.STAGED_CLEAN_STALE not in staged
    assert mod.read_staged(None) == {} and mod.read_staged(tmp_path / "missing") == {}


def test_read_staged_tolerates_a_byte_order_mark(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / mod.STAGED_DETECT).write_bytes(b"\xef\xbb\xbf" + json.dumps(_detect_output()).encode("utf-8"))
    assert mod.read_staged(run_dir)[mod.STAGED_DETECT]["tier"]["calculated"] == "Forge"


def _cli_in(args, stdin: str):
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", timeout=10)


def test_emit_from_staged_files_matches_the_hand_built_payload(tmp_path):
    """The envelope is unchanged: staging moves only where its values come from."""
    detect = _detect_output()
    run_dir = _stage(tmp_path / "skf-setup-RUN", detect=detect, classify=CLASSIFIED,
                     clean_stale={"qmd_removed": [], "ccc_removed": ["/gone"], "wrote": True})
    staged = _cli_in(["emit", "--run-dir", str(run_dir)], (run_dir / "report-context.json").read_text(encoding="utf-8"))
    assert staged.returncode == 0, staged.stderr
    full = {**REPORT_CONTEXT, "tier": "Forge", "previous_tier": "Forge", "tools": detect["tools"],
            "ccc_index": {"status": "none", "indexed_path": None, "file_count": None},
            "previous_tools": detect["prior"]["previous_tools"], "tier_override_active": False,
            "tier_override_invalid": True, "tier_override_invalid_value": "deep",
            "tier_override_invalid_suggestion": "Deep", "tier_override_unsafe": False,
            "tier_override_unsafe_missing": [], "require_tier_satisfied": False,
            "require_tier_failure_missing": ["ccc"], "qmd_status": "absent",
            "tools_below_minimum": [GIT_BELOW],
            "ccc_registry_stale_removed": ["/gone"], "files_written": ["forge-tier.yaml"]}
    rc, stdout, stderr = _run_emit(full)
    assert rc == 0, stderr
    assert staged.stdout == stdout
    env = _envelope_of(stdout)
    assert mod._validate_against_schema(env, _schema()) == []
    env = env["skf_setup"]
    assert env["status"] == "tier_failure" and env["tools_added"] == ["gh_cli"]
    assert "tier_override_invalid: deep (did you mean Deep?)" in env["warnings"]
    assert "ccc_registry_stale_removed: /gone" in env["warnings"]
    assert "tool_below_minimum: git 2.10.0 (minimum 2.15)" in env["warnings"]


def test_emit_reads_every_value_from_the_staged_files(tmp_path):
    """A Deep run with ccc whose step 4 payload holds only the paths, the
    orphan decision and a null error: every other value comes from a file."""
    detect = _detect_output()
    detect["tools"]["ccc"] = {"available": True, "daemon": "healthy", "version": "0.2.41"}
    detect["require_tier"] = {"requested": None, "satisfied": None, "missing_tools": []}
    run_dir = _stage(tmp_path / "skf-setup-RUN", detect=detect, classify=ORPHANS, ccc=CCC_RESULT,
                     remove={"status": "ok", "removed": ["a-brief", "b-docs", "c-temporal"], "failed": [],
                             "errors": {}},
                     clean_stale={"qmd_removed": [], "ccc_removed": [], "wrote": False})
    context = {**REPORT_CONTEXT, "orphan_auto_resolution": {"action": "remove", "source": "orphan-action-flag"}}
    done = _cli_in(["emit", "--run-dir", str(run_dir)], json.dumps(context))
    assert done.returncode == 0, done.stderr
    env = _envelope_of(done.stdout)
    assert mod._validate_against_schema(env, _schema()) == []
    env = env["skf_setup"]
    assert env["status"] == "success"
    assert env["files_written"] == ["forge-tier.yaml", "settings.yml", "ccc_index"]
    assert env["ccc_index"] == {"status": "created", "indexed_path": "/p", "file_count": 12}
    assert env["warnings"][-4:] == [
        "orphan_auto_resolution: remove 3 orphaned collection(s) (non-interactive, orphan-action-flag)",
        "orphan_removed: a-brief", "orphan_removed: b-docs", "orphan_removed: c-temporal"]
    assert "add /.cocoindex_code/ to {project-root}/.gitignore" in env["warnings"]
    banner = _cli_in(["render-report", "--run-dir", str(run_dir)], json.dumps(context))
    assert banner.returncode == 0, banner.stderr
    for line in ("  3 orphaned collection(s) removed", "  indexed this run, semantic discovery ready",
                 "  - add /.cocoindex_code/ to /p/.gitignore",
                 "  - .cocoindex_code/settings.yml: /p/.cocoindex_code/settings.yml (3 SKF exclusion pattern(s) "
                 "merged, 1 stale SKF pattern(s) removed)",
                 "  - .cocoindex_code/ ccc index: 12 files indexed"):
        assert line in banner.stdout.splitlines(), line


# ─── skf-setup: FORGE STATUS banner (render-report) ─────────────────────────


TIER_RULES = ROOT / "src" / "skf-setup" / "references" / "tier-rules.md"
MERGE_HELPER = ROOT / "src" / "shared" / "scripts" / "skf-merge-ccc-exclusions.py"
# The banner template render_report follows. report.md no longer holds it:
# the step displays what the script prints, and these tests keep the two in step.
BANNER_TEMPLATE = ROOT / "test" / "fixtures" / "setup-report" / "forge-status-template.txt"
COPY = mod.load_tier_rules(TIER_RULES)
RULE = "═" * 39

AST = {"available": True, "version": "ast-grep 0.45.3"}
GH = {"available": True, "version": "gh version 2.91.0 (2026-04-22)"}
QMD = {"available": True, "status": "healthy", "version": "qmd 2.8.3 (facd35e)"}
CCC = {"available": True, "daemon": "healthy", "version": None}
NO_AST = {"available": False, "version": None}
NO_GH = {"available": False, "version": None}
NO_QMD = {"available": False, "status": "absent", "version": None}
NO_CCC = {"available": False, "daemon": None, "version": None}


def _probes(ast=AST, gh=GH, qmd=NO_QMD, ccc=NO_CCC) -> dict:
    return {"ast_grep": ast, "gh_cli": gh, "qmd": qmd, "ccc": ccc}


def _banner_payload(**over) -> dict:
    """A same-tier Forge re-run with ast-grep and gh, and nothing else to report."""
    payload = {**REPORT_CONTEXT, "ccc_index": {"status": "none", "indexed_path": None, "file_count": None},
               "settings_yml_written": False, "settings_yml_patterns_added": 0, "settings_yml_patterns_removed": 0,
               "gitignore_updated": False, "ccc_exclusion_warnings": [], "ccc_indexing_failed_reason": None,
               "hygiene_orphaned_removed": 0, "hygiene_orphaned_kept": 0,
               "tier": "Forge", "previous_tier": "Forge", "tools": _probes(),
               "previous_tools": {"ast_grep": True, "gh_cli": True, "qmd": False, "ccc": False},
               "tier_override_active": False, "tier_override_invalid": False, "tier_override_unsafe": False,
               "require_tier_satisfied": None, "qmd_status": "absent", "hygiene_result": "skipped"}
    payload.update(over)
    return payload


def _banner(**over) -> list[str]:
    return mod.render_report(_banner_payload(**over), COPY)


def _ccc(daemon="healthy", index="fresh", count=None, **over) -> dict:
    """A same-tier Forge+ re-run with ccc (ast-grep, gh and ccc)."""
    return {"tier": "Forge+", "previous_tier": "Forge+",
            "tools": _probes(ccc={"available": True, "daemon": daemon, "version": None}),
            "previous_tools": {"ast_grep": True, "gh_cli": True, "qmd": False, "ccc": True},
            "ccc_index": {"status": index, "indexed_path": "/p" if index in ("fresh", "created") else None,
                          "file_count": count}, **over}


def _hygiene(**counts) -> dict:
    return {"hygiene_result": "completed", "hygiene_healthy": 2, **counts}


QUICK = {"tier": "Quick", "previous_tier": "Quick", "tools": _probes(ast=NO_AST, gh=NO_GH),
         "previous_tools": {"ast_grep": False, "gh_cli": False, "qmd": False, "ccc": False}}
DEEP = {"tier": "Deep", "previous_tier": "Deep", "tools": _probes(qmd=QMD), "qmd_status": "healthy",
        "previous_tools": {"ast_grep": True, "gh_cli": True, "qmd": True, "ccc": False}}
GAINED_GH = {"previous_tools": {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": False}}
LOST_GH = {"tools": _probes(gh=NO_GH)}


def _below(tool: str, name: str, version: str, minimum: str, upgrade: str, tier=None) -> dict:
    """One entry of skf-detect-tools.py's tools_below_minimum."""
    return {"tool": tool, "name": name, "version": version, "minimum": minimum, "upgrade": upgrade, "tier": tier}


AST_BELOW = _below("ast_grep", "ast-grep", "0.42.2", "0.45.3", "npm install -g @ast-grep/cli@latest", "Forge")
# A tier tool below its minimum is installed, and reads unavailable, as the detector reports it.
QUICK_OLD_AST = {**QUICK, "tools": _probes(ast={"available": False, "version": "ast-grep 0.42.2"}, gh=NO_GH),
                 "tools_below_minimum": [AST_BELOW]}
OLD_CCC = {"tools": _probes(ccc={"available": False, "daemon": "healthy", "version": "0.1.0"}),
           "tools_below_minimum": [_below("ccc", "ccc", "0.1.0", "0.2", "uv tool upgrade cocoindex-code", "Forge+")]}
OLD_GH = {"tools": _probes(gh={"available": False, "version": "gh version 2.10.0"}),
          "tools_below_minimum": [_below("gh_cli", "gh", "2.10.0", "2.40",
                                         "Install the latest release from https://cli.github.com", "Deep")]}
OLD_QMD = {"qmd_status": "daemon_stopped",
           "tools_below_minimum": [_below("qmd", "qmd", "1.0.0", "2.0", "bun install -g @tobilu/qmd@latest", "Deep")]}
TIER_MISS = {"require_tier": "Forge+", "require_tier_satisfied": False, "require_tier_failure_missing": ["ccc"]}

# One case per `{if ...}` of the FORGE STATUS template (BANNER_TEMPLATE), in
# the template's order: the condition as the template writes it, the payload
# changes that make it hold, the changes that make it fail, and the line the
# banner shows only when it holds.
BANNER_CASES = [
    ("no tools are available and ast-grep is not below its minimum", QUICK, QUICK_OLD_AST,
     '  (none yet, see "Climb to next tier" below)'),
    ("no tools are available and ast-grep is below its minimum", QUICK_OLD_AST, QUICK,
     '  (none yet, see "Tool upgrades" below)'),
    ("a tool is below its minimum", {"tools_below_minimum": [GIT_BELOW]}, {}, "  Tool upgrades:"),
    ("calculated_tier is not Deep and a hint below holds", {}, QUICK_OLD_AST, "  Climb to next tier:"),
    ("not tools.ast_grep and ast-grep is not below its minimum", QUICK, QUICK_OLD_AST,
     "  - Install ast-grep (https://ast-grep.github.io): unlocks AST-backed code analysis (Forge tier)"),
    ("tools.ast_grep and not tools.ccc and ccc is not below its minimum", {}, OLD_CCC,
     "  - Install cocoindex-code (https://github.com/cocoindex-io/cocoindex-code): adds semantic-guided "
     "precision compilation (Forge+ tier)"),
    ("tools.ast_grep and not tools.gh_cli and gh is not below its minimum", LOST_GH, OLD_GH,
     "  - Install GitHub CLI (https://cli.github.com): required for Deep tier (cross-repository synthesis)"),
    ('tools.ast_grep and not tools.qmd and qmd_status is "absent"', {}, {"qmd_status": "daemon_stopped"},
     "  - Install qmd (https://github.com/tobi/qmd): required for Deep tier (knowledge search)"),
    ('tools.ast_grep and not tools.qmd and qmd_status is "daemon_stopped" and qmd is not below its minimum',
     {"qmd_status": "daemon_stopped"}, OLD_QMD,
     "  - Start the qmd daemon (already installed): run `qmd start` (or your distribution's qmd service "
     "command) to unlock Deep tier (knowledge search)"),
    ('tools.ccc and ccc_daemon is "error"', _ccc(daemon="error"), _ccc(),
     "  - The ccc daemon is reporting errors: run `ccc doctor` to diagnose. CCC index will fail until resolved"),
    ('hygiene_result is "completed"', _hygiene(), {}, "  QMD Registry:"),
    ("hygiene_orphaned_removed > 0", _hygiene(hygiene_orphaned_removed=2), _hygiene(),
     "  2 orphaned collection(s) removed"),
    ("hygiene_orphaned_kept > 0", _hygiene(hygiene_orphaned_kept=3), _hygiene(),
     "  3 orphaned collection(s) kept"),
    ("hygiene_stale_cleaned > 0", _hygiene(hygiene_stale_cleaned=1), _hygiene(),
     "  1 stale QMD registry entry/entries cleaned"),
    ("ccc_registry_stale_cleaned > 0", {"ccc_registry_stale_cleaned": 2}, {"ccc_registry_stale_cleaned": 0},
     "  CCC Registry: 2 stale entry/entries cleaned"),
    ('hygiene_result is "completed" and hygiene_healthy is 0', _hygiene(hygiene_healthy=0), _hygiene(),
     "  QMD Registry: empty. Collections are created automatically when you run /skf-create-skill."),
    ('hygiene_result is "qmd_unavailable"', {"hygiene_result": "qmd_unavailable"}, {},
     "  QMD Registry: skipped (qmd unavailable; if the daemon is stopped, `qmd start` restores it)."),
    ("tools.ccc is true", _ccc(), {}, "  CCC Index:"),
    ('ccc_index_result is "fresh"', _ccc(), _ccc(index="created", count=5),
     "  up to date, semantic discovery ready"),
    ('ccc_index_result is "created"', _ccc(index="created", count=5), _ccc(),
     "  indexed this run, semantic discovery ready"),
    ('ccc_index_result is "skipped" and ccc_index_deferred is false', _ccc(index="skipped"),
     _ccc(index="skipped", ccc_index_deferred=True),
     "  skipped (--ccc-skip-index). Run `/skf-setup` without --ccc-skip-index to build or refresh the "
     "index when you're ready"),
    ('ccc_index_result is "skipped" and ccc_index_deferred is true', _ccc(index="skipped", ccc_index_deferred=True),
     _ccc(index="skipped"),
     "  skipped (--require-tier not met). The next `/skf-setup` run that meets the required tier builds or "
     "refreshes the index"),
    ('ccc_index_result is "failed"', _ccc(index="failed", ccc_indexing_failed_reason="daemon down"), _ccc(),
     "  indexing failed, semantic discovery unavailable this session (daemon down)"),
    ("ccc_exclusion_warnings is non-empty", _ccc(ccc_exclusion_warnings=["a note"]), _ccc(),
     "  CCC exclusion notes:"),
    ("settings_yml_written is true", {"settings_yml_written": True, "settings_yml_patterns_added": 3}, {},
     "  - .cocoindex_code/settings.yml: /p/.cocoindex_code/settings.yml (3 SKF exclusion pattern(s) merged)"),
    ("settings_yml_patterns_removed > 0",
     {"settings_yml_written": True, "settings_yml_patterns_added": 3, "settings_yml_patterns_removed": 2},
     {"settings_yml_written": True, "settings_yml_patterns_added": 3},
     "  - .cocoindex_code/settings.yml: /p/.cocoindex_code/settings.yml (3 SKF exclusion pattern(s) merged, "
     "2 stale SKF pattern(s) removed)"),
    ("gitignore_updated is true", {"gitignore_updated": True}, {},
     "  - .gitignore: /p/.gitignore (`/.cocoindex_code/` added by `ccc init`)"),
    ('ccc_index_result is "created"', _ccc(index="created", count=42), _ccc(),
     "  - .cocoindex_code/ ccc index: 42 files indexed"),
    ("tier_override is active", {"tier_override_active": True}, {},
     "  Note: Tier override active (set in preferences.yaml)"),
    ("tier_override_invalid is true", {"tier_override_invalid": True, "tier_override_invalid_value": "deep"}, {},
     '  Note: tier_override value "deep" in preferences.yaml is not valid.'),
    ("tier_override_invalid_suggestion is non-null",
     {"tier_override_invalid": True, "tier_override_invalid_value": "deep",
      "tier_override_invalid_suggestion": "Deep"},
     {"tier_override_invalid": True, "tier_override_invalid_value": "xyz"},
     '        Did you mean "Deep"?'),
    ("tier_override_unsafe is true",
     {"tier_override_unsafe": True, "tier_override_unsafe_missing": ["gh", "qmd"]}, {},
     "  Warning: tier_override is forcing Forge but the underlying tool prerequisites are not satisfied."),
    ("{previous_tier} is null", {"previous_tier": None, "previous_tools": None}, {},
     "  Initial detection: Forge tier established."),
    ("{tier_changed} is true",
     {"previous_tier": "Quick", "previous_tools": {"ast_grep": False, "gh_cli": True, "qmd": False, "ccc": False}},
     {}, "  " + COPY["upgrade"].replace("{previous}", "Quick").replace("{current}", "Forge")
     .replace("{newly available tool(s)}", "ast-grep")),
    ("{tier_changed} is false and {tools_added} is empty and {tools_removed} is empty and {previous_tier} "
     "is non-null", {}, {"previous_tier": None, "previous_tools": None},
     "  " + COPY["same"].replace("{current}", "Forge")),
    ('settings_yml_written is false and ccc_index_result is "fresh"',
     _ccc(), _ccc(settings_yml_written=True),
     "  Your ccc settings were left untouched, and the ccc index was already current."),
    ('settings_yml_written is false and ccc_index_result is "skipped" and ccc_index_deferred is false',
     _ccc(index="skipped"), _ccc(index="skipped", ccc_index_deferred=True),
     "  Your ccc settings were left untouched; the ccc index was not checked (--ccc-skip-index)."),
    ("{tier_changed} is false and ({tools_added} or {tools_removed} is non-empty) and {previous_tier} "
     "is non-null", GAINED_GH, {}, "  Tier unchanged: Forge."),
    ("{tools_added} non-empty", GAINED_GH, LOST_GH, "  Newly detected: gh."),
    ("ccc was added and tier is Deep", {**DEEP, "tools": _probes(qmd=QMD, ccc=CCC)},
     {**_ccc(), "previous_tools": {"ast_grep": True, "gh_cli": True, "qmd": False, "ccc": False}},
     "  Newly detected: ccc. ccc enhances Deep tier transparently."),
    ("a tool in {tools_removed} is not below its minimum", LOST_GH, OLD_GH,
     "  No longer detected: gh. Re-install to restore those capabilities."),
    ("require_tier_satisfied is false", TIER_MISS, {}, "  REQUIRED TIER NOT MET"),
]


def _case_id(n: int, condition: str) -> str:
    return f"{n:02d}-" + re.sub(r"[^a-z0-9]+", "-", condition.lower()).strip("-")[:48]


@pytest.mark.parametrize("condition,holds,fails,line", BANNER_CASES,
                         ids=[_case_id(n, case[0]) for n, case in enumerate(BANNER_CASES)])
def test_banner_line_shows_exactly_when_its_condition_holds(condition, holds, fails, line):
    assert line in _banner(**holds), condition
    assert line not in _banner(**fails), condition


def _template_lines() -> list[str]:
    """The FORGE STATUS template, one string per line."""
    return BANNER_TEMPLATE.read_text(encoding="utf-8").strip("\n").splitlines()


def _tokens(text: str) -> list[tuple[str, str]]:
    """Split a template line into ("text", ...) and ("token", <inside of a {...}, nested braces kept>)."""
    out, i = [], 0
    while i < len(text):
        if text[i] != "{":
            j = text.find("{", i)
            j = len(text) if j < 0 else j
            out.append(("text", text[i:j]))
            i = j
            continue
        depth, j = 0, i
        while True:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
            if depth == 0:
                break
        out.append(("token", text[i + 1:j - 1]))
        i = j
    return out


def _is_if(line: str) -> bool:
    return line.strip().startswith(("{if ", "{end if}"))


def _template_entries() -> list[tuple[str, str]]:
    """(condition, the template line it shows) for every `{if ...}`, in template order.

    `{if C: T}` shows T in its own line; `{if C:}` alone on a line opens a
    block whose first line other than a rule is what it shows; `{if C:} T`
    and a condition inside a line show that line.
    """
    lines = _template_lines()
    entries = []
    for n, line in enumerate(lines):
        tokens = _tokens(line.strip())
        for kind, value in tokens:
            if kind != "token" or not value.startswith("if "):
                continue
            condition, _, shown = value[3:].partition(":")
            if not shown.strip() and len(tokens) == 1:
                line = next(later for later in lines[n + 1:]
                            if later.strip() and not _is_if(later) and later.strip() != RULE)
            entries.append((condition, line))
    return entries


def _shown(line: str, condition: str) -> str:
    """A regex for what a template line shows when `condition` holds.

    Placeholders match any text, the text of any other condition in the
    line is optional, and a space matches any run of spaces.
    """
    out, opened = [], []
    for kind, value in _tokens(re.sub(r"\s+", " ", line)):
        if kind == "text":
            out.append(re.escape(value).replace("\\ ", "\\s*"))
        elif value == "end if":
            out.append(")" if opened.pop() else ")?")
        elif value.startswith("if "):
            cond, _, text = value[3:].partition(":")
            text = text.strip()
            if not text:
                out.append("(?:")
                opened.append(cond == condition)
                continue
            if len(text) > 1 and text[0] == text[-1] == '"':
                text = text[1:-1]
            out.append(f"(?:{_shown(text, condition)})" + ("" if cond == condition else "?"))
        else:
            out.append(".+?")
    out += [")" if required else ")?" for required in reversed(opened)]
    return "".join(out)


def test_every_template_condition_has_its_case_in_template_order():
    """The template is what render-report prints: 42 conditions, a case for each."""
    entries = _template_entries()
    assert len(entries) == 42
    assert [condition for condition, _ in entries] == [case[0] for case in BANNER_CASES]
    assert "{headless_mode}" not in "\n".join(_template_lines())


def test_each_case_line_is_the_template_line_of_its_condition():
    """A wording change on either side, in report.md or in the script, fails here or above."""
    for (condition, line), case in zip(_template_entries(), BANNER_CASES):
        expected = " ".join(case[3].split())
        assert re.fullmatch(_shown(line, condition), expected), (condition, line, expected)


def _wild(text: str) -> str:
    return ".+?".join(re.escape(part) for part in re.split(r"\{[^{}]*\}", text))


def _copy_pattern(message: str, cut: str | None = None) -> str:
    """A tier-rules.md message with its placeholders as any text; past `cut` it may stop."""
    head, sep, tail = message.partition(cut) if cut else (message, "", "")
    return _wild(head + sep) + (f"(?:{_wild(tail)})?" if sep else "")


# What a descriptive template token stands for.
DESCRIBED = {
    "tier capability description from tier-rules.md":
        "(?:" + "|".join(re.escape(COPY[tier]) for tier in mod.VALID_TIERS) + ")",
    "appropriate upgrade/downgrade message from tier-rules.md, naming no tool below its minimum":
        "(?:" + "|".join(_copy_pattern(COPY[key], "{current}.") for key in ("upgrade", "downgrade")) + ")",
    "same-tier message from tier-rules.md": _copy_pattern(COPY["same"]),
}
# The more specific prefix first: the first one a `{for each ...}` line starts with wins.
FOR_EACH = {"for each tool below its minimum": r"- Upgrade \S+ \S+ to \S+ or newer(?: \(.+?\))?(?: to use the \S+ tier)?",
            "for each tool ": r"- (?:ast-grep|gh|qmd|ccc)(?: .+)?", "for each entry ": r"- .+"}


def _template_text(text: str) -> str:
    """A regex for a template line's text: a placeholder is any text, and an
    inline `{if C: T}` or `{if C:}...{end if}` may be left out."""
    parts, opened = [], []
    for kind, value in _tokens(text):
        if kind == "text":
            parts.append(re.escape(value))
        elif value == "end if":
            start = opened.pop()
            parts[start:] = ["(?:" + "".join(parts[start:]) + ")?"]
        elif value.startswith("if ") and value.endswith(":"):
            opened.append(len(parts))
        elif value.startswith("if "):
            shown = value[3:].partition(":")[2].strip()
            if len(shown) > 1 and shown[0] == shown[-1] == '"':
                shown = shown[1:-1]
            parts.append(f"(?:{_template_text(shown)})?")
        else:
            parts.append(DESCRIBED.get(value, ".+?"))
    assert not opened, text
    return "".join(parts)


def _template_pattern() -> tuple[str, list[str]]:
    """The whole template as one regex over a banner's non-blank lines (runs
    of spaces collapsed), and the regex of each line it can print.

    A `{if C:}` line opens a block that may be left out: an indented one runs
    to its `{end if}`, one at the left margin to the end of its paragraph. A
    line led by `{if C: T}` or `{if C:} T` may be left out, and a
    `{for each ...}` line repeats.
    """
    whole, lines, depth, paragraph = [], [], 0, False
    for raw in [*_template_lines(), ""]:
        line = " ".join(raw.split())
        tokens = _tokens(line)
        kind, value = tokens[0] if tokens else ("text", "")
        if not line:
            if paragraph:
                whole.append(")?")
                paragraph = False
        elif kind == "token" and value == "end if":
            depth -= 1
            whole.append(")?")
        elif kind == "token" and value.startswith("if ") and value.endswith(":") and len(tokens) == 1:
            if raw.startswith("{"):
                paragraph = True
            else:
                depth += 1
            whole.append("(?:")
        else:
            each = next((p for prefix, p in FOR_EACH.items() if kind == "token" and value.startswith(prefix)), None)
            if each:
                body, repeat = each, "*"
            elif kind == "token" and value.startswith("if "):
                assert value.endswith(":") or len(tokens) == 1, line
                shown = line[len(value) + 2:] if value.endswith(":") else value[3:].partition(":")[2]
                body, repeat = _template_text(shown.strip()), "?"
            else:
                body, repeat = _template_text(line), ""
            lines.append(body)
            whole.append(f"(?:{body}\n){repeat}")
    assert depth == 0 and not paragraph
    return "".join(whole), lines


def _banners() -> list[list[str]]:
    """The banner for each payload a case makes its condition hold or fail with, and a first Deep run."""
    first_deep = dict(tier="Deep", previous_tier=None, previous_tools=None, qmd_status="healthy",
                      tools=_probes(qmd=QMD, ccc=CCC), settings_yml_written=True,
                      ccc_index={"status": "created", "indexed_path": "/p", "file_count": 1},
                      settings_yml_patterns_added=6, gitignore_updated=True, hygiene_result="completed",
                      hygiene_healthy=0, hygiene_orphaned_kept=23)
    return [_banner(**over) for case in BANNER_CASES for over in case[1:3]] + [_banner(**first_deep)]


def test_every_banner_line_is_a_template_line_in_template_order():
    """Unconditional and continuation lines too: a wording change in any line
    of the template, or in any line the script prints, fails here."""
    whole, lines = _template_pattern()
    shown = []
    for banner in _banners():
        text = "".join(" ".join(line.split()) + "\n" for line in banner if line.strip())
        assert re.fullmatch(whole, text), text
        shown += text.splitlines()
    for line in lines:
        assert any(re.fullmatch(line, printed) for printed in shown), f"no banner prints {line!r}"


def test_a_first_deep_run_renders_the_whole_banner():
    lines = _banner(tier="Deep", previous_tier=None, previous_tools=None, qmd_status="healthy",
                    tools=_probes(qmd=QMD, ccc=CCC),
                    ccc_index={"status": "created", "indexed_path": "/p", "file_count": 1},
                    settings_yml_written=True, settings_yml_patterns_added=6,
                    gitignore_updated=True, hygiene_result="completed", hygiene_healthy=0,
                    hygiene_orphaned_kept=23)
    assert lines == [
        RULE, "  FORGE STATUS", RULE, "",
        "  Tier:  Deep", f"  {COPY['Deep']}", "",
        "  Tools Detected:", "  - ast-grep 0.45.3", "  - gh 2.91.0 (2026-04-22)", "  - qmd 2.8.3 (facd35e)",
        "  - ccc (daemon healthy)", "",
        "  QMD Registry:", "  0 collection(s) healthy", "  23 orphaned collection(s) kept", "",
        "  QMD Registry: empty. Collections are created automatically when you run /skf-create-skill.", "",
        "  CCC Index:", "  indexed this run, semantic discovery ready", "",
        "  Files written this run:",
        "  - forge-tier.yaml: /p/_bmad/_memory/forger-sidecar/forge-tier.yaml",
        "  - /p/forge-data/ (directory ensured)",
        "  - .cocoindex_code/settings.yml: /p/.cocoindex_code/settings.yml (6 SKF exclusion pattern(s) merged)",
        "  - .gitignore: /p/.gitignore (`/.cocoindex_code/` added by `ccc init`)",
        "  - .cocoindex_code/ ccc index: 1 files indexed", "",
        "  Initial detection: Deep tier established.", "",
        RULE, "  Forge ready. Deep tier active.", RULE, "",
        mod.NEXT_STEPS,
    ]


@pytest.mark.parametrize("key,probe,daemon,line", [
    ("ast_grep", AST, None, "  - ast-grep 0.45.3"),
    ("gh_cli", GH, None, "  - gh 2.91.0 (2026-04-22)"),
    ("qmd", {"available": True, "version": "2.0.1"}, None, "  - qmd 2.0.1"),
    ("qmd", {"available": True, "version": None}, None, "  - qmd"),
    ("gh_cli", True, None, "  - gh"),
    ("ccc", {"available": True, "daemon": "error"}, "error", "  - ccc (daemon error)"),
    ("ccc", {"available": True, "daemon": "healthy", "version": "0.2.41"}, "healthy", "  - ccc 0.2.41 (daemon healthy)"),
    ("ccc", True, None, "  - ccc"),
], ids=["ast-grep", "gh-version-word", "bare-version", "no-version", "bool-shape", "ccc-daemon", "ccc-uv-version",
        "ccc-bool"])
def test_tools_detected_lines(key, probe, daemon, line):
    assert mod._tool_line(key, probe, daemon) == line


def test_a_tier_change_names_the_tools_that_changed_or_stops_after_one_sentence():
    lost_ccc = _banner(previous_tier="Forge+",
                       previous_tools={"ast_grep": True, "gh_cli": True, "qmd": False, "ccc": True})
    assert "  " + COPY["downgrade"].replace("{previous}", "Forge+").replace("{current}", "Forge").replace(
        "{tool}", "ccc") in lost_ccc
    # A tier_override moved the tier, so no tool changed and there is none to name.
    assert "  Tier changed from Deep to Forge." in _banner(previous_tier="Deep", tier_override_active=True)
    assert "  Tier upgraded from Quick to Forge." in _banner(previous_tier="Quick", tier_override_active=True)


# ─── skf-setup: tools below their minimum version ───────────────────────────


def test_each_tool_below_its_minimum_is_a_warning_and_no_envelope_field_changes():
    p = _baseline_payload()
    p["tools_below_minimum"] = [AST_BELOW, GIT_BELOW]
    env = mod.assemble_envelope(p)
    assert env["skf_setup"]["warnings"] == ["tool_below_minimum: ast-grep 0.42.2 (minimum 0.45.3)",
                                            "tool_below_minimum: git 2.10.0 (minimum 2.15)"]
    assert mod._validate_against_schema(env, _schema()) == []
    assert set(env["skf_setup"]) == set(_schema()["properties"]["skf_setup"]["properties"])


def test_a_tier_tool_below_its_minimum_reads_false_in_the_envelope(tmp_path):
    """The detector reports it unavailable, so it counts toward no tier and the
    envelope's tools say false, as they do for a stopped qmd."""
    detect = _detect_output()
    detect["tools"]["ast_grep"] = {"available": False, "version": "ast-grep 0.42.2", "minimum": "0.45.3",
                                   "meets_minimum": False, "below_minimum": True}
    detect["tools_below_minimum"] = [AST_BELOW, GIT_BELOW]
    detect["tier"].update(calculated="Quick", detected="Quick")
    detect["require_tier"] = {"requested": "Forge", "satisfied": False, "missing_tools": ["ast-grep"]}
    run_dir = _stage(tmp_path / "skf-setup-RUN", detect=detect)
    proc = _cli_in(["emit", "--run-dir", str(run_dir)], (run_dir / "report-context.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0, proc.stderr
    env = _envelope_of(proc.stdout)
    assert mod._validate_against_schema(env, _schema()) == []
    env = env["skf_setup"]
    assert env["status"] == "tier_failure" and env["tier"] == "Quick" and env["tools"]["ast_grep"] is False
    # The tool no longer counts, so a re-run lists it as removed; the banner, not the envelope, says why.
    assert env["tools_removed"] == ["ast_grep"]
    assert env["warnings"][-3:] == ["tool_below_minimum: ast-grep 0.42.2 (minimum 0.45.3)",
                                    "tool_below_minimum: git 2.10.0 (minimum 2.15)",
                                    "require_tier_failed: missing ast-grep"]


@pytest.mark.parametrize("tool,line", [
    (AST_BELOW, "  - Upgrade ast-grep 0.42.2 to 0.45.3 or newer (npm install -g @ast-grep/cli@latest) "
                "to use the Forge tier"),
    (GIT_BELOW, "  - Upgrade git 2.10.0 to 2.15 or newer "
                "(Install the latest release from https://git-scm.com/downloads)"),
    ({**GIT_BELOW, "upgrade": None}, "  - Upgrade git 2.10.0 to 2.15 or newer"),
], ids=["tier-tool", "warn-only", "no-upgrade-text"])
def test_tool_upgrade_lines(tool, line):
    lines = _banner(tools_below_minimum=[tool])
    assert lines[lines.index("  Tool upgrades:") + 1] == line


def test_the_upgrade_block_shows_at_every_tier_even_deep():
    """Climb to next tier renders only below Deep, and a ccc on Deep still needs its line."""
    old_ccc = _below("ccc", "ccc", "0.1.0", "0.2", "uv tool upgrade cocoindex-code", "Forge+")
    lines = _banner(**DEEP, tools_below_minimum=[old_ccc])
    assert "  Climb to next tier:" not in lines
    assert "  - Upgrade ccc 0.1.0 to 0.2 or newer (uv tool upgrade cocoindex-code) to use the Forge+ tier" in lines
    assert lines.index("  Tools Detected:") < lines.index("  Tool upgrades:")


def test_a_tool_that_dropped_below_its_minimum_is_not_called_no_longer_detected():
    # Forge to Quick: ast-grep still answers, but below its minimum it counts toward no tier.
    downgraded = _banner(**{**QUICK_OLD_AST, "previous_tier": "Forge",
                            "previous_tools": {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": False}})
    assert "  Tier changed from Forge to Quick." in downgraded
    assert not any("no longer detected" in line.lower() for line in downgraded)
    assert '  (none yet, see "Tool upgrades" below)' in downgraded
    assert not any(line.startswith("  - Install ast-grep") for line in downgraded)
    # Same tier: the delta block keeps its first line and names no tool.
    same = _banner(**OLD_GH)
    assert "  Tier unchanged: Forge." in same
    assert not any("No longer detected" in line for line in same)
    assert "  - Upgrade gh 2.10.0 to 2.40 or newer (Install the latest release from https://cli.github.com) " \
           "to use the Deep tier" in same
    # A tool that is really gone is still named next to one below its minimum.
    both = _banner(tools=_probes(ast={"available": False, "version": "ast-grep 0.42.2"}, gh=NO_GH),
                   tools_below_minimum=[AST_BELOW], tier="Quick")
    assert "  Tier changed from Forge to Quick. gh no longer detected. Run the tool's installation to restore " \
           "capabilities." in both


def test_the_required_tier_block_ends_the_banner():
    lines = _banner(**{**DEEP, **TIER_MISS, "require_tier_failure_missing": ["ast-grep", "ccc"]})
    assert lines[-10:] == [
        RULE, "  REQUIRED TIER NOT MET", RULE, "",
        "  Required:  Forge+", "  Detected:  Deep", "  Missing:   ast-grep, ccc", "",
        "  Install or upgrade the missing tool(s) and re-run, or relax `--require-tier`.", RULE,
    ]
    assert lines[-12] == mod.NEXT_STEPS
    # Deep can miss Forge+ (Deep does not need ccc): the block points at no Climb section.
    assert "  Climb to next tier:" not in lines
    assert "  REQUIRED TIER NOT MET" not in _banner(**DEEP)


def test_the_required_tier_comes_from_the_staged_detector_output(tmp_path):
    run_dir = _stage(tmp_path / "skf-setup-RUN", detect=_detect_output())
    proc = _cli_in(["render-report", "--run-dir", str(run_dir), "--tier-rules", str(TIER_RULES)],
                   (run_dir / "report-context.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    for line in ("  Tool upgrades:", "  Required:  Forge+", "  Detected:  Forge", "  Missing:   ccc"):
        assert line in lines, line


def _placeholder_refusal() -> str:
    """The refusal skf-merge-ccc-exclusions.py itself writes for a value that holds a placeholder."""
    spec = importlib.util.spec_from_file_location("skf_merge_ccc_exclusions", MERGE_HELPER)
    merge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge)
    kept, refusal = merge.validate_config_value("skills_output_folder", "{output_folder}/skills")
    assert kept is None and refusal
    return refusal


def test_exclusion_notes_resolve_every_project_root_placeholder():
    # The helper's own refusal names the placeholder in words, so every
    # `{project-root}` a note holds is the project root, which the banner shows.
    refusal = _placeholder_refusal()
    assert "{project-root}" not in refusal and "project-root placeholder" in refusal
    lines = _banner(**_ccc(ccc_exclusion_warnings=["add /.cocoindex_code/ to {project-root}/.gitignore",
                                                   refusal, "ccc init failed in /elsewhere"]))
    assert "  - add /.cocoindex_code/ to /p/.gitignore" in lines
    assert f"  - {refusal}" in lines
    assert "  - ccc init failed in /elsewhere" in lines
    assert not hasattr(mod, "PLACEHOLDER_REFUSAL")


def test_a_failure_reason_on_several_lines_stays_on_its_banner_line():
    lines = _banner(**_ccc(index="failed", ccc_indexing_failed_reason="ccc index failed:\n  daemon down\n"))
    assert "  indexing failed, semantic discovery unavailable this session (ccc index failed: daemon down)" in lines


def test_the_banner_takes_the_hygiene_counts_from_the_staged_outputs():
    payload = mod.fold_staged(_banner_payload(hygiene_result="skipped"),
                              {mod.STAGED_CLASSIFY: CLASSIFIED,
                               mod.STAGED_CLEAN_STALE: {"qmd_removed": ["x-docs"], "ccc_removed": ["/gone"]}})
    lines = mod.render_report(payload, COPY)
    for line in ("  QMD Registry:", "  1 collection(s) healthy", "  1 stale QMD registry entry/entries cleaned",
                 "  CCC Registry: 1 stale entry/entries cleaned"):
        assert line in lines, line


def test_tier_rules_copy_is_read_from_its_file():
    assert set(COPY) == {"Quick", "Forge", "Forge+", "Deep", "upgrade", "downgrade", "same"}
    assert COPY["Quick"].startswith("Quick tier active.") and not COPY["Quick"].endswith('"')
    assert "{previous}" in COPY["upgrade"] and "{current}" in COPY["same"]
    assert mod.TIER_RULES_FILE.resolve() == TIER_RULES.resolve()


def test_tier_rules_without_one_of_its_headings_is_a_user_error(tmp_path, capsys):
    broken = tmp_path / "tier-rules.md"
    broken.write_text(TIER_RULES.read_text(encoding="utf-8").replace("### Same", "### Unchanged"),
                      encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        mod.load_tier_rules(broken)
    assert exc.value.code == 1 and "Same" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        mod.load_tier_rules(tmp_path / "missing.md")
    assert exc.value.code == 1


def test_cli_render_report_reads_the_run_folder(tmp_path):
    run_dir = _stage(tmp_path / "skf-setup-RUN", detect=_detect_output(), classify=CLASSIFIED,
                     clean_stale={"qmd_removed": ["x-docs"], "ccc_removed": [], "wrote": True})
    proc = _cli_in(["render-report", "--run-dir", str(run_dir), "--tier-rules", str(TIER_RULES)],
                   (run_dir / "report-context.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    for line in ("  - gh 2.91.0 (2026-04-22)", '        Did you mean "Deep"?', "  1 collection(s) healthy",
                 "  1 stale QMD registry entry/entries cleaned", "  Newly detected: gh."):
        assert line in lines, line
    # The detector output misses --require-tier=Forge+, so the tier-miss block ends the banner.
    assert lines[0] == RULE and lines[-1] == RULE and lines[-9] == "  REQUIRED TIER NOT MET"
    assert mod.NEXT_STEPS in lines


def test_cli_render_report_finds_the_tier_copy_in_an_installed_project(tmp_path):
    """Installed under _bmad/skf/, with skf-setup/ beside shared/."""
    import shutil
    scripts = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
    shutil.copytree(SCHEMA_PATH.parent, scripts / "schemas")
    shutil.copy2(SCRIPT_PATH, scripts / SCRIPT_PATH.name)
    references = tmp_path / "_bmad" / "skf" / "skf-setup" / "references"
    references.mkdir(parents=True)
    shutil.copy2(TIER_RULES, references / TIER_RULES.name)
    proc = subprocess.run([sys.executable, str(scripts / SCRIPT_PATH.name), "render-report"],
                          input=json.dumps(_banner_payload()), capture_output=True, text=True,
                          encoding="utf-8", timeout=10, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert f"  {COPY['Forge']}" in proc.stdout.splitlines()


@pytest.mark.parametrize("args,payload,needle", [
    (["--tier-rules", "does-not-exist.md"], _banner_payload(), "tier copy"),
    ([], _banner_payload(tier="Sparkle"), "tier must be one of"),
], ids=["missing-tier-copy", "bad-tier"])
def test_cli_render_report_refuses_what_it_cannot_render(tmp_path, args, payload, needle):
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "render-report", *args],
                          input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
                          timeout=10, cwd=tmp_path)
    assert proc.returncode == 1 and proc.stdout == ""
    assert needle in json.loads(proc.stderr)["message"]


# ─── emit-blocked: the payload from options, the reason from stderr ──────────


def _blocked(*args: str, stdin: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT_PATH), "emit-blocked", *args], input=stdin,
                          capture_output=True, timeout=10)


def _blocked_envelope(done: subprocess.CompletedProcess) -> dict:
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    env = _envelope_of(done.stdout.decode("utf-8"))
    assert mod._validate_against_schema(env, _schema()) == []
    return env["skf_setup"]


# A failed helper's stderr, as `2>` saved it: uv's own lines may come first.
STDERR_CASES = [
    (b'{"status": "error", "message": "Permission denied: /p/forge-tier.yaml"}\n',
     "Permission denied: /p/forge-tier.yaml"),
    (b'Installed 1 package in 3ms\n{"status":"error","message":"two\\nlines   and \\"quotes\\""}\n',
     'two lines and "quotes"'),
    (b'{\n  "status": "error",\n  "message": "pretty printed"\n}\n', "pretty printed"),
    (b"\nmkdir: cannot create directory: Read-only file system\nsecond line\n",
     "mkdir: cannot create directory: Read-only file system"),
    (b'{"status": "error"}\nTraceback (most recent call last):\n', '{"status": "error"}'),
    (b"", mod.NO_STDERR_MESSAGE),
    (b"\xef\xbb\xbf\xff bad byte\n", "\ufffd bad byte"),
]


@pytest.mark.parametrize("raw,message", STDERR_CASES,
                         ids=["json", "uv-lines-first", "pretty-json", "first-line", "json-without-message",
                              "empty", "bom-and-bad-byte"])
def test_stderr_from_takes_the_message_on_one_line(tmp_path, raw, message):
    err = tmp_path / "write-tools.err"
    err.write_bytes(raw)
    env = _blocked_envelope(_blocked("--phase", "step 2:write-tools", "--path", "/p/forge-tier.yaml",
                                     "--reason", "Setup cannot proceed: <message>", "--stderr-from", str(err)))
    assert env["error"] == {"phase": "step 2:write-tools", "path": "/p/forge-tier.yaml",
                            "reason": f"Setup cannot proceed: {message}"}
    assert env["config_path"] == "/p/forge-tier.yaml" and env["status"] == "blocked"


def test_stderr_from_dash_reads_the_pipe():
    env = _blocked_envelope(_blocked("--phase", "step 1:run-folder", "--reason",
                                     "Setup cannot proceed: the run folder could not be created: <message>",
                                     "--stderr-from", "-", stdin=b"mkdir: /p/_bmad-output: Not a directory\n"))
    assert env["error"] == {"phase": "step 1:run-folder", "path": "<n/a>",
                            "reason": "Setup cannot proceed: the run folder could not be created: "
                                      "mkdir: /p/_bmad-output: Not a directory"}


def test_a_stderr_file_that_is_gone_reads_as_no_message(tmp_path):
    env = _blocked_envelope(_blocked("--phase", "step 1:detect-tools", "--reason", "failed: <message>",
                                     "--stderr-from", str(tmp_path / "missing.err")))
    assert env["error"]["reason"] == f"failed: {mod.NO_STDERR_MESSAGE}"


def test_options_and_a_typed_payload_build_the_same_envelope():
    """The On Activation halts still pipe JSON until they switch to the options."""
    payload = {"phase": "step 3:helper-missing", "reason": "Setup cannot proceed: x was not found.",
               "path": "/p/_bmad/skf/shared/scripts/x.py"}
    typed = _blocked_envelope(_blocked(stdin=json.dumps(payload).encode("utf-8")))
    options = _blocked_envelope(_blocked("--phase", payload["phase"], "--reason", payload["reason"],
                                         "--path", payload["path"]))
    assert typed == options


@pytest.mark.parametrize("args,needle", [
    (("--reason", "r"), "need --phase"),
    (("--stderr-from", "-"), "need --phase"),
    (("--customization-resolver-unavailable", "r"), "need --phase"),
    (("--phase", "p"), "must be non-empty"),
    (("--phase", "p", "--reason", "no placeholder", "--stderr-from", "-"), "<message>"),
    (("--phase", "p", "--reason", "x <message>"), "needs --stderr-from"),
], ids=["reason-alone", "stderr-alone", "resolver-alone", "no-reason", "no-placeholder", "placeholder-unfilled"])
def test_emit_blocked_refuses_options_it_cannot_use(args, needle):
    done = _blocked(*args)
    assert done.returncode == 1 and done.stdout == b""
    assert needle in json.loads(done.stderr)["message"]


@pytest.mark.parametrize("value,warning", [
    ('resolve_customization.py: "tomllib"\n  missing', 'customization_resolver_unavailable: resolve_customization.py: '
                                                       '"tomllib" missing'),
    ("  ", None),
], ids=["reason", "blank"])
def test_a_halt_after_the_resolver_carries_its_warning(value, warning):
    """A halt after On Activation's resolver failed still says the overrides were not applied."""
    env = _blocked_envelope(_blocked("--phase", "step 2:write-tools", "--reason", "Setup cannot proceed: x",
                                     "--customization-resolver-unavailable", value))
    assert env["warnings"] == ([warning] if warning else [])
    piped = {"phase": "step 2:write-tools", "reason": "Setup cannot proceed: x",
             "customization_resolver_unavailable": " ".join(value.split()) or None}
    assert _blocked_envelope(_blocked(stdin=json.dumps(piped).encode("utf-8")))["warnings"] == env["warnings"]


def test_stderr_message_is_documented():
    doc = mod.__doc__
    for token in ("--phase, --reason and --path", "--stderr-from", "`<message>`", "`(no error message)`",
                  "with no --stderr-from is refused", "--customization-resolver-unavailable"):
        assert token in doc, token
    assert mod.STDERR_MESSAGE == "<message>" and mod.NO_STDERR_MESSAGE == "(no error message)"


# ─── emit and render-report: the run's paths from the project ───────────────


PREFLIGHT_PATH = ROOT / "src" / "shared" / "scripts" / "skf-preflight.py"


def _project(tmp_path: Path, config: bytes) -> Path:
    project = tmp_path / "project"
    (project / "_bmad" / "skf").mkdir(parents=True)
    (project / "_bmad" / "skf" / "config.yaml").write_bytes(config)
    return project


def _preflight_config(project: Path) -> dict:
    """The `config` skf-preflight.py prints, whose folders setup's On Activation binds."""
    pytest.importorskip("yaml")
    spec_pf = importlib.util.spec_from_file_location("skf_preflight_paths", PREFLIGHT_PATH)
    preflight = importlib.util.module_from_spec(spec_pf)
    spec_pf.loader.exec_module(preflight)
    return preflight.run_preflight(str(project), allow_missing_sidecar=True)["config"]


def _path_options(project: Path) -> list[str]:
    """The path options report.md passes, filled in with what activation bound."""
    config = _preflight_config(project)
    return ["--project-root", str(project), "--sidecar-path", config["sidecar_path_resolved"],
            "--forge-data-folder", config["forge_data_folder_resolved"]]


# config.yaml as the two installers and a hand edit write it, the YAML shapes a
# second reader of the file would get wrong among them.
CONFIGS = [
    (b"# SKF Configuration - Generated by installer\nuser_name: Ada\nforge_data_folder: forge-data\n"
     b"sidecar_path: _bmad/_memory/forger-sidecar\nides:\n  - claude-code\n", "standalone-installer"),
    (b"forge_data_folder: '{project-root}/forge-data'\nsidecar_path: '{project-root}/_bmad/_memory/forger-sidecar'\n",
     "bmad-method-quoted"),
    (b'forge_data_folder: "{project-root}/data/forge"  # moved\nsidecar_path: "_bmad/_memory/forger-sidecar"\n',
     "double-quoted-with-comment"),
    (b"forge_data_folder: '{project-root}/{output_folder}/forge'\nsidecar_path: _bmad/_memory/forger-sidecar\n",
     "placeholder-left-in-forge-data"),
    (b"forge_data_folder: # set me\nsidecar_path: _bmad/_memory/forger-sidecar\n", "comment-only-forge-data"),
    (b"forge_data_folder: forge-data\nsidecar_path: >-\n  _bmad/_memory/forger-sidecar\n", "block-scalar-sidecar"),
]


@pytest.mark.parametrize("config", [c for c, _ in CONFIGS], ids=[i for _, i in CONFIGS])
def test_the_paths_are_the_folders_preflight_resolved(tmp_path, config):
    """The emitter reads no config.yaml: config_path is the forge-tier.yaml in the
    sidecar folder activation bound from skf-preflight.py, and forge_data_folder
    that folder too, whatever YAML shape the config uses."""
    project = _project(tmp_path, config)
    expected = _preflight_config(project)
    paths = mod.setup_paths(*_path_options(project)[1::2])
    assert paths["project_root"] == Path(expected["project_root"]).as_posix()
    assert paths["config_path"] == (Path(expected["sidecar_path_resolved"]) / "forge-tier.yaml").as_posix()
    if expected["forge_data_folder_resolved"]:
        assert paths["forge_data_folder"] == Path(expected["forge_data_folder_resolved"]).as_posix()
    else:
        assert "forge_data_folder" not in paths


def test_setup_paths_join_a_relative_folder_to_the_project_root(tmp_path):
    root = tmp_path.resolve()
    paths = mod.setup_paths(str(tmp_path), "_bmad/_memory/forger-sidecar", "forge-data")
    assert paths == {"project_root": root.as_posix(),
                     "config_path": (root / "_bmad" / "_memory" / "forger-sidecar" / "forge-tier.yaml").as_posix(),
                     "forge_data_folder": (root / "forge-data").as_posix()}
    assert mod.setup_paths(str(tmp_path), None, None) == {"project_root": root.as_posix()}


@pytest.mark.parametrize("args", [(None, "/p/sidecar", None), (None, None, "/p/forge-data"), ("/p", " ", None)],
                         ids=["sidecar-without-root", "forge-data-without-root", "empty-sidecar"])
def test_setup_paths_refuse_what_they_cannot_place(args):
    with pytest.raises(SystemExit) as exc:
        mod.setup_paths(*args)
    assert exc.value.code == 1
    assert mod.setup_paths(None, None, None) == {}


def test_emit_and_render_report_derive_the_paths_the_payload_no_longer_carries(tmp_path):
    """determinism-2: report.md stages no path, so no escaping rule and no repair retry."""
    project = _project(tmp_path, CONFIGS[1][0])
    run_dir = _stage(project / "_bmad-output" / ".skf-run" / "skf-setup-RUN", detect=_detect_output())
    payload = json.dumps({"orphan_auto_resolution": None, "customization_resolver_unavailable": None,
                          "error": None})
    paths = _path_options(project)
    root = project.resolve().as_posix()
    done = _cli_in(["emit", "--run-dir", str(run_dir), *paths], payload)
    assert done.returncode == 0, done.stderr
    env = _envelope_of(done.stdout)["skf_setup"]
    assert env["config_path"] == f"{root}/_bmad/_memory/forger-sidecar/forge-tier.yaml"
    assert env["status"] == "tier_failure" and "require_tier_failed: missing ccc" in env["warnings"]
    banner = _cli_in(["render-report", "--run-dir", str(run_dir), *paths], payload)
    assert banner.returncode == 0, banner.stderr
    lines = banner.stdout.splitlines()
    assert f"  - forge-tier.yaml: {root}/_bmad/_memory/forger-sidecar/forge-tier.yaml" in lines
    assert f"  - {root}/forge-data/ (directory ensured)" in lines
    # Without the options the payload must carry config_path itself, as before.
    bare = _cli_in(["emit", "--run-dir", str(run_dir)], payload)
    assert bare.returncode == 1 and "config_path" in json.loads(bare.stderr)["message"]


def test_a_resolver_reason_in_the_report_payload_becomes_its_warning(tmp_path):
    project = _project(tmp_path, CONFIGS[0][0])
    run_dir = _stage(project / "run" / "skf-setup-RUN", detect=_detect_output())
    payload = json.dumps({"orphan_auto_resolution": None,
                          "customization_resolver_unavailable": 'resolve_customization.py: "tomllib" missing',
                          "error": None})
    done = _cli_in(["emit", "--run-dir", str(run_dir), *_path_options(project)], payload)
    assert done.returncode == 0, done.stderr
    warnings = _envelope_of(done.stdout)["skf_setup"]["warnings"]
    assert warnings[0] == 'customization_resolver_unavailable: resolve_customization.py: "tomllib" missing'


@pytest.mark.parametrize("args", [["--workflow", "skf-update-skill"], []], ids=["other-workflow", "sidecar-alone"])
def test_the_path_options_are_setups_alone(tmp_path, args):
    extra = ["--sidecar-path", str(tmp_path / "sidecar")]
    if args:
        extra = ["--project-root", str(tmp_path), *extra]
    done = _cli_in(["emit", *args, *extra], json.dumps(_baseline_payload()))
    assert done.returncode == 1 and done.stdout == ""


# ─── a --require-tier miss defers a due index build ─────────────────────────


def test_a_deferred_index_build_reads_as_skipped_and_says_why(tmp_path):
    """The merge helper's `defer` action: the index status is an existing one
    (`skipped`), and the banner names the tier miss, not --ccc-skip-index."""
    deferred = {**CCC_RESULT, "written": False, "index_action": "defer",
                "index": {"status": "skipped", "indexed_path": None, "last_indexed": None, "file_count": None,
                          "failed_reason": None}}
    folded = mod.fold_staged({}, {mod.STAGED_CCC: deferred})
    assert folded["ccc_index_deferred"] is True
    assert folded["ccc_index"] == {"status": "skipped", "indexed_path": None, "file_count": None}
    assert mod.fold_staged({}, {mod.STAGED_CCC: CCC_RESULT})["ccc_index_deferred"] is False
    lines = mod.render_report(_banner_payload(**_ccc(index="skipped"), **TIER_MISS, ccc_index_deferred=True), COPY)
    assert ("  skipped (--require-tier not met). The next `/skf-setup` run that meets the required tier builds or "
            "refreshes the index") in lines
    assert not any("--ccc-skip-index" in line for line in lines), lines
    detect = _detect_output()
    detect["tools"]["ccc"] = {"available": True, "daemon": "healthy", "version": None}
    run_dir = _stage(tmp_path / "skf-setup-RUN", detect=detect, ccc=deferred)
    done = _cli_in(["emit", "--run-dir", str(run_dir)], json.dumps(REPORT_CONTEXT))
    assert done.returncode == 0, done.stderr
    env = _envelope_of(done.stdout)["skf_setup"]
    assert (env["status"], env["ccc_index"]["status"]) == ("tier_failure", "skipped")
    assert "ccc_index" not in env["files_written"]
