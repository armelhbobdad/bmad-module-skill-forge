"""Unit tests for src/skf-test-skill/scripts/validate-inventory.py.

Validates the subagent-inventory schema check (kinds, required fields,
cross-check-mismatch shape, fence stripping, CLI exit codes) that
coverage-check.md delegates to instead of validating in-prompt.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

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
