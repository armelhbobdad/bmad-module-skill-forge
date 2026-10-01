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
        # One copy of the line format, here beside the parser call that reads it, not in SKILL.md.
        assert "rewritten as manifest lines in the manifest format above" in intake
        assert intake.count("one `name,repo_url,tier,pin` target per line") == 1
        skill_md = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert "**`--manifest` format:**" not in skill_md
        assert "step-01 §1 documents the manifest format" in skill_md

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
    body = _section(_step("step-01-setup.md"), 3)
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
        chain = _section(text, 6)
        assert (
            'When `{headless_mode}` is false, display, from the §2 result: "**Campaign complete.** '
            '{skills_completed} completed, {skills_failed} failed in {duration}. Report at `{reportFile}`."'
        ) in chain
        assert "In headless mode display nothing: the envelope is the run's last line." in chain
        assert text.count("**Campaign complete.**") == 1
        assert text.count("Chain to `{nextStepFile}`") == 1

    def test_step_11_chain_line_names_the_true_terminal_step(self) -> None:
        assert (
            "Chain to `{nextStepFile}`: the health-check step is the true terminal step, so do not stop here "
            "even though the summary reads as final."
        ) in _section(_step("step-11-maintenance.md"), 6)

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


# ---------------------------------------------------------------------------
# Run state: every write goes through campaign-state.py
# ---------------------------------------------------------------------------

STATE_SCRIPT = CAMPAIGN_DIR / "scripts" / "campaign-state.py"
WRITING_STEPS = [p for p in STEP_FILES if p.name != "step-01-setup.md"]
STATE_CALL_RE = re.compile(r"uv run \{stateScript\} ([a-z-]+)([^`\n<]*)")


def _state_parser():
    import importlib.util

    spec = importlib.util.spec_from_file_location("campaign_state_stepfiles", STATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_parser()


@pytest.mark.parametrize("path", STEP_FILES + [REFERENCES_DIR / "step-resume.md"], ids=lambda p: p.name)
class TestRunState:
    def test_state_is_never_written_by_hand(self, path: pathlib.Path) -> None:
        text = path.read_text(encoding="utf-8")
        for gone in ("current ISO-8601", "Backup and write state", "Copy `{stateFile}` to `{backupFile}`",
                     "backup `{stateFile}` to `{backupFile}`", "Backup `{stateFile}` to `{backupFile}`",
                     "copy `{backupFile}` over `{stateFile}`", "Read-only step caveat"):
            assert gone not in text, gone
        assert _frontmatter(text).get("stateScript") == "scripts/campaign-state.py"

    def test_every_step_calls_the_helper(self, path: pathlib.Path) -> None:
        # test-skf-helper-call-contract.py runs each of these calls through the helper's parser.
        assert STATE_CALL_RE.findall(path.read_text(encoding="utf-8")), f"{path.name} names no {{stateScript}} call"


@pytest.mark.parametrize("path", WRITING_STEPS, ids=lambda p: p.name)
def test_stage_is_written_with_its_reason_after_every_gate(path: pathlib.Path) -> None:
    stage = int(path.name[5:7]) - 1
    text = path.read_text(encoding="utf-8")
    rules = _rules_section(text)
    assert f"Write `campaign.current_stage` = {stage} only in this stage's final state write" in rules
    assert "step-resume resumes at `current_stage + 1`" in rules
    assert re.search(rf"uv run \{{stateScript\}} [a-z-]+ [^`\n]*--stage {stage}\b", text), path.name


@pytest.mark.parametrize("path", STEP_FILES + [REFERENCES_DIR / "step-resume.md"], ids=lambda p: p.name)
def test_headings_use_the_colon_separator(path: pathlib.Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### §"):
            assert re.match(r"^### §\d+: \S", line), line


def test_strategy_writes_the_plan_after_its_gate() -> None:
    text = _step("step-02-strategy.md")
    gate = _section(text, 6)
    assert "Plan Confirmation Gate" in re.search(r"^### §6\b.*$", text, re.M).group(0)
    assert "uv run {stateScript} apply-plan --state-file {stateFile} --stage 1" in _section(text, 7)
    assert text.index("### §6") < text.index("apply-plan")
    assert "re-run `campaign` and choose overwrite" in gate
    assert "editing `campaign-brief.yaml` does not reach them" in gate
    assert "edit the campaign brief" not in text


def test_resume_takes_its_point_from_the_helper() -> None:
    text = _step("step-resume.md")
    point = _section(text, 3)
    assert "uv run {stateScript} resume --state-file {stateFile} [--from <skill>]" in point
    assert (
        "whose batch script, `campaign-render-batch.py`, selects the interrupted active Tier B skills together "
        "with the pending ones, so resume resets no status"
    ) in point
    assert "The batch step processes Tier B skills." not in text
    assert "BYPASSES" not in text and "Do not apply the `+1` again" not in text
    assert "uv run {stateScript} recover --state-file {stateFile}" in _section(text, 1)


def test_provenance_hint_sits_above_the_errors() -> None:
    text = _step("step-04-provenance.md")
    assert "show that root-cause line first, above the per-repo errors, never in their place" in _section(text, 4)
    assert "instead of a wall" not in text
    # The step reads the script's fields; how it calls gh is the script's business.
    assert "gh repo view" not in text and "gh api" not in text
    assert "`error_class`" in _section(text, 3)


@pytest.mark.parametrize(
    "name, schema",
    [("step-08-verify.md", "skf-verify-stack-result-envelope.v1.json"),
     ("step-09-refine.md", "skf-refine-architecture-result-envelope.v1.json")],
    ids=["verify", "refine"],
)
def test_sub_skill_envelopes_point_at_their_schema(name: str, schema: str) -> None:
    text = _step(name)
    assert f"`shared/scripts/schemas/{schema}`" in _section(text, 4)
    assert '{"status":"' not in text
    assert (CAMPAIGN_DIR.parent / "shared" / "scripts" / "schemas" / schema).is_file()


def test_refine_keeps_its_reads() -> None:
    invoke = _section(_step("step-09-refine.md"), 4)
    assert "reads `status`, `refined_path`, `gap_count`, `issue_count` and `improvement_count`" in invoke
    outcome = _section(_step("step-09-refine.md"), 5)
    for field in ("refined_path", "gap_count", "issue_count", "improvement_count"):
        assert f"- `campaign.refinement.{field}`: from the envelope" in outcome


def test_maintenance_terminal_sequence() -> None:
    text = _step("step-11-maintenance.md")
    order = [text.index(marker) for marker in (
        "uv run {reportScript}", "set-stage --state-file {stateFile} --stage 10", "{onComplete} --report-path",
        "emit --workflow skf-campaign", "Chain to `{nextStepFile}`")]
    assert order == sorted(order)
    hook = _section(text, 4)
    assert "after the final state write" in hook
    assert "When §2 wrote the report, run `{onComplete} --report-path={reportFile}`" in hook
    assert "run `{onComplete}` without `--report-path`" in hook
    envelope = _section(text, 5)
    assert "Bind `{result_envelope_line}` to the `SKF_CAMPAIGN_RESULT_JSON:` line it prints" in envelope
    assert "do not display it here" in envelope
    assert "SKF_CAMPAIGN_RESULT_JSON: {" not in text
    relay = _step("health-check.md")
    assert "step 11 bound `{result_envelope_line}`" in relay


def test_success_envelope_has_one_definition() -> None:
    contracts = _step("campaign-contracts.md")
    assert "## Campaign Headless Envelope" not in contracts
    assert "SKF_CAMPAIGN_RESULT_JSON: {" not in contracts
    assert "emit-halt --workflow skf-campaign" in contracts
    schema = CAMPAIGN_DIR.parent / "shared" / "scripts" / "schemas" / "skf-campaign-result-envelope.v1.json"
    assert json.loads(schema.read_text(encoding="utf-8"))["$defs"]["skf-envelope"]["const"]["workflow"] == "skf-campaign"
    for name in ("campaign-contracts.md", "step-11-maintenance.md"):
        assert "skf-campaign-result-envelope.v1.json" in _step(name), name
    assert "skf-campaign-result-envelope.v1.json" in (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")


def test_exit_codes_table_matches_the_envelope_schema() -> None:
    schema = json.loads((CAMPAIGN_DIR.parent / "shared" / "scripts" / "schemas"
                         / "skf-campaign-result-envelope.v1.json").read_text(encoding="utf-8"))
    codes = schema["$defs"]["skf-envelope"]["const"]["exit_codes"]
    table = dict(
        (m.group(2), int(m.group(1)))
        for m in re.finditer(r"^\| (\d+)\s+\| ([a-z-]+)\s+\|", _step("campaign-contracts.md"), re.M)
    )
    assert table.pop("success") == 0
    assert table == codes


def test_decision_log_entries_are_typed() -> None:
    contracts = _step("campaign-contracts.md")
    assert "--type <decision|auto|event>" in contracts
    parser = _state_parser()
    log = parser._subparsers._group_actions[0].choices["log"]
    choices = next(a.choices for a in log._actions if a.dest == "type")
    assert tuple(choices) == ("decision", "auto", "event")


# ---------------------------------------------------------------------------
# The Exit Codes table cites sections that exist; the helper's codes are the campaign's
# ---------------------------------------------------------------------------

EXIT_ROW_RE = re.compile(r"^\| (\d+)\s+\| ([a-z-]+)\s+\| (.*) \|$", re.M)
SECTION_REF_RE = re.compile(r"(?P<resume>step-resume)|steps?[- ](?P<nums>\d\d(?:/\d\d)*)|(?P<any>any step)|§(?P<sec>\d+)")


def _cited_sections() -> list[tuple[str, str, int]]:
    """(row meaning, step file, section) for each `step-NN §M` the Raised-by column cites."""
    cited = []
    for match in EXIT_ROW_RE.finditer(_step("campaign-contracts.md")):
        files: list[str] = []
        for token in SECTION_REF_RE.finditer(match.group(3)):
            if token.group("resume"):
                files = ["step-resume.md"]
            elif token.group("nums"):
                files = [next(REFERENCES_DIR.glob(f"step-{num}-*.md")).name for num in token.group("nums").split("/")]
            elif token.group("any"):
                files = []
            else:
                cited.extend((match.group(2), name, int(token.group("sec"))) for name in files)
    return cited


def test_exit_codes_cite_sections_that_exist() -> None:
    cited = _cited_sections()
    assert ("circular-deps", "step-02-strategy.md", 7) in cited
    for meaning, name, number in cited:
        assert re.search(rf"^### §{number}: ", _step(name), re.M), f"{meaning}: {name} has no §{number}"


@pytest.mark.parametrize(
    "meaning, name, number, operation",
    [("circular-deps", "step-02-strategy.md", 7, "apply-plan"),
     ("invalid-pin", "step-03-pins.md", 5, "apply-pins"),
     ("inaccessible-repo", "step-04-provenance.md", 5, "apply-provenance")],
    ids=["plan", "pins", "provenance"],
)
def test_a_refused_write_halts_with_its_stages_code(meaning: str, name: str, number: int, operation: str) -> None:
    code = {"circular-deps": 4, "invalid-pin": 5, "inaccessible-repo": 6}[meaning]
    body = _section(_step(name), number)
    assert f"uv run {{stateScript}} {operation} " in body
    assert f"exit {code}" in body and "exit 2" not in body
    assert (meaning, name, number) in _cited_sections()
    contract = _step("campaign-contracts.md")
    assert f"{code} for a" in contract and f"`{operation}` refuses" in contract


# ---------------------------------------------------------------------------
# One state rule per step; the mechanics live only in the State Contract
# ---------------------------------------------------------------------------

STATE_RULE = (
    "- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the "
    "same code (State Contract in `references/campaign-contracts.md`). A log entry is "
    "`uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`."
)
MECHANICS = ("rotates `{backupFile}`", "writes atomically", "stamps the time", "stamps every time")


@pytest.mark.parametrize("path", WRITING_STEPS, ids=lambda p: p.name)
def test_state_rule_names_the_call_not_the_mechanics(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert STATE_RULE in _rules_section(text).splitlines()
    for phrase in MECHANICS:
        assert phrase not in text, phrase
    assert "backupFile" not in _frontmatter(text)


def test_skill_md_keeps_one_state_rule() -> None:
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert (
        "- Every state write goes through `scripts/campaign-state.py` (State Contract in "
        "`references/campaign-contracts.md`); never edit the state or its `.bak` by hand"
    ) in skill
    assert "writes atomically" not in skill
    assert "`references/` holds the stage-chained step files plus reference specs" in skill


def test_setup_logs_through_the_helper() -> None:
    text = _step("step-01-setup.md")
    assert _frontmatter(text)["decisionLogFile"] == "{campaignWorkspacePath}/_campaign-decision-log.md"
    assert "`uv run {stateScript} log --log-file {decisionLogFile} --type auto --text '<entry>'`" in _rules_section(text)


def test_model_built_text_is_single_quoted() -> None:
    for path in sorted(REFERENCES_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert '--text "' not in text and '--entry "' not in text, path.name


# ---------------------------------------------------------------------------
# HARD HALT payload, a finished campaign's resume, the backup check, overwrite
# ---------------------------------------------------------------------------


def _contract(heading: str) -> str:
    text = _step("campaign-contracts.md")
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 3)
    return text[start:] if end < 0 else text[start:end]


def test_halt_payload_comes_from_the_helper() -> None:
    result = _contract("Result Contract on HARD HALT")
    assert (
        "uv run scripts/campaign-state.py halt-payload --state-file {campaignWorkspacePath}/_campaign-state.yaml "
        "--phase <step slug> --halt-reason <class> <<'SKF_CAMPAIGN_HALT' | "
        "uv run {emitEnvelopeHelper} emit-halt --workflow skf-campaign --target stderr"
    ) in result
    assert "campaign-status.py" not in result and "<completed>" not in result
    # The contract survives compaction without SKILL.md: it names the emitter's path itself.
    assert "`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` when installed" in result
    assert "Exit code 0 is never an error halt" in result
    halt = _state_parser().parse_args(["halt-payload", "--state-file", "s", "--phase", "setup",
                                       "--halt-reason", "invalid-input"])
    assert (halt.phase, halt.halt_reason) == ("setup", "invalid-input")


def test_a_finished_campaign_resumes_to_its_success_line() -> None:
    point = _section(_step("step-resume.md"), 3)
    complete = next(line for line in point.splitlines() if line.startswith("- **`complete: true`:**"))
    assert "which is no error halt: stop with exit code 0" in complete
    assert "uv run {emitEnvelopeHelper} emit --workflow skf-campaign < {resultContextFile}" in complete
    assert '{"status": "success", "skills_completed": <completed>, "skills_failed": <failed>' in complete
    assert "verbatim as the run's last line" in complete
    assert "emit-halt" not in complete
    row = next(m.group(3) for m in EXIT_ROW_RE.finditer(_step("campaign-contracts.md")) if m.group(1) == "0")
    assert "Never an error halt: no `emit-halt`" in row
    rules = _rules_section(_step("step-11-maintenance.md"))
    assert "so a report step cut short before §3 runs again" in rules
    assert "After §3 a resume reports the campaign complete" in rules
    assert "that was cut short runs again" not in rules


def test_resume_halts_a_setup_that_wrote_no_brief() -> None:
    point = _section(_step("step-resume.md"), 3)
    assert "- **`stage` 1 with no `{briefFile}`:**" in point
    assert "HALT (exit code 8, `missing-brief`)" in point
    assert ("missing-brief", "step-resume.md", 3) in _cited_sections()


def test_resume_offers_no_recovery_from_a_newer_backup() -> None:
    text = _step("step-resume.md")
    for gone in ("primary_behind", "--backup-file", "[R]ecover", "[K]eep", "crash during the last write",
                 "crash-during-write"):
        assert gone not in text, gone
    assert "When `uv run {validateScript} --state-file {backupFile}` fails, warn" in _section(text, 2)
    assert "the cause is a hand edit, disk damage, or a state written before v3.0.0" in _section(text, 1)


def test_batch_records_results_only_after_the_record_call() -> None:
    record = _section(_step("step-06-batch.md"), 5)
    blocks = [b.strip() for b in re.findall(r"```\n(.*?)```", record, re.S)]
    assert blocks[0] == "uv run {batchScript} --record <summary_path> --map {batchMapFile} > {batchResultsFile}"
    assert "When that call exits 0, record the results" in record
    assert blocks[1].endswith("--results-file {batchResultsFile} --stage 5")
    assert blocks[2].endswith("--no-results --stage 5")


def test_overwrite_archives_through_the_helper() -> None:
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    call = ("uv run scripts/campaign-state.py archive --state-file {campaignWorkspacePath}/_campaign-state.yaml "
            "--brief-file {campaignWorkspacePath}/campaign-brief.yaml")
    assert call in skill
    assert "log the `archive_dir` it returns (type `decision`)" in skill
    assert "{name}-{timestamp}" not in skill
    archive = _state_parser().parse_args(call.split()[3:])
    assert archive.op == "archive"
