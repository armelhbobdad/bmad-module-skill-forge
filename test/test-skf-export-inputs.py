#!/usr/bin/env python3
"""export-skill's inputs, helpers and headless contract (wave 5).

Step prose is not executed by any test, so these checks pin it and run the
commands it documents:

- #594: On Activation resolves every helper steps 1 to 4 cannot run without,
  the skill inventory included, before any prompt or write, and no step
  resolves one again (the test-report lookup is advisory and stays in step
  1); every flag the contract lists is parsed, `--context-file` included;
  the snippet-root probe takes only roots an earlier export chose as
  evidence, asks one layout question when there is none, and resolves a
  mismatch headless by the folder on disk that holds the skills; option (d)
  binds the root steps 2 and 3 read.
- #596: the `on_complete` and `snippet_format_path` comments say what runs and
  which snippet lines scripts parse, and the helpers agree with them.
- #599: no step keeps a by-hand fallback for a helper activation resolved.
- #600: the headless contract lives in references/invocation-contract.md
  behind a one-line pointer, load-skill.md §5 renders the export-gate
  verdict without restating it, and the description names its object.
- #1162: the export gate's `package` object feeds step 1's confirm screen,
  one table with the version and the package status of every skill, §1c
  states step 1's batch rules, and update-context.md asks one question
  that names every target with its case.
- The export-gate halt names the Section 7b heading the gate matched.
- #1111: the `activation_steps_append` entries run in step 6, after the
  exit-4 checks of steps 4 and 5, not in step 3.
- #1163: step 1 lists the skills `--all` and the menu offer through the
  inventory's `exportable` action, the snippet-root probe builds its paths
  from the manifest, and a run with `passive_context: false`, which On
  Activation binds once, takes no snippet-root question.
- #1166: SKILL.md stays under its 2,500-token budget with the Run log rule,
  its run folder moved to references/result-envelope.md, and step 2 runs
  `{validateOutputHelper}` too.
"""

from __future__ import annotations

import json
import os
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
INVENTORY_PY = SRC / "shared" / "scripts" / "skf-skill-inventory.py"

SKILL_MD = "SKILL.md"
CONTRACT = "references/invocation-contract.md"
LOAD = "references/load-skill.md"
PROBE = "references/preflight-snippet-root-probe.md"
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
# #1111: the step that loads the first stage runs the append entries, after every step that can halt.
LOAD_STEP = ("6. Execute each entry in `workflow.activation_steps_append` in order, then load, read the full file, "
             "and execute `references/load-skill.md` to begin the workflow.")


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
    for gate in ("step 1 §1b", "and `passive_context` is not false", "the layout question", "(headless: [I]",
                 "the mismatch gate", "checks the disk", "step 1 §6", "step 3 §3b", "§4c.1", "step 3 §8"):
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
    assert skill.index("4. **Resolve the helpers") < skill.index(LOAD_STEP)


# The step each reference file that names an activation helper belongs to.
REFERENCE_STEPS = {"load-skill.md": 1, "preflight-snippet-root-probe.md": 1, "generate-snippet.md": 2,
                   "update-context.md": 3, "orphan-context-detection.md": 3, "orphan-row-detection.md": 3,
                   "token-report.md": 4, "summary.md": 5}


def test_each_helper_lists_the_steps_that_run_it():
    """#1164: the steps On Activation lists beside a helper are the steps whose files name it (step 2 now runs the
    rebuild helper's `gotchas` action and no longer reads the manifest)."""
    resolve = _section(_read(SKILL_MD), "4. **Resolve the helpers and create the run folder.**",
                       "5. **Pre-flight write check.**")
    for name in ACTIVATION_HELPERS:
        if name == "emitEnvelopeHelper":
            continue  # every envelope, whatever the step
        [line] = [line for line in resolve.splitlines() if line.lstrip().startswith(f"- `{{{name}}}` ←")]
        listed = re.search(r"\((steps? [\d, and]+)\)\.$", line.rstrip())
        assert listed, line
        files = [path.name for path in sorted((EXPORT / "references").glob("*.md"))
                 if f"{{{name}}}" in path.read_text(encoding="utf-8")]
        assert set(files) <= set(REFERENCE_STEPS), (name, files)
        assert {int(step) for step in re.findall(r"\d+", listed.group(1))} == \
            {REFERENCE_STEPS[file] for file in files}, (name, files)


def test_skill_md_stays_under_its_token_budget():
    """#1166 architecture-7: SKILL.md measured 2,715 cl100k tokens at 11,006 characters, over the 2,500-token prepass
    guideline. With the headless-only run folder moved to the Run Folder section of references/result-envelope.md,
    the Run log rule added and the trims the issue names, it measures 2,474 cl100k tokens at 10,049 characters.
    10,050 characters holds it there without a tokenizer."""
    assert len(_read(SKILL_MD)) < 10_050, len(_read(SKILL_MD))
    resolve = _section(_read(SKILL_MD), "4. **Resolve the helpers and create the run folder.**",
                       "5. **Pre-flight write check.**")
    [line] = [line for line in resolve.splitlines() if line.lstrip().startswith("- `{validateOutputHelper}` ←")]
    assert line.endswith("(steps 1 and 2)."), "generate-snippet §4 checks each draft with it"


def test_the_append_entries_run_after_the_pre_flight_halts():
    """#1111: On Activation step 3 runs only the prepend entries; step 6, after the exit-4 checks of steps 4 and 5,
    runs the append entries and then loads load-skill.md, as customize.toml says."""
    skill = _read(SKILL_MD)
    customization = _section(skill, "3. **Resolve workflow customization.**",
                             "4. **Resolve the helpers and create the run folder.**")
    assert "activation_steps_append" not in customization
    assert "activation_steps_prepend" in customization
    assert skill.count(LOAD_STEP) == 1
    assert skill.index("5. **Pre-flight write check.**") < skill.index(LOAD_STEP)
    assert skill.index("on-activation §5") < skill.index(LOAD_STEP)
    after = skill[skill.index(LOAD_STEP):].split("\n## ", 1)[0]
    assert "HALT" not in after and after.count("activation_steps_append") == 1
    comment = _comment_above((EXPORT / "customize.toml").read_text(encoding="utf-8"), "activation_steps_append")
    assert "once activation completes successfully" in comment


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
# #600 leanness and #1162: step 1 §5 renders the verdict and restates none of it
# --------------------------------------------------------------------------

VALIDATE_PY = SRC / "shared" / "scripts" / "skf-validate-output.py"
COUNT_TOKENS_PY = SRC / "shared" / "scripts" / "skf-count-tokens.py"
CONFIRM_HEADER = "| # | Name | Version | Type | Authority | Confidence | Exports | References | Generated | Test | Package |"


def _summary_section() -> str:
    return _section(_read(LOAD), "### 5. Present Skill Summary", "### 6. Confirmation Gate")


def test_the_confirm_screen_renders_the_export_gate_verdict_without_restating_it():
    summary = _summary_section()
    assert "├──" not in summary, "the layout tree drives no check"
    for restated in ("Enum membership", "NOT READY", "ProbeOrder", "metadata.json`:", "`.md` files"):
        assert restated not in summary, restated
    assert "§2 halts on `NOT_READY`, so `export_status` is `READY` or `WARNINGS` here." in summary
    for field in ("`export_status`", "`validation.metadata.recommended_missing`", "`validation.crossref_7b.orphans`"):
        assert field in summary, field
    # The verdict lost from context: §5 runs the gate again on that package.
    assert ("Only when it is not in context, run `python3 {validateOutputHelper} {resolved_skill_package} "
            "--export-gate` again: the same package gives the same verdict.") in summary
    gate = _section(_read(LOAD), "**Validation (the export gate):**", "### 3. Read Skill Metadata")
    assert "**Retain this JSON as the export verdict**: §5 renders each skill's package status from it" in gate
    assert "`package`, the metadata fields and the reference count §3 binds" in gate
    # #1162 leanness-3: the gate's line names the verdict fields to read, not the checks its docstring lists.
    [verdict] = [line for line in gate.splitlines() if line.startswith("The script emits one JSON verdict")]
    assert verdict.startswith("The script emits one JSON verdict. Read `result` (PASS/FAIL), `export_status` "
                              "(READY/WARNINGS/NOT_READY), the issue arrays under "
                              "`validation.metadata.{issues,enum_issues,recommended_missing}` and "
                              "`validation.crossref_7b.{missing,orphans}`")
    for restated in ("docstring lists every check", "present and valid", "agentskills.io fields",
                     "Quick/Forge/Forge+/Deep", "low orphan warning"):
        assert restated not in gate, restated
    # load-skill §2 names what §3 and §5 read in one line, before the gate, and loads no package file itself.
    before_gate = _read(LOAD).split("**Validation (the export gate):**", 1)[0]
    assert ("The export gate below reads what §3 and §5 show: `metadata.json` and `SKILL.md`, each a high issue "
            "when it is missing, and the files under `references/`. Step 2 reads the prior `context-snippet.md` "
            "itself.") in before_gate


def test_step_1_confirms_with_one_table_holding_the_version_and_the_package_status():
    """leanness-4, enhancement-2: one field list in one table, a row per skill, then the configuration
    once and one question; no single-skill and batch templates side by side."""
    summary = _summary_section()
    tables = [line for line in summary.splitlines() if line.startswith("| # |")]
    assert tables == [CONFIRM_HEADER]
    [row] = [line for line in summary.splitlines() if line.startswith("| {i} |")]
    assert row.count("|") == CONFIRM_HEADER.count("|"), "a cell per column"
    assert "{export_status} |" in row and "{Version}" in row
    for stale in ("Single-skill mode", "Multi-skill mode", "**Top Exports:**", "(applies to all)",
                  "Is this the correct skill", "Are these the correct skills"):
        assert stale not in summary, stale
    assert summary.count("**Export Configuration:**") == 1
    assert summary.count('**Export {this skill / these N skills}?**"') == 1
    assert '"**{N} skill(s) loaded and validated.**' in summary
    cells = summary[summary.index("Fill the capitalized cells"):]
    for rule in ("- **Version:** `v{resolved_version}`, with ` (migrated from the flat layout)` when §2 migrated",
                 "`flat layout, would migrate` when `{resolved_version}` is null (a flat skill in a dry run)",
                 "for a stack, `stack ({components_count} libraries, {integrations_count} integrations)`",
                 "- **Confidence:** `{confidence_tier}`, with ` (forge {forge_tier})` when `{forge_tier}` is set.",
                 "- **References:** `{references_count}`, or `none` when it is 0.",
                 "`{testResult} ({score}%)`", "`{testResult}` alone when its score is null", "`no verdict`",
                 "`none` when no report was found", "`not checked`"):
        assert rule in cells, rule
    # The Warnings line appears only for a WARNINGS skill and never stops the export.
    assert ("{For each skill whose `export_status` is `WARNINGS`:}\n**Warnings for {name}** (none of them stops "
            "the export)") in summary
    # The dry-run rung leaves the version null, which the Version cell names.
    assert "`{resolved_version}` and `{forge_version}` stay null" in _section(
        _read(LOAD), "### 2. Load and Validate Skill Artifacts", "**Validation (the export gate):**")


def test_the_confirmation_gate_continues_to_snippet_generation():
    load = _read(LOAD)
    gate = _section(load, "### 6. Confirmation Gate", None)
    assert ('"**Select:** [C] Continue to snippet generation | [X] Cancel and exit (or type `cancel` / `exit` / '
            '`:q`)"') in gate
    assert 'display "Cancelled: no snippet or context file writes were performed."' in gate
    assert "packaging" not in load.lower(), "no Package stage remains"
    assert "nextStepFile: 'generate-snippet.md'" in _frontmatter(load)


def test_section_1c_states_step_1s_batch_rules():
    """architecture-4: the batch matrix drifted from each stage's own rule; §1c keeps only step 1's."""
    batch = _section(_read(LOAD), "### 1c. ", "### 2. ")
    assert "references/" not in batch and "matrix" not in batch, "§1c loads no batch reference"
    assert "§2 to §5 run for each skill in `skill_batch`, in order" in batch
    assert "§5 shows every skill in one table, a row per skill, so §6 asks once for the whole batch" in batch
    halt = next(line for line in batch.splitlines() if "fails §2" in line)
    assert "`not-skf-output`" in halt and "HALT as §2 states for that skill" in halt
    assert "no skill of the batch is exported" in halt
    assert "halt_reason" not in batch, "§2 names each halt's reason and phase"
    assert "each later stage's Rules state its own" in batch
    row = _row(_read(CONTRACT), "Multi-skill mode")
    assert "`references/load-skill.md` §1c holds step 1's batch rules, and each later stage's Rules hold its own" in row
    for path in sorted((EXPORT / "references").glob("*.md")):
        assert "See step 1 §1c." not in path.read_text(encoding="utf-8"), path.name


def _write_package(root: Path, meta: dict, *, refs: tuple[str, ...] = (), files: tuple[str, ...] = ()) -> Path:
    package = root / meta["name"] / meta["version"] / meta["name"]
    package.mkdir(parents=True)
    (package / "SKILL.md").write_bytes(f"---\nname: {meta['name']}\ndescription: demo\n---\n\n# demo\n".encode("utf-8"))
    (package / "metadata.json").write_bytes(json.dumps(meta).encode("utf-8"))
    for rel in refs + files:
        (package / rel).parent.mkdir(parents=True, exist_ok=True)
        (package / rel).write_bytes(b"x\n")
    return package


def _run_documented_gate(package: Path) -> dict:
    gate = _section(_read(LOAD), "**Validation (the export gate):**", "### 3. Read Skill Metadata")
    [call] = [line for line in _fenced_lines(gate) if "--export-gate" in line]
    words = shlex.split(call)
    assert words[:3] == ["python3", "{validateOutputHelper}", "{resolved_skill_package}"], call
    proc = subprocess.run([sys.executable, str(VALIDATE_PY), str(package), *words[3:]], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.stdout, proc.stderr
    return json.loads(proc.stdout)


SINGLE_META = {"name": "zod", "version": "3.23.8", "skill_type": "single", "source_authority": "official",
               "exports": ["z", {"name": "ZodType", "type": "class"}, {"type": "function"}, "parse",
                           {"name": "safeParse", "type": "function"}, "infer", "ZodError"],
               "generation_date": "2026-11-01", "confidence_tier": "Forge+", "description": "zod",
               "source_repo": "https://github.com/colinhacks/zod", "language": "typescript",
               "tool_versions": {"skf": "3.0.0"}}
STACK_META = {"name": "web-stack", "version": "1.0.0", "skill_type": "stack", "source_authority": "community",
              "exports": [], "generation_date": "2026-11-02", "confidence_tier": "T1-low", "forge_tier": "Deep",
              "library_count": 3, "integration_count": 2, "libraries": ["a", "b", "c"],
              "integration_pairs": [["a", "b"], ["b", "c"]], "language": "typescript",
              "tool_versions": {"skf": "3.0.0"}}


@pytest.mark.parametrize("meta, expected", [
    (SINGLE_META, {"exports_count": 7, "top_exports": ["z", "ZodType", "parse", "safeParse", "infer"],
                   "references_count": 3, "components_count": None, "integrations_count": None,
                   "forge_tier": None}),
    (STACK_META, {"exports_count": 0, "top_exports": [], "references_count": 0, "components_count": 3,
                  "integrations_count": 2, "forge_tier": "Deep"}),
], ids=["single", "stack"])
def test_each_section_3_binding_reads_a_field_the_documented_gate_prints(tmp_path, meta, expected):
    """determinism-6: §3 binds the gate's `package` object instead of reading metadata.json by hand."""
    refs = ("references/a.md", "references/sub/b.md", "references/data.json") if meta is SINGLE_META else ()
    package = _write_package(tmp_path, meta, refs=refs)
    out = _run_documented_gate(package)
    read = _section(_read(LOAD), "### 3. Read Skill Metadata", "### 4. ")
    bindings = re.findall(r"`\{(\w+)\}` ← `package\.(\w+)`", read)
    assert {field for _, field in bindings} == set(out["package"]), "§3 binds every field the gate prints"
    bound = {name: out["package"][field] for name, field in bindings}
    for name in ("skill_type", "source_authority", "confidence_tier"):
        assert f"{{{name}}}" in _read("references/summary.md") and name in bound, name
    assert {k: bound[k] for k in expected} == expected
    assert (bound["name"], bound["version"], bound["skill_type"]) == (meta["name"], meta["version"],
                                                                       meta["skill_type"])
    # The References cell is the count the token report gives for the same package.
    proc = subprocess.run([sys.executable, str(COUNT_TOKENS_PY), str(package)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert json.loads(proc.stdout)["references_total"]["count"] == bound["references_count"]
    # Every placeholder §5 fills from §3 is one §3 binds.
    cells = _summary_section()[_summary_section().index("Fill the capitalized cells"):]
    used = set(re.findall(r"\{(\w+)\}", cells)) - {"resolved_version", "testResult", "score"}
    assert used <= set(bound), used - set(bound)
    assert out["result"] == "PASS" and "metadata.json`:" not in read


def test_a_warnings_package_names_the_field_and_the_orphan(tmp_path):
    """A missing recommended field and a Section 7b orphan: WARNINGS, and §5's Warnings line reads both."""
    meta = {k: v for k, v in SINGLE_META.items() if k != "language"}
    package = _write_package(tmp_path, meta, files=("scripts/run.sh",))
    out = _run_documented_gate(package)
    assert (out["result"], out["export_status"]) == ("PASS", "WARNINGS")
    assert [i["field"] for i in out["validation"]["metadata"]["recommended_missing"]] == ["language"]
    assert out["validation"]["crossref_7b"]["orphans"] == ["scripts/run.sh"]
    warnings = next(line for line in _summary_section().splitlines() if line.startswith("- **Warnings:**"))
    assert "the `field` of each `validation.metadata.recommended_missing` entry" in warnings
    assert "each path in `validation.crossref_7b.orphans`" in warnings


def test_the_stages_run_1_to_6_and_each_heading_matches_its_row():
    """#1162: the Package stage is gone, so the six stages renumber and no file names a seventh."""
    stages = _section(_read(SKILL_MD), "## Stages", "## Invocation Contract")
    rows = re.findall(r"^\| (\d) \| ([^|]+?) \| (references/[a-z-]+\.md) \|", stages, re.M)
    assert [int(n) for n, _, _ in rows] == [1, 2, 3, 4, 5, 6]
    assert [name for _, name, _ in rows] == ["Load Skill", "Generate Snippet", "Update Context", "Token Report",
                                             "Summary", "Workflow Health Check"]
    for number, name, rel in rows:
        assert f"\n# Step {number}: {name}\n" in _read(rel), rel
    chain = [rel.split("/")[1] for _, _, rel in rows]
    for here, there in zip(chain, chain[1:]):
        assert f"nextStepFile: '{there}'" in _frontmatter(_read(f"references/{here}")), here
    # Every other reference is one a stage loads by name (test-skf-export-terminal.py checks each route).
    loaded = set(re.findall(r"`references/([a-z-]+\.md)`", _read(SKILL_MD) + _read(LOAD) + _read(UPDATE)))
    for path in sorted((EXPORT / "references").glob("*.md")):
        assert path.name in set(chain) | loaded, f"{path.name}: no stage runs or loads it"
    for path in sorted(EXPORT.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?i)\bstep[ -]0?7\b|\bStep 02\b", text), path.name


def test_update_context_asks_once_naming_every_target_with_its_case():
    """leanness-4: one preview block per target and one prompt, with no counter that contradicts it."""
    update = _read(UPDATE)
    for stale in ("platform {i}", "{total}", "Multi-target behavior", "Ready to write changes",
                  "write changes to all targets"):
        assert stale not in update, stale
    preview = _section(update, "### 7. Present Change Preview", "### 8. ")
    assert "then one block per target, in the order §3 set, from its `{section_diff}`" in preview
    # #1165: the helper's diff gives the header line, the rows and the unified diff; no count is bound by hand.
    assert ('"**Target:** `{context_file}` ({case})\n**Header:** `{header.old}` → `{header.new}`\n'
            "**Rows:** {each `rows.added` entry as added `{skill_name} v{version}`, each `rows.removed` entry as "
            "removed `{skill_name} v{version}`, and each `rows.changed` entry as changed `{skill_name}` "
            "v{old_version} → v{new_version}, with root `{old_root}` → `{new_root}` when the two differ") in preview
    # Four backticks: a section line of three backticks shows as a context line that would close a three-backtick fence.
    assert "\n````diff\n{unified}\n````\n" in preview
    assert "show the version once when `old_version` equals `new_version`" in preview
    assert "and a null root as `(none)`" in preview
    assert '"No change to the section." in place of the `diff` fence when `unified` is `""`' in preview
    assert "**Content outside markers:** {preserved / n/a (new file)}" in preview
    assert "{n_single}" not in update and "{n_stack}" not in update
    # An orphaned file orphan-context (a) listed gets its own block after the targets, and the prompt names it.
    clear = ('"**Target:** `{context_file}` (clear)\nIts managed section and both markers are removed; the content '
             'outside them stays."')
    assert preview.index("Then one block per file in `orphans_to_clear`") > preview.index("```diff") and clear in preview
    selects = [line for line in update.splitlines() if "**Select:**" in line]
    assert len(selects) == 1, selects
    real = _section(update, "**If NOT dry-run:**", "#### Gate handling")
    assert selects[0] in real
    assert ("[C] Continue: write changes to {each target as `{context_file}` ({case}), then each file in "
            "`orphans_to_clear` as `{context_file}` (clear), comma-separated} | "
            "[X] Cancel and exit (or type `cancel` / `exit` / `:q`)") in selects[0]
    assert "**[DRY RUN] No files will be written." in _section(update, "**If dry-run mode:**", "**If NOT dry-run:**")


# --------------------------------------------------------------------------
# #594: the snippet-root probe, its layout question and its disk check
# --------------------------------------------------------------------------


def test_the_probe_takes_only_exported_roots_as_evidence():
    probe = _read(PROBE)
    listing = _section(probe, "## Probe", "## Layout Question")
    assert "The helper reads the manifest itself and, for each skill whose `active_version` has an entry under " \
           "`versions`, probes" in listing
    assert "`snippet_files`" in listing and "{snippet-1}" not in probe and "result.manifest" not in probe
    assert "HALT as load-skill.md §1 states for a corrupt export manifest, with the helper's `error`" in listing
    assert "With no snippet to list" not in listing, "an empty `observed_prefixes` already asks the question"
    assert "current skill" not in probe, "a skill the manifest does not list holds the draft root only"
    assert "`draft_roots`" in listing and "`disk_root`" in listing
    for branch in ("`observed_prefixes` is empty", "`mismatch` is false", "`mismatch` is true"):
        assert branch in listing, branch
    assert "### (d)" not in probe and "(d) Use the observed prefix for this run only" in probe


def test_the_layout_question_and_the_mismatch_gate_have_headless_defaults():
    probe = _read(PROBE)
    layout = _section(probe, "## Layout Question", "## Mismatch Gate")
    for option in ("**[I] IDE skill folder** (default)", "**[S] Shared skills folder**", "**[X] Cancel**",
                   "**GATE [default: I]**: headless", '"gate":"load-skill.snippet-root-layout"'):
        assert option in layout, option
    assert "`{project-root}/_bmad/skf/config.yaml`" in layout, "the halt message names the project path"
    gate = _section(probe, "## Mismatch Gate", "### Choice handling")
    assert "**GATE [default: (d) or (b), by the disk]**: headless, take (d) when `disk_root` is the observed prefix" in gate
    assert '"gate":"load-skill.snippet-root-probe"' in gate and '"disk_root":"{disk_root}"' in gate
    choices = _section(probe, "### Choice handling", None)
    assert "bind `{snippet_skill_root_override}` ← the observed prefix for this run" in choices
    assert "drop-skill and rename-skill read only `config.yaml`" in choices


def test_option_d_binds_the_root_steps_2_and_3_read():
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


def test_a_run_with_passive_context_off_takes_no_snippet_root_question():
    """architecture-2: §4 read passive_context only after §1b had asked where a run with no snippet points it."""
    headless = _section(_read(SKILL_MD), "2. **Resolve `{headless_mode}`**", "3. **Resolve workflow customization.**")
    assert "`headless_mode: true` in `{sidecar_path}/preferences.yaml`. Default: false." in headless
    assert ("From the same file, bind `{passive_context}` ← its `passive_context`, true when the file or the key "
            "is absent.") in headless
    assert "A false value means this run writes no snippet and no managed-section row" in headless
    skip = _section(_read(LOAD), "### 1b. Snippet Root", "**Otherwise:**")
    assert ("Skip it too when `{passive_context}` is false: this run writes no snippet and no managed-section row, "
            "so no `root:` path is chosen.") in skip
    forge = _section(_read(LOAD), "### 4. Check Forge Configuration", "### 4b. ")
    assert "Read `{passive_context}`, which SKILL.md's On Activation bound" in forge
    assert "- If `passive_context: false`" in forge, "the wording the later stages name"
    # On Activation is the one place that reads the preferences file.
    for path in sorted((EXPORT / "references").glob("*.md")):
        assert "{sidecar_path}/preferences.yaml" not in path.read_text(encoding="utf-8"), path.name
    gates = _row(_read(CONTRACT), "Gates")
    assert ("step 1 §1b, only when config.yaml sets no `snippet_skill_root_override` and `passive_context` is not "
            "false:") in gates
    assert "`snippet_skill_root_override` and `passive_context` is not false." in _frontmatter(_read(PROBE))


def _probe_call(project: Path) -> list[str]:
    """The documented root-probe call, filled in as an agent would, without a shell."""
    [call] = [line for line in _fenced_lines(_read(PROBE)) if " root-probe " in line]
    words = shlex.split(call)
    assert words[:2] == ["python3", "{rebuildManagedSectionsHelper}"], call
    values = {"{rebuildManagedSectionsHelper}": [str(REBUILD_PY)],
              "{skills_output_folder}": [str(project / "skills")], "{reference_root}": [".claude/skills/"],
              "{project-root}": [str(project)]}
    argv = [sys.executable]
    for word in words[1:]:
        argv.extend(values.get(word, [word]))
    return argv


def _exported(project: Path, name: str, root: str) -> Path:
    """A snippet at the version the export manifest records for the skill."""
    snippet = project / "skills" / name / "1.0.0" / name / "context-snippet.md"
    snippet.parent.mkdir(parents=True)
    snippet.write_bytes(f"[{name} v1.0.0]|root: {root}{name}/\n|IMPORTANT: {name} v1.0.0\n".encode("utf-8"))
    manifest_path = project / "skills" / ".export-manifest.json"
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.is_file() else {
        "schema_version": "2", "exports": {}}
    manifest["exports"][name] = {"active_version": "1.0.0", "versions": {"1.0.0": {"status": "active"}}}
    manifest_path.write_bytes(json.dumps(manifest).encode("utf-8"))
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
    proc = subprocess.run(_probe_call(project), capture_output=True, text=True, encoding="utf-8",
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert [Path(p) for p in out["snippet_files"]] == snippets, "the helper builds each path from the manifest"
    taken = "layout" if not out["observed_prefixes"] else "mismatch" if out["mismatch"] else "fast"
    assert taken == branch
    assert out["disk_root"] == disk_root
    if branch == "mismatch":
        # The prose's headless rule: (d) only when the earlier root alone holds the skills.
        headless = "d" if out["disk_root"] == out["observed_prefixes"][0] else "b"
        assert headless == ("d" if disk_root == "vendor/skills/" else "b")


def _link_active(group: Path, version: str) -> None:
    """Point `active` at a version: a symlink, or a junction on Windows without the privilege."""
    active = group / "active"
    try:
        active.symlink_to(version, target_is_directory=True)
    except OSError as e:
        if os.name != "nt" or getattr(e, "winerror", None) not in (1314, 5):
            raise
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(active), str((group / version).resolve())],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise OSError(f"junction fallback failed: {result.stderr.strip() or result.stdout.strip()}") from e


def _exportable_call(skills: Path, all_skills: bool) -> dict:
    """§1's documented `exportable` call, filled in as an agent would, without a shell."""
    discovery = _section(_read(LOAD), "**Skill Path Discovery", "**Flag Parsing:**")
    [call] = [line for line in _fenced_lines(discovery) if " exportable " in line]
    words = shlex.split(call)
    assert words[:3] == ["uv", "run", "{skillInventoryHelper}"], call
    values = {"{skills_output_folder}": [str(skills)], "[--all]": ["--all"] if all_skills else []}
    argv = [sys.executable, str(INVENTORY_PY)]
    for word in words[3:]:
        argv.extend(values.get(word, [word]))
    proc = subprocess.run(argv, capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.decode("utf-8"))


def test_the_documented_exportable_call_leaves_out_the_deprecated_skill(tmp_path):
    """determinism-2: a deprecated skill on disk came back through the menu's hand-built scan."""
    skills = tmp_path / "skills"
    marker = {"generated_by": "create-skill", "tool_versions": {"skf": "3.0.0"}}
    for name, version in (("zod", "1.0.0"), ("old", "2.0.0"), ("fresh", "0.1.0")):
        package = skills / name / version / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_bytes(f"---\nname: {name}\n---\n".encode("utf-8"))
        (package / "metadata.json").write_bytes(json.dumps({"name": name, **marker}).encode("utf-8"))
        _link_active(skills / name, version)
    (skills / "module").mkdir()
    (skills / "module" / "SKILL.md").write_bytes(b"---\nname: module\n---\n")
    exports = {name: {"active_version": version, "versions": {version: {"status": status}}}
               for name, version, status in (("zod", "1.0.0", "active"), ("old", "2.0.0", "deprecated"))}
    (skills / ".export-manifest.json").write_bytes(json.dumps({"schema_version": "2", "exports": exports}).encode())
    menu = _exportable_call(skills, all_skills=False)
    assert [(s["name"], s["source"]) for s in menu["skills"]] == [("fresh", "disk"), ("zod", "manifest")]
    assert (menu["deprecated"], menu["not_skf_output"]) == (["old"], ["module"])
    batch = _exportable_call(skills, all_skills=True)
    assert [s["name"] for s in batch["skills"]] == ["zod"]
    # The prose binds and shows what the call prints, and filters nothing itself.
    discovery = _section(_read(LOAD), "**Skill Path Discovery", "**Flag Parsing:**")
    assert "`skill_batch` ← every `skills[].name`" in discovery
    for line in ('"Skipped (not SKF output): {not_skf_output}"',
                 '"Skipped (deprecated in the export manifest): {deprecated}"'):
        assert discovery.count(line) == 1, line
    assert "result.manifest" not in _read(LOAD) and "`skf_skill` is true" not in discovery
    # A manifest the helper cannot read halts; an empty list (every entry deprecated, or no folder) finds nothing.
    assert ("A non-zero exit (an export manifest the helper cannot read, or a `{skills_output_folder}` that is not a "
            'folder) is a HALT (exit code 3, `halt_reason: "resolution-failure"`, phase `load-skill §1`) with the '
            "helper's `error`.") in discovery
    assert ('If no skills found (`skills` is empty), HALT (exit code 3, `halt_reason: "resolution-failure"`, phase '
            '`load-skill §1`): "No skills found in {skills_output_folder}/.') in discovery
    assert discovery.index("**Headless guard:**") < discovery.index(" exportable ")


# --------------------------------------------------------------------------
# The export-gate halt names the heading it matched
# --------------------------------------------------------------------------


def test_the_export_gate_halt_names_the_section_7b_heading():
    validation = _section(_read(LOAD), "**Validation (the export gate):**", "### 3. Read Skill Metadata")
    assert "`validation.crossref_7b.{heading,heading_line}`" in validation
    assert ("Section 7b is the `{validation.crossref_7b.heading}` heading at line "
            "{validation.crossref_7b.heading_line}") in validation
    assert "Run create-skill to generate a complete skill first." not in validation
    # In a batch the halt names the skill that failed, so the operator knows which one to fix.
    assert '"**Export cannot proceed for `{skill-name}`.** Missing or invalid:' in validation


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


def _flat_comment(toml: str, key: str) -> str:
    return " ".join(line.lstrip("#").strip() for line in _comment_above(toml, key).splitlines())


def test_on_complete_says_it_runs_a_shell_command():
    """#1108: the hook runs from {project-root}, so the comment says so, its example names the script from there,
    and step 6b invokes it from there."""
    toml = (EXPORT / "customize.toml").read_text(encoding="utf-8")
    comment = _comment_above(toml, "on_complete")
    assert '`<value> --result-path="<per-run result JSON>"`' in comment
    flat = _flat_comment(toml, "on_complete")
    assert "Optional post-export hook: a shell command run from {project-root}, not an instruction." in flat
    # The example is the override file it names: `[workflow]` first, or the key is ignored without a warning.
    example = comment.split("Example, in {project-root}/_bmad/custom/skf-export-skill.toml:\n", 1)[1]
    example = "\n".join(line.removeprefix("#").strip() for line in example.splitlines() if line.startswith("#   "))
    assert tomllib.loads(example) == {"workflow": {"on_complete": "{project-root}/scripts/publish-skill.sh"}}
    assert 'on_complete = "scripts/publish-skill.sh"' not in flat
    # Nothing between the resolver and the shell replaces the example's placeholder but the binding itself.
    [binding] = [line for line in _read("SKILL.md").splitlines() if "`{onCompleteCommand}` ←" in line]
    assert "`workflow.on_complete` with `{project-root}` replaced by the project root, else empty" in binding
    hook = _section(_read("references/summary.md"), "### 6b. Post-Export Hook (Optional)", "### 7. ")
    assert '{onCompleteCommand} --result-path="{result_path}"' in hook
    assert "Otherwise invoke it now from `{project-root}`, after the emitter wrote the per-run record:" in hook


def test_snippet_format_path_names_the_lines_scripts_parse():
    toml = (EXPORT / "customize.toml").read_text(encoding="utf-8")
    # #1108: the bundled default is named, and a house copy lives outside the skill folder.
    assert tomllib.loads(toml)["workflow"]["snippet_format_path"] == "assets/snippet-format.md"
    assert "# --- Optional override. An empty string means the default named below. ---\n" in toml
    assert ("Default: assets/snippet-format.md, a path from the skill root. Keep a house-style copy outside the "
            "skill folder, which every update overwrites, and name it as {project-root}/<path to the copy>."
            ) in _flat_comment(toml, "snippet_format_path")
    comment = _comment_above(toml, "snippet_format_path")
    for fixed in ("assets/snippet-format.md", "`[{skill-name} v{version}]|root: {skill_root}{skill-name}/`",
                  "skipped_malformed_snippet", "`|IMPORTANT:`", "`writing {skill-name} code`",
                  "`|gotchas:`", "`[CARRIED]`", "bare `|`"):
        assert fixed in comment.replace("\n# ", " ").replace("\n#   ", " "), fixed
    # #1164: the `|api:` label and the gotchas separator are parsed too, by the rebuild helper's `gotchas` action.
    flat = _flat_comment(toml, "snippet_format_path")
    assert ("- the `|api:` label, and the `|gotchas:` label with its `; ` separator and its `[CARRIED]` marker: the "
            "rebuild helper's `gotchas` action reads them back in step 2") in flat
    assert ("The quick-start and key-types lines, and the stack and integrations lines, are free to change, as long "
            "as each anchor they hold resolves.") in flat
    assert "quick-start, api and key-types" not in flat
    # Review of #1166: step 2's draft check stops the export before assemble could leave the skill out.
    assert ("Step 2 checks each draft with skf-validate-output.py --snippet-check, which fails, among other things, "
            "a line 1 that does not start with the skill at its metadata.json version") in flat
    assert ("a draft that still fails after one correction stops the export with exit 4 (context-rebuild-failed)."
            ) in flat
    assert "leaves out a snippet whose first line differs" not in flat
    note = _read(SNIPPET_FORMAT)
    assert "`snippet_format_path` in `customize.toml`" in note
    assert ("the `|api:` label, the `|gotchas:` label with its `; ` separator and its `[CARRIED]` marker, which the "
            "rebuild helper's `gotchas` action reads back") in note
    assert "line 1, which names the skill at its metadata.json version, with its `root:` field" in note
    assert "stops the export (exit 4) on a draft that still fails after one correction" in note


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


# --------------------------------------------------------------------------
# architecture-6: every context file gets its own skill root
# --------------------------------------------------------------------------


def _joined_calls(text: str, word: str) -> list[str]:
    """The fenced lines of `text` that run `word`, backslash continuations joined."""
    joined = re.sub(r"\\\n\s*", "", "\n".join(_fenced_lines(text)))
    return [line for line in joined.split("\n") if f" {word} " in f" {line} "]


def _documented_argv(call: str, values: dict, override: str | None = None) -> list[str]:
    """A documented helper call filled in as an agent would, run without a shell (so on Windows too)."""
    group = '[--skill-root-override "{snippet_skill_root_override}"]'
    call = call.replace(group, group[1:-1] if override else "")
    argv = []
    for word in shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call)):
        whole = re.fullmatch(r"@@(\w+)@@", word)
        if whole and isinstance(values[whole.group(1)], list):
            argv.extend(values[whole.group(1)])
        else:
            argv.append(re.sub(r"@@(\w+)@@", lambda m: str(values[m.group(1)]), word))
    assert argv[:2] == ["python3", str(REBUILD_PY)], argv
    return [sys.executable, *argv[1:]]


@pytest.mark.parametrize("override", [None, "skills/"], ids=["ide-roots", "override"])
def test_two_ides_give_each_context_file_its_own_skill_root(tmp_path, override):
    """With ides [claude-code, codex], AGENTS.md lists the skills under Codex's
    `.agents/skills/`, not the `.claude/skills/` of the first target the snippet
    root came from; --skill-root-override still wins for both."""
    skills = tmp_path / "skills"
    package = skills / "zod" / "1.4.0" / "zod"
    package.mkdir(parents=True)
    (package / "context-snippet.md").write_bytes(
        b"[zod v1.4.0]|root: .claude/skills/zod/\n|IMPORTANT: zod v1.4.0: read SKILL.md before writing zod code.\n")
    (package / "metadata.json").write_bytes(json.dumps({"name": "zod", "skill_type": "single"}).encode("utf-8"))
    draft = tmp_path / "stage" / "drafts" / "zod" / "context-snippet.md"
    draft.parent.mkdir(parents=True)
    draft.write_bytes((package / "context-snippet.md").read_bytes())
    resolve = _section(_read(LOAD), "**Context File Resolution:**", "### 1b.")
    [call] = _joined_calls(resolve, "resolve-targets")
    values = {"rebuildManagedSectionsHelper": str(REBUILD_PY), "ides": "claude-code,codex",
              "skills_output_folder": str(skills), "batch_includes": "zod@1.4.0", "orphan_mode": "keep",
              "export_stage_dir": str(tmp_path / "stage"), "snippet_skill_root_override": override or ""}
    proc = subprocess.run(_documented_argv(call, values), capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    targets = json.loads(proc.stdout)["targets"]
    assert [(t["context_file"], t["skill_root"]) for t in targets] == [
        ("CLAUDE.md", ".claude/skills/"), ("AGENTS.md", ".agents/skills/")]
    # Step 2 binds the snippet's root once, from the first target; step 3 must not reuse it.
    values["skill_root"] = targets[0]["skill_root"]
    values["target_paths"] = [str(tmp_path / t["context_file"]) for t in targets]
    [assemble] = _joined_calls(_section(_read(UPDATE), "#### 4b. Assemble One Body per Target", "#### 4c. "),
                               "assemble")
    roots = {}
    for target in targets:
        values.update(context_path=str(tmp_path / target["context_file"]), context_file=target["context_file"],
                      target_skill_root=target["skill_root"])
        proc = subprocess.run(_documented_argv(assemble, values, override), capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        body = Path(json.loads(proc.stdout)["content_file"]).read_bytes().decode("utf-8")
        roots[target["context_file"]] = re.findall(r"\|root: (\S+)zod/", body)
    expected = override or None
    assert roots == {"CLAUDE.md": [expected or ".claude/skills/"], "AGENTS.md": [expected or ".agents/skills/"]}


def test_the_snippet_root_is_the_snippets_only():
    """Step 2's {skill_root} roots the snippet; step 3 passes each target's own root."""
    snippet = _read(SNIPPET)
    assert "§2.7 resolves `{skill_root}`, the snippet's root only" in snippet
    root = _section(snippet, "### 2.7. Resolve Skill Root Path", "### 2.8. ")
    assert "it is the snippet's root only" in root
    assert "step 3 builds each context file's managed section with that target's own skill root" in root
    update = _read(UPDATE)
    targets = _section(update, "### 3. Determine Target Files", "#### 3b.")
    assert "its skill root `{target_skill_root}` is that entry's own `skill_root`" in targets
    assemble = _section(update, "#### 4b. Assemble One Body per Target", "#### 4c. ")
    assert '--skill-root "{target_skill_root}"' in assemble and "{skill_root}" not in assemble
