#!/usr/bin/env python3
"""Tests for load-coverage-inputs.py (skf-test-skill coverage-check.md §0, §2, §2b; #613, #540).

coverage-check.md decides whether a bookkeeping variant is a real export and
the two judgments the denominator clause needs; the script picks the clause
and makes every count, the
surfaces of the Quick-tier and fallback per-file scans included (the
branches coverage-check.md §2 loads from coverage-check-tiers.md), and
State 2's (the States 2 to 4 section it loads from coverage-check-branches.md):
  - census: the docs-only verdict from the citation forms a skill writes
  - metadata: Cluster A and B under check-metadata-coherence.py's keys,
    the named-export count, the inflation signature and the declared names,
    and a stack's composition surface
  - surface: the source surface from a --mode full extraction (public names
    less those outside scope, each listed with its line, entry point and
    the brief's exclude glob or missing include glob that scopes it out,
    never the recipes' internal matches), quick
    output, per-file results, names read by eye, or the provenance map and
    metadata (State 2 union and counts, the canonical fold over both), with
    the name sets, the Denominator Candidates (the block coverage-check.md
    §4 appends from coverage-check-branches.md), the guards and the fallback
    verdict; a brief gives the scope when no extraction recorded one, so a
    Quick-tier surface has its scope sets and guards too
  - surface, #677: an include glob that matches no file restores the root
    exports the brief does not exclude (the stale-scope guard), and a
    Python top nested in another top's folder is no barrel
  - surface, #918: each declaration of a surface name exports[] holds in a
    file none of its records names is listed in `otherDeclarations`, and
    changes no record, set or guard
  - surface, #913: a restored name takes the kind the provenance map gives
    it at its file, and score-signatures.py counts it in Type Coverage when
    that is a type kind, else names it in a warning when it has none
  - surface, #1020: so does an extraction gap (a public name no recipe
    found), or any public name exports[] gives no kind at its file, so Type
    Coverage counts it whether or not the guard restored it
The extraction fixture mirrors skf-extract-public-api.py --mode full output;
a last test runs the real extractor when ast-grep is installed.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "skf-test-skill" / "scripts"
SCRIPT = SCRIPTS / "load-coverage-inputs.py"
COHERENCE = SCRIPTS / "check-metadata-coherence.py"
COMPUTE_SCORE = SCRIPTS / "compute-score.py"
EXTRACTOR = REPO_ROOT / "src" / "shared" / "scripts" / "skf-extract-public-api.py"
GAP_LEDGER = SCRIPTS / "gap-ledger.py"
NUMERATOR = SCRIPTS / "verify-declared-numerator.py"
SCORE_SIGNATURES = SCRIPTS / "score-signatures.py"
RESOLVER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-resolve-authoritative-files.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load(SCRIPT, "load_coverage_inputs")
gap_ledger = _load(GAP_LEDGER, "skf_gap_ledger_for_coverage_inputs")


def _write(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return str(path)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")


# A --mode full result: index.ts declares fetchData, Options and Mode and
# re-exports helper; extra.ts (a non-root `exports` subpath) declares Extra
# and Level; internalThing is a recipe match no entry point exports; legacy is
# exported but defined outside scope.include; gapFn is exported but no recipe
# found it.
EXTRACTION = {
    "mode": "full",
    "status": "ok",
    "files_in_scope": 3,
    "truncated": False,
    "files_without_recipes": {},
    "file_issues": [],
    "errors": [],
    "scope": {"include": ["src/**"], "exclude": ["src/vendor/**"], "tier_a_include": None,
              "type": "full-library", "languages": ["typescript"], "files_from": None},
    "exports": [
        {"export_name": "Extra", "export_type": "class", "source_file": "src/extra.ts", "source_line": 1,
         "signature_line": "export class Extra { run(): void {} }"},
        {"export_name": "Level", "export_type": "enum", "source_file": "src/extra.ts", "source_line": 2,
         "signature_line": "export enum Level { Low, High }"},
        {"export_name": "helper", "export_type": "function", "source_file": "src/helper.ts", "source_line": 1,
         "signature_line": "export function helper(x: number): number { return x; }"},
        {"export_name": "internalThing", "export_type": "function", "source_file": "src/helper.ts",
         "source_line": 2, "signature_line": "export function internalThing(): void {}"},
        {"export_name": "fetchData", "export_type": "function", "source_file": "src/index.ts", "source_line": 1,
         "signature_line": "export function fetchData(url: string): Promise<string> {"},
        {"export_name": "Options", "export_type": "interface", "source_file": "src/index.ts", "source_line": 2,
         "signature_line": "export interface Options { retries: number }"},
        {"export_name": "helper", "export_type": "re-export", "source_file": "src/index.ts", "source_line": 3,
         "signature_line": "export { helper } from './helper';"},
        {"export_name": "Mode", "export_type": "type", "source_file": "src/index.ts", "source_line": 4,
         "signature_line": "export type Mode = 'a' | 'b';"},
    ],
    "entry_points": {
        "status": "barrel",
        "files": [
            {"language": "typescript", "file": "src/index.ts", "package": ".", "subpath": ".",
             "resolution": "file", "in_scope": True},
            {"language": "typescript", "file": "src/extra.ts", "package": ".", "subpath": "./extra",
             "resolution": "file", "in_scope": True},
        ],
        "exports_maps": [], "unresolved": [],
    },
    "entry_point_diff": {
        "public": [
            {"name": "Extra", "entry": "src/extra.ts", "via": "declaration", "file": "src/extra.ts", "line": 1},
            {"name": "Level", "entry": "src/extra.ts", "via": "declaration", "file": "src/extra.ts", "line": 2},
            {"name": "Mode", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 4},
            {"name": "Options", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 2},
            {"name": "fetchData", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 1},
            {"name": "gapFn", "entry": "src/index.ts", "via": "re-export", "file": "src/gap.ts", "line": 7},
            {"name": "helper", "entry": "src/index.ts", "via": "re-export", "file": "src/helper.ts", "line": 1},
            {"name": "legacy", "entry": "src/index.ts", "via": "re-export", "file": "lib/legacy.ts", "line": 3},
        ],
        "internal": [{"name": "internalThing", "language": "javascript", "source_file": "src/helper.ts",
                      "source_line": 2}],
        "extraction_gaps": [{"name": "gapFn", "language": "javascript", "entry": "src/index.ts",
                             "file": "src/gap.ts", "line": 7}],
        "outside_scope": [{"name": "legacy", "language": "javascript", "entry": "src/index.ts",
                           "file": "lib/legacy.ts", "line": 3}],
    },
    "counts": {"exports_public_api": 8, "exports_internal": 1, "effective_denominator": 7,
               "effective_denominator_basis": "scope.include", "denominator_files": 4},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
}

METADATA = {
    "skill_type": "single",
    "exports": ["fetchData", "helper", "Options"],
    "stats": {"exports_public_api": 7, "exports_documented": 5, "effective_denominator": 4},
    "confidence_distribution": {"t1": 5, "t1_low": 0, "t2": 0, "t3": 0},
}

PROVENANCE = {"entries": [
    {"export_name": "fetchData", "export_type": "function", "source_file": "src/index.ts", "source_line": 1},
    {"export_name": "helper", "export_type": "function", "source_file": "src/helper.ts", "source_line": 1},
    {"export_name": "Extra::run", "export_type": "function"},
    {"export_name": "Button_def"},
    {"export_name": "Button"},
    {"export_name": "a11y_Checkbox"},
    {"export_name": "mobile_Card"},
    {"export_name": "Card"},
    {"export_name": "mobile_Orphan"},
]}


def _surface(tmp_path: Path, *args: str) -> dict:
    proc = _run("surface", *args, "--output", str(tmp_path / "surface.json"))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert json.loads((tmp_path / "surface.json").read_text(encoding="utf-8")) == out
    return out


# --------------------------------------------------------------------------
# census (#540, #613 item 4)
# --------------------------------------------------------------------------


def _skill(tmp_path: Path, body: str, refs: dict[str, str] | None = None) -> Path:
    root = tmp_path / "skill"
    _write(root / "SKILL.md", body)
    for name, text in (refs or {}).items():
        _write(root / "references" / name, text)
    return root


@pytest.mark.parametrize("body, refs, docs_only", [
    ("Use it [EXT:https://example.com/a]. Then [EXT:https://example.com/b].", {}, True),
    ("Use it [EXT:https://example.com/a] and `go()` [AST:src/a.ts:L3].", {}, False),
    ("Use it [EXT:https://example.com/a].", {"api.md": "`go()` [SRC:src/a.py:L9]"}, False),
    ("[from skill: liba] `connect()` and [EXT:https://example.com]", {}, False),
    ("No citation at all.", {}, False),
    ("[EXT:https://x.dev] [QMD:docs:intro] [DOC:readme]", {}, True),
], ids=["ext-only", "ext-and-ast", "src-in-a-reference", "stack-citation", "none", "qmd-decides-nothing"])
def test_census_decides_docs_only(tmp_path, body, refs, docs_only):
    root = _skill(tmp_path, body, refs)
    proc = _run("census", "--skill-dir", str(root))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["docsOnly"] is docs_only
    assert out["files"][0] == "SKILL.md"


def test_census_counts_each_form(tmp_path):
    root = _skill(tmp_path, "[EXT:a] [EXT:b] [AST:x:L1] [QMD:c:d]", {"r.md": "[SRC:y:L2] [from skill: z]"})
    out = mod.census(str(root))
    assert out["citations"] == {"EXT": 2, "AST": 1, "SRC": 1, "from skill": 1, "QMD": 1, "DOC": 0}
    assert out["localCitations"] == 3


def test_census_without_a_skill_md_exits_1(tmp_path):
    proc = _run("census", "--skill-dir", str(tmp_path))
    assert proc.returncode == 1 and "holds no SKILL.md" in proc.stderr and proc.stdout == ""


# --------------------------------------------------------------------------
# floor (#790): the names the skill documents in a fixed form
# --------------------------------------------------------------------------


def _origin(file: str, line: int, form: str, signature: dict | None = None) -> dict:
    origin = {"file": file, "line": line, "form": form}
    if signature is not None:
        origin["signature"] = signature
    return origin


def _signature(params: str, return_type: str = "") -> dict:
    return {"params": params, "return_type": return_type}


def _usage(usage_signature: str, return_type: str = "") -> dict:
    return {"usage_signature": usage_signature, "return_type": return_type}


API_TABLE = (
    "| Export | Kind | Purpose | Source |\n"                                    # 1
    "| --- | --- | --- | --- |\n"                                               # 2
    "| `fetchData`, `fetchAll` | function | Wraps `inner`. | [AST:src/a.ts:L1] |\n"  # 3
    "| `useQuery<T>()` | hook | Queries. | [AST:src/q.ts:L4] |\n"              # 4
    "| `request(url): Promise<T>` | function | Requests. | |\n"                 # 5
    "| `new Client(opts)` | class | Builds. | |\n"                               # 6
    "| plain | function | No code span. | |\n"                                   # 7
    "\n"                                                                        # 8
    "| API | Purpose |\n"                                                       # 9
    "|-----|---------|\n"                                                       # 10
    "| `connect(url)` | Opens. |\n"                                             # 11
    "\n"                                                                        # 12
    "| Prop | Type |\n"                                                         # 13
    "| --- | --- |\n"                                                           # 14
    "| `size` | number |\n"                                                     # 15
)


def test_floor_lists_export_table_first_column_names(tmp_path):
    """Every code span in the first cell of an export table's row, a leading `new ` and everything from the first
    `(`, `<` or `[` cut, with the row's Kind cell as written; another column's span, a cell with no span and a Prop
    table give none. A first cell that writes a call is the origin's signature (#888), a constructor call as its
    `usage_signature`."""
    out = mod.floor(str(_skill(tmp_path, "# Demo\n", {"api.md": API_TABLE})))
    assert out["files"] == ["SKILL.md", "references/api.md"]
    assert out["names"] == [
        {"name": "Client", "kindLabel": "class",
         "origins": [_origin("references/api.md", 6, "table-row", _usage("new Client(opts)"))]},
        {"name": "connect", "kindLabel": None,
         "origins": [_origin("references/api.md", 11, "table-row", _signature("url"))]},
        {"name": "fetchAll", "kindLabel": "function", "origins": [_origin("references/api.md", 3, "table-row")]},
        {"name": "fetchData", "kindLabel": "function", "origins": [_origin("references/api.md", 3, "table-row")]},
        {"name": "request", "kindLabel": "function",
         "origins": [_origin("references/api.md", 5, "table-row", _signature("url", "Promise<T>"))]},
        {"name": "useQuery", "kindLabel": "hook", "origins": [_origin("references/api.md", 4, "table-row")]},
    ]
    assert out["summary"] == {"names": 6, "byForm": {"table-row": 6, "heading": 0, "declaration": 0}}


@pytest.mark.parametrize("header", ["Functions", "**Hooks**", "__Types__", "CLASSES", "Components", "**Export**",
                                    "APIs", "Symbols"])
def test_floor_reads_plural_and_emphasized_header_words(tmp_path, header):
    body = f"| {header} | **Kind** |\n| --- | --- |\n| `useThing` | hook |\n"
    assert mod.floor(str(_skill(tmp_path, body)))["names"] == [
        {"name": "useThing", "kindLabel": "hook", "origins": [_origin("SKILL.md", 3, "table-row")]}]


@pytest.mark.parametrize("header", ["Name", "**Methods**", "Props", "*Export*", "Exported", "Import"])
def test_floor_reads_no_other_header_word(tmp_path, header):
    body = f"| {header} | Kind |\n| --- | --- |\n| `useThing` | hook |\n"
    assert mod.floor(str(_skill(tmp_path, body)))["names"] == []


def test_floor_keeps_the_first_kind_label_in_origin_order(tmp_path):
    """Two tables label one name differently: the first label in origin order (file order, then line) is the
    name's `kindLabel`, the skill's own label; a later one is not kept."""
    root = _skill(tmp_path, "# Demo\n\n| Export | Kind |\n| --- | --- |\n| `Store` | class |\n", {
        "api.md": "| Export | Kind |\n| --- | --- |\n| `Store` | component |\n\n"
                  "| Type | Kind |\n| --- | --- |\n| `Store` | type |\n"})
    assert mod.floor(str(root))["names"] == [{"name": "Store", "kindLabel": "class", "origins": [
        _origin("SKILL.md", 5, "table-row"), _origin("references/api.md", 3, "table-row"),
        _origin("references/api.md", 7, "table-row")]}]


def test_floor_reads_code_only_headings(tmp_path):
    """A heading whose whole text is one code span; a heading with other words, a dotted name, and a heading in
    the frontmatter, an HTML comment or a fenced block give none. A heading that writes a call is the origin's
    signature (#888)."""
    body = ("---\nname: demo\n# `fm`\n---\n# Demo\n\n"         # 1-6
            "### `Meta<T>`\n\n"                               # 7
            "## Testing with `mount`\n\n"                     # 9
            "### `render(ui)` ###\n\n"                        # 11
            "#### `client.get`\n\n"                           # 13
            "<!--\n### `hidden`\n-->\n\n"                     # 15-18
            "```md\n### `inFence`\n```\n")                    # 19-21
    out = mod.floor(str(_skill(tmp_path, body)))
    assert out["names"] == [
        {"name": "Meta", "kindLabel": None, "origins": [_origin("SKILL.md", 7, "heading")]},
        {"name": "render", "kindLabel": None, "origins": [_origin("SKILL.md", 11, "heading", _signature("ui"))]},
    ]


BRACKET_NAMES = (
    "# Demo\n"                                                                  # 1
    "\n"                                                                        # 2
    "| Export | Kind |\n"                                                       # 3
    "| --- | --- |\n"                                                           # 4
    "| `App[P, R]` | class |\n"                                                 # 5
    "| `LiveMapFeed[K, V]` / `LiveMapView[K, V]` | class |\n"                   # 6
    "| `first[T](xs: list[T]) -> T` | function |\n"                             # 7
    "| `Foo[]`, `Arr[][]`, `Gap[ ]` | type |\n"                                 # 8
    "| `Meta<T>` | type |\n"                                                    # 9
    "| `Foo<T>[]` | type |\n"                                                   # 10
    "| `a.b[T]` | function |\n"                                                 # 11
    "\n"                                                                        # 12
    "### `Box[T]`\n"                                                            # 13
    "\n"                                                                        # 14
    "### `Map[K comparable, V any](m map[K]V) []K`\n"                           # 15
)


def test_floor_cuts_a_name_at_a_bracket(tmp_path):
    """A Python or Go generic is cut at its first `[` as at `(` and `<` (#915): `App[P, R]` gives `App`, in a
    table's first cell or a code-only heading, and a call written that way pins its form, but a Go call whose
    return follows its group with no separator (line 15's `Map`) pins only its name, as any call does that writes
    its return without `->`, `=>`, `→` or `:`. An empty `[]` at the cut (a TS array type, `Foo[]`, `Arr[][]`,
    `Gap[ ]`) gives none; `Foo<T>[]` is cut at `<` first, and a dotted name gives none as before."""
    out = mod.floor(str(_skill(tmp_path, BRACKET_NAMES)))
    assert out["names"] == [
        {"name": "App", "kindLabel": "class", "origins": [_origin("SKILL.md", 5, "table-row")]},
        {"name": "Box", "kindLabel": None, "origins": [_origin("SKILL.md", 13, "heading")]},
        {"name": "Foo", "kindLabel": "type", "origins": [_origin("SKILL.md", 10, "table-row")]},
        {"name": "LiveMapFeed", "kindLabel": "class", "origins": [_origin("SKILL.md", 6, "table-row")]},
        {"name": "LiveMapView", "kindLabel": "class", "origins": [_origin("SKILL.md", 6, "table-row")]},
        {"name": "Map", "kindLabel": None, "origins": [_origin("SKILL.md", 15, "heading")]},
        {"name": "Meta", "kindLabel": "type", "origins": [_origin("SKILL.md", 9, "table-row")]},
        {"name": "first", "kindLabel": "function",
         "origins": [_origin("SKILL.md", 7, "table-row", _signature("xs: list[T]", "T"))]},
    ]
    assert out["summary"] == {"names": 8, "byForm": {"table-row": 6, "heading": 2, "declaration": 0}}


CITED_BLOCKS = (
    "# Demo\n"                                                                  # 1
    "\n"                                                                        # 2
    "Fetches data [AST:src/api.ts:L12] and models [SRC:src/model.py:L3-L9].\n"  # 3
    "\n"                                                                        # 4
    "The client:\n"                                                             # 5
    "\n"                                                                        # 6
    "```ts\n"                                                                   # 7
    "// src/api.ts:12\n"                                                        # 8
    "export interface Options { a: string }\n"                                  # 9
    "const local = 1;\n"                                                        # 10
    "export async function fetchData() {}\n"                                    # 11
    "export default function main() {}\n"                                       # 12
    "// export const commented = 1\n"                                           # 13
    "  export const indented = 1;\n"                                            # 14
    "const t = `\n"                                                             # 15
    "export const inTemplate = 1;\n"                                            # 16
    "`;\n"                                                                      # 17
    "export default class extends Base {}\n"                                    # 18
    "```\n"                                                                     # 19
    "\n"                                                                        # 20
    "```tsx\n"                                                                  # 21
    "export const Primary = {};\n"                                              # 22
    "```\n"                                                                     # 23
    "\n"                                                                        # 24
    "```ts\n"                                                                   # 25
    "// src/other.ts:3\n"                                                       # 26
    "export const Uncited = 1;\n"                                               # 27
    "```\n"                                                                     # 28
    "\n"                                                                        # 29
    "```json\n"                                                                 # 30
    "// src/api.ts:12\n"                                                        # 31
    "{\"export\": \"const Data\"}\n"                                            # 32
    "```\n"                                                                     # 33
    "\n"                                                                        # 34
    "An example [SRC:src/example.py:L1]:\n"                                     # 35
    "\n"                                                                        # 36
    "```python\n"                                                               # 37
    "class User(BaseModel):\n"                                                  # 38
    "    name: str\n"                                                           # 39
    "```\n"                                                                     # 40
    "\n"                                                                        # 41
    "The model:\n"                                                              # 42
    "\n"                                                                        # 43
    "```python\n"                                                               # 44
    "# src/model.py:L3\n"                                                       # 45
    "class Model:\n"                                                            # 46
    "    def save(self): ...\n"                                                 # 47
    "def build(): ...\n"                                                        # 48
    "async def fetch(): ...\n"                                                  # 49
    "def _private(): ...\n"                                                     # 50
    "'''\n"                                                                     # 51
    "def in_docstring(): ...\n"                                                 # 52
    "'''\n"                                                                     # 53
    "```\n"                                                                     # 54
    "\n"                                                                        # 55
    "<!--\n"                                                                    # 56
    "```ts\n"                                                                   # 57
    "// src/api.ts:12\n"                                                        # 58
    "export const Hidden = 1;\n"                                                # 59
    "```\n"                                                                     # 60
    "-->\n"                                                                     # 61
)


def test_floor_reads_public_declarations_in_cited_blocks(tmp_path):
    """A block whose first line is a comment naming a cited path (its line left out): its column-0 public
    declarations, comments and strings masked. An uncited block, one whose comment names a path the skill never
    cites, a data block, a block only the line above cites (a user example) and a block in an HTML comment give
    none."""
    out = mod.floor(str(_skill(tmp_path, CITED_BLOCKS)))
    assert [(n["name"], n["origins"]) for n in out["names"]] == [
        ("Model", [_origin("SKILL.md", 46, "declaration")]),
        ("Options", [_origin("SKILL.md", 9, "declaration")]),
        ("build", [_origin("SKILL.md", 48, "declaration")]),
        ("fetch", [_origin("SKILL.md", 49, "declaration")]),
        ("fetchData", [_origin("SKILL.md", 11, "declaration")]),
        ("main", [_origin("SKILL.md", 12, "declaration")]),
    ]
    assert all(n["kindLabel"] is None for n in out["names"])


HEAD_DECLARATIONS = {"ts": "export const Head = 1;", "python": "class Head: ...", "go": "type Head struct{}",
                     "rust": "pub struct Head;"}


@pytest.mark.parametrize("language, head", [
    ("ts", "// src/api.ts:12"),
    ("ts", "// ./src/api.ts:L12-L30"),
    ("ts", "/* src/api.ts */"),
    ("ts", "/** src/api.ts:L1 **/"),
    ("ts", "// [AST:src/elsewhere.ts:L4]"),
    ("python", "# src/api.ts:12-30"),
    ("python", "## [SRC:src/model.py:L3]"),
    ("go", "// [SRC:src/api.go:L1-9]"),
    ("rust", "-- src/api.ts"),
    ("rust", "<!-- src/api.ts:L2 -->"),
    ("ts", "; src/api.ts"),
], ids=["slash-line", "slash-range", "block", "doc-block", "slash-citation", "hash-range", "hash-citation",
        "go-citation", "dashes", "html", "semicolon"])
def test_floor_a_first_line_comment_heads_a_block(tmp_path, language, head):
    """Each first-line comment form, with no citation above the fence: a citation in it, or a path the skill
    cites elsewhere (its line suffix left out)."""
    body = ("# Demo\n\nThe client [AST:src/api.ts:L12].\n\nNo citation here.\n\n"
            f"```{language}\n{head}\n{HEAD_DECLARATIONS[language]}\n```\n")
    assert [(n["name"], n["origins"]) for n in mod.floor(str(_skill(tmp_path, body)))["names"]] == [
        ("Head", [_origin("SKILL.md", 9, "declaration")])]


@pytest.mark.parametrize("above, head", [
    ("The client [AST:src/api.ts:L12]:", None),
    ("No citation here.", "// [AST:src/api.ts]"),
    ("No citation here.", "src/api.ts:12"),
    ("No citation here.", "// see src/api.ts:12"),
    ("No citation here.", "// src/other.ts:3"),
], ids=["only-the-line-above", "citation-without-a-line", "path-not-in-a-comment", "more-than-a-path",
        "uncited-path"])
def test_floor_nothing_else_heads_a_block(tmp_path, above, head):
    body = (f"# Demo\n\nCited once [AST:src/api.ts:L12].\n\n{above}\n```ts\n" + (f"{head}\n" if head else "")
            + "export const Nope = 1;\n```\n")
    assert mod.floor(str(_skill(tmp_path, body)))["names"] == []


def test_floor_reads_a_long_comment_in_linear_time(tmp_path):
    """A first-line comment with a long run of inner whitespace is read in one pass (a backtracking pattern took
    seconds at 800 spaces)."""
    spaces = " " * 5000
    body = ("# Demo\n\nCited [AST:src/api.ts:L1].\n\n"
            f"```ts\n//{spaces}src/api.ts:1{spaces}\nexport const Kept = 1;\n```\n\n"
            f"```ts\n// a{spaces}b{spaces}*/\nexport const Dropped = 1;\n```\n")
    started = time.perf_counter()
    names = [n["name"] for n in mod.floor(str(_skill(tmp_path, body)))["names"]]
    assert time.perf_counter() - started < 1.0
    assert names == ["Kept"]


@pytest.mark.parametrize("language, code, names", [
    ("ts", "export const a = 1;\nexport let b = 2;\nexport var v = 3;\nexport class C {}\nexport type T = string;\n"
           "export enum E { A }\nexport const enum F { A }\nexport declare function d(): void;\n"
           "export abstract class G {}\nexport function* gen() {}\nexport { x } from './x';\n"
           "export type { Y } from './y';\nexport default class H {}\nexport default async function load() {}\n"
           "export default function() {}\nexport default class extends Base {}\nexport namespace N {}\n",
     ["C", "E", "F", "G", "H", "T", "a", "b", "d", "gen", "load", "v"]),
    ("svelte", "export let prop = 1;\nexport const k = 2;\n", []),
    ("rust", "pub fn connect() {}\npub(crate) fn hidden() {}\npub const fn size() -> usize { 0 }\n"
             "pub const LIMIT: u32 = 3;\npub static mut COUNT: u32 = 0;\npub struct Client;\n"
             "pub async unsafe fn run() {}\nimpl Client {\n    pub fn get(&self) {}\n}\nfn private() {}\n"
             "pub mod inner {}\npub use inner::Thing;\n"
             "#[macro_export]\nmacro_rules! exported {\n    () => {};\n}\nmacro_rules! internal { () => {} }\n"
             "#[macro_export] macro_rules! inline_one { () => {} }\n"
             "#[macro_export]\n#[doc(hidden)]\nmacro_rules! hidden_doc { () => {} }\n"
             "#[macro_export]\nfn not_a_macro() {}\nmacro_rules! after_a_fn { () => {} }\n",
     ["COUNT", "Client", "LIMIT", "connect", "exported", "hidden_doc", "inline_one", "run", "size"]),
    ("go", "func Open() {}\nfunc (c *Client) Get() {}\nfunc private() {}\ntype Client struct{}\n"
           "type handler func()\nvar Default = New()\nvar a, B = 1, 2\nconst Version = \"1\"\n"
           "const (\n\tStatusOK = 200\n\tstatusHidden = 1\n\tA, Bb = 1, 2\n)\n"
           "var (\n\tErrClosed = errors.New(\"closed\")\n)\n"
           "type (\n\tConfig struct {\n\t\tName string\n\t}\n\treader interface {\n\t\tRead() error\n\t}\n"
           "\tID string\n)\n",
     ["A", "B", "Bb", "Client", "Config", "Default", "ErrClosed", "ID", "Open", "StatusOK", "Version"]),
    ("", "export const untagged = 1;\n", []),
    ("java", "public class Main {}\n", []),
], ids=["ts", "svelte", "rust", "go", "untagged", "other-language"])
def test_floor_reads_each_languages_public_declarations(tmp_path, language, code, names):
    body = f"# Demo\n\n```{language}\n// [SRC:src/lib:L1]\n{code}```\n"
    assert [n["name"] for n in mod.floor(str(_skill(tmp_path, body)))["names"]] == names


def test_floor_skips_dotted_names_and_method_tables(tmp_path):
    """A dotted or `::` name gives none, so a namespace-style skill such as zod gets no table floor."""
    body = ("# Demo\n\n| Export | Kind |\n| --- | --- |\n| `cognee.add` | function |\n| `Store::get` | method |\n"
            "| `z.object(shape)` | function |\n\n"
            "| Method | Signature |\n| --- | --- |\n| `close` | `() => void` |\n\n"
            "| Name | Kind |\n| --- | --- |\n| `config` | object |\n\n### `client.fetch()`\n")
    out = mod.floor(str(_skill(tmp_path, body)))
    assert out["names"] == []
    assert out["summary"] == {"names": 0, "byForm": {"table-row": 0, "heading": 0, "declaration": 0}}


def test_floor_reads_direct_references_only(tmp_path):
    root = _skill(tmp_path, "# Demo\n", {"api.md": "### `top`\n", "sub/x.md": "### `nested`\n"})
    out = mod.floor(str(root))
    assert out["files"] == ["SKILL.md", "references/api.md"]
    assert out["names"] == [{"name": "top", "kindLabel": None, "origins": [_origin("references/api.md", 1, "heading")]}]


def test_floor_is_byte_identical_across_runs(tmp_path):
    """The same skill gives the same bytes, each name's origins in file order then line."""
    root = _skill(tmp_path, "# Demo\n\n### `fetchData`\n\n" + CITED_BLOCKS,
                  {"b.md": "### `fetchAll`\n", "api.md": API_TABLE})
    first, second = tmp_path / "floor-1.json", tmp_path / "floor-2.json"
    for target in (first, second):
        proc = _run("floor", "--skill-dir", str(root), "--output", str(target))
        assert proc.returncode == 0, proc.stderr
    assert first.read_bytes() == second.read_bytes()
    out = json.loads(first.read_bytes())
    assert out["files"] == ["SKILL.md", "references/api.md", "references/b.md"]
    fetch_data = next(n for n in out["names"] if n["name"] == "fetchData")
    assert fetch_data == {"name": "fetchData", "kindLabel": "function", "origins": [
        _origin("SKILL.md", 3, "heading"), _origin("SKILL.md", 15, "declaration"),
        _origin("references/api.md", 3, "table-row")]}
    assert [n["name"] for n in out["names"]] == sorted(n["name"] for n in out["names"])


FIXED_FORMS = (
    "# Demo\n"                                                                   # 1
    "\n"                                                                         # 2
    "Cited [SRC:src/a.py:L1], [AST:src/b.ts:L1] and [SRC:src/c.rs:L1].\n"        # 3
    "\n"                                                                         # 4
    "```python\n"                                                                # 5
    "# src/a.py:L1\n"                                                            # 6
    "def f(a: int = 1,\n"                                                        # 7
    "    b: str = \"#x\") -> R: ...\n"                                           # 8
    "def build(): ...\n"                                                         # 9
    "class Model:\n"                                                             # 10
    "    pass\n"                                                                 # 11
    "def p(x) \\\n"                                                              # 12
    "    -> R: ...\n"                                                            # 13
    "```\n"                                                                      # 14
    "\n"                                                                         # 15
    "```ts\n"                                                                    # 16
    "// src/b.ts:1\n"                                                            # 17
    "export declare function d(x: T): void;\n"                                   # 18
    "export function g(): { a: T } {\n"                                          # 19
    "  return x;\n"                                                              # 20
    "}\n"                                                                        # 21
    "export function open(x: T): {\n"                                            # 22
    "  a: T\n"                                                                   # 23
    "} {\n"                                                                      # 24
    "export const arrow = (x: T): R => x;\n"                                     # 25
    "export function check(x: unknown): asserts x is { a: T } {\n"               # 26
    "export function either(x: T): A | {\n"                                      # 27
    "export function sel(sel: (s: S) => T): (state: S) => { value: S } {\n"      # 28
    "export function thunk(): () => { a: number } {\n"                           # 29
    "export function ctor(): new () => { a: T } {\n"                             # 30
    "export function keys(): keyof { a: 1 } {\n"                                 # 31
    "export function cond<T>(x: T): T extends U ? { a: 1 } : never {\n"          # 32
    "export function dangling(x: T): Promise<A> |\n"                             # 33
    "  B {\n"                                                                    # 34
    "```\n"                                                                      # 35
    "\n"                                                                         # 36
    "```rust\n"                                                                  # 37
    "// src/c.rs:L1\n"                                                           # 38
    "pub fn w<'a, T>(x: &'a T) -> &'a str where T: Clone {\n"                    # 39
    "```\n"                                                                      # 40
    "\n"                                                                         # 41
    "```go\n"                                                                    # 42
    "// [SRC:src/d.go:L1]\n"                                                     # 43
    "func New(opts Options) (*Client, error) {\n"                                # 44
    "type Config struct{}\n"                                                     # 45
    "func Any() interface{} {\n"                                                 # 46
    "func Make() struct{ a int } {\n"                                            # 47
    "func Chain(hs ...Handler) func(http.Handler) http.Handler {\n"              # 48
    "func WithTimeout(d time.Duration) func(*Options) {\n"                       # 49
    "func G1(f func(int) int) func(int) int {\n"                                 # 50
    "```\n"                                                                      # 51
    "\n"                                                                         # 52
    "| Export | Kind | Signature | Props |\n"                                    # 53
    "| --- | --- | --- | --- |\n"                                                # 54
    "| `pick` | function | `(x: A \\| B) => C` picks one | |\n"                  # 55
    "| `useQuery<T>()` | hook | | |\n"                                           # 56
    "| `new Client(opts)` | class | `new Client(opts: O)` | |\n"                 # 57
    "| `Meta<T>` | type | `Meta<T>` | |\n"                                       # 58
    "| `one`, `two` | function | `(x) => y` | |\n"                               # 59
    "| `Enhancer` | type | `ArgTypesEnhancer<Renderer>` | |\n"                   # 60
    "| `Docs` | component | | `{ context }: DocsProps`, both required |\n"       # 61
    "| `bare` | function | | |\n"                                                # 62
    "| `fetch(url): Promise<T>` | function | `(url: string) => Response` | |\n"  # 63
    "| `useData(key).data` | hook | | |\n"                                       # 64
    "| `overload(a) / overload(a, b)` | function | | |\n"                        # 65
    "| `since` | function | `(a) => R // since v2` | |\n"                        # 66
    "| `alias` (same as `http.request(opts)`) | function | | |\n"                # 67
    "| `typed(x): Typed` | function | `Typed<X>` | |\n"                          # 68
    "| `other` | function | `elsewhere(a): B` | |\n"                             # 69
    "| `useStore().getState()` | hook | | |\n"                                   # 70
    "| `get(k)` | function | `client.get(k, default=None) -> str` | |\n"         # 71
    "| `Client2(opts)` | class | `new Client2(opts: ClientOptions)` | |\n"       # 72
    "| `run(a, b)` | function | `await run(a, b): Promise<R>` | |\n"             # 73
    "| `useQ(key)` | hook | `const { data } = useQ(key, fn, opts?)` | |\n"       # 74
    "| `make(a)` | function | `make(a, b) // overload` | |\n"                    # 75
    "\n"                                                                         # 76
    "| Function | Signatures |\n"                                                # 77
    "| --- | --- |\n"                                                            # 78
    "| `multi` | `<T>(a: T[]) -> T` |\n"                                         # 79
    "\n"                                                                         # 80
    "| Hook | Params | Returns |\n"                                              # 81
    "| --- | --- | --- |\n"                                                      # 82
    "| `useThing` | `key: string` | `Thing` |\n"                                 # 83
    "\n"                                                                         # 84
    "| API | Parameters |\n"                                                     # 85
    "| --- | --- |\n"                                                            # 86
    "| `call` | `(a, b)` |\n"                                                    # 87
    "\n"                                                                         # 88
    "| Component | Props (simplified) | Purpose |\n"                             # 89
    "| --- | --- | --- |\n"                                                      # 90
    "| `Simple` | `{ a }` | Renders. |\n"                                        # 91
    "\n"                                                                         # 92
    "### `render(ui, options?): Result`\n"                                       # 93
    "\n"                                                                         # 94
    "### `Bare`\n"                                                               # 95
    "\n"                                                                         # 96
    "### `empty()`\n"                                                            # 97
    "\n"                                                                         # 98
    "### `chain(x).value`\n"                                                     # 99
)


def test_floor_records_each_fixed_form(tmp_path):
    """#888: an origin whose place writes the name"s signature in a complete fixed form carries it as `signature`:
    a cited function declaration (its split parameter list joined, its body cut before the return is read, a TS
    object return kept), a table row"s Signature or Signatures cell (its leading code span, `\\|` read as `|`), else
    the one first-cell span that gives the row"s name, and a code-only heading. A Signature cell that writes a usage
    (`new`, `await`, a receiver path, a destructuring assignment) pins it as `usage_signature` and `return_type`
    (step 2). Only then a Props, Params or Parameters cell that is one code span: a parameter group gives its
    params, any other span is `params` whole, and a `Props (simplified)` one is labelled partial. A wrong pin would
    be forced into the inventory, so anything short of a complete form pins nothing: a bare first cell or heading,
    an empty call, a generic-only span, a row naming two names, a Props cell with prose after its span, a type row
    whose Signature cell has no parameter group, text after the group (`useData(key).data`, an overload pair, a
    trailing comment, a chained call), another export"s span in the first cell or the Signature cell, a `const`
    arrow, a non-function declaration, one whose brackets do not close, one whose body opener follows `interface`,
    `struct`, `|`, `is`, `=>`, `keyof` or `?`, one that ends mid-type (`Promise<A> |`, Python's `\\`), and a Go
    function returning a `func(...)` type. A Signature cell with no group falls back to the row's own first-cell
    form; one whose call the floor refuses (a trailing comment) does not, so a shorter first-cell call is never
    pinned in its place. The same skill gives the same bytes."""
    root = _skill(tmp_path, FIXED_FORMS)
    out = mod.floor(str(root))
    assert {n["name"]: [(o["line"], o.get("signature")) for o in n["origins"]] for n in out["names"]} == {
        "Any": [(46, None)],
        "Bare": [(95, None)],
        "Chain": [(48, None)],
        "Client": [(57, _usage("new Client(opts: O)"))],
        "Client2": [(72, _usage("new Client2(opts: ClientOptions)"))],
        "Config": [(45, None)],
        "Docs": [(61, None)],
        "Enhancer": [(60, None)],
        "G1": [(50, None)],
        "Make": [(47, None)],
        "Meta": [(58, None)],
        "Model": [(10, None)],
        "New": [(44, _signature("opts Options", "(*Client, error)"))],
        "Simple": [(91, {**_signature("{ a }"), "signature_form": "partial"})],
        "WithTimeout": [(49, None)],
        "alias": [(67, None)],
        "arrow": [(25, None)],
        "bare": [(62, None)],
        "build": [(9, None)],
        "call": [(87, _signature("a, b"))],
        "chain": [(99, None)],
        "check": [(26, None)],
        "cond": [(32, None)],
        "ctor": [(30, None)],
        "d": [(18, _signature("x: T", "void"))],
        "dangling": [(33, None)],
        "either": [(27, None)],
        "empty": [(97, None)],
        "f": [(7, _signature('a: int = 1, b: str = "#x"', "R"))],
        "fetch": [(63, _signature("url: string", "Response"))],
        "g": [(19, _signature("", "{ a: T }"))],
        "get": [(71, _usage("client.get(k, default=None)", "str"))],
        "keys": [(31, None)],
        "make": [(75, None)],
        "multi": [(79, _signature("a: T[]", "T"))],
        "one": [(59, None)],
        "open": [(22, None)],
        "other": [(69, None)],
        "overload": [(65, None)],
        "p": [(12, None)],
        "pick": [(55, _signature("x: A | B", "C"))],
        "render": [(93, _signature("ui, options?", "Result"))],
        "run": [(73, _usage("await run(a, b)", "Promise<R>"))],
        "sel": [(28, None)],
        "since": [(66, None)],
        "thunk": [(29, None)],
        "two": [(59, None)],
        "typed": [(68, _signature("x", "Typed"))],
        "useData": [(64, None)],
        "useQ": [(74, _usage("const { data } = useQ(key, fn, opts?)"))],
        "useQuery": [(56, None)],
        "useStore": [(70, None)],
        "useThing": [(83, _signature("key: string"))],
        "w": [(39, _signature("x: &'a T", "&'a str"))],
    }
    # an origin with no form carries no `signature` key at all
    assert all(("signature" in o) == (o.get("signature") is not None) for n in out["names"] for o in n["origins"])
    first, second = tmp_path / "floor-1.json", tmp_path / "floor-2.json"
    for target in (first, second):
        proc = _run("floor", "--skill-dir", str(root), "--output", str(target))
        assert proc.returncode == 0, proc.stderr
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_bytes()) == out


def _labelled(signature: dict | None) -> dict | None:
    return None if signature is None else {**signature, "signature_form": "partial"}


@pytest.mark.parametrize("header, labelled", [
    ("Signature (simplified)", True),
    ("**Signatures (Key Parameters)**", True),
    ("Signature (partial)", True),
    ("signature (key params)", True),
    ("Signature ( Key   Parameters )", True),
    ("Signature (TypeScript)", False),
    ("Signature (each name in the row)", False),
    ("Simplified signature", False),
], ids=["simplified", "emphasized-plural-key-parameters", "partial", "lower-case-key-params", "padded-key-parameters",
        "another-label", "a-longer-label", "the-word-first"])
def test_floor_pins_a_signature_header_s_partial_label(tmp_path, header, labelled):
    """#888 step 1: a Signature or Signatures header with one partial label in parentheses after its word, any case
    (`simplified`, `partial`, `key parameters`, `key params`), is read as a Signature column, and each form read
    from it also carries `signature_form` "partial", so the label is the script's, not the reader's, a usage form
    (`client.get(k) -> str`, step 2) too. The label heads that column only: the first-cell form a span with no group
    (`Typed<X>`) falls back to carries none. Any other text after the word, or before it, leaves the column unread,
    as before: the first-cell form is then pinned, with no label. The same skill gives the same bytes."""
    body = (f"| Export | Kind | {header} |\n"                                     # 1
            "| --- | --- | --- |\n"                                               # 2
            "| `fetch` | function | `(url: string) => Response` |\n"              # 3
            "| `other(a): B` | function | `(b: C) => D` |\n"                     # 4
            "| `typed(x): Typed` | function | `Typed<X>` |\n"                     # 5
            "| `get(k)` | function | `client.get(k) -> str` |\n"                 # 6
            "| `request(url): Promise<T>` | function | `(url: string, opts?: O) => T` |\n")  # 7
    root = _skill(tmp_path, body)
    out = mod.floor(str(root))
    cell = {"fetch": _labelled(_signature("url: string", "Response")), "other": _labelled(_signature("b: C", "D")),
            "get": _labelled(_usage("client.get(k)", "str")),
            "request": _labelled(_signature("url: string, opts?: O", "T"))}
    first_cell = {"fetch": None, "other": _signature("a", "B"), "get": _signature("k"),
                  "request": _signature("url", "Promise<T>")}
    expected = {**(cell if labelled else first_cell), "typed": _signature("x", "Typed")}
    assert {n["name"]: [(o["line"], o.get("signature")) for o in n["origins"]] for n in out["names"]} == {
        name: [(line, expected[name])] for name, line in
        (("fetch", 3), ("get", 6), ("other", 4), ("request", 7), ("typed", 5))}
    first, second = tmp_path / "floor-1.json", tmp_path / "floor-2.json"
    for target in (first, second):
        proc = _run("floor", "--skill-dir", str(root), "--output", str(target))
        assert proc.returncode == 0, proc.stderr
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_bytes()) == out


PROPS_FORMS = (
    "| Component | Props | Purpose |\n"                                                       # 1
    "| --- | --- | --- |\n"                                                                     # 2
    "| `Title` | `TitleProps =  { of?: Of }` | Renders the title. |\n"                        # 3
    "| `Panel` | `{ of? }` (all optional) | Renders a story. |\n"                              # 4
    "| `Source` | `{ of? }`, `{ code? }` | Renders source. |\n"                               # 5
    "| `Docs` | `{ context }: DocsProps`, both required: `Docs({ context }: DocsProps)` | Docs. |\n"  # 6
    "| `Stories` | `{ title?: ReactElement \\| string }` | Lists stories. |\n"                # 7
    "| `Handler` | `fn: (x: T) => void` | Handles. |\n"                                       # 8
    "| `Store` | `new Store()` | Builds. |\n"                                                  # 9
    "| `Preview` | `<Preview />` | Previews. |\n"                                              # 10
    "| `Story` | `<Story of={S} />` | One story. |\n"                                          # 11
    "| `useData(key).data` | `{ a }` | Reads. |\n"                                             # 12
    "\n"                                                                                     # 13
    "| Hook | Params | Returns |\n"                                                           # 14
    "| --- | --- | --- |\n"                                                                   # 15
    "| `useKey` | `key: string` | `Thing` |\n"                                                # 16
    "\n"                                                                                     # 17
    "| API | Parameters |\n"                                                                  # 18
    "| --- | --- |\n"                                                                         # 19
    "| `call` | `(a, b)` |\n"                                                                 # 20
    "| `fetchIt` | `await fetchIt(url)` |\n"                                                   # 21
    "\n"                                                                                     # 22
    "| Component | Props (simplified) | Purpose |\n"                                          # 23
    "| --- | --- | --- |\n"                                                                   # 24
    "| `Simple` | `{ title?: string }` | Renders. |\n"                                         # 25
    "\n"                                                                                     # 26
    "| Component | Props / Usage | Key params |\n"                                            # 27
    "| --- | --- | --- |\n"                                                                   # 28
    "| `Unread` | `{ a }` | `{ b }` |\n"                                                      # 29
    "\n"                                                                                     # 30
    "| Export | Kind | Signature | Props |\n"                                                 # 31
    "| --- | --- | --- | --- |\n"                                                             # 32
    "| `add` | function | `await cognee.add(data)` | |\n"                                     # 33
    "| `get` | function | `client.get(k) -> str` | |\n"                                       # 34
    "| `Canvas` | component | `<Canvas of={X} />` | |\n"                                       # 35
    "| `Button` | component | `(props: ButtonProps) => Element` | `{ size? }` |\n"            # 36
    "| `new Client(opts)` | class | | `{ a }` |\n"                                            # 37
    "\n"                                                                                     # 38
    "### `new Client(opts)`\n"                                                               # 39
    "\n"                                                                                     # 40
    "| API | Parameters (key params) |\n"                                                    # 41
    "| --- | --- |\n"                                                                        # 42
    "| `Fn` | `(a, b?)` |\n"                                                                 # 43
    "| `fetchFn` | `await fetchFn(url)` |\n"                                                 # 44
)


def test_floor_pins_a_props_cell_and_a_usage_form(tmp_path):
    """#888 step 2: after the Signature and first-cell forms, a Props, Params or Parameters cell that is exactly one
    code span is pinned, whitespace runs as one space and `\\|` read as `|`: a parameter group gives its params
    (`(a, b)`), a usage its `usage_signature`, and any other span is `params` whole with `return_type` "" (an alias
    such as `TitleProps = {...}` kept), a `Props (simplified)` or `Parameters (key params)` label pinning
    `signature_form` "partial" with any form its cell gives. Trailing prose, several spans (`Docs`'s complete form
    among them), a span with a group that is no form (`fn: (x: T) => void`, `new Store()`), a prop-less element and a
    `Props / Usage` or `Key params` header pin nothing, and a first cell that writes a call the floor cannot pin
    (`useData(key).data`) leaves the Props cell unread. A usage form, in a Signature cell (`await`, a receiver path,
    a JSX element setting a prop), a first cell or a heading (`new Client(opts)`), is pinned as `usage_signature` and
    `return_type`; a Signature form beside a Props cell wins, and so does a first-cell form. The same skill gives the
    same bytes."""
    root = _skill(tmp_path, PROPS_FORMS)
    out = mod.floor(str(root))
    assert {n["name"]: [(o["line"], o.get("signature")) for o in n["origins"]] for n in out["names"]} == {
        "Button": [(36, _signature("props: ButtonProps", "Element"))],
        "Canvas": [(35, _usage("<Canvas of={X} />"))],
        "Client": [(37, _usage("new Client(opts)")), (39, _usage("new Client(opts)"))],
        "Docs": [(6, None)],
        "Fn": [(43, _labelled(_signature("a, b?")))],
        "Handler": [(8, None)],
        "Panel": [(4, None)],
        "Preview": [(10, None)],
        "Simple": [(25, _labelled(_signature("{ title?: string }")))],
        "Source": [(5, None)],
        "Store": [(9, None)],
        "Stories": [(7, _signature("{ title?: ReactElement | string }"))],
        "Story": [(11, _usage("<Story of={S} />"))],
        "Title": [(3, _signature("TitleProps = { of?: Of }"))],
        "Unread": [(29, None)],
        "add": [(33, _usage("await cognee.add(data)"))],
        "call": [(20, _signature("a, b"))],
        "fetchFn": [(44, _labelled(_usage("await fetchFn(url)")))],
        "fetchIt": [(21, _usage("await fetchIt(url)"))],
        "get": [(34, _usage("client.get(k)", "str"))],
        "useData": [(12, None)],
        "useKey": [(16, _signature("key: string"))],
    }
    first, second = tmp_path / "floor-1.json", tmp_path / "floor-2.json"
    for target in (first, second):
        proc = _run("floor", "--skill-dir", str(root), "--output", str(target))
        assert proc.returncode == 0, proc.stderr
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_bytes()) == out


@pytest.mark.parametrize("span, name", [
    ("new Client()", "Client"), ("<Canvas />", "Canvas"), ("<Canvas of={X} /> <Canvas />", "Canvas"),
    ("<Canvas>x</Canvas>", "Canvas"), ("client.get(k).data", "get"), ("x = Canvas(a) + 1", "Canvas"),
    ("Canvas(a)", "Canvas"), ("cognee.Canvas.call(a)", "Canvas"), ("<Canvas of={X />", "Canvas"),
    ('<Canvas title="x />', "Canvas"), ("x == run(a)", "run"), ("x => run(a)", "run")])
def test_a_usage_form_needs_a_prefix_and_the_name_s_complete_form(span, name):
    """#888 step 2: a usage form is a prefix (an assignment, `await`, `new`, a receiver or module path) and the name's
    complete form, or one self-closing element of the name setting a prop: an empty call, a prop-less element, two
    elements, an element with children, text after the group, no prefix, another name after the path, an unclosed
    brace or string, and a comparison or arrow (`==`, `=>`) in place of an assignment give none."""
    assert mod._usage_form(span, name) is None


@pytest.mark.parametrize("span, name", [
    ("const [state, setState] = useState(initial)", "useState"), ("a, b = run(x)", "run"),
    ("const { a: { b } } = useX(k)", "useX"), ("await new Client(a)", "Client"), ('<Link href="/docs" />', "Link")])
def test_a_usage_form_reads_its_whole_prefix_and_element(span, name):
    """#888 step 2: an assignment to an array pattern, a comma list or a nested object pattern, `await` then `new`,
    and an element whose quoted prop holds a `/` are each a usage form: the span whole, with no return."""
    assert mod._usage_form(span, name) == {"usage_signature": span, "return_type": ""}


@pytest.mark.parametrize("span", ["ButtonProps", "HTMLAttributes<HTMLDivElement>", "ComponentProps<typeof Link>",
                                  "None", "-", "\u2013", "\u2014"])
def test_a_props_cell_that_only_names_a_type_pins_nothing(span):
    """#888 step 2: a Props, Params or Parameters span that only names a type (one identifier or dotted path, then at
    most one `<...>` type-argument list) or writes a placeholder dash lists no prop or parameter, so it pins none,
    while `key: string`, `{ a }` and `TitleProps = { of?: Of }` stay pinned."""
    assert mod._row_form(["Component", "Props"], ["`Button`", f"`{span}`"]) is None
    for kept in ("key: string", "{ a }", "TitleProps = { of?: Of }"):
        assert mod._row_form(["Component", "Props"], ["`Button`", f"`{kept}`"]) == _signature(kept)


def test_floor_without_skill_md_exits_1(tmp_path):
    proc = _run("floor", "--skill-dir", str(tmp_path))
    assert proc.returncode == 1 and "holds no SKILL.md" in proc.stderr and proc.stdout == ""
    root = _skill(tmp_path / "bad", "# Demo\n")
    _write(root / "references" / "api.md", b"\xff\xfe broken")
    proc = _run("floor", "--skill-dir", str(root), "--output", str(tmp_path / "floor.json"))
    assert proc.returncode == 1 and "references/api.md" in proc.stderr and not (tmp_path / "floor.json").exists()


# --------------------------------------------------------------------------
# metadata (#613 item 3)
# --------------------------------------------------------------------------


def test_metadata_counts_feed_check_metadata_coherence(tmp_path):
    out = mod.metadata_inputs(METADATA, PROVENANCE)
    assert out["clusterA"] == {"exports_public_api": 7, "exports_length": 3}
    assert out["clusterB"] == {"exports_documented": 5}
    assert out["confidenceDistribution"] == {"t1": 5, "t1_low": 0, "t2": 0, "t3": 0}
    assert out["namedExports"]["count"] == 8 and "Extra::run" not in out["namedExports"]["names"]
    assert out["inflationSignature"] is False
    assert out["declaredNames"] == ["Options", "fetchData", "helper"]
    # check-metadata-coherence.py reads the same file by path.
    path = _write(tmp_path / "coverage-inputs.json", out)
    proc = subprocess.run([sys.executable, str(COHERENCE), "--inputs", path], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    coherence = json.loads(proc.stdout)
    assert coherence["clusterBCounts"] == {"stats.exports_documented": 5, "provenance named-exports": 8,
                                           "confidence_distribution sum": 5}


def test_metadata_flags_the_inflation_signature():
    meta = {**METADATA, "stats": {"exports_documented": 4, "effective_denominator": 4}}
    out = mod.metadata_inputs(meta, None)
    assert out["inflationSignature"] is True
    assert out["provenanceExportNames"] is None and out["namedExports"] is None


# #734: the map holds `foo` at src/a.ts and at src/b.ts (a name the entry points pass on from two files)
TWO_FILE_PROVENANCE = {"entries": [
    {"export_name": "foo", "export_type": "function", "source_file": "src/a.ts", "source_line": 1},
    {"export_name": "foo", "export_type": "function", "source_file": "src/b.ts", "source_line": 1},
    {"export_name": "bar", "export_type": "function", "source_file": "src/b.ts", "source_line": 2},
]}


# #734: a map whose `Foo` carries two `::` methods: two named exports, four distinct entry names
METHOD_PROVENANCE = {"entries": [{"export_name": name, "export_type": "function", "source_file": "src/foo.rs",
                                  "source_line": line}
                                 for line, name in enumerate(["Foo", "Foo::new", "Foo::run", "bar"], 1)]}
# `Foo` at two files beside `Foo::new` and `bar`: three distinct entry names, one of them a method
COINCIDENT_METHOD_PROVENANCE = {"entries": [
    {"export_name": "Foo", "export_type": "struct", "source_file": "src/a.rs", "source_line": 1},
    {"export_name": "Foo", "export_type": "struct", "source_file": "src/b.rs", "source_line": 1},
    {"export_name": "Foo::new", "export_type": "function", "source_file": "src/a.rs", "source_line": 2},
    {"export_name": "bar", "export_type": "function", "source_file": "src/a.rs", "source_line": 5},
]}
METHODS_ONLY_PROVENANCE = {"entries": [{"export_name": name, "export_type": "function"}
                                       for name in ("Foo::new", "Foo::run")]}


@pytest.mark.parametrize(("exports", "stats", "provenance", "signature", "named"), [
    (["foo", "bar"], {"exports_documented": 3, "effective_denominator": 2}, TWO_FILE_PROVENANCE, True, 2),
    (["foo", "bar"], {"exports_documented": 3, "effective_denominator": 3}, TWO_FILE_PROVENANCE, True, 2),
    (["foo", "bar"], {"exports_documented": 3, "effective_denominator": 4}, TWO_FILE_PROVENANCE, False, 2),
    (["foo", "bar"], {"effective_denominator": 2}, TWO_FILE_PROVENANCE, True, 2),
    (["Foo", "Foo::new", "Foo::run", "bar"], {"exports_documented": 4, "effective_denominator": 2},
     METHOD_PROVENANCE, False, 2),
    ([], {"effective_denominator": 0}, {"entries": []}, False, 0),
    (["foo", "bar"], {"exports_documented": 5}, PROVENANCE, False, 8),
    (["Foo", "bar", "baz"], {"exports_documented": 4, "effective_denominator": 3}, COINCIDENT_METHOD_PROVENANCE,
     False, 2),
    ([], {"effective_denominator": 2}, METHODS_ONLY_PROVENANCE, False, 0),
], ids=["two-entries-one-name", "documented-equals-the-count", "neither-equals", "no-documented-count",
        "method-entries", "empty-map", "no-stored-count", "method-entries-matching-by-chance", "methods-only"])
def test_the_inflation_signature_compares_the_stored_count_with_the_map_names_too(exports, stats, provenance,
                                                                                  signature, named):
    """#734: the stored count counts each name once and the map holds a name passed on from two files twice,
    so the signature fires when `stats.exports_documented` or the map's distinct entry names equal it. A map
    with a `::` entry never takes the map arm, even when its names match the stored count by chance, so a
    skill with methods behaves as before; an empty map fires nothing."""
    out = mod.metadata_inputs({"skill_type": "single", "exports": exports, "stats": stats}, provenance)
    assert out["inflationSignature"] is signature
    assert out["namedExports"]["count"] == named
    assert out["clusterB"] == {"exports_documented": stats.get("exports_documented")}


def test_the_map_arm_of_the_signature_runs_the_numerator_check_and_records_its_gap(tmp_path):
    """#734: a skill whose map holds `foo` at two files (3 entries, 2 names) stores 3 documented exports against
    a count of 2. The map's arm fires the signature, so verify-declared-numerator.py checks the declared names
    instead of reporting `skipped`, and the gap it raises claims neither that `stats.exports_documented` equals
    the denominator nor that it should be set by hand."""
    meta = _write(tmp_path / "skill" / "metadata.json", {"skill_type": "single", "exports": ["foo", "bar"],
                                                         "stats": {"exports_documented": 3,
                                                                   "effective_denominator": 2}})
    _write(tmp_path / "skill" / "SKILL.md", "# demo\n\n- `bar()`: returns nothing.\n")
    provenance = _write(tmp_path / "provenance-map.json", TWO_FILE_PROVENANCE)
    inputs = tmp_path / "run" / "coverage-inputs.json"
    proc = _run("metadata", "--metadata", meta, "--provenance", provenance, "--output", str(inputs))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["inflationSignature"] is True
    proc = subprocess.run([sys.executable, str(NUMERATOR), "--inputs", str(inputs), "--skill-dir",
                           str(tmp_path / "skill")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    numerator = json.loads(proc.stdout)
    assert (numerator["skipped"], numerator["declared"], numerator["verified"], numerator["absent"],
            numerator["inflated"]) == (False, 2, 1, ["foo"], True)
    [gap] = gap_ledger.from_numerator(numerator, "skill/metadata.json")
    assert (gap["severity"], gap["category"], gap["source"]) == ("High", "numerator-inflation", "skill/metadata.json")
    assert gap["title"] == "numerator inflation: 1 of 2 declared exports absent from SKILL.md/references"
    assert gap["issue"] == ("a declared count (`stats.exports_documented`, or the provenance map's distinct entry "
                            "names) equals `stats.effective_denominator`, and these declared exports are absent "
                            "from SKILL.md and references/: `foo`")
    assert gap["remediation"] == ("Document the absent exports in SKILL.md or references/: the skill documents 1 "
                                  "of its 2 declared exports.")


def test_metadata_declared_names_fall_back_to_the_provenance_map():
    out = mod.metadata_inputs({"stats": {}}, PROVENANCE)
    assert "fetchData" in out["declaredNames"] and "Extra::run" not in out["declaredNames"]


def test_a_stack_denominator_comes_from_its_cited_contracts():
    meta = {"skill_type": "stack", "libraries": ["liba", "libb"], "integration_pairs": [["liba", "libb"]]}
    prov = {"entries": [{"export_name": "connect"}, {"export_name": "connect"}, {"export_name": "Client"},
                        {"export_name": "Client::new"}]}
    out = mod.metadata_inputs(meta, prov)
    assert out["stack"] == {"basis": "provenance", "denominator": 2, "compositionNames": ["Client", "connect"]}


def test_a_stack_without_a_map_counts_libraries_and_pairs():
    meta = {"skill_type": "stack", "libraries": ["liba", {"name": "libb"}],
            "integration_pairs": [["liba", "libb"], {"a": "libb", "b": "libc"}]}
    out = mod.metadata_inputs(meta, None)
    assert out["stack"] == {"basis": "composition", "denominator": 4,
                            "compositionNames": ["liba", "libb", "liba + libb", "libb + libc"]}


def test_metadata_cli_writes_the_file(tmp_path):
    meta = _write(tmp_path / "metadata.json", METADATA)
    out_path = tmp_path / "run" / "coverage-inputs.json"
    proc = _run("metadata", "--metadata", meta, "--output", str(out_path))
    assert proc.returncode == 0 and json.loads(out_path.read_text(encoding="utf-8")) == json.loads(proc.stdout)


def test_a_missing_metadata_file_exits_1(tmp_path):
    proc = _run("metadata", "--metadata", str(tmp_path / "absent.json"))
    assert proc.returncode == 1 and "cannot read --metadata" in proc.stderr


# --------------------------------------------------------------------------
# surface: a --mode full extraction (wave-3 determinism-1, determinism-5)
# --------------------------------------------------------------------------


def test_the_extraction_surface_is_the_public_names_less_outside_scope(tmp_path):
    extraction = _write(tmp_path / "extract-full.json", EXTRACTION)
    out = _surface(tmp_path, "--extraction", extraction)
    assert out["sets"]["all"] == ["Extra", "Level", "Mode", "Options", "fetchData", "gapFn", "helper"]
    assert "internalThing" not in out["sets"]["all"], "a recipe match no entry point exports is internal"
    # #796: each row keeps its line and entry point, and says why the brief scopes its file out: no include glob
    assert out["excluded"]["outsideScope"] == [{"name": "legacy", "file": "lib/legacy.ts", "line": 3,
                                                "entry": "src/index.ts", "excludeGlob": None,
                                                "outsideInclude": True}]
    assert out["extractionGaps"] == [{"name": "gapFn", "file": "src/gap.ts", "line": 7}]
    kinds = {e["name"]: e["kind"] for e in out["exports"]}
    # A re-export takes the kind recorded at the file that defines it.
    assert kinds == {"Extra": "class", "Level": "enum", "Mode": "type", "Options": "interface",
                     "fetchData": "function", "gapFn": None, "helper": "function"}
    helper = next(e for e in out["exports"] if e["name"] == "helper")
    assert (helper["file"], helper["line"]) == ("src/helper.ts", 1)
    assert out["extraction"]["fallback"] == {"needed": False, "reason": None}


def test_the_extraction_name_sets_and_candidates(tmp_path):
    extraction = _write(tmp_path / "extract-full.json", EXTRACTION)
    meta = _write(tmp_path / "metadata.json", METADATA)
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    out = _surface(tmp_path, "--extraction", extraction, "--metadata", meta, "--provenance", prov)
    # With an extraction the metadata and the map are baselines and add no name.
    assert out["sets"]["all"] == ["Extra", "Level", "Mode", "Options", "fetchData", "gapFn", "helper"]
    assert out["sets"]["scope.include"] == ["Extra", "Level", "Mode", "Options", "fetchData", "gapFn", "helper"]
    assert "tier_a_include" not in out["sets"]
    assert out["sets"]["subpaths"] == ["Extra", "Level"]
    assert out["sets"]["root"] == ["Mode", "Options", "fetchData", "gapFn", "helper", "legacy"]
    assert out["candidates"] == {"statsEffectiveDenominator": 4, "tierAIncludeUnion": None,
                                 "scopeIncludeUnion": 7, "tierAIncludeFiles": None, "scopeIncludeFiles": 4,
                                 "subpathUnion": 2, "subpathEntries": 1, "rootBarrel": 6,
                                 "extractorEffectiveDenominator": 7, "extractorBasis": "scope.include"}
    guards = out["guards"]
    assert guards["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 4,
                                   "rederived": 7, "pct": 75.0, "fires": True}
    assert guards["inflation"] == {"applicable": True, "scopeIncludeUnion": 7, "provenanceEntries": 9,
                                   "pct": -22.22, "fires": False}
    assert guards["umbrella"]["ratio"] == 0.5 and guards["umbrella"]["umbrella"] is False
    assert out["state2"] is None


def test_candidates_count_the_files_each_scope_set_sits_at(tmp_path):
    """#822: the stratified-scope, specific-modules and multi-entry Denominator annotations read their file
    counts from `candidates`: the files that define each scope set's names, and the subpath entry points."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["tier_a_include"] = ["src/index.ts", "src/extra.ts"]
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert out["sets"]["tier_a_include"] == ["Extra", "Level", "Mode", "Options", "fetchData"]
    candidates = out["candidates"]
    # tier A: index.ts and extra.ts; scope.include: those two, gap.ts and helper.ts (legacy's lib/ file is out)
    assert (candidates["tierAIncludeFiles"], candidates["scopeIncludeFiles"], candidates["subpathEntries"]) == (2, 4, 1)
    assert (candidates["tierAIncludeUnion"], candidates["scopeIncludeUnion"], candidates["subpathUnion"]) == (5, 7, 2)


def test_no_tier_a_set_has_no_tier_a_file_count(tmp_path):
    """#822: with no tier A list the tier A file count is null, as its union is (the annotation reads `absent`),
    and so is the subpath entry count of an extraction whose `exports` map has no non-root subpath."""
    data = json.loads(json.dumps(EXTRACTION))
    data["entry_points"]["files"] = data["entry_points"]["files"][:1]
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert "tier_a_include" not in out["sets"] and "subpaths" not in out["sets"]
    candidates = out["candidates"]
    assert candidates["tierAIncludeFiles"] is None and candidates["tierAIncludeUnion"] is None
    assert candidates["subpathEntries"] is None and candidates["subpathUnion"] is None
    assert candidates["scopeIncludeFiles"] == 4


def _subpath_entry(file: str, subpath: str, in_scope: bool = True) -> dict:
    return {"language": "typescript", "file": file, "package": ".", "subpath": subpath, "resolution": "file",
            "in_scope": in_scope}


@pytest.mark.parametrize("subpaths, count", [
    # two subpaths behind one file: two entry points
    ([_subpath_entry("src/extra.ts", "./extra"), _subpath_entry("src/extra.ts", "./extra/index")], 2),
    # an entry point outside the files in scope is no subpath the skill documents
    ([_subpath_entry("src/extra.ts", "./extra"), _subpath_entry("lib/legacy.ts", "./legacy", False)], 1),
    # one subpath whose conditions name two files: one entry point
    ([_subpath_entry("src/extra.ts", "./extra"), _subpath_entry("src/extra.mjs", "./extra")], 1),
], ids=["shared-file", "out-of-scope-entry", "two-files-one-subpath"])
def test_the_subpath_entry_count_is_the_in_scope_subpaths(tmp_path, subpaths, count):
    """#822: `subpathEntries` counts each in-scope non-root subpath once: not the files behind them, and not an
    entry point the scope leaves out."""
    data = json.loads(json.dumps(EXTRACTION))
    data["entry_points"]["files"] = data["entry_points"]["files"][:1] + subpaths
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert out["sets"]["subpaths"] == ["Extra", "Level"]
    assert out["candidates"]["subpathEntries"] == count


def test_a_tier_a_set_keeps_both_guards_off_on_the_standard_barrel(tmp_path):
    """A tier A set keeps both guards off on the standard barrel, whose ladder holds no stored count: the
    deflation guard reads the scope.include union (#813 measures a stored count against the tier A set only on
    stratified-scope, specific-modules and multi-entry)."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["tier_a_include"] = ["src/index.ts"]
    extraction = _write(tmp_path / "extract-full.json", data)
    meta = _write(tmp_path / "metadata.json", METADATA)
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "x"}]})
    out = _surface(tmp_path, "--extraction", extraction, "--metadata", meta, "--provenance", prov)
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 4,
                                          "rederived": 7, "pct": 75.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False
    # #695: an extraction written before the runner listed unmatched tier A globs reads as listing none
    assert "unmatched_tier_a_include" not in data["scope"]
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}


def _stale_tier_a(tmp_path: Path, tier_a: list[str], unmatched: list[str], include: list[str] | None = None,
                  stats: dict | None = None) -> dict:
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"].update(tier_a_include=tier_a, unmatched_include=[], unmatched_tier_a_include=unmatched)
    if include is not None:
        data["scope"]["include"] = include
    data["warnings"] = [f"scope.tier_a_include pattern {g!r} matches no file" for g in unmatched]
    extraction = _write(tmp_path / "extract-full.json", data)
    meta = _write(tmp_path / "metadata.json", METADATA if stats is None else {**METADATA, "stats": stats})
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "x"}]})
    return _surface(tmp_path, "--extraction", extraction, "--metadata", meta, "--provenance", prov)


def test_a_stale_tier_a_glob_counts_no_name(tmp_path):
    """#695: the runner lists one of the two tier A globs as matching no file. The stale-scope guard
    fires and names it, the set comes from the glob that matched, and that glob keeps both guards off."""
    # The loader never matches a glob itself: it trusts the runner's list, so the listed glob counts no
    # name even where a record's file would match it.
    out = _stale_tier_a(tmp_path, ["src/index.ts", "src/extra.ts"], ["src/extra.ts"])
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["candidates"]["tierAIncludeUnion"] == 3
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": True, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": ["src/extra.ts"], "restored": []}
    assert out["guards"]["deflation"]["fires"] is False
    assert out["guards"]["inflation"]["applicable"] is False
    assert out["warnings"] == ["extract-full.json: scope.tier_a_include pattern 'src/extra.ts' matches no file"]
    [record] = gap_ledger.from_guards(out)
    assert (record["category"], record["title"]) == (
        "brief-scope-stale", "stale brief scope: scope.tier_a_include globs match no source file")


def test_a_brief_with_only_stale_tier_a_globs_still_fires_the_guard(tmp_path):
    """#695: with no scope.include glob, a stale tier A glob alone makes the stale-scope guard apply and
    fire, and the ledger records one brief-scope-stale gap."""
    out = _stale_tier_a(tmp_path, ["src/old/**"], ["src/old/**"], include=[])
    stale = out["guards"]["staleScope"]
    assert (stale["applicable"], stale["fires"], stale["unmatchedTierAInclude"]) == (True, True, ["src/old/**"])
    records = [r for r in gap_ledger.from_guards(out) if r["category"] == "brief-scope-stale"]
    assert [r["title"] for r in records] == ["stale brief scope: scope.tier_a_include globs match no source file"]


def test_with_no_tier_a_glob_matching_both_guards_run(tmp_path):
    """#695: every tier A glob is stale, so surface.json has no tier_a_include set (the protocol and
    Type Coverage fall to the next set) and the deflation and inflation guards run and fire."""
    out = _stale_tier_a(tmp_path, ["src/old/**", "src/gone.ts"], ["src/old/**", "src/gone.ts"])
    assert "tier_a_include" not in out["sets"]
    assert out["candidates"]["tierAIncludeUnion"] is None
    assert out["guards"]["staleScope"]["fires"] is True
    assert out["guards"]["staleScope"]["unmatchedTierAInclude"] == ["src/old/**", "src/gone.ts"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 4,
                                          "rederived": 7, "pct": 75.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 7, "provenanceEntries": 1,
                                          "pct": 600.0, "fires": True}
    records = gap_ledger.from_guards(out)
    assert [r["category"] for r in records] == ["metadata-drift", "denominator-inflation", "brief-scope-stale"]
    assert all(r["issue"].endswith("and no `scope.tier_a_include` glob in the brief matches a file")
               for r in records[:2])
    assert out["guards"]["tierAInclude"] == ["src/old/**", "src/gone.ts"]


def test_a_stored_zero_is_deflation_not_a_denominator(tmp_path):
    """#712: a stratified skill whose Create Skill run stored an effective_denominator of 0 (every tier A glob
    stale) is deflation against the re-derived surface, with no percentage above 0, and the ledger gives one
    Medium metadata-drift gap that reads, not a 0-export halt."""
    out = _stale_tier_a(tmp_path, ["src/old/**"], ["src/old/**"], stats={"effective_denominator": 0})
    assert out["candidates"]["statsEffectiveDenominator"] == 0
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 0,
                                          "rederived": 7, "pct": None, "fires": True}
    records = gap_ledger.from_guards(out)
    drift = [r for r in records if r["category"] == "metadata-drift"]
    assert [(r["severity"], r["title"]) for r in drift] == [
        ("Medium", "denominator deflation: effective_denominator below source public surface without tier_a_include")]
    assert drift[0]["issue"] == (
        "the re-derived surface counts 7 exports against a `stats.effective_denominator` of 0, and no "
        "`scope.tier_a_include` glob in the brief matches a file")
    assert "brief-scope-stale" in [r["category"] for r in records]


def test_a_stored_zero_over_an_empty_surface_does_not_fire(tmp_path):
    """#712: with nothing re-derived there is nothing above the stored 0."""
    out = _stale_tier_a(tmp_path, ["src/old/**"], ["src/old/**"], include=["nothing/**"],
                        stats={"effective_denominator": 0})
    assert out["sets"]["scope.include"] == []
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 0,
                                          "rederived": 0, "pct": None, "fires": False}


def test_a_stored_zero_under_a_live_tier_a_set_on_the_standard_barrel_does_not_fire(tmp_path):
    """#712 leaves this open on purpose: with a tier_a_include set the scope.include guard stays off, so a stored
    0 is not deflation on the standard barrel, whose ladder holds no stored count (on the clauses whose ladder
    does, #813 measures it against the set: test_a_stored_zero_against_a_tier_a_set_is_drift)."""
    out = _stale_tier_a(tmp_path, ["src/index.ts"], [], stats={"effective_denominator": 0})
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 0,
                                          "rederived": 7, "pct": None, "fires": False}


@pytest.mark.parametrize("tier_a", [["lib/**"], ["src/vendor/**"], ["src/reexports.ts"]],
                         ids=["out-of-scope-only", "excluded-only", "nameless"])
def test_a_tier_a_list_that_counts_no_name_gives_no_set(tmp_path, tier_a):
    """#712: a live tier A glob whose files define no name in the surface (out of scope, excluded, or a barrel
    that only re-exports) counts no name either: no tier_a_include set, and both guards run."""
    out = _stale_tier_a(tmp_path, tier_a, [])
    assert "tier_a_include" not in out["sets"]
    assert out["candidates"]["tierAIncludeUnion"] is None
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 4,
                                          "rederived": 7, "pct": 75.0, "fires": True}
    assert out["guards"]["inflation"]["fires"] is True
    assert out["guards"]["staleScope"]["fires"] is False
    assert out["guards"]["tierAInclude"] == tier_a
    deflation, inflation = gap_ledger.from_guards(out)
    assert all(r["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")
               for r in (deflation, inflation))
    assert inflation["remediation"].startswith("Edit `scope.tier_a_include`")


def test_a_tier_a_glob_over_a_named_re_export_from_outside_scope_gives_no_set(tmp_path):
    """#725: a name an in-scope barrel re-exports by name from a file scope.include leaves out has no
    outside_scope row, so it stays in the surface; a tier A name counts only in a file scope.include matches."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["tier_a_include"] = ["lib/gen.ts"]
    data["entry_point_diff"]["public"].append(
        {"name": "gen", "entry": "src/index.ts", "via": "re-export", "file": "lib/gen.ts", "line": 1})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert "gen" in out["sets"]["all"] and "gen" not in out["sets"]["scope.include"]
    assert "tier_a_include" not in out["sets"]
    assert out["candidates"]["tierAIncludeUnion"] is None


def test_a_fallback_extraction_gives_only_its_scope_and_stale_globs(tmp_path):
    """#712: the fallback per-file scan passes the runner's exit-3 JSON beside its per-file results: its stale
    tier A glob counts no name and fires the stale-scope guard, the deflation guard runs on the per-file names,
    and the extraction adds no name and no `subpaths` or `root` set."""
    data = json.loads(json.dumps(EXTRACTION))
    data.update(status="no-ast-grep", exports=[], counts=None)
    data["scope"].update(tier_a_include=["src/old/**"], unmatched_include=[], unmatched_tier_a_include=["src/old/**"])
    data["warnings"] = ["scope.tier_a_include pattern 'src/old/**' matches no file",
                        "ast-grep is not on PATH: no recipe ran; extract by source reading"]
    per_file = _write(tmp_path / "per-file-1.txt", json.dumps({
        "file": "src/index.ts", "exports_found": ["fetchData", "Options"], "types_found": ["Options"],
        "signature_mismatches": []}))
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    out = _surface(tmp_path, "--per-file", per_file, "--extraction", _write(tmp_path / "extract-full.json", data),
                   "--metadata", meta)
    assert out["extraction"]["fallback"] == {"needed": True, "reason": "no ast-grep the runner can run"}
    assert out["sets"] == {"all": ["Options", "fetchData"], "scope.include": ["Options", "fetchData"]}
    assert out["excluded"] == {"outsideScope": [], "nestedEntries": []} and out["extractionGaps"] == []
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": True, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": ["src/old/**"], "restored": []}
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                          "rederived": 2, "pct": 100.0, "fires": True}
    assert out["guards"]["umbrella"] == mod.NO_UMBRELLA
    assert out["warnings"][0] == "extract-full.json: scope.tier_a_include pattern 'src/old/**' matches no file"


def test_a_namespace_gives_its_members_in_its_place(tmp_path):
    """#703: a namespace item (`export * as ns`, a Python submodule) stands for the names its module passes on,
    users' `pkg.ns.name`: each member joins the surface at the file that defines it, looked up by its `local` name
    there, with the namespace's entry; a member another public name has (same name and file) is listed once, one
    defined out of scope stays out with its outside_scope row, and a namespace the runner could not read stays."""
    extraction = json.loads(json.dumps(EXTRACTION))
    extraction["exports"].append({"export_name": "realFmt", "export_type": "function", "source_file": "src/ns/fmt.ts",
                                  "source_line": 2, "signature_line": "export function realFmt(): string {"})
    extraction["entry_point_diff"]["public"] += [
        {"name": "ns", "entry": "src/index.ts", "via": "namespace", "file": "src/ns/index.ts", "line": None,
         "members": [{"name": "fmt", "local": "realFmt", "file": "src/ns/fmt.ts", "line": 2},
                     {"name": "helper", "local": None, "file": "src/helper.ts", "line": 1},
                     {"name": "old", "local": None, "file": "lib/old.ts", "line": 9}]},
        {"name": "remote", "entry": "src/index.ts", "via": "namespace", "file": None, "line": None, "members": None}]
    extraction["entry_point_diff"]["outside_scope"].append(
        {"name": "old", "language": "javascript", "entry": "src/index.ts", "file": "lib/old.ts", "line": 9})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", extraction))
    assert out["sets"]["all"] == ["Extra", "Level", "Mode", "Options", "fetchData", "fmt", "gapFn", "helper", "remote"]
    assert out["sets"]["root"] == ["Mode", "Options", "fetchData", "fmt", "gapFn", "helper", "legacy", "old", "remote"]
    fmt = [e for e in out["exports"] if e["name"] == "fmt"]
    assert [(e["kind"], e["file"], e["line"], e["signatureLine"]) for e in fmt] == [
        ("function", "src/ns/fmt.ts", 2, "export function realFmt(): string {")]
    assert [e["file"] for e in out["exports"] if e["name"] == "helper"] == ["src/helper.ts"]
    assert {"name": "old", "file": "lib/old.ts", "line": 9, "entry": "src/index.ts", "excludeGlob": None,
            "outsideInclude": True} in out["excluded"]["outsideScope"]
    # the umbrella ratio counts the members too, each a re-export: the root's six names (gapFn, helper and legacy
    # re-exported) plus fmt and old, and remote, a namespace the runner could not read
    umbrella = out["guards"]["umbrella"]
    assert (umbrella["names"], umbrella["reexported"]) == (9, 6)


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_namespace_feeds_its_members(tmp_path):
    """The #703 fixture through the runner: the surface is foo and sub's baz, never the module sub."""
    source = tmp_path / "src"
    for rel, text in (("pkg/__init__.py", "from .a import foo\nfrom . import sub\n"),
                      ("pkg/a.py", "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"),
                      ("pkg/sub.py", "def baz():\n    return 4\n")):
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--scope-type", "public-api", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert out["sets"]["all"] == ["baz", "foo"]
    assert {e["name"]: (e["kind"], e["file"], e["line"]) for e in out["exports"]} == {
        "baz": ("function", "pkg/sub.py", 1), "foo": ("function", "pkg/a.py", 1)}


def test_an_aliased_reexport_takes_the_kind_of_its_definition(tmp_path):
    """`export { Settings as Config } from './impl'`: the extractor records the
    export under the name impl.ts gives it, `local`."""
    data = json.loads(json.dumps(EXTRACTION))
    data["exports"].append({"export_name": "Settings", "export_type": "interface", "source_file": "src/impl.ts",
                            "source_line": 3, "signature_line": "export interface Settings {"})
    data["entry_point_diff"]["public"].append({"name": "Config", "entry": "src/index.ts", "via": "re-export",
                                               "local": "Settings", "file": "src/impl.ts", "line": 3})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", data))
    config = next(e for e in out["exports"] if e["name"] == "Config")
    assert (config["kind"], config["line"], config["signatureLine"]) == (
        "interface", 3, "export interface Settings {")


def test_a_local_list_item_is_planned_at_its_declaration(tmp_path):
    """#836: an item of a local `export { ... }` list gives the surface the line and signature line of the
    declaration the extractor records for it, both from that one pair; a record without them (or with no line
    in it) gives the list's, as before, and no other record moves."""
    data = json.loads(json.dumps(EXTRACTION))
    data["exports"].append({"export_name": "NativeButton", "export_type": "function", "source_file": "src/native.tsx",
                            "source_line": 40, "signature_line": "export { NativeButton, nativeVariants }",
                            "declaration_line": 15, "declaration_signature_line": "const NativeButton = ({"})
    data["entry_point_diff"]["public"].append({"name": "NativeButton", "entry": "src/index.ts", "via": "re-export",
                                               "file": "src/native.tsx", "line": 40})
    plain = json.loads(json.dumps(data))
    del plain["exports"][-1]["declaration_line"], plain["exports"][-1]["declaration_signature_line"]
    unset = json.loads(json.dumps(data))
    unset["exports"][-1]["declaration_line"] = None
    surfaces = {key: _surface(tmp_path / key, "--extraction", _write(tmp_path / key / "e.json", extraction))
                for key, extraction in (("declared", data), ("plain", plain), ("unset", unset))}

    def button(key: str) -> tuple:
        (record,) = [e for e in surfaces[key]["exports"] if e["name"] == "NativeButton"]
        return record["kind"], record["file"], record["line"], record["signatureLine"]

    assert button("declared") == ("function", "src/native.tsx", 15, "const NativeButton = ({")
    assert button("plain") == button("unset") == (
        "function", "src/native.tsx", 40, "export { NativeButton, nativeVariants }")
    others = {key: [e for e in out["exports"] if e["name"] != "NativeButton"] for key, out in surfaces.items()}
    assert others["declared"] == others["plain"] == others["unset"]
    rest = {key: {k: v for k, v in out.items() if k not in ("inputs", "exports")} for key, out in surfaces.items()}
    assert rest["declared"] == rest["plain"] == rest["unset"]


# #830: the runner's storybook shape. Core's `./preview-api` subpath re-exports its composeStories by name (the
# public row); react's root entry point passes react's own on through `export *` (an other definition, in scope
# too) beside StoryObj. This is skf-extract-public-api.py's output for the STORYBOOK_TREE below, trimmed.
CORE_INDEX = "code/core/src/preview-api/index.ts"
CORE_PORTABLE = "code/core/src/preview-api/portable.ts"
REACT_INDEX = "code/renderers/react/src/index.ts"
REACT_PORTABLE = "code/renderers/react/src/portable.ts"
CORE_SIG = "export function composeStories(csfExports: CoreExports, annotations?: CoreAnnotations) {"
REACT_SIG = "export function composeStories(csfExports: ReactExports, annotations?: ReactAnnotations) {"
STORYBOOK_TREE = {
    "code/core/package.json": '{"name": "@sb/core", "exports": {"./preview-api": "./src/preview-api/index.ts"}}\n',
    CORE_INDEX: "export { composeStories } from './portable';\n",
    CORE_PORTABLE: CORE_SIG + "\n  return csfExports;\n}\n",
    "code/renderers/react/package.json": '{"name": "@sb/react", "exports": {".": "./src/index.ts"}}\n',
    REACT_INDEX: "export * from './portable';\nexport type StoryObj = { args: object };\n",
    REACT_PORTABLE: REACT_SIG + "\n  return csfExports;\n}\n",
}
STORYBOOK = {
    "mode": "full", "status": "ok", "files_in_scope": 4, "truncated": False, "files_without_recipes": {},
    "file_issues": [], "errors": [],
    "scope": {"include": ["code/core/**", "code/renderers/react/**"], "exclude": [],
              "tier_a_include": ["code/renderers/react/src/**"], "type": None, "languages": ["typescript"],
              "files_from": None, "unmatched_include": [], "unmatched_tier_a_include": []},
    "exports": [
        {"export_name": "composeStories", "export_type": "re-export", "source_file": CORE_INDEX, "source_line": 1,
         "signature_line": "export { composeStories } from './portable';"},
        {"export_name": "composeStories", "export_type": "function", "source_file": CORE_PORTABLE, "source_line": 1,
         "signature_line": CORE_SIG},
        {"export_name": "StoryObj", "export_type": "type", "source_file": REACT_INDEX, "source_line": 2,
         "signature_line": "export type StoryObj = { args: object };"},
        {"export_name": "composeStories", "export_type": "function", "source_file": REACT_PORTABLE,
         "source_line": 1, "signature_line": REACT_SIG},
    ],
    "entry_points": {
        "status": "barrel",
        "files": [{"language": "typescript", "file": CORE_INDEX, "package": "code/core", "subpath": "./preview-api",
                   "resolution": "file", "in_scope": True},
                  {"language": "typescript", "file": REACT_INDEX, "package": "code/renderers/react", "subpath": ".",
                   "resolution": "file", "in_scope": True}],
        "exports_maps": [], "unresolved": [],
    },
    "entry_point_diff": {
        "public": [{"name": "StoryObj", "entry": REACT_INDEX, "via": "declaration", "from": None, "local": None,
                    "file": REACT_INDEX, "line": 2, "language": "javascript"},
                   {"name": "composeStories", "entry": CORE_INDEX, "via": "re-export", "from": "./portable",
                    "local": None, "file": CORE_PORTABLE, "line": 1, "language": "javascript"}],
        "other_definitions": [{"name": "composeStories", "entry": REACT_INDEX, "via": "star", "from": "./portable",
                               "local": None, "file": REACT_PORTABLE, "line": 1, "language": "javascript"}],
        "internal": [], "extraction_gaps": [], "outside_scope": [],
    },
    "counts": {"exports_public_api": 2, "exports_internal": 0, "effective_denominator": 2,
               "effective_denominator_basis": "tier_a_include", "denominator_files": 2, "curated_subset": True},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
}


def test_each_in_scope_definition_of_a_name_is_a_surface_record(tmp_path):
    """#830: the runner's other definition of composeStories is a record of its own, with the kind, line and
    signature line react's file gives it, so the tier A set holds the name through react's file and the root
    set through react's entry point, though its public row is core's; the count matches the runner's."""
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", STORYBOOK))
    assert [(e["name"], e["kind"], e["file"], e["line"], e["signatureLine"]) for e in out["exports"]] == [
        ("StoryObj", "type", REACT_INDEX, 2, "export type StoryObj = { args: object };"),
        ("composeStories", "function", CORE_PORTABLE, 1, CORE_SIG),
        ("composeStories", "function", REACT_PORTABLE, 1, REACT_SIG)]
    assert out["sets"] == {"all": ["StoryObj", "composeStories"], "root": ["StoryObj", "composeStories"],
                           "subpaths": ["composeStories"], "scope.include": ["StoryObj", "composeStories"],
                           "tier_a_include": ["StoryObj", "composeStories"]}
    candidates = out["candidates"]
    assert candidates["tierAIncludeUnion"] == candidates["extractorEffectiveDenominator"] == 2
    # the umbrella ratio reads the public rows alone, as on main: react's root barrel gives StoryObj, its own
    assert out["guards"]["umbrella"] == {"entries": [REACT_INDEX], "names": 1, "reexported": 0, "ratio": 0.0,
                                         "umbrella": False}


def test_a_name_reaches_the_subpaths_set_through_an_other_definition(tmp_path):
    """#830 review 2: with react's root entry point holding composeStories and core's `./preview-api` subpath
    giving it only as an other definition, the subpaths set holds the name through that definition."""
    data = json.loads(json.dumps(STORYBOOK))
    data["entry_point_diff"]["public"][1] = {**data["entry_point_diff"]["other_definitions"][0]}
    data["entry_point_diff"]["other_definitions"] = [
        {"name": "composeStories", "entry": CORE_INDEX, "via": "re-export", "from": "./portable", "local": None,
         "file": CORE_PORTABLE, "line": 1, "language": "javascript"}]
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert (out["sets"]["subpaths"], out["sets"]["root"]) == (["composeStories"], ["StoryObj", "composeStories"])
    assert out["candidates"]["subpathUnion"] == 1


def test_an_extraction_with_no_other_definition_gives_the_same_surface(tmp_path):
    """#830: a name defined once has no other definition, and an empty list changes no record, set or guard."""
    data = json.loads(json.dumps(EXTRACTION))
    data["entry_point_diff"]["other_definitions"] = []
    before = _surface(tmp_path / "before", "--extraction", _write(tmp_path / "before" / "e.json", EXTRACTION))
    after = _surface(tmp_path / "after", "--extraction", _write(tmp_path / "after" / "e.json", data))
    assert {k: v for k, v in after.items() if k != "inputs"} == {k: v for k, v in before.items() if k != "inputs"}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_monorepo_name_counts_through_its_other_definition(tmp_path):
    """#830 end to end: the runner over STORYBOOK_TREE, then the surface. The runner's tier A count and the
    surface's tier A set both hold composeStories through react's file, and the surface gives one record per
    file."""
    source = tmp_path / "src"
    for rel, text in STORYBOOK_TREE.items():
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--include", "code/core/**", "--include", "code/renderers/react/**",
                           "--tier-a-include", "code/renderers/react/src/**", "--tier", "Forge", "--head-cap", "0",
                           "--output", str(extraction)], capture_output=True, text=True, timeout=600)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(extraction.read_text(encoding="utf-8"))
    assert data["entry_point_diff"]["other_definitions"] == STORYBOOK["entry_point_diff"]["other_definitions"]
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert [(e["name"], e["file"]) for e in out["exports"]] == [
        ("StoryObj", REACT_INDEX), ("composeStories", CORE_PORTABLE), ("composeStories", REACT_PORTABLE)]
    assert data["counts"]["effective_denominator"] == out["candidates"]["tierAIncludeUnion"] == 2


# #918: cognee's two run_pipeline functions. The root entry point binds `pipelines` to cognee.modules.pipelines, a
# namespace whose members hold the orchestrator in operations/pipeline.py. The lightweight runner in
# operations/run_pipeline.py reaches users only through a lazy `__getattr__` in cognee/pipelines/__init__.py, no
# entry point, so exports[] alone records it. This is skf-extract-public-api.py's output for such a tree, trimmed,
# with a test file's run_pipeline (scope.exclude drops it) and a name no entry point exports.
ORCHESTRATOR = "cognee/modules/pipelines/operations/pipeline.py"
LIGHTWEIGHT = "cognee/modules/pipelines/operations/run_pipeline.py"
RUN_TASKS = "cognee/modules/pipelines/operations/run_tasks.py"
PIPELINES = {
    "mode": "full", "status": "ok", "files_in_scope": 5, "truncated": False, "files_without_recipes": {},
    "file_issues": [], "errors": [],
    "scope": {"include": ["cognee/**"], "exclude": ["cognee/tests/**"], "tier_a_include": None, "type": "public-api",
              "languages": ["python"], "files_from": None, "unmatched_include": [], "unmatched_tier_a_include": []},
    "exports": [
        {"export_name": "run_pipeline", "export_type": "function", "source_file": ORCHESTRATOR, "source_line": 53,
         "signature_line": "async def run_pipeline("},
        {"export_name": "run_tasks", "export_type": "function", "source_file": RUN_TASKS, "source_line": 20,
         "signature_line": "async def run_tasks("},
        {"export_name": "run_pipeline", "export_type": "function", "source_file": LIGHTWEIGHT, "source_line": 37,
         "signature_line": "async def run_pipeline("},
        {"export_name": "run_pipeline", "export_type": "function", "source_file": "cognee/tests/fake.py",
         "source_line": 3, "signature_line": "def run_pipeline():"},
        {"export_name": "run_steps", "export_type": "function", "source_file": LIGHTWEIGHT, "source_line": 90,
         "signature_line": "def run_steps(steps):"},
    ],
    "entry_points": {"status": "barrel", "files": [
        {"language": "python", "file": "cognee/__init__.py", "package": "cognee", "subpath": None,
         "resolution": "file", "in_scope": True}], "exports_maps": [], "unresolved": []},
    "entry_point_diff": {
        "public": [{"name": "pipelines", "entry": "cognee/__init__.py", "via": "namespace", "from": ".modules",
                    "local": None, "file": "cognee/modules/pipelines/__init__.py", "line": None,
                    "language": "python",
                    "members": [{"name": "run_pipeline", "local": None, "file": ORCHESTRATOR, "line": 53},
                                {"name": "run_tasks", "local": None, "file": RUN_TASKS, "line": 20}]}],
        "other_definitions": [], "internal": [], "extraction_gaps": [], "outside_scope": [],
    },
    "counts": {"exports_public_api": 2, "exports_internal": 0, "effective_denominator": 2,
               "effective_denominator_basis": "all", "denominator_files": 2},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
}


def test_a_same_named_declaration_no_entry_point_exports_is_an_other_declaration(tmp_path):
    """#918: the surface records run_pipeline once, at the orchestrator, and lists the lightweight runner exports[]
    holds as an other declaration, with its kind, line and signature line. A declaration in a file scope.exclude
    drops, and a name with no record (run_steps), give none. Records, sets, candidates and guards stay those of
    the same extraction without the other rows."""
    bare = json.loads(json.dumps(PIPELINES))
    bare["exports"] = bare["exports"][:2]
    out = _surface(tmp_path / "full", "--extraction", _write(tmp_path / "full" / "e.json", PIPELINES))
    before = _surface(tmp_path / "bare", "--extraction", _write(tmp_path / "bare" / "e.json", bare))
    assert [(e["name"], e["file"], e["line"]) for e in out["exports"]] == [
        ("run_pipeline", ORCHESTRATOR, 53), ("run_tasks", RUN_TASKS, 20)]
    assert out["otherDeclarations"] == [{"name": "run_pipeline", "kind": "function", "file": LIGHTWEIGHT, "line": 37,
                                         "signatureLine": "async def run_pipeline("}]
    assert before["otherDeclarations"] == []
    drop = ("inputs", "otherDeclarations")
    assert {k: v for k, v in out.items() if k not in drop} == {k: v for k, v in before.items() if k not in drop}
    assert out["sets"]["all"] == ["run_pipeline", "run_tasks"]


def test_an_other_declaration_is_looked_up_as_a_record_is(tmp_path):
    """#918: an aliased record (`export { Settings as Config }`) has as other declarations those of the name its
    defining file gives it, under its own name, and a local `export { ... }` list's item gives the line and
    signature line of the declaration it names (#836). A re-export row declares nothing: index.ts's `helper`
    row is none, nor is core's `export { composeStories }`, and a name whose every declaration is a record (#830)
    has none."""
    data = json.loads(json.dumps(EXTRACTION))
    data["exports"] += [
        {"export_name": "Settings", "export_type": "interface", "source_file": "src/impl.ts", "source_line": 3,
         "signature_line": "export interface Settings {"},
        {"export_name": "Settings", "export_type": "interface", "source_file": "src/legacy/settings.ts",
         "source_line": 20, "signature_line": "export { Settings };", "declaration_line": 8,
         "declaration_signature_line": "interface Settings {"}]
    data["entry_point_diff"]["public"].append({"name": "Config", "entry": "src/index.ts", "via": "re-export",
                                               "local": "Settings", "file": "src/impl.ts", "line": 3})
    out = _surface(tmp_path / "alias", "--extraction", _write(tmp_path / "alias" / "e.json", data))
    assert out["otherDeclarations"] == [{"name": "Config", "kind": "interface", "file": "src/legacy/settings.ts",
                                         "line": 8, "signatureLine": "interface Settings {"}]
    for key, extraction in (("plain", EXTRACTION), ("storybook", STORYBOOK)):
        out = _surface(tmp_path / key, "--extraction", _write(tmp_path / key / "e.json", extraction))
        assert out["otherDeclarations"] == []


def test_an_other_declaration_written_twice_is_listed_once():
    """#918: `b.py` and `./b.py` are one declaration: listed once, its file written without the `./`, and a record
    file written with one still keeps its own declaration out."""
    row = {"exportName": "f", "kind": "function", "line": 3, "signatureLine": "def f():"}
    out = mod.other_declarations([{"name": "f", "file": "./a.py"}],
                                 [{**row, "file": "b.py"}, {**row, "file": "./b.py"}, {**row, "file": "a.py"}], {}, [])
    assert out == [{"name": "f", "kind": "function", "file": "b.py", "line": 3, "signatureLine": "def f():"}]


def test_no_extraction_or_a_replaced_one_leaves_other_declarations_unknown(tmp_path):
    """#918, #1026: other declarations come from a runner extraction alone. A fallback one, which the per-file scan
    replaces, a surface read by eye and a Quick-tier one never look for them, so `otherDeclarations` is null, not
    the [] of an extraction that looked and found none, which the split-body Source reads as no other declaration
    (test_a_same_named_declaration_no_entry_point_exports_is_an_other_declaration keeps the runner's lists)."""
    fallback = {**PIPELINES, "status": "no-ast-grep"}
    out = _surface(tmp_path / "fallback", "--extraction", _write(tmp_path / "fallback" / "e.json", fallback))
    assert out["extraction"]["fallback"]["needed"] and out["otherDeclarations"] is None
    assert _surface(tmp_path / "eye", "--name", "run_pipeline")["otherDeclarations"] is None
    quick = _write(tmp_path / "quick" / "quick-1.json", {"exports": [
        {"name": "run_pipeline", "type": "function", "source_file": ORCHESTRATOR, "defined_in": ORCHESTRATOR}]})
    assert _surface(tmp_path / "quick", "--quick", quick)["otherDeclarations"] is None
    assert ("and [] with none; null with no extraction or with one the per-file scan replaces, which looks for none, "
            "so null means never looked for (#1026).") in " ".join(mod.__doc__.split())


@pytest.mark.parametrize("runner_json", [True, False], ids=["with-the-runner-json", "no-runner-json"])
def test_a_fallback_scan_surface_leaves_other_declarations_unknown(tmp_path, runner_json):
    """#1026 (oms-cognee run_pipeline): the fallback per-file scan reads the orchestrator's and run_tasks' files,
    not the lightweight runner's, and its results name no other declaration. Its surface records run_pipeline at
    the orchestrator's file with no line, and `otherDeclarations` is null, with the runner's no-ast-grep JSON or
    without it, so the split-body Source never settles a pair by that one record as if nothing else declared the
    name; a full extraction of the same tree lists the lightweight runner. A scan that reads the runner's file
    too records run_pipeline twice and still lists nothing."""
    per_file = [_write(tmp_path / f"per-file-{n}.txt", {"file": file, "exports_found": [name],
                                                        "signature_mismatches": []})
                for n, (file, name) in enumerate([(ORCHESTRATOR, "run_pipeline"), (RUN_TASKS, "run_tasks"),
                                                  (LIGHTWEIGHT, "run_pipeline")], 1)]
    runner = (["--extraction", _write(tmp_path / "e.json", {**PIPELINES, "status": "no-ast-grep", "exports": []})]
              if runner_json else [])
    out = _surface(tmp_path / "two", *("--per-file", per_file[0], "--per-file", per_file[1]), "--fallback-scan",
                   *runner)
    assert [(e["name"], e["file"], e["line"]) for e in out["exports"]] == [
        ("run_pipeline", ORCHESTRATOR, None), ("run_tasks", RUN_TASKS, None)]
    assert out["otherDeclarations"] is None
    out = _surface(tmp_path / "three", *(arg for path in per_file for arg in ("--per-file", path)),
                   "--fallback-scan", *runner)
    assert [(e["name"], e["file"]) for e in out["exports"]] == [
        ("run_pipeline", ORCHESTRATOR), ("run_pipeline", LIGHTWEIGHT), ("run_tasks", RUN_TASKS)]
    assert out["otherDeclarations"] is None


@pytest.mark.parametrize("patch, reason", [
    ({"status": "no-ast-grep", "exports": []}, "no ast-grep the runner can run"),
    ({"files_in_scope": 0}, "no file in scope"),
    ({"files_without_recipes": {".java": 12}, "exports": []}, "no recipe reads the files in scope (.java)"),
], ids=["no-ast-grep", "nothing-in-scope", "no-recipe-for-the-language"])
def test_the_fallback_verdict(tmp_path, patch, reason):
    extraction = _write(tmp_path / "extract-full.json", {**EXTRACTION, **patch})
    out = _surface(tmp_path, "--extraction", extraction)
    assert out["extraction"]["fallback"] == {"needed": True, "reason": reason}


@pytest.mark.parametrize("brief_language, meta_language, needed", [
    (None, "java", True), ("Kotlin", "typescript", True), (None, "typescript", False), ("python", None, False),
    (None, None, False),
], ids=["metadata-java", "brief-kotlin-wins", "metadata-typescript", "brief-python", "no-language"])
def test_files_no_recipe_reads_in_the_skills_language_fall_back(tmp_path, brief_language, meta_language, needed):
    """A Java skill whose scope also matches a few JS files still needs the
    per-file scan: the recipes read only the JS files."""
    extraction = _write(tmp_path / "e.json", {**EXTRACTION, "files_without_recipes": {".java": 12}})
    args = ["--extraction", extraction]
    if meta_language:
        args += ["--metadata", _write(tmp_path / "metadata.json", {**METADATA, "language": meta_language})]
    if brief_language:
        args += ["--brief", _write(tmp_path / "skill-brief.yaml", f"name: demo\nlanguage: {brief_language}\n")]
    fallback = _surface(tmp_path, *args)["extraction"]["fallback"]
    assert fallback["needed"] is needed
    if needed:
        assert fallback["reason"] == (f"no recipe reads the skill's language, {brief_language or meta_language} "
                                      "(.java in scope)")


def test_an_incomplete_run_names_the_files_to_read_by_eye(tmp_path):
    patch = {"status": "incomplete",
             "file_issues": [{"file": "src/broken.ts", "issue": "syntax-errors", "count": 2, "line": 9},
                             {"file": "src/style.css", "issue": "no-recipes"}],
             "errors": [{"reason": "ast-grep-timeout", "files": 3, "first_file": "src/huge.ts", "detail": "x"}]}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", {**EXTRACTION, **patch}))
    assert out["extraction"]["readByEye"] == ["src/broken.ts", "src/huge.ts"]
    assert out["extraction"]["fallback"]["needed"] is False


def test_an_incomplete_run_reads_by_eye_every_file_a_failed_call_lists_unread(tmp_path):
    """#722: a failed ast-grep call lists every file of its batch in `unread`, since a call cut while it prints can
    keep some of a file's exports and lose the rest: each of them is read by eye, not only the call's first file."""
    patch = {"status": "incomplete",
             "errors": [{"reason": "ast-grep-error", "files": 3, "first_file": "a.py", "detail": "exit 1: killed",
                         "unread": ["a.py", "b.py", "c.py"]}]}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", {**EXTRACTION, **patch}))
    assert out["extraction"]["readByEye"] == ["a.py", "b.py", "c.py"]


@pytest.mark.parametrize("issue", ["syntax-errors", "not-utf8"])
def test_a_complete_run_names_the_files_it_could_not_parse_to_read_by_eye(tmp_path, issue):
    """#789: the runner keeps status `ok` when a file fails to parse or decode and lists the file in `file_issues`,
    and `readByEye` names it all the same: coverage-check.md keys its read-by-eye pass on a non-empty `readByEye`,
    not on an `incomplete` status, so such a file is read whatever the status."""
    record = {"file": "src/broken.ts", "issue": issue}
    if issue == "syntax-errors":
        record |= {"count": 2, "line": 9}
    patch = {"file_issues": [record, {"file": "src/style.css", "issue": "no-recipes"}]}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", {**EXTRACTION, **patch}))
    assert out["extraction"]["status"] == "ok"
    assert out["extraction"]["readByEye"] == ["src/broken.ts"]
    assert out["extraction"]["unread"] == []
    assert out["extraction"]["fallback"]["needed"] is False


@pytest.mark.parametrize("status", ["ok", "incomplete"])
def test_a_file_no_one_can_open_is_unread_not_read_by_eye(tmp_path, status):
    """#789: a `missing` or `unreadable` file issue names a file the runner could not open, which no one can read by
    eye either: it goes to `extraction.unread`, while a file that failed to parse or decode stays in `readByEye`
    and a `no-recipes` file is in neither list."""
    patch = {"status": status, "file_issues": [
        {"file": "src/gone.ts", "issue": "missing"},
        {"file": "src/locked.ts", "issue": "unreadable"},
        {"file": "src/broken.ts", "issue": "syntax-errors", "count": 1, "line": 3},
        {"file": "src/latin1.ts", "issue": "not-utf8"},
        {"file": "src/style.css", "issue": "no-recipes"},
    ]}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", {**EXTRACTION, **patch}))
    assert out["extraction"]["readByEye"] == ["src/broken.ts", "src/latin1.ts"]
    assert out["extraction"]["unread"] == ["src/gone.ts", "src/locked.ts"]


def test_quick_mode_output_is_not_an_extraction(tmp_path):
    proc = _run("surface", "--extraction", _write(tmp_path / "q.json", {"exports": []}))
    assert proc.returncode == 1 and "--mode full" in proc.stderr


@pytest.mark.parametrize("path, pattern", [
    ("src/index.ts", "src/**"), ("src/a/b/c.ts", "src/**/*.ts"), ("src/index.ts", "src/**/*.ts"),
    ("test_x.py", "**/test_*"), ("a/test_x.py", "**/test_*"), ("src", "src/**"), ("srcx/a.ts", "src/**"),
    ("src/a.ts", "src/?.ts"), ("src/ab.ts", "src/?.ts"), ("src/a/b.ts", "src/*.ts"), ("lib/x.d.ts", "lib/*.d.ts"),
], ids=lambda v: v)
def test_the_glob_rule_is_the_extractors(path, pattern):
    resolver = _load(RESOLVER, "skf_resolve_authoritative_files_glob")
    assert mod.glob_match(path, pattern) == resolver.glob_match(path, pattern)


# --------------------------------------------------------------------------
# surface: a stale brief scope and nested Python tops (#677)
# --------------------------------------------------------------------------


# cognee v1.0.0 under a brief written for v0.5.8: pipelines.py became the
# pipelines/ package, so the brief's `cognee/pipelines.py` glob matches no
# file and the root re-exports run_pipeline and Task from files no glob
# covers; test_helper's file is excluded; the FastAPI routers/__init__.py is
# a top only because cognee/api/v1/ has no __init__.py. The shape is
# skf-extract-public-api.py's output on that tree (test_a_real_cognee_tree).
COGNEE_BRIEF = ("name: cognee\nlanguage: python\nscope:\n  type: public-api\n"
                "  include: ['cognee/__init__.py', 'cognee/pipelines.py', 'cognee/api/**']\n"
                "  exclude: ['cognee/tests/**']\n")
ROUTERS = "cognee/api/v1/routers/__init__.py"
ROUTER_NAMES = ["get_add_router", "get_search_router"]


def _public(name: str, entry: str, module: str, file: str, line: int = 1) -> dict:
    return {"name": name, "entry": entry, "via": "re-export", "from": module, "local": None, "file": file,
            "line": line, "language": "python"}


def _outside(name: str, file: str, line: int = 1, entry: str = "cognee/__init__.py") -> dict:
    return {"name": name, "language": "python", "entry": entry, "file": file, "line": line}


COGNEE = {
    "mode": "full",
    "status": "ok",
    "files_in_scope": 5,
    "truncated": False,
    "files_without_recipes": {},
    "file_issues": [],
    "errors": [],
    "scope": {"include": ["cognee/__init__.py", "cognee/pipelines.py", "cognee/api/**"],
              "exclude": ["cognee/tests/**"], "tier_a_include": None, "type": "public-api",
              "languages": ["python"], "files_from": None, "unmatched_include": ["cognee/pipelines.py"],
              "unmatched_tier_a_include": []},
    "exports": [
        {"export_name": "add", "export_type": "function", "source_file": "cognee/api/v1/add.py", "source_line": 1,
         "signature_line": "def add(data, dataset_name=\"main\"):"},
        {"export_name": "get_add_router", "export_type": "function", "source_file": "cognee/api/v1/routers/add.py",
         "source_line": 1, "signature_line": "def get_add_router():"},
        {"export_name": "get_search_router", "export_type": "function",
         "source_file": "cognee/api/v1/routers/search.py", "source_line": 1,
         "signature_line": "def get_search_router():"},
    ],
    "entry_points": {
        "status": "barrel",
        "files": [
            {"language": "python", "file": "cognee/__init__.py", "package": "cognee", "subpath": None,
             "resolution": "file", "in_scope": True},
            {"language": "python", "file": ROUTERS, "package": "cognee/api/v1/routers", "subpath": None,
             "resolution": "file", "in_scope": True},
        ],
        "exports_maps": [], "unresolved": [],
    },
    "entry_point_diff": {
        "public": [
            _public("Task", "cognee/__init__.py", ".pipelines", "cognee/pipelines/task.py", 2),
            _public("add", "cognee/__init__.py", ".api.v1.add", "cognee/api/v1/add.py"),
            _public("get_add_router", ROUTERS, ".add", "cognee/api/v1/routers/add.py"),
            _public("get_search_router", ROUTERS, ".search", "cognee/api/v1/routers/search.py"),
            _public("run_pipeline", "cognee/__init__.py", ".pipelines", "cognee/pipelines/run.py", 4),
            _public("test_helper", "cognee/__init__.py", ".tests.helper", "cognee/tests/helper.py"),
        ],
        "other_definitions": [],
        "internal": [],
        "extraction_gaps": [],
        "outside_scope": [_outside("Task", "cognee/pipelines/task.py", 2),
                          _outside("run_pipeline", "cognee/pipelines/run.py", 4),
                          _outside("test_helper", "cognee/tests/helper.py")],
    },
    "counts": {"exports_public_api": 6, "exports_internal": 0, "effective_denominator": 3,
               "effective_denominator_basis": "scope.include", "denominator_files": 5},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
    "warnings": ["scope.include pattern 'cognee/pipelines.py' matches no file"],
}
RESTORED = [{"name": "Task", "file": "cognee/pipelines/task.py", "line": 2},
            {"name": "run_pipeline", "file": "cognee/pipelines/run.py", "line": 4}]


def _cognee(tmp_path: Path, patch: dict | None = None, brief: str | None = COGNEE_BRIEF,
            data: dict | None = None) -> dict:
    data = json.loads(json.dumps(data or COGNEE))
    for key, value in (patch or {}).items():
        data["scope"][key] = value
    args = ["--extraction", _write(tmp_path / "extract-full.json", data)]
    if brief is not None:
        args += ["--brief", _write(tmp_path / "skill-brief.yaml", brief)]
    return _surface(tmp_path, *args)


def test_a_stale_glob_restores_the_root_exports_it_dropped(tmp_path):
    """The #677 acceptance: the re-exports come back to `all`, the routers'
    names leave it, and the ledger holds one brief-scope-stale gap."""
    out = _cognee(tmp_path)
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES], "a restored file matches no include glob"
    assert out["sets"]["root"] == ["Task", "add", "run_pipeline", "test_helper"]
    assert out["excluded"]["outsideScope"] == [{"name": "test_helper", "file": "cognee/tests/helper.py", "line": 1,
                                                "entry": "cognee/__init__.py", "excludeGlob": "cognee/tests/**",
                                                "outsideInclude": True}]
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": True,
                                           "unmatchedInclude": ["cognee/pipelines.py"], "unmatchedTierAInclude": [],
                                           "restored": RESTORED}
    # No recipe reads a file out of scope, so a restored name has no kind: it
    # carries the file and line of its outside_scope row.
    restored = [e for e in out["exports"] if e["origin"] == "restored"]
    assert restored == [{"name": "Task", "kind": None, "file": "cognee/pipelines/task.py", "line": 2,
                         "signatureLine": None, "origin": "restored"},
                        {"name": "run_pipeline", "kind": None, "file": "cognee/pipelines/run.py", "line": 4,
                         "signatureLine": None, "origin": "restored"}]
    # The runner's warning text reaches the surface unchanged.
    assert out["warnings"] == ["extract-full.json: scope.include pattern 'cognee/pipelines.py' matches no file"]
    ledger = tmp_path / "test-findings-20261007T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--from", "guards", "--input", str(tmp_path / "surface.json")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    records = json.loads(ledger.read_text(encoding="utf-8"))["records"]
    assert [(r["severity"], r["category"], r["source"]) for r in records] == [
        ("Medium", "brief-scope-stale", str(tmp_path / "skill-brief.yaml"))]
    assert records[0]["issue"] == (
        "the `scope.include` glob `cognee/pipelines.py` matches no file in the source tested; the `all` set "
        "restores 2 root exports, defined in files no include glob covers: `Task` in `cognee/pipelines/task.py`, "
        "`run_pipeline` in `cognee/pipelines/run.py`")


TASK_FILE = "cognee/pipelines/task.py"
# score-signatures.py's warning for the restored names (#913) and extraction gaps (#1020) with no kind, less the
# names.
KINDLESS = ("Type Coverage leaves out each name the stale-scope guard restored or the extraction recorded with no "
            "kind, such as an extraction gap (the provenance map, when one is given, gives it no kind Type Coverage "
            "reads at its file): ")


def _restored_surface(folder: Path, entries: list[dict]) -> dict:
    """The cognee surface, whose stale include glob restores `Task` and
    `run_pipeline`, read with a provenance map of `entries`."""
    return _surface(folder, "--extraction", _write(folder / "extract-full.json", COGNEE),
                    "--brief", _write(folder / "skill-brief.yaml", COGNEE_BRIEF),
                    "--provenance", _write(folder / "provenance-map.json", {"entries": entries}))


@pytest.mark.parametrize(("task_entries", "kind"), [
    ([("dataclass", TASK_FILE)], "class"),
    ([("NamedTuple", TASK_FILE)], "class"),
    ([("Protocol", TASK_FILE)], "interface"),
    ([("type_alias", TASK_FILE)], "type"),
    ([("enum", TASK_FILE)], "enum"),
    ([("TypeVar", TASK_FILE)], "const"),
    ([("constant", TASK_FILE)], "const"),
    ([("function", TASK_FILE)], "function"),
    ([("async_function", TASK_FILE)], "function"),
    ([("decorator", TASK_FILE)], "function"),
    ([("component", TASK_FILE)], "function"),
    ([("class", TASK_FILE)], "class"),
    ([("interface", TASK_FILE)], "interface"),
    ([("type", TASK_FILE)], "type"),
    ([("const", TASK_FILE)], "const"),
    ([("TypedDict", TASK_FILE)], "class"),
    ([("decorator_namespace", TASK_FILE)], None),
    ([("dataclass", "cognee/task.py")], None),
    ([("dataclass", f"./{TASK_FILE}")], "class"),
    ([("decorator_namespace", TASK_FILE), ("dataclass", "cognee/task.py"), ("Protocol", TASK_FILE),
      ("enum", TASK_FILE)], "interface"),
], ids=["dataclass", "namedtuple", "protocol", "type-alias", "enum", "typevar", "constant", "function",
        "async-function", "decorator", "component",
        "class", "interface", "type", "const", "typeddict", "decorator-namespace", "another-file", "dot-slash-path",
        "first-known-kind"])
def test_a_restored_name_takes_its_kind_from_the_provenance_map(tmp_path, task_entries, kind):
    """#913: no recipe reads a restored name's file, so the name takes the
    kind the provenance map gives it at that file, read as Type Coverage's
    kinds (first entry in map order with a known kind); a record the
    extraction gave a kind keeps it. No set, count or guard changes: the
    same map with no export_type gives the same surface but for the
    restored kinds."""
    entries = [{"export_name": "Task", "export_type": t, "source_file": f, "source_line": 2}
               for t, f in task_entries]
    entries.append({"export_name": "add", "export_type": "class", "source_file": "cognee/api/v1/add.py",
                    "source_line": 1})
    out = _restored_surface(tmp_path / "typed", entries)
    restored = {e["name"]: e["kind"] for e in out["exports"] if e["origin"] == "restored"}
    assert restored == {"Task": kind, "run_pipeline": None}, "run_pipeline has no entry"
    assert [e["kind"] for e in out["exports"] if e["name"] == "add"] == ["function"], "the extraction's kind stays"
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES]
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    control = _restored_surface(tmp_path / "untyped", [{**e, "export_type": None} for e in entries])
    assert [e["kind"] for e in control["exports"] if e["origin"] == "restored"] == [None, None]
    assert ({k: v for k, v in out.items() if k not in ("inputs", "exports")}
            == {k: v for k, v in control.items() if k not in ("inputs", "exports")})
    assert [{**e, "kind": None} if e["origin"] == "restored" else e for e in out["exports"]] == control["exports"]


def test_a_restored_type_counts_in_type_coverage(tmp_path):
    """#913 end to end: `score` counts the restored `Task` the map gives a
    type kind (undocumented, so a missing type), and names `run_pipeline`,
    which has no kind, in place of the warning that the surface has no type."""
    _restored_surface(tmp_path, [{"export_name": "Task", "export_type": "dataclass", "source_file": TASK_FILE}])
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "add", "kind": "function", "params": "data, dataset_name", "return_type": "None"},
    ], "cross_check_mismatches": []})
    out = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "score", "--inventory", inventory,
                                     "--surface", str(tmp_path / "surface.json")],
                                    capture_output=True, text=True, check=True).stdout)
    assert (out["documentedTypes"], out["totalTypes"], out["typeCoverage"], out["missingTypes"]) == (
        0, 1, 0.0, ["Task"])
    assert out["warnings"] == [KINDLESS + "`run_pipeline`"]


@pytest.mark.parametrize(("task_type", "run_type", "types", "warnings"), [
    ("dataclass", "async_function", (0, 1, 0.0, ["Task"]), []),
    ("dataclass", "decorator", (0, 1, 0.0, ["Task"]), []),
    ("dataclass", "component", (0, 1, 0.0, ["Task"]), []),
    ("constant", "async_function", (0, 0, 100.0, []),
     ["the source surface has no interface, type alias, enum or class: Type Coverage has nothing to cover "
      "and scores 100"]),
], ids=["async-function", "decorator", "component", "no-types"])
def test_a_restored_function_kind_is_no_possible_type(tmp_path, task_type, run_type, types, warnings):
    """#1032: a restored name the map gives a by-eye function kind
    (`async_function`, `decorator`, a React `component`) is a function, so
    Type Coverage counts the same types and no longer names it as one that
    may be a type; on a surface with no type, the no-types warning shows."""
    surface = _restored_surface(tmp_path, [
        {"export_name": "Task", "export_type": task_type, "source_file": TASK_FILE},
        {"export_name": "run_pipeline", "export_type": run_type, "source_file": "cognee/pipelines/run.py"}])
    assert [e["kind"] for e in surface["exports"] if e["name"] == "run_pipeline"] == ["function"]
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "add", "kind": "function", "params": "data, dataset_name", "return_type": "None"},
    ], "cross_check_mismatches": []})
    out = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "score", "--inventory", inventory,
                                     "--surface", str(tmp_path / "surface.json")],
                                    capture_output=True, text=True, check=True).stdout)
    assert (out["documentedTypes"], out["totalTypes"], out["typeCoverage"], out["missingTypes"]) == types
    assert out["warnings"] == warnings


def _gap_surface(folder: Path, entries: list[dict] | None, task_file: str | None = TASK_FILE) -> dict:
    """The cognee surface once the brief's include glob covers the pipelines
    folder (the oms-cocoindex shape, #1020): no glob is stale and no name is
    restored, and no recipe found `Task` or `run_pipeline`, so both are
    extraction gaps with no kind, read with a provenance map of `entries`
    when given. `task_file` is the file the trace reached for `Task`."""
    data = json.loads(json.dumps(COGNEE))
    data["scope"].update({"include": ["cognee/__init__.py", "cognee/pipelines/**", "cognee/api/**"],
                          "unmatched_include": []})
    data["entry_point_diff"]["public"][0]["file"] = task_file
    data["entry_point_diff"]["extraction_gaps"] = [
        {"name": "Task", "language": "python", "entry": "cognee/__init__.py", "file": task_file,
         "line": 2 if task_file else None},
        {"name": "run_pipeline", "language": "python", "entry": "cognee/__init__.py",
         "file": "cognee/pipelines/run.py", "line": 4}]
    data["entry_point_diff"]["outside_scope"] = [_outside("test_helper", "cognee/tests/helper.py")]
    data["warnings"] = []
    args = ["--extraction", _write(folder / "extract-full.json", data)]
    if entries is not None:
        args += ["--provenance", _write(folder / "provenance-map.json", {"entries": entries})]
    return _surface(folder, *args)


@pytest.mark.parametrize(("task_entries", "task_file", "kind"), [
    ([("type_alias", TASK_FILE)], TASK_FILE, "type"),
    ([("dataclass", TASK_FILE)], TASK_FILE, "class"),
    ([("Protocol", f"./{TASK_FILE}")], TASK_FILE, "interface"),
    ([("function", TASK_FILE)], TASK_FILE, "function"),
    ([("dataclass", "cognee/task.py")], TASK_FILE, None),
    ([("dataclass", TASK_FILE)], None, None),
], ids=["type-alias", "dataclass", "dot-slash-protocol", "function", "another-file", "no-file"])
def test_an_extraction_gap_takes_its_kind_from_the_provenance_map(tmp_path, task_entries, task_file, kind):
    """#1020: an extraction gap is a public name no recipe found, so it has
    no kind from exports[] and takes the one the provenance map gives it at
    its file, as a restored name does; a gap whose trace reached no file
    keeps none, and a record the extraction gave a kind keeps it. No set,
    count or guard changes: the same map with no export_type gives the same
    surface but for the gaps' kinds."""
    entries = [{"export_name": "Task", "export_type": t, "source_file": f, "source_line": 2}
               for t, f in task_entries]
    entries.append({"export_name": "add", "export_type": "class", "source_file": "cognee/api/v1/add.py",
                    "source_line": 1})
    out = _gap_surface(tmp_path / "typed", entries, task_file)
    assert out["guards"]["staleScope"]["restored"] == [] and [e["name"] for e in out["extractionGaps"]] == [
        "Task", "run_pipeline"]
    gaps = {e["name"]: e["kind"] for e in out["exports"] if e["name"] in ("Task", "run_pipeline")}
    assert gaps == {"Task": kind, "run_pipeline": None}, "run_pipeline has no entry"
    assert [e["kind"] for e in out["exports"] if e["name"] == "add"] == ["function"], "the extraction's kind stays"
    control = _gap_surface(tmp_path / "untyped", [{**e, "export_type": None} for e in entries], task_file)
    assert ({k: v for k, v in out.items() if k not in ("inputs", "exports")}
            == {k: v for k, v in control.items() if k not in ("inputs", "exports")})
    assert [{**e, "kind": None} if e["name"] == "Task" else e for e in out["exports"]] == control["exports"]


def test_a_name_found_only_in_another_file_takes_its_kind_from_the_provenance_map(tmp_path):
    """#1020: the map's kind goes to every public name exports[] gives no
    kind at its file, not only to an extraction gap. A recipe found `Task`
    only in another file, so the runner lists no gap for it, and its record
    at the file the trace reached has no kind: it takes the type the map
    gives it there, as What the Surface Holds says."""
    data = json.loads(json.dumps(COGNEE))
    data["scope"].update({"include": ["cognee/__init__.py", "cognee/pipelines/**", "cognee/api/**"],
                          "unmatched_include": []})
    data["exports"].append({"export_name": "Task", "export_type": "function",
                            "source_file": "cognee/pipelines/legacy.py", "source_line": 7,
                            "signature_line": "def Task():"})
    data["entry_point_diff"]["extraction_gaps"] = [
        {"name": "run_pipeline", "language": "python", "entry": "cognee/__init__.py",
         "file": "cognee/pipelines/run.py", "line": 4}]
    data["entry_point_diff"]["outside_scope"] = [_outside("test_helper", "cognee/tests/helper.py")]
    data["warnings"] = []
    entries = [{"export_name": "Task", "export_type": "type_alias", "source_file": TASK_FILE, "source_line": 2}]
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data),
                   "--provenance", _write(tmp_path / "provenance-map.json", {"entries": entries}))
    assert [e["name"] for e in out["extractionGaps"]] == ["run_pipeline"]
    assert [(e["file"], e["kind"], e["origin"]) for e in out["exports"] if e["name"] == "Task"] == [
        (TASK_FILE, "type", "extraction")]


def test_an_extraction_gap_type_counts_in_type_coverage(tmp_path):
    """#1020 end to end: with the brief's globs fixed, the type the map gives
    an extraction gap still counts in Type Coverage (undocumented, so a
    missing type), as it did when the guard restored the name, and the gap
    with no kind is named in place of the warning that the surface has no
    type. With no map, both gaps are named."""
    _gap_surface(tmp_path / "typed", [{"export_name": "Task", "export_type": "type_alias", "source_file": TASK_FILE}])
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "add", "kind": "function", "params": "data, dataset_name", "return_type": "None"},
    ], "cross_check_mismatches": []})

    def score(folder: str) -> dict:
        return json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "score", "--inventory", inventory,
                                          "--surface", str(tmp_path / folder / "surface.json")],
                                         capture_output=True, text=True, check=True).stdout)

    out = score("typed")
    assert (out["documentedTypes"], out["totalTypes"], out["typeCoverage"], out["missingTypes"]) == (
        0, 1, 0.0, ["Task"])
    assert out["warnings"] == [KINDLESS + "`run_pipeline`"]
    _gap_surface(tmp_path / "unmapped", None)
    out = score("unmapped")
    assert (out["totalTypes"], out["typeCoverage"]) == (0, 100.0)
    assert out["warnings"] == [KINDLESS + "`Task`, `run_pipeline`"]


@pytest.mark.parametrize(("tier_a", "expected"), [(["cognee/pipelines/**"], None),
                                                  (["cognee/pipelines/**", "cognee/api/v1/add.py"], ["add"])],
                         ids=["restored-only", "restored-and-in-scope"])
def test_a_tier_a_glob_over_a_restored_file_counts_no_name(tmp_path, tier_a, expected):
    """#725: a restored name is back in `all`, but its file matches no include glob, so no tier A glob counts it."""
    out = _cognee(tmp_path, patch={"tier_a_include": tier_a})
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    assert out["sets"].get("tier_a_include") == expected


def test_a_stale_tier_a_glob_joins_the_stale_scope_gap(tmp_path):
    """#695 end to end: the oms-cognee brief's old trace_context/** tier A glob beside a stale include
    glob is one Medium brief-scope-stale gap that names both, and the other tier A glob gives the set."""
    stale = "cognee/modules/observability/trace_context/**"
    out = _cognee(tmp_path, {"tier_a_include": ["cognee/api/**", stale], "unmatched_tier_a_include": [stale]})
    assert out["sets"]["tier_a_include"] == ["add", *ROUTER_NAMES]
    assert out["guards"]["staleScope"]["unmatchedTierAInclude"] == [stale]
    assert out["guards"]["staleScope"]["restored"] == RESTORED, "the include glob restores as before"
    ledger = tmp_path / "test-findings-20261009T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--from", "guards", "--input", str(tmp_path / "surface.json")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    [record] = json.loads(ledger.read_text(encoding="utf-8"))["records"]
    assert (record["severity"], record["category"], record["title"]) == (
        "Medium", "brief-scope-stale",
        "stale brief scope: scope.include and scope.tier_a_include globs match no source file")
    assert record["issue"].startswith("the `scope.include` glob `cognee/pipelines.py` matches no file")
    assert record["issue"].endswith(
        f"; the `scope.tier_a_include` glob `{stale}` matches no file in the source tested, so it counts no name")


def test_a_nested_python_top_is_no_barrel(tmp_path):
    out = _cognee(tmp_path)
    assert not set(ROUTER_NAMES) & (set(out["sets"]["all"]) | set(out["sets"]["root"]))
    assert out["excluded"]["nestedEntries"] == [{"entry": ROUTERS, "within": "cognee/__init__.py",
                                                 "names": ROUTER_NAMES}]
    # The umbrella ratio counts the root barrel only: its four names, each a re-export.
    umbrella = out["guards"]["umbrella"]
    assert (umbrella["entries"], umbrella["names"], umbrella["reexported"]) == (["cognee/__init__.py"], 4, 4)
    # The records stay, with the kind and line the recipes gave them.
    kept = [(e["name"], e["kind"], e["file"], e["line"], e["origin"]) for e in out["exports"]
            if e["name"] in ROUTER_NAMES]
    assert kept == [("get_add_router", "function", "cognee/api/v1/routers/add.py", 1, "extraction"),
                    ("get_search_router", "function", "cognee/api/v1/routers/search.py", 1, "extraction")]


def test_a_documented_nested_name_keeps_its_signature_check(tmp_path):
    """A nested top's names leave `all`, yet score-signatures.py still plans
    and scores a documented one from its record: its wrong signature is a
    Critical gap, not a warning."""
    _cognee(tmp_path)
    surface = str(tmp_path / "surface.json")
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "add", "kind": "function", "params": "data, dataset_name", "return_type": "None"},
        {"name": "get_add_router", "kind": "function", "params": "", "return_type": "Router"},
    ], "cross_check_mismatches": []})
    plan = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "plan", "--inventory", inventory,
                                      "--surface", surface], capture_output=True, text=True, check=True).stdout)
    assert plan["compared"] == 2
    assert plan["files"][1] == {"file": "cognee/api/v1/routers/add.py", "checks": [
        {"name": "get_add_router", "line": 1, "signatureLine": "def get_add_router():",
         "documented": {"params": "", "return_type": "Router"}}]}
    mismatch = {"name": "get_add_router", "line": 1, "source_sig": "() -> APIRouter",
                "documented_sig": "() -> Router", "issue": "wrong return type"}
    results = _write(tmp_path / "signatures-1.txt", {"file": "cognee/api/v1/routers/add.py",
                                                      "signature_mismatches": [mismatch]})
    out = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "score", "--inventory", inventory,
                                     "--surface", surface, "--results", results],
                                    capture_output=True, text=True, check=True).stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (1, 2, 50.0)
    assert [(g["severity"], g["export"], g["source"]) for g in out["gapRecords"]] == [
        ("Critical", "get_add_router", "cognee/api/v1/routers/add.py:1")]
    # #913: the restored names have no kind without a provenance map, so Type Coverage names them, never
    # claiming the surface has no type.
    assert out["warnings"] == [KINDLESS + "`Task`, `run_pipeline`"]


def test_a_nested_name_has_its_other_declarations(tmp_path):
    """#918: a nested Python top's records leave `all` and `root` but keep their signature checks, so a same-named
    declaration in another file is an other declaration of theirs too, and the name stays out of both sets."""
    data = json.loads(json.dumps(COGNEE))
    data["exports"].append({"export_name": "get_add_router", "export_type": "function",
                            "source_file": "cognee/api/v2/routers/add.py", "source_line": 4,
                            "signature_line": "def get_add_router():"})
    out = _cognee(tmp_path, data=data)
    assert out["otherDeclarations"] == [{"name": "get_add_router", "kind": "function",
                                         "file": "cognee/api/v2/routers/add.py", "line": 4,
                                         "signatureLine": "def get_add_router():"}]
    assert "get_add_router" not in set(out["sets"]["all"]) | set(out["sets"]["root"])


def test_a_nested_top_keeps_its_names_in_the_scope_sets(tmp_path):
    """A specific-modules or stratified brief that scopes the sub-package in
    still counts it: a nested top leaves only `all`, `root` and the umbrella
    ratio, and a glob over its folder does not list its file."""
    out = _cognee(tmp_path, {"tier_a_include": ["cognee/api/v1/routers/**"]})
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES]
    assert out["sets"]["tier_a_include"] == ROUTER_NAMES
    assert (out["candidates"]["scopeIncludeUnion"], out["candidates"]["tierAIncludeUnion"]) == (3, 2)
    assert not set(ROUTER_NAMES) & set(out["sets"]["all"])
    assert [n["entry"] for n in out["excluded"]["nestedEntries"]] == [ROUTERS]


def test_a_nested_top_keeps_its_outside_scope_and_extraction_gap_rows(tmp_path):
    data = json.loads(json.dumps(COGNEE))
    diff = data["entry_point_diff"]
    diff["public"] += [_public("RouterConfig", ROUTERS, "..shared.config", "cognee/shared/config.py", 3),
                       _public("get_admin_router", ROUTERS, ".admin", "cognee/api/v1/routers/admin.py", 5)]
    diff["outside_scope"].append(_outside("RouterConfig", "cognee/shared/config.py", 3, entry=ROUTERS))
    diff["extraction_gaps"].append({"name": "get_admin_router", "language": "python", "entry": ROUTERS,
                                    "file": "cognee/api/v1/routers/admin.py", "line": 5})
    for rows in ("public", "outside_scope"):
        diff[rows].sort(key=lambda row: row["name"])  # the runner's order
    out = _cognee(tmp_path, data=data)
    assert [(o["name"], o["file"], o["line"], o["entry"]) for o in out["excluded"]["outsideScope"]] == [
        ("RouterConfig", "cognee/shared/config.py", 3, ROUTERS), ("test_helper", "cognee/tests/helper.py", 1,
                                                                 "cognee/__init__.py")]
    assert out["guards"]["staleScope"]["restored"] == RESTORED, "a nested top is no root entry point"
    assert out["extractionGaps"] == [{"name": "get_admin_router", "file": "cognee/api/v1/routers/admin.py",
                                      "line": 5}]
    assert out["excluded"]["nestedEntries"][0]["names"] == ["RouterConfig", "get_add_router", "get_admin_router",
                                                            "get_search_router"]
    assert out["sets"]["scope.include"] == ["add", "get_add_router", "get_admin_router", "get_search_router"]
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]


@pytest.mark.parametrize("key", ["include", "tier_a_include"])
def test_a_nested_top_the_brief_names_stays_a_barrel(tmp_path, key):
    scope = json.loads(json.dumps(COGNEE["scope"]))
    out = _cognee(tmp_path, {key: (scope[key] or []) + [ROUTERS]})
    assert set(ROUTER_NAMES) <= set(out["sets"]["all"]) & set(out["sets"]["root"])
    assert out["excluded"]["nestedEntries"] == []


@pytest.mark.parametrize("amendments, restored", [
    ([("cognee/pipelines/**", "skipped", "scope-expansion", None)], []),
    ([("cognee/pipelines/run.py", "demoted-include", "scope-expansion", None)], RESTORED[:1]),
    ([("cognee/pipelines/**", "skipped", "scope-expansion", None),
      ("./cognee/pipelines/**", "promoted", "scope-expansion", None)], RESTORED),
    ([("cognee/pipelines/**", "skipped", "scope-expansion", "headless: no user to prompt")], RESTORED),
    ([("cognee/pipelines/**", "skipped", "auth-doc", None)], RESTORED),
], ids=["skipped", "demoted-include", "latest-wins", "legacy-headless-skip-is-a-deferral", "other-category"])
def test_a_declined_scope_expansion_keeps_its_file_out(tmp_path, amendments, restored):
    lines = "".join(f"    - path: '{path}'\n      action: {action}\n      category: {category}\n"
                    + (f"      reason: '{reason}'\n" if reason else "")
                    for path, action, category, reason in amendments)
    out = _cognee(tmp_path, brief=COGNEE_BRIEF + "  amendments:\n" + lines)
    assert out["guards"]["staleScope"]["restored"] == restored
    kept = {r["name"] for r in RESTORED} - {r["name"] for r in restored}
    assert [o["name"] for o in out["excluded"]["outsideScope"]] == sorted(kept | {"test_helper"})
    assert out["guards"]["staleScope"]["fires"] is True, "the glob is stale whatever the brief declined"


def test_an_excluded_file_stays_outside_scope(tmp_path):
    out = _cognee(tmp_path, {"exclude": ["cognee/tests/**", "cognee/pipelines/task.py"]})
    assert out["guards"]["staleScope"]["restored"] == RESTORED[1:]
    assert [o["name"] for o in out["excluded"]["outsideScope"]] == ["Task", "test_helper"]
    assert "Task" not in out["sets"]["all"]


@pytest.mark.parametrize("file, exclude, why", [
    ("lib/legacy.ts", [], (None, True)),
    ("src/vendor/legacy.ts", ["src/gen/**", "src/vendor/**"], ("src/vendor/**", False)),
    ("lib/vendor/legacy.ts", ["lib/vendor/**"], ("lib/vendor/**", True)),
    # a file the include glob covers and no exclude glob matches, such as one no recipe reads
    ("src/legacy.c", ["src/vendor/**"], (None, False)),
    (None, ["src/vendor/**"], (None, False)),
], ids=["no-include-glob", "an-exclude-glob", "both", "not-the-briefs-doing", "no-file"])
def test_an_outside_scope_row_says_why_the_brief_scopes_its_file_out(tmp_path, file, exclude, why):
    """#796: the first scope.exclude glob that matches the row's file (`excludeGlob`), and whether no
    scope.include glob covers it (`outsideInclude`), so gap-ledger.py blames the brief only when it is the cause."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["exclude"] = exclude
    data["entry_point_diff"]["outside_scope"][0]["file"] = file
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    [row] = out["excluded"]["outsideScope"]
    assert (row["name"], row["file"], row["line"], row["entry"]) == ("legacy", file, 3, "src/index.ts")
    assert (row["excludeGlob"], row["outsideInclude"]) == why


@pytest.mark.parametrize("namespace, kept", [
    ("legacy", True), ("tools", True), (None, False), ("", False), (3, False), ("absent", False),
], ids=["its-own-name", "another-name", "null", "empty", "a-number", "no-key"])
def test_a_namespace_members_row_keeps_its_namespace(tmp_path, namespace, kept):
    """#969: a namespace's member's outside_scope row names the namespace it came through, which
    `excluded.outsideScope` keeps beside why the brief scopes its file out, so gap-ledger.py can tell a member
    named like its namespace from the module a skill documents; anything but a non-empty string gives no key."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["exclude"] = ["lib/**"]
    if namespace != "absent":
        data["entry_point_diff"]["outside_scope"][0]["namespace"] = namespace
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    [row] = out["excluded"]["outsideScope"]
    expected = {"name": "legacy", "file": "lib/legacy.ts", "line": 3, "entry": "src/index.ts",
                "excludeGlob": "lib/**", "outsideInclude": True}
    assert row == (expected | {"namespace": namespace} if kept else expected)


def test_a_stale_glob_restores_root_exports_only(tmp_path):
    """A non-root `exports` subpath is no standard barrel: its outside_scope
    name stays out under a stale glob, while the root entry's comes back."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"].update(include=["src/**", "src/old.ts"], unmatched_include=["src/old.ts"])
    data["entry_point_diff"]["public"].append(
        {"name": "oldExtra", "entry": "src/extra.ts", "via": "re-export", "file": "lib/old-extra.ts", "line": 5})
    data["entry_point_diff"]["outside_scope"].append(
        {"name": "oldExtra", "language": "javascript", "entry": "src/extra.ts", "file": "lib/old-extra.ts",
         "line": 5})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert out["guards"]["staleScope"]["restored"] == [{"name": "legacy", "file": "lib/legacy.ts", "line": 3}]
    assert [(o["name"], o["file"]) for o in out["excluded"]["outsideScope"]] == [("oldExtra", "lib/old-extra.ts")]
    assert "legacy" in out["sets"]["all"] and "oldExtra" not in out["sets"]["all"]


def test_a_fresh_brief_leaves_the_surface_unchanged(tmp_path):
    out = _cognee(tmp_path, {"unmatched_include": []})
    assert out["sets"]["all"] == ["add"]
    assert [o["name"] for o in out["excluded"]["outsideScope"]] == ["Task", "run_pipeline", "test_helper"]
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}
    assert gap_ledger.from_guards(out) == []


def test_without_a_brief_the_recorded_scope_still_decides(tmp_path):
    out = _cognee(tmp_path, brief=None)
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    assert out["inputs"]["brief"] is None


def test_without_an_extraction_the_stale_scope_guard_does_not_apply(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", COGNEE_BRIEF)
    out = _surface(tmp_path, "--name", "add", "--brief", brief)
    assert out["guards"]["staleScope"] == {"applicable": False, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}
    assert out["excluded"] == {"outsideScope": [], "nestedEntries": []}


@pytest.mark.parametrize("tops, silent, nested", [
    (["pkg/__init__.py", "pkg/a/routers/__init__.py"], [], {"pkg/a/routers/__init__.py": "pkg/__init__.py"}),
    (["ns/a/__init__.py", "ns/b/__init__.py"], [], {}),
    (["__init__.py", "sub/x/__init__.py"], [], {"sub/x/__init__.py": "__init__.py"}),
    (["pkg/__init__.py", "pkg/a/x/__init__.py", "pkg/a/x/b/y/__init__.py"], [],
     {"pkg/a/x/__init__.py": "pkg/__init__.py", "pkg/a/x/b/y/__init__.py": "pkg/__init__.py"}),
    (["pkg/__init__.py", "pkgx/a/__init__.py"], [], {}),
    (["pkg/__init__.py", "pkg/a/routers/__init__.py"], ["pkg/__init__.py"], {}),
    (["__init__.py", "pkg/__init__.py", "pkg/a/routers/__init__.py"], ["__init__.py"],
     {"pkg/a/routers/__init__.py": "pkg/__init__.py"}),
], ids=["nested", "siblings", "source-root-top", "outermost-holder", "prefix-is-not-a-folder",
        "outer-exports-nothing", "stray-source-root-init"])
def test_which_python_tops_are_nested(tops, silent, nested):
    """`silent` lists the tops that export no public name: such a top nests no other."""
    entries = [{"language": "python", "file": f, "subpath": None} for f in tops]
    assert mod._nested_tops(entries, set(), set(tops) - set(silent)) == nested


def test_a_stray_source_root_init_leaves_the_barrel_whole(tmp_path):
    """An empty __init__.py at the source root exports nothing, so it nests
    neither cognee/ nor its routers: the root barrel keeps its names, and the
    routers stay nested in cognee/__init__.py."""
    data = json.loads(json.dumps(COGNEE))
    data["entry_points"]["files"].insert(0, {"language": "python", "file": "__init__.py", "package": ".",
                                             "subpath": None, "resolution": "file", "in_scope": True})
    out = _cognee(tmp_path, data=data)
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["root"] == ["Task", "add", "run_pipeline", "test_helper"]
    assert out["excluded"]["nestedEntries"] == [{"entry": ROUTERS, "within": "cognee/__init__.py",
                                                 "names": ROUTER_NAMES}]
    assert out["guards"]["staleScope"]["restored"] == RESTORED


def test_sibling_tops_both_stay_barrels(tmp_path):
    data = {"mode": "full", "status": "ok", "files_in_scope": 2, "exports": [],
            "scope": {"include": ["ns/**"], "exclude": [], "tier_a_include": None, "unmatched_include": []},
            "entry_points": {"files": [
                {"language": "python", "file": "ns/a/__init__.py", "package": "ns/a", "subpath": None},
                {"language": "python", "file": "ns/b/__init__.py", "package": "ns/b", "subpath": None}]},
            "entry_point_diff": {"public": [
                {"name": "alpha", "entry": "ns/a/__init__.py", "via": "declaration", "file": "ns/a/__init__.py",
                 "line": 1},
                {"name": "beta", "entry": "ns/b/__init__.py", "via": "declaration", "file": "ns/b/__init__.py",
                 "line": 1}], "outside_scope": [], "extraction_gaps": []}}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", data))
    assert out["sets"]["all"] == out["sets"]["root"] == ["alpha", "beta"]
    assert out["excluded"]["nestedEntries"] == []


def test_a_ts_entry_inside_the_root_entrys_folder_stays_a_barrel(tmp_path):
    """Only a Python top can be nested: a TypeScript entry point is a barrel
    wherever its folder lies."""
    data = {"mode": "full", "status": "ok", "files_in_scope": 2, "exports": [],
            "scope": {"include": ["pkg/**"], "exclude": [], "tier_a_include": None, "unmatched_include": []},
            "entry_points": {"files": [
                {"language": "python", "file": "pkg/__init__.py", "package": "pkg", "subpath": None},
                {"language": "typescript", "file": "pkg/ui/index.ts", "package": "pkg/ui", "subpath": "."}]},
            "entry_point_diff": {"public": [
                {"name": "alpha", "entry": "pkg/__init__.py", "via": "declaration", "file": "pkg/__init__.py",
                 "line": 1},
                {"name": "Widget", "entry": "pkg/ui/index.ts", "via": "declaration", "file": "pkg/ui/index.ts",
                 "line": 2}], "outside_scope": [], "extraction_gaps": []}}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", data))
    assert out["sets"]["all"] == out["sets"]["root"] == ["Widget", "alpha"]
    assert out["excluded"]["nestedEntries"] == []
    entries = [{"language": "typescript", "file": f, "subpath": "."} for f in ("src/index.ts", "src/sub/index.ts")]
    assert mod._nested_tops(entries, set(), {"src/index.ts", "src/sub/index.ts"}) == {}


# --------------------------------------------------------------------------
# surface: the other sources
# --------------------------------------------------------------------------


def test_quick_output_and_names_read_by_eye(tmp_path):
    quick = _write(tmp_path / "quick-1.json", {"exports": [{"name": "fetchData", "type": "function",
                                                            "source_file": "src/index.ts"}],
                                               "warnings": ["src/index.ts:3: export * from './x'"]})
    out = _surface(tmp_path, "--quick", quick, "--name", "fromStar")
    assert out["sets"]["all"] == ["fetchData", "fromStar"]
    assert out["warnings"] == ["quick-1.json: src/index.ts:3: export * from './x'"]
    assert {e["origin"] for e in out["exports"]} == {"quick", "by-eye"}
    assert out["candidates"] is None and out["guards"] is None


def test_per_file_results_are_schema_checked(tmp_path):
    good = _write(tmp_path / "per-file-1.txt", "```json\n" + json.dumps({
        "file": "src/a.ts", "exports_found": ["a", "B"], "types_found": ["B"], "signature_mismatches": []}) + "\n```\n")
    out = _surface(tmp_path, "--per-file", good)
    assert out["sets"]["all"] == ["B", "a"]
    assert {e["name"]: e["kind"] for e in out["exports"]} == {"B": "type", "a": None}
    bad = _write(tmp_path / "per-file-2.txt", json.dumps({"file": "src/b.ts", "exports_found": "a"}))
    stale = tmp_path / "stale-surface.json"
    stale.write_bytes(b"{}")
    proc = _run("surface", "--per-file", good, "--per-file", bad, "--output", str(stale))
    # The breach exits 2 with the violations, as score-signatures.py does, so
    # the subagent can be re-dispatched with them.
    assert proc.returncode == 2, proc.stderr
    out = json.loads(proc.stdout)
    assert out["valid"] is False
    assert any(v.startswith("per-file-2.txt") and "signature_mismatches" in v for v in out["violations"])
    assert not stale.exists(), "a refused surface leaves no file for the next command to read"


# A curated brief at Quick tier: two packages of a monorepo, read by the
# quick parser; the brief scopes in core and api and names core's entry as
# its tier A surface.
BRIEF = ("name: demo\nlanguage: typescript\nscope:\n  type: specific-modules\n"
         "  include: ['packages/core/**', 'packages/api/**']\n  exclude: ['packages/api/internal/**']\n")


def _quick_monorepo(tmp_path: Path) -> list[str]:
    core = _write(tmp_path / "quick-1.json", {"exports": [
        {"name": n, "type": "function", "source_file": "packages/core/src/index.ts"}
        for n in ("connect", "query", "close")]})
    api = _write(tmp_path / "quick-2.json", {"exports": [
        {"name": "serve", "type": "function", "source_file": "packages/api/src/index.ts"},
        {"name": "route", "type": "function", "source_file": "packages/api/internal/router.ts"}]})
    cli = _write(tmp_path / "quick-3.json", {"exports": [
        {"name": "main", "type": "function", "source_file": "packages/cli/src/index.ts"}]})
    return ["--quick", core, "--quick", api, "--quick", cli]


def test_a_quick_tier_tier_a_glob_that_counts_no_name_gives_no_set(tmp_path):
    """#712: no empty tier_a_include set at Quick tier either; with no runner JSON the brief's glob still
    keeps the guards off (a quick name carries its entry file, not the file that defines it)."""
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF + "  tier_a_include: ['packages/core/src/util/**']\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 2}})
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "x"}]})
    out = _surface(tmp_path, *_quick_monorepo(tmp_path), "--brief", brief, "--metadata", meta, "--provenance", prov)
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 2,
                                          "rederived": 4, "pct": 100.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False
    assert out["guards"]["tierAInclude"] == ["packages/core/src/util/**"]


# #733: the issue's fixture, `src/**` in scope. At Quick tier the loader
# keeps this glob rule whether or not the quick names carry defined_in: a
# name read by eye, or a quick name with no defined_in, carries the entry
# file that exports it, so only a tier A glob whose folder or file differs
# from every scope.include glob's before any wildcard, or one a
# scope.exclude glob covers segment by segment (#749), is known to count no
# name.
FX_BRIEF = "name: fx\nlanguage: typescript\nscope:\n  type: specific-modules\n  include: ['src/**']\n"
FX_PROVENANCE = {"entries": [{"export_name": n} for n in ("alpha", "beta", "gamma")]}


def _fx(tmp_path: Path, tier_a: str, stored: int, head: str = FX_BRIEF) -> list[str]:
    brief = _write(tmp_path / "skill-brief.yaml", head + f"  tier_a_include: ['{tier_a}']\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": stored}})
    prov = _write(tmp_path / "provenance.json", FX_PROVENANCE)
    return ["--brief", brief, "--metadata", meta, "--provenance", prov]


def _fx_quick(tmp_path: Path) -> list[str]:
    return ["--quick", _write(tmp_path / "quick-1.json", {"exports": [
        {"name": n, "type": "function", "source_file": "src/index.ts"} for n in ("alpha", "beta", "gamma")]})]



def _fx_names(tmp_path: Path, source: str) -> list[str]:
    """The three names of src/index.ts, read as `source` gives them."""
    names = ("alpha", "beta", "gamma")
    if source.startswith("quick"):
        traced = {"defined_in": "src/index.ts"} if source == "quick-traced" else {}
        return ["--quick", _write(tmp_path / "quick-1.json", {"exports": [
            {"name": n, "type": "function", "source_file": "src/index.ts", **traced} for n in names]})]
    per_file = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": list(names),
                                                     "signature_mismatches": []})
    return ["--per-file", per_file] + (["--fallback-scan"] if source == "fallback-scan" else [])


@pytest.mark.parametrize(("source", "counted"), [
    ("quick-traced", True), ("fallback-scan", True), ("quick", False), ("per-file", False)])
def test_the_scalar_branch_counts_its_set_only_from_names_at_their_defining_files(tmp_path, source, counted):
    """#791, #792: the scalar branch counts its scope set as the numerator's set only when each name sits at the
    file that defines it, the tier A basis's rule (quick output whose every name carries its defined_in, the
    fallback scan); a name read by eye (State 4) or a quick name with no defined_in sits at its entry file, and
    the branch keeps its looked-up numerator."""
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 3}})
    out = _surface(tmp_path, *_fx_names(tmp_path, source), "--brief", _write(tmp_path / "skill-brief.yaml", FX_BRIEF),
                   "--metadata", meta)
    assert out["sets"]["scope.include"] == ["alpha", "beta", "gamma"]
    assert out["denominator"] == {"clause": "specific-modules", "branch": "scalar", "surfaceSet": "scope.include",
                                  "ladderStep": 1, "absentSet": None, "rebuild": None,
                                  "barrel": out["denominator"]["barrel"], "setCounted": counted}


def test_the_scalar_branch_counts_no_set_from_a_truncated_extraction_or_over_all(tmp_path):
    """#791, #792: a truncated extraction can miss names, and `all` is the whole surface, not a scope set."""
    truncated = _extraction("specific-modules")
    truncated["truncated"] = True
    assert _clause(tmp_path, truncated, STORED) == _scalar("specific-modules", "scope.include", counted=False)
    over_all = _extraction("specific-modules")
    over_all["scope"]["include"] = []
    assert _clause(tmp_path, over_all, STORED) == _scalar("specific-modules", "all", counted=False)

@pytest.mark.parametrize(("tier_a", "include", "apart"), [
    ("gen/**", "src/**", True),
    ("packages/core/src/util/**", "packages/api/**", True),
    ("src/a.ts", "src/b.ts", True),
    ("src/*.ts", "lib/**", True),
    ("packages/core/src/util/**", "packages/core/**", False),
    ("src/b.ts", "src/**", False),
    ("**/gen/**", "src/**", False),
    ("s?c/gen/**", "src/**", False),
    ("src", "src/index.ts", False),
])
def test_two_globs_are_apart_when_a_literal_segment_differs_before_any_wildcard(tier_a, include, apart):
    """#733: two globs are apart when a literal segment differs before either has a `*` or `?`; any other
    pair counts as overlapping, even one no file can match both of (`src` beside `src/index.ts`), so the
    rule never drops a tier A glob that can count a name."""
    assert mod._apart(tier_a, include) is apart
    assert mod._apart(include, tier_a) is apart


@pytest.mark.parametrize(("tier_a", "exclude", "inside"), [
    ("src/gen/**", "src/gen/**", True),
    ("src/gen/extra.ts", "src/gen/**", True),
    ("src/gen/*.ts", "src/gen/**", True),
    ("src/b.ts", "src/b.ts", True),
    ("src/gen/**", "src/**", True),
    ("src/gen/**", "**/gen/**", True),
    ("src/gen/x.ts", "src/*/x.ts", True),
    ("src/gen", "src/gen/**", False),
    ("src/**", "src/gen/**", False),
    ("src/*/x.ts", "src/gen/**", False),
    ("src/g?n/**", "src/gen/**", False),
    ("src/gen/**", "src/gen/*", False),
    ("src/gen/x.ts", "src/gen/y.ts", False),
    ("gen/**", "**/gen/**", False),
])
def test_a_tier_a_glob_is_inside_an_exclude_glob_that_covers_it_segment_by_segment(tier_a, exclude, inside):
    """#749: a tier A glob is inside an exclude glob when, segment by segment, each of the exclude's is
    `**`, the same, or `*` beside one that is not `**`, with no segment of the tier A glob left over unless
    the exclude ends in `**`; any other pair counts as not inside, even one the exclude does cover (`gen/**`
    in `**/gen/**`), so the rule never drops a tier A glob that can count a name."""
    assert mod._inside(tier_a, exclude) is inside


def test_a_glob_inside_another_matches_no_path_the_other_misses():
    """#749: every pair `_inside` holds for, over globs of one to three segments, leaves no sampled path of
    one to four segments the tier A glob matches outside the exclude glob, by the extractor's own glob rule."""
    segments = ["src", "gen", "x.ts", "*", "**", "*.ts", "g?n"]
    globs = ["/".join(p) for n in (1, 2, 3) for p in itertools.product(segments, repeat=n)]
    names = ["src", "gen", "x.ts", "a"]
    paths = ["/".join(p) for n in (1, 2, 3, 4) for p in itertools.product(names, repeat=n)]
    for tier_a in globs:
        matched = [p for p in paths if mod.glob_match(p, tier_a)]
        for exclude in globs:
            if mod._inside(tier_a, exclude):
                assert all(mod.glob_match(p, exclude) for p in matched), (tier_a, exclude)


def test_a_quick_tier_tier_a_glob_outside_scope_include_runs_the_guards(tmp_path):
    """#733: `gen/**` beside `src/**` counts no name whatever the tree holds, so at Quick tier too it leaves
    the tier A list and both guards run; a glob inside `src/**` still keeps them off (#712)."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, "gen/**", 1))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                          "rederived": 3, "pct": 200.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert out["guards"]["tierAInclude"] == ["gen/**"], "the gap still names the brief's glob"
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"]) == ("Medium", "metadata-drift")
    assert drift["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, "src/b.ts", 2))
    assert "tier_a_include" not in out["sets"], "no quick name carries src/b.ts"
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 2,
                                          "rederived": 3, "pct": 50.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


@pytest.mark.parametrize(("head", "basis"), [
    ("name: fx\nlanguage: typescript\nscope:\n  type: specific-modules\n  include: ['src/**', 'gen/**']\n",
     "scope.include"),
    ("name: fx\nlanguage: typescript\nscope:\n  type: specific-modules\n", "all"),
], ids=["an-include-glob-over-gen", "no-scope-include"])
def test_a_quick_tier_tier_a_glob_not_apart_from_every_include_glob_keeps_the_guards_off(tmp_path, head, basis):
    """#733: `gen/**` leaves the list only when it is apart from every scope.include glob: beside a `gen/**`
    include, or with no scope.include at all, it stays, so at Quick tier the guards stay off (#712). With no
    scope.include set the guard measures the `all` set, and says so."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, "gen/**", 1, head))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": basis, "effectiveDenominator": 1,
                                          "rederived": 3, "pct": 200.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


# #749: an exclude that covers a tier A glob segment by segment leaves no file
# that glob can match, so at Quick tier too it counts no name.
FX_EXCLUDE = FX_BRIEF + "  exclude: ['src/gen/**']\n"


@pytest.mark.parametrize("tier_a", ["src/gen/**", "src/gen/extra.ts"])
def test_a_quick_tier_tier_a_glob_inside_a_scope_exclude_glob_runs_the_guards(tmp_path, tier_a):
    """#749: a tier A glob a scope.exclude glob covers counts no name whatever the tree holds, so at Quick tier
    it leaves the tier A list and both guards run, as at Forge tier."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, tier_a, 1, FX_EXCLUDE))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                          "rederived": 3, "pct": 200.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert out["guards"]["tierAInclude"] == [tier_a], "the gap still names the brief's glob"
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"]) == ("Medium", "metadata-drift")
    assert drift["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")


def _fx_globs(tmp_path: Path, exclude: list[str], tier_a: list[str]) -> list[str]:
    """`_fx` at a stored 1, with a list of scope.exclude globs and a list of tier A globs."""
    brief = _write(tmp_path / "skill-brief.yaml", FX_BRIEF + f"  exclude: {json.dumps(exclude)}\n"
                   f"  tier_a_include: {json.dumps(tier_a)}\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    prov = _write(tmp_path / "provenance.json", FX_PROVENANCE)
    return ["--brief", brief, "--metadata", meta, "--provenance", prov]


@pytest.mark.parametrize(("exclude", "tier_a", "fires"), [
    (["src/vendor/**", "src/gen/**"], ["src/gen/**"], True),
    (["src/gen/**"], ["src/gen/**", "gen/**"], True),
    (["src/gen/**"], ["src/gen/**", "src/b.ts"], False),
], ids=["inside-the-second-exclude-glob", "beside-a-glob-apart-from-scope-include",
        "beside-a-file-the-exclude-leaves"])
def test_a_quick_tier_tier_a_list_runs_the_guards_only_when_each_glob_leaves_it(tmp_path, exclude, tier_a,
                                                                                 fires):
    """#749: any scope.exclude glob can cover a tier A glob, and at Quick tier the guards run only when each
    glob leaves the list, inside an exclude glob or apart from every scope.include glob (#733)."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx_globs(tmp_path, exclude, tier_a))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                          "rederived": 3, "pct": 200.0, "fires": fires}
    assert out["guards"]["inflation"]["applicable"] is fires
    assert out["guards"]["tierAInclude"] == tier_a
    gaps = gap_ledger.from_guards(out)
    assert [(g["severity"], g["category"]) for g in gaps] == ([("Medium", "metadata-drift")] if fires else [])
    assert all(g["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")
               for g in gaps)


@pytest.mark.parametrize(("tier_a", "tier_a_set"), [
    ("src/b.ts", None),
    ("src/**", ["alpha", "beta", "gamma"]),
    ("src/g?n/**", None),
], ids=["a-file-the-exclude-leaves", "the-include-glob", "a-wildcard-segment"])
def test_a_quick_tier_tier_a_glob_an_exclude_glob_does_not_cover_keeps_the_guards_off_without_defined_in(
        tmp_path, tier_a, tier_a_set):
    """#749: a tier A glob that can match a file the exclude leaves stays in the list, so at Quick tier the
    guards stay off (#712). The quick names carry no defined_in, so they sit at their entry file: even the set
    `src/**` gives is no count to measure the stored 1 against (#813), and the guard reads the scope.include
    union."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, tier_a, 1, FX_EXCLUDE))
    assert out["sets"].get("tier_a_include") == tier_a_set
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                          "rederived": 3, "pct": 200.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


def test_a_provenance_surface_with_a_tier_a_glob_that_counts_no_name_gives_no_set(tmp_path):
    """#712: State 2 (and a pattern-reference app's map-only surface) has no empty tier_a_include set, so
    the canonicalized provenance map is the denominator."""
    prov = _write(tmp_path / "provenance.json", {"entries": PROVENANCE["entries"][:3]})
    brief = _write(tmp_path / "skill-brief.yaml", "scope:\n  include: ['src/**']\n  tier_a_include: ['src/old/**']\n")
    out = _surface(tmp_path, "--provenance", prov, "--brief", brief, "--fold")
    assert out["sets"] == {"all": ["fetchData", "helper"], "scope.include": ["fetchData", "helper"]}
    assert out["guards"]["deflation"]["applicable"] is False


def test_a_quick_tier_surface_takes_its_scope_from_the_brief(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF + "  tier_a_include: ['packages/core/**']\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 3}})
    out = _surface(tmp_path, *_quick_monorepo(tmp_path), "--brief", brief, "--metadata", meta)
    # metadata.json is a baseline here: its exports[] add no name.
    assert out["sets"]["all"] == ["close", "connect", "main", "query", "route", "serve"]
    assert out["sets"]["scope.include"] == ["close", "connect", "query", "serve"]
    assert out["sets"]["tier_a_include"] == ["close", "connect", "query"]
    assert "subpaths" not in out["sets"] and "root" not in out["sets"], "an extraction gives those"
    # A quick name sits at its defined_in, else its entry file: core's three at one file, serve at another.
    assert out["candidates"] == {"statsEffectiveDenominator": 3, "tierAIncludeUnion": 3, "scopeIncludeUnion": 4,
                                 "tierAIncludeFiles": 1, "scopeIncludeFiles": 2, "subpathUnion": None,
                                 "subpathEntries": None, "rootBarrel": None, "extractorEffectiveDenominator": None,
                                 "extractorBasis": None}
    assert out["guards"]["deflation"]["applicable"] is True and out["guards"]["deflation"]["fires"] is False
    assert out["guards"]["umbrella"]["umbrella"] is False
    # #695: with no runner JSON nothing says a tier A glob is stale: the brief's globs all count
    assert out["guards"]["staleScope"] == {"applicable": False, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}


def test_the_deflation_guard_fires_at_quick_tier(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 2}})
    out = _surface(tmp_path, *_quick_monorepo(tmp_path), "--brief", brief, "--metadata", meta)
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 2,
                                          "rederived": 4, "pct": 100.0, "fires": True}
    assert out["candidates"]["scopeIncludeUnion"] == 4


def test_per_file_results_carry_their_file_into_the_scope_sets(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    per_file = _write(tmp_path / "per-file-1.json", {"file": "packages/core/src/index.ts",
                                                     "exports_found": ["connect"], "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", per_file, "--name", "unplaced", "--brief", brief)
    assert out["sets"]["all"] == ["connect", "unplaced"]
    assert out["sets"]["scope.include"] == ["connect"], "a name with no file is in `all` only"


def _fx_fallback(tmp_path: Path) -> list[str]:
    """The fallback scan's results for the #733 fixture: each at the file that defines its names."""
    a = _write(tmp_path / "per-file-1.txt", {"file": "src/a.ts", "exports_found": ["alpha"], "types_found": [],
                                              "signature_mismatches": []})
    b = _write(tmp_path / "per-file-2.txt", {"file": "src/b.ts", "exports_found": ["beta", "gamma"],
                                              "types_found": [], "signature_mismatches": []})
    return ["--per-file", a, "--per-file", b]


@pytest.mark.parametrize("tier_a", ["src/gone/**", "src/types.ts", "gen/**"])
def test_a_fallback_scan_tier_a_list_that_counts_no_name_runs_the_guards(tmp_path, tier_a):
    """#733: with no runner JSON, --fallback-scan reads the per-file results as an extraction's records: a
    tier A list that gives no set (stale, over a file that defines no public name, or outside
    scope.include) narrows nothing, and the stale-scope guard still needs the runner's word."""
    out = _surface(tmp_path, *_fx_fallback(tmp_path), "--fallback-scan", *_fx(tmp_path, tier_a, 1))
    assert out["sets"] == {"all": ["alpha", "beta", "gamma"], "scope.include": ["alpha", "beta", "gamma"]}
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                          "rederived": 3, "pct": 200.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert out["guards"]["staleScope"]["applicable"] is False
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"]) == ("Medium", "metadata-drift"), "no brief-scope-stale gap"
    assert drift["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")


def test_a_fallback_scan_live_tier_a_glob_keeps_its_set_and_matches_the_stored_count(tmp_path):
    """#733: a tier A glob over the file that defines two of the names gives a set, so the guards stay off on
    the scope.include union; the deflation guard measures the stored 2 against the set instead (#813)."""
    out = _surface(tmp_path, *_fx_fallback(tmp_path), "--fallback-scan", *_fx(tmp_path, "src/b.ts", 2))
    assert out["sets"]["tier_a_include"] == ["beta", "gamma"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "tier_a_include", "effectiveDenominator": 2,
                                          "rederived": 2, "pct": 0.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


@pytest.mark.parametrize("tier_a", ["src/gone/**", "src/types.ts", "src/b.ts"], ids=["stale", "nameless", "live"])
def test_per_file_results_without_fallback_scan_keep_the_glob_rule(tmp_path, tier_a):
    """#733: Quick tier's by-eye results and State 4's carry the entry file, not the defining one, so with no
    --fallback-scan a tier A glob inside scope.include that gives no set, stale or not, still keeps the
    guards off (#712)."""
    entry = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": ["alpha", "beta", "gamma"],
                                                  "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", entry, *_fx(tmp_path, tier_a, 2))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 2,
                                          "rederived": 3, "pct": 50.0, "fires": False}


def test_per_file_results_without_fallback_scan_drop_a_tier_a_glob_apart_from_scope_include(tmp_path):
    """#733: the glob rule leaves `gen/**` beside `src/**` out of the list for State 4's results too, so with
    no --fallback-scan the guards still run."""
    entry = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": ["alpha", "beta", "gamma"],
                                                  "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", entry, *_fx(tmp_path, "gen/**", 2))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 2,
                                          "rederived": 3, "pct": 50.0, "fires": True}
    assert out["guards"]["inflation"]["applicable"] is True


def test_per_file_results_without_fallback_scan_drop_a_tier_a_glob_inside_a_scope_exclude_glob(tmp_path):
    """#749: State 4's results carry the entry file too, so with no --fallback-scan a tier A glob a
    scope.exclude glob covers leaves the list and the guards run."""
    entry = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": ["alpha", "beta", "gamma"],
                                                  "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", entry, *_fx(tmp_path, "src/gen/**", 2, FX_EXCLUDE))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 2,
                                          "rederived": 3, "pct": 50.0, "fires": True}
    assert out["guards"]["inflation"]["applicable"] is True


# #750: the quick parser's `defined_in` places each name at the file that
# defines it, as the runner's records do, and the fallback scan's barrel
# result leaves out the names it only passes on.
FX_DEFINED_IN = {"alpha": "src/a.ts", "beta": "src/b.ts", "gamma": "src/b.ts", "extra": "gen/extra.ts"}


def _fx_quick_traced(tmp_path: Path, defined_in: dict[str, str | None] | None) -> list[str]:
    exports = [{"name": n, "type": "re-export", "source_file": "src/index.ts"} for n in FX_DEFINED_IN]
    if defined_in is not None:
        exports = [{**e, "defined_in": defined_in[e["name"]]} for e in exports]
    return ["--quick", _write(tmp_path / "quick-1.json", {"exports": exports, "warnings": []})]


def _fx_stored(tmp_path: Path, tier_a: str | None, head: str = FX_BRIEF) -> list[str]:
    brief = _write(tmp_path / "skill-brief.yaml", head + (f"  tier_a_include: ['{tier_a}']\n" if tier_a else ""))
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 3}})
    return ["--brief", brief, "--metadata", meta, "--provenance", _write(tmp_path / "provenance.json", FX_PROVENANCE)]


@pytest.mark.parametrize("tier_a", [None, "gen/**"], ids=["no-tier-a-list", "tier-a-apart"])
def test_a_quick_surface_places_each_name_at_its_defined_in(tmp_path, tier_a):
    """#750: `extra`, which the entry file passes on from gen/extra.ts, leaves the scope.include set, so the
    runner's stored 3 fires neither guard; the `all` set keeps every name."""
    out = _surface(tmp_path, *_fx_quick_traced(tmp_path, FX_DEFINED_IN), *_fx_stored(tmp_path, tier_a))
    assert out["sets"] == {"all": ["alpha", "beta", "extra", "gamma"], "scope.include": ["alpha", "beta", "gamma"]}
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 3,
                                          "rederived": 3, "pct": 0.0, "fires": False}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert gap_ledger.from_guards(out) == []


@pytest.mark.parametrize("tier_a", [None, "src/gen/**"], ids=["exclude-only", "tier-a-inside-exclude"])
def test_a_quick_surface_leaves_out_a_name_defined_in_an_excluded_file(tmp_path, tier_a):
    """#750 with #749: `extra`, which the entry file passes on from src/gen/extra.ts, keeps that file, which
    scope.exclude drops, so it leaves the scope.include set and the stored 3 fires neither guard, with no tier A
    list or with a tier A glob inside the exclude (which leaves the list)."""
    traced = {**FX_DEFINED_IN, "extra": "src/gen/extra.ts"}
    out = _surface(tmp_path, *_fx_quick_traced(tmp_path, traced), *_fx_stored(tmp_path, tier_a, FX_EXCLUDE))
    assert [e["file"] for e in out["exports"] if e["name"] == "extra"] == ["src/gen/extra.ts"]
    assert out["sets"] == {"all": ["alpha", "beta", "extra", "gamma"], "scope.include": ["alpha", "beta", "gamma"]}
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 3,
                                          "rederived": 3, "pct": 0.0, "fires": False}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    if tier_a:
        assert out["guards"]["tierAInclude"] == [tier_a]
    assert gap_ledger.from_guards(out) == []


def test_a_quick_surface_with_no_defined_in_keeps_the_entry_file(tmp_path):
    """#750: an older quick output (no key) and a name the parser could not trace (null) carry their
    source_file, as before."""
    without = _surface(tmp_path, *_fx_quick_traced(tmp_path, None), *_fx_stored(tmp_path, None))
    assert without["sets"]["scope.include"] == ["alpha", "beta", "extra", "gamma"]
    assert without["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 3,
                                              "rederived": 4, "pct": 33.33, "fires": True}
    null = _surface(tmp_path, *_fx_quick_traced(tmp_path, dict.fromkeys(FX_DEFINED_IN)), *_fx_stored(tmp_path, None))
    assert {k: null[k] for k in ("sets", "candidates", "guards")} == {
        k: without[k] for k in ("sets", "candidates", "guards")}


def test_a_quick_tier_live_tier_a_glob_over_a_defining_file_gives_a_set(tmp_path):
    """#750: with names at their defining files, a tier A glob over src/b.ts gives a set at Quick tier, as at
    Forge tier, and the inflation guard stays off under #712's glob rule; the deflation guard measures the
    stored 3 against the set's 2 names, 33.33% below it, and fires (#813)."""
    out = _surface(tmp_path, *_fx_quick_traced(tmp_path, FX_DEFINED_IN), *_fx_stored(tmp_path, "src/b.ts"))
    assert out["sets"]["tier_a_include"] == ["beta", "gamma"]
    assert out["guards"]["inflation"]["applicable"] is False
    deflation = out["guards"]["deflation"]
    assert (deflation["basis"], deflation["rederived"], deflation["pct"], deflation["fires"]) == (
        "tier_a_include", 2, -33.33, True)


def test_a_fallback_scan_barrel_result_without_its_passed_on_names_matches_the_runner(tmp_path):
    """#750: the barrel's own result holds only what it defines (here nothing), so the scope sets are the
    definition files' and the stored 3 fires no guard; with the names it passes on, `extra` comes in."""
    barrel = _write(tmp_path / "per-file-3.txt", {"file": "src/index.ts", "exports_found": [], "types_found": [],
                                                   "signature_mismatches": []})
    out = _surface(tmp_path, *_fx_fallback(tmp_path), "--per-file", barrel, "--fallback-scan",
                   *_fx_stored(tmp_path, None))
    assert out["sets"] == {"all": ["alpha", "beta", "gamma"], "scope.include": ["alpha", "beta", "gamma"]}
    assert (out["guards"]["deflation"]["pct"], out["guards"]["deflation"]["fires"]) == (0.0, False)
    assert (out["guards"]["inflation"]["pct"], out["guards"]["inflation"]["fires"]) == (0.0, False)
    passes_on = _write(tmp_path / "per-file-3.txt", {"file": "src/index.ts", "types_found": [],
                                                      "exports_found": ["alpha", "beta", "gamma", "extra"],
                                                      "signature_mismatches": []})
    out = _surface(tmp_path, *_fx_fallback(tmp_path), "--per-file", passes_on, "--fallback-scan",
                   *_fx_stored(tmp_path, None))
    assert out["sets"]["scope.include"] == ["alpha", "beta", "extra", "gamma"]
    assert out["guards"]["deflation"]["fires"] and out["guards"]["inflation"]["fires"]


def test_without_a_source_read_the_guards_do_not_run(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    out = _surface(tmp_path, "--metadata", meta, "--brief", brief)
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"]
    assert "scope.include" not in out["sets"], "no metadata name carries a file"
    assert out["candidates"]["statsEffectiveDenominator"] == 1
    assert out["guards"]["deflation"]["applicable"] is False and out["guards"]["deflation"]["fires"] is False
    # #712: a stored 0 is no exception: with no source read there is nothing to re-derive
    _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 0}})
    deflation = _surface(tmp_path, "--metadata", meta, "--brief", brief)["guards"]["deflation"]
    assert (deflation["applicable"], deflation["pct"], deflation["fires"]) == (False, None, False)


def test_an_extraction_scope_wins_over_the_brief(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", "scope:\n  include: ['nothing/**']\n")
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", EXTRACTION), "--brief", brief)
    assert out["sets"]["scope.include"] == out["sets"]["all"]


def test_a_brief_that_is_not_yaml_exits_1(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", "scope: [unclosed\n")
    proc = _run("surface", "--name", "x", "--brief", brief)
    assert proc.returncode == 1 and "is not valid YAML" in proc.stderr and proc.stderr.count("\n") == 1


def test_state_2_is_the_union_with_its_counts(tmp_path):
    meta = _write(tmp_path / "metadata.json", METADATA)
    prov = _write(tmp_path / "provenance.json", {"entries": PROVENANCE["entries"][:3]})
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta)
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"]
    assert out["state2"] == {"provenanceCount": 2, "metadataCount": 3, "unionCount": 3,
                             "metadataOnly": ["Options"]}


def test_state_3_is_the_metadata_names(tmp_path):
    out = _surface(tmp_path, "--metadata", _write(tmp_path / "metadata.json", METADATA))
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"] and out["state2"] is None


def test_the_canonical_fold(tmp_path):
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    out = _surface(tmp_path, "--provenance", prov, "--fold", "--fold-prefix", "mobile_", "--keep", "a11y_Checkbox")
    # Button_def folds to Button; mobile_Card folds to Card (Card is an entry);
    # mobile_Orphan stays (no Orphan entry); a11y_Checkbox is kept as a real export.
    assert out["sets"]["all"] == ["Button", "Card", "a11y_Checkbox", "fetchData", "helper", "mobile_Orphan"]
    canonical = out["canonical"]
    assert (canonical["raw"], canonical["canonical"]) == (8, 6)
    assert canonical["folded"] == {"_def": 1, "_exact": 0, "a11y_": 0, "other": 1}
    assert canonical["variants"] == {"Button_def": "Button", "mobile_Card": "Card"}
    assert canonical["summary"].startswith("Provenance-map canonicalization: 8 raw entries")


def test_the_fold_covers_the_metadata_names_too(tmp_path):
    """A variant folded out of the map never comes back through metadata.json,
    so two files listing the same names show no State 2 divergence."""
    names = [f"Widget{i}" for i in range(20)] + [f"Widget{i}_def" for i in range(5)]
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": n} for n in names]})
    meta = _write(tmp_path / "metadata.json", {"skill_type": "single", "exports": names})
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta, "--fold")
    assert out["sets"]["all"] == sorted(f"Widget{i}" for i in range(20))
    assert out["state2"] == {"provenanceCount": 20, "metadataCount": 20, "unionCount": 20, "metadataOnly": []}
    assert (out["canonical"]["raw"], out["canonical"]["canonical"]) == (25, 20)
    assert out["canonical"]["folded"]["_def"] == 5
    flags = {"mode": "naive", "tier": "Forge", "state2": True, "analysisConfidence": "provenance-map",
             "toolingStatus": "ok", "scores": {"exportCoverage": 90, "externalValidation": 80}}
    proc = subprocess.run([sys.executable, str(COMPUTE_SCORE), "--json-input", json.dumps(flags),
                           "--surface", str(tmp_path / "surface.json")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    deduction = json.loads(proc.stdout)["state2Deduction"]
    assert (deduction["divergencePct"], deduction["applied"]) == (0.0, False)


def test_a_variant_only_metadata_lists_folds_to_a_map_base(tmp_path):
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "Button"}, {"export_name": "Card"}]})
    meta = _write(tmp_path / "metadata.json", {"exports": ["Button", "Button_exact", "Card", "Extra"]})
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta, "--fold", "--keep", "Card")
    assert out["sets"]["all"] == ["Button", "Card", "Extra"]
    assert out["state2"] == {"provenanceCount": 2, "metadataCount": 3, "unionCount": 3, "metadataOnly": ["Extra"]}
    assert out["canonical"]["variants"] == {}, "the map itself held no variant"


def test_without_fold_no_variant_folds(tmp_path):
    out = _surface(tmp_path, "--provenance", _write(tmp_path / "provenance.json", PROVENANCE))
    assert "Button_def" in out["sets"]["all"] and out["canonical"] is None


def test_help_names_every_subcommand():
    proc = _run("--help")
    assert proc.returncode == 0
    for cmd in ("census", "metadata", "surface"):
        assert cmd in proc.stdout


# --------------------------------------------------------------------------
# A real --mode full run (needs ast-grep)
# --------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_extraction_feeds_the_surface(tmp_path):
    source = tmp_path / "src"
    _write(source / "package.json", '{"name": "demo", "version": "1.0.0", "exports": {".": "./src/index.ts"}}\n')
    _write(source / "src" / "index.ts", "export function fetchData(url: string): string { return url; }\n"
                                        "export interface Options { retries: number }\n"
                                        "export { helper } from './helper';\n"
                                        "export { Settings as Config } from './impl';\n")
    _write(source / "src" / "helper.ts", "export function helper(x: number): number { return x; }\n"
                                         "export function internalThing(): void {}\n")
    _write(source / "src" / "impl.ts", "export interface Settings { depth: number }\n")
    brief = _write(tmp_path / "skill-brief.yaml", "name: demo\nlanguage: typescript\n"
                                                   "scope:\n  type: full-library\n  include: ['src/**']\n")
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--brief", brief, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert out["sets"]["all"] == ["Config", "Options", "fetchData", "helper"]
    # Config is Settings re-exported under an alias: it keeps the kind and
    # line impl.ts defines it with.
    assert {e["name"]: e["kind"] for e in out["exports"]} == {"Config": "interface", "Options": "interface",
                                                              "fetchData": "function", "helper": "function"}
    config = next(e for e in out["exports"] if e["name"] == "Config")
    assert (config["file"], config["line"]) == ("src/impl.ts", 1)


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_local_list_item_feeds_its_declaration_line(tmp_path):
    """#836 end to end: the barrel re-exports NativeButton from a file that declares it at line 1 and lists it in
    `export { ... }` at line 4. The runner keeps the item at the list and records the declaration, and
    score-signatures.py plans the check at the declaration."""
    source = tmp_path / "src"
    _write(source / "package.json", '{"name": "demo", "version": "1.0.0", "exports": {".": "./src/index.ts"}}\n')
    _write(source / "src" / "index.ts", "export { NativeButton } from './native-button';\n")
    _write(source / "src" / "native-button.tsx", "const NativeButton = ({\n  label,\n}: Props) => label\n"
                                                 "export { NativeButton }\n")
    brief = _write(tmp_path / "skill-brief.yaml", "name: demo\nlanguage: typescript\n"
                                                   "scope:\n  type: full-library\n  include: ['src/**']\n")
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--brief", brief, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(extraction.read_text(encoding="utf-8"))
    (item,) = [e for e in data["exports"] if e["source_file"] == "src/native-button.tsx"]
    assert (item["source_line"], item["signature_line"], item["citation"]) == (
        4, "export { NativeButton }", "[AST:src/native-button.tsx:L4]")
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert [(e["name"], e["kind"], e["file"], e["line"]) for e in out["exports"]] == [
        ("NativeButton", "function", "src/native-button.tsx", 1)]
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "NativeButton", "kind": "function", "params": "label", "return_type": "string"},
    ], "cross_check_mismatches": []})
    plan = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "plan", "--inventory", inventory,
                                      "--surface", str(tmp_path / "surface.json")],
                                     capture_output=True, text=True, check=True).stdout)
    assert [(f["file"], [(c["name"], c["line"], c["signatureLine"]) for c in f["checks"]]) for f in plan["files"]] == [
        ("src/native-button.tsx", [("NativeButton", 1, "const NativeButton = ({")])]


COGNEE_TREE = {
    "cognee/__init__.py": "from .api.v1.add import add\nfrom .pipelines import run_pipeline, Task\n"
                          "from .tests.helper import test_helper\n",
    "cognee/pipelines/__init__.py": "from .run import run_pipeline\nfrom .task import Task\n",
    "cognee/pipelines/run.py": ("\"\"\"Run a pipeline.\"\"\"\n\n\n"
                                "def run_pipeline(tasks, data=None):\n    return tasks\n"),
    "cognee/pipelines/task.py": "# A pipeline step.\nclass Task:\n    pass\n",
    "cognee/api/v1/add.py": "def add(data, dataset_name=\"main\"):\n    return data\n",
    "cognee/api/v1/routers/__init__.py": "from .add import get_add_router\nfrom .search import get_search_router\n",
    "cognee/api/v1/routers/add.py": "def get_add_router():\n    return None\n",
    "cognee/api/v1/routers/search.py": "def get_search_router():\n    return None\n",
    "cognee/tests/helper.py": "def test_helper():\n    return 1\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_cognee_tree(tmp_path):
    """#677 end to end: the runner on the cognee v1.0.0 shape under its v0.5.8
    brief, then the surface: COGNEE above is this run's output."""
    source = tmp_path / "src"
    for rel, text in COGNEE_TREE.items():
        _write(source / rel, text)
    brief = _write(tmp_path / "skill-brief.yaml", COGNEE_BRIEF)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--brief", brief, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(extraction.read_text(encoding="utf-8"))
    assert data["scope"] == COGNEE["scope"]
    assert data["entry_points"]["files"] == COGNEE["entry_points"]["files"]
    assert data["entry_point_diff"] == COGNEE["entry_point_diff"]
    assert data["warnings"] == COGNEE["warnings"]
    out = _surface(tmp_path, "--extraction", str(extraction), "--brief", brief)
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES]
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    assert [n["entry"] for n in out["excluded"]["nestedEntries"]] == [ROUTERS]


TIER_A_TREE = {
    "package.json": '{"name": "demo", "exports": {".": "./src/index.ts", "./macro": "./macro/index.ts"}}\n',
    "src/index.ts": "export { format } from './utils/format';\nexport const VERSION = '1';\n",
    "src/utils/format.ts": "export function format(v: string): string { return v; }\n",
    "macro/index.ts": "export function macro(): void {}\nexport interface MacroOptions { x: number }\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
@pytest.mark.parametrize(("include", "tier_a", "basis", "count"),
                         [(["src/**"], ["macro/**"], "scope.include", 2),
                          (["src/**"], ["src/utils/**", "macro/**"], "tier_a_include", 1),
                          (["src/**"], ["src/utils/**"], "tier_a_include", 1),
                          ([], ["macro/**"], "tier_a_include", 2)],
                         ids=["outside-only", "mixed", "inside-only", "no-include"])
def test_the_runner_and_the_surface_count_one_tier_a_set(tmp_path, include, tier_a, basis, count):
    """#725: the count Create Skill stores is the one Test Skill re-derives: the runner's tier A count is the
    tier_a_include set, and when it falls back to scope.include the surface has no set."""
    source = tmp_path / "src"
    for rel, text in TIER_A_TREE.items():
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    argv = [sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
            "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)]
    for glob in include:
        argv += ["--include", glob]
    for glob in tier_a:
        argv += ["--tier-a-include", glob]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    counts = json.loads(extraction.read_text(encoding="utf-8"))["counts"]
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert counts["effective_denominator_basis"] == basis
    if basis == "tier_a_include":
        assert counts["effective_denominator"] == out["candidates"]["tierAIncludeUnion"] == count
    else:
        assert "tier_a_include" not in out["sets"]
        assert counts["effective_denominator"] == out["candidates"]["scopeIncludeUnion"] == count


# #734: `foo` at src/a.ts and, through `export * as ns`, at src/b.ts beside `bar`: two records, one name
TWO_FILE_TREE = {
    "package.json": '{"name": "demo", "exports": {".": "./src/index.ts"}}\n',
    "src/index.ts": "export { foo } from './a';\nexport * as ns from './b';\n",
    "src/a.ts": "export function foo(): number { return 1; }\n",
    "src/b.ts": "export function foo(): string { return ''; }\nexport function bar(): void {}\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
@pytest.mark.parametrize(("flags", "basis", "union", "records", "count"), [
    (["--tier-a-include", "src/**"], "tier_a_include", "tierAIncludeUnion",
     [("bar", "src/b.ts"), ("foo", "src/a.ts"), ("foo", "src/b.ts")], 2),
    ([], "scope.include", "scopeIncludeUnion", [("bar", "src/b.ts"), ("foo", "src/a.ts"), ("foo", "src/b.ts")], 2),
    (["--exclude", "src/b.ts"], "scope.include", "scopeIncludeUnion", [("foo", "src/a.ts")], 1),
    (["--tier-a-include", "src/a.ts"], "tier_a_include", "tierAIncludeUnion",
     [("bar", "src/b.ts"), ("foo", "src/a.ts"), ("foo", "src/b.ts")], 1),
], ids=["tier-a", "scope-include", "one-key-excluded", "tier-a-a-only"])
def test_the_runner_counts_a_name_passed_on_from_two_files_once_as_the_surface_does(tmp_path, flags, basis, union,
                                                                                    records, count):
    """#734: the count Create Skill stores is the set Test Skill re-derives when the entry points pass one
    name on from two files: the runner counts it once, while the surface keeps a record (a signature) for each.
    With src/b.ts excluded, or a tier A list of src/a.ts alone, `foo` still counts once, by its key at src/a.ts."""
    source = tmp_path / "src"
    for rel, text in TWO_FILE_TREE.items():
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    argv = [sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source), "--include", "src/**",
            *flags, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    counts = json.loads(extraction.read_text(encoding="utf-8"))["counts"]
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert [(r["name"], r["file"]) for r in out["exports"]] == records
    assert (counts["exports_public_api"], counts["effective_denominator_basis"]) == (3, basis)
    candidates = out["candidates"]
    assert counts["effective_denominator"] == candidates[union] == candidates["extractorEffectiveDenominator"] == count
    assert len(out["sets"][basis]) == count


# --------------------------------------------------------------------------
# surface: the denominator clause (v4.0.0 quality gate run 1, skf-test-skill
# determinism-1). The pick was a hand-run decision table in
# source-access-protocol.md and coverage-check.md §2b; the script makes it
# from the brief, the extraction, metadata.json and the two judgments the
# model passes as flags, one golden case per clause.
# --------------------------------------------------------------------------


def _clause(tmp_path: Path, extraction: dict | None = None, stats: dict | None = None, *flags: str,
            meta: dict | None = None) -> dict:
    args = []
    if extraction is not None:
        args += ["--extraction", _write(tmp_path / "extract-full.json", extraction)]
    if stats is not None or meta is not None:
        args += ["--metadata", _write(tmp_path / "metadata.json", meta or dict(METADATA, stats=stats))]
    return _surface(tmp_path, *args, *flags)["denominator"]


def _extraction(scope_type: str = "full-library", status: str = "barrel", **arms) -> dict:
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["type"] = scope_type
    data["entry_points"]["status"] = status
    data["arms"].update(arms)
    return data


def _barrel(clause: str, surface_set: str, step: int | None = None, absent: str | None = None,
            rebuild: str | None = None, barrel: str | None = "barrel") -> dict:
    return {"clause": clause, "branch": "barrel", "surfaceSet": surface_set, "ladderStep": step,
            "absentSet": absent, "rebuild": rebuild, "barrel": barrel, "setCounted": None}


def _scalar(clause: str, surface_set: str, counted: bool = True) -> dict:
    """The scalar branch; `counted`: it counts its scope set (#791, #792), as a complete runner extraction allows."""
    return {"clause": clause, "branch": "scalar", "surfaceSet": surface_set, "ladderStep": 1, "absentSet": None,
            "rebuild": None, "barrel": "barrel", "setCounted": counted}


STORED = {"exports_public_api": 7, "exports_documented": 5, "effective_denominator": 7}
DEFLATED = {"exports_public_api": 7, "exports_documented": 5, "effective_denominator": 4}


def test_a_full_library_barrel_is_the_standard_barrel(tmp_path):
    assert _clause(tmp_path, _extraction(), STORED) == _barrel("standard-barrel", "all")


@pytest.mark.parametrize(("stats", "flags", "expected"), [
    (STORED, [], _scalar("stratified-scope", "scope.include")),
    (DEFLATED, [], _barrel("stratified-scope", "scope.include", 1)),
    (None, [], _barrel("stratified-scope", "scope.include", 3))],
    ids=["stored", "deflated", "no-stored-count"])
def test_a_curated_monorepo_subset_walks_the_stratified_ladder(tmp_path, stats, flags, expected):
    """Priority 1 is the stored count unless the deflation guard fires, then the `scope.include` set; with no
    stored count and no tier A set, priority 3."""
    extraction = _extraction("public-api")
    meta = None if stats is not None else {k: v for k, v in METADATA.items() if k != "stats"}
    assert _clause(tmp_path, extraction, stats, "--monorepo", "--curated-subset", *flags, meta=meta) == expected


def test_a_stratified_tier_a_set_is_priority_2(tmp_path):
    extraction = _extraction("public-api")
    extraction["scope"]["tier_a_include"] = ["src/index.ts"]
    meta = {k: v for k, v in METADATA.items() if k != "stats"}
    assert _clause(tmp_path, extraction, None, "--monorepo", "--curated-subset", meta=meta) == _barrel(
        "stratified-scope", "tier_a_include", 2)


def test_a_full_library_monorepo_or_a_whole_workspace_is_the_standard_barrel(tmp_path):
    assert _clause(tmp_path, _extraction(), STORED, "--monorepo", "--curated-subset") == _barrel(
        "standard-barrel", "all")
    assert _clause(tmp_path, _extraction("public-api"), STORED, "--monorepo") == _barrel("standard-barrel", "all")


@pytest.mark.parametrize(("stats", "expected"), [
    (STORED, _scalar("specific-modules", "scope.include")),
    (None, _barrel("specific-modules", "scope.include", 2))], ids=["stored", "no-stored-count"])
def test_a_specific_modules_skill_takes_its_stored_count_first(tmp_path, stats, expected):
    """§2b sent specific-modules to the barrel branch while the protocol and Create Skill's compile §4 put
    `stats.effective_denominator` first: the stored count is the denominator, under the deflation guard."""
    meta = None if stats is not None else {k: v for k, v in METADATA.items() if k != "stats"}
    assert _clause(tmp_path, _extraction("specific-modules"), stats, meta=meta) == expected


@pytest.mark.parametrize(("stats", "expected"), [
    (STORED, _scalar("multi-entry", "scope.include")),
    (None, _barrel("multi-entry", "subpaths", 3))], ids=["stored", "no-stored-count"])
def test_a_multi_entry_package_takes_its_stored_count_then_its_subpaths(tmp_path, stats, expected):
    meta = None if stats is not None else {k: v for k, v in METADATA.items() if k != "stats"}
    extraction = _extraction("public-api", multi_subpath_exports=True)
    assert _clause(tmp_path, extraction, stats, meta=meta) == expected


def test_an_empty_barrel_counts_the_scope_include_set(tmp_path):
    assert _clause(tmp_path, _extraction("public-api", "empty-barrel"), STORED) == _barrel(
        "empty-barrel", "scope.include", barrel="empty-barrel")


@pytest.mark.parametrize(("status", "flags", "expected"), [
    ("no-entry-point", [], _barrel("pattern-reference", "all", rebuild="provenance-fold", barrel="no-entry-point")),
    ("empty-barrel", ["--pattern-reference-intent"], _barrel("pattern-reference", "all", rebuild="provenance-fold",
                                                             barrel="empty-barrel")),
    ("barrel", ["--pattern-reference-intent"], _barrel("standard-barrel", "all"))],
    ids=["no-barrel", "intent", "a-non-empty-barrel"])
def test_a_pattern_reference_app_counts_its_canonical_map(tmp_path, status, flags, expected):
    """Either trigger fires, never over a non-empty barrel: with no tier A set the surface is built again
    from the provenance map alone, folded."""
    assert _clause(tmp_path, _extraction("public-api", status), STORED, *flags) == expected


def test_a_pattern_reference_surface_from_the_map_needs_no_rebuild(tmp_path):
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    out = _surface(tmp_path, "--provenance", prov, "--fold", "--pattern-reference-intent")
    assert out["denominator"] == _barrel("pattern-reference", "all", barrel=None)


def test_a_stack_takes_the_stack_branch(tmp_path):
    meta = dict(METADATA, skill_type="stack")
    assert _clause(tmp_path, None, None, meta=meta) == {
        "clause": "stack", "branch": "stack", "surfaceSet": None, "ladderStep": None, "absentSet": None,
        "rebuild": None, "barrel": None, "setCounted": None}


def test_an_absent_set_falls_back_to_all(tmp_path):
    """A clause whose set the surface lacks (no brief glob, no file on the names) counts the `all` set, and
    names the set it lacked for the `Denominator:` line."""
    extraction = _extraction("specific-modules")
    extraction["scope"]["include"] = []
    meta = {k: v for k, v in METADATA.items() if k != "stats"}
    assert _clause(tmp_path, extraction, None, meta=meta) == _barrel("specific-modules", "all", 2, "scope.include")


def test_the_map_already_canonical_is_not_folded(tmp_path):
    """The protocol's last canonicalization judgment was a compare: a map whose raw count equals
    `stats.effective_denominator` is already canonical, so `--fold` folds nothing."""
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    named = 8  # the named exports less Extra::run
    meta = _write(tmp_path / "metadata.json", dict(METADATA, stats={"effective_denominator": named}))
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta, "--fold")
    assert out["canonical"]["folded"] == {"_def": 0, "_exact": 0, "a11y_": 0, "other": 0}
    assert out["canonical"]["canonical"] == named and out["canonical"]["skipped"] is True
    folded = _write(tmp_path / "metadata2.json", dict(METADATA, stats={"effective_denominator": 5}))
    out = _surface(tmp_path, "--provenance", prov, "--metadata", folded, "--fold")
    assert out["canonical"]["skipped"] is False and out["canonical"]["residual"] == out["canonical"]["canonical"] - 5


# v4.0.0 quality gate run 1 review: the entry points' state where no complete extraction or quick output gives it,
# the extraction's curated-subset and monorepo verdicts, and a stored 0


def _no_ast_grep(entry_files: list[dict]) -> dict:
    """The runner's exit-3 JSON over one Python app: no recipe ran, the entry points it found listed."""
    data = json.loads(json.dumps(EXTRACTION))
    data.update(status="no-ast-grep", exports=[], counts=None, entry_point_diff=None)
    data["scope"].update(include=["app/**"], exclude=[], type="full-library", languages=["python"])
    data["entry_points"] = {"status": None, "by_language": {}, "files": entry_files, "exports_maps": [],
                            "unresolved": []}
    return data


APP_FILES = [{"file": "app/main.py", "exports_found": ["run", "serve"], "signature_mismatches": []},
             {"file": "app/db.py", "exports_found": ["connect"], "signature_mismatches": []}]
INIT_ENTRY = [{"language": "python", "file": "app/__init__.py", "package": "app", "subpath": None,
               "resolution": "file", "in_scope": True}]


def _fallback_scan(tmp_path: Path, extraction: dict | None, *flags: str) -> dict:
    per_file = [_write(tmp_path / f"per-file-{n}.txt", result) for n, result in enumerate(APP_FILES, 1)]
    args = [arg for path in per_file for arg in ("--per-file", path)]
    if extraction is not None:
        args += ["--fallback-scan", "--extraction", _write(tmp_path / "extract-full.json", extraction)]
    else:
        args += ["--brief", _write(tmp_path / "skill-brief.yaml", "name: app\nlanguage: python\nscope:\n"
                                   "  type: full-library\n  include: ['app/**']\n")]
    meta = _write(tmp_path / "metadata.json", {k: v for k, v in METADATA.items() if k != "stats"})
    return _surface(tmp_path, *args, "--metadata", meta, *flags)["denominator"]


def test_a_fallback_scan_with_no_entry_point_is_a_pattern_reference_app(tmp_path):
    """A Python app with no `__init__.py`: with ast-grep the runner says `no-entry-point` and the app counts its
    canonical map; without it the exit-3 JSON lists no entry file, which says the same, so the clause no longer
    depends on whether ast-grep is installed."""
    assert _fallback_scan(tmp_path, _no_ast_grep([])) == _barrel(
        "pattern-reference", "all", rebuild="provenance-fold", barrel="no-entry-point")


@pytest.mark.parametrize(("flags", "expected"), [
    ([], _barrel("standard-barrel", "all", barrel=None)),
    (["--barrel", "empty"], _barrel("empty-barrel", "scope.include", barrel="empty-barrel")),
    (["--barrel", "none"], _barrel("pattern-reference", "all", rebuild="provenance-fold", barrel="no-entry-point")),
    (["--barrel", "barrel"], _barrel("standard-barrel", "all"))], ids=["unknown", "empty", "none", "barrel"])
def test_where_no_file_tells_the_entry_points_state_the_flag_does(tmp_path, flags, expected):
    """An entry file the runner listed but no recipe read (an empty `__init__.py` read by eye), and a surface
    of per-file results alone (Quick tier read by eye, State 4): `surface` cannot tell an empty barrel or a
    missing one, so `--barrel` carries what the workflow read; with none the state is unknown."""
    assert _fallback_scan(tmp_path, _no_ast_grep(INIT_ENTRY), *flags) == expected
    assert _fallback_scan(tmp_path / "eye", None, *flags) == expected


def test_a_complete_extraction_wins_over_the_barrel_flag(tmp_path):
    assert _clause(tmp_path, _extraction(), STORED, "--barrel", "none") == _barrel("standard-barrel", "all")


@pytest.mark.parametrize(("curated", "flags", "expected"), [
    (True, [], _scalar("stratified-scope", "scope.include")),
    (False, ["--curated-subset"], _barrel("standard-barrel", "all"))], ids=["extraction-curated", "extraction-not"])
def test_the_extraction_decides_the_curated_monorepo_subset(tmp_path, curated, flags, expected):
    """Create Skill stores `stats.effective_denominator` by the runner's `counts.curated_subset`, which the
    extraction Test Skill runs carries too: it and `arms.monorepo` pick the stratified clause with no flag, and
    a judgment that disagrees with the script is not taken."""
    extraction = _extraction("public-api", monorepo=True)
    extraction["counts"]["curated_subset"] = curated
    assert _clause(tmp_path, extraction, STORED, *flags) == expected


def test_a_stored_zero_is_no_denominator(tmp_path):
    """A legacy stored 0 at State 2 (no source read, so no deflation guard): the scalar branch over 0 halted as
    an indeterminate surface; the specific-modules ladder goes on to its set."""
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    meta = _write(tmp_path / "metadata.json", dict(METADATA, scope_type="specific-modules",
                                                   stats={"effective_denominator": 0}))
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta, "--brief", brief)
    assert out["guards"]["deflation"]["applicable"] is False
    assert out["denominator"] == _barrel("specific-modules", "scope.include", 2, barrel=None)


# #788, #813: on a clause whose ladder holds a stored count, a stored `stats.effective_denominator` the brief's
# tier A set disagrees with beyond the deflation threshold, either way, is stale: the gap asks to recount, and the
# ladder's tier A rung (stratified-scope, multi-entry), else the scope.include set, is the denominator. When the
# deflation and inflation guards both fire on the `scope.include` union, that union stays the denominator and both
# gaps name the brief's tier A list.
TIER_A_CLAUSES = {
    "stratified-scope": (_extraction("public-api"), ["--monorepo", "--curated-subset"]),
    "specific-modules": (_extraction("specific-modules"), []),
    "multi-entry": (_extraction("public-api", multi_subpath_exports=True), []),
}
# The set a fire counts: specific-modules' ladder has no tier A rung.
FIRED_SET = {"stratified-scope": "tier_a_include", "specific-modules": "scope.include", "multi-entry": "tier_a_include"}


def _tier_a_clause(tmp_path: Path, clause: str, stored: int, tier_a: tuple[str, ...] = ("src/index.ts",),
                   status: str = "ok") -> dict:
    extraction, flags = TIER_A_CLAUSES[clause]
    extraction = json.loads(json.dumps(extraction))
    extraction["scope"]["tier_a_include"] = list(tier_a)
    extraction["status"] = status
    meta = _write(tmp_path / "metadata.json", dict(METADATA, stats={"effective_denominator": stored}))
    return _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", extraction), "--metadata", meta,
                    "--provenance", _write(tmp_path / "provenance.json", PROVENANCE), *flags)


@pytest.mark.parametrize("clause", list(TIER_A_CLAUSES))
@pytest.mark.parametrize(("stored", "pct"), [(2, 50.0), (7, -57.14)], ids=["above", "below"])
def test_a_tier_a_set_beats_a_stale_stored_count(tmp_path, clause, stored, pct):
    """#813: the brief's 3 tier A names against a stored 2 (+50%) or 7 (-57%): beyond the threshold either way,
    so the deflation guard fires on the tier A basis, the barrel branch counts the ladder's tier A rung (the
    scope.include set on specific-modules, which has none), and the ledger records a drift gap that asks Create
    Skill to recount and names that set."""
    out = _tier_a_clause(tmp_path, clause, stored)
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "tier_a_include",
                                          "effectiveDenominator": stored, "rederived": 3, "pct": pct, "fires": True}
    assert out["guards"]["inflation"]["applicable"] is False, "inflation stays gated on no tier A list"
    assert out["denominator"] == _barrel(clause, FIRED_SET[clause], 1)
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"], drift["title"]) == (
        "Medium", "metadata-drift",
        "denominator drift: effective_denominator disagrees with the brief's tier_a_include set")
    assert drift["remediation"].startswith("Re-run Create Skill to recount")
    assert drift["remediation"].endswith(f"Until then Test Skill counts the `{FIRED_SET[clause]}` set as the "
                                         "denominator.")


@pytest.mark.parametrize("clause", list(TIER_A_CLAUSES))
def test_a_stored_count_within_the_threshold_of_the_tier_a_set_stays_the_denominator(tmp_path, clause):
    """#813: a stored 3 equal to the tier A set's count fires nothing: the scalar branch, as before (the guard's
    tier A basis is pinned beside the stale counts above)."""
    out = _tier_a_clause(tmp_path, clause, 3)
    assert out["guards"]["deflation"]["fires"] is False
    assert out["denominator"] == _scalar(clause, "tier_a_include")
    assert gap_ledger.from_guards(out) == []


def test_a_tier_a_set_25_percent_above_the_stored_count_does_not_fire(tmp_path):
    """#813: the threshold is exclusive on the tier A basis too: 5 tier A names against a stored 4 is +25.0%."""
    out = _tier_a_clause(tmp_path, "stratified-scope", 4, ("src/index.ts", "src/extra.ts"))
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "tier_a_include", "effectiveDenominator": 4,
                                          "rederived": 5, "pct": 25.0, "fires": False}
    assert out["denominator"] == _scalar("stratified-scope", "tier_a_include")


def test_a_stored_zero_against_a_tier_a_set_is_drift(tmp_path):
    """#813 closes what #712 left open on a stratified skill: a stored 0 under a tier A set that counts names is
    a stale count to recount, with no percentage against 0. A stored 0 was never the denominator: the ladder's
    tier A rung still counts."""
    out = _tier_a_clause(tmp_path, "stratified-scope", 0)
    assert out["guards"]["deflation"] == {"applicable": True, "basis": "tier_a_include", "effectiveDenominator": 0,
                                          "rederived": 3, "pct": None, "fires": True}
    assert out["denominator"] == _barrel("stratified-scope", "tier_a_include", 2)
    [drift] = gap_ledger.from_guards(out)
    assert drift["title"] == "denominator drift: effective_denominator disagrees with the brief's tier_a_include set"
    assert drift["issue"] == ("the brief's `scope.tier_a_include` set counts 3 exports against a "
                              "`stats.effective_denominator` of 0")


@pytest.mark.parametrize(("extraction", "expected"), [
    (_extraction(), _barrel("standard-barrel", "all")),
    (_extraction("public-api", "empty-barrel"), _barrel("empty-barrel", "scope.include", barrel="empty-barrel")),
    (_extraction("public-api", "no-entry-point"),
     _barrel("pattern-reference", "tier_a_include", barrel="no-entry-point")),
], ids=["standard-barrel", "empty-barrel", "pattern-reference"])
def test_a_clause_with_no_stored_count_takes_no_drift_gap(tmp_path, extraction, expected):
    """#813: on a clause whose denominator is never the stored count, a tier A set that disagrees with it is no
    drift: the guard reads the scope.include union (and stays off beside the tier A list), so no gap says the
    tier A set is a denominator the clause does not count."""
    extraction = json.loads(json.dumps(extraction))
    extraction["scope"]["tier_a_include"] = ["src/index.ts"]
    meta = _write(tmp_path / "metadata.json", dict(METADATA, stats={"effective_denominator": 2}))
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", extraction), "--metadata", meta)
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert (out["guards"]["deflation"]["basis"], out["guards"]["deflation"]["fires"]) == ("scope.include", False)
    assert out["denominator"] == expected
    assert gap_ledger.from_guards(out) == []


@pytest.mark.parametrize(("stored", "expected"), [
    (7, _scalar("stratified-scope", "tier_a_include", counted=False)),
    (2, _barrel("stratified-scope", "tier_a_include", 1)),
], ids=["below-keeps-the-stored-count", "above-takes-the-set"])
def test_an_incomplete_extraction_reports_a_downward_drift_without_taking_the_set(tmp_path, stored, expected):
    """#813: an incomplete extraction can miss tier A names, so a tier A set below the stored count is drift to
    report, not a denominator to take; a set above the stored count still counts. #791, #792: nor does the scalar
    branch count that set as its numerator's (`setCounted` false): it keeps the looked-up numerator."""
    out = _tier_a_clause(tmp_path, "stratified-scope", stored, status="incomplete")
    assert out["extraction"]["status"] == "incomplete"
    assert out["guards"]["deflation"]["fires"] is True
    assert out["denominator"] == expected
    [drift] = gap_ledger.from_guards(out)
    assert drift["title"] == "denominator drift: effective_denominator disagrees with the brief's tier_a_include set"
    assert drift["remediation"].endswith(
        "Until then the stored count stays the denominator: the extraction is incomplete, so the tier A set can miss "
        "names." if expected["branch"] == "scalar" else
        "Until then Test Skill counts the `tier_a_include` set as the denominator.")


def test_both_guards_on_an_umbrella_barrel_keep_the_scope_include_denominator(tmp_path):
    """#788 end to end: six more root re-exports make the root barrel an umbrella (9 of 12 names re-exported), and
    a stored 4 against the 13-name `scope.include` union and four provenance entries fires both guards. The union
    stays the denominator, and both gaps name the brief's tier A list instead of a stored count set by hand."""
    extraction = _extraction("public-api")
    extraction["entry_point_diff"]["public"] += [
        {"name": f"util{n}", "entry": "src/index.ts", "via": "re-export", "file": f"src/util/u{n}.ts", "line": 1}
        for n in range(6)]
    meta = _write(tmp_path / "metadata.json", dict(METADATA, stats={"effective_denominator": 4}))
    prov = _write(tmp_path / "provenance.json", {"entries": PROVENANCE["entries"][:4]})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", extraction), "--metadata", meta,
                   "--provenance", prov, "--monorepo", "--curated-subset")
    guards = out["guards"]
    assert guards["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 4,
                                   "rederived": 13, "pct": 225.0, "fires": True}
    assert guards["inflation"] == {"applicable": True, "scopeIncludeUnion": 13, "provenanceEntries": 4,
                                   "pct": 225.0, "fires": True}
    assert (guards["umbrella"]["names"], guards["umbrella"]["reexported"], guards["umbrella"]["umbrella"]) == (
        12, 9, True)
    assert out["denominator"] == _barrel("stratified-scope", "scope.include", 1)
    deflation, inflation = gap_ledger.from_guards(out)
    assert [deflation["category"], inflation["category"]] == ["metadata-drift", "denominator-inflation"]
    assert deflation["remediation"] == inflation["remediation"]
    assert inflation["remediation"].startswith("Add `scope.tier_a_include`")
    assert "Set `stats.effective_denominator`" not in inflation["remediation"]
