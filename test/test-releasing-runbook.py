#!/usr/bin/env python3
"""docs/_internal/RELEASING.md: the maintainer runbook's commands and records.

Issues #568, #569, #574 and #575. The runbook's commands run against the
live repository and the npm registry, mostly during an incident, so these
tests check what can be checked without them: every command reads the
ruleset by name and stops on an empty id, the baselines the commands read
are committed where they say, every restore reads the one committed filter,
which agrees with the baseline, and the prose names no planning label, no
file outside the repository and no pipeline as future work.

Covers:
  - Preconditions: before Branch Protection, with a check for gh, its admin
    rights, jq, node, the npm login, the package's owners, npm's version and
    the account's 2FA
  - No command names a ruleset or environment id; a recorded id is labelled
    as the value at the time of writing
  - Every ruleset lookup pipes gh into jq with release.yaml's guard and is
    followed by an empty-id check before any use; the guard turns an error
    body or a list without Default into nothing (run with jq)
  - The three baselines are committed in release-audits/baselines/, parse,
    and are the files the capture writes and the restore reads
  - Every restore snippet reads the one filter file,
    release-audits/baselines/ruleset-put.jq, and the drill record names it;
    run on the baseline, it keeps every field a PUT takes and every rule,
    minus the keys of the required_status_checks rule a PUT has refused
    (do_not_enforce_on_create, a null integration_id)
  - The restore shows its diff and sends the PUT only on an answer of y
    (run with a stub gh)
  - The environment's restore JSON agrees with its baseline, which the
    runbook leaves to this test instead of a check by hand
  - Scenario C is retired, and the matrix lists every scenario that remains
  - Scenario F revokes with npm trust and says what to do without an npm
    login; the Trusted Publisher section inspects with npm trust list, has
    a slot for the last check and says who approves a publish
  - No planning label outside quoted section titles of the launch audit,
    each of which is a real heading there; no reference outside the
    repository; nothing described as future work
  - The dist-tag policy, the registry's stale tags as a dated observation,
    its post-publish step, no verification comment expecting rc or alpha,
    and the install smoke dispatch with an exact version, the run found by
    its title, and its install-smoke.json record
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
RELEASING = REPO_ROOT / "docs" / "_internal" / "RELEASING.md"
RELEASE_YAML = REPO_ROOT / ".github" / "workflows" / "release.yaml"
INSTALL_SMOKE = REPO_ROOT / ".github" / "workflows" / "install-smoke.yaml"
LAUNCH_AUDIT = REPO_ROOT / "release-audits" / "v1.0.0-launch-audit.md"
BASELINES = REPO_ROOT / "release-audits" / "baselines"
RULESET_BASELINE = BASELINES / "baseline-ruleset-Default.json"
ENV_BASELINE = BASELINES / "baseline-env-release.json"
POLICIES_BASELINE = BASELINES / "baseline-env-release-branch-policies.json"
PUT_FILTER = BASELINES / "ruleset-put.jq"
PUT_FILTER_RUN = "jq -f release-audits/baselines/ruleset-put.jq"

# The guard release.yaml's Wait step uses: any answer but a list of
# rulesets, or a list without Default, gives nothing.
GUARD = """jq -r 'if type=="array" then (map(select(.name=="Default")) | .[0].id // empty) else empty end'"""
# Fields of a ruleset GET that a PUT does not take.
READ_ONLY = {"id", "source_type", "source", "node_id", "created_at", "updated_at", "current_user_can_bypass", "_links"}

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="runs the lookup's own jq filter")
needs_shell = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None or shutil.which("jq") is None,
    reason="runs the restore snippet under bash with jq and a stub gh",
)


def text() -> str:
    return RELEASING.read_text(encoding="utf-8")


def section(heading: str) -> str:
    """The body of the section whose heading starts with `heading`, up to the
    next heading of the same or a higher level. A `#` line inside a fenced
    block is a shell comment, not a heading."""
    lines = text().splitlines(keepends=True)
    fenced = False
    level = None
    body: list[str] = []
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        heading_match = None if fenced else re.match(r"^(#+) (.*)", line)
        if level is None:
            if heading_match and re.match(rf"{re.escape(heading)}\b", heading_match.group(2)):
                level = len(heading_match.group(1))
            continue
        if heading_match and len(heading_match.group(1)) <= level:
            break
        body.append(line)
    assert level is not None, heading
    return "".join(body)


def code_blocks(body: str) -> list[str]:
    return re.findall(r"^\s*```bash\n(.*?)^\s*```", body, re.MULTILINE | re.DOTALL)


# --------------------------------------------------------------------------
# #574: preconditions, ids, guarded lookups, baselines
# --------------------------------------------------------------------------


def test_preconditions_come_first_with_a_check_for_each_tool():
    body = text()
    assert body.index("## Preconditions\n") < body.index("## Branch Protection on `main`\n")
    checks = "\n".join(code_blocks(section("Preconditions")))
    for command in (
        "gh auth status",
        "gh api repos/armelhbobdad/bmad-module-skill-forge --jq .permissions.admin",
        "jq --version",
        "node --version",
        "npm whoami",
        "npm owner ls bmad-module-skill-forge",
        "npm --version",
        'npm profile get "two-factor auth"',
    ):
        assert command in checks, command
    prose = section("Preconditions")
    for need in ("admin rights", "`jq`", "publish rights", "11.15.0", "2FA"):
        assert need in prose, need


def test_no_command_names_a_ruleset_or_environment_id():
    for block in code_blocks(text()):
        assert not re.search(r"rulesets/\d", block), block
        assert not re.search(r"environments/\d", block), block
    for recorded in ("13855503", "14347249917"):
        lines = [line for line in text().splitlines() if recorded in line]
        assert lines, recorded
        assert all("at the time of writing" in line for line in lines), lines


def test_every_ruleset_lookup_is_guarded_before_the_id_is_used():
    blocks = [block for block in code_blocks(text()) if "RULESET_ID" in block]
    assert len(blocks) >= 3
    for block in blocks:
        assign = block.index("RULESET_ID=$(")
        lookup = block[assign : block.index("\n", block.index("\n", assign) + 1)]
        assert '2>/dev/null \\\n  | ' + GUARD + ")" in lookup, lookup
        guard = block.index('if [ -z "$RULESET_ID" ]; then', assign)
        # Nothing reads the id between the lookup and its empty-id check.
        assert "$RULESET_ID" not in block[assign + len("RULESET_ID=$(") : guard], block
        assert "--jq" not in lookup


def test_the_lookup_is_the_one_release_yaml_uses():
    assert GUARD.removeprefix("jq -r ") in RELEASE_YAML.read_text(encoding="utf-8")


@needs_jq
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param([{"id": 7, "name": "Other"}, {"id": 13, "name": "Default"}], "13", id="list with Default"),
        pytest.param([{"id": 7, "name": "Other"}], "", id="list without Default"),
        pytest.param({"message": "Not Found", "status": "404"}, "", id="error body"),
    ],
)
def test_the_lookup_gives_nothing_unless_a_ruleset_is_named_default(answer, expected):
    program = GUARD.removeprefix("jq -r ").strip("'")
    proc = subprocess.run(["jq", "-r", program], input=json.dumps(answer), capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected


def test_the_baselines_are_committed_where_the_capture_writes_and_the_restore_reads():
    ruleset = json.loads(RULESET_BASELINE.read_text(encoding="utf-8"))
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    policies = json.loads(POLICIES_BASELINE.read_text(encoding="utf-8"))
    assert (ruleset["name"], ruleset["target"]) == ("Default", "branch")
    assert environment["name"] == "release"
    assert [p["name"] for p in policies["branch_policies"]] == ["main"]
    body = text()
    capture = code_blocks(body[body.index("**Capture.**") :])[0]
    assert "DIR=release-audits/baselines" in capture
    for path in (RULESET_BASELINE, ENV_BASELINE, POLICIES_BASELINE):
        assert f" {path.name}\n" in capture, path.name
    restore = code_blocks(section("Restore from a saved baseline"))[0]
    assert "release-audits/baselines/baseline-ruleset-Default.json" in restore
    assert "_bmad-output" not in body
    assert "already git-tracked" not in body
    assert "ls -t" not in body


# --------------------------------------------------------------------------
# #575: the restore drill, Scenario C, Scenario F, the inspection note
# --------------------------------------------------------------------------


def test_every_restore_snippet_uses_the_one_filter():
    assert PUT_FILTER.is_file()
    restores = [
        block
        for block in code_blocks(text())
        if ("--method PUT" in block or "--method POST" in block) and "/rulesets" in block
    ]
    assert len(restores) >= 2
    for block in restores:
        assert PUT_FILTER_RUN in block, block
    # One copy of the filter: none written out in the runbook.
    assert "FILTER=" not in text()
    assert "jq '{name, target" not in text()


def test_the_restore_asks_before_its_put():
    restore = code_blocks(section("Restore from a saved baseline"))[0]
    diff = restore.index("| diff - /tmp/restore.json")
    ask = restore.index("read -r ok")
    put = restore.index('[ "$ok" = y ] && gh api --method PUT')
    assert diff < ask < put, restore
    assert restore.count("--method PUT") == 1


@needs_shell
@pytest.mark.parametrize(
    ("answer", "sends"),
    [
        pytest.param("y", True, id="yes"),
        pytest.param("n", False, id="no"),
        pytest.param("", False, id="enter"),
    ],
)
def test_the_restore_sends_the_put_only_on_yes(tmp_path, answer, sends):
    body = tmp_path / "restore.json"
    restore = code_blocks(section("Restore from a saved baseline"))[0].replace("/tmp/restore.json", body.as_posix())
    script = tmp_path / "restore.sh"
    script.write_text(restore, encoding="utf-8")
    log = tmp_path / "gh.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # The live ruleset is the baseline, so the diff prints nothing.
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{log.as_posix()}"\n'
        'case "$*" in\n'
        "  *'--method PUT'*) echo '{}' ;;\n"
        f"  */rulesets/*) cat '{RULESET_BASELINE.as_posix()}' ;;\n"
        """  */rulesets) echo '[{"id": 13, "name": "Default"}]' ;;\n"""
        "esac\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    proc = subprocess.run(
        ["bash", str(script)], input=answer + "\n", cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert "PUT " + body.as_posix() + " to ruleset 13? [y/N]" in proc.stdout, proc.stdout + proc.stderr
    assert not proc.stdout.startswith("<") and "---" not in proc.stdout, proc.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    puts = [call for call in calls if "--method PUT" in call]
    assert puts == ([f"api --method PUT repos/armelhbobdad/bmad-module-skill-forge/rulesets/13 --input {body.as_posix()}"] if sends else [])


@needs_jq
def test_the_filter_keeps_every_field_a_put_takes_minus_what_a_put_refused():
    proc = subprocess.run(
        ["jq", "-f", str(PUT_FILTER), str(RULESET_BASELINE)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    ruleset = json.loads(RULESET_BASELINE.read_text(encoding="utf-8"))
    assert set(body) == set(ruleset) - READ_ONLY
    assert [rule["type"] for rule in body["rules"]] == [rule["type"] for rule in ruleset["rules"]]
    for kept, saved in zip(body["rules"], ruleset["rules"]):
        if saved["type"] != "required_status_checks":
            assert kept == saved
            continue
        assert "do_not_enforce_on_create" not in kept["parameters"]
        checks = kept["parameters"]["required_status_checks"]
        assert [c["context"] for c in checks] == [c["context"] for c in saved["parameters"]["required_status_checks"]]
        assert all(value is not None for check in checks for value in check.values())
    assert body["bypass_actors"] == ruleset["bypass_actors"]


def test_the_restore_drill_has_a_record_that_names_its_filter():
    body = text()
    drill = body[body.index("**Restore drill.**") :]
    table = re.search(r"^\| Date \| Target \| Filter \| Result \|\n\| -.*\n((?:\|.*\n)+)", drill, re.MULTILINE)
    assert table, "no drill record table"
    rows = [row.strip("|").split("|") for row in table.group(1).splitlines()]
    assert rows
    for cells in rows:
        assert "`release-audits/baselines/ruleset-put.jq`" in cells[2], cells


def test_the_environment_restore_agrees_with_its_baseline():
    restore = code_blocks(section("Restore / re-apply"))[0]
    put = json.loads(re.search(r"<<'JSON'\n(.*?)\nJSON", restore, re.DOTALL).group(1))
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    reviewers = next(rule for rule in environment["protection_rules"] if rule["type"] == "required_reviewers")
    timers = [rule["wait_timer"] for rule in environment["protection_rules"] if rule["type"] == "wait_timer"]
    assert put["wait_timer"] == (timers[0] if timers else 0)
    assert put["prevent_self_review"] == reviewers["prevent_self_review"]
    assert put["reviewers"] == [{"type": r["type"], "id": r["reviewer"]["id"]} for r in reviewers["reviewers"]]
    assert put["deployment_branch_policy"] == environment["deployment_branch_policy"]
    policies = json.loads(POLICIES_BASELINE.read_text(encoding="utf-8"))
    posted = re.findall(r'\{ "name": "([^"]+)" \}', restore)
    assert posted == [p["name"] for p in policies["branch_policies"]]
    # The runbook leaves this comparison to this test, not to a check by hand.
    assert "`test/test-releasing-runbook.py` checks on every pull request" in section("Baseline snapshots")
    assert "check that their JSON still matches" not in text()


def test_scenario_c_is_retired_and_the_matrix_lists_every_scenario_left():
    body = text()
    scenarios = set(re.findall(r"^### Scenario ([A-Z])\b", body, re.MULTILINE))
    assert "C" not in scenarios
    assert "**Scenario C (unpublish) is retired.**" in body
    matrix = section("Cross-reference matrix")
    rows = set(re.findall(r"^\| ([A-Z])\s+\|", matrix, re.MULTILINE))
    assert rows == scenarios
    assert "time.modified" not in body
    assert "NFR" not in matrix


def test_scenario_f_revokes_with_npm_trust_and_says_what_to_do_without_a_login():
    scenario = section("Scenario F")
    assert "npm trust list bmad-module-skill-forge" in scenario
    assert "npm trust revoke bmad-module-skill-forge --id=<id>" in scenario
    assert "**No maintainer can sign in to npm**" in scenario
    assert "Contact npm support" in scenario
    assert "11.15.0" in scenario and "2FA" in scenario


def test_the_trusted_publisher_section_inspects_with_npm_trust_list():
    publisher = section("npm Trusted Publisher")
    assert "npm trust list bmad-module-skill-forge --json" in publisher
    assert "npm 11.15.0 or later" in publisher
    for field in ('"type": "github"', '"file": "release.yaml"', '"environment": "release"'):
        assert field in publisher, field
    assert "UI-only" not in publisher
    assert "No CLI" not in publisher
    assert "self-approval" in publisher
    assert "admin-bypass merge" in publisher
    assert "**Last checked with `npm trust list`:**" in publisher


# --------------------------------------------------------------------------
# #574 and #575: planning labels, outside references, future tense
# --------------------------------------------------------------------------

QUOTED_TITLE = re.compile(r"v1\.0\.0-launch-audit\.md((?: § [^§`]+)+)`")
LABEL = re.compile(r"\b(?:Story \d|NFR\d|FR\d|Epic \d|AC #?\d)")


def test_no_planning_label_outside_quoted_launch_audit_titles():
    body = text()
    headings = {h.strip() for h in re.findall(r"^#+ (.+)$", LAUNCH_AUDIT.read_text(encoding="utf-8"), re.MULTILINE)}
    titles = QUOTED_TITLE.findall(body)
    assert titles
    for quoted in titles:
        for title in quoted.split(" § ")[1:]:
            assert title.strip() in headings, title
    stripped = QUOTED_TITLE.sub("", body)
    assert not LABEL.findall(stripped), sorted(set(LABEL.findall(stripped)))
    assert "<!-- Rollback Playbook" not in body


def test_no_reference_outside_the_repository():
    body = text()
    assert "_bmad-output" not in body
    assert "research doc" not in body


def test_nothing_is_described_as_future_or_pending():
    body = text()
    for stale in (
        "The future `release.yaml`",
        "will use to push",
        "Pre-registration inversion",
        "Pre-Story",
        "Post-Story",
        "Pre-v1.0.0 context",
        "first live validator",
    ):
        assert stale not in body, stale


# --------------------------------------------------------------------------
# #568 and #569: dist-tag policy, install smoke dispatch and record
# --------------------------------------------------------------------------


def test_the_dist_tag_policy_and_its_post_publish_step():
    policy = section("Dist-tag policy")
    assert "`latest` is the only permanent dist-tag." in policy
    assert "`alpha`, `beta` and `rc` exist only while a prerelease line is open" in policy
    # The registry's stale tags are an observation with its date, not a fact.
    assert re.search(r"On \d{4}-\d{2}-\d{2} npm still carried `alpha`", policy), policy
    after = section("After the publish")
    assert "npm dist-tag rm bmad-module-skill-forge" in after
    assert '# expected: {"latest":"<version>"}' in after
    for block in code_blocks(text()):
        for line in block.splitlines():
            if "expected" in line:
                assert not re.search(r'"(alpha|rc)"\s*:', line), line
    assert 'Other dist-tags (e.g. "alpha")' not in text()


def load_run_name() -> str:
    return yaml.safe_load(INSTALL_SMOKE.read_text(encoding="utf-8"))["run-name"]


def test_the_install_smoke_test_is_dispatched_with_an_exact_version():
    after = section("After the publish")
    assert "gh workflow run install-smoke.yaml --ref main -f version=<version>" in after
    # The run is found by its title (the workflow's run-name), and the watch
    # waits for it to be listed: the newest run can still be the previous one.
    dispatch = next(block for block in code_blocks(after) if "install-smoke.yaml" in block)
    assert """select(.displayTitle=="Install smoke <version>")""" in dispatch
    assert 'if [ -z "$RUN_ID" ]; then' in dispatch
    assert "--limit 1" not in dispatch
    assert load_run_name() == "Install smoke ${{ inputs.version }}"
    assert "version=latest" not in text()
    assert "install-smoke.json" in after
    assert "gh release download v<version> --pattern install-smoke.json" in after
    workflow = yaml.safe_load(INSTALL_SMOKE.read_text(encoding="utf-8"))
    # PyYAML reads the bare `on` key as the boolean True.
    assert "version" in workflow[True]["workflow_dispatch"]["inputs"]
    assert "Post-publish verification (NFR9)" not in text()
