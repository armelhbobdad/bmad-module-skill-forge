#!/usr/bin/env python3
"""Tests for reconcile-coverage.py (skf-test-skill coverage-check.md §2c).

Covers the four §2c branches:
  - "barrel"  (enumerated intersection): Documented / Missing / Stale / coverage
  - "scalar"  (effective_denominator: the named surface set's documented, missing
               and stale names on a surface read from the source, #791 and #792;
               else a looked-up numerator and no Stale)
  - "stack"   (composition-surface looked-up numerator, empty barrel)
  - "docsOnly" (#540: documentation completeness over the inventory)
Plus method-exclusion, dedup, rounding, validation, the whole-name lookup
(`get` is found in neither `target` nor `getAll`), the run-folder file flags
(an extraction surface whose internal recipe matches never count), the
subprocess CLI (exit codes + JSON-on-stdout contract), and `render`, the
Coverage Analysis section coverage-check.md §5 writes unchanged, pinned by a
golden output.
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = (
    REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "reconcile-coverage.py"
)

spec = importlib.util.spec_from_file_location("reconcile_coverage", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
reconcile = mod.reconcile


# --------------------------------------------------------------------------
# Barrel branch (enumerated intersection)
# --------------------------------------------------------------------------


def test_barrel_split_body_intersection():
    """Split-body fixture from the brief: documented=[a,b,c,x] (+ one method,
    dropped), barrel=[a,b,c,d,e] -> Documented=3, Missing=[d,e], Stale=[x],
    exportCoverage=60.0."""
    out = reconcile(
        {
            "denominatorSource": "barrel",
            "exports": [
                {"name": "a", "kind": "function"},
                {"name": "b", "kind": "class"},
                {"name": "c", "kind": "type"},
                {"name": "x", "kind": "constant"},
                {"name": "helper", "kind": "method"},  # must be dropped
            ],
            "barrelSet": ["a", "b", "c", "d", "e"],
        }
    )
    assert out["branch"] == "enumerated"
    assert out["documented"] == 3
    assert out["missing"] == ["d", "e"]
    assert out["stale"] == ["x"]
    assert out["missingCount"] == 2
    assert out["staleCount"] == 1
    assert out["staleApplicable"] is True
    assert out["denominator"] == 5
    assert out["exportCoverage"] == 60.0


def test_barrel_method_excluded_from_documented_set():
    """A method whose name matches a barrel export is NOT counted as documented
    (methods roll up under their type, not top-level barrel exports)."""
    out = reconcile(
        {
            "denominatorSource": "barrel",
            "exports": [
                {"name": "a", "kind": "function"},
                {"name": "onlyAsMethod", "kind": "method"},
            ],
            "barrelSet": ["a", "onlyAsMethod"],
        }
    )
    # onlyAsMethod is dropped from documented_set -> it is Missing, not Documented.
    assert out["documented"] == 1
    assert out["missing"] == ["onlyAsMethod"]
    assert out["stale"] == []


def test_barrel_dedup_of_documented_names():
    """Duplicate documented names collapse to one before intersection."""
    out = reconcile(
        {
            "denominatorSource": "barrel",
            "exports": [
                {"name": "a", "kind": "function"},
                {"name": "a", "kind": "function"},  # duplicate
                {"name": "b", "kind": "type"},
            ],
            "barrelSet": ["a", "b", "c"],
        }
    )
    assert out["documented"] == 2
    assert out["missing"] == ["c"]
    assert out["stale"] == []
    assert out["denominator"] == 3


def test_barrel_set_from_per_file_union():
    """barrel_set is the union of exports_found[] across per-file results when
    no explicit barrelSet is supplied; the union de-duplicates."""
    out = reconcile(
        {
            "denominatorSource": "barrel",
            "exports": [{"name": "a", "kind": "function"}],
            "perFileResults": [
                {"exports_found": ["a", "b"]},
                {"exports_found": ["b", "c"]},  # b duplicated across files
            ],
        }
    )
    assert out["denominator"] == 3  # {a, b, c}
    assert out["documented"] == 1
    assert sorted(out["missing"]) == ["b", "c"]


def test_barrel_full_coverage_rounds_clean():
    out = reconcile(
        {
            "denominatorSource": "barrel",
            "exports": [
                {"name": "a", "kind": "function"},
                {"name": "b", "kind": "function"},
                {"name": "c", "kind": "function"},
            ],
            "barrelSet": ["a", "b", "c"],
        }
    )
    assert out["documented"] == 3
    assert out["exportCoverage"] == 100.0
    assert out["missing"] == []
    assert out["stale"] == []


def test_barrel_empty_barrel_is_error():
    out = reconcile(
        {
            "denominatorSource": "barrel",
            "exports": [{"name": "a", "kind": "function"}],
            "barrelSet": [],
        }
    )
    assert out.get("code") == "INVALID_INPUT"


# --------------------------------------------------------------------------
# Scalar branch (effective_denominator, grep numerator)
# --------------------------------------------------------------------------


def _make_skill_pkg(tmp_path, skill_md_text, refs=None):
    (tmp_path / "SKILL.md").write_text(skill_md_text, encoding="utf-8")
    if refs:
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        for name, text in refs.items():
            (refs_dir / name).write_text(text, encoding="utf-8")
    return str(tmp_path)


def test_scalar_grep_numerator(tmp_path):
    """effective_denominator=10, 7 of the documented names appear across
    SKILL.md ∪ references -> Documented=7, Missing=3, no Stale, coverage=70.0."""
    documented = [f"exp{i}" for i in range(1, 11)]  # exp1..exp10
    # 7 present: exp1..exp5 in SKILL.md, exp6/exp7 in a reference file.
    pkg = _make_skill_pkg(
        tmp_path,
        skill_md_text="uses exp1 exp2 exp3 exp4 exp5 here",
        refs={"api.md": "reference documents exp6 and exp7 too"},
    )
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "exports": [{"name": n, "kind": "function"} for n in documented],
            "denominatorValue": 10,
            "skillPackagePath": pkg,
        }
    )
    assert out["branch"] == "scalar"
    assert out["documented"] == 7
    assert out["missingCount"] == 3
    assert out["missing"] == []
    assert out["stale"] == []
    assert out["staleApplicable"] is False
    assert out["denominator"] == 10
    assert out["exportCoverage"] == 70.0


def test_scalar_excludes_methods_before_grep(tmp_path):
    """Methods are dropped from the documented_set even in the scalar branch, so
    a method name present in the docs is not counted toward the numerator."""
    pkg = _make_skill_pkg(tmp_path, "mentions funcA and methB in prose")
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "exports": [
                {"name": "funcA", "kind": "function"},
                {"name": "methB", "kind": "method"},  # dropped
            ],
            "denominatorValue": 5,
            "skillPackagePath": pkg,
        }
    )
    assert out["documented"] == 1  # only funcA


def test_scalar_uses_injected_doc_text():
    """Doc text can be injected (grep logic is unit-testable without disk)."""
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "exports": [
                {"name": "alpha", "kind": "function"},
                {"name": "beta", "kind": "function"},
            ],
            "denominatorValue": 4,
            "skillPackagePath": "/does/not/exist",
        },
        doc_text="only alpha shows up",
    )
    assert out["documented"] == 1
    assert out["exportCoverage"] == 25.0


def test_scalar_within_denominator_reports_no_surplus():
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "exports": [{"name": n, "kind": "function"} for n in ("a", "b")],
            "denominatorValue": 4,
            "skillPackagePath": "/does/not/exist",
        },
        doc_text="a and b both appear",
    )
    assert out["numeratorSurplus"] == 0
    assert out["coverageCapped"] is False
    assert out["coverageUncapped"] == out["exportCoverage"] == 50.0


def test_scalar_surplus_is_bounded_and_reported():
    """A consumer-scoped denominator can be smaller than the documented mention
    count. The ratio is capped and the residual floored, but `documented` stays
    the true count and the overshoot is reported rather than swallowed."""
    names = [f"exp{i}" for i in range(90)]
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "exports": [{"name": n, "kind": "function"} for n in names],
            "denominatorValue": 72,
            "skillPackagePath": "/does/not/exist",
        },
        doc_text=" ".join(names),
    )
    assert out["documented"] == 90  # raw, truthful — never capped
    assert out["denominator"] == 72
    assert out["missingCount"] == 0  # floored, not -18
    assert out["numeratorSurplus"] == 18
    assert out["exportCoverage"] == 100.0  # capped, not 125.0
    assert out["coverageUncapped"] == 125.0
    assert out["coverageCapped"] is True


def test_scalar_exact_match_is_not_treated_as_surplus():
    names = ["a", "b", "c"]
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "exports": [{"name": n, "kind": "function"} for n in names],
            "denominatorValue": 3,
            "skillPackagePath": "/does/not/exist",
        },
        doc_text="a b c",
    )
    assert out["documented"] == 3
    assert out["missingCount"] == 0
    assert out["numeratorSurplus"] == 0
    assert out["coverageCapped"] is False
    assert out["exportCoverage"] == 100.0


# --------------------------------------------------------------------------
# Scalar branch over the named surface set (#791, #792)
# --------------------------------------------------------------------------

TIER_A = ["alpha", "beta", "gamma", "delta", "epsilon"]
# The whole public surface: the tier A set and a Tier B name the skill may document without it counting.
ALL_NAMES = TIER_A + ["tierB"]
DOCUMENTED = ["alpha", "beta", "gamma", "phantomOne", "phantomTwo"]


def _scalar_over_set(**overrides):
    """A tier A set the surface trusts (`setCounted`), read from the source."""
    inp = {"denominatorSource": "scalar", "denominatorValue": 5, "skillPackagePath": "/unused",
           "exports": [{"name": n, "kind": "function"} for n in DOCUMENTED],
           "barrelSet": TIER_A, "surfaceSet": "tier_a_include", "allSet": ALL_NAMES, "sourceRead": True,
           "setCounted": True}
    inp.update(overrides)
    # Every documented name is written in the skill: the lookup alone would count all five (#792).
    return reconcile(inp, doc_text=" ".join(e["name"] for e in inp["exports"]))


def _lookup(**overrides):
    """The scalar branch with no surface: today's looked-up numerator."""
    inp = {"denominatorSource": "scalar", "denominatorValue": 5, "skillPackagePath": "/unused",
           "exports": [{"name": n, "kind": "function"} for n in DOCUMENTED]}
    inp.update(overrides)
    return reconcile(inp, doc_text=" ".join(DOCUMENTED))


def test_scalar_counts_only_the_documented_names_of_its_set():
    """#792: two documented extras no longer offset two undocumented exports: the numerator counts the
    documented names the counted set holds, and the set's undocumented names are listed."""
    out = _scalar_over_set()
    assert (out["documented"], out["documentedNames"]) == (3, ["alpha", "beta", "gamma"])
    assert (out["missing"], out["missingCount"]) == (["delta", "epsilon"], 2)
    assert (out["denominator"], out["exportCoverage"], out["numeratorSource"]) == (5, 60.0, "surface")
    assert (out["surfaceSet"], out["surfaceSetSize"], out["warnings"]) == ("tier_a_include", 5, [])


def test_scalar_reports_the_documented_names_the_source_does_not_export_as_stale():
    """#791: the documented names the whole public surface (`allSet`) lacks are stale; a documented Tier B name
    the source exports is neither counted nor stale."""
    out = _scalar_over_set()
    assert (out["stale"], out["staleCount"], out["staleApplicable"]) == (["phantomOne", "phantomTwo"], 2, True)
    tier_b = _scalar_over_set(exports=[{"name": n, "kind": "function"} for n in DOCUMENTED + ["tierB"]])
    assert "tierB" not in tier_b["stale"] and "tierB" not in tier_b["documentedNames"]
    assert tier_b["documented"] == 3


def test_a_nested_package_name_in_the_set_is_not_stale():
    """A nested Python package's name sits in the scope sets, never in `all`: S ∪ `allSet` is the whole surface."""
    out = _scalar_over_set(barrelSet=TIER_A + ["nested"],
                           exports=[{"name": n, "kind": "function"} for n in DOCUMENTED + ["nested"]])
    assert "nested" not in out["stale"] and "nested" in out["documentedNames"]
    assert out["stale"] == ["phantomOne", "phantomTwo"]


# --------------------------------------------------------------------------
# A stale name is one the whole surface lacks, on both branches (#912)
# --------------------------------------------------------------------------


def _barrel_over_set(**overrides):
    """The barrel branch over the tier A set, the whole public surface beside it."""
    inp = {"denominatorSource": "barrel", "barrelSet": TIER_A, "allSet": ALL_NAMES,
           "exports": [{"name": n, "kind": "function"} for n in ["alpha", "beta", "tierB", "phantomOne"]]}
    inp.update(overrides)
    return reconcile(inp)


def test_barrel_a_documented_tier_b_name_is_neither_counted_nor_stale():
    """#912: the barrel branch subtracted only the set it counts, so a documented Tier B name was stale."""
    out = _barrel_over_set()
    assert (out["stale"], out["staleCount"], out["staleApplicable"]) == (["phantomOne"], 1, True)
    assert "tierB" not in out["documentedNames"] and "tierB" not in out["missing"]
    assert (out["denominator"], out["documented"], out["exportCoverage"]) == (5, 2, 40.0)
    assert out["missing"] == ["delta", "epsilon", "gamma"]


def test_barrel_without_the_whole_surface_keeps_todays_result():
    """A JSON caller that gives no `allSet` finds a stale name against the counted set alone, as before."""
    out = _barrel_over_set(allSet=None)
    assert (out["stale"], out["denominator"], out["documented"]) == (["phantomOne", "tierB"], 5, 2)
    bare = {"denominatorSource": "barrel", "barrelSet": TIER_A,
            "exports": [{"name": n, "kind": "function"} for n in ["alpha", "tierB"]]}
    assert reconcile(bare)["stale"] == ["tierB"]


def test_barrel_refuses_an_all_set_that_is_not_a_list():
    out = _barrel_over_set(allSet="alpha")
    assert out == {"error": "barrel branch: `allSet` must be a list of names", "code": "INVALID_INPUT"}
    proc = _run_cli([json.dumps({"denominatorSource": "barrel", "barrelSet": TIER_A, "allSet": "alpha"})])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["error"] == "barrel branch: `allSet` must be a list of names"


@pytest.mark.parametrize("overrides, message", [
    ({"allSet": "alpha"}, "scalar branch: `allSet` must be a list of names"),
    ({"allSet": None}, "scalar branch on a surface read from the source requires `allSet` (the surface's `all` "
                       "set) to find the stale names"),
], ids=["all-not-a-list", "no-all-set"])
def test_the_scalar_refusals_keep_their_messages(overrides, message):
    assert _scalar_over_set(**overrides) == {"error": message, "code": "INVALID_INPUT"}


# load-coverage-inputs.py surface output with a nested Python entry: `nested` keeps its record but leaves `all`,
# and `scopedOut` is a name the brief scoped out (no record, in no set).
PROBE_SURFACE = {
    "exports": [{"name": n, "kind": "function", "file": f"pkg/{n}.py", "line": 1, "origin": "extraction"}
                for n in ("alpha", "beta", "tierB", "nested")],
    "sets": {"all": ["alpha", "beta", "tierB"], "tier_a_include": ["alpha", "beta"]},
    "excluded": {"outsideScope": [{"name": "scopedOut", "file": "scripts/tool.py"}],
                 "nestedEntries": [{"entry": "pkg/api/__init__.py", "within": "pkg/__init__.py",
                                    "names": ["nested"]}]},
    "guards": {"deflation": {"applicable": True, "fires": False}},
    "denominator": {"clause": "stratified-scope", "branch": "scalar", "surfaceSet": "tier_a_include",
                    "setCounted": True},
}
PROBE_DOCUMENTED = ["alpha", "tierB", "nested", "phantom"]


def _probe(tmp_path, branch, surface_set, documented=PROBE_DOCUMENTED):
    """reconcile-coverage.py on the probe surface through the run files, as coverage-check runs it."""
    skill = tmp_path / "skill"
    skill.mkdir(exist_ok=True)
    (skill / "SKILL.md").write_bytes(" ".join(documented).encode("utf-8"))
    inventory = _write(tmp_path / "i.json", {"exports": [{"name": n, "kind": "function"} for n in documented]})
    args = ["--denominator-source", branch, "--inventory", inventory, "--surface-set", surface_set,
            "--surface", _write(tmp_path / "surface.json", PROBE_SURFACE)]
    if branch == "scalar":
        args += ["--coverage-inputs", _write(tmp_path / "ci.json", {"effectiveDenominator": 2, "stack": None}),
                 "--skill-dir", str(skill)]
    proc = _run_cli(args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("branch, surface_set, numerator", [
    ("barrel", "tier_a_include", (2, 1, ["alpha"], ["beta"])),
    ("barrel", "all", (3, 2, ["alpha", "tierB"], ["beta"])),
    ("scalar", "tier_a_include", (2, 1, ["alpha"], ["beta"])),
    ("scalar", "all", (2, 4, None, [])),
], ids=["barrel-tier-a", "barrel-all", "scalar-scope-set-lacking-nested", "scalar-all"])
def test_a_documented_tier_b_or_nested_entry_name_is_not_stale(tmp_path, branch, surface_set, numerator):
    """#912: a documented Tier B name and a nested entry's name (on an `exports` record, outside `all`) are in the
    whole surface, so neither is stale on either branch; a phantom name stays stale. The numerator is unchanged."""
    out = _probe(tmp_path, branch, surface_set)
    assert (out["stale"], out["staleCount"], out["staleApplicable"]) == (["phantom"], 1, True)
    assert (out["denominator"], out["documented"], out.get("documentedNames"), out["missing"]) == numerator


@pytest.mark.parametrize("branch, surface_set", [("barrel", "tier_a_include"), ("barrel", "all"),
                                                 ("scalar", "tier_a_include"), ("scalar", "all")])
def test_a_scoped_out_name_stays_stale(tmp_path, branch, surface_set):
    """An `excluded.outsideScope` name has no record and sits in no set: it is not part of the surface."""
    out = _probe(tmp_path, branch, surface_set, documented=PROBE_DOCUMENTED + ["scopedOut"])
    assert out["stale"] == ["phantom", "scopedOut"]


@pytest.mark.parametrize("overrides", [
    {"barrelSet": ALL_NAMES, "surfaceSet": "all", "allSet": None},
    {"barrelSet": ALL_NAMES, "surfaceSet": None, "allSet": None},
    {"setCounted": False},
], ids=["all", "null-is-all", "untrusted-scope-set"])
def test_scalar_over_all_or_an_untrusted_set_keeps_the_lookup_and_lists_stale(overrides):
    """`all` is the whole surface, not a scope set, and a set read by eye or from an incomplete extraction is
    not trusted: the looked-up numerator and the count stay, and no name is listed missing, but the stale names
    are valid against `all` on a surface read from the source."""
    out = _scalar_over_set(**overrides)
    lookup = _lookup()
    for key in ("documented", "missingCount", "exportCoverage", "numeratorSource", "missing"):
        assert out[key] == lookup[key], key
    assert (out["documented"], out["numeratorSource"], out["missing"]) == (5, "lookup", [])
    assert (out["stale"], out["staleApplicable"], out["warnings"]) == (["phantomOne", "phantomTwo"], True, [])
    assert "documentedNames" not in out and "surfaceSetSize" not in out


def test_scalar_over_all_still_takes_the_verified_numerator():
    out = _scalar_over_set(barrelSet=ALL_NAMES, surfaceSet="all", allSet=None, verifiedNumerator=2)
    assert (out["documented"], out["numeratorSource"], out["missingCount"]) == (2, "verified", 3)
    assert out["stale"] == ["phantomOne", "phantomTwo"]


def test_a_counted_set_ignores_the_verified_numerator():
    out = _scalar_over_set(verifiedNumerator=1)
    assert (out["documented"], out["numeratorSource"]) == (3, "surface")


def test_an_empty_set_falls_back_to_the_lookup_with_a_warning():
    """An empty S would read 0% by construction."""
    out = _scalar_over_set(barrelSet=[])
    assert (out["documented"], out["numeratorSource"], out["missing"]) == (5, "lookup", [])
    [warning] = out["warnings"]
    assert "`tier_a_include` set names no export" in warning
    assert out["stale"] == ["phantomOne", "phantomTwo"]


def test_scalar_warns_when_its_set_differs_from_the_stored_count():
    names = [f"name{i}" for i in range(280)]
    out = _scalar_over_set(denominatorValue=216, barrelSet=names, allSet=names,
                           exports=[{"name": n, "kind": "function"} for n in names[:200]])
    assert out["surfaceSetSize"] == 280 and out["denominator"] == 216
    [warning] = out["warnings"]
    assert "280" in warning and "216" in warning and "`tier_a_include`" in warning
    assert (out["documented"], out["missingCount"], len(out["missing"])) == (200, 16, 80)


@pytest.mark.parametrize("overrides", [{"sourceRead": False, "setCounted": False},
                                       {"sourceRead": None, "setCounted": None}, {"barrelSet": None}],
                         ids=["not-read-from-source", "no-flags", "no-set"])
def test_scalar_without_a_source_read_surface_keeps_the_lookup(overrides):
    """A surface not read from the source (States 2 and 3) names no set to count and no stale name: the lookup,
    unchanged."""
    out = _scalar_over_set(**overrides)
    assert out == _lookup()
    assert (out["documented"], out["stale"], out["staleApplicable"]) == (5, [], False)
    assert "documentedNames" not in out and "warnings" not in out


@pytest.mark.parametrize("overrides, message", [
    ({"barrelSet": "alpha"}, "`barrelSet` must be a list"),
    ({"surfaceSet": 7}, "`surfaceSet` must be a set name"),
    ({"allSet": "alpha"}, "`allSet` must be a list"),
    ({"allSet": None}, "requires `allSet`"),
], ids=["set-not-a-list", "set-name-not-a-string", "all-not-a-list", "no-all-set"])
def test_scalar_refuses_a_malformed_surface(overrides, message):
    out = _scalar_over_set(**overrides)
    assert out["code"] == "INVALID_INPUT" and message in out["error"], out


# --------------------------------------------------------------------------
# Stack branch (composition-surface grep, empty barrel)
# --------------------------------------------------------------------------


def test_stack_composition_surface_grep(tmp_path):
    """Stack: empty source barrel; numerator is grep of composition names across
    SKILL.md ∪ references; denominator is the stack_denominator."""
    pkg = _make_skill_pkg(
        tmp_path,
        skill_md_text="composes react-query and zod",
        refs={"patterns.md": "wires react-query with a custom adapter"},
    )
    out = reconcile(
        {
            "denominatorSource": "stack",
            "compositionNames": ["react-query", "zod", "trpc"],
            "denominatorValue": 3,
            "skillPackagePath": pkg,
        }
    )
    assert out["branch"] == "stack"
    assert out["documented"] == 2  # react-query + zod present; trpc absent
    assert out["missingCount"] == 1
    assert out["stale"] == []
    assert out["staleApplicable"] is False
    assert out["denominator"] == 3
    assert out["exportCoverage"] == round((2 / 3) * 100, 2)


def test_stack_ignores_exports_uses_composition_names():
    """Stack numerator comes from compositionNames, not exports[] (the stack's
    own barrel is empty by design)."""
    out = reconcile(
        {
            "denominatorSource": "stack",
            "exports": [{"name": "ignored", "kind": "function"}],
            "compositionNames": ["libX", "libY"],
            "denominatorValue": 2,
            "skillPackagePath": "/unused",
        },
        doc_text="libX and libY both appear; ignored also appears",
    )
    assert out["documented"] == 2
    assert out["exportCoverage"] == 100.0


def test_stack_surplus_is_bounded_too():
    """The stack branch shares the grep code path, so it gets the same bounds."""
    out = reconcile(
        {
            "denominatorSource": "stack",
            "compositionNames": ["libX", "libY", "libZ"],
            "denominatorValue": 2,
            "skillPackagePath": "/unused",
        },
        doc_text="libX libY libZ all appear",
    )
    assert out["documented"] == 3
    assert out["missingCount"] == 0
    assert out["numeratorSurplus"] == 1
    assert out["exportCoverage"] == 100.0
    assert out["coverageUncapped"] == 150.0
    assert out["coverageCapped"] is True


@pytest.mark.parametrize(
    "payload,doc_text",
    [
        (
            {
                "denominatorSource": "scalar",
                "exports": [{"name": f"n{i}", "kind": "function"} for i in range(9)],
                "denominatorValue": 3,
                "skillPackagePath": "/unused",
            },
            " ".join(f"n{i}" for i in range(9)),
        ),
        (
            {
                "denominatorSource": "stack",
                "compositionNames": [f"n{i}" for i in range(9)],
                "denominatorValue": 3,
                "skillPackagePath": "/unused",
            },
            " ".join(f"n{i}" for i in range(9)),
        ),
    ],
    ids=["scalar", "stack"],
)
def test_grep_branches_stay_in_compute_score_range(payload, doc_text):
    """compute-score.py rejects any category score outside 0-100, so the
    reconciler must never hand it an out-of-range exportCoverage."""
    out = reconcile(payload, doc_text=doc_text)
    assert 0 <= out["exportCoverage"] <= 100
    assert out["missingCount"] >= 0


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_deterministic_same_input_same_output():
    inp = {
        "denominatorSource": "barrel",
        "exports": [
            {"name": "c", "kind": "function"},
            {"name": "a", "kind": "function"},
            {"name": "b", "kind": "function"},
        ],
        "barrelSet": ["b", "a", "z", "y"],
    }
    first = reconcile(dict(inp))
    second = reconcile(dict(inp))
    assert first == second
    # ordering is stable/sorted regardless of input order
    assert first["missing"] == ["y", "z"]
    assert first["stale"] == ["c"]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_missing_denominator_source_is_error():
    out = reconcile({"exports": []})
    assert out.get("code") == "INVALID_INPUT"


def test_bad_denominator_source_is_error():
    out = reconcile({"denominatorSource": "bogus"})
    assert out.get("code") == "INVALID_INPUT"


def test_barrel_requires_barrel_or_perfile():
    out = reconcile({"denominatorSource": "barrel", "exports": []})
    assert out.get("code") == "INVALID_INPUT"


def test_scalar_requires_denominator_value():
    out = reconcile(
        {"denominatorSource": "scalar", "skillPackagePath": "/x", "exports": []}
    )
    assert out.get("code") == "INVALID_INPUT"


def test_scalar_rejects_bool_denominator():
    out = reconcile(
        {
            "denominatorSource": "scalar",
            "denominatorValue": True,  # bool is not a valid int denominator
            "skillPackagePath": "/x",
            "exports": [],
        }
    )
    assert out.get("code") == "INVALID_INPUT"


def test_stack_requires_composition_names():
    out = reconcile(
        {
            "denominatorSource": "stack",
            "denominatorValue": 3,
            "skillPackagePath": "/x",
        }
    )
    assert out.get("code") == "INVALID_INPUT"


# --------------------------------------------------------------------------
# CLI (subprocess) — JSON-on-stdout + exit-code contract
# --------------------------------------------------------------------------


def _run_cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_positional_json_exit0():
    payload = json.dumps(
        {
            "denominatorSource": "barrel",
            "exports": [{"name": "a", "kind": "function"}],
            "barrelSet": ["a", "b"],
        }
    )
    proc = _run_cli([payload])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["documented"] == 1
    assert out["exportCoverage"] == 50.0


def test_cli_stdin():
    payload = json.dumps(
        {
            "denominatorSource": "barrel",
            "exports": [{"name": "a", "kind": "function"}],
            "barrelSet": ["a", "b"],
        }
    )
    proc = _run_cli(["--stdin"], stdin=payload)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["denominator"] == 2


def test_cli_no_input_exit1():
    proc = _run_cli([])
    assert proc.returncode == 1


def test_cli_malformed_json_exit1():
    proc = _run_cli(["{not json"])
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_invalid_schema_exit2():
    proc = _run_cli([json.dumps({"denominatorSource": "bogus"})])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


# --------------------------------------------------------------------------
# Whole-name lookup (shared with verify-declared-numerator.py)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("doc_text, found", [
    ("call `get(url)` first", True),
    ("the target is reached", False),
    ("use getAll() instead", False),
    ("obj.get and more", True),
    ("forget it", False),
], ids=["call", "inside-target", "prefix-of-getAll", "member", "suffix"])
def test_scalar_lookup_never_matches_inside_a_longer_name(doc_text, found):
    out = reconcile(
        {"denominatorSource": "scalar", "exports": [{"name": "get", "kind": "function"}],
         "denominatorValue": 1, "skillPackagePath": "/unused"},
        doc_text=doc_text,
    )
    assert out["documented"] == (1 if found else 0)


def test_lookup_reads_skill_md_and_flat_references(tmp_path):
    (tmp_path / "references" / "deep").mkdir(parents=True)
    (tmp_path / "SKILL.md").write_bytes(b"`alpha()`\n")
    (tmp_path / "references" / "api.md").write_bytes("`b\u00e9ta`\n".encode("utf-8"))
    (tmp_path / "references" / "deep" / "x.md").write_bytes(b"`gamma`\n")
    out = reconcile({"denominatorSource": "stack", "compositionNames": ["alpha", "b\u00e9ta", "gamma"],
                     "denominatorValue": 3, "skillPackagePath": str(tmp_path)})
    assert out["documented"] == 2


# --------------------------------------------------------------------------
# docsOnly branch (#540)
# --------------------------------------------------------------------------


def test_docs_only_scores_completeness():
    exports = [
        {"name": "fmt", "kind": "function", "params": "x: str", "return_type": "str", "description": "Formats."},
        {"name": "run", "kind": "function", "params": "", "return_type": "None", "description": "Runs."},
        {"name": "go", "kind": "function", "params": "x", "description": "No return type."},
        {"name": "Cfg", "kind": "class", "description": "Config."},
        {"name": "Mode", "kind": "type", "description": ""},
        {"name": "Cfg.load", "kind": "method", "params": [], "return_type": "Cfg", "description": "Loads."},
    ]
    out = reconcile({"denominatorSource": "docsOnly", "exports": exports})
    assert (out["branch"], out["denominator"], out["documented"], out["missingCount"]) == ("docsOnly", 6, 4, 2)
    assert out["exportCoverage"] == 66.67
    assert out["incomplete"] == [{"name": "go", "kind": "function", "missing": ["return_type"]},
                                 {"name": "Mode", "kind": "type", "missing": ["description"]}]
    assert (out["staleApplicable"], out["missing"], out["stale"]) == (False, [], [])


def test_docs_only_counts_a_listed_twice_item_once():
    exports = [{"name": "a", "kind": "constant"}, {"name": "a", "kind": "constant", "description": "A."}]
    out = reconcile({"denominatorSource": "docsOnly", "exports": exports})
    assert (out["denominator"], out["documented"]) == (1, 1)


def test_docs_only_with_no_item_is_an_error():
    out = reconcile({"denominatorSource": "docsOnly", "exports": []})
    assert out.get("code") == "INVALID_INPUT"
    assert reconcile({"denominatorSource": "docsOnly"}).get("code") == "INVALID_INPUT"


# --------------------------------------------------------------------------
# Verified numerator (scalar) and the run-folder file flags
# --------------------------------------------------------------------------


def test_scalar_takes_the_verified_numerator_when_inflated():
    out = reconcile({"denominatorSource": "scalar", "exports": [{"name": "a", "kind": "function"}],
                     "denominatorValue": 10, "skillPackagePath": "/unused", "verifiedNumerator": 7},
                    doc_text="a")
    assert (out["documented"], out["missingCount"], out["numeratorSource"]) == (7, 3, "verified")


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(payload).encode("utf-8"))
    return str(path)


INVENTORY = {"exports": [{"name": "fetchData", "kind": "function"}, {"name": "helper", "kind": "function"},
                         {"name": "stale", "kind": "function"}, {"name": "Client.run", "kind": "method"}],
             "cross_check_mismatches": []}
# load-coverage-inputs.py surface output from a --mode full extraction: the
# entry points' names only; the recipe match internalThing is not in a set.
SURFACE = {"exports": [{"name": n, "kind": "function", "file": "src/index.ts", "line": 1, "origin": "extraction"}
                       for n in ("fetchData", "helper", "parse")],
           "sets": {"all": ["fetchData", "helper", "parse"], "root": ["fetchData", "parse"]},
           "excluded": {"outsideScope": [{"name": "legacy", "file": "lib/legacy.ts"}]}}


def test_cli_barrel_from_the_run_files(tmp_path):
    out_path = tmp_path / "run" / "coverage.json"
    proc = _run_cli(["--denominator-source", "barrel", "--inventory", _write(tmp_path / "inventory.json", INVENTORY),
                     "--surface", _write(tmp_path / "surface.json", SURFACE), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == out
    assert (out["documented"], out["missing"], out["stale"]) == (2, ["parse"], ["stale"])
    assert "internalThing" not in out["missing"] and "legacy" not in out["missing"]


def test_cli_surface_set_picks_the_name_set(tmp_path):
    proc = _run_cli(["--denominator-source", "barrel", "--inventory", _write(tmp_path / "i.json", INVENTORY),
                     "--surface", _write(tmp_path / "s.json", SURFACE), "--surface-set", "root"])
    assert json.loads(proc.stdout)["denominator"] == 2
    missing_set = _run_cli(["--denominator-source", "barrel", "--inventory", str(tmp_path / "i.json"),
                            "--surface", str(tmp_path / "s.json"), "--surface-set", "subpaths"])
    assert missing_set.returncode == 1 and "no name set `subpaths`" in missing_set.stderr


def test_cli_validate_inventory_result_is_accepted_as_inventory(tmp_path):
    wrapped = {"valid": True, "inventory": INVENTORY}
    proc = _run_cli(["--denominator-source", "docsOnly", "--inventory", _write(tmp_path / "i.json", wrapped)])
    assert proc.returncode == 0 and json.loads(proc.stdout)["denominator"] == 4


def test_cli_stack_from_coverage_inputs(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_bytes(b"`connect()` and `Client`\n")
    inputs = _write(tmp_path / "coverage-inputs.json",
                    {"stack": {"basis": "provenance", "denominator": 3, "compositionNames": ["Client", "connect", "x"]}})
    proc = _run_cli(["--denominator-source", "stack", "--coverage-inputs", inputs, "--skill-dir", str(skill)])
    out = json.loads(proc.stdout)
    assert (out["documented"], out["denominator"], out["missingCount"]) == (2, 3, 1)


@pytest.mark.parametrize("verified, documented", [
    ({"inflated": True, "verified": 1, "declared": 4}, 1),
    ({"inflated": False, "verified": 4, "declared": 4}, 2),
    ({"skipped": True, "inflated": False, "verified": None}, 2),
], ids=["inflated", "not-inflated", "skipped"])
def test_cli_scalar_reads_the_verified_numerator(tmp_path, verified, documented):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_bytes(b"fetchData helper\n")
    proc = _run_cli(["--denominator-source", "scalar", "--denominator-value", "4",
                     "--inventory", _write(tmp_path / "i.json", INVENTORY), "--skill-dir", str(skill),
                     "--verified", _write(tmp_path / "numerator.json", verified)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["documented"] == documented


def test_cli_scalar_takes_its_denominator_from_the_coverage_inputs(tmp_path):
    """The scalar is read from the loader's file, never typed into the command."""
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_bytes(b"fetchData helper\n")
    inventory = _write(tmp_path / "i.json", INVENTORY)
    inputs = _write(tmp_path / "coverage-inputs.json", {"effectiveDenominator": 5, "stack": None})
    proc = _run_cli(["--denominator-source", "scalar", "--coverage-inputs", inputs, "--inventory", inventory,
                     "--skill-dir", str(skill)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert (out["denominator"], out["documented"], out["missingCount"]) == (5, 2, 3)
    without = _write(tmp_path / "no-scalar.json", {"effectiveDenominator": None, "stack": None})
    proc = _run_cli(["--denominator-source", "scalar", "--coverage-inputs", without, "--inventory", inventory,
                     "--skill-dir", str(skill)])
    assert proc.returncode == 1 and "has no `effectiveDenominator`" in proc.stderr


def _scalar_surface(applicable=True, counted=True, picked="tier_a_include"):
    """load-coverage-inputs.py surface's result on the scalar branch: its tier A set, the deflation guard that
    says whether the surface was read from the source, and whether it counts the set it picked."""
    return {"exports": [{"name": n, "kind": "function", "file": "src/index.ts", "line": i}
                        for i, n in enumerate(ALL_NAMES, 1)],
            "sets": {"all": ALL_NAMES, "tier_a_include": TIER_A},
            "guards": {"deflation": {"applicable": applicable, "fires": False}},
            "denominator": {"clause": "stratified-scope", "branch": "scalar", "surfaceSet": picked,
                            "setCounted": counted}}


@pytest.mark.parametrize("surface, surface_set, expected", [
    ({}, "tier_a_include", (3, 60.0, "surface", ["delta", "epsilon"], ["phantomOne", "phantomTwo"])),
    ({"counted": False}, "tier_a_include", (5, 100.0, "lookup", [], ["phantomOne", "phantomTwo"])),
    ({}, "all", (5, 100.0, "lookup", [], ["phantomOne", "phantomTwo"])),
    ({"applicable": False, "counted": None}, "tier_a_include", (5, 100.0, "lookup", [], [])),
], ids=["counted", "untrusted", "another-set-than-picked", "not-read-from-source"])
def test_cli_scalar_counts_the_set_the_surface_trusts(tmp_path, surface, surface_set, expected):
    """#791, #792 through coverage-check's flags: the set the surface picked and trusts (`setCounted`) is counted;
    any other keeps the lookup, with the stale names whenever the surface was read from the source."""
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_bytes(" ".join(DOCUMENTED).encode("utf-8"))
    inventory = _write(tmp_path / "i.json", {"exports": [{"name": n, "kind": "function"} for n in DOCUMENTED]})
    inputs = _write(tmp_path / "coverage-inputs.json", {"effectiveDenominator": 5, "stack": None})
    out_path = tmp_path / "coverage.json"
    proc = _run_cli(["--denominator-source", "scalar", "--coverage-inputs", inputs, "--inventory", inventory,
                     "--surface", _write(tmp_path / "surface.json", _scalar_surface(**surface)),
                     "--surface-set", surface_set, "--skill-dir", str(skill), "--output", str(out_path)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert (out["documented"], out["exportCoverage"], out["numeratorSource"], out["missing"],
            out["stale"]) == expected


def test_render_draws_the_table_of_a_counted_set():
    """A scalar result that counts its set names its exports: the per-export table, and its stale count."""
    coverage = _scalar_over_set()
    text = mod.render(coverage, _scalar_surface())
    assert "No per-export table" not in text
    rows = [line for line in text.splitlines() if line.startswith("| `")]
    assert rows == [
        "| `alpha` | function | yes | unverified | src/index.ts:1 | PASS |",
        "| `beta` | function | yes | unverified | src/index.ts:2 | PASS |",
        "| `delta` | function | no | - | src/index.ts:4 | WARN |",
        "| `epsilon` | function | no | - | src/index.ts:5 | WARN |",
        "| `gamma` | function | yes | unverified | src/index.ts:3 | PASS |",
        "| `phantomOne` | - | yes | unverified | - | WARN |",
        "| `phantomTwo` | - | yes | unverified | - | WARN |",
    ]
    for line in ("- **Exports Found:** 5", "- **Documented:** 3 (60%)", "- **Missing Documentation:** 2",
                 "- **Stale Documentation:** 2, documented extras included", "| Export Coverage | 60% |"):
        assert line in text.splitlines(), line
    assert "Coverage Warnings" not in text


def test_render_lists_the_coverage_warnings():
    names = [f"name{i}" for i in range(6)]
    coverage = _scalar_over_set(barrelSet=names, allSet=names)
    text = mod.render(coverage, _scalar_surface())
    [warning] = coverage["warnings"]
    lines = text.splitlines()
    assert lines[lines.index("- **Coverage Warnings:**") + 1] == f"  - {warning}"
    # Over `all` the lookup counts: no table, the stale count still given.
    over_all = mod.render(_scalar_over_set(barrelSet=ALL_NAMES, surfaceSet="all", allSet=None), _scalar_surface())
    assert "No per-export table: the scalar denominator" in over_all
    assert "- **Stale Documentation:** 2, documented extras included" in over_all.splitlines()
    assert "Coverage Warnings" not in over_all


def test_render_lists_the_borderline_calls(tmp_path):
    """#1021: the inventory's `undecided` readings reach coverage.json on every branch, each command coverage-check
    runs reading the inventory, and render lists them, then the judges' from signatures.json, under Borderline Calls
    in the Coverage Summary, so the report names each reading the rules leave open that its verdict rests on. A
    result with none renders as before (the golden section)."""
    reader = {"export": "Symbol", "at": "SKILL.md:12",
              "rule": "A name the skill writes only in a type position is a type mention.",
              "reading": "a type mention, no entry", "other_gap": "a Medium `missing-type` gap"}
    judge = {"export": "lifespan", "at": None, "rule": "Equivalent spellings name no `Optional[X]` of a default",
             "reading": "the same type", "other_gap": "a Critical\n`signature-mismatch`"}
    inventory = _write(tmp_path / "inventory.json", {**INVENTORY, "undecided": [reader]})
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_bytes(b"fetchData helper `connect()`\n")
    inputs = _write(tmp_path / "coverage-inputs.json",
                    {"effectiveDenominator": 4, "stack": {"denominator": 2, "compositionNames": ["connect", "x"]}})
    branches = {
        "barrel": ["--surface", _write(tmp_path / "surface.json", SURFACE)],
        "scalar": ["--coverage-inputs", inputs, "--skill-dir", str(skill)],
        "stack": ["--coverage-inputs", inputs, "--skill-dir", str(skill)],
        "docsOnly": [],
    }
    for branch, flags in branches.items():
        proc = _run_cli(["--denominator-source", branch, "--inventory", inventory, *flags])
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["undecided"] == [reader], branch
    coverage = json.loads(_run_cli(["--denominator-source", "barrel", "--inventory", inventory,
                                    *branches["barrel"]]).stdout)
    lines = mod.render(coverage, SURFACE, {**RENDER_SIGNATURES, "undecided": [judge]}).splitlines()
    at = lines.index("- **Borderline Calls:**")
    assert lines[at + 1:at + 4] == [
        "  - `Symbol` (SKILL.md:12), inventory reader: a type mention, no entry; left open by: A name the skill "
        "writes only in a type position is a type mention; the other reading gives: a Medium `missing-type` gap",
        "  - `lifespan`, signature judge: the same type; left open by: Equivalent spellings name no `Optional[X]` of "
        "a default; the other reading gives: a Critical `signature-mismatch`",
        "- **Scoped Out by the Brief:** `legacy` (lib/legacy.ts)",
    ], lines[at:]
    assert lines[at - 2:at] == ["- **Scoring Warnings:**", f"  - {RENDER_SIGNATURES['warnings'][0]}"]
    # No reading recorded: no Borderline Calls line, and coverage.json carries no `undecided`.
    plain = json.loads(_run_cli(["--denominator-source", "barrel", "--inventory",
                                 _write(tmp_path / "plain.json", {**INVENTORY, "undecided": []}),
                                 *branches["barrel"]]).stdout)
    assert "undecided" not in plain
    assert "Borderline Calls" not in mod.render(plain, SURFACE, {**RENDER_SIGNATURES, "undecided": []})


def test_cli_refused_input_removes_a_stale_output(tmp_path):
    out_path = tmp_path / "coverage.json"
    out_path.write_bytes(b'{"exportCoverage": 100}')
    proc = _run_cli(["--denominator-source", "barrel", "--output", str(out_path)])
    assert proc.returncode == 2 and not out_path.exists()


def test_cli_unreadable_input_file_exits_1(tmp_path):
    proc = _run_cli(["--denominator-source", "docsOnly", "--inventory", str(tmp_path / "absent.json")])
    assert proc.returncode == 1 and "cannot read --inventory" in proc.stderr



# --------------------------------------------------------------------------
# render: the Coverage Analysis section coverage-check.md §5 writes unchanged
# (v4.0.0 quality gate run 1, determinism-2)
# --------------------------------------------------------------------------

COVERAGE_STEP = REPO_ROOT / "src" / "skf-test-skill" / "references" / "coverage-check.md"
RENDER_INVENTORY = {"exports": [
    {"name": "createClient", "kind": "function", "params": "opts", "return_type": "Client", "description": "d"},
    {"name": "Client", "kind": "class", "description": "d"},
    {"name": "Client.run", "kind": "method", "params": "", "return_type": "void", "description": "d"},
    {"name": "parse", "kind": "function", "params": "text", "return_type": "Ast", "description": "d"},
    {"name": "legacyFn", "kind": "function", "params": "", "return_type": "void", "description": "d"},
]}
RENDER_SURFACE = {
    "exports": [
        {"name": "Client", "kind": "class", "file": "src/client.ts", "line": 40, "origin": "extraction"},
        {"name": "Options", "kind": "interface", "file": "src/types.ts", "line": 7, "origin": "extraction"},
        {"name": "VERSION", "kind": "constant", "file": None, "line": None, "origin": "metadata"},
        {"name": "createClient", "kind": "function", "file": "src/client.ts", "line": 12, "origin": "extraction"},
        {"name": "parse", "kind": None, "file": "src/index.ts", "line": None, "origin": "extraction"},
        {"name": "parse", "kind": "function", "file": "src/parse.ts", "line": 3, "origin": "extraction"},
    ],
    "sets": {"all": ["Client", "Options", "VERSION", "createClient", "parse"]},
}
RENDER_SIGNATURES = {
    "valid": True, "signatureAccuracy": 50.0, "matchingSignatures": 1, "totalDocumented": 2,
    "comparedNames": ["createClient", "parse"], "typeCoverage": 50.0, "documentedTypes": 1, "totalTypes": 2,
    "missingTypes": ["Options"],
    "mismatches": [{"name": "parse", "file": "src/parse.ts", "line": 3, "source_sig": "(text: string, o?: O) => Ast",
                    "documented_sig": "(text: string) => Ast", "issue": "missing optional parameter 'o'"}],
    "gapRecords": [],
    "warnings": ["src/extra.ts:9: a signature mismatch for `ghost`, which is no documented signature on the "
                 "source surface: not scored, no gap"],
}
# The golden output: one row per counted, stale or mismatched name; FAIL for a signature mismatch, WARN for a
# missing or stale name, PASS otherwise; Files Analyzed counts the distinct files the surface records.
GOLDEN_BARREL = """**Files Analyzed:** 4

### Export Coverage

| Export | Type | Documented | Signature | Source Location | Status |
|--------|------|------------|-----------|-----------------|--------|
| `Client` | class | yes | - | src/client.ts:40 | PASS |
| `Options` | interface | no | - | src/types.ts:7 | WARN |
| `VERSION` | constant | no | - | - | WARN |
| `createClient` | function | yes | yes | src/client.ts:12 | PASS |
| `legacyFn` | - | yes | - | - | WARN |
| `parse` | function | yes | no | src/parse.ts:3 | FAIL |

### Coverage Summary

- **Exports Found:** 5
- **Documented:** 3 (60%)
- **Missing Documentation:** 2
- **Signature Mismatches:** 1
- **Stale Documentation:** 1, documented extras included
- **Scoring Warnings:**
  - src/extra.ts:9: a signature mismatch for `ghost`, which is no documented signature on the source surface: not scored, no gap

### Category Scores

| Category | Score |
|----------|-------|
| Export Coverage | 60% |
| Signature Accuracy | 50% |
| Type Coverage | 50% |
"""


def test_a_mismatched_row_sits_at_the_declaration_it_was_compared_with():
    """#781: a name the surface records in two files is compared at the one the skill cites, so its row's Source
    Location is its mismatch's `file:line`, its most severe one's, not the surface's first record."""
    coverage = {"branch": "enumerated", "documentedNames": ["defineMain"], "missing": [], "stale": []}
    surface = {"exports": [
        {"name": "defineMain", "kind": "function", "file": "code/angular/index.ts", "line": 3, "origin": "extraction"},
        {"name": "defineMain", "kind": "function", "file": "code/react-vite/index.ts", "line": 5,
         "origin": "extraction"}], "sets": {"all": ["defineMain"]}}
    mismatch = {"name": "defineMain", "file": "code/react-vite/index.ts", "line": 5, "source_sig": "(c: C) => C",
                "documented_sig": "(config: C) => C", "issue": "renamed", "severity": "Low"}
    critical = {**mismatch, "file": "code/angular/index.ts", "line": 3, "severity": "Critical"}
    for mismatches, at in (([mismatch], "code/react-vite/index.ts:5"), ([mismatch, critical], "code/angular/index.ts:3")):
        rows = mod._rows(coverage, surface, {"mismatches": mismatches, "comparedNames": ["defineMain"]})
        assert rows[2].split(" | ")[4] == at, rows[2]


def _run_render(*args):
    return subprocess.run([sys.executable, str(SCRIPT_PATH), "render", *args], capture_output=True, text=True,
                          encoding="utf-8")


def _render_run_files(run):
    """The run files §2, §2b and §2c write, the coverage one by this script's barrel branch."""
    _write(run / "inventory.json", RENDER_INVENTORY)
    _write(run / "surface.json", RENDER_SURFACE)
    _write(run / "signatures.json", RENDER_SIGNATURES)
    proc = _run_cli(["--denominator-source", "barrel", "--inventory", (run / "inventory.json").as_posix(),
                     "--surface", (run / "surface.json").as_posix(), "--output", (run / "coverage.json").as_posix()])
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_render_helpers_doctests_pass():
    result = doctest.testmod(mod, verbose=False)
    assert result.attempted > 0 and result.failed == 0


def test_barrel_lists_the_documented_names_it_counts():
    out = reconcile({"denominatorSource": "barrel", "exports": RENDER_INVENTORY["exports"],
                     "barrelSet": RENDER_SURFACE["sets"]["all"]})
    assert out["documentedNames"] == ["Client", "createClient", "parse"]
    assert (out["missing"], out["stale"]) == (["Options", "VERSION"], ["legacyFn"])


def test_render_matches_the_golden_barrel_section(tmp_path):
    run = tmp_path / "run"
    _render_run_files(run)
    proc = _run_render("--coverage", (run / "coverage.json").as_posix(), "--surface", (run / "surface.json").as_posix(),
                       "--signatures", (run / "signatures.json").as_posix())
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == GOLDEN_BARREL
    # identical run files give an identical section
    assert _run_render("--coverage", (run / "coverage.json").as_posix(), "--surface",
                       (run / "surface.json").as_posix(), "--signatures",
                       (run / "signatures.json").as_posix()).stdout == GOLDEN_BARREL


def test_coverage_check_writes_the_render_output_as_written(tmp_path):
    """§5 runs the render with every run file the barrel branch wrote, and the model writes it unchanged."""
    text = COVERAGE_STEP.read_text(encoding="utf-8")
    section = text[text.index("### 5. Write the Coverage Analysis Section"):text.index("### 5b.")]
    [command] = [line for line in section.splitlines() if line.startswith("uv run {reconcileScript} render")]
    run = tmp_path / "run"
    _render_run_files(run)
    command = re.sub(r" \[([^\]]+)\]", r" \1", command).replace("{run_dir}", run.as_posix())
    words = shlex.split(command)
    assert words[:3] == ["uv", "run", "{reconcileScript}"]
    proc = _run_render(*words[4:])
    assert proc.returncode == 0 and proc.stdout == GOLDEN_BARREL
    flow = " ".join(section.split())
    assert "write its output unchanged where the section below places it" in flow
    assert '(`halt_reason: "helper-failed"`, phase `coverage-check:render`)' in flow
    assert "Exit 2 is a usage error: correct the command and run it again." in flow
    # §4's Denominator Candidates block has its place, right under the Denominator line.
    assert ("**Denominator:** {the §4 annotation}\n{the Denominator Candidates block, when §4 adds one}\n\n"
            "{the render output}") in section
    # The render marks a Quick-tier signature unverified, and lists the names the surface leaves out:
    # the earlier sections no longer have the model write either by hand.
    assert "Signatures cannot be verified at this tier (§5's render marks them unverified)." in text
    assert 'note them as "unverified"' not in text
    assert ("§5's render lists `excluded.outsideScope`, `excluded.nestedEntries`, the restored names and "
            "`extractionGaps`.") in text
    # No row, count or score is typed by hand any more.
    for typed in ("| {name} | {kind} |", "{count}", "### Coverage Summary", "| Export Coverage | {N}% |"):
        assert typed not in text, typed
    assert "{file_count}" not in text


def test_render_without_signatures_leaves_them_unverified(tmp_path):
    """Quick tier, States 2 to 4: no signatures.json, so a documented name's signature is unverified."""
    coverage = reconcile({"denominatorSource": "barrel", "exports": RENDER_INVENTORY["exports"],
                          "barrelSet": RENDER_SURFACE["sets"]["all"]})
    text = mod.render(coverage, RENDER_SURFACE)
    assert "| `Client` | class | yes | unverified | src/client.ts:40 | PASS |" in text
    assert "| `Options` | interface | no | - | src/types.ts:7 | WARN |" in text
    assert "- **Signature Mismatches:** N/A" in text and "Scoring Warnings" not in text
    assert "| Signature Accuracy | N/A |" in text and "| Type Coverage | N/A |" in text


def test_render_a_docs_only_run():
    exports = [{"name": "load", "kind": "function", "description": "Loads it."},
               {"name": "Config", "kind": "type", "fields": ["a"], "description": "The config."}]
    coverage = reconcile({"denominatorSource": "docsOnly", "exports": exports})
    assert mod.render(coverage) == """**Files Analyzed:** N/A: no source surface

### Export Coverage

No per-export table: a docs-only run has no source surface to compare against. The summary below gives its \
documentation completeness.

### Coverage Summary

- **Exports Found:** 2 documented items
- **Documented:** 1 complete (50%)
- **Missing Documentation:** 1 incomplete: `load` (function) lacks `params`, `return_type`
- **Signature Mismatches:** N/A
- **Stale Documentation:** N/A: a docs-only run has no source surface

### Category Scores

| Category | Score |
|----------|-------|
| Export Coverage | 50% |
| Signature Accuracy | N/A |
| Type Coverage | N/A |
"""


def test_render_states_a_capped_surplus():
    coverage = reconcile({"denominatorSource": "scalar", "denominatorValue": 2,
                          "exports": [{"name": n, "kind": "function"} for n in ("a", "b", "c")],
                          "skillPackagePath": "/unused"}, doc_text="a b c")
    text = mod.render(coverage, {"exports": []})
    assert "**Files Analyzed:** 0" in text
    assert "No per-export table: the scalar denominator (`stats.effective_denominator`)" in text
    assert "- **Missing Documentation:** 0 (a floored residual: the numerator exceeds the denominator)" in text
    assert "- **Numerator Surplus:** 1, uncapped coverage 150%" in text
    assert ("- **Stale Documentation:** N/A: the scalar denominator (`stats.effective_denominator`) counts the "
            "exports without naming them") in text


def test_render_a_stack_run_names_no_export(tmp_path):
    """A stack counts its composition surface without naming each export: one line stands in for the table."""
    pkg = _make_skill_pkg(tmp_path, skill_md_text="composes react-query and zod")
    coverage = reconcile({"denominatorSource": "stack", "compositionNames": ["react-query", "zod", "trpc"],
                          "denominatorValue": 3, "skillPackagePath": pkg})
    text = mod.render(coverage, {"exports": []})
    assert "| Export |" not in text
    for line in ("**Files Analyzed:** 0",
                 "No per-export table: the stack denominator counts the composition surface without naming each "
                 "export. The summary below gives the counts.",
                 "- **Exports Found:** 3", "- **Documented:** 2 (66.67%)", "- **Missing Documentation:** 1",
                 "- **Stale Documentation:** N/A: the stack denominator counts the composition surface without "
                 "naming each export",
                 "| Signature Accuracy | N/A |"):
        assert line in text.splitlines(), line


def test_render_gives_a_mismatch_outside_the_counted_set_its_own_fail_row():
    """score-signatures.py compares every name a surface record names, so a method the barrel never counts
    (`Client.run`) can mismatch: it gets its own FAIL row, and the counted rows stay as they were."""
    method = {"name": "Client.run", "kind": "method", "file": "src/client.ts", "line": 55, "origin": "extraction"}
    surface = {**RENDER_SURFACE, "exports": [*RENDER_SURFACE["exports"], method]}
    coverage = reconcile({"denominatorSource": "barrel", "exports": RENDER_INVENTORY["exports"],
                          "barrelSet": surface["sets"]["all"]})
    assert "Client.run" not in coverage["documentedNames"] + coverage["missing"] + coverage["stale"]
    mismatch = {"name": "Client.run", "file": "src/client.ts", "line": 55, "source_sig": "() => Promise<void>",
                "documented_sig": "() => void", "issue": "return type differs"}
    signatures = {**RENDER_SIGNATURES, "comparedNames": ["Client.run", "createClient", "parse"],
                  "mismatches": [*RENDER_SIGNATURES["mismatches"], mismatch]}
    text = mod.render(coverage, surface, signatures)
    assert "| `Client.run` | method | yes | no | src/client.ts:55 | FAIL |" in text
    assert "- **Signature Mismatches:** 2" in text and "- **Exports Found:** 5" in text
    golden_rows = [line for line in GOLDEN_BARREL.splitlines() if line.startswith("| `")]
    assert [line for line in text.splitlines() if line.startswith("| `") and "Client.run" not in line] == golden_rows


def test_render_shows_a_signature_mismatch_graded_low_or_info_as_matching():
    """#793, #816: score-signatures.py grades a caller-invisible difference Low (a renamed parameter in a TS
    file) or Info (an optional member a partial form leaves out), and counts it as matching. Its row shows the
    signature as matching and warns instead of failing, the summary counts only the Critical mismatches, and a
    Critical mismatch of the same name still fails the row."""
    coverage = reconcile({"denominatorSource": "barrel", "exports": RENDER_INVENTORY["exports"],
                          "barrelSet": RENDER_SURFACE["sets"]["all"]})
    [parse] = RENDER_SIGNATURES["mismatches"]
    rename = {"name": "createClient", "file": "src/client.ts", "line": 12, "source_sig": "(options) => Client",
              "documented_sig": "(opts) => Client", "issue": "the parameter is named 'options'",
              "difference": "parameter-name", "severity": "Low"}
    partial = {**parse, "difference": "omitted-optional", "severity": "Info"}
    signatures = {**RENDER_SIGNATURES, "mismatches": [rename, partial]}
    text = mod.render(coverage, RENDER_SURFACE, signatures)
    assert "| `createClient` | function | yes | yes (Low) | src/client.ts:12 | WARN |" in text
    assert "| `parse` | function | yes | yes (Info) | src/parse.ts:3 | WARN |" in text
    assert "FAIL" not in text
    assert "- **Signature Mismatches:** 0, plus 2 graded Low or Info and counted as matching" in text
    critical = {**parse, "difference": None, "severity": "Critical"}
    text = mod.render(coverage, RENDER_SURFACE, {**signatures, "mismatches": [rename, partial, critical]})
    assert "| `parse` | function | yes | no | src/parse.ts:3 | FAIL |" in text
    assert "| `createClient` | function | yes | yes (Low) | src/client.ts:12 | WARN |" in text
    assert "- **Signature Mismatches:** 1, plus 2 graded Low or Info and counted as matching" in text


def test_render_reads_the_grades_score_signatures_gives():
    """The render's NON_BLOCKING_MISMATCH restates the grades score-signatures.py gives: score a Low, an Info and a
    Critical mismatch with the real script, render its result, and each row and the summary agree with it."""
    scorer_spec = importlib.util.spec_from_file_location(
        "score_signatures_for_render", SCRIPT_PATH.parent / "score-signatures.py")
    scorer = importlib.util.module_from_spec(scorer_spec)
    scorer_spec.loader.exec_module(scorer)
    inventory = [
        {"name": "rename", "kind": "function", "params": "x: number", "return_type": "number", "description": "d"},
        {"name": "Canvas", "kind": "function", "params": "{ of }", "return_type": "JSX.Element", "description": "d",
         "signature_form": "partial"},
        {"name": "broken", "kind": "function", "params": "", "return_type": "void", "description": "d"},
        {"name": "fine", "kind": "function", "params": "", "return_type": "void", "description": "d"},
    ]
    surface = {"exports": [{"name": n, "kind": "function", "file": f, "line": 1, "origin": "extraction"}
                           for n, f in (("Canvas", "src/Canvas.tsx"), ("broken", "src/broken.ts"),
                                        ("fine", "src/fine.ts"), ("rename", "src/rename.ts"))],
               "sets": {"all": ["Canvas", "broken", "fine", "rename"]}}
    sig = {"line": 1, "source_sig": "(a)", "documented_sig": "(b)", "issue": "differs"}
    results = [
        {"file": "src/rename.ts", "signature_mismatches": [{**sig, "name": "rename", "difference": "parameter-name"}]},
        {"file": "src/Canvas.tsx", "signature_mismatches": [{**sig, "name": "Canvas",
                                                             "difference": "omitted-optional"}]},
        {"file": "src/broken.ts", "signature_mismatches": [{**sig, "name": "broken"}]},
    ]
    signatures = scorer.score(inventory, surface["sets"]["all"], surface["exports"], results)
    assert {m["name"]: m["severity"] for m in signatures["mismatches"]} == {
        "rename": "Low", "Canvas": "Info", "broken": "Critical"}
    assert set(mod.NON_BLOCKING_MISMATCH) == {"Low", "Info"} and "Critical" in scorer.GRADES
    coverage = reconcile({"denominatorSource": "barrel", "exports": inventory, "barrelSet": surface["sets"]["all"]})
    text = mod.render(coverage, surface, signatures)
    rows = [line for line in text.splitlines() if line.startswith("| `")]
    assert rows == [
        "| `Canvas` | function | yes | yes (Info) | src/Canvas.tsx:1 | WARN |",
        "| `broken` | function | yes | no | src/broken.ts:1 | FAIL |",
        "| `fine` | function | yes | yes | src/fine.ts:1 | PASS |",
        "| `rename` | function | yes | yes (Low) | src/rename.ts:1 | WARN |",
    ]
    assert "- **Signature Mismatches:** 1, plus 2 graded Low or Info and counted as matching" in text
    assert (signatures["matchingSignatures"], signatures["totalDocumented"]) == (3, 4)
    assert "| Signature Accuracy | 75% |" in text


def test_render_lists_the_names_the_surface_leaves_out_or_puts_back():
    """coverage-check §2: the names a brief scoped out, a nested entry point's names, the names the stale-scope
    guard restored and the names no recipe found (#1048: read by eye by no step, a gap with no file listed as not
    located) reach the Coverage Summary from surface.json, each line only when it names one."""
    surface = {**RENDER_SURFACE,
               "excluded": {"outsideScope": [{"name": "genClient", "file": "src/gen/client.ts"}],
                            "nestedEntries": [{"entry": "pkg/routers/__init__.py", "within": "pkg/__init__.py",
                                               "names": ["Route", "router"]}]},
               "guards": {"staleScope": {"applicable": True, "fires": True, "unmatchedInclude": ["lib/**"],
                                         "unmatchedTierAInclude": [],
                                         "restored": [{"name": "legacy", "file": "src/legacy.ts", "line": 9},
                                                      {"name": "older", "file": "src/older.ts", "line": None}]}},
               "extractionGaps": [{"name": "fn", "file": "src/fn.ts", "line": 3},
                                  {"name": "Sym", "file": "src/sym.ts", "line": None},
                                  {"name": "Lance", "file": None, "line": None}]}
    coverage = reconcile({"denominatorSource": "barrel", "exports": RENDER_INVENTORY["exports"],
                          "barrelSet": surface["sets"]["all"]})
    text = mod.render(coverage, surface)
    summary = text[text.index("### Coverage Summary"):text.index("### Category Scores")].splitlines()
    assert "- **Scoped Out by the Brief:** `genClient` (src/gen/client.ts)" in summary
    assert "- **Nested Entry Points:** `pkg/routers/__init__.py` inside `pkg/__init__.py`: `Route`, `router`" in summary
    assert "- **Restored by the Stale-Scope Guard:** `legacy` (src/legacy.ts:9), `older` (src/older.ts)" in summary
    assert "- **Extraction Gaps:** `fn` (src/fn.ts:3), `Sym` (src/sym.ts), `Lance` (not located)" in summary
    # A surface that leaves nothing out and has no gap writes none of the four lines.
    assert not [line for line in GOLDEN_BARREL.splitlines() if "Scoped Out" in line or "Nested Entry" in line
                or "Restored by" in line or "Extraction Gaps" in line]
    assert not mod._left_out({**RENDER_SURFACE, "extractionGaps": []})


@pytest.mark.parametrize("coverage, signatures, error", [
    ({"branch": "enumerated", "denominator": 1, "documented": 1, "missing": [], "stale": []}, None,
     "no `documentedNames`"),
    ({"branch": "sideways"}, None, "no known `branch`"),
    ({"branch": "docsOnly", "denominator": 1, "documented": 1}, {"valid": False, "violations": ["x"]},
     "not score-signatures.py score's result"),
], ids=["no-documented-names", "unknown-branch", "invalid-signatures"])
def test_render_refuses_a_file_it_cannot_read(tmp_path, coverage, signatures, error):
    args = ["--coverage", _write(tmp_path / "coverage.json", coverage)]
    if signatures is not None:
        args += ["--signatures", _write(tmp_path / "signatures.json", signatures)]
    proc = _run_render(*[Path(a).as_posix() if a.endswith(".json") else a for a in args])
    assert proc.returncode == 1 and error in proc.stderr and proc.stdout == ""
    proc = _run_render("--coverage", (tmp_path / "absent.json").as_posix())
    assert proc.returncode == 1 and "cannot read --coverage" in proc.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
