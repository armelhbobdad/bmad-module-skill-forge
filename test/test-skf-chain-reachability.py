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
but no chain reaches — the failure mode the dropped "Workflow Rules" trio
only claimed to prevent. `skf-forger` is excluded because it is an agent
persona, not a chained workflow.
"""

from __future__ import annotations

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
