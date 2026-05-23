#!/usr/bin/env python3
"""Tests for skf-forge-tier-rw.py.

Highest-value test: round-trip preservation of `qmd_collections`,
`ccc_index_registry`, and `ccc_index.staleness_threshold_hours` across
a write-tools call. Losing those arrays would silently break every
downstream skill that reads them.
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
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-forge-tier-rw.py"
)

spec = importlib.util.spec_from_file_location("skf_forge_tier_rw", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ─── Fixture payloads ────────────────────────────────────────────────────────


def _baseline_payload() -> dict:
    return {
        "tools": {
            "ast_grep": True,
            "gh_cli": True,
            "qmd": True,
            "ccc": True,
            "ccc_daemon": "healthy",
            "security_scan": False,
        },
        "tier": "Deep",
        "tier_detected_at": "2026-04-27T12:00:00+00:00",
        "ccc_index": {
            "indexed_path": "/repo",
            "last_indexed": "2026-04-27T12:00:00+00:00",
            "status": "fresh",
            "file_count": 1234,
            "exclude_patterns": ["**/_bmad", "**/_bmad-output"],
        },
    }


def _payload_with_arrays() -> dict:
    """Same as baseline but with non-empty registry arrays — used for preservation tests."""
    payload = _baseline_payload()
    payload["qmd_collections"] = [
        {"name": "foo-brief", "type": "brief", "skill_name": "foo", "created_at": "2026-04-25"},
        {"name": "foo-extraction", "type": "extraction", "skill_name": "foo",
         "created_at": "2026-04-25"},
    ]
    payload["ccc_index_registry"] = [
        {"path": "/repo/skills/foo", "indexed_at": "2026-04-25T10:00:00+00:00"},
    ]
    payload["ccc_index"]["staleness_threshold_hours"] = 48  # user-customized
    return payload


# ─── render_forge_tier_yaml ─────────────────────────────────────────────────


def test_render_produces_parseable_yaml():
    payload = _payload_with_arrays()
    rendered = mod.render_forge_tier_yaml(payload)
    parsed = yaml.safe_load(rendered)
    assert parsed["tier"] == "Deep"
    assert parsed["tools"]["ast_grep"] is True
    assert parsed["tools"]["ccc_daemon"] == "healthy"
    assert parsed["ccc_index"]["status"] == "fresh"
    assert parsed["ccc_index"]["staleness_threshold_hours"] == 48
    assert len(parsed["qmd_collections"]) == 2
    assert len(parsed["ccc_index_registry"]) == 1


def test_render_preserves_canonical_section_comments():
    """Header + section comments per step 2 template are preserved."""
    rendered = mod.render_forge_tier_yaml(_baseline_payload())
    assert "# Ferris Sidecar: Forge Tier State" in rendered
    assert "# Tool availability" in rendered
    assert "# Capability tier" in rendered
    assert "# CCC semantic index state" in rendered
    assert "# CCC index registry" in rendered
    assert "PRESERVE existing entries" in rendered
    assert "# QMD collection registry" in rendered


def test_render_section_order_is_canonical():
    """Sections appear in the same order as the step 2 template."""
    rendered = mod.render_forge_tier_yaml(_baseline_payload())
    sections = [
        ("tools:", rendered.find("tools:")),
        ("tier:", rendered.find("\ntier:")),
        ("tier_detected_at:", rendered.find("tier_detected_at:")),
        ("ccc_index:", rendered.find("ccc_index:")),
        ("ccc_index_registry:", rendered.find("ccc_index_registry:")),
        ("qmd_collections:", rendered.find("qmd_collections:")),
    ]
    positions = [pos for _, pos in sections]
    assert all(p > 0 for p in positions), f"missing sections: {sections}"
    assert positions == sorted(positions), f"sections out of canonical order: {sections}"


def test_render_uses_default_staleness_when_unset():
    payload = _baseline_payload()
    payload["ccc_index"].pop("staleness_threshold_hours", None)
    rendered = mod.render_forge_tier_yaml(payload)
    parsed = yaml.safe_load(rendered)
    assert parsed["ccc_index"]["staleness_threshold_hours"] == mod.DEFAULT_STALENESS_HOURS


def test_render_is_deterministic_byte_for_byte():
    """Same input → byte-identical output (no random ordering, no timestamp leakage)."""
    payload = _payload_with_arrays()
    rendered_a = mod.render_forge_tier_yaml(payload)
    rendered_b = mod.render_forge_tier_yaml(payload)
    assert rendered_a == rendered_b


# ─── _merge_preserved_fields (the data-loss surface) ────────────────────────


def test_merge_preserves_existing_qmd_collections():
    new_payload = _baseline_payload()  # no qmd_collections key
    existing = {
        "qmd_collections": [{"name": "x-brief", "type": "brief"}],
        "ccc_index_registry": [],
    }
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["qmd_collections"] == [{"name": "x-brief", "type": "brief"}]


def test_merge_preserves_existing_ccc_index_registry():
    new_payload = _baseline_payload()
    existing = {
        "qmd_collections": [],
        "ccc_index_registry": [{"path": "/old/path", "indexed_at": "2026-04-01T00:00:00+00:00"}],
    }
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["ccc_index_registry"] == [
        {"path": "/old/path", "indexed_at": "2026-04-01T00:00:00+00:00"}
    ]


def test_merge_preserves_user_customized_staleness_threshold():
    new_payload = _baseline_payload()  # no staleness in new
    existing = {"ccc_index": {"staleness_threshold_hours": 72}}
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["ccc_index"]["staleness_threshold_hours"] == 72


def test_merge_uses_default_when_neither_set():
    new_payload = _baseline_payload()
    new_payload["ccc_index"].pop("staleness_threshold_hours", None)
    existing = {"ccc_index": {}}
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["ccc_index"]["staleness_threshold_hours"] == mod.DEFAULT_STALENESS_HOURS


def test_merge_no_existing_file_returns_payload_unchanged():
    new_payload = _baseline_payload()
    merged = mod._merge_preserved_fields(new_payload, None)
    assert merged is new_payload


def test_merge_does_not_preserve_exclude_patterns():
    """exclude_patterns is rewritten fresh every run, NOT preserved."""
    new_payload = _baseline_payload()  # has exclude_patterns: ["**/_bmad", ...]
    existing = {
        "ccc_index": {
            "exclude_patterns": ["**/old-stale-pattern"],
            "staleness_threshold_hours": 24,
        },
    }
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert "**/old-stale-pattern" not in merged["ccc_index"]["exclude_patterns"]
    assert merged["ccc_index"]["exclude_patterns"] == ["**/_bmad", "**/_bmad-output"]


# ─── End-to-end: write-tools subcommand via subprocess ──────────────────────


@pytest.fixture
def tmp_target():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "forge-tier.yaml"


def _write_tools(target: Path, payload: dict) -> dict:
    """Invoke write-tools subcommand via subprocess, return parsed JSON response."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write-tools", "--target", str(target)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return json.loads(result.stdout)


def _read_yaml_file(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_write_tools_creates_file_on_first_run(tmp_target):
    response = _write_tools(tmp_target, _baseline_payload())
    assert response["status"] == "ok"
    assert response["wrote"] == str(tmp_target)
    assert response["preserved_arrays"] == {"qmd_collections": 0, "ccc_index_registry": 0}
    assert tmp_target.exists()
    parsed = _read_yaml_file(tmp_target)
    assert parsed["tier"] == "Deep"


def test_write_tools_preserves_arrays_on_rerun(tmp_target):
    """The headline data-loss test: arrays from existing file survive a fresh write."""
    # First run: write a file WITH arrays.
    initial = _payload_with_arrays()
    _write_tools(tmp_target, initial)
    initial_parsed = _read_yaml_file(tmp_target)
    assert len(initial_parsed["qmd_collections"]) == 2
    assert len(initial_parsed["ccc_index_registry"]) == 1
    assert initial_parsed["ccc_index"]["staleness_threshold_hours"] == 48

    # Second run: write with a payload that does NOT mention the arrays.
    rerun_payload = _baseline_payload()  # no qmd_collections, no ccc_index_registry
    rerun_payload["tools"]["ccc_daemon"] = "stopped"  # something changed
    response = _write_tools(tmp_target, rerun_payload)
    assert response["preserved_arrays"]["qmd_collections"] == 2
    assert response["preserved_arrays"]["ccc_index_registry"] == 1

    # Verify arrays are still there byte-for-byte.
    rerun_parsed = _read_yaml_file(tmp_target)
    assert rerun_parsed["qmd_collections"] == initial_parsed["qmd_collections"]
    assert rerun_parsed["ccc_index_registry"] == initial_parsed["ccc_index_registry"]
    assert rerun_parsed["ccc_index"]["staleness_threshold_hours"] == 48
    # The thing that DID change.
    assert rerun_parsed["tools"]["ccc_daemon"] == "stopped"


def test_write_tools_default_staleness_does_not_overwrite_user_value(tmp_target):
    """A fresh payload with no staleness must not clobber a user-customized value."""
    initial = _payload_with_arrays()  # staleness=48
    _write_tools(tmp_target, initial)

    rerun_payload = _baseline_payload()
    rerun_payload["ccc_index"].pop("staleness_threshold_hours", None)
    _write_tools(tmp_target, rerun_payload)

    parsed = _read_yaml_file(tmp_target)
    assert parsed["ccc_index"]["staleness_threshold_hours"] == 48


def test_write_tools_rejects_payload_missing_required_keys(tmp_target):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write-tools", "--target", str(tmp_target)],
        input=json.dumps({"tools": {}}),  # missing tier and ccc_index
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    err = json.loads(result.stderr)
    assert "missing required keys" in err["message"]


def test_write_tools_rejects_invalid_json(tmp_target):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "write-tools", "--target", str(tmp_target)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1


# ─── read subcommand ────────────────────────────────────────────────────────


def test_read_missing_file_emits_null_payload(tmp_target):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "read", "--target", str(tmp_target)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["exists"] is False
    assert payload["data"] is None


def test_read_existing_file_emits_full_data(tmp_target):
    _write_tools(tmp_target, _payload_with_arrays())
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "read", "--target", str(tmp_target)],
        capture_output=True, text=True, timeout=10,
    )
    payload = json.loads(result.stdout)
    assert payload["exists"] is True
    assert payload["data"]["tier"] == "Deep"
    assert len(payload["data"]["qmd_collections"]) == 2


# ─── init-prefs subcommand ───────────────────────────────────────────────────


def test_init_prefs_creates_when_missing(tmp_target):
    target = tmp_target.parent / "preferences.yaml"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "init-prefs", "--target", str(target)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["wrote"] is True
    assert payload["first_run"] is True
    assert target.exists()
    parsed = _read_yaml_file(target)
    assert parsed["tier_override"] is None
    assert parsed["headless_mode"] is False


def test_init_prefs_preserves_existing(tmp_target):
    """Running init-prefs against an existing file MUST NOT overwrite user customization."""
    target = tmp_target.parent / "preferences.yaml"
    custom = "tier_override: Deep\nheadless_mode: true\n"
    target.write_text(custom, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "init-prefs", "--target", str(target)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["wrote"] is False
    assert target.read_text(encoding="utf-8") == custom


# ─── clean-stale subcommand ─────────────────────────────────────────────────


def test_clean_stale_removes_qmd_entries_not_in_live_list(tmp_target):
    _write_tools(tmp_target, _payload_with_arrays())  # 2 qmd_collections: foo-brief, foo-extraction
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale",
         "--target", str(tmp_target),
         "--qmd-live-names", "foo-brief"],  # only foo-brief is live
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert response["qmd_removed"] == ["foo-extraction"]
    assert response["wrote"] is True

    parsed = _read_yaml_file(tmp_target)
    assert [c["name"] for c in parsed["qmd_collections"]] == ["foo-brief"]


def test_clean_stale_no_changes_skips_write(tmp_target):
    _write_tools(tmp_target, _payload_with_arrays())
    mtime_before = tmp_target.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale",
         "--target", str(tmp_target),
         "--qmd-live-names", "foo-brief,foo-extraction"],  # all live
        capture_output=True, text=True, timeout=10,
    )
    response = json.loads(result.stdout)
    assert response["qmd_removed"] == []
    assert response["wrote"] is False
    # File must not have been touched.
    assert tmp_target.stat().st_mtime_ns == mtime_before


def test_clean_stale_prunes_missing_ccc_paths(tmp_target):
    """ccc_index_registry entries whose path no longer exists are removed."""
    payload = _payload_with_arrays()
    # Replace the registry with a mix of present + absent paths.
    present = tmp_target.parent  # tmp dir definitely exists
    payload["ccc_index_registry"] = [
        {"path": str(present), "indexed_at": "2026-04-25T10:00:00+00:00"},
        {"path": "/absolutely/does/not/exist/xyz123", "indexed_at": "2026-04-25T10:00:00+00:00"},
    ]
    _write_tools(tmp_target, payload)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale",
         "--target", str(tmp_target),
         "--prune-missing-ccc-paths"],
        capture_output=True, text=True, timeout=10,
    )
    response = json.loads(result.stdout)
    assert response["wrote"] is True
    assert response["ccc_removed"] == ["/absolutely/does/not/exist/xyz123"]
    parsed = _read_yaml_file(tmp_target)
    assert len(parsed["ccc_index_registry"]) == 1
    assert parsed["ccc_index_registry"][0]["path"] == str(present)


def test_clean_stale_combined_qmd_and_ccc(tmp_target):
    payload = _payload_with_arrays()
    payload["ccc_index_registry"] = [
        {"path": "/absolutely/does/not/exist/abc", "indexed_at": "2026-04-25T10:00:00+00:00"},
    ]
    _write_tools(tmp_target, payload)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale",
         "--target", str(tmp_target),
         "--qmd-live-names", "foo-brief",
         "--prune-missing-ccc-paths"],
        capture_output=True, text=True, timeout=10,
    )
    response = json.loads(result.stdout)
    assert response["qmd_removed"] == ["foo-extraction"]
    assert response["ccc_removed"] == ["/absolutely/does/not/exist/abc"]


def test_clean_stale_missing_target_is_user_error(tmp_target):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale",
         "--target", str(tmp_target),  # does not exist
         "--qmd-live-names", "foo"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1


# ─── End-to-end: register-qmd-collection subcommand via subprocess ──────────


def _register_qmd(target: Path, entry: dict) -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "register-qmd-collection",
         "--target", str(target)],
        input=json.dumps(entry),
        capture_output=True,
        text=True,
        timeout=10,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload, result.stderr


def test_register_qmd_appends_when_name_is_new(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    code, response, _ = _register_qmd(tmp_target, {
        "name": "marked-brief",
        "type": "brief",
        "source_workflow": "brief-skill",
        "skill_name": "marked",
        "created_at": "2026-05-02T00:00:00Z",
    })
    assert code == 0
    assert response["action"] == "appended"
    assert response["qmd_collections_count"] == 1

    persisted = _read_yaml_file(tmp_target)
    names = [e["name"] for e in persisted["qmd_collections"]]
    assert names == ["marked-brief"]


def test_register_qmd_replaces_when_name_collides(tmp_target):
    payload = _baseline_payload()
    payload["qmd_collections"] = [
        {"name": "marked-brief", "skill_name": "marked", "type": "brief", "created_at": "2025-01-01"},
        {"name": "stripe-extraction", "skill_name": "stripe", "type": "extraction"},
    ]
    _write_tools(tmp_target, payload)

    code, response, _ = _register_qmd(tmp_target, {
        "name": "marked-brief",
        "type": "brief",
        "skill_name": "marked",
        "created_at": "2026-05-02T00:00:00Z",
        "status": "pending",
    })
    assert code == 0
    assert response["action"] == "replaced"
    assert response["qmd_collections_count"] == 2  # other entry preserved

    persisted = _read_yaml_file(tmp_target)
    by_name = {e["name"]: e for e in persisted["qmd_collections"]}
    assert by_name["marked-brief"]["created_at"] == "2026-05-02T00:00:00Z"
    assert by_name["marked-brief"]["status"] == "pending"
    assert by_name["stripe-extraction"]["skill_name"] == "stripe"  # untouched


def test_register_qmd_preserves_unrelated_state(tmp_target):
    payload = _baseline_payload()
    payload["ccc_index_registry"] = [{"path": "/some/abs/path", "indexed_at": "2025-01-01"}]
    payload["ccc_index"]["staleness_threshold_hours"] = 99
    _write_tools(tmp_target, payload)

    _register_qmd(tmp_target, {"name": "new-collection", "skill_name": "x", "type": "brief"})

    persisted = _read_yaml_file(tmp_target)
    assert persisted["ccc_index_registry"] == [{"path": "/some/abs/path", "indexed_at": "2025-01-01"}]
    assert persisted["ccc_index"]["staleness_threshold_hours"] == 99
    assert persisted["tier"] == payload["tier"]


def test_register_qmd_rejects_missing_name(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    code, _, stderr = _register_qmd(tmp_target, {"skill_name": "x", "type": "brief"})
    assert code == 1
    assert "name" in stderr


def test_register_qmd_rejects_empty_stdin(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "register-qmd-collection",
         "--target", str(tmp_target)],
        input="",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "empty stdin" in result.stderr


def test_register_qmd_rejects_invalid_json(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "register-qmd-collection",
         "--target", str(tmp_target)],
        input="not-json",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "invalid JSON" in result.stderr


def test_register_qmd_rejects_non_object_entry(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "register-qmd-collection",
         "--target", str(tmp_target)],
        input='["array", "not", "object"]',
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "JSON object" in result.stderr


def test_register_qmd_missing_target_is_user_error(tmp_target):
    # tmp_target has not been written yet
    code, _, stderr = _register_qmd(tmp_target, {"name": "foo", "type": "brief"})
    assert code == 1
    assert "does not exist" in stderr


class TestAtomicWriteBinary:
    """_atomic_write persists content verbatim — no CRLF injection on Windows."""

    def test_byte_identity_multiline(self):
        content = "tools:\n  qmd: true\nqmd_collections:\n  - a\n  - b\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "forge.yaml"
            mod._atomic_write(target, content)
            assert target.read_bytes() == content.encode("utf-8")
            assert b"\r\n" not in target.read_bytes()
