# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Classify Changed Files: update-skill's file-level changes (Category A) in one call.

skf-update-skill's detect-changes step sorts the source's files into
MODIFIED, ADDED and DELETED against the provenance map and the brief's
scope, before Category B compares the exports of the MODIFIED files. Done
by hand, that is glob matching (`**`, an exclude that overrides an include)
and set arithmetic in the prompt, where one missed match silently drops a
new in-scope file and its exports are never extracted. This helper does it
in one call, with the tested `glob_match` of
skf-resolve-authoritative-files.py.

Subcommand:
  classify --source-root <path> [--provenance-map <provenance-map.json>]
           [--brief <skill-brief.yaml>] [--language <language>]...
           [--tree-status <status>] [--diff-status <status>]
           [--changed-files <changed-files.json>] [--exclude <path>]...
           [--lists-dir <dir>]

  --tree-status, --diff-status and --changed-files take the values the
  update-skill init step bound from skf-source-tree.py (`status`,
  `diff_status`, `changed_files`); an empty, `null` or `none` value counts
  as not given. --exclude (repeatable) names a path to leave out entirely:
  the change-detection excludes, such as a document the authoritative-files
  mirror just promoted. Without --brief (a skill built without one, such
  as a quick skill) the scope is empty. --language (repeatable) is the
  skill's language, metadata.json `language`. Without --provenance-map
  (update-skill's degraded mode) the mode is `full`.

  --lists-dir writes two JSON arrays of paths into that folder for the
  steps that read the files next: modified-files.json (category_a's
  modified files, the ones whose exports are diffed) and extract-files.json
  (the modified and added files and each moved file's new path, whose
  current exports are extracted).

The files it sorts:
  tracked   a file a provenance-map `entries[].source_file` names
  named     a tracked file, or one a `file_entries[].source_file` names
            (a script, an asset or a promoted document: those are
            Category D's, never ADDED here)
  in scope  a `scope.include` glob matches it and no `scope.exclude` glob
            does. With an empty `scope.include`, a file whose extension one
            of the tracked files has, or --language's language uses, and
            that no `scope.exclude` glob matches.
  promoted  a file a promoted glob matches: the path of a
            `scope.amendments[]` entry whose latest action is `promoted`
            with category `scope-expansion`, when no tracked file matches
            that glob yet (the scope reconciliation promoted it, and its
            files were never extracted)
  Globs follow the brief's semantics: `**` spans any number of folders,
  `*` and `?` never cross a `/`. Walking the source skips symbolic links
  and generated or vendored folders (node_modules, dist, build, .git, ...),
  and an unnamed file in one of them is never ADDED. An --exclude path is
  in no list.

Modes, from the statuses:
  diff  --diff-status ok (or --changed-files alone): the changed-files.json
        skf-source-tree.py wrote, git's list of the files changed since the
        skill's commit, {"base", "target", "files": [{"status": "A"|"M"|"D",
        "path"}]}. A checkout rewrites every timestamp, so only this list
        says what changed.
          MODIFIED  a tracked file with an M or A row
          DELETED   a tracked file with a D row, or one the source lacks
          ADDED     an unnamed, in-scope file with an A or M row (a file
                    that exported nothing when the map was built can gain
                    an export), or a promoted file, changed or not
          MOVED     a DELETED file with a D row and an ADDED file with an A
                    row holding the same contents (one git blob at base and
                    at target, each matched once): listed in moved_files,
                    and in neither added nor deleted
  tree-without-diff  --tree-status ready or offline, the diff unavailable:
        the skill's commit could not be read, so
          MODIFIED  every tracked file the source holds
          DELETED   a tracked file the source lacks
          ADDED     every unnamed, in-scope file
        with a `file-diff-unavailable` warning.
  local  anything else (a local source, read as it stands): a walk that
        compares each file's modification time with the provenance map's
        time, the later of its `generated_at` and, when its top-level
        `update_type` is `incremental` or `full` (an update that read the
        source), its top-level `last_update`. A time with a zone is that
        instant. A date alone (update-skill wrote `last_update` as a date
        before v3.0.0) or a time without a zone is the earliest instant it
        can name, 14 hours before its UTC reading (the day starts first at
        UTC+14): a baseline too early only re-checks a few files, while
        one too late would miss a file edited after the update.
          MODIFIED  a tracked file modified at or after that time
          DELETED   a tracked file the source lacks
          ADDED     an unnamed, in-scope file modified at or after that
                    time, or a promoted file
        With no usable time every tracked file the source holds is
        MODIFIED and every unnamed, in-scope file ADDED, with a
        `no-baseline-time` warning. No MOVED: a deleted file's contents
        are gone.
  full  no --provenance-map: with no map to compare against, every
        in-scope file the walk finds is MODIFIED, and none is ADDED,
        DELETED or MOVED. A run with nothing to scope the walk by (no
        `scope.include` glob and no --language this helper knows) is an
        input error rather than an empty list.

An unknown --language value adds an `unknown-language` warning.

Output JSON (stdout):

  {
    "status": "ok",
    "mode": "diff" | "tree-without-diff" | "local" | "full",
    "category_a": {"modified": [...], "added": [...], "deleted": [...]},
    "moved_files": [{"old_path": "...", "new_path": "..."}],
    "summary": {"tracked": N, "modified": N, "added": N, "deleted": N,
                "moved": N, "unchanged": N},
    "baseline_time": "<YYYY-MM-DDTHH:MM:SSZ>" | null,
    "baseline_source": "last_update" | "generated_at" | null,
    "warnings": ["file-diff-unavailable: ..." | "no-baseline-time: ..." |
                 "moved-check-skipped: ..." | "unknown-language: ..."]
  }

category_a is the slice skf-build-change-manifest.py build reads, and each
moved_files item has the shape of its category_c.renamed_files items.
Paths are relative to the source root, with forward slashes, sorted.
baseline_time is the instant local mode compared the files with (a date
alone already moved to its earliest instant), and baseline_source the key
it came from; both are null outside local mode. summary
counts the tracked files the run read (an --exclude path is not one), and
unchanged is those neither MODIFIED, DELETED nor moved.

Exit codes:
  0  classified
  1  input error: a missing source root, provenance map, brief or
     changed-files file, one that cannot be parsed, --diff-status ok
     without --changed-files, a full mode with nothing to scope the walk
     by, or a --lists-dir it cannot write (message on stderr)
  2  usage error (argparse, usage on stderr)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

_TREE_STATUSES = ("ready", "offline")
# The update types that re-read the whole source (a normal update and a
# rebuild without a provenance map); a gap-driven repair reads no changes.
_SOURCE_READING_UPDATES = ("incremental", "full")
# The easternmost zone (UTC+14): a day there starts 14 hours before UTC's.
_EARLIEST_ZONE_OFFSET = timedelta(hours=14)
_GIT_TIMEOUT_SEC = 60.0
# --language (metadata.json `language`) -> the source file extensions a skill
# in that language reads: the recipe runner's language families
# (skf-extract-public-api.py EXTENSION_LANGUAGES) and the languages it has
# no recipe for, which are read by eye.
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue")
_C_EXTENSIONS = (".c", ".h")
_CPP_EXTENSIONS = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h")
LANGUAGE_EXTENSIONS = {
    **dict.fromkeys(("javascript", "js", "jsx", "typescript", "ts", "tsx", "vue"), _JS_EXTENSIONS),
    "python": (".py", ".pyi"),
    "rust": (".rs",),
    "go": (".go",),
    "golang": (".go",),
    "java": (".java",),
    "kotlin": (".kt", ".kts"),
    "swift": (".swift",),
    "csharp": (".cs",),
    "c#": (".cs",),
    "php": (".php",),
    "ruby": (".rb",),
    "c": _C_EXTENSIONS,
    "cpp": _CPP_EXTENSIONS,
    "c++": _CPP_EXTENSIONS,
}
_RESOLVER = None
_SOURCE_TREE = None


def _sibling(name: str, stem: str):
    path = Path(__file__).resolve().parent / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolver():
    """skf-resolve-authoritative-files.py from this folder, loaded once: the
    brief is read and matched with its load_brief, glob_match, scope_match,
    normalize_rel_path and EXCLUDED_DIR_NAMES."""
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = _sibling("skf_resolve_authoritative_files", "skf-resolve-authoritative-files")
    return _RESOLVER


def _source_tree():
    """skf-source-tree.py from this folder, loaded once: git runs through
    its runner (_run stops a call at the time limit; _resolve_outside_cwd
    never takes a git planted in the current folder)."""
    global _SOURCE_TREE
    if _SOURCE_TREE is None:
        _SOURCE_TREE = _sibling("skf_source_tree", "skf-source-tree")
    return _SOURCE_TREE


def _given(value: str | None) -> str:
    """value stripped; "" for an empty, `null` or `none` value."""
    value = (value or "").strip()
    return "" if value.lower() in ("null", "none") else value


def language_extensions(languages: list[str]) -> tuple[set[str], list[str]]:
    """(the extensions the --language values use, the values none is known for).

    An empty or `null` value is no language.

    >>> sorted(language_extensions(["Python", "null"])[0]), language_extensions(["cobol"])[1]
    (['.py', '.pyi'], ['cobol'])
    """
    extensions: set[str] = set()
    unknown = []
    for value in languages:
        if not _given(value):
            continue
        known = LANGUAGE_EXTENSIONS.get(_given(value).lower())
        if known is None:
            unknown.append(value)
        else:
            extensions.update(known)
    return extensions, unknown


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def _read_json(path: Path, what: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {what} at {path}: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"{what} at {path} is not valid JSON: {exc}") from exc


def _source_files(provenance: dict, key: str) -> set[str]:
    norm = _resolver().normalize_rel_path
    rows = provenance.get(key)
    if not isinstance(rows, list):
        return set()
    return {
        norm(row["source_file"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("source_file"), str) and row["source_file"].strip()
    }


def _parse_time(value: object) -> datetime | None:
    """An ISO-8601 date or date-time as a UTC instant, or None.

    A time with a zone is that instant. A date alone, or a time without a
    zone, was written in some zone as far east as UTC+14, so it is read as
    the earliest instant it can name: its UTC reading less 14 hours. A
    baseline too early only re-checks a few files; one too late would miss
    a file edited after the update.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
        if moment.tzinfo is None:
            return moment.replace(tzinfo=timezone.utc) - _EARLIEST_ZONE_OFFSET
        return moment.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def baseline_time(provenance: dict) -> tuple[datetime | None, str | None]:
    """(time, source) a local source's files are compared with: the later of
    generated_at and a source-reading update's last_update."""
    found = []
    generated = _parse_time(provenance.get("generated_at"))
    if generated is not None:
        found.append((generated, "generated_at"))
    if provenance.get("update_type") in _SOURCE_READING_UPDATES:
        updated = _parse_time(provenance.get("last_update"))
        if updated is not None:
            found.append((updated, "last_update"))
    if not found:
        return None, None
    return max(found, key=lambda item: item[0])


def promoted_globs(brief: dict, tracked: set[str]) -> list[str]:
    """The scope-expansion globs the latest amendment promoted and no tracked
    file matches yet."""
    resolver = _resolver()
    scope = brief.get("scope") if isinstance(brief.get("scope"), dict) else {}
    amendments = scope.get("amendments") if isinstance(scope.get("amendments"), list) else []
    latest: dict[str, dict] = {}
    for amend in amendments:
        if isinstance(amend, dict) and isinstance(amend.get("path"), str) and amend["path"].strip():
            latest[resolver.normalize_rel_path(amend["path"])] = amend
    return sorted(
        glob
        for glob, amend in latest.items()
        if amend.get("action") == "promoted"
        and amend.get("category") == "scope-expansion"
        and not any(resolver.glob_match(path, glob) for path in tracked)
    )


# --------------------------------------------------------------------------
# Walk and scope
# --------------------------------------------------------------------------


def _vendored(rel: str) -> bool:
    return any(part in _resolver().EXCLUDED_DIR_NAMES for part in rel.split("/")[:-1])


def walk_source(root: Path) -> list[tuple[str, Path]]:
    """(relative path, path) of every file under root, sorted: no symbolic
    link, and no generated or vendored folder."""
    excluded = _resolver().EXCLUDED_DIR_NAMES
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in excluded and not (here / d).is_symlink()]
        for name in filenames:
            path = here / name
            if path.is_symlink() or not path.is_file():
                continue
            found.append((path.relative_to(root).as_posix(), path))
    return sorted(found)


def _in_scope(rel: str, includes: list[str], excludes: list[str], extensions: set[str]) -> bool:
    resolver = _resolver()
    if includes:
        return resolver.scope_match(rel, includes, excludes)[0]
    if any(resolver.glob_match(rel, pattern) for pattern in excludes):
        return False
    return PurePosixPath(rel).suffix in extensions


# --------------------------------------------------------------------------
# Same-content moves (diff mode)
# --------------------------------------------------------------------------


def _blobs(tree: Path, commit: str, paths: set[str]) -> dict[str, str]:
    """{path: blob id} at commit for the given paths. Raises RuntimeError
    when git cannot list the commit."""
    try:
        runner = _source_tree()
    except (ImportError, OSError) as exc:
        raise RuntimeError(f"cannot load skf-source-tree.py: {exc}") from exc
    exe = runner._resolve_outside_cwd("git")
    if exe is None:
        raise RuntimeError("git is not installed")
    argv = [exe, "-c", f"core.hooksPath={os.devnull}", "-C", str(tree), "ls-tree", "-r", "-z", commit]
    try:
        rc, out, err, _killed = runner._run(argv, _GIT_TIMEOUT_SEC)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"git could not run: {exc}") from exc
    if rc is None:
        raise RuntimeError(f"git ls-tree timed out after {_GIT_TIMEOUT_SEC:g} seconds")
    if rc != 0:
        raise RuntimeError(runner._last_error(err.decode("utf-8", errors="replace")))
    blobs = {}
    for record in out.split(b"\0"):
        meta, _, raw_path = record.partition(b"\t")
        fields = meta.split()
        if len(fields) != 3 or fields[1] != b"blob":
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if path in paths:
            blobs[path] = fields[2].decode("ascii", errors="replace")
    return blobs


def same_content_moves(
    tree: Path, base: str, target: str, deleted: set[str], added: set[str]
) -> list[dict]:
    """{old_path, new_path} for each deleted file whose blob at base is the
    blob of exactly one added file at target, and no other deleted file's.
    Raises RuntimeError when git cannot list either commit."""
    if not deleted or not added:
        return []
    by_blob: dict[str, tuple[list[str], list[str]]] = {}
    for path, blob in _blobs(tree, base, deleted).items():
        by_blob.setdefault(blob, ([], []))[0].append(path)
    for path, blob in _blobs(tree, target, added).items():
        by_blob.setdefault(blob, ([], []))[1].append(path)
    return sorted(
        ({"old_path": old[0], "new_path": new[0]} for old, new in by_blob.values() if len(old) == 1 and len(new) == 1),
        key=lambda move: move["new_path"],
    )


# --------------------------------------------------------------------------
# Classify
# --------------------------------------------------------------------------


def _changed_rows(data: object, path: Path) -> tuple[dict[str, str], str, str]:
    """({path: status}, base, target) of a changed-files.json."""
    norm = _resolver().normalize_rel_path
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise ValueError(f"changed-files file at {path} has no files[] list")
    rows = {}
    for row in data["files"]:
        if isinstance(row, dict) and row.get("status") in ("A", "M", "D") and isinstance(row.get("path"), str):
            rows[norm(row["path"])] = row["status"]
    base, target = data.get("base"), data.get("target")
    return rows, base if isinstance(base, str) else "", target if isinstance(target, str) else ""


def classify(
    source_root: Path,
    provenance: dict | None,
    brief: dict,
    *,
    tree_status: str = "",
    diff_status: str = "",
    changed: object = None,
    changed_path: Path | None = None,
    excludes: list[str] | None = None,
    languages: list[str] | None = None,
) -> dict:
    """Run Category A. See the module docstring for the output shape.

    provenance is None in full mode, and brief {} for a skill without one.
    changed is the parsed changed-files.json in diff mode (None otherwise).
    Raises ValueError for a full mode with nothing to scope the walk by.
    """
    resolver = _resolver()
    norm = resolver.normalize_rel_path
    left_out = {norm(p) for p in excludes or [] if isinstance(p, str) and p.strip()}
    tracked = _source_files(provenance or {}, "entries") - left_out
    named = tracked | _source_files(provenance or {}, "file_entries")
    includes, scope_excludes, _ = resolver.extract_scope(brief)
    includes = [norm(p) for p in includes]
    scope_excludes = [norm(p) for p in scope_excludes]
    spoken, unknown_languages = language_extensions(languages or [])
    extensions = {PurePosixPath(p).suffix for p in tracked if PurePosixPath(p).suffix} | spoken
    promoted = promoted_globs(brief, tracked)

    def candidate(rel: str) -> bool:
        """An unnamed, in-scope file: ADDED when it changed, MODIFIED in full mode."""
        return (
            rel not in named
            and rel not in left_out
            and not _vendored(rel)
            and _in_scope(rel, includes, scope_excludes, extensions)
        )

    def is_promoted(rel: str) -> bool:
        return any(resolver.glob_match(rel, glob) for glob in promoted)

    def present(rel: str) -> bool:
        return (source_root / rel).is_file()

    warnings: list[str] = [
        f"unknown-language: no source file extension is known for {value!r}" for value in unknown_languages
    ]
    moved: list[dict] = []
    modified: set[str] = set()
    added: set[str] = set()
    deleted: set[str] = set()
    baseline, baseline_source = None, None

    if provenance is None:
        mode = "full"
        if not includes and not extensions:
            raise ValueError(
                "nothing scopes the walk without a provenance map: give a --brief whose scope.include "
                "names the source files, or the skill's --language"
            )
        modified.update(rel for rel, _ in walk_source(source_root) if candidate(rel))
    elif diff_status == "ok" or (not diff_status and changed is not None):
        mode = "diff"
        rows, base, target = _changed_rows(changed, changed_path or Path("changed-files.json"))
        for rel in tracked:
            status = rows.get(rel)
            if status == "D" or not present(rel):
                deleted.add(rel)
            elif status in ("A", "M"):
                modified.add(rel)
        for rel, status in rows.items():
            if status in ("A", "M") and candidate(rel) and present(rel):
                added.add(rel)
        if promoted:
            added.update(rel for rel, _ in walk_source(source_root) if candidate(rel) and is_promoted(rel))
        gone = {rel for rel in deleted if rows.get(rel) == "D"}
        new = {rel for rel in added if rows.get(rel) == "A"}
        if gone and new:
            try:
                if not (base and target):
                    raise RuntimeError("the changed-files list names no base or target commit")
                moved = same_content_moves(source_root, base, target, gone, new)
            except RuntimeError as exc:
                warnings.append(f"moved-check-skipped: {exc}")
        for move in moved:
            deleted.discard(move["old_path"])
            added.discard(move["new_path"])
    elif tree_status in _TREE_STATUSES:
        mode = "tree-without-diff"
        for rel in tracked:
            (modified if present(rel) else deleted).add(rel)
        added.update(rel for rel, _ in walk_source(source_root) if candidate(rel))
        commit = provenance.get("source_commit")
        commit = commit.strip() if isinstance(commit, str) and commit.strip() else "the skill's commit"
        warnings.append(
            f"file-diff-unavailable: {commit} could not be read, so every tracked file was re-checked"
        )
    else:
        mode = "local"
        baseline, baseline_source = baseline_time(provenance)
        since = baseline.timestamp() if baseline is not None else None

        def touched(path: Path) -> bool:
            if since is None:
                return True
            try:
                return path.stat().st_mtime >= since
            except OSError:
                return True

        for rel in tracked:
            path = source_root / rel
            if not path.is_file():
                deleted.add(rel)
            elif touched(path):
                modified.add(rel)
        added.update(
            rel for rel, path in walk_source(source_root)
            if candidate(rel) and (touched(path) or is_promoted(rel))
        )
        if baseline is None:
            warnings.append(
                "no-baseline-time: the provenance map records no usable generated_at or "
                "last_update, so every tracked file was re-checked and every in-scope file "
                "it does not name was listed as added"
            )

    unchanged = len(tracked - modified - deleted - {m["old_path"] for m in moved})
    return {
        "status": "ok",
        "mode": mode,
        "category_a": {
            "modified": sorted(modified),
            "added": sorted(added),
            "deleted": sorted(deleted),
        },
        "moved_files": moved,
        "summary": {
            "tracked": len(tracked),
            "modified": len(modified),
            "added": len(added),
            "deleted": len(deleted),
            "moved": len(moved),
            "unchanged": unchanged,
        },
        "baseline_time": baseline.strftime("%Y-%m-%dT%H:%M:%SZ") if baseline is not None else None,
        "baseline_source": baseline_source,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def write_lists(result: dict, folder: Path) -> None:
    """--lists-dir: modified-files.json and extract-files.json. Raises
    ValueError when a list cannot be written."""
    category_a = result["category_a"]
    extract = set(category_a["modified"]) | set(category_a["added"])
    extract.update(move["new_path"] for move in result["moved_files"])
    for name, paths in (("modified-files.json", category_a["modified"]), ("extract-files.json", sorted(extract))):
        try:
            (folder / name).write_text(json.dumps(paths, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot write {name} in {folder}: {exc}") from exc


def _cmd_classify(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    if not source_root.is_dir():
        print(f"error: source-root not a directory: {source_root}", file=sys.stderr)
        return 1
    for label, value in (("provenance map", args.provenance_map), ("brief", args.brief)):
        if value is not None and not Path(value).is_file():
            print(f"error: {label} not found: {value}", file=sys.stderr)
            return 1
    tree_status = _given(args.tree_status).lower()
    diff_status = _given(args.diff_status).lower()
    changed_files = _given(args.changed_files)
    if diff_status == "ok" and not changed_files and args.provenance_map is not None:
        print("error: --diff-status ok needs --changed-files", file=sys.stderr)
        return 1
    try:
        provenance = None
        if args.provenance_map is not None:
            provenance = _read_json(Path(args.provenance_map), "provenance map")
            if not isinstance(provenance, dict):
                raise ValueError(f"provenance map at {args.provenance_map} must be a JSON object")
        brief = _resolver().load_brief(Path(args.brief)) if args.brief is not None else {}
        changed = None
        if provenance is not None and changed_files and diff_status in ("ok", ""):
            changed = _read_json(Path(changed_files), "changed-files list")
        result = classify(
            source_root,
            provenance,
            brief,
            tree_status=tree_status,
            diff_status=diff_status,
            changed=changed,
            changed_path=Path(changed_files) if changed_files else None,
            excludes=args.exclude or [],
            languages=args.language or [],
        )
        if args.lists_dir is not None:
            write_lists(result, Path(args.lists_dir))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    # --help (and classify --help) print the module docstring: the modes,
    # their MODIFIED, ADDED and DELETED rules and the output a step cites.
    parser = argparse.ArgumentParser(
        prog="skf-classify-changed-files",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "classify",
        help="classify the file-level changes",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source-root", required=True, help="path to the source tree the run reads")
    p.add_argument("--provenance-map", help="path to provenance-map.json (none: full mode)")
    p.add_argument("--brief", help="path to skill-brief.yaml (none: an empty scope)")
    p.add_argument(
        "--language",
        action="append",
        metavar="LANG",
        help="the skill's language, whose extensions an empty scope.include takes (repeatable)",
    )
    p.add_argument("--tree-status", help="skf-source-tree.py status (ready, offline, ...)")
    p.add_argument("--diff-status", help="skf-source-tree.py diff_status (ok or unavailable)")
    p.add_argument("--changed-files", help="path to skf-source-tree.py's changed-files.json")
    p.add_argument(
        "--exclude",
        action="append",
        metavar="PATH",
        help="a path to leave out entirely (repeatable)",
    )
    p.add_argument(
        "--lists-dir",
        metavar="DIR",
        help="write modified-files.json and extract-files.json into this folder",
    )
    p.set_defaults(func=_cmd_classify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
