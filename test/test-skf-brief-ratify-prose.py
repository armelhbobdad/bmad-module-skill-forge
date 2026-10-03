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
is retyped or dropped. No test runs the step prose, so these checks pin it.
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
    component = templates[templates.index("### Component Library Boundaries"):templates.index("## Scripts & Assets")]
    assert "On a step 4 `[R]` re-entry" in component
    for field in ("`scope.registry_path`", "`scope.demo_patterns`", "`scope.ui_variants`"):
        assert component.count(field) >= 2, field  # re-presented, and recorded by its phase
    confirm = _read(REFERENCES / "confirm-brief.md")
    [after_r] = [line for line in confirm.splitlines() if line.startswith("After a `[R]` pass on a ratify run")]
    assert "except `scope.amendments`, which step 3 never writes" in after_r
    assert "`scope.amendments` included, stays hydrated" in after_r
