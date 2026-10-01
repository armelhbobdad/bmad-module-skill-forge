# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Skills Module: is a repository a skills module, and what does it ship.

skf-quick-skill wraps a library's public API, but some repositories ship
agent skills instead of code: a plain Agent Skills package (folders that
each hold a SKILL.md), and a BMad module, whose module.yaml or
module-help.csv adds menu codes. Which folder holds the skills, and which
folders are skills, has one right answer per file listing, so this helper
computes it from the listing instead of the model walking the tree, and
reads the staged SKILL.md frontmatter and module-help.csv (with Python's
yaml and csv modules) into the envelope skf-extract-public-api.py prints
for a library.

CLI:
  uv run skf-skills-module.py sniff --tree-file <file> [--package-json <file>] \\
      [--scope-hint <folder>] [--fetch-list <file>]
  uv run skf-skills-module.py extract --sniff <file> --source-root <dir> \\
      [--package <file>] [--name <name>]

sniff
  Reads the repository's file listing (--tree-file: skf-github-probe.py
  tree output, or any listing skf-detect-language.py's --tree-file reads)
  and, with --package-json, the root package.json staged from it. The
  rules:
    - A skill folder holds its own SKILL.md. A module root is a folder that
      directly holds module.yaml or module-help.csv and sits in no skill
      folder (a skill's own assets/module.yaml makes none).
    - The skill folders of a module root are all the folders below it that
      hold a SKILL.md and sit in no other skill folder. The skill folders
      of any other folder are its direct subfolders that hold one.
    - With --scope-hint, that folder is the only candidate, and it counts
      whenever it has skill folders. Otherwise the candidates are the
      repository root and each top-level folder that has skill folders,
      and a candidate counts only when it is a module root or the root
      ships no code. The root ships no code when it has no package
      manifest (package.json, pyproject.toml, setup.py, setup.cfg,
      Cargo.toml, go.mod, pom.xml, build.gradle, build.gradle.kts, Gemfile
      or a *.csproj), or when its only one is a package.json that declares
      no `main` (or an empty one), `exports`, `bin` or `workspaces` and has
      no index.js or index.ts beside it. A root package.json the call was
      not given, or could not read (no --package-json, no file there, or
      not a JSON object), counts as one that ships code. So a library with
      a manifest and one skill/SKILL.md stays a library.
    - When several candidates count, a module root wins, then the one with
      the most skill folders.
  Prints:
    skills_module    whether a candidate counts
    skills_root      the folder that holds the skill folders ("." for the
                     repository root), else null
    module_root      whether skills_root is a module root
    skill_folders    its skill folders, in path order
    candidates       [{"folder", "module_root", "skill_folders" (a count),
                     "counts"}] for every candidate looked at
    suggested_scope  when the repository is not a skills module: the
                     folder a run with no export should name as a scope to
                     re-run with (the module root with the most skill
                     folders, else the folder with the most), else null
    root_files       the files at the repository root
    readme           the root README: README.md, else another root file
                     named README in any letter case (a .md one first, then
                     by name), else null
    asset_dirs       the first 10 folders named scripts, bin, assets,
                     templates or schemas (within --scope-hint when given)
    asset_dir_count  how many such folders there are
    skill_md_count   SKILL.md files anywhere in the listing
    truncated        the listing was cut short
    warnings         [...]
  --fetch-list writes the files extract reads, one path per line, for
  skf-github-fetch.py --patterns-file: each skill folder's SKILL.md, then
  the module-help.csv directly in the skills root when the listing has one
  (an empty file when the repository is not a skills module).

extract
  Reads sniff's output (--sniff) and the files --fetch-list named, staged
  under --source-root laid out as in the repository, and prints
  skf-extract-public-api.py's quick-mode envelope for the module:
    exports         one {"name", "type": "skill", "brief_description",
                    "source_file"} per skill folder, in sniff's order:
                    name from the frontmatter `name` (the folder name when
                    it has none), brief_description from its
                    `description`, whitespace runs made one space; then one
                    {"name", "type": "menu-code", "brief_description",
                    "source_file"} per module-help.csv row that has a
                    menu-code, in file order: the code, then the row's
                    description, display-name and the skill it runs, with
                    its action when set
    usage_patterns  one {"menu_code", "display_name", "description",
                    "skill", "action", "args", "preceded_by",
                    "followed_by"} per module-help.csv row (empty fields
                    null); a row whose skill is empty or starts with `_`
                    (the _meta row) gives neither an export nor a pattern
    confidence      "high" when every skill folder's frontmatter gave a
                    name and a description, else "medium"
    skills, menu_codes  the two counts
    skills_root     sniff's
  --package takes skf-extract-public-api.py's output for the module's root
  manifest, whose language, package_name, version, description,
  dependencies and warnings the envelope keeps; without it package_name is
  --name (the repository's name) and the rest is empty. A SKILL.md or
  module-help.csv that is missing or cannot be read is named in
  `warnings`.

Exit codes:
  0  output printed
  2  usage error: argparse, or an input file that cannot be read, a
     listing that reports a failure, or a --sniff file that is not sniff's
     output ({"status": "error", "message": ...} on stderr)
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import yaml

MANIFESTS = frozenset({"package.json", "pyproject.toml", "setup.py", "setup.cfg", "Cargo.toml", "go.mod",
                       "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile"})
MODULE_FILES = ("module.yaml", "module-help.csv")
ASSET_DIR_NAMES = frozenset({"scripts", "bin", "assets", "templates", "schemas"})
ASSET_DIR_SHOWN = 10
ROOT = "."


class UsageError(ValueError):
    """An input the call cannot run with: exit 2."""


def _load(filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(filename[:-3].replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# sniff: the skills root from the listing
# --------------------------------------------------------------------------


def _folder(path: str) -> str:
    return path.rpartition("/")[0]


def _ancestors(folder: str) -> list[str]:
    """The folders above `folder`, the root excluded."""
    parts = folder.split("/") if folder else []
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _skill_dirs(listing: set[str]) -> set[str]:
    return {_folder(p) for p in listing if p.rpartition("/")[2] == "SKILL.md"}


def _is_module_root(folder: str, listing: set[str], skill_dirs: set[str]) -> bool:
    """Directly holds module.yaml or module-help.csv, and sits in no skill folder."""
    prefix = f"{folder}/" if folder else ""
    holds = any(f"{prefix}{name}" in listing for name in MODULE_FILES)
    in_skill = folder in skill_dirs or any(a in skill_dirs for a in _ancestors(folder))
    return holds and not in_skill


def _skill_folders(folder: str, listing: set[str], skill_dirs: set[str]) -> list[str]:
    prefix = f"{folder}/" if folder else ""
    below = [d for d in skill_dirs if d.startswith(prefix) and d != folder]
    if _is_module_root(folder, listing, skill_dirs):
        return sorted(d for d in below if not any(a in skill_dirs for a in _ancestors(d)))
    return sorted(d for d in below if "/" not in d[len(prefix):])


def _ships_no_code(listing: set[str], package_json: dict | None) -> bool:
    root = {p for p in listing if "/" not in p}
    manifests = {p for p in root if p in MANIFESTS or p.endswith(".csproj")}
    if not manifests:
        return True
    if manifests != {"package.json"} or package_json is None:
        return False
    if package_json.get("main") or any(key in package_json for key in ("exports", "bin", "workspaces")):
        return False
    return not root & {"index.js", "index.ts"}


def _suggested_scope(listing: set[str], skill_dirs: set[str]) -> str | None:
    folders = {a for p in listing for a in [*_ancestors(_folder(p)), _folder(p)] if a}
    scored = [(_is_module_root(f, listing, skill_dirs), len(_skill_folders(f, listing, skill_dirs)), f)
              for f in sorted(folders)]
    scored = [s for s in scored if s[1]]
    return max(scored, key=lambda s: s[:2])[2] if scored else None


def _readme(root_files: list[str]) -> str | None:
    named = [f for f in root_files if f.lower() == "readme" or f.lower().startswith("readme.")]
    if not named:
        return None
    return min(named, key=lambda f: (f != "README.md", f.lower() != "readme.md", not f.lower().endswith(".md"), f))


def _asset_dirs(listing: set[str], scope: str) -> list[str]:
    prefix = f"{scope}/" if scope else ""
    folders = {a for p in listing if p.startswith(prefix) for a in [*_ancestors(_folder(p)), _folder(p)] if a}
    return sorted(f for f in folders if f.startswith(prefix) and f.rpartition("/")[2] in ASSET_DIR_NAMES)


def _shown(folder: str) -> str:
    return folder or ROOT


def sniff(paths: list[str], package_json: dict | None, scope_hint: str | None, truncated: bool = False) -> dict:
    """The skills-module facts of a file listing (see the module docstring)."""
    listing = set(paths)
    skill_dirs = _skill_dirs(listing)
    scope = scope_hint.strip().strip("/") if scope_hint is not None and scope_hint.strip() not in ("", ".", "./") \
        else None
    candidates = []
    if scope is not None:
        found = _skill_folders(scope, listing, skill_dirs)
        candidates.append((_is_module_root(scope, listing, skill_dirs), found, scope, bool(found)))
    else:
        no_code = _ships_no_code(listing, package_json)
        for folder in ["", *sorted({p.split("/")[0] for p in listing if "/" in p})]:
            found = _skill_folders(folder, listing, skill_dirs)
            if not found:
                continue
            module_root = _is_module_root(folder, listing, skill_dirs)
            candidates.append((module_root, found, folder, module_root or no_code))
    counting = [c for c in candidates if c[3]]
    best = max(counting, key=lambda c: (c[0], len(c[1]))) if counting else None
    root_files = sorted(p for p in listing if "/" not in p)
    assets = _asset_dirs(listing, scope or "")
    warnings = []
    if "package.json" in root_files and package_json is None and scope is None and \
            {p for p in root_files if p in MANIFESTS or p.endswith(".csproj")} == {"package.json"}:
        warnings.append("the root package.json was not read (--package-json): it counts as one that ships code")
    if truncated:
        warnings.append("the listing was cut short: a skill folder it lacks is not counted")
    return {
        "skills_module": best is not None,
        "skills_root": _shown(best[2]) if best else None,
        "module_root": bool(best and best[0]),
        "skill_folders": list(best[1]) if best else [],
        "candidates": [{"folder": _shown(c[2]), "module_root": c[0], "skill_folders": len(c[1]), "counts": c[3]}
                       for c in candidates],
        "suggested_scope": None if best else _suggested_scope(listing, skill_dirs),
        "root_files": root_files,
        "readme": _readme(root_files),
        "asset_dirs": assets[:ASSET_DIR_SHOWN],
        "asset_dir_count": len(assets),
        "skill_md_count": sum(1 for p in listing if p.rpartition("/")[2] == "SKILL.md"),
        "truncated": truncated,
        "warnings": warnings,
    }


def fetch_list(result: dict, paths: list[str]) -> list[str]:
    """The files extract reads: each skill folder's SKILL.md, then the skills root's module-help.csv."""
    if not result["skills_module"]:
        return []
    files = [f"{folder}/SKILL.md" for folder in result["skill_folders"]]
    root = result["skills_root"]
    csv_path = "module-help.csv" if root == ROOT else f"{root}/module-help.csv"
    if csv_path in set(paths):
        files.append(csv_path)
    return files


# --------------------------------------------------------------------------
# extract: the envelope from the staged files
# --------------------------------------------------------------------------


FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def _one_line(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def frontmatter(text: str) -> dict:
    """The YAML frontmatter of a SKILL.md, {} when it has none or it is not a mapping."""
    m = FRONTMATTER_RE.match(text.lstrip("﻿"))
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def _field(row: dict, name: str) -> str | None:
    value = row.get(name)
    return value.strip() or None if isinstance(value, str) else None


def menu_rows(text: str) -> list[dict]:
    """The module-help.csv rows that run a skill: the _meta row and rows with no skill left out."""
    rows = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        skill = _field(row, "skill")
        if skill is None or skill.startswith("_"):
            continue
        rows.append({"menu_code": _field(row, "menu-code"), "display_name": _field(row, "display-name"),
                     "description": _field(row, "description"), "skill": skill, "action": _field(row, "action"),
                     "args": _field(row, "args"), "preceded_by": _field(row, "preceded-by"),
                     "followed_by": _field(row, "followed-by")})
    return rows


def _menu_description(row: dict) -> str:
    parts = [row["description"] or "", f"({row['display_name']})" if row["display_name"] else "",
             f"runs {row['skill']}" + (f" ({row['action']})" if row["action"] else "")]
    return " ".join(p for p in parts if p)


def extract(sniffed: dict, source_root: Path, package: dict | None = None, name: str | None = None) -> dict:
    """skf-extract-public-api.py's quick-mode envelope for a skills module."""
    package = package or {}
    warnings = [w for w in package.get("warnings", []) if isinstance(w, str)]
    exports, complete = [], True
    for folder in sniffed.get("skill_folders", []):
        rel = f"{folder}/SKILL.md"
        text = _read_text(source_root / rel)
        if text is None:
            warnings.append(f"{rel}: not staged under the source root; the skill is named after its folder")
        meta = frontmatter(text or "")
        skill_name = _one_line(meta.get("name"))
        description = _one_line(meta.get("description"))
        if text is not None and not (skill_name and description):
            warnings.append(f"{rel}: the frontmatter gives no {'name' if not skill_name else 'description'}")
        complete = complete and bool(skill_name and description)
        exports.append({"name": skill_name or folder.rpartition("/")[2], "type": "skill",
                        "brief_description": description or "", "source_file": rel})
    root = sniffed.get("skills_root")
    usage_patterns: list[dict] = []
    if root is not None:
        csv_rel = "module-help.csv" if root == ROOT else f"{root}/module-help.csv"
        text = _read_text(source_root / csv_rel)
        if text is not None:
            try:
                usage_patterns = menu_rows(text)
            except csv.Error as e:
                warnings.append(f"{csv_rel}: cannot be read as CSV ({e})")
            for row in usage_patterns:
                if row["menu_code"]:
                    exports.append({"name": row["menu_code"], "type": "menu-code",
                                    "brief_description": _menu_description(row), "source_file": csv_rel})
    skills = sum(1 for e in exports if e["type"] == "skill")
    return {
        "language": package.get("language"),
        "package_name": package.get("package_name") or name,
        "version": package.get("version"),
        "description": package.get("description"),
        "exports": exports,
        "dependencies": package.get("dependencies") or [],
        "usage_patterns": usage_patterns,
        "confidence": "high" if complete and skills else "medium",
        "skills": skills,
        "menu_codes": len(exports) - skills,
        "skills_root": root,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_json(value: str, flag: str) -> dict:
    try:
        with open(value, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise UsageError(f"cannot read {flag} {value}: {getattr(e, 'strerror', None) or e}") from e
    if not isinstance(data, dict):
        raise UsageError(f"{flag} {value} is not a JSON object")
    return data


def _package_json(value: str | None) -> dict | None:
    """The staged root package.json, or None when it is absent or unreadable (it then counts as shipping code)."""
    if not value or not Path(value).is_file():
        return None
    try:
        return _read_json(value, "--package-json")
    except UsageError:
        return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-skills-module",
        description="Find a repository's skills root from its file listing, and list a skills module's exports.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sniff = sub.add_parser("sniff", help="the skills root and the listing facts")
    p_sniff.add_argument("--tree-file", required=True, help="the repository's file listing")
    p_sniff.add_argument("--package-json", help="the root package.json, staged")
    p_sniff.add_argument("--scope-hint", help="the one folder to look at")
    p_sniff.add_argument("--fetch-list", help="write the files extract reads here, one per line")
    p_extract = sub.add_parser("extract", help="the envelope from the staged SKILL.md files and module-help.csv")
    p_extract.add_argument("--sniff", required=True, help="sniff's output, saved")
    p_extract.add_argument("--source-root", required=True, help="the folder the files were staged in")
    p_extract.add_argument("--package", help="skf-extract-public-api.py's output for the root manifest")
    p_extract.add_argument("--name", help="the package name when there is no --package")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "sniff":
            try:
                paths, truncated = _load("skf-detect-language.py").read_tree_file(args.tree_file)
            except ValueError as e:
                raise UsageError(str(e)) from e
            out = sniff(paths, _package_json(args.package_json), args.scope_hint, truncated)
            if args.fetch_list:
                try:
                    Path(args.fetch_list).write_text("".join(f"{p}\n" for p in fetch_list(out, paths)),
                                                     encoding="utf-8")
                except OSError as e:
                    raise UsageError(f"cannot write --fetch-list {args.fetch_list}: {e.strerror or e}") from e
        else:
            sniffed = _read_json(args.sniff, "--sniff")
            if not isinstance(sniffed.get("skill_folders"), list) or "skills_root" not in sniffed:
                raise UsageError(f"--sniff {args.sniff} is not skf-skills-module.py sniff output")
            package = _read_json(args.package, "--package") if args.package else None
            out = extract(sniffed, Path(args.source_root), package, args.name)
    except UsageError as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
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
