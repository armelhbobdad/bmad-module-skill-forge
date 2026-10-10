#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF test-skill coverage inputs: the counts, name sets and candidates coverage-check reads.

coverage-check.md decides which denominator clause applies to a skill and
whether a bookkeeping variant is a real export; everything it counts, folds
or unions on the way runs here, so no count is made by hand. Three
subcommands, each reading files and writing one JSON object:

  census    docs-only detection. Counts the citations SKILL.md and each .md
            file directly in references/ write, by form: `[EXT:` against
            the local forms `[AST:`, `[SRC:` and a stack's `[from skill:`
            (`[QMD:` and `[DOC:` are counted and decide nothing). A skill is
            docs-only when it cites `[EXT:` and no local form.

  metadata  the metadata.json and provenance-map counts. Cluster A
            (`stats.exports_public_api`, the `exports[]` length) and Cluster
            B (`stats.exports_documented`, the provenance entry names, the
            `confidence_distribution`) under the keys
            check-metadata-coherence.py reads; the provenance named exports
            (`::` impl-block methods left out); the inflation signature
            (`stats.exports_documented` equals `stats.effective_denominator`)
            with the declared names verify-declared-numerator.py looks up
            (the `exports[]` names, else the provenance named exports); and,
            for a stack, its composition surface: the distinct provenance
            named exports when the map has entries, else each library and
            each integration pair (`{a} + {b}`, as the stack's Library Pair
            Integrations heading writes it), as reconcile-coverage.py's
            stack branch takes them.

  surface   the enumerated source surface, from every input given (their
            union):
              --extraction  skf-extract-public-api.py --mode full output:
                            the names in entry_point_diff.public, a
                            namespace with a `members` list given as its
                            members (the names its module passes on, each
                            at its file, once with a public name of the
                            same name and file), less the outside_scope
                            names (defined in a file the brief scopes
                            out); exports[] only gives each name's
                            kind, line and signature line, looked up by the
                            name its defining file gives it (an aliased
                            re-export's `local`) and that file.
                            extraction_gaps are listed to read by eye, and
                            the runner's warnings join `warnings`. A Python
                            top __init__.py inside the folder of another top
                            that exports a public name (a sub-package
                            behind a folder with no __init__.py) is no
                            barrel, unless scope.include or tier_a_include
                            lists its file: its names leave `all`, `root`
                            and the umbrella ratio and are listed in
                            `excluded.nestedEntries`, but keep their records
                            (so the scope.include and tier_a_include sets)
                            and their outside_scope and extraction_gaps
                            rows. When the runner lists an
                            include glob that matches no file
                            (scope.unmatched_include: a brief older than the
                            source), each outside_scope name a root entry
                            point exports is restored, with the file and
                            line of its outside_scope row, when no include,
                            exclude or declined scope-expansion amendment
                            (latest action skipped or demoted-include, from
                            --brief) matches its file. A tier_a_include glob
                            the runner lists as matching no file
                            (scope.unmatched_tier_a_include, [] when the key
                            is absent) counts no name.
              --quick       skf-extract-public-api.py --mode quick output
              --per-file    a subagent's per-file result (exports_found and
                            types_found), schema-checked as
                            score-signatures.py checks it
              --name        a name read by eye whose file is not known
              --provenance  the provenance entries' named exports (State 2)
              --metadata    the metadata.json exports[] names (States 2, 3)
            A surface read from the source (--extraction, --quick or
            --per-file) takes no name from --provenance and --metadata:
            they are the baselines of the candidates and guards. Without
            one, with --provenance and --metadata both, `state2` gives the
            provenance count, the metadata count and their union count,
            which compute-score.py turns into the State 2 divergence. --fold
            folds the bookkeeping variants among the provenance and metadata
            names to their base name (`X_def`, `X_exact`, `a11y_X`, and
            `<prefix>X` for each --fold-prefix when `X` is itself a name)
            unless --keep names the variant as a real export, and
            `canonical` gives the provenance map's fold summary. --brief
            gives the skill brief's scope, language and scope-expansion
            amendments; an extraction's recorded scope wins over its scope.

Name sets (surface `sets`, each sorted): `all` (the union above, less a
nested Python top's names);
`scope.include` and `tier_a_include` when the scope has those globs and a
record names a file: the names whose file (an extraction's definition file,
the quick output's source_file, a per-file result's file, a provenance
entry's source_file) matches a glob of the list and no scope.exclude glob,
so a name with no file is in `all` only (a tier_a_include glob an
extraction lists as matching no file is left out of the list, and with every
glob left out there is no tier_a_include set); and, from an extraction only,
`subpaths` (the names a non-root `exports` map subpath without `*` reaches)
and `root` (the names the root entry points reach). reconcile-coverage.py
and score-signatures.py --surface-set pick one.

Candidates and guards (with an extraction, --brief or --metadata): each
set's count, the metadata `stats.effective_denominator` (--metadata), and
the extractor's own effective_denominator and its basis. Both guards run
only on a surface read from the source. The deflation guard compares the
re-derived scope.include set (the `all` set without one) with
`stats.effective_denominator` and fires above DEFLATION_PCT when no
tier_a_include glob matches a file (the scope has none, or the extraction
lists each as matching no file); the inflation guard compares the
scope.include set with the provenance entry count (--provenance) and fires
above INFLATION_PCT under the same condition; the umbrella ratio (an
extraction only) is the share of the root entry points' names that are
re-exports (a namespace with `members` counting as its members there
too, each a re-export), and above UMBRELLA_RATIO the barrel is an
umbrella; the
stale-scope guard (an extraction with scope.include or tier_a_include only)
fires when the runner lists an include or tier_a_include glob that matches
no file, and lists those globs (`unmatchedInclude`,
`unmatchedTierAInclude`) and the names restored for the include globs, each
with its file and line (`restored`). Globs follow
skf-extract-public-api.py: `**` spans any number of path segments, none
included, and `*` and `?` stay inside one.

Fallback verdict: `extraction.fallback.needed` is true when the extractor
found no ast-grep (`no-ast-grep`), read no file in scope, read files only
in languages it has no recipe for (`files_without_recipes` and no export),
or found files no recipe reads while the skill's language (the --brief
`language`, else the metadata.json `language`) is not one RECIPE_LANGUAGES
holds, so the per-file scan has to run instead. An `incomplete` run keeps
its exports; `extraction.readByEye` lists the files its errors and file
issues name.

Usage:
  uv run load-coverage-inputs.py census --skill-dir <dir> [--output <file>]
  uv run load-coverage-inputs.py metadata --metadata <metadata.json> \\
      [--provenance <provenance-map.json>] [--output <file>]
  uv run load-coverage-inputs.py surface [--extraction <file>] [--quick <file>]... \\
      [--per-file <file>]... [--name <name>]... [--provenance <file>] [--metadata <file>] \\
      [--brief <skill-brief.yaml>] [--fold] [--fold-prefix <prefix>]... [--keep <name>]... \\
      [--output <file>]

Exit codes:
  0  the result was printed (and written to --output)
  1  an input file is missing, unreadable or not the JSON (or the YAML
     brief) it should be (one line on stderr)
  2  a per-file result breaks the schema: {"valid": false, "violations":
     [...]} names each breach and nothing is written to --output; or a
     usage error (argparse)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import posixpath
import re
import sys
from pathlib import Path

DEFLATION_PCT = 25
INFLATION_PCT = 25
UMBRELLA_RATIO = 0.5
METHOD_SEPARATOR = "::"
CITATION_FORMS = {
    "EXT": "[EXT:",
    "AST": "[AST:",
    "SRC": "[SRC:",
    "from skill": "[from skill:",
    "QMD": "[QMD:",
    "DOC": "[DOC:",
}
LOCAL_FORMS = ("AST", "SRC", "from skill")
# Bookkeeping variants folded to their base name, in rule order.
FOLD_SUFFIXES = ("_def", "_exact")
FOLD_PREFIX = "a11y_"
ROOT_SUBPATHS = (None, ".")
# The latest action of a scope-expansion amendment that keeps its path out of scope.
DECLINED_ACTIONS = ("skipped", "demoted-include")
# The languages skf-extract-public-api.py's recipes read (its LANGUAGE_FAMILIES).
RECIPE_LANGUAGES = frozenset({"python", "rust", "go", "golang", "typescript", "ts", "tsx", "javascript", "js",
                              "jsx", "vue"})


class InputError(Exception):
    """An input file that cannot be used."""


class SchemaError(Exception):
    """Per-file results that break the schema: `violations` names each breach."""

    def __init__(self, violations: list[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


_SIBLINGS: dict[str, object] = {}
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"


def _sibling(filename: str, folder: Path | None = None):
    """A script beside this one, loaded once: validate-inventory.py (the doc
    text) and score-signatures.py (the per-file result schema); or, with
    `folder`, one in that folder: SHARED_SCRIPTS'
    skf-resolve-authoritative-files.py (a skill brief's YAML)."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = (folder or Path(__file__).resolve().parent) / filename
        spec = importlib.util.spec_from_file_location("skf_" + filename[:-3].replace("-", "_"), path)
        if spec is None or spec.loader is None or not path.is_file():
            where = f"in {folder}" if folder else f"beside {Path(__file__).name}"
            raise InputError(f"{filename} not found {where}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[filename] = module
    return module


def round2(value: float) -> float:
    """Round to 2 decimals with JS-compatible half-up rounding (matches compute-score.py)."""
    return math.floor(value * 100 + 0.5) / 100


def _read_json(path: str, flag: str):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {flag} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"{flag} {path} is not JSON: {exc.msg}") from exc


def _object(path: str, flag: str) -> dict:
    data = _read_json(path, flag)
    if not isinstance(data, dict):
        raise InputError(f"{flag} {path} is not a JSON object")
    return data


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _export_name(item) -> str | None:
    """The name of a metadata exports[] item: a string, or an object's name."""
    if isinstance(item, str):
        return item or None
    if isinstance(item, dict):
        for key in ("name", "export_name"):
            if isinstance(item.get(key), str) and item[key]:
                return item[key]
    return None


def _entries(provenance: dict | None) -> list[dict]:
    entries = provenance.get("entries") if isinstance(provenance, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _entry_names(provenance: dict | None) -> list[str]:
    return [e["export_name"] for e in _entries(provenance)
            if isinstance(e.get("export_name"), str) and e["export_name"]]


# --------------------------------------------------------------------------
# census
# --------------------------------------------------------------------------


def census(skill_dir: str) -> dict:
    root = Path(skill_dir)
    if not (root / "SKILL.md").is_file():
        raise InputError(f"--skill-dir {skill_dir} holds no SKILL.md")
    try:
        text = _sibling("validate-inventory.py").load_doc_text(skill_dir)
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read the skill text under {skill_dir}: {exc}") from exc
    counts = {form: text.count(marker) for form, marker in CITATION_FORMS.items()}
    local = sum(counts[form] for form in LOCAL_FORMS)
    refs = root / "references"
    files = ["SKILL.md"] + ([f"references/{p.name}" for p in sorted(refs.glob("*.md"))] if refs.is_dir() else [])
    return {
        "citations": counts,
        "localCitations": local,
        "docsOnly": counts["EXT"] > 0 and local == 0,
        "files": files,
    }


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------


def _pair_name(pair) -> str | None:
    if isinstance(pair, str):
        return pair or None
    if isinstance(pair, (list, tuple)) and len(pair) == 2 and all(isinstance(p, str) and p for p in pair):
        return f"{pair[0]} + {pair[1]}"
    if isinstance(pair, dict) and all(isinstance(pair.get(k), str) and pair[k] for k in ("a", "b")):
        return f"{pair['a']} + {pair['b']}"
    return None


def _library_name(lib) -> str | None:
    if isinstance(lib, str):
        return lib or None
    if isinstance(lib, dict) and isinstance(lib.get("name"), str) and lib["name"]:
        return lib["name"]
    return None


def metadata_inputs(meta: dict, provenance: dict | None) -> dict:
    stats = meta.get("stats") if isinstance(meta.get("stats"), dict) else {}
    exports = meta.get("exports")
    names = [n for n in (_export_name(e) for e in exports) if n] if isinstance(exports, list) else []
    entry_names = _entry_names(provenance) if provenance is not None else None
    named = sorted({n for n in entry_names or [] if METHOD_SEPARATOR not in n})
    dist = stats.get("confidence_distribution")
    if not isinstance(dist, dict):
        dist = meta.get("confidence_distribution") if isinstance(meta.get("confidence_distribution"), dict) else None
    if dist is not None:
        dist = {tier: dist[tier] for tier in ("t1", "t1_low", "t2", "t3") if _count(dist.get(tier)) is not None}
    documented = _count(stats.get("exports_documented"))
    effective = _count(stats.get("effective_denominator"))
    skill_type = meta.get("skill_type") if isinstance(meta.get("skill_type"), str) else None

    stack = None
    if skill_type == "stack":
        if named:
            stack = {"basis": "provenance", "denominator": len(named), "compositionNames": named}
        else:
            libraries = [n for n in (_library_name(lib) for lib in meta.get("libraries") or []) if n]
            pairs = [n for n in (_pair_name(p) for p in meta.get("integration_pairs") or []) if n]
            stack = {"basis": "composition", "denominator": len(libraries) + len(pairs),
                     "compositionNames": libraries + pairs}

    return {
        "skillType": skill_type,
        "scopeType": meta.get("scope_type") if isinstance(meta.get("scope_type"), str) else None,
        "clusterA": {
            "exports_public_api": _count(stats.get("exports_public_api")),
            "exports_length": len(exports) if isinstance(exports, list) else None,
        },
        "clusterB": {"exports_documented": documented},
        "provenanceExportNames": entry_names,
        "confidenceDistribution": dist or None,
        "namedExports": {"count": len(named), "names": named} if entry_names is not None else None,
        "effectiveDenominator": effective,
        "inflationSignature": documented is not None and effective is not None and documented == effective,
        "declaredNames": sorted(set(names)) if names else named,
        "stack": stack,
    }


# --------------------------------------------------------------------------
# surface
# --------------------------------------------------------------------------


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_match(rel_path: str, pattern: str) -> bool:
    """skf-resolve-authoritative-files.py's glob rule, which the extractor applies."""
    compiled = _GLOB_CACHE.get(pattern)
    if compiled is None:
        parts = pattern.split("/")
        out: list[str] = []
        for i, part in enumerate(parts):
            if part == "**":
                out.append("(?:.*/)?" if i + 1 < len(parts) else ".*")
                continue
            out.append("".join("[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch) for ch in part))
            if i + 1 < len(parts):
                out.append("/")
        compiled = re.compile("^" + "".join(out) + "$")
        _GLOB_CACHE[pattern] = compiled
    return bool(compiled.match(rel_path))


def _norm(path) -> str:
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _record(name, kind, file, line, signature_line, origin) -> dict:
    return {"name": name, "kind": kind, "file": file, "line": line, "signatureLine": signature_line,
            "origin": origin}


def _globs(value) -> list[str]:
    return [g for g in (_norm(v) for v in value if isinstance(v, str)) if g] if isinstance(value, list) else []


def _scope(include, exclude, tier_a_include) -> dict:
    return {"include": _globs(include), "exclude": _globs(exclude), "tier_a_include": _globs(tier_a_include)}


def read_brief(path: str) -> dict:
    """A skill brief's scope globs and language, the fields skf-extract-public-api.py reads, and the
    latest action of each scope-expansion amendment by its path (`amendments`), a legacy headless skip
    read as a deferral as skf-resolve-authoritative-files.py reads it."""
    try:
        import yaml  # --brief only; `uv run` installs it from the header
    except ImportError as exc:
        raise InputError("--brief is read with PyYAML: run the script with `uv run`") from exc
    resolver = _sibling("skf-resolve-authoritative-files.py", SHARED_SCRIPTS)
    try:
        data = resolver.parse_brief_yaml(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read --brief {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise InputError(f"--brief {path} is not valid YAML: {' '.join(str(exc).split())}") from exc
    if not isinstance(data, dict):
        raise InputError(f"--brief {path} is not a YAML mapping")
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    amendments: dict[str, str] = {}
    for amend in scope.get("amendments") if isinstance(scope.get("amendments"), list) else []:
        if isinstance(amend, dict) and amend.get("category") == "scope-expansion":
            amended = _norm(amend["path"]) if isinstance(amend.get("path"), str) else ""
            action = resolver._amendment_action(amend)
            if amended and action is not None:
                amendments[amended] = action
    return {"scope": _scope(scope.get("include"), scope.get("exclude"), scope.get("tier_a_include")),
            "language": data.get("language") if isinstance(data.get("language"), str) else None,
            "amendments": amendments}


def matching(records: list[dict], globs: list[str], excludes: list[str]) -> list[str]:
    """The names whose record names a file one of `globs` matches and no exclude glob does."""
    return sorted({r["name"] for r in records if r.get("file")
                   and any(glob_match(_norm(r["file"]), g) for g in globs)
                   and not any(glob_match(_norm(r["file"]), g) for g in excludes)})


def _nested_tops(entry_files: list[dict], named: set[str], exporting: set[str]) -> dict[str, str]:
    """{top: the outermost top whose folder holds it} for each Python top
    __init__.py inside the folder of another top that `exporting` lists (one
    that exports at least one public name), a sub-package behind a folder
    with no __init__.py, unless `named` lists its file. A top that exports
    nothing (a stray __init__.py at the source root, say) nests no other."""
    tops = sorted({e["file"] for e in entry_files
                   if e.get("language") == "python" and isinstance(e.get("file"), str) and e["file"]})
    nested = {}
    for top in tops:
        folder = posixpath.dirname(top)
        outer = [o for o in tops if o != top and o in exporting
                 and (not posixpath.dirname(o) or folder.startswith(posixpath.dirname(o) + "/"))]
        if outer and _norm(top) not in named:
            nested[top] = min(outer, key=lambda o: (o.count("/"), o))
    return nested


def _members_in_place(public: list[dict]) -> list[dict]:
    """The public names, a namespace item with a `members` list (the names
    its module passes on, `pkg.sub.name`) given as its members, each with
    the namespace's entry and language and `via: namespace`. A member whose
    name and file another public name, or an earlier member, has is left
    out; a namespace whose members the runner could not read (null), or one
    from a runner that lists none, stays itself."""
    expanded = [p for p in public if not (p.get("via") == "namespace" and isinstance(p.get("members"), list))]
    seen = {(p["name"], p.get("file")) for p in expanded}
    for item in public:
        if item.get("via") != "namespace" or not isinstance(item.get("members"), list):
            continue
        for member in item["members"]:
            if not isinstance(member, dict) or not isinstance(member.get("name"), str) or not member["name"]:
                continue
            key = (member["name"], member.get("file"))
            if key in seen:
                continue
            seen.add(key)
            expanded.append({"name": member["name"], "language": item.get("language"), "entry": item.get("entry"),
                             "via": "namespace", "local": member.get("local"), "file": member.get("file"),
                             "line": member.get("line")})
    return expanded


def from_extraction(data: dict, language: str | None = None, brief: dict | None = None) -> dict:
    """The public surface of an extraction, less what lies outside scope,
    plus the root exports a stale scope.include glob left out. A nested
    Python top's records come apart (`nestedRecords`): they count in the
    scope sets, not in `all`."""
    if data.get("mode") != "full":
        raise InputError("--extraction is not skf-extract-public-api.py --mode full output")
    diff = data.get("entry_point_diff") if isinstance(data.get("entry_point_diff"), dict) else {}
    public = _members_in_place([p for p in diff.get("public") or []
                                if isinstance(p, dict) and isinstance(p.get("name"), str)])
    outside = [o for o in diff.get("outside_scope") or [] if isinstance(o, dict)]
    gaps = [g for g in diff.get("extraction_gaps") or [] if isinstance(g, dict)]

    # The scope: the one the extractor recorded, else the brief's.
    recorded = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    scope = _scope(recorded.get("include"), recorded.get("exclude"), recorded.get("tier_a_include"))
    if not any(scope.values()) and brief is not None:
        scope = brief["scope"]

    entry_points = data.get("entry_points") if isinstance(data.get("entry_points"), dict) else {}
    entry_files = [e for e in entry_points.get("files") or [] if isinstance(e, dict)]
    # A Python top nested in another that exports a name is no barrel: its
    # names leave `all`, `root` and the umbrella ratio, and keep their
    # records (so the scope sets a specific-modules or stratified brief
    # counts) and their outside_scope and extraction_gaps rows.
    nested = _nested_tops(entry_files, set(scope["include"]) | set(scope["tier_a_include"]),
                          {p.get("entry") for p in public})
    nested_names = {top: sorted({p["name"] for p in public if p.get("entry") == top}) for top in nested}

    subpath_files = {e.get("file") for e in entry_files
                     if e.get("subpath") not in ROOT_SUBPATHS and "*" not in str(e.get("subpath"))}
    root_files = {e.get("file") for e in entry_files if e.get("subpath") in ROOT_SUBPATHS} - set(nested)

    # A scope.include glob that matches no file: the brief predates the
    # source, so a root export defined in a file no glob covers comes back,
    # unless the brief excludes or declined that file.
    unmatched = _globs(recorded.get("unmatched_include"))
    declined = [path for path, action in ((brief or {}).get("amendments") or {}).items()
                if action in DECLINED_ACTIONS]
    restored = [o for o in outside if unmatched and o.get("entry") in root_files
                and isinstance(o.get("name"), str) and isinstance(o.get("file"), str) and o["file"]
                and not any(glob_match(_norm(o["file"]), g)
                            for g in scope["include"] + scope["exclude"] + declined)]
    restored_at = {(o["name"], o["file"]): o.get("line") for o in restored}
    # A tier A glob that matches no file: the runner's list, never re-matched here.
    unmatched_tier_a = _globs(recorded.get("unmatched_tier_a_include"))
    outside = [o for o in outside if (o.get("name"), o.get("file")) not in restored_at]

    outside_keys = {(o.get("name"), o.get("file")) for o in outside}
    index = {(e.get("export_name"), e.get("source_file")): e
             for e in data.get("exports") or [] if isinstance(e, dict)}
    records, nested_records = [], []
    for info in public:
        name, file = info["name"], info.get("file")
        if (name, file) in outside_keys:
            continue
        if (name, file) in restored_at:
            # No recipe reads a file out of scope, so its kind is unknown: the
            # name carries the file and line of its outside_scope row.
            records.append(_record(name, None, file, restored_at[(name, file)], None, "restored"))
            continue
        # An aliased re-export (`export { Options as Config }`) is recorded
        # under the name its defining file gives it, `local`.
        found = index.get((info.get("local") or name, file)) or index.get((name, file))
        kind = found.get("export_type") if found else None
        (nested_records if info.get("entry") in nested else records).append(
            _record(name, None if kind == "re-export" else kind, file,
                    found.get("source_line") if found else info.get("line"),
                    found.get("signature_line") if found else None, "extraction"))

    root_names = [p for p in public if p.get("entry") in root_files]
    reexported = [p for p in root_names if p.get("via") not in (None, "declaration")]

    sets = {}
    if subpath_files:
        sets["subpaths"] = sorted({p["name"] for p in public if p.get("entry") in subpath_files})
    if root_files:
        sets["root"] = sorted({p["name"] for p in root_names})

    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    arms = data.get("arms") if isinstance(data.get("arms"), dict) else {}
    without = data.get("files_without_recipes") if isinstance(data.get("files_without_recipes"), dict) else {}
    status = data.get("status")
    reason = None
    if status == "no-ast-grep":
        reason = "no ast-grep the runner can run"
    elif not data.get("files_in_scope"):
        reason = "no file in scope"
    elif without and not data.get("exports"):
        reason = f"no recipe reads the files in scope ({', '.join(sorted(without))})"
    elif without and language and language.strip().lower() not in RECIPE_LANGUAGES:
        reason = (f"no recipe reads the skill's language, {language} "
                  f"({', '.join(sorted(without))} in scope)")
    read_by_eye = sorted({str(i["file"]) for i in data.get("file_issues") or []
                          if isinstance(i, dict) and i.get("file") and i.get("issue") != "no-recipes"}
                         | {str(e["first_file"]) for e in data.get("errors") or []
                            if isinstance(e, dict) and e.get("first_file")})
    return {
        "records": records,
        "nestedRecords": nested_records,
        "sets": sets,
        "outside": [{"name": o.get("name"), "file": o.get("file")} for o in outside],
        "nested": [{"entry": top, "within": nested[top], "names": nested_names[top]} for top in sorted(nested)],
        "staleScope": {"unmatchedInclude": unmatched, "unmatchedTierAInclude": unmatched_tier_a,
                       "restored": [{"name": o["name"], "file": o["file"], "line": o.get("line")}
                                    for o in sorted(restored, key=lambda o: (o["name"], o["file"]))]},
        "gaps": [{"name": g.get("name"), "file": g.get("file"), "line": g.get("line")} for g in gaps],
        "scope": scope,
        "umbrella": {
            "entries": sorted(f for f in root_files if f),
            "names": len(root_names),
            "reexported": len(reexported),
            "ratio": round2(len(reexported) / len(root_names)) if root_names else None,
            "umbrella": bool(root_names) and len(reexported) / len(root_names) > UMBRELLA_RATIO,
        },
        "extraction": {
            "status": status,
            "filesInScope": data.get("files_in_scope"),
            "truncated": data.get("truncated"),
            "effectiveDenominator": _count(counts.get("effective_denominator")),
            "effectiveDenominatorBasis": counts.get("effective_denominator_basis"),
            "exportsPublicApi": _count(counts.get("exports_public_api")),
            "arms": arms,
            "readByEye": read_by_eye,
            "fallback": {"needed": reason is not None, "reason": reason},
        },
    }


def from_quick(data: dict) -> list[dict]:
    exports = data.get("exports")
    if not isinstance(exports, list):
        raise InputError("--quick is not skf-extract-public-api.py --mode quick output (no exports list)")
    return [_record(e["name"], e.get("type"), e.get("source_file"), None, None, "quick")
            for e in exports if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]]


def from_per_file(path: str) -> tuple[list[dict], list[str]]:
    """(the records of one per-file result, its schema breaches)."""
    scorer = _sibling("score-signatures.py")
    try:
        text = Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read --per-file {path}: {exc}") from exc
    results, errors = scorer.parse_result_text(text, Path(path).name)
    if errors:
        return [], errors
    records = []
    for result in results:
        types = set(result.get("types_found") or [])
        for name in sorted(set(result.get("exports_found") or []) | types):
            if name:
                records.append(_record(name, "type" if name in types else None, result["file"], None, None,
                                       "per-file"))
    return records, []


def fold_names(names: list[str], prefixes: list[str], keep: set[str],
               tallied: set[str] | None = None) -> tuple[dict[str, str], dict]:
    """({variant: base}, the fold tally of `tallied`, else of every name) under the canonicalization rules."""
    present = set(names)
    variants: dict[str, str] = {}
    tally = {"_def": 0, "_exact": 0, FOLD_PREFIX: 0, "other": 0}
    for name in sorted(present):
        if name in keep:
            continue
        rule, base = None, None
        for suffix in FOLD_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                rule, base = suffix, name[: -len(suffix)]
                break
        if rule is None and name.startswith(FOLD_PREFIX) and len(name) > len(FOLD_PREFIX):
            rule, base = FOLD_PREFIX, name[len(FOLD_PREFIX):]
        if rule is None:
            for prefix in prefixes:
                if prefix and name.startswith(prefix) and name[len(prefix):] in present:
                    rule, base = "other", name[len(prefix):]
                    break
        if rule is not None:
            variants[name] = base
            if tallied is None or name in tallied:
                tally[rule] += 1
    return variants, tally


NO_UMBRELLA = {"entries": [], "names": 0, "reexported": 0, "ratio": None, "umbrella": False}


def surface(args: argparse.Namespace) -> dict:
    records: list[dict] = []
    sets: dict[str, list[str]] = {}
    warnings: list[str] = []
    out: dict = {"candidates": None, "guards": None, "state2": None, "canonical": None,
                 "extraction": None, "extractionGaps": [], "excluded": {"outsideScope": [], "nestedEntries": []}}

    meta = _object(args.metadata, "--metadata") if args.metadata else None
    provenance = _object(args.provenance, "--provenance") if args.provenance else None
    brief = read_brief(args.brief) if args.brief else None
    language = (brief or {}).get("language")
    if not language and meta is not None and isinstance(meta.get("language"), str):
        language = meta["language"]

    extracted = None
    if args.extraction:
        data = _object(args.extraction, "--extraction")
        extracted = from_extraction(data, language, brief)
        records += extracted["records"]
        sets.update(extracted["sets"])
        out["extraction"] = extracted["extraction"]
        out["extractionGaps"] = extracted["gaps"]
        out["excluded"] = {"outsideScope": extracted["outside"], "nestedEntries": extracted["nested"]}
        warnings += [f"{Path(args.extraction).name}: {w}" for w in data.get("warnings") or [] if isinstance(w, str)]
    for path in args.quick or []:
        data = _object(path, "--quick")
        records += from_quick(data)
        warnings += [f"{Path(path).name}: {w}" for w in data.get("warnings") or [] if isinstance(w, str)]
    violations: list[str] = []
    for path in args.per_file or []:
        found, errors = from_per_file(path)
        records += found
        violations += errors
    if violations:
        raise SchemaError(violations)
    records += [_record(name, None, None, None, None, "by-eye") for name in args.name or [] if name]

    # A surface read from the source takes no name from the provenance map or
    # metadata.json: they are only the baselines of the candidates and guards.
    source_read = extracted is not None or bool(args.quick) or bool(args.per_file)
    if not source_read and (provenance is not None or meta is not None):
        named = [e for e in _entries(provenance)
                 if isinstance(e.get("export_name"), str) and e["export_name"]
                 and METHOD_SEPARATOR not in e["export_name"]]
        prov_names = sorted({e["export_name"] for e in named})
        exports = meta.get("exports") if meta is not None else None
        meta_names = sorted({n for n in (_export_name(e) for e in exports) if n}) if isinstance(exports, list) else []
        base_of: dict[str, str] = {}
        if args.fold:
            # One fold over both lists, so a variant folded out of the map
            # never comes back through metadata.json.
            base_of, tally = fold_names(sorted(set(prov_names) | set(meta_names)), args.fold_prefix or [],
                                        set(args.keep or []), tallied=set(prov_names))
            if provenance is not None:
                canonical = sorted({base_of.get(n, n) for n in prov_names})
                out["canonical"] = {
                    "raw": len(prov_names),
                    "canonical": len(canonical),
                    "folded": tally,
                    "variants": {n: base_of[n] for n in prov_names if n in base_of},
                    "summary": (f"Provenance-map canonicalization: {len(prov_names)} raw entries → "
                                f"{len(canonical)} canonical bases ({len(prov_names) - len(canonical)} "
                                f"bookkeeping variants folded: _def×{tally['_def']}, _exact×{tally['_exact']}, "
                                f"a11y_×{tally[FOLD_PREFIX]}, other×{tally['other']})"),
                }
        seen = set()
        for e in named:
            name = base_of.get(e["export_name"], e["export_name"])
            if name in seen:
                continue
            seen.add(name)
            records.append(_record(name, e.get("export_type"), e.get("source_file"), e.get("source_line"),
                                   None, "provenance"))
        meta_bases = sorted({base_of.get(n, n) for n in meta_names})
        records += [_record(n, None, None, None, None, "metadata") for n in meta_bases]
        if seen and meta_bases:
            out["state2"] = {
                "provenanceCount": len(seen),
                "metadataCount": len(meta_bases),
                "unionCount": len(seen | set(meta_bases)),
                "metadataOnly": sorted(set(meta_bases) - seen),
            }

    sets["all"] = sorted({r["name"] for r in records})
    # A nested Python top's records count in the scope sets, never in `all`.
    records += extracted["nestedRecords"] if extracted is not None else []
    records.sort(key=lambda r: (r["name"], str(r["file"] or ""), r["origin"]))

    # The scope: the one the extractor recorded, else the brief's.
    scope = extracted["scope"] if extracted is not None and any(extracted["scope"].values()) else None
    if scope is None:
        scope = brief["scope"] if brief is not None else _scope(None, None, None)
    # A tier A glob the runner lists as matching no file counts no name: the
    # set comes from the globs that matched, and with none there is no set.
    stale_tier_a = set(extracted["staleScope"]["unmatchedTierAInclude"]) if extracted is not None else set()
    tier_a = [g for g in scope["tier_a_include"] if g not in stale_tier_a]
    filed = [r for r in records if r["file"]]
    if filed and scope["include"]:
        sets["scope.include"] = matching(filed, scope["include"], scope["exclude"])
    if filed and tier_a:
        sets["tier_a_include"] = matching(filed, tier_a, scope["exclude"])

    if extracted is not None or brief is not None or meta is not None:
        stats = meta.get("stats") if isinstance(meta, dict) and isinstance(meta.get("stats"), dict) else {}
        stats_eff = _count(stats.get("effective_denominator"))
        include_union = len(sets["scope.include"]) if "scope.include" in sets else len(sets["all"])
        extraction = extracted["extraction"] if extracted is not None else {}
        out["candidates"] = {
            "statsEffectiveDenominator": stats_eff,
            "tierAIncludeUnion": len(sets["tier_a_include"]) if "tier_a_include" in sets else None,
            "scopeIncludeUnion": len(sets["scope.include"]) if "scope.include" in sets else None,
            "subpathUnion": len(sets["subpaths"]) if "subpaths" in sets else None,
            "rootBarrel": len(sets["root"]) if "root" in sets else None,
            "extractorEffectiveDenominator": extraction.get("effectiveDenominator"),
            "extractorBasis": extraction.get("effectiveDenominatorBasis"),
        }
        no_tier_a = not tier_a
        deflation = {"applicable": source_read and bool(stats_eff), "effectiveDenominator": stats_eff,
                     "rederived": include_union if source_read else None, "pct": None, "fires": False}
        if deflation["applicable"]:
            deflation["pct"] = round2((include_union - stats_eff) / stats_eff * 100)
            deflation["fires"] = no_tier_a and deflation["pct"] > DEFLATION_PCT
        entry_count = len(_entries(provenance)) if provenance is not None else 0
        inflation = {"applicable": source_read and no_tier_a and bool(scope["include"]) and entry_count > 0,
                     "scopeIncludeUnion": include_union if scope["include"] else None,
                     "provenanceEntries": entry_count if provenance is not None else None,
                     "pct": None, "fires": False}
        if inflation["applicable"]:
            inflation["pct"] = round2((include_union - entry_count) / entry_count * 100)
            inflation["fires"] = inflation["pct"] > INFLATION_PCT
        stale_scope = {"applicable": extracted is not None and bool(scope["include"] or scope["tier_a_include"]),
                       "fires": False, "unmatchedInclude": [], "unmatchedTierAInclude": [], "restored": []}
        if stale_scope["applicable"]:
            stale_scope.update(extracted["staleScope"])
            stale_scope["fires"] = bool(stale_scope["unmatchedInclude"] or stale_scope["unmatchedTierAInclude"])
        out["guards"] = {
            "deflation": deflation,
            "inflation": inflation,
            "staleScope": stale_scope,
            "umbrella": extracted["umbrella"] if extracted is not None else dict(NO_UMBRELLA),
            "thresholds": {"deflationPct": DEFLATION_PCT, "inflationPct": INFLATION_PCT,
                           "umbrellaRatio": UMBRELLA_RATIO},
        }

    return {
        "inputs": {
            "extraction": args.extraction, "quick": args.quick or [], "perFile": args.per_file or [],
            "names": args.name or [], "provenance": args.provenance, "metadata": args.metadata,
            "brief": args.brief, "fold": bool(args.fold),
        },
        "exports": records,
        "sets": sets,
        **out,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_census(args: argparse.Namespace) -> dict:
    return census(args.skill_dir)


def _cmd_metadata(args: argparse.Namespace) -> dict:
    meta = _object(args.metadata, "--metadata")
    provenance = _object(args.provenance, "--provenance") if args.provenance else None
    return metadata_inputs(meta, provenance)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load-coverage-inputs",
        description="The counts, name sets and denominator candidates coverage-check reads, from files.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("census", help="count the citation forms: is the skill docs-only?")
    p.add_argument("--skill-dir", required=True, help="the skill package: SKILL.md and references/")
    p.add_argument("--output", help="also write the result to this file")
    p.set_defaults(func=_cmd_census)

    p = sub.add_parser("metadata", help="the metadata.json and provenance-map counts")
    p.add_argument("--metadata", required=True, help="the skill's metadata.json")
    p.add_argument("--provenance", help="the provenance map, when there is one")
    p.add_argument("--output", help="also write the result to this file")
    p.set_defaults(func=_cmd_metadata)

    p = sub.add_parser("surface", help="the enumerated source surface, its name sets and candidates")
    p.add_argument("--extraction", help="skf-extract-public-api.py --mode full output")
    p.add_argument("--quick", action="append", help="skf-extract-public-api.py --mode quick output (repeatable)")
    p.add_argument("--per-file", action="append", help="a subagent per-file result (repeatable)")
    p.add_argument("--name", action="append", help="a name read by eye whose file is not known (repeatable)")
    p.add_argument("--provenance", help="the provenance map: its named exports")
    p.add_argument("--metadata", help="metadata.json: its exports[] names, stats and language")
    p.add_argument("--brief", help="the skill brief: its scope globs and language")
    p.add_argument("--fold", action="store_true", help="fold the provenance and metadata bookkeeping variants")
    p.add_argument("--fold-prefix", action="append", help="a renderer prefix to fold (repeatable)")
    p.add_argument("--keep", action="append", help="a variant that is a real export (repeatable)")
    p.add_argument("--output", help="also write the result to this file")
    p.set_defaults(func=surface)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except SchemaError as exc:
        if args.output:
            Path(args.output).unlink(missing_ok=True)
        print(json.dumps({"valid": False, "violations": exc.violations}, indent=2))
        return 2
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))
    return 0


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
    sys.exit(main())
