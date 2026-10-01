#!/usr/bin/env python3
"""export-skill's inputs, helpers and headless contract (wave 5).

Step prose is not executed by any test, so these checks pin it and run the
commands it documents:

- #594: On Activation resolves every helper steps 1 to 5 cannot run without,
  the skill inventory included, before any prompt or write, and no step
  resolves one again (the test-report lookup is advisory and stays in step
  1); every flag the contract lists is parsed, `--context-file` included;
  the snippet-root probe takes only roots an earlier export chose as
  evidence, asks one layout question when there is none, and resolves a
  mismatch headless by the folder on disk that holds the skills; option (d)
  binds the root steps 3 and 4 read.
- #596: the `on_complete` and `snippet_format_path` comments say what runs and
  which snippet lines scripts parse, and the helpers agree with them.
- #599: no step keeps a by-hand fallback for a helper activation resolved.
- #600: the headless contract lives in references/invocation-contract.md
  behind a one-line pointer, package.md renders the export-gate verdict
  without restating it, and the description names its object.
- The export-gate halt names the Section 7b heading the gate matched.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
EXPORT = SRC / "skf-export-skill"
REBUILD_PY = SRC / "shared" / "scripts" / "skf-rebuild-managed-sections.py"

SKILL_MD = "SKILL.md"
CONTRACT = "references/invocation-contract.md"
LOAD = "references/load-skill.md"
PROBE = "references/preflight-snippet-root-probe.md"
PACKAGE = "references/package.md"
SNIPPET = "references/generate-snippet.md"
UPDATE = "references/update-context.md"
TOKENS = "references/token-report.md"
SNIPPET_FORMAT = "assets/snippet-format.md"

# The helpers On Activation resolves for every stage, by placeholder and file.
ACTIVATION_HELPERS = {
    "emitEnvelopeHelper": "skf-emit-result-envelope.py",
    "manifestOpsHelper": "skf-manifest-ops.py",
    "skillInventoryHelper": "skf-skill-inventory.py",
    "rebuildManagedSectionsHelper": "skf-rebuild-managed-sections.py",
    "validateOutputHelper": "skf-validate-output.py",
    "countTokensHelper": "skf-count-tokens.py",
}
FENCE_RE = re.compile(r"^\s*```")


def _read(rel: str) -> str:
    return (EXPORT / rel).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` up to marker `end` (or the end of the text)."""
    assert text.count(start) == 1, f"marker {start!r} must occur once"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _fenced_lines(text: str) -> list[str]:
    lines, fenced = [], False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            fenced = not fenced
        elif fenced:
            lines.append(line.strip())
    return lines


def _row(text: str, aspect: str) -> str:
    [row] = [line for line in text.splitlines() if line.startswith(f"| **{aspect}** |")]
    return row


def _frontmatter(text: str) -> str:
    return text.split("\n---\n", 1)[0]


# --------------------------------------------------------------------------
# #600: the description and the headless contract
# --------------------------------------------------------------------------


def test_the_description_says_what_it_exports_and_quotes_no_bare_verb():
    description = next(line for line in _read(SKILL_MD).splitlines() if line.startswith("description: "))
    assert description.startswith("description: Exports an SKF skill, ")
    triggers = re.findall(r'"([^"]+)"', description)
    assert "export a skill" in triggers
    for trigger in triggers:
        assert len(trigger.rstrip(".").split()) > 1, f"{trigger!r} is a bare verb: name its object"
    assert "Package for distribution" not in description, "no step builds a distribution package"


def test_the_headless_contract_lives_behind_a_one_line_pointer():
    skill = _read(SKILL_MD)
    pointer = _section(skill, "## Invocation Contract", "## On Activation")
    assert "`references/invocation-contract.md`" in pointer and "`references/result-envelope.md`" in pointer
    assert len([line for line in pointer.splitlines()[1:] if line.strip()]) == 1, "a one-line pointer"
    assert "| **" not in skill, "no contract row stays in the always-loaded SKILL.md"
    contract = _read(CONTRACT)
    for aspect in ("Inputs", "Flags", "Gates", "Outputs", "Multi-skill mode", "Headless", "Exit codes"):
        _row(contract, aspect)


def _contract_flags() -> set[str]:
    return set(re.findall(r"`(--[a-z][a-z-]*|-[A-Z])\b", _row(_read(CONTRACT), "Flags")))


def test_every_contract_flag_is_parsed_and_every_parsed_flag_is_listed():
    """#594: --context-file was parsed by step 1 but missing from the contract."""
    flags = _contract_flags()
    assert flags == {"--headless", "-H", "--all", "--context-file", "--dry-run"}
    parsing = _section(_read(LOAD), "**Flag Parsing:**", "**Context File Resolution:**")
    parsed = set(re.findall(r"^- `(--[a-z-]+)` flag", parsing, re.M))
    headless = _section(_read(SKILL_MD), "2. **Resolve `{headless_mode}`**", "3. **Resolve workflow customization.**")
    parsed |= set(re.findall(r"`(--[a-z-]+|-[A-Z])`", headless))
    assert parsed == flags
    context_file = _row(_read(CONTRACT), "Flags")
    for name in ("`CLAUDE.md`", "`AGENTS.md`", "`.cursorrules`", "exit code 3, `resolution-failure`"):
        assert name in context_file, name


def test_the_contract_gates_name_each_headless_default():
    gates = _row(_read(CONTRACT), "Gates")
    for gate in ("step 1 §1b", "the layout question", "(headless: [I]", "the mismatch gate", "checks the disk",
                 "step 1 §6", "step 4 §3b", "§4c.1", "step 4 §8"):
        assert gate in gates, gate


# --------------------------------------------------------------------------
# #594: every helper resolves at activation, before any prompt or write
# --------------------------------------------------------------------------


def test_activation_resolves_every_helper_the_steps_cannot_run_without():
    skill = _read(SKILL_MD)
    resolve = _section(skill, "4. **Resolve the helpers and create the run folder.**", "5. **Pre-flight write check.**")
    for name, script in ACTIVATION_HELPERS.items():
        [line] = [line for line in resolve.splitlines() if line.lstrip().startswith(f"- `{{{name}}}` ←")]
        assert f"`{{project-root}}/_bmad/skf/shared/scripts/{script}`" in line, name
        assert f"`{{project-root}}/src/shared/scripts/{script}`" in line, name
        assert (SRC / "shared" / "scripts" / script).is_file(), script
    assert "before any prompt or write" in resolve
    assert 'HALT (exit code 4, `halt_reason: "context-rebuild-failed"`)' in resolve
    # Activation hands over to step 1 only after it: the first prompt is in step 1.
    assert skill.index("4. **Resolve the helpers") < skill.index("Load, read the full file, and then execute "
                                                                 "`references/load-skill.md`")


def test_no_step_resolves_an_activation_helper_again():
    """One home: a probe order or a halt for a missing helper in a step file restates activation's."""
    stems = [name[:-len("Helper")] for name in ACTIVATION_HELPERS]
    for path in sorted((EXPORT / "references").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(EXPORT).as_posix()
        for stem in stems:
            assert f"{stem}ProbeOrder" not in text, f"{rel}: {stem}ProbeOrder"
        for name in ACTIVATION_HELPERS:
            assert not re.search(rf"[Rr]esolve `\{{{name}\}}`", text), f"{rel}: resolves {{{name}}} again"
    assert "**Resolve the helpers**" not in _read(LOAD)
    update = _read(UPDATE)
    assert "### 2. Stage Folder" in update and "### 2. Resolve the Helpers" not in update
    assert "manifest-write-failed\"`): \"`skf-manifest-ops.py` is missing" not in update
    assert "`{countTokensProbeOrder}` candidate" not in _read(SNIPPET)


def test_each_activation_helper_has_a_step_that_calls_it():
    calls = "\n".join(path.read_text(encoding="utf-8") for path in sorted((EXPORT / "references").glob("*.md")))
    for name in ACTIVATION_HELPERS:
        assert re.search(rf"(?:python3|uv run) \{{{name}\}} ", calls), name


# --------------------------------------------------------------------------
# #599: no by-hand fallback for a helper activation resolved
# --------------------------------------------------------------------------


def test_no_step_keeps_a_by_hand_fallback_for_a_resolved_helper():
    tokens = _read(TOKENS)
    assert "Graceful fallback" not in tokens and "in-prompt using the char-over-four convention" not in tokens
    load = _read(LOAD)
    assert "If the script cannot run" not in load and "perform the checks listed above by hand" not in load
    # Discovery and the version choice: no `active`-link scan and no exit-4 halt of their own.
    for stale in ("no helper candidate resolves, add only the groups", "`skf-skill-inventory.py` is missing",
                  "no helper candidate resolved"):
        assert stale not in load, stale
    assert "`{countTokensHelper}` against the resolved skill package" in tokens


# --------------------------------------------------------------------------
# #600 leanness: package.md renders the verdict and restates none of it
# --------------------------------------------------------------------------


def test_package_renders_the_export_gate_verdict_without_restating_it():
    package = _read(PACKAGE)
    assert "├──" not in package, "the layout tree drives no check"
    for restated in ("generation_date", "source_authority", "Enum membership", "NOT READY", "ProbeOrder"):
        assert restated not in package, restated
    assert "Step 1 §2 halts on `NOT_READY`" in package
    for field in ("`export_status`", "`validation.metadata.recommended_missing`", "`validation.crossref_7b.orphans`"):
        assert field in package, field
    assert "python3 {validateOutputHelper} {resolved_skill_package} --export-gate" in package
    assert "Only when it is not in context" in package


# --------------------------------------------------------------------------
# #594: the snippet-root probe, its layout question and its disk check
# --------------------------------------------------------------------------


def test_the_probe_takes_only_exported_roots_as_evidence():
    probe = _read(PROBE)
    listing = _section(probe, "## Probe", "## Layout Question")
    assert "for each skill in step 1 §1's `result.manifest.exports`" in listing
    assert "current skill" not in probe, "a skill the manifest does not list holds the draft root only"
    assert "`draft_roots`" in listing and "`disk_root`" in listing
    for branch in ("`observed_prefixes` is empty", "`mismatch` is false", "`mismatch` is true"):
        assert branch in listing, branch
    assert "### (d)" not in probe and "(d) Use the observed prefix for this run only" in probe


def test_the_layout_question_and_the_mismatch_gate_have_headless_defaults():
    probe = _read(PROBE)
    layout = _section(probe, "## Layout Question", "## Mismatch Gate")
    for option in ("**[I] IDE skill folder** (default)", "**[S] Shared skills folder**", "**[X] Cancel**",
                   "**Headless** [default I]", '"gate":"load-skill.snippet-root-layout"'):
        assert option in layout, option
    assert "`{project-root}/_bmad/skf/config.yaml`" in layout, "the halt message names the project path"
    gate = _section(probe, "## Mismatch Gate", "### Choice handling")
    assert "**Headless default, by the disk:** take (d) when `disk_root` is the observed prefix" in gate
    assert '"gate":"load-skill.snippet-root-probe"' in gate and '"disk_root":"{disk_root}"' in gate
    choices = _section(probe, "### Choice handling", None)
    assert "bind `{snippet_skill_root_override}` ← the observed prefix for this run" in choices
    assert "drop-skill and rename-skill read only `config.yaml`" in choices


def test_option_d_binds_the_root_steps_3_and_4_read():
    """architecture-1: (d) used to set a run-only root no stage read."""
    root = _section(_read(SNIPPET), "### 2.7. Resolve Skill Root Path", "### 2.8. ")
    assert "**If `{snippet_skill_root_override}` is set** (by `config.yaml`, or for this run by step 1's " \
           "snippet-root option (d))" in root
    assemble = _section(_read(UPDATE), "#### 4b. Assemble One Body per Target", "#### 4c. ")
    assert '[--skill-root-override "{snippet_skill_root_override}"]' in assemble
    assert "only when `{snippet_skill_root_override}` is set (by `config.yaml`, or for this run by step 1's " \
           "snippet-root option (d))" in assemble
    back = _section(_read(LOAD), "### 1b. Snippet Root", "### 1c. ")
    assert "after the mismatch gate's (b) or (d), where (d) binds `{snippet_skill_root_override}`" in back
    assert "continue at §1c" in back


def _probe_call(snippets: list[Path], project: Path) -> list[str]:
    """The documented root-probe call, filled in as an agent would, without a shell."""
    [call] = [line for line in _fenced_lines(_read(PROBE)) if " root-probe " in line]
    words = shlex.split(call)
    assert words[:2] == ["python3", "{rebuildManagedSectionsHelper}"], call
    values = {"{rebuildManagedSectionsHelper}": [str(REBUILD_PY)], "{snippet-1}": [str(p) for p in snippets],
              "{snippet-2}": [], "…": [], "{reference_root}": [".claude/skills/"],
              "{project-root}": [str(project)]}
    argv = [sys.executable]
    for word in words[1:]:
        argv.extend(values.get(word, [word]))
    return argv


def _exported(project: Path, name: str, root: str) -> Path:
    snippet = project / "skills" / name / "1.0.0" / name / "context-snippet.md"
    snippet.parent.mkdir(parents=True)
    snippet.write_bytes(f"[{name} v1.0.0]|root: {root}{name}/\n|IMPORTANT: {name} v1.0.0\n".encode("utf-8"))
    return snippet


@pytest.mark.parametrize("roots, installed, branch, disk_root", [
    ({"zod": "skills/"}, {}, "layout", None),
    ({"zod": ".claude/skills/"}, {}, "fast", None),
    ({"zod": "vendor/skills/"}, {"vendor/skills/": ["zod"]}, "mismatch", "vendor/skills/"),
    ({"zod": "vendor/skills/"}, {".claude/skills/": ["zod"]}, "mismatch", ".claude/skills/"),
    ({"zod": "vendor/skills/"}, {}, "mismatch", None),
], ids=["drafts-only", "same-root", "earlier-root-holds", "ide-root-holds", "nothing-installed"])
def test_the_documented_probe_picks_the_branch_and_the_disk_root(tmp_path, roots, installed, branch, disk_root):
    project = tmp_path / "project"
    snippets = [_exported(project, name, root) for name, root in roots.items()]
    for prefix, names in installed.items():
        for name in names:
            skill = project / prefix / name / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_bytes(b"# skill\n")
    proc = subprocess.run(_probe_call(snippets, project), capture_output=True, text=True, encoding="utf-8",
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    taken = "layout" if not out["observed_prefixes"] else "mismatch" if out["mismatch"] else "fast"
    assert taken == branch
    assert out["disk_root"] == disk_root
    if branch == "mismatch":
        # The prose's headless rule: (d) only when the earlier root alone holds the skills.
        headless = "d" if out["disk_root"] == out["observed_prefixes"][0] else "b"
        assert headless == ("d" if disk_root == "vendor/skills/" else "b")


# --------------------------------------------------------------------------
# The export-gate halt names the heading it matched
# --------------------------------------------------------------------------


def test_the_export_gate_halt_names_the_section_7b_heading():
    validation = _section(_read(LOAD), "**Validation (the export gate):**", "### 3. Read Skill Metadata")
    assert "`validation.crossref_7b.{heading,heading_line}`" in validation
    assert ("Section 7b is the `{validation.crossref_7b.heading}` heading at line "
            "{validation.crossref_7b.heading_line}") in validation
    assert "Run create-skill to generate a complete skill first." not in validation


# --------------------------------------------------------------------------
# #596: the customize.toml comments, checked against the helpers
# --------------------------------------------------------------------------


def _comment_above(toml: str, key: str) -> str:
    lines = toml[:toml.index(f"\n{key} = ")].split("\n")
    block = []
    for line in reversed(lines):
        if line.startswith("#"):
            block.append(line)
        elif block:
            break
    return "\n".join(reversed(block))


def test_on_complete_says_it_runs_a_shell_command():
    toml = (EXPORT / "customize.toml").read_text(encoding="utf-8")
    comment = _comment_above(toml, "on_complete")
    assert "a shell command, not an instruction" in comment
    assert '`<value> --result-path="<per-run result JSON>"`' in comment
    hook = _section(_read("references/summary.md"), "### 6b. Post-Export Hook (Optional)", "### 7. ")
    assert '{onCompleteCommand} --result-path="{result_path}"' in hook


def test_snippet_format_path_names_the_lines_scripts_parse():
    toml = (EXPORT / "customize.toml").read_text(encoding="utf-8")
    assert tomllib.loads(toml)["workflow"]["snippet_format_path"] == ""
    comment = _comment_above(toml, "snippet_format_path")
    for fixed in ("assets/snippet-format.md", "`[{skill-name} v{version}]|root: {skill_root}{skill-name}/`",
                  "skipped_malformed_snippet", "`|IMPORTANT:`", "`writing {skill-name} code`",
                  "`|gotchas:`", "`[CARRIED]`", "bare `|`",
                  "quick-start, api and key-types lines, and the stack and integrations"):
        assert fixed in comment.replace("\n# ", " ").replace("\n#   ", " "), fixed
    assert "`snippet_format_path` in `customize.toml`" in _read(SNIPPET_FORMAT)


def _template(heading: str) -> str:
    text = _read(SNIPPET_FORMAT)
    block = re.search(r"^```markdown\n(.*?)^```", text[text.index(heading):], re.S | re.M)
    return block.group(1)


def _assemble(tmp_path: Path, snippet: str) -> dict:
    skills = tmp_path / "skills"
    package = skills / "zod" / "1.4.0" / "zod"
    package.mkdir(parents=True)
    (package / "context-snippet.md").write_bytes(snippet.encode("utf-8"))
    (package / "metadata.json").write_bytes(json.dumps({"name": "zod", "skill_type": "single"}).encode("utf-8"))
    manifest = {"schema_version": "2", "exports": {"zod": {"active_version": "1.4.0", "versions": {
        "1.4.0": {"ides": ["claude-code"], "last_exported": "2026-09-01", "status": "active"}}}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    out = tmp_path / "stage" / "CLAUDE.md.skf-content"
    proc = subprocess.run([sys.executable, str(REBUILD_PY), "assemble", str(tmp_path / "CLAUDE.md"),
                           "--skills-folder", str(skills), "--skill-root", ".claude/skills/", "--out", str(out)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    result["body"] = out.read_bytes().decode("utf-8")
    return result


def _filled(template: str) -> str:
    return (template.replace("{skill_root}", ".claude/skills/").replace("{skill-name}", "zod")
            .replace("{version}", "1.4.0"))


def test_a_restyled_first_line_leaves_the_skill_out_of_the_section(tmp_path):
    """The comment's first fixed line: assemble refuses a snippet whose header changed."""
    snippet = _filled(_template("## Single Skill Snippet Template"))
    restyled = "### zod 1.4.0 (.claude/skills/zod/)\n" + snippet.split("\n", 1)[1]
    result = _assemble(tmp_path, restyled)
    assert [s["skill_name"] for s in result["skipped_malformed_snippet"]] == ["zod"]
    assert "zod" not in result["body"]


def test_an_added_line_is_free_and_reaches_the_section(tmp_path):
    """The comment says a copy may add a line, such as an owner line."""
    snippet = _filled(_template("## Single Skill Snippet Template")).rstrip("\n") + "\n|owner: platform-team\n"
    result = _assemble(tmp_path, snippet)
    assert result["skipped_malformed_snippet"] == []
    assert "|[zod v1.4.0]|root: .claude/skills/zod/" in result["body"] and "|owner: platform-team" in result["body"]
