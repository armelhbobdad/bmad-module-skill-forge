#!/usr/bin/env python3
"""Tests for src/shared/scripts/skf-names-present.py.

The helper create-stack-skill runs before it commits a compose-mode stack
(generate-output section 8):
  - absent[] lists, in entries[] order, each entry whose export_name the
    staged SKILL.md and references/*.md never write (case-sensitive; a
    references/ subfolder does not count); a `::` name and an entry with
    no name are skipped
  - --drop-absent removes those entries and rewrites the map through
    skf-atomic-write.py; with nothing absent it writes nothing
  - a folder without SKILL.md, a missing or malformed map, a reference file
    that is not UTF-8 and a missing atomic writer exit 2 with no JSON, and
    leave the map as it was

test-skf-stack-step-rules.py pins the rule to skf-test-skill's scorer.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts"
SCRIPT = SCRIPTS / "skf-names-present.py"

SKILL_MD = "# demo Stack Skill\n\nCall `connect()` first, then read `café_menu`.\n".encode("utf-8")
LIBA_MD = b"# liba\n\n`Client` wraps a session.\n"
PAIR_MD = b"# liba + libb\n\n`get_config` feeds libb.\n"

# connect and Client are written; client (case) and get_config (only in
# references/integrations/) are not; the rest are never looked up.
ENTRIES = [
    {"export_name": "connect", "source_library": "liba"},
    {"export_name": "client", "source_library": "liba"},
    {"export_name": "get_config", "source_library": "liba"},
    {"export_name": "Client::new", "source_library": "liba"},
    {"export_name": "Client", "source_library": "liba"},
    {"source_library": "libb"},
    {"export_name": "", "source_library": "libb"},
    "not an entry",
    {"export_name": "café_menu", "source_library": "bibliothèque"},
]


def make_package(root: Path) -> Path:
    package = root / "demo-stack.skf-tmp"
    (package / "references" / "integrations").mkdir(parents=True)
    (package / "SKILL.md").write_bytes(SKILL_MD)
    (package / "references" / "liba.md").write_bytes(LIBA_MD)
    (package / "references" / "integrations" / "liba-libb.md").write_bytes(PAIR_MD)
    return package


def make_map(root: Path, entries: list | None = None) -> Path:
    path = root / "provenance-map.json"
    body = {"skill_type": "stack", "entries": ENTRIES if entries is None else entries, "constituents": []}
    path.write_bytes(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    return path


def run(*args: str, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


def check(provenance: Path, package: Path, *flags: str, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    return run("--provenance", str(provenance), "--skill-dir", str(package), *flags, script=script)


def test_absent_lists_each_unwritten_name_in_entry_order(tmp_path):
    result = check(make_map(tmp_path), make_package(tmp_path))
    assert result.returncode == 1, result.stderr
    out = json.loads(result.stdout)
    assert out["absent"] == [
        {"entry_index": 1, "export_name": "client", "source_library": "liba"},
        {"entry_index": 2, "export_name": "get_config", "source_library": "liba"},
    ]
    assert (out["checked"], out["skipped"]) == (5, 4)
    assert (out["dropped"], out["provenance_written"]) == ([], False)


def test_every_name_written_exits_0_and_writes_nothing(tmp_path):
    provenance = make_map(tmp_path, [e for i, e in enumerate(ENTRIES) if i not in (1, 2)])
    before = provenance.read_bytes()
    for flags in ((), ("--drop-absent",)):
        result = check(provenance, make_package(tmp_path / str(len(flags))), *flags)
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)
        assert (out["absent"], out["dropped"], out["provenance_written"]) == ([], [], False)
        assert provenance.read_bytes() == before


def test_drop_absent_removes_the_absent_entries(tmp_path):
    provenance, package = make_map(tmp_path), make_package(tmp_path)
    result = check(provenance, package, "--drop-absent")
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["dropped"] == out["absent"] and [a["export_name"] for a in out["absent"]] == ["client", "get_config"]
    assert out["provenance_written"] is True
    text = provenance.read_bytes().decode("utf-8")
    assert text.endswith("}\n") and '\n  "entries": [' in text and "bibliothèque" in text
    written = json.loads(text)
    assert written["entries"] == [e for i, e in enumerate(ENTRIES) if i not in (1, 2)]
    assert (written["skill_type"], written["constituents"]) == ("stack", [])
    again = check(provenance, package)
    assert again.returncode == 0 and json.loads(again.stdout)["absent"] == []


def test_a_folder_without_skill_md_is_refused(tmp_path):
    # Every name would read as absent, and --drop-absent would empty the map.
    provenance = make_map(tmp_path)
    before = provenance.read_bytes()
    empty = tmp_path / "wrong-folder"
    empty.mkdir()
    result = check(provenance, empty, "--drop-absent")
    assert result.returncode == 2
    assert result.stdout == "" and "no SKILL.md" in result.stderr
    assert provenance.read_bytes() == before


@pytest.mark.parametrize("case", ["missing-map", "not-json", "top-level-list", "entries-not-a-list", "reference-not-utf8"])
def test_bad_input_exits_2_without_json(tmp_path, case):
    package = make_package(tmp_path)
    provenance = tmp_path / "provenance-map.json"
    if case == "not-json":
        provenance.write_bytes(b'{"entries": [')
    elif case == "top-level-list":
        provenance.write_bytes(b"[]")
    elif case == "entries-not-a-list":
        provenance.write_bytes(b'{"entries": {"connect": {}}}')
    elif case == "reference-not-utf8":
        make_map(tmp_path)
        (package / "references" / "latin1.md").write_bytes("caf\xe9".encode("latin-1"))
    result = check(provenance, package, "--drop-absent")
    assert result.returncode == 2, result.stdout
    assert result.stdout == "" and result.stderr.startswith("error: ")


def test_a_missing_atomic_writer_writes_nothing(tmp_path):
    alone = tmp_path / "scripts" / SCRIPT.name
    alone.parent.mkdir()
    shutil.copyfile(SCRIPT, alone)
    provenance = make_map(tmp_path)
    before = provenance.read_bytes()
    result = check(provenance, make_package(tmp_path), "--drop-absent", script=alone)
    assert result.returncode == 2
    assert result.stdout == "" and "skf-atomic-write.py not found" in result.stderr
    assert provenance.read_bytes() == before


@pytest.mark.parametrize("args", [
    pytest.param(("--help",), id="help"),
    pytest.param(("--provenance", "map.json"), id="no-skill-dir"),
    pytest.param(("--provenance", "map.json", "--skill-dir", "pkg", "--dry-run"), id="unknown-flag"),
])
def test_the_cli(args):
    result = run(*args)
    if args == ("--help",):
        assert result.returncode == 0 and "--drop-absent" in result.stdout
    else:
        assert result.returncode == 2 and result.stdout == ""


@pytest.mark.parametrize("text, absent", [
    ("call `get(url)`", False), ("the target", True), ("getAll()", True),
], ids=["whole-name", "inside-target", "prefix-of-getAll"])
def test_a_name_inside_a_longer_identifier_is_absent(tmp_path, text, absent):
    """skf-test-skill credits a name only as a whole name, so the check is the same."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "SKILL.md").write_bytes(f"# demo\n\n{text}\n".encode("utf-8"))
    result = check(make_map(tmp_path, [{"export_name": "get", "source_library": "liba"}]), package)
    assert result.returncode == (1 if absent else 0), result.stderr
    assert [a["export_name"] for a in json.loads(result.stdout)["absent"]] == (["get"] if absent else [])


def _module(path: Path, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VALIDATE_INVENTORY = SCRIPTS.parent.parent / "skf-test-skill" / "scripts" / "validate-inventory.py"
# The first text writes each name whole; the second holds `get`, `state`,
# `then` and `new` only inside longer identifiers.
BOUNDARY_TEXTS = (
    "call `get(url)` on the target, then getAll(); `$state` and .then and `Type::new` and get_; the café\n",
    "the target, getAll() and $states; promise.thenable, renew, get_x\n",
)


@pytest.mark.parametrize("name", [
    "get", "getAll", "target", "arg", "$state", "state", ".then", "then", "Type::new", "new", "get_", "get_x",
    "ge", "café",
])
def test_the_whole_name_rule_is_the_scorers(name):
    """skf-names-present.py copies validate-inventory.py's whole-name match;
    the two must agree on every boundary, `get` against `target` and `getAll`
    included."""
    scorer = _module(VALIDATE_INVENTORY, "validate_inventory_names_parity")
    helper = _module(SCRIPT, "skf_names_present_parity")
    assert helper.NAME_CHARS == scorer.IDENT_CHARS
    for text in BOUNDARY_TEXTS:
        assert helper.name_written(name, text) == bool(scorer.name_pattern(name).search(text)), (name, text)
    assert not helper.name_written("get", BOUNDARY_TEXTS[1]), "`get` is not found in `target` or `getAll`"
