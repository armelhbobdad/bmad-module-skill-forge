#!/usr/bin/env python3
"""install-smoke.yaml: the post-publish install smoke test and its record.

Issues #568 and #569. The workflow only runs for real on a dispatch after a
publish, so these tests read it with PyYAML and run its steps' own `run:`
scripts under `bash -e`, with stub `npm`, `npx` and `gh` commands first on
PATH. A stub answers from a list of rules the test gives (the first rule
whose `match` is a substring of the joined arguments wins) and logs every
call, so a test can assert what the step asked npm or GitHub.

Covers:
  - The run title and the concurrency group name the requested version, and
    two dispatches for one version queue (cancel-in-progress false)
  - Only the final job may write (contents: write), the legs keep the
    workflow's contents: read, and the final job runs after a failed leg
    but not on a cancelled run
  - The version input offers latest or an exact version, never rc or alpha,
    has no default, and no run script interpolates it
  - Each leg uploads the file the final job downloads and reads
  - A leg passes only when --version prints the version npm resolves the
    input to (CR stripped), and fails on another version (1.0.0-01
    included), on an input that resolves to several versions (with a
    one-line annotation, and no expected version written) and on a version
    npm does not have, before npx runs
  - Each leg records its row (OS, Node, npm, expected, printed, outcome)
    after a failure too
  - The final job writes install-smoke.json and one summary row per OS,
    and attaches the file to the GitHub Release of the version the legs
    resolved; it attaches nothing and fails when the legs resolved
    different versions or a value that is not one version, when there is
    no such Release or when no leg left a result
  - Every RELEASING.md section the workflow points to exists

The behaviour tests need bash, jq and node (all on the GitHub-hosted Ubuntu
runner) and are skipped on Windows.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "install-smoke.yaml"
RELEASING = REPO_ROOT / "docs" / "_internal" / "RELEASING.md"

SMOKE = "Run npx bmad-module-skill-forge --version"
RECORD_LEG = "Record the result"
UPLOAD = "Upload the result"
DOWNLOAD = "Download the results"
ATTACH = "Write install-smoke.json and attach it to the Release"
OSES = ["ubuntu-latest", "windows-latest", "macos-latest"]

needs_shell = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None or shutil.which("jq") is None or shutil.which("node") is None,
    reason="the step scripts run under bash with jq and node, as on the Ubuntu runner",
)

# One stub for npm, npx and gh, called with the tool's name first: its rules
# are in <STUB_DIR>/<name>.json, and every call is logged to calls.jsonl.
STUB = """\
import json, os, sys
d = os.environ["STUB_DIR"]
name = sys.argv[1]
args = sys.argv[2:]
with open(os.path.join(d, "calls.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps([name] + args) + "\\n")
line = " ".join(args)
with open(os.path.join(d, name + ".json"), encoding="utf-8") as f:
    rules = json.load(f)
for rule in rules:
    if rule["match"] in line:
        sys.stdout.write(rule.get("stdout", ""))
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(rule.get("exit", 0))
sys.stderr.write("stub %s: no rule for: %s\\n" % (name, line))
sys.exit(97)
"""


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def job(name: str) -> dict:
    return load_workflow()["jobs"][name]


def step(job_name: str, name: str) -> dict:
    matches = [s for s in job(job_name)["steps"] if s.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r} in {job_name}, found {len(matches)}"
    return matches[0]


class Result:
    def __init__(self, proc: subprocess.CompletedProcess, stub_dir: Path):
        self.code = proc.returncode
        self.out = proc.stdout + proc.stderr
        log = stub_dir / "calls.jsonl"
        self.calls = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        summary = stub_dir / "summary.md"
        self.summary = summary.read_text(encoding="utf-8") if summary.exists() else ""

    def called(self, name: str, *parts: str) -> list[list[str]]:
        """Calls of `name` whose joined arguments contain every part."""
        return [c for c in self.calls if c[0] == name and all(p in " ".join(c[1:]) for p in parts)]


def run_step(
    tmp_path: Path,
    job_name: str,
    name: str,
    env: dict[str, str],
    npm: list[dict] | None = None,
    npx: list[dict] | None = None,
    gh: list[dict] | None = None,
) -> Result:
    stub_dir = tmp_path / "stub"
    bin_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    bin_dir.mkdir(exist_ok=True)
    stub_py = stub_dir / "stub.py"
    stub_py.write_text(STUB, encoding="utf-8")
    for tool, rules in (("npm", npm), ("npx", npx), ("gh", gh)):
        exe = bin_dir / tool
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub_py}" {tool} "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
        (stub_dir / f"{tool}.json").write_text(json.dumps(rules or []), encoding="utf-8")
    script = tmp_path / "step.sh"
    script.write_text(step(job_name, name)["run"], encoding="utf-8")
    full_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(tmp_path),
        "STUB_DIR": str(stub_dir),
        "RUNNER_TEMP": str(tmp_path / "runner-temp"),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_RUN_ID": "42",
        "GITHUB_STEP_SUMMARY": str(stub_dir / "summary.md"),
        **env,
    }
    proc = subprocess.run(
        ["bash", "-e", str(script)],
        cwd=tmp_path,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return Result(proc, stub_dir)


def resolves(version: str) -> list[dict]:
    """npm rules: `npm view` resolves the input to `version`."""
    return [{"match": "view bmad-module-skill-forge@", "stdout": version + "\n"}]


def prints(output: str) -> list[dict]:
    """npx rules: --version prints `output`."""
    return [{"match": "--version", "stdout": output}]


def result_dir(tmp_path: Path) -> Path:
    return tmp_path / "runner-temp" / "install-smoke"


# --------------------------------------------------------------------------
# The workflow's shape
# --------------------------------------------------------------------------


def test_the_run_title_and_the_concurrency_group_name_the_requested_version():
    workflow = load_workflow()
    assert workflow["run-name"] == "Install smoke ${{ inputs.version }}"
    assert "${{ inputs.version }}" in workflow["concurrency"]["group"]
    # Queue, never cancel: a cancelled run would leave no record.
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_only_the_final_job_writes_and_it_runs_after_a_failed_leg():
    workflow = load_workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in workflow["jobs"]["smoke"]
    record = workflow["jobs"]["record"]
    assert record["permissions"] == {"contents": "write"}
    assert record["needs"] == "smoke"
    # After a failed leg, but not after a cancel: a cancelled run's partial
    # result would replace a complete record (gh release upload --clobber).
    assert record["if"] == "${{ !cancelled() }}"
    assert set(workflow["jobs"]) == {"smoke", "record"}


def test_the_version_input_offers_latest_or_an_exact_version():
    # PyYAML reads the bare `on` key as the boolean True.
    trigger = load_workflow()[True]
    version = trigger["workflow_dispatch"]["inputs"]["version"]
    assert version["required"] is True
    # No default: the dispatch form asks for a version instead of offering
    # latest, which RELEASING.md says not to dispatch right after a publish.
    assert "default" not in version
    assert not re.search(r"\b(rc|alpha|beta)\b", version["description"]), version["description"]
    assert "exact version" in version["description"]
    header = WORKFLOW.read_text(encoding="utf-8").split("\nname:", 1)[0]
    assert "-f version=3.0.0" in header
    assert "`rc`, `alpha`" not in header


def test_no_run_script_interpolates_the_input():
    for job_name, body in load_workflow()["jobs"].items():
        for s in body["steps"]:
            assert "${{" not in s.get("run", ""), f"{job_name}: {s.get('name')}"


def test_each_leg_uploads_the_file_the_final_job_reads():
    upload = step("smoke", UPLOAD)
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == "install-smoke-${{ matrix.os }}"
    assert upload["with"]["path"].endswith("/install-smoke/install-smoke-${{ matrix.os }}.json")
    download = step("record", DOWNLOAD)
    assert download["with"]["pattern"] == "install-smoke-*"
    assert str(download["with"]["merge-multiple"]).lower() == "true"
    assert 'FILES=(results/install-smoke-*.json)' in step("record", ATTACH)["run"]
    assert step("smoke", RECORD_LEG)["if"] == "always()"
    assert job("smoke")["strategy"]["matrix"]["os"] == OSES


def test_every_releasing_md_section_the_workflow_points_to_exists():
    text = WORKFLOW.read_text(encoding="utf-8")
    releasing = RELEASING.read_text(encoding="utf-8")
    flat = re.sub(r"\s*\n\s*#?\s*", " ", text)
    for section in ("After the publish", "Dist-tag policy"):
        assert f"§ {section}" in flat
        assert re.search(rf"^#+ {re.escape(section)}$", releasing, re.MULTILINE), section
    scenarios = set(re.findall(r"^### Scenario ([A-Z])\b", releasing, re.MULTILINE))
    pointers = set(re.findall(r"RELEASING\.md, Scenario ([A-Z])\b", flat))
    assert pointers and pointers <= scenarios, sorted(pointers - scenarios)


# --------------------------------------------------------------------------
# A leg: Run npx bmad-module-skill-forge --version
# --------------------------------------------------------------------------


@needs_shell
@pytest.mark.parametrize(
    ("requested", "resolved", "output"),
    [
        pytest.param("3.0.0", "3.0.0", "3.0.0\n", id="exact version"),
        pytest.param("latest", "3.0.0", "3.0.0\n", id="dist-tag"),
        pytest.param("3.0.0", "3.0.0", "3.0.0\r\n", id="CRLF output"),
        pytest.param("3.0.0-rc.1", "3.0.0-rc.1", "3.0.0-rc.1\n", id="prerelease"),
    ],
)
def test_a_leg_passes_when_version_prints_the_resolved_version(tmp_path, requested, resolved, output):
    result = run_step(tmp_path, "smoke", SMOKE, {"VERSION": requested}, npm=resolves(resolved), npx=prints(output))
    assert result.code == 0, result.out
    assert result.called("npm", "view", f"bmad-module-skill-forge@{requested}", "version")
    assert result.called("npx", "--yes", f"bmad-module-skill-forge@{requested}", "--version")
    assert (result_dir(tmp_path) / "expected").read_text(encoding="utf-8") == resolved
    assert (result_dir(tmp_path) / "actual").read_text(encoding="utf-8") == resolved


@needs_shell
@pytest.mark.parametrize(
    "output",
    [
        pytest.param("1.0.0-01\n", id="leading zero"),
        pytest.param("1.0.0-.\n", id="empty identifier"),
        pytest.param("01.0.0\n", id="leading zero major"),
        pytest.param("0.9.9\n", id="stale registry read"),
        pytest.param("\n", id="nothing"),
    ],
)
def test_a_leg_fails_when_version_prints_another_version(tmp_path, output):
    result = run_step(tmp_path, "smoke", SMOKE, {"VERSION": "1.0.0"}, npm=resolves("1.0.0"), npx=prints(output))
    assert result.code == 1, result.out
    assert "::error::--version printed" in result.out
    assert "not 1.0.0" in result.out
    assert (result_dir(tmp_path) / "actual").read_text(encoding="utf-8") == output.strip()


@needs_shell
def test_a_leg_fails_when_the_input_resolves_to_several_versions(tmp_path):
    several = "bmad-module-skill-forge@2.0.0 '2.0.0'\nbmad-module-skill-forge@2.1.0 '2.1.0'\n"
    npm = [{"match": "view", "stdout": several}]
    result = run_step(tmp_path, "smoke", SMOKE, {"VERSION": "^2"}, npm=npm, npx=prints("2.1.0\n"))
    assert result.code == 1, result.out
    annotation = [line for line in result.out.splitlines() if line.startswith("::error::")]
    assert len(annotation) == 1, result.out
    assert "does not resolve to one published version" in annotation[0]
    assert "bmad-module-skill-forge@2.1.0 '2.1.0'" in annotation[0]
    assert not result.called("npx")
    # Nothing to record as the expected version: the final job then finds no
    # single version and attaches the record to no Release.
    assert not (result_dir(tmp_path) / "expected").exists()


@needs_shell
def test_a_leg_fails_when_npm_has_no_such_version(tmp_path):
    npm = [{"match": "view", "exit": 1, "stderr": "npm error 404 No match found for version 9.9.9\n"}]
    result = run_step(tmp_path, "smoke", SMOKE, {"VERSION": "9.9.9"}, npm=npm, npx=prints("9.9.9\n"))
    assert result.code == 1, result.out
    assert "::error::npm has no bmad-module-skill-forge@9.9.9" in result.out
    assert not result.called("npx")
    assert not (result_dir(tmp_path) / "expected").exists()


# --------------------------------------------------------------------------
# A leg: Record the result
# --------------------------------------------------------------------------


@needs_shell
def test_each_leg_records_its_row(tmp_path):
    folder = result_dir(tmp_path)
    folder.mkdir(parents=True)
    (folder / "expected").write_bytes(b"3.0.0")
    (folder / "actual").write_bytes(b"3.0.0")
    npm = [{"match": "--version", "stdout": "10.9.2\n"}]
    result = run_step(tmp_path, "smoke", RECORD_LEG, {"LEG_OS": "macos-latest", "OUTCOME": "success"}, npm=npm)
    assert result.code == 0, result.out
    row = json.loads((folder / "install-smoke-macos-latest.json").read_text(encoding="utf-8"))
    assert row["os"] == "macos-latest"
    assert row["node"].startswith("v")
    assert row["npm"] == "10.9.2"
    assert (row["expected"], row["actual"], row["result"]) == ("3.0.0", "3.0.0", "success")


@needs_shell
def test_a_leg_that_failed_before_npx_still_records_its_row(tmp_path):
    npm = [{"match": "--version", "stdout": "10.9.2\n"}]
    result = run_step(tmp_path, "smoke", RECORD_LEG, {"LEG_OS": "windows-latest", "OUTCOME": "failure"}, npm=npm)
    assert result.code == 0, result.out
    row = json.loads((result_dir(tmp_path) / "install-smoke-windows-latest.json").read_text(encoding="utf-8"))
    assert (row["expected"], row["actual"], row["result"]) == ("", "", "failure")


# --------------------------------------------------------------------------
# The final job: Write install-smoke.json and attach it to the Release
# --------------------------------------------------------------------------


def leg(os_name: str, expected: str = "3.0.0", actual: str = "3.0.0", result: str = "success") -> dict:
    row = {"os": os_name, "node": "v22.12.0", "npm": "10.9.2"}
    return {**row, "expected": expected, "actual": actual, "result": result}


def write_results(tmp_path: Path, legs: list[dict]) -> None:
    folder = tmp_path / "results"
    folder.mkdir()
    for row in legs:
        (folder / f"install-smoke-{row['os']}.json").write_text(json.dumps(row), encoding="utf-8")


RELEASE_FOUND = [
    {"match": "release view v3.0.0", "stdout": '{"tagName":"v3.0.0"}\n'},
    {"match": "release upload v3.0.0 install-smoke.json --clobber", "stdout": ""},
]


@needs_shell
def test_the_final_job_attaches_install_smoke_json_to_the_release(tmp_path):
    write_results(tmp_path, [leg(name) for name in reversed(OSES)])
    env = {"VERSION": "3.0.0", "SMOKE_RESULT": "success"}
    result = run_step(tmp_path, "record", ATTACH, env, gh=RELEASE_FOUND)
    assert result.code == 0, result.out
    assert len(result.called("gh", "release", "upload", "v3.0.0", "install-smoke.json", "--clobber")) == 1
    record = json.loads((tmp_path / "install-smoke.json").read_text(encoding="utf-8"))
    assert record["package"] == "bmad-module-skill-forge"
    assert (record["requested"], record["result"]) == ("3.0.0", "success")
    assert record["run"] == "https://github.com/owner/repo/actions/runs/42"
    assert [row["os"] for row in record["legs"]] == sorted(OSES)
    rows = [line for line in result.summary.splitlines() if line.startswith("| ") and "-latest" in line]
    assert rows == [f"| {name} | v22.12.0 | 10.9.2 | 3.0.0 | 3.0.0 | success |" for name in sorted(OSES)]
    assert "Recorded as `install-smoke.json` on the GitHub Release `v3.0.0`." in result.summary


@needs_shell
def test_a_failed_leg_is_recorded_with_the_others(tmp_path):
    legs = [
        leg("ubuntu-latest"),
        leg("windows-latest", actual="1.0.0-01", result="failure"),
        leg("macos-latest", expected="", actual="", result="failure"),
    ]
    write_results(tmp_path, legs)
    env = {"VERSION": "latest", "SMOKE_RESULT": "failure"}
    result = run_step(tmp_path, "record", ATTACH, env, gh=RELEASE_FOUND)
    assert result.code == 0, result.out
    assert result.called("gh", "release", "upload", "v3.0.0")
    record = json.loads((tmp_path / "install-smoke.json").read_text(encoding="utf-8"))
    assert record["result"] == "failure"
    assert "| windows-latest | v22.12.0 | 10.9.2 | 3.0.0 | 1.0.0-01 | failure |" in result.summary


@needs_shell
def test_legs_that_read_different_versions_attach_nothing(tmp_path):
    write_results(tmp_path, [leg("ubuntu-latest", "3.0.0", "3.0.0"), leg("macos-latest", "2.2.0", "2.2.0")])
    result = run_step(tmp_path, "record", ATTACH, {"VERSION": "latest", "SMOKE_RESULT": "success"}, gh=RELEASE_FOUND)
    assert result.code == 1, result.out
    assert "did not resolve 'latest' to one version" in result.out
    assert "Dispatch again with an exact version." in result.out
    assert not result.called("gh")
    # The table is still written: the summary shows what each leg read.
    assert "| macos-latest | v22.12.0 | 10.9.2 | 2.2.0 | 2.2.0 | success |" in result.summary


@needs_shell
def test_a_leg_that_recorded_several_versions_attaches_nothing(tmp_path):
    several = "bmad-module-skill-forge@2.0.0 '2.0.0'\nbmad-module-skill-forge@2.1.0 '2.1.0'"
    write_results(tmp_path, [leg(name, expected=several, actual="", result="failure") for name in OSES])
    result = run_step(tmp_path, "record", ATTACH, {"VERSION": "^2", "SMOKE_RESULT": "failure"}, gh=RELEASE_FOUND)
    assert result.code == 1, result.out
    assert "did not resolve '^2' to one version" in result.out
    assert "Dispatch again with an exact version." in result.out
    assert "Could not read the GitHub Release" not in result.out
    assert not result.called("gh")


@needs_shell
def test_no_release_for_the_version_fails_and_says_so(tmp_path):
    write_results(tmp_path, [leg(name) for name in OSES])
    gh = [{"match": "release view v3.0.0", "exit": 1, "stderr": "release not found\n"}]
    result = run_step(tmp_path, "record", ATTACH, {"VERSION": "3.0.0", "SMOKE_RESULT": "success"}, gh=gh)
    assert result.code == 1, result.out
    assert "Could not read the GitHub Release v3.0.0" in result.out
    assert "RELEASING.md, Scenario E" in result.out
    assert not result.called("gh", "release", "upload")
    assert "No GitHub Release `v3.0.0` was found: the result is in this summary only." in result.summary


@needs_shell
def test_no_result_from_any_leg_fails(tmp_path):
    (tmp_path / "results").mkdir()
    result = run_step(tmp_path, "record", ATTACH, {"VERSION": "3.0.0", "SMOKE_RESULT": "cancelled"}, gh=RELEASE_FOUND)
    assert result.code == 1, result.out
    assert "No leg left a result" in result.out
    assert not result.called("gh")
