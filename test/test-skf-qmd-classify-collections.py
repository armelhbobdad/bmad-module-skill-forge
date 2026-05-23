#!/usr/bin/env python3
"""Tests for skf-qmd-classify-collections.py.

Classification rules under test (per step 3 §3 and PR #244):

  Healthy   = forge-suffix-matched live ∩ registry
  Orphaned  = forge-suffix-matched live − registry
  Stale     = registry − ALL live (includes foreign-suffix names)
  Foreign   = live − forge-suffix-matched (silently excluded from
              every classification, reported as count + capped sample)

The PR #244 incident — a fresh-setup user with 48 unrelated Hindsight
memory-bank collections in their QMD daemon — is reproduced as
test_pr244_incident_reproduction below.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-qmd-classify-collections.py"
)

spec = importlib.util.spec_from_file_location("skf_qmd_classify", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ─── Forge-namespace recognition ────────────────────────────────────────────


@pytest.mark.parametrize("name,expected", [
    ("foo-brief",          True),
    ("foo-temporal",       True),
    ("foo-docs",           True),
    ("foo-extraction",     True),
    ("multi-word-skill-name-extraction", True),
    ("memory-root-1",      False),
    ("sessions-2",         False),
    ("foo",                False),
    ("foo-other",          False),
    ("brief",              False),  # exact match without prefix dash → not forge
    ("foo-brief-extra",    False),  # suffix must be terminal
    ("",                   False),
])
def test_is_forge_owned(name, expected):
    assert mod.is_forge_owned(name) is expected


# ─── parse_live_names ───────────────────────────────────────────────────────


def test_parse_live_names_handles_empty():
    assert mod.parse_live_names("") == []
    assert mod.parse_live_names("   ") == []


def test_parse_live_names_strips_whitespace():
    assert mod.parse_live_names(" foo , bar ,  baz ") == ["foo", "bar", "baz"]


def test_parse_live_names_dedups_preserving_order():
    assert mod.parse_live_names("a,b,a,c,b,a") == ["a", "b", "c"]


def test_parse_live_names_skips_empty_segments():
    assert mod.parse_live_names("a,,b,,,c,") == ["a", "b", "c"]


# ─── parse_collection_list_output (qmd CLI stdout) ───────────────────────────


def test_parse_collection_list_modern_format():
    """Newer qmd: header, blank lines, `name (qmd://name/)`, indented metadata.

    Regression for the silent no-op where suffixed entries failed the
    is_forge_owned check and every forge collection was mis-classified foreign.
    """
    raw = (
        "Collections (3):\n"
        "\n"
        "oms-cognee-brief (qmd://oms-cognee-brief/)\n"
        "  Pattern:  skill-brief.yaml\n"
        "  Files:    0\n"
        "\n"
        "livekit-extraction (qmd://livekit-extraction/)\n"
        "  Pattern:  *.rs\n"
        "  Files:    42\n"
        "\n"
        "memory-root-1 (qmd://memory-root-1/)\n"
        "  Files:    7\n"
    )
    assert mod.parse_collection_list_output(raw) == [
        "oms-cognee-brief",
        "livekit-extraction",
        "memory-root-1",
    ]


def test_parse_collection_list_legacy_bare_names():
    """Older qmd printed one bare name per line — still supported."""
    raw = "foo-brief\nbar-extraction\nmemory-root-1\n"
    assert mod.parse_collection_list_output(raw) == [
        "foo-brief",
        "bar-extraction",
        "memory-root-1",
    ]


def test_parse_collection_list_empty():
    assert mod.parse_collection_list_output("") == []
    assert mod.parse_collection_list_output("Collections (0):\n\n") == []


def test_parse_collection_list_name_resembling_header_not_skipped():
    """A collection named `Collections-*` must not be mistaken for the header."""
    raw = (
        "Collections (1):\n"
        "\n"
        "Collections-brief (qmd://Collections-brief/)\n"
        "  Files:    1\n"
    )
    assert mod.parse_collection_list_output(raw) == ["Collections-brief"]


def test_parse_collection_list_feeds_classify_correctly():
    """End-to-end: modern stdout → parse → classify yields real classifications,
    not an all-foreign no-op."""
    raw = (
        "Collections (2):\n"
        "\n"
        "foo-brief (qmd://foo-brief/)\n"
        "  Files:    3\n"
        "\n"
        "lost-extraction (qmd://lost-extraction/)\n"
        "  Files:    9\n"
    )
    live = mod.parse_collection_list_output(raw)
    out = mod.classify(live, ["foo-brief"])
    assert out["healthy"] == ["foo-brief"]
    assert out["orphaned"] == ["lost-extraction"]
    assert out["foreign_filtered_count"] == 0


# ─── load_registry_names ─────────────────────────────────────────────────────


@pytest.fixture
def tmp_yaml():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "forge-tier.yaml"


def test_load_registry_missing_file_returns_empty(tmp_yaml):
    assert mod.load_registry_names(tmp_yaml) == []


def test_load_registry_extracts_names_from_qmd_collections(tmp_yaml):
    tmp_yaml.write_text(
        "qmd_collections:\n"
        "  - name: foo-brief\n"
        "    type: brief\n"
        "  - name: foo-extraction\n"
        "    type: extraction\n",
        encoding="utf-8",
    )
    assert mod.load_registry_names(tmp_yaml) == ["foo-brief", "foo-extraction"]


def test_load_registry_skips_entries_without_name(tmp_yaml):
    tmp_yaml.write_text(
        "qmd_collections:\n"
        "  - name: foo-brief\n"
        "  - type: extraction\n"  # no name
        "  - name: bar-docs\n",
        encoding="utf-8",
    )
    assert mod.load_registry_names(tmp_yaml) == ["foo-brief", "bar-docs"]


def test_load_registry_empty_array(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: []\n", encoding="utf-8")
    assert mod.load_registry_names(tmp_yaml) == []


def test_load_registry_missing_array_key(tmp_yaml):
    tmp_yaml.write_text("tier: Deep\n", encoding="utf-8")
    assert mod.load_registry_names(tmp_yaml) == []


def test_load_registry_malformed_yaml_dies(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: [unclosed\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        mod.load_registry_names(tmp_yaml)
    assert exc.value.code == 1


def test_load_registry_non_list_dies(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: 42\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        mod.load_registry_names(tmp_yaml)
    assert exc.value.code == 1


# ─── classify() — the core set arithmetic ────────────────────────────────────


def test_classify_first_run_no_collections():
    """Empty live, empty registry — everything is empty."""
    out = mod.classify([], [])
    assert out == {
        "live_names": [],
        "healthy": [],
        "orphaned": [],
        "stale": [],
        "foreign_filtered_count": 0,
        "foreign_filtered_sample": [],
    }


def test_classify_returns_live_names_sorted_unique():
    """live_names mirrors the input (sorted, deduplicated) so downstream callers don't re-fetch."""
    out = mod.classify(["foo-brief", "memory-root-1", "foo-brief"], [])
    assert out["live_names"] == ["foo-brief", "memory-root-1"]


def test_classify_all_healthy():
    live = ["foo-brief", "foo-extraction"]
    registry = ["foo-brief", "foo-extraction"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["foo-brief", "foo-extraction"]
    assert out["orphaned"] == []
    assert out["stale"] == []


def test_classify_orphan_in_qmd_only():
    """Live collection with forge suffix but not in registry → orphaned."""
    live = ["foo-brief", "lost-extraction"]
    registry = ["foo-brief"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["foo-brief"]
    assert out["orphaned"] == ["lost-extraction"]
    assert out["stale"] == []


def test_classify_stale_in_registry_only():
    """Registry entry not in QMD → stale."""
    live = ["foo-brief"]
    registry = ["foo-brief", "deleted-temporal"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["foo-brief"]
    assert out["orphaned"] == []
    assert out["stale"] == ["deleted-temporal"]


def test_classify_foreign_silently_excluded():
    """Live collections without forge suffix are foreign — never displayed."""
    live = ["foo-brief", "memory-root-1", "sessions-2", "bar-extraction"]
    registry = ["foo-brief", "bar-extraction"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["bar-extraction", "foo-brief"]
    assert out["orphaned"] == []
    assert out["stale"] == []
    assert out["foreign_filtered_count"] == 2
    assert out["foreign_filtered_sample"] == ["memory-root-1", "sessions-2"]


def test_classify_pr244_incident_reproduction():
    """The exact data-loss footgun PR #244 closed, in test form.

    User runs setup for the first time on a host that has 48 Hindsight
    memory-bank collections in QMD. Registry is empty. Without the
    forge-namespace filter, all 48 Hindsight collections would have
    been classified as orphaned and offered for removal. With the
    filter, they are silently excluded and never enter the orphan
    classification.
    """
    hindsight = [f"{prefix}-{i}" for prefix in
                 ("memory-root", "memory-alt", "memory-dir", "sessions") for i in range(12)]
    assert len(hindsight) == 48

    out = mod.classify(hindsight, [])
    assert out["orphaned"] == [], "PR #244 regression — Hindsight banks would be deleted"
    assert out["stale"] == []
    assert out["foreign_filtered_count"] == 48
    assert len(out["foreign_filtered_sample"]) == mod.FOREIGN_SAMPLE_CAP  # capped


def test_classify_mixed_realistic_scenario():
    """A real-world Deep host with some forge skills + some foreign collections + drift."""
    live = [
        # Forge-managed, in registry — healthy
        "lib1-brief", "lib1-extraction", "lib2-brief",
        # Forge-managed, NOT in registry — orphaned (manual ccc test maybe)
        "experimental-extraction",
        # Foreign collections from other tools — silently excluded
        "memory-root-1", "memory-alt-2",
    ]
    registry = [
        "lib1-brief", "lib1-extraction", "lib2-brief",
        "deleted-skill-extraction",  # was deleted from QMD — stale
    ]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["lib1-brief", "lib1-extraction", "lib2-brief"]
    assert out["orphaned"] == ["experimental-extraction"]
    assert out["stale"] == ["deleted-skill-extraction"]
    assert out["foreign_filtered_count"] == 2


def test_classify_results_are_sorted_for_determinism():
    """Same input — byte-identical output. Set ops are unordered; sorted() makes them stable."""
    live = ["zoo-brief", "alpha-brief", "mid-extraction"]
    registry = ["zoo-brief", "alpha-brief", "mid-extraction"]
    out = mod.classify(live, registry)
    assert out["healthy"] == ["alpha-brief", "mid-extraction", "zoo-brief"]


def test_classify_foreign_sample_capped_but_count_accurate():
    live = [f"foreign-{i}" for i in range(20)]  # all foreign (no forge suffix)
    out = mod.classify(live, [])
    assert out["foreign_filtered_count"] == 20
    assert len(out["foreign_filtered_sample"]) == mod.FOREIGN_SAMPLE_CAP


def test_classify_registry_entries_with_non_forge_names_still_classified():
    """Hand-edited registry could contain a non-forge name — still tracked correctly."""
    live = ["foo-brief"]  # no foreign-name in live
    registry = ["foo-brief", "weird-no-suffix"]  # registry has a non-forge name
    out = mod.classify(live, registry)
    # weird-no-suffix is not in live, so it's stale (registry−live).
    assert "weird-no-suffix" in out["stale"]


# ─── End-to-end CLI subprocess tests ────────────────────────────────────────


def _run(*args) -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, timeout=10,
    )
    payload = json.loads(result.stdout) if result.stdout else None
    return result.returncode, payload, result.stderr


def test_cli_first_run_state(tmp_yaml):
    """No live collections, no registry file → emit empty everything."""
    rc, payload, stderr = _run("--live-names", "", "--registry-from-yaml", str(tmp_yaml))
    assert rc == 0, f"stderr: {stderr}"
    assert payload["status"] == "ok"
    assert payload["version"] == "v1"
    assert payload["healthy"] == []
    assert payload["orphaned"] == []
    assert payload["stale"] == []


def test_cli_realistic_deep_host(tmp_yaml):
    tmp_yaml.write_text(
        "qmd_collections:\n"
        "  - name: lib1-brief\n"
        "    type: brief\n"
        "  - name: lib1-extraction\n"
        "    type: extraction\n",
        encoding="utf-8",
    )
    rc, payload, _ = _run(
        "--live-names", "lib1-brief,lib1-extraction,memory-root-1",
        "--registry-from-yaml", str(tmp_yaml),
    )
    assert rc == 0
    assert payload["healthy"] == ["lib1-brief", "lib1-extraction"]
    assert payload["orphaned"] == []
    assert payload["stale"] == []
    assert payload["foreign_filtered_count"] == 1


def test_cli_pr244_incident(tmp_yaml):
    """End-to-end repro of the PR #244 incident."""
    # Empty registry, 4 Hindsight foreign collections in live
    rc, payload, _ = _run(
        "--live-names", "memory-root-1,memory-alt-2,memory-dir-3,sessions-4",
        "--registry-from-yaml", str(tmp_yaml),  # missing file → empty registry
    )
    assert rc == 0
    assert payload["orphaned"] == []
    assert payload["foreign_filtered_count"] == 4


def test_cli_missing_required_arg():
    """--registry-from-yaml is required."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--live-names", "foo-brief"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0


def test_cli_malformed_registry_emits_error(tmp_yaml):
    tmp_yaml.write_text("qmd_collections: [unclosed\n", encoding="utf-8")
    rc, _, stderr = _run("--live-names", "", "--registry-from-yaml", str(tmp_yaml))
    assert rc == 1
    err = json.loads(stderr)
    assert "failed to parse" in err["message"]
