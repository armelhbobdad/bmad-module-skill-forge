#!/usr/bin/env python3
"""Tests for skf-check-preservation.py (skf-refine-architecture compile.md, init.md).

The script builds the refined document from an insertion plan instead of the
model retyping the original, so these pin what it promises (#587):

- every original line keeps its bytes and terminator (LF, CRLF, no final
  newline), and setting RA's marked blocks aside in the draft gives the
  original back exactly, so a later pass replaces RA's annotations and keeps
  the user's text;
- placement: an issue goes after the paragraph, whole list (a code fence
  indented under one of its items included), table, blockquote or code fence
  that holds its anchor (after a heading anchor, the heading line), a gap or
  improvement at the end of its section one heading level deeper, entries at
  one point issue, gap, improvement and each by tier, and null anchors in
  fallback sections ordered by severity and value;
- the summary's counts, unverified technologies and evidence rows come from
  the plan, apply's record holds the filled summary, and a summary that
  types the totals or leaves an unknown placeholder is refused;
- the plan check names each anchor that is missing (with the closest line)
  or ambiguous (with every match and its heading), and every other problem,
  before anything is written, so an earlier draft stays as it was; a
  heading anchor matches its own heading, not a longer one;
- an earlier pass is detected and set aside: marked blocks, the unmarked
  annotations of an older pass with its Refinement Summary, a
  refined-architecture-*.md name; a marker without its pair and markers in
  code fences are kept as the user's text; every block set aside is named
  by its lines, a user paragraph an older section swallowed included;
- check fails on a dropped or changed line and passes on added ones;
- promote renames an existing output with the run's timestamp (-2 when that
  name is taken), moves the draft, refuses a draft that lost a line, copies
  across file systems and puts the earlier output back when the move or
  the write of its record fails, naming where each file is when it cannot;
- context merges the three records into the result contract's payload and
  refuses a record that is missing;
- writes go through the shared atomic writer (exit 3 when it is missing), -o
  writes the JSON only on success, and the CLI exit codes match the docstring;
- rules (init.md section 4, #598) passes the bundled refinement rules and a
  renamed copy, and names each table and tier rule a copy breaks: a missing
  or empty table, a tier name the summary cannot count, a reserved or
  repeated name, an unknown, repeated or unmapped VS token and a VS row
  that raises no tier;
- verdicts (issue-detection.md section 4, #598) joins each [VS] row to the
  skill of that name or of a single alias, routes a pair with an
  out-of-scope skill or a library no skill matches (a cycle row's `cycle`)
  to out_of_scope, gives each in-scope row the tier its token raises, and
  reports a report [VS] rewrote, one that cannot be read or breaks the
  contract, and rules that changed, as stale (exit 1); a missing reader
  exits 3.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-refine-architecture" / "scripts" / "skf-check-preservation.py"

spec = importlib.util.spec_from_file_location("skf_check_preservation", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

ARCH = """---
project_name: demo
---
# Demo Architecture

Intro paragraph.

## Data Layer

Loro stores documents.
Sync runs over gRPC.

- item one
- item two

  continuation of item two

- item three

| A | B |
|---|---|
| loro | yjs |

> A quoted design note.
> Its second line.

```python
# not a heading
print("x")
```

## API Layer

The API uses FastAPI.

### Endpoints

GET /docs
"""

SUMMARY = (
    "## Refinement Summary\n\n"
    "Produced by: Refine Architecture workflow using 3 skills\n\n"
    "| Category | Count | Breakdown |\n|---|---|---|\n"
    "| Gaps Filled | {gap_count} | - |\n"
    "| Issues Flagged | {issue_count} | Critical: {critical_count}, Major: {major_count}, Minor: {minor_count} |\n"
    "| Improvements Suggested | {improvement_count} | High: {high_count}, Medium: {medium_count}, Low: {low_count} |\n"
    "| Not verified (no skill) | {unverified_count} | Redis |\n\n"
    "| Skill | Refinements |\n|---|---|\n{evidence_rows}"
)


def _entry(entry_id, kind, anchor, block, tier=None, skills=(), **extra):
    entry = {"id": entry_id, "kind": kind, "anchor": anchor, "block": block, "skills": list(skills), **extra}
    if tier is not None:
        entry["tier"] = tier
    return entry


def _plan(*entries, summary=SUMMARY, **extra):
    return {"entries": list(entries), "summary": summary, "unverified_technologies": ["Redis"], **extra}


GAP = "#### RA: Loro <-> Yjs Integration Path\n\n> [!NOTE] **Gap Identified by Refine Architecture**\n> body"
ISSUE = "> [!WARNING] **Issue Detected by Refine Architecture** ({tier})\n> Architecture states: claim"
IMPROVEMENT = "#### RA: Enhancement: {title}\n\n> [!TIP] **Improvement Suggested by Refine Architecture**"


def _issue(entry_id, anchor, tier="Major", **extra):
    return _entry(entry_id, "issue", anchor, ISSUE.format(tier=tier), tier=tier, **extra)


def _improvement(entry_id, anchor, tier="High", title="Use it", **extra):
    return _entry(entry_id, "improvement", anchor, IMPROVEMENT.format(title=title), tier=tier, **extra)


def _write(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *[str(a) for a in args]],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def _apply(tmp_path, plan, original=ARCH, name="arch.md"):
    doc = _write(tmp_path / name, original)
    plan_path = _write(tmp_path / "plan.json", json.dumps(plan))
    draft = tmp_path / "draft.md"
    proc = _run("apply", "--original", doc, "--plan", plan_path, "--draft", draft)
    return proc, draft


def _texts(text: str) -> list[str]:
    return [line.text for line in mod.split_lines(text)]


def _region_after(draft: str, entry_id: str) -> str:
    """The original line right before an entry's BEGIN marker."""
    lines = _texts(draft)
    begin = next(i for i, t in enumerate(lines) if t.startswith(f"<!-- RA:BEGIN") and t.split()[3] == entry_id)
    return lines[begin - 1]


def _stripped(text: str) -> str:
    return mod.render(mod.strip_ra(mod.split_lines(text)).kept)


# --------------------------------------------------------------------------
# Lines keep their bytes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["a\nb\n", "a\r\nb\r\n", "a\nb", "", "\n\n", "a\r\nb"],
                         ids=["lf", "crlf", "no-final-newline", "empty", "blank-lines", "crlf-no-final"])
def test_split_and_render_round_trip(text):
    assert mod.render(mod.split_lines(text)) == text


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_setting_the_blocks_aside_gives_the_original_back(tmp_path, newline):
    original = ARCH.replace("\n", newline)
    plan = _plan(
        _entry("gap-1", "gap", "## Data Layer", GAP, skills=["loro", "yjs"]),
        _issue("issue-1", "Sync runs over gRPC.", "Critical", skills=["loro"]),
        _improvement("improvement-1", None, "Low"),
    )
    proc, draft = _apply(tmp_path, plan, original)
    assert proc.returncode == 0, proc.stdout
    data = draft.read_bytes().decode("utf-8")
    assert _stripped(data) == original
    # Added lines take the document's own line ending.
    assert all(line.end == newline for line in mod.split_lines(data))


def test_a_document_without_a_final_newline_keeps_none(tmp_path):
    original = ARCH.rstrip("\n")
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "GET /docs")), original)
    assert proc.returncode == 0, proc.stdout
    data = draft.read_bytes().decode("utf-8")
    assert not data.endswith("\n")
    assert data.endswith("<!-- RA:END -->")
    assert _stripped(data).rstrip("\n") == original


def test_a_second_pass_replaces_the_first(tmp_path):
    plan = _plan(_entry("gap-1", "gap", "## Data Layer", GAP), _issue("issue-1", "Sync runs over gRPC."))
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    first = draft.read_text(encoding="utf-8")
    # The refined document as input: its blocks are set aside and written once.
    proc, again = _apply(tmp_path, plan, first, name="refined-architecture-demo.md")
    assert proc.returncode == 0, proc.stdout
    second = again.read_text(encoding="utf-8")
    assert second == first
    assert second.count("## Refinement Summary") == 1
    assert json.loads(proc.stdout)["lines_set_aside"] == first.count("\n") - ARCH.count("\n")


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------


def test_an_issue_goes_after_the_block_that_holds_its_anchor(tmp_path):
    plan = _plan(
        _issue("in-paragraph", "Sync runs over gRPC."),
        _issue("in-list", "- item two"),
        _issue("in-table", "| loro | yjs |"),
        _issue("in-quote", "> A quoted design note."),
        _issue("in-fence", "# not a heading"),
        _issue("on-heading", "### Endpoints"),
    )
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    text = draft.read_text(encoding="utf-8")
    assert _region_after(text, "in-paragraph") == "Sync runs over gRPC."
    # A loose list is one block: the callout goes after its last item.
    assert _region_after(text, "in-list") == "- item three"
    assert _region_after(text, "in-table") == "| loro | yjs |"
    assert _region_after(text, "in-quote") == "> Its second line."
    assert _region_after(text, "in-fence") == "```"
    assert _region_after(text, "on-heading") == "### Endpoints"


LIST_WITH_CODE = """# Setup

1. Install the server with gRPC sync:
   ```bash
   npm i server
   ```
2. Start it.

   It listens on port 80.

   ```bash
   server --port 80
   ```

After the list.
"""


@pytest.mark.parametrize(
    "anchor",
    ["Install the server with gRPC sync", "npm i server", "It listens on port 80.", "server --port 80"],
    ids=["item-line", "in-fence", "after-blank", "in-later-fence"],
)
def test_a_code_fence_inside_a_list_item_stays_in_its_list(tmp_path, anchor):
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", anchor)), LIST_WITH_CODE)
    assert proc.returncode == 0, proc.stdout
    lines = _texts(draft.read_text(encoding="utf-8"))
    # The callout follows the whole list: no item loses its code block.
    assert _region_after(draft.read_text(encoding="utf-8"), "issue-1") == "   ```"
    assert lines.index("<!-- RA:BEGIN issue issue-1 -->") > lines.index("   server --port 80")
    assert lines.index("<!-- RA:BEGIN issue issue-1 -->") < lines.index("After the list.")


def test_a_fence_that_is_not_in_a_list_still_ends_its_block(tmp_path):
    original = "# T\n\nSome prose.\n\n  ```\n  indented code\n  ```\n\nMore prose.\n"
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "indented code")), original)
    assert proc.returncode == 0, proc.stdout
    assert _region_after(draft.read_text(encoding="utf-8"), "issue-1") == "  ```"


def test_a_gap_or_improvement_ends_its_section_one_level_deeper(tmp_path):
    plan = _plan(
        _entry("gap-1", "gap", "## Data Layer", GAP),
        # A body line anchors to the nearest heading above it.
        _improvement("improvement-1", "The API uses FastAPI."),
    )
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    lines = _texts(draft.read_text(encoding="utf-8"))
    gap_end = lines.index("<!-- RA:END -->", lines.index("<!-- RA:BEGIN gap gap-1 -->"))
    assert lines[gap_end + 1] == "## API Layer", "the gap closes the Data Layer section"
    assert "### RA: Loro <-> Yjs Integration Path" in lines
    # The API Layer section runs to the end, past its own ### Endpoints.
    improvement = lines.index("<!-- RA:BEGIN improvement improvement-1 -->")
    assert lines.index("GET /docs") < improvement
    assert "### RA: Enhancement: Use it" in lines


def test_the_heading_level_stops_at_six(tmp_path):
    original = "# A\n\n###### Deep\n\ntext\n"
    proc, draft = _apply(tmp_path, _plan(_entry("gap-1", "gap", "###### Deep", GAP)), original)
    assert proc.returncode == 0, proc.stdout
    assert "###### RA: Loro <-> Yjs Integration Path" in _texts(draft.read_text(encoding="utf-8"))


def test_entries_at_one_point_are_ordered_by_kind_and_tier(tmp_path):
    plan = _plan(
        _improvement("imp-low", "## Data Layer", "Low"),
        _entry("gap-1", "gap", "## Data Layer", GAP),
        _improvement("imp-high", "## Data Layer", "High"),
        _issue("issue-minor", "Sync runs over gRPC.", "Minor"),
        _issue("issue-critical", "Loro stores documents.", "Critical"),
    )
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    begins = [t.split()[3] for t in _texts(draft.read_text(encoding="utf-8")) if t.startswith("<!-- RA:BEGIN")]
    assert begins[:2] == ["issue-critical", "issue-minor"]
    assert begins[2:5] == ["gap-1", "imp-high", "imp-low"]


def test_null_anchors_fill_the_fallback_sections_in_order(tmp_path):
    plan = _plan(
        _issue("issue-minor", None, "Minor"),
        _improvement("imp-low", None, "Low", title="Low one"),
        _issue("issue-critical", None, "Critical"),
        _improvement("imp-high", None, "High", title="High one"),
        _entry("gap-1", "gap", None, GAP),
    )
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    assert result["fallback"] == ["gap-1", "issue-critical", "issue-minor", "imp-high", "imp-low"]
    lines = _texts(draft.read_text(encoding="utf-8"))
    sections = [t for t in lines if t.startswith("<!-- RA:BEGIN")]
    assert sections == ["<!-- RA:BEGIN section gap -->", "<!-- RA:BEGIN section issue -->",
                        "<!-- RA:BEGIN section improvement -->",
                        "<!-- RA:BEGIN summary refinement-summary -->"]
    assert "## RA: Additional Integration Paths" in lines and "## RA: Additional Issues Detected" in lines
    assert lines.index("### RA: Enhancement: High one") < lines.index("### RA: Enhancement: Low one")
    critical = lines.index("> [!WARNING] **Issue Detected by Refine Architecture** (Critical)")
    assert critical < lines.index("> [!WARNING] **Issue Detected by Refine Architecture** (Minor)")


def test_a_gap_with_no_heading_above_its_anchor_goes_to_the_fallback(tmp_path):
    original = "Loose text before any heading.\n\n# Title\n"
    proc, _ = _apply(tmp_path, _plan(_entry("gap-1", "gap", "Loose text", GAP)), original)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["fallback"] == ["gap-1"]


def test_a_document_ending_in_an_open_fence_is_closed_first(tmp_path):
    original = "# Title\n\n```\ncode never closed\n"
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "code never closed")), original)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    lines = _texts(draft.read_text(encoding="utf-8"))
    assert lines[result["closed_fence_line"] - 1] == "```"
    structure = mod.scan(lines)
    summary = lines.index("## Refinement Summary")
    assert not structure.fence[summary], "nothing RA adds lands in the code"
    check = mod.check_preservation(mod.split_lines(original), mod.split_lines(draft.read_text(encoding="utf-8")))
    assert check["preserved"] and check["added_count"] == 1


def test_the_frontmatter_is_never_an_anchor(tmp_path):
    proc, _ = _apply(tmp_path, _plan(_issue("issue-1", "project_name: demo")))
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["problems"][0]["reason"] == "anchor-not-found"


# --------------------------------------------------------------------------
# Counts come from the plan
# --------------------------------------------------------------------------


def test_the_summary_counts_and_evidence_come_from_the_plan(tmp_path):
    plan = _plan(
        _entry("gap-1", "gap", "## Data Layer", GAP, skills=["loro", "yjs"]),
        _issue("issue-1", "Sync runs over gRPC.", "Critical", skills=["loro"]),
        _issue("issue-2", "The API uses FastAPI.", "Minor", skills=["fastapi", "fastapi"]),
        _improvement("improvement-1", None, "Medium", skills=["loro"]),
    )
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    assert result["counts"] == {
        "gap": 1, "issue": 2, "improvement": 1,
        "issue_tiers": {"Critical": 1, "Major": 0, "Minor": 1},
        "improvement_tiers": {"High": 0, "Medium": 1, "Low": 0},
        "unverified": 1,
        "skills": None,
    }
    assert result["evidence"] == {"loro": 3, "fastapi": 1, "yjs": 1}
    lines = _texts(draft.read_text(encoding="utf-8"))
    assert "| Gaps Filled | 1 | - |" in lines
    assert "| Issues Flagged | 2 | Critical: 1, Major: 0, Minor: 1 |" in lines
    assert "| Improvements Suggested | 1 | High: 0, Medium: 1, Low: 0 |" in lines
    assert "| Not verified (no skill) | 1 | Redis |" in lines
    assert lines[-5:-2] == ["| loro | 3 |", "| fastapi | 1 |", "| yjs | 1 |"]
    assert [p["id"] for p in result["placed"]] == ["issue-1", "gap-1", "issue-2"]
    assert lines[result["placed"][0]["line"] - 1] == "<!-- RA:BEGIN issue issue-1 -->"


def test_the_skill_count_comes_from_the_plan(tmp_path):
    summary = SUMMARY.replace("using 3 skills", "using {skill_count} skills")
    [problem] = _problems(tmp_path, _plan(summary=summary))
    assert problem["reason"] == "summary-placeholder" and "{skill_count}" in problem["detail"]
    proc, draft = _apply(tmp_path, _plan(summary=summary, skill_count=4))
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["counts"]["skills"] == 4
    assert "Produced by: Refine Architecture workflow using 4 skills" in _texts(draft.read_text(encoding="utf-8"))
    again = tmp_path / "again"
    again.mkdir()
    problems = _problems(again, _plan(summary=summary, skill_count=-1))
    assert [p["reason"] for p in problems] == ["plan-invalid", "summary-placeholder"]


@pytest.mark.parametrize(("names", "shown"), [(["Redis", "Kafka"], "Redis, Kafka"), ([], "none")],
                         ids=["named", "none"])
def test_the_unverified_technologies_come_from_the_plan(tmp_path, names, shown):
    summary = SUMMARY.replace("| {unverified_count} | Redis |", "| {unverified_count} | {unverified_technologies} |")
    proc, draft = _apply(tmp_path, {**_plan(summary=summary), "unverified_technologies": names})
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    row = f"| Not verified (no skill) | {len(names)} | {shown} |"
    assert row in _texts(draft.read_text(encoding="utf-8"))
    assert result["unverified_technologies"] == names


def test_the_record_holds_the_summary_the_draft_shows(tmp_path):
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "Sync runs over gRPC.", "Critical", skills=["loro"])))
    assert proc.returncode == 0, proc.stdout
    summary = json.loads(proc.stdout)["summary"]
    assert summary.startswith("## Refinement Summary\n") and "| loro | 1 |" in summary
    lines = _texts(draft.read_text(encoding="utf-8"))
    start = lines.index("## Refinement Summary")
    assert lines[start:start + len(summary.split("\n"))] == summary.split("\n")


def test_tiers_can_be_renamed(tmp_path):
    summary = SUMMARY.replace("{critical_count}", "{blocker_count}").replace("{major_count}", "{warn_count}")
    summary = summary.replace(", Minor: {minor_count}", "")
    plan = _plan(_issue("issue-1", "Sync runs over gRPC.", "Blocker"), summary=summary,
                 tiers={"issue": ["Blocker", "Warn"]})
    proc, draft = _apply(tmp_path, plan)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["counts"]["issue_tiers"] == {"Blocker": 1, "Warn": 0}
    assert "| Issues Flagged | 1 | Critical: 1, Major: 0 |" in _texts(draft.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The plan check
# --------------------------------------------------------------------------


def _problems(tmp_path, plan, original=ARCH):
    proc, draft = _apply(tmp_path, plan, original)
    assert proc.returncode == 1, proc.stdout
    result = json.loads(proc.stdout)
    assert result["status"] == "problems"
    assert not draft.exists(), "a plan with a problem writes nothing"
    return result["problems"]


def test_a_missing_anchor_names_the_closest_line(tmp_path):
    [problem] = _problems(tmp_path, _plan(_issue("issue-1", "Sync runs over gRPC streams.")))
    assert problem["reason"] == "anchor-not-found" and problem["id"] == "issue-1"
    assert problem["closest"] == {"line": 11, "text": "Sync runs over gRPC.", "heading": "## Data Layer"}


def test_an_ambiguous_anchor_names_every_match_and_occurrence_picks_one(tmp_path):
    [problem] = _problems(tmp_path, _plan(_issue("issue-1", "item two")))
    assert problem["reason"] == "anchor-ambiguous"
    assert [(m["line"], m["heading"]) for m in problem["matches"]] == [(14, "## Data Layer"), (16, "## Data Layer")]
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "item two", occurrence=2)))
    assert proc.returncode == 0, proc.stdout
    assert _region_after(draft.read_text(encoding="utf-8"), "issue-1") == "- item three"
    again = tmp_path / "again"
    again.mkdir()
    [problem] = _problems(again, _plan(_issue("issue-1", "item two", occurrence=3)))
    assert problem["reason"] == "occurrence-out-of-range"


def test_a_heading_anchor_matches_its_own_heading(tmp_path):
    original = "# T\n\n## API\n\nText.\n\n### API Gateway\n\nMore.\n\n## API Clients\n\nEnd.\n"
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "## API"), _entry("gap-1", "gap", "### API Gateway", GAP)),
                         original)
    assert proc.returncode == 0, proc.stdout
    text = draft.read_text(encoding="utf-8")
    assert _region_after(text, "issue-1") == "## API"
    lines = _texts(text)
    assert lines[lines.index("<!-- RA:END -->", lines.index("<!-- RA:BEGIN gap gap-1 -->")) + 1] == "## API Clients"
    # A heading-shaped anchor that names no heading is matched as text.
    proc, _ = _apply(tmp_path, _plan(_issue("issue-1", "# not a heading")))
    assert proc.returncode == 0, proc.stdout


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        (_issue("bad id", "Sync runs over gRPC."), "entry-invalid"),
        (_entry("x-1", "note", "Sync runs over gRPC.", "text"), "entry-invalid"),
        (_issue("x-1", "Sync runs over gRPC.", "Severe"), "tier-unknown"),
        (_entry("x-1", "issue", "Sync runs over gRPC.", "> <!-- RA:END -->", tier="Major"), "block-has-marker"),
        (_entry("x-1", "issue", "Sync runs over gRPC.", "```\nopen", tier="Major"), "block-unclosed-fence"),
        (_entry("x-1", "gap", "## Data Layer", "no heading here"), "block-no-heading"),
        (_entry("x-1", "issue", "Sync runs over gRPC.", "   ", tier="Major"), "entry-invalid"),
        ({"id": "x-1", "kind": "gap", "anchor": "## Data Layer", "block": GAP, "skills": "loro"}, "entry-invalid"),
    ],
    ids=["id", "kind", "tier", "marker", "fence", "heading", "empty-block", "skills"],
)
def test_each_entry_problem_is_named(tmp_path, entry, reason):
    [problem] = _problems(tmp_path, _plan(entry))
    assert problem["reason"] == reason, problem


def test_a_duplicate_id_is_a_problem(tmp_path):
    [problem] = _problems(tmp_path, _plan(_issue("x-1", "Sync runs over gRPC."), _issue("x-1", "GET /docs")))
    assert problem == {"id": "x-1", "reason": "entry-invalid", "detail": "the id is used twice"}


@pytest.mark.parametrize(
    ("summary", "reason"),
    [
        (SUMMARY.replace("{gap_count}", "2"), "summary-count-typed"),
        (SUMMARY + "\n\nUsing {skill_count} skills", "summary-placeholder"),
        (SUMMARY + "\n<!-- RA:BEGIN x y -->", "summary-has-marker"),
        (SUMMARY + "\n```\nopen", "summary-unclosed-fence"),
        ("", "plan-invalid"),
    ],
    ids=["typed", "unknown-placeholder", "marker", "fence", "empty"],
)
def test_each_summary_problem_is_named(tmp_path, summary, reason):
    problems = _problems(tmp_path, _plan(summary=summary))
    assert [p["reason"] for p in problems] == [reason]


def test_a_plan_that_is_not_json_is_a_problem(tmp_path):
    doc = _write(tmp_path / "arch.md", ARCH)
    plan = _write(tmp_path / "plan.json", "{not json")
    proc = _run("apply", "--original", doc, "--plan", plan, "--draft", tmp_path / "draft.md")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["problems"][0]["reason"] == "plan-invalid"


def test_a_failed_build_keeps_the_earlier_draft_and_its_record(tmp_path):
    doc = _write(tmp_path / "arch.md", ARCH)
    plan = _write(tmp_path / "plan.json", json.dumps(_plan(_issue("issue-1", "GET /docs"))))
    draft, record = tmp_path / "draft.md", tmp_path / "apply.json"
    proc = _run("apply", "--original", doc, "--plan", plan, "--draft", draft, "-o", record)
    assert proc.returncode == 0, proc.stdout
    before = (draft.read_bytes(), record.read_bytes())
    _write(plan, json.dumps(_plan(_issue("issue-1", "no such line"))))
    proc = _run("apply", "--original", doc, "--plan", plan, "--draft", draft, "-o", record)
    assert proc.returncode == 1
    assert (draft.read_bytes(), record.read_bytes()) == before
    assert json.loads(before[1])["status"] == "ok"


def test_apply_refuses_a_draft_that_would_lose_a_line(tmp_path, monkeypatch):
    doc = _write(tmp_path / "arch.md", ARCH)
    plan = _write(tmp_path / "plan.json", json.dumps(_plan()))
    real = mod.compose

    def lossy(base, resolved):
        out, info = real(base, resolved)
        return [line for line in out if line.text != "Intro paragraph."], info

    monkeypatch.setattr(mod, "compose", lossy)
    draft = tmp_path / "draft.md"
    code = mod.main(["apply", "--original", str(doc), "--plan", str(plan), "--draft", str(draft)])
    assert code == 1 and not draft.exists()


# --------------------------------------------------------------------------
# An earlier pass
# --------------------------------------------------------------------------

LEGACY = """# Demo

## Data Layer

Loro stores documents.

> [!WARNING] **Issue Detected by Refine Architecture** (Major)
> Architecture states: "Loro stores documents."

#### RA: Loro <-> Yjs Integration Path

> [!NOTE] **Gap Identified by Refine Architecture**
> body

## API Layer

The API uses FastAPI.

## Refinement Summary

| Category | Count |
|---|---|
| Gaps Filled | 1 |
"""


def test_inspect_finds_an_older_unmarked_pass_and_sets_it_aside(tmp_path):
    doc = _write(tmp_path / "arch.md", LEGACY)
    out = tmp_path / "analysis.md"
    proc = _run("inspect", "--doc", doc, "--stripped", out)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    assert result["previous_pass"] is True and result["signals"] == ["legacy-annotations"]
    assert result["legacy_blocks"] == 3 and result["marked_blocks"] == 0
    stripped = _texts(out.read_text(encoding="utf-8"))
    assert [t for t in stripped if t.strip()] == [
        "# Demo", "## Data Layer", "Loro stores documents.", "## API Layer", "The API uses FastAPI."]


def test_unmarked_ra_headings_without_a_summary_are_the_users(tmp_path):
    text = LEGACY.split("## Refinement Summary")[0]
    result = mod.strip_ra(mod.split_lines(text))
    assert result.legacy == 0 and mod.render(result.kept) == text


def test_every_block_set_aside_is_named_by_its_lines(tmp_path):
    # An older pass marked nothing, so its RA: section runs to the next heading
    # and takes the user's paragraph after it: inspect and apply name the lines.
    legacy = ("# Doc\n\n## Data Layer\n\nLoro handles sync.\n\n#### RA: Loro <-> FastAPI Integration Path\n\n"
              "> [!NOTE] **Gap Identified by Refine Architecture**\n\nWe also cache everything in Redis.\n\n"
              "## API\n\nThe API uses FastAPI.\n\n<!-- RA:BEGIN gap g -->\nx\n<!-- RA:END -->\n\n"
              "## Refinement Summary\n\nold\n")
    doc = _write(tmp_path / "arch.md", legacy)
    result = json.loads(_run("inspect", "--doc", doc).stdout)
    assert result["set_aside"] == [
        {"start": 7, "end": 12, "kind": "legacy", "first_line": "#### RA: Loro <-> FastAPI Integration Path"},
        {"start": 17, "end": 19, "kind": "marked", "first_line": "<!-- RA:BEGIN gap g -->"},
        {"start": 21, "end": 23, "kind": "legacy", "first_line": "## Refinement Summary"},
    ]
    assert "We also cache everything in Redis." not in _stripped(legacy)
    proc, draft = _apply(tmp_path, _plan(_issue("issue-1", "The API uses FastAPI.")), legacy)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["set_aside"] == result["set_aside"]
    # The check compares both files with the same lines set aside, so it cannot see them.
    assert mod.check_preservation(mod.split_lines(legacy), mod.split_lines(draft.read_text(encoding="utf-8")))["preserved"]


def test_inspect_signals(tmp_path):
    plain = _write(tmp_path / "arch.md", ARCH)
    result = json.loads(_run("inspect", "--doc", plain).stdout)
    assert (result["previous_pass"], result["signals"], result["stripped"]) == (False, [], None)
    named = _write(tmp_path / "refined-architecture-demo.md", ARCH)
    assert json.loads(_run("inspect", "--doc", named).stdout)["signals"] == ["refined-document"]
    marked = _write(tmp_path / "marked.md", ARCH + "<!-- RA:BEGIN gap g -->\nx\n<!-- RA:END -->\n")
    result = json.loads(_run("inspect", "--doc", marked).stdout)
    assert result["signals"] == ["ra-markers"] and result["marked_blocks"] == 1
    assert result["lines_set_aside"] == 3


def test_a_marker_without_its_pair_keeps_the_users_text():
    text = ("# T\n\n<!-- RA:BEGIN gap lost-end -->\nmine\n<!-- RA:BEGIN gap g -->\nRA text\n<!-- RA:END -->\n"
            "after\n<!-- RA:END -->\n")
    result = mod.strip_ra(mod.split_lines(text))
    assert result.malformed == [3, 9]
    assert _texts(mod.render(result.kept)) == ["# T", "", "<!-- RA:BEGIN gap lost-end -->", "mine", "after",
                                               "<!-- RA:END -->"]


def test_markers_inside_a_code_fence_are_the_users():
    text = "# T\n\n```html\n<!-- RA:BEGIN gap g -->\nexample\n<!-- RA:END -->\n```\n"
    result = mod.strip_ra(mod.split_lines(text))
    assert result.marked == 0 and mod.render(result.kept) == text


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def test_check_passes_on_added_lines_and_ra_blocks(tmp_path):
    original = _write(tmp_path / "a.md", ARCH)
    refined = _write(tmp_path / "b.md", ARCH.replace("Intro paragraph.\n", "Intro paragraph.\nA new line.\n")
                     + "<!-- RA:BEGIN gap g -->\n## RA: x\n<!-- RA:END -->\n")
    proc = _run("check", "--original", original, "--refined", refined)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    assert result["preserved"] is True and result["added_count"] == 1


def test_check_names_a_dropped_and_a_changed_line(tmp_path):
    original = _write(tmp_path / "a.md", ARCH)
    refined = _write(tmp_path / "b.md", ARCH.replace("Loro stores documents.\n", "")
                     .replace("The API uses FastAPI.", "The API uses Flask."))
    proc = _run("check", "--original", original, "--refined", refined)
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["status"] == "not-preserved"
    assert result["missing"] == [{"line": 10, "text": "Loro stores documents."}]
    [altered] = result["altered"]
    assert (altered["line"], altered["original"], altered["refined"]) == (34, "The API uses FastAPI.",
                                                                          "The API uses Flask.")


def test_check_keeps_the_first_fifty_of_each_list(tmp_path):
    original = _write(tmp_path / "a.md", "".join(f"line {i}\n" for i in range(120)))
    refined = _write(tmp_path / "b.md", "")
    result = json.loads(_run("check", "--original", original, "--refined", refined).stdout)
    assert result["missing_count"] == 120 and len(result["missing"]) == 50


def test_a_file_that_is_not_utf8_exits_2_with_json(tmp_path):
    bad = tmp_path / "a.md"
    bad.write_bytes(b"caf\xe9\n")
    proc = _run("check", "--original", bad, "--refined", bad)
    assert proc.returncode == 2
    assert "not UTF-8" in json.loads(proc.stdout)["error"]
    proc = _run("check", "--original", tmp_path / "missing.md", "--refined", bad)
    assert proc.returncode == 2 and json.loads(proc.stdout)["status"] == "error"


# --------------------------------------------------------------------------
# promote
# --------------------------------------------------------------------------


def _promote_setup(tmp_path):
    doc = _write(tmp_path / "arch.md", ARCH)
    plan = _write(tmp_path / "plan.json", json.dumps(_plan(_issue("issue-1", "GET /docs"))))
    draft = tmp_path / "forge" / ".skf-ra-draft-demo.md"
    draft.parent.mkdir()
    assert _run("apply", "--original", doc, "--plan", plan, "--draft", draft).returncode == 0
    output = tmp_path / "docs" / "refined-architecture-demo.md"
    output.parent.mkdir()
    return doc, draft, output


def test_promote_keeps_an_earlier_output_under_a_timestamped_name(tmp_path):
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "my curated refinement\n")
    _write(output.with_name("refined-architecture-demo-20261001-120000.md"), "taken\n")
    content = draft.read_bytes()
    record = tmp_path / "promote.json"
    proc = _run("promote", "--original", doc, "--draft", draft, "--output", output,
                "--timestamp", "20261001-120000", "-o", record)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)
    previous = output.with_name("refined-architecture-demo-20261001-120000-2.md")
    assert Path(result["previous"]).as_posix() == previous.as_posix()
    assert previous.read_text(encoding="utf-8") == "my curated refinement\n"
    assert output.read_bytes() == content and not draft.exists()
    assert json.loads(record.read_text(encoding="utf-8")) == result


def test_promote_with_no_earlier_output(tmp_path):
    doc, draft, output = _promote_setup(tmp_path)
    proc = _run("promote", "--original", doc, "--draft", draft, "--output", output, "--timestamp", "20261001-120000")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["previous"] is None and output.is_file()


def test_promote_refuses_a_draft_that_lost_a_line(tmp_path):
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "earlier\n")
    _write(draft, draft.read_text(encoding="utf-8").replace("Intro paragraph.\n", ""))
    record = tmp_path / "promote.json"
    proc = _run("promote", "--original", doc, "--draft", draft, "--output", output,
                "--timestamp", "20261001-120000", "-o", record)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["missing"][0]["text"] == "Intro paragraph."
    assert output.read_text(encoding="utf-8") == "earlier\n" and draft.exists() and not record.exists()


def test_promote_copies_across_file_systems(tmp_path, monkeypatch):
    doc, draft, output = _promote_setup(tmp_path)
    content = draft.read_bytes()

    def cross_device(src, dst):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(mod.os, "replace", cross_device)
    code = mod.main(["promote", "--original", str(doc), "--draft", str(draft), "--output", str(output),
                     "--timestamp", "20261001-120000"])
    assert code == 0
    assert output.read_bytes() == content and not draft.exists()


def test_a_failed_move_puts_the_earlier_output_back(tmp_path, monkeypatch, capsys):
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "earlier\n")

    def refused(src, dst):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(mod.os, "replace", refused)
    code = mod.main(["promote", "--original", str(doc), "--draft", str(draft), "--output", str(output),
                     "--timestamp", "20261001-120000"])
    assert code == 3
    assert "Permission denied" in json.loads(capsys.readouterr().out)["error"]
    assert output.read_text(encoding="utf-8") == "earlier\n" and draft.exists()
    assert sorted(p.name for p in output.parent.iterdir()) == ["refined-architecture-demo.md"]


def test_a_promotion_whose_record_cannot_be_written_is_undone(tmp_path, monkeypatch, capsys):
    # Step 6 reads the record, so a promotion without one is put back: the
    # draft returns to its place and the earlier output to its name.
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "earlier\n")
    content = draft.read_bytes()
    record = tmp_path / "promote.json"
    write_atomic = mod.write_atomic

    def refuse_the_record(path, data):
        if Path(path).as_posix() == record.as_posix():
            raise mod.WriteError(f"{record.as_posix()}: No space left on device")
        write_atomic(path, data)

    monkeypatch.setattr(mod, "write_atomic", refuse_the_record)
    code = mod.main(["promote", "--original", str(doc), "--draft", str(draft), "--output", str(output),
                     "--timestamp", "20261001-120000", "-o", str(record)])
    assert code == 3
    assert "No space left on device" in json.loads(capsys.readouterr().out)["error"]
    assert output.read_text(encoding="utf-8") == "earlier\n" and draft.read_bytes() == content
    assert sorted(p.name for p in output.parent.iterdir()) == ["refined-architecture-demo.md"]
    assert not record.exists()


def test_a_failed_rollback_says_where_each_file_is(tmp_path, monkeypatch, capsys):
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "earlier\n")
    previous = output.with_name("refined-architecture-demo-20261001-120000.md")
    rename = mod.os.rename

    def refused(src, dst):
        raise OSError(errno.EACCES, "Permission denied")

    def no_way_back(src, dst):
        if Path(src).as_posix() == previous.as_posix():
            raise OSError(errno.EIO, "Input/output error")
        rename(src, dst)

    monkeypatch.setattr(mod.os, "replace", refused)
    monkeypatch.setattr(mod.os, "rename", no_way_back)
    code = mod.main(["promote", "--original", str(doc), "--draft", str(draft), "--output", str(output),
                     "--timestamp", "20261001-120000"])
    assert code == 3
    error = json.loads(capsys.readouterr().out)["error"]
    assert f"stays at {previous.as_posix()}" in error and f"the draft is at {draft.as_posix()}" in error
    assert previous.read_text(encoding="utf-8") == "earlier\n" and not output.exists() and draft.exists()


def test_an_undo_that_fails_says_where_each_file_is(tmp_path, monkeypatch, capsys):
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "earlier\n")
    record = tmp_path / "promote.json"
    write_atomic = mod.write_atomic

    def refuse_the_record(path, data):
        if Path(path).as_posix() == record.as_posix():
            raise mod.WriteError(f"{record.as_posix()}: No space left on device")
        write_atomic(path, data)

    def stuck(src, dst):
        raise OSError(errno.EBUSY, "Device or resource busy")

    monkeypatch.setattr(mod, "write_atomic", refuse_the_record)
    monkeypatch.setattr(mod.shutil, "move", stuck)
    code = mod.main(["promote", "--original", str(doc), "--draft", str(draft), "--output", str(output),
                     "--timestamp", "20261001-120000", "-o", str(record)])
    assert code == 3
    error = json.loads(capsys.readouterr().out)["error"]
    previous = output.with_name("refined-architecture-demo-20261001-120000.md")
    assert f"stays at {output.as_posix()} as the refined document" in error
    assert f"the earlier output is at {previous.as_posix()}" in error
    assert previous.read_text(encoding="utf-8") == "earlier\n" and output.is_file() and not draft.exists()


def test_promote_refuses_an_output_that_is_a_folder(tmp_path):
    doc, draft, output = _promote_setup(tmp_path)
    output.mkdir()
    proc = _run("promote", "--original", doc, "--draft", draft, "--output", output, "--timestamp", "20261001-120000")
    assert proc.returncode == 3 and "not a file" in json.loads(proc.stdout)["error"]


def test_promote_needs_a_timestamp_shaped_like_the_runs(tmp_path):
    proc = _run("promote", "--original", "a", "--draft", "b", "--output", "c", "--timestamp", "2026-10-01")
    assert proc.returncode == 2 and proc.stdout == ""


# --------------------------------------------------------------------------
# context
# --------------------------------------------------------------------------


def _records(tmp_path):
    doc, draft, output = _promote_setup(tmp_path)
    _write(output, "earlier\n")
    run = tmp_path / "run"
    run.mkdir()
    plan = _write(tmp_path / "plan.json", json.dumps(_plan(_issue("issue-1", "GET /docs"), _entry("gap-1", "gap", None, GAP))))
    assert _run("inspect", "--doc", doc, "-o", run / "inspect.json").returncode == 0
    assert _run("apply", "--original", doc, "--plan", plan, "--draft", draft, "-o", run / "apply.json").returncode == 0
    assert _run("promote", "--original", doc, "--draft", draft, "--output", output, "--timestamp", "20261001-120000",
                "-o", run / "promote.json").returncode == 0
    return run, output


def test_context_stages_the_result_payload_from_the_records(tmp_path):
    run, output = _records(tmp_path)
    proc = _run("context", "--inspect", run / "inspect.json", "--apply", run / "apply.json",
                "--promote", run / "promote.json", "--out", run / "result-context.json")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["status"] == "ok"
    payload = json.loads((run / "result-context.json").read_text(encoding="utf-8"))
    previous = output.with_name("refined-architecture-demo-20261001-120000.md").as_posix()
    totals = {"gap_count": 1, "issue_count": 1, "improvement_count": 0, "unverified_count": 1}
    assert payload == {
        "status": "success", "refined_path": output.as_posix(), "previous_refined_path": previous,
        "previous_pass": False, **totals,
        "result_contract": {"skill": "skf-refine-architecture", "status": "success",
                            "outputs": [{"type": "report", "path": output.as_posix()}],
                            "summary": {**totals, "previous_refined_path": previous}},
    }


def test_context_refuses_a_missing_or_foreign_record(tmp_path):
    run, _ = _records(tmp_path)
    (run / "promote.json").unlink()
    argv = ("context", "--inspect", run / "inspect.json", "--apply", run / "apply.json",
            "--promote", run / "promote.json", "--out", run / "result-context.json")
    proc = _run(*argv)
    assert proc.returncode == 2 and json.loads(proc.stdout)["status"] == "error"
    _write(run / "promote.json", json.dumps({"status": "not-preserved"}))
    proc = _run(*argv)
    assert proc.returncode == 2 and "successful promote" in json.loads(proc.stdout)["error"]
    assert not (run / "result-context.json").exists()


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


def test_writes_go_through_the_shared_atomic_writer(tmp_path, monkeypatch, capsys):
    assert mod.ATOMIC_WRITER.as_posix().endswith("src/shared/scripts/skf-atomic-write.py")
    assert mod.ATOMIC_WRITER.is_file()
    monkeypatch.setattr(mod, "ATOMIC_WRITER", tmp_path / "missing" / "skf-atomic-write.py")
    doc = _write(tmp_path / "arch.md", ARCH)
    plan = _write(tmp_path / "plan.json", json.dumps(_plan()))
    code = mod.main(["apply", "--original", str(doc), "--plan", str(plan), "--draft", str(tmp_path / "d.md")])
    assert code == 3
    assert "atomic writer is not installed" in json.loads(capsys.readouterr().out)["error"]
    code = mod.main(["inspect", "--doc", str(doc), "--stripped", str(tmp_path / "s.md")])
    assert code == 3 and not (tmp_path / "s.md").exists()


def test_inspect_writes_its_record_only_on_success(tmp_path):
    record = tmp_path / "inspect.json"
    proc = _run("inspect", "--doc", tmp_path / "missing.md", "-o", record)
    assert proc.returncode == 2 and not record.exists()
    doc = _write(tmp_path / "arch.md", ARCH)
    proc = _run("inspect", "--doc", doc, "--stripped", tmp_path / "s.md", "-o", record)
    assert proc.returncode == 0
    assert json.loads(record.read_text(encoding="utf-8")) == json.loads(proc.stdout)
    assert (tmp_path / "s.md").read_bytes() == ARCH.encode("utf-8")


def test_the_cli_has_the_seven_subcommands():
    proc = _run("--help")
    assert proc.returncode == 0
    for command in ("inspect", "apply", "check", "promote", "context", "rules", "verdicts"):
        assert command in proc.stdout
    assert _run().returncode == 2


# --------------------------------------------------------------------------
# rules: the refinement rules a step classifies with
# --------------------------------------------------------------------------

RULES_PATH = REPO_ROOT / "src" / "skf-refine-architecture" / "references" / "refinement-rules.md"
BUNDLED_RULES = RULES_PATH.read_bytes().decode("utf-8")


def _rules(tmp_path, text: str) -> Path:
    return _write(tmp_path / "rules.md", text)


def _rules_result(tmp_path, text: str) -> tuple[int, dict]:
    proc = _run("rules", "--rules", _rules(tmp_path, text))
    return proc.returncode, json.loads(proc.stdout)


def _broken(*changes: tuple[str, str]) -> str:
    text = BUNDLED_RULES
    for old, new in changes:
        assert old in text, old
        text = text.replace(old, new, 1)
    return text


def test_the_bundled_rules_pass(tmp_path):
    code, result = _rules_result(tmp_path, BUNDLED_RULES)
    assert code == 0 and result["status"] == "ok", result
    assert result["tiers"] == {"issue": ["Critical", "Major", "Minor"], "improvement": ["High", "Medium", "Low"]}
    assert result["vs_raises"] == {"Verified": None, "Plausible": "Minor", "Risky": "Major", "Blocked": "Critical"}
    assert result["missing_tables"] == [] and result["violations"] == []


def test_a_renamed_copy_passes_and_maps_its_own_tiers(tmp_path):
    text = _broken(("**Critical**", "**Blocker**"), ("**Major**", "**Should fix**"), ("**Minor**", "**Later**"),
                   ("A **Critical** issue", "A **blocker** issue"), ("A **Major** issue", "A **Should fix** issue"),
                   ("A **Minor**, potential issue", "A **Later**, potential issue"))
    code, result = _rules_result(tmp_path, text)
    assert code == 0, result
    assert result["tiers"]["issue"] == ["Blocker", "Should fix", "Later"]
    assert result["vs_raises"]["Blocked"] == "Blocker" and result["vs_raises"]["Risky"] == "Should fix"


def test_an_unbolded_copy_passes_and_maps_its_tiers(tmp_path):
    # A team's copy need not bold the tier a VS row raises: its text names one, or says No issue or None.
    text = _broken(("A **Critical** issue: the architecture", "A Critical issue: the architecture"),
                   ("A **Major** issue, confirmed by the VS evidence", "major"),
                   ("A **Minor**, potential issue", "Minor, a potential issue"), ("| No issue", "| None"))
    code, result = _rules_result(tmp_path, text)
    assert code == 0, result
    assert result["vs_raises"] == {"Verified": None, "Plausible": "Minor", "Risky": "Major", "Blocked": "Critical"}


def test_a_bold_no_issue_raises_no_issue_whatever_its_prose_names(tmp_path):
    # Bold decides, as it does for a tier, so a tier word in the prose around it never raises that tier.
    text = _broken(("| No issue", "| **No issue**, even when the rationale notes minor caveats"))
    code, result = _rules_result(tmp_path, text)
    assert code == 0 and result["violations"] == [], result
    assert result["vs_raises"] == {"Verified": None, "Plausible": "Minor", "Risky": "Major", "Blocked": "Critical"}


def test_a_longer_tier_is_not_also_read_as_a_shorter_one():
    tiers = {"severe_count": "Severe", "very_severe_count": "Very Severe"}
    assert mod.vs_raised("A very  severe issue", tiers) == (["Very Severe"], False)
    assert mod.vs_raised("A **Severe** issue, not Very Severe", tiers) == (["Severe"], False)
    assert mod.vs_raised("Nothing to raise", tiers) == ([], False)
    assert mod.vs_raised("No issue: the pair is verified", tiers) == ([], True)
    # A bold No issue or None counts as a bold tier does: the prose around it is not read.
    assert mod.vs_raised("**No issue**, even when the rationale notes severe caveats", tiers) == ([], True)
    assert mod.vs_raised("__None__, whatever the Severe rationale says", tiers) == ([], True)
    # Unbolded, a tier word no longer hides No issue or None: check_rules reports the pair.
    assert mod.vs_raised("No issue unless a severe caveat shows", tiers) == (["Severe"], True)
    assert mod.vs_raised("A **Severe** issue or **No issue**", tiers) == (["Severe"], True)
    assert mod.vs_raised("A **Severe** issue, none of the rationale changes it", tiers) == (["Severe"], False)


def test_a_heading_of_any_level_and_case_holds_a_table(tmp_path):
    code, result = _rules_result(tmp_path, _broken(("## Issue Severity", "### issue severity")))
    assert code == 0, result


VALUE_ROWS = [line for line in BUNDLED_RULES.splitlines(keepends=True)
              if line.startswith(("| **High**", "| **Medium**", "| **Low**"))]
BROKEN_RULES = [
    pytest.param((("## Improvement Value", "## Value Tiers"),), "table-missing", "lacks the Improvement Value table",
                 id="table-missing"),
    pytest.param(tuple((row, "") for row in VALUE_ROWS), "table-empty", "names no tier", id="table-empty"),
    pytest.param((("**Low**    |", "**Must-fix** |"),), "tier-name", "tier `Must-fix`", id="punctuation"),
    pytest.param((("**Low**    |", "**1st** |"),), "tier-name", "tier `1st`", id="leading-digit"),
    pytest.param((("**Low**    |", "**Gap** |"),), "tier-reserved", "tier `Gap`", id="reserved"),
    pytest.param((("**Low**    |", "**critical** |"),), "tier-duplicate", "same name as `Critical`",
                 id="duplicate-across-tables"),
    pytest.param((("| `Verified`  |", "| `VERIFIED`  |"),), "vs-token-unknown", "VS row `VERIFIED`", id="token-case"),
    pytest.param((("| `Verified`  | No issue", "| `Risky` | No issue"),), "vs-token-duplicate",
                 "VS token `Risky` has a second row", id="token-duplicate"),
    pytest.param((("| `Verified`  | No issue", "| `Risky` | No issue"),), "vs-token-unmapped",
                 "no VS Report Integration row maps `Verified`", id="token-unmapped"),
    pytest.param((("A **Major** issue", "A **Severe** issue"),), "vs-raises", "VS row `Risky`",
                 id="raises-unknown-tier"),
    pytest.param((("| No issue", "| Nothing"),), "vs-raises", "VS row `Verified`", id="raises-nothing"),
    pytest.param((("A **Major** issue, confirmed", "Major or Minor, confirmed"),), "vs-raises",
                 "VS row `Risky` (line 57) names more than one tier of the Issue Severity table: Major, Minor",
                 id="raises-two-tiers"),
    pytest.param((("| No issue", "| No issue, even when the rationale notes minor caveats"),), "vs-raises",
                 "VS row `Verified` (line 59) names Minor and also says No issue or None", id="raises-tier-and-none"),
    pytest.param((("| No issue", "| None (Critical findings are tracked elsewhere)"),), "vs-raises",
                 "VS row `Verified` (line 59) names Critical and also says No issue or None: bold the one it raises",
                 id="raises-none-and-tier"),
]


@pytest.mark.parametrize(("changes", "rule", "detail"), BROKEN_RULES)
def test_each_broken_rule_is_named(tmp_path, changes, rule, detail):
    code, result = _rules_result(tmp_path, _broken(*changes))
    assert code == 1 and result["status"] == "violations", result
    found = [v for v in result["violations"] if v["rule"] == rule]
    assert found and any(detail in v["detail"] for v in found), result["violations"]


def test_a_table_in_a_code_fence_is_not_the_rules(tmp_path):
    fenced = _broken(("## Improvement Value", "```\n## Improvement Value"))
    code, result = _rules_result(tmp_path, fenced + "```\n")
    assert code == 1 and result["missing_tables"] == ["Improvement Value"], result


def test_an_unreadable_rules_file_exits_2_with_json(tmp_path):
    proc = _run("rules", "--rules", tmp_path / "missing.md")
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "error"


# --------------------------------------------------------------------------
# verdicts: the [VS] rows joined to the inventory and the scope
# --------------------------------------------------------------------------

GENERATED = "2026-10-01T10:00:00Z"
VS_ROWS = [
    ("loro", "yjs", "Blocked", "no bridge between the two"),
    ("Yjs", "Loro", "Plausible", "every check passed"),
    ("loro", "fastapi", "Risky", "fastapi is out of scope"),
    ("cycle", "loro \u2192 yjs \u2192 loro", "Risky", "circular integration dependency detected"),
    ("redis", "yjs", "Verified", "yjs cites redis"),
    ("loro", "mongo", "Risky", "no skill for mongo"),
]
SKILL_TERMS = [{"name": "loro", "aliases": ["loro-crdt"]}, "yjs", "fastapi",
               {"name": "redis-cache", "aliases": ["Redis"]}]


def _vs_report(rows=VS_ROWS, generated_at=GENERATED, verdict_row=None) -> str:
    lines = ["---", 'schemaVersion: "1.0"', "reportType: feasibility", 'overallVerdict: "CONDITIONALLY_FEASIBLE"']
    if generated_at:
        lines.append(f'generatedAt: "{generated_at}"')
    lines += ["---", "", "# Feasibility Report", ""]
    for section in ("Executive Summary", "Coverage Analysis", "Integration Verdicts", "Recommendations",
                    "Evidence Sources"):
        lines += [f"## {section}", "", f"Body text for {section}.", ""]
        if section == "Integration Verdicts":
            lines += ["| lib_a | lib_b | verdict | rationale |", "|-------|-------|---------|-----------|"]
            lines += [f"| {a} | {b} | {v} | {r} |" for a, b, v, r in rows]
            lines.append("")
    return "\n".join(lines) + "\n"


def _verdicts(tmp_path, report=None, generated_at=GENERATED, skills=None, in_scope="loro,yjs,redis-cache",
              rules=BUNDLED_RULES):
    report_path = _write(tmp_path / "feasibility-report-app-latest.md", _vs_report() if report is None else report)
    skills_path = _write(tmp_path / "skill-terms.json", json.dumps(SKILL_TERMS if skills is None else skills))
    proc = _run("verdicts", "--report", report_path, "--generated-at", generated_at, "--skills", skills_path,
                "--in-scope", in_scope, "--rules", _rules(tmp_path, rules))
    return proc.returncode, json.loads(proc.stdout)


def test_verdicts_route_each_row_by_the_inventory_and_the_scope(tmp_path):
    code, result = _verdicts(tmp_path)
    assert code == 0 and result["status"] == "ok", result
    joined = [(r["skill_a"], r["skill_b"], r["verdict"], r["raises"]) for r in result["in_scope"]]
    assert joined == [("loro", "yjs", "Blocked", "Critical"), ("yjs", "loro", "Plausible", "Minor"),
                      ("redis-cache", "yjs", "Verified", None)]
    left = [(r["lib_a"], r["reason"]) for r in result["out_of_scope"]]
    assert left == [("loro", "out-of-scope"), ("cycle", "no-inventory-skill"), ("loro", "no-inventory-skill")]
    assert result["issue_count"] == 2
    assert result["generatedAt"] == GENERATED and result["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    # Each row keeps what the report says, for the issue's citation.
    assert result["in_scope"][0]["rationale"] == "no bridge between the two"


def test_an_alias_two_skills_share_names_neither(tmp_path):
    skills = [{"name": "vue-runtime", "aliases": ["core"]}, {"name": "vue-compiler", "aliases": ["core"]}, "yjs"]
    report = _vs_report(rows=[("core", "yjs", "Risky", "x"), ("vue-runtime", "yjs", "Risky", "y")])
    code, result = _verdicts(tmp_path, report=report, skills=skills, in_scope="vue-runtime,vue-compiler,yjs")
    assert code == 0, result
    assert [r["lib_a"] for r in result["out_of_scope"]] == ["core"]
    assert [(r["skill_a"], r["raises"]) for r in result["in_scope"]] == [("vue-runtime", "Major")]


def test_a_row_naming_one_skill_twice_is_left_out(tmp_path):
    # A name and an alias of one skill are no pair: the pair lists never held one.
    report = _vs_report(rows=[("loro", "Loro-CRDT", "Risky", "x"), ("loro", "yjs", "Risky", "y")])
    code, result = _verdicts(tmp_path, report=report)
    assert code == 0, result
    left = [(r["skill_a"], r["skill_b"], r["reason"]) for r in result["out_of_scope"]]
    assert left == [("loro", "loro", "same-skill")]
    assert [(r["skill_a"], r["skill_b"]) for r in result["in_scope"]] == [("loro", "yjs")]
    assert result["issue_count"] == 1


def test_a_renamed_rules_copy_raises_its_own_tiers(tmp_path):
    rules = BUNDLED_RULES.replace("**Critical**", "**Blocker**")
    code, result = _verdicts(tmp_path, rules=rules)
    assert code == 0, result
    assert result["in_scope"][0]["raises"] == "Blocker"


STALE = [
    pytest.param({"generated_at": "2026-09-30T08:00:00Z"}, "report", "[VS] rewrote it", id="rewritten"),
    pytest.param({"report": _vs_report(rows=[("loro", "yjs", "RISKY", "x")])}, "report",
                 "no longer passes the feasibility-report contract", id="breaks-the-contract"),
    pytest.param({"rules": BUNDLED_RULES.replace("## Gap Classification", "## Gaps")}, "rules",
                 "lacks the Gap Classification table", id="rules-fail-the-check"),
]


@pytest.mark.parametrize(("change", "source", "detail"), STALE)
def test_a_changed_report_or_rules_that_fail_the_check_are_stale(tmp_path, change, source, detail):
    code, result = _verdicts(tmp_path, **change)
    assert code == 1 and result["status"] == "stale", result
    assert any(p["source"] == source and detail in p["detail"] for p in result["problems"]), result["problems"]


def test_a_report_that_cannot_be_read_again_is_stale(tmp_path):
    skills = _write(tmp_path / "skill-terms.json", json.dumps(SKILL_TERMS))
    proc = _run("verdicts", "--report", tmp_path / "gone.md", "--generated-at", GENERATED, "--skills", skills,
                "--in-scope", "loro", "--rules", RULES_PATH)
    assert proc.returncode == 1
    [problem] = json.loads(proc.stdout)["problems"]
    assert problem["source"] == "report" and "cannot be read again" in problem["detail"]


def test_an_empty_generated_at_matches_a_report_without_one(tmp_path):
    code, result = _verdicts(tmp_path, report=_vs_report(generated_at=None), generated_at="")
    assert code == 0, result
    code, result = _verdicts(tmp_path, report=_vs_report(generated_at=None))
    assert code == 1 and "not 2026-10-01T10:00:00Z" in result["problems"][0]["detail"]


@pytest.mark.parametrize("skills", ['{"loro": []}', '[{"aliases": ["x"]}]', "not json"],
                         ids=["object", "no-name", "not-json"])
def test_a_skills_file_that_is_not_an_array_of_skills_exits_2(tmp_path, skills):
    report = _write(tmp_path / "report.md", _vs_report())
    proc = _run("verdicts", "--report", report, "--generated-at", GENERATED,
                "--skills", _write(tmp_path / "skills.json", skills), "--in-scope", "loro", "--rules", RULES_PATH)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "error"


def test_a_missing_reader_exits_3(tmp_path, monkeypatch, capsys):
    assert mod.FEASIBILITY_READER.as_posix().endswith("src/shared/scripts/skf-validate-feasibility-report.py")
    monkeypatch.setattr(mod, "FEASIBILITY_READER", tmp_path / "missing" / "skf-validate-feasibility-report.py")
    report = _write(tmp_path / "report.md", _vs_report())
    skills = _write(tmp_path / "skills.json", json.dumps(SKILL_TERMS))
    code = mod.main(["verdicts", "--report", str(report), "--generated-at", GENERATED, "--skills", str(skills),
                     "--in-scope", "loro", "--rules", str(RULES_PATH)])
    assert code == 3
    assert "feasibility-report reader is not installed" in json.loads(capsys.readouterr().out)["error"]
