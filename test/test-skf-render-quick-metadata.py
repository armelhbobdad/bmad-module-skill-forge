#!/usr/bin/env python3
"""Tests for skf-render-quick-metadata.py.

The renderer is pure (no I/O beyond stdin/stdout) so tests call
render_metadata() directly and assert on the returned envelope.
A frozen `now_fn` injects a deterministic timestamp.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_render_quick_metadata",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-render-quick-metadata.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


FROZEN_TS = "2026-05-01T12:00:00Z"


def _payload(**overrides) -> dict:
    """Minimal valid payload; tests override one field at a time."""
    base = {
        "name": "foo",
        "version": "1.2.3",
        "description": "a python lib",
        "language": "python",
        "source_repo": "https://github.com/x/foo",
        "exports": [{"name": "fn", "type": "def"}, {"name": "Cls", "type": "class"}],
        "dependencies": ["requests"],
        "language_hint": None,
        "scope_hint": None,
        "skf_version": "1.2.0",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Constants — must always be literal regardless of input
# --------------------------------------------------------------------------


class TestConstants:
    def test_top_level_constants(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["skill_type"] == "single"
        assert m["spec_version"] == "1.3"
        assert m["source_authority"] == "community"
        assert m["confidence_tier"] == "Quick"
        assert m["generated_by"] == "quick-skill"

    def test_tool_versions_ast_grep_qmd_null(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["tool_versions"]["ast_grep"] is None
        assert m["tool_versions"]["qmd"] is None

    def test_zero_buckets_in_confidence_distribution(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        cd = m["confidence_distribution"]
        assert cd["t1"] == 0
        assert cd["t2"] == 0
        assert cd["t3"] == 0

    def test_zero_and_unit_stats(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        s = m["stats"]
        assert s["exports_internal"] == 0
        assert s["scripts_count"] == 0
        assert s["assets_count"] == 0
        assert s["public_api_coverage"] == 1.0
        assert s["total_coverage"] == 1.0


# --------------------------------------------------------------------------
# Input-derived
# --------------------------------------------------------------------------


class TestInputDerived:
    def test_echoes_basic_fields(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["name"] == "foo"
        assert m["version"] == "1.2.3"
        assert m["description"] == "a python lib"
        assert m["language"] == "python"
        assert m["source_repo"] == "https://github.com/x/foo"

    def test_skf_version_passes_through(self):
        m = mod.render_metadata(_payload(skf_version="2.0.0-rc.1"), now_fn=lambda: FROZEN_TS)
        assert m["tool_versions"]["skf"] == "2.0.0-rc.1"

    def test_source_package_defaults_to_name(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["source_package"] == "foo"

    def test_source_package_explicit_wins(self):
        m = mod.render_metadata(_payload(source_package="@scope/foo"), now_fn=lambda: FROZEN_TS)
        assert m["source_package"] == "@scope/foo"

    def test_optional_strings_default_to_empty(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["source_root"] == ""
        assert m["source_commit"] == ""
        assert m["compatibility"] == ""

    def test_provenance_hints_echoed_when_provided(self):
        m = mod.render_metadata(
            _payload(language_hint="python", scope_hint="src/foo"),
            now_fn=lambda: FROZEN_TS,
        )
        assert m["provenance"]["language_hint"] == "python"
        assert m["provenance"]["scope_hint"] == "src/foo"

    def test_dependencies_echoed_as_list(self):
        m = mod.render_metadata(_payload(dependencies=["a", "b", "c"]), now_fn=lambda: FROZEN_TS)
        assert m["dependencies"] == ["a", "b", "c"]


# --------------------------------------------------------------------------
# Computed (export-count-driven, timestamp)
# --------------------------------------------------------------------------


class TestComputed:
    def test_timestamp_uses_injected_now(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["generation_date"] == FROZEN_TS

    def test_default_timestamp_format(self):
        # Without an injected now_fn, the real one runs — assert it matches the
        # documented "YYYY-MM-DDTHH:MM:SSZ" shape (don't pin the exact value).
        m = mod.render_metadata(_payload())
        ts = m["generation_date"]
        assert len(ts) == 20
        assert ts.endswith("Z")
        assert ts[4] == "-" and ts[7] == "-" and ts[10] == "T" and ts[13] == ":" and ts[16] == ":"

    def test_t1_low_equals_export_count(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        assert m["confidence_distribution"]["t1_low"] == 2

    def test_stats_count_fields_equal_export_count(self):
        m = mod.render_metadata(_payload(), now_fn=lambda: FROZEN_TS)
        s = m["stats"]
        assert s["exports_documented"] == 2
        assert s["exports_public_api"] == 2
        assert s["exports_total"] == 2

    def test_zero_exports_envelope(self):
        m = mod.render_metadata(_payload(exports=[]), now_fn=lambda: FROZEN_TS)
        assert m["exports"] == []
        assert m["confidence_distribution"]["t1_low"] == 0
        s = m["stats"]
        assert s["exports_documented"] == 0
        assert s["exports_public_api"] == 0
        assert s["exports_total"] == 0


# --------------------------------------------------------------------------
# Export normalisation
# --------------------------------------------------------------------------


class TestExportNormalisation:
    def test_accepts_list_of_strings(self):
        m = mod.render_metadata(_payload(exports=["a", "b", "c"]), now_fn=lambda: FROZEN_TS)
        assert m["exports"] == ["a", "b", "c"]

    def test_accepts_list_of_dicts(self):
        m = mod.render_metadata(
            _payload(exports=[{"name": "fn", "type": "def"}, {"name": "Cls", "type": "class"}]),
            now_fn=lambda: FROZEN_TS,
        )
        assert m["exports"] == ["fn", "Cls"]

    def test_dedupes_repeated_names(self):
        m = mod.render_metadata(
            _payload(exports=[{"name": "fn"}, "fn", {"name": "Cls"}]),
            now_fn=lambda: FROZEN_TS,
        )
        assert m["exports"] == ["fn", "Cls"]
        assert m["confidence_distribution"]["t1_low"] == 2

    def test_skips_invalid_items(self):
        m = mod.render_metadata(
            _payload(exports=[None, 42, {"type": "def"}, {"name": "ok"}, ""]),
            now_fn=lambda: FROZEN_TS,
        )
        assert m["exports"] == ["ok"]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


class TestRequiredFields:
    def test_missing_name_returns_error(self):
        result = mod.render_metadata(
            {"language": "python", "source_repo": "https://github.com/x/y"},
            now_fn=lambda: FROZEN_TS,
        )
        assert "_error" in result
        assert "name" in result["_error"]

    def test_missing_language_returns_error(self):
        result = mod.render_metadata(
            {"name": "foo", "source_repo": "https://github.com/x/y"},
            now_fn=lambda: FROZEN_TS,
        )
        assert "_error" in result
        assert "language" in result["_error"]

    def test_missing_source_repo_returns_error(self):
        result = mod.render_metadata(
            {"name": "foo", "language": "python"}, now_fn=lambda: FROZEN_TS
        )
        assert "_error" in result
        assert "source_repo" in result["_error"]

    def test_empty_string_treated_as_missing(self):
        result = mod.render_metadata(
            {"name": "", "language": "python", "source_repo": "https://github.com/x/y"},
            now_fn=lambda: FROZEN_TS,
        )
        assert "_error" in result


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------


class TestDefaults:
    def test_version_defaults_to_1_0_0(self):
        p = _payload()
        del p["version"]
        m = mod.render_metadata(p, now_fn=lambda: FROZEN_TS)
        assert m["version"] == "1.0.0"

    def test_skf_version_defaults_to_unknown(self):
        p = _payload()
        del p["skf_version"]
        m = mod.render_metadata(p, now_fn=lambda: FROZEN_TS)
        assert m["tool_versions"]["skf"] == "unknown"

    def test_dependencies_default_to_empty_list(self):
        p = _payload()
        del p["dependencies"]
        m = mod.render_metadata(p, now_fn=lambda: FROZEN_TS)
        assert m["dependencies"] == []

    def test_provenance_hints_default_to_null(self):
        p = _payload()
        del p["language_hint"]
        del p["scope_hint"]
        m = mod.render_metadata(p, now_fn=lambda: FROZEN_TS)
        assert m["provenance"]["language_hint"] is None
        assert m["provenance"]["scope_hint"] is None


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class TestCli:
    def test_stdin_round_trip(self, monkeypatch, capsys):
        payload = _payload()
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        rc = mod.main([])
        assert rc == 0
        out = capsys.readouterr().out
        envelope = json.loads(out)
        assert envelope["name"] == "foo"
        assert envelope["confidence_tier"] == "Quick"

    def test_empty_stdin_returns_2(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        rc = mod.main([])
        assert rc == 2

    def test_invalid_json_returns_2(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        rc = mod.main([])
        assert rc == 2

    def test_array_root_returns_2(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("[1,2,3]"))
        rc = mod.main([])
        assert rc == 2

    def test_missing_required_field_returns_1(self, monkeypatch):
        # Missing source_repo
        payload = {"name": "foo", "language": "python"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        rc = mod.main([])
        assert rc == 1
