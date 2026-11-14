"""Structural integration tests for the threshold fallback record (story 3.3, #1190).

Validates the threshold fallback compute-score.py applies and the score.md
§4b fields that read it (the prose restates no trigger), INCONCLUSIVE guard
clause, 80% floor constant, the Completeness Score section's Threshold
Fallback subsection that build-result-context.py settle prints (§6), the
fallback fields in output frontmatter (§7), fallback notice in score report
(§8), the result contract fallback fields, which build-result-context.py
writes for report.md §4c (present only when the fallback fired, #593), and
report.md §6 fallback notice block. #1190: the subsection replaced the
`evidence-report-fallback.md` file, so no step, doc or result field names
that file any more, and the inventory still counts an older copy as SKF's.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
SCORE_FILE = TS_DIR / "references" / "score.md"
REPORT_FILE = TS_DIR / "references" / "report.md"
SKILL_MD = TS_DIR / "SKILL.md"
CONTRACT_FILE = TS_DIR / "references" / "invocation-contract.md"
BUILD_CONTEXT = TS_DIR / "scripts" / "build-result-context.py"
GAP_LEDGER = TS_DIR / "scripts" / "gap-ledger.py"
PIPELINE_CONTRACTS = REPO_ROOT / "src" / "shared" / "references" / "pipeline-contracts.md"
VERSION_PATHS = REPO_ROOT / "src" / "knowledge" / "version-paths.md"
INVENTORY = REPO_ROOT / "src" / "shared" / "scripts" / "skf-skill-inventory.py"
# The names #1190 retired with the fallback file: its name, its frontmatter key, its result field and settle's flag.
RETIRED = ("evidence-report-fallback.md", "evidenceReportPath", "evidence_report_path", "--evidence-report")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# score.md §4b — Threshold Fallback Section Exists
# ---------------------------------------------------------------------------


class TestScoreFallbackSection:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_section_4b_exists(self, text: str) -> None:
        assert re.search(r"###?\s+4b\.", text), (
            "score.md must have a §4b section for threshold fallback"
        )

    def test_section_4b_between_4_and_5(self, text: str) -> None:
        idx_4 = text.find("### 4. Determine Result")
        idx_4b = text.find("### 4b.")
        idx_5 = text.find("### 5. Determine Next Workflow Recommendation")
        assert idx_4 != -1 and idx_4b != -1 and idx_5 != -1, (
            "score.md must have §4, §4b, and §5 sections"
        )
        assert idx_4 < idx_4b < idx_5, (
            "§4b must appear between §4 and §5 in score.md"
        )


# ---------------------------------------------------------------------------
# Fallback trigger conditions: compute-score.py holds them, score.md reads them
# ---------------------------------------------------------------------------


def _compute_score():
    spec = importlib.util.spec_from_file_location("compute_score_fallback", TS_DIR / "scripts" / "compute-score.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestFallbackTriggerConditions:
    """An uncapped FAIL scoring 80 or more against a threshold above 80 passes
    at the 80 floor. compute-score.py is the one home of the rule."""

    @staticmethod
    def _score(total: float, threshold: float) -> dict:
        categories = ("exportCoverage", "signatureAccuracy", "typeCoverage", "coherence", "externalValidation")
        return _compute_score().compute_score({"mode": "contextual", "tier": "Deep", "threshold": threshold,
                                               "toolingStatus": "ok",
                                               "scores": {c: total for c in categories}})

    def test_fail_condition(self) -> None:
        out = self._score(95, 90)
        assert out["result"] == "PASS" and "thresholdFallback" not in out, "a PASS never falls back"

    def test_score_gte_80(self) -> None:
        fired = self._score(85, 90)
        assert (fired["result"], fired["effectiveResult"], fired["thresholdFallback"]) == ("FAIL", "PASS", True)
        assert fired["originalThreshold"] == 90
        assert "thresholdFallback" not in self._score(79, 90), "below the floor the FAIL stands"

    def test_threshold_gt_80(self) -> None:
        out = self._score(85, 80)
        assert out["result"] == "PASS" and "thresholdFallback" not in out, "at 80 the score passes outright"
        assert _compute_score().FALLBACK_FLOOR == 80

    def test_score_md_reads_the_fields_and_restates_no_rule(self) -> None:
        text = _read(SCORE_FILE)
        section = text[text.find("### 4b."):text.find("### 5.")]
        for field in ("thresholdFallback", "effectiveResult", "originalThreshold"):
            assert field in section, field
        for restated in ("totalScore >= 80", "effective_threshold > 80", 'result == "FAIL"'):
            assert restated not in section, restated


# ---------------------------------------------------------------------------
# score.md §4b — INCONCLUSIVE Guard Clause
# ---------------------------------------------------------------------------


class TestInconclusiveGuard:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_inconclusive_not_triggered(self, text: str) -> None:
        # §4 settles the verdict the §4b fallback reads: INCONCLUSIVE is never overridden.
        verdict_sections = text[text.find("### 4. Determine Result"):text.find("### 5.")]
        assert "INCONCLUSIVE" in verdict_sections and "never overridden" in verdict_sections, (
            "§4 must say INCONCLUSIVE is never overridden by the fallback"
        )


# ---------------------------------------------------------------------------
# score.md §4b — 80% Floor Constant
# ---------------------------------------------------------------------------


class TestFloorConstant:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_80_floor_present(self, fallback_section: str) -> None:
        assert "80" in fallback_section, (
            "§4b must reference the 80% floor constant"
        )

    def test_override_result_to_pass(self, fallback_section: str) -> None:
        assert re.search(r'effectiveResult.*"PASS"', fallback_section), (
            "§4b must read the script's PASS from effectiveResult on fallback"
        )


# ---------------------------------------------------------------------------
# score.md §4b: the fallback is recorded in the report, in no file of its own
# ---------------------------------------------------------------------------


class TestFallbackRecordedInTheReport:
    @pytest.fixture
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_section_4b_names_the_subsection(self, fallback_section: str) -> None:
        flow = " ".join(fallback_section.split())
        assert fallback_section.startswith("### 4b. Threshold Fallback\n")
        assert ("§6's settle records the fallback in the Completeness Score section's `### Threshold Fallback` "
                "subsection") in flow
        assert "a pointer to the Gap Report, which report.md §4c renders from the gap ledger" in flow
        assert flow.endswith("No other file records it.")

    def test_section_4b_writes_no_file(self, fallback_section: str) -> None:
        for gone in ("Evidence Report", "evidence report", "evidence-report-fallback", "render --ledger", "Write the"):
            assert gone not in fallback_section, gone


# ---------------------------------------------------------------------------
# score.md §6: the Threshold Fallback subsection settle prints in the Completeness Score section
# ---------------------------------------------------------------------------


def _settle(tmp_path: pathlib.Path) -> tuple[str, str]:
    """(the Completeness Score section, the report) score.md §6's `settle` writes for a run the fallback accepted
    (#1186): 85 against a 90 target, from compute-score.py's own output."""
    report = tmp_path / "report.md"
    report.write_bytes(("---\nworkflowType: 'test-skill'\ntestMode: 'contextual'\nhardGate: 'passed'\n"
                        "testResult: ''\nscore: ''\nthreshold: '90%'\nthresholdSource: 'CLI override (90%)'\n"
                        "analysisConfidence: 'full'\ntoolingStatus: 'ok'\nworkspaceDrift: 'ok'\n"
                        "nextWorkflow: ''\n---\n# Test Report: demo\n").encode("utf-8"))
    categories = ("exportCoverage", "signatureAccuracy", "typeCoverage", "coherence", "externalValidation")
    scored = _compute_score().compute_score({"mode": "contextual", "tier": "Deep", "threshold": 90,
                                             "toolingStatus": "ok", "scores": dict.fromkeys(categories, 85)})
    score = tmp_path / "score.json"
    score.write_bytes(json.dumps(scored).encode("utf-8"))
    external = tmp_path / "external.json"
    external.write_bytes(json.dumps({"externalScore": 85, "toolsUsed": ["skill-check"]}).encode("utf-8"))
    proc = subprocess.run([sys.executable, str(BUILD_CONTEXT), "settle", "--report", str(report), "--score",
                           str(score), "--external", str(external)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout, report.read_text(encoding="utf-8")


# The subsection settle prints for 85 against a CLI 90% target on the version's first test run.
SUBSECTION = """### Threshold Fallback

**Attempted Threshold:** 90%
**Achieved Score:** 85%
**Accepted At:** 80% floor
**Threshold Source:** CLI override (90%)
**Prior Test Report:** none found beside this report
**Findings:** the Gap Report lists this run's gaps; address them to reach the 90% target
"""


class TestScoreSection6Fallback:
    """#1186: §6 writes what `settle` prints, so the fallback record is the script's (#1190: a subsection)."""

    def test_threshold_fallback_subsection_in_section_6(self, tmp_path: pathlib.Path) -> None:
        section, _ = _settle(tmp_path)
        assert section.endswith("\n\n" + SUBSECTION), (
            "settle's output must end with the Threshold Fallback subsection when fallback is active"
        )
        assert "**Threshold Fallback:**" not in section and "Evidence report" not in section
        text = _read(SCORE_FILE)
        section6 = text[text.find("### 6. Write the Completeness Score"):text.find("### 7.")]
        assert "uv run {resultContextScript} settle" in section6 and "--evidence-report" not in section6

    def test_subsection_follows_the_result_block(self, tmp_path: pathlib.Path) -> None:
        section, _ = _settle(tmp_path)
        ts_idx = section.find("**Threshold Source:** CLI override (90%)\n")
        tooling_idx = section.find("**Tooling Status:** ok\n")
        fb_idx = section.find("### Threshold Fallback\n")
        assert -1 < ts_idx < tooling_idx < fb_idx, (
            "### Threshold Fallback must follow the Result block's last line"
        )


# ---------------------------------------------------------------------------
# score.md §7 — Fallback Fields in Output Frontmatter
# ---------------------------------------------------------------------------


class TestScoreSection7Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_threshold_fallback_in_frontmatter(self, text: str) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):]
        assert "thresholdFallback" in fm_section, (
            "§7 must include thresholdFallback field in output frontmatter"
        )

    def test_original_threshold_in_frontmatter(self, text: str) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):]
        assert "originalThreshold" in fm_section, (
            "§7 must include originalThreshold field in output frontmatter"
        )

    def test_no_evidence_report_path_in_frontmatter(self, text: str) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):text.find("### 8.")]
        assert ("after a threshold fallback, `thresholdFallback` and `originalThreshold`. Update the rest"
                in fm_section)
        assert "evidenceReportPath" not in fm_section


# ---------------------------------------------------------------------------
# score.md §8 — Fallback Notice in Score Report
# ---------------------------------------------------------------------------


class TestScoreSection8Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_fallback_notice_in_report(self, text: str) -> None:
        report_section = text[text.find("### 8. Report Score"):]
        assert "**Threshold fallback:**" in report_section, (
            "§8 must include a threshold fallback notice in the pipeline output"
        )

    def test_fallback_notice_points_at_the_subsection(self, text: str) -> None:
        report_section = text[text.find("### 8. Report Score"):]
        assert ("\n**Threshold fallback:** scored {totalScore}% against {original_threshold}% target: accepted at 80% "
                "floor (the Completeness Score section's Threshold Fallback subsection has the details)\n"
                ) in report_section, "§8 fallback notice must point at the Threshold Fallback subsection"


# ---------------------------------------------------------------------------
# invocation-contract.md: the Outputs name no fallback file
# ---------------------------------------------------------------------------


def _contract_section(heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", _read(CONTRACT_FILE),
                  flags=re.MULTILINE | re.DOTALL)
    assert m, f"invocation-contract.md must have a {heading} section"
    return m.group(1)


class TestContractOutputs:
    def test_outputs_name_no_fallback_file(self) -> None:
        section = _contract_section("## Invocation Contract")
        assert "the test report `test-report-{skill_name}-{run_id}.md`" in section
        assert "evidence-report-fallback.md" not in section, (
            "a threshold fallback writes no file of its own (#1190)"
        )

    def test_skill_md_points_at_the_contract(self) -> None:
        text = _read(SKILL_MD)
        assert "## Result Contract" not in text and "`references/invocation-contract.md`" in text


# ---------------------------------------------------------------------------
# invocation-contract.md: Result Contract Includes Fallback Fields
# ---------------------------------------------------------------------------


class TestContractFallbackFields:
    @pytest.fixture
    def section(self) -> str:
        return _contract_section("## Result Envelope (Headless)") + _contract_section("## Result Files")

    @pytest.mark.parametrize("field", ["threshold_fallback", "original_threshold"])
    def test_result_contract_names_the_field(self, section: str, field: str) -> None:
        assert field in section, f"the result contract must include {field}"

    def test_result_contract_names_no_evidence_path(self, section: str) -> None:
        assert ("`threshold_fallback` and `original_threshold` when the threshold fallback fired" in
                " ".join(section.split()))
        assert "evidence_report_path" not in section


# ---------------------------------------------------------------------------
# report.md §6 — Fallback Notice in Final Presentation
# ---------------------------------------------------------------------------


class TestReportSection6Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_fallback_notice_in_presentation(self, text: str) -> None:
        presentation_match = re.search(
            r"### 6\. Present Final Report\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert presentation_match, "report.md must have a §6 Present Final Report section"
        section = presentation_match.group(1)
        assert "thresholdFallback" in section, (
            "report.md §6 must reference thresholdFallback from output frontmatter"
        )

    def test_fallback_notice_points_at_the_subsection(self, text: str) -> None:
        presentation_match = re.search(
            r"### 6\. Present Final Report\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert presentation_match
        section = presentation_match.group(1)
        assert ("{If `thresholdFallback` is present in output frontmatter:}\n**Threshold fallback:** scored {score}% "
                "against {originalThreshold} target: accepted at 80% floor (the Completeness Score section's "
                "Threshold Fallback subsection has the details)\n") in section, (
            "report.md §6 fallback notice must point at the Threshold Fallback subsection"
        )
        assert "evidenceReportPath" not in section


# ---------------------------------------------------------------------------
# report.md §4c: the result contract's fallback fields come from the script
# ---------------------------------------------------------------------------


def _build(tmp_path: pathlib.Path, fallback: bool) -> dict:
    """Run build-result-context.py on a scored report, with or without a fallback."""
    lines = ["---", "skillName: 'demo'", "runId: '20260101T000000Z-ab12cd34'", "testMode: 'naive'",
             "hardGate: 'passed'", "testResult: 'pass'", "score: '84.5%'", "analysisConfidence: 'full'"]
    if fallback:
        lines += ["threshold: '80%'", "thresholdFallback: true", "originalThreshold: '90%'"]
    else:
        lines += ["threshold: '80%'"]
    report = tmp_path / "test-report-demo-20260101T000000Z-ab12cd34.md"
    report.write_bytes(("\n".join(lines + ["---", "# Report", ""])).encode("utf-8"))
    ledger = tmp_path / "test-findings-20260101T000000Z-ab12cd34.json"
    subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage", "coverage-check"],
                   input="[]", capture_output=True, text=True, encoding="utf-8", check=True)
    # compute-score.py's output: the fallback turned its FAIL into a PASS at the 80 floor (the override group).
    scored = {"result": "PASS", "totalScore": 84.5, "threshold": 80,
              "activeCategories": ["exportCoverage", "externalValidation"]}
    if fallback:
        scored |= {"result": "FAIL", "threshold": 90, "effectiveResult": "PASS", "capReason": None,
                   "thresholdFallback": True, "originalThreshold": 90}
    score = tmp_path / "score.json"
    score.write_bytes(json.dumps(scored).encode("utf-8"))
    out = tmp_path / "result-context.json"
    proc = subprocess.run([sys.executable, str(BUILD_CONTEXT), "--report", str(report), "--ledger", str(ledger),
                           "--score", str(score), "--output", str(out)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(out.read_text(encoding="utf-8"))


class TestReportResultContract:
    def test_report_builds_the_contract_with_the_script(self) -> None:
        contract_match = re.search(
            r"### 4c\. Result Contract\b(.*?)(?=^### |\Z)",
            _read(REPORT_FILE),
            flags=re.MULTILINE | re.DOTALL,
        )
        assert contract_match, "report.md must have a §4c Result Contract section"
        section = contract_match.group(1)
        assert "uv run {resultContextScript}" in section
        assert "emit --workflow skf-test-skill" in section

    def test_a_fallback_records_its_two_fields(self, tmp_path: pathlib.Path) -> None:
        payload = _build(tmp_path, fallback=True)
        assert (payload["threshold_fallback"], payload["original_threshold"]) == (True, 90)
        summary = payload["result_contract"]["summary"]
        assert (summary["threshold_fallback"], summary["original_threshold"]) == (True, 90)
        assert "evidence_report_path" not in json.dumps(payload), "#1190: no evidence report path anywhere"
        assert payload["threshold"] == 80, "the threshold the verdict was settled against"


# ---------------------------------------------------------------------------
# pipeline-contracts.md — Circuit Breaker Fallback Note
# ---------------------------------------------------------------------------


class TestPipelineContractsFallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(PIPELINE_CONTRACTS)

    def test_ts_circuit_breaker_mentions_fallback(self, text: str) -> None:
        cb_match = re.search(
            r"## Circuit Breakers\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert cb_match, "pipeline-contracts.md must have a Circuit Breakers section"
        section = cb_match.group(1)
        assert "fallback" in section.lower(), (
            "TS circuit breaker must mention fallback behavior for scores between 80% and threshold"
        )

    def test_ts_circuit_breaker_80_floor(self, text: str) -> None:
        cb_match = re.search(
            r"## Circuit Breakers\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert cb_match
        section = cb_match.group(1)
        assert "80%" in section, (
            "TS circuit breaker must reference the 80% floor in the halt condition"
        )


# ---------------------------------------------------------------------------
# #1190: no step, doc or result field names the retired fallback file
# ---------------------------------------------------------------------------


def _swept() -> list[pathlib.Path]:
    """Every text file under src/skf-test-skill/, every docs/ page, README.md and pipeline-contracts.md."""
    files = [p for p in sorted(TS_DIR.rglob("*")) if p.is_file() and p.suffix in (".md", ".py", ".toml", ".yaml",
                                                                                   ".json", ".txt")]
    files += sorted((REPO_ROOT / "docs").rglob("*.md")) + [REPO_ROOT / "README.md", PIPELINE_CONTRACTS]
    return files


class TestRetiredFallbackFile:
    def test_the_sweep_reads_the_files_it_names(self) -> None:
        names = {p.relative_to(REPO_ROOT).as_posix() for p in _swept()}
        for name in ("src/skf-test-skill/references/score.md", "src/skf-test-skill/scripts/build-result-context.py",
                     "src/skf-test-skill/references/invocation-contract.md", "docs/forge-auto.md",
                     "docs/verifying-a-skill.md", "docs/troubleshooting.md", "docs/workflows.md", "README.md",
                     "src/shared/references/pipeline-contracts.md"):
            assert name in names, name

    @pytest.mark.parametrize("token", RETIRED)
    def test_no_file_names_the_retired_token(self, token: str) -> None:
        naming = [p.relative_to(REPO_ROOT).as_posix() for p in _swept() if token in _read(p)]
        assert naming == [], f"{token} is still named in {naming}"

    def test_version_paths_names_the_file_only_as_an_older_record(self) -> None:
        text = _read(VERSION_PATHS)
        paragraphs = [p for p in text.split("\n\n") if "evidence-report-fallback.md" in p]
        assert paragraphs == [
            "An `evidence-report-fallback.md` in a version folder is an older test-skill run's threshold fallback "
            "record: test-skill now records a fallback in the test report's Completeness Score section, and the "
            "inventory still counts the file as SKF's."], paragraphs

    def test_score_md_reads_no_ledger(self) -> None:
        text = _read(SCORE_FILE)
        for gone in ("#### 4b.1", "{gapLedgerScript}", "{ledgerFile}", "gapLedgerScript:", "ledgerFile:"):
            assert gone not in text, gone

    def test_an_older_copy_stays_skf_owned(self, tmp_path: pathlib.Path) -> None:
        """A version folder holding an older run's fallback file is still SKF's, not a foreign entry."""
        spec = importlib.util.spec_from_file_location("skf_skill_inventory_fallback", INVENTORY)
        inventory = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(inventory)
        assert "evidence-report-fallback.md" in inventory.FORGE_VERSION_FILES
        version = tmp_path / "demo" / "1.0.0"
        version.mkdir(parents=True)
        (version / "provenance-map.json").write_bytes(b"{}")
        (version / "evidence-report-fallback.md").write_bytes(b"# Evidence Report: Threshold Fallback\n")
        group = inventory.classify_forge_group(tmp_path / "demo", "demo")
        assert (group["ownership"], group["foreign_entries"]) == ("skf", []), group
        # a file SKF never wrote is foreign beside it
        (version / "notes.md").write_bytes(b"mine\n")
        group = inventory.classify_forge_group(tmp_path / "demo", "demo")
        assert group["ownership"] == "mixed" and group["foreign_entries"] == ["1.0.0/notes.md"], group


# ---------------------------------------------------------------------------
# score.md §4b: the prior test report the subsection names, and the post-score cap context
# ---------------------------------------------------------------------------


class TestFallbackPriorReportContext:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_prior_test_report_check(self, fallback_section: str) -> None:
        flow = " ".join(fallback_section.split())
        assert "the latest earlier test report beside this one, or none found" in flow, (
            "§4b must say the subsection names the latest earlier test report beside this one, or none found"
        )
        # #1190: settle cannot know whether a repair ran between runs or whether earlier runs halted
        assert "remediation" not in flow.lower() and "first test run" not in flow, (
            "§4b must infer no remediation and no first run from the prior test report"
        )

    def test_post_score_cap_context(self, fallback_section: str) -> None:
        # The cap interaction is stated once, in §3d, which §4b's fallback follows.
        text = _read(SCORE_FILE)
        caps = text[text.find("### 3d."):text.find("### 4.")]
        assert "a capped run stays FAIL whatever the threshold" in caps, (
            "§3d must say a capped run never falls back"
        )


# ---------------------------------------------------------------------------
# score.md §4b — Workflow Context Variable Recording
# ---------------------------------------------------------------------------


class TestFallbackWorkflowContext:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_records_threshold_fallback(self, fallback_section: str) -> None:
        assert "threshold_fallback: true" in fallback_section, (
            "§4b must document recording threshold_fallback: true in workflow context"
        )

    def test_records_original_threshold(self, fallback_section: str) -> None:
        assert "original_threshold" in fallback_section, (
            "§4b must document recording original_threshold in workflow context"
        )

    def test_records_fallback_threshold_80(self, fallback_section: str, tmp_path: pathlib.Path) -> None:
        """#1186: settle writes the 80 floor as the report's threshold, so §4b binds no threshold of its own."""
        assert "fallback_threshold" not in fallback_section and "effective_threshold = 80" not in fallback_section
        _, report = _settle(tmp_path)
        for line in ("threshold: '80%'", "thresholdFallback: true", "originalThreshold: '90%'"):
            assert f"\n{line}\n" in report, line
        assert "evidenceReportPath" not in report
        assert sorted(p.name for p in tmp_path.iterdir()) == ["external.json", "report.md", "score.json"]


# ---------------------------------------------------------------------------
# The contract: Fallback Fields Omitted (Not False/Null) When No Fallback
# ---------------------------------------------------------------------------


class TestContractAbsentSemantics:
    def test_headless_envelope_omits_when_no_fallback(self) -> None:
        section = _contract_section("## Result Envelope (Headless)")
        assert "appear only when the threshold fallback fired" in section, (
            "the contract must state that fallback fields are omitted when no fallback occurred"
        )


# ---------------------------------------------------------------------------
# build-result-context.py: Fallback Fields Absent (Not False/Null) When No Fallback
# ---------------------------------------------------------------------------


class TestReportAbsentSemantics:
    def test_result_contract_absent_not_false(self, tmp_path: pathlib.Path) -> None:
        payload = _build(tmp_path, fallback=False)
        for record in (payload, payload["result_contract"], payload["result_contract"]["summary"]):
            for field in ("threshold_fallback", "original_threshold", "evidence_report_path"):
                assert field not in record, field
