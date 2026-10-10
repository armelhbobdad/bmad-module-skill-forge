#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Structural Diff: deterministic comparison of skill export inventories.

Compares a baseline export inventory against a current export inventory and
produces a structured JSON diff showing added, removed, changed, and moved
entries. Used by audit-skill (structural-diff step, references/structural-diff.md
section 1) to replace LLM-based, token-spending inventory comparison: the LLM
can silently drop or mis-match entries when diffing dozens/hundreds of exports
by hand.

CLI:
  python3 skf-structural-diff.py baseline.json current.json
  python3 skf-structural-diff.py baseline.json current.json -o diff-result.json
  python3 skf-structural-diff.py provenance-map.json snapshot.json --reexport-map map.json
  python3 skf-structural-diff.py provenance-map.json snapshot.json --group-by source_library
  python3 skf-structural-diff.py provenance-map.json snapshot.json --files category-a.json
  python3 skf-structural-diff.py provenance-map.json extraction.json --current-extra details.json

Input:
  Two JSON files. Each file may be either:
    - An object with an "exports" array   (extraction-snapshot format)
    - An object with an "entries" array    (provenance-map.json format)
    - A plain array of export entries
    - A name-keyed object of entry objects

  Field-name aliasing (provenance-map entries[] vs extraction-snapshot
  exports[]) is handled transparently, so the two sides may use different
  shapes:
    - name        <- name        | export_name
    - type        <- type        | export_type
    - file        <- file        | source_file
    - line        <- line        | source_line
    - signature   <- signature
    - params      <- params        (a provenance map's parameter list)
    - return_type <- return_type
    - confidence  <- confidence
    - extraction_method <- extraction_method

  Nameless entries are skipped. ast_node_type is ignored on purpose: it
  describes the tool's match, not the export, and a relabel changes it along
  with confidence.

Matching:
  An export is identified by its name and its file together, so two exports
  that share a name (a `GET` handler in each of two route files, two `parse`
  functions) are never taken for one another, whatever order the inventories
  list them in. The file is compared stripped, with backslashes read as
  forward slashes and no leading `./`, so a path written on Windows or with
  a `./` prefix names the same file as the plain one; every list emits the
  file as the inventory wrote it. One side listing the same name twice in
  one file (overload signatures, a definition in both branches of an `if`)
  keeps the entry on the first line, as the AST Extraction Protocol
  deduplicates.

  An entry left on one side only is paired with one left on the other side
  as a move when its name occurs exactly once in each inventory. When the
  name occurs more than once on either side, the leftover entries cannot be
  paired by name alone: they stay in removed[] and added[], and the name is
  listed in ambiguous_names[] with the files on each side, for a reviewer
  to judge.

Public surface:
  A current entry may carry `public`, true or false: the mark
  skf-extraction-snapshot.py build --scope-type public-api gives each
  export by the public-surface rule a public-api skill's provenance map is
  kept to. After the pairing above, a current entry marked false that
  pairs with none (no baseline entry of its name and file, and no move)
  goes to not_public[], not added[]: create-skill and update-skill never
  document an export off the surface, so it is no drift. One whose name is
  in ambiguous_names[] stays in added[], where a reviewer pairs it. A
  matched or moved entry is compared whatever its mark, so a baseline
  entry off the surface is never reported removed. An entry with no mark
  (any other scope type, a family with no barrel, an older snapshot) is
  added as before. not_public[] never counts toward the exit code.

File scope (--files FILE):
  For a caller that re-extracted only the files that changed (update-skill's
  Category B), --files limits the diff to the exports of the files FILE
  names: a JSON array of paths, or the output of skf-classify-changed-files.py
  classify, which names category_a's modified, added and deleted files and
  both paths of each moved_files item. A path compares in the form an
  export's file does (see Matching). An export of any other file is taken as
  unchanged on both sides: it enters no list and no count, and its name
  still counts when a move needs a name unique on both sides, so the scoped
  diff pairs the moves a diff of the whole inventories would. The current
  inventory must hold the exports of every named file the source still has,
  or they read as removed.

Extra current entries (--current-extra FILE):
  For a caller that adds to a recipe runner's output what the recipes do
  not record (update-skill's Category B: each export's params and
  return_type, read at its line, and the exports read by eye), FILE is an
  inventory in any input format above, merged into the current one before
  the diff: an entry with the name and file of a current entry fills each
  field that entry lacks (null or absent), and any other entry is added as
  an export of its own. Names and files compare as written, the file in the
  form Matching describes.

Canonicalization (applied symmetrically to BOTH sides before matching):
  The baseline extractor (skf-create-skill) and the re-extractor (audit step 2)
  can differ in cosmetic detail that would otherwise surface as false-positive
  "Changed"/"Removed"/"Added" entries. These deterministic transforms collapse
  the cosmetic differences:
    - quote-style          : normalize string-literal quotes in signatures
                             (double -> single), so `= "Hnsw"` == `= 'Hnsw'`.
    - stdlib-prefix        : strip module prefixes on well-known stdlib helpers
                             (typing., dataclasses., collections[.abc]., enum.),
                             so `typing.Optional[int]` == `Optional[int]`.
                             User-defined namespaces (e.g. `pkg.typing.X`) are
                             NOT collapsed.
    - reexport-resolution  : rewrite internal symbol names to their public
                             re-export name via the reexport map, so a renamed
                             public re-export (`_Impl` -> `Public`) matches the
                             baseline entry instead of showing up as
                             Removed `_Impl` + Added `Public`.

  The reexport map is taken from --reexport-map when provided; otherwise it is
  derived from the baseline provenance map itself (top-level `reexport_map`
  plus any per-entry `reexported_as`), the same projection produced by
  `skf-load-provenance.py normalize`.

  params (each parameter) and return_type are canonicalized the same way as
  a signature. A parameter the recipe runner records as {name, type,
  default, optional} is first written in the provenance map's form
  (skf-extraction-inventory.py typed_param: `name: type`, `name?: type`,
  ` = default`), so a runner's export compares with the map's entry.

Change detection:
  The diffed fields are type (compared through export-type, below),
  signature, params, return_type and line. A field is only compared when
  present (non-null) on BOTH sides: a field absent on one side means
  "insufficient data", never an asserted change.
  This avoids false positives when the two inventories carry different
  metadata. The line of a moved export is not compared: a move changes it.

  export-type: no record is rewritten, but when a matched export's two
  types differ, a semantic kind a by-eye read records is the base kind
  the recipe runner records for the same declaration when the base-kind
  side's canonical signature shows that form: `async_function` is
  `function` for an `async def`, `async function`, `async fn` or
  `async unsafe fn`, or a `const`, `let` or `var` bound to an `async`
  arrow or function (after `export`, `default`, `declare` or `pub`);
  `decorator` is `function` for a Python `def` or `async def`; `enum` is
  `class` for a Python class with a stdlib `Enum`, `IntEnum`, `StrEnum`,
  `ReprEnum`, `Flag` or `IntFlag` base. Either side may hold the by-eye
  kind; with no signature on the base-kind side the types differ. Each
  export whose types it takes as one counts once as `export-type` in
  applied_transforms.

  A signature has two parts, the parameters and the return type. A side
  carries the parameters as params or in its signature, and the return
  type as return_type or in its signature. When both sides carry a part
  but no field holds it on both (a provenance map's params and return_type
  against a snapshot's signature text), that part is never compared, and
  the export is listed in signature_unverified[]: a change there cannot be
  seen, so a diff that finds nothing does not pass for a verified one.

Provenance labels:
  confidence and extraction_method describe the tool that extracted an export,
  not the source, so a difference in them is not drift. For an export matched
  on both sides, a label that differs (compared case-insensitively after trimming,
  and only when both sides have a value) is reported once per export in
  label_changes[]. A blank label counts as no value and is emitted as null.
  The stack spellings of extraction_method compare equal to the library ones
  (ast_bridge = ast-grep, source_reading = source-read); emitted values keep
  the spelling each side wrote. Label changes never enter changed[], never
  make an export count as changed, and never affect the exit code.

Output:
  JSON object:
    summary:            { added, removed, changed, moved, unchanged,
                          label_changes, ambiguous_names,
                          signature_unverified, not_public }
    added:              list of entries present in current but not baseline
    removed:            list of entries present in baseline but not current
    changed:            list of { name, field, baseline_value, current_value,
                        file, line, confidence } where field is type,
                        signature, params, return_type or line, and file,
                        line and confidence are the export's current ones
    moved:              list of { name, previous_file, current_file,
                        previous_line, line, confidence }
    ambiguous_names:    list of { name, removed: [{file, line}], added:
                        [{file, line}] }: a name left on both sides that
                        occurs more than once on a side, so its entries stay
                        in removed[] and added[] unpaired
    label_changes:      list of { name, file, baseline: {confidence,
                        extraction_method}, current: {confidence,
                        extraction_method} }; informational, not drift
    signature_unverified: list of { name, file, baseline, current }: a
                        matched export with a signature part no field
                        holds on both sides (see Change detection);
                        baseline and current list which of signature,
                        params and return_type each side carries.
                        Informational: never a change, never in the exit
                        code
    not_public:         list of current entries marked `public: false`
                        that pair with no baseline entry and whose name is
                        not ambiguous (see Public surface): exports off a
                        public-api skill's public surface, left out of
                        added[]. Not drift, never in the exit code
    unchanged_count:    number of entries that matched with no field change
                        (a label change or an unverified signature alone
                        leaves an entry unchanged)
    applied_transforms: list of { transform, count }: which canonicalization
                        transforms, and the export-type comparison,
                        actually fired and how many values each touched
                        (export-type: how many exports; empty when none
                        fired). Surfaced by audit
                        step 6's Provenance section so a reviewer can tell
                        which differences the diff collapsed.

  added[], removed[] and not_public[] hold normalized records: name, type,
  signature, params, return_type, file, line, confidence and
  extraction_method, and `public` when the entry carries a true or false
  mark (see Public surface).

  With --group-by source_library, each side is split by its entries'
  source_library (a stack's libraries; an entry without one falls in a
  null group, diffed against the other side's) and each group is diffed on
  its own, so an export never matches one of another library. The lists
  above then hold every group's items, each tagged with its source_library,
  the summary sums the groups, and two keys are added:
    group_by:           "source_library"
    groups:             list of { source_library, summary }, one per group
  An inventory whose entries all lack a source_library is an error when
  the other inventory's entries have one: its every export would land in
  the null group and read as added or removed.

  With --files, one key is added:
    file_scope:         { files, baseline_left_out, current_left_out }: the
                        paths FILE names, and the exports of each inventory
                        left out as outside them

  With -o, the JSON is written to the file and stdout gets one line:
  { status: "ok", output: <file>, summary: {...} }.

Exit codes:
  0  no export added, removed, changed or moved
  1  differences found
  2  error: an input that cannot be read or parsed, a --files file that is
     neither a path list nor a classify output, --group-by over an
     inventory whose entries all lack the field while the other's have it,
     an output that cannot be written, or a usage error ({status: "error",
     error} on stdout, or argparse's usage on stderr)
  Label differences (label_changes), unverified signatures
  (signature_unverified) and exports off the public surface (not_public) do
  not count toward the exit code.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import re
import sys
from pathlib import Path

_INVENTORY = None


def _typed_params(params: object, language: object) -> object:
    """A recipe runner's {name, type, default, optional} parameters in the provenance map's typed form, through
    skf-extraction-inventory.py's typed_param (loaded once from this folder); any other value as it is."""
    global _INVENTORY
    if not isinstance(params, list) or not any(isinstance(p, dict) for p in params):
        return params
    if _INVENTORY is None:
        path = Path(__file__).resolve().parent / "skf-extraction-inventory.py"
        spec = importlib.util.spec_from_file_location("skf_extraction_inventory", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        _INVENTORY = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_INVENTORY)
    lang = language if isinstance(language, str) else None
    return [s for s in (_INVENTORY.typed_param(p, lang) for p in params) if s is not None]


# Fields compared for change detection (in order).
# "name" and "file" identify the export and are not diffed as fields; a file
# change is tracked separately in the "moved" list.
# Provenance labels are excluded too: they say which tool extracted the export,
# so a relabel is reported in label_changes[] and is never drift.
# params and return_type are the provenance map's form of a signature.
DIFF_FIELDS = ["type", "signature", "params", "return_type", "line"]

# The fields that hold a signature, and for each of its two parts (the
# parameters, the return type) the fields that hold that part: a signature
# string holds both.
SIGNATURE_FIELDS = ("signature", "params", "return_type")
SIGNATURE_PARTS = (("params", "signature"), ("return_type", "signature"))

# The one --group-by field: a stack's per-library split.
GROUP_FIELDS = ["source_library"]

# Provenance labels compared for the informational label_changes[] list.
LABEL_FIELDS = ["confidence", "extraction_method"]

# Stack provenance maps spell extraction_method differently from library maps
# and the audit re-index; compare them as the same tool.
_METHOD_ALIASES = {"ast_bridge": "ast-grep", "source_reading": "source-read"}

# Well-known stdlib module prefixes whose unqualified form is importable at
# the call site. Longer prefixes must precede their own containing prefix
# (collections.abc before collections) so the alternation strips the longest.
# The negative lookbehind `(?<![\w.])` ensures we only strip a top-level module
# reference, never a user-defined namespace such as `pkg.typing.Foo`.
_STDLIB_PREFIX_RE = re.compile(
    r"(?<![\w.])(?:typing|dataclasses|collections\.abc|collections|enum)\."
)

# export-type: a semantic kind a by-eye read records, against the base kind
# the recipe runner records for the same declaration, names one kind when
# the base-kind side's canonical signature shows that form. Any other pair
# of types, or a base-kind side with no signature, is compared as written.
# An async form: `async def`, `async function`, `async fn` or `async unsafe
# fn`, or a `const` / `let` / `var` bound to an `async` arrow or function
# (`export const add = async (x) => x;`), after any `export`, `default`,
# `declare` or `pub` modifier.
_ASYNC_FORM_RE = re.compile(
    r"^\s*(?:(?:export|default|declare|pub(?:\s*\([^()]*\))?)\s+)*"
    r"(?:async\s+(?:unsafe\s+)?(?:def|function|fn)\b"
    r"|(?:const|let|var)\s+[\w$]+\s*(?::(?:[^=]|=>)*)?=\s*async\b)"
)
_DEF_FORM_RE = re.compile(r"^\s*(?:async\s+)?def\s")
_CLASS_BASES_RE = re.compile(r"^\s*class\s+\w+\s*\(([^()]*)\)")
_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "ReprEnum", "Flag", "IntFlag"})


def _enum_class_form(signature: str) -> bool:
    """True when a Python class declaration lists a stdlib enum base."""
    m = _CLASS_BASES_RE.match(signature)
    return m is not None and any(base.strip() in _ENUM_BASES for base in m.group(1).split(","))


# (by-eye kind, base kind) -> the test of the base-kind side's signature.
EXPORT_TYPE_FORMS = {
    ("async_function", "function"): lambda signature: _ASYNC_FORM_RE.match(signature) is not None,
    ("decorator", "function"): lambda signature: _DEF_FORM_RE.match(signature) is not None,
    ("enum", "class"): _enum_class_form,
}


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_json(path: Path) -> tuple[object, str | None]:
    """Read and parse a JSON file. Returns (data, error_message)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"Cannot read file '{path}': {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON in '{path}': {exc}"


def entries_from_data(data: object, source: str = "") -> tuple[list[dict], str | None]:
    """Extract the export-entry list from an already-parsed inventory.

    Accepts:
      - [...]                 (plain array)
      - {"exports": [...]}    (extraction-snapshot format)
      - {"entries": [...]}    (provenance-map.json format)
      - {name: {...}, ...}    (name-keyed object of entry objects)

    Returns (entries, error_message).
    """
    where = f" in '{source}'" if source else ""
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        if isinstance(data.get("exports"), list):
            return data["exports"], None
        if isinstance(data.get("entries"), list):
            return data["entries"], None
        # A plain name-keyed object of entries (some inventory formats).
        values = list(data.values())
        if values and all(isinstance(v, dict) for v in values):
            return values, None
        return [], (
            f"Unrecognised inventory format{where}: expected array or object "
            f"with an 'exports' or 'entries' key"
        )
    return [], f"Unrecognised inventory format{where}: top-level value must be array or object"


def load_inventory(path: Path) -> tuple[list[dict], str | None]:
    """Load an export inventory from a JSON file (thin wrapper, back-compat).

    Returns (exports, error_message).
    """
    data, err = load_json(path)
    if err:
        return [], err
    return entries_from_data(data, str(path))


# The keys one field may be written under (see Input): an entry lacks the
# field only when it has none of them.
_ALIAS_GROUPS = {
    key: group
    for group in (("name", "export_name"), ("type", "export_type"), ("file", "source_file"),
                  ("line", "source_line"))
    for key in group
}


def merge_extra(entries: list[dict], extra: list[dict]) -> list[dict]:
    """The current entries with --current-extra's merged in by name and file:
    an extra entry fills each field the entry of its name and file lacks,
    and one with no such entry is added.

    >>> merge_extra([{"export_name": "f", "source_file": "a.py", "source_line": 3}],
    ...             [{"export_name": "f", "source_file": "./a.py", "params": ["x: int"]},
    ...              {"name": "g", "file": "a.py", "line": 9}])
    [{'export_name': 'f', 'source_file': 'a.py', 'source_line': 3, 'params': ['x: int']}, {'name': 'g', 'file': 'a.py', 'line': 9}]
    """
    merged = [dict(entry) if isinstance(entry, dict) else entry for entry in entries]
    by_key: dict[tuple, dict] = {}
    for entry in merged:
        if isinstance(entry, dict):
            name = _first(entry, "name", "export_name")
            if isinstance(name, str):
                by_key.setdefault((name.strip(), _file_key(_first(entry, "file", "source_file"))), entry)
    for item in extra:
        if not isinstance(item, dict):
            continue
        name = _first(item, "name", "export_name")
        target = by_key.get((name.strip(), _file_key(_first(item, "file", "source_file")))) \
            if isinstance(name, str) else None
        if target is None:
            merged.append(dict(item))
            continue
        for field, value in item.items():
            if value is not None and all(target.get(key) is None for key in _ALIAS_GROUPS.get(field, (field,))):
                target[field] = value
    return merged


def files_from_data(data: object, source: str = "") -> tuple[list[str], str | None]:
    """The paths of a --files file, already parsed.

    Accepts:
      - [...]                 (a JSON array of paths)
      - {"category_a": {...}} (skf-classify-changed-files.py classify output:
                               category_a's modified, added and deleted
                               paths, and both paths of each moved_files item)

    Returns (paths, error_message).
    """
    where = f" in '{source}'" if source else ""
    if isinstance(data, list):
        if all(isinstance(path, str) for path in data):
            return data, None
        return [], f"--files list{where} must hold only path strings"
    if not isinstance(data, dict) or not isinstance(data.get("category_a"), dict):
        return [], (
            f"Unrecognised --files format{where}: expected an array of paths or "
            f"the output of skf-classify-changed-files.py classify"
        )
    paths: list[str] = []
    for key in ("modified", "added", "deleted"):
        listed = data["category_a"].get(key, [])
        if not isinstance(listed, list) or not all(isinstance(path, str) for path in listed):
            return [], f"--files category_a.{key}{where} must be a list of paths"
        paths.extend(listed)
    moves = data.get("moved_files", [])
    if not isinstance(moves, list) or not all(isinstance(move, dict) for move in moves):
        return [], f"--files moved_files{where} must be a list of {{old_path, new_path}} objects"
    for move in moves:
        paths.extend(move[key] for key in ("old_path", "new_path") if isinstance(move.get(key), str))
    return paths, None


# --------------------------------------------------------------------------
# Re-export map
# --------------------------------------------------------------------------


def extract_reexport_map(data: object) -> dict[str, str]:
    """Derive the {internal -> public} re-export map from a provenance map.

    Mirrors skf-load-provenance.extract_reexport_map:
      1. top-level `reexport_map` object, plus
      2. per-entry `reexported_as` on `entries[]` items
         ({"export_name": "_Impl", "reexported_as": "Public"}).
    Non-string keys/values are skipped. Returns {} for non-dict input.
    """
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
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
                out.setdefault(internal, public)
    return out


def load_reexport_map(path: Path) -> tuple[dict[str, str], str | None]:
    """Load an explicit re-export map file.

    Accepts either a plain {internal: public} object or the full
    `skf-load-provenance.py normalize` output (which nests it under the
    `reexport_map` key). Non-string pairs are skipped.
    """
    data, err = load_json(path)
    if err:
        return {}, err
    if not isinstance(data, dict):
        return {}, f"reexport map '{path}' must be a JSON object"
    src = data["reexport_map"] if isinstance(data.get("reexport_map"), dict) else data
    return {k: v for k, v in src.items() if isinstance(k, str) and isinstance(v, str)}, None


# --------------------------------------------------------------------------
# Canonicalization
# --------------------------------------------------------------------------


def _first(entry: dict, *keys: str) -> object:
    """First non-null value among the given keys (field-name aliasing)."""
    for k in keys:
        v = entry.get(k)
        if v is not None:
            return v
    return None


def canon_signature(sig: object) -> tuple[object, set[str]]:
    """Canonicalize a signature string. Returns (canonical, transforms_fired).

    Non-string input passes through unchanged (empty transform set).
    """
    if not isinstance(sig, str):
        return sig, set()
    applied: set[str] = set()
    out = sig
    if '"' in out:
        out = out.replace('"', "'")
        applied.add("quote-style")
    stripped = _STDLIB_PREFIX_RE.sub("", out)
    if stripped != out:
        applied.add("stdlib-prefix")
        out = stripped
    return out, applied


def _canon_value(value: object, transform_counts: collections.Counter) -> object:
    """Canonicalize a signature, a return type or each item of a parameter list."""
    if isinstance(value, list):
        return [_canon_value(item, transform_counts) for item in value]
    canon, fired = canon_signature(value)
    for t in fired:
        transform_counts[t] += 1
    return canon


def _is_line(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _file_key(file: object) -> str | None:
    """The file half of an export's key: stripped, forward slashes, no
    leading `./` (normalize_rel_path of skf-resolve-authoritative-files.py),
    or None when the entry names no file."""
    if not isinstance(file, str):
        return None
    path = file.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path or None


def _normalize_entries(
    entries: list[dict],
    reexport_map: dict[str, str],
    transform_counts: collections.Counter,
) -> dict[tuple, dict]:
    """Build a dict of canonicalized records keyed by (name, file).

    Applies field-name aliasing, signature canonicalization, and re-export
    name resolution. Accumulates fired-transform counts into transform_counts.
    Nameless entries are skipped. The key holds the file in _file_key's form;
    the record keeps it as written. When one (name, file) repeats, the entry
    on the first line wins, whatever order the inventory lists them in (an
    entry with no line only wins when no other has one).
    """
    result: dict[tuple, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_name = _first(entry, "name", "export_name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name = raw_name.strip()
        resolved = reexport_map.get(name, name)
        if resolved != name:
            transform_counts["reexport-resolution"] += 1
            name = resolved

        # Normalized record: also the public entry shape emitted in
        # added[]/removed[], so both sides render into one consistent table
        # regardless of the input shape they came from.
        record = {
            "name": name,
            "type": _first(entry, "type", "export_type"),
            "signature": _canon_value(entry.get("signature"), transform_counts),
            "params": _canon_value(_typed_params(entry.get("params"), entry.get("language")), transform_counts),
            "return_type": _canon_value(entry.get("return_type"), transform_counts),
            "file": _first(entry, "file", "source_file"),
            "line": _first(entry, "line", "source_line"),
            "confidence": entry.get("confidence"),
            "extraction_method": entry.get("extraction_method"),
        }
        # The snapshot's public-surface mark, kept only when it is one, so an
        # unmarked inventory's records are as before.
        if isinstance(entry.get("public"), bool):
            record["public"] = entry["public"]
        key = (name, _file_key(record["file"]))
        kept = result.get(key)
        if kept is not None and not (
            _is_line(record["line"]) and (not _is_line(kept["line"]) or record["line"] < kept["line"])
        ):
            continue
        result[key] = record
    return result


def _label_key(field: str, value: object) -> object:
    """Comparison key for a provenance label, or None when the side has no value.

    Strings compare case-insensitively after trimming; a blank string counts
    as no value. Stack extraction_method spellings map to the library ones.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().casefold()
        if not value:
            return None
        if field == "extraction_method":
            value = _METHOD_ALIASES.get(value, value)
    return value


def _label_side(rec: dict) -> dict:
    """One side's labels as emitted: the value as written, or null when blank."""
    return {
        k: (rec.get(k) if _label_key(k, rec.get(k)) is not None else None)
        for k in LABEL_FIELDS
    }


def _label_change(base_rec: dict, curr_rec: dict) -> dict | None:
    """The label_changes[] item for one matched export, or None when labels agree.

    A label is compared only when both sides have a value for it.
    """
    for field in LABEL_FIELDS:
        base_key = _label_key(field, base_rec.get(field))
        curr_key = _label_key(field, curr_rec.get(field))
        if base_key is None or curr_key is None:
            continue
        if base_key != curr_key:
            return {
                "name": curr_rec["name"],
                "file": curr_rec["file"],
                "baseline": _label_side(base_rec),
                "current": _label_side(curr_rec),
            }
    return None


def _export_type_collapses(base_rec: dict, curr_rec: dict) -> bool:
    """True when two matched records' types name one kind (EXPORT_TYPE_FORMS):
    one side's by-eye kind against the other's base kind, whose canonical
    signature shows that form. Either side may hold the by-eye kind."""
    for by_eye, base in ((base_rec, curr_rec), (curr_rec, base_rec)):
        kinds = (by_eye.get("type"), base.get("type"))
        signature = base.get("signature")
        if not all(isinstance(kind, str) for kind in kinds) or not isinstance(signature, str):
            continue
        form = EXPORT_TYPE_FORMS.get(kinds)
        if form is not None and form(signature):
            return True
    return False


def _signature_fields(rec: dict) -> list[str]:
    return [field for field in SIGNATURE_FIELDS if rec.get(field) is not None]


def _unverified_signature(base_rec: dict, curr_rec: dict) -> dict | None:
    """The signature_unverified[] item for one matched export, or None when
    every signature part both sides carry sits in a field both sides have."""
    for fields in SIGNATURE_PARTS:
        base_has = {field for field in fields if base_rec.get(field) is not None}
        curr_has = {field for field in fields if curr_rec.get(field) is not None}
        if base_has and curr_has and not (base_has & curr_has):
            return {
                "name": curr_rec["name"],
                "file": curr_rec["file"],
                "baseline": _signature_fields(base_rec),
                "current": _signature_fields(curr_rec),
            }
    return None


# --------------------------------------------------------------------------
# Diff
# --------------------------------------------------------------------------


LISTS = ["added", "removed", "changed", "moved", "ambiguous_names", "label_changes", "signature_unverified",
         "not_public"]


def _key_order(key: tuple) -> tuple:
    return (key[0], key[1] or "")


def _file_line(rec: dict) -> dict:
    return {"file": rec["file"], "line": rec["line"]}


def _diff_records(
    baseline: dict[tuple, dict],
    current: dict[tuple, dict],
    unchanged_names: collections.Counter | None = None,
    transform_counts: collections.Counter | None = None,
) -> dict:
    """Diff two (name, file)-keyed record sets: the LISTS, plus the counts
    unchanged_count and changed_exports (exports with a changed field).

    unchanged_names counts the names of exports left out of both sets as
    unchanged (--files): each counts on both sides when a move needs a name
    unique on both sides. transform_counts gains one export-type for each
    matched export whose types name one kind (_export_type_collapses).
    """
    if transform_counts is None:
        transform_counts = collections.Counter()
    removed_keys = sorted((k for k in baseline if k not in current), key=_key_order)
    added_keys = sorted((k for k in current if k not in baseline), key=_key_order)

    # A leftover is paired as a move only when its name occurs once on each
    # side; any other name left on both sides is ambiguous.
    base_names = collections.Counter(name for name, _ in baseline)
    curr_names = collections.Counter(name for name, _ in current)
    if unchanged_names:
        base_names.update(unchanged_names)
        curr_names.update(unchanged_names)
    removed_by_name: dict[str, list[tuple]] = collections.defaultdict(list)
    added_by_name: dict[str, list[tuple]] = collections.defaultdict(list)
    for key in removed_keys:
        removed_by_name[key[0]].append(key)
    for key in added_keys:
        added_by_name[key[0]].append(key)

    pairs: list[tuple[tuple, tuple]] = [(key, key) for key in baseline if key in current]
    ambiguous_names: list[dict] = []
    for name in sorted(set(removed_by_name) & set(added_by_name)):
        if base_names[name] == 1 and curr_names[name] == 1:
            pairs.append((removed_by_name[name][0], added_by_name[name][0]))
            continue
        ambiguous_names.append({
            "name": name,
            "removed": [_file_line(baseline[k]) for k in removed_by_name[name]],
            "added": [_file_line(current[k]) for k in added_by_name[name]],
        })
    paired_base = {base_key for base_key, _ in pairs}
    paired_curr = {curr_key for _, curr_key in pairs}

    # Emit normalized entries (uniform shape) so added[] and removed[] render
    # into the same report table even though they originate from the
    # snapshot and provenance-map shapes. After the pairing, a leftover
    # current entry marked off the public surface is no addition, unless its
    # name is ambiguous: a reviewer may pair it as a move.
    ambiguous = {item["name"] for item in ambiguous_names}
    added: list[dict] = []
    not_public: list[dict] = []
    for key in added_keys:
        if key in paired_curr:
            continue
        rec = current[key]
        if rec.get("public") is False and rec["name"] not in ambiguous:
            not_public.append(rec)
        else:
            added.append(rec)
    removed = [baseline[k] for k in removed_keys if k not in paired_base]

    changed: list[dict] = []
    moved: list[dict] = []
    label_changes: list[dict] = []
    signature_unverified: list[dict] = []
    unchanged_count = 0
    changed_exports = 0

    for base_key, curr_key in sorted(pairs, key=lambda pair: _key_order(pair[1])):
        base_rec = baseline[base_key]
        curr_rec = current[curr_key]

        # File moves are tracked separately from field changes, and a moved
        # export's line is not compared: the move changes it.
        is_move = base_key[1] is not None and curr_key[1] is not None and base_key[1] != curr_key[1]
        if is_move:
            moved.append({
                "name": curr_rec["name"],
                "previous_file": base_rec["file"],
                "current_file": curr_rec["file"],
                "previous_line": base_rec["line"],
                "line": curr_rec["line"],
                "confidence": curr_rec["confidence"],
            })

        entry_changed = False
        for field in DIFF_FIELDS:
            if is_move and field == "line":
                continue
            base_val = base_rec.get(field)
            curr_val = curr_rec.get(field)
            # Compare only when data is present on both sides; a missing value
            # on either side is insufficient evidence to assert a change.
            if base_val is None or curr_val is None:
                continue
            if base_val != curr_val:
                # A by-eye kind and the runner's base kind of one declaration
                # are one type: compared pairwise, never rewritten.
                if field == "type" and _export_type_collapses(base_rec, curr_rec):
                    transform_counts["export-type"] += 1
                    continue
                changed.append({
                    "name": curr_rec["name"],
                    "field": field,
                    "baseline_value": base_val,
                    "current_value": curr_val,
                    "file": curr_rec["file"],
                    "line": curr_rec["line"],
                    "confidence": curr_rec["confidence"],
                })
                entry_changed = True

        if entry_changed:
            changed_exports += 1
        else:
            unchanged_count += 1

        # Provenance labels are informational: reported, never counted as drift.
        label_change = _label_change(base_rec, curr_rec)
        if label_change is not None:
            label_changes.append(label_change)

        # A signature part the two sides hold in different fields was never
        # compared: reported, so an empty diff does not read as verified.
        unverified = _unverified_signature(base_rec, curr_rec)
        if unverified is not None:
            signature_unverified.append(unverified)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "moved": moved,
        "ambiguous_names": ambiguous_names,
        "label_changes": label_changes,
        "signature_unverified": signature_unverified,
        "not_public": not_public,
        "unchanged_count": unchanged_count,
        "changed_exports": changed_exports,
    }


def _summary(part: dict) -> dict:
    return {
        "added": len(part["added"]),
        "removed": len(part["removed"]),
        "changed": part["changed_exports"],
        "moved": len(part["moved"]),
        "unchanged": part["unchanged_count"],
        "label_changes": len(part["label_changes"]),
        "ambiguous_names": len(part["ambiguous_names"]),
        "signature_unverified": len(part["signature_unverified"]),
        "not_public": len(part["not_public"]),
    }


def _group_of(entry: object, group_by: str) -> str | None:
    value = entry.get(group_by) if isinstance(entry, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _grouped(entries: list, group_by: str) -> bool:
    return any(_group_of(entry, group_by) is not None for entry in entries)


def _in_scope(entry: object, scope: set[str]) -> bool:
    return isinstance(entry, dict) and _file_key(_first(entry, "file", "source_file")) in scope


def diff_inventories(
    baseline_entries: list[dict],
    current_entries: list[dict],
    reexport_map: dict[str, str] | None = None,
    group_by: str | None = None,
    sources: tuple[str, str] = ("the baseline inventory", "the current inventory"),
    files: list[str] | None = None,
) -> dict:
    """Compute the structural diff between two export inventories.

    Returns a dict with keys: summary, added, removed, changed, moved,
    ambiguous_names, label_changes, signature_unverified, not_public,
    unchanged_count, applied_transforms; with group_by, group_by and
    groups; and with files, file_scope (see the module docstring). files
    limits the diff to the exports of those files, and every other export
    is taken as unchanged.

    Raises ValueError when group_by is set and one side has entries but
    none with a group_by value while the other side has some; the message
    names that side as sources does (the CLI passes the two file paths).
    """
    if group_by:
        sides = (
            (baseline_entries, current_entries, sources[0]),
            (current_entries, baseline_entries, sources[1]),
        )
        for entries, other, source in sides:
            if entries and not _grouped(entries, group_by) and _grouped(other, group_by):
                raise ValueError(f"--group-by {group_by}: {source} has no entry with {group_by}")

    reexport_map = reexport_map or {}
    transform_counts: collections.Counter = collections.Counter()
    scope = None if files is None else {key for key in map(_file_key, files) if key}

    base_groups: dict[str | None, list] = collections.defaultdict(list)
    curr_groups: dict[str | None, list] = collections.defaultdict(list)
    for entry in baseline_entries:
        base_groups[_group_of(entry, group_by) if group_by else None].append(entry)
    for entry in current_entries:
        curr_groups[_group_of(entry, group_by) if group_by else None].append(entry)
    values = sorted(set(base_groups) | set(curr_groups), key=lambda v: (v is None, v or ""))

    total: dict = {name: [] for name in LISTS}
    total.update(unchanged_count=0, changed_exports=0)
    groups: list[dict] = []
    left_out = {"baseline": 0, "current": 0}
    for value in values or [None]:
        base_part = base_groups.get(value, [])
        curr_part = curr_groups.get(value, [])
        unchanged_names: collections.Counter = collections.Counter()
        if scope is not None:
            # Exports outside the scope are normalized apart, so a transform
            # they need is not reported: they are in no list and no count.
            outside = {
                side: _normalize_entries(
                    [e for e in entries if not _in_scope(e, scope)], reexport_map, collections.Counter()
                )
                for side, entries in (("baseline", base_part), ("current", curr_part))
            }
            unchanged_names.update(name for name, _ in outside["baseline"])
            for side, records in outside.items():
                left_out[side] += len(records)
            base_part = [e for e in base_part if _in_scope(e, scope)]
            curr_part = [e for e in curr_part if _in_scope(e, scope)]
        part = _diff_records(
            _normalize_entries(base_part, reexport_map, transform_counts),
            _normalize_entries(curr_part, reexport_map, transform_counts),
            unchanged_names,
            transform_counts,
        )
        if group_by:
            for name in LISTS:
                part[name] = [{group_by: value, **item} for item in part[name]]
            groups.append({group_by: value, "summary": _summary(part)})
        for name in LISTS:
            total[name].extend(part[name])
        total["unchanged_count"] += part["unchanged_count"]
        total["changed_exports"] += part["changed_exports"]

    applied_transforms = [
        {"transform": name, "count": transform_counts[name]}
        for name in sorted(transform_counts)
        if transform_counts[name] > 0
    ]

    result = {"summary": _summary(total)}
    result.update((name, total[name]) for name in LISTS)
    result["unchanged_count"] = total["unchanged_count"]
    result["applied_transforms"] = applied_transforms
    if group_by:
        result["group_by"] = group_by
        result["groups"] = groups
    if scope is not None:
        result["file_scope"] = {
            "files": len(scope),
            "baseline_left_out": left_out["baseline"],
            "current_left_out": left_out["current"],
        }
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


# Exit codes: no difference, differences found, error.
EXIT_SAME = 0
EXIT_DIFFERENT = 1
EXIT_ERROR = 2


def _fail(message: str) -> int:
    print(json.dumps({"status": "error", "error": message}, indent=2))
    return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    # --help prints the module docstring: the input, matching and output
    # contract a calling step cites.
    parser = argparse.ArgumentParser(
        prog="skf-structural-diff.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "baseline",
        metavar="baseline.json",
        help="path to the baseline export inventory (e.g. provenance-map.json)",
    )
    parser.add_argument(
        "current",
        metavar="current.json",
        help="path to the current export inventory (e.g. extraction-snapshot.json)",
    )
    parser.add_argument(
        "--reexport-map",
        metavar="FILE",
        help=(
            "path to a JSON re-export map ({internal: public}) or a "
            "skf-load-provenance normalize output. When omitted, the map is "
            "derived from the baseline provenance map itself."
        ),
    )
    parser.add_argument(
        "--group-by",
        choices=GROUP_FIELDS,
        help=(
            "diff each group of entries on its own (source_library: a stack's "
            "libraries) and tag every listed item with its group; an "
            "inventory whose entries all lack the field is an error when "
            "the other's have it"
        ),
    )
    parser.add_argument(
        "--files",
        metavar="FILE",
        help=(
            "diff only the exports of the files FILE names (a JSON array of "
            "paths, or a skf-classify-changed-files.py classify output) and "
            "take every other export as unchanged"
        ),
    )
    parser.add_argument(
        "--current-extra",
        metavar="FILE",
        help=(
            "an inventory merged into the current one by name and file: it fills "
            "the fields a current entry lacks, and adds the entries no current "
            "one has"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write the JSON diff to FILE and print only a summary line on stdout",
    )

    args = parser.parse_args(argv)

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    baseline_data, err = load_json(baseline_path)
    if err:
        return _fail(err)
    current_data, err = load_json(current_path)
    if err:
        return _fail(err)

    baseline_entries, err = entries_from_data(baseline_data, str(baseline_path))
    if err:
        return _fail(err)
    current_entries, err = entries_from_data(current_data, str(current_path))
    if err:
        return _fail(err)
    if args.current_extra:
        extra_entries, err = load_inventory(Path(args.current_extra))
        if err:
            return _fail(err)
        current_entries = merge_extra(current_entries, extra_entries)

    if args.reexport_map:
        reexport_map, err = load_reexport_map(Path(args.reexport_map))
        if err:
            return _fail(err)
    else:
        reexport_map = extract_reexport_map(baseline_data)

    files = None
    if args.files:
        files_data, err = load_json(Path(args.files))
        if err:
            return _fail(err)
        files, err = files_from_data(files_data, args.files)
        if err:
            return _fail(err)

    try:
        result = diff_inventories(
            baseline_entries, current_entries, reexport_map, args.group_by,
            sources=(str(baseline_path), str(current_path)),
            files=files,
        )
    except ValueError as exc:
        return _fail(str(exc))
    output_text = json.dumps(result, indent=2)

    if args.output:
        out_path = Path(args.output)
        try:
            out_path.write_text(output_text + "\n", encoding="utf-8")
        except OSError as exc:
            return _fail(f"Cannot write output: {exc}")
        print(json.dumps({"status": "ok", "output": str(out_path), "summary": result["summary"]}))
    else:
        print(output_text)

    summary = result["summary"]
    has_diff = summary["added"] or summary["removed"] or summary["changed"] or summary["moved"]
    return EXIT_DIFFERENT if has_diff else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
