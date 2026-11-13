#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF render drift tables: the drift report's per-item tables, from the JSON
audit-skill saved.

Step 1c (references/constituent-freshness.md section 2), step 3
(references/structural-diff.md section 5), step 4
(references/semantic-diff.md section 4), step 5
(references/severity-classify.md section 3) and step 5a
(references/doc-drift.md section 3) each append a section of tables to the
drift report, and step 6 (references/report.md sections 2 and 3) its
Out-of-Scope New Public API and Provenance tables. Every cell of those
tables is a field of the JSON an earlier step saved, or of the report's
frontmatter, so this script prints them, rather than the model copying
hundreds of rows by hand, where a row can be dropped or mis-matched and a
`|` in a value breaks the table. The model keeps only what the files do not
hold: each section's heading, the Comparison and Method lines of steps 1c
and 3, step 4's Method and QMD Collection lines, step 1c's Semantic Drift
skip and step 6's Confidence Legend.

structural DIFF [--file-drift FILE]
  DIFF is the skf-structural-diff.py result step 3 section 1 saved
  (structural-diff.json). Prints, in this order:
    ### Added Exports (N)       Export | Type | Signature | Location | Confidence
    ### Removed Exports (N)     Export | Type | Original Signature |
                                Original Location | Confidence
    ### Moved Exports (N)       Export | From | To | Confidence
    ### Changed Exports (N)     Export | Change Type | Before | After |
                                Location | Confidence (one row per changed
                                field; a line change reads `location`)
    ### Ambiguous Names (N)     Export | Removed At | Added At (only when
                                ambiguous_names[] is non-empty)
    ### Summary                 Added, Removed, Moved, Changed and
                                **Total Drift Items**, their sum
    **Signatures not compared:** (only when summary.signature_unverified
                                is above 0)
    **Off the public surface:** (only when summary.not_public is above 0:
                                the exports of a public-api skill the
                                diff left out of Added Exports, which are
                                not drift; the first ten of not_public[]
                                as `name` (`file`), then `and N more`)
    ### By Library              a stack diff (--group-by source_library):
                                each groups[] entry's counts
    ### Script/Asset Drift (added N, removed N, changed N)
                                File | Change | Detail, from FILE, the
                                skf-compare-file-hashes.py compare result
                                step 3 section 4b saved (only when FILE is
                                given and exists; when FILE cannot be read
                                or is not such a result, the heading reads
                                `### Script/Asset Drift: skipped (<reason>)`
                                and the other tables still print). When
                                FILE's `added_not_checked` names a reason
                                (no brief, or one the comparison could not
                                read), a **New files not checked:** line
                                follows the table
    ### Provenance label differences (not drift) (N)
                                Export | Baseline label | Current label
                                (only when label_changes[] is non-empty)
  Every heading count comes from the diff's summary (FILE's stats for
  Script/Asset Drift), never from the rows. An export of a stack reads
  `<library>: <name>`.

severity CLASSIFICATION
  CLASSIFICATION is the skf-severity-classify.py result step 5 section 2
  saved (severity.json). Prints the **Overall Drift Score** line, one table
  per severity, CRITICAL first:
    ### <SEVERITY> (by_severity[<SEVERITY>])
                                # | Finding | Type | Detail | Location |
                                Confidence
  and the Classification Summary, whose **Total** is total_items. Type is
  `semantic` for a semantic finding, `doc` for a changed document of a
  docs-only skill and `structural` for every other one; a finding with no
  confidence or file (a hash comparison) shows `n/a`.

outside-scope SNAPSHOT
  SNAPSHOT is the extraction-snapshot.json step 2 wrote
  (skf-extraction-snapshot.py build). Prints
    ### Out-of-Scope New Public API
                                Path | Evidence, one row per outside_scope
                                entry: `path` | exports `name`, ... through
                                `entry`, ... (no `through` part when the
                                entry names no entry point)
  and nothing when outside_scope is empty or absent (Quick tier). The table
  is the shape skf-provenance-gap-dispatch.py parses back for
  update-skill's scope reconciliation, and never rolls up: the snapshot
  already groups the names by file.

semantic FINDINGS
  FINDINGS is the semantic-findings.json step 4 section 4 saved (`[]` when
  the source still supports every claim). Prints one table per category
  that has rows, in this order:
    ### Changed Conventions (N) Convention | Before | After |
                                Affected Exports | Evidence | Confidence
    ### Dependency Shifts (N)   Export | Original Dependencies |
                                Current Dependencies | Change | Evidence |
                                Confidence
    ### Architectural Changes (N)
                                Change | Description | Affected Exports |
                                Evidence | Confidence
    ### Deprecated Patterns (N) Pattern | Documented In Skill |
                                Current Status | Evidence | Confidence
    ### Summary                 each category shown and **Total Semantic
                                Items**, their sum
  A row's table is its `category` (convention, dependency, architecture or
  deprecated_pattern). The first cell is its `name`; Before and After, and
  the two dependency columns, its `before` and `after`; Affected Exports
  its `exports`; Documented In Skill its `skill_reference`; Change,
  Description and Current Status its `detail`; Evidence its `file`:`line`.
  With no row it prints a no-drift line and the Summary, whose Total is 0.
  A row that is not a semantic finding, or whose category is none of the
  four, exits 1 with the row's index.

doc-drift DOC_DRIFT --detected-at WHEN
  DOC_DRIFT is the skf-detect-docs.py compare-hashes result step 5a section
  2 saved (doc-drift.json). When stats.changed is above 0, prints
                                URL | Old Hash | New Hash | Detected At,
                                each changed entry, then each fetch_failed
                                one (New Hash `_(fetch failed: <reason>)_`),
                                then each skipped_null_hash one (Old Hash
                                `_(not recorded)_`, the last two cells n/a),
                                Detected At reading WHEN (the run's
                                timestamp)
  and the **<changed> of <total_tracked> tracked documentation source(s)
  have changed since compile.** line. Otherwise a no-drift line counting
  stats.unchanged of stats.total_tracked, then a **Could not be fetched:**
  line naming each fetch_failed URL with its reason and a **No compile-time
  hash recorded:** line naming each skipped_null_hash URL, each only when
  it names one. Every count comes from stats.

constituents FRESHNESS
  FRESHNESS is the skf-hash-content.py compare-constituent-hashes result
  step 1c section 1 saved (constituent-freshness.json). Prints
    ### Constituent Freshness (drifted N, missing N, fresh N)
                                Constituent | Compose-time Hash |
                                Current Hash, one row per drifted[] entry
  then the **Missing constituents:** line (each missing[] entry's name,
  else its path, with its reason, or none) and the **Not compared (no compose-time hash):** line
  (each skipped_null_hash[] entry, or none). The counts come from stats.

provenance REPORT --stage-data DIR
  REPORT is the drift report, whose frontmatter holds the run context
  steps 1 to 3 wrote (read with yaml's safe loader, a value other than
  true, false or null kept as written, so a ref such as 1.10 stays 1.10; a
  BOM and CRLF line ends are fine). Prints step 6 section 3's Field | Value table, a row each for
  Audit Date, Audited By, Forge Tier, Tools Used (the tier's tools, as
  knowledge/progressive-capability.md lists them), Source Path (and the
  private tree, when source_tree is set), Skill Path, Audited Version (and
  the export manifest's version, when manifest_version is set),
  Provenance Map, Provenance Age, AST fallback files (none when empty, n/a
  at Quick tier), Applied Transforms (`<transform>` ×<count>, or none),
  Baseline Ref / Commit, Audit Ref / Commit, Upstream Latest, Upstream
  Moved (and the ref, when true) and Stage Data (DIR/). A commit shows its
  first 7 characters, and a value the frontmatter leaves null or empty
  reads n/a.

Rollup (structural and severity, mechanical):
  10 or more rows of one table that share a file roll up into one row, so a
  deleted or a new file reads as one row. Removed rows go one level on: 10
  or more of the removed rows left that share a directory (never the top
  level) roll up too, so a removed package tree reads as one row. Added
  rows stop at the file, since a directory is no shared cause: exports
  added across the files of one directory keep a row each.
  Rows roll up only with rows of their own kind:
    - Added and Removed Exports: per library. The Export cell reads
      `N exports (rep: a, b, c, ...)`, the Location the file or directory.
    - Script/Asset Drift: per change (added, removed, changed); a removed
      file by directory.
    - Provenance label differences: 10 or more rows with one baseline and
      one current label (compared case-insensitively) roll up whatever
      their files.
    - Severity tables: added and removed findings and Script/Asset files,
      per type, category and library, a removed one by directory too.
      The Finding cell reads
      `<type> in <file or directory> (xN; rep: a, b, c, ...)`, N counting
      each finding's `count`, and the Detail cell the findings' shared
      detail, else their rule.
  Moved, Changed and Ambiguous rows, and changed-signature, moved and
  semantic findings, never roll up. A rollup changes how a table reads,
  never a count: every heading and summary comes from the JSON.

Output: the markdown on stdout, UTF-8.

Exit codes:
  0  the tables were printed (for outside-scope, also when there was
     nothing to print)
  1  the input file is missing, is not JSON (REPORT: has no frontmatter)
     or is not what the command reads ({"status": "error", "error"} on
     stdout, the error starting with the input's path)
  2  usage error (argparse, usage on stderr)
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

import yaml

# Rows of one table that share a file or a directory roll up from this many on.
ROLLUP_MIN = 10
# Representative names a rollup row shows.
REP_COUNT = 3
# The exports the Off the public surface note names, as update-skill's not_public warning does.
NOT_PUBLIC_NAMED = 10
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
NONE = "(none)"
NA = "n/a"
# Characters a plain table cell escapes, so text renders as written.
_MARKDOWN = "\\`*_[]<>|"
# Step 4's semantic categories, in the order semantic-diff.md section 4 maps
# them: (category, table heading, table columns).
SEMANTIC_CATEGORIES = (
    ("convention", "Changed Conventions",
     ("Convention", "Before", "After", "Affected Exports", "Evidence", "Confidence")),
    ("dependency", "Dependency Shifts",
     ("Export", "Original Dependencies", "Current Dependencies", "Change", "Evidence", "Confidence")),
    ("architecture", "Architectural Changes",
     ("Change", "Description", "Affected Exports", "Evidence", "Confidence")),
    ("deprecated_pattern", "Deprecated Patterns",
     ("Pattern", "Documented In Skill", "Current Status", "Evidence", "Confidence")),
)
# The tools each forge tier runs: the Tier Definitions table of
# knowledge/progressive-capability.md.
TIER_TOOLS = {
    "Quick": (),
    "Forge": ("ast-grep",),
    "Forge+": ("ast-grep", "ccc"),
    "Deep": ("ast-grep", "gh", "qmd"),
}
# A commit shows this many characters, as skf-check-workspace-drift.py's short().
SHORT_COMMIT = 7
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,64}")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*$", re.M | re.S)


class RenderError(Exception):
    """An input the tables cannot be rendered from: exit 1."""


# --------------------------------------------------------------------------
# Cells
# --------------------------------------------------------------------------


def _flat(value) -> str:
    """One line of text for a value; a list reads (a, b)."""
    if isinstance(value, list):
        value = "(" + ", ".join(str(v) for v in value) + ")"
    return " ".join(str(value).split())


def text(value) -> str:
    """A plain cell: markdown characters escaped, `n/a` for no value.

    >>> text("def __init__(self) | None")
    'def \\\\_\\\\_init\\\\_\\\\_(self) \\\\| None'
    >>> text(None)
    'n/a'
    """
    if value is None or value == "":
        return NA
    return "".join("\\" + ch if ch in _MARKDOWN else ch for ch in _flat(value))


def code(value) -> str:
    """A code span holding the value as written, `(none)` for no value.

    A pipe is escaped, which a GFM table needs even inside a code span, and
    the fence is longer than any run of backticks in the value.

    >>> code("a | b")
    '`a \\\\| b`'
    >>> code("x`y")
    '`` x`y ``'
    >>> code(None)
    '(none)'
    """
    if value is None or value == "":
        return NONE
    flat = _flat(value).replace("|", "\\|")
    longest = run = 0
    for ch in flat:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    pad = " " if longest else ""
    return f"{fence}{pad}{flat}{pad}{fence}"


def where(file, line=None) -> str:
    """`file:line`, `file` without a line, `n/a` without a file."""
    if file is None or file == "":
        return NA
    return code(f"{file}:{line}" if line is not None else file)


def export_cell(item: dict) -> str:
    """An export's name, after its library for a stack."""
    name = code(item.get("name"))
    if item.get("source_library") is not None:
        return f"{text(item['source_library'])}: {name}"
    return name


def _table(header: tuple[str, ...], rows: list[list[str]]) -> str:
    """A markdown table, or `None.` when it has no row."""
    if not rows:
        return "None."
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("-" * (len(h) + 2) for h in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _distinct(values) -> list:
    """The values in first-seen order, each once."""
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _labels(values) -> str:
    """Confidence labels of rolled-up rows, each once."""
    return ", ".join(text(v) for v in _distinct(values))


def _rep(names: list) -> str:
    """The first REP_COUNT names as code spans, then `…` when there are more."""
    shown = ", ".join(code(n) for n in names[:REP_COUNT])
    return shown + (", …" if len(names) > REP_COUNT else "")


# --------------------------------------------------------------------------
# Rollup
# --------------------------------------------------------------------------


def _directory(path) -> str | None:
    """A path's directory, or None at the top level."""
    if not isinstance(path, str) or not path:
        return None
    parent = posixpath.dirname(path.replace("\\", "/").rstrip("/"))
    return parent or None


def plan_rows(items: list, key, path, eligible=lambda item: True, by_directory=lambda item: True) -> list[tuple]:
    """The rows of one table in order: ("item", item) for a row of its own,
    ("rollup", place, members) for a rollup row at its first member's place.

    Eligible items of one key that share a path roll up when ROLLUP_MIN or
    more do; then the eligible items left that by_directory admits and that
    share a directory, the directory read as `<dir>/`.

    >>> rows = plan_rows([{"f": "a.py"}] * 10 + [{"f": "b.py"}], key=lambda i: 0, path=lambda i: i["f"])
    >>> [(r[0], r[1] if r[0] == "rollup" else r[1]["f"]) for r in rows]
    [('rollup', 'a.py'), ('item', 'b.py')]
    """
    member_of: dict[int, int] = {}
    groups: list[tuple[str, list[int]]] = []
    for level in ("file", "directory"):
        buckets: dict[tuple, list[int]] = {}
        for index, item in enumerate(items):
            if index in member_of or not eligible(item) or (level == "directory" and not by_directory(item)):
                continue
            place = path(item) if level == "file" else _directory(path(item))
            if not isinstance(place, str) or not place:
                continue
            buckets.setdefault((key(item), place), []).append(index)
        for (_, place), members in buckets.items():
            if len(members) >= ROLLUP_MIN:
                for index in members:
                    member_of[index] = len(groups)
                groups.append((place if level == "file" else place + "/", members))
    rows: list[tuple] = []
    shown: set[int] = set()
    for index, item in enumerate(items):
        group = member_of.get(index)
        if group is None:
            rows.append(("item", item))
        elif group not in shown:
            shown.add(group)
            place, members = groups[group]
            rows.append(("rollup", place, [items[m] for m in members]))
    return rows


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def load_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RenderError(f"{path}: no such file ({what})") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise RenderError(f"{path}: cannot read {what}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise RenderError(f"{path}: {what} is not JSON: {exc}") from None


def load_text(path: Path, what: str) -> str:
    """A UTF-8 file's text, a leading BOM dropped."""
    try:
        return path.read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        raise RenderError(f"{path}: no such file ({what})") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise RenderError(f"{path}: cannot read {what}: {exc}") from None


class _TextLoader(yaml.SafeLoader):
    """yaml.SafeLoader reading only true, false and null as typed values, so
    an unquoted ref such as 1.10, a commit such as 0123456 or a timestamp
    stays as written."""


_TextLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers
            if tag in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:null")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def read_frontmatter(text: str) -> dict:
    """The leading `---` block of a markdown file, read with yaml's safe
    loader, every value but true, false and null kept as the text written.

    A BOM and CRLF line ends read as plain text would. Raises RenderError
    when the text has no such block, or the block is not a YAML mapping.

    >>> read_frontmatter("\\ufeff---\\r\\nskill_name: demo\\r\\nupstream_moved: true\\r\\n---\\r\\n# Report")
    {'skill_name': 'demo', 'upstream_moved': True}
    >>> read_frontmatter("---\\naudit_ref: 1.10\\nbaseline_commit: 0123456\\nupstream_ref: null\\n---\\n")
    {'audit_ref': '1.10', 'baseline_commit': '0123456', 'upstream_ref': None}
    """
    match = _FRONTMATTER_RE.match(text.lstrip("﻿").replace("\r\n", "\n"))
    if not match:
        raise RenderError("no frontmatter: expected a leading `---` block")
    try:
        data = yaml.load(match.group(1), Loader=_TextLoader)
    except yaml.YAMLError as exc:
        raise RenderError("the frontmatter is not valid YAML (write a value that holds `: ` or a quote as a "
                          f"double-quoted string): {exc}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RenderError("the frontmatter is not a YAML mapping")
    return data


def flag(value) -> bool | None:
    """A frontmatter true or false (a YAML bool, or the word as text), else None.

    >>> flag(True), flag("false"), flag(" True "), flag(""), flag(None), flag("yes")
    (True, False, True, None, None, None)
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def _records(data: dict, key: str) -> list[dict]:
    return [r for r in data.get(key) or [] if isinstance(r, dict)]


def _count(summary: dict, key: str) -> int:
    value = summary.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


# --------------------------------------------------------------------------
# structural
# --------------------------------------------------------------------------


def _shape(rec: dict):
    """An export's signature: its signature, else its params and return type."""
    if rec.get("signature"):
        return rec["signature"]
    if rec.get("params") is None and not rec.get("return_type"):
        return None
    shape = _flat(rec.get("params") or [])
    if rec.get("return_type"):
        shape += f" -> {rec['return_type']}"
    return shape


def _export_rows(records: list[dict], removed: bool) -> list[list[str]]:
    """Added or Removed Exports rows; only removed ones roll up by directory."""
    rows = []
    plan = plan_rows(records, key=lambda r: r.get("source_library"), path=lambda r: r.get("file"),
                     by_directory=lambda r: removed)
    for row in plan:
        if row[0] == "item":
            rec = row[1]
            rows.append([export_cell(rec), text(rec.get("type")), code(_shape(rec)),
                         where(rec.get("file"), rec.get("line")), text(rec.get("confidence"))])
            continue
        _, place, members = row
        library = members[0].get("source_library")
        cell = f"{len(members)} exports (rep: {_rep([m.get('name') for m in members])})"
        if library is not None:
            cell = f"{text(library)}: {cell}"
        rows.append([cell, ", ".join(text(t) for t in _distinct(m.get("type") for m in members)), NA,
                     code(place), _labels(m.get("confidence") for m in members)])
    return rows


def _label(side) -> str:
    side = side if isinstance(side, dict) else {}
    return " / ".join(text(side.get(k)) if side.get(k) is not None else NONE
                      for k in ("confidence", "extraction_method"))


def _label_rows(records: list[dict]) -> list[list[str]]:
    def pair(rec):
        return tuple(_label(rec.get(side)).casefold() for side in ("baseline", "current"))

    buckets: dict[tuple, list[int]] = {}
    for index, rec in enumerate(records):
        buckets.setdefault(pair(rec), []).append(index)
    rolled = {members[0]: members for members in buckets.values() if len(members) >= ROLLUP_MIN}
    skip = {i for members in rolled.values() for i in members[1:]}
    rows = []
    for index, rec in enumerate(records):
        if index in skip:
            continue
        cell = export_cell(rec)
        if index in rolled:
            members = [records[i] for i in rolled[index]]
            cell = f"{len(members)} exports (rep: {_rep([m.get('name') for m in members])})"
        rows.append([cell, _label(rec.get("baseline")), _label(rec.get("current"))])
    return rows


def check_file_drift(data) -> None:
    """Raise RenderError unless data is a skf-compare-file-hashes.py compare result."""
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) for k in ("added", "removed", "changed")):
        raise RenderError("not a file drift result: expected an object with added, removed and changed lists "
                          "(the output of skf-compare-file-hashes.py compare)")


def _file_drift_section(data) -> str:
    check_file_drift(data)
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    items = [{"path": p, "change": "added", "detail": "new file"} for p in data["added"] if isinstance(p, str)]
    items += [{"path": p, "change": "removed", "detail": "file removed"} for p in data["removed"]
              if isinstance(p, str)]
    items += [{"path": c.get("path"), "change": "changed",
               "detail": f"content {c.get('stored_hash')} -> {c.get('current_hash')}"}
              for c in data["changed"] if isinstance(c, dict)]
    rows = []
    for row in plan_rows(items, key=lambda i: i["change"], path=lambda i: i["path"],
                         by_directory=lambda i: i["change"] == "removed"):
        if row[0] == "item":
            item = row[1]
            rows.append([code(item["path"]), item["change"], text(item["detail"])])
            continue
        _, place, members = row
        names = [posixpath.basename(str(m["path"]).replace("\\", "/")) for m in members]
        details = _distinct(m["detail"] for m in members)
        rows.append([f"{code(place)} ({len(members)} files, rep: {_rep(names)})", members[0]["change"],
                     text(details[0]) if len(details) == 1 else NA])
    heading = (f"### Script/Asset Drift (added {_count(stats, 'added')}, removed {_count(stats, 'removed')}, "
               f"changed {_count(stats, 'changed')})")
    section = heading + "\n\n" + _table(("File", "Change", "Detail"), rows)
    reason = data.get("added_not_checked")
    if isinstance(reason, str) and reason.strip():
        section += (f"\n\n**New files not checked:** {text(reason.strip())}. The tracked files were compared, but "
                    "no new script, asset or document was looked for, so `added` lists none.")
    return section


def render_structural(diff, file_drift=None, file_drift_skipped=None) -> str:
    """The Structural Drift tables of a skf-structural-diff.py result (and,
    given one, a skf-compare-file-hashes.py compare result, or the reason
    one could not be read, which its skipped heading shows)."""
    buckets = ("added", "removed", "changed", "moved")
    if not isinstance(diff, dict) or not all(isinstance(diff.get(b), list) for b in buckets) \
            or not isinstance(diff.get("summary"), dict):
        raise RenderError("not a structural diff: expected an object with a summary and added, removed, changed "
                          "and moved lists (the output of skf-structural-diff.py)")
    summary = diff["summary"]
    parts = []

    parts.append(f"### Added Exports ({_count(summary, 'added')})\n\n" + _table(
        ("Export", "Type", "Signature", "Location", "Confidence"),
        _export_rows(_records(diff, "added"), removed=False)))
    parts.append(f"### Removed Exports ({_count(summary, 'removed')})\n\n" + _table(
        ("Export", "Type", "Original Signature", "Original Location", "Confidence"),
        _export_rows(_records(diff, "removed"), removed=True)))

    moved = [[export_cell(m), where(m.get("previous_file"), m.get("previous_line")),
              where(m.get("current_file"), m.get("line")), text(m.get("confidence"))]
             for m in _records(diff, "moved")]
    parts.append(f"### Moved Exports ({_count(summary, 'moved')})\n\n"
                 + _table(("Export", "From", "To", "Confidence"), moved))

    changed = []
    for c in _records(diff, "changed"):
        field = c.get("field")
        changed.append([export_cell(c), text("location" if field == "line" else field),
                        code(c.get("baseline_value")), code(c.get("current_value")),
                        where(c.get("file"), c.get("line")), text(c.get("confidence"))])
    parts.append(f"### Changed Exports ({_count(summary, 'changed')})\n\n"
                 + _table(("Export", "Change Type", "Before", "After", "Location", "Confidence"), changed))

    ambiguous = _records(diff, "ambiguous_names")
    if ambiguous:
        rows = []
        for a in ambiguous:
            sides = [", ".join(where(s.get("file"), s.get("line")) for s in a.get(side) or [] if isinstance(s, dict))
                     or NA for side in ("removed", "added")]
            rows.append([export_cell(a), *sides])
        parts.append(f"### Ambiguous Names ({_count(summary, 'ambiguous_names')})\n\n"
                     + _table(("Export", "Removed At", "Added At"), rows))

    counts = [(label, _count(summary, key)) for label, key in
              (("Added", "added"), ("Removed", "removed"), ("Moved", "moved"), ("Changed", "changed"))]
    rows = [[label, str(n)] for label, n in counts] + [["**Total Drift Items**", str(sum(n for _, n in counts))]]
    block = "### Summary\n\n" + _table(("Category", "Count"), rows)
    unverified = _count(summary, "signature_unverified")
    if unverified:
        block += (f"\n\n**Signatures not compared:** {unverified} matched exports hold their signature in "
                  "different fields on the two sides, so a change there cannot be seen.")
    not_public = _count(summary, "not_public")
    if not_public:
        one = not_public == 1
        named = [f"{export_cell(r)} ({where(r.get('file'))})"
                 for r in _records(diff, "not_public")[:NOT_PUBLIC_NAMED]]
        more = f" and {not_public - len(named)} more" if named and not_public > len(named) else ""
        listed = f": {', '.join(named)}{more}" if named else ""
        block += (f"\n\n**Off the public surface:** {not_public} {'export' if one else 'exports'} the provenance "
                  f"map does not hold {'is' if one else 'are'} off this public-api skill's public surface "
                  f"(`not_public[]` in the saved diff), so {'it is' if one else 'they are'} not reported as added "
                  f"and {'is' if one else 'are'} excluded from Total Drift Items{listed}.")
    parts.append(block)

    groups = _records(diff, "groups")
    if groups:
        rows = [[text(g.get("source_library")) if g.get("source_library") is not None else NONE,
                 *(str(_count(g.get("summary") or {}, k)) for k in ("added", "removed", "moved", "changed"))]
                for g in groups]
        parts.append("### By Library\n\n" + _table(("Library", "Added", "Removed", "Moved", "Changed"), rows))

    if file_drift_skipped is not None:
        parts.append(f"### Script/Asset Drift: skipped ({file_drift_skipped})")
    elif file_drift is not None:
        parts.append(_file_drift_section(file_drift))

    labels = _records(diff, "label_changes")
    if labels:
        parts.append(f"### Provenance label differences (not drift) ({_count(summary, 'label_changes')})\n\n"
                     "These rows are informational: a label names the tool that extracted the export, so they "
                     "are excluded from Total Drift Items and are not findings.\n\n"
                     + _table(("Export", "Baseline label", "Current label"), _label_rows(labels)))
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# severity
# --------------------------------------------------------------------------


def _norm(value):
    return value.strip().lower() if isinstance(value, str) else None


def _weight(finding: dict) -> int:
    count = finding.get("count", 1)
    return count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 1


def _kind(finding: dict) -> str:
    if _norm(finding.get("type")) == "semantic":
        return "semantic"
    if _norm(finding.get("category")) == "doc_source":
        return "doc"
    return "structural"


def _rolls_up(finding: dict) -> bool:
    """Added and removed findings and Script/Asset files: the rows step 3 rolls up."""
    return _norm(finding.get("type")) in ("added", "removed") or _norm(finding.get("category")) == "file"


def _rep_name(finding: dict):
    name = finding.get("name")
    if isinstance(name, str) and name == finding.get("file"):
        return posixpath.basename(name.replace("\\", "/")) or name
    return name


def _severity_rows(findings: list[dict]) -> list[list[str]]:
    plan = plan_rows(findings,
                     key=lambda f: (_norm(f.get("type")), _norm(f.get("category")), f.get("source_library")),
                     path=lambda f: f.get("file"), eligible=_rolls_up,
                     by_directory=lambda f: _norm(f.get("type")) == "removed")
    rows = []
    for number, row in enumerate(plan, start=1):
        if row[0] == "item":
            f = row[1]
            finding = export_cell(f)
            if _weight(f) > 1:
                finding += f" (×{_weight(f)})"
            rows.append([str(number), finding, _kind(f), text(f.get("detail")), where(f.get("file"), f.get("line")),
                         text(f.get("confidence"))])
            continue
        _, place, members = row
        first = members[0]
        cell = (f"{text(first.get('type'))} in {code(place)} "
                f"(×{sum(_weight(m) for m in members)}; rep: {_rep([_rep_name(m) for m in members])})")
        if first.get("source_library") is not None:
            cell = f"{text(first['source_library'])}: {cell}"
        details = _distinct(m.get("detail") for m in members)
        detail = details[0] if len(details) == 1 else first.get("rule")
        rows.append([str(number), cell, _kind(first), text(detail), code(place),
                     _labels(m.get("confidence") for m in members)])
    return rows


def render_severity(result) -> str:
    """The Severity Classification section of a skf-severity-classify.py result."""
    if not isinstance(result, dict) or not isinstance(result.get("findings"), list) \
            or not isinstance(result.get("by_severity"), dict) or "drift_score" not in result:
        raise RenderError("not a severity classification: expected an object with drift_score, by_severity and "
                          "findings (the output of skf-severity-classify.py)")
    by_severity = result["by_severity"]
    findings = [f for f in result["findings"] if isinstance(f, dict)]
    parts = [f"**Overall Drift Score: {text(result['drift_score'])}**"]
    header = ("#", "Finding", "Type", "Detail", "Location", "Confidence")
    for level in SEVERITIES:
        rows = _severity_rows([f for f in findings if f.get("severity") == level])
        parts.append(f"### {level} ({_count(by_severity, level)})\n\n" + _table(header, rows))
    rows = [[level, str(_count(by_severity, level))] for level in SEVERITIES]
    rows.append(["**Total**", str(_count(result, "total_items"))])
    parts.append("### Classification Summary\n\n" + _table(("Severity", "Count"), rows))
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# outside-scope
# --------------------------------------------------------------------------


def _strings(values) -> list[str]:
    return [v for v in values if isinstance(v, str) and v] if isinstance(values, list) else []


def render_outside_scope(snapshot) -> str:
    """The Out-of-Scope New Public API table of an extraction snapshot, or
    nothing when its outside_scope is empty or absent.

    >>> render_outside_scope({"exports": [], "outside_scope": [
    ...     {"path": "src/b.ts", "names": ["Beta"], "entries": ["index.ts"]}]}).splitlines()[-1]
    '| `src/b.ts` | exports `Beta` through `index.ts` |'
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("exports"), list) \
            or not isinstance(snapshot.get("outside_scope", []), list):
        raise RenderError("not an extraction snapshot: expected an object with an exports list and, when present, "
                          "an outside_scope list (the output of skf-extraction-snapshot.py build)")
    rows = []
    for item in _records(snapshot, "outside_scope"):
        names = _strings(item.get("names"))
        if not isinstance(item.get("path"), str) or not item["path"] or not names:
            continue
        evidence = "exports " + ", ".join(code(n) for n in names)
        entries = _strings(item.get("entries"))
        if entries:
            evidence += " through " + ", ".join(code(e) for e in entries)
        rows.append([code(item["path"]), evidence])
    if not rows:
        return ""
    return "### Out-of-Scope New Public API\n\n" + _table(("Path", "Evidence"), rows) + "\n"


# --------------------------------------------------------------------------
# semantic
# --------------------------------------------------------------------------


def _exports(value) -> str:
    """Export names as code spans, `n/a` for none."""
    names = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    names = [n for n in names if isinstance(n, str) and n]
    return ", ".join(code(n) for n in names) if names else NA


def _semantic_cells(category: str, row: dict) -> list[str]:
    evidence, confidence = where(row.get("file"), row.get("line")), text(row.get("confidence"))
    if category == "convention":
        return [text(row.get("name")), text(row.get("before")), text(row.get("after")), _exports(row.get("exports")),
                evidence, confidence]
    if category == "dependency":
        return [code(row.get("name")), text(row.get("before")), text(row.get("after")), text(row.get("detail")),
                evidence, confidence]
    if category == "architecture":
        return [text(row.get("name")), text(row.get("detail")), _exports(row.get("exports")), evidence, confidence]
    return [text(row.get("name")), text(row.get("skill_reference")), text(row.get("detail")), evidence, confidence]


def render_semantic(findings) -> str:
    """The Semantic Drift tables of step 4's semantic-findings.json: one per
    category that has rows, then the Summary.

    >>> render_semantic([]).splitlines()[-1]
    '| **Total Semantic Items** | 0 |'
    """
    if not isinstance(findings, list):
        raise RenderError("not a semantic findings file: expected an array of objects whose type is semantic "
                          "(the semantic-findings.json step 4 saves)")
    known = [category for category, _, _ in SEMANTIC_CATEGORIES]
    by_category: dict[str, list[dict]] = {category: [] for category in known}
    for index, row in enumerate(findings):
        if not isinstance(row, dict) or _norm(row.get("type")) != "semantic":
            raise RenderError(f"row {index}: not a semantic finding (an object whose type is semantic)")
        category = _norm(row.get("category"))
        if category not in by_category:
            raise RenderError(f"row {index}: category {row.get('category')!r} is not one of {', '.join(known)}")
        by_category[category].append(row)
    parts, summary = [], []
    for category, heading, header in SEMANTIC_CATEGORIES:
        rows = by_category[category]
        if rows:
            parts.append(f"### {heading} ({len(rows)})\n\n"
                         + _table(header, [_semantic_cells(category, row) for row in rows]))
            summary.append([heading.capitalize(), str(len(rows))])
    if not parts:
        parts.append("No semantic drift: the current source still supports every claim this step checked.")
    summary.append(["**Total Semantic Items**", str(len(findings))])
    parts.append("### Summary\n\n" + _table(("Category", "Count"), summary))
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# doc-drift
# --------------------------------------------------------------------------


def render_doc_drift(data, detected_at) -> str:
    """The Documentation Drift section of a skf-detect-docs.py compare-hashes
    result, its heading left out; `detected_at` fills the Detected At column."""
    if not isinstance(data, dict) or not isinstance(data.get("stats"), dict) \
            or not all(isinstance(data.get(k), list) for k in ("changed", "unchanged", "fetch_failed")):
        raise RenderError("not a doc drift result: expected an object with stats and changed, unchanged and "
                          "fetch_failed lists (the output of skf-detect-docs.py compare-hashes)")
    stats = data["stats"]
    changed, total = _count(stats, "changed"), _count(stats, "total_tracked")
    failed, unhashed = _records(data, "fetch_failed"), _records(data, "skipped_null_hash")
    if changed > 0:
        when = text(detected_at)
        rows = [[code(r.get("url")), code(r.get("old_hash")), code(r.get("new_hash")), when]
                for r in _records(data, "changed")]
        rows += [[code(r.get("url")), code(r.get("old_hash")), f"_(fetch failed: {text(r.get('reason'))})_", when]
                 for r in failed]
        rows += [[code(r.get("url")), "_(not recorded)_", NA, NA] for r in unhashed]
        return (_table(("URL", "Old Hash", "New Hash", "Detected At"), rows)
                + f"\n\n**{changed} of {total} tracked documentation source(s) have changed since compile.**\n")
    parts = [f"No documentation drift detected. {_count(stats, 'unchanged')} of {total} tracked documentation "
             "source(s) match their compile-time hashes."]
    if failed:
        parts.append("**Could not be fetched:** "
                     + ", ".join(f"{code(r.get('url'))} ({text(r.get('reason'))})" for r in failed) + ".")
    if unhashed:
        parts.append("**No compile-time hash recorded:** " + ", ".join(code(r.get("url")) for r in unhashed) + ".")
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------------
# constituents
# --------------------------------------------------------------------------


def render_constituents(data) -> str:
    """The Constituent Freshness table of a skf-hash-content.py
    compare-constituent-hashes result, and its two lines."""
    if not isinstance(data, dict) or not isinstance(data.get("stats"), dict) \
            or not all(isinstance(data.get(k), list) for k in ("drifted", "missing")):
        raise RenderError("not a constituent freshness result: expected an object with stats and drifted and "
                          "missing lists (the output of skf-hash-content.py compare-constituent-hashes)")
    stats = data["stats"]
    heading = (f"### Constituent Freshness (drifted {_count(stats, 'drifted')}, missing {_count(stats, 'missing')}, "
               f"fresh {_count(stats, 'fresh')})")
    rows = [[code(r.get("skill_name")), code(r.get("stored_hash")), code(r.get("current_hash"))]
            for r in _records(data, "drifted")]
    missing = ", ".join(f"{code(r.get('skill_name') or r.get('skill_path'))} ({text(r.get('reason'))})"
                        for r in _records(data, "missing")) or "none"
    unhashed = ", ".join(code(r.get("skill_name")) for r in _records(data, "skipped_null_hash")) or "none"
    return (heading + "\n\n" + _table(("Constituent", "Compose-time Hash", "Current Hash"), rows)
            + f"\n\n**Missing constituents:** {missing}.\n\n**Not compared (no compose-time hash):** {unhashed}.\n")


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------


def _set(value) -> bool:
    return value is not None and value != "" and value != []


def _or_na(value, cell=code) -> str:
    """cell(value), or `n/a` for a value the run does not have."""
    return cell(value) if _set(value) else NA


def short_commit(value):
    """A commit's first SHORT_COMMIT characters; any other value as it is.

    >>> short_commit("0123456789abcdef0123456789abcdef01234567"), short_commit("(unknown)"), short_commit(None)
    ('0123456', '(unknown)', None)
    """
    if isinstance(value, str) and _COMMIT_RE.fullmatch(value):
        return value[:SHORT_COMMIT]
    return value


def tier_tools(tier) -> str:
    """The tools a forge tier runs, `none` at Quick, `n/a` for no known tier."""
    for name, tools in TIER_TOOLS.items():
        if isinstance(tier, str) and tier.strip().casefold() == name.casefold():
            return ", ".join(text(t) for t in tools) or "none"
    return NA


def _list_cell(value, item) -> str:
    """A list's items, `none` when it is empty, `n/a` when the run has none."""
    if value is None:
        return NA
    if isinstance(value, list):
        return ", ".join(item(v) for v in value) or "none"
    return text(value) if value != "" else "none"


def _transform(entry) -> str:
    if isinstance(entry, dict):
        count = entry.get("count")
        return f"{code(entry.get('transform'))} ×{text(count) if count is not None else NA}"
    return code(entry)


def render_provenance(front: dict, stage_data: str) -> str:
    """Step 6's Provenance table of the drift report's frontmatter; `stage_data`
    is the run's stage data folder."""
    source = _or_na(front.get("source_path"))
    if _set(front.get("source_tree")):
        source += f"; read from the private tree {code(front['source_tree'])}"
    version = _or_na(front.get("audited_version"))
    if _set(front.get("audited_version_reason")):
        version += f" ({text(front['audited_version_reason'])})"
    if _set(front.get("manifest_version")):
        version += f"; the export manifest names {code(front['manifest_version'])}"
    age, generated = front.get("provenance_age_days"), front.get("provenance_generated_at")
    age_cell = f"{text(age)} days" if _set(age) else NA
    if _set(generated):
        age_cell += f" (generated {text(generated)})"
    quick = isinstance(front.get("forge_tier"), str) and front["forge_tier"].strip().casefold() == "quick"
    fallback = NA if quick else _list_cell(front.get("ast_fallback_files"), code)
    latest = front.get("latest_tag") if _set(front.get("latest_tag")) else short_commit(front.get("remote_head"))
    moved = flag(front.get("upstream_moved"))
    moved_cell = NA if moved is None else str(moved).lower()
    if moved and _set(front.get("upstream_ref")):
        moved_cell += f": to {code(front['upstream_ref'])}"
    folder = stage_data.rstrip("/\\") + "/"
    rows = [
        ("Audit Date", text(front.get("date"))),
        ("Audited By", "Ferris (Audit mode)"),
        ("Forge Tier", text(front.get("forge_tier"))),
        ("Tools Used", tier_tools(front.get("forge_tier"))),
        ("Source Path", source),
        ("Skill Path", _or_na(front.get("skill_path"))),
        ("Audited Version", version),
        ("Provenance Map", _or_na(front.get("provenance_map"))),
        ("Provenance Age", age_cell),
        ("AST fallback files", fallback),
        ("Applied Transforms", _list_cell(front.get("applied_transforms"), _transform)),
        ("Baseline Ref / Commit", f"{_or_na(front.get('baseline_ref'))} @ "
                                  f"{_or_na(short_commit(front.get('baseline_commit')))}"),
        ("Audit Ref / Commit", f"{_or_na(front.get('audit_ref'))} @ {_or_na(short_commit(front.get('audit_commit')))} "
                               f"({text(front.get('audit_ref_source'))})"),
        ("Upstream Latest", f"{code(latest if _set(latest) else '(not fetched)')} "
                            f"(fetch: {text(front.get('upstream_fetch'))})"),
        ("Upstream Moved", moved_cell),
        ("Stage Data", f"{code(folder)}: the JSON this run saved and classified (the structural diff, the "
                       "constituents' freshness or the documents' comparison, the findings and their classification)"),
    ]
    return _table(("Field", "Value"), [[f"**{name}**", value] for name, value in rows]) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _named(path: Path, func, *args):
    """func(*args), a RenderError it raises starting with the input's path."""
    try:
        return func(*args)
    except RenderError as exc:
        raise RenderError(f"{path}: {exc}") from None


def _structural(args) -> str:
    path = Path(args.diff)
    diff = load_json(path, "the structural diff")
    # The Script/Asset Drift check is supplementary: a saved file it cannot
    # read skips its table, never the export tables.
    file_drift = skipped = None
    if args.file_drift is not None and Path(args.file_drift).is_file():
        drift_path = Path(args.file_drift)
        try:
            file_drift = load_json(drift_path, "the file drift result")
            _named(drift_path, check_file_drift, file_drift)
        except RenderError as exc:
            file_drift, skipped = None, str(exc)
    return _named(path, render_structural, diff, file_drift, skipped)


def _severity(args) -> str:
    path = Path(args.classification)
    return _named(path, render_severity, load_json(path, "the severity classification"))


def _outside_scope(args) -> str:
    path = Path(args.snapshot)
    return _named(path, render_outside_scope, load_json(path, "the extraction snapshot"))


def _semantic(args) -> str:
    path = Path(args.findings)
    return _named(path, render_semantic, load_json(path, "the semantic findings"))


def _doc_drift(args) -> str:
    path = Path(args.doc_drift)
    return _named(path, render_doc_drift, load_json(path, "the doc drift result"), args.detected_at)


def _constituents(args) -> str:
    path = Path(args.freshness)
    return _named(path, render_constituents, load_json(path, "the constituent freshness result"))


def _provenance(args) -> str:
    path = Path(args.report)
    front = _named(path, read_frontmatter, load_text(path, "the drift report"))
    return render_provenance(front, args.stage_data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render-drift-tables.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    structural = sub.add_parser("structural", help="Print step 3's Structural Drift tables from structural-diff.json")
    structural.add_argument("diff", help="structural-diff.json, the skf-structural-diff.py result step 3 saved")
    structural.add_argument("--file-drift", default=None,
                            help="file-drift.json, step 3 section 4b's comparison: its Script/Asset Drift table "
                                 "(none when the file does not exist, a skipped heading when it cannot be read)")
    structural.set_defaults(func=_structural)
    severity = sub.add_parser("severity", help="Print step 5's Severity Classification section from severity.json")
    severity.add_argument("classification", help="severity.json, the skf-severity-classify.py result step 5 saved")
    severity.set_defaults(func=_severity)
    outside = sub.add_parser("outside-scope",
                             help="Print step 6's Out-of-Scope New Public API table from extraction-snapshot.json")
    outside.add_argument("snapshot", help="extraction-snapshot.json, the snapshot step 2 wrote (nothing is printed "
                                          "when its outside_scope is empty)")
    outside.set_defaults(func=_outside_scope)
    semantic = sub.add_parser("semantic", help="Print step 4's Semantic Drift tables from semantic-findings.json")
    semantic.add_argument("findings", help="semantic-findings.json, the rows step 4 saved")
    semantic.set_defaults(func=_semantic)
    doc_drift = sub.add_parser("doc-drift", help="Print step 5a's Documentation Drift section from doc-drift.json")
    doc_drift.add_argument("doc_drift", metavar="doc-drift",
                           help="doc-drift.json, the skf-detect-docs.py compare-hashes result step 5a saved")
    doc_drift.add_argument("--detected-at", required=True, help="the run's timestamp, for the Detected At column")
    doc_drift.set_defaults(func=_doc_drift)
    constituents = sub.add_parser("constituents",
                                  help="Print step 1c's Constituent Freshness table from constituent-freshness.json")
    constituents.add_argument("freshness", help="constituent-freshness.json, the skf-hash-content.py "
                                                "compare-constituent-hashes result step 1c saved")
    constituents.set_defaults(func=_constituents)
    provenance = sub.add_parser("provenance", help="Print step 6's Provenance table from the drift report's "
                                                   "frontmatter")
    provenance.add_argument("report", help="the drift report, whose frontmatter holds the run context")
    provenance.add_argument("--stage-data", required=True, help="the run's stage data folder, for the Stage Data row")
    provenance.set_defaults(func=_provenance)
    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the output streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        output = args.func(args)
    except RenderError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
