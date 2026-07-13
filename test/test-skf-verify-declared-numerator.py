#!/usr/bin/env python3
"""Tests for verify-declared-numerator.py (skf-test-skill coverage-check.md §4b).

Covers the numerator ground-truth grep: which declared export names are present
in / absent from the documentation surface, the verified numerator, the
`inflated` flag, injected-doc-text determinism, on-disk grepping over
SKILL.md ∪ references/*.md, schema validation, and the subprocess CLI contract
(exit codes + JSON-on-stdout).
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
    REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "verify-declared-numerator.py"
)

spec = importlib.util.spec_from_file_location("verify_declared_numerator", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
verify = mod.verify


# --------------------------------------------------------------------------
# Core grep semantics (injected doc_text)
# --------------------------------------------------------------------------


def test_all_present_not_inflated():
    doc = "foo bar baz appear here"
    out = verify({"declaredNames": ["foo", "bar", "baz"], "skillPackagePath": "x"}, doc_text=doc)
    assert out["declared"] == 3
    assert out["verified"] == 3
    assert out["present"] == ["bar", "baz", "foo"]
    assert out["absent"] == []
    assert out["inflated"] is False


def test_some_absent_is_inflated():
    doc = "only foo is documented here"
    out = verify(
        {"declaredNames": ["foo", "bar", "baz"], "skillPackagePath": "x"}, doc_text=doc
    )
    assert out["declared"] == 3
    assert out["verified"] == 1
    assert out["present"] == ["foo"]
    assert out["absent"] == ["bar", "baz"]
    assert out["inflated"] is True


def test_case_sensitive_substring():
    """Matching mirrors `grep "{name}"` — case-sensitive substring containment."""
    doc = "Foo and FOObar exist; formatDate is used"
    out = verify(
        {"declaredNames": ["foo", "Foo", "formatDate"], "skillPackagePath": "x"},
        doc_text=doc,
    )
    # "foo" is absent (only "Foo"/"FOObar"); "Foo" present (substring of FOObar? no —
    # FOObar is uppercase; "Foo" appears as the standalone token). "formatDate" present.
    assert "Foo" in out["present"]
    assert "formatDate" in out["present"]
    assert "foo" in out["absent"]


def test_declared_names_deduplicated():
    doc = "alpha present"
    out = verify(
        {"declaredNames": ["alpha", "alpha", "beta"], "skillPackagePath": "x"},
        doc_text=doc,
    )
    assert out["declared"] == 2  # alpha counted once
    assert out["verified"] == 1
    assert out["absent"] == ["beta"]


def test_impl_block_method_names_grep_verbatim():
    """`Type::method` declared names are greped verbatim (no folding here)."""
    doc = "Widget::render is documented; the other method is not"
    out = verify(
        {"declaredNames": ["Widget::render", "Widget::hidden"], "skillPackagePath": "x"},
        doc_text=doc,
    )
    assert out["present"] == ["Widget::render"]
    assert out["absent"] == ["Widget::hidden"]
    assert out["inflated"] is True


# --------------------------------------------------------------------------
# On-disk grep over SKILL.md ∪ references/*.md
# --------------------------------------------------------------------------


def test_reads_skill_md_and_references(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("documents alpha here\n", encoding="utf-8")
    refs = skill / "references"
    refs.mkdir()
    (refs / "api.md").write_text("beta lives in a reference file\n", encoding="utf-8")
    out = verify(
        {"declaredNames": ["alpha", "beta", "gamma"], "skillPackagePath": str(skill)}
    )
    assert out["verified"] == 2
    assert out["present"] == ["alpha", "beta"]
    assert out["absent"] == ["gamma"]
    assert out["inflated"] is True


def test_non_ascii_export_utf8(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("função café documented\n", encoding="utf-8")
    out = verify({"declaredNames": ["função", "café"], "skillPackagePath": str(skill)})
    assert out["verified"] == 2
    assert out["inflated"] is False


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"declaredNames": [], "skillPackagePath": "x"},
        {"declaredNames": ["a"]},
        {"declaredNames": "a", "skillPackagePath": "x"},
        None,
    ],
)
def test_invalid_input(bad):
    out = verify(bad, doc_text="a")
    assert out["code"] == "INVALID_INPUT"


# --------------------------------------------------------------------------
# CLI contract (subprocess)
# --------------------------------------------------------------------------


def _run_cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_ok(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("foo bar\n", encoding="utf-8")
    payload = json.dumps({"declaredNames": ["foo", "bar"], "skillPackagePath": str(skill)})
    res = _run_cli(["--stdin"], stdin=payload)
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["verified"] == 2
    assert out["inflated"] is False


def test_cli_no_input_exit_1():
    res = _run_cli(["--stdin"], stdin="")
    assert res.returncode == 1


def test_cli_invalid_schema_exit_2():
    res = _run_cli(["--stdin"], stdin=json.dumps({"declaredNames": []}))
    assert res.returncode == 2
    out = json.loads(res.stdout)
    assert out["code"] == "INVALID_INPUT"


def test_cli_malformed_json_exit_1():
    res = _run_cli(["--stdin"], stdin="{not json")
    assert res.returncode == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
