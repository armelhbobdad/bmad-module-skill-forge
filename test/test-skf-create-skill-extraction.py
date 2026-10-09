#!/usr/bin/env python3
"""Prose pins: create-skill extracts through the recipe runner and repairs
provenance through the verifier (#584, and the #556 pre-release fix for the
AST extraction protocol, create-skill part).

extract.md §4 held its own copy of the AST decision tree, and the copy had
drifted from the protocol in extraction-patterns.md: it sent a small scope
to `find_code` with text output, prescribed `ast-grep run -p`, keyed the
tree on step 1's file count and had no `.vue` branch. §4b read the entry
points and diffed the sets by eye, and compile §4 counted the public API by
hand. validate §7a had the model rewrite citation prefixes and move source
lines itself, and compile §4 and validate §7 each carried the relabel rule.
These tests keep the steps on the scripts:

- extract §4 runs the tier Strategy and the AST Extraction Protocol, whose
  recipe runner is `skf-extract-public-api.py --mode full`, with a call the
  runner's parser accepts, after a `mkdir -p` of the folder its JSON goes
  to (the runner creates none, and the staging folder comes at step 5) and
  an `rm -f` of the JSON an earlier run left there; it holds no copy of the
  decision tree and keeps only the AST-unavailable warning, the per-file
  fallback, co-import detection and the re-export tracing pointer;
- a call that leaves no JSON, and a brief whose language no recipe reads,
  go where the protocol's When the Runner Cannot Run sends them: the
  recipes by hand, or source reading;
- §2 builds the filtered file list by hand only where a step reads it, and
  §4b and §5 read the runner's entry-point diff, aggregates and truncation
  flag, and compile §4 its counts and arms, never a hand count;
- step 3d's component-library runner writes to the same {extraction_json},
  which §2b binds and removes for every brief, outside the scratch folder
  step 3d removes, so §5's `init` seeds a component library's inventory and
  extraction rules from it too, and step 3d acts on its `status`, never its
  exit code (step 5b determinism-1);
- the protocol runs the runner where a step gives its command, so a step
  that gives none (audit-skill's re-index) still runs the recipes; a CCC
  ranking orders only the files read one at a time, which every file that
  describes it says;
- validate §7a removes the JSON an earlier run left, runs `verify -o` and
  then `fix` on that JSON, and triages every `why` the fix can leave;
- the relabel rule is written once, in relabel-rule.md, which only a label
  violation loads (extraction-patterns.md keeps a one-line Relabel Rule
  section naming it, so every pointer at the rule still resolves), and its
  node kind lookup is a `kind-at` call that fits the verifier, given a
  patterns path that resolves from {project-root} in every step that binds it.

The documented verify and fix calls repair a staged skill. The documented
runner call that fails on its input leaves no JSON, so a stale one is never
read. With the pinned ast-grep on PATH, the documented runner call extracts
a small tree (a top-level `test_x.py` falls to `**/test_*`), reads no file
of a `language: java` brief, every runner field the prose reads is in its
JSON, a public name past the head cap comes back as an extraction gap, the
documented step 3d call's JSON seeds a component library's inventory and
extraction rules, and the relabel rule's `kind-at` call finds the recipe's
kind.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import fnmatch
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
REFS = SRC / "skf-create-skill" / "references"
EXTRACT = REFS / "extract.md"
COMPONENT = REFS / "component-extraction.md"
COMPILE = REFS / "compile.md"
VALIDATE = REFS / "validate.md"
PATTERNS = REFS / "extraction-patterns.md"
RELABEL = REFS / "relabel-rule.md"
KNOWLEDGE = SRC / "knowledge"
SCRIPTS = SRC / "shared" / "scripts"
RUNNER = SCRIPTS / "skf-extract-public-api.py"
VERIFIER = SCRIPTS / "skf-verify-provenance-completeness.py"
INVENTORY = SCRIPTS / "skf-extraction-inventory.py"

# every step that binds the patterns file binds it to a path that resolves
# from {project-root}, where `kind-at` reads it, as update-skill's write.md does
PATTERNS_PROBE = ["{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md",
                  "{project-root}/src/skf-create-skill/references/extraction-patterns.md"]
RUNNER_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py",
                "{project-root}/src/shared/scripts/skf-extract-public-api.py"]
VERIFIER_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py",
                  "{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py"]
STAGE = "{project-root}/_bmad-output/.skf-stage/"
RUNNER_CALL = "uv run {extractPublicApiHelper} --mode full"
# the runner writes -o into a folder it does not create, and at step 3 the
# staging folder (step 5) does not exist yet
MKDIR_CALL = 'mkdir -p "{project-root}/_bmad-output/.skf-stage"'
# each JSON sits at one path per skill name, so a run first removes the one an
# earlier run left: a JSON there after the call is then this call's
RM_EXTRACTION = 'rm -f "{extraction_json}"'
RM_VERIFY = 'rm -f "{verify_json}"'
VERIFY_CALL = "uv run {verifyProvenanceCompletenessHelper} verify"
FIX_CALL = "uv run {verifyProvenanceCompletenessHelper} fix"
KIND_AT_CALL = "uv run {verifyProvenanceCompletenessHelper} kind-at"
FENCE_RE = re.compile(r"^[ \t]*```bash\n(.*?)^[ \t]*```", re.M | re.S)
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z][\w-]*\}|<[a-z][\w-]*>")
TOKEN_RE = re.compile(r"`([a-z_]+(?:\[\])?(?:\.[a-z_0-9]+(?:\[\])?)*)`")
# The relabel rule's own sentences: each is written once, in relabel-rule.md.
RELABEL_RULE = (
    "follow its `extraction_method`, never the reverse",
    "so `direct-read` becomes `source-read`",
    "T1 needs evidence that an ast-grep rule matched",
)
# What a CCC ranking was said to do before the runner: none of it holds now.
CCC_CLAIMS = (
    "pre-rank the file extraction queue",
    "pre-ranks the file extraction queue",
    "extraction will prioritize these first",
    "most relevant files first",
    "pre-ranks files before AST extraction",
    "improved extraction coverage",
    "pre-ranked extraction",
    "narrows the file set before ast-grep runs",
    "changes nothing it extracts",
)
RESOLVE_VERIFIER = ("resolving `{verifyProvenanceCompletenessHelper}` ← first existing path in "
                    "`{verifyProvenanceCompletenessProbeOrder}` for its `kind-at` lookup")


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


def _section(path: Path, number: str) -> str:
    """A `### <number>. ` section of a step file, up to the next `### ` heading."""
    text = _read(path)
    start = f"\n### {number}. "
    assert text.count(start) == 1, f"{path.name}: no single section {number}"
    i = text.index(start) + 1
    j = text.find("\n### ", i)
    return text[i:j if j != -1 else len(text)]


def _commands(text: str) -> list[list[str]]:
    """The commands of each fenced bash block in `text`, each with its
    backslash continuations joined."""
    blocks = []
    for block in FENCE_RE.findall(text):
        commands, current = [], []
        for line in (line.strip() for line in block.strip().splitlines()):
            current.append(line[:-1].strip() if line.endswith("\\") else line)
            if not line.endswith("\\"):
                commands.append(" ".join(current))
                current = []
        assert not current, f"a fenced command ends in a backslash: {current}"
        blocks.append(commands)
    return blocks


def _call(text: str, prefix: str) -> str:
    """The one fenced bash command in `text` that starts with `prefix`."""
    calls = [command for block in _commands(text) for command in block if command.startswith(prefix)]
    assert len(calls) == 1, f"expected one fenced call starting {prefix!r}, found {len(calls)}"
    return calls[0]


def _block(text: str, prefix: str) -> list[str]:
    """The one fenced bash block in `text` holding a command that starts with `prefix`."""
    blocks = [block for block in _commands(text) if any(c.startswith(prefix) for c in block)]
    assert len(blocks) == 1, f"expected one fenced block with {prefix!r}, found {len(blocks)}"
    return blocks[0]


def _binding(text: str, name: str) -> str:
    """What the prose binds `{name}` to: `{name}` ← `<value>`."""
    found = re.findall(r"`\{" + re.escape(name) + r"\}` ← `([^`]+)`", text)
    assert len(found) == 1, f"expected one binding of {{{name}}}, found {found}"
    return found[0]


def _extraction_json() -> str:
    """The runner JSON's path, which §2b's start clean binds for §4 and step 3d."""
    return _binding(_section(EXTRACT, "2b"), "extraction_json")


def _fill(command: str, values: dict[str, str]) -> list[str]:
    """The shell words of `command` with each placeholder replaced."""
    names = {m.group(0) for m in PLACEHOLDER_RE.finditer(command)}
    missing = sorted(n for n in names if n[1:-1] not in values)
    assert not missing, f"no value for {missing} in {command!r}"
    for name in names:
        command = command.replace(name, values[name[1:-1]])
    return shlex.split(command)


def _rm(command: str, values: dict[str, str]) -> None:
    """Carry out a documented `rm -f <file>` the way the shell would."""
    words = _fill(command, values)
    assert words[:2] == ["rm", "-f"] and len(words) == 3, words
    Path(words[2]).unlink(missing_ok=True)


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER_MOD = _module("skf_create_extraction_runner", RUNNER)
VERIFIER_MOD = _module("skf_create_extraction_verifier", VERIFIER)


def _parses(parser, words: list[str]) -> None:
    """The words after `uv run <script>` parse with the script's own parser."""
    assert words[:2] == ["uv", "run"], words
    parser.parse_args(words[3:])


def _run(words: list[str], script: Path, cwd: Path) -> subprocess.CompletedProcess:
    """Run a documented `uv run <script> ...` call with this interpreter."""
    return subprocess.run([sys.executable, str(script), *words[3:]], capture_output=True, text=True,
                          encoding="utf-8", cwd=cwd, check=False)


def _cannot_run() -> str:
    """The protocol's When the Runner Cannot Run section."""
    return _slice(_read(PATTERNS), "### When the Runner Cannot Run", "### Known ast-grep Limitations")


# --------------------------------------------------------------------------
# extract §4: the tier Strategy, the protocol and the runner, no tree copy
# --------------------------------------------------------------------------


def test_extract_binds_the_runner() -> None:
    text = _read(EXTRACT)
    frontmatter = _frontmatter(text)
    assert frontmatter["extractPublicApiProbeOrder"] == RUNNER_PROBE
    assert (REPO_ROOT / RUNNER_PROBE[1].removeprefix("{project-root}/")).is_file()
    # step 3 binds the patterns file as steps 5 and 6 do, so no step-relative path carries over
    assert "extractionPatternsData" not in frontmatter
    assert frontmatter["extractionPatternsDataProbeOrder"] == PATTERNS_PROBE
    assert ("Resolve `{extractionPatternsData}` ← first existing path in `{extractionPatternsDataProbeOrder}` "
            f"and load it up to its `{CUT}` heading") in _section(EXTRACT, "1")


def test_section_4_runs_the_protocol_through_the_runner() -> None:
    four = _section(EXTRACT, "4")
    opening = four.split("\n\n")[1]
    for phrase in ("Run the Strategy for the current tier from `{extractionPatternsData}`",
                   "the **AST Extraction Protocol** there, whose recipe runner reads `{source_root}` itself",
                   "A branch that extracts without the runner (source reading, or the protocol's fallback) "
                   "reads the §2 filtered file list: build it first, from `{source_root}`, when §2 did not",
                   "Label each export by the tool that produced it"):
        assert phrase in opening, phrase
    call = _call(four, RUNNER_CALL)
    for flag in ('--source-root "{source_root}"', '--brief "{brief_path}"', '--tier "{tier}"',
                 '-o "{extraction_json}"'):
        assert flag in call, flag
    words = _fill(call, {"extractPublicApiHelper": "runner.py", "source_root": "src", "brief_path": "brief.yaml",
                         "tier": "Forge", "extraction_json": "out.json"})
    _parses(RUNNER_MOD._build_parser(), words)
    # every tier create-skill records is one the runner takes for its head cap
    tiers = re.findall(r"`(Quick|Forge\+?|Deep)`", _read(REFS / "load-brief.md"))
    assert set(tiers) == set(RUNNER_MOD.TIERS), tiers
    assert "resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}`" in four
    # the runner's JSON sits beside the staging folder, never in the skill; §2b binds it
    assert _extraction_json() == STAGE + "{skill-name}.extraction.json"
    assert "`{extraction_json}` ←" not in four
    assert ("it writes `{extraction_json}` (bound in §2b, beside the staging folder step 5 creates, never inside "
            "the skill)") in four
    # the step acts on the JSON, never on the exit code, and points at the one list of fallback cases
    assert ("A JSON at `{extraction_json}` after the call is this call's: read it, in parts when it is large, "
            "and act on its `status` and fields") in four
    assert "never on the exit code" in four and "exits 2 or 3" not in four
    assert ("When no path resolves, or a case the protocol's **When the Runner Cannot Run** lists applies, such "
            "as no JSON at `{extraction_json}` after the call or an empty `scope.languages` (no recipe reads the "
            "brief's language), follow that section.") in four


def test_section_4_makes_the_folder_and_removes_a_stale_json() -> None:
    """At step 3 the staging folder does not exist yet, and the runner's -o
    creates no folder: the documented mkdir, in the runner's block and before
    it, makes the folder {extraction_json} sits in. The path is the same on
    every run of a skill, so the block removes the JSON an earlier run left
    before the call."""
    four = _section(EXTRACT, "4")
    block = _block(four, RUNNER_CALL)
    assert block[:2] == [MKDIR_CALL, RM_EXTRACTION] and block[2].startswith(RUNNER_CALL), block
    folder = shlex.split(MKDIR_CALL)[2]
    assert _extraction_json().rpartition("/")[0] == folder
    assert ("create that folder (the runner creates no folder) and remove the JSON an earlier run left there, "
            "then call the runner") in four


def test_section_4_holds_no_copy_of_the_decision_tree() -> None:
    four = _section(EXTRACT, "4")
    for gone in ("find_code()", 'output_format="text"', "ast-grep run -p", "step 1's file tree", "≤100", "≤500",
                 ">500", "EXCLUDES", "head -N", "max_results", "1. Detect language", "**Quick Tier (No AST tools):**",
                 "gh_bridge.list_tree", "Build extraction rules YAML", "decision tree"):
        assert gone not in four, gone


def test_section_4_keeps_what_the_protocol_does_not_say() -> None:
    four = _section(EXTRACT, "4")
    unavailable = _slice(four, "**If AST tools are unavailable at Forge, Forge+ or Deep tier**",
                         "Degrade to Quick tier extraction.")
    assert "`{tierDegradationRulesData}`" in unavailable and "Run [SF] Setup Forge" in unavailable
    failures = _slice(four, "**For each file, handle failures gracefully:**", "**Re-export tracing")
    assert "(the runner lists each one in `file_issues`): fall back to source reading for that file" in failures
    co_imports = _slice(four, "**Co-import detection (Forge tier and above):**", "\n")
    assert "`ast_bridge.detect_co_imports(path, libraries[])`" in co_imports
    tracing = _slice(four, "**Re-export tracing (Forge tier and above):**", "\n")
    for token in ("**Re-Export Tracing** protocol in `{extractionPatternsTracingData}`", "`entry_points.unresolved`",
                  "`entry_point_diff.extraction_gaps` name with no `file`"):
        assert token in tracing, token
    truncated = _slice(four, "**When `truncated` is true,**", "\n")
    assert "keep the warning for §6 and the evidence report" in truncated
    assert "{each `recipes[]` id whose `truncated` is true} matched more than {head_cap} exports" in truncated
    # what a capped run loses, as test_a_capped_public_name_comes_back_as_a_gap shows
    assert "a public name among them comes back as an extraction gap (§4b), read by eye" in truncated
    assert "Narrow `scope.include` in the brief until no recipe reaches the cap." in truncated


def test_ccc_ranking_orders_the_files_read_one_at_a_time() -> None:
    """The runner reads every file in scope in one call and keeps a capped
    recipe's matches in file and line order, so a CCC ranking orders only the
    files read one at a time. The patterns file says so once, and no file
    that describes the ranking claims more."""
    integration = _slice(_read(EXTRACT), "**CCC Discovery Integration (Forge+ and Deep with ccc only):**", "### 2a.")
    assert ("§4 and §4b read the files they read one at a time in its order, as the CCC Pre-Ranking Strategy in "
            "`{extractionPatternsData}` says") in integration
    assert ("Display: \"**CCC discovery: {N} files ranked by semantic relevance.** Files read one at a time "
            "follow this order.\"") in integration
    ranking = _slice(_read(PATTERNS), "### CCC Pre-Ranking Strategy", "### ast-grep Patterns")
    assert ("rank the files extraction reads one at a time: those the recipe runner leaves to source reading (its "
            "`file_issues`, its extraction gaps and the files of a language no recipe reads), or the filtered file "
            "list when extraction runs without the runner") in ranking
    describers = [EXTRACT, PATTERNS, REFS / "sub" / "ccc-discover.md", REFS / "load-brief.md",
                  KNOWLEDGE / "ccc-bridge.md", KNOWLEDGE / "progressive-capability.md"]
    for path in describers:
        text = _read(path)
        for claim in CCC_CLAIMS:
            assert claim not in text, (path.name, claim)
    assert "the recipe runner reads every file in scope, so its result does not depend on it" in _read(
        KNOWLEDGE / "ccc-bridge.md")
    assert "step 3 reads the files it reads one at a time in their order" in _read(REFS / "sub" / "ccc-discover.md")


def test_tool_resolution_names_the_runner_where_a_step_gives_it() -> None:
    note = _slice(_read(KNOWLEDGE / "tool-resolution.md"),
                  "`scan_definitions()` follows the AST Extraction Protocol", "\n")
    assert ("where the step gives the recipe runner's command (`skf-extract-public-api.py --mode full`), it runs "
            "them all in one call; otherwise, and when the runner cannot run, the protocol's decision tree") in note


def test_filtered_list_is_built_by_hand_only_where_a_step_reads_it() -> None:
    two = _section(EXTRACT, "2")
    assert ("At Forge tier and above the recipe runner (§4) applies these globs to the source tree itself, and "
            "its `files_in_scope` is the filtered file count") in two
    assert ("Build the filtered file list by hand only where a step reads it: at Quick tier, for a "
            "`component-library` brief (§2c), and in a §4 branch that extracts without the runner") in two
    # the glob rule is stated once, in the protocol's Recipe Runner section
    assert "matching the globs by the **Files in scope** rule of the Recipe Runner section in" in two
    assert "`**/test_*` matches a top-level `test_x.py`" not in two
    assert "decision tree" not in two
    # the auth-files order note stays where test-skf-auth-files-after-clone.py reads it
    assert "Sections 2b and 2a follow in that order" in two
    ready = _slice(_section(EXTRACT, "2b"), "- **`ready`**", "\n")
    assert ("Build the §2 filtered file list again from `{source_root}` when §2 builds one (a `component-library` "
            "brief)") in ready


def test_entry_point_check_reads_the_runner_diff() -> None:
    four_b = _section(EXTRACT, "4b")
    runner = _slice(four_b, "**When the recipe runner extracted (§4: its JSON's `status` is `ok` or `incomplete`, "
                            "and `scope.languages` is not empty),**", "**Otherwise**")
    assert "do not read the entry points or diff the sets yourself" in runner
    for name in ("public", "internal", "extraction_gaps", "outside_scope"):
        assert f"\n- `{name}`:" in runner, name
    assert ("§5's `init` records its `counts` (`exports_public_api`, `exports_internal`, `effective_denominator` "
            "and `effective_denominator_basis`) and `arms` for step 5 §4") in runner
    # the runner's reading of entry points is its own business: --help, not a copy here
    assert "`skf-extract-public-api.py --help` lists the entry points it reads" in runner
    assert "`__all__`" not in runner and "`pub use`" not in runner
    # an out-of-scope surface still counts in the public API, so leaving it out costs coverage
    outside = _slice(runner, "- `outside_scope`:", "\n")
    assert ("this surface stays undocumented while `exports_public_api` still counts it, so `public_api_coverage` "
            "drops (only `effective_denominator`, for the curated-subset shapes, leaves it out)") in outside
    assert ("Files you read by eye because no recipe reads their language (`files_without_recipes`) are outside "
            "this diff and these counts") in runner
    # the by-eye read stays for Quick tier and source reading, after the runner branch
    by_eye = four_b[four_b.index("**Otherwise**"):]
    assert ("Quick tier, extraction by source reading, a brief whose language no recipe reads included, or the "
            "protocol's fallback") in by_eye
    assert ("when the runner's JSON has `status: no-ast-grep`, its `entry_points.files` lists them, and §5's "
            "`init` records its `arms` for step 5 §4") in by_eye
    # its per-language reads live in a reference only that branch loads, so extract.md stays in budget
    assert "load `{entryPointsByHandData}`, which only this branch reads" in by_eye
    assert _frontmatter(_read(EXTRACT))["entryPointsByHandData"] == "references/entry-points-by-hand.md"
    by_hand = _read(EXTRACT.parent / "entry-points-by-hand.md")
    assert "- **Python:** Read `{source_root}/__init__.py`" in by_hand
    assert "so public_api_coverage drops (only effective_denominator, for the curated-subset shapes" in by_hand
    assert "**Multi-entry packages (`exports` map / declaration-file entry points).**" in by_hand
    assert "- **Python:** Read" not in four_b and "**Multi-entry packages" not in four_b
    assert "outside the coverage denominator" not in four_b and "excluded from the coverage denominator" not in four_b


def test_inventory_counts_come_from_the_runner() -> None:
    """§5's `init` (skf-extraction-inventory.py) copies the runner's records and counts into the inventory."""
    five = _section(EXTRACT, "5")
    for token in ("`files_scanned` (the runner's `files_in_scope`)", "its `aggregates`, `counts` and `arms`",
                  "the head-cap warning (§4)", "each `errors[]` item", "each `file_issues[]` file",
                  "each extension `files_without_recipes` counts", "its `recipe_set`", "`ast_grep.version`"):
        assert token in five, token
    assert ("`init` writes each export as the runner recorded it (T1, `ast-grep`, with its `source_file`, "
            "`source_line`, `citation`, `ast_recipe`, `ast_node_type` and `export_type`)") in five
    assert "The summary's `counts` give §6 its numbers" in five
    assert "{warnings: the inventory's `warnings`}" in _section(EXTRACT, "6")


def _phase_4() -> str:
    """component-extraction.md's Phase 4, where step 3d runs the component-library recipes."""
    return _slice(_read(COMPONENT), "### Phase 4: Props-First Extraction", "### Phase 5:")


def test_step_3d_writes_the_runner_json_step_3_seeds_from() -> None:
    """Step 5b determinism-1: step 3d's runner writes to the {extraction_json}
    §5 passes to `init --extraction`, beside the staging folder and outside
    the scratch folder Phase 6 removes, so `init` seeds a component library's
    inventory with the runner's exports, counts and extraction rules, and the
    model sends only what it read by eye, the Props fields and the catalog.
    §2b binds the path and removes it for every brief, so a JSON there is
    this run's even when no runner candidate resolves."""
    phase_4 = _phase_4()
    assert "`{extraction_json}` ←" not in phase_4
    assert "it writes `{extraction_json}`, which step 3 §2b bound beside the staging folder" in phase_4
    assert _extraction_json() == STAGE + "{skill-name}.extraction.json"
    assert 'rm -f "{extraction_inventory}" "{detected_json}" "{extraction_json}" ' in _section(EXTRACT, "2b")
    block = _block(phase_4, RUNNER_CALL)
    assert block[:2] == [MKDIR_CALL, RM_EXTRACTION] and block[2].startswith(RUNNER_CALL), block
    call = block[2]
    assert call.endswith('-o "{extraction_json}"') and "--recipe-set component-library" in call, call
    _parses(RUNNER_MOD._build_parser(), _fill(call, {
        "extractPublicApiHelper": "runner.py", "source_root": "src", "scan_list": "files.txt", "tier": "Forge",
        "extraction_json": "out.json"}))
    text = _read(COMPONENT)
    assert "{component_scan}/extraction.json" not in text
    assert "Phase 4's runner JSON at `{extraction_json}`" in _slice(text, "## Rules", "## MANDATORY SEQUENCE")
    five = _section(EXTRACT, "5")
    assert ("Pass `--extraction` when §4's runner, or step 3d's Phase 4 for a component library, left a JSON at "
            "`{extraction_json}`") in five
    assert "with the labels step 3d gave them" not in five
    assert ("A component library (§2c) sends here only the exports step 3d read by eye (Quick tier, a `file_issues` "
            "file, or the runner's fallback); it sends each Props interface's fields with `patch` as `params`, and "
            "`component_catalog` with `set`.") in five
    assert ("for each function export whose `params` the runner left null (and each Props interface of a component "
            "library)") in five
    six = _slice(text, "### Phase 6:", "## RETURN PROTOCOL")
    assert "keep the aggregate counts below in context for step 5's `metadata.json` stats" in six
    assert "- `params`: each field as `{name, type, default, optional, description}`, sent with `patch`" in six


def test_step_3d_acts_on_the_runner_status() -> None:
    """Step 3d reads the runner's JSON as extract §4 does: by its `status`,
    never its exit code, so an `incomplete` run keeps its exports (which §5
    seeds) and no recipe runs again by hand; and the runner's warnings reach
    Gate 2 once, through `init`, so Phase 6 composes no head-cap message."""
    phase_4 = _phase_4()
    assert "Act on the JSON's `status`, never on the exit code. **On `ok` or `incomplete`**" in phase_4
    assert "On exit" not in phase_4
    assert ("**On `no-ast-grep`, or with no JSON at `{extraction_json}`** (an input error, or no candidate "
            "resolves): load `{extractionPatternsData}`") in phase_4
    assert ("Step 3 §5's `init` records the runner's warnings, and Gate 2 shows them: the head-cap warning when "
            "`truncated` is true") in phase_4
    text = _read(COMPONENT)
    assert "Phase 6 says so" not in text
    assert "head cap" not in _slice(text, "### Phase 6:", "## RETURN PROTOCOL")
    # the protocol's own status rule, which step 3d follows
    assert "Act on its `status`, not its exit code" in _read(PATTERNS)


# --------------------------------------------------------------------------
# The protocol: the runner first, the recipe runs by hand only as its fallback
# --------------------------------------------------------------------------


def test_protocol_runs_the_recipes_through_the_runner() -> None:
    patterns = _read(PATTERNS)
    protocol = _slice(patterns, "## AST Extraction Protocol", "### Known ast-grep Limitations")
    assert ("`skf-extract-public-api.py --mode full` runs the recipes below over the files in scope in one "
            "call") in protocol
    assert "never run the recipes one at a time, batch them, or merge and dedupe their matches by hand" in protocol
    # a step that gives no runner command runs the recipes
    assert "and the step that runs this protocol gives the recipe runner's command, the runner extracts" in protocol
    assert ("`-o` for the JSON, a file the step removes before the call, so that a JSON there after the call is "
            "this call's") in protocol
    runner = _slice(protocol, "### Recipe Runner", "### When the Runner Cannot Run")
    assert "`**/test_*` matches a top-level `test_x.py`" in runner
    # the recipe file by name, not by a project path an installed module does not have
    assert f"SKF's shared recipe file, `{RUNNER_MOD.RECIPES_FILE.name}`" in runner and RUNNER_MOD.RECIPES_FILE.is_file()
    assert "src/shared/" not in runner
    # only what the model acts on: the merge order is the recipe file's, never a copy of it here
    assert "**Merging:**" not in runner and "Pattern Merging" not in runner
    assert "- **Each export** is one name in one file" in runner
    assert "`skf-extract-public-api.py --help` gives the rest of its rules" in runner
    assert ("the files `files_without_recipes` counts that hold public API (by the Quick tier Strategy)") in runner
    assert "Act on its `status`, not its exit code" in runner and "Exit codes:" not in runner
    fallback = _cannot_run()
    assert ("There is no runner result when the step gives no runner command, no runner path resolves, or no JSON "
            "is at the `-o` path after the call (`uv` missing or failing, an input error, which prints one line on "
            "stderr, a crash, or a shell timeout that stopped it). Then, and when its `status` is `no-ast-grep`, "
            f"run the recipes as **{CUT.removeprefix('## ')}** below says, on the filtered file list: read this "
            "file on from that heading (a run the runner serves stops there)") in fallback
    assert "`tier-degradation-rules.md` \"AST Tool Unavailable\"" in fallback
    assert "## AST Tool Unavailable" in _read(REFS / "tier-degradation-rules.md")
    strategy = _slice(patterns, "## Forge Tier (AST Available)", "### Confidence")
    assert "1. Run the AST Extraction Protocol below: the recipe runner finds every export" in strategy


RUNNER_FAILED = ("When no JSON is there and a stderr line holds `error:` (the runner's input error or crash, or `uv` "
                 "failing; a shell timeout prints none), warn \"**Recipe runner failed:** {that line}. Extraction ran "
                 "without it.\" and keep the warning with the step's other warnings.")
RUNNER_FAILED_KEPT = "When {} warns that the runner failed (no JSON, and a stderr line that holds `error:`), send the "


def test_a_runner_error_line_is_warned_and_kept() -> None:
    """#694: no JSON after the call and an `error:` line on stderr (an input error or a crash, which the runner
    names in one line, or uv's own failure) still sends the run to the by-hand recipes, now with a warning that
    quotes the line; a shell timeout prints no such line and warns nothing. The protocol keys on the JSON and that
    line, never on an exit code. Create Skill keeps the warning for Gate 2 and the evidence report, from §4 and
    from step 3d's Phase 4."""
    fallback = _cannot_run()
    first = fallback.index("There is no runner result when")
    assert RUNNER_FAILED in fallback and fallback.index(RUNNER_FAILED) > first
    assert "exit 2" not in fallback and "exits 2" not in fallback
    four = _section(EXTRACT, "4")
    assert (RUNNER_FAILED_KEPT.format("that section") + "warning with §5's `add --field warnings` for §6 and the evidence "
            "report.") in four
    assert "exits 2" not in four and "exit 2" not in four
    assert "the runner's failure (§4), the detector's failure (§4c)" in _section(EXTRACT, "5")
    phase_4 = _phase_4()
    assert (RUNNER_FAILED_KEPT.format("that section") + "warning with step 3 §5's `add --field warnings`, so Gate 2 "
            "and the evidence report show it.") in phase_4
    assert "On exit" not in phase_4
    # Gate 2 and the evidence report show the inventory's warnings, where `add --field warnings` puts them
    assert "{warnings: the inventory's `warnings`}" in _section(EXTRACT, "6")


def test_a_brief_language_no_recipe_reads_goes_to_source_reading() -> None:
    """A brief whose language no recipe reads (java, kotlin, csharp, ruby,
    swift and php are languages skf-detect-language.py emits) leaves the
    runner's `scope.languages` empty with `status: ok`: the protocol sends it
    to source reading, and §4b counts its entry points by hand."""
    fallback = _cannot_run()
    assert ("When the runner's `scope.languages` is empty, whatever its `status`, no recipe reads the brief's "
            "language (the runner warns `no recipe reads {language} files` and reads no file): extract by the "
            "Quick tier Strategy (source reading, T1-low).") in fallback
    assert "## Quick Tier (No AST)" in _read(PATTERNS)
    wanted, unknown = RUNNER_MOD._wanted_languages(["java"])
    assert (wanted, unknown) == (set(), ["java"])
    for language in ("kotlin", "csharp", "ruby", "swift", "php"):
        assert RUNNER_MOD._wanted_languages([language])[0] == set(), language
    four_b = _section(EXTRACT, "4b")
    assert "and `scope.languages` is not empty),**" in four_b
    assert "a brief whose language no recipe reads included" in four_b[four_b.index("**Otherwise**"):]


def test_a_runner_call_that_writes_no_json_leaves_no_stale_result(tmp_path: Path) -> None:
    """The runner writes -o only when it has a result: an input error (exit
    2) writes none. The documented block removes the JSON an earlier run
    left first, so the step finds no JSON and follows When the Runner Cannot
    Run, never reading the earlier run's exports as this run's."""
    four = _section(EXTRACT, "4")
    out = tmp_path / "_bmad-output" / ".skf-stage" / "demo.extraction.json"
    out.parent.mkdir(parents=True)
    out.write_bytes(b'{"status": "ok", "exports": [{"export_name": "stale"}]}\n')
    values = {"extractPublicApiHelper": "runner.py", "source_root": (tmp_path / "missing").as_posix(),
              "brief_path": (tmp_path / "brief.yaml").as_posix(), "tier": "Forge", "extraction_json": out.as_posix()}
    _rm(_call(four, "rm -f "), values)
    result = _run(_fill(_call(four, RUNNER_CALL), values), RUNNER, tmp_path)
    assert result.returncode == 2 and result.stdout == "", result
    assert not out.exists()
    assert "no JSON is at the `-o` path after the call" in _cannot_run()


# --------------------------------------------------------------------------
# compile §4: the counts and arms come from the runner
# --------------------------------------------------------------------------


def test_compile_counts_come_from_the_runner() -> None:
    four = _section(COMPILE, "4")
    payload = _slice(four, "**Judgment payload (passed as JSON on stdin):**", "    2. `scope.type` is not")
    for token in ("`counts.exports_public_api`", "`counts.exports_internal`", "`counts.effective_denominator`",
                  "`counts.effective_denominator_basis`", "`arms.monorepo`", "`arms.specific_modules`",
                  "`arms.multi_subpath_exports`"):
        assert token in payload, token
    for gone in ("count the union of **named exports**", "derive this from step 3's entry-point validation",
                 "count of all other non-underscore-prefixed exports", "detected via `packages/` layout",
                 "a `packages/` layout"):
        assert gone not in four, gone
    # the arms by their field names, with the rule the runner applies for a run without its JSON
    assert "one of the `arms` step 3 recorded is true. When it recorded none, judge each from the source" in payload
    assert "`arms.monorepo` (a workspace layout of a kind `skf-detect-workspaces.py` detects)" in payload
    assert ("`arms.multi_subpath_exports` (an in-scope `package.json` whose `exports` map has more than one "
            "non-root subpath without `*` whose target is a JS/TS file, not a monorepo)") in payload
    assert ("- Set `ast_node_count` to the number of exports ast-grep matched (the recipe runner's "
            "`aggregates.exports`)") in four


# --------------------------------------------------------------------------
# The relabel rule: one home, looked up through kind-at
# --------------------------------------------------------------------------


def test_relabel_rule_is_written_once() -> None:
    for sentence in RELABEL_RULE:
        homes = [path.name for path in sorted(REFS.rglob("*.md")) if sentence in _read(path)]
        assert homes == ["relabel-rule.md"], (sentence, homes)
    # extraction-patterns.md keeps the section every pointer names, and it names the rule's file
    pointer_section = _slice(_read(PATTERNS), "\n## Relabel Rule\n", "\n---\n")
    assert _read(PATTERNS).count("\n## Relabel Rule\n") == 1
    assert "is in `relabel-rule.md`, beside this file" in pointer_section
    assert "kind-at" not in pointer_section and RELABEL.is_file()
    # the readers load the rule's file itself, never the patterns file for a pointer to it
    pointer = "relabel it by the Relabel Rule in `{relabelRuleData}`"
    assert pointer in _section(COMPILE, "4") and pointer in _section(VALIDATE, "7")
    assert "the Relabel Rule in `{relabelRuleData}` gives" in _section(VALIDATE, "7a")
    for path in (COMPILE, VALIDATE):
        assert _frontmatter(_read(path))["relabelRuleData"] == "references/relabel-rule.md", path.name
        assert "Relabel Rule in `{extractionPatternsData}`" not in _read(path), path.name
    for path in (EXTRACT, COMPILE, VALIDATE):
        text = _read(path)
        frontmatter = _frontmatter(text)
        # one binding, a path `kind-at` can read from {project-root}
        assert "extractionPatternsData" not in frontmatter, path.name
        assert frontmatter["extractionPatternsDataProbeOrder"] == PATTERNS_PROBE, path.name
        assert (REPO_ROOT / PATTERNS_PROBE[1].removeprefix("{project-root}/")).resolve() == PATTERNS.resolve()
        assert "run the ast-grep recipes for its language" not in text, path.name


BY_HAND = REFS / "extraction-patterns-by-hand.md"
# #600: extract §1 reads extraction-patterns.md on every source run, up to this
# heading; what follows serves only a run without the recipe runner.
CUT = "## Running the Recipes Without the Runner"
# The whole file stays under the 9,000-token budget of a single-purpose
# reference (tiktoken cl100k_base) and what every run reads under the 4,500 of
# a multi-branch one: about 4 characters a token, so 36,000 and 18,500
# characters stand in for them here.
PATTERNS_CHAR_BUDGET = 36_000
EVERY_RUN_CHAR_BUDGET = 18_500


def test_the_patterns_file_keeps_only_what_every_run_reads() -> None:
    """#600 carve: the recipes (which the runner's data file mirrors and
    `kind-at` reads) and Known Limitations #4 and #11 stay; each recipe's
    notes, the shape table and the other limitations load only when the
    runner cannot run, and the relabel rule only on a label violation.
    Every run reads the file only up to the cut: the decision tree, the
    CLI streaming template, the line-number rule and the recipe fences come
    after it, and only a run without the runner reads on."""
    patterns = _read(PATTERNS)
    assert len(patterns) < PATTERNS_CHAR_BUDGET, len(patterns)
    assert patterns.count(f"\n{CUT}\n") == 1
    every_run, by_hand_run = patterns.split(f"\n{CUT}\n")
    assert len(every_run) < EVERY_RUN_CHAR_BUDGET, len(every_run)
    for part in ("### Decision Tree", "### CLI Streaming Fallback", "**Line numbers are 0-based in ast-grep JSON**",
                 "### YAML Rule Recipes by Language", "### Component Library YAML Rule Recipes", "```yaml"):
        assert part in by_hand_run and part not in every_run, part
    for part in ("### Recipe Runner", "### When the Runner Cannot Run", "### Known ast-grep Limitations",
                 "\n## Relabel Rule\n"):
        assert part in every_run, part
    # the head cap the runner applies is in the Recipe Runner, read on every run
    assert "keeps at most 200 matches, or at Forge+ and Deep 500 for" in _slice(every_run, "### Recipe Runner", "### When")
    cannot_run = _cannot_run()
    assert ("first load `extraction-patterns-by-hand.md`, beside this file, completely: it holds each recipe's "
            "notes and the limitations of patterns run by hand") in cannot_run
    loads = [line for line in patterns.splitlines() if "load `extraction-patterns-by-hand.md`" in line]
    assert loads and all(line in cannot_run for line in loads), "the by-hand file loads on that branch only"
    hand = _read(BY_HAND)
    assert "```yaml" not in hand, "every recipe stays in extraction-patterns.md"
    for note in ("**Language selection:**", "**JS/TS Pattern Merging:**", "**Vue note:**", "| Export shape |",
                 "\n7. **Python class patterns", "\n10. **Generic class declarations"):
        assert note in hand and note not in patterns, note
    limitations = _slice(patterns, "### Known ast-grep Limitations", "### Re-Export Tracing")
    assert "\n4. **Fallback protocol:**" in limitations and "\n11. **Forms the recipes deliberately" in limitations
    # #4 is the by-hand run's fallback, #11 every run's, and neither file says otherwise
    assert "Limitation #11 applies to every run" in limitations and "#4 is the fallback of a recipe run by hand" in limitations
    assert "#4, the `find_code` fallback of a recipe run by hand" in hand
    for text in (patterns, hand):
        assert "#4 and #11 apply to every run" not in text
    # the by-hand notes point at the recipes where they are, and say each thing once
    assert "forms below" not in hand and "form below" not in hand and "Limitation #4 is in" not in hand
    assert hand.count("never reports the kind") == 1
    relabel = _slice(patterns, "\n## Relabel Rule\n", "\n---\n")
    assert "which compile.md §4 and validate.md §7 and §7a load themselves" in relabel
    assert "load it when another reader, such as update-skill's write.md, meets a" in relabel
    # the qmd CLI forms enrich.md runs, never a subcommand qmd lacks
    assert "`qmd search` / `qmd vsearch`" in patterns and "vector-search" not in patterns + hand


def test_relabel_rule_looks_the_kind_up_with_kind_at() -> None:
    rule = _read(RELABEL)
    call = _call(rule, KIND_AT_CALL)
    assert call == ('uv run {verifyProvenanceCompletenessHelper} kind-at --source-root "{source_root}" '
                    '--file "{source_file}" --line {source_line} --name "{export_name}" '
                    '--recipes "{extractionPatternsData}"')
    words = _fill(call, {"verifyProvenanceCompletenessHelper": "v.py", "source_root": "src", "source_file": "a.py",
                         "source_line": "3", "export_name": "f", "extractionPatternsData": "p.md"})
    _parses(VERIFIER_MOD._build_parser(), words)
    assert "record the `kind` it prints when `status` is `found`" in rule and "never invent a kind" in rule
    # both steps that follow the rule resolve the verifier it calls, where they relabel
    for path, number in ((COMPILE, "4"), (VALIDATE, "7")):
        assert _frontmatter(_read(path))["verifyProvenanceCompletenessProbeOrder"] == VERIFIER_PROBE, path.name
        assert RESOLVE_VERIFIER in _section(path, number), path.name
    # validate's frontmatter names both of its verifier users
    assert "§7's relabel runs its `kind-at`, and §7a its `verify` and `fix`." in _read(VALIDATE)


# --------------------------------------------------------------------------
# validate §7a: verify writes its JSON, fix repairs, the prose triages
# --------------------------------------------------------------------------


def _section_7a() -> str:
    return _section(VALIDATE, "7a")


def test_validate_7a_fixes_through_the_verifier() -> None:
    seven_a = _section_7a()
    verify = _call(seven_a, VERIFY_CALL)
    fix = _call(seven_a, FIX_CALL)
    assert verify.endswith('--check-node-kinds -o "{verify_json}"'), verify
    assert fix == ('uv run {verifyProvenanceCompletenessHelper} fix --verify "{verify_json}" '
                   '--provenance <staging-skill-dir>/provenance-map.json --skill-dir <staging-skill-dir>')
    parser = VERIFIER_MOD._build_parser()
    values = {"verifyProvenanceCompletenessHelper": "v.py", "source_root": "src", "verify_json": "v.json",
              "staging-skill-dir": "stage"}
    for call in (verify, fix):
        _parses(parser, _fill(call, values))
    assert _binding(seven_a, "verify_json") == STAGE + "{skill-name}.verify.json"
    # the block that both runs use first removes the JSON an earlier run (or the first run) left
    block = _block(seven_a, VERIFY_CALL)
    assert block[0] == RM_VERIFY and block[1] == verify, block
    assert ("A JSON at `{verify_json}` after the call is this run's: read it, not the exit code (exit 1 means "
            "findings). When no JSON is there after the call") in seven_a
    assert "If that second run leaves no JSON at `{verify_json}`" in seven_a
    assert "Exit 2 writes no JSON" not in seven_a and "If that second run exits 2" not in seven_a
    # step 7 promotes the staged files byte for byte: no in-context copy to keep in step
    assert "in-context copy" not in seven_a and "step 7 writes from" not in seven_a
    for by_hand in ("Plan every move before making any", "A range citation shifts both ends",
                    "change its prefix to `expected_prefix`", "run the recipes `{extractionPatternsData}` gives",
                    "or a clone that is already deleted", "--no-line-moves"):
        assert by_hand not in seven_a, by_hand
    kinds = _slice(seven_a, "2. **Node kinds.**", "\n")
    assert "the node kind the Relabel Rule in `{relabelRuleData}` gives" in kinds
    assert "never change `extraction_method` to clear the finding" in kinds
    # item 1's fix may have moved the line, so the entry is confirmed without it and looked up where it is now
    assert ("(its `export_name` and `source_file` confirm it; item 1's `fix` may have moved its `source_line`)"
            in kinds)
    assert "its `kind-at` lookup at the entry's current `source_line`" in kinds


def test_validate_7a_triages_every_warn_fix_leaves() -> None:
    whys = set(re.findall(r'why\s*=\s*"([a-z-]+)"', _read(VERIFIER)))
    # create-skill never passes --no-line-moves, so no line move is skipped
    assert "line-moves-skipped" in whys and "no-definition-line" in whys
    triage = _slice(_section_7a(), "Fix nothing else, and triage what is left:", "Record the result")
    named = set(re.findall(r"`([a-z-]+)`", triage))
    assert whys - {"line-moves-skipped"} <= named, sorted(whys - named)
    assert "A `left_as_warn[]` item whose `why` is `no-definition-line` is unverified, not gone" in triage


def _staged_skill(root: Path) -> Path:
    """A staged skill whose map cites a decorator line and whose SKILL.md
    gives an ast-grep entry an [SRC:] prefix."""
    files = {
        "src/api.py": "@decorator\ndef search(q):\n    return q\n\n\ndef fetch(url):\n    return url\n",
        "_bmad-output/.skf-stage/mylib/SKILL.md": (
            "---\nname: mylib\ndescription: Search things. Use when searching.\n---\n\n# mylib\n\n"
            "- `search(q)` [SRC:src/api.py:L1]\n- `fetch(url)` [AST:src/api.py:L6]\n"),
        "_bmad-output/.skf-stage/mylib/references/api.md": "# API\n\n`search(q)` returns q [AST:src/api.py:L1-3].\n",
        "_bmad-output/.skf-stage/mylib/metadata.json": json.dumps(
            {"name": "mylib", "scope_type": "full-library", "exports": ["search", "fetch"],
             "generated_by": "create-skill"}),
        "_bmad-output/.skf-stage/mylib/provenance-map.json": json.dumps({"skill_name": "mylib", "entries": [
            {"export_name": name, "export_type": "function", "source_file": "src/api.py", "source_line": line,
             "confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "function_definition",
             "signature_source": "T1"} for name, line in (("search", 1), ("fetch", 6))]}, indent=2),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        # bytes, so the files keep their LF line ends on Windows too
        (root / rel).write_bytes(text.encode("utf-8"))
    return root / "_bmad-output" / ".skf-stage" / "mylib"


def test_documented_verify_and_fix_repair_a_staged_skill(tmp_path: Path) -> None:
    stage = _staged_skill(tmp_path)
    seven_a = _section_7a()
    verify_json = _binding(seven_a, "verify_json").replace("{project-root}", tmp_path.as_posix())
    values = {"verifyProvenanceCompletenessHelper": "v.py", "source_root": tmp_path.as_posix(),
              "staging-skill-dir": stage.as_posix(), "verify_json": verify_json.replace("{skill-name}", "mylib")}
    # an earlier run's JSON, which the documented block removes before the call
    Path(values["verify_json"]).write_bytes(b'{"status": "pass", "stale": [], "citations": []}\n')
    rm = _call(seven_a, "rm -f ")
    verify = _fill(_call(seven_a, VERIFY_CALL), values)
    _rm(rm, values)
    first = _run(verify, VERIFIER, tmp_path)
    assert first.returncode == 1 and first.stdout == "", first.stderr
    found = json.loads(Path(values["verify_json"]).read_text(encoding="utf-8"))
    assert [(s["export_name"], s["definition_lines"]) for s in found["stale"]] == [("search", [2])]
    assert [c["expected_prefix"] for c in found["citations"]] == ["AST"]
    fixed = _run(_fill(_call(seven_a, FIX_CALL), values), VERIFIER, tmp_path)
    assert fixed.returncode == 0, fixed.stderr
    result = json.loads(fixed.stdout)
    assert result["summary"] == {"citation_prefixes_fixed": 1, "source_lines_moved": 1, "citations_moved": 2,
                                 "left_as_warn_count": 0}
    assert {Path(p).name for p in result["files_written"]} == {"SKILL.md", "api.md", "provenance-map.json"}
    assert "- `search(q)` [AST:src/api.py:L2]\n" in (stage / "SKILL.md").read_text(encoding="utf-8")
    assert "[AST:src/api.py:L2-4]" in (stage / "references" / "api.md").read_text(encoding="utf-8")
    _rm(rm, values)
    second = _run(verify, VERIFIER, tmp_path)
    assert second.returncode == 0, second.stderr
    again = json.loads(Path(values["verify_json"]).read_text(encoding="utf-8"))
    assert (again["status"], again["stale"], again["citations"]) == ("pass", [], [])


# --------------------------------------------------------------------------
# The CLI streaming template's fnmatch, beside the Files in scope rule
# --------------------------------------------------------------------------


def test_cli_template_says_where_fnmatch_differs() -> None:
    """The fallback template filters with fnmatch, whose `**/x` needs a
    folder: the template's note says to list x as well, and that holds."""
    note = ("# fnmatch is not the Files in scope rule above: its `*` also crosses `/`, and `**/x`\n"
            "# needs a folder before x, so add x too for a top-level file ('test_*' beside '**/test_*').")
    assert note in _read(PATTERNS)
    assert not fnmatch.fnmatch("test_x.py", "**/test_*") and fnmatch.fnmatch("test_x.py", "test_*")
    assert fnmatch.fnmatch("pkg/deep/test_x.py", "**/test_*") and fnmatch.fnmatch("pkg/deep/x.py", "*.py")


# --------------------------------------------------------------------------
# Real ast-grep runs: the documented runner and kind-at calls
# --------------------------------------------------------------------------


def _pinned_ast_grep() -> bool:
    """True when the ast-grep on PATH is the version package.json's test:python pins."""
    scripts = json.loads(_read(REPO_ROOT / "package.json"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


needs_ast_grep = pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")

SOURCE_TREE = {
    "src/pkg/__init__.py": 'from .core import alpha, Beta\n\n__all__ = ["alpha", "Beta"]\n',
    "src/pkg/core.py": ("def alpha(x):\n    return x\n\n\nclass Beta:\n    def method(self):\n        pass\n\n\n"
                        "def _hidden():\n    pass\n\n\ndef helper():\n    pass\n"),
    "src/pkg/tests/test_core.py": "def test_alpha():\n    pass\n",
    "test_x.py": "def test_top():\n    pass\n",
    "brief/skill-brief.yaml": ("name: demo\nlanguage: python\nscope:\n  type: full-library\n"
                               "  include: ['**/*.py']\n  exclude: ['**/test_*']\n"),
}


CAPPED_TREE = {
    "src/pkg/__init__.py": 'from .core import first, second\n\n__all__ = ["first", "second"]\n',
    "src/pkg/core.py": "def first():\n    pass\n\n\ndef second():\n    pass\n",
    "brief/skill-brief.yaml": "name: demo\nlanguage: python\nscope:\n  type: full-library\n  include: ['**/*.py']\n",
}


JAVA_TREE = {
    "src/main/java/com/acme/Widget.java": ("package com.acme;\n\npublic class Widget {\n"
                                           "    public void run() {}\n}\n"),
    "brief/skill-brief.yaml": ("name: demo\nlanguage: java\nscope:\n  type: full-library\n"
                               "  include: ['src/**/*.java']\n"),
}


def _runner_output(tmp_path: Path, tree: dict[str, str] = SOURCE_TREE, extra: tuple[str, ...] = ()) -> dict:
    """The documented runner block over `tree`, run as extract §4 gives it
    (with `extra` arguments after the runner call)."""
    root = tmp_path / "source"
    for rel, text in tree.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode("utf-8"))
    four = _section(EXTRACT, "4")
    out = _extraction_json().replace("{project-root}", tmp_path.as_posix())
    out = out.replace("{skill-name}", "demo")
    # the folder the documented `mkdir -p` makes, and nothing more
    mkdir = _fill(_call(four, "mkdir -p "), {"project-root": tmp_path.as_posix()})
    assert not Path(mkdir[2]).exists()
    Path(mkdir[2]).mkdir(parents=True)
    _rm(_call(four, "rm -f "), {"extraction_json": out})
    words = _fill(_call(four, RUNNER_CALL), {
        "extractPublicApiHelper": "runner.py", "source_root": root.as_posix(),
        "brief_path": (root / "brief" / "skill-brief.yaml").as_posix(), "tier": "Forge", "extraction_json": out})
    result = _run([*words, *extra], RUNNER, tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(Path(out).read_text(encoding="utf-8"))


def _resolve(data: dict, path: str) -> None:
    """Assert that the dotted `path` (a `[]` part is a list) names a field of `data`."""
    node: object = data
    for part in path.split("."):
        key = part.removesuffix("[]")
        assert isinstance(node, dict) and key in node, f"{path}: no {key!r}"
        node = node[key]
        if part.endswith("[]"):
            assert isinstance(node, list), f"{path}: {key!r} is not a list"
            if not node:
                return
            node = node[0]


@needs_ast_grep
def test_documented_runner_call_extracts_the_scope(tmp_path: Path) -> None:
    out = _runner_output(tmp_path)
    # `**/test_*` drops the top-level test_x.py and the nested test file
    assert (out["status"], out["files_in_scope"], out["truncated"]) == ("ok", 2, False)
    found = [(e["export_name"], e["source_file"], e["source_line"], e["citation"], e["ast_recipe"], e["ast_node_type"])
             for e in out["exports"]]
    assert found == [
        ("alpha", "src/pkg/core.py", 1, "[AST:src/pkg/core.py:L1]", "python-public-functions", "function_definition"),
        ("Beta", "src/pkg/core.py", 5, "[AST:src/pkg/core.py:L5]", "python-public-classes", "class_definition"),
        ("helper", "src/pkg/core.py", 14, "[AST:src/pkg/core.py:L14]", "python-public-functions",
         "function_definition")]
    diff = out["entry_point_diff"]
    assert sorted(item["name"] for item in diff["public"]) == ["Beta", "alpha"]
    assert [item["name"] for item in diff["internal"]] == ["helper"]
    assert (out["counts"]["exports_public_api"], out["counts"]["exports_internal"]) == (2, 1)


@needs_ast_grep
def test_documented_runner_call_reads_no_file_of_a_java_brief(tmp_path: Path) -> None:
    """The case When the Runner Cannot Run sends to source reading: the run
    says `status: ok` and exits 0, yet its empty `scope.languages` shows no
    recipe read the brief's language, and it found nothing."""
    out = _runner_output(tmp_path, JAVA_TREE)
    assert (out["status"], out["scope"]["languages"], out["files_in_scope"]) == ("ok", [], 0)
    assert out["files_without_recipes"] == {".java": 1}
    assert "no recipe reads java files" in out["warnings"]
    assert (out["exports"], out["counts"]["exports_public_api"]) == ([], 0)


@needs_ast_grep
def test_a_capped_public_name_comes_back_as_a_gap(tmp_path: Path) -> None:
    """extract §4's head-cap note: a public name past the cap is an
    extraction gap with its file and line, which §4b reads by eye."""
    out = _runner_output(tmp_path, CAPPED_TREE, ("--head-cap", "1"))
    assert out["truncated"] is True
    assert [r["id"] for r in out["recipes"] if r["truncated"]] == ["python-public-functions"]
    assert [e["export_name"] for e in out["exports"]] == ["first"]
    gaps = [(g["name"], g["file"], g["line"]) for g in out["entry_point_diff"]["extraction_gaps"]]
    assert gaps == [("second", "src/pkg/core.py", 5)]
    # the public API count does not shrink with the cap
    assert out["counts"]["exports_public_api"] == 2


@needs_ast_grep
def test_every_runner_field_the_prose_reads_is_in_its_json(tmp_path: Path) -> None:
    out = _runner_output(tmp_path)
    passages = [_section(EXTRACT, number) for number in ("2", "4", "4b", "5", "6")]
    passages.append(_section(COMPILE, "4"))
    patterns = _read(PATTERNS)
    passages.append(_slice(patterns, "### Recipe Runner", "### Known ast-grep Limitations"))
    # `scope.*` names brief fields too (`scope.notes`), so the runner's `scope` is checked on its own
    named = {token for text in passages for token in TOKEN_RE.findall(text)
             if token.split(".")[0].removesuffix("[]") in out and not token.startswith("scope")}
    assert {"files_in_scope", "files_without_recipes", "truncated", "status",
            "counts.effective_denominator", "arms.multi_subpath_exports", "entry_points.unresolved",
            "entry_points.files", "ast_grep.version"} <= named, sorted(named)
    for token in sorted(named):
        _resolve(out, token)
    assert set(out["scope"]) >= {"include", "exclude", "tier_a_include", "type", "languages"}
    for name in ("public", "internal", "extraction_gaps", "outside_scope"):
        assert name in out["entry_point_diff"], name
    for name in ("exports_public_api", "exports_internal", "effective_denominator", "effective_denominator_basis"):
        assert name in out["counts"], name
    each_export = _slice(patterns, "- **Each export** is one name in one file, and gives", "\n")
    fields = set(re.findall(r"`([a-z_]+)`", each_export)) - {"kind"}
    assert fields and fields <= set(out["exports"][0]), sorted(fields - set(out["exports"][0]))
    assert {(e["confidence"], e["extraction_method"]) for e in out["exports"]} == {("T1", "ast-grep")}
    # the protocol dispatches on every status the runner documents, and on no other
    documented = re.search(r'"status": ([^,\n]+),', RUNNER_MOD.__doc__)
    assert documented, "the runner documents no status"
    statuses = _slice(patterns, "Act on its `status`, not its exit code:", "\n").split(":", 1)[1]
    assert set(re.findall(r"`([a-z-]+)`, ", statuses)) == set(re.findall(r'"([a-z-]+)"', documented.group(1)))


COMPONENT_TREE = {
    "components/ui/button.tsx": ("export interface ButtonProps {\n  variant?: string\n}\n\n"
                                 "export function Button(props: ButtonProps) {\n  return null\n}\n"),
    "components/ui/card.tsx": ("interface CardProps {\n  title: string\n}\n\n"
                               "const Card = (props: CardProps) => null\n\nexport { Card }\nexport type { CardProps }\n"),
}


@needs_ast_grep
def test_the_component_runner_json_seeds_the_inventory(tmp_path: Path) -> None:
    """The documented step 3d block, then §5's `init --mode component-library
    --extraction`: the inventory holds the runner's exports, counts and
    warnings as it wrote them, a Props interface takes its fields through
    `patch` (its JSDoc description included, which the Tier 2 Props table
    reads), and step 7's `rules` writes the component-library recipe set
    and the recipes the runner ran into extraction-rules.yaml."""
    root = tmp_path / "source"
    for rel, text in COMPONENT_TREE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode("utf-8"))
    scan_list = tmp_path / "kept.txt"
    scan_list.write_bytes("".join(f"{rel}\n" for rel in COMPONENT_TREE).encode("utf-8"))
    phase_4 = _phase_4()
    out = _extraction_json().replace("{project-root}", tmp_path.as_posix())
    out = out.replace("{skill-name}", "demo")
    Path(_fill(_call(phase_4, "mkdir -p "), {"project-root": tmp_path.as_posix()})[2]).mkdir(parents=True)
    _rm(_call(phase_4, "rm -f "), {"extraction_json": out})
    words = _fill(_call(phase_4, RUNNER_CALL), {
        "extractPublicApiHelper": "runner.py", "source_root": root.as_posix(), "scan_list": scan_list.as_posix(),
        "tier": "Forge", "extraction_json": out})
    result = _run(words, RUNNER, tmp_path)
    assert result.returncode == 0, result.stderr
    runner = json.loads(Path(out).read_text(encoding="utf-8"))
    assert runner["recipe_set"] == "component-library" and runner["exports"], runner["status"]

    inventory = tmp_path / "_bmad-output" / ".skf-stage" / "demo.inventory.json"

    def _helper(*args: str, stdin: str | None = None) -> dict:
        proc = subprocess.run([sys.executable, str(INVENTORY), *args, "--inventory", str(inventory)], input=stdin,
                              capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, check=False)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    _helper("init", "--skill", "demo", "--mode", "component-library", "--tier", "Forge", "--extraction", out)
    data = json.loads(inventory.read_text(encoding="utf-8"))
    assert data["exports"] == runner["exports"]
    assert (data["counts"], data["arms"], data["files_scanned"]) == (runner["counts"], runner["arms"],
                                                                     runner["files_in_scope"])
    assert data["extraction_rules"]["recipe_set"] == "component-library"
    assert data["extraction_rules"]["recipes"] == [r["id"] for r in runner["recipes"]]
    props = next(e for e in data["exports"] if e["export_name"] == "ButtonProps")
    fields = [{"name": "variant", "type": "string", "default": None, "optional": True,
               "description": "The look of the button."}]
    patched = _helper("patch", stdin=json.dumps([{"export_name": "ButtonProps", "source_file": props["source_file"],
                                                  "params": fields}]))
    assert (patched["patched"], patched["unmatched"], patched["ambiguous"]) == (1, [], [])
    data = json.loads(inventory.read_text(encoding="utf-8"))
    assert next(e for e in data["exports"] if e["export_name"] == "ButtonProps")["params"] == fields
    rules_target = tmp_path / "extraction-rules.yaml"
    proc = subprocess.run([sys.executable, str(INVENTORY), "rules", "--inventory", str(inventory), "--language",
                           "typescript", "--target", str(rules_target)], capture_output=True, text=True,
                          encoding="utf-8", cwd=tmp_path, check=False)
    assert proc.returncode == 0, proc.stderr
    rules = yaml.safe_load(rules_target.read_text(encoding="utf-8"))
    assert (rules["extraction_mode"], rules["recipe_set"]) == ("component-library", "component-library")
    assert "react-props-interfaces" in rules["recipes"] and rules["ast_grep_version"]


@needs_ast_grep
def test_relabel_rule_kind_at_call_finds_the_recipe_kind(tmp_path: Path) -> None:
    _staged_skill(tmp_path)
    rule = _read(RELABEL)
    # {extractionPatternsData} as validate.md binds it, in this checkout as the project root
    patterns = _frontmatter(_read(VALIDATE))["extractionPatternsDataProbeOrder"][1]
    words = _fill(_call(rule, KIND_AT_CALL), {
        "verifyProvenanceCompletenessHelper": "v.py", "source_root": tmp_path.as_posix(), "source_file": "src/api.py",
        "source_line": "2", "export_name": "search",
        "extractionPatternsData": patterns.replace("{project-root}", REPO_ROOT.as_posix())})
    result = _run(words, VERIFIER, REPO_ROOT)
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    assert (found["status"], found["kind"]) == ("found", "function_definition")
    assert [m["recipe"] for m in found["matches"]] == ["python-public-functions"]
