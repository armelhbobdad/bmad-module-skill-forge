#!/usr/bin/env python3
"""Tests for skf-security-scan.py (the optional Snyk Agent Scan) and its wiring.

The fixtures under test/fixtures/security-scan/ are real snyk-agent-scan 0.6.11
outputs, its paths shortened to /work and /venv. `uvx snyk-agent-scan@0.6.11
--json --skills <package>` ran with a token against a local stand-in for
Snyk's analysis server that answered one prompt-injection risk (risky.json),
no risk (clean.json), no skill (no-skill.json) and HTTP 401
(analysis-error-401.json, whose run printed analysis-error-401.stderr and
still exited 0), and with a token and no reachable server (exit 1,
network-error.stderr ends its traceback). Without SNYK_TOKEN the same
command exits 1 and prints nothing on either stream. No run against Snyk's
own server is recorded: no SNYK_TOKEN was available (#892).

No test runs the real scanner: the unit tests stub _find_uvx and _scan, the
time-limit test runs a Python stand-in through the real runner, and the CLI
test puts a stub uvx on PATH.

The wiring tests pin the step-file prose of the four workflows that run the
helper, since step files are otherwise untested.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
HELPER = SRC / "shared" / "scripts" / "skf-security-scan.py"
FIXTURES = REPO / "test" / "fixtures" / "security-scan"
TOOL_LIST = SRC / "shared" / "tool-requirements.yaml"

spec = importlib.util.spec_from_file_location("skf_security_scan", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

STEP_FILES = {
    "quick-skill": SRC / "skf-quick-skill" / "references" / "write-and-validate.md",
    "create-skill": SRC / "skf-create-skill" / "references" / "validate.md",
    "update-skill": SRC / "skf-update-skill" / "references" / "write.md",
    "create-stack-skill": SRC / "skf-create-stack-skill" / "references" / "validate.md",
}
PROBE_ORDER = ["{project-root}/_bmad/skf/shared/scripts/skf-security-scan.py",
               "{project-root}/src/shared/scripts/skf-security-scan.py"]


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _response(*skills: dict, error: dict | None = None) -> str:
    path = {"path": "/work/skills", "server_risks": [], "skill_risks": list(skills)}
    if error is not None:
        path["error"] = error
    return json.dumps({"scan_path_responses": [path]})


def _skill(name: str = "demo", risks: dict | None = None, error: dict | None = None) -> dict:
    entry = {"name": name, "files": [{"name": "SKILL.md", "type": "instruction"}], "risk_indexes": risks or {}}
    if error is not None:
        entry["error"] = error
    return entry


# ---------------------------------------------------------------------------
# classify: the scanner's recorded outputs
# ---------------------------------------------------------------------------


class TestRecordedOutputs:
    def test_a_risk_reads_warn_with_one_finding(self):
        r = mod.classify(0, _fixture("risky.json"), "")
        assert r["security_result"] == "warn" and r["note"] == "the scanner reported 1 risk"
        assert r["findings"] == [{
            "skill": "demo", "risk": "prompt_injection_skill_instructions", "name": "Potential prompt injection",
            "score": 800, "evidence": "Instructs the agent to ignore prior instructions",
            "text": "Potential prompt injection (800/1000) in demo: Instructs the agent to ignore prior instructions",
        }]
        assert r["errors"] == [] and r["scanner"] == mod.SCANNER_SPEC

    def test_no_risk_reads_pass(self):
        r = mod.classify(0, _fixture("clean.json"), "")
        assert r == {"security_result": "pass", "scanner": mod.SCANNER_SPEC, "findings": [], "errors": [],
                     "note": "the scanner reported no risk"}

    def test_a_401_exits_0_and_never_reads_pass(self):
        """The scanner exits 0 on a rejected token: its JSON's analysis error makes the scan skipped."""
        r = mod.classify(0, _fixture("analysis-error-401.json"), _fixture("analysis-error-401.stderr"))
        assert r["security_result"] == "skipped" and r["findings"] == []
        assert r["note"].startswith("scanner could not analyse the package (Unauthorized.")
        assert r["errors"] == ["Unauthorized. Please check your SNYK_TOKEN environment variable or your push key."]

    def test_no_skill_reads_skipped(self):
        r = mod.classify(0, _fixture("no-skill.json"), "")
        assert (r["security_result"], r["note"]) == ("skipped", "scanner found no skill")

    def test_a_token_less_run_exits_1_with_no_output(self):
        r = mod.classify(1, "", "")
        assert (r["security_result"], r["note"]) == ("skipped", "scanner exited 1 with no output")

    def test_a_network_error_quotes_the_last_stderr_line(self):
        r = mod.classify(1, "", _fixture("network-error.stderr"))
        assert r["security_result"] == "skipped"
        assert r["note"] == ("scanner could not run (aiohttp.client_exceptions.ClientProxyConnectionError: Cannot "
                             "connect to host 127.0.0.1:9 ssl:default [Connect call failed ('127.0.0.1', 9)])")


# ---------------------------------------------------------------------------
# classify: every other rule
# ---------------------------------------------------------------------------


class TestClassify:
    @pytest.mark.parametrize("stdout", [
        "", "Snyk Agent Scan v0.6.11\n\nTo use Agent Scan, set the SNYK_TOKEN environment variable.\n", "[]",
        '{"scan_path_responses": {}}', '{"other": 1}', '{"scan_path_responses": ["x"]}', "{not json",
    ], ids=["empty", "rich-text", "list", "paths-not-a-list", "other-object", "path-not-an-object", "broken"])
    def test_output_that_is_not_the_scanner_json_never_reads_pass(self, stdout):
        r = mod.classify(0, stdout, "")
        assert (r["security_result"], r["note"]) == ("skipped", "scanner output not recognized")

    def test_a_risk_reads_warn_whatever_the_exit_code(self):
        """--ci exits 1 on a risk and still prints the JSON; a risk is never hidden behind an exit code."""
        r = mod.classify(1, _fixture("risky.json"), "")
        assert r["security_result"] == "warn" and len(r["findings"]) == 1

    def test_a_clean_report_with_a_non_zero_exit_reads_skipped(self):
        r = mod.classify(2, _fixture("clean.json"), "boom\n\n")
        assert (r["security_result"], r["note"]) == ("skipped", "scanner could not run (boom)")

    def test_the_time_limit_reads_skipped(self):
        r = mod.classify(None, _fixture("risky.json"), "", timeout=110)
        assert (r["security_result"], r["note"]) == ("skipped", "scanner did not finish within 110 s")

    def test_a_stray_line_before_the_json_is_skipped(self):
        r = mod.classify(0, "a notice\n" + _fixture("clean.json"), "")
        assert r["security_result"] == "pass"

    def test_risks_and_an_error_read_warn_and_name_the_error(self):
        failed = {"message": "could not read scripts/run.sh", "is_failure": True, "category": "skill_scan_error"}
        stdout = _response(_skill("demo", {"malicious_code": {"score": 650, "evidence": "curl | sh"},
                                           "secret_detection": {"score": 900, "evidence": "an API key"}}),
                           _skill("other", error=failed))
        r = mod.classify(0, stdout, "")
        assert r["security_result"] == "warn" and [f["risk"] for f in r["findings"]] == ["malicious_code",
                                                                                         "secret_detection"]
        assert r["note"] == "the scanner reported 2 risks; it could not analyse part of the package (could not read " \
                            "scripts/run.sh)"
        assert r["errors"] == ["could not read scripts/run.sh"]

    def test_an_error_that_is_no_failure_does_not_skip(self):
        stdout = _response(_skill(), error={"message": "config file not found", "is_failure": False,
                                            "category": "file_not_found"})
        assert mod.classify(0, stdout, "")["security_result"] == "pass"

    def test_a_skill_error_alone_reads_skipped(self):
        stdout = _response(_skill(error={"message": "Invalid SKILL.md file", "category": "skill_scan_error"}))
        r = mod.classify(0, stdout, "")
        assert (r["security_result"], r["note"]) == ("skipped",
                                                     "scanner could not analyse the package (Invalid SKILL.md file)")

    def test_a_server_risk_counts_and_an_unknown_risk_keeps_its_key(self):
        stdout = json.dumps({"scan_path_responses": [{"path": "/work", "server_risks": [
            {"name": "files", "risk_indexes": {"untrusted_content": {"score": 300, "evidence": "reads web pages"}}}],
            "skill_risks": [_skill(risks={"new_risk": {"evidence": "x"}})]}]})
        r = mod.classify(0, stdout, "")
        assert r["security_result"] == "warn"
        assert [f["text"] for f in r["findings"]] == ["new_risk (?/1000) in demo: x",
                                                      "Untrusted content (300/1000) in files: reads web pages"]

    def test_long_evidence_is_one_short_line_in_text_and_whole_in_evidence(self):
        evidence = "line one\n" + "word " * 200
        r = mod.classify(0, _response(_skill(risks={"malicious_code": {"score": 1, "evidence": evidence}})), "")
        [finding] = r["findings"]
        assert finding["evidence"] == evidence
        assert "\n" not in finding["text"] and len(finding["text"]) <= mod.MAX_LINE and finding["text"].endswith("...")


# ---------------------------------------------------------------------------
# run_scan: the token, uvx and the command
# ---------------------------------------------------------------------------


class TestRunScan:
    @pytest.fixture
    def calls(self, monkeypatch):
        seen = []

        def scan(argv, timeout):
            seen.append((argv, timeout))
            return 0, _fixture("clean.json").encode("utf-8"), b""

        monkeypatch.setattr(mod, "_find_uvx", lambda: "/bin/uvx")
        monkeypatch.setattr(mod, "_scan", scan)
        return seen

    @pytest.mark.parametrize("env", [{}, {"SNYK_TOKEN": ""}, {"SNYK_TOKEN": " \t\n"}],
                             ids=["unset", "empty", "whitespace"])
    def test_no_token_starts_nothing(self, calls, monkeypatch, tmp_path, env):
        monkeypatch.setattr(mod, "_find_uvx", lambda: pytest.fail("uvx looked up without a token"))
        r = mod.run_scan(tmp_path, env=env)
        assert (r["security_result"], r["note"]) == ("skipped", "SNYK_TOKEN not configured") and calls == []

    def test_the_command_pins_the_scanner_and_reads_its_json(self, calls, tmp_path):
        r = mod.run_scan(tmp_path / "pkg", timeout=42, env={"SNYK_TOKEN": "t"})
        assert r["security_result"] == "pass"
        assert calls == [(["/bin/uvx", mod.SCANNER_SPEC, "--json", "--skills", os.path.abspath(tmp_path / "pkg")],
                          42)]
        assert "--ci" not in calls[0][0], "--ci would need --dangerously-run-mcp-servers"

    def test_no_uvx_reads_skipped(self, calls, monkeypatch, tmp_path):
        monkeypatch.setattr(mod, "_find_uvx", lambda: None)
        r = mod.run_scan(tmp_path, env={"SNYK_TOKEN": "t"})
        assert (r["security_result"], r["note"]) == ("skipped", "uvx not found") and calls == []

    def test_a_scanner_that_cannot_start_reads_skipped(self, calls, monkeypatch, tmp_path):
        def refuse(argv, timeout):
            raise OSError("exec format error")

        monkeypatch.setattr(mod, "_scan", refuse)
        r = mod.run_scan(tmp_path, env={"SNYK_TOKEN": "t"})
        assert (r["security_result"], r["note"]) == ("skipped", "scanner could not start (exec format error)")

    def test_the_default_time_limit_leaves_room_under_two_minutes(self):
        sibling = mod._sibling()
        assert mod.DEFAULT_TIMEOUT_SEC + 2 * sibling.KILL_WAIT_SEC + 5 < 120

    def test_the_sibling_names_this_helper_among_the_scripts_that_load_it(self):
        """skf-source-tree.py lists each script that loads it and the names it takes, so a change to _run's
        4-tuple or KILL_WAIT_SEC is checked against this helper too."""
        sibling = (HELPER.parent / "skf-source-tree.py").read_text(encoding="utf-8")
        start = sibling.index("# skf-check-workspace-drift.py (upstream)")
        comment = " ".join(line.lstrip("# ") for line in sibling[start:sibling.index("\ndef ", start)].splitlines())
        assert ("skf-security-scan.py for _run and _resolve_outside_cwd (its test reads KILL_WAIT_SEC): keep those "
                "names and what they take and return.") in comment
        names = {name for name in ("_run", "_resolve_outside_cwd") if f"_sibling().{name}(" in HELPER.read_text(
            encoding="utf-8")}
        assert names == {"_run", "_resolve_outside_cwd"}


class TestRealSubprocess:
    def test_the_time_limit_stops_the_scanner_and_what_it_started(self, monkeypatch, tmp_path):
        """The runner kills the whole group: a grandchild that would outlive the scanner never writes its marker.

        The marker path goes in as an argument, so a Windows path's backslashes cannot break the code.
        """
        marker = tmp_path / "grandchild-survived"
        script = tmp_path / "fake_scanner.py"
        script.write_text(textwrap.dedent(f"""
            import subprocess, sys, time
            subprocess.Popen([sys.executable, "-c",
                              "import pathlib, sys, time; time.sleep(3); pathlib.Path(sys.argv[1]).write_text('x')",
                              {str(marker)!r}])
            time.sleep(60)
            """), encoding="utf-8")
        monkeypatch.setattr(mod, "_find_uvx", lambda: "uvx")
        monkeypatch.setattr(mod, "scanner_command", lambda uvx, package: [sys.executable, str(script)])
        start = time.monotonic()
        r = mod.run_scan(tmp_path, timeout=1, env={"SNYK_TOKEN": "t"})
        assert (r["security_result"], r["note"]) == ("skipped", "scanner did not finish within 1 s")
        assert time.monotonic() - start < 20
        time.sleep(4)
        assert not marker.exists()

    def _cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=60, env=env)

    def test_parse_prints_one_result_and_exits_0(self):
        proc = self._cli("parse", "--stdout-file", str(FIXTURES / "risky.json"), "--exit-code", "0")
        assert proc.returncode == 0 and proc.stderr == ""
        assert json.loads(proc.stdout)["security_result"] == "warn"
        assert list(json.loads(proc.stdout)) == list(mod.RESULT_KEYS)

    def test_run_without_a_token_exits_0(self, tmp_path):
        env = {k: v for k, v in os.environ.items() if k != "SNYK_TOKEN"}
        proc = self._cli("run", "--package", str(tmp_path), env=env)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["note"] == "SNYK_TOKEN not configured"

    @pytest.mark.parametrize("args", [["run", "--package", "no-such-folder"], ["run"],
                                      ["run", "--package", ".", "--timeout", "0"],
                                      ["parse", "--stdout-file", "no-such-file", "--exit-code", "0"]],
                             ids=["missing-folder", "no-package", "zero-timeout", "missing-stdout-file"])
    def test_a_usage_error_exits_2(self, args):
        proc = self._cli(*args)
        assert proc.returncode == 2 and proc.stdout == ""

    @pytest.mark.skipif(os.name == "nt", reason="POSIX shell shim")
    def test_run_finds_uvx_on_path_and_passes_the_package(self, tmp_path):
        """The stub exits 1 with no output when SNYK_TOKEN does not reach it, as the real scanner does, so a
        runner whose child environment dropped the token would read `skipped` here."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        seen = tmp_path / "argv.txt"
        uvx = bin_dir / "uvx"
        uvx.write_text(f"#!/bin/sh\n[ \"$SNYK_TOKEN\" = t ] || exit 1\nprintf '%s\\n' \"$@\" > '{seen}'\n"
                       f"cat '{FIXTURES / 'risky.json'}'\n", encoding="utf-8")
        uvx.chmod(0o755)
        package = tmp_path / "my skill"
        package.mkdir()
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "SNYK_TOKEN": "t"}
        proc = subprocess.run([sys.executable, str(HELPER), "run", "--package", str(package)], capture_output=True,
                              text=True, encoding="utf-8", timeout=60, env=env, cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["security_result"] == "warn"
        assert seen.read_text(encoding="utf-8").splitlines() == [mod.SCANNER_SPEC, "--json", "--skills",
                                                                 str(package)]


# ---------------------------------------------------------------------------
# The pin and its tool-requirements entry
# ---------------------------------------------------------------------------


def test_the_pinned_scanner_is_the_one_tool_requirements_names():
    entry = yaml.safe_load(TOOL_LIST.read_text(encoding="utf-8"))["tools"]["snyk_agent_scan"]
    name, version = mod.SCANNER_SPEC.split("@")
    assert entry["name"] == name and entry["kind"] == "optional" and entry["minimum"] is None
    assert f"`uvx {mod.SCANNER_SPEC} --json --skills <package>`" in entry["basis"]
    assert f"response models of snyk-agent-scan {version}" in entry["basis"]
    assert entry["workflows"] == sorted(STEP_FILES)
    assert "version_command" not in entry and entry["acknowledged_as"] == "Snyk Agent Scan"


def test_the_readme_credits_the_scan_to_snyk_agent_scan_not_skill_check():
    """SKF runs skill-check with the scan left out, so its Acknowledgements row names no scan, as the architecture
    page's tool table does."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| \[([^\]]+)\]\([^)]*\) *\| (.*?) *\|$", readme, re.M))
    assert rows["skill-check"] == "Skill validation, auto-fix and quality scoring"
    assert "security" not in rows["skill-check"].lower()
    assert rows["Snyk Agent Scan"].startswith("Security scanning for prompt injection")
    architecture = (REPO / "docs" / "architecture.md").read_text(encoding="utf-8")
    [row] = [line for line in architecture.splitlines() if line.startswith("| **`skill-check`** |")]
    assert "security" not in row.lower()


# ---------------------------------------------------------------------------
# Wiring: the four workflows run the helper, and skill-check runs no scan
# ---------------------------------------------------------------------------


def _frontmatter(text: str) -> dict:
    return yaml.safe_load(text.split("---\n", 2)[1])


@pytest.mark.parametrize("workflow", sorted(STEP_FILES))
def test_each_workflow_runs_the_helper_and_keeps_the_scan_out_of_skill_check(workflow):
    text = STEP_FILES[workflow].read_text(encoding="utf-8")
    assert _frontmatter(text)["securityScanProbeOrder"] == PROBE_ORDER
    assert "`{securityScanHelper}` ← first existing path in `{securityScanProbeOrder}`" in text
    assert len(re.findall(r'uv run \{securityScanHelper\} run --package "[^"]+"', text)) == 1
    assert "rely on the JSON it prints, never on an exit code" in text
    assert "skf-security-scan.py missing" in text and "skf-security-scan.py printed no result" in text
    # every skill-check validation call leaves the scan out (Create Skill's probed flag included)
    calls = [line for line in text.splitlines() if re.search(r"npx skill-check check [<\"{]", line)]
    assert calls, workflow
    for line in calls:
        for call in re.findall(r"npx skill-check check [^`\n]*", line):
            assert "--no-security-scan" in call or "{security_scan_flag}" in call, (workflow, call)
    # the reading rule built on skill-check's stderr tail and finding codes is gone
    for stale in ("finding code", "does not pass the scan's findings on", "(#892)", "mcp-scan", "security[]",
                  "To use Agent Scan", "skill-check.stderr` and the exit code"):
        assert stale not in text, (workflow, stale)


def test_the_helper_runs_whether_or_not_skill_check_is_available():
    quick, create, update, stack = (STEP_FILES[name].read_text(encoding="utf-8") for name in
                                    ("quick-skill", "create-skill", "update-skill", "create-stack-skill"))
    assert "**Security scan.** Run it whether or not skill-check ran." in quick
    assert ("- If fails (command not found or error): skip to the frontmatter validator in section 4; the security "
            "scan at the end of section 4 still runs") in quick
    assert "### 5. Security Scan\n\nRun the scan whether or not skill-check is available." in create
    assert "**Security scan**, whether or not skill-check is available:" in update
    assert "### 9. Security Scan\n\nRun the scan whether or not skill-check is available." in stack
    assert "- If exits 0: Use skill-check for automated validation in section 3." in stack
    assert "security scan skipped: skill-check unavailable" not in quick + create + update + stack
    assert "Security: SKIP (skill-check unavailable)" not in update
