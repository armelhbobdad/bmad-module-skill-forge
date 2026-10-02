#!/usr/bin/env python3
"""On Activation's customization step and path rules in ten workflows
(#595, #596, #601, #603; stage 6b of the v3.0.0 plan).

The ten workflows are analyze-source, brief, campaign, create, create-stack,
quick, refine-architecture, rename, test and verify-stack; the other five get
the same block from their own stage-6b package, and a later test compares the
block across all sixteen activations.

- #595 (option a): each runs BMad core's resolver through `uv run` with
  `--project-root`, prints one `customization_resolver_unavailable` line when
  it cannot run, reads the bundled customize.toml alone, and sends the reason
  the way its result goes: the run sink, brief's warning list, campaign's
  decision log, or test-skill's result context. A sink route records the
  reason in the step that creates or binds the run folder, and every command
  that carries it keeps a reason that holds quotes or `$( )` as plain text.
- #596 (the maintainer's 2026-10-02 decision): a `!` persistent_facts entry
  drops the bundled project-context.md default; SKILL.md says so and each
  customize.toml shows the override, with no "cannot remove it" left.
- #601: each Conventions block states the module-level path exception, and
  the sibling-skill rule wherever the skill names another skill's folder.
- #603: headless_mode is read from `{sidecar_path}/preferences.yaml`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
EMITTER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"

# Each workflow's customization step heading and the heading of the step after it.
STEPS = {
    "skf-analyze-source": ("4. **Resolve workflow customization.**", "5. **Create the run folder.**"),
    "skf-brief-skill": ("3. **Resolve workflow customization.**", "4. **Resolve the envelope emitter**"),
    "skf-campaign": ("3. **Resolve workflow customization.**", "4. **Parse CLI overrides**"),
    "skf-create-skill": ("3. **Resolve workflow customization.**", "4. Resolve `{emitEnvelopeHelper}`"),
    "skf-create-stack-skill": ("3. **Resolve workflow customization.**", "4. Load, read the full file"),
    "skf-quick-skill": ("3. **Resolve workflow customization.**", "4. **Parse CLI overrides**"),
    "skf-refine-architecture": ("4. **Resolve workflow customization.**", "5. **Pre-flight"),
    "skf-rename-skill": ("3. **Resolve workflow customization.**", "4. Load, read the full file"),
    "skf-test-skill": ("3. **Resolve workflow customization.**", "4. Load, read the full file"),
    "skf-verify-stack": ("4. **Resolve workflow customization.**", "5. **Pre-flight: the emitter.**"),
}
WORKFLOWS = sorted(STEPS)

COMMAND = ("uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} "
           "--project-root {project-root} --key workflow")
WARNING = "`[activation/warn] customization_resolver_unavailable: <reason>`"
FALLBACK = ("If the resolver cannot run, read `{skill-root}/customize.toml` alone and use its bundled defaults: "
            "the `{project-root}/_bmad/custom/` overrides do not apply to this run.")
RECORD = ('`uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" '
          '--warning "$(cat "{run_dir}/resolver-warning.txt")"`')
# Where each workflow sends the reason: the route its result takes.
ROUTES = {
    "skf-analyze-source": ("for step 5 to record in the run sink", RECORD),
    "skf-brief-skill": ("add `customization_resolver_unavailable: <reason>` to `workflow_warnings[]`",),
    "skf-campaign": ("log `customization_resolver_unavailable: <reason>` as an `event` in the decision log",
                     "unless the invocation is `campaign status` (which writes nothing)"),
    "skf-create-skill": ("for step 1 §0 to record in each brief's run folder",),
    "skf-create-stack-skill": ("`references/init.md` records it as the run's first warning",),
    "skf-quick-skill": ("record it in the run sink", RECORD,
                        "Under `--batch`, `references/batch-mode.md` §2 records that file in each target's run folder"),
    "skf-refine-architecture": ("for §5 to record",),
    "skf-rename-skill": ("for select.md §1 to record once it has created `{run_dir}`",),
    "skf-test-skill": ("keep the reason as `{customization_resolver_unavailable}`: report.md §4c hands it to the "
                       "result as a warning",),
    "skf-verify-stack": ("for init.md to record once it has created `{run_dir}`",),
}

FACTS_CLAUSE = ("the bundled default loads every `project-context.md` under `{project-root}`; an entry prefixed "
                "`!` drops each earlier entry it names and loads nothing itself, so an override's "
                "`\"!file:{project-root}/**/project-context.md\"` turns that default off")
# The workflows whose SKILL.md gains the clause here; brief, create and rename shipped their own wording.
FACTS_CLAUSE_SKILLS = ("skf-analyze-source", "skf-campaign", "skf-create-stack-skill", "skf-quick-skill",
                       "skf-refine-architecture", "skf-test-skill", "skf-verify-stack")
CUSTOMIZE_CHANGED = ("skf-analyze-source", "skf-campaign", "skf-create-stack-skill", "skf-quick-skill",
                     "skf-refine-architecture", "skf-rename-skill", "skf-test-skill", "skf-verify-stack")
DEFAULT_FACT = "file:{project-root}/**/project-context.md"

MODULE_RULE = ("- **Module-level path exception:** bare paths beginning with `knowledge/` or `shared/` resolve "
               "from the SKF module root (`{project-root}/_bmad/skf/` installed, `src/` in dev), not the skill root")
SIBLING_RULE = ("- **Sibling skills:** a path that names another SKF skill's folder (`skf-<name>/...`) resolves "
                "from the SKF module root, and that skill must be installed with this one.")
SIBLING_PATH = re.compile(r"(?<![\w/.-])(skf-[a-z-]+)/(?:references|assets|scripts|templates)/")

POSIX_BASH = os.name != "nt" and shutil.which("bash") is not None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_md(skill: str) -> str:
    return _read(SRC / skill / "SKILL.md")


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def _activation(skill: str) -> str:
    """The On Activation section, up to the next heading or the end of the file."""
    return _skill_md(skill).split("## On Activation", 1)[1].split("\n## ", 1)[0]


def _step(skill: str) -> str:
    start, end = STEPS[skill]
    return _section(_skill_md(skill), start, end)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --------------------------------------------------------------------------
# #595: the resolver runs through uv, warns once and falls back to the defaults
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_the_resolver_runs_through_uv_with_the_project_root(skill):
    step = _step(skill)
    fences = re.findall(r"```bash\n(.*?)```", step, re.S)
    assert [line.strip() for fence in fences for line in fence.splitlines() if line.strip()] == [COMMAND], skill
    assert "python3 {project-root}/_bmad/scripts/resolve_customization.py" not in _skill_md(skill)


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_a_resolver_that_cannot_run_prints_one_warning_and_uses_the_defaults(skill):
    step = _flat(_step(skill))
    assert step.count("When it exits non-zero, prints no JSON or is missing, print one line, " + WARNING) == 1
    assert step.count(FALLBACK) == 1
    assert "fall back to reading `{skill-root}/customize.toml` directly" not in step
    # The warning comes first, then the fallback, then where the reason goes.
    assert step.index(WARNING) < step.index(FALLBACK) < step.index("In that case")


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_the_override_layers_are_named_from_the_project_root(skill):
    step = _flat(_step(skill))
    assert f"`{{project-root}}/_bmad/custom/{skill}.toml` (team overrides, committed)" in step
    assert "(personal overrides, gitignored)" in step
    assert "_bmad/custom/<skill-name>.toml` under `{project-root}`" not in _skill_md(skill)


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_the_reason_takes_the_route_the_result_takes(skill):
    flat = _flat(_activation(skill))
    for needle in ROUTES[skill]:
        assert needle in flat, (skill, needle)


def test_the_late_routes_record_once_the_run_folder_exists():
    """Analyze-source and refine-architecture record in the step that creates the run folder, after it."""
    for skill, folder_step, nxt in (("skf-analyze-source", "5. **Create the run folder.**", "6. Run"),
                                    ("skf-refine-architecture", "**Run folder (exit 4).**", "6. Load")):
        step = _flat(_section(_skill_md(skill), folder_step, nxt))
        assert step.index("mkdir -p") < step.index("Once the folder exists" if skill == "skf-analyze-source"
                                                   else "Once it exists") < step.index(RECORD), skill
        assert "`{customization_resolver_unavailable}` is set, record the reason in the run sink" in step


RECORD_RE = re.compile(r'`(uv run \{emitEnvelopeHelper\} record --run-dir "\{run_dir\}" '
                       r'--warning "\$\(cat "\{(?:run_dir|batch_dir)\}/([a-z-]+\.txt)"\)")`')
REFERENCES = {skill: SRC / skill / "references" for skill in WORKFLOWS}
CREATE_STACK_INIT = REFERENCES["skf-create-stack-skill"] / "init.md"
# The stage that creates or binds each run folder records the reason there, so the record never waits in
# context: (file, section start, section end, the line that creates or binds the folder).
BIND_SITES = {
    "skf-create-skill": (REFERENCES["skf-create-skill"] / "load-brief.md", "### 0. Start the Run Folder", "### 1. ",
                         "Bind `{run_dir}` ← the path it prints"),
    "skf-quick-skill": (REFERENCES["skf-quick-skill"] / "batch-mode.md", '- **`"status": "next"`**',
                        '- **`"status": "record"`**', "Bind `{run_dir}` ← its `run_dir`"),
    "skf-rename-skill": (REFERENCES["skf-rename-skill"] / "select.md", "### 1. Start the Run", "### 2. ",
                         'for dir in "{run_dir}"'),
    "skf-verify-stack": (REFERENCES["skf-verify-stack"] / "init.md", "**Pre-flight: run folder and write probe.**",
                         "Then check that `forge_data_folder`", 'mkdir "{run_dir}"'),
}
HOSTILE_REASON = "customization_resolver_unavailable: No module named 'tomllib' \"x\" $(touch pwned) `touch pwned2`"


def _bind_site(skill: str) -> str:
    path, start, end, _ = BIND_SITES[skill]
    return _flat(_section(_read(path), start, end))


def _record_commands() -> list:
    """Each documented record command that reads the reason from a file, as the file documents it."""
    sources = [(skill, _activation(skill)) for skill in WORKFLOWS]
    sources += [(f"{skill}/{path.name}", _read(path)) for skill, (path, *_) in sorted(BIND_SITES.items())]
    sources.append(("create-stack/init.md", _read(CREATE_STACK_INIT)))
    found = []
    for label, text in sources:
        for n, (command, name) in enumerate(RECORD_RE.findall(text), 1):
            found.append(pytest.param(command, name, id=f"{label}#{n}"))
    return found


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented record command in a POSIX bash")
@pytest.mark.parametrize("command,name", _record_commands())
def test_the_record_command_keeps_a_hostile_reason_as_text(tmp_path, command, name):
    """The reason reaches the sink exactly as written: a quote, `$( )` or a backtick runs nothing."""
    run_dir = tmp_path / "skf-x-20261002"
    run_dir.mkdir()
    (run_dir / name).write_bytes((HOSTILE_REASON + "\n").encode("utf-8"))
    filled = (command.replace("uv run {emitEnvelopeHelper}", f'"{sys.executable}" "{EMITTER.as_posix()}"')
              .replace("{run_dir}", run_dir.as_posix()).replace("{batch_dir}", run_dir.as_posix()))
    proc = subprocess.run(["bash", "-c", filled], capture_output=True, timeout=60, cwd=run_dir)
    assert proc.returncode == 0, proc.stderr
    lines = (run_dir / "warnings.jsonl").read_bytes().decode("utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [HOSTILE_REASON]
    assert not (run_dir / "pwned").exists() and not (run_dir / "pwned2").exists()


def test_every_file_route_documents_its_record_command():
    """Each sink route records the reason from a file: in the activation of analyze-source, quick and
    refine-architecture, which create their run folder there, and else in the stage that does."""
    assert sorted(param.id for param in _record_commands()) == [
        "create-stack/init.md#1", "skf-analyze-source#1", "skf-create-skill/load-brief.md#1",
        "skf-create-skill/load-brief.md#2", "skf-quick-skill#1", "skf-quick-skill/batch-mode.md#1",
        "skf-refine-architecture#1", "skf-rename-skill/select.md#1", "skf-verify-stack/init.md#1"]


@pytest.mark.parametrize("skill", sorted(BIND_SITES))
def test_the_stage_that_makes_the_run_folder_records_the_reason(skill):
    """The record comes right after the folder is created or bound, in the file that does it."""
    site = _bind_site(skill)
    made = BIND_SITES[skill][3]
    assert site.index(made) < site.index('record --run-dir "{run_dir}" --warning "$(cat'), skill
    assert "`{customization_resolver_unavailable}`" in site or "`{batch_dir}/resolver-warning.txt` exists" in site
    if skill != "skf-quick-skill":
        assert "record --run-dir" not in _activation(skill), skill


def test_a_batch_keeps_the_reason_on_disk_for_every_target():
    """A --batch run reads the reason from the batch folder, so a target after a compaction still records it."""
    quick_batch = _read(BIND_SITES["skf-quick-skill"][0])
    assert "`{batch_dir}` is the run folder SKILL.md On Activation step 1 created" in quick_batch
    create_start = _flat(_section(_read(REFERENCES["skf-create-skill"] / "batch-mode.md"), "### 1. Start the Batch",
                                  "### 2. "))
    assert ("write `customization_resolver_unavailable: {customization_resolver_unavailable}` to "
            "`{batch_dir}/resolver-warning.txt` with a file write") in create_start
    for skill in ("skf-create-skill", "skf-quick-skill"):
        site = _bind_site(skill)
        assert "`{batch_dir}/resolver-warning.txt` exists" in site, skill
        assert '--warning "$(cat "{batch_dir}/resolver-warning.txt")"' in site, skill
    rename = _bind_site("skf-rename-skill")
    assert rename.index("--warning") < rename.index('`rm -f "{run_dir}/resolver-warning.txt"`')


# The halts that come before the run folder, and the heredoc each passes its payload in.
EARLY_HALTS = {
    "skf-analyze-source": (SRC / "skf-analyze-source" / "SKILL.md", "SKF_ANALYZE_HALT",
                           'its payload with `"customization_resolver_unavailable": "<reason>"` added when step 4 '
                           "kept one"),
    "skf-create-skill": (BIND_SITES["skf-create-skill"][0], "SKF_JSON",
                         'adding `"customization_resolver_unavailable": "<reason>"` to the payload when On '
                         "Activation step 3 kept one"),
    "skf-refine-architecture": (SRC / "skf-refine-architecture" / "SKILL.md", "SKF_RA_HALT",
                                'with `"customization_resolver_unavailable": "<reason>"` added when step 4 kept one'),
    "skf-verify-stack": (BIND_SITES["skf-verify-stack"][0], "SKF_VS_HALT",
                         'with `"customization_resolver_unavailable": "<reason>"` added when SKILL.md On Activation '
                         "step 4 kept one"),
}


@pytest.mark.parametrize("skill", sorted(EARLY_HALTS))
def test_a_halt_before_the_run_folder_carries_the_reason(skill):
    """With no sink yet, the payload carries the reason, and the emitter turns it into the envelope's warning."""
    path, tag, rule = EARLY_HALTS[skill]
    text = _read(path)
    assert rule in _flat(text), skill
    shown = re.search(rf"<<'{tag}'\n\s*(\{{.*?\}})\n\s*{tag}", text, re.S)
    assert shown, skill
    payload = json.loads(shown.group(1).replace("<halt_reason>", "write-failed"))
    payload["customization_resolver_unavailable"] = HOSTILE_REASON.split(": ", 1)[1]
    proc = subprocess.run([sys.executable, str(EMITTER), "emit-halt", "--workflow", skill, "--target", "stderr"],
                          input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    [line] = [line for line in proc.stderr.decode("utf-8").splitlines() if "_RESULT_JSON: " in line]
    envelope = json.loads(line.split("_RESULT_JSON: ", 1)[1])
    assert HOSTILE_REASON in envelope["warnings"], skill


@pytest.mark.skipif(not POSIX_BASH, reason="runs the documented argument in a POSIX bash")
def test_test_skill_passes_the_reason_as_one_literal_argument(tmp_path):
    """report.md §4c reads the reason from a file, so build-result-context.py gets it as one argument."""
    report = _read(REFERENCES["skf-test-skill"] / "report.md")
    [argument] = re.findall(r'\[(--warning "\$\(cat "\{run_dir\}/resolver-warning\.txt"\)")\]', report)
    (tmp_path / "resolver-warning.txt").write_bytes((HOSTILE_REASON + "\n").encode("utf-8"))
    script = (f'"{sys.executable}" -c "import json, sys; print(json.dumps(sys.argv[1:]))" '
              + argument.replace("{run_dir}", tmp_path.as_posix()))
    proc = subprocess.run(["bash", "-c", script], capture_output=True, timeout=60, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8")) == ["--warning", HOSTILE_REASON]
    assert not (tmp_path / "pwned").exists() and not (tmp_path / "pwned2").exists()


def test_create_stack_records_the_reason_in_its_pre_flight():
    init = _read(CREATE_STACK_INIT)
    rule = _section(init, "**Resolver warning.**", "### 0. Validate Project Config")
    assert init.index("Bind `{run_dir}`") < init.index("**Resolver warning.**")
    for needle in ("`[activation/warn] customization_resolver_unavailable: {customization_resolver_unavailable}`",
                   "`{run_dir}/warning.txt` with a file write", "never an `echo` or a quoted `--warning` argument",
                   "then run the `record` command above"):
        assert needle in rule, needle
    contract = _read(REFERENCES["skf-create-stack-skill"] / "invocation-contract.md")
    result = contract.split("## Result Contract (Headless)", 1)[1]
    assert "`[activation/warn] customization_resolver_unavailable: <reason>`" in result


# --------------------------------------------------------------------------
# #596: a `!` entry drops the bundled project-context.md default
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skill", FACTS_CLAUSE_SKILLS)
def test_activation_honours_a_drop_entry(skill):
    assert FACTS_CLAUSE in _flat(_activation(skill)), skill


@pytest.mark.parametrize("skill", CUSTOMIZE_CHANGED)
def test_customize_toml_shows_how_to_drop_the_default(skill):
    text = _read(SRC / skill / "customize.toml")
    assert tomllib.loads(text)["workflow"]["persistent_facts"] == [DEFAULT_FACT]
    comment = text[:text.index("\npersistent_facts = [")].rsplit("\n\n", 1)[-1]
    assert f'#   persistent_facts = ["!{DEFAULT_FACT}"]' in comment
    assert f"{{project-root}}/_bmad/custom/{skill}.toml" in comment
    assert "an entry prefixed with `!`, which loads nothing and drops each earlier" in comment
    for stale in ("cannot remove it", "add a literal fact", "Each entry is either", "kickoff_template_path"):
        assert stale not in comment, (skill, stale)


@pytest.mark.parametrize("skill", CUSTOMIZE_CHANGED)
def test_customize_toml_names_the_override_files_from_the_project_root(skill):
    text = _read(SRC / skill / "customize.toml")
    assert f"# Team overrides:     {{project-root}}/_bmad/custom/{skill}.toml\n" in text
    assert f"# Personal overrides: {{project-root}}/_bmad/custom/{skill}.user.toml\n" in text
    assert ".toml (under {project-root})" not in text and ".toml under {project-root}" not in text


def test_the_refine_architecture_header_says_when_overrides_apply():
    header = _read(SRC / "skf-refine-architecture" / "customize.toml").split("[workflow]", 1)[0]
    assert "apply only when BMad core's customization resolver runs" in _flat(header.replace("# ", ""))
    assert "`customization_resolver_unavailable`" in header


# --------------------------------------------------------------------------
# #601: Conventions say how module-level and sibling-skill paths resolve
# --------------------------------------------------------------------------


def _conventions(skill: str) -> str:
    return _section(_skill_md(skill), "## Conventions", "\n## ")


def _sibling_paths(skill: str) -> set[str]:
    found = set()
    for path in (SRC / skill).rglob("*.md"):
        found |= {name for name in SIBLING_PATH.findall(_read(path)) if name != skill}
    return found


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_conventions_state_the_module_level_exception(skill):
    conventions = _conventions(skill)
    assert conventions.count(MODULE_RULE) == 1, skill
    assert "\u2014" not in next(line for line in conventions.splitlines() if line.startswith(MODULE_RULE))


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_conventions_state_the_sibling_rule_where_a_sibling_path_appears(skill):
    """The rule is there exactly when the skill's files name another skill's folder."""
    assert (SIBLING_RULE in _conventions(skill)) == bool(_sibling_paths(skill)), (skill, _sibling_paths(skill))


def test_create_skill_declares_its_sub_step_folder():
    conventions = _conventions("skf-create-skill")
    assert "`references/sub/` the conditional sub-steps" in conventions
    assert ("a `nextStepFile` is relative to its own stage file (so a sub-step that returns to a main stage "
            "names it in the parent folder)") in conventions


# --------------------------------------------------------------------------
# #603: headless_mode comes from the sidecar's preferences.yaml
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skill", WORKFLOWS)
def test_headless_mode_reads_the_sidecar_preferences(skill):
    activation = _activation(skill)
    assert "`{sidecar_path}/preferences.yaml`" in activation, skill
    assert "in preferences.yaml." not in activation, skill
