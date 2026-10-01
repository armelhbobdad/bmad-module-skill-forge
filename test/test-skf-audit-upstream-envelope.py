#!/usr/bin/env python3
"""Pins and fixtures: audit-skill reads a newer upstream ref from a private
tree, asks the remote once, and prints every envelope through the emitter.

#588 (audit part): step 1 §5b asks skf-check-workspace-drift.py `upstream`
whether the remote moved, in one call, and its [C] choice reads the upstream
ref with skf-source-tree.py `resolve` into a tree of the run's own: no lock,
no hygiene pass, no dirty-worktree sub-gate, no `dirty_worktree_choice` or
`force`, and [C] is the headless default because nothing on disk changes.
The result carries `upstream_moved` and `upstream_ref`, `next_workflow` is
update-skill when upstream moved, and the forger's AS to US handoff follows
it. A real `--depth 1 --branch <tag>` clone of a scratch upstream reads
`unchanged`, then `moved` after a release, and the [C] tree holds the new
commit while the clone stays where it was.

#593 (audit part): every HARD HALT names a halt_reason the new
skf-audit-result-envelope.v1.json lists, with the emitter command in the
stage that halts; the exit-code table and the envelope live in
references/headless-contract.md, which keeps SKILL.md within its token
budget; the choice gates record their decisions in the run sink under the
gate names the schema lists, the upstream-drift one once its choice has
run; warnings are recorded by code, never free text a quote can break;
step 6's payload emits a valid envelope and the result files.

#589 (audit part): the drift report's Out-of-Scope New Public API table is
one skf-provenance-gap-dispatch.py reads.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
AUDIT = SRC / "skf-audit-skill"
REFS = AUDIT / "references"
SKILL = AUDIT / "SKILL.md"
HEADLESS = REFS / "headless-contract.md"
INIT = REFS / "init.md"
RE_INDEX = REFS / "re-index.md"
STRUCTURAL = REFS / "structural-diff.md"
SEVERITY = REFS / "severity-classify.md"
COMPOSE = REFS / "constituent-freshness.md"
REPORT = REFS / "report.md"
SCRIPTS = SRC / "shared" / "scripts"
SCHEMA = SCRIPTS / "schemas" / "skf-audit-result-envelope.v1.json"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
DRIFT = SCRIPTS / "skf-check-workspace-drift.py"
TREE = SCRIPTS / "skf-source-tree.py"
DISPATCH = SCRIPTS / "skf-provenance-gap-dispatch.py"
CONTRACTS = SRC / "shared" / "references" / "pipeline-contracts.md"
PIPELINE_MODE = SRC / "skf-forger" / "references" / "pipeline-mode.md"
URL = "https://github.com/acme/lib"

HALT_STAGES = [INIT, RE_INDEX, STRUCTURAL, COMPOSE, SEVERITY, REPORT]
HALT_IDS = [p.stem for p in HALT_STAGES]
EMIT_HALT = ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" '
             '--target stderr < "{run_dir}/halt.json"')


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _flow(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _schema() -> dict:
    return json.loads(_read(SCHEMA))


def _settings() -> dict:
    return _schema()["$defs"]["skf-envelope"]["const"]


def _fenced(text: str, needle: str) -> str:
    lines = [line.strip() for block in re.findall(r"^[ \t]*```[a-z]*\n(.*?)^[ \t]*```", text, re.M | re.S)
             for line in block.splitlines() if needle in line]
    assert len(lines) == 1, f"expected one fenced line holding {needle!r}, found {lines}"
    return lines[0]


def _frontmatter(path: Path) -> dict:
    text = _read(path)
    assert text.startswith("---\n"), f"no frontmatter in {path.name}"
    return yaml.safe_load(text[4:text.index("\n---\n", 4)])


def _upstream() -> str:
    return _slice(_read(INIT), "### 5b. Detect Upstream Drift", "### 6. Create Drift Report")


# --------------------------------------------------------------------------
# #588: one upstream call, a private tree, no lock and no sub-gate
# --------------------------------------------------------------------------


def test_the_upstream_check_is_one_helper_call():
    section = _upstream()
    assert _fenced(section, "{checkWorkspaceDriftHelper}") == (
        'uv run {checkWorkspaceDriftHelper} upstream --source-root "{source_root}" '
        '--baseline-commit "{baseline_commit}" --baseline-ref "{baseline_ref}"')
    init = _read(INIT)
    for by_hand in ("fetch --tags", "rev-parse origin/HEAD", "origin/main", "for-each-ref", "semver-equals",
                    "git -C {source_root}"):
        assert by_hand not in init, by_hand
    flow = _flow(section)
    for status in ("**`unchanged`**", "**`skipped`**", "**`fetch-failed`**", "**`moved`**"):
        assert status in flow, status
    assert "Never compare refs by hand" in flow


def test_c_reads_the_upstream_ref_into_a_private_tree():
    section = _upstream()
    resolve = _fenced(section, "{sourceTreeHelper} resolve")
    assert resolve == ('uv run {sourceTreeHelper} resolve --source-repo "{source_repo}" --source-root '
                       '"{source_root}" --target-ref "{upstream_ref}" --timeout "{tree_timeout}"')
    assert "--update-clone" not in resolve
    flow = _flow(section)
    assert "never writes to the clone (the call passes no `--update-clone`)" in flow
    assert "bind `{source_tree}` ← `tree` and `{source_root}` ← `{source_tree}`" in flow
    # report.md, its version note and its test key on this value (#597's W3 pins).
    assert 'Set `audit_ref = {upstream_ref}`, `audit_ref_source = "checkout-latest"`' in flow
    assert "continue as **[S]**" in flow and "upstream_tree_unavailable" in flow


@pytest.mark.parametrize("path", sorted(REFS.glob("*.md")) + [SKILL], ids=lambda p: p.name)
def test_no_step_moves_the_shared_clone_or_holds_a_lock(path):
    text = _read(path)
    for gone in (".skf-workspace.lock", "flock", "cccGitHygiene", "git stash", "checkout --force",
                 "git checkout", "dirty_worktree_choice", "Dirty-Worktree", "dirty-worktree", "force=true",
                 "pre_checkout_stash_ref", "pre_checkout_force_discard", "Hold the lock"):
        assert gone not in text, (path.name, gone)


def test_c_is_the_headless_default_and_the_inputs_lose_the_consent_flags():
    flow = _flow(_upstream())
    assert "Unset or `C` runs **[C]**, the default: it reads a private tree and changes nothing on disk" in flow
    skill = _read(SKILL)
    inputs = _slice(skill, "| **Inputs** |", "\n")
    assert "`upstream_drift_choice` [optional: C / S / X" in inputs and "C, auditing the upstream ref" in inputs
    assert "`force`" not in inputs
    gates = _slice(skill, "| **Gates** |", "\n")
    assert gates.strip() == ("| **Gates** | step 1: Manifest-vs-Symlink Gate [N/M/X] · Upstream-Drift Gate [C/S/X] · "
                             "Degraded-Mode Gate [D/X] · Baseline Confirm Gate [C] |")


def test_every_halt_after_the_tree_closes_it():
    rules = _flow(_slice(_read(SKILL), "## Workflow Rules", "## Stages"))
    assert ("every HALT after it first runs `uv run {sourceTreeHelper} close --tree \"{source_tree}\"` from "
            "`{project-root}`") in rules
    assert "every step reads the source there, never at the recorded `source_path`" in rules
    for path in (INIT, RE_INDEX, STRUCTURAL, SEVERITY, REPORT):
        envelope = _flow(_slice(_read(path), "**Halt envelope.**", "```bash"))
        assert 'first run `uv run {sourceTreeHelper} close --tree "{source_tree}"`' in envelope, path.name
        # each stage binds the helper itself, so a compacted session still resolves it
        assert _frontmatter(path)["sourceTreeProbeOrder"] == [
            "{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py",
            "{project-root}/src/shared/scripts/skf-source-tree.py"], path.name
    contract = _flow(_slice(_read(REPORT), "**Remove the private source tree first.**", "The shared emitter"))
    assert 'run `uv run {sourceTreeHelper} close --tree "{source_tree}"`' in contract
    assert "source_tree_not_removed" in contract


def test_a_private_tree_has_no_ccc_index_so_relocations_use_git_grep():
    relocate = _flow(_slice(_read(STRUCTURAL), "### 1b.", "### 2."))
    assert 'When `{source_tree}` is set' in relocate
    assert '`git -C "{source_root}" grep -l -w -F -e "{name}"`' in relocate


# --------------------------------------------------------------------------
# #588: upstream_moved, upstream_ref and the route to update-skill
# --------------------------------------------------------------------------


def test_the_result_carries_the_upstream_signal():
    props = _schema()["properties"]
    assert props["upstream_moved"]["type"] == ["boolean", "null"]
    assert props["upstream_ref"]["type"] == ["string", "null"]
    assert {"upstream_moved", "upstream_ref"} <= set(_schema()["required"])
    contract = _flow(_read(HEADLESS)[_read(HEADLESS).index("## Result Contract (Headless)"):])
    assert ('`next_workflow` is `"update-skill"` when CRITICAL or HIGH findings exist or when `upstream_moved` is '
            "true") in contract
    report = _flow(_read(REPORT))
    assert ("Set `nextWorkflow` to `'update-skill'` when the saved classification's `by_severity.CRITICAL` or "
            "`by_severity.HIGH` is above 0, or when the frontmatter's `upstream_moved` is true") in report
    assert "Skill is current with source code" not in report
    assert "{IF the frontmatter's `upstream_moved` is true:}" in report
    assert "Run `[US] Update Skill` with `--target-ref {upstream_ref}`" in report


def test_the_forger_hands_upstream_ref_to_us():
    contracts = _flow(_read(CONTRACTS))
    assert ("| AS | US | skill name + drift severity + route + upstream ref | The forger's gate reads the drift "
            "severity (`drift_score`) and the route (`next_workflow`)") in contracts
    assert "US takes as `--target-ref`" in contracts
    mode = _flow(_read(PIPELINE_MODE))
    assert "an AS whose envelope names an `upstream_ref`" in mode and "`target_ref=<upstream_ref>`" in mode
    assert "goes to US as `--target-ref <target_ref>`" in mode


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    """A scratch upstream served as https://github.com/acme/lib, SKF's
    `--depth 1 --branch v1.0.0` clone of it, and the prose's commands."""
    if shutil.which("git") is None:
        pytest.skip("no git")
    work, bare = tmp_path / "work", tmp_path / "up.git"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / "lib.py").write_bytes(b"def a():\n    pass\n")
    _git(work, "add", "lib.py")
    _git(work, "commit", "-q", "-m", "v1")
    _git(work, "tag", "v1.0.0")
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    config = tmp_path / "gitconfig"
    config.write_bytes(f'[url "{bare.as_uri()}"]\n\tinsteadOf = {URL}\n'.encode("utf-8"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    ws, tmp = tmp_path / "ws", tmp_path / "t"
    tmp.mkdir()
    monkeypatch.setenv("SKF_WORKSPACE", str(ws))
    for var in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(var, str(tmp))
    clone = ws / "repos" / "github.com" / "acme" / "lib"
    clone.parent.mkdir(parents=True)
    _git(clone.parent, "clone", "-q", "--depth", "1", "--branch", "v1.0.0", URL, str(clone))

    def release(tag: str) -> str:
        (work / "lib.py").write_bytes(b"def a():\n    pass\n\n\ndef b():\n    pass\n")
        _git(work, "commit", "-q", "-am", tag)
        _git(work, "tag", tag)
        _git(work, "push", "-q", str(bare), "main", f"refs/tags/{tag}")
        return _git(work, "rev-parse", "HEAD")

    def run(line: str, values: dict[str, str]) -> dict:
        words = shlex.split(line)
        assert words[:2] == ["uv", "run"]
        script = {"{checkWorkspaceDriftHelper}": DRIFT, "{sourceTreeHelper}": TREE}[words[2]]
        args = []
        for word in words[3:]:
            for name, value in values.items():
                word = word.replace(name, value)
            assert "{" not in word, word
            args.append(word)
        proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=180, check=False, cwd=str(tmp_path),
                              stdin=subprocess.DEVNULL)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return json.loads(proc.stdout)

    baseline = _git(clone, "rev-parse", "HEAD")
    values = {"{source_root}": str(clone), "{baseline_commit}": baseline, "{baseline_ref}": "v1.0.0",
              "{source_repo}": URL, "{tree_timeout}": "100"}
    return clone, baseline, release, run, values


def test_a_tag_pinned_clone_reads_unchanged_then_moved_and_c_leaves_it_alone(upstream):
    """The #588 acceptance fixture: a `--depth 1 --branch <tag>` clone has no
    origin/HEAD, which made the prose read every audit as moved."""
    clone, baseline, release, run, values = upstream
    check = _fenced(_upstream(), "{checkWorkspaceDriftHelper}")
    result = run(check, values)
    assert (result["status"], result["upstream_ref"]) == ("unchanged", None)
    new = release("v1.1.0")
    result = run(check, values)
    assert (result["status"], result["upstream_ref"], result["upstream_commit"]) == ("moved", "v1.1.0", new)
    values["{upstream_ref}"] = result["upstream_ref"]
    tree = run(_fenced(_upstream(), "{sourceTreeHelper} resolve"), values)
    assert (tree["status"], tree["tag_resolution"]["status"], tree["source_commit"]) == ("ready", "target-ref", new)
    assert b"def b():" in (Path(tree["tree"]) / "lib.py").read_bytes()
    # Nothing moved the shared clone.
    assert _git(clone, "rev-parse", "HEAD") == baseline
    assert _git(clone, "status", "--porcelain") == ""
    closed = run('uv run {sourceTreeHelper} close --tree "{source_tree}"', {"{source_tree}": tree["tree"]})
    assert closed["status"] == "removed" and not Path(tree["tree"]).exists()


# --------------------------------------------------------------------------
# #593: one schema, one emitter, every halt
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", HALT_STAGES, ids=HALT_IDS)
def test_each_halting_stage_carries_the_emit_command(path):
    text = _read(path)
    assert "**Halt envelope.**" in text
    assert _fenced(text, "emit-halt") == EMIT_HALT
    assert "shape per SKILL.md" not in text and "emit the error envelope" not in text


@pytest.mark.parametrize("path", sorted(REFS.glob("*.md")) + [SKILL], ids=lambda p: p.name)
def test_every_halt_reason_is_one_the_schema_lists(path):
    reasons = set(re.findall(r'`halt_reason: "([a-z-]+)"`', _read(path)))
    assert reasons <= set(_settings()["exit_codes"]), (path.name, reasons - set(_settings()["exit_codes"]))


def test_the_exit_code_table_agrees_with_the_schema():
    rows = {}
    for line in _slice(_read(HEADLESS), "## Exit Codes", "## Result Contract").splitlines():
        m = re.match(r"\| (\d) +\| ([a-z-]+) +\| (.*)\|$", line)
        if m:
            rows[int(m.group(1))] = m.group(2) + " " + m.group(3)
    for reason, code in _settings()["exit_codes"].items():
        assert reason in rows[code], (reason, code)
    assert set(rows) == set(_schema()["properties"]["exit_code"]["enum"])
    contract = _read(HEADLESS)[_read(HEADLESS).index("## Result Contract (Headless)"):]
    listed = set(re.findall(r'`"([a-z-]+)"`', _slice(contract, "`halt_reason` is one of:", "\n")))
    assert listed == set(_settings()["exit_codes"])


def test_skill_md_points_at_the_carved_contract():
    """SKILL.md stays within its token budget: the exit-code table and the
    envelope live in the reference its Invocation Contract names."""
    skill = _read(SKILL)
    for carved in ("## Exit Codes", "## Result Contract", "SKF_AUDIT_RESULT_JSON: {"):
        assert carved not in skill, carved
    row = _slice(skill, "| **Exit codes** |", "\n")
    assert "`references/headless-contract.md`" in row
    assert "`SKF_AUDIT_RESULT_JSON: {" in _read(HEADLESS)
    # the exit-4 site of the report write is step 6's §4, where report.md raises it
    assert "step 6 §4 (drift report write failed" in _read(HEADLESS)
    assert '### 4. Update Report Frontmatter' in _read(REPORT)
    assert "HALT with **exit 4**, `halt_reason: \"write-failed\"`, phase `report:write`" in _flow(
        _slice(_read(REPORT), "### 4. Update Report Frontmatter", "### 5."))


def test_the_overview_claims_only_what_the_stages_do():
    """A code-mode stack's map records no single source root (create-stack's
    provenance-map-schema.md), so normalize returns none and step 1 §5 stops
    it: no line says it is re-indexed (W5-audit-inputs-leanness binds it)."""
    overview = _flow(_slice(_read(SKILL), "## Overview", "## Conventions"))
    assert "a code-mode stack's provenance map records no single source root, so its audit stops at step 1 §5" in (
        overview)
    stack = _flow(_slice(_read(STRUCTURAL), "**For code-mode stacks:**", "\n"))
    assert "none reaches this step yet" in stack and "re-extracted" not in stack


def test_the_tier_override_input_wins():
    tier = _flow(_slice(_read(INIT), "**Apply tier override:**", "\n"))
    assert ("the invocation's `tier_override` input wins, then `tier_override` in `{sidecar_path}/preferences.yaml`, "
            "then the detected tier") in tier
    assert "log which one set the tier" in tier
    headless = _slice(_read(SKILL), "| **Headless** |", "\n")
    assert "`tier_override` sets the tier (step 1 §2)" in headless and "consumed at the gates" not in headless


def test_the_upstream_check_runs_whatever_the_baseline():
    """The helper owns the skip rules (no baseline ref or commit, degraded
    mode): only a compose-mode stack, which has no source tree, skips by
    hand, and nothing binds the audit-ref values by hand outside the
    helper-unavailable branch."""
    section = _flow(_upstream())
    assert "**Skip this section** if any of the following hold" not in section
    assert 'audit_ref = baseline_ref or "(unknown)"' not in section
    assert ('**A compose-mode stack** (`{compose_mode_stack}`) has no source tree: skip this section with '
            '`upstream_fetch = "skipped: compose-mode stack"`') in section
    assert "**Otherwise**, ask the remote once, whatever the baseline" in section


@pytest.mark.parametrize("ref,commit,reason,source", [("local", "", "no-baseline-ref", "unavailable"),
                                                      ("", "", "no-baseline-ref", "unavailable"),
                                                      ("v1.0.0", "", "no-baseline-commit", "baseline")],
                         ids=["local-ref", "degraded-mode", "no-commit"])
def test_the_helper_skips_a_run_with_no_baseline(tmp_path, ref, commit, reason, source):
    """The prose's one call, with the values a non-git source or degraded
    mode leaves, skips by itself and returns the audit-ref values step 6
    renders, without touching the source root."""
    words = shlex.split(_fenced(_upstream(), "{checkWorkspaceDriftHelper}"))
    values = {"{source_root}": str(tmp_path / "nowhere"), "{baseline_commit}": commit, "{baseline_ref}": ref}
    args = []
    for word in words[3:]:
        for name, value in values.items():
            word = word.replace(name, value)
        args.append(word)
    proc = subprocess.run([sys.executable, str(DRIFT), *args], capture_output=True, text=True, encoding="utf-8",
                          timeout=120, check=False, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert (result["status"], result["skip_reason"], result["audit_ref_source"]) == ("skipped", reason, source)
    assert result["audit_ref"] == (ref if ref and ref != "local" else "(unknown)")


def test_c_records_its_decision_once_it_ran_and_its_warning_by_code():
    """A headless [C] that falls back to the baseline records S with the
    fallback's code, and the warning holds a code, never a git message whose
    apostrophe would break a single-quoted shell argument."""
    section = _flow(_upstream())
    assert "record the decision in the run sink once the choice has run, and before an [X] halt" in section
    assert ("with `taken_action` `S` and `\"fallback\": \"<code>\"` in the evidence when [C] could not read the "
            "tree") in section
    assert ('--warning "upstream_tree_unavailable: <code>"`, the code being `skipped`, the `reason` of an '
            '`unavailable` result, `other-ref` or `helper-unavailable`') in section
    for path in sorted(REFS.glob("*.md")):
        assert "--warning '" not in _read(path), path.name


def test_the_hook_failure_is_shown_and_the_resolver_fallback_is_a_warning():
    """The run folder is gone after step 6, so a hook failure is told to the
    user, not recorded; a resolver fallback reaches the envelope through the
    emitter's payload-only key."""
    report = _flow(_read(REPORT))
    assert "on_complete_failed" not in report
    assert "When the hook fails, tell the user it failed and why, and go on" in report
    assert ('When On Activation step 3 fell back to the bundled `customize.toml`, add '
            '`"customization_resolver_unavailable": "<the reason>"`') in report
    activation = _flow(_slice(_read(SKILL), "## On Activation", "5. Load, read the full file"))
    assert "keep the reason as `{customization_resolver_unavailable}`" in activation
    assert "the run folder step 4 below creates" in activation


def test_the_gates_record_the_decisions_the_schema_names():
    gates = set(re.findall(r'\{"gate": "(init\.[a-z-]+)"', _read(INIT)))
    enum = set(_schema()["properties"]["headless_decisions"]["items"]["properties"]["gate"]["enum"])
    assert gates == enum
    record = ('uv run {emitEnvelopeHelper} record --workflow skf-audit-skill --run-dir "{run_dir}" --decision '
              '< "{run_dir}/decision.json"')
    assert _read(INIT).count(record) == len(enum)


def test_activation_resolves_the_emitter_and_creates_the_run_folder():
    activation = _flow(_slice(_read(SKILL), "## On Activation", "5. Load, read the full file"))
    assert "`run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-audit-skill-{timestamp}`" in activation
    assert ("`{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, "
            "else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`") in activation
    assert 'mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"' in activation
    assert "rm -rf \"{run_dir}\"" in _read(REPORT)


def _result_context(drift_score: str, upstream_moved, upstream_ref) -> dict:
    """report.md's payload, filled as its rules say."""
    route = "update-skill" if drift_score in ("CRITICAL",) or upstream_moved is True else None
    summary = {"drift_count": 0, "severity": drift_score, "next_workflow": route, "audit_ref": "v1.1.0",
               "upstream_moved": upstream_moved, "upstream_ref": upstream_ref}
    return {"status": "success", "skill_name": "demo", "drift_score": drift_score,
            "report_path": "/f/demo/1.0.0/drift-report-20260101-000000.md", "next_workflow": route,
            "audit_ref": "v1.1.0", "upstream_moved": upstream_moved, "upstream_ref": upstream_ref,
            "result_contract": {"skill": "skf-audit-skill", "status": "success",
                                "outputs": [{"type": "report", "path": "/f/demo/1.0.0/drift-report.md"}],
                                "summary": summary}}


def test_the_report_payload_holds_the_envelope_fields():
    block = _slice(_read(REPORT), "Write `{run_dir}/result-context.json`:", "Then run, in every mode")
    for field in ("status", "skill_name", "drift_score", "report_path", "next_workflow", "audit_ref",
                  "upstream_moved", "upstream_ref", "result_contract"):
        assert f'"{field}":' in block, field
    assert _fenced(_read(REPORT), " emit --workflow") == (
        'uv run {emitEnvelopeHelper} emit --workflow skf-audit-skill --run-dir "{run_dir}" '
        '--result-dir "{forge_version}" < "{run_dir}/result-context.json"')


@pytest.mark.parametrize("drift_score,moved,ref", [("CLEAN", True, "v1.1.0"), ("CLEAN", False, None),
                                                   ("CRITICAL", None, None)],
                         ids=["clean-upstream-moved", "clean-unchanged", "critical-unchecked"])
def test_the_emitter_writes_the_result_and_a_valid_envelope(tmp_path, drift_score, moved, ref):
    run_dir = tmp_path / "run" / "skf-audit-skill-20260101-000000"
    version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir.mkdir(parents=True)
    version.mkdir(parents=True)
    decision = {"gate": "init.upstream-drift", "default_action": "C", "taken_action": "C",
                "reason": "headless: upstream moved (v1.0.0 -> v1.1.0); auditing v1.1.0 per upstream_drift_choice="
                          "default C."}
    record = subprocess.run([sys.executable, str(EMITTER), "record", "--workflow", "skf-audit-skill", "--run-dir",
                             str(run_dir), "--decision"], input=json.dumps(decision), capture_output=True,
                            text=True, encoding="utf-8", check=False)
    assert record.returncode == 0, record.stderr
    proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-audit-skill", "--run-dir",
                           str(run_dir), "--result-dir", str(version)],
                          input=json.dumps(_result_context(drift_score, moved, ref)), capture_output=True,
                          text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    prefix, _, line = proc.stdout.strip().partition(": ")
    assert prefix == "SKF_AUDIT_RESULT_JSON"
    envelope = json.loads(line)
    Draft202012Validator(_schema()).validate(envelope)
    assert (envelope["upstream_moved"], envelope["upstream_ref"], envelope["run_id"]) == (moved, ref,
                                                                                         "20260101-000000")
    assert envelope["next_workflow"] == ("update-skill" if moved or drift_score == "CRITICAL" else None)
    assert [d["gate"] for d in envelope["headless_decisions"]] == ["init.upstream-drift"]
    latest = json.loads((version / "audit-skill-result-latest.json").read_text(encoding="utf-8"))
    assert latest["summary"]["upstream_moved"] is moved and Path(envelope["result_path"]).is_file()


# --------------------------------------------------------------------------
# #589: Out-of-Scope New Public API, as update-skill's §1c reads it
# --------------------------------------------------------------------------


def test_the_out_of_scope_table_is_one_the_dispatcher_reads():
    spec = importlib.util.spec_from_file_location("skf_gap_dispatch_for_audit", DISPATCH)
    dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dispatch)
    block = _slice(_read(REPORT), "## Remediation Suggestions\n", "### Workflow Recommendation")
    row = "| `{outside_scope[].path}` | exports `{name}`, `{name}` through `{entry point}` |"
    assert row in block
    report = block.replace(row, "| `src/next/index.ts` | exports `Zed`, `Alpha` through `index.ts` |")
    section = dispatch.extract_out_of_scope_section("# Drift Report\n\n" + report)
    assert dispatch.parse_candidates(section) == [
        {"path": "src/next/index.ts", "evidence": "exports `Zed`, `Alpha` through `index.ts`"}]
    prose = _flow(_slice(_read(REPORT), "**Public API outside the skill's scope.**", "Append to {outputFile}:"))
    assert "lists items in `outside_scope`" in prose and "nothing here is judged by eye" in prose
    template = _read(AUDIT / "assets" / "drift-report-template.md")
    remediation = _slice(template, "## Remediation Suggestions", "---")
    assert "Out-of-Scope New Public API" in remediation
