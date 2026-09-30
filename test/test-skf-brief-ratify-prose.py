#!/usr/bin/env python3
"""brief-skill's ratify Revise Scope and activation prose (issue #603).

A ratified brief skips steps 2 and 3, so step 4's `[R] Revise Scope` must
run the target analysis before scope definition for every source brief,
and analyze-source writes its briefs without `source_type` (a source brief
by the schema default). SKILL.md must resolve `document_output_language`,
the language step 1 writes the description in, and read `headless_mode`
from the sidecar's preferences.yaml. No test runs the step prose, so these
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
    """analyze-source writes briefs without source_type; the ratify hydration gives them the schema default.

    step-auto-validate's reject path hydrates the same way from a brief the
    writer wrote, which always carries source_type, so one list is enough.
    """
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
