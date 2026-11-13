#!/usr/bin/env python3
"""brief-skill's ratify Revise Scope and activation prose (issue #603).

A ratified brief skips steps 2 and 3, so step 4's `[R] Revise Scope` must
run the target analysis before scope definition for every source brief,
and analyze-source writes its briefs without `source_type` (a source brief
by the schema default). SKILL.md must resolve `document_output_language`,
the language step 1 writes the description in, and read `headless_mode`
from the sidecar's preferences.yaml. The ratify route itself is one file,
gather-intent-ratify.md, and an [R] pass keeps a ratified brief's
component-library fields and its amendments log. Step 5b gate run 3
(determinism-3): step 5 writes a ratified brief from the file it ratified,
with a patch of the fields steps 3 and 4 can change, so no field it holds
is retyped or dropped. #1136 (enhancement-3): a target, a brief path
included, given when invoking the skill answers the first prompt. #1137
(enhancement-4): step 1 offers `[U] Revise` of a finished brief for the
target through the ratify route, and a derive run that overwrites a brief
keeps the brief's `scope.amendments`. No test runs the step prose, so these
checks pin it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "src" / "skf-brief-skill"
REFERENCES = SKILL_DIR / "references"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The text under `heading`, up to the next heading of the same or a higher level."""
    start = text.index(f"\n{heading}\n")
    level = len(heading) - len(heading.lstrip("#"))
    end = re.compile(rf"^#{{1,{level}}} ", re.M).search(text, start + len(heading) + 2)
    return text[start:end.start() if end else len(text)]


def _references_text() -> str:
    return "\n".join(_read(path) for path in sorted(REFERENCES.glob("*.md")))


def test_revise_scope_on_a_ratify_run_analyzes_every_source_brief():
    text = _read(REFERENCES / "confirm-brief.md")
    assert re.search(r"^analyzeStepFile: 'analyze-target\.md'$", text, re.M)
    [handler] = [line for line in text.splitlines() if line.startswith("- IF R:")]
    route, _, otherwise = handler.partition("Otherwise")
    assert "`ratify_mode` is true" in route and "`ratify_analyzed` is not set" in route
    assert "{analyzeStepFile}" in route and "{reviseStepFile}" in otherwise
    # A brief without source_type is a source brief, so the route tests the negative.
    assert "`source_type` is not `docs-only`" in route


def test_ratify_hydration_fills_the_source_type_default():
    """analyze-source writes briefs without source_type; the ratify hydration gives them the schema default."""
    lines = [line for line in _references_text().splitlines() if "`source_type` ← `brief.source_type`" in line]
    assert any("`source` when absent" in line for line in lines), lines


def test_the_ratify_analysis_is_recorded_and_keeps_the_hydrated_fields():
    rules = _section(_read(REFERENCES / "analyze-target.md"), "## Rules")
    [rule] = [line for line in rules.splitlines() if "`ratify_mode: true`" in line]
    assert "`ratify_analyzed: true`" in rule
    assert "never replaces the hydrated `name`, `version` or `language`" in rule


def test_activation_resolves_document_output_language():
    activation = _section(_read(SKILL_DIR / "SKILL.md"), "## On Activation")
    assert "`document_output_language`" in activation
    assert "`{document_output_language}`" in _references_text()


def test_activation_reads_headless_mode_from_the_sidecar_preferences():
    activation = _section(_read(SKILL_DIR / "SKILL.md"), "## On Activation")
    [line] = [line for line in activation.splitlines() if "`headless_mode: true`" in line]
    assert "`{sidecar_path}/preferences.yaml`" in line
    assert line.count("preferences.yaml") == line.count("{sidecar_path}/preferences.yaml"), line


def test_ratify_hydration_keeps_the_component_library_fields():
    """#605: skf-create-skill writes a confirmed registry path and demo globs
    back to the brief, so a ratify must hydrate them, with ui_variants, and
    step 5 must keep them: its ratify write starts from the brief file.
    #600: the ratify route is one file, gather-intent-ratify.md, which the
    interactive §3.1a branch and the headless `from_brief` route both load,
    so the mapping list is written once."""
    ratify = _read(REFERENCES / "gather-intent-ratify.md")
    [line] = [line for line in ratify.splitlines()
              if "`scope.registry_path` / `scope.ui_variants` / `scope.demo_patterns` ← `brief.scope.*`" in line]
    assert "preserve all three verbatim" in line
    # one mapping list: no other reference restates it, and both routes load the file that holds it
    holders = [path.name for path in sorted(REFERENCES.glob("*.md")) if "`name` ← `brief.name`" in _read(path)]
    assert holders == ["gather-intent-ratify.md"], holders
    for route in ("gather-intent.md", "headless-args.md"):
        assert re.search(r"^ratifyFile: 'references/gather-intent-ratify\.md'$", _read(REFERENCES / route), re.M), route
    writer = (REPO / "src" / "shared" / "scripts" / "skf-write-skill-brief.py").read_text(encoding="utf-8")
    flat_keys = writer[writer.index("_FLAT_SCOPE_KEYS = ("):]
    flat_keys = flat_keys[:flat_keys.index(")")]
    for field in ("registry_path", "ui_variants", "demo_patterns"):
        assert f'"scope_{field}"' in flat_keys, field
    # A derive run's payload names the three flat keys. Step 5b gate run 3 (determinism-3): a ratify run writes
    # from the brief it ratified, which keeps them, and its patch names them, so an [R] pass that sets or drops
    # them reaches the brief.
    write = _section(_read(REFERENCES / "write-brief.md"), "### 3. Write the Brief")
    [call] = [line for line in write.splitlines() if line.startswith("uv run {writeSkillBriefHelper}")
              and "--base-brief" in line]
    assert '--base-brief "{ratify_source_path}" --patch-file "{run_dir}/ratify-patch.json"' in call
    for field in ("registry_path", "ui_variants", "demo_patterns"):
        assert f'"scope_{field}":' in write, field
        assert f'"{field}": <scope.{field}>' in write, field


def test_revise_scope_keeps_the_hydrated_component_library_fields_and_amendments():
    """W3 handoff: an [R] Revise Scope pass re-presents the registry path, demo globs and variants it found,
    and drops them only when the scope type stops being component-library; step 3 never writes
    `scope.amendments`, so a ratify run keeps the hydrated log after the pass."""
    rules = _section(_read(REFERENCES / "scope-definition.md"), "## Rules")
    [reentry] = [line for line in rules.splitlines() if line.startswith("- **Re-entry from step 4 [R] revise:**")]
    preserved = reentry[:reentry.index("are preserved")]
    for field in ("`scope.registry_path`", "`scope.ui_variants`", "`scope.demo_patterns`", "`scope.tier_a_include`"):
        assert field in preserved, field
    assert "dropped only when this pass changes `scope.type` away from `component-library`" in reentry
    templates = _read(SKILL_DIR / "assets" / "scope-templates.md")
    component = templates[templates.index("### Component Library Boundaries"):]  # the file's last section (#1135)
    assert "On a step 4 `[R]` re-entry" in component
    for field in ("`scope.registry_path`", "`scope.demo_patterns`", "`scope.ui_variants`"):
        assert component.count(field) >= 2, field  # re-presented, and recorded by its phase
    confirm = _read(REFERENCES / "confirm-brief.md")
    [after_r] = [line for line in confirm.splitlines() if line.startswith("After a `[R]` pass on a ratify run")]
    assert "except `scope.amendments`, which step 3 never writes" in after_r
    assert "`scope.amendments` included, stays hydrated" in after_r


def test_a_target_named_when_invoking_the_skill_answers_the_first_prompt():
    """#1136 (enhancement-3): a target the invoking message names is the §3.1 answer, so the prompt is skipped, and
    every file that names the interactive ratify entry says a brief path given when invoking the skill counts too."""
    collect = _section(_read(REFERENCES / "gather-intent.md"), "#### 3.1 Collect target")
    first = collect.strip().split("\n\n")[1]
    assert first.startswith("**Invoking message.** When the message that invoked this skill names a target"), first
    for kind in ("a URL", "a package", "a local path", "a `skill-brief.yaml` or its folder"):
        assert kind in first, kind
    assert "that message is the §3.1 answer: skip the prompt below" in first and "pre-fill included" in first
    # A branch that re-displays the prompt shows it, so a fresh start or a failed target never re-reads the message.
    assert "It answers the first prompt only: when a branch below re-displays the prompt, show it." in first
    for path in (SKILL_DIR / "SKILL.md", REFERENCES / "invocation-contract.md", REFERENCES / "confirm-brief.md"):
        text = _read(path)
        uses = [m.start() for m in re.finditer(r"at the first (?:interactive )?prompt", text)]
        assert uses, path.name
        for at in uses:
            assert text[:at].endswith("when invoking the skill or "), (path.name, text[max(0, at - 60):at + 30])


def test_a_finished_brief_for_the_target_is_offered_for_revision():
    """#1137 (enhancement-4): after the draft offer, step 1 lists the finished briefs for the target with the briefs
    helper and offers `[U] Revise` through the ratify route, or `[N] New brief`. The ratify file skips its menu for
    that pick and goes on with a new brief when the pick is invalid, and every file that lists the ways into the
    ratify route names the pick."""
    gather = _read(REFERENCES / "gather-intent.md")
    check = gather[gather.index("**Draft-resume check.**"):gather.index("### 3b. Gather Target Version")]
    assert check.index("**A draft.**") < check.index("**A finished brief.**")
    assert "On `null`, or on `[N]`, look for a finished brief." in check
    finished = check[check.index("**A finished brief.**"):]
    assert "uv run {briefDraftsHelper} briefs --forge-data \"{forge_data_folder}\" <<'SKF_TARGET'" in finished
    for needle in ("  [U] Revise `{name}`: review it at step 4 and write it back\n",
                   "  [N] New brief: keep gathering\n", "list them as `[U1]`, `[U2]` and so on",
                   "end with `[N] New brief`", "On a `[U]` pick, load `{ratifyFile}` with that brief's `path`",
                   "its §2 menu is skipped", "its §3 hands the run to step 4 as a ratify run",
                   "On `[N]`, continue at §3b."):
        assert needle in finished, needle
    for gone in ("grep -lF", "most-recently-modified"):
        assert gone not in gather, gone
    ratify = _read(REFERENCES / "gather-intent-ratify.md")
    assert "or when the user picks `[U] Revise` at the draft-resume check" in ratify
    [invalid] = [line for line in ratify.splitlines() if line.startswith("- **`valid: false`**, interactive:")]
    assert ('After a `[U] Revise` pick, end the line with "Continuing with a new brief." in place of its last '
            'sentence, and continue at step 1 §3b, as `[N]` does.') in invalid
    [gate] = [line for line in ratify.splitlines() if line.startswith("**GATE [default: R]**")]
    assert "A `[U] Revise` pick at step 1's draft-resume check skips the menu too" in gate and "at §3." in gate
    for path in (SKILL_DIR / "SKILL.md", REFERENCES / "invocation-contract.md", REFERENCES / "confirm-brief.md",
                 REFERENCES / "write-brief.md"):
        assert "step 1's `[U] Revise`" in _read(path), path.name


def test_a_derive_run_that_overwrites_a_brief_keeps_its_amendments():
    """#1137 (enhancement-4): before its overwrite gates, step 5 reads an existing brief's `scope.amendments` with the
    schema validator on a derive run, says in the question how many the new brief keeps, and passes them to the
    writer as `scope_amendments`, which a headless `force` overwrite does too. A ratify run writes from its own base
    brief, which keeps its log."""
    write = _read(REFERENCES / "write-brief.md")
    assert re.search(r"^validateBriefSchemaProbeOrder:$", write, re.M)
    overwrite = write[write.index("### 2b. Existing Brief"):write.index("### 3. Write the Brief")]
    derive = overwrite[overwrite.index("**Derive run** (any run but a ratify run), when the file exists:"):]
    assert derive.index("**Derive run**") < derive.index("**Interactive (`{headless_mode}` is false)")
    assert 'uv run {validateBriefSchemaHelper} "{resolved-target-path}" > "{run_dir}/existing-brief.json"' in derive
    assert ("Bind `existing_amendments` to the `brief.scope.amendments` it writes when that is a non-empty "
            "list") in derive
    question = derive[derive.index('"**An existing brief was found at `{path}`.**'):]
    count = "It holds {count} scope amendments (create-skill's log of scope changes); the new brief keeps them.\n"
    assert question.index("{If existing_amendments is set:}\n" + count) < question.index(
        "Overwrite it with the brief you just approved? [Y/N]")
    assert "- **[Y]** Overwrite: proceed to §3.\n" in derive
    [cancel] = [line for line in derive.splitlines() if line.startswith("- **[N]** Cancel")]
    assert "HALT with exit code 5" in cancel  # a new brief over a finished one still stops on [N]
    section = _section(write, "### 3. Write the Brief")
    payload = section[section.index("```json\n"):section.index("```\n", section.index("```json\n") + 8)]
    assert '"scope_amendments":     null | [{"...": "each entry of the existing_amendments §2b bound, verbatim"}],' \
        in payload
