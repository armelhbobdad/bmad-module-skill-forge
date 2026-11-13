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

#1110: On Activation step 3 checks the template paths it binds, before
Mode Routing and unless the invocation is `campaign status`, and halts with
exit code 2 (`invalid-input`) on one that names no readable file, so a bad
report template no longer surfaces only at stage 10.

#1140: the step files keep each command, its exit branches and the model's
own flags and log lines, not what a helper writes. The Exit Codes table keeps
the code, its meaning and a note; RAISED_BY below indexes where each code is
raised, and the directive spec recognizes only the sections the gate script
parses.

#1141: the skill loop records CS's skill path and kept doc-rot corrections
right after CS, before TS, so nothing after the test reads CS's context; the
strategy view comes from campaign-deps.py --render, and the export, resume
and strategy steps state what to show in one sentence, not a fixed layout.

#1142: customize.toml no longer ships quality_gate_hard (one legal value) or
brief_template_path (no later stage reads the brief template), and neither
name is left in SKILL.md or a reference. Setup's init writes into the brief
only the gate values the seeding brief set and passes no --hard. An overwrite
archives the old campaign in step-01 §0, so Setup's numbering may start at 0,
and `campaign status` names its real exits: 2 for no state, 3 for a state that
fails validation, else 0.

#1143: Setup looks for the architecture document, so Verification and
Refinement never ask for one and skip with a logged event in every run. The
plan gate offers [U]nattended and `campaign resume` takes --unattended, which
let only the skill loop's dependency gate take its headless default. An
interactive run corrects an invalid pin through `set-skill --pin`, and the
headless HALT names the ways out, an interactive `campaign resume` first. Each
failed or skipped skill's reason goes through `set-skill --halt-reason`,
quoted as a log entry is, the dependency gate logs the default it takes in
both branches, and step-03 and step-04 state their halt rule once.
"""

from __future__ import annotations

import json
import pathlib
import re
import shlex
import subprocess
import sys
import tomllib

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
        # A §0 runs before §1 only on some runs (step-01's overwrite archive, #1142).
        start = nums[0] if nums[0] in (0, 1) else 1
        assert nums == list(range(start, start + len(nums))), (
            f"{path.name} section numbering is not contiguous from 0 or 1: {nums}"
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
    # A seeded brief's language or scope hint reaches the kickoff and the Tier B batch:
    # init writes the brief from the parsed targets, so Setup types no YAML.
    setup = _step("step-01-setup.md")
    state = _section(setup, 2)
    # #1142: init writes the brief from the bundled template; no setting swaps it.
    assert "--brief-out {briefFile} [--notes '<operator notes>']" in state
    assert "--brief-template" not in setup and "{templateFile}" not in setup
    assert "templateFile" not in _frontmatter(setup)


def test_setup_logs_each_gate_value_the_brief_set() -> None:
    # #1142: the new brief keeps only the gate values the seeding brief set, and Setup logs each one from
    # init's `gate_from_brief`, so the decision log says which values customize.toml did not decide.
    state = " ".join(_section(_step("step-01-setup.md"), 2).split())
    assert "the new brief keeps only those values" in state
    call = ("uv run {stateScript} log --log-file {decisionLogFile} --type event --text "
            "'quality_gate.<key> <value> comes from the campaign brief, not customize.toml'")
    assert f"After `init` exits 0, log one entry per key of its `gate_from_brief`: `{call}`." in state


class TestHealthCheckChain:
    def test_step_11_carries_no_routing_setting(self) -> None:
        text = _step("step-11-maintenance.md")
        assert "health_findings_queue" not in text
        assert "Findings routing" not in text

    def test_step_11_shows_one_summary_and_chains_once(self) -> None:
        text = _step("step-11-maintenance.md")
        chain = _section(text, 6)
        assert (
            'When `{headless_mode}` is false, display, from the §2 result: "**Campaign summary:** '
            '{skills_completed} completed, {skills_failed} failed in {duration}. Report at `{reportFile}`."'
        ) in chain
        assert "In headless mode display nothing: the envelope is the run's last line." in chain
        assert text.count("**Campaign summary:**") == 1
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


@pytest.mark.parametrize(
    "name, section, code, line, field, stage, skip",
    [
        ("step-07-capstone.md", 4, "SS", "SKF_STACK_RESULT_JSON", "capstone", 6, "§2 found no skill to compose"),
        ("step-08-verify.md", 5, "VS", "SKF_VERIFY_STACK_RESULT_JSON", "verification", 7, "§3 skipped VS"),
        ("step-09-refine.md", 5, "RA", "SKF_REFINE_ARCHITECTURE_RESULT_JSON", "refinement", 8, "§3 skipped RA"),
    ],
    ids=["step-07", "step-08", "step-09"],
)
def test_a_sub_skill_with_no_line_is_recorded_no_result(
    name: str, section: int, code: str, line: str, field: str, stage: int, skip: str
) -> None:
    # #890: a run that printed no result line has no result to read (output-contract-schema.md), so the
    # stage is recorded failed with `no-result`; `--no-<field>` is only for a stage skipped on purpose.
    text = _step(name)
    invoke, record = _section(text, section - 1), _section(text, section)
    # A HARD HALT prints the sub-skill's `error` line on stderr: it is read, never taken for no line.
    assert f"Keep the `{line}` line it prints for §{section}" in invoke
    assert f"on stdout, or on stderr when {code} halts." in invoke
    assert "prints on stdout for" not in invoke
    call = "uv run {stateScript} set-campaign --state-file {stateFile}"
    assert (f"When {skip}, record no {field} instead: `{call} --no-{field} --stage {stage}`.") in record
    assert (f"When {code} printed no `{line}` line on stdout or stderr, there is no result to read, whatever its "
            f"exit code: record it with `{call} --no-result {field} --stage {stage}`, log \"no {line} line "
            f"(exit <code>)\" with {code}'s exit code (type `event`), and go on.") in record
    if code != "SS":
        # The failure bullet covers a line that failed, never a run with no line (an empty heredoc halts).
        assert (f"**On {code} failure** (a line whose `status` is `error` or whose `exit_code` is non-zero): the "
                f"helper sets `campaign.{field}` to `null` and names it in `not_recorded`; log that line's "
                "`exit_code` and `halt_reason` (type `event`).") in record
        assert "a non-zero exit, an `error` envelope" not in record
        assert "from the envelope or stderr" not in record
    assert text.count(f"--no-{field}") == 1
    output = text.split("## OUTPUT", 1)[1]
    assert '"skipped"' in output and "\"failed (<halt_reason>)\" from the helper's `not_recorded` row" in output
    # The fallback campaign-report.py's export cell uses: the halt reason, else the exit code, else none.
    assert (f"That row's `halt_reason` fills it (`failed (no-result)` when {code} printed no line); when that is "
            "null, show `failed (exit <exit_code>)`, or `failed (no exit code)` when the exit code is null too.") in output
    for gone in ("printed no envelope, or", "no result envelope", "or no envelope"):
        assert gone not in text, gone
    assert "\u2014" not in text and "\u2013" not in text


@pytest.mark.parametrize(
    "name, section, code, line, field, stage, skip",
    [
        ("step-07-capstone.md", 4, "SS", "SKF_STACK_RESULT_JSON", "capstone", 6, "§2 found no skill to compose"),
        ("step-08-verify.md", 5, "VS", "SKF_VERIFY_STACK_RESULT_JSON", "verification", 7, "§3 skipped VS"),
        ("step-09-refine.md", 5, "RA", "SKF_REFINE_ARCHITECTURE_RESULT_JSON", "refinement", 8, "§3 skipped RA"),
    ],
    ids=["step-07", "step-08", "step-09"],
)
def test_a_sub_skill_with_an_unparseable_line_is_recorded_result_unreadable(
    name: str, section: int, code: str, line: str, field: str, stage: int, skip: str
) -> None:
    # #905: the helper records a line it cannot read as failed with `result-unreadable` and exits 0, so the
    # stage logs it and goes on, as step-10 does for an Export line, instead of halting on exit 2.
    text = _step(name)
    record = _section(text, section)
    sentence = (f"When the helper's `not_recorded` row gives the halt reason `result-unreadable` ({code} printed a "
                "line that does not parse, or one with no `status` or `exit_code`), log "
                f"\"unparseable {line} line\" (type `event`) and go on.")
    assert sentence in record
    # It follows the no-result sentence, and names no flag: the helper sets the reason, the step only logs it.
    no_result = f"`uv run {{stateScript}} set-campaign --state-file {{stateFile}} --no-result {field} --stage {stage}`"
    assert record.index(no_result) < record.index(sentence)
    assert text.count(f"--no-{field}") == 1
    assert text.count("result-unreadable") == 1
    for explicit in ('"halt_reason": "result-unreadable"', "--halt-reason result-unreadable"):
        assert explicit not in text, explicit
    assert "\u2014" not in text and "\u2013" not in text


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
    assert "It returns the stage to resume, its `step_file` and a `reason`. Then:" in point
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


def test_maintenance_terminal_sequence() -> None:
    text = _step("step-11-maintenance.md")
    order = [text.index(marker) for marker in (
        "uv run {reportScript}", "set-stage --state-file {stateFile} --stage 10", "{onComplete} --report-path",
        "emit --workflow skf-campaign", "Chain to `{nextStepFile}`")]
    assert order == sorted(order)
    hook = _section(text, 4)
    assert "after the final state write" in hook
    assert 'When §2 wrote the report, run `{onComplete} --report-path="{reportFile}"`' in hook
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
# Each exit code is raised where this index says; the helper's codes are the campaign's
# ---------------------------------------------------------------------------

EXIT_ROW_RE = re.compile(r"^\| (\d+)\s+\| ([a-z-]+)\s+\| (.*) \|$", re.M)

# Where each code is raised, as (meaning, step file, section). The Exit Codes table the model reads on every
# HALT keeps only the code, its meaning and a note that changes a move (#1140), so the per-step index lives here,
# where test_exit_codes_cite_sections_that_exist keeps it true. Codes 3 (any step's §1 and any refused state
# write) and 12 (any interactive gate) have no one section to cite. Three sites fall outside this (meaning, step
# file, section) shape: SKILL.md On Activation step 3 (exit 2, pinned by
# test_activation_checks_the_templates_before_mode_routing), SKILL.md Mode Routing 4, `campaign status` (exits 2
# and 3, pinned by test_campaign_status_names_its_real_exits) and step-11's terminal success (exit 0).
RAISED_BY: list[tuple[str, str, int]] = [
    ("success", "step-resume.md", 3),
    ("invalid-input", "step-01-setup.md", 0),
    ("invalid-input", "step-01-setup.md", 1),
    ("invalid-input", "step-01-setup.md", 2),
    ("invalid-input", "step-02-strategy.md", 3),
    ("invalid-input", "step-03-pins.md", 3),
    ("invalid-input", "step-04-provenance.md", 3),
    ("invalid-input", "step-06-batch.md", 3),
    ("invalid-input", "step-05-skill-loop.md", 4),
    ("invalid-input", "step-05-skill-loop.md", 5),
    ("invalid-input", "step-07-capstone.md", 2),
    ("invalid-input", "step-10-export.md", 3),
    ("invalid-input", "step-resume.md", 1),
    ("invalid-input", "step-resume.md", 3),
    ("circular-deps", "step-02-strategy.md", 4),
    ("circular-deps", "step-02-strategy.md", 7),
    ("invalid-pin", "step-03-pins.md", 4),
    ("invalid-pin", "step-03-pins.md", 5),
    ("inaccessible-repo", "step-04-provenance.md", 4),
    ("inaccessible-repo", "step-04-provenance.md", 5),
    ("dependency-deadlock", "step-05-skill-loop.md", 4),
    ("missing-brief", "step-03-pins.md", 2),
    ("missing-brief", "step-04-provenance.md", 2),
    ("missing-brief", "step-05-skill-loop.md", 2),
    ("missing-brief", "step-05-skill-loop.md", 4),
    ("missing-brief", "step-05-skill-loop.md", 5),
    ("missing-brief", "step-06-batch.md", 3),
    ("missing-brief", "step-resume.md", 3),
    ("corrupt-state", "step-resume.md", 1),
    ("report-failure", "step-11-maintenance.md", 2),
    ("export-cancelled", "step-10-export.md", 4),
    ("dependency-blocked", "step-05-skill-loop.md", 4),
]

# The rows whose Note changes what a caller does next; every other row leaves it empty.
NOTED_EXITS = {"success", "invalid-pin", "dependency-deadlock", "report-failure", "export-cancelled",
               "user-cancelled", "dependency-blocked"}


def _cited_sections() -> list[tuple[str, str, int]]:
    """(meaning, step file, section) for each section that raises an exit code."""
    return RAISED_BY


def _exit_table() -> dict[str, tuple[int, str]]:
    """Each Exit Codes row's meaning, with its code and its Note."""
    rows = EXIT_ROW_RE.finditer(_step("campaign-contracts.md"))
    return {m.group(2): (int(m.group(1)), m.group(3).strip()) for m in rows}


def _section_with_subsections(text: str, number: int) -> str | None:
    """The body of `### §<number>` up to the next `##` or `###` heading, its `####` subsections included."""
    match = re.search(rf"^### §{number}: [^\n]*\n(.*?)(?=^#{{2,3}} |\Z)", text, re.M | re.S)
    return match.group(1) if match else None


def test_exit_codes_cite_sections_that_exist() -> None:
    table = _exit_table()
    cited = _cited_sections()
    assert len(set(cited)) == len(cited)
    assert {meaning for meaning, _, _ in cited} == set(table) - {"invalid-state", "user-cancelled"}
    for meaning, name, number in cited:
        body = _section_with_subsections(_step(name), number)
        assert body is not None, f"{meaning}: {name} has no §{number}"
        code = table[meaning][0]
        assert re.search(rf"\bexit (?:code )?{code}\b", body), f"{meaning}: {name} §{number} names no exit {code}"
    # The table carries no per-step index: a Note only qualifies how the caller treats the code.
    for meaning, (code, note) in table.items():
        assert not re.search(r"step|§|SKILL\.md", note, re.I), f"{code} {meaning}: {note}"
    assert {meaning for meaning, (_, note) in table.items() if note} == NOTED_EXITS
    assert "Every HARD HALT exits with one of these codes:" in _step("campaign-contracts.md")


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
        for flag in ("--text", "--entry", "--halt-reason", "--pin"):
            assert f'{flag} "' not in text, (path.name, flag)


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


def test_resume_offers_no_recovery_from_a_newer_backup() -> None:
    text = _step("step-resume.md")
    for gone in ("primary_behind", "--backup-file", "[R]ecover", "[K]eep", "crash during the last write",
                 "crash-during-write"):
        assert gone not in text, gone
    assert "When `uv run {validateScript} --state-file {backupFile}` fails, warn" in _section(text, 2)
    assert "the cause is a hand edit, disk damage, or a state written before v3.0.0" in _section(text, 1)
    # #1140: no `.bak` is the normal state after Setup, so only a backup that fails validation is warned about.
    assert re.search(r"^### §2: Backup Check$", text, re.M)
    assert ("Skip this check when §1 recovered from the backup or `{backupFile}` does not exist. When "
            "`uv run {validateScript} --state-file {backupFile}` fails, warn \"Backup file fails validation: cannot "
            "use for recovery.\" and continue with the primary.") in _section(text, 2)
    assert "No backup file found" not in text


def test_batch_records_results_only_after_the_record_call() -> None:
    record = _section(_step("step-06-batch.md"), 5)
    blocks = [b.strip() for b in re.findall(r"```\n(.*?)```", record, re.S)]
    assert blocks[0] == "uv run {batchScript} --record <summary_path> --map {batchMapFile} > {batchResultsFile}"
    assert "When that call exits 0, record the results" in record
    assert blocks[1].endswith("--results-file {batchResultsFile} --stage 5")
    assert blocks[2].endswith("--no-results --stage 5")


def test_batch_reads_the_batch_file_when_no_summary_was_written() -> None:
    """#904: with summary_path null, QS's batch.jsonl takes the summary's place in the §5 record call."""
    execute = _section(_step("step-06-batch.md"), 4)
    for token in ("`summary_path` is null", "`batch_file`", "as `<summary_path>`",
                  "`summary_write_failed` warning, type `event`"):
        assert token in execute, token
    record = _section(_step("step-06-batch.md"), 5)
    assert "uv run {batchScript} --record <summary_path> --map {batchMapFile}" in record


def test_overwrite_archives_through_the_helper() -> None:
    # #1142: only Setup uses the archive, so its call, log and brief-path rule live in step-01 §0, not SKILL.md.
    setup = _step("step-01-setup.md")
    assert re.search(r"^### §0: Archive the Previous Campaign$", setup, re.M)
    assert setup.index("### §0:") < setup.index("### §1:")
    archive = " ".join(_section(setup, 0).split())
    assert "Run this section only when `{stateFile}` or `{stateFile}.bak` exists; otherwise start at §1." in archive
    call = "uv run {stateScript} archive --state-file {stateFile} --brief-file {briefFile}"
    assert f"`{call}`" in archive
    parsed = _state_parser().parse_args(call.split()[3:])
    assert (parsed.op, parsed.state_file, parsed.brief_file) == ("archive", "{stateFile}", "{briefFile}")
    assert "log the `archive_dir` it returns (type `decision`)" in archive
    assert "`uv run {stateScript} log --log-file {decisionLogFile} --type decision --text '" in archive
    # A `write-failed` exit can come after the state moved, so the HALT claims nothing about what moved.
    assert "On exit 2, HALT (exit code 2, `invalid-input`) with its `error`." in archive
    assert "nothing was moved" not in archive
    assert ("A brief path that names `{briefFile}`, from `--brief` or from §1's answer, is read from `archive_dir` "
            "instead.") in archive
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "campaign-state.py archive" not in skill and "{name}-{timestamp}" not in skill
    route = next(line for line in skill.splitlines() if line.startswith("3. **`campaign`** (state exists)"))
    assert "prompt **resume** (via `references/step-resume.md`) or **overwrite**" in route
    assert "`references/step-01-setup.md`, whose §0 archives the old campaign first" in route
    assert ("**GATE [default: resume]**: in headless mode, default to **resume** (never silently clobber); "
            "archive-and-overwrite only when `--brief`/`--manifest` explicitly seeds a new campaign.") in route
    contracts = _step("campaign-contracts.md")
    assert re.search(r"^\| `archive` \| step-01 §0 \(overwrite\) \|", contracts, re.M)


def test_campaign_status_names_its_real_exits() -> None:
    """#1142: Mode Routing 4 halts with exit 2 when no state exists and exit 3 when it fails validation (the
    load rule's code), pointing to `campaign resume` when a backup exists, and never names exit 9."""
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    route = next(line for line in skill.splitlines() if line.startswith("4. **`campaign status`** (read-only)"))
    assert ("A missing state says no campaign has started and HALTs (exit code 2, `invalid-input`); a failed "
            "validation HALTs (exit code 3, `invalid-state`) and, when `_campaign-state.yaml.bak` exists, points to "
            "`campaign resume`, which can recover it; each HALT is at phase `status`. Otherwise exit 0.") in route
    assert not re.search(r"\b9\b", route)
    table = _exit_table()
    assert (table["invalid-input"][0], table["invalid-state"][0]) == (2, 3)
    assert "HALT (exit code 3, `invalid-state`) on non-zero" in skill
    # The user doc names the same exits.
    [doc] = [line for line in (REPO_ROOT / "docs" / "campaign.md").read_text(encoding="utf-8").splitlines()
             if line.startswith("- **`campaign status`**")]
    for token in ("With no `_campaign-state.yaml` it says no campaign has started and stops with exit code 2 "
                  "(`invalid-input`).", "A state that fails validation stops it with exit code 3 (`invalid-state`)",
                  "when `_campaign-state.yaml.bak` exists it points to `campaign resume`"):
        assert token in doc, token


def test_the_removed_customize_keys_are_named_nowhere() -> None:
    """#1142: `quality_gate_hard` had one legal value and `brief_template_path` swapped a template no later stage
    reads, so neither ships, no binding or step reads either one, and the user docs offer neither."""
    texts = {"customize.toml": (CAMPAIGN_DIR / "customize.toml").read_text(encoding="utf-8"),
             "SKILL.md": (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")}
    texts.update({f"references/{p.name}": p.read_text(encoding="utf-8") for p in sorted(REFERENCES_DIR.glob("*.md"))})
    texts["docs/campaign.md"] = (REPO_ROOT / "docs" / "campaign.md").read_text(encoding="utf-8")
    for name, text in texts.items():
        for gone in ("quality_gate_hard", "brief_template_path", "{qualityGateHard}", "{briefTemplatePath}"):
            assert gone not in text, f"{name}: {gone}"
    workflow = tomllib.loads(texts["customize.toml"])["workflow"]
    assert "quality_gate_hard" not in workflow and "brief_template_path" not in workflow


# ---------------------------------------------------------------------------
# #1110: the template overrides are checked as the campaign starts
# ---------------------------------------------------------------------------

TEMPLATE_KEYS = {"reportTemplatePath": "report_template_path", "kickoffTemplatePath": "kickoff_template_path"}


def test_activation_checks_the_templates_before_mode_routing() -> None:
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    step_3 = skill[skill.index("3. **Resolve workflow customization.**"):skill.index("4. **Parse CLI overrides**")]
    flat = " ".join(step_3.split())
    check = flat.index("Unless the invocation is `campaign status`, check now that")
    halt = flat.index("HALT (exit code 2, `invalid-input`) before Mode Routing")
    emitter = flat.index("- `{emitEnvelopeHelper}` ←")
    facts = flat.index("Load `workflow.persistent_facts`")
    assert emitter < check < halt < facts
    assert skill.index("4. **Parse CLI overrides**") < skill.index("## Mode Routing")
    for variable, key in TEMPLATE_KEYS.items():
        binding = f"- `{{{variable}}}` ← `workflow.{key}` if non-empty, else `templates/"
        assert binding in flat and flat.index(binding) < check, key
        assert f"`{{{variable}}}`" in flat[check:halt], variable
    assert ("Bind each path as the path it names: `{forge_data_folder}` and `{project-root}` replaced by their "
            "values, a bare path") in flat
    assert "taken from `{skill-root}`" in flat
    assert "are readable files (`test -f`, `test -r`)" in flat[check:halt]
    assert ("\"`<key>` names `<path>`, which is not a readable file. Point it at your copy in "
            "`{project-root}/_bmad/custom/skf-campaign.toml` or `.user.toml`, or re-install SKF when it is a bundled "
            "template.\"") in flat
    assert ("with the error envelope of `references/campaign-contracts.md` at phase `activation` and with every "
            "message displayed as its halt message: nothing is written") in flat
    # A seeded run is headless from step 4 on, so its activation halt still prints the envelope line.
    assert "A run given `--brief` or `--manifest` is headless for this HALT, since step 4 makes it so." in flat
    assert "If `--brief` or `--manifest` is set, force `{headless_mode} = true`" in skill
    events = " ".join(_step("campaign-contracts.md").split())
    assert ("For the non-numbered routing/terminal steps (`resume`, `health-check`), and for a HARD HALT in SKILL.md "
            "On Activation (slug `activation`), emit `\"stage\":null` with the slug.") in events
    assert ("`activation_steps_append` runs at step 5, after step 3's template check has passed and step 4 has "
            "parsed the CLI overrides.") in flat


def test_each_bundled_template_passes_the_activation_check() -> None:
    """The defaults customize.toml ships name the files the check finds."""
    workflow = tomllib.loads((CAMPAIGN_DIR / "customize.toml").read_text(encoding="utf-8"))["workflow"]
    for key in TEMPLATE_KEYS.values():
        assert (CAMPAIGN_DIR / workflow[key]).is_file(), key


def test_the_activation_halt_prints_an_exit_2_line_and_writes_nothing(tmp_path: pathlib.Path) -> None:
    """Before Setup there is no workspace: the contract's halt-payload and emitter commands, at the phase step 3
    names, print a valid exit-2 line, and nothing is created."""
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    step_3 = " ".join(skill[skill.index("3. **Resolve workflow customization.**"):
                            skill.index("4. **Parse CLI overrides**")].split())
    phase = re.search(r"HALT \(exit code 2, `invalid-input`\) before Mode Routing, with the error envelope of "
                      r"`references/campaign-contracts.md` at phase `([a-z-]+)`", step_3)
    assert phase, "step 3 names no phase for its template halt"
    workspace = tmp_path / "forge-data" / "_campaign"
    message = "`kickoff_template_path` names `/srv/house/kickoff.md`, which is not a readable file."
    payload = subprocess.run(
        [sys.executable, str(STATE_SCRIPT), "halt-payload", "--state-file", str(workspace / "_campaign-state.yaml"),
         "--phase", phase.group(1), "--halt-reason", "invalid-input"],
        input=message + "\n", capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert payload.returncode == 0, payload.stderr
    emitter = CAMPAIGN_DIR.parent / "shared" / "scripts" / "skf-emit-result-envelope.py"
    line = subprocess.run([sys.executable, str(emitter), "emit-halt", "--workflow", "skf-campaign", "--target",
                           "stderr"], input=payload.stdout, capture_output=True, text=True, encoding="utf-8",
                          timeout=60)
    assert line.returncode == 0, line.stdout + line.stderr
    prefix, _, body = (line.stdout + line.stderr).strip().partition(": ")
    assert prefix == "SKF_CAMPAIGN_RESULT_JSON"
    envelope = json.loads(body)
    assert (envelope["exit_code"], envelope["halt_reason"], envelope["phase"]) == (2, "invalid-input", "activation")
    assert envelope["error"]["message"] == message
    assert not (tmp_path / "forge-data").exists()


# ---------------------------------------------------------------------------
# #1140: step text holds the command, its exit branches and the model's own flags and log lines
# ---------------------------------------------------------------------------


def test_no_reference_declares_the_unused_schema_path() -> None:
    for path in sorted(REFERENCES_DIR.glob("*.md")):
        assert "stateSchemaFile" not in path.read_text(encoding="utf-8"), path.name


@pytest.mark.parametrize(
    "name, gone",
    [("step-01-setup.md", ["### §3", "a duplicate name, a brief `pin`", "so the state takes its targets",
                           "The helper settles and checks the gate", "`repo_url` lives only in the brief"]),
     ("step-02-strategy.md", ["Kahn"]),
     ("step-03-pins.md", ["`resolved_ref` wherever the two differ"]),
     ("step-05-skill-loop.md", ["[F]orce one", "[S]kip one", "Deadlock detection",
                                "In execution order every dependency comes first", "X.Y.Z", "exclusion windows"]),
     ("step-06-batch.md", ["stamping `started_at` from the clock", "A `completed` result sets the skill"]),
     ("step-07-capstone.md", ["derived artifact", "From a `success` envelope it sets"]),
     ("step-08-verify.md", ["§5 reads", "**On success**", "It also sets `campaign.capstone.verified`"]),
     ("step-09-refine.md", ["§5 reads", "**On success**"]),
     ("step-11-maintenance.md", ["`export_verdicts`", "`stage_outcomes` (whether"]),
     ("step-resume.md", ["campaign-render-batch.py", "`terminal-cap`", "No backup file found"])],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_step_text_lists_no_helper_internals(name: str, gone: list[str]) -> None:
    text = _step(name)
    for phrase in gone:
        assert phrase not in text, phrase
    if name in ("step-07-capstone.md", "step-08-verify.md", "step-09-refine.md"):
        # The helper reads the envelope: no step lists the fields it writes.
        assert not re.search(r"^- `campaign\.", text, re.M)


def test_steps_keep_the_rules_they_act_on() -> None:
    setup = _step("step-01-setup.md")
    assert "A target the script rejects (`errors[]` non-empty, exit 1, including a brief `pin` that is not a string)" \
        in _section(setup, 1)
    assert setup.count("a Tier A pin that is no X.Y.Z version") == 1
    assert setup.count("never from the raw source") == 1
    assert "The directive's `## Quality Overrides` apply later, while the campaign runs, and are never written here." \
        in _section(setup, 2)
    assert "`execution_order` (the ordered skill names)" in _section(_step("step-02-strategy.md"), 3)
    loop = _step("step-05-skill-loop.md")
    gate = _section(loop, 4)
    assert ("7. If the pass ends with a Tier A skill still `pending` (only a hand-edited state can do this), "
            "HALT (exit code 7, `dependency-deadlock`) and log it (type `event`).") in gate.splitlines()
    assert "runs `[H]alt`.\n" in gate
    assert ("Its JSON result on stdout carries `skills_completed`, `skills_failed` and `duration`, which §6 displays; "
            "§5 builds the envelope from `{resultContextFile}`") in _section(_step("step-11-maintenance.md"), 2)


def test_directive_recognizes_what_the_gate_script_reads() -> None:
    """The directive spec recognizes exactly the sections campaign-quality-gate.py parses (#1140)."""
    spec = _step("campaign-directive-spec.md")
    recognized = spec[spec.index("## Recognized Sections"):spec.index("## Absence Behavior")]
    listed = {title.lower() for title in re.findall(r"^- \*\*`## ([^`]+)`\*\*", recognized, re.M)}
    gate_script = CAMPAIGN_DIR / "scripts" / "campaign-quality-gate.py"
    parsed = set(re.findall(r'sections\.get\("([^"]+)"', gate_script.read_text(encoding="utf-8")))
    assert parsed == {"skip list", "quality overrides"}
    assert listed == parsed
    assert "Pipeline Flags" not in spec
    # No script parses any other heading: a flag or gate value written under it changes nothing.
    import importlib.util

    spec_obj = importlib.util.spec_from_file_location("campaign_quality_gate_stepfiles", gate_script)
    gate = importlib.util.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(gate)
    other = "## Pipeline Flags\n\n- core: --skip-tests\n- soft_target: 50\n\n## Notes\n\n- skip: core\n"
    assert gate.parse_directive(other) == {"skip": {}, "campaign": {}, "skills": {}, "unparsed": []}
    flat = " ".join(spec.split())
    assert ("Such guidance never changes a sub-skill's flags or inputs: the stages pass fixed flags and the inputs "
            "their scripts resolve.") in flat
    assert ("Only the two sections above are parsed by a script; the kickoff script copies the whole directive "
            "into each Tier A kickoff as context.") in flat
    assert "reach a script" not in flat
    absence = spec.split("## Absence Behavior\n", 1)[1].strip()
    assert absence == ("An unset `campaign.directive_path` or a missing file is no error: the campaign proceeds "
                       "with defaults.")
    doc = (REPO_ROOT / "docs" / "campaign.md").read_text(encoding="utf-8")
    [paragraph] = [p for p in doc.split("\n\n") if p.startswith("An optional Markdown file of standing instructions")]
    assert "It can hold `## Quality Overrides` and `## Skip List` sections" in paragraph
    assert "which changes no sub-skill's flags or inputs" in paragraph
    for gone in ("Pipeline Flags", "## Notes"):
        assert gone not in paragraph, gone


# ---------------------------------------------------------------------------
# #1141: CS's results are recorded right after CS; views come from scripts
# ---------------------------------------------------------------------------


def _state_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("campaign_state_stepfiles_run", STATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pipeline() -> tuple[str, str, str]:
    """step-05 §5.2's CS bullet, the sub-bullets after it up to TS, and the TS bullet."""
    body = _section(_step("step-05-skill-loop.md"), 5)
    cs = body.index("     - **CS** (`skf-create-skill`)")
    ts = body.index("     - **TS** (`skf-test-skill`)")
    return body[cs:ts], body[ts:body.index("\n", ts)], body


def test_the_skill_path_and_corrections_are_recorded_before_the_test() -> None:
    before_ts, ts, body = _pipeline()
    path_write = "uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --skill-path <skill_package>"
    doc_rot = ("uv run {stateScript} append-workarounds --state-file {stateFile} --skill {skill_name} --doc-rot-file "
               '"{project-root}/_bmad-output/.skf-stage/{skill_name}/doc-rot-corrections.json"')
    assert path_write in before_ts and doc_rot in before_ts
    assert before_ts.index(path_write) < before_ts.index("     - **Doc-rot check:**") < before_ts.index(doc_rot)
    assert "On a `success` or `partial` line, record the `skill_package`" in before_ts
    assert "on that same `success` or `partial` line" in before_ts
    # #1141: the record gates no stage, so a file the helper cannot read is logged and passed, never a HALT.
    assert ("An exit 2 (a file that is no JSON array of records with an `affected` and a `candidate_category`) "
            "writes nothing and stops nothing, since this record gates no stage: log \"doc-rot corrections not "
            "recorded: <error>\" (type `event`) and go on to TS.") in before_ts
    # The step's state rule stays the shared one: the State Contract it points to names the exception.
    assert ("HALT with the same code, except where the step names another route for that call: step-05 logs a "
            "doc-rot file `append-workarounds` cannot read and goes on.") in _step("campaign-contracts.md")
    # Nothing after the test reads what CS left in context.
    after_ts = body[body.index(ts) + len(ts):]
    for gone in ("skill_package", "--skill-path", "correction_matches", "Doc-rot", "--entry"):
        assert gone not in after_ts, gone
    assert "**Do not hand-grep the feeders" not in body


def test_a_path_recorded_before_a_failed_test_stays(tmp_path: pathlib.Path, capsys) -> None:
    """The documented calls: CS `success` records the path; TS FAIL then fails the skill, which keeps it."""
    before_ts, _, body = _pipeline()
    state = _state_module()
    path = tmp_path / "_campaign-state.yaml"
    skill = {"name": "core", "status": "active", "depends_on": [], "tier": "A", "pin": "1.2.0", "brief_path": None,
             "skill_path": None, "quality_score": None, "workarounds_applied": [], "started_at": None,
             "completed_at": None, "commit_sha": None}
    path.write_text(yaml.safe_dump({
        "campaign": {"name": "demo", "started_at": "2026-10-01T10:00:00Z", "last_updated": "2026-10-01T10:00:00Z",
                     "current_stage": 3,
                     "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80}},
        "skills": [skill], "dependency_graph": {"execution_order": ["core"], "circular_deps_detected": False},
    }, sort_keys=False), encoding="utf-8")
    failed = re.search(r"`(uv run \{stateScript\} set-skill [^`]*--status failed)[^`]*`", body).group(1)
    for call in (re.search(r"`(uv run \{stateScript\} set-skill [^`]*--skill-path <skill_package>)`",
                           before_ts).group(1), failed):
        argv = (call.replace("{stateFile}", str(path)).replace("{skill_name}", "core")
                .replace("<skill_package>", "skills/core/1.2.0/core").split()[3:])
        assert state.main(argv) == 0, call
    capsys.readouterr()
    [written] = yaml.safe_load(path.read_text(encoding="utf-8"))["skills"]
    assert (written["status"], written["skill_path"]) == ("failed", "skills/core/1.2.0/core")


def test_strategy_shows_the_view_campaign_deps_renders() -> None:
    text = _step("step-02-strategy.md")
    view = _section(text, 5)
    assert ("Run `uv run {depsScript} --render --state-file {stateFile}` and show its output verbatim (display only: "
            "it is not written to a file).") in view
    assert "then HALT as §3 and §4 say" in view
    for gone in ("DEPENDENCY MAP", "TIER DISTRIBUTION", "EXECUTION ORDER", "```"):
        assert gone not in view, gone
    assert "`cycle_edges`" in _section(text, 3)
    assert "each `cycle_edges` entry" in _section(text, 4)
    # §5's view exits 1 with a CIRCULAR_DEPENDENCY error, not --compute's JSON: §4's cycle case names it.
    assert "- **Cycle** (`circular_deps_detected: true`, or a `CIRCULAR_DEPENDENCY` error from §5" in _section(text, 4)
    assert "`tier_counts`" not in text
    for gone in ("last review surface", "display the strategy view"):
        assert gone not in text, gone
    # §3 only parses --compute's JSON: the view the operator sees is §5's --render output, ordered as --compute is.
    write = _section(text, 7)
    assert ("from the same `campaign-deps.py --compute` §3 ran, which orders the skills as the §5 view does, "
            "so the order on disk is the order shown.") in write
    assert "§3 view" not in text
    gate = _section(text, 6)
    assert "- `[P]roceed`: write the plan (§7)" in gate and "- `[C]ancel`: log the cancel" in gate
    assert "exit code 12 (`user-cancelled`)" in gate
    assert text.rstrip().endswith("## OUTPUT\n\nChain to `{nextStepFile}`.")


def test_only_strategy_renders_and_no_step_joins_the_plan_by_hand() -> None:
    for path in sorted(REFERENCES_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if path.name != "step-02-strategy.md":
            assert "--render" not in text, path.name
        assert 'status == "completed"' not in text, path.name
    strategy = _step("step-02-strategy.md")
    assert strategy.count("--render") == 1 and "--render" in _section(strategy, 5)


def test_export_and_resume_state_what_to_show() -> None:
    export = _step("step-10-export.md")
    for gone in ("Export Results", "{summary table and exclusions from §3}", "Display export summary",
                 "| # | Name |", "ready for export.**"):
        assert gone not in export, gone
    assert ("Show one row per `skills[]` entry with its name, tier, quality score, verdict, `export_name` and skill "
            "path, then each `excluded[]` skill with its score and `reason`, and `{N}`, the number of `export[]` "
            "skills.") in _section(export, 3)
    gate = _section_with_subsections(export, 4)
    assert ("{N} skill(s) that clear the quality gate, listed in the §3 view, will be exported via "
            "`skf-export-skill`:") in gate
    assert "- **[E]xport all**:" in gate and "- **[C]ancel**:" in gate
    assert "HALT with exit code 11 (`export-cancelled`)" in gate
    assert ("After all exports, show how many skills exported, how many failed (each with its halt reason or exit "
            "code) and how many the quality gate kept from export.") in _section(export, 5)
    assert export.rstrip().endswith("## OUTPUT\n\nChain to `{nextStepFile}`.")
    resume = _section(_step("step-resume.md"), 4)
    assert "CAMPAIGN RESUME" not in _step("step-resume.md") and "```" not in resume
    # #1143: §4 opens with the `--unattended` write, then shows the resume point.
    assert resume.strip().split("\n\n")[-1].startswith(
        "Before chaining, show the campaign name, the stage and `step_file` it resumes")
    assert "(never a hand count of `skills[]`)" in resume


# ---------------------------------------------------------------------------
# #1143: Setup finds the architecture document; [U]nattended; pin correction; halt reasons
# ---------------------------------------------------------------------------

ARCH_PATHS = ("`{project-root}/docs/architecture.md`",
              "`{project-root}/_bmad-output/planning-artifacts/architecture.md`")


def _state_call(text: str, start: str) -> str:
    """The one inline `uv run {stateScript} ...` call in `text` that starts with `start`."""
    calls = [c for c in re.findall(r"`(uv run \{stateScript\} [^`]+)`", text) if c.startswith(start)]
    assert len(calls) == 1, (start, calls)
    return calls[0]


def _parse(call: str, **values: str):
    """The call's arguments, placeholders filled, through campaign-state.py's own parser."""
    for placeholder, value in values.items():
        call = call.replace(placeholder, value)
    return _state_parser().parse_args(shlex.split(call)[3:])


def test_setup_looks_for_the_architecture_document_in_both_modes() -> None:
    intake = _section(_step("step-01-setup.md"), 1)
    [bullet] = [line for line in intake.splitlines() if line.startswith("- `architecture_doc_path`:")]
    for token in (*ARCH_PATHS, "in both modes", "`--architecture-doc-path`", "a `--manifest`",
                  "a brief without `architecture_doc_path`"):
        assert token in bullet, token
    assert bullet.index(ARCH_PATHS[0]) < bullet.index(ARCH_PATHS[1])
    for gone in ("discover it at runtime", "re-prompting"):
        assert gone not in intake, gone
    assert ('"architecture doc: <path>" or "architecture doc: none found, so verification and refinement will be '
            'skipped"') in intake
    assert "[--architecture-doc-path <architecture_doc_path>]" in _section(_step("step-01-setup.md"), 2)


@pytest.mark.parametrize("name, stage, short", [("step-08-verify.md", "verification", "VS"),
                                                 ("step-09-refine.md", "refinement", "RA")], ids=["verify", "refine"])
def test_verify_and_refine_never_ask_for_the_architecture_document(name: str, stage: str, short: str) -> None:
    locate = _section(_step(name), 3)
    assert "prompt" not in locate.lower() and "`{headless_mode}` is false" not in locate
    assert "{headless_mode}" not in locate
    steps = re.findall(r"^\d\. (.*)$", locate, re.M)
    assert len(steps) == 3, steps
    assert ARCH_PATHS[0] in steps[1] and ARCH_PATHS[1] in steps[1]
    assert steps[2].startswith(f"If still not found: skip {short} invocation with a warning; do not HALT.")
    assert f"Log that {stage} was skipped due to missing architecture doc (type `event`)" in steps[2]
    persist = next(p for p in locate.split("\n\n") if "--architecture-doc-path <path>" in p)
    assert persist.startswith("When step 2 finds it, persist the path")
    _parse(_state_call(persist, "uv run {stateScript} set-campaign"))


def test_the_capstone_gets_the_architecture_document_setup_recorded() -> None:
    """Setup records a document it found as one given, and the capstone hands it to SS compose mode, so the docs
    and the fragment name the capstone; a recorded path whose file is gone is left out, since SS halts on it."""
    [line] = [line for line in _section(_step("step-07-capstone.md"), 3).splitlines()
              if line.startswith("- `architecture_doc_path`:")]
    assert "the document Setup was given or found, only when state sets it and that file exists" in line
    intake = _section(_step("step-01-setup.md"), 1)
    for token in ("the capstone (Stage 6), verify (Stage 7) and refine (Stage 8) stages consume",
                  "with none, the capstone composes without it, and verification and refinement skip and log it"):
        assert token in intake, token
    doc = (REPO_ROOT / "docs" / "campaign.md").read_text(encoding="utf-8")
    for token in ("Only the Capstone, Verification and Refinement stages use it",
                  "The Capstone, Verification and Refinement stages use the architecture document Setup recorded",
                  "and composes without it when the state holds none or its file is gone"):
        assert token in doc, token
    fragment = (REPO_ROOT / "changes" / "campaign-architecture-doc-found-at-setup.yaml").read_text(encoding="utf-8")
    assert "The Capstone now passes a found document to `skf-create-stack-skill` as well" in fragment


def test_the_plan_gate_offers_unattended() -> None:
    text = _step("step-02-strategy.md")
    gate = _section(text, 6)
    options = [line for line in gate.splitlines() if line.startswith("- `[")]
    assert [o[:16] for o in options] == ["- `[P]roceed`: w", "- `[U]nattended`", "- `[C]ancel`: lo"]
    unattended = options[1]
    assert "write the plan as `[P]` does, with `--unattended` (§7)" in unattended
    log = _parse(_state_call(unattended, "uv run {stateScript} log"))
    assert (log.type, log.text) == ("decision", "unattended: chosen at the plan gate")
    assert "Export still asks" in unattended
    # Headless still takes [P]: no unattended default at the plan gate.
    assert "**GATE [default: P]**: in headless mode, auto-proceed with `[P]`" in gate
    assert "campaign.unattended" not in gate
    write = _section(text, 7)
    assert "On `[P]roceed` or `[U]nattended`" in write
    call = "uv run {stateScript} apply-plan --state-file {stateFile} --stage 1 [--unattended]"
    assert call in write
    parsed = _parse(call.replace(" [--unattended]", " --unattended"))
    assert (parsed.op, parsed.stage, parsed.unattended) == ("apply-plan", 1, True)
    assert _parse(call.replace(" [--unattended]", "")).unattended is False


def test_an_interactive_run_corrects_an_invalid_pin() -> None:
    text = _step("step-03-pins.md")
    rules = _rules_section(text)
    assert "invalid pins are errors" not in rules and "invalid-pin" not in rules
    handle = _section(text, 4)
    first, gate = [p.strip() for p in handle.strip().split("\n\n")]
    for token in ("If any result is `invalid`", "its attempted `pin`", "the script's `suggestions`",
                  "ask for every corrected pin in one question", "nothing for the latest release",
                  "a Tier A pin that is no X.Y.Z version: ask for that pin again", "then run §3 again"):
        assert token in first, token
    pin = _parse(_state_call(first, "uv run {stateScript} set-skill"), **{"<skill>": "core", "<pin>": "1.2.0"})
    assert (pin.op, pin.skill, pin.pin) == ("set-skill", ["core"], "1.2.0")
    # A pin is free text the operator typed: quoted as a log entry is.
    assert ("the pin single-quoted as a log entry is, per the Decision Log in `references/campaign-contracts.md`"
            in first)
    log = _parse(_state_call(first, "uv run {stateScript} log"))
    assert log.type == "decision" and log.text.startswith("pin: <skill> <old pin> corrected to")
    # An empty answer or a null pin is the latest release, so the decision line never ends on nothing.
    assert "(`latest release` for an empty or null pin), then run §3 again." in first
    assert gate.startswith("**GATE [default: HALT]**: in headless mode, HALT (exit code 5, `invalid-pin`)")
    for token in ("listing each skill, its attempted pin and the script's suggestions",
                  "run `campaign resume` interactively (no `--headless`, `headless_mode` off), which asks for the "
                  "corrected pins here", "since a headless resume checks the same pin again",
                  "run `campaign`, choose overwrite and give the archived `campaign-brief.yaml` with corrected pins"):
        assert token in gate, token
    for gone in ("Do NOT partially proceed", "all-or-nothing", "HALT as in §4"):
        assert gone not in text, gone
    assert "on exit 5 (nothing written), HALT (exit code 5, `invalid-pin`)" in _section(text, 5)
    note = _exit_table()["invalid-pin"][1]
    assert note == ("an interactive `campaign resume` asks for the corrected pins; a headless one checks the same pin "
                    "again, so run `campaign`, choose overwrite and give the archived `campaign-brief.yaml` with "
                    "corrected pins")


def test_the_invalid_pin_way_out_names_the_interactive_resume_first() -> None:
    # A headless exit 5 leaves current_stage at 1, so a resume runs step-03 again, which an
    # interactive run answers there: the overwrite route comes second.
    docs = (REPO_ROOT / "docs" / "campaign.md").read_text(encoding="utf-8")
    [bullet] = [line for line in docs.splitlines() if line.startswith("- **An invalid pin**")]
    fragment = (REPO_ROOT / "changes" / "campaign-invalid-pin-correction.yaml").read_text(encoding="utf-8")
    for where, text in (("step-03 GATE", _section(_step("step-03-pins.md"), 4).split("**GATE", 1)[1]),
                        ("row 5", _exit_table()["invalid-pin"][1]), ("docs", bullet),
                        ("fragment", fragment.split("A headless run", 1)[1])):
        resume = text.find("`campaign resume` interactively") if where != "row 5" else text.find(
            "an interactive `campaign resume`")
        overwrite = text.find("choose overwrite")
        assert 0 <= resume < overwrite, where
    assert "Run `campaign resume` interactively (no `--headless`, and `headless_mode` not set to true): it asks for " \
        "the corrected pins at Pin Validation." in bullet


def test_provenance_states_its_halt_rule_once() -> None:
    text = _step("step-04-provenance.md")
    assert "Do NOT partially proceed" not in text
    assert "Any inaccessible repo halts the campaign" in _rules_section(text)
    assert re.search(r"^### §4: Handle Inaccessible Repos$", text, re.M)
    assert re.search(r"^### §5: Write State$", text, re.M)


def test_the_skill_loop_records_why_a_skill_failed_or_was_skipped() -> None:
    loop = _step("step-05-skill-loop.md")
    gate, body = _section(loop, 4), _section(loop, 5)
    directive = _parse(_state_call(gate, "uv run {stateScript} set-skill --state-file {stateFile} --skill "
                                         "{skill_name} --status skipped --halt-reason 'directive"),
                       **{"{skill_name}": "core"})
    assert (directive.status, directive.halt_reason) == ("skipped", "directive Skip List: <skip_reason>")
    assert "with `'directive Skip List'` when `skip_reason` is null" in gate
    [skip] = [line for line in gate.splitlines() if line.startswith("   - `[S]kip`:")]
    blocked = _parse(_state_call(skip, "uv run {stateScript} set-skill"), **{"{skill_name}": "core"})
    assert (blocked.status, blocked.halt_reason) == ("skipped", "unmet dependency: <dependency> is <status>")
    assert "one such clause per unmet dependency, joined by `, `" in skip
    failed = _parse(_state_call(body, "uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} "
                                      "--status failed"),
                    **{"{skill_name}": "core", "[--quality-score <quality_score>]": "--quality-score 70"})
    assert (failed.status, failed.halt_reason, failed.quality_score) == ("failed", "<reason>", 70)
    # The reason names the sub-skill that failed: a bare `no-result` could be BS's, CS's or TS's.
    assert ("`<reason>` is the failure reason, also logged as an `event`, led by the sub-skill that failed (`BS`, "
            "`CS` or `TS`, such as `CS: no-result`): the record's `reason`, the failing sub-skill's `halt_reason`, "
            "else `exit <code>`, `no-result`, or `unparseable result envelope`.") in body
    batch = _section(_step("step-06-batch.md"), 5)
    assert "apply-batch also saves that code as the skill's `halt_reason`, which the report prints" in batch


def test_only_the_dependency_gate_takes_the_unattended_default() -> None:
    loop = _step("step-05-skill-loop.md")
    rules = _rules_section(loop)
    assert ("- When state sets `campaign.unattended` to true (the plan gate's `[U]nattended`, or `campaign resume "
            "--unattended`), an interactive run takes §4.6's `default_action` too, and never forces a dependency."
            ) in rules.splitlines()
    gate = _section(loop, 4)
    [annotation] = [line for line in gate.splitlines() if "**GATE [default: `default_action`]**" in line]
    assert ("headless, take `default_action`; a run whose state sets `campaign.unattended` to true takes it too."
            in annotation)
    # A headless run whose state is also unattended logs one label, every time.
    assert ('logs "<mode>: skipped {skill_name}: {dependency} is {status}" (type `auto`, `<mode>` `headless` when '
            '`{headless_mode}` is true, else `unattended`)') in annotation
    # The halt default is logged too, so an unattended exit 13 shows in the report's Operator Decisions.
    assert ('`halt` (a dependency is still pending or active, an order the loop cannot follow) logs "<mode>: halted '
            'at {skill_name}: {dependency} is {status}" (type `auto`) for each unmet dependency, then runs `[H]alt`.'
            ) in annotation
    assert annotation.rstrip().endswith("runs `[H]alt`.")
    assert "- `[H]alt`: stop the campaign with exit code 13 (`dependency-blocked`)" in gate
    # Every other gate still asks: no other step, the Export gate included, reads the flag.
    for path in sorted(REFERENCES_DIR.glob("*.md")):
        if path.name != "step-05-skill-loop.md":
            assert "campaign.unattended" not in path.read_text(encoding="utf-8"), path.name
    assert "unattended" not in _step("step-10-export.md").lower()


def test_resume_sets_unattended_before_it_chains() -> None:
    text = _step("step-resume.md")
    assert ("- Leave state untouched except for the three writes below (§1 backup restore, §3 `[R]e-run`, §4 "
            "`--unattended`), each through `{stateScript}`, and on a non-zero exit HALT with the same code."
            ) in _rules_section(text)
    routing = _section(text, 4)
    first = routing.strip().split("\n\n")[0]
    assert first.startswith("When the invocation passed `--unattended`, run ")
    write = _parse(_state_call(first, "uv run {stateScript} set-campaign"))
    assert (write.op, write.unattended, write.stage) == ("set-campaign", True, None)
    log = _parse(_state_call(first, "uv run {stateScript} log"))
    assert (log.type, log.text) == ("decision", "unattended: set by campaign resume --unattended")
    skill = (CAMPAIGN_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "1. **`campaign resume [--from=<skill>] [--unattended]`**" in skill
    assert "`campaign resume [--from=<skill>] [--unattended]` to resume" in skill
    # docs/workflows.md lists the resume options too.
    workflows = (REPO_ROOT / "docs" / "workflows.md").read_text(encoding="utf-8")
    assert "`@Ferris campaign resume [--from=<skill>] [--unattended]` resumes" in workflows
    assert "`@Ferris campaign resume [--from=<skill>]` resumes" not in workflows
    assert re.search(r"^   \| `--unattended` \| With `campaign resume`:", skill, re.M)
    assert "| 2 | Pin Validation | references/step-03-pins.md | Conditional (an invalid pin; headless HALTs) |" in skill


def test_contracts_name_the_new_writes() -> None:
    contracts = _step("campaign-contracts.md")
    # #1141: `log --once` counts only this campaign's lines, as the report's Operator Decisions does.
    assert ("With `--once` it appends nothing when the log already holds a line of the same type and text stamped at "
            "or after the campaign's `started_at` (read from the `_campaign-state.yaml` beside the log, since an "
            "overwrite archives the state but leaves the log)") in contracts
    rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| `([a-z-]+)` \|.*$", contracts, re.M)}
    assert ("`unattended`: true with `--unattended` (the plan gate's `[U]nattended`), else false, keeping a true that "
            "`campaign resume --unattended` wrote") in rows["apply-plan"]
    for token in ("| step-03, step-05, step-10, step-resume |", "`pin` (`--pin`: empty for the latest release",
                  "`halt_reason` (`--halt-reason`, only with `--status failed` or `skipped`)",
                  "`pending` clears both, the `export` outcome and the `halt_reason`"):
        assert token in rows["set-skill"], token
    assert "with each failed or skipped skill's `halt_reason`" in rows["apply-batch"]
    assert "| steps 07 to 09, step-resume |" in rows["set-campaign"]
    assert "`unattended` (`--unattended`, from `campaign resume --unattended`)" in rows["set-campaign"]
    assert "a Tier A pin that is no X.Y.Z version), 3 for" in contracts
    log = _contract("Decision Log")
    assert "a corrected pin, an unattended run)" in log
    assert "- `auto`: the default a headless or unattended run took at a gate" in log


def test_a_halt_reason_and_a_pin_are_quoted_as_a_log_entry_is() -> None:
    # A reason (a directive's skip_reason, a record's reason) or a pin is free text: an apostrophe
    # in it would end a single-quoted argument and break the call.
    log = _contract("Decision Log")
    assert ("write an apostrophe inside it as `'\\''`; a `set-skill --halt-reason` or `--pin` value is quoted the "
            "same way)") in log
    rules = _rules_section(_step("step-05-skill-loop.md"))
    assert ("A `--halt-reason` text is single-quoted as a log entry is, an apostrophe written as `'\\''` "
            "(`references/campaign-contracts.md`, Decision Log).") in rules
    # Every value the step calls pass after these flags opens a single-quoted argument.
    for name, flag, count in (("step-03-pins.md", "--pin", 1), ("step-05-skill-loop.md", "--halt-reason", 3)):
        values = re.findall(rf"{flag} (\S)", _step(name))
        assert values == ["'"] * count, (name, flag, values)


def test_the_campaign_page_says_which_log_lines_and_architecture_paths_count() -> None:
    lines = (REPO_ROOT / "docs" / "campaign.md").read_text(encoding="utf-8").splitlines()
    # Operator Decisions keeps the lines stamped at or after campaign.started_at, which `init` writes.
    [report] = [line for line in lines if line.startswith("- **Campaign report**")]
    assert ("each default a headless or unattended run took after Setup wrote the state (a line logged before "
            "that, such as an earlier campaign's or one of Setup's own, stays in the log only)") in report
    # A copy of the report template shows the section only with its placeholder.
    [templates] = [line for line in lines if line.startswith("- **Template overrides**")]
    assert "only once it holds the `{{operator_decisions}}` placeholder the bundled template ends with" in templates
    template = (CAMPAIGN_DIR / "templates" / "campaign-report-template.md").read_text(encoding="utf-8")
    assert template.rstrip().endswith("{{operator_decisions}}")
    # Step 1 of step-08/09 §3 takes the state's path only when its file exists.
    assert any("When the state holds none, or the file it names is gone, they look in those two places again"
               in line for line in lines)
