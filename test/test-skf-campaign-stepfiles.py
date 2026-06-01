"""Structural linter for skf-campaign step files.

The bulk of the campaign workflow lives in LLM-consumed markdown step files,
which carry real logic (state transitions, stage numbering, file references)
but have no unit coverage beyond chain-reachability. The two HIGH-severity
findings of Epic 4 both lived in this layer:

  - step-06 was missing the pending->active state transition (4.7-H1)
  - step-06 hardcoded a batch-file path not declared in frontmatter (4.7-M1)
  - step-06/07 omitted the current_stage update in RULES, breaking resume (4.7-M2)

This linter encodes those lessons as deterministic assertions so the class of
bug is caught by `npm test`, not only by adversarial review.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCES_DIR = REPO_ROOT / "src" / "skf-campaign" / "references"

# Numbered pipeline step files (step-01-*.md … step-11-*.md). Routing/reference
# files (step-resume.md, health-check.md, campaign-directive-spec.md) are excluded.
STEP_FILES = sorted(
    p for p in REFERENCES_DIR.glob("step-*.md") if re.match(r"step-\d+-", p.name)
)

# Tokens ending in "File" are frontmatter-declared path variables; config
# variables (communication_language, headless_mode, project-root, …) are not.
FILE_VAR_RE = re.compile(r"\{([a-zA-Z]+File)\}")
SECTION_PARAGRAPH_RE = re.compile(r"^### §(\d+)\b")
SECTION_NUMERIC_RE = re.compile(r"^### (\d+)\.")


def _frontmatter(text: str) -> dict[str, str]:
    """Parse the top YAML-ish frontmatter block into a flat key->value dict."""
    assert text.startswith("---"), "step file must open with frontmatter"
    end = text.index("---", 3)
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip().strip("'\"")
    return out


def _rules_section(text: str) -> str:
    """Return the body of the ## RULES section (until the next ## heading)."""
    lines = text.splitlines()
    collecting = False
    buf: list[str] = []
    for line in lines:
        if line.strip().startswith("## RULES"):
            collecting = True
            continue
        if collecting and line.startswith("## "):
            break
        if collecting:
            buf.append(line)
    return "\n".join(buf)


def test_step_files_discovered() -> None:
    assert STEP_FILES, "no numbered campaign step files found"


@pytest.mark.parametrize("path", STEP_FILES, ids=lambda p: p.name)
class TestStepFileStructure:
    def test_opens_with_frontmatter(self, path: pathlib.Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---"), f"{path.name} must open with frontmatter"
        assert text.count("---") >= 2, f"{path.name} frontmatter not closed"

    def test_has_step_goal_heading(self, path: pathlib.Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert "## STEP GOAL:" in text, (
            f"{path.name} must declare a '## STEP GOAL:' heading"
        )

    def test_file_vars_are_declared_in_frontmatter(self, path: pathlib.Path) -> None:
        text = path.read_text(encoding="utf-8")
        fm = _frontmatter(text)
        body = text[text.index("---", 3) + 3 :]
        used = set(FILE_VAR_RE.findall(body))
        undeclared = sorted(v for v in used if v not in fm)
        assert not undeclared, (
            f"{path.name} references {undeclared} but they are not declared in "
            f"frontmatter (declared: {sorted(k for k in fm if k.endswith('File'))})"
        )

    def test_next_step_target_exists(self, path: pathlib.Path) -> None:
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        target = fm.get("nextStepFile")
        if target:
            assert (REFERENCES_DIR / target).is_file(), (
                f"{path.name} chains to '{target}' which does not exist"
            )

    def test_rules_declare_current_stage_when_used(
        self, path: pathlib.Path
    ) -> None:
        text = path.read_text(encoding="utf-8")
        # Fires only for steps that *transition* the stage ("set/update
        # current_stage to N"), not the setup step that initializes it
        # ("current_stage: 0" in the freshly constructed state object).
        if "## RULES" not in text:
            return
        if not re.search(r"current_stage`?\s+to\s", text):
            return
        rules = _rules_section(text)
        assert "current_stage" in rules, (
            f"{path.name} transitions current_stage in its body but its RULES "
            f"section does not declare the update — breaks resume resilience "
            f"(cf. 4.7-M2)"
        )

    def test_section_numbering_is_contiguous(self, path: pathlib.Path) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()
        para = [int(m.group(1)) for line in lines if (m := SECTION_PARAGRAPH_RE.match(line))]
        numeric = [int(m.group(1)) for line in lines if (m := SECTION_NUMERIC_RE.match(line))]
        nums = para or numeric
        assert nums, f"{path.name} has no recognizable ### section headings"
        assert nums == list(range(1, len(nums) + 1)), (
            f"{path.name} section numbering is not contiguous from 1: {nums}"
        )
