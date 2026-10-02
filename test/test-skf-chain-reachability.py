"""Chain reachability lint for SKF workflow skills.

For each `src/skf-*/` workflow skill, asserts:

1. Every step-file path listed in SKILL.md's Stages table exists on disk.
2. Every `nextStepFile` value in step-file frontmatter resolves to an existing
   file (or to a recognised external target such as `shared/health-check.md`).
3. Every step file (anything with a `nextStepFile` frontmatter key) is
   reachable from the SKILL.md entry set by walking the `nextStepFile` chain.

The entry set is every `references/...md` path SKILL.md mentions — the
Stages table for the main flow, plus conditional entries invoked from
On Activation (e.g. `--batch` loading `references/batch-mode.md` in
skf-quick-skill before the main pipeline starts).

The third check is the safety net: it catches step files that exist on disk
but no chain reaches, the failure mode the dropped "Workflow Rules" trio
only claimed to prevent. `skf-forger` is excluded because it is an agent
persona, not a chained workflow.

Every exit reaches its terminal sequence (#585):

4. Every step file's nextStepFile chain ends at `shared/health-check.md`.
5. Every file that emits a run's success envelope is reachable from SKILL.md,
   and the hook runs once the result files exist: a success emit that writes
   them (`--result-dir`) is followed by the workflow's on_complete in the
   same file, and an emit that writes none (a dry run) calls no hook. Brief
   and setup write no result file and call theirs after the envelope;
   campaign calls its hook before the envelope, as its customize.toml says.
6. Every exit an exit-code table lists is one an envelope carries: a halt
   code is raised by a HALT (or a gate option that stops the run) in a step
   file SKILL.md reaches, and the other codes are finished runs, which the
   success envelope carries; for update, every halt status is raised so.
7. No step file ends the workflow early ("End workflow", "No further steps",
   "Mark workflow complete", "Do not proceed further", "the workflow is
   done"): only the shared health check ends a run. And no Rules block
   forbids every write ahead of a section that writes, unless it names the
   exception (folded in from test-skf-stack-step-rules.py, for every
   workflow).
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import deque

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

WORKFLOW_SKILLS = sorted(
    d.name
    for d in SRC.iterdir()
    if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger"
)

# `nextStepFile` values that resolve outside the skill directory.
# `shared/health-check.md` resolves from the SKF module root (src/ in dev,
# {project-root}/_bmad/skf/ when installed), per the comment in
# `references/health-check.md` step files.
EXTERNAL_TARGETS = {"shared/health-check.md"}


def _read_frontmatter(file_path: pathlib.Path) -> str | None:
    """Return the raw YAML frontmatter block (without the `---` fences), or None."""
    text = file_path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else None


def _next_step(file_path: pathlib.Path) -> str | None:
    """Extract the `nextStepFile` value from a step file's frontmatter."""
    fm = _read_frontmatter(file_path)
    if fm is None:
        return None
    match = re.search(
        r"^nextStepFile:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
        fm,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else None


_REFERENCES_PATH_RE = re.compile(r"\breferences/[A-Za-z0-9_./-]+\.md\b")


def _stages_entries(skill_md: pathlib.Path) -> list[str]:
    """Extract `references/...md` paths from the SKILL.md `## Stages` table only."""
    text = skill_md.read_text(encoding="utf-8")
    section = re.search(
        r"^## Stages\b(.*?)(?=^## )", text, flags=re.MULTILINE | re.DOTALL
    )
    if not section:
        return []
    return _REFERENCES_PATH_RE.findall(section.group(1))


def _skill_md_entries(skill_md: pathlib.Path) -> list[str]:
    """Every `references/...md` path SKILL.md mentions — main flow entries plus
    conditional entries invoked from On Activation (e.g. `--batch` modes)."""
    text = skill_md.read_text(encoding="utf-8")
    return list(dict.fromkeys(_REFERENCES_PATH_RE.findall(text)))


def _resolve_next(current: pathlib.Path, next_value: str) -> pathlib.Path | None:
    """Resolve a nextStepFile value to an absolute path, or None for external targets."""
    if next_value in EXTERNAL_TARGETS:
        return None
    return (current.parent / next_value).resolve()


def _skill_inventory(skill: str) -> dict:
    """Collect Stages entries, step files, and all references/*.md for one skill."""
    skill_dir = SRC / skill
    skill_md = skill_dir / "SKILL.md"
    ref_dir = skill_dir / "references"
    if not skill_md.exists() or not ref_dir.exists():
        return {}
    all_md = sorted(p for p in ref_dir.rglob("*.md"))
    step_files = [p for p in all_md if _next_step(p) is not None]
    return {
        "skill_dir": skill_dir,
        "skill_md": skill_md,
        "stages_entries": _stages_entries(skill_md),
        "skill_md_entries": _skill_md_entries(skill_md),
        "all_md": all_md,
        "step_files": step_files,
    }


@pytest.fixture(scope="module")
def skills() -> dict[str, dict]:
    return {skill: _skill_inventory(skill) for skill in WORKFLOW_SKILLS}


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_stages_entries_exist(skill: str, skills: dict[str, dict]) -> None:
    """Stages-table entries must resolve to existing files under references/."""
    info = skills[skill]
    if not info:
        pytest.skip(f"{skill}: no SKILL.md or references/")
    skill_dir = info["skill_dir"]
    missing = [
        entry for entry in info["stages_entries"] if not (skill_dir / entry).exists()
    ]
    assert not missing, (
        f"{skill}: SKILL.md Stages table references missing files: {missing}"
    )


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_next_step_files_resolve(skill: str, skills: dict[str, dict]) -> None:
    """Every `nextStepFile` value must resolve to an existing file or external target."""
    info = skills[skill]
    if not info:
        pytest.skip(f"{skill}: no SKILL.md or references/")
    broken: list[str] = []
    for step in info["step_files"]:
        nx = _next_step(step)
        if nx is None:
            continue
        if nx in EXTERNAL_TARGETS:
            external = SRC / nx
            if not external.exists():
                broken.append(
                    f"{step.relative_to(info['skill_dir']).as_posix()} → {nx} "
                    f"(external target missing at {external.as_posix()})"
                )
            continue
        resolved = _resolve_next(step, nx)
        if resolved is not None and not resolved.exists():
            broken.append(
                f"{step.relative_to(info['skill_dir']).as_posix()} → {nx} "
                f"(resolves to {resolved.as_posix()})"
            )
    assert not broken, f"{skill}: broken nextStepFile references:\n  " + "\n  ".join(
        broken
    )


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_step_files_reachable_from_skill_md(
    skill: str, skills: dict[str, dict]
) -> None:
    """Every step file must be reachable from a SKILL.md entry via the nextStepFile chain.

    Entry set is every `references/...md` path SKILL.md mentions: Stages-table
    rows plus conditional entries from On Activation (e.g. `--batch` modes).
    """
    info = skills[skill]
    if not info:
        pytest.skip(f"{skill}: no SKILL.md or references/")
    skill_dir = info["skill_dir"]

    reachable: set[pathlib.Path] = set()
    queue: deque[pathlib.Path] = deque()
    for entry in info["skill_md_entries"]:
        path = (skill_dir / entry).resolve()
        if path.exists() and path not in reachable:
            reachable.add(path)
            queue.append(path)

    while queue:
        current = queue.popleft()
        nx = _next_step(current)
        if nx is None or nx in EXTERNAL_TARGETS:
            continue
        next_path = _resolve_next(current, nx)
        if next_path is None or not next_path.exists() or next_path in reachable:
            continue
        reachable.add(next_path)
        queue.append(next_path)

    orphans = [
        step.relative_to(skill_dir).as_posix()
        for step in info["step_files"]
        if step.resolve() not in reachable
    ]
    assert not orphans, (
        f"{skill}: step files not reachable from SKILL.md entries: {orphans}"
    )


# ---------------------------------------------------------------------------
# Every exit reaches the terminal sequence (#585)
# ---------------------------------------------------------------------------


SCHEMA_DIR = SRC / "shared" / "scripts" / "schemas"
NAMED_MD_RE = re.compile(r"(?<![\w/.-])((?:references/)?[\w./-]+\.md)\b")


def _schema_settings() -> dict[str, tuple[dict, dict]]:
    found = {}
    for path in sorted(SCHEMA_DIR.glob("*-result-envelope.v*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        meta = schema["$defs"]["skf-envelope"]["const"]
        found[meta["workflow"]] = (schema, meta)
    return found


SCHEMAS = _schema_settings()

# The variable each workflow's on_complete hook runs from.
HOOKS = {skill: "{onCompleteCommand}" for skill in WORKFLOW_SKILLS}
HOOKS["skf-campaign"] = "{onComplete}"
HOOKS["skf-verify-stack"] = "{workflow.on_complete}"
# Workflows that write no result file and call their hook after the envelope.
NO_RESULT_FILE = {"skf-brief-skill", "skf-setup"}
# Campaign's hook runs after the report and the final state write, before
# the headless envelope (its customize.toml says so).
HOOK_BEFORE_ENVELOPE = {"skf-campaign"}


def _success_emit_re(skill: str) -> re.Pattern:
    """The command that prints a run's success envelope (not a halt's)."""
    if skill == "skf-brief-skill":
        return re.compile(r"\{emitBriefEnvelopeHelper\} emit <<")
    if skill == "skf-setup":
        return re.compile(r"\{emitEnvelopeHelper\} emit --run-dir")
    return re.compile(rf"\{{emitEnvelopeHelper\}} emit --workflow {re.escape(skill)}\b")


def _reachable(skill: str) -> set[pathlib.Path]:
    """SKILL.md, the files it names, their nextStepFile chains and every
    file a reachable file loads by name."""
    skill_dir = SRC / skill
    seen = {(skill_dir / "SKILL.md").resolve()}
    queue = deque(seen)
    while queue:
        current = queue.popleft()
        text = current.read_text(encoding="utf-8")
        names = set(NAMED_MD_RE.findall(text))
        nx = _next_step(current) if current.name != "SKILL.md" else None
        if nx and nx not in EXTERNAL_TARGETS:
            names.add(nx)
        for name in names:
            for base in (current.parent, skill_dir, skill_dir / "references"):
                candidate = (base / name).resolve()
                if candidate.is_file() and skill_dir.resolve() in candidate.parents and candidate not in seen:
                    seen.add(candidate)
                    queue.append(candidate)
    return seen


def _step_files(skill: str) -> list[pathlib.Path]:
    return [SRC / skill / "SKILL.md", *sorted((SRC / skill / "references").rglob("*.md"))]


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_every_step_chain_ends_at_the_shared_health_check(skill: str, skills: dict[str, dict]) -> None:
    info = skills[skill]
    dead_ends = []
    for step in info["step_files"]:
        current, seen = step.resolve(), set()
        while True:
            nx = _next_step(current)
            if nx in EXTERNAL_TARGETS:
                break
            if nx is None or current in seen:
                dead_ends.append(f"{step.relative_to(info['skill_dir']).as_posix()} stops at {current.name}")
                break
            seen.add(current)
            current = _resolve_next(current, nx)
            if not current.exists():
                dead_ends.append(f"{step.relative_to(info['skill_dir']).as_posix()} names a missing {nx}")
                break
    assert not dead_ends, f"{skill}: chains that never reach shared/health-check.md: {dead_ends}"


def _success_emits(skill: str):
    """(file, the emit's line, the text after it) for each success emit."""
    pattern = _success_emit_re(skill)
    for path in sorted((SRC / skill / "references").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line = text[match.start():text.find("\n", match.start())]
            yield path, line, text[match.end():], text[:match.start()]


SUCCESS_EMITS = [(skill, path, line) for skill in WORKFLOW_SKILLS for path, line, _, _ in _success_emits(skill)]


def test_every_workflow_emits_a_success_envelope():
    assert sorted({skill for skill, _, _ in SUCCESS_EMITS}) == WORKFLOW_SKILLS


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_every_success_emit_is_reachable(skill: str) -> None:
    reachable = _reachable(skill)
    stray = sorted({path.relative_to(SRC / skill).as_posix() for path, _, _, _ in _success_emits(skill)
                    if path.resolve() not in reachable})
    assert not stray, f"{skill}: no stage reaches the success emit in {stray}"


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_the_hook_runs_once_the_result_files_exist(skill: str) -> None:
    hook = HOOKS[skill]
    wrong = []
    for path, line, after, before in _success_emits(skill):
        where = path.relative_to(SRC / skill).as_posix()
        if skill in HOOK_BEFORE_ENVELOPE:
            if hook in after or (hook not in before and "complete: true" not in before[-600:]):
                wrong.append(f"{where}: campaign's hook must run before its envelope")
        elif "--result-dir" in line or skill in NO_RESULT_FILE:
            if hook not in after:
                wrong.append(f"{where}: no {hook} after the emit that writes the result files")
        elif hook in after:
            wrong.append(f"{where}: an emit that writes no result file (a dry run) is followed by {hook}")
    assert not wrong, "\n".join(wrong)


def _halt_lines(skill: str) -> list[str]:
    """Lines of reachable step files, outside tables, that stop a run: a
    HALT, or an exit code a gate option or a degraded finish names ("stop
    the campaign with exit code 13")."""
    reachable = _reachable(skill)
    return [line for path in _step_files(skill) if path.resolve() in reachable
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("|") and re.search(r"\bHALT\b|\bexit code\b", line)]


def _token(value: str) -> re.Pattern:
    return re.compile(rf"(?<![\w-]){re.escape(value)}(?![\w-])")


@pytest.mark.parametrize("skill", [s for s in WORKFLOW_SKILLS if SCHEMAS[s][1].get("exit_codes")])
def test_every_halt_exit_code_is_raised_by_a_reachable_step(skill: str) -> None:
    codes = SCHEMAS[skill][1]["exit_codes"]
    lines = _halt_lines(skill)
    unraised = []
    for code in sorted(set(codes.values())):
        reasons = [r for r, c in codes.items() if c == code]
        if not any(_token(r).search(line) for line in lines for r in reasons) and not any(
                re.search(rf"\bexit(?: code)?\s*\**\s*{code}\b", line) for line in lines):
            unraised.append(f"exit {code} ({', '.join(reasons)})")
    assert not unraised, f"{skill}: no reachable HALT raises {unraised}"


def _table_codes(skill: str) -> set[int]:
    """The exit codes the workflow's exit-code tables list (not a helper's own
    table), or its contract's Exit codes row ("0 for a finished brief; at a
    HARD HALT 2 (...), 3 (...)") where it keeps no table."""
    codes = set()
    for path in _step_files(skill):
        for row in path.read_text(encoding="utf-8").splitlines():
            if row.startswith("| **Exit codes** |"):
                codes.update(int(n) for n in re.findall(r"\b(\d+) (?:\(|for\b)", row))
    for path in _step_files(skill):
        if path.name == "step-shape-detect.md":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^\|\s*Code\s*\|\s*Meaning\b", line):
                for row in lines[i + 2:]:
                    if not row.startswith("|"):
                        break
                    cell = row.strip("|").split("|")[0].strip()
                    if cell.isdigit():
                        codes.add(int(cell))
    return codes


@pytest.mark.parametrize("skill", [s for s in WORKFLOW_SKILLS if SCHEMAS[s][1].get("exit_codes")])
def test_every_exit_a_table_lists_reaches_an_envelope(skill: str) -> None:
    """A table's halt code is one a HALT raises (above); every other code is
    a finished run's, which the success envelope carries."""
    schema, meta = SCHEMAS[skill]
    table = _table_codes(skill)
    allowed = set(schema["properties"]["exit_code"]["enum"])
    halts = set(meta["exit_codes"].values())
    assert table, f"{skill}: no exit-code table"
    assert table <= allowed, f"{skill}: the table lists exit codes {sorted(table - allowed)} no envelope carries"
    assert halts <= table, f"{skill}: halt exit codes {sorted(halts - table)} are missing from the table"
    assert 0 in table, f"{skill}: the table lists no success exit"


def test_every_update_halt_status_is_raised_by_a_reachable_halt() -> None:
    schema, meta = SCHEMAS["skf-update-skill"]
    statuses = schema["properties"][meta["wrapper"]]["properties"]["status"]["enum"]
    halting = [s for s in statuses if s.startswith("halted-for-") or s == "blocked"]
    text = "\n".join(_halt_lines("skf-update-skill"))
    unraised = [s for s in halting if not _token(s).search(text)]
    assert len(halting) >= 7 and not unraised, f"skf-update-skill: no reachable HALT carries {unraised}"


# An unconditional end of the run, which only the shared health check may
# say. "after the shared health check completes, the workflow is fully done"
# names the terminal step and is not one.
EARLY_END_RE = re.compile(
    r"\bEnd workflow\b|\bNo further steps\b|\bMark workflow complete\b|\bDo not proceed further\b"
    r"|(?<!completes, )\bthe workflow is (?:fully )?(?:done|complete)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_no_step_file_ends_the_workflow_early(skill: str) -> None:
    early = [f"{path.relative_to(SRC / skill).as_posix()}: {m.group(0)!r}"
             for path in _step_files(skill) for m in EARLY_END_RE.finditer(path.read_text(encoding="utf-8"))]
    assert not early, f"{skill}: step files that end the run ahead of its terminal sequence: {early}"


def test_only_the_shared_health_check_ends_the_run():
    shared = (SRC / "shared" / "health-check.md").read_text(encoding="utf-8")
    assert EARLY_END_RE.search(shared), "the shared health check no longer says the workflow is done"


# Rules wording that forbids every write. "Do not modify the refined
# document" names one file, which a step may well leave alone while it
# writes its result files.
BLANKET_NO_WRITE_RE = re.compile(
    r"read-only|do not write or modify|do not modify any|do not write output files|no [^.\n]*file writes",
    re.IGNORECASE,
)
# A Rules line that names what it still allows.
NAMED_EXCEPTION_RE = re.compile(r"\b(?:except|apart from|other than)\b", re.IGNORECASE)
# A write a section runs: an atomic-writer call, a --fix or --write pass, a
# body split, a folder it creates, or the result files an emit writes.
WRITE_OP_RE = re.compile(
    r"\{atomicWriteHelper\}\s+(?:write|stage-dir|commit-dir|flip-link)\b"
    r"|--fix(?![\w-])|--write(?![\w-])|\bsplit-body\b|\bmkdir -p\b|--result-dir(?![\w-])"
)
RULES_RE = re.compile(r"^## (?:Rules|RULES)\s*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
RULES_STEPS = sorted(path for skill in WORKFLOW_SKILLS for path in (SRC / skill / "references").rglob("*.md")
                     if RULES_RE.search(path.read_text(encoding="utf-8")))


def test_the_scan_reads_the_steps_that_write():
    """The no-write check below reads every step with a Rules block, the
    create-stack steps whose rules once forbade their own writes included."""
    stack = SRC / "skf-create-stack-skill" / "references"
    assert {stack / "generate-output.md", stack / "validate.md", stack / "report.md"} <= set(RULES_STEPS)
    assert len(RULES_STEPS) >= 100, len(RULES_STEPS)


@pytest.mark.parametrize("path", RULES_STEPS, ids=lambda p: p.relative_to(SRC).as_posix())
def test_no_blanket_no_write_rule_ahead_of_a_write(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    match = RULES_RE.search(text)
    write = WRITE_OP_RE.search(text[match.end():])
    for line in match.group(1).splitlines():
        forbid = BLANKET_NO_WRITE_RE.search(line)
        if forbid and not NAMED_EXCEPTION_RE.search(line):
            assert write is None, (
                f"{path.relative_to(SRC).as_posix()}: the Rules say {forbid.group(0)!r} but a section runs "
                f"{write.group(0)!r}; name the write in the Rules instead"
            )


@pytest.mark.parametrize("rule", [
    "Do not write or modify any files: report is console output only",
    "Validate structure and completeness, not content quality: validation is read-only",
    "Do not write output files (Step 07)",
    "No user-facing reports, file writes, or result contracts in this step",
])
def test_blanket_rule_pattern_matches_a_no_write_rule(rule: str) -> None:
    assert BLANKET_NO_WRITE_RE.search(rule) and not NAMED_EXCEPTION_RE.search(rule)


@pytest.mark.parametrize("line", [
    "python3 {atomicWriteHelper} commit-dir --target {skill_package}",
    "npx skill-check split-body <skill-dir> --write",
    'uv run {emitEnvelopeHelper} emit --workflow skf-audit-skill --run-dir "{run_dir}" --result-dir "{forge_version}"',
])
def test_write_pattern_matches_a_write(line: str) -> None:
    assert WRITE_OP_RE.search(line)
