"""skf-extraction-inventory.py: create-skill's extraction inventory, written, extended and read on disk.

Step 3 starts the inventory with `init` from the recipe runner's JSON and
the script/asset detector's JSON, then sends only what it produced: `patch`
(signatures), `add` (exports read by eye, warnings) and `set` (top exports,
co-imports, the authoritative-files records, a free-text intent's
mapping). Step 3c appends its T3 items and step 4 its T2 annotations
through `add`, `summary` counts it (step 3c's zero-content check reads
`items`, step 5 its `t2_future`), step 5 writes the provenance map with
`provenance` (an entry per inventory export, T1 and T1-low, the runner's
params as the map's typed strings, per language) and merges its T2, T3 and
file entries with `provenance --add-entries`, and step 7 writes
extraction-rules.yaml with `rules`. A T3 item never overrides an export the
inventory already holds, and an entry added twice is kept once.
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
    assert out["counts"] == {"files_scanned": 4, "exports": 2, "not_public": 0, "t1": 1, "t1_low": 1,
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
    assert data["public_surface"] is None  # a full-library run: no public surface, no export marked


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
# provenance: the provenance map, written from the inventory, never typed by hand
# --------------------------------------------------------------------------

HEADER = {"source_repo": "https://github.com/o/r", "source_commit": "0123abcd", "source_ref": "v2.3.0",
          "generated_at": "2026-10-01T12:00:00Z"}


def _provenance(path: Path, target: Path, header: dict = HEADER) -> dict:
    return _ok(_run("provenance", "--inventory", str(path), "--target", str(target), stdin=json.dumps(header)))

_runner_spec = importlib.util.spec_from_file_location("skf_extract_public_api_for_inventory", RUNNER)
runner = importlib.util.module_from_spec(_runner_spec)
_runner_spec.loader.exec_module(runner)


def _t1(name: str, language: str, signature: str, export_type: str = "function", **extra) -> dict:
    """A runner export record, its params and return_type read as the runner reads them."""
    params, returns = (runner.signature_parts(signature, language, name) if export_type == "function"
                       else (None, None))
    return {"export_name": name, "export_type": export_type, "language": language, "source_file": f"src/{name}",
            "source_line": 3, "signature": signature, "params": params, "return_type": returns,
            "ast_recipe": "r", "ast_node_type": "export_statement", "confidence": "T1",
            "extraction_method": "ast-grep", **extra}


@pytest.mark.parametrize(
    ("language", "signature", "name", "params", "return_type"),
    [
        ("python", "def fetch(url: str, *, retries: int = 3, **kw) -> bytes:", "fetch",
         ["url: str", "retries: int = 3", "**kw"], "bytes"),
        ("typescript", "export function getToken(userId: string, options?: TokenOptions): Token {", "getToken",
         ["userId: string", "options?: TokenOptions"], "Token"),
        ("tsx", "export const Card = ({ title }: CardProps, ref?: Ref<HTMLDivElement>) => {", "Card",
         ["{ title }: CardProps", "ref?: Ref<HTMLDivElement>"], None),
        ("javascript", "export function label(text, sep = '-', ...rest) {", "label",
         ["text", "sep = '-'", "...rest"], None),
        ("rust", "pub fn parse(&self, input: &str) -> Result<Ast, Error> {", "parse",
         ["&self", "input: &str"], "Result<Ast, Error>"),
        ("go", "func New(a, b int, opts ...Option) (*Client, error) {", "New",
         ["a: int", "b: int", "opts: ...Option"], "(*Client, error)"),
    ],
    ids=["python", "typescript", "tsx", "javascript", "rust", "go"],
)
def test_provenance_writes_each_language_as_the_maps_typed_strings(tmp_path, language, signature, name, params,
                                                                   return_type):
    """skill-sections.md's form: 'userId: string', 'options?: TokenOptions'."""
    path = _write(tmp_path, {**INVENTORY, "exports": [_t1(name, language, signature)]})
    target = tmp_path / "provenance-map.json"
    out = _provenance(path, target)
    assert (out["entries"], out["unsigned"]) == (1, [])
    assert _load(target)["entries"] == [{
        "export_name": name, "export_type": "function", "params": params, "return_type": return_type,
        "source_file": f"src/{name}", "source_line": 3, "confidence": "T1", "extraction_method": "ast-grep",
        "ast_node_type": "export_statement", "signature_source": "T1"}]


def test_provenance_writes_an_entry_for_every_inventory_export(tmp_path):
    """The map's entries[] are the inventory's exports, T1 and T1-low alike,
    each labeled by the tool that found it; a function nobody read the
    signature of is listed, and a class carries no params."""
    exports = [
        _t1("run", "python", "def run(a: int) -> str:"),
        _t1("Engine", "python", "class Engine(Base):", export_type="class"),
        _t1("cut", "python", "def cut(a: int,"),
        {**_t1("patched", "python", "def patched("), "params": ["text: str"], "return_type": "Node"},
        {"export_name": "by_eye", "export_type": "function", "source_file": "src/b.py", "source_line": 7,
         "confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None, "params": ["x"],
         "return_type": None},
        # a by-eye entry that claims T1 is labeled by its method, never the reverse
        {"export_name": "mislabeled", "export_type": "const", "source_file": "src/c.py", "confidence": "T1",
         "extraction_method": "source-read", "ast_node_type": "expression_statement"},
    ]
    path = _write(tmp_path, {**INVENTORY, "exports": exports})
    before = path.read_bytes()
    target = tmp_path / "provenance-map.json"
    out = _provenance(path, target)
    assert (out["entries"], out["unsigned"]) == (6, ["cut (src/cut)"])
    written = _load(target)
    assert [(e["export_name"], e["source_file"]) for e in written["entries"]] == [
        (e["export_name"], e["source_file"]) for e in exports]
    entries = {e["export_name"]: e for e in written["entries"]}
    assert (entries["run"]["params"], entries["run"]["return_type"]) == (["a: int"], "str")
    assert (entries["Engine"]["params"], entries["Engine"]["return_type"]) == (None, None)
    assert (entries["cut"]["params"], entries["cut"]["return_type"]) == (None, None)
    assert (entries["patched"]["params"], entries["patched"]["return_type"]) == (["text: str"], "Node")
    t1 = ("T1", "ast-grep", "export_statement", "T1")
    t1_low = ("T1-low", "source-read", None, "T1-low")
    labels = {name: (e["confidence"], e["extraction_method"], e["ast_node_type"], e["signature_source"])
              for name, e in entries.items()}
    assert labels == {"run": t1, "Engine": t1, "cut": t1, "patched": t1, "by_eye": t1_low, "mislabeled": t1_low}
    assert entries["by_eye"]["params"] == ["x"] and entries["by_eye"]["source_line"] == 7
    assert path.read_bytes() == before, "the inventory is not changed"


def test_provenance_writes_the_maps_header(tmp_path):
    """skill-sections.md's header: stdin gives the source, the rest defaults."""
    path = _write(tmp_path)
    target = tmp_path / "provenance-map.json"
    _provenance(path, target, {"source_repo": "https://github.com/o/r", "source_commit": None})
    written = _load(target)
    assert list(written) == ["provenance_version", "skill_name", "skill_type", "source_repo", "source_commit",
                             "source_ref", "generated_at", "entries"]
    assert (written["provenance_version"], written["skill_name"], written["skill_type"]) == ("2.0", "demo", "single")
    assert (written["source_commit"], written["source_ref"]) == (None, None)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", written["generated_at"])
    _provenance(path, target)
    assert {k: _load(target)[k] for k in HEADER} == HEADER


@pytest.mark.parametrize(
    "header",
    [None, [], {"source_repo": "r"}, {**HEADER, "entries": []}],
    ids=["none", "not-an-object", "no-commit", "unknown-key"],
)
def test_provenance_refuses_a_bad_header(tmp_path, header):
    path = _write(tmp_path)
    target = tmp_path / "provenance-map.json"
    proc = _run("provenance", "--inventory", str(path), "--target", str(target),
                stdin="" if header is None else json.dumps(header))
    assert proc.returncode == 1 and not target.exists()


def test_provenance_adds_the_entries_compile_writes(tmp_path):
    """T2 and T3 entries and the file entries go through the same helper; an
    entry the map holds (an inventory export's) is never replaced."""
    path = _write(tmp_path)
    target = tmp_path / "provenance-map.json"
    _provenance(path, target)
    inventory_entries = _load(target)["entries"]
    t3 = {"export_name": "configure", "export_type": "function", "params": None, "return_type": None,
          "source_file": None, "source_line": None, "confidence": "T3", "extraction_method": "doc-fetch",
          "ast_node_type": None, "signature_source": "T3"}
    clash = {"export_name": "parse", "source_file": "src/a.py", "confidence": "T2", "signature_source": "T2"}
    script = {"file_name": "scripts/run.sh", "file_type": "script", "source_file": "bin/run.sh",
              "content_hash": "sha256:00", "confidence": "T1-low", "extraction_method": "file-copy"}
    payload = {"entries": [t3, clash], "file_entries": [script]}
    out = _ok(_run("provenance", "--inventory", str(path), "--target", str(target), "--add-entries",
                   stdin=json.dumps(payload)))
    assert (out["entries"], out["file_entries"], out["added"], out["duplicates"]) == (3, 1, 2, 1)
    written = _load(target)
    assert written["entries"] == [*inventory_entries, t3] and written["file_entries"] == [script]
    again = _ok(_run("provenance", "--inventory", str(path), "--target", str(target), "--add-entries",
                     stdin=json.dumps(payload)))
    assert (again["added"], again["duplicates"]) == (0, 3)


def test_provenance_adds_no_entry_for_an_export_off_the_surface(tmp_path):
    """The map left out an export marked `public: false`, so no duplicate check catches a T2 or T3 entry of it: the
    helper skips the entry and lists it in `not_public`."""
    path = _init_from(tmp_path, _fixture_run())
    target = tmp_path / "provenance-map.json"
    _provenance(path, target)
    off = {"export_name": "bar", "export_type": "function", "params": None, "return_type": None,
           "source_file": "pkg/a.py", "source_line": 5, "confidence": "T2", "extraction_method": "qmd_bridge",
           "ast_node_type": None, "signature_source": "T2"}
    other = {**off, "export_name": "configure", "source_file": None, "source_line": None, "confidence": "T3",
             "extraction_method": "doc-fetch", "signature_source": "T3"}
    out = _ok(_run("provenance", "--inventory", str(path), "--target", str(target), "--add-entries",
                   stdin=json.dumps({"entries": [off, other]})))
    assert (out["added"], out["duplicates"], out["not_public"]) == (1, 0, [{"name": "bar", "file": "pkg/a.py"}])
    assert [e["export_name"] for e in _load(target)["entries"]] == ["foo", "baz", "configure"]


@pytest.mark.parametrize(
    "payload",
    ["", "[]", json.dumps({"entries": [{"source_file": "x"}]}), json.dumps({"rows": []}),
     json.dumps({"file_entries": [{"file_type": "script"}]})],
    ids=["empty", "a-list", "no-export-name", "unknown-key", "no-file-name"],
)
def test_provenance_add_entries_refuses_a_bad_payload(tmp_path, payload):
    path = _write(tmp_path)
    target = tmp_path / "provenance-map.json"
    _provenance(path, target)
    before = target.read_bytes()
    proc = _run("provenance", "--inventory", str(path), "--target", str(target), "--add-entries", stdin=payload)
    assert proc.returncode == 1 and target.read_bytes() == before


def test_provenance_add_entries_needs_the_map(tmp_path):
    path = _write(tmp_path)
    proc = _run("provenance", "--inventory", str(path), "--target", str(tmp_path / "none.json"), "--add-entries",
                stdin=json.dumps({"entries": []}))
    assert proc.returncode == 1 and "provenance map" in proc.stderr


COMPILE = REPO / "src" / "skf-create-skill" / "references" / "compile.md"


def test_compile_writes_the_map_through_the_helper(tmp_path):
    """compile.md §6 never types an entry the inventory holds: the helper
    writes the staged map, an unsigned function goes back through extract's
    patch, and the T2, T3 and file entries go through --add-entries. Each
    documented payload is one the helper takes."""
    text = COMPILE.read_text(encoding="utf-8")
    six = text[text.index("### 6. Build provenance-map.json Content"):text.index("### 7. ")]
    write, add = re.findall(r"```bash\n(.*?)```", six, re.S)
    target = '--target "{project-root}/_bmad-output/.skf-stage/{skill-name}/provenance-map.json"'
    assert target in write and "--add-entries" not in write
    assert target in add and "--add-entries <<'SKF_JSON'" in add
    assert "never type an entry the inventory holds" in six and "Start `entries[]`" not in six
    assert "send them through that `patch` call as extract.md §5 says, and run the command above again" in six
    payloads = [json.loads(block.split("<<'SKF_JSON'\n")[1].split("\nSKF_JSON")[0]) for block in (write, add)]
    path = _write(tmp_path)
    map_path = tmp_path / "provenance-map.json"
    _provenance(path, map_path, payloads[0])
    out = _ok(_run("provenance", "--inventory", str(path), "--target", str(map_path), "--add-entries",
                   stdin=json.dumps(payloads[1])))
    assert (out["added"], out["file_entries"]) == (2, 1)


def test_provenance_refuses_a_missing_inventory(tmp_path):
    proc = _run("provenance", "--inventory", str(tmp_path / "none.json"), "--target", str(tmp_path / "e.json"),
                stdin=json.dumps(HEADER))
    assert proc.returncode == 1 and not (tmp_path / "e.json").exists()


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_provenance_reads_what_the_runner_writes(tmp_path):
    """The runner's -o JSON, through init, gives entries with the signature parts."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "api.py").write_bytes(b"def fetch(\n    url: str,\n    retries: int = 3,\n) -> bytes:\n    return b''\n")
    (src / "client.ts").write_bytes(b"export function connect(host: string, port?: number): Client {\n  return c;\n}\n")
    runner_json = tmp_path / "demo.extraction.json"
    ran = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(tmp_path),
                          "--tier", "Forge", "-o", str(runner_json)],
                         capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    assert ran.returncode == 0, ran.stderr
    path = tmp_path / "demo.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge",
             "--extraction", str(runner_json)))
    target = tmp_path / "provenance-map.json"
    _provenance(path, target)
    entries = {e["export_name"]: (e["params"], e["return_type"]) for e in _load(target)["entries"]}
    assert entries == {"fetch": (["url: str", "retries: int = 3"], "bytes"),
                       "connect": (["host: string", "port?: number"], "Client")}


# --------------------------------------------------------------------------
# a public-api skill: the map, exports[] and SKILL.md keep to the public surface (#699)
# --------------------------------------------------------------------------

STATS = REPO / "src" / "shared" / "scripts" / "skf-render-metadata-stats.py"
MANIFEST = REPO / "src" / "shared" / "scripts" / "skf-build-change-manifest.py"
EXTRACT = REPO / "src" / "skf-create-skill" / "references" / "extract.md"
_stats_spec = importlib.util.spec_from_file_location("skf_render_metadata_stats_for_inventory", STATS)
stats = importlib.util.module_from_spec(_stats_spec)
_stats_spec.loader.exec_module(stats)
_manifest_spec = importlib.util.spec_from_file_location("skf_build_change_manifest_for_inventory", MANIFEST)
manifest = importlib.util.module_from_spec(_manifest_spec)
_manifest_spec.loader.exec_module(manifest)
COHERENCE = REPO / "src" / "skf-test-skill" / "scripts" / "check-metadata-coherence.py"
_coherence_spec = importlib.util.spec_from_file_location("check_metadata_coherence_for_inventory", COHERENCE)
coherence = importlib.util.module_from_spec(_coherence_spec)
_coherence_spec.loader.exec_module(coherence)


def _fixture_export(name: str, path: str, line: int) -> dict:
    return {"export_name": name, "source_file": path, "source_line": line, "signature_line": f"def {name}():",
            "signature": f"def {name}():", "params": [], "return_type": None, "citation": f"[AST:{path}:L{line}]",
            "ast_recipe": "python-public-functions", "ast_node_type": "function_definition", "export_type": "function",
            "language": "python", "from": None, "from_file": None, "confidence": "T1", "extraction_method": "ast-grep"}


def _fixture_run(scope_type: str = "public-api") -> dict:
    """The issue's fixture as the runner records it: pkg/__init__.py re-exports foo from a.py and imports the
    submodule sub (a namespace, whose member baz, users' `pkg.sub.baz`, the runner counts in its place, #703);
    a.py also defines bar, helpers.py helper and sub.py baz."""
    return {
        "mode": "full", "status": "ok", "recipe_set": "standard", "ast_grep": {"version": "0.45.3"},
        "scope": {"include": [], "exclude": [], "tier_a_include": None, "type": scope_type, "languages": ["python"]},
        "files_in_scope": 4, "files_without_recipes": {}, "file_issues": [], "head_cap": 200, "truncated": False,
        "recipes": [{"id": "python-public-functions", "languages": ["python"], "matches": 4, "truncated": False}],
        "exports": [_fixture_export("foo", "pkg/a.py", 1), _fixture_export("bar", "pkg/a.py", 5),
                    _fixture_export("helper", "pkg/helpers.py", 1), _fixture_export("baz", "pkg/sub.py", 1)],
        "aggregates": {"exports": 4, "by_type": {"function": 4}, "t1": 4, "t1_low": 0},
        "entry_points": {"status": "barrel", "by_language": {"python": "barrel"}, "files": [], "unresolved": []},
        "entry_point_diff": {
            "public": [{"name": "foo", "entry": "pkg/__init__.py", "via": "re-export", "from": ".a", "local": None,
                        "file": "pkg/a.py", "line": 1, "language": "python"},
                       {"name": "sub", "entry": "pkg/__init__.py", "via": "namespace", "from": ".", "local": None,
                        "file": "pkg/sub.py", "line": None, "language": "python",
                        "members": [{"name": "baz", "local": None, "file": "pkg/sub.py", "line": 1}]}],
            "internal": [{"name": "bar", "language": "python", "source_file": "pkg/a.py", "source_line": 5},
                         {"name": "helper", "language": "python", "source_file": "pkg/helpers.py", "source_line": 1}],
            "extraction_gaps": [], "outside_scope": []},
        "counts": {"exports_public_api": 2, "exports_internal": 2, "effective_denominator": 2,
                   "effective_denominator_basis": "all-files", "denominator_files": 4},
        "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
        "errors": [], "warnings": [],
    }


def _init_from(tmp_path: Path, extraction: dict) -> Path:
    runner_json = _write(tmp_path, extraction, "demo.extraction.json")
    path = tmp_path / "demo.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge",
             "--extraction", str(runner_json)))
    return path


def _stats_of(target: Path, extraction: dict) -> dict:
    """The stats helper over the written map, with step 5 §4's payload from the runner's counts."""
    doc = _load(target)
    counts = extraction["counts"]
    derived = stats.derive_stats(doc, {"exports_public_api": counts["exports_public_api"],
                                       "exports_internal": counts["exports_internal"]})
    assert stats.coherence_compute(derived, doc)["ok"]
    return derived


def _barrel_findings(extraction: dict, entries: list[dict]) -> list[str]:
    """Test Skill's count check over the skill create writes: stats.exports_public_api (the runner's count)
    against an exports[] of the map's names; the titles of the findings it gives."""
    names = sorted({e["export_name"] for e in entries})
    result = coherence.check({"clusterA": {"exports_public_api": extraction["counts"]["exports_public_api"],
                                           "exports_length": len(names)}})
    return [f["title"] for f in result["findings"]]


def _update_marks_public(extraction: dict) -> set[tuple[str, str]]:
    """The exports update-skill's `records` keeps on a public-api skill's surface (marked true, or not marked)."""
    records, _summary = manifest.build_records(extraction, None, None, [])
    return {(r["name"], b["file_path"]) for b in records["files"] for r in b["exports"] if r.get("public") is not False}


NOT_PUBLIC_WARNING = ("Off the public surface: {n} export(s) of this public-api skill are left out of the provenance "
                      "map, SKILL.md, references/, the context snippet and metadata.json's exports[] (each is marked "
                      "`public: false` in the inventory, and `summary` lists them all): {names}")


def test_a_public_api_map_holds_only_the_public_surface(tmp_path):
    """The matrix's fixture: map and exports[] `foo` and `baz` (the member of sub, #703); exports_documented 2,
    public_api_coverage 1.0, t1 2, the names update's records keeps, and no barrel finding. Before #703 the map
    held `foo` alone (coverage 0.5, a barrel finding at 50%), and before #699 all 4 entries (2.0)."""
    extraction = _fixture_run()
    path = _init_from(tmp_path, extraction)
    data = _load(path)
    assert {e["export_name"]: e.get("public") for e in data["exports"]} == \
        {"foo": True, "bar": False, "helper": False, "baz": True}
    assert [e.get("internal", False) for e in data["exports"]] == [False, True, True, False]  # the mark stays
    assert data["public_surface"] == {
        "by_language": {"python": "barrel"},
        "public": [{"name": "foo", "language": "python", "file": "pkg/a.py", "local": None, "via": "re-export"},
                   {"name": "sub", "language": "python", "file": "pkg/sub.py", "local": None, "via": "namespace",
                    "members": [{"name": "baz", "local": None, "file": "pkg/sub.py"}]}],
        "extraction_gaps": []}
    assert data["warnings"] == [NOT_PUBLIC_WARNING.format(n=2, names="bar (pkg/a.py), helper (pkg/helpers.py)")]
    summary = _ok(_run("summary", "--inventory", str(path)))
    counts = summary["counts"]
    assert (counts["exports"], counts["not_public"], counts["items"]) == (4, 2, 2)
    # the evidence report lists each one with its file, from the summary
    assert summary["not_public"] == [{"name": "bar", "file": "pkg/a.py"}, {"name": "helper", "file": "pkg/helpers.py"}]
    target = tmp_path / "provenance-map.json"
    assert _provenance(path, target)["entries"] == 2
    entries = _load(target)["entries"]
    assert [(e["export_name"], e["source_file"]) for e in entries] == [("foo", "pkg/a.py"), ("baz", "pkg/sub.py")]
    assert {(e["export_name"], e["source_file"]) for e in entries} == _update_marks_public(extraction)
    derived = _stats_of(target, extraction)
    assert (derived["stats"]["exports_documented"], derived["stats"]["public_api_coverage"]) == (2, 1.0)
    assert derived["confidence_distribution"] == {"t1": 2, "t1_low": 0, "t2": 0, "t3": 0}
    assert _barrel_findings(extraction, entries) == []


def test_another_scope_type_maps_every_export_as_before(tmp_path):
    extraction = _fixture_run("full-library")
    path = _init_from(tmp_path, extraction)
    data = _load(path)
    assert all("public" not in e for e in data["exports"])
    assert data["public_surface"] is None and data["warnings"] == []
    target = tmp_path / "provenance-map.json"
    assert _provenance(path, target)["entries"] == 4
    assert _stats_of(target, extraction)["stats"]["public_api_coverage"] == 2.0


def _break(extraction: dict, change: str) -> None:
    if change == "no-entry-point-diff":
        extraction["entry_point_diff"] = None  # a no-ast-grep run: the runner diffed nothing
    if change == "incomplete":
        extraction["status"] = "incomplete"
    if change == "errors":
        extraction["errors"] = [{"reason": "ast-grep-timeout", "files": 1, "first_file": "pkg/a.py", "detail": "x"}]
    if change == "unresolved":
        extraction["entry_points"]["unresolved"] = [{"entry": "pkg/__init__.py", "name": "x", "from": ".gone",
                                                     "file": "pkg/__init__.py"}]


@pytest.mark.parametrize("change, why", [
    ("no-entry-point-diff", "the recipe runner gave no entry-point diff (Quick tier, or a run that could not read "
                            "the tree)"),
    ("incomplete", "the recipe runner's run is incomplete"),
    ("errors", "the recipe runner's run is incomplete"),
    ("unresolved", "an entry point names a module the runner could not trace (entry_points.unresolved)"),
])
def test_a_surface_the_rule_cannot_read_keeps_every_export_with_one_warning(tmp_path, change, why):
    extraction = _fixture_run()
    _break(extraction, change)
    path = _init_from(tmp_path, extraction)
    data = _load(path)
    assert all("public" not in e for e in data["exports"]) and data["public_surface"] is None
    expected = (f"The public surface of this public-api skill could not be applied ({why}): no export is marked "
                "`public: false`, so every export found is documented")
    assert [w for w in data["warnings"] if w.startswith("The public surface")] == [expected]
    assert not any(w.startswith("Off the public surface") for w in data["warnings"])
    assert _provenance(path, tmp_path / "provenance-map.json")["entries"] == 4
    # an export read by eye later is not marked either
    out = _ok(_run("add", "--inventory", str(path), "--field", "exports",
                   stdin=json.dumps([{"export_name": "qux", "export_type": "function", "source_file": "pkg/q.py"}])))
    assert out["counts"]["not_public"] == 0 and "public" not in _load(path)["exports"][-1]


def test_an_export_read_by_eye_is_marked_by_the_same_rule(tmp_path):
    """Update marks every record it seeds; create marks each export add sends after init the same way: a runner gap
    read by eye is public, a name the surface does not hold is not, whatever the payload says."""
    extraction = _fixture_run()
    extraction["entry_point_diff"]["extraction_gaps"] = [
        {"name": "Drop", "language": "python", "entry": "pkg/__init__.py", "file": "pkg/types.py", "line": 3}]
    path = _init_from(tmp_path, extraction)
    by_eye = [{"export_name": "Drop", "export_type": "sentinel", "source_file": "pkg/types.py", "source_line": 3},
              {"export_name": "__version__", "export_type": "const", "source_file": "pkg/__init__.py",
               "source_line": 2, "public": True},
              {"export_name": "notes", "export_type": "const", "source_file": "README.md", "public": False}]
    out = _ok(_run("add", "--inventory", str(path), "--field", "exports", stdin=json.dumps(by_eye)))
    assert (out["added"], out["counts"]["exports"], out["counts"]["not_public"]) == (3, 7, 3)
    data = _load(path)
    # a file of no barrel family gets no mark, and the payload's own `public` is never kept
    assert {e["export_name"]: e.get("public") for e in data["exports"][4:]} == \
        {"Drop": True, "__version__": False, "notes": None}
    # the one warning is written again, in its place, after the warnings that came before it
    _ok(_run("add", "--inventory", str(path), "--field", "warnings", stdin='["a file could not be read"]'))
    _ok(_run("add", "--inventory", str(path), "--field", "exports",
             stdin=json.dumps([{"export_name": "late", "export_type": "function", "source_file": "pkg/a.py"}])))
    assert _load(path)["warnings"] == [
        NOT_PUBLIC_WARNING.format(n=4, names="bar (pkg/a.py), helper (pkg/helpers.py), __version__ (pkg/__init__.py), "
                                             "late (pkg/a.py)"),
        "a file could not be read"]
    target = tmp_path / "provenance-map.json"
    _provenance(path, target)
    assert [e["export_name"] for e in _load(target)["entries"]] == ["foo", "baz", "Drop", "notes"]
    # update's records marks the same two by-eye records, from step 2's export details
    details = {"exports": [dict(e, source_line=1) for e in by_eye[:2]]}
    records, _ = manifest.build_records(extraction, details, None, [])
    assert {r["name"]: r.get("public") for b in records["files"] for r in b["exports"]
            if r["name"] in ("Drop", "__version__")} == {"Drop": True, "__version__": False}


def test_an_export_read_by_eye_keeps_no_mark_outside_a_public_api_run(tmp_path):
    path = _write(tmp_path)  # an inventory with no public_surface: every scope type but public-api
    out = _ok(_run("add", "--inventory", str(path), "--field", "exports",
                   stdin=json.dumps([{"export_name": "gap", "export_type": "function", "source_file": "src/c.py",
                                      "public": False}])))
    assert out["counts"]["not_public"] == 0 and "public" not in _load(path)["exports"][-1]
    assert "warnings" not in _load(path)
    target = tmp_path / "provenance-map.json"
    assert _provenance(path, target)["entries"] == 3


def test_a_function_off_the_surface_is_not_listed_unsigned(tmp_path):
    extraction = _fixture_run()
    for record in extraction["exports"]:
        record["params"] = None  # nobody read a signature
    path = _init_from(tmp_path, extraction)
    out = _provenance(path, tmp_path / "provenance-map.json")
    assert (out["entries"], out["unsigned"]) == (2, ["foo (pkg/a.py)", "baz (pkg/sub.py)"])


def test_a_t2_annotation_of_an_export_off_the_surface_is_not_counted(tmp_path):
    """The evidence report's t2_future_count and the migration section read these counts: an annotation of a name
    every export of which is off the surface counts in none of them; one of a name also on the surface counts."""
    extraction = _fixture_run()
    extraction["exports"].append(_fixture_export("foo", "pkg/helpers.py", 9))  # a second foo, off the surface
    path = _init_from(tmp_path, extraction)
    notes = [{"export_name": "bar", "temporal": "T2-future", "citation": "[QMD:demo-temporal:CHANGELOG.md]"},
             {"export_name": "foo", "temporal": "T2-past", "citation": "[QMD:demo-temporal:issue-4.md]"},
             {"export_name": "foo", "temporal": "T2-future", "citation": "[QMD:demo-temporal:issue-9.md]"},
             {"temporal": "T2-past", "citation": "[QMD:demo-temporal:issue-12.md]"}]
    out = _ok(_run("add", "--inventory", str(path), "--field", "t2_annotations", stdin=json.dumps(notes)))
    assert out["added"] == 4 and len(_load(path)["t2_annotations"]) == 4
    assert {k: out["counts"][k] for k in ("t2_annotations", "t2_past", "t2_future", "functions_enriched")} == \
        {"t2_annotations": 3, "t2_past": 2, "t2_future": 1, "functions_enriched": 1}


def test_top_exports_keep_no_name_off_the_surface(tmp_path):
    """Step 3b's temporal fetch and the Key API Summary read top_exports: a name every export of which is off the
    surface is dropped, as add drops a T3 item named after a held export."""
    path = _init_from(tmp_path, _fixture_run())
    out = _ok(_run("set", "--inventory", str(path), stdin=json.dumps({"top_exports": ["foo", "bar", "helper", "other"]})))
    assert (out["set"], out["dropped"]) == (["top_exports"], ["bar", "helper"])
    assert _load(path)["top_exports"] == ["foo", "other"]
    plain = _ok(_run("set", "--inventory", str(_write(tmp_path)), stdin='{"top_exports": ["parse", "Client"]}'))
    assert plain["dropped"] == [] and plain["counts"]["top_exports"] == 2


def test_the_not_public_warning_names_ten_and_counts_the_rest(tmp_path):
    extraction = _fixture_run()
    names = [f"internal_{i:02d}" for i in range(12)]
    extraction["exports"] = [_fixture_export("foo", "pkg/a.py", 1)] + [
        _fixture_export(name, "pkg/helpers.py", i + 1) for i, name in enumerate(names)]
    data = _load(_init_from(tmp_path, extraction))
    shown = ", ".join(f"{name} (pkg/helpers.py)" for name in names[:10])
    assert data["warnings"] == [NOT_PUBLIC_WARNING.format(n=12, names=shown) + " and 2 more"]


def test_gate_2_sees_an_empty_map_when_every_export_is_off_the_surface(tmp_path):
    """extract.md §6's zero-export check reads `not_public` beside `exports`."""
    extraction = _fixture_run()
    extraction["exports"] = extraction["exports"][1:3]  # foo and baz are not found: only the internals
    counts = _ok(_run("summary", "--inventory", str(_init_from(tmp_path, extraction))))["counts"]
    assert (counts["exports"], counts["not_public"], counts["items"]) == (2, 2, 0)
    six = EXTRACT.read_text(encoding="utf-8")
    six = six[six.index("### 6. Present Extraction Summary"):six.index("### 7. ")]
    assert "the §5 summary counts no export the provenance map will hold (its `exports` is 0, or equals its " \
           "`not_public`)" in six
    zero = next(line for line in (REPO / "src" / "skf-create-skill" / "references" / "sub" / "fetch-docs.md")
                .read_text(encoding="utf-8").splitlines() if line.startswith('- **`source_type: "source"`, `counts.exports`'))
    assert "`counts.exports` is 0 (or equals `counts.not_public`)" in zero


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
@pytest.mark.parametrize("scope_type, sub, mapped, coverage", [
    ("public-api", "def baz():\n    return 4\n", [("foo", "pkg/a.py"), ("baz", "pkg/sub.py")], 1.0),
    ("public-api", "def baz():\n    return 4\n\n\ndef qux():\n    return 5\n",
     [("foo", "pkg/a.py"), ("baz", "pkg/sub.py"), ("qux", "pkg/sub.py")], 1.0),
    ("full-library", "def baz():\n    return 4\n",
     [("foo", "pkg/a.py"), ("bar", "pkg/a.py"), ("helper", "pkg/helpers.py"), ("baz", "pkg/sub.py")], 2.0),
], ids=["public-api", "public-api-qux", "full-library"])
def test_the_fixture_through_the_runner(tmp_path, scope_type, sub, mapped, coverage):
    """The issue's fixture from the runner's real JSON: init, provenance and the stats helper, and for public-api
    the names update's records keeps from the same records, through the same public_surface (#703: create and
    update both mark sub's baz, and qux, public, and the runner counts them in place of sub)."""
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    for name, text in (("__init__.py", "from .a import foo\nfrom . import sub\n"),
                       ("a.py", "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"),
                       ("helpers.py", "def helper():\n    return 3\n"), ("sub.py", sub)):
        (pkg / name).write_bytes(text.encode("utf-8"))
    runner_json = tmp_path / "demo.extraction.json"
    ran = subprocess.run([sys.executable, str(RUNNER), "--mode", "full", "--source-root", str(tmp_path / "src"),
                          "--scope-type", scope_type, "--tier", "Forge", "-o", str(runner_json)],
                         capture_output=True, text=True, encoding="utf-8", timeout=300, check=False)
    assert ran.returncode == 0, ran.stderr
    extraction = _load(runner_json)
    members = len(mapped) - 1 if scope_type == "public-api" else 1
    assert extraction["counts"]["exports_public_api"] == 1 + members  # foo and sub's members
    path = tmp_path / "demo.inventory.json"
    _ok(_run("init", "--inventory", str(path), "--skill", "demo", "--mode", "source", "--tier", "Forge",
             "--extraction", str(runner_json)))
    target = tmp_path / "provenance-map.json"
    _provenance(path, target)
    entries = sorted((e["export_name"], e["source_file"]) for e in _load(target)["entries"])
    assert entries == sorted(mapped)
    if scope_type == "public-api":
        assert set(entries) == _update_marks_public(extraction)
    derived = _stats_of(target, extraction)
    assert (derived["stats"]["exports_documented"], derived["stats"]["public_api_coverage"]) == (len(mapped), coverage)
    assert derived["confidence_distribution"]["t1"] == len(mapped)
    if scope_type == "public-api":
        assert _barrel_findings(extraction, _load(target)["entries"]) == []


def _namespace_run(namespace: dict, exports: list[tuple[str, str]], language: str = "python") -> dict:
    """The fixture run with `sub` replaced by `namespace` and the given (name, file) exports."""
    extraction = _fixture_run()
    extraction["exports"] = [dict(_fixture_export(name, path, 1), language=language) for name, path in exports]
    extraction["entry_point_diff"]["public"] = [extraction["entry_point_diff"]["public"][0],
                                                {"entry": "pkg/__init__.py", "from": ".", "local": None, "line": None,
                                                 "language": language, "via": "namespace", **namespace}]
    extraction["entry_points"]["by_language"] = {language: "barrel"}
    return extraction


@pytest.mark.parametrize("namespace, marked", [
    # members: each one's name (or local) at its file, never the module itself nor its folder; a member with no
    # file (a name of another package) its name, as a public name with no file is
    ({"name": "sub", "file": "pkg/sub.py", "members": [
        {"name": "baz", "local": None, "file": "pkg/sub.py", "line": 1},
        {"name": "alias", "local": "real", "file": "pkg/deep/impl.py", "line": 4},
        {"name": "ext", "local": None, "file": None}]},
     {("sub", "pkg/sub.py"): False, ("sub", "pkg/other.py"): False, ("baz", "pkg/sub.py"): True,
      ("real", "pkg/deep/impl.py"): True, ("baz", "pkg/other.py"): False, ("ext", "pkg/x.py"): True}),
    # an empty module: nothing of its own
    ({"name": "sub", "file": "pkg/sub.py", "members": []},
     {("sub", "pkg/sub.py"): False, ("baz", "pkg/sub.py"): False}),
    # members the runner could not read, and a runner from before members: the item's own pair, no folder
    ({"name": "sub", "file": "pkg/sub.py", "members": None},
     {("sub", "pkg/sub.py"): True, ("sub", "pkg/other.py"): False, ("baz", "pkg/sub.py"): False}),
    ({"name": "sub", "file": "pkg/sub.py"},
     {("sub", "pkg/sub.py"): True, ("sub", "pkg/other.py"): False, ("baz", "pkg/sub.py"): False}),
], ids=["members", "empty", "null-members", "stale-json"])
def test_a_namespace_marks_its_members_in_its_place(tmp_path, namespace, marked):
    """#703: create's init and update's records mark a namespace item's members by the one rule, and the rule
    keeps no folder clause: a name of the item's in its folder is not public for that."""
    extraction = _namespace_run(namespace, [("foo", "pkg/a.py"), *marked])
    data = _load(_init_from(tmp_path, extraction))
    assert {(e["export_name"], e["source_file"]): e["public"] for e in data["exports"]} == \
        {("foo", "pkg/a.py"): True, **marked}
    records, _ = manifest.build_records(extraction, None, None, [])
    assert {(r["name"], b["file_path"]): r["public"] for b in records["files"] for r in b["exports"]} == \
        {("foo", "pkg/a.py"): True, **marked}


def test_an_export_namespace_record_gives_way_to_its_members(tmp_path):
    """A JavaScript `export * as utils from './utils'`: the recipe's record of `utils` at the entry point, which
    the folder clause marked public when the module sat in the entry's folder, is not; the module's members are."""
    extraction = _namespace_run({"name": "utils", "file": "src/utils.ts", "members": [
        {"name": "fmt", "local": None, "file": "src/utils.ts", "line": 1}]},
        [("foo", "pkg/a.py"), ("utils", "src/index.ts"), ("fmt", "src/utils.ts"), ("hidden", "src/utils2.ts")],
        language="javascript")
    extraction["exports"][0]["language"] = "python"
    extraction["entry_points"]["by_language"]["python"] = "barrel"
    data = _load(_init_from(tmp_path, extraction))
    assert {e["export_name"]: e["public"] for e in data["exports"]} == \
        {"foo": True, "utils": False, "fmt": True, "hidden": False}


def test_an_export_read_by_eye_is_marked_by_a_stored_member(tmp_path):
    """`add` reads the members init kept in public_surface: a member read by eye, under the name its file gives
    it, is public."""
    extraction = _namespace_run({"name": "sub", "file": "pkg/sub.py", "members": [
        {"name": "alias", "local": "real", "file": "pkg/sub.py", "line": 7}]}, [("foo", "pkg/a.py")])
    path = _init_from(tmp_path, extraction)
    assert _load(path)["public_surface"]["public"][1]["members"] == [
        {"name": "alias", "local": "real", "file": "pkg/sub.py"}]
    _ok(_run("add", "--inventory", str(path), "--field", "exports", stdin=json.dumps([
        {"export_name": "real", "export_type": "variable", "source_file": "pkg/sub.py", "source_line": 7},
        {"export_name": "sub", "export_type": "module", "source_file": "pkg/sub.py", "source_line": 1}])))
    assert {e["export_name"]: e["public"] for e in _load(path)["exports"]} == {"foo": True, "real": True, "sub": False}


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
