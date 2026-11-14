#!/usr/bin/env python3
"""The customize.toml surface of every workflow (#596).

Each workflow's bundled customize.toml is what a team overrides through
`{project-root}/_bmad/custom/<skill>.toml`. An override has to reach the code
that owns its rule, or it changes nothing, so:

- every workflow ships exactly the scalars ALLOWED lists, beside the three
  arrays BMad's resolver merges (activation_steps_prepend,
  activation_steps_append, persistent_facts); a scalar added or removed
  changes this list in the same pull request;
- SKILL.md On Activation binds each scalar to its variable, and a stage file
  reads that variable: a helper command passes it on for a scalar a script
  owns, and campaign's quality gate scalars, passed the way step-01 passes
  them, change the state campaign-state.py writes;
- each on_complete comment (#1109) takes one of the two documented forms:
  a shell command, whose comment says so, says that unlike BMad core this
  workflow hands the value to the shell, and quotes any path it shows; or
  an instruction (Setup Forge and Verify Stack only), whose comment opens
  by saying so. Every command-style terminal stage passes its path quoted,
  runs the hook from `{project-root}`, states when it skips the hook, and
  never fails the run on a hook failure;
- the `!` persistent_facts rule (the maintainer's 2026-10-02 decision): for
  every workflow that ships a non-empty persistent_facts, the On Activation
  persistent_facts sentence drops a `!` entry and each earlier entry it
  names, and the customize.toml comment above persistent_facts shows
  `persistent_facts = ["!file:{project-root}/**/project-context.md"]` and
  never says an override cannot remove or delete the default or suggests a
  counter-fact;
- every persistent_facts example (#1108) is the override file it names:
  `#   [workflow]` is the line before the `persistent_facts = [...]` line, so
  the two lines, `#` markers dropped, parse to the `workflow` table the
  resolver's `--key workflow` reads, where a key above that line is ignored
  without a warning;
- each `file` scalar's bundled default (#1108) names a file the skill
  bundles, and only the scalars STILL_EMPTY lists ship an empty string; the
  template comments of Audit, Test, Stack, Quick and Export say to keep a
  house-style copy outside the skill folder and name it from
  {project-root}, since a bare path resolves from the skill root;
- Campaign (#1110) ships its real defaults: `{forge_data_folder}/_campaign`
  for its workspace and the bundled `templates/` files for its three template
  scalars, and its comments say a bare path resolves from the skill root;
- the project-context default (the maintainer's 2026-11-12 decision, #1107):
  the twelve workflows that read the project context ship it, and Audit,
  Brief and Test Skill say it is kept on purpose; skf-setup, skf-drop-skill
  and skf-campaign ship `[]`, and the comment of the last two shows the
  two-line `[workflow]` override that loads those files anyway; campaign's
  kickoff loader applies it, and a later `!` entry drops it again.

skf-forger is not a workflow: its customize.toml holds an [agent] block.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"

ARRAYS = ("activation_steps_prepend", "activation_steps_append", "persistent_facts")

# Each workflow's scalars: the variable SKILL.md binds from it, and what it is.
#   hook    on_complete, run by the stage that finishes the run
#   file    a file a team swaps for a house-style copy, read by the model
#   folder  where the run writes
#   script  passed to a helper script as an argument
#   setting read by the model at a gate
ALLOWED = {
    "skf-analyze-source": {
        "analysis_report_template_path": ("analysisReportTemplatePath", "file"),
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-audit-skill": {
        "drift_report_template_path": ("driftReportTemplatePath", "file"),
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-brief-skill": {
        "description_voice_examples_path": ("descriptionVoiceExamplesPath", "file"),
        "scope_templates_path": ("scopeTemplatesPath", "file"),
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-campaign": {
        "campaign_workspace_path": ("campaignWorkspacePath", "folder"),
        "quality_gate_soft_target": ("qualityGateSoftTarget", "script"),
        "quality_gate_soft_fallback": ("qualityGateSoftFallback", "script"),
        "report_template_path": ("reportTemplatePath", "file"),
        "kickoff_template_path": ("kickoffTemplatePath", "file"),
        "on_complete": ("onComplete", "hook"),
    },
    "skf-create-skill": {
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-create-stack-skill": {
        "on_complete": ("onCompleteCommand", "hook"),
        "stack_skill_template_path": ("stackSkillTemplatePath", "file"),
        "integration_patterns_path": ("integrationPatternsPath", "file"),
    },
    "skf-drop-skill": {
        "on_complete": ("onCompleteCommand", "hook"),
        "forbid_purge_in_headless": ("forbidPurgeInHeadless", "setting"),
    },
    "skf-export-skill": {
        "on_complete": ("onCompleteCommand", "hook"),
        "snippet_format_path": ("snippetFormatPath", "file"),
    },
    "skf-quick-skill": {
        "skill_template_path": ("skillTemplatePath", "file"),
        "batch_output_path": ("batchOutputPath", "script"),
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-refine-architecture": {
        "refinement_rules_path": ("refinementRulesPath", "file"),
        "output_folder_path": ("outputFolderPath", "folder"),
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-rename-skill": {
        "on_complete": ("onCompleteCommand", "hook"),
        "force_source_authority_in_headless": ("forceSourceAuthorityInHeadless", "setting"),
    },
    "skf-setup": {
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-test-skill": {
        "test_report_template_path": ("testReportTemplatePath", "file"),
        "default_threshold": ("defaultThreshold", "setting"),
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-update-skill": {
        "on_complete": ("onCompleteCommand", "hook"),
    },
    "skf-verify-stack": {
        "on_complete": ("workflow.on_complete", "hook"),
        "report_template_path": ("reportTemplatePath", "file"),
    },
}
WORKFLOWS = sorted(ALLOWED)
SCALARS = [(skill, key) for skill in WORKFLOWS for key in ALLOWED[skill]]

DEFAULT_FACT = "file:{project-root}/**/project-context.md"
DROP_OVERRIDE = f'#   persistent_facts = ["!{DEFAULT_FACT}"]'
# A sentence that tells a team the default cannot be dropped, or to answer
# it with a contradicting fact instead.
STALE_FACT_ADVICE = ("cannot remove it", "cannot delete it", "no override can delete it", "add a literal fact",
                     "counter-fact", "counter fact")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _customize(skill: str) -> str:
    return _read(SRC / skill / "customize.toml")


def _workflow_table(skill: str) -> dict:
    return tomllib.loads(_customize(skill))["workflow"]


def _comment_above(skill: str, key: str) -> str:
    """The comment block right above `key = ...` (the lines after the last blank line)."""
    text = _customize(skill)
    return text[: text.index(f"\n{key} =")].rsplit("\n\n", 1)[-1]


def _activation(skill: str) -> str:
    return _read(SRC / skill / "SKILL.md").split("## On Activation", 1)[1].split("\n## ", 1)[0]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _stage_files(skill: str) -> list[Path]:
    return sorted((SRC / skill / "references").rglob("*.md"))


def test_every_workflow_is_listed():
    found = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")
    assert found == WORKFLOWS


def test_the_forger_ships_an_agent_block_not_a_workflow_surface():
    table = tomllib.loads(_read(SRC / "skf-forger" / "customize.toml"))
    assert "agent" in table and "workflow" not in table


# --------------------------------------------------------------------------
# The allowed scalars
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_customize_toml_ships_only_the_allowed_scalars(skill):
    table = _workflow_table(skill)
    for array in ARRAYS:
        assert isinstance(table.get(array), list), (skill, array)
    scalars = sorted(key for key in table if key not in ARRAYS)
    assert scalars == sorted(ALLOWED[skill]), (
        f"{skill}: customize.toml scalars {scalars} differ from the allowed {sorted(ALLOWED[skill])}; "
        "a removed scalar leaves the list, and a new one names the code it reaches"
    )


@pytest.mark.parametrize("skill,key", SCALARS, ids=[f"{s}:{k}" for s, k in SCALARS])
def test_activation_binds_each_scalar_to_its_variable(skill, key):
    variable, _ = ALLOWED[skill][key]
    group = "quality_gate_*" if key.startswith("quality_gate_") else None
    lines = [line for line in _activation(skill).splitlines()
             if f"workflow.{key}" in line or (group and f"`{group}`" in line)]
    assert lines, f"{skill}: On Activation never reads workflow.{key}"
    if variable != f"workflow.{key}":
        assert any(f"{{{variable}}}" in line for line in lines), (
            f"{skill}: On Activation reads workflow.{key} but binds no `{{{variable}}}` there")


# A setting that acts in On Activation, before any stage loads: its HALT reads the placeholder there.
ACTS_IN_ACTIVATION = {("skf-drop-skill", "forbid_purge_in_headless")}


@pytest.mark.parametrize("skill,key", SCALARS, ids=[f"{s}:{k}" for s, k in SCALARS])
def test_each_scalar_reaches_a_stage(skill, key):
    variable, kind = ALLOWED[skill][key]
    placeholder = f"{{{variable}}}"
    if (skill, key) in ACTS_IN_ACTIVATION:
        halts = [line for line in _activation(skill).splitlines() if placeholder in line and "HALT" in line]
        assert halts, f"{skill}: workflow.{key} is bound to {placeholder}, which no On Activation HALT reads"
        return
    readers = [path for path in _stage_files(skill) if placeholder in _read(path)]
    assert readers, f"{skill}: workflow.{key} is bound to {placeholder}, which no stage file reads"
    if kind == "script":
        commands = [line for path in readers for line in _read(path).splitlines()
                    if placeholder in line and re.search(r"\buv run\b", line)]
        assert commands, f"{skill}: {placeholder} reaches no helper command"


# #1109: in BMad core on_complete is an instruction; a command-style comment says
# this workflow departs from that.
HOOK_CONTRAST = ('Unlike BMad core, where on_complete is an instruction, this workflow hands the value to the shell, '
                 'so an instruction such as "run Test Skill" fails.')
INSTRUCTION_HOOKS = {"skf-setup", "skf-verify-stack"}
# Each command-style terminal stage, by workflow: (file under references/, the
# heading or lead that opens it, what follows it, the skip it states).
HOOK_STAGES = {
    "skf-analyze-source": [
        ("generate-briefs.md", "### 9b.", "### 10.", "skip the hook and say so"),
        ("step-auto-scope.md", "If `{onCompleteCommand}` is non-empty, the line's", "Then delete the run folder",
         "skip the hook and say so"),
        ("auto-docs-only.md", "If `{onCompleteCommand}` is non-empty, the line's", "### 6.",
         "skip the hook and say so"),
    ],
    "skf-audit-skill": [("report.md", "**Post-audit hook (optional).**", "### 6.", "skip the hook when it is null")],
    "skf-brief-skill": [
        ("write-brief.md", "### 6b.", "### 7.", "the hook never names a missing file"),
        ("step-auto-validate.md", "**On-complete hook.**", "**Remove the run folder.**",
         "the hook never names a missing file"),
    ],
    # Campaign's skip is its call without --report-path when no report was written.
    "skf-campaign": [("step-11-maintenance.md", "### §4: Post-Completion Hook", "### §5",
                      "without `--report-path`, since there is no report to read")],
    "skf-create-skill": [("report.md", "**Post-completion hook.**", "**Remove the run folder.**",
                          "skip the hook and display the line for its case")],
    "skf-create-stack-skill": [("report.md", "### 2c.", "### 3.",
                                '"on_complete skipped: no result contract was written ({reason})"')],
    "skf-drop-skill": [("report.md", "### Post-drop hook (optional)", "### 3.", "`{result_json_path}` is not null")],
    "skf-export-skill": [("summary.md", "### 6b.", "### 7.", "when `{result_path}` is null")],
    "skf-quick-skill": [("finalize.md", "**Post-completion hook (optional).**", "In a single-target run",
                         "skip the hook and say so")],
    "skf-refine-architecture": [("report.md", "### 5. Post-Completion Hook", "### 6.",
                                 "When `{result_path}` is null, skip it too")],
    "skf-rename-skill": [("report.md", "### 3. Post-Completion Hook", "### 4.",
                          "when `{result_path}` is null, skip it")],
    "skf-test-skill": [("report.md", "**Post-finalization hook.**", "### 6.", "`{result_path}` is not null")],
    "skf-update-skill": [("report.md", "**Post-finalization hook.**", "### 6.", "skip it and say why")],
}
HOOK_STAGE_CASES = [(skill, *stage) for skill, stages in HOOK_STAGES.items() for stage in stages]
UNQUOTED_PATH = re.compile(r"--(?:result|report)-path=(?!\")")


def test_each_on_complete_comment_is_a_shell_command_or_an_instruction():
    """#1109: a command-style comment says it is a shell command, gives the
    BMad core contrast and quotes the path it shows; an instruction-style
    comment opens by saying it is one. Setup Forge and Verify Stack alone are
    instructions, and every other workflow has a stage in HOOK_STAGES."""
    command, instruction = set(), set()
    for skill in WORKFLOWS:
        comment = _flat(_flat_comment(skill, "on_complete"))
        if "shell command" in comment and HOOK_CONTRAST in comment:
            assert not UNQUOTED_PATH.search(comment), f"{skill}: customize.toml shows an unquoted path"
            command.add(skill)
        elif re.match(r"(An instruction|Instruction)\b", comment) and "hands the value to the shell" not in comment:
            instruction.add(skill)
        else:
            pytest.fail(f"{skill}: customize.toml describes on_complete in neither documented form: {comment[:120]}")
    assert instruction == INSTRUCTION_HOOKS, sorted(instruction ^ INSTRUCTION_HOOKS)
    assert command == set(HOOK_STAGES), sorted(command ^ set(HOOK_STAGES))


@pytest.mark.parametrize("skill,name,start,end,skip", HOOK_STAGE_CASES,
                         ids=[f"{case[0]}:{case[1]}" for case in HOOK_STAGE_CASES])
def test_every_command_style_stage_runs_the_hook_the_same_way(skill, name, start, end, skip):
    """#1109: the quoted path, the `{project-root}` working directory, a
    failure that never fails the run, and the skip when there is no file."""
    text = _read(SRC / skill / "references" / name)
    assert start in text, f"{skill} {name}: no {start!r}"
    stage = text.split(start, 1)[1]
    assert end in stage, f"{skill} {name}: no {end!r} after {start!r}"
    stage = stage.split(end, 1)[0]
    campaign = skill == "skf-campaign"
    hook = "{onComplete}" if campaign else "{onCompleteCommand}"
    flag = "--report-path" if campaign else "--result-path"
    assert f'{hook} {flag}="' in stage, f"{skill} {name}: the hook's path is not quoted"
    # The call as the shell reads it in a project whose path holds a space: the path stays one argument.
    call = re.search(re.escape(f"{hook} {flag}=") + r'"[^"\n]*"', stage)
    assert call, f"{skill} {name}: the hook's quoted path does not close on its line"
    words = shlex.split(re.sub(r"\{[^}]+\}", "/a b", call.group(0).replace(hook, "hook", 1)))
    assert len(words) == 2 and words[1].startswith(f"{flag}=/a b"), (
        f"{skill} {name}: {call.group(0)} splits into {words}")
    assert not UNQUOTED_PATH.search(stage), f"{skill} {name}: an unquoted path"
    assert "from `{project-root}`" in stage, f"{skill} {name}: no working directory for the hook"
    assert re.search(r"(?i)\bnever fails? the\b", stage), f"{skill} {name}: a hook failure may fail the run"
    assert skip in stage, f"{skill} {name}: no skip when there is no result file"


def _step_01_init_args(**values: str) -> list[str]:
    """The quality-gate arguments step-01 §2 passes to campaign-state.py init."""
    step = _read(SRC / "skf-campaign" / "references" / "step-01-setup.md")
    [command] = [line for line in step.splitlines() if " init --state-file " in line]
    gate = command.split(" init ", 1)[1]
    for name, value in values.items():
        gate = gate.replace(f"{{{name}}}", value)
    tokens = re.findall(r'--(hard|soft-target|soft-fallback) "?([^"\s]+)"?', gate)
    assert [t[0] for t in tokens] == ["soft-target", "soft-fallback"], gate
    return [part for flag, value in tokens for part in (f"--{flag}", value)]


def _campaign_init(tmp_path: Path, table: dict) -> dict:
    targets = tmp_path / "targets.json"
    targets.write_bytes(json.dumps({"targets": [{"name": "zod", "tier": "A"}], "errors": []}).encode("utf-8"))
    state = tmp_path / "_campaign-state.yaml"
    args = _step_01_init_args(qualityGateSoftTarget=str(table["quality_gate_soft_target"]),
                              qualityGateSoftFallback=str(table["quality_gate_soft_fallback"]))
    script = SRC / "skf-campaign" / "scripts" / "campaign-state.py"
    proc = subprocess.run([sys.executable, str(script), "init", "--state-file", str(state), "--targets-file",
                           str(targets), "--name", "demo", *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return yaml.safe_load(state.read_bytes().decode("utf-8"))["campaign"]["quality_gate"]


def test_campaign_quality_gate_overrides_change_the_state(tmp_path):
    """Passed as step-01 passes them, the bundled values and an override each
    reach the state campaign-state.py writes."""
    bundled = _workflow_table("skf-campaign")
    first = tmp_path / "bundled"
    first.mkdir()
    assert _campaign_init(first, bundled) == {
        "hard": "zero-critical-high",
        "soft_target": bundled["quality_gate_soft_target"],
        "soft_fallback": bundled["quality_gate_soft_fallback"],
    }
    override = {**bundled, "quality_gate_soft_target": 95, "quality_gate_soft_fallback": 85}
    second = tmp_path / "override"
    second.mkdir()
    gate = _campaign_init(second, override)
    assert (gate["soft_target"], gate["soft_fallback"]) == (95, 85)


# --------------------------------------------------------------------------
# The `!` persistent_facts rule
# --------------------------------------------------------------------------


FACT_SKILLS = [skill for skill in WORKFLOWS if _workflow_table(skill)["persistent_facts"]]
# #1107 (the maintainer's 2026-11-12 decision): no Drop Skill stage reads the project context, and Brief, Create
# and Test Skill load it in each run a campaign starts, so these two ship no default and show the override that
# loads it anyway.
NO_DEFAULT = ("skf-campaign", "skf-drop-skill")
OPT_IN = f'#   [workflow]\n#   persistent_facts = ["{DEFAULT_FACT}"]\n'
# Workflows that read the project context and say the default is kept on purpose.
KEPT_ON_PURPOSE = ("skf-audit-skill", "skf-brief-skill", "skf-test-skill")


def _example(skill: str) -> str:
    """The override lines the persistent_facts comment shows after naming the override file, `#` markers kept."""
    return _comment_above(skill, "persistent_facts").split(f"{{project-root}}/_bmad/custom/{skill}.toml:\n", 1)[1]


def _opt_in(skill: str) -> dict:
    """The override the persistent_facts comment shows, `#` markers dropped, read as the override file it is."""
    return tomllib.loads("\n".join(line.removeprefix("#").strip() for line in _example(skill).splitlines()))


def test_only_setup_drop_and_campaign_ship_no_project_context_default():
    assert sorted(set(WORKFLOWS) - set(FACT_SKILLS)) == sorted(("skf-setup", *NO_DEFAULT))
    assert len(FACT_SKILLS) == 12, FACT_SKILLS
    for skill in FACT_SKILLS:
        assert _workflow_table(skill)["persistent_facts"] == [DEFAULT_FACT], skill
    for skill in ("skf-setup", *NO_DEFAULT):
        assert _workflow_table(skill)["persistent_facts"] == [], skill


@pytest.mark.parametrize("skill", FACT_SKILLS + list(NO_DEFAULT))
def test_activation_drops_a_bang_entry_and_the_entry_it_names(skill):
    sentences = [s for s in re.split(r"(?<=[.;])\s+(?=[A-Z])", _flat(_activation(skill)))
                 if "workflow.persistent_facts" in s]
    assert sentences, f"{skill}: On Activation never loads workflow.persistent_facts"
    sentence = " ".join(sentences)
    assert "`!" in sentence and re.search(r"\bdrops?\b", sentence) and "entry it names" in sentence, (
        f"{skill}: the persistent_facts sentence does not say that a `!` entry drops each entry it names")


@pytest.mark.parametrize("skill", FACT_SKILLS)
def test_customize_toml_shows_the_drop_override(skill):
    comment = _comment_above(skill, "persistent_facts")
    assert DROP_OVERRIDE in comment, f"{skill}: the persistent_facts comment does not show the `!` override"
    assert f"{{project-root}}/_bmad/custom/{skill}.toml" in comment, skill
    stale = [phrase for phrase in STALE_FACT_ADVICE if phrase in comment.lower()]
    assert not stale, f"{skill}: the persistent_facts comment still says {stale}"


@pytest.mark.parametrize("skill", FACT_SKILLS + list(NO_DEFAULT))
def test_the_persistent_facts_example_is_written_under_the_workflow_table(skill):
    """#1108: the resolver reads `--key workflow`, so the example a team copies opens with the `[workflow]` line;
    without it the key lands at the file's root, and the default stays loaded with no warning."""
    entry = DEFAULT_FACT if skill in NO_DEFAULT else f"!{DEFAULT_FACT}"
    assert _example(skill) == f'#   [workflow]\n#   persistent_facts = ["{entry}"]\n', (
        f"{skill}: the persistent_facts example is not the two lines `[workflow]` then `persistent_facts = [...]`")
    assert _opt_in(skill) == {"workflow": {"persistent_facts": [entry]}}, skill
    comment = _comment_above(skill, "persistent_facts").lower()
    stale = [phrase for phrase in STALE_FACT_ADVICE if phrase in comment]
    assert not stale, f"{skill}: the persistent_facts comment still says {stale}"


@pytest.mark.parametrize("skill", NO_DEFAULT)
def test_customize_toml_shows_the_override_that_loads_the_project_context(skill):
    comment = _comment_above(skill, "persistent_facts")
    assert "# Ships empty: " in comment, skill
    assert f"{{project-root}}/_bmad/custom/{skill}.toml:\n{OPT_IN}" in comment, (
        f"{skill}: the persistent_facts comment does not end with the two-line opt-in")
    assert _opt_in(skill) == {"workflow": {"persistent_facts": [DEFAULT_FACT]}}, skill
    assert "!file:" not in comment and "The default below" not in comment, skill
    # A personal override can still drop an entry the team override adds, so the `!` bullet stays.
    assert "an entry prefixed with `!`, which loads nothing and drops each earlier" in comment, skill
    for stale in ("cannot remove it", "add a literal fact", "Each entry is either", "kickoff_template_path"):
        assert stale not in comment, (skill, stale)


@pytest.mark.parametrize("skill", KEPT_ON_PURPOSE)
def test_a_workflow_that_reads_the_project_context_keeps_the_default_on_purpose(skill):
    comment = " ".join(line.lstrip("#").strip() for line in _comment_above(skill, "persistent_facts").splitlines())
    assert ("The default below loads every project-context.md under {project-root} and is kept on purpose: this "
            "workflow reads the project context (Drop Skill and Campaign, which do not need it, ship none). A `!` "
            "entry in an override drops it; to stop loading those files, set in "
            f"{{project-root}}/_bmad/custom/{skill}.toml:") in comment, skill
    assert "cannot delete it" not in comment, skill


# --------------------------------------------------------------------------
# The file scalars' defaults (#1108)
# --------------------------------------------------------------------------


FILE_SCALARS = [(skill, key) for skill, key in SCALARS if ALLOWED[skill][key][1] == "file"]
# The file scalars that ship an empty string today. The test never requires them to stay empty: one that gains
# a bundled default leaves this set, and the check below then holds it to a file the skill bundles.
STILL_EMPTY = {
    ("skf-refine-architecture", "refinement_rules_path"),
    ("skf-verify-stack", "report_template_path"),
}
# The sentence a template comment gives for a house-style copy: a bare path resolves from the skill root, which
# every update overwrites.
OUTSIDE_THE_SKILL = ("Keep a house-style copy outside the skill folder, which every update overwrites, and name it "
                     "as {project-root}/<path to the copy>.")
EMPTY_MEANS_DEFAULT = "# --- Optional overrides. An empty string means the default named below. ---\n"


def _flat_comment(skill: str, key: str) -> str:
    return " ".join(line.lstrip("#").strip() for line in _comment_above(skill, key).splitlines())


def test_still_empty_names_file_scalars():
    assert STILL_EMPTY <= set(FILE_SCALARS), STILL_EMPTY - set(FILE_SCALARS)


@pytest.mark.parametrize("skill,key", FILE_SCALARS, ids=[f"{s}:{k}" for s, k in FILE_SCALARS])
def test_each_file_scalar_default_names_a_bundled_file(skill, key):
    value = _workflow_table(skill)[key]
    assert isinstance(value, str), (skill, key, value)
    if (skill, key) not in STILL_EMPTY:
        assert value, f"{skill}: {key} ships an empty string instead of naming its bundled default"
    if value:
        assert not value.startswith(("/", "{")) and (SRC / skill / value).is_file(), (
            f"{skill}: {key} = {value!r} names no file under src/{skill}/")


@pytest.mark.parametrize("skill,key", [
    ("skf-audit-skill", "drift_report_template_path"),
    ("skf-test-skill", "test_report_template_path"),
    ("skf-create-stack-skill", "stack_skill_template_path"),
    ("skf-quick-skill", "skill_template_path"),
    ("skf-export-skill", "snippet_format_path"),
])
def test_a_template_comment_keeps_the_house_copy_outside_the_skill(skill, key):
    comment = _flat_comment(skill, key)
    value = _workflow_table(skill)[key]
    assert f"Default: {value}, a path from the skill root." in comment, (skill, key)
    assert OUTSIDE_THE_SKILL in comment, (skill, key)


def test_campaign_ships_its_real_path_defaults():
    """#1110: the workspace and the three templates name their defaults, and the comments say how a path
    resolves, so an org copy starts with {project-root}/."""
    workflow = _workflow_table("skf-campaign")
    assert workflow["campaign_workspace_path"] == "{forge_data_folder}/_campaign"
    workspace = _flat_comment("skf-campaign", "campaign_workspace_path")
    assert "Default: {forge_data_folder}/_campaign (an empty string means the same)." in workspace
    assert ("a bare path resolves from the skill root, which every update overwrites, so name the folder as "
            "{project-root}/<folder> or an absolute path.") in workspace
    assert workflow["report_template_path"] == "templates/campaign-report-template.md"
    assert workflow["kickoff_template_path"] == "templates/kickoff-template.md"
    assert "brief_template_path" not in workflow
    text = _customize("skf-campaign")
    assert "# --- Optional template overrides. An empty string means the default named below. ---\n" in text
    comment = _flat_comment("skf-campaign", "report_template_path")
    assert "Each defaults to its bundled file under templates/, a path from the skill root." in comment
    assert OUTSIDE_THE_SKILL in comment
    assert ("On Activation step 3 halts the campaign (exit 2, `invalid-input`) on one that names no readable file, "
            "before Setup or a resume (`campaign status` skips it).") in comment
    assert "Empty string = use the bundled default" not in text


@pytest.mark.parametrize("skill", ("skf-test-skill", "skf-create-stack-skill"))
def test_the_overrides_header_says_what_an_empty_string_means(skill):
    text = _customize(skill)
    assert EMPTY_MEANS_DEFAULT in text, skill
    for gone in ("Optional asset overrides", "Empty string = use the bundled default"):
        assert gone not in text, (skill, gone)


def _kickoff_module():
    path = SRC / "skf-campaign" / "scripts" / "campaign-render-kickoff.py"
    spec = importlib.util.spec_from_file_location("campaign_render_kickoff_surface", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_kickoff_loads_the_project_context_only_when_an_override_adds_it(tmp_path):
    """Campaign's facts reach each Tier A kickoff through load_facts, not
    activation prose: the bundled list loads nothing (#1107), the team
    override the comment shows, appended as BMad's resolver appends arrays,
    loads the project-context.md, and a later `!` entry in the personal
    override drops it again."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "project-context.md").write_bytes(b"House rule.\n")
    load_facts = _kickoff_module().load_facts
    bundled = _workflow_table("skf-campaign")["persistent_facts"]
    assert bundled == [] and load_facts(bundled, str(tmp_path)) == []
    team = _opt_in("skf-campaign")["workflow"]["persistent_facts"]
    [fact] = load_facts(bundled + team, str(tmp_path))
    assert "House rule." in fact
    user = tomllib.loads(DROP_OVERRIDE.lstrip("# "))["persistent_facts"]
    assert user == [f"!{DEFAULT_FACT}"]
    assert load_facts(bundled + team + user, str(tmp_path)) == []
    assert load_facts([*bundled, *team, "Cite sources.", *user], str(tmp_path)) == ["Cite sources."]
