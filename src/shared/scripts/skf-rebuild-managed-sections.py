# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Rebuild Managed Sections — Context file marker surgery.

Reads a context file (CLAUDE.md/AGENTS.md/.cursorrules), finds the
<!-- SKF:BEGIN --> / <!-- SKF:END --> markers, and replaces the managed
section with new content. Preserves all content outside the markers.

CLI: python3 skf-rebuild-managed-sections.py <context-file> <action> [args]

Actions:
  read          — Extract current managed section content
  replace       — Replace managed section with content from stdin or --content
  clear         — Remove managed section entirely (markers + content)
  insert        — Insert managed section if not present (at end of file)
  check         — Check if managed section exists, report status

Query actions (read-only, take positional file lists instead of <file> <action>):
  orphan-detect <context-file>... --exported-skills a,b
                — Parse `[skill-name v...]` rows across one or more context
                  files, drop rows whose skill_name is in the exported set,
                  and report the survivors (deduped by (skill_name, version),
                  with verbatim snippet_text and sorted source_files provenance)
                  as `orphan_managed_rows`.
  root-probe <snippet-file>... --reference-root .claude/skills/
                — Read each snippet's first line, parse its `root:` prefix
                  (trailing `{skill-name}/` stripped), collect the unique
                  `observed_prefixes`, and flag `mismatch` against the reference.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BEGIN_MARKER_PREFIX = "<!-- SKF:BEGIN"
END_MARKER = "<!-- SKF:END -->"
MARKER_PATTERN = re.compile(
    r"(<!-- SKF:BEGIN[^>]*-->)(.*?)(<!-- SKF:END -->)",
    re.DOTALL,
)

# A managed-section skill row header: `[skill-name v1.2.3]…`, optionally
# prefixed by the format's leading `|`. Requires a ` v<version>` inside the
# brackets so the section header `[SKF Skills]|{n} skills|{m} stack` (no ` v`)
# is never mistaken for a skill row.
ROW_HEADER_PATTERN = re.compile(
    r"^\|?\[(?P<name>[^\]]+?) v(?P<version>[^\]\s]+)\]"
)
# The `root:` field of a snippet's first line: `…|root: {prefix}{skill-name}/`.
SNIPPET_ROOT_PATTERN = re.compile(r"root:\s*(?P<root>\S.*?)\s*$")


def read_context_file(file_path):
    """Read a context file. Returns (content, None) or (None, error)."""
    try:
        return Path(file_path).read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, f"File not found: {file_path}"


def find_managed_section(content):
    """Find the managed section in content. Returns match or None."""
    return MARKER_PATTERN.search(content)


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
    """Check if managed section exists."""
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    has_begin = BEGIN_MARKER_PREFIX in content
    has_end = END_MARKER in content
    match = find_managed_section(content)

    if match:
        section_content = match.group(2)
        return {
            "status": "ok",
            "has_managed_section": True,
            "markers_valid": True,
            "section_length": len(section_content.strip()),
            "section_line_count": len(section_content.strip().split("\n")) if section_content.strip() else 0,
        }
    elif has_begin and not has_end:
        return {
            "status": "ok",
            "has_managed_section": False,
            "markers_valid": False,
            "error_detail": "Found <!-- SKF:BEGIN but no matching <!-- SKF:END -->",
        }
    elif not has_begin and has_end:
        return {
            "status": "ok",
            "has_managed_section": False,
            "markers_valid": False,
            "error_detail": "Found <!-- SKF:END --> but no matching <!-- SKF:BEGIN",
        }
    else:
        return {"status": "ok", "has_managed_section": False, "markers_valid": True}


def cmd_read(file_path):
    """Extract the managed section content."""
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    match = find_managed_section(content)
    if not match:
        return {"status": "ok", "has_managed_section": False, "content": None}

    return {"status": "ok", "has_managed_section": True, "content": match.group(2)}


def cmd_replace(file_path, new_content):
    """Replace managed section content between markers."""
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    match = find_managed_section(content)
    if not match:
        return {"status": "error", "error": "No managed section found. Use 'insert' to create one."}

    # Replace content between markers with fresh timestamp
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_section = f"<!-- SKF:BEGIN updated:{today} -->\n{new_content}\n{END_MARKER}"
    updated = content[: match.start()] + new_section + content[match.end() :]

    verify_err = _write_and_verify(file_path, updated, expect_section=True)
    if verify_err:
        return {"status": "error", "error": verify_err}
    return {"status": "ok", "action": "replaced", "bytes_written": len(updated)}


def cmd_clear(file_path):
    """Remove managed section entirely (markers + content)."""
    content, err = read_context_file(file_path)
    if err:
        return {"status": "error", "error": err}

    match = find_managed_section(content)
    if not match:
        return {"status": "ok", "action": "no_change", "reason": "No managed section found"}

    # Remove the entire marker block, plus any surrounding blank lines
    before = content[: match.start()].rstrip("\n")
    after = content[match.end() :].lstrip("\n")
    updated = before + ("\n\n" if before and after else "") + after

    verify_err = _write_and_verify(file_path, updated, expect_section=False)
    if verify_err:
        return {"status": "error", "error": verify_err}
    return {"status": "ok", "action": "cleared", "bytes_written": len(updated)}


def cmd_insert(file_path, new_content):
    """Insert managed section at end of file if not present."""
    content, err = read_context_file(file_path)
    if err:
        # File doesn't exist — create it
        if "not found" in err.lower():
            content = ""
        else:
            return {"status": "error", "error": err}

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


def cmd_orphan_detect(context_files, exported_skills):
    """Detect managed-section rows absent from the exported skill set.

    Scans every context file that exists and has a managed section, parses its
    skill rows, drops those whose skill_name is in `exported_skills`, and
    accumulates the survivors keyed by (skill_name, version). The first-seen
    snippet_text wins; each file the row appears in is added to source_files.
    Deterministic: rows sorted by (skill_name, version), source_files sorted.
    """
    exported = {s.strip() for s in exported_skills.split(",") if s.strip()}
    orphans = {}  # (name, version) -> {skill_name, version, snippet_text, source_files:set}
    for cf in context_files:
        content, err = read_context_file(cf)
        if err:
            continue  # missing file — no orphans by definition
        match = find_managed_section(content)
        if not match:
            continue  # no managed section — no orphans
        for row in parse_managed_rows(match.group(2)):
            if row["skill_name"] in exported:
                continue  # not an orphan — it is being (re)exported
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
    return {"status": "ok", "orphan_managed_rows": orphan_rows}


def cmd_root_probe(snippet_files, reference_root):
    """Observe snippet root prefixes and flag mismatch against a reference.

    Reads the first line of each snippet that exists, parses its `root:` value,
    strips the trailing `{skill-name}/` to recover the prefix, and collects the
    unique prefixes. `mismatch` is True when any observed prefix differs from
    `reference_root`. Deterministic: observed_prefixes sorted.
    """
    observed = set()
    for sf in snippet_files:
        content, err = read_context_file(sf)
        if err:
            continue  # missing snippet — skip
        first_line = content.split("\n", 1)[0]
        header = ROW_HEADER_PATTERN.match(first_line)
        root_match = SNIPPET_ROOT_PATTERN.search(first_line)
        if not root_match:
            continue  # no root: field — skip
        root_value = root_match.group("root")
        prefix = root_value
        if header:
            suffix = header.group("name") + "/"
            if root_value.endswith(suffix):
                prefix = root_value[: -len(suffix)]
        observed.add(prefix)
    observed_prefixes = sorted(observed)
    return {
        "status": "ok",
        "reference_root": reference_root,
        "observed_prefixes": observed_prefixes,
        "mismatch": any(p != reference_root for p in observed_prefixes),
    }


def _run_query_action(argv):
    """Dispatch the read-only query actions (orphan-detect / root-probe).

    These take a positional file list rather than the legacy `<file> <action>`
    shape, so they are parsed with argparse and routed here before the legacy
    path. Returns (result_dict, exit_code).
    """
    action = argv[0]
    if action == "orphan-detect":
        parser = argparse.ArgumentParser(
            prog="skf-rebuild-managed-sections.py orphan-detect",
            description="Detect managed-section rows absent from the exported skill set.",
        )
        parser.add_argument("context_files", nargs="+", help="Context file paths to scan")
        parser.add_argument(
            "--exported-skills",
            default="",
            help="Comma-separated skill names being exported (excluded from orphans)",
        )
        args = parser.parse_args(argv[1:])
        return cmd_orphan_detect(args.context_files, args.exported_skills), 0
    # action == "root-probe"
    parser = argparse.ArgumentParser(
        prog="skf-rebuild-managed-sections.py root-probe",
        description="Observe snippet root prefixes and flag mismatch against a reference.",
    )
    parser.add_argument("snippet_files", nargs="+", help="Snippet file paths to probe")
    parser.add_argument(
        "--reference-root",
        required=True,
        help="Reference skill root prefix to compare observed prefixes against",
    )
    args = parser.parse_args(argv[1:])
    return cmd_root_probe(args.snippet_files, args.reference_root), 0


def main():
    # Query actions take a positional file list, so they are action-first
    # (`orphan-detect <file>...`) rather than the legacy `<file> <action>` shape.
    if len(sys.argv) >= 2 and sys.argv[1] in ("orphan-detect", "root-probe"):
        result, code = _run_query_action(sys.argv[1:])
        print(json.dumps(result, indent=2))
        sys.exit(code)

    if len(sys.argv) < 3:
        print("Usage: python3 skf-rebuild-managed-sections.py <context-file> <action> [--content <text>]", file=sys.stderr)
        print("Actions: read, replace, clear, insert, check", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    action = sys.argv[2]

    content_arg = None
    if "--content" in sys.argv:
        idx = sys.argv.index("--content")
        if idx + 1 < len(sys.argv):
            content_arg = sys.argv[idx + 1]
    elif action in ("replace", "insert") and not sys.stdin.isatty():
        content_arg = sys.stdin.read()

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
