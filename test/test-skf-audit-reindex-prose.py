#!/usr/bin/env python3
"""Prose pins: audit-skill's re-index follows the AST Extraction Protocol and
adds nothing to its snapshot after writing it.

#561: at Deep tier, re-index asked QMD for temporal context on every export
and appended it to `extraction-snapshot.json` after §3 had written the file,
whose schema had no field for it, and nothing read it there. That pass is
gone: semantic-diff.md stays the one audit step that queries QMD. These
tests keep re-index.md on that contract:
- no T2 label, temporal context or QMD query is left in it, and no sentence
  after the snapshot write adds data to the snapshot;
- the §3 schema documents every field skf-structural-diff.py reads and no
  temporal field, and the §5 Labels row lists only the labels its
  `confidence` field holds;
- its sections run 1 to 6 with no gap, and the Forge+ pointer names the ccc
  rename section.

The AST Extraction Protocol in create-skill's extraction-patterns.md runs the
ast-grep recipes, with `find_code` only as its fallback. These tests keep
audit and the knowledge base on it:
- re-index.md names the protocol through an `extractionPatternsData` path
  that resolves, runs every recipe once over the bounded scan list, keeps the
  matches on it, reruns a run that fills its cap, takes `$NAME`'s line and
  uses `find_code` only as Known Limitation #4's fallback, and every protocol
  anchor it cites exists;
- tool-resolution.md's ast_bridge rows name `find_code_by_rule` with the
  recipes and `ast-grep scan -r ... --json=stream`, never `sg run`,
  `ast-grep -p` or `ast-grep run -p`;
- audit-skill's SKILL.md names both create-skill files re-index.md loads.
With the pinned ast-grep on PATH, the protocol's CLI streaming template run
over a batch of listed files prints only their exports, at `$NAME`'s line.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
AUDIT = SRC / "skf-audit-skill"
RE_INDEX = AUDIT / "references" / "re-index.md"
SEMANTIC_DIFF = AUDIT / "references" / "semantic-diff.md"
AUDIT_SKILL = AUDIT / "SKILL.md"
PATTERNS = SRC / "skf-create-skill" / "references" / "extraction-patterns.md"
TOOL_RESOLUTION = SRC / "knowledge" / "tool-resolution.md"
DIFF_HELPER = SRC / "shared" / "scripts" / "skf-structural-diff.py"

PATTERNS_PATH = "skf-create-skill/references/extraction-patterns.md"
DEGRADATION_PATH = "skf-create-skill/references/tier-degradation-rules.md"
SNAPSHOT_WRITE = "**Build extraction snapshot and persist it to `{forge_version}/extraction-snapshot.json`**"
CLI_COMMAND = "ast-grep scan -r {recipe_file} --json=stream"
# The fields skf-structural-diff.py keeps from a snapshot export (#561).
READ_BY_DIFF = ("name", "type", "signature", "file", "line", "confidence", "extraction_method")

FENCE_RE = re.compile(r"^```yaml\n(.*?)^```", re.M | re.S)
CLI_TEMPLATE_RE = re.compile(
    r'^ast-grep scan -r \{recipe_file\} --json=stream \{path\} \| python3 -c "\n(.*?)^" \| head -\{HEAD_CAP\}$',
    re.M | re.S,
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    section = text[i:j]
    assert section.strip(), f"empty slice between {start!r} and {end!r}"
    return section


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "no frontmatter"
    return yaml.safe_load(text[4:text.index("\n---\n", 4)])


def _body(text: str) -> str:
    return text[text.index("\n---\n", 4) + 5:]


def _schema(text: str) -> tuple[str, str]:
    """The §3 snapshot schema block, and the text after its closing fence."""
    write = text.index(SNAPSHOT_WRITE)
    opening = text.index("```", write)
    body = text.index("\n", opening) + 1
    closing = text.index("```", body)
    return text[body:closing], text[closing + 3:]


def _export_fields(text: str) -> dict[str, str]:
    """Each field of one snapshot export in the §3 schema, with its value."""
    block, _ = _schema(text)
    export = block[block.index('"exports": ['):]
    fields = dict(re.findall(r'^\s*"(\w+)":\s*(.+?),?$', export, re.M))
    assert fields, "no export fields in the snapshot schema"
    return fields


def _sentences(text: str) -> list[str]:
    return [s for line in text.splitlines() for s in re.split(r"(?<=[.:;])\s+", line) if s.strip()]


# --------------------------------------------------------------------------
# #561: no temporal pass, nothing added to the written snapshot
# --------------------------------------------------------------------------


def test_no_temporal_pass_is_left() -> None:
    text = _read(RE_INDEX)
    assert not re.search(r"\bT2\b", text), "a T2 label is left in re-index.md"
    lowered = text.lower()
    for gone in ("temporal", "enrichment", "qmd_bridge", "qmd_collections", "qmd ls", "{skill_name}-extraction"):
        assert gone not in lowered, gone
    assert "Deep Tier Enhancement" not in text


def test_deep_tier_extracts_as_forge_and_semantic_diff_queries_qmd() -> None:
    deep = _slice(_read(RE_INDEX), "**Deep tier (ast-grep + QMD available):**", "**Tool resolution:**")
    assert "Identical extraction to Forge tier, labeled by tool as at Forge tier" in deep
    assert "No QMD query at this step: step 4 (semantic diff) queries QMD itself" in deep
    # semantic-diff.md reads the QMD registry itself, and its direct-content
    # fallback still points at this block for the Deep-tier AST tooling.
    semantic = _read(SEMANTIC_DIFF)
    assert "`qmd_collections` registry" in semantic
    assert 'see step 2 §1 "Deep tier"' in semantic


def test_nothing_is_added_to_the_snapshot_after_it_is_written() -> None:
    _, after = _schema(_read(RE_INDEX))
    mentions = [s for s in _sentences(after) if "snapshot" in s.lower()]
    assert mentions, "no sentence after the schema mentions the snapshot"
    for sentence in mentions:
        assert not re.search(r"\b(append|add|enrich|attach)", sentence, re.I), sentence


def test_snapshot_schema_holds_what_structural_diff_reads(tmp_path: Path) -> None:
    fields = _export_fields(_read(RE_INDEX))
    assert "temporal" not in fields
    for key in READ_BY_DIFF:
        assert key in fields, f"the snapshot schema lacks {key}"
    # One export holding every documented field, against an empty baseline:
    # the helper reports it as added, in the record it builds from the fields
    # it reads, so a field read under a name the schema lacks comes back null.
    export = {key: 3 if key == "line" else f"sample-{key}" for key in fields}
    baseline = tmp_path / "baseline.json"
    snapshot = tmp_path / "extraction-snapshot.json"
    baseline.write_text(json.dumps({"exports": []}), encoding="utf-8")
    snapshot.write_text(json.dumps({"exports": [export]}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(DIFF_HELPER), str(baseline), str(snapshot)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode in (0, 1) and result.stdout.strip(), result.stderr
    (added,) = json.loads(result.stdout)["added"]
    for key in READ_BY_DIFF:
        assert added.get(key) is not None, f"the helper reads {key} under another name"


def test_labels_row_lists_only_the_snapshot_labels() -> None:
    text = _read(RE_INDEX)
    fields = _export_fields(text)
    confidences = fields["confidence"].strip('"').split("|")
    methods = fields["extraction_method"].strip('"').split("|")
    assert confidences == ["T1", "T1-low"]
    assert methods == ["ast-grep", "source-read"]
    row = _slice(text, "| Labels |", "\n")
    assert re.findall(r"\} (T1(?:-low)?) \(`([a-z-]+)`\)", row) == list(zip(confidences, methods))
    assert row.rstrip().endswith("T1-low (`source-read`) |"), row


def test_sections_run_one_to_six_and_the_ccc_pointer_resolves() -> None:
    text = _read(RE_INDEX)
    headings = re.findall(r"^### (\w+)\. (.+)$", text, re.M)
    assert [number for number, _ in headings] == ["1", "2", "3", "4", "5", "6"]
    assert dict(headings)["4"] == "CCC Rename Detection (Forge+ and Deep with ccc)"
    forge_plus = _slice(text, "**Forge+ tier (ast-grep + ccc available):**", "**Deep tier")
    assert "CCC rename detection available (see section 4)" in forge_plus
    assert "4b" not in text


# --------------------------------------------------------------------------
# #556's pre-release fix: the AST Extraction Protocol in audit and the knowledge base
# --------------------------------------------------------------------------


def test_frontmatter_names_the_protocol_and_every_data_path_resolves() -> None:
    text = _read(RE_INDEX)
    frontmatter = _frontmatter(text)
    assert frontmatter["extractionPatternsData"] == PATTERNS_PATH
    assert frontmatter["tierDegradationRulesData"] == DEGRADATION_PATH
    data_keys = {key for key in frontmatter if key.endswith("Data")}
    assert data_keys == set(re.findall(r"\{(\w+Data)\}", _body(text))), "a Data key unused, or used undeclared"
    for key in data_keys:
        assert (SRC / frontmatter[key]).is_file(), frontmatter[key]


def test_forge_tier_follows_the_protocol() -> None:
    text = _read(RE_INDEX)
    forge = _slice(text, "**Forge tier (ast-grep available):**", "**Tier degradation handling")
    for phrase in (
        "Follow the **AST Extraction Protocol** in `{extractionPatternsData}` with the bounded scan list from §2 "
        "as the files in scope: the list's file count is the decision tree's input",
        "Run every recipe for the language once over the whole list, not once per file",
        "keep only the matches whose file, relative to `{source_root}` and with forward slashes, is on the list",
        "A run that returns as many matches as its cap (`max_results`, or the CLI template's `| head -N`) may have "
        "dropped some, and step 3 would report each dropped export as removed",
        "until no run fills its cap",
        "the line is `$NAME`'s line (`metaVariables.single.NAME.range.start.line + 1`)",
        "Read by eye the forms the recipes leave out (Known Limitation #11 in `{extractionPatternsData}`)",
        "`find_code` is only the fallback of Known Limitation #4",
    ):
        assert phrase in forge, phrase
    assert "per source file" not in text
    forge_plus = _slice(text, "**Forge+ tier (ast-grep + ccc available):**", "**Deep tier")
    assert "Identical extraction to Forge tier (the AST Extraction Protocol, above)" in forge_plus
    # The recipes run once over the list; the per-file workers build records.
    rules = _slice(text, "## Rules", "## MANDATORY SEQUENCE")
    assert "for AST extraction" not in rules
    assert "when available to build each file's exports (§3)" in rules
    extract = _slice(text, "### 3. Extract Current Exports", "**For each file in the bounded scan list")
    assert "run the recipes over the bounded scan list first (§1)" in extract


def test_tool_resolution_line_names_the_recipes() -> None:
    line = _slice(_read(RE_INDEX), "**Tool resolution:** `gh_bridge`", "\n")
    assert '`find_code_by_rule` with a recipe and `output_format="json"`' in line
    assert f"(`{CLI_COMMAND}`)" in line
    assert "`find_code` only as the fallback of Known Limitation #4" in line
    assert "`find_code`, `find_code_by_rule`" not in line
    assert "qmd_bridge" not in line and "vector_search" not in line


def test_protocol_holds_the_anchors_re_index_cites() -> None:
    patterns = _read(PATTERNS)
    protocol = _slice(patterns, "## AST Extraction Protocol", "### YAML Rule Recipes by Language")
    assert "use the filtered count" in protocol.lower() and "decision tree input" in protocol
    assert "find_code_by_rule(" in protocol and 'output_format="json"' in protocol
    assert f"{CLI_COMMAND} {{path}}" in protocol
    assert "`| head -N`" in protocol and "max_results=" in protocol
    assert "metaVariables.single.NAME.range.start.line + 1" in protocol
    limitations = _slice(patterns, "### Known ast-grep Limitations", "### Re-Export Tracing and Script/Asset Extraction")
    assert "\n4. **Fallback protocol:**" in limitations
    assert "\n11. **Forms the recipes deliberately do not cover" in limitations


def _table(text: str) -> list[dict[str, str]]:
    lines = _slice(text, "| Bridge ", "\n\n").splitlines()
    cells = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    header = cells[0]
    assert all(len(row) == len(header) for row in cells), "a row with another cell count than the header"
    return [dict(zip(header, row)) for row in cells[2:]]


def test_tool_resolution_ast_bridge_rows_name_the_recipes() -> None:
    text = _read(TOOL_RESOLUTION)
    rows = {row["Operation"]: row for row in _table(text) if row["Bridge"] == "`ast_bridge`"}
    scan = rows["`scan_definitions()`"]
    assert scan["Claude Code"].startswith("`mcp__ast-grep__find_code_by_rule` with each recipe, `output_format=\"json\"`")
    assert scan["Claude Code"].endswith("`mcp__ast-grep__find_code` only as the fallback")
    assert scan["CLI"] == f"`{CLI_COMMAND}`"
    co_imports = rows["`detect_co_imports()`"]
    assert co_imports["Claude Code"].startswith("`mcp__ast-grep__find_code_by_rule` with co-import YAML rule")
    assert co_imports["CLI"] == "`ast-grep scan -r {rule_file} --json=stream`"
    for old in ("sg run", "ast-grep -p", "ast-grep run -p"):
        assert old not in text, old
    note = _slice(text, "`scan_definitions()` follows the AST Extraction Protocol", "\n")
    assert "create-skill's `extraction-patterns.md`" in note
    assert "not the priority order below" in note and "Known Limitation #4 fallback" in note


def test_skill_md_names_both_create_skill_files() -> None:
    coupling = _slice(_read(AUDIT_SKILL), "- **Cross-skill data coupling:**", "\n")
    frontmatter = _frontmatter(_read(RE_INDEX))
    assert "`skf-create-skill/references/`" in coupling
    for key in ("extractionPatternsData", "tierDegradationRulesData"):
        assert f"`{key}`" in coupling, key
        assert f"`{Path(frontmatter[key]).name}`" in coupling, frontmatter[key]


# --------------------------------------------------------------------------
# Real ast-grep run: the CLI streaming template over a batch of listed files
# --------------------------------------------------------------------------


def _pinned_version() -> str:
    """The ast-grep-cli version package.json's test:python installs."""
    scripts = json.loads(_read(REPO_ROOT / "package.json"))["scripts"]
    match = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    assert match, "package.json test:python pins no ast-grep-cli version"
    return match.group(1)


PINNED_VERSION = _pinned_version()


def _ast_grep() -> str | None:
    exe = shutil.which("ast-grep")
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return exe if out.returncode == 0 and out.stdout.split()[-1:] == [PINNED_VERSION] else None


AST_GREP = _ast_grep()
needs_ast_grep = pytest.mark.skipif(AST_GREP is None, reason=f"no ast-grep {PINNED_VERSION} binary on PATH")

# Two files of a bounded scan list and one file outside it. A decorated def
# matches at its def line; a method, a nested def and a private name do not
# match.
SOURCE_FILES = {
    "pkg/listed_a.py": "def alpha():\n    pass\n\n\n@decorator\ndef beta(x):\n    return x\n\n\ndef _hidden():\n    pass\n",
    "pkg/listed_b.py": "class Gamma:\n    def method(self):\n        pass\n\n\nasync def delta():\n    def inner():\n        pass\n",
    "pkg/unlisted.py": "def outside():\n    pass\n",
}
BATCH = ["pkg/listed_a.py", "pkg/listed_b.py"]


def _recipe(recipe_id: str) -> str:
    for block in FENCE_RE.findall(_read(PATTERNS)):
        doc = yaml.safe_load(block)
        if isinstance(doc, dict) and doc.get("id") == recipe_id:
            return block
    raise AssertionError(f"no {recipe_id} recipe in {PATTERNS.name}")


@needs_ast_grep
def test_cli_template_over_a_batch_prints_only_the_batch(tmp_path: Path) -> None:
    root = tmp_path / "source"
    for name, body in SOURCE_FILES.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        # bytes, so the sources keep their LF line ends on Windows too
        (root / name).write_bytes(body.encode("utf-8"))
    rule = tmp_path / "scratch" / "recipe.yml"
    rule.parent.mkdir()
    rule.write_text(_recipe("python-public-functions"), encoding="utf-8")
    (code,) = CLI_TEMPLATE_RE.findall(_read(PATTERNS))
    code = (code.replace("{exclude_patterns}", "[]").replace("{recipe_id}", "python-public-functions")
            .replace("{node_kind}", "function_definition"))
    stream = subprocess.run(
        [AST_GREP, "scan", "-r", str(rule), "--json=stream", *BATCH],
        capture_output=True, text=True, encoding="utf-8", check=True, cwd=root,
    ).stdout
    out = subprocess.run([sys.executable, "-c", code], input=stream, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    cited = re.findall(r"^\[AST:(.+?):L(\d+)\] python-public-functions kind=function_definition name=(\w+) ",
                       out, re.M)
    # The list holds forward-slash paths relative to the source root.
    found = sorted((file.replace("\\", "/"), int(line), name) for file, line, name in cited)
    assert found == [("pkg/listed_a.py", 1, "alpha"), ("pkg/listed_a.py", 6, "beta"), ("pkg/listed_b.py", 6, "delta")]
    assert {file for file, _, _ in found} <= set(BATCH)
