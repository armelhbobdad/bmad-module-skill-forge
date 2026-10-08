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
- the snapshot skf-extraction-snapshot.py builds holds every field
  skf-structural-diff.py reads and no temporal field, and the §4 Labels row
  lists only the labels it writes (the prose points at the helper's --help
  for the shape, so there is no second copy of it to drift);
- its sections run 1 to 5 with no gap, and the Forge+ pointer names the ccc
  rename section, which runs in structural-diff.md over the removed exports
  of the saved diff (#589), not over a set difference re-index made by hand.
semantic-diff.md compares what QMD retrieves of the skill with the current
source under {source_root}, so the step has a current side (step 5b
architecture-1).

The AST Extraction Protocol in create-skill's extraction-patterns.md runs the
ast-grep recipes through the recipe runner, with `find_code` only as its
fallback. These tests keep audit and the knowledge base on it:
- re-index.md names the protocol through an `extractionPatternsData` path
  that resolves, has the runner (skf-extract-public-api.py --mode full)
  extract over the bounded scan list with no head cap, after removing the
  JSON an earlier run left, acts on the JSON's `status`, reads by eye only
  what the runner leaves, uses `find_code` only as Known Limitation #4's
  fallback, and every protocol anchor it cites exists; when the runner
  cannot run, the recipes it runs one at a time keep every match too, over
  the files the snapshot left to read (step 5b gate run 2 architecture-2);
- skf-extraction-snapshot.py writes the scan list and builds the snapshot
  (a status per file, the libraries of a stack, the counts §4 shows), and
  the step acts on the line it prints (the files to read, the extraction
  gaps, the files read after an ast-grep failure), so no step opens the
  runner's JSON, copies exports or judges completeness by eye, and a file
  it can read neither way halts instead of looping; run as the prose writes
  them, the commands give a complete snapshot (BMad Builder determinism-2);
- every re-index scans the bounded list of a provenance map: degraded mode,
  its source-tree scan and its exclusion list are gone (enhancement-4);
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

import importlib.util
import json
import re
import shlex
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
STRUCTURAL_DIFF = AUDIT / "references" / "structural-diff.md"
AUDIT_SKILL = AUDIT / "SKILL.md"
PATTERNS = SRC / "skf-create-skill" / "references" / "extraction-patterns.md"
TOOL_RESOLUTION = SRC / "knowledge" / "tool-resolution.md"
DIFF_HELPER = SRC / "shared" / "scripts" / "skf-structural-diff.py"
EXTRACT = SRC / "shared" / "scripts" / "skf-extract-public-api.py"
SNAPSHOT_HELPER = SRC / "shared" / "scripts" / "skf-extraction-snapshot.py"

PATTERNS_PATH = "skf-create-skill/references/extraction-patterns.md"
DEGRADATION_PATH = "skf-create-skill/references/tier-degradation-rules.md"
SNAPSHOT_WRITE = "**The snapshot.** The command writes `{forge_version}/extraction-snapshot.json`"
CLI_COMMAND = "ast-grep scan -r {recipe_file} --json=stream"
# The fields skf-structural-diff.py keeps from a snapshot export (#561).
READ_BY_DIFF = ("name", "type", "signature", "file", "line", "confidence", "extraction_method")

FENCE_RE = re.compile(r"^```yaml\n(.*?)^```", re.M | re.S)

_spec = importlib.util.spec_from_file_location("skf_extraction_snapshot_for_reindex", SNAPSHOT_HELPER)
SNAPSHOT_MOD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SNAPSHOT_MOD)
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


def _after_snapshot(text: str) -> str:
    """The text after the §3 paragraph that names the written snapshot."""
    assert text.count(SNAPSHOT_WRITE) == 1, "the snapshot paragraph is not found exactly once"
    return text[text.index(SNAPSHOT_WRITE) + len(SNAPSHOT_WRITE):]


def _helper_snapshot(tmp_path: Path) -> dict:
    """A snapshot skf-extraction-snapshot.py builds from one runner export and
    one export read by eye."""
    root = tmp_path / "source"
    for name in ("pkg/a.py", "pkg/b.py"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"")
    runner = {"status": "ok", "exports": [
        {"export_name": "a", "source_file": "pkg/a.py", "source_line": 1, "signature": "def a(x: int) -> int:",
         "export_type": "function", "confidence": "T1", "extraction_method": "ast-grep",
         "ast_node_type": "function_definition"}],
        "file_issues": [{"file": "pkg/b.py", "issue": "syntax-errors", "count": 1, "line": 1}]}
    details = [{"name": "b", "file": "pkg/b.py", "line": 2, "type": "class", "signature": "class b:"}]
    provenance = {"entries": [{"export_name": n, "source_file": f"pkg/{n}.py"} for n in ("a", "b")]}
    return SNAPSHOT_MOD.build(root, "Forge", "t", provenance, runner, ["pkg/b.py"], details)


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


def test_semantic_diff_compares_the_skill_with_the_current_source() -> None:
    # Step 5b architecture-1: QMD only retrieves what the skill documents, so
    # §3's current side is the source under {source_root}, never QMD again.
    compare = _slice(_read(SEMANTIC_DIFF), "### 3. Compare Knowledge Context", "### 4.")
    assert "against the current source under `{source_root}` (item 3)" in compare


def test_nothing_is_added_to_the_snapshot_after_it_is_written() -> None:
    after = _after_snapshot(_read(RE_INDEX))
    mentions = [s for s in _sentences(after) if "snapshot" in s.lower()]
    assert mentions, "no sentence after the schema mentions the snapshot"
    for sentence in mentions:
        assert not re.search(r"\b(append|add|enrich|attach)", sentence, re.I), sentence


def test_snapshot_schema_holds_what_structural_diff_reads(tmp_path: Path) -> None:
    snapshot = _helper_snapshot(tmp_path)
    assert "temporal" not in json.dumps(snapshot)
    for export in snapshot["exports"]:
        for key in READ_BY_DIFF:
            assert export.get(key) is not None, f"the snapshot export lacks {key}: {export}"
    # Against an empty baseline the diff reports every export as added, in
    # the record it builds from the fields it reads, so a field the snapshot
    # holds under a name the diff does not read comes back null.
    baseline = tmp_path / "baseline.json"
    path = tmp_path / "extraction-snapshot.json"
    baseline.write_text(json.dumps({"exports": []}), encoding="utf-8")
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(DIFF_HELPER), str(baseline), str(path)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode in (0, 1) and result.stdout.strip(), result.stderr
    added = json.loads(result.stdout)["added"]
    assert len(added) == 2
    for record in added:
        for key in READ_BY_DIFF:
            assert record.get(key) is not None, f"the helper reads {key} under another name"
    # The prose points at the helper for the shape, never a copy of it.
    paragraph = _slice(_read(RE_INDEX), SNAPSHOT_WRITE, "\n")
    assert "`skf-extraction-snapshot.py --help` gives the full shape" in paragraph
    assert '"source_root": "{source_path}"' not in _read(RE_INDEX)


def test_labels_row_lists_only_the_snapshot_labels(tmp_path: Path) -> None:
    labels = sorted({(e["confidence"], e["extraction_method"]) for e in _helper_snapshot(tmp_path)["exports"]})
    assert labels == [("T1", "ast-grep"), ("T1-low", "source-read")]
    row = _slice(_read(RE_INDEX), "| Labels |", "\n")
    assert re.findall(r"\} (T1(?:-low)?) \(`([a-z-]+)`\)", row) == labels
    assert row.rstrip().endswith("T1-low (`source-read`) |"), row


def test_sections_run_one_to_five_and_the_ccc_pointer_resolves() -> None:
    text = _read(RE_INDEX)
    headings = re.findall(r"^### (\w+)\. (.+)$", text, re.M)
    assert [number for number, _ in headings] == ["1", "2", "3", "4", "5"]
    assert "ccc search" not in text and "CCC Rename Detection" not in text
    forge_plus = _slice(text, "**Forge+ tier (ast-grep + ccc available):**", "**Deep tier")
    assert "CCC rename detection runs in step 3 (`structural-diff.md` §1b)" in forge_plus
    assert "4b" not in text
    # The pass it points at exists, and starts from the saved diff's removed[].
    ccc = _slice(_read(STRUCTURAL_DIFF), "### 1b. Find Relocated Exports (Forge+ and Deep with ccc)", "### 2.")
    assert "each `removed[]` entry of `{auditDataFolder}/structural-diff.json`" in ccc


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
        "The recipe runner extracts, as the **AST Extraction Protocol** in `{extractionPatternsData}` says",
        "one `skf-extract-public-api.py --mode full` call over the bounded scan list from §2",
        "keeps every match (`--head-cap 0`: a match past a cap would read as a removed export in step 3)",
        "never run the recipes one at a time, batch them, or merge and dedupe their matches by hand",
        "line (`$NAME`'s line, as create-skill records it",
        "the declaration on one line even when a formatter split its parameters over several",
        "Read by eye only what the runner leaves (§3): the forms the recipes leave out (Known Limitation #11 in "
        "`{extractionPatternsData}`)",
    ):
        assert phrase in forge, phrase
    assert "per source file" not in text
    forge_plus = _slice(text, "**Forge+ tier (ast-grep + ccc available):**", "**Deep tier")
    assert "Identical extraction to Forge tier (the AST Extraction Protocol, above)" in forge_plus
    rules = _flow(_slice(text, "## Rules", "## MANDATORY SEQUENCE"))
    assert "At Forge, Forge+ and Deep the recipe runner extracts; read by eye only what it leaves (§3)" in rules
    assert "never judge completeness by eye" in rules


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
    """The coupling bullet names each create-skill file re-index.md's frontmatter
    loads; the Sibling skills rule says where such a path resolves (#601)."""
    skill = _read(AUDIT_SKILL)
    coupling = _slice(skill, "- **Cross-skill data coupling:**", "\n")
    frontmatter = _frontmatter(_read(RE_INDEX))
    assert "`skf-create-skill/references/`" in coupling
    for key in ("extractionPatternsData", "tierDegradationRulesData"):
        assert frontmatter[key].startswith("skf-create-skill/references/"), key
        assert f"`{Path(frontmatter[key]).name}`" in coupling, frontmatter[key]
    assert "- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`)" in skill


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


# --------------------------------------------------------------------------
# BMad Builder determinism-2 (#589): the runner extracts, a script builds the snapshot
# --------------------------------------------------------------------------


HELPERS = {"{extractPublicApiHelper}": EXTRACT, "{extractionSnapshotHelper}": SNAPSHOT_HELPER}


def _flow(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _blocks(section: str) -> list[list[str]]:
    """Each fenced bash block of `section`, as its logical lines (a trailing
    backslash continues a line)."""
    out = []
    for block in re.findall(r"^[ \t]*```bash\n(.*?)^[ \t]*```", section, re.M | re.S):
        out.append([line.strip() for line in block.replace("\\\n", " ").splitlines() if line.strip()])
    return out


def test_the_runner_call_starts_from_a_removed_json() -> None:
    """The protocol reads any JSON at -o after the call as the call's own
    (extraction-patterns.md), so the runner block removes it first, then
    reads the scan list the helper wrote, with no head cap."""
    section = _slice(_read(RE_INDEX), "### 3. Extract Current Exports", "**2. Build the snapshot.**")
    (lines,) = _blocks(section)
    assert lines[0] == 'rm -f "{auditDataFolder}/extraction.json"', lines[0]
    call = _flow(lines[1])
    assert call.startswith("uv run {extractPublicApiHelper} --mode full --source-root \"{source_root}\"")
    assert "--head-cap 0" in call and call.endswith('-o "{auditDataFolder}/extraction.json"')
    assert '--files-from "{auditDataFolder}/scan-files.json"' in call
    flow = _flow(section)
    assert ("Never open the JSON: item 2's helper reads it and prints what this step acts on, its `status` "
            "included (never the exit code)") in flow
    build = _flow(_slice(_read(RE_INDEX), "**2. Build the snapshot.**", "**3. What the runner leaves.**"))
    for status in ("**`runner_status` is `incomplete`**", "**`runner_status` is `no-ast-grep`, or null at Forge "
                   "tier and above** (no JSON at `-o` after the call"):
        assert status in build, status


def test_the_fallback_keeps_every_match() -> None:
    """When the runner cannot run, re-index borrows create-skill's by-hand protocol with the audit's own inputs: the
    files `to_read` lists size the Decision Tree, and neither the MCP tool's `max_results` nor the CLI template's
    `| head` caps a recipe, in a directory batch or a Known Limitation #4 retry either, since a match past a cap
    would read as a removed export in step 3."""
    build = _flow(_slice(_read(RE_INDEX), "**2. Build the snapshot.**", "**3. What the runner leaves.**"))
    fallback = _slice(build, "**`runner_status` is `no-ast-grep`", "- **`to_read`")
    for token in ("Follow **When the Runner Cannot Run** in `{extractionPatternsData}` over the files in `to_read`, "
                  "with this audit's parameters in place of create-skill's",
                  "the files in scope are those `to_read` lists, and their count is the Decision Tree's input (not "
                  "create-skill's step 3 count)",
                  "Keep every match, in every directory batch and every retry:",
                  "pass `find_code_by_rule` a `max_results` that no recipe can reach (100000), and a Known "
                  "Limitation #4 `find_code` retry the same",
                  "drop the `| head -{HEAD_CAP}` from the CLI streaming template, in each batch,",
                  "a match past a cap reads as a removed export in step 3",
                  "Record each export as item 3 does, T1 with `ast-grep` for one the recipes match."):
        assert token in fallback, token
    # the parameters it overrides are the ones the protocol sets
    patterns = _read(PATTERNS)
    assert "### Decision Tree" in patterns and "max_results=150" in patterns
    assert "cap per-batch output" in patterns and "with the same head cap" in patterns
    assert "max_results=100," in _read(PATTERNS.with_name("extraction-patterns-by-hand.md"))  # Known Limitation #4
    assert CLI_TEMPLATE_RE.search(patterns), "the CLI streaming template no longer ends in | head -{HEAD_CAP}"
    assert "use the filtered count from step 3 section 2" in patterns


def test_the_scan_list_and_the_snapshot_come_from_the_helper() -> None:
    text = _read(RE_INDEX)
    scan = _slice(text, "### 2. Build Bounded Scan List", "### 3. Extract Current Exports")
    (lines,) = _blocks(scan)[:1]
    assert lines == ['mkdir -p "{auditDataFolder}"',
                     'uv run {extractionSnapshotHelper} scan-list "{provenanceMap}" -o "{auditDataFolder}/scan-files.json"']
    assert "never retype it" in scan
    build = _slice(text, "**2. Build the snapshot.**", "**3. What the runner leaves.**")
    (block,) = _blocks(build)
    call = _flow(block[0])
    assert call.startswith("uv run {extractionSnapshotHelper} build")
    assert '--source-path "{source_path}"' in call
    # Every skill that reaches re-index has a provenance map (degraded mode is gone).
    assert ' --provenance-map "{provenanceMap}" ' in call and "[--provenance-map" not in call
    assert '[--details "{auditDataFolder}/export-details-{n}.json"]...' in call
    assert call.endswith('-o "{forge_version}/extraction-snapshot.json"')
    flow = _flow(build)
    assert "Step 3 never reads an incomplete snapshot" in flow
    # The step acts on the printed line, and a file it can read neither way halts.
    for field in ("`runner_status`", "`to_read`", "`extraction_gaps`", "`complete`"):
        assert field in flow, field
    assert ('When `complete` is still false, the files `to_read` lists could not be read: HALT with **exit 3**, '
            '`halt_reason: "source-unreadable"`') in flow
    # The by-eye workers hand back records, one file each, never the snapshot.
    leaves = _flow(_slice(text, "**3. What the runner leaves.**", SNAPSHOT_WRITE))
    assert 'returns ONLY `{"files": [...], "exports": [...]}`' in leaves
    assert "`{auditDataFolder}/export-details-{n}.json`" in leaves and "never merged by hand" in leaves
    for read in ("each file in `to_read`", "each name in `extraction_gaps`"):
        assert read in leaves, read
    assert "the snapshot helper gives each one its file's `source_library`" in leaves
    assert "looked up once per file in the provenance map's `entries[]`" not in text
    assert "`{auditDataFolder}/export-details.json`" not in text


def test_a_baseline_gap_is_read_with_the_kind_its_declaration_has() -> None:
    """#682: the build lists the map's entries the runner leaves out (a
    dunder, a module) while their file still declares them. The worker
    records each at its line with the map's kind only while the declaration
    still has it, so a real kind change still reaches step 3; it says what
    a module, a package and a renaming alias record. One by-eye pass: a gap
    the reader cannot place is a warning, never a second loop."""
    text = _read(RE_INDEX)
    forge = _flow(_slice(text, "**Forge tier (ast-grep available):**", "**Tier degradation handling"))
    assert ("the provenance map's entries the runner leaves out (an underscore name such as `__version__`, a "
            "module) that the source still declares") in forge
    build = _flow(_slice(text, "**2. Build the snapshot.**", "**3. What the runner leaves.**"))
    assert ("Item 3 reads the gaps once: when `complete` is true and `extraction_gaps` still lists a name after "
            "that read (one the reader could not place), warn \"**Extraction gap:** {name} ({file}:{line}) was not "
            "found by eye; step 3 reports it as removed.\" for each and go on to §4 without reading again") in build
    leaves = _flow(_slice(text, "**3. What the runner leaves.**", SNAPSHOT_WRITE))
    assert ("a gap whose `entry` is null is a provenance map entry the runner leaves out (an underscore name such "
            "as `__version__`, a module) that its file still declares") in leaves
    for rule in (
        "as `type`, its `export_type` when the declaration at that line still has that kind, else the kind it has "
        "now (a `variable` now declared by a `def` is a `function`, which step 3 reports as a changed kind)",
        "when the gap gives no `export_type`, the kind the declaration has",
        "the import line for an alias that renames",
        "for a module or package (a gap at line 1 of a file the name is the module or package of) `module` and "
        "the file's path from `{source_root}` without its extension or a final `__init__` or `index`",
    ):
        assert rule in leaves, rule


def test_re_index_always_scans_the_bounded_list() -> None:
    """Degraded mode is gone (BMad Builder enhancement-4): step 1 stops a
    skill without a provenance map, so re-index never scans the whole source
    tree and keeps no exclusion list of its own."""
    text = _read(RE_INDEX)
    assert "degraded" not in text.lower()
    scan = _flow(_slice(text, "### 2. Build Bounded Scan List", "### 3. Extract Current Exports"))
    assert ("Every skill that reaches this step has a provenance map: step 1 stops a skill without one, and "
            "sends a compose-mode stack and a docs-only skill around this step") in scan
    for gone in ("--language", "--exclude", "**/node_modules/**", "Scan mode"):
        assert gone not in text, gone


def test_the_summary_takes_its_counts_from_the_snapshot() -> None:
    summary = _flow(_slice(_read(RE_INDEX), "### 4. Validate Extraction Completeness", "### 5."))
    assert ("Take every value from the snapshot (`files_by_status`, `counts`, `cap_hits`) and the build's line "
            "(`ast_fallback_files`), never a recount") in summary
    assert "{hash-tracked} tracked by hash" in summary
    for slot in ("{files_scanned}", "{counts.exports}", "counts.by_type", "{t1_count}", "{t1_low_count}"):
        assert slot in summary, slot


def _prose_words(line: str, values: dict[str, str]) -> list[str]:
    """A prose command as argv: optional groups kept or dropped as `keep`
    says, placeholders filled after the split."""
    words = shlex.split(line)
    out = []
    for word in words:
        for name, value in values.items():
            word = word.replace(name, value)
        out.append(word)
    return out


def _run_line(line: str, values: dict[str, str], keep: set[str]) -> subprocess.CompletedProcess:
    def group(m: re.Match) -> str:
        return m.group(1) if m.group(1).split()[0] in keep else ""
    line = re.sub(r"\[(--[^\[\]]+)\](?:\.\.\.)?", group, line)
    words = _prose_words(line, values)
    assert words[:2] == ["uv", "run"] and words[2] in [str(p) for p in HELPERS.values()], words[:3]
    return subprocess.run([sys.executable, *words[2:]], capture_output=True, text=True, encoding="utf-8",
                          timeout=300, check=False)


@needs_ast_grep
def test_the_prose_commands_build_a_complete_snapshot(tmp_path: Path) -> None:
    """Steps 2 §2 and §3 as written: the scan list, the runner, the
    snapshot. A deleted file is `missing`, a split signature arrives on one
    line, and nothing was read by eye, so the snapshot is complete."""
    root = tmp_path / "source"
    for name, body in {"pkg/api.py": "def fetch(\n    url: str,\n) -> bytes:\n    return b''\n",
                       "pkg/util.py": "def helper(x: int) -> int:\n    return x\n"}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(body.encode("utf-8"))
    forge = tmp_path / "forge" / "demo" / "1.0.0"
    data = forge / ".skf-audit" / "20260101-000000"
    provenance = forge / "provenance-map.json"
    provenance.parent.mkdir(parents=True)
    provenance.write_bytes(json.dumps({"entries": [
        {"export_name": n, "source_file": f, "source_line": 1} for n, f in
        [("fetch", "pkg/api.py"), ("helper", "pkg/util.py"), ("gone", "pkg/gone.py")]]}).encode("utf-8"))
    values = {"{auditDataFolder}": str(data), "{provenanceMap}": str(provenance), "{source_root}": str(root),
              "{source_path}": str(root), "{forge_version}": str(forge), "{tier}": "Forge",
              "{timestamp}": "20260101-000000",
              **{name: str(path) for name, path in HELPERS.items()}}
    text = _read(RE_INDEX)
    mkdir, scan_list = _blocks(_slice(text, "### 2. Build Bounded Scan List", "### 3."))[0]
    data.mkdir(parents=True)
    assert _run_line(scan_list, values, set()).returncode == 0
    runner = _blocks(_slice(text, "### 3. Extract Current Exports", "**2. Build the snapshot.**"))[0][1]
    result = _run_line(runner, values, set())
    assert json.loads((data / "extraction.json").read_text(encoding="utf-8"))["status"] == "ok", result.stderr
    build = _blocks(_slice(text, "**2. Build the snapshot.**", "**3. What the runner leaves."))[0][0]
    result = _run_line(build, values, {"--extraction"})
    line = json.loads(result.stdout)
    assert (result.returncode, line["complete"], line["runner_status"]) == (0, True, "ok"), (
        result.stdout + result.stderr)
    assert (line["to_read"], line["extraction_gaps"], line["ast_fallback_files"]) == ([], [], [])
    snapshot = json.loads((forge / "extraction-snapshot.json").read_text(encoding="utf-8"))
    assert {f["file"]: f["status"] for f in snapshot["files"]} == {
        "pkg/api.py": "extracted", "pkg/gone.py": "missing", "pkg/util.py": "extracted"}
    by_name = {e["name"]: e for e in snapshot["exports"]}
    assert by_name["fetch"]["signature"] == "def fetch(url: str) -> bytes:"
    assert by_name["fetch"]["confidence"] == "T1" and snapshot["counts"]["t1"] == 2
