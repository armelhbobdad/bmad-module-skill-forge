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

import json
import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAMPAIGN_DIR = REPO_ROOT / "src" / "skf-campaign"
REFERENCES_DIR = CAMPAIGN_DIR / "references"

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


# ---------------------------------------------------------------------------
# Prose the campaign scripts and the state schema rely on
# ---------------------------------------------------------------------------


def _step(name: str) -> str:
    return (REFERENCES_DIR / name).read_text(encoding="utf-8")


def _section(text: str, number: int) -> str:
    """The body of `### §<number>` up to the next `##` or `###` heading, or the end."""
    match = re.search(rf"^### §{number}\b[^\n]*\n(.*?)(?=^##|\Z)", text, re.M | re.S)
    assert match, f"no ### §{number} section"
    return match.group(1)


@pytest.mark.parametrize(
    "name, reader",
    [("step-03-pins.md", "pin script"), ("step-05-skill-loop.md", "kickoff script")],
    ids=["step-03", "step-05"],
)
def test_brief_is_read_only_to_confirm_it_parses(name: str, reader: str) -> None:
    body = _section(_step(name), 2)
    assert f"only to confirm it parses (the {reader} reads it directly)" in body
    assert "HALT (exit code 8, `missing-brief`)" in body
    assert "lookup map" not in _step(name)


def test_skill_loop_writes_no_campaign_level_findings() -> None:
    text = _step("step-05-skill-loop.md")
    assert "Propagate Findings" not in text
    assert "campaign-level tracking" not in text
    assert "§6 propagation" not in text
    assert re.search(r"^### §6\b.*Loop Completion$", text, re.M)


@pytest.fixture
def intake() -> str:
    """step-01's section 1, the target intake."""
    return _section(_step("step-01-setup.md"), 1)


class TestSetupOpening:
    def test_one_question_takes_any_target_form(self, intake: str) -> None:
        questions = [line for line in intake.splitlines() if line.startswith("> ")]
        question = (
            "> Share the targets for this campaign in whatever form you have them: a manifest or "
            "`campaign-brief.yaml` path, a pasted list, or repository URLs. Add a campaign name and "
            "a directive or architecture document path if you have them."
        )
        assert questions == [question]
        assert "open with this one question, and ask nothing before it" in intake

    def test_paste_goes_through_the_manifest_parser(self, intake: str) -> None:
        assert "`uv run {manifestScript} <manifest-file>`" in intake
        assert "piped to `uv run {manifestScript} -`" in intake

    def test_paste_takes_the_documented_manifest_format(self, intake: str) -> None:
        # One copy of the line format, in SKILL.md On Activation, not a third one here.
        assert "rewritten as manifest lines in the `--manifest` format On Activation describes" in intake
        assert "name,repo_url,tier,pin" not in intake
        assert "**`--manifest` format:**" in (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_one_draft_then_only_missing_or_ambiguous_fields(self, intake: str) -> None:
        assert "Show the drafted campaign once for correction" in intake
        assert "ask only about what is still missing or ambiguous" in intake
        assert '`tier` `"A"`, `pin` `null`, `depends_on` empty' in intake

    def test_brief_and_manifest_still_imply_headless(self, intake: str) -> None:
        assert "**Headless** (`--brief` and `--manifest` imply it)" in intake

    def test_no_findings_routing_prompt(self) -> None:
        text = _step("step-01-setup.md")
        assert "health_findings_queue" not in text
        assert "improvement queue" not in text


def test_brief_keeps_every_field_of_a_target() -> None:
    # A seeded brief's language or scope hint reaches the kickoff and the Tier B batch.
    body = _section(_step("step-01-setup.md"), 4)
    assert (
        "`targets`: one entry per target with `name`, `repo_url`, `tier`, `pin` and `depends_on`, "
        "plus every other field its source gave it"
    ) in body


class TestHealthCheckChain:
    def test_step_11_carries_no_routing_setting(self) -> None:
        text = _step("step-11-maintenance.md")
        assert "health_findings_queue" not in text
        assert "Findings routing" not in text

    def test_step_11_shows_one_summary_and_chains_once(self) -> None:
        text = _step("step-11-maintenance.md")
        assert (
            'Display, from the §2 result: "**Campaign complete.** {skills_completed} completed, '
            '{skills_failed} failed in {duration}. Report at `{reportFile}`."'
        ) in _section(text, 5)
        assert text.count("**Campaign complete.**") == 1
        assert text.count("Chain to `{nextStepFile}`") == 1

    def test_health_check_step_only_delegates(self) -> None:
        text = _step("health-check.md")
        keys = {k: v for k, v in _frontmatter(text).items() if not k.startswith("#")}
        assert keys == {"nextStepFile": "shared/health-check.md"}
        assert "health_findings_queue" not in text
        assert "consent" not in text
        assert "Load `{nextStepFile}`, read it fully, then execute it." in text

    def test_brief_template_has_no_queue_key(self) -> None:
        brief = yaml.safe_load((CAMPAIGN_DIR / "templates" / "campaign-brief-template.yaml").read_text(encoding="utf-8"))
        assert "health_findings_queue" not in brief


def test_refine_reads_the_report_path_from_state() -> None:
    text = _step("step-09-refine.md")
    assert "read `campaign.verification.report_path` from state" in _section(text, 3)
    invoke = _section(text, 4)
    assert "--vs-report-path <report_path|none>" in invoke
    assert "or `none` when state holds no report path" in invoke
    assert "feasibility-report-" not in text


def test_verify_saves_the_timestamped_report() -> None:
    # report_latest_path is the -latest copy every Verify Stack run rewrites.
    outcome = _section(_step("step-08-verify.md"), 5)
    assert "- `campaign.verification.report_path`: `report_path` from the envelope," in outcome
    assert "`report_latest_path` from the envelope" not in outcome


def test_verify_records_verify_stacks_verdicts() -> None:
    text = _step("step-08-verify.md")
    outcome = _section(text, 5)
    schema = json.loads((CAMPAIGN_DIR / "assets" / "campaign-state-schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["campaign"]["properties"]["verification"]["properties"]["overall_verdict"]["enum"]
    listed = re.search(r"`overall_verdict` from the envelope, one of (.*)$", outcome, re.M).group(1)
    assert re.findall(r"`([A-Z_]+)`", listed) == [v for v in enum if v is not None]
    assert "`campaign.capstone.verified` to `true` when `overall_verdict` is `FEASIBLE`" in outcome
    for token in ("Verified", "Plausible", "Risky", "Blocked"):
        assert f"`{token}`" not in text
