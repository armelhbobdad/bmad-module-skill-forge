"""Prose-contract tests: a health-check fingerprint names the defect.

The dedup Action closes a newer open issue that carries an earlier open one's
`fp-*` label, so a fingerprint must tell two defects in one section apart.
It hashes the severity, workflow, step file, section slug and a defect key,
the name of the thing the fix would change, so two different defects of one
severity in one section (the only section of
skf-test-skill/references/inventory-contract.md, say) get two fingerprints,
while two reports of one defect still get one. Issues and seen-cache records
made before the key carry the legacy fingerprint, without it: the seen-cache
check and the remote search still look it up, but only as a possible match,
which never suppresses a finding or posts on an issue without the user's
pick. No test runs the step prose, so these checks pin it.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SHARED_HEALTH_CHECK = REPO / "src" / "shared" / "health-check.md"
ISSUE_TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md"
WORKFLOWS_DOC = REPO / "docs" / "workflows.md"

SUB_STEP_1 = "**1. Compute the fingerprint**"
SUB_STEP_2 = "**2. Check the local seen-cache**"
SUB_STEP_3 = "**3. Check GitHub CLI availability**"
SUB_STEP_4 = "**4. Remote dedup search**"
SUB_STEP_5A_II = "**5a-ii. If no matching open issue exists**"

# A sample finding: two different gaps in the only section of one step file.
SAMPLE = {
    "{severity}": "gap",
    "{workflow}": "skf-test-skill",
    "{step_file}": "src/skf-test-skill/references/inventory-contract.md",
    "{section-slug}": "documented-inventory-contract",
}
KEYS = ("function-valued-const", "type-only-name")


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


def _sha7(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]


def _hash_input(key: str | None) -> str:
    fields = [SAMPLE["{severity}"], SAMPLE["{workflow}"], SAMPLE["{step_file}"], SAMPLE["{section-slug}"]]
    return "|".join(fields + ([key] if key else []))


def _fill(template: str, key: str) -> str:
    for placeholder, value in {**SAMPLE, "{defect-key}": key}.items():
        template = template.replace(placeholder, value)
    assert "{" not in template, template
    return template


def _headings(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("## ")]


# ---------------------------------------------------------------- the formula


def test_the_fingerprint_hashes_the_defect_key():
    text = _read(SHARED_HEALTH_CHECK)
    table = _slice(text, "### 3. Present Findings", "**What happened:**")
    assert ('| **Fingerprint** | `fp-{7-hex}`: first 7 hex chars of '
            '`sha1("{severity}|{workflow}|{step_file}|{section-slug}|{defect-key}")` |') in table
    assert "| **Defect Key** | `{defect-key}`:" in table
    step = _slice(text, SUB_STEP_1, SUB_STEP_2)
    assert ('fp="fp-$(printf \'%s|%s|%s|%s|%s\' "{severity}" "{workflow}" "{step_file}" "{section-slug}" '
            '"{defect-key}" | sha1sum | cut -c1-7)"') in step
    assert ('legacy_fp="fp-$(printf \'%s|%s|%s|%s\' "{severity}" "{workflow}" "{step_file}" "{section-slug}" '
            '| sha1sum | cut -c1-7)"') in step
    # No formula anywhere in the file still leaves the key out, but the legacy one.
    assert text.count("{section-slug}\" | sha1sum") == 1
    assert "|{section-slug}\")" not in text and "section-slug)[:7]" not in text


def test_the_defect_key_rule_says_how_to_pick_it():
    rule = _flow(_slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_1, SUB_STEP_2))
    for needle in (
        "one to four lower-case ASCII words joined by hyphens that name the thing the fix would change",
        "in the step file's or the code's own words",
        "Pick the most specific name the fix would edit; when the defect is a missing rule, name the case the rule "
        "should cover.",
        "`floor_check` gives `floor-check`",
        "`--orphan-action` flag gives `orphan-action`",
        "gives `shared-text-order`",
        "Never use a line number, a file name or path (the step file already says where), a severity, or words from "
        "this session's own story",
        "whoever reports the same defect next must reach the same key from the source alone",
        "If you cannot name such a thing, use the section's own subject.",
    ):
        assert needle in rule, needle


def test_the_defect_key_examples_name_real_things():
    """The examples are the step files' and the code's own names, not invented ones."""
    src = REPO / "src"
    assert "def floor_check(" in _read(src / "skf-test-skill" / "scripts" / "validate-inventory.py")
    assert "`--orphan-action`" in _read(src / "skf-setup" / "references" / "auto-index.md")
    assert "the shared text first, then `; `" in _read(src / "skf-test-skill" / "references" /
                                                     "inventory-contract.md")


def test_a_worked_example_through_the_portable_command():
    """Two different gaps in inventory-contract.md's only section shared one
    fingerprint before the key; the key keeps them apart, and the doc's
    command gives the same 7 hex characters as hashlib, with and without it."""
    step = _slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_1, SUB_STEP_2)
    m = re.search(r'^uv run python -c "(.+?)" '
                  r'"\{severity\}\|\{workflow\}\|\{step_file\}\|\{section-slug\}\|\{defect-key\}"$',
                  step, re.MULTILINE)
    assert m, "portable fingerprint snippet not found"
    assert "for `legacy_fp`, leave `|{defect-key}` out of its last argument" in step

    def run(arg: str) -> str:
        return subprocess.run([sys.executable, "-c", m.group(1), arg], capture_output=True, text=True,
                              encoding="utf-8", check=True).stdout.strip()

    keyed = {key: run(_hash_input(key)) for key in KEYS}
    legacy = run(_hash_input(None))
    assert keyed == {key: _sha7(_hash_input(key)) for key in KEYS}
    assert legacy == _sha7(_hash_input(None))
    assert keyed[KEYS[0]] != keyed[KEYS[1]], "two defects in one section must not share a fingerprint"
    assert legacy not in keyed.values()
    # The sample's own numbers, so a change to either formula shows here.
    assert _hash_input(KEYS[0]) == ("gap|skf-test-skill|src/skf-test-skill/references/inventory-contract.md|"
                                    "documented-inventory-contract|function-valued-const")


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None or shutil.which("sha1sum") is None,
                    reason="needs bash and sha1sum")
def test_a_worked_example_through_the_sha1sum_commands():
    step = _slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_1, SUB_STEP_2)
    lines = [line for line in step.splitlines() if line.startswith(("fp=", "legacy_fp="))]
    assert [line.split("=", 1)[0] for line in lines] == ["fp", "legacy_fp"]
    for key in KEYS:
        script = "\n".join(_fill(line, key) for line in lines) + '\nprintf "%s %s" "$fp" "$legacy_fp"'
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
        assert out == f"fp-{_sha7(_hash_input(key))} fp-{_sha7(_hash_input(None))}"


# ---------------------------------------------------------------- the legacy fallback


def test_the_seen_cache_falls_back_to_the_legacy_fingerprint():
    step = _flow(_slice(_read(SHARED_HEALTH_CHECK), SUB_STEP_2, SUB_STEP_3))
    assert ("Look up `{fp}`, and only when the cache has no record for it, `{legacy_fp}` (see **Legacy records** "
            "below). Work these branches on the record found") in step
    assert "1. **No record under either fingerprint** → `unseen`." in step
    legacy = step[step.index("**Legacy records.**"):step.index("**`handled` is the only verdict that suppresses.**")]
    for needle in (
        "A record found only under `{legacy_fp}` is a possible match, never a certain one",
        "Work the same branches on it, then change two verdicts.",
        "`handled` does not suppress: continue as `unseen`",
        "sub-step 4 still offers its issue while that issue is open",
        "`regression` becomes `possible-regression`",
        "Leave the legacy record itself untouched.",
    ):
        assert needle in legacy, needle


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
    assert command in search
    flow = _flow(search)
    assert "When it returns no issue, run it again with `{legacy_fp}` in place of `{fp}`." in flow
    assert "An issue found only by `{legacy_fp}`" in flow and "so it is a possible match" in flow


def test_a_legacy_match_goes_to_the_users_choice():
    choice = _flow(_slice(_read(SHARED_HEALTH_CHECK), "**5a-i. If a matching open issue exists:**", SUB_STEP_5A_II))
    assert "When the issue was found by `{legacy_fp}`, present the same options under this opening instead" in choice
    assert '"**Possible match:** #{N}: {title}' in choice
    for option in ("**\\[R]**", "**\\[C]**", "**\\[N]**", "**\\[S]**"):
        assert option in choice, option
    # Headless never reaches it; a run with nobody to ask never acts on a guess.
    assert "Only the user decides a legacy match." in choice
    assert "A headless run never reaches this choice, because §4 queues its findings locally" in choice
    assert "A run that reaches it with no user to ask takes **\\[S]**" in choice
    assert ("Record the outcome to the seen-cache under `{fp}` with fields `{action, issue_url, date}`, also when the "
            "match was found by `{legacy_fp}`.") in choice


def test_the_seen_cache_is_written_under_the_new_fingerprint():
    text = _read(SHARED_HEALTH_CHECK)
    assert "write the `{fp}` → issue-url mapping to the seen-cache" in text
    cache = _flow(_slice(text, "### 5b.", "### 5c."))
    assert ("**Write under `{fp}` only.** A record under `{legacy_fp}` stays exactly as it is, whatever its action"
            in cache)


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


def test_the_issue_template_records_every_fingerprint_input():
    template = _read(ISSUE_TEMPLATE)
    headings = _headings(template)
    order = ["## Workflow", "## Step File", "## Section", "## Severity", "## Fingerprint", "## Defect Key",
             "## Finding"]
    assert [h for h in headings if h in order] == order
    flow = _flow(template)
    assert 'first 7 hex chars of sha1("severity|workflow|step_file|section-slug|defect-key")' in flow
    assert "compute it from those five fields" in flow
    defect = _flow(_slice(template, "## Defect Key", "## Finding"))
    assert "One to four lower-case words joined by hyphens that name the thing the fix would change" in defect


def test_the_docs_state_the_keyed_fingerprint():
    bullet = next(line for line in _read(WORKFLOWS_DOC).splitlines() if line.startswith("- **Fingerprint dedup.**"))
    assert "a `sha1` hash of `severity|workflow|step_file|section|defect-key`" in bullet
    assert "two different defects in one section get different ones" in bullet
    assert "not an LLM similarity judgment" in bullet
    assert "as a possible match only" in bullet
