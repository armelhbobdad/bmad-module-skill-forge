# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Render Stack Metadata: a stack's export labels, library tiers, pair tiers, metadata.json fields and provenance entries.

create-stack-skill relabels its code-mode export records and sets each
library's tier from them (parallel-extract section 3a), gives each
integration the tier of its pair (detect-integrations section 3), writes the
counted and ranked fields of metadata.json (generate-output section 6) and
writes the code-mode provenance map's entries and integrations from the
records and the extraction bundle (generate-output section 7). This helper holds those rules once, so no step
file restates them, and skf-validate-output.py --skill-type stack recomputes
the dominant tier with dominant_tier here.

Rules:
  Tiers, from the strongest: T1, T1-low, T2, T3.

  library_tier(records)
      A code-mode library is T1 when it has export records and every one
      names extraction_method ast_bridge (an ast-grep rule matched it), and
      T1-low otherwise: one export read by eye, or none recorded at all.

  combine_pair_tier(a, b, mode)
      An integration takes the weaker of its two libraries' tiers, one rule
      in code mode and compose mode: T1 + T1 is T1; T1 + T1-low and
      T1-low + T1-low are T1-low; T1 + T2, T1-low + T2 and T2 + T2 are T2; a
      pair with a T3 member is T3. A T2 member lowers the pair like any
      other tier: its temporal annotations never keep a stronger one.
      `mode` must name a mode, and both modes take this rule.

  dominant_tier(distribution)
      The tier of the largest bin of a confidence_distribution. A tie goes
      to the weaker tier, so the tier never overstates confidence, and a
      distribution with no positive bin (no library) reads T1-low. This is
      the stack's confidence_tier.

  confidence_distribution
      Each library once, in the bin of its tier, so the four bins sum to
      library_count. The evidence report bins the provenance entries
      instead (skf-render-metadata-stats.py).

  source_authority
      The lowest authority among the libraries: official, then community,
      then internal, so a community and an internal library give internal.
      A library that records none counts as community, so a constituent
      without one never lifts a stack to official, and a code-mode stack,
      whose libraries are dependencies rather than skills with an
      authority, is community.

  relabel(records)
      The label check is skf-render-metadata-stats.py's, run beside this
      script on the records as its stack shape: each violation's field
      takes the `expected` value the check gives, never the reverse, and the
      check runs again until it passes. Three violations name no value to
      copy, so the rule here sets one: an unknown or missing
      extraction_method becomes its canonical spelling when it is a known
      method in another case, and source_reading otherwise, since nothing
      shows an ast-grep rule matched it; an ast-grep record with no node
      kind becomes ast_bridge, the stack's name for that tool, which pairs
      with no kind; and a record with no valid signature_source takes T1
      when an ast-grep rule matched it (ast_bridge or ast-grep) and T1-low
      otherwise.

Input (--input <json-file-or-'-'>, where '-' reads stdin):
  {
    "mode": "code" | "compose",
    "libraries": [
      {"name": "<library>",
       "confidence": "T1|T1-low|T2|T3",          # per_library_extractions[].confidence
       "source_authority": "official|community|internal"},   # optional
      ...
    ],
    "integrations": [{"a": "<library>", "b": "<library>"}, ...]   # optional
  }
  Tier, mode and authority tokens compare case-insensitively and are printed
  in their canonical spelling. Each library is named once, and each pair
  names two different libraries of `libraries`, once in either order.

Export records (--records <json-file>, or '-' for library-tiers): the
file parallel-extract section 3a writes and relabels,
  {"entries": [{"source_library": "<library>",
                "extraction_method": "ast_bridge|source_reading", ...}, ...]}
and, for library-tiers, --libraries, the stack's libraries, comma-separated.
Every record names one of them; a library with no record is T1-low.

Subcommands:
  relabel     relabels the records against the label check, rewrites the
              file atomically when a label changed (parallel-extract
              section 3a), and prints each relabeled export and the
              records' label counts (one per record, by signature_source):
                {"relabeled": [{"entry_index": I, "export_name": "<name>",
                                "source_library": "<library>",
                                "changes": [{"field": "<field>",
                                             "from": <old>, "to": <new>}]}, ...],
                 "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
                 "coherence": {"ok": true, "violations": []}}
              A removed ast_node_type shows "to": null.
  library-tiers
              each library's tier, in the order --libraries gives
              (parallel-extract section 3a):
                {"libraries": [{"name": "<library>", "tier": "T1|T1-low",
                                "export_count": N, "ast_bridge_count": M}, ...]}
  pair-tiers  the tier of each integration (detect-integrations section 3):
                {"mode": "<mode>",
                 "integrations": [{"a": "<a>", "b": "<b>", "tier": "<tier>"}, ...]}
  metadata    the computed fields of metadata.json (generate-output section
              6), with the libraries and pairs in the order given:
                {"mode": "<mode>",
                 "library_count": N,
                 "integration_count": M,
                 "libraries": ["<library>", ...],
                 "integration_pairs": [["<a>", "<b>"], ...],
                 "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
                 "confidence_tier": "<dominant tier>",
                 "source_authority": "<authority>",
                 "integrations": [{"a": "<a>", "b": "<b>", "tier": "<tier>"}, ...]}
  provenance  writes a code-mode provenance-map.json to --target atomically
              (generate-output section 7): the object --input holds (the
              map's provenance_version, skill_name, skill_type, source_repo,
              source_commit and generated_at) with `entries` set to the
              records' entries as they stand and `integrations` built from
              the extraction bundle --bundle names, one per pair of its
              `integrations`: libraries [a, b], pattern_type from its type,
              its detection_method, its co_import_files as they stand and
              confidence from its tier. Each replaces the field of that name
              the input holds. It prints
                {"target": "<path>", "entry_count": N, "integration_count": M}

CLI:
  uv run skf-render-stack-metadata.py relabel --records export-records.json
  uv run skf-render-stack-metadata.py library-tiers --records export-records.json --libraries "react,zod"
  uv run skf-render-stack-metadata.py pair-tiers --input -
  uv run skf-render-stack-metadata.py metadata --input stack.json
  uv run skf-render-stack-metadata.py provenance --records export-records.json --bundle extraction-bundle.json --input - --target provenance-map.json

Exit codes:
  0  the JSON is printed (relabel: the records pass the label check)
  1  relabel only: a violation no rule fixes is left; the JSON lists it in
     coherence.violations, and the file holds every label that was fixed
  2  a usage, read, write or input error, or skf-render-metadata-stats.py
     missing beside this script for relabel: one line on stderr, no JSON,
     nothing written
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import math
import os
import re
import secrets
import sys
import time
from pathlib import Path

# Tiers from the strongest to the weakest: T1-low is weaker than T1, T2 than
# T1-low, T3 than T2.
TIERS = ("T1", "T1-low", "T2", "T3")
MODES = ("code", "compose")
# The extraction_method of an export an ast-grep rule matched: the only one
# that keeps a code-mode library at T1.
AST_METHOD = "ast_bridge"
# Authorities from the highest to the lowest.
AUTHORITIES = ("official", "community", "internal")
# The authority of a library that records none.
DEFAULT_AUTHORITY = "community"

# The confidence_distribution bins of metadata.json, from the strongest tier
# to the weakest. dominant_tier reads them in this order and lets a later bin
# win a tie, so a tie resolves toward the weaker tier.
_DISTRIBUTION_BINS = (("t1", "T1"), ("t1_low", "T1-low"), ("t2", "T2"), ("t3", "T3"))

# The tier of a distribution that records no evidence (the conservative default).
_NO_EVIDENCE_TIER = "T1-low"

# The label check relabel runs: skf-render-metadata-stats.py beside this
# script (src/shared/scripts/ and _bmad/skf/shared/scripts/ alike).
_STATS_HELPER = "skf-render-metadata-stats.py"
# The stats helper's shape for a stack's records.
_STATS_SHAPE = "stack"
# The method a record takes when nothing shows an ast-grep rule matched it.
_READ_BY_EYE_METHOD = "source_reading"
# The extraction_method values that name an ast-grep match, and the label a
# record of each kind takes when it has no valid signature_source.
_AST_METHODS = ("ast_bridge", "ast-grep")
# The violation field of a record: provenance.entries[<index>].<field>.
_RECORD_FIELD_RE = re.compile(r"^provenance\.entries\[(\d+)\]\.(\w+)$")
# The `expected` value of an ast-grep record's missing node kind.
_NODE_KIND_EXPECTED = "non-null"
# Relabeling passes before relabel reports what is left: each pass fixes
# every violation it finds, so two or three passes settle every record.
_RELABEL_PASSES = 5
# Windows refuses to replace a file another process holds open, and a virus
# scanner or the search indexer may open a just-written file for a moment:
# _write_atomic retries the rename there for up to this long before failing.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.02


class InputError(ValueError):
    """An input the caller must fix: exit 2 with one line on stderr."""


class WriteError(OSError):
    """A file that could not be written: exit 2 with one line on stderr."""


def _token(value, allowed: tuple[str, ...], what: str) -> str:
    """`value` in its canonical spelling from `allowed`, compared case-insensitively."""
    if isinstance(value, str):
        for token in allowed:
            if value.strip().lower() == token.lower():
                return token
    raise InputError(f"{what} must be one of {', '.join(allowed)}; got {value!r}")


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def library_tier(methods: list[str]) -> str:
    """A code-mode library's tier from the extraction_method of each of its export records.

    T1 when there is at least one record and every one is ast_bridge, T1-low
    otherwise: an export read by eye, or no export recorded, never earns T1.
    """
    return "T1" if methods and all(method == AST_METHOD for method in methods) else "T1-low"


def combine_pair_tier(a: str, b: str, mode: str) -> str:
    """The tier of an integration between a library of tier `a` and one of tier `b`.

    The weaker of the two, in both modes. Raises InputError on an unknown tier
    or mode.
    """
    _token(mode, MODES, "mode")
    return max(_token(a, TIERS, "tier"), _token(b, TIERS, "tier"), key=TIERS.index)


# Keep identical to _bin_count and dominant_tier in skf-enumerate-stack-skills.py
# (test/test-skf-render-stack-metadata.py pins the copies).
def _bin_count(value):
    """A confidence_distribution bin's count: a positive finite number, else 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return value if value > 0 else 0


def dominant_tier(distribution) -> str:
    """The tier of the largest bin of a metadata.json confidence_distribution.

    The bins are read from the strongest tier to the weakest and a later bin
    wins a tie, so a tie resolves toward the weaker tier (T1-low over T1, T2
    over T1-low, T3 over T2) and the tier never overstates confidence. A bin
    counts only when it holds a positive number. T1-low when none does: the
    distribution is absent, not an object or all zero.
    """
    tier, best = _NO_EVIDENCE_TIER, 0
    if isinstance(distribution, dict):
        for key, bin_tier in _DISTRIBUTION_BINS:
            count = _bin_count(distribution.get(key))
            if count and count >= best:
                tier, best = bin_tier, count
    return tier


def library_distribution(tiers: list[str]) -> dict[str, int]:
    """confidence_distribution with each library once, in the bin of its tier."""
    bin_of = {tier: key for key, tier in _DISTRIBUTION_BINS}
    distribution = {key: 0 for key, _ in _DISTRIBUTION_BINS}
    for tier in tiers:
        distribution[bin_of[tier]] += 1
    return distribution


def lowest_authority(authorities: list[str | None]) -> str:
    """The lowest of the authorities, a library that records none (None)
    counting as DEFAULT_AUTHORITY; DEFAULT_AUTHORITY for no library."""
    return max((authority or DEFAULT_AUTHORITY for authority in authorities),
               key=AUTHORITIES.index, default=DEFAULT_AUTHORITY)


# --------------------------------------------------------------------------
# Input and projections
# --------------------------------------------------------------------------


def parse_stack(data) -> tuple[str, list[dict], list[tuple[str, str]]]:
    """(mode, libraries, pairs) from the input JSON. Raises InputError."""
    if not isinstance(data, dict):
        raise InputError(f"the input must be a JSON object; got {type(data).__name__}")
    mode = _token(data.get("mode"), MODES, "mode")

    raw_libraries = data.get("libraries")
    if not isinstance(raw_libraries, list):
        raise InputError("`libraries` must be an array of {name, confidence} objects")
    libraries: list[dict] = []
    tiers: dict[str, str] = {}
    for i, item in enumerate(raw_libraries):
        where = f"libraries[{i}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object with `name` and `confidence`; got {item!r}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{where}.name must be a non-empty string; got {name!r}")
        if name in tiers:
            raise InputError(f"library {name!r} is listed twice")
        tier = _token(item.get("confidence"), TIERS, f"{where}.confidence")
        authority = item.get("source_authority")
        if authority is not None:
            authority = _token(authority, AUTHORITIES, f"{where}.source_authority")
        tiers[name] = tier
        libraries.append({"name": name, "confidence": tier, "source_authority": authority})

    raw_pairs = data.get("integrations", [])
    if not isinstance(raw_pairs, list):
        raise InputError("`integrations` must be an array of {a, b} objects")
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()
    for i, item in enumerate(raw_pairs):
        where = f"integrations[{i}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object with `a` and `b`; got {item!r}")
        a, b = item.get("a"), item.get("b")
        for side, name in (("a", a), ("b", b)):
            if not isinstance(name, str) or name not in tiers:
                raise InputError(f"{where}.{side} {name!r} is not one of the libraries")
        if a == b:
            raise InputError(f"{where} pairs {a!r} with itself")
        key = frozenset((a, b))
        if key in seen:
            raise InputError(f"the pair {a!r} + {b!r} is listed twice")
        seen.add(key)
        pairs.append((a, b))
    return mode, libraries, pairs


def parse_library_names(value: str) -> list[str]:
    """The comma-separated --libraries list, each name once. Raises InputError."""
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names:
        raise InputError("--libraries must name at least one library")
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise InputError(f"library {name!r} is listed twice in --libraries")
        seen.add(name)
    return names


def library_tiers(data, names: list[str]) -> list[dict]:
    """Each library of `names` with its tier and record counts, from the export records.

    `data` is the parsed records file, {"entries": [...]}. Raises InputError
    on a record that names no library, or one --libraries does not list.
    """
    methods: dict[str, list[str]] = {name: [] for name in names}
    for i, record in enumerate(parse_records(data)):
        where = f"entries[{i}]"
        library = record.get("source_library")
        if not isinstance(library, str) or library not in methods:
            raise InputError(f"{where}.source_library {library!r} is not one of --libraries")
        method = record.get("extraction_method")
        methods[library].append(method.strip().lower() if isinstance(method, str) else "")
    return [
        {"name": name, "tier": library_tier(found), "export_count": len(found),
         "ast_bridge_count": sum(method == AST_METHOD for method in found)}
        for name, found in methods.items()
    ]


def parse_records(data) -> list[dict]:
    """The `entries` of an export records file, each an object. Raises InputError."""
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise InputError("the export records must be a JSON object with an `entries` array")
    for i, record in enumerate(data["entries"]):
        if not isinstance(record, dict):
            raise InputError(f"entries[{i}] must be an object; got {record!r}")
    return data["entries"]


# --------------------------------------------------------------------------
# Relabeling
# --------------------------------------------------------------------------


def _load_stats_rules():
    """skf-render-metadata-stats.py beside this script, as a module. Raises ImportError."""
    path = Path(__file__).resolve().parent / _STATS_HELPER
    if not path.is_file():
        raise ImportError(f"{_STATS_HELPER} not found beside {Path(__file__).name}: no label check can run")
    spec = importlib.util.spec_from_file_location("skf_render_metadata_stats_rules", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{_STATS_HELPER} beside {Path(__file__).name} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as exc:
        raise ImportError(f"{_STATS_HELPER} beside {Path(__file__).name} cannot be loaded: {exc}") from exc
    return module


def label_check(stats, entries: list[dict]) -> tuple[dict, dict]:
    """(confidence_distribution, coherence) of the stats helper's stack check on the records."""
    prov = {"entries": entries}
    derived = stats.derive_stats(prov, {}, _STATS_SHAPE)
    return derived["confidence_distribution"], stats.coherence_compute(derived, prov)


def _set(changes: dict, entries: list[dict], index: int, field: str, value) -> None:
    """Set (or, for None on ast_node_type, remove) one field of a record and note the change."""
    record = entries[index]
    old = record.get(field)
    if field == "ast_node_type" and value is None:
        record.pop(field, None)
    else:
        record[field] = value
    changes.setdefault(index, []).append({"field": field, "from": old, "to": value})


def _known_method(value, known: tuple[str, ...]) -> str | None:
    """`value` as a known extraction_method in its canonical spelling, or None."""
    if isinstance(value, str):
        token = value.strip().lower()
        if token in known:
            return token
    return None


def relabel_pass(stats, entries: list[dict], violations: list[dict], changes: dict) -> bool:
    """Apply one fix per violation to the records in place. True when a label changed."""
    changed = False
    for violation in violations:
        field = violation.get("field")
        if field == "confidence_distribution":
            # Records with no valid signature_source: each takes the label its method implies.
            for index, record in enumerate(entries):
                signature = record.get("signature_source")
                if isinstance(signature, str) and signature.strip().upper() in stats._SIG_MAP:
                    continue
                method = _known_method(record.get("extraction_method"), _AST_METHODS)
                _set(changes, entries, index, "signature_source", "T1" if method else "T1-low")
                changed = True
            continue
        match = _RECORD_FIELD_RE.match(field) if isinstance(field, str) else None
        if match is None:
            continue  # no rule for it: it stays in coherence.violations
        index, name = int(match.group(1)), match.group(2)
        expected = violation.get("expected")
        if name == "extraction_method":
            method = _known_method(entries[index].get("extraction_method"), stats._KNOWN_METHODS)
            _set(changes, entries, index, name, method or _READ_BY_EYE_METHOD)
        elif name == "ast_node_type" and expected == _NODE_KIND_EXPECTED:
            _set(changes, entries, index, "extraction_method", _AST_METHODS[0])
        else:
            _set(changes, entries, index, name, expected)
        changed = True
    return changed


def relabel(stats, entries: list[dict]) -> tuple[list[dict], dict, dict]:
    """Relabel the records in place until they pass the label check.

    Returns (relabeled, confidence_distribution, coherence), `relabeled`
    holding each changed record once, in entries[] order, with its changes.
    """
    changes: dict[int, list[dict]] = {}
    for _ in range(_RELABEL_PASSES):
        _distribution, coherence = label_check(stats, entries)
        if coherence["ok"] or not relabel_pass(stats, entries, coherence["violations"], changes):
            break
    distribution, coherence = label_check(stats, entries)
    relabeled = [
        {"entry_index": index, "export_name": entries[index].get("export_name"),
         "source_library": entries[index].get("source_library"), "changes": found}
        for index, found in sorted(changes.items())
    ]
    return relabeled, distribution, coherence


# --------------------------------------------------------------------------
# Provenance map
# --------------------------------------------------------------------------


def bundle_integrations(bundle) -> list[dict]:
    """The provenance map's integrations[] from the extraction bundle's, in its order.

    Each bundle pair {a, b, type, tier, detection_method, co_import_files, ...}
    gives {libraries: [a, b], pattern_type, detection_method, co_import_files,
    confidence}, the co-import files as they stand. Raises InputError on a
    bundle with no `integrations` array or a pair missing one of those fields.
    """
    if not isinstance(bundle, dict) or not isinstance(bundle.get("integrations"), list):
        raise InputError("the extraction bundle must be a JSON object with an `integrations` array")
    out = []
    for i, pair in enumerate(bundle["integrations"]):
        where = f"the bundle's integrations[{i}]"
        if not isinstance(pair, dict):
            raise InputError(f"{where} must be an object; got {pair!r}")
        for key in ("a", "b", "type", "detection_method"):
            if not isinstance(pair.get(key), str) or not pair[key].strip():
                raise InputError(f"{where}.{key} must be a non-empty string; got {pair.get(key)!r}")
        if not isinstance(pair.get("co_import_files"), list):
            raise InputError(f"{where}.co_import_files must be an array; got {pair.get('co_import_files')!r}")
        out.append({
            "libraries": [pair["a"], pair["b"]],
            "pattern_type": pair["type"],
            "detection_method": pair["detection_method"],
            "co_import_files": pair["co_import_files"],
            "confidence": _token(pair.get("tier"), TIERS, f"{where}.tier"),
        })
    return out


def provenance_map(base, entries: list[dict], integrations: list[dict] | None = None) -> dict:
    """The code-mode provenance map: `base` with `entries` set to the records
    and, when given, `integrations` set to the bundle's.

    The entries take the place of any `entries` in `base`, or go before its
    `integrations` (the schema's order), or last; the given integrations
    take the place of any in `base`, or go last. Raises InputError when
    `base` is not an object.
    """
    if not isinstance(base, dict):
        raise InputError(f"the provenance map input must be a JSON object; got {type(base).__name__}")
    fields = dict(base)
    if integrations is not None:
        fields["integrations"] = integrations
    out: dict = {}
    for key, value in fields.items():
        if key == "entries" or (key == "integrations" and "entries" not in fields):
            out["entries"] = entries
            if key == "entries":
                continue
        out[key] = value
    out.setdefault("entries", entries)
    return out


def pair_tiers(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> list[dict]:
    """Each pair with the tier combine_pair_tier gives it."""
    tier = {library["name"]: library["confidence"] for library in libraries}
    return [{"a": a, "b": b, "tier": combine_pair_tier(tier[a], tier[b], mode)} for a, b in pairs]


def stack_metadata(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> dict:
    """The computed fields of a stack's metadata.json."""
    distribution = library_distribution([library["confidence"] for library in libraries])
    return {
        "mode": mode,
        "library_count": len(libraries),
        "integration_count": len(pairs),
        "libraries": [library["name"] for library in libraries],
        "integration_pairs": [[a, b] for a, b in pairs],
        "confidence_distribution": distribution,
        "confidence_tier": dominant_tier(distribution),
        "source_authority": lowest_authority([library["source_authority"] for library in libraries]),
        "integrations": pair_tiers(mode, libraries, pairs),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_input(source: str):
    """The parsed JSON of a file path, or of stdin for '-'. Raises InputError."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read the input {source}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"the input is not valid JSON: {exc}") from exc


def _write_atomic(path: Path, data: dict) -> None:
    """Write `data` as JSON to `path` atomically: a temp file of its own beside
    it, then a rename. Raises WriteError, leaving `path` as it was."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.skf-tmp")
    payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    # O_EXCL: never write into another writer's temp file. O_BINARY (Windows
    # only; 0 elsewhere) keeps the \n line ends.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, flags, 0o644)
    except OSError as exc:
        raise WriteError(f"cannot write {path}: {exc.strerror or exc}") from exc
    try:
        with open(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if not _IS_WINDOWS or time.monotonic() >= deadline:
                    raise
                time.sleep(_REPLACE_POLL_SECONDS)
    except BaseException as exc:
        with contextlib.suppress(OSError):
            tmp.unlink()
        if isinstance(exc, OSError):
            raise WriteError(f"cannot write {path}: {exc.strerror or exc}") from exc
        raise


def _records_file(value: str, command: str, flag: str = "--records") -> str:
    """The path a command reads from a file, never stdin (--records, or --bundle)."""
    if value == "-":
        raise InputError(f"{command} reads {flag} from a file, not stdin")
    return value


def _cmd_relabel(args: argparse.Namespace) -> tuple[dict, int]:
    stats = _load_stats_rules()
    data = _read_input(_records_file(args.records, "relabel"))
    entries = parse_records(data)
    relabeled, distribution, coherence = relabel(stats, entries)
    if relabeled:
        _write_atomic(Path(args.records), data)
    result = {"relabeled": relabeled, "confidence_distribution": distribution, "coherence": coherence}
    return result, 0 if coherence["ok"] else 1


def _cmd_library_tiers(args: argparse.Namespace) -> dict:
    names = parse_library_names(args.libraries)
    return {"libraries": library_tiers(_read_input(args.records), names)}


def _cmd_pair_tiers(args: argparse.Namespace) -> dict:
    mode, libraries, pairs = parse_stack(_read_input(args.input))
    return {"mode": mode, "integrations": pair_tiers(mode, libraries, pairs)}


def _cmd_metadata(args: argparse.Namespace) -> dict:
    return stack_metadata(*parse_stack(_read_input(args.input)))


def _cmd_provenance(args: argparse.Namespace) -> dict:
    entries = parse_records(_read_input(_records_file(args.records, "provenance")))
    integrations = bundle_integrations(_read_input(_records_file(args.bundle, "provenance", "--bundle")))
    target = Path(args.target)
    _write_atomic(target, provenance_map(_read_input(args.input), entries, integrations))
    return {"target": str(target), "entry_count": len(entries), "integration_count": len(integrations)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-render-stack-metadata",
        description=(
            "Relabel a code-mode stack's export records against the label check of "
            "skf-render-metadata-stats.py, compute its library tiers (T1 only when an "
            "ast-grep rule matched every export), its pair tiers (the weaker of the "
            "two libraries' tiers, in both modes) and the counted and ranked fields "
            "of its metadata.json: counts, libraries, integration_pairs, "
            "confidence_distribution (each library once), confidence_tier (the "
            "dominant tier) and source_authority (the lowest, community for a "
            "library that records none), and write its provenance map's entries "
            "and integrations from the records and the extraction bundle."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    text = ("relabel the export records against the label check, rewrite the file when a "
            "label changed, and print the relabeled exports and the label counts as JSON")
    command = sub.add_parser("relabel", help=text, description=text)
    command.add_argument(
        "--records", required=True, help="path to the export records JSON ({entries: [...]}), rewritten in place")
    command.set_defaults(func=_cmd_relabel)
    text = "print each library's tier from its checked export records as JSON"
    command = sub.add_parser("library-tiers", help=text, description=text)
    command.add_argument(
        "--records",
        required=True,
        help="path to the export records JSON ({entries: [...]}), or '-' for stdin",
    )
    command.add_argument(
        "--libraries",
        required=True,
        help="the stack's libraries, comma-separated; a library with no record is T1-low",
    )
    command.set_defaults(func=_cmd_library_tiers)
    for name, func, text in (
        ("pair-tiers", _cmd_pair_tiers, "print the tier of each integration pair as JSON"),
        ("metadata", _cmd_metadata, "print the computed metadata.json fields of the stack as JSON"),
    ):
        command = sub.add_parser(name, help=text, description=text)
        command.add_argument(
            "--input",
            required=True,
            help="path to the stack JSON ({mode, libraries, integrations}), or '-' for stdin",
        )
        command.set_defaults(func=func)
    text = "write the code-mode provenance-map.json with its entries and integrations from the run's files"
    command = sub.add_parser("provenance", help=text, description=text)
    command.add_argument("--records", required=True, help="path to the export records JSON ({entries: [...]})")
    command.add_argument(
        "--bundle", required=True, help="path to the extraction bundle JSON, whose integrations[] the map takes")
    command.add_argument(
        "--input",
        required=True,
        help="path to the map's other fields as JSON (an object), or '-' for stdin",
    )
    command.add_argument("--target", required=True, help="the provenance-map.json to write")
    command.set_defaults(func=_cmd_provenance)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except (InputError, ImportError, WriteError) as exc:
        print(f"error: {' '.join(str(exc).split())}", file=sys.stderr)
        return 2
    result, code = result if isinstance(result, tuple) else (result, 0)
    # ASCII escapes: a Windows console's code page cannot encode every name.
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure the standard streams to UTF-8, keeping each one's error handler.

    A Windows console pipes them as cp1252, which cannot carry every character
    a library name or an error message may hold. stdin is reconfigured before
    its first read, so `--input -` reads the UTF-8 JSON a step pipes.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
