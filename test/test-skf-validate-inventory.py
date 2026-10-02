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
