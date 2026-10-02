"""skf-create-skill's run contract: halts, decisions, the terminal sequence and run state on disk.

- Every HARD HALT in steps 1 to 7 emits SKF_CREATE_SKILL_RESULT_JSON through
  the shared emitter, inline where it fires, with an exit code and a
  halt_reason that skf-create-skill-result-envelope.v1.json maps (#593).
- Each decision the run takes without asking lands in the run folder's sink
  through the emitter's `record`, the one trail the evidence report, the
  envelope and the result contract read (#593).
- Step 8 ends every brief, each brief of a --batch run included, with its
  result contract and on_complete call, and the health check runs once, after
  the last brief; no line tells the run to stop before that (#585).
- The extraction inventory is written to disk at the end of extraction and
  every later step reads it there; step 7 promotes the staging folder byte
  for byte (#587).
- The ecosystem-check stage is gone (#599), and a docs-only brief with
  nothing fetched halts before compile (docs-unreachable).
- Under --batch a HARD HALT ends only its brief, and batch-mode.md's halts
  before the first brief carry their own phase (#585, #594).
- validate §4 splits the body by one rule set (#600), and customize.toml
  names its override files by {project-root} and says how to drop the
  persistent_facts default (#596).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CS = REPO / "src" / "skf-create-skill"
REFS = CS / "references"
SKILL = CS / "SKILL.md"
SCHEMA_PATH = REPO / "src" / "shared" / "scripts" / "schemas" / "skf-create-skill-result-envelope.v1.json"
EMITTER = REPO / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
STEP_FILES = sorted(p for p in REFS.rglob("*.md"))
EMIT_HALT = ('`uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" '
             '--target stderr < "{run_dir}/halt.json"`')
EMIT_HALT_RESULT = ('`uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" '
                    '--result-dir "{forge_version}" --target stderr < "{run_dir}/halt.json"`')
HALT_RE = re.compile(r"\*\*HARD HALT\*\* \(exit code (\d), `([^`]+)`, phase `([a-z-]+)`")
PHASES = {"load-brief", "extract", "component-extraction", "fetch-docs", "compile", "doc-sources", "auto-shard",
          "validate", "generate-artifacts", "batch-mode"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _body(path: Path) -> str:
    text = _read(path)
    if text.startswith("---\n"):
        return text[text.index("\n---\n", 4) + 5:]
    return text


def _section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))] if end else text[begin:]


def _schema() -> dict:
    return json.loads(_read(SCHEMA_PATH))


def _exit_codes() -> dict:
    return _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"]


def _halt_lines() -> list[tuple[Path, str]]:
    return [(path, line) for path in STEP_FILES for line in _body(path).splitlines() if "**HARD HALT**" in line]


# --------------------------------------------------------------------------
# HARD HALTs emit the envelope where they fire (#593)
# --------------------------------------------------------------------------


def test_skill_md_resolves_the_emitter_at_activation():
    text = _read(SKILL)
    activation = _section(text, "## On Activation", None)
    assert ("Resolve `{emitEnvelopeHelper}` ← the first existing path of "
            "`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and "
            "`{project-root}/src/shared/scripts/skf-emit-result-envelope.py`") in activation
    assert activation.index("{emitEnvelopeHelper}") < activation.index("references/load-brief.md")


def test_the_envelope_rule_sits_beside_the_tree_rule():
    rules = _section(_read(SKILL), "## Workflow Rules", "## Stages").splitlines()
    tree = next(i for i, line in enumerate(rules) if "bound `{source_tree}`" in line)
    rule = rules[tree + 1]
    assert rule.startswith("- Every HARD HALT in steps 1 to 7 emits the result envelope before it stops, in every mode.")
    for token in ('"summary": {"halt_reason": "<halt_reason>", "evidence_report": null}', EMIT_HALT,
                  'adding `--result-dir "{forge_version}"` once step 7 has created `{forge_version}`',
                  "skf-create-skill-result-envelope.v1.json"):
        assert token in rule, token


def test_every_hard_halt_names_a_mapped_code_and_emits():
    codes = _exit_codes()
    lines = _halt_lines()
    assert len(lines) >= 25, len(lines)
    for path, line in lines:
        where = f"{path.relative_to(REPO).as_posix()}: {line[:90]}"
        match = HALT_RE.search(line)
        assert match, where
        code, reason, phase = int(match.group(1)), match.group(2), match.group(3)
        assert phase in PHASES, where
        if reason.startswith("{"):
            # the brief validator's halt_reason, or an ownership refusal's: each case is mapped
            assert reason == "{halt_reason}", where
        else:
            assert codes.get(reason) == code, where
        assert ("emit-halt --workflow skf-create-skill" in line) or ("emit with nothing to stage in" in line), where


def test_no_halt_is_left_without_its_envelope():
    """The old forms (a bare `Halt with:`, a `HALT if no candidate exists`) printed only a message."""
    for path in STEP_FILES:
        body = _body(path)
        for stale in ("Halt with:", "HALT if no candidate exists", "halt with:", "per `references/report.md` "
                      "\"Result Contract on HARD HALT\"", "emit the stderr envelope per"):
            assert stale not in body, (path.name, stale)


def test_every_schema_reason_has_a_halt_site():
    used = {m.group(2) for _, line in _halt_lines() for m in [HALT_RE.search(line)] if m}
    load_brief = _read(REFS / "load-brief.md")
    generate = _read(REFS / "generate-artifacts.md")
    for reason in _exit_codes():
        assert (reason in used or (reason in ("brief-malformed", "brief-invalid") and f"`{reason}`" in load_brief)
                or (reason in ("not-skf-output", "flat-layout") and f'halt_reason: "{reason}"' in generate)), reason


def test_the_promotion_and_post_promotion_halts_write_their_result_file():
    generate = _body(REFS / "generate-artifacts.md")
    promotion = _section(generate, "### 3. Promote the Staged Skill", None)
    for reason in ("staging-unreadable", "write-failed", "active-link-blocked", "references-missing"):
        line = next(ln for ln in promotion.splitlines() if f"`{reason}`" in ln and "**HARD HALT**" in ln)
        assert EMIT_HALT_RESULT in line, reason
    refusal = next(p for p in generate.split("\n\n") if p.startswith("Each refusal is a **HARD HALT**"))
    assert EMIT_HALT in refusal and "leaves out `--result-dir`" in refusal
    # extraction-rules.yaml is written before the promotion creates {forge_version}: no result file yet
    rules = _section(generate, "### 2. Generate extraction-rules.yaml", "### 3.")
    for line in (ln for ln in rules.splitlines() if "**HARD HALT**" in ln):
        assert EMIT_HALT in line and "--result-dir" not in line, line[:80]


def test_the_halt_payload_the_rule_stages_is_schema_valid(tmp_path):
    run_dir = tmp_path / "skf-create-skill-abc12345"
    run_dir.mkdir()
    decision = {"step": "extract", "gate": "authoritative-file:AGENTS.md", "decision": "deferred-headless",
                "rationale": "headless mode: no person to decide", "timestamp": "2026-10-01T00:00:00Z"}
    rec = subprocess.run([sys.executable, str(EMITTER), "record", "--workflow", "skf-create-skill", "--run-dir",
                          str(run_dir), "--decision"], input=json.dumps(decision), capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    assert rec.returncode == 0, rec.stderr
    halt = {"phase": "fetch-docs", "halt_reason": "docs-unreachable", "reason": "No documentation could be fetched.",
            "summary": {"halt_reason": "docs-unreachable", "evidence_report": None}}
    proc = subprocess.run([sys.executable, str(EMITTER), "emit-halt", "--workflow", "skf-create-skill", "--run-dir",
                           str(run_dir), "--target", "stdout"], input=json.dumps(halt), capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    line = proc.stdout.strip()
    assert line.startswith("SKF_CREATE_SKILL_RESULT_JSON: ")
    envelope = json.loads(line.split(": ", 1)[1])
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("failed", 3, "docs-unreachable")
    assert envelope["summary"] == {"halt_reason": "docs-unreachable", "evidence_report": None}
    assert envelope["headless_decisions"] == [decision]
    assert envelope["run_id"] == "abc12345" and envelope["result_path"] is None


# --------------------------------------------------------------------------
# One decision trail on disk (#593)
# --------------------------------------------------------------------------


def test_decisions_go_to_the_run_sink_only():
    for path in [SKILL, *STEP_FILES]:
        text = _read(path)
        for stale in ("auto-decisions.jsonl", "headless_decisions[]` buffer", "to `headless_decisions[]`"):
            assert stale not in text, (path.name, stale)
    rule = next(line for line in _read(SKILL).splitlines()
                if line.startswith("- Every decision the run takes without asking"))
    assert ('`uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision '
            '< "{run_dir}/decision.json"`') in rule
    assert "`{run_dir}/headless-decisions.jsonl`, is the brief's one decision trail" in rule


def _decision_examples() -> list[tuple[str, str]]:
    found = []
    for path in [SKILL, *STEP_FILES]:
        for match in re.finditer(r'`(\{"step": "[^`]+\})`', _read(path)):
            found.append((path.name, match.group(1)))
    return found


def test_every_documented_decision_fits_the_schema():
    item = _schema()["properties"]["headless_decisions"]["items"]
    examples = [(name, text) for name, text in _decision_examples() if '"<step>"' not in text]
    gates = {json.loads(re.sub(r"\{[A-Za-z_]+\}", "x", text))["gate"] for _, text in examples}
    assert {"tier-override", "tag-choice", "review-gate", "zero-exports", "authoritative-file:x", "demo-exclusion",
            "registry-confirm", "provide-or-skip-registry"} <= gates
    for name, text in examples:
        decision = json.loads(re.sub(r"\{[A-Za-z_]+\}", "x", text))
        assert set(item["required"]) <= set(decision), (name, text)
        assert set(decision) <= set(item["properties"]), (name, text)


def test_every_decision_site_spells_out_its_record_command():
    """A step that records a decision names the command itself: SKILL.md may have left context by then."""
    record = ('as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill '
              '--run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`')
    for path in STEP_FILES:
        for line in _body(path).splitlines():
            if re.search(r'`\{"step": "', line):
                assert record in line or "stage the object as `{run_dir}/decision.json`" in _body(path), \
                    (path.name, line[:90])
    load_brief = _read(REFS / "load-brief.md")
    assert ('stage the object as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow '
            'skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`') in load_brief


def test_every_headless_gate_is_recorded_and_declared():
    """Gate 2's headless default is recorded like every other gate, and SKILL.md lists every stop."""
    seven = _section(_read(REFS / "extract.md"), "### 7. Gate 2", None)
    assert '"gate": "review-gate", "decision": "continue"' in seven and "record --workflow skf-create-skill" in seven
    gate_text = _schema()["properties"]["headless_decisions"]["items"]["properties"]["gate"]["description"]
    assert "review-gate" in gate_text
    skill = _read(SKILL)
    gates = next(line for line in skill.splitlines() if line.startswith("| **Gates** |"))
    for gate in ("Tag Choice Gate", "Authoritative-File Gate [P]/[S]/[U]", "Review Gate [C]",
                 "step 3c: Zero-Export Gate [C]", "Demo-Exclusion Gate [Y]"):
        assert gate in gates, gate
    # #594: step 1 stops to ask which brief when none is named and several exist; headless halts
    assert ("step 1: Brief Selection (no brief named and several in `{forge_data_folder}`; headless: HARD HALT "
            "`brief-missing`, exit 2; one brief: picked and recorded as gate `brief-selection`)") in gates
    assert "| 1 | Load Brief | references/load-brief.md | Conditional |" in skill
    several = next(line for line in _read(REFS / "load-brief.md").splitlines() if line.startswith("- **Several briefs:**"))
    assert "**GATE [default: HALT]**: headless, ask nothing: **HARD HALT** (exit code 2, `brief-missing`" in several
    overview = _section(skill, "## Overview", "## Conventions")
    assert "it stops for the user in step 1 when no brief is named and several exist" in overview
    assert "for each authoritative AI documentation file the brief's scope leaves out (step 3 §2a)" in overview
    assert "at step 3c when a source brief extracted no export" in overview
    footnote = next(line for line in skill.splitlines() if line.startswith("*Sub-steps under"))
    assert "a branch inside step 3" in footnote and "alternative main step" not in footnote
    for name in ("auto_decision_count",):
        text = _schema()["properties"]["summary"]["properties"][name]["description"]
        assert "tier override in any mode" in text and "interactive run" not in text
    assert "Empty for an interactive run" not in json.dumps(_schema())


def test_compile_renders_the_auto_decisions_from_the_sink():
    seven = _section(_read(REFS / "compile.md"), "### 7. Build evidence-report.md Content", "### 8.")
    assert "from `{run_dir}/headless-decisions.jsonl`, the run's one decision trail: one row per line" in seven
    assert "step 3 tag-choice" in seven and "step 3 review-gate" in seven and "step 2 ecosystem gate" not in seven
    assert "| Step | Gate | Decision | Rationale | Timestamp |" in seven
    validate = _section(_read(REFS / "validate.md"), "### 8. Update Evidence Report", "### 9.")
    assert "keep the `## Auto-Decisions` section step 5 §7 rendered from the run sink as it is" in validate
    assert "union" not in validate


# --------------------------------------------------------------------------
# The terminal sequence: every brief's result contract and hook, one health check (#585)
# --------------------------------------------------------------------------


def test_report_has_no_line_that_ends_the_run_early():
    for path in (REFS / "report.md", REFS / "health-check.md"):
        text = _read(path)
        for stale in ("End workflow", "do not modify any files", "do not stop here", "### Result Contract on HARD HALT"):
            assert stale not in text, (path.name, stale)


def test_report_orders_contract_then_batch_then_health_check():
    text = _read(REFS / "report.md")
    headings = re.findall(r"^### (\d)\. (.+)$", text, re.M)
    assert headings[4:] == [("5", "Result Contract and Post-Completion Hook"), ("6", "Chain to the Next Step")]
    five = _section(text, "### 5. Result Contract", "### 6.")
    assert "each brief of a `--batch` run included" in five
    assert ('uv run {emitEnvelopeHelper} emit --workflow skf-create-skill --run-dir "{run_dir}" '
            '--result-dir "{forge_version}" < "{run_dir}/result-context.json"') in five
    assert "{onCompleteCommand} --result-path={forge_version}/create-skill-result-latest.json" in five
    assert five.index("emit --workflow") < five.index("{onCompleteCommand} --result-path")
    assert 'rm -rf "{run_dir}"' in five
    # under --batch the batch helper reads the staged payload, then removes the folder itself
    assert "under `--batch`, batch-mode.md §3 reads the staged `result-context.json` there" in five
    six = _section(text, "### 6.", None)
    assert "**Under `--batch`:** go to `references/batch-mode.md` §3, which records this brief" in six
    assert "The health check runs once per run" in six
    batch = _read(REFS / "batch-mode.md")
    assert "the health check runs once per batch, here" in batch
    # the health check step names the same loop: batch-mode.md §4, never a loop back to load-brief
    health = _section(_read(REFS / "health-check.md"), "## Rules", "## MANDATORY SEQUENCE")
    assert "Under `--batch`, `references/batch-mode.md` §4 loads this step once, after the batch summary" in health
    assert "loops back to load-brief" not in health
    toml = _read(CS / "customize.toml")
    assert "Under --batch it runs once per brief" in toml and "workflow_warnings" not in toml


def test_on_complete_is_a_shell_command_run_only_after_a_result_contract():
    toml = _read(CS / "customize.toml")
    assert "The value is a shell\n# command, run from {project-root}, not an agent instruction" in toml
    assert "TS test-skill" not in toml and "EX export" not in toml
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    assert "downstream-skill chain" not in five
    assert "the emitter wrote this brief's result contract (its `emit` exited 0), run it as a shell command" in five
    assert "on_complete skipped for `{name}`: no result contract was written" in five
    rules = _section(_read(REFS / "report.md"), "## Rules", "## MANDATORY SEQUENCE")
    assert "except in §5's fallback when `{emitEnvelopeHelper}` resolved no path" in rules
    load_rules = _section(_read(REFS / "load-brief.md"), "## Rules", "## MANDATORY SEQUENCE")
    # the batch's state is the batch helper's, in its run folder: no sidecar checkpoint is written
    assert "batch-state.yaml" not in load_rules
    assert "Write nothing but the brief's run folder (§0) and the decisions recorded in it" in load_rules


def test_the_documented_result_payload_is_schema_valid(tmp_path):
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    payload_text = re.search(r"<<'SKF_JSON'\n(.+?)\nSKF_JSON", five, re.S).group(1)
    filled = re.sub(r"\{(run_status)\}", "success", payload_text)
    filled = re.sub(r"\{tier\}", "Forge", filled)
    filled = re.sub(r"\{[a-z_]+\}", "x", filled)
    payload = json.loads(filled)
    run_dir = tmp_path / "skf-create-skill-run00001"
    run_dir.mkdir()
    forge = tmp_path / "forge" / "demo" / "1.0.0"
    forge.mkdir(parents=True)
    proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-create-skill", "--run-dir",
                           str(run_dir), "--result-dir", str(forge)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout.strip().split(": ", 1)[1])
    assert (envelope["status"], envelope["exit_code"], envelope["halt_reason"]) == ("success", 0, None)
    latest = json.loads((forge / "create-skill-result-latest.json").read_text(encoding="utf-8"))
    assert latest["skill"] == "skf-create-skill" and latest["run_id"] == "run00001"
    assert latest["headless_decisions"] == [] and "timestamp" in latest
    assert envelope["result_path"] == next(p for p in forge.iterdir() if p.name != "create-skill-result-latest.json").as_posix()


# --------------------------------------------------------------------------
# Run state on disk: the extraction inventory, the promotion (#587)
# --------------------------------------------------------------------------


def test_the_inventory_is_written_at_the_end_of_extraction():
    extract = _read(REFS / "extract.md")
    assert "extraction stays in context" not in extract
    assert ("Bind `{extraction_inventory}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json` "
            "and `{detected_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.detected.json`, and run "
            '`rm -f "{extraction_inventory}" "{detected_json}" '
            '"{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json"`') in extract
    five = _section(extract, "### 5. Build Extraction Inventory", "### 6.")
    helper = 'uv run {extractionInventoryHelper} '
    inventory = '--inventory "{extraction_inventory}"'
    for call in (f'{helper}init {inventory} --skill "{{name}}" --mode {{source|component-library}} --tier "{{tier}}" '
                 '[--extraction "{extraction_json}"] [--detected "{detected_json}"]',
                 f"{helper}patch {inventory} <<'SKF_INVENTORY'",
                 f"{helper}add {inventory} --field exports <<'SKF_INVENTORY'",
                 f"{helper}add {inventory} --field warnings <<'SKF_INVENTORY'",
                 f"{helper}set {inventory} <<'SKF_INVENTORY'",
                 f"{helper}summary {inventory}"):
        assert call in five, call
    # the runner's records reach the inventory through init, never typed again
    assert "{atomicWriteHelper}" not in extract and "atomicWriteProbeOrder" not in extract
    for runner_field in ('"citation": ""', '"ast_recipe": null', '"extraction_rules": {', '"aggregates": {}'):
        assert runner_field not in five, runner_field
    assert "From the runner's JSON, `init` writes each export as the runner recorded it" in five
    three = _section(extract, "### 3. Check for Docs-Only Mode", "### 4.")
    assert (f'{helper}init {inventory} --skill "{{name}}" --mode docs-only --tier "{{tier}}"') in three
    four_c = _section(extract, "### 4c.", "### 5.")
    assert '[--max-lines 500] > "{detected_json}"' in four_c


def test_later_steps_read_and_extend_the_inventory():
    enrich = _read(REFS / "enrich.md")
    assert ('uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field t2_annotations'
            in enrich)
    docs = _read(REFS / "sub" / "fetch-docs.md")
    assert 'uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field t3_items' in docs
    assert "{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json" in docs
    compile_one = _section(_read(REFS / "compile.md"), "### 1. Load Data Files", "### 1a.")
    assert "Then load `{extraction_inventory}` (`{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`)" in compile_one
    assert "{skill-name}.language-guide.json" in compile_one
    for field in ("`intent_mapping`", "an export marked `internal: true` stays out of `metadata.json`'s `exports[]`"):
        assert field in compile_one, field
    assert ('run `uv run {extractionInventoryHelper} summary --inventory "{extraction_inventory}"`: bind '
            "`{inventory_counts}` ← its `counts`") in compile_one
    seven_a = _section(_read(REFS / "validate.md"), "### 7a.", "### 8.")
    assert "the export's `ast_recipe` names in the extraction inventory step 3 §5 wrote" in seven_a
    rules = _section(_read(REFS / "generate-artifacts.md"), "### 2. Generate extraction-rules.yaml", "### 3.")
    assert "its `extraction_rules`" in rules and "{extraction_inventory}" in rules
    assert ('uv run {extractionInventoryHelper} rules --inventory "{extraction_inventory}" --language '
            '"{brief.language}" --target "<staging-skill-dir>/extraction-rules.yaml"') in rules
    assert "{extraction-rules YAML}" not in rules


def test_counts_come_from_the_inventory_helper():
    """Enrich's summary and compile's t2_future_count are the helper's counts, never counted by hand."""
    enrich = _read(REFS / "enrich.md")
    assert "come from the call's output, never counted by hand" in enrich
    for count in ("counts.functions_enriched", "counts.t2_annotations", "counts.t2_past", "counts.t2_future"):
        assert "{" + count + "}" in enrich, count
    seven = _section(_read(REFS / "compile.md"), "### 7. Build evidence-report.md Content", "### 8.")
    assert "Take `t2_future_count` from `{inventory_counts}.t2_future`" in seven
    assert "Compute `t2_future_count`" not in seven


def test_a_free_text_intent_mapping_reaches_the_evidence_report():
    seven = _section(_read(REFS / "compile.md"), "### 7. Build evidence-report.md Content", "### 8.")
    assert "When the inventory's `intent_mapping` is not empty" in seven
    assert ('`{kind} intent "{intent}": kept {each kept source file, or none}; left out {each left_out source file, '
            "or none}`") in seven


def test_the_language_guide_is_an_index_of_kept_pages():
    """Step 3c keeps the registry pages and writes an index; compile reads the prose from the pages."""
    docs = _read(REFS / "sub" / "fetch-docs.md")
    four_a = _section(docs, "### 4a.", "### 5.")
    assert '{"docs_folder": "{docs_staging}", "language_guide": [{"url": "...", "label": "...", "pages": ["page-1.md"]}]}' \
        in four_a
    assert '"prose": "..."' not in four_a
    five_c = _section(docs, "### 5c.", "### 6.")
    assert "and the brief is not a whole-language reference** (`whole_language_reference` false)" in five_c
    compile_one = _section(_read(REFS / "compile.md"), "### 1. Load Data Files", "### 1a.")
    assert "build `language_guide[]` from it" in compile_one
    assert "When the file is missing, or a page it lists is gone" in compile_one
    check = _section(docs, "**Zero-content check.**", "### 5b.")
    assert "When no page of this run was saved (every fetch failed, or no fetch tool), skip §5b and §5c" in check


def test_step_7_promotes_instead_of_rewriting():
    generate = _read(REFS / "generate-artifacts.md")
    for stale in ("from the compiled content", "Write these 4 files", "Write these 3 files", "### 2. Write Deliverables"):
        assert stale not in generate, stale
    for path in (REFS / "compile.md", REFS / "validate.md", REFS / "generate-artifacts.md"):
        text = _read(path)
        assert "in-context copies" not in text and "in-context copy step 7" not in text, path.name
    compile_1a = _section(_read(REFS / "compile.md"), "### 1a. Create Staging Directory", "### 1b.")
    assert ('rm -rf "{project-root}/_bmad-output/.skf-stage/{skill-name}" && mkdir -p '
            '"{project-root}/_bmad-output/.skf-stage/{skill-name}/references"') in compile_1a
    assert "step 7 promotes this folder byte for byte" in compile_1a


# --------------------------------------------------------------------------
# The ecosystem-check stage is gone (#599)
# --------------------------------------------------------------------------


def test_no_ecosystem_check_stage():
    assert not (REFS / "ecosystem-check.md").exists()
    load_brief = _read(REFS / "load-brief.md")
    assert "nextStepFile: 'sub/ccc-discover.md'" in load_brief
    assert 'Proceeding to extraction..."' in load_brief
    for path in [SKILL, *STEP_FILES]:
        assert "ecosystem" not in _read(path).lower(), path.name
    gates = next(line for line in _read(SKILL).splitlines() if line.startswith("| **Gates** |"))
    assert "step 2:" not in gates


# --------------------------------------------------------------------------
# A docs-only brief with nothing fetched halts before compile
# --------------------------------------------------------------------------


def test_zero_content_check_halts_a_docs_only_brief():
    docs = _read(REFS / "sub" / "fetch-docs.md")
    check = _section(docs, "**Zero-content check.**", "### 5b.")
    assert 'uv run {extractionInventoryHelper} summary --inventory "{extraction_inventory}"' in check
    halt = next(line for line in check.splitlines() if "`docs-unreachable`" in line)
    assert "no URL or subpage fetched in this run, and `counts.items` is 0" in halt
    assert "Stage and promote nothing" in halt and EMIT_HALT in halt
    assert "Apply that check here" in check
    all_failed = next(line for line in docs.splitlines() if line.startswith("**If ALL URLs fail"))
    assert "continue at §5's **Zero-content check**" in all_failed and "section 7" not in all_failed
    assert "with one exception: a `docs-only` brief left with nothing to compile" in docs
    assert _exit_codes()["docs-unreachable"] == 3


# --------------------------------------------------------------------------
# Scripts and assets: the detector takes detect or none (determinism-2)
# --------------------------------------------------------------------------


def test_free_text_intent_never_reaches_the_detector():
    four_c = _section(_read(REFS / "extract.md"), "### 4c.", "### 5.")
    assert "--scripts-intent {detect|none}" in four_c and "--assets-intent {detect|none}" in four_c
    assert "<scripts_intent>" not in four_c
    assert "**If it exits non-zero**" in four_c
    assert '`{"intent_mapping": {"scripts": {"intent": "<the text>", "kept": [source_file, ...]}}}`' in four_c
    assert "records the others as the mapping's `left_out`" in four_c
    gate = _section(_read(REFS / "extract.md"), "### 6.", "### 7.")
    assert "each kept entry as `{name}` (`{source_file}`): {purpose}" in gate
    assert "the files its `intent_mapping` left out" in gate


@pytest.mark.parametrize("flag", ["--scripts-intent", "--assets-intent"])
def test_the_detector_refuses_free_text(tmp_path, flag):
    detector = REPO / "src" / "shared" / "scripts" / "skf-detect-scripts-assets.py"
    proc = subprocess.run([sys.executable, str(detector), "detect", str(tmp_path), flag, "the CLI tools in bin/"],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 1 and "must be detect|none" in proc.stderr


# --------------------------------------------------------------------------
# validate §4: one rule set for the body split (#600)
# --------------------------------------------------------------------------


def test_validate_splits_the_body_by_one_rule_set():
    """The splitter runs inside the description guard; a pulled Tier 1 section
    halts (the context-snippet anchors are Tier 1 headings, so the same halt
    covers them), and so does a cross-reference that does not resolve, as in
    step 5b; an over-budget Tier 1 is trimmed and split again; and the
    split-everything `split-body --write` never runs. No hand-check list, no
    second guard and no copy of the splitter's statistics remain."""
    four = _section(_read(REFS / "validate.md"), "### 4. Split Oversized Body", "### 5. ")
    capture = four.index("uv run {descriptionGuardHelper} capture")
    split = four.index("uv run {shardBodyHelper} <staging-skill-dir>/SKILL.md --budget 400")
    restore = four.index("uv run {descriptionGuardHelper} verify-restore")
    assert capture < split < restore
    assert four.count("**HARD HALT**") == 2
    assert "**HARD HALT** (exit code 5, `tier1-not-preserved`, phase `validate`" in four
    assert "- **`xref_ok` is false:** **HARD HALT** (exit code 5, `shard-xref-broken`, phase `validate`" in four
    nine = _section(_read(REFS / "validate.md"), "### 9. Auto-Proceed", None)
    assert "the §4 Tier-1 preservation and cross-reference checks" in nine
    # the evidence report names the split that ran, never the split-body it no longer runs
    validate = _read(REFS / "validate.md")
    assert "- Body: {pass/fail} {body split applied if applicable}" in validate
    assert "(`skill-check --fix` in §2, `skf-shard-body.py` in §4)" in validate
    assert "skill-check split-body" not in validate.replace("Never run `npx skill-check split-body --write`", "")
    assert "`#quick-start` and `#key-types` anchors name two of them" in four
    assert "trim `## Key API Summary` and `## Architecture at a Glance`" in four
    assert "Never run `npx skill-check split-body --write`" in four
    for stale in ("last resort", "last-resort", "Vercel", "Tier 1 preservation check:", "Anchor validation",
                  "Restoring from staging backup", "restore it immediately"):
        assert stale not in four, stale


# --------------------------------------------------------------------------
# customize.toml: the override paths and the persistent_facts default (#596)
# --------------------------------------------------------------------------


def test_customize_names_its_override_files_and_how_to_drop_the_default():
    import tomllib

    text = _read(CS / "customize.toml")
    assert "# Team overrides:     {project-root}/_bmad/custom/skf-create-skill.toml\n" in text
    assert "# Personal overrides: {project-root}/_bmad/custom/skf-create-skill.user.toml\n" in text
    assert "(under {project-root})" not in text
    default = "file:{project-root}/**/project-context.md"
    assert tomllib.loads(text)["workflow"]["persistent_facts"] == [default]
    assert f'#   persistent_facts = ["!{default}"]' in text
    activation = _section(_read(SKILL), "## On Activation", None)
    assert f"except a `!` entry and the entry it names (`!{default}` drops the bundled project-context default)" \
        in activation
    assert "`{project-root}/_bmad/custom/skf-create-skill.toml` (team overrides, committed)" in activation
    assert "`_bmad/custom/skf-create-skill.toml` under `{project-root}`" not in activation
