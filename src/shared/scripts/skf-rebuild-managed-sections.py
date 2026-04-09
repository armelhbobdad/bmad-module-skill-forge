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
"""

from __future__ import annotations

import json
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


def read_context_file(file_path):
    """Read a context file. Returns (content, None) or (None, error)."""
    try:
        return Path(file_path).read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, f"File not found: {file_path}"


def find_managed_section(content):
    """Find the managed section in content. Returns match or None."""
    return MARKER_PATTERN.search(content)


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

    Path(file_path).write_text(updated, encoding="utf-8")
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

    Path(file_path).write_text(updated, encoding="utf-8")
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

    Path(file_path).write_text(updated, encoding="utf-8")
    return {"status": "ok", "action": "inserted", "bytes_written": len(updated)}


def main():
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
        if content_arg is None:
            result = {"status": "error", "error": "replace requires --content or stdin"}
        else:
            result = cmd_replace(file_path, content_arg)
    elif action == "clear":
        result = cmd_clear(file_path)
    elif action == "insert":
        if content_arg is None:
            result = {"status": "error", "error": "insert requires --content or stdin"}
        else:
            result = cmd_insert(file_path, content_arg)
    else:
        result = {"status": "error", "error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
