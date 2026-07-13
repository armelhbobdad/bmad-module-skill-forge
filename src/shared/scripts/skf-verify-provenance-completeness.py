#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Verify Provenance Completeness — deterministic Check D for update-skill.

`skf-update-skill/references/validate.md §2 Check D (Provenance Completeness)`
previously asked the model to perform three deterministic set/citation
operations by eye, against in-context data:

  1. **Completeness** — verify every documented export has a provenance-map
     entry (metadata `exports[]` \\ provenance `entries[].export_name`).
  2. **Orphans** — flag provenance entries whose export was removed
     (provenance `entries[].export_name` \\ metadata `exports[]`).
  3. **Stale citations** — flag entries whose `source_file:source_line`
     no longer resolves (file gone, or line past end of file).

An LLM set-diff can silently pass a dropped or orphaned entry, and eyeballing
whether a cited line still exists is not something the model can do reliably.
Both inputs are machine-readable — `metadata.json` (`exports[]`, a list of
export-name strings) and `provenance-map.json` (`entries[]` with
`export_name` / `source_file` / `source_line`, plus an optional
`reexport_map` for stack-skill barrel renames) are written by
`write.md` §2 and §3. This script diffs the two sets and re-checks the
citations exactly, so Check D consumes JSON rather than computing it.

Timing: this runs **post-write** (`write.md` §6), after `metadata.json`
(§2) and `provenance-map.json` (§3) are on disk. `validate.md` Check D
defers here — the provenance map does not exist yet at validate time.

Determinism:
  - Set operations are pure over the two JSON inputs.
  - Citation resolution reads the source tree at `source_root` (from the
    provenance map, or `--source-root`). When no source root resolves on
    disk, the stale check is SKIPPED (`summary.stale_check` reports it) and
    only completeness + orphan diffs run — those need no source tree. Same
    input tree → same output.

Stack-skill canonicalization: a provenance entry's `export_name` may be the
internal name of a barrel-renamed export (e.g. `_Impl` re-exported as
`Public`). Names are canonicalized through `reexport_map`
(`{internal: public}`) before the set-diff, mirroring
`skf-load-provenance.extract_reexport_map`, so an internal-named entry does
not read as a missing public export nor as an orphan.

Subcommand:
  verify --metadata <metadata.json> --provenance <provenance-map.json>
         [--source-root <path>] [-o <out.json>]

    Emit JSON:
      {
        "status": "pass" | "findings",
        "missing":  ["<export documented but not in provenance>", ...],
        "orphaned": ["<provenance entry with no documented export>", ...],
        "stale": [
          {"export_name": "<raw entry name>",
           "source_file": "<rel path>",
           "source_line": <int|null>,
           "reason": "file-missing" | "line-out-of-bounds" | "line-invalid"},
          ...
        ],
        "summary": {
          "exports_checked":  <int>,   # documented exports (metadata)
          "entries_checked":  <int>,   # provenance entries with export_name
          "missing_count":    <int>,
          "orphaned_count":   <int>,
          "stale_count":      <int>,
          "citations_checked": <int>,  # entries whose citation was resolved
          "stale_check": "checked" | "skipped-no-source-root"
        }
      }

    `missing` / `orphaned` are sorted, deduplicated public names.
    `stale` is sorted by (export_name, source_file).

CLI examples:
  uv run skf-verify-provenance-completeness.py verify \\
      --metadata {skill_package}/metadata.json \\
      --provenance {forge_version}/provenance-map.json \\
      --source-root {source_root}

Exit codes:
  0  — verification ran and found nothing (status "pass")
  1  — verification ran and found missing / orphaned / stale entries
       (status "findings"); advisory — the caller decides how to surface it
  2  — error (input file not found, malformed JSON, invalid structure)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


STALE_FILE_MISSING = "file-missing"
STALE_LINE_OOB = "line-out-of-bounds"
STALE_LINE_INVALID = "line-invalid"


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def load_json_object(path: Path, label: str) -> dict:
    """Read a JSON file and require a top-level object. Raises ValueError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {label} {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{label} {path} must be a JSON object at top level; "
            f"got {type(data).__name__}"
        )
    return data


# --------------------------------------------------------------------------
# Extraction / canonicalization
# --------------------------------------------------------------------------


def extract_export_names(metadata: dict) -> list[str]:
    """Pull documented export names from metadata.exports.

    `exports` is a list of export-name strings (per the skill templates).
    Defensively also accept dict items carrying `name` / `export_name`.
    Non-string / unnamed items are skipped. Order preserved; caller dedupes.
    """
    names: list[str] = []
    exports = metadata.get("exports")
    if not isinstance(exports, list):
        return names
    for item in exports:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            nm = item.get("name") or item.get("export_name")
            if isinstance(nm, str) and nm:
                names.append(nm)
    return names


def extract_reexport_map(prov: dict) -> dict[str, str]:
    """Build the `{internal: public}` re-export map.

    Mirrors `skf-load-provenance.extract_reexport_map`: top-level
    `reexport_map` is authoritative; per-entry `reexported_as` fills gaps.
    Non-string keys/values skipped.
    """
    out: dict[str, str] = {}
    top = prov.get("reexport_map")
    if isinstance(top, dict):
        for k, v in top.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    entries = prov.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            internal = entry.get("export_name")
            public = entry.get("reexported_as")
            if isinstance(internal, str) and isinstance(public, str):
                out.setdefault(internal, public)
    return out


def canon(name: str, reexport_map: dict[str, str]) -> str:
    """Canonicalize an export name to its public form via reexport_map.

    Idempotent for names that are not internal (public names are not keys).
    """
    return reexport_map.get(name, name)


def provenance_entry_names(prov: dict) -> list[str]:
    """Raw `export_name` of every well-formed provenance entry (order kept)."""
    names: list[str] = []
    entries = prov.get("entries")
    if not isinstance(entries, list):
        return names
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nm = entry.get("export_name")
        if isinstance(nm, str) and nm:
            names.append(nm)
    return names


# --------------------------------------------------------------------------
# Citation resolution
# --------------------------------------------------------------------------


def _coerce_line(value: object) -> int | None | str:
    """Return an int line number, None (tolerated), or a sentinel str for
    an un-coercible non-null value (reported as line-invalid)."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass — a boolean line number is nonsense
        return "invalid"
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return "invalid"
    return "invalid"


def check_citation(
    source_file: object, source_line: object, source_root: Path
) -> str | None:
    """Resolve a single `source_file:source_line` citation under source_root.

    Returns a stale reason (one of the STALE_* constants) when the citation
    does not resolve, or None when it is valid OR tolerated.

    Tolerated (returns None): source_file missing/empty, or source_line null
    or empty — `unknown`-outcome entries legitimately carry null citations
    (write.md §3), so an absent citation is not "stale".
    """
    if not isinstance(source_file, str) or not source_file.strip():
        return None
    line = _coerce_line(source_line)
    if line is None:
        return None
    if isinstance(line, str):  # sentinel for un-coercible non-null value
        return STALE_LINE_INVALID

    rel = source_file.strip().replace("\\", "/")
    target = (source_root / rel).resolve()
    if not target.is_file():
        return STALE_FILE_MISSING

    if line < 1:
        return STALE_LINE_OOB
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            line_count = sum(1 for _ in fh)
    except OSError:
        return STALE_FILE_MISSING
    if line > line_count:
        return STALE_LINE_OOB
    return None


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def resolve_source_root(prov: dict, override: str | None) -> Path | None:
    """Pick the source root for citation resolution.

    `--source-root` override wins; otherwise the provenance map's top-level
    `source_root`. Returns None when neither resolves to an on-disk dir.
    """
    candidate: str | None = None
    if override:
        candidate = override
    else:
        sr = prov.get("source_root")
        if isinstance(sr, str) and sr:
            candidate = sr
    if not candidate:
        return None
    root = Path(candidate)
    return root if root.is_dir() else None


def verify(metadata: dict, prov: dict, source_root: Path | None) -> dict:
    """Compute the completeness / orphan / stale report over the two maps."""
    reexport_map = extract_reexport_map(prov)

    documented = extract_export_names(metadata)
    documented_canon = {canon(n, reexport_map) for n in documented}

    raw_entry_names = provenance_entry_names(prov)
    entry_canon = {canon(n, reexport_map) for n in raw_entry_names}

    missing = sorted(documented_canon - entry_canon)
    orphaned = sorted(entry_canon - documented_canon)

    stale: list[dict] = []
    citations_checked = 0
    if source_root is not None:
        entries = prov.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("export_name")
                if not isinstance(name, str) or not name:
                    continue
                sf = entry.get("source_file")
                sl = entry.get("source_line")
                # Only count a resolvable (non-null) citation as "checked".
                if isinstance(sf, str) and sf.strip() and _coerce_line(sl) is not None:
                    citations_checked += 1
                reason = check_citation(sf, sl, source_root)
                if reason is not None:
                    stale.append(
                        {
                            "export_name": name,
                            "source_file": sf if isinstance(sf, str) else None,
                            "source_line": sl if isinstance(sl, int)
                            and not isinstance(sl, bool) else sl,
                            "reason": reason,
                        }
                    )
        stale.sort(key=lambda s: (s["export_name"], s.get("source_file") or ""))

    status = "pass" if not (missing or orphaned or stale) else "findings"
    return {
        "status": status,
        "missing": missing,
        "orphaned": orphaned,
        "stale": stale,
        "summary": {
            "exports_checked": len(documented_canon),
            "entries_checked": len(raw_entry_names),
            "missing_count": len(missing),
            "orphaned_count": len(orphaned),
            "stale_count": len(stale),
            "citations_checked": citations_checked,
            "stale_check": "checked"
            if source_root is not None
            else "skipped-no-source-root",
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    meta_path = Path(args.metadata)
    prov_path = Path(args.provenance)
    if not meta_path.is_file():
        print(f"error: metadata not found: {meta_path}", file=sys.stderr)
        return 2
    if not prov_path.is_file():
        print(f"error: provenance map not found: {prov_path}", file=sys.stderr)
        return 2
    try:
        metadata = load_json_object(meta_path, "metadata")
        prov = load_json_object(prov_path, "provenance map")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    source_root = resolve_source_root(prov, args.source_root)
    if args.verbose:
        if source_root is None:
            print(
                "verbose: no source root resolved — skipping stale-citation "
                "check (completeness + orphan diffs only)",
                file=sys.stderr,
            )
        else:
            print(f"verbose: resolving citations under {source_root}", file=sys.stderr)

    result = verify(metadata, prov, source_root)

    out_text = json.dumps(result, indent=2) + "\n"
    if args.output and args.output != "-":
        Path(args.output).write_text(out_text, encoding="utf-8")
    else:
        sys.stdout.write(out_text)

    return 0 if result["status"] == "pass" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-verify-provenance-completeness",
        description=(
            "Cross-reference documented exports (metadata.json) against "
            "provenance-map entries — completeness, orphans, and stale "
            "file:line citations — emitting findings as JSON."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "verify",
        help="emit provenance completeness / orphan / stale-citation findings",
    )
    p.add_argument("--metadata", required=True, help="path to metadata.json")
    p.add_argument(
        "--provenance", required=True, help="path to provenance-map.json"
    )
    p.add_argument(
        "--source-root",
        default=None,
        help=(
            "source tree root for citation resolution; overrides the "
            "provenance map's source_root. Stale check is skipped when no "
            "root resolves on disk."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.add_argument(
        "--verbose", action="store_true", help="diagnostics to stderr"
    )
    p.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
