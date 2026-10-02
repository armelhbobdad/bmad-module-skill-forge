#!/usr/bin/env python3
"""Each workflow's Invocation Contract lists what its activation parses (#594).

A pipeline author reads a workflow's flags and inputs from its Invocation
Contract (the table in SKILL.md, or in references/invocation-contract.md
where a headless contract moved out of SKILL.md). A flag the table lists
that activation never reads does nothing, and a flag activation reads that
the table leaves out is one no caller learns about. So, for the 15
workflows:

- every flag in a flag row (Flags, Inputs, Headless inputs, Headless flag,
  Overrides: the rows tools/covered-surfaces.js reads) is parsed at
  activation: On Activation names the flag or binds its variable, or the
  first stage does (stage 1 and its lettered sub-stages, `0` for campaign),
  which is where an init step binds what the invocation passed;
- every flag On Activation parses is in the contract, apart from the shared
  `--headless` / `-H` pair, which src/shared/references/headless-gate-convention.md
  defines for every workflow, and the KNOWN_UNLISTED flags below;
- every input an Inputs row names with a `[required]` or `[optional]` marker
  is bound at activation, by its name or its flag.

skf-forger is the agent, not a workflow: it dispatches to these contracts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
WORKFLOWS = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")
CONVENTION = SRC / "shared" / "references" / "headless-gate-convention.md"

# The flags every workflow takes, defined once by the headless gate convention.
SHARED_FLAGS = {"--headless", "-H"}

# Flags activation parses that no contract row lists yet. Listing one in a
# flag row makes it a covered flag (docs/_internal/STABILITY.md), which takes
# an `added` change fragment, so each waits for the pull request that ships
# that fragment; until then this list keeps them visible.
KNOWN_UNLISTED = {
    "skf-campaign": {"--brief", "--manifest"},
    "skf-create-stack-skill": {"--no-headless"},
}

# tools/covered-surfaces.js: a flag that opens a backticked span, or a long
# flag written outside one, in one of these rows.
FLAG_ROW_RE = re.compile(r"^\|\s*\*\*(Flags|Inputs|Headless inputs|Headless flag|Overrides)\*\*\s*\|")
FLAG_IN_BACKTICKS_RE = re.compile(r"`((--[a-z][a-z0-9-]*|-[A-Za-z])(?![\w-])[^`]*)`")
BARE_LONG_FLAG_RE = re.compile(r"(?<![\w`-])(--[a-z][a-z0-9-]*)(?![\w-])")
LONG_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)(?![\w-])")
SHORT_FLAG_SPAN_RE = re.compile(r"^(-[A-Za-z])(?![\w-])")
# A backticked span that runs a program: its flags are that program's.
COMMAND_RE = re.compile(
    r"^\s*(?:(?:uv|uvx|python3?|py|node|npx|git|gh|bash|sh|curl|mkdir|rm|printf|mktemp|ccc|qmd)(?=\s|$)"
    r"|\{\w+(?:Helper|Script)\}|<runner>|<helper>|<preflight>)"
)
# A flag handed a {variable}, or an argument the prose says it passes to a helper.
PASSED_FLAG_RE = re.compile(r"(--[a-z][a-z0-9-]*)(?:\s+|=)[\"']?\{")
HELPER_ARG_RE = re.compile(r"passes it to `[^`]+` as `(--[a-z][a-z0-9-]*)`")
NAMED_INPUT_RE = re.compile(r"`?\b([a-z][a-z0-9_]*)\b`?(?: \([^)]*\))? \[(?:required|optional|one or more)")
FENCE_RE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.MULTILINE | re.DOTALL)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_md(workflow: str) -> str:
    return _read(SRC / workflow / "SKILL.md")


def _contract_files(workflow: str) -> list[Path]:
    files = [SRC / workflow / "SKILL.md"]
    lifted = SRC / workflow / "references" / "invocation-contract.md"
    return files + [lifted] if lifted.is_file() else files


def _flag_rows(workflow: str) -> list[str]:
    return [line for path in _contract_files(workflow) for line in _read(path).splitlines()
            if FLAG_ROW_RE.match(line)]


def _row_flags(row: str) -> set[str]:
    flags = {m.group(2) for m in FLAG_IN_BACKTICKS_RE.finditer(row)}
    outside = re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), row)
    return flags | {m.group(1) for m in BARE_LONG_FLAG_RE.finditer(outside)}


def _contract_flags(workflow: str) -> set[str]:
    return set().union(*(_row_flags(row) for row in _flag_rows(workflow)))


def _contract_mentions(workflow: str) -> set[str]:
    """Every flag a contract row names, a flag inside a longer span included
    (`campaign resume [--from=<skill>]`)."""
    rows = "\n".join(_flag_rows(workflow))
    return set(LONG_FLAG_RE.findall(rows)) | _contract_flags(workflow)


def _on_activation(workflow: str) -> str:
    return _skill_md(workflow).split("## On Activation", 1)[1].split("\n## ", 1)[0]


def _first_stage_files(workflow: str) -> list[Path]:
    """The files of the first stage and its lettered sub-stages (1, 1a, 1h, ...)."""
    stages = re.search(r"^## Stages\b(.*?)(?=^## )", _skill_md(workflow), re.MULTILINE | re.DOTALL).group(1)
    rows = re.findall(r"^\|\s*(\d+)([a-z]?)\s*\|[^|]*\|\s*(references/[\w./-]+\.md)\s*\|", stages, re.MULTILINE)
    first = rows[0][0]
    return [SRC / workflow / path for number, _, path in rows if number == first]


def _activation_text(workflow: str) -> str:
    return "\n".join([_on_activation(workflow), *(_read(p) for p in _first_stage_files(workflow))])


def _variable(flag: str) -> str:
    return "{" + flag.lstrip("-").replace("-", "_") + "}"


def _parsed_at_activation(workflow: str, flag: str) -> bool:
    text = _activation_text(workflow)
    return bool(re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text)) or _variable(flag) in text


def _activation_flags(workflow: str) -> set[str]:
    """The flags On Activation parses: every flag it names outside a code
    block, a command span, an argument handed a {variable}, an argument it
    says it passes to a helper, and a blockquote, which states how the run
    calls a helper (setup's halt contract and its emitter arguments)."""
    text = FENCE_RE.sub("", _on_activation(workflow))
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    helper_args = set(HELPER_ARG_RE.findall(text))
    found: set[str] = set()

    def span(match: re.Match) -> str:
        body = match.group(1)
        if COMMAND_RE.match(body) or re.search(r"\{\w+(?:Helper|Script)\}", body):
            return " "
        passed = set(PASSED_FLAG_RE.findall(body))
        found.update(flag for flag in LONG_FLAG_RE.findall(body) if flag not in passed)
        short = SHORT_FLAG_SPAN_RE.match(body)
        if short:
            found.add(short.group(1))
        return " "

    rest = re.sub(r"`([^`\n]*)`", span, text)
    found.update(LONG_FLAG_RE.findall(rest))
    return found - helper_args


def test_the_fifteen_workflows_are_checked():
    assert len(WORKFLOWS) == 15, WORKFLOWS


def test_the_convention_defines_the_shared_flags():
    resolving = _read(CONVENTION).split("## Resolving `{headless_mode}`", 1)[1].split("\n## ", 1)[0]
    assert "`--headless` or `-H`" in resolving


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_contract_flag_is_parsed_at_activation(workflow):
    missing = sorted(flag for flag in _contract_flags(workflow) if not _parsed_at_activation(workflow, flag))
    assert not missing, (
        f"{workflow}: the Invocation Contract lists {missing}, which neither On Activation nor the first "
        f"stage ({[p.name for p in _first_stage_files(workflow)]}) parses")


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_flag_activation_parses_is_in_the_contract(workflow):
    listed = _contract_mentions(workflow) | SHARED_FLAGS | KNOWN_UNLISTED.get(workflow, set())
    unlisted = sorted(_activation_flags(workflow) - listed)
    assert not unlisted, f"{workflow}: On Activation parses {unlisted}, which its Invocation Contract does not list"


@pytest.mark.parametrize("workflow,flag", sorted((w, f) for w, flags in KNOWN_UNLISTED.items() for f in flags))
def test_a_known_unlisted_flag_is_still_parsed_and_still_unlisted(workflow, flag):
    """Once a pull request lists the flag (with its `added` fragment), it leaves KNOWN_UNLISTED."""
    assert flag in _activation_flags(workflow), f"{workflow}: activation no longer parses {flag}"
    assert flag not in _contract_mentions(workflow), f"{workflow}: {flag} is listed now; drop it from KNOWN_UNLISTED"


def _named_inputs(workflow: str) -> set[str]:
    rows = [row for row in _flag_rows(workflow) if row.startswith("| **Inputs** |")]
    return {name for row in rows for name in NAMED_INPUT_RE.findall(row)}


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_named_input_is_bound_at_activation(workflow):
    text = _activation_text(workflow)

    def bound(name: str) -> bool:
        flags = {"--" + name.replace("_", "-"), "--" + name.removesuffix("_path").replace("_", "-")}
        return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None or any(f in text for f in flags)

    missing = sorted(name for name in _named_inputs(workflow) if not bound(name))
    assert not missing, f"{workflow}: the Inputs row names {missing}, which activation never binds"


def test_the_named_input_scan_reads_the_contracts():
    """The inputs the scan finds, so a reworded row cannot empty the check."""
    found = {w: _named_inputs(w) for w in WORKFLOWS}
    assert {"skill_name", "skill_path", "tier_override", "upstream_drift_choice"} <= found["skf-audit-skill"]
    assert {"skill_name", "mode", "version"} <= found["skf-drop-skill"]
    assert {"old_name", "new_name"} <= found["skf-rename-skill"]
    assert {"architecture_doc_path", "prd_path", "previous_report_path"} <= found["skf-verify-stack"]
    assert sum(len(v) for v in found.values()) >= 20, found
