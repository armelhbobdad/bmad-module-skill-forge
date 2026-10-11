# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Extraction Inventory: write, extend and read create-skill's extraction inventory on disk.

skf-create-skill step 3 keeps its extraction inventory as JSON beside the
staging folder (`_bmad-output/.skf-stage/{skill-name}.inventory.json`), so
the exports, their citations and the extraction rules survive a context
compaction between extraction and compile. `init` seeds it from the recipe
runner's JSON and the script/asset detector's JSON, so the model never
types a record those tools already wrote; the model then sends only what it
produced itself (`patch`, `add`, `set`). Step 3c adds the T3 items it
extracts from fetched documentation, step 4 the T2 annotations it finds in
QMD, and step 7 writes `extraction-rules.yaml` from it (`rules`). Every
write goes through a temporary file and one rename.

Subcommands:

  init     --inventory <file> --skill <name>
           --mode source|docs-only|component-library
           --tier Quick|Forge|Forge+|Deep
           [--extraction <runner JSON>] [--detected <detector JSON>]
           Write a new inventory, replacing any file at --inventory. From
           --extraction (skf-extract-public-api.py --mode full): every
           export as the runner recorded it (confidence T1, extraction_method
           ast-grep), with `internal: true` on each one its
           entry_point_diff.internal lists; files_scanned (its
           files_in_scope); aggregates, counts and arms; extraction_rules
           (recipe_set, the recipes ids, scope, ast_grep_version); and the
           runner warnings as lines (the head cap, each errors[] item, each
           file_issues[] file, each files_without_recipes extension, each
           warnings[] entry). From --detected (skf-detect-scripts-assets.py
           detect): scripts_inventory and assets_inventory.
           Public surface. When the runner's scope.type is public-api (in
           any case) and its entry-point diff can be read, each export of a
           language family whose entry_points.by_language status is
           `barrel` is marked `public: true` when its name and file are a
           pair of the diff's `public` (its name, or the name `local` gives
           it in that file) or `extraction_gaps`, or when a `public` item of
           its name and family has no file; `public: false` otherwise. A
           `public` item with `via` namespace and a `members` list (what
           the submodule passes on, which users reach as `pkg.sub.name`)
           gives its members' pairs (each member's name, or its `local`
           one, and its file; a member with no file its name) in place of
           its own; one whose `members` is null (a module the runner could
           not read), or that has no `members` key (an older runner's),
           gives its own pair, as any item does. It is the rule
           skf-build-change-manifest.py's `records` marks an update's
           exports by (that script loads it from here). The rule's inputs
           are kept as `public_surface`, so `add` marks an export read by
           eye the same way. Any other scope type, and a family with no
           barrel, mark nothing. A public-api run with no entry-point diff,
           an incomplete one, one with errors or one whose
           entry_points.unresolved is not empty marks nothing either
           (`public_surface` null), with one warning that says why: every
           export is then documented. One warning names the exports marked
           `public: false`, each as `name (file)` (the first ten, then how
           many more).

  add      --inventory <file> --field exports|t2_annotations|t3_items|warnings
           Read a JSON list on stdin (objects; strings for warnings) and
           append it to that list. An entry already in the list (equal
           JSON; for exports, the same export_name and source_file) is not
           added twice and counts in `duplicates`. An exports entry needs an
           export_name; a missing confidence, extraction_method,
           ast_node_type or ast_recipe defaults to T1-low, source-read,
           null and null (an export read by eye). An exports entry is
           marked `public` by the inventory's `public_surface`, as `init`
           marks the runner's (a `public` key the payload sends is not
           kept), and the warning naming the exports marked `public: false`
           is written again, in its place. A t3_items entry whose
           export_name names an export the inventory already holds is
           dropped, not added: T3 content never overrides a T1, T1-low or
           T2 entry for the same export.

  patch    --inventory <file>
           Read a JSON list of objects on stdin, each an export_name, an
           optional source_file, and any of signature, params and
           return_type, and set those fields on the export it names (by
           export_name and source_file; by export_name alone when no
           source_file is given). A name that matches no export is listed
           in `unmatched`, one that matches several in `ambiguous`; neither
           changes anything. params lists each parameter as the runner
           records one, {name, type, default, optional}, or as a typed
           string ('userId: string').

  set      --inventory <file>
           Read a JSON object on stdin and set each of its keys: top_exports,
           co_imports, promoted_docs, component_catalog (lists),
           authoritative_files_scan (an object or null), files_scanned (an
           integer), counts and arms (objects, merged into what is there)
           and intent_mapping. intent_mapping maps `scripts` and `assets`
           to {"intent": "<free text>", "kept": [source_file, ...]}: the
           inventory keeps only the kept entries of that list and records
           the others in the mapping's `left_out`. A top_exports name every
           export of which is marked `public: false` is not kept and is
           listed in `dropped`.

  provenance --inventory <file> --target <provenance-map.json> [--add-entries]
           Write the provenance map to --target, so compile never types an
           entry the inventory holds. stdin holds the map's header, a JSON
           object: source_repo and source_commit (required, null allowed),
           and source_ref (default null), provenance_version (default
           "2.0"), skill_name (default the inventory's), skill_type
           (default "single") and generated_at (default now, ISO-8601
           UTC); any other key is refused. entries[] holds the entry of
           every export of the inventory, in its order, but one marked
           `public: false` (off a public-api skill's public surface, which
           neither entries[] nor `unsigned` lists): export_name,
           export_type, params, return_type, source_file, source_line,
           confidence, extraction_method, ast_node_type and
           signature_source, labeled by the tool that found it. An export
           an ast-grep rule matched is T1 (extraction_method ast-grep, the
           ast_node_type its recipe declares, signature_source T1); any
           other was read by eye and is T1-low (extraction_method
           source-read, ast_node_type null, signature_source T1-low).
           params holds the map's typed strings, one per parameter the
           runner (or a patch) recorded: `name: type`, `name?: type` for a
           JS/TS parameter that is optional and has no default,
           ` = default` after a default, and the type alone for a
           parameter with no name; a string a patch or an add sent is kept
           as it is. params and return_type are null on an export whose
           params is null: any export but a function, or a function nobody
           read the signature of, which `unsigned` lists (patch them and
           run provenance again). The inventory is not changed.
           With --add-entries, stdin holds instead a JSON object with an
           `entries` list, a `file_entries` list or both, appended to the
           map at --target: the entries the inventory does not hold (T2 and
           T3) and the file entries. An entry whose export_name and
           source_file the map already holds, or a file entry whose
           file_name it holds, is not added and counts in `duplicates`, so
           an inventory export's entry is never replaced. An entry whose
           export_name and source_file are an inventory export's marked
           `public: false` is not added either and is listed in
           `not_public`, so the map never holds an export off the surface.

  rules    --inventory <file> --language <language> --target <file>
           Write extraction-rules.yaml (the skill, its language, tier and
           extraction mode, and the inventory's extraction_rules) to
           --target. The inventory is not changed.

  summary  --inventory <file>
           Print the inventory's counts without changing it, and in
           `not_public` each export marked `public: false` ({name, file}),
           which the evidence report lists.

Inventory shape (the keys this helper reads or writes):

  {
    "skill_name": "...", "extraction_mode": "...", "tier": "...",
    "files_scanned": N | null,
    "exports":        [{"export_name": "...", "source_file": "...", ...}, ...],
    "top_exports":    ["name", ...],
    "aggregates": {...}, "counts": {...}, "arms": {...},
    "scripts_inventory": [...], "assets_inventory": [...],
    "intent_mapping": {"scripts": {"intent", "kept", "left_out"}, ...},
    "co_imports": [...], "promoted_docs": [...],
    "authoritative_files_scan": {...} | null,
    "extraction_rules": {"recipe_set", "recipes", "scope", "ast_grep_version"},
    "public_surface": {"by_language": {...}, "public": [...],
                       "extraction_gaps": [...]} | null,
    "t2_annotations": [...], "t3_items": [...], "warnings": ["..."]
  }

An export may carry `internal: true` (the runner's entry_point_diff.internal
lists it) and `public: true` or `public: false` (see init's Public surface).

Output (stdout, exit 0), for every subcommand but rules and provenance:

  {
    "status": "ok",
    "inventory": "<path, / separators>",
    "extraction_mode": "...",
    "counts": {"files_scanned": N | null, "exports": N, "not_public": N,
               "t1": N, "t1_low": N, "by_type": {"<export_type>": N, ...},
               "top_exports": N, "co_imports": N, "scripts": N,
               "assets": N, "t2_annotations": N, "t2_past": N,
               "t2_future": N, "functions_enriched": N, "t3_items": N,
               "items": N},
    "added": N, "duplicates": N, "dropped": ["name"],   # add
    "patched": N, "unmatched": [...], "ambiguous": [...],  # patch
    "set": ["key", ...], "dropped": ["name"],           # set
    "not_public": [{"name", "file"}, ...]               # summary
  }

not_public counts the exports marked `public: false`, which the provenance
map leaves out: when it equals `exports`, the map holds no export. `items`
is exports plus t3_items, less not_public: what compile can document. t1
and t1_low count the exports by their `confidence`, by_type by their
`export_type`.
t2_past and t2_future count the T2 annotations by their `temporal`, and
functions_enriched the distinct export_name values among them; an
annotation of a name every export of which is marked `public: false`
counts in none of t2_annotations, t2_past, t2_future and
functions_enriched. rules
prints {"status": "ok", "target": "<path>", "bytes": N}, provenance
{"status": "ok", "target": "<path>", "entries": N, "unsigned": ["name
(file)", ...]}, and provenance --add-entries {"status": "ok", "target":
"<path>", "entries": N, "file_entries": N, "added": N, "duplicates": N,
"not_public": [{"name", "file"}, ...]}, the counts of the map after the
merge.

Exit codes:
  0  success
  1  input error, nothing changed: an inventory that is missing, not JSON
     or has no exports list, an --extraction or --detected file that
     cannot be read, a provenance map at --target that --add-entries
     cannot read, a stdin payload of the wrong shape, an unknown key or a
     kept file the inventory does not list, or a write that failed
  2  usage error (argparse)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

FIELDS = ("exports", "t2_annotations", "t3_items", "warnings")
MODES = ("source", "docs-only", "component-library")
TIERS = ("Quick", "Forge", "Forge+", "Deep")
LISTS = ("top_exports", "co_imports", "promoted_docs", "component_catalog", "scripts_inventory",
         "assets_inventory", "t2_annotations", "t3_items", "warnings")
PATCHABLE = ("signature", "params", "return_type")
# set: the key, the JSON types it takes, and whether an object merges into the one there.
SETTABLE = {
    "top_exports": ((list,), False),
    "co_imports": ((list,), False),
    "promoted_docs": ((list,), False),
    "component_catalog": ((list,), False),
    "authoritative_files_scan": ((dict, type(None)), False),
    "files_scanned": ((int,), False),
    "counts": ((dict,), True),
    "arms": ((dict,), True),
    "intent_mapping": ((dict,), False),
}
# intent_mapping kinds and the inventory list each one filters.
INTENT_LISTS = {"scripts": "scripts_inventory", "assets": "assets_inventory"}
BY_EYE_DEFAULTS = {"confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
                   "ast_recipe": None}
YAML_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


class InventoryError(Exception):
    """Exit 1."""


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InventoryError(f"cannot read the inventory {path.as_posix()}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("exports"), list):
        raise InventoryError(f"the inventory {path.as_posix()} is not an object with an exports list")
    for key in LISTS:
        if key in data and not isinstance(data[key], list):
            raise InventoryError(f"the inventory's {key} is not a list")
    return data


def _read_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InventoryError(f"cannot read the {label} {path.as_posix()}: {exc}") from exc


def _off_surface_names(data: dict) -> set[str]:
    """The export names every inventory export of which is marked `public: false`."""
    marks: dict[str, bool] = {}
    for export in data.get("exports") or []:
        if isinstance(export, dict) and isinstance(export.get("export_name"), str):
            name = export["export_name"]
            marks[name] = marks.get(name, True) and export.get("public") is False
    return {name for name, off in marks.items() if off}


def _not_public(data: dict) -> list[dict]:
    """{name, file} of each export marked `public: false`, in the inventory's order."""
    return [{"name": e.get("export_name"), "file": e.get("source_file")} for e in data.get("exports") or []
            if isinstance(e, dict) and e.get("public") is False]


def counts(data: dict) -> dict:
    exports = [e for e in data["exports"] if isinstance(e, dict)]
    off = _off_surface_names(data)
    raw_notes = [n for n in data.get("t2_annotations") or [] if isinstance(n, dict)]
    notes = [n for n in raw_notes if not (isinstance(n.get("export_name"), str) and n["export_name"] in off)]

    def _length(key: str) -> int:
        value = data.get(key)
        return len(value) if isinstance(value, list) else 0

    by_type: dict[str, int] = {}
    for export in exports:
        kind = export.get("export_type")
        if isinstance(kind, str) and kind:
            by_type[kind] = by_type.get(kind, 0) + 1
    files = data.get("files_scanned")
    not_public = sum(1 for e in exports if e.get("public") is False)
    return {
        "files_scanned": files if isinstance(files, int) else None,
        "exports": len(data["exports"]),
        "not_public": not_public,
        "t1": sum(1 for e in exports if e.get("confidence") == "T1"),
        "t1_low": sum(1 for e in exports if e.get("confidence") == "T1-low"),
        "by_type": dict(sorted(by_type.items())),
        "top_exports": _length("top_exports"),
        "co_imports": _length("co_imports"),
        "scripts": _length("scripts_inventory"),
        "assets": _length("assets_inventory"),
        "t2_annotations": _length("t2_annotations") - (len(raw_notes) - len(notes)),
        "t2_past": sum(1 for n in notes if n.get("temporal") == "T2-past"),
        "t2_future": sum(1 for n in notes if n.get("temporal") == "T2-future"),
        "functions_enriched": len({n["export_name"] for n in notes if isinstance(n.get("export_name"), str)}),
        "t3_items": _length("t3_items"),
        "items": len(data["exports"]) - not_public + _length("t3_items"),
    }


def runner_warnings(extraction: dict) -> list[str]:
    """The recipe runner's anomalies, one line each, for Gate 2 and the evidence report."""
    lines: list[str] = []
    recipes = [r for r in extraction.get("recipes") or [] if isinstance(r, dict)]
    if extraction.get("truncated"):
        capped = ", ".join(f"`{r.get('id')}`" for r in recipes if r.get("truncated")) or "a recipe"
        lines.append(f"Extraction hit the head cap: {capped} matched more than {extraction.get('head_cap')} "
                     "exports, so some exports were read by eye or left out. Narrow `scope.include` in the "
                     "brief until no recipe reaches the cap.")
    for error in extraction.get("errors") or []:
        if isinstance(error, dict):
            lines.append(f"ast-grep did not finish on {error.get('files')} files from `{error.get('first_file')}` "
                         f"({error.get('detail')}): exports in them may be missing")
    for issue in extraction.get("file_issues") or []:
        if isinstance(issue, dict):
            lines.append(f"`{issue.get('file')}` ({issue.get('issue')}): its exports are read by eye")
    without = extraction.get("files_without_recipes")
    if isinstance(without, dict):
        for ext, number in sorted(without.items()):
            lines.append(f"{number} `{ext}` files in scope are in a language no recipe reads")
    lines.extend(w for w in extraction.get("warnings") or [] if isinstance(w, str) and w)
    return lines


# --------------------------------------------------------------------------
# The public surface of a public-api skill (see init's "Public surface"):
# one rule, which skf-build-change-manifest.py loads from here for update-skill
# --------------------------------------------------------------------------


def _norm_path(path: object) -> str | None:
    """A file path compared as structural-diff compares it: `/` separators, no leading `./`."""
    if not isinstance(path, str) or not path.strip():
        return None
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


PUBLIC_API = "public-api"
# A record's language family, the one whose entry points declare its names: skf-extract-public-api.py's FAMILY_OF,
# by the record's `language`, else by its file's extension (that script's EXTENSION_LANGUAGES).
_FAMILY_OF_LANGUAGE = {"python": "python", "typescript": "javascript", "tsx": "javascript",
                       "javascript": "javascript", "vue": "javascript", "rust": "rust", "go": "go"}
_FAMILY_OF_EXTENSION = {".py": "python", ".pyi": "python", ".rs": "rust", ".go": "go",
                        **dict.fromkeys((".ts", ".mts", ".cts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue"),
                                        "javascript")}


class _PublicSurface:
    """The public surface of a public-api skill's extraction (see init's "Public surface" in the module
    docstring)."""

    def __init__(self, diff: dict, statuses: dict):
        self.barrels = {family for family, status in statuses.items() if status == "barrel"}
        self.pairs: set[tuple[str, str]] = set()
        self.unfiled: set[tuple[object, str]] = set()  # (family, name) of a public name no file defines
        for key in ("public", "extraction_gaps"):
            for item in diff.get(key) or []:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
                    continue
                family = item.get("language")
                members = item.get("members") if key == "public" and item.get("via") == "namespace" else None
                if isinstance(members, list):
                    # a namespace whose module the runner read: its members, in place of the module itself
                    for member in members:
                        if isinstance(member, dict) and isinstance(member.get("name"), str) and member["name"]:
                            self._add(family, member["name"], member.get("local"), member.get("file"), True)
                    continue
                self._add(family, item["name"], item.get("local") if key == "public" else None, item.get("file"),
                          key == "public")

    def _add(self, family: object, name: str, local: object, path: object, listed_public: bool) -> None:
        """The pairs one public name (or gap) gives: (name, file) and (local, file), or, with no file, its
        (family, name) when `public` lists it."""
        file = _norm_path(path)
        if not file:
            if listed_public:
                self.unfiled.add((family, name))
            return
        self.pairs.update((n, file) for n in (name, local) if isinstance(n, str) and n)

    def public(self, name: str, path: str, language: object = None) -> bool | None:
        """Whether the export is on the public surface; None (no mark) when its family's entry points are no
        barrel."""
        family = _FAMILY_OF_LANGUAGE.get(language) if isinstance(language, str) else None
        if family is None:
            family = _FAMILY_OF_EXTENSION.get(os.path.splitext(path)[1].lower())
        if family not in self.barrels:
            return None
        return (name, path) in self.pairs or (family, name) in self.unfiled


def public_surface(extraction: object) -> tuple[_PublicSurface | None, str | None]:
    """(the public surface, None) of the recipe runner's output when its scope type is public-api; (None, why the
    surface cannot be read from it) for a public-api run with no entry-point diff, an incomplete one, one with
    errors or one whose entry points name a module the trace could not follow; (None, None) for any other scope
    type. With no surface every export is kept, as before."""
    if not isinstance(extraction, dict):
        return None, None
    scope, diff, points = extraction.get("scope"), extraction.get("entry_point_diff"), extraction.get("entry_points")
    kind = scope.get("type") if isinstance(scope, dict) else None
    if not (isinstance(kind, str) and kind.strip().lower() == PUBLIC_API):
        return None, None
    statuses = points.get("by_language") if isinstance(points, dict) else None
    if not isinstance(diff, dict) or not isinstance(statuses, dict):
        return None, "the recipe runner gave no entry-point diff (Quick tier, or a run that could not read the tree)"
    if extraction.get("status") == "incomplete" or extraction.get("errors"):
        return None, "the recipe runner's run is incomplete"
    if points.get("unresolved"):
        return None, "an entry point names a module the runner could not trace (entry_points.unresolved)"
    return _PublicSurface(diff, statuses), None


# The fields of an entry_point_diff item the rule reads, which the inventory's public_surface keeps for `add`, and
# those of each member of a namespace item.
SURFACE_FIELDS = {"public": ("name", "language", "file", "local", "via", "members"),
                  "extraction_gaps": ("name", "language", "file")}
MEMBER_FIELDS = ("name", "local", "file")
NOT_PUBLIC_NAMED = 10  # the names the not-public warning spells out, as update-skill's apply does
NOT_PUBLIC_LEAD = "Off the public surface: "


def _surface_state(extraction: dict) -> dict:
    """The parts of the runner's JSON the rule reads (public_surface found a surface in it)."""
    diff = extraction["entry_point_diff"]
    state: dict = {"by_language": dict(extraction["entry_points"]["by_language"])}
    for key, fields in SURFACE_FIELDS.items():
        state[key] = [{field: item[field] for field in fields if field in item}
                      for item in diff.get(key) or [] if isinstance(item, dict)]
    for item in state["public"]:
        if isinstance(item.get("members"), list):
            item["members"] = [{field: m[field] for field in MEMBER_FIELDS if field in m}
                               for m in item["members"] if isinstance(m, dict)]
    return state


def _stored_surface(data: dict) -> _PublicSurface | None:
    """The public surface the inventory's public_surface keeps, or None when init kept none."""
    state = data.get("public_surface")
    if not isinstance(state, dict) or not isinstance(state.get("by_language"), dict):
        return None
    return _PublicSurface(state, state["by_language"])


def _mark(surface: _PublicSurface | None, export: dict) -> None:
    """Set the export's `public` mark by the rule; no other `public` value is kept."""
    export.pop("public", None)
    name, path = export.get("export_name"), _norm_path(export.get("source_file"))
    if surface is None or not isinstance(name, str) or not name or path is None:
        return
    mark = surface.public(name, path, export.get("language"))
    if mark is not None:
        export["public"] = mark


def _not_public_warning(names: list[str]) -> str:
    """The one warning naming the exports marked `public: false` (`name (file)`), for Gate 2 and the evidence
    report."""
    shown = ", ".join(names[:NOT_PUBLIC_NAMED])
    more = f" and {len(names) - NOT_PUBLIC_NAMED} more" if len(names) > NOT_PUBLIC_NAMED else ""
    return (f"{NOT_PUBLIC_LEAD}{len(names)} export(s) of this public-api skill are left out of the provenance map, "
            f"SKILL.md, references/, the context snippet and metadata.json's exports[] (each is marked "
            f"`public: false` in the inventory, and `summary` lists them all): {shown}{more}")


def _write_not_public_warning(data: dict) -> None:
    """Write the not-public warning in place of the one an earlier call wrote (else at the end), or drop it when
    no export is marked `public: false`."""
    names = [f"{item['name']} ({item['file']})" for item in _not_public(data)]
    warnings = data.setdefault("warnings", [])
    at = next((i for i, w in enumerate(warnings) if isinstance(w, str) and w.startswith(NOT_PUBLIC_LEAD)), None)
    if at is not None:
        del warnings[at]
    if names:
        warnings.insert(len(warnings) if at is None else at, _not_public_warning(names))


def init(skill: str, mode: str, tier: str, extraction: dict | None = None, detected: dict | None = None) -> dict:
    """A new inventory, seeded from the runner's JSON and the detector's JSON."""
    data: dict = {
        "skill_name": skill, "extraction_mode": mode, "tier": tier, "files_scanned": None,
        "exports": [], "top_exports": [], "aggregates": {}, "counts": {}, "arms": {},
        "scripts_inventory": [], "assets_inventory": [], "intent_mapping": {}, "co_imports": [],
        "promoted_docs": [], "authoritative_files_scan": None, "extraction_rules": {}, "public_surface": None,
        "t2_annotations": [], "t3_items": [], "warnings": [],
    }
    if extraction is not None:
        if not isinstance(extraction, dict):
            raise InventoryError("the --extraction file is not a JSON object")
        diff = extraction.get("entry_point_diff")
        internal = {(i.get("name"), i.get("source_file"))
                    for i in (diff.get("internal") or [] if isinstance(diff, dict) else []) if isinstance(i, dict)}
        surface, problem = public_surface(extraction)
        for record in extraction.get("exports") or []:
            if not isinstance(record, dict):
                continue
            export = dict(record)
            export.setdefault("confidence", "T1")
            export.setdefault("extraction_method", "ast-grep")
            if (export.get("export_name"), export.get("source_file")) in internal:
                export["internal"] = True
            _mark(surface, export)
            data["exports"].append(export)
        files = extraction.get("files_in_scope")
        data["files_scanned"] = files if isinstance(files, int) else None
        for key in ("aggregates", "counts", "arms"):
            value = extraction.get(key)
            data[key] = dict(value) if isinstance(value, dict) else {}
        ast_grep = extraction.get("ast_grep")
        data["extraction_rules"] = {
            "recipe_set": extraction.get("recipe_set"),
            "recipes": [r.get("id") for r in extraction.get("recipes") or [] if isinstance(r, dict)],
            "scope": extraction.get("scope") if isinstance(extraction.get("scope"), dict) else {},
            "ast_grep_version": ast_grep.get("version") if isinstance(ast_grep, dict) else None,
        }
        data["warnings"] = runner_warnings(extraction)
        if problem:
            data["warnings"].append(f"The public surface of this public-api skill could not be applied ({problem}): "
                                    "no export is marked `public: false`, so every export found is documented")
        if surface is not None:
            data["public_surface"] = _surface_state(extraction)
            _write_not_public_warning(data)
    if detected is not None:
        if not isinstance(detected, dict):
            raise InventoryError("the --detected file is not a JSON object")
        for key in ("scripts_inventory", "assets_inventory"):
            value = detected.get(key) or []
            if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
                raise InventoryError(f"the --detected file's {key} is not a list of objects")
            data[key] = [dict(e) for e in value]
    return data


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def add(data: dict, field: str, entries: list) -> tuple[int, int, list[str]]:
    """Append `entries` to data[field]; return (added, duplicates, dropped export names)."""
    if field not in FIELDS:
        raise InventoryError(f"--field must be one of {', '.join(FIELDS)}")
    kind = str if field == "warnings" else dict
    if not isinstance(entries, list) or not all(isinstance(e, kind) for e in entries):
        raise InventoryError(f"stdin must hold a JSON list of {'strings' if kind is str else 'objects'}")
    surface = _stored_surface(data) if field == "exports" else None
    if field == "exports":
        if not all(isinstance(e.get("export_name"), str) and e["export_name"] for e in entries):
            raise InventoryError("every exports entry needs an export_name")
        entries = [{**BY_EYE_DEFAULTS, **e} for e in entries]
        for entry in entries:
            _mark(surface, entry)
    target = data.setdefault(field, [])
    known = {e.get("export_name") for e in data["exports"] if isinstance(e, dict)} - {None}
    added = duplicates = 0
    dropped: list[str] = []
    for entry in entries:
        if field == "t3_items" and entry.get("export_name") in known:
            dropped.append(entry["export_name"])
            continue
        if field == "exports":
            key = (entry["export_name"], entry.get("source_file"))
            repeat = any(isinstance(e, dict) and (e.get("export_name"), e.get("source_file")) == key
                         for e in target)
        else:
            repeat = any(_same(entry, e) for e in target)
        if repeat:
            duplicates += 1
            continue
        target.append(entry)
        added += 1
    if surface is not None:
        _write_not_public_warning(data)
    return added, duplicates, dropped


def patch(data: dict, entries: list) -> tuple[int, list[str], list[str]]:
    """Set signature, params and return_type on the exports named; return (patched, unmatched, ambiguous)."""
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise InventoryError("stdin must hold a JSON list of objects")
    for entry in entries:
        if not isinstance(entry.get("export_name"), str) or not entry["export_name"]:
            raise InventoryError("every patch entry needs an export_name")
        extra = sorted(set(entry) - {"export_name", "source_file", *PATCHABLE})
        if extra:
            raise InventoryError(f"patch sets only {', '.join(PATCHABLE)}; {entry['export_name']} also has "
                                 f"{', '.join(extra)}")
    patched = 0
    unmatched: list[str] = []
    ambiguous: list[str] = []
    for entry in entries:
        name, source = entry["export_name"], entry.get("source_file")
        found = [e for e in data["exports"] if isinstance(e, dict) and e.get("export_name") == name
                 and (source is None or e.get("source_file") == source)]
        label = name if source is None else f"{name} ({source})"
        if not found:
            unmatched.append(label)
        elif len(found) > 1:
            ambiguous.append(label)
        else:
            found[0].update({k: entry[k] for k in PATCHABLE if k in entry})
            patched += 1
    return patched, unmatched, ambiguous


def set_fields(data: dict, values: dict) -> tuple[list[str], list[str]]:
    """Set the keys of `values` on the inventory (see the module docstring); return (the keys set, the top_exports
    names dropped as off the public surface)."""
    if not isinstance(values, dict):
        raise InventoryError("stdin must hold a JSON object")
    unknown = sorted(set(values) - set(SETTABLE))
    if unknown:
        raise InventoryError(f"set takes only {', '.join(SETTABLE)}; not {', '.join(unknown)}")
    for key, value in values.items():
        types, _ = SETTABLE[key]
        if not isinstance(value, types) or (key == "files_scanned" and isinstance(value, bool)):
            names = " or ".join("null" if t is type(None) else t.__name__ for t in types)
            raise InventoryError(f"{key} must be {names}")
    mapping = _intent_mapping(data, values["intent_mapping"]) if "intent_mapping" in values else {}
    dropped: list[str] = []
    if "top_exports" in values:
        off = _off_surface_names(data)
        dropped = [n for n in values["top_exports"] if isinstance(n, str) and n in off]
        values = {**values, "top_exports": [n for n in values["top_exports"] if not (isinstance(n, str) and n in off)]}
    for key, value in values.items():
        if key == "intent_mapping":
            data["intent_mapping"] = {**(data.get("intent_mapping") or {}), **mapping}
        elif SETTABLE[key][1]:
            data[key] = {**(data.get(key) if isinstance(data.get(key), dict) else {}), **value}
        else:
            data[key] = value
    return list(values), dropped


def _intent_mapping(data: dict, mapping: dict) -> dict:
    """Keep only the kept entries of each list a free-text intent names; return the recorded mapping."""
    unknown = sorted(set(mapping) - set(INTENT_LISTS))
    if unknown:
        raise InventoryError(f"intent_mapping takes only {', '.join(INTENT_LISTS)}; not {', '.join(unknown)}")
    recorded: dict = {}
    filtered: dict[str, list] = {}
    for kind, spec in mapping.items():
        kept_files = spec.get("kept") if isinstance(spec, dict) else None
        if not isinstance(spec, dict) or not isinstance(spec.get("intent"), str) or not isinstance(kept_files, list) \
                or not all(isinstance(f, str) for f in kept_files):
            raise InventoryError(f'intent_mapping.{kind} must be {{"intent": "<text>", "kept": [source_file, ...]}}')
        entries = [e for e in data.get(INTENT_LISTS[kind]) or [] if isinstance(e, dict)]
        listed = {e.get("source_file") for e in entries}
        missing = [f for f in spec["kept"] if f not in listed]
        if missing:
            raise InventoryError(f"{INTENT_LISTS[kind]} lists no {', '.join(missing)}")
        kept = set(spec["kept"])
        filtered[kind] = [e for e in entries if e.get("source_file") in kept]
        earlier = (data.get("intent_mapping") or {}).get(kind)
        left_out = {e.get("source_file") for e in entries if e.get("source_file") not in kept}
        if isinstance(earlier, dict) and earlier.get("intent") == spec["intent"]:
            left_out |= set(earlier.get("left_out") or [])
        recorded[kind] = {"intent": spec["intent"], "kept": sorted(kept), "left_out": sorted(left_out - kept)}
    for kind, entries in filtered.items():
        data[INTENT_LISTS[kind]] = entries
    return recorded


JS_LANGUAGES = frozenset({"typescript", "tsx", "javascript"})


def typed_param(param, language: str | None) -> str | None:
    """One parameter as the provenance map writes it ('userId: string',
    'options?: TokenOptions', 'retries: int = 3'); a string is kept."""
    if isinstance(param, str):
        return param
    if not isinstance(param, dict):
        return None
    name, type_, default = param.get("name"), param.get("type"), param.get("default")
    if not name:
        return type_ or None
    text = str(name)
    if param.get("optional") and default is None and language in JS_LANGUAGES and not text.startswith("..."):
        text += "?"
    if type_:
        text += f": {type_}"
    if default is not None:
        text += f" = {default}"
    return text


# provenance: the header keys stdin may give, and the default of each (REQUIRED: no default).
REQUIRED = object()
MAP_HEADER = {
    "provenance_version": "2.0",
    "skill_name": None,  # the inventory's
    "skill_type": "single",
    "source_repo": REQUIRED,
    "source_commit": REQUIRED,
    "source_ref": None,
    "generated_at": None,  # now
}


def _labels(export: dict) -> dict:
    """The labels the tool that found `export` gives its entry (compile.md §6)."""
    if export.get("extraction_method") == "ast-grep":
        return {"confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": export.get("ast_node_type"),
                "signature_source": "T1"}
    return {"confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
            "signature_source": "T1-low"}


def provenance_entries(data: dict) -> tuple[list[dict], list[str]]:
    """(the provenance map entry of every export but one marked `public: false`, the functions among them with no
    params)."""
    entries: list[dict] = []
    unsigned: list[str] = []
    for export in data.get("exports") or []:
        if not isinstance(export, dict) or export.get("public") is False:
            continue
        raw = export.get("params")
        params = None
        if isinstance(raw, list):
            params = [s for s in (typed_param(p, export.get("language")) for p in raw) if s is not None]
        elif export.get("export_type") == "function":
            unsigned.append(f"{export.get('export_name')} ({export.get('source_file')})")
        entries.append({
            "export_name": export.get("export_name"),
            "export_type": export.get("export_type"),
            "params": params,
            "return_type": export.get("return_type") if params is not None else None,
            "source_file": export.get("source_file"),
            "source_line": export.get("source_line"),
            **_labels(export),
        })
    return entries, unsigned


def map_header(data: dict, given) -> dict:
    """The provenance map's header: stdin's keys over the defaults."""
    if not isinstance(given, dict):
        raise InventoryError("stdin must hold the map's header, a JSON object with source_repo and source_commit")
    unknown = sorted(set(given) - set(MAP_HEADER))
    if unknown:
        raise InventoryError(f"the map's header takes only {', '.join(MAP_HEADER)}; not {', '.join(unknown)}")
    missing = [key for key, default in MAP_HEADER.items() if default is REQUIRED and key not in given]
    if missing:
        raise InventoryError(f"the map's header needs {', '.join(missing)} (null when unknown)")
    defaults = {"skill_name": data.get("skill_name"),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return {key: given[key] if key in given else defaults.get(key, default) for key, default in MAP_HEADER.items()}


def provenance_map(data: dict, header) -> tuple[dict, list[str]]:
    """(the provenance map of the inventory, the functions with no params)."""
    entries, unsigned = provenance_entries(data)
    return {**map_header(data, header), "entries": entries}, unsigned


def add_map_entries(provenance: dict, payload, off: frozenset = frozenset()) -> tuple[int, int, list[dict]]:
    """Append stdin's `entries` and `file_entries` to the map; return (added, duplicates, {name, file} of each entry
    not added because `off`, the (export_name, source_file) of the inventory's exports marked `public: false`,
    holds it)."""
    if not isinstance(payload, dict) or not payload or set(payload) - {"entries", "file_entries"}:
        raise InventoryError('stdin must hold {"entries": [...], "file_entries": [...]} (either list, or both)')
    keys = {"entries": ("export_name", "source_file"), "file_entries": ("file_name",)}
    added = duplicates = 0
    not_public: list[dict] = []
    for field, items in payload.items():
        if not isinstance(items, list) or not all(isinstance(e, dict) for e in items):
            raise InventoryError(f"{field} must be a list of objects")
        need = keys[field][0]
        if not all(isinstance(e.get(need), str) and e[need] for e in items):
            raise InventoryError(f"every {field} item needs a {need}")
        target = provenance.setdefault(field, [])
        if not isinstance(target, list):
            raise InventoryError(f"the map's {field} is not a list")
        held = {tuple(e.get(k) for k in keys[field]) for e in target if isinstance(e, dict)}
        for item in items:
            key = tuple(item.get(k) for k in keys[field])
            if field == "entries" and (item.get("export_name"), _norm_path(item.get("source_file"))) in off:
                not_public.append({"name": item.get("export_name"), "file": item.get("source_file")})
                continue
            if key in held:
                duplicates += 1
                continue
            held.add(key)
            target.append(item)
            added += 1
    return added, duplicates, not_public


def rules_yaml(data: dict, language: str) -> str:
    """extraction-rules.yaml: how the skill was extracted, for a later run to reproduce it."""
    head = {"skill_name": data.get("skill_name"), "language": language, "tier": data.get("tier"),
            "extraction_mode": data.get("extraction_mode")}
    rules = data.get("extraction_rules") if isinstance(data.get("extraction_rules"), dict) else {}
    lines = ["# Generated by skf-extraction-inventory.py rules from the extraction inventory."]
    lines += _yaml_lines({**head, **rules})
    return "\n".join(lines) + "\n"


def _yaml_scalar(value) -> str:
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, list):
        return "[]"
    return json.dumps(value, ensure_ascii=False)  # JSON scalars are YAML scalars


def _yaml_key(key) -> str:
    text = str(key)
    return text if YAML_KEY_RE.fullmatch(text) else json.dumps(text, ensure_ascii=False)


def _yaml_lines(value, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    items = value.items() if isinstance(value, dict) else ((None, v) for v in value)
    for key, item in items:
        lead = f"{pad}{_yaml_key(key)}:" if isinstance(value, dict) else f"{pad}-"
        if isinstance(item, (dict, list)) and item:
            nested = _yaml_lines(item, indent + 1)
            if isinstance(value, list):
                lines.append(f"{lead} {nested[0].lstrip()}")
                lines.extend(nested[1:])
            else:
                lines.append(lead)
                lines.extend(nested)
        else:
            lines.append(f"{lead} {_yaml_scalar(item)}")
    return lines


def write(path: Path, data: dict | str) -> None:
    """Write `data` (JSON, or text as it is) to `path` through a temporary file and one rename."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise InventoryError(f"cannot write {path.as_posix()}: {exc}") from exc


def _result(path: Path, data: dict, **extra) -> dict:
    return {"status": "ok", "inventory": path.as_posix(), "extraction_mode": data.get("extraction_mode"),
            "counts": counts(data), **extra}


def _stdin_json():
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else None
    except ValueError as exc:
        raise InventoryError(f"stdin is not JSON: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-extraction-inventory.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    inventory_help = "the extraction inventory JSON"
    p_init = sub.add_parser("init", help="write a new inventory from the runner's and the detector's JSON")
    p_init.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    p_init.add_argument("--skill", required=True, help="the skill name")
    p_init.add_argument("--mode", required=True, choices=MODES, help="the extraction mode")
    p_init.add_argument("--tier", required=True, choices=TIERS, help="the forge tier")
    p_init.add_argument("--extraction", type=Path, default=None,
                        help="the recipe runner's JSON (skf-extract-public-api.py --mode full -o)")
    p_init.add_argument("--detected", type=Path, default=None,
                        help="the script and asset detector's JSON (skf-detect-scripts-assets.py detect)")
    p_add = sub.add_parser("add", help="append a JSON list from stdin to one of the inventory's lists")
    p_add.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    p_add.add_argument("--field", required=True, choices=FIELDS, help="the list to append to")
    p_patch = sub.add_parser("patch", help="set signature, params and return_type on exports from stdin")
    p_patch.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    p_set = sub.add_parser("set", help="set the keys of a JSON object from stdin")
    p_set.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    p_rules = sub.add_parser("rules", help="write extraction-rules.yaml from the inventory")
    p_rules.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    p_rules.add_argument("--language", required=True, help="the brief's language")
    p_rules.add_argument("--target", required=True, type=Path, help="the extraction-rules.yaml to write")
    p_prov = sub.add_parser("provenance", help="write the provenance map from the inventory, the header on stdin")
    p_prov.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    p_prov.add_argument("--target", required=True, type=Path, help="the provenance-map.json to write")
    p_prov.add_argument("--add-entries", action="store_true",
                        help="append stdin's entries and file_entries to the map at --target instead")
    p_summary = sub.add_parser("summary", help="print the inventory's counts")
    p_summary.add_argument("--inventory", required=True, type=Path, help=inventory_help)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    path = args.inventory
    try:
        if args.command == "init":
            extraction = _read_json(args.extraction, "runner JSON") if args.extraction else None
            detected = _read_json(args.detected, "detector JSON") if args.detected else None
            data = init(args.skill, args.mode, args.tier, extraction, detected)
            write(path, data)
            result = _result(path, data)
        elif args.command == "provenance" and args.add_entries:
            data = load(path)
            provenance = _read_json(args.target, "provenance map")
            if not isinstance(provenance, dict) or not isinstance(provenance.get("entries"), list):
                raise InventoryError(f"the provenance map {args.target.as_posix()} has no entries list: "
                                     "run provenance without --add-entries first")
            off = frozenset((item["name"], _norm_path(item["file"])) for item in _not_public(data))
            added, duplicates, not_public = add_map_entries(provenance, _stdin_json(), off)
            write(args.target, provenance)
            result = {"status": "ok", "target": args.target.as_posix(), "entries": len(provenance["entries"]),
                      "file_entries": len(provenance.get("file_entries") or []), "added": added,
                      "duplicates": duplicates, "not_public": not_public}
        elif args.command == "provenance":
            provenance, unsigned = provenance_map(load(path), _stdin_json())
            write(args.target, provenance)
            result = {"status": "ok", "target": args.target.as_posix(), "entries": len(provenance["entries"]),
                      "unsigned": unsigned}
        elif args.command == "rules":
            text = rules_yaml(load(path), args.language)
            write(args.target, text)
            result = {"status": "ok", "target": args.target.as_posix(), "bytes": len(text.encode("utf-8"))}
        else:
            data = load(path)
            if args.command == "summary":
                result = _result(path, data, not_public=_not_public(data))
            elif args.command == "add":
                payload = _stdin_json()
                added, duplicates, dropped = add(data, args.field, [] if payload is None else payload)
                write(path, data)
                result = _result(path, data, added=added, duplicates=duplicates, dropped=dropped)
            elif args.command == "patch":
                payload = _stdin_json()
                patched, unmatched, ambiguous = patch(data, [] if payload is None else payload)
                write(path, data)
                result = _result(path, data, patched=patched, unmatched=unmatched, ambiguous=ambiguous)
            else:
                payload = _stdin_json()
                keys, dropped = set_fields(data, {} if payload is None else payload)
                write(path, data)
                result = _result(path, data, set=keys, dropped=dropped)
    except InventoryError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdin and the JSON streams to UTF-8 (a Windows console uses cp1252)."""
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
