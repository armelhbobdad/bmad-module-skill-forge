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
  §2 ahead of the pair-intersect pass that needs step 3's per-library file
  lists (#537).
- report.md's Rules allow the result contract and keep the rest on the
  console; a missing atomic writer records a warning instead of halting
  (#539).
- generate-output writes the evidence report after the pre-commit gate,
  the gate records its warnings in `workflow_warnings[]`, the report lists
  that accumulator, and nothing later in the run tells the agent to add to
  the written report (#585, create-stack part).
- No create-stack step keeps a blanket no-write rule ahead of a write one
  of its sections makes, and every in-file anchor link names a heading.
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
  map before the commit, and that helper applies the rule skf-test-skill
  scores names by (#538).
- One tier rule: step 5 §3 takes each pair's tier from
  skf-render-stack-metadata.py (and halts with its envelope when the helper
  is missing), compose-mode-rules and integration-patterns point at it, and
  no step file restates the tier ordering; step 7 §6 takes metadata.json's
  counts, lists, distribution, dominant tier and source_authority from it,
  with the authority step 2 records; step 8 reads the validator's stack
  structure pass instead of checking headings, keys and labels by hand, and
  runs it again after §3 changes the package (#606).
- Compose-mode pairs are candidates: step 5 §2 drops the pairs a document
  only lists together, confirms the rest from their excerpts, finds pairs
  with no architecture document by docs mentions or shared keywords (never
  a shared language) and judges those too, writes each pair in an evidence
  format whose label the structure pass reads, and locates the [VS] report
  with --locate, an unknown verdict token staying a hard error (#582,
  #590).
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
- The scope is confirmed at one gate, and a missing comention helper halts
  instead of a hand scan (#599). customize.toml keeps only the template and
  integration-pattern paths, and the metadata.json contract is fixed in
  assets/metadata-contract.md (#596). The constituent hash anchor is stated
  once, in step 4, and generate-output states each rule once (#600).

The step calls run as written, on small fixtures.

The pins check what the steps do rather than how a sentence is worded, so a
later change can reword these sections and still pass. Every slicer asserts
that its markers exist and that the slice is not empty, so a renamed
heading fails instead of passing vacuously.
"""

from __future__ import annotations

import importlib.util
import io
import json
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


# --- #537: no pair-intersect pass in compose mode -------------------------------


def test_pair_intersect_pass_skips_in_compose_mode():
    sections = _sections(_body(_read(DETECT)))
    first, second = sections["1"], sections["2"]
    opening = first.split("\n", 1)[1].lstrip("\n").split("\n", 1)[0]
    assert "compose_mode" in opening, f"§1 does not open with the compose-mode guard: {opening!r}"
    helper = PAIR_INTERSECT_RE.search(first)
    assert helper, "§1 lost the pair-intersect pass"
    heading = SECTION_HEADING_RE.match(second)
    assert heading, "§2 has no numbered heading"
    ahead = first[: helper.start()]
    assert _slug(f"{heading.group(1)}. {heading.group(2)}") in SKIP_LINK_RE.findall(ahead), (
        "the compose guard does not skip to §2 ahead of the pair-intersect pass"
    )


def test_section_2_has_the_compose_branch_the_skip_lands_on():
    assert "compose_mode" in _sections(_body(_read(DETECT)))["2"], "§2 has no compose-mode branch"


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
    assert "Code mode only" in check.split("\n\n")[1], "§3a does not open with its code-mode guard"
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
    # {version} is first bound at step 7 §1 (S11): no earlier step names a staging folder under it.
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


def _provenance_call() -> str:
    return _call(_sections(_body(_read(GENERATE)))["7"], "renderStackMetadataHelper", "provenance")


def test_step_7_writes_the_code_mode_entries_with_the_helper(tmp_path):
    """W5 handoff (determinism-5): the records step 4 checked are the map's entries and the bundle's
    pairs its integrations, never typed again; the piped input holds only the map's anchor fields."""
    seven = _sections(_body(_read(GENERATE)))["7"]
    (bullet,) = [line for line in seven.splitlines() if line.startswith("- **In code-mode:**")]
    assert "`entries` of `{exportRecordsFile}`" in bullet and "the call below writes both" in bullet
    assert "the pairs of `{bundleFile}`" in bullet
    assert "one entry per export record" not in seven and "first call" not in seven and "second call" not in seven
    # Each mode shows its own call only, under its own bullet.
    code, compose = seven.split("- **In compose-mode:**", 1)
    assert "{atomicWriteHelper}" not in code and "{renderStackMetadataHelper}" not in compose
    run_dir = tmp_path / "run dir"
    run_dir.mkdir()
    records = run_dir / "export-records.json"
    records.write_text(json.dumps({"entries": _liba_records()}), encoding="utf-8")
    bundle = run_dir / "extraction-bundle.json"
    co_import = [{"path": "src/app.py", "line_a": 1, "line_b": 2}]
    bundle.write_text(json.dumps({"integrations": [
        {"a": "liba", "b": "libb", "type": "adapter", "tier": "T1-low", "qualifier": "grep-co-import",
         "detection_method": "co-import grep", "co_import_files": co_import, "key_files": [],
         "description": "liba feeds libb"}]}), encoding="utf-8")
    forge_version = tmp_path / "forge" / "demo-stack" / "1.0.0"
    forge_version.mkdir(parents=True)
    values = {"{exportRecordsFile}": str(records), "{bundleFile}": str(bundle), "{forge_version}": str(forge_version)}
    if sys.platform == "win32":  # a POSIX shell split would eat a Windows path's backslashes
        argv = _argv(_provenance_call(), "renderStackMetadataHelper", values)
    else:  # a run folder with a space in its path reaches the helper whole: the call quotes its paths
        argv = _shell_filled(_provenance_call(), "renderStackMetadataHelper", values)
    fields = {"provenance_version": "2.0", "skill_name": "demo-stack", "skill_type": "stack", "source_repo": [],
              "source_commit": {}, "generated_at": "2026-10-02T08:00:00Z"}
    for field in fields:
        assert f"`{field}`" in bullet, field
    result = subprocess.run([sys.executable, str(STACK_METADATA), *argv], input=json.dumps(fields),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    written = json.loads((forge_version / "provenance-map.json").read_text(encoding="utf-8"))
    assert written["entries"] == _liba_records()
    assert written["integrations"] == [{"libraries": ["liba", "libb"], "pattern_type": "adapter",
                                        "detection_method": "co-import grep", "co_import_files": co_import,
                                        "confidence": "T1-low"}]
    assert list(written).index("entries") < list(written).index("integrations")


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
    zero = _sections(_body(_read(EXTRACT)))["0"]
    assert '"evidence_tier": "T1|T1-low|T2|T3"' in zero
    (bullet,) = [line for line in zero.splitlines() if line.startswith("- `confidence`:")]
    assert bullet.startswith("- `confidence`: `inventory.skills[i].evidence_tier` (one of `T1|T1-low|T2|T3`)")
    # The field §0 reads: the largest bin, ties to the weaker tier, T3
    # included, T1-low when nothing is recorded.
    enumerate_ = _load(ENUMERATE, "skf_enumerate_stack_skills_stack_rules")
    assert enumerate_.dominant_tier({"t1": 0, "t1_low": 0, "t2": 0, "t3": 12}) == "T3"
    assert enumerate_.dominant_tier({"t1": 2, "t1_low": 2, "t2": 0, "t3": 0}) == "T1-low"
    assert enumerate_.dominant_tier(None) == "T1-low"


def test_compose_entries_carry_their_constituent_tier():
    seven = _sections(_body(_read(GENERATE)))["7"]
    (bullet,) = [line for line in seven.splitlines() if line.startswith("- **In compose-mode:**")]
    for needle in ("`confidence`", "`signature_source`", "`per_library_extractions[].confidence`"):
        assert needle in bullet, needle
    for path in (EXTRACT, SCHEMA):
        assert "when it was forged" not in _read(path), f"{path.name} says a constituent checked the stack's labels"


def test_compose_pairs_take_the_helper_tier():
    """#534, #606: a pair's tier is the helper's, the weaker of its two tiers, in both modes."""
    rules = _h2_section(_read(COMPOSE_RULES), "## Confidence Tier Inheritance")
    assert "`skf-render-stack-metadata.py`" in rules and "`combine_pair_tier`" in rules
    assert not PAIR_CASE_RE.search(rules), "compose-mode-rules still works pair cases out by hand"
    for path in (COMPOSE_RULES, DETECT):
        assert "+T2 annotations" not in _read(path), f"{path.name} still keeps a T2 pair at a stronger tier"
    for path in (COMPOSE_RULES, DETECT, SCHEMA):
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
    (line,) = [line for line in _read(INTEGRATION_PATTERNS).splitlines() if line.lstrip().startswith("Confidence:")]
    assert "skf-render-stack-metadata.py" in line and "weaker" not in line, line
    detect_2 = _sections(_body(_read(DETECT)))["2"]
    compose = detect_2[:detect_2.index("**If not compose_mode:**")]
    assert "{renderStackMetadataHelper}" in compose, "§2's compose tier line does not point at the helper"
    assert "Confidence Tier Inheritance" in compose


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
    (read,) = [line for line in _sections(_body(_read(MANIFESTS)))["0"].splitlines()
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
    for needle in ("`fixed[]` is non-empty", "a split ran", "the §1 `{outputValidator}` command again", "§4 to §8"):
        assert needle in rerun, needle
    assert "§4 to §8 read the latest run" in sections["1"]
    for number in ("5", "7"):
        assert "the latest output-validator run" in sections[number], number
        assert "the §1 output-validator run" not in sections[number], number
    # The section-by-section restatements of the validator's checks are gone: each section records by `check`.
    for number in VALIDATE_CHECKS:
        assert "The pass checks" not in sections[number] and "the pass looks for" not in sections[number], number


# --- #582: compose-mode pairs are candidates, judged on their evidence ---------------


def _compose_branch() -> str:
    two = _sections(_body(_read(DETECT)))["2"]
    return two[:two.index("**If not compose_mode:**")]


def test_compose_candidates_are_judged_on_their_evidence():
    branch = _compose_branch()
    for needle in ("`comention_count`", "`lead_in_count`", "`list-only`", "`unit_excerpt`", "`unit_line`",
                   "comention-list-only", "comention-unconfirmed", "`workflow_warnings[]`"):
        assert needle in branch, needle
    for stale in ("qualify automatically", "detected-integration-pair set", "same `language` field"):
        assert stale not in _read(DETECT), stale
    assert "the candidates §2 kept qualify" in _sections(_body(_read(DETECT)))["3"]
    mapping = _h2_section(_read(COMPOSE_RULES), "## Architecture Integration Mapping")
    for stale in ("A **co-mention** is detected when", "Complementary domain roles"):
        assert stale not in mapping, stale
    assert "`unit_excerpt`" in mapping


def test_the_comention_call_runs_as_written(tmp_path):
    call = _call(_compose_branch(), "comentionHelper", "comention")
    doc = tmp_path / "architecture.md"
    doc.write_bytes(
        b"# Architecture\n\n## Tech Stack\n\n- react\n- express\n- zod\n\n"
        b"## Components\n\n| Part | Library |\n|------|---------|\n| UI | react |\n| API | express |\n| Schemas | zod |\n\n"
        b"## Data Flow\n\nThe react client posts forms to express, which validates them with zod.\n\n"
        b"Every express handler parses its body with zod before it runs.\n"
    )
    argv = _argv(call, "comentionHelper", {"{architecture_doc_path}": str(doc)})
    result = subprocess.run([sys.executable, str(COMENTION), *argv], input='["react", "express", "zod"]',
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    pairs = {(p["a"], p["b"]): p for p in json.loads(result.stdout)["pairs"]}
    # Listed together only in the Tech Stack list and the Components table, and
    # named once in prose: dropped at §2 step 4 unless a unit names both.
    assert set(pairs) == {("express", "react"), ("express", "zod"), ("react", "zod")}
    confirmed = pairs[("express", "zod")]
    assert confirmed["comention_count"] == 2
    assert [e["kind"] for e in confirmed["evidence"]] == ["list-only", "list-only", "co-mention", "co-mention"]
    assert all(e["unit_excerpt"] for e in confirmed["evidence"] if e["kind"] == "co-mention")


def test_a_diagram_edge_is_a_co_mention(tmp_path):
    """§2 step 5 counts a Mermaid edge as data flow: the script reads fenced code as text."""
    assert "`react --> express`" in _compose_branch()
    call = _call(_compose_branch(), "comentionHelper", "comention")
    doc = tmp_path / "architecture.md"
    doc.write_bytes(b"# Architecture\n\n## Flow\n\n```mermaid\ngraph LR\n  A[react] --> B[express]\n```\n\n"
                    b"The react client calls express.\n")
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
    rules = _h2_section(_read(COMPOSE_RULES), "## Inferred Integrations (No Architecture Document)")
    assert "never on a shared language alone" in rules
    assert "Infer potential integrations from skills sharing the same `language` field" not in rules


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
                   "both skills' descriptions and exports show how that domain makes them work together",
                   "never for two libraries that do the same job"):
        assert needle in shared, needle
    assert "Keep the pair as a `constituent-documented-contract` integration only when" in _infer_bullet("docs-mention")
    assert "finds and judges these pairs" in _h2_section(_read(COMPOSE_RULES),
                                                          "## Inferred Integrations (No Architecture Document)")
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
    """SKILL.md's workflow_warnings[] shape: {step, severity, code, message}."""
    entries = WARNING_ENTRY_RE.findall(_body(_read(DETECT)))
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
    for path in (DETECT, COMPOSE_RULES):
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
    assert "**Headless:** do not ask; keep the project root" in scope
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
    assert "`{importCountsFile}`" in _from(sections["1"], "**If not compose_mode:**")
    # Pair files and CCC hits share the project-root base, so the guard compares paths as they stand.
    assert "both paths are relative to `{project_root}`" in _from(sections["2"], "**If not compose_mode:**")


def test_the_monorepo_note_points_back_to_step_1():
    two = _sections(_body(_read(MANIFESTS)))["2"]
    note = _from(two, "When `folders[]` lists more than one folder").split("\n\n")[0]
    assert "the folder step 1 §3 chose" in note and "re-run with `project_path`" in note


# --- #606 item 4: compose candidates from the enumerate helper ---------------------


def test_compose_candidates_come_from_the_helper():
    manifests = _read(MANIFESTS)
    assert _probe_script(manifests, "enumerateStackSkills") == ENUMERATE
    zero = _sections(_body(manifests))["0"]
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
    headless = _from(three, "**Headless default (B8):**").split("\n\n")[0]
    assert "accept the suggestion" in headless and "With `explicit_deps`, keep code mode" not in headless


def test_the_candidates_call_runs_as_written(tmp_path):
    call = _call(_sections(_body(_read(MANIFESTS)))["0"], "enumerateStackSkillsHelper", "candidates").strip()
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
    code = _from(_sections(_body(rank))["1"], "**If not compose_mode:**")
    found = HAND_COUNT_RE.search(code)
    assert found is None, f"step 3 still counts by hand: {found.group(0)!r}"
    for stale in ("{manifestPatternsPath}", "Exclude from counting", "Use subprocess Pattern 1"):
        assert stale not in rank, stale
    assert "`{importCountsFile}`" in code and "`unresolved[]`" in code and '"modules"' in code
    # The rerun for a known import name must not replace the counts file.
    assert "without the `>` redirect" in _from(code, "**Unresolved names.**")
    assert (3, "helper-missing", "rank-and-confirm:count") in _halts(code), "a missing import counter halts with no code"
    assert (3, "helper-missing", "init:mode") in _halts(_sections(_body(_read(INIT)))["3"])
    exit_codes = _slice(_read(CONTRACT), "## Exit Codes", "## Result Contract")
    (row,) = [line for line in exit_codes.splitlines() if line.startswith("| 3 ")]
    assert "`skf-count-imports.py` (step 3 §1)" in row
    unresolved = _from(code, "**Unresolved names.**").split("\n\n")[0]
    assert "a guessed import name that matched no file, no import name, or an ecosystem with no import rules" \
        in unresolved
    assert "drop the entry from `unresolved[]`" in unresolved and "keep `dependencies[]` sorted" in unresolved
    two = _sections(_body(rank))["2"]
    assert "`above_threshold`" in two and "dev-only" in two
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
    code = _from(_sections(_body(text))["2"], "**If not compose_mode:**")
    found = HAND_COUNT_RE.search(code)
    assert found is None, f"step 5 still finds co-imports by hand: {found.group(0)!r}"
    for needle in ("`intersection_count` 2 or more", "`line_a`", "`line_b`",
                   "`co_import_files` ← its `files[]` as they stand"):
        assert needle in code, needle
    guard = _from(code, "**CCC precision guard (H3):**").split("\n\n")[0]
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
    pairs = run(PAIR_INTERSECT, pair_call, "pairIntersectHelper", web, names=",".join(recommended))["pairs"]
    assert [(p["a"], p["b"], p["intersection_count"]) for p in pairs] == [("react-dom", "zustand", 2)]
    assert pairs[0]["files"] == [{"path": "apps/web/src/main.tsx", "line_a": 2, "line_b": 3},
                                 {"path": "apps/web/src/store.tsx", "line_a": 2, "line_b": 1}]


# --- Every create-stack step file -------------------------------------------------


# #585 plans this rule for every skill in test-skf-chain-reachability.py; this
# is the create-stack slice, to fold in there when that lands.
@pytest.mark.parametrize("path", STEP_FILES, ids=lambda p: p.name)
def test_no_blanket_no_write_rule_ahead_of_a_write(path):
    text = _read(path)
    if "## Rules\n" not in text:
        pytest.skip(f"{path.name} has no Rules block")
    forbid = BLANKET_NO_WRITE_RE.search(_rules(text))
    if forbid is None:
        return
    write = WRITE_OP_RE.search(_body(text))
    assert write is None, (
        f"{path.name}: the Rules say {forbid.group(0)!r} but a section runs {write.group(0)!r}; "
        "name the write in the Rules instead"
    )


def test_the_scan_reads_the_steps_that_write():
    with_rules = {path for path in STEP_FILES if "## Rules\n" in _read(path)}
    assert {GENERATE, VALIDATE, REPORT} <= with_rules


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
    "init:emitter", "init:stack-name", "init:mode", "detect-manifests:enumerate", "detect-manifests:scan",
    "rank-and-confirm:count", "parallel-extract:enumerate", "parallel-extract:library-tiers",
    "detect-integrations:pair-intersect", "detect-integrations:comention", "detect-integrations:pair-tiers",
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
    text = _read(DETECT)
    assert "Graceful degradation" not in text and "perform the equivalent scan directly" not in text
    compose = _compose_branch()
    assert compose.index("phase `detect-integrations:comention`") < compose.index("uv run {comentionHelper}")
    assert "when no candidate resolves or `uv` cannot run it" not in compose


def test_an_unknown_verdict_token_halts_with_exit_2():
    (bullet,) = [line for line in _compose_branch().splitlines() if line.startswith("- **`unknownTokens`")]
    assert _halts(bullet) == [(2, "unknown-verdict-token", "detect-integrations:vs-report")]


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
    assert set(evidence) == {"scope", "dropped"} and set(evidence["dropped"][0]) == {"library", "reason"}
    (gate,) = [line for line in _sections(_body(_read(RANK)))["3"].splitlines() if line.startswith("- **GATE")]
    assert "names each library the default left out" in gate
    report = _sections(_body(_read(GENERATE)))["8b"]
    assert "`{run_dir}/headless-decisions.jsonl`" in report and "dropped libraries" in report


def test_the_scope_is_confirmed_at_one_gate():
    """#599 architecture-2: the user confirms the scope once, and both modes set it before the gate."""
    rank = _read(RANK)
    sections = _sections(_body(rank))
    assert list(sections) == ["1", "2", "3"]
    assert rank.count("**Select:**") == 1 and "Please confirm your scope" not in rank
    assert "ask for final confirmation" not in rank
    assert "Set `confirmed_dependencies` ← the recommended scope" in sections["2"]
    compose = sections["1"][:sections["1"].index("**If not compose_mode:**")]
    assert "Set `confirmed_dependencies` ←" in compose and "[Confirm the Scope](#3-confirm-the-scope)" in compose


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
    (state,) = [p for p in skill.split("\n\n") if p.startswith("**Single-pass, no resume:**")]
    assert "`{run_dir}`" in state and state.count(". ") == 0, "the run state is one sentence naming the run folder"


def test_the_extraction_bundle_is_written_and_read_from_disk():
    extract = _read(EXTRACT)
    bundle = json.loads(_first_fence(_from(_body(extract), "**Extraction bundle.**")))
    assert set(bundle) == {"mode", "scope", "per_library_extractions", "failed", "integrations", "hubs",
                           "cross_cutting"}
    sections = _sections(_body(extract))
    assert "Write `{bundleFile}`: `mode`, `scope` and these entries" in sections["0"]
    assert "write `{bundleFile}`: `mode`, `scope`" in sections["3"]
    # Compose mode keeps each constituent's hash in the bundle, and its usage patterns from its SKILL.md.
    zero = sections["0"]
    assert "§1+" not in extract and "fan-out at" not in zero
    assert "- `usage_patterns`: read from the constituent's `SKILL.md` loaded above" in zero
    detect_graph = _sections(_body(_read(DETECT)))["4"]
    assert "Write the graph into `{bundleFile}`" in detect_graph and '"co_import_files"' in detect_graph
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
    assert "{lib_count} libraries with" in _first_fence(sections["2"])
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
    # The stable copy at the stack group root is copied from the emitter's -latest record.
    (copy,) = [line for line in _fence_lines(two_b) if "{atomicWriteHelper} write" in line]
    assert copy.endswith("< {forge_version}/create-stack-skill-result-latest.json")
    assert "--target {forge_data_folder}/{stack_name}/create-stack-skill-result-latest.json" in copy


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
            # Step 5 keeps the name, bound to the fixed file in its own frontmatter: no override reaches it.
            assert path == DETECT, path.name
            assert "composeModeRulesPath: 'references/compose-mode-rules.md'" in _frontmatter(_read(path))
    assert "## metadata.json Structure" not in _read(TEMPLATE), "the template override still swaps the contract"
    six = _sections(_body(_read(GENERATE)))["6"]
    assert "`assets/metadata-contract.md`" in six and "{stackSkillTemplatePath}" not in six
    assert "`assets/provenance-map-schema.md`" in _sections(_body(_read(GENERATE)))["7"]


# --- #600 (create-stack part): one home per rule -----------------------------------


def test_the_constituent_hash_anchor_is_stated_once():
    homes = [path.name for path in sorted(STACK.rglob("*.md")) if "provenance anchor (S13)" in _read(path)]
    assert homes == ["parallel-extract.md"], homes
    for path in sorted(STACK.rglob("*.md")):
        assert "manifest-detection" not in _read(path), path.name
    four = [line for line in _sections(_body(_read(MANIFESTS)))["0"].splitlines()
            if line.startswith("4. **Record the constituent metadata_hash")]
    assert len(four) == 1 and "Step-07" not in four[0] and "step 7" not in four[0]
    assert "never a fresh hash" in _sections(_body(_read(GENERATE)))["7"]


def test_the_lifted_contract_keeps_skill_md_short():
    skill = _read(STACK_SKILL)
    for heading in ("## Exit Codes", "## Result Contract"):
        assert heading not in skill, heading
    assert "`references/invocation-contract.md`" in _from(skill, "## Invocation Contract")
    # About 2,000 cl100k tokens today; 10,000 characters stays below the 2,500-token guideline.
    assert len(skill) < 10_000, len(skill)
    assert "| 1 | Initialize & Mode Detection | references/init.md | Conditional |" in skill


def test_generate_output_states_each_rule_once():
    """W2 handoff (leanness-7): no advisory labels in the frontmatter, the snippet format and helper
    internals left to their owners, the atomic-writer halt in §1's body."""
    text = _read(GENERATE)
    assert "#" not in _frontmatter(text), "generate-output's frontmatter still carries comments"
    one = _sections(_body(text))["1"]
    assert one.index("**The atomic writer.**") < one.index("stage-dir --target {skill_package}")
    assert one.index("**Pre-flight: ownership, phase 1 (S3).**") < one.index("**Stack version.**") \
        < one.index("**Pre-flight: ownership, phase 2.**")
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


def test_a_warning_reaches_the_sink_as_text(tmp_path):
    """A message can quote backticks, a Mermaid edge or `$( )`: the shell must never run it."""
    contract = _h2_section(_read(STACK_SKILL), "## Workflow state contract")
    assert RECORD_WARNING in _fence_lines(contract)
    assert "`{run_dir}/warning.txt` with a file write, never an `echo`" in contract
    if sys.platform == "win32":
        return
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    message = "[step-05/warn] comention-unconfirmed: react + express: `react --> express` $(touch pwned) café"
    (run_dir / "warning.txt").write_bytes(message.encode("utf-8") + b"\n")
    command = (RECORD_WARNING.replace("uv run {emitEnvelopeHelper}", f'"{sys.executable}" "{EMITTER.as_posix()}"')
               .replace("{run_dir}", run_dir.as_posix()))
    result = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "express").exists() and not (tmp_path / "pwned").exists(), "the shell ran the message"
    (line,) = (run_dir / "warnings.jsonl").read_text(encoding="utf-8").splitlines()
    # The sink holds a JSON string, so the reports decode each line before they show it.
    assert line.startswith('"') and "\\u00e9" in line and json.loads(line) == message


@pytest.mark.parametrize("path", [p for p in STEP_FILES if p != CONTRACT], ids=lambda p: p.name)
def test_every_step_that_warns_records_in_the_sink(path):
    """Each step file shows the record command itself, so a step read on its own still records."""
    text = _read(path)
    if "workflow_warnings[]" not in text:
        return
    assert RECORD_WARNING in text, f"{path.name} appends warnings but never shows the record command"
    assert "--warning \"[" not in text, f"{path.name} puts a message inside the shell command"


def test_evidence_report_facts_are_recorded_warnings():
    """No step keeps a fact for the evidence report in memory: each is a warning in the sink."""
    detect, extract = _read(DETECT), _read(EXTRACT)
    for code, text in (("pair-cap-truncated", detect), ("infer-cap-truncated", detect),
                       ("ccc-files-dropped", detect), ("ast-degraded", extract)):
        (entry,) = [e for e in WARNING_ENTRY_RE.findall(text) if f'`code: "{code}"`' in e]
        assert re.search(r'`severity: "(info|warn|error)"`', entry), entry
    for stale in ("in context for the evidence report", "in workflow state for the evidence report",
                  "record the cap in the evidence report", "record the cap as §1 does"):
        assert stale not in detect + extract, stale
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
