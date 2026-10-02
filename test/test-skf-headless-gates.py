#!/usr/bin/env python3
"""Every gate of the 15 workflows names its headless default or a coded HALT (#594).

A headless run must never wait for a reply that cannot come, make up a
value or widen what it acts on. src/shared/references/headless-gate-convention.md
gives every gate a `**GATE [default: <option>]**` annotation, so this file
scans SKILL.md and the step files (references/, code blocks included, tables
left out):

- a gate is a section (a heading of level 1 to 3 and what follows it) that
  waits for the user, shows a menu ("Wait for the user's choice",
  "Select: [C] ...", "[Y/N]", "Choose [A/M/S]") or lists two or more
  options, one per line ("- **[S]kip**", "[P] Promote"); each one holds a
  GATE annotation, or the section after it does when that section handles
  the answer (its heading names a gate, a menu or the choice), or the
  section before it does when this one handles that section's answer,
  unless headless runs never reach it (INTERACTIVE_ONLY, each with the
  route that keeps them out, which this file checks);
- every annotation names a default, says what a headless run does, and,
  when the default is a HALT, gives that HALT its exit code and its
  `halt_reason` (update-skill: its status); a gate that decides for the
  user records the decision in the run sink, except the ones a pre-supplied
  argument answers, the ones NO_RECORD lists with the field or warning that
  carries the decision instead, and the workflows WORKFLOW_RECORDS lists
  with the place they keep their decisions (the convention's Binding Inputs
  at Activation names these exceptions);
- export-skill (the W5-export-inputs-leanness handoff): each gate the Gates
  row of references/invocation-contract.md lists states the headless
  default that row gives, at its site, and records it, so the contract and
  the step files cannot drift apart.

skf-forger is the agent, not a workflow.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
WORKFLOWS = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")
CONVENTION = SRC / "shared" / "references" / "headless-gate-convention.md"

WAIT_RE = re.compile(
    r"(?i)\bwait for (?:the )?(?:user|operator)|\bwait for (?:their|a reply|input)|\bhalt and wait\b"
    r"|\bstop and wait\b|\bwait for (?:an? )?(?:answer|reply|choice|selection|confirmation|response)"
)
MENU_RE = re.compile(
    r"\bSelect:?\**:?\s*\[|\bChoose \[[A-Z](?:/[A-Z])+\]|\[Y/N\]|\[Y\]/\[N\]|\[C\] Continue|\[P\] Proceed"
)
# One option per line, bulleted or in a menu block: "- **[S]kip**", "[P] Promote".
OPTION_LINE_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?`?\[[A-Z0-9]\]", re.MULTILINE)
GATE_RE = re.compile(r"GATE \[default: ([^\]]+)\]")
# The heading of a section that handles the answer to the one before it
# ("### 7. Gate 2: Confirm Extraction", "### 2. Act on the Choice").
ANSWER_HEADING_RE = re.compile(r"(?i)\b(?:gate|menu|choice|selection|answer)\b")
HEADING_RE = re.compile(r"^#{1,3} ", re.MULTILINE)
RECORD_RE = re.compile(r"\brecord\b", re.IGNORECASE)

# Sections a headless run never reaches, with the text that sends it
# elsewhere: brief-skill's interactive intake, which a headless run skips
# for references/headless-args.md (SKILL.md's Stages row 1h), and the draft
# resume offer that intake's §3 loads, whose file says headless runs skip it.
INTERACTIVE_ONLY = {
    ("skf-brief-skill", "references/gather-intent.md"): (
        ("### 3. Gather Target Repository", "### 3b. Gather Target Version", "### 4. Gather User Intent",
         "### 6. Derive Skill Name", "### 8. Present MENU OPTIONS"),
        ("references/gather-intent.md", "headless-args.md"),
    ),
    ("skf-brief-skill", "references/draft-checkpoint.md"): (
        ("## Half 1: Resume Check (loaded from §3 after the target is confirmed)",),
        ("references/draft-checkpoint.md", "**Headless mode skips this entire lifecycle**"),
    ),
}

# Gates whose decision a field or warning the run writes carries instead of
# the run sink, with the sentence of the gate's section that says so.
NO_RECORD = {
    ("skf-analyze-source", "references/step-auto-scope-coexistence.md"):
        "The envelope's `coexistence` field carries the choice",
    ("skf-setup", "references/auto-index.md"):
        "Set `{orphan_auto_resolution: {action: <keep|remove>, source: <as above>}}`",
    # Update's rule R1: the change manifest entry carries the document or
    # rescope choice, and step 4 writes a rescope into the brief.
    ("skf-update-skill", "references/gap-driven.md"):
        "give the manifest entry a `rescope` object",
    # Update's §4b test-report offer: headless keeps normal mode and warns.
    ("skf-update-skill", "references/init.md"):
        "add `unconsumed-test-report: {unconsumed_test_report}` to `warnings[]`. The warning is the notice",
}
# Workflows whose gates keep their decisions elsewhere, with the SKILL.md
# sentence that says where: campaign's decision log, and brief, whose
# envelope has no `headless_decisions` (its gates log each choice).
WORKFLOW_RECORDS = {
    "skf-campaign": "Log every operator decision, headless default and event",
    "skf-brief-skill": "auto-proceed through confirmation gates with their default action and log each auto-decision",
}
# A default an argument supplies: the caller decided, not the gate.
ARGUMENT_DEFAULTS = ("use args",)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _step_files(workflow: str) -> list[Path]:
    return [SRC / workflow / "SKILL.md", *sorted((SRC / workflow / "references").rglob("*.md"))]


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading line, text without table rows) per section of level 1 to 3."""
    starts = [0, *(m.start() for m in HEADING_RE.finditer(text)), len(text)]
    out = []
    for a, b in zip(starts, starts[1:]):
        chunk = text[a:b]
        if not chunk.strip():
            continue
        heading = chunk.splitlines()[0] if chunk.startswith("#") else ""
        body = "\n".join(line for line in chunk.splitlines() if not line.lstrip().startswith("|"))
        out.append((heading, body))
    return out


def _gate_sites(workflow: str):
    """(file, heading, section, section before, section after) for each
    section that waits, shows a menu or lists two or more options."""
    for path in _step_files(workflow):
        sections = _sections(_read(path))
        for index, (heading, body) in enumerate(sections):
            if WAIT_RE.search(body) or MENU_RE.search(body) or len(OPTION_LINE_RE.findall(body)) >= 2:
                before = sections[index - 1][1] if index else ""
                after = sections[index + 1][1] if index + 1 < len(sections) else ""
                yield path, heading, body, before, after


def _annotated(heading: str, body: str, before: str, after: str) -> bool:
    """The gate's section holds its annotation, or the section that handles
    its answer does, or this section handles the answer of the one before."""
    return bool(GATE_RE.search(body)
                or (ANSWER_HEADING_RE.search(after.split("\n", 1)[0]) and GATE_RE.search(after))
                or (ANSWER_HEADING_RE.search(heading) and GATE_RE.search(before)))


def _rel(workflow: str, path: Path) -> str:
    return path.relative_to(SRC / workflow).as_posix()


def _annotations(workflow: str):
    """(file, heading, section, default) per GATE annotation."""
    for path in _step_files(workflow):
        for heading, body in _sections(_read(path)):
            for match in GATE_RE.finditer(body):
                yield path, heading, body, match.group(1).strip()


def test_the_convention_states_the_annotation():
    text = _read(CONVENTION)
    assert "**GATE [default: <option>]**" in text
    assert "`**GATE [default: HALT]**`" in text
    assert "## Binding Inputs at Activation" in text


def test_the_convention_names_campaigns_resolver_warning_route():
    """Campaign's run spans several sessions, so a missing resolver goes to
    its decision log, which the envelope names (the W6-sweep-resolver-rest
    handoff); campaign's SKILL.md says the same."""
    resolver = next(paragraph for paragraph in _read(CONVENTION).split("\n\n")
                    if paragraph.startswith("When the On Activation customization resolver"))
    assert "Campaign" in resolver and "as an `event` in its decision log" in resolver, resolver
    assert "`decision_log` names that file" in resolver, resolver
    assert "`customization_resolver_unavailable: <reason>` as an `event` in the decision log" in _read(
        SRC / "skf-campaign" / "SKILL.md")


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_gate_carries_a_gate_annotation(workflow):
    bare = []
    for path, heading, body, before, after in _gate_sites(workflow):
        exempt = INTERACTIVE_ONLY.get((workflow, _rel(workflow, path)))
        if exempt and heading in exempt[0]:
            continue
        if not _annotated(heading, body, before, after):
            bare.append(f"{_rel(workflow, path)}: {heading or '(top of file)'}")
    assert not bare, (f"{workflow}: sections that wait for the user, show a menu or list options with no "
                      f"`**GATE [default: <option>]**` annotation: {bare}")


def test_the_gate_scan_finds_option_lists():
    """A gate written as a list of options, with no wait or menu wording, is
    still a gate: campaign's blocked-dependency menu is one."""
    sites = {(_rel("skf-campaign", path), heading) for path, heading, _, _, _ in _gate_sites("skf-campaign")}
    assert ("references/step-05-skill-loop.md", "### §4: Dependency Gate Check") in sites


@pytest.mark.parametrize("key", sorted(INTERACTIVE_ONLY), ids=lambda k: f"{k[0]}:{k[1]}")
def test_an_interactive_only_gate_is_one_headless_runs_skip(key):
    workflow, rel = key
    headings, (router, target) = INTERACTIVE_ONLY[key]
    text = _read(SRC / workflow / rel)
    for heading in headings:
        assert heading in text, f"{rel}: {heading} is gone; drop it from INTERACTIVE_ONLY"
    route = _read(SRC / workflow / router)
    assert target in route and "headless" in route.lower(), f"{router} no longer sends a headless run to {target}"
    if target.endswith(".md"):
        skill = _read(SRC / workflow / "SKILL.md")
        assert f"references/{target}" in skill and "(headless only)" in skill


def test_brief_envelope_has_no_headless_decisions():
    """Why brief's gates log their choices instead of recording them: its
    schema has nowhere to put them."""
    schema = json.loads(_read(SRC / "shared" / "scripts" / "schemas" / "skf-brief-result-envelope.v1.json"))
    assert "headless_decisions" not in schema["properties"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_annotation_says_what_headless_does(workflow):
    silent = []
    for path, heading, body, default in _annotations(workflow):
        if not default:
            silent.append(f"{_rel(workflow, path)}: {heading}: an empty default")
        elif not re.search(r"(?i)headless|\{quiet_mode\}", body + _headless_only_title(path)):
            silent.append(f"{_rel(workflow, path)}: {heading}: GATE [default: {default}] says nothing about headless")
    assert not silent, "\n".join(silent)


def _headless_only_title(path: Path) -> str:
    """The title of a file only headless runs load (brief's headless-args.md)."""
    title = next((line for line in _read(path).splitlines() if line.startswith("# ")), "")
    return title if "headless" in title.lower() else ""


def _halt_default(default: str) -> bool:
    return default.upper().startswith("HALT")


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_a_halt_default_names_its_exit_code_and_reason(workflow):
    bare = []
    for path, heading, body, default in _annotations(workflow):
        if not _halt_default(default):
            continue
        coded = re.search(r"\bexit(?: code)?\s*\**\s*\d", body) and re.search(
            r"halt_reason|`[a-z]+(?:-[a-z]+)+`|\([a-z]+(?:-[a-z]+)+\)", body)
        if workflow == "skf-update-skill":
            coded = re.search(r'status[`:\s"]*`?"?(?:blocked|halted-for-[a-z-]+)\b', body)
        if not coded:
            bare.append(f"{_rel(workflow, path)}: {heading}")
    assert not bare, f"{workflow}: GATE [default: HALT] with no exit code and halt_reason: {bare}"


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_a_gate_that_decides_records_the_decision(workflow):
    """A gate that picks an option for the user records it in the run sink
    (the convention's Recording Auto-Decisions), so the envelope's
    headless_decisions shows it, unless the workflow keeps its decisions
    elsewhere (WORKFLOW_RECORDS) or an envelope field carries it (NO_RECORD)."""
    if workflow in WORKFLOW_RECORDS:
        assert WORKFLOW_RECORDS[workflow] in _read(SRC / workflow / "SKILL.md"), workflow
        return
    unrecorded = []
    for path, heading, body, default in _annotations(workflow):
        if _halt_default(default) or default in ARGUMENT_DEFAULTS:
            continue
        carried = NO_RECORD.get((workflow, _rel(workflow, path)))
        if carried and carried in body:
            continue
        if not RECORD_RE.search(body):
            unrecorded.append(f"{_rel(workflow, path)}: {heading}: GATE [default: {default}]")
    assert not unrecorded, f"{workflow}: gates that decide headless and record nothing: {unrecorded}"


@pytest.mark.parametrize("key", sorted(NO_RECORD), ids=lambda k: f"{k[0]}:{k[1]}")
def test_a_no_record_gate_still_names_what_carries_its_decision(key):
    workflow, rel = key
    held = [body for path, _, body, _ in _annotations(workflow) if _rel(workflow, path) == rel]
    assert any(NO_RECORD[key] in body for body in held), f"{rel}: no GATE section says {NO_RECORD[key]!r}"


# --------------------------------------------------------------------------
# export-skill: each gate of the contract's Gates row, at its site
# --------------------------------------------------------------------------


EXPORT = SRC / "skf-export-skill"
EXPORT_CONTRACT = EXPORT / "references" / "invocation-contract.md"


def _export_gates_row() -> str:
    [row] = [line for line in _read(EXPORT_CONTRACT).splitlines() if line.startswith("| **Gates** |")]
    return row


def _section_of(rel: str, heading: str) -> str:
    sections = dict(_sections(_read(EXPORT / rel)))
    [key] = [k for k in sections if k.startswith(heading)]
    return sections[key]


# Each gate the row lists: the row's text for it, which captures the
# headless default it gives, the file and section that hold the gate, and
# how the gate writes that default.
EXPORT_GATES = {
    "layout question": (r"the layout question [^;]*?\(headless: \[([A-Z])\]",
                        "references/preflight-snippet-root-probe.md", "## Layout Question", "[{}]"),
    "mismatch gate": (r"the mismatch gate [^;]*?\(headless: checks the disk, and takes \(([a-z])\).*?, else \(([a-z])\)",
                      "references/preflight-snippet-root-probe.md", "## Mismatch Gate", "({})"),
    "step 1 confirm": (r"step 1 §6: one Confirm Gate \[[A-Z]\][^;]*\(headless: \[([A-Z])\]\)",
                       "references/load-skill.md", "### 6. Confirmation Gate", "[{}]"),
    "orphaned context files": (r"§3b orphaned context files \(headless: (\w+)\)",
                               "references/orphan-context-detection.md", "## Gate Protocol", "{}"),
    "orphaned rows": (r"§4c\.1 orphaned managed-section rows \(headless: (\w+)\)",
                      "references/orphan-row-detection.md", "## Gate Protocol", "{}"),
    "step 4 confirm": (r"step 4 §8: one Confirm Gate \[[A-Z]\][^|]*?\(headless: \[([A-Z])\]\)",
                       "references/update-context.md", "### 8.", "[{}]"),
}
RECORD_COMMAND = 'record --workflow skf-export-skill --run-dir "{run_dir}" --decision'


def test_the_export_contract_lists_every_gate_its_steps_hold():
    row = _export_gates_row()
    for name, (pattern, _, _, _) in EXPORT_GATES.items():
        assert re.search(pattern, row), f"the export Gates row no longer names the {name} with its headless default"
    listed = {(rel, heading) for _, rel, heading, _ in EXPORT_GATES.values()}

    def site(path: Path, heading: str):
        rel = _rel("skf-export-skill", path)
        return next(((r, h) for r, h in listed if r == rel and heading.startswith(h)), (rel, heading))

    held = {site(path, heading) for path, heading, _, _ in _annotations("skf-export-skill")}
    assert listed <= held, f"export gates the Gates row lists with no GATE annotation: {sorted(listed - held)}"
    assert held <= listed, f"export GATE annotations the Gates row does not list: {sorted(held - listed)}"


@pytest.mark.parametrize("name", sorted(EXPORT_GATES))
def test_each_export_gate_states_the_row_default_and_records_it(name):
    pattern, rel, heading, form = EXPORT_GATES[name]
    defaults = re.search(pattern, _export_gates_row()).groups()
    section = _section_of(rel, heading)
    annotations = GATE_RE.findall(section)
    assert len(annotations) == 1, f"{rel} {heading}: {len(annotations)} GATE annotations"
    gate = section[section.index("GATE [default:"):]
    gate = gate[:gate.find("\n\n") if "\n\n" in gate else len(gate)]
    assert re.search(r"(?i)headless", gate), f"{rel} {heading}: the annotation says nothing about headless"
    for default in defaults:
        written = form.format(default)
        assert written.lower() in gate.lower(), f"{rel} {heading}: the row's headless default {written} is not at the gate"
    assert RECORD_COMMAND in section, f"{rel} {heading}: the headless default is not recorded as a decision"
