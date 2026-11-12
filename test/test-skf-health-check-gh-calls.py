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
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"

SUB_STEP_5A_I = "**5a-i. If a matching open issue exists:**"
SUB_STEP_5A_II = "**5a-ii. If no matching open issue exists**"

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
    # What follows the prefix, the body, is #1203's to change.
    assert "- **C:** Same reaction call, then `gh issue comment {N} --repo {healthCheckRepo} " in actions
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
    assert choice.index(rule) < choice.index(success) < plain < instead < regression
    # The queue takes the finding, with a reason of its own.
    queue = _flow(_slice(text, "### 5c.", "**Filename:**"))
    assert ("a run with no user to ask took **\\[S]** at a possible match, a reaction or comment at the dedup gate "
            "failed, or the §4 review gate resolved to **\\[Q]**") in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "**{N} finding(s) saved locally:**"))
    assert ('"Posting these to GitHub failed." (the failed-submission reason) or "The review gate queued these '
            'locally."') in reasons
