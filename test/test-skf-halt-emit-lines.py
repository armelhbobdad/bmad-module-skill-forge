#!/usr/bin/env python3
"""Every HARD HALT of the 15 workflows reaches the shared emitter (#593).

A HARD HALT must print the workflow's result envelope through the shared
emitter, so a pipeline learns why the run stopped. A step file meets that in
one of two ways:

- the HALT carries the emit command inline (create-skill, quick-skill,
  rename-skill and brief-skill write it at each HALT); or
- the step states the emit command once, in a halt rule ("Halt envelope",
  "Halt procedure", "Halt Envelope", a Rules bullet), and every HALT in it
  names that rule's inputs: its `halt_reason` and exit code, its status
  (update-skill) or its phase (setup). Drop's select.md and execute.md
  state theirs in section 1, its On Activation HALTs follow the Halt
  Envelope section of references/invocation-contract.md, and rename's
  select.md and execute.md in their Halt procedure paragraphs. A reference
  file a step loads takes that step's rule, and a step may name the file
  that holds the rule (export's references/result-envelope.md, campaign's
  references/campaign-contracts.md).

This file checks, for every step file (SKILL.md and references/, outside
code blocks and tables):

- a file whose HALTs name a reason holds the workflow's emit command, names
  where its rule lives, or is loaded by a file that does;
- every such HALT names a `halt_reason` the workflow's schema lists, with
  the exit code the schema maps it to (or, where each exit code has one
  reason, only the code), update's a schema status, setup's a phase;
- every HALT instruction names one of these, points at another HALT ("HALT
  as in §4", "HALT below", "HALT the same way") or sits in a section whose
  "**Every ... HALT**" rule names them, except an interactive-only HALT, a
  Rules bullet that restates the halts of the sections below it, and the
  install-fault HALT a workflow's rule says emits nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCHEMA_DIR = SRC / "shared" / "scripts" / "schemas"
WORKFLOWS = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")


def _settings() -> dict[str, tuple[dict, dict]]:
    found = {}
    for path in sorted(SCHEMA_DIR.glob("*-result-envelope.v*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        meta = schema["$defs"]["skf-envelope"]["const"]
        found[meta["workflow"]] = (schema, meta)
    return found


SCHEMAS = _settings()

# The emit commands a workflow's halts run.
EMIT = {workflow: (f"emit-halt --workflow {workflow}",) for workflow in WORKFLOWS}
EMIT["skf-brief-skill"] = ("{emitBriefEnvelopeHelper} emit",)
EMIT["skf-setup"] = ("emit-blocked",)
# Update's halt helper prints the line; an activation halt before the run
# folder exists calls the emitter itself.
EMIT["skf-update-skill"] = ("{runStateHelper} halt", "emit-halt --workflow skf-update-skill")


def _emits(workflow: str, text: str) -> bool:
    return any(command in text for command in EMIT[workflow])


# Where a workflow states its halt rule, when its step files name the file
# instead of restating the command.
RULE_HOMES = {
    "skf-campaign": ("`references/campaign-contracts.md`",),
    "skf-drop-skill": ("Halt Envelope section of `references/invocation-contract.md`",),
    "skf-export-skill": ("`references/result-envelope.md`",),
    "skf-setup": ("SKILL.md halt contract",),
    "skf-brief-skill": ("SKILL.md Halt Contract",),
    "skf-verify-stack": ("`references/exit-codes.md`",),
}

# A SKILL.md rule that every step file's HALTs follow. Elsewhere SKILL.md
# leaves the command to each stage, so listing a stage does not cover it.
WORKFLOW_WIDE_RULES = {
    "skf-brief-skill": "Every HALT that names a `halt_reason`, in any step file, emits the `SKF_BRIEF_RESULT_JSON` error envelope",
    "skf-create-skill": "Every HARD HALT in steps 1 to 7 emits the result envelope before it stops, in every mode.",
}

# The halt rule a workflow states for an install fault that emits nothing,
# and the HALT that takes it. Brief's schema lists no `helper-missing`
# value: a helper with no installed path HALTs with no halt_reason.
EMITS_NOTHING = {
    "skf-brief-skill": ("A HALT that names no `halt_reason`, such as a helper with no installed path",
                        re.compile(r"HALT if (?:no candidate|neither) exists")),
}

LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*]|\d+[a-z]?\.)\s")
# HALT used as an instruction: at the start of a sentence, list item or
# clause (a bold label's "**On error:** HALT" included), or after "then",
# "and" or "or". Not "every HARD HALT", "each
# step's entry, exit, and HARD HALT,", "a HALT keeps it" or a gate's
# "GATE [default: HALT ...]" annotation.
HALT_RE = re.compile(
    r"(?:^|[:.;→)]\s+|[:.)]\*\*\s+|^\s*(?:[-*]|\d+[a-z]?\.)\s+|\bthen\s+|\band\s+|\bor\s+|,\s+|\*\*)"
    r"(?<!every )(?<!each )(?<!any )(?<!at )(?<!default: )"
    r"(?:HARD )?HALT\b(?:\*\*)?(?!,)"
    r"(?!\s+(?:envelope|contract|procedure|reason|message|line|site|path|payload|event|code)s?\b)",
    re.MULTILINE,
)
# A HALT that points at another one, which names its reason there.
POINTER_RE = re.compile(r"\bHALT\b\**\s+(?:as\b|below\b|per\b|the same way\b|with the same code\b"
                        r"|with the mapped code\b)|\bHALT\b[^.\n]*\b(?:below|above)\b")
# A section rule for every HALT in it ("**Every §6b HALT** runs the halt
# procedure with `status: "blocked"`, ..."), which its HALTs take.
SECTION_RULE_RE = re.compile(r"^\*\*Every [^*]*HALT\*\*")
# A halt_reason value written out, and one a variable or a helper supplies.
EXPLICIT_REASON_RE = re.compile(r'halt_reason[`*]*:\s*\\?"([a-z][a-z0-9-]*)"|"halt_reason":\s*"([a-z][a-z0-9-]*)"')
PLACEHOLDER_REASON_RE = re.compile(r"\{halt_reason\}|\{rename_verdict\}|<halt_reason>|<the halt reason>"
                                   r"|(?:its|the script's|the helper's) `halt_reason`")
# "HALT and wait for operator input": a gate that waits, not a halt.
GATE_WAIT_RE = re.compile(r"\bHALT and wait\b")
INTERACTIVE_RE = re.compile(r"(?i)^\s*(?:[-*]\s*)?(?:\*\*)?interactive\b|interactive-only|interactive only")
# The HALT's own exit code: right after it ("HALT (exit code 4", "HALT with
# **exit 3**"), or an "exit code N" phrase anywhere in its block. A bare
# "exit 2" elsewhere is a helper's exit, not the halt's.
HALT_CODE_RE = re.compile(r"\bHALT\b\**\s*(?:\(|with\s+)?\s*\**\s*exit(?: code)?\s*\**\s*(\d+)\b")
EXIT_CODE_RE = re.compile(r"\bexit code\s*\**\s*(\d+)\b")
STATUS_RE = re.compile(r"\bstatus[`*:\s\"]*`?\"?([a-z][a-z-]+)`?\"?")
PHASE_RE = re.compile(r"\bphase\b\s*`[^`]+`|\"phase\":\s*\"|\bphase: \"")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _files(workflow: str) -> list[Path]:
    skill = SRC / workflow
    return [skill / "SKILL.md", *sorted((skill / "references").rglob("*.md"))]


def _blocks(text: str):
    """[first line, heading, text] per paragraph or list item outside tables.
    A list item keeps its nested items, its indented continuation
    paragraphs and its code blocks; a paragraph keeps the code block that
    follows it."""
    out: list[list] = []
    heading, current, start, item_indent, fence, blank = "", [], 0, None, None, False

    def close():
        nonlocal current, item_indent
        if current:
            out.append([start, heading, "\n".join(current)])
        current, item_indent = [], None

    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("```"):
            if fence is None:
                fence = []
            else:
                if current:
                    current.extend(fence)
                elif out:
                    out[-1][2] += "\n" + "\n".join(fence)
                fence = None
            continue
        if fence is not None:
            fence.append(line)
            continue
        if not stripped:
            blank = True
            continue
        item = LIST_ITEM_RE.match(line)
        continues = item_indent is not None and indent > item_indent
        if stripped.startswith("#"):
            close()
            heading = stripped
            blank = False
            continue
        if stripped.startswith("|"):
            if not continues:
                close()
            blank = False
            continue
        if current and (blank and not continues or item and not continues):
            close()
        if not current:
            start = number
            item_indent = len(item.group(1)) if item else None
        current.append(line)
        blank = False
    close()
    return out


def _with_followers(blocks, index: int) -> str:
    """A block that ends with a colon takes what it introduces: the list that
    follows it, or the next few paragraphs."""
    text = blocks[index][2]
    if not text.rstrip().endswith(":"):
        return text
    taken = []
    for block in blocks[index + 1:index + 12]:
        if taken and not LIST_ITEM_RE.match(block[2]) and LIST_ITEM_RE.match(taken[0]):
            break
        taken.append(block[2])
        if len(taken) == 4 and not LIST_ITEM_RE.match(taken[0]):
            break
    return text + "\n" + "\n".join(taken)


def _token(reason: str) -> re.Pattern:
    return re.compile(rf"(?<![\w-]){re.escape(reason)}(?![\w-])")


def _halt_reasons(workflow: str) -> dict[str, int]:
    return SCHEMAS[workflow][1].get("exit_codes") or {}


def _statuses(workflow: str) -> set[str]:
    schema, meta = SCHEMAS[workflow]
    inner = schema["properties"][meta["wrapper"]] if meta.get("wrapper") else schema
    return set(inner["properties"]["status"]["enum"])


def _names_its_halt(workflow: str, text: str) -> bool:
    """The block names what the halt rule needs: a reason, a code, a status or a phase."""
    reasons = _halt_reasons(workflow)
    if workflow == "skf-update-skill":
        return bool(STATUS_RE.search(text) or "halt procedure" in text)
    if workflow == "skf-setup":
        return bool(PHASE_RE.search(text))
    return bool("halt_reason" in text or HALT_CODE_RE.search(text) or EXIT_CODE_RE.search(text)
                or any(_token(r).search(text) for r in reasons))


def _halt_sites(workflow: str):
    """(file, first line, heading, block) for each block that holds a HALT instruction."""
    for path in _files(workflow):
        blocks = _blocks(_read(path))
        for index, (line, heading, text) in enumerate(blocks):
            if HALT_RE.search(text) or (workflow == "skf-setup" and re.search(r"\bhalt\b[^.\n]*\bwith phase\b", text)):
                yield path, line, heading, _with_followers(blocks, index)


def _rule_files(workflow: str) -> set[Path]:
    """Files that hold the emit command or name where the halt rule lives."""
    homes = RULE_HOMES.get(workflow, ())
    return {path for path in _files(workflow)
            if _emits(workflow, _read(path)) or any(home in _read(path) for home in homes)}


NEXT_STEP_RE = re.compile(r"^nextStepFile:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", re.MULTILINE)


def _stage_files(workflow: str) -> set[Path]:
    """The stages: every file the Stages table lists, every file with a
    nextStepFile and every file one names."""
    skill = SRC / workflow
    stages = re.search(r"^## Stages\b(.*?)(?=^## )", _read(skill / "SKILL.md"), re.MULTILINE | re.DOTALL).group(1)
    found = {(skill / rel).resolve() for rel in re.findall(r"references/[\w./-]+\.md", stages)}
    for path in (skill / "references").rglob("*.md"):
        frontmatter = _read(path).split("\n---\n", 1)[0] if _read(path).startswith("---\n") else ""
        target = NEXT_STEP_RE.search(frontmatter)
        if target:
            found.add(path.resolve())
            found.add((path.parent / target.group(1)).resolve())
    return found


def _covered(workflow: str, path: Path, rules: set[Path]) -> bool:
    """The file holds the rule, or SKILL.md states it for every step file,
    or (for a file no Stages row or chain names, which a step loads) a step
    file that holds the rule names it."""
    if path in rules:
        return True
    skill_md = SRC / workflow / "SKILL.md"
    if path != skill_md and skill_md in rules and workflow in WORKFLOW_WIDE_RULES:
        return True
    if path == skill_md or path.resolve() in _stage_files(workflow):
        return False
    name = path.relative_to(SRC / workflow / "references").as_posix()
    return any(name in _read(rule) for rule in rules if rule not in (path, skill_md))


def test_every_workflow_has_a_schema():
    assert sorted(SCHEMAS) == WORKFLOWS


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_the_emit_command_is_written_where_the_rule_lives(workflow):
    holders = [p for p in _files(workflow) if _emits(workflow, _read(p))]
    homes = RULE_HOMES.get(workflow, ())
    assert holders, f"{workflow}: no step file writes {EMIT[workflow]}"
    for home in homes:
        if home.startswith("`references/"):
            target = SRC / workflow / home.strip("`")
            assert _emits(workflow, _read(target)), f"{workflow}: {home} names none of {EMIT[workflow]}"


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_each_file_that_halts_states_or_names_its_emit_rule(workflow):
    rules = _rule_files(workflow)
    bare = sorted({path.relative_to(SRC).as_posix()
                   for path, _, _, text in _halt_sites(workflow)
                   if _names_its_halt(workflow, text) and not _covered(workflow, path, rules)})
    assert not bare, (
        f"{workflow}: these files HALT but neither write {EMIT[workflow]} nor name the file that does, "
        f"and no step that loads them does: {bare}")


def _reason_problem(workflow: str, text: str) -> str | None:
    """Why a halt that names its reason names one the emitter would refuse, or None."""
    if workflow == "skf-update-skill":
        named = {m.group(1) for m in STATUS_RE.finditer(text)} & _statuses(workflow)
        stated = {m.group(1) for m in STATUS_RE.finditer(text)}
        unknown = sorted(s for s in stated - named if s not in ("ok", "flipped", "missing-target", "mismatch"))
        return f"statuses {unknown} are not in the schema" if unknown and not named else None
    if workflow == "skf-setup":
        return None
    codes = _halt_reasons(workflow)
    stated = {a or b for a, b in EXPLICIT_REASON_RE.findall(text)}
    if stated - set(codes):
        return f"names halt_reason {sorted(stated - set(codes))}, which the schema does not list"
    reasons = [r for r in codes if _token(r).search(text)]
    halt_codes = [int(c) for c in HALT_CODE_RE.findall(text)] or [int(c) for c in EXIT_CODE_RE.findall(text)]
    if halt_codes and set(halt_codes) == {0}:
        return None  # a finished exit, such as drop's dry run, takes no halt_reason
    if reasons:
        if halt_codes and not any(codes[r] in halt_codes for r in reasons):
            return f"names {reasons} with exit {halt_codes}, which the schema maps to {[codes[r] for r in reasons]}"
        return None
    if halt_codes:
        by_code: dict[int, list[str]] = {}
        for reason, code in codes.items():
            by_code.setdefault(code, []).append(reason)
        if any(len(by_code.get(c, [])) == 1 for c in halt_codes):
            return None
        if PLACEHOLDER_REASON_RE.search(text):
            return None
        return f"names exit {halt_codes} but no halt_reason, and the schema maps that code to several"
    return None


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_halt_names_a_reason_the_schema_maps(workflow):
    problems = []
    for path, line, _, text in _halt_sites(workflow):
        if not _names_its_halt(workflow, text):
            continue
        problem = _reason_problem(workflow, text)
        if problem:
            problems.append(f"{path.relative_to(SRC).as_posix()}:{line}: {problem}")
    assert not problems, "\n".join(problems)


def _exempt(workflow: str, heading: str, text: str) -> bool:
    if INTERACTIVE_RE.search(text) or POINTER_RE.search(text) or GATE_WAIT_RE.search(text):
        return True
    if heading.lstrip("# ").rstrip(":").endswith("Rules"):
        return True
    rule = EMITS_NOTHING.get(workflow)
    return bool(rule and rule[1].search(text))


def _section_rules(workflow: str) -> set[tuple[Path, str]]:
    """(file, heading) of each section whose rule names what all its HALTs need."""
    return {(path, heading) for path in _files(workflow) for _, heading, text in _blocks(_read(path))
            if SECTION_RULE_RE.match(text) and _names_its_halt(workflow, text)}


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_no_halt_instruction_is_left_without_its_reason(workflow):
    ruled = _section_rules(workflow)
    bare = [f"{path.relative_to(SRC).as_posix()}:{line}: {text.strip()[:140]}"
            for path, line, heading, text in _halt_sites(workflow)
            if not _names_its_halt(workflow, text) and not _exempt(workflow, heading, text)
            and (path, heading) not in ruled]
    assert not bare, f"{workflow}: HALT instructions that name no reason the emitter could use:\n" + "\n".join(bare)


@pytest.mark.parametrize("workflow", sorted(WORKFLOW_WIDE_RULES))
def test_a_workflow_wide_rule_is_stated_in_skill_md_with_its_command(workflow):
    text = _read(SRC / workflow / "SKILL.md")
    assert WORKFLOW_WIDE_RULES[workflow] in text and _emits(workflow, text), workflow


@pytest.mark.parametrize("workflow", sorted(EMITS_NOTHING))
def test_an_emit_nothing_halt_is_one_the_workflow_rule_allows(workflow):
    sentence, pattern = EMITS_NOTHING[workflow]
    assert sentence in _read(SRC / workflow / "SKILL.md"), f"{workflow}: SKILL.md no longer states {sentence!r}"
    assert any(pattern.search(text) for _, _, _, text in _halt_sites(workflow)), (
        f"{workflow}: no HALT takes the emit-nothing rule any more; drop it from EMITS_NOTHING")


# --------------------------------------------------------------------------
# The handed-over halt rules (drop and rename)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("step", ["select.md", "execute.md"])
def test_drop_steps_state_the_halt_envelope_once_in_section_1(step):
    text = _read(SRC / "skf-drop-skill" / "references" / step)
    section = text.split("### 1. Halt Envelope", 1)[1].split("\n### ", 1)[0]
    [command] = EMIT["skf-drop-skill"]
    assert text.count(command) == 1 and command in section
    sites = [(line, t) for path, line, _, t in _halt_sites("skf-drop-skill")
             if path.name == step and _names_its_halt("skf-drop-skill", t)
             and not INTERACTIVE_RE.search(t) and HALT_CODE_RE.findall(t) != ["0"]]
    unnamed = [line for line, t in sites if "§1 halt envelope" not in t]
    assert sites and not unnamed, f"{step}: HALTs that do not say they take the section 1 halt envelope: {unnamed}"


def test_drop_activation_halts_follow_the_contract_halt_envelope():
    contract = _read(SRC / "skf-drop-skill" / "references" / "invocation-contract.md")
    envelope = contract.split("## Halt Envelope", 1)[1].split("\n## ", 1)[0]
    assert _emits("skf-drop-skill", envelope)
    activation = _read(SRC / "skf-drop-skill" / "SKILL.md").split("## On Activation", 1)[1]
    assert "the Halt Envelope section of `references/invocation-contract.md`" in activation


@pytest.mark.parametrize("step", ["select.md", "execute.md"])
def test_rename_steps_state_the_halt_procedure(step):
    text = _read(SRC / "skf-rename-skill" / "references" / step)
    blocks = _blocks(text)
    procedure = [_with_followers(blocks, i) for i, b in enumerate(blocks) if b[2].startswith("**Halt procedure")]
    assert len(procedure) == 1 and _emits("skf-rename-skill", procedure[0]), step
