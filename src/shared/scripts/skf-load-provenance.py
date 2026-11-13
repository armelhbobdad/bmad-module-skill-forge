# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
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
no comparisons. `normalize` reads one JSON, emits one JSON; `baseline` reads
the skill's metadata.json, its brief and its map.

The module's top level imports only the standard library, since
skf-extraction-snapshot.py loads it beside itself; `baseline` loads
skf-resolve-authoritative-files.py (and with it PyYAML, which the PEP 723
header above declares) only to read a brief that exists.

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

  baseline --metadata <metadata.json> --current-tier <tier> [--brief <skill-brief.yaml>]
           [--provenance-map <map.json>] [--now <ISO-8601>]
      The facts audit-skill init.md §3 and §7 route on (#1132). Emit JSON:
        {
          "original_tier": "<Quick|Forge|Forge+|Deep or null>",
          "scope_type": "<scope type or null>",
          "scope_type_source": "metadata" | "brief" | null,
          "brief_error": "<why an existing brief could not be read, or null>",
          "docs_only_skill": <bool>,
          "no_baseline": "no-doc-hashes" | "no-provenance-map" | null,
          "compose_mode_stack": <bool or null>,
          "provenance_age_days": <int or null>,
          "tier_dropped": <bool>,
          "baseline_old": <bool>
        }

      - `original_tier`, the tier the skill was compiled at: metadata.json's
        `forge_tier` when it is one of Quick, Forge, Forge+, Deep (a stack
        records it there), else its `confidence_tier` when it is one (a
        single skill records it there), else null.
      - `scope_type`: metadata.json's `scope_type` (source "metadata"), else,
        only then, the `scope.type` of the --brief file when it exists and
        names one (source "brief"), else null. A brief that exists but
        cannot be read, is not YAML or is not a mapping sets `brief_error`
        and gives no scope type; an SKF 1.x brief's trailing `---` reads.
      - `docs_only_skill`: metadata.json's `scope_type`, or the
        `source_type` an older one records, is `docs-only`. The brief never
        makes a skill docs-only.
      - `no_baseline`: "no-doc-hashes" for a docs-only skill whose
        `doc_sources` is missing, not a list, or holds no entry with a
        `content_hash`; "no-provenance-map" for any other skill when
        --provenance-map is absent or empty; else null.
      - `compose_mode_stack` and `provenance_age_days` are the
        `compose_mode_stack` and `age_days` that `normalize` gives for the
        map; both are null when the map is not read: a docs-only skill never
        reads it, and a skill without one has none.
      - `tier_dropped`: the map was read, the skill is no compose-mode
        stack, `original_tier` is set, and --current-tier comes before it
        in the order Quick, Forge, Forge+, Deep.
      - `baseline_old`: `provenance_age_days` is above 90.

CLI examples:
  uv run skf-load-provenance.py normalize /path/to/provenance-map.json
  uv run skf-load-provenance.py normalize /path/to/provenance-map.json --now 2026-05-01T00:00:00Z
  uv run skf-load-provenance.py baseline --metadata /path/to/metadata.json --current-tier Forge \\
      --brief /path/to/skill-brief.yaml --provenance-map /path/to/provenance-map.json

Exit codes:
  0  normalization succeeded (including an empty, well-formed map with no
     entries, which emits all-defaults JSON), or the baseline facts were read
  1  user error (file not found, malformed JSON, structurally invalid map;
     for `baseline`, a metadata.json or map that is missing, cannot be
     read or is not a JSON object, or a --now that is not ISO-8601)
"""

from __future__ import annotations

import argparse
import importlib.util
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
# Baseline facts (audit-skill init.md §3 and §7)
# --------------------------------------------------------------------------


VALID_TIERS = ("Quick", "Forge", "Forge+", "Deep")
# A provenance map older than this many days is a doubt init.md §7 stops on.
BASELINE_MAX_AGE_DAYS = 90
DOCS_ONLY = "docs-only"

_RESOLVER = None


def _resolver():
    """skf-resolve-authoritative-files.py from this folder, loaded once: its
    parse_brief_yaml reads a brief's YAML, an SKF 1.x brief's trailing `---`
    included. Raises ValueError when it cannot be loaded (PyYAML missing,
    for one)."""
    global _RESOLVER
    if _RESOLVER is None:
        path = Path(__file__).resolve().parent / "skf-resolve-authoritative-files.py"
        spec = importlib.util.spec_from_file_location("skf_resolve_authoritative_files", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load {path.name} beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError) as exc:
            raise ValueError(f"cannot load {path.name} beside {Path(__file__).name}: {exc}") from exc
        _RESOLVER = module
    return _RESOLVER


def _load_json_object(path: Path, label: str) -> dict:
    """The JSON object at `path`. Raises ValueError when it is missing, cannot
    be read or parsed, or is not an object."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"failed to read {label} {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} {path} must be a JSON object at top level; got {type(data).__name__}")
    return data


def brief_scope_type(brief_path: Path) -> tuple[str | None, str | None]:
    """(the brief's `scope.type`, None), or (None, why the brief could not be read).

    The caller passes a brief that exists. One that names no scope type
    gives (None, None).
    """
    try:
        resolver = _resolver()
    except ValueError as exc:
        return None, str(exc)
    try:
        text = brief_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return None, f"cannot read brief at {brief_path}: {exc}"
    try:
        brief = resolver.parse_brief_yaml(text)
    except resolver.yaml.YAMLError as exc:
        return None, f"brief at {brief_path} is not valid YAML: {' '.join(str(exc).split())}"
    if not isinstance(brief, dict):
        return None, f"brief at {brief_path} must be a YAML mapping; got {type(brief).__name__}"
    scope = brief.get("scope")
    value = scope.get("type") if isinstance(scope, dict) else None
    return (value if isinstance(value, str) and value else None), None


def _has_doc_hash(metadata: dict) -> bool:
    """Whether an entry of `doc_sources` records a `content_hash`."""
    sources = metadata.get("doc_sources")
    if not isinstance(sources, list):
        return False
    return any(isinstance(entry, dict) and isinstance(entry.get("content_hash"), str)
               and entry["content_hash"] for entry in sources)


def original_tier(metadata: dict) -> str | None:
    """The tier the skill was compiled at: `forge_tier`, else `confidence_tier`, when it is a tier."""
    for key in ("forge_tier", "confidence_tier"):
        if metadata.get(key) in VALID_TIERS:
            return metadata[key]
    return None


def baseline(
    metadata: dict,
    current_tier: str,
    brief_path: Path | None = None,
    provenance_path: Path | None = None,
    now: datetime | None = None,
) -> dict:
    """The baseline facts audit-skill init.md §3 and §7 route on.

    Raises ValueError for a map that is missing, unreadable or not a JSON
    object; a docs-only skill never reads its map.
    """
    compiled = original_tier(metadata)
    scope_type, source, brief_error = None, None, None
    if isinstance(metadata.get("scope_type"), str) and metadata["scope_type"]:
        scope_type, source = metadata["scope_type"], "metadata"
    elif brief_path is not None and brief_path.exists():
        scope_type, brief_error = brief_scope_type(brief_path)
        source = "brief" if scope_type is not None else None
    docs_only = DOCS_ONLY in (metadata.get("scope_type"), metadata.get("source_type"))
    no_baseline, compose, age_days = None, None, None
    if docs_only:
        if not _has_doc_hash(metadata):
            no_baseline = "no-doc-hashes"
    elif provenance_path is None:
        no_baseline = "no-provenance-map"
    else:
        data = _load_json_object(provenance_path, "provenance map")
        try:
            mtime = datetime.fromtimestamp(provenance_path.stat().st_mtime, timezone.utc)
        except OSError as exc:
            raise ValueError(f"failed to read provenance map {provenance_path}: {exc}") from exc
        projection = normalize(data, mtime, now)
        compose, age_days = projection["compose_mode_stack"], projection["age_days"]
    tier_dropped = (compose is False and compiled is not None
                    and VALID_TIERS.index(current_tier) < VALID_TIERS.index(compiled))
    return {
        "original_tier": compiled,
        "scope_type": scope_type,
        "scope_type_source": source,
        "brief_error": brief_error,
        "docs_only_skill": docs_only,
        "no_baseline": no_baseline,
        "compose_mode_stack": compose,
        "provenance_age_days": age_days,
        "tier_dropped": tier_dropped,
        "baseline_old": age_days is not None and age_days > BASELINE_MAX_AGE_DAYS,
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


def _cmd_baseline(args: argparse.Namespace) -> int:
    now = None
    if args.now is not None:
        now = _parse_iso_utc(args.now)
        if now is None:
            print(f"error: --now is not an ISO-8601 date-time: {args.now}", file=sys.stderr)
            return 1
    try:
        metadata = _load_json_object(Path(args.metadata), "metadata.json")
        result = baseline(
            metadata,
            args.current_tier,
            Path(args.brief) if args.brief else None,
            Path(args.provenance_map) if args.provenance_map else None,
            now,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-load-provenance",
        description=(
            "Normalize provenance-map.json into deterministic projections "
            "(bounded scan, stack flags, source_root/commit/ref, reexport map, "
            "file-to-library map, export count, generated_at and age), or read "
            "the baseline facts audit-skill routes on."
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
    p_base = sub.add_parser(
        "baseline",
        help="emit the baseline facts audit-skill init routes on (compile tier, "
             "scope type, docs-only, no-baseline reason, tier drop, baseline age)",
    )
    p_base.add_argument("--metadata", required=True, help="path to the skill's metadata.json")
    p_base.add_argument(
        "--current-tier", required=True, choices=VALID_TIERS,
        help="the tier this run works at, compared with the compile tier",
    )
    p_base.add_argument(
        "--brief",
        help="path to the skill's skill-brief.yaml, read for scope.type only when "
             "metadata.json records no scope_type and the file exists",
    )
    p_base.add_argument(
        "--provenance-map",
        help="path to the skill's provenance-map.json; absent or empty means no map",
    )
    p_base.add_argument(
        "--now",
        help="ISO-8601 date-time that the map's age counts to (default: the current time)",
    )
    p_base.set_defaults(func=_cmd_baseline)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
