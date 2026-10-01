#!/usr/bin/env python3
"""Analyze Source's step-by-step chain: one opening question, one gate per
step, a shared [D] handler, units deferred by the stated goal, each unit's
own project path and ref carried into its brief, and the customization
surface (#602, #594, #596, #599, #600).

Step prose is not executed by any test, so these checks pin the prose and
run the commands it documents, filled in as an agent fills them:

- init asks at most one opening question, reads the invocation first,
  binds --target-ref and resolves each path's ref once into `refs`;
  generate-briefs writes each unit's ref and project path into its brief
  through the brief writer, and an [auto] run that falls back keeps its pin.
- scan-root.md makes each project path's scan root: a shorthand is cloned
  over https, and a package folder of a local repository with a ref is read
  from a copy at the ref (the documented commands run on a fixture).
- identify-units lets skf-disqualify-candidates.py list each boundary's
  files under the project path's scan root and hands each unit's list to
  skf-detect-language.py by file: the documented commands run on a fixture.
- Every step-by-step gate keeps one menu and records its headless default
  in the run sink; each documented decision passes the envelope schema's
  gate enum through the emitter and reaches `headless_decisions`.
- Both [D] handlers load discover-additional-source.md, which declares the
  probe order of every helper it calls, maps units through the same
  map-unit-exports.md as map-and-detect, and leaves map-and-detect's
  sections for its own section 7 to write.
- An interactive run defers the units outside the stated goal; a headless
  run never does.
- step-auto-scope.md loads its coexistence, split and corpora branches
  from their own files, and honours the hints.
- customize.toml keeps only the settings a stage reads.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
AN = SRC / "skf-analyze-source"
REFS = AN / "references"
SCRIPTS = SRC / "shared" / "scripts"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
WRITER = SCRIPTS / "skf-write-skill-brief.py"
DISQUALIFY = SCRIPTS / "skf-disqualify-candidates.py"
LANGUAGE = SCRIPTS / "skf-detect-language.py"
SCHEMA = json.loads((SCRIPTS / "schemas" / "skf-analyze-result-envelope.v1.json").read_text(encoding="utf-8"))
GATE_ENUM = SCHEMA["properties"]["headless_decisions"]["items"]["properties"]["gate"]["enum"]
PREFIX = "SKF_ANALYZE_RESULT_JSON: "

SKILL = AN / "SKILL.md"
CUSTOMIZE = AN / "customize.toml"
INIT = REFS / "init.md"
SCAN = REFS / "scan-project.md"
SCAN_ROOT = REFS / "scan-root.md"
UNIT_EXPORTS = REFS / "map-unit-exports.md"
IDENTIFY = REFS / "identify-units.md"
MAP = REFS / "map-and-detect.md"
RECOMMEND = REFS / "recommend.md"
GENERATE = REFS / "generate-briefs.md"
DISCOVER = REFS / "discover-additional-source.md"
AUTO = REFS / "step-auto-scope.md"
COEXIST = REFS / "step-auto-scope-coexistence.md"
SPLIT = REFS / "step-auto-scope-split.md"
CORPORA = REFS / "step-auto-scope-corpora.md"
HEADLESS = REFS / "headless-contract.md"
CHAIN = [SCAN, IDENTIFY, MAP, RECOMMEND, GENERATE]
RECORD = 'uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"'
HALT = 'uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"'


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    assert text.count(start) == 1, f"expected exactly one {start!r}"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    return body


def _frontmatter(text: str) -> str:
    return text.split("\n---\n", 1)[0]


def _bash_lines(text: str) -> list[str]:
    lines = []
    for m in re.finditer(r"^( *)```bash\n(.*?)^\1```", text, flags=re.M | re.S):
        lines += [line.strip() for line in m.group(2).split("\n") if line.strip()]
    return lines


def _argv(command: str, values: dict) -> list[str]:
    words = []
    for word in shlex.split(re.sub(r"\{([\w-]+)\}", r"@@\1@@", command)):
        words.append(re.sub(r"@@([\w-]+)@@", lambda m: values[m.group(1)], word))
    assert words[:2] == ["uv", "run"], words
    return [sys.executable, *words[2:]]


def _run(command: str, values: dict, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    command, _, source = command.partition(" < ")
    if source:
        path = re.sub(r"\{([\w-]+)\}", lambda m: values[m.group(1)], source.strip().strip('"'))
        stdin = Path(path).read_bytes()
    return subprocess.run(_argv(command, values), input=stdin, capture_output=True, timeout=120)


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / "skf-analyze-source-Ab3dE5gH"
    run_dir.mkdir(parents=True)
    return run_dir


# --------------------------------------------------------------------------
# One opening question (#602 item 4); the ref pins reach the briefs (#594)
# --------------------------------------------------------------------------


def test_init_asks_at_most_one_opening_question():
    opening = _section(_read(INIT), "### 3. Opening Question", "### 4. Validate the Inputs")
    for needle in ("Read the invocation first", "A flag wins over the message", "ask at most one question",
                   "**A path and a goal:** ask nothing", "a headless run never reads one from the message",
                   'HARD HALT (exit code 2, `halt_reason: "input-missing"`, phase `init:3`)'):
        assert needle in opening, needle
    assert opening.count("Wait for the answer") == 1
    text = _read(INIT)
    for gone in ("What are you hoping to get out of this analysis?", "Do you have scope hints to narrow",
                 "### 4. Collect Optional Scope Hints", "Otherwise prompt as today"):
        assert gone not in text, gone
    # The stale-report check asks the same question, once.
    assert "ask section 3's opening question now" in _section(text, "### 1.", "### 2. Verify")


def test_target_ref_is_bound_validated_and_persisted():
    text = _read(INIT)
    pins = _section(text, "**Ref pins:**", "### 5.")
    assert "`target_ref` ← it" in pins and "mutually exclusive" in pins
    assert "Resolve each project path's **ref** once, here: its `--target-refs` entry, else `target_ref`, else none" in pins
    assert "Every later step reads a path's ref from `refs` alone" in pins
    frontmatter = _section(text, "### 6. Create Analysis Report", "### 7.")
    assert "target_ref: '{target_ref, or empty}'" in frontmatter
    assert "refs: {each project path with a ref: its ref}" in frontmatter
    assert "project_paths[0]" not in "".join(_read(p) for p in REFS.glob("*.md"))


def test_the_ref_rule_is_stated_once():
    """init resolves each path's ref into `refs`; the later steps read it there."""
    for path in REFS.glob("*.md"):
        text = _read(path)
        assert "`constituent_refs` entry" not in text, path.name
        if path != INIT:
            assert "else `target_ref`" not in text, path.name
    for path in (SCAN, RECOMMEND, GENERATE, SCAN_ROOT, DISCOVER):
        assert "`refs`" in _read(path), path.name


def test_an_auto_run_that_falls_back_keeps_its_pin():
    text = _read(AUTO)
    exit1 = next(line for line in text.splitlines() if line.startswith("- **Exit 1 (unknown shape):**"))
    assert "`target_ref: '{pinned_ref}'`" in exit1 and "`refs: {each project path: '{pinned_ref}'}`" in exit1
    assert '`{pinned_ref_type}` is `"tag"` or `"branch"`' in exit1
    assert exit1.index("refs:") < exit1.index("execute `references/scan-project.md`")


@pytest.mark.parametrize("ref", ["v2.1.0", "release/next", None], ids=["tag", "branch", "no-ref"])
def test_each_brief_gets_its_unit_ref_and_project_path(tmp_path, ref):
    """generate-briefs' context carries the unit's ref and source; the writer keeps them."""
    text = _read(GENERATE)
    mapping = _section(text, "**Field mapping:**", "Write each unit's context")
    assert "| source_repo | The unit's project path" in mapping
    assert "| target_ref | The unit's ref: its project path's entry in `refs`, else null" in mapping
    [template] = re.findall(r"```json\n(\{.*?\})\n```", _section(text, "### 2. Build Each Brief's Context", "### 3."),
                            flags=re.S)
    values = {"unit-name": "auth", "the unit's ref, or null": ref, "version, or null": None,
              "source_repo": "https://github.com/acme/mono", "language": "typescript",
              "description": "Auth helpers. Use when signing users in.", "forge_tier": "Forge",
              "current_date": "2026-10-01", "user_name": "armel", "scope.type": "full-library",
              "scope.include": "packages/auth/**", "scope.exclude": "**/tests/**", "scope.notes": "Auth package."}
    filled = re.sub(r'"\{([^{}"]+)\}"', lambda m: json.dumps(values[m.group(1)]), template)
    context = json.loads(filled)
    run_dir = _run_dir(tmp_path)
    (run_dir / "brief-auth.json").write_bytes(json.dumps(context).encode("utf-8"))
    target = tmp_path / "forge" / "auth" / "skill-brief.yaml"
    proc = subprocess.run([sys.executable, str(WRITER), "write", "--target", str(target), "--from-flat"],
                          input=(run_dir / "brief-auth.json").read_bytes(), capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    brief = target.read_text(encoding="utf-8")
    assert "source_repo: https://github.com/acme/mono" in brief
    assert ("target_ref:" in brief) is (ref is not None)
    if ref:
        assert ref in brief


# --------------------------------------------------------------------------
# Each unit is listed and named under its own project path (W3 handoffs)
# --------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_documented_step_a_and_language_calls_run_on_a_scan_root(tmp_path):
    """identify-units Step A lists each boundary under the scan root and §4
    reads the list from the record's tree_file: no file list is typed."""
    text = _read(IDENTIFY)
    [step_a] = [line for line in _bash_lines(text) if "{disqualifyCandidatesHelper}" in line]
    command = step_a.partition(" <<")[0]
    scan_root = tmp_path / "source-1"
    for rel, data in {"packages/auth/package.json": b'{"name": "@acme/auth"}\n',
                      "packages/auth/tsconfig.json": b"{}\n",
                      "packages/auth/src/a.ts": b"export const a = 1;\n" * 40,
                      "packages/auth/src/b.ts": b"export const b = 2;\n" * 40,
                      "packages/auth/src/c.ts": b"export const c = 3;\n" * 40,
                      "packages/auth/docs/package.json": b'{"name": "docs", "private": true}\n'}.items():
        (scan_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (scan_root / rel).write_bytes(data)
    subprocess.run(["git", "init", "-q"], cwd=scan_root, check=True, capture_output=True, timeout=60)
    run_dir = _run_dir(tmp_path)
    values = {"disqualifyCandidatesHelper": str(DISQUALIFY), "scan_root": str(scan_root),
              "run_dir": str(run_dir), "i": "1", "detectLanguageHelper": str(LANGUAGE)}
    proc = _run(command, values, stdin=json.dumps([{"name": "auth", "path": "packages/auth"}]).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    [record] = json.loads(proc.stdout)["kept"]
    assert record["manifest"]["name"] == "@acme/auth" and record["files_count"] == 3
    [language_call] = [line for line in _bash_lines(text) if "{detectLanguageHelper}" in line]
    language = _run(language_call.replace("{the unit's tree_file}", record["tree_file"]), values)
    assert language.returncode == 0, language.stderr
    out = json.loads(language.stdout)
    assert (out["language"], out["confidence"]) == ("typescript", "high")


def test_the_scan_roots_are_recorded_once_and_read_by_every_step():
    scan = _read(SCAN)
    assert "scan_roots: {each project path: its scan root}" in scan
    assert 'phase `scan-project:2`, path `{path}`' in scan
    assert 'uv run {scanManifestsHelper} scan "{scan_root}"' in scan
    assert "**Per-path ref resolution:**" not in scan, "one rule for every path"
    # One statement of the scan root, which every step that makes one loads.
    for path in (SCAN, IDENTIFY, MAP, DISCOVER):
        text = _read(path)
        assert "scanRootFile: 'references/scan-root.md'" in _frontmatter(text), path.name
        assert "by {scanRootFile}" in text or "Load {scanRootFile}" in text, path.name
        assert "git clone" not in text, path.name
    # A resumed session in a new run folder makes a vanished copy again.
    for path, phase in ((IDENTIFY, "identify-units:1"), (MAP, "map-and-detect:1")):
        gone = _section(_read(path), "**A scan root that is gone.**", "Load {heuristicsFile}")
        assert "no longer exists" in gone and "update `scan_roots`" in gone, path.name
        assert f"phase `{phase}`, path `{{path}}`" in gone, path.name
    assert "step 3 §1 and step 4 §1" in _read(HEADLESS)


def test_a_remote_shorthand_is_cloned_over_https():
    """git reads `acme/mono` as a local folder: the clone gets a URL."""
    text = _read(SCAN_ROOT)
    assert 'git clone --quiet --depth 1 {ref_flag} "{url}" "{run_dir}/source-{i}"' in text
    assert '"{path}" "{run_dir}/source-{i}"' not in text
    for needle in ("`https://github.com/{path}` for the `owner/repo` shorthand",
                   "`https://{path}` for a host path without a scheme",
                   "The project path stays as it was given everywhere else"):
        assert needle in text, needle


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=a", "-c", "commit.gpgsign=false",
                           "-c", "tag.gpgsign=false", *args], cwd=cwd,
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.decode("utf-8")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize("folder", ["packages/auth", "."], ids=["package-folder", "top-folder"])
def test_a_local_path_with_a_ref_is_read_at_the_ref(tmp_path, folder):
    """A package folder of a monorepo given with --target-ref: the documented
    commands copy the repository at the ref and point inside the copy."""
    mono = tmp_path / "mono"
    (mono / "packages" / "auth").mkdir(parents=True)
    (mono / "packages" / "auth" / "old.ts").write_bytes(b"export const v = 1;\n")
    _git(mono, "init", "-q")
    _git(mono, "add", "-A")
    _git(mono, "commit", "-qm", "v1")
    _git(mono, "tag", "v1.0.0")
    (mono / "packages" / "auth" / "new.ts").write_bytes(b"export const v = 2;\n")
    _git(mono, "add", "-A")
    _git(mono, "commit", "-qm", "v2")
    local = _section(_read(SCAN_ROOT), "- **A local path with a ref:**", "- **A remote path:**")
    show, clone = _bash_lines(local)
    run_dir = _run_dir(tmp_path)
    path = (mono / folder).as_posix()
    printed = subprocess.run(shlex.split(show.replace("{path}", path)), capture_output=True, timeout=60)
    assert printed.returncode == 0, printed.stderr
    top, prefix = (printed.stdout.decode("utf-8").splitlines() + [""])[:2]
    clone = (clone.replace("{ref}", "v1.0.0").replace("{the first line it printed}", top)
             .replace("{run_dir}", run_dir.as_posix()).replace("{i}", "1"))
    proc = subprocess.run(shlex.split(clone), capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "followed by the second line without its trailing slash" in local
    scan_root = run_dir / "source-1" / prefix.rstrip("/") if prefix else run_dir / "source-1"
    auth = scan_root / "old.ts" if folder != "." else scan_root / "packages" / "auth" / "old.ts"
    assert auth.is_file() and not (auth.parent / "new.ts").exists()


# --------------------------------------------------------------------------
# One gate per step, and every headless default is recorded (#599, #594)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", CHAIN, ids=[p.stem for p in CHAIN])
def test_each_step_keeps_one_gate(path):
    text = _read(path)
    assert text.count("**GATE [default:") == 1, path.name
    for gone in ("Wait for user feedback", "Wait for explicit final confirmation", "This is your final confirmation",
                 "Save scan results", "Save classifications", "Save findings", "Save recommendations"):
        assert gone not in text, (path.name, gone)


GATE_DECISION = re.compile(r'stage `\{run_dir\}/decision\.json` as `(\{"gate": "([a-z.-]+)".*?\})`, then run')


def _decision(path: Path) -> tuple[str, str]:
    text = _read(path)
    m = GATE_DECISION.search(text)
    assert m, f"{path.name}: the gate records no decision"
    assert RECORD in [line for line in _bash_lines(text)], path.name
    return m.group(2), m.group(1)


def _fill_decision(template: str) -> dict:
    text = re.sub(r"\[<[^<>]+>\]", '["x"]', template)
    text = re.sub(r"<[^<>]+>", "1", text)
    return json.loads(text)


def test_every_gate_decision_reaches_the_envelope(tmp_path):
    """Each documented decision passes the schema's gate enum (the emitter
    checks it with --workflow) and a later halt still reports it."""
    run_dir = _run_dir(tmp_path)
    gates = []
    for path in CHAIN:
        gate, template = _decision(path)
        decision = _fill_decision(template)
        assert decision["reason"].startswith("headless: "), path.name
        (run_dir / "decision.json").write_bytes(json.dumps(decision).encode("utf-8"))
        proc = _run(RECORD, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
        assert proc.returncode == 0, (path.name, proc.stderr)
        gates.append(gate)
    (run_dir / "halt.json").write_bytes(json.dumps(
        {"phase": "generate-briefs:5", "reason": "x", "halt_reason": "write-failed"}).encode("utf-8"))
    proc = _run(HALT, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    [line] = proc.stderr.decode("utf-8").splitlines()
    envelope = json.loads(line[len(PREFIX):])
    assert not list(Draft202012Validator(SCHEMA).iter_errors(envelope))
    assert [d["gate"] for d in envelope["headless_decisions"]] == gates


def test_a_gate_the_schema_does_not_know_is_refused(tmp_path):
    run_dir = _run_dir(tmp_path)
    (run_dir / "decision.json").write_bytes(json.dumps(
        {"gate": "recommend.final-confirmation", "default_action": "C", "taken_action": "C",
         "reason": "headless: x"}).encode("utf-8"))
    proc = _run(RECORD, {"emitEnvelopeHelper": str(EMITTER), "run_dir": str(run_dir)})
    assert proc.returncode != 0


def test_the_gate_enum_is_the_set_of_gates_the_steps_record():
    named = set()
    for path in REFS.glob("*.md"):
        named |= set(re.findall(r'\{"gate": "([a-z.-]+)"', _read(path)))
    assert named == set(GATE_ENUM)
    contract = next(line for line in _read(HEADLESS).splitlines() if line.startswith("- `headless_decisions`"))
    for gate in GATE_ENUM:
        assert f"`{gate}`" in contract, gate


def test_recommend_takes_every_decision_before_its_one_menu():
    text = _read(RECOMMEND)
    assert "Do not proceed without explicit confirmation for each unit" not in text
    headless = _section(text, "**Headless** (`{headless_mode}` true)", '"**Recommendations for')
    assert "Take the §7 GATE default now" in headless and "continue at §6" in headless
    menu = _section(text, "### 7. Present MENU OPTIONS", None)
    assert menu.index("**Confirmed for brief generation:**") < menu.index("**Select an Option:**")
    for option in ("- IF A:", "- IF P:", "- IF D:"):
        line = next(line for line in menu.splitlines() if line.startswith(option))
        assert "redo §6" in line or "as [A] does" in line, option
    # Only [C] marks the step complete: a run cancelled at the menu resumes here.
    save = _section(text, "### 6. Append to Report", "### 7.")
    assert "stepsCompleted" not in save and "only once" not in save
    leave = next(line for line in menu.splitlines() if line.startswith("- IF C:"))
    assert "append `recommend`" in leave and "then execute {nextStepFile}" in leave
    rules = _section(_read(GENERATE), "## Rules", "## MANDATORY SEQUENCE")
    assert "re-ask for confirmations" not in rules
    assert "the §4 preview confirms only the write" in rules


def test_the_stages_table_states_the_gates():
    text = _read(SKILL)
    row = next(line for line in text.splitlines() if line.startswith("| 1b |"))
    assert "| Always |" not in row
    gates = next(line for line in text.splitlines() if line.startswith("| **Gates** |"))
    assert "one per step" in gates and "`headless_decisions`" in gates
    assert "None in auto mode" not in gates
    assert "Auto mode: only the step 1a coexistence gate (default [A]longside)" in gates
    assert "| **Headless** |" not in text
    inputs = next(line for line in text.splitlines() if line.startswith("| **Headless inputs** |"))
    assert "written into every brief; not `[auto]`, which pins with `--pin`" in inputs
    assert "not with `--target-ref`, and not `[auto]`" in inputs


def test_every_interactive_menu_can_cancel():
    """Step 4 offers [X] like steps 2, 3 and 5, and the exit-6 row says so."""
    menu = _section(_read(MAP), "### 6. Present the Findings and Confirm", "### 7.")
    assert "| [X] Cancel and exit" in menu
    assert '- IF X: HARD HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `map-and-detect:6`)' in menu
    row = next(line for line in _read(HEADLESS).splitlines() if line.startswith("| 6 "))
    assert "steps 2/3/4/5/6" in row


def test_a_headless_brief_failing_a_semantic_check_halts():
    """No one corrects a 3b failure in a headless run: it halts as 3a does."""
    checks = _section(_read(GENERATE), "**3b. Semantic cross-checks**", "### 4.")
    line = next(line for line in checks.splitlines() if line.startswith("- In headless mode"))
    assert 'HARD HALT (exit code 4, `halt_reason: "write-failed"`, phase `generate-briefs:3`' in line
    assert "a brief still failing a 3b check" in line


# --------------------------------------------------------------------------
# [D] loads one file that declares its own helpers (#602 item 2)
# --------------------------------------------------------------------------


def test_both_d_handlers_load_the_discover_file():
    for path in (MAP, RECOMMEND):
        text = _read(path)
        assert "discoverFile: 'references/discover-additional-source.md'" in _frontmatter(text), path.name
        [handler] = [line for line in text.splitlines() if line.startswith("- IF D:")]
        assert "execute {discoverFile}" in handler, path.name
    for path in REFS.glob("*.md"):
        text = _read(path)
        for by_number in ("from step 02", "from step 03", "same logic as step 04", "subset of steps"):
            assert by_number not in text, (path.name, by_number)


def test_the_discover_file_declares_every_helper_it_calls():
    text = _read(DISCOVER)
    declared = set(re.findall(r"^([A-Za-z]+)ProbeOrder:", _frontmatter(text), flags=re.M))
    called = {m for m in re.findall(r"\{([A-Za-z]+)Helper\}", text.split("\n---\n", 1)[1])} - {"emitEnvelope"}
    assert called == declared, (called ^ declared)
    for needle in ("derive-name --from -", '--tree-dir "{run_dir}/unit-trees/{i}"', "{countImportsHelper} count",
                   "{findCyclesHelper} find", "{pairIntersectHelper} intersect", "SKF_COMPOSITE_NAMES",
                   "Return to the menu that loaded this file", "a headless run never takes [D]"):
        assert needle in text, needle


def test_one_statement_of_the_per_unit_export_mapping():
    """map-and-detect and [D] run the same export mapping from one file, so
    the discovered units get the same API surface, script check and extras."""
    for path in (MAP, DISCOVER):
        text = _read(path)
        assert "unitExportsFile: 'references/map-unit-exports.md'" in _frontmatter(text), path.name
        assert "execute {unitExportsFile}" in text, path.name
    contract = '"scripts_assets": {"scripts": [], "assets": []}'
    holders = [p.name for p in REFS.glob("*.md") if contract in _read(p)]
    assert holders == [UNIT_EXPORTS.name], holders
    shared = _read(UNIT_EXPORTS)
    for needle in ("**No recipe for the unit's language:**", "entry_point_diff.extraction_gaps[]", "file_issues[]",
                   "**Tier-aware extras:**", "Script/asset presence", "**Graceful degradation.**",
                   'uv run {checkUnitRecordsHelper} --dir "{run_dir}/unit-records"',
                   "`files_count` is the unit's file count the loading file gave"):
        assert needle in shared, needle
    assert "the `files_count` of its §3 record" in _read(DISCOVER)


def test_the_discover_file_leaves_map_and_detect_sections_to_its_section_7():
    """From map-and-detect the placeholders are still there: §7 writes both
    sections with the new units; from recommend the rows are appended."""
    merge = _section(_read(DISCOVER), "### 6. Merge Into the Report and Return", None)
    by_map = next(line for line in merge.splitlines() if line.startswith("- **Loaded by map-and-detect:**"))
    by_recommend = next(line for line in merge.splitlines() if line.startswith("- **Loaded by recommend:**"))
    assert "write nothing more" in by_map and "§7 writes both sections" in by_map
    assert "Export Map" in by_recommend and "Integration Points" in by_recommend
    assert "refs: {add the new path: its ref, when §1 gave it one}" in merge
    handler = next(line for line in _read(MAP).splitlines() if line.startswith("- IF D:"))
    assert "§7 writes the Export Map and Integration Points with them" in handler


def test_the_discover_file_leaves_out_an_aggregating_root():
    scan = _section(_read(DISCOVER), "### 2. Scan It", "### 3.")
    assert "leave out a folder whose manifest only gathers the member folders below it" in scan
    assert "`.` stays a candidate only when it holds code of its own" in scan


# --------------------------------------------------------------------------
# The goal defers units before the fan-out, interactively only (#602 item 5)
# --------------------------------------------------------------------------


def test_an_interactive_run_defers_what_the_goal_leaves_out():
    defer = _section(_read(IDENTIFY), "### 5. Defer What the Goal Leaves Out", "### 6.")
    for needle in ("Interactive runs only", "`intent_hint` is not empty", "`deferred`",
                   "A headless run defers nothing", "stay in the classification table"):
        assert needle in defer, needle
    menu = _section(_read(IDENTIFY), "### 6. Present the Classifications and Confirm", "### 7.")
    assert "restore any unit" in menu and "restoring a deferred unit" in menu
    fan_out = _section(_read(MAP), "### 1. Load Context", "### 3.")
    assert "is not analyzed here" in fan_out and "leaving out the deferred units" in fan_out
    row = next(line for line in _read(SKILL).splitlines() if line.startswith("| **Headless inputs** |"))
    assert "a headless run never" in row and "`--intent-hint <text>`" in row


# --------------------------------------------------------------------------
# step-auto-scope carved, hints honoured, warnings recorded (#600, #594, W4)
# --------------------------------------------------------------------------


def test_the_auto_branches_load_from_their_own_files():
    text = _read(AUTO)
    front = _frontmatter(text)
    for key, path in (("coexistenceFile", COEXIST), ("splitFile", SPLIT), ("corporaFile", CORPORA)):
        assert f"{key}: 'references/{path.name}'" in front, key
        assert f"execute {{{key}}}" in text, key
        assert path.exists()
    for gone in ("### 6b.", "### 4a.", "### 5a.", "### 6a.", "languageCorporaProbeOrder", "[A]longside \u2014 ",
                 "## Companion Corpora", "Decomposition ({N} skills)"):
        assert gone not in text, gone
    for path in (COEXIST, SPLIT, CORPORA):
        assert path.name in _read(SKILL), path.name


def test_the_auto_path_reads_the_hints():
    init = _section(_read(INIT), "### 2b. Auto Mode Check", "### 3.")
    assert "intent_hint: '{intent_hint}'" in init and "scope_hint: '{scope_hint}'" in init
    text = _read(AUTO)
    assert "`scope_hint` (the folders or packages to focus on or skip) and `intent_hint`" in text
    assert "**Apply `scope_hint`** when it is not empty" in text
    assert "the facets it names are the ones in scope" in text
    assert "worded toward `intent_hint`" in text and "worded toward `intent_hint`" in _read(SPLIT)
    assert "outside the folders `scope_hint` focuses on" in _read(SPLIT)


def test_no_home_path_in_the_auto_routing():
    """`~` already covers `~/...`: the routing reads the same without a home path."""
    text = _read(AUTO)
    assert "~/" not in text
    assert "| Starts with `/`, `./`, or `~` | Local filesystem path |" in text
    assert "(starts with `/`, `./`, or `~`, or is an existing directory)" in text


def test_the_auto_warnings_reach_the_run_sink():
    text = _read(AUTO)
    exit2 = next(line for line in text.splitlines() if line.startswith("- **Exit 2**: record the warning"))
    assert "--warning 'pin_unresolved: " in exit2 and "Log warning" not in text
    split = _read(SPLIT)
    assert "--warning 'coexistence: {name} exists, forging {name}-wiki alongside'" in split


def test_shape_detection_reads_the_scan_envelope_by_file():
    text = _read(AUTO)
    [call] = [line for line in _bash_lines(text) if "{shapeDetectHelper}" in line]
    assert call == ('uv run {shapeDetectHelper} --repo-url "{project_path}" --manifests-file '
                    '"{run_dir}/manifests-1.json" --manifest-dir "{scan_root}" --tree-file "{run_dir}/tree.txt"')
    assert "comma-joined" not in text and "<comma_separated_manifest_paths>" not in text
    assert "--manifests-file" in _read(REFS / "step-shape-detect.md")


def test_no_pointer_to_the_carved_section_6b():
    """The corpora block lives in step-auto-scope-corpora.md now."""
    for path in [*REFS.glob("*.md"), SCRIPTS / "skf-derive-assembly-shape.py"]:
        text = _read(path)
        assert "step-auto-scope.md §6b" not in text, path.name
    assert "step-auto-scope-corpora.md, which step-auto-scope.md §6 loads" in _read(REFS / "step-shape-detect.md")


# --------------------------------------------------------------------------
# customize.toml keeps only what a stage reads (#596)
# --------------------------------------------------------------------------


def test_the_customization_surface_is_what_the_stages_read():
    settings = tomllib.loads(_read(CUSTOMIZE))["workflow"]
    assert set(settings) == {"activation_steps_prepend", "activation_steps_append", "persistent_facts",
                             "analysis_report_template_path", "on_complete"}
    assert (AN / settings["analysis_report_template_path"]).is_file(), "the default names the bundled file"
    every = "".join(_read(p) for p in [SKILL, *REFS.glob("*.md")])
    for gone in ("brief_schema_path", "unit_detection_heuristics_path", "briefSchemaPath",
                 "unitDetectionHeuristicsPath"):
        assert gone not in every, gone
    comments = _read(CUSTOMIZE)
    assert "--result-path=<forge_data_folder>/analyze-source-result-latest.json" in comments
    assert "workflow_warnings" not in comments and "never fails the run" in comments
    assert "right after the customization resolve" in comments
    assert "before the standard activation (uv probe, config load)" not in comments
