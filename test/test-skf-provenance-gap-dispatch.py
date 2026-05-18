#!/usr/bin/env python3
"""Tests for skf-provenance-gap-dispatch.py.

Covers:
  - discover_drift_report: missing dir, no reports, single report, multiple
    reports (returns latest by name DESC)
  - extract_out_of_scope_section: top-level heading, nested under
    Remediation Suggestions, missing section, multiple matches
  - parse_candidates: bullet format, table format, mixed formats,
    em-dash / en-dash / hyphen separators, empty section
  - reconcile: already-in-scope, pre-decided-skipped,
    pre-decided-demoted (both flavors), unresolved, most-recent-wins
    when same path has multiple amendments
  - dispatch end-to-end: no-report, no-candidates, candidates-found
  - CLI: happy path, bad paths exit 1
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-provenance-gap-dispatch.py"

spec = importlib.util.spec_from_file_location("skf_provenance_gap_dispatch", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------


def _make_report_dir(tmp_path: Path, skill: str, version: str) -> Path:
    d = tmp_path / skill / version
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_report(report_dir: Path, name: str, body: str) -> Path:
    p = report_dir / name
    p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return p


def _write_brief(tmp_path: Path, amendments: list[dict]) -> Path:
    brief = {
        "name": "x",
        "version": "1.0.0",
        "scope": {"include": [], "exclude": [], "notes": "", "amendments": amendments},
    }
    p = tmp_path / "brief.yaml"
    p.write_text(yaml.safe_dump(brief), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# discover_drift_report
# --------------------------------------------------------------------------


class TestDiscover:
    def test_missing_directory_returns_none(self, tmp_path: Path) -> None:
        assert mod.discover_drift_report(tmp_path, "missing", "1.0.0") is None

    def test_empty_directory_returns_none(self, tmp_path: Path) -> None:
        _make_report_dir(tmp_path, "my-skill", "1.0.0")
        assert mod.discover_drift_report(tmp_path, "my-skill", "1.0.0") is None

    def test_single_report(self, tmp_path: Path) -> None:
        d = _make_report_dir(tmp_path, "my-skill", "1.0.0")
        report = _write_report(d, "drift-report-2026-04-01T120000.md", "# Report")
        result = mod.discover_drift_report(tmp_path, "my-skill", "1.0.0")
        assert result == report

    def test_picks_latest_by_name_desc(self, tmp_path: Path) -> None:
        d = _make_report_dir(tmp_path, "my-skill", "1.0.0")
        _write_report(d, "drift-report-2026-04-01T120000.md", "# Old")
        _write_report(d, "drift-report-2026-05-01T120000.md", "# New")
        _write_report(d, "drift-report-2026-04-15T120000.md", "# Middle")
        result = mod.discover_drift_report(tmp_path, "my-skill", "1.0.0")
        assert result.name == "drift-report-2026-05-01T120000.md"

    def test_ignores_non_matching_files(self, tmp_path: Path) -> None:
        d = _make_report_dir(tmp_path, "my-skill", "1.0.0")
        _write_report(d, "other.md", "# Other")
        _write_report(d, "drift-report-A.md", "# A")
        result = mod.discover_drift_report(tmp_path, "my-skill", "1.0.0")
        assert result.name == "drift-report-A.md"


# --------------------------------------------------------------------------
# extract_out_of_scope_section
# --------------------------------------------------------------------------


class TestExtractSection:
    def test_top_level_heading(self) -> None:
        report = textwrap.dedent("""
            # Drift Report

            ## Summary
            Some summary text.

            ## Out-of-Scope Observations
            - `path/to/new.py` — 4 new exports
            - `path/to/other.py` — 2 new exports

            ## Other Section
            Not part of out-of-scope.
        """).strip()
        section = mod.extract_out_of_scope_section(report)
        assert section is not None
        assert "path/to/new.py" in section
        assert "Other Section" not in section

    def test_nested_under_remediation(self) -> None:
        report = textwrap.dedent("""
            # Drift Report

            ## Remediation Suggestions

            ### Out-of-Scope New Public API
            - `lib/new_module.py` — 3 exports added

            ### Other Subsection
            Unrelated content.

            ## Next Top-Level
            Other content.
        """).strip()
        section = mod.extract_out_of_scope_section(report)
        assert section is not None
        assert "lib/new_module.py" in section
        assert "Other Subsection" not in section

    def test_no_section_returns_none(self) -> None:
        report = "# Drift Report\n\n## Summary\nNothing relevant.\n"
        assert mod.extract_out_of_scope_section(report) is None

    def test_remediation_without_nested_heading_returns_none(self) -> None:
        report = (
            "# Drift Report\n\n## Remediation Suggestions\n"
            "General suggestions but no Out-of-Scope subsection.\n"
        )
        assert mod.extract_out_of_scope_section(report) is None


# --------------------------------------------------------------------------
# parse_candidates
# --------------------------------------------------------------------------


class TestParseCandidates:
    def test_bullet_em_dash(self) -> None:
        section = "- `src/foo.py` — 3 new exports"
        result = mod.parse_candidates(section)
        assert result == [{"path": "src/foo.py", "evidence": "3 new exports"}]

    def test_bullet_en_dash(self) -> None:
        section = "- `src/foo.py` – 3 new exports"
        result = mod.parse_candidates(section)
        assert result == [{"path": "src/foo.py", "evidence": "3 new exports"}]

    def test_bullet_plain_hyphen(self) -> None:
        section = "- `src/foo.py` - 3 new exports"
        result = mod.parse_candidates(section)
        assert result == [{"path": "src/foo.py", "evidence": "3 new exports"}]

    def test_bullet_with_asterisk(self) -> None:
        section = "* `src/foo.py` — 3 new exports"
        result = mod.parse_candidates(section)
        assert result == [{"path": "src/foo.py", "evidence": "3 new exports"}]

    def test_multiple_bullets(self) -> None:
        section = textwrap.dedent("""
            - `src/a.py` — 5 exports
            - `lib/b.py` — 2 exports
            - `tools/c.py` — 1 export
        """).strip()
        result = mod.parse_candidates(section)
        assert len(result) == 3
        assert {c["path"] for c in result} == {"src/a.py", "lib/b.py", "tools/c.py"}

    def test_glob_path(self) -> None:
        section = "- `python/cocoindex/resources/**` — restructured public API"
        result = mod.parse_candidates(section)
        assert result == [
            {"path": "python/cocoindex/resources/**", "evidence": "restructured public API"}
        ]

    def test_table_format(self) -> None:
        section = textwrap.dedent("""
            | Path | Evidence |
            | --- | --- |
            | `src/foo.py` | 3 new exports |
            | `lib/bar.py` | 1 new export |
        """).strip()
        result = mod.parse_candidates(section)
        assert len(result) == 2
        assert result[0]["path"] == "src/foo.py"
        assert result[0]["evidence"] == "3 new exports"

    def test_empty_section(self) -> None:
        assert mod.parse_candidates("") == []
        assert mod.parse_candidates("   \n\n   ") == []

    def test_mixed_with_prose(self) -> None:
        # narrative paragraphs between bullets — only bullets match
        section = textwrap.dedent("""
            The following paths fell out of scope after refactor:

            - `src/foo.py` — 3 new exports

            Some explanation text here.

            - `lib/bar.py` — 1 new export
        """).strip()
        result = mod.parse_candidates(section)
        assert len(result) == 2


# --------------------------------------------------------------------------
# reconcile
# --------------------------------------------------------------------------


class TestReconcile:
    def test_already_in_scope(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [
            {"action": "promoted", "path": "src/foo.py"}
        ])
        brief = mod.load_brief(brief_path)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["status"] == "already-in-scope"
        assert result[0]["prior_action"] == "promoted"

    def test_pre_decided_skipped(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [
            {"action": "skipped", "path": "src/foo.py"}
        ])
        brief = mod.load_brief(brief_path)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["status"] == "pre-decided-skipped"
        assert result[0]["prior_action"] == "skipped"

    def test_pre_decided_demoted_include(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [
            {"action": "demoted-include", "path": "src/foo.py"}
        ])
        brief = mod.load_brief(brief_path)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["status"] == "pre-decided-demoted"
        assert result[0]["prior_action"] == "demoted-include"

    def test_pre_decided_demoted_exclude(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [
            {"action": "demoted-exclude", "path": "src/foo.py"}
        ])
        brief = mod.load_brief(brief_path)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["prior_action"] == "demoted-exclude"

    def test_unresolved_when_no_match(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [
            {"action": "promoted", "path": "other.py"}
        ])
        brief = mod.load_brief(brief_path)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["status"] == "unresolved"
        assert result[0]["prior_action"] is None

    def test_most_recent_action_wins(self, tmp_path: Path) -> None:
        # User promoted, then later demoted-exclude. Most-recent wins.
        brief_path = _write_brief(tmp_path, [
            {"action": "promoted", "path": "src/foo.py"},
            {"action": "demoted-exclude", "path": "src/foo.py"},
        ])
        brief = mod.load_brief(brief_path)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["status"] == "pre-decided-demoted"
        assert result[0]["prior_action"] == "demoted-exclude"

    def test_missing_scope_field(self, tmp_path: Path) -> None:
        # brief without scope — everything is unresolved
        p = tmp_path / "brief.yaml"
        p.write_text("name: x\nversion: 1.0.0\n", encoding="utf-8")
        brief = mod.load_brief(p)
        result = mod.reconcile([{"path": "src/foo.py", "evidence": "x"}], brief)
        assert result[0]["status"] == "unresolved"


# --------------------------------------------------------------------------
# dispatch end-to-end
# --------------------------------------------------------------------------


class TestDispatch:
    def test_no_report(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [])
        forge = tmp_path / "forge"
        forge.mkdir()
        result = mod.dispatch(
            forge_data_folder=forge,
            skill_name="x",
            baseline_version="1.0.0",
            brief_path=brief_path,
        )
        assert result["status"] == "no-report"
        assert result["report_path"] is None
        assert result["candidates_total"] == 0

    def test_no_candidates_when_section_missing(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [])
        forge = tmp_path / "forge"
        d = _make_report_dir(forge, "x", "1.0.0")
        _write_report(d, "drift-report-A.md", "# Drift Report\n\nNo out-of-scope.\n")
        result = mod.dispatch(
            forge_data_folder=forge,
            skill_name="x",
            baseline_version="1.0.0",
            brief_path=brief_path,
        )
        assert result["status"] == "no-candidates"
        assert result["report_path"].endswith("drift-report-A.md")

    def test_candidates_found_with_classification(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [
            {"action": "skipped", "path": "src/already_skipped.py"},
        ])
        forge = tmp_path / "forge"
        d = _make_report_dir(forge, "x", "1.0.0")
        _write_report(d, "drift-report-A.md", """
            # Drift Report

            ## Out-of-Scope Observations
            - `src/unresolved.py` — 3 exports
            - `src/already_skipped.py` — 2 exports
        """)
        result = mod.dispatch(
            forge_data_folder=forge,
            skill_name="x",
            baseline_version="1.0.0",
            brief_path=brief_path,
        )
        assert result["status"] == "candidates-found"
        assert result["candidates_total"] == 2
        statuses = {c["path"]: c["status"] for c in result["classified"]}
        assert statuses["src/unresolved.py"] == "unresolved"
        assert statuses["src/already_skipped.py"] == "pre-decided-skipped"
        assert result["summary"]["unresolved_count"] == 1
        assert result["summary"]["pre_decided_count"] == 1


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_no_report_exits_0(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [])
        forge = tmp_path / "forge"
        forge.mkdir()
        result = _run_cli(
            "dispatch",
            "--skill-name", "x",
            "--baseline-version", "1.0.0",
            "--forge-data-folder", str(forge),
            "--brief", str(brief_path),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "no-report"

    def test_candidates_found_via_cli(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [])
        forge = tmp_path / "forge"
        d = _make_report_dir(forge, "x", "1.0.0")
        _write_report(d, "drift-report-A.md", """
            # Report

            ## Out-of-Scope Observations
            - `src/new.py` — 1 export
        """)
        result = _run_cli(
            "dispatch",
            "--skill-name", "x",
            "--baseline-version", "1.0.0",
            "--forge-data-folder", str(forge),
            "--brief", str(brief_path),
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "candidates-found"
        assert payload["candidates_total"] == 1

    def test_missing_forge_dir_exits_1(self, tmp_path: Path) -> None:
        brief_path = _write_brief(tmp_path, [])
        result = _run_cli(
            "dispatch",
            "--skill-name", "x",
            "--baseline-version", "1.0.0",
            "--forge-data-folder", str(tmp_path / "missing"),
            "--brief", str(brief_path),
        )
        assert result.returncode == 1
        assert "not a directory" in result.stderr

    def test_missing_brief_exits_1(self, tmp_path: Path) -> None:
        forge = tmp_path / "forge"
        forge.mkdir()
        result = _run_cli(
            "dispatch",
            "--skill-name", "x",
            "--baseline-version", "1.0.0",
            "--forge-data-folder", str(forge),
            "--brief", str(tmp_path / "missing.yaml"),
        )
        assert result.returncode == 1
        assert "brief not found" in result.stderr

    def test_no_subcommand_exits_2(self) -> None:
        result = _run_cli()
        assert result.returncode == 2
