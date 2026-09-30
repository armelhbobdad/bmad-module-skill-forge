#!/usr/bin/env python3
"""Prose pins: the user docs describe what the skills they document do.

Each test reads a page under docs/ and the skill file or script the page
describes, so a change on one side that the other does not follow fails:

- docs/workflows.md's Quick Skill section describes the skills-module shape
  quick-extract records, says `--description` and `--exports` are
  single-target overrides that a `--batch` run refuses with the exit code and
  halt reason batch-mode.md raises, and its headless exit-code map is
  halt-contract.md's;
- its Refine Architecture section describes the gate gap analysis shows for
  a derived scope and the Refinement Summary rows and next step compile
  writes;
- docs/skill-model.md gives `confidence_tier` the scale the export gate
  accepts for each `skill_type`, says a stack's `confidence_distribution`
  sums to `library_count` as the stack validator checks, and says where an
  update records `last_update` now that update-skill writes none into
  metadata.json;
- docs/troubleshooting.md names Ferris's two install halts beside setup's
  and the installer command they all give;
- docs/agents.md lists the first-run starting points Ferris highlights, what
  WS ends with, and the offer Ferris makes before a second workflow.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
DOCS = REPO_ROOT / "docs"
WORKFLOWS = DOCS / "workflows.md"
SKILL_MODEL = DOCS / "skill-model.md"
TROUBLESHOOTING = DOCS / "troubleshooting.md"
AGENTS = DOCS / "agents.md"
QUICK = SRC / "skf-quick-skill"
QUICK_EXTRACT = QUICK / "references" / "quick-extract.md"
BATCH_MODE = QUICK / "references" / "batch-mode.md"
HALT_CONTRACT = QUICK / "references" / "halt-contract.md"
RA_REFS = SRC / "skf-refine-architecture" / "references"
FORGER_SKILL = SRC / "skf-forger" / "SKILL.md"
UPDATE_WRITE = SRC / "skf-update-skill" / "references" / "write.md"
VALIDATE_OUTPUT = SRC / "shared" / "scripts" / "skf-validate-output.py"

INSTALLERS = ("npx bmad-module-skill-forge install", "npx bmad-method install")
EXIT_ROW_RE = re.compile(r"^\s*\| (\d+)\s+\| ([a-z-]+)\s+\|", re.M)
BOLD_PATH_RE = re.compile(r"\*\*([^*]+)\*\* \(")
NUMBER_WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


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


def _paragraph(text: str, start: str) -> str:
    """The one paragraph of `text` that starts with `start`."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.lstrip().startswith(start)]
    assert len(paragraphs) == 1, f"one paragraph starting with {start!r} expected, found {len(paragraphs)}"
    return paragraphs[0]


def _quick_section() -> str:
    return _slice(_read(WORKFLOWS), "### Quick Skill (QS)", "**Agent:**")


def _ra_section() -> str:
    return _slice(_read(WORKFLOWS), "### Refine Architecture (RA)", "**Agent:**")


def _exit_codes(table: str) -> dict[str, str]:
    """{code: meaning} from the rows of a markdown table led by Code and Meaning columns."""
    return dict(EXIT_ROW_RE.findall(table))


# --------------------------------------------------------------------------
# Quick Skill: skills modules, the batch refusal and the exit-code map
# --------------------------------------------------------------------------


def test_quick_skill_documents_the_skills_module_shape():
    """#527: the section names the shape quick-extract records and what such a skill documents."""
    sniff = _slice(_read(QUICK_EXTRACT), "### 1.5. Repo-Shape Sniff", "### 2.")
    assert "record `repo_shape: skills-module`" in sniff
    shape = _paragraph(_quick_section(), "**Skills modules:**")
    for token in ("`repo_shape: skills-module`", "`SKILL.md` frontmatter", "`module-help.csv`", "`module.yaml`",
                  "Key Exports", "`exports` of its `metadata.json`", "Usage Patterns", "scope hint",
                  "`scope=<path>` on a batch line", "stays a library"):
        assert token in shape, token
    for signal in ("`module.yaml`", "`module-help.csv`", "`scope_hint`"):
        assert signal in sniff, signal


def test_quick_skill_batch_refuses_the_single_target_overrides():
    """#609: `--description` and `--exports` never reach every target of a batch.

    The doc gives the exit code and halt reason batch-mode.md raises before the batch starts
    (SKILL.md On Activation step 5 loads it first under `--batch`).
    """
    before = _slice(_read(BATCH_MODE), "## Before the Batch Starts", "## Input format")
    halt = re.search(r"HARD HALT with \*\*exit code (\d+) \(([a-z-]+)\)\*\*", before)
    assert halt, "the --batch refusal halt not found in batch-mode.md"
    code, reason = halt.groups()
    section = _quick_section()
    assert "globally to every target" not in section
    overrides = _slice(section, "**Per-target overrides**", "**Safety:**")
    heading = overrides.splitlines()[0]
    assert "`--skip-snippet` and `--no-active-pointer` also apply to every target in `--batch`" in heading
    for flag in ("--description", "--exports"):
        [row] = [line for line in overrides.splitlines() if line.startswith(f"- `{flag} ")]
        assert row.endswith("Single-target runs only."), row
    refusal = _paragraph(overrides, "`--description` and `--exports` do not combine with `--batch`")
    assert f"exit `{code}` (`{reason}`)" in refusal
    for token in ("before its first target", "writes no batch summary", "run it on its own"):
        assert token in refusal, token
    assert "no batch summary is written" in before


def test_quick_skill_exit_code_map_matches_the_halt_contract():
    """The headless exit-code map in the docs is halt-contract.md's, code for code (exit 2 included)."""
    contract = _slice(_read(HALT_CONTRACT), "## Exit Codes", "## Result Contract on HARD HALT")
    doc = _slice(_read(WORKFLOWS), "**Exception: `/skf-quick-skill` headless", "3. **Error-variant result contract")
    expected = _exit_codes(contract)
    assert expected.get("2") == "input-invalid"
    assert _exit_codes(doc) == expected


# --------------------------------------------------------------------------
# Refine Architecture: the derived-scope gate and the Refinement Summary
# --------------------------------------------------------------------------


def test_refine_architecture_documents_the_scope_confirmation():
    """#610: the section describes the gate gap analysis shows for a derived scope, and its headless default."""
    gate = _slice(_read(RA_REFS / "gap-analysis.md"), "**Confirm a derived scope.**", "**Technologies with no skill.**")
    for token in ("Type **C** to keep this scope", "Type skill names to bring them **into** scope",
                  "Type **-skill_name** to take a skill **out** of scope",
                  "keep the derived sets and auto-proceed with [C]",
                  "Pairs, VS verdicts and improvement suggestions that involve an out-of-scope skill are listed for "
                  "awareness only and stay out of the refined document."):
        assert token in gate, token
    section = _ra_section()
    assert "Gap analysis (confirms a derived scope)" in section
    scope = _paragraph(section, "**Scope:**")
    for token in ("`--scope-skills`", "type `C` to keep the scope", "a skill's name to bring it in",
                  "`-<name>` to take it out", "A headless run keeps the derived scope and logs that decision",
                  "VS verdicts and improvement suggestions that involve an out-of-scope skill are listed for awareness "
                  "only and stay out of the refined document"):
        assert token in scope, token


def test_refine_architecture_documents_the_summary_rows_and_next_step():
    """#610: the rows the section names are rows compile writes, and so is the [CS] or [QS] next step."""
    summary = _slice(_read(RA_REFS / "compile.md"), "### 5. Add Refinement Summary Section", "### 6.")
    rows = re.findall(r"^\| ([^|]+?) \| \{", summary, re.M)
    output = _paragraph(_ra_section(), "**Output:**")
    for row in ("Not verified (no skill)", "VS Coverage"):
        assert row in rows, row
        assert f"`{row}`" in output, row
    assert "**[CS] Create Skill** or **[QS] Quick Skill** and re-run **[RA]** first" in summary
    for token in ("`@Ferris CS` or `@Ferris QS`", "run RA again before Stack Skill",
                  "when RA used one", "the document mentions but no skill covers"):
        assert token in output, token


# --------------------------------------------------------------------------
# Skill model: confidence_tier scales, a stack's distribution and where an update records itself
# --------------------------------------------------------------------------


def _validate_output():
    spec = importlib.util.spec_from_file_location("skf_validate_output_user_docs", VALIDATE_OUTPUT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tier_verdict(gate, skill_type: str, tier: str) -> str:
    """How the export gate takes `tier` in a `skill_type` skill: accepted, warned or rejected."""
    required, enums, _ = gate({"name": "demo", "version": "1.0.0", "skill_type": skill_type,
                               "source_authority": "community", "exports": ["demo"],
                               "generation_date": "2026-09-30", "confidence_tier": tier})
    if any(issue["field"] == "confidence_tier" for issue in enums):
        return "rejected"
    if any(issue["field"] == "confidence_tier" for issue in required):
        return "warned"
    return "accepted"


def _tiers(words: str) -> list[str]:
    """The names in a list such as "Quick, Forge, Forge+ or Deep"."""
    return re.split(r", | or ", words)


def test_skill_model_gives_confidence_tier_the_export_gate_scales():
    """#552: a single skill holds its forge tier, a stack the dominant confidence tier of its libraries.

    The export gate accepts exactly those scales, and takes a stack's forge tier with a warning.
    """
    paragraph = _paragraph(_read(SKILL_MODEL), "Two fields are easy to mix up.")
    single = re.search(r"holds the forge tier a single skill like this one was compiled at \(([^)]+)\)", paragraph)
    stack = re.search(r"A stack skill records there the dominant confidence tier of its libraries \(([^)]+)\)",
                      paragraph)
    assert single and stack, paragraph
    forge_tiers, stack_tiers = _tiers(single.group(1)), _tiers(stack.group(1))
    gate = _validate_output().validate_metadata_export_gate
    for tier in forge_tiers:
        assert _tier_verdict(gate, "single", tier) == "accepted", tier
        assert _tier_verdict(gate, "stack", tier) == "warned", tier
    for tier in stack_tiers:
        assert _tier_verdict(gate, "stack", tier) == "accepted", tier
        assert _tier_verdict(gate, "single", tier) == "rejected", tier
    assert "keeps its forge tier in `forge_tier`" in paragraph
    assert ("Export Skill still accepts a forge tier from a stack made by an earlier SKF version, with a warning "
            "that running Stack Skill again records the dominant tier") in paragraph
    template = _read(SRC / "skf-create-stack-skill" / "assets" / "stack-skill-template.md")
    assert f'"forge_tier": "{{{"|".join(forge_tiers)}}}"' in template
    assert f'"confidence_tier": "{{{"|".join(stack_tiers)}}}"' in template


def test_skill_model_says_what_a_stack_distribution_counts(tmp_path):
    """#528: a stack's `confidence_distribution` counts each library once, so its bins sum to `library_count`.

    The stack validator checks that sum, so bins that count provenance entries instead are an issue.
    """
    paragraph = _paragraph(_read(SKILL_MODEL), "Two fields are easy to mix up.")
    assert ("In a stack it counts each library once, by the library's tier, so its bins sum to `library_count`."
            in paragraph)
    validate_stack_counts = _validate_output().validate_stack_counts
    meta = {"library_count": 3, "integration_count": 0}
    for bins, fits in (({"t1": 2, "t1_low": 1, "t2": 0, "t3": 0}, True),
                       ({"t1": 15, "t1_low": 7, "t2": 0, "t3": 0}, False)):  # 22 provenance entries, 3 libraries
        issues, _ = validate_stack_counts(tmp_path, {**meta, "confidence_distribution": bins})
        assert any(issue["field"] == "confidence_distribution" for issue in issues) != fits, bins


def test_skill_model_says_where_an_update_records_itself():
    """#548: an update writes `last_update` and `update_type` into provenance-map.json, never into metadata.json."""
    write = _read(UPDATE_WRITE)
    metadata = _slice(write, "### 2. Write Updated metadata.json", "### 3.")
    assert "Write neither key into metadata.json" in metadata
    provenance = _slice(write, "### 3. Write Updated provenance-map.json", "### 4.")
    for key in ('"last_update"', '"update_type"'):
        assert key in provenance, key
    doc = _read(SKILL_MODEL)
    excerpt = _slice(doc, "```json\n{\n  \"name\": \"oms-cognee\"", "\n```\n")
    assert "last_update" not in excerpt and "update_type" not in excerpt
    omitted = _paragraph(doc, "Fields omitted from this excerpt for brevity:")
    for token in ("a `last_update` that an earlier SKF version wrote",
                  "records `last_update` and `update_type` at the top level of `provenance-map.json`",
                  "an update removes both from `metadata.json`", "`generation_date`"):
        assert token in omitted, token


# --------------------------------------------------------------------------
# Troubleshooting and the Ferris page
# --------------------------------------------------------------------------


def test_troubleshooting_names_ferris_install_halts_and_the_installer():
    """#608: Ferris stops on a missing config, or on missing scripts, as setup does, and all name the installer."""
    forger = _read(FORGER_SKILL)
    guard = _slice(forger, "1. **Config guard.**", "\n").replace("**", "")
    scripts = _slice(forger, "2. **Preflight.**", "Otherwise run it once").replace("**", "")
    ki = _slice(forger, "- **KI**:", "\n")
    entry = _slice(_read(TROUBLESHOOTING), '### "Setup cannot proceed: `_bmad/skf/config.yaml` was not found"',
                   "\n### ")
    for halt, source in (("Cannot initialize. SKF is not installed in this project", guard),
                         ("Cannot initialize. SKF's scripts are missing from this project", scripts)):
        assert halt in source, halt
        assert f'"{halt}"' in entry, halt
    for command in INSTALLERS:
        for name, text in (("config guard", guard), ("missing scripts", scripts), ("KI", ki),
                           ("troubleshooting", entry)):
            assert command in text, (name, command)
    for token in ("setup reads the file and never writes it, and only the installer does",
                  "start Ferris again and give him SF", "KI says so when the knowledge index is missing",
                  "Ferris names the file and the parser error"):
        assert token in entry, token


def test_agents_doc_lists_the_first_run_paths_ferris_highlights():
    """Ferris's first-run greeting and the Ferris page name the same starting points, in the same order."""
    greeting = _slice(_read(FORGER_SKILL), "5. **Greet, then wait.**", "\n")
    paths = BOLD_PATH_RE.findall(_slice(greeting, "On a first run", "Otherwise"))
    assert "forge-auto `<repo-or-doc-url>`" in paths
    doc = _paragraph(_read(AGENTS), "On your first run")
    assert BOLD_PATH_RE.findall(doc) == paths
    assert f"points you to {NUMBER_WORDS[len(paths)]} places to start" in doc


def test_agents_doc_says_what_ws_ends_with():
    """WS lists each skill's stage, then the next code for each skill in flight; the menu row says the same."""
    ws = _slice(_read(FORGER_SKILL), "- **WS**:", "## Pipeline Mode")
    stages = re.search(r"List each skill with its stage (\([^)]+\))", ws)
    assert stages, "WS stage list not found"
    assert "then end with the recommended codes" in ws
    [row] = [line for line in _read(AGENTS).splitlines() if line.startswith("| 17 | WS |")]
    assert f"Show where each skill stands {stages.group(1)}" in row
    assert "the next code to run for each skill in flight" in row


def test_agents_doc_describes_the_second_workflow_offer():
    """A single code picked after another workflow ran first offers a fresh session or a pipeline."""
    dispatch = _slice(_read(FORGER_SKILL), "- **Any other single code**", "\n")
    for token in ("When another workflow already ran in this session", "the command to paste into a fresh session",
                  "the remaining steps chained now as a pipeline", "in place only when the user asks for that"):
        assert token in dispatch, token
    menu = _paragraph(_read(AGENTS), "Ferris shows his menu as a numbered table")
    for token in ("after another workflow already ran in the same session", "the command to paste into a new session",
                  "the remaining steps chained as a pipeline", "runs it in place only if you ask"):
        assert token in menu, token
