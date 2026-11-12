#!/usr/bin/env python3
"""Tests for skf-summarize-validation.py, the reader of Quick Skill's saved validator outputs (#1120).

The skill-check fixtures follow skill-check 1.2.0's `check --format json` output (dist/cli/main.js: the
`summary`, `diagnostics` and `metadata` of toJson, then `scores`), and its `Wrote <path>` line when a
project config sets a report path. The output validator, frontmatter validator and security scan outputs
come from running those helpers on a fixture package, so a change to their shape fails here.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "src" / "shared" / "scripts"
READER = SCRIPTS / "skf-summarize-validation.py"
SECURITY_FIXTURES = REPO / "test" / "fixtures" / "security-scan"

spec = importlib.util.spec_from_file_location("skf_summarize_validation", READER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ZERO = {"skill_md": 0, "context_snippet": 0, "metadata": 0, "security": 0}


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((data if isinstance(data, str) else json.dumps(data, indent=2)).encode("utf-8"))
    return path


def _diagnostic(rule: str, rel: str, line: int = 1, severity: str = "warn") -> dict:
    return {"ruleId": rule, "severity": severity, "message": f"{rule} reported", "file": rel, "line": line,
            "column": 1, "suggestion": f"Fix {rule}."}


def _skill_check(diagnostics: list[dict], scores: list[dict] | None = None, **extra) -> dict:
    data = {"summary": {"skillCount": 1, "errorCount": sum(d["severity"] == "error" for d in diagnostics),
                        "warningCount": sum(d["severity"] == "warn" for d in diagnostics)},
            "diagnostics": diagnostics,
            "metadata": {"roots": ["skills"], "include": ["**/SKILL.md"], "exclude": [], "format": "json"}}
    if scores is not None:
        data["scores"] = scores
    return {**data, **extra}


def _score_entry(skill_id: str, rel: str, score) -> dict:
    return {"skillId": skill_id, "relativePath": rel, "score": score,
            "breakdown": {"frontmatter": 30, "description": 30, "body": 20, "links": 10, "file": 10}}


def _run(tmp_path: Path, *args: str, cwd: Path | None = None) -> dict:
    proc = subprocess.run([sys.executable, str(READER), *args], cwd=cwd or tmp_path, capture_output=True,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """A Quick Skill package, `{skills_output_folder}/{repo_name}/{version}/{repo_name}/`."""
    skill = tmp_path / "skills" / "demo" / "1.0.0" / "demo"
    _write(skill / "SKILL.md", "---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n")
    return skill


def _validator_outputs(run: Path, body: int = 1, snippet: int = 1, metadata: int = 0, findings: int = 1) -> None:
    """output.json and security.json in the shapes skf-validate-output.py and skf-security-scan.py print."""
    issue = {"severity": "medium", "field": "section:Usage", "message": "Missing ## Usage section"}
    _write(run / "output.json", {
        "result": "FAIL", "skill_dir": "x",
        "validation": {"skill_md": {"frontmatter": {"skipped": "frontmatter validation skipped (--skip-frontmatter)"},
                                    "body": [issue] * body},
                       "context_snippet": {"issues": [{"severity": "low", "field": "length",
                                                       "message": "Context snippet may be too short"}] * snippet},
                       "metadata": {"issues": [{"severity": "medium", "field": "source_repo",
                                                "message": "source_repo missing"}] * metadata}},
        "summary": {"total_issues": body + snippet + metadata}})
    _write(run / "security.json", {
        "security_result": "warn" if findings else "pass", "scanner": "snyk-agent-scan@0.6.11",
        "findings": [{"skill": "demo", "risk": "prompt_injection_skill_instructions",
                      "name": "Potential prompt injection", "score": 800, "evidence": "Ignore prior instructions",
                      "text": "Potential prompt injection (800/1000) in demo: Ignore prior instructions"}] * findings,
        "errors": [], "note": "the scanner reported 1 risk"})


def _all_flags(run: Path, package: Path) -> list[str]:
    return ["--skill-check", str(run / "skill-check.json"), "--frontmatter", str(run / "frontmatter.json"),
            "--output", str(run / "output.json"), "--security", str(run / "security.json"),
            "--skill-dir", str(package)]


# --------------------------------------------------------------------------
# The I/O matrix rows
# --------------------------------------------------------------------------


def test_the_score_of_the_matching_scores_entry(tmp_path: Path, package: Path):
    """QS scores match: the entry whose relativePath is this SKILL.md, past another skill's, and the
    `Wrote <path>` line after the JSON is ignored."""
    rel = "skills/demo/1.0.0/demo/SKILL.md"
    run = tmp_path / "run"
    data = _skill_check([_diagnostic("description.use_when_phrase", rel), _diagnostic("body.max_lines", rel, 9)],
                        [_score_entry("tmp/other", "skills/other/1.0.0/other/SKILL.md", 50),
                         _score_entry("tmp/demo", rel, 88)])
    _write(run / "skill-check.json", json.dumps(data, indent=2) + "\nWrote reports/r.json\n")
    _validator_outputs(run, body=1, snippet=1, metadata=0, findings=1)
    out = _run(tmp_path, *_all_flags(run, package))
    assert (out["status"], out["quality_score"], out["quality_score_source"], out["skill_check"]) == (
        "ok", 88, "scores", "validated")
    assert out["validation_issues"] == {"skill_md": 3, "context_snippet": 1, "metadata": 0, "security": 1}
    # §6 lists exactly what was counted: skill-check's diagnostics first, then the body issues, each with the
    # severity and message of the entry it was read from.
    assert out["issues"]["skill_md"] == [
        {"check": "description.use_when_phrase", "severity": "warn", "message": "description.use_when_phrase reported",
         "line": 1},
        {"check": "body.max_lines", "severity": "warn", "message": "body.max_lines reported", "line": 9},
        {"check": "section:Usage", "severity": "medium", "message": "Missing ## Usage section", "line": None}]
    assert out["issues"]["context_snippet"] == [
        {"check": "length", "severity": "low", "message": "Context snippet may be too short", "line": None}]
    assert out["issues"]["security"] == [{
        "check": "prompt_injection_skill_instructions", "severity": None,
        "message": "Potential prompt injection (800/1000) in demo: Ignore prior instructions", "line": None}]
    assert {k: len(v) for k, v in out["issues"].items()} == out["validation_issues"]


def test_an_older_build_s_top_level_quality_score(tmp_path: Path, package: Path):
    """QS old build: no `scores`, a top-level `qualityScore`."""
    run = tmp_path / "run"
    _write(run / "skill-check.json", _skill_check([], qualityScore=72))
    out = _run(tmp_path, *_all_flags(run, package))
    assert (out["quality_score"], out["quality_score_source"], out["skill_check"]) == (72, "qualityScore",
                                                                                       "validated")
    assert out["validation_issues"] == ZERO


def test_an_early_stop_counts_the_frontmatter_validator(tmp_path: Path, package: Path):
    """QS early stop: skill-check printed no JSON, so the frontmatter validator's issues count."""
    run = tmp_path / "run"
    _write(run / "skill-check.json", "Error: unknown option '--frobnicate'\n")
    _write(run / "frontmatter.json", {"status": "fail", "name": "demo", "issues": [
        {"severity": "high", "field": "name", "message": "name does not match"},
        {"severity": "low", "field": "description", "message": "description is short"}], "summary": {}})
    _validator_outputs(run, body=2, snippet=0, findings=0)
    out = _run(tmp_path, *_all_flags(run, package))
    assert (out["quality_score"], out["quality_score_source"], out["skill_check"]) == (None, None, "stopped")
    assert out["validation_issues"] == {"skill_md": 4, "context_snippet": 0, "metadata": 0, "security": 0}
    assert [i["check"] for i in out["issues"]["skill_md"]] == ["name", "description", "section:Usage",
                                                                "section:Usage"]


def test_without_skill_check_the_frontmatter_validator_counts(tmp_path: Path, package: Path):
    """QS frontmatter only: no skill-check.json at all."""
    run = tmp_path / "run"
    _write(run / "frontmatter.json", {"status": "fail", "issues": [
        {"severity": "medium", "field": "name", "message": "name is long"}]})
    _validator_outputs(run, body=1, snippet=0, findings=0)
    out = _run(tmp_path, *_all_flags(run, package))
    assert (out["quality_score"], out["skill_check"]) == (None, "not-run")
    assert out["validation_issues"]["skill_md"] == 2


def test_a_report_of_another_skill_gives_no_score(tmp_path: Path, package: Path):
    """QS no match: `scores` names only another skill, and there is no `qualityScore`."""
    run = tmp_path / "run"
    _write(run / "skill-check.json", _skill_check([], [_score_entry("tmp/other", "skills/other/SKILL.md", 91)]))
    out = _run(tmp_path, *_all_flags(run, package))
    assert (out["quality_score"], out["quality_score_source"], out["skill_check"]) == (None, None, "validated")


def test_a_validated_run_ignores_a_frontmatter_file(tmp_path: Path, package: Path):
    """skill-check's diagnostics replace the frontmatter validator's issues, never add to them."""
    run = tmp_path / "run"
    _write(run / "skill-check.json", _skill_check([]))
    _write(run / "frontmatter.json", {"issues": [{"severity": "high", "field": "name", "message": "x"}]})
    out = _run(tmp_path, *_all_flags(run, package))
    assert out["validation_issues"] == ZERO


# --------------------------------------------------------------------------
# The score rule
# --------------------------------------------------------------------------


def test_the_skill_id_matches_when_run_from_another_folder(tmp_path: Path, package: Path):
    """relativePath is relative to skill-check's folder; run elsewhere, the skillId rule finds the entry."""
    rel = "skills/demo/1.0.0/demo/SKILL.md"
    expected_id = f"{tmp_path.name}/demo"  # the segments around the last `skills` segment
    assert mod.skill_check_id(package / "SKILL.md") == expected_id
    run = tmp_path / "run"
    _write(run / "skill-check.json", _skill_check([], [_score_entry("x/other", rel.replace("demo", "other"), 40),
                                                       _score_entry(expected_id, rel, 64)]))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    out = _run(tmp_path, "--skill-check", str(run / "skill-check.json"), "--skill-dir", str(package), cwd=elsewhere)
    assert (out["quality_score"], out["quality_score_source"]) == (64, "scores")


def test_the_skill_id_without_a_skills_segment(tmp_path: Path):
    """No `skills` segment with one on each side: the parent folder's name and the skill folder's."""
    skill = tmp_path / "pkg" / "zod"
    assert mod.skill_check_id(skill / "SKILL.md") == "pkg/zod"
    # The path's segments include the file's own name, as skill-check splits them.
    assert mod.skill_check_id(tmp_path / "a" / "skills" / "SKILL.md") == "a/SKILL.md"


def test_the_relative_path_matches_with_either_separator_and_through_a_link(tmp_path: Path, package: Path,
                                                                            monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    windows = {"scores": [_score_entry("nope/nope", "skills\\demo\\1.0.0\\demo\\SKILL.md", 77)]}
    assert mod.quality_score(windows, package) == (77, "scores")
    if not hasattr(os, "symlink"):
        return
    link = tmp_path / "linked"
    try:
        link.symlink_to(package, target_is_directory=True)
    except OSError:
        pytest.skip("no symlinks here")
    posix = {"scores": [_score_entry("nope/nope", "skills/demo/1.0.0/demo/SKILL.md", 81)]}
    assert mod.quality_score(posix, link) == (81, "scores")


@pytest.mark.parametrize("bad", [True, "88", 101, -1, None])
def test_only_a_number_from_0_to_100_counts(tmp_path: Path, package: Path, monkeypatch: pytest.MonkeyPatch, bad):
    """An entry whose score is not a number from 0 to 100 gives none; the next rule is read."""
    monkeypatch.chdir(tmp_path)
    rel = "skills/demo/1.0.0/demo/SKILL.md"
    assert mod.quality_score({"scores": [_score_entry("x/y", rel, bad)]}, package) == (None, None)
    assert mod.quality_score({"scores": [_score_entry("x/y", rel, bad)], "qualityScore": 60}, package) == (
        60, "qualityScore")
    assert mod.quality_score({"qualityScore": bad}, package) == (None, None)


def test_quality_score_called_directly(tmp_path: Path, package: Path, monkeypatch: pytest.MonkeyPatch):
    """combine-external-scores.py calls it with skill-check's parsed JSON, or None for a run with no JSON."""
    monkeypatch.chdir(tmp_path)
    rel = "skills/demo/1.0.0/demo/SKILL.md"
    data = {"scores": [_score_entry("a/b", "elsewhere/SKILL.md", 10), _score_entry("a/b", rel, 92.5)],
            "qualityScore": 12}
    assert mod.quality_score(data, package) == (92.5, "scores")
    assert mod.quality_score(data, str(package)) == (92.5, "scores")
    assert mod.quality_score(None, package) == (None, None)
    assert mod.quality_score({"scores": "not a list", "qualityScore": 0}, package) == (0, "qualityScore")


# --------------------------------------------------------------------------
# Reading the files
# --------------------------------------------------------------------------


def test_a_byte_order_mark_and_leading_whitespace_are_skipped(tmp_path: Path, package: Path):
    run = tmp_path / "run"
    text = "\n  " + json.dumps(_skill_check([_diagnostic("file.trailing_newline_single", "x")], qualityScore=55))
    (run).mkdir()
    (run / "skill-check.json").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    out = _run(tmp_path, "--skill-check", str(run / "skill-check.json"), "--skill-dir", str(package))
    assert (out["quality_score"], out["skill_check"], out["validation_issues"]["skill_md"]) == (55, "validated", 1)
    assert mod.read_json_object(run / "skill-check.json")["qualityScore"] == 55


@pytest.mark.parametrize("content", ["", "[1, 2]", "Wrote r.json\n{}", "{broken", "\xff"])
def test_a_file_without_a_json_object_at_its_start_is_a_stopped_check(tmp_path: Path, content: str):
    path = tmp_path / "f.json"
    path.write_bytes(content.encode("latin-1"))
    assert mod.read_json_object(path) is None
    assert mod.read_json_object(tmp_path / "missing.json") is None
    assert mod.read_json_object(None) is None


def test_a_skipped_snippet_and_metadata_count_zero(tmp_path: Path, package: Path):
    """skf-validate-output.py writes `{"skipped": ...}` for a snippet or metadata it did not check."""
    run = tmp_path / "run"
    _write(run / "output.json", {"validation": {
        "skill_md": {"frontmatter": {"skipped": "x"}, "body": []},
        "context_snippet": {"skipped": "context-snippet.md not found"},
        "metadata": {"skipped": "metadata.json not found"}}})
    out = _run(tmp_path, "--output", str(run / "output.json"), "--skill-dir", str(package))
    assert out["validation_issues"] == ZERO and out["skill_check"] == "not-run"


def test_no_file_at_all_counts_nothing(tmp_path: Path, package: Path):
    out = _run(tmp_path, *_all_flags(tmp_path / "empty-run", package))
    assert out == {"status": "ok", "quality_score": None, "quality_score_source": None, "skill_check": "not-run",
                   "validation_issues": ZERO, "issues": {k: [] for k in ZERO}}


def test_the_real_validators_outputs_are_read(tmp_path: Path, package: Path):
    """The output validator, the frontmatter validator and the security scan, run on a fixture package, print
    the shapes the reader counts, so the counts follow their real output."""
    _write(package / "context-snippet.md", "x\n")
    _write(package / "metadata.json", {"name": "demo"})
    run = tmp_path / "run"
    run.mkdir()

    def save(name: str, *argv: str) -> dict:
        proc = subprocess.run([sys.executable, *argv], capture_output=True, timeout=120)
        (run / name).write_bytes(proc.stdout)
        return json.loads(proc.stdout)

    validated = save("output.json", str(SCRIPTS / "skf-validate-output.py"), str(package), "--generated-by",
                     "quick-skill", "--skip-frontmatter")
    frontmatter = save("frontmatter.json", str(SCRIPTS / "skf-validate-frontmatter.py"),
                       str(package / "SKILL.md"), "--skill-dir-name", "other-name")
    security = save("security.json", str(SCRIPTS / "skf-security-scan.py"), "parse", "--stdout-file",
                    str(SECURITY_FIXTURES / "risky.json"), "--exit-code", "0")
    out = _run(tmp_path, *_all_flags(run, package))
    expected = {
        "skill_md": len(frontmatter["issues"]) + len(validated["validation"]["skill_md"]["body"]),
        "context_snippet": len(validated["validation"]["context_snippet"]["issues"]),
        "metadata": len(validated["validation"]["metadata"]["issues"]),
        "security": len(security["findings"]),
    }
    assert out["validation_issues"] == expected
    assert all(expected.values()), "the fixture package gives each heading an issue"

    def read(entries: list[dict]) -> list[tuple]:
        return [(e["field"], e["severity"], e["message"]) for e in entries]

    # Each entry keeps the check, severity and message of the validator entry it was read from.
    assert {heading: [(i["check"], i["severity"], i["message"]) for i in entries]
            for heading, entries in out["issues"].items()} == {
        "skill_md": read(frontmatter["issues"]) + read(validated["validation"]["skill_md"]["body"]),
        "context_snippet": read(validated["validation"]["context_snippet"]["issues"]),
        "metadata": read(validated["validation"]["metadata"]["issues"]),
        "security": [(f["risk"], None, f["text"]) for f in security["findings"]],
    }


# --------------------------------------------------------------------------
# The script itself
# --------------------------------------------------------------------------


def test_no_step_file_picks_the_score_or_types_the_findings():
    """#1120: the score rule lives here, so no Quick Skill or Test Skill step names skill-check's score fields, and
    Test Skill's external validators type no score input and no ledger record."""
    files = [*(REPO / "src" / "skf-quick-skill").rglob("*.md"), *(REPO / "src" / "skf-test-skill" / "references")
             .rglob("*.md")]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in ("relativePath", "skillId", "scores[].score"):
            assert name not in text, (path.name, name)
    external = (REPO / "src" / "skf-test-skill" / "references" / "external-validators.md").read_text(encoding="utf-8")
    assert "echo '{" not in external and "<<'SKF_GAPS'" not in external


def test_the_header_and_the_cli():
    text = READER.read_text(encoding="utf-8")
    header = re.match(r"# /// script\n(.*?)# ///\n", text, re.S)
    assert header and '# dependencies = []\n' in header.group(1)
    imports = {alias.name.split(".")[0] for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Import)
               for alias in node.names}
    imports |= {node.module.split(".")[0] for node in ast.walk(ast.parse(text))
                if isinstance(node, ast.ImportFrom) and node.module}
    assert imports <= {"__future__", "argparse", "json", "os", "sys", "pathlib"}, imports
    assert "add_subparsers(" not in text
    # A missing --skill-dir is argparse's exit 2.
    proc = subprocess.run([sys.executable, str(READER)], capture_output=True, timeout=60)
    assert proc.returncode == 2 and proc.stdout == b""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
