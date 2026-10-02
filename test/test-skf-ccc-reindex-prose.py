#!/usr/bin/env python3
"""Prose pins: ccc setting changes are applied with a plain index, never a reset.

ccc reads `settings.yml` again on every index run, so a plain `ccc index`
(or `ccc search --refresh`) applies an edited `exclude_patterns` or
`include_patterns` list. `ccc reset` deletes only the index databases, keeps
`settings.yml`, and run from a folder without its own settings file it
deletes the enclosing project's index. These tests keep the create-skill
step files and the ccc knowledge fragment on that contract:
- no workflow or shared file tells the agent to run `ccc reset`, and the
  one repair procedure forbids it;
- create-skill writes a workspace clone's `settings.yml` only through
  `skf-merge-ccc-exclusions.py --clone-root` (whose tests pin the `**/name`
  form and the single-quoted items), and every pattern a step shows the user
  to add is a single-quoted YAML item (YAML reads an unquoted leading `*` as
  an alias, and ccc then cannot load the file);
- a reused workspace index still gets the standard exclusions and a plain
  `ccc index`, and the deferred discovery block needs no `--refresh`;
- the verify-and-repair procedure is written once, in
  references/ccc-index-check.md, which step 3 and step 7 both load: its
  repairs fix `settings.yml` (a project of its own, or a missing language in
  `include_patterns`, skipped when no extension is missing), it waits for a
  running pass with `ccc index` rather than a sleep, and it edits only a
  clone SKF made;
- step 7 indexes SKF's workspace clone of a remote source, never the private
  tree, and checks the project-root exception before any `ccc init`;
- create-skill discovery branches on every `ccc_index.status` value setup
  writes (setup never writes "stale") plus any other status: all but "none"
  and "failed" search setup's index with `--refresh` under a timeout with a
  plain-search fallback, "skipped" included, because `--ccc-skip-index`
  still writes `settings.yml` with the SKF exclusions; "none" and "failed"
  index lazily. Create-stack-skill integration detection and the
  extraction-patterns summary state the same rule, and no reader gates on a
  subset of those statuses or names "stale" as a live one;
- every step that runs ccc outside the project root, and every move of a
  workspace clone, runs `skf-ccc-git-hygiene.py`, which never gates: a workspace
  clone gets ccc's `.gitignore` edit undone and the index and lock listed
  in `.git/info/exclude`, a nested local index gets a self-ignoring
  `.cocoindex_code/.gitignore`, and the lazy index never initializes the
  enclosing checkout; audit's `[C]` reads the upstream ref into a private
  tree and moves no clone, so it runs no clean-up (#588);
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
CCC_CHECK = SRC / "skf-create-skill" / "references" / "ccc-index-check.md"
CCC_DISCOVER = SRC / "skf-create-skill" / "references" / "sub" / "ccc-discover.md"
CCC_BRIDGE = SRC / "knowledge" / "ccc-bridge.md"
SOURCE_RESOLUTION = SRC / "skf-create-skill" / "references" / "source-resolution-protocols.md"
TIER_DEGRADATION = SRC / "skf-create-skill" / "references" / "tier-degradation-rules.md"
UPDATE_WRITE = SRC / "skf-update-skill" / "references" / "write.md"
AUDIT_INIT = SRC / "skf-audit-skill" / "references" / "init.md"
# The upstream-moved gate step 1 §5b loads, whose [C] reads the private tree.
AUDIT_CHECKOUT = SRC / "skf-audit-skill" / "references" / "upstream-checkout.md"
TROUBLESHOOTING = REPO_ROOT / "docs" / "troubleshooting.md"
HYGIENE_HELPER = SRC / "shared" / "scripts" / "skf-ccc-git-hygiene.py"
SETUP_ENVELOPE_SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-setup-result-envelope.v1.json"
STEP_FILES = sorted(SRC.glob("skf-*/references/**/*.md"))
# Every markdown file a workflow can load: SKILL.md files, step files and the
# shared references. The reset and citation guards scan all of them.
WORKFLOW_FILES = sorted({*SRC.glob("skf-*/**/*.md"), *SRC.glob("shared/**/*.md")})

FORBID = "Do not run `ccc reset`"
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


def _extract_index() -> str:
    return _extract_item(2, "Index the clone", "3. **Construct semantic query")


def _generate_6b() -> str:
    return _slice(_read(GENERATE), "### 6b.", "### 7.")


def _generate_repair() -> str:
    return _slice(_generate_6b(), "**Verify the index is not degraded:**", "**Registry update:**")


def _check_repair() -> str:
    """The one verify-and-repair procedure, from its repair section to its end."""
    text = _read(CCC_CHECK)
    return text[text.index("## 3. Repair"):]


def _check_branch(owner: str) -> str:
    """The `skf` or `user` branch of the language repair."""
    repair = _slice(_check_repair(), "**Language not included:**", "A plain `ccc index` is enough")
    return _slice(repair, f"   - `{owner}`:", "\n")


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


def test_the_one_repair_procedure_forbids_ccc_reset():
    section = _check_repair()
    assert FORBID in section
    assert "A plain `ccc index` is enough after any `settings.yml` edit" in section


@pytest.mark.parametrize("path, section", [
    (EXTRACT, ("**Deferred CCC Discovery", "**CCC Discovery Integration")),
    (GENERATE, ("### 6b.", "### 7.")),
], ids=["extract", "generate-6b"])
def test_both_stages_load_the_one_check(path, section):
    """The verify-and-repair procedure is written once, in the file both stages load."""
    text = _read(path)
    assert yaml.safe_load(_frontmatter(text))["cccIndexCheckData"] == "references/ccc-index-check.md"
    body = _slice(text, *section)
    assert "load `{cccIndexCheckData}` and run it with `{ccc_root}`" in body
    for copy in ("Indexing in progress:", "**No project of its own:**", "**Language not included:**",
                 "Do not run `ccc reset`"):
        assert copy not in body, copy


def test_the_check_is_written_once():
    for path in sorted((SRC / "skf-create-skill").rglob("*.md")):
        count = _read(path).count("**Language not included:**")
        assert count == (1 if path == CCC_CHECK else 0), path.relative_to(REPO_ROOT)


def test_standard_exclusions_are_merged_by_the_helper():
    """The model never appends to a clone's settings.yml by hand: the helper owns the list and its quoting."""
    item = _extract_item(1, "Prepare the settings", "2. **Index the clone")
    assert 'uv run {mergeCccExclusionsHelper} --clone-root "{remote_clone_path}"' in item
    assert "`**/node_modules`" in item
    assert _fences(item) == [], "the standard exclusions live in the helper, not in a fence of step prose"
    assert "keeping every entry already there" in item
    assert "set `{ccc_discovery: []}` and continue" in item
    for path in sorted((SRC / "skf-create-skill").rglob("*.md")):
        text = _read(path)
        for by_hand in ("Read `settings.yml` and append", "put single quotes around each unquoted",
                        "append one single-quoted"):
            assert by_hand not in text, (path.relative_to(REPO_ROOT), by_hand)
    frontmatter = yaml.safe_load(_frontmatter(_read(EXTRACT)))
    assert frontmatter["mergeCccExclusionsProbeOrder"][-1] == "{project-root}/src/shared/scripts/skf-merge-ccc-exclusions.py"


def test_unquoted_yaml_glob_item_breaks_settings():
    # The reason the prose insists on quotes: ccc loads settings.yml with a
    # YAML safe loader, which rejects a plain scalar that starts with `*`.
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load("exclude_patterns:\n- **/build\n")
    assert yaml.safe_load("exclude_patterns:\n- '**/build'\n") == {"exclude_patterns": ["**/build"]}


@pytest.mark.parametrize("owner", ["skf", "user"])
def test_added_include_patterns_are_single_quoted(owner):
    branch = _check_branch(owner)
    assert QUOTED_INCLUDE_ITEM in branch
    assert "single-quoted" in branch
    for bare in ("one `**/*.{ext}` entry", "`**/*.{ext}` entry per"):
        assert bare not in branch, bare


def test_user_settings_hint_is_single_quoted():
    hint = _check_branch("user")
    assert "do not edit them" in hint
    assert QUOTED_INCLUDE_ITEM in _slice(hint, "the exact lines to add", "followed by a plain `ccc index`")


def test_no_unquoted_yaml_glob_items_in_prose():
    for path in [*WORKFLOW_FILES, CCC_BRIDGE]:
        match = UNQUOTED_GLOB_ITEM_RE.search(_read(path))
        assert match is None, (
            f"{path.relative_to(REPO_ROOT)} shows an unquoted YAML glob item: "
            f"{_read(path)[match.start():match.start() + 40]!r}"
        )


def test_reused_index_applies_standard_exclusions():
    item = _extract_item(1, "Prepare the settings", "2. **Index the clone")
    assert "--clone-root \"{remote_clone_path}\"" in item
    assert "on a first run and on a reused index alike" in item
    assert "run step 3" not in item
    for gone in ("skip steps 2-3", "proceed directly to step 4", "--refresh"):
        assert gone not in item, gone
    assert "Added {patterns_added} standard exclusions to the reused workspace index settings." in item
    assert "When `settings_yml_existed` is true and `patterns_added_list` is not empty" in item


def test_deferred_discovery_needs_no_refresh_flag():
    block = _deferred_block()
    assert "--refresh" not in block
    search = _extract_item(4, "Execute search", "5. **Store results")
    assert 'ccc search --limit 20 "{query}"' in search


def test_degraded_index_repair_targets_settings():
    section = _read(CCC_CHECK)
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
        "it adds nothing",
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
    for step in (_extract_index(), _generate_repair()):
        assert "load `{cccIndexCheckData}`" in step


def test_language_repair_skips_when_no_extension_is_missing():
    none = "the files are excluded rather than left out of `include_patterns`"
    covers = "`exclude_patterns` entry covers the `{brief.language}` source files"
    skf = _check_branch("skf")
    # Only extensions an include entry already matches point at an exclusion: with no include list,
    # the helper added nothing and the files were never excluded.
    assert "When `includes_covered_list` holds every extension, " + none in skf
    assert "When `includes_added_list` is empty" not in skf
    assert "skip this repair" in skf and covers in skf
    assert skf.index("`--include-ext` per extension") < skf.index("When `includes_covered_list` holds")
    no_list = _slice(skf, "On a file with no `include_patterns` list", "When `includes_covered_list`")
    assert "has no `include_patterns` list to add the `{brief.language}` file types to" in no_list
    assert "return **degraded**" in no_list
    user = _check_branch("user")
    assert "If there are none, " + none in user and covers in user
    assert user.index(none) < user.index(QUOTED_INCLUDE_ITEM)


def test_generate_6b_skips_language_check_when_unverified():
    wait = _slice(_read(CCC_CHECK), "## 1. Wait for the Pass", "## 2.")
    assert "return **index unverified** to the caller and skip §2 and §3" in wait
    check = _slice(_read(CCC_CHECK), "## 2. Check the Languages", "## 3.")
    assert "Once the line is gone, read the `Languages:` breakdown" in check
    section = _generate_repair()
    assert 'On **index unverified**, log "index unverified" and continue with **Keep the index out of git**' in section


def test_generate_6b_edits_include_patterns_only_in_skf_clones():
    pick = _slice(_generate_6b(), "**Pick the folder:**", "**Index verification:**")
    assert "bind `{ccc_root}` ← `{remote_clone_path}` and `{ccc_settings_owner}` ← `skf`" in pick
    assert "bind `{ccc_root}` ← `{source_root}` and `{ccc_settings_owner}` ← `user`" in pick
    assert "`skf` when `{ccc_root}` is SKF's workspace clone of a remote source" in _read(CCC_CHECK)
    assert 'uv run {mergeCccExclusionsHelper} --clone-root "{ccc_root}" --include-ext {ext}' in _check_branch("skf")
    assert "do not edit them" in _check_branch("user")
    assert "--clone-root" not in _check_branch("user")


def test_project_root_without_settings_is_not_initialized_in_6b():
    section = _generate_6b()
    guard = _slice(section, "**Project root without settings:**", "\n\n")
    assert "`{ccc_root}` is `{project-root}`" in guard
    assert "`{project-root}/.cocoindex_code/settings.yml` does not exist" in guard
    assert "do not run `ccc init` or `ccc index`" in guard
    assert "`/skf-setup`" in guard
    assert "registry update" in guard
    assert "before running any ccc command" in guard
    exception = section.index("**Project root without settings:**")
    assert exception < section.index("requires the directory to be initialized first")
    assert exception < section.index('ccc init` (idempotent')
    assert exception < section.index("**Nested project marker:**")


def test_generate_6b_indexes_the_workspace_clone_never_the_tree():
    """The private tree is removed in §7: an index or registry entry there would outlive nothing."""
    pick = _slice(_generate_6b(), "**Pick the folder:**", "**Index verification:**")
    assert "the index belongs in SKF's workspace clone, which persists, and not in the tree" in pick
    assert "When it left `{remote_clone_path}` null" in pick and "skip the rest of this section" in pick
    # A docs-only brief has no source: it never indexes or registers a folder another brief left bound.
    bullets = [line for line in pick.splitlines() if line.startswith("- **")]
    assert bullets[0].startswith('- **Docs-only skill** (`source_type: "docs-only"`)')
    assert "Skip the rest of this section." in bullets[0]
    registry = _slice(_generate_6b(), "**Registry update:**", "**Error handling:**")
    assert '"path": "{ccc_root}"' in registry
    assert "{source_tree}" not in _generate_6b()


def _function_text(path: Path, name: str) -> str:
    text = _read(path)
    start = text.index(f"def {name}(")
    end = text.find("\ndef ", start + 1)
    return text[start:end if end > 0 else len(text)]


def _setup_written_statuses() -> set[str]:
    """Every `ccc_index.status` value setup records (#592: helpers, not step prose, set it):
    the merge helper's index result, and the none and failed write-tools records."""
    scripts = SRC / "shared" / "scripts"
    found = set(re.findall(r'"status": "([a-z]+)"', _function_text(scripts / "skf-merge-ccc-exclusions.py",
                                                                   "build_index")))
    found |= set(re.findall(r'"status": "([a-z]+)"', _function_text(scripts / "skf-forge-tier-rw.py",
                                                                    "_staged_ccc_index")))
    assert found, "no ccc_index status found in the setup helpers"
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
NESTED_CMD = 'uv run {cccGitHygieneHelper} nested --dir "{source_root}" --project-root "{project-root}"'
GENERATE_NESTED_CMD = 'uv run {cccGitHygieneHelper} nested --dir "{ccc_root}" --project-root "{project-root}"'
NOTICE_BINDING = "`{ccc_ignore_notice}` ← `notice`"
# The notice carries a quoted `git rm -r --cached -- "<dir>"` remedy: shown as printed.
NOTICE_DISPLAY = "display `{ccc_ignore_notice}` verbatim when it is not null"


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
    ],
    ids=["extract", "update-write", "generate", "ccc-discover"],
)
def test_hygiene_probe_order_declared(loader, users):
    frontmatter = _frontmatter(_read(loader))
    assert HYGIENE_PROBE_BLOCK in frontmatter
    assert yaml.safe_load(frontmatter)["cccGitHygieneProbeOrder"] == HYGIENE_PROBE_PATHS
    assert "never gates the workflow" in HYGIENE_PROBE_BLOCK
    assert "HALT" not in HYGIENE_PROBE_BLOCK
    for user in users:
        assert "{cccGitHygieneHelper}" in _read(user), user.relative_to(REPO_ROOT)


def _resolve_command() -> str:
    """extract.md §2b's fenced resolve command, its backslash continuations joined."""
    section = _slice(_read(EXTRACT), "### 2b. Resolve Source Access", "**Deferred CCC Discovery")
    [fence] = [f for f in _fences(section) if "resolve" in f]
    return " ".join(line.strip().rstrip("\\").strip() for line in fence.strip().splitlines())


def test_resolve_runs_hygiene_before_it_moves_the_clone():
    """create-skill no longer fetches or checks out the workspace clone itself: resolve does, hygiene first."""
    command = _resolve_command()
    assert "--update-clone" in command
    assert '[--hygiene-helper "{cccGitHygieneHelper}"]' in command
    remote = _slice(_read(SOURCE_RESOLUTION), "## Remote Source Resolution", "## Source Commit Capture")
    assert "after running `{cccGitHygieneHelper}` there" in remote
    assert "never forcing a checkout" in remote
    # Regression guard only: the check is ccc's exact edit, never a status gate.
    for path in sorted((SRC / "skf-create-skill").rglob("*.md")):
        text = _read(path)
        for by_hand in ("status --porcelain", "fetch origin", "checkout FETCH_HEAD", "git clone --depth"):
            assert by_hand not in text, (path.relative_to(REPO_ROOT), by_hand)


def test_no_create_skill_step_holds_the_workspace_lock():
    """The clone lock lives inside the helper call that moves the clone, never across tool calls."""
    for path in sorted((SRC / "skf-create-skill").rglob("*.md")):
        text = _read(path)
        for gone in ("**Concurrency guard:**", "flock -x", "fcntl.flock", "acquire the lock"):
            assert gone not in text, (path.relative_to(REPO_ROOT), gone)
    remote = _slice(_read(SOURCE_RESOLUTION), "## Remote Source Resolution", "## Source Commit Capture")
    assert "moves SKF's workspace clone to the same commit in the same call" in remote
    assert "under the clone's `.skf-workspace.lock`" in remote


def test_no_ephemeral_clone_is_left():
    """The private tree replaced the ephemeral fallback clone and its cleanup."""
    for path in sorted((SRC / "skf-create-skill").rglob("*.md")):
        text = _read(path)
        for gone in ("ephemeral", "remote_clone_type", "{temp_path}", "{workspace_repo_path}"):
            assert gone not in text, (path.relative_to(REPO_ROOT), gone)


def test_only_the_ccc_steps_name_the_workspace_clone():
    """`{remote_clone_path}` is SKF's clone, which another run can move: only ccc indexes it."""
    allowed = {
        "extract.md": _slice(_read(EXTRACT), "### 2b. Resolve Source Access", "### 2a."),
        "generate-artifacts.md": _generate_6b(),
        "source-resolution-protocols.md": _slice(_read(SOURCE_RESOLUTION), "## Shell Path Quoting",
                                                 "## Tag Resolution"),
    }
    for path in sorted((SRC / "skf-create-skill").rglob("*.md")):
        text = _read(path)
        for line in text.splitlines():
            if "remote_clone_path" in line:
                assert line in allowed.get(path.name, ""), (path.relative_to(REPO_ROOT), line[:100])
    # extraction reads the tree §2b resolved: the runner itself, a branch without it through its list
    extraction = _slice(_read(EXTRACT), "### 4. Execute Tier-Dependent Extraction", "### 4b.")
    assert "whose recipe runner reads `{source_root}` itself" in extraction
    assert "reads the §2 filtered file list: build it first, from `{source_root}`, when §2 did not" in extraction
    assert "step 1's file tree" not in extraction
    # the demo scan lists the tree extraction reads, not SKF's clone
    component = _read(SRC / "skf-create-skill" / "references" / "component-extraction.md")
    assert 'demo --source-root "{source_root}"' in component


def test_extract_leaves_workspace_clone_clean():
    block = _deferred_block()
    marker = "**Leave the workspace clone clean:**"
    assert block.index("6. **On failure:**") < block.index(marker)
    clean = block[block.index(marker):]
    for token in ('uv run {cccGitHygieneHelper} workspace --repo "{remote_clone_path}"',
                  "after step 5 or step 6", "step 1 or step 2"):
        assert token in clean, token
    # The sentence reads "... and read nothing from its output".
    assert "read nothing from its output" in clean.lower()
    for path in sorted(SRC.rglob("*.md")):
        assert ".forge-sources" not in _read(path), path.relative_to(REPO_ROOT)


def test_generate_6b_keeps_index_out_of_git():
    repair = _generate_repair()
    marker = "**Keep the index out of git:**"
    assert repair.index("load `{cccIndexCheckData}`") < repair.index(marker)
    keep = repair[repair.index(marker):]
    for token in ('uv run {cccGitHygieneHelper} workspace --repo "{ccc_root}"', GENERATE_NESTED_CMD,
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


def test_audit_reads_a_private_tree_and_moves_no_clone():
    """#588: audit's [C] used to check the shared clone out in place, after a
    hygiene pass and a dirty-worktree probe; it now reads the upstream ref
    into a private tree, so the clone keeps its checkout and needs no
    clean-up. The [C] lives in upstream-checkout.md, which init.md loads when
    upstream moved."""
    for path in (AUDIT_INIT, AUDIT_CHECKOUT):
        for gone in ("cccGitHygiene", "git checkout", "git stash", "stash pop"):
            assert gone not in _read(path), (path.name, gone)
    upstream = _slice(_read(AUDIT_CHECKOUT), "**Gate handling:**", "**Headless default**")
    assert 'uv run {sourceTreeHelper} resolve --source-repo "{source_repo}"' in upstream
    assert "never writes to the clone (the call passes no `--update-clone`)" in upstream


def test_tier_degradation_mentions_hygiene():
    text = _read(TIER_DEGRADATION)
    item1 = _line_starting(text, "1. `skf-source-tree.py resolve` reads")
    assert "git hygiene check" in item1 and "`.gitignore`" in item1
    # resolve itself reports a missing git: no step runs `git --version` first.
    assert "resolve reports `git-unavailable`" in _line_starting(text, "2. When `git` is missing")
    assert "git --version" not in text
    assert "fetch or checkout fails" in _line_starting(text, "6. If")


def test_ccc_bridge_keeps_indexes_out_of_git():
    text = _read(CCC_BRIDGE)
    exclusion = _slice(text, "### Exclusion Patterns", "### Deferred Discovery")
    for token in ("`.cocoindex_code/.gitignore` holding `*`", "SKF never edits a project's own `.gitignore`",
                  "`git check-ignore -q --no-index`", "`.git/info/exclude`"):
        assert token in exclusion, token
    deferred = _slice(text, "### Deferred Discovery", "### Relationship to QMD Registry")
    for token in ("skf-ccc-git-hygiene.py workspace", "`/.skf-workspace.lock`", "never the tree",
                  "skf-merge-ccc-exclusions.py --clone-root"):
        assert token in deferred, token
    assert "ephemeral" not in deferred
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
