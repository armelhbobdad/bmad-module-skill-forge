#!/usr/bin/env python3
"""Tests for reconcile-coverage.py (skf-test-skill coverage-check.md §2c).

Covers the four §2c branches:
  - "barrel"  (enumerated intersection): Documented / Missing / Stale / coverage
  - "scalar"  (effective_denominator, looked-up numerator, no Stale)
  - "stack"   (composition-surface looked-up numerator, empty barrel)
  - "docsOnly" (#540: documentation completeness over the inventory)
Plus method-exclusion, dedup, rounding, validation, the whole-name lookup
(`get` is found in neither `target` nor `getAll`), the run-folder file flags
(an extraction surface whose internal recipe matches never count), and the
subprocess CLI (exit codes + JSON-on-stdout contract).
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


def test_cli_refused_input_removes_a_stale_output(tmp_path):
    out_path = tmp_path / "coverage.json"
    out_path.write_bytes(b'{"exportCoverage": 100}')
    proc = _run_cli(["--denominator-source", "barrel", "--output", str(out_path)])
    assert proc.returncode == 2 and not out_path.exists()


def test_cli_unreadable_input_file_exits_1(tmp_path):
    proc = _run_cli(["--denominator-source", "docsOnly", "--inventory", str(tmp_path / "absent.json")])
    assert proc.returncode == 1 and "cannot read --inventory" in proc.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
