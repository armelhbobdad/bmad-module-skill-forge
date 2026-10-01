#!/usr/bin/env python3
"""Tests for skf-render-quick-metadata.py.

render_metadata() is pure, so most tests call it directly and assert on
the returned envelope; a frozen `now_fn` injects a deterministic
timestamp. The file mode (--input, --extraction, --skf-root, --output)
runs through main() over files in a temporary folder, a description with
an apostrophe included (#592: the staged file replaces a single-quoted
echo that broke on one).
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


# --------------------------------------------------------------------------
# File mode: the staged fields, the extraction files and the SKF version
# --------------------------------------------------------------------------


EXTRACT = {"language": "python", "package_name": "foo-pkg", "version": "2.0.0", "description": "From the manifest.",
           "exports": [{"name": "fn", "type": "def", "source_file": "foo/__init__.py"},
                       {"name": "Cls", "type": "class", "source_file": "foo/__init__.py"}],
           "dependencies": ["requests", "pydantic"], "modules": [], "extra": {}, "warnings": []}
STAGED = {"name": "foo", "description": "Lodash's \"utilities\" for `$HOME`", "version": None,
          "language": "python", "source_repo": "https://github.com/x/foo", "source_root": "", "source_commit": "",
          "source_package": "", "compatibility": "", "language_hint": None, "scope_hint": "src/",
          "exports": None}


def _write(path: Path, value) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def _render_files(tmp_path, staged=STAGED, extractions=(EXTRACT,), skf_root=None):
    args = ["--input", _write(tmp_path / "metadata-input.json", staged),
            "--output", str(tmp_path / "metadata.json")]
    for i, extraction in enumerate(extractions):
        args += ["--extraction", _write(tmp_path / f"extract-{i}.json", extraction)]
    if skf_root is not None:
        args += ["--skf-root", str(skf_root)]
    return mod.main(args)


class TestFileMode:
    def test_the_description_reaches_metadata_as_staged(self, tmp_path, capsys):
        assert _render_files(tmp_path) == 0
        written = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
        assert written["description"] == "Lodash's \"utilities\" for `$HOME`"
        assert json.loads(capsys.readouterr().out) == written

    def test_exports_dependencies_and_version_come_from_the_extraction(self, tmp_path, capsys):
        assert _render_files(tmp_path) == 0
        m = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
        assert m["exports"] == ["fn", "Cls"] and m["stats"]["exports_documented"] == 2
        assert m["dependencies"] == ["requests", "pydantic"]
        assert (m["version"], m["source_package"]) == ("2.0.0", "foo-pkg")
        assert m["provenance"] == {"language_hint": None, "scope_hint": "src/"}

    def test_modules_aggregate_in_order_each_name_once(self, tmp_path, capsys):
        child = {"package_name": "foo-core", "version": "9.9.9", "exports": [{"name": "Core"}, {"name": "fn"}],
                 "dependencies": ["requests", "attrs"]}
        assert _render_files(tmp_path, extractions=(EXTRACT, child)) == 0
        m = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
        assert m["exports"] == ["fn", "Cls", "Core"]
        assert m["dependencies"] == ["requests", "pydantic", "attrs"]
        assert m["version"] == "2.0.0", "the parent manifest's version"

    def test_the_staged_fields_win(self, tmp_path, capsys):
        staged = {**STAGED, "version": "0.5.0", "exports": ["only", "these"], "source_package": "@x/foo"}
        assert _render_files(tmp_path, staged=staged) == 0
        m = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
        assert (m["version"], m["exports"], m["source_package"]) == ("0.5.0", ["only", "these"], "@x/foo")

    def test_no_extraction_falls_back_to_the_defaults(self, tmp_path, capsys):
        assert _render_files(tmp_path, staged={**STAGED, "description": ""}, extractions=()) == 0
        m = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
        assert (m["version"], m["exports"], m["source_package"], m["description"]) == ("1.0.0", [], "foo", "")

    def test_a_skills_module_extraction_renders_like_a_library(self, tmp_path, capsys):
        module = {"package_name": "demo", "exports": [
            {"name": "alpha", "type": "skill", "brief_description": "Builds.", "source_file": "skills/alpha/SKILL.md"},
            {"name": "BA", "type": "menu-code", "brief_description": "x", "source_file": "skills/module-help.csv"}]}
        assert _render_files(tmp_path, staged={**STAGED, "language": "markdown"}, extractions=(module,)) == 0
        m = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
        assert m["exports"] == ["alpha", "BA"] and m["confidence_distribution"]["t1_low"] == 2


class TestSkfVersion:
    def test_package_json_first(self, tmp_path):
        (tmp_path / "package.json").write_text('{"version": "3.0.0"}', encoding="utf-8")
        (tmp_path / "VERSION").write_text("2.9.0\n", encoding="utf-8")
        assert mod.probe_skf_version(tmp_path) == "3.0.0"

    def test_then_the_version_file(self, tmp_path):
        (tmp_path / "VERSION").write_text("3.0.0-rc.2\n", encoding="utf-8")
        assert mod.probe_skf_version(tmp_path) == "3.0.0-rc.2"

    def test_else_unknown(self, tmp_path):
        assert mod.probe_skf_version(tmp_path / "missing") == "unknown"
        assert mod.probe_skf_version(None) == "unknown"

    def test_the_render_carries_it(self, tmp_path, capsys):
        root = tmp_path / "skf"
        root.mkdir()
        (root / "VERSION").write_text("3.0.0\n", encoding="utf-8")
        assert _render_files(tmp_path, skf_root=root) == 0
        assert json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))["tool_versions"]["skf"] == "3.0.0"


class TestFileModeErrors:
    def test_an_unreadable_input_returns_2(self, tmp_path, capsys):
        assert mod.main(["--input", str(tmp_path / "missing.json")]) == 2
        assert "cannot read --input" in capsys.readouterr().err

    def test_a_bad_extraction_returns_2(self, tmp_path, capsys):
        (tmp_path / "bad.json").write_text("[1]", encoding="utf-8")
        assert mod.main(["--input", _write(tmp_path / "in.json", STAGED), "--extraction", str(tmp_path / "bad.json")]) == 2
        assert "must hold a JSON object" in capsys.readouterr().err

    def test_a_missing_required_field_returns_1(self, tmp_path, capsys):
        assert mod.main(["--input", _write(tmp_path / "in.json", {**STAGED, "source_repo": ""})]) == 1
