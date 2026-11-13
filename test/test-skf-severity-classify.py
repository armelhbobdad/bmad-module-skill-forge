#!/usr/bin/env python3
"""Tests for skf-severity-classify.py."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
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

    def test_a_by_eye_kind_with_a_moved_line_is_a_location_change(self):
        """#680: the map's by-eye `async_function` is the runner's `function`
        of an `async def`, so only the line is left: changed/location, LOW,
        never the CRITICAL changed/signature a raw `type` compare gave."""
        base = [_export("add", "add.py", 22, type="async_function", confidence="T1-low")]
        curr = [_export("add", "add.py", 39, signature="async def add(data, dataset_name: str = 'main'):")]
        diff = _diff(base, curr)
        assert {"transform": "export-type", "count": 1} in diff["applied_transforms"]
        (finding,) = mod.project_diff(diff)
        assert (finding["type"], finding["category"], finding["detail"]) == ("changed", "location", "line 22 -> 39")
        assert classify_all([finding])["findings"][0]["severity"] == "LOW"
        # a plain `def` is a real kind change, which stays a signature finding
        curr = [_export("add", "add.py", 39, signature="def add(data):")]
        (finding,) = mod.project_diff(_diff(base, curr))
        assert (finding["type"], finding["category"]) == ("changed", "signature")
        assert finding["detail"].startswith("type: async_function -> function")

    def test_a_collapsed_kind_beside_a_real_signature_change_reports_the_signature_only(self):
        base = [_export("add", "add.py", 22, type="async_function", signature="async def add(data):")]
        curr = [_export("add", "add.py", 22, signature="async def add(data, *, mode: str = 'soft'):")]
        diff = _diff(base, curr)
        assert [c["field"] for c in diff["changed"]] == ["signature"]
        assert {"transform": "export-type", "count": 1} in diff["applied_transforms"]
        (finding,) = mod.project_diff(diff)
        # #1131: the new keyword argument has a default, so the fields settle it
        assert (finding["type"], finding["category"]) == ("changed", "optional_parameter")
        assert "category_choices" not in finding
        assert finding["detail"].startswith("signature: ") and "type:" not in finding["detail"]

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
# #1131: a changed export's category settled by the diff's fields
# --------------------------------------------------------------------------

OPEN = ["signature", "interface_contract", "inheritance", "implementation", "style"]
# The choices of a changed export whose parameters the helper cannot read on
# one side: those its fields would have settled are offered too.
UNREAD = ["signature", "parameter_count", "parameter_type", "return_type", "interface_contract", "inheritance",
          "required_parameter", "default_value", "optional_parameter", "implementation", "style"]


def _expected(category):
    """(category, category_choices) a CHANGED row expects: OPEN or UNREAD
    is an open signature with those choices."""
    return ("signature", category) if isinstance(category, list) else (category, None)

# (id, file, baseline fields, current fields, category or the open choices,
# severity): each export is one function of `file` named `f` (`add` for the
# async one).
CHANGED = [
    ("spacing", "a.py", {"signature": "def f(a,b)"}, {"signature": "def f(a, b)"}, "whitespace", "LOW"),
    ("spacing-runs-and-params", "a.ts", {"params": ["a:  string", "b ?: number"]},
     {"params": ["a: string", "b?: number"]}, "whitespace", "LOW"),
    ("optional-keyword", "add.py", {"signature": "async def add(data):"},
     {"signature": "async def add(data, *, mode: str = 'soft'):"}, "optional_parameter", "MEDIUM"),
    ("optional-ts", "a.ts", {"params": ["a: string"]}, {"params": ["a: string", "b?: number"]},
     "optional_parameter", "MEDIUM"),
    ("optional-star-args", "a.py", {"params": ["a"]}, {"params": ["a", "*args"]}, "optional_parameter", "MEDIUM"),
    ("optional-rest", "a.ts", {"signature": "export function f(a: string): void {"},
     {"signature": "export function f(a: string, ...more: string[]): void {"}, "optional_parameter", "MEDIUM"),
    ("removed-and-added", "a.py", {"signature": "def f(a, b)"}, {"signature": "def f(a, c)"},
     "parameter_count", "CRITICAL"),
    ("removed-param", "a.py", {"params": ["a: int", "b: int"]}, {"params": ["a: int"]}, "parameter_count", "CRITICAL"),
    ("retyped", "a.py", {"params": ["a: int"]}, {"params": ["a: str"]}, "parameter_type", "CRITICAL"),
    ("retyped-ts", "a.ts", {"signature": "export function f(a: string): void {"},
     {"signature": "export function f(a: number): void {"}, "parameter_type", "CRITICAL"),
    ("return", "a.ts", {"signature": "export function f(a: string): void {"},
     {"signature": "export function f(a: string): number {"}, "return_type", "CRITICAL"),
    ("return-field", "a.py", {"return_type": "int"}, {"return_type": "str"}, "return_type", "CRITICAL"),
    ("return-python", "a.py", {"signature": "def f(a) -> int:"}, {"signature": "def f(a) -> str:"},
     "return_type", "CRITICAL"),
    ("required", "a.py", {"signature": "def f(a):"}, {"signature": "def f(a, b):"}, "required_parameter", "HIGH"),
    ("required-ts", "a.ts", {"params": ["a: string"]}, {"params": ["a: string", "b: number"]},
     "required_parameter", "HIGH"),
    ("default", "a.py", {"params": ["mode: str = 'r'"]}, {"params": ["mode: str = 'w'"]}, "default_value", "HIGH"),
    ("default-set", "a.py", {"signature": "def f(a):"}, {"signature": "def f(a=1):"}, "default_value", "HIGH"),
    ("default-dropped", "a.ts", {"params": ["a: string = 'x'"]}, {"params": ["a: string"]}, "default_value", "HIGH"),
    # a removed parameter outranks a new optional one: the most severe holds first
    ("removed-beats-optional", "a.py", {"signature": "def f(a, b):"}, {"signature": "def f(a, c=1):"},
     "parameter_count", "CRITICAL"),
    # #1131 review 1: each rule outranks the ones after it
    ("retyped-beats-optional", "a.py", {"signature": "def f(a: int):"}, {"signature": "def f(a: str, b=None):"},
     "parameter_type", "CRITICAL"),
    ("return-beats-required", "a.py", {"signature": "def f(a) -> int:"}, {"signature": "def f(a, b) -> str:"},
     "return_type", "CRITICAL"),
    ("default-beats-optional", "a.py", {"signature": "def f(a=1):"}, {"signature": "def f(a=2, b=None):"},
     "default_value", "HIGH"),
    # a quoted literal keeps its spaces: a changed string default is no spacing change
    ("literal", "a.py", {"signature": "def f(s, sep=' '):"}, {"signature": "def f(s, sep=''):"}, "default_value",
     "HIGH"),
    ("literal-comma", "a.py", {"signature": "def f(s, sep=', '):"}, {"signature": "def f(s, sep=','):"},
     "default_value", "HIGH"),
    ("literal-params", "a.py", {"params": ["sep: str = ', '"]}, {"params": ["sep: str = ','"]}, "default_value",
     "HIGH"),
    ("literal-ts", "a.ts", {"signature": "export function f(sep = ' '): void {"},
     {"signature": "export function f(sep = ''): void {"}, "default_value", "HIGH"),
    ("spacing-beside-literal", "a.py", {"signature": "def f(s, sep = ' ' ):"}, {"signature": "def f(s,sep=' '):"},
     "whitespace", "LOW"),
    # a Rust ' opens a lifetime, not a literal
    ("spacing-rust-lifetime", "a.rs", {"signature": "pub fn f<'a>(x: &'a  str, y:  u8) -> &'a str {"},
     {"signature": "pub fn f<'a>(x: &'a str, y: u8) -> &'a str {"}, "whitespace", "LOW"),
    # a parameter made required or optional with its default unchanged
    ("made-required", "a.ts", {"signature": "export function f(a?: string): void {"},
     {"signature": "export function f(a: string, b?: number): void {"}, "required_parameter", "HIGH"),
    ("made-required-alone", "a.ts", {"params": ["a?: string"]}, {"params": ["a: string"]}, "required_parameter",
     "HIGH"),
    ("made-optional", "a.ts", {"params": ["a: string", "b: number"]}, {"params": ["a: string", "b?: number"]},
     "optional_parameter", "MEDIUM"),
    # by position outside Python: a Go parameter the map writes by its type alone
    ("go-by-type", "a.go", {"params": ["int"]}, {"params": ["int", "int"]}, "required_parameter", "HIGH"),
    ("open-kind", "add.py", {"type": "async_function"}, {"signature": "def add(data):"}, OPEN, "CRITICAL"),
    ("open-reorder", "a.py", {"signature": "def f(a, b):"}, {"signature": "def f(b, a):"}, OPEN, "CRITICAL"),
    # a reorder, a move to keyword-only or positional-only, or a kept
    # parameter's place shifted, beside a new optional parameter
    ("open-reorder-and-optional", "a.py", {"signature": "def f(a, b):"}, {"signature": "def f(b, a, c=None):"},
     OPEN, "CRITICAL"),
    # #1131 review 2: the open check outranks a new required parameter and a changed default
    ("open-reorder-and-required", "a.py", {"signature": "def f(a, b):"}, {"signature": "def f(b, a, c):"}, OPEN,
     "CRITICAL"),
    ("open-reorder-and-default", "a.py", {"signature": "def f(a=1, b=1):"}, {"signature": "def f(b=1, a=2):"},
     OPEN, "CRITICAL"),
    # #1131 review 2: outside Python a kept place whose name changed is a rename, a swap or a shift
    ("open-shifted-ts", "a.ts", {"signature": "export function f(a: string, b?: string): void {"},
     {"signature": "export function f(a: string, c?: string, b?: string): void {"}, OPEN, "CRITICAL"),
    ("open-shifted-js", "a.js", {"signature": "export function f(a, b = 1) {"},
     {"signature": "export function f(a, c = 2, b = 1) {"}, OPEN, "CRITICAL"),
    ("open-swap-go", "a.go", {"signature": "func f(a int, b int) {"}, {"signature": "func f(b int, a int, c ...int) {"},
     OPEN, "CRITICAL"),
    ("open-rename-and-required-rust", "a.rs", {"signature": "pub fn f(a: u32) {"},
     {"signature": "pub fn f(b: u32, c: u32) {"}, OPEN, "CRITICAL"),
    # #1131 review 2: a Python parameter no caller passes by name keeps its slot when renamed
    ("open-star-args-renamed", "a.py", {"signature": "def f(a, *args):"}, {"signature": "def f(a, *rest):"}, OPEN,
     "CRITICAL"),
    ("open-kwargs-renamed", "a.py", {"signature": "def f(a, **kwargs):"}, {"signature": "def f(a, **options):"},
     OPEN, "CRITICAL"),
    ("open-positional-only-renamed", "a.py", {"signature": "def f(a, /, b):"}, {"signature": "def f(x, /, b):"},
     OPEN, "CRITICAL"),
    ("optional-beside-positional-only-renamed", "a.py", {"signature": "def f(a, /):"},
     {"signature": "def f(x, /, b=1):"}, "optional_parameter", "MEDIUM"),
    ("star-args-gone", "a.py", {"signature": "def f(a, *args):"}, {"signature": "def f(a):"}, "parameter_count",
     "CRITICAL"),
    ("star-args-to-kwargs", "a.py", {"signature": "def f(a, *args):"}, {"signature": "def f(a, **args):"},
     "parameter_count", "CRITICAL"),
    # #1131 review 2: a quoted Python annotation names the type it quotes
    ("open-quoted-annotation", "a.py", {"signature": "def f(a: 'Node') -> 'Node':"},
     {"signature": "def f(a: Node) -> Node:"}, OPEN, "CRITICAL"),
    ("open-quoted-return", "a.py", {"signature": "def f(a) -> 'pkg.Node':"}, {"signature": "def f(a) -> pkg.Node:"},
     OPEN, "CRITICAL"),
    ("open-quoted-in-subscript", "a.py", {"signature": "def f(b: Optional['Node'] = None):"},
     {"signature": "def f(b: Optional[Node] = None):"}, OPEN, "CRITICAL"),
    ("quoted-retyped", "a.py", {"signature": "def f(a: 'Node'):"}, {"signature": "def f(a: Leaf):"},
     "parameter_type", "CRITICAL"),
    ("literal-type-ts", "a.ts", {"signature": "export function f(a: 'x' | 'y'): void {"},
     {"signature": "export function f(a: x | y): void {"}, "parameter_type", "CRITICAL"),
    # #1131 review 3: a Python type compares as Python reads it, so another
    # spelling of the same type (a ruff or pyupgrade fix) settles nothing
    ("open-optional-as-union", "a.py", {"signature": "def f(a: Optional[int] = None):"},
     {"signature": "def f(a: int | None = None):"}, OPEN, "CRITICAL"),
    ("open-union-order", "a.py", {"signature": "def f(a: Union[int, str]):"}, {"signature": "def f(a: str | int):"},
     OPEN, "CRITICAL"),
    ("open-generic-alias", "a.py", {"signature": "def f(a: List[int]) -> Dict[str, Tuple[int, ...]]:"},
     {"signature": "def f(a: list[int]) -> dict[str, tuple[int, ...]]:"}, OPEN, "CRITICAL"),
    ("open-quoted-whole-annotation", "a.py", {"signature": "def f(a: 'list[Node]') -> 'Optional[Node]':"},
     {"signature": "def f(a: list[Node]) -> Optional[Node]:"}, OPEN, "CRITICAL"),
    ("optional-beside-union", "a.py", {"signature": "def f(a: Optional[int] = None):"},
     {"signature": "def f(a: int | None = None, b=1):"}, "optional_parameter", "MEDIUM"),
    ("union-retyped", "a.py", {"signature": "def f(a: Optional[int] = None):"},
     {"signature": "def f(a: str | None = None):"}, "parameter_type", "CRITICAL"),
    ("literal-value-retyped", "a.py", {"signature": "def f(a: Literal['0']):"}, {"signature": "def f(a: Literal[0]):"},
     "parameter_type", "CRITICAL"),
    # a dropped default is default_value: required_parameter needs the default unchanged
    ("default-dropped-python", "a.py", {"signature": "def f(a=1):"}, {"signature": "def f(a):"}, "default_value",
     "HIGH"),
    ("open-keyword-only", "a.py", {"signature": "def f(a, b=1):"}, {"signature": "def f(a, *, b=1, c=2):"}, OPEN,
     "CRITICAL"),
    ("open-positional-only", "a.py", {"signature": "def f(a, b):"}, {"signature": "def f(a, b, /, c=1):"}, OPEN,
     "CRITICAL"),
    ("open-shifted", "a.py", {"signature": "def f(a, b=1):"}, {"signature": "def f(a, c=2, b=1):"}, OPEN,
     "CRITICAL"),
    ("open-keyword-only-params", "a.py", {"params": ["a", "b"]}, {"params": ["a", "*args", "b"]}, OPEN, "CRITICAL"),
    ("optional-keyword-only-beside", "a.py", {"signature": "def f(a, *, b=1):"},
     {"signature": "def f(a, *, c=2, b=1):"}, "optional_parameter", "MEDIUM"),
    # a rename in place where callers pass by position
    ("open-rename-ts", "a.ts", {"signature": "export function f(a: string): void {"},
     {"signature": "export function f(b: string): void {"}, OPEN, "CRITICAL"),
    ("open-rename-go", "a.go", {"signature": "func f(a int) {"}, {"signature": "func f(b int) {"}, OPEN, "CRITICAL"),
    ("open-rename-rust", "a.rs", {"signature": "pub fn f(a: u32) {"}, {"signature": "pub fn f(b: u32) {"}, OPEN,
     "CRITICAL"),
    # a parameter annotation added changes no call
    ("open-annotation-added", "a.py", {"signature": "def f(a):"}, {"signature": "def f(a: int):"}, OPEN, "CRITICAL"),
    # parameters the helper cannot read on a side
    ("open-unparsed", "a.py", {"signature": "grows(a)"}, {"signature": "grows(a, b)"}, UNREAD, "CRITICAL"),
    ("open-no-language", "a.txt", {"signature": "def f(a):"}, {"signature": "def f(a, b):"}, UNREAD, "CRITICAL"),
    ("open-vue", "a.vue", {"signature": "export function f(a) {"}, {"signature": "export function f(a, b) {"},
     UNREAD, "CRITICAL"),
    ("open-bare-star", "a.py", {"params": ["a", "b = 1"]}, {"params": ["a", "*", "b = 1", "c = 2"]}, UNREAD,
     "CRITICAL"),
    ("open-bare-slash", "a.py", {"params": ["a", "b"]}, {"params": ["a", "b", "/", "c = 1"]}, UNREAD, "CRITICAL"),
    ("return-unread-params", "a.py", {"signature": "grows(a)", "return_type": "int"},
     {"signature": "grows(a, b)", "return_type": "str"}, "return_type", "CRITICAL"),
    ("open-quoted-return-unread-params", "a.py", {"signature": "grows(a)", "return_type": "'Node'"},
     {"signature": "grows(a, b)", "return_type": "Node"}, UNREAD, "CRITICAL"),
]


def _changed_diff(file, base_fields, curr_fields):
    name = "add" if file == "add.py" else "f"
    return _diff([_export(name, file, 3, **base_fields)], [_export(name, file, 3, **curr_fields)])


class TestChangedCategory:
    @pytest.mark.parametrize("file,base,curr,expected,severity", [row[1:] for row in CHANGED],
                             ids=[row[0] for row in CHANGED])
    def test_the_fields_settle_one_category_on_every_projection(self, file, base, curr, expected, severity):
        diff = _changed_diff(file, base, curr)
        assert diff["changed"], diff
        first, second = mod.project_diff(diff), mod.project_diff(json.loads(json.dumps(diff)))
        assert first == second
        (finding,) = first
        category, choices = _expected(expected)
        assert (finding["type"], finding["category"]) == ("changed", category)
        assert finding.get("category_choices") == choices
        assert classify_all(first)["findings"][0]["severity"] == severity

    def test_a_signature_python_warns_on_leaves_stderr_empty(self, tmp_path):
        """#1131 review 3: a default such as '\\s+' makes Python's parser
        warn (a SyntaxWarning from 3.12); the projection prints nothing on
        stderr."""
        diff = _write_json(tmp_path / "structural-diff.json", _changed_diff(
            "a.py", {"signature": r"def f(text, pattern='\s+'):"}, {"signature": r"def f(text, pattern='\s+', n=0):"}))
        res = _run_cli("--from-diff", str(diff), "-o", str(tmp_path / "findings.json"))
        assert res.returncode == 0, res.stdout + res.stderr
        assert res.stderr == ""
        (finding,) = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))
        assert finding["category"] == "optional_parameter"

    def test_the_detail_lists_every_changed_item_either_way(self):
        diff = _diff([_export("f", "a.py", 3, signature="def f(a):", return_type="int")],
                     [_export("f", "a.py", 5, signature="def f(a, b):", return_type="int ")])
        (finding,) = mod.project_diff(diff)
        assert finding["category"] == "required_parameter"
        assert finding["detail"] == "signature: def f(a): -> def f(a, b):; return_type: int -> int ; line: 3 -> 5"

    def test_one_diff_grades_the_same_among_other_findings(self):
        """The matrix's same-input row: one diff whose changed exports sit
        among other buckets projects the same categories and severities
        twice over."""
        base = [_export("gone", "a.py", 1), _export("shifts", "a.py", 9)]
        curr = [_export("shifts", "a.py", 12), _export("fresh", "c.py", 3)]
        for i, (_, file, base_fields, curr_fields, _, _) in enumerate(CHANGED):
            name = "add" if file == "add.py" else "f"
            base.append(_export(name, f"x{i}/{file}", 3, **base_fields))
            curr.append(_export(name, f"x{i}/{file}", 3, **curr_fields))
        diff = _diff(base, curr)
        runs = [classify_all(mod.project_diff(json.loads(json.dumps(diff)))) for _ in range(2)]
        assert runs[0] == runs[1]
        graded = {f["file"]: (f["category"], f["severity"]) for f in runs[0]["findings"]}
        for i, row in enumerate(CHANGED):
            assert graded[f"x{i}/{row[1]}"] == (_expected(row[4])[0], row[5]), row[0]


def _projected(tmp_path, base, curr):
    diff = _write_json(tmp_path / "structural-diff.json", _diff(base, curr))
    return diff, tmp_path / "findings.json"


# An ambiguous GET (removed b/route.ts:4, added c/route.ts:6), a removed
# helper and a changed signature no field settles.
JUDGED_BASE = [_export("GET", "a/route.ts", 1), _export("GET", "b/route.ts", 4), _export("helper", "u.py", 2),
               _export("grows", "a.py", 3, signature="grows(a)")]
JUDGED_CURR = [_export("GET", "a/route.ts", 1), _export("GET", "c/route.ts", 6),
               _export("grows", "a.py", 3, signature="grows(a, b)")]


class TestJudgmentFlags:
    def _indices(self, findings):
        return {(f["type"], f["name"]): i for i, f in enumerate(findings)}

    def test_judge_lists_each_finding_left_to_judgment(self, tmp_path):
        diff, out = _projected(tmp_path, JUDGED_BASE, JUDGED_CURR)
        res = _run_cli("--from-diff", str(diff), "-o", str(out))
        assert res.returncode == 0, res.stdout + res.stderr
        line = json.loads(res.stdout)
        findings = json.loads(out.read_text(encoding="utf-8"))
        at = self._indices(findings)
        assert line["needs_judgment"] == len(line["judge"]) == 4
        assert line["judge"] == [
            {"index": at[("added", "GET")], "type": "added", "category": "export", "name": "GET",
             "file": "c/route.ts", "line": 6, "ambiguous_name": True},
            {"index": at[("removed", "GET")], "type": "removed", "category": "export", "name": "GET",
             "file": "b/route.ts", "line": 4, "category_choices": ["export", "internal_helper"],
             "ambiguous_name": True},
            {"index": at[("removed", "helper")], "type": "removed", "category": "export", "name": "helper",
             "file": "u.py", "line": 2, "category_choices": ["export", "internal_helper"]},
            {"index": at[("changed", "grows")], "type": "changed", "category": "signature", "name": "grows",
             "file": "a.py", "line": 3, "category_choices": UNREAD},
        ]

    def test_the_flags_record_the_judgment_and_a_rerun_writes_the_same_file(self, tmp_path):
        diff, out = _projected(tmp_path, JUDGED_BASE, JUDGED_CURR)
        assert _run_cli("--from-diff", str(diff), "-o", str(out)).returncode == 0
        at = self._indices(json.loads(out.read_text(encoding="utf-8")))
        flags = ["--set-category", f"{at[('removed', 'helper')]}=Internal_Helper",
                 "--set-category", f"{at[('changed', 'grows')]}=implementation",
                 "--pair-move", str(at[("removed", "GET")]), str(at[("added", "GET")])]
        res = _run_cli("--from-diff", str(diff), *flags, "-o", str(out))
        assert res.returncode == 0, res.stdout + res.stderr
        written = out.read_bytes()
        findings = json.loads(written)
        by_key = {(f["type"], f["name"]): f for f in findings}
        assert ("removed", "GET") not in by_key and ("added", "GET") not in by_key
        assert by_key[("moved", "GET")] == {"type": "moved", "category": "export", "name": "GET",
                                            "detail": "moved from b/route.ts:4 to c/route.ts:6",
                                            "file": "c/route.ts", "line": 6, "confidence": "T1"}
        assert by_key[("removed", "helper")]["category"] == "internal_helper"
        assert by_key[("changed", "grows")]["category"] == "implementation"
        line = json.loads(res.stdout)
        # judge keeps the indices the flags take, and shows each set category
        assert [(j["index"], j["category"]) for j in line["judge"]] == [
            (at[("removed", "helper")], "internal_helper"), (at[("changed", "grows")], "implementation")]
        assert line["findings"] == 3 and line["needs_judgment"] == 2
        assert _run_cli("--from-diff", str(diff), *flags, "-o", str(out)).returncode == 0
        assert out.read_bytes() == written
        graded = {f["name"]: f["severity"] for f in classify_all(findings)["findings"]}
        assert graded == {"GET": "MEDIUM", "helper": "HIGH", "grows": "MEDIUM"}

    def test_a_pair_of_two_libraries_is_refused(self):
        """#1131 review 2: one name in two libraries is two exports."""
        pair = [dict(type=f_type, category="export", name="GET", file=f"{lib}/route.ts", line=1,
                     source_library=lib, ambiguous_name=True) for f_type, lib in (("removed", "a"), ("added", "b"))]
        with pytest.raises(ValueError, match=r"^--pair-move 0 1: findings 0 and 1 differ in source_library$"):
            mod.apply_judgments(pair, pair_moves=[(0, 1)])

    def test_a_grouped_pair_keeps_its_library(self, tmp_path):
        base = [dict(_export("GET", f"{p}/route.ts", 1), source_library="lib") for p in ("a", "b")]
        curr = [dict(_export("GET", f"{p}/route.ts", 1), source_library="lib") for p in ("a", "c")]
        diff = _write_json(tmp_path / "d.json", _diff(base, curr, group_by="source_library"))
        out = tmp_path / "findings.json"
        assert _run_cli("--from-diff", str(diff), "-o", str(out)).returncode == 0
        at = self._indices(json.loads(out.read_text(encoding="utf-8")))
        res = _run_cli("--from-diff", str(diff), "--pair-move", str(at[("removed", "GET")]),
                       str(at[("added", "GET")]), "-o", str(out))
        assert res.returncode == 0, res.stdout
        (moved,) = json.loads(out.read_text(encoding="utf-8"))
        assert (moved["type"], moved["source_library"]) == ("moved", "lib")

    @pytest.mark.parametrize("flags,needle", [
        (["--set-category", "{gone}=module"], "--set-category {gone}=module: module is not one of finding {gone}'s"),
        (["--set-category", "{fresh}=export"], "--set-category {fresh}=export: finding {fresh} has no category_choices"),
        (["--set-category", "9=style"], "--set-category 9=style: index 9 is out of range"),
        (["--set-category=-1=style"], "--set-category -1=style: index -1 is out of range"),
        (["--set-category", "{gone}=export", "--set-category", "{gone}=internal_helper"],
         "--set-category {gone}=internal_helper: index {gone} is used twice"),
        (["--set-category", "{removed}=export", "--pair-move", "{removed}", "{added}"],
         "--pair-move {removed} {added}: index {removed} is used twice"),
        (["--pair-move", "{gone}", "{added}"], "--pair-move {gone} {added}: finding {gone} is not a removed finding "
                                               "with ambiguous_name"),
        (["--pair-move", "{removed}", "{gone}"], "--pair-move {removed} {gone}: finding {gone} is not an added finding "
                                                 "with ambiguous_name"),
        (["--pair-move", "{removed}", "{other}"], "--pair-move {removed} {other}: findings {removed} and {other} differ "
                                                  "in name"),
    ], ids=["outside-choices", "no-choices", "out-of-range", "negative", "set-twice", "set-and-paired",
            "removed-not-ambiguous", "added-not-ambiguous", "two-names"])
    def test_a_flag_its_rule_refuses_writes_nothing(self, tmp_path, flags, needle):
        base = [_export("GET", "a/route.ts", 1), _export("GET", "b/route.ts", 4), _export("POST", "a/route.ts", 2),
                _export("POST", "b/route.ts", 2), _export("gone", "u.py", 1)]
        curr = [_export("GET", "a/route.ts", 1), _export("GET", "c/route.ts", 6), _export("POST", "a/route.ts", 2),
                _export("POST", "c/route.ts", 2), _export("fresh", "n.py", 1)]
        diff, out = _projected(tmp_path, base, curr)
        findings = mod.project_diff(_diff(base, curr))
        at = {
            "removed": next(i for i, f in enumerate(findings) if (f["type"], f["name"]) == ("removed", "GET")),
            "added": next(i for i, f in enumerate(findings) if (f["type"], f["name"]) == ("added", "GET")),
            "other": next(i for i, f in enumerate(findings) if (f["type"], f["name"]) == ("added", "POST")),
            "gone": next(i for i, f in enumerate(findings) if f["name"] == "gone"),
            "fresh": next(i for i, f in enumerate(findings) if f["name"] == "fresh"),
        }
        res = _run_cli("--from-diff", str(diff), *(flag.format(**at) for flag in flags), "-o", str(out))
        assert res.returncode == 1, res.stdout + res.stderr
        error = json.loads(res.stdout)
        assert error["status"] == "error" and error["error"].startswith(needle.format(**at)), error
        assert not out.exists()

    @pytest.mark.parametrize("args", [
        ["x.json", "--set-category", "0=export"], ["--rules", "--pair-move", "0", "1"],
        ["--from-diff", "d.json", "--set-category", "export"], ["--from-diff", "d.json", "--set-category", "a=export"],
        ["--from-diff", "d.json", "--pair-move", "0"]],
        ids=["with-findings", "with-rules", "no-index", "index-not-a-number", "one-index"])
    def test_flags_without_the_projection_or_malformed_are_usage_errors(self, args):
        res = _run_cli(*args)
        assert res.returncode == 2, res.stdout + res.stderr

    def test_a_runner_that_cannot_load_is_an_error(self, tmp_path):
        """A changed signature reads its parts with the recipe runner beside
        the helper: one missing there stops the projection with exit 1."""
        alone = tmp_path / "scripts"
        alone.mkdir()
        shutil.copy2(SCRIPT_PATH, alone / SCRIPT_PATH.name)
        diff = _write_json(tmp_path / "d.json", _changed_diff("a.py", {"signature": "def f(a):"},
                                                              {"signature": "def f(a, b):"}))
        out = tmp_path / "findings.json"
        res = subprocess.run([sys.executable, str(alone / SCRIPT_PATH.name), "--from-diff", str(diff), "-o", str(out)],
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert res.returncode == 1, res.stdout + res.stderr
        assert json.loads(res.stdout)["error"].startswith(
            "cannot load skf-extract-public-api.py beside skf-severity-classify.py: ")
        assert "Traceback" not in res.stderr and not out.exists()
        # a diff with nothing to read never loads it
        diff = _write_json(tmp_path / "d.json", _diff([_export("f", "a.py", 3)], [_export("f", "a.py", 5)]))
        res = subprocess.run([sys.executable, str(alone / SCRIPT_PATH.name), "--from-diff", str(diff), "-o", str(out)],
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert res.returncode == 0, res.stdout + res.stderr


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

    def test_a_direct_content_fallback_row_is_classified_with_its_label(self, tmp_path):
        """#681: a Deep audit with no collection registered saves its semantic
        rows as T1-low-fallback; step 5 projects and grades them as it does
        a T2 row, the label kept."""
        semantic = _write_json(tmp_path / "semantic-findings.json", [
            {"type": "semantic", "category": "convention", "name": "errors", "detail": "now raises ValueError",
             "file": "pkg/api.py", "line": 12, "confidence": "T1-low-fallback"}])
        diff = _write_json(tmp_path / "structural-diff.json", _diff([], []))
        findings = tmp_path / "findings.json"
        res = _run_cli("--from-diff", str(diff), "--semantic", str(semantic), "-o", str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout)["sources"] == {"diff": 0, "semantic": 1}
        res = _run_cli(str(findings))
        assert res.returncode == 0, res.stdout + res.stderr
        (graded,) = json.loads(res.stdout)["findings"]
        assert (graded["confidence"], graded["file"], graded["line"]) == ("T1-low-fallback", "pkg/api.py", 12)
        assert graded["severity"] == classify_all([{**graded, "confidence": "T2"}])["findings"][0]["severity"]

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
        # #1131: a changed default settles the category, so nothing is left to judge
        assert json.loads(res.stdout) == {"status": "ok", "output": str(findings), "findings": 1,
                                          "needs_judgment": 0, "judge": [], "sources": {"diff": 1}}
        result = tmp_path / "severity.json"
        res = _run_cli(str(findings), "-o", str(result))
        assert res.returncode == 0, res.stdout
        line = json.loads(res.stdout)
        assert line["drift_score"] == "SIGNIFICANT" and line["total_findings"] == 1
        (graded,) = json.loads(result.read_text(encoding="utf-8"))["findings"]
        assert (graded["category"], graded["severity"]) == ("default_value", "HIGH")
        assert graded["detail"] == "params: (mode: str = 'r') -> (mode: str = 'w')"


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
