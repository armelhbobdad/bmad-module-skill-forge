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

A headless run also must not end before its work does: under `claude -p`
the run stops when the agent's turn ends, so the 6.0.0 release-gate run of
Test Skill that left a subagent in the background and ended its turn
printed no result line. So:

- all sixteen SKILL.md files, Ferris's Critical Actions included, carry one
  identical rule: every subagent runs in the foreground, every long-running
  command is waited for, and no turn ends while either still runs; the rule
  has every Agent call pass `run_in_background: false`, since Claude Code
  runs a subagent in the background when the flag is left out (#1037);
- no .md, .py, .yaml, .toml, .json or .csv file under src/, read one
  paragraph at a time with its wrapped lines joined, holds
  `run_in_background: true`, a "background agent", "subagent" or
  "sub-agent", `nohup`, `disown`, "in the background", "background
  process", "job", "task", "run", "shell" or "command", or "backgrounded",
  and each `run_in_background` it names is directly followed by `: false`
  in a clause with no word that negates or drops it, so a rule that only
  says to leave the flag out ("never with `run_in_background`", "never
  with `run_in_background: false`") fails too;
- each skill's headless contract (the sixteen places HEADLESS_CONTRACTS
  names) says a run that printed no envelope line has no result to read,
  whatever the process exit code;
- each `--batch` contract (the two skills BATCH_CONTRACTS names: the
  Headless row of SKILL.md and the "Reading a batch" paragraph of
  references/batch-mode.md, and the user docs' "Reading the result lines"
  paragraph) says a batch's result is its `batch_summary` event and the
  file its `summary_path` names, a batch that printed no such event has no
  batch result, whatever the process exit code, and its `-latest` copy is
  never read in its place (#889).
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
        "step 4 passes the flags that decided it, and the emitter records the decision with its `source`",
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


# ─── every subagent and long-running command is waited for ─────────────────

# The one rule sentence every SKILL.md carries, word for word. It names the flag's value, not only the flag: Claude
# Code runs a subagent in the background when the flag is left out, so "never with `run_in_background`" read word for
# word started one there (#1037).
FOREGROUND_RULE = (
    "- Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs "
    "a subagent in the background when the flag is left out), with parallel ones as several such calls in one "
    "message, and wait for every long-running command to exit before the next instruction; in a headless run, never "
    "end a turn while either still runs, since under `claude -p` a run stops when its turn ends.")
SKILLS = sorted(d.name for d in SRC.iterdir() if (d / "SKILL.md").is_file())
# Ferris, the agent, states his standing rules under Critical Actions; each workflow under Workflow Rules.
RULES_HEADING = {skill: "## Critical Actions" if skill == "skf-forger" else "## Workflow Rules" for skill in SKILLS}
# What the scan refuses anywhere under src/: the background flag set, a background agent, a detached process, and any
# command or job run in the background.
BACKGROUND_RE = re.compile(
    r"(?i)run_in_background\s*[:=]\s*true|\bbackground(?:ed)?\s+(?:sub-?)?agents?\b|\bnohup\b|\bdisown\b"
    r"|\bin\s+(?:the\s+)?background\b|\bbackground\s+(?:process(?:es)?|jobs?|tasks?|runs?|shells?|commands?)\b"
    r"|\bbackgrounded\b")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*])")
# What ends the clause around a `run_in_background: false`, and the words that negate or drop the setting in it.
CLAUSE_END_RE = re.compile(r"[.,;:!?()|]")
NEGATION_RE = re.compile(r"(?i)\b(?:never|not|no|nor|without|omit(?:s|ted|ting)?|leave|leaves|leaving|left|out"
                         r"|drop(?:s|ped|ping)?|skip(?:s|ped|ping)?|remove[ds]?|removing)\b|n['’]t\b")
# The one background run the scan allows: an interactive run's long `ccc index`, which the step waits for, in a
# sentence that also keeps a headless run in the foreground (a headless run stops when its turn ends).
INTERACTIVE_INDEX = ("in an interactive run, an index that can outlast that timeout may run in the background "
                     "instead, the step waiting for it to exit before it goes on; a headless run keeps it in the "
                     "foreground")
# The one other "in the background" the scan allows: the rule's reason for passing the flag, which names the tool's
# default only right after the instruction that overrides it (#1037).
FLAG_DEFAULT = ("passing `run_in_background: false` on every Agent call (Claude Code runs a subagent in the "
                "background when the flag is left out)")
SCANNED = {".md", ".py", ".yaml", ".toml", ".json", ".csv"}
# The sites that recommended a background run, or a timeout only a background run enforces, and what they say now.
FORMER_BACKGROUND_SITES = {
    "knowledge/tool-resolution.md": ("Several Agent calls in one message, each with `run_in_background: false`",
                                     "`xargs -P` (it waits for every job)",
                                     "Agent tool with `run_in_background: false`, sequential per unit"),
    "skf-setup/references/ccc-index.md": (
        f"Run the call in the foreground with the shell's longest timeout ({INTERACTIVE_INDEX}); a call the shell "
        "stops at that timeout goes on as the paragraph after the command says:",
        "Go on to section 3 however the call ends: a non-zero exit, or a call the shell stopped, is no workflow error "
        "either (steps 2 and 4 report it as a failed index)."),
    "skf-create-stack-skill/references/parallel-extract.md": (
        "stop and return what it has after about 20 tool calls",
        "and wait for it in the foreground",
        "One whose subprocess returned no usable data is a complete failure (§3): it goes in `failed[]` with an "
        "`extraction-failed` warning and counts toward the `all-extractions-failed` halt.",
        "Do NOT abort the batch on a single library that reached its budget or failed.",
        "`code: \"extraction-partial\"`"),
    "skf-create-skill/references/generate-artifacts.md": (
        f"ccc index` in the foreground with the shell's longest timeout ({INTERACTIVE_INDEX}), or use the ccc MCP "
        "tool; a call the shell stops at that timeout is ccc indexing that failed, which **Error handling** at the "
        "end of this section covers.",
        "**Error handling:** If ccc indexing or registry update fails, log and continue: do not fail the workflow."),
    "skf-create-skill/references/extract.md": (
        f"ccc index` in the foreground with the shell's longest timeout ({INTERACTIVE_INDEX}); a call the shell "
        "stops at that timeout is a `ccc index` that failed, below.",
        "When `ccc index` fails, or the check returns **degraded**, set `{ccc_discovery: []}` and continue"),
}
# The reading rule, word for word in every skill's headless contract.
NO_RESULT = ("printed no envelope line has no result to read, whatever the process exit code: it was cut off, or "
             "could not write its result")
# Where each skill states it: its invocation or headless contract, the Headless row of the SKILL.md that holds
# its contract table, Campaign's result contract, and Ferris's pipeline step that records a workflow's outcome.
HEADLESS_CONTRACTS = {
    "skf-analyze-source": "references/headless-contract.md",
    "skf-audit-skill": "SKILL.md",
    "skf-brief-skill": "references/invocation-contract.md",
    "skf-campaign": "references/campaign-contracts.md",
    "skf-create-skill": "SKILL.md",
    "skf-create-stack-skill": "references/invocation-contract.md",
    "skf-drop-skill": "references/invocation-contract.md",
    "skf-export-skill": "references/invocation-contract.md",
    "skf-forger": "references/pipeline-mode.md",
    "skf-quick-skill": "SKILL.md",
    "skf-refine-architecture": "SKILL.md",
    "skf-rename-skill": "references/invocation-contract.md",
    "skf-setup": "references/invocation-contract.md",
    "skf-test-skill": "references/invocation-contract.md",
    "skf-update-skill": "references/invocation-contract.md",
    "skf-verify-stack": "SKILL.md",
}
# The batch reading rule (#889), word for word in each --batch contract: a batch is read from its own summary event.
BATCH_NO_RESULT = "A batch that printed no `batch_summary` event has no batch result, whatever the process exit code"
# Batches share `_batch/`, and another terminal may run another batch, so the copy may be a later batch's too.
BATCH_ANOTHER = "holds the last batch summary written, which may be another batch's"
# Per skill: its -latest batch summary copy as the Headless row names it (Quick Skill's SKILL.md names no result
# file, which test-skf-quick-skill-contract.py checks) and as references/batch-mode.md names it, the phases of the
# halt line a batch prints of its own (a failed batch, not a cut-off one), the targets that printed no event, and
# the next step after a cut-off batch (Quick Skill takes a new run folder, so it starts over; Create Skill finds its
# batch folder again from the same briefs while it has no summary, and start begins a new batch once it has one).
BATCH_CONTRACTS = {
    "skf-quick-skill": ("the batch summary's `-latest` copy", "`quick-skill-batch-latest.json`",
                        "(phase `batch-mode`, or `on-activation`)",
                        ("and a target with no event did not run in this session",),
                        ("starts over from the first target",)),
    "skf-create-skill": ("`create-skill-batch-latest.json`", "`create-skill-batch-latest.json`",
                         "(phase `batch-mode`)",
                         ("a brief the plan listed as not compiled ended failed with its message",
                          "and any other target with no event did not run in this session"),
                         ("run `--batch` again with the same briefs: while the batch has no summary, it finds the "
                          "batch folder again and goes on with the brief it was working on",
                          "If `summarize` already ran but its event never reached the caller, `start` begins a new "
                          "batch from the first brief", "the per-batch file in `{skills_output_folder}/_batch/` whose "
                          "`input_briefs` match")),
}


def _paragraphs(text: str):
    """(first line number, the paragraph with its wrapped lines joined) for each blank-line-separated block."""
    block, first = [], 0
    for n, line in enumerate([*text.splitlines(), ""], 1):
        if line.strip():
            first = first or n
            block.append(line.strip())
        elif block:
            yield first, " ".join(block)
            block, first = [], 0


def _background_findings(paragraph: str) -> list[str]:
    """What in a paragraph runs something in the background, or names `run_in_background` without setting it false."""
    paragraph = " ".join(paragraph.split())
    found = [f"background run: {m.group(0)!r}" for sentence in SENTENCE_RE.split(paragraph)
             for m in BACKGROUND_RE.finditer(sentence.replace(INTERACTIVE_INDEX, "").replace(FLAG_DEFAULT, ""))]
    # Leaving the flag out runs the subagent in the background, so the only safe mention sets it false (#1037), in a
    # clause that neither negates nor drops it ("never with `run_in_background: false`", "Leave ... out").
    for match in re.finditer(r"run_in_background", paragraph):
        setting = re.match(r"`?\s*[:=]\s*`?false\b`?", paragraph[match.end():], re.IGNORECASE)
        if not setting:
            found.append("`run_in_background` that `: false` does not directly follow")
            continue
        before = CLAUSE_END_RE.split(paragraph[:match.start()])[-1]
        after = CLAUSE_END_RE.split(paragraph[match.end() + setting.end():])[0]
        if NEGATION_RE.search(before) or NEGATION_RE.search(after):
            found.append("`run_in_background: false` in a clause that negates or drops it")
    return found


def test_the_sixteen_skills_are_checked():
    assert len(SKILLS) == 16 and "skf-forger" in SKILLS, SKILLS
    assert sorted(HEADLESS_CONTRACTS) == SKILLS


@pytest.mark.parametrize("skill", SKILLS)
def test_every_skill_md_keeps_subagents_and_long_commands_waited_for(skill):
    text = _read(SRC / skill / "SKILL.md")
    heading = RULES_HEADING[skill]
    assert text.count(f"\n{heading}\n") == 1, f"{skill}: one {heading} block"
    block = text.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0]
    assert block.splitlines().count(FOREGROUND_RULE) == 1, f"{skill}: the {heading} block lacks the foreground rule"
    assert text.count(FOREGROUND_RULE) == 1, skill


def test_no_src_file_recommends_a_background_run():
    found = []
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED:
            continue
        for n, paragraph in _paragraphs(_read(path)):
            found += [f"{path.relative_to(REPO).as_posix()}:{n}: {why}" for why in _background_findings(paragraph)]
    assert found == []


@pytest.mark.parametrize("text", [
    "Use the Agent tool with `run_in_background: true`.",
    "Dispatch a background subagent per file.",
    "Dispatch a background sub-agent per file.",
    "Launch the reader subagent in the background and go on.",
    "Run `ccc index` in the foreground, or in the background, polling until it exits.",
    "Run `ccc index`\nin the background.",
    "Start the indexer as a background process.",
    "Two background jobs do the work.",
    "A background task does the work.",
    "The scan is backgrounded.",
    "Run it under nohup.",
    "Agent calls, or `run_in_background`, run them.",
    "Agent calls (`run_in_background`\nis never set).",
    # #1037: leaving the flag out runs the subagent in the background, so each wording that only leaves it out fails
    "Several calls in one message, never with `run_in_background`.",
    "Agent calls, never `run_in_background`.",
    "Run every subagent in the foreground (parallel ones as several calls in one message, never\nwith "
    "`run_in_background`).",
    "Leave `run_in_background` out of each Agent call.",
    "Pass `run_in_background: true` on every Agent call.",
    # ... and so does each wording that names the false setting only to negate or drop it
    "Agent calls, never with `run_in_background: false`.",
    "In an interactive run, a subagent may run without `run_in_background: false`.",
    "Leave `run_in_background: false` out of each Agent call.",
    "Do not pass `run_in_background: false`.",
    "On every Agent call `run_in_background: false` is left out.",
    # the flag's default is allowed only as the reason right after the instruction that passes it false
    "Claude Code runs a subagent in the background.",
    "Run every subagent in the foreground (Claude Code runs a subagent in the background when the flag is left out).",
    # the interactive allowance needs its headless half: without it, a background index is a background run
    "In an interactive run, an index that can outlast that timeout may run in the background instead.",
    "In an interactive run, a subagent may run in the background instead, the step waiting for it to exit.",
])
def test_the_background_scan_catches_each_form(text):
    [(_, paragraph)] = list(_paragraphs(text))
    assert _background_findings(paragraph), text


@pytest.mark.parametrize("text", [
    FOREGROUND_RULE,
    "Run every subagent in the foreground, passing `run_in_background: false` on every Agent call (Claude Code runs "
    "a\nsubagent in the background when the flag is left out), with parallel ones as several such calls.",
    "Several Agent calls in one message, each with `run_in_background: false`.",
    "Agent tool with `run_in_background: false`, sequential per unit.",
    "Run the call in the foreground with the shell's longest timeout.",
    f"Run the call in the foreground with the shell's longest timeout ({INTERACTIVE_INDEX}); a call the shell stops "
    "at that timeout goes on.",
])
def test_the_background_scan_passes_the_foreground_forms(text):
    [(_, paragraph)] = list(_paragraphs(text))
    assert _background_findings(paragraph) == [], text


@pytest.mark.parametrize("rel", sorted(FORMER_BACKGROUND_SITES))
def test_the_former_background_sites_keep_the_work_in_the_foreground(rel):
    text = " ".join(_read(SRC / rel).split())
    for token in FORMER_BACKGROUND_SITES[rel]:
        assert token in text, f"{rel}: {token}"
    assert "wall-clock timeout" not in text, rel


@pytest.mark.parametrize("skill", SKILLS)
def test_every_headless_contract_says_a_run_with_no_line_has_no_result(skill):
    rel = HEADLESS_CONTRACTS[skill]
    text = " ".join(_read(SRC / skill / rel).split())
    assert NO_RESULT in text, f"{skill}/{rel}"
    if rel == "SKILL.md":
        [row] = [line for line in _read(SRC / skill / rel).splitlines() if line.startswith("| **Headless** |")]
        assert NO_RESULT in row, f"{skill}: the reading rule belongs in the Headless row"


@pytest.mark.parametrize("skill", sorted(BATCH_CONTRACTS))
def test_batch_contracts_say_a_batch_with_no_summary_has_no_result(skill):
    """#889: a batch cut off before `summarize` leaves another batch's -latest summary in place."""
    row_copy, latest, phases, no_event, next_step = BATCH_CONTRACTS[skill]
    # a printed event wins over a halt line after it (Create Skill §4 halts on a summarize a compaction repeated)
    after = "A printed `batch_summary` event stays the batch's result even if a halt line follows it"
    # a batch refused with no halt line (Quick Skill's python3/uv check, no emitter) is not called cut off alone
    halt = (f"a halt line of its own {phases} says why it stopped, and with no halt line it was cut off or could not "
            "print its halt line")
    rule = (BATCH_NO_RESULT, "`batch_summary` event and the summary file its `summary_path` names",
            f"that copy {BATCH_ANOTHER}", after, halt, "A target it printed a `done` or `fail` event for ended as "
            "that event says", "a target with a `start` event and no end event has no result", *no_event)
    [row] = [line for line in _read(SRC / skill / "SKILL.md").splitlines() if line.startswith("| **Headless** |")]
    assert NO_RESULT in row, f"{skill}: the run's own rule stays in the Headless row"
    for token in (*rule, f"never {row_copy} in its place"):
        assert token in row, f"{skill} Headless row: {token}"
    [reading] = [p for _, p in _paragraphs(_read(SRC / skill / "references" / "batch-mode.md"))
                 if p.startswith("**Reading a batch.**")]
    # the event comes before the health check, so it is never a `claude -p` run's final message
    stream = ("The event comes before the health check, so a caller reads it from the session's output stream "
              "(`claude -p --output-format stream-json`) or transcript, not from the final message")
    for token in (*rule, f"never {latest} in its place", stream, *next_step):
        assert token in reading, f"{skill} batch-mode.md: {token}"
    # a null path: the per-batch file was not written, so the event and the batch file; a set path with the
    # warning: only the copy failed, and the named file still stands
    assert ("When the event's `summary_path` is null, the per-batch file was not written (its `summary_write_failed` "
            "warning says why): the event and `{batch_dir}/batch.jsonl`") in reading, skill
    assert ("A `summary_write_failed` warning beside a set `summary_path` means only the `-latest` copy failed: the "
            "file it names is still the batch's result") in reading, skill
    assert reading.count(f"never {latest}") == 2, f"{skill}: the null summary_path clause names the copy too"
    assert "an earlier one" not in row + reading, f"{skill}: the copy may be a later or concurrent batch's too"
    [docs] = [p for _, p in _paragraphs(_read(REPO / "docs" / "workflows.md"))
              if p.startswith("**Reading the result lines.**")]
    for token in (BATCH_NO_RESULT, "`quick-skill-batch-latest.json` or `create-skill-batch-latest.json`: each "
                  f"{BATCH_ANOTHER}", "(the event plus the batch run folder's `batch.jsonl` when `summary_path` is "
                  "null)", stream, after, "a halt line of its own (phase `batch-mode`, or `on-activation` for Quick "
                  "Skill) says why it stopped, and with no halt line it was cut off or could not print its halt line",
                  "a Quick Skill batch starts over from the first target, and a Create Skill batch run with the same "
                  "briefs goes on with the brief it was working on"):
        assert token in docs, f"docs/workflows.md: {token}"
    for text in (row, reading, docs):
        assert "\u2014" not in text and "\u2013" not in text, skill


@pytest.mark.parametrize("skill", sorted(BATCH_CONTRACTS))
def test_batch_contracts_list_the_batch_summary_among_their_outputs(skill):
    """#889: each Outputs row names the batch summary a --batch run writes (Quick Skill's names no file)."""
    [outputs] = [line for line in _read(SRC / skill / "SKILL.md").splitlines() if line.startswith("| **Outputs** |")]
    assert "under `--batch` the batch summary" in outputs, skill
    if skill == "skf-create-skill":
        assert ("; and under `--batch` the batch summary (`create-skill-batch-{YYYYMMDD-HHmmss}.json` and its "
                "`-latest.json` copy in `{skills_output_folder}/_batch/`) |") in outputs
