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
runs the step prose, so these checks pin it. The hashes, the seen-cache
verdicts and its merge are skf-health-check-seen.py's (#1122), whose
behaviour test-skf-health-check-seen.py pins.
"""

from __future__ import annotations

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

SUB_STEP_1 = "**1. Compute the fingerprint**"
SUB_STEP_2 = "**2. Check the local seen-cache**"
SUB_STEP_3 = "**3. Check GitHub CLI availability**"
SUB_STEP_4 = "**4. Remote dedup search**"
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


# ---------------------------------------------------------------- the formula


def test_the_fingerprint_hashes_the_defect_key():
    text = _read(SHARED_HEALTH_CHECK)
    table = _slice(text, "### 3. Present Findings", "**What happened:**")
    assert ('| **Fingerprint** | `fp-{7-hex}`: first 7 hex chars of '
            '`sha1("{severity}|{workflow}|{step_file}|{section-slug}|{defect-key}")`, ') in table
    assert "| **Defect Key** | `{defect-key}`:" in table
    assert "from §5a sub-step 1's `fingerprint` call (`N/A` when SKF's health-check helper is missing)" in table
    step = _slice(text, SUB_STEP_1, SUB_STEP_2)
    # The helper hashes both (test-skf-health-check-seen.py runs this call); the step only names its inputs.
    assert ('uv run {seenCacheHelper} fingerprint --severity "{severity}" --workflow "{workflow}" '
            '--step-file "{step_file}" --section "{section-slug}" --defect-key "{defect-key}"') in step
    flow = _flow(step)
    assert ("`{fp}` is `fp-` and the first 7 hex characters of "
            "`sha1(\"{severity}|{workflow}|{step_file}|{section-slug}|{defect-key}\")`, and `{legacy_fp}` the same "
            "hash without `|{defect-key}`.") in flow
    # No formula anywhere in the file leaves the key out.
    assert "|{section-slug}\")" not in text and "section-slug)[:7]" not in text


def test_the_defect_key_rule_says_how_to_pick_it():
    rule = _flow(_slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_1, SUB_STEP_2))
    for needle in (
        "one to four lower-case ASCII words joined by hyphens that name the thing the fix would change",
        "in the step file's or the code's own words",
        "Pick the most specific name the fix would edit.",
        "When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two "
        "to four of the step file's own words, the noun the rule would be about, then what makes the case distinct.",
        "`floor_check` gives `floor-check`",
        "`--orphan-action` flag gives `orphan-action`",
        "gives `const-holding-function`",
        "Never use a line number, a file name or path (the step file already says where), a severity, or words from "
        "this session's own story",
        "whoever reports the same defect next must reach the same key from the source alone",
        "Never use the section's own subject alone either: every defect in the section shares it.",
    ):
        assert needle in rule, needle
    # A fallback to the section's subject gives every such report in a section one key, the merge the key ends.
    assert "use the section's own subject." not in rule


def _to_key(name: str) -> str:
    """The doc's conversion, as written: drop leading dashes and underscores; split at spaces, underscores,
    hyphens, dots and each lower-case letter followed by an upper-case one; drop every character of a word that is
    not an ASCII letter or digit; lower-case; keep the last four."""
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name.lstrip("-_"))
    words = [re.sub(r"[^A-Za-z0-9]", "", w).lower() for w in re.split(r"[ _.\-]+", name)]
    return "-".join([w for w in words if w][-4:])


def test_the_defect_key_conversion_gives_the_examples_keys():
    rule = _flow(_slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_1, SUB_STEP_2))
    assert ("To turn a name into the key, drop its leading dashes and underscores, split it at spaces, underscores, "
            "hyphens, dots and each lower-case letter followed by an upper-case one, drop every character of each word "
            "that is not an ASCII letter or digit, lower-case each word and join them with hyphens (`composeStories` "
            "gives `compose-stories`, `reader's own code` gives `readers-own-code`); a name of more than four words "
            "keeps its last four.") in rule
    for name, key in (("floor_check", "floor-check"), ("--orphan-action", "orphan-action"),
                      ("composeStories", "compose-stories"), ("const holding function", "const-holding-function"),
                      ("_declared_names", "declared-names"), ("cognee.agents.get", "cognee-agents-get"),
                      ("a_very_long_helper_name", "very-long-helper-name"),
                      # Two independent reports of one defect wrote these two (PR #982's key-stability measurement).
                      ("reader's own code", "readers-own-code"), ("readers own code", "readers-own-code")):
        assert _to_key(name) == key, name
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
    calls = re.findall(r"^uv run \{seenCacheHelper\} (\w+) ", text, re.MULTILINE)
    # §5a-i and §5b each have a plain record call and one with --regression.
    assert calls == ["fingerprint", "lookup", "record", "record", "record", "record"], calls
    frontmatter = text.split("\n---\n", 1)[0]
    assert ("seenCacheProbeOrder:\n  - '{project-root}/_bmad/skf/shared/scripts/skf-health-check-seen.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-health-check-seen.py'\n") in frontmatter + "\n"
    assert "seenCachePath: '$HOME/.skf/health-check-seen.json'" in frontmatter
    step = _flow(_slice(text, SUB_STEP_1, SUB_STEP_2))
    assert "Resolve `{seenCacheHelper}` from `{seenCacheProbeOrder}`; first existing path wins." in step
    # No helper, no hand-rolled fallback: the findings stay local, with their own reason.
    assert ("If no candidate exists, give each finding the fingerprint `N/A`, and send every finding that §4 does not "
            "discard to the local queue (§5c) with the missing-helper reason instead of submitting it: there is no "
            "fallback.") in step
    assert ("so neither fingerprint is hashed by hand and `{seenCachePath}` is never read or written by hand."
            in step)
    assert ("makes the call exit 2 and print one `{\"status\": \"error\", \"message\": ...}` line on stderr that names "
            "the rule") in step
    assert "Fix that value by its rule and run the call again." in step
    # A call the helper never answered (uv or Python could not start it) is a missing helper, not a value to fix.
    assert ("A call that prints no JSON on stdout and no such line on stderr did not run the helper (uv or Python could "
            "not start it, and uv's own errors exit 2 as well): treat it as a missing helper, so the finding gets the "
            "fingerprint `N/A` and goes to the local queue (§5c) with the missing-helper reason.") in step
    queue = _flow(_slice(text, "### 5c.", "**{N} finding(s) saved locally:**"))
    assert "gh unavailable, SKF's health-check helper missing," in queue
    assert "write `N/A` as the `fingerprint` here" in queue
    assert '"SKF\'s health-check helper is missing; re-install SKF to submit these."' in queue


# ---------------------------------------------------------------- the legacy fallback


def test_the_seen_cache_falls_back_to_the_legacy_fingerprint():
    text = _read(SHARED_HEALTH_CHECK)
    raw = _slice(text, SUB_STEP_2, SUB_STEP_3)
    assert 'uv run {seenCacheHelper} lookup --fp "{fp}" --legacy-fp "{legacy_fp}"' in raw
    step = _flow(raw)
    assert "If the call fails or prints no JSON, continue as `unseen`: this check never halts a run." in step
    assert ("The helper looks up `{fp}`, and only when the cache has no record for it, `{legacy_fp}`, then works its "
            "branches on the record found.") in step
    # One line per verdict the helper prints, in its branch order, each saying what comes next.
    verdicts = re.findall(r"^- `([a-z-]+)`: ", raw, re.MULTILINE)
    assert verdicts == ["unseen", "handled", "regression", "possible-regression", "unrecognized"]
    for needle in (
        "- `unseen`: no record under either fingerprint, or a record found only under `{legacy_fp}` (`matched_on` is "
        "`legacy_fp`) that would have suppressed. That record was written by an SKF version without the defect key",
        "so it may be another defect's: log `\"{fp}: legacy record {legacy_fp} may be another defect, reporting\"`",
        "sub-step 4 still offers its issue while that issue is open. Go to sub-step 3.",
        "- `possible-regression`: the same, found only under `{legacy_fp}`, so what was fixed may be another defect "
        "in this section. Go to sub-step 3 and apply the possible-regression treatment below.",
        "- `regression`: a record under `{fp}` marked `resolved` by hand when the defect was fixed, or whose issue was "
        "closed as completed",
        "was closed as not planned (how the dedup Action closes a duplicate and a maintainer closes a wontfix, neither "
        "of them a fix)",
    ):
        assert needle in step, needle
    # What the old prose said around the branches stays.
    assert ("**Presence in the cache is not the verdict.** A fingerprint whose defect was already fixed must NOT "
            "suppress: a fresh sighting of a fixed defect is a *regression*") in step
    assert "**`handled` is the only verdict that suppresses.**" in step


def test_a_legacy_regression_is_only_a_possible_one():
    text = _read(SHARED_HEALTH_CHECK)
    treatment = _flow(_slice(text, "**Possible regression** (verdict `possible-regression` only).",
                             "**What this does and does not catch.**"))
    assert "`Possibly a regression of {issue_url}, resolved {date}:" in treatment
    assert "Leave the title unmarked" in treatment
    # The title marker stays with `regression` alone.
    create = _flow(_slice(text, SUB_STEP_5A_II, "**Writing rules"))
    assert "When sub-step 2 returned `regression`, append" in create
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
    assert ("Each issue this second search finds is a possible match: it was filed by an SKF version whose "
            "fingerprints carry no defect key, or it reports a defect of this severity in this section under another "
            "defect key.") in flow
    assert "the user decides at 5a-i" in flow


def test_a_keyless_fingerprint_is_not_dated_to_this_change():
    """Older SKF installs keep filing keyless fingerprints after this ships."""
    text = _flow(_read(SHARED_HEALTH_CHECK))
    assert "filed before fingerprints carried a defect key" not in text
    assert "made before the key existed" not in text
    assert "Issues and seen-cache records made by an SKF version without the key carry it" in text


def test_a_legacy_match_goes_to_the_users_choice():
    choice = _flow(_slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II))
    assert ("When the issues were found by `{legacy_fp}`, list each one and present the same options under this "
            "opening instead") in choice
    assert '"**Possible match:** #{N}: {title} (one line for each issue found)' in choice
    assert "it was filed by an SKF version whose fingerprints carry no defect key, or it reports a defect in this " \
           "section under another defect key" in choice
    assert "naming it when more than one is listed, and **\\[N]** if none does" in choice
    for option in ("**\\[R]**", "**\\[C]**", "**\\[N]**", "**\\[S]**"):
        assert option in choice, option
    # Headless never reaches it; a run with nobody to ask never acts on a guess.
    assert "Only the user decides a possible match." in choice
    assert "A headless run never reaches this choice, because §4 queues its findings locally" in choice
    assert ("A run that reaches it with no user to ask takes **\\[S]**, so the finding goes to the local queue (§5c) "
            "with the possible-match reason") in choice
    # #1202: only a reaction or comment that posted is recorded (test-skf-health-check-gh-calls.py pins the rest).
    assert ("When every call of **R** or **C** succeeded, record the outcome under `{fp}`, also when the match was "
            "found by `{legacy_fp}`: `reacted` after **R** and `commented` after **C**") in choice
    raw = _slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II)
    reaction = ('uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" '
                '--date "{today}"')
    assert f"{reaction}\n" in raw and f"{reaction} --regression\n" in raw
    # After a regression verdict, a plain call leaves the hand-written `resolved` record in place, so every later
    # session would get `regression` again and ask about the same open issue (#1122, review loop 1).
    assert ("When sub-step 2 returned `regression`, run this one instead: **R** or **C** says this open issue reports "
            "the defect, so it now tracks the recurrence and replaces the `resolved` record the fix left under "
            "`{fp}`.") in choice
    assert "**S** records nothing, and **N** records its new issue in §5b." in choice
    assert "Read what the call prints as §5b says; if it fails, log its stderr message and go on." in choice


def test_new_at_an_exact_match_names_the_defect_more_specifically():
    """The issue 5a-ii creates carries the `{fp}` label, which the dedup Action closes as a duplicate of the
    open match: [N] there has to change the key first. A possible match carries another label."""
    choice = _flow(_slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II))
    assert ("**N:** After a match found by `{fp}`: the open issue carries this same fingerprint, so a new issue "
            "under it would be closed as its duplicate. Choose a more specific defect key that names what sets this "
            "defect apart (the more specific name the fix edits, or the case it covers, still in the source's words), "
            "recompute `{fp}` with it, then proceed to step 5a-ii.") in choice
    assert ("After a possible match, proceed to step 5a-ii as is: that issue's `fp-*` label differs from `{fp}`."
            in choice)
    assert "- **N:** Proceed to step 5a-ii." not in choice
    action = _read(REPO / ".github" / "workflows" / "health-check-dedup.yaml")
    assert "labels: `health-check,${fpLabel}`" in action


def test_a_run_with_nobody_to_ask_queues_with_its_own_reason():
    text = _read(SHARED_HEALTH_CHECK)
    queue = _flow(_slice(text, "### 5c.", "**Filename:**"))
    assert "a run with no user to ask took **\\[S]** at a possible match" in queue
    reasons = _flow(_slice(text, "`{reason}` is the sentence", "**{N} finding(s) saved locally:**"))
    assert ('"These may match an open issue from the same section; review them before submitting." '
            "(the possible-match reason)") in reasons


def test_a_differently_named_report_is_safe_but_unlinked():
    caught = _flow(_slice(_read(SHARED_HEALTH_CHECK), "**What this does and does not catch.**", SUB_STEP_3))
    assert ("changes the fingerprint. So does a report that names the same defect by another thing than an earlier "
            "report did: independent reports of one defect often pick different keys.") in caught
    assert "safe but unlinked here; once it is filed, the dedup Action flags it (§5a-ii)." in caught


def test_the_step_says_the_action_flags_a_shared_section_fingerprint():
    filing = _flow(_slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_5A_II, "**Writing rules"))
    assert ("The dedup Action reads the body's `Section fingerprint:` line too. When the new issue matches no open "
            "issue's fingerprint but another open health-check issue records the same section fingerprint under a "
            "different defect key, or was filed without a key and carries it as its label, the Action comments with a "
            "link to each such issue and adds the `possible-duplicate` label. It closes nothing on that match") in filing


def test_the_seen_cache_is_written_under_the_new_fingerprint():
    text = _read(SHARED_HEALTH_CHECK)
    assert "After the issue is created, record it under `{fp}` as §5b says" in _flow(text)
    raw = _slice(text, "### 5b.", "### 5c.")
    created = 'uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}"'
    assert f"{created}\n" in raw and f"{created} --regression\n" in raw
    cache = _flow(raw)
    assert ("When sub-step 2 returned `regression`, run this one instead: the new issue tracks the recurrence, so it "
            "replaces the `resolved` record the fix left under `{fp}`.") in cache
    assert ("It writes under `{fp}` only: a record under `{legacy_fp}` stays exactly as it is, whatever its action"
            in cache)
    assert "It never downgrades a `resolved` record: without `--regression` it leaves one alone" in cache
    assert "It merges, never replaces: it sets the `{fp}` key alone and keeps every other fingerprint" in cache
    # A cache the helper set aside is named to the user, who can still copy its records back.
    assert ("When `set_aside` is not null, after this call or §5a-i's, tell the user that `{seenCachePath}` did not "
            "parse, so it was renamed to that path and a new cache was started, and that they keep its records by "
            "fixing that file and copying its entries into `{seenCachePath}`.") in cache
    # The vocabulary and the global-file note stay; the helper makes the folder, so the step does not.
    assert "**The `action` vocabulary is `created`, `reacted`, `commented`, `resolved`.**" in cache
    assert ("This file is global across the user's machine, not per-project, so the same defect is not re-reported "
            "across different repos the user works in while its issue stays open.") in cache
    assert "Ensure the parent directory exists." not in text


# ---------------------------------------------------------------- the issue body


def test_the_issue_body_records_every_fingerprint_input():
    text = _read(SHARED_HEALTH_CHECK)
    body = _slice(text, "**Issue body format:**", "### 5b.")
    headings = _headings(body)
    order = ["## Workflow", "## Step File", "## Section", "## Severity", "## Fingerprint", "## Defect Key",
             "## Finding"]
    assert [h for h in headings if h in order] == order
    assert "## Section\n`{section-slug}`\n" in body
    assert "## Defect Key\n`{defect-key}`\n" in body
    assert "sha1(severity|workflow|step_file|section-slug|defect-key)[:7]" in body
    # The section fingerprint rides in the body, where the fallback search reads it, and never as a label,
    # because the dedup Action takes the first `fp-*` label it finds.
    fingerprint = _slice(body, "## Fingerprint", "## Defect Key")
    assert "\nSection fingerprint: `{legacy_fp}`\n" in fingerprint
    assert "Body text only, never a label: the dedup Action reads it to flag possible duplicates." in fingerprint
    # The Action finds that line by the pattern the body writes it in, at the start of a line.
    assert "const SECTION_RE = /^Section fingerprint: `(fp-[0-9a-f]{7})`/m;" in _read(DEDUP_WORKFLOW)
    create = _slice(text, "**Then create the issue:**", "**Writing rules")
    assert '--label "health-check,workflow-improvement,{severity},{fp}"' in create
    assert "legacy_fp" not in create


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
        "the most specific function, script subcommand, field, flag or rule the fix would edit",
        "split at underscores, dots and case changes, leading dashes dropped (`floor_check` gives `floor-check`)",
        "For a missing rule, name the case it should cover in two to four of the step file's words, never the "
        "section's subject alone.",
        "Never a line number, file name, severity or words from your session's story.",
    ):
        assert needle in defect, needle


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
// The payload is the snapshot the event carried; the Action must read the issue's current state instead.
const context = { payload: { issue: { number: scenario.issue.number, labels: [] } }, repo: { owner: 'o', repo: 'r' } };
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


def _run_dedup(tmp_path: pathlib.Path, issue: dict, others: list[dict], label_exists: bool = False) -> list:
    yaml = pytest.importorskip("yaml")
    script = yaml.safe_load(_read(DEDUP_WORKFLOW))["jobs"]["dedup"]["steps"][0]["with"]["script"]
    (tmp_path / "script.js").write_text(script, encoding="utf-8")
    (tmp_path / "runner.js").write_text(_NODE_RUNNER, encoding="utf-8")
    scenario = {"issue": issue, "open": [issue, *others], "labelExists": label_exists}
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


def test_runs_for_one_issue_never_overlap():
    yaml = pytest.importorskip("yaml")
    job = yaml.safe_load(_read(DEDUP_WORKFLOW))["jobs"]["dedup"]
    assert job["concurrency"] == {"group": "health-check-dedup-${{ github.event.issue.number }}",
                                  "cancel-in-progress": False}


def test_the_action_header_says_it_flags_and_never_closes_a_section_match():
    header = _flow(re.sub(r"^#\s?", "", _read(DEDUP_WORKFLOW).split('"on":', 1)[0], flags=re.MULTILINE))
    assert "adds the `possible-duplicate` label" in header
    assert "It closes nothing on that match" in header
