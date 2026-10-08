# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Extraction Snapshot: audit-skill's current export inventory, built by script.

audit-skill's step 2 (re-index.md) re-extracts the files the provenance map
covers and writes `extraction-snapshot.json`, which step 3 diffs against the
map. The recipe runner (skf-extract-public-api.py --mode full) does the
extraction; this helper gives it the files to read and turns its JSON, with
the exports the step read by eye, into the snapshot, so no step opens the
runner's JSON, copies hundreds of exports by hand or decides by eye whether
every file was read.

CLI:

  uv run skf-extraction-snapshot.py scan-list <provenance-map> -o <files.json>
  uv run skf-extraction-snapshot.py build --source-root <dir> --tier <tier> \\
      --date <timestamp> [--source-path <recorded root>] \\
      [--provenance-map <map>] [--extraction <runner.json>] \\
      [--details <by-eye.json>]... -o <extraction-snapshot.json>
  uv run skf-extraction-snapshot.py relocate <extraction-snapshot.json> \\
      --diff <structural-diff.json> --extraction <runner.json>

scan-list

  Writes the bounded scan list, the files the provenance map covers (the
  union of `entries[].source_file` and `file_entries[].source_file`, sorted,
  with forward slashes: skf-load-provenance.py's `bounded_scan_files`), as a
  JSON list of paths, the form the runner's --files-from reads. Prints
  {"status": "ok", "output": <file>, "files": N}.

build

  The files in scope are the bounded scan list with --provenance-map (every
  audit passes it), else every file the runner or the details name. Each
  gets one status, in this order of precedence:

    missing        not a file under --source-root
    hash-tracked   only `file_entries[]` names it (a script, an asset or a
                   promoted doc): step 3 compares its content hash, so
                   nothing reads it for exports
    read-by-eye    the details name it in `files` (the step read it)
    parse-failed   the runner listed it in `file_issues` (a syntax error,
                   not UTF-8, unreadable, or a language no recipe reads):
                   read it by eye
    unread         no runner result, a runner that could not run
                   (`no-ast-grep`), or an incomplete run that names it as
                   unread (`errors[].unread`) or found no export in it
    extracted      the runner read it

  `complete` is true when no file is `parse-failed` or `unread`: step 2
  reads those by eye, adds them to the details and builds again. A file
  carries `fallback: true` when the runner ran and left it `parse-failed`
  or `unread`: read by eye after an ast-grep failure.

  Exports: the runner's exports of the files in scope (each T1, with the
  declaration on one line as `signature`), then each export of the details
  (`name` or `export_name`, `file` or `source_file`, `line` or
  `source_line`, `type` or `export_type`, `signature`; T1-low and
  `source-read` unless it says otherwise). A details export with the name
  and file of a runner export fills only the fields that one lacks; any
  other is added. An export of a file outside the files in scope, or of a
  `hash-tracked` one (the map records no export there, so it would read
  as added), is left out, with a warning. With --provenance-map, each export of a file the
  map gives a library (`source_library_by_file`) carries it as
  `source_library`, which step 3's `--group-by source_library` diff reads.

  Details file: {"files": [paths read by eye], "exports": [export objects]}
  (either key may be absent). Give --details once per file: one per worker.

  Output (-o), the snapshot step 3 reads:

    {
      "extraction_date": "<--date>",
      "confidence_tier": "<--tier>",
      "source_root": "<--source-path, else --source-root>",
      "bounded_scan": true | false,
      "bounded_scan_source": "provenance-map" | "source-tree-fallback",
      "runner_status": "ok" | "incomplete" | "no-ast-grep" | null,
      "runner_errors": [the runner's errors[]],
      "files_scanned": N,
      "complete": bool,
      "files": [{"file", "status", "issue": <the runner's issue> | null,
                 "fallback": bool, "exports": N}, ...],
      "files_by_status": {"extracted": N, "read-by-eye": N,
                          "hash-tracked": N, "missing": N,
                          "parse-failed": N, "unread": N},
      "ast_fallback_files": ["<file>", ...],
      "extraction_gaps": [{"name", "file", "line", "entry",
                           "export_type"?}, ...],
      "truncated": bool,               # a recipe hit the runner's head cap
      "cap_hits": ["<recipe id>", ...],
      "outside_scope": [{"path": "<file>", "names": [...],
                         "entries": [...]}, ...],
      "counts": {"exports": N, "by_type": {"<type>": N, ...},
                 "t1": N, "t1_low": N},
      "exports": [{"name", "type", "signature", "file", "line",
                   "confidence", "extraction_method", "ast_node_type",
                   "source_library"?}, ...],
      "relocations": [{"name", "file", "line"}, ...],   # relocate's
      "warnings": ["..."]
    }

  `ast_fallback_files` names the files read after an ast-grep failure (the
  `fallback` ones) when the runner ran; when it did not, it is
  ["all files (ast-grep unavailable)"], and [] at the Quick tier.
  `extraction_gaps` lists the names a package entry point exports that no
  recipe found (the runner's `entry_point_diff.extraction_gaps`), less the
  ones an export of the snapshot now holds, then, with --provenance-map,
  the baseline gaps: each entry of the map the snapshot lacks whose file
  still declares it (the runner leaves out an underscore name such as
  `__version__`, and a module), which would otherwise read as removed. A
  baseline gap gives the line that declares the name, `entry` null and,
  when the entry has one, its `export_type`. It is checked only for an
  entry whose file is `extracted` or `read-by-eye`, whose name is not
  dotted, and that the snapshot holds neither under its name nor under
  its `reexported_as` target at that file. The selection and the
  declaration are skf-verify-provenance-completeness.py's (`baseline_gaps`,
  by `declared_line`), loaded from beside this script, the rule
  update-skill's Category B applies through skf-build-change-manifest.py
  baseline-gaps: a line at column 0 of a Python or TS/JS file that the
  definition-line rules match with imports left out (an alias that
  renames counts; a plain or star import and a re-export never do),
  and for a `module` or `package` entry the module or package so named
  (at its line 1). An entry no rule can check (its file neither Python
  nor TS/JS, a file the lookup does not read, such as a test file or one
  with a symlink on its path, or a dotted `module` or `package` name) is
  named in one warning, as `name (file)`. Each name and file is listed
  once, and each file is read once. Read them by eye.
  `outside_scope` groups the runner's `entry_point_diff.outside_scope` by
  the file that defines each name: public API a package entry point exports
  from a file the skill does not cover, which the drift report lists under
  Out-of-Scope New Public API for update-skill's scope reconciliation.

  Prints {"status": "ok", "output", "runner_status", "complete",
  "to_read": [{"file", "status", "issue"}, ...] (the `parse-failed` and
  `unread` files), "extraction_gaps", "ast_fallback_files",
  "files_by_status", "counts"} on stdout: what step 2 acts on, so it never
  opens the runner's JSON.

relocate

  Step 3's relocation check: --extraction is the runner's JSON over the
  files that hold a name the diff reports removed, outside the bounded scan
  list. Each export the runner found there under a name of the diff's
  `removed[]`, in a file outside the snapshot's files in scope, joins the
  snapshot's exports (T1, with the removed entry's `source_library` when it
  has one) and `relocations`; the counts are recounted and the snapshot is
  written back in place. Prints {"status": "ok", "output", "added": N,
  "names": [...]}; added 0 changes nothing.

Exit codes: 0 the file was written (or relocate found nothing to add); 2
an input that cannot be read or parsed, a helper beside this script that
cannot be loaded, or an output that cannot be written ({"status":
"error", "error"} on stdout), or a usage error (argparse, on stderr).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

STATUSES = ("extracted", "read-by-eye", "hash-tracked", "missing", "parse-failed", "unread")
TO_READ = ("parse-failed", "unread")
RUNNER_READ = frozenset({"ok", "incomplete"})
# The files whose provenance entries a baseline gap checks: the ones read.
BASELINE_GAP_STATUSES = ("extracted", "read-by-eye")
AST_GREP_UNAVAILABLE = "all files (ast-grep unavailable)"
EXIT_ERROR = 2


class SnapshotError(Exception):
    """An input or output the helper cannot use (exit 2)."""


_SIBLINGS: dict[str, object] = {}


def _sibling(filename: str, *needs: str):
    """A script installed beside this one, loaded once. Any failure to load
    it, or a script without each name `needs` lists, is a SnapshotError
    (exit 2)."""
    if filename not in _SIBLINGS:
        path = Path(__file__).resolve().parent / filename
        try:
            spec = importlib.util.spec_from_file_location(filename[:-3].replace("-", "_"), path)
            if spec is None or spec.loader is None:
                raise ImportError(f"no loader for {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # whatever the script raises, the build reports it
            raise SnapshotError(f"cannot load {filename} beside {Path(__file__).name}: {exc}") from exc
        missing = [need for need in needs if getattr(module, need, None) is None]
        if missing:
            raise SnapshotError(f"cannot load {filename} beside {Path(__file__).name}: "
                                f"it has no {', '.join(missing)}")
        _SIBLINGS[filename] = module
    return _SIBLINGS[filename]


def _provenance():
    """skf-load-provenance.py, for the scan list and the libraries (the
    verifier's `baseline_gaps` reads the re-export map itself)."""
    return _sibling("skf-load-provenance.py", "bounded_scan_files", "source_library_by_file")


def _verifier():
    """skf-verify-provenance-completeness.py, for its baseline gaps
    (`baseline_gaps`, by its declaration rule `declared_line`)."""
    return _sibling("skf-verify-provenance-completeness.py", "baseline_gaps", "declared_line")


def _posix(path: str) -> str:
    """A path as the scan list writes it: forward slashes, no leading `./`."""
    rel = path.strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _read_json(path: Path, what: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SnapshotError(f"cannot read {what} {path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, ValueError) as exc:
        raise SnapshotError(f"{what} {path} is not JSON: {exc}") from exc


def _read_object(path: Path, what: str) -> dict:
    data = _read_json(path, what)
    if not isinstance(data, dict):
        raise SnapshotError(f"{what} {path} must be a JSON object")
    return data


def _write(path: Path, data: object) -> None:
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise SnapshotError(f"cannot write {path}: {exc.strerror or exc}") from exc


def _first(entry: dict, *keys: str) -> object:
    for key in keys:
        if entry.get(key) is not None:
            return entry[key]
    return None


# --------------------------------------------------------------------------
# Building the snapshot
# --------------------------------------------------------------------------


def _runner_export(export: dict) -> dict:
    return {
        "name": export.get("export_name"),
        "type": export.get("export_type"),
        "signature": _first(export, "signature", "signature_line"),
        "file": _posix(str(export.get("source_file") or "")),
        "line": export.get("source_line"),
        "confidence": export.get("confidence") or "T1",
        "extraction_method": export.get("extraction_method") or "ast-grep",
        "ast_node_type": export.get("ast_node_type"),
    }


def _details_export(export: dict) -> dict | None:
    name, file = _first(export, "name", "export_name"), _first(export, "file", "source_file")
    if not isinstance(name, str) or not name.strip() or not isinstance(file, str) or not file.strip():
        return None
    return {
        "name": name.strip(),
        "type": _first(export, "type", "export_type"),
        "signature": export.get("signature"),
        "file": _posix(file),
        "line": _first(export, "line", "source_line"),
        "confidence": export.get("confidence") or "T1-low",
        "extraction_method": export.get("extraction_method") or "source-read",
        "ast_node_type": export.get("ast_node_type"),
    }


def _details(path: Path) -> tuple[list[str], list[dict]]:
    data = _read_object(path, "details file")
    files, exports = data.get("files", []), data.get("exports", [])
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise SnapshotError(f"details file {path}: `files` must be a list of paths")
    if not isinstance(exports, list) or not all(isinstance(e, dict) for e in exports):
        raise SnapshotError(f"details file {path}: `exports` must be a list of objects")
    return [_posix(f) for f in files], exports


def _entry_point_diff(runner: dict) -> dict:
    diff = runner.get("entry_point_diff")
    return diff if isinstance(diff, dict) else {}


def _outside_scope(runner: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in _entry_point_diff(runner).get("outside_scope") or []:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str) or not item.get("name"):
            continue
        group = grouped.setdefault(_posix(item["file"]), {"names": [], "entries": []})
        if item["name"] not in group["names"]:
            group["names"].append(item["name"])
        entry = item.get("entry")
        if isinstance(entry, str) and entry not in group["entries"]:
            group["entries"].append(entry)
    return [{"path": path, "names": sorted(g["names"]), "entries": sorted(g["entries"])}
            for path, g in sorted(grouped.items())]


def _extraction_gaps(runner: dict, exports: list[dict]) -> list[dict]:
    """The runner's extraction gaps no export of the snapshot holds yet, one
    per name and file."""
    held = {(e["name"], e["file"]) for e in exports}
    names = {e["name"] for e in exports}
    gaps: dict[tuple, dict] = {}
    for item in _entry_point_diff(runner).get("extraction_gaps") or []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            continue
        file = _posix(item["file"]) if isinstance(item.get("file"), str) else None
        if (item["name"], file) in held or (file is None and item["name"] in names):
            continue
        gaps.setdefault((item["name"], file),
                        {"name": item["name"], "file": file, "line": item.get("line"), "entry": item.get("entry")})
    return list(gaps.values())


def _baseline_gaps(provenance: dict, source_root: Path, statuses: dict[str, str], exports: list[dict],
                   listed: set[tuple]) -> tuple[list[dict], list[str]]:
    """The provenance entries the snapshot lacks whose cited file still
    declares them, and the entries no rule can check, by the verifier's
    `baseline_gaps` (the selection and the declaration rule both live
    there, beside `declared_line`, for update-skill's `baseline-gaps` too):
    the entries of the files `extracted` or `read-by-eye`, against the
    snapshot's exports, less the gaps `listed` already holds."""
    files = {file for file, status in statuses.items() if status in BASELINE_GAP_STATUSES}
    held = {(e["name"], e["file"]) for e in exports}
    return _verifier().baseline_gaps(provenance, source_root, held, files, listed)


def _ordered(exports) -> list[dict]:
    return sorted(exports, key=lambda e: (e["file"], e["line"] if isinstance(e["line"], int) else 0, e["name"]))


def _counts(exports: list[dict]) -> dict:
    by_type = Counter(str(e["type"]) for e in exports if e.get("type") is not None)
    t1 = sum(1 for e in exports if e.get("confidence") == "T1")
    return {"exports": len(exports), "by_type": dict(sorted(by_type.items())), "t1": t1,
            "t1_low": len(exports) - t1}


def build(source_root: Path, tier: str, date: str, provenance: dict | None, runner: dict | None,
          details_files: list[str], details_exports: list[dict], root_text: str | None = None) -> dict:
    """The snapshot (see the module docstring)."""
    warnings: list[str] = []
    runner = runner or {}
    runner_status = runner.get("status") if runner else None
    ran = runner_status in RUNNER_READ
    issues = {_posix(i["file"]): i.get("issue") for i in runner.get("file_issues") or []
              if isinstance(i, dict) and isinstance(i.get("file"), str)}
    unread = {_posix(f) for e in runner.get("errors") or [] if isinstance(e, dict)
              for f in e.get("unread") or [] if isinstance(f, str)}
    runner_exports = [_runner_export(e) for e in runner.get("exports") or []
                      if isinstance(e, dict) and e.get("export_name")] if ran else []
    extra = [x for x in (_details_export(e) for e in details_exports) if x is not None]
    if len(extra) < len(details_exports):
        warnings.append(f"{len(details_exports) - len(extra)} details export(s) name no export or no file: "
                        "left out")

    if provenance is not None:
        scope = list(_provenance().bounded_scan_files(provenance))
        # the files a code entry names; any other is a file_entries[] row
        code_files = set(_provenance().bounded_scan_files({"entries": provenance.get("entries")}))
        libraries = _provenance().source_library_by_file(provenance)
    else:
        named = [e["file"] for e in runner_exports + extra] + list(issues) + list(unread) + details_files
        scope = sorted(set(f for f in named if f))
        code_files = set(scope)
        libraries = {}
    in_scope = set(scope)

    exports: dict[tuple[str, str], dict] = {}
    hashed = Counter()
    for record in runner_exports + extra:
        if record["file"] not in in_scope:
            warnings.append(f"{record['name']} in {record['file']}: the file is outside the files in scope, "
                            "left out")
            continue
        if record["file"] not in code_files:
            hashed[record["file"]] += 1
            continue
        key = (record["name"], record["file"])
        held = exports.get(key)
        if held is None:
            exports[key] = record
        else:
            for field, value in record.items():
                if held.get(field) is None and value is not None:
                    held[field] = value
    warnings += [f"{count} export(s) in {file}: only file_entries[] names the file, which step 3 compares "
                 "by hash, left out" for file, count in sorted(hashed.items())]
    per_file = Counter(file for _, file in exports)

    files = []
    read_by_eye = set(details_files)
    for rel in scope:
        issue = issues.get(rel)
        if not (source_root / rel).is_file():
            runner_said = "missing"
        elif rel not in code_files:
            runner_said = "hash-tracked"
        elif ran and issue is not None and issue != "missing":
            runner_said = "parse-failed"
        elif not ran or (runner_status == "incomplete" and (rel in unread or not per_file[rel])):
            runner_said = "unread"
        else:
            runner_said = "extracted"
        by_eye = rel in read_by_eye and runner_said not in ("missing", "hash-tracked")
        status = "read-by-eye" if by_eye else runner_said
        files.append({"file": rel, "status": status,
                      "issue": issue if runner_said in ("parse-failed", "hash-tracked") else None,
                      "fallback": ran and runner_said in TO_READ, "exports": per_file[rel]})

    ordered = _ordered(exports.values())
    for record in ordered:
        library = libraries.get(record["file"])
        if library is not None:
            record["source_library"] = library
    by_status = Counter(f["status"] for f in files)
    recipes = [r for r in runner.get("recipes") or [] if isinstance(r, dict)]
    cap_hits = [r.get("id") for r in recipes if r.get("truncated")]
    if ran:
        fallback_files = [f["file"] for f in files if f["fallback"]]
    else:
        fallback_files = [] if tier.strip().lower() == "quick" else [AST_GREP_UNAVAILABLE]
    gaps = _extraction_gaps(runner, ordered) if ran else []
    if provenance is not None:
        baseline, unchecked = _baseline_gaps(provenance, source_root, {f["file"]: f["status"] for f in files},
                                             ordered, {(g["name"], g["file"]) for g in gaps})
        gaps += baseline
        if unchecked:
            warnings.append(f"{len(unchecked)} map entr{'y' if len(unchecked) == 1 else 'ies'} the snapshot "
                            f"lacks that no rule can check (in a file neither Python nor TS/JS, a file the "
                            f"declaration lookup does not read, or a dotted module name), so step 3 may report "
                            f"{'it' if len(unchecked) == 1 else 'them'} removed: "
                            + ", ".join(f"{u['name']} ({u['file']})" for u in unchecked))
    return {
        "extraction_date": date,
        "confidence_tier": tier,
        "source_root": root_text if root_text is not None else str(source_root),
        "bounded_scan": provenance is not None,
        "bounded_scan_source": "provenance-map" if provenance is not None else "source-tree-fallback",
        "runner_status": runner_status,
        "runner_errors": [e for e in runner.get("errors") or [] if isinstance(e, dict)],
        "files_scanned": len(scope),
        "complete": not any(by_status[status] for status in TO_READ),
        "files": files,
        "files_by_status": {status: by_status[status] for status in STATUSES},
        "ast_fallback_files": fallback_files,
        "extraction_gaps": gaps,
        "truncated": bool(runner.get("truncated")) or bool(cap_hits),
        "cap_hits": cap_hits,
        "outside_scope": _outside_scope(runner) if ran else [],
        "counts": _counts(ordered),
        "exports": ordered,
        "relocations": [],
        "warnings": warnings,
    }


def relocate(snapshot: dict, diff: dict, runner: dict) -> list[dict]:
    """Add to `snapshot` each export `runner` found under a removed name of
    `diff` in a file outside the snapshot's scope; the exports added."""
    removed: dict[str, dict] = {}
    for item in diff.get("removed") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            removed.setdefault(item["name"], item)
    exports = snapshot.get("exports")
    if not isinstance(exports, list) or not all(isinstance(e, dict) for e in exports):
        raise SnapshotError("the snapshot's `exports` must be a list of objects")
    scope = {f.get("file") for f in snapshot.get("files") or [] if isinstance(f, dict)}
    held = {(e.get("name"), e.get("file")) for e in exports}
    added = []
    if runner.get("status") in RUNNER_READ:
        for export in runner.get("exports") or []:
            if not isinstance(export, dict) or export.get("export_name") not in removed:
                continue
            record = _runner_export(export)
            if record["file"] in scope or (record["name"], record["file"]) in held:
                continue
            library = removed[record["name"]].get("source_library")
            if isinstance(library, str):
                record["source_library"] = library
            held.add((record["name"], record["file"]))
            added.append(record)
    if added:
        snapshot["exports"] = _ordered(exports + added)
        snapshot["counts"] = _counts(snapshot["exports"])
        snapshot["relocations"] = list(snapshot.get("relocations") or []) + [
            {"name": e["name"], "file": e["file"], "line": e["line"]} for e in added]
    return added


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_scan_list(args: argparse.Namespace) -> dict:
    provenance = _read_object(Path(args.provenance_map), "provenance map")
    files = list(_provenance().bounded_scan_files(provenance))
    _write(Path(args.output), files)
    return {"status": "ok", "output": args.output, "files": len(files)}


def _cmd_build(args: argparse.Namespace) -> dict:
    root = Path(args.source_root)
    if not root.is_dir():
        raise SnapshotError(f"source root not found: {args.source_root}")
    provenance = _read_object(Path(args.provenance_map), "provenance map") if args.provenance_map else None
    runner = _read_object(Path(args.extraction), "runner result") if args.extraction else None
    details_files: list[str] = []
    details_exports: list[dict] = []
    for path in args.details or []:
        files, exports = _details(Path(path))
        details_files += files
        details_exports += exports
    snapshot = build(root, args.tier, args.date, provenance, runner, details_files, details_exports,
                     root_text=args.source_path or args.source_root)
    _write(Path(args.output), snapshot)
    return {"status": "ok", "output": args.output, "runner_status": snapshot["runner_status"],
            "complete": snapshot["complete"],
            "to_read": [{"file": f["file"], "status": f["status"], "issue": f["issue"]}
                        for f in snapshot["files"] if f["status"] in TO_READ],
            "extraction_gaps": snapshot["extraction_gaps"], "ast_fallback_files": snapshot["ast_fallback_files"],
            "files_by_status": snapshot["files_by_status"], "counts": snapshot["counts"]}


def _cmd_relocate(args: argparse.Namespace) -> dict:
    path = Path(args.snapshot)
    snapshot = _read_object(path, "snapshot")
    added = relocate(snapshot, _read_object(Path(args.diff), "structural diff"),
                     _read_object(Path(args.extraction), "runner result"))
    if added:
        _write(path, snapshot)
    return {"status": "ok", "output": args.snapshot, "added": len(added),
            "names": sorted({e["name"] for e in added})}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-extraction-snapshot",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    scan = sub.add_parser("scan-list", help="write the files the provenance map covers as a JSON list")
    scan.add_argument("provenance_map", help="path to provenance-map.json")
    scan.add_argument("-o", "--output", required=True, help="the JSON list to write")
    scan.set_defaults(func=_cmd_scan_list)
    snap = sub.add_parser("build", help="build extraction-snapshot.json")
    snap.add_argument("--source-root", required=True, help="the source tree the runner read")
    snap.add_argument("--source-path",
                      help="the source root the provenance map records, written as the snapshot's source_root "
                           "(default: --source-root)")
    snap.add_argument("--tier", required=True, help="the forge tier the re-index ran at")
    snap.add_argument("--date", required=True, help="the run's timestamp, recorded as extraction_date")
    snap.add_argument("--provenance-map", help="the provenance map: its files are the files in scope")
    snap.add_argument("--extraction", help="the JSON skf-extract-public-api.py --mode full wrote")
    snap.add_argument("--details", action="append",
                      help="the exports read by eye: {\"files\": [...], \"exports\": [...]}; repeat per file")
    snap.add_argument("-o", "--output", required=True, help="the snapshot to write")
    snap.set_defaults(func=_cmd_build)
    move = sub.add_parser("relocate", help="add the exports the runner found under removed names elsewhere")
    move.add_argument("snapshot", help="extraction-snapshot.json, rewritten in place")
    move.add_argument("--diff", required=True, help="the structural diff whose removed[] names to look for")
    move.add_argument("--extraction", required=True, help="the runner's JSON over the candidate files")
    move.set_defaults(func=_cmd_relocate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except SnapshotError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return EXIT_ERROR
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
