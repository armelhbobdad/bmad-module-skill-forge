"""skf-create-skill's run contract: halts, decisions, the terminal sequence and run state on disk.

- Every HARD HALT in steps 1 to 7 emits SKF_CREATE_SKILL_RESULT_JSON through
  the shared emitter, with an exit code and a halt_reason that
  skf-create-skill-result-envelope.v1.json maps (#593); the stage file's Rules
  state the emit command once and each HALT names its code, reason, phase and
  message (#1147).
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
- Every stage that can halt after step 3 §2a states in its own Rules that
  the halt closes the private source tree and, under --batch, returns to
  batch-mode.md §3, and binds both helpers it needs for that, so a halt after
  a compaction that dropped SKILL.md still ends only its brief; step 1 and
  batch-mode.md bind the emitter too (step 5b architecture-1), and so does
  step 8, which writes every finished brief's result contract and resolves
  its on_complete hook itself (v4.0.0 quality gate run 1, architecture-1 and
  customization-2).
- Gate 2 and both zero-export gates offer [R] Refine the brief, a HARD HALT
  with halted-for-brief-refinement (step 5b enhancement-1).
- validate §4 splits the body by one rule set (#600), and customize.toml
  names its override files by {project-root} and says how to drop the
  persistent_facts default (#596).
- validate §5 captures the scan call's stdout, stderr and exit code in the
  run folder and binds the Security row from them by Quick Skill's rule,
  the first that applies: skipped, warn, then pass (#934).
- validate §2 hashes SKILL.md before the guard's capture and after its
  verify-restore, since skill-check 1.2.0's JSON lists no fix, and §8's
  Auto-Fixed line, the same in skill-sections.md, keys on that (#901).
- validate §2's and §4's guard lines stage the description snapshot in the
  run folder and read it back with `--captured-file`, never in a shell
  string (#951).
- Version Reconciliation, and update-skill's init §6c with it, reads the
  source's version through the extractor's quick mode, so a release-time
  placeholder such as 0.0.0-development keeps the brief's version (v4.0.0
  quality gate run 2, determinism-2).
- Step 3 §2a records the run's source and run folder in the extraction
  inventory right after it resolves the source, docs-only briefs included;
  compile §1 binds a lost `{run_dir}` and `{source_tree}` back from it and
  halts with staging-unreadable when the run folder is lost, and report §5
  binds a lost `{run_dir}` back, so a lost folder is an error, never zero
  decisions (#1144).
"""

from __future__ import annotations

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
CS = REPO / "src" / "skf-create-skill"
REFS = CS / "references"
SKILL = CS / "SKILL.md"
# #1148: the Invocation Contract table lives beside the stages; SKILL.md keeps a pointer line
CONTRACT = REFS / "invocation-contract.md"
VALIDATOR = REPO / "src" / "shared" / "scripts" / "skf-validate-brief-schema.py"
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
# The stages whose HARD HALTs can fire once step 3 §2a has bound the private
# source tree. load-brief.md halts before it, batch-mode.md is the loop the
# halts return to, and extract.md runs the authoritative-files protocol under
# its own Rules.
TREE_HALT_STAGES = ("extract.md", "fetch-docs.md", "compile.md", "step-doc-sources.md", "step-auto-shard.md",
                    "validate.md", "generate-artifacts.md")
TREE_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py",
              "{project-root}/src/shared/scripts/skf-source-tree.py"]
EMIT_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py",
              "{project-root}/src/shared/scripts/skf-emit-result-envelope.py"]
BATCH_RETURN = "return to `references/batch-mode.md` §3, even when the halt reads as the end of the run"


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


def _frontmatter(path: Path) -> dict:
    text = _read(path)
    return yaml.safe_load(text[4:text.index("\n---\n", 4)])


def _rules(path: Path) -> str:
    return _section(_body(path), "## Rules", "## MANDATORY SEQUENCE")


def _schema() -> dict:
    return json.loads(_read(SCHEMA_PATH))


def _exit_codes() -> dict:
    return _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"]


def _halt_lines() -> list[tuple[Path, str]]:
    return [(path, line) for path in STEP_FILES for line in _body(path).splitlines() if "**HARD HALT**" in line]


HALT_PAYLOAD = ('it stages `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", '
                '"summary": {"halt_reason": "<halt_reason>", "evidence_report": null}}`, plus `"path"` when the HALT names '
                'a file or folder, as `{run_dir}/halt.json`, runs ' + EMIT_HALT)


def _halt_rules(path: Path) -> list[str]:
    """The Rules bullets of a stage file that hold the emit command; the authoritative-files protocol, which has
    no Rules and runs under step 3's, states it in a paragraph of its Overview (#1147)."""
    if path.name == "authoritative-files-protocol.md":
        return [p for p in _section(_read(path), "## Overview", "## Procedure").split("\n\n") if EMIT_HALT in p]
    return [line for line in _rules(path).splitlines() if EMIT_HALT in line]


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


def test_every_hard_halt_names_a_mapped_code_and_its_file_states_the_emit():
    """#1147 leanness-3: a HALT names its exit code, halt_reason, phase, path and message where it fires, and the
    stage file's Rules (the protocol's Overview) state the emit command once, so a halt after a compaction that
    dropped SKILL.md still finds it; the halts with nothing to stage in keep their own command."""
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
        assert "emit-halt" not in line, where
        if "emit with nothing to stage in" in line:
            continue
        rules = _halt_rules(path)
        assert len(rules) == 1 and HALT_PAYLOAD in rules[0], where
        assert ("displays the line it prints (the halt message alone when no path resolves) and stops with the "
                "HALT's exit code") in rules[0], where


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
    # #1148: load-brief halts with the validator's own `halt_reason`, the one place the brief faults are named
    from_validator = ("**HARD HALT** (exit code 2, `{halt_reason}`, phase `load-brief`), with the helper's "
                      "`halt_reason`") in load_brief
    validator = _read(VALIDATOR)
    for reason in _exit_codes():
        assert (reason in used or (reason in ("brief-malformed", "brief-invalid") and from_validator
                                   and f'"{reason}"' in validator)
                or (reason in ("not-skf-output", "flat-layout") and f'halt_reason: "{reason}"' in generate)), reason


def test_every_halting_stage_closes_the_tree_and_returns_to_the_batch():
    """Step 5b architecture-1: a halt in steps 3 to 7 works without SKILL.md,
    which a compaction in a long --batch run can drop. Each stage's own Rules
    close the private source tree and send the halt back to batch-mode.md §3,
    and its frontmatter binds the tree helper and the emitter again, so the
    halt ends only its brief and the batch still writes its summary. Step 1,
    which halts before the tree exists, and batch-mode.md, the loop every
    halt returns to, bind the emitter the same way."""
    halting = {path.relative_to(REFS).as_posix() for path, _ in _halt_lines()}
    assert halting - {"batch-mode.md", "load-brief.md", "authoritative-files-protocol.md"} == set(TREE_HALT_STAGES)
    for name in TREE_HALT_STAGES:
        rules = [line for line in _rules(REFS / name).splitlines()
                 if line.startswith("- A HARD HALT, once step 3 §2a has bound `{source_tree}`")]
        assert len(rules) == 1, name
        for token in ('first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` '
                      "(resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints",
                      "emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not "
                      "bound", f"After its envelope, under `--batch` it ends only this brief: {BATCH_RETURN}."):
            assert token in rules[0], (name, token)
        frontmatter = _frontmatter(REFS / name)
        assert frontmatter["sourceTreeProbeOrder"] == TREE_PROBE, name
        assert frontmatter["emitEnvelopeProbeOrder"] == EMIT_PROBE, name
    # step 1 halts before the tree exists, but its halts find the emitter and, under --batch, end only the brief
    load_brief = [line for line in _rules(REFS / "load-brief.md").splitlines() if line.startswith("- A HARD HALT")]
    assert load_brief == ["- A HARD HALT emits through `{emitEnvelopeHelper}`, resolved from "
                          f"`{{emitEnvelopeProbeOrder}}` when it is not bound: {HALT_PAYLOAD}, displays the line it "
                          "prints (the halt message alone when no path resolves) and stops with the HALT's exit code. "
                          f"After its envelope, under `--batch` it ends only this brief: {BATCH_RETURN}."], load_brief
    # batch-mode.md, the loop every halt returns to, halts through the emitter too
    execution = _section(_read(REFS / "batch-mode.md"), "## Execution", "### 1.")
    assert ("`{emitEnvelopeHelper}`, which every HARD HALT here emits through, ← the first existing path in "
            "`{emitEnvelopeProbeOrder}` when it is not bound") in execution
    for name in ("load-brief.md", "batch-mode.md"):
        assert _frontmatter(REFS / name)["emitEnvelopeProbeOrder"] == EMIT_PROBE, name
    record = _section(_read(REFS / "batch-mode.md"), "### 3. Record the Brief", "### 4.")
    assert "every HARD HALT of steps 1 to 7 returns here after its envelope (each stage's Rules say so)" in record
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    assert "it emits its envelope where it fires, as its stage file's Rules say" in five
    for path in STEP_FILES:
        assert "SKILL.md Workflow Rules" not in _read(path), path.name


def test_the_report_step_binds_the_emitter_and_the_hook_itself():
    """v4.0.0 quality gate run 1, architecture-1 and customization-2: step 8
    writes every finished brief's result contract and runs its on_complete
    hook, at the end of the longest chain and once per brief under --batch.
    Like every other stage that emits, it binds the emitter in its own
    frontmatter and Rules, so a compaction that dropped SKILL.md's binding
    never sends a healthy install down §5's incomplete-install branch (no
    result contract, metadata.json set to schema-unavailable): only an install
    where neither path exists takes it. The hook resolves `{onCompleteCommand}`
    the way activation does, with the resolver's dotted key, so a lost binding
    never skips a team's hook as if it were the empty default. No line of the
    step points back at SKILL.md for either."""
    report = _read(REFS / "report.md")
    rules = _rules(REFS / "report.md")
    assert _frontmatter(REFS / "report.md")["emitEnvelopeProbeOrder"] == EMIT_PROBE
    assert ("- §5 emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not "
            "bound.") in rules.splitlines()
    assert "SKILL.md On Activation" not in report
    five = _section(_body(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    assert ("**If no path in `{emitEnvelopeProbeOrder}` exists** (an incomplete install), write no result "
            "contract") in five
    hook = _section(five, "**Post-completion hook.**", "{onCompleteCommand} --result-path=")
    assert hook.startswith("**Post-completion hook.** When `{onCompleteCommand}` is not bound, bind it to the "
                           "`workflow.on_complete` value this prints, or to the one in `{skill-root}/customize.toml` "
                           "when the resolver cannot run:\n")
    [activation_call] = [line.strip() for line in _section(_read(SKILL), "## On Activation", None).splitlines()
                         if "{resolveCustomizationHelper}" in line and line.strip().startswith("uv run ")]
    # The activation resolves persistent_facts too (#1106); the hook reads one key and takes no --facts.
    assert activation_call.endswith(" --key workflow --facts")
    [hook_call] = re.findall(r"```bash\n(uv run \{resolveCustomizationHelper\}[^\n]*)\n```", hook)
    assert hook_call == activation_call.removesuffix(" --facts") + ".on_complete"
    assert "on_complete" in tomllib.loads(_read(CS / "customize.toml"))["workflow"]
    assert ("When `{onCompleteCommand}` is non-empty and the emitter wrote this brief's result contract (its `emit` "
            "exited 0, the line's `result_path` is not null and its `warnings` hold no `result_file_write_failed` "
            "entry naming `create-skill-result-latest.json`), run it") in hook
    assert hook.index(hook_call) < hook.index("When `{onCompleteCommand}` is non-empty")
    # One wording for the incomplete install, wherever the step names it.
    assert "resolved no path" not in report and "no `{emitEnvelopeHelper}`" not in report
    assert "(no path in `{emitEnvelopeProbeOrder}` exists, `emit` failed twice, or the run folder is lost)" in five


def test_the_refine_exit_stops_the_run_at_both_zero_export_gates():
    """Step 5b enhancement-1: Gate 2, when it shows the zero-export or the
    head-cap warning, and step 3c's zero-export gate offer [R] Refine the
    brief, a HARD HALT with halted-for-brief-refinement (exit 6) that names
    the fix. The stage's Rules close the tree first and, under --batch, end
    only the brief; a headless run keeps the [C] default."""
    extract = _read(REFS / "extract.md")
    six = _section(extract, "### 6. Present Extraction Summary", "### 7.")
    assert "**[C] Continue anyway**: compile an empty surface (default)\n**[R] Refine the brief**: stop here\"" in six
    assert '"gate": "zero-exports", "decision": "C"' in six
    seven = _section(extract, "### 7. Gate 2", None)
    assert ("When §6 showed the zero-export or the head-cap warning, also offer **[R] Refine the brief**: stop "
            "here. **GATE [default: continue]**") in seven
    assert '"gate": "review-gate", "decision": "continue"' in seven
    docs = _read(REFS / "fetch-docs.md")
    zero = next(line for line in docs.splitlines() if line.startswith('- **`source_type: "source"`, `counts.exports` is 0'))
    assert "offer **[C] Continue anyway** or **[R] Refine the brief**: stop here. **GATE [default: C]**" in zero
    # step 3c also names `doc_urls`: every fetch of it failed there
    for text, phase, fix in ((seven, "extract", "`scope.include` or `target_version`"),
                             (zero, "fetch-docs", "`scope.include`, `target_version` or `doc_urls`")):
        halt = next(line for line in text.splitlines() if "`halted-for-brief-refinement`" in line)
        match = HALT_RE.search(halt)
        assert match and match.groups() == ("6", "halted-for-brief-refinement", phase), halt[:90]
        assert "emit-halt" not in halt
        assert f"Fix {fix} in the brief (or re-run `skf-brief-skill`), then re-run `skf-create-skill`." in halt
    for name in ("extract.md", "fetch-docs.md"):
        assert len(_halt_rules(REFS / name)) == 1, name
    assert _exit_codes()["halted-for-brief-refinement"] == 6
    gates = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Gates** |"))
    assert "step 3: Review Gate [C]/[R]" in gates and "step 3c: Zero-Export Gate [C]/[R]" in gates


def test_the_promotion_and_post_promotion_halts_write_their_result_file():
    """#1147: generate-artifacts.md's Rules bullet names both commands, the `--result-dir` one for the four halts
    after §3's `promote` call has run, and no HALT line carries a command of its own."""
    generate = _body(REFS / "generate-artifacts.md")
    [rule] = _halt_rules(REFS / "generate-artifacts.md")
    assert EMIT_HALT_RESULT in rule and rule.index(EMIT_HALT) < rule.index(EMIT_HALT_RESULT)
    assert ("(for every HARD HALT after §3's `promote` call has run, its exit 1 and exit 2, §4's `active-link-blocked` "
            f"and §5's `references-missing`: {EMIT_HALT_RESULT}, so the emitter also writes the halt's result file in "
            "`{forge_version}`)") in rule
    # a halt after the package was promoted points its envelope at the promoted evidence report, as SKILL.md says
    assert ('A HARD HALT that stages `"skill_package"` and `"outputs"` (the package was promoted) also sets '
            "`summary.evidence_report` to `{forge_version}/evidence-report.md`.") in rule
    promotion = _section(generate, "### 3. Promote the Staged Skill", None)
    for reason in ("staging-unreadable", "write-failed", "active-link-blocked", "references-missing"):
        line = next(ln for ln in promotion.splitlines() if f"`{reason}`" in ln and "**HARD HALT**" in ln)
        assert "emit-halt" not in line and "--result-dir" not in line, reason
    refusal = next(p for p in generate.split("\n\n") if p.startswith("Each refusal is a **HARD HALT**"))
    assert "emit-halt" not in refusal and "leaves out `--result-dir`" in refusal
    # extraction-rules.yaml is written before the promotion creates {forge_version}: no result file yet
    rules = _section(generate, "### 2. Generate extraction-rules.yaml", "### 3.")
    for line in (ln for ln in rules.splitlines() if "**HARD HALT**" in ln):
        assert "emit-halt" not in line and "--result-dir" not in line, line[:80]


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
    # `record` stamps the time (#1145): no documented decision types one, and SKILL.md says so.
    assert "timestamp" in item["required"] and "timestamp" in item["properties"]
    for name, text in examples:
        decision = json.loads(re.sub(r"\{[A-Za-z_]+\}", "x", text))
        assert set(item["required"]) - {"timestamp"} <= set(decision), (name, text)
        assert set(decision) <= set(item["properties"]) and "timestamp" not in decision, (name, text)
    rule = next(line for line in _read(SKILL).splitlines()
                if line.startswith("- Every decision the run takes without asking"))
    assert '"timestamp"' not in rule and "which stamps the decision's `timestamp` from the clock" in rule
    for path in [SKILL, *STEP_FILES, *sorted((CS / "assets").glob("*.md"))]:
        for typed in ('"timestamp": "{ISO}"', '"timestamp": "<ISO-8601>"', '"{current ISO date}"',
                      '"created_at": "', '"indexed_at": "'):
            assert typed not in _read(path), (path.name, typed)


def test_validate_checks_frontmatter_with_the_validator():
    """#1145: §3's fallback runs the validator skf-validate-frontmatter.py, never a checklist by hand."""
    three = _section(_read(REFS / "validate.md"), "### 3. Validate Frontmatter (Fallback)", "### 4.")
    [fence] = re.findall(r"```bash\n(.*?)```", three, re.DOTALL)
    assert fence.strip() == 'uv run {frontmatterValidator} "<staging-skill-dir>/SKILL.md"'
    assert "Fix in the staged SKILL.md what each `high` issue of `issues` names, then run the command once more." in three
    assert ('When that run\'s `status` is not `fail`, record "Frontmatter: PASS", with its `medium` and `low` issues '
            'under Remaining Warnings; otherwise record "Frontmatter: FAIL" with the `high` issues left.') in three
    assert "HALT" not in three and "never halts" in three
    for by_hand in ("- [ ]", "lowercase alphanumeric", "1-1024 characters"):
        assert by_hand not in three, by_hand


def test_validate_writes_metadata_through_the_stats_helper():
    """#1145: §1 and §7 write no metadata.json field by hand: --fix and --validation-status do."""
    validate = _read(REFS / "validate.md")
    one = _section(validate, "### 1. Check Tool Availability", "### 2.")
    assert "§7's call passes `--validation-status manual-only`" in one
    seven = _section(validate, "### 7. Validate metadata.json", "### 7a.")
    [fence] = re.findall(r"```bash\n(.*?)```", seven, re.DOTALL)
    assert fence.split() == ["uv", "run", "{renderMetadataStatsHelper}", "<staging-skill-dir>/provenance-map.json",
                             "\\", "--check", "<staging-skill-dir>/metadata.json", "--fix",
                             "[--validation-status", "manual-only]"]
    assert "Pass `--validation-status manual-only` when §1 found skill-check unavailable" in seven
    assert "lists those fields in `fixed`" in seven
    assert 'record "Metadata: auto-fixed {N} computed-value discrepanc(y|ies)" listing its fields' in seven
    # A fix the first --fix call wrote before a relabel re-run is still recorded.
    assert "listing its fields and those of the earlier calls" in seven
    assert "or the auto-fixed line below when an earlier call of this section listed fields in `fixed`" in seven
    for path in (REFS / "validate.md", REFS / "report.md"):
        assert "{atomicWriteHelper} write --target <staging-skill-dir>/metadata.json" not in _read(path)
        assert "write --target {skill_package}/metadata.json" not in _read(path)
    report = _read(REFS / "report.md")
    assert ('uv run {renderMetadataStatsHelper} "{forge_version}/provenance-map.json" --check '
            '"{skill_package}/metadata.json" --validation-status schema-unavailable') in report
    one = _section(report, "### 1. Display Forge Completion Banner", "### 2.")
    assert "Bind `{primary_confidence}` ← its `primary_confidence`" in one
    assert "counted from the entries' own labels" not in report
    assert _frontmatter(REFS / "report.md")["renderMetadataStatsProbeOrder"][-1] == (
        "{project-root}/src/shared/scripts/skf-render-metadata-stats.py")


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
    """Gate 2's headless default is recorded like every other gate, and the contract's Gates row lists every
    stop, which SKILL.md's Overview points at."""
    seven = _section(_read(REFS / "extract.md"), "### 7. Gate 2", None)
    assert '"gate": "review-gate", "decision": "continue"' in seven and "record --workflow skf-create-skill" in seven
    gate_text = _schema()["properties"]["headless_decisions"]["items"]["properties"]["gate"]["description"]
    assert "review-gate" in gate_text
    skill = _read(SKILL)
    gates = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Gates** |"))
    for gate in ("Tag Choice Gate", "Authoritative-File Gate [P]/[S]/[U]", "Review Gate [C]",
                 "step 3c: Zero-Export Gate [C]", "Demo-Exclusion Gate [Y]"):
        assert gate in gates, gate
    # #594: step 1 stops to ask which brief when none is named and several exist; headless halts
    assert ("step 1: Brief Selection (no brief named and several in `{forge_data_folder}`; headless: HARD HALT "
            "`brief-missing`, exit 2; one brief: picked and recorded as gate `brief-selection`)") in gates
    assert "| 1 | Load Brief | references/load-brief.md | Conditional |" in skill
    several = next(line for line in _read(REFS / "load-brief.md").splitlines() if line.startswith("- **Several briefs:**"))
    assert "**GATE [default: HALT]**: headless, ask nothing: **HARD HALT** (exit code 2, `brief-missing`" in several
    # #1148: the Overview points at the Gates row, which names the stops it used to re-list
    overview = _section(skill, "## Overview", "## Conventions")
    assert "the Gates row of `references/invocation-contract.md` lists every stop" in overview
    assert "step 3 §2b: Authoritative-File Gate [P]/[S]/[U]" in gates
    assert "step 3c: Zero-Export Gate [C]/[R]" in gates
    footnote = next(line for line in skill.splitlines() if line.startswith("*Step 3d"))
    assert "a branch inside step 3" in footnote and "alternative main step" not in footnote
    for name in ("auto_decision_count",):
        text = _schema()["properties"]["summary"]["properties"][name]["description"]
        assert "tier override in any mode" in text and "interactive run" not in text
    assert "Empty for an interactive run" not in json.dumps(_schema())


def test_compile_renders_the_auto_decisions_from_the_sink():
    seven = _section(_read(REFS / "compile.md"), "### 7. Build evidence-report.md Content", "### 8.")
    assert ("from `{run_dir}/headless-decisions.jsonl`, the run's one decision trail: one row per line of the sink, "
            "in file order") in seven
    # #1148: the sink is the list; §7 names no gate a row may come from
    for gate in ("tag-choice", "review-gate", "tier-override", "zero-exports", "manual-carry-forward"):
        assert gate not in seven, gate
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
    assert '{onCompleteCommand} --result-path="{forge_version}/create-skill-result-latest.json"' in five
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
    health = _read(REFS / "health-check.md")
    assert "Under `--batch`, `references/batch-mode.md` §4 loads this step once, after the batch summary" in health
    assert "loops back to load-brief" not in health
    toml = _read(CS / "customize.toml")
    assert "Under --batch it runs once per brief" in toml and "workflow_warnings" not in toml


def test_a_headless_brief_hands_its_line_to_the_health_check():
    """#1113: a headless run that is not --batch binds `{result_envelope_line}` to the brief's line instead of
    displaying it, so the shared health check displays it as the run's last line; an interactive run and each
    brief of a --batch run still display it here. An emit that never succeeded, and an install with no emitter,
    bind it empty, and a batch binds it empty before its one health check, so no line an earlier workflow of the
    session bound (Analyze Source's, which hands its briefs to a batch) shows as this run's result."""
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    bind = ("When `{headless_mode}` is true and the run is not `--batch`, bind `{result_envelope_line}` ← the line "
            "and do not display it here: the shared health check displays it verbatim as the run's last line (empty "
            "when no `emit` succeeded, the incomplete-install branch below included).")
    otherwise = "Otherwise display the line the emitter prints."
    assert bind in five and otherwise in five
    assert five.index(bind) < five.index(otherwise) < five.index("When it fails again, display its `message`")
    assert "Display the line the emitter prints." not in five
    assert ("When it fails again, display its `message` and, in a headless run that is not `--batch`, bind "
            "`{result_envelope_line}` empty: this brief has no result contract.") in five
    assert ("write no result contract and, in a headless run that is not `--batch`, bind `{result_envelope_line}` "
            "empty: append") in five
    summary = _section(_read(REFS / "batch-mode.md"), "### 4. Batch Summary", "**Reading a batch.**")
    empty = "Then bind `{result_envelope_line}` empty, so the health check shows no line an earlier workflow"
    assert summary.index(empty) < summary.index("load, read in full and execute `{healthCheckStepFile}`")
    row = _section(_read(CONTRACT), "| **Headless** |", "\n")
    assert ("A caller reads the run's own `SKF_CREATE_SKILL_RESULT_JSON` line. Outside `--batch` it is the run's "
            "last line: the shared health check displays it after everything else.") in row
    health = _read(REFS / "health-check.md")
    assert ("In a headless run that is not `--batch`, report.md §5 bound `{result_envelope_line}` to the brief's "
            "`SKF_CREATE_SKILL_RESULT_JSON` line without displaying it: the shared health check displays that line "
            "verbatim as the run's last line") in health
    assert health.index("Under `--batch`") < health.index("In a headless run that is not `--batch`")


def test_on_complete_is_a_shell_command_run_only_after_a_result_contract():
    toml = _read(CS / "customize.toml")
    assert "The value is a shell\n# command, run from {project-root}, not an agent instruction" in toml
    assert "TS test-skill" not in toml and "EX export" not in toml
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    assert "downstream-skill chain" not in five
    assert ("the emitter wrote this brief's result contract (its `emit` exited 0, the line's `result_path` is not "
            "null and its `warnings` hold no `result_file_write_failed` entry naming `create-skill-result-latest.json`), "
            "run it as a shell command") in five
    assert "on_complete skipped for `{name}`: no result contract was written" in five
    # #891: the skip cases are one list, each with its own line: no successful emit, or one that did not write
    # the -latest copy
    assert ("When `{onCompleteCommand}` is non-empty but the hook does not run, `--result-path` would name a missing "
            "file or an earlier compile's: skip the hook and display the line for its case:\n\n") in five
    assert ('- No `emit` succeeded (no path in `{emitEnvelopeProbeOrder}` exists, `emit` failed twice, or the run '
            'folder is lost): '
            '"on_complete skipped for `{name}`: no result contract was written ({the reason})".\n') in five
    assert ("- `emit` exited 0, but the line's `result_path` is null (the per-run record was not written) or a "
            "`result_file_write_failed` warning names `create-skill-result-latest.json` (the copy alone failed): "
            '"on_complete skipped for `{name}`: `create-skill-result-latest.json` was not written".\n') in five
    assert "skip the hook too" not in five
    assert ("a brief that halts, or whose result file or its -latest copy was\n# not written, gets no call"
            in toml)
    rules = _section(_read(REFS / "report.md"), "## Rules", "## MANDATORY SEQUENCE")
    assert "except in §5's fallback when no path in `{emitEnvelopeProbeOrder}` exists" in rules
    load_rules = _section(_read(REFS / "load-brief.md"), "## Rules", "## MANDATORY SEQUENCE")
    # the batch's state is the batch helper's, in its run folder: no sidecar checkpoint is written
    assert "batch-state.yaml" not in load_rules
    assert "Write nothing but the brief's run folder (§0) and the decisions recorded in it" in load_rules
    # #1109: a BMad-style instruction makes the shell exit 127, and the failure line then names the key's meaning.
    assert ('display "on_complete failed for `{name}`: {its exit code and first stderr line}", and when it exited '
            '127 (the shell found no such command) end that line with "; on_complete is a shell command in this '
            'workflow, not an instruction", then go on.') in five


def test_the_documented_result_payload_is_schema_valid(tmp_path):
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    payload_text = re.search(r"<<'SKF_JSON'\n(.+?)\nSKF_JSON", five, re.S).group(1)
    filled = re.sub(r"\{(run_status)\}", "success", payload_text)
    filled = re.sub(r"\{tier\}", "Forge", filled)
    # #902: the evidence report's `- Security: skipped` row, a scan that could not run
    filled = filled.replace("{security_result}", "skipped")
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
    assert envelope["summary"]["security_result"] == latest["summary"]["security_result"] == "skipped"
    assert latest["headless_decisions"] == [] and "timestamp" in latest
    assert envelope["result_path"] == next(p for p in forge.iterdir() if p.name != "create-skill-result-latest.json").as_posix()
    # #891: a folder where the -latest copy goes. The emit still exits 0 and keeps result_path, and one warning
    # names the copy: §5's hook condition skips on it.
    run_dir = tmp_path / "skf-create-skill-run00002"
    run_dir.mkdir()
    blocked = tmp_path / "forge" / "demo" / "1.0.1"
    (blocked / "create-skill-result-latest.json").mkdir(parents=True)
    proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-create-skill", "--run-dir",
                           str(run_dir), "--result-dir", str(blocked)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout.strip().split(": ", 1)[1])
    [per_run] = [p for p in blocked.iterdir() if p.name != "create-skill-result-latest.json"]
    assert envelope["result_path"] == per_run.as_posix() and per_run.is_file()
    failed = [w for w in envelope.get("warnings", []) if w.startswith("result_file_write_failed:")]
    assert len(failed) == 1 and "create-skill-result-latest.json" in failed[0], envelope.get("warnings")
    assert ("warning names `create-skill-result-latest.json` (the copy alone failed): \"on_complete skipped for "
            "`{name}`: `create-skill-result-latest.json` was not written\"") in five


def test_the_result_payload_reads_the_security_row(tmp_path):
    """#902: §5 reads the scan's outcome from the promoted evidence report's Security row, the row validate §8
    writes, and stages it in both summary objects; a value outside the schema's three stops the emitter."""
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    assert ("Bind `{security_result}` ← the first word of the `- Security:` line under `## Validation Results` in the "
            "promoted `{forge_version}/evidence-report.md` (`pass`, `warn` or `skipped`)") in five
    assert ("when that line is missing or starts with another word, leave `security_result` out of both `summary` "
            "objects") in five
    payload_text = re.search(r"<<'SKF_JSON'\n(.+?)\nSKF_JSON", five, re.S).group(1)
    assert payload_text.count('"auto_decision_count": 0, "security_result": "{security_result}"}') == 2
    payload = json.loads(payload_text.replace("{run_status}", "success").replace("{tier}", "Forge"))
    assert payload["summary"]["security_result"] == "{security_result}"
    assert payload["result_contract"]["summary"]["security_result"] == "{security_result}"
    # §8 fills skill-sections.md's blocks by name (#1147): the row lives in that template
    results = _section(_read(REFS / "validate.md"), "### 8. Update Evidence Report", "### 9.")
    assert "Fill the `## Validation Results`," in results and "of `{skillSectionsData}`'s evidence-report.md Structure" in results
    template = _section(_read(CS / "assets" / "skill-sections.md"), "## Validation Results\n", "## Quality Score Breakdown")
    assert "\n- Security: {pass/warn/skipped} ({the note §5's Security row gives})\n" in template
    # the row's three words are the schema's values
    schema = _schema()
    assert schema["properties"]["summary"]["properties"]["security_result"]["enum"] == ["pass", "warn", "skipped"]
    filled = re.sub(r"\{[a-z_]+\}", "x", json.dumps(payload).replace("{security_result}", "SKIP"))
    run_dir = tmp_path / "skf-create-skill-run00003"
    run_dir.mkdir()
    proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-create-skill", "--run-dir",
                           str(run_dir)], input=filled, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 1 and "security_result" in proc.stderr, proc.stderr


# --------------------------------------------------------------------------
# Run state on disk: the extraction inventory, the promotion (#587)
# --------------------------------------------------------------------------


def test_the_inventory_is_written_at_the_end_of_extraction():
    extract = _read(REFS / "extract.md")
    assert "extraction stays in context" not in extract
    assert ("Bind `{extraction_inventory}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`, "
            "`{detected_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.detected.json`, "
            "`{extraction_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.extraction.json`, "
            "`{co_imports_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.co-imports.json`, "
            "`{components_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.components.json` and "
            "`{read_by_eye_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.read-by-eye.json`, and run "
            '`rm -f "{extraction_inventory}" "{detected_json}" "{extraction_json}" "{co_imports_json}" '
            '"{components_json}" "{read_by_eye_json}" '
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
    docs = _read(REFS / "fetch-docs.md")
    assert 'uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field t3_items' in docs
    assert "{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json" in docs
    compile_one = _section(_read(REFS / "compile.md"), "### 1. Load Data Files", "### 1a.")
    assert "Then load `{extraction_inventory}` (`{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`)" in compile_one
    assert "{skill-name}.language-guide.json" in compile_one
    assert "`intent_mapping`" in compile_one
    # which exports metadata.json lists is the `metadata` helper's rule, stated there once (v4.0.0 quality gate
    # run 1, skf-create-skill determinism-1); §1 keeps the public: false rule for what compile writes itself
    assert "`metadata.json`'s `exports[]`" not in compile_one
    assert ("one marked `public: false`, off a `public-api` skill's public surface, stays out of SKILL.md, "
            "`references/` and the provenance map") in compile_one
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
    docs = _read(REFS / "fetch-docs.md")
    four_a = _section(docs, "### 4a.", "### 5.")
    assert '{"docs_folder": "{docs_staging}", "language_guide": [{"url": "...", "label": "...", "pages": ["page-1.md"]}]}' \
        in four_a
    assert '"prose": "..."' not in four_a
    # §4 sends a whole-language reference's registry corpora to §4a, the index's only writer (step 5b leanness-1)
    four = _section(docs, "### 4. Extract API Information", "### 4a.")
    assert "skip §4a" not in docs
    assert ("So for these briefs, extract no per-export items from the registry corpora (`source: language-registry`): "
            "§4a below keeps their pages as the Language Guide.") in four
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
# The run record: step 3 §2a writes it, compile §1 and report §5 read it back (#1144)
# --------------------------------------------------------------------------

INVENTORY_HELPER = REPO / "src" / "shared" / "scripts" / "skf-extraction-inventory.py"
INVENTORY_PROBE = ["{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py",
                   "{project-root}/src/shared/scripts/skf-extraction-inventory.py"]
RUN_KEYS = ["run_dir", "source_ref", "source_commit", "tag_resolution", "source_tree", "resolved_source_path",
            "version"]


def _helper_call(line: str, values: dict) -> list[str]:
    """A documented `uv run {extractionInventoryHelper} ...` line, its placeholders filled, as argv for this
    interpreter; a heredoc's `<<` and an optional `[--flag ...]` group are dropped."""
    for placeholder, value in values.items():
        line = line.replace(placeholder, value)
    line = re.sub(r" \[[^\]]*\]", "", line.split(" <<")[0])
    words = shlex.split(line)
    assert words[:3] == ["uv", "run", "{extractionInventoryHelper}"], words
    return [sys.executable, str(INVENTORY_HELPER), *words[3:]]


def _run_helper(argv: list[str], stdin: str = "") -> dict:
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


RECORD_THE_RUN = "**Record the run** in the extraction inventory"


def _record_the_run(two_a: str) -> str:
    """§2a's **Record the run** paragraph and its fence (the docs-only skip line names it first)."""
    return _section(two_a, RECORD_THE_RUN, "**Deferred CCC Discovery")


@pytest.mark.parametrize("mode", ["source", "docs-only"])
def test_step_3_records_the_run_right_after_it_resolves_the_source(tmp_path, mode):
    """#1144 enhancement-2: §2a records the run's source identity, the reconciled version and the run folder in
    the extraction inventory right after its dispatch, Source Commit Capture and Version Reconciliation; a
    docs-only brief records it from its skip line. The documented fence runs on a temp inventory, §3's and §5's
    `init` keep the run it recorded, and compile §1's `summary` call reads it back."""
    extract = _read(REFS / "extract.md")
    two_a = _section(extract, "### 2a. Resolve Source Access", "### 2b.")
    # #1147: the remote block's dispatch lives in references/remote-source-access.md, which §2a loads first
    assert "Dispatch on `{source_resolve_status}`:" in _read(REFS / "remote-source-access.md")
    assert (two_a.index("load `{remoteSourceAccessData}` and follow its **Read the Source Into a Private Tree** section")
            < two_a.index("Then run Source Commit Capture and Version Reconciliation")
            < two_a.index(RECORD_THE_RUN) < two_a.index("**Deferred CCC Discovery"))
    assert two_a.count(RECORD_THE_RUN) == 1
    skip = next(line for line in two_a.splitlines() if line.startswith('**If `source_type: "docs-only"`:**'))
    assert ("skip the rest of §2a but **Record the run** below, with every source field `null` and `version` the "
            "brief's `target_version`, else its `version`") in skip
    record = _record_the_run(two_a)
    assert ("resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}` (halt "
            "as §5 does when neither exists)") in record
    assert "§3's and §5's `init` keep this `run` when they start the inventory again." in record
    assert _frontmatter(REFS / "extract.md")["extractionInventoryProbeOrder"] == INVENTORY_PROBE
    [fence] = re.findall(r"```bash\n(.*?)```", record, re.S)
    mkdir_line, init_line, set_line, payload, end = fence.strip("\n").split("\n")
    assert end == "SKF_INVENTORY" and set_line.endswith(" <<'SKF_INVENTORY'")
    assert list(json.loads(payload)["run"]) == RUN_KEYS
    # on a project's first run nothing has created the stage folder, and the helper creates none
    assert mkdir_line == 'mkdir -p "{project-root}/_bmad-output/.skf-stage"'
    assert "create the folder the inventory sits in" in record
    run_dir = (tmp_path / ".skf-run" / "skf-create-skill-a1b2c3d4").as_posix()
    stage = Path(shlex.split(mkdir_line.replace("{project-root}", tmp_path.as_posix()))[2])
    inventory = stage / "demo.inventory.json"
    values = {"{extraction_inventory}": inventory.as_posix(), "{name}": "demo", "{tier}": "Forge",
              "{source|docs-only|component-library}": mode, "{source|component-library}": "source",
              "{run_dir}": run_dir}
    if mode == "source":
        expected = {"run_dir": run_dir, "source_ref": "v2.3.0", "source_commit": "89abcdef01234567",
                    "tag_resolution": {"tag": "v2.3.0"}, "source_tree": (tmp_path / "tree").as_posix(),
                    "resolved_source_path": (tmp_path / "ws").as_posix(), "version": "2.3.1"}
    else:
        expected = {key: None for key in RUN_KEYS} | {"run_dir": run_dir, "version": "1.2.0"}
    filled = payload.replace('"tag_resolution": null', '"tag_resolution": ' + json.dumps(expected["tag_resolution"]))
    for key in ("source_ref", "source_commit", "source_tree", "resolved_source_path", "version"):
        placeholder = {"resolved_source_path": "resolved-source-path"}.get(key, key)
        filled = filled.replace(f'"<{placeholder}>"', json.dumps(expected[key]))
    for placeholder, value in values.items():
        filled = filled.replace(placeholder, value)
    without_folder = subprocess.run(_helper_call(init_line, values), capture_output=True, text=True,
                                    encoding="utf-8", timeout=60)
    assert without_folder.returncode == 1 and not stage.exists(), without_folder.stderr
    stage.mkdir(parents=True)  # the fence's mkdir line
    _run_helper(_helper_call(init_line, values))
    _run_helper(_helper_call(set_line, values), filled)
    # §3 (docs-only) or §5 starts the inventory again: the run stays
    if mode == "source":
        five = _section(extract, "### 5. Build Extraction Inventory", "### 6.")
        again = next(line for line in five.splitlines() if line.startswith("uv run {extractionInventoryHelper} init "))
    else:
        three = _section(extract, "### 3. Check for Docs-Only Mode", "### 4.")
        again = next(line for line in three.splitlines() if line.startswith("uv run {extractionInventoryHelper} init "))
    _run_helper(_helper_call(again, values))
    # compile §1's summary call gives the run back
    compile_one = _section(_read(REFS / "compile.md"), "### 1. Load Data Files", "### 1a.")
    [summary] = re.findall(r'`(uv run \{extractionInventoryHelper\} summary --inventory "\{extraction_inventory\}")`',
                           compile_one)
    assert _run_helper(_helper_call(summary, values))["run"] == expected


def test_compile_binds_the_run_back_and_halts_when_the_run_folder_is_lost(tmp_path):
    """#1144: compile §1 binds `{run_dir}` and `{source_tree}` from the inventory's run when a compaction lost them;
    when no run folder can be found it halts with staging-unreadable (exit 4), emitted with nothing to stage in,
    before anything is promoted, instead of writing "No auto-decisions" for a sink it cannot read."""
    compile_md = _read(REFS / "compile.md")
    one = _section(compile_md, "### 1. Load Data Files", "### 1a.")
    assert ("Bind `{run_dir}` ← its `run.run_dir` when `{run_dir}` is not bound, and `{source_tree}` ← its "
            "`run.source_tree` when `{source_tree}` is not bound") in one
    assert one.index("bind `{inventory_counts}` ← its `counts`") < one.index("Bind `{run_dir}` ← its `run.run_dir`")
    assert "`warnings` and `run` (a component library's `component_catalog` and `component_stats` too)" in one
    [halt] = [line for line in one.splitlines() if "**HARD HALT**" in line]
    assert halt.startswith("When `{run_dir}` is still not bound, **HARD HALT** (exit code 4, `staging-unreadable`, "
                           "phase `compile`; emit with nothing to stage in, as load-brief.md §0 does, with no "
                           "`--run-dir`)")
    assert ('"Cannot compile: the run folder is lost (`{run_dir}` is not bound and the extraction inventory records '
            "none), so this run's decisions cannot be read. Re-run create-skill.\"") in halt
    assert _exit_codes()["staging-unreadable"] == 4
    [fence] = re.findall(r"```bash\n(.*?)```", one, re.S)
    command, rest = fence.split(" <<'SKF_JSON'\n")
    assert command == "uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --target stderr"
    payload = rest.split("\nSKF_JSON")[0].replace("<that message, one line>", "Cannot compile: the run folder is lost.")
    proc = subprocess.run([sys.executable, str(EMITTER), "emit-halt", "--workflow", "skf-create-skill", "--target",
                           "stderr"], input=payload, capture_output=True, text=True, encoding="utf-8", timeout=30,
                          cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    line = next(text for text in proc.stderr.splitlines() if text.startswith("SKF_CREATE_SKILL_RESULT_JSON: "))
    envelope = json.loads(line.split(": ", 1)[1])
    assert (envelope["exit_code"], envelope["halt_reason"], envelope["phase"]) == (4, "staging-unreadable", "compile")
    # §7: "No auto-decisions" now means a bound run folder whose sink is empty
    seven = _section(compile_md, "### 7. Build evidence-report.md Content", "### 8.")
    assert ("`{run_dir}` is bound here (§1 halted otherwise), so a file that is missing or empty means no gate "
            "recorded a decision: emit the section with the single line `No auto-decisions:") in seven
    assert "When the file is missing or empty, emit the section" not in seven


def test_report_binds_a_lost_run_folder_back_or_writes_no_contract():
    """#1144: report §5 binds a lost `{run_dir}` from the inventory's run before it reads the sink, never
    `{source_tree}` (step 7 removed the tree); a run folder it still cannot find gets no result contract, the
    hook's "No `emit` succeeded" case and no `rm -rf`, never a count of 0 decisions."""
    assert _frontmatter(REFS / "report.md")["extractionInventoryProbeOrder"] == INVENTORY_PROBE
    five = _section(_read(REFS / "report.md"), "### 5. Result Contract", "### 6.")
    find = _section(five, "**Find the run folder.**", "Otherwise first read the run sink")
    assert ("When `{run_dir}` is not bound, resolve `{extractionInventoryHelper}` ← first existing path in "
            "`{extractionInventoryProbeOrder}` and bind `{run_dir}` ← the `run.run_dir` this prints, from "
            "`{project-root}` (never `{source_tree}`: step 7 removed the tree)") in find
    assert ('uv run {extractionInventoryHelper} summary --inventory '
            '"{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json"') in find
    assert five.index("**Find the run folder.**") < five.index('grep -c . "{run_dir}/headless-decisions.jsonl"')
    assert ("write no result contract: display \"No result contract for `{name}`: its run folder is lost, so its "
            "decisions cannot be read.\" and, in a headless run that is not `--batch`, bind "
            "`{result_envelope_line}` empty") in find
    assert 'The post-completion hook below then skips under its "No `emit` succeeded" case' in find
    remove = _section(five, "**Remove the run folder.**", "\n")
    assert 'delete `{run_dir}` (`rm -rf "{run_dir}"`), unless it is lost;' in remove


# --------------------------------------------------------------------------
# The ecosystem-check stage is gone (#599)
# --------------------------------------------------------------------------


def test_no_ecosystem_check_stage():
    assert not (REFS / "ecosystem-check.md").exists()
    load_brief = _read(REFS / "load-brief.md")
    assert "nextStepFile: 'ccc-discover.md'" in load_brief
    assert 'Proceeding to extraction..."' in load_brief
    for path in [SKILL, *STEP_FILES]:
        assert "ecosystem" not in _read(path).lower(), path.name
    gates = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Gates** |"))
    assert "step 2:" not in gates


# --------------------------------------------------------------------------
# A docs-only brief with nothing fetched halts before compile
# --------------------------------------------------------------------------


def test_zero_content_check_halts_a_docs_only_brief():
    docs = _read(REFS / "fetch-docs.md")
    check = _section(docs, "**Zero-content check.**", "### 5b.")
    assert 'uv run {extractionInventoryHelper} summary --inventory "{extraction_inventory}"' in check
    halt = next(line for line in check.splitlines() if "`docs-unreachable`" in line)
    assert "no URL or subpage fetched in this run, and `counts.items` is 0" in halt
    assert "Stage and promote nothing" in halt and "emit-halt" not in halt
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


def _fenced_call(text: str, needle: str) -> str:
    """The one fenced command that holds `needle`, its continued lines joined."""
    blocks = [block.replace("\\\n", " ") for block in re.findall(r"^```[a-z]*\n(.*?)^```", text, re.M | re.S)]
    lines = [line.strip() for block in blocks for line in block.splitlines() if needle in line]
    assert len(lines) == 1, (needle, lines)
    return re.sub(r"\s+", " ", lines[0])


def _argv(call: str, helper: str, values: dict) -> list[str]:
    """The arguments of a documented `uv run {helper} ...` call, each `{name}` bound, optional groups kept."""
    words = shlex.split(call.split(">")[0].replace("[", "").replace("]", ""))
    assert words[:3] == ["uv", "run", "{" + helper + "}"], words
    out = []
    for word in words[3:]:
        for name, value in values.items():
            word = word.replace("{" + name + "}", value)
        out.append(word)
    return out


def test_the_detector_keeps_to_the_brief():
    """#697: §4c scopes the detector with the brief, by the scope test update-skill uses, and no longer with
    `--scope-include` (fnmatch: `*` crossed `/`, `**/` needed a folder, `scope.exclude` was ignored)."""
    four_c = _section(_read(REFS / "extract.md"), "### 4c.", "### 5.")
    call = _fenced_call(four_c, "{detectScriptsAssetsHelper} detect")
    assert '--brief "{brief_path}" [--max-lines 500]' in call
    assert "--scope-include" not in four_c and "<glob1>" not in four_c
    assert "`--brief` keeps it to the files the brief's `scope.include` and `scope.exclude` take" in four_c
    assert "or a brief it cannot read): warn" in four_c
    rules = _section(_read(REFS / "extraction-patterns-tracing.md"), "### Inclusion Rules", "### Provenance")
    assert "a `scope.include` pattern matches them and no `scope.exclude` pattern does" in rules


def test_create_and_update_detect_the_same_paths(tmp_path):
    """#697: §4c's documented detector call and update-skill Category D's documented pipe (the unscoped
    detector into skf-new-file-diff.py --brief), run on one tree and brief with an empty map, keep the same
    paths."""
    scripts = REPO / "src" / "shared" / "scripts"
    detector = scripts / "skf-detect-scripts-assets.py"
    new_file_diff = REPO / "src" / "skf-update-skill" / "scripts" / "skf-new-file-diff.py"
    source = tmp_path / "src"
    for rel, text in {"scripts/build.sh": "#!/bin/bash\n", "scripts/dev/release.sh": "#!/bin/bash\n",
                      "api.schema.json": "{}\n", "pkg/__init__.py": "", "pkg/scripts/run.sh": "echo\n",
                      "pkg/tools/__init__.py": "", "pkg/tools/t.py": "T = 1\n", "pkg/cli/main.sh": "#!/bin/sh\n",
                      "examples/demo.json": "{}\n", "tools/release.sh": "#!/bin/bash\n"}.items():
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(text.encode("utf-8"))
    brief = tmp_path / "skill-brief.yaml"
    brief.write_bytes(b"name: demo\nlanguage: Python\nscope:\n  include:\n  - 'scripts/*'\n  - '**/*.schema.json'\n"
                      b"  - 'pkg/**'\n  exclude:\n  - 'pkg/cli/**'\n")
    provenance = tmp_path / "provenance-map.json"
    provenance.write_bytes(b"{}")
    values = {"source_root": str(source), "brief_path": str(brief), "provenance_map_path": str(provenance)}
    four_c = _section(_read(REFS / "extract.md"), "### 4c.", "### 5.")
    call = _fenced_call(four_c, "{detectScriptsAssetsHelper} detect").replace("{detect|none}", "detect")
    created = subprocess.run([sys.executable, str(detector), *_argv(call, "detectScriptsAssetsHelper", values)],
                             capture_output=True, text=True, check=True)
    inventory = json.loads(created.stdout)
    create_paths = sorted(r["source_file"] for key in ("scripts_inventory", "assets_inventory")
                          for r in inventory[key])
    category_d = _section(_read(REPO / "src" / "skf-update-skill" / "references" / "detect-changes.md"),
                          "**Category D:", "**Write the category JSON**")
    left, right = _fenced_call(category_d, "{detectScriptsAssetsHelper} detect").split("|", 1)
    found = subprocess.run([sys.executable, str(detector), *_argv(left, "detectScriptsAssetsHelper", values)],
                           capture_output=True, text=True, check=True)
    diffed = subprocess.run([sys.executable, str(new_file_diff), *_argv(right.strip(), "newFileDiffHelper", values)],
                            input=found.stdout, capture_output=True, text=True, check=True)
    update_paths = sorted(r["source_file"] for r in json.loads(diffed.stdout)["new_files"])
    assert create_paths == update_paths == ["api.schema.json", "pkg/scripts/run.sh", "scripts/build.sh"]


@pytest.mark.parametrize("flag", ["--scripts-intent", "--assets-intent"])
def test_the_detector_refuses_free_text(tmp_path, flag):
    detector = REPO / "src" / "shared" / "scripts" / "skf-detect-scripts-assets.py"
    proc = subprocess.run([sys.executable, str(detector), "detect", str(tmp_path), flag, "the CLI tools in bin/"],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 1 and "must be detect|none" in proc.stderr


# --------------------------------------------------------------------------
# validate §4: one rule set for the body split (#600)
# --------------------------------------------------------------------------


# validate §2's and §4's guard lines: the snapshot is staged in the run folder and read back by path (#951)
GUARD_CAPTURE = 'uv run {descriptionGuardHelper} capture <staging-skill-dir>/SKILL.md > "{run_dir}/description-guard.json"\n'
GUARD_VERIFY = ('uv run {descriptionGuardHelper} verify-restore <staging-skill-dir>/SKILL.md \\\n'
                '    --captured-file "{run_dir}/description-guard.json"\n')


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
    for line in (GUARD_CAPTURE, GUARD_VERIFY):  # #951: the snapshot goes by file
        assert four.count(line) == 1, line
    assert "--captured-description" not in four
    assert four.count("**HARD HALT**") == 2
    assert "**HARD HALT** (exit code 5, `tier1-not-preserved`, phase `validate`" in four
    assert "- **`xref_ok` is false:** **HARD HALT** (exit code 5, `shard-xref-broken`, phase `validate`" in four
    nine = _section(_read(REFS / "validate.md"), "### 9. Auto-Proceed", None)
    assert "the §4 Tier-1 preservation and cross-reference checks" in nine
    # the evidence report names the split that ran, never the split-body it no longer runs
    validate = _read(REFS / "validate.md")
    assert "- Body: {pass/fail} {body split applied if applicable}" in _read(CS / "assets" / "skill-sections.md")
    assert "(`skill-check --fix` in §2, `skf-shard-body.py` in §4)" in validate
    assert "skill-check split-body" not in validate.replace("Never run `npx skill-check split-body --write`", "")
    assert "`#quick-start` and `#key-types` anchors name two of them" in four
    assert "trim `## Key API Summary` and `## Architecture at a Glance`" in four
    assert "Never run `npx skill-check split-body --write`" in four
    for stale in ("last resort", "last-resort", "Vercel", "Tier 1 preservation check:", "Anchor validation",
                  "Restoring from staging backup", "restore it immediately"):
        assert stale not in four, stale


def test_validate_refreshes_the_score_after_section_4():
    """#892: §5 no longer calls skill-check, so §4 ends with the call that scores the staged SKILL.md once a split
    or a §0 restore has changed it, and the evidence report takes its score over §2's when the two differ."""
    four = _section(_read(REFS / "validate.md"), "### 4. Split Oversized Body", "### 5. ")
    refresh = _section(four, "**Score refresh.**", None)
    assert four.index("**If skill-check unavailable or no body size issue:** Skip.") < four.index("**Score refresh.**")
    for needle in ("A split or a §0 restore changes SKILL.md after §2 scored it.",
                   "Unless skill-check is unavailable or `{skill_check_flag_fallback}` is true, run "
                   '`npx skill-check check <staging-skill-dir> --format json {security_scan_flag} > '
                   '"{run_dir}/skill-check.json"` once §4 is done, split or not',
                   "read only the JSON object at the start of `{run_dir}/skill-check.json`",
                   "If its quality score differs from section 2's, update the evidence-report with the newer score.",
                   "When the file does not start with a JSON object (exit 2 on a config, option or plugin error, or a "
                   "stopped call), keep section 2's score."):
        assert needle in refresh, needle


def test_validate_tells_a_fix_from_the_file_hash():
    """#901: two identical `hash` calls bracket the guarded `--fix` call; a changed SKILL.md, or one the missing
    helper left unhashed, reaches §8's Auto-Fixed line, which skill-sections.md's template repeats word for word."""
    validate = _read(REFS / "validate.md")
    sections = _read(CS / "assets" / "skill-sections.md")
    assert "fixed[]" not in validate and "fixed[]" not in sections
    assert _frontmatter(REFS / "validate.md")["hashContentProbeOrder"] == [
        "{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py",
        "{project-root}/src/shared/scripts/skf-hash-content.py"]
    # Advisory: the helper is not one the step halts without.
    (helpers,) = [line for line in _body(REFS / "validate.md").splitlines() if line.startswith("**Helpers.**")]
    assert "hashContent" not in helpers
    two = _section(validate, "### 2. Validate & Auto-Fix", "### 3. ")
    hash_call = "uv run {hashContentHelper} hash <staging-skill-dir>/SKILL.md"
    assert two.count(hash_call) == 2
    marks = [two.index(hash_call), two.index("uv run {descriptionGuardHelper} capture"),
             two.index("uv run {descriptionGuardHelper} verify-restore"), two.rindex(hash_call)]
    assert marks == sorted(marks), "hash, capture, verify-restore, hash"
    for guard_line in (GUARD_CAPTURE, GUARD_VERIFY):  # #951: the snapshot goes by file
        assert two.count(guard_line) == 1, guard_line
    assert "--captured-description" not in validate
    assert "`{hashContentHelper}` (resolve it ← first existing path in `{hashContentProbeOrder}`)" in two
    for needle in ("Run the second `hash` call after the last `verify-restore`, a §0 re-run included.",
                   "When `skill_md_hash_before` and `skill_md_hash_after` differ, record "
                   "`skill_check_fix_changed: true` for §8.",
                   "When no `{hashContentProbeOrder}` path exists (skip both `hash` calls) or a `hash` call prints no "
                   "`content_hash`, record `skill_check_fix_changed: unchecked`"):
        assert needle in two, needle
    line = ('- {"skill-check --fix rewrote SKILL.md" when §2 recorded `skill_check_fix_changed: true`, "SKILL.md may '
            'have been rewritten (not hashed) by skill-check --fix" when it recorded `skill_check_fix_changed: '
            'unchecked`, otherwise "none"}\n')
    # §8 fills skill-sections.md's `## Auto-Fixed Issues` block by name (#1147)
    assert f"## Auto-Fixed Issues\n{line}" in sections and line not in validate
    assert "`## Auto-Fixed Issues`" in _section(validate, "### 8. Update Evidence Report", "### 9.")


QUICK_WRITE = REPO / "src" / "skf-quick-skill" / "references" / "write-and-validate.md"


def _scan_reading(text: str) -> str:
    """The clause that says how a workflow reads skf-security-scan.py, from "rely on the JSON it prints"."""
    start = text.index("rely on the JSON it prints")
    return text[start:text.index("never on an exit code.", start) + len("never on an exit code.")]


def test_the_security_scan_reads_the_helpers_result():
    """#892: §5 runs skf-security-scan.py on the staged skill whether or not skill-check is available, since
    skill-check 1.2.0 passes none of the scanner's findings on, and binds the Security row from the helper's
    JSON: its `security_result` and `note`, each finding an advisory warning, a missing helper `skipped`."""
    validate = _read(REFS / "validate.md")
    five = _section(validate, "### 5. Security Scan", "### 6. ")
    assert five.startswith("### 5. Security Scan\n\nRun the scan whether or not skill-check is available.")
    assert '```bash\nuv run {securityScanHelper} run --package "<staging-skill-dir>"\n```\n' in five
    assert "npx skill-check" not in five, "skill-check runs no scan"
    assert _scan_reading(five) == _scan_reading(_read(QUICK_WRITE)), "read as Quick Skill reads it"
    assert "The helper scans only when `SNYK_TOKEN` is set;" in five
    for needle in ("Bind `{security_result}` ← its `security_result` (`pass`, `warn` or `skipped`) and "
                   "`{security_note}` ← its `note`",
                   "record each `findings[]` entry's `text` under the evidence report's Remaining Warnings as an "
                   "advisory warning: security findings do not block artifact generation",
                   'For `skipped`, log "security scan skipped: {security_note}" there.',
                   "When no `{securityScanProbeOrder}` path exists, bind `{security_result}` ← `skipped` and "
                   "`{security_note}` ← `skf-security-scan.py missing`"):
        assert needle in five, needle
    row = _section(five, "**Security row.**", "\n")
    assert ("§8 writes the `- Security:` row as `{security_result}`, then `{security_note}` in parentheses, such as "
            "`skipped (SNYK_TOKEN not configured)` or `pass (the scanner reported no risk)`") in row
    assert "Step 8 takes the row's first word as `security_result`." in row
    # The helper's own notes are the ones the row quotes.
    import importlib.util

    spec = importlib.util.spec_from_file_location("skf_security_scan", EMITTER.parent / "skf-security-scan.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert helper.run_scan(REFS, env={})["note"] == "SNYK_TOKEN not configured"
    clean = REPO / "test" / "fixtures" / "security-scan" / "clean.json"
    assert helper.classify(0, clean.read_text(encoding="utf-8"), "")["note"] == "the scanner reported no risk"
    # No token: the Display text, keyed on the helper's note, without the old `.env` and skip-flag advice.
    display = _section(five, "**If `{security_note}` is `SNYK_TOKEN not configured`:**", None)
    assert 'Display: "Security scan requires a Snyk Enterprise API token' in display
    assert ".env" not in display and "--no-security-scan" not in display
    # §1 marks only the Body row when skill-check is missing; the scan does not depend on it.
    one = _section(validate, "### 1. Check Tool Availability", "### 2. ")
    assert "mark the Body row explicitly as `skipped: skill-check unavailable` (§5, §6 and §6b do not depend on " \
        "skill-check)" in one
    for stale in ("finding code", "skill-check.stderr", "mcp-scan", "(#892)", "**If skill-check unavailable:**",
                  "security[]"):
        assert stale not in five, stale
    assert "\u2014" not in five and "\u2013" not in five
    rules = _rules(REFS / "validate.md")
    assert ("- For the validation verdict, ignore non-zero exit codes from skill-check if JSON output shows 0 errors; "
            "the security scan's row follows the result `skf-security-scan.py` prints (§5)\n") in rules


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
    assert ("(the bundled default loads every `project-context.md` under `{project-root}`, none in "
            "`{project-root}/_bmad-output/.skf-run/`; if the resolver ran, `--facts` has applied each `!` entry, "
            "which drops each earlier entry it names") in activation
    assert "except a `!` entry and the entry it names" not in activation
    assert "`{project-root}/_bmad/custom/skf-create-skill.toml` (team overrides, committed)" in activation
    assert "`_bmad/custom/skf-create-skill.toml` under `{project-root}`" not in activation


def _hook_comment(key: str) -> str:
    """The comment block directly above `key = ...` in customize.toml, as one line."""
    lines = _read(CS / "customize.toml").splitlines()
    [at] = [i for i, line in enumerate(lines) if line.startswith(f"{key} = ")]
    block = []
    for line in reversed(lines[:at]):
        if line.startswith("#"):
            block.append(line.lstrip("# "))
        elif block:
            break
    return " ".join(reversed(block))


def test_the_hook_comments_name_the_steps_that_run_them():
    """#1111: prepend runs in step 3, with no uv probe to precede; the append entries run once, after step 4
    resolves the emitter and before step 5 loads the first stage, and SKILL.md says so."""
    prepend = _hook_comment("activation_steps_prepend")
    assert "uv probe" not in prepend
    assert "SKILL.md On Activation step 3" in prepend
    assert "after the config load (step 1) and the headless flag (step 2)" in prepend
    step3 = " ".join(_section(_read(SKILL), "3. **Resolve workflow customization.**", "\n4. ").split())
    assert ("After step 4 and before step 5 loads load-brief.md or batch-mode.md, execute each entry in "
            "`workflow.activation_steps_append` in order; a --batch run executes them once, not per brief.") in step3
    assert "After activation completes" not in step3
    append = _hook_comment("activation_steps_append")
    assert "after step 4 and before step 5 loads load-brief.md or batch-mode.md" in append
    assert "once, not per brief" in append


# --------------------------------------------------------------------------
# Version Reconciliation reads the source's version through the extractor
# (v4.0.0 quality gate run 2, determinism-2)
# --------------------------------------------------------------------------

PROTOCOLS = REFS / "source-resolution-protocols.md"
UPDATE_INIT = REPO / "src" / "skf-update-skill" / "references" / "load-baseline.md"  # its §6c (#1196)
EXTRACTOR = REPO / "src" / "shared" / "scripts" / "skf-extract-public-api.py"


def _reconciliation() -> str:
    return _section(_read(PROTOCOLS), "## Version Reconciliation", None)


def _reconcile_call() -> str:
    [call] = re.findall(r"```bash\n(uv run \{extractPublicApiHelper\} [^\n]*)\n```", _reconciliation())
    return call


def _reconciled(brief_version: str, out: dict) -> str:
    """The working version the section's rule gives: the JSON's version when a file of the source states it."""
    source = out.get("version_source") or ""
    if out.get("version") is not None and (source == "manifest" or source.startswith("file:")):
        return out["version"]
    return brief_version


def test_version_reconciliation_reads_the_version_through_the_extractor():
    """A release-time placeholder (0.0.0-development) or a version that is not a string is no source version: the
    section calls the extractor, which reports either as none, in place of reading a version file by eye, and
    update-skill init §6c reads the source's version through the same call."""
    text = _reconciliation()
    assert _reconcile_call() == ('uv run {extractPublicApiHelper} --mode quick --language "{brief.language}" '
                                 '--source-root "{source_root}" --resolve-version --package-name "{brief.name}"')
    # #1193: the helper picks the version file, so a sibling package of a monorepo never names the version
    assert "The helper picks the version file itself, in this order, and reports it as `manifest_file`" in text
    assert "never from a version file by eye" in text and "Look for the first matching version file" not in text
    assert ("**The source version** is the JSON's `version` when its `version_source` is `manifest` or starts with "
            "`file:`. Keep `brief.version`, with no mismatch warning, when `version` is null or `version_source` "
            "starts with `tag:`") in text
    assert "Record the JSON's `warnings` in context for the evidence report (step 8)." in text
    # A remote source with no tree stages the version file first, and the same call reads it there.
    [fetch] = re.findall(r"```bash\n(gh api [^\n]*)\n```", text)
    assert fetch.endswith('| uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{source_ref}" --tree-file - '
                          '--dest "{run_dir}/files" "<version file>"')
    assert ('then run the call above with `--source-root "{run_dir}/files"` and `--manifest-file "<version file>"` '
            'in place of `--package-name`') in text
    assert ("`{githubFetchHelper}` (resolve it ← the first existing path of "
            "`{project-root}/_bmad/skf/shared/scripts/skf-github-fetch.py` and "
            "`{project-root}/src/shared/scripts/skf-github-fetch.py`)") in text
    extract = _frontmatter(REFS / "extract.md")
    assert extract["extractPublicApiProbeOrder"] == ["{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py",
                                                     "{project-root}/src/shared/scripts/skf-extract-public-api.py"]
    # A tag implicit resolution matched need not hold brief.version in its files: semantic-release commits a placeholder.
    implicit = _section(_read(PROTOCOLS), "**Interaction with Version Reconciliation (below):**", "\n")
    assert ("the tree's version file should carry `brief.version`, unless it holds a release-time placeholder, which "
            "the extractor reports as no version") in implicit
    six_c = _section(_read(UPDATE_INIT), "### 6c. Detect the Source Version", "### 7.")
    assert ("by the Version Reconciliation section of `skf-create-skill/references/source-resolution-protocols.md` "
            "(its `{extractPublicApiHelper}` call, from `{extractPublicApiProbeOrder}`)") in six_c
    assert "`__version__`" not in six_c and "`go.mod`" not in six_c
    assert "with `{skill_name}` as `{brief.name}`" in six_c
    assert _frontmatter(UPDATE_INIT)["extractPublicApiProbeOrder"] == extract["extractPublicApiProbeOrder"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize("manifest, content, language, brief_version, expected", [
    pytest.param("package.json", '{"name": "semrel", "version": "0.0.0-development"}', "typescript", "4.2.0",
                 "4.2.0", id="semantic-release-placeholder"),
    pytest.param("package.json", '{"name": "semrel", "version": "4.3.0"}', "typescript", "4.2.0", "4.3.0",
                 id="literal-manifest-version"),
    pytest.param("Cargo.toml", '[workspace]\nmembers = []\n\n[workspace.package]\nversion = "0.7.42"\n', "rust",
                 "0.7.41", "0.7.42", id="cargo-workspace-version"),
])
def test_the_documented_reconciliation_keeps_the_brief_version_over_a_placeholder(
        tmp_path, manifest, content, language, brief_version, expected):
    """The semantic-release case: package.json holds 0.0.0-development at tag v4.2.0, so the version stays the
    brief's 4.2.0 and the extractor's placeholder warning reaches the evidence report. A literal version, or one a
    Cargo workspace root holds, is still the source version."""
    root = tmp_path / "source"
    root.mkdir()
    (root / manifest).write_bytes(content.encode("utf-8"))
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "release"], ["tag", "v4.2.0"]):
        subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)
    values = {"{extractPublicApiHelper}": EXTRACTOR.as_posix(), "{brief.language}": language,
              "{source_root}": root.as_posix(), "{brief.name}": "semrel"}
    argv = [values.get(arg, arg) for arg in shlex.split(_reconcile_call())[2:]]
    proc = subprocess.run([sys.executable, *argv], capture_output=True, text=True, encoding="utf-8", env=env,
                          timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert _reconciled(brief_version, out) == expected
    if expected == brief_version:
        assert out["version_source"] == "tag:v4.2.0"
        assert any("'0.0.0-development' is a release-time placeholder" in w for w in out["warnings"]), out["warnings"]
