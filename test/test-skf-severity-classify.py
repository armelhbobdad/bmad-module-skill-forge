#!/usr/bin/env python3
"""Tests for skf-severity-classify.py."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys

import pytest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "skf_severity",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-severity-classify.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
classify_all = mod.classify_all


class TestEmptyFindings:
    """Suite 1: Empty findings."""

    def test_clean_on_empty(self):
        r = classify_all([])
        assert r["drift_score"] == "CLEAN"
        assert r["total_findings"] == 0


class TestCriticalRemovedExport:
    """Suite 2: Critical -- removed export."""

    def test_critical_score(self):
        r = classify_all([
            {"type": "removed", "category": "export", "detail": "function foo() removed"},
        ])
        assert r["drift_score"] == "CRITICAL"
        assert r["findings"][0]["severity"] == "CRITICAL"
        assert r["by_severity"]["CRITICAL"] == 1


class TestCriticalChangedSignature:
    """Suite 3: Changed signature."""

    def test_critical_on_signature_change(self):
        r = classify_all([
            {"type": "changed", "category": "signature", "detail": "param count changed"},
        ])
        assert r["drift_score"] == "CRITICAL"


class TestHighManyAddedExports:
    """Suite 4: HIGH -- >3 added exports."""

    def test_significant_score(self):
        r = classify_all([
            {"type": "added", "category": "export", "detail": "new fn 1"},
            {"type": "added", "category": "export", "detail": "new fn 2"},
            {"type": "added", "category": "export", "detail": "new fn 3"},
            {"type": "added", "category": "export", "detail": "new fn 4"},
        ])
        assert r["drift_score"] == "SIGNIFICANT"
        assert r["by_severity"]["HIGH"] == 4


class TestMediumFewAddedExports:
    """Suite 5: MEDIUM -- 1-3 added exports."""

    def test_medium_threshold(self):
        r = classify_all([
            {"type": "added", "category": "export", "detail": "new fn 1"},
            {"type": "added", "category": "export", "detail": "new fn 2"},
        ])
        assert r["by_severity"]["MEDIUM"] == 2


class TestLowConvention:
    """Suite 6: LOW -- convention changes."""

    def test_minor_score(self):
        r = classify_all([
            {"type": "changed", "category": "convention", "detail": "naming style changed"},
            {"type": "changed", "category": "comment", "detail": "docs updated"},
        ])
        assert r["drift_score"] == "MINOR"
        assert r["by_severity"]["LOW"] == 2


class TestMixedSeverities:
    """Suite 7: Mixed severities."""

    def test_critical_wins(self):
        r = classify_all([
            {"type": "removed", "category": "export", "detail": "critical"},
            {"type": "changed", "category": "implementation", "detail": "medium"},
            {"type": "changed", "category": "style", "detail": "low"},
        ])
        assert r["drift_score"] == "CRITICAL"
        assert r["findings"][0]["severity"] == "CRITICAL"
        assert r["findings"][-1]["severity"] == "LOW"


class TestSemanticFindings:
    """Suite 8: Semantic findings."""

    def test_semantic_medium_default(self):
        r = classify_all([
            {"type": "semantic", "category": "behavior", "detail": "meaning shifted"},
        ])
        assert r["findings"][0]["severity"] == "MEDIUM"


class TestMovedExports:
    """Suite 9: Moved exports."""

    def test_moved_medium(self):
        r = classify_all([
            {"type": "moved", "category": "export", "detail": "foo moved from a.ts to b.ts"},
        ])
        assert r["findings"][0]["severity"] == "MEDIUM"


class TestDeprecatedExport:
    """Suite 10: Deprecated export."""

    def test_deprecated_high(self):
        r = classify_all([
            {"type": "deprecated", "category": "export", "detail": "function bar() deprecated"},
        ])
        assert r["findings"][0]["severity"] == "HIGH"
        assert r["drift_score"] == "SIGNIFICANT"


class TestInvalidInput:
    """Suite 11: Invalid input."""

    def test_error_on_non_array(self):
        r = classify_all("not an array")
        assert r["status"] == "error"


# --------------------------------------------------------------------------
# The rule table against severity-rules.md
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-severity-classify.py"
DIFF_SCRIPT = REPO_ROOT / "src" / "shared" / "scripts" / "skf-structural-diff.py"
RULES_FILE = REPO_ROOT / "src" / "skf-audit-skill" / "references" / "severity-rules.md"
_LEVEL_RE = re.compile(r"^### (CRITICAL|HIGH|MEDIUM|LOW)\b")

diff_spec = importlib.util.spec_from_file_location("skf_diff_for_severity", DIFF_SCRIPT)
diff_mod = importlib.util.module_from_spec(diff_spec)
diff_spec.loader.exec_module(diff_mod)

def _rules_file_lines():
    """(severity, text) of each bullet under a severity heading of
    severity-rules.md, its **Impact:** line left out."""
    lines, level = [], None
    for line in RULES_FILE.read_text(encoding="utf-8").splitlines():
        heading = _LEVEL_RE.match(line)
        if heading:
            level = heading.group(1)
        elif line.startswith("## "):
            level = None
        elif level and line.startswith("- ") and not line.startswith("- **Impact:**"):
            lines.append((level, line[2:].strip()))
    return lines


RULES_FILE_LINES = _rules_file_lines()


def _grade(f_type, category, count=1):
    r = classify_all([{"type": f_type, "category": category, "count": count}])
    assert r["status"] == "ok", r
    return r["findings"][0]["severity"]


def test_the_rules_file_is_read():
    assert {level for level, _ in RULES_FILE_LINES} == set(mod.SEVERITIES)
    assert len(RULES_FILE_LINES) >= 23


@pytest.mark.parametrize(
    "severity,text", RULES_FILE_LINES,
    ids=[f"{level.lower()}-{i}" for i, (level, _) in enumerate(RULES_FILE_LINES)],
)
def test_each_rules_file_line_is_graded_by_the_helper(severity, text):
    rules = [rule for rule in mod.RULES if rule["rule"] == text]
    assert rules, f"no helper rule grades {severity}: {text}"
    for rule in rules:
        assert rule["severity"] == severity, text
        count = mod.ADDED_EXPORT_THRESHOLD + 1 if rule["above_threshold"] else 1
        for f_type in rule["types"]:
            for category in rule["categories"]:
                assert _grade(f_type, category, count) == severity, (f_type, category)


def test_every_helper_rule_is_in_the_rules_file():
    stated = set(RULES_FILE_LINES)
    for rule in mod.RULES:
        assert (rule["severity"], rule["rule"]) in stated, f"severity-rules.md must state {rule['rule']}"


def test_no_pair_reaches_two_rules_but_the_added_exports_threshold():
    for pair, rules in mod.PAIRS.items():
        if len(rules) > 1:
            assert pair == ("added", "export")
            assert sorted(r["above_threshold"] for r in rules) == [False, True]


@pytest.mark.parametrize("f_type,category", [
    ("changed", "interface"), ("renamed", "class"), ("renamed", "function"), ("renamed", "type"),
    ("removed", "function"), ("removed", "type"), ("changed", "parameter_type"),
])
def test_pairs_the_rules_state_are_critical(f_type, category):
    assert _grade(f_type, category) == "CRITICAL"


@pytest.mark.parametrize("f_type,severity", [("added", "MEDIUM"), ("changed", "MEDIUM"), ("removed", "CRITICAL")])
def test_script_asset_drift_rows_take_the_file_category(f_type, severity):
    # skf-compare-file-hashes.py's three lists each have one pair.
    assert _grade(f_type, "file") == severity


# --------------------------------------------------------------------------
# A pair no rule accepts is an error, never MEDIUM
# --------------------------------------------------------------------------


class TestUnknownPairs:
    def test_an_unknown_pair_is_an_error_naming_it(self):
        r = classify_all([
            {"type": "removed", "category": "export"},
            {"type": "changed", "category": "behavior", "detail": "x"},
        ])
        assert r["status"] == "error"
        assert r["problems"] == [{"index": 1, "type": "changed", "category": "behavior",
                                  "problem": "unknown type/category pair"}]
        assert "changed/behavior" in r["error"] and "--rules" in r["error"]

    @pytest.mark.parametrize("finding", [
        {"type": "semantic", "category": "vibes"},
        {"type": "changed"},
        {"type": "changed", "category": 3},
        "not an object",
    ], ids=["semantic-unknown", "no-category", "category-not-a-string", "not-an-object"])
    def test_findings_that_fit_no_rule(self, finding):
        r = classify_all([finding])
        assert r["status"] == "error"
        assert r["problems"][0]["index"] == 0

    def test_every_problem_is_listed(self):
        r = classify_all([{"type": "x", "category": "y"} for _ in range(12)])
        assert len(r["problems"]) == 12
        assert "and 2 more" in r["error"]

    def test_pairs_compare_case_insensitively(self):
        assert _grade("Removed", " Export ") == "CRITICAL"

    def test_the_cli_exits_1_and_names_the_pair(self, tmp_path):
        findings = _write_json(tmp_path / "findings.json", [{"type": "changed", "category": "vibes"}])
        res = _run_cli(str(findings))
        assert res.returncode == 1
        out = json.loads(res.stdout)
        assert out["status"] == "error" and "changed/vibes" in out["error"]


# --------------------------------------------------------------------------
# Counts: line-only changes, rollups, constituents
# --------------------------------------------------------------------------


class TestLocationCategory:
    def test_forty_line_only_changes_score_minor(self):
        r = classify_all([
            {"type": "changed", "category": "location", "detail": f"line {i} -> {i + 2}"} for i in range(40)
        ])
        assert r["drift_score"] == "MINOR"
        assert r["by_severity"] == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 40}
        assert {f["rule"] for f in r["findings"]} == {mod.LINE_ONLY_RULE}


class TestRollupCount:
    def test_a_rollup_of_fifteen_added_exports_grades_high(self):
        r = classify_all([
            {"type": "added", "category": "export", "count": 15, "detail": "15 new exports in src/api/"},
        ])
        assert r["findings"][0]["severity"] == "HIGH"
        assert r["drift_score"] == "SIGNIFICANT"
        assert r["by_severity"]["HIGH"] == 15
        assert r["total_findings"] == 1 and r["total_items"] == 15
        assert r["added_export_count"] == 15

    def test_a_rollup_of_three_stays_medium(self):
        r = classify_all([{"type": "added", "category": "export", "count": 3}])
        assert r["findings"][0]["severity"] == "MEDIUM"

    def test_rollups_and_single_rows_add_up(self):
        r = classify_all([
            {"type": "added", "category": "export", "count": 2},
            {"type": "added", "category": "export"},
            {"type": "added", "category": "export"},
        ])
        assert r["added_export_count"] == 4
        assert {f["severity"] for f in r["findings"]} == {"HIGH"}

    def test_by_severity_sums_to_total_items(self):
        r = classify_all([
            {"type": "removed", "category": "export", "count": 12},
            {"type": "changed", "category": "location"},
        ])
        assert r["by_severity"]["CRITICAL"] == 12
        assert sum(r["by_severity"].values()) == r["total_items"] == 13
        assert r["total_findings"] == 2

    @pytest.mark.parametrize("count", [0, -1, "3", True, 1.5, None],
                             ids=["zero", "negative", "string", "bool", "float", "null"])
    def test_a_count_must_be_a_positive_integer(self, count):
        r = classify_all([{"type": "added", "category": "export", "count": count}])
        assert r["status"] == "error"
        assert r["problems"][0]["problem"] == "count must be a positive integer"


class TestConstituent:
    def test_a_drifted_constituent_is_high(self):
        r = classify_all([{"type": "changed", "category": "constituent", "detail": "lib-a metadata hash changed"}])
        assert r["findings"][0]["severity"] == "HIGH"
        assert r["drift_score"] == "SIGNIFICANT"

    def test_a_missing_constituent_grades_below_a_drifted_one(self):
        assert _grade("removed", "constituent") == "MEDIUM"


class TestCategoryChoices:
    def test_a_category_outside_its_choices_is_an_error(self):
        r = classify_all([{"type": "removed", "category": "module", "category_choices": ["export", "internal_helper"]}])
        assert r["status"] == "error"
        assert r["problems"][0]["problem"] == "category is not one of category_choices"

    def test_a_category_from_its_choices_is_graded(self):
        r = classify_all([{"type": "removed", "category": "Internal_Helper",
                           "category_choices": ["export", "internal_helper"]}])
        assert r["findings"][0]["severity"] == "HIGH"


# --------------------------------------------------------------------------
# --from-diff: a structural diff projected into findings
# --------------------------------------------------------------------------


def _export(name, file, line, **extra):
    return {"name": name, "type": "function", "file": file, "line": line, "confidence": "T1", **extra}


def _diff(base, curr, **kwargs):
    return diff_mod.diff_inventories(base, curr, **kwargs)


class TestFromDiff:
    def test_each_bucket_gets_its_type_and_category(self):
        base = [_export("gone", "a.py", 1), _export("moves", "a.py", 5), _export("shifts", "a.py", 9),
                _export("grows", "a.py", 20, signature="grows(a)")]
        curr = [_export("moves", "b.py", 2), _export("shifts", "a.py", 12),
                _export("grows", "a.py", 20, signature="grows(a, b)"), _export("fresh", "c.py", 3)]
        findings = mod.project_diff(_diff(base, curr))
        by_name = {f["name"]: f for f in findings}
        assert (by_name["fresh"]["type"], by_name["fresh"]["category"]) == ("added", "export")
        assert (by_name["gone"]["type"], by_name["gone"]["category"]) == ("removed", "export")
        assert by_name["gone"]["category_choices"] == ["export", "internal_helper"]
        assert (by_name["moves"]["type"], by_name["moves"]["category"]) == ("moved", "export")
        assert (by_name["shifts"]["type"], by_name["shifts"]["category"]) == ("changed", "location")
        assert (by_name["grows"]["type"], by_name["grows"]["category"]) == ("changed", "signature")
        assert "style" in by_name["grows"]["category_choices"]
        for key in ("fresh", "moves", "shifts"):
            assert "category_choices" not in by_name[key]

    def test_findings_carry_file_line_and_confidence(self):
        base = [_export("moves", "a.py", 5), _export("shifts", "a.py", 9)]
        curr = [_export("moves", "b.py", 2, confidence="T1-low"), _export("shifts", "a.py", 12)]
        by_name = {f["name"]: f for f in mod.project_diff(_diff(base, curr))}
        assert (by_name["moves"]["file"], by_name["moves"]["line"], by_name["moves"]["confidence"]) == (
            "b.py", 2, "T1-low")
        assert by_name["moves"]["detail"] == "moved from a.py:5 to b.py:2"
        assert (by_name["shifts"]["file"], by_name["shifts"]["line"]) == ("a.py", 12)
        assert by_name["shifts"]["detail"] == "line 9 -> 12"

    def test_one_finding_per_changed_export(self):
        base = [_export("grows", "a.py", 20, signature="grows(a)", return_type="int")]
        curr = [_export("grows", "a.py", 22, signature="grows(a, b)", return_type="str")]
        (finding,) = mod.project_diff(_diff(base, curr))
        assert finding["detail"] == "signature: grows(a) -> grows(a, b); return_type: int -> str; line: 20 -> 22"

    def test_label_changes_are_never_findings(self):
        diff = _diff([_export("a", "a.py", 1, confidence="T1-low")], [_export("a", "a.py", 1)])
        assert diff["summary"]["label_changes"] == 1
        assert mod.project_diff(diff) == []

    def test_ambiguous_names_are_flagged(self):
        base = [_export("GET", "a/route.ts", 1), _export("GET", "b/route.ts", 1)]
        curr = [_export("GET", "a/route.ts", 1), _export("GET", "c/route.ts", 1)]
        findings = mod.project_diff(_diff(base, curr))
        assert sorted((f["type"], f["file"]) for f in findings if f.get("ambiguous_name")) == [
            ("added", "c/route.ts"), ("removed", "b/route.ts")]

    def test_an_ambiguous_pair_judged_a_move_is_one_moved_finding(self):
        base = [_export("GET", "a/route.ts", 1), _export("GET", "b/route.ts", 4)]
        curr = [_export("GET", "a/route.ts", 1), _export("GET", "c/route.ts", 6)]
        findings = mod.project_diff(_diff(base, curr))
        added = next(f for f in findings if f["type"] == "added")
        # Recorded as the docstring says: the added finding becomes the move,
        # without the flag, and the removed finding is dropped.
        judged = [{**{k: v for k, v in added.items() if k != "ambiguous_name"},
                   "type": "moved", "detail": "moved from b/route.ts:4 to c/route.ts:6"}]
        r = classify_all(judged)
        assert r["status"] == "ok" and r["findings"][0]["severity"] == "MEDIUM"
        kept_flag = [{**added, "type": "moved"}]
        r = classify_all(kept_flag)
        assert r["status"] == "error"
        assert r["problems"][0]["problem"].startswith("an ambiguous_name finding stays removed or added")

    def test_a_grouped_diff_keeps_the_library(self):
        base = [dict(_export("parse", "i.ts", 1), source_library="lib-a")]
        diff = _diff(base, [], group_by="source_library")
        (finding,) = mod.project_diff(diff)
        assert finding["source_library"] == "lib-a"

    def test_forty_line_only_changes_classify_minor(self):
        base = [_export(f"f{i}", "a.py", i * 10) for i in range(40)]
        curr = [_export(f"f{i}", "a.py", i * 10 + 3) for i in range(40)]
        r = classify_all(mod.project_diff(_diff(base, curr)))
        assert r["drift_score"] == "MINOR"
        assert r["by_severity"]["LOW"] == 40

    def test_fifteen_added_exports_classify_high(self):
        curr = [_export(f"g{i}", "api.py", i) for i in range(15)]
        r = classify_all(mod.project_diff(_diff([], curr)))
        assert r["by_severity"]["HIGH"] == 15
        assert r["drift_score"] == "SIGNIFICANT"

    def test_a_projection_classifies_as_it_stands(self):
        base = [_export("gone", "a.py", 1), _export("grows", "a.py", 3, signature="grows(a)")]
        curr = [_export("grows", "a.py", 3, signature="grows(a, b)")]
        r = classify_all(mod.project_diff(_diff(base, curr)))
        assert r["status"] == "ok"
        assert r["drift_score"] == "CRITICAL"

    @pytest.mark.parametrize("diff", [[], {"added": []}, {"status": "error", "error": "x"}],
                             ids=["array", "partial", "error-output"])
    def test_a_file_that_is_not_a_diff_is_refused(self, diff):
        with pytest.raises(ValueError, match="not a structural diff"):
            mod.project_diff(diff)


# --------------------------------------------------------------------------
# --file-drift, --constituents, --semantic, --doc-drift: the other drift sources
# --------------------------------------------------------------------------


FILE_DRIFT = {"added": ["scripts/new.sh"], "removed": ["assets/old.json"],
              "changed": [{"path": "scripts/run.sh", "stored_hash": "sha256:aa", "current_hash": "sha256:bb"}],
              "stats": {"added": 1, "removed": 1, "changed": 1, "unchanged": 4}}
FRESHNESS = {"drifted": [{"skill_name": "lib-a", "skill_path": "skills/lib-a/", "stored_hash": "sha256:aa",
                          "current_hash": "sha256:bb"}],
             "fresh": [{"skill_name": "lib-b"}],
             "missing": [{"skill_name": "lib-c", "skill_path": "skills/lib-c/", "stored_hash": "sha256:cc",
                          "reason": "metadata-not-found"}],
             "skipped_null_hash": [{"skill_name": "lib-d"}],
             "stats": {"total": 4, "drifted": 1, "fresh": 1, "missing": 1, "skipped_null_hash": 1}}
# A skf-detect-docs.py compare-hashes result: a docs-only skill's whole drift.
DOC_DRIFT = {"changed": [{"url": "https://docs.example.com/api", "old_hash": "sha256:aa", "new_hash": "sha256:bb"}],
             "unchanged": [{"url": "https://docs.example.com/"}],
             "fetch_failed": [{"url": "https://docs.example.com/gone", "old_hash": "sha256:cc", "reason": "HTTP 404"}],
             "skipped_null_hash": [{"url": "https://docs.example.com/new"}],
             "stats": {"total_tracked": 4, "changed": 1, "unchanged": 1, "fetch_failed": 1,
                       "skipped_null_hash": 1}}


class TestOtherSources:
    def test_file_drift_rows_take_the_file_category(self):
        findings = mod.project_file_drift(FILE_DRIFT)
        assert [(f["type"], f["category"], f["name"], f["file"]) for f in findings] == [
            ("added", "file", "scripts/new.sh", "scripts/new.sh"),
            ("removed", "file", "assets/old.json", "assets/old.json"),
            ("changed", "file", "scripts/run.sh", "scripts/run.sh")]
        assert findings[2]["detail"] == "content sha256:aa -> sha256:bb"
        assert all(f["line"] is None and f["confidence"] is None for f in findings)
        assert [f["severity"] for f in classify_all(findings)["findings"]] == ["CRITICAL", "MEDIUM", "MEDIUM"]

    def test_drifted_and_missing_constituents_are_findings(self):
        findings = mod.project_constituents(FRESHNESS)
        assert [(f["type"], f["category"], f["name"], f["file"], f["detail"]) for f in findings] == [
            ("changed", "constituent", "lib-a", "skills/lib-a/", "metadata.json sha256:aa -> sha256:bb"),
            ("removed", "constituent", "lib-c", "skills/lib-c/", "metadata-not-found")]
        r = classify_all(findings)
        assert r["by_severity"] == {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 1, "LOW": 0}

    def test_semantic_findings_are_kept_as_written(self):
        rows = [{"type": "semantic", "category": "convention", "name": "errors", "detail": "now raises",
                 "file": None, "line": None, "confidence": "T2"}]
        assert mod.project_semantic(rows) == rows
        with pytest.raises(ValueError, match="not a semantic findings file"):
            mod.project_semantic([{"type": "added", "category": "export"}])

    def test_only_a_changed_document_is_a_finding(self):
        """Doc drift is a docs-only skill's whole drift: each changed document
        is changed/doc_source, graded HIGH, so the score is SIGNIFICANT and
        report.md routes to update-skill; an unreachable or never-hashed
        document is not drift."""
        findings = mod.project_doc_drift(DOC_DRIFT)
        assert [(f["type"], f["category"], f["name"], f["file"], f["detail"]) for f in findings] == [
            ("changed", "doc_source", "https://docs.example.com/api", "https://docs.example.com/api",
             "content sha256:aa -> sha256:bb")]
        assert findings[0]["line"] is None and findings[0]["confidence"] is None
        r = classify_all(findings)
        assert (r["drift_score"], r["by_severity"]["HIGH"]) == ("SIGNIFICANT", 1)
        assert r["findings"][0]["rule"] == mod.DOC_SOURCE_RULE

    def test_no_changed_document_is_clean(self):
        unchanged = {**DOC_DRIFT, "changed": []}
        assert classify_all(mod.project_doc_drift(unchanged))["drift_score"] == "CLEAN"

    @pytest.mark.parametrize("project,data", [
        (mod.project_file_drift, {"added": [], "removed": []}),
        (mod.project_constituents, {"drifted": []}),
        (mod.project_constituents, [FRESHNESS]),
        (mod.project_doc_drift, {"changed": []}),
        (mod.project_doc_drift, FILE_DRIFT),
    ], ids=["file-drift-partial", "constituents-partial", "constituents-array", "doc-drift-partial",
            "doc-drift-file-drift"])
    def test_a_file_that_is_not_its_source_is_refused(self, project, data):
        with pytest.raises(ValueError, match="^not a "):
            project(data)

    def test_sources_come_in_order_after_the_diff(self, tmp_path):
        diff = _write_json(tmp_path / "structural-diff.json", _diff([_export("gone", "a.py", 1)], []))
        drift = _write_json(tmp_path / "file-drift.json", FILE_DRIFT)
        semantic = _write_json(tmp_path / "semantic-findings.json", [
            {"type": "semantic", "category": "pattern", "name": "retry", "detail": "x"}])
        findings = tmp_path / "findings.json"
        res = _run_cli("--from-diff", str(diff), "--file-drift", str(drift), "--semantic", str(semantic),
                       "-o", str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        line = json.loads(res.stdout)
        assert line["sources"] == {"diff": 1, "file_drift": 3, "semantic": 1}
        written = json.loads(findings.read_text(encoding="utf-8"))
        assert [f["category"] for f in written] == ["export", "file", "file", "file", "pattern"]

    def test_an_absent_optional_file_is_skipped(self, tmp_path):
        diff = _write_json(tmp_path / "structural-diff.json", _diff([], []))
        res = _run_cli("--from-diff", str(diff), "--file-drift", str(tmp_path / "file-drift.json"),
                       "--semantic", str(tmp_path / "semantic-findings.json"))
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout) == []

    def test_an_absent_diff_is_an_error(self, tmp_path):
        res = _run_cli("--from-diff", str(tmp_path / "structural-diff.json"),
                       "--file-drift", str(_write_json(tmp_path / "file-drift.json", FILE_DRIFT)))
        assert res.returncode == 1
        assert "structural-diff.json" in json.loads(res.stdout)["error"]

    def test_constituents_alone_project_a_compose_stack(self, tmp_path):
        freshness = _write_json(tmp_path / "constituent-freshness.json", FRESHNESS)
        findings = tmp_path / "findings.json"
        res = _run_cli("--constituents", str(freshness), "-o", str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout)["sources"] == {"constituents": 2}
        r = classify_all(json.loads(findings.read_text(encoding="utf-8")))
        assert (r["drift_score"], r["by_severity"]["HIGH"]) == ("SIGNIFICANT", 1)

    def test_doc_drift_alone_projects_a_docs_only_skill(self, tmp_path):
        docs = _write_json(tmp_path / "doc-drift.json", DOC_DRIFT)
        findings = tmp_path / "findings.json"
        res = _run_cli("--doc-drift", str(docs), "-o", str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout)["sources"] == {"doc_drift": 1}
        res = _run_cli(str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout)["drift_score"] == "SIGNIFICANT"

    def test_no_source_file_is_an_error(self, tmp_path):
        res = _run_cli("--constituents", str(tmp_path / "constituent-freshness.json"))
        assert res.returncode == 1
        assert json.loads(res.stdout)["error"].startswith("none of the source files exists")

    def test_a_bad_source_file_is_named(self, tmp_path):
        bad = tmp_path / "file-drift.json"
        bad.write_bytes(b"{not json")
        res = _run_cli("--file-drift", str(bad))
        assert res.returncode == 1
        assert json.loads(res.stdout)["error"].startswith(str(bad))

    def test_an_output_that_cannot_be_written_says_so(self, tmp_path):
        diff = _write_json(tmp_path / "structural-diff.json", _diff([], []))
        res = _run_cli("--from-diff", str(diff), "-o", str(tmp_path / "absent" / "findings.json"))
        assert res.returncode == 1
        assert json.loads(res.stdout)["error"].startswith("Cannot write output")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, encoding="utf-8", input=stdin, timeout=60,
    )


def _write_json(path, data):
    path.write_bytes(json.dumps(data).encode("utf-8"))
    return path


QUOTED = "signature: f(a: str = 'x') -> f(a: str = 'x', b: str = \"y\"); it's quoted"


class TestQuotesSurvive:
    def test_a_quoted_detail_reaches_the_helper_through_a_file(self, tmp_path):
        findings = _write_json(tmp_path / "findings.json", [
            {"type": "changed", "category": "signature", "detail": QUOTED}])
        res = _run_cli(str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout)["findings"][0]["detail"] == QUOTED

    def test_stdin_still_reads_a_quoted_detail(self):
        res = _run_cli("-", stdin=json.dumps([{"type": "changed", "category": "signature", "detail": QUOTED}]))
        assert res.returncode == 0
        assert json.loads(res.stdout)["findings"][0]["detail"] == QUOTED

    def test_an_inline_array_still_works(self):
        res = _run_cli('[{"type": "removed", "category": "export"}]')
        assert res.returncode == 0
        assert json.loads(res.stdout)["drift_score"] == "CRITICAL"

    def test_diff_to_findings_to_result_through_files(self, tmp_path):
        base = _write_json(tmp_path / "provenance-map.json", {"entries": [
            {"export_name": "open", "export_type": "function", "source_file": "io.py", "source_line": 3,
             "params": ["mode: str = \"r\""]}]})
        curr = _write_json(tmp_path / "extraction-snapshot.json", {"exports": [
            {"name": "open", "type": "function", "file": "io.py", "line": 3, "params": ["mode: str = 'w'"]}]})
        diff = tmp_path / "structural-diff.json"
        ran = subprocess.run([sys.executable, str(DIFF_SCRIPT), str(base), str(curr), "-o", str(diff)],
                             capture_output=True, text=True, timeout=60)
        assert ran.returncode == 1, ran.stdout + ran.stderr
        findings = tmp_path / "findings.json"
        res = _run_cli("--from-diff", str(diff), "-o", str(findings))
        assert res.returncode == 0, res.stdout
        assert json.loads(res.stdout) == {"status": "ok", "output": str(findings), "findings": 1,
                                          "needs_judgment": 1, "sources": {"diff": 1}}
        result = tmp_path / "severity.json"
        res = _run_cli(str(findings), "-o", str(result))
        assert res.returncode == 0, res.stdout
        line = json.loads(res.stdout)
        assert line["drift_score"] == "CRITICAL" and line["total_findings"] == 1
        detail = json.loads(result.read_text(encoding="utf-8"))["findings"][0]["detail"]
        assert detail == "params: (mode: str = 'r') -> (mode: str = 'w')"


class TestCli:
    def test_rules_json_lists_every_rule(self):
        res = _run_cli("--rules")
        assert res.returncode == 0
        out = json.loads(res.stdout)
        assert out["added_export_threshold"] == 3
        assert [r["rule"] for r in out["rules"]] == [r["rule"] for r in mod.RULES]
        high = next(r for r in out["rules"] if r["severity"] == "HIGH" and r["types"] == ["added"])
        assert high["added_exports"] == "more than 3"

    def test_rules_markdown_is_a_table_row_per_rule(self):
        res = _run_cli("--rules", "--format", "markdown")
        assert res.returncode == 0
        lines = res.stdout.strip().splitlines()
        assert lines[0] == "| Severity | Types | Categories | Rule |"
        assert len(lines) == 2 + len(mod.RULES)
        assert "| CRITICAL | `changed` | `inheritance`, `interface`, `interface_contract` |" in res.stdout

    @pytest.mark.parametrize("args", [[], ["x.json", "--rules"], ["--from-diff", "d.json", "--rules"],
                                      ["x.json", "--format", "markdown"], ["x.json", "--constituents", "c.json"]],
                             ids=["none", "findings-and-rules", "diff-and-rules", "format-without-rules",
                                  "findings-and-constituents"])
    def test_usage_errors_exit_2(self, args):
        assert _run_cli(*args).returncode == 2

    def test_invalid_json_exits_1(self, tmp_path):
        bad = tmp_path / "findings.json"
        bad.write_bytes(b"[{not json")
        res = _run_cli(str(bad))
        assert res.returncode == 1
        assert json.loads(res.stdout)["status"] == "error"

    def test_a_non_diff_file_exits_1(self, tmp_path):
        res = _run_cli("--from-diff", str(_write_json(tmp_path / "d.json", [1, 2])))
        assert res.returncode == 1
        assert "not a structural diff" in json.loads(res.stdout)["error"]

    def test_a_missing_file_exits_1(self, tmp_path):
        res = _run_cli(str(tmp_path / "absent.json"))
        assert res.returncode == 1

    def test_help_prints_the_contract(self):
        res = _run_cli("--help")
        assert res.returncode == 0, res.stderr
        for section in ("--from-diff DIFF:",
                        "--file-drift FILE, --constituents FILE, --semantic FILE, --doc-drift FILE:",
                        "category_choices", "ambiguous_name", "--rules:", "Exit codes:"):
            assert section in res.stdout, section
