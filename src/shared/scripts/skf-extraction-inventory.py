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

  add      --inventory <file> --field exports|t2_annotations|t3_items|warnings
           Read a JSON list on stdin (objects; strings for warnings) and
           append it to that list. An entry already in the list (equal
           JSON; for exports, the same export_name and source_file) is not
           added twice and counts in `duplicates`. An exports entry needs an
           export_name; a missing confidence, extraction_method,
           ast_node_type or ast_recipe defaults to T1-low, source-read,
           null and null (an export read by eye). A t3_items entry whose
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
           changes anything.

  set      --inventory <file>
           Read a JSON object on stdin and set each of its keys: top_exports,
           co_imports, promoted_docs, component_catalog (lists),
           authoritative_files_scan (an object or null), files_scanned (an
           integer), counts and arms (objects, merged into what is there)
           and intent_mapping. intent_mapping maps `scripts` and `assets`
           to {"intent": "<free text>", "kept": [source_file, ...]}: the
           inventory keeps only the kept entries of that list and records
           the others in the mapping's `left_out`.

  rules    --inventory <file> --language <language> --target <file>
           Write extraction-rules.yaml (the skill, its language, tier and
           extraction mode, and the inventory's extraction_rules) to
           --target. The inventory is not changed.

  summary  --inventory <file>
           Print the inventory's counts without changing it.

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
    "t2_annotations": [...], "t3_items": [...], "warnings": ["..."]
  }

Output (stdout, exit 0), for every subcommand but rules:

  {
    "status": "ok",
    "inventory": "<path, / separators>",
    "extraction_mode": "...",
    "counts": {"files_scanned": N | null, "exports": N, "t1": N,
               "t1_low": N, "by_type": {"<export_type>": N, ...},
               "top_exports": N, "co_imports": N, "scripts": N,
               "assets": N, "t2_annotations": N, "t2_past": N,
               "t2_future": N, "functions_enriched": N, "t3_items": N,
               "items": N},
    "added": N, "duplicates": N, "dropped": ["name"],   # add
    "patched": N, "unmatched": [...], "ambiguous": [...],  # patch
    "set": ["key", ...]                                 # set
  }

`items` is exports plus t3_items: what compile can document. t1 and t1_low
count the exports by their `confidence`, by_type by their `export_type`.
t2_past and t2_future count the T2 annotations by their `temporal`, and
functions_enriched the distinct export_name values among them. rules
prints {"status": "ok", "target": "<path>", "bytes": N}.

Exit codes:
  0  success
  1  input error, nothing changed: an inventory that is missing, not JSON
     or has no exports list, an --extraction or --detected file that
     cannot be read, a stdin payload of the wrong shape, an unknown key or
     a kept file the inventory does not list, or a write that failed
  2  usage error (argparse)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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


def counts(data: dict) -> dict:
    exports = [e for e in data["exports"] if isinstance(e, dict)]
    notes = [n for n in data.get("t2_annotations") or [] if isinstance(n, dict)]

    def _length(key: str) -> int:
        value = data.get(key)
        return len(value) if isinstance(value, list) else 0

    by_type: dict[str, int] = {}
    for export in exports:
        kind = export.get("export_type")
        if isinstance(kind, str) and kind:
            by_type[kind] = by_type.get(kind, 0) + 1
    files = data.get("files_scanned")
    return {
        "files_scanned": files if isinstance(files, int) else None,
        "exports": len(data["exports"]),
        "t1": sum(1 for e in exports if e.get("confidence") == "T1"),
        "t1_low": sum(1 for e in exports if e.get("confidence") == "T1-low"),
        "by_type": dict(sorted(by_type.items())),
        "top_exports": _length("top_exports"),
        "co_imports": _length("co_imports"),
        "scripts": _length("scripts_inventory"),
        "assets": _length("assets_inventory"),
        "t2_annotations": _length("t2_annotations"),
        "t2_past": sum(1 for n in notes if n.get("temporal") == "T2-past"),
        "t2_future": sum(1 for n in notes if n.get("temporal") == "T2-future"),
        "functions_enriched": len({n["export_name"] for n in notes if isinstance(n.get("export_name"), str)}),
        "t3_items": _length("t3_items"),
        "items": len(data["exports"]) + _length("t3_items"),
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


def init(skill: str, mode: str, tier: str, extraction: dict | None = None, detected: dict | None = None) -> dict:
    """A new inventory, seeded from the runner's JSON and the detector's JSON."""
    data: dict = {
        "skill_name": skill, "extraction_mode": mode, "tier": tier, "files_scanned": None,
        "exports": [], "top_exports": [], "aggregates": {}, "counts": {}, "arms": {},
        "scripts_inventory": [], "assets_inventory": [], "intent_mapping": {}, "co_imports": [],
        "promoted_docs": [], "authoritative_files_scan": None, "extraction_rules": {},
        "t2_annotations": [], "t3_items": [], "warnings": [],
    }
    if extraction is not None:
        if not isinstance(extraction, dict):
            raise InventoryError("the --extraction file is not a JSON object")
        diff = extraction.get("entry_point_diff")
        internal = {(i.get("name"), i.get("source_file"))
                    for i in (diff.get("internal") or [] if isinstance(diff, dict) else []) if isinstance(i, dict)}
        for record in extraction.get("exports") or []:
            if not isinstance(record, dict):
                continue
            export = dict(record)
            export.setdefault("confidence", "T1")
            export.setdefault("extraction_method", "ast-grep")
            if (export.get("export_name"), export.get("source_file")) in internal:
                export["internal"] = True
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
    if field == "exports":
        if not all(isinstance(e.get("export_name"), str) and e["export_name"] for e in entries):
            raise InventoryError("every exports entry needs an export_name")
        entries = [{**BY_EYE_DEFAULTS, **e} for e in entries]
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


def set_fields(data: dict, values: dict) -> list[str]:
    """Set the keys of `values` on the inventory (see the module docstring); return the keys set."""
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
    for key, value in values.items():
        if key == "intent_mapping":
            data["intent_mapping"] = {**(data.get("intent_mapping") or {}), **mapping}
        elif SETTABLE[key][1]:
            data[key] = {**(data.get(key) if isinstance(data.get(key), dict) else {}), **value}
        else:
            data[key] = value
    return list(values)


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
        elif args.command == "rules":
            text = rules_yaml(load(path), args.language)
            write(args.target, text)
            result = {"status": "ok", "target": args.target.as_posix(), "bytes": len(text.encode("utf-8"))}
        else:
            data = load(path)
            if args.command == "summary":
                result = _result(path, data)
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
                keys = set_fields(data, {} if payload is None else payload)
                write(path, data)
                result = _result(path, data, set=keys)
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
