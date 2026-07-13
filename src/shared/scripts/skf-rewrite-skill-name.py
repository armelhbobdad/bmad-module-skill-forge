#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Rewrite Skill Name — field-scoped, meaning-independent rename transforms.

Performs the deterministic in-file name substitutions the rename workflow needs,
so the LLM never hand-edits JSON or eyeballs "only within the frontmatter". Each
transform is scoped to a single field / region and applied by exact-key or
anchored-pattern match, then written atomically (stage to <target>.skf-tmp,
fsync, rename) in the same call — a process kill mid-rewrite leaves the original
file intact.

Four file kinds (one per --kind), each doing exactly one field-scoped edit:

  skill-frontmatter  Replace the top-level `name:` value inside the YAML
                     frontmatter block ONLY (between the leading `---` and the
                     first `---` on its own line). Body text is never touched,
                     so a legitimate mention of the old name below the closing
                     `---` survives. Anchored on `^name:` so a longer key like
                     `renamed:` or a nested `  name:` is not matched.

  metadata-json      JSON round-trip: parse, set `name` = <new-name>, re-emit
                     with indent=2. Key order is preserved (dict insertion
                     order); no manual string surgery, so no risk of reordering
                     or dropping keys.

  provenance-json    Same JSON round-trip, but the field is `skill_name`.

  context-snippet    Rewrite the display header `[<old> v...]` -> `[<new> v...]`
                     (version suffix preserved) and every `root:` path. Root
                     rewrite parses `root: {prefix}{old}/`, preserves the prefix
                     verbatim, and swaps the trailing `{old}/` segment for
                     `{new}/` — so any IDE prefix (.claude/skills/,
                     .windsurf/skills/, draft skills/, ...) is handled without
                     enumeration and an old name that is a substring of the
                     prefix is left alone. The legacy nested draft form
                     `root: skills/{old}/active/{old}/` is flattened to
                     `root: skills/{new}/`.

Exit codes:
  0  success (file processed; written iff content changed)
  1  user error (bad args, invalid new name, target not found)
  2  operation failure (unparseable structure, atomic write failed)

CLI examples:
  python3 skf-rewrite-skill-name.py SKILL.md \
      --kind skill-frontmatter --old-name rename --new-name rename-skill
  python3 skf-rewrite-skill-name.py context-snippet.md \
      --kind context-snippet --old-name rename --new-name rename-skill --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# The module's canonical skill-name rule (same regex as skf-validate-output.py /
# skf-validate-brief-inputs.py / skf-rename-skill select.md §5).
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")

KINDS = ("skill-frontmatter", "metadata-json", "context-snippet", "provenance-json")


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


# --- Atomic write (self-contained; mirrors skf-atomic-write.py cmd_write) -----


def atomic_write_text(target: Path, text: str) -> int:
    """Write `text` to `target` atomically via temp + fsync + rename.

    Returns the number of bytes written. Raises OSError on failure.
    """
    data = text.encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".skf-tmp")
    # O_BINARY (Windows only; 0 elsewhere) suppresses the text-mode \n -> \r\n
    # translation that would otherwise corrupt verbatim writes on Windows.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except OSError:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    return len(data)


# --- Pure transforms (import-friendly for unit tests) -------------------------


def rewrite_frontmatter_name(content: str, new_name: str):
    """Replace the top-level `name:` value inside the frontmatter block only.

    Returns (new_content, old_value, matched). Raises ValueError if the content
    has no valid `--- ... ---` frontmatter block.
    """
    if not content.startswith("---\n"):
        raise ValueError("SKILL.md has no opening '---' frontmatter delimiter")

    lines = content.split("\n")
    # Locate the closing '---' on its own line (not a substring inside a value).
    close_start = None  # char offset of the start of the closing '---' line
    offset = len(lines[0]) + 1  # start of lines[1]
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            close_start = offset
            break
        offset += len(lines[i]) + 1
    if close_start is None:
        raise ValueError("SKILL.md has no closing '---' frontmatter delimiter")

    head = content[:4]  # "---\n"
    fm_block = content[4:close_start]
    tail = content[close_start:]  # closing '---' onward (body preserved verbatim)

    out_lines = []
    old_value = None
    matched = False
    for line in fm_block.split("\n"):
        # Anchor on an exact top-level `name` key (no leading indent) so
        # `renamed:` or a nested `  name:` under `metadata:` is never touched.
        m = re.match(r"^(name)(\s*:\s*)(.*)$", line)
        if m and not matched:
            raw = m.group(3).strip()
            quote = ""
            if len(raw) >= 2 and raw[0] in "'\"" and raw[-1] == raw[0]:
                quote = raw[0]
                old_value = raw[1:-1]
            else:
                old_value = raw
            out_lines.append(f"{m.group(1)}{m.group(2)}{quote}{new_name}{quote}")
            matched = True
        else:
            out_lines.append(line)

    return head + "\n".join(out_lines) + tail, old_value, matched


def rewrite_json_field(content: str, field: str, new_name: str):
    """JSON round-trip: set `field` = new_name, re-emit with indent=2.

    Returns (new_content, old_value, matched). Raises ValueError on invalid JSON.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON root is not an object")
    matched = field in data
    old_value = data.get(field)
    data[field] = new_name
    return json.dumps(data, indent=2) + "\n", old_value, matched


def _rewrite_root_path(path: str, old_name: str, new_name: str) -> str:
    """Swap the trailing `{old}/` segment of a skill root for `{new}/`.

    Legacy nested draft form `{prefix}{old}/active/{old}/` flattens to
    `{prefix}{new}/`. A prefix that merely contains old_name is preserved.
    Returns the path unchanged when it does not end in the old-name segment.
    """
    legacy = f"{old_name}/active/{old_name}/"
    normal = f"{old_name}/"
    if path.endswith(legacy):
        return path[: -len(legacy)] + f"{new_name}/"
    if path.endswith(normal):
        return path[: -len(normal)] + f"{new_name}/"
    return path


def rewrite_context_snippet(content: str, old_name: str, new_name: str):
    """Rewrite the display header and every `root:` path in a context snippet.

    Returns (new_content, details) where details records what changed. Never
    raises — a snippet missing the header or a root just yields no change there.
    """
    details = {"header_rewritten": False, "roots": []}

    # Display header: [<old> v<version>] -> [<new> v<version>], suffix preserved.
    header_re = re.compile(r"\[" + re.escape(old_name) + r"(\s+v[^\]]*)\]")

    def _header_sub(m):
        details["header_rewritten"] = True
        return "[" + new_name + m.group(1) + "]"

    content = header_re.sub(_header_sub, content)

    # root: <path> — path is a non-whitespace token.
    root_re = re.compile(r"(root:\s*)(\S+)")

    def _root_sub(m):
        prefix, path = m.group(1), m.group(2)
        new_path = _rewrite_root_path(path, old_name, new_name)
        if new_path != path:
            details["roots"].append({"old": path, "new": new_path})
        return prefix + new_path

    content = root_re.sub(_root_sub, content)
    return content, details


# --- CLI orchestration --------------------------------------------------------


def process(target: Path, kind: str, old_name: str, new_name: str, dry_run: bool) -> dict:
    original = target.read_text(encoding="utf-8")

    result = {
        "status": "ok",
        "kind": kind,
        "target": str(target),
        "old_name": old_name,
        "new_name": new_name,
    }

    if kind == "skill-frontmatter":
        new_content, old_value, matched = rewrite_frontmatter_name(original, new_name)
        result["field"] = "name"
        result["matched"] = matched
        result["old_value"] = old_value
    elif kind == "metadata-json":
        new_content, old_value, matched = rewrite_json_field(original, "name", new_name)
        result["field"] = "name"
        result["matched"] = matched
        result["old_value"] = old_value
    elif kind == "provenance-json":
        new_content, old_value, matched = rewrite_json_field(original, "skill_name", new_name)
        result["field"] = "skill_name"
        result["matched"] = matched
        result["old_value"] = old_value
    elif kind == "context-snippet":
        new_content, details = rewrite_context_snippet(original, old_name, new_name)
        result["header_rewritten"] = details["header_rewritten"]
        result["roots_rewritten"] = details["roots"]
        result["matched"] = details["header_rewritten"] or bool(details["roots"])
    else:  # pragma: no cover - argparse choices guard this
        raise ValueError(f"unknown kind: {kind}")

    changed = new_content != original
    result["changed"] = changed
    if dry_run:
        result["dry_run"] = True
        result["new_content"] = new_content
        return result

    if changed:
        result["bytes"] = atomic_write_text(target, new_content)
        result["wrote"] = str(target)
    else:
        result["wrote"] = None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", type=Path, help="File to rewrite (SKILL.md, metadata.json, ...)")
    parser.add_argument("--kind", required=True, choices=KINDS, help="File kind / transform to apply")
    parser.add_argument("--old-name", required=True, help="Current skill name")
    parser.add_argument("--new-name", required=True, help="New skill name (kebab-case)")
    parser.add_argument("--dry-run", action="store_true", help="Compute without writing; emit new_content")
    parser.add_argument("--verbose", action="store_true", help="Diagnostics to stderr")
    args = parser.parse_args()

    if not args.old_name:
        _die(1, "old-name must be non-empty")
    if not NAME_RE.match(args.new_name) or len(args.new_name) > 64:
        _die(1, f"new-name must be kebab-case, 1-64 chars, got: {args.new_name!r}")

    if not args.target.exists():
        _die(1, f"target not found: {args.target}")

    try:
        result = process(args.target, args.kind, args.old_name, args.new_name, args.dry_run)
    except ValueError as e:
        _die(2, f"{args.kind} transform failed for {args.target}: {e}")
    except OSError as e:
        _die(2, f"atomic write failed for {args.target}: {e}")

    if args.verbose:
        print(f"[skf-rewrite-skill-name] {args.kind} changed={result['changed']}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
