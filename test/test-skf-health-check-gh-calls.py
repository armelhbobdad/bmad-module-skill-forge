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
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"

SUB_STEP_5A_I = "**5a-i. If a matching open issue exists:**"
SUB_STEP_5A_II = "**5a-ii. If no matching open issue exists**"
CREATE = "**Then create the issue:**"
WRITING_RULES = "**Writing rules"

# Where each issue and comment body is written before the call that posts it: a file of its own for each post,
# apart from the findings the queue folder holds.
BODY_FILE = '--body-file "{localFallbackFolder}/bodies/{fp}-{timestamp}.md"'

# The calls the step must hold, each as the start of one call found, so an extractor that misses fenced lines,
# continuation lines or inline code spans fails here instead of passing on too few calls.
REQUIRED_CALLS = {
    "the search by fingerprint": 'gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" ',
    "the search by section fingerprint":
        'gh search issues --repo {healthCheckRepo} --state open "{legacy_fp} in:title,body" ',
    "the reaction": "gh api -X POST repos/{healthCheckRepo}/issues/{N}/reactions -f content='+1'",
    "the comment": "gh issue comment {N} --repo {healthCheckRepo} ",
    "the label": 'gh label create "{fp}" --repo {healthCheckRepo} ',
    "the new issue":
        'gh issue create --repo {healthCheckRepo} --title "[health-check][{severity}][{fp}] {workflow}: ',
    "the local queue's hint": 'gh issue create --repo {healthCheckRepo} --title \\"[title]\\" ',
}

# `gh` commands the step names without running them on an issue of its own: the helper's `gh issue view` (it
# asks by the recorded issue URL), the availability check, and the commands the label guard talks about.
MENTIONS = {"gh issue view", "gh auth status", "gh issue create --label fp-XXXX", "gh label create", "gh issue create"}

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
            assert "--repo {healthCheckRepo}" in call or "repos/{healthCheckRepo}/" in call, call
    # A call with no placeholder can only be one the step mentions, never one it runs on an issue.
    plain = {call for call in calls if not PLACEHOLDER.search(call)}
    assert plain <= MENTIONS, plain - MENTIONS


def test_r_and_c_react_and_comment_on_the_health_check_issue():
    actions = _slice(_read(SHARED_HEALTH_CHECK), "Execute the chosen action:", SUB_STEP_5A_II)
    # No leading slash, as the repository's other `gh api` calls write the path.
    assert "- **R:** `gh api -X POST repos/{healthCheckRepo}/issues/{N}/reactions -f content='+1'`\n" in actions
    # The comment's body goes in a file, written before either call, so a Write that fails posts nothing.
    assert (f"- **C:** Same reaction call, then `gh issue comment {{N}} --repo {{healthCheckRepo}} {BODY_FILE}`. The "
            "delta body is the Environment table plus ONE sentence describing what's different from the original. No "
            "session narrative. Write it to that file with the Write tool before the reaction, as **Pass each body as "
            "a file** in §5a-ii says.") in _flow(actions)
    assert ("The **R** and **C** calls name `{healthCheckRepo}`, as the step's other issue calls do: without it, `gh` "
            "reacts or comments on the repository of the folder the workflow ran in, usually the user's own "
            "project.") in _flow(actions)


def test_only_a_reaction_or_comment_that_posted_is_recorded():
    text = _read(SHARED_HEALTH_CHECK)
    choice = _flow(_slice(text, SUB_STEP_5A_I, SUB_STEP_5A_II))
    rule = ("If one of them exits non-zero, log its stderr message and make no further call for this finding: **C** "
            "posts no comment after a failed reaction, and a reaction it already added stays. Record nothing (run "
            "neither record call below) and write the finding to the local queue (§5c) with the failed-submission "
            "reason.")
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
    instead = choice.index("When sub-step 2 returned `regression`, run this one instead")
    # A **C** whose reaction or comment failed keeps its body file, named by the fingerprint the queued finding records.
    kept = ("When **C** fails, its body file stays in `{localFallbackFolder}/bodies/`, its name starting with the "
            "`fingerprint` the queued finding records.")
    assert choice.index(rule) < choice.index(kept) < choice.index(success) < plain < instead < regression
    # The queue takes the finding, with a reason of its own.
    queue = _flow(_slice(text, "### 5c.", "**Filename:**"))
    assert ("a run with no user to ask took **\\[S]** at a possible match, a reaction or comment at the dedup gate "
            "failed, a new issue failed to post, or the §4 review gate resolved to **\\[Q]**") in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "**{N} finding(s) saved locally:**"))
    assert ('"Posting these to GitHub failed." (the failed-submission reason) or "The review gate queued these '
            'locally."') in reasons


def test_no_body_goes_on_the_command_line():
    """Inside double quotes the shell runs each backticked span of a body, so every body goes to `gh` as a file."""
    text = _read(SHARED_HEALTH_CHECK)
    # Not in a call and not in the prose either, so no copied example puts a body back on the command line.
    inline = re.search(r"--body(?!-file)", text)
    assert inline is None, text[max(0, inline.start() - 80):inline.end() + 80]
    short = re.search(r"(?<![\w-])-b(?![\w-])", text)
    assert short is None, text[max(0, short.start() - 80):short.end() + 80]
    # The comment and the new issue each post the body file, as the call's last argument.
    calls = _gh_calls(text)
    for name in ("the comment", "the new issue"):
        found = [call for call in calls if call.startswith(REQUIRED_CALLS[name])]
        assert found and all(call.endswith(BODY_FILE) for call in found), (name, found)


def test_each_body_is_written_to_a_file_with_the_write_tool():
    raw = _slice(_read(SHARED_HEALTH_CHECK), CREATE, WRITING_RULES)
    # The command keeps its other lines; only the body line changed.
    assert ('  --title "[health-check][{severity}][{fp}] {workflow}: {short description}" \\\n'
            '  --label "health-check,workflow-improvement,{severity},{fp}" \\\n'
            f"  {BODY_FILE}\n```\n") in raw
    after = _flow(raw[raw.index(f"  {BODY_FILE}\n```\n"):])
    # Written before the label call too, so a Write that fails leaves no `fp-*` label with no issue behind it.
    rule = ("**Pass each body as a file.** Before the label call above, write the issue body (the format below) with "
            "the Write tool to a file of its own, `{localFallbackFolder}/bodies/{fp}-{timestamp}.md`, `{timestamp}` "
            "being the time of the write as YYYYMMDD-HHmmss; **C** writes its comment body the same way.")
    for needle in (
        rule,
        "on the command line, inside double quotes, the shell would run each backticked span or `$(...)` as a "
        "command and put its output in its place, and a double quote in it would end the argument.",
        "So a body never goes on the command line, and the file is never written through the shell (`echo`, "
        "`printf` or a heredoc), which can expand it the same way.",
        # With no body of this post written, a call would send nothing or an earlier post's body.
        "If the Write fails, make no call for this finding: log the error and write the finding to the local "
        "queue (§5c) with the failed-submission reason.",
        # Inside double quotes a backslash still escapes what follows it, the closing quote included.
        "The title does stay on the command line, so write `{short description}` with no backtick, `$`, double quote "
        "or backslash.",
        # Each post keeps its own file, out of the queue's findings, so none is replaced or read as one waiting.
        "The file stays after the call, in `bodies/` apart from the findings the queue holds, as the record of what "
        "was sent or tried; a later post writes a new one.",
    ):
        assert needle in after, needle
    # The rule comes right after the command, before the regression marker that edits it.
    assert after.index(rule) < after.index("When sub-step 2 returned `regression`, append")


def test_a_create_that_failed_goes_to_the_local_queue_with_its_body():
    text = _read(SHARED_HEALTH_CHECK)
    create = _flow(_slice(text, CREATE, WRITING_RULES))
    recorded = ("After the issue is created, record it under `{fp}` as §5b says, so this user does not re-report it "
                "while that issue stays open.")
    failed = ("If `gh issue create` exits non-zero, log its stderr message and record nothing: §5b runs only after a "
              "create that succeeded, so after a `regression` verdict the `resolved` record stays. Write the finding "
              "to the local queue (§5c) with the failed-submission reason, as a failed reaction or comment is: its "
              "queue file holds the text of its body file under the §5c frontmatter, so what failed to post is what "
              "waits to be submitted.")
    assert recorded in create and failed in create
    assert create.index(recorded) < create.index(failed)
    # The issues-created display counts only the issues that posted.
    display = _flow(_slice(text, "**Issue body format:**", "### 5b."))
    assert ("After creating all issues, display those that were created, `{N}` counting only them, unless none was "
            "(a create that failed is listed by §5c): \"**{N} issue(s) created on {healthCheckRepo}:**") in display
    # The queue file of a failed create holds the body that failed to post.
    queue = _flow(_slice(text, "### 5c.", "```yaml"))
    assert ("**File content:** Same structured format as the issue body above, with YAML frontmatter (for a create "
            "that failed, that body is the text of its body file in `{localFallbackFolder}/bodies/`, "
            "unchanged):") in queue


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
        'more here: §5c writes its files, then ends its block with that line. Otherwise display "Workflow complete." '
        "now, after the block above, or alone when no issue was created because every finding was a reaction or a "
        "comment that posted (§5a-i).")
    # §5c's block, displayed after its files are written, keeps the line, and only the result line comes after it.
    queue = _slice(text, "After writing all files,", "When `{result_envelope_line}` is bound (§0), display it verbatim "
                                                     "after that block, as the last line.")
    assert queue.rstrip().endswith("Workflow complete.\"")
