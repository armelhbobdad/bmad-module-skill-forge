# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Load Provenance — normalize provenance-map.json into deterministic projections.

`skf-audit-skill` reads one provenance map in several steps, and each needs
a projection of it with one correct answer:

  1. **init.md §4 Load Provenance Map + Stack Skill Detection** — extracts
     `source_root`, `baseline_commit` (`source_commit`), `baseline_ref`
     (`source_ref`), detects stack-skill flags (`provenance_version` and
     top-level `libraries` for legacy v1 stacks), and takes the baseline
     facts init.md §7 shows (export count, generation time and age).

  2. **re-index.md §2 and §3**: the **bounded scan list** (the union of
     `entries[].source_file` and `file_entries[].source_file`), which the
     recipe runner reads, and for a stack the library of each file
     (`source_library_by_file`), which skf-extraction-snapshot.py gives each
     export of the snapshot it builds (it loads this script beside it).

skf-structural-diff.py derives the re-export map from the provenance map
itself and applies the quote-style, stdlib-prefix and re-export transforms
on both sides (structural-diff.md §1), so no step carries `reexport_map`
from here; the field stays for a caller that passes it to the diff as
`--reexport-map`. The diff also takes a semantic kind a by-eye read
records as the runner's base kind for the same declaration (its
export-type comparison).

The transforms here are pure projections — no I/O against the source tree,
no comparisons. The script reads one JSON, emits one JSON.

Subcommand:
  normalize <map.json> [--now <ISO-8601>]
      Emit JSON:
        {
          "bounded_scan_files": ["<rel-path, forward-slash>", ...],
          "is_stack_skill": <bool>,
          "legacy_stack_provenance": <bool>,
          "compose_mode_stack": <bool>,
          "source_root": "<path or null>",
          "baseline_commit": "<sha or null>",
          "baseline_ref": "<ref or null>",
          "reexport_map": {"<from-internal>": "<to-public>"},
          "source_library_by_file": {"<rel-path>": "<library>"},
          "export_count": <int>,
          "generated_at": "<YYYY-MM-DDTHH:MM:SSZ or null>",
          "age_days": <int or null>,
          "age_source": "generated_at" | "mtime" | null
        }

      Bounded scan = union of `entries[].source_file` and
      `file_entries[].source_file`, deduplicated, sorted, normalized to
      POSIX forward-slash separators.

      Stack-skill detection mirrors `init.md` §Stack Skill Detection:
        - `is_stack_skill` is true if `provenance_version >= "2.0"` AND a
          top-level `libraries` key is present.
        - `legacy_stack_provenance` is true if `provenance_version` is "1"
          (or "1.0", or absent treated as v1) AND `skill_type == "stack"`.
        Note: detecting `is_stack_skill` for a v1 map by the presence of
        `libraries` alone (the documented behavior in init.md) is also
        honored — see condition handling in `detect_stack_flags`.
        - `compose_mode_stack` is true for a stack whose map holds a
          `constituents` list: the compose-mode variant create-stack-skill
          writes, whose entries come from constituent skills rather than a
          source tree. Audit-skill checks its constituents' freshness
          instead of re-indexing a source.

      File-to-library map: each `entries[].source_file` (forward slashes)
      with the `source_library` of its entries, for a stack's per-library
      diff. A file whose entries name no library is left out, and when its
      entries name two, the first one's wins. Empty for a single skill
      whose entries carry no `source_library`.

      Re-export map: read `reexport_map` field directly from the provenance
      map if it exists (writer-side captures __init__.py walk results there).
      Otherwise, walk `entries[]` for any `reexported_as` field on individual
      entries — older provenance writers may have used that shape. Empty
      object when neither is present.

      Baseline facts for init.md §7 (the audit baseline summary):
        - `export_count` is the number of `entries[]` objects.
        - `generated_at` is the map's `generated_at` in UTC, whatever zone
          it was written in; null when absent or not an ISO-8601 date-time.
        - `age_days` is the whole days from `generated_at` to now (never
          below 0), or from the file's modification time when the map has
          no usable `generated_at` (`age_source` says which; null when
          neither is known). `--now` fixes "now" for a reproducible run.

CLI examples:
  uv run skf-load-provenance.py normalize /path/to/provenance-map.json
  uv run skf-load-provenance.py normalize /path/to/provenance-map.json --now 2026-05-01T00:00:00Z

Exit codes:
  0  — normalization succeeded (including empty / well-formed map with no
       entries — emits all-defaults JSON)
  1  — user error (file not found, malformed JSON, structurally invalid map)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


# --------------------------------------------------------------------------
# Provenance map I/O
# --------------------------------------------------------------------------


def load_provenance(path: Path) -> dict:
    """Read a provenance map JSON. Returns the top-level object.

    Raises ValueError on read failure or non-object top-level.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read provenance file {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in provenance file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"provenance file {path} must be a JSON object at top level; "
            f"got {type(data).__name__}"
        )
    return data


# --------------------------------------------------------------------------
# Projections
# --------------------------------------------------------------------------


def _posix(p: str) -> str:
    """Normalize a path string to forward-slash form."""
    return p.replace("\\", "/")


def bounded_scan_files(data: dict) -> list[str]:
    """Union of entries[].source_file + file_entries[].source_file.

    Deduplicated; sorted; forward-slash. Non-string source_file values are
    silently skipped (consistent with downstream code that expects strings).
    """
    paths: set[str] = set()
    entries = data.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sf = entry.get("source_file")
            if isinstance(sf, str) and sf:
                paths.add(_posix(sf))
    file_entries = data.get("file_entries")
    if isinstance(file_entries, list):
        for entry in file_entries:
            if not isinstance(entry, dict):
                continue
            sf = entry.get("source_file")
            if isinstance(sf, str) and sf:
                paths.add(_posix(sf))
    return sorted(paths)


def source_library_by_file(data: dict) -> dict[str, str]:
    """{source_file: source_library} from `entries[]`, paths forward-slash.

    The first library named for a file wins; entries without a string
    `source_library` add nothing.
    """
    out: dict[str, str] = {}
    entries = data.get("entries")
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sf, library = entry.get("source_file"), entry.get("source_library")
        if isinstance(sf, str) and sf and isinstance(library, str) and library:
            out.setdefault(_posix(sf), library)
    return dict(sorted(out.items()))


def _normalize_version(v: object) -> tuple[int, ...] | None:
    """Parse a provenance_version string like "2.0" / "1.5" into a tuple.

    Returns None on absence or unparseable input (treat as legacy v1).
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return (int(v),)
    if not isinstance(v, str):
        return None
    parts: list[int] = []
    for chunk in v.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            return None
    return tuple(parts) if parts else None


def detect_stack_flags(data: dict) -> tuple[bool, bool]:
    """Return (is_stack_skill, legacy_stack_provenance).

    Mirrors init.md §Stack Skill Detection:
      - v2+ with libraries → is_stack_skill=true
      - v2+ with skill_type=="stack" → is_stack_skill=true
      - v1 / no version with top-level `libraries` → is_stack_skill=true,
        legacy_stack_provenance=true
      - v1 / no version with skill_type=="stack" → is_stack_skill=true,
        legacy_stack_provenance=true
      - otherwise → both false
    """
    version = _normalize_version(data.get("provenance_version"))
    has_libraries = isinstance(data.get("libraries"), (dict, list))
    skill_type = data.get("skill_type") if isinstance(data.get("skill_type"), str) else None
    is_v2 = version is not None and version[0] >= 2

    if is_v2:
        # v2 stack signaled by either skill_type or libraries presence
        is_stack = (skill_type == "stack") or has_libraries
        legacy = False
        return is_stack, legacy

    # v1 / unversioned — legacy detection by `libraries` key OR skill_type
    if has_libraries or skill_type == "stack":
        return True, True
    return False, False


def extract_reexport_map(data: dict) -> dict[str, str]:
    """Build the public-API re-export map.

    Two writer schemas are supported:

      1. **Top-level `reexport_map`** — modern writers persist the
         __init__.py walk results here directly, as `{"<internal>": "<public>"}`.

      2. **Per-entry `reexported_as`** — legacy writers (or hand-edited maps)
         may carry the re-export on each `entries[]` item as
         `{"export_name": "_Impl", "reexported_as": "Public"}`. We collect
         all such pairs into the same map shape.

    Non-string keys/values are silently skipped.
    """
    out: dict[str, str] = {}
    top = data.get("reexport_map")
    if isinstance(top, dict):
        for k, v in top.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    entries = data.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            internal = entry.get("export_name")
            public = entry.get("reexported_as")
            if isinstance(internal, str) and isinstance(public, str):
                # per-entry value wins only if the top-level didn't already
                # carry a binding for the internal name (top-level is the
                # canonical aggregated form)
                out.setdefault(internal, public)
    return out


ISO_TIME_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?"
    r"\s*([Zz]|[+-]\d{2}(?::?\d{2})?)?")


# Keep identical to _parse_iso_utc in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _parse_iso_utc(value):
    """An ISO-8601 date or date-time as an aware UTC datetime, else None.

    A time without a zone is read as UTC, a date alone as its midnight UTC.
    """
    if not isinstance(value, str):
        return None
    m = ISO_TIME_RE.fullmatch(value.strip())
    if not m:
        return None
    year, month, day, hour, minute, second, fraction, zone = m.groups()
    offset = timedelta(0)
    if zone and zone not in ("Z", "z"):
        digits = zone[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:] or 0))
        if zone[0] == "-":
            offset = -offset
    try:
        moment = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                          int(second or 0), int((fraction or "0")[:6].ljust(6, "0")))
        return (moment - offset).replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):  # no such date, or out of datetime's range
        return None


def export_count(data: dict) -> int:
    """The number of `entries[]` objects (the exports the map records)."""
    entries = data.get("entries")
    if not isinstance(entries, list):
        return 0
    return sum(1 for entry in entries if isinstance(entry, dict))


def provenance_age(
    data: dict, mtime: datetime | None = None, now: datetime | None = None
) -> dict:
    """{generated_at, age_days, age_source} for the audit baseline.

    `generated_at` is the map's field in UTC (null when absent or not
    ISO-8601). The age counts whole days from it to `now` (the current time
    when None), else from `mtime` (the file's modification time), never
    below 0.
    """
    generated = _parse_iso_utc(data.get("generated_at"))
    if generated is not None:
        since, source = generated, "generated_at"
    elif mtime is not None:
        since, source = mtime, "mtime"
    else:
        since, source = None, None
    age_days = None
    if since is not None:
        age_days = max(0, ((now or datetime.now(timezone.utc)) - since).days)
    return {
        "generated_at": generated.strftime("%Y-%m-%dT%H:%M:%SZ") if generated else None,
        "age_days": age_days,
        "age_source": source,
    }


def normalize(
    data: dict, mtime: datetime | None = None, now: datetime | None = None
) -> dict:
    """Build the full normalized projection record."""
    is_stack, legacy = detect_stack_flags(data)
    source_root = data.get("source_root") if isinstance(data.get("source_root"), str) else None
    baseline_commit = (
        data.get("source_commit") if isinstance(data.get("source_commit"), str) else None
    )
    baseline_ref = (
        data.get("source_ref") if isinstance(data.get("source_ref"), str) else None
    )
    return {
        "bounded_scan_files": bounded_scan_files(data),
        "is_stack_skill": is_stack,
        "legacy_stack_provenance": legacy,
        "compose_mode_stack": is_stack and isinstance(data.get("constituents"), list),
        "source_root": source_root,
        "baseline_commit": baseline_commit,
        "baseline_ref": baseline_ref,
        "reexport_map": extract_reexport_map(data),
        "source_library_by_file": source_library_by_file(data),
        "export_count": export_count(data),
        **provenance_age(data, mtime, now),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_normalize(args: argparse.Namespace) -> int:
    path = Path(args.provenance_map)
    if not path.is_file():
        print(f"error: provenance map not found: {path}", file=sys.stderr)
        return 1
    now = None
    if args.now is not None:
        now = _parse_iso_utc(args.now)
        if now is None:
            print(f"error: --now is not an ISO-8601 date-time: {args.now}", file=sys.stderr)
            return 1
    try:
        data = load_provenance(path)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    result = normalize(data, mtime=mtime, now=now)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-load-provenance",
        description=(
            "Normalize provenance-map.json into deterministic projections "
            "(bounded scan, stack flags, source_root/commit/ref, reexport map, "
            "file-to-library map, export count, generated_at and age)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_norm = sub.add_parser(
        "normalize", help="emit normalized projection JSON from a provenance map"
    )
    p_norm.add_argument("provenance_map", help="path to provenance-map.json")
    p_norm.add_argument(
        "--now",
        help="ISO-8601 date-time that age_days counts to (default: the current time)",
    )
    p_norm.set_defaults(func=_cmd_normalize)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
