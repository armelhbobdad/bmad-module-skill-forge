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

The pins check what the steps do rather than how a sentence is worded, so a
later change can reword these sections and still pass. Every slicer asserts
that its markers exist and that the slice is not empty, so a renamed
heading fails instead of passing vacuously.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STACK = REPO_ROOT / "src" / "skf-create-stack-skill"
REFS = STACK / "references"
TEMPLATE = STACK / "assets" / "stack-skill-template.md"
COMPILE = REFS / "compile-stack.md"
GENERATE = REFS / "generate-output.md"
VALIDATE = REFS / "validate.md"
DETECT = REFS / "detect-integrations.md"
REPORT = REFS / "report.md"
STEP_FILES = sorted(REFS.glob("*.md"))

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
