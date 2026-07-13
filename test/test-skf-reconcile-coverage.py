#!/usr/bin/env python3
"""Tests for reconcile-coverage.py (skf-test-skill coverage-check.md §2c).

Covers the three §2c branches:
  - "barrel"  (enumerated intersection) — Documented / Missing / Stale / coverage
  - "scalar"  (effective_denominator, grep numerator, no Stale)
  - "stack"   (composition-surface grep numerator, empty barrel)
Plus method-exclusion, dedup, rounding, validation, and the subprocess CLI
(exit codes + JSON-on-stdout contract).
"""

from __future__ import annotations

import importlib.util
import json
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
