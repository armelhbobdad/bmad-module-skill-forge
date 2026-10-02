#!/usr/bin/env python3
"""Pins and fixtures: audit-skill classifies drift from the helper JSON it
saves in the audited version's folder.

#589 (audit part): step 3 saves skf-structural-diff.py's result with `-o` in
this run's stage data folder `{forge_version}/.skf-audit/{timestamp}/`,
looks for relocated exports with ccc over the saved diff's removed[] and
diffs again, and saves the Script/Asset hash comparison beside it; step 4
saves its rows as semantic findings. A compose-mode stack has no source
tree, so step 1 sends it to step 1c, which saves its constituents' freshness
in place of steps 2 to 4. Step 5 projects the saved files with
skf-severity-classify.py and classifies the findings file through a file
path. These tests keep the prose on that contract and run the prose's own
commands against the real helpers:
- 40 line-only changes score MINOR, and 15 added exports grade HIGH and
  route to update-skill however step 3 rolls them up;
- a relocation the snapshot helper adds turns a CRITICAL removal into a
  MEDIUM move on the second diff;
- a signature's quotes reach the classification intact through the findings
  file;
- a stack diff groups by library, and a snapshot without the library is the
  helper error §1 sends back to step 2's file;
- a compose stack whose only change is a drifted constituent takes the
  compose route, grades HIGH and routes to update-skill, where a source diff
  would have read every entry as removed;
- every type and category the prose maps a source to is one the helper
  grades;
- the stage data folder keeps the version folder SKF's own for drop-skill
  and rename-skill, where a bare new name would not.

#589 (audit part, BMad Builder determinism-5): step 3 §5 and step 5 §3
print their tables with the skill's render-drift-tables.py from the saved
JSON, so 15 added exports in one file read as one rollup row of each and
still grade HIGH (test-skf-render-drift-tables.py tests the renderer).

#597 (audit part): init §1 binds one audited version from
skf-skill-inventory.py resolve in every branch, and `{forge_version}` and the
provenance map come from it, so the manifest-lag default [N] reads and writes
the `active` link's version folder, and the gate says when that version has
no provenance map.

#587 (audit part): the drift report's frontmatter holds the run context each
step writes, report.md builds its Provenance table from it, and every run
creates a fresh report.

#599 (audit part, BMad Builder enhancement-8): step 1 §7 shows the
baseline and goes on, stopping for confirmation only when the tier dropped
below the compile tier or the provenance map is more than 90 days old, and
there [X] stops the run (user-cancelled) with the baseline-only report.

#594 and #599 (audit part): the baseline a skill records decides its route.
A skill with no provenance map stops at step 1 (`no-baseline`) and names
Test Skill, since degraded mode had no baseline downstream; a docs-only
skill goes from step 1 to step 5a, whose saved comparison step 5 grades, so
a changed document makes it SIGNIFICANT and routes to update-skill, and a
comparison that reached no document halts instead of scoring CLEAN; a
code-mode stack is re-indexed from the project root and diffed by library
(#589). No stage keeps a by-hand fallback for a helper: On Activation checks
them, and the supplementary checks skip with a note.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
AUDIT = SRC / "skf-audit-skill"
REFS = AUDIT / "references"
SKILL = AUDIT / "SKILL.md"
HEADLESS = REFS / "headless-contract.md"
INIT = REFS / "init.md"
COMPOSE = REFS / "constituent-freshness.md"
DOC_DRIFT = REFS / "doc-drift.md"
RE_INDEX = REFS / "re-index.md"
STRUCTURAL = REFS / "structural-diff.md"
SEMANTIC = REFS / "semantic-diff.md"
SEVERITY = REFS / "severity-classify.md"
REPORT = REFS / "report.md"
TEMPLATE = AUDIT / "assets" / "drift-report-template.md"
SCRIPTS = SRC / "shared" / "scripts"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
DIFF = SCRIPTS / "skf-structural-diff.py"
CLASSIFY = SCRIPTS / "skf-severity-classify.py"
HASH_CONTENT = SCRIPTS / "skf-hash-content.py"
LOAD_PROVENANCE = SCRIPTS / "skf-load-provenance.py"
SNAPSHOT = SCRIPTS / "skf-extraction-snapshot.py"
DETECT_DOCS = SCRIPTS / "skf-detect-docs.py"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
RENDER = AUDIT / "scripts" / "render-drift-tables.py"
# The script each prose placeholder names, for running a prose command.
PROSE_SCRIPTS = {
    "{extractionSnapshotHelper}": SNAPSHOT,
    "{structuralDiffHelper}": DIFF,
    "{severityClassifyHelper}": CLASSIFY,
    "{compareConstituentHashesHelper}": HASH_CONTENT,
    "{skillInventoryHelper}": INVENTORY,
    "{loadProvenanceHelper}": LOAD_PROVENANCE,
    "{compareDocHashesHelper}": DETECT_DOCS,
    "{emitEnvelopeHelper}": EMITTER,
    "{renderDriftTablesScript}": RENDER,
}

STAGE_DATA = "{forge_version}/.skf-audit/{timestamp}"
TIMESTAMP = "20260101-000000"
DIFF_CMD = ('uv run {structuralDiffHelper} "{provenanceMap}" "{extractionSnapshot}" '
            '-o "{auditDataFolder}/structural-diff.json"')
RULES_CMD = "uv run {severityClassifyHelper} --rules --format markdown"
PROJECT_CMD = ('uv run {severityClassifyHelper} --from-diff "{auditDataFolder}/structural-diff.json" '
               '--file-drift "{auditDataFolder}/file-drift.json" '
               '--semantic "{auditDataFolder}/semantic-findings.json" -o "{auditDataFolder}/findings.json"')
COMPOSE_PROJECT_CMD = ('uv run {severityClassifyHelper} --constituents "{auditDataFolder}/constituent-freshness.json" '
                       '-o "{auditDataFolder}/findings.json"')
CLASSIFY_CMD = ('uv run {severityClassifyHelper} "{auditDataFolder}/findings.json" '
                '-o "{auditDataFolder}/severity.json"')
CONSTITUENT_CMD = ('uv run {compareConstituentHashesHelper} compare-constituent-hashes "{provenanceMap}" '
                   '--skills-root "{project-root}" > "{auditDataFolder}/constituent-freshness.json"')
NORMALIZE_CMD = "uv run {loadProvenanceHelper} normalize {provenanceMap}"
RESOLVE_CMD = ('uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill_name} '
               '--forge-data-folder "{forge_data_folder}"')
BINDING_RE = re.compile(r"`(\{[A-Za-z_]+\})` ← `([a-z_.]+)`")
SEMANTIC_RE = re.compile(r"(New Patterns|Changed Conventions|Dependency Shifts|Architectural Changes|"
                         r"Deprecated Patterns) `([a-z_]+)`")
# The run context the drift report's frontmatter carries, by the step that writes it.
RUN_CONTEXT = {
    INIT: ("audited_version", "audited_version_reason", "manifest_version", "docs_only_skill",
           "provenance_map", "provenance_generated_at", "provenance_age_days", "baseline_ref",
           "baseline_commit", "audit_ref", "audit_ref_source", "audit_commit", "latest_tag",
           "remote_head", "upstream_fetch", "upstream_moved", "upstream_ref", "source_tree"),
    RE_INDEX: ("ast_fallback_files",),
    STRUCTURAL: ("applied_transforms",),
}
RUN_CONTEXT_IDS = ["init", "re-index", "structural-diff"]
# Each Provenance row of report.md, with the frontmatter keys it shows.
PROVENANCE_ROWS = {
    "Audit Date": ("date",),
    "Forge Tier": ("forge_tier",),
    "Source Path": ("source_path", "source_tree"),
    "Skill Path": ("skill_path",),
    "Audited Version": ("audited_version", "audited_version_reason", "manifest_version"),
    "Provenance Map": ("provenance_map",),
    "Provenance Age": ("provenance_age_days", "provenance_generated_at"),
    "AST fallback files": ("ast_fallback_files",),
    "Applied Transforms": ("applied_transforms",),
    "Baseline Ref / Commit": ("baseline_ref", "baseline_commit"),
    "Audit Ref / Commit": ("audit_ref", "audit_commit", "audit_ref_source"),
    "Upstream Latest": ("latest_tag", "remote_head", "upstream_fetch"),
    "Upstream Moved": ("upstream_moved", "upstream_ref"),
}

spec = importlib.util.spec_from_file_location("skf_severity_for_audit", CLASSIFY)
classify_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classify_mod)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    section = text[i:j]
    assert section.strip(), f"empty slice between {start!r} and {end!r}"
    return section


def _flow(text: str) -> str:
    """The text with each run of whitespace folded to one space."""
    return re.sub(r"\s+", " ", text)


def _frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", _read(path), re.S)
    assert match, f"{path.name} has no frontmatter"
    return yaml.safe_load(match.group(1))


def _fenced_line(text: str, needle: str) -> str:
    """The one line of a fenced block that holds `needle`."""
    lines = [line.strip() for block in re.findall(r"^```[a-z]*\n(.*?)^```", text, re.M | re.S)
             for line in block.splitlines() if needle in line]
    assert len(lines) == 1, f"expected one fenced line holding {needle!r}, found {lines}"
    return lines[0]


def _run_prose(command: str, values: dict[str, str]) -> subprocess.CompletedProcess:
    """Run a prose command as the step would, with `uv run {xHelper}` as the
    Python running the script and each `{placeholder}` filled in after the
    split, so a Windows path is never read as shell escapes."""
    words = shlex.split(command)
    assert words[:2] == ["uv", "run"] and words[2] in PROSE_SCRIPTS, command
    redirect = None
    if ">" in words:
        at = words.index(">")
        redirect, words = words[at + 1], words[:at]

    def fill(word: str) -> str:
        for name, value in values.items():
            word = word.replace(name, value)
        assert "{" not in word, f"unfilled placeholder in {word!r}"
        return word

    args = [sys.executable, str(PROSE_SCRIPTS[words[2]]), *(fill(w) for w in words[3:])]
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    if redirect is not None:
        Path(fill(redirect)).write_bytes(result.stdout.encode("utf-8"))
    return result


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data, indent=2).encode("utf-8"))
    return path


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _next_workflow(result: dict) -> str | None:
    """report.md §4's rule for nextWorkflow (test_report_counts_come_from_the_saved_classification pins it)."""
    counts = result["by_severity"]
    return "update-skill" if counts["CRITICAL"] > 0 or counts["HIGH"] > 0 else None


def _entry(name: str, file: str, line: int, **extra) -> dict:
    """A provenance-map entry, in the fields create-skill writes."""
    return {"export_name": name, "export_type": "function", "source_file": file, "source_line": line,
            "confidence": "T1", "extraction_method": "ast-grep", **extra}


def _export(name: str, file: str, line: int, **extra) -> dict:
    """A snapshot export, in the fields step 2 writes."""
    return {"name": name, "type": "function", "signature": f"def {name}()", "file": file, "line": line,
            "confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "function_definition",
            **extra}


class Audit:
    """One audit's version folder: the provenance map, the snapshot (none for
    a compose-mode stack) and this run's stage data folder, driven through
    the prose's own commands."""

    def __init__(self, tmp_path: Path, entries: list, exports: list | None, **provenance):
        self.forge_version = tmp_path / "forge" / "demo" / "1.0.0"
        self.data = self.forge_version / ".skf-audit" / TIMESTAMP
        self.provenance = _write_json(self.forge_version / "provenance-map.json",
                                      {"entries": entries, **provenance})
        self.snapshot = self.forge_version / "extraction-snapshot.json"
        if exports is not None:
            _write_json(self.snapshot, {"exports": exports})
        self.data.mkdir(parents=True)
        self.values = {
            "{provenanceMap}": str(self.provenance),
            "{extractionSnapshot}": str(self.snapshot),
            "{auditDataFolder}": str(self.data),
            "{project-root}": str(tmp_path),
        }

    def run(self, path: Path, needle: str, extra: str = "") -> subprocess.CompletedProcess:
        return _run_prose(_fenced_line(_read(path), needle) + extra, self.values)

    def diff(self, extra: str = "") -> dict:
        result = self.run(STRUCTURAL, "-o \"{auditDataFolder}/structural-diff.json\"", extra)
        assert result.returncode in (0, 1), result.stdout + result.stderr
        assert json.loads(result.stdout)["status"] == "ok"
        return _load(self.data / "structural-diff.json")

    def project(self, needle: str = "--from-diff") -> list:
        result = self.run(SEVERITY, needle)
        assert result.returncode == 0, result.stdout + result.stderr
        self.sources = json.loads(result.stdout)["sources"]
        return _load(self.data / "findings.json")

    def classify(self, findings: list | None = None) -> dict:
        if findings is not None:
            _write_json(self.data / "findings.json", findings)
        result = self.run(SEVERITY, '"{auditDataFolder}/findings.json" -o')
        assert result.returncode == 0, result.stdout + result.stderr
        return _load(self.data / "severity.json")

    def render(self, path: Path) -> str:
        """The tables the stage's render command prints."""
        result = self.run(path, "{renderDriftTablesScript} ")
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout


# --------------------------------------------------------------------------
# #589: the stages pass the helpers' JSON through files
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [COMPOSE, STRUCTURAL, SEMANTIC, SEVERITY, REPORT],
                         ids=["constituent-freshness", "structural-diff", "semantic-diff", "severity", "report"])
def test_each_stage_names_this_runs_stage_data_folder(path):
    assert _frontmatter(path)["auditDataFolder"] == STAGE_DATA


def test_structural_diff_saves_the_diff():
    text = _read(STRUCTURAL)
    section = _slice(text, "### 1. Run the Deterministic Export Diff", "### 1b.")
    assert _fenced_line(section, "-o ") == DIFF_CMD
    flow = _flow(section)
    assert 'mkdir -p "{auditDataFolder}"' in flow
    assert "add `--group-by source_library`" in flow
    # No by-hand diff is left to fall back on (BMad Builder architecture-4).
    assert "Never diff them by hand" in flow
    for gone in ("Match by canonicalized export name", "Identify each export by its name and its file together",
                 "Quote style on string defaults", "Hash-prefix normalization"):
        assert gone not in text, gone


def test_a_diff_that_saved_nothing_halts_inside_the_contract():
    """Each exit-2 cause has its handling: the snapshot is fixed and the diff
    run again, a failed write is exit 4, and a map step 1 could read but the
    diff cannot halts as provenance-invalid (exit 3), as step 1 §4 does."""
    flow = _flow(_slice(_read(STRUCTURAL), "### 1. Run the Deterministic Export Diff", "### 1b."))
    assert "Exit `2` saved nothing; act on its `error`:" in flow
    assert ("It names `{extractionSnapshot}` (unreadable, not JSON, or, with `--group-by`, no export with a "
            "`source_library`): step 2 wrote that file, so fix it as re-index §3 describes and run the command "
            "again.") in flow
    assert 'It starts `Cannot write output`: HALT with **exit 4**, `halt_reason: "write-failed"`' in flow
    assert ('Otherwise it names `{provenanceMap}`, which step 1 §4 read: HALT with **exit 3**, '
            '`halt_reason: "provenance-invalid"`') in flow
    assert "Exit `2` is an error that saved nothing" not in flow
    rerun = _flow(_slice(_read(STRUCTURAL), "### 1b.", "### 2."))
    assert "acting on its exit code as §1 does" in rerun
    severity = _flow(_slice(_read(SEVERITY), "### 2. Classify, Score, and Count", "The saved result"))
    assert ('An `error` that starts `Cannot write output` (here or in §1) is a failed write: HALT with '
            '**exit 4**, `halt_reason: "write-failed"`') in severity
    rows = [line for line in _read(HEADLESS).splitlines() if re.match(r"\| 4 +\| write-failure ", line)]
    assert len(rows) == 1 and "step 1c, step 2 §2 and §3, step 3 §1 and step 5 §2" in rows[0], rows


def test_the_helpers_report_what_the_branches_read(tmp_path):
    """The error texts the halts branch on are the ones the helpers print: a
    folder in place of the output file makes the write fail on any system."""
    audit = Audit(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 1)])
    (audit.data / "structural-diff.json").mkdir()
    result = audit.run(STRUCTURAL, "-o \"{auditDataFolder}/structural-diff.json\"")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"].startswith("Cannot write output")
    _write_json(audit.data / "findings.json", [])
    (audit.data / "severity.json").mkdir()
    result = audit.run(SEVERITY, '"{auditDataFolder}/findings.json" -o')
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert "problems" not in out and out["error"].startswith("Cannot write output")


def test_step_3_names_only_the_diff_fields_it_reads_itself(tmp_path):
    """§5's renderer prints every set, so the step names only the fields §1b
    and §6 read, and each is one the helper saves (BMad Builder leanness)."""
    section = _flow(_slice(_read(STRUCTURAL), "The saved diff holds every set §5 renders.", "### 1b."))
    assert ("§1b reads `summary.removed` and the `name` of each `removed[]` entry (an export in the provenance map "
            "but not in the snapshot), and §6 records `applied_transforms`") in section
    audit = Audit(tmp_path, [_entry("a", "a.py", 1)], [_export("b", "b.py", 2)])
    saved = audit.diff()
    assert saved["summary"]["removed"] == 1 and saved["removed"][0]["name"] == "a"
    assert isinstance(saved["applied_transforms"], list)
    structural = _read(STRUCTURAL)
    for gone in ("Read the saved diff from the file:", "An `<entry>` in `added[]` or `removed[]` holds",
                 "### 3. Read Changed Exports from the Diff", "### 3b. Read Provenance Label Differences"):
        assert gone not in structural, gone


def test_the_diff_section_keeps_what_steers_judgment():
    """§2 keeps the facts later steps judge by: a move is no removal, an
    ambiguous name goes to step 5, and two fields are not drift."""
    section = _flow(_slice(_read(STRUCTURAL), "### 2. What the Diff Decides", "### 4b."))
    assert "never from set arithmetic of your own" in section
    assert "A move is **not** a removal." in section
    assert ("**Not drift:** `summary.signature_unverified` counts matched exports whose signature sits in "
            "different fields on the two sides") in section
    assert "`label_changes[]` lists matched exports whose `confidence` or `extraction_method` differs" in section
    assert "Neither is counted in Total Drift Items, and step 5 classifies neither." in section


def test_ambiguous_names_are_shown_and_judged():
    structural = _read(STRUCTURAL)
    section = _flow(_slice(structural, "### 2. What the Diff Decides", "### 4b."))
    assert "**Ambiguous names** (`ambiguous_names[]`)" in section
    assert ("step 5 judges whether a removed and an added entry of one name are one export that "
            "moved") in section
    judged = _flow(_slice(_read(SEVERITY), "2. **Ambiguous names.**", "Keep one finding per item"))
    # Recorded the way skf-severity-classify.py --from-diff describes a judged move.
    assert '`{type: "moved", category: "export", detail: "moved from {removed file:line} to {file:line}"}`' in judged
    assert "without `ambiguous_name`, and the removed finding is deleted" in judged
    assert "ambiguous_name" in classify_mod.__doc__ and "moved from" in classify_mod.__doc__


def test_no_step_echoes_findings():
    for path in sorted(REFS.glob("*.md")):
        text = _read(path)
        assert "echo '" not in text and "{findings_json}" not in text, path.name


def test_severity_classify_projects_the_saved_files():
    text = _read(SEVERITY)
    build = _slice(text, "### 1. Build the Findings File", "### 2.")
    assert _fenced_line(build, "--rules") == RULES_CMD
    assert _fenced_line(build, "--from-diff") == PROJECT_CMD
    assert _fenced_line(build, "--constituents") == COMPOSE_PROJECT_CMD
    flow = _flow(build)
    assert "A compose-mode stack has no structural diff" in flow
    assert "the helper skips that file, and its summary line's `sources` says which files it read" in flow
    # The helper builds every source's findings: no hand-built source is left.
    assert "3. **The other sources.**" not in text and "Append one finding per item" not in text
    classify = _slice(text, "### 2. Classify, Score, and Count", "### 3.")
    assert _fenced_line(classify, "findings.json") == CLASSIFY_CMD
    flow = _flow(classify)
    assert "**Exit 1 with `problems[]`:**" in flow and "then run the command again" in flow
    assert "`by_severity` sums to `total_items`" in flow
    # The rule table replaces the hand-kept category list.
    for gone in ("`optional_parameter`, `function` (for a move)", "Gather every drift item already recorded",
                 "however step 3 rendered them", "so a `detail` that quotes a signature arrives intact"):
        assert gone not in text, gone
    # §3's renderer prints the Total from total_items; no hand template is left.
    assert "| **Total** |" not in text
    assert "It prints the section's tables (`--help` lists them)." in _flow(text)


def test_every_pair_the_prose_maps_is_graded():
    """Each fixed type/category pair the helper's projections emit is one it
    grades, and each table of step 4 has a semantic category the helper
    grades. No stage maps a pair by hand any more."""
    fixed = {(f["type"], f["category"]) for f in
             classify_mod.project_diff({"added": [{"name": "a"}], "removed": [{"name": "r"}],
                                        "moved": [{"name": "m"}],
                                        "changed": [{"name": "l", "field": "line"}]})
             + classify_mod.project_file_drift({"added": ["x"], "removed": ["y"],
                                                "changed": [{"path": "z"}]})
             + classify_mod.project_constituents({"drifted": [{}], "missing": [{}]})
             + classify_mod.project_doc_drift({"changed": [{"url": "u"}], "unchanged": [], "fetch_failed": []})
             if "category_choices" not in f}
    for pair in fixed:
        assert pair in classify_mod.PAIRS, pair
    semantic_text = _flow(_slice(_read(SEMANTIC), "Save the same rows to", "### 5."))
    semantic = SEMANTIC_RE.findall(semantic_text)
    assert len(semantic) == 5, semantic
    for _, category in semantic:
        assert ("semantic", category) in classify_mod.PAIRS, category
    headings = re.findall(r"^### ([A-Z][A-Za-z ]+?) \(\{count\}\)$", _read(SEMANTIC), re.M)
    assert len(headings) == 5, headings
    for heading in headings:
        assert any(heading.startswith(name) for name, _ in semantic), heading


def test_the_semantic_rows_are_saved_as_findings():
    section = _flow(_slice(_read(SEMANTIC), "### 4. Compile Semantic Drift Section", "### 5."))
    assert "Save the same rows to `{auditDataFolder}/semantic-findings.json`: step 5 classifies this file" in section
    assert '`{"type": "semantic", "category", "name", "detail", "file", "line", "confidence"}`' in section


def test_constituent_findings_map_as_the_rules_say():
    findings = classify_mod.project_constituents({
        "drifted": [{"skill_name": "a", "skill_path": "skills/a", "stored_hash": "sha256:1",
                     "current_hash": "sha256:2"}],
        "missing": [{"skill_name": "b", "skill_path": "skills/b", "reason": "metadata-not-found"}],
        "skipped_null_hash": [{"skill_name": "c"}], "fresh": [{"skill_name": "d"}]})
    assert [(f["type"], f["category"], f["name"], f["detail"]) for f in findings] == [
        ("changed", "constituent", "a", "metadata.json sha256:1 -> sha256:2"),
        ("removed", "constituent", "b", "metadata-not-found")]
    assert [classify_mod.classify_finding(f) for f in findings] == ["HIGH", "MEDIUM"]
    compose = _flow(_read(COMPOSE))
    assert "Step 5 grades each one HIGH" in compose and "Step 5 grades each one MEDIUM" in compose


def test_rollups_are_rendering_only():
    assert "Keep one finding per item: a rollup belongs to the tables §3 renders" in _read(SEVERITY)
    for path in (STRUCTURAL, SEVERITY):
        text = _read(path)
        assert "A rollup changes no count: the headings and the summary come from the JSON." in text, path.name
        # The renderer's docstring is the one statement of the rollup rule.
        assert "**Rollup.**" not in text, path.name
    assert "Record which groupings were collapsed" not in _read(STRUCTURAL)


def test_report_counts_come_from_the_saved_classification():
    text = _flow(_read(REPORT))
    assert "`{auditDataFolder}/severity.json`, the classification step 5 saved" in text
    assert "`total_items` for **Total**" in text
    assert "`drift_count` (the saved classification's `total_findings`" in text
    assert ("Set `nextWorkflow` to `'update-skill'` when the saved classification's `by_severity.CRITICAL` "
            "or `by_severity.HIGH` is above 0") in text


@pytest.mark.parametrize("path", sorted(REFS.glob("*.md")), ids=lambda p: p.name)
def test_no_stage_keeps_a_by_hand_fallback(path):
    """BMad Builder architecture-4 and enhancement-4: On Activation checks
    uv and the shared helpers, so a fallback for a helper that cannot run is
    unreachable, and a hand-made diff, grade or hash is the drift the
    zero-hallucination contract forbids. Each stage halts in the contract or,
    for a supplementary check, skips with a note."""
    text = _read(path)
    for gone in ("cannot execute", "claude.ai web", "hash by hand instead", "classify in the main thread",
                 "fall back to comparing the two lists by hand", "{severityRulesFile}"):
        assert gone not in text, (path.name, gone)


def test_the_supplementary_checks_skip_and_the_rest_halt():
    file_drift = _flow(_slice(_read(STRUCTURAL), "### 4b. Detect Script/Asset Drift", "### Stack-Specific"))
    assert ("**When no candidate resolves, or the command exits non-zero** (delete the file then), skip the check "
            "with a `### Script/Asset Drift: skipped ({the reason})` note") in file_drift
    assert "HALT" not in file_drift
    compose = _flow(_slice(_read(COMPOSE), "### 1. Compare the Constituents' Hashes", "### 2."))
    assert ('If no candidate exists, HALT with **exit 3**, `halt_reason: "helper-missing"`, phase '
            '`constituent-freshness:compare`') in compose
    assert ('If the command exits non-zero, the map\'s constituents cannot be compared: HALT with **exit 3**, '
            '`halt_reason: "provenance-invalid"`') in compose
    assert "severityRulesFile" not in _frontmatter(SEVERITY)


# --------------------------------------------------------------------------
# #589 fixtures: the prose commands, run on real helpers
# --------------------------------------------------------------------------


def test_forty_line_only_changes_score_minor(tmp_path):
    entries = [_entry(f"f{i}", "mod.py", i * 10 + 1) for i in range(40)]
    exports = [_export(f"f{i}", "mod.py", i * 10 + 4) for i in range(40)]
    audit = Audit(tmp_path, entries, exports)
    assert audit.diff()["summary"]["changed"] == 40
    findings = audit.project()
    assert audit.sources == {"diff": 40, "file_drift": None, "semantic": None}
    assert {(f["type"], f["category"]) for f in findings} == {("changed", "location")}
    result = audit.classify()
    assert result["drift_score"] == "MINOR"
    assert result["by_severity"]["LOW"] == 40
    assert _next_workflow(result) is None


def test_fifteen_added_exports_grade_high_however_they_render(tmp_path):
    """Step 3 renders these as one rollup row; step 5 classifies the saved
    diff, one finding per export, and renders them as one row again."""
    audit = Audit(tmp_path, [], [_export(f"g{i}", "api/routes.py", i + 1) for i in range(15)])
    audit.diff()
    tables = audit.render(STRUCTURAL)
    # The diff lists exports by name, and a rollup row shows the first three.
    assert "### Added Exports (15)" in tables
    assert "| 15 exports (rep: `g0`, `g1`, `g10`, …) | function | n/a | `api/routes.py` | T1 |" in tables
    assert "| **Total Drift Items** | 15 |" in tables
    result = audit.classify(audit.project())
    assert result["by_severity"]["HIGH"] == 15
    assert result["total_findings"] == result["total_items"] == 15
    assert result["drift_score"] == "SIGNIFICANT"
    assert _next_workflow(result) == "update-skill"
    tables = audit.render(SEVERITY)
    assert "**Overall Drift Score: SIGNIFICANT**" in tables and "### HIGH (15)" in tables
    assert "| 1 | added in `api/routes.py` (×15; rep: `g0`, `g1`, `g10`, …) | structural |" in tables
    assert "| **Total** | 15 |" in tables


def test_a_relocated_export_becomes_a_move(tmp_path):
    """§1b: the runner's find over the candidates, added to the snapshot by
    the prose's relocate command, then the same diff again."""
    audit = Audit(tmp_path, [_entry("keep", "pkg/a.py", 1), _entry("parse", "pkg/a.py", 9)],
                  [_export("keep", "pkg/a.py", 1)])
    first = audit.diff()
    assert [r["name"] for r in first["removed"]] == ["parse"]
    assert audit.classify(audit.project())["drift_score"] == "CRITICAL"
    _write_json(audit.data / "relocations.json", {"status": "ok", "exports": [
        {"export_name": "parse", "source_file": "pkg/util/parsing.py", "source_line": 3, "export_type": "function",
         "signature": "def parse(text)", "confidence": "T1", "extraction_method": "ast-grep"},
        {"export_name": "unrelated", "source_file": "pkg/util/parsing.py", "source_line": 9}]})
    section = _slice(_read(STRUCTURAL), "### 1b.", "### 2.")
    (relocate,) = [line.strip() for line in section.splitlines() if line.strip().startswith(
        "uv run {extractionSnapshotHelper} relocate ")]
    result = _run_prose(relocate, audit.values)
    assert (result.returncode, json.loads(result.stdout)["added"]) == (0, 1), result.stdout + result.stderr
    second = audit.diff()
    assert second["removed"] == [] and [m["name"] for m in second["moved"]] == ["parse"]
    result = audit.classify(audit.project())
    (finding,) = result["findings"]
    assert (finding["type"], finding["category"], finding["severity"]) == ("moved", "export", "MEDIUM")
    assert finding["detail"] == "moved from pkg/a.py:9 to pkg/util/parsing.py:3"
    assert _next_workflow(result) is None


def test_a_quoted_signature_reaches_the_classification_intact(tmp_path):
    """The findings travel by file path, so the single quotes the diff writes
    into a signature's string default survive, where `echo '<JSON>'` broke."""
    audit = Audit(tmp_path, [_entry("parse", "pkg/a.py", 3, signature='def parse(mode: str = "fast")')],
                  [_export("parse", "pkg/a.py", 3, signature="def parse(mode: str = 'fast', label: str = 'x')")])
    audit.diff()
    (projected,) = audit.project()
    assert projected["detail"] == ("signature: def parse(mode: str = 'fast') -> "
                                   "def parse(mode: str = 'fast', label: str = 'x')")
    (classified,) = audit.classify()["findings"]
    assert (classified["detail"], classified["severity"]) == (projected["detail"], "CRITICAL")


def test_saved_script_asset_and_semantic_files_are_findings(tmp_path):
    """file-drift.json (step 3 §4b) and semantic-findings.json (step 4) reach
    the findings file through the same command as the diff."""
    audit = Audit(tmp_path, [_entry("a", "a.py", 1)], [_export("a", "a.py", 1)])
    audit.diff()
    _write_json(audit.data / "file-drift.json", {
        "added": ["scripts/new.sh"], "removed": [], "changed": [],
        "stats": {"added": 1, "removed": 0, "changed": 0, "unchanged": 2}})
    _write_json(audit.data / "semantic-findings.json", [
        {"type": "semantic", "category": "convention", "name": "error handling", "detail": "now raises",
         "file": "a.py", "line": 4, "confidence": "T2"}])
    findings = audit.project()
    assert audit.sources == {"diff": 0, "file_drift": 1, "semantic": 1}
    assert [(f["type"], f["category"]) for f in findings] == [("added", "file"), ("semantic", "convention")]
    result = audit.classify()
    assert (result["drift_score"], result["by_severity"]["MEDIUM"]) == ("SIGNIFICANT", 2)


def test_a_stack_diff_groups_by_library(tmp_path):
    """§1 with --group-by source_library over the snapshot step 2 tags."""
    section = _flow(_slice(_read(STRUCTURAL), "### 1. Run the Deterministic Export Diff", "### 1b."))
    assert "For a stack skill with v2 provenance, add `--group-by source_library`" in section
    entries = [_entry("parse", "a/index.ts", 3, source_library="lib-a"),
               _entry("parse", "b/index.ts", 3, source_library="lib-b"),
               _entry("gone", "b/util.ts", 9, source_library="lib-b")]
    exports = [_export("parse", "a/index.ts", 3, source_library="lib-a"),
               _export("parse", "b/index.ts", 5, source_library="lib-b")]
    audit = Audit(tmp_path, entries, exports, provenance_version="2.0", skill_type="stack",
                  libraries=["lib-a", "lib-b"])
    diff = audit.diff(" --group-by source_library")
    assert diff["group_by"] == "source_library"
    assert {g["source_library"]: (g["summary"]["removed"], g["summary"]["changed"]) for g in diff["groups"]} == {
        "lib-a": (0, 0), "lib-b": (1, 1)}
    assert [(r["source_library"], r["name"]) for r in diff["removed"]] == [("lib-b", "gone")]
    findings = audit.project()
    assert sorted((f["source_library"], f["type"], f["category"]) for f in findings) == [
        ("lib-b", "changed", "location"), ("lib-b", "removed", "export")]


def test_a_stack_snapshot_without_its_library_is_sent_back_to_step_2(tmp_path):
    """The helper error names the snapshot, the file §1 has step 2's fix applied to."""
    entries = [_entry("parse", "a/index.ts", 3, source_library="lib-a")]
    audit = Audit(tmp_path, entries, [_export("parse", "a/index.ts", 3)], provenance_version="2.0",
                  skill_type="stack", libraries=["lib-a"])
    result = audit.run(STRUCTURAL, "-o \"{auditDataFolder}/structural-diff.json\"", " --group-by source_library")
    assert result.returncode == 2
    error = json.loads(result.stdout)["error"]
    assert str(audit.snapshot) in error and "source_library" in error
    assert not (audit.data / "structural-diff.json").exists()
    worker = _flow(_slice(_read(RE_INDEX), "### 3. Extract Current Exports", "### 4."))
    assert ("the snapshot helper gives each one its file's `source_library` from the provenance map (the map "
            "`normalize` returns as `source_library_by_file`)") in worker
    assert "looked up once per file in the provenance map's `entries[]`" not in worker


# --------------------------------------------------------------------------
# #589: a compose-mode stack takes the compose route (step 1c)
# --------------------------------------------------------------------------


def _link_active(active_link: Path, version: str) -> None:
    """active -> version, with the junction fallback of skf-atomic-write.py on
    a Windows host that does not grant the symlink privilege."""
    try:
        active_link.symlink_to(version)
        return
    except OSError as e:
        if os.name != "nt" or getattr(e, "winerror", None) not in (1314, 5):
            raise
        target = (active_link.parent / version).resolve()
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(active_link), str(target)],
                                capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            raise OSError(f"junction fallback failed: {result.stderr or result.stdout}") from e


def _constituent(skills: Path, name: str, metadata: bytes) -> dict:
    """A constituent skill on disk, and its provenance record hashed from `metadata`."""
    package = skills / name / "1.0.0" / name
    package.mkdir(parents=True)
    (package / "metadata.json").write_bytes(metadata)
    _link_active(skills / name / "active", "1.0.0")
    return {"skill_name": name, "skill_path": f"skills/{name}/", "version": "1.0.0",
            "composed_at": "2026-01-01T00:00:00Z",
            "metadata_hash": "sha256:" + hashlib.sha256(metadata).hexdigest()}


def _compose_entries() -> list:
    """Entries in create-stack-skill's compose-mode variant: records of the
    constituent skills, with no source tree behind them."""
    return [
        {"export_name": "connect", "export_type": "function", "source_library": "lib-fresh", "params": [],
         "return_type": "Connection", "source_file": "src/db.ts", "source_line": 12, "confidence": "T1",
         "extraction_method": "compose-from-skill", "signature_source": "T1"},
        {"export_name": "retry", "export_type": "function", "source_library": "lib-moved-on", "params": ["fn"],
         "return_type": "Promise", "source_file": "src/retry.ts", "source_line": 3, "confidence": "T1-low",
         "extraction_method": "compose-from-skill", "signature_source": "T1-low"},
    ]


def _compose_map(constituents: list) -> dict:
    """The rest of a compose-mode map: null source anchors and constituents[]."""
    return {"provenance_version": "2.0", "skill_name": "app-stack", "skill_type": "stack",
            "source_repo": None, "source_commit": None, "source_ref": None,
            "generated_at": "2026-01-01T00:00:00Z",
            "integrations": [{"libraries": ["lib-fresh", "lib-moved-on"], "pattern_type": "provider-consumer",
                              "detection_method": "architecture_co_mention", "co_import_files": [],
                              "confidence": "T1-low"}],
            "constituents": constituents}


def test_init_sends_a_compose_stack_around_the_source_tree():
    init = _read(INIT)
    assert _frontmatter(INIT)["composeStepFile"] == COMPOSE.name
    assert _frontmatter(COMPOSE)["nextStepFile"] == "severity-classify.md"
    assert NORMALIZE_CMD in _slice(init, "### 4. Load Provenance Map", "### Stack Skill Detection")
    assert "`{compose_mode_stack}`: stack-skill flags" in init
    detection = _flow(_slice(init, "### Stack Skill Detection", "### 5."))
    assert "If `{compose_mode_stack}` is true" in detection
    assert "so §5 and §5b skip, and §7 then loads `{composeStepFile}` (step 1c)" in detection
    source = _flow(_slice(init, "### 5. Resolve Source Path", "### 5b."))
    assert ("**A compose-mode stack** (`{compose_mode_stack}`) has no source tree to resolve: skip this "
            "section, and §5b skips too.") in source
    upstream = _flow(_slice(init, "### 5b. Detect Upstream Drift", "**Otherwise**"))
    assert ('**A compose-mode stack** (`{compose_mode_stack}`) has no source tree: skip this section with '
            '`upstream_fetch = "skipped: compose-mode stack"`') in upstream
    confirm = _flow(_slice(init, "### 7. Present Baseline Summary", "**GATE"))
    assert "execute `{nextStepFile}`, or `{composeStepFile}` when `{compose_mode_stack}` is true" in confirm
    stages = _slice(_read(SKILL), "## Stages", "## Invocation Contract")
    assert "| 1c | Constituent Freshness (compose-mode stacks only) | references/constituent-freshness.md | Yes |" in (
        stages)
    assert "it replaces stages 2 to 4 for a compose-mode stack" in stages


def test_the_constituent_check_lives_in_the_compose_stage():
    init = _read(INIT)
    assert "compare-constituent-hashes" not in init and "compareConstituentHashesProbeOrder" not in init
    structural = _read(STRUCTURAL)
    assert "compare-constituent-hashes" not in structural and "### 4c." not in structural
    assert "compareConstituentHashesProbeOrder" not in _frontmatter(STRUCTURAL)
    assert "A compose-mode stack never reaches this step" in structural
    # Integration drift had no saved JSON and no classifier category: it is gone (#589).
    assert "**Integration drift:**" not in structural
    compose = _read(COMPOSE)
    assert _fenced_line(compose, "compare-constituent-hashes") == CONSTITUENT_CMD
    assert 'mkdir -p "{auditDataFolder}"' in compose
    assert "compareConstituentHashesProbeOrder" in _frontmatter(COMPOSE)
    assert "### Constituent Freshness (drifted {stats.drifted}" in compose
    assert "**Status:** Skipped: a compose-mode stack has no source tree to compare" in compose
    template = _read(TEMPLATE)
    assert "Constituent Freshness (compose-mode stacks)" in template
    assert "each drifted (HIGH) or missing (MEDIUM) one is a finding" in template


def test_a_drifted_constituent_alone_grades_high(tmp_path):
    """A compose stack whose only change is one constituent's metadata.json,
    run through the route the prose takes: normalize, step 1c, step 5."""
    skills = tmp_path / "skills"
    fresh = _constituent(skills, "lib-fresh", b'{"name": "lib-fresh", "version": "1.0.0"}\n')
    drifted = _constituent(skills, "lib-moved-on", b'{"name": "lib-moved-on", "version": "1.0.0"}\n')
    (skills / "lib-moved-on" / "1.0.0" / "lib-moved-on" / "metadata.json").write_bytes(
        b'{"name": "lib-moved-on", "version": "1.1.0"}\n')
    unhashed = {"skill_name": "lib-cascade", "skill_path": "skills/lib-cascade/", "metadata_hash": None}
    audit = Audit(tmp_path, _compose_entries(), None, **_compose_map([fresh, drifted, unhashed]))
    normalized = _run_prose(NORMALIZE_CMD, audit.values)
    assert normalized.returncode == 0, normalized.stderr
    flags = json.loads(normalized.stdout)
    assert (flags["is_stack_skill"], flags["compose_mode_stack"], flags["source_root"]) == (True, True, None)
    result = audit.run(COMPOSE, "compare-constituent-hashes")
    assert result.returncode == 0, result.stderr
    freshness = _load(audit.data / "constituent-freshness.json")
    assert [d["skill_name"] for d in freshness["drifted"]] == ["lib-moved-on"]
    assert freshness["skipped_null_hash"] == [{"skill_name": "lib-cascade"}]
    findings = audit.project("--constituents")
    assert audit.sources == {"constituents": 1}
    assert [(f["type"], f["category"], f["name"]) for f in findings] == [
        ("changed", "constituent", "lib-moved-on")]
    classified = audit.classify()
    assert classified["by_severity"]["HIGH"] == 1 and classified["total_findings"] == 1
    assert classified["drift_score"] == "SIGNIFICANT"
    assert _next_workflow(classified) == "update-skill"
    # The route never diffs: steps 2 to 4 do not run for a compose-mode stack.
    assert not (audit.data / "structural-diff.json").exists() and not audit.snapshot.exists()


def test_a_source_diff_would_read_a_compose_stack_as_removed(tmp_path):
    """Why the route exists: with no source tree, a re-index finds nothing,
    and the diff reads every compose-time entry as removed (CRITICAL)."""
    audit = Audit(tmp_path, _compose_entries(), [], **_compose_map([]))
    assert audit.diff()["summary"]["removed"] == 2
    assert audit.classify(audit.project())["drift_score"] == "CRITICAL"


def test_a_missing_constituent_grades_below_a_drifted_one(tmp_path):
    missing = {"skill_name": "lib-gone", "skill_path": "skills/lib-gone/", "metadata_hash": "sha256:" + "0" * 64}
    audit = Audit(tmp_path, _compose_entries(), None, **_compose_map([missing]))
    assert audit.run(COMPOSE, "compare-constituent-hashes").returncode == 0
    freshness = _load(audit.data / "constituent-freshness.json")
    assert [m["reason"] for m in freshness["missing"]] == ["metadata-not-found"]
    classified = audit.classify(audit.project("--constituents"))
    assert classified["by_severity"] == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 1, "LOW": 0}
    assert _next_workflow(classified) is None


# --------------------------------------------------------------------------
# #589: the stage data folder keeps the version folder SKF's own
# --------------------------------------------------------------------------


def _stage_files() -> set[str]:
    names = set()
    for path in (COMPOSE, STRUCTURAL, SEMANTIC, SEVERITY, REPORT):
        names |= set(re.findall(r"\{auditDataFolder\}/([\w.-]+\.json)", _read(path)))
    assert {"structural-diff.json", "findings.json", "severity.json", "file-drift.json",
            "constituent-freshness.json", "semantic-findings.json"} <= names, names
    return names


def _audited_skill(tmp_path: Path, stage_files: list[str], bare: list[str]) -> tuple[Path, Path]:
    """A skill `demo` 1.0.0 after two audits wrote their outputs."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    package = skills / "demo" / "1.0.0" / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_bytes(b"---\nname: demo\ndescription: Demo. Use when testing.\n---\n")
    (package / "metadata.json").write_bytes(b'{"name": "demo", "version": "1.0.0", "generated_by": "create-skill"}\n')
    version = forge / "demo" / "1.0.0"
    runs = ("20260101-000000", "20260102-000000")
    names = ["provenance-map.json", "extraction-snapshot.json", "audit-skill-result-latest.json", *bare]
    for run in runs:
        names += [f"drift-report-{run}.md", *(f".skf-audit/{run}/{n}" for n in stage_files)]
    for name in names:
        (version / name).parent.mkdir(parents=True, exist_ok=True)
        (version / name).write_bytes(b"{}\n")
    return skills, forge


@pytest.mark.parametrize("check,key", [("--purge-check", "purge_check"), ("--rename-check", "rename_check")],
                         ids=["purge", "rename"])
def test_the_stage_data_keeps_the_version_skf_owned(tmp_path, check, key):
    skills, forge = _audited_skill(tmp_path, sorted(_stage_files()), bare=[])
    result = subprocess.run([sys.executable, str(INVENTORY), str(skills), "--skill", "demo", check,
                             "--forge-data-folder", str(forge)],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout)[key]
    assert (verdict["verdict"], verdict["forge_ownership"]) == ("ok", "skf"), verdict


def test_a_bare_stage_file_would_block_a_purge(tmp_path):
    """Why the folder's name holds `.skf-`: a bare new name reads as a file SKF did not write."""
    skills, forge = _audited_skill(tmp_path, [], bare=["structural-diff.json"])
    result = subprocess.run([sys.executable, str(INVENTORY), str(skills), "--skill", "demo", "--purge-check",
                             "--forge-data-folder", str(forge)],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    verdict = json.loads(result.stdout)["purge_check"]
    assert verdict["verdict"] == "not-skf-output"
    assert verdict["forge_foreign_entries"] == ["1.0.0/structural-diff.json"]


# --------------------------------------------------------------------------
# #597: one audited version, bound from the helper
# --------------------------------------------------------------------------


def _init_1() -> str:
    return _slice(_read(INIT), "### 1. Get Skill Path", "### 2. Load Forge Tier")


def _bind_list() -> str:
    """§1's list of the values every branch binds from the helper."""
    return _slice(_init_1(), "**Bind** the audited version from the `resolve` object", "§6 writes the audited")


def test_init_binds_the_audited_version_from_the_helper():
    section = _init_1()
    assert _fenced_line(section, " resolve ") == RESOLVE_CMD
    bindings = dict(BINDING_RE.findall(_bind_list()))
    for name, field in {
        "{audited_version}": "chosen_version",
        "{audited_version_reason}": "reason",
        "{manifest_version}": "active_version",
        "{resolved_skill_package}": "skill_package",
        "{forge_version}": "forge_version",
        "{provenanceMap}": "paths.provenance_map.path",
    }.items():
        assert bindings.get(name) == field, name
    flow = _flow(section)
    # [M] and a full path bind a named version through the same helper.
    assert "**[M]** runs the command above again with `--version {active_version}`" in flow
    assert "run the command above with `--version {version}` from the same file" in flow
    assert "run the `resolve` command above again and bind its values anew" in flow
    assert 'Run `uv run {skillInventoryHelper} "{skills_output_folder}" --skill {skill_name}`' in flow
    for reason in ("`manifest-and-link`", "`manifest`", "`link`", "`manifest-lags-link`", "`flat-layout`",
                   "`missing`", "`newest-on-disk`", "`SKILL_NOT_FOUND`", "`DIR_NOT_FOUND`"):
        assert reason in section, reason
    for hand_walk in (".export-manifest.json", "read the `active` symlink", "`generated_at` timestamps",
                      "audit_target_version", "manifest_symlink_drift", "{active_version}/{skill_name}/"):
        assert hand_walk not in section, hand_walk


def test_init_offers_the_skills_when_none_was_named():
    """#594 (audit part): a name or path the invocation gave is used in both
    modes; an interactive run without one offers the SKF skills, a headless
    one halts input-missing."""
    section = _flow(_init_1())
    assert ("A `skill_name` or `skill_path` the invocation supplied answers the question above, and it is not "
            "asked.") in section
    assert ('run `uv run {skillInventoryHelper} "{skills_output_folder}"` and, above the question, list, numbered, '
            'the `name` and `active_version` of each `skills[]` entry whose `skf_skill` is true') in section
    assert ('**No `skill_name` supplied** (neither name nor path given): HALT with **exit 2**, '
            '`halt_reason: "input-missing"`') in section
    # A crashed or missing inventory helper is helper-missing, not a missing skill.
    assert ('A command that prints no JSON crashed (On Activation already checked `uv`): HALT with **exit 3**, '
            '`halt_reason: "helper-missing"`') in section
    assert ('**`skf-skill-inventory.py` missing or crashed** (item 6\'s command with no JSON, or no candidate and '
            'no flat `SKILL.md`): HALT with **exit 3**, `halt_reason: "helper-missing"`') in section


def test_init_loads_the_bound_provenance_map():
    section = _slice(_read(INIT), "### 4. Load Provenance Map", "### Stack Skill Detection")
    assert "Load the provenance map at `{provenanceMap}`, the path §1 bound" in section
    assert "**If `{provenanceMap}` is null**" in section
    assert "{active_version}" not in section and "from file mtime" not in section
    # The baseline facts come from the normalize call.
    for name, field in {"{export_count}": "export_count", "{provenance_generated_at}": "generated_at",
                        "{provenance_age_days}": "age_days"}.items():
        assert f"`{name}` ← `{field}`" in section, name
    baseline = _slice(_read(INIT), "### 7. Present Baseline Summary", "**Analysis plan")
    assert "{provenance_age_days} days" in baseline and "{export_count} exports" in baseline


def test_the_baseline_stops_only_on_doubt():
    """BMad Builder enhancement-8 (#599): every real choice has its own gate
    before §7, so §7 shows the baseline and goes on; it stops only when the
    baseline looks wrong, and there [X] stops the run with the baseline-only
    report. The headless default is unchanged, and the GATE line names the
    gate the Gates row lists, with its options and its [C] default."""
    init = _read(INIT)
    confirm = _flow(_slice(init, "### 7. Present Baseline Summary (Confirm Only on Doubt)", "**GATE"))
    assert "Ready to begin drift analysis?" not in init
    assert ("Display the summary and the plan. When neither doubt below holds, go straight on: load, read the "
            "entire file, and execute") in confirm
    assert "Either of these doubts stops the run here:" in confirm
    assert ("**The tier dropped:** the run takes steps 2 to 4 (neither a compose-mode stack nor a docs-only "
            "skill), and `{current_tier}` (§2) comes before `{original_tier}` (§3) in the order Quick, Forge, "
            "Forge+, Deep. A null `{original_tier}` never counts as a drop.") in confirm
    assert "**The baseline is old:** `{provenance_age_days}` (§4) is above 90." in confirm
    # The number is stated once; each reason once, in the prompt line, by the tool the run lacks.
    assert init.count("90") == 1
    assert ("so it lacks {Quick: ast-grep, so exports are read by eye / Forge: ccc, so an export moved out of the "
            "scan list reads as removed / Forge+: QMD, so no semantic diff runs}, and its drift can reflect the "
            "tools rather than the source.") in confirm
    assert "`[US] Update Skill` (for a stack, `[SS] Create Stack Skill`) refreshes it." in confirm
    assert "- **[C] Continue the audit** (default) - **[X] Stop**, to refresh the baseline first" in confirm
    assert ('**[X]** HALTs with **exit 6**, `halt_reason: "user-cancelled"`, phase `init:baseline-confirm`: '
            '"Audit stopped: `{outputFile}` holds the baseline only.') in confirm
    # §6 wrote the report, so the halt envelope adds its path.
    assert '`"report_path": "{outputFile}"` once §6 wrote the report' in _read(INIT)
    row = _slice(_read(HEADLESS), "| 6    | user-cancelled", "\n")
    assert "step 1 §7 baseline confirm gate `[X]`" in row
    # Both tiers are bound by name: the run's in §2, the compile tier where the metadata is read.
    tier = _flow(_slice(init, "**Apply tier override:**", "\n"))
    assert tier.endswith("log which one set the tier, and bind it as `{current_tier}`.")
    artifacts = _flow(_slice(init, "### 3. Load Skill Artifacts", "### 4."))
    assert ("`{original_tier}`, the tier the skill was compiled at: `forge_tier` when it holds Quick, Forge, "
            "Forge+ or Deep (a stack records it there), else `confidence_tier` when it does (a single skill "
            "records it there), else null") in artifacts
    gate = _slice(init, "**GATE [default: C]**", "\n")
    assert gate.startswith("**GATE [default: C]**: Baseline Confirm Gate [C/X], reached only on a doubt above.")
    assert 'log: "headless: auto-continue past baseline confirmation ({each doubt that holds})"' in gate
    # The other GATE line is §1's Manifest-vs-Symlink Gate, the Gates row's [N/M/X].
    assert init.count("**GATE") == 2 and "**GATE [default: N]**: headless mode auto-selects **[N]**" in init


BASELINE_RECORD = ('uv run {emitEnvelopeHelper} record --workflow skf-audit-skill --run-dir "{run_dir}" --decision '
                   '< "{run_dir}/decision.json"')


@pytest.mark.parametrize("original_tier", ["Forge+", None], ids=["tier-dropped", "no-compile-tier"])
def test_the_headless_baseline_confirm_records_its_decision(tmp_path, original_tier):
    """headless-gate-convention.md: a headless run that continues past a
    baseline doubt records the decision in the run sink, as step 1's other
    gates do, so the envelope's headless_decisions carries the doubt. The
    schema lists the gate, so the emitter's --workflow check takes the record,
    and the evidence holds a null compile tier as JSON null."""
    gate = _slice(_read(INIT), "**GATE [default: C]**", "\n")
    assert BASELINE_RECORD in gate
    # Only the headless auto-decision is recorded: an interactive [C] adds no `headless:` entry.
    assert ('({each doubt that holds})". In headless mode, after that log line, record the decision in the run '
            "sink: stage `{run_dir}/decision.json`") in gate
    staged = re.search(r"stage `\{run_dir\}/decision\.json` as `(\{\"gate\": \"init\.baseline-confirm\".*?\}\})`", gate)
    assert staged, "the decision the gate stages"
    assert "with JSON `null` for an `{original_tier}` that is null" in gate
    reason = "headless: auto-continue past baseline confirmation (the baseline is old)"
    tier = json.dumps(original_tier)
    decision = (staged.group(1).replace('"{original_tier}"', tier).replace("{current_tier}", "Forge")
                .replace("{provenance_age_days}", "120").replace("<the log line>", reason))
    run_dir = tmp_path / "skf-audit-skill-20260101-000000"
    run_dir.mkdir()
    (run_dir / "decision.json").write_bytes(decision.encode("utf-8"))
    # The prose command, its stdin redirect fed by hand.
    words = shlex.split(BASELINE_RECORD.partition(" < ")[0])
    assert words[:3] == ["uv", "run", "{emitEnvelopeHelper}"]
    args = [word.replace("{run_dir}", str(run_dir)) for word in words[3:]]
    done = subprocess.run([sys.executable, str(EMITTER), *args], input=decision.encode("utf-8"),
                          capture_output=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    halt = {"phase": "init:baseline-confirm", "reason": "stopped", "halt_reason": "user-cancelled"}
    envelope = subprocess.run([sys.executable, str(EMITTER), "emit-halt", "--workflow", "skf-audit-skill",
                               "--run-dir", str(run_dir), "--target", "stdout"],
                              input=json.dumps(halt).encode("utf-8"), capture_output=True, timeout=60, check=False)
    assert envelope.returncode == 0, envelope.stderr
    line = envelope.stdout.decode("utf-8").strip()
    [recorded] = json.loads(line[line.index("{"):])["headless_decisions"]
    assert recorded == {"gate": "init.baseline-confirm", "default_action": "C", "taken_action": "C",
                        "reason": reason, "evidence": {"original_tier": original_tier, "current_tier": "Forge",
                                                       "provenance_age_days": 120}}


def _two_versions(tmp_path: Path) -> tuple[Path, Path]:
    """demo 1.0.0 in the export manifest, 1.1.0 behind the `active` link (update-skill ran since)."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in ("1.0.0", "1.1.0"):
        package = skills / "demo" / version / "demo"
        package.mkdir(parents=True)
        (package / "SKILL.md").write_bytes(b"---\nname: demo\ndescription: Demo. Use when testing.\n---\n")
        (package / "metadata.json").write_bytes(
            f'{{"name": "demo", "version": "{version}", "generated_by": "create-skill"}}\n'.encode("utf-8"))
        _write_json(forge / "demo" / version / "provenance-map.json", {"entries": [], "version": version})
    _link_active(skills / "demo" / "active", "1.1.0")
    manifest = {"schema_version": "2", "exports": {"demo": {"active_version": "1.0.0", "versions": {
        "1.0.0": {"status": "active", "last_exported": "2026-01-01T00:00:00Z"}}}}}
    _write_json(skills / ".export-manifest.json", manifest)
    return skills, forge


def _resolve(values: dict[str, str], extra: list[str] | None = None) -> dict:
    result = _run_prose(RESOLVE_CMD + " " + " ".join(extra or []), values)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)["resolve"]


def _bound(resolved: dict) -> dict[str, object]:
    values = {}
    for name, field in BINDING_RE.findall(_bind_list()):
        value = resolved
        for part in field.split("."):
            assert isinstance(value, dict) and part in value, f"the helper prints no `{field}`"
            value = value[part]
        values[name] = value
    return values


def _values(skills: Path, forge: Path) -> dict[str, str]:
    return {"{skills_output_folder}": str(skills), "{skill_name}": "demo", "{forge_data_folder}": str(forge)}


def test_the_default_audits_the_active_links_version_folder(tmp_path):
    """[N], and the headless default: provenance and outputs in the link's version folder."""
    skills, forge = _two_versions(tmp_path)
    bound = _bound(_resolve(_values(skills, forge)))
    assert bound["{audited_version}"] == "1.1.0"
    assert bound["{audited_version_reason}"] == "manifest-lags-link"
    assert Path(bound["{forge_version}"]).as_posix() == (forge / "demo" / "1.1.0").as_posix()
    assert Path(bound["{provenanceMap}"]).as_posix() == (forge / "demo" / "1.1.0" / "provenance-map.json").as_posix()
    assert Path(bound["{resolved_skill_package}"]).as_posix() == (skills / "demo" / "1.1.0" / "demo").as_posix()
    # Every step writes under the bound folder.
    for path in (INIT, COMPOSE, RE_INDEX, STRUCTURAL, SEMANTIC, SEVERITY, REPORT):
        assert _frontmatter(path)["outputFile"] == "{forge_version}/drift-report-{timestamp}.md", path.name


def test_m_audits_the_manifests_version_folder(tmp_path):
    skills, forge = _two_versions(tmp_path)
    bound = _bound(_resolve(_values(skills, forge), ["--version", "1.0.0"]))
    assert (bound["{audited_version}"], bound["{audited_version_reason}"]) == ("1.0.0", "requested")
    assert Path(bound["{provenanceMap}"]).as_posix() == (forge / "demo" / "1.0.0" / "provenance-map.json").as_posix()


def test_the_gate_says_when_the_links_version_has_no_map(tmp_path):
    """A quick-skill version has no provenance map: [N] then audits in
    degraded mode, which the gate and the headless log say."""
    skills, forge = _two_versions(tmp_path)
    (forge / "demo" / "1.1.0" / "provenance-map.json").unlink()
    resolved = _resolve(_values(skills, forge))
    assert resolved["reason"] == "manifest-lags-link"
    assert resolved["paths"]["provenance_map"]["path"] is None
    assert resolved["candidates"]["manifest"]["provenance_map"] is not None
    gate = _flow(_slice(_init_1(), "2. `manifest-lags-link`", "3. `flat-layout`"))
    assert ("When `paths.provenance_map.path` is null but `candidates.manifest.provenance_map` is set") in gate
    assert "so **[N]** stops at §4 with no baseline to audit against" in gate
    assert "**[M]** audits `{active_version}` against its map" in gate
    assert ("so this run stops at step 1 (no-baseline): set skill_path to the {active_version} package to audit "
            "that version against its map.") in gate
    assert "degraded" not in gate


# --------------------------------------------------------------------------
# #587: the run context lives in the drift report's frontmatter
# --------------------------------------------------------------------------


def test_the_template_has_a_slot_for_the_run_context():
    keys = set(_frontmatter(TEMPLATE))
    for slots in RUN_CONTEXT.values():
        assert set(slots) <= keys, set(slots) - keys


@pytest.mark.parametrize("path,slots", list(RUN_CONTEXT.items()), ids=RUN_CONTEXT_IDS)
def test_each_slot_is_written_by_its_step(path, slots):
    text = _read(path)
    if path == INIT:
        writer = _flow(_slice(text, "Create `{outputFile}` from `{templateFile}`:", "If the write fails"))
    else:
        writer = _flow(_slice(text, "Update {outputFile} frontmatter:", "\n"))
    for slot in slots:
        assert f"`{slot}`" in writer, slot


def test_the_provenance_table_reads_the_frontmatter():
    section = _slice(_read(REPORT), "### 3. Add Provenance Section", "**Confidence Legend:**")
    assert "Build the section from the frontmatter of {outputFile}" in section
    rows = dict(re.findall(r"^\| \*\*(.+?)\*\* \| (.+) \|$", section, re.M))
    keys = set(_frontmatter(TEMPLATE))
    for row, fields in PROVENANCE_ROWS.items():
        assert row in rows, row
        for field in fields:
            assert field in keys, field
            assert field in rows[row], (row, field)


def test_no_step_keeps_a_value_no_stage_reads():
    for path in sorted(REFS.glob("*.md")):
        text = _read(path)
        for gone in ("audit_target_version", "manifest_symlink_drift", "split_body",
                     "mapping consumed by `structural-diff.md` §1 to collapse public-API renames"):
            assert gone not in text, (path.name, gone)


def test_every_run_creates_a_fresh_report():
    """With audit_ref in the frontmatter, the old re-audit gate would start
    firing; its [D] and [R] branches read state no stage keeps."""
    init = _read(INIT)
    for gone in ("Re-audit detection", "[F] Fresh audit", "[R] Resume", "Diff Against Prior Report",
                 "prior_findings", "Recent audit found"):
        assert gone not in init, gone
    create = _slice(init, "### 6. Create Drift Report", "### 7.")
    assert create.split("\n", 2)[2].lstrip().startswith("Create `{outputFile}` from `{templateFile}`:")


def test_the_version_note_names_only_bound_values():
    report = _read(REPORT)
    for unbound in ("{skill_group}", "{new_version}", "{baseline_version}", "{audit_version}"):
        assert unbound not in report, unbound
    note = _slice(report, "**Version preservation (non-destructive).**", "\n")
    assert "keeps the audited version (`{audited_version}`) unchanged" in note
    assert "{IF the frontmatter's `audit_ref_source` is `checkout-latest`" in report


def test_init_records_the_fetch_outcome():
    """Every outcome of the one upstream call (#588) records its fetch value,
    and whether upstream moved, for the report and the envelope."""
    upstream = _flow(_slice(_read(INIT), "### 5b. Detect Upstream Drift", "### 6. Create Drift Report"))
    for outcome in ('`upstream_fetch = "skipped: compose-mode stack"`', '`upstream_fetch = "ok"`',
                    '`upstream_fetch = "skipped: {skip_reason}"`', '`upstream_fetch = "failed:{fetch_error}"`',
                    '`upstream_fetch = "failed:helper-unavailable"`'):
        assert outcome in upstream, outcome
    for moved in ("`upstream_moved = true`", "`upstream_moved = false`", "`upstream_moved = null`"):
        assert moved in upstream, moved


# --------------------------------------------------------------------------
# #589: semantic-diff ends its step itself, and every table has a category
# --------------------------------------------------------------------------


def test_a_missing_registry_writes_the_section_before_moving_on():
    section = _flow(_slice(_read(SEMANTIC), "### 2. Query Original Knowledge Context", "### 3."))
    assert "Run item 1 in the main thread, because only the main thread can end this step" in section
    missing = _slice(section, "**Registry entry missing.**", "**Registry entry present but")
    for step in ("Append a `## Semantic Drift` section", "append `'semantic-diff'` to `stepsCompleted`",
                 "auto-proceed to {nextStepFile}"):
        assert step in missing, step
    assert "| Architectural changes | {count} |" in _read(SEMANTIC)


# --------------------------------------------------------------------------
# #589 (BMad Builder architecture-2): a code-mode stack is audited from the
# project root it was scanned from
# --------------------------------------------------------------------------


CODE_MODE_FILES = {"node_modules/lib-a/index.js": "lib-a", "node_modules/lib-b/retry.js": "lib-b"}


def _code_mode_provenance() -> dict:
    """create-stack-skill's code-mode variant: no top-level source_root, one
    commit per repository, each source_file relative to the project root."""
    return {"provenance_version": "2.0", "skill_name": "app-stack", "skill_type": "stack",
            "source_repo": ["https://github.com/acme/lib-a", "https://github.com/acme/lib-b"],
            "source_commit": {"acme/lib-a": "1" * 40, "acme/lib-b": "2" * 40},
            "generated_at": "2026-01-01T00:00:00Z", "integrations": []}


def test_a_code_mode_stack_reaches_step_2_with_its_source_root(tmp_path):
    """normalize finds no single source root in a code-mode map, so step 1 §5
    binds the project root, where every file of the map resolves; step 2 then
    reads them there, and step 3 diffs them library by library."""
    project = tmp_path / "project"
    for rel in CODE_MODE_FILES:
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_bytes(b"export function f() {}\n")
    entries = [_entry(f"f_{lib.replace('-', '_')}", rel, 1, source_library=lib) for rel, lib in CODE_MODE_FILES.items()]
    audit = Audit(tmp_path, entries, None, **_code_mode_provenance())
    normalized = _run_prose(NORMALIZE_CMD, audit.values)
    assert normalized.returncode == 0, normalized.stderr
    flags = json.loads(normalized.stdout)
    assert (flags["is_stack_skill"], flags["compose_mode_stack"]) == (True, False)
    assert (flags["source_root"], flags["baseline_commit"], flags["baseline_ref"]) == (None, None, None)
    # Step 1 §5 binds the project root; §5b's helper then skips on the null baseline.
    source = _flow(_slice(_read(INIT), "### 5. Resolve Source Path", "### 5b."))
    assert ("**A code-mode stack** (`{is_stack_skill}` true, `{compose_mode_stack}` false) has no single "
            "`source_root` in its map") in source
    assert "Bind `{source_root}` ← `{project-root}`." in source
    source_root = project
    for rel in flags["bounded_scan_files"]:
        assert (source_root / rel).is_file(), rel
    # Step 2: the scan list and a snapshot read there, each export tagged with its library.
    values = {**audit.values, "{project-root}": str(project)}
    (scan_list,) = [line.strip() for line in _read(RE_INDEX).splitlines()
                    if line.strip().startswith("uv run {extractionSnapshotHelper} scan-list ")]
    scan = _run_prose(scan_list, values)
    assert scan.returncode == 0, scan.stdout + scan.stderr
    details = _write_json(audit.data / "export-details-1.json", {
        "files": list(CODE_MODE_FILES),
        "exports": [{"name": e["export_name"], "file": e["source_file"], "line": 1, "type": "function",
                     "signature": "export function f() {}"} for e in entries]})
    build = subprocess.run([sys.executable, str(SNAPSHOT), "build", "--source-root", str(source_root), "--tier",
                            "Quick", "--date", TIMESTAMP, "--provenance-map", str(audit.provenance), "--details",
                            str(details), "-o", str(audit.snapshot)],
                           capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    line = json.loads(build.stdout)
    assert (build.returncode, line["complete"]) == (0, True), build.stdout + build.stderr
    snapshot = _load(audit.snapshot)
    assert {f["file"]: f["status"] for f in snapshot["files"]} == {rel: "read-by-eye" for rel in CODE_MODE_FILES}
    assert sorted(e["source_library"] for e in snapshot["exports"]) == ["lib-a", "lib-b"]
    # Step 3: one diff per library, no drift.
    diff = audit.diff(" --group-by source_library")
    assert {g["source_library"] for g in diff["groups"]} == {"lib-a", "lib-b"}
    assert diff["removed"] == [] and diff["added"] == []


# --------------------------------------------------------------------------
# #594 and BMad Builder enhancement-4/enhancement-5: the baseline each skill
# records decides its route
# --------------------------------------------------------------------------


def test_a_skill_without_a_provenance_map_stops_and_names_test_skill():
    """Degraded mode had no baseline downstream, so it is gone: the
    `degraded` input, its gate, its decision and confidence_mode."""
    section = _flow(_slice(_read(INIT), "### 4. Load Provenance Map", "### Stack Skill Detection"))
    assert ('**If `{provenanceMap}` is null** (no map in the version folder, nor a flat copy): the skill records '
            'no baseline') in section
    assert ('HALT with **exit 3**, `halt_reason: "no-baseline"`, phase `init:provenance`, in either mode') in section
    assert "`[TS] Test Skill`" in section and "`[CS] Create Skill`" in section
    for path in [SKILL, *sorted(REFS.glob("*.md")), TEMPLATE]:
        text = _read(path)
        for gone in ("degraded", "Degraded", "confidence_mode", "[D]egraded", "init.degraded-mode"):
            assert gone not in text, (path.name, gone)
    inputs = _slice(_read(SKILL), "| **Inputs** |", "\n")
    assert "`degraded`" not in inputs and "`tier_override`" in inputs


def test_init_routes_a_docs_only_skill_to_its_document_hashes():
    init = _read(INIT)
    assert _frontmatter(INIT)["docsOnlyStepFile"] == DOC_DRIFT.name
    assert _frontmatter(DOC_DRIFT)["classifyStepFile"] == SEVERITY.name
    assert _frontmatter(SEVERITY)["reportStepFile"] == REPORT.name
    artifacts = _flow(_slice(init, "### 3. Load Skill Artifacts", "### 4."))
    assert ("**A docs-only skill** (its `scope_type`, or the `source_type` an older `metadata.json` records, is "
            "`docs-only`)") in artifacts
    assert ('When `doc_sources` is missing or empty, or no entry of it has a `content_hash` (create-skill records '
            'null for a document it could not fetch), nothing records the documents\' state: HALT with **exit 3**, '
            '`halt_reason: "no-baseline"`, phase `init:baseline`') in artifacts
    assert "skip §4, Stack Skill Detection and §5, take §5b's docs-only skip, and continue at §6" in artifacts
    upstream = _flow(_slice(init, "### 5b. Detect Upstream Drift", "**Otherwise**"))
    assert 'A docs-only skill (§3) skips it the same way, with `upstream_fetch = "skipped: docs-only skill"`' in (
        upstream)
    confirm = _flow(_slice(init, "### 7. Present Baseline Summary", "**GATE"))
    assert "or `{docsOnlyStepFile}` when `{docs_only_skill}` is true" in confirm
    # Steps 5a and 5 pick their next step from the flag, so they read it from
    # the report, where a compacted session cannot lose it.
    for path in (DOC_DRIFT, SEVERITY):
        assert ("`{docs_only_skill}` is the `docs_only_skill` value step 1 §6 wrote into {outputFile}'s "
                "frontmatter: read it there, not from memory") in _flow(_read(path)), path.name
    stages = _flow(_slice(_read(SKILL), "## Stages", "## Invocation Contract"))
    assert ("A docs-only skill skips stages 2 to 4 too (step 1 §3): init.md → doc-drift.md → "
            "severity-classify.md → report.md.") in stages
    severity = _slice(_read(SEVERITY), "### 1. Build the Findings File", "### 2.")
    assert _fenced_line(severity, "--doc-drift") == (
        'uv run {severityClassifyHelper} --doc-drift "{auditDataFolder}/doc-drift.json" '
        '-o "{auditDataFolder}/findings.json"')


def _docs_only_skill(tmp_path: Path, names: tuple[str, ...], unhashed: tuple[str, ...] = ()) -> tuple[Path, Path]:
    """A docs-only skill whose doc_sources hash local documents (file:// URLs,
    which skf-detect-docs.py reads as it reads a fetched page); an `unhashed`
    one records the null hash create-skill writes when a fetch failed."""
    docs = tmp_path / "docs"
    docs.mkdir()
    sources = []
    for name in names:
        (docs / name).write_bytes(f"# {name} v1\n".encode("utf-8"))
        digest = "sha256:" + hashlib.sha256((docs / name).read_bytes()).hexdigest()
        sources.append({"url": "file://" + (docs / name).as_posix(), "detected_via": "brief_doc_urls",
                        "content_hash": None if name in unhashed else digest})
    package = tmp_path / "skills" / "demo" / "1.0.0" / "demo"
    _write_json(package / "metadata.json", {"name": "demo", "version": "1.0.0", "scope_type": "docs-only",
                                            "source_root": None, "doc_sources": sources})
    return docs, package


# Step 5a §2's warning commands, with the stats count each one records.
DOC_WARNING_RE = re.compile(r'`(uv run \{emitEnvelopeHelper\} record --run-dir "\{run_dir\}" '
                            r'--warning "doc_[a-z_]+: \{([a-z_]+)\}")`')


@pytest.mark.parametrize("changed,unreachable,unhashed,score,warnings", [
    (("api.md",), (), (), "SIGNIFICANT", []),
    ((), (), (), "CLEAN", []),
    ((), ("guide.md",), (), "CLEAN", ["doc_fetch_failed: 1"]),
    ((), (), ("guide.md",), "CLEAN", ["doc_not_hashed: 1"]),
    ((), ("api.md",), ("guide.md",), None, []),
], ids=["a-document-changed", "no-document-changed", "a-document-unreachable", "a-document-not-hashed",
        "no-document-compared"])
def test_a_docs_only_skill_is_graded_by_its_documents(tmp_path, changed, unreachable, unhashed, score, warnings):
    """Step 5a's command saves the comparison, step 5 grades each changed
    document HIGH, so a docs-only skill whose source changed is no longer
    CLEAN and a maintain pipeline reaches update-skill. A comparison that
    reached no document halts instead of vouching for documents nobody
    read, and one that left some out records how many in the envelope."""
    docs, package = _docs_only_skill(tmp_path, ("api.md", "guide.md"), unhashed)
    for name in changed:
        (docs / name).write_bytes(f"# {name} v2\n".encode("utf-8"))
    for name in unreachable:
        (docs / name).unlink()
    audit = Audit(tmp_path, [], None)
    audit.values["{resolved_skill_package}"] = str(package)
    result = audit.run(DOC_DRIFT, "compare-hashes")
    assert result.returncode == 0, result.stderr
    stats = _load(audit.data / "doc-drift.json")["stats"]
    assert (stats["total_tracked"], stats["changed"], stats["fetch_failed"], stats["skipped_null_hash"]) == (
        2, len(changed), len(unreachable), len(unhashed))
    rules = _flow(_slice(_read(DOC_DRIFT), "**Once the comparison is saved, a docs-only skill**", "### 3."))
    if score is None:
        assert stats["changed"] + stats["unchanged"] == 0
        assert "**`stats.changed` + `stats.unchanged` is 0:** no document was compared" in rules
        assert ('HALT with **exit 3**, `halt_reason: "source-unreadable"`, phase `doc-drift:compare`, '
                '`"path": "{resolved_skill_package}/metadata.json"`') in rules
        return
    run_dir = tmp_path / "run"
    audit.values.update({"{run_dir}": str(run_dir), **{f"{{{key}}}": str(n) for key, n in stats.items()}})
    commands = DOC_WARNING_RE.findall(rules)
    assert [count for _, count in commands] == ["fetch_failed", "skipped_null_hash"]
    for command, count in commands:
        if stats[count]:
            recorded = _run_prose(command, audit.values)
            assert recorded.returncode == 0, recorded.stderr
    sink = run_dir / "warnings.jsonl"
    lines = sink.read_text(encoding="utf-8").splitlines() if sink.exists() else []
    assert [json.loads(line) for line in lines] == warnings
    findings = audit.project("--doc-drift")
    assert audit.sources == {"doc_drift": len(changed)}
    assert [(f["type"], f["category"]) for f in findings] == [("changed", "doc_source")] * len(changed)
    classified = audit.classify()
    assert classified["drift_score"] == score
    assert _next_workflow(classified) == ("update-skill" if changed else None)
