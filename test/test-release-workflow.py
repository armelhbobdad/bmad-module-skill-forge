#!/usr/bin/env python3
"""release.yaml: the retry-safe check wait, the cleanup after a failed run,
the version, dist-tag and commit steps, the resume path, the required
checks compared with the ruleset before the bump, and the npm version floor;
and the action pins of every workflow, with their check and Dependabot.

Issues #563, #564, #565, #566, #570 and #571. The main-dispatch path of
.github/workflows/release.yaml only runs for real on a `--ref main` dispatch,
which is also a real npm publish, so these tests run the steps' own `run:`
scripts instead. Each script is read from the workflow with PyYAML and run
under `bash -e`, the runner's default shell, with stub `gh`, `git`, `npm`
and `sleep` commands (and `node`, where a test says so) first on PATH. A
stub answers from a list of rules the test gives (first matching rule wins,
each rule answers its calls in order and repeats its last answer) and logs
every call, so a test can assert what the step asked GitHub or npm to do
and how often it waited.

A failed `gh api --paginate --slurp` call exits 1 but still prints an array,
because gh closes it on the way out: `[]` when no page arrived, the pages
read so far when a later page failed, and the error body as the last page
on an HTTP error. The stubs print the same, so a step that takes that output
for data fails here.

Covers:
  - Push commit to temp branch: the branch name carries the run attempt
  - Open bot PR: a review within the REVIEW_BUDGET of tools/changes.js goes
    into the body as written, under GitHub's 65,536-character limit; a
    longer one, or the notes the fallback shows for a missing review, gives
    way to a pointer to `npm run changes:preview`. Write release notes and
    CHANGELOG.md leaves the run summary to the tool, which writes the full
    review there
  - Wait for required status checks: check-runs read as one list over
    several pages (a context on two pages resolves to its newest run), a
    failed read of every shape retried as a pending tick until the timeout,
    in the registration poll too, a failed check and a timeout that no
    longer say the PR was left open, and that name version_bump=resume, not
    Re-run failed jobs, once the bot PR has merged (or say what to do either
    way when its state cannot be read), any conclusion but success, skipped
    and neutral failing the wait as tools/release-state.js counts it, and a
    step timeout that leaves the loop's own timeout room to come first
  - Cancel action_required pull_request runs: the run list read as one list,
    a failed list read again, then an error
  - Both steps: the head commit lookup retried, then an error
  - Close the bot PR and delete its branch after a failed run: its `if`, an
    open PR closed and then commented on once with a link to the run, a
    merged PR left alone with a warning and a summary that name
    version_bump=resume, the leftover branch of a closed PR or of a run
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
  - The resume path (issue #566): the steps each dispatch runs, from their
    `if:` expressions (a resumed cut runs no step that bumps, commits,
    tests or opens a PR, runs the tag before the publish, skips each part
    already there, and stops after the resume step when nothing is missing;
    the normal paths run none of its steps), what the resume, checkout,
    notes and tag steps run, the guard before the gate, every resume output
    the workflow reads written by tools/release-state.js, the commit
    subject, PR title and temp branch the tool looks for written by the
    workflow, every RELEASING.md scenario they point to there, and the
    summary of a resumed cut
  - Create and push tag on main: the merge commit when main did not move,
    the release commit when it did (the rule tools/release-state.js applies
    for a resumed cut), and errors that name version_bump=resume, or the
    patch ship-forward when resume cannot finish the cut either
  - Check the required checks against the ruleset (issue #570): a cut from
    main runs it right after the tests and before Bump version, a
    prerelease from another branch and a resumed cut skip it, it asks
    tools/check-required-checks.js about the dispatch repository, and
    end to end, with gh answering for the ruleset, a ruleset that disagrees
    with quality.yaml stops it, naming the missing and the extra checks,
    before anything is committed
  - Action pins (issue #571): every `uses:` of every workflow names a
    40-character commit SHA and its exact version (`# vX.Y.Z`), the lines
    read as text are exactly the uses: YAML runs, each action has one pin,
    install-smoke.yaml pins its three actions, and actions/checkout stays on
    v5 with the reason on the line above each pin. The pin check, a Linux
    step of quality.yaml's validate job, passes on this repository naming
    every workflow it read, and on fixture workflows names each uses: it
    refuses and fails when it finds none. .github/dependabot.yaml has one
    monthly github-actions entry whose group lists every action the
    workflows use and that ignores only the major updates of
    actions/checkout. The comment on the docs link guard step names the
    required-checks tool its script also runs
  - Verify npm version floor for OIDC trusted publishing (issue #565): it
    runs on every dispatch right after Setup Node.js (which reads .nvmrc),
    prints Node and its bundled npm, passes from 11.5.1 up (a two-digit
    minor compared as a number) and fails below it naming .nvmrc as the
    fix; no step installs npm or writes $GITHUB_PATH, release.yaml names no
    npm@latest, and no comment describes Node 22.22.2 or its npm 10.9.7

The behaviour tests need bash and jq (both on the GitHub-hosted Ubuntu
runner) and are skipped on Windows. The version step's tests also need node
and the semver devDependency (npm ci), found through NODE_PATH, and so do
the checks that compare the workflow with tools/release-state.js, which
they load.
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
RELEASE_STATE = REPO_ROOT / "tools" / "release-state.js"
RELEASING = REPO_ROOT / "docs" / "_internal" / "RELEASING.md"

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
RESUME_FIND = "Find what the cut on main still needs (resume)"
RESUME_CHECKOUT = "Check out the release commit (resume)"
RESUME_NOTES = "Write the release notes (resume)"
RESUME_TAG = "Create and push the tag (resume)"
GUARD = "Refuse to bump past an unpublished release"
GATE = "Check the version bump against the change fragments"
REQUIRED_CHECKS = "Check the required checks against the ruleset"
NPM_FLOOR = "Verify npm version floor for OIDC trusted publishing"
TAG = "Create and push tag"
MERGE_SHA = "b" * 40
DISPATCH_SHA = "f" * 40

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


def release_state(name: str, tool: str = "release-state.js") -> object:
    """An export of tools/<tool>, release-state.js by default, read through node (needs_node)."""
    proc = subprocess.run(
        ["node", "-e", f"process.stdout.write(JSON.stringify(require('./tools/{tool}').{name}))"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


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
    node: list[dict] | None = None,
    cwd: Path | None = None,
) -> Result:
    stub_dir = tmp_path / "stub"
    bin_dir = tmp_path / "bin"
    stub_dir.mkdir()
    bin_dir.mkdir()
    stub_py = stub_dir / "stub.py"
    stub_py.write_text(STUB, encoding="utf-8")
    # node is stubbed only when a test gives it rules: the version step's
    # tests run the real one.
    stubbed = [("gh", gh), ("git", git), ("npm", npm)] + ([("node", node)] if node is not None else [])
    for tool, rules in stubbed:
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
        cwd=cwd or tmp_path,
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


WAIT_ENV = {"PR_NUMBER": "7", "NEW_VERSION": "3.0.0"}


def wait_rules(
    check_runs: list[dict], pr_view: list[dict] | None = None, state: list[dict] | None = None
) -> list[dict]:
    return [
        {"match": "pr view 7 --json headRefOid", "answers": pr_view or [ok(HEAD_SHA + "\n")]},
        {"match": "pr view 7 --json state --jq .state", "answers": state or [ok("OPEN\n")]},
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
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(THREE_PAGES)]))
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
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(failed_rerun)]))
    assert result.code == 1, result.out
    assert "Required context(s) failed: lint(conclusion=failure" in result.out
    assert "left open" not in result.out
    assert "closes the bot PR, unless it has merged, and deletes its branch" in result.out
    assert "Re-run failed jobs" in result.out
    # The PR is still open, so nothing is merged to resume.
    assert "version_bump=resume" not in result.out


@needs_shell
@pytest.mark.parametrize("failed", slurp_failures(THREE_PAGES))
def test_wait_counts_a_failed_read_as_a_pending_tick(tmp_path, failed):
    # Registration reads fine, one read fails, then the checks are green.
    # Taken for data, `[]` would leave every context unregistered, and the
    # first page alone holds only the failed run of `lint`, so the wait
    # would stop on it.
    answers = [ok(THREE_PAGES), failed, ok(THREE_PAGES)]
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules(answers))
    assert result.code == 0, result.out
    assert result.out.count(f"Reading the check-runs on {HEAD_SHA} failed") == 1
    assert "unregistered" not in result.out
    assert "Required context(s) failed" not in result.out
    assert "All 2 required contexts green" in result.out


@needs_shell
def test_wait_retries_a_failed_read_until_the_timeout(tmp_path):
    answers = [ok(THREE_PAGES), fail("connect: connection refused\n", "[]")]
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules(answers))
    assert result.code == 1, result.out
    assert result.out.count(f"Reading the check-runs on {HEAD_SHA} failed") == 60
    assert "did not all succeed within 1200s" in result.out
    assert "Pending: unknown, the check-runs could not be read." in result.out


@needs_shell
@pytest.mark.parametrize("failed", slurp_failures(THREE_PAGES))
def test_wait_registration_poll_survives_a_failed_read(tmp_path, failed):
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([failed, ok(THREE_PAGES)]))
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
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(pending)]))
    assert result.code == 1, result.out
    assert "did not all succeed within 1200s" in result.out
    assert "Pending: lint(in_progress)" in result.out
    assert "left open" not in result.out
    assert "closes the bot PR, unless it has merged, and deletes its branch" in result.out
    assert "version_bump=resume" not in result.out


# The bot PR merged (an admin merge) before its checks finished, and then
# `lint` failed: main carries v3.0.0, and Re-run failed jobs would cut it
# again from the dispatch commit (issue #566).
LINT_FAILED = pages(
    [
        check_run("lint", "failure", "2026-09-22T19:45:00Z"),
        check_run("validate (ubuntu-latest)", "success", "2026-09-22T19:41:00Z"),
    ]
)
RESUME_HINT = (
    "dispatch release.yaml on main with version_bump=resume, which tags, publishes and creates the GitHub Release "
    "of v3.0.0, each only if missing (docs/_internal/RELEASING.md, Scenario H)"
)


@needs_shell
def test_wait_names_the_resume_path_when_a_check_fails_after_the_merge(tmp_path):
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(LINT_FAILED)], state=[ok("MERGED\n")]))
    assert result.code == 1, result.out
    assert "Required context(s) failed: lint(conclusion=failure" in result.out
    assert "Bot PR #7 was merged before its checks finished, so main now carries v3.0.0" in result.out
    assert f"once every required check on {HEAD_SHA} is green, {RESUME_HINT}" in result.out
    assert "dispatch version_bump=patch instead" in result.out
    assert "Re-run failed jobs" not in result.out
    assert "closes the bot PR" not in result.out


@needs_shell
def test_wait_names_the_resume_path_on_a_timeout_after_the_merge(tmp_path):
    pending = pages([check_run("lint", None, "2026-09-22T19:40:00Z", status="in_progress")])
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(pending)], state=[ok("MERGED\n")]))
    assert result.code == 1, result.out
    assert "did not all succeed within 1200s" in result.out
    assert "so main now carries v3.0.0, which this run does not tag or publish" in result.out
    assert RESUME_HINT in result.out
    assert "Re-run failed jobs" not in result.out


@needs_shell
def test_wait_says_what_to_do_either_way_when_the_pr_state_cannot_be_read(tmp_path):
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(LINT_FAILED)], state=[fail()]))
    assert result.code == 1, result.out
    assert len(result.called("gh", "pr view 7 --json state")) == 3
    # Three reads, a wait between two: none after the last.
    assert result.slept(10) == 2
    assert "closes the bot PR, unless it has merged, and deletes its branch" in result.out
    assert "If bot PR #7 has merged meanwhile, main carries v3.0.0" in result.out
    assert RESUME_HINT in result.out


def test_wait_reads_the_bot_pr_and_the_version_of_the_cut():
    wait = step(WAIT)
    assert wait["env"]["PR_NUMBER"] == "${{ steps.open_pr.outputs.pr_number }}"
    # Its errors name the version main carries once the PR has merged.
    assert wait["env"]["NEW_VERSION"] == "${{ steps.version.outputs.new_version }}"
    # The loop counts only its sleeps toward TIMEOUT, so the step's own
    # timeout leaves room for the registration poll and the calls of each
    # tick: the loop's error, which reads the PR's state, must come first.
    loop = int(re.search(r"^\s*TIMEOUT=(\d+)$", wait["run"], re.MULTILINE).group(1))
    assert wait["timeout-minutes"] * 60 >= loop + 600


@needs_shell
@pytest.mark.parametrize("conclusion", [pytest.param("stale", id="stale"), pytest.param("not_yet_known", id="unknown")])
def test_wait_fails_on_a_conclusion_that_is_not_green(tmp_path, conclusion):
    runs = pages(
        [
            check_run("lint", conclusion, "2026-09-22T19:45:00Z"),
            check_run("validate (ubuntu-latest)", "success", "2026-09-22T19:41:00Z"),
        ]
    )
    result = run_step(tmp_path, WAIT, WAIT_ENV, gh=wait_rules([ok(runs)]))
    assert result.code == 1, result.out
    assert f"Required context(s) failed: lint(conclusion={conclusion}" in result.out
    assert "All 2 required contexts green" not in result.out


@needs_node
def test_the_wait_step_and_the_tool_count_the_same_conclusions_as_green():
    # tools/release-state.js reads the required checks of a resumed cut "as
    # in the Wait step" (RELEASING.md): the same conclusions count as green.
    green = re.search(r"^\s*([\w|]+)\)\n\s*: # green$", step(WAIT)["run"], re.MULTILINE)
    assert green, "the Wait step has no green case"
    assert sorted(green.group(1).split("|")) == sorted(release_state("GREEN_CONCLUSIONS"))


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

CLEANUP_ENV = {"TEMP_BRANCH": TEMP_BRANCH, "NEW_VERSION": "3.0.0", "JOB_STATUS": "failure"}


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
    # The warning for a merged PR names the version main carries.
    assert last["env"]["NEW_VERSION"] == "${{ steps.version.outputs.new_version }}"
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
    # The cut is on main now: the way to finish it is resume, never a re-run.
    warning = (
        "::warning::Bot PR #7 merged before this run stopped, so main now carries v3.0.0, whose tag, npm publish and "
        "GitHub Release this run did not finish. Finish them: dispatch release.yaml on main with version_bump=resume"
    )
    assert warning in result.out
    assert "Do not use Re-run failed jobs: it cuts the version again from the dispatch commit" in result.out
    assert "## Release stopped after the bot PR merged" in result.summary
    assert "version_bump=resume" in result.summary


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


# --------------------------------------------------------------------------
# The bot PR body and the release notes under GitHub's size limits
# --------------------------------------------------------------------------

OPEN_PR = "Open bot PR"
NOTES = "Write release notes and CHANGELOG.md"
PR_BODY_LIMIT = 65_536
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}"
POINTER = (
    "The review is too long for a pull request body: `npm run changes:preview` prints its reasons, "
    "surface changes and notes. Read them, and the `CHANGELOG.md` diff, before approving."
)


def open_pr(tmp_path: Path, review: str | None, notes: str = "## [3.0.0]\n") -> tuple[Result, str]:
    """Run the Open bot PR step with these files; return the result and pr_body.md."""
    (tmp_path / "release_notes.md").write_text(notes, encoding="utf-8")
    if review is not None:
        (tmp_path / "release_review.md").write_text(review, encoding="utf-8")
    gh = [
        {"match": "pr create", "answers": [ok("https://github.com/owner/repo/pull/7\n")]},
        {"match": "pr view", "answers": [ok("7\n")]},
    ]
    result = run_step(tmp_path, OPEN_PR, {"TEMP_BRANCH": TEMP_BRANCH, "NEW_VERSION": "3.0.0"}, gh=gh)
    return result, (tmp_path / "pr_body.md").read_text(encoding="utf-8")


@needs_shell
def test_bot_pr_body_holds_a_review_within_the_budget(tmp_path):
    review = "## Review before approving\n\n" + ("- a line of the review that fits\n" * 1800)
    assert len(review) < 60_000
    result, body = open_pr(tmp_path, review)
    assert result.code == 0, result.out
    assert result.called("gh", "pr create", "--body-file pr_body.md")
    assert review in body
    assert f"## Workflow run\n\n{RUN_URL}\n" in body
    assert len(body) < PR_BODY_LIMIT
    assert "::warning::" not in result.out


@needs_shell
@pytest.mark.parametrize(
    "review, notes",
    [(("x" * 70 + "\n") * 1000, "## [3.0.0]\n"), (None, ("y" * 99 + "\n") * 1200)],
    ids=["review", "fallback notes"],
)
def test_bot_pr_body_points_to_the_preview_when_the_review_is_over_the_budget(tmp_path, review, notes):
    # A review written some other way, or the notes the fallback shows when
    # the review is missing (a shortened release body runs to 120,000).
    result, body = open_pr(tmp_path, review, notes)
    assert result.code == 0, result.out
    assert len(body) < PR_BODY_LIMIT
    assert f"## Review before approving\n\n{POINTER}\n" in body
    assert f"## Workflow run\n\n{RUN_URL}\n" in body
    assert "::warning::release_review.md is over 60000 characters" in result.out


@needs_node
def test_bot_pr_step_checks_the_review_against_the_budget_of_the_tool():
    budget = release_state("REVIEW_BUDGET", "changes.js")
    assert f"REVIEW_BUDGET={budget}\n" in step(OPEN_PR)["run"]
    assert budget + 1_000 < release_state("PR_BODY_LIMIT", "changes.js") == PR_BODY_LIMIT


def test_the_notes_step_leaves_the_run_summary_to_the_tool():
    # tools/changes.js writes the full review into the step summary (within
    # its 1 MiB limit); a copy of release_review.md would add the shortened one.
    run = step(NOTES)["run"]
    assert "--notes release_notes.md --review release_review.md" in run
    assert "GITHUB_STEP_SUMMARY" not in run


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
    # that channel, so the choices and the rule move together. resume bumps
    # nothing: it publishes the version main already carries.
    prereleases = [choice for choice in version_bump_choices() if choice not in ("patch", "minor", "major", "resume")]
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


# --------------------------------------------------------------------------
# The resume path (issue #566)
# --------------------------------------------------------------------------

# A step's `if:` as GitHub evaluates the expressions release.yaml uses:
# string literals, ==, !=, !, && (before ||), parentheses, the status
# functions and the github and steps contexts, where an output of a step
# that has not run is the empty string.
EXPRESSION_TOKEN = re.compile(
    r"\s*(?:(?P<text>'(?:[^']|'')*')|(?P<op>&&|\|\||==|!=|!|\(|\))"
    r"|(?P<call>[A-Za-z_]\w*)\(\)|(?P<name>[A-Za-z_][\w.-]*))"
)
# Every step before the one evaluated succeeded, so the success() that an
# `if:` without a status function implies is true.
STATUS = {"success": True, "always": True, "failure": False, "cancelled": False}


def evaluate(expression: str, context: dict[str, str], outputs: dict[str, dict[str, str]]) -> bool:
    """Whether a step with this `if:` runs in a job where every earlier step succeeded."""
    text = expression.strip()
    tokens = []
    pos = 0
    while pos < len(text):
        token = EXPRESSION_TOKEN.match(text, pos)
        assert token and token.end() > pos, f"cannot read {text[pos:]!r} in {expression!r}"
        pos = token.end()
        tokens.append((token.lastgroup, token.group(token.lastgroup)))
    tokens.append(("end", ""))
    at = 0

    def take() -> tuple[str, str]:
        nonlocal at
        at += 1
        return tokens[at - 1]

    def value(kind: str, raw: str) -> str | bool:
        if kind == "text":
            return raw[1:-1].replace("''", "'")
        if kind == "call":
            return STATUS[raw]
        parts = raw.split(".")
        if parts[0] == "steps":
            assert len(parts) == 4 and parts[2] == "outputs", raw
            return outputs.get(parts[1], {}).get(parts[3], "")
        assert raw in context, f"unknown context {raw} in {expression!r}"
        return context[raw]

    def atom() -> str | bool:
        kind, raw = take()
        if (kind, raw) == ("op", "("):
            result = either()
            assert take() == ("op", ")"), expression
            return result
        assert kind in ("text", "call", "name"), f"unexpected {raw!r} in {expression!r}"
        return value(kind, raw)

    def comparison() -> str | bool:
        left = atom()
        if tokens[at] in (("op", "=="), ("op", "!=")):
            operator = take()[1]
            right = atom()
            return (left == right) == (operator == "==")
        return left

    def negation() -> bool:
        if tokens[at] == ("op", "!"):
            take()
            return not negation()
        return bool(comparison())

    def both() -> bool:
        result = negation()
        while tokens[at] == ("op", "&&"):
            take()
            result = negation() and result
        return result

    def either() -> bool:
        result = both()
        while tokens[at] == ("op", "||"):
            take()
            result = both() or result
        return result

    result = either()
    assert tokens[at] == ("end", ""), f"unread {tokens[at:]} in {expression!r}"
    return result


def steps_that_run(ref: str, bump: str, outputs: dict[str, dict[str, str]]) -> list[str]:
    """The steps a dispatch runs when every step succeeds, each step id's outputs set once it has run."""
    context = {"github.ref": ref, "github.event.inputs.version_bump": bump}
    produced: dict[str, dict[str, str]] = {}
    ran = []
    for s in steps():
        if evaluate(str(s.get("if", "success()")), context, produced):
            ran.append(s["name"])
            if s.get("id") in outputs:
                produced[s["id"]] = outputs[s["id"]]
    return ran


RESUME_STEPS = [RESUME_FIND, RESUME_CHECKOUT, RESUME_NOTES, RESUME_TAG]
PR_FLOW = [
    TEMP_PUSH,
    "Open bot PR",
    "Force-trigger required status checks on bot PR",
    CANCEL,
    WAIT,
    "Wait for PR approval or admin-bypass merge",
    "Auto-merge bot PR",
    "Wait for merge completion",
]
SETUP = ["Checkout", "Setup Node.js", NPM_FLOOR]
CUT_OUTPUTS = {
    "version": {"new_version": "3.0.0", "dist_tag": "latest"},
    "temp_push": {"temp_branch": TEMP_BRANCH},
    "open_pr": {"pr_number": "7"},
    "wait_approval": {"already_merged": "false"},
}


def resume_outputs(**missing: str) -> dict[str, dict[str, str]]:
    plan = {"done": "false", "create_tag": "true", "publish": "true", "create_release": "true", **missing}
    return {"resume": plan, "version": {"new_version": "3.0.0", "dist_tag": "latest"}}


def test_a_resumed_cut_runs_what_is_missing_in_the_order_of_a_cut():
    ran = steps_that_run("refs/heads/main", "resume", resume_outputs())
    assert ran == [
        *SETUP,
        "Install dependencies",
        RESUME_FIND,
        RESUME_CHECKOUT,
        "Configure Git",
        VERSION,
        RESUME_NOTES,
        DRY_RUN,
        RESUME_TAG,
        PUBLISH,
        GH_RELEASE,
        DOCS,
        SUMMARY,
    ]


def test_a_resumed_cut_skips_the_parts_already_there():
    ran = steps_that_run("refs/heads/main", "resume", resume_outputs(create_tag="false", publish="false"))
    assert ran == [
        *SETUP,
        "Install dependencies",
        RESUME_FIND,
        RESUME_CHECKOUT,
        "Configure Git",
        VERSION,
        RESUME_NOTES,
        GH_RELEASE,
        DOCS,
        SUMMARY,
    ]


def test_a_resumed_cut_with_only_the_tag_missing_writes_no_notes_and_creates_no_release():
    # Scenario E after the tag was deleted: npm and the GitHub Release are
    # there, so the run neither publishes nor writes notes for a Release.
    ran = steps_that_run("refs/heads/main", "resume", resume_outputs(publish="false", create_release="false"))
    assert ran == [
        *SETUP,
        "Install dependencies",
        RESUME_FIND,
        RESUME_CHECKOUT,
        "Configure Git",
        VERSION,
        RESUME_TAG,
        DOCS,
        SUMMARY,
    ]


def test_a_resume_with_nothing_missing_stops_after_the_resume_step():
    ran = steps_that_run("refs/heads/main", "resume", {"resume": {"done": "true"}})
    assert ran == [*SETUP, "Install dependencies", RESUME_FIND, "Configure Git"]


def test_a_resumed_cut_never_bumps_tests_commits_or_opens_a_pr():
    never = {
        "Install uv",
        GUARD,
        GATE,
        "Run tests and validation",
        "Bump version",
        "Update marketplace.json version",
        "Update docs/_data/pinned.yaml skf_version",
        "Write release notes and CHANGELOG.md",
        COMMIT,
        *PR_FLOW,
        "Skip PR flow (non-main dispatch ref)",
        "Create and push tag",
        CLEANUP,
    }
    for outputs in (resume_outputs(), {"resume": {"done": "true"}}):
        assert never.isdisjoint(steps_that_run("refs/heads/main", "resume", outputs))


def test_a_cut_from_main_runs_no_resume_step_and_the_guard_before_the_gate():
    ran = steps_that_run("refs/heads/main", "major", CUT_OUTPUTS)
    names = [s["name"] for s in steps()]
    skipped = [name for name in names if name not in ran]
    assert skipped == [
        RESUME_FIND,
        RESUME_CHECKOUT,
        RESUME_NOTES,
        "Skip PR flow (non-main dispatch ref)",
        RESUME_TAG,
        CLEANUP,
    ]
    assert ran.index(GUARD) < ran.index(GATE) < ran.index("Run tests and validation")


def test_a_prerelease_from_a_branch_runs_no_resume_step_and_no_guard():
    outputs = {"version": {"new_version": "3.0.1-alpha.0", "dist_tag": "alpha"}}
    ran = steps_that_run("refs/heads/feat/x", "alpha", outputs)
    for name in [*RESUME_STEPS, GUARD, *PR_FLOW, DOCS, CLEANUP]:
        assert name not in ran, name
    assert "Skip PR flow (non-main dispatch ref)" in ran
    assert ran.index("Create and push tag") < ran.index(PUBLISH)


def test_resume_is_a_choice_of_version_bump():
    workflow = load_workflow()
    version_bump = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]["version_bump"]
    assert version_bump["options"][-1] == "resume"
    assert "resume" in version_bump["description"]


NODE_OK = [{"match": "tools/", "answers": [ok("")]}]


@needs_shell
def test_resume_step_asks_the_tool_about_the_dispatch_ref_and_repository(tmp_path):
    result = run_step(tmp_path, RESUME_FIND, {}, node=NODE_OK)
    assert result.code == 0, result.out
    resume = ["node", "tools/release-state.js", "resume"]
    assert result.called("node") == [[*resume, "--ref", "refs/heads/main", "--repo", REPOSITORY]]
    assert step(RESUME_FIND)["id"] == "resume"


@needs_shell
def test_a_refusal_of_the_tool_stops_the_run(tmp_path):
    refusal = [{"match": "tools/", "answers": [{"exit": 1, "stdout": "The resume path refuses: no merged bot PR.\n"}]}]
    for name, env in ((RESUME_FIND, {}), (GUARD, {"VERSION_BUMP": "major"})):
        run_dir = tmp_path / ("resume" if name == RESUME_FIND else "guard")
        run_dir.mkdir()
        assert run_step(run_dir, name, env, node=refusal).code == 1, name


@needs_shell
def test_guard_step_passes_the_version_bump(tmp_path):
    result = run_step(tmp_path, GUARD, {"VERSION_BUMP": "major"}, node=NODE_OK)
    assert result.code == 0, result.out
    assert result.called("node") == [["node", "tools/release-state.js", "guard", "--bump", "major"]]
    assert step(GUARD)["env"]["VERSION_BUMP"] == "${{ github.event.inputs.version_bump }}"


@needs_shell
def test_resume_checks_out_the_release_commit_and_installs_its_lockfile(tmp_path):
    git = [{"match": "checkout", "answers": [ok("")]}]
    npm = [{"match": "ci", "answers": [ok("")]}]
    result = run_step(tmp_path, RESUME_CHECKOUT, {"HEAD_SHA": HEAD_SHA}, git=git, npm=npm)
    assert result.code == 0, result.out
    assert result.called("git") == [["git", "checkout", "--quiet", "--detach", HEAD_SHA]]
    assert result.called("npm") == [["npm", "ci"]]
    assert step(RESUME_CHECKOUT)["env"]["HEAD_SHA"] == "${{ steps.resume.outputs.head_sha }}"


RESUME_NOTES_ENV = {"VERSION": "3.0.0", "BASE": "v2.2.0", "DATE": "2026-09-30"}


@needs_shell
def test_resume_notes_take_the_base_and_the_date_of_the_resume_step(tmp_path):
    # The stub node writes nothing, so the notes file is there already.
    (tmp_path / "release_notes.md").write_text("## [3.0.0]\n", encoding="utf-8")
    result = run_step(tmp_path, RESUME_NOTES, RESUME_NOTES_ENV, node=NODE_OK)
    assert result.code == 0, result.out
    notes = ["node", "tools/changes.js", "release", "--notes-only", "--base", "v2.2.0", "--version", "3.0.0"]
    assert result.called("node") == [[*notes, "--date", "2026-09-30", "--notes", "release_notes.md"]]
    env = step(RESUME_NOTES)["env"]
    assert (env["BASE"], env["DATE"]) == ("${{ steps.resume.outputs.base }}", "${{ steps.resume.outputs.date }}")


@needs_shell
def test_resume_stops_before_the_tag_when_the_notes_are_empty(tmp_path):
    result = run_step(tmp_path, RESUME_NOTES, RESUME_NOTES_ENV, node=NODE_OK)
    assert result.code == 1, result.out
    message = "::error::release_notes.md is empty or missing, so this run tagged, published and released nothing."
    assert message in result.out


@needs_shell
def test_resume_tags_the_anchor_it_was_given_then_pushes_the_tag(tmp_path):
    git = [{"match": "tag -a", "answers": [ok("")]}, {"match": "push origin v3.0.0", "answers": [ok("")]}]
    env = {"VERSION": "3.0.0", "ANCHOR": MERGE_SHA, "ANCHOR_KIND": "merge commit"}
    result = run_step(tmp_path, RESUME_TAG, env, git=git)
    assert result.code == 0, result.out
    assert result.called("git") == [
        ["git", "tag", "-a", "v3.0.0", "-m", "Release v3.0.0", MERGE_SHA],
        ["git", "push", "origin", "v3.0.0"],
    ]
    assert f"Tagged v3.0.0 on the merge commit {MERGE_SHA}" in result.out
    assert step(RESUME_TAG)["env"]["ANCHOR"] == "${{ steps.resume.outputs.anchor }}"


@needs_node
def test_every_resume_output_the_workflow_reads_is_one_the_tool_writes():
    read = set(re.findall(r"steps\.resume\.outputs\.(\w+)", WORKFLOW.read_text(encoding="utf-8")))
    written = set(release_state("RESUME_OUTPUTS"))
    assert {"done", "create_tag", "publish", "create_release", "anchor", "base", "date"} <= read
    assert read <= written, sorted(read - written)


@needs_node
def test_the_tool_looks_for_the_subject_title_and_branch_the_workflow_writes():
    # The resume path finds the bot PR by its title and branch, and the guard
    # the release commit by its subject: another wording here would leave
    # every cut unresumable and let every bump past it.
    subject = release_state("BOT_SUBJECT_PREFIX")
    branch = release_state("BOT_BRANCH_PREFIX")
    assert f'git commit --no-verify -m "{subject}$NEW_VERSION"' in step(COMMIT)["run"]
    assert f'--title "{subject}$NEW_VERSION"' in step("Open bot PR")["run"]
    assert f'TEMP_BRANCH="{branch}$NEW_VERSION-' in step(TEMP_PUSH)["run"]


def test_every_scenario_the_workflow_and_the_tool_point_to_is_in_releasing_md():
    scenarios = set(re.findall(r"^### Scenario ([A-Z])\b", RELEASING.read_text(encoding="utf-8"), re.MULTILINE))
    for path in (WORKFLOW, RELEASE_STATE):
        # A pointer that a comment wraps onto its next line counts too.
        text = re.sub(r"\s*\n\s*(?:#|\*|//)?\s*", " ", path.read_text(encoding="utf-8"))
        pointers = set(re.findall(r"RELEASING\.md,? Scenario ([A-Z])\b", text))
        assert pointers, path.name
        assert pointers <= scenarios, f"{path.name}: {sorted(pointers - scenarios)}"


@needs_shell
def test_summary_of_a_resumed_cut_points_to_the_resume_section(tmp_path):
    env = {"VERSION_BUMP": "resume", "NEW_VERSION": "3.0.0", "DIST_TAG": "latest", "DOCS_DEPLOY": "dispatched"}
    result = run_step(tmp_path, SUMMARY, env)
    assert result.code == 0, result.out
    line = (
        "- Dispatch: `version_bump=resume` on `main`, nothing bumped or committed; "
        "what it did and what was already there is listed under **Resume v3.0.0** above"
    )
    assert line in result.summary
    assert "Temp branch" not in result.summary
    # The resume step's own section says what the run did, so the summary reads none of its outputs.
    assert not [name for name in step(SUMMARY)["env"] if name.startswith("RESUME_")]


# --------------------------------------------------------------------------
# Create and push tag, main path
# --------------------------------------------------------------------------

TAG_ENV = {"NEW_VERSION": "3.0.0", "PR_NUMBER": "7", "GITHUB_SHA": DISPATCH_SHA}
TAG_GH = [{"match": "pr view 7 --json mergeCommit", "answers": [ok(MERGE_SHA + "\n")]}]


def tag_rules(merge_parent: str, head_on_main: bool = True, fetch: dict | None = None) -> list[dict]:
    """git for a cut whose bot PR merged as MERGE_SHA, with `merge_parent` as its first parent; HEAD is HEAD_SHA."""
    return [
        {"match": "fetch origin main", "answers": [fetch or ok("")]},
        {"match": "rev-parse origin/main", "answers": [ok(MERGE_SHA + "\n")]},
        {"match": "cat-file -e", "answers": [ok("")]},
        {"match": f"rev-parse {MERGE_SHA}^1", "answers": [ok(merge_parent + "\n")]},
        {"match": "merge-base --is-ancestor HEAD", "answers": [ok("") if head_on_main else {"exit": 1}]},
        {"match": "rev-parse HEAD", "answers": [ok(HEAD_SHA + "\n")]},
        {"match": "rev-parse v3.0.0", "answers": [{"exit": 1}]},
        {"match": "tag -a", "answers": [ok("")]},
        {"match": "push origin v3.0.0", "answers": [ok("")]},
    ]


# The two shapes test-release-state.js gives decideResume, which applies this
# step's rule to a resumed cut: the two must put the tag on the same commit.
@needs_shell
@pytest.mark.parametrize(
    ("merge_parent", "anchor", "kind"),
    [
        pytest.param(DISPATCH_SHA, MERGE_SHA, "merge commit", id="main did not move"),
        pytest.param("e" * 40, HEAD_SHA, "release commit", id="main moved"),
    ],
)
def test_the_tag_step_tags_the_commit_resume_would(tmp_path, merge_parent, anchor, kind):
    result = run_step(tmp_path, TAG, TAG_ENV, gh=TAG_GH, git=tag_rules(merge_parent))
    assert result.code == 0, result.out
    assert result.output == f"anchor={anchor}\nanchor_kind={kind}\n"
    assert result.called("git", "tag -a") == [["git", "tag", "-a", "v3.0.0", "-m", "Release v3.0.0", anchor]]
    assert result.called("git", "push origin v3.0.0")


@needs_shell
def test_a_failed_fetch_in_the_tag_step_names_resume_not_a_re_run(tmp_path):
    # The bot PR has merged by now: Re-run failed jobs would cut v3.0.0 again.
    git = tag_rules(DISPATCH_SHA, fetch=fail("fatal: unable to access 'https://github.com/owner/repo/'\n"))
    result = run_step(tmp_path, TAG, TAG_ENV, gh=TAG_GH, git=git)
    assert result.code == 1, result.out
    message = (
        "::error::git fetch origin main failed, so the tag cannot be anchored. Nothing was tagged or published, "
        "and main carries v3.0.0: once origin can be fetched again (check the network and the token), dispatch "
        "release.yaml on main with version_bump=resume (docs/_internal/RELEASING.md, Scenario H). "
        "Do not use Re-run failed jobs"
    )
    assert message in result.out
    assert not result.called("git", "tag -a")


@needs_shell
def test_the_squash_merge_error_of_the_tag_step_names_the_ship_forward(tmp_path):
    # main moved and the PR was squash-merged: the release commit is off main.
    result = run_step(tmp_path, TAG, TAG_ENV, gh=TAG_GH, git=tag_rules("e" * 40, head_on_main=False))
    assert result.code == 1, result.out
    ship_forward = "version_bump=resume cannot finish the cut either: ship v3.0.0 forward with version_bump=patch"
    assert ship_forward in result.out
    assert not result.called("git", "tag -a")


# --------------------------------------------------------------------------
# Check the required checks against the ruleset (issue #570)
# --------------------------------------------------------------------------


def test_a_cut_from_main_checks_the_ruleset_right_after_the_tests_and_before_the_bump():
    ran = steps_that_run("refs/heads/main", "major", CUT_OUTPUTS)
    assert ran[ran.index("Run tests and validation") + 1] == REQUIRED_CHECKS
    assert ran.index(REQUIRED_CHECKS) < ran.index("Bump version") < ran.index(COMMIT) < ran.index(TEMP_PUSH)


def test_only_a_cut_from_main_checks_the_ruleset():
    # A prerelease from another branch opens no bot PR, and a resumed cut
    # runs no tests and no bump.
    prerelease = {"version": {"new_version": "3.0.1-alpha.0", "dist_tag": "alpha"}}
    assert REQUIRED_CHECKS not in steps_that_run("refs/heads/feat/x", "alpha", prerelease)
    for outputs in (resume_outputs(), {"resume": {"done": "true"}}):
        assert REQUIRED_CHECKS not in steps_that_run("refs/heads/main", "resume", outputs)


@needs_shell
def test_the_ruleset_check_asks_the_tool_about_the_dispatch_repository(tmp_path):
    result = run_step(tmp_path, REQUIRED_CHECKS, {}, node=NODE_OK)
    assert result.code == 0, result.out
    assert result.called("node") == [["node", "tools/check-required-checks.js", "--ruleset", "--repo", REPOSITORY]]


@needs_shell
@pytest.mark.parametrize("exit_code", [pytest.param(1, id="drift"), pytest.param(2, id="cannot-run")])
def test_a_ruleset_check_that_fails_stops_the_run(tmp_path, exit_code):
    node = [{"match": "tools/", "answers": [{"exit": exit_code, "stdout": "The Default ruleset ... disagree\n"}]}]
    assert run_step(tmp_path, REQUIRED_CHECKS, {}, node=node).code == exit_code


def test_the_ruleset_check_and_the_wait_step_read_the_same_ruleset():
    # The tool reads the ruleset through tools/release-state.js, by name.
    assert 'select(.name=="Default")' in step(WAIT)["run"]
    assert "candidate.name === 'Default'" in RELEASE_STATE.read_text(encoding="utf-8")


def quality_checks() -> list[str]:
    """The check names tools/check-required-checks.js derives from this repository's quality.yaml."""
    proc = subprocess.run(
        ["node", "tools/check-required-checks.js"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def ruleset_rules(required: list[str]) -> list[dict]:
    """gh answering for the Default ruleset, found by name, with these required checks."""
    body = {
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": [{"context": c} for c in required]},
            }
        ]
    }
    return [
        {"match": f"repos/{REPOSITORY}/rulesets/5", "answers": [ok(json.dumps(body))]},
        {"match": f"repos/{REPOSITORY}/rulesets", "answers": [ok(json.dumps([{"name": "Default", "id": 5}]))]},
    ]


@needs_shell
@needs_node
def test_the_ruleset_check_passes_when_the_ruleset_requires_every_job(tmp_path):
    checks = quality_checks()
    result = run_step(tmp_path, REQUIRED_CHECKS, {}, gh=ruleset_rules(checks), cwd=REPO_ROOT)
    assert result.code == 0, result.out
    assert f"The Default ruleset of {REPOSITORY} requires the {len(checks)} checks" in result.out
    assert [c[1:3] for c in result.called("gh")] == [
        ["api", f"repos/{REPOSITORY}/rulesets"],
        ["api", f"repos/{REPOSITORY}/rulesets/5"],
    ]


@needs_shell
@needs_node
def test_a_ruleset_that_disagrees_with_quality_yaml_stops_the_run_naming_each_check(tmp_path):
    # The ruleset lost `docs-links` and still requires a `lint` no job reports.
    checks = quality_checks()
    assert "docs-links" in checks
    required = [c for c in checks if c != "docs-links"] + ["lint"]
    result = run_step(tmp_path, REQUIRED_CHECKS, {}, gh=ruleset_rules(required), cwd=REPO_ROOT)
    assert result.code == 1, result.out
    assert "  reported by a quality.yaml job, but not required, so it gates nothing: `docs-links`" in result.out
    assert "  required, but no quality.yaml job reports it" in result.out
    assert result.out.count("`lint`") == 1


# --------------------------------------------------------------------------
# Verify npm version floor for OIDC trusted publishing (issue #565)
# --------------------------------------------------------------------------


def floor_tools(node_version: str, npm_version: str) -> dict[str, list[dict]]:
    """node and npm answering `--version` as setup-node's Node and its bundled npm would."""
    return {
        "node": [{"match": "--version", "answers": [ok(node_version + "\n")]}],
        "npm": [{"match": "--version", "answers": [ok(npm_version + "\n")]}],
    }


@needs_shell
@pytest.mark.parametrize(
    "npm_version",
    [
        pytest.param("11.5.1", id="at the floor"),
        # A string compare would put 11.10.0 below 11.5.1.
        pytest.param("11.10.0", id="two-digit minor"),
        pytest.param("11.19.0", id="Node 24 in the v2.2.0 run"),
        pytest.param("12.0.2", id="next major"),
    ],
)
def test_the_floor_check_prints_node_and_its_bundled_npm_and_passes_from_11_5_1(tmp_path, npm_version):
    result = run_step(tmp_path, NPM_FLOOR, {}, **floor_tools("v24.21.0", npm_version))
    assert result.code == 0, result.out
    assert f"Node: v24.21.0; bundled npm: {npm_version}" in result.out
    assert "::error::" not in result.out
    assert result.called("npm") == [["npm", "--version"]]


@needs_shell
@pytest.mark.parametrize(
    ("node_version", "npm_version"),
    [
        pytest.param("v24.0.0", "11.5.0", id="just below"),
        pytest.param("v22.22.2", "10.9.7", id="Node 22 npm"),
    ],
)
def test_the_floor_check_fails_below_11_5_1_and_names_nvmrc_as_the_fix(tmp_path, node_version, npm_version):
    result = run_step(tmp_path, NPM_FLOOR, {}, **floor_tools(node_version, npm_version))
    assert result.code == 1, result.out
    assert f"Node: {node_version}; bundled npm: {npm_version}" in result.out
    message = (
        f"::error::npm {npm_version}, the one bundled with Node {node_version}, is below the OIDC "
        "trusted-publishing floor (11.5.1), so the run stopped before anything was committed, tagged or "
        "published. Fix .nvmrc: in a pull request, move it to a Node version whose bundled npm is 11.5.1 or later"
    )
    assert message in result.out
    # The npm that ships with Node is the only one: nothing to blame on PATH.
    assert "PATH" not in result.out


def test_the_floor_check_runs_on_every_dispatch_right_after_setup_node():
    names = [s["name"] for s in steps()]
    assert names[: len(SETUP)] == SETUP
    assert "if" not in step(NPM_FLOOR)
    assert step("Setup Node.js")["with"]["node-version-file"] == ".nvmrc"
    for ref, bump, outputs in (
        ("refs/heads/main", "major", CUT_OUTPUTS),
        ("refs/heads/feat/x", "alpha", {"version": {"new_version": "3.0.1-alpha.0", "dist_tag": "alpha"}}),
        ("refs/heads/main", "resume", resume_outputs()),
    ):
        ran = steps_that_run(ref, bump, outputs)
        assert ran.index(NPM_FLOOR) < ran.index("Install dependencies") < ran.index(PUBLISH), (ref, bump)


def test_no_step_installs_npm_so_the_publish_uses_the_one_node_ships():
    # npm@latest put a major nobody chose on the v2.2.0 publish (11.19.0
    # bundled, 12.0.2 installed). A step that installs npm must pin one
    # exact version; none is needed while Node 24 ships 11.19.0.
    assert "npm@latest" not in WORKFLOW.read_text(encoding="utf-8")
    for s in steps():
        run = s.get("run", "")
        assert not re.search(r"\bnpm\s+(?:install|i|add|update|up)\b", run), s["name"]
        assert "GITHUB_PATH" not in run, s["name"]


def test_no_comment_describes_node_22_or_its_npm():
    # The side-prefix install was written for Node 22.22.2 and its npm
    # 10.9.7; .nvmrc selects Node 24 now.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "22.22.2" not in text
    assert "10.9.7" not in text
    assert "side-prefix" not in text.lower()


# --------------------------------------------------------------------------
# Action pins and Dependabot (issue #571)
# --------------------------------------------------------------------------

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
QUALITY = WORKFLOWS / "quality.yaml"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yaml"
PIN_CHECK = "Check that every action is pinned to a commit SHA"
# A `uses:` key opens its line, after the indent and an optional list dash,
# as the pin check reads it.
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:(.*)$")
PIN = re.compile(r"^(?P<action>[^\s@]+)@(?P<sha>[0-9a-f]{40}) # (?P<version>v\d+\.\d+\.\d+)$")
CHECKOUT_HOLD = "# Held on v5: v6 changes how it stores the git credentials, and release.yaml pushes with them."


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOWS.glob("*.yaml"), *WORKFLOWS.glob("*.yml")])


def uses_lines(path: Path) -> list[tuple[int, str]]:
    """(line number, value with its comment) of every `uses:` key of a workflow, read as text."""
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = USES_LINE.match(line)
        if match:
            found.append((number, match.group(1).strip()))
    return found


def parsed_uses(path: Path) -> list[str]:
    """Every `uses:` value YAML reads in a workflow: its steps' and its reusable-workflow jobs'."""
    values = []
    for job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].values():
        if "uses" in job:
            values.append(job["uses"])
        values.extend(s["uses"] for s in job.get("steps", []) if "uses" in s)
    return values


def pins() -> list[tuple[str, int, re.Match]]:
    """(workflow name, line number, PIN match) of every `uses:` that names an action."""
    found = []
    for path in workflow_files():
        for number, value in uses_lines(path):
            if not value.startswith("./"):
                found.append((path.name, number, PIN.match(value)))
    return found


def test_every_action_is_pinned_to_a_commit_sha_with_its_exact_version():
    names = [path.name for path in workflow_files()]
    for name in ("quality.yaml", "release.yaml", "docs.yaml", "install-smoke.yaml", "health-check-dedup.yaml"):
        assert name in names
    for path in workflow_files():
        # The text the pin check reads holds exactly the uses: YAML runs.
        assert [value.split(" #")[0] for _, value in uses_lines(path)] == parsed_uses(path), path.name
        # The acceptance grep of issue #571: no uses: names a version tag.
        assert not re.search(r"uses: [^ ]+@v[0-9]", path.read_text(encoding="utf-8")), path.name
    unpinned = [f"{name}:{number}" for name, number, match in pins() if match is None]
    assert unpinned == []


def test_each_action_has_one_pin_across_the_workflows():
    # A partial update would run two commits of one action.
    seen: dict[str, set[tuple[str, str]]] = {}
    for _, _, match in pins():
        if match:
            seen.setdefault(match["action"], set()).add((match["sha"], match["version"]))
    assert {action: len(shas) for action, shas in seen.items() if len(shas) != 1} == {}


def test_install_smoke_pins_its_three_actions():
    pinned = {match["action"] for name, _, match in pins() if name == "install-smoke.yaml" and match}
    assert {"actions/setup-node", "actions/upload-artifact", "actions/download-artifact"} <= pinned


def test_checkout_stays_on_v5_with_the_reason_beside_each_pin():
    checkouts = []
    for path in workflow_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, value in uses_lines(path):
            if not value.startswith("actions/checkout@"):
                continue
            checkouts.append(path.name)
            match = PIN.match(value)
            assert match and match["version"].startswith("v5."), f"{path.name}:{number}"
            assert lines[number - 2].strip() == CHECKOUT_HOLD, f"{path.name}:{number}"
    # release.yaml pushes with the credentials of its own checkout.
    assert "release.yaml" in checkouts


def pin_check_step() -> dict:
    found = [
        (job_id, s)
        for job_id, job in yaml.safe_load(QUALITY.read_text(encoding="utf-8"))["jobs"].items()
        for s in job.get("steps", [])
        if s.get("name") == PIN_CHECK
    ]
    assert [job_id for job_id, _ in found] == ["validate"]
    return found[0][1]


def test_the_pin_check_is_a_step_of_the_validate_job_on_linux():
    # A step of a required job, not a new required job.
    s = pin_check_step()
    assert s["if"] == "runner.os == 'Linux'"
    assert "shell" not in s
    validate = yaml.safe_load(QUALITY.read_text(encoding="utf-8"))["jobs"]["validate"]
    assert "ubuntu-latest" in validate["strategy"]["matrix"]["os"]


def run_pin_check(tmp_path: Path, cwd: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "pin-check.sh"
    script.write_text(pin_check_step()["run"], encoding="utf-8")
    return subprocess.run(["bash", "-e", str(script)], cwd=cwd, capture_output=True, text=True, timeout=60)


@needs_shell
def test_the_pin_check_passes_on_this_repository_and_reads_every_workflow(tmp_path):
    proc = run_pin_check(tmp_path, REPO_ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    total = 0
    for path in workflow_files():
        count = len(uses_lines(path))
        assert f"Checked {count} uses: in .github/workflows/{path.name}\n" in proc.stdout
        total += count
    assert "Checked 3 uses: in .github/workflows/install-smoke.yaml\n" in proc.stdout
    assert f"All {total} uses: in .github/workflows/ name a commit SHA and its version." in proc.stdout


SAMPLE_SHA = "1234567890abcdef1234567890abcdef12345678"
PINNED = f"actions/checkout@{SAMPLE_SHA} # v5.1.0"
# Line by line: the ones the check refuses are marked.
PIN_FIXTURE = [
    ("jobs:", False),
    ("  a:", False),
    ("    steps:", False),
    ("      - uses: actions/checkout@v5", True),
    ("      - uses: actions/checkout@main", True),
    ("      - uses: actions/checkout@fbc6f39 # v5.1.0", True),
    (f"      - uses: actions/checkout@{SAMPLE_SHA}", True),
    (f"      - uses: actions/checkout@{SAMPLE_SHA} # v5", True),
    (f"      - uses: actions/checkout@{SAMPLE_SHA.upper()} # v5.1.0", True),
    (f'      - uses: "{PINNED}"', True),
    (f"      - uses: {PINNED}", False),
    ("      - name: Local", False),
    ("        uses: ./.github/actions/local", False),
    ("      # uses: actions/checkout@v5", False),
    ("      - run: |", False),
    ('          echo "the publish below uses: it"', False),
    ("  b:", False),
    ("    uses: owner/repo/.github/workflows/build.yaml@v1", True),
]


@needs_shell
def test_the_pin_check_names_each_uses_that_is_not_pinned(tmp_path):
    workflows = tmp_path / "repo" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yaml").write_text("\n".join(line for line, _ in PIN_FIXTURE) + "\n", encoding="utf-8")
    # A .yml workflow is read as well.
    (workflows / "b.yml").write_text("jobs:\n  c:\n    steps:\n      - uses: actions/setup-node@v6\n", encoding="utf-8")
    proc = run_pin_check(tmp_path, tmp_path / "repo")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    refused = [n for n, (_, bad) in enumerate(PIN_FIXTURE, start=1) if bad]
    reported = [int(m) for m in re.findall(r"::error file=\.github/workflows/a\.yaml,line=(\d+)::", proc.stdout)]
    assert reported == refused
    assert "::error file=.github/workflows/b.yml,line=4::Not pinned to a commit SHA with its version: " in proc.stdout
    assert "uses: actions/setup-node@v6\n" in proc.stdout
    uses = sum(1 for line, _ in PIN_FIXTURE if USES_LINE.match(line)) + 1
    assert f"::error::{len(refused) + 1} of the {uses} uses: in .github/workflows/ are not pinned." in proc.stdout
    assert "gh api repos/<owner>/<repo>/commits/<tag> --jq .sha" in proc.stdout


@needs_shell
def test_the_pin_check_fails_when_it_finds_nothing_to_check(tmp_path):
    (tmp_path / "repo" / ".github" / "workflows").mkdir(parents=True)
    proc = run_pin_check(tmp_path, tmp_path / "repo")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "::error::No uses: found in .github/workflows/, so nothing was checked." in proc.stdout


def dependabot_actions() -> dict:
    config = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    assert config["version"] == 2
    entries = [u for u in config["updates"] if u["package-ecosystem"] == "github-actions"]
    assert len(entries) == 1
    return entries[0]


def test_dependabot_proposes_every_pinned_action_monthly_in_one_group():
    entry = dependabot_actions()
    assert entry["directory"] == "/"
    assert entry["schedule"]["interval"] == "monthly"
    groups = entry["groups"]
    assert len(groups) == 1
    group = next(iter(groups.values()))
    used = {match["action"] for _, _, match in pins() if match}
    assert {"actions/upload-artifact", "actions/download-artifact"} <= used
    # A new action goes on the list, so its updates join the group.
    assert sorted(group["patterns"]) == sorted(used)
    assert sorted(group["update-types"]) == ["minor", "patch"]
    # One file: GitHub reads dependabot.yml or dependabot.yaml, not both.
    assert not (REPO_ROOT / ".github" / "dependabot.yml").exists()


def test_dependabot_never_proposes_a_checkout_major():
    ignored = [i for i in dependabot_actions()["ignore"] if i["dependency-name"] == "actions/checkout"]
    # Only the major is ignored: checkout still gets its v5 minor and patch updates.
    assert ignored == [{"dependency-name": "actions/checkout", "update-types": ["version-update:semver-major"]}]


def test_the_docs_link_guard_step_also_checks_the_required_checks_list():
    # The step keeps its name (a required check is a job name), and its
    # comment names what test:docs-links-tool runs besides the link guard.
    text = QUALITY.read_text(encoding="utf-8")
    comment = text[: text.index("      - name: Test the docs link guard\n")].rsplit("\n\n", 1)[1]
    script = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]["test:docs-links-tool"]
    for part in ("test/test-check-required-checks.js", "tools/check-required-checks.js --releasing"):
        assert part in script
        assert part in " ".join(line.strip().lstrip("# ") for line in comment.splitlines())
    validate = yaml.safe_load(text)["jobs"]["validate"]["steps"]
    assert [s["run"] for s in validate if s.get("name") == "Test the docs link guard"] == [
        "npm run test:docs-links-tool"
    ]
