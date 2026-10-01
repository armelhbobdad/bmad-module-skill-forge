#!/usr/bin/env python3
"""Tests for skf-forge-tier-rw.py.

Highest-value test: round-trip preservation of `qmd_collections`,
`ccc_index_registry`, and `ccc_index.staleness_threshold_hours` across
a write-tools call. Losing those arrays would silently break every
downstream skill that reads them. `ccc_index.exclude_patterns` (the SKF
exclusion record) is kept when the payload sends null, so a setup run
that did not reconcile ccc exclusions cannot wipe it.

Every subcommand that rewrites forge-tier.yaml holds forge-tier.yaml.lock
through skf-run-lock.py for its one read-modify-write: concurrent registers
lose no entry, a held lock makes a call wait and then exit 3 with nothing
written, a stale lock is replaced, and so at once is the empty file an
`flock` on the same path leaves. remove-qmd-collection is
register-qmd-collection's rollback.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
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


def test_merge_replaces_exclude_patterns_when_payload_lists_them():
    """A payload list replaces the recorded exclude_patterns outright (no union)."""
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


def test_merge_keeps_recorded_exclude_patterns_when_payload_null():
    """A null payload value means step 1b did not reconcile — keep the record."""
    new_payload = _baseline_payload()
    new_payload["ccc_index"]["exclude_patterns"] = None
    existing = {"ccc_index": {"exclude_patterns": ["**/_bmad", "skills"]}}
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["ccc_index"]["exclude_patterns"] == ["**/_bmad", "skills"]


def test_merge_keeps_recorded_exclude_patterns_when_key_absent():
    new_payload = _baseline_payload()
    new_payload["ccc_index"].pop("exclude_patterns")
    existing = {"ccc_index": {"exclude_patterns": ["**/_bmad", "skills"]}}
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["ccc_index"]["exclude_patterns"] == ["**/_bmad", "skills"]


@pytest.mark.parametrize("recorded", ["skills", {"a": 1}, 7, None])
def test_merge_null_with_non_list_existing_gives_empty_list(recorded):
    """A corrupt (non-list) record is not carried forward; null never survives."""
    new_payload = _baseline_payload()
    new_payload["ccc_index"]["exclude_patterns"] = None
    existing = {"ccc_index": {"exclude_patterns": recorded}}
    merged = mod._merge_preserved_fields(new_payload, existing)
    assert merged["ccc_index"]["exclude_patterns"] == []


def test_render_null_exclude_patterns_first_run_renders_empty_list():
    """First run with no existing file: a null payload value renders as []."""
    new_payload = _baseline_payload()
    new_payload["ccc_index"]["exclude_patterns"] = None
    merged = mod._merge_preserved_fields(new_payload, None)
    rendered = mod.render_forge_tier_yaml(merged)
    assert "exclude_patterns: null" not in rendered
    assert yaml.safe_load(rendered)["ccc_index"]["exclude_patterns"] == []


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


def test_cli_write_tools_null_exclude_patterns_preserves_record(tmp_target):
    """A run that did not reconcile ccc exclusions (payload null) keeps the record."""
    # First run without ccc: null on a missing file is accepted and renders [].
    first = _baseline_payload()
    first["ccc_index"]["exclude_patterns"] = None
    assert _write_tools(tmp_target, first)["status"] == "ok"
    assert _read_yaml_file(tmp_target)["ccc_index"]["exclude_patterns"] == []

    # A reconciling run records the SKF-owned patterns.
    recorded = ["**/_bmad", "**/_bmad-output", "skills", "_bmad-output/forge-data"]
    second = _baseline_payload()
    second["ccc_index"]["exclude_patterns"] = recorded
    _write_tools(tmp_target, second)
    assert _read_yaml_file(tmp_target)["ccc_index"]["exclude_patterns"] == recorded

    # A later non-reconciling run sends null: the record survives verbatim.
    third = _baseline_payload()
    third["ccc_index"]["exclude_patterns"] = None
    third["ccc_index"]["status"] = "none"
    assert _write_tools(tmp_target, third)["status"] == "ok"
    parsed = _read_yaml_file(tmp_target)
    assert parsed["ccc_index"]["exclude_patterns"] == recorded
    assert parsed["ccc_index"]["status"] == "none"


def test_write_tools_round_trips_per_entry_exclude_patterns(tmp_target):
    """Per-entry patterns from a mixed folder (class escapes, `*` families,
    non-ASCII names) are recorded exactly as the merge helper produced them."""
    recorded = [
        "**/_bmad",
        "skills/.export-manifest.json",
        "skills/[[]x[]]",
        "skills/[{]a,b[}]",
        "skills/caf\u00e9",
        "skills/export-skill-result*.json",
        "forge-data/analyze-source-*",
    ]
    payload = _baseline_payload()
    payload["ccc_index"]["exclude_patterns"] = recorded
    assert _write_tools(tmp_target, payload)["status"] == "ok"
    assert _read_yaml_file(tmp_target)["ccc_index"]["exclude_patterns"] == recorded

    # A later run that sends null keeps the per-entry record verbatim.
    rerun = _baseline_payload()
    rerun["ccc_index"]["exclude_patterns"] = None
    _write_tools(tmp_target, rerun)
    assert _read_yaml_file(tmp_target)["ccc_index"]["exclude_patterns"] == recorded


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


# ─── write-tools from a setup run's staged outputs ──────────────────────────


DETECT_SCRIPT = SCRIPT_PATH.parent / "skf-detect-tools.py"


def _write_staged(target: Path, detect: Path, ccc: Path | None = None) -> subprocess.CompletedProcess:
    """write-tools with --detect-from (and --ccc-from), nothing on stdin."""
    argv = [sys.executable, str(SCRIPT_PATH), "write-tools", "--target", str(target), "--detect-from", str(detect)]
    if ccc is not None:
        argv += ["--ccc-from", str(ccc)]
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)


def _detect_fixture(tmp_path: Path, tier="Forge+", ccc=True, daemon="healthy") -> Path:
    """A detect-tools.json shaped like skf-detect-tools.py's output."""
    path = tmp_path / "detect-tools.json"
    path.write_text(json.dumps({
        "status": "ok", "version": "v1",
        "tools": {"ast_grep": {"available": True, "version": "ast-grep 0.45.3"},
                  "gh_cli": {"available": False, "version": None},
                  "qmd": {"available": False, "status": "absent", "version": None},
                  "ccc": {"available": ccc, "daemon": daemon if ccc else None, "version": "0.2.41"},
                  "git": {"available": True, "version": "git version 2.47.3"},
                  "uv": {"available": True, "version": "uv 0.12.15"},
                  "security_scan": {"available": True}},
        "tier": {"calculated": tier, "detected": tier},
        "prior": {},
    }), encoding="utf-8")
    return path


def _ccc_result(tmp_path: Path, index: dict | None, patterns=None, status="ok") -> Path:
    path = tmp_path / "ccc-exclusions.json"
    body = {"status": status, "version": "v2", "effective_patterns": patterns, "index_action": "index"}
    if index is not None:
        body["index"] = index
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_write_tools_reads_real_detector_output(tmp_path):
    """The handoff test: real skf-detect-tools.py output, staged as setup step 1
    stages it, gives write-tools its tools and tier with nothing typed back."""
    detect = tmp_path / "detect-tools.json"
    proc = subprocess.run([sys.executable, str(DETECT_SCRIPT), "--project-root", str(tmp_path)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    detect.write_text(proc.stdout, encoding="utf-8")
    probed = json.loads(proc.stdout)
    target = tmp_path / "sidecar" / "forge-tier.yaml"
    done = _write_staged(target, detect)
    assert done.returncode == 0, done.stderr
    written = _read_yaml_file(target)
    assert written["tier"] == probed["tier"]["calculated"]
    for key in ("ast_grep", "gh_cli", "qmd", "ccc"):
        assert written["tools"][key] is probed["tools"][key]["available"], key
    assert written["tools"]["ccc_daemon"] == probed["tools"]["ccc"].get("daemon")
    assert written["tools"]["security_scan"] is probed["tools"]["security_scan"]["available"]
    # No ccc result staged: the run did not prepare ccc, or, with ccc on
    # this machine, step 1b's helper wrote nothing.
    assert written["ccc_index"]["status"] == ("failed" if probed["tools"]["ccc"]["available"] else "none")
    assert written["ccc_index"]["exclude_patterns"] == []


def test_write_tools_takes_the_index_and_the_record_from_the_ccc_result(tmp_path):
    target = tmp_path / "forge-tier.yaml"
    index = {"status": "created", "indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00",
             "file_count": 42, "failed_reason": None}
    record = ["**/_bmad", "skills/[[]x[]]", "skills/caf\u00e9"]
    done = _write_staged(target, _detect_fixture(tmp_path), _ccc_result(tmp_path, index, record))
    assert done.returncode == 0, done.stderr
    written = _read_yaml_file(target)
    assert written["tools"] == {"ast_grep": True, "gh_cli": False, "qmd": False, "ccc": True,
                                "ccc_daemon": "healthy", "security_scan": True}
    assert written["tier"] == "Forge+"
    assert written["ccc_index"] == {"indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00",
                                    "status": "created", "staleness_threshold_hours": 24, "file_count": 42,
                                    "exclude_patterns": record}


@pytest.mark.parametrize("content,ccc,status", [
    (None, False, "none"),
    (None, True, "failed"),
    ("", True, "failed"),
    ('{"status": "error", "message": "settings.yml is not a mapping"}', True, "failed"),
], ids=["not-staged-no-ccc", "not-staged-with-ccc", "empty", "helper-error"])
def test_write_tools_keeps_the_record_when_ccc_was_not_prepared(tmp_path, content, ccc, status):
    """No result (ccc unavailable: none; ccc available, so the helper wrote
    nothing: failed) or a failed one: the SKF exclusion record already in
    forge-tier.yaml survives."""
    target = tmp_path / "forge-tier.yaml"
    recorded = ["**/_bmad", "skills"]
    first = _write_staged(target, _detect_fixture(tmp_path), _ccc_result(
        tmp_path, {"status": "created", "indexed_path": "/p", "last_indexed": "2026-10-01T10:00:00+00:00",
                   "file_count": 3}, recorded))
    assert first.returncode == 0, first.stderr
    ccc_path = tmp_path / "ccc-exclusions.json"
    ccc_path.unlink()
    if content is not None:
        ccc_path.write_text(content, encoding="utf-8")
    done = _write_staged(target, _detect_fixture(tmp_path, ccc=ccc), ccc_path)
    assert done.returncode == 0, done.stderr
    written = _read_yaml_file(target)["ccc_index"]
    assert written["status"] == status
    assert written["indexed_path"] is None and written["last_indexed"] is None and written["file_count"] is None
    assert written["exclude_patterns"] == recorded


@pytest.mark.parametrize("detect,ccc,needle", [
    ("missing", None, "holds no skf-detect-tools.py output"),
    ('{"status": "ok"}', None, "has no `tools` and `tier.calculated`"),
    ("good", '{"status": "ok", "effective_patterns": null}', "holds no `index` result"),
], ids=["no-detector-output", "no-tier", "no-index"])
def test_write_tools_refuses_staged_outputs_it_cannot_read(tmp_path, detect, ccc, needle):
    detect_path = _detect_fixture(tmp_path) if detect == "good" else tmp_path / "detect-tools.json"
    if detect not in ("good", "missing"):
        detect_path.write_text(detect, encoding="utf-8")
    ccc_path = None
    if ccc is not None:
        ccc_path = tmp_path / "ccc-exclusions.json"
        ccc_path.write_text(ccc, encoding="utf-8")
    done = _write_staged(tmp_path / "forge-tier.yaml", detect_path, ccc_path)
    assert done.returncode == 1
    assert needle in json.loads(done.stderr)["message"]
    assert not (tmp_path / "forge-tier.yaml").exists()


def test_write_tools_ccc_from_needs_detect_from(tmp_path):
    done = subprocess.run([sys.executable, str(SCRIPT_PATH), "write-tools", "--target", str(tmp_path / "f.yaml"),
                           "--ccc-from", str(tmp_path / "ccc.json")],
                          input=json.dumps(_baseline_payload()), capture_output=True, text=True, timeout=10)
    assert done.returncode == 1
    assert "--ccc-from needs --detect-from" in json.loads(done.stderr)["message"]


def test_init_prefs_is_gone():
    """The installer writes preferences.yaml (setupSidecar); setup no longer does."""
    assert not hasattr(mod, "PREFERENCES_TEMPLATE") and not hasattr(mod, "cmd_init_prefs")
    done = subprocess.run([sys.executable, str(SCRIPT_PATH), "init-prefs", "--target", "x.yaml"],
                          capture_output=True, text=True, timeout=10)
    assert done.returncode == 2


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


def _clean_from(target: Path, staged: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale", "--target", str(target), "--qmd-live-from", str(staged)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_clean_stale_reads_the_live_names_from_the_staged_classification(tmp_target):
    _write_tools(tmp_target, _payload_with_arrays())  # foo-brief, foo-extraction
    staged = tmp_target.parent / "qmd-classify.json"
    staged.write_text(json.dumps({"status": "ok", "live_names": ["foo-brief", "memory-root-1"],
                                  "healthy": ["foo-brief"]}), encoding="utf-8")
    response = _clean_from(tmp_target, staged)
    assert response["qmd_removed"] == ["foo-extraction"]
    assert [c["name"] for c in _read_yaml_file(tmp_target)["qmd_collections"]] == ["foo-brief"]


@pytest.mark.parametrize("content", [None, "", '{"status": "ok"}', '{"live_names": "foo-brief"}'],
                         ids=["not-staged", "classifier-failed", "no-live-names", "not-a-list"])
def test_clean_stale_skips_qmd_cleanup_without_a_classification(tmp_target, content):
    """An empty list would mean nothing is live and empty the registry: a
    classifier that did not run or failed must leave it as it is."""
    _write_tools(tmp_target, _payload_with_arrays())
    before = tmp_target.read_bytes()
    staged = tmp_target.parent / "qmd-classify.json"
    if content is not None:
        staged.write_text(content, encoding="utf-8")
    response = _clean_from(tmp_target, staged)
    assert response["qmd_removed"] == [] and response["wrote"] is False
    assert tmp_target.read_bytes() == before


def test_clean_stale_live_sources_are_mutually_exclusive(tmp_target):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "clean-stale", "--target", str(tmp_target),
         "--qmd-live-from", "x.json", "--qmd-live-names", "foo-brief"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2


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


# ─── End-to-end: register-ccc-index subcommand via subprocess ────────────────


def _register_ccc(target: Path, entry: dict) -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "register-ccc-index",
         "--target", str(target)],
        input=json.dumps(entry),
        capture_output=True,
        text=True,
        timeout=10,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload, result.stderr


def test_register_ccc_appends_when_key_is_new(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    code, response, _ = _register_ccc(tmp_target, {
        "source_repo": "https://github.com/test/repo",
        "skill_name": "test-skill",
        "path": "/tmp/test",
        "indexed_at": "2026-05-25T14:00:00Z",
        "source_workflow": "create-skill",
    })
    assert code == 0
    assert response["action"] == "appended"
    assert response["ccc_index_registry_count"] == 1

    persisted = _read_yaml_file(tmp_target)
    assert len(persisted["ccc_index_registry"]) == 1
    assert persisted["ccc_index_registry"][0]["skill_name"] == "test-skill"


def test_register_ccc_replaces_when_composite_key_collides(tmp_target):
    payload = _baseline_payload()
    payload["ccc_index_registry"] = [
        {"source_repo": "https://github.com/test/repo", "skill_name": "test-skill",
         "path": "/old/path", "indexed_at": "2025-01-01"},
        {"source_repo": "https://github.com/other/repo", "skill_name": "other-skill",
         "path": "/other", "indexed_at": "2025-01-01"},
    ]
    _write_tools(tmp_target, payload)

    code, response, _ = _register_ccc(tmp_target, {
        "source_repo": "https://github.com/test/repo",
        "skill_name": "test-skill",
        "path": "/new/path",
        "indexed_at": "2026-05-25T15:00:00Z",
        "source_workflow": "create-skill",
    })
    assert code == 0
    assert response["action"] == "replaced"
    assert response["ccc_index_registry_count"] == 2

    persisted = _read_yaml_file(tmp_target)
    by_skill = {e["skill_name"]: e for e in persisted["ccc_index_registry"]}
    assert by_skill["test-skill"]["path"] == "/new/path"
    assert by_skill["other-skill"]["path"] == "/other"


def test_register_ccc_preserves_unrelated_state(tmp_target):
    payload = _baseline_payload()
    payload["qmd_collections"] = [{"name": "foo-brief", "type": "brief"}]
    payload["ccc_index"]["staleness_threshold_hours"] = 99
    _write_tools(tmp_target, payload)

    _register_ccc(tmp_target, {
        "source_repo": "https://github.com/x/y",
        "skill_name": "x",
        "path": "/x",
        "indexed_at": "2026-05-25",
        "source_workflow": "create-skill",
    })

    persisted = _read_yaml_file(tmp_target)
    assert persisted["qmd_collections"] == [{"name": "foo-brief", "type": "brief"}]
    assert persisted["ccc_index"]["staleness_threshold_hours"] == 99
    assert persisted["tier"] == payload["tier"]


def test_register_ccc_rejects_missing_source_repo(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    code, _, stderr = _register_ccc(tmp_target, {"skill_name": "x", "path": "/x"})
    assert code == 1
    assert "source_repo" in stderr


def test_register_ccc_rejects_missing_skill_name(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    code, _, stderr = _register_ccc(tmp_target, {"source_repo": "https://github.com/x/y", "path": "/x"})
    assert code == 1
    assert "skill_name" in stderr


def test_register_ccc_rejects_empty_stdin(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "register-ccc-index",
         "--target", str(tmp_target)],
        input="",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "empty stdin" in result.stderr


def test_register_ccc_missing_target_is_user_error(tmp_target):
    code, _, stderr = _register_ccc(tmp_target, {
        "source_repo": "https://github.com/x/y",
        "skill_name": "x",
        "path": "/x",
        "indexed_at": "2026-05-25",
        "source_workflow": "create-skill",
    })
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


# ─── remove-qmd-collection subcommand ───────────────────────────────────────


def _remove_qmd(target: Path, name: str, *extra: str) -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "remove-qmd-collection",
         "--target", str(target), "--name", name, *extra],
        capture_output=True, text=True, timeout=60,
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload, result.stderr


def test_remove_qmd_removes_the_named_entry_and_keeps_the_rest(tmp_target):
    payload = _payload_with_arrays()  # foo-brief, foo-extraction; staleness 48
    _write_tools(tmp_target, payload)

    code, response, stderr = _remove_qmd(tmp_target, "foo-extraction")
    assert code == 0, stderr
    assert response["action"] == "removed"
    assert response["removed_count"] == 1
    assert response["qmd_collections_count"] == 1
    assert response["wrote"] == str(tmp_target)

    persisted = _read_yaml_file(tmp_target)
    assert [e["name"] for e in persisted["qmd_collections"]] == ["foo-brief"]
    assert persisted["ccc_index_registry"] == payload["ccc_index_registry"]
    assert persisted["ccc_index"]["staleness_threshold_hours"] == 48
    assert persisted["tier"] == "Deep"


def test_remove_qmd_rolls_back_a_register(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    before = _read_yaml_file(tmp_target)
    _register_qmd(tmp_target, {"name": "marked-extraction", "type": "extraction",
                               "skill_name": "marked"})
    code, response, _ = _remove_qmd(tmp_target, "marked-extraction")
    assert code == 0
    assert response["action"] == "removed"
    assert _read_yaml_file(tmp_target) == before


def test_remove_qmd_absent_name_writes_nothing(tmp_target):
    _write_tools(tmp_target, _payload_with_arrays())
    mtime_before = tmp_target.stat().st_mtime_ns
    code, response, _ = _remove_qmd(tmp_target, "never-registered")
    assert code == 0
    assert response["action"] == "absent"
    assert response["removed_count"] == 0
    assert response["qmd_collections_count"] == 2
    assert response["wrote"] is None
    assert tmp_target.stat().st_mtime_ns == mtime_before


def test_remove_qmd_removes_every_entry_with_that_name(tmp_target):
    payload = _baseline_payload()
    payload["qmd_collections"] = [
        {"name": "dup-docs", "type": "docs"},
        {"name": "keep-brief", "type": "brief"},
        {"name": "dup-docs", "type": "docs", "created_at": "2026-05-01"},
    ]
    _write_tools(tmp_target, payload)
    code, response, _ = _remove_qmd(tmp_target, "dup-docs")
    assert code == 0
    assert response["removed_count"] == 2
    assert _read_yaml_file(tmp_target)["qmd_collections"] == [{"name": "keep-brief", "type": "brief"}]


@pytest.mark.parametrize("name", ["", "   "])
def test_remove_qmd_rejects_an_empty_name(tmp_target, name):
    _write_tools(tmp_target, _baseline_payload())
    code, _, stderr = _remove_qmd(tmp_target, name)
    assert code == 1
    assert "--name" in stderr


def test_remove_qmd_missing_target_is_user_error(tmp_path):
    target = tmp_path / "sidecar" / "forge-tier.yaml"
    code, _, stderr = _remove_qmd(target, "foo")
    assert code == 1
    assert "does not exist" in stderr
    # The call stops before it takes the lock, so it creates nothing.
    assert not target.parent.exists()


# ─── The registry lock ──────────────────────────────────────────────────────


def _lock_of(target: Path) -> Path:
    return target.with_name(target.name + ".lock")


def _hold_lock(target: Path, owner: str = "create-skill:other:run-1",
               acquired_at: datetime | None = None) -> None:
    """Write the lock record another run holds (fresh unless acquired_at is given)."""
    when = acquired_at or datetime.now(timezone.utc)
    record = {"owner": owner, "acquired_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "tool": "skf-run-lock"}
    _lock_of(target).write_bytes((json.dumps(record) + "\n").encode("utf-8"))


def _run(target: Path, argv: list[str], stdin: str | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), argv[0], "--target", str(target), *argv[1:]],
        input=stdin if stdin is not None else "", capture_output=True, text=True, timeout=60,
    )


# (arguments after the subcommand name, stdin) for each subcommand that rewrites the file.
LOCKED_CALLS = {
    "write-tools": (["write-tools"], json.dumps(_baseline_payload())),
    "register-qmd-collection": (["register-qmd-collection"],
                                json.dumps({"name": "new-brief", "type": "brief"})),
    "remove-qmd-collection": (["remove-qmd-collection", "--name", "foo-brief"], None),
    "register-ccc-index": (["register-ccc-index"],
                           json.dumps({"source_repo": "https://github.com/x/y",
                                       "skill_name": "y", "path": "/y"})),
    "clean-stale": (["clean-stale", "--qmd-live-names", "foo-brief"], None),
}


@pytest.mark.parametrize("call", sorted(LOCKED_CALLS))
def test_every_rewrite_releases_its_lock(tmp_target, call):
    _write_tools(tmp_target, _payload_with_arrays())
    argv, stdin = LOCKED_CALLS[call]
    result = _run(tmp_target, argv, stdin)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["lock_stale_replaced"] is None
    # No lock, guard or temp file is left beside forge-tier.yaml.
    assert sorted(p.name for p in tmp_target.parent.iterdir()) == ["forge-tier.yaml"]


@pytest.mark.parametrize("call", sorted(LOCKED_CALLS))
def test_a_held_lock_makes_every_rewrite_exit_3_without_writing(tmp_target, call):
    _write_tools(tmp_target, _payload_with_arrays())
    before = tmp_target.read_bytes()
    _hold_lock(tmp_target)
    argv, stdin = LOCKED_CALLS[call]
    start = time.monotonic()
    result = _run(tmp_target, [*argv, "--lock-timeout", "0.3"], stdin)
    assert result.returncode == 3, result.stderr
    assert time.monotonic() - start >= 0.3
    message = json.loads(result.stderr)["message"]
    assert "create-skill:other:run-1" in message
    assert "Nothing was written" in message
    assert tmp_target.read_bytes() == before
    assert json.loads(_lock_of(tmp_target).read_text(encoding="utf-8"))["owner"] == \
        "create-skill:other:run-1"


def test_a_user_error_inside_the_lock_still_releases_it(tmp_target):
    """_die inside the locked section (an unreadable file) must not leave the lock."""
    tmp_target.write_text("- a list, not a mapping\n", encoding="utf-8")
    code, _, stderr = _register_qmd(tmp_target, {"name": "x", "type": "brief"})
    assert code == 2
    assert "expected mapping" in stderr
    assert not _lock_of(tmp_target).exists()


def test_a_stale_lock_is_replaced_and_reported(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    killed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    _hold_lock(tmp_target, owner="forge-tier-rw:register-qmd-collection:killed", acquired_at=killed_at)
    code, response, stderr = _register_qmd(tmp_target, {"name": "after-crash", "type": "brief"})
    assert code == 0, stderr
    assert response["lock_stale_replaced"] == {
        "held_by": "forge-tier-rw:register-qmd-collection:killed",
        "held_since": killed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    assert [e["name"] for e in _read_yaml_file(tmp_target)["qmd_collections"]] == ["after-crash"]
    assert not _lock_of(tmp_target).exists()


@pytest.mark.parametrize("age", [0, 3600])
def test_an_empty_lock_file_left_by_flock_is_replaced_at_once(tmp_target, age):
    """create-skill prose runs `flock -x forge-tier.yaml.lock`, which leaves an empty file.

    The run-lock helper never writes an empty lock, so even a fresh one holds
    nothing: the call replaces it within a 1-second --lock-timeout instead of
    waiting the 15 seconds a lock of an unnamed owner takes to go stale.
    """
    _write_tools(tmp_target, _baseline_payload())
    lock = _lock_of(tmp_target)
    lock.write_bytes(b"")
    stamp = time.time() - age
    os.utime(lock, (stamp, stamp))
    argv, stdin = LOCKED_CALLS["register-qmd-collection"]
    result = _run(tmp_target, [*argv, "--lock-timeout", "1"], stdin)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["lock_stale_replaced"]["held_by"] is None
    assert not lock.exists()


@pytest.mark.skipif(os.name == "nt", reason="fcntl.flock is POSIX only")
def test_a_call_inside_a_held_flock_does_not_wait(tmp_target):
    """What create-skill §6b does: register-ccc-index inside `flock -x forge-tier.yaml.lock`."""
    import fcntl

    _write_tools(tmp_target, _baseline_payload())
    argv, stdin = LOCKED_CALLS["register-ccc-index"]
    with open(_lock_of(tmp_target), "ab") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        result = _run(tmp_target, [*argv, "--lock-timeout", "1"], stdin)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["action"] == "appended"
    assert sorted(p.name for p in tmp_target.parent.iterdir()) == ["forge-tier.yaml"]


def test_a_folder_at_the_lock_path_is_an_io_error(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    before = tmp_target.read_bytes()
    _lock_of(tmp_target).mkdir()
    code, _, stderr = _register_qmd(tmp_target, {"name": "x-brief", "type": "brief"})
    assert code == 2
    assert "folder" in json.loads(stderr)["message"]
    assert tmp_target.read_bytes() == before


def test_a_call_waits_for_a_lock_released_meanwhile(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    run_lock = mod._load_run_lock()
    lock = _lock_of(tmp_target)
    holder = "create-skill:other:run-2"
    assert run_lock.acquire(lock, holder, 3600)["acquired"] is True

    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT_PATH), "register-qmd-collection",
         "--target", str(tmp_target), "--lock-timeout", "30"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    proc.stdin.write(json.dumps({"name": "waited-brief", "type": "brief"}))
    proc.stdin.close()
    time.sleep(0.8)
    assert proc.poll() is None, "the call did not wait for the lock"
    assert run_lock.release(lock, holder)["released"] is True

    stdout = proc.stdout.read()
    stderr = proc.stderr.read()
    assert proc.wait(timeout=60) == 0, stderr
    assert json.loads(stdout)["action"] == "appended"
    assert [e["name"] for e in _read_yaml_file(tmp_target)["qmd_collections"]] == ["waited-brief"]


# Runs a script once a start file exists, so the calls reach the lock together.
RUNNER = (
    "import os, runpy, sys, time\n"
    "go, script = sys.argv[1], sys.argv[2]\n"
    "while not os.path.exists(go):\n"
    "    time.sleep(0.002)\n"
    "sys.argv = sys.argv[2:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def test_concurrent_registers_lose_no_entry(tmp_target):
    """Without the lock, calls that read the same file overwrite each other's entry."""
    _write_tools(tmp_target, _baseline_payload())
    go = tmp_target.parent / "go"
    names = [f"skill{i}-extraction" for i in range(8)]
    procs = []
    for name in names:
        proc = subprocess.Popen(
            [sys.executable, "-c", RUNNER, str(go), str(SCRIPT_PATH),
             "register-qmd-collection", "--target", str(tmp_target)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        proc.stdin.write(json.dumps({"name": name, "type": "extraction"}))
        proc.stdin.close()
        procs.append(proc)
    time.sleep(0.8)
    go.write_bytes(b"")
    for proc in procs:
        stderr = proc.stderr.read()
        proc.stdout.read()
        assert proc.wait(timeout=90) == 0, stderr

    persisted = _read_yaml_file(tmp_target)
    assert sorted(e["name"] for e in persisted["qmd_collections"]) == sorted(names)
    assert sorted(p.name for p in tmp_target.parent.iterdir()) == ["forge-tier.yaml", "go"]


def test_lock_timeout_must_not_be_negative(tmp_target):
    _write_tools(tmp_target, _baseline_payload())
    code, _, stderr = _remove_qmd(tmp_target, "foo", "--lock-timeout", "-1")
    assert code == 1
    assert "--lock-timeout" in stderr


def _installed_copy(tmp_path: Path, *scripts: str) -> Path:
    """Copy scripts into an installed layout (_bmad/skf/shared/scripts/)."""
    scripts_dir = tmp_path / "_bmad" / "skf" / "shared" / "scripts"
    scripts_dir.mkdir(parents=True)
    for name in scripts:
        shutil.copy2(SCRIPT_PATH.parent / name, scripts_dir / name)
    return scripts_dir / "skf-forge-tier-rw.py"


def test_installed_layout_loads_the_sibling_run_lock_helper(tmp_path):
    script = _installed_copy(tmp_path, "skf-forge-tier-rw.py", "skf-run-lock.py")
    target = tmp_path / "_bmad" / "_memory" / "forger-sidecar" / "forge-tier.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(mod.render_forge_tier_yaml(_baseline_payload()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "register-qmd-collection", "--target", str(target)],
        input=json.dumps({"name": "x-brief", "type": "brief"}),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert [e["name"] for e in _read_yaml_file(target)["qmd_collections"]] == ["x-brief"]


def test_a_missing_run_lock_helper_is_an_io_error(tmp_path):
    script = _installed_copy(tmp_path, "skf-forge-tier-rw.py")
    target = tmp_path / "forge-tier.yaml"
    target.write_text(mod.render_forge_tier_yaml(_baseline_payload()), encoding="utf-8")
    before = target.read_bytes()
    result = subprocess.run(
        [sys.executable, str(script), "register-qmd-collection", "--target", str(target)],
        input=json.dumps({"name": "x-brief", "type": "brief"}),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 2
    assert "run-lock helper" in json.loads(result.stderr)["message"]
    assert target.read_bytes() == before
