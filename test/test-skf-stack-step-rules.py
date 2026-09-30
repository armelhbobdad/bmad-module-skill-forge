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
  record per export, relative to step 1's project root, checks the labels
  with skf-render-metadata-stats.py in code mode (§3a) and makes a library
  T1 only when an ast-grep rule matched every export it recorded; the
  stack provenance schema holds step 4's labels and no node kind; step 7
  runs the provenance verifier on the code-mode map and lets it move the
  lines with one answer (#555).
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
COMPOSE_RULES = REFS / "compose-mode-rules.md"
STEP_FILES = sorted(REFS.glob("*.md"))
TIERS = REPO_ROOT / "src" / "knowledge" / "confidence-tiers.md"
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
STATS_HELPER = SCRIPTS / "skf-render-metadata-stats.py"
VERIFIER = SCRIPTS / "skf-verify-provenance-completeness.py"
ENUMERATE = SCRIPTS / "skf-enumerate-stack-skills.py"
NAMES_HELPER = SCRIPTS / "skf-names-present.py"
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
    assert "{scan_root}" in records, "source_file is not relative to the scanned root"
    library_level = shape.replace(records, "")
    assert not re.search(r"^\s+confidence:", library_level, re.MULTILINE), (
        "the worker still returns a library tier; §3a sets it from the checked records")


def test_scan_root_is_the_project_root_from_step_1():
    # The explicit-dependency path skips step 2's manifest scan, so every
    # step that names {scan_root} binds it to step 1's project_root.
    assert "`project_root`" in _sections(_read(REFS / "init.md"))["1"]
    places = {
        "step 4 §2": _sections(_body(_read(EXTRACT)))["2"],
        "step 7 §7": _from(_sections(_body(_read(GENERATE)))["7"], "**Source lines (code mode only).**"),
        "the schema": _h2_section(_read(SCHEMA), "## Code-mode variant").split("```")[0],
    }
    for where, text in places.items():
        binding = [s for s in re.split(r"(?<=[.:]) ", text) if "{scan_root}" in s and "`project_root`" in s]
        assert binding and "step 1" in binding[0], f"{where} does not bind {{scan_root}} to step 1's project_root"
        assert "step 2 scanned" not in text, where


def test_the_label_check_runs_between_extraction_and_the_summary():
    text = _read(EXTRACT)
    assert _probe_script(text, "renderMetadataStats") == STATS_HELPER
    sections = _sections(_body(text))
    order = list(sections)
    assert order.index("3") + 1 == order.index("3a") == order.index("4") - 1
    check = sections["3a"]
    assert "Code mode only" in check.split("\n\n")[1], "§3a does not open with its code-mode guard"
    call = _call(check, "renderMetadataStatsHelper")
    assert "--shape stack" in call and "--check" not in call, call
    assert "`coherence`" in check and "`confidence_distribution`" in check
    assert "§3a" in sections["4"], "§4 does not show the export label counts §3a kept"
    tiers = _from(check, "**Library tiers.**")
    assert "`per_library_extractions[].confidence`" in tiers
    assert "`ast_bridge`" in tiers and "`T1-low` otherwise" in tiers, "the library tier is not keyed on the method"


def test_the_labels_file_is_in_the_purges():
    check = _sections(_body(_read(EXTRACT)))["3a"]
    labels = _call(check, "renderMetadataStatsHelper").split("uv run {renderMetadataStatsHelper}", 1)[1].split()[0]
    assert labels.endswith(".skf-labels.json"), labels
    (cancel,) = [line for line in _read(COMPILE).splitlines() if line.startswith("- IF X:")]
    for where, text in (("step 4 §3", _sections(_body(_read(EXTRACT)))["3"]), ("step 6 [X]", cancel)):
        assert f"`{labels}`" in text, f"{where} does not purge {labels}"


def test_the_label_check_call_runs_as_written(tmp_path, monkeypatch, capsys):
    check = _sections(_body(_read(EXTRACT)))["3a"]
    call = _call(check, "renderMetadataStatsHelper")
    payload = re.search(r"echo '(.*?)' \|", call).group(1)
    argv = _argv(call, "renderMetadataStatsHelper", {"{forge_data_folder}": str(tmp_path), "{project_name}": "demo"})
    labels = Path(argv[0])
    stats = _load(STATS_HELPER, "skf_render_metadata_stats_stack_rules")

    def run(records):
        labels.write_text(json.dumps({"entries": records}), encoding="utf-8")
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        code = stats.main(argv)
        return code, json.loads(capsys.readouterr().out)

    # Client was read by eye but labeled T1, the Forge-tier label before #555.
    code, out = run(_liba_records(client_tier="T1"))
    assert code == 1
    assert [(v["field"], v["expected"]) for v in out["coherence"]["violations"]] == [
        ("provenance.entries[2].confidence", "T1-low"),
        ("provenance.entries[2].signature_source", "T1-low"),
    ]
    code, out = run(_liba_records())
    assert (code, out["coherence"]) == (0, {"ok": True, "violations": []})
    assert out["confidence_distribution"] == {"t1": 2, "t1_low": 1, "t2": 0, "t3": 0}  # §4's label counts


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
    assert "--source-root {scan_root}" in verify and "--skill-dir" not in verify, verify
    fix = _call(check, "verifyProvenanceCompletenessHelper", "fix")
    assert "--provenance {forge_version}/provenance-map.json" in fix, fix
    assert "`missing`" in check and "`orphaned`" in check
    assert "`workflow_warnings[]`" in check, "the line check leaves its warnings nowhere"


def test_the_line_check_calls_run_as_written(tmp_path):
    check = _from(_sections(_body(_read(GENERATE)))["7"], "**Source lines (code mode only).**")
    scan_root = tmp_path / "project"
    (scan_root / "libs" / "liba").mkdir(parents=True)
    (scan_root / "libs" / "liba" / "api.py").write_bytes(LIBA_API)
    staging = tmp_path / "skills" / "demo-stack" / "1.0.0" / "demo-stack.skf-tmp"
    staging.mkdir(parents=True)
    skill_md = b"# demo Stack Skill\n\n`get_config()` caches its result (libs/liba/api.py:10).\n"
    (staging / "SKILL.md").write_bytes(skill_md)
    (staging / "metadata.json").write_text(json.dumps({"skill_type": "stack", "exports": []}), encoding="utf-8")
    forge_version = tmp_path / "forge" / "demo-stack" / "1.0.0"
    forge_version.mkdir(parents=True)
    provenance = forge_version / "provenance-map.json"
    provenance.write_text(json.dumps({"skill_type": "stack", "entries": _liba_records()}), encoding="utf-8")
    values = {"{skill_staging}": str(staging), "{forge_version}": str(forge_version), "{scan_root}": str(scan_root)}

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


# --- #528: a stack bins libraries, not provenance entries -------------------------


def test_stack_distribution_counts_each_library_once():
    (bullet,) = [line for line in _sections(_body(_read(GENERATE)))["6"].splitlines()
                 if line.startswith("- `confidence_distribution`")]
    for needle in ("`per_library_extractions[].confidence`", "`library_count`", "evidence report"):
        assert needle in bullet, needle
    note = _h2_section(_read(TEMPLATE), "## metadata.json Structure").split("```")[-1]
    knowledge = _slice(_read(TIERS), "## Confidence Distribution in Metadata", "## Anti-Patterns")
    for where, text in (("the template note", note), ("confidence-tiers.md", knowledge)):
        assert "`library_count`" in text and "`per_library_extractions[].confidence`" in text, where
    assert "read by eye" not in note, "the template re-derives the tier step 4 sets"
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


def test_compose_pairs_take_the_weaker_tier():
    rules = _h2_section(_read(COMPOSE_RULES), "## Confidence Tier Inheritance")
    cases = PAIR_CASE_RE.findall(rules)
    assert len(cases) >= 2, "the rule lost its worked pair cases"
    for a, b, c, d, tier in cases:
        for x, y in ((a, b), (c, d)):
            if x:
                assert tier == _weaker(x, y), f"{x} + {y} gives {tier}, not the weaker tier"
    for path in (COMPOSE_RULES, DETECT):
        assert "+T2 annotations" not in _read(path), f"{path.name} still keeps a T2 pair at a stronger tier"
    for path in (COMPOSE_RULES, DETECT, SCHEMA):
        assert not OLD_MATRIX_RE.search(_read(path)), f"{path.name} still points at the old tier matrix"


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
