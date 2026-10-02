#!/usr/bin/env python3
"""The customization resolver block, the same in all sixteen activations
(#595, #601; stage 6c of the v3.0.0 plan).

Every activation runs BMad core's resolver once: the fifteen workflow
SKILL.md files with `--key workflow`, and Ferris (skf-forger) with
`--key agent`, since his customize.toml holds only an [agent] table. Three
parts are word for word the same in all sixteen, compared from the one copy
test-skf-activation-customization.py keeps (COMMAND, WARNING, FALLBACK):

- the `uv run ... --project-root {project-root}` command, alone in its fence;
- the merge sentence that names the override layers from the project root,
  the one-line `[activation/warn] customization_resolver_unavailable:
  <reason>` warning and how the reason is worded;
- the fallback to the bundled defaults.

Where the warning goes next is each activation's own sentence and is not
compared; ROUTE_EXCEPTIONS names the routes that differ most from a plain
record, so a rewording that drops one shows up here. With a stub `python3`
that reports 3.10 first on PATH, the bare form fails and the documented
`uv run` form still returns a team override: the stub does not answer uv's
interpreter query, so uv skips it and picks an interpreter that meets the
resolver's `requires-python`. Ferris states the module-level and
sibling-skill path rules the workflows state, and pipeline-mode.md says how
its paths resolve.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The ten workflows' steps and the strings they share, from their own test.
AC = _load("skf_activation_customization", REPO / "test" / "test-skf-activation-customization.py")

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

REASON = ("(`<reason>`: its first stderr line, `not found` when the script is missing, `no JSON` when it "
          "printed none).")
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


def _command(skill: str) -> str:
    assert AC.COMMAND.endswith(" --key workflow")
    return AC.COMMAND.removesuffix("workflow") + KEY[skill]


def _shared(skill: str) -> str:
    """The merge, warning and fallback sentences every activation writes word for word."""
    return (f"It merges the bundled `{{skill-root}}/customize.toml` with `{{project-root}}/_bmad/custom/{skill}.toml` "
            "(team overrides, committed) and `.user.toml` (personal overrides, gitignored). When it exits non-zero, "
            f"prints no JSON or is missing, print one line, {AC.WARNING} {REASON} {AC.FALLBACK}")


def test_every_activation_is_compared():
    """The fifteen workflows and Ferris: every skill folder under src/."""
    assert ACTIVATIONS == sorted(p.name for p in SRC.glob("skf-*") if (p / "SKILL.md").is_file())
    assert len(ACTIVATIONS) == 16


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_the_resolver_runs_through_uv_with_the_project_root(skill):
    fences = re.findall(r"```bash\n(.*?)```", _step(skill), re.S)
    assert [line.strip() for fence in fences for line in fence.splitlines() if line.strip()] == [_command(skill)]
    assert "python3 {project-root}/_bmad/scripts/resolve_customization.py" not in _skill_md(skill)


@pytest.mark.parametrize("skill", ACTIVATIONS)
def test_the_warning_and_the_fallback_are_the_same_everywhere(skill):
    step = AC._flat(_step(skill))
    assert step.count(_shared(skill)) == 1, skill
    # Only the prefixed override folder: the bare form is gone from every activation.
    assert "the `_bmad/custom/` overrides" not in step


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
                  "an entry prefixed `!` drops each earlier entry it names and loads nothing itself",
                  "run `agent.activation_steps_append` once step 6 has greeted, before it dispatches a pick"):
        assert token in step, token
    assert "`workflow." not in step


# --------------------------------------------------------------------------
# The documented command still reads a team override when python3 is 3.10
# --------------------------------------------------------------------------

# A stand-in for BMad core's resolver (which the BMAD Method installer ships, not this repository): the same
# PEP 723 header, the same flags and the same three-layer merge, enough to show what `uv run` changes.
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


def _project(tmp_path: Path, skill: str) -> tuple[Path, dict]:
    root = tmp_path / "project"
    (root / "_bmad" / "scripts").mkdir(parents=True)
    (root / "_bmad" / "custom").mkdir()
    (root / "_bmad" / "scripts" / "resolve_customization.py").write_bytes(RESOLVER.encode("utf-8"))
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
@pytest.mark.parametrize("skill", sorted(OVERRIDES))
def test_the_command_reads_a_team_override_under_a_python3_without_tomllib(tmp_path, skill):
    key, _, (field, value) = OVERRIDES[skill]
    root, env = _project(tmp_path, skill)
    [command] = re.findall(r"^\s*(uv run \{project-root\}/_bmad/scripts/resolve_customization\.py .+)$", _step(skill),
                           re.M)
    words = [w.replace("{project-root}", root.as_posix()).replace("{skill-root}", (SRC / skill).as_posix())
             for w in shlex.split(command)]
    assert words[:2] == ["uv", "run"] and words[-2:] == ["--key", key]
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
