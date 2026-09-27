#!/usr/bin/env python3
"""Prose pins: ccc setting changes are applied with a plain index, never a reset.

ccc reads `settings.yml` again on every index run, so a plain `ccc index`
(or `ccc search --refresh`) applies an edited `exclude_patterns` or
`include_patterns` list. `ccc reset` deletes only the index databases, keeps
`settings.yml`, and run from a folder without its own settings file it
deletes the enclosing project's index. These tests keep the create-skill
step files and the ccc knowledge fragment on that contract:
- no workflow or shared file tells the agent to run `ccc reset`, and both
  repair sites forbid it;
- the workspace standard exclusions use the `**/name` form (a trailing-slash
  form such as `build/` matches nothing in ccc), and every pattern SKF adds
  to `settings.yml` is a single-quoted YAML item (YAML reads an unquoted
  leading `*` as an alias, and ccc then cannot load the file);
- a reused workspace index still gets the standard exclusions and a plain
  `ccc index`, and the deferred discovery block needs no `--refresh`;
- both degraded-index repairs fix `settings.yml` (a project of its own, or a
  missing language in `include_patterns`, skipped when no extension is
  missing), wait for a running pass with `ccc index` rather than a sleep,
  and step 7 edits only a clone SKF made;
- step 7 checks the project-root exception before any `ccc init`;
- create-skill discovery branches on every `ccc_index.status` value setup
  writes (setup never writes "stale") plus any other status: all but "none"
  and "failed" search setup's index with `--refresh` under a timeout with a
  plain-search fallback, "skipped" included, because `--ccc-skip-index`
  still writes `settings.yml` with the SKF exclusions; "none" and "failed"
  index lazily. Create-stack-skill integration detection and the
  extraction-patterns summary state the same rule, and no reader gates on a
  subset of those statuses or names "stale" as a live one;
- every step that runs ccc outside the project root, and every workspace
  fetch or checkout, runs `skf-ccc-git-hygiene.py`, which never gates: a workspace
  clone gets ccc's `.gitignore` edit undone and the index and lock listed
  in `.git/info/exclude`, a nested local index gets a self-ignoring
  `.cocoindex_code/.gitignore`, the lazy index never initializes the
  enclosing checkout, and audit's `[C]` checkout cleans up before its
  dirty-worktree probe;
- no step prose cites ccc source lines.

Every section slicer asserts that its markers exist and that the slice is
not empty, so a renamed heading fails instead of passing vacuously.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src"
EXTRACT = SRC / "skf-create-skill" / "references" / "extract.md"
GENERATE = SRC / "skf-create-skill" / "references" / "generate-artifacts.md"
CCC_DISCOVER = SRC / "skf-create-skill" / "references" / "sub" / "ccc-discover.md"
CCC_BRIDGE = SRC / "knowledge" / "ccc-bridge.md"
SOURCE_RESOLUTION = SRC / "skf-create-skill" / "references" / "source-resolution-protocols.md"
TIER_DEGRADATION = SRC / "skf-create-skill" / "references" / "tier-degradation-rules.md"
UPDATE_WRITE = SRC / "skf-update-skill" / "references" / "write.md"
AUDIT_INIT = SRC / "skf-audit-skill" / "references" / "init.md"
TROUBLESHOOTING = REPO_ROOT / "docs" / "troubleshooting.md"
HYGIENE_HELPER = SRC / "shared" / "scripts" / "skf-ccc-git-hygiene.py"
SETUP_REFS = SRC / "skf-setup" / "references"
SETUP_ENVELOPE_SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-setup-result-envelope.v1.json"
STEP_FILES = sorted(SRC.glob("skf-*/references/**/*.md"))
# Every markdown file a workflow can load: SKILL.md files, step files and the
# shared references. The reset and citation guards scan all of them.
WORKFLOW_FILES = sorted({*SRC.glob("skf-*/**/*.md"), *SRC.glob("shared/**/*.md")})

FORBID = "Do not run `ccc reset`"
STANDARD_ENTRY_RE = re.compile(r"^\*\*/[A-Za-z0-9_.-]+$")
STANDARD_ITEM_RE = re.compile(r"^- '\*\*/[A-Za-z0-9_.-]+'$")
# A YAML list item whose value starts with an unquoted `*` (an alias).
UNQUOTED_GLOB_ITEM_RE = re.compile(r"(?:^|`)[ \t]*- \*(?:\*/|\.)", flags=re.MULTILINE)
QUOTED_INCLUDE_ITEM = "`- '**/*.{ext}'`"
CCC_SOURCE_CITATION_RE = re.compile(
    r"\b(?:cli|settings|indexer|daemon|project|client|server|query)\.py:\d"
    r"|\(C\d\)|METADATA:\d"
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    section = text[i:j]
    assert section.strip(), f"empty slice between {start!r} and {end!r}"
    return section


def _fences(text: str) -> list[str]:
    return re.findall(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", text, flags=re.DOTALL | re.MULTILINE)


def _deferred_block() -> str:
    return _slice(_read(EXTRACT), "**Deferred CCC Discovery", "**CCC Discovery Integration")


def _extract_item(number: int, heading: str, next_heading: str) -> str:
    return _slice(_deferred_block(), f"{number}. **{heading}", next_heading)


def _extract_repair() -> str:
    return _extract_item(3, "Index the clone", "4. **Construct semantic query")


def _generate_6b() -> str:
    return _slice(_read(GENERATE), "### 6b.", "### 7.")


def _generate_repair() -> str:
    return _slice(_generate_6b(), "**Verify the index is not degraded:**", "**Registry update:**")


def test_step_file_glob_is_recursive():
    assert EXTRACT in STEP_FILES
    assert CCC_DISCOVER in STEP_FILES
    assert set(STEP_FILES) <= set(WORKFLOW_FILES)
    assert SRC / "skf-create-skill" / "SKILL.md" in WORKFLOW_FILES
    assert SRC / "skf-setup" / "SKILL.md" in WORKFLOW_FILES
    assert any(p.is_relative_to(SRC / "shared") for p in WORKFLOW_FILES)


def test_no_step_file_prescribes_ccc_reset():
    for path in WORKFLOW_FILES:
        text = _read(path)
        for block in _fences(text):
            assert "ccc reset" not in block, f"{path.relative_to(REPO_ROOT)} runs ccc reset in a fence"
        for line in text.splitlines():
            if "ccc reset" in line:
                assert line.count("ccc reset") == line.count(FORBID), (
                    f"{path.relative_to(REPO_ROOT)} mentions ccc reset outside a "
                    f"'{FORBID}' sentence: {line[:120]!r}"
                )


@pytest.mark.parametrize("slicer", [_extract_repair, _generate_repair], ids=["extract", "generate-6b"])
def test_repair_sites_forbid_ccc_reset(slicer):
    section = slicer()
    assert FORBID in section
    assert "A plain `ccc index` is enough after any `settings.yml` edit" in section


def test_standard_exclusions_use_double_star_form():
    item = _extract_item(2, "Initialize index", "3. **Index the clone")
    excl = _slice(item, "**Apply standard exclusions", "**Note:**")
    fences = _fences(excl)
    assert len(fences) == 1, "expected exactly one fence with the standard exclusions"
    lines = [line.strip() for line in fences[0].strip().splitlines()]
    for line in lines:
        assert STANDARD_ITEM_RE.match(line), f"not a single-quoted '**/name' YAML item: {line!r}"
    entries = yaml.safe_load(fences[0])
    assert isinstance(entries, list) and entries
    assert len(entries) == len(lines)
    for entry in entries:
        assert STANDARD_ENTRY_RE.match(entry), f"not a **/name entry: {entry!r}"
        assert not entry.endswith("/"), entry
    assert {"**/build", "**/out", "**/node_modules"} <= set(entries)
    assert len(entries) == len(set(entries))
    assert "matches nothing" in excl
    assert "add nothing" in excl
    assert "single-quoted YAML list item" in excl
    assert "alias" in excl


def test_unquoted_yaml_glob_item_breaks_settings():
    # The reason the prose insists on quotes: ccc loads settings.yml with a
    # YAML safe loader, which rejects a plain scalar that starts with `*`.
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load("exclude_patterns:\n- **/build\n")
    assert yaml.safe_load("exclude_patterns:\n- '**/build'\n") == {"exclude_patterns": ["**/build"]}


@pytest.mark.parametrize("slicer", [_extract_repair, _generate_repair], ids=["extract", "generate-6b"])
def test_added_include_patterns_are_single_quoted(slicer):
    section = slicer()
    assert QUOTED_INCLUDE_ITEM in section
    assert "single-quoted" in section
    for bare in ("one `**/*.{ext}` entry", "`**/*.{ext}` entry per"):
        assert bare not in section, bare


def test_generate_6b_display_hint_is_single_quoted():
    section = _generate_repair()
    hint = _slice(section, "Otherwise the settings belong to the user's project", "\n")
    assert QUOTED_INCLUDE_ITEM in hint


def test_no_unquoted_yaml_glob_items_in_prose():
    for path in [*WORKFLOW_FILES, CCC_BRIDGE]:
        match = UNQUOTED_GLOB_ITEM_RE.search(_read(path))
        assert match is None, (
            f"{path.relative_to(REPO_ROOT)} shows an unquoted YAML glob item: "
            f"{_read(path)[match.start():match.start() + 40]!r}"
        )


def test_reused_index_applies_standard_exclusions():
    item = _extract_item(1, "Check existing index", "2. **Initialize index")
    assert "{remote_clone_path}/.cocoindex_code/settings.yml" in item
    assert "standard exclusions" in item
    assert "run step 3" in item
    for gone in ("skip steps 2-3", "proceed directly to step 4", "--refresh"):
        assert gone not in item, gone
    item2 = _extract_item(2, "Initialize index", "3. **Index the clone")
    assert "**Apply standard exclusions (first run and reused index):**" in item2
    assert "Added {N} standard exclusions to the reused workspace index settings." in item2


def test_deferred_discovery_needs_no_refresh_flag():
    block = _deferred_block()
    assert "--refresh" not in block
    search = _extract_item(5, "Execute search", "6. **Store results")
    assert 'ccc search --limit 20 "{query}"' in search


@pytest.mark.parametrize("slicer", [_extract_repair, _generate_repair], ids=["extract", "generate-6b"])
def test_degraded_index_repair_targets_settings(slicer):
    section = slicer()
    for token in (
        "Indexing in progress:",
        "ccc index` again, which waits for the running pass to finish",
        "after 3 such runs",
        "index unverified",
        "Languages:",
        ".cocoindex_code/settings.yml",
        "`Project:` line",
        "ccc init -f",
        "include_patterns",
        "**/*.{ext}",
        "at most 3",
        "add nothing",
    ):
        assert token in section, token
    for gone in (
        "clean init",
        "clean rebuild",
        "forced re-init",
        "Project already initialized",
        "at most 20 times",
        "seconds apart",
    ):
        assert gone not in section, gone
    assert section.index("ccc init -f") < section.index("**/*.{ext}"), "repairs are out of order"


@pytest.mark.parametrize("slicer", [_extract_repair, _generate_repair], ids=["extract", "generate-6b"])
def test_language_repair_skips_when_no_extension_is_missing(slicer):
    section = slicer()
    repair = _slice(section, "**Language not included:**", "A plain `ccc index` is enough")
    none = "If there are none, the files are excluded rather than left out of `include_patterns`"
    assert none in repair
    assert "skip this repair" in repair
    assert "`exclude_patterns` entry covers the `{brief.language}` source files" in repair
    assert repair.index(none) < repair.index(QUOTED_INCLUDE_ITEM)


def test_generate_6b_skips_language_check_when_unverified():
    section = _generate_repair()
    assert "skip the language check and the repairs below" in section
    assert "Once the line is gone, read the `Languages:` breakdown" in section


def test_generate_6b_edits_include_patterns_only_in_skf_clones():
    section = _generate_repair()
    assert "When `{remote_clone_path}` is set and `{source_root}` is inside it" in section
    assert "do not edit them" in section
    assert section.index("is inside it") < section.index("do not edit them")


def test_project_root_without_settings_is_not_initialized_in_6b():
    section = _generate_6b()
    guard = _slice(section, "**Project root without settings:**", "\n\n")
    assert "`{source_root}` is `{project-root}`" in guard
    assert "`{project-root}/.cocoindex_code/settings.yml` does not exist" in guard
    assert "do not run `ccc init` or `ccc index`" in guard
    assert "`/skf-setup`" in guard
    assert "registry update" in guard
    assert "before running any ccc command" in guard
    exception = section.index("**Project root without settings:**")
    assert exception < section.index("requires the directory to be initialized first")
    assert exception < section.index('ccc init` (idempotent')
    assert exception < section.index("**Nested project marker:**")


def _setup_written_statuses() -> set[str]:
    """Every `ccc_index.status` value the setup steps bind (write-config stores it as is)."""
    found: set[str] = set()
    for path in sorted(SETUP_REFS.glob("*.md")):
        found.update(re.findall(r'ccc_index_result: "([a-z]+)"', _read(path)))
    assert found, "no ccc_index_result binding found in the setup steps"
    return found


# The bullet that covers a status setup does not write, such as a "stale"
# an older SKF recorded.
OTHER_STATUS = "*"
# The statuses after which setup built no index: the only ones a reader may
# route away from the refresh search.
NO_INDEX = {"none", "failed"}
DETECT_INTEGRATIONS = SRC / "skf-create-stack-skill" / "references" / "detect-integrations.md"
EXTRACTION_PATTERNS = SRC / "skf-create-skill" / "references" / "extraction-patterns.md"


def _discover_state_branches() -> dict[str, str]:
    """Map each status a ccc-discover section 2 bullet names to that bullet.

    The "Any other status" bullet is keyed as OTHER_STATUS.
    """
    state = _slice(_read(CCC_DISCOVER), "### 2. Check CCC Index State", "**Tool resolution for ccc_bridge.ensure_index")
    branches: dict[str, str] = {}
    for line in state.splitlines():
        if not line.startswith("- "):
            continue
        if line.startswith("- Any other status"):
            statuses = [OTHER_STATUS]
        else:
            statuses = re.findall(r'`"([a-z]+)"`', line.split(":", 1)[0])
        assert statuses, f"section 2 bullet names no status: {line[:80]!r}"
        for status in statuses:
            assert status not in branches, f"status {status!r} has two branches"
            branches[status] = line
    assert branches, "section 2 has no status bullets"
    return branches


def test_setup_writes_the_envelope_status_enum():
    schema = json.loads(_read(SETUP_ENVELOPE_SCHEMA))
    enum = schema["properties"]["skf_setup"]["properties"]["ccc_index"]["properties"]["status"]["enum"]
    assert _setup_written_statuses() == set(enum)
    assert "stale" not in enum
    assert NO_INDEX < set(enum)


def test_ccc_discover_branches_on_every_status_setup_writes():
    assert set(_discover_state_branches()) == _setup_written_statuses() | {OTHER_STATUS}


def test_every_status_with_settings_searches_with_refresh():
    """Only "none" and "failed" skip the refresh search; they index lazily."""
    text = _read(CCC_DISCOVER)
    branches = _discover_state_branches()
    refresh = {status for status, line in branches.items() if line == branches["fresh"]}
    assert refresh == _setup_written_statuses() - NO_INDEX
    branch = branches["fresh"]
    assert "continue to section 3" in branch
    assert "--refresh" in branch
    assert "never needs checking" in branch
    assert "treat it like `\"fresh\"`" in branches[OTHER_STATUS]
    lazy = branches["none"]
    assert lazy == branches["failed"] and "ensure_index" in lazy
    for line in text.splitlines():
        if '"stale"' in line:
            assert line == branches[OTHER_STATUS], f"stale outside the other-status bullet: {line[:80]!r}"
    search = _slice(text, "### 4. Execute CCC Semantic Search", "### 5.")
    marker = '**Setup\'s index (every section 2 status except `"none"` and `"failed"`):**'
    refresh_rule = _slice(search, marker, "\n")
    assert 'ccc search --refresh --limit 20 "{query}"' in refresh_rule
    assert "extended timeout" in refresh_rule
    assert "`refresh_index` set to true" in refresh_rule
    assert "fails or times out" in refresh_rule
    assert 'the plain `cd "{source_root}" && ccc search --limit 20 "{query}"` once' in refresh_rule
    assert "After lazy indexing in section 2, the plain search is enough" in refresh_rule
    assert 'after `"skipped"` there may be no index yet' in refresh_rule


def test_skipped_index_searches_like_fresh():
    """--ccc-skip-index only defers the indexing cost: settings.yml already holds the exclusions."""
    branch = _discover_state_branches()["skipped"]
    assert "`--ccc-skip-index`" in branch
    assert "`settings.yml` with the SKF exclusions" in branch
    assert "only defers the indexing cost" in branch
    for gone in ("Run no ccc command", "{ccc_discovery: []}", "Re-run `/skf-setup` without it",
                 "ensure_index"):
        assert gone not in branch, gone


def test_integration_detection_augments_after_every_status_with_settings():
    """After a first setup the status is "created": a fresh-only gate never augmented."""
    block = _slice(_read(DETECT_INTEGRATIONS), "**CCC Semantic Augmentation", "CCC failures:")
    gate = next(line for line in block.splitlines() if "ccc_index.status" in line)
    skip = _slice(gate, "with one exception", "Every other status augments")
    assert set(re.findall(r'`"([a-z]+)"`', skip)) == NO_INDEX
    assert "skip augmentation" in skip
    rest = gate[gate.index("Every other status augments"):]
    assert {"fresh", "created", "skipped"} <= set(re.findall(r'`"([a-z]+)"`', rest))
    assert "does not know" in rest
    refresh = _slice(block, "**Refresh first:**", "\n")
    assert 'ccc search --refresh --limit 10 "{libA} {libB}"' in refresh
    assert "extended timeout" in refresh and "run the plain search once" in refresh
    assert "`refresh_index` set to true" in refresh


def test_extraction_patterns_state_the_same_status_rule():
    rule = _slice(_read(EXTRACTION_PATTERNS), "### When CCC Pre-Discovery Applies", "### CCC Pre-Ranking")
    line = next(line for line in rule.splitlines() if "ccc_index.status" in line)
    before, after = line.split("first attempts lazy indexing", 1)
    assert {"fresh", "created", "skipped"} <= set(re.findall(r'`"([a-z]+)"`', before))
    assert "does not know" in before and "--refresh" in before
    assert set(re.findall(r'`"([a-z]+)"`', after)) == NO_INDEX


def _status_reader_files() -> list[Path]:
    files = sorted({*SRC.rglob("*.md"), *(REPO_ROOT / "docs").rglob("*.md")})
    readers = [p for p in files if "ccc_index.status" in _read(p)]
    for expected in (CCC_DISCOVER, CCC_BRIDGE, DETECT_INTEGRATIONS, EXTRACTION_PATTERNS):
        assert expected in readers, expected
    return readers


@pytest.mark.parametrize(
    "path", [pytest.param(p, id=p.relative_to(REPO_ROOT).as_posix()) for p in _status_reader_files()]
)
def test_no_reader_limits_the_index_to_a_status_subset(path):
    """A status setup never writes is named only as an older SKF's leftover, and a
    reader naming "fresh" also names "created" and "skipped", which reach the same search."""
    written = _setup_written_statuses()
    for line in _read(path).splitlines():
        if "ccc_index.status" not in line:
            continue
        named = set(re.findall(r'"([a-z]+)"', line.split("ccc_index.status", 1)[1]))
        rel = path.relative_to(REPO_ROOT)
        if named - written:
            assert "older SKF" in line, f"{rel} names {sorted(named - written)}: {line[:120]!r}"
        if "fresh" in named:
            assert {"created", "skipped"} <= named, f"{rel} gates on a subset: {line[:120]!r}"


def test_ccc_exclusions_augmented_removed():
    for path in sorted(SRC.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".py", ".yaml", ".yml", ".csv", ".json"}:
            assert "ccc_exclusions_augmented" not in _read(path), path.relative_to(REPO_ROOT)


def test_ccc_bridge_states_plain_index_applies_edits():
    text = _read(CCC_BRIDGE)
    assert "re-indexes only if files changed" not in text
    exclusion = _slice(text, "### Exclusion Patterns", "### Deferred Discovery")
    assert "plain `ccc index`" in exclusion
    assert "`ccc search --refresh`" in exclusion
    assert "A plain `ccc search` does not re-index" in exclusion
    deferred = _slice(text, "### Deferred Discovery", "### Relationship to QMD Registry")
    assert "{remote_clone_path}/.cocoindex_code/settings.yml" in deferred
    assert "--refresh" not in deferred
    anti = _slice(text, "## Anti-Patterns", "## Related Fragments")
    assert "Running `ccc reset`" in anti
    assert "`**/name` form" in anti
    freshness = _slice(text, "### Freshness", "### Exclusion Patterns")
    assert "`ccc search --refresh`" in freshness
    assert "designated refresh authority" not in freshness
    assert "does not change the recorded status" in freshness
    assert "no status records staleness" in freshness
    assert "A workflow step never computes staleness" in freshness
    assert "stale index" not in freshness
    for line in text.splitlines():
        if '"stale"' in line:
            assert "older SKF" in line, f"stale named as a live status: {line[:80]!r}"
    availability = _slice(text, "## Availability", "## Operations")
    assert "skip ccc discovery silently" in availability
    assert "Create-skill discovery indexes lazily" in availability
    bullets = [line for line in availability.splitlines() if line.startswith("- ")]
    assert len(bullets) == 2, bullets
    searched, no_index = (set(re.findall(r'`"([a-z]+)"`', b.split(":", 1)[0])) for b in bullets)
    assert searched == _setup_written_statuses() - NO_INDEX | {"stale"}
    assert "does not know" in bullets[0] and "`ccc search --refresh`" in bullets[0]
    assert no_index == NO_INDEX
    when = _slice(text, "### When Indexing Happens", "### Freshness")
    assert "create-stack-skill integration detection" in when
    assert "runs no ccc command" not in text
    assert "single-quoted YAML list item" in anti


def test_no_ccc_source_line_citations_in_step_prose():
    for path in [*WORKFLOW_FILES, CCC_BRIDGE]:
        match = CCC_SOURCE_CITATION_RE.search(_read(path))
        assert match is None, f"{path.relative_to(REPO_ROOT)} cites ccc source: {match.group(0)!r}"


# --------------------------------------------------------------------------
# ccc's index folders and SKF's workspace lock stay out of git
# --------------------------------------------------------------------------

HYGIENE_PROBE_BLOCK = (
    "# Resolve `{cccGitHygieneHelper}` to the first existing path. It keeps ccc's\n"
    "# index folders and SKF's workspace lock out of git, and undoes the\n"
    "# `.gitignore` edit `ccc init` makes in a workspace clone. If neither path\n"
    "# exists, skip the call and continue: it never gates the workflow.\n"
    "cccGitHygieneProbeOrder:\n"
    "  - '{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py'\n"
    "  - '{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py'\n"
)
HYGIENE_PROBE_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-ccc-git-hygiene.py",
    "{project-root}/src/shared/scripts/skf-ccc-git-hygiene.py",
]
WORKSPACE_CORE = (
    "The helper lists `.cocoindex_code/` and `/.skf-workspace.lock` in the clone's "
    "`.git/info/exclude`, then restores a tracked `.gitignore` whose only change is those "
    "two lines (or deletes an untracked one that holds only them), and leaves every other "
    "local change alone."
)
WS_CMD = 'uv run {cccGitHygieneHelper} workspace --repo "{workspace_repo_path}"'
NESTED_CMD = 'uv run {cccGitHygieneHelper} nested --dir "{source_root}" --project-root "{project-root}"'
NOTICE_BINDING = "`{ccc_ignore_notice}` ← `notice`"
# The notice carries a quoted `git rm -r --cached -- "<dir>"` remedy: shown as printed.
NOTICE_DISPLAY = "display `{ccc_ignore_notice}` verbatim when it is not null"
CREATE_HIT = "**If `{workspace_repo_path}/.git/` exists (workspace hit):**"
CREATE_MISS = "**If `{workspace_repo_path}/.git/` does not exist (workspace miss):**"


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "no frontmatter"
    end = text.index("\n---\n", 4)
    return text[4:end + 1]


def _line_starting(text: str, prefix: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith(prefix)]
    assert len(lines) == 1, f"expected one line starting {prefix!r}, found {len(lines)}"
    return lines[0]


@pytest.mark.parametrize(
    "loader, users",
    [
        (EXTRACT, [EXTRACT, SOURCE_RESOLUTION]),
        (UPDATE_WRITE, [UPDATE_WRITE]),
        (GENERATE, [GENERATE]),
        (CCC_DISCOVER, [CCC_DISCOVER]),
        (AUDIT_INIT, [AUDIT_INIT]),
    ],
    ids=["extract", "update-write", "generate", "ccc-discover", "audit-init"],
)
def test_hygiene_probe_order_declared(loader, users):
    frontmatter = _frontmatter(_read(loader))
    assert HYGIENE_PROBE_BLOCK in frontmatter
    assert yaml.safe_load(frontmatter)["cccGitHygieneProbeOrder"] == HYGIENE_PROBE_PATHS
    assert "never gates the workflow" in HYGIENE_PROBE_BLOCK
    assert "HALT" not in HYGIENE_PROBE_BLOCK
    for user in users:
        assert "{cccGitHygieneHelper}" in _read(user), user.relative_to(REPO_ROOT)


def _create_hit() -> str:
    return _slice(_read(SOURCE_RESOLUTION), CREATE_HIT, CREATE_MISS)


@pytest.mark.parametrize("slicer", [_create_hit], ids=["create"])
def test_workspace_hit_runs_hygiene_before_fetch(slicer):
    hit = slicer()
    for token in (WS_CMD, WORKSPACE_CORE, "from `{project-root}`", "Read nothing from its output",
                  "never a gate"):
        assert token in hit, token
    assert hit.index(WS_CMD) < hit.index("fetch origin") < hit.index("checkout FETCH_HEAD")
    # Regression guard only: the check is ccc's exact edit, never a status gate.
    assert "status --porcelain" not in hit


def test_workspace_miss_clones_then_locks():
    text = _read(SOURCE_RESOLUTION)
    guard = _slice(text, "**Concurrency guard:**", CREATE_HIT)
    for token in ("never create `{workspace_repo_path}` or the lock file before the clone",
                  "Clone first, then acquire the lock", "`.git/info/exclude`"):
        assert token in guard, token
    assert "Acquire the lock before the workspace-hit check" not in guard
    miss = _slice(text, CREATE_MISS, "4. **If workspace resolution succeeds:**")
    for token in ("**After the clone succeeds:**", "clone_head", WS_CMD, "**Detect tag vs branch**"):
        assert token in miss, token
    assert miss.index("git clone") < miss.index(WS_CMD)
    assert miss.index("**After the clone succeeds:**") < miss.index(WS_CMD)


def test_fallback_trigger_names_checkout():
    step5 = _slice(_read(SOURCE_RESOLUTION), "5. **Ephemeral fallback", "6. **If all cloning fails")
    assert "If the workspace clone, fetch or checkout fails" in step5


def test_extract_leaves_workspace_clone_clean():
    block = _deferred_block()
    marker = "**Leave the workspace clone clean:**"
    assert block.index("7. **On failure:**") < block.index(marker)
    clean = block[block.index(marker):]
    for token in ('uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"',
                  '`remote_clone_type` is `"workspace"`', "after step 6 or step 7", "step 2 or step 3"):
        assert token in clean, token
    # The sentence reads "... and read nothing from its output".
    assert "read nothing from its output" in clean.lower()
    for path in sorted(SRC.rglob("*.md")):
        assert ".forge-sources" not in _read(path), path.relative_to(REPO_ROOT)


def test_generate_6b_keeps_index_out_of_git():
    repair = _generate_repair()
    marker = "**Keep the index out of git:**"
    assert repair.index("A plain `ccc index` is enough") < repair.index(marker)
    keep = repair[repair.index(marker):]
    for token in ('uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"', NESTED_CMD,
                  NOTICE_BINDING, NOTICE_DISPLAY, "SKF never edits a project's own `.gitignore`",
                  "never fails the workflow", 'after "index unverified"'):
        assert token in keep, token
    assert "continue with **Keep the index out of git**" in repair
    assert "continue to the registry update." not in repair
    nested = _slice(_generate_6b(), "**Nested project marker:**", "\n")
    assert "linked worktree or submodule" in nested
    assert "**Keep the index out of git** below" in nested


def test_lazy_index_keeps_to_the_source_folder():
    lazy = _slice(_read(CCC_DISCOVER), "**Tool resolution for ccc_bridge.ensure_index:**", "### 3.")
    for token in ('cd "{source_root}" && ccc init -f',
                  "only once `{source_root}/.cocoindex_code/settings.yml` exists",
                  "**Keep a lazy index out of git:**", NESTED_CMD, NOTICE_BINDING, NOTICE_DISPLAY,
                  "discovery never blocks", "Exception: when `{source_root}` is `{project-root}`"):
        assert token in lazy, token


def test_audit_checkout_clears_ccc_traces_before_dirty_probe():
    text = _read(AUDIT_INIT)
    lock = _slice(text, "**[C]:** Acquire an exclusive lock", "**Dirty-worktree probe")
    assert 'uv run {cccGitHygieneHelper} workspace --repo "{source_root}"' in lock
    assert "after the clean-up above" in text
    for gone in ("CCC daemon appending", "`setup-forge` pointed it", "pop the stash on the way out"):
        assert gone not in text, gone
    stash = _line_starting(text, "- **[T] Transient stash**")
    assert "stash pop" in stash
    assert "'skf-audit-skill: pre-checkout {chosen_ref}'" in stash
    assert "tooling-generated" not in stash


def test_tier_degradation_mentions_hygiene():
    text = _read(TIER_DEGRADATION)
    item2 = _line_starting(text, "2. If `git` is available")
    assert "git hygiene check" in item2 and "`.gitignore`" in item2
    assert "fetch or checkout fails" in _line_starting(text, "6. If")


def test_ccc_bridge_keeps_indexes_out_of_git():
    text = _read(CCC_BRIDGE)
    exclusion = _slice(text, "### Exclusion Patterns", "### Deferred Discovery")
    for token in ("`.cocoindex_code/.gitignore` holding `*`", "SKF never edits a project's own `.gitignore`",
                  "`git check-ignore -q --no-index`", "`.git/info/exclude`"):
        assert token in exclusion, token
    deferred = _slice(text, "### Deferred Discovery", "### Relationship to QMD Registry")
    for token in ("skf-ccc-git-hygiene.py workspace", "`/.skf-workspace.lock`", "ephemeral clone"):
        assert token in deferred, token
    assert "--refresh" not in deferred
    ensure = _slice(text, "### `ccc_bridge.ensure_index(path)`", "### `ccc_bridge.status()`")
    assert "ccc init -f" in ensure
    assert "only once `{path}/.cocoindex_code/settings.yml` exists" in ensure
    when = _slice(text, "### When Indexing Happens", "### Freshness")
    assert "create-skill step 7" in when


def _helper_constant(name: str):
    tree = ast.parse(_read(HYGIENE_HELPER), filename=str(HYGIENE_HELPER))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {HYGIENE_HELPER.name}")


def test_troubleshooting_nested_index_entry():
    heading = "### `git status` lists a `.cocoindex_code` folder inside a source folder"
    entry = _slice(_read(TROUBLESHOOTING), heading, "\n### ")
    for token in ("holding `*`", "never edits your own `.gitignore`", "git rm -r --cached"):
        assert token in entry, token
    assert _helper_constant("SELF_IGNORE").endswith(b"\n*\n")
