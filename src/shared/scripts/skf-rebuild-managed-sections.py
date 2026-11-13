# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Rebuild Managed Sections: context file marker surgery and section assembly.

Reads a context file (CLAUDE.md/AGENTS.md/.cursorrules), finds the
<!-- SKF:BEGIN --> / <!-- SKF:END --> markers, and replaces the managed
section with new content. Preserves all content outside the markers.

CLI: python3 skf-rebuild-managed-sections.py <context-file> <action> [args]

Actions:
  read          Extract current managed section content
  replace       Replace managed section with content from stdin or --content
  clear         Remove managed section entirely (markers + content)
  insert        Insert managed section if not present (at end of file,
                creating the file when it is missing)
  check         Report the section and the write that fits the file as
                `case`: create (no file), append (no section: insert),
                regenerate (a section: replace), or, with status "error",
                malformed or unreadable
  diff --content-file FILE
                Compare the section between the markers (empty for create
                and append) with the body FILE holds: `case` as check gives
                it, `header` {old, new} (each body's `[SKF Skills]` line or
                null), `rows` {added, removed, changed} (rows pair by skill
                name, or by name and version when a name has several rows on
                one side; a changed pair gives both versions and both `root:`
                values), and `unified`, a unified diff of the two bodies ("" when
                they are equal). check's errors are its own; a FILE that is
                missing, a folder or not UTF-8 text is an error too.

replace and insert take only the body that goes between the markers: they
write `<!-- SKF:BEGIN updated:{date} -->` and `<!-- SKF:END -->` around it
themselves. They refuse (exit 1) content that holds a marker of its own, which
would nest a second pair inside the section. Without --content they read the
body from stdin as UTF-8 on every platform; callers stage it in a file and
redirect it (`replace < file`), because a body passed inline as
`--content "..."` goes through the shell, which expands the backticks and `$`
that snippets carry.

Malformed markers (the Case 4 halt): every `<!-- SKF:BEGIN` in the file,
matched by that prefix with or without an `updated:` date, must end with
`-->` on its own line and be closed by a `<!-- SKF:END -->` after it, with no
text between it and another BEGIN marker before that END. (BEGIN markers with
only blank space between them count as one: the second pair drop-skill and
rename-skill once wrote inside the section. Every rebuild after that left one
more END below the section, so replace and clear take in each END that
follows it with only blank space before it.) A file where one is not closed
is malformed: check reports it with status "error" and case "malformed", and
insert, replace and clear refuse it, all with exit 1 and the file unchanged.
An insert there would append a second section after the unclosed marker, and
the next replace would then take the user's lines between the two BEGIN
markers for SKF's own and delete them. A stray END is never malformed: in a
file with no section, check reports it as `markers_valid: false` with case
append.

Unreadable files: a context file that is a folder, that cannot be read, or
that is not UTF-8 text (a cp1252 CLAUDE.md saved on Windows) is an error
reported as JSON, with exit 1: check returns case "unreadable", read,
insert, replace and clear leave it unchanged, and orphan-detect and assemble
stop when a file they scan is one. root-probe skips such a snippet as it
skips a missing one.

Action-first actions (the action name comes first):
  orphan-detect <context-file>... --exported-skills a,b
                Parse `[skill-name v...]` rows across one or more context
                files, drop rows whose skill_name is in the exported set,
                and report the survivors (deduped by (skill_name, version),
                with verbatim snippet_text and sorted source_files provenance)
                as `orphan_managed_rows`. A file with malformed markers is
                skipped and listed in `malformed_files`; an unreadable one is
                an error.
  root-probe [<snippet-file>...] [--skills-folder DIR] --reference-root .claude/skills/
             [--project-root DIR]
                Read each snippet's first line, parse its `root:` prefix
                (trailing `{skill-name}/` stripped), collect the unique
                `observed_prefixes`, and flag `mismatch` against the reference,
                with the skills that differ in `mismatched_skills`. A draft
                root (`skills/{skill-name}/`, which every workflow that builds
                a skill writes before an export chooses the real one) counts
                as no evidence: its skill is listed in `draft_roots`. With
                --project-root, `disk_root` names the root under DIR that
                holds every mismatched skill's SKILL.md (the reference first,
                then the one observed prefix), or is null. With
                --skills-folder, also probe DIR/{name}/{active_version}/{name}/
                context-snippet.md for each export manifest entry whose
                active_version has a `versions` record (deprecated ones too),
                listed in name order in `snippet_files`; a manifest it cannot
                read is an error. It needs a snippet file or --skills-folder.
  assemble <context-file> --skills-folder DIR --skill-root PREFIX
           [--skill-root-override PREFIX] [--include NAME@VERSION]...
           [--snippet NAME=FILE]... [--snippet-dir DIR] [--renamed OLD:NEW]
           [--dropped NAME]... [--orphan-sources FILE...] [--orphans keep|drop]
           [--out FILE]
                Build the body that replace and insert take for one context
                file and write it to `<context-file>.skf-content`, or to
                --out FILE (creating its folder), with no trailing newline, so
                no caller types a snippet. A dry run, or a preview shown
                before the user confirms, passes --out with a path outside
                the project, so nothing lands beside the context file; --out
                never names a context file the call reads. The skills are
                every entry of DIR/.export-manifest.json (read through
                skf-manifest-ops.py) whose active_version has an entry under
                `versions` that is not deprecated, plus each --include at its
                version (which wins over the manifest). Each one's
                context-snippet.md comes from its versioned package, else its
                `active` link, else the flat layout (--snippet names the file
                to use instead, and --snippet-dir a folder of staged drafts,
                read as DIR/<name>/context-snippet.md for each skill that has
                one there). Its `root:` becomes the effective prefix plus
                the skill name and `/`: --skill-root-override when given, else
                --skill-root. A row found in the managed section of
                <context-file> or of an --orphan-sources file is an orphan
                when the manifest has no entry for its skill and neither
                --include, --renamed OLD nor --dropped names it. Orphans are
                kept verbatim (the default) or left out with --orphans drop;
                pass every target context file, in the same order, to each
                call, so every file keeps the same rows. Rows are sorted by
                name, and the header counts single and stack skills from each
                package's metadata.json `skill_type` (`individual` counts as
                single; an orphan, or a package without one, counts as a stack
                when its row has a `|stack:` line). Returns content_file,
                n_single, n_stack, included[], orphan_rows[],
                skipped_deprecated[], skipped_integrity[],
                skipped_missing_snippet[], skipped_malformed_snippet[],
                malformed_context_files[] and warnings[]. A manifest it cannot
                read, or a context file it scans that is unreadable, is an
                error, and nothing is written.
  resolve-targets [--ides a,b] [--context-file NAME]
                Map config.yaml `ides` to the context files to write, from
                shared/data/ide-context-files.json: `targets` holds one
                {context_file, skill_root, ides} per file, in the order of the
                first IDE that maps to it, whose skill_root wins. An IDE the
                mapping does not list resolves to AGENTS.md with
                `.agents/skills/` and a warning; an empty list resolves to
                AGENTS.md too, with a note.
                --context-file keeps only that file (CLAUDE.md, .cursorrules
                or AGENTS.md). `ides_written` is the union of targets[].ides
                over the files written; `other_context_files` lists the known
                context files no target names.
  gotchas prior <snippet> --skills-folder DIR --skill NAME
  gotchas resolve <snippet> --skills-folder DIR --skill NAME --judgments FILE
                Read and write a skill's `|gotchas:` line, so no caller
                splits, marks or counts it. prior reads the snippet's first
                `|gotchas:` line into `prior_gotchas`, each pitfall {text,
                already_carried, read_whole} (null for no snippet, no line or
                an empty one): it splits on each `; ` outside code spans and
                parentheses, a leading `[CARRIED]` marks a pitfall already
                carried, and a value of more than 3 pitfalls is one pitfall,
                read whole. It reads the first `|api:` line into `prior_api`,
                each name once as {name, parens}, and sets `is_first_export`
                when the export manifest (read through skf-manifest-ops.py)
                records no `last_exported` for the skill. resolve reads the
                same, and a JSON judgments file {"backed": [one boolean per
                prior pitfall], "new_gotchas": [in source order]}, and returns
                {line, is_first_export, left_off, carried, dropped}: the backed
                prior pitfalls, then the new gotchas, at most 3 (the new ones
                past them in left_off), then each unbacked prior pitfall in a
                free slot, marked `[CARRIED]` on a re-export (carried), or
                dropped when it was already carried on a re-export or no slot
                is left. Every pitfall it writes has each `; ` outside a code
                span written as `, `; line is null when it writes none. A
                snippet that is a folder or not UTF-8, a manifest it cannot
                read and a judgments file it cannot use are errors.
  rebuild --project-root DIR --ides a,b --skills-folder DIR [--dropped NAME]...
          [--skill-root-override PREFIX]
                Rebuild the managed section of every context file
                resolve-targets gives for --ides, under DIR, from the
                manifest as it is now: Drop Skill's rebuild after it changed
                the manifest. Per target, in order: check; a file with no
                section (case create or append) is listed in `skipped` as
                {file, case}, and one that is malformed or unreadable in
                `failed` as {file, error}; else assemble with that target's
                own skill_root (or the override), every target file as an
                orphan source (but one check found malformed or unreadable)
                and --dropped, then replace. The staged body is removed
                whatever the outcome. A failure of one file never stops the
                next. `updated` lists the files rewritten, as
                paths under DIR; `warnings` holds one line per assemble
                warning and skipped_* entry, naming its file and skill,
                except the skipped_deprecated entry of a --dropped skill
                (the drop deprecated it). A mapping it cannot read is an
                error (exit 1); otherwise it exits 0, failures included.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BEGIN_MARKER_PREFIX = "<!-- SKF:BEGIN"
END_MARKER = "<!-- SKF:END -->"
MARKER_PATTERN = re.compile(
    r"(<!-- SKF:BEGIN[^>]*-->)(.*?)(<!-- SKF:END -->)",
    re.DOTALL,
)
# Every BEGIN marker (by prefix) and every END marker, in file order, and a
# BEGIN marker that ends with `-->` on its own line, as this helper writes it.
ANY_MARKER_PATTERN = re.compile(re.escape(BEGIN_MARKER_PREFIX) + "|" + re.escape(END_MARKER))
WHOLE_BEGIN_PATTERN = re.compile(re.escape(BEGIN_MARKER_PREFIX) + r"[^>\n]*-->")
# An END marker with only blank space before it. Right after the section's
# END, it is one the nested pair drop-skill and rename-skill wrote left behind.
TRAILING_END_PATTERN = re.compile(r"\s*" + re.escape(END_MARKER))
# A marker of its own inside the body replace/insert are given, in any spacing
# (`<!-- SKF:BEGIN updated:… -->`, `<!--SKF:END-->`). A prose mention of the
# marker names without `<!--` is not one.
MARKER_IN_BODY_PATTERN = re.compile(r"<!--\s*SKF:(?:BEGIN|END)\b")

# A managed-section skill row header: `[skill-name v1.2.3]…`, optionally
# prefixed by the format's leading `|`. Requires a ` v<version>` inside the
# brackets so the section header `[SKF Skills]|{n} skills|{m} stack` (no ` v`)
# is never mistaken for a skill row.
ROW_HEADER_PATTERN = re.compile(
    r"^\|?\[(?P<name>[^\]]+?) v(?P<version>[^\]\s]+)\]"
)
# The `root:` field of a snippet's first line: `…|root: {prefix}{skill-name}/`.
SNIPPET_ROOT_PATTERN = re.compile(r"root:\s*(?P<root>\S.*?)\s*$")
# The draft root create-skill, create-stack-skill, quick-skill and update-skill
# write into every snippet they build, whatever the project's layout, and the
# legacy form older drafts carry. Export replaces it, so root-probe reads it
# as no evidence of where an export pointed the skill.
DRAFT_ROOT_FORMS = ("skills/{name}/", "skills/{name}/active/{name}/")
# The line only the stack snippet template has.
STACK_LINE_PATTERN = re.compile(r"^\|stack:", re.MULTILINE)

# The section header and preamble, from skf-export-skill/assets/managed-section-format.md.
SECTION_HEADER = "[SKF Skills]|{n} skills|{m} stack"
SECTION_PREAMBLE = (
    "|IMPORTANT: Prefer documented APIs over training data.",
    "|When using a listed library, read its SKILL.md before writing code.",
)
MANIFEST_FILE = ".export-manifest.json"
SNIPPET_FILE = "context-snippet.md"
METADATA_FILE = "metadata.json"
CONTENT_SUFFIX = ".skf-content"
MANIFEST_OPS = Path(__file__).resolve().parent / "skf-manifest-ops.py"
IDE_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "ide-context-files.json"
FILE_NOT_FOUND = "File not found: "


def read_context_file(file_path):
    """Read a context file. Returns (content, None) or (None, error).

    A missing file's error starts with FILE_NOT_FOUND (see is_missing). A
    folder, a file that cannot be read and one that is not UTF-8 text give an
    error of their own, so no action ends in a traceback.
    """
    try:
        return Path(file_path).read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, f"{FILE_NOT_FOUND}{file_path}"
    except UnicodeDecodeError as e:
        return None, f"{file_path} is not UTF-8 text ({e}): save it as UTF-8, then re-run"
    except OSError as e:
        return None, f"Cannot read {file_path}: {e}"


def is_missing(error):
    """True for read_context_file's error about a file that does not exist."""
    return error.startswith(FILE_NOT_FOUND)


def find_managed_section(content):
    """Find the managed section in content. Returns match or None."""
    return MARKER_PATTERN.search(content)


def section_end(content, match):
    """Where the section `match` found ends, with the END markers left below it.

    drop-skill and rename-skill once wrote a second marker pair inside the
    section, and every rebuild after that left one more END below it: `match`
    stops at the first END, which closed only the inner BEGIN. So the section
    runs on over each END that follows it with only blank space before it, and
    replace and clear take those in rather than leave them for every later
    write to keep as the user's text. Such an END closes nothing: every BEGIN
    before it is closed already.
    """
    end = match.end()
    while True:
        closing = TRAILING_END_PATTERN.match(content, end)
        if closing is None:
            return end
        end = closing.end()


def find_unclosed_begin(content):
    """The first BEGIN marker no END marker closes, as (line, detail), else None.

    Any `<!-- SKF:BEGIN` counts, by prefix. It must end with `-->` on its own
    line and be closed by a `<!-- SKF:END -->` after it. Text between it and a
    later BEGIN marker, with no END between them, leaves it unclosed: a
    section swap would take that text for SKF's own. BEGIN markers with only
    blank space between them count as one (the second pair drop-skill and
    rename-skill once wrote inside the section). A stray END with no BEGIN
    before it opens nothing, so an insert after it cannot pull the user's text
    into a section.
    """

    def line_of(offset):
        return content.count("\n", 0, offset) + 1

    open_at = open_end = None
    for m in ANY_MARKER_PATTERN.finditer(content):
        if m.group(0) == END_MARKER:
            open_at = None
            continue
        whole = WHOLE_BEGIN_PATTERN.match(content, m.start())
        if not whole:
            return line_of(m.start()), f"<!-- SKF:BEGIN on line {line_of(m.start())} does not end with --> on that line"
        if open_at is not None and content[open_end : m.start()].strip():
            return line_of(open_at), (
                f"<!-- SKF:BEGIN on line {line_of(open_at)} has no matching <!-- SKF:END --> "
                f"before the next <!-- SKF:BEGIN on line {line_of(m.start())}"
            )
        if open_at is None:
            open_at = m.start()
        open_end = whole.end()
    if open_at is None:
        return None
    return line_of(open_at), f"<!-- SKF:BEGIN on line {line_of(open_at)} has no matching <!-- SKF:END --> after it"


def _malformed(file_path, problem, *, write):
    """The error result for a file `find_unclosed_begin` reported."""
    line, detail = problem
    error = (
        f"Malformed SKF markers in {file_path}: {detail}. Fix the markers by hand (restore the "
        "<!-- SKF:END --> line, or remove the stray <!-- SKF:BEGIN), then re-run."
    )
    if write:
        error += " The file was not changed."
    return {"status": "error", "case": "malformed", "begin_line": line, "error": error}


def _atomic_write(file_path, text):
    """Stage `text` into <file>.skf-tmp, fsync, then os.replace into place.

    Mirrors skf-atomic-write.py's `write` so the marker-surgery actions deliver
    the crash-safety the step file documents: a mid-write process kill leaves
    the original file intact rather than truncated. Cleans up the temp file on
    failure. Raises OSError on any I/O failure.
    """
    path = Path(file_path)
    tmp = path.with_name(path.name + ".skf-tmp")
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise diverge the on-disk bytes from the staged
    # string and trip the byte-identity verify below.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, text.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _write_and_verify(file_path, updated, *, expect_section):
    """Atomically write `updated`, then re-read to confirm integrity.

    Returns None on success or an error string. The re-read asserts the on-disk
    bytes match what was staged (so content outside the markers is byte-identical)
    and that managed-section marker presence matches `expect_section`.
    """
    try:
        _atomic_write(file_path, updated)
    except OSError as e:
        return f"atomic write failed: {e}"

    # Re-read raw bytes (no newline translation) for a true byte-identity check.
    try:
        on_disk = Path(file_path).read_bytes()
    except OSError as e:
        return f"post-write verification failed: {e}"
    if on_disk != updated.encode("utf-8"):
        return "post-write verification failed: on-disk bytes do not match staged content"
    if (find_managed_section(on_disk.decode("utf-8")) is not None) != expect_section:
        return (
            "post-write verification failed: managed section "
            + ("missing after write" if expect_section else "still present after clear")
        )
    return None


def cmd_check(file_path):
    """Report the managed section and the write that fits the file (`case`)."""
    content, err = read_context_file(file_path)
    if err and is_missing(err):
        return {"status": "ok", "exists": False, "case": "create", "has_managed_section": False, "markers_valid": True}
    if err:
        return {
            "status": "error",
            "case": "unreadable",
            "error": err,
            "exists": True,
            "has_managed_section": False,
            "markers_valid": False,
        }

    problem = find_unclosed_begin(content)
    if problem:
        result = _malformed(file_path, problem, write=False)
        result.update(exists=True, has_managed_section=False, markers_valid=False, error_detail=problem[1])
        return result

    match = find_managed_section(content)
    if match:
        section_content = match.group(2)
        return {
            "status": "ok",
            "exists": True,
            "case": "regenerate",
            "has_managed_section": True,
            "markers_valid": True,
            "section_length": len(section_content.strip()),
            "section_line_count": len(section_content.strip().split("\n")) if section_content.strip() else 0,
        }
    if END_MARKER in content:
        return {
            "status": "ok",
            "exists": True,
            "case": "append",
            "has_managed_section": False,
            "markers_valid": False,
            "error_detail": "Found <!-- SKF:END --> but no matching <!-- SKF:BEGIN",
        }
    return {"status": "ok", "exists": True, "case": "append", "has_managed_section": False, "markers_valid": True}


def cmd_read(file_path):
    """Extract the managed section content."""
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    match = find_managed_section(content)
    if not match:
        return {"status": "ok", "has_managed_section": False, "content": None}

    return {"status": "ok", "has_managed_section": True, "content": match.group(2)}


def _marker_in_body_error(new_content):
    """An error message when `new_content` holds an SKF marker, else None.

    replace and insert write both markers around the body themselves, so a body
    that carries `<!-- SKF:BEGIN …` or `<!-- SKF:END -->` (the whole managed
    section instead of what goes between its markers) would leave a second
    marker pair nested inside the section.
    """
    if MARKER_IN_BODY_PATTERN.search(new_content) is None:
        return None
    return (
        "content holds an SKF marker (<!-- SKF:BEGIN or <!-- SKF:END): pass only "
        "the body that goes between the markers; this helper writes both markers "
        "and the updated: date itself. The file was not changed."
    )


def cmd_replace(file_path, new_content):
    """Replace managed section content between markers."""
    marker_err = _marker_in_body_error(new_content)
    if marker_err:
        return {"status": "error", "error": marker_err}
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    problem = find_unclosed_begin(content)
    if problem:
        return _malformed(file_path, problem, write=True)
    match = find_managed_section(content)
    if not match:
        return {"status": "error", "error": "No managed section found. Use 'insert' to create one."}

    # Replace content between markers with fresh timestamp
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_section = f"<!-- SKF:BEGIN updated:{today} -->\n{new_content}\n{END_MARKER}"
    updated = content[: match.start()] + new_section + content[section_end(content, match) :]

    verify_err = _write_and_verify(file_path, updated, expect_section=True)
    if verify_err:
        return {"status": "error", "error": verify_err}
    return {"status": "ok", "action": "replaced", "bytes_written": len(updated)}


def cmd_clear(file_path):
    """Remove managed section entirely (markers + content)."""
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    problem = find_unclosed_begin(content)
    if problem:
        return _malformed(file_path, problem, write=True)
    match = find_managed_section(content)
    if not match:
        return {"status": "ok", "action": "no_change", "reason": "No managed section found"}

    # Remove the entire marker block, plus any surrounding blank lines
    before = content[: match.start()].rstrip("\n")
    after = content[section_end(content, match) :].lstrip("\n")
    updated = before + ("\n\n" if before and after else "") + after

    verify_err = _write_and_verify(file_path, updated, expect_section=False)
    if verify_err:
        return {"status": "error", "error": verify_err}
    return {"status": "ok", "action": "cleared", "bytes_written": len(updated)}


def cmd_insert(file_path, new_content):
    """Insert managed section at end of file if not present."""
    marker_err = _marker_in_body_error(new_content)
    if marker_err:
        return {"status": "error", "error": marker_err}
    content, err = read_context_file(file_path)
    if err:
        # A missing file is created; one that cannot be read is left alone.
        if is_missing(err):
            content = ""
        else:
            return {"status": "error", "error": err}

    problem = find_unclosed_begin(content)
    if problem:
        return _malformed(file_path, problem, write=True)
    match = find_managed_section(content)
    if match:
        return {"status": "error", "error": "Managed section already exists. Use 'replace' instead."}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    section = f"\n<!-- SKF:BEGIN updated:{today} -->\n{new_content}\n{END_MARKER}\n"
    updated = content.rstrip("\n") + "\n" + section if content.strip() else section.lstrip("\n")

    verify_err = _write_and_verify(file_path, updated, expect_section=True)
    if verify_err:
        return {"status": "error", "error": verify_err}
    return {"status": "ok", "action": "inserted", "bytes_written": len(updated)}


def _is_row_separator(line):
    """A blank/separator line between snippets: bare `|` or empty."""
    return line.strip() in ("", "|")


def parse_managed_rows(body):
    """Split the between-marker `body` into skill rows.

    Returns a list of {skill_name, version, snippet_text} dicts, one per
    `[skill-name v...]` header found. `snippet_text` is the header line plus its
    continuation lines, captured verbatim (byte-preserved) up to — but not
    including — the next bare-`|` separator, the next row header, or end of body.
    Non-row lines (the `[SKF Skills]` header, the IMPORTANT preamble) are skipped.
    """
    lines = body.split("\n")
    rows = []
    i = 0
    n = len(lines)
    while i < n:
        m = ROW_HEADER_PATTERN.match(lines[i])
        if not m:
            i += 1
            continue
        start = i
        i += 1
        while i < n and not ROW_HEADER_PATTERN.match(lines[i]) and not _is_row_separator(lines[i]):
            i += 1
        rows.append(
            {
                "skill_name": m.group("name"),
                "version": m.group("version"),
                "snippet_text": "\n".join(lines[start:i]),
            }
        )
    return rows


def _row_root(snippet_text):
    """The `root:` value of a row's first line as written, else None."""
    match = SNIPPET_ROOT_PATTERN.search(snippet_text.split("\n", 1)[0])
    return match.group("root") if match else None


def _section_header(body):
    """The first line of `body` that starts with `[SKF Skills]`, else None."""
    return next((line for line in body.split("\n") if line.startswith("[SKF Skills]")), None)


def _pair_rows(old_rows, new_rows):
    """(added, removed, changed) between two bodies' rows, each in skill-name order.

    Rows pair by skill name. A name with several rows on one side pairs by name
    and version instead, and its rows left without a partner are added or
    removed. A pair whose text differs is changed.
    """

    def by_name(rows):
        grouped = {}
        for row in rows:
            grouped.setdefault(row["skill_name"], []).append(row)
        return grouped

    def lone(row):
        return {"skill_name": row["skill_name"], "version": row["version"], "root": _row_root(row["snippet_text"])}

    old_by_name, new_by_name = by_name(old_rows), by_name(new_rows)
    added, removed, changed = [], [], []
    for name in sorted(set(old_by_name) | set(new_by_name)):
        olds, news = old_by_name.get(name, []), new_by_name.get(name, [])
        if len(olds) == 1 and len(news) == 1:
            pairs, left_old, left_new = [(olds[0], news[0])], [], []
        else:
            pairs, left_old, left_new = [], list(olds), []
            for new in news:
                at = next((i for i, old in enumerate(left_old) if old["version"] == new["version"]), None)
                if at is None:
                    left_new.append(new)
                else:
                    pairs.append((left_old.pop(at), new))
        for old, new in pairs:
            if old["snippet_text"] != new["snippet_text"]:
                changed.append(
                    {
                        "skill_name": name,
                        "old_version": old["version"],
                        "new_version": new["version"],
                        "old_root": _row_root(old["snippet_text"]),
                        "new_root": _row_root(new["snippet_text"]),
                    }
                )
        removed += [lone(row) for row in left_old]
        added += [lone(row) for row in left_new]
    return added, removed, changed


def cmd_diff(file_path, content_file):
    """Compare the managed section of `file_path` with the body in `content_file`.

    `case` and its errors are check's. The old body is the section between the
    markers without the newline after the BEGIN marker and the one before the
    END marker, as replace writes it, and empty for create and append. The
    unified diff runs it on to the last END marker section_end takes in, so it
    shows the nested marker lines an older rebuild left that replace removes;
    the rows come from the body the first marker pair holds.
    """
    checked = cmd_check(file_path)
    if checked["status"] != "ok":
        return checked
    new, err = read_context_file(content_file)
    if err:
        return {"status": "error", "error": err}
    old = section = ""
    if checked["case"] == "regenerate":
        content, err = read_context_file(file_path)
        if err:
            return {"status": "error", "error": err}
        match = find_managed_section(content)
        if match:
            old = match.group(2).removeprefix("\n").removesuffix("\n")
            end = section_end(content, match) - len(END_MARKER)
            section = content[match.start(2) : end].removeprefix("\n").removesuffix("\n")
    added, removed, changed = _pair_rows(parse_managed_rows(old), parse_managed_rows(new))
    name = Path(file_path).name
    unified = difflib.unified_diff(
        section.split("\n") if section else [],
        new.split("\n") if new else [],
        fromfile=f"{name} (current)",
        tofile=f"{name} (new)",
        lineterm="",
    )
    return {
        "status": "ok",
        "case": checked["case"],
        "header": {"old": _section_header(old), "new": _section_header(new)},
        "rows": {"added": added, "removed": removed, "changed": changed},
        "unified": "\n".join(unified),
    }


def _scan_rows(context_files, known_names):
    """Rows of skills outside `known_names` across `context_files`, the malformed files and the unreadable ones.

    Reads each file that exists and has a managed section. A file whose
    markers are malformed is skipped and returned in the second list: its
    section cannot be told apart from the user's own text. A file that cannot
    be read, or is not UTF-8 text, is skipped and its error returned in the
    third list: its rows are unknown, so a caller stops rather than drop them.
    Rows are keyed by (skill_name, version): the first-seen snippet_text wins,
    and each file the row appears in is added to its source_files.
    Deterministic: rows sorted by (skill_name, version), source_files sorted.
    """
    orphans = {}  # (name, version) -> {skill_name, version, snippet_text, source_files:set}
    malformed, unreadable = [], []
    for cf in context_files:
        content, err = read_context_file(cf)
        if err:
            if not is_missing(err):
                unreadable.append(err)
            continue  # a missing file has no rows
        if find_unclosed_begin(content):
            malformed.append(cf)
            continue
        match = find_managed_section(content)
        if not match:
            continue  # no managed section, no rows
        for row in parse_managed_rows(match.group(2)):
            if row["skill_name"] in known_names:
                continue
            key = (row["skill_name"], row["version"])
            if key in orphans:
                orphans[key]["source_files"].add(cf)  # keep first-seen snippet_text
            else:
                orphans[key] = {
                    "skill_name": row["skill_name"],
                    "version": row["version"],
                    "snippet_text": row["snippet_text"],
                    "source_files": {cf},
                }
    orphan_rows = [
        {
            "skill_name": v["skill_name"],
            "version": v["version"],
            "snippet_text": v["snippet_text"],
            "source_files": sorted(v["source_files"]),
        }
        for _, v in sorted(orphans.items())
    ]
    return orphan_rows, malformed, unreadable


def cmd_orphan_detect(context_files, exported_skills):
    """Detect managed-section rows absent from the exported skill set.

    Scans every context file that exists and has a managed section, parses its
    skill rows, drops those whose skill_name is in `exported_skills`, and
    accumulates the survivors keyed by (skill_name, version). The first-seen
    snippet_text wins; each file the row appears in is added to source_files.
    Deterministic: rows sorted by (skill_name, version), source_files sorted.
    A file with malformed markers is skipped and listed in malformed_files. A
    file that cannot be read, or is not UTF-8 text, is an error.
    """
    exported = {s.strip() for s in exported_skills.split(",") if s.strip()}
    orphan_rows, malformed, unreadable = _scan_rows(context_files, exported)
    if unreadable:
        return {"status": "error", "error": "; ".join(unreadable)}
    return {"status": "ok", "orphan_managed_rows": orphan_rows, "malformed_files": malformed}


def _holds_skill(project_root, prefix, name):
    """True when the folder `prefix` names under `project_root` holds `name`'s
    SKILL.md: flat, as `npx skills add` installs it, or through the `active`
    link of SKF's versioned layout."""
    base = Path(project_root, prefix, name)
    return (base / "SKILL.md").is_file() or (base / "active" / name / "SKILL.md").is_file()


def cmd_root_probe(snippet_files, reference_root, project_root=None, skills_folder=None):
    """Observe snippet root prefixes and flag mismatch against a reference.

    Reads the first line of each snippet that exists, parses its `root:` value,
    strips the trailing `{skill-name}/` to recover the prefix, and collects the
    unique prefixes. A root in the draft form (DRAFT_ROOT_FORMS) is no
    evidence of where an export pointed the skill: the snippet is left out and
    its skill listed in `draft_roots`. `mismatch` is True when any observed
    prefix differs from `reference_root`, and `mismatched_skills` names the
    skills whose prefix does. Deterministic: every list sorted.

    With `project_root`, `disk_root` says which folder on disk holds the
    mismatched skills: `reference_root` when it holds every one, else the one
    observed prefix when only one was observed and it holds every one, else
    None (also when nothing mismatched).

    With `skills_folder`, the snippet of each version its export manifest
    records is probed too, `{name}/{active_version}/{name}/context-snippet.md`
    for each entry `_active_version` accepts, and `snippet_files` lists those
    paths in name order. A manifest `_read_manifest` cannot read is an error.
    """
    built = []
    if skills_folder is not None:
        exports, err = _read_manifest(skills_folder)
        if err:
            return {"status": "error", "error": err}
        for name in sorted(exports):
            active, reason = _active_version(name, exports[name])
            if reason is None:
                built.append(str(Path(skills_folder) / name / active / name / "context-snippet.md"))
    observed = set()
    drafts = set()
    mismatched = []  # (skill name or None, prefix)
    for sf in [*built, *snippet_files]:
        content, err = read_context_file(sf)
        if err:
            continue  # a missing or unreadable snippet: skip
        first_line = content.split("\n", 1)[0]
        header = ROW_HEADER_PATTERN.match(first_line)
        root_match = SNIPPET_ROOT_PATTERN.search(first_line)
        if not root_match:
            continue  # no root: field, skip
        root_value = root_match.group("root")
        name = header.group("name") if header else None
        if name and root_value in {form.format(name=name) for form in DRAFT_ROOT_FORMS}:
            drafts.add(name)
            continue
        prefix = root_value
        if name and root_value.endswith(name + "/"):
            prefix = root_value[: -len(name + "/")]
        observed.add(prefix)
        if prefix != reference_root:
            mismatched.append((name, prefix))
    observed_prefixes = sorted(observed)
    result = {
        "status": "ok",
        "reference_root": reference_root,
        "observed_prefixes": observed_prefixes,
        "mismatch": bool(mismatched),
        "mismatched_skills": sorted({name for name, _ in mismatched if name}),
        "draft_roots": sorted(drafts),
    }
    if skills_folder is not None:
        result["snippet_files"] = built
    if project_root is not None:
        def held_by(prefix):
            return all(name and _holds_skill(project_root, prefix, name) for name, _ in mismatched)

        disk_root = None
        if mismatched and held_by(reference_root):
            disk_root = reference_root
        elif mismatched and len(observed_prefixes) == 1 and held_by(observed_prefixes[0]):
            disk_root = observed_prefixes[0]
        result["disk_root"] = disk_root
    return result


# ---------------------------------------------------------------------------
# assemble: the managed-section body, built from the manifest and the snippets
# ---------------------------------------------------------------------------


def is_plain_name(value):
    """True for a skill name or version that is one folder name and nothing else."""
    return bool(value) and value not in (".", "..") and not any(c in value for c in "/\\:\0")


def _as_prefix(value):
    """A skill root prefix, with the trailing `/` the `root:` field needs."""
    value = (value or "").strip()
    return value if not value or value.endswith("/") else value + "/"


def _read_manifest(skills_folder):
    """(exports, None) from the export manifest, or (None, error).

    Reads through skf-manifest-ops.py, which installs beside this script, so
    a v1 manifest or a legacy `platforms` field reads the same here as in
    every other manifest step. A missing manifest has no exports.
    """
    try:
        spec = importlib.util.spec_from_file_location("skf_manifest_ops", MANIFEST_OPS)
        ops = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ops)
    except (ImportError, OSError, AttributeError) as e:
        return None, f"cannot load {MANIFEST_OPS.name} beside this script ({e}): re-install SKF"
    manifest_path = Path(skills_folder) / MANIFEST_FILE
    try:
        data, err = ops.read_manifest(manifest_path)
    except (OSError, ValueError, AttributeError, TypeError) as e:
        return None, f"cannot read {manifest_path}: {e}"
    if err:
        return None, f"cannot read {manifest_path}: {err}"
    exports = data.get("exports", {})
    if not isinstance(exports, dict):
        return None, f"cannot read {manifest_path}: `exports` is not an object"
    return exports, None


def _active_version(name, entry):
    """(active_version, None) for a manifest entry the section can use, else (active_version, reason)."""
    if not isinstance(entry, dict):
        return None, "the manifest entry is not an object"
    active = entry.get("active_version")
    if not isinstance(active, str) or not active:
        return None, "the manifest entry has no active_version"
    versions = entry.get("versions")
    if not isinstance(versions, dict) or not isinstance(versions.get(active), dict):
        return active, f"active_version {active} has no entry under versions"
    if not is_plain_name(name) or not is_plain_name(active):
        return active, "the skill name or its active_version is not a plain folder name"
    return active, None


def _find_snippet(skills_folder, name, version, given):
    """(snippet path, source, package folder, paths tried) for one skill.

    The package is the versioned one, else the `active` link's, else the flat
    layout's: the first that holds a context-snippet.md. A `given` snippet
    replaces that search, and its package is the first that holds a
    metadata.json. The path is None when no snippet was found.
    """
    group = Path(skills_folder) / name
    packages = [("versioned", group / version / name), ("active", group / "active" / name), ("flat", group)]
    if given is not None:
        if not Path(given).is_file():
            return None, None, None, [str(given)]
        package = next((p for _, p in packages if (p / METADATA_FILE).is_file()), None)
        return Path(given), "given", package, [str(given)]
    tried = []
    for source, package in packages:
        snippet = package / SNIPPET_FILE
        tried.append(str(snippet))
        if snippet.is_file():
            return snippet, source, package, tried
    return None, None, None, tried


def _row_shape(row_text):
    """`stack` for a row with a `|stack:` line (the stack snippet template), else `single`."""
    return "stack" if STACK_LINE_PATTERN.search(row_text) else "single"


def _skill_type(package, row_text):
    """(skill_type, warning or None): metadata.json's skill_type, else the row's shape.

    `individual` is a single skill, as skf-skill-inventory.py reads it too.
    """
    shape = _row_shape(row_text)
    if package is None:
        return shape, f"no {METADATA_FILE} found, counted as {shape} from its snippet"
    try:
        meta = json.loads((package / METADATA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return shape, f"cannot read {package / METADATA_FILE} ({e}), counted as {shape} from its snippet"
    skill_type = meta.get("skill_type") if isinstance(meta, dict) else None
    if skill_type in ("single", "individual"):
        return "single", None
    if skill_type == "stack":
        return "stack", None
    return shape, (
        f"{package / METADATA_FILE} has no skill_type single, individual or stack, "
        f"counted as {shape} from its snippet"
    )


def _snippet_row(text, name, prefix):
    """The row a snippet adds to the section, or (None, reason).

    Returns ({text, version, root_rewritten, has_root}, None). The row is the
    snippet without its blank edge lines, with `|` before its header line (the
    format puts one there; a snippet that already has it keeps one) and its
    `root:` value set to `prefix` + name + `/`. A snippet whose first line is
    not the `[name vX]` row header of this skill, or that holds an SKF marker,
    is refused: the section could not be parsed back into the same rows.
    """
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None, "the snippet is empty"
    if MARKER_IN_BODY_PATTERN.search(text):
        return None, "the snippet holds an SKF marker (<!-- SKF:BEGIN or <!-- SKF:END)"
    first = lines[0][1:] if lines[0].startswith("|") else lines[0]
    header = ROW_HEADER_PATTERN.match(first)
    if not first.startswith("[") or not header:
        return None, "its first line is not a [skill-name vX.Y.Z] row header"
    if header.group("name") != name:
        return None, f"its header names {header.group('name')}, not {name}"
    root = SNIPPET_ROOT_PATTERN.search(first)
    rewritten = False
    if root:
        new_root = prefix + name + "/"
        rewritten = root.group("root") != new_root
        first = first[: root.start("root")] + new_root + first[root.end("root") :]
    lines[0] = "|" + first
    row = {"text": "\n".join(lines), "version": header.group("version"), "root_rewritten": rewritten, "has_root": root is not None}
    return row, None


def cmd_assemble(
    context_file,
    skills_folder,
    skill_root,
    *,
    override=None,
    includes=(),
    snippets=None,
    snippet_dir=None,
    renamed=None,
    dropped=(),
    orphan_sources=(),
    orphans="keep",
    out=None,
):
    """Build the managed-section body for `context_file` and stage it for replace/insert.

    `includes` is a list of (name, version), `snippets` maps a skill name to
    the snippet file to use, `snippet_dir` is a folder of staged drafts (a
    `snippets` entry wins over it), `renamed` is (old, new) and `dropped` a
    list of names. The body goes to `out`, else to
    <context_file>.skf-content. See the module docstring for the rules.
    """
    snippets = snippets or {}
    prefix = _as_prefix(override) or _as_prefix(skill_root)
    if not prefix:
        return {"status": "error", "error": "the skill root is empty: pass --skill-root (or --skill-root-override)"}
    content_file = out or context_file + CONTENT_SUFFIX
    if out:
        read_here = {os.path.normcase(os.path.realpath(cf)) for cf in [*orphan_sources, context_file]}
        if os.path.normcase(os.path.realpath(out)) in read_here:
            return {
                "status": "error",
                "error": f"--out {out} is a context file this call reads: pass a path of its own. Nothing was written.",
            }
    if not Path(skills_folder).is_dir():
        return {"status": "error", "error": f"the skills folder {skills_folder} does not exist. Nothing was written."}
    exports, err = _read_manifest(skills_folder)
    if err:
        return {"status": "error", "error": f"{err}. Nothing was written."}
    include_versions = dict(includes)

    wanted = {}  # name -> active_version
    skipped_deprecated, skipped_integrity = [], []
    for name in sorted(exports):
        if name in include_versions:
            continue  # --include sets this skill's version
        active, reason = _active_version(name, exports[name])
        if reason:
            skipped_integrity.append({"skill_name": name, "active_version": active, "reason": reason})
        elif exports[name]["versions"][active].get("status") == "deprecated":
            skipped_deprecated.append({"skill_name": name, "version": active})
        else:
            wanted[name] = active
    wanted.update(include_versions)

    entries = []  # (skill_name, version, row text, skill_type)
    included, skipped_missing, skipped_malformed, warnings = [], [], [], []
    for name in sorted(set(snippets) - set(wanted)):
        warnings.append(f"--snippet {name}: not one of the section's skills, so its file was not read")
    for name in sorted(wanted):
        version = wanted[name]
        given = snippets.get(name)
        if given is None and snippet_dir and (Path(snippet_dir) / name / SNIPPET_FILE).is_file():
            given = str(Path(snippet_dir) / name / SNIPPET_FILE)
        path, source, package, tried = _find_snippet(skills_folder, name, version, given)
        if path is None:
            skipped_missing.append({"skill_name": name, "version": version, "tried": tried})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError) as e:
            skipped_malformed.append({"skill_name": name, "version": version, "snippet_path": str(path), "reason": f"cannot read it: {e}"})
            continue
        row, reason = _snippet_row(text, name, prefix)
        if reason:
            skipped_malformed.append({"skill_name": name, "version": version, "snippet_path": str(path), "reason": reason})
            continue
        if not row["has_root"]:
            warnings.append(f"{name}: {path} has no root: field, so its row keeps no root path")
        skill_type, warning = _skill_type(package, row["text"])
        if warning:
            warnings.append(f"{name}: {warning}")
        entries.append((name, row["version"], row["text"], skill_type))
        included.append(
            {
                "skill_name": name,
                "version": row["version"],
                "active_version": version,
                "skill_type": skill_type,
                "snippet_path": str(path),
                "snippet_source": source,
                "root_rewritten": row["root_rewritten"],
            }
        )

    # Orphans: rows of skills the manifest does not know, from every source file.
    known = set(exports) | set(wanted) | set(dropped)
    if renamed:
        known.add(renamed[0])
        if renamed[1] not in wanted:
            warnings.append(f"--renamed: {renamed[1]} is not in the manifest, so the section has no row for it")
    sources, seen = [], set()
    for cf in [*orphan_sources, context_file]:
        key = os.path.normcase(os.path.abspath(cf))
        if key not in seen:
            seen.add(key)
            sources.append(cf)
    orphan_rows, malformed_files, unreadable = _scan_rows(sources, known)
    if unreadable:
        return {"status": "error", "error": f"{'; '.join(unreadable)}. Nothing was written."}
    for row in orphan_rows:
        row["skill_type"] = _row_shape(row["snippet_text"])
    if orphans == "keep":
        # A row that holds a marker variant would make replace and insert refuse the whole body.
        marked = [r for r in orphan_rows if MARKER_IN_BODY_PATTERN.search(r["snippet_text"])]
        if marked:
            where = "; ".join(f"{r['skill_name']} v{r['version']} in {', '.join(r['source_files'])}" for r in marked)
            return {
                "status": "error",
                "error": f"an orphan row to keep holds an SKF marker (<!-- SKF:BEGIN or <!-- SKF:END): {where}. "
                "Fix it by hand, then re-run. Nothing was written.",
            }
        entries += [(r["skill_name"], r["version"], r["snippet_text"], r["skill_type"]) for r in orphan_rows]

    entries.sort(key=lambda e: (e[0], e[1]))
    n_single = sum(1 for e in entries if e[3] == "single")
    n_stack = len(entries) - n_single
    lines = [SECTION_HEADER.format(n=n_single, m=n_stack), *SECTION_PREAMBLE]
    for entry in entries:
        lines += ["|", entry[2]]
    body = "\n".join(lines)

    try:
        Path(content_file).parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(content_file, body)
    except OSError as e:
        return {"status": "error", "error": f"cannot write {content_file}: {e}"}
    return {
        "status": "ok",
        "context_file": context_file,
        "content_file": content_file,
        "skill_root": skill_root,
        "effective_root": prefix,
        "n_single": n_single,
        "n_stack": n_stack,
        "included": included,
        "orphans": orphans,
        "orphan_rows": orphan_rows,
        "skipped_deprecated": skipped_deprecated,
        "skipped_integrity": skipped_integrity,
        "skipped_missing_snippet": skipped_missing,
        "skipped_malformed_snippet": skipped_malformed,
        "malformed_context_files": malformed_files,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# resolve-targets: config.yaml `ides` to the context files to write
# ---------------------------------------------------------------------------


def load_ide_mapping():
    """(ides, unknown_ide) from shared/data/ide-context-files.json. Raises OSError or ValueError."""
    data = json.loads(IDE_DATA_FILE.read_text(encoding="utf-8"))

    def usable(entry):
        return isinstance(entry, dict) and all(isinstance(entry.get(k), str) and entry[k] for k in ("context_file", "skill_root"))

    ides = data.get("ides") if isinstance(data, dict) else None
    unknown = data.get("unknown_ide") if isinstance(data, dict) else None
    if not isinstance(ides, dict) or not usable(unknown) or not all(usable(e) for e in ides.values()):
        raise ValueError("it needs an `ides` object and an `unknown_ide` entry, each with context_file and skill_root")
    return ides, unknown


def cmd_resolve_targets(ides_csv, context_file=None):
    """The context files to write for config.yaml's `ides`, one target per file.

    Unknown IDEs resolve to the mapping's `unknown_ide` with a warning, and an
    empty list to it with a note. `context_file` keeps that one file, with the
    skill root of the first configured IDE that maps to it (else the root the
    mapping gives that file: its first IDE's, or unknown_ide's for AGENTS.md).
    """
    try:
        known_ides, unknown = load_ide_mapping()
    except (OSError, ValueError) as e:
        return {"status": "error", "error": f"cannot read {IDE_DATA_FILE.name}: {e}"}

    ides = []
    for raw in (ides_csv or "").split(","):
        ide = raw.strip()
        if ide and ide not in ides:
            ides.append(ide)
    warnings, notes, unknown_ides = [], [], []
    mapped = []  # (ide, context_file, skill_root)
    for ide in ides:
        entry = known_ides.get(ide)
        if entry is None:
            unknown_ides.append(ide)
            warnings.append(
                f"Unknown IDE '{ide}' in config.yaml: defaulting to {unknown['context_file']} with `{unknown['skill_root']}`"
            )
            entry = unknown
        mapped.append((ide, entry["context_file"], entry["skill_root"]))

    known_files = []
    for entry in [*known_ides.values(), unknown]:
        if entry["context_file"] not in known_files:
            known_files.append(entry["context_file"])

    if context_file:
        if context_file not in known_files:
            return {
                "status": "error",
                "error": f"unknown context file '{context_file}': expected one of {', '.join(known_files)}",
            }
        matching = [(ide, root) for ide, cf, root in mapped if cf == context_file]
        if matching:
            root = matching[0][1]
        elif context_file == unknown["context_file"]:
            root = unknown["skill_root"]
        else:
            root = next(e["skill_root"] for e in known_ides.values() if e["context_file"] == context_file)
        targets = [{"context_file": context_file, "skill_root": root, "ides": [ide for ide, _ in matching]}]
        others = [ide for ide, cf, _ in mapped if cf != context_file]
        if others:
            notes.append(
                f"Exporting to {context_file} only. config.yaml also lists: {', '.join(others)}. "
                "Run without `--context-file` to export to all configured IDEs."
            )
    else:
        targets, by_file = [], {}
        for ide, cf, root in mapped:
            if cf in by_file:
                by_file[cf]["ides"].append(ide)
            else:
                by_file[cf] = {"context_file": cf, "skill_root": root, "ides": [ide]}
                targets.append(by_file[cf])
        for target in targets:
            if len(target["ides"]) > 1:
                notes.append(
                    f"Multiple IDEs target {target['context_file']}: using {target['ides'][0]}'s skill root "
                    f"(`{target['skill_root']}`). Each IDE's skills are installed to its own directory."
                )
        if not targets:
            targets = [{"context_file": unknown["context_file"], "skill_root": unknown["skill_root"], "ides": []}]
            notes.append(
                f"No IDEs configured in config.yaml: defaulting to {unknown['context_file']} with `{unknown['skill_root']}`."
            )

    targeted = {t["context_file"] for t in targets}
    return {
        "status": "ok",
        "targets": targets,
        "ide_map": {ide: cf for ide, cf, _ in mapped},
        "unknown_ides": unknown_ides,
        "other_context_files": [cf for cf in known_files if cf not in targeted],
        "warnings": warnings,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# gotchas: a snippet's `|gotchas:` line read back, and the judgments placed on it
# ---------------------------------------------------------------------------

GOTCHAS_LABEL = "|gotchas:"
API_LABEL = "|api:"
CARRIED_MARK = "[CARRIED]"
GOTCHA_SEPARATOR = "; "
# What a `; ` inside a pitfall is written as, so no pitfall holds the separator.
GOTCHA_SEPARATOR_WRITTEN = ", "
GOTCHA_SLOTS = 3


def split_gotchas(value):
    """The pieces a `|gotchas:` value splits into, before more than 3 are read as one.

    A `; ` separates two pieces only outside a code span (an even number of
    backticks before it) and outside parentheses (every `(` before it outside
    a code span is closed before it: a `)` outside a code span closes the last
    `(` still open, and one with no `(` open closes nothing). Any other `; `
    stays inside its piece.
    """
    pieces, start, ticks, depth = [], 0, 0, 0
    for i, char in enumerate(value):
        if char == "`":
            ticks += 1
        elif ticks % 2 == 0 and char == "(":
            depth += 1
        elif ticks % 2 == 0 and char == ")":
            depth = max(depth - 1, 0)
        elif value.startswith(GOTCHA_SEPARATOR, i) and ticks % 2 == 0 and depth == 0:
            pieces.append(value[start:i])
            start = i + len(GOTCHA_SEPARATOR)
    pieces.append(value[start:])
    return pieces


def _pitfall(piece):
    """(text, already_carried) of one piece: stripped, its leading `[CARRIED]` marker removed."""
    text = piece.strip()
    carried = text.startswith(CARRIED_MARK)
    return (text[len(CARRIED_MARK):].strip() if carried else text), carried


def read_gotchas(value):
    """The pitfalls of a `|gotchas:` value, in order, each {text, already_carried, read_whole}.

    A piece left empty is no pitfall. A value that splits into more than 3
    pitfalls comes from a line resolve never writes, such as an older or
    hand-written one: the whole value is then one pitfall, `read_whole`, and
    already carried when it starts with `[CARRIED]`.
    """
    pitfalls = [pitfall for pitfall in map(_pitfall, split_gotchas(value)) if pitfall[0]]
    if len(pitfalls) > GOTCHA_SLOTS:
        text, carried = _pitfall(value)
        return [{"text": text, "already_carried": carried, "read_whole": True}]
    return [{"text": text, "already_carried": carried, "read_whole": False} for text, carried in pitfalls]


def _written(text):
    """A pitfall as the line writes it: each `; ` outside a code span as `, ` (a code span keeps its `; `)."""
    spans = text.split("`")
    return "`".join(
        span.replace(GOTCHA_SEPARATOR, GOTCHA_SEPARATOR_WRITTEN) if k % 2 == 0 else span for k, span in enumerate(spans)
    )


def write_gotchas(pitfalls):
    """The `|gotchas:` value of (text, carried) pairs: each pitfall written, a carried one after `[CARRIED] `,
    joined on `; `."""
    return GOTCHA_SEPARATOR.join((CARRIED_MARK + " " if carried else "") + _written(text) for text, carried in pitfalls)


def read_api(value):
    """The names of an `|api:` value, in order, each {name, parens}.

    `parens` is true for a name written with `()`, which is removed with its
    spaces. Each name is kept once: its first place and its first mark win.
    """
    names = {}
    for piece in (piece.strip() for piece in value.split(",")):
        parens = piece.endswith("()")
        name = piece[:-2].strip() if parens else piece
        if name and name not in names:
            names[name] = parens
    return [{"name": name, "parens": parens} for name, parens in names.items()]


def _line_value(content, label):
    """The value of the first line that starts with `label`, leading whitespace aside: label removed, stripped."""
    for line in content.splitlines():
        text = line.lstrip()
        if text.startswith(label):
            return text[len(label):].strip()
    return None


def _first_export(skills_folder, skill):
    """(is_first_export, None) from the export manifest, or (None, error).

    True when the manifest has no entry for the skill, or no `versions` record
    of it with a non-empty `last_exported`: the workflow that built or updated
    the skill wrote its snippet, and no export has written one yet.
    """
    exports, err = _read_manifest(skills_folder)
    if err:
        return None, err
    entry = exports.get(skill)
    versions = entry.get("versions") if isinstance(entry, dict) else None
    if not isinstance(versions, dict):
        return True, None
    return not any(isinstance(record, dict) and record.get("last_exported") for record in versions.values()), None


def read_prior(snippet, skills_folder, skill):
    """({prior_gotchas, prior_api, is_first_export}, None) for a skill's prior snippet, or (None, error).

    A missing snippet is no prior snippet. `prior_gotchas` is null for no
    snippet, no `|gotchas:` line or a value that holds no pitfall.
    """
    content, err = read_context_file(snippet)
    if err and not is_missing(err):
        return None, err
    first, err = _first_export(skills_folder, skill)
    if err:
        return None, err
    gotchas = _line_value(content, GOTCHAS_LABEL) if content is not None else None
    api = _line_value(content, API_LABEL) if content is not None else None
    return {
        "prior_gotchas": (read_gotchas(gotchas) or None) if gotchas else None,
        "prior_api": read_api(api) if api else [],
        "is_first_export": first,
    }, None


def read_judgments(path, prior_count):
    """({backed, new_gotchas}, None) from a judgments file, or (None, error).

    The file is a UTF-8 JSON object (a BOM is allowed): `backed` holds one
    boolean per prior pitfall, in order, and `new_gotchas` the new gotchas,
    each a non-empty line that does not start with `[CARRIED]`.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, f"the judgments file {path} does not exist: write it, then run resolve again"
    except UnicodeDecodeError as e:
        return None, f"the judgments file {path} is not UTF-8 text ({e}): write it as UTF-8"
    except ValueError as e:
        return None, f"the judgments file {path} is not JSON ({e})"
    except OSError as e:
        return None, f"cannot read the judgments file {path}: {e}"
    if not isinstance(data, dict):
        return None, f"the judgments file {path} must hold a JSON object with `backed` and `new_gotchas`"
    backed, new = data.get("backed"), data.get("new_gotchas")
    if not isinstance(backed, list) or not all(isinstance(value, bool) for value in backed):
        return None, f"`backed` in {path} must be a list of true or false, one per prior pitfall"
    if not isinstance(new, list) or not all(isinstance(value, str) for value in new):
        return None, f"`new_gotchas` in {path} must be a list of strings, one per new gotcha"
    if len(backed) != prior_count:
        return None, (
            f"`backed` in {path} holds {len(backed)} values, but the prior snippet has {prior_count} pitfalls: "
            "give one per `prior_gotchas` entry, in its order"
        )
    for number, gotcha in enumerate(new, start=1):
        text = gotcha.strip()
        if not text:
            return None, f"`new_gotchas` entry {number} in {path} is empty: remove it"
        if gotcha.splitlines() != [gotcha]:
            return None, f"`new_gotchas` entry {number} in {path} holds a line break: write each gotcha on one line"
        if text.startswith(CARRIED_MARK):
            return None, (
                f"`new_gotchas` entry {number} in {path} starts with `{CARRIED_MARK}`: give the gotcha without it, "
                "since only resolve marks a carried pitfall"
            )
    return {"backed": backed, "new_gotchas": new}, None


def resolve_gotchas(prior_gotchas, backed, new_gotchas, is_first_export):
    """Place the judgments on the `|gotchas:` line: {line, left_off, carried, dropped}.

    `prior_gotchas` is read_gotchas's list (None for none), `backed` one bool
    per entry, `new_gotchas` the new gotchas in source order. A new gotcha
    written as a prior pitfall is written is that prior pitfall, backed, and
    a repeated one is kept once. The line takes the backed prior pitfalls in
    prior order, then the new gotchas, the first 3, unmarked (the new ones
    past them go to `left_off`, as given); then each unbacked prior pitfall in
    prior order: already carried on a re-export, it is dropped
    (`already-carried`); with no free slot, dropped (`no-slot`); else written,
    `[CARRIED]` and in `carried` on a re-export, unmarked on a first export.
    `line` is null when nothing is written.
    """
    prior = list(prior_gotchas or [])
    backed = list(backed)
    if len(backed) != len(prior):
        raise ValueError(f"{len(backed)} judgments for {len(prior)} prior pitfalls")
    prior_forms = [_written(pitfall["text"]) for pitfall in prior]
    new, seen = [], set()
    for gotcha in new_gotchas:
        text = gotcha.strip()
        form = _written(text)
        if form in prior_forms:
            backed = [b or f == form for b, f in zip(backed, prior_forms)]
        elif form not in seen:
            seen.add(form)
            new.append((text, gotcha))
    ordered = [(pitfall["text"], None) for pitfall, b in zip(prior, backed) if b] + new
    line = [(text, False) for text, _ in ordered[:GOTCHA_SLOTS]]
    left_off = [given for _, given in ordered[GOTCHA_SLOTS:] if given is not None]
    carried, dropped = [], []
    for pitfall, b in zip(prior, backed):
        if b:
            continue
        if pitfall["already_carried"] and not is_first_export:
            dropped.append({"text": pitfall["text"], "reason": "already-carried"})
        elif len(line) >= GOTCHA_SLOTS:
            dropped.append({"text": pitfall["text"], "reason": "no-slot"})
        else:
            line.append((pitfall["text"], not is_first_export))
            if not is_first_export:
                carried.append(pitfall["text"])
    return {"line": write_gotchas(line) if line else None, "left_off": left_off, "carried": carried, "dropped": dropped}


def cmd_gotchas_prior(snippet, skills_folder, skill):
    prior, err = read_prior(snippet, skills_folder, skill)
    if err:
        return {"status": "error", "error": err}
    return {"status": "ok", **prior}


def cmd_gotchas_resolve(snippet, skills_folder, skill, judgments_file):
    prior, err = read_prior(snippet, skills_folder, skill)
    if err:
        return {"status": "error", "error": err}
    judgments, err = read_judgments(judgments_file, len(prior["prior_gotchas"] or []))
    if err:
        return {"status": "error", "error": err}
    placed = resolve_gotchas(
        prior["prior_gotchas"], judgments["backed"], judgments["new_gotchas"], prior["is_first_export"]
    )
    return {
        "status": "ok",
        "line": placed["line"],
        "is_first_export": prior["is_first_export"],
        "left_off": placed["left_off"],
        "carried": placed["carried"],
        "dropped": placed["dropped"],
    }


# ---------------------------------------------------------------------------
# rebuild: every target's section, after a manifest change
# ---------------------------------------------------------------------------

# What each assemble skip says, by its key.
SKIP_REASONS = {
    "skipped_deprecated": "its active version {version} is deprecated, so it has no row",
    "skipped_integrity": "its manifest entry cannot be used ({reason}), so it has no row",
    "skipped_missing_snippet": "no context-snippet.md was found for {version}, so it has no row",
    "skipped_malformed_snippet": "its snippet {snippet_path} was skipped: {reason}",
}


def _skip_warnings(context_file, assembled, dropped):
    """One line per assemble warning and skipped_* entry, naming the file and the skill."""
    lines = [f"{context_file}: {warning}" for warning in assembled.get("warnings", [])]
    for key, reason in SKIP_REASONS.items():
        for entry in assembled.get(key, []):
            if key == "skipped_deprecated" and entry["skill_name"] in dropped:
                continue  # the drop itself deprecated it
            values = {"version": entry.get("version") or entry.get("active_version"), **entry}
            lines.append(f"{context_file}: {entry['skill_name']}: {reason.format(**values)}")
    return lines


def cmd_rebuild(project_root, ides_csv, skills_folder, *, dropped=(), override=None):
    """Rebuild the managed section of each context file `ides_csv` maps to under `project_root`."""
    targets = cmd_resolve_targets(ides_csv)
    if targets["status"] != "ok":
        return {"status": "error", "error": f"{targets['error']}. No context file was rebuilt."}
    paths = [str(Path(project_root) / t["context_file"]) for t in targets["targets"]]
    checks = [cmd_check(path) for path in paths]
    # A file that cannot be read is no orphan source: the others are rebuilt without its rows.
    sources = [path for path, check in zip(paths, checks) if check["status"] == "ok"]
    updated, failed, skipped, warnings = [], [], [], []
    for target, path, check in zip(targets["targets"], paths, checks):
        if check["status"] != "ok":
            failed.append({"file": path, "error": check["error"]})
            continue
        if check["case"] != "regenerate":
            skipped.append({"file": path, "case": check["case"]})
            continue
        try:
            stage = tempfile.mkdtemp(prefix="skf-rebuild-")
        except OSError as e:
            failed.append({"file": path, "error": f"cannot create a folder to stage the body in: {e}"})
            continue
        try:
            assembled = cmd_assemble(path, skills_folder, target["skill_root"], override=override,
                                     dropped=dropped, orphan_sources=sources,
                                     out=str(Path(stage) / (target["context_file"] + CONTENT_SUFFIX)))
            if assembled["status"] != "ok":
                failed.append({"file": path, "error": assembled["error"]})
                continue
            warnings += _skip_warnings(target["context_file"], assembled, dropped)
            try:
                body = Path(assembled["content_file"]).read_bytes().decode("utf-8")
            except (OSError, ValueError) as e:
                failed.append({"file": path, "error": f"cannot read the staged body: {e}"})
                continue
            replaced = cmd_replace(path, body)
            if replaced["status"] != "ok":
                failed.append({"file": path, "error": replaced["error"]})
                continue
            updated.append(path)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    return {"status": "ok", "updated": updated, "failed": failed, "skipped": skipped, "warnings": warnings}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

ACTION_FIRST = ("orphan-detect", "root-probe", "assemble", "resolve-targets", "gotchas", "rebuild")


def _include_list(value):
    """--include: NAME@VERSION, or several separated by commas."""
    items = []
    for part in filter(None, (p.strip() for p in value.split(","))):
        name, sep, version = part.partition("@")
        if not sep or not is_plain_name(name) or not is_plain_name(version):
            raise argparse.ArgumentTypeError(f"expected NAME@VERSION with plain folder names, got {part!r}")
        items.append((name, version))
    return items


def _name_list(value):
    """--dropped: a skill name, or several separated by commas."""
    names = [part for part in (p.strip() for p in value.split(",")) if part]
    if not all(is_plain_name(n) for n in names):
        raise argparse.ArgumentTypeError(f"expected skill names, got {value!r}")
    return names


def _renamed_pair(value):
    """--renamed: OLD:NEW."""
    old, sep, new = value.partition(":")
    if not sep or not is_plain_name(old) or not is_plain_name(new) or old == new:
        raise argparse.ArgumentTypeError(f"expected OLD:NEW with two different skill names, got {value!r}")
    return old, new


def _snippet_pair(value):
    """--snippet: NAME=FILE."""
    name, sep, path = value.partition("=")
    if not sep or not is_plain_name(name) or not path:
        raise argparse.ArgumentTypeError(f"expected NAME=FILE, got {value!r}")
    return name, path


def _skill_name(value):
    """--skill: one skill name, a plain folder name."""
    if not is_plain_name(value):
        raise argparse.ArgumentTypeError(f"expected a skill name, got {value!r}")
    return value


def _action_parser(action):
    """The argparse parser of one action-first action."""
    prog = f"skf-rebuild-managed-sections.py {action}"
    if action == "orphan-detect":
        parser = argparse.ArgumentParser(
            prog=prog, description="Detect managed-section rows absent from the exported skill set."
        )
        parser.add_argument("context_files", nargs="+", help="Context file paths to scan")
        parser.add_argument(
            "--exported-skills",
            default="",
            help="Comma-separated skill names being exported (excluded from orphans)",
        )
    elif action == "root-probe":
        parser = argparse.ArgumentParser(
            prog=prog, description="Observe snippet root prefixes and flag mismatch against a reference."
        )
        parser.add_argument("snippet_files", nargs="*", help="Snippet file paths to probe")
        parser.add_argument(
            "--skills-folder",
            help="skills_output_folder: also probe the snippet of each version its export manifest records",
        )
        parser.add_argument(
            "--reference-root",
            required=True,
            help="Reference skill root prefix to compare observed prefixes against",
        )
        parser.add_argument(
            "--project-root",
            help="The project the roots are relative to: report in disk_root which root holds "
            "the mismatched skills",
        )
    elif action == "assemble":
        parser = argparse.ArgumentParser(
            prog=prog,
            description="Build a context file's managed-section body from the export manifest and the "
            "skill snippets, and write it to <context-file>.skf-content (or --out FILE) for replace or insert.",
        )
        parser.add_argument("context_file", help="The context file the body is for")
        parser.add_argument("--skills-folder", required=True, help="skills_output_folder, which holds .export-manifest.json")
        parser.add_argument("--skill-root", required=True, help="The context file's skill root, such as .claude/skills/")
        parser.add_argument(
            "--skill-root-override",
            default="",
            help="snippet_skill_root_override from config.yaml: every row's root uses it instead of --skill-root",
        )
        parser.add_argument(
            "--include",
            action="append",
            type=_include_list,
            default=[],
            metavar="NAME@VERSION",
            help="A skill to write at this version whatever the manifest says (the skills being exported)",
        )
        parser.add_argument(
            "--snippet",
            action="append",
            type=_snippet_pair,
            default=[],
            metavar="NAME=FILE",
            help="Read NAME's snippet from FILE instead of its package",
        )
        parser.add_argument(
            "--snippet-dir",
            metavar="DIR",
            help="A folder of staged snippet drafts: a skill with DIR/<name>/context-snippet.md "
            "reads it instead of its package (--snippet wins over it)",
        )
        parser.add_argument("--renamed", type=_renamed_pair, metavar="OLD:NEW", help="A rename: OLD's rows are not orphans")
        parser.add_argument(
            "--dropped",
            action="append",
            type=_name_list,
            default=[],
            metavar="NAME",
            help="A dropped skill: its rows are not orphans",
        )
        parser.add_argument(
            "--orphan-sources",
            nargs="+",
            default=[],
            metavar="FILE",
            help="Every target context file, scanned for orphan rows (the context file itself always is)",
        )
        parser.add_argument(
            "--orphans",
            choices=("keep", "drop"),
            default="keep",
            help="Write the orphan rows verbatim (keep, the default) or leave them out (drop)",
        )
        parser.add_argument(
            "--out",
            metavar="FILE",
            help="Write the body to FILE instead of <context-file>.skf-content (a dry run, or a preview "
            "before the user confirms, passes a path outside the project)",
        )
    elif action == "gotchas":
        parser = argparse.ArgumentParser(
            prog=prog,
            description="Read a snippet's prior `|gotchas:` and `|api:` lines and whether an export wrote it "
            "(prior), or place the gotchas judgments on the line (resolve).",
        )
        parser.add_argument(
            "mode",
            choices=("prior", "resolve"),
            help="prior: read the prior lines; resolve: place the judgments of --judgments on the gotchas line",
        )
        parser.add_argument("snippet", help="The skill's prior context-snippet.md (a missing file is no prior snippet)")
        parser.add_argument("--skills-folder", required=True, help="skills_output_folder, which holds .export-manifest.json")
        parser.add_argument("--skill", required=True, type=_skill_name, help="The skill's name in the export manifest")
        parser.add_argument(
            "--judgments",
            metavar="FILE",
            help='resolve only: a JSON file {"backed": [one boolean per prior pitfall], "new_gotchas": [...]}',
        )
    elif action == "rebuild":
        parser = argparse.ArgumentParser(
            prog=prog,
            description="Rebuild the managed section of every context file config.yaml's IDE list maps to, "
            "from the export manifest as it is now (Drop Skill, after its manifest change).",
        )
        parser.add_argument("--project-root", required=True, help="The project the context files sit in")
        parser.add_argument("--ides", default="", help="Comma-separated IDE identifiers from config.yaml `ides`")
        parser.add_argument("--skills-folder", required=True, help="skills_output_folder, which holds .export-manifest.json")
        parser.add_argument(
            "--dropped",
            action="append",
            type=_name_list,
            default=[],
            metavar="NAME",
            help="A dropped skill: its rows are not orphans, and its skipped_deprecated entry is no warning",
        )
        parser.add_argument(
            "--skill-root-override",
            default="",
            help="snippet_skill_root_override from config.yaml: every row's root uses it instead of the target's",
        )
    else:  # resolve-targets
        parser = argparse.ArgumentParser(
            prog=prog, description="Map config.yaml's IDE list to the context files to write and their skill roots."
        )
        parser.add_argument("--ides", default="", help="Comma-separated IDE identifiers from config.yaml `ides`")
        parser.add_argument(
            "--context-file",
            default="",
            help="Keep only this context file (CLAUDE.md, .cursorrules or AGENTS.md)",
        )
    return parser


def _run_action_first(argv):
    """Parse and run an action-first action. Returns (result_dict, exit_code).

    These take the action name first (`orphan-detect <file>...`) rather than
    the legacy `<file> <action>` shape, so they are parsed with argparse and
    routed here before the legacy path.
    """
    action = argv[0]
    parser = _action_parser(action)
    args = parser.parse_args(argv[1:])
    if action == "orphan-detect":
        result = cmd_orphan_detect(args.context_files, args.exported_skills)
    elif action == "root-probe":
        if args.skills_folder == "":
            parser.error("--skills-folder needs a folder")
        if not args.snippet_files and args.skills_folder is None:
            parser.error("root-probe needs a snippet file or --skills-folder")
        result = cmd_root_probe(args.snippet_files, args.reference_root, args.project_root, args.skills_folder)
    elif action == "assemble":
        includes = [item for group in args.include for item in group]
        names = [name for name, _ in includes]
        if len(set(names)) != len(names):
            parser.error("--include names a skill twice")
        snippet_names = [name for name, _ in args.snippet]
        if len(set(snippet_names)) != len(snippet_names):
            parser.error("--snippet names a skill twice")
        result = cmd_assemble(
            args.context_file,
            args.skills_folder,
            args.skill_root,
            override=args.skill_root_override,
            includes=includes,
            snippets=dict(args.snippet),
            snippet_dir=args.snippet_dir,
            renamed=args.renamed,
            dropped=[name for group in args.dropped for name in group],
            orphan_sources=args.orphan_sources,
            orphans=args.orphans,
            out=args.out,
        )
    elif action == "gotchas":
        if args.skills_folder == "":
            parser.error("--skills-folder needs a folder")
        if args.mode == "resolve" and not args.judgments:
            parser.error("gotchas resolve needs --judgments FILE")
        if args.mode == "prior" and args.judgments is not None:
            parser.error("gotchas prior takes no --judgments")
        if args.mode == "prior":
            result = cmd_gotchas_prior(args.snippet, args.skills_folder, args.skill)
        else:
            result = cmd_gotchas_resolve(args.snippet, args.skills_folder, args.skill, args.judgments)
    elif action == "rebuild":
        result = cmd_rebuild(
            args.project_root,
            args.ides,
            args.skills_folder,
            dropped=[name for group in args.dropped for name in group],
            override=args.skill_root_override,
        )
    else:
        result = cmd_resolve_targets(args.ides, args.context_file)
    return result, 0 if result["status"] == "ok" else 1


def main():
    # Action-first actions take a positional file list or flags only, so the
    # action comes first (`orphan-detect <file>...`) rather than the legacy
    # `<file> <action>` shape.
    if len(sys.argv) >= 2 and sys.argv[1] in ACTION_FIRST:
        result, code = _run_action_first(sys.argv[1:])
        print(json.dumps(result, indent=2))
        sys.exit(code)

    if len(sys.argv) < 3:
        print("Usage: python3 skf-rebuild-managed-sections.py <context-file> <action> [--content <text>] [--content-file <file>]", file=sys.stderr)
        print("Actions: read, replace, clear, insert, check, diff", file=sys.stderr)
        print("   or: python3 skf-rebuild-managed-sections.py {" + ",".join(ACTION_FIRST) + "} ...", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    action = sys.argv[2]

    content_arg = None
    if "--content" in sys.argv:
        idx = sys.argv.index("--content")
        if idx + 1 < len(sys.argv):
            content_arg = sys.argv[idx + 1]
    elif action in ("replace", "insert") and not sys.stdin.isatty():
        # Read the bytes and decode them as UTF-8 ourselves: sys.stdin decodes
        # a pipe or redirect with the locale's code page (cp1252 on Windows),
        # which turns the em dash every snippet's IMPORTANT line carries into
        # mojibake that the byte-identity check then accepts.
        try:
            content_arg = sys.stdin.buffer.read().decode("utf-8")
        except UnicodeDecodeError as e:
            print(json.dumps({"status": "error", "error": f"content on stdin is not UTF-8: {e}"}, indent=2))
            sys.exit(1)

    if action == "check":
        result = cmd_check(file_path)
    elif action == "read":
        result = cmd_read(file_path)
    elif action == "replace":
        if content_arg is None or not content_arg.strip():
            result = {"status": "error", "error": "replace requires non-empty --content or stdin"}
        else:
            result = cmd_replace(file_path, content_arg)
    elif action == "clear":
        result = cmd_clear(file_path)
    elif action == "diff":
        # Read by hand, as --content is: `"--content" in sys.argv` never matches it.
        content_file = None
        if "--content-file" in sys.argv:
            idx = sys.argv.index("--content-file")
            if idx + 1 < len(sys.argv):
                content_file = sys.argv[idx + 1]
        if not content_file:
            result = {"status": "error", "error": "diff requires --content-file <file>"}
        else:
            result = cmd_diff(file_path, content_file)
    elif action == "insert":
        if content_arg is None or not content_arg.strip():
            result = {"status": "error", "error": "insert requires non-empty --content or stdin"}
        else:
            result = cmd_insert(file_path, content_arg)
    else:
        result = {"status": "error", "error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
