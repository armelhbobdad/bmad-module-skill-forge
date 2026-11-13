#!/usr/bin/env python3
"""Prose pins: create-stack-skill's step rules match the writes, links and
compose branch of the sections they govern.

- A link resolves from the file that holds it. The template's SKILL.md
  blocks link a per-library file as `references/{name}.md`; the extracted
  `references/stack-catalog.md` sits beside those files, so its links
  resolve inside `references/`. Every place that moves the catalog there
  (the template's sizing guidance, compile-stack §4 and §6, generate-output
  §3 and its pre-commit body split, validate §3's post-commit split) states
  the file-relative form (#535).
- validate.md's Rules drop "read-only" and name §3's writes, and no other
  section of the step writes to the committed package (#536).
- detect-integrations §1 opens with the compose-mode guard, which skips to
  §3 ahead of the pair-intersect pass that needs step 3's per-library file
  lists (#537, #1151).
- report.md's Rules allow the result contract and keep the rest on the
  console; a missing atomic writer records a warning instead of halting
  (#539).
- generate-output writes the evidence report after the pre-commit gate,
  the gate records its warnings in `workflow_warnings[]`, the report lists
  that accumulator, and nothing later in the run tells the agent to add to
  the written report (#585, create-stack part).
- Every in-file anchor link names a heading. (That no step keeps a blanket
  no-write rule ahead of a write one of its sections makes is checked for
  every workflow in test-skf-chain-reachability.py.)
- Labels follow the tool at every forge tier: step 4 returns one labeled
  record per export, relative to step 1's project root, relabels the
  records in code mode with skf-render-stack-metadata.py `relabel`, which
  runs skf-render-metadata-stats.py's check and reruns it itself (§3a), and
  makes a library T1 only when an ast-grep rule matched every export it
  recorded; the stack provenance schema holds step 4's labels and no node
  kind; step 7 writes the code-mode map's entries from the records with the
  same helper and runs the provenance verifier on it, which moves the lines
  with one answer (#555, #606).
- A stack's metadata.json bins each library once, so its distribution sums
  to library_count, and the approval preview and final report show those
  library bins, T3 included; the evidence report bins the provenance
  entries with the stats helper (#528).
- A compose-mode constituent's tier is the enumerate helper's evidence_tier,
  each of its entries carries that tier, and every pair takes the weaker
  tier, T2 and T3 included (#534).
- Step 7's pre-commit gate runs skf-names-present.py on the compose-mode
  map before the commit, and that helper applies the text match
  skf-test-skill scores names by (#538); skf-test-skill also needs the
  name's inventory entry, which the gate runs too early to check (#1068).
- One tier rule: step 5 §3 takes each pair's tier from
  skf-render-stack-metadata.py (and halts with its envelope when the helper
  is missing), compose-mode-rules and integration-patterns point at it, and
  no step file restates the tier ordering; step 7 §6 takes metadata.json's
  counts, lists, distribution, dominant tier and source_authority from it,
  with the authority step 2 records; step 8 reads the validator's stack
  structure pass instead of checking headings, keys and labels by hand, and
  runs it again after §3 changes the package (#606).
- Compose-mode pairs are candidates: the co-mention helper leaves out the
  pairs a document only lists together and counts them, so compose-pairs.md
  §1 records one warning, confirms the rest from their excerpts, finds pairs
  with no architecture document by docs mentions or shared keywords (never
  a shared language) and judges those too, writes each pair in an evidence
  format whose label the structure pass reads, and locates the [VS] report
  with --locate, an unknown verdict token staying a hard error (#582,
  #590). The pair's bundle entry keeps that evidence and its VS verdicts
  (`evidence`, `reference`, `vs`), and steps 6 and 7 render a compose pair
  from them in the evidence format, a `[VS: Blocked]` pair still carrying
  the label the structure pass reads (step 5b run 2 architecture-1).
- Step 7 §1 takes the stack version from skf-skill-inventory.py `version`
  (#597), and §5 measures the snippet with skf-count-tokens.py, the count
  the validator takes (#591).
- Step 1 binds every input the Invocation Contract declares and halts with
  `input-invalid` on one it cannot use (#594); `stack_name` names every path
  and envelope, and every envelope carries the skill-check `quality_score`
  (#586). `{scan_root}` comes from `project_path` or one question, and the
  step 2 scan, the step 3 import counts and the step 5 co-import pairs stay
  inside it (#606 item 5). Step 1 checks a requested stack name with the
  validator step 7 runs, after `-stack` is appended.
- Step 1 and step 2 pick compose-mode skills with the enumerate helper's
  candidates mode, never by hand (#606 item 4); step 3 counts imports with
  skf-count-imports.py, step 2 shows what the scanner searched and splits
  runtime from dev by `scope`, and step 5 pipes step 3's counts to the pair
  helper, whose pairs carry their co-import files and lines, instead of
  grepping again (#598). Every path the run records is relative to the
  project root.
- Every HARD HALT names its exit code, `halt_reason` and phase, and each
  halting step shows the shared emitter's emit-halt command; no step types
  an `SKF_STACK_RESULT_JSON` line. A shared helper that resolves to no path
  halts `helper-missing` (exit 3), an unknown verdict token
  `unknown-verdict-token` (exit 2), and the schema lists exactly the
  reasons the steps raise. Each headless gate records its decision in the
  run sink, the scope gate naming every library it drops, and step 9 writes
  the result files and the success line through the emitter (#593).
- The run folder holds the run's state: step 3's import counts, step 4's
  extraction bundle and the checked export records, which steps 4 to 7 read
  from disk, and step 6's draft, reviewed by path and staged verbatim; only
  a finished or cancelled run deletes it. Step 4 takes each library's tier
  from skf-render-stack-metadata.py library-tiers and step 6 its counts, the
  description's included, from the metadata projection (#587, W3 handoffs).
  Each warning reaches the run sink as text through a staged file, every
  step that warns shows the record command, and the facts the evidence
  report lists are warnings there.
- Step 5 saves the pair helper's result and step 4 the enumerate helper's
  in the run folder, and step 7 writes the provenance map from them with
  skf-render-stack-metadata.py in both modes: the helper copies each pair's
  co-import files and each constituent's hash, so no step types them, and
  an audit finds every constituent of a stack built under a skills folder
  that is not the default one fresh (step 5b determinism-2, determinism-3).
- The co-mention helper filters on no meaning: one paragraph makes a
  candidate, an introductory section marks its evidence `excluded_section`,
  step 5 judges both from the excerpt, and a document that names no pair
  warns (step 5b determinism-1). compile-stack leaves the frontmatter, the
  catalog sizing and the reference index to the template, which holds the
  one description form (step 5b leanness-1).
- The scope is confirmed at one gate, and a missing comention helper halts
  instead of a hand scan (#599). customize.toml keeps only the template and
  integration-pattern paths, and the metadata.json contract is fixed in
  assets/metadata-contract.md (#596). The constituent hash anchor is stated
  once, in step 4, and generate-output states each rule once (#600).
- Step 8 §9 reads skill-check's JSON, not its exit code: a security scan
  that did not finish (exit 2, or a scan tail on stderr with no finding
  code) is a note in the validation results, never a WARNING finding, and
  §10 lists each §9 note whether or not the run had findings (#885).
- Step 8 §3 hashes SKILL.md before and after `skill-check --fix`, since
  skill-check 1.2.0's JSON lists no fix: a changed or unhashed SKILL.md
  raises S15 and runs the §1 validator again, and the step still has no
  HALT (#901).
- Each warning stage states the whole record rule, the file write and,
  after step 1, the emitter fallback its frontmatter backs; SKILL.md keeps
  the entry shape and the sink, binds its three scalars in Quick Skill's
  shape and keeps no ticket tag. Step 1 saves its bindings to `run.json`,
  which step 2 updates and steps 7 and 8 read the tier from, and an
  interactive run can resume at step 6's review gate (#1150).
- A compose-mode run reads its own stage files, routed by
  `composeNextStepFile`, and passes through one guard in rank-and-confirm
  and detect-integrations; a subagent reads each constituent's SKILL.md and
  returns only its description keywords, usage patterns and signatures,
  which step 5 reads from the bundle; compose-mode-rules keeps three
  sections and compile-stack states §3 as one goal and §7 as one
  invitation (#1151).
- The scope gate checks the scope before it shows the gate and after each
  change: an empty one offers no [C] and halts a headless run with
  `empty-scope` (exit 2) before any decision is recorded. Step 1 runs the
  ownership check on the stack's folder and saves the published stack's
  version and libraries in `run.json`; on a rerun step 3 keeps each
  published library the counts still find, marks each row kept or new,
  lists the published libraries it leaves out and records the keeps as
  `prior_kept`, and step 7 versions from step 1's read (#1152).
- Step 3 takes the scope from skf-count-imports.py `scope` in both modes
  and writes it to `{scopeFile}`, which the Left out table, a rerun's
  Dropped line and the headless decision read; each unknown override
  records `scope-override-unknown`. A known import name reruns the count
  with `--module`, and compose-scope.md takes each skill's layer candidates
  from skf-comention-pairs.py `mentions`, warning when it cannot run
  (#1153).

The step calls run as written, on small fixtures.

The pins check what the steps do rather than how a sentence is worded, so a
later change can reword these sections and still pass. Every slicer asserts
that its markers exist and that the slice is not empty, so a renamed
heading fails instead of passing vacuously.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STACK = REPO_ROOT / "src" / "skf-create-stack-skill"
REFS = STACK / "references"
TEMPLATE = STACK / "assets" / "stack-skill-template.md"
SCHEMA = STACK / "assets" / "provenance-map-schema.md"
COMPILE = REFS / "compile-stack.md"
GENERATE = REFS / "generate-output.md"
VALIDATE = REFS / "validate.md"
DETECT = REFS / "detect-integrations.md"
REPORT = REFS / "report.md"
EXTRACT = REFS / "parallel-extract.md"
MANIFESTS = REFS / "detect-manifests.md"
COMPOSE_RULES = REFS / "compose-mode-rules.md"
# Steps 2 to 5 of a compose-mode run (#1151): rank-and-confirm.md and detect-integrations.md each hold one
# compose guard, the scope gate and the pair classification staying their one home.
COMPOSE_SKILLS = REFS / "compose-skills.md"
COMPOSE_SCOPE = REFS / "compose-scope.md"
COMPOSE_EXTRACT = REFS / "compose-extract.md"
COMPOSE_PAIRS = REFS / "compose-pairs.md"
STACK_SKILL = STACK / "SKILL.md"
CONTRACT = REFS / "invocation-contract.md"
METADATA_CONTRACT = STACK / "assets" / "metadata-contract.md"
CUSTOMIZE = STACK / "customize.toml"
STEP_FILES = sorted(REFS.glob("*.md"))
TIERS = REPO_ROOT / "src" / "knowledge" / "confidence-tiers.md"
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
STATS_HELPER = SCRIPTS / "skf-render-metadata-stats.py"
VERIFIER = SCRIPTS / "skf-verify-provenance-completeness.py"
ENUMERATE = SCRIPTS / "skf-enumerate-stack-skills.py"
HASH_CONTENT = SCRIPTS / "skf-hash-content.py"
NAMES_HELPER = SCRIPTS / "skf-names-present.py"
STACK_METADATA = SCRIPTS / "skf-render-stack-metadata.py"
COMENTION = SCRIPTS / "skf-comention-pairs.py"
FEASIBILITY = SCRIPTS / "skf-validate-feasibility-report.py"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
VALIDATOR = SCRIPTS / "skf-validate-output.py"
COUNT_TOKENS = SCRIPTS / "skf-count-tokens.py"
INTEGRATION_PATTERNS = REFS / "integration-patterns.md"
INIT = REFS / "init.md"
RANK = REFS / "rank-and-confirm.md"
SCAN_MANIFESTS = SCRIPTS / "skf-scan-manifests.py"
COUNT_IMPORTS = SCRIPTS / "skf-count-imports.py"
PAIR_INTERSECT = SCRIPTS / "skf-pair-intersect.py"
FRONTMATTER = SCRIPTS / "skf-validate-frontmatter.py"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
ENVELOPE_SCHEMA = SCRIPTS / "schemas" / "skf-stack-result-envelope.v1.json"
RECONCILE = REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "reconcile-coverage.py"
NUMERATOR = REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "verify-declared-numerator.py"

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6}) (.+)$", re.MULTILINE)
SECTION_HEADING_RE = re.compile(r"^### (\d+[a-z]?)\. (.+)$", re.MULTILINE)
ANCHOR_LINK_RE = re.compile(r"\]\(#([^)\s]+)\)")
SKIP_LINK_RE = re.compile(r"Skip to \[[^\]]+\]\(#([^)\s]+)\)")
PER_LIBRARY_FILE = "references/{name}.md"
CATALOG_FILE = "references/stack-catalog.md"
# A per-library link written file-relative, as step prose quotes it:
# `[ref]({name}.md)`, `{name}.md` or `{library}.md`.
FILE_RELATIVE_LINK_RE = re.compile(r"`(?:\[ref\]\()?\{(?:name|library)\}\.md\)?`")
PAIR_INTERSECT_RE = re.compile(r"pairIntersect|skf-pair-intersect")
GATE_RUN_RE = re.compile(r"^[ \t]*(?:uv run|python3) \{frontmatterValidator\}", re.MULTILINE)
EVIDENCE_REPORT = "evidence-report.md"
# Instructions that change a file: the atomic writer's subcommands, the
# skill-check writes and a directory create. A flag counts only whole, so
# the inventory's read-only `--write-check` is not a write.
WRITE_OP_RE = re.compile(
    r"\{atomicWriteHelper\}\s+(?:write|stage-dir|commit-dir|flip-link)\b"
    r"|--fix(?![\w-])|--write(?![\w-])|\bsplit-body\b|\bmkdir -p\b"
)
# Rules wording that forbids every write, or every change to what a step reads.
BLANKET_NO_WRITE_RE = re.compile(
    r"read-only|do not write or modify|do not modify|do not write output files|no [^.\n]*file writes",
    re.IGNORECASE,
)
# An instruction to put something into the evidence report.
ADD_TO_EVIDENCE_REPORT_RE = re.compile(
    r"\b(?:record|note|add|log|write|append|put)\w*\b[^.\n]*\b(?:in|into|to) the evidence report\b",
    re.IGNORECASE,
)
# Tiers from the strongest to the weakest: T1-low is weaker than T1, T2 than
# T1-low, T3 than T2.
TIER_ORDER = ("T1", "T1-low", "T2", "T3")
TIER = r"(T1-low|T1|T2|T3)"
# A worked pair case of the compose rule: "a T1 + T2 or T1-low + T2 pair is T2".
PAIR_CASE_RE = re.compile(rf"{TIER} \+ {TIER}(?: or {TIER} \+ {TIER})? pair is {TIER}")
PROBE_ITEM_RE = re.compile(r"^\s+-\s*'\{project-root\}/src/([^']+)'\s*$")
# One export label pairing of step 4 §1.
PAIRING_RE = re.compile(
    r'`extraction_method: "(\w+)"`, `confidence: "([\w-]+)"`, `signature_source: "([\w-]+)"`')
# A pointer at the compose tier matrix the weaker-tier rule replaced.
OLD_MATRIX_RE = re.compile(r"Inheritance\**\s+matrix|matrix above")
# Prose that restates the tier ordering skf-render-stack-metadata.py holds:
# an ordering of two tiers, a worked pair case, a tie-break or the authority
# order.
ORDERING_RE = re.compile(
    r"T1-low\s*>\s*T1\b|T2\s*>\s*T1-low|T3\s*>\s*T2|\bis weaker than\b|\btie-break\b.*T1|highest count"
    r"|official\s*>\s*community|" + PAIR_CASE_RE.pattern,
    re.IGNORECASE,
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


def _from(text: str, start: str) -> str:
    assert text.count(start) == 1, f"marker not found exactly once: {start!r}"
    return text[text.index(start):]


def _h2_section(text: str, heading: str) -> str:
    """A `## ` section of the template, up to the next H2 outside a fenced block."""
    lines = text.splitlines(keepends=True)
    starts = [k for k, line in enumerate(lines) if line.rstrip("\n") == heading]
    assert len(starts) == 1, f"heading not found exactly once: {heading!r}"
    kept, in_fence = [lines[starts[0]]], False
    for line in lines[starts[0] + 1:]:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            break
        kept.append(line)
    section = "".join(kept)
    assert section.strip() != heading, f"empty section: {heading!r}"
    return section


def _first_fence(section: str) -> str:
    """The body of the first fenced block, which may sit indented in a list item."""
    match = re.search(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", section, flags=re.DOTALL | re.MULTILINE)
    assert match, "no fenced block in the section"
    return match.group(1)


def _rules(text: str) -> str:
    return _slice(text, "## Rules\n", "\n## ")


def _body(text: str) -> str:
    """Everything after the Rules block: the sections the Rules govern."""
    rules = _rules(text)
    return text[text.index(rules) + len(rules):]


def _sections(text: str) -> dict[str, str]:
    """`### N.` sections of a step file, keyed by their number (`8b` included)."""
    matches = list(SECTION_HEADING_RE.finditer(text))
    assert matches, "no numbered sections"
    return {
        m.group(1): text[m.start(): matches[k + 1].start() if k + 1 < len(matches) else len(text)]
        for k, m in enumerate(matches)
    }


def _section_with(text: str, pattern: re.Pattern[str]) -> str:
    """The one numbered section of a step file's body that matches `pattern`."""
    hits = [section for section in _sections(_body(text)).values() if pattern.search(section)]
    assert len(hits) == 1, f"{len(hits)} sections match {pattern.pattern!r}, expected 1"
    return hits[0]


def _slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _resolved_links(block: str, holder_dir: str) -> list[str]:
    """Each link target in `block`, resolved from the folder of the file that holds it."""
    return [posixpath.normpath(posixpath.join(holder_dir, target)) for target in LINK_RE.findall(block)]


def _evidence_writes(text: str) -> list[re.Match[str]]:
    """Lines that write the evidence report."""
    return [
        line for line in re.finditer(r"^.*$", text, re.MULTILINE)
        if EVIDENCE_REPORT in line.group(0) and WRITE_OP_RE.search(line.group(0))
    ]


def _chunks(text: str) -> list[str]:
    """The text ahead of the first `### N.` heading, then each numbered section."""
    starts = [0, *(m.start() for m in SECTION_HEADING_RE.finditer(text)), len(text)]
    return [text[a:b] for a, b in zip(starts, starts[1:]) if text[a:b].strip()]


# --- #535: catalog links resolve from references/ ------------------------------


def test_skill_md_links_resolve_from_the_skill_root():
    template = _read(TEMPLATE)
    structure = _first_fence(_h2_section(template, "## SKILL.md Section Structure"))
    sizing = _h2_section(template, "## Sizing Guidance for Large Stacks")
    pointer = _first_fence(_from(sizing, "- **Inline pointer form**"))
    assert PER_LIBRARY_FILE in _resolved_links(structure, "")
    assert CATALOG_FILE in _resolved_links(pointer, "")


def _catalog_section() -> str:
    return _h2_section(_read(TEMPLATE), "## references/stack-catalog.md Structure")


def test_catalog_links_resolve_inside_references():
    resolved = _resolved_links(_first_fence(_catalog_section()), posixpath.dirname(CATALOG_FILE))
    assert PER_LIBRARY_FILE in resolved, resolved
    assert not [path for path in resolved if path.startswith("references/references/")], resolved


def test_catalog_structure_does_not_copy_the_inline_links():
    prose = _catalog_section().split("```", 1)[0]
    assert "verbatim" not in prose, "the catalog cannot copy the inline links verbatim"
    assert FILE_RELATIVE_LINK_RE.search(prose), "the catalog structure does not give the file-relative link"


def test_each_per_library_summary_links_its_reference_file():
    """compile-stack §4 leaves the summary form to the template (step 5b leanness-1), so the template
    gives every summary its reference link, in the form the file that holds it resolves (#535)."""
    template = _read(TEMPLATE)
    inline = _slice(_first_fence(_h2_section(template, "## SKILL.md Section Structure")),
                    "## Per-Library Summaries", "\n## Conventions")
    catalog = _from(_first_fence(_catalog_section()), "## Per-Library Summaries")
    assert _resolved_links(inline, "") == [PER_LIBRARY_FILE], inline
    assert _resolved_links(catalog, posixpath.dirname(CATALOG_FILE)) == [PER_LIBRARY_FILE], catalog


def test_the_template_holds_the_one_description_form():
    """Step 5b leanness-1: the template's frontmatter carries the description with its negative
    trigger, and compile-stack §2 defers to it instead of typing the description again."""
    structure = _first_fence(_h2_section(_read(TEMPLATE), "## SKILL.md Section Structure"))
    frontmatter = structure.split("\n---\n", 1)[0]
    assert "description:" in frontmatter and "NOT for:" in frontmatter, frontmatter
    compile_ = _read(COMPILE)
    assert "NOT for" not in compile_, "compile-stack types the description's negative trigger again"
    assert "template's frontmatter" in _sections(_body(compile_))["2"]


CATALOG_MOVES = {
    "template-sizing-guidance": None,
    "compile-stack-4": (COMPILE, "4"),
    "compile-stack-6": (COMPILE, "6"),
    "generate-output-3": (GENERATE, "3"),
    "generate-output-8-pre-commit-split": (GENERATE, "8"),
    "validate-3-post-commit-split": (VALIDATE, "3"),
}


def _catalog_move(where: str) -> str:
    """The text of one place that moves the catalog into references/stack-catalog.md."""
    if CATALOG_MOVES[where] is None:
        sizing = _h2_section(_read(TEMPLATE), "## Sizing Guidance for Large Stacks")
        return _slice(sizing, "- **Catalog placement.**", "\n- **")
    path, number = CATALOG_MOVES[where]
    return _sections(_body(_read(path)))[number]


@pytest.mark.parametrize("where", sorted(CATALOG_MOVES))
def test_every_catalog_move_gives_the_file_relative_link(where):
    text = _catalog_move(where)
    assert CATALOG_FILE in text, f"{where} no longer moves the catalog into {CATALOG_FILE}"
    assert FILE_RELATIVE_LINK_RE.search(text), f"{where} moves the catalog without its file-relative links"


# --- #536: validate.md names its only package writes -----------------------------


def test_validate_rules_name_the_section_3_writes():
    rules = _rules(_read(VALIDATE))
    assert not BLANKET_NO_WRITE_RE.search(rules), "validate.md's Rules still call the step read-only"
    for needle in ("§3", "--fix", "split-body"):
        assert needle in rules, needle


def test_only_validate_section_3_writes_the_package():
    sections = _sections(_body(_read(VALIDATE)))
    writers = {number for number, section in sections.items() if WRITE_OP_RE.search(section)}
    assert writers == {"3"}, f"validate.md sections that write: {sorted(writers)}"


# --- #885, #892: the scan runs through skf-security-scan.py; a skipped scan is a note ----


def test_security_scan_notes_a_scan_that_could_not_run():
    sections = _sections(_body(_read(VALIDATE)))
    nine = sections["9"]
    assert nine.startswith("### 9. Security Scan\n\nRun the scan whether or not skill-check is available.")
    # skill-check 1.2.0 passes none of the scanner's findings on, so the helper runs the scan (#892).
    assert 'uv run {securityScanHelper} run --package "<skill-dir>"' in _first_fence(nine)
    assert "npx skill-check" not in nine
    assert "reads the scanner's own JSON report, so rely on the JSON it prints, never on an exit code." in nine
    assert ("Record each `findings[]` entry's `text` as an advisory **WARNING** finding: security findings do not "
            "block the report.") in nine
    assert ('Record its `note` in the §10 validation results, as "security scan: {note}" for `pass` and `warn` and '
            'as "security scan skipped: {note}" for `skipped`.') in nine
    assert ('When no `{securityScanProbeOrder}` path exists, record no finding, only the §10 note "security scan '
            'skipped: skf-security-scan.py missing"') in nine
    for stale in ("finding code", "skill-check.stderr", "(#892)", "**Could not run:**", "**If unavailable:**",
                  "security[]", "mcp-scan"):
        assert stale not in nine, stale
    # skill-check's own sections no longer name the scan.
    two = sections["2"]
    assert "- If exits 0: Use skill-check for automated validation in section 3." in two
    assert '`message: "skill-check unavailable: manual fallback checks used"`' in two
    # §10 lists the §9 note whether or not the run had findings.
    ten = sections["10"]
    assert ten.index("If all checks passed") < ten.index("If there were findings") < ten.index(
        "In both cases, list each §9 security scan note.")


# --- #537: no pair-intersect pass in compose mode -------------------------------


def test_pair_intersect_pass_skips_in_compose_mode():
    """#537, #1151: compose-pairs.md found the pairs, so the guard skips both co-import passes to §3."""
    sections = _sections(_body(_read(DETECT)))
    first, third = sections["1"], sections["3"]
    opening = first.split("\n", 1)[1].lstrip("\n").split("\n", 1)[0]
    assert "compose_mode" in opening, f"§1 does not open with the compose-mode guard: {opening!r}"
    helper = PAIR_INTERSECT_RE.search(first)
    assert helper, "§1 lost the pair-intersect pass"
    heading = SECTION_HEADING_RE.match(third)
    assert heading, "§3 has no numbered heading"
    ahead = first[: helper.start()]
    assert _slug(f"{heading.group(1)}. {heading.group(2)}") in SKIP_LINK_RE.findall(ahead), (
        "the compose guard does not skip to §3 ahead of the pair-intersect pass"
    )


def test_section_2_holds_no_compose_branch():
    """#1151: the compose pairs come from compose-pairs.md, so §2 is the code-mode co-import pass alone."""
    two = _sections(_body(_read(DETECT)))["2"]
    assert not COMPOSE_MODE_RE.search(two), "§2 still holds a compose-mode branch"


# --- #539: report.md writes only the result contract ----------------------------


def test_report_rules_allow_the_result_contract():
    rules = _rules(_read(REPORT))
    assert not BLANKET_NO_WRITE_RE.search(rules), "report.md's Rules still forbid every write"
    assert "result contract" in rules.lower()
    assert "console" in rules.lower()


def test_report_missing_writer_warns_instead_of_halting():
    text = _read(REPORT)
    frontmatter = text.split("\n---\n", 1)[0]
    assert "atomicWriteProbeOrder" in frontmatter
    assert not re.search(r"\bHALT\b", frontmatter), "a missing atomic writer still halts the report"
    missing = [paragraph for paragraph in _body(text).split("\n\n") if "{atomicWriteProbeOrder}" in paragraph]
    assert len(missing) == 1, "no single paragraph handles a missing atomic writer"
    assert not re.search(r"\bHALT\b", missing[0])
    assert "workflow_warnings[]" in missing[0], "a skipped result contract leaves no warning entry"


# --- #585 (create-stack part): gate warnings reach the evidence report -----------


def test_evidence_report_is_written_after_the_pre_commit_gate():
    text = _read(GENERATE)
    gate = GATE_RUN_RE.search(text)
    assert gate, "generate-output no longer runs the pre-commit gate"
    writes = _evidence_writes(text)
    assert writes, "generate-output no longer writes the evidence report"
    early = [line.group(0).strip() for line in writes if line.start() < gate.start()]
    assert not early, f"evidence report written before the pre-commit gate: {early}"


def test_gate_warnings_reach_the_evidence_report():
    text = _read(GENERATE)
    gate = _section_with(text, GATE_RUN_RE)
    assert "workflow_warnings[]" in gate, "the gate does not record its warnings in workflow_warnings[]"
    first_write = _evidence_writes(text)[0].group(0)
    report = _section_with(text, re.compile(re.escape(first_write)))
    assert "workflow_warnings[]" in report, "the evidence report does not list workflow_warnings[]"
    assert "rollback" in report.lower(), "a failed evidence-report write no longer rolls back"


def test_nothing_is_added_to_the_written_evidence_report():
    # A section that writes the report again may add to it; any other
    # section after the write would add to a file that is already final.
    generate = _read(GENERATE)
    after_write = generate[_evidence_writes(generate)[-1].end():]
    for where, text in (
        ("generate-output after the evidence-report write", after_write),
        ("validate.md", _body(_read(VALIDATE))),
        ("report.md", _body(_read(REPORT))),
    ):
        hits = [
            match.group(0)
            for chunk in _chunks(text) if not _evidence_writes(chunk)
            for match in ADD_TO_EVIDENCE_REPORT_RE.finditer(chunk)
        ]
        assert not hits, f"{where} adds to the evidence report after it is written: {hits}"


def test_generate_output_rules_allow_the_gate_fixes():
    rules = _rules(_read(GENERATE))
    assert not BLANKET_NO_WRITE_RE.search(rules), "generate-output's Rules forbid the fixes the gate makes"
    assert "gate" in rules


# --- Shared helpers for the tier and provenance pins (#555, #528, #534, #538) ----


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "no frontmatter"
    return text[4:text.index("\n---\n", 4)]


def _probe_script(text: str, stem: str) -> Path:
    """The src/ script a step file's `<stem>ProbeOrder` frontmatter list binds."""
    lines = _frontmatter(text).splitlines()
    starts = [k for k, line in enumerate(lines) if line == f"{stem}ProbeOrder:"]
    assert len(starts) == 1, f"no single {stem}ProbeOrder list"
    for line in lines[starts[0] + 1:]:
        match = PROBE_ITEM_RE.match(line)
        if match:
            return REPO_ROOT / "src" / match.group(1)
        if not line.startswith(" "):
            break
    raise AssertionError(f"{stem}ProbeOrder names no src/ script")


def _fence_lines(section: str) -> list[str]:
    """The logical lines of a section's fenced blocks, backslash continuations joined."""
    lines, joined, fenced = [], "", False
    for line in section.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            continue
        if line.rstrip().endswith("\\"):
            joined += line.rstrip()[:-1] + " "
            continue
        lines.append(joined + line)
        joined = ""
    return lines


def _call(section: str, helper: str, subcommand: str | None = None) -> str:
    """The one fenced call of `{helper}` (with that subcommand) in a section."""
    calls = [line for line in _fence_lines(section) if f"{{{helper}}}" in line
             and (subcommand is None or f"{{{helper}}} {subcommand} " in line)]
    assert len(calls) == 1, f"{len(calls)} fenced {helper} {subcommand or ''} calls, expected 1"
    return calls[0]


def _argv(call: str, helper: str, values: dict[str, str]) -> list[str]:
    """The arguments of a documented call, split first and filled in after, so a
    Windows path keeps its backslashes."""
    args = shlex.split(call.split(f"uv run {{{helper}}}", 1)[1])
    filled = []
    for arg in args:
        for placeholder, value in values.items():
            arg = arg.replace(placeholder, value)
        assert "{" not in arg, f"placeholder left unfilled: {arg}"
        filled.append(arg)
    return filled


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _weaker(a: str, b: str) -> str:
    return max(a, b, key=TIER_ORDER.index)


# The code-mode library of #555: two ast-grep matches and a class read by eye,
# `get_config` recorded on its decorator line (10) instead of its `def` (13).
LIBA_API = (
    b'"""liba public API."""\n'
    b"\n"
    b"import functools\n"
    b"\n"
    b"\n"
    b'def connect(url: str) -> "Client":\n'
    b"    return Client(url)\n"
    b"\n"
    b"\n"
    b"@functools.lru_cache(\n"
    b"    maxsize=None,\n"
    b")\n"
    b"def get_config() -> dict:\n"
    b"    return {}\n"
    b"\n"
    b"\n"
    b"class Client:\n"
    b"    def __init__(self, url: str) -> None:\n"
    b"        self.url = url\n"
)


def _liba_records(client_tier: str = "T1-low") -> list[dict]:
    """Step 4's export records for liba, each with its library, as §3a writes them."""
    base = {"source_library": "liba", "source_file": "libs/liba/api.py", "params": []}
    return [
        dict(base, export_name="connect", export_type="function", source_line=6,
             extraction_method="ast_bridge", confidence="T1", signature_source="T1"),
        dict(base, export_name="get_config", export_type="function", source_line=10,
             extraction_method="ast_bridge", confidence="T1", signature_source="T1"),
        dict(base, export_name="Client", export_type="class", source_line=17,
             extraction_method="source_reading", confidence=client_tier, signature_source=client_tier),
    ]


# --- #555: labels follow the tool, checked in step 4 and step 7 ------------------


def _pairings() -> dict[str, tuple[str, str]]:
    """Step 4 §1's labels: extraction_method -> (confidence, signature_source)."""
    plan = _sections(_body(_read(EXTRACT)))["1"]
    found = PAIRING_RE.findall(plan)
    assert len(found) == 2, f"§1 states {len(found)} label pairings, expected the two methods once each"
    return {method: (confidence, signature) for method, confidence, signature in found}


def test_labels_follow_the_tool_at_every_tier():
    plan = _sections(_body(_read(EXTRACT)))["1"]
    assert not re.search(r"^- Confidence:", plan, re.MULTILINE), "a forge tier still sets the confidence"
    pairings = _pairings()
    assert pairings == {"ast_bridge": ("T1", "T1"), "source_reading": ("T1-low", "T1-low")}, pairings
    rules = _rules(_read(EXTRACT))
    assert "tool" in rules and "forge tier" in rules
    # The pairings pass the helper §3a checks them with.
    stats = _load(STATS_HELPER, "skf_render_metadata_stats_pairings")
    entries = [{"export_name": method, "extraction_method": method, "confidence": confidence,
                "signature_source": signature} for method, (confidence, signature) in pairings.items()]
    assert stats.check_label_agreement({"entries": entries}) == []


def test_the_worker_returns_one_labeled_record_per_export():
    launch = _sections(_body(_read(EXTRACT)))["2"]
    shape = _first_fence(launch)
    assert "exports_found" not in shape, "the worker still returns bare export names"
    records = shape[shape.index("exports: ["):shape.index("usage_patterns:")]
    for field in ("export_name", "source_file", "source_line", "extraction_method", "confidence",
                  "signature_source"):
        assert re.search(rf"^\s+{field}:", records, re.MULTILINE), field
    assert "{project_root}" in records, "source_file is not relative to step 1's project root"
    library_level = shape.replace(records, "")
    assert not re.search(r"^\s+confidence:", library_level, re.MULTILINE), (
        "the worker still returns a library tier; §3a sets it from the checked records")


def test_source_files_are_relative_to_step_1s_project_root():
    # {scan_root} may narrow the scan to one package, but a library's source
    # can sit outside it (a dependency hoisted to the root node_modules), so
    # every step that anchors source_file names step 1's project_root.
    assert "`project_root`" in _sections(_read(REFS / "init.md"))["1"]
    places = {
        "step 4 §2": _sections(_body(_read(EXTRACT)))["2"],
        "step 7 §7": _from(_sections(_body(_read(GENERATE)))["7"], "**Source lines (code mode only).**"),
        "the schema": _h2_section(_read(SCHEMA), "## Code-mode variant").split("```")[0],
    }
    for where, text in places.items():
        binding = [s for s in re.split(r"(?<=[.:]) ", text) if "{project_root}" in s and "`project_root`" in s]
        assert binding and "step 1" in binding[0], f"{where} does not bind {{project_root}} to step 1's project_root"
        assert "step 2 scanned" not in text, where


def _relabel_call() -> str:
    return _call(_sections(_body(_read(EXTRACT)))["3a"], "renderStackMetadataHelper", "relabel")


def test_the_label_check_runs_between_extraction_and_the_summary():
    text = _read(EXTRACT)
    # The stack helper runs the stats helper's check itself (W5 handoff, determinism-5).
    assert "renderMetadataStatsProbeOrder" not in _frontmatter(text)
    assert _probe_script(text, "renderStackMetadata") == STACK_METADATA
    sections = _sections(_body(text))
    order = list(sections)
    assert order.index("3") + 1 == order.index("3a") == order.index("4") - 1
    check = sections["3a"]
    call = _relabel_call()
    assert call.strip() == 'uv run {renderStackMetadataHelper} relabel --records "{exportRecordsFile}"', call
    for needle in ("`coherence.violations[]`", "`confidence_distribution`", "`relabeled[]`", "export-labels-relabeled",
                   "label-check-skipped"):
        assert needle in check, needle
    # The helper relabels and reruns the check: the step copies no `expected` value, runs no loop
    # and leaves the helper's own steps to its --help.
    for stale in ("run the helper again until", "Rewrite the file", "`expected` value", "until `coherence.ok`",
                  "rewrites the file", "sets each mislabeled field"):
        assert stale not in check, stale
    assert "§3a" in sections["4"], "§4 does not show the export label counts §3a kept"
    halt = '(exit 3, `halt_reason: "helper-missing"`, phase `parallel-extract:library-tiers`)'
    assert check.index(halt) < check.index(call), "the missing helper must halt before the relabel call"
    tiers = _from(check, "**Library tiers.**")
    assert "`per_library_extractions[].confidence`" in tiers and "`tier`" in tiers
    # The tier rule lives in the helper (W3 handoff): the step names no method or tier itself.
    assert "`ast_bridge`" not in tiers and "otherwise" not in tiers, "§3a still works the library tier out by hand"


def _library_tiers_call() -> str:
    return _call(_sections(_body(_read(EXTRACT)))["3a"], "renderStackMetadataHelper", "library-tiers")


def test_the_library_tier_call_runs_as_written(tmp_path):
    """#555 rule, one home: T1 only when an ast-grep rule matched every export of the library."""
    records = tmp_path / "run" / "export-records.json"
    records.parent.mkdir()
    entries = _liba_records() + [dict(_liba_records()[0], source_library="libb")]
    records.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    argv = _argv(_library_tiers_call(), "renderStackMetadataHelper",
                 {"{exportRecordsFile}": str(records), "<names>": "liba,libb,libc"})
    result = subprocess.run([sys.executable, str(STACK_METADATA), *argv], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    tiers = {row["name"]: row["tier"] for row in json.loads(result.stdout)["libraries"]}
    assert tiers == {"liba": "T1-low", "libb": "T1", "libc": "T1-low"}  # Client read by eye; libc recorded none


def test_the_records_file_lives_in_the_run_folder():
    """The checked records stay for step 7 in the run folder, which only a finished or cancelled run deletes."""
    text = _read(EXTRACT)
    assert re.search(r"^exportRecordsFile: '\{run_dir\}/[^']+\.json'$", _frontmatter(text), re.MULTILINE)
    assert re.search(r"^bundleFile: '\{run_dir\}/[^']+\.json'$", _frontmatter(text), re.MULTILINE)
    check = _sections(_body(text))["3a"]
    assert shlex.split(_relabel_call().split("--records", 1)[1])[0] == "{exportRecordsFile}"
    assert "delete the file" not in check and ".skf-labels.json" not in text
    purge = 'rm -rf "{run_dir}"'
    (cancel_3,) = [line for line in _read(RANK).splitlines() if line.startswith("- IF X:")]
    (cancel_6,) = [line for line in _read(COMPILE).splitlines() if line.startswith("- IF X:")]
    no_manifests = _from(_sections(_body(_read(MANIFESTS)))["2"], "STOP and wait").split("\n\n")[0]
    for where, line in (("step 2 option 3", no_manifests), ("step 3 [X]", cancel_3),
                        ("step 6 [X]", cancel_6), ("step 9", _sections(_body(_read(REPORT)))["3"])):
        assert purge in line, f"{where} does not delete the run folder"
    # Every other halt keeps the folder, as the contract's Outputs row says: the all-failed halt's
    # warnings.jsonl is the only record of why each library failed.
    holders = sorted(path.name for path in STEP_FILES if purge in _read(path))
    assert holders == ["compile-stack.md", "detect-manifests.md", "rank-and-confirm.md", "report.md"], holders
    all_failed = _from(_sections(_body(text))["3"], "**If ALL extractions fail:**").split("\n\n")[0]
    assert "The run folder stays" in all_failed and "`extraction-failed`" in all_failed
    assert "deleted when the run finishes or the user cancels and kept after any other HALT" in _contract_row("Outputs")
    # {version} is first bound at step 7 §1's Stack version paragraph: no earlier step names a
    # staging folder under it.
    for path in (RANK, EXTRACT, COMPILE):
        assert "{version}/*-tmp" not in _read(path), path.name


def test_the_label_check_call_runs_as_written(tmp_path):
    """The documented relabel call fixes the records in place, so the next run finds nothing to fix."""
    records = tmp_path / "run" / "export-records.json"
    records.parent.mkdir()
    argv = _argv(_relabel_call(), "renderStackMetadataHelper", {"{exportRecordsFile}": str(records)})

    def run():
        result = subprocess.run([sys.executable, str(STACK_METADATA), *argv], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    # Client was read by eye but labeled T1, the Forge-tier label before #555.
    records.write_text(json.dumps({"entries": _liba_records(client_tier="T1")}), encoding="utf-8")
    out = run()
    assert [(r["entry_index"], r["export_name"], r["source_library"]) for r in out["relabeled"]] == [
        (2, "Client", "liba")]
    assert [(c["field"], c["to"]) for c in out["relabeled"][0]["changes"]] == [
        ("confidence", "T1-low"), ("signature_source", "T1-low")]
    assert out["coherence"] == {"ok": True, "violations": []}
    assert out["confidence_distribution"] == {"t1": 2, "t1_low": 1, "t2": 0, "t3": 0}  # §4's label counts
    assert json.loads(records.read_text(encoding="utf-8")) == {"entries": _liba_records()}
    # The stats helper the step used to run agrees: the records pass its check now.
    stats = _load(STATS_HELPER, "skf_render_metadata_stats_stack_rules")
    assert stats.check_label_agreement({"entries": _liba_records()}) == []
    assert run()["relabeled"] == []


def _template_values(template: str, key: str) -> set[str]:
    """The `|` alternatives of the first `"key": "..."` value in a JSON template."""
    match = re.search(rf'"{key}": "([^"]+)"', template)
    assert match, key
    return set(match.group(1).split("|"))


def test_the_schema_holds_step_4_labels_and_no_node_kind():
    schema = _read(SCHEMA)
    code, compose = re.findall(r"```json\n(.*?)```", schema, re.DOTALL)
    assert "ast_node_type" not in code and "ast_node_type" not in compose
    # A code-mode entry holds what step 4 records: the §1 pairings.
    pairings = _pairings()
    assert _template_values(code, "extraction_method") == set(pairings)
    assert _template_values(code, "confidence") == {confidence for confidence, _ in pairings.values()}
    assert _template_values(code, "signature_source") == {signature for _, signature in pairings.values()}
    # A compose entry carries its constituent's tier, T3 included.
    for key in ("confidence", "signature_source"):
        assert _template_values(compose, key) == set(TIER_ORDER), key
    (note,) = [line for line in schema.splitlines() if line.startswith("> **Note:**")]
    assert "`ast_node_type`" in note
    assert "skill-sections.md" not in note, "the note points at a file that does not resolve from this skill"
    assert "constituents[]" not in note, "the note repeats the intro's drift-detection sentence"


def test_step_7_runs_the_verifier_on_the_code_mode_map():
    text = _read(GENERATE)
    assert _probe_script(text, "verifyProvenanceCompleteness") == VERIFIER
    check = _from(_sections(_body(text))["7"], "**Source lines (code mode only).**")
    verify = _call(check, "verifyProvenanceCompletenessHelper", "verify")
    assert "--source-root {project_root}" in verify and "--skill-dir" not in verify, verify
    fix = _call(check, "verifyProvenanceCompletenessHelper", "fix")
    assert "--provenance {forge_version}/provenance-map.json" in fix, fix
    assert "`missing`" in check and "`orphaned`" in check
    assert "`workflow_warnings[]`" in check, "the line check leaves its warnings nowhere"


def test_the_line_check_calls_run_as_written(tmp_path):
    check = _from(_sections(_body(_read(GENERATE)))["7"], "**Source lines (code mode only).**")
    project_root = tmp_path / "project"
    (project_root / "libs" / "liba").mkdir(parents=True)
    (project_root / "libs" / "liba" / "api.py").write_bytes(LIBA_API)
    staging = tmp_path / "skills" / "demo-stack" / "1.0.0" / "demo-stack.skf-tmp"
    staging.mkdir(parents=True)
    skill_md = b"# demo Stack Skill\n\n`get_config()` caches its result (libs/liba/api.py:10).\n"
    (staging / "SKILL.md").write_bytes(skill_md)
    (staging / "metadata.json").write_text(json.dumps({"skill_type": "stack", "exports": []}), encoding="utf-8")
    forge_version = tmp_path / "forge" / "demo-stack" / "1.0.0"
    forge_version.mkdir(parents=True)
    provenance = forge_version / "provenance-map.json"
    provenance.write_text(json.dumps({"skill_type": "stack", "entries": _liba_records()}), encoding="utf-8")
    values = {"{skill_staging}": str(staging), "{forge_version}": str(forge_version),
              "{project_root}": str(project_root)}

    def run(subcommand):
        argv = _argv(_call(check, "verifyProvenanceCompletenessHelper", subcommand),
                     "verifyProvenanceCompletenessHelper", values)
        return subprocess.run([sys.executable, str(VERIFIER), *argv], capture_output=True, text=True)

    verify_json = forge_version / "provenance-verify.skf-tmp"
    first = run("verify")
    assert first.returncode == 1, first.stderr
    result = json.loads(verify_json.read_text(encoding="utf-8"))
    assert [(s["export_name"], s["reason"], s["definition_lines"]) for s in result["stale"]] == [
        ("get_config", "line-not-definition", [13])]
    assert result["orphaned"] == ["Client", "connect", "get_config"]  # exports [] by design: ignored
    fixed = run("fix")
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    entries = json.loads(provenance.read_text(encoding="utf-8"))["entries"]
    assert [e["source_line"] for e in entries] == [6, 13, 17]
    assert (staging / "SKILL.md").read_bytes() == skill_md, "a plain file:line citation moved"
    again = run("verify")
    assert again.returncode == 1, again.stderr  # orphaned stays: stack exports are []
    assert json.loads(verify_json.read_text(encoding="utf-8"))["stale"] == []


def _provenance_call(mode: str = "code") -> str:
    """Step 7 §7's provenance call under the bullet of `mode`."""
    code, compose = _sections(_body(_read(GENERATE)))["7"].split("- **In compose-mode:**", 1)
    return _call(code if mode == "code" else compose, "renderStackMetadataHelper", "provenance")


def _filled_argv(call: str, values: dict[str, str]) -> list[str]:
    if sys.platform == "win32":  # a POSIX shell split would eat a Windows path's backslashes
        return _argv(call, "renderStackMetadataHelper", values)
    # A run folder with a space in its path reaches the helper whole: the call quotes its paths.
    return _shell_filled(call, "renderStackMetadataHelper", values)


def test_step_7_writes_the_code_mode_entries_with_the_helper(tmp_path):
    """W5 handoff (determinism-5): the records step 4 checked are the map's entries and the bundle's
    pairs its integrations, never typed again; the piped input holds only the map's anchor fields.
    Step 5b handoff (determinism-2): each pair's co-import files come from the pair helper's saved
    result, matched on the two libraries, so no step types a {path, line_a, line_b} tuple."""
    seven = _sections(_body(_read(GENERATE)))["7"]
    (bullet,) = [line for line in seven.splitlines() if line.startswith("- **In code-mode:**")]
    assert "`entries` of `{exportRecordsFile}`" in bullet and "the call below writes both" in bullet
    assert "the pairs of `{bundleFile}`" in bullet and "co-import files from `{pairsFile}`" in bullet
    assert "one entry per export record" not in seven and "first call" not in seven and "second call" not in seven
    # Each mode shows its own helper call, under its own bullet, and no map is written by hand.
    code, compose = seven.split("- **In compose-mode:**", 1)
    assert "{atomicWriteHelper}" not in code and "{atomicWriteHelper}" not in compose
    assert "{renderStackMetadataHelper}" in compose
    assert '--pairs "{pairsFile}"' in _provenance_call("code")
    run_dir = tmp_path / "run dir"
    run_dir.mkdir()
    records = run_dir / "export-records.json"
    records.write_text(json.dumps({"entries": _liba_records()}), encoding="utf-8")
    bundle = run_dir / "extraction-bundle.json"
    # The pair helper names the pair (liba, libb); the bundle names it the other way round.
    co_import = [{"path": "src/app.py", "line_a": 1, "line_b": 2}]
    pairs = run_dir / "pair-intersect.json"
    pairs.write_text(json.dumps({"pairs": [{"a": "liba", "b": "libb", "intersection_count": 1,
                                            "files": co_import}], "truncated": False, "total_pairs": 1}),
                     encoding="utf-8")
    bundle.write_text(json.dumps({"mode": "code", "integrations": [
        {"a": "libb", "b": "liba", "type": "adapter", "tier": "T1-low", "qualifier": "grep-co-import",
         "detection_method": "co-import grep", "key_files": [], "description": "liba feeds libb"}]}),
        encoding="utf-8")
    forge_version = tmp_path / "forge" / "demo-stack" / "1.0.0"
    forge_version.mkdir(parents=True)
    values = {"{exportRecordsFile}": str(records), "{bundleFile}": str(bundle), "{pairsFile}": str(pairs),
              "{forge_version}": str(forge_version)}
    argv = _filled_argv(_provenance_call(), values)
    fields = {"provenance_version": "2.0", "skill_name": "demo-stack", "skill_type": "stack", "source_repo": [],
              "source_commit": {}, "generated_at": "2026-10-02T08:00:00Z"}
    for field in fields:
        assert f"`{field}`" in bullet, field
    result = subprocess.run([sys.executable, str(STACK_METADATA), *argv], input=json.dumps(fields),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    written = json.loads((forge_version / "provenance-map.json").read_text(encoding="utf-8"))
    assert written["entries"] == _liba_records()
    # line_a stays the line that imports libraries[0]: the swapped pair swaps its lines.
    assert written["integrations"] == [{"libraries": ["libb", "liba"], "pattern_type": "adapter",
                                        "detection_method": "co-import grep",
                                        "co_import_files": [{"path": "src/app.py", "line_a": 2, "line_b": 1}],
                                        "confidence": "T1-low"}]
    assert list(written).index("entries") < list(written).index("integrations")


def test_step_7_writes_the_compose_mode_map_with_the_helper(tmp_path):
    """Step 5b handoff (determinism-3): step 4 saves its inventory, the model writes only the cited
    entries, and the helper writes the integrations and the constituents, each hash copied from the
    inventory and each skill_path relative to the project root, so an audit of the stack finds every
    constituent fresh, under a skills folder that is not the default one."""
    extract = _read(COMPOSE_EXTRACT)
    assert "stackInventoryFile: '{run_dir}/stack-inventory.json'" in _frontmatter(extract)
    enumerate_call = _call(_sections(_body(extract))["1"], "enumerateStackSkillsHelper", "enumerate").strip()
    enumerate_call, target = enumerate_call.split(" > ")
    assert target == '"{stackInventoryFile}"', "step 4 does not save its inventory in the run folder"
    seven = _sections(_body(_read(GENERATE)))["7"]
    compose = seven.split("- **In compose-mode:**", 1)[1].split("**Source lines (code mode only).**")[0]
    assert "write only the entries" in compose and "`{composeEntriesFile}`" in compose
    for frontmatter_key in ("stackInventoryFile: '{run_dir}/stack-inventory.json'",
                            "composeEntriesFile: '{run_dir}/compose-entries.json'"):
        assert frontmatter_key in _frontmatter(_read(GENERATE)), frontmatter_key
    project = tmp_path / "my project"
    skills_root = project / "my-skills"
    hashes = {}
    for name, version in (("react", "18.2.0"), ("express", "4.19.0")):
        package = skills_root / name / version / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_bytes(f"# {name}\n".encode("utf-8"))
        metadata = json.dumps({"name": name, "version": version, "generated_by": "create-skill",
                               "exports": ["render"], "skill_type": "single"}).encode("utf-8")
        (package / "metadata.json").write_bytes(metadata)
        hashes[name] = "sha256:" + hashlib.sha256(metadata).hexdigest()
        try:
            os.symlink(version, skills_root / name / "active", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
    run_dir = project / "_bmad-output" / ".skf-run" / "skf-create-stack-skill-1"
    run_dir.mkdir(parents=True)
    inventory = run_dir / "stack-inventory.json"
    argv = _argv(enumerate_call, "enumerateStackSkillsHelper", {"{skills_output_folder}": str(skills_root)})
    result = subprocess.run([sys.executable, str(ENUMERATE), *argv], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    inventory.write_text(result.stdout, encoding="utf-8")  # the shell redirect
    bundle = run_dir / "extraction-bundle.json"
    bundle.write_text(json.dumps({
        "mode": "compose", "scope": ["react", "express"],
        "per_library_extractions": [
            {"library": name, "skill_dir": name, "version": version, "confidence": "T1",
             "skill_package_path": f"{skills_root.as_posix()}/{name}/active/{name}"}
            for name, version in (("react", "18.2.0"), ("express", "4.19.0"))],
        "failed": [],
        "integrations": [{"a": "react", "b": "express", "type": "data-flow", "tier": "T1",
                          "qualifier": "architecture-co-mention", "detection_method": "architecture_co_mention",
                          "key_files": [], "description": "react calls express",
                          # The compose evidence step 5 keeps for steps 6 and 7 (architecture-1).
                          "evidence": ["[from skill: react] render(el)", "[from skill: express] listen(port)"],
                          "reference": '**Architecture reference:** "react calls express" (architecture doc line 3)',
                          "vs": {"pair": "Risky", "overall": "CONDITIONALLY_FEASIBLE"}}],
        "hubs": [], "cross_cutting": []}), encoding="utf-8")
    entries = run_dir / "compose-entries.json"
    # The model writes only the cited fields; the helper adds the constituent's tier.
    entries.write_text(json.dumps({"entries": [{"export_name": "render", "source_library": "react"}]}),
                       encoding="utf-8")
    forge_version = project / "forge-data" / "demo-stack" / "1.0.0"
    values = {"{composeEntriesFile}": str(entries), "{bundleFile}": str(bundle),
              "{stackInventoryFile}": str(inventory), "{skills_output_folder}": str(skills_root),
              "{project-root}": str(project), "{forge_version}": str(forge_version)}
    fields = {"provenance_version": "2.0", "skill_name": "demo-stack", "skill_type": "stack", "source_repo": None,
              "source_commit": None, "source_ref": None, "generated_at": "2026-10-03T08:00:00Z"}
    assert "the code-mode fields and `source_ref`" in compose
    result = subprocess.run([sys.executable, str(STACK_METADATA), *_filled_argv(_provenance_call("compose"), values)],
                            input=json.dumps(fields), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    provenance = forge_version / "provenance-map.json"
    written = json.loads(provenance.read_text(encoding="utf-8"))
    assert [(c["skill_name"], c["skill_path"], c["version"], c["metadata_hash"]) for c in written["constituents"]] == [
        ("react", "my-skills/react/", "18.2.0", hashes["react"]),
        ("express", "my-skills/express/", "4.19.0", hashes["express"])]
    assert {c["composed_at"] for c in written["constituents"]} == {"2026-10-03T08:00:00Z"}
    assert written["entries"] == [{"export_name": "render", "source_library": "react", "confidence": "T1",
                                   "extraction_method": "compose-from-skill", "signature_source": "T1"}]
    assert written["integrations"][0]["co_import_files"] == []
    assert set(written["integrations"][0]) == {"libraries", "pattern_type", "detection_method", "co_import_files",
                                               "confidence"}, "the compose evidence leaked into the map"
    # The audit's constituent check, run as Audit Skill runs it, finds both constituents fresh.
    audit = subprocess.run([sys.executable, str(HASH_CONTENT), "compare-constituent-hashes", str(provenance),
                            "--skills-root", str(project)], capture_output=True, text=True)
    assert audit.returncode == 0, audit.stderr
    stats = json.loads(audit.stdout)["stats"]
    assert (stats["fresh"], stats["drifted"], stats["missing"]) == (2, 0, 0), audit.stdout


# --- #528: a stack bins libraries, not provenance entries -------------------------


def test_stack_distribution_counts_each_library_once():
    six = _sections(_body(_read(GENERATE)))["6"]
    # §6 pipes each library's step-4 tier to the helper, which bins each library once; the
    # contract it writes to says what the distribution counts (W5 handoff, leanness-6).
    assert "per_library_extractions[].confidence" in six and "`assets/metadata-contract.md`" in six
    note = _h2_section(_read(METADATA_CONTRACT), "## metadata.json Structure").split("```")[-1]
    for needle in ("`confidence_distribution`", "`library_count`", "evidence report"):
        assert needle in note, needle
    knowledge = _slice(_read(TIERS), "## Confidence Distribution in Metadata", "## Anti-Patterns")
    for where, text in (("the metadata contract note", note), ("confidence-tiers.md", knowledge)):
        assert "`library_count`" in text and "`per_library_extractions[].confidence`" in text, where
    assert "read by eye" not in note, "the metadata contract re-derives the tier step 4 sets"
    assert "constituent count" not in _read(STATS_HELPER), "the helper still says a stack sums to its constituents"
    # create-skill never builds a stack, so its steps give no stack carve-out.
    create = REPO_ROOT / "src" / "skf-create-skill" / "references"
    assert "--shape stack" not in _read(create / "compile.md")
    assert "**stack** distribution" not in _read(create / "validate.md")


@pytest.mark.parametrize("path, number", [(REPORT, "1"), (COMPILE, "7")], ids=["report-1", "compile-stack-7"])
def test_the_run_shows_libraries_per_tier(path, number):
    (line,) = [line for line in _sections(_body(_read(path)))[number].splitlines()
               if line.lstrip().startswith("- **Confidence")]
    label, counts = line.split(":**", 1)
    assert "libraries per tier" in label, line
    assert re.findall(r"\bT1-low\b|\bT1\b|\bT2\b|\bT3\b", counts)[:4] == list(TIER_ORDER), line
    assert "QMD" not in line, "a library tier is not a temporal annotation"


def test_the_evidence_report_bins_the_final_map(tmp_path, monkeypatch, capsys):
    text = _read(GENERATE)
    assert _probe_script(text, "renderMetadataStats") == STATS_HELPER
    report = _sections(_body(text))["8b"]
    call = _call(report, "renderMetadataStatsHelper")
    assert "{forge_version}/provenance-map.json" in call and "--shape stack" in call, call
    assert report.index(call) < report.index("{atomicWriteHelper} write"), "the report is written before it is binned"
    assert "counts libraries" in report
    # A compose-mode map: each entry carries its constituent's tier.
    forge_version = tmp_path / "forge" / "demo-stack" / "1.0.0"
    forge_version.mkdir(parents=True)
    entries = [
        {"export_name": name, "source_library": library, "extraction_method": "compose-from-skill",
         "confidence": tier, "signature_source": tier}
        for name, library, tier in (("connect", "liba", "T1"), ("Client", "liba", "T1"), ("render", "libb", "T3"))
    ]
    (forge_version / "provenance-map.json").write_text(
        json.dumps({"skill_type": "stack", "entries": entries}), encoding="utf-8")
    argv = _argv(call, "renderMetadataStatsHelper", {"{forge_version}": str(forge_version)})
    monkeypatch.setattr(sys, "stdin", io.StringIO(re.search(r"echo '(.*?)' \|", call).group(1)))
    stats = _load(STATS_HELPER, "skf_render_metadata_stats_report")
    assert stats.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["confidence_distribution"] == {"t1": 2, "t1_low": 0, "t2": 0, "t3": 1}


# --- #534: compose tiers come from each constituent's own evidence ----------------


def test_compose_constituent_tier_is_the_evidence_tier():
    sections = _sections(_body(_read(COMPOSE_EXTRACT)))
    assert '"evidence_tier": "T1|T1-low|T2|T3"' in sections["1"]
    (bullet,) = [line for line in sections["3"].splitlines() if line.startswith("- `confidence`:")]
    assert bullet.startswith("- `confidence`: `inventory.skills[i].evidence_tier` (one of `T1|T1-low|T2|T3`)")
    # The field §3 takes: the largest bin, ties to the weaker tier, T3
    # included, T1-low when nothing is recorded.
    enumerate_ = _load(ENUMERATE, "skf_enumerate_stack_skills_stack_rules")
    assert enumerate_.dominant_tier({"t1": 0, "t1_low": 0, "t2": 0, "t3": 12}) == "T3"
    assert enumerate_.dominant_tier({"t1": 2, "t1_low": 2, "t2": 0, "t3": 0}) == "T1-low"
    assert enumerate_.dominant_tier(None) == "T1-low"


def test_compose_entries_carry_their_constituent_tier():
    seven = _sections(_body(_read(GENERATE)))["7"]
    (bullet,) = [line for line in seven.splitlines() if line.startswith("- **In compose-mode:**")]
    for needle in ("`confidence`", "`signature_source`", "`extraction_method`",
                   "`per_library_extractions[].confidence`"):
        assert needle in bullet, needle
    # The helper sets the tier from the bundle: the model types only the cited fields (step 5b review).
    assert "The call below sets each entry's `confidence`" in bullet, bullet
    assert "are its constituent's tier" not in bullet
    for path in (EXTRACT, COMPOSE_EXTRACT, SCHEMA):
        assert "when it was forged" not in _read(path), f"{path.name} says a constituent checked the stack's labels"


def test_compose_pairs_take_the_helper_tier():
    """#534, #606: a pair's tier is the helper's, the weaker of its two tiers, in both modes."""
    rules = _h2_section(_read(COMPOSE_RULES), "## Confidence Tier Inheritance")
    assert "`skf-render-stack-metadata.py`" in rules and "`combine_pair_tier`" in rules
    assert not PAIR_CASE_RE.search(rules), "compose-mode-rules still works pair cases out by hand"
    for path in (COMPOSE_RULES, COMPOSE_PAIRS, DETECT):
        assert "+T2 annotations" not in _read(path), f"{path.name} still keeps a T2 pair at a stronger tier"
    for path in (COMPOSE_RULES, COMPOSE_PAIRS, DETECT, SCHEMA):
        assert not OLD_MATRIX_RE.search(_read(path)), f"{path.name} still points at the old tier matrix"
    helper = _load(STACK_METADATA, "skf_render_stack_metadata_stack_rules")
    for mode in ("code", "compose"):
        for a, b in (("T1", "T2"), ("T1-low", "T2"), ("T2", "T2"), ("T1", "T1-low"), ("T1-low", "T3")):
            assert helper.combine_pair_tier(a, b, mode) == _weaker(a, b), (a, b, mode)


# --- #606: one tier rule, one metadata projection, one structure pass -------------


@pytest.mark.parametrize("path", [*STEP_FILES, TEMPLATE, SCHEMA], ids=lambda p: p.name)
def test_no_step_file_restates_the_tier_ordering(path):
    """The ordering lives in skf-render-stack-metadata.py; a step names the helper instead."""
    hits = [m.group(0) for m in ORDERING_RE.finditer(_read(path))]
    assert not hits, f"{path.name} restates the tier ordering: {hits}"


@pytest.mark.parametrize("text", [
    "tie-break: T1-low > T1, T2 > T1-low, T3 > T2",
    "`T1-low` is weaker than `T1`",
    "a T1 + T2 or T1-low + T2 pair is T2",
    "Pick the tier with the highest count",
    "the lowest authority among constituent skills (official > community > internal)",
])
def test_the_ordering_pattern_matches_a_restatement(text):
    assert ORDERING_RE.search(text)


def test_the_integration_label_names_the_helper_tier():
    """#1151 leanness-4: integration-patterns.md holds the types only, its unused Output Format gone, and the
    compose pair's tier line points at step 5 §3's helper call and the compose rules."""
    patterns = _read(INTEGRATION_PATTERNS)
    assert not [line for line in patterns.splitlines() if line.lstrip().startswith("Confidence:")]
    assert "## Output Format" not in patterns
    (item,) = [line for line in _sections(_body(_read(COMPOSE_PAIRS)))["1"].splitlines()
               if line.startswith("6. ")]
    assert "Its tier comes from the pair-tiers call of `references/detect-integrations.md` §3" in item, item
    assert "Confidence Tier Inheritance" in item and "weaker" not in item


def _pair_tiers_call() -> str:
    return _call(_sections(_body(_read(DETECT)))["3"], "renderStackMetadataHelper", "pair-tiers")


def test_step_5_takes_each_pair_tier_from_the_helper():
    text = _read(DETECT)
    assert _probe_script(text, "renderStackMetadata") == STACK_METADATA
    three = _sections(_body(text))["3"]
    assert "--input -" in _pair_tiers_call()
    for needle in ('"mode": "code|compose"', "per_library_extractions[].confidence", "`tier`"):
        assert needle in three, needle
    assert "weaker" not in three, "§3 still states the tier rule itself"


def test_a_missing_tier_helper_halts_with_its_envelope():
    """Every HARD HALT carries an exit code, a halt_reason and an envelope (invocation-contract.md)."""
    three = _sections(_body(_read(DETECT)))["3"]
    halt = _slice(three, "If no candidate exists, HALT", "When at least one pair qualifies")
    assert '(exit 3, `halt_reason: "helper-missing"`, phase `detect-integrations:pair-tiers`)' in halt
    # Step 7 §6 resolves the same helper after staging: it rolls back with the same code, not as a write failure.
    six = _sections(_body(_read(GENERATE)))["6"]
    assert 'invoke the rollback contract from §1, with exit 3, `halt_reason: "helper-missing"` and phase' in six
    (row,) = [line for line in _read(CONTRACT).splitlines() if line.startswith("| 3 ")]
    assert "`skf-render-stack-metadata.py` (step 4 §3a, step 5 §3, step 6 §1, step 7 §6)" in row


def test_step_2_records_the_authority_step_7_projects():
    """§6 pipes each constituent's source_authority, so step 2 must still read it (#606)."""
    six = _sections(_body(_read(GENERATE)))["6"]
    assert '"source_authority": "<compose mode: the constituent\'s>"' in six
    (read,) = [line for line in _sections(_body(_read(COMPOSE_SKILLS)))["1"].splitlines()
               if line.startswith("3. Read `metadata.json` from `skill_package_path`")]
    assert "source_authority" in read, "step 2 no longer records each constituent's source_authority"


def _stack_input(mode: str = "compose") -> dict:
    return {
        "mode": mode,
        "libraries": [{"name": "react", "confidence": "T1", "source_authority": "community"},
                      {"name": "express", "confidence": "T2", "source_authority": "internal"},
                      {"name": "zod", "confidence": "T1-low"}],
        "integrations": [{"a": "react", "b": "express"}, {"a": "react", "b": "zod"}],
    }


def _run_stack_metadata(call: str, payload: dict) -> dict:
    argv = _argv(call, "renderStackMetadataHelper", {})
    result = subprocess.run([sys.executable, str(STACK_METADATA), *argv], input=json.dumps(payload),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_pair_tier_call_runs_as_written():
    out = _run_stack_metadata(_pair_tiers_call(), _stack_input())
    assert out["integrations"] == [{"a": "react", "b": "express", "tier": "T2"},
                                   {"a": "react", "b": "zod", "tier": "T1-low"}]


def _metadata_call() -> str:
    return _call(_sections(_body(_read(GENERATE)))["6"], "renderStackMetadataHelper", "metadata")


def test_step_7_writes_the_metadata_projection():
    text = _read(GENERATE)
    assert _probe_script(text, "renderStackMetadata") == STACK_METADATA
    six = _sections(_body(text))["6"]
    # §6 writes the fields the contract takes from the helper, and lists them no second time.
    assert "write the fields the contract takes from it verbatim" in six and "rollback contract" in six
    contract_note = _h2_section(_read(METADATA_CONTRACT), "## metadata.json Structure").split("```")[-1]
    assert "`skf-render-stack-metadata.py`" in contract_note
    out = _run_stack_metadata(_metadata_call(), _stack_input())
    for field in ("library_count", "integration_count", "libraries", "integration_pairs",
                  "confidence_distribution", "confidence_tier", "source_authority"):
        assert f"`{field}`" in contract_note and field in out, field
        assert f"`{field}`" not in six, f"§6 restates the contract's field {field}"


def test_the_metadata_call_runs_as_written():
    """The distribution counts each library once and sums to library_count (#528)."""
    out = _run_stack_metadata(_metadata_call(), _stack_input())
    assert out["library_count"] == sum(out["confidence_distribution"].values()) == 3
    assert out["confidence_distribution"] == {"t1": 1, "t1_low": 1, "t2": 1, "t3": 0}
    assert out["confidence_tier"] == "T2"  # a tie goes to the weaker tier
    assert out["source_authority"] == "internal"  # community and internal give internal
    assert out["integration_pairs"] == [["react", "express"], ["react", "zod"]]
    code = _run_stack_metadata(_metadata_call(), _stack_input("code"))
    assert code["confidence_tier"] == out["confidence_tier"]


VALIDATE_CHECKS = {"4": "skill_md", "5": "metadata", "6": "references", "7": "tier_labels"}


def test_step_8_reads_the_structure_pass():
    text = _read(VALIDATE)
    sections = _sections(_body(text))
    call = [line for line in _fence_lines(sections["1"]) if "{outputValidator}" in line]
    assert len(call) == 1 and "--skill-type stack" in call[0] and "--forge-tier {forge_tier}" in call[0], call
    assert "`validation.stack_structure`" in sections["1"]
    for number, check in VALIDATE_CHECKS.items():
        assert "`validation.stack_structure.issues[]`" in sections[number], number
        assert f"`check` is `{check}`" in sections[number], number
    assert "Scan all output files" not in sections["7"], "§7 still scans every output file by hand"
    validator = _load(VALIDATOR, "skf_validate_output_stack_rules")
    source = VALIDATOR.read_text(encoding="utf-8")
    for check in VALIDATE_CHECKS.values():
        assert f'"{check}"' in source, check
    assert validator._STACK_RULES_HELPER == STACK_METADATA.name


def test_the_validator_call_runs_as_written(tmp_path):
    call = [line for line in _fence_lines(_sections(_body(_read(VALIDATE)))["1"]) if "{outputValidator}" in line][0]
    package = tmp_path / "demo-stack"
    package.mkdir()
    args = shlex.split(call.split("python3 {outputValidator}", 1)[1].replace("{skill_package}", str(package))
                       .replace("{forge_tier}", "Deep"))
    result = subprocess.run([sys.executable, str(VALIDATOR), *args], capture_output=True, text=True)
    out = json.loads(result.stdout)
    assert set(out["validation"]) >= {"stack_counts", "stack_structure"}


def test_a_changed_package_is_validated_again():
    """§3's fixes and splits change the committed package after §1 ran: §4 to §8 read a run made after them."""
    sections = _sections(_body(_read(VALIDATE)))
    rerun = _from(sections["3"], "**Re-validate a changed package.**").split("\n\n", 1)[0]
    for needle in ("SKILL.md changed across the `--fix` call", "a split ran", "the §1 `{outputValidator}` command again",
                   "§4 to §8"):
        assert needle in rerun, needle
    assert "§4 to §8 read the latest run" in sections["1"]
    for number in ("5", "7"):
        assert "the latest output-validator run" in sections[number], number
        assert "the §1 output-validator run" not in sections[number], number
    # The section-by-section restatements of the validator's checks are gone: each section records by `check`.
    for number in VALIDATE_CHECKS:
        assert "The pass checks" not in sections[number] and "the pass looks for" not in sections[number], number


def test_section_3_tells_a_fix_from_the_file_hash():
    """#901: skill-check 1.2.0's JSON has no `fixed[]`, so §3 hashes SKILL.md around the `--fix` call; a change, or
    a SKILL.md left unhashed, raises one S15 WARNING with fixed text and runs the §1 validator again."""
    text = _read(VALIDATE)
    assert "fixed[]" not in text
    assert _probe_script(text, "hashContent") == HASH_CONTENT
    three = _sections(_body(text))["3"]
    hash_call = "`uv run {hashContentHelper} hash <skill-dir>/SKILL.md`"
    fix_call = "`npx skill-check check <skill-dir> --fix --format json --no-security-scan`"
    assert three.count(hash_call) == 2 and three.count(fix_call) == 1
    assert three.index(hash_call) < three.index(fix_call) < three.rindex(hash_call), "hash, call, hash"
    assert "resolve `{hashContentHelper}` ← first existing path in `{hashContentProbeOrder}`" in three
    for needle in ("SKILL.md changed across the `--fix` call when the two `content_hash` values differ",
                   "taken as changed, not hashed, when no `{hashContentProbeOrder}` path exists (run the skill-check "
                   "call alone) or a `hash` call prints no `content_hash`"):
        assert needle in three, needle
    s15 = _slice(three, "**Post-fix provenance drift guard:**", "\n")
    assert "When SKILL.md changed across the `--fix` call" in s15 and "Emit one **WARNING** finding" in s15
    tail = "after step 7 wrote it: metadata.json hashes and provenance may be out of date"
    assert f'`"skill-check --fix modified SKILL.md {tail}"`' in s15
    assert f'`"SKILL.md may have been rewritten (not hashed) by skill-check --fix {tail}"` when SKILL.md was not ' \
           "hashed" in s15
    assert "{fix_description}" not in s15 and "\u2014" not in s15
    rerun = _slice(three, "**Re-validate a changed package.**", "\n")
    assert "When SKILL.md changed across the `--fix` call (not hashed included) or a split ran" in rerun
    assert "HALT" not in text, "the step stays advisory"


# --- #582: compose-mode pairs are candidates, judged on their evidence ---------------


def _compose_branch() -> str:
    """Step 5's compose-mode sequence, which compose-pairs.md holds (#1151)."""
    return _body(_read(COMPOSE_PAIRS))


def test_compose_candidates_are_judged_on_their_evidence():
    branch = _compose_branch()
    for needle in ("`comention_count`", "`lead_in_count`", "`list-only`", "`unit_excerpt`", "`unit_line`",
                   "`list_only_pair_count`", "comention-list-only", "comention-unconfirmed", "`workflow_warnings[]`"):
        assert needle in branch, needle
    # The helper leaves out the pairs only listed together and counts them: the step drops none by
    # hand and records one warning with the count, never one per pair (step 5b review).
    (list_only,) = [line for line in branch.splitlines() if 'code: "comention-list-only"' in line]
    assert "`list_only_pair_count`" in list_only and "one `workflow_warnings[]` entry" in list_only, list_only
    assert "the pair and its `paragraph_count`" not in branch and "both 0" not in branch
    (empty,) = [line for line in branch.splitlines() if 'code: "comention-no-candidates"' in line]
    assert "{list_only_pair_count}" in empty, "the no-candidates warning does not give the list-only count"
    for stale in ("qualify automatically", "detected-integration-pair set", "same `language` field"):
        assert stale not in _read(DETECT) + _read(COMPOSE_PAIRS), stale
    assert "the pairs `references/compose-pairs.md` wrote qualify" in _sections(_body(_read(DETECT)))["3"]


def test_the_comention_call_runs_as_written(tmp_path):
    call = _call(_compose_branch(), "comentionHelper", "comention")
    doc = tmp_path / "architecture.md"
    doc.write_bytes(
        b"# Architecture\n\n## Tech Stack\n\n- react\n- express\n- zod\n- prisma\n\n"
        b"## Components\n\n| Part | Library |\n|------|---------|\n| UI | react |\n| API | express |\n"
        b"| Schemas | zod |\n| Storage | prisma |\n\n"
        b"## Data Flow\n\nThe react client posts forms to express, which validates them with zod.\n\n"
        b"Every express handler parses its body with zod before it runs.\n"
    )
    argv = _argv(call, "comentionHelper", {"{architecture_doc_path}": str(doc)})
    result = subprocess.run([sys.executable, str(COMENTION), *argv], input='["react", "express", "zod", "prisma"]',
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    pairs = {(p["a"], p["b"]): p for p in out["pairs"]}
    # prisma is only listed in the Tech Stack list and the Components table: its
    # three pairs are counted, never emitted, so §1 item 4 records one warning.
    assert set(pairs) == {("express", "react"), ("express", "zod"), ("react", "zod")}
    assert out["list_only_pair_count"] == 3
    confirmed = pairs[("express", "zod")]
    assert confirmed["comention_count"] == 2
    assert [e["kind"] for e in confirmed["evidence"]] == ["list-only", "list-only", "co-mention", "co-mention"]
    assert all(e["unit_excerpt"] for e in confirmed["evidence"] if e["kind"] == "co-mention")


def test_the_comention_guards_are_fields_the_step_weighs(tmp_path):
    """Step 5b handoff (determinism-1): the script filters on no meaning. A pair one paragraph names
    is a candidate, an introductory section marks its evidence `excluded_section`, the step judges
    that mark from the excerpt, and a document that names no pair warns."""
    branch = _compose_branch()
    assert "never apply them in-prompt" not in branch and "applies the co-mention guards" not in branch
    for needle in ("`excluded_section`", "`paragraph_count`", 'code: "comention-no-candidates"',
                   "`excluded_section` entry whose excerpt only names both confirms nothing"):
        assert needle in branch, needle
    call = _call(branch, "comentionHelper", "comention")
    doc = tmp_path / "architecture.md"
    doc.write_bytes(b"# Shop\n\n## Overview\n\nThe React client calls the Express API for every page.\n")
    argv = _argv(call, "comentionHelper", {"{architecture_doc_path}": str(doc)})
    result = subprocess.run([sys.executable, str(COMENTION), *argv], input='["react", "express"]',
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    (pair,) = out["pairs"]
    assert [(e["kind"], e["excluded_section"]) for e in pair["evidence"]] == [("co-mention", True)]
    assert out["excluded_section_count"] == 1


def test_a_diagram_edge_is_a_co_mention(tmp_path):
    """§2 step 5 counts a Mermaid edge as data flow: the script reads fenced code as text, and a lone
    diagram is enough, with no prose paragraph beside it (step 5b determinism-1)."""
    assert "`react --> express`" in _compose_branch()
    call = _call(_compose_branch(), "comentionHelper", "comention")
    doc = tmp_path / "architecture.md"
    doc.write_bytes(b"# Architecture\n\n## Flow\n\n```mermaid\ngraph LR\n  A[react] --> B[express]\n```\n")
    argv = _argv(call, "comentionHelper", {"{architecture_doc_path}": str(doc)})
    result = subprocess.run([sys.executable, str(COMENTION), *argv], input='["react", "express"]',
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (pair,) = json.loads(result.stdout)["pairs"]
    assert [(e["kind"], e["unit_excerpt"]) for e in pair["evidence"]][0] == ("co-mention", "A[react] --> B[express]")


def test_no_document_pairs_come_from_docs_or_keywords(tmp_path):
    branch = _compose_branch()
    for needle in ("`docs-mention`", "`shared-keywords`", "`language_only_pair_count`", "`truncated`",
                   "never on a shared language alone", "infer-unconfirmed"):
        assert needle in branch, needle
    call = _call(branch, "comentionHelper", "infer")
    assert "--top-k 20" in call
    docs = tmp_path / "express.md"
    docs.write_bytes(b"# express\n\nMount the passport middleware before the router.\n")
    skills = [
        {"name": "express", "keywords": ["http"], "language": "typescript", "docs": [str(docs)]},
        {"name": "passport", "keywords": ["auth"], "language": "typescript", "docs": []},
        {"name": "axios", "keywords": ["http"], "language": "typescript", "docs": []},
        {"name": "zod", "keywords": ["validation"], "language": "typescript", "docs": []},
    ]
    argv = _argv(call, "comentionHelper", {})
    result = subprocess.run([sys.executable, str(COMENTION), *argv], input=json.dumps(skills),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    kinds = {(p["a"], p["b"]): [e["kind"] for e in p["evidence"]] for p in out["pairs"]}
    assert kinds == {("express", "passport"): ["docs-mention"], ("axios", "express"): ["shared-keywords"]}
    assert out["language_only_pair_count"] == 4  # the typescript pairs with no evidence


def _infer_bullet(kind: str) -> str:
    (bullet,) = [line for line in _compose_branch().splitlines() if line.startswith(f"- **`{kind}`:**")]
    return bullet


def test_shared_keyword_candidates_are_judged(tmp_path):
    """A shared keyword makes a candidate, never an integration on its own (determinism-5, #582).

    Libraries that do the same job share their domain keywords: the helper
    reports such pairs, so the step judges every one before it keeps it.
    """
    shared = _infer_bullet("shared-keywords")
    for needle in ("Keep the pair as an `inferred-shared-domain` integration only when",
                   "both skills' `description_keywords`, `usage_patterns` and `exports` in `{bundleFile}` show how that "
                   "domain makes them work together",
                   "never for two libraries that do the same job"):
        assert needle in shared, needle
    assert "Keep the pair as a `constituent-documented-contract` integration only when" in _infer_bullet("docs-mention")
    call = _call(_compose_branch(), "comentionHelper", "infer")
    skills = [{"name": name, "keywords": keywords, "language": "typescript", "docs": []}
              for name, keywords in (("zod", ["validation", "schema"]), ("yup", ["validation", "schema"]),
                                     ("express", ["http", "server"]), ("fastify", ["http", "server"]),
                                     ("react", ["ui"]))]
    result = subprocess.run([sys.executable, str(COMENTION), *_argv(call, "comentionHelper", {})],
                            input=json.dumps(skills), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    pairs = json.loads(result.stdout)["pairs"]
    assert {(p["a"], p["b"]) for p in pairs} == {("express", "fastify"), ("yup", "zod")}
    assert {e["kind"] for p in pairs for e in p["evidence"]} == {"shared-keywords"}


def test_the_infer_call_failures_have_a_branch(tmp_path):
    branch = _compose_branch()
    infer = _from(branch, "**No architecture document.**")
    assert "On exit `1` its stderr names the input it refused" in infer
    assert '`code: "infer-unavailable"`' in infer and "compose with no inferred pairs" in infer
    call = _call(branch, "comentionHelper", "infer")
    missing = tmp_path / "express" / "SKILL.md"
    skills = [{"name": "express", "docs": [str(missing)]}, {"name": "passport"}]
    result = subprocess.run([sys.executable, str(COMENTION), *_argv(call, "comentionHelper", {})],
                            input=json.dumps(skills), capture_output=True, text=True)
    assert (result.returncode, result.stdout) == (1, "")
    assert str(missing) in result.stderr


WARNING_ENTRY_RE = re.compile(r"\(([^()]*`code: \"[a-z-]+\"`[^()]*)\)")


def test_every_step_5_warning_names_its_step_and_severity():
    """SKILL.md's workflow_warnings[] shape: {step, severity, code, message}, in both of step 5's files."""
    entries = WARNING_ENTRY_RE.findall(_body(_read(DETECT)) + _body(_read(COMPOSE_PAIRS)))
    assert len(entries) >= 7, entries
    for entry in entries:
        assert '`step: "step-05"`' in entry and re.search(r'`severity: "(info|warn|error)"`', entry), entry


def test_the_evidence_format_writes_the_label_the_validator_reads():
    """A compose pair entry written to the format passes the structure pass's tier-label check (#606)."""
    section = _h2_section(_read(COMPOSE_RULES), "## Integration Evidence Format")
    block = _first_fence(section)
    validator = _load(VALIDATOR, "skf_validate_output_evidence_format")
    filled = block.replace("{pair tier}", "T1-low").replace("{qualifier}", "architecture-co-mention")
    assert validator._TIER_LABEL_RE.search(filled), block
    assert "**Architecture reference:** \"{unit_excerpt}\" (architecture doc line {unit_line})" in block
    # A pair found without an architecture document cites its own evidence, not an architecture line.
    after = section.split("```")[-1]
    assert '`**Contract reference:** "{excerpt}" ({doc} line {line})`' in after
    assert "`**Shared domain:** {keywords}`" in after


def _fill_evidence(vs_pair: str | None) -> str:
    """The evidence format filled for an architecture pair, with the VS lines and annotation that
    compose-mode-rules' Feasibility Report Integration adds when the pair's `vs` is set."""
    block = _first_fence(_h2_section(_read(COMPOSE_RULES), "## Integration Evidence Format"))
    filled = (block.replace("{Skill A name}", "liba").replace("{Skill B name}", "libb")
              .replace("{exported_function_signature}", "connect(url: str) -> Client")
              .replace("{unit_excerpt}", "liba feeds libb").replace("{unit_line}", "12")
              .replace("{the pair's type, assigned in step 5 §3 from {integrationPatternsPath}}", "data-flow")
              .replace("{pair tier}", "T1-low").replace("{qualifier}", "architecture-co-mention"))
    if vs_pair is None:
        return filled
    lines = filled.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("**Architecture reference:**")) + 1
    lines[at:at] = ["VS overall: CONDITIONALLY_FEASIBLE", f"VS pair: {vs_pair}"]
    return "\n".join(f"{line} [VS: {vs_pair}]" if line.startswith("**Confidence:**") else line
                     for line in lines) + "\n"


def test_a_vs_rated_pair_keeps_the_label_the_validator_reads():
    """Step 5b run 2 architecture-1: a pair VS rated Blocked carries its verdict lines and annotation
    where the rules put them, and the structure pass still reads its tier label."""
    rules = _h2_section(_read(COMPOSE_RULES), "## Feasibility Report Integration")
    for needle in ("its bundle entry's `vs`", "`VS overall: {overallVerdict}` and `VS pair: {verdict}` lines after "
                   "its Architecture reference", "its Confidence line ends with a `[VS: Risky]` or `[VS: Blocked]`"):
        assert needle in rules, needle
    validator = _load(VALIDATOR, "skf_validate_output_vs_evidence")
    blocked = _fill_evidence("Blocked")
    assert validator._TIER_LABEL_RE.search(blocked), blocked
    assert "[VS: Blocked]" in blocked and "VS pair: Blocked" in blocked
    assert "[from skill: liba] connect(url: str) -> Client" in blocked
    assert "[composed]" in blocked, "the annotation must not hide the compose-mode marker test-skill reads"
    assert "[VS:" not in _fill_evidence(None)


def test_the_compose_evidence_reaches_the_package():
    """Step 5b run 2 architecture-1: step 5 keeps each compose pair's evidence and VS verdicts in its bundle
    entry, step 6 renders the pair from them in the fixed-path evidence format, and step 7 carries them into
    the pair file, so neither a [VS: Blocked] flag nor the [from skill: ...] lines dead-end at step 5."""
    pairs = _sections(_body(_read(COMPOSE_PAIRS)))
    assert "§3 writes them to the pair's bundle entry" in pairs["1"]
    entry = json.loads(_first_fence(pairs["3"]))
    assert entry["evidence"] == ["[from skill: <A>] <signature>", "[from skill: <B>] <signature>"]
    assert entry["reference"] == "<its Architecture reference, Contract reference or Shared domain line>"
    assert entry["vs"] == {"pair": "<verdict>", "overall": "<overallVerdict>"}
    assert "`vs` is `null` when no usable [VS] report rated the pair" in pairs["3"]
    # Step 5 §4 completes the entry compose-pairs.md wrote and keeps its evidence (#1151).
    four = _sections(_body(_read(DETECT)))["4"]
    assert ("In compose mode each entry keeps the `evidence`, `reference` and `vs` `references/compose-pairs.md` "
            "wrote; code mode leaves the three out.") in four
    compile_ = _read(COMPILE)
    assert "composeModeRulesPath: 'references/compose-mode-rules.md'" in _frontmatter(compile_)
    three = _sections(_body(compile_))["3"]
    (goal,) = [p for p in three.split("\n\n") if p.startswith("Otherwise fill the template's Integration Patterns")]
    for needle in ("evidence format of `{composeModeRulesPath}`",
                   "`type`, `evidence`, `reference`, `tier` and `qualifier`", "the entry's `vs` is set",
                   "a compose pair has no key files"):
        assert needle in goal, needle
    pair_file = _sections(_body(_read(GENERATE)))["4"]
    for needle in ("In compose mode its Integration Pattern section carries the entry's `evidence` and `reference` "
                   "lines", "when its `vs` is set"):
        assert needle in pair_file, needle


# --- #590: the [VS] report is located and read through the helper -----------------


FEASIBILITY_REPORT = """---
schemaVersion: "{version}"
reportType: feasibility
projectName: "Demo App"
overallVerdict: "CONDITIONALLY_FEASIBLE"
---

# Feasibility Report

## Executive Summary

Summary.

## Coverage Analysis

Coverage.

## Integration Verdicts

| lib_a | lib_b | verdict | rationale |
|-------|-------|---------|-----------|
| react | express | Risky | an adapter is needed |

## Recommendations

None.

## Evidence Sources

Skills.
"""


def test_the_vs_report_is_located_through_the_helper(tmp_path):
    branch = _compose_branch()
    call = _call(branch, "validateFeasibilityReportHelper")
    assert "--locate" in call and '--project-name "{project_name}"' in call, call
    for path in (COMPOSE_PAIRS, DETECT, COMPOSE_RULES):
        assert "feasibility-report-{project_slug}" not in _read(path), f"{path.name} still builds the file name"
    for needle in ("`schemaVersionOk`", "schema-version-mismatch", "`unknownTokens`", "vs-report-unusable",
                   "`pairVerdicts`", 'status: "not-found"'):
        assert needle in branch, needle
    forge = tmp_path / "forge data"
    forge.mkdir()
    argv = _argv(call, "validateFeasibilityReportHelper",
                 {"{forge_data_folder}": str(forge), "{project_name}": "Demo App"})

    def run():
        result = subprocess.run([sys.executable, str(FEASIBILITY), *argv], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    assert run()[1]["status"] == "not-found"
    report = forge / "feasibility-report-demo-app-latest.md"
    report.write_text(FEASIBILITY_REPORT.replace("{version}", "1.0"), encoding="utf-8")
    code, out = run()
    assert (code, out["status"], out["overallVerdict"]) == (0, "ok", "CONDITIONALLY_FEASIBLE")
    assert [(v["lib_a"], v["lib_b"], v["verdict"]) for v in out["pairVerdicts"]] == [("react", "express", "Risky")]
    report.write_text(FEASIBILITY_REPORT.replace("{version}", "2.0"), encoding="utf-8")
    code, out = run()
    assert (code, out["schemaVersionOk"]) == (1, False)
    report.write_text(FEASIBILITY_REPORT.replace("{version}", "1.0").replace("| Risky |", "| Maybe |"),
                      encoding="utf-8")
    code, out = run()
    assert (code, out["schemaVersionOk"]) == (1, True)
    assert [t["token"] for t in out["unknownTokens"]] == ["Maybe"]


def test_an_unknown_verdict_token_is_a_hard_error():
    """The shared schema's consumer obligation: an unknown token stops the run, never dropped or mapped (#590).

    The branches apply in order, so a report of another schemaVersion halts as
    a mismatch first, and only a contract break with no unknown token is read
    as unusable and composed without verdicts.
    """
    branch = _compose_branch()
    assert "Act on the first of these that applies" in branch
    bullets = [line for line in branch.splitlines() if line.startswith("- **")]
    order = [next(i for i, line in enumerate(bullets) if line.startswith(start))
             for start in ("- **`schemaVersionOk` is false:**", "- **`unknownTokens` is not empty:**",
                           "- **Any other exit `1`")]
    assert order == sorted(order), order
    unknown = bullets[order[1]]
    for needle in ("hard error", "HALT", "never drop or map"):
        assert needle in unknown, needle
    assert "vs-report-unusable" not in unknown and "unknownTokens" not in bullets[order[2]]


# --- #597, #591: the stack version and the snippet estimate ------------------------


def _one() -> str:
    return _sections(_body(_read(GENERATE)))["1"]


def test_the_stack_version_comes_from_the_inventory_helper():
    one = _one()
    assert "never reduce, compare or bump a version by hand" in one
    for stale in ("**Major** if any library", "**Minor** otherwise", "{primary_library_version}"):
        assert stale not in one, stale
    for needle in ("`NOT_A_VERSION`", "`BAD_INPUT`", "`USAGE`", "stack-version-default", "`reason`", "`bump`"):
        assert needle in one, needle
    assert not re.search(r"\bHALT\b[^.\n]*version", one), "a version the helper cannot give halts the run"
    # A malformed call is fixed and run again; only a version the helper cannot give starts a new line.
    (rule,) = [line for line in one.splitlines() if line.startswith("Narrate the version")]
    fix, default = rule.split("Start a new release line at `1.0.0` only when", 1)
    assert "`BAD_INPUT` or `USAGE`" in fix and "run it again" in fix
    assert "`NOT_A_VERSION`" in default and "`USAGE`" not in default and "`NOT_INCREASING`" not in default


def _inventory(argv: list[str], stdin: str | None = None) -> dict:
    result = subprocess.run([sys.executable, str(INVENTORY), *argv], input=stdin, capture_output=True, text=True)
    out = json.loads(result.stdout)
    assert result.returncode == (0 if out["status"] == "ok" else 1)
    return out


def _version_call(command: str) -> str:
    calls = [line for line in _fence_lines(_one()) if f"{{skillInventoryHelper}} version {command} " in line]
    assert len(calls) == 1, calls
    return calls[0]


def test_the_primary_version_call_runs_as_written():
    argv = _argv(_version_call("primary"), "skillInventoryHelper", {})
    candidates = [{"name": "react", "import_count": 12, "version": "^18.2.0"},
                  {"name": "express", "import_count": 12, "version": None},
                  {"name": "zod", "import_count": 3, "version": "3.22.4+build.7"}]
    out = _inventory(argv, json.dumps(candidates))
    assert (out["primary"], out["version"], out["reason"]) == ("react", "18.2.0", "tie-usable-version")
    assert _inventory(argv, "[]")["version"] == "1.0.0"


def test_the_compose_bump_call_runs_as_written():
    call = _version_call("bump")
    values = {"{prior_stack_version}": "3.0.5", "{prior_libraries}": "react,express",
              "{stack_libraries}": "react,express,zod"}
    assert _inventory(_argv(call, "skillInventoryHelper", values))["version"] == "3.1.0"
    values["{stack_libraries}"] = "react,zod"
    out = _inventory(_argv(call, "skillInventoryHelper", values))
    assert (out["bump"], out["version"], out["removed"]) == ("major", "4.0.0", ["express"])
    values["{prior_stack_version}"] = "latest"
    assert _inventory(_argv(call, "skillInventoryHelper", values))["code"] == "NOT_A_VERSION"


def _shell_filled(call: str, helper: str, values: dict[str, str]) -> list[str]:
    """The arguments of a documented call as a shell gives them: filled in first, then split."""
    rest = call.split(f"uv run {{{helper}}}", 1)[1]
    for placeholder, value in values.items():
        rest = rest.replace(placeholder, value)
    return shlex.split(rest)


def test_a_list_with_spaces_survives_the_bump_call():
    """A list written with a space after a comma reaches the helper whole, so a 3.0.5 stack is never reset."""
    call = _version_call("bump")
    values = {"{prior_stack_version}": "3.0.5", "{prior_libraries}": "react, express",
              "{stack_libraries}": "react, express, zod"}
    out = _inventory(_shell_filled(call, "skillInventoryHelper", values))
    assert (out["bump"], out["version"]) == ("minor", "3.1.0")
    # Unquoted, the shell splits the list and the helper refuses the call: USAGE, which the step fixes and reruns.
    unquoted = call.replace('"', "")
    refused = _inventory(_shell_filled(unquoted, "skillInventoryHelper", values))
    assert (refused["status"], refused["code"]) == ("error", "USAGE")
    assert "unexpected argument" in refused["error"]


def test_the_snippet_is_measured_with_the_count_helper(tmp_path):
    """#591: the snippet budget reads the count step 8's validator takes, from a script, not an estimate."""
    text = _read(GENERATE)
    assert _probe_script(text, "countTokens") == COUNT_TOKENS
    five = _sections(_body(text))["5"]
    assert "ceil(" not in five and "character count" not in five
    assert "`{token_estimate}` exceeds **120**" in five and "snippet-unmeasured" in five
    call = _call(five, "countTokensHelper")
    staging = tmp_path / "demo-stack.skf-tmp"
    staging.mkdir()
    snippet = ("[demo-stack v1.0.0]|root: skills/demo-stack/\n|IMPORTANT: demo-stack: read SKILL.md first.\n"
               "|stack: react@18.2.0, express@4.19.2\n|integrations: react+express\n")
    (staging / "context-snippet.md").write_bytes(snippet.encode("utf-8"))
    argv = _argv(call, "countTokensHelper", {"{skill_staging}": str(staging)})
    result = subprocess.run([sys.executable, str(COUNT_TOKENS), *argv], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (row,) = [row for row in json.loads(result.stdout)["files"] if row["path"] == "context-snippet.md"]
    assert row["tokens"] == len(snippet) // 4
    # Step 8's validator takes the same count of the same file.
    assert "approx_tokens = len(content) // 4" in VALIDATOR.read_text(encoding="utf-8")


# --- #538: compose-mode export names checked before the commit --------------------


def _names_check() -> str:
    return _from(_sections(_body(_read(GENERATE)))["8"], "**Compose-mode export names (compose mode only).**")


def test_compose_export_names_are_checked_before_the_commit():
    text = _read(GENERATE)
    assert _probe_script(text, "namesPresent") == NAMES_HELPER
    sections = _sections(_body(text))
    order = list(sections)
    assert order.index("8") < order.index("8b") < order.index("9")
    gate = sections["8"]
    assert GATE_RUN_RE.search(gate).start() < gate.index("**Compose-mode export names"), (
        "the name check must run after the body split, which can move names into references/")
    names = _names_check()
    call = _call(names, "namesPresentHelper")
    assert "--provenance {forge_version}/provenance-map.json" in call and "--skill-dir {skill_staging}" in call, call
    for needle in ("`absent[]`", "`--drop-absent`", "`{headless_mode}`", "compose-export-name-renamed",
                   "compose-export-name-dropped", "`workflow_warnings[]`"):
        assert needle in names, needle
    # A rename edits the entries file and runs the §7 helper again, which copies each metadata_hash:
    # the model never writes the map, so the schema's only-copier claim holds (step 5b review).
    assert "in `{composeEntriesFile}`" in names and "§7 compose-mode `provenance` call again" in names
    assert "{atomicWriteHelper}" not in names and "atomic writer" not in names
    assert "the only copier of each `metadata_hash`" in _read(SCHEMA)
    # The helper owns the rule: the step matches no name itself.
    for rule_word in ("case-sensitive", "substring", "verbatim", "`::`"):
        assert rule_word not in names, f"the step still states the name rule ({rule_word})"


def test_the_names_check_calls_run_as_written(tmp_path):
    call = _call(_names_check(), "namesPresentHelper")
    staging = tmp_path / "skills" / "demo-stack" / "1.0.0" / "demo-stack.skf-tmp"
    (staging / "references" / "integrations").mkdir(parents=True)
    (staging / "SKILL.md").write_bytes(b"# demo Stack Skill\n\n`createClient()` opens the session.\n")
    (staging / "references" / "liba.md").write_bytes(b"# liba\n\n`Session` holds its state.\n")
    (staging / "references" / "integrations" / "liba-libb.md").write_bytes(b"`toStream` feeds libb.\n")
    forge_version = tmp_path / "forge" / "demo-stack" / "1.0.0"
    forge_version.mkdir(parents=True)
    provenance = forge_version / "provenance-map.json"
    entries = [
        {"export_name": "createClient", "source_library": "liba"},
        {"export_name": "client factory", "source_library": "liba"},  # a descriptive label
        {"export_name": "toStream", "source_library": "liba"},  # written only in references/integrations/
        {"export_name": "Session", "source_library": "liba"},
    ]
    provenance.write_text(json.dumps({"skill_type": "stack", "entries": entries}), encoding="utf-8")
    argv = _argv(call, "namesPresentHelper", {"{forge_version}": str(forge_version), "{skill_staging}": str(staging)})

    def run(*flags):
        result = subprocess.run([sys.executable, str(NAMES_HELPER), *argv, *flags], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    code, out = run()
    assert code == 1
    assert [(a["entry_index"], a["export_name"]) for a in out["absent"]] == [(1, "client factory"), (2, "toStream")]
    # An interactive run renames the label to the identifier SKILL.md writes;
    # the --drop-absent run then drops what is still absent.
    entries[1]["export_name"] = "createClient"
    provenance.write_text(json.dumps({"skill_type": "stack", "entries": entries}), encoding="utf-8")
    code, out = run("--drop-absent")
    assert code == 0 and [d["export_name"] for d in out["dropped"]] == ["toStream"]
    kept = json.loads(provenance.read_text(encoding="utf-8"))["entries"]
    assert [e["export_name"] for e in kept] == ["createClient", "createClient", "Session"]
    assert run() == (0, {"checked": 3, "skipped": 0, "absent": [], "dropped": [], "provenance_written": False})


def test_the_name_rule_matches_the_scorer(tmp_path):
    # skf-test-skill credits a name found, case-sensitive, in SKILL.md or a .md
    # file directly in references/; a pair file in references/integrations/
    # does not count, and a `::` name is never looked up. The step 7 helper
    # applies that rule to the same text (verify-declared-numerator.py reads
    # the same text too).
    reconcile = _load(RECONCILE, "reconcile_coverage_stack_rules")
    names = _load(NAMES_HELPER, "skf_names_present_stack_rules")
    package = tmp_path / "demo-stack"
    (package / "references" / "integrations").mkdir(parents=True)
    (package / "SKILL.md").write_bytes("# demo\n\nCall `connect()` first; the `café` view renders.\n".encode("utf-8"))
    (package / "references" / "liba.md").write_bytes(b"# liba\r\n\r\n`Client` wraps a session.\r\n")
    (package / "references" / "integrations" / "liba-libb.md").write_bytes(b"`get_config` feeds libb.\n")
    text = reconcile.load_doc_text(str(package))
    assert names.load_doc_text(package) == text
    assert _load(NUMERATOR, "verify_declared_numerator_stack_rules").load_doc_text(str(package)) == text
    candidates = ["connect", "Client", "client", "get_config", "café", "wraps a", "Client::new"]
    credited = set(reconcile.names_present(candidates, text))
    assert credited == {"connect", "Client", "café", "wraps a"}
    checked, absent = names.find_absent([{"export_name": name} for name in candidates], text)
    looked_up = [name for name in candidates if "::" not in name]
    assert checked == len(looked_up)
    assert {item["export_name"] for item in absent} == set(looked_up) - credited


# --- #594, #586: the inputs step 1 binds, the stack name and the quality score -----


# The inputs the Invocation Contract declares.
CONTRACT_INPUTS = {"project_path", "skills", "stack_name", "scope_overrides", "architecture_doc_path", "mode"}
# An envelope line, indented or not (a list item holds some).
ANY_ENVELOPE_RE = re.compile(r"^\s*SKF_STACK_RESULT_JSON: (\{.*\})$", re.MULTILINE)
# Import counting or co-import detection done by hand.
HAND_COUNT_RE = re.compile(r"import \.\* from|\bgrep\b|\brg\b|Grep tool|subprocess", re.IGNORECASE)


def _contract_row(aspect: str) -> str:
    (row,) = [line for line in _read(CONTRACT).splitlines() if line.startswith(f"| **{aspect}** |")]
    return row


# A HARD HALT as a step file names it: `HALT (exit <code>, `halt_reason: "<reason>"`, phase `<phase>`...`,
# with `, or `halt_reason: "<other>"` for <case>` when one halt has two reasons of the same code.
HALT_NAMED_RE = re.compile(
    r'HALTs? \(exit (\d), `halt_reason: "([a-z-]+)"`(?:, or `halt_reason: "([a-z-]+)"` for [^,]+)?, '
    r"phase `([a-z-]+:[a-z-]+)`")


def _halts(text: str) -> list[tuple[int, str, str]]:
    """(exit code, halt_reason, phase) of every HARD HALT a text names, one per reason."""
    return [(int(code), reason, phase)
            for code, first, other, phase in HALT_NAMED_RE.findall(text)
            for reason in (first, other) if reason]


def test_the_contract_declares_every_input_step_1_binds():
    inputs = _contract_row("Inputs")
    declared = set(re.findall(r"`(\w+)`: ", inputs))
    assert declared == CONTRACT_INPUTS, declared
    assert "[required]" not in inputs
    sections = _sections(_body(_read(INIT)))
    bound = set(re.findall(r"^- `(\w+)` → ", sections["3"], re.MULTILINE))
    assert "the `stack_name` input" in sections["0"], "step 1 §0 does not bind the stack name"
    assert bound | {"stack_name"} == declared, bound


def test_a_bad_input_halts_with_input_invalid():
    sections = _sections(_body(_read(INIT)))
    for number in ("0", "3"):
        halts = [halt for halt in _halts(sections[number]) if halt[1] == "input-invalid"]
        assert len(halts) == 1 and halts[0][0] == 2, f"step 1 §{number}"
    exit_codes = _slice(_read(CONTRACT), "## Exit Codes", "## Result Contract")
    (row,) = [line for line in exit_codes.splitlines() if line.startswith("| 2 ")]
    assert "`input-invalid`" in row
    assert "input-invalid" in json.loads(ENVELOPE_SCHEMA.read_text(encoding="utf-8"))["properties"]["halt_reason"]["enum"]


def test_the_stack_name_names_every_path_and_envelope():
    zero = _sections(_body(_read(INIT)))["0"]
    assert "`-stack` appended" in zero and "else `{project_name}-stack`" in zero
    holders = {path.relative_to(STACK).as_posix(): _read(path).count("{project_name}-stack")
               for path in sorted(STACK.rglob("*.md"))
               if "{project_name}-stack" in _read(path) or "{project}-stack" in _read(path)}
    # Only the default itself, in step 1 §0 and the contract, names the old form.
    assert holders == {"references/invocation-contract.md": 1, "references/init.md": 1}, holders
    # Every staged halt payload names the stack by {stack_name}; the emitter types no other name.
    for path in sorted(REFS.glob("*.md")):
        for payload in re.findall(r'`(\{"phase": "<phase>".*?\})`', _read(path)):
            assert '"skill_name": "{stack_name}"' in payload, (path.name, payload)
    assert "--skill-dir-name {stack_name}" in _read(GENERATE)


def test_every_envelope_carries_the_quality_score():
    schema = json.loads(ENVELOPE_SCHEMA.read_text(encoding="utf-8"))
    assert "quality_score" in schema["required"], "every envelope, a halt's included, carries quality_score"
    two_b = _sections(_body(_read(REPORT)))["2b"]
    payload = json.loads(_first_fence(two_b))
    assert payload["quality_score"] is None and payload["result_contract"]["summary"]["quality_score"] is None
    assert "Both `quality_score` fields are `{quality_score}`" in two_b
    three = _sections(_body(_read(VALIDATE)))["3"]
    assert "Bind `{quality_score}` ← that score" in three and "not a test-skill score" in three
    # The contract leaves field meanings to the schema's descriptions.
    assert "not a test-skill score" in schema["properties"]["quality_score"]["description"]
    assert "whose descriptions say what each field holds" in _from(_read(CONTRACT), "## Result Contract (Headless)")


@pytest.mark.parametrize(("given", "verdict"), [
    pytest.param("acme-web", 0, id="skill-name"),
    pytest.param("a" * 58, 0, id="64-chars-with-suffix"),
    pytest.param("a" * 60, 1, id="66-chars-with-suffix"),
    pytest.param("acme--web", 1, id="two-hyphens"),
    pytest.param("Acme-web", 1, id="upper-case"),
])
def test_the_stack_name_check_runs_as_written(given, verdict):
    # Step 7's pre-commit check refuses these names for the stack's folder, which
    # the run cannot rename, so step 1 checks the bound name before anything runs.
    init = _read(INIT)
    zero = _sections(_body(init))["0"]
    assert _probe_script(init, "frontmatterValidator") == FRONTMATTER
    call = _call(zero, "frontmatterValidator")
    assert call.strip() == "uv run {frontmatterValidator} --check-name {stack_name}"
    stack_name = given if given.endswith("-stack") else f"{given}-stack"
    argv = _argv(call, "frontmatterValidator", {"{stack_name}": stack_name})
    result = subprocess.run([sys.executable, str(FRONTMATTER), *argv], capture_output=True, text=True)
    assert result.returncode == verdict, result.stdout
    assert 'HALT (exit 3, `halt_reason: "helper-missing"`, phase `init:stack-name`, no `skill_name`)' in zero
    assert "{each `issues[]` message}" in zero


# --- #606 item 5: {scan_root} from project_path or one question -------------------


def test_step_1_binds_the_scan_root():
    three = _sections(_body(_read(INIT)))["3"]
    root = _from(three, "**Scan root.**").split("\n\n")[0]
    assert "It is `project_path` when given" in root and "else `project_root`" in root
    scope = _from(three, "**Scan scope (code mode).**")
    assert "no `project_path` was given, ask once" in scope
    assert "**GATE [default: A]**: headless, do not ask; keep the project root" in scope
    # The recorded decision tells the user to pass project_path; no warning repeats it.
    assert "pass project_path to scan one package" in _decision("init.scan-root")["reason"]
    assert "headless-scan-root-default" not in scope
    inputs = _contract_row("Inputs")
    assert "`project_path`: the folder code mode scans (default: the project root;" in inputs
    assert "an interactive run asks once" in inputs
    assert "`folders[]` lists more than one folder" in scope


def test_steps_2_3_and_5_stay_inside_the_scan_root():
    init, manifests, rank = _read(INIT), _read(MANIFESTS), _read(RANK)
    scan = "uv run {scanManifestsHelper} scan {scan_root} --include-dev"
    assert _probe_script(init, "scanManifests") == SCAN_MANIFESTS == _probe_script(manifests, "scanManifests")
    assert _call(_sections(_body(init))["3"], "scanManifestsHelper", "scan").strip() == scan
    assert _call(_sections(_body(manifests))["2"], "scanManifestsHelper", "scan").strip() == scan
    assert _probe_script(rank, "countImports") == COUNT_IMPORTS
    count = _call(_sections(_body(rank))["1"], "countImportsHelper", "count").strip()
    assert count == ('uv run {countImportsHelper} count {scan_root} --deps - --relative-to {project_root}'
                     ' > "{importCountsFile}"')
    sections = _sections(_body(_read(DETECT)))
    assert "`{importCountsFile}`" in sections["1"]
    # Pair files and CCC hits share the project-root base, so the guard compares paths as they stand.
    assert "both paths are relative to `{project_root}`" in sections["2"]


def test_the_monorepo_note_points_back_to_step_1():
    two = _sections(_body(_read(MANIFESTS)))["2"]
    note = _from(two, "When `folders[]` lists more than one folder").split("\n\n")[0]
    assert "the folder step 1 §3 chose" in note and "re-run with `project_path`" in note


# --- #606 item 4: compose candidates from the enumerate helper ---------------------


def test_compose_candidates_come_from_the_helper():
    skills = _read(COMPOSE_SKILLS)
    assert _probe_script(skills, "enumerateStackSkills") == ENUMERATE
    zero = _sections(_body(skills))["1"]
    call = _call(zero, "enumerateStackSkillsHelper", "candidates").strip()
    assert call == 'uv run {enumerateStackSkillsHelper} candidates {skills_output_folder} [--explicit "<names>"]'
    for field in ("`{skill_candidates}`", "`manifest_parse_error`", "`not_skf_output`", "`excluded[]`",
                  "`stale_manifest_keys`", "`kept[]`"):
        assert field in zero, field
    halts = [(code, reason) for code, reason, _ in _halts(zero)]
    assert halts == [(3, "helper-missing")] + [(3, "resolution-failure")] * 2, (
        "a missing helper is helper-missing; the stale-manifest and no-skill halts keep resolution-failure")
    for stale in ("try/except", "visited set", "*/active/*/SKILL.md", "`{stack_roster}`", "enumerate {skills"):
        assert stale not in zero, stale
    assert "An exit `1` (no skills folder) counts as an empty `kept[]`" in zero
    init = _read(INIT)
    three = _sections(_body(init))["3"]
    assert _probe_script(init, "enumerateStackSkills") == ENUMERATE
    # Step 1 runs the call step 2 would, explicit list included, and step 2 reuses its result.
    assert _call(three, "enumerateStackSkillsHelper", "candidates").strip() == call
    assert "When step 1 kept `{skill_candidates}`, use that result: it ran this same call." in zero
    assert ".export-manifest.json" not in three, "step 1 still reads the export manifest by hand"
    assert "**Compose-mode skill names.**" not in three, "step 1 still reduces package paths by hand"
    # A headless run accepts the suggestion, which names only the listed skills when a list is given.
    headless = _from(three, "**GATE [default: accept]**, headless default:").split("\n\n")[0]
    assert "accept the suggestion" in headless and "With `explicit_deps`, keep code mode" not in headless


def test_the_candidates_call_runs_as_written(tmp_path):
    call = _call(_sections(_body(_read(COMPOSE_SKILLS)))["1"], "enumerateStackSkillsHelper", "candidates").strip()
    skills = tmp_path / "skills"
    for name, skill_type, generator in (("alpha", "single", "create-skill"),
                                        ("app-stack", "stack", "create-stack-skill")):
        package = skills / name / "1.0.0" / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_bytes(b"# x\n")
        metadata = {"name": name, "skill_type": skill_type, "generated_by": generator, "exports": []}
        (package / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def run(written: str) -> dict:
        argv = _argv(written, "enumerateStackSkillsHelper", {"{skills_output_folder}": str(skills)})
        result = subprocess.run([sys.executable, str(ENUMERATE), *argv], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    named = run(call.replace('[--explicit "<names>"]', '--explicit "alpha,app-stack,gone"'))
    assert [(e["name"], e["path"]) for e in named["kept"]] == [("alpha", "alpha/1.0.0/alpha")]
    # A campaign passes package paths: the helper reduces each to its skill folder.
    package = (skills / "alpha" / "1.0.0" / "alpha").as_posix()
    paths = run(call.replace('[--explicit "<names>"]', f'--explicit "{package},{tmp_path.as_posix()}/x/y"'))
    assert [e["name"] for e in paths["kept"]] == ["alpha"]
    assert [x["reason"] for x in paths["excluded"]] == ["outside-skills-root"]
    assert {x["skill_dir"]: x["reason"] for x in named["excluded"]} == {
        "app-stack": "not-a-skill", "gone": "no-such-folder"}
    assert all(x["message"].startswith(x["skill_dir"] + ": ") for x in named["excluded"])
    # A manifest key whose folder is gone is the stale-manifest halt.
    (skills / ".export-manifest.json").write_text(json.dumps({"exports": {"alpha": {}, "gone": {}}}),
                                                  encoding="utf-8")
    listed = run(call.replace(' [--explicit "<names>"]', ""))
    assert [e["name"] for e in listed["kept"]] == ["alpha"] and listed["stale_manifest_keys"] == ["gone"]


# --- #598: import counts, the searched files and the co-import pairs ---------------


def test_step_3_counts_imports_with_the_helper():
    rank = _read(RANK)
    code = _sections(_body(rank))["1"]
    found = HAND_COUNT_RE.search(code)
    assert found is None, f"step 3 still counts by hand: {found.group(0)!r}"
    for stale in ("{manifestPatternsPath}", "Exclude from counting", "Use subprocess Pattern 1"):
        assert stale not in rank, stale
    assert "`{importCountsFile}`" in code and "`unresolved[]`" in code
    assert (3, "helper-missing", "rank-and-confirm:count") in _halts(code), "a missing import counter halts with no code"
    assert (3, "helper-missing", "init:mode") in _halts(_sections(_body(_read(INIT)))["3"])
    exit_codes = _slice(_read(CONTRACT), "## Exit Codes", "## Result Contract")
    (row,) = [line for line in exit_codes.splitlines() if line.startswith("| 3 ")]
    assert "`skf-count-imports.py` (step 3 §1, `references/compose-scope.md` §1)" in row
    unresolved = _from(code, "**Unresolved names.**").split("\n\n")[0]
    assert "a guessed import name that matched no file, no import name, or an ecosystem with no import rules" \
        in unresolved
    # #1153 determinism-5: a known import name reruns the same count, whose output is the counts file; the
    # model never splices an entry into it.
    for token in ("run the command above again, unchanged, redirect included",
                  "adding one `--module <name>=<import name>` per such entry (`--module acme-client=acme`)",
                  "the helper counts and ranks it with the others",
                  "§2 leaves every other unresolved entry out with its `reason`",
                  # The redirect empties the counts before the helper runs, so a refused `--module` is rerun.
                  "A later rerun keeps every `--module` an earlier one passed.",
                  "on a non-zero exit fix or drop the `--module` its error names and run the command again before "
                  "§2"):
        assert token in unresolved, token
    for stale in ("write the file back", "without the `>` redirect", "drop the entry from `unresolved[]`",
                  "keep `dependencies[]` sorted", '"modules"'):
        assert stale not in rank, stale
    two = _sections(_body(rank))["2"]
    # #1153 determinism-9: the scope, its reasons and the unknown overrides come from the helper.
    assert _call(two, "countImportsHelper", "scope").endswith('> "{scopeFile}"')
    for stale in ("**Include by default:**", "**Below threshold:**", "**Apply scope_overrides**", "Apply filtering"):
        assert stale not in two, stale
    assert 'scope: "dev"' in _sections(_body(rank))["3"], "the Category column does not follow scope"
    gate = [line for line in _sections(_body(rank))["3"].splitlines() if line.startswith("- **GATE")]
    assert len(gate) == 1 and "the recommended libraries in code mode" in gate[0]


def test_step_2_shows_what_the_scanner_searched():
    sections = _sections(_body(_read(MANIFESTS)))
    message = _slice(sections["2"], "**Interactive mode:**", "STOP and wait")
    assert "`searched_filenames`" in message
    assert "csproj" not in _read(MANIFESTS)
    assert "`scope`" in sections["3"] and "`total_unique_dev`" in sections["3"]


def test_step_5_takes_co_imports_from_step_3s_counts():
    text = _read(DETECT)
    code = _sections(_body(text))["2"]
    found = HAND_COUNT_RE.search(code)
    assert found is None, f"step 5 still finds co-imports by hand: {found.group(0)!r}"
    for needle in ("`intersection_count` 2 or more", "`line_a`", "`line_b`",
                   "The pair's co-import files stay in `{pairsFile}`"):
        assert needle in code, needle
    # Step 5 types no co-import file: step 7's helper copies them from the saved pairs (determinism-2).
    assert "`co_import_files` ←" not in text
    guard = _from(code, "**CCC precision guard:**").split("\n\n")[0]
    assert "keep a CCC-surfaced file only when the pair's `files[]` lists it" in guard
    # A file that imports both libraries is already a pair file: CCC never raises a count.
    assert "CCC never changes which pairs qualify" in code
    for stale in ("even without explicit import co-location", "0 or 1 co-import files", "ccc-augmented"):
        assert stale not in text, stale
    assert "{manifestPatternsPath}" not in text
    patterns = _read(INTEGRATION_PATTERNS)
    for stale in ("## Co-Import Detection", "extract all import statements", "ccc-augmented"):
        assert stale not in patterns, stale


def test_the_scan_count_and_pair_calls_run_as_written(tmp_path):
    """Step 1 scans, step 3 counts inside the chosen package, step 5 pairs from those counts."""
    project = tmp_path / "project"
    files = {
        "apps/web/package.json": b'{"name": "web", "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0",'
                                 b' "zustand": "^4.5.0"}, "devDependencies": {"vitest": "^1.0.0"}}\n',
        "apps/web/requirements.txt": b"PyYAML==6.0\n",
        "apps/web/src/main.tsx": b'import React from "react";\nimport { createRoot } from "react-dom/client";\n'
                                 b'import { create } from "zustand";\n',
        "apps/web/src/store.tsx": b'import { create } from "zustand";\nimport { hydrateRoot } from "react-dom/client";\n',
        "apps/web/tools/a.py": b"import yaml\n",
        "apps/web/tools/b.py": b"from yaml import safe_load\n",
        "apps/api/package.json": b'{"name": "api", "dependencies": {"express": "^4.19.0"}}\n',
        "apps/api/server.js": b'const express = require("express");\n',
        "apps/api/routes.js": b'const express = require("express");\n',
    }
    for rel, content in files.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_bytes(content)

    counts_file = tmp_path / "run" / "import-counts.json"
    counts_file.parent.mkdir()

    def run(script: Path, call: str, helper: str, scan_root: Path, stdin: str | None = None,
            names: str = "") -> dict:
        argv = _argv(call, helper, {"{scan_root}": str(scan_root), "{project_root}": str(project),
                                    "<names>": names, "{importCountsFile}": str(counts_file)})
        result = subprocess.run([sys.executable, str(script), *argv], input=stdin, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    scan_call = _call(_sections(_body(_read(INIT)))["3"], "scanManifestsHelper", "scan").strip()
    whole = run(SCAN_MANIFESTS, scan_call, "scanManifestsHelper", project)
    folders = [f["path"] for f in whole["folders"]]
    assert whole["monorepo"] is True and folders == ["apps/api", "apps/web"], "step 1 would ask its question"
    assert {f["path"]: f["names"] for f in whole["folders"]}["apps/web"] == ["web"]
    # The user names apps/web: step 1 scans it again, and steps 2 and 3 read only that package.
    web = project / "apps" / "web"
    scan = run(SCAN_MANIFESTS, scan_call, "scanManifestsHelper", web)
    assert (scan["total_unique"], scan["total_unique_dev"]) == (4, 1)
    assert {"package.json", "requirements.txt", "Package.swift"} <= set(scan["searched_filenames"])
    count_call = _call(_sections(_body(_read(RANK)))["1"], "countImportsHelper", "count").strip()
    count_call, target = count_call.split(" > ")
    assert target == '"{importCountsFile}"', "step 3 does not save its counts in the run folder"
    counts = run(COUNT_IMPORTS, count_call, "countImportsHelper", web, json.dumps(scan))
    # The shell redirect writes the counts file step 5 reads.
    counts_file.write_text(json.dumps(counts), encoding="utf-8")
    by_name = {d["name"]: d for d in counts["dependencies"]}
    assert "express" not in by_name, "a dependency outside the scan root was counted"
    assert (by_name["react"]["file_count"], by_name["react"]["above_threshold"]) == (1, False), "react-dom counted"
    assert by_name["PyYAML"]["above_threshold"] is True, "PyYAML's yaml imports were not counted"
    assert by_name["vitest"]["scope"] == "dev"
    recommended = [d["name"] for d in counts["dependencies"] if d["above_threshold"] and "scope" not in d]
    assert recommended == ["PyYAML", "react-dom", "zustand"]
    # Paths are relative to the project root, as source_file and the CCC hits are.
    assert [f["path"] for f in by_name["zustand"]["files"]] == ["apps/web/src/main.tsx", "apps/web/src/store.tsx"]
    # Step 5 §1: the counts file read as it stands; each pair carries its co-import files and lines.
    pair_call = _call(_sections(_body(_read(DETECT)))["1"], "pairIntersectHelper", "intersect").strip()
    pair_call, target = pair_call.split(" > ")
    assert target == '"{pairsFile}"', "step 5 does not save its pairs in the run folder"
    pairs = run(PAIR_INTERSECT, pair_call, "pairIntersectHelper", web, names=",".join(recommended))["pairs"]
    assert [(p["a"], p["b"], p["intersection_count"]) for p in pairs] == [("react-dom", "zustand", 2)]
    assert pairs[0]["files"] == [{"path": "apps/web/src/main.tsx", "line_a": 2, "line_b": 3},
                                 {"path": "apps/web/src/store.tsx", "line_a": 2, "line_b": 1}]


# --- Every create-stack step file -------------------------------------------------


# The rule that no Rules block forbids every write ahead of a section that
# writes runs for every workflow in test-skf-chain-reachability.py (#585);
# these pin the two patterns the #536 and #539 checks above use.
@pytest.mark.parametrize("rule", [
    "Do not write or modify any files: report is console output only",
    "Validate structure and completeness, not content quality: validation is read-only",
    "Write all output files in correct directory structure, do not modify compiled content from Step 06",
    "Do not write output files (Step 07)",
    "No user-facing reports, file writes, or result contracts in this step",
])
def test_blanket_rule_pattern_matches_a_no_write_rule(rule):
    assert BLANKET_NO_WRITE_RE.search(rule)


@pytest.mark.parametrize("line", [
    "<json-content> | python3 {atomicWriteHelper} write \\",
    "python3 {atomicWriteHelper} commit-dir --target {skill_package}",
    "npx skill-check check <skill-dir> --fix --format json --no-security-scan",
    "npx skill-check split-body <skill-dir> --write",
    "mkdir -p {forge_version}",
])
def test_write_pattern_matches_a_write(line):
    assert WRITE_OP_RE.search(line)


@pytest.mark.parametrize("line", [
    "uv run {skillInventoryHelper} {skills_output_folder} --skill {stack_name} --write-check",
    "npx skill-check check <skill-dir> --format json",
    "timeout 10s npx --no-install skill-check -h",
])
def test_write_pattern_skips_a_read(line):
    assert not WRITE_OP_RE.search(line)


@pytest.mark.parametrize("path", sorted(STACK.rglob("*.md")), ids=lambda p: p.relative_to(STACK).as_posix())
def test_in_file_anchor_links_name_a_heading(path):
    text = _read(path)
    headings = {_slug(m.group(2)) for m in HEADING_RE.finditer(text)}
    missing = [anchor for anchor in ANCHOR_LINK_RE.findall(text) if anchor not in headings]
    assert not missing, f"{path.name}: anchor links with no heading: {missing}"


# --- #593 (create-stack part): every halt through the emitter, helper-missing ------

# The halts a missing shared helper raises, by phase (generate-output §6's goes
# through the rollback contract and is checked on its own).
HELPER_MISSING_PHASES = {
    "init:emitter", "init:stack-name", "init:mode", "init:run-state", "compose-skills:enumerate",
    "detect-manifests:scan",
    "rank-and-confirm:count", "compose-scope:scope", "compose-extract:enumerate", "parallel-extract:library-tiers",
    "detect-integrations:pair-intersect", "compose-pairs:comention", "detect-integrations:pair-tiers",
    "compile-stack:stats", "generate-output:atomic-writer",
}
HALT_COMMAND = ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" '
                '--target stderr < "{run_dir}/halt.json"')
RECORD_DECISION = ('uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" '
                   '--decision < "{run_dir}/decision.json"')


def _schema() -> dict:
    return json.loads(ENVELOPE_SCHEMA.read_text(encoding="utf-8"))


def _exit_codes() -> dict[str, int]:
    return _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"]


def _sequence(path: Path) -> str:
    """A step file's body after its Rules, or a reference file whole."""
    text = _read(path)
    return _body(text) if "## Rules\n" in text else text


def _step_halts() -> dict[str, list[tuple[int, str, str]]]:
    return {path.name: _halts(_sequence(path)) for path in STEP_FILES if path != CONTRACT}


def test_every_halt_names_its_code_reason_and_phase():
    codes = _exit_codes()
    for name, halts in _step_halts().items():
        text = _sequence(REFS / name)
        assert len(re.findall(r"HALTs? \(exit", text)) == len(HALT_NAMED_RE.findall(text)), (
            f"{name}: a HALT annotation does not parse")
        for code, reason, phase in halts:
            assert codes.get(reason) == code, f"{name}: {reason} exits {codes.get(reason)}, not {code}"
            assert phase.split(":")[0] == name.removesuffix(".md"), f"{name}: phase {phase} names another step"
        for bare in ("HALT if no candidate exists", "HALT if neither", "emit the result envelope on stderr per"):
            assert bare not in text, f"{name}: {bare!r}"


def test_every_halt_reason_is_raised_and_listed():
    raised = {reason for halts in _step_halts().values() for _, reason, _ in halts}
    enum = {reason for reason in _schema()["properties"]["halt_reason"]["enum"] if reason}
    assert raised == enum == set(_exit_codes()), (raised ^ enum)
    exit_codes = _slice(_read(CONTRACT), "## Exit Codes", "## Result Contract")
    listed = set(re.findall(r"\(`([a-z-]+)`", exit_codes)) | set(re.findall(r"; [^|;]*\(`([a-z-]+)`", exit_codes))
    assert enum <= set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", exit_codes)) | listed, "a halt_reason is missing a row"


def test_a_missing_helper_halts_helper_missing():
    phases = {phase for halts in _step_halts().values() for _, reason, phase in halts if reason == "helper-missing"}
    assert phases == HELPER_MISSING_PHASES
    six = _sections(_body(_read(GENERATE)))["6"]
    assert 'with exit 3, `halt_reason: "helper-missing"` and phase `generate-output:metadata`' in six
    (row,) = [line for line in _read(CONTRACT).splitlines() if line.startswith("| 3 ")]
    for helper in ("skf-emit-result-envelope.py", "skf-validate-frontmatter.py", "skf-scan-manifests.py",
                   "skf-enumerate-stack-skills.py", "skf-count-imports.py", "skf-render-stack-metadata.py",
                   "skf-pair-intersect.py", "skf-comention-pairs.py", "skf-atomic-write.py"):
        assert f"`{helper}`" in row, helper
    # SKILL.md's main-thread rule no longer covers a helper whose step halts without it, and leaves an
    # advisory check to its step: step 8 runs its manual checks when the output validator is missing.
    (rule,) = [line for line in _read(STACK_SKILL).splitlines() if "achieve the outcome in your main context" in line]
    assert "never work out by hand what a shared helper computes where its step names a `helper-missing` HALT" in rule
    assert "Where a step says what to do without its helper (an advisory check, a default value), do as it says" \
        in rule
    assert "\u2014" not in rule
    validate = _read(VALIDATE)
    assert "Advisory mode" in _rules(validate) and not _halts(_sequence(VALIDATE))
    assert "fall back to the manual file/frontmatter/snippet checks" in _sections(_body(validate))["1"]


def test_the_compose_branch_has_no_prose_fallback():
    """#599: a helper that halts when missing has no hand-run equivalent."""
    text = _read(DETECT) + _read(COMPOSE_PAIRS)
    assert "Graceful degradation" not in text and "perform the equivalent scan directly" not in text
    compose = _compose_branch()
    assert compose.index("phase `compose-pairs:comention`") < compose.index("uv run {comentionHelper}")
    assert "when no candidate resolves or `uv` cannot run it" not in compose


def test_an_unknown_verdict_token_halts_with_exit_2():
    (bullet,) = [line for line in _compose_branch().splitlines() if line.startswith("- **`unknownTokens`")]
    assert _halts(bullet) == [(2, "unknown-verdict-token", "compose-pairs:vs-report")]


@pytest.mark.parametrize("path", [p for p in STEP_FILES if p != CONTRACT], ids=lambda p: p.name)
def test_every_halting_step_shows_the_emit_command(path):
    text = _read(path)
    if not _halts(_sequence(path)):
        return
    assert _probe_script(text, "emitEnvelope") == EMITTER
    envelope = _from(_body(text), "**Halt envelope.**").split("###", 1)[0]
    assert HALT_COMMAND in _fence_lines(envelope), f"{path.name} does not show the emit-halt command"
    assert "display the halt message alone" in envelope


def test_no_step_types_an_envelope_line():
    typed = [path.name for path in sorted(STACK.rglob("*.md")) if ANY_ENVELOPE_RE.search(_read(path))]
    assert typed == ["invocation-contract.md"], typed
    assert "never type an `SKF_STACK_RESULT_JSON` line" in _read(STACK_SKILL)


def _payload(text: str) -> dict:
    """A staged JSON payload as a step file shows it, its placeholders filled."""
    filled = text.replace(", ...]", "]").replace("{N}", "3")
    return json.loads(filled)


def test_a_staged_halt_emits_a_schema_valid_envelope(tmp_path):
    from jsonschema import Draft202012Validator

    envelope_text = _from(_body(_read(GENERATE)), "**Halt envelope.**")
    staged = re.search(r'`(\{"phase": "<phase>".*?\})`', envelope_text).group(1)
    payload = _payload(staged.replace("<phase>", "generate-output:atomic-writer")
                       .replace("<halt_reason>", "helper-missing").replace("<code|compose>", "code"))
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-create-stack-skill-ab12cd34"
    run_dir.mkdir(parents=True)
    (run_dir / "warnings.jsonl").write_text('"[step-04/warn] extraction-failed: libz: timeout"\n', encoding="utf-8")
    (run_dir / "halt.json").write_text(json.dumps(payload), encoding="utf-8")
    argv = _argv(HALT_COMMAND.split(" < ")[0], "emitEnvelopeHelper", {"{run_dir}": str(run_dir)})
    result = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(payload),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (line,) = result.stderr.splitlines()
    envelope = json.loads(line.removeprefix("SKF_STACK_RESULT_JSON: "))
    assert not list(Draft202012Validator(_schema()).iter_errors(envelope))
    assert (envelope["exit_code"], envelope["skill_name"], envelope["run_id"]) == (3, "{stack_name}", "ab12cd34")
    assert envelope["warnings"] == ["[step-04/warn] extraction-failed: libz: timeout"]
    assert envelope["error"]["phase"] == "generate-output:atomic-writer"


# --- #593: auto-decisions recorded the moment a gate decides ----------------------

GATES = {
    "init.compose-suggestion": INIT,
    "init.scan-root": INIT,
    "rank-and-confirm.scope": RANK,
    "compile-stack.review": COMPILE,
}


def _decision(gate: str) -> dict:
    text = _read(GATES[gate])
    staged = re.search(r'`(\{"gate": "' + re.escape(gate) + r'".*?\})`(?: as|,)', text, re.DOTALL)
    assert staged, f"no staged decision for {gate}"
    return _payload(staged.group(1))


@pytest.mark.parametrize("gate", sorted(GATES))
def test_every_headless_gate_records_its_decision(gate, tmp_path):
    from jsonschema import Draft202012Validator

    decision = _decision(gate)
    item = _schema()["properties"]["headless_decisions"]["items"]
    assert not list(Draft202012Validator(item).iter_errors(decision)), decision
    assert decision["default_action"] == decision["taken_action"]
    run_dir = tmp_path / "skf-create-stack-skill-run1"
    argv = _argv(RECORD_DECISION.split(" < ")[0], "emitEnvelopeHelper", {"{run_dir}": str(run_dir)})
    result = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(decision),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((run_dir / "headless-decisions.jsonl").read_text(encoding="utf-8")) == decision
    # The record command the gate runs stages the decision the same way.
    assert RECORD_DECISION in _read(GATES[gate])


def test_the_scope_gate_records_the_libraries_it_drops():
    evidence = _decision("rank-and-confirm.scope")["evidence"]
    assert set(evidence) == {"scope", "dropped", "prior_kept"} and set(evidence["dropped"][0]) == {"library", "reason"}
    assert isinstance(evidence["prior_kept"], list), "#1152: one stable shape, [] when nothing was kept"
    (gate,) = [line for line in _sections(_body(_read(RANK)))["3"].splitlines() if line.startswith("- **GATE")]
    assert "names each library the default left out" in gate
    report = _sections(_body(_read(GENERATE)))["8b"]
    assert "`{run_dir}/headless-decisions.jsonl`" in report and "dropped libraries" in report
    assert "`prior_kept`" in report
    described = _schema()["properties"]["headless_decisions"]["items"]["properties"]["evidence"]["description"]
    assert "prior_kept" in described and "'in v<version>: '" in described


def test_the_scope_is_confirmed_at_one_gate():
    """#599 architecture-2: the user confirms the scope once, and both modes set it before the gate."""
    rank = _read(RANK)
    sections = _sections(_body(rank))
    assert list(sections) == ["1", "2", "3"]
    assert rank.count("**Select:**") == 1 and "Please confirm your scope" not in rank
    assert "ask for final confirmation" not in rank
    assert "Set `confirmed_dependencies` ← the recommended scope" in sections["2"]
    # #1151: compose-scope.md sets the compose scope, and §1's guard sends a compose run to the one gate.
    (guard,) = [line for line in sections["1"].splitlines() if "compose_mode" in line]
    assert guard.startswith("**If `compose_mode` is true:** `references/compose-scope.md` set `confirmed_dependencies`")
    assert guard.endswith("Skip to [Confirm the Scope](#3-confirm-the-scope).")
    scope = _sections(_body(_read(COMPOSE_SCOPE)))["1"]
    assert scope.rstrip().endswith("Set `confirmed_dependencies` ← `{scopeFile}`'s `scope`.")
    assert "**Select:**" not in _read(COMPOSE_SCOPE), "compose-scope.md holds a second scope gate"


# --- #587 (create-stack part): the run folder holds the run's state ---------------


def test_the_run_folder_is_created_before_anything_can_halt(tmp_path):
    init = _read(INIT)
    assert _probe_script(init, "emitEnvelope") == EMITTER
    preflight = _slice(_body(init), "**Pre-flight: the emitter and the run folder.**", "### 0.")
    (mktemp,) = [line for line in _fence_lines(preflight) if "mktemp -d" in line]
    filled = mktemp.replace("{project-root}", tmp_path.as_posix())
    if sys.platform != "win32":
        result = subprocess.run(["sh", "-c", filled], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        made = Path(result.stdout.strip())
        assert made.is_dir() and made.parent == tmp_path / "_bmad-output" / ".skf-run"
        assert made.name.startswith("skf-create-stack-skill-")
    assert (4, "write-failure", "init:run-folder") in _halts(preflight)
    assert (3, "helper-missing", "init:emitter") in _halts(preflight)
    skill = _read(STACK_SKILL)
    assert "no mid-run checkpoint" not in skill and "State lives in memory" not in skill
    assert "Single-pass, no resume" not in skill
    (state,) = [p for p in skill.split("\n\n") if p.startswith("**Resume only at the review gate:**")]
    assert "`{run_dir}`" in state and state.count(". ") == 0, "the run state is one sentence naming the run folder"
    assert "re-read from its `run.json`" in state and "unless step 1 resumes an interactive one" in state
    # `run.json` holds step 1's bindings (and step 2's rebinds), not every binding a later step makes.
    assert "a step 1 binding lost to compaction" in state


def test_the_extraction_bundle_is_written_and_read_from_disk():
    extract = _read(EXTRACT)
    bundle = json.loads(_first_fence(_from(_body(extract), "**Extraction bundle.**")))
    assert set(bundle) == {"mode", "scope", "per_library_extractions", "failed", "integrations", "hubs",
                           "cross_cutting"}
    sections = _sections(_body(extract))
    assert "write `{bundleFile}`: `mode`, `scope`" in sections["3"]
    # Compose mode writes each constituent's entry, with what its subagent read, from compose-extract.md (#1151).
    compose = _read(COMPOSE_EXTRACT)
    three = _sections(_body(compose))["3"]
    assert "Write `{bundleFile}`: `mode`, `scope` and these entries" in three
    assert "§1+" not in compose + extract and "fan-out at" not in compose
    assert ("- `description_keywords`, `usage_patterns` and `signatures`: what §2 returned for it, each usage pattern "
            "with the file and line it cites.") in three
    detect_graph = _sections(_body(_read(DETECT)))["4"]
    assert "Write the graph into `{bundleFile}`" in detect_graph
    # The bundle carries no co-import file: they stay in the saved pairs, which step 7's helper reads.
    assert '"co_import_files"' not in detect_graph and "`{pairsFile}`" in detect_graph
    for key in ("`hubs`", "`cross_cutting`"):
        assert key in detect_graph, key
    # Step 6: the bundle, and in code mode each library's key exports from its records, which the
    # entry no longer holds; a dropped library leaves both files.
    compile_ = _read(COMPILE)
    assert "exportRecordsFile: '{run_dir}/export-records.json'" in _frontmatter(compile_)
    one = _sections(_body(compile_))["1"]
    assert "compiles from `{bundleFile}`" in one
    assert "key exports are its records in `{exportRecordsFile}` in code mode" in one
    (feedback,) = [line for line in compile_.splitlines() if line.startswith("- IF Any other:")]
    assert "its records from `{exportRecordsFile}`" in feedback and "from `{bundleFile}` too" in feedback
    generate = _sections(_body(_read(GENERATE)))
    for number in ("3", "4", "6", "7"):
        assert "`{bundleFile}`" in generate[number], f"step 7 §{number} does not read the bundle"
    assert "`entries` of `{exportRecordsFile}`" in generate["7"]


def test_the_draft_is_reviewed_by_path_and_staged_verbatim():
    compile_ = _read(COMPILE)
    sections = _sections(_body(compile_))
    seven = sections["7"]
    assert "Write the compiled SKILL.md to `{draftFolder}/SKILL.md`" in seven
    assert "{Display full compiled SKILL.md content}" not in compile_
    menu = sections["8"]
    assert "[P] Preview the full draft" in menu and "- IF P: Display the full draft files" in menu
    (gate,) = [line for line in menu.splitlines() if line.startswith("- **GATE")]
    assert "displaying no draft" in gate
    assert "apply it to the draft files in `{draftFolder}`" in menu
    two = _sections(_body(_read(GENERATE)))["2"]
    assert _fence_lines(two) == ['cp "{draftFolder}/SKILL.md" "{skill_staging}/SKILL.md"']
    assert "skill_content" not in _read(GENERATE)


def test_the_compile_stats_come_from_the_metadata_helper():
    """W3 handoff: Libraries, Integration pairs and the tier line come from one helper run."""
    text = _read(COMPILE)
    assert _probe_script(text, "renderStackMetadata") == STACK_METADATA
    sections = _sections(_body(text))
    one = sections["1"]
    call = _call(one, "renderStackMetadataHelper", "metadata")
    assert call.strip() == "uv run {renderStackMetadataHelper} metadata --input -"
    assert (3, "helper-missing", "compile-stack:stats") in _halts(one)
    assert "Bind `{lib_count}` ← its `library_count` and `{integration_count}` ← its `integration_count`" in one
    # The description §2 writes and the stats §7 shows take those bindings; nothing counts by hand.
    assert "with the counts §1 bound" in sections["2"]
    assert "{lib_count} libraries with" in _first_fence(_h2_section(_read(TEMPLATE), "## SKILL.md Section Structure"))
    seven = sections["7"]
    assert "renderStackMetadataHelper" not in seven and "the count of" not in text
    for field in ("{lib_count}", "{integration_count}", "`confidence_distribution.t1`"):
        assert field in seven, field
    (feedback,) = [line for line in text.splitlines() if line.startswith("- IF Any other:")]
    assert "run the §1 helper call again" in feedback and "rewrite the draft's `description`" in feedback
    out = _run_stack_metadata(call, _stack_input())
    assert (out["library_count"], out["integration_count"]) == (3, 2)


def test_working_files_go_after_commit_and_the_folder_after_the_envelope():
    nine = _sections(_body(_read(GENERATE)))["9"]
    assert nine.index("commit-dir --target {skill_package}") < nine.index(
        'rm -rf "{draftFolder}" "{bundleFile}" "{exportRecordsFile}"')
    three = _sections(_body(_read(REPORT)))["3"]
    two_b = _sections(_body(_read(REPORT)))["2b"]
    assert 'rm -rf "{run_dir}"' in three and "emit --workflow skf-create-stack-skill" in two_b


# --- #593: the result contract and the success envelope ---------------------------


def test_the_success_envelope_and_result_files_come_from_the_emitter(tmp_path):
    from jsonschema import Draft202012Validator

    report = _read(REPORT)
    assert _probe_script(report, "emitEnvelope") == EMITTER
    two_b = _sections(_body(report))["2b"]
    for stale in ("{pid}", "{rand}", "{YYYYMMDD-HHmmss}", "Append `-{pid}"):
        assert stale not in report, stale
    (emit,) = [line for line in _fence_lines(two_b) if "{emitEnvelopeHelper} emit " in line]
    payload = json.loads(_first_fence(two_b))
    payload["mode"] = "code"
    # #902: step 8 §9's outcome for a scan that could not run, at the top level and in the contract's summary
    payload["security_result"] = payload["result_contract"]["summary"]["security_result"] = "skipped"
    run_dir = tmp_path / "skf-create-stack-skill-run9"
    forge_version = tmp_path / "forge" / "demo-stack" / "18.2.0"
    run_dir.mkdir()
    forge_version.mkdir(parents=True)
    (run_dir / "headless-decisions.jsonl").write_text(json.dumps(_decision("rank-and-confirm.scope")) + "\n",
                                                      encoding="utf-8")
    argv = _argv(emit.split(" < ")[0], "emitEnvelopeHelper",
                 {"{run_dir}": str(run_dir), "{forge_version}": str(forge_version)})
    result = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(payload),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout.strip().removeprefix("SKF_STACK_RESULT_JSON: "))
    assert not list(Draft202012Validator(_schema()).iter_errors(envelope))
    assert (envelope["status"], envelope["exit_code"], envelope["run_id"]) == ("success", 0, "run9")
    assert envelope["headless_decisions"][0]["gate"] == "rank-and-confirm.scope"
    names = sorted(p.name for p in forge_version.iterdir())
    assert len(names) == 2 and names[1] == "create-stack-skill-result-latest.json"
    assert re.fullmatch(r"create-stack-skill-result-\d{8}-\d{6}\.json", names[0]), names
    assert Path(envelope["result_path"]).name == names[0]
    record = json.loads((forge_version / names[0]).read_text(encoding="utf-8"))
    assert record["skill"] == "skf-create-stack-skill" and record["headless_decisions"] == envelope["headless_decisions"]
    assert envelope["security_result"] == record["summary"]["security_result"] == "skipped"
    # The stable copy at the stack group root is copied from the emitter's -latest record.
    (copy,) = [line for line in _fence_lines(two_b) if "{atomicWriteHelper} write" in line]
    assert copy.endswith("< {forge_version}/create-stack-skill-result-latest.json")
    assert "--target {forge_data_folder}/{stack_name}/create-stack-skill-result-latest.json" in copy


def test_a_headless_run_hands_its_line_to_the_health_check():
    """#1113: step 9 §2b binds `{result_envelope_line}` to the success line instead of displaying it, so the shared
    health check (step 10) displays it as the run's last line; an emit that fails twice binds it empty, so no line an
    earlier workflow of the session left there is shown as this run's result."""
    two_b = _sections(_body(_read(REPORT)))["2b"]
    bind = ("and prints the success line on stdout. When `{headless_mode}` is true, bind `{result_envelope_line}` ← "
            "the line and do not display it here: the shared health check displays it verbatim as the run's last "
            "line (the line the retry below prints when the first run printed none).")
    assert bind in two_b
    assert "if it fails again, print its error, bind `{result_envelope_line}` empty and continue:" in two_b
    assert two_b.index(bind) < two_b.index("bind `{result_envelope_line}` empty")
    contract = _read(CONTRACT)
    row = _slice(contract, "| **Headless** |", "\n")
    assert ("A caller reads the run's own `SKF_STACK_RESULT_JSON` line. It is the run's last line: the shared health "
            "check displays it after everything else.") in row
    result = _from(contract, "## Result Contract (Headless)")
    assert ("step 9 prints the success line on **stdout** and, when `{headless_mode}` is true, binds "
            "`{result_envelope_line}` to it instead of displaying it, so the shared health check (step 10) displays "
            "it as the run's last line:") in result
    for stale in ("displays it when `{headless_mode}` is true", "before chaining to step 10"):
        assert stale not in contract, stale
    assert "display it when `{headless_mode}` is true" not in _read(REPORT)
    relay = _read(REFS / "health-check.md")
    assert ("In a headless run report.md §2b bound `{result_envelope_line}` to the `SKF_STACK_RESULT_JSON` line "
            "without displaying it: the shared health check displays that line verbatim as the run's last line") in relay


def test_the_security_scan_outcome_reaches_the_envelope(tmp_path):
    """#902: step 8 §9 binds `{security_result}` from the branch its scan took, and step 9 stages it beside
    `quality_score` and in the contract's summary; a value outside the schema's three stops the emitter."""
    nine = _sections(_body(_read(VALIDATE)))["9"]
    binding = _slice(nine, "Bind `{security_result}`", "\n")
    assert binding == ("Bind `{security_result}` ← the helper's `security_result` (`pass`, `warn` or `skipped`), or "
                       "`skipped` when the helper is missing or printed no JSON object. Step 9 puts it in the result "
                       "envelope and the result contract.")
    # a paragraph of its own, after the helper call and the missing-helper case it names
    for part in ("uv run {securityScanHelper} run", "When no `{securityScanProbeOrder}` path exists"):
        assert nine.index(part) < nine.index(binding), part
    two_b = _sections(_body(_read(REPORT)))["2b"]
    assert "Both `security_result` fields are `{security_result}`, the scan outcome step 8 §9 bound." in two_b
    payload = json.loads(_first_fence(two_b))
    schema = _schema()
    enum = schema["properties"]["security_result"]["enum"]
    assert payload["security_result"].split("|") == enum == ["pass", "warn", "skipped"]
    assert payload["result_contract"]["summary"]["security_result"] == payload["security_result"]
    assert list(payload).index("security_result") == list(payload).index("quality_score") + 1
    assert "security_result" not in schema["required"]
    (emit,) = [line for line in _fence_lines(two_b) if "{emitEnvelopeHelper} emit " in line]
    payload.update(mode="code", security_result="passed")
    run_dir = tmp_path / "skf-create-stack-skill-run10"
    run_dir.mkdir()
    argv = _argv(emit.split(" < ")[0], "emitEnvelopeHelper",
                 {"{run_dir}": str(run_dir), "{forge_version}": str(tmp_path)})
    result = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(payload),
                            capture_output=True, text=True)
    assert result.returncode == 1 and "security_result" in result.stderr, result.stderr


def test_a_late_failure_prints_a_line_instead_of_a_dropped_warning():
    """W1 handoff: §2c runs after §1 rendered the warnings, so its failure prints a report line."""
    hook = _sections(_body(_read(REPORT)))["2c"]
    assert "workflow_warnings[]" not in hook and "print one report line" in hook
    customize = CUSTOMIZE.read_text(encoding="utf-8")
    assert "report.md §2c" in customize and "§6c" not in customize and "§6c" not in _read(STACK_SKILL)
    assert "step 9 §1 renders it" in _read(STACK_SKILL) and "step 9 §5" not in _read(STACK_SKILL)


# --- #596 (create-stack part): the override surface --------------------------------


def test_contract_settings_are_off_the_override_surface():
    import tomllib

    workflow = tomllib.loads(CUSTOMIZE.read_text(encoding="utf-8"))["workflow"]
    path_keys = {key for key in workflow if key.endswith("_path")}
    assert path_keys == {"stack_skill_template_path", "integration_patterns_path"}, path_keys
    for path in sorted(STACK.rglob("*.md")):
        for stale in ("{manifestPatternsPath}", "{provenanceMapSchemaPath}",
                      "manifest_patterns_path", "compose_mode_rules_path", "provenance_map_schema_path"):
            assert stale not in _read(path), (path.name, stale)
        if "{composeModeRulesPath}" in _read(path):
            # Steps 5 and 6 keep the name, each bound to the fixed file in its own frontmatter: no
            # override reaches it, so a team's stack_skill_template_path never drops the compose evidence.
            assert path in (COMPOSE_PAIRS, DETECT, COMPILE), path.name
            assert "composeModeRulesPath: 'references/compose-mode-rules.md'" in _frontmatter(_read(path))
    assert "## metadata.json Structure" not in _read(TEMPLATE), "the template override still swaps the contract"
    six = _sections(_body(_read(GENERATE)))["6"]
    assert "`assets/metadata-contract.md`" in six and "{stackSkillTemplatePath}" not in six
    assert "`assets/provenance-map-schema.md`" in _sections(_body(_read(GENERATE)))["7"]


# --- #1108 (create-stack part): what a house copy of the template must keep ---------


def _customize_comment(key: str) -> str:
    """The comment block right above `key = ...` in customize.toml (the lines after the last blank line)."""
    text = CUSTOMIZE.read_text(encoding="utf-8")
    return text[: text.index(f"\n{key} =")].rsplit("\n\n", 1)[-1]


def _template_top_headings() -> list[str]:
    """The template's `## ` headings outside its code fences: the structures the steps find by name."""
    found, fenced = [], False
    for line in _read(TEMPLATE).splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(line)
    return found


def test_the_template_comment_names_what_a_copy_must_keep():
    """#1108: the comment names the steps that read the template, its real default, and each heading the
    steps and skf-validate-output.py find by name; every heading it names is one the bundled template holds."""
    import tomllib

    assert tomllib.loads(CUSTOMIZE.read_text(encoding="utf-8"))["workflow"]["stack_skill_template_path"] == (
        "assets/stack-skill-template.md")
    comment = _customize_comment("stack_skill_template_path")
    flat = " ".join(line.lstrip("#").strip() for line in comment.splitlines())
    assert ("The template steps 6 (references/compile-stack.md sections 1, 2, 4 and 6), 7 "
            "(references/generate-output.md sections 3 to 5) and 8 (the body split of references/validate.md "
            "section 3) build the stack from. Default: assets/stack-skill-template.md, a path from the skill "
            "root.") in flat
    lines = {line.strip() for line in _read(TEMPLATE).splitlines()}
    named = re.findall(r"`(#{2,3} [^`]+)`", comment)
    assert named, "the comment names no heading"
    for heading in named:
        assert heading in lines, f"the template comment names `{heading}`, which the bundled template lacks"
    top = _template_top_headings()
    assert len(top) == 6, top
    for heading in top:
        assert f"`{heading}`" in comment, f"the template comment leaves out `{heading}`"
    validator = _load(VALIDATOR, "skf_validate_output_template_comment")
    for name in (validator._INTEGRATION_PATTERNS, validator._REFERENCE_INDEX, validator._PER_LIBRARY,
                 validator._CATALOG_POINTER, validator._CONVENTIONS, *validator._LIBRARY_FILE_HEADINGS,
                 *validator._PAIR_FILE_HEADINGS):
        assert f"`## {name}`" in comment, f"the template comment leaves out `## {name}`, which step 8 checks"
    assert f"`### {validator._PAIR_INTEGRATIONS}`" in comment
    assert "`### Cross-Cutting Patterns`" in comment, "Test Skill's coherence check counts it"


def test_the_integration_patterns_comment_says_what_step_5_does_with_it():
    import tomllib

    assert tomllib.loads(CUSTOMIZE.read_text(encoding="utf-8"))["workflow"]["integration_patterns_path"] == (
        "references/integration-patterns.md")
    flat = " ".join(line.lstrip("#").strip() for line in _customize_comment("integration_patterns_path").splitlines())
    for token in ("The integration types step 5 (references/detect-integrations.md section 3) classifies every pair "
                  "against, in both modes.",
                  "name a copy kept outside the skill folder as {project-root}/<path to the copy>.",
                  "step 5 writes each type name verbatim to the pair's `type` in the stack bundle"):
        assert token in flat, token
    assert "Load `{integrationPatternsPath}` for classification rules." in _sections(_body(_read(DETECT)))["3"]


# --- #600 (create-stack part): one home per rule -----------------------------------


def test_the_constituent_hash_anchor_is_stated_once():
    homes = [path.name for path in sorted(STACK.rglob("*.md")) if "The provenance anchor is the hash" in _read(path)]
    assert homes == ["compose-extract.md"], homes
    for path in sorted(STACK.rglob("*.md")):
        assert "manifest-detection" not in _read(path), path.name
    four = [line for line in _sections(_body(_read(COMPOSE_SKILLS)))["1"].splitlines()
            if line.startswith("4. **Record the constituent metadata_hash")]
    assert len(four) == 1 and "Step-07" not in four[0] and "step 7" not in four[0]
    assert "never a fresh hash" in _sections(_body(_read(GENERATE)))["7"]


def test_the_lifted_contract_keeps_skill_md_short():
    skill = _read(STACK_SKILL)
    for heading in ("## Exit Codes", "## Result Contract"):
        assert heading not in skill, heading
    assert "`references/invocation-contract.md`" in _from(skill, "## Invocation Contract")
    # #1151: 8,558 characters measured 1,996 cl100k tokens, under the 2,000-token target; the ceiling is that
    # length rounded up to 50, so a SKILL.md that grows past it is measured again.
    assert len(skill) < 8_600, len(skill)
    assert "| 1 | Initialize & Mode Detection | references/init.md | Conditional |" in skill


def test_generate_output_states_each_rule_once():
    """W2 handoff (leanness-7): no advisory labels in the frontmatter, the snippet format and helper
    internals left to their owners, the atomic-writer halt in §1's body."""
    text = _read(GENERATE)
    assert "#" not in _frontmatter(text), "generate-output's frontmatter still carries comments"
    one = _sections(_body(text))["1"]
    assert one.index("**The atomic writer.**") < one.index("stage-dir --target {skill_package}")
    assert one.index("**Prior stack.**") < one.index("**Stack version.**") \
        < one.index("**Pre-flight: ownership, phase 2.**")
    assert "phase 1" not in one, "#1152: step 1 runs phase 1"
    assert "the pre-flight below resolves it" not in one and "S11" not in one
    five = _sections(_body(text))["5"]
    assert "|IMPORTANT:" not in five and "context-snippet format of `{stackSkillTemplatePath}`" in five
    for internal in (".skf-rollback-", "flock", "ECH BLOCKER", "Workflow Rules in SKILL.md"):
        assert internal not in text, internal
    assert _from(_body(text), "**Advisory checks.**").count("never halt the run") == 1


def test_the_co_import_shape_is_the_pair_helpers():
    """W4 handoff: the schema's code-mode co_import_files is the shape skf-pair-intersect.py gives."""
    code = re.findall(r"```json\n(.*?)```", _read(SCHEMA), re.DOTALL)[0]
    assert '"co_import_files": [{"path": "{path}", "line_a": 0, "line_b": 0}]' in code
    assert "co_import_files[].file" not in _read(SCHEMA)


# --- #593, #587 (create-stack part): warnings reach the sink as text ---------------

RECORD_WARNING = ('uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" '
                  '--warning "$(cat "{run_dir}/warning.txt")"')
FILE_WRITE = "`{run_dir}/warning.txt` with a file write, never an `echo`"
# #1150: a stage after step 1 may have lost the emitter's binding, so it names the probe list it resolves from.
EMITTER_FALLBACK = "resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound"
EMITTER_PROBES = ("emitEnvelopeProbeOrder:\n"
                  "  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'\n"
                  "  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'")


def test_a_warning_reaches_the_sink_as_text(tmp_path):
    """A message can quote backticks, a Mermaid edge or `$( )`: the shell must never run it. #1150: the stage
    holds the record command and the file-write rule, and SKILL.md's contract keeps only the shape and the sink."""
    (warnings,) = [p for p in _body(_read(INIT)).split("\n\n") if p.startswith("**Warnings.**")]
    assert FILE_WRITE in warnings
    (record,) = re.findall(r"`(uv run \{emitEnvelopeHelper\} record [^`]+)`", warnings)
    assert record == RECORD_WARNING, record
    contract = _h2_section(_read(STACK_SKILL), "## Workflow state contract")
    assert "warning.txt" not in contract and "```" not in contract and "a shell runs" not in contract
    for token in ("`{run_dir}/warnings.jsonl`", "step 7 §8b", "step 9 §1 renders it",
                  "the result envelope carries it"):
        assert token in contract, token
    if sys.platform == "win32":
        return
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    message = "[step-05/warn] comention-unconfirmed: react + express: `react --> express` $(touch pwned) café"
    (run_dir / "warning.txt").write_bytes(message.encode("utf-8") + b"\n")
    command = (record.replace("uv run {emitEnvelopeHelper}", f'"{sys.executable}" "{EMITTER.as_posix()}"')
               .replace("{run_dir}", run_dir.as_posix()))
    result = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "express").exists() and not (tmp_path / "pwned").exists(), "the shell ran the message"
    (line,) = (run_dir / "warnings.jsonl").read_text(encoding="utf-8").splitlines()
    # The sink holds a JSON string, so the reports decode each line before they show it.
    assert line.startswith('"') and "\\u00e9" in line and json.loads(line) == message


@pytest.mark.parametrize("path", [p for p in STEP_FILES if p != CONTRACT], ids=lambda p: p.name)
def test_every_step_that_warns_records_in_the_sink(path):
    """Each step file shows the record command itself, so a step read on its own still records. #1150: it also
    states the file write, and after step 1 resolves a lost emitter from its own frontmatter."""
    text = _read(path)
    if "workflow_warnings[]" not in text:
        return
    assert RECORD_WARNING in text, f"{path.name} appends warnings but never shows the record command"
    assert "--warning \"[" not in text, f"{path.name} puts a message inside the shell command"
    clauses = [line for line in text.splitlines() if RECORD_WARNING in line]
    for clause in clauses:
        assert FILE_WRITE in clause, f"{path.name}: a record command with no file-write rule"
        if path != INIT:
            assert EMITTER_FALLBACK in clause, f"{path.name}: a record command with no emitter fallback"
    assert EMITTER_PROBES in _frontmatter(text), f"{path.name} declares no emitEnvelopeProbeOrder"
    assert "Workflow state contract shows" not in text, f"{path.name} defers the rule to SKILL.md"


def test_evidence_report_facts_are_recorded_warnings():
    """No step keeps a fact for the evidence report in memory: each is a warning in the sink."""
    detect, extract, pairs = _read(DETECT), _read(EXTRACT), _read(COMPOSE_PAIRS)
    for code, text in (("pair-cap-truncated", detect), ("infer-cap-truncated", pairs),
                       ("ccc-files-dropped", detect), ("ast-degraded", extract)):
        (entry,) = [e for e in WARNING_ENTRY_RE.findall(text) if f'`code: "{code}"`' in e]
        assert re.search(r'`severity: "(info|warn|error)"`', entry), entry
    for stale in ("in context for the evidence report", "in workflow state for the evidence report",
                  "record the cap in the evidence report", "record the cap as §1 does"):
        assert stale not in detect + extract + pairs, stale
    eight_b = _sections(_body(_read(GENERATE)))["8b"]
    assert "each line of `{run_dir}/warnings.jsonl` decoded as the JSON string it holds" in eight_b
    assert "as its `gate`, `taken_action` and `reason`" in eight_b
    assert "decoded as the JSON string it holds" in _sections(_body(_read(REPORT)))["1"]


def test_the_import_counts_live_in_the_run_folder():
    """Step 3 saves its counts in the run folder; steps 4, 5 and 7 name the same file."""
    for path in (RANK, EXTRACT, DETECT, GENERATE):
        assert "importCountsFile: '{run_dir}/import-counts.json'" in _frontmatter(_read(path)), path.name
    for path in sorted(STACK.rglob("*.md")):
        text = _read(path)
        assert "{import_counts}" not in text and "temp file under `{forge_data_folder}/`" not in text, path.name
    assert "`{importCountsFile}`" in _sections(_body(_read(EXTRACT)))["2"]
    nine = _sections(_body(_read(GENERATE)))["9"]
    assert '"{importCountsFile}"' in nine


def test_the_group_root_copy_skips_a_stale_latest_record():
    two_b = _sections(_body(_read(REPORT)))["2b"]
    skip = _from(two_b, "Skip the copy").split("\n\n")[0]
    assert "`result_file_write_failed`" in skip and "`create-stack-skill-result-latest.json`" in skip
    assert "the emitter printed no line" in skip and "If the copy is skipped or fails, print" in skip
    assert "`stack_libraries` the committed `metadata.json`'s `libraries`" in two_b


def test_the_metadata_contract_names_the_markers_the_inventory_reads(tmp_path):
    """The contract's ownership markers are the ones skf-skill-inventory.py checks, spec_version not among them."""
    contract = _read(METADATA_CONTRACT)
    assert contract.endswith("\n") and not contract.endswith("\n\n"), "a blank line at the end of the file"
    claim = [p for p in contract.split("\n\n") if "ownership check reads" in p]
    assert len(claim) == 1 and "`spec_version`" not in claim[0]
    assert "`generated_by`, `tool_versions.skf`, and `skill_type` with `forge_tier` or `confidence_tier`" in claim[0]
    inventory = _load(INVENTORY, "skf_skill_inventory_markers")
    metadata = json.loads(_first_fence(contract).replace('"{number-or-omitted-if-no-ast}"', "0"))
    cases = {
        "contract": (metadata, True),
        "generated_by": ({"generated_by": "create-stack-skill"}, True),
        "tool_versions.skf": ({"tool_versions": {"skf": "3.0.0"}}, True),
        "skill_type+forge_tier": ({"skill_type": "stack", "forge_tier": "Forge"}, True),
        "skill_type+confidence_tier": ({"skill_type": "stack", "confidence_tier": "T1"}, True),
        "skill_type alone": ({"skill_type": "stack"}, False),
        "spec_version alone": ({"spec_version": "1.3"}, False),
    }
    for k, (name, (data, owned)) in enumerate(cases.items()):
        path = tmp_path / f"metadata-{k}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert inventory._has_skf_metadata(path) is owned, name


def test_the_contract_pointers_are_current():
    three = _sections(_body(_read(INIT)))["3"]
    assert "(`references/invocation-contract.md` lists them; `stack_name` is bound in §0)" in three
    assert "SKILL.md's Invocation Contract lists them" not in _read(INIT)
    result = _from(_read(CONTRACT), "## Result Contract (Headless)")
    assert "except the `init:emitter` halt, which has no emitter to print one" in result
    assert "(the `init:emitter` halt, with no emitter, only displays its message)" in _read(STACK_SKILL)
    description = _schema()["description"]
    assert "lists each halt with its step; each halting step file shows the emit-halt command" in description


# --- #1109 (create-stack part): the hook gets the -latest record, or is skipped ----


def test_the_hook_gets_the_latest_record_and_is_skipped_without_one():
    """#1109: §2c passes the `-latest` record §2b wrote, quoted and from the project root, and skips the hook
    with one report line when the emitter wrote no line, no `-latest` record or no per-run record, so the hook
    never reads a missing file or an earlier forge's record. A missing atomic writer or a failed group-root
    copy leaves the version folder's `-latest` record in place, so neither skips it. The comment shows the
    same call."""
    two_c = _sections(_body(_read(REPORT)))["2c"]
    assert "invoke it now from `{project-root}`, after §2b and before chaining to health-check" in two_c
    assert ('```bash\n{onCompleteCommand} --result-path="{forge_version}/create-stack-skill-result-latest.json"\n'
            '```') in two_c
    skip = _from(two_c, "Skip it when").split("\n\n")[0]
    for token in ("Skip it when the emitter printed no line, a `result_file_write_failed` warning names "
                  "`create-stack-skill-result-latest.json` or `{forge_version}` itself, or the line's `result_path` "
                  "is null",
                  '"on_complete skipped: no result contract was written ({reason})"',
                  "the hook never gets a missing file or an earlier forge's record"):
        assert token in skip, token
    assert "group-root" not in skip, skip
    assert two_c.index("Skip it when") < two_c.index("Run it with a bounded timeout (default 60s)")
    assert "The hook runs even when" not in _read(REPORT)
    assert "**The hook must never fail the workflow**" in two_c
    comment = " ".join(line.lstrip("#").strip() for line in _customize_comment("on_complete").splitlines())
    for token in ("a shell command, not an instruction", "runs it from {project-root}",
                  '<on_complete> --result-path="<{forge_version}/create-stack-skill-result-latest.json>"',
                  "It is skipped, with a report line saying so, when the emitter wrote no result file or not that "
                  "-latest copy"):
        assert token in comment, token


# --- #1150: each stage carries its rules, step 1 saves its bindings, resume at the review gate --------

# Phrases SKILL.md no longer holds: the fallback said four times, its own design note, the `references/` note,
# the Workflow Rules' pointer at the contract and the trace rule the Overview already states.
SKILL_GONE = ("so stage files don't have to repeat", "empty-string overrides fall through", "if non-empty, else",
              "Stash both paths", "carved out of SKILL.md", "Warnings use a single accumulator", "Zero hallucination")
BINDING_LEAD = ("   Bind these three as workflow-context variables, taking the default when the merged value is "
                "empty or absent:")
BOUND = (("stackSkillTemplatePath", "stack_skill_template_path"),
         ("integrationPatternsPath", "integration_patterns_path"),
         ("onCompleteCommand", "on_complete"))
# A maintainer's ticket tag, (B2) or (S7, 20); a Markdown header level such as "H1/H2 header" is none.
TICKET_TAG_RE = re.compile(r"\b[BSHM]\d{1,2}\b")
HEADER_LEVEL_RE = re.compile(r"\bH[1-6](?:/H[1-6])? (?:header|structure)\b")
RUN_KEYS = ["stack_name", "headless_mode", "project_root", "scan_root", "compose_mode", "architecture_doc_path",
            "explicit_deps", "scope_overrides", "prior_active_version", "prior_stack_version", "prior_libraries",
            "stackSkillTemplatePath", "integrationPatternsPath", "onCompleteCommand", "forge_tier", "detected_tier",
            "available_tools"]
RUN_WRITE = 'uv run {atomicWriteHelper} write --target "{runFile}" < "{run_dir}/run-bindings.json"'
ATOMIC_WRITER = SCRIPTS / "skf-atomic-write.py"


def test_skill_md_states_each_rule_once():
    """leanness-2: the three bindings in Quick Skill's shape, one lead and one bullet each, and no rule twice."""
    skill = _read(STACK_SKILL)
    for gone in SKILL_GONE:
        assert gone not in skill, gone
    lines = skill.splitlines()
    (lead,) = [k for k, line in enumerate(lines) if line == BINDING_LEAD]
    assert lines[lead + 1] == "" and lines[lead + 5] == "", "the lead, a blank line, three bullets, a blank line"
    for line, (variable, key) in zip(lines[lead + 2: lead + 5], BOUND):
        assert line.startswith(f"   - `{{{variable}}}` ← `workflow.{key}`, else "), line
    assert "Every finding must trace to its source with file:line citations." in _h2_section(skill, "## Overview")
    # The trace rule as a word: a later rule may say "traceback" or "tracing".
    assert not re.search(r"\btrace\b", _h2_section(skill, "## Workflow Rules"))
    (headless,) = [line for line in lines if line.startswith("2. **Resolve `{headless_mode}`**")]
    # A `-H=false` turns nothing on: it falls through to the preferences, as before the rules became one sentence.
    rules = ["`false` when `--headless=false` or `--no-headless`",
             "`true` when `--headless` or `-H` was passed without `=false`",
             "otherwise `headless_mode` from `{sidecar_path}/preferences.yaml`", "otherwise `false`."]
    positions = [headless.index(rule) for rule in rules]
    assert positions == sorted(positions), "the four rules in their order of precedence"


def test_no_stage_keeps_a_ticket_tag():
    """leanness-8: a tag such as (B8) or (S13) names a maintainer's ticket and tells the model nothing."""
    for path in [STACK_SKILL, *STEP_FILES]:
        tags = TICKET_TAG_RE.findall(HEADER_LEVEL_RE.sub("", _read(path)))
        assert not tags, f"{path.name}: {tags}"
    three = _sections(_body(_read(INIT)))["3"]
    assert "as B8 does" not in three
    assert "record the auto-decision as the compose-suggestion gate above does" in three


def test_step_1_saves_its_bindings_to_run_json(tmp_path):
    """enhancement-5: step 1's bindings, the tier after its downgrade among them, go to `run.json` with the
    atomic writer, and a missing writer or a failed write halts there."""
    init = _read(INIT)
    assert "runFile: '{run_dir}/run.json'" in _frontmatter(init)
    assert _probe_script(init, "atomicWrite") == ATOMIC_WRITER
    sections = _sections(_body(init))
    assert list(sections)[-3:] == ["4", "5", "6"] and "{nextStepFile}" in sections["6"]
    five = sections["5"]
    assert five.startswith("### 5. Save the Run's Bindings")
    bindings = json.loads(_first_fence(five))
    assert list(bindings) == RUN_KEYS
    for token in ("`{run_dir}/run-bindings.json` with a file write", "keyed by each binding's own name",
                  "an input not given being `null`", "`forge_tier` is the run tier, after §1's override and §2's "
                  "downgrade", "`detected_tier` is the one `forge-tier.yaml` names",
                  # #1152: step 3 and step 7 read the published stack step 1 found, a resumed run restores it.
                  "the three `prior_` keys are §0's, `null` on a new stack",
                  "with `prior_libraries` the published `libraries` list"):
        assert token in five, token
    assert [bindings[key] for key in RUN_KEYS if key.startswith("prior_")] == [None, None, None]
    assert RUN_WRITE in _fence_lines(five)
    assert _halts(five) == [(3, "helper-missing", "init:run-state"), (4, "write-failure", "init:run-state")]
    (row,) = [line for line in _read(CONTRACT).splitlines() if line.startswith("| 3 ")]
    assert "`skf-atomic-write.py` (step 1 §5, step 7 §1)" in row
    # The documented call, run with the real writer, leaves the staged object in run.json.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run-bindings.json").write_bytes(json.dumps(bindings).encode("utf-8"))
    argv = _argv(RUN_WRITE.split(" < ")[0], "atomicWriteHelper", {"{runFile}": str(run_dir / "run.json")})
    with open(run_dir / "run-bindings.json", "rb") as staged:
        result = subprocess.run([sys.executable, str(ATOMIC_WRITER), *argv], stdin=staged, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((run_dir / "run.json").read_bytes().decode("utf-8")) == bindings


def test_an_interactive_run_offers_to_resume_at_the_review_gate():
    """enhancement-5: an interactive run finds an interrupted run of the same stack that holds a draft, and
    resumes at step 6's review or starts fresh; a headless run never looks."""
    sections = _sections(_body(_read(INIT)))
    keys = list(sections)
    assert keys.index("0") + 1 == keys.index("0b") == keys.index("1") - 1, "the offer follows §0's stack name"
    offer = sections["0b"]
    assert offer.startswith("### 0b. Offer to Resume at the Review Gate")
    for token in ("Only an interactive run looks for an earlier run: a headless run always starts fresh.",
                  "`{project-root}/_bmad-output/.skf-run/skf-create-stack-skill-*/run.json`",
                  "whose `run.json` parses", "names this `{stack_name}`", "holds `headless_mode` false",
                  "With none, go on to §1.",
                  "the one whose `draft/SKILL.md` changed last", "(last changed: {that file's modification time})"):
        assert token in offer, token
    # A run that finished the stack since replaced that draft, so a declined or abandoned one is not offered
    # again once the stack's group-root result copy (step 9) is newer than it.
    assert ("that holds a `draft/SKILL.md` changed after "
            "`{forge_data_folder}/{stack_name}/create-stack-skill-result-latest.json` was written, "
            "when that file exists") in offer
    options = [line.strip().rstrip('"') for line in offer.splitlines() if re.match(r"\s+\[[YN]\] ", line)]
    assert options == ["[Y] Resume at the review of that draft",
                       "[N] Start fresh (that run folder stays as it is: {its path})"]
    (yes,) = [line for line in offer.splitlines() if line.startswith("- **[Y]:**")]
    for token in ("delete this run's new folder, the one the pre-flight created",
                  "bind `{run_dir}` to the found folder", "restore every binding its `run.json` holds",
                  "Set `{resumed_at_review}` true", "when On Activation bound `{customization_resolver_unavailable}`, "
                  "record it in that folder as the resolver warning above does",
                  "execute `references/compile-stack.md`"):
        assert token in yes, token
    (no,) = [line for line in offer.splitlines() if line.startswith("- **[N]:**")]
    assert "leave the found folder as it is and go on to §1" in no
    # No gate a headless run reaches: nothing to record, and the contract says so.
    assert "GATE [default:" not in offer and "--decision" not in offer
    assert "step 1: the resume offer [Y]/[N] (interactive only; a headless run always starts fresh)" in \
        _contract_row("Gates")


def test_a_resumed_run_goes_to_the_review_of_its_draft():
    body = _body(_read(COMPILE))
    (resumed,) = [p for p in body.split("\n\n") if p.startswith("**A resumed run.**")]
    assert body.index("**Halt envelope.**") < body.index("**A resumed run.**") < body.index("### 1.")
    for token in ("(`{resumed_at_review}` true)", "run §1's counts call", "go to §7's display and §8's menu",
                  "the draft in `{draftFolder}` stays as the interrupted run left it, the user's own edits included",
                  # §7's display and step 7's copy both follow §4's catalog decision, which the resume skips.
                  "§4 moved the catalog out when `{draftFolder}/stack-catalog.md` exists"):
        assert token in resumed, token


def test_steps_7_and_8_take_the_run_tier_from_run_json():
    """architecture-2, enhancement-5: a step that lost `{forge_tier}` to compaction reads step 1's saved tier."""
    for path in (MANIFESTS, GENERATE, VALIDATE):
        assert "runFile: '{run_dir}/run.json'" in _frontmatter(_read(path)), path.name
    assert "`forge_tier` ← the `forge_tier` of `{runFile}`" in _sections(_body(_read(GENERATE)))["6"]
    one = _sections(_body(_read(VALIDATE)))["1"]
    assert one.index("--forge-tier {forge_tier}") < one.index("`{forge_tier}` is the `forge_tier` of `{runFile}`")
    for path in STEP_FILES:
        assert "step 1's run tier" not in _read(path), path.name


def test_step_2_saves_a_binding_it_changes():
    """enhancement-5: the no-manifests answer rebinds `explicit_deps` or `{scan_root}`, so run.json follows it."""
    text = _read(MANIFESTS)
    assert _probe_script(text, "atomicWrite") == ATOMIC_WRITER
    two = _sections(_body(text))["2"]
    options = _from(two, "STOP and wait").split("\n\n")[0]
    assert "Option 1 binds `explicit_deps` to the names the user gives" in options
    # Option 1's own sentences save the list before they go on to §3.
    one = options[options.index("Option 1 binds"): options.index("Option 2 sets")]
    assert one.index("saves `explicit_deps` as **Save the new binding** below shows") \
        < one.index("goes on to [Display Detection Summary](#3-display-detection-summary)")
    save = _from(two, "**Save the new binding.**")
    save = save[:save.index("When `manifests` is not empty")]
    for token in ("When option 1 binds `explicit_deps` or option 2 sets `{scan_root}`", "read `{runFile}`",
                  "stage the whole object as `{run_dir}/run-bindings.json` with a file write",
                  "resolving `{atomicWriteHelper}` from `{atomicWriteProbeOrder}` if it is not bound"):
        assert token in save, token
    assert RUN_WRITE in _fence_lines(save)
    assert _halts(save) == [(4, "write-failure", "detect-manifests:run-state")]
    # The message names the binding the answer changed; nothing binds a `{binding}`.
    assert "{binding}" not in save
    assert "The new `explicit_deps` could not be saved to `{runFile}`" in save
    assert "naming `scan_root` in place of `explicit_deps` after option 2" in save
    (row,) = [line for line in _read(CONTRACT).splitlines() if line.startswith("| 4 ")]
    assert "step 1 §5 and step 2 §2: `run.json` cannot be written" in row


# --- #1151: a compose run reads its own stage files; one home per integration rule ---

NEXT_STEP_RE = re.compile(r"^(nextStepFile|composeNextStepFile): '([^']+)'$", re.MULTILINE)
# The guard each shared stage opens §1 with, sending a compose run past the code-mode passes.
RANK_GUARD = ("**If `compose_mode` is true:** `references/compose-scope.md` set `confirmed_dependencies` and showed "
              "the skills table. Skip to [Confirm the Scope](#3-confirm-the-scope).")
DETECT_GUARD = ("**If `compose_mode` is true:** `references/compose-pairs.md` found the pairs and wrote them to "
                "`{bundleFile}`'s `integrations[]`. Skip to [Classify Integration Types](#3-classify-integration-types).")
STAGES_ROWS = (
    "| 2 | Detect Manifests | references/detect-manifests.md; compose: references/compose-skills.md | Conditional "
    "(no manifest found) |",
    "| 3 | Rank & Confirm Libraries | references/rank-and-confirm.md; compose: references/compose-scope.md first | No "
    "(confirm) |",
    "| 4 | Parallel Extract | references/parallel-extract.md; compose: references/compose-extract.md | Yes |",
    "| 5 | Detect Integrations | references/detect-integrations.md; compose: references/compose-pairs.md first | Yes |",
)
COMPOSE_RULE_SECTIONS = ["## Confidence Tier Inheritance", "## Integration Evidence Format",
                         "## Feasibility Report Integration"]
# What step 4's subagent returns for one constituent, and nothing else (enhancement-4).
CONSTITUENT_FIELDS = {"library", "description_keywords", "usage_patterns", "signatures"}
# Prose that loads a constituent's SKILL.md into the parent, as step 4 §0 did before #1151.
PARENT_LOAD_RE = re.compile(r"load SKILL\.md from|SKILL\.md` loaded|loaded above|its SKILL\.md `description` names",
                            re.IGNORECASE)


# Compose mode named in prose or as the flag (compose mode, compose-mode, compose_mode), not the `composes` field.
COMPOSE_MODE_RE = re.compile(r"compose[-_ ]mode", re.IGNORECASE)


def _next_steps(path: Path) -> dict[str, str]:
    return dict(NEXT_STEP_RE.findall(_frontmatter(_read(path))))


def _chain(compose: bool) -> list[str]:
    """The stage files a run loads from step 1 to step 6, by the frontmatter each stage routes with."""
    names, path = [], INIT
    while path != COMPILE:
        assert path.name not in names, f"the routing loops back to {path.name}"
        steps = _next_steps(path)
        names.append(path.name)
        path = REFS / (steps.get("composeNextStepFile", steps["nextStepFile"]) if compose
                       else steps["nextStepFile"])
    return names + [COMPILE.name]


def test_a_compose_run_reads_its_own_stage_files():
    """architecture-6: init.md and rank-and-confirm.md route a compose run by `composeNextStepFile`, each compose
    file names its successor, and the scope gate and the pair classification stay each mode's one home."""
    assert _next_steps(INIT) == {"nextStepFile": "detect-manifests.md", "composeNextStepFile": "compose-skills.md"}
    assert _next_steps(RANK) == {"nextStepFile": "parallel-extract.md", "composeNextStepFile": "compose-extract.md"}
    for path, successor in ((COMPOSE_SKILLS, "compose-scope.md"), (COMPOSE_SCOPE, "rank-and-confirm.md"),
                            (COMPOSE_EXTRACT, "compose-pairs.md"), (COMPOSE_PAIRS, "detect-integrations.md")):
        assert _next_steps(path) == {"nextStepFile": successor}, path.name
    assert _chain(compose=False) == ["init.md", "detect-manifests.md", "rank-and-confirm.md", "parallel-extract.md",
                                     "detect-integrations.md", "compile-stack.md"]
    assert _chain(compose=True) == ["init.md", "compose-skills.md", "compose-scope.md", "rank-and-confirm.md",
                                    "compose-extract.md", "compose-pairs.md", "detect-integrations.md",
                                    "compile-stack.md"]
    six = _sections(_body(_read(INIT)))["6"]
    assert ("Load, read the full file and then execute `{composeNextStepFile}` when `compose_mode` is true, else "
            "`{nextStepFile}`.") in six
    (proceed,) = [line for line in _sections(_body(_read(RANK)))["3"].splitlines() if line.startswith("- IF C:")]
    assert proceed.endswith("then execute `{composeNextStepFile}` when `compose_mode` is true, else {nextStepFile}")
    # A headless compose run takes the same gate, records it, and goes on by the same line.
    (gate,) = [line for line in _sections(_body(_read(RANK)))["3"].splitlines() if line.startswith("- **GATE")]
    assert "every skill in compose mode" in gate and '"gate": "rank-and-confirm.scope"' in gate
    # One guard opens §1 of each shared stage, and no `**If not compose_mode:**` header follows it.
    for path, guard, anchor in ((RANK, RANK_GUARD, "3-confirm-the-scope"),
                                (DETECT, DETECT_GUARD, "3-classify-integration-types")):
        text = _read(path)
        one = _sections(_body(text))["1"]
        assert one.split("\n\n")[1] == guard, path.name
        assert text.count("compose_mode` is true:**") == 1 and "If not compose_mode" not in text, path.name
        assert anchor in {_slug(f"{m.group(1)}. {m.group(2)}") for m in SECTION_HEADING_RE.finditer(text)}
    for path in STEP_FILES:
        assert "**If not compose_mode:**" not in _read(path), path.name
    # The code stages name no compose branch, and keep the section numbers every "step N §M" pointer names.
    for path, numbers in ((MANIFESTS, ["1", "2", "3", "4"]), (EXTRACT, ["1", "2", "3", "3a", "4", "5"])):
        text = _read(path)
        assert not COMPOSE_MODE_RE.search(text), f"{path.name} still names compose mode"
        assert list(_sections(_body(text))) == numbers, path.name
    # The Stages table names both chains.
    skill = _read(STACK_SKILL)
    for row in STAGES_ROWS:
        assert row in skill, row


def test_detect_integrations_fits_its_budget():
    """architecture-6: a stage that keeps a compose guard stays under the 4,500-token budget of a multi-branch
    file. #1151: 11,910 characters measured 2,941 cl100k tokens; the ceiling is that length rounded up to 50, so
    a detect-integrations.md that grows past it is measured again."""
    text = _read(DETECT)
    assert len(text) < 11_950, len(text)
    goal = _slice(text, "## STEP GOAL:\n", "\n## Rules")
    assert ("Find the library pairs whose co-imports show where and how they connect in this codebase, classify every "
            "pair, compose mode's included, and build the integration graph.") in goal
    for gone in ("comentionProbeOrder", "validateFeasibilityReportProbeOrder", "{comentionHelper}",
                 "{validateFeasibilityReportHelper}", "`docs-mention`", "- `architecture-co-mention`:"):
        assert gone not in text, gone
    assert "composeModeRulesPath: 'references/compose-mode-rules.md'" in _frontmatter(text)


def test_a_code_run_loads_no_compose_rule():
    """A code-mode run reads `{composeModeRulesPath}` only where a sentence says compose mode does."""
    for path in (DETECT, COMPILE):
        for paragraph in _body(_read(path)).split("\n\n"):
            for sentence in re.split(r"(?<=[.;])\s", paragraph):
                if "{composeModeRulesPath}" in sentence:
                    assert "compose" in sentence.replace("{composeModeRulesPath}", ""), (path.name, sentence)


def test_compose_mode_rules_keep_three_sections():
    """leanness-1, customization-4: the rules keep the labels, the evidence format and the [VS] lines; the type
    line names the resolved integration patterns, and the step that assigns it."""
    text = _read(COMPOSE_RULES)
    assert [line for line in text.splitlines() if line.startswith("## ")] == COMPOSE_RULE_SECTIONS
    for gone in ("## Skill Loading", "## Compose-mode Co-mention Precision", "## Architecture Integration Mapping",
                 "## Inferred Integrations", "\u2014"):
        assert gone not in text, gone
    assert ("The labels and the evidence format of a compose-mode integration: step 5 "
            "(`references/compose-pairs.md`) builds each pair's evidence in this format, and step 6 renders it.") in text
    block = _first_fence(_h2_section(text, "## Integration Evidence Format"))
    assert "**Type:** {the pair's type, assigned in step 5 §3 from {integrationPatternsPath}}" in block
    assert "integration-patterns.md" not in text
    assert "step 4 (`references/compose-extract.md`) takes from the constituent's `evidence_tier`" in text
    assert "Step 5 (`references/compose-pairs.md` §2) reads the [VS] report" in text


def test_each_constituent_is_read_by_its_own_subagent():
    """enhancement-4: one foreground subagent per constituent returns only its description keywords, usage
    patterns and signatures; a failed read leaves them empty with a warning; step 5 reads them from the bundle."""
    text = _read(COMPOSE_EXTRACT)
    assert "- Keep each constituent's SKILL.md out of this context: its subagent (§2) returns only the fields §3 " \
        "writes" in _rules(text)
    sections = _sections(_body(text))
    assert list(sections) == ["1", "2", "3", "4", "5"]
    two = sections["2"]
    returned = json.loads(_first_fence(two))
    assert set(returned) == CONSTITUENT_FIELDS, returned
    assert "(<the file:line it cites>)" in returned["usage_patterns"][0]
    assert list(returned["signatures"]) == ["<listed export>"]
    for token in ("launch one per confirmed skill, at most five in one message, each with `run_in_background: "
                  "false`, and wait for every one before you launch more",
                  "Tell each to stop and return what it has after about 20 tool calls",
                  "With no subagent support, read them one at a time here and keep only the fields below",
                  "the export names its `{stackInventoryFile}` entry lists",
                  "its `references/` for a listed export whose signature `SKILL.md` does not give"):
        assert token in two, token
    (failed,) = [e for e in WARNING_ENTRY_RE.findall(two) if 'code: "constituent-read-failed"' in e]
    assert '`step: "step-04"`' in failed and '`severity: "warn"`' in failed
    assert "`description_keywords` and `usage_patterns` are `[]` and its `signatures` `{}`" in two
    assert "Its exports still come from §1." in two
    (written,) = [line for line in sections["3"].splitlines() if line.startswith("- `description_keywords`")]
    assert "what §2 returned for it" in written
    assert "`constituent-read-failed`" in sections["4"]
    # No stage loads a constituent's SKILL.md into the parent, or reads its keywords from that body.
    for path in STEP_FILES:
        found = PARENT_LOAD_RE.search(_read(path))
        assert not found, f"{path.name}: {found.group(0)!r}"
    # Step 5 builds the signatures and the infer keywords from the bundle fields.
    pairs = _read(COMPOSE_PAIRS)
    assert "bundleFile: '{run_dir}/extraction-bundle.json'" in _frontmatter(pairs)
    (item,) = [line for line in _sections(_body(pairs))["1"].splitlines() if line.startswith("6. ")]
    for token in ("the signature from that skill's `signatures` in `{bundleFile}` for an export the pair rests on",
                  "else that export's name from its `exports`"):
        assert token in item, token
    infer = _from(_body(pairs), "**No architecture document.**")
    assert "Its `keywords` are its bundle entry's `description_keywords`" in infer
    assert "under `skill_package_path`, which the helper reads" in infer
    # A pair kept with no architecture document cites the bundle too, with its own reference line.
    assert ("For each kept pair, write one `[from skill: <skill>] <signature>` line per skill from `{bundleFile}`, "
            "as item 6 says") in infer
    assert "`**Contract reference:**`" in infer and "`**Shared domain:**`" in infer


def test_the_compose_halts_name_their_stage():
    """Each halt a compose stage raises names that file in its phase, with the code and reason it kept."""
    assert _halts(_body(_read(COMPOSE_SKILLS))) == [
        (3, "helper-missing", "compose-skills:enumerate"), (3, "resolution-failure", "compose-skills:stale-manifest"),
        (3, "resolution-failure", "compose-skills:no-skills")]
    assert sorted(_halts(_body(_read(COMPOSE_EXTRACT)))) == [
        (3, "helper-missing", "compose-extract:enumerate"), (3, "resolution-failure", "compose-extract:constituent-gone"),
        (3, "resolution-failure", "compose-extract:cycle")]
    assert _halts(_body(_read(COMPOSE_PAIRS))) == [
        (3, "helper-missing", "compose-pairs:comention"), (2, "schema-version-mismatch", "compose-pairs:vs-report"),
        (2, "unknown-verdict-token", "compose-pairs:vs-report")]
    # #1153: compose-scope.md takes the scope from the import counter, so a missing one halts there.
    assert _halts(_body(_read(COMPOSE_SCOPE))) == [(3, "helper-missing", "compose-scope:scope")]
    for path in (COMPOSE_SKILLS, COMPOSE_SCOPE, COMPOSE_EXTRACT, COMPOSE_PAIRS):
        assert '"mode": "compose"' in _from(_body(_read(path)), "**Halt envelope.**").split("###", 1)[0], path.name
    # The schema's example phase is one a step still raises.
    schema = ENVELOPE_SCHEMA.read_text(encoding="utf-8")
    assert "for example 'detect-manifests:scan'." in schema and "detect-manifests:enumerate" not in schema


def test_compose_pairs_write_their_entries_for_step_5_section_3():
    """architecture-6: compose-pairs.md writes each kept pair with its qualifier and evidence, and step 5 §3 and §4
    complete the entry, so the hand-over crosses the file load on disk."""
    sections = _sections(_body(_read(COMPOSE_PAIRS)))
    three = sections["3"]
    assert three.startswith("### 3. Write the Kept Pairs\n\nSet `{bundleFile}`'s `integrations[]` to one entry per "
                            "kept pair, so `references/detect-integrations.md` §3 reads them from disk:")
    entry = json.loads(_first_fence(three))
    assert list(entry) == ["a", "b", "qualifier", "detection_method", "evidence", "reference", "vs"]
    mappings = dict(re.findall(r"^- `([a-z-]+)`: .*Maps to `detection_method: ([a-z_]+)`", three, re.MULTILINE))
    assert mappings == {"architecture-co-mention": "architecture_co_mention",
                        "constituent-documented-contract": "constituent_documented_contract",
                        "inferred-shared-domain": "inferred_from_shared_domain"}, mappings
    schema = _read(SCHEMA)
    for method in mappings.values():
        assert f'"{method}"' in schema, method
    assert "With no pair kept, `integrations[]` stays empty." in three
    assert sections["4"].rstrip().endswith("its §1 sends a compose run to §3, which classifies these pairs.")
    # Step 5 §3 classifies and tiers those pairs, keeping what compose-pairs.md wrote.
    detect = _sections(_body(_read(DETECT)))
    assert "  - A compose-mode pair keeps the `qualifier` and `detection_method` `references/compose-pairs.md` " \
        "wrote." in detect["3"]
    assert "When at least one pair qualifies, run it once on all of them" in detect["3"]
    assert "a compose-mode pair has none, so its `key_files` is `[]`" in detect["3"]
    assert "If none were detected, report that the libraries appear to operate independently" in detect["5"]


def test_compile_states_the_integration_layer_as_one_goal():
    """leanness-6, customization-4: §3 fills the template's Integration Patterns as one goal, a compose pair from
    its entry's type, and §7 invites edits instead of asking fixed questions."""
    sections = _sections(_body(_read(COMPILE)))
    three = sections["3"]
    assert "Compile in order" not in three and not re.search(r"^\s*- ", three, re.MULTILINE), three
    paragraphs = [p for p in three.split("\n\n")[1:] if p.strip()]
    assert [p.split(":", 1)[0] for p in paragraphs][:1] == ["**Zero-integration guard"]
    (goal,) = paragraphs[1:]
    for token in ("Otherwise fill the template's Integration Patterns section from `{bundleFile}`",
                  "Cross-Cutting Patterns from `cross_cutting` when it lists any",
                  "one Library Pair Integrations entry per `integrations[]` entry",
                  "with file:line citations and its key files from `key_files`",
                  "from its entry's `type`, `evidence`, `reference`, `tier` and `qualifier`",
                  "After the pairs, a Hub Library Connections list gives each hub library (`hubs`, 3+ partners)"):
        assert token in goal, token
    seven = sections["7"]
    assert seven.rstrip().endswith("Edit the draft yourself, or tell me what to change before the stack is written.\"")
    assert "?" not in seven and "**Please review the integration layer" not in seven


# --- #1152: the scope gate stops an empty scope and marks a rerun against the published stack ---


def _scope_gate() -> str:
    return _sections(_body(_read(RANK)))["3"]


def _paragraph(text: str, start: str) -> str:
    (found,) = [p for p in text.split("\n\n") if p.startswith(start)]
    return found


def test_an_empty_scope_offers_no_continue():
    """enhancement-1: §3 checks the scope before the gate and after each change; an interactive run gets no [C],
    a headless one halts `empty-scope` (exit 2) before it records a scope decision, in both modes."""
    three = _scope_gate()
    empty = _paragraph(three, "**Empty scope.**")
    assert three.index("**Empty scope.**") < three.index("**Select:**") < three.index("- **GATE")
    for token in ("before presenting the gate and after each scope change", "the gate offers no [C]",
                  '"**No library is in scope.**"',
                  # The interactive view lists what the headless halt lists: every library left out (#1153: the
                  # helper's `dropped[]`, in both modes).
                  "shows each library left out with its reason (the Left out table: `{scopeFile}`'s `dropped[]`, "
                  "then each library the user took out)",
                  "takes only names to add, a custom list or [X]", "a headless run records no scope decision",
                  "{each library left out, with its reason}",
                  "Pass `scope_overrides` with `<name>: include` for each library the stack should cover"):
        assert token in empty, token
    assert _halts(empty) == [(2, "empty-scope", "rank-and-confirm:scope")]
    assert three.index("HALTs (exit 2") < three.index(RECORD_DECISION), "the halt comes before the record"
    # One Select line, which itself says [C] is not offered while the scope is empty.
    (select,) = [line for line in three.splitlines() if "**Select:**" in line]
    assert "**Select:** [C] Continue to extraction with this scope (not offered while the scope is empty) | [X]" \
        in select
    (gate,) = [line for line in three.splitlines() if line.startswith("- **GATE")]
    assert "(an empty scope has halted above)" in gate
    menu = _from(three, "#### Menu Handling Logic:")
    (take_c,) = [line for line in menu.splitlines() if line.startswith("- IF C:")]
    assert take_c.startswith("- IF C: While `confirmed_dependencies` is empty, refuse it")
    assert take_c.index("show the gate again") < take_c.index("Otherwise display \"**Scope confirmed:**")
    (other,) = [line for line in menu.splitlines() if line.startswith("- IF Any other:")]
    assert "check the scope again as **Empty scope** says" in other
    (row,) = [line for line in _read(CONTRACT).splitlines() if line.startswith("| 2 ")]
    assert "step 3 §3 headless with no library in scope (`empty-scope`)" in row
    assert "step 3: scope gate [C] (no [C] while the scope is empty; headless: HALT `empty-scope`, exit 2)" \
        in _contract_row("Gates")
    schema = _schema()
    assert _exit_codes()["empty-scope"] == 2 and "empty-scope" in schema["properties"]["halt_reason"]["enum"]
    assert "no-manifests, empty-scope, all-extractions-failed" in schema["properties"]["exit_code"]["description"]


@pytest.mark.parametrize("mode", ["code", "compose"])
def test_an_empty_scope_halt_emits_exit_2(mode, tmp_path):
    """The halt staged from rank-and-confirm's own envelope exits 2, records no decision and fits the schema."""
    from jsonschema import Draft202012Validator

    staged = re.search(r'`(\{"phase": "<phase>".*?\})`', _from(_body(_read(RANK)), "**Halt envelope.**")).group(1)
    payload = _payload(staged.replace("<phase>", "rank-and-confirm:scope").replace("<halt_reason>", "empty-scope")
                       .replace("<code|compose>", mode))
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-create-stack-skill-ef56ab78"
    run_dir.mkdir(parents=True)
    (run_dir / "halt.json").write_text(json.dumps(payload), encoding="utf-8")
    argv = _argv(HALT_COMMAND.split(" < ")[0], "emitEnvelopeHelper", {"{run_dir}": str(run_dir)})
    result = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(payload),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (line,) = result.stderr.splitlines()
    envelope = json.loads(line.removeprefix("SKF_STACK_RESULT_JSON: "))
    assert not list(Draft202012Validator(_schema()).iter_errors(envelope))
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("error", 2, "empty-scope")
    assert (envelope["mode"], envelope["stack_libraries"], envelope["headless_decisions"]) == (mode, [], [])
    assert envelope["error"]["phase"] == "rank-and-confirm:scope"


def test_step_1_reads_the_published_stack():
    """enhancement-2: step 1 §0 checks the stack's folder and binds the published version and libraries once the
    stack name is bound; step 3 and step 7 read them, from `{runFile}` when lost."""
    init = _read(INIT)
    assert _probe_script(init, "skillInventory") == INVENTORY
    zero = _sections(_body(init))["0"]
    phase_1 = _paragraph(zero, "**Ownership, phase 1.**")
    assert zero.index("--check-name {stack_name}") < zero.index("**Ownership, phase 1.**")
    assert "`{skill_group}` (`{skills_output_folder}/{stack_name}/`)" in phase_1
    (binds,) = [p for p in zero.split("\n\n") if p.startswith("Bind `{write_verdict}`")]
    for token in ("`{prior_active_version}` ← `write_check.marked_active_version`",
                  "bind `{prior_stack_version}` ← its `version` and `{prior_libraries}` ← its `libraries`",
                  # Only a compose-mode re-composition versions from them; code mode versions from the bundle.
                  "which step 3 marks the scope against and step 7 versions a compose-mode re-composition from",
                  "A new stack leaves all three `null`."):
        assert token in binds, token
    assert _halts(binds) == [(4, "write-failure", "init:not-a-stack")]
    assert "`path` `{skill_group}`" in binds
    # The step's goal and its summary name the check and the published stack a rerun builds on.
    goal = _slice(init, "## STEP GOAL:", "## Rules")
    assert "check the stack's folder and read the stack a rerun builds on" in goal
    four = _sections(_body(init))["4"]
    assert ("the stack name (`{stack_name}`) and, on a rerun, the published version it builds on "
            "(`v{prior_stack_version}`, with its `{prior_libraries}` count)") in four
    for path in (RANK, COMPOSE_SCOPE, GENERATE):
        assert "runFile: '{run_dir}/run.json'" in _frontmatter(_read(path)), path.name
    prior = _paragraph(_one(), "**Prior stack.**")
    for token in ("Step 1 §0 checked `{skill_group}`", "(read them from `{runFile}` if lost)",
                  "a set `{prior_stack_version}` makes this run a **re-composition**"):
        assert token in prior, token
    # The halt envelope names the folder of the not-a-stack and ownership halts.
    assert 'adding `"path"` when the halt names a file or folder' in _from(_body(init), "**Halt envelope.**")
    (rule,) = [line for line in _read(STACK_SKILL).splitlines() if "Never write into a skill folder" in line]
    assert "step 1 runs the inventory's write check before any prior metadata is read, step 7 again before staging" \
        in rule and "\u2014" not in rule


def _make_stack_version(skills: Path, name: str, version: str, metadata: dict) -> Path:
    package = skills / name / version / name
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    (package / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return package


def test_the_step_1_write_check_runs_as_written(tmp_path):
    """The phase-1 call names no version: it answers for the stack's folder and names the published version."""
    call = _call(_sections(_body(_read(INIT)))["0"], "skillInventoryHelper")
    assert "--write-version" not in call
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    skills.mkdir()

    def check(stack: str) -> dict:
        argv = _argv(call, "skillInventoryHelper", {"{skills_output_folder}": str(skills), "{stack_name}": stack,
                                                    "{forge_data_folder}": str(forge)})
        return _inventory(argv)["write_check"]

    new = check("acme-stack")
    assert (new["verdict"], new["marked_active_version"]) == ("ok", None), "a new stack leaves the prior bindings null"
    (skills / "foreign-stack").mkdir()
    (skills / "foreign-stack" / "README.md").write_text("mine\n", encoding="utf-8")
    assert check("foreign-stack")["verdict"] == "not-skf-output", "step 1 refuses a folder SKF did not generate"
    _make_stack_version(skills, "web-stack", "1.2.0", {
        "skill_type": "stack", "generated_by": "create-stack-skill", "forge_tier": "Forge", "version": "1.2.0",
        "libraries": ["react", "zod", "lodash"]})
    try:
        (skills / "web-stack" / "active").symlink_to("1.2.0", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    published = check("web-stack")
    assert (published["verdict"], published["marked_active_version"]) == ("ok", "1.2.0")
    (binds,) = [p for p in _sections(_body(_read(INIT)))["0"].split("\n\n") if p.startswith("Bind `{write_verdict}`")]
    read = re.search(r"read `(\{skills_output_folder\}/\{stack_name\}/\{prior_active_version\}/[^`]+)`", binds).group(1)
    metadata = Path(read.replace("{skills_output_folder}", str(skills)).replace("{stack_name}", "web-stack")
                    .replace("{prior_active_version}", published["marked_active_version"]))
    assert json.loads(metadata.read_text(encoding="utf-8"))["libraries"] == ["react", "zod", "lodash"]


def test_a_rerun_marks_the_scope_against_the_published_stack():
    """enhancement-2: on a rerun §2 keeps each published library the counts still find, §3 marks each row kept or
    new and lists each published library left out, and the decision records the keeps as `prior_kept`."""
    sections = _sections(_body(_read(RANK)))
    two, three = sections["2"], sections["3"]
    # #1153: the helper holds the rerun rule; §2 passes the published stack only on a rerun, from `{runFile}`
    # when lost (the rule itself runs in test_a_rerun_keeps_the_published_libraries_the_counts_find).
    assert '[--prior-version "{prior_stack_version}" --prior-libraries "{prior_libraries}"]' in \
        _call(two, "countImportsHelper", "scope")
    assert "only on a rerun (`{prior_libraries}` set; read it and `{prior_stack_version}` from `{runFile}` if lost)" \
        in two
    rerun = _paragraph(three, "**A rerun.**")
    for token in ("When `{prior_libraries}` is set (from `{runFile}` if lost)",
                  "Published column says `kept` for a library of `{prior_libraries}` and `new` for any other",
                  # A reason for each way a published library leaves the scope, and a line for none.
                  "each `{scopeFile}` `dropped[]` entry whose `reason` starts `in v{prior_stack_version}: `, with "
                  "the reason after that lead",
                  "`removed at the scope gate` for one the user took out",
                  "the line reads `none` when it leaves none out",
                  "Each scope change recomputes the marks and the Dropped line.",
                  "A new stack shows no Published column and no Dropped line."):
        assert token in rerun, token
    # The display itself marks the rerun-only parts, so a new stack never prints "Dropped from vnull".
    assert "Present the scope and the one gate, with the Published column and the Dropped line only on a rerun." \
        in three
    assert [line for line in three.splitlines() if line.startswith("| # | Library |")] == [
        "| # | Library | Files | Category | Published |"]
    # A kept published library can be dev-only, so the scope row's Category reads as the below-threshold row's.
    rows = [line for line in three.splitlines() if line.startswith(("| 1 | {name}", "| 2 | {name}"))]
    assert rows == [f'| {k} | {{name}} | {{file_count}} | {{runtime, or dev for a `scope: "dev"` dependency}} '
                    "| {kept or new} |" for k in (1, 2)]
    (total,) = [line for line in three.splitlines() if line.startswith("**Total:**")]
    assert total == "**Total:** {total} dependencies detected, {count of confirmed_dependencies} recommended for " \
        "inclusion", "the Total line counts the scope the table shows, published keeps included"
    assert three.index("**Total:**") < three.index("**Dropped from v{prior_stack_version}:** {name} ({its reason})") \
        < three.index("**Select:**")
    compose = _paragraph(three, "**In compose mode**")
    assert "with its Published column on a rerun, followed by the same Left out table and Dropped line" in compose
    lines = three.splitlines()
    (at,) = [k for k, line in enumerate(lines) if line.startswith("- **GATE")]
    gate = lines[at]
    for token in ("a published library's `reason` reads `in v{prior_stack_version}: ` and then its reason",
                  "`prior_kept` lists the libraries §2 kept only because the published stack holds them",
                  "`[]` on a new stack and in compose mode"):
        assert token in gate, token
    # The explanation comes before the staged decision, so "and run:" still introduces the record command.
    assert gate.index("`[]` on a new stack and in compose mode") < gate.index('stage `{"gate"')
    assert gate.endswith("as `{run_dir}/decision.json` and run:")
    (command,) = [line.strip() for line in lines[at + 1:] if line.strip()][1:2]
    assert command == RECORD_DECISION
    reason = _decision("rank-and-confirm.scope")["evidence"]["dropped"][0]["reason"]
    assert "under 2 files, no importing file, dev only, its unresolved reason" in reason
    assert "excluded by scope_overrides, or not among this run's dependencies" in reason
    assert "led by in v{prior_stack_version}: for a published library" in reason
    menu = _from(three, "#### Menu Handling Logic:")
    (other,) = [line for line in menu.splitlines() if line.startswith("- IF Any other:")]
    assert "on a rerun recompute the marks and the Dropped line as **A rerun** says" in other
    one = _sections(_body(_read(COMPOSE_SCOPE)))["1"]
    (header,) = [line for line in one.splitlines() if line.startswith("| # | Skill |")]
    assert header == "| # | Skill | Language | Tier | Architecture Layer | Published |"
    assert "`kept` for a skill of `{prior_libraries}`, `new` for any other" in one
    assert "Published column only on a rerun (`{prior_libraries}` set; read it from `{runFile}` if lost)" in one
    assert one.rstrip().endswith("Set `confirmed_dependencies` ← `{scopeFile}`'s `scope`.")


# A `[--flag ...]` synopsis group of a documented call.
BRACKET_GROUP_RE = re.compile(r" \[(--[^\[\]]*)\]")


def _bracketed(call: str, keep: tuple[str, ...]) -> str:
    """The call with each bracket group that holds one of the `keep` flags kept, its brackets off, and the rest
    dropped, as a stage passes them."""
    return BRACKET_GROUP_RE.sub(lambda m: " " + m.group(1) if m.group(1).split()[0] in keep else "", call)


def _run_scope_call(path: Path, run_dir: Path, stdin: str, values: dict[str, str], keep: tuple[str, ...]) -> dict:
    """A stage's own `skf-count-imports.py scope` call, run as written with the bracket groups `keep` names and
    without the others; the result is the `{scopeFile}` its redirect writes."""
    section = _sections(_body(_read(path)))["2" if path == RANK else "1"]
    call, target = _call(section, "countImportsHelper", "scope").strip().split(" > ")
    assert target == '"{scopeFile}"', f"{path.name} does not save the scope in the run folder"
    assert "scopeFile: '{run_dir}/scope.json'" in _frontmatter(_read(path)), path.name
    argv = _argv(_bracketed(call, keep), "countImportsHelper", {**values, "{run_dir}": str(run_dir)})
    result = subprocess.run([sys.executable, str(COUNT_IMPORTS), *argv], input=stdin, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    scope = json.loads(result.stdout)
    assert set(scope) == {"scope", "dropped", "prior_kept", "unknown_overrides"}
    return scope


def _code_scope(tmp_path: Path, counts: dict, prior: list[str], version: str, overrides: dict[str, str]) -> dict:
    """§2's scope call on the helper's counts: `scope_overrides` piped, the published stack passed on a rerun."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    counts_file = run_dir / "import-counts.json"
    counts_file.write_text(json.dumps(counts), encoding="utf-8")
    values = {"{importCountsFile}": str(counts_file), "{prior_stack_version}": version,
              "{prior_libraries}": ",".join(prior)}
    keep = ("--prior-version",) if prior else ()
    return _run_scope_call(RANK, run_dir, json.dumps(overrides or None), values, keep)


def _project_counts(project: Path, files: dict[str, bytes], *module: str) -> dict:
    """Step 2's scan and step 3's count, run as the steps write them, on a project of `files`; each `module`
    is a `--module` value §1 adds when it knows an unresolved entry's import name."""
    for rel, content in files.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_bytes(content)
    scan_call = _call(_sections(_body(_read(INIT)))["3"], "scanManifestsHelper", "scan").strip()
    scan = subprocess.run([sys.executable, str(SCAN_MANIFESTS),
                           *_argv(scan_call, "scanManifestsHelper", {"{scan_root}": str(project)})],
                          capture_output=True, text=True)
    assert scan.returncode == 0, scan.stderr
    count_call = _call(_sections(_body(_read(RANK)))["1"], "countImportsHelper", "count").split(" > ")[0].strip()
    argv = _argv(count_call, "countImportsHelper", {"{scan_root}": str(project), "{project_root}": str(project)})
    argv += [arg for value in module for arg in ("--module", value)]
    result = subprocess.run([sys.executable, str(COUNT_IMPORTS), *argv], input=scan.stdout,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_a_rerun_keeps_the_published_libraries_the_counts_find(tmp_path):
    """The rerun rows of the matrix, §2's scope call run on the import counter's own output: a published library
    imported by one file stays in by default, one the counts no longer hold or hold at 0 files drops with its
    published-stack reason, and an exclude override still wins (#1153: the helper, not the model, applies them)."""
    counts = _project_counts(tmp_path / "project", {
        "package.json": b'{"name": "web", "dependencies": {"react": "^18.2.0", "zod": "^3.22.0",'
                        b' "express": "^4.19.0"}}\n',
        "src/a.js": b'import React from "react";\nconst express = require("express");\n',
        "src/b.js": b'import React from "react";\nconst express = require("express");\n',
        "src/c.js": b'import React from "react";\nimport { z } from "zod";\n',
    })
    by_name = {d["name"]: d for d in counts["dependencies"]}
    assert {name: (d["file_count"], d["above_threshold"]) for name, d in by_name.items()} == {
        "react": (3, True), "express": (2, True), "zod": (1, False)}
    prior = ["react", "zod", "lodash"]
    rerun = _code_scope(tmp_path, counts, prior, "1.2.0", {})
    assert rerun["scope"] == ["react", "express", "zod"], "the scope keeps the rank order"
    assert {name: ("kept" if name in prior else "new") for name in rerun["scope"]} == {
        "react": "kept", "express": "new", "zod": "kept"}
    assert rerun["prior_kept"] == ["zod"]
    assert rerun["dropped"] == [{"library": "lodash", "reason": "in v1.2.0: not among this run's dependencies"}]
    excluded = _code_scope(tmp_path, counts, prior, "1.2.0", {"zod": "exclude"})
    assert excluded["prior_kept"] == []
    assert {"library": "zod", "reason": "in v1.2.0: excluded by scope_overrides"} in excluded["dropped"]
    included = _code_scope(tmp_path, counts, prior, "1.2.0", {"zod": "include"})
    assert "zod" in included["scope"] and included["prior_kept"] == [], "the override, not the rerun, kept it"
    assert _code_scope(tmp_path, counts, [], "1.2.0", {})["prior_kept"] == [], "a new stack keeps nothing that way"
    # A published library the manifest still declares but no file imports: the counts hold it at 0 files.
    declared = _project_counts(tmp_path / "declared", {
        "package.json": b'{"name": "web", "dependencies": {"react": "^18.2.0", "lodash": "^4.17.0"}}\n',
        "src/a.js": b'import React from "react";\n',
        "src/b.js": b'import React from "react";\n',
    })
    assert {d["name"]: d["file_count"] for d in declared["dependencies"]} == {"react": 2, "lodash": 0}
    unimported = _code_scope(tmp_path, declared, prior, "1.2.0", {})
    assert unimported["scope"] == ["react"] and unimported["prior_kept"] == []
    assert unimported["dropped"] == [
        {"library": "lodash", "reason": "in v1.2.0: no importing file"},
        {"library": "zod", "reason": "in v1.2.0: not among this run's dependencies"}]
    # Each decision is the gate's own shape: schema-valid, and the record command takes it.
    from jsonschema import Draft202012Validator

    template = _decision("rank-and-confirm.scope")
    item = _schema()["properties"]["headless_decisions"]["items"]
    assert set(template["evidence"]) == {"scope", "dropped", "prior_kept"}
    for k, scope in enumerate((rerun, excluded, unimported)):
        # The gate copies `{scopeFile}`'s three keys as they stand.
        evidence = {key: scope[key] for key in template["evidence"]}
        decision = {**template, "evidence": evidence}
        assert not list(Draft202012Validator(item).iter_errors(decision)), decision
        run_dir = tmp_path / f"skf-create-stack-skill-run{k}"
        argv = _argv(RECORD_DECISION.split(" < ")[0], "emitEnvelopeHelper", {"{run_dir}": str(run_dir)})
        recorded = subprocess.run([sys.executable, str(EMITTER), *argv], input=json.dumps(decision),
                                  capture_output=True, text=True)
        assert recorded.returncode == 0, recorded.stderr
        assert json.loads((run_dir / "headless-decisions.jsonl").read_text(encoding="utf-8")) == decision


# --- #1153: the scope, an unresolved re-count and the compose layers come from helpers ---

UNKNOWN_OVERRIDE_WARNING = ("Append one `workflow_warnings[]` entry per `unknown_overrides[]` key (`step: \"step-03\"`, "
                            "`severity: \"warn\"`, `code: \"scope-override-unknown\"`, `message`: \"scope_override: "
                            "unknown dependency '{key}', skipped\"); an unknown key never halts the run.")
MENTIONS_CALL = 'uv run {comentionHelper} mentions --doc "{architecture_doc_path}" --skills -'


def _scope_paragraph(path: Path) -> str:
    """The paragraph after a stage's scope call, which says what `{scopeFile}` holds."""
    section = _sections(_body(_read(path)))["2" if path == RANK else "1"]
    return _paragraph(section, "A non-zero exit means the call is malformed")


def test_a_known_import_name_reruns_the_count(tmp_path):
    """determinism-5: §1's own count call, run again with `--module`, ranks an unresolved entry with the others,
    so `{importCountsFile}` stays the helper's output."""
    files = {
        "requirements.txt": b"acme-client==1.0\nrequests==2.31\n",
        "app/a.py": b"import acme\nimport requests\n",
        "app/b.py": b"from acme import client\nimport requests\n",
        "app/c.py": b"import requests\n",
    }
    first = _project_counts(tmp_path / "first", files)
    assert [u["name"] for u in first["unresolved"]] == ["acme-client"]
    assert [d["name"] for d in first["dependencies"]] == ["requests"]
    again = _project_counts(tmp_path / "again", files, "acme-client=acme")
    assert again["unresolved"] == []
    assert [(d["name"], d["file_count"], d["resolution"]) for d in again["dependencies"]] == [
        ("requests", 3, "guessed"), ("acme-client", 2, "explicit")]
    # §2 then ranks it like any other library.
    assert _code_scope(tmp_path, again, [], "", {})["scope"] == ["requests", "acme-client"]


def test_the_scope_calls_run_as_written(tmp_path):
    """determinism-9: §2 and compose-scope.md §1 each run the scope helper into `{scopeFile}`, and each records one
    `scope-override-unknown` warning per unknown override, never a halt."""
    counts = _project_counts(tmp_path / "project", {
        "package.json": b'{"name": "web", "dependencies": {"react": "^18.2.0", "zod": "^3.22.0"},'
                        b' "devDependencies": {"vitest": "^1.0.0"}}\n',
        "src/a.js": b'import React from "react";\nimport { z } from "zod";\n',
        "src/b.js": b'import React from "react";\nimport { test } from "vitest";\n',
        "src/c.js": b'import { test } from "vitest";\n',
    })
    code = _code_scope(tmp_path, counts, [], "", {"zod": "include", "lodash": "include"})
    assert code == {"scope": ["react", "zod"], "dropped": [{"library": "vitest", "reason": "dev only"}],
                    "prior_kept": [], "unknown_overrides": ["lodash"]}
    # Compose mode: the names step 2 stored, piped; the overrides written beside the run, as the stage says.
    run_dir = tmp_path / "compose-run"
    run_dir.mkdir()
    one = _sections(_body(_read(COMPOSE_SCOPE)))["1"]
    assert "after writing it as JSON to `{run_dir}/scope-overrides.json` with a file write" in one
    (run_dir / "scope-overrides.json").write_text(json.dumps({"c": "exclude", "x": "include"}), encoding="utf-8")
    raw_dependencies = [{"name": name, "language": "typescript", "source": "existing_skill"} for name in "abc"]
    compose = _run_scope_call(COMPOSE_SCOPE, run_dir, json.dumps([d["name"] for d in raw_dependencies]),
                              {"{prior_stack_version}": "2.0.0", "{prior_libraries}": "a,d"},
                              ("--overrides", "--prior-version"))
    assert compose == {"scope": ["a", "b"],
                       "dropped": [{"library": "c", "reason": "excluded by scope_overrides"},
                                   {"library": "d", "reason": "in v2.0.0: not among this run's dependencies"}],
                       "prior_kept": [], "unknown_overrides": ["x"]}
    # With no overrides and no published stack both bracket groups go, and every skill is in.
    bare = _run_scope_call(COMPOSE_SCOPE, run_dir, json.dumps(["a", "b"]), {}, ())
    assert bare == {"scope": ["a", "b"], "dropped": [], "prior_kept": [], "unknown_overrides": []}
    for path in (RANK, COMPOSE_SCOPE):
        held = _scope_paragraph(path)
        assert UNKNOWN_OVERRIDE_WARNING in held, path.name
        (entry,) = [e for e in WARNING_ENTRY_RE.findall(held) if '`code: "scope-override-unknown"`' in e]
        assert '`step: "step-03"`' in entry and '`severity: "warn"`' in entry
    assert "`--overrides -`" not in _read(COMPOSE_SCOPE) and '--overrides -' in _call(
        _sections(_body(_read(RANK)))["2"], "countImportsHelper", "scope")
    # The model sets the scope from the file the helper wrote, in both modes.
    assert "Set `confirmed_dependencies` ← the recommended scope: `{scopeFile}`'s `scope`." in \
        _sections(_body(_read(RANK)))["2"]
    assert "Take every count and the recommended scope from `skf-count-imports.py`" in _rules(_read(RANK))
    assert "Take the scope from `skf-count-imports.py scope`" in _rules(_read(COMPOSE_SCOPE))


def test_the_gate_shows_and_records_the_scope_file():
    """§3 shows the helper's `dropped[]` as the Left out table in both modes, lists a rerun's drops from it and
    copies the three decision keys from `{scopeFile}`."""
    rank = _read(RANK)
    three = _scope_gate()
    assert "Below threshold" not in rank and "below-threshold" not in rank
    assert "**Left out:**" in three and "excluded by default" not in rank
    assert [line for line in three.splitlines() if line.startswith("| Library |")] == ["| Library | Reason |"]
    assert "| {library} | {reason} |" in three
    shown = _paragraph(three, "Present the scope and the one gate")
    assert ("The Left out table lists each `{scopeFile}` `dropped[]` entry, its `library` and `reason` as they "
            "stand, then each library the user took out, as `removed at the scope gate`; one the user adds leaves "
            "it.") in shown
    assert "followed by the same Left out table and Dropped line" in _paragraph(three, "**In compose mode**")
    assert "`{scopeFile}`'s `dropped[]`" in _paragraph(three, "**Empty scope.**")
    assert "each `{scopeFile}` `dropped[]` entry whose `reason` starts `in v{prior_stack_version}: `" in \
        _paragraph(three, "**A rerun.**")
    (select,) = [line for line in three.splitlines() if "**Select:**" in line]
    assert "type library names to **add** from the Left out table" in select
    (gate,) = [line for line in three.splitlines() if line.startswith("- **GATE")]
    assert "whose `evidence` copies `{scopeFile}`'s `scope`, `dropped` and `prior_kept` as they stand" in gate
    assert gate.index("copies `{scopeFile}`'s") < gate.index('stage `{"gate"')


def test_compose_layers_come_from_the_mentions_helper(tmp_path):
    """determinism-11, leanness-7: compose-scope.md takes each skill's layer candidates from the co-mention
    helper's `mentions`, warns when it cannot run, and states goals rather than a parse to emulate."""
    text = _read(COMPOSE_SCOPE)
    assert _probe_script(text, "comention") == COMENTION
    assert _probe_script(text, "countImports") == COUNT_IMPORTS
    one = _sections(_body(text))["1"]
    assert _call(one, "comentionHelper", "mentions") == MENTIONS_CALL
    # Every skill step 2 picked gets its candidates, so one the user adds at the gate has a layer too.
    assert "pipe the `raw_dependencies` names on stdin as a JSON array, so a skill the user adds at the gate has " \
        "its layer too" in one
    layers = _paragraph(one, "A skill's layer candidates are")
    for token in ("the non-null `paragraphs[].header` values of its `skills[]` entry", "`Unclassified`",
                  "When no candidate path exists or the call exits non-zero, list the skills by name",
                  "With no `architecture_doc_path`, or a document whose paragraphs have no header, list the skills "
                  "by name, with no warning."):
        assert token in layers, token
    (entry,) = [e for e in WARNING_ENTRY_RE.findall(layers) if '`code: "architecture-doc-parse-failed"`' in e]
    assert '`step: "step-03"`' in entry and '`severity: "warn"`' in entry
    assert "the layers in the order the document first names them and `Unclassified` last, by name within a layer" \
        in one
    for stale in ("try/except", "MUST", "alphabetical", "Validate override keys", "Log any overrides applied"):
        assert stale not in text, stale
    # The call as written, on a document with two sections: one header candidate each, and none for zod. The
    # path holds a space, which the quoted placeholder keeps in one argument.
    doc = tmp_path / "docs dir" / "architecture.md"
    doc.parent.mkdir()
    doc.write_text("# Web Stack\n\n## Frontend\n\nThe pages render with react.\n\n## API\n\n"
                   "The server runs express and returns JSON.\n", encoding="utf-8")
    argv = _argv(MENTIONS_CALL, "comentionHelper", {"{architecture_doc_path}": str(doc)})
    result = subprocess.run([sys.executable, str(COMENTION), *argv], input=json.dumps(["zod", "express", "react"]),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    skills = json.loads(result.stdout)["skills"]
    candidates = {s["name"]: list(dict.fromkeys(p["header"] for p in s["paragraphs"] if p["header"])) for s in skills}
    headed = [(p["header"], p["line"]) for s in skills for p in s["paragraphs"] if p["header"]]
    first_line = {header: min(line for h, line in headed if h == header) for header, _ in headed}
    # Among several candidates the model picks the one that names a layer; this document gives none several.
    assert all(len(found) <= 1 for found in candidates.values()), candidates
    layer = {name: found[0] if found else "Unclassified" for name, found in candidates.items()}
    order = sorted(layer, key=lambda name: (layer[name] == "Unclassified", first_line.get(layer[name], 0), name))
    assert [(name, layer[name]) for name in order] == [
        ("react", "Frontend"), ("express", "API"), ("zod", "Unclassified")]
    # A document the helper cannot read exits non-zero: the stage lists by name and records the warning.
    argv = _argv(MENTIONS_CALL, "comentionHelper", {"{architecture_doc_path}": str(tmp_path / "missing.md")})
    failed = subprocess.run([sys.executable, str(COMENTION), *argv], input='["react"]', capture_output=True, text=True)
    assert failed.returncode == 1 and failed.stdout == ""
