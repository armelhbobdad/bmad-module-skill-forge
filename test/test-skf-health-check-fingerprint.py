"""Prose-contract tests: a health-check fingerprint names the defect.

The dedup Action closes a newer open issue that carries an earlier open one's
`fp-*` label, so a fingerprint must tell two defects in one section apart.
It hashes the severity, workflow, step file, section slug and a defect key,
the name of the thing the fix would change, so two different defects of one
severity in one section (the only section of
skf-test-skill/references/inventory-contract.md, say) get two fingerprints,
while two reports of one defect that name the same thing still get one.
Issues and seen-cache records made by an SKF version without the key carry
the section (legacy) fingerprint, the same hash without it, and every new
issue records that one in its body: the seen-cache check and the remote
search still look it up, but only as a possible match, which never
suppresses a finding or posts on an issue without the user's pick. No test
runs the step prose, so these checks pin it. The hashes, the fields they
hash in one form whatever the install, the section slug and defect key the
helper derives from a heading and a name, the seen-cache verdicts and its
merge are skf-health-check-seen.py's (#1122), whose behaviour
test-skf-health-check-seen.py pins.

The dedup Action is run under node with a stubbed client: its event gate, the
canonical and flagged issues numbered below the new one, a report filed
without labels (a reporter without push access) labelled from SKF's title or
its body, and the flag's label before its comment (armelhbobdad/bmad-module-ultracode-goal#226).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"
ISSUE_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md"
WORKFLOWS_DOC = REPO / "docs" / "workflows.md"
DEDUP_WORKFLOW = REPO / ".github" / "workflows" / "health-check-dedup.yaml"
HELPER = REPO / "src" / "shared" / "scripts" / "skf-health-check-seen.py"

# §3 names, fingerprints and drafts every finding, whatever its route (#226): its rules run from its heading to
# **Write the draft.**, and §5a starts at the seen-cache lookup.
DRAFT = "### 3. Draft Each Finding"
WRITE_DRAFT = "**Write the draft.**"
SUB_STEP_2 = "**1. Check the local seen-cache**"
SUB_STEP_3 = "**2. Check GitHub CLI availability**"
SUB_STEP_4 = "**3. Remote dedup search**"
SUB_STEP_5A_II = "**5a-ii. If no matching open issue exists**"

# The keys of two different defects in the only section of one step file
# (test-skf-health-check-seen.py hashes them through the step's own call).
KEYS = ("const-holding-function", "shared-text")


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


def _headings(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("## ")]


def _helper():
    spec = importlib.util.spec_from_file_location("skf_health_check_seen_prose", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- the formula


def test_the_fingerprint_hashes_the_defect_key():
    text = _read(SHARED_HEALTH_CHECK)
    # The draft's header shows the fields in the form the helper prints, never a doubled `src/skf-skf-` prefix.
    assert "skf-{workflow}" not in text
    step = _slice(text, DRAFT, WRITE_DRAFT)
    # The helper hashes both (test-skf-health-check-seen.py runs this call and pins the formula); the step names the
    # heading, the thing and the title's description, in a file the Write tool writes, so no quote in them meets the
    # shell.
    assert ('uv run {seenCacheHelper} fingerprint --severity "{severity}" --workflow "{workflow}" '
            '--step-file "{step_file}" --stdin < "{localFallbackFolder}/bodies/names-{timestamp}-{i}.json"') in step
    flow = _flow(step)
    assert ("Write the two names and the description with the Write tool to "
            "`{localFallbackFolder}/bodies/names-{timestamp}-{i}.json`, `{timestamp}` being the time of the write as "
            "YYYYMMDD-HHmmss and `{i}` the finding's number, as the JSON object `{\"section_heading\": \"<the "
            "heading>\", \"defect_name\": \"<the name>\", \"short_description\": \"<the description>\"}` with each "
            "value JSON-escaped, so no quote in a name meets the shell.") in flow
    # The title, its regression form and the body's header come from the same call: the model types none of them.
    assert ("It prints `{\"fp\", \"legacy_fp\", \"tuple\", \"step_file\", \"section_slug\", \"defect_key\", "
            "\"title\", \"regression_title\", \"body_header\"}`.") in flow
    assert ("Use `{title}`, or `{regression_title}` after a `regression` verdict (§5a), exactly as printed wherever "
            "the finding's title appears.") in flow
    assert "No `title` means the names file held no description: add it there and run the call once more." in flow
    # UltraCode Goal's quality gate (round 1, leanness-1): the model hashes nothing, so the step states no formula.
    assert "sha1(" not in text and "sha1sum" not in text


def test_the_defect_key_rule_says_how_to_pick_it():
    rule = _flow(_slice(_read(SHARED_HEALTH_CHECK), DRAFT, WRITE_DRAFT))
    for needle in (
        "in the step file's or the code's own words: a script by its file name, a function, a script subcommand",
        "Pick the most specific name the fix would edit, so two defects in one section get two fingerprints and two "
        "reports of one defect get one",
        # The cap the helper holds (test_the_helpers_slug_and_key_rules_give_the_steps_examples): a name to keep short.
        "the helper turns it into the defect key, one to four lower-case ASCII words (a longer name keeps its last "
        "four).",
        "When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two "
        "to four of the step file's own words, the noun the rule would be about, then what makes the case distinct.",
        "`floor_check` gives `floor-check`",
        "`--orphan-action` flag gives `orphan-action`",
        "gives `const-holding-function`",
        # A script is named by its file name now, as bmad-module-ultracode-goal names it: the helper drops its path,
        # extension and line.
        "Never use a path, a line number, a severity, or words from this session's own story",
        "whoever reports the same defect next must reach the same key from the source alone",
        "Never use the section's own subject alone either: every defect in the section shares it.",
    ):
        assert needle in rule, needle
    # A fallback to the section's subject gives every such report in a section one key, the merge the key ends.
    assert "use the section's own subject." not in rule
    assert "a file name or path" not in rule


def test_the_step_says_how_to_name_the_step_file_and_the_section():
    rule = _flow(_slice(_read(SHARED_HEALTH_CHECK), DRAFT, WRITE_DRAFT))
    for needle in (
        # A step file one workflow loads from another's references/ is that other workflow's: one fingerprint. The
        # helper names that workflow when it is given the wrong one (test-skf-health-check-seen.py).
        "The step file is the `references/` file whose instruction bit, and `{workflow}` is the folder name of the "
        "workflow whose `references/` folder holds it: usually the workflow that just ran, and the other workflow for "
        "a step file loaded from its `references/`.",
        "The section is the heading of the innermost section of the step file that holds the instruction, copied "
        "exactly as the file writes it, numbering included.",
        "A bold run-in label (`**Foo.**`) is no heading: take the heading that encloses it.",
        # bmad-module-ultracode-goal's rule for a defect outside the stage files, in SKF's terms.
        "A defect in an instruction of the workflow's SKILL.md, of a script or of a `shared/references` file takes "
        "the step file that was running when it bit and the heading of that file's section that was running, or the "
        "file's H1 when none fits.",
        # Round 1 architecture-2: the relays that hold an instruction of their own are step files too. Round 2: the
        # section comes from the innermost-section rule, since Update Skill's relay has three headings, and a defect in
        # its steps 1 to 1c named under the H1 or under `Steps` would get two fingerprints.
        "A defect in what a workflow's own `references/health-check.md` does besides loading this step (Update "
        "Skill's, Quick Skill's and Verify Stack's) takes that file, its section found by the innermost-section "
        "rule above.",
    ):
        assert needle in rule, needle
    assert "takes that file and its heading" not in rule


def test_a_refused_value_is_fixed_once_and_never_loops():
    """A headless run has nobody to fix a value for it: a second refusal sends the finding to the local queue."""
    text = _read(SHARED_HEALTH_CHECK)
    rule = _flow(_slice(text, DRAFT, WRITE_DRAFT))
    assert ("On exit 2 its stderr line names the value it refused: fix that value, or for a refused heading take the "
            "heading that encloses it (the file's H1 at the top), and run the call once more. Never loop: when that "
            "second call is refused too, log its message, naming the finding, give the finding the fingerprint `N/A` "
            "and send it to the local queue (§5c) with the could-not-fingerprint reason.") in rule
    assert "Fix that value by its rule and run the call again." not in rule
    # A names file that was never written makes a call that prints no JSON: that is no missing helper.
    assert ("If the Write fails, or the shell says it cannot open that file, make no fingerprint call for this finding "
            "(a call that cannot read its names file prints no JSON, which does not mean the helper is missing): log "
            "the error, naming the finding, give the finding the fingerprint `N/A` and send it to the local queue "
            "(§5c) with the could-not-fingerprint reason.") in rule
    queue = _flow(text[text.index("### 5c."):])
    assert ("a missing helper, no fingerprint, an unchecked draft, no repository or a refused call, which skips §4 "
            "before the gate (§3)") in queue
    assert ('"SKF\'s health-check helper could not fingerprint these findings, so they carry the fingerprint N/A; '
            'compute it with its fingerprint call before submitting." (the could-not-fingerprint reason)') in queue
    assert "refused-values" not in text and "as its message says" not in text
    # Every route has its draft and fingerprint before the gate: §3 runs the call for each finding, so **IF Q** and a
    # headless run need no call of their own.
    assert "§3's call" not in _slice(text, "- **IF Q:**", "### 5.")
    assert ("Every finding, whatever its route, gets its fingerprints, its title and its issue body on disk before "
            "anyone reviews it") in _flow(text)


def test_the_helpers_slug_and_key_rules_give_the_steps_examples():
    """The model no longer turns a heading into a slug or a name into a key: the helper does, so the step states
    neither rule (UltraCode Goal's quality gate, round 1, leanness-1) and the helper holds both, with every example
    the step and the old prose gave."""
    text = _read(SHARED_HEALTH_CHECK)
    rule = _flow(_slice(text, DRAFT, WRITE_DRAFT))
    for gone in ("The section slug is the heading with its leading", "The helper drops the backticks or quotes",
                 "keeps its last path component"):
        assert gone not in rule, gone
    helper = _helper()
    assert helper.section_slug("### 5a. Live-Submit Path: Dedup and Create") == "live-submit-path-dedup-and-create"
    # A heading copied in another letter case or with other punctuation gives the same slug.
    assert helper.section_slug("### 5A. LIVE-SUBMIT PATH: dedup and create") == "live-submit-path-dedup-and-create"
    # The heading is the step's own, so the own stage's call takes it.
    assert "### 5a. Live-Submit Path: Dedup and Create\n" in text
    for name, key in re.findall(r"`([^`]+)` gives `([a-z0-9-]+)`", rule):
        if name.startswith("#"):
            assert helper.section_slug(name) == key, name
        else:
            assert helper.defect_key(name) == key, name
    for name, key in (("floor_check", "floor-check"), ("--orphan-action", "orphan-action"),
                      ("const holding function", "const-holding-function"),
                      ("scripts/gate_eval.py:42:7", "gate-eval"), ("composeStories", "compose-stories"),
                      # Two independent reports of one defect wrote these two (PR #982's key-stability measurement).
                      ("reader's own code", "readers-own-code"), ("readers own code", "readers-own-code"),
                      # A name of more than four words keeps its last four (DEFECT_KEY_WORDS), as the step says.
                      ("the run lock release step", "run-lock-release-step"),
                      ("one two three four five six", "three-four-five-six")):
        assert helper.defect_key(name) == key, name
    assert helper.DEFECT_KEY_WORDS == 4
    for key in KEYS:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){0,3}", key), key


def test_the_defect_key_examples_name_real_things():
    """The examples are the step files' and the code's own names, not invented ones."""
    src = REPO / "src"
    assert "def floor_check(" in _read(src / "skf-test-skill" / "scripts" / "validate-inventory.py")
    assert "`--orphan-action`" in _read(src / "skf-setup" / "references" / "auto-index.md")
    contract = _read(src / "skf-test-skill" / "references" / "inventory-contract.md")
    # The missing-rule example names its case in the step file's own words: the rule for a `const` holding a
    # component exists. Whether the contract later adds the function case (#970) does not matter here: the example
    # only has to use the step file's own words.
    assert "A `const` holding a component" in contract
    # The sample's second key is that file's own rule term.
    assert "shared text" in contract


def test_the_step_hashes_nothing_and_works_no_cache_by_hand():
    """#1122: every fingerprint and seen-cache read and write is a {seenCacheHelper} call, which
    test-skf-health-check-seen.py pins, and test-skf-helper-call-contract.py checks against its parser."""
    text = _read(SHARED_HEALTH_CHECK)
    for gone in ("sha1sum", "shasum", "python -c", "timeout 10", "Read `{seenCachePath}`", "append to `{seenCachePath}`",
                 "Read the existing file", "**Legacy records.**"):
        assert gone not in text, gone
    calls = re.findall(r"^uv run \{seenCacheHelper\} ([\w-]+)(?: |$)", text, re.MULTILINE)
    # §3 reads the settings once, fingerprints and checks each finding and takes the version for its draft's
    # Environment; §5a-i and §5b each have a plain record call and one with --regression; §5c queues each finding
    # that stays local.
    assert calls == ["settings", "fingerprint", "check-draft", "version", "lookup", "record", "record", "record",
                     "record", "queue"], calls
    frontmatter = text.split("\n---\n", 1)[0]
    # The last entry resolves from the SKF module root, as the path convention says: a plugin install has neither
    # {project-root} path.
    assert ("seenCacheProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-health-check-seen.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-health-check-seen.py'\n"
            "  - 'shared/scripts/skf-health-check-seen.py'\n") in frontmatter + "\n"
    assert "seenCachePath: '$HOME/.skf/health-check-seen.json'" in frontmatter
    step = _flow(_slice(text, DRAFT, WRITE_DRAFT))
    assert "Resolve `{seenCacheHelper}` from `{seenCacheProbeOrder}`; first existing path wins." in step
    assert ("Its last entry resolves from the SKF module root (the path convention above), where a plugin install "
            "keeps it.") in step
    assert "> **Path convention:** This file is referenced as `shared/health-check.md`" in text
    # No helper, no hand-rolled fallback: the findings stay local, with their own reason.
    assert ("If no candidate exists, give each finding the fingerprint `N/A`, write its draft by hand as **Write the "
            "draft** says, and send every finding that §4 does not discard to the local queue (§5c) with the "
            "missing-helper reason: there is no fallback.") in step
    assert "Never hash a fingerprint or read or write `{seenCachePath}` by hand: the helper does both." in step
    assert "On exit 2 its stderr line names the value it refused" in step
    # A call the helper never answered (uv or Python could not start it) is a missing helper, not a value to fix.
    assert ("JSON on neither stream means the helper did not run: treat it as missing (fingerprint `N/A`, "
            "missing-helper reason).") in step
    queue = _flow(text[text.index("### 5c."):])
    assert "gh unavailable or refused (§5a sub-step 2)" in queue
    # A finding with no fingerprint has no header the queue call reads: its hand-written draft stands in.
    assert ("A finding with the fingerprint `N/A` gets no queue call, and nor does any finding when `{healthCheckRepo}` "
            "is no repository (§3) or after a refused call (§3): list its draft (§3) in the queue file's place") in queue
    assert '"SKF\'s health-check helper is missing; re-install SKF to submit these."' in queue
    draft = _flow(_slice(text, WRITE_DRAFT, "**Writing rules"))
    assert ("A finding with the fingerprint `N/A` has no `body_header`: write its header by hand in the same form, "
            "with the workflow, the step file as `src/{workflow}/references/{file}.md`") in draft
    assert ("`N/A` as the Fingerprint and in the `Section fingerprint:` line, and the defect name, each in backticks. "
            "Name its draft `{localFallbackFolder}/bodies/hc-{workflow}-{timestamp}-{i}-draft.md`, `{i}` being the "
            "finding's number, and its title `[health-check][{severity}][N/A] {workflow}: {short description}`.") in draft


# ---------------------------------------------------------------- the legacy fallback


def test_the_step_maps_each_verdict_to_its_action():
    """The helper works the cache, the issue's state, --repo and the legacy fallback (test-skf-health-check-seen.py
    pins every branch); the step maps its five verdicts to skip, submit or submit with a `## Regression` section
    (UltraCode Goal's quality gate, round 1, leanness-2)."""
    text = _read(SHARED_HEALTH_CHECK)
    raw = _slice(text, SUB_STEP_2, SUB_STEP_3)
    assert 'uv run {seenCacheHelper} lookup --fp "{fp}" --legacy-fp "{legacy_fp}" --repo "{healthCheckRepo}"\n' in raw
    step = _flow(raw)
    assert "If the call fails or prints no JSON, continue as `unseen`: this check never halts a run." in step
    bullets = re.findall(r"^- `([a-z-]+)`(?: and `([a-z-]+)`)?[,:]", raw, re.MULTILINE)
    assert sorted(v for pair in bullets for v in pair if v) == sorted(
        ["unseen", "handled", "regression", "possible-regression", "unrecognized"]), bullets
    for needle in (
        "- `handled`, the only verdict that suppresses: skip the finding and log "
        "`\"{fp}: already handled on {date}, issue {url}, skipping\"`.",
        "- `unseen` and `unrecognized`: submit it as a first sighting. When `matched_on` is `legacy_fp`, log "
        "`\"{fp}: legacy record {legacy_fp} may be another defect, reporting\"`.",
        "- `regression`: file it under `{regression_title}` in place of `{title}` (§5a-ii, §5c), and add a "
        "`## Regression` section to the draft right above `## Finding`, holding the `opening_line` exactly as printed.",
        "- `possible-regression`: add the same section, and keep `{title}`: the fix it links may be another defect's.",
        "Every verdict but `handled` goes on to sub-step 2. If adding the `## Regression` section fails, log its error "
        "and write the finding to the local queue (§5c) with the failed-submission reason.",
    ):
        assert needle in step, needle
    # What the helper decides is no longer retold.
    for gone in ("**Presence in the cache is not the verdict.**", "**What this does and does not catch.**",
                 "**Why anything uncertain reports instead of suppressing.**", "The cache serves every project"):
        assert gone not in text, gone
    # The reason the helper reports anything uncertain lives beside the verdicts it gives.
    doc = _helper().__doc__
    assert "handled is the only verdict that suppresses a report." in doc
    assert "a duplicate heals itself" in doc and "silenced regression is caught by nothing" in doc


def test_a_legacy_regression_is_only_a_possible_one():
    text = _read(SHARED_HEALTH_CHECK)
    step = _flow(_slice(text, SUB_STEP_2, SUB_STEP_3))
    assert "- `possible-regression`: add the same section, and keep `{title}`" in step
    # The helper writes the line, as UCG's does (test-skf-health-check-seen.py's TestOpeningLine pins its text).
    assert "holding the `opening_line` exactly as printed" in step
    assert "\u2014 REGRESSION" not in text, "the old suffix marker"
    assert "resolved {date}.`" not in text, "no hand-written line that dates a fix by its report"
    # The title marker stays with `regression` alone.
    create = _flow(_slice(text, SUB_STEP_5A_II, "### 5b."))
    assert ("When sub-step 1 returned `regression`, put `{regression_title}` in that `--title` value in place of "
            "`{title}`") in create
    assert "A `possible-regression` gets its `## Regression` section and no title marker." in create


def test_the_remote_search_falls_back_to_the_legacy_fingerprint():
    text = _read(SHARED_HEALTH_CHECK)
    search = _slice(text, SUB_STEP_4, "**5a-i. If a matching open issue exists:**")
    command = ('gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" '
               '--json number,url,title --limit 1')
    fallback = ('gh search issues --repo {healthCheckRepo} --state open "{legacy_fp} in:title,body" '
                '--json number,url,title --limit 5')
    assert command in search and fallback in search
    assert search.index(command) < search.index(fallback)
    flow = _flow(search)
    assert "When it finds none, search once more, for the section fingerprint in titles and bodies" in flow
    # Bodies too: a keyed issue from the same section under another key carries the section fingerprint only there.
    assert "Each issue this second search finds is only a possible match: the user decides at 5a-i." in flow


def test_a_keyless_fingerprint_is_not_dated_to_this_change():
    """Older SKF installs keep filing keyless fingerprints after this ships."""
    text = _flow(_read(SHARED_HEALTH_CHECK))
    assert "filed before fingerprints carried a defect key" not in text
    assert "made before the key existed" not in text
    assert ("`{legacy_fp}` is the section fingerprint, the same hash without the defect key, so a match on it is only "
            "ever a possible match.") in text


def test_a_legacy_match_goes_to_the_users_choice():
    choice = _flow(_slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II))
    assert ("When the issues were found by `{legacy_fp}`, list each one and present the same options under this "
            "opening instead") in choice
    assert '"**Possible match:** #{N}: {title} (one line for each issue found)' in choice
    assert ("It carries this section's fingerprint `{legacy_fp}`, which every `{severity}` finding in this section "
            "shares, so it may report another defect.") in choice
    assert "naming it when more than one is listed, and **\\[N]** if none does" in choice
    for option in ("**\\[R]**", "**\\[C]**", "**\\[N]**", "**\\[S]**"):
        assert option in choice, option
    # A headless run with autosubmit on reaches it, and never acts on a guess.
    assert ("**Headless default: \\[S].** Only the user decides a match: a headless run takes **\\[S]** at an exact or "
            "a possible match, with the match or the possible-match reason.") in choice
    # #1202: only a reaction or comment that posted is recorded (test-skf-health-check-gh-calls.py pins the rest).
    assert ("When every call of **R** or **C** succeeded, record the outcome under `{fp}`, also when the match was "
            "found by `{legacy_fp}`: `reacted` after **R** and `commented` after **C**") in choice
    raw = _slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II)
    reaction = ('uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" '
                '--date "{today}"')
    assert f"{reaction}\n" in raw and f"{reaction} --regression\n" in raw
    # After a regression verdict, a plain call leaves the hand-written `resolved` record in place, so every later
    # session would get `regression` again and ask about the same open issue (#1122, review loop 1).
    assert ("When sub-step 1 returned `regression`, run this one instead, since this open issue now tracks the "
            "recurrence:") in choice
    assert "- **S:** Record nothing" in choice
    assert "Read what the call prints as §5b says; if it fails, log its stderr message and go on." in choice


def test_new_at_an_exact_match_names_the_defect_more_specifically():
    """The issue 5a-ii creates carries the `{fp}` label, which the dedup Action closes as a duplicate of the
    open match: [N] there has to change the key first. A possible match carries another label."""
    choice = _flow(_slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II))
    assert ("**N:** After a match found by `{fp}`, a new issue under that fingerprint would be closed as its duplicate: "
            "choose a more specific defect name that sets this defect apart, still in the source's words, write the "
            "names file anew, run §3's fingerprint call again and write and check the draft anew under the new `{fp}`, "
            "as §3 does, without a section the old verdict added, then run sub-steps 1 to 3 again for it.") in choice
    # A longer name can give the same key, so the same match would come back: that is a skip.
    assert "When the new `{fp}` is the old one, take **S** instead." in choice
    assert "After a possible match, go on to 5a-ii as is: that issue's `fp-*` label differs from `{fp}`." in choice
    assert "- **N:** Proceed to step 5a-ii." not in choice
    action = _read(REPO / ".github" / "workflows" / "health-check-dedup.yaml")
    assert "labels: `health-check,${fpLabel}`" in action


def test_a_run_with_nobody_to_ask_queues_with_its_own_reason():
    text = _read(SHARED_HEALTH_CHECK)
    queue = _flow(text[text.index("### 5c."):])
    assert "**\\[S]** (§5a-i)" in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "When `{result_envelope_line}` is bound"))
    assert ('"These may match an open issue from the same section; review them before submitting." '
            "(the possible-match reason)") in reasons
    assert ('"These match an open issue with the same fingerprint; react or comment there, or file them anyway, after '
            'review." (the match reason)') in reasons


def test_a_differently_named_report_is_left_to_the_docs_and_the_action():
    """The step no longer retells what the fingerprint cannot catch or what the dedup Action does with a shared
    section fingerprint (round 1, leanness-2): the docs say it (test_the_docs_state_the_keyed_fingerprint) and the
    Action does it (the node tests below)."""
    text = _read(SHARED_HEALTH_CHECK)
    assert "safe but unlinked" not in text and "possible-duplicate" not in text
    bullet = next(line for line in _read(WORKFLOWS_DOC).splitlines() if line.startswith("- **Fingerprint dedup.**"))
    assert ("Two reports of one defect often name it differently, so a report you open anyway can arrive as a new "
            "issue even when it duplicates an open one.") in bullet


def test_the_seen_cache_is_written_under_the_new_fingerprint():
    text = _read(SHARED_HEALTH_CHECK)
    assert "After the issue is created, record it under `{fp}` as §5b says." in _flow(text)
    raw = _slice(text, "### 5b.", "### 5c.")
    created = 'uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}"'
    assert f"{created}\n" in raw and f"{created} --regression\n" in raw
    cache = _flow(raw)
    assert ("When sub-step 1 returned `regression`, run this one instead: the new issue tracks the recurrence, so it "
            "replaces the `resolved` record the fix left under `{fp}`.") in cache
    # What the helper guarantees is its own (TestRecord): the step keeps what the model acts on (spec-gh-1122).
    assert ('`"written": false` is no error: the helper kept a `resolved` record, which only `--regression` '
            "replaces.") in cache
    assert ("If the call fails, log its stderr message and go on: a lost record costs at most a duplicate report, "
            "which the dedup Action closes.") in cache
    assert "**What the helper guarantees.**" not in cache
    # A cache the helper set aside is named to the user, who can still copy its records back.
    assert ("When `set_aside` is not null, after this call or §5a-i's, tell the user that `{seenCachePath}` did not "
            "parse, so it was renamed to that path and a new cache was started, and that they keep its records by "
            "fixing that file and copying its entries into `{seenCachePath}`.") in cache
    # The vocabulary stays; the helper makes the folder, so the step does not.
    assert "**The `action` vocabulary is `created`, `reacted`, `commented`, `resolved`.**" in cache
    assert ("Nothing else is recorded: not a queued finding, not **\\[S]**, not a failed or refused call. A queued "
            "finding is not an issue, and a record for it would suppress the same defect when a later run approves "
            "it.") in cache
    assert "Ensure the parent directory exists." not in text


# ---------------------------------------------------------------- the issue body


def test_the_issue_body_records_every_fingerprint_input():
    text = _read(SHARED_HEALTH_CHECK)
    body = _slice(text, "**Issue body format:**", "### 4.")
    headings = _headings(body)
    order = ["## Workflow", "## Step File", "## Section", "## Severity", "## Fingerprint", "## Defect Key",
             "## Finding"]
    assert [h for h in headings if h in order] == order
    assert "## Section\n`{section-slug}`\n" in body
    assert "## Defect Key\n`{defect-key}`\n" in body
    # The section fingerprint rides in the body, where the fallback search reads it, and never as a label,
    # because the dedup Action takes the first `fp-*` label it finds.
    fingerprint = _slice(body, "## Fingerprint", "## Defect Key")
    assert "\nSection fingerprint: `{legacy_fp}`\n" in fingerprint
    assert "body text only, never a label, since the dedup Action reads it to flag possible duplicates." in _flow(body)
    # The Action finds that line by the pattern the body writes it in, at the start of a line.
    assert "const SECTION_RE = /^Section fingerprint: `(fp-[0-9a-f]{7})`/m;" in _read(DEDUP_WORKFLOW)
    create = _slice(text, "**Then create the issue:**", "When sub-step 1 returned `regression`, put")
    assert '--label "health-check,workflow-improvement,{severity},{fp}"' in create
    assert "legacy_fp" not in create


def test_the_body_format_opens_with_the_helpers_body_header():
    """The model copies the header the helper prints: the step's format shows exactly that, filled in."""
    body = _skf_body("gap", BARE_FP, SECTION_FP)
    header = _helper().body_header("gap", "skf-test-skill", "src/skf-test-skill/references/inventory-contract.md",
                                   "documented-inventory-contract", "const-holding-function", BARE_FP, SECTION_FP)
    assert body.startswith(header + "\n## Finding\n"), body[:400]
    assert ("**Issue body format:** the sections from `## Workflow` to `## Defect Key` are the `body_header` the "
            "fingerprint call printed, copied exactly as printed.") in _read(SHARED_HEALTH_CHECK)


def test_the_environment_rows_are_the_same_in_the_step_the_template_and_the_docs():
    """What gets sent is one list: the step's body, the issue template and the docs' "What gets sent" table."""
    def rows(table: str) -> list[str]:
        return [line.split("|")[1].strip() for line in table.splitlines()
                if line.startswith("|") and not set(line) <= set("|- ")]

    step = _slice(_read(SHARED_HEALTH_CHECK), "## Environment\n", "```\n")
    template = _read(ISSUE_TEMPLATE).split("## Environment\n", 1)[1]
    docs = _slice(_read(WORKFLOWS_DOC), "### What gets sent", "### The review gate")
    expected = ["Field", "Date", "OS", "AI Editor", "Model", "Forge Tier", "Run Mode", "SKF Version"]
    assert rows(step) == expected
    assert rows(template) == expected
    assert rows(docs) == ["Field", *expected[1:]]
    assert "| Run Mode | {interactive or headless} |" in step


def test_the_issue_template_records_every_fingerprint_input():
    template = _read(ISSUE_TEMPLATE)
    headings = _headings(template)
    order = ["## Workflow", "## Step File", "## Section", "## Severity", "## Fingerprint", "## Defect Key",
             "## Finding"]
    assert [h for h in headings if h in order] == order
    flow = _flow(template)
    assert 'first 7 hex chars of sha1("severity|workflow|step_file|section-slug|defect-key")' in flow
    assert "compute it from those five fields" in flow
    fingerprint = _flow(_slice(template, "## Fingerprint", "## Defect Key"))
    assert "Section fingerprint: `fp-XXXXXXX`" in fingerprint
    assert "write it here only, never as a label" in fingerprint
    defect = _flow(_slice(template, "## Defect Key", "## Finding"))
    for needle in (
        "One to four lower-case ASCII words joined by hyphens that name the thing the fix would change",
        "the most specific script (by its file name), function, script subcommand, field, flag or rule the fix would "
        "edit",
        "split at underscores, dots and case changes, leading dashes, a path, an extension and a line suffix dropped "
        "(`floor_check` gives `floor-check`, `scripts/gate_eval.py:42` gives `gate-eval`)",
        "For a missing rule, name the case it should cover in two to four of the step file's words, never the "
        "section's subject alone.",
        "Never a line number, a severity or words from your session's story.",
    ):
        assert needle in defect, needle
    assert "file name, severity" not in defect
    # A manual filer computes the fields with the helper, and needs no push access for the labels.
    assert ("uv run src/shared/scripts/skf-health-check-seen.py fingerprint --severity <severity> --workflow "
            "<workflow> --step-file <file>.md --stdin < names.json") in fingerprint
    assert ("Without push access you cannot set labels: the dedup Action reads this section and the Severity one, adds "
            "the labels, and links your report to any existing canonical issue.") in fingerprint
    assert "`src/skf-<name>/references/<file>.md`" in template and "skf-{workflow}" not in template
    # The examples the template gives are what the helper gives.
    helper = _helper()
    for name, key in (("floor_check", "floor-check"), ("scripts/gate_eval.py:42", "gate-eval")):
        assert helper.defect_key(name) == key
    assert helper.section_slug("### 5a. Live-Submit Path") == "live-submit-path"
    assert "`### 5a. Live-Submit Path` gives `live-submit-path`" in _flow(_slice(template, "## Section", "## Severity"))


def test_the_docs_state_the_keyed_fingerprint():
    bullet = next(line for line in _read(WORKFLOWS_DOC).splitlines() if line.startswith("- **Fingerprint dedup.**"))
    assert "a `sha1` hash of `severity|workflow|step_file|section|defect-key`" in bullet
    assert ("Two reports of the same defect that name the same thing get the same fingerprint, and two different "
            "defects in one section get different ones.") in bullet
    assert "Two reports of the same defect name the same thing" not in bullet
    assert "not an LLM similarity judgment" in bullet
    assert ("Ferris then names the defect more specifically, since an issue under the same fingerprint would be "
            "closed as a duplicate") in bullet
    assert "Ferris searches for the section fingerprint" in bullet
    assert "including one that named the same defect differently" in bullet
    assert "each is a possible match only" in bullet
    assert "safe but unlinked" not in bullet
    assert ("The repository's dedup Action flags it: when another open issue records the same section fingerprint "
            "under a different defect key, it links each one in a comment and adds the `possible-duplicate` label, "
            "and leaves the issue open for a maintainer to decide.") in bullet
    cache = next(line for line in _read(WORKFLOWS_DOC).splitlines() if line.startswith("- **Global seen-cache.**"))
    assert ("A record written by an SKF version whose fingerprints carry no defect key never suppresses on its own, "
            "since it may be another defect's: Ferris shows you its issue as a possible match while it is open, links "
            "a fixed one as a possible regression without the REGRESSION title marker, and records your choice under "
            "the new fingerprint.") in cache


# ---------------------------------------------------------------- the dedup Action

# Runs the Action's script with a stubbed `github` client, the way actions/github-script does: as the body of an
# async function given `github`, `context` and `core`. Every write call is recorded; nothing reaches GitHub.
_NODE_RUNNER = r"""
const fs = require('fs');
const [scriptPath, scenarioPath] = process.argv.slice(2);
const script = fs.readFileSync(scriptPath, 'utf8');
const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
const calls = [];
const withLabels = i => ({ ...i, labels: (i.labels || []).map(name => ({ name })) });
const open = scenario.open.map(withLabels);
const listForRepo = async ({ labels }) => {
  const want = labels.split(',');
  return { data: open.filter(i => want.every(w => i.labels.some(l => l.name === w))) };
};
const current = { state: 'open', ...withLabels(scenario.issue), ...(scenario.issue.state ? { state: scenario.issue.state } : {}) };
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: {
    issues: {
      get: async p => ({ data: p.issue_number === current.number ? current : null }),
      listForRepo,
      createComment: async p => { calls.push(['comment', p.issue_number, p.body]); },
      addLabels: async p => { calls.push(['label', p.issue_number, p.labels]); },
      update: async p => { calls.push(['update', p.issue_number, p.state, p.state_reason]); },
      createLabel: async p => {
        calls.push(['createLabel', p.name]);
        if (scenario.labelExists) { const e = new Error('exists'); e.status = 422; throw e; }
      },
    },
    reactions: { createForIssue: async p => { calls.push(['react', p.issue_number, p.content]); } },
  },
};
// The payload is the snapshot the event carried, open and with no labels: the Action must read the issue itself.
const payload = { action: scenario.event || 'opened', issue: { number: scenario.issue.number, state: 'open', labels: [] } };
if (scenario.label) payload.label = { name: scenario.label };
const context = { payload, repo: { owner: 'o', repo: 'r' } };
const core = { info: () => {} };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('github', 'context', 'core', script)(github, context, core)
  .then(() => process.stdout.write(JSON.stringify(calls)))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

NEW_FP, OTHER_FP, SECTION_FP = "fp-1111111", "fp-2222222", "fp-3333333"


def _body(section_fp: str | None) -> str:
    return "## Fingerprint\n`fp-x`\n\n" + (f"Section fingerprint: `{section_fp}`\n" if section_fp else "") + "\n## Finding\n"


def _issue(number: int, fp: str, section_fp: str | None, *extra: str) -> dict:
    return {"number": number, "labels": ["health-check", fp, *extra], "body": _body(section_fp)}


def _script() -> str:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(_read(DEDUP_WORKFLOW))["jobs"]["dedup"]["steps"][0]["with"]["script"]


def _run_dedup(tmp_path: pathlib.Path, issue: dict, others: list[dict], label_exists: bool = False,
               event: str = "opened", label: str | None = None) -> list:
    (tmp_path / "script.js").write_text(_script(), encoding="utf-8")
    (tmp_path / "runner.js").write_text(_NODE_RUNNER, encoding="utf-8")
    scenario = {"issue": issue, "open": [issue, *others], "labelExists": label_exists, "event": event,
                "label": label}
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    done = subprocess.run(["node", str(tmp_path / "runner.js"), str(tmp_path / "script.js"),
                           str(tmp_path / "scenario.json")], capture_output=True, text=True, encoding="utf-8",
                          timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="the Action's script runs under node")


@needs_node
def test_the_action_still_closes_an_exact_fingerprint_match(tmp_path):
    calls = _run_dedup(tmp_path, _issue(20, NEW_FP, SECTION_FP), [_issue(10, NEW_FP, SECTION_FP)])
    assert ["update", 20, "closed", "not_planned"] in calls
    assert ["react", 10, "+1"] in calls
    assert not any(c[0] == "label" and c[2] == ["possible-duplicate"] for c in calls)


@needs_node
def test_the_action_flags_an_open_issue_with_the_same_section_fingerprint_and_another_key(tmp_path):
    calls = _run_dedup(tmp_path, _issue(20, NEW_FP, SECTION_FP),
                       [_issue(10, OTHER_FP, SECTION_FP), _issue(12, "fp-4444444", "fp-5555555")])
    comments = [c for c in calls if c[0] == "comment"]
    assert len(comments) == 1 and comments[0][1] == 20
    assert comments[0][2].startswith(f"Possible duplicate of #10: same section fingerprint `{SECTION_FP}`")
    assert "#12" not in comments[0][2]
    assert ["label", 20, ["possible-duplicate"]] in calls
    assert ["createLabel", "possible-duplicate"] in calls
    assert not any(c[0] in ("update", "react") for c in calls), "a possible match closes and upvotes nothing"
    # The label that stops a later run goes on before the comment, so a failed label call leaves no comment to repeat.
    assert [c[0] for c in calls] == ["createLabel", "label", "comment"]


@needs_node
def test_the_action_flags_a_keyless_issue_whose_label_is_the_section_fingerprint(tmp_path):
    # An issue filed by an SKF version without the defect key carries the section fingerprint as its label.
    calls = _run_dedup(tmp_path, _issue(20, NEW_FP, SECTION_FP), [_issue(7, SECTION_FP, None)], label_exists=True)
    assert any(c[0] == "comment" and c[2].startswith("Possible duplicate of #7:") for c in calls)
    assert ["label", 20, ["possible-duplicate"]] in calls


@needs_node
def test_the_action_flags_a_keyed_issue_for_a_new_keyless_one(tmp_path):
    # A report filed without the key: its label is its section fingerprint, which a keyed issue records in its body.
    calls = _run_dedup(tmp_path, _issue(20, SECTION_FP, None), [_issue(10, OTHER_FP, SECTION_FP)])
    assert any(c[0] == "comment" and c[2].startswith(f"Possible duplicate of #10: same section fingerprint "
                                                     f"`{SECTION_FP}`") for c in calls)


@needs_node
def test_the_action_does_nothing_without_a_shared_section_or_once_flagged(tmp_path):
    assert _run_dedup(tmp_path, _issue(20, NEW_FP, SECTION_FP), [_issue(10, OTHER_FP, "fp-5555555")]) == []
    flagged = _issue(20, NEW_FP, SECTION_FP, "possible-duplicate")
    assert _run_dedup(tmp_path, flagged, [_issue(10, OTHER_FP, SECTION_FP)]) == []


@needs_node
def test_a_later_run_for_an_issue_already_closed_does_nothing(tmp_path):
    # GitHub sends `opened` and a `labeled` event per label, so the job runs several times for one issue.
    closed = {**_issue(20, NEW_FP, SECTION_FP), "state": "closed"}
    assert _run_dedup(tmp_path, closed, [_issue(10, NEW_FP, SECTION_FP)]) == []


@needs_node
def test_two_reports_filed_together_close_only_the_later(tmp_path):
    """#10 and #12 opened together with one fingerprint: #12 closes into #10, and #10's own run closes nothing, so
    neither closes the other."""
    calls = _run_dedup(tmp_path, _issue(12, NEW_FP, SECTION_FP), [_issue(10, NEW_FP, SECTION_FP)])
    assert calls == [["comment", 12, calls[0][2]], ["label", 12, ["duplicate"]], ["update", 12, "closed", "not_planned"],
                     ["react", 10, "+1"]]
    assert calls[0][2].startswith(f"Auto-deduped: same fingerprint `{NEW_FP}` as #10.")
    assert _run_dedup(tmp_path, _issue(10, NEW_FP, SECTION_FP), [_issue(12, NEW_FP, SECTION_FP)]) == []


@needs_node
def test_only_the_later_of_two_reports_is_flagged(tmp_path):
    older, newer = _issue(9, OTHER_FP, SECTION_FP), _issue(12, NEW_FP, SECTION_FP)
    assert _run_dedup(tmp_path, older, [newer]) == []
    assert [c[0] for c in _run_dedup(tmp_path, newer, [older])] == ["createLabel", "label", "comment"]


@needs_node
@pytest.mark.parametrize("label", ["confirmed", "possible-duplicate", "duplicate", "bug", "fp-123"])
def test_a_labeled_event_for_any_other_label_does_nothing(tmp_path, label):
    """A maintainer reopened a duplicate, or removed `possible-duplicate`, then triaged the issue with a label."""
    assert _run_dedup(tmp_path, _issue(12, NEW_FP, SECTION_FP), [_issue(10, NEW_FP, SECTION_FP)], event="labeled",
                      label=label) == []
    assert _run_dedup(tmp_path, _issue(12, NEW_FP, SECTION_FP), [_issue(9, SECTION_FP, None)], event="labeled",
                      label=label) == []


@needs_node
@pytest.mark.parametrize("label", ["health-check", NEW_FP])
def test_a_labeled_event_for_health_check_or_a_fingerprint_acts(tmp_path, label):
    calls = _run_dedup(tmp_path, _issue(12, NEW_FP, SECTION_FP), [_issue(10, NEW_FP, SECTION_FP)], event="labeled",
                       label=label)
    assert ["update", 12, "closed", "not_planned"] in calls and ["react", 10, "+1"] in calls


@needs_node
@pytest.mark.parametrize("event", ["edited", "reopened"])
def test_another_event_does_nothing(tmp_path, event):
    assert _run_dedup(tmp_path, _issue(12, NEW_FP, SECTION_FP), [_issue(10, NEW_FP, SECTION_FP)], event=event) == []


# ---------------------------------------------------------------- a report filed without labels

SEVERITIES = ("bug", "friction", "gap")
BARE_FP = "fp-1234abc"


def _bare(number: int, title: str, body: str, *labels: str) -> dict:
    """An issue as GitHub files it for a reporter without push access: no label they passed survives."""
    return {"number": number, "title": title, "body": body, "labels": list(labels)}


def _labeled(number: int, *labels: str) -> list:
    return ["label", number, list(labels)]


def _skf_title(severity: str, fp: str, regression: bool = False) -> str:
    """SKF's title as §5a-ii's create command takes it from the helper: `{title}`, or `{regression_title}` after a
    regression, whose marker comes before the description."""
    text = _read(SHARED_HEALTH_CHECK)
    command = _slice(text, "**Then create the issue:**", "When sub-step 1 returned `regression`, put")
    (template,) = re.findall(r'--title "([^"]+)"', command)
    assert template == "{title}"
    assert "put `{regression_title}` in that `--title` value in place of `{title}`" in _flow(text)
    prefix = _helper().title_prefix(severity, fp, "skf-test-skill")
    description = "inventory-contract names no rule for a const holding a function"
    return prefix + ("REGRESSION: " if regression else "") + description


def _skf_body(severity: str, fp: str, section_fp: str) -> str:
    """SKF's issue body as the body format writes it, its machine-read fields filled in."""
    body = _slice(_read(SHARED_HEALTH_CHECK), "**Issue body format:**", "\n```\n")
    body = body.split("```markdown\n", 1)[1] + "\n"
    for placeholder, value in {"{workflow}": "skf-test-skill",
                               "{step_file}": "src/skf-test-skill/references/inventory-contract.md",
                               "{section-slug}": "documented-inventory-contract", "{bug | friction | gap}": severity,
                               "{fp}": fp, "{legacy_fp}": section_fp, "{defect-key}": "const-holding-function"}.items():
        assert placeholder in body, placeholder
        body = body.replace(placeholder, value)
    return body


def _template(fp: str | None = None, severity: str | None = None, section_fp: str | None = None) -> str:
    """The issue template's body as a reporter submits it, with the given fields filled in."""
    text = _read(ISSUE_TEMPLATE).split("---\n", 2)[2]
    for value, old, new in (
        (fp, "`fp-XXXXXXX`\n\nSection fingerprint:", f"`{fp}`\n\nSection fingerprint:"),
        (section_fp, "Section fingerprint: `fp-XXXXXXX`", f"Section fingerprint: `{section_fp}`"),
        (severity, "covered at all -->\n", f"covered at all -->\n`{severity}`\n"),
    ):
        if value:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
    return text


def _title_re() -> re.Pattern:
    """The Action's title regex, as a Python pattern (the JS literal uses only syntax both share)."""
    match = re.search(r"const title = /(.+)/i\.exec", _script())
    assert match, "the Action reads the title with a case-blind regex literal"
    return re.compile(match.group(1), re.IGNORECASE)


@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("regression", [False, True], ids=["title", "regression-title"])
def test_skfs_titles_match_the_actions_title_regex(severity, regression):
    title = _skf_title(severity, BARE_FP, regression)
    assert ("] skf-test-skill: REGRESSION: " in title) is regression
    match = _title_re().match(title)
    assert match and match.groups() == (severity, BARE_FP), title
    assert title.startswith("[health-check]"), "the job's own filter lets it through"


@needs_node
@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("regression", [False, True], ids=["title", "regression-title"])
@pytest.mark.parametrize("label_exists", [False, True], ids=["new-label", "label-exists"])
def test_a_report_filed_without_labels_is_labeled_from_skfs_title(tmp_path, severity, regression, label_exists):
    """The create retried without --label (no push access): a 422 on the fp-* label, which exists, is no error."""
    issue = _bare(12, _skf_title(severity, BARE_FP, regression), _skf_body(severity, BARE_FP, SECTION_FP))
    calls = _run_dedup(tmp_path, issue, [], label_exists=label_exists)
    assert calls == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", severity, BARE_FP)]


@needs_node
def test_the_title_is_read_whatever_its_case(tmp_path):
    calls = _run_dedup(tmp_path, _bare(12, "[Health-Check][Bug][FP-1234ABC] skf-setup: x", ""), [])
    assert calls == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", "bug", BARE_FP)]


@needs_node
@pytest.mark.parametrize("severity", SEVERITIES)
def test_skfs_body_alone_is_read_by_the_action(tmp_path, severity):
    """Under a title the Action cannot read, the body's Fingerprint and Severity sections give the labels."""
    calls = _run_dedup(tmp_path, _bare(12, "[health-check] x", _skf_body(severity, BARE_FP, SECTION_FP)), [])
    assert calls == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", severity, BARE_FP)]


@needs_node
@pytest.mark.parametrize("crlf", [False, True], ids=["lf", "crlf"])
def test_a_template_filing_whose_labels_were_dropped_is_labeled_from_its_body(tmp_path, crlf):
    body = _template(fp=BARE_FP, severity="bug", section_fp=SECTION_FP)
    calls = _run_dedup(tmp_path, _bare(12, "[health-check] x", body.replace("\n", "\r\n") if crlf else body), [])
    assert calls == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", "bug", BARE_FP)]


@needs_node
@pytest.mark.parametrize("body", [
    "## Fingerprint\n`fp-XXXXXXX`\n\nSection fingerprint: `fp-3333333`\n\n## Severity\nbug\n",
    "## Fingerprint\n`fp-XXXXXXX`\n**Section fingerprint:** `fp-3333333`\n",
    "## Fingerprint\n`fp-XXXXXXX`\n\n## Finding\nSee `fp-1234abc`.\n",
    "SPLIT-TEMPLATE-SECTION-ONLY",
    "SPLIT-TEMPLATE-UNFILLED",
], ids=["section-line", "bold-section-line", "fp-elsewhere", "template-section-only", "template-unfilled"])
@pytest.mark.parametrize("labels", [(), ("health-check", "workflow-improvement")], ids=["bare", "template-labels"])
def test_neither_the_section_line_nor_the_placeholder_is_ever_taken(tmp_path, body, labels):
    body = {"SPLIT-TEMPLATE-SECTION-ONLY": _template(severity="bug", section_fp=SECTION_FP),
            "SPLIT-TEMPLATE-UNFILLED": _template()}.get(body, body)
    assert _run_dedup(tmp_path, _bare(12, "[health-check] x", body, *labels), [_issue(9, SECTION_FP, None)]) == []


@needs_node
@pytest.mark.parametrize("body", [
    f"## Fingerprint\n`{BARE_FP}`\n\n## Finding\nOne sentence.\n",
    f"## Severity\n\n## Fingerprint\n`{BARE_FP}`\n",
    f"## Severity\nbug or gap\n\n## Fingerprint\n`{BARE_FP}`\n",
    f"## Severity\nA bug, I think\n\n## Fingerprint\n{BARE_FP}\n",
], ids=["no-section", "empty-section", "two-severities", "a-sentence"])
def test_a_report_with_no_severity_gets_no_severity_label(tmp_path, body):
    """No null label: the labels the report lacks, without a severity it does not name."""
    calls = _run_dedup(tmp_path, _bare(12, "[health-check] x", body), [])
    assert calls == [["createLabel", BARE_FP], ["label", 12, ["health-check", "workflow-improvement", BARE_FP]]]


@needs_node
@pytest.mark.parametrize("line", ["`FP-1234ABC`", "Fp-1234AbC", "  `fp-1234ABC`  "])
def test_the_bodys_fingerprint_is_read_whatever_its_case(tmp_path, line):
    """Case-blind, as the title is, and labelled in lower case."""
    body = f"## Severity\n`gap`\n\n## Fingerprint\n{line}\n\nSection fingerprint: `{SECTION_FP}`\n"
    calls = _run_dedup(tmp_path, _bare(12, "[health-check] x", body), [])
    assert calls == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", "gap", BARE_FP)]


@needs_node
def test_a_report_labeled_from_its_title_then_closes_as_a_duplicate(tmp_path):
    earlier = _issue(9, BARE_FP, SECTION_FP)
    calls = _run_dedup(tmp_path, _bare(12, _skf_title("bug", BARE_FP), _skf_body("bug", BARE_FP, SECTION_FP)),
                       [earlier])
    assert calls[:2] == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", "bug", BARE_FP)]
    assert [c[:2] for c in calls[2:]] == [["comment", 12], ["label", 12], ["update", 12], ["react", 9]]


@needs_node
def test_a_report_labeled_from_its_title_is_then_flagged(tmp_path):
    keyless = _issue(9, SECTION_FP, None)
    calls = _run_dedup(tmp_path, _bare(12, _skf_title("gap", BARE_FP), _skf_body("gap", BARE_FP, SECTION_FP)),
                       [keyless])
    assert calls[:2] == [["createLabel", BARE_FP], _labeled(12, "health-check", "workflow-improvement", "gap", BARE_FP)]
    assert [c[0] for c in calls[2:]] == ["createLabel", "label", "comment"]
    assert calls[3] == ["label", 12, ["possible-duplicate"]]


@needs_node
def test_only_the_missing_labels_are_added(tmp_path):
    issue = _bare(12, _skf_title("bug", BARE_FP), "", "health-check", "bug")
    assert _run_dedup(tmp_path, issue, []) == [["createLabel", BARE_FP], _labeled(12, "workflow-improvement", BARE_FP)]


@needs_node
def test_a_labeled_report_gets_no_label_call(tmp_path):
    """The labels went on with the issue: the title is never read, even when it names another fingerprint."""
    issue = {**_issue(12, NEW_FP, SECTION_FP), "title": _skf_title("bug", BARE_FP)}
    assert _run_dedup(tmp_path, issue, []) == []


def test_the_job_runs_for_a_health_check_label_or_title():
    """A report filed without labels carries only the title the health check writes."""
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(_read(DEDUP_WORKFLOW))["jobs"]["dedup"]["if"] == (
        "contains(github.event.issue.labels.*.name, 'health-check') "
        "|| startsWith(github.event.issue.title, '[health-check]')")


def test_runs_for_one_issue_never_overlap():
    yaml = pytest.importorskip("yaml")
    job = yaml.safe_load(_read(DEDUP_WORKFLOW))["jobs"]["dedup"]
    assert job["concurrency"] == {"group": "health-check-dedup-${{ github.event.issue.number }}",
                                  "cancel-in-progress": False}


def test_the_action_header_says_it_flags_and_never_closes_a_section_match():
    header = _flow(re.sub(r"^#\s?", "", _read(DEDUP_WORKFLOW).split('"on":', 1)[0], flags=re.MULTILINE))
    assert "adds the `possible-duplicate` label" in header
    assert "It closes nothing on that match" in header
    assert "numbered below this one" in header
    assert "client-side dedup in src/shared/health-check.md" in header


def test_the_action_header_says_a_report_without_labels_is_labeled():
    header = _flow(re.sub(r"^#\s?", "", _read(DEDUP_WORKFLOW).split('"on":', 1)[0], flags=re.MULTILINE))
    assert "or whose title starts with `[health-check]`" in header
    assert ("Acts on the `opened` event, and on a `labeled` event only when the label added is `health-check` or an "
            "`fp-XXXXXXX` fingerprint") in header
    assert "`[health-check][{severity}][{fp}] ...`, or else from the body's `## Fingerprint` and `## Severity`" in header
    assert "never from a `Section fingerprint:` line or the template's `fp-XXXXXXX` placeholder" in header
