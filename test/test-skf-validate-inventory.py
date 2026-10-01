"""Unit tests for src/skf-test-skill/scripts/validate-inventory.py.

Validates the subagent-inventory schema check (kinds, required fields,
cross-check-mismatch shape, fence stripping, CLI exit codes) that
coverage-check.md delegates to instead of validating in-prompt, the run
files (--input reads the saved response, so an apostrophe never meets a
shell; --output writes the validated inventory), the docs-only completeness
count (#540: a missing description is incomplete, never invalid) and the
shared whole-name match (`get` is found in neither `target` nor `getAll`).
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
