"""skf-extraction-inventory.py: create-skill's extraction inventory, written, extended and read on disk.

Step 3 starts the inventory with `init` from the recipe runner's JSON and
the script/asset detector's JSON, then sends only what it produced: `patch`
(signatures), `add` (exports read by eye, warnings) and `set` (top exports,
co-imports, the authoritative-files records, a free-text intent's
mapping). Step 3c appends its T3 items and step 4 its T2 annotations
through `add`, `summary` counts it (step 3c's zero-content check reads
`items`, step 5 its `t2_future`), and step 7 writes extraction-rules.yaml
with `rules`. A T3 item never overrides an export the inventory already
holds, and an entry added twice is kept once.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "shared" / "scripts" / "skf-extraction-inventory.py"
RUNNER = REPO / "src" / "shared" / "scripts" / "skf-extract-public-api.py"
FETCH_TEMPORAL = REPO / "src" / "shared" / "scripts" / "skf-fetch-temporal.py"

spec = importlib.util.spec_from_file_location("skf_extraction_inventory", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

INVENTORY = {
    "skill_name": "demo",
    "extraction_mode": "source",
    "tier": "Forge",
    "files_scanned": 4,
    "exports": [
        {"export_name": "parse", "export_type": "function", "source_file": "src/a.py", "confidence": "T1",
         "ast_recipe": "py-function-defs"},
        {"export_name": "Client", "export_type": "class", "source_file": "src/b.py", "confidence": "T1-low",
         "ast_recipe": None},
    ],
    "top_exports": ["parse", "Client"],
    "scripts_inventory": [{"name": "run.sh", "source_file": "bin/run.sh"}],
    "assets_inventory": [],
}

# The fields of skf-extract-public-api.py --mode full that init reads.
RUNNER_JSON = {
    "mode": "full",
    "status": "ok",
    "recipe_set": "standard",
    "ast_grep": {"path": "/usr/bin/ast-grep", "version": "0.45.3"},
    "scope": {"include": ["src/**"], "exclude": [], "tier_a_include": None, "type": "full-library",
              "languages": ["python"], "files_from": None},
    "files_in_scope": 3,
    "files_without_recipes": {".java": 2},
    "file_issues": [{"file": "src/broken.py", "issue": "syntax-errors", "count": 1, "line": 4}],
    "head_cap": 200,
    "truncated": True,
    "recipes": [{"id": "py-function-defs", "languages": ["python"], "matches": 201, "truncated": True},
                {"id": "py-class-defs", "languages": ["python"], "matches": 1, "truncated": False}],
    "exports": [
        {"export_name": "alpha", "source_file": "src/pkg/core.py", "source_line": 1, "signature_line": "def alpha(x):",
         "citation": "[AST:src/pkg/core.py:L1]", "ast_recipe": "py-function-defs", "ast_node_type": "function_definition",
         "export_type": "function", "language": "python", "from": None, "from_file": None, "confidence": "T1",
         "extraction_method": "ast-grep"},
        {"export_name": "helper", "source_file": "src/pkg/core.py", "source_line": 9, "signature_line": "def helper():",
         "citation": "[AST:src/pkg/core.py:L9]", "ast_recipe": "py-function-defs", "ast_node_type": "function_definition",
         "export_type": "function", "language": "python", "from": None, "from_file": None, "confidence": "T1",
         "extraction_method": "ast-grep"},
    ],
    "aggregates": {"exports": 2, "by_type": {"function": 2}, "t1": 2, "t1_low": 0},
    "entry_point_diff": {"public": [], "internal": [{"name": "helper", "language": "python",
                                                     "source_file": "src/pkg/core.py", "source_line": 9}],
                         "extraction_gaps": [], "outside_scope": []},
    "counts": {"exports_public_api": 1, "exports_internal": 1, "effective_denominator": 1,
               "effective_denominator_basis": "scope.include", "denominator_files": 1},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
    "errors": [{"reason": "ast-grep-timeout", "files": 5, "first_file": "src/big.py", "detail": "timed out"}],
    "warnings": ["no recipe reads java files"],
}

DETECTED_JSON = {
    "scripts_inventory": [
        {"name": "run.sh", "source_file": "bin/run.sh", "purpose": "runner", "content_hash": "sha256:aa",
         "confidence": "T1-low", "lines": 3, "size_flag": None},
        {"name": "release.sh", "source_file": "scripts/release.sh", "purpose": "release",
         "content_hash": "sha256:bb", "confidence": "T1-low", "lines": 9, "size_flag": None},
    ],
    "assets_inventory": [{"name": "a.schema.json", "source_file": "schemas/a.schema.json", "purpose": "schema",
                          "content_hash": "sha256:cc", "confidence": "T1-low", "lines": 4, "size_flag": None}],
    "scripts_skipped": False,
    "assets_skipped": False,
    "stats": {"scripts_found": 2, "assets_found": 1, "files_scanned": 40},
}


def _write(tmp_path: Path, data: dict = INVENTORY, name: str = "demo.inventory.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def _ok(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# summary and add
# --------------------------------------------------------------------------


def test_summary_counts_the_inventory(tmp_path):
    out = _ok(_run("summary", "--inventory", str(_write(tmp_path))))
    assert out["extraction_mode"] == "source"
    assert out["counts"] == {"files_scanned": 4, "exports": 2, "t1": 1, "t1_low": 1,
                             "by_type": {"class": 1, "function": 1}, "top_exports": 2, "co_imports": 0,
                             "scripts": 1, "assets": 0, "t2_annotations": 0, "t2_past": 0, "t2_future": 0,
                             "functions_enriched": 0, "t3_items": 0, "items": 2}


def test_t2_annotations_are_appended_once_and_counted(tmp_path):
    """Enrich displays its summary from these counts, and compile takes t2_future_count from them."""
    path = _write(tmp_path)
    notes = [{"export_name": "parse", "temporal": "T2-future", "citation": "[QMD:demo-temporal:CHANGELOG.md]"},
             {"export_name": "parse", "temporal": "T2-past", "citation": "[QMD:demo-temporal:issue-4.md]"},
             {"export_name": "Client", "temporal": "T2-past", "citation": "[QMD:demo-temporal:issue-9.md]"}]
    out = _ok(_run("add", "--inventory", str(path), "--field", "t2_annotations", stdin=json.dumps(notes)))
    assert (out["added"], out["duplicates"], out["dropped"]) == (3, 0, [])
    assert {k: out["counts"][k] for k in ("t2_annotations", "t2_past", "t2_future", "functions_enriched")} == \
        {"t2_annotations": 3, "t2_past": 2, "t2_future": 1, "functions_enriched": 2}
    # the same call again, after its output was lost, adds nothing
    again = _ok(_run("add", "--inventory", str(path), "--field", "t2_annotations", stdin=json.dumps(notes)))
    assert (again["added"], again["duplicates"], again["counts"]["t2_annotations"]) == (0, 3, 3)
    data = _load(path)
    assert data["t2_annotations"] == notes
    # every other field is left as it was
    assert {k: v for k, v in data.items() if k != "t2_annotations"} == INVENTORY


def test_a_t3_item_never_overrides_an_export(tmp_path):
    path = _write(tmp_path)
    items = [{"export_name": "parse", "citation": "[EXT:https://docs]"},
             {"export_name": "configure", "citation": "[EXT:https://docs]"},
             {"kind": "example", "citation": "[EXT:https://docs]"},
             {"kind": "example", "citation": "[EXT:https://docs]"}]
    out = _ok(_run("add", "--inventory", str(path), "--field", "t3_items", stdin=json.dumps(items)))
    assert (out["added"], out["duplicates"], out["dropped"]) == (2, 1, ["parse"])
    assert out["counts"]["items"] == 4
    names = [i.get("export_name") for i in _load(path)["t3_items"]]
    assert names == ["configure", None]


def test_an_export_read_by_eye_gets_the_by_eye_labels_once(tmp_path):
    path = _write(tmp_path)
    by_eye = [{"export_name": "gap", "export_type": "function", "source_file": "src/c.py", "source_line": 3,
               "signature": "def gap(x: int) -> str", "citation": "[SRC:src/c.py:L3]"}]
    out = _ok(_run("add", "--inventory", str(path), "--field", "exports", stdin=json.dumps(by_eye)))
    assert (out["added"], out["counts"]["exports"], out["counts"]["t1_low"]) == (1, 3, 2)
    added = _load(path)["exports"][-1]
    assert (added["confidence"], added["extraction_method"], added["ast_node_type"], added["ast_recipe"]) == \
        ("T1-low", "source-read", None, None)
    # the same export again (same name and file) is a duplicate, whatever else it says
    again = _ok(_run("add", "--inventory", str(path), "--field", "exports",
                     stdin=json.dumps([{**by_eye[0], "signature": "def gap(x)"}])))
    assert (again["added"], again["duplicates"], again["counts"]["exports"]) == (0, 1, 3)
    refused = _run("add", "--inventory", str(path), "--field", "exports", stdin='[{"source_file": "x.py"}]')
    assert refused.returncode == 1 and "export_name" in json.loads(refused.stderr)["message"]


def test_warnings_are_strings_kept_once(tmp_path):
    path = _write(tmp_path)
    out = _ok(_run("add", "--inventory", str(path), "--field", "warnings",
                   stdin=json.dumps(["Degraded to source reading", "Degraded to source reading"])))
    assert (out["added"], out["duplicates"]) == (1, 1)
    assert _load(path)["warnings"] == ["Degraded to source reading"]
    assert _run("add", "--inventory", str(path), "--field", "warnings", stdin='[{"w": 1}]').returncode == 1


def test_an_empty_docs_only_inventory_has_no_item(tmp_path):
    """Step 3c's zero-content check halts a docs-only brief whose inventory holds no item."""
    path = tmp_path / "docs.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "docs", "--mode", "docs-only", "--tier", "Quick"))
    out = _ok(_run("summary", "--inventory", str(path)))
    assert out["extraction_mode"] == "docs-only" and out["counts"]["items"] == 0
    proc = _run("add", "--inventory", str(path), "--field", "t3_items", stdin="[]")
    assert _ok(proc)["counts"]["items"] == 0


@pytest.mark.parametrize("content,needle", [
    ("not json", "cannot read the inventory"),
    ('{"top_exports": []}', "not an object with an exports list"),
    ('{"exports": [], "t3_items": {}}', "t3_items is not a list"),
], ids=["not-json", "no-exports", "field-not-a-list"])
def test_a_bad_inventory_is_refused(tmp_path, content, needle):
    path = tmp_path / "inv.json"
    path.write_text(content, encoding="utf-8")
    proc = _run("summary", "--inventory", str(path))
    assert proc.returncode == 1
    assert needle in json.loads(proc.stderr)["message"]


@pytest.mark.parametrize("command,stdin", [
    (["add", "--field", "t2_annotations"], '{"export_name": "x"}'),
    (["add", "--field", "t2_annotations"], '["x"]'),
    (["add", "--field", "t2_annotations"], "not json"),
    (["patch"], '[{"export_name": "parse", "citation": "[AST:x:L1]"}]'),
    (["set"], '{"exports": []}'),
    (["set"], '{"files_scanned": true}'),
    (["set"], '{"intent_mapping": {"scripts": {"intent": "the CLI", "kept": ["bin/none.sh"]}}}'),
], ids=["add-object", "add-list-of-strings", "add-not-json", "patch-other-field", "set-unknown-key",
        "set-wrong-type", "set-unknown-kept-file"])
def test_a_bad_payload_changes_nothing(tmp_path, command, stdin):
    path = _write(tmp_path)
    before = path.read_bytes()
    proc = _run(command[0], "--inventory", str(path), *command[1:], stdin=stdin)
    assert proc.returncode == 1
    assert path.read_bytes() == before


def test_a_missing_inventory_is_refused(tmp_path):
    proc = _run("add", "--inventory", str(tmp_path / "none.json"), "--field", "t3_items", stdin="[]")
    assert proc.returncode == 1


# --------------------------------------------------------------------------
# init: the runner's and the detector's records, never typed again
# --------------------------------------------------------------------------


def test_init_seeds_the_inventory_from_the_runner_and_the_detector(tmp_path):
    runner = _write(tmp_path, RUNNER_JSON, "demo.extraction.json")
    detected = _write(tmp_path, DETECTED_JSON, "demo.detected.json")
    path = tmp_path / "demo.inventory.json"
    path.write_text('{"exports": [{"export_name": "stale"}]}', encoding="utf-8")
    out = _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge+",
                   "--extraction", str(runner), "--detected", str(detected)))
    assert out["counts"]["exports"] == 2 and out["counts"]["files_scanned"] == 3
    data = _load(path)
    assert (data["skill_name"], data["extraction_mode"], data["tier"]) == ("demo", "source", "Forge+")
    # each runner record is kept as the runner wrote it; only the internal mark is added
    assert [{k: v for k, v in e.items() if k != "internal"} for e in data["exports"]] == RUNNER_JSON["exports"]
    assert [e.get("internal", False) for e in data["exports"]] == [False, True]
    for key in ("aggregates", "counts", "arms"):
        assert data[key] == RUNNER_JSON[key], key
    assert data["extraction_rules"] == {"recipe_set": "standard", "recipes": ["py-function-defs", "py-class-defs"],
                                        "scope": RUNNER_JSON["scope"], "ast_grep_version": "0.45.3"}
    assert data["warnings"] == [
        "Extraction hit the head cap: `py-function-defs` matched more than 200 exports, so some exports were read "
        "by eye or left out. Narrow `scope.include` in the brief until no recipe reaches the cap.",
        "ast-grep did not finish on 5 files from `src/big.py` (timed out): exports in them may be missing",
        "`src/broken.py` (syntax-errors): its exports are read by eye",
        "2 `.java` files in scope are in a language no recipe reads",
        "no recipe reads java files",
    ]
    assert data["scripts_inventory"] == DETECTED_JSON["scripts_inventory"]
    assert data["assets_inventory"] == DETECTED_JSON["assets_inventory"]
    for key in ("top_exports", "co_imports", "promoted_docs", "t2_annotations", "t3_items"):
        assert data[key] == [], key
    assert data["intent_mapping"] == {} and data["authoritative_files_scan"] is None


@pytest.mark.parametrize("flag", ["--extraction", "--detected"])
def test_init_refuses_a_file_it_cannot_read(tmp_path, flag):
    path = tmp_path / "demo.inventory.json"
    proc = _run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge",
                flag, str(tmp_path / "missing.json"))
    assert proc.returncode == 1 and not path.exists()


def _pinned_ast_grep() -> bool:
    scripts = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_init_reads_what_the_runner_writes(tmp_path):
    """The runner's real -o JSON goes through init unchanged: no field init reads is renamed."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('from .core import alpha\n\n__all__ = ["alpha"]\n', encoding="utf-8")
    (src / "core.py").write_text("def alpha(x):\n    return x\n\n\ndef helper():\n    pass\n", encoding="utf-8")
    runner_json = tmp_path / "demo.extraction.json"
    ran = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(tmp_path),
                          "--language", "python", "--tier", "Forge", "-o", str(runner_json)],
                         capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    assert ran.returncode == 0, ran.stderr
    path = tmp_path / "demo.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge",
             "--extraction", str(runner_json)))
    data = _load(path)
    by_name = {e["export_name"]: e for e in data["exports"]}
    assert set(by_name) == {"alpha", "helper"}
    assert by_name["alpha"]["citation"] == "[AST:src/pkg/core.py:L1]"
    assert by_name["alpha"]["confidence"] == "T1" and "internal" not in by_name["alpha"]
    assert by_name["helper"]["internal"] is True
    assert data["files_scanned"] == 2
    assert data["extraction_rules"]["recipe_set"] == "standard" and data["extraction_rules"]["ast_grep_version"]
    assert data["counts"]["exports_public_api"] == 1


# --------------------------------------------------------------------------
# patch and set: only what the model produced
# --------------------------------------------------------------------------


def test_patch_sets_the_signatures_the_model_read(tmp_path):
    data = {**INVENTORY, "exports": [*INVENTORY["exports"],
                                     {"export_name": "parse", "source_file": "src/other.py", "confidence": "T1"}]}
    path = _write(tmp_path, data)
    patches = [{"export_name": "Client", "signature": "class Client(url: str)", "params": ["url: str"],
                "return_type": "Client"},
               {"export_name": "parse", "source_file": "src/a.py", "signature": "def parse(text: str) -> Node"},
               {"export_name": "parse", "signature": "def parse()"},
               {"export_name": "nothing", "signature": "def nothing()"}]
    out = _ok(_run("patch", "--inventory", str(path), stdin=json.dumps(patches)))
    assert (out["patched"], out["unmatched"], out["ambiguous"]) == (2, ["nothing"], ["parse"])
    exports = _load(path)["exports"]
    assert exports[1]["signature"] == "class Client(url: str)" and exports[1]["params"] == ["url: str"]
    assert exports[0]["signature"] == "def parse(text: str) -> Node"
    assert exports[0]["ast_recipe"] == "py-function-defs" and "signature" not in exports[2]


def test_set_replaces_lists_and_merges_counts(tmp_path):
    path = _write(tmp_path, {**INVENTORY, "counts": {"exports_public_api": 5, "exports_internal": 1}})
    values = {"top_exports": ["Client"], "co_imports": [{"library": "httpx"}], "files_scanned": 7,
              "counts": {"exports_public_api": 6},
              "authoritative_files_scan": {"not_scanned": "remote source not cloned"},
              "promoted_docs": [{"path": "AGENTS.md", "content_hash": "sha256:dd"}]}
    out = _ok(_run("set", "--inventory", str(path), stdin=json.dumps(values)))
    assert sorted(out["set"]) == sorted(values)
    data = _load(path)
    assert data["top_exports"] == ["Client"] and data["files_scanned"] == 7
    assert data["counts"] == {"exports_public_api": 6, "exports_internal": 1}
    assert data["authoritative_files_scan"] == {"not_scanned": "remote source not cloned"}
    assert out["counts"]["co_imports"] == 1


def test_a_free_text_intent_keeps_only_its_files(tmp_path):
    """Extract §4c's free-text intent: the inventory keeps the kept files and records the others."""
    path = tmp_path / "demo.inventory.json"
    detected = _write(tmp_path, DETECTED_JSON, "demo.detected.json")
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge",
             "--detected", str(detected)))
    mapping = {"intent_mapping": {"scripts": {"intent": "the release script", "kept": ["scripts/release.sh"]}}}
    for _ in range(2):  # a second run of the same call changes nothing
        out = _ok(_run("set", "--inventory", str(path), stdin=json.dumps(mapping)))
        assert (out["counts"]["scripts"], out["counts"]["assets"]) == (1, 1)
        data = _load(path)
        assert [e["source_file"] for e in data["scripts_inventory"]] == ["scripts/release.sh"]
        assert data["intent_mapping"] == {"scripts": {"intent": "the release script", "kept": ["scripts/release.sh"],
                                                      "left_out": ["bin/run.sh"]}}


# --------------------------------------------------------------------------
# rules: extraction-rules.yaml from the inventory
# --------------------------------------------------------------------------


def test_rules_writes_extraction_rules_from_the_inventory(tmp_path):
    runner = _write(tmp_path, RUNNER_JSON, "demo.extraction.json")
    path = tmp_path / "demo.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Deep",
             "--extraction", str(runner)))
    before = path.read_bytes()
    target = tmp_path / "stage" / "extraction-rules.yaml"
    target.parent.mkdir()
    out = _ok(_run("rules", "--inventory", str(path), "--language", "python", "--target", str(target)))
    assert out == {"status": "ok", "target": target.as_posix(), "bytes": len(target.read_bytes())}
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "skill_name": "demo", "language": "python", "tier": "Deep", "extraction_mode": "source",
        "recipe_set": "standard", "recipes": ["py-function-defs", "py-class-defs"],
        "scope": RUNNER_JSON["scope"], "ast_grep_version": "0.45.3"}
    assert path.read_bytes() == before


def test_rules_writes_a_source_read_extraction_too(tmp_path):
    path = tmp_path / "demo.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "docs-only", "--tier", "Quick"))
    target = tmp_path / "extraction-rules.yaml"
    _ok(_run("rules", "--inventory", str(path), "--language", "typescript", "--target", str(target)))
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "skill_name": "demo", "language": "typescript", "tier": "Quick", "extraction_mode": "docs-only"}


def test_the_yaml_writer_round_trips_nested_values():
    value = {"a": [{"b": 1, "c": [None, "x: y"]}, "d"], "e": {}, "f": [], "weird key": {"g": True}}
    assert yaml.safe_load("\n".join(mod._yaml_lines(value))) == value


# --------------------------------------------------------------------------
# step 3b reads the inventory's top_exports
# --------------------------------------------------------------------------


def test_the_temporal_fetch_reads_top_exports_from_the_inventory(tmp_path):
    """sub/fetch-temporal.md passes `--exports "{extraction_inventory}"`: the fetch helper
    reads the inventory's top_exports from it, and an empty list for a docs-only brief."""
    spec_t = importlib.util.spec_from_file_location("skf_fetch_temporal_inventory", FETCH_TEMPORAL)
    fetch = importlib.util.module_from_spec(spec_t)
    spec_t.loader.exec_module(fetch)
    assert fetch.read_exports(str(_write(tmp_path))) == ["parse", "Client"]
    empty = _write(tmp_path, {"extraction_mode": "docs-only", "exports": [], "top_exports": []})
    assert fetch.read_exports(str(empty)) == []
    prose = (REPO / "src" / "skf-create-skill" / "references" / "sub" / "fetch-temporal.md").read_text(encoding="utf-8")
    assert ('uv run {fetchTemporalHelper} fetch --repo "{temporal_repo}" --feeder "{temporal_feeder}" '
            '--exports "{extraction_inventory}"') in prose
    assert "SKF_TOP_EXPORTS" not in prose and "as a JSON list" not in prose
