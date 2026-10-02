#!/usr/bin/env python3
"""Each workflow's Stages table and Gates row match its GATE annotations (#599).

A workflow states its gates in three places: the `**GATE [default: X]**`
annotation at the gate in a stage file (the source of truth, per
src/shared/references/headless-gate-convention.md), the Auto-proceed column
of the SKILL.md Stages table, and the Gates row of its Invocation Contract.
memory/stages-table-gate-drift.md records them drifting apart: a wrong
"Yes" makes an interactive run skip a confirmation, or a headless run stall
on a menu the table said would auto-proceed. So, for the 15 workflows:

- a stage holds a gate when its file, or a file it loads that no Stages row
  names, carries a GATE annotation, or waits for the user in a section only
  interactive runs reach (brief-skill's intake);
- a stage that holds a gate does not read "Yes" (a headless-only stage,
  whose gate consumes the arguments and never waits, excepted), and a stage
  marked "No" or "Conditional" holds one;
- the Gates row names the steps that hold a gate, and no other: "step 3c"
  and "step 1 ratify" count for step 3 and step 1, and test-skill's row says
  "none". Campaign keeps no Gates row: its Stages table alone lists them,
  each gated stage reading "No" or "Conditional".

Setup's Stages table has no Auto-proceed column, so only its Gates row is
checked. skf-forger is the agent, not a workflow.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
WORKFLOWS = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")

GATE_RE = re.compile(r"GATE \[default: ([^\]]+)\]")
WAIT_RE = re.compile(r"(?i)\bwait for (?:the )?user|\bwait for (?:a reply|input|confirmation)\b")
ROW_RE = re.compile(r"^\|\s*(\d+)([a-z]?)\s*\|([^|\n]*)\|\s*(references/[\w./-]+\.md)\s*\|(?:([^|\n]*)\|)?",
                    re.MULTILINE)
STEP_REF_RE = re.compile(r"\bsteps? (\d+)[a-z]?(?: to (\d+))?\b")

# Sections only interactive runs reach, which wait without a GATE annotation
# (test-skf-headless-gates.py checks the route that keeps headless runs out).
INTERACTIVE_ONLY_FILES = {("skf-brief-skill", "references/gather-intent.md")}
# Workflows whose Invocation Contract has no Gates row.
NO_GATES_ROW = {"skf-campaign"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_md(workflow: str) -> str:
    return _read(SRC / workflow / "SKILL.md")


def _stages(workflow: str) -> list[dict]:
    table = re.search(r"^## Stages\b(.*?)(?=^## )", _skill_md(workflow), re.MULTILINE | re.DOTALL).group(1)
    return [{"number": m.group(1), "letter": m.group(2), "step": m.group(3).strip(), "file": m.group(4),
             "auto": m.group(5).strip() if m.group(5) is not None else None}
            for m in ROW_RE.finditer(table)]


def _stage_paths(workflow: str) -> set[Path]:
    return {(SRC / workflow / row["file"]).resolve() for row in _stages(workflow)}


def _loaded(workflow: str, path: Path) -> list[Path]:
    """The stage file and the reference files it loads that no Stages row
    names: a frontmatter key holding the path, or a "load `...`" sentence.
    A file it only cites belongs to the stage that loads it."""
    references = SRC / workflow / "references"
    stages = _stage_paths(workflow)
    text = _read(path)
    frontmatter = text.split("\n---\n", 1)[0] if text.startswith("---\n") else ""
    found = [path]
    for candidate in sorted(references.rglob("*.md")):
        rel = re.escape(candidate.relative_to(references).as_posix())
        if candidate.resolve() in stages or candidate == path:
            continue
        if (re.search(rf"^\w+:\s*['\"](?:references/)?{rel}['\"]", frontmatter, re.MULTILINE)
                or re.search(rf"(?i)\bload\b[^.\n]{{0,40}}`(?:references/)?{rel}`", text)):
            found.append(candidate)
    return found


def _gates(workflow: str, row: dict) -> list[str]:
    """What makes the stage a gate: its GATE annotations, or an interactive-only wait."""
    gates = []
    for path in _loaded(workflow, SRC / workflow / row["file"]):
        text = _read(path)
        gates += [f"{path.name}: GATE [default: {d}]" for d in GATE_RE.findall(text)]
        rel = path.relative_to(SRC / workflow).as_posix()
        if (workflow, rel) in INTERACTIVE_ONLY_FILES and WAIT_RE.search(text):
            gates.append(f"{path.name}: interactive-only wait")
    return gates


def _gates_row(workflow: str) -> str | None:
    files = [SRC / workflow / "SKILL.md", SRC / workflow / "references" / "invocation-contract.md"]
    rows = [line for path in files if path.is_file() for line in _read(path).splitlines()
            if line.startswith("| **Gates** |")]
    assert len(rows) <= 1, workflow
    return rows[0] if rows else None


def _row_steps(row: str) -> set[str]:
    steps = set()
    for first, last in STEP_REF_RE.findall(row):
        steps.update(str(n) for n in range(int(first), int(last or first) + 1))
    return steps


def test_the_fifteen_workflows_are_checked():
    assert len(WORKFLOWS) == 15, WORKFLOWS


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_stage_row_names_a_file(workflow):
    rows = _stages(workflow)
    assert len(rows) >= 4, f"{workflow}: the Stages table parsed to {rows}"
    for row in rows:
        assert (SRC / workflow / row["file"]).is_file(), (workflow, row["file"])


AUTO_WORKFLOWS = [w for w in WORKFLOWS if _stages(w)[0]["auto"] is not None]


def test_only_setup_has_no_auto_proceed_column():
    assert sorted(set(WORKFLOWS) - set(AUTO_WORKFLOWS)) == ["skf-setup"]


@pytest.mark.parametrize("workflow", AUTO_WORKFLOWS)
def test_a_stage_that_holds_a_gate_does_not_auto_proceed(workflow):
    wrong = []
    for row in _stages(workflow):
        gates = _gates(workflow, row)
        if gates and row["auto"].startswith("Yes") and "(headless only)" not in row["step"]:
            wrong.append(f"{row['number']}{row['letter']} {row['file']} says {row['auto']!r} but holds {gates}")
    assert not wrong, f"{workflow}: " + "\n".join(wrong)


@pytest.mark.parametrize("workflow", AUTO_WORKFLOWS)
def test_a_stage_marked_as_waiting_holds_a_gate(workflow):
    wrong = [f"{row['number']}{row['letter']} {row['file']} says {row['auto']!r} but holds no GATE annotation"
             for row in _stages(workflow)
             if row["auto"].startswith(("No", "Conditional")) and not _gates(workflow, row)]
    assert not wrong, f"{workflow}: " + "\n".join(wrong)


@pytest.mark.parametrize("workflow", sorted(set(WORKFLOWS) - NO_GATES_ROW))
def test_the_gates_row_names_the_steps_that_hold_gates(workflow):
    row = _gates_row(workflow)
    assert row is not None, f"{workflow}: no Gates row"
    gated = {r["number"] for r in _stages(workflow) if _gates(workflow, r)}
    named = _row_steps(row)
    if not gated:
        assert "none" in row.split("|")[2], f"{workflow}: no stage holds a gate, but the Gates row names {named}"
    assert named == gated, (
        f"{workflow}: the Gates row names steps {sorted(named)}, the stages that hold a GATE annotation are "
        f"{sorted(gated)}")


@pytest.mark.parametrize("workflow", sorted(NO_GATES_ROW))
def test_a_workflow_without_a_gates_row_lists_its_gates_in_the_stages_table(workflow):
    assert _gates_row(workflow) is None, f"{workflow}: it has a Gates row now; drop it from NO_GATES_ROW"
    gated = [row for row in _stages(workflow) if _gates(workflow, row)]
    assert gated and all(row["auto"].startswith(("No", "Conditional")) for row in gated), gated


def test_the_gate_scan_finds_the_known_gates():
    """A reworded annotation cannot empty the checks above."""
    found = {w: {r["number"] + r["letter"] for r in _stages(w) if _gates(w, r)} for w in WORKFLOWS}
    assert found["skf-test-skill"] == set()
    assert {"2", "3", "4", "5", "6"} <= found["skf-analyze-source"]
    assert {"1", "4"} <= found["skf-export-skill"]
    assert {"1", "3c", "3d"} <= found["skf-create-skill"]
    assert found["skf-setup"] == {"3"}
    assert {"1", "4", "9"} <= found["skf-campaign"]
