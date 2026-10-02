# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF QMD Classify Collections — Set arithmetic over QMD collection names.

Replaces the prose-driven classification logic in `src/skf-setup/references/
auto-index.md` §2 with one Python invocation. Compares the live
QMD collections (from `qmd collection list`) against the forge registry
(`qmd_collections` array in forge-tier.yaml) and classifies each name as
Healthy / Orphaned / Stale, applying the forge-namespace suffix filter
added in PR #244 to silently exclude collections owned by unrelated
tools sharing the QMD daemon.

Classification rules (per step 3 §2):

  Healthy:  name in {forge-suffix-matched live} AND in registry.
              No action needed.
  Orphaned: name in {forge-suffix-matched live}, NOT in registry, and
              `qmd collection show <name>` reports a Path inside
              --project-root. Offered for removal in step 3 §3.
  Stale:    name in registry but NOT in {all live}. Registry entry
              should be removed.
  Foreign:  name in live that does NOT match a forge suffix, or a
              forge-suffixed name missing from the registry whose Path
              lies outside --project-root (or that qmd cannot show).
              Silently excluded from every classification: never
              displayed, never proposed for removal. Reported as a count
              for telemetry only.

QMD's index is shared by every project on the machine, and every SKF
project names its collections with the same suffixes, so a suffix alone
cannot tell this project's orphan from another project's healthy
collection. SKF adds each collection from a folder inside its project
(the forge data folder, the skills folder or `_bmad-output/`), so the
collection's Path names its owner. A Path that resolves outside the
project root, or none at all, never makes a collection removable here.

Forge suffixes (the only suffixes a forge-managed collection can have,
set by producers `skf-brief-skill` and `skf-create-skill` per
src/knowledge/qmd-registry.md § Collection Types):

  -brief, -temporal, -docs, -extraction

Subcommands:

  classify        Classify the live collections against the registry.

    --registry-from-yaml <path>
                  Path to forge-tier.yaml. The script reads the file's
                  `qmd_collections` array and extracts the `name` field
                  from each entry. Missing file or missing array → empty
                  registry, which is a valid first-run state.

    --project-root <path>
                  The project whose orphans may be offered for removal.

    --live-names  Comma-separated list of collection names currently
                  in QMD. If omitted, the script invokes `qmd collection
                  list` itself. Empty string → no live collections, which
                  is a valid first-run state.

  remove-orphans  Remove the orphans a classification found.

    --classification-from <path>
                  The classify output step 3 staged (`qmd-classify.json`);
                  its `orphaned` list names the collections to remove.

    --project-root <path>
                  Each collection's Path is read again with `qmd
                  collection show` just before `qmd collection remove`
                  runs, and a collection whose Path no longer lies inside
                  this root is not removed (it is listed under `failed`).

Output of classify (single JSON document on stdout):

  {
    "status": "ok",
    "version": "v1",
    "live_names":       ["bar-extraction", "foo-brief", "memory-root-1"],
    "healthy":          ["foo-brief", "foo-extraction"],
    "orphaned":         ["bar-extraction"],
    "orphaned_paths":   {"bar-extraction": "/abs/project/skills/bar"},
    "stale":            ["baz-docs"],
    "foreign_filtered_count": 4,
    "foreign_filtered_sample": ["memory-root-1", "sessions-2"]
  }

Output of remove-orphans (single JSON document on stdout):

  {
    "status": "ok",
    "version": "v1",
    "removed": ["bar-extraction"],
    "failed":  ["old-docs"],
    "errors":  {"old-docs": "its Path no longer lies inside the project root"}
  }

A collection that could not be removed is a hygiene note, not an error:
remove-orphans exits 0 whatever it removed.

`foreign_filtered_sample` is capped at 5 names (telemetry; the full list
is never useful: if it were forge-relevant it would have a forge suffix
and a Path inside the project).

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared
above is auto-resolved on first call and cached. `docs/getting-started.md`
documents uv as the runtime prerequisite for exactly this. Bare
`python3` will fail with `ModuleNotFoundError: No module named 'yaml'`
on a fresh interpreter:

  uv run skf-qmd-classify-collections.py classify \\
      --registry-from-yaml /path/forge-tier.yaml --project-root /path/project
  uv run skf-qmd-classify-collections.py remove-orphans \\
      --classification-from /run/qmd-classify.json --project-root /path/project

Exit codes:
  0 success
  1 user error (bad args, malformed registry or classification file)
  2 internal error (qmd collection list failed)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

import yaml


FORGE_SUFFIXES = ("-brief", "-temporal", "-docs", "-extraction")
FOREIGN_SAMPLE_CAP = 5

# Header line emitted by newer qmd builds, e.g. "Collections (56):".
_QMD_HEADER_RE = re.compile(r"^Collections \(\d+\):\s*$")

# Empty-state message from `qmd collection list`, e.g.
# "No collections found. Run 'qmd collection add .' to create one."
_QMD_EMPTY_STATE_PREFIX = "No collections found"


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    payload.setdefault("version", "v1")
    print(json.dumps(payload))


def is_forge_owned(name: str) -> bool:
    """True if `name` ends with one of the forge suffixes."""
    return any(name.endswith(suffix) for suffix in FORGE_SUFFIXES)


def parse_live_names(raw: str) -> list[str]:
    """Comma-separated → de-duplicated list, preserving first-occurrence order.

    Collection names from `qmd collection list` are user-facing strings;
    we trust them as-is rather than imposing additional validation.
    """
    seen = set()
    out: list[str] = []
    for token in raw.split(","):
        name = token.strip()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def load_registry_names(path: Path) -> list[str]:
    """Read forge-tier.yaml and extract `name` from each qmd_collections entry.

    Missing file → empty list (valid first-run state). Malformed file
    (parse error, wrong top-level type) → exit 1 with an actionable
    message. Entries without a `name` field are skipped silently — the
    forge-tier-rw.py contract guarantees `name` is always present, but
    a hand-edited file might violate it; classify what we can.
    """
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        _die(1, f"failed to parse {path}: {e}")
    if data is None:
        return []
    if not isinstance(data, dict):
        _die(1, f"expected mapping at top of {path}, got {type(data).__name__}")
    entries = data.get("qmd_collections", []) or []
    if not isinstance(entries, list):
        _die(1, f"qmd_collections in {path} is not a list (got {type(entries).__name__})")
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return names


def is_inside(path: str | None, root) -> bool:
    """True when `path` resolves to `root` or a folder below it.

    Both sides go through realpath and normcase, so a symlinked project
    root or a Windows drive letter in another case still matches. A path
    on another drive, or none at all, is never inside.
    """
    if not path or not root:
        return False
    try:
        target = os.path.normcase(os.path.realpath(path))
        base = os.path.normcase(os.path.realpath(str(root)))
        return os.path.commonpath([target, base]) == base
    except (OSError, ValueError):
        return False


def classify(live: list[str], registry: list[str], project_root=None,
             paths: dict | None = None) -> dict:
    """Pure function: classify live vs registry into healthy/orphaned/stale/foreign.

    With `project_root`, a forge-suffixed live name missing from the
    registry is orphaned only when `paths` maps it to a Path inside that
    root; the rest count as foreign. Without it every such name is
    orphaned: only a caller that already knows they all belong to this
    project may leave it out (the CLI always passes it).

    Returns the classification payload (without status/version envelope).
    """
    paths = paths or {}
    forge_live = [n for n in live if is_forge_owned(n)]
    foreign_live = [n for n in live if not is_forge_owned(n)]

    forge_live_set = set(forge_live)
    registry_set = set(registry)
    all_live_set = set(live)

    healthy = sorted(forge_live_set & registry_set)
    candidates = sorted(forge_live_set - registry_set)
    if project_root is None:
        orphaned = candidates
    else:
        orphaned = [n for n in candidates if is_inside(paths.get(n), project_root)]
        # Another project's collection, or one qmd could not show, is no
        # orphan of this one: it counts the way a name with no forge suffix does.
        foreign_live += [n for n in candidates if n not in orphaned]
    # Stale uses the full live set, NOT just the forge-filtered set, so a
    # registry entry whose name happens to match a non-forge live collection
    # would still count as stale. Registry entries always have forge suffixes
    # by convention, so this distinction matters only on hand-edited files.
    stale = sorted(registry_set - all_live_set)

    return {
        "live_names": sorted(all_live_set),
        "healthy": healthy,
        "orphaned": orphaned,
        "orphaned_paths": {n: paths[n] for n in orphaned if paths.get(n)},
        "stale": stale,
        "foreign_filtered_count": len(foreign_live),
        "foreign_filtered_sample": foreign_live[:FOREIGN_SAMPLE_CAP],
    }


def parse_collection_list_output(raw: str) -> list[str]:
    """Extract collection names from `qmd collection list` stdout.

    qmd's output format varies by version. Newer builds print a
    `Collections (N):` header, a blank line between entries, each entry as
    `<name> (qmd://<name>/)`, and indented metadata lines (`  Pattern:`,
    `  Files:`). Older builds print one bare name per line. Both layouts are
    handled: skip blank lines, the header, and indented metadata, then take
    the first whitespace-delimited token of each remaining line — that strips
    the trailing ` (qmd://name/)` URI and is a no-op for the bare-name form.
    Without this, suffixed entries fail the `is_forge_owned` suffix check and
    every forge collection is mis-classified as foreign.

    The empty-state message ("No collections found. …") is recognized before
    per-line tokenizing — it would otherwise parse as a collection named "No".
    """
    if raw.lstrip().startswith(_QMD_EMPTY_STATE_PREFIX):
        return []
    names: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line[0].isspace():  # indented per-collection metadata
            continue
        if _QMD_HEADER_RE.match(line):
            continue
        names.append(line.split()[0])
    return names


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here is the repo under analysis — a bare-name lookup resolving
    into CWD would execute a repo-planted shim (e.g. qmd.cmd). Such a
    resolution is treated as not-found. Explicit paths supplied by callers
    (containing a separator) are honored as-is. Keep identical to the
    sibling guards in skf-detect-tools.py,
    skf-merge-ccc-exclusions.py, skf-ccc-git-hygiene.py,
    skf-source-tree.py, skf-tessl-review.py and
    skf-verify-provenance-completeness.py.
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    if os.sep in command or (os.altsep and os.altsep in command):
        return resolved
    resolved_dir = os.path.dirname(resolved)
    if resolved_dir:
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        if os.path.normcase(os.path.abspath(resolved_dir)) == cwd:
            return None
    return resolved


def _run_qmd(*args: str) -> tuple[int | None, str, str]:
    """Run `qmd <args>`; return (exit code, stdout, stderr), exit code None when it could not run."""
    import subprocess
    # Resolve before spawning: on Windows qmd ships from npm as a .CMD
    # shim, which a bare-name subprocess.run cannot launch (WinError 2).
    qmd = _resolve_outside_cwd("qmd")
    if qmd is None:
        return None, "", "qmd not found on PATH"
    try:
        # qmd emits UTF-8; a locale-default decode (cp1252 on Windows)
        # mojibakes names or raises UnicodeDecodeError on unmapped bytes.
        result = subprocess.run(
            [qmd, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return None, "", f"qmd {' '.join(args[:2])} failed: {e}"
    return result.returncode, result.stdout or "", result.stderr or ""


def fetch_live_names_from_qmd() -> tuple[list[str], str | None]:
    """Invoke `qmd collection list` and return (names, error).

    Owns the CLI parsing so callers (and prompts) don't reinvent it.
    Empty stdout / non-zero exit → ([], error_message). The classifier's
    same-process invocation here is the single source of truth for what
    counts as a "live collection name".
    """
    code, out, err = _run_qmd("collection", "list")
    if code is None:
        return [], err
    if code != 0:
        return [], f"qmd collection list exited {code}: {err.strip() or '<no stderr>'}"
    return parse_collection_list_output(out), None


def parse_collection_path(raw: str) -> str | None:
    """The folder a `qmd collection show` output names on its `Path:` line, or None."""
    for line in raw.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key == "Path" and value.strip():
            return value.strip()
    return None


def fetch_collection_path(name: str) -> tuple[str | None, str | None]:
    """Run `qmd collection show <name>`; return (its Path, error)."""
    code, out, err = _run_qmd("collection", "show", name)
    if code is None:
        return None, err
    if code != 0:
        return None, f"qmd collection show exited {code}: {(err or out).strip() or '<no output>'}"
    path = parse_collection_path(out)
    return (path, None) if path else (None, "qmd collection show printed no Path line")


def remove_orphans(names: list[str], project_root) -> dict:
    """Remove each orphan whose Path still lies inside `project_root`.

    The Path is read again just before each removal, so a collection that
    another project re-created under the same name since the classification
    is left alone. Returns {"removed", "failed", "errors"}.
    """
    removed: list[str] = []
    failed: list[str] = []
    errors: dict[str, str] = {}
    for name in names:
        path, error = fetch_collection_path(name)
        if error is None and not is_inside(path, project_root):
            error = "its Path no longer lies inside the project root"
        if error is None:
            code, out, err = _run_qmd("collection", "remove", name)
            if code is None:
                error = err
            elif code != 0:
                error = f"qmd collection remove exited {code}: {(err or out).strip() or '<no output>'}"
        if error is None:
            removed.append(name)
        else:
            failed.append(name)
            errors[name] = " ".join(error.split())
    return {"removed": removed, "failed": failed, "errors": errors}


def load_orphaned_names(path: Path) -> list[str]:
    """The `orphaned` list of a staged classification, or exit 1 when there is none."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        _die(1, f"remove-orphans: cannot read the classification {path}: {e}")
    orphaned = data.get("orphaned") if isinstance(data, dict) else None
    if not isinstance(orphaned, list) or not all(isinstance(n, str) for n in orphaned):
        _die(1, f"remove-orphans: {path} holds no `orphaned` list of names")
    return orphaned


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify QMD collections vs forge registry, and remove the orphans.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_classify = sub.add_parser("classify", help="Classify live collections against the registry")
    p_classify.add_argument(
        "--live-names",
        default=None,
        help="Comma-separated list of collection names currently in QMD. "
             "If omitted, the script invokes `qmd collection list` itself. "
             "Empty string → no live collections.",
    )
    p_classify.add_argument(
        "--registry-from-yaml",
        type=Path,
        required=True,
        help="Path to forge-tier.yaml. Script reads qmd_collections array. "
             "Missing file → empty registry (first-run state).",
    )
    p_classify.add_argument(
        "--project-root",
        required=True,
        help="The project whose orphans may be offered for removal: a collection "
             "outside the registry is orphaned only when its Path lies inside it.",
    )
    p_remove = sub.add_parser("remove-orphans",
                              help="Remove the orphans a staged classification lists")
    p_remove.add_argument("--classification-from", type=Path, required=True,
                          help="The classify output (qmd-classify.json).")
    p_remove.add_argument("--project-root", required=True,
                          help="Each Path is checked against this root again before its removal.")
    args = parser.parse_args()

    if args.cmd == "remove-orphans":
        _ok(remove_orphans(load_orphaned_names(args.classification_from), args.project_root))
        return
    if args.live_names is None:
        names, error = fetch_live_names_from_qmd()
        if error is not None:
            _die(2, error)
        live = names
    else:
        live = parse_live_names(args.live_names)
    registry = load_registry_names(args.registry_from_yaml)
    candidates = sorted({n for n in live if is_forge_owned(n)} - set(registry))
    paths = {name: fetch_collection_path(name)[0] for name in candidates}
    _ok(classify(live, registry, args.project_root, paths))


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
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
