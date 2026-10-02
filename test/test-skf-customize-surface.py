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
- each on_complete comment says whether the value is a command (named, or
  shown with the arguments the run appends) or an instruction;
- the `!` persistent_facts rule (the maintainer's 2026-10-02 decision): for
  every workflow that ships a non-empty persistent_facts (all but skf-setup),
  the On Activation persistent_facts sentence drops a `!` entry and each
  earlier entry it names, the customize.toml comment above persistent_facts
  shows `persistent_facts = ["!file:{project-root}/**/project-context.md"]`
  and never says an override cannot remove the default or suggests a
  counter-fact, and campaign's kickoff loader drops the default for that
  override.

skf-forger is not a workflow: its customize.toml holds an [agent] block.
"""

from __future__ import annotations

import importlib.util
import json
import re
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
        "quality_gate_hard": ("qualityGateHard", "script"),
        "quality_gate_soft_target": ("qualityGateSoftTarget", "script"),
        "quality_gate_soft_fallback": ("qualityGateSoftFallback", "script"),
        "report_template_path": ("reportTemplatePath", "file"),
        "kickoff_template_path": ("kickoffTemplatePath", "file"),
        "brief_template_path": ("briefTemplatePath", "file"),
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
STALE_FACT_ADVICE = ("cannot remove it", "add a literal fact", "counter-fact", "counter fact")


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


@pytest.mark.parametrize("skill,key", SCALARS, ids=[f"{s}:{k}" for s, k in SCALARS])
def test_each_scalar_reaches_a_stage(skill, key):
    variable, kind = ALLOWED[skill][key]
    placeholder = f"{{{variable}}}"
    readers = [path for path in _stage_files(skill) if placeholder in _read(path)]
    assert readers, f"{skill}: workflow.{key} is bound to {placeholder}, which no stage file reads"
    if kind == "script":
        commands = [line for path in readers for line in _read(path).splitlines()
                    if placeholder in line and re.search(r"\buv run\b", line)]
        assert commands, f"{skill}: {placeholder} reaches no helper command"


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_each_on_complete_comment_says_what_it_runs(skill):
    """A command, shown or named, or an instruction the agent carries out."""
    comment = _comment_above(skill, "on_complete")
    assert re.search(r"(?i)\bcommand\b|\binstruction\b", comment) or "<on_complete> --" in comment, (
        f"{skill}: the on_complete comment does not say whether the value is a command or an instruction")


def _step_01_init_args(**values: str) -> list[str]:
    """The quality-gate arguments step-01 §2 passes to campaign-state.py init."""
    step = _read(SRC / "skf-campaign" / "references" / "step-01-setup.md")
    [command] = [line for line in step.splitlines() if " init --state-file " in line]
    gate = command.split(" init ", 1)[1]
    for name, value in values.items():
        gate = gate.replace(f"{{{name}}}", value)
    tokens = re.findall(r'--(hard|soft-target|soft-fallback) "?([^"\s]+)"?', gate)
    assert [t[0] for t in tokens] == ["hard", "soft-target", "soft-fallback"], gate
    return [part for flag, value in tokens for part in (f"--{flag}", value)]


def _campaign_init(tmp_path: Path, table: dict) -> dict:
    targets = tmp_path / "targets.json"
    targets.write_bytes(json.dumps({"targets": [{"name": "zod", "tier": "A"}], "errors": []}).encode("utf-8"))
    state = tmp_path / "_campaign-state.yaml"
    args = _step_01_init_args(qualityGateHard=str(table["quality_gate_hard"]),
                              qualityGateSoftTarget=str(table["quality_gate_soft_target"]),
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
        "hard": bundled["quality_gate_hard"],
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


def test_every_workflow_but_setup_ships_the_project_context_default():
    assert sorted(set(WORKFLOWS) - set(FACT_SKILLS)) == ["skf-setup"]
    for skill in FACT_SKILLS:
        assert _workflow_table(skill)["persistent_facts"] == [DEFAULT_FACT], skill


@pytest.mark.parametrize("skill", FACT_SKILLS)
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


def _kickoff_module():
    path = SRC / "skf-campaign" / "scripts" / "campaign-render-kickoff.py"
    spec = importlib.util.spec_from_file_location("campaign_render_kickoff_surface", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_kickoff_drops_the_default_for_the_documented_override(tmp_path):
    """Campaign's facts reach each Tier A kickoff through load_facts, not
    activation prose: the override the comment shows, appended to the
    bundled default as BMad's resolver appends arrays, leaves no fact."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "project-context.md").write_bytes(b"House rule.\n")
    load_facts = _kickoff_module().load_facts
    bundled = _workflow_table("skf-campaign")["persistent_facts"]
    assert len(load_facts(bundled, str(tmp_path))) == 1
    override = tomllib.loads(DROP_OVERRIDE.lstrip("# "))["persistent_facts"]
    assert override == [f"!{DEFAULT_FACT}"]
    assert load_facts(bundled + override, str(tmp_path)) == []
    assert load_facts([*bundled, "Cite sources.", *override], str(tmp_path)) == ["Cite sources."]
