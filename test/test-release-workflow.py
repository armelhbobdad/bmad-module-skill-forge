#!/usr/bin/env python3
"""release.yaml: the retry-safe check wait, the cleanup after a failed run,
and the version, dist-tag and commit steps.

Issues #563 and #564. The main-dispatch path of .github/workflows/release.yaml
only runs for real on a `--ref main` dispatch, which is also a real npm
publish, so these tests run the steps' own `run:` scripts instead. Each
script is read from the workflow with PyYAML and run under `bash -e`, the
runner's default shell, with stub `gh`, `git`, `npm` and `sleep` commands
first on PATH. A stub answers from a list of rules the test gives (first
matching rule wins, each rule answers its calls in order and repeats its
last answer) and logs every call, so a test can assert what the step asked
GitHub or npm to do and how often it waited.

A failed `gh api --paginate --slurp` call exits 1 but still prints an array,
because gh closes it on the way out: `[]` when no page arrived, the pages
read so far when a later page failed, and the error body as the last page
on an HTTP error. The stubs print the same, so a step that takes that output
for data fails here.

Covers:
  - Push commit to temp branch: the branch name carries the run attempt
  - Wait for required status checks: check-runs read as one list over
    several pages (a context on two pages resolves to its newest run), a
    failed read of every shape retried as a pending tick until the timeout,
    in the registration poll too, a failed check and a timeout that no
    longer say the PR was left open
  - Cancel action_required pull_request runs: the run list read as one list,
    a failed list read again, then an error
  - Both steps: the head commit lookup retried, then an error
  - Close the bot PR and delete its branch after a failed run: its `if`, an
    open PR closed and then commented on once with a link to the run, a
    merged PR left alone, the leftover branch of a closed PR or of a run
    with no PR deleted, a close that failed because the PR merged meanwhile
    or after gh closed it, retried closes, a PR read that never succeeds, a
    comment or a branch lookup that fails, and a PR from a fork with the same
    branch name ignored
  - Every retry loop: the last try neither says it retries nor waits
  - No failure message in the workflow says the PR was left open, and no
    paginated read filters page by page or pipes gh straight into jq
  - Get new version and previous tag: new_version, dist_tag and
    previous_tag, written only for a valid version; latest for a stable
    version and alpha, beta or rc for those prerelease ids, each prerelease
    choice of version_bump included; any other id, an invalid or missing
    version and an unreadable package.json stop the step before anything
    is written, and it runs before every step that writes a file from it
  - The dry-run, the publish, the Release's prerelease flag, the docs deploy
    and the summary read dist_tag, no substring test on the version is left,
    and npm never runs without a dist_tag
  - Commit version bump: git commit --no-verify, with HUSKY "0" still at job
    level
  - setup-uv, in every workflow: its cache-dependency-glob matches a file

The behaviour tests need bash and jq (both on the GitHub-hosted Ubuntu
runner) and are skipped on Windows. The version step's tests also need node
and the semver devDependency (npm ci), found through NODE_PATH.
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
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yaml"

REPOSITORY = "owner/repo"
RUN_ID = "42"
RUN_ATTEMPT = "2"
HEAD_SHA = "a" * 40
TEMP_BRANCH = f"release/bot/v3.0.0-{RUN_ID}-{RUN_ATTEMPT}"
REQUIRED = ["lint", "validate (ubuntu-latest)"]

TEMP_PUSH = "Push commit to temp branch"
CANCEL = "Cancel action_required pull_request runs on bot PR head"
WAIT = "Wait for required status checks"
CLEANUP = "Close the bot PR and delete its branch after a failed run"
VERSION = "Get new version and previous tag"
DRY_RUN = "Pre-publish dry-run (catch package validation failures before tag push)"
COMMIT = "Commit version bump"
PUBLISH = "Publish to npm via OIDC trusted publishing"
GH_RELEASE = "Create GitHub Release"
DOCS = "Deploy the docs site at the new tag"
SUMMARY = "Summary"

needs_shell = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the step scripts run under bash and jq, as on the Ubuntu runner",
)

# The version step runs node with the semver devDependency, which npm ci
# installs on the runner; its tests find it through NODE_PATH.
NODE_MODULES = REPO_ROOT / "node_modules"
needs_node = pytest.mark.skipif(
    shutil.which("node") is None or not (NODE_MODULES / "semver").is_dir(),
    reason="the version step runs node with the semver devDependency (npm ci)",
)

# One stub for gh, git and npm, called with the tool's name first: its rules
# are in <STUB_DIR>/<name>.json. A rule matches when its `match` is a
# substring of the joined arguments. An answer may remove files in STUB_DIR
# (the tests use a file named `branch` for "the temp branch is on origin"),
# and an answer with `stdout_if` prints its stdout only while that file
# exists.
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
for i, rule in enumerate(rules):
    if rule["match"] not in line:
        continue
    count_file = os.path.join(d, "%s.%d.count" % (name, i))
    n = int(open(count_file).read()) if os.path.exists(count_file) else 0
    with open(count_file, "w") as f:
        f.write(str(n + 1))
    answer = rule["answers"][min(n, len(rule["answers"]) - 1)]
    out = answer.get("stdout", "")
    if "stdout_if" in answer and not os.path.exists(os.path.join(d, answer["stdout_if"])):
        out = ""
    for path in answer.get("remove", []):
        if os.path.exists(os.path.join(d, path)):
            os.remove(os.path.join(d, path))
    sys.stdout.write(out)
    sys.stderr.write(answer.get("stderr", ""))
    sys.exit(answer.get("exit", 0))
sys.stderr.write("stub %s: no rule for: %s\\n" % (name, line))
sys.exit(97)
"""


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps() -> list[dict]:
    return load_workflow()["jobs"]["release"]["steps"]


def step(name: str) -> dict:
    matches = [s for s in steps() if s.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


class Result:
    def __init__(self, proc: subprocess.CompletedProcess, stub_dir: Path):
        self.code = proc.returncode
        self.out = proc.stdout + proc.stderr
        log = stub_dir / "calls.jsonl"
        self.calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        summary = stub_dir / "summary.md"
        self.summary = summary.read_text() if summary.exists() else ""
        output = stub_dir / "output.txt"
        self.output = output.read_text() if output.exists() else ""
        self.branch_on_origin = (stub_dir / "branch").exists()

    def called(self, name: str, *parts: str) -> list[list[str]]:
        """Calls of `name` whose joined arguments contain every part."""
        return [c for c in self.calls if c[0] == name and all(p in " ".join(c[1:]) for p in parts)]

    def slept(self, seconds: int) -> int:
        """How many times the step ran `sleep <seconds>`."""
        return self.calls.count(["sleep", str(seconds)])


def run_step(
    tmp_path: Path,
    name: str,
    env: dict[str, str],
    gh: list[dict] | None = None,
    git: list[dict] | None = None,
    branch_on_origin: bool = False,
    npm: list[dict] | None = None,
) -> Result:
    stub_dir = tmp_path / "stub"
    bin_dir = tmp_path / "bin"
    stub_dir.mkdir()
    bin_dir.mkdir()
    stub_py = stub_dir / "stub.py"
    stub_py.write_text(STUB, encoding="utf-8")
    for tool, rules in (("gh", gh), ("git", git), ("npm", npm)):
        exe = bin_dir / tool
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub_py}" {tool} "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
        (stub_dir / f"{tool}.json").write_text(json.dumps(rules or []), encoding="utf-8")
    # sleep returns at once and logs its call, so a test can count the waits.
    sleep = bin_dir / "sleep"
    sleep.write_text('#!/bin/sh\necho "[\\"sleep\\", \\"$1\\"]" >> "$STUB_DIR/calls.jsonl"\n', encoding="utf-8")
    sleep.chmod(0o755)
    if branch_on_origin:
        (stub_dir / "branch").touch()

    script = tmp_path / "step.sh"
    script.write_text(step(name)["run"], encoding="utf-8")
    full_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(tmp_path),
        "STUB_DIR": str(stub_dir),
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_RUN_ID": RUN_ID,
        "GITHUB_RUN_ATTEMPT": RUN_ATTEMPT,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_OUTPUT": str(stub_dir / "output.txt"),
        "GITHUB_STEP_SUMMARY": str(stub_dir / "summary.md"),
        **env,
    }
    proc = subprocess.run(
        ["bash", "-e", str(script)],
        cwd=tmp_path,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return Result(proc, stub_dir)


def ok(stdout: str) -> dict:
    return {"stdout": stdout}


def fail(stderr: str = "HTTP 502\n", stdout: str = "") -> dict:
    return {"exit": 1, "stderr": stderr, "stdout": stdout}


def slurp_failures(full: str) -> list:
    """A failed `gh api --paginate --slurp` call for each shape of its output,
    given the output of the call that succeeds (at least one page)."""
    first = json.loads(full)[:1]
    error = {"message": "Server Error", "status": "502"}
    return [
        pytest.param(fail("gh: stopped before the first request\n"), id="no output"),
        pytest.param(fail("connect: connection refused\n", "[]"), id="no page"),
        pytest.param(fail("read: connection reset by peer\n", json.dumps(first)), id="first page only"),
        pytest.param(fail("gh: Server Error (HTTP 502)\n", json.dumps([error])), id="error body"),
        pytest.param(fail("gh: Server Error (HTTP 502)\n", json.dumps(first + [error])), id="error body after a page"),
    ]


# --------------------------------------------------------------------------
# Wait for required status checks
# --------------------------------------------------------------------------


def check_run(name: str, conclusion: str | None, started_at: str, status: str = "completed") -> dict:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
        "html_url": f"https://github.com/{REPOSITORY}/actions/runs/1?check={name}@{started_at}",
        "app": {"slug": "github-actions"},
    }


def pages(*page_runs: list[dict]) -> str:
    """What `gh api --paginate --slurp` prints: one array of the page objects."""
    return json.dumps([{"total_count": sum(len(p) for p in page_runs), "check_runs": p} for p in page_runs])


# `lint` ran twice: its first run failed and sits on the first page, its
# re-run passed and sits on the last page. Read page by page, the lookup of
# `lint` found one line per page; read as one list, it finds the re-run.
THREE_PAGES = pages(
    [check_run("lint", "failure", "2026-09-22T19:40:00Z"), check_run("prettier", "success", "2026-09-22T19:40:01Z")],
    [check_run("validate (ubuntu-latest)", "success", "2026-09-22T19:41:00Z")],
    [check_run("lint", "success", "2026-09-22T19:45:00Z")],
)


def wait_rules(check_runs: list[dict], pr_view: list[dict] | None = None) -> list[dict]:
    return [
        {"match": "pr view 7 --json headRefOid", "answers": pr_view or [ok(HEAD_SHA + "\n")]},
        {
            "match": f"/repos/{REPOSITORY}/rulesets/5",
            "answers": [
                ok(
                    json.dumps(
                        {
                            "rules": [
                                {
                                    "type": "required_status_checks",
                                    "parameters": {"required_status_checks": [{"context": c} for c in REQUIRED]},
                                }
                            ]
                        }
                    )
                )
            ],
        },
        {"match": f"/repos/{REPOSITORY}/rulesets", "answers": [ok(json.dumps([{"name": "Default", "id": 5}]))]},
        {
            "match": f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs?per_page=100 --paginate --slurp",
            "answers": check_runs,
        },
    ]


@needs_shell
def test_wait_reads_every_page_as_one_list(tmp_path):
    result = run_step(tmp_path, WAIT, {"PR_NUMBER": "7"}, gh=wait_rules([ok(THREE_PAGES)]))
    assert result.code == 0, result.out
    assert "All 2 required contexts green" in result.out


@needs_shell
def test_wait_newest_run_of_a_context_wins_across_pages(tmp_path):
    # The same two runs of `lint`, the other way round: the re-run failed.
    failed_rerun = pages(
        [check_run("lint", "success", "2026-09-22T19:40:00Z")],
        [check_run("validate (ubuntu-latest)", "success", "2026-09-22T19:41:00Z")],
        [check_run("lint", "failure", "2026-09-22T19:45:00Z")],
    )
    result = run_step(tmp_path, WAIT, {"PR_NUMBER": "7"}, gh=wait_rules([ok(failed_rerun)]))
    assert result.code == 1, result.out
    assert "Required context(s) failed: lint(conclusion=failure" in result.out
    assert "left open" not in result.out
    assert "closes the bot PR, unless it has merged, and deletes its branch" in result.out
    assert "Re-run failed jobs" in result.out


@needs_shell
@pytest.mark.parametrize("failed", slurp_failures(THREE_PAGES))
def test_wait_counts_a_failed_read_as_a_pending_tick(tmp_path, failed):
    # Registration reads fine, one read fails, then the checks are green.
    # Taken for data, `[]` would leave every context unregistered, and the
    # first page alone holds only the failed run of `lint`, so the wait
    # would stop on it.
    answers = [ok(THREE_PAGES), failed, ok(THREE_PAGES)]
    result = run_step(tmp_path, WAIT, {"PR_NUMBER": "7"}, gh=wait_rules(answers))
    assert result.code == 0, result.out
    assert result.out.count(f"Reading the check-runs on {HEAD_SHA} failed") == 1
    assert "unregistered" not in result.out
    assert "Required context(s) failed" not in result.out
    assert "All 2 required contexts green" in result.out


@needs_shell
def test_wait_retries_a_failed_read_until_the_timeout(tmp_path):
    answers = [ok(THREE_PAGES), fail("connect: connection refused\n", "[]")]
    result = run_step(tmp_path, WAIT, {"PR_NUMBER": "7"}, gh=wait_rules(answers))
    assert result.code == 1, result.out
    assert result.out.count(f"Reading the check-runs on {HEAD_SHA} failed") == 60
    assert "did not all succeed within 1200s" in result.out
    assert "Pending: unknown, the check-runs could not be read." in result.out


@needs_shell
@pytest.mark.parametrize("failed", slurp_failures(THREE_PAGES))
def test_wait_registration_poll_survives_a_failed_read(tmp_path, failed):
    result = run_step(tmp_path, WAIT, {"PR_NUMBER": "7"}, gh=wait_rules([failed, ok(THREE_PAGES)]))
    assert result.code == 0, result.out
    assert "4 check-run(s) registered" in result.out
    assert result.slept(5) == 1


@needs_shell
def test_wait_timeout_names_the_cleanup_not_an_open_pr(tmp_path):
    pending = pages(
        [
            check_run("lint", None, "2026-09-22T19:40:00Z", status="in_progress"),
            check_run("validate (ubuntu-latest)", "success", "2026-09-22T19:41:00Z"),
        ]
    )
    result = run_step(tmp_path, WAIT, {"PR_NUMBER": "7"}, gh=wait_rules([ok(pending)]))
    assert result.code == 1, result.out
    assert "did not all succeed within 1200s" in result.out
    assert "Pending: lint(in_progress)" in result.out
    assert "left open" not in result.out
    assert "closes the bot PR, unless it has merged, and deletes its branch" in result.out


# --------------------------------------------------------------------------
# Cancel action_required pull_request runs on bot PR head
# --------------------------------------------------------------------------


def run_pages(*page_ids: list[tuple[int, str]]) -> str:
    return json.dumps(
        [
            {"total_count": 0, "workflow_runs": [{"id": i, "conclusion": c} for i, c in page]}
            for page in page_ids
        ]
    )


# Runs 11 and 13 are stuck in action_required, one on each page.
TWO_RUN_PAGES = run_pages([(11, "action_required"), (12, "success")], [(13, "action_required")])
CANCELLED_11_13 = [f"/repos/{REPOSITORY}/actions/runs/11/cancel", f"/repos/{REPOSITORY}/actions/runs/13/cancel"]


def cancel_rules(runs: list[dict], pr_view: list[dict] | None = None) -> list[dict]:
    return [
        {"match": "pr view 7 --json headRefOid", "answers": pr_view or [ok(HEAD_SHA + "\n")]},
        {"match": "--method POST", "answers": [ok("")]},
        {
            "match": f"/repos/{REPOSITORY}/actions/runs?head_sha={HEAD_SHA}&per_page=100 --paginate --slurp",
            "answers": runs,
        },
    ]


def cancelled(result: Result) -> list[str]:
    return [c[-1] for c in result.called("gh", "--method POST")]


@needs_shell
def test_cancel_counts_and_cancels_across_pages(tmp_path):
    result = run_step(tmp_path, CANCEL, {"PR_NUMBER": "7"}, gh=cancel_rules([ok(TWO_RUN_PAGES)]))
    assert result.code == 0, result.out
    assert f"Cancelling 2 action_required run(s) on {HEAD_SHA}" in result.out
    assert cancelled(result) == CANCELLED_11_13


@needs_shell
def test_cancel_with_nothing_stuck(tmp_path):
    runs = run_pages([(11, "success")], [])
    result = run_step(tmp_path, CANCEL, {"PR_NUMBER": "7"}, gh=cancel_rules([ok(runs)]))
    assert result.code == 0, result.out
    assert "nothing to cancel" in result.out
    assert not result.called("gh", "--method POST")


@needs_shell
@pytest.mark.parametrize("failed", slurp_failures(TWO_RUN_PAGES))
def test_cancel_reads_a_failed_list_again(tmp_path, failed):
    # Taken for data, `[]` would cancel nothing and the first page alone
    # would miss run 13, whose action_required run blocks the merge.
    result = run_step(tmp_path, CANCEL, {"PR_NUMBER": "7"}, gh=cancel_rules([failed, ok(TWO_RUN_PAGES)]))
    assert result.code == 0, result.out
    assert f"Listing the workflow runs on {HEAD_SHA} failed (try 1 of 6); retrying" in result.out
    assert cancelled(result) == CANCELLED_11_13


@needs_shell
@pytest.mark.parametrize("failed", slurp_failures(TWO_RUN_PAGES))
def test_cancel_a_list_that_keeps_failing_fails_with_a_message(tmp_path, failed):
    result = run_step(tmp_path, CANCEL, {"PR_NUMBER": "7"}, gh=cancel_rules([failed]))
    assert result.code == 1, result.out
    assert f"Could not list the workflow runs on {HEAD_SHA} in 6 tries" in result.out
    assert len(result.called("gh", "actions/runs?head_sha=")) == 6
    assert not result.called("gh", "--method POST")
    # One wait before the first read, then one per retry: none after the last.
    assert result.out.count("retrying") == 5
    assert result.slept(10) == 6


# --------------------------------------------------------------------------
# Head commit lookup (Wait for required status checks and Cancel)
# --------------------------------------------------------------------------


def lookup_rules(name: str, pr_view: list[dict]) -> list[dict]:
    if name == WAIT:
        return wait_rules([ok(THREE_PAGES)], pr_view=pr_view)
    return cancel_rules([ok(run_pages([(11, "success")]))], pr_view=pr_view)


@needs_shell
@pytest.mark.parametrize("name", [WAIT, CANCEL])
def test_head_commit_lookup_is_retried(tmp_path, name):
    lookups = [fail(), ok("\n"), ok(HEAD_SHA + "\n")]
    result = run_step(tmp_path, name, {"PR_NUMBER": "7"}, gh=lookup_rules(name, lookups))
    assert result.code == 0, result.out
    assert result.out.count("Reading the head commit of PR #7 failed") == 2
    assert len(result.called("gh", "pr view 7")) == 3


@needs_shell
@pytest.mark.parametrize("name", [WAIT, CANCEL])
def test_head_commit_lookup_gives_up_after_six_tries(tmp_path, name):
    result = run_step(tmp_path, name, {"PR_NUMBER": "7"}, gh=lookup_rules(name, [fail()]))
    assert result.code == 1, result.out
    assert "Could not read the head commit of PR #7 in 6 tries" in result.out
    assert len(result.called("gh", "pr view 7")) == 6
    assert not result.called("gh", "api")
    # The sixth failed try neither says it retries nor waits.
    assert result.out.count("retrying") == 5
    assert "try 6 of 6" not in result.out
    assert result.slept(10) == 5


# --------------------------------------------------------------------------
# Close the bot PR and delete its branch after a failed run
# --------------------------------------------------------------------------

CLEANUP_ENV = {"TEMP_BRANCH": TEMP_BRANCH, "JOB_STATUS": "failure"}


def pr_list(*prs: tuple[int, str, bool]) -> dict:
    return ok(json.dumps([{"number": n, "state": s, "isCrossRepository": cross} for n, s, cross in prs]))


def cleanup_rules(lists: list[dict], close: list[dict] | None = None, comment: list[dict] | None = None) -> list[dict]:
    return [
        {"match": f"pr list --head {TEMP_BRANCH} --state all", "answers": lists},
        {"match": "pr close 7 --delete-branch", "answers": close or [{"remove": ["branch"]}]},
        {"match": "pr comment 7 --body", "answers": comment or [ok("")]},
    ]


GIT_RULES = [
    {
        "match": f"ls-remote --heads origin refs/heads/{TEMP_BRANCH}",
        "answers": [{"stdout": f"{HEAD_SHA}\trefs/heads/{TEMP_BRANCH}\n", "stdout_if": "branch"}],
    },
    {"match": f"push origin --delete {TEMP_BRANCH}", "answers": [{"remove": ["branch"]}]},
]


def test_cleanup_runs_last_on_failure_or_cancel_once_the_branch_exists():
    last = steps()[-1]
    assert last["name"] == CLEANUP
    condition = last["if"]
    assert "failure() || cancelled()" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "steps.temp_push.outputs.temp_branch != ''" in condition
    assert last["env"]["TEMP_BRANCH"] == "${{ steps.temp_push.outputs.temp_branch }}"
    assert "uses" not in last


@needs_shell
def test_cleanup_closes_an_open_pr_then_comments_with_a_link_to_the_run(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "OPEN", False))]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    closes = result.called("gh", "pr close 7")
    assert closes == [["gh", "pr", "close", "7", "--delete-branch"]]
    comments = result.called("gh", "pr comment 7 --body")
    assert len(comments) == 1
    # gh pr close --comment posts before it closes; the step comments after.
    assert result.calls.index(comments[0]) > result.calls.index(closes[0])
    comment = comments[0][-1]
    assert f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}" in comment
    assert f"attempt {RUN_ATTEMPT}" in comment
    assert "job status: failure" in comment
    assert TEMP_BRANCH in comment
    assert "Re-run failed jobs" in comment
    assert not result.branch_on_origin
    assert not result.called("git", "push")
    assert f"Closed bot PR #7 with a comment linking this run and deleted {TEMP_BRANCH}." in result.out
    assert "Release stopped before the bot PR merged" in result.summary


@needs_shell
def test_cleanup_comments_once_when_the_close_is_retried(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "OPEN", False))], close=[fail(), fail(), {"remove": ["branch"]}]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert result.out.count("Closing bot PR #7 failed") == 2
    assert len(result.called("gh", "pr close 7")) == 3
    assert not result.called("gh", "pr close", "--comment")
    assert len(result.called("gh", "pr comment 7")) == 1
    assert not result.branch_on_origin


@needs_shell
def test_cleanup_leaves_a_merged_pr_and_its_branch_alone(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "MERGED", False))]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert not result.called("gh", "pr close")
    assert not result.called("gh", "pr comment")
    assert not result.called("git")
    assert result.branch_on_origin
    assert "Bot PR #7 merged before this run stopped" in result.out


@needs_shell
def test_cleanup_deletes_the_leftover_branch_of_a_closed_pr(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "CLOSED", False))]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert not result.called("gh", "pr close")
    assert not result.called("gh", "pr comment")
    assert len(result.called("git", "push origin --delete", TEMP_BRANCH)) == 1
    assert not result.branch_on_origin
    assert f"Bot PR #7 is closed and {TEMP_BRANCH} is deleted." in result.out


@needs_shell
def test_cleanup_closed_pr_whose_branch_is_gone(tmp_path):
    result = run_step(
        tmp_path, CLEANUP, CLEANUP_ENV, gh=cleanup_rules([pr_list((7, "CLOSED", False))]), git=GIT_RULES
    )
    assert result.code == 0, result.out
    assert result.called("git", "ls-remote")
    assert not result.called("git", "push")


@needs_shell
def test_cleanup_deletes_the_branch_of_a_run_that_opened_no_pr(tmp_path):
    result = run_step(
        tmp_path, CLEANUP, CLEANUP_ENV, gh=cleanup_rules([pr_list()]), git=GIT_RULES, branch_on_origin=True
    )
    assert result.code == 0, result.out
    assert not result.called("gh", "pr close")
    assert not result.called("gh", "pr comment")
    assert len(result.called("git", "push origin --delete", TEMP_BRANCH)) == 1
    assert "No bot PR was open" in result.out


@needs_shell
def test_cleanup_ignores_a_fork_pr_with_the_same_branch_name(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((9, "OPEN", True), (7, "OPEN", False))]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert not result.called("gh", "pr close 9")
    assert len(result.called("gh", "pr close 7")) == 1


@needs_shell
def test_cleanup_retries_a_failed_pr_read(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([fail(), ok("not json"), pr_list((7, "OPEN", False))]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert result.out.count(f"Reading the bot PR of {TEMP_BRANCH} failed") == 2
    assert len(result.called("gh", "pr close 7")) == 1


@needs_shell
def test_cleanup_reads_the_state_again_after_a_failed_close(tmp_path):
    # The maintainer merged the PR between the read and the close.
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules(
            [pr_list((7, "OPEN", False)), pr_list((7, "MERGED", False))],
            close=[fail("Pull request #7 can't be closed because it was already merged\n")],
        ),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert len(result.called("gh", "pr close 7")) == 1
    assert not result.called("gh", "pr comment")
    assert not result.called("git")
    assert result.branch_on_origin


@needs_shell
def test_cleanup_deletes_the_branch_when_close_left_it(tmp_path):
    # gh closed the PR but failed to delete the branch, and says so: the PR
    # this run tried to close now reads as closed, so the run closed it.
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules(
            [pr_list((7, "OPEN", False)), pr_list((7, "CLOSED", False))],
            close=[fail("failed to delete remote branch\n")],
        ),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert len(result.called("gh", "pr close 7")) == 1
    assert len(result.called("gh", "pr comment 7")) == 1
    assert len(result.called("git", "push origin --delete", TEMP_BRANCH)) == 1
    assert not result.branch_on_origin
    assert f"Closed bot PR #7 with a comment linking this run and deleted {TEMP_BRANCH}." in result.out


@needs_shell
def test_cleanup_warns_when_the_comment_fails(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "OPEN", False))], comment=[fail()]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 0, result.out
    assert len(result.called("gh", "pr comment 7")) == 1
    assert "::warning::Bot PR #7 is closed, but the comment linking this run could not be posted." in result.out
    assert f"Closed bot PR #7 and deleted {TEMP_BRANCH}." in result.out
    assert not result.branch_on_origin


@needs_shell
def test_cleanup_reports_a_branch_it_could_not_look_up(tmp_path):
    git = [{"match": "ls-remote", "answers": [fail("fatal: unable to access origin\n")]}]
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "OPEN", False))]),
        git=git,
        branch_on_origin=True,
    )
    assert result.code == 1, result.out
    # The PR is closed and commented on before the branch is looked up.
    assert len(result.called("gh", "pr comment 7")) == 1
    assert not result.called("git", "push")
    assert f"Could not look up {TEMP_BRANCH} on origin" in result.out


@needs_shell
def test_cleanup_touches_nothing_when_the_pr_cannot_be_read(tmp_path):
    result = run_step(
        tmp_path, CLEANUP, CLEANUP_ENV, gh=cleanup_rules([fail()]), git=GIT_RULES, branch_on_origin=True
    )
    assert result.code == 1, result.out
    assert len(result.called("gh", "pr list")) == 6
    assert not result.called("gh", "pr close")
    assert not result.called("gh", "pr comment")
    assert not result.called("git")
    assert f"Could not read the bot PR of {TEMP_BRANCH} in 6 tries" in result.out
    assert result.out.count("retrying") == 5
    assert result.slept(10) == 5


@needs_shell
def test_cleanup_reports_a_pr_it_could_not_close(tmp_path):
    result = run_step(
        tmp_path,
        CLEANUP,
        CLEANUP_ENV,
        gh=cleanup_rules([pr_list((7, "OPEN", False))], close=[fail()]),
        git=GIT_RULES,
        branch_on_origin=True,
    )
    assert result.code == 1, result.out
    assert len(result.called("gh", "pr close 7")) == 6
    assert not result.called("gh", "pr comment")
    assert not result.called("git")
    assert "Could not close bot PR #7 in 6 tries. Close it by hand" in result.out
    assert "try 6 of 6" not in result.out
    assert result.slept(10) == 5


# --------------------------------------------------------------------------
# Temp branch name, failure messages and paginated reads
# --------------------------------------------------------------------------


@needs_shell
def test_temp_branch_name_carries_the_run_attempt(tmp_path):
    git = [{"match": f"push origin HEAD:refs/heads/{TEMP_BRANCH}", "answers": [ok("")]}]
    result = run_step(tmp_path, TEMP_PUSH, {"NEW_VERSION": "3.0.0"}, git=git)
    assert result.code == 0, result.out
    assert f"temp_branch={TEMP_BRANCH}" in result.output


def test_no_failure_message_says_the_pr_was_left_open():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"left (open|in closed state)", text, re.IGNORECASE)


def test_paginated_reads_are_slurped_not_filtered_per_page():
    # `gh api --paginate --jq` filters each page on its own; every paginated
    # read in the workflow gathers the pages with --slurp and filters in jq.
    # A failed slurped call still prints an array, so gh's output never goes
    # straight into jq: the step checks gh's exit status first.
    for s in steps():
        script = (s.get("run") or "").replace("\\\n", " ")
        for line in script.splitlines():
            if "--paginate" in line and not line.strip().startswith("#"):
                assert "--slurp" in line and "--jq" not in line, f"{s['name']}: {line.strip()}"
                assert not re.search(r"--slurp.*\|\s*jq", line), f"{s['name']}: {line.strip()}"


# --------------------------------------------------------------------------
# Get new version and previous tag, and the steps that read its dist_tag
# --------------------------------------------------------------------------


def run_version_step(tmp_path: Path, version: str | None) -> Result:
    """Run the version step on a package.json holding `version` (None: no version key)."""
    package = {"name": "bmad-module-skill-forge"}
    if version is not None:
        package["version"] = version
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")
    git = [{"match": "describe --tags --abbrev=0 --match v[0-9]* --exclude *-*", "answers": [ok("v2.2.0\n")]}]
    return run_step(tmp_path, VERSION, {"NODE_PATH": str(NODE_MODULES)}, git=git)


def version_bump_choices() -> list[str]:
    workflow = load_workflow()
    # PyYAML reads the bare `on:` key as the boolean true.
    trigger = workflow.get("on", workflow.get(True))
    return trigger["workflow_dispatch"]["inputs"]["version_bump"]["options"]


@needs_shell
@needs_node
@pytest.mark.parametrize(
    ("version", "dist_tag"),
    [
        pytest.param("3.0.0", "latest", id="stable"),
        pytest.param("3.0.0-alpha.0", "alpha", id="alpha"),
        pytest.param("3.0.0-beta.2", "beta", id="beta"),
        pytest.param("3.0.0-rc.1", "rc", id="rc"),
        pytest.param("3.0.0-rc", "rc", id="rc without a number"),
    ],
)
def test_version_step_outputs_the_version_and_its_dist_tag(tmp_path, version, dist_tag):
    result = run_version_step(tmp_path, version)
    assert result.code == 0, result.out
    assert result.output == f"new_version={version}\ndist_tag={dist_tag}\nprevious_tag=v2.2.0\n"


@needs_shell
@needs_node
def test_every_prerelease_choice_of_version_bump_has_its_dist_tag(tmp_path):
    # A prerelease choice the rule does not list would stop every cut of
    # that channel, so the choices and the rule move together.
    prereleases = [choice for choice in version_bump_choices() if choice not in ("patch", "minor", "major")]
    assert prereleases
    for choice in prereleases:
        run_dir = tmp_path / choice
        run_dir.mkdir()
        result = run_version_step(run_dir, f"3.0.0-{choice}.0")
        assert result.code == 0, result.out
        assert f"\ndist_tag={choice}\n" in result.output


@needs_shell
@needs_node
@pytest.mark.parametrize(
    ("version", "preid"),
    [
        pytest.param("3.0.0-next.0", "next", id="unknown id"),
        pytest.param("3.0.0-0", "0", id="numeric id"),
        pytest.param("3.0.0-latest.0", "latest", id="id named latest"),
        pytest.param("3.0.0-RC.1", "RC", id="uppercase id"),
        # A substring test sent these two to alpha and rc.
        pytest.param("3.0.0-alphabet.0", "alphabet", id="id holding alpha"),
        pytest.param("3.0.0-source.1", "source", id="id holding rc"),
    ],
)
def test_version_step_fails_on_any_other_prerelease_id(tmp_path, version, preid):
    result = run_version_step(tmp_path, version)
    assert result.code == 1, result.out
    message = (
        f"::error::{version} is a prerelease with the id {preid}, "
        "and only alpha, beta and rc have an npm dist-tag, so the run stops instead of publishing it to latest."
    )
    assert message in result.out
    assert result.output == ""
    assert not result.called("git")


@needs_shell
@needs_node
@pytest.mark.parametrize(
    ("version", "shown"),
    [
        pytest.param("", "", id="empty"),
        pytest.param(None, "undefined", id="no version key"),
        pytest.param("v3.0.0", "v3.0.0", id="leading v"),
        pytest.param(" 3.0.0", " 3.0.0", id="leading space"),
        pytest.param("3.0", "3.0", id="two parts"),
        pytest.param("3.0.0.0", "3.0.0.0", id="four parts"),
        pytest.param("03.0.0", "03.0.0", id="leading zero"),
        pytest.param("3.0.0-rc.01", "3.0.0-rc.01", id="leading zero in the prerelease"),
        pytest.param("3.0.0+build.1", "3.0.0+build.1", id="build metadata"),
    ],
)
def test_version_step_fails_on_an_invalid_version(tmp_path, version, shown):
    result = run_version_step(tmp_path, version)
    assert result.code == 1, result.out
    assert f'::error::package.json holds the version "{shown}", which is not a valid semantic version' in result.out
    assert result.output == ""
    assert not result.called("git")


@needs_shell
@needs_node
def test_version_step_stops_when_package_json_cannot_be_read(tmp_path):
    # Inside echo's argument, the failed read wrote new_version= and the
    # step went on; the plain assignment stops it.
    git = [{"match": "describe --tags", "answers": [ok("v2.2.0\n")]}]
    result = run_step(tmp_path, VERSION, {"NODE_PATH": str(NODE_MODULES)}, git=git)
    assert result.code != 0, result.out
    assert result.output == ""
    assert not result.called("git")


def test_version_step_runs_before_every_file_it_feeds_is_written():
    names = [s.get("name") for s in steps()]
    at = names.index(VERSION)
    assert names.index("Bump version") < at
    writers = [
        "Update marketplace.json version",
        "Update docs/_data/pinned.yaml skf_version",
        "Write release notes and CHANGELOG.md",
    ]
    for writer in writers:
        assert at < names.index(writer), writer


def test_one_dist_tag_drives_the_publish_the_release_and_the_docs():
    dist_tag = "${{ steps.version.outputs.dist_tag }}"
    for name in (DRY_RUN, PUBLISH, SUMMARY):
        assert step(name)["env"]["DIST_TAG"] == dist_tag, name
    for name in (DRY_RUN, PUBLISH):
        assert step(name)["env"]["NPM_TOKEN"] == "", name
    assert step(GH_RELEASE)["with"]["prerelease"] == "${{ steps.version.outputs.dist_tag != 'latest' }}"
    assert step(DOCS)["if"] == "github.ref == 'refs/heads/main' && steps.version.outputs.dist_tag == 'latest'"


def test_no_substring_test_on_the_version_is_left():
    # A substring match on the version sent an id it did not list, or an
    # empty version, to latest.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"contains\(\s*steps\.version\.outputs\.new_version", text)
    assert not re.search(r"\*\"?(alpha|beta|rc)\"?\*", text)


NPM_RULES = [{"match": "publish", "answers": [ok("")]}]


@needs_shell
@pytest.mark.parametrize(
    ("name", "args"),
    [
        pytest.param(DRY_RUN, ["publish", "--dry-run", "--tag"], id="dry-run"),
        pytest.param(PUBLISH, ["publish", "--tag"], id="publish"),
    ],
)
@pytest.mark.parametrize("dist_tag", ["latest", "alpha", "beta", "rc"])
def test_npm_publishes_under_the_dist_tag(tmp_path, name, args, dist_tag):
    result = run_step(tmp_path, name, {"DIST_TAG": dist_tag, "NPM_TOKEN": ""}, npm=NPM_RULES)
    assert result.code == 0, result.out
    assert result.called("npm") == [["npm", *args, dist_tag]]


@needs_shell
@pytest.mark.parametrize("name", [pytest.param(DRY_RUN, id="dry-run"), pytest.param(PUBLISH, id="publish")])
def test_npm_does_not_run_without_a_dist_tag(tmp_path, name):
    result = run_step(tmp_path, name, {"DIST_TAG": "", "NPM_TOKEN": ""}, npm=NPM_RULES)
    assert result.code == 1, result.out
    assert "::error::The version step set no dist_tag" in result.out
    assert not result.called("npm")


@needs_shell
@pytest.mark.parametrize(
    ("version", "dist_tag", "docs", "line"),
    [
        pytest.param(
            "3.0.0",
            "latest",
            "dispatched",
            "**Docs site**: deploy at v3.0.0 dispatched (docs.yaml)",
            id="stable, deployed",
        ),
        pytest.param(
            "3.0.0", "latest", "failed", "**Docs site**: not deployed; deploy it by hand", id="stable, not deployed"
        ),
        pytest.param(
            "3.0.0-rc.1", "rc", "", "**Docs site**: unchanged (a prerelease does not deploy it)", id="prerelease"
        ),
    ],
)
def test_summary_reads_the_dist_tag(tmp_path, version, dist_tag, docs, line):
    result = run_step(tmp_path, SUMMARY, {"NEW_VERSION": version, "DIST_TAG": dist_tag, "DOCS_DEPLOY": docs})
    assert result.code == 0, result.out
    assert f"bmad-module-skill-forge/v/{version} (dist-tag `{dist_tag}`)" in result.summary
    assert line in result.summary


# --------------------------------------------------------------------------
# Commit version bump, and setup-uv in every workflow
# --------------------------------------------------------------------------


@needs_shell
def test_commit_skips_the_pre_commit_hook(tmp_path):
    git = [{"match": "add ", "answers": [ok("")]}, {"match": "commit ", "answers": [ok("")]}]
    result = run_step(tmp_path, COMMIT, {"NEW_VERSION": "3.0.0"}, git=git)
    assert result.code == 0, result.out
    assert result.called("git", "commit") == [["git", "commit", "--no-verify", "-m", "release: bump to v3.0.0"]]


def test_husky_opt_out_stays_at_job_level():
    # With --no-verify, either one alone keeps the hook off the release commit.
    assert load_workflow()["jobs"]["release"]["env"]["HUSKY"] == "0"
    assert "git commit --no-verify " in step(COMMIT)["run"]


def test_setup_uv_keys_its_cache_on_files_that_exist():
    # setup-uv hashes the files its cache-dependency-glob matches into the
    # cache key. The default globs (requirements*.txt, pyproject.toml,
    # uv.lock and the like) match no file here, so every run warned "No
    # file matched to"; package.json is where the uv tools are pinned.
    workflows = REPO_ROOT / ".github" / "workflows"
    found = []
    for path in sorted([*workflows.glob("*.yaml"), *workflows.glob("*.yml")]):
        for job_id, job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].items():
            for s in job.get("steps", []):
                if not str(s.get("uses", "")).startswith("astral-sh/setup-uv@"):
                    continue
                where = f"{path.name} {job_id}"
                globs = str((s.get("with") or {}).get("cache-dependency-glob", ""))
                patterns = [p.strip() for p in globs.splitlines() if p.strip()]
                assert patterns, f"{where}: setup-uv has no cache-dependency-glob"
                for pattern in patterns:
                    assert any(REPO_ROOT.glob(pattern)), f"{where}: {pattern} matches no file"
                found.append(where)
    assert {"release.yaml release", "quality.yaml lintlang", "quality.yaml python"} <= set(found)
