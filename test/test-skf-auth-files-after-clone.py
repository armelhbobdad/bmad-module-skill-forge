"""create-skill scans for authoritative files in the tree it resolved.

extract.md §2a runs skf-resolve-authoritative-files.py, which walks a local
directory and refuses anything else. §2b reads a remote source into a private
tree at the resolved commit, so §2a runs after §2b, and a remote source that
was never read into a tree (Quick tier, or a read that failed) skips the scan
with a notice instead of handing the helper a URL. The skip reaches the
evidence report that step 7 writes, under a key of its own, and each brief
of a --batch run starts with no scan record. A halt the scan asks for removes
the tree first.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REFS = REPO_ROOT / "src" / "skf-create-skill" / "references"
EXTRACT = REFS / "extract.md"
PROTOCOL = REFS / "authoritative-files-protocol.md"
GENERATE_ARTIFACTS = REFS / "generate-artifacts.md"

SKIP_RECORD = 'authoritative_files_scan: {not_scanned: "remote source not cloned"}'
FULL_RECORD_RE = re.compile(r"\*\*Record for evidence report:\*\* `authoritative_files_scan: \{([^`]+)\}`")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    """The text from `start` up to `end`."""
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def _step_3_sections() -> list[str]:
    """extract.md's `### <label>.` headings, in document order."""
    return re.findall(r"^### (\w+)\. ", _read(EXTRACT), re.M)


def _scan_section() -> str:
    return _section(_read(EXTRACT), "### 2a. Discovered Authoritative Files Protocol", "### 2c.")


def test_scan_runs_after_source_resolution() -> None:
    sections = _step_3_sections()
    assert sections.index("2") < sections.index("2b") < sections.index("2a") < sections.index("2c")


def test_scope_filters_announce_the_order() -> None:
    scope = _section(_read(EXTRACT), "### 2. Apply Scope Filters", "### 2b.")
    assert "Sections 2b and 2a follow in that order" in scope


def test_scan_walks_the_tree_source_resolution_left() -> None:
    scan = _scan_section()
    assert "**Runs after §2b, not before it.**" in scan
    assert "`{source_root}` now names the local source itself, or the private tree §2b read a remote source into" in scan
    assert "which no other run can move" in scan
    assert ".skf-workspace.lock" not in scan, "no step holds the workspace lock across tool calls"


def test_remote_source_guard_skips_with_a_notice() -> None:
    scan = _scan_section()
    guard = next(p for p in scan.split("\n\n") if p.startswith("**Remote source guard:**"))
    assert "if `source_root` is still a remote URL after §2b" in guard
    assert "a Quick-tier remote source, which §2b never clones" in guard
    assert "a remote source §2b could not read into a tree" in guard
    assert "Skip the scan and continue to §2c" in guard
    assert f"record `{SKIP_RECORD}` for the evidence report" in guard
    assert 'display "**Authoritative files scan skipped:** `{source_repo}` was not cloned' in guard


def test_guard_runs_before_the_protocol_is_loaded() -> None:
    scan = _scan_section()
    assert scan.index("**Remote source guard:**") < scan.index("Load `{authoritativeFilesProtocol}`")


def test_each_brief_starts_with_no_scan_record() -> None:
    """A --batch run comes back through §2a for the next brief in the same context."""
    scan = _scan_section()
    reset = scan.index(
        "**Start clean:** set `authoritative_files_scan` to null and `promoted_docs[]` to empty"
    )
    assert "in a `--batch` run one brief's scan never carries into the next" in scan
    assert reset < scan.index("**Skip this section entirely if") < scan.index("**Remote source guard:**")


def test_skip_record_has_a_key_of_its_own() -> None:
    """The full record counts `skipped` candidates, so the scan skip must not reuse that key."""
    protocol = _read(PROTOCOL)
    [fields] = FULL_RECORD_RE.findall(protocol)
    full_keys = {field.split(":")[0].strip() for field in fields.split(",") if ":" in field}
    assert "skipped" in full_keys
    [skip_key] = re.findall(r"the record is `authoritative_files_scan: \{(\w+):", protocol)
    assert skip_key not in full_keys


def test_protocol_opening_follows_source_access() -> None:
    protocol = _read(PROTOCOL)
    overview = _section(protocol, "## Overview", "## Procedure")
    assert "Before resolving source access" not in protocol
    assert "after `### 2b. Resolve Source Access` has resolved the source to a local tree" in overview
    assert "Once §2b has resolved source access, scan the resolved source tree" in overview
    assert "**Skip it too when `source_root` is still a remote URL**" in overview


def test_protocol_helper_gets_the_resolved_tree() -> None:
    procedure = _section(_read(PROTOCOL), "## Procedure", "## How promoted docs")
    assert '--source-root "{source_root}"' in procedure
    assert "`{source_root}` is the local tree §2b resolved" in procedure


def test_update_halt_removes_the_private_tree() -> None:
    update = _section(_read(PROTOCOL), "- **[U] Update:**", "6. **Summary.**")
    assert ('When `{source_tree}` is set, first run `uv run {sourceTreeHelper} close --tree "{source_tree}"` '
            "from `{project-root}`") in update
    assert "ephemeral" not in _read(PROTOCOL)


def test_skip_reaches_the_evidence_report() -> None:
    assert f"the record is `{SKIP_RECORD}` instead" in _read(PROTOCOL)
    file_6 = _section(_read(GENERATE_ARTIFACTS), "**File 6:**", "**File 7:**")
    assert "`## Remaining Warnings`" in file_6
    assert "`authoritative_files_scan.not_scanned`" in file_6
