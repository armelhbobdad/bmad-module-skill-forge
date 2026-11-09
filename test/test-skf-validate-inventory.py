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
inventory invalid. Each entry with a compared form is asked for its place,
`at` (#918): a line of SKILL.md or a listed reference that writes its name,
the floor's origin where the floor pins its signature, and the form's own
citations are read there. A missing or bad `at` is a warning, never a
refusal: the bad one is dropped, so plan leaves that form unbound.
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


def test_an_entry_key_the_contract_does_not_define_is_refused(tmp_path):
    """#1001: an entry key outside the contract, such as `usage` written for `usage_signature`, passed with no
    violation, and score-signatures.py reads only SIGNATURE_FIELDS, so the documented form was never compared. Each
    entry with such a key is now a violation naming the entry, its unknown keys and the keys an entry carries, so the
    re-dispatched reader spreads its fields into them; an entry using every contract key passes, null-valued too."""
    every = {"name": "Client", "kind": "class", "description": "A client.", "params": "api_key, timeout=5",
             "return_type": "Client", "usage_signature": "Client(api_key, timeout=5)", "signature_form": "full",
             "at": "SKILL.md:6", "owner": "sdk", "methods": ["close()"], "properties": ["api_key"],
             "fields": ["timeout"]}
    assert set(every) == set(mod.ENTRY_KEYS) and len(mod.ENTRY_KEYS) == 12
    for entry in (every, dict.fromkeys(mod.ENTRY_KEYS) | {"name": "Client", "kind": "class"}):
        r = mod.validate_inventory(json.dumps({"exports": [entry], "cross_check_mismatches": []}))
        assert r["valid"] is True and r["violations"] == [], entry
    usage = {"name": "Client", "kind": "class", "usage": "client = Client(api_key=\"k\", timeout=5)",
             "description": "A client.", "at": "SKILL.md:6"}
    keys = ", ".join(f"`{k}`" for k in mod.ENTRY_KEYS[:-1]) + f" and `{mod.ENTRY_KEYS[-1]}`"
    raw = json.dumps({"exports": [{"name": "ok", "kind": "function"}, usage,
                                  {"kind": "class", "signature": "Client(api_key)", "line": 6}],
                      "cross_check_mismatches": []})
    r = mod.validate_inventory(raw)
    assert r["valid"] is False and r["inventory"] is None and r["rejectedCount"] == 1
    assert r["violations"][1:] == [
        f"exports[1] (`Client`): `usage` is not a key the contract defines; an entry carries only {keys}",
        f"exports[2]: `signature` and `line` are not keys the contract defines; an entry carries only {keys}"]
    # The CLI exits 2 and writes no inventory, with or without --floor (the floor check runs once the schema passed).
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(json.dumps({"exports": [usage], "cross_check_mismatches": []}).encode("utf-8"))
    floor = tmp_path / "inventory-floor.json"
    floor.write_bytes(json.dumps({"names": []}).encode("utf-8"))
    output = tmp_path / "inventory.json"
    for extra in ([], ["--floor", str(floor)]):
        output.write_bytes(b"{}")
        p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(output), *extra],
                           capture_output=True, text=True)
        assert p.returncode == 2, p.stderr
        assert [v for v in json.loads(p.stdout)["violations"] if "`usage`" in v], p.stdout
        assert not output.exists()


@pytest.mark.parametrize("form", ["short", "Partial", "", True, ["partial"]],
                         ids=["short", "capitalized", "empty", "boolean", "list"])
def test_a_signature_form_is_partial_or_full(form):
    """#816: the optional `signature_form` says whether the skill labels its form partial. `partial` and `full`
    pass (a null counts as absent), and score-signatures.py finds them in the inventory; any other value is a
    violation naming the entry."""
    for good in ("partial", "full", None):
        entry = {"name": "Canvas", "kind": "function", "params": "{ of }", "return_type": "JSX.Element",
                 "signature_form": good, "at": "SKILL.md:3"}
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


def test_a_method_pair_keeps_its_owner():
    """#1035: a pair of a `method`'s forms gives the `owner` its entries give, so the split-body Source reads that
    owner's member and never a same-named root record (`cognee.delete` for `agents.delete`). The validator checks no
    `owner`, and the inventory it writes keeps it for the Source to read."""
    entry = {"export": "delete", "owner": "agents", "skill_md_line": 3, "reference_file": "references/a.md",
             "reference_line": 7, "issue": "SKILL.md shows delete(user=None), references/a.md delete(agent_id, "
                                           "user=None)"}
    raw = json.dumps({"exports": [{"name": "delete", "kind": "method", "owner": "agents"}],
                      "cross_check_mismatches": [entry]})
    r = mod.validate_inventory(raw)
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["inventory"]["cross_check_mismatches"] == [entry]


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


EXPORT_RULE = ("`export` must name an inventory entry, by its `name` (a `method`'s bare `name`, or `{owner}.{name}` "
               "for one that gives an `owner`), not ")


@pytest.mark.parametrize("export", ["Widget", "", 3, None, ["run_tasks_parallel"], "run_tasks_parallel "],
                         ids=["no-entry", "empty", "number", "null", "list", "trailing-space"])
def test_a_mismatch_export_names_an_inventory_entry(export):
    """#1033: a mismatch's `export` was checked only for its presence, so a name no entry has, an empty string or a
    number passed, and §5b titled a High split-body gap with it. It is now one violation naming the value and the
    spellings an `export` takes, so the re-dispatched reader can correct it."""
    violation = _violation(export=export, skill_md_line=4)
    assert f"{EXPORT_RULE}{json.dumps(export)}" in violation, violation


def test_a_method_mismatch_names_its_bare_name_or_its_owner_and_name():
    """An entry's `name` is an `export` (a dotted one as written), and a `method` entry that gives an `owner` is also
    named `{owner}.{name}`. Another owner, a function under an owner and a method with no `owner` are refused."""
    exports = [{"name": "run", "kind": "function"}, {"name": "datasets.list_data", "kind": "function"},
               {"name": "get", "kind": "method", "owner": "Client"}, {"name": "put", "kind": "method"}]

    def checked(export):
        mismatch = {"export": export, "skill_md_line": 4, "reference_file": "references/b.md", "reference_line": 5,
                    "issue": "SKILL.md shows (a), references/b.md (a, b)"}
        return mod.validate_inventory(json.dumps({"exports": exports, "cross_check_mismatches": [mismatch]}))

    for export in ("run", "datasets.list_data", "get", "Client.get", "put"):
        r = checked(export)
        assert r["valid"] is True, (export, r["violations"])
        assert r["inventory"]["cross_check_mismatches"][0]["export"] == export
    for export in ("Other.get", "Client.run", "Client.put", ".put", "list_data"):
        r = checked(export)
        assert r["valid"] is False and r["inventory"] is None, export
        assert r["violations"] == [f"cross_check_mismatches[0]: {EXPORT_RULE}{json.dumps(export)}"], r["violations"]


@pytest.mark.parametrize("export, code", [("Widget", 2), ("", 2), (3, 2), ("a", 0)])
def test_the_cli_refuses_a_mismatch_export_no_entry_has_on_a_package(tmp_path, export, code):
    """#1033's two-file package: SKILL.md writes `a(x)` at line 5, references/api.md writes `b(y)` at line 3, and the
    inventory lists `a`. A mismatch naming no entry exits 2 and leaves no inventory, as any schema violation does;
    one naming `a` passes."""
    pkg = tmp_path / "pkg"
    (pkg / "references").mkdir(parents=True)
    (pkg / "SKILL.md").write_bytes(b"# Demo\n\nIntro.\n\n`a(x)` runs it.\n")
    (pkg / "references" / "api.md").write_bytes(b"# API\n\n`b(y)` runs it.\n")
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(json.dumps({
        "exports": [{"name": "a", "kind": "function"}], "references": ["references/api.md"],
        "cross_check_mismatches": [{"export": export, "skill_md_line": 5, "reference_file": "references/api.md",
                                    "reference_line": 3, "issue": "SKILL.md shows (x), references/api.md (y)"}],
    }).encode("utf-8"))
    output = tmp_path / "inventory.json"
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                        "--output", str(output)], capture_output=True, text=True)
    assert p.returncode == code, p.stdout + p.stderr
    result = json.loads(p.stdout)
    if code:
        assert result["violations"] == [f"cross_check_mismatches[0]: {EXPORT_RULE}{json.dumps(export)}"]
        assert not output.exists()
    else:
        assert result["valid"] is True and output.exists()


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
                     "description": "Parses the user's input; it's \"lenient\" about $HOME and `backticks`.",
                     "at": "SKILL.md:12"}],
        "cross_check_mismatches": []}) + "\n```\n"
    response.write_bytes(raw.encode("utf-8"))
    out_path = tmp_path / "run" / "inventory.json"
    p = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--output", str(out_path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["exports"][0]["description"].startswith("Parses the user's input; it's")
    assert written == mod.validate_inventory(raw)["inventory"]
    assert json.loads(p.stdout)["output"] == str(out_path)


def test_output_prints_the_verdict_without_the_inventory(tmp_path):
    """#1040: with --output the inventory goes to the file alone, so stdout keeps the verdict, the violations and
    warnings the step reads there and the counts, never a copy of the inventory or its completeness, which no step
    reads, and names the file; null when the inventory is refused and no file is left. Without --output stdout is
    the whole result, as before."""
    exports = [{"name": f"fn{i}", "kind": "function", "description": "Does it."} for i in range(40)]
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(json.dumps({"exports": exports, "cross_check_mismatches": []}).encode("utf-8"))
    out_path = tmp_path / "run" / "inventory.json"
    command = [sys.executable, str(SCRIPT), "--input", str(response), "--output", str(out_path)]
    p = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout) == {"valid": True, "violations": [], "warnings": [], "rejectedCount": 0,
                                    "exportsCount": 40, "output": str(out_path)}
    assert "fn7" not in p.stdout and "Does it." not in p.stdout
    whole = subprocess.run(command[:-2], capture_output=True, text=True, encoding="utf-8")
    assert whole.returncode == 0, whole.stdout + whole.stderr
    full = json.loads(whole.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == full["inventory"]
    assert full["completeness"]["total"] == 40 and len(whole.stdout) > 10 * len(p.stdout)
    response.write_bytes(json.dumps({"exports": exports + [{"name": "x", "kind": "widget"}],
                                     "cross_check_mismatches": []}).encode("utf-8"))
    p = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 2, p.stdout + p.stderr
    refused = json.loads(p.stdout)
    assert refused["valid"] is False and refused["violations"] and refused["output"] is None
    assert "inventory" not in refused and not out_path.exists()


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
        {"name": "fmt", "kind": "function", "params": "", "return_type": "str", "description": "Formats.",
         "at": "SKILL.md:3"},
        {"name": "go", "kind": "function", "params": [], "return_type": "None", "at": "SKILL.md:4"},
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


def test_a_function_written_as_a_call_carries_its_form():
    """#916: the contract records a call expression whole in `usage_signature`, never in `params`, so a function or
    method entry with a non-blank `usage_signature` (or a list with a non-blank usage) and no `params` carries its
    form: it is complete in the validator's count and in docs-only Export Coverage, which reconcile-coverage.py
    scores with this rule. A blank or empty usage carries none, and a `return_type` left out is still missing."""
    mount = {"name": "mount", "kind": "function", "usage_signature": "h = await coco.mount(fn)",
             "return_type": "Handle", "description": "Mounts.", "at": "SKILL.md:3"}
    assert mod.missing_fields(mount) == []
    assert mod.missing_fields({**mount, "kind": "method"}) == []
    assert mod.missing_fields({**mount, "usage_signature": ["", "mount(fn)"]}) == []
    for blank in ("  ", [], [" "], None):
        assert mod.missing_fields({**mount, "usage_signature": blank}) == ["params"], blank
    exports = [mount,
               {"name": "stop", "kind": "function", "usage_signature": "await coco.stop()", "description": "Stops.",
                "at": "SKILL.md:4"},
               {"name": "run", "kind": "function", "usage_signature": "", "return_type": "None",
                "description": "Runs."}]
    r = mod.validate_inventory(json.dumps({"exports": exports, "cross_check_mismatches": []}))
    assert r["valid"] is True, r["violations"]
    assert r["completeness"] == {"total": 3, "complete": 1, "incomplete": [
        {"name": "stop", "kind": "function", "missing": ["return_type"]},
        {"name": "run", "kind": "function", "missing": ["params"]},
    ]}
    path = SCRIPT.parent / "reconcile-coverage.py"
    pin = importlib.util.spec_from_file_location("skf_pin_reconcile_docs_only", path)
    reconcile = importlib.util.module_from_spec(pin)
    pin.loader.exec_module(reconcile)
    out = reconcile.reconcile({"denominatorSource": "docsOnly", "exports": exports})
    assert (out["denominator"], out["documented"], out["incomplete"]) == (3, 1, r["completeness"]["incomplete"])


PROSE_CALL_SKILL = ("# Demo\n\n`fetchComponent(componentName)` loads a component's source.\n\n"
                    "| Export | Kind | Description |\n| --- | --- | --- |\n"
                    "| `add` | function | `add(componentName, options)` writes it to the project. |\n")


def test_a_prose_call_with_arguments_is_left_to_the_reader_as_a_usage(tmp_path):
    """#1016 (oms-uitripled): the contract records a call with arguments and no prefix in running text or a
    description cell (`fetchComponent(componentName)`, `add(componentName, options)`) whole in `usage_signature`,
    so its argument names are never compared with the declaration's parameter names. The floor reads no prose and
    no Description cell, so it pins no signature at either place and the reader's routing decides: an inventory
    that records both as usages, each at its own line, passes --floor (exit 0) with no violation or warning, each
    entry missing only its return type, and is written as given. No script changed."""
    pkg = _package(tmp_path, PROSE_CALL_SKILL)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert [(n["name"], n["origins"]) for n in mod.read_floor(floor)["names"]] == [
        ("add", [_floor_origin("SKILL.md", 7, "table-row")])], "neither prose call is pinned a signature"
    exports = [("fetchComponent", "function", {"usage_signature": "fetchComponent(componentName)",
                                               "description": "Loads a component's source.", "at": "SKILL.md:3"}),
               ("add", "function", {"usage_signature": "add(componentName, options)",
                                    "description": "Writes it to the project.", "at": "SKILL.md:7"})]
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(*exports).encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [] and result["warnings"] == [], (result["violations"], result["warnings"])
    assert result["floor"] == {"names": 1, "checked": 1, "absent": []}
    written = json.loads(out.read_bytes())
    assert mod.completeness(written["exports"])["incomplete"] == [
        {"name": name, "kind": "function", "missing": ["return_type"]} for name in ("fetchComponent", "add")]
    assert written["exports"] == [
        {"name": name, "kind": kind, **fields} for name, kind, fields in exports], "each usage kept as given"


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


# --- crossChecked (#920): the Exports Cross-Checked count ------------------------
#
# The names two or more of the spot-check's files write, each file counted once by its resolved path, a name once
# however many entries give it; written into the inventory, so --output writes it.


def test_a_split_body_counts_the_names_two_files_write(tmp_path):
    """`alpha` only in SKILL.md, `beta` in SKILL.md and x.md, `gamma` in x.md and in y.md's prose: two names."""
    pkg = _package(tmp_path, "# Demo\n\n`alpha()` and `beta()`.\n",
                   {"x.md": "`beta(n)` and `gamma(n)`.\n", "y.md": "Then call gamma to finish.\n"})
    refs = ["references/x.md", "references/y.md"]
    r = mod.validate_inventory(_inventory("alpha", "beta", "gamma", references=refs), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 2, "names": ["beta", "gamma"]}
    # The spot-check's result is the same as before the count.
    assert r["spotCheck"] == {"sampled": ["alpha", "beta", "gamma"], "absent": [],
                              "files": ["SKILL.md", "references/x.md", "references/y.md"], "unread": []}


def test_a_name_one_file_writes_many_times_is_not_counted(tmp_path):
    pkg = _package(tmp_path, "# Demo\n\n`solo()`, `solo(n)` and solo again.\n", {"x.md": "# Nothing here\n"})
    r = mod.validate_inventory(_inventory("solo", references=["references/x.md"]), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 0, "names": []}


def test_a_homonym_counts_once(tmp_path):
    """`get` as a function and as a method, both files write it: one name."""
    pkg = _package(tmp_path, "# Demo\n\n`get(key)` reads a key.\n", {"x.md": "`client.get(url)` fetches.\n"})
    raw = json.dumps({"exports": [{"name": "get", "kind": "function"},
                                  {"name": "get", "kind": "method", "owner": "client"}],
                      "cross_check_mismatches": [], "references": ["references/x.md"]})
    r = mod.validate_inventory(raw, pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 1, "names": ["get"]}


def test_a_lookalike_in_the_second_file_does_not_count(tmp_path):
    pkg = _package(tmp_path, "# Demo\n\n`get(key)` reads a key.\n", {"x.md": "`getAll()` and the `target`.\n"})
    r = mod.validate_inventory(_inventory("get", references=["references/x.md"]), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 0, "names": []}


@pytest.mark.parametrize("references", [None, []], ids=["absent", "empty"])
def test_no_references_count_nothing(tmp_path, references):
    pkg = _package(tmp_path, "# Demo\n\n`run()` and `run(n)`.\n", {"x.md": "`run()`\n"})
    r = mod.validate_inventory(_inventory("run", references=references), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 0, "names": []}


def test_one_file_under_two_spellings_is_one_file(tmp_path):
    """A reference listed twice, or SKILL.md listed again, is read under each spelling as before, but counted once."""
    pkg = _package(tmp_path, "# Demo\n\n`body()`\n", {"x.md": "`twice()`\n"})
    refs = ["references/x.md", "./references/x.md", "./SKILL.md"]
    r = mod.validate_inventory(_inventory("body", "twice", references=refs), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 0, "names": []}
    assert r["spotCheck"]["files"] == ["SKILL.md", "references/x.md", "./references/x.md", "./SKILL.md"]


def test_an_unread_file_is_not_counted(tmp_path):
    (tmp_path / "outside.md").write_bytes(b"`helper()`\n")
    pkg = _package(tmp_path, "# Demo\n\n`helper()`\n")
    r = mod.validate_inventory(_inventory("helper", references=["../outside.md", "references/gone.md"]), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 0, "names": []}
    assert r["spotCheck"]["unread"] == ["../outside.md", "references/gone.md"]


@pytest.mark.parametrize("given", [{"count": 99, "names": ["ghost"]}, "7", None], ids=["object", "string", "null"])
def test_a_readers_cross_checked_is_replaced_with_the_package_and_removed_without(tmp_path, given):
    pkg = _package(tmp_path, "# Demo\n\n`both()`\n", {"x.md": "`both()`\n"})
    data = json.loads(_inventory("both", references=["references/x.md"]))
    data["crossChecked"] = given
    with_package = mod.validate_inventory(json.dumps(data), pkg)
    assert with_package["valid"] is True, with_package["violations"]
    assert with_package["inventory"]["crossChecked"] == {"count": 1, "names": ["both"]}
    without = mod.validate_inventory(json.dumps(data))
    assert without["valid"] is True and "crossChecked" not in without["inventory"]


def test_no_cross_checked_without_the_package():
    r = mod.validate_inventory(_inventory("both", references=["references/x.md"]))
    assert r["valid"] is True and "crossChecked" not in r["inventory"]
    assert "spotCheck" not in r


def test_cli_output_carries_cross_checked_and_stdout_names_it(tmp_path):
    pkg = _package(tmp_path, "# Demo\n\n`shared()` and `own()`.\n", {"x.md": "`shared(n)`\n"})
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_inventory("own", "shared", references=["references/x.md"]).encode("utf-8"))
    out = tmp_path / "run" / "inventory.json"
    command = [sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg), "--output", str(out)]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["crossChecked"] == {"count": 1, "names": ["shared"]}
    assert written == mod.validate_inventory(response.read_text(encoding="utf-8"), pkg)["inventory"]
    stdout = json.loads(proc.stdout)
    assert (stdout["output"], stdout["spotCheck"]["absent"], "inventory" in stdout) == (str(out), [], False)
    # An invalid inventory still leaves no file.
    response.write_bytes(_inventory("own", "shared", "ghost", references=["references/x.md"]).encode("utf-8"))
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 2 and json.loads(proc.stdout)["output"] is None
    assert not out.exists()


def test_a_name_a_file_cites_only_in_a_citation_path_is_not_counted(tmp_path):
    """`config` is written in SKILL.md alone and `client` in no file: their other spellings sit inside `[SRC:]` and
    `[AST:]` paths, which write no name (the module's documented-name match). `fetch` is written in two references."""
    pkg = _package(tmp_path, "`config()` [SRC:src/client.py:L3]\n",
                   {"a.md": "`fetch(url)` [SRC:src/config.py:L9]\n",
                    "b.md": "`fetch(url, timeout)` [AST:src/client.py:L12]\n"})
    r = mod.validate_inventory(_inventory("client", "config", "fetch",
                                          references=["references/a.md", "references/b.md"]), pkg)
    assert r["valid"] is True, r["violations"]
    assert r["inventory"]["crossChecked"] == {"count": 1, "names": ["fetch"]}


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
    assert result["spotCheck"]["absent"] == [] and result["output"] is None
    assert not out.exists()


def test_a_dropped_bracket_generic_floor_name_fails(tmp_path):
    """#915: an export table's first cell that writes a Python or Go generic (`App[P, R]`) pins its name, so an
    inventory that leaves it out is a violation naming it and its origin, exit 2, and no inventory file is left."""
    pkg = _package(tmp_path, "# Demo\n\n| Export | Kind |\n| --- | --- |\n| `App[P, R]` | class |\n"
                             "| `ContextKey[T]` | class |\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_inventory("ContextKey").encode("utf-8"))
    out = tmp_path / "inventory.json"
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [
        "floor: `App` is documented at SKILL.md:5 (table-row), but no inventory entry lists it"]
    assert result["floor"] == {"names": 2, "checked": 2, "absent": ["App"]}
    assert result["spotCheck"]["absent"] == [] and result["output"] is None
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
                  'entry of that name carries it; copy it as given, with `at` "SKILL.md:5"')
# An entry at the table row's place, the floor origin's (#918).
AT_ROW = {"at": "SKILL.md:5"}


def _signed(*entries, references=None):
    """An inventory of (name, kind, fields) entries."""
    data = {"exports": [{"name": n, "kind": k, **fields} for n, k, fields in entries], "cross_check_mismatches": []}
    if references is not None:
        data["references"] = references
    return json.dumps(data)


def test_a_floor_form_the_inventory_changes_fails(tmp_path):
    """#888: an origin's `signature`, the form the skill writes there in a fixed form, must be carried by an entry
    of that name, whatever its kind: each field it pins non-blank read as form_key reads it (whitespace runs as one
    space, a list joined with `, `, a blank or null field as absent; a `usage_signature` beside a pinned `params` is
    not read), a blank pinned return leaving the entry's free. An inventory whose only entry of the name writes
    another form fails with exit 2, the violation naming the origin and the signature, and leaves no inventory file;
    the form copied, beside an extra prose entry, validates. Another name's entry carrying the form does not carry
    it, each checked origin of a name needs its own form, a name left out fails on its name and its form, and an
    unlisted reference's form is not checked."""
    pkg = _package(tmp_path, FORM_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(floor.read_bytes())["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", FORM)]
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(("fetchData", "function", {"params": "url: string", "return_type": "Promise<Data>",
                                                            **AT_ROW})).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [FORM_VIOLATION]
    assert result["floor"] == {"names": 1, "checked": 1, "absent": []} and result["output"] is None
    assert not out.exists()

    read = mod.read_floor(floor)
    prose = ("fetchData", "function", {"params": "url", "return_type": "Promise<Data>", "description": "In prose.",
                                       **AT_ROW})
    for copied in ({"params": "url:  string,\n  retries?: number", "return_type": " Promise<Data> ", **AT_ROW},
                   {"params": ["url: string", "retries?: number"], "return_type": "Promise<Data>", **AT_ROW},
                   {**FORM, "usage_signature": "fetchData(url)", "signature_form": "full", **AT_ROW}):
        for kind in ("function", "constant"):
            r = mod.validate_inventory(_signed(prose, ("fetchData", kind, copied)), pkg, read)
            assert r["valid"] is True, (copied, kind, r["violations"])
            assert r["floor"] == {"names": 1, "checked": 1, "absent": []}
    # A blank pinned field leaves the entry's free: an origin with no return is carried with or without one.
    floor = _floor(("connect", [("SKILL.md", 3, "heading", {"params": "url", "return_type": ""})]))
    for returned in (None, "", "Socket"):
        r = mod.validate_inventory(_signed(("connect", "function", {"params": "url", "return_type": returned,
                                                                    "at": "SKILL.md:3"})), floor=floor)
        assert r["valid"] is True, (returned, r["violations"])
    r = mod.validate_inventory(_signed(("connect", "function", {"params": "opts", "return_type": "Socket",
                                                                "at": "SKILL.md:3"})), floor=floor)
    assert r["violations"] == [
        'floor: `connect` is documented at SKILL.md:3 (heading) with the signature {"params": "url", '
        '"return_type": ""}, but no inventory entry of that name carries it; copy it as given, with `at` '
        '"SKILL.md:3"']
    # Another name's entry carrying the form does not carry it for this name.
    floor = _floor(("fetchData", [("SKILL.md", 5, "table-row", FORM)]))
    r = mod.validate_inventory(_signed(("fetchData", "function", {"params": "url", **AT_ROW}),
                                       ("getData", "function", {**FORM, **AT_ROW})), floor=floor)
    assert r["valid"] is False and r["violations"] == [FORM_VIOLATION]
    # Each checked origin of a name needs its own form; an unlisted reference's origin needs none.
    other = {"params": "url: string", "return_type": "Data"}
    floor = _floor(("fetchData", [("SKILL.md", 5, "table-row", FORM), ("references/api.md", 8, "heading", other),
                                  ("references/b.md", 2, "heading", {"params": "x", "return_type": "Y"})]))
    listed = ["references/api.md"]
    r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, **AT_ROW}), references=listed),
                               floor=floor)
    assert r["valid"] is False and r["violations"] == [
        'floor: `fetchData` is documented at references/api.md:8 (heading) with the signature {"params": '
        '"url: string", "return_type": "Data"}, but no inventory entry of that name carries it; copy it as given, '
        'with `at` "references/api.md:8"']
    r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, **AT_ROW}),
                                       ("fetchData", "function", {**other, "at": "references/api.md:8"}),
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
    that opens with the shared text and `; ` carries it, as the pinned form copied alone does. #1028: a `params`
    that only ends with the pinned text, with no `; ` before it, carries it too, since it holds the pinned members
    in their order after another (test_a_pinned_form_among_shared_members_is_carried_in_order)."""
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
        r = mod.validate_inventory(_signed(("Note", "class", {"params": note, "at": "SKILL.md:7"}),
                                           ("Task", "class", {"params": task, "at": "SKILL.md:8"})), pkg, read)
        assert r["valid"] is True, (note, task, r["violations"])
    r = mod.validate_inventory(_signed(("Note", "class", {"params": "id, content, title=None", "at": "SKILL.md:7"}),
                                       ("Task", "class", {"params": "title, done=False", "at": "SKILL.md:8"})),
                               pkg, read)
    assert r["valid"] is True and r["warnings"] == [], (r["violations"], r["warnings"])


def test_a_pinned_form_among_shared_members_is_carried_in_order(tmp_path):
    """#1028: where the skill puts a name's own member before the members it states once for several names
    (`leading`), the contract has the entry write the name's whole list in the skill's order, a pinned place
    included. A pinned `params` is carried when the entry's members, cut at top-level commas, hold each pinned
    member in the pinned order, others before, among or after them: the whole list passes `--floor` (exit 0), as a
    list `params` and the `; ` shape do, while a list that reorders or drops a pinned member is refused. A member
    with a nested comma (`Dict[str, int]`) is one member, and a pinned `usage_signature` is still carried only as
    given or after the shared text and `; `."""
    pkg = _package(tmp_path, "# Demo\n\nBoth models take the base fields `id, scope=Scope()` right after their leading "
                             "first argument.\n\n| Class | Kind | Signature |\n| --- | --- | --- |\n"
                             "| `Note` | class | `(content, title=None)` |\n"
                             "| `Task` | class | `(title, done=False)` |\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert [(n["name"], [o.get("signature") for o in n["origins"]]) for n in read["names"]] == [
        ("Note", [{"params": "content, title=None", "return_type": ""}]),
        ("Task", [{"params": "title, done=False", "return_type": ""}])]
    task = ("Task", "class", {"params": "title, id, scope=Scope(), done=False", "at": "SKILL.md:8"})
    response = tmp_path / "inventory-response.txt"
    response.write_bytes(_signed(("Note", "class", {"params": "content, id, scope=Scope(), title=None",
                                                    "at": "SKILL.md:7"}), task).encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--floor", str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["valid"] is True and result["violations"] == [] and result["warnings"] == []
    for note in (["content", "id", "scope=Scope()", "title=None"], "content, title=None, id, scope=Scope(),",
                 "id, scope=Scope(); content, title=None"):
        r = mod.validate_inventory(_signed(("Note", "class", {"params": note, "at": "SKILL.md:7"}), task), pkg, read)
        assert r["valid"] is True and r["warnings"] == [], (note, r["violations"], r["warnings"])
    # A pinned member out of its order, or dropped, is refused.
    for note in ("title=None, content, id, scope=Scope()", "content, id, scope=Scope()",
                 "content, id, scope=Scope(), title=Scope()"):
        r = mod.validate_inventory(_signed(("Note", "class", {"params": note, "at": "SKILL.md:7"}), task), pkg, read)
        assert r["valid"] is False and r["violations"] == [
            'floor: `Note` is documented at SKILL.md:7 (table-row) with the signature {"params": "content, '
            'title=None", "return_type": ""}, but no inventory entry of that name carries it; copy it as given, '
            'with `at` "SKILL.md:7"'], note
    # A nested comma is inside its member: `content: Dict[str, id, int]` is no `content: Dict[str, int]`.
    nested = _floor(("Note", [("SKILL.md", 3, "heading", {"params": "content: Dict[str, int], title=None",
                                                          "return_type": ""})]))
    for note, valid in (("id, content: Dict[str, int], scope=Scope(), title=None", True),
                        ("content: Dict[str, id, int], title=None", False)):
        r = mod.validate_inventory(_signed(("Note", "class", {"params": note, "at": "SKILL.md:3"})), floor=nested)
        assert r["valid"] is valid, (note, r["violations"])
    # A pinned usage form is carried as given or after the shared text and `; `, never among other members.
    usage = _floor(("Client", [("SKILL.md", 3, "heading", {"usage_signature": "new Client(opts)",
                                                           "return_type": ""})]))
    for given, valid in (("new Client(opts)", True), ("id; new Client(opts)", True), ("id, new Client(opts)", False)):
        r = mod.validate_inventory(_signed(("Client", "class", {"usage_signature": given, "at": "SKILL.md:3"})),
                                   floor=usage)
        assert r["valid"] is valid, (given, r["violations"])


def test_a_longer_list_at_another_place_never_carries_a_pin(tmp_path):
    """#1028 review: the in-order carry is the pinned place's own, for the entry whose `at` is the origin. A longer
    form of the name written at another place (a reference's prose line), or one with no `at`, is another form: it
    never carries the pin, so an inventory that leaves the row's form out, or drops a pinned member there, is still
    refused, and it keeps its own `at`; at a labelled pin it is no unlabelled copy of the pinned form, so the
    labelled copy at the row stays valid beside it, with the missing-`at` warning alone."""
    row = "# Lib\n\n| Function | {} |\n|---|---|\n| `connect` | `connect(host: str, port: int)` |\n"
    prose = {"api.md": "# API\n\nCall `connect(host: str, port: int, *, tls: bool)` to open a connection.\n"}
    pkg = _package(tmp_path / "plain", row.format("Signature"), prose)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert read["names"][0]["origins"] == [
        _floor_origin("SKILL.md", 5, "table-row", {"params": "host: str, port: int", "return_type": ""})]
    longer = {"params": "host: str, port: int, *, tls: bool", "at": "references/api.md:3"}
    refs = ["references/api.md"]
    for entries in ([longer], [{"params": "host: str", "at": "SKILL.md:5"}, longer]):
        r = mod.validate_inventory(_signed(*(("connect", "function", e) for e in entries), references=refs), pkg,
                                   read)
        assert r["valid"] is False and r["warnings"] == [] and r["violations"] == [
            'floor: `connect` is documented at SKILL.md:5 (table-row) with the signature {"params": "host: str, '
            'port: int", "return_type": ""}, but no inventory entry of that name carries it; copy it as given, with '
            '`at` "SKILL.md:5"'], entries
    r = mod.validate_inventory(_signed(("connect", "function", {"params": "host: str, port: int"}),
                                       ("connect", "function", longer), references=refs), pkg, read)
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["warnings"] == [f"exports[0] (`connect`) carries a form but no `at`, so {UNBOUND}"]
    assert [e.get("at") for e in r["inventory"]["exports"]] == [None, "references/api.md:3"]

    pkg = _package(tmp_path / "labelled", row.format("Signature (simplified)"), prose)
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert read["names"][0]["origins"][0]["signature"] == {
        "params": "host: str, port: int", "return_type": "", "signature_form": "partial"}
    labelled = {"params": "host: str, port: int", "signature_form": "partial", "at": "SKILL.md:5"}
    for at, warning in ((None, f"exports[1] (`connect`) carries a form but no `at`, so {UNBOUND}"),
                        ("SKILL.md:1", 'exports[1] (`connect`): `at` "SKILL.md:1" is a line that does not write '
                                       f"`connect`; it is dropped and {UNBOUND}")):
        other = {"params": "host: str, port: int, *, tls: bool", **({} if at is None else {"at": at})}
        r = mod.validate_inventory(_signed(("connect", "function", labelled), ("connect", "function", other),
                                           references=refs), pkg, read)
        assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [warning], (at, r["violations"])


PROPS_SKILL = ("# Demo\n\n## `connect(host, port)`\n\nOpens a connection.\n\n### Canvas\n\n"
               "| Prop | Type | Default | Description |\n| --- | --- | --- | --- |\n"
               "| `of` | `ModuleExport` | | The story. |\n| `layout` | `L` | `\"padded\"` | The layout. |\n")


def test_a_pinned_call_keeps_its_params_and_a_props_table_is_placed_at_its_heading(tmp_path):
    """#916: the contract records a call expression whole as a `usage_signature`, except at a place the floor gives
    a `signature`: a heading that writes `connect(host, port)` is pinned `{"params": "host, port"}`, so an entry
    that writes it only as a usage carries no pinned form and is refused (exit 2, no inventory file), while the
    pinned `params` at the heading validates. #931: a props table is a place of its own, at the heading above it
    that writes the name: its entry there has no warning, and one placed on a row, which writes a prop and not the
    name, has its `at` dropped with a warning, the inventory still valid. No script changed for either."""
    pkg = _package(tmp_path, PROPS_SKILL)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert [(n["name"], n["origins"]) for n in read["names"]] == [
        ("connect", [_floor_origin("SKILL.md", 3, "heading", {"params": "host, port", "return_type": ""})])], (
        "the heading's call is pinned; the props table pins nothing")
    canvas = ("Canvas", "function", {"params": "{ of: ModuleExport; layout: L }", "description": "",
                                     "at": "SKILL.md:7"})
    usage = ("connect", "function", {"usage_signature": "connect(host, port)", "description": "", "at": "SKILL.md:3"})
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(usage, canvas).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [
        'floor: `connect` is documented at SKILL.md:3 (heading) with the signature {"params": "host, port", '
        '"return_type": ""}, but no inventory entry of that name carries it; copy it as given, with `at` '
        '"SKILL.md:3"']
    assert result["output"] is None and not out.exists()
    pinned = ("connect", "function", {"params": "host, port", "description": "", "at": "SKILL.md:3"})
    r = mod.validate_inventory(_signed(pinned, canvas), pkg, read)
    assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (r["violations"], r["warnings"])
    assert [e["at"] for e in r["inventory"]["exports"]] == ["SKILL.md:3", "SKILL.md:7"]
    row = (canvas[0], canvas[1], {**canvas[2], "at": "SKILL.md:11"})
    r = mod.validate_inventory(_signed(pinned, row), pkg, read)
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["warnings"] == ['exports[1] (`Canvas`): `at` "SKILL.md:11" is a line that does not write `Canvas`; '
                             f"it is dropped and {mod.UNBOUND}"]
    assert "at" not in r["inventory"]["exports"][1]


FACTORY_SKILL = ("# Demo\n\n| Export | Kind | Signature |\n| --- | --- | --- |\n"
                 "| `badgeVariants` | const | `const badgeVariants = cva(…)` |\n\n"
                 "```ts\n// [SRC:src/button.ts:L5]\nexport const buttonVariants = cva(…)\n```\n\n"
                 "```ts\nconst onSubmit = make(…)\n```\n")


def test_a_const_written_only_as_its_factory_call_has_no_pinned_form(tmp_path):
    """#1019: the contract gives a `const` that a place writes only as the call that builds its function
    (oms-uitripled's `const badgeVariants = cva(…)`) no `params`, `return_type` or `usage_signature` there, so
    its entry is never compared, whatever the factory returns (an in-tree `make` that returns
    `(event: Event) => void` included). The floor pins no signature at such a place, a Signature cell or a cited
    fenced declaration, and an uncited block gives no origin, so an inventory whose entries there carry no form
    passes --floor (exit 0) with no violation or warning and is written as given. No script changed."""
    pkg = _package(tmp_path, FACTORY_SKILL)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert [(n["name"], n["origins"]) for n in mod.read_floor(floor)["names"]] == [
        ("badgeVariants", [_floor_origin("SKILL.md", 5, "table-row")]),
        ("buttonVariants", [_floor_origin("SKILL.md", 9, "declaration")])], (
        "neither factory call is pinned a signature, and the uncited block gives no origin")
    names = ("badgeVariants", "buttonVariants", "onSubmit")
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(*[(name, "constant", {"description": ""}) for name in names]).encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [] and result["warnings"] == [], (result["violations"], result["warnings"])
    assert result["floor"] == {"names": 2, "checked": 2, "absent": []}
    assert json.loads(out.read_bytes())["exports"] == [
        {"name": name, "kind": "constant", "description": ""} for name in names], "no form is added or asked for"


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
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"usage_signature": "new x(a)"}}]}]}',
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"usage_signature": " ", "return_type": ""}}]}]}',
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"usage_signature": ["new x(a)"], "return_type": ""}}]}]}',
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"params": "a", "return_type": "", "signature_form": "full"}}]}]}',
    b'{"names": [{"name": "x", "origins": [{"file": "SKILL.md", "line": 1, "form": "heading", '
    b'"signature": {"params": "a", "return_type": "", "signature_form": 1}}]}]}',
], ids=["missing", "not-json", "no-origins", "not-an-object", "bad-signature", "signature-without-a-return",
        "signature-with-an-extra-key", "usage-without-a-return", "blank-usage", "usage-list",
        "signature-labelled-full", "signature-labelled-1"])
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
    assert content in (None, b"{not json") or "is not a floor" in proc.stderr, proc.stderr
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


# --- A form's place, `at`, and its own citations (#918) ---------------------------

# oms-cognee's two run_pipeline functions: a prose form cited to the lightweight runner, then its fenced block,
# whose citation stands on the first non-blank line after the closing fence.
PLACES_SKILL = ("# Demo\n\n"
                "`run_pipeline(tasks=None, data=None)` runs a dataset pipeline [AST:pipeline.py:L53].\n"
                "\n"
                "```python\n"
                "async def run_pipeline(\n"
                "    steps,\n"
                ")\n"
                "```\n"
                "\n"
                "[AST:run_pipeline.py:L37]\n")
PLACES_REFERENCE = ("### run_pipeline\n\n"
                    "| Export | Signature |\n| --- | --- |\n"
                    "| `run_pipeline` | `(steps, *, data=None)` |\n")


def _form_entry(at, name="run_pipeline", **fields):
    entry = {"name": name, "kind": "function", "params": "steps", "description": ""}
    if at is not None:
        entry["at"] = at
    return {**entry, **fields}


def _places(*entries, references=("references/api.md",)):
    return json.dumps({"exports": list(entries), "references": list(references), "cross_check_mismatches": []})


def test_each_form_gives_the_place_it_starts():
    """#918: an entry that carries a form `plan` compares gives `at`, "<path>:<line>" in SKILL.md or a listed
    reference, kept as the package names it. Without the package only its shape and its file are checked."""
    r = mod.validate_inventory(_places(_form_entry("./SKILL.md:3"), _form_entry("references\\api.md:5"),
                                       _form_entry(" SKILL.md:7 ", usage_signature="run_pipeline(steps)")))
    assert r["valid"] is True and r["warnings"] == [], r["violations"]
    assert [e["at"] for e in r["inventory"]["exports"]] == ["SKILL.md:3", "references/api.md:5", "SKILL.md:7"]


UNBOUND = "the form is compared as one whose citations name no declaration"


@pytest.mark.parametrize("entry", [
    {"name": "run", "kind": "function", "params": "a"},
    {"name": "run", "kind": "function", "params": ""},
    {"name": "run", "kind": "function", "params": []},
    {"name": "Card", "kind": "constant", "usage_signature": "<Card />"},
    {"name": "Note", "kind": "class", "params": "id; content"},
    {"name": "run", "kind": "function", "params": "a", "at": None},
    {"name": "withActions", "kind": "constant", "params": "storyFn: PartialStoryFn<T>", "return_type": "T['storyResult']"},
    {"name": "getTheme", "kind": "constant", "params": [], "return_type": "Theme"},
], ids=["params", "empty-function-params", "empty-list", "usage", "class-params", "null", "function-constant",
        "no-argument-function-constant"])
def test_an_entry_with_a_form_and_no_at_is_a_warning(entry):
    """#918: a form with no place is still compared, unbound, so the inventory stays valid and the entry is
    listed in `warnings`; a JSON null `at` is no `at`, and is left out of the inventory."""
    r = mod.validate_inventory(_places(entry))
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["warnings"] == [f"exports[0] (`{entry['name']}`) carries a form but no `at`, so {UNBOUND}"]
    assert "at" not in r["inventory"]["exports"][0]


@pytest.mark.parametrize("entry", [
    {"name": "get", "kind": "method", "params": "key"},
    {"name": "Cfg", "kind": "class", "params": ""},
    {"name": "MAX", "kind": "constant"},
    {"name": "parse", "kind": "function", "return_type": "Doc"},
    {"name": "Card", "kind": "constant", "usage_signature": "  "},
], ids=["method", "blank-class-params", "data-constant", "return-type-only", "blank-usage"])
def test_an_entry_plan_compares_no_form_of_needs_no_at(entry):
    r = mod.validate_inventory(_places(entry))
    assert r["valid"] is True and r["warnings"] == []
    assert mod.compared_form(entry) is False


@pytest.mark.parametrize("at, violation", [
    ("SKILL.md", "`at` must be \"<path>:<line>\""),
    ("SKILL.md:0", "`at` must be \"<path>:<line>\""),
    ("SKILL.md:L3", "`at` must be \"<path>:<line>\""),
    (":3", "`at` must be \"<path>:<line>\""),
    (3, "`at` must be \"<path>:<line>\""),
    ("README.md:1", "`at` names \"README.md\", no file the inventory reads"),
    ("references/other.md:1", "`at` names \"references/other.md\", no file the inventory reads"),
], ids=["no-line", "line-0", "an-L", "no-path", "a-number", "another-file", "an-unlisted-reference"])
def test_a_bad_at_is_dropped_with_a_warning(at, violation):
    """Any entry's `at`, one a method gives too, is "<path>:<line>" in a file the inventory reads. One that is not
    never refuses the inventory: it is dropped, so the inventory carries no bad `at`, and listed in `warnings`."""
    for entry, left in ((_form_entry(at), f"; it is dropped and {UNBOUND}"),
                        ({"name": "get", "kind": "method", "at": at}, "; it is dropped")):
        r = mod.validate_inventory(_places(entry))
        assert r["valid"] is True and r["violations"] == [], r["violations"]
        [message] = r["warnings"]
        assert message.startswith(f"exports[0] (`{entry['name']}`): ") and violation in message, message
        assert message.endswith(left), message
        assert "at" not in r["inventory"]["exports"][0]


@pytest.mark.parametrize("at, good", [
    ("SKILL.md:3", True),       # the prose line
    ("SKILL.md:6", True),       # the fenced block's declaration line
    ("SKILL.md:7", True),       # another line of the block, which writes the name
    ("references/api.md:5", True),  # the table row
    ("references/api.md:1", True),  # the heading
    ("SKILL.md:5", False),      # the opening fence: no line of the block's body
    ("SKILL.md:11", False),     # the citation line after the block
    ("SKILL.md:12", False),     # past the end
    ("references/api.md:3", False),
], ids=["prose", "declaration", "in-the-block", "table-row", "heading", "fence", "after-the-block", "past-the-end",
        "header-row"])
def test_an_at_is_a_line_that_writes_the_name(tmp_path, at, good):
    """#918: with the package, an `at` is a line of its file that writes the entry's name outside its citations,
    or a line in the body of a fenced block that writes it. Any other is dropped with a warning, and the inventory
    stays valid."""
    pkg = _package(tmp_path, PLACES_SKILL, {"api.md": PLACES_REFERENCE})
    r = mod.validate_inventory(_places(_form_entry(at)), pkg)
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    [entry] = r["inventory"]["exports"]
    if good:
        assert r["warnings"] == [] and entry["at"] == at
    else:
        [message] = r["warnings"]
        assert message.startswith(f"exports[0] (`run_pipeline`): `at` {json.dumps(at)} ")
        assert ("past the end of SKILL.md (11 lines)" in message if at == "SKILL.md:12"
                else "is a line that does not write `run_pipeline`" in message), message
        assert message.endswith(f"; it is dropped and {UNBOUND}") and "at" not in entry, message


def test_a_name_only_a_citation_writes_is_not_on_the_line(tmp_path):
    """A citation's path holds `run_pipeline` (`run_pipeline.py`): the name match reads the line without its
    citations, so the citation line after the block is not the form's place."""
    pkg = _package(tmp_path, PLACES_SKILL, {"api.md": PLACES_REFERENCE})
    r = mod.validate_inventory(_places(_form_entry("SKILL.md:11")), pkg)
    assert r["warnings"] == ["exports[0] (`run_pipeline`): `at` \"SKILL.md:11\" is a line that does not write "
                             f"`run_pipeline`; it is dropped and {UNBOUND}"]
    r = mod.validate_inventory(_places(_form_entry("SKILL.md:7", name="missing")), pkg)
    assert r["warnings"] == [
        "exports[0] (`missing`): `at` \"SKILL.md:7\" is a line that does not write `missing`, nor does the fenced "
        f"block that holds it; it is dropped and {UNBOUND}"]


def test_an_at_in_a_listed_file_that_cannot_be_read_is_dropped(tmp_path):
    pkg = _package(tmp_path, PLACES_SKILL)
    r = mod.validate_inventory(_places(_form_entry("references/api.md:1"), references=["references/api.md"]), pkg)
    assert r["valid"] is True and "at" not in r["inventory"]["exports"][0]
    assert r["warnings"] == ["exports[0] (`run_pipeline`): `at` \"references/api.md:1\" names a file that cannot "
                             f"be read; it is dropped and {UNBOUND}"]


@pytest.mark.parametrize("at, warning", [
    (None, f"exports[0] (`run_pipeline`) carries a form but no `at`, so {UNBOUND}"),
    ("SKILL.md:11", "exports[0] (`run_pipeline`): `at` \"SKILL.md:11\" is a line that does not write "
                    f"`run_pipeline`; it is dropped and {UNBOUND}"),
    ("SKILL.md:6", None),
], ids=["missing", "bad", "good"])
def test_the_cli_writes_the_inventory_with_no_bad_at(tmp_path, at, warning):
    """#918: a missing or bad `at` exits 0 with its warning, and the inventory --output writes leaves the bad one
    out; a good one is kept."""
    pkg = _package(tmp_path, PLACES_SKILL)
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_places(_form_entry(at), references=()).encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["warnings"] == ([] if warning is None else [warning])
    [entry] = json.loads(out.read_bytes())["exports"]
    assert entry.get("at") == ("SKILL.md:6" if warning is None else None)


PINNED = ('floor: `fetchData` is documented at {} (table-row) with the signature {{"params": "url: string, '
          'retries?: number", "return_type": "Promise<Data>"}}')


def test_a_floor_signature_is_carried_at_its_origin(tmp_path):
    """#918: where the floor pins a form's origin, the entry that carries its signature gives that origin as its
    `at`. One that carries it elsewhere is a warning, never a refusal: its `at` is dropped, so plan leaves the form
    unbound, and the inventory stays valid."""
    pkg = _package(tmp_path, FORM_TABLE + "\nAlso `fetchData(url: string, retries?: number)` in prose.\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, "at": "SKILL.md:7"})), pkg, read)
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["warnings"] == [PINNED.format("SKILL.md:5") + ', but exports[0], which carries it, gives `at` '
                             f'"SKILL.md:7"; it is dropped and {UNBOUND}']
    assert "at" not in r["inventory"]["exports"][0]
    r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, "at": "SKILL.md:7"}),
                                       ("fetchData", "function", {**FORM, "at": "./SKILL.md:5"})), pkg, read)
    assert r["valid"] is True and r["warnings"] == [], r["violations"]
    assert [e["at"] for e in r["inventory"]["exports"]] == ["SKILL.md:7", "SKILL.md:5"]


def test_a_floor_signature_carried_at_another_origin_keeps_that_place(tmp_path):
    """#918: the floor pins one form at two places, and one entry carries it at the first. Its `at` is a pinned
    origin of that form, so it is kept; the second origin, which no entry gives as its `at`, is a warning of its
    own, its citations not read."""
    pkg = _package(tmp_path, FORM_TABLE, {"api.md": FORM_TABLE})
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, "at": "SKILL.md:5"}),
                                       references=["references/api.md"]), pkg, mod.read_floor(floor))
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["warnings"] == [PINNED.format("references/api.md:5") + ', but no inventory entry that carries it gives '
                             '`at` "references/api.md:5", so the citations there are not read']
    assert r["inventory"]["exports"][0]["at"] == "SKILL.md:5"


@pytest.mark.parametrize("at, warning", [
    (None, f"exports[0] (`fetchData`) carries a form but no `at`, so {UNBOUND}"),
    ("SKILL.md:99", f"exports[0] (`fetchData`): `at` \"SKILL.md:99\" is past the end of SKILL.md (5 lines); it is "
                    f"dropped and {UNBOUND}"),
    ("SKILL.md:1", f"exports[0] (`fetchData`): `at` \"SKILL.md:1\" is a line that does not write `fetchData`; it is "
                   f"dropped and {UNBOUND}"),
    ("README.md:1", f"exports[0] (`fetchData`): `at` names \"README.md\", no file the inventory reads: SKILL.md or a "
                    f"file `references` lists; it is dropped and {UNBOUND}"),
], ids=["missing", "past-the-end", "another-line", "another-file"])
def test_a_floor_form_with_no_good_at_is_one_warning(tmp_path, at, warning):
    """#918 review: a form the floor pins whose `at` is missing or dropped before the floor check is one form left
    unbound, so it is one warning, its own: the floor origin adds none, as the entry that carries it has no `at`."""
    pkg = _package(tmp_path, FORM_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    fields = {**FORM} if at is None else {**FORM, "at": at}
    r = mod.validate_inventory(_signed(("fetchData", "function", fields)), pkg, mod.read_floor(floor))
    assert r["valid"] is True and r["violations"] == [], r["violations"]
    assert r["warnings"] == [warning]
    assert "at" not in r["inventory"]["exports"][0]


PARTIAL_TABLE = ("# Demo\n\n| Export | Kind | Signature (simplified) |\n| --- | --- | --- |\n"
                 "| `fetchData` | function | `(url: string, retries?: number) => Promise<Data>` |\n\n"
                 "Also `fetchData(url: string)` in prose.\n")
PARTIAL = {**FORM, "signature_form": "partial"}
PARTIAL_VIOLATION = ('floor: `fetchData` is documented at SKILL.md:5 (table-row) with the signature {"params": "url: '
                     'string, retries?: number", "return_type": "Promise<Data>", "signature_form": "partial"}, but no '
                     'inventory entry of that name at that place carries it, or one gives its form without its '
                     '`signature_form` there or with no `at`; copy it as given, with `at` "SKILL.md:5"')


def test_a_floor_partial_label_is_carried_at_its_origin(tmp_path):
    """#888 step 1: the floor pins a Signature header's partial label with the form read from that column, so an
    entry carries that origin only with `signature_form` "partial" too, and only at that origin: at least one entry
    of the name whose `at` is the row gives the form, each of them with the label. The form and the label at the row
    are valid with no floor warning, the form after shared text and `; ` too, and beside another form the row
    quotes as a contrast. A dropped label (none, or "full") fails with exit 2, the violation naming the origin, the
    labelled signature and the `at`, and leaves no inventory file. A labelled carrier elsewhere (the prose line) or
    with no `at` is that violation too, never the warning an unlabelled pin gives, and so is an unlabelled twin of
    the form at the row, which score-signatures.py would keep as the full form, and an unlabelled copy beside the
    labelled carrier with no `at` (none given, or a bad one dropped), which shows no place the skill writes it in
    full and would be kept over the label too. An unlabelled copy whose `at` is another line that writes the name
    (the prose line) beside the labelled carrier is valid: it is compared there."""
    pkg = _package(tmp_path, PARTIAL_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert read["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", PARTIAL)]
    contrast = ("fetchData", "function", {"params": "url: string", "return_type": "Data", **AT_ROW})
    for entries in ([("fetchData", "function", {**PARTIAL, **AT_ROW})],
                    [("fetchData", "constant", {**PARTIAL, "params": "id; " + FORM["params"], **AT_ROW})],
                    [("fetchData", "function", {**PARTIAL, **AT_ROW}), contrast],
                    [("fetchData", "function", {**PARTIAL, **AT_ROW}),
                     ("fetchData", "function", {**FORM, "at": "SKILL.md:7"})]):
        r = mod.validate_inventory(_signed(*entries), pkg, read)
        assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (
            entries, r["violations"], r["warnings"])
        assert r["floor"] == {"names": 1, "checked": 1, "absent": []}

    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(("fetchData", "function", {**FORM, **AT_ROW})).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [PARTIAL_VIOLATION] and result["output"] is None
    assert not out.exists()

    for entries, warnings in (
        ([{**FORM, "signature_form": "full", **AT_ROW}], []),
        ([{**PARTIAL, "at": "SKILL.md:7"}], []),
        ([PARTIAL], [f"exports[0] (`fetchData`) carries a form but no `at`, so {UNBOUND}"]),
        ([{**PARTIAL, **AT_ROW}, {**FORM, **AT_ROW}], []),
        ([{**PARTIAL, **AT_ROW}, FORM], [f"exports[1] (`fetchData`) carries a form but no `at`, so {UNBOUND}"]),
        ([{**PARTIAL, **AT_ROW}, {**FORM, "at": "SKILL.md:1"}],
         [f'exports[1] (`fetchData`): `at` "SKILL.md:1" is a line that does not write `fetchData`; it is dropped '
          f"and {UNBOUND}"]),
    ):
        r = mod.validate_inventory(_signed(*(("fetchData", "function", e) for e in entries)), pkg, read)
        assert r["valid"] is False and r["violations"] == [PARTIAL_VIOLATION], (entries, r["violations"])
        assert r["warnings"] == warnings, (entries, r["warnings"])


LABEL_ADDED_VIOLATION = (PINNED.format("SKILL.md:5") + ', but an inventory entry of that name gives its form with '
                         '`signature_form` "partial" there or with no `at`, a label the floor does not pin; copy it '
                         'as given, without that label, with `at` "SKILL.md:5"')


def test_a_partial_label_at_an_unlabelled_floor_pin_fails(tmp_path):
    """#1029: the label at a place the floor pins is the floor's. Where the pin gives no label, an entry of the name
    that gives its form with `signature_form` "partial" at that place fails with exit 2, one violation naming the
    origin, the signature and the `at`, and leaves no inventory file: score-signatures.py would grade a left-out
    optional parameter Info, not Critical, where the skill gives no label. So does a labelled copy of the form with
    no `at` (none given, or a bad one dropped), alone or beside the unlabelled carrier at the row. The form with no
    label, or "full", at the row is valid, and so is a labelled copy whose `at` is another line that writes the name
    (the prose line), compared there."""
    pkg = _package(tmp_path, FORM_TABLE + "\nAlso `fetchData(url: string)` in prose.\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert read["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", FORM)]
    for entries in ([{**FORM, **AT_ROW}], [{**FORM, "signature_form": "full", **AT_ROW}],
                    [{**FORM, **AT_ROW}, {**PARTIAL, "at": "SKILL.md:7"}]):
        r = mod.validate_inventory(_signed(*(("fetchData", "function", e) for e in entries)), pkg, read)
        assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (
            entries, r["violations"], r["warnings"])

    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(("fetchData", "function", {**PARTIAL, **AT_ROW})).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [LABEL_ADDED_VIOLATION] and result["output"] is None
    assert not out.exists()

    for entries, warnings in (
        ([PARTIAL], [f"exports[0] (`fetchData`) carries a form but no `at`, so {UNBOUND}"]),
        ([{**FORM, **AT_ROW}, PARTIAL], [f"exports[1] (`fetchData`) carries a form but no `at`, so {UNBOUND}"]),
        ([{**FORM, **AT_ROW}, {**PARTIAL, "at": "SKILL.md:1"}],
         [f'exports[1] (`fetchData`): `at` "SKILL.md:1" is a line that does not write `fetchData`; it is dropped '
          f"and {UNBOUND}"]),
    ):
        r = mod.validate_inventory(_signed(*(("fetchData", "function", e) for e in entries)), pkg, read)
        assert r["valid"] is False and r["violations"] == [LABEL_ADDED_VIOLATION], (entries, r["violations"])
        assert r["warnings"] == warnings, (entries, r["warnings"])


def test_a_labelled_longer_form_elsewhere_is_no_labelled_copy_of_a_pin(tmp_path):
    """#1029 review: the refusal of a partial label at an unlabelled pin reads the entries that carry the pin, and
    a longer list carries it only at the pin's own place (#1028). A longer form the skill writes elsewhere and
    labels with its own `...` (`fetchData(url: string, retries?: number, ...)` in prose), with no `at` or a bad one,
    is another form, labelled as the contract says: it stays valid, with only the missing-`at` warning, beside the
    unlabelled copy at the row. Given as the row's own form (`at` the row), its label is still refused."""
    pkg = _package(tmp_path, FORM_TABLE + "\nAlso `fetchData(url: string, retries?: number, ...)` in prose.\n")
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert read["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", FORM)]
    longer = {"params": "url: string, retries?: number, ...", "return_type": "Promise<Data>",
              "signature_form": "partial"}
    for at, warnings in (
        (None, [f"exports[1] (`fetchData`) carries a form but no `at`, so {UNBOUND}"]),
        ("SKILL.md:1", ['exports[1] (`fetchData`): `at` "SKILL.md:1" is a line that does not write `fetchData`; '
                        f"it is dropped and {UNBOUND}"]),
        ("SKILL.md:7", []),
    ):
        other = {**longer, **({} if at is None else {"at": at})}
        r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, **AT_ROW}),
                                           ("fetchData", "function", other)), pkg, read)
        assert r["valid"] is True and r["violations"] == [] and r["warnings"] == warnings, (
            at, r["violations"], r["warnings"])
    r = mod.validate_inventory(_signed(("fetchData", "function", {**FORM, **AT_ROW}),
                                       ("fetchData", "function", {**longer, **AT_ROW})), pkg, read)
    assert r["valid"] is False and r["violations"] == [LABEL_ADDED_VIOLATION], r["violations"]


ELLIPSIS_TABLE = ("# Demo\n\n| Export | Kind | Signature |\n| --- | --- | --- |\n"
                  "| `fetchData` | function | `(url: string, ...) => Promise<Data>` |\n")


def test_an_ellipsis_pin_on_the_floor_is_carried_with_its_label(tmp_path):
    """#1029: a plain Signature cell whose form holds an ellipsis item is pinned with `signature_form` "partial",
    so the label rule of a header's label holds for it: the labelled copy at the row is valid, and the copy without
    the label, which validated before, is one violation naming the origin and the labelled signature."""
    pkg = _package(tmp_path, ELLIPSIS_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    pinned = {"params": "url: string, ...", "return_type": "Promise<Data>", "signature_form": "partial"}
    assert read["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", pinned)]
    r = mod.validate_inventory(_signed(("fetchData", "function", {**pinned, **AT_ROW})), pkg, read)
    assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (r["violations"], r["warnings"])
    unlabelled = {key: value for key, value in pinned.items() if key != "signature_form"}
    r = mod.validate_inventory(_signed(("fetchData", "function", {**unlabelled, **AT_ROW})), pkg, read)
    assert r["valid"] is False and r["violations"] == [
        f"floor: `fetchData` is documented at SKILL.md:5 (table-row) with the signature {json.dumps(pinned)}, but no "
        "inventory entry of that name at that place carries it, or one gives its form without its `signature_form` "
        'there or with no `at`; copy it as given, with `at` "SKILL.md:5"'], r["violations"]


KEY_PARAMS_TABLE = ("# Demo\n\n| Export | Kind | Key params | Source |\n|---|---|---|---|\n"
                    '| `Mem0Source` | class | `Mem0Source(data, mode="re-derive")`: `data` is a path. | |\n'
                    '| `IMPORT_MODES` | tuple | `("re-derive", "preserve")`: the modes. | |\n')


def test_a_key_params_pin_on_the_floor_is_carried_with_its_label(tmp_path):
    """#997: a Key params cell on a `class` row is pinned with `signature_form` "partial", the label its header
    gives each row, so the label rule holds for it: the labelled copy at the row is valid with no warning, while a
    copy without the label (exit 2, no inventory file left), a usage recorded in its place and another form there
    are each one violation naming the origin and the labelled signature. A `tuple` row's cell pins nothing, so its
    name is carried with no form."""
    pkg = _package(tmp_path, KEY_PARAMS_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    pinned = {"params": 'data, mode="re-derive"', "return_type": "", "signature_form": "partial"}
    assert [(n["name"], n["origins"]) for n in read["names"]] == [
        ("IMPORT_MODES", [_floor_origin("SKILL.md", 6, "table-row")]),
        ("Mem0Source", [_floor_origin("SKILL.md", 5, "table-row", pinned)])]
    modes = ("IMPORT_MODES", "constant", {"description": ""})
    r = mod.validate_inventory(_signed(("Mem0Source", "class", {**pinned, **AT_ROW}), modes), pkg, read)
    assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (r["violations"], r["warnings"])
    assert r["floor"] == {"names": 2, "checked": 2, "absent": []}

    violation = ("floor: `Mem0Source` is documented at SKILL.md:5 (table-row) with the signature "
                 f"{json.dumps(pinned)}, but no inventory entry of that name at that place carries it, or one gives "
                 'its form without its `signature_form` there or with no `at`; copy it as given, with `at` '
                 '"SKILL.md:5"')
    unlabelled = {"params": 'data, mode="re-derive"', "return_type": "", **AT_ROW}
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(("Mem0Source", "class", unlabelled), modes).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [violation] and result["output"] is None
    assert not out.exists()
    for fields in ({"usage_signature": 'Mem0Source(data, mode="re-derive")', "return_type": "", **AT_ROW},
                   {"params": "data", "return_type": "", "signature_form": "partial", **AT_ROW}):
        r = mod.validate_inventory(_signed(("Mem0Source", "class", fields), modes), pkg, read)
        assert r["valid"] is False and r["violations"] == [violation], (fields, r["violations"])


USAGE_SKILL = ("# Demo\n\n"
               "| Component | Props | Purpose |\n| --- | --- | --- |\n"
               "| `Title` | `TitleProps = { of?: Of }` | Renders the title. |\n\n"
               "| Component | Props (simplified) | Purpose |\n| --- | --- | --- |\n"
               "| `Stories` | `{ title?: string }` | Lists the stories. |\n\n"
               "| Export | Kind | Signature |\n| --- | --- | --- |\n"
               "| `add` | function | `await cognee.add(data)` |\n"
               "| `get` | function | `client.get(k) -> str` |\n")
TITLE = {"params": "TitleProps = { of?: Of }", "return_type": ""}
STORIES = {"params": "{ title?: string }", "return_type": "", "signature_form": "partial"}
ADD = {"usage_signature": "await cognee.add(data)", "return_type": ""}
GET = {"usage_signature": "client.get(k)", "return_type": "str"}


def _usage_entries(**changed):
    """The four entries that carry USAGE_SKILL's pins at their rows, each name's fields replaced by `changed`."""
    fields = {"Title": {**TITLE, "at": "SKILL.md:5"}, "Stories": {**STORIES, "at": "SKILL.md:9"},
              "add": {**ADD, "at": "SKILL.md:13"}, "get": {**GET, "at": "SKILL.md:14"}}
    return [(name, "function", {"description": "", **changed.get(name, value)}) for name, value in fields.items()]


def test_a_props_cell_and_a_usage_form_pinned_on_the_floor_are_carried_at_their_rows(tmp_path):
    """#888 step 2: the floor the script writes pins a one-span Props cell as `params` (its label as
    `signature_form` "partial") and a Signature cell's usage form as `usage_signature` and `return_type`. Each is
    carried by an entry of that name at its row that copies it, whitespace aside, a usage after shared text and `; `
    too, with no floor warning. A usage pin given as `params`, a Props pin that drops its `TitleProps = `, a labelled
    Props pin copied without its label and a usage pin with another return fail with exit 2, one violation naming
    the origin and the signature, and leave no inventory file."""
    pkg = _package(tmp_path, USAGE_SKILL)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert [(n["name"], n["origins"]) for n in read["names"]] == [
        ("Stories", [_floor_origin("SKILL.md", 9, "table-row", STORIES)]),
        ("Title", [_floor_origin("SKILL.md", 5, "table-row", TITLE)]),
        ("add", [_floor_origin("SKILL.md", 13, "table-row", ADD)]),
        ("get", [_floor_origin("SKILL.md", 14, "table-row", GET)])]
    for changed in ({}, {"add": {"usage_signature": "await\n  cognee.add(data) ", "at": "SKILL.md:13"}},
                    {"add": {"usage_signature": "data: Data; await cognee.add(data)", "at": "SKILL.md:13"}},
                    {"get": {**GET, "params": "k", "at": "SKILL.md:14"}}):
        r = mod.validate_inventory(_signed(*_usage_entries(**changed)), pkg, read)
        assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (
            changed, r["violations"], r["warnings"])
        assert r["floor"] == {"names": 4, "checked": 4, "absent": []}

    pinned = "floor: `{}` is documented at SKILL.md:{} (table-row) with the signature {}, but "
    elsewhere = 'no inventory entry of that name carries it; copy it as given, with `at` "SKILL.md:{}"'
    response, out = tmp_path / "inventory-response.txt", tmp_path / "inventory.json"
    response.write_bytes(_signed(*_usage_entries(add={"params": "await cognee.add(data)", "return_type": "",
                                                      "at": "SKILL.md:13"})).encode("utf-8"))
    out.write_bytes(b"{}")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(response), "--skill-package", str(pkg),
                           "--output", str(out), "--floor", str(floor)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["violations"] == [pinned.format("add", 13, json.dumps(ADD)) + elsewhere.format(13)]
    assert result["output"] is None and not out.exists()
    for changed, violation in (
        ({"Title": {"params": "{ of?: Of }", "return_type": "", "at": "SKILL.md:5"}},
         pinned.format("Title", 5, json.dumps(TITLE)) + elsewhere.format(5)),
        ({"Stories": {"params": "{ title?: string }", "return_type": "", "at": "SKILL.md:9"}},
         pinned.format("Stories", 9, json.dumps(STORIES)) + "no inventory entry of that name at that place carries "
         "it, or one gives its form without its `signature_form` there or with no `at`; copy it as given, with `at` "
         '"SKILL.md:9"'),
        ({"get": {**GET, "return_type": "bytes", "at": "SKILL.md:14"}},
         pinned.format("get", 14, json.dumps(GET)) + elsewhere.format(14)),
    ):
        r = mod.validate_inventory(_signed(*_usage_entries(**changed)), pkg, read)
        assert r["valid"] is False and r["violations"] == [violation], (changed, r["violations"])


LABELLED_USAGE_TABLE = ("# Demo\n\n| Export | Kind | Signature (simplified) |\n| --- | --- | --- |\n"
                        "| `get` | function | `client.get(k) -> str` |\n")
LABELLED_GET = {**GET, "signature_form": "partial"}


def test_a_labelled_usage_form_on_the_floor_is_carried_with_its_label(tmp_path):
    """#888 step 2: a usage form read from a Signature cell under a partial label is pinned as `usage_signature` and
    `return_type` with `signature_form` "partial", and the label rule holds for it as for a `params` pin: the labelled
    copy at the row validates with no warning, while the copy without the label, and an unlabelled twin at the row
    beside the labelled copy, are each one violation naming the origin and the labelled signature."""
    pkg = _package(tmp_path, LABELLED_USAGE_TABLE)
    floor = tmp_path / "inventory-floor.json"
    proc = subprocess.run([sys.executable, str(FLOOR_SCRIPT), "floor", "--skill-dir", str(pkg), "--output",
                           str(floor)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    read = mod.read_floor(floor)
    assert read["names"][0]["origins"] == [_floor_origin("SKILL.md", 5, "table-row", {
        "usage_signature": "client.get(k)", "return_type": "str", "signature_form": "partial"})]
    labelled = ("get", "function", {**LABELLED_GET, **AT_ROW})
    r = mod.validate_inventory(_signed(labelled), pkg, read)
    assert r["valid"] is True and r["violations"] == [] and r["warnings"] == [], (r["violations"], r["warnings"])
    assert r["floor"] == {"names": 1, "checked": 1, "absent": []}

    violation = (f"floor: `get` is documented at SKILL.md:5 (table-row) with the signature {json.dumps(LABELLED_GET)}, "
                 "but no inventory entry of that name at that place carries it, or one gives its form without its "
                 '`signature_form` there or with no `at`; copy it as given, with `at` "SKILL.md:5"')
    unlabelled = ("get", "function", {**GET, **AT_ROW})
    for entries in ([unlabelled], [labelled, unlabelled]):
        r = mod.validate_inventory(_signed(*entries), pkg, read)
        assert r["valid"] is False and r["violations"] == [violation], (entries, r["violations"])


@pytest.mark.parametrize("line, citations", [
    (3, {("pipeline.py", 53, 53)}),                         # on the line
    (1, set()),                                             # the next non-blank line writes the name: its own place
    (6, {("run_pipeline.py", 37, 37)}),                     # in a block: the first non-blank line after it
    (8, {("run_pipeline.py", 37, 37)}),
    (11, {("run_pipeline.py", 37, 37)}),
    (0, set()),
    (12, set()),
], ids=["same-line", "next-line-another-place", "declaration-in-a-block", "last-line-of-the-block",
        "the-citation-line", "line-0", "past-the-end"])
def test_a_form_s_own_citations(line, citations):
    assert mod.form_citations(PLACES_SKILL.split("\n"), line, "run_pipeline") == citations


def test_a_form_s_own_citations_on_the_next_line_or_a_heading_comment():
    """The next non-blank line (a heading, then its citation); a block's first non-blank line when it is a comment,
    never a code line; a range, read in order, and a citation with no line, which covers its whole file."""
    lines = ["### `run(a)`", "", "[SRC:./a.py:L12-L20] [AST:b.py]", "", "`run(b)` alone", "",
             "```ts", "", "// [AST:c.ts:L9-3]", "export function run(a: A) {}", "```",
             "```py", "run(1)  # [AST:d.py:L1]", "x = run(2)", "```", "Prose [AST:e.py:L5]",
             "```py", "def run(a):", "    return a"]
    assert mod.form_citations(lines, 1, "run") == {("a.py", 12, 20), ("b.py", None, None)}
    assert mod.form_citations(lines, 5, "run") == set(), "no citation on its line or the next non-blank one"
    assert mod.form_citations(lines, 10, "run") == {("c.ts", 3, 9)}
    # the block's first line is code, not a comment: only the line after the block counts
    assert mod.form_citations(lines, 14, "run") == {("e.py", 5, 5)}
    # an unclosed block runs to the end: no line after it
    assert mod.form_citations(lines, 18, "run") == set()


def test_a_neighbouring_line_that_is_another_place_of_the_name_is_not_read():
    """#918 review: a neighbouring line read for a form's citations belongs to that form only. The next non-blank
    line that writes the name (the next table row) is another place, whose citations are its own; a block that
    holds another place of the name (`others`) gives neither form its block-wide citations, the comment heading the
    block nor the line after it; in a block, each declaration's own heading is the comment just above it, and a
    comment after it heads the next one; and a note after a block that names the name is a place of its own."""
    rows = ["| `run(a)` | x |", "| `run(b)` | y [AST:b.py:L5] |"]
    assert mod.form_citations(rows, 1, "run") == set()
    assert mod.form_citations(rows, 2, "run") == {("b.py", 5, 5)}
    block = ["```py", "# [AST:a.py:L1]", "def run(a): ...", "", "# [AST:b.py:L2]", "def run(b): ...", "```", "",
             "[AST:c.py:L3]"]
    assert mod.form_citations(block, 3, "run", {6}) == {("a.py", 1, 1)}
    assert mod.form_citations(block, 6, "run", [3]) == {("b.py", 2, 2)}
    # a place's own line in `others` is no other place; alone in its block, each form reads the block-wide ones
    assert mod.form_citations(block, 3, "run", (3,)) == {("a.py", 1, 1), ("c.py", 3, 3)}
    assert mod.form_citations(block, 6, "run") == {("a.py", 1, 1), ("b.py", 2, 2), ("c.py", 3, 3)}
    # another place in another block leaves this block's citations to its one place
    assert mod.form_citations(block + ["```py", "run(1)", "```"], 6, "run", {11}) == {
        ("a.py", 1, 1), ("b.py", 2, 2), ("c.py", 3, 3)}
    two = ["```py", "def run(a): ...", "def run(b): ...", "```", "", "[AST:c.py:L3]"]
    assert mod.form_citations(two, 2, "run", {3}) == set()
    assert mod.form_citations(two, 3, "run", {2}) == set()
    note = ["```ts", "export type Mode = 'a' | 'b';", "```", "",
            "The other package declares its own `Mode`, with one member [AST:other/types.ts:L1]"]
    assert mod.form_citations(note, 2, "Mode") == set()
    assert mod.form_citations(note, 5, "Mode") == {("other/types.ts", 1, 1)}


def test_a_table_row_s_own_citations_are_in_its_cells():
    """#998 (oms-cocoindex `Settings`): a table row outside a fenced block (the floor's table row) reads no line after
    it, whatever name that line writes. The next row documents another export, whose citations are its own, so a
    row that cites its declaration keeps that citation alone and a row that cites none has none; a line after the
    table is the table's, not its last row's. A heading still reads the next non-blank line, and a line that opens
    with `|` in a fenced block is code, read by the fence rules."""
    rows = ["| Export | Kind | Source |", "| --- | --- | --- |",
            "| `Settings` | class | [AST:pkg/_internal/setting.py:L56] |",
            "| `ServerSettings` | class | [AST:pkg/setting.py:L93] |"]
    assert mod.form_citations(rows, 3, "Settings") == {("pkg/_internal/setting.py", 56, 56)}
    assert mod.form_citations(rows, 4, "ServerSettings") == {("pkg/setting.py", 93, 93)}
    uncited = ["  | `Settings` | class | The settings |", "| `ServerSettings` | class | [AST:pkg/setting.py:L93] |"]
    assert mod.form_citations(uncited, 1, "Settings") == set()
    last = ["| `Settings` | class |", "", "[AST:pkg/setting.py:L93]"]
    assert mod.form_citations(last, 1, "Settings") == set()
    heading = ["### `Settings`", "", "[AST:pkg/_internal/setting.py:L56]", "", "| `ServerSettings` | class |"]
    assert mod.form_citations(heading, 1, "Settings") == {("pkg/_internal/setting.py", 56, 56)}
    fenced = ["```elixir", "| Settings.load(path)", "[AST:pkg/_internal/setting.py:L56]", "```"]
    assert mod.form_citations(fenced, 2, "Settings") == {("pkg/_internal/setting.py", 56, 56)}


@pytest.mark.parametrize("citations, file, line, named", [
    ({("a.py", 37, 37)}, "a.py", 37, True),
    ({("a.py", 37, 37)}, "./a.py", 37, True),
    ({("a.py", 30, 45)}, "a.py", 37, True),
    ({("a.py", 38, 45)}, "a.py", 37, False),
    ({("a.py", 37, 37)}, "b.py", 37, False),
    ({("a.py", None, None)}, "a.py", 37, True),
    ({("a.py", None, None)}, "a.py", None, True),
    ({("a.py", 37, 37)}, "a.py", None, False),
], ids=["its-line", "a-path-written-otherwise", "a-range-that-holds-it", "a-range-past-it", "another-file",
        "no-line", "no-line-and-no-declaration-line", "a-line-and-no-declaration-line"])
def test_a_citation_names_a_declaration_at_its_line(citations, file, line, named):
    assert mod.cites_declaration(citations, file, line) is named


@pytest.mark.parametrize("citations, line, end, named", [
    ({("run_pipeline.py", 46, 61)}, 37, 100, True),
    ({("run_pipeline.py", 46, 46)}, 37, 100, True),
    ({("run_pipeline.py", 100, 120)}, 37, 100, True),
    ({("run_pipeline.py", 30, 37)}, 37, 100, True),
    ({("run_pipeline.py", 101, 120)}, 37, 100, False),
    ({("run_pipeline.py", 1, 36)}, 37, 100, False),
    ({("run_pipeline.py", 46, 61)}, 37, None, False),
    ({("run_pipeline.py", 46, 61)}, 37, 10, False),
    ({("run_pipeline.py", 46, 61)}, None, 100, False),
    ({("run_pipeline.py", None, None)}, None, 100, True),
    ({("pipeline.py", 46, 61)}, 37, 100, False),
], ids=["a-range-of-its-body", "a-line-of-its-body", "a-range-from-its-last-line", "a-range-that-ends-at-its-line",
        "past-its-span", "above-it", "no-span-its-line-alone", "a-span-that-ends-before-its-line-its-line-alone",
        "no-declaration-line", "no-line-and-no-declaration-line", "another-file"])
def test_a_citation_of_a_declaration_s_body_names_it(citations, line, end, named):
    """#918 (oms-cognee pipelines-and-datapoints.md: run_pipeline.py:L46-L61 cites the body of the runner declared
    at L37): a citation names a declaration when its line or range holds a line of the declaration's span, from
    its line to `end`; with no `end`, its line alone."""
    assert mod.cites_declaration(citations, "run_pipeline.py", line, end) is named


def test_a_form_s_comment_marker_is_the_floor_s():
    """A fenced block's first-line comment is read with the markers the floor reads a headed block with."""
    loader = importlib.util.spec_from_file_location("skf_pin_load_coverage_inputs_comments", FLOOR_SCRIPT)
    inputs = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(inputs)
    assert mod._COMMENT_MARKER_RE.pattern == inputs.COMMENT_MARKER_RE.pattern
    assert "Keep identical to COMMENT_MARKER_RE in" in SCRIPT.read_text(encoding="utf-8")
