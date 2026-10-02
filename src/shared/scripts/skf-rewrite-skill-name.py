#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Rewrite Skill Name — field-scoped, meaning-independent rename transforms.

Performs the deterministic in-file name substitutions the rename workflow needs,
so the LLM never hand-edits JSON or eyeballs "only within the frontmatter". Each
transform is scoped to a single field / region (for the context snippet, the
places its template writes the name) and applied by exact-key, anchored-pattern
or name-token match, then written atomically (stage to <target>.skf-tmp, fsync,
rename) in the same call — a process kill mid-rewrite leaves the original file
intact.

Four file kinds (one per --kind), each editing only the skill's name:

  skill-frontmatter  Replace the top-level `name:` value inside the YAML
                     frontmatter block ONLY (between the leading `---` and the
                     first `---` on its own line). Body text is never touched,
                     so a legitimate mention of the old name below the closing
                     `---` survives. Anchored on `^name:` so a longer key like
                     `renamed:` or a nested `  name:` is not matched.

  metadata-json      JSON round-trip: parse, set `name` = <new-name>, re-emit
                     with indent=2. Key order is preserved (dict insertion
                     order); no manual string surgery, so no risk of reordering
                     or dropping keys. With --moved-folder FOLDER (repeatable),
                     every string value that is a path into FOLDER/<old>/ is
                     pointed at FOLDER/<new>/, and the package folder
                     FOLDER/<old>/<version>/<old>/ at FOLDER/<new>/<version>/<new>/:
                     the rename moves those folders, and skf-verify-no-trace.py
                     counts the old name in such a path as a leftover. A path
                     counts only where it begins, at the start of the value or
                     of a word in it, spelled as FOLDER itself or as its last
                     components (a path from the project root, such as
                     forge-data/<old>/...); the old name must be a whole path
                     segment there, by the verifier's token rule. So a URL, a
                     path into another folder and a path that only holds
                     FOLDER's name further in stay. The values of the keys that
                     name the upstream source or a file in it (UPSTREAM_KEYS:
                     the verifier's SOURCE_FACT_KEYS, `source_file` and
                     `co_import_files`) never change, even when one holds such
                     a path: the rename does not move the source. Keys, every
                     other value and file names (`test-report-<old>.md`) stay.

  provenance-json    Same JSON round-trip, but the field is `skill_name`; takes
                     --moved-folder the same way.

  context-snippet    Rewrite the name where every SKF snippet template writes
                     it, so a snippet that follows a template leaves nothing
                     for skf-verify-no-trace.py, which counts any mention there
                     as a leftover: the display header `[<old> v...]`, the first
                     word of the `|IMPORTANT:` line and its `writing <old> code`
                     phrase. In those slots a complete skill-name token of the
                     old name becomes the new name, matched by the verifier's
                     own rule (_name_token_re, a pinned copy). Nothing else in
                     the snippet changes: a field label (`root:`, `|api:`), a
                     fixed word of the template ("training data", "SKILL.md")
                     or the library's own content that is the old name stays,
                     and the verifier then stops the rename rather than let it
                     commit a changed snippet. Each `root:` path parses as
                     `root: {prefix}{old}/`: the prefix is kept verbatim and
                     the trailing `{old}/` segment becomes
                     `{new}/`, so any IDE prefix (.claude/skills/,
                     .windsurf/skills/, draft skills/, ...) is handled without
                     enumeration and a prefix that contains the old name is
                     never changed. The legacy nested draft form
                     `root: skills/{old}/active/{old}/` is flattened to
                     `root: skills/{new}/`.

Batch mode (--skill-group, no target): the rename workflow's whole in-place
pass over a copied skill folder in one call, as execute.md section 2 runs it.
For each version in --versions, in the order given, it moves the package
folder <skill-group>/<version>/<old>/ to <skill-group>/<version>/<new>/; a
version without that folder (a manifest version with no folder, or a version
folder an interrupted run left without a package) is skipped and named in
`package_warnings`. Then it rewrites, for each version it moved, the
package's SKILL.md (skill-frontmatter), metadata.json (metadata-json) and
context-snippet.md (context-snippet) and, with --forge-group, every
version's <forge-group>/<version>/provenance-map.json (provenance-json),
package or not, each as the single-file mode does; --moved-folder applies to
the two JSON kinds. A file that is not there is listed in `missing_files`,
never a failure. The first move or rewrite that fails stops the batch:
`status` is "error" and `error` names its `stage` ("inner-rename" or
"rewrite"), `path` and `message`; the caller rolls the copied folders back.

The batch prints one JSON object on stdout, and writes it to --result-to
FILE too (atomically), the record the rename's report reads back:

  {"status": "ok"|"error", "old_name", "new_name", "skill_group",
   "forge_group": str|null, "renamed_versions": [...],
   "files_rewritten": [{"kind", "path"}],
   "counts": {"skill-frontmatter": n, "metadata-json": n,
              "context-snippet": n, "provenance-json": n},
   "package_warnings": [...], "missing_files": [...],
   "error": null | {"stage", "path", "message"}}

`counts` tallies files_rewritten by kind. A --result-to file that cannot be
written fails a batch that had not failed yet: `error.stage` is "record",
with that file as its `path`, so the caller rolls back as for a rewrite.

Exit codes:
  0  success (file processed, written iff content changed; or batch done)
  1  user error (bad args, --moved-folder with a kind other than the two JSON
     kinds, invalid new name, target not found)
  2  operation failure (unparseable structure, atomic write failed, or a
     batch move, rewrite or --result-to write that failed)

CLI examples:
  python3 skf-rewrite-skill-name.py SKILL.md \
      --kind skill-frontmatter --old-name rename --new-name rename-skill
  python3 skf-rewrite-skill-name.py context-snippet.md \
      --kind context-snippet --old-name rename --new-name rename-skill --dry-run
  python3 skf-rewrite-skill-name.py forge-data/rename/1.0.0/provenance-map.json \
      --kind provenance-json --old-name rename --new-name rename-skill \
      --moved-folder /project/skills --moved-folder /project/forge-data
  python3 skf-rewrite-skill-name.py --skill-group /project/skills/rename-skill \
      --versions 1.0.0,0.9.0 --old-name rename --new-name rename-skill \
      --moved-folder /project/skills --result-to run/rename-rewrite.json
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
JSON_KINDS = ("metadata-json", "provenance-json")


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


# Keep identical to _name_token_re in skf-verify-no-trace.py
# (test/test-skf-rewrite-skill-name.py pins the copies).
def _name_token_re(old_name: str) -> "re.Pattern[str]":
    """Match old_name only where it is a complete skill-name token.

    Negative lookbehind/lookahead on `[a-z0-9-]` so `rename` matches inside
    `/rename/` or `"rename"` but not inside `rename-skill` or `renamed`.
    """
    return re.compile(r"(?<![a-z0-9-])" + re.escape(old_name) + r"(?![a-z0-9-])")


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


# The places every SKF snippet template writes the skill's name, besides the
# root path: the display header `[<name> v...]`, and on the `|IMPORTANT:` line
# its first word and the `writing <name> code` phrase. The rest of a snippet is
# the template's fixed words and field labels (`root:`, `|api:`, "training
# data", "SKILL.md") or the library's own content, which a rename must not touch.
_HEADER_SLOT_RE = re.compile(r"\[(?P<slot>[^\]\s]+)(?=\s+v[^\]]*\])")
_IMPORTANT_LINE_RE = re.compile(r"^\|IMPORTANT:[^\n]*", re.M)
_IMPORTANT_SLOT_RES = (
    re.compile(r"^\|IMPORTANT:[ \t]*(?P<slot>\S+)"),
    re.compile(r"\bwriting[ \t]+(?P<slot>\S+?)[ \t]+code\b"),
)
_ROOT_PATH_RE = re.compile(r"root:\s*(?P<path>\S+)")


def rewrite_context_snippet(content: str, old_name: str, new_name: str):
    """Rewrite the name where SKF's snippet templates write it.

    skf-verify-no-trace.py counts any complete-token mention of the old name in
    context-snippet.md as a leftover, and every SKF snippet template writes the
    name in its display header, on its `|IMPORTANT:` line (first word, and
    `writing <name> code`) and in its `root:` path. In the header and the
    IMPORTANT-line slots every token _name_token_re matches (the verifier's
    rule) becomes new_name. Each `root:` path goes through _rewrite_root_path,
    which keeps its prefix (the IDE's skill folder) and swaps only the trailing
    `{old}/` segment.

    Nothing else changes: a field label, a fixed word of the template or the
    library's content that happens to be the old name stays, and the verifier
    then stops the rename (it rolls back with the old skill intact) instead of
    committing a changed snippet.

    Returns (new_content, details): `header_rewritten` (a `[<old> v...]` header
    was present), `roots` (each root path changed) and `mentions` (how many
    tokens were rewritten in the header and IMPORTANT-line slots). Never
    raises: a snippet with no mention just yields no change.
    """
    details = {"header_rewritten": False, "roots": [], "mentions": 0}
    token_re = _name_token_re(old_name)

    # (start, end, kind) of each slot. Root paths are rewritten as paths.
    spans = [(m.start("slot"), m.end("slot"), "header") for m in _HEADER_SLOT_RE.finditer(content)]
    for line in _IMPORTANT_LINE_RE.finditer(content):
        for slot_re in _IMPORTANT_SLOT_RES:
            for m in slot_re.finditer(line.group(0)):
                spans.append((line.start() + m.start("slot"), line.start() + m.end("slot"), "important"))
    spans += [(m.start("path"), m.end("path"), "root") for m in _ROOT_PATH_RE.finditer(content)]

    out = []
    pos = 0
    for start, end, kind in sorted(set(spans)):
        if start < pos:  # inside a slot already rewritten
            continue
        out.append(content[pos:start])
        text = content[start:end]
        if kind == "root":
            new_text = _rewrite_root_path(text, old_name, new_name)
            if new_text != text:
                details["roots"].append({"old": text, "new": new_text})
        else:
            new_text, count = token_re.subn(new_name, text)
            details["mentions"] += count
            if count and kind == "header":
                details["header_rewritten"] = True
        out.append(new_text)
        pos = end
    out.append(content[pos:])
    return "".join(out), details


# Keep identical to SOURCE_FACT_KEYS in skf-verify-no-trace.py
# (test/test-skf-rewrite-skill-name.py pins the copies). The keys whose value
# names the upstream source the skill was made from, not the skill.
SOURCE_FACT_KEYS = frozenset({
    "source_repo",
    "source_root",
    "source_commit",
    "source_ref",
    "source_package",
    "source_library",
})

# The values rewrite_moved_paths never changes: the upstream source, and the
# files in it (`source_file` of an export, script, asset or promoted doc, and
# the `co_import_files` of a stack integration). The rename moves the skill's
# folders, not the source, so a path such as `skills/<old>/x.py` there is the
# source's own layout; skf-verify-no-trace.py then reports a `source_file`
# that names the old name instead of the rename rewriting it.
UPSTREAM_KEYS = SOURCE_FACT_KEYS | {"source_file", "co_import_files"}

# A path begins at the start of a value or of a word in it: never inside a URL
# or after another folder of a longer path.
_PATH_START = r"(?<![^\s\"'`(\[<=,;])"


def _moved_path_re(folder: str, old_name: str) -> "re.Pattern[str]":
    """`<folder>/<old>` where a path begins, and the package folder in it.

    `folder` is a folder the rename moves `<old>` out of
    (`{skills_output_folder}` or `{forge_data_folder}`), as given. The path
    must begin with it, spelled in full or as its last components (so a value
    relative to the project root, `forge-data/<old>/...` or
    `_bmad-output/skills/<old>/...`, matches as well as an absolute one), at the
    start of the value or of a word in it, optionally after `./`. Either
    separator matches. The old name is matched by the verifier's token rule and
    must also end its path segment, so `forge-data/<old>/<v>/test-report-<old>.md`
    matches only at the folder. A following `/<version>/<old>` is the package
    folder the rename also moves (`{skill_group}/{version}/{skill-name}/`).
    """
    parts = re.split(r"[/\\]", folder.rstrip("/\\"))
    sep = r"[/\\]"
    spellings = dict.fromkeys(sep.join(re.escape(p) for p in parts[k:]) for k in range(len(parts)))
    heads = "|".join(sorted((s for s in spellings if s), key=len, reverse=True))
    name = _name_token_re(old_name).pattern
    seg_end = r"(?![A-Za-z0-9._-])"
    return re.compile(
        _PATH_START + r"(?P<head>(?:\.[/\\])?(?:" + heads + r")[/\\])" + name + seg_end
        + r"(?:(?P<mid>[/\\][^/\\\s]+[/\\])" + name + seg_end + r")?"
    )


def rewrite_moved_paths(content: str, old_name: str, new_name: str, folders):
    """Point every JSON string value that is a path into a moved folder at the new name.

    The rename moves `<folder>/<old>/` to `<folder>/<new>/` for each of
    `folders` (and the package folder `<old>/<version>/<old>/` inside the skill
    folder), so a value such as a test report's
    `forge-data/<old>/<v>/test-report-<old>.md` would name a folder that no
    longer exists, and the verifier would count it as a leftover. A path counts
    where it begins (see _moved_path_re). The values of UPSTREAM_KEYS, at any
    depth, keys and every other value stay; a file named after the skill keeps
    its name, as the rename keeps the file's name. Returns (new_content, paths)
    where paths lists each changed value as {"old", "new"}. Raises ValueError on
    invalid JSON.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    patterns = [_moved_path_re(f, old_name) for f in dict.fromkeys(folders) if _folder_name(f)]
    paths = []

    def _sub(m):
        return m.group("head") + new_name + ((m.group("mid") + new_name) if m.group("mid") else "")

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key not in UPSTREAM_KEYS:
                    node[key] = _walk(value)
        elif isinstance(node, list):
            node[:] = [_walk(value) for value in node]
        elif isinstance(node, str):
            new_value = node
            for pattern in patterns:
                new_value = pattern.sub(_sub, new_value)
            if new_value != node:
                paths.append({"old": node, "new": new_value})
            return new_value
        return node

    data = _walk(data)
    if not paths:
        return content, paths
    return json.dumps(data, indent=2) + "\n", paths


# --- Batch: every version of a copied skill folder in one call ----------------

# The package files each moved version rewrites, in order, then the forge file
# every version rewrites when the forge folder moves.
PACKAGE_FILES = (
    ("skill-frontmatter", "SKILL.md"),
    ("metadata-json", "metadata.json"),
    ("context-snippet", "context-snippet.md"),
)
FORGE_FILE = ("provenance-json", "provenance-map.json")


def _plain_segment(value: str) -> bool:
    """True for a version or a name that is one folder name and nothing else."""
    return value not in ("", ".", "..") and not any(c in value for c in "/\\:\0")


def run_batch(skill_group: Path, versions, old_name: str, new_name: str,
              forge_group: Path | None = None, moved_folders=()) -> dict:
    """Move each version's package to the new name, then rewrite its files.

    See "Batch mode" in the module docstring. Never raises on a file it
    processes: a failure ends the batch with `status` "error".
    """
    result = {
        "status": "ok",
        "old_name": old_name,
        "new_name": new_name,
        "skill_group": str(skill_group),
        "forge_group": str(forge_group) if forge_group is not None else None,
        "renamed_versions": [],
        "files_rewritten": [],
        "counts": {kind: 0 for kind in KINDS},
        "package_warnings": [],
        "missing_files": [],
        "error": None,
    }

    def fail(stage: str, path: Path, message: str) -> dict:
        result["status"] = "error"
        result["error"] = {"stage": stage, "path": str(path), "message": message}
        return result

    for version in versions:
        source = skill_group / version / old_name
        target = skill_group / version / new_name
        if not source.is_dir():
            result["package_warnings"].append(
                f"{version}: no {old_name}/ package in {skill_group / version}; skipped")
            continue
        if os.path.lexists(target):
            return fail("inner-rename", target, "the new package folder already exists")
        try:
            os.rename(source, target)
        except OSError as e:
            return fail("inner-rename", source, str(e))
        result["renamed_versions"].append(version)

    for version in versions:
        files = []
        if version in result["renamed_versions"]:
            files += [(kind, skill_group / version / new_name / name) for kind, name in PACKAGE_FILES]
        if forge_group is not None:
            files.append((FORGE_FILE[0], forge_group / version / FORGE_FILE[1]))
        for kind, path in files:
            if not path.is_file():
                result["missing_files"].append(str(path))
                continue
            moved = moved_folders if kind in JSON_KINDS else ()
            try:
                done = process(path, kind, old_name, new_name, False, moved)
            except ValueError as e:
                return fail("rewrite", path, f"{kind} transform failed: {e}")
            except OSError as e:
                return fail("rewrite", path, f"atomic write failed: {e}")
            if done["wrote"] is not None:
                result["files_rewritten"].append({"kind": kind, "path": done["wrote"]})
                result["counts"][kind] += 1
    return result


def _main_batch(args) -> None:
    if not _plain_segment(args.old_name):
        _die(1, f"--old-name must be one folder name, got: {args.old_name!r}")
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    bad = [v for v in versions if not _plain_segment(v)]
    if bad:
        _die(1, f"--versions must name version folders, got: {bad!r}")
    if not args.skill_group.is_dir():
        _die(1, f"skill group not found: {args.skill_group}")
    result = run_batch(args.skill_group, versions, args.old_name, args.new_name,
                       args.forge_group, args.moved_folder)
    if args.result_to is not None:
        try:
            atomic_write_text(args.result_to, json.dumps(result, indent=2) + "\n")
        except OSError as e:
            if result["error"] is None:
                result["status"] = "error"
                result["error"] = {"stage": "record", "path": str(args.result_to), "message": f"cannot write it: {e}"}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 2)


# --- CLI orchestration --------------------------------------------------------


def _folder_name(folder: str) -> str:
    """The last component of a folder path, whatever its separators."""
    return re.split(r"[/\\]", folder.rstrip("/\\"))[-1]


def process(target: Path, kind: str, old_name: str, new_name: str, dry_run: bool,
            moved_folders=()) -> dict:
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
        result["mentions_rewritten"] = details["mentions"]
        result["matched"] = details["mentions"] > 0 or bool(details["roots"])
    else:  # pragma: no cover - argparse choices guard this
        raise ValueError(f"unknown kind: {kind}")

    if kind in JSON_KINDS:
        new_content, paths = rewrite_moved_paths(
            new_content, old_name, new_name, list(moved_folders))
        result["paths_rewritten"] = paths

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", type=Path, nargs="?",
                        help="File to rewrite (SKILL.md, metadata.json, ...); leave out with --skill-group")
    parser.add_argument("--kind", choices=KINDS, help="File kind / transform to apply (single-file mode)")
    parser.add_argument("--old-name", required=True, help="Current skill name")
    parser.add_argument("--new-name", required=True, help="New skill name (kebab-case)")
    parser.add_argument(
        "--moved-folder", action="append", default=[], metavar="FOLDER",
        help="metadata-json / provenance-json only, repeatable: a folder the rename moves <old>/ "
             "to <new>/ in ({skills_output_folder}, and {forge_data_folder} when the forge folder "
             "moves); path values into FOLDER/<old>/ are pointed at FOLDER/<new>/")
    parser.add_argument("--dry-run", action="store_true", help="Compute without writing; emit new_content")
    parser.add_argument("--verbose", action="store_true", help="Diagnostics to stderr")
    batch = parser.add_argument_group("batch mode (see the module docstring)")
    batch.add_argument("--skill-group", type=Path, metavar="FOLDER",
                       help="the copied skill folder whose versions to rename, in place of a target")
    batch.add_argument("--versions", metavar="V1,V2",
                       help="batch: the comma-separated version folders to rename (required with --skill-group)")
    batch.add_argument("--forge-group", type=Path, metavar="FOLDER",
                       help="batch: the copied forge folder whose provenance maps to rewrite")
    batch.add_argument("--result-to", type=Path, metavar="FILE",
                       help="batch: also write the result JSON to FILE")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.old_name:
        _die(1, "old-name must be non-empty")
    if not NAME_RE.match(args.new_name) or len(args.new_name) > 64:
        _die(1, f"new-name must be kebab-case, 1-64 chars, got: {args.new_name!r}")
    if any(not _folder_name(f) for f in args.moved_folder):
        _die(1, f"--moved-folder must name a folder, got: {args.moved_folder!r}")

    batch_only = {"--versions": args.versions, "--forge-group": args.forge_group, "--result-to": args.result_to}
    if args.skill_group is not None:
        if args.target is not None or args.kind is not None or args.dry_run:
            _die(1, "--skill-group takes no target, --kind or --dry-run")
        if args.versions is None:
            _die(1, "--skill-group needs --versions")
        _main_batch(args)
    given = [flag for flag, value in batch_only.items() if value is not None]
    if given:
        _die(1, f"{', '.join(given)} {'needs' if len(given) == 1 else 'need'} --skill-group")
    if args.target is None or args.kind is None:
        _die(1, "pass a target file and --kind, or --skill-group for the batch")

    if args.moved_folder and args.kind not in JSON_KINDS:
        _die(1, f"--moved-folder applies to {' and '.join(JSON_KINDS)} only, not {args.kind}")

    if not args.target.exists():
        _die(1, f"target not found: {args.target}")

    try:
        result = process(args.target, args.kind, args.old_name, args.new_name, args.dry_run,
                         args.moved_folder)
    except ValueError as e:
        _die(2, f"{args.kind} transform failed for {args.target}: {e}")
    except OSError as e:
        _die(2, f"atomic write failed for {args.target}: {e}")

    if args.verbose:
        print(f"[skf-rewrite-skill-name] {args.kind} changed={result['changed']}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    sys.exit(0)


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    the --help text or a path may hold.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    main()
