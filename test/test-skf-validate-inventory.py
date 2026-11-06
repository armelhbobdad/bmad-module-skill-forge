"""Unit tests for src/skf-test-skill/scripts/validate-inventory.py.

Validates the subagent-inventory schema check (kinds, required fields,
cross-check-mismatch shape, fence stripping, CLI exit codes) that
coverage-check.md delegates to instead of validating in-prompt, the run
files (--input reads the saved response, so an apostrophe never meets a
shell; --output writes the validated inventory), the docs-only completeness
count (#540: a missing description is incomplete, never invalid), the
shared whole-name match (`get` is found in neither `target` nor `getAll`),
and the §1a ground-truth spot-check folded into the script (#598 item 5):
the first, middle and last names after a sort, looked up as whole names in
SKILL.md and the listed reference files, so an export named `$state` or
`a.b` is neither a shell variable nor a regex, and an absent name makes the
inventory invalid.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "skf-test-skill"
    / "scripts"
    / "validate-inventory.py"
)

spec = importlib.util.spec_from_file_location("validate_inventory", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_valid_minimal():
    raw = json.dumps({"exports": [{"name": "foo", "kind": "function"}], "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is True
    assert r["violations"] == []
    assert r["rejectedCount"] == 0
    assert r["exportsCount"] == 1
    assert r["inventory"]["exports"][0]["name"] == "foo"


def test_valid_empty_exports():
    raw = json.dumps({"exports": [], "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is True
    assert r["exportsCount"] == 0
    assert r["inventory"] is not None


def test_fence_stripped_json_object():
    raw = "```json\n" + json.dumps({"exports": [{"name": "A", "kind": "class"}], "cross_check_mismatches": []}) + "\n```"
    r = mod.validate_inventory(raw)
    assert r["valid"] is True
    assert r["inventory"]["exports"][0]["kind"] == "class"


def test_fence_stripped_no_lang_tag():
    raw = "```\n" + json.dumps({"exports": [{"name": "A", "kind": "class"}], "cross_check_mismatches": []}) + "\n```"
    r = mod.validate_inventory(raw)
    assert r["valid"] is True


def test_not_json():
    r = mod.validate_inventory("this is not json at all")
    assert r["valid"] is False
    assert any("not valid JSON" in v for v in r["violations"])
    assert r["inventory"] is None


def test_missing_exports_key():
    raw = json.dumps({"cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert any("exports" in v for v in r["violations"])


def test_exports_wrong_type():
    raw = json.dumps({"exports": "nope", "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert any("exports" in v for v in r["violations"])


def test_missing_cross_check_key():
    raw = json.dumps({"exports": [{"name": "x", "kind": "function"}]})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert any("cross_check_mismatches" in v for v in r["violations"])


def test_bad_kind_rejected():
    raw = json.dumps({"exports": [{"name": "x", "kind": "widget"}], "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert r["rejectedCount"] == 1
    assert r["inventory"] is None


def test_empty_name_rejected():
    raw = json.dumps({"exports": [{"name": "", "kind": "function"}], "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert r["rejectedCount"] == 1


def test_non_dict_export_rejected():
    raw = json.dumps({"exports": ["justastring"], "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert r["rejectedCount"] == 1


def test_rejected_count_multiple():
    raw = json.dumps(
        {
            "exports": [
                {"name": "ok", "kind": "function"},
                {"name": "", "kind": "class"},
                {"name": "bad", "kind": "widget"},
                "notadict",
            ],
            "cross_check_mismatches": [],
        }
    )
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert r["rejectedCount"] == 3
    assert r["exportsCount"] == 4


def test_all_kinds_accepted():
    exports = [{"name": f"n{i}", "kind": k} for i, k in enumerate(mod.VALID_KINDS)]
    raw = json.dumps({"exports": exports, "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is True
    assert r["rejectedCount"] == 0


@pytest.mark.parametrize("form", ["short", "Partial", "", True, ["partial"]],
                         ids=["short", "capitalized", "empty", "boolean", "list"])
def test_a_signature_form_is_partial_or_full(form):
    """#816: the optional `signature_form` says whether the skill labels its form partial. `partial` and `full`
    pass (a null counts as absent), and score-signatures.py finds them in the inventory; any other value is a
    violation naming the entry."""
    for good in ("partial", "full", None):
        entry = {"name": "Canvas", "kind": "function", "params": "{ of }", "return_type": "JSX.Element",
                 "signature_form": good}
        r = mod.validate_inventory(json.dumps({"exports": [entry], "cross_check_mismatches": []}))
        assert r["valid"] is True and r["violations"] == [], good
        assert r["inventory"]["exports"][0]["signature_form"] == good
    raw = json.dumps({"exports": [{"name": "ok", "kind": "function"},
                                  {"name": "Canvas", "kind": "function", "signature_form": form}],
                      "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False and r["inventory"] is None and r["rejectedCount"] == 0
    assert r["violations"] == [f"exports[1] (`Canvas`): `signature_form` must be `partial` or `full` when present, "
                               f"not {json.dumps(form)}"]


def test_a_bad_signature_form_fails_the_cli_and_writes_no_inventory(tmp_path):
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(json.dumps({"exports": [{"name": "Canvas", "kind": "function", "signature_form": "short"}],
                                     "cross_check_mismatches": []}).encode("utf-8"))
    output = tmp_path / "inventory.json"
    output.write_bytes(b"{}")
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(output)],
                       capture_output=True, text=True)
    assert p.returncode == 2
    assert any("`signature_form`" in v for v in json.loads(p.stdout)["violations"])
    assert not output.exists()


def test_cross_check_missing_fields():
    raw = json.dumps(
        {
            "exports": [{"name": "x", "kind": "function"}],
            "cross_check_mismatches": [{"export": "x", "skill_md_line": 1}],
        }
    )
    r = mod.validate_inventory(raw)
    assert r["valid"] is False
    assert any("missing field" in v for v in r["violations"])


def test_cross_check_all_fields_ok():
    raw = json.dumps(
        {
            "exports": [{"name": "x", "kind": "function"}],
            "cross_check_mismatches": [
                {
                    "export": "x",
                    "skill_md_line": 1,
                    "reference_file": "references/a.md",
                    "reference_line": 2,
                    "issue": "sig mismatch",
                }
            ],
        }
    )
    r = mod.validate_inventory(raw)
    assert r["valid"] is True


def _cross_check(**fields):
    """An inventory with one cross-check mismatch: its export, reference side and issue, plus `fields`. The issue is
    a mismatch by the rules: a typed form claims its list is complete, and leaves out `dataset`."""
    entry = {"export": "run_tasks_parallel", "reference_file": "references/b.md", "reference_line": 5,
             "issue": "references/a.md shows (tasks: list[Task], data: Any, dataset: str) -> None, references/b.md "
                      "(tasks: list[Task], data: Any) -> None"}
    return json.dumps({"exports": [{"name": "run_tasks_parallel", "kind": "function"}],
                       "cross_check_mismatches": [entry | fields]})


def _violation(**fields) -> str:
    r = mod.validate_inventory(_cross_check(**fields))
    assert r["valid"] is False and r["inventory"] is None
    [violation] = r["violations"]
    assert violation.startswith("cross_check_mismatches[0]"), violation
    return violation


def test_cross_check_between_two_references_is_valid():
    """#841: the split-body cross-check compares two reference files the body does not settle, so their
    contradiction is one entry, the one that sorts first as `other_file` at `other_line` in place of
    `skill_md_line`. Before, the validator required `skill_md_line` and refused the pair."""
    r = mod.validate_inventory(_cross_check(other_file="references/a.md", other_line=3))
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["cross_check_mismatches"][0]["other_file"] == "references/a.md"
    # a JSON null counts as absent, so a null `skill_md_line` beside a reference pair is no second side
    assert mod.validate_inventory(_cross_check(skill_md_line=None, other_file="references/a.md",
                                               other_line=3))["valid"] is True


@pytest.mark.parametrize("fields, needle", [
    ({}, "missing its other side"),
    ({"skill_md_line": 1, "other_file": "references/a.md", "other_line": 3}, "gives two other sides"),
    ({"other_file": "references/a.md"}, "missing field(s): other_line"),
    ({"other_line": 3}, "missing field(s): other_file"),
    ({"other_file": None, "other_line": 3}, "missing field(s): other_file"),
    ({"other_file": "references/a.md", "other_line": None}, "missing field(s): other_line"),
], ids=["neither", "both", "other-file-alone", "other-line-alone", "null-other-file", "null-other-line"])
def test_cross_check_needs_exactly_one_other_side(fields, needle):
    """An entry names one other side: the SKILL.md body's `skill_md_line`, or `other_file` and `other_line`. Each
    violation names both shapes, so the re-dispatched subagent knows what to write."""
    violation = _violation(**fields)
    assert needle in violation, violation
    assert ("`skill_md_line` (the SKILL.md body) or `other_file` and `other_line` (a second reference file)"
            in violation), violation


@pytest.mark.parametrize("field, value", [
    ("other_file", 3), ("other_file", ""), ("other_file", "SKILL.md"), ("other_file", "metadata.json"),
    ("other_file", "/elsewhere/references/a.md"), ("other_file", "references/../SKILL.md"),
    ("reference_file", None), ("reference_file", "SKILL.md"), ("reference_file", ""),
], ids=["other-int", "other-empty", "other-skill-md", "other-metadata", "other-absolute-outside",
        "other-escapes", "reference-null", "reference-skill-md", "reference-empty"])
def test_each_file_of_a_pair_is_a_reference_of_the_package(field, value):
    """`reference_file` on every entry and `other_file` on a pair are `references/*.md` files of the package: never
    SKILL.md (the body side is `skill_md_line`), another file, an empty or non-string value, or a path outside it."""
    fields = {"other_file": "references/a.md", "other_line": 3} if field == "other_file" else {"skill_md_line": 4}
    violation = _violation(**(fields | {field: value}))
    assert (f"`{field}` must be a `references/*.md` file of the skill package, not {json.dumps(value)}"
            in violation), violation


def test_each_file_of_a_pair_is_normalized_to_its_package_path(tmp_path):
    """`./references/a.md`, a backslash path and an absolute path inside --skill-package are checked, ordered and
    echoed as the package names them, so a rerun titles the gap one way."""
    (tmp_path / "references").mkdir()
    (tmp_path / "SKILL.md").write_bytes(b"# demo\n\nrun_tasks_parallel(tasks)\n")
    for other, ref in (("./references/a.md", "references\\b.md"),
                       (str(tmp_path / "references" / "a.md"), "./references/b.md")):
        r = mod.validate_inventory(_cross_check(other_file=other, other_line=3, reference_file=ref), tmp_path)
        assert r["valid"] is True, r["violations"]
        [entry] = r["inventory"]["cross_check_mismatches"]
        assert (entry["other_file"], entry["reference_file"]) == ("references/a.md", "references/b.md")
    # normalized first: `./references/c.md` is `references/c.md`, which sorts after `references/b.md`
    assert "sorts after" in _violation(other_file="./references/c.md", other_line=3)


@pytest.mark.parametrize("field, value", [
    ("skill_md_line", True), ("skill_md_line", "42"), ("skill_md_line", 0), ("other_line", -1),
    ("other_line", "3"), ("other_line", False), ("reference_line", "5"), ("reference_line", None),
], ids=["body-bool", "body-string", "body-zero", "other-negative", "other-string", "other-bool",
        "reference-string", "reference-null"])
def test_each_line_is_a_positive_integer(field, value):
    fields = {"skill_md_line": 4} if field == "skill_md_line" else {"other_file": "references/a.md", "other_line": 3}
    violation = _violation(**(fields | {field: value}))
    assert f"`{field}` must be a line number (a positive integer), not {json.dumps(value)}" in violation, violation


@pytest.mark.parametrize("other_file, other_line, relation", [
    ("references/b.md", 5, "names the same line as"),
    ("references/b.md", 9, "sorts after"),
    ("references/c.md", 3, "sorts after"),
    ("references/b.md.bak.md", 1, "sorts after"),
], ids=["same-place", "same-file-later-line", "later-path", "longer-path"])
def test_cross_check_other_file_sorts_before_reference_file(other_file, other_line, relation):
    """A pair of references is written in one order, so a rerun titles one gap one way and the ledger, which tells
    gaps apart by their title, records it once: (`other_file`, `other_line`) sorts first in codepoint order, path
    then line."""
    violation = _violation(other_file=other_file, other_line=other_line)
    assert (f'`other_file` "{other_file}" at `other_line` {other_line} {relation} `reference_file` "references/b.md" '
            "at `reference_line` 5: a pair of references gives the one that sorts first in codepoint order, by path "
            "and then line, as `other_file` and `other_line`") in violation, violation


def test_one_export_documented_twice_in_one_reference_is_a_pair_of_its_lines():
    """The same file at two lines is a pair too, ordered by line; codepoint order puts `B` before `a`."""
    assert mod.validate_inventory(_cross_check(other_file="references/b.md", other_line=2))["valid"] is True
    assert mod.validate_inventory(_cross_check(other_file="references/B.md", other_line=9))["valid"] is True


def test_the_cli_refuses_a_reference_pair_out_of_order(tmp_path):
    """The CLI exits 2 on the order violation and leaves no inventory behind, as for any schema violation."""
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_cross_check(other_file="references/z.md", other_line=3).encode("utf-8"))
    output = tmp_path / "inventory.json"
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(output)],
                       capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr
    assert any("sorts after `reference_file`" in v for v in json.loads(p.stdout)["violations"])
    assert not output.exists()


def test_json_array_not_object():
    r = mod.validate_inventory(json.dumps([1, 2, 3]))
    assert r["valid"] is False
    assert any("not a JSON object" in v for v in r["violations"])


def test_cli_stdin_valid_exit0():
    raw = json.dumps({"exports": [{"name": "x", "kind": "function"}], "cross_check_mismatches": []})
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"], input=raw, capture_output=True, text=True
    )
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert out["valid"] is True


def test_cli_stdin_invalid_exit2():
    raw = json.dumps({"exports": [{"name": "x", "kind": "widget"}], "cross_check_mismatches": []})
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"], input=raw, capture_output=True, text=True
    )
    assert p.returncode == 2
    out = json.loads(p.stdout)
    assert out["valid"] is False


def test_cli_no_input_exit1():
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"], input="", capture_output=True, text=True
    )
    assert p.returncode == 1


# --------------------------------------------------------------------------
# Run files: the saved response by path, the validated inventory to a file
# --------------------------------------------------------------------------


def test_cli_input_file_with_an_apostrophe_validates(tmp_path):
    response = tmp_path / "inventory-response.txt"
    raw = "```json\n" + json.dumps({
        "exports": [{"name": "parse", "kind": "function", "params": "text: str", "return_type": "Doc",
                     "description": "Parses the user's input; it's \"lenient\" about $HOME and `backticks`."}],
        "cross_check_mismatches": []}) + "\n```\n"
    response.write_bytes(raw.encode("utf-8"))
    out_path = tmp_path / "run" / "inventory.json"
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(out_path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["exports"][0]["description"].startswith("Parses the user's input; it's")
    assert written == json.loads(p.stdout)["inventory"]


def test_cli_invalid_input_file_removes_a_stale_inventory(tmp_path):
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(json.dumps({"exports": [{"name": "x", "kind": "widget"}],
                                     "cross_check_mismatches": []}).encode("utf-8"))
    out_path = tmp_path / "inventory.json"
    out_path.write_bytes(b'{"exports": []}')
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(out_path)],
                       capture_output=True, text=True)
    assert p.returncode == 2 and not out_path.exists()


def test_cli_missing_input_file_exits_1(tmp_path):
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(tmp_path / "absent.txt")],
                       capture_output=True, text=True)
    assert p.returncode == 1 and "cannot read --input" in p.stderr


# --------------------------------------------------------------------------
# Completeness (#540)
# --------------------------------------------------------------------------


def test_a_missing_description_is_incomplete_not_invalid():
    raw = json.dumps({"exports": [
        {"name": "fmt", "kind": "function", "params": "", "return_type": "str", "description": "Formats."},
        {"name": "go", "kind": "function", "params": [], "return_type": "None"},
        {"name": "Cfg", "kind": "class", "description": "  "},
        {"name": "MAX", "kind": "constant", "description": "Limit."},
        {"name": "hop", "kind": "method", "description": "Hops."},
    ], "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is True
    assert r["completeness"] == {"total": 5, "complete": 2, "incomplete": [
        {"name": "go", "kind": "function", "missing": ["description"]},
        {"name": "Cfg", "kind": "class", "missing": ["description"]},
        {"name": "hop", "kind": "method", "missing": ["params", "return_type"]},
    ]}


def test_no_completeness_for_an_invalid_inventory():
    assert "completeness" not in mod.validate_inventory("not json")


# --------------------------------------------------------------------------
# The shared whole-name match
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text, found", [
    ("call get(url)", True),
    ("the target", False),
    ("getAll()", False),
    ("forget", False),
    ("client.get", True),
    ("`get`", True),
], ids=["call", "target", "getAll", "forget", "member", "code-span"])
def test_get_is_found_only_as_a_whole_name(text, found):
    assert mod.names_present(["get"], text) == (["get"] if found else [])


def test_a_name_that_ends_in_punctuation_still_matches_inside():
    assert mod.names_present([".then", "Type::method", "$state", "wraps a"],
                             "promise.then(Type::method) $state; it wraps a session") == \
        ["$state", ".then", "Type::method", "wraps a"]
    assert mod.names_present(["$state"], "my$state") == []


def test_load_doc_text_reads_skill_md_then_sorted_references(tmp_path):
    (tmp_path / "references" / "sub").mkdir(parents=True)
    (tmp_path / "SKILL.md").write_bytes(b"one")
    (tmp_path / "references" / "b.md").write_bytes(b"three")
    (tmp_path / "references" / "a.md").write_bytes("tw\u00f6".encode("utf-8"))
    (tmp_path / "references" / "sub" / "c.md").write_bytes(b"never")
    assert mod.load_doc_text(str(tmp_path)) == "one\ntw\u00f6\nthree"


# --- §1a spot-check (--skill-package) ----------------------------------------


def _package(tmp_path, skill_md, references=None):
    pkg = tmp_path / "pkg"
    (pkg / "references").mkdir(parents=True)
    (pkg / "SKILL.md").write_bytes(skill_md.encode("utf-8"))
    for name, text in (references or {}).items():
        (pkg / "references" / name).write_bytes(text.encode("utf-8"))
    return pkg


def _inventory(*names, references=None):
    data = {"exports": [{"name": n, "kind": "function"} for n in names], "cross_check_mismatches": []}
    if references is not None:
        data["references"] = references
    return json.dumps(data)


@pytest.mark.parametrize("names, sampled", [
    (["c", "a", "b", "e", "d"], ["a", "c", "e"]),
    (["b", "a"], ["a", "b"]),
    (["only"], ["only"]),
    ([], []),
], ids=["five", "two", "one", "none"])
def test_the_sample_is_first_middle_and_last_after_a_sort(names, sampled):
    assert mod.sample_names([{"name": n} for n in names]) == sampled


def test_dollar_and_dotted_names_are_found_as_written(tmp_path):
    """A double-quoted grep reads `$state` as an empty pattern and `a.b` as a regex: the
    script matches both as fixed strings, so neither a lookalike nor a longer name counts."""
    pkg = _package(tmp_path, "# Demo\n\nlet count = $state(0);\n", {"api.md": "Call `a.b(x)`.\n"})
    r = mod.validate_inventory(_inventory("$state", "a.b", references=["references/api.md"]), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["spotCheck"] == {"sampled": ["$state", "a.b"], "absent": [],
                              "files": ["SKILL.md", "references/api.md"], "unread": []}


@pytest.mark.parametrize("text", ["x$state and aXb\n", "$stated, ca.b and a.bc\n"],
                         ids=["lookalikes", "longer-names"])
def test_a_lookalike_never_counts(tmp_path, text):
    pkg = _package(tmp_path, text)
    r = mod.validate_inventory(_inventory("$state", "a.b"), pkg)
    assert r["valid"] is False and r["inventory"] is None
    assert r["spotCheck"]["absent"] == ["$state", "a.b"]
    assert any("`$state` is listed as an export" in v for v in r["violations"])


def test_a_name_only_a_listed_reference_writes_is_found(tmp_path):
    """A split-body skill documents some exports only in references/*.md."""
    pkg = _package(tmp_path, "# Demo\n", {"api.md": "`helper()` helps.\n"})
    assert mod.validate_inventory(_inventory("helper", references=["references/api.md"]), pkg)["valid"] is True
    # A reference the subagent did not list is not read.
    assert mod.validate_inventory(_inventory("helper"), pkg)["valid"] is False


def test_a_listed_file_outside_the_package_is_never_read(tmp_path):
    (tmp_path / "outside.md").write_bytes(b"`helper()`\n")
    pkg = _package(tmp_path, "# Demo\n")
    r = mod.validate_inventory(_inventory("helper", references=["../outside.md", "references/gone.md"]), pkg)
    assert r["valid"] is False
    assert r["spotCheck"]["unread"] == ["../outside.md", "references/gone.md"]


def test_no_spot_check_without_the_package_or_for_an_invalid_schema(tmp_path):
    pkg = _package(tmp_path, "# Demo\n")
    assert "spotCheck" not in mod.validate_inventory(_inventory("ghost"))
    bad = json.dumps({"exports": [{"name": "ghost", "kind": "nope"}], "cross_check_mismatches": []})
    assert "spotCheck" not in mod.validate_inventory(bad, pkg)


def test_cli_spot_check_failure_exits_2_and_removes_the_inventory(tmp_path):
    pkg = _package(tmp_path, "# Demo\n`real()`\n")
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_inventory("real", "ghost").encode("utf-8"))
    out = tmp_path / "inventory.json"
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["spotCheck"]["absent"] == ["ghost"]
    assert not out.exists()


def test_cli_a_package_without_skill_md_exits_1(tmp_path):
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_inventory("real").encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package",
                           str(tmp_path / "missing")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 1 and "--skill-package" in proc.stderr


# --- Floor (#790) ---------------------------------------------------------------

FLOOR_SCRIPT = SCRIPT.parent / "load-coverage-inputs.py"


def _floor_origin(file, line, form, signature=None):
    origin = {"file": file, "line": line, "form": form}
    if signature is not None:
        origin["signature"] = signature
    return origin


def _floor(*names):
    """A floor whose names each come with origins: (name, [(file, line, form[, signature]), ...])."""
    return {"files": ["SKILL.md"], "names": [
        {"name": name, "kindLabel": None, "origins": [_floor_origin(*origin) for origin in origins]}
        for name, origins in names]}


def _entries(*entries, references=None):
    data = {"exports": [{"name": n, "kind": k} for n, k in entries], "cross_check_mismatches": []}
    if references is not None:
        data["references"] = references
    return json.dumps(data)


def test_a_dropped_floor_name_fails_and_removes_the_inventory(tmp_path):
    """The floor load-coverage-inputs.py writes, read by path: a name SKILL.md writes in an export table that the
    inventory leaves out is a violation naming it and its origin, exit 2, and no inventory file is left."""
    pkg = _package(tmp_path, "# Demo\n\n| Export | Kind |\n| --- | --- |\n| `fetchData`, `fetchAll` | function |\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_inventory("fetchData").encode("utf-8"))
    out = tmp_path / "inventory.json"
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [
        "floor: `fetchAll` is documented at SKILL.md:5 (table-row), but no inventory entry lists it"]
    assert result["floor"] == {"names": 2, "checked": 2, "absent": ["fetchAll"]}
    assert result["spotCheck"]["absent"] == [] and result["inventory"] is None
    assert not out.exists()


def test_any_entry_keeps_a_floor_name_whatever_its_kind(tmp_path):
    """Kinds stay the reader's: a skill's own `| get | method |` row is kept by a `method` entry."""
    pkg = _package(tmp_path, "# Demo\n\n| Function | Kind |\n| --- | --- |\n| `get` | method |\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    r = mod.validate_inventory(_entries(("get", "method")), pkg, mod.read_floor(floor))
    assert r["valid"] is True, r["violations"]
    assert r["floor"] == {"names": 1, "checked": 1, "absent": []}


FORM_TABLE = ("# Demo\n\n| Export | Kind | Signature |\n| --- | --- | --- |\n"
              "| `fetchData` | function | `(url: string, retries?: number) => Promise<Data>` |\n")
FORM = {"params": "url: string, retries?: number", "return_type": "Promise<Data>"}
FORM_VIOLATION = ('floor: `fetchData` is documented at SKILL.md:5 (table-row) with the signature '
                  '{"params": "url: string, retries?: number", "return_type": "Promise<Data>"}, but no inventory '
                  'entry of that name carries it; copy it as given')


def _signed(*entries, references=None):
    """An inventory of (name, kind, fields) entries."""
    data = {"exports": [{"name": n, "kind": k, **fields} for n, k, fields in entries], "cross_check_mismatches": []}
    if references is not None:
        data["references"] = references
    return json.dumps(data)


def test_a_floor_form_the_inventory_changes_fails(tmp_path):
    """#888: an origin's `signature`, the form the skill writes there in a fixed form, must be carried by an entry
    of that name, whatever its kind: each field it pins non-blank read as form_key reads it (whitespace runs as one
    space, a list joined with `, `, a blank or null field as absent; a `usage_signature` is not read), a blank
    pinned return leaving the entry's free. An inventory whose only entry of the name writes another form fails
    with exit 2, the violation naming the origin and the signature, and leaves no inventory file; the form copied,
    beside an extra prose entry, validates. Another name's entry carrying the form does not carry it, each checked
    origin of a name needs its own form, a name left out fails on its name and its form, and an unlisted
    reference's form is not checked."""
    pkg = _package(tmp_path, FORM_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(floor.read_bytes())["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", FORM)]
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(("fetchData", "function", {"params": "url: string",
                                                            "return_type": "Promise<Data>"})).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [FORM_VIOLATION]
    assert result["floor"] == {"names": 1, "checked": 1, "absent": []} and result["inventory"] is None
    assert not out.exists()

    read = mod.read_floor(floor)
    prose = ("fetchData", "function", {"params": "url", "return_type": "Promise<Data>", "description": "In prose."})
    for copied in ({"params": "url:  string,\n  retries?: number", "return_type": " Promise<Data> "},
                   {"params": ["url: string", "retries?: number"], "return_type": "Promise<Data>"},
                   {**FORM, "usage_signature": "fetchData(url)", "signature_form": "full"}):
        for kind in ("function", "constant"):
            r = mod.validate_inventory(_signed(prose, ("fetchData", kind, copied)), pkg, read)
            assert r["valid"] is True, (copied, kind, r["violations"])
            assert r["floor"] == {"names": 1, "checked": 1, "absent": []}
    # A blank pinned field leaves the entry's free: an origin with no return is carried with or without one.
    floor = _floor(("connect", [("SKILL.md", 3, "heading", {"params": "url", "return_type": ""})]))
    for returned in (None, "", "Socket"):
        r = mod.validate_inventory(_signed(("connect", "function", {"params": "url", "return_type": returned})),
                                   floor=floor)
        assert r["valid"] is True, (returned, r["violations"])
    r = mod.validate_inventory(_signed(("connect", "function", {"params": "url, opts", "return_type": "Socket"})),
                               floor=floor)
    assert r["violations"] == [
        'floor: `connect` is documented at SKILL.md:3 (heading) with the signature {"params": "url", '
        '"return_type": ""}, but no inventory entry of that name carries it; copy it as given']
    # Another name's entry carrying the form does not carry it for this name.
    floor = _floor(("fetchData", [("SKILL.md", 5, "table-row", FORM)]))
    r = mod.validate_inventory(_signed(("fetchData", "function", {"params": "url"}), ("getData", "function", FORM)),
                               floor=floor)
    assert r["valid"] is False and r["violations"] == [FORM_VIOLATION]
    # Each checked origin of a name needs its own form; an unlisted reference's origin needs none.
    other = {"params": "url: string", "return_type": "Data"}
    floor = _floor(("fetchData", [("SKILL.md", 5, "table-row", FORM), ("references/api.md", 8, "heading", other),
                                  ("references/b.md", 2, "heading", {"params": "x", "return_type": "Y"})]))
    listed = ["references/api.md"]
    r = mod.validate_inventory(_signed(("fetchData", "function", FORM), references=listed), floor=floor)
    assert r["valid"] is False and r["violations"] == [
        'floor: `fetchData` is documented at references/api.md:8 (heading) with the signature {"params": '
        '"url: string", "return_type": "Data"}, but no inventory entry of that name carries it; copy it as given']
    r = mod.validate_inventory(_signed(("fetchData", "function", FORM), ("fetchData", "function", other),
                                       references=listed), floor=floor)
    assert r["valid"] is True and r["floor"] == {"names": 1, "checked": 1, "absent": []}
    # A name left out fails on its name and on its form; an unlisted reference's form is not checked.
    floor = _floor(("fetchData", [("SKILL.md", 5, "table-row", FORM)]),
                   ("helper", [("references/api.md", 2, "heading", {"params": "x", "return_type": ""})]))
    r = mod.validate_inventory(_signed(("other", "function", {})), floor=floor)
    assert r["valid"] is False and r["floor"] == {"names": 2, "checked": 1, "absent": ["fetchData"]}
    assert r["violations"] == [
        "floor: `fetchData` is documented at SKILL.md:5 (table-row), but no inventory entry lists it",
        FORM_VIOLATION]


def test_a_pinned_form_after_shared_members_is_carried(tmp_path):
    """#888: the contract has each of several names whose members the skill states once carry that shared text,
    then `; `, then its own members in its `params`. The floor pins the row's own Signature cell, so a `params`
    that opens with the shared text and `; ` carries it, as the pinned form copied alone does; a `params` that
    only ends with the pinned text, with no `; ` before it, does not."""
    pkg = _package(tmp_path, "# Demo\n\nEach model has the base fields `id, scope=Scope()`.\n\n"
                             "| Class | Kind | Signature |\n| --- | --- | --- |\n"
                             "| `Note` | class | `(content, title=None)` |\n| `Task` | class | `(title, done=False)` |\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert [(n["name"], [o.get("signature") for o in n["origins"]]) for n in read["names"]] == [
        ("Note", [{"params": "content, title=None", "return_type": ""}]),
        ("Task", [{"params": "title, done=False", "return_type": ""}])]
    for note, task in (("id, scope=Scope(); content, title=None", "id, scope=Scope(); title, done=False"),
                       ("content, title=None", ["id", "scope=Scope(); title", "done=False"])):
        r = mod.validate_inventory(_signed(("Note", "class", {"params": note}), ("Task", "class", {"params": task})),
                                   pkg, read)
        assert r["valid"] is True, (note, task, r["violations"])
    r = mod.validate_inventory(_signed(("Note", "class", {"params": "id, content, title=None"}),
                                       ("Task", "class", {"params": "title, done=False"})), pkg, read)
    assert r["valid"] is False and r["violations"] == [
        'floor: `Note` is documented at SKILL.md:7 (table-row) with the signature {"params": "content, title=None", '
        '"return_type": ""}, but no inventory entry of that name carries it; copy it as given']


def test_a_floor_name_of_an_unlisted_reference_is_not_checked():
    """A floor name counts only through SKILL.md or a reference the inventory lists; the first such origin is
    the one the violation names."""
    floor = _floor(("helper", [("references/api.md", 4, "table-row")]),
                   ("Client", [("references/api.md", 9, "heading"), ("references/b.md", 2, "declaration")]))
    r = mod.validate_inventory(_entries(("other", "function")), floor=floor)
    assert r["valid"] is True and r["floor"] == {"names": 2, "checked": 0, "absent": []}
    r = mod.validate_inventory(_entries(("other", "function"), references=["./references/b.md"]), floor=floor)
    assert r["valid"] is False and r["floor"] == {"names": 2, "checked": 1, "absent": ["Client"]}
    assert r["violations"] == [
        "floor: `Client` is documented at references/b.md:2 (declaration), but no inventory entry lists it"]


def test_an_absolute_reference_path_is_matched_to_its_floor_origin(tmp_path):
    """A `references` item given as an absolute path inside the package counts as its package-relative path."""
    pkg = _package(tmp_path, "# Demo\n\n`other()` runs.\n", {"api.md": "### `Client`\n"})
    floor = _floor(("Client", [("references/api.md", 1, "heading")]))
    listed = [str((pkg / "references" / "api.md").resolve())]
    r = mod.validate_inventory(_entries(("other", "function"), references=listed), pkg, floor)
    assert r["floor"] == {"names": 1, "checked": 1, "absent": ["Client"]}
    assert r["violations"] == [
        "floor: `Client` is documented at references/api.md:1 (heading), but no inventory entry lists it"]
    r = mod.validate_inventory(_entries(("other", "function"), ("Client", "class"), references=listed), pkg, floor)
    assert r["valid"] is True and r["floor"]["absent"] == []
    # Outside the package an absolute path names no origin.
    (tmp_path / "elsewhere" / "references").mkdir(parents=True)
    outside = [str((tmp_path / "elsewhere" / "references" / "api.md").resolve())]
    r = mod.validate_inventory(_entries(("other", "function"), references=outside), pkg, floor)
    assert r["floor"] == {"names": 1, "checked": 0, "absent": []}


def test_an_inventory_that_keeps_the_floor_passes():
    floor = _floor(("Options", [("SKILL.md", 7, "heading")]), ("fetchData", [("SKILL.md", 3, "table-row")]))
    r = mod.validate_inventory(_entries(("fetchData", "function"), ("Options", "interface")), floor=floor)
    assert r["valid"] is True and r["violations"] == []
    assert r["floor"] == {"names": 2, "checked": 2, "absent": []}
    # No floor check without a floor, or for an inventory the schema refused.
    assert "floor" not in mod.validate_inventory(_entries(("fetchData", "function")))
    assert "floor" not in mod.validate_inventory(_entries(("fetchData", "nope")), floor=floor)


@pytest.mark.parametrize("content", [
    None, b"{not json", b'{"names": [{"name": "x"}]}', b"[]",
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"params": ["a"], "return_type": ""}}]}]}',
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"params": "a"}}]}]}',
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"params": "a", "return_type": "", "usage_signature": "a()"}}]}]}',
], ids=["missing", "not-json", "no-origins", "not-an-object", "bad-signature", "signature-without-a-return",
        "signature-with-an-extra-key"])
def test_an_unreadable_floor_file_exits_1(tmp_path, content):
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_inventory("real").encode("utf-8"))
    floor = tmp_path / "inventory-floor.json"
    if content is not None:
        floor.write_bytes(content)
    out = tmp_path / "inventory.json"
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(out),
                           "--floor", str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 1 and "--floor" in proc.stderr and proc.stdout == ""
    assert not out.exists()


def test_the_citation_scan_is_the_verifiers(tmp_path):
    """The skill citations gap-ledger.py's homonym pick and score-signatures.py's plan read (#781), and the files
    they read them in, are the verifier's."""
    path = SCRIPT.parents[2] / "shared" / "scripts" / "skf-verify-provenance-completeness.py"
    text = SCRIPT.read_text(encoding="utf-8")
    for name in ("_SKILL_CITATION_RE", "skill_markdown_files"):
        assert f"Keep identical to {name} in skf-verify-provenance-completeness.py." in text, name
    pin = importlib.util.spec_from_file_location("skf_pin_verify_provenance_citations", path)
    verifier = importlib.util.module_from_spec(pin)
    pin.loader.exec_module(verifier)
    assert (mod._SKILL_CITATION_RE.pattern, mod._SKILL_CITATION_RE.flags) == (
        verifier._SKILL_CITATION_RE.pattern, verifier._SKILL_CITATION_RE.flags)
    skill = tmp_path / "skill"
    for rel in ("SKILL.md", "references/b.md", "references/a.md", "references/deep/c.md", "references/x.txt",
                "notes.md"):
        (skill / rel).parent.mkdir(parents=True, exist_ok=True)
        (skill / rel).write_bytes(b"# x\n")
    assert mod.skill_markdown_files(skill) == verifier.skill_markdown_files(skill)
    assert [p.relative_to(skill).as_posix() for p in mod.skill_markdown_files(skill)] == [
        "SKILL.md", "references/a.md", "references/b.md", "references/deep/c.md"]
