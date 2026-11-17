"""Prose-contract tests: every `gh` call of the shared health check names the health-check repository (#1202).

The step searches, files, reacts and comments on `{healthCheckRepo}`. A `gh` call that names no repository acts on
the repository of the folder the workflow ran in, usually the user's own project: [R] ran
`gh api -X POST /repos/{repo}/issues/{N}/reactions`, whose `{repo}` gh fills from that folder (a name with no
owner, so a 404, or no repository at all), and [C] then ran `gh issue comment {N}` on issue N of that project.
Both then recorded `reacted` or `commented` in the seen-cache either way, so the health-check issue never got the
signal and later sightings of the defect on that machine were suppressed while it stayed open. Now the outcome is
recorded only when every call posted, and a failed reaction or comment goes to the local queue. No test runs the
step prose, so these checks pin it: every `gh` command it holds, fenced or inline, and the rule that records only
what posted.

Each issue and comment body also went on the command line, inside double quotes (#1203). A body quotes paths,
evidence and its `Section fingerprint:` line in backticks, so the shell ran each backticked span as a command and
put its output in its place: text from a finding ran on the user's machine, the line the dedup Action reads could
come out empty, and a double quote in the body broke the command, whose failed create then had no fallback and
lost the finding. Now each body is written with the Write tool to a file of its own in the local queue folder's
`bodies/` subfolder and passed with `--body-file`, and a create that fails goes to the local queue with that body.

A reporter without push access can neither create the `fp-*` label nor set one, so `gh issue create --label` fails
for them (armelhbobdad/bmad-module-ultracode-goal#226). The label create runs on its own, its failure no error, and
a create that fails is run once more without `--label`: the dedup Action labels that issue from its title.

The gate and routing follow UltraCode Goal's (#226, the second pull request): an empty `health_check_repo` turns the
check off; each finding is drafted in §3 and the gate shows the drafts, names the repository and says "public" for
the default one, with **[Y]** for the bug findings and **[A]** for all of them; a headless run with
`health_check_autosubmit` on submits its bug findings; a `gh` call the session refuses stops every later one; a
finding about the health check itself is only ever queued; and the helper's `queue` writes each local finding with
the commands that submit it. Every `gh` call stands alone, with `--repo` right after its subcommand, so an allow
rule, scoped to the repository or not, matches it.

The round-1 quality gate of that change (#226) moved the rest of the deterministic work to the helper: `settings`
reads the two config keys, `check-draft` refuses a draft that names the user's folders before anything is posted,
and the step, held to its token budget, keeps only what the model judges or acts on. A call refused before the gate
skips it and goes to the local queue.

`health_check_repo` may name a host (`HOST/OWNER/REPO`), which `--repo` takes but `gh api` does not (#1237): [R]
posted its reaction to `repos/HOST/OWNER/REPO/...` on github.com and failed, so [C] posted no comment, and the local
queue linked `https://github.com/HOST/OWNER/REPO/issues/new/choose`. `settings` now prints the `host` and the
`owner_repo`, which the step names `{healthCheckHost}` and `{healthCheckOwnerRepo}` (a bare `{host}` is the source's
in Create Skill's and Quick Skill's steps, earlier in the same session), the reaction takes `repos/` with the second,
and the link is built from both. The reaction and the gh check take `{healthCheckHostFlag}`, settings' `host_flag`:
`--hostname HOST` for a value that names a host and nothing for OWNER/REPO, so they reach the host each `--repo` call
reaches; pinning github.com for OWNER/REPO split one run across two hosts under GH_HOST or a login to an Enterprise
host alone. A block of the local queue that lists only drafts, as
for a value that is no repository, printed no commands, so it ends with its reason alone.

The review of that fix found that `gh search issues` does not take a host either: its `--repo` is an OWNER/REPO filter
on gh's default host, so `gh search issues --repo ghe.example.com/acme/skills ...` exits 1 with "Invalid search query"
and a GitHub Enterprise Server run never reached the reaction. The dedup searches are now `gh issue list --repo
{healthCheckRepo} --search ...`, which takes the host as every other `--repo` does, a search that exits non-zero
queues the finding, and for a value that names a host the gh check names it too, so a stale login on another host
does not stop it and a host never logged in to does (with no host named it checks every host, as in 11.1.0).
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"

REPO_ROOT = REPO
ISSUE_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md"
WORKFLOWS_DOC = REPO / "docs" / "workflows.md"

SUB_STEP_5A_I = "**5a-i. If a matching open issue exists:**"
SUB_STEP_5A_II = "**5a-ii. If no matching open issue exists**"
CREATE = "**Then create the issue:**"
WRITE_DRAFT = "**Write the draft.**"
WRITING_RULES = "**Writing rules"
CLOSING = "**Closing line.**"

# Where each issue body is drafted before the gate (§3), and each comment body before the call that posts it: a file
# of its own for each, apart from the findings the queue folder holds.
# A later section names the draft §3 wrote by its path, never by a `{timestamp}` it would have to recompute.
BODY_FILE = '--body-file "{draft_path}"'
COMMENT_FILE = '--body-file "{localFallbackFolder}/bodies/{fp}-comment-{timestamp}.md"'

# The calls the step must hold, each as the start of one call found, so an extractor that misses fenced lines,
# continuation lines or inline code spans fails here instead of passing on too few calls.
REQUIRED_CALLS = {
    "the gh check": "gh auth status {healthCheckHostFlag}",
    "the search by fingerprint": 'gh issue list --repo {healthCheckRepo} --state open --search "{fp} in:title" ',
    "the search by section fingerprint":
        'gh issue list --repo {healthCheckRepo} --state open --search "{legacy_fp} in:title,body" ',
    "the reaction":
        "gh api {healthCheckHostFlag} -X POST repos/{healthCheckOwnerRepo}/issues/{N}/reactions -f content='+1'",
    "the comment": "gh issue comment --repo {healthCheckRepo} {N} ",
    "the label": 'gh label create --repo {healthCheckRepo} "{fp}" ',
    "the new issue": 'gh issue create --repo {healthCheckRepo} --title "{title}" ',
}

# `gh` commands the step names without running them on an issue of its own: the helper's `gh issue view` (it
# asks by the recorded issue URL), the availability check, and the commands the label and create rules talk about.
MENTIONS = {"gh issue view", "gh auth status", "gh label create", "gh issue create"}

PLACEHOLDER = re.compile(r"\{[^{}]+\}")
# A code span may wrap onto the next line; the extractor never lets one cross a blank line.
CODE_SPAN = re.compile(r"`([^`]+)`")
# `gh ` at the start of a command or after a space, `;`, `&`, `|` or `(`: an indented, chained, piped or
# env-prefixed call counts, and a word that ends in "gh" ("through") does not.
GH_START = re.compile(r"(?<![^\s;&|(])gh ")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _flow(text: str) -> str:
    """The text with each run of whitespace folded to one space."""
    return re.sub(r"\s+", " ", text)


def _gh_commands(command: str) -> list[str]:
    """Each `gh ` call in one command, from its `gh ` up to the next one, whitespace folded."""
    starts = [match.start() for match in GH_START.finditer(command)]
    return [_flow(command[a:b]).strip() for a, b in zip(starts, starts[1:] + [len(command)])]


def _gh_calls(text: str) -> list[str]:
    """Every `gh ` call of the step, whitespace folded: in each fenced line, joined with the lines its trailing
    backslashes continue onto, and in each inline code span outside the fences."""
    calls: list[str] = []
    prose: list[str] = []

    def spans() -> None:
        for paragraph in re.split(r"\n[ \t]*\n", "\n".join(prose)):
            for span in CODE_SPAN.findall(paragraph):
                calls.extend(_gh_commands(span))
        prose.clear()

    lines = text.splitlines()
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            if not in_fence:
                spans()
            in_fence = not in_fence
        elif in_fence:
            parts = [line]
            while parts[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                parts[-1] = parts[-1].rstrip()[:-1]
                i += 1
                parts.append(lines[i])
            calls.extend(_gh_commands(" ".join(parts)))
        else:
            prose.append(line)
        i += 1
    assert not in_fence, "a code fence is never closed"
    spans()
    return calls


def test_the_extractor_finds_indented_chained_prefixed_and_wrapped_calls():
    """So a call the step adds in another shape is still checked, not skipped."""
    text = ("- Item:\n\n  ```\n  gh issue comment {N} \\\n    --body-file b\n  ```\n\n"
            "```\nGH_REPO=x gh api a && gh issue create --title t\ncat f | gh label create l\n```\n\n"
            "Run `cd x && gh issue\nview {N}`, then go through the `ghost` list.\n")
    assert _gh_calls(text) == ["gh issue comment {N} --body-file b", "gh api a &&", "gh issue create --title t",
                               "gh label create l", "gh issue view {N}"]


def test_every_gh_call_with_a_placeholder_names_the_health_check_repository():
    """A call that names no repository reacts, comments or files on the folder's own repository."""
    calls = _gh_calls(_read(SHARED_HEALTH_CHECK))
    for name, start in REQUIRED_CALLS.items():
        assert any(call.startswith(start) for call in calls), f"{name} not found: {start!r} in {calls}"
    for call in calls:
        for wrong in ("{repo}", "{owner}", "/repos/"):
            assert wrong not in call, f"{wrong} in {call!r}"
        if PLACEHOLDER.search(call):
            # `gh api` and `gh auth status` take no --repo: the host goes to --hostname, and an API path names
            # OWNER/REPO alone (#1237).
            if call.startswith("gh api "):
                assert call.startswith("gh api {healthCheckHostFlag} "), call
                assert " repos/{healthCheckOwnerRepo}/" in call, call
            elif call.startswith("gh auth status"):
                assert call == "gh auth status {healthCheckHostFlag}", call
            else:
                assert "--repo {healthCheckRepo}" in call, call
            assert "repos/{healthCheckRepo}" not in call, call
        # `gh search`'s --repo is an OWNER/REPO filter on gh's default host: it cannot search another host (#1237).
        assert not call.startswith("gh search "), call
    # A --hostname of the step's own would pin github.com for OWNER/REPO while --repo follows gh's default host.
    assert "--hostname {" not in _read(SHARED_HEALTH_CHECK)
    # A call with no placeholder can only be one the step mentions, never one it runs on an issue.
    plain = {call for call in calls if not PLACEHOLDER.search(call)}
    assert plain <= MENTIONS, plain - MENTIONS
    # The local queue's hint that posted the queue file's frontmatter is gone: the helper's `queue` prints commands.
    assert '--title \\"[title]\\"' not in _read(SHARED_HEALTH_CHECK)


def test_every_gh_call_stands_alone():
    """An allow rule matches a command, not a chain: a call with shell glue is one a headless run cannot be allowed."""
    for call in _gh_calls(_read(SHARED_HEALTH_CHECK)):
        for glue in ("||", "&&", "|", ";", "2>"):
            assert glue not in call, (glue, call)


def test_every_gh_call_names_the_repository_right_after_its_subcommand():
    """So a rule scoped to the repository, `Bash(gh issue create --repo OWNER/REPO *)`, matches the call."""
    for call in _gh_calls(_read(SHARED_HEALTH_CHECK)):
        words = call.split()
        if "--repo" in words:
            assert words.index("--repo") == 3, call


def test_r_and_c_react_and_comment_on_the_health_check_issue():
    actions = _slice(_read(SHARED_HEALTH_CHECK), "Execute the chosen action:", SUB_STEP_5A_II)
    # No leading slash, as the repository's other `gh api` calls write the path; a named host goes to --hostname
    # through `{healthCheckHostFlag}` (#1237).
    assert ("- **R:** `gh api {healthCheckHostFlag} -X POST repos/{healthCheckOwnerRepo}/issues/{N}/reactions "
            "-f content='+1'`\n") in actions
    # The comment's body goes in a file, written and shown to the user before either call, so a Write that fails
    # posts nothing and what is posted is what was shown.
    assert ("- **C:** Write the delta body, the Environment table plus one sentence on what differs from the "
            "original, with no session narrative, with the Write tool to "
            "`{localFallbackFolder}/bodies/{fp}-comment-{timestamp}.md`, check that file as §3 checks a draft, and "
            "show the user its text. Then run the same reaction call, then "
            f"`gh issue comment --repo {{healthCheckRepo}} {{N}} {COMMENT_FILE}`. If the Write fails, make no call for "
            "this finding: log the error and write the finding to the local queue (§5c) with the failed-submission "
            "reason; a comment the check refused twice or could not check posts nothing either, and the finding goes "
            "there with the unchecked-draft reason.") in _flow(actions)
    # Every issue call names the repository (test_every_gh_call_with_a_placeholder_names_the_health_check_repository).
    assert "If the **R** or **C** call exits non-zero" in _flow(actions)


def test_only_a_reaction_or_comment_that_posted_is_recorded():
    text = _read(SHARED_HEALTH_CHECK)
    choice = _flow(_slice(text, SUB_STEP_5A_I, SUB_STEP_5A_II))
    rule = ("If the **R** or **C** call exits non-zero, log its stderr message and make no further call for this "
            "finding: **C** posts no comment after a failed reaction, and a reaction it already added stays. Record "
            "nothing (run neither record call below) and write the finding to the local queue (§5c) with the "
            "failed-submission reason.")
    assert rule in choice
    success = ("When every call of **R** or **C** succeeded, record the outcome under `{fp}`, also when the match was "
               "found by `{legacy_fp}`: `reacted` after **R** and `commented` after **C**")
    assert success in choice
    assert "After **R** or **C**, record the outcome" not in choice
    # The rule holds back both record calls, so after a `regression` verdict the `resolved` record stays too.
    record = ('uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" '
              '--date "{today}"')
    plain = choice.index(f"{record} ```")
    regression = choice.index(f"{record} --regression ```")
    instead = choice.index("When sub-step 1 returned `regression`, run this one instead")
    assert choice.index(rule) < choice.index(success) < plain < instead < regression
    # The queue takes the finding, with a reason of its own.
    queue = _flow(text[text.index("### 5c."):])
    assert "or a search, reaction, comment or new issue that failed (§5a)." in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "When `{result_envelope_line}` is bound"))
    assert '"Posting these to GitHub failed." (the failed-submission reason).' in reasons
    assert ('"SKF\'s health-check helper could not fingerprint these findings, so they carry the fingerprint N/A; '
            'compute it with its fingerprint call before submitting." (the could-not-fingerprint reason)') in reasons
    # A reason its route quotes is not listed again.
    assert "the one its route quotes, or the one named here:" in reasons
    assert '"The review gate queued these locally."' not in reasons
    assert 'the reason "The review gate queued these locally."' in _flow(_slice(text, "- **IF Q:**", "### 5."))


def test_no_body_goes_on_the_command_line():
    """Inside double quotes the shell runs each backticked span of a body, so every body goes to `gh` as a file."""
    text = _read(SHARED_HEALTH_CHECK)
    # Not in a call and not in the prose either, so no copied example puts a body back on the command line.
    inline = re.search(r"--body(?!-file)", text)
    assert inline is None, text[max(0, inline.start() - 80):inline.end() + 80]
    short = re.search(r"(?<![\w-])-b(?![\w-])", text)
    assert short is None, text[max(0, short.start() - 80):short.end() + 80]
    # The comment and the new issue each post their body file, as the call's last argument.
    calls = _gh_calls(text)
    for name, body_file in (("the comment", COMMENT_FILE), ("the new issue", BODY_FILE)):
        found = [call for call in calls if call.startswith(REQUIRED_CALLS[name])]
        assert found and all(call.endswith(body_file) for call in found), (name, found)


def test_each_body_is_written_to_a_file_with_the_write_tool():
    text = _read(SHARED_HEALTH_CHECK)
    raw = _slice(text, CREATE, "When sub-step 1 returned `regression`, put")
    # The command keeps its other lines; the title is the one the helper printed.
    assert ('  --title "{title}" \\\n'
            '  --label "health-check,workflow-improvement,{severity},{fp}" \\\n'
            f"  {BODY_FILE}\n```\n") in raw
    # §3 writes every draft before the gate, so the gate shows what `gh` posts and the queue copies.
    draft = _flow(_slice(text, WRITE_DRAFT, WRITING_RULES))
    for needle in (
        "**Write the draft.** Write each finding's issue body (the format below) with the Write tool to a file of its "
        "own, `{localFallbackFolder}/bodies/{fp}-{timestamp}.md`, opening with the call's `body_header` exactly as "
        "printed: `{draft_path}` is its path from here on.",
        "Every route uses that file as it stands, and after the gate it changes only by a regression's "
        "`## Regression` section (§5a sub-step 1) or an **\\[N]** re-key at the dedup gate (§5a-i).",
        "Never put a body on the command line or write it through the shell (`echo`, `printf` or a heredoc): the "
        "shell would run each backticked span or `$(...)` in it, and a double quote in it would end the argument.",
        # With no draft written, there is nothing to show, post or queue.
        "If the Write fails, log the error, naming the finding, and drop the finding: there is no text to show, post "
        "or queue.",
    ):
        assert needle in draft, needle
    # Inside double quotes a backslash still escapes what follows it, the closing quote included: the helper refuses
    # a description that would break the title.
    describe = _flow(_slice(text, "**Give it a short description**", "```\nuv run {seenCacheHelper} fingerprint"))
    assert ("**Give it a short description**, one line naming the defect for its issue title, with no backtick, `$`, "
            "double quote, backslash or `!`: the title goes on the command line.") in describe


def test_a_create_that_failed_goes_to_the_local_queue_with_its_body():
    text = _read(SHARED_HEALTH_CHECK)
    create = _flow(_slice(text, CREATE, CLOSING))
    recorded = "After the issue is created, record it under `{fp}` as §5b says."
    retry = ("If `gh issue create` exits non-zero, run it once more without its `--label` line, with the same title "
             "(`{regression_title}` after a `regression` verdict) and the same body file: a reporter without push "
             "access to `{healthCheckRepo}` can set no label, and the dedup Action labels the issue from its title.")
    failed = ("If the retry exits non-zero too, log its stderr message, record nothing, and write the finding to the "
              "local queue (§5c) with the failed-submission reason.")
    assert recorded in create and retry in create and failed in create
    assert create.index(recorded) < create.index(retry) < create.index(failed)
    # §5b records a create that succeeded on either run.
    assert ("After each successful `gh issue create`, on its first run or its retry without `--label` (§5a-ii), record "
            "the new issue under `{fp}`") in _flow(_slice(text, "### 5b.", "### 5c."))
    # The issues-created display counts only the issues that posted.
    display = _flow(_slice(text, CREATE, "### 5b."))
    assert ("After creating all issues, display those that were created, `{N}` counting only them, unless none was "
            "(a create that failed is listed by §5c): \"**{N} issue(s) created on {healthCheckRepo}:**") in display
    # The queue file of a failed create holds the draft that failed to post, with no frontmatter.
    queue = _flow(text[text.index("### 5c."):])
    assert ("It copies the draft, unchanged and with no frontmatter, to "
            "`{localFallbackFolder}/hc-{workflow}-{YYYYMMDD-HHmmss}.md` (UTC)") in queue
    assert "```yaml" not in text and "type: workflow-health-finding" not in text


def test_the_label_create_runs_on_its_own_and_its_failure_is_no_error():
    """A reporter without push access cannot create the `fp-*` label: the create goes on, retried without labels."""
    text = _read(SHARED_HEALTH_CHECK)
    label = _slice(text, "**First, create the `{fp}` label**", CREATE)
    # The prose names `gh issue create`, which fails on a label that does not exist; the call is the label's alone.
    calls = [call for call in _gh_calls(label) if PLACEHOLDER.search(call)]
    assert calls == ['gh label create --repo {healthCheckRepo} "{fp}" --color "ededed" '
                     '--description "Health-check fingerprint dedup key"'], calls
    # No shell glue: a call the session allows on its own needs no `|| true` or redirect after it.
    assert "|| true" not in text and "2>/dev/null" not in text
    assert ("If it exits non-zero, that is no error: the label exists already, or you have no push access to "
            "`{healthCheckRepo}` and cannot create one. Go on to the create.") in _flow(label)
    # The title keeps the prefix the dedup Action labels a report without labels from.
    create = _flow(_slice(text, CREATE, CLOSING))
    assert ("Keep the title's `[health-check][{severity}][{fp}] {workflow}: ` prefix exactly as the helper printed it: "
            "the dedup Action reads the severity and the fingerprint from it to label an issue filed without "
            "labels.") in create
    # The local queue's third command files without labels, so it needs no push access.
    hint = _flow(_slice(text, "{reason} Run a finding's first two commands", "`{reason}` is the sentence"))
    assert ("Without push access to {healthCheckRepo}, run its third command alone instead: you can neither create a "
            "label nor set one, and the dedup Action labels the issue from its title.") in hint


def test_a_run_that_posts_and_queues_says_workflow_complete_once_and_last():
    """A failed post (#1202, #1203) now reaches the local queue in a run whose other findings posted. The
    issues-created block ended "Workflow complete." and §5c then wrote the failed finding and said it again: an
    agent that stops at the first completion line, as #1115 found agents do, loses the finding the queue was to
    keep. The created block now ends without it, and one closing rule says where the line comes."""
    text = _read(SHARED_HEALTH_CHECK)
    display = _slice(text, "After creating all issues, display", "### 5b.")
    assert display.count('"Workflow complete."') == 2 and "\nWorkflow complete.\"" not in display
    assert '{list each issue URL}"\n\n**Closing line.**' in display
    closing = _flow(display[display.index("**Closing line.**"):]).strip()
    assert closing == (
        '**Closing line.** The step displays "Workflow complete." once, after everything else it displays but a bound '
        "`{result_envelope_line}` (§0). When any finding of this run goes to the local queue (§5c), display nothing "
        'more here: §5c ends its block with that line. Otherwise display "Workflow complete." now, after the block '
        "above, or alone when no issue was created. When `{result_envelope_line}` is bound (§0), display it verbatim "
        "after that line, as the last line.")
    # §5c's blocks, displayed after its files are written, end with the line, and only the result line comes after.
    queue = text[text.index("After writing the files,"):]
    assert queue.rstrip().endswith('"Workflow complete."\n\nWhen `{result_envelope_line}` is bound (§0), display it '
                                   "verbatim after that block, as the last line.")
    assert 'then "Workflow complete." after the last block:' in _flow(queue)


# ---------------------------------------------------------------- the gate and routing (UltraCode Goal's #226)

DEFAULT_REPO = "armelhbobdad/bmad-module-skill-forge"


def helper():
    import importlib.util
    spec = importlib.util.spec_from_file_location("skf_hc_seen_gh_calls",
                                                  REPO / "src" / "shared" / "scripts" / "skf-health-check-seen.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section(text: str, heading: str) -> str:
    """From a `### ` heading to the next `### ` one, or to the end."""
    i = text.index(heading)
    j = text.find("\n### ", i + len(heading))
    return text[i:] if j == -1 else text[i:j]


def test_an_empty_repository_turns_the_check_off_before_anything_else():
    text = _read(SHARED_HEALTH_CHECK)
    arrival = _section(text, "### 0. Announce Arrival")
    # Before the announcement, and so before the reflection.
    assert arrival.index("**Off switch.**") < arrival.index("**Display in `{communication_language}`:**")
    flow = _flow(arrival[arrival.index("**Off switch.**"):])
    # The model reads the one key itself: a switched-off run makes no helper call (round 1, determinism-1).
    assert ("**Off switch.** Before anything else, read `health_check_repo` in `{project-root}/_bmad/skf/config.yaml` "
            "yourself: a workflow binds only its own config keys. When the key is there and empty (`''`, `\"\"`, "
            "nothing or only a comment after its colon, or a YAML null such as `~` or `null`), the health check is "
            "off") in flow
    # One off line and the completion line, then the envelope line last, and nothing reflected on.
    assert ('"**Health Check: off.** `health_check_repo` is empty in `_bmad/skf/config.yaml`, so nothing was reviewed '
            'or sent. Workflow complete."') in flow
    assert ("then, when `{result_envelope_line}` is bound, that line verbatim, as the last line, and STOP: announce "
            "nothing and reflect on nothing.") in flow
    # Absent (every BMAD Method install) or no file: the default, until the helper reads the file.
    assert (f"Otherwise `{{healthCheckRepo}}` is that value, or `{DEFAULT_REPO}` when the key or the file is absent, "
            "until §3's `settings` call checks it.") in flow
    assert "wherever this step stops (the off switch below, the clean-run stop in §2," in _flow(arrival)
    assert f'default: "{DEFAULT_REPO}"' in _read(REPO / "src" / "module.yaml")
    # The helper's settings call decides the rest, and an off state it finds stops the check as §0's does.
    settings = _flow(_slice(text, "**Read the settings.**", "**A refused call.**"))
    assert 'uv run {seenCacheHelper} settings --config "{project-root}/_bmad/skf/config.yaml"' in settings
    assert ("and `{healthCheckAutosubmit}` its `autosubmit`, which is off without a helper. On `off`, display §0's two "
            "off lines, then the bound `{result_envelope_line}`, and STOP, drafting nothing.") in settings
    assert helper().DEFAULT_REPO == DEFAULT_REPO


def test_a_clean_or_switched_off_run_makes_no_helper_call():
    """Zero overhead: the settings call runs once §3 resolves the helper, never before a finding exists."""
    text = _read(SHARED_HEALTH_CHECK)
    before = text[:text.index("### 3. Draft Each Finding")]
    assert "{seenCacheHelper}" not in before
    # A run with findings skips the clean-run close that sits between them.
    reflect = _flow(_section(text, "### 1. Reflect on the Run"))
    assert "If there is none, close the clean run (§2); otherwise go on to §3." in reflect
    draft = text[text.index("### 3. Draft Each Finding"):]
    assert draft.index("**Resolve the helper.**") < draft.index("uv run {seenCacheHelper} settings") < draft.index(
        "uv run {seenCacheHelper} fingerprint")


def test_a_later_check_in_one_session_reviews_only_what_came_after_the_last():
    """Round 2: in a forger pipeline or back-to-back workflows, each workflow's check would draft again what an
    earlier check in the same session already showed, queued or filed. A check that was off reviewed nothing, so it
    sets no start, and a check run on request (Ferris's health-check bullet) reviews the whole workflow it is run
    for, whose own check may already have run."""
    text = _read(SHARED_HEALTH_CHECK)
    reflect = _flow(_section(text, "### 1. Reflect on the Run"))
    assert ("Silently review this session, from the end of the last health check in it that was not off (its start "
            "when none did; for a check run on request, the start of the workflow it is run for), for each point "
            "where") in reflect
    # The leave-out rule governs the whole step, the own-stage finding of §3 included.
    rules = _flow(_slice(text, "### Findings Rule:", "## MANDATORY SEQUENCE"))
    assert "Report only a bug, friction or gap you hit in this session since its last health check" in rules
    assert "Leave out too any finding an earlier check in this session already showed, queued or filed." in rules
    assert "Leave out any finding an earlier check" not in reflect
    goal = _flow(_slice(text, "## STEP GOAL:", "**Zero overhead for clean runs.**"))
    assert "Reflect on this session since the last health check that ran in it" in goal
    assert "the workflow that just completed" not in goal


def test_the_issue_text_is_english_and_the_displays_are_the_users_language():
    """Round 2: a non-English session filed issues the maintainers read in that language."""
    rules = _flow(_slice(_read(SHARED_HEALTH_CHECK), WRITING_RULES, "**Issue body format:**"))
    # What the user approves is what is posted: a draft, a title or a comment is never shown translated.
    assert ("- **Write it in English.** The short description, the issue body and a **C** comment are in English "
            "whatever `{communication_language}`; the gate and every other display stay in `{communication_language}`, "
            "and a title, a draft or a comment is shown exactly as written.") in rules
    docs = _flow(_slice(_read(WORKFLOWS_DOC), "### What gets sent", "### The review gate"))
    assert "It is written in English, whatever language Ferris speaks with you." in docs


def test_no_limit_is_shouted_and_the_version_cell_is_said_once():
    """Round 2 leanness: the last all-caps limit is gone, and the Environment table's version cell is not restated
    after the version call."""
    text = _read(SHARED_HEALTH_CHECK)
    assert not re.search(r"\bONE\b", text)
    assert "Write its `version` into the Environment table" not in text
    assert "| SKF Version | {the `version` the helper prints, below, else N/A} |" in text
    version = _flow(_slice(text, "**SKF Version comes from the helper**", "### 4."))
    assert "never from `{project-root}`" in version and "uv run {seenCacheHelper} version" in version
    assert "Run Mode is `headless` when `{headless_mode}` is true, else `interactive`." in _flow(text)


def test_the_step_stays_within_its_token_budget():
    """The step is read at the end of all 15 workflows (UltraCode Goal's quality gate, round 1, architecture-1): it
    stays one file of at most 9,000 tokens by SKF's chars/4 convention."""
    assert len(_read(SHARED_HEALTH_CHECK)) // 4 <= 9000


def test_a_value_that_is_no_repository_queues_every_finding_and_runs_no_gh_call():
    """A URL or a value with shell characters is never handed to `gh` or to the helper's `--repo`: the helper's
    `settings` checks it against REPO_RE, which test-skf-health-check-seen.py pins with every YAML form."""
    text = _read(SHARED_HEALTH_CHECK)
    settings = _flow(_slice(text, "**Read the settings.**", "**A refused call.**"))
    # The line names the value as `settings` printed it, so the user sees what to fix.
    assert ("On `invalid`, `{healthCheckRepo}` is no repository: display \"**Health Check:** `health_check_repo` is "
            "`{repo}` in `_bmad/skf/config.yaml`, which is not OWNER/REPO or HOST/OWNER/REPO, so no finding will be "
            "submitted.\", run no `gh` call, and send every finding to the local queue (§5c) with the no-repository "
            "reason.") in settings
    # The step no longer sorts the value by eye.
    assert "letters, digits and `-` in the owner" not in text
    module = helper()
    for good in (DEFAULT_REPO, "ghe.example.com/my-org/my.repo_x"):
        assert module.REPO_RE.fullmatch(good), good
    for bad in ("https://github.com/o/r", "o/r; rm -rf ~", "my org/r", "o/r/x/y", "o/$(id)"):
        assert not module.REPO_RE.fullmatch(bad), bad
    route = _flow(_section(text, "### 5. Route Each Finding by Severity"))
    assert "and one that §3 sent there keeps its reason: none of them is submitted." in route
    queue = _flow(text[text.index("### 5c."):])
    assert "and nor does any finding when `{healthCheckRepo}` is no repository (§3)" in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "When `{result_envelope_line}` is bound"))
    assert ('"health_check_repo in _bmad/skf/config.yaml is not a repository; fix it, then submit these." (the '
            'no-repository reason)') in reasons


def test_the_gate_shows_each_draft_and_names_the_repository_before_it_halts():
    gate = _section(_read(SHARED_HEALTH_CHECK), "### 4. User Review Gate")
    halt = gate.index("**HALT and wait for user input.**")
    shown = _flow(gate[:halt])
    assert ("**If interactive:** show every finding: for each one, its title (§3), the path of its draft and the "
            "draft's full text.") in shown
    # The helper says whether the repository is the default, in any letter case (test-skf-health-check-seen.py).
    assert ('Then ask, saying "public issues" for "issues" when §3\'s `settings` call printed `is_default` true, and '
            'for any other repository adding "(public if that repository is public)" after its name:') in shown
    assert '"**Submit these findings as issues on {healthCheckRepo}, filed with your GitHub account?**' in shown
    options = re.findall(r"^- \*\*\[(\w)\]\*\* (.+)$", gate[:halt], re.MULTILINE)
    assert options == [("Y", "Yes: submit the bug findings; friction and gap findings stay local"),
                       ("A", "All: submit every finding, friction and gap included"),
                       ("N", "No: discard all findings"),
                       ("E", "Edit: let me revise before submitting"),
                       ("Q", "Queue locally: save every finding to {localFallbackFolder}/, submit nothing")]
    assert "- **IF Y or A:** Proceed to step 5" in gate[halt:]
    route = _flow(_section(_read(SHARED_HEALTH_CHECK), "### 5. Route Each Finding by Severity"))
    assert "- **\\[A]**: every finding goes to the live-submit path (step 5a below)." in route


def test_no_yes_no_prompt_is_left():
    """[A] took the place of the second question about friction and gap findings."""
    for path in (ISSUE_TEMPLATE, WORKFLOWS_DOC, REPO / "README.md", REPO / "docs" / "getting-started.md",
                 *sorted((REPO / "src").rglob("*.md"))):
        text = _read(path)
        assert "[y/N]" not in text and "\\[y/N]" not in text, path


def test_a_headless_run_queues_or_submits_its_bug_findings_only():
    text = _read(SHARED_HEALTH_CHECK)
    gate = _section(text, "### 4. User Review Gate")
    (annotation,) = [block for block in gate.split("\n\n") if block.startswith("**GATE [default: Q]**")]
    flow = _flow(annotation)
    # The helper's `settings` reads autosubmit: on only for a plain `true` (test-skf-health-check-seen.py).
    assert ("**GATE [default: Q]**: if `{headless_mode}` is true, skip the question below and choose by "
            "`{healthCheckAutosubmit}` (§3)") in flow
    assert ('while it is off, choose **[Q]**, with the reason "Headless runs queue every finding while '
            'health_check_autosubmit is off."') in flow
    assert ('when it is on, choose **[Y]**, which submits the bug findings, still deduped, and queues the friction and '
            'gap findings with the reason "Headless runs never submit friction or gap findings."') in flow
    # A headless run chooses only listed options.
    assert re.findall(r"\bchoose \*\*\[(\w)\]\*\*", annotation) == ["Q", "Y"]
    route = _flow(_section(text, "### 5. Route Each Finding by Severity"))
    assert ("- **\\[Y]**, and a headless run that chose it: each finding whose severity is in "
            "`{liveSubmitSeverities}`, a `bug`, goes to the live-submit path (step 5a below)") in route
    assert '"Headless runs never submit friction or gap findings." in a headless one' in route
    frontmatter = text.split("\n---\n", 1)[0]
    assert "healthCheckAutosubmit: '{health_check_autosubmit}'" in frontmatter
    assert "liveSubmitSeverities: ['bug']" in frontmatter
    module = helper()
    assert module.config_values("health_check_autosubmit: true\n")["health_check_autosubmit"] == (module.PLAIN, "true")


def test_a_refused_gh_call_stops_every_later_one_and_queues_what_is_left():
    text = _read(SHARED_HEALTH_CHECK)
    rule = _flow(_slice(text, "**A refused `gh` call.**", "**3. Remote dedup search**"))
    for needle in (
        "When the session refuses `gh auth status` or any later `gh` call of §5a, so that the command never ran",
        "make no further `gh` call in this check: a refused call is no failure, so it gets no retry and no other "
        "call after it.",
        "Write this finding and every live-submit finding not yet submitted to the local queue (§5c), with the "
        "refused-gh reason.",
    ):
        assert needle in rule, needle
    # A `gh auth status` that ran and failed is no refusal: gh is unavailable.
    assert ("If it runs and fails (no `gh`, or not logged in), fall through to step 5c with the gh-unavailable "
            "reason.") in _flow(text)
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "When `{result_envelope_line}` is bound"))
    assert ('"You declined a gh call; nothing was posted." and "A gh call was refused in this session; allow the '
            'health check\'s gh commands, as health_check_autosubmit\'s docs say, to submit headless." (the refused-gh '
            'reason, interactive and headless)') in reasons
    # The headless reason points at the allow rules the docs give, each scoped or not: the four gh commands, the
    # helper and the writes to the queue folder. A headless run never reacts or comments, so it needs no rule for it.
    docs = _flow(_slice(_read(WORKFLOWS_DOC), "### Submitting from headless runs", "### Submitting a queued finding"))
    for allow in ('"Bash(gh auth status)"', '"Bash(gh issue list *)"', '"Bash(gh label create *)"',
                  '"Bash(gh issue create *)"', '"Bash(uv run *skf-health-check-seen.py *)"',
                  '"Edit(./forge-data/improvement-queue/**)"', f"Bash(gh issue create --repo {DEFAULT_REPO} *)"):
        assert allow in docs, allow
    for unneeded in ("Bash(gh api", "Bash(gh issue comment"):
        assert unneeded not in docs, unneeded
    # The search rule the 11.1.0 docs gave matches no call the step makes now (#1237), and the docs say to replace it.
    assert "Bash(gh search issues" not in docs
    assert ("Rules written for SKF 11.1.0 allow `gh search issues`, which the health check no longer runs: replace that "
            "rule with `Bash(gh issue list *)` or its scoped form.") in docs
    for sub in ("gh issue list", "gh label create", "gh issue create"):
        assert f"`Bash({sub} --repo {DEFAULT_REPO} *)`" in docs, sub
    # `gh auth status` takes no --repo, and gets a --hostname only for a value that names a host.
    assert ("For a `HOST/OWNER/REPO` value, write it in these rules, and allow "
            "`Bash(gh auth status --hostname HOST)` in place of the bare `gh auth status`, with HOST as "
            "`gh auth status` lists it: in lower case, `github.com` for any `*.github.com` name and `TENANT.ghe.com` "
            "for `api.TENANT.ghe.com`.") in docs
    setup = _flow(_slice(_read(WORKFLOWS_DOC), "### Turning it off", "### What gets sent"))
    assert ("set the key to `OWNER/REPO`, or to `HOST/OWNER/REPO` for one on a GitHub Enterprise Server host (log in to "
            "that host first, with `gh auth login --hostname HOST`)") in setup
    assert ("the health check puts `--repo` right after the subcommand of every `gh issue list`, "
            "`gh label create` and `gh issue create` it runs") in docs


def test_a_refused_helper_call_or_write_is_no_missing_helper():
    """A refusal never ran the call: it is neither the missing-helper case ("re-install SKF") nor a failed Write that
    drops the finding. One before the gate skips it (round 1, architecture-3): the gate would show drafts and offer
    submissions that do not exist."""
    text = _read(SHARED_HEALTH_CHECK)
    rule = _flow(_slice(text, "**A refused call.**", "**Name the step file, the section and the defect.**"))
    for needle in (
        "so a refused helper call (any `uv run` of `{seenCacheHelper}`) is no missing helper and a refused Write no "
        "failed one.",
        "After the session refuses a helper call or a Write of this step, make no further helper call, Write or `gh` "
        "call in this check, and send every finding not yet submitted to the local queue (§5c) with the refused "
        "reason.",
        "A refusal before the review gate skips §4 and §5: go straight to §5c.",
    ):
        assert needle in rule, needle
    queue = _flow(text[text.index("### 5c."):])
    assert "or a refused call, which skips §4 before the gate (§3)" in queue
    assert ("or after a refused call (§3): list its draft (§3) in the queue file's place, or display the text of a "
            "finding that has no draft on disk") in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "When `{result_envelope_line}` is bound"))
    assert ('"You declined one of the health check\'s calls; nothing more was posted." and "A call of the health check '
            'was refused in this session; allow its helper, its writes and its gh commands, as '
            'health_check_autosubmit\'s docs say, to submit headless." (the refused reason, interactive and '
            'headless)') in reasons


def test_a_finding_about_the_health_check_itself_is_only_ever_queued():
    text = _read(SHARED_HEALTH_CHECK)
    defect = _flow(_slice(text, "**A defect in this step.**", "**Resolve the helper.**"))
    assert ("its workflow is `health-check` and its step file `shared/health-check.md`. It is never posted (§4)."
            in defect)
    assert "Take at most one per check" in defect and "Display any further one only as a one-line note" in defect
    gate = _flow(_section(text, "### 4. User Review Gate"))
    assert ("Every route that submits or queues it (**\\[Y]**, **\\[A]**, **\\[Q]** and a headless run) writes it to "
            "the local queue (§5c) with the reason \"Found in the health check's own instructions; review it before "
            "submitting.\", which replaces any reason its route would give; **\\[N]** discards it with the rest."
            ) in gate
    # Nor is a gate offered that nothing can answer with a post: N/A findings, or no repository, ask to queue too.
    assert ("When no finding can be submitted, because each one is about the health check itself or §3 sent it to "
            "the local queue, ask instead \"**Queue these findings locally?**\" with **\\[Q]**, **\\[N]** and "
            "**\\[E]** only.") in gate
    # An edit that removes every finding leaves nothing to ask about.
    assert "When the edit leaves no finding, handle it as **IF N**." in gate
    route = _flow(_section(text, "### 5. Route Each Finding by Severity"))
    assert "Under either, a finding about the health check itself goes to the local queue with §4's reason" in route


def test_the_evidence_cites_only_skfs_own_files():
    rules = _flow(_slice(_read(SHARED_HEALTH_CHECK), WRITING_RULES, "**Issue body format:**"))
    # Every section, the title and a comment, not only the Evidence.
    assert ("**Name nothing of the user's.** The title, every section of the body and a **C** comment describe SKF's "
            "instruction, never the user's work: they name no project, library, skill, file or path of the user's and "
            "no secret, and Evidence quotes only SKF's own files (its step files, SKILL.md files, shared files and "
            "scripts)") in rules
    body = _slice(_read(SHARED_HEALTH_CHECK), "**Issue body format:**", "### 4.")
    assert "`skills/" not in body, "an example that names a user's folder"
    template = _flow(_slice(_read(ISSUE_TEMPLATE), "## Evidence", "## Impact"))
    assert "citations of SKF's own files" in template and "Never your project's code" in template
    # The docs promise what the rule says, no more.
    docs = _flow(_slice(_read(WORKFLOWS_DOC), "### What gets sent", "### The review gate"))
    assert ("its title, every section of its body and any comment Ferris posts on a matching issue describe SKF's "
            "instructions, and name no project, library, skill, file or path of yours and no secret, and the Evidence "
            "quotes only SKF's own files") in docs
    assert "Nothing else is sent" not in docs
    assert "`skf-health-check-seen.py check-draft`" in docs


def test_a_draft_that_names_the_users_folders_is_never_posted():
    """Round 1, enhancement-1: the post that cannot be undone, with autosubmit nobody reads first, is checked by the
    helper after each draft Write (test-skf-health-check-seen.py pins the check), its title included, and so is a
    comment's body and a re-keyed draft."""
    text = _read(SHARED_HEALTH_CHECK)
    draft = _slice(text, WRITE_DRAFT, WRITING_RULES)
    call = ('uv run {seenCacheHelper} check-draft --body-file "{draft_path}" --title "{title}" --project-dir '
            '"{project-root}"\n')
    assert call in draft
    assert draft.index("**Write the draft.**") < draft.index(call)
    flow = _flow(draft)
    # Every draft when a helper exists, `N/A` included: the queue lists an N/A draft for the user to submit.
    assert ("With a helper, then check every draft, `N/A` included, and its title for the user's folders, which a "
            "public issue must never name:") in flow
    # Only a message that names lines is rewritten: a bad argument exits 2 too, and that draft is unchecked.
    assert ("When it exits 2 with a message that names lines or the title holding the project's folder or the home "
            "folder, rewrite them, citing SKF's files by their module path "
            "(`src/skf-test-skill/references/report.md:12`), and run the call once more. A draft refused twice, or one "
            "the call could not check (any other exit 2, a failure or no JSON), goes to the local queue (§5c) with the "
            "unchecked-draft reason and is never posted.") in flow
    # An edit at the gate, a comment's body and a re-keyed draft are checked too.
    assert "check each changed draft as §3 does" in _flow(_section(text, "### 4. User Review Gate"))
    choice = _flow(_slice(text, SUB_STEP_5A_I, SUB_STEP_5A_II))
    assert "check that file as §3 checks a draft" in choice
    assert "write and check the draft anew under the new `{fp}`, as §3 does" in choice
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "When `{result_envelope_line}` is bound"))
    assert ('"These drafts may name a folder of yours; check them before submitting." (the unchecked-draft '
            'reason)') in reasons
    assert "an unchecked draft" in _flow(text[text.index("### 5c."):])
    # [Q], at the gate or headless, keeps the reason §3 gave a finding it already sent to the queue.
    assert ("or the GATE's own reason in a headless run; one that §3 sent there keeps its reason, as §5 says. STOP "
            "after §5c") in _flow(_slice(text, "- **IF Q:**", "### 5."))


def test_the_local_queue_is_written_by_the_helper_with_the_commands_that_submit_it():
    text = _read(SHARED_HEALTH_CHECK)
    queue = text[text.index("### 5c."):]
    assert ('uv run {seenCacheHelper} queue --queue-dir "{localFallbackFolder}" --body-file "{draft_path}" '
            '--title "{title}" --repo "{healthCheckRepo}"\n') in queue
    assert "**Filename:**" not in text and "**File content:**" not in text
    # A finding queued at a match names the issue it matched, so whoever submits it can react there instead.
    assert ("{each path written, each followed by its three `commands`, exactly as printed, and, for a finding queued "
            "at a match (§5a-i), the URL of each issue it matched}") in queue


def test_the_queue_links_the_issue_form_on_the_repositorys_host_and_a_block_of_drafts_names_no_command():
    """#1237: the queue's link pasted `{healthCheckRepo}` after github.com, a 404 for a HOST/OWNER/REPO value and
    meaningless for one that is no repository, and a block that listed drafts, printing no command, still said to run
    a finding's first two commands."""
    text = _read(SHARED_HEALTH_CHECK)
    settings = _flow(_slice(text, "**Read the settings.**", "**A refused call.**"))
    assert ('It prints `{"repo_state", "repo", "host", "owner_repo", "host_flag", "is_default", "autosubmit"}`. From '
            "here on `{healthCheckRepo}` is its `repo`, `{healthCheckHost}` its `host`, `{healthCheckOwnerRepo}` its "
            "`owner_repo`, `{healthCheckHostFlag}` its `host_flag` (empty for OWNER/REPO) and `{healthCheckAutosubmit}` "
            "its `autosubmit`, which is off without a helper.") in settings
    # Named apart from another step's `{host}` or `{owner}`, and only ever as the helper printed them.
    for bare in ("{host}", "{owner_repo}", "{owner}"):
        assert bare not in text, bare
    # No github.com path is built from the setting anywhere in the step.
    assert "github.com/{" not in text
    hint = _flow(_slice(text, "{reason} Run a finding's first two commands", "`{reason}` is the sentence"))
    assert "or open one at <https://{healthCheckHost}/{healthCheckOwnerRepo}/issues/new/choose>." in hint
    # A value that is no repository, a missing helper, no fingerprint or a refused call lists drafts only.
    queue = _flow(text[text.index("### 5c."):])
    assert ('followed, in place of commands, by "Submit it as '
            '<https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/#submitting-a-queued-finding> says." '
            "A block that lists no queue file ends with `{reason}` alone.") in queue
    # The helper's split, pinned with every form in test-skf-health-check-seen.py.
    module = helper()
    assert module.split_repo("GHE.example.com/acme/skills") == ("ghe.example.com", "acme/skills")
    assert module.split_repo(DEFAULT_REPO) == ("github.com", DEFAULT_REPO)


def test_every_stop_of_the_step_ends_on_the_envelope_line():
    text = _read(SHARED_HEALTH_CHECK)
    draft = _flow(_slice(text, WRITE_DRAFT, WRITING_RULES))
    assert ('When no finding survives this step, display "**Health Check:** no finding could be drafted, so nothing '
            'was reviewed or sent." and then "Workflow complete.", then, when `{result_envelope_line}` is bound, that '
            "line verbatim, as the last line, and STOP.") in draft
    assert "the stop when no finding survives §3," in _flow(_section(text, "### 0. Announce Arrival"))


def test_the_docs_cover_the_off_switch_what_is_sent_the_gate_autosubmit_and_the_own_stage():
    section = _slice(_read(WORKFLOWS_DOC), "## Terminal Step: Health Check", "### Please let workflows run")
    for heading in ("### Turning it off", "### What gets sent", "### The review gate", "### How findings are routed",
                    "### Submitting from headless runs", "### Submitting a queued finding"):
        assert heading in section, heading
    flow = _flow(section)
    for needle in ("health_check_repo: ''", "health_check_autosubmit: true", "**A defect in the health check itself.**",
                   "name no project, library, skill, file or path of yours and no secret",
                   "filed with your own GitHub account; on the default repository it is public",
                   "a YAML null (`~`, `null`, `Null` or `NULL`) all count as empty",
                   # Round 1: a BMAD Method install or update rewrites the config, so a hand-set key is gone.
                   "A BMAD Method install or update (`npx bmad-method install`) rewrites `_bmad/skf/config.yaml` and "
                   "drops a `health_check_repo` or `health_check_autosubmit` you set by hand"):
        assert needle in flow, needle
    # A draft with no fingerprint takes the whole header the helper prints, not two filled-in lines.
    assert ("replace the draft's whole header, from `## Workflow` to the `## Defect Key` section, with the "
            "`body_header` it prints") in flow
