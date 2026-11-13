#!/usr/bin/env python3
"""The customization resolver block, the same in all sixteen activations
(#595, #601; stage 6c of the v3.0.0 plan).

Every activation runs BMad core's resolver once, through SKF's
skf-resolve-customization.py (#770): the fifteen workflow SKILL.md files
with `--key workflow`, and Ferris (skf-forger) with `--key agent`, since his
customize.toml holds only an [agent] table, each with `--facts` (#1106), so
the helper applies the `!` drop and expands each glob of persistent_facts.
Four parts are word for word the same in all sixteen, compared from the one
copy test-skf-activation-customization.py keeps (COMMAND, WARNING, FALLBACK,
FACTS_POINTER):

- the `uv run {resolveCustomizationHelper} ... --project-root
  {project-root} ... --facts` command, alone in its fence, after the line
  that binds the helper (BINDING); Setup's alone adds a stderr redirect
  after `--facts` (STDERR_FILES), which the tests that run the fence cut off;
- the merge sentence that names the override layers from the project root,
  the one-line `[activation/warn] customization_resolver_unavailable:
  <reason>` warning and how the reason is worded;
- the fallback to the bundled defaults;
- the pointer that says what the resolved persistent_facts list holds.

Where the warning goes next is each activation's own sentence and is not
compared; ROUTE_EXCEPTIONS names the routes that differ most from a plain
record, so a rewording that drops one shows up here. With a stub `python3`
that reports 3.10 first on PATH, the bare form fails and the documented
`uv run` form still returns a team override, from a core that takes
`--project-root` and from one before 6.11.0 that does not: the stub does not
answer uv's interpreter query, so uv skips it and picks an interpreter that
meets the helper's `requires-python`, which the helper runs core under. No
step runs core's resolver directly, and the helper runs at all twenty-three
call sites. A report step that runs an `on_complete` hook binds a lost
`{onCompleteCommand}` from the helper right before the hook (#1116), and
that call returns a team's hook. Ferris states the module-level and
sibling-skill path rules the workflows state, and pipeline-mode.md says how
its paths resolve. An override copied from a customize.toml comment (#1108),
`#` markers dropped, changes what the step's own command resolves: the
`!` example drops the project-context default, Rename Skill's two-line
force setting reaches `workflow`, and an empty path override wins over its
bundled default, which SKILL.md then falls back to.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The ten workflows' steps and the strings they share, from their own test.
AC = _load("skf_activation_customization", REPO / "test" / "test-skf-activation-customization.py")
# The helper's own test keeps the stand-ins for BMAD core before and from 6.11.0.
RC = _load("skf_resolve_customization_test", REPO / "test" / "test-skf-resolve-customization.py")
HELPER = SRC / "shared" / "scripts" / AC.HELPER

# Each activation's customization step heading and the heading of the step after it.
STEPS = {
    **AC.STEPS,
    "skf-audit-skill": ("3. **Resolve workflow customization.**", "4. **Pre-flight"),
    "skf-update-skill": ("4. **Resolve workflow customization.**", "5. Load"),
    "skf-setup": ("6. **Resolve workflow customization.**", "7. Execute"),
    "skf-export-skill": ("3. **Resolve workflow customization.**", "4. **Resolve the helpers"),
    "skf-drop-skill": ("3. **Resolve workflow customization.**", "4. **Pre-flight"),
    "skf-forger": ("3. **Resolve agent customization.**", "4. **Resolve `{headless_mode}`**"),
}
ACTIVATIONS = sorted(STEPS)
KEY = {skill: "agent" if skill == "skf-forger" else "workflow" for skill in ACTIVATIONS}

# #965: the helper's own `not found` means BMAD core's resolver is missing (SKF alone), so a missing helper names
# itself with no path: a bare `_bmad/` path fails the path-standards scan, and `{project-root}` would expand to a
# home path in a published envelope.
MISSING_HELPER = "SKF helper skf-resolve-customization.py not found"
REASON = (f"(`<reason>`: its first stderr line, `{MISSING_HELPER}` when the script is missing, `no JSON` when "
          "it printed none).")
# Setup and Quick Skill halt at activation when the script is missing (#1117), so they name no reason for it.
HELPERS_REASON = "(`<reason>`: its first stderr line, `no JSON` when it printed none)."
# Routes that keep the reason for a later stage, or print it under a condition, instead of recording it at once.
# test, refine-architecture and create-stack take their phrase from the ROUTES table their own test keeps.
ROUTE_EXCEPTIONS = {
    **{skill: AC.ROUTES[skill][:1] for skill in ("skf-test-skill", "skf-refine-architecture",
                                                  "skf-create-stack-skill")},
    "skf-audit-skill": ("keep the reason as `{customization_resolver_unavailable}`",),
    "skf-setup": ("Bind `{customization_resolver_unavailable}` ← that reason (null when the resolver ran)",
                  "print the warning only when `{quiet_mode}` is false"),
    "skf-forger": ("Ferris keeps no run log of his own, so that line opens the greeting",),
}
# The activations that bind the helper from skf-preflight.py --helpers instead of probing for it.
ITEM_4_BINDS = {"skf-setup": "With `{resolveCustomizationHelper}` bound in item 4, run:",
                "skf-quick-skill": AC.HELPERS_BINDINGS["skf-quick-skill"] + ", and run:"}
# The activations that save the resolver's stderr for the emitter to read the reason from (#1119).
STDERR_FILES = {"skf-setup": ' 2> "{run_dir}/resolver.err"'}
CREATE_STACK_INIT = SRC / "skf-create-stack-skill" / "references" / "init.md"
PIPELINE_MODE = SRC / "skf-forger" / "references" / "pipeline-mode.md"

POSIX_UV = os.name != "nt" and shutil.which("uv") is not None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_md(skill: str) -> str:
    return _read(SRC / skill / "SKILL.md")


def _step(skill: str) -> str:
    start, end = STEPS[skill]
    text = _skill_md(skill)
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def _fence(skill: str) -> str:
    """The step's resolver command as argv text: the shell redirect STDERR_FILES names (#1119) cut off."""
    [command] = re.findall(r"^\s*(uv run \{resolveCustomizationHelper\} .+)$", _step(skill), re.M)
    return command.removesuffix(STDERR_FILES.get(skill, ""))


# The command up to its key, which the two stage calls share; they take no --facts.
RESOLVE_KEY = AC.COMMAND.removesuffix("workflow --facts")


def _command(skill: str) -> str:
    assert AC.COMMAND.endswith(" --key workflow --facts")
    return f"{RESOLVE_KEY}{KEY[skill]} --facts" + STDERR_FILES.get(skill, "")


def _shared(skill: str) -> str:
    """The merge, warning and fallback sentences every activation writes word for word."""
    opener, reason = (AC.HELPERS_WARNING_OPENER, HELPERS_REASON) if skill in ITEM_4_BINDS else (AC.WARNING_OPENER,
                                                                                                REASON)
    return (f"It merges the bundled `{{skill-root}}/customize.toml` with `{{project-root}}/_bmad/custom/{skill}.toml` "
            f"(team overrides, committed) and `.user.toml` (personal overrides, gitignored). {opener}{AC.WARNING} "
            f"{reason} {AC.FALLBACK}")


def test_every_activation_is_compared():
    """The fifteen workflows and Ferris: every skill folder under src/."""
    assert ACTIVATIONS == sorted(p.name for p in SRC.glob("skf-*") if (p / "SKILL.md").is_file())
    assert len(ACTIVATIONS) == 16


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_the_resolver_runs_through_uv_with_the_project_root(skill):
    step = _step(skill)
    fences = re.findall(r"```bash\n(.*?)```", step, re.S)
    assert [line.strip() for fence in fences for line in fence.splitlines() if line.strip()] == [_command(skill)]
    # #770: the installed-else-src binding, on one line, before the fence. Setup binds the
    # helper with the rest of its helpers from item 4's one preflight call (#1117).
    if skill in ITEM_4_BINDS:
        assert AC.BINDING not in step, skill
        binding = ITEM_4_BINDS[skill]
        assert step.index(binding) < step.index("```bash"), skill
        if skill == "skf-setup":
            ok = next(line for line in _skill_md(skill).splitlines() if "`status` `ok`" in line)
            assert "`{resolveCustomizationHelper}` from `helpers.<stem>`" in ok
    else:
        [binding] = [line for line in step.splitlines() if AC.BINDING in line]
        assert step.index(binding) < step.index("```bash"), skill
    assert AC.CORE_RESOLVER not in _skill_md(skill)


# The seven calls outside an activation: the on_complete hooks of the report steps of Create, Drop, Update, Audit,
# Test and Rename Skill (#1116), and Campaign's kickoff pipe, each with the key it reads and a probe list for the
# helper, since a compaction may have lost the activation's binding.
STAGE_CALLS = {
    "src/skf-create-skill/references/report.md": "workflow.on_complete",
    "src/skf-drop-skill/references/report.md": "workflow.on_complete",
    "src/skf-update-skill/references/report.md": "workflow.on_complete",
    "src/skf-audit-skill/references/report.md": "workflow.on_complete",
    "src/skf-test-skill/references/report.md": "workflow.on_complete",
    "src/skf-rename-skill/references/report.md": "workflow.on_complete",
    "src/skf-campaign/references/step-05-skill-loop.md": "workflow.persistent_facts",
}
PROBE_ORDER = [f"{{project-root}}/_bmad/skf/shared/scripts/{AC.HELPER}",
               f"{{project-root}}/src/shared/scripts/{AC.HELPER}"]


@pytest.mark.parametrize("rel", sorted(STAGE_CALLS))
def test_the_stage_calls_run_the_helper_with_their_key(rel):
    text = _read(REPO / rel)
    assert yaml.safe_load(text.split("---", 2)[1])["resolveCustomizationProbeOrder"] == PROBE_ORDER
    [rule] = [line for line in text.splitlines() if "`{resolveCustomizationProbeOrder}` when it is not bound" in line]
    assert "`{resolveCustomizationHelper}`" in rule
    assert text.count(RESOLVE_KEY + STAGE_CALLS[rel]) == 1
    assert f"{RESOLVE_KEY}{STAGE_CALLS[rel]} --facts" not in text, rel


# #1116: the sentence each report step binds a lost `{onCompleteCommand}` with, create-skill's word for word, and
# the line that skips an empty one, the bundled default (the steps not listed share the first wording).
HOOK_BINDING = ("When `{onCompleteCommand}` is not bound, bind it to the `workflow.on_complete` value this prints, "
                "or to the one in `{skill-root}/customize.toml` when the resolver cannot run")
EMPTY_HOOK = {
    "src/skf-update-skill/references/report.md": "Empty `{onCompleteCommand}` = no-op, no log entry.",
    "src/skf-test-skill/references/report.md": "If `{onCompleteCommand}` is empty, this hook is a no-op",
}
HOOK_STEPS = sorted(rel for rel, key in STAGE_CALLS.items() if key == "workflow.on_complete")


@pytest.mark.parametrize("rel", HOOK_STEPS)
def test_a_report_step_binds_a_lost_on_complete_before_its_hook(rel):
    """#1116: a compaction that dropped `{onCompleteCommand}` never skips a team's hook as if it were the empty
    default. The step binds an unbound one with activation's call narrowed to the hook's key, alone in a fence
    right after the sentence and before the hook runs; a bound value, an empty one included, calls nothing, and
    an empty one still skips the hook. No pointer to the activation's binding is left."""
    text = _read(REPO / rel)
    call = f"\n```bash\n{RESOLVE_KEY}workflow.on_complete\n```\n"
    assert text.count(HOOK_BINDING) == 1 and text.count(call) == 1, rel
    sentence, fence, hook = text.index(HOOK_BINDING), text.index(call), text.index("{onCompleteCommand} --result-path")
    assert sentence < fence < hook, rel
    tail = text[sentence + len(HOOK_BINDING):fence]
    assert tail.endswith(":\n") and "\n" not in tail[:-1], f"{rel}: the call follows the sentence: {tail!r}"
    assert "from `workflow.on_complete`" not in text, rel
    empty = EMPTY_HOOK.get(rel, "When `{onCompleteCommand}` is empty (bundled default), skip the invocation entirely")
    assert text.count(empty) == 1 and text.index(empty) > hook, rel


@pytest.mark.parametrize("rel", HOOK_STEPS)
def test_the_hook_call_returns_a_team_on_complete(tmp_path, rel):
    """#1116: run as written, the step's call returns the `on_complete` a team override sets, the hook a run that
    lost the binding then fires; with no override it returns the bundled default, the empty string a run whose
    resolver cannot run reads from customize.toml, so no hook runs."""
    skill = rel.split("/")[1]
    [line] = re.findall(r"```bash\n(uv run \{resolveCustomizationHelper\} [^\n]*)\n```", _read(REPO / rel))
    root = tmp_path / "project"
    (root / "_bmad" / "scripts").mkdir(parents=True)
    (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(RC.CORE_6_12.encode("utf-8"))
    words = [w.replace("{resolveCustomizationHelper}", HELPER.as_posix()).replace("{project-root}", root.as_posix())
             .replace("{skill-root}", (SRC / skill).as_posix()) for w in shlex.split(line)]
    assert words[:3] == ["uv", "run", HELPER.as_posix()] and words[-2:] == ["--key", "workflow.on_complete"]

    def resolve() -> dict:
        proc = subprocess.run([sys.executable, *words[2:]], capture_output=True, encoding="utf-8", cwd=root,
                              timeout=120)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    assert tomllib.loads(_read(SRC / skill / "customize.toml"))["workflow"]["on_complete"] == ""
    assert resolve() == {"workflow.on_complete": ""}
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad" / "custom" / f"{skill}.toml").write_bytes(b'[workflow]\non_complete = "scripts/notify-ci.sh"\n')
    assert resolve() == {"workflow.on_complete": "scripts/notify-ci.sh"}


def test_no_step_runs_core_s_resolver_directly():
    """Every customization call goes through the helper, which serves a core before 6.11.0 too: core's
    resolver is named in no src/ Markdown file, and the helper runs at the sixteen activations and the
    seven stage calls."""
    direct, calls = [], 0
    for md in sorted(SRC.rglob("*.md")):
        text = _read(md)
        rel = md.relative_to(REPO).as_posix()
        if "resolve_customization.py" in text:
            direct.append(rel)
        calls += len(re.findall(r"uv run \{resolveCustomizationHelper\} --skill \{skill-root\} "
                                r"--project-root \{project-root\} --key [\w.]+", text))
    assert not direct, f"run core's resolver through {AC.HELPER}: {direct}"
    assert calls == len(ACTIVATIONS) + len(STAGE_CALLS) == 23


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_the_warning_and_the_fallback_are_the_same_everywhere(skill):
    step = AC._flat(_step(skill))
    assert step.count(_shared(skill)) == 1, skill
    # Only the prefixed override folder: the bare form is gone from every activation.
    assert "the `_bmad/custom/` overrides" not in step
    assert "`not found` when the script is missing" not in AC._flat(_skill_md(skill)), skill


def test_a_missing_helper_and_a_missing_core_give_different_reasons():
    """#965: the helper prints `not found` when BMAD core's resolver is missing, the documented SKF-alone warning,
    so the reason an activation gives when the helper itself is missing names the helper by its file name, the
    one the stage calls probe for, with no path and never core's resolver."""
    assert _load("skf_resolve_customization_helper", HELPER).MISSING == "not found"
    assert all(probe.endswith("/" + AC.HELPER) for probe in PROBE_ORDER)
    expected = f"SKF helper {AC.HELPER} not found"
    assert expected == MISSING_HELPER
    assert f"`{expected}` when the script is missing" in REASON
    for gone in ("`not found`", "_bmad/", "{project-root}", "resolve_customization.py"):
        assert gone not in REASON, gone


# What the old prose asked the model to do by hand, before the helper resolved the list (#1106).
HAND_RESOLVED = ("loads nothing itself", "file/glob contents", "globs expanded", "paths or globs whose contents",
                 "file or glob contents")


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_each_activation_reads_the_list_the_helper_resolved(skill):
    """#1106: the step points at what `--facts` did, once, and no longer tells the model to drop or expand."""
    step = AC._flat(_step(skill))
    assert step.count(AC.FACTS_POINTER) == 1, skill
    assert f"`{KEY[skill]}.persistent_facts`" in step, skill
    for gone in HAND_RESOLVED:
        assert gone not in step, (skill, gone)
    # A skill whose bundled list is empty (Setup, Drop Skill, Campaign and Ferris since #1107) carries the pointer
    # alone; every other step names the default its customize.toml ships.
    if not tomllib.loads(_read(SRC / skill / "customize.toml"))[KEY[skill]]["persistent_facts"]:
        assert f"({AC.FACTS_POINTER})" in step and "the bundled default loads" not in step, skill
    else:
        assert step.count(AC.FACTS_NOTE) == 1, skill


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_the_fence_hands_the_activation_one_file_per_project_context(tmp_path, skill):
    """#1106: the step's own command, the bundled customize.toml and no override: the list names each
    project-context.md once, as a file, and none of the clones a halted run keeps under _bmad-output/.skf-run/."""
    root = tmp_path / "project"
    (root / "_bmad" / "scripts").mkdir(parents=True)
    (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(RC.CORE_6_12.encode("utf-8"))
    for folder in ("docs", "_bmad-output/.skf-run/x/source-1"):
        (root / folder).mkdir(parents=True)
        (root / folder / "project-context.md").write_bytes(b"rule\n")
    command = _fence(skill)
    words = [w.replace("{resolveCustomizationHelper}", str(HELPER)).replace("{project-root}", str(root))
             .replace("{skill-root}", str(SRC / skill)) for w in shlex.split(command)]
    assert words[:2] == ["uv", "run"]
    done = subprocess.run([sys.executable, *words[2:]], capture_output=True, cwd=root, timeout=120,
                          env={k: v for k, v in os.environ.items() if not k.startswith("SKF_TEST_")})
    assert done.returncode == 0 and done.stderr == b"", done.stderr
    bundled = tomllib.loads(_read(SRC / skill / "customize.toml"))[KEY[skill]]["persistent_facts"]
    assert bundled in ([], [AC.DEFAULT_FACT]), (skill, bundled)
    docs = "file:" + (root / "docs" / "project-context.md").as_posix()
    assert json.loads(done.stdout)[KEY[skill]]["persistent_facts"] == ([docs] if bundled else []), skill


@pytest.mark.parametrize("skill", ("skf-campaign", "skf-drop-skill"))
def test_the_opt_in_the_comment_shows_loads_each_project_context(tmp_path, skill):
    """#1107: Drop Skill and Campaign ship no default. The team override their persistent_facts comment shows,
    `#` markers dropped, makes the step's own command load each project-context.md once, and a personal
    override's `!` entry drops it again."""
    text = _read(SRC / skill / "customize.toml")
    comment = text[:text.index("\npersistent_facts = []\n")].rsplit("\n\n", 1)[-1]
    example = comment.split(f"{{project-root}}/_bmad/custom/{skill}.toml:\n", 1)[1]
    team = "\n".join(line.removeprefix("#").strip() for line in example.splitlines()) + "\n"
    assert tomllib.loads(team) == {"workflow": {"persistent_facts": [AC.DEFAULT_FACT]}}
    root = tmp_path / "project"
    (root / "_bmad" / "scripts").mkdir(parents=True)
    (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(RC.CORE_6_12.encode("utf-8"))
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad" / "custom" / f"{skill}.toml").write_bytes(team.encode("utf-8"))
    (root / "docs").mkdir()
    (root / "docs" / "project-context.md").write_bytes(b"rule\n")
    command = _fence(skill)
    words = [w.replace("{resolveCustomizationHelper}", str(HELPER)).replace("{project-root}", str(root))
             .replace("{skill-root}", str(SRC / skill)) for w in shlex.split(command)]
    env = {k: v for k, v in os.environ.items() if not k.startswith("SKF_TEST_")}

    def facts() -> list:
        done = subprocess.run([sys.executable, *words[2:]], capture_output=True, cwd=root, timeout=120, env=env)
        assert done.returncode == 0 and done.stderr == b"", done.stderr
        return json.loads(done.stdout)["workflow"]["persistent_facts"]

    assert facts() == ["file:" + (root / "docs" / "project-context.md").as_posix()], skill
    (root / "_bmad" / "custom" / f"{skill}.user.toml").write_bytes(
        f'[workflow]\npersistent_facts = ["!{AC.DEFAULT_FACT}"]\n'.encode("utf-8"))
    assert facts() == [], skill


def _resolve(root: Path, skill: str, team: str | None = None) -> dict:
    """The `workflow` table the step's own command resolves under `root`, with `team` as the team override."""
    (root / "_bmad" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(RC.CORE_6_12.encode("utf-8"))
    override = root / "_bmad" / "custom" / f"{skill}.toml"
    override.unlink(missing_ok=True)
    if team is not None:
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_bytes(team.encode("utf-8"))
    command = _fence(skill)
    words = [w.replace("{resolveCustomizationHelper}", str(HELPER)).replace("{project-root}", str(root))
             .replace("{skill-root}", str(SRC / skill)) for w in shlex.split(command)]
    done = subprocess.run([sys.executable, *words[2:]], capture_output=True, cwd=root, timeout=120,
                          env={k: v for k, v in os.environ.items() if not k.startswith("SKF_TEST_")})
    assert done.returncode == 0 and done.stderr == b"", (skill, done.stderr)
    return json.loads(done.stdout)["workflow"]


def _copied(comment: str) -> str:
    """A comment's lines with their `#` markers dropped: what a team pastes into its override file."""
    return "\n".join(line.removeprefix("#").strip() for line in comment.splitlines()) + "\n"


DEFAULT_SKILLS = [skill for skill in ACTIVATIONS if KEY[skill] == "workflow"
                  and tomllib.loads(_read(SRC / skill / "customize.toml"))["workflow"]["persistent_facts"]]


def test_twelve_workflows_ship_the_project_context_default():
    assert len(DEFAULT_SKILLS) == 12, DEFAULT_SKILLS


@pytest.mark.parametrize("skill", DEFAULT_SKILLS)
def test_the_copied_drop_example_stops_loading_the_project_context(tmp_path, skill):
    """#1108: the `!` override the persistent_facts comment shows, `#` markers dropped and written as the team
    override file the comment names, drops the bundled default from the list the step's own command resolves.
    Written without its `[workflow]` line, the key lands at the file's root and the default stays loaded."""
    text = _read(SRC / skill / "customize.toml")
    comment = text[:text.index("\npersistent_facts = [")].rsplit("\n\n", 1)[-1]
    team = _copied(comment.split(f"{{project-root}}/_bmad/custom/{skill}.toml:\n", 1)[1])
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "project-context.md").write_bytes(b"rule\n")
    docs = "file:" + (root / "docs" / "project-context.md").as_posix()
    assert _resolve(root, skill)["persistent_facts"] == [docs], skill
    assert _resolve(root, skill, team)["persistent_facts"] == [], (
        f"{skill}: the copied example leaves the project-context default loaded")
    assert team.startswith("[workflow]\n"), skill
    assert _resolve(root, skill, team.split("\n", 1)[1])["persistent_facts"] == [docs], (
        f"{skill}: the example without its `[workflow]` line still reached the workflow table")


def test_the_copied_hook_example_sets_on_complete(tmp_path):
    """#1108: Export Skill's on_complete example, `#` markers dropped and written as the team override file it
    names, sets the hook; the key line alone lands at the file's root and leaves the hook off."""
    skill = "skf-export-skill"
    text = _read(SRC / skill / "customize.toml")
    comment = text[:text.index('\non_complete = ""')].rsplit("\n\n", 1)[-1]
    example = comment.split(f"Example, in {{project-root}}/_bmad/custom/{skill}.toml:\n", 1)[1]
    team = _copied("\n".join(line for line in example.splitlines() if line.startswith("#   ")))
    root = tmp_path / "project"
    assert _resolve(root, skill, team)["on_complete"] == "{project-root}/scripts/publish-skill.sh"
    assert _resolve(root, skill, team.split("\n", 1)[1])["on_complete"] == ""


def test_the_copied_force_setting_reaches_the_gate(tmp_path):
    """#1108: Rename Skill's comment gives its standing approval as two lines; written as the team override, the
    step's own command resolves `"true"`, which SKILL.md binds to a true `{forceSourceAuthorityInHeadless}`.
    The same key without the `[workflow]` line resolves the bundled empty value."""
    skill = "skf-rename-skill"
    text = _read(SRC / skill / "customize.toml")
    comment = " ".join(line.lstrip("#").strip() for line in
                       text[:text.index('\nforce_source_authority_in_headless = ""')].rsplit("\n\n", 1)[-1]
                       .splitlines())
    lines = re.search(r"as two lines: `(\[workflow\])` then `([^`]+)`", comment).groups()
    root = tmp_path / "project"
    assert _resolve(root, skill, "\n".join(lines) + "\n")["force_source_authority_in_headless"] == "true"
    assert _resolve(root, skill, lines[1] + "\n")["force_source_authority_in_headless"] == ""
    binding = next(line for line in _skill_md(skill).splitlines() if "`{forceSourceAuthorityInHeadless}` ←" in line)
    assert 'true when `workflow.force_source_authority_in_headless` is `"true"`' in binding


FILLED_DEFAULTS = (
    ("skf-test-skill", "test_report_template_path", "testReportTemplatePath"),
    # #1110: Campaign's three template scalars ship their bundled files too.
    ("skf-campaign", "report_template_path", "reportTemplatePath"),
    ("skf-campaign", "kickoff_template_path", "kickoffTemplatePath"),
    ("skf-campaign", "brief_template_path", "briefTemplatePath"),
    ("skf-create-stack-skill", "stack_skill_template_path", "stackSkillTemplatePath"),
    ("skf-create-stack-skill", "integration_patterns_path", "integrationPatternsPath"),
)


@pytest.mark.parametrize("skill,key,variable", FILLED_DEFAULTS, ids=[f"{s}:{k}" for s, k, _ in FILLED_DEFAULTS])
def test_an_empty_path_override_falls_back_to_the_bundled_file(tmp_path, skill, key, variable):
    """#1108: these scalars now ship their bundled default. A team override of `""` still wins in the merge, and
    the SKILL.md binding then falls back to that same bundled file, so the empty string keeps its meaning."""
    default = tomllib.loads(_read(SRC / skill / "customize.toml"))["workflow"][key]
    assert default and (SRC / skill / default).is_file(), (skill, key, default)
    root = tmp_path / "project"
    assert _resolve(root, skill)[key] == default
    assert _resolve(root, skill, f'[workflow]\n{key} = ""\n')[key] == ""
    binding = next(line for line in _skill_md(skill).splitlines() if f"`{{{variable}}}` ←" in line)
    assert f"`workflow.{key}` if non-empty, else `{default}`" in binding, (skill, binding)


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_each_activation_says_where_the_reason_goes(skill):
    """The sentence after the fallback differs per skill; the exceptions keep the words they route with."""
    after = AC._flat(_step(skill)).split(AC.FALLBACK, 1)[1].strip()
    assert after, skill
    for phrase in ROUTE_EXCEPTIONS.get(skill, ()):
        assert phrase in after, (skill, phrase)


def test_create_stack_writes_the_reason_to_its_warning_file():
    assert "`[activation/warn] customization_resolver_unavailable: {customization_resolver_unavailable}` to " \
           "`{run_dir}/warning.txt` with a file write" in _read(CREATE_STACK_INIT)


def test_ferris_resolves_the_agent_table_his_customize_toml_holds():
    assert list(tomllib.loads(_read(SRC / "skf-forger" / "customize.toml"))) == ["agent"]
    for skill in ACTIVATIONS:
        if skill != "skf-forger":
            assert "[workflow]" in _read(SRC / skill / "customize.toml"), skill


def test_ferris_applies_the_array_surfaces_an_override_adds():
    step = AC._flat(_step("skf-forger"))
    for token in ("run `agent.activation_steps_prepend` in order now", "`agent.persistent_facts`",
                  AC.FACTS_POINTER,
                  "run `agent.activation_steps_append` once step 6 has greeted, before it dispatches a pick"):
        assert token in step, token
    assert "`workflow." not in step


# --------------------------------------------------------------------------
# The documented command still reads a team override when python3 is 3.10
# --------------------------------------------------------------------------

# A stand-in for BMad core's resolver from 6.11.0 (which the BMAD Method installer ships, not this repository):
# the same PEP 723 header, the same flags and the same three-layer merge, enough to show what `uv run` changes.
# The core before 6.11.0, which knows no --project-root and declares no requires-python, is the helper test's.
RESOLVER = '''#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
import argparse
import json
import tomllib
from pathlib import Path


def merge(base, over):
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            base[key] = base[key] + value
        else:
            base[key] = value
    return base


parser = argparse.ArgumentParser()
parser.add_argument("--skill", required=True)
parser.add_argument("--project-root", required=True)
parser.add_argument("--key", action="append", default=[])
args = parser.parse_args()
skill = Path(args.skill)
custom = Path(args.project_root) / "_bmad" / "custom"
merged = {}
for layer in (skill / "customize.toml", custom / f"{skill.name}.toml", custom / f"{skill.name}.user.toml"):
    if layer.is_file():
        merge(merged, tomllib.loads(layer.read_text(encoding="utf-8")))
print(json.dumps({key: merged[key] for key in args.key if key in merged}))
'''
# A python3 that reports 3.10 and has no tomllib, as the resolver's own check reports. It answers nothing but
# `--version`, so uv's interpreter query fails on it and uv skips it for one that meets `requires-python`.
STUB_PYTHON = '''#!/bin/sh
if [ "$1" = "--version" ]; then echo "Python 3.10.12"; exit 0; fi
echo "error: Python 3.11+ is required (stdlib \\`tomllib\\` not found)." >&2
exit 3
'''
OVERRIDES = {
    "skf-forger": ("agent", '[agent]\npersistent_facts = ["Our services deploy to AWS only."]\n',
                   ("persistent_facts", ["Our services deploy to AWS only."])),
    "skf-drop-skill": ("workflow", '[workflow]\nforbid_purge_in_headless = "true"\n',
                       ("forbid_purge_in_headless", "true")),
}


CORES = {"6.11+": RESOLVER, "6.10": RC.CORE_6_10}


def _project(tmp_path: Path, skill: str, core: str) -> tuple[Path, dict]:
    root = tmp_path / "project"
    (root / "_bmad" / "scripts").mkdir(parents=True)
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(CORES[core].encode("utf-8"))
    (root / "_bmad" / "custom" / f"{skill}.toml").write_bytes(OVERRIDES[skill][1].encode("utf-8"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python3", "python"):
        stub = bin_dir / name
        stub.write_bytes(STUB_PYTHON.encode("utf-8"))
        stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    return root, env


@pytest.mark.skipif(not POSIX_UV, reason="needs a POSIX shell for the python3 stub, and uv")
@pytest.mark.parametrize("core", sorted(CORES))
@pytest.mark.parametrize("skill", sorted(OVERRIDES))
def test_the_command_reads_a_team_override_under_a_python3_without_tomllib(tmp_path, skill, core):
    key, _, (field, value) = OVERRIDES[skill]
    root, env = _project(tmp_path, skill, core)
    skill_root = SRC / skill
    if core == "6.10":
        # A core before 6.11.0 reads the overrides of the nearest folder above the skill holding `_bmad` or `.git`:
        # the project only for a skill installed inside it, never for this checkout's src/.
        skill_root = root / "_bmad" / "skf" / skill
        skill_root.mkdir(parents=True)
        shutil.copyfile(SRC / skill / "customize.toml", skill_root / "customize.toml")
    command = _fence(skill)
    words = [w.replace("{resolveCustomizationHelper}", HELPER.as_posix()).replace("{project-root}", root.as_posix())
             .replace("{skill-root}", skill_root.as_posix()) for w in shlex.split(command)]
    assert words[:3] == ["uv", "run", HELPER.as_posix()] and words[-3:] == ["--key", key, "--facts"]
    bare = subprocess.run(["python3", *words[2:]], capture_output=True, text=True, encoding="utf-8", env=env,
                          cwd=root, timeout=60)
    assert bare.returncode == 3 and "tomllib" in bare.stderr
    done = subprocess.run(words, capture_output=True, text=True, encoding="utf-8", env=env, cwd=root, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    merged = json.loads(done.stdout)[key]
    assert merged[field] == value
    # The bundled defaults are still there under the override.
    bundled = tomllib.loads(_read(SRC / skill / "customize.toml"))[key]
    assert {k for k in bundled if k != field} <= set(merged)
    if core == "6.10":  # rejected with the flag, then run again without it
        calls = [json.loads(line) for line in _read(root / "_bmad" / "scripts" / "calls.jsonl").splitlines()]
        assert ["--project-root" in call["argv"] for call in calls] == [True, False]


# --------------------------------------------------------------------------
# #601: Ferris states the path rules the workflows state
# --------------------------------------------------------------------------


def test_ferris_conventions_state_the_module_level_and_sibling_rules():
    conventions = AC._section(_skill_md("skf-forger"), "## Conventions", "\n## ")
    assert conventions.count(AC.MODULE_RULE) == 1
    assert conventions.count(AC.SIBLING_RULE) == 1
    assert "`shared/references/pipeline-contracts.md`" in conventions
    assert "where every `uv run scripts/...` call runs" in conventions


def test_pipeline_mode_says_how_its_paths_resolve():
    note = _read(PIPELINE_MODE).split("## Activation", 1)[0]
    for token in ("SKILL.md **Conventions**", "each `uv run scripts/...` call runs from the skf-forger skill root",
                  "`shared/references/pipeline-contracts.md`", "`{project-root}/_bmad/skf/` installed, `src/` in dev"):
        assert token in note, token
