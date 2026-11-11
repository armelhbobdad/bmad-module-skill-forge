#!/usr/bin/env python3
"""Tests for verify-declared-numerator.py (skf-test-skill coverage-check.md §2b, recorded in §4b).

Covers the numerator ground-truth lookup: which declared export names are
present in / absent from the documentation surface (as whole names, the
match validate-inventory.py shares: `get` is found in neither `target` nor
`getAll`), the verified numerator, the `inflated` flag, injected-doc-text
determinism, on-disk lookups over SKILL.md ∪ references/*.md, schema
validation, the --inputs file load-coverage-inputs.py metadata writes (a
run without the inflation signature is skipped), and the subprocess CLI
contract (exit codes + JSON-on-stdout).
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


def test_case_sensitive_whole_name():
    """A declared name counts when the text writes it, case-sensitive, as a whole name."""
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


@pytest.mark.parametrize("doc, present", [
    ("call get(url)", ["get"]), ("the target", []), ("getAll()", []),
], ids=["whole-name", "inside-target", "prefix-of-getAll"])
def test_a_name_inside_a_longer_identifier_is_absent(doc, present):
    out = verify({"declaredNames": ["get"], "skillPackagePath": "x"}, doc_text=doc)
    assert out["present"] == present and out["inflated"] is (not present)


# --------------------------------------------------------------------------
# --inputs: load-coverage-inputs.py metadata output
# --------------------------------------------------------------------------


def _inputs(tmp_path, signature, names):
    path = tmp_path / "coverage-inputs.json"
    path.write_bytes(json.dumps({"inflationSignature": signature, "declaredNames": names}).encode("utf-8"))
    skill = tmp_path / "skill"
    skill.mkdir(exist_ok=True)
    (skill / "SKILL.md").write_bytes(b"`foo()` only\n")
    return str(path), str(skill)


def test_inputs_without_the_signature_are_skipped(tmp_path):
    inputs, skill = _inputs(tmp_path, False, ["foo", "bar"])
    res = _run_cli(["--inputs", inputs, "--skill-dir", skill])
    assert res.returncode == 0
    assert json.loads(res.stdout) == {"skipped": True, "declared": 2, "verified": None, "present": [],
                                      "absent": [], "inflated": False}


def test_inputs_with_the_signature_are_verified_and_written(tmp_path):
    inputs, skill = _inputs(tmp_path, True, ["foo", "bar"])
    out_path = tmp_path / "numerator.json"
    res = _run_cli(["--inputs", inputs, "--skill-dir", skill, "--output", str(out_path)])
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == out
    assert (out["skipped"], out["verified"], out["absent"], out["inflated"]) == (False, 1, ["bar"], True)


def test_inputs_need_a_skill_dir(tmp_path):
    inputs, _ = _inputs(tmp_path, True, ["foo"])
    assert _run_cli(["--inputs", inputs]).returncode == 2


def test_unreadable_inputs_exit_1(tmp_path):
    res = _run_cli(["--inputs", str(tmp_path / "absent.json"), "--skill-dir", str(tmp_path)])
    assert res.returncode == 1 and "cannot read --inputs" in res.stderr


# --------------------------------------------------------------------------
# #1068: a declared name counts only when the inventory gives it an entry
# --------------------------------------------------------------------------

# The inventory-contract rules that give a name the text writes no entry, #1013 (not covered), #1008 (an alias, or a
# name the skill says the source does not export), #1038 (a removed form) and a type mention: each case's doc text
# writes both declared names, and the inventory gives only the first one an entry.
NO_ENTRY_CASES = {
    "not-covered": (["foo", "bar"], "`foo()` fetches the page. `bar` is not covered here.\n"),
    "alias": (["Grid", "GridCellType"],
              "`Grid` renders the cells. `import { CellType as GridCellType } from 'grid'` imports it as "
              "`GridCellType`.\n"),
    "unexported": (["Grid", "RowState"], "`Grid` renders each row. `RowState` is internal: the source does not "
                                         "export it.\n"),
    "removed-form": (["newCall", "oldCall"],
                     "| v0.3 (gone) | v0.4 |\n| --- | --- |\n| `oldCall(a)` | `newCall(a, b)` |\n"),
    "type-mention": (["connect", "Options"], "`connect(opts: Options)` opens a session.\n"),
}


@pytest.mark.parametrize("declared, doc", list(NO_ENTRY_CASES.values()), ids=list(NO_ENTRY_CASES))
def test_a_name_the_inventory_gives_no_entry_is_absent(declared, doc):
    """#1068: the text writes both declared names, but the inventory contract gives the second no entry (a
    not-covered sentence, a local import alias, a name the source does not export, a form marked removed, a type
    mention), so it is absent and the count inflated."""
    kept, dropped = declared
    out = verify({"declaredNames": declared, "skillPackagePath": "x",
                  "exports": [{"name": kept, "kind": "function"}]}, doc_text=doc)
    assert (out["declared"], out["verified"], out["present"], out["absent"], out["inflated"]) == \
        (2, 1, [kept], [dropped], True)


def test_a_declared_owned_method_matches_its_method_entry():
    """A declared Rust `Widget::render` counts through its `method` entry (`render`, owner `Widget`); a declared
    method the text writes but the inventory gives no entry does not."""
    out = verify({"declaredNames": ["Widget::render", "Widget::hidden"], "skillPackagePath": "x",
                  "exports": [{"name": "Widget", "kind": "struct"},
                              {"name": "render", "kind": "method", "owner": "Widget"}]},
                 doc_text="`Widget::render` draws it. `Widget::hidden` is out of scope for this skill.")
    assert (out["verified"], out["present"], out["absent"]) == (1, ["Widget::render"], ["Widget::hidden"])


def test_an_entry_the_text_does_not_write_is_still_absent():
    """A name counts only when the inventory gives it an entry and the text writes it, so an entry for a declared
    name the text never writes does not make it verified."""
    out = verify({"declaredNames": ["foo", "ghost"], "skillPackagePath": "x",
                  "exports": [{"name": "foo", "kind": "function"}, {"name": "ghost", "kind": "function"}]},
                 doc_text="`foo()` fetches the page.\n")
    assert (out["verified"], out["present"], out["absent"], out["inflated"]) == (1, ["foo"], ["ghost"], True)


@pytest.mark.parametrize("extra", [{}, {"exports": None}], ids=["no-key", "null"])
def test_without_an_inventory_the_text_alone_decides(extra):
    """No `exports`: every declared name the text writes counts, as before #1068."""
    declared, doc = NO_ENTRY_CASES["not-covered"]
    out = verify({"declaredNames": declared, "skillPackagePath": "x", **extra}, doc_text=doc)
    assert (out["verified"], out["absent"], out["inflated"]) == (2, [], False)


def _no_entry_run(tmp_path):
    """coverage-inputs.json with the inflation signature, and a skill that writes `bar` only in a not-covered
    sentence."""
    inputs, skill = _inputs(tmp_path, True, ["foo", "bar"])
    Path(skill, "SKILL.md").write_bytes(NO_ENTRY_CASES["not-covered"][1].encode("utf-8"))
    return inputs, skill


@pytest.mark.parametrize("wrap", [lambda inv: inv, lambda inv: {"valid": True, "inventory": inv}],
                         ids=["inventory-file", "whole-result"])
def test_cli_inventory_with_inputs(tmp_path, wrap):
    """The command coverage-check.md runs: --inventory reads validate-inventory.py's --output file, or its whole
    result, and the declared `bar` the inventory gives no entry is absent."""
    inputs, skill = _no_entry_run(tmp_path)
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(json.dumps(wrap({"exports": [{"name": "foo", "kind": "function"}]})).encode("utf-8"))
    out_path = tmp_path / "numerator.json"
    res = _run_cli(["--inputs", inputs, "--skill-dir", skill, "--inventory", str(inventory),
                    "--output", str(out_path)])
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == out
    assert (out["skipped"], out["verified"], out["absent"], out["inflated"]) == (False, 1, ["bar"], True)
    # Without --inventory the text alone decides, as before.
    plain = json.loads(_run_cli(["--inputs", inputs, "--skill-dir", skill]).stdout)
    assert (plain["verified"], plain["absent"], plain["inflated"]) == (2, [], False)


def test_cli_inventory_wins_over_the_json_exports(tmp_path):
    _, skill = _no_entry_run(tmp_path)
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(json.dumps({"exports": [{"name": "foo", "kind": "function"}]}).encode("utf-8"))
    payload = json.dumps({"declaredNames": ["foo", "bar"], "skillPackagePath": skill, "exports": []})
    res = _run_cli(["--stdin", "--inventory", str(inventory)], stdin=payload)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["present"] == ["foo"]


@pytest.mark.parametrize("content, message", [
    (None, "cannot read --inventory"),
    (b"{not json", "is not JSON"),
    (b'{"exports": "foo"}', "holds no `exports` list"),
    (b'{"valid": false, "inventory": null, "violations": ["x"]}', "holds no `exports` list"),
], ids=["missing", "not-json", "exports-not-a-list", "refused-result"])
def test_cli_bad_inventory_exits_1_and_writes_nothing(tmp_path, content, message):
    inputs, skill = _no_entry_run(tmp_path)
    inventory = tmp_path / "inventory.json"
    if content is not None:
        inventory.write_bytes(content)
    out_path = tmp_path / "numerator.json"
    res = _run_cli(["--inputs", inputs, "--skill-dir", skill, "--inventory", str(inventory),
                    "--output", str(out_path)])
    assert res.returncode == 1 and res.stdout == "" and not out_path.exists()
    assert len(res.stderr.splitlines()) == 1 and message in res.stderr, res.stderr


def test_json_exports_that_is_no_list_is_invalid(tmp_path):
    payload = {"declaredNames": ["foo"], "skillPackagePath": str(tmp_path), "exports": {"name": "foo"}}
    assert verify(payload, doc_text="foo")["code"] == "INVALID_INPUT"
    res = _run_cli(["--stdin"], stdin=json.dumps(payload))
    assert res.returncode == 2 and json.loads(res.stdout)["code"] == "INVALID_INPUT"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
