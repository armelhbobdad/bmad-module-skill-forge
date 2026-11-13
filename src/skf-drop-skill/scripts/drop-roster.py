#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drop Skill roster: what a drop reads and checks, each from one call.

  skills <skills-folder> --forge-data-folder <path> [--skill <name>]
      select.md section 2: every skill the drop can offer (section 3 lists
      it). It joins the export manifest, read through skf-manifest-ops.py
      (which migrates a v1 manifest), with the on-disk scan of
      skf-skill-inventory.py: each manifest skill, and each skill SKF
      generated that the manifest does not list (a draft, which only a purge
      can drop). A folder holding a skill SKF did not generate is never
      offered: it is listed in `not_offered`, with the scan's errors for it.
      Each skill carries its versions newest first, in the order
      skf-skill-inventory.py resolve gives them (numeric, so 0.10.0 comes
      before 0.9.0), each with its manifest status, last export date and
      IDEs, and the counts the active-version guard and the blast-radius
      line read. With --skill the roster holds that skill only, so a run
      given its target reads one skill rather than every one; `empty` and
      `not_offered` still cover the whole folder. report.md section 1 reads
      the remaining versions from it too.

      `keep_candidate` is the version select.md section 7 names to keep
      when the user drops the manifest's active_version: the pick
      skf-update-active-symlink.py repair-after-drop makes after a purge
      (pick_new_active), with the active version as the dropped one. It
      is null when the skill has no active_version, when no other version
      qualifies, and when that script cannot be loaded.

      Without skf-skill-inventory.py (an older or broken install), or when
      its scan or resolve fails, `inventory` is false and the roster holds
      the manifest skills alone: SKF cannot check that it generated a folder
      the manifest does not list, so none is offered.

  rows --skill <name> [--version <v>]... <context-file>...
      verify's context-rows check (execute.md section 5) runs it: the
      managed-section rows the context files still hold for a skill (for
      those versions only, with --version), as {file, version}, read with
      the parser skf-rebuild-managed-sections.py writes the section with. A
      row's snippet text never comes back. A file whose markers are
      malformed, or that cannot be read, is listed in `unchecked` with the
      reason: its rows are unknown. A missing file holds no row.

  activation  (stdin: the JSON skf-resolve-customization.py printed)
      SKILL.md On Activation section 4: whether the headless-purge guard is
      on. `purge_forbidden` is true when `forbid_purge_in_headless`, under
      the `workflow` table or as a `workflow.forbid_purge_in_headless` key,
      holds any value other than the empty string (true, false and "false"
      included), and false when it is "" or absent. stdin is read as bytes
      and decoded as UTF-8 with replacement (a leading BOM dropped, as the
      resolver drops one), since a fact path need not be UTF-8. stdin that is not a JSON object, or a `workflow` that is not
      one, exits 1: the caller then counts the guard as on.

  verify <skills-folder> --skill <name> --mode deprecate|purge
         [--version <v>]... [<context-file>...]
      execute.md section 5: the state a drop should leave. The manifest
      check: each --version has status "deprecated"; with no --version, a
      deprecate leaves every version of the entry deprecated and a purge
      leaves no entry (a draft, which the manifest never listed, too). A
      manifest that cannot be read fails the check rather than the call.
      The context-rows check, run over the context files given: each row
      `rows` finds (for those versions, with --version) and each file it
      cannot check fails it. Each failure is {check: "manifest" or
      "context-rows", detail: what failed, manual_fix}. The context files
      may come before or after the flags.

The shared scripts are read from the shared scripts folder beside this
skill's folder (shared/scripts/), where the installer puts them in an
installed project as in this checkout.

Output (stdout, one JSON object):

  skills: {"status": "ok", "inventory": bool, "inventory_error": str|null,
           "skills": [{"name", "in_manifest", "purge_only", "active_version",
                       "layout": "versioned"|"flat"|"none"|null,
                       "versions": [{"version", "status", "active",
                                     "in_manifest", "on_disk",
                                     "last_exported", "ides"}],
                       "counts": {"non_deprecated", "on_disk"},
                       "keep_candidate": str|null}],
           "not_offered": [{"name", "errors"}], "empty": bool}
  rows:   {"status": "ok", "skill", "versions": [...]|null,
           "rows": [{"file", "version"}], "unchecked": [{"file", "error"}]}
  activation: {"status": "ok", "purge_forbidden": bool}
  verify: {"status": "ok", "failures": [{"check", "detail", "manual_fix"}]}

`status` of a version is its manifest status, null for a folder the manifest
does not list; `active` marks the manifest's active_version. `counts` gives
`non_deprecated` (the manifest versions whose status is not "deprecated")
and `on_disk` (the version folders; null without the inventory helper).

Exit codes:
  0  status "ok"
  1  status "error", with a `code`: manifest-corrupt (skills: the export
     manifest exists but does not parse, is not UTF-8 or is not an object
     of entry objects; `path` names it), helper-missing (a shared script
     this one reads cannot be loaded) or bad-input (activation: stdin is
     not the resolver's JSON object)
  2  usage error (JSON on stderr)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# Installed (under _bmad/skf/ or an IDE's skills folder) and in a dev
# checkout (src/), shared/ sits beside this skill's folder.
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
MANIFEST_OPS = "skf-manifest-ops.py"
INVENTORY = "skf-skill-inventory.py"
REBUILD = "skf-rebuild-managed-sections.py"
ACTIVE_SYMLINK = "skf-update-active-symlink.py"
MANIFEST_FILE = ".export-manifest.json"
# The headless-purge guard's setting, under the `workflow` table the resolver prints.
FORBID_KEY = "forbid_purge_in_headless"
# The manual fix of each verify check.
EXPORT_FIX = "re-run `[EX] Export Skill`"
# What a shared helper raises on a file it cannot read as it expects (a
# manifest of the wrong shape or encoding, a folder it cannot list).
HELPER_ERRORS = (AttributeError, TypeError, ValueError, OSError)


def _load(filename: str):
    """(module, None) for a shared script, or (None, the reason it cannot load)."""
    path = SHARED_SCRIPTS / filename
    try:
        spec = importlib.util.spec_from_file_location(filename[:-3].replace("-", "_"), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (ImportError, OSError, AttributeError, SyntaxError) as e:
        return None, f"cannot load {filename} from {SHARED_SCRIPTS} ({e}): re-install SKF"
    return module, None


def _plain_name(value) -> bool:
    """True for a name that is one folder name and nothing else."""
    return isinstance(value, str) and value not in ("", ".", "..") and not any(c in value for c in "/\\:\0")


def _manifest_rows(entry) -> tuple[str | None, dict]:
    """(active_version, {version: {status, last_exported, ides}}) of a migrated manifest entry."""
    if not isinstance(entry, dict):
        return None, {}
    active = entry.get("active_version")
    active = active if isinstance(active, str) and active else None
    versions = entry.get("versions")
    records = {}
    if isinstance(versions, dict):
        for version, record in versions.items():
            record = record if isinstance(record, dict) else {}
            status = record.get("status")
            last = record.get("last_exported")
            ides = record.get("ides")
            records[version] = {
                "status": status if isinstance(status, str) else None,
                "last_exported": last if isinstance(last, str) and last else None,
                "ides": [i for i in ides if isinstance(i, str)] if isinstance(ides, list) else [],
            }
    return active, records


def _version_row(version: str, active: str | None, records: dict, on_disk: bool) -> dict:
    record = records.get(version, {})
    return {
        "version": version,
        "status": record.get("status"),
        "active": version == active,
        "in_manifest": version in records,
        "on_disk": on_disk,
        "last_exported": record.get("last_exported"),
        "ides": record.get("ides", []),
    }


def _skill(name, entry, ops, manifest_path, inventory, skills_folder, forge_folder, symlink=None) -> dict:
    """One roster entry: the skill's versions newest first, with their manifest records, counts and keep_candidate."""
    active, records = _manifest_rows(entry)
    in_manifest = entry is not None
    resolved = None
    if inventory is not None and _plain_name(name):
        resolved = inventory.resolve_skill(skills_folder, name, forge_folder)
    if resolved is not None:
        rows = [_version_row(r["version"], active, records, r["on_disk"]) for r in resolved["versions"]]
        layout = resolved["layout"]
    else:
        # No on-disk scan: the manifest's versions, in the manifest helper's order.
        ordered = ops.cmd_affected_versions(manifest_path, skills_folder, name).get("sources", {}).get("manifest", [])
        rows = [_version_row(v, active, records, False) for v in ordered if v in records]
        layout = None
    return {
        "name": name,
        "in_manifest": in_manifest,
        "purge_only": not in_manifest,
        "active_version": active,
        "layout": layout,
        "versions": rows,
        "counts": {
            "non_deprecated": sum(1 for r in rows if r["in_manifest"] and r["status"] != "deprecated"),
            "on_disk": sum(1 for r in rows if r["on_disk"]) if resolved is not None else None,
        },
        "keep_candidate": symlink.pick_new_active(active, rows, active) if symlink and active else None,
    }


def _read_manifest(ops, manifest_path: Path) -> tuple[dict | None, str | None]:
    """(data, None), or (None, why the manifest cannot be read as one).

    The manifest helper reports a file that is not JSON; a JSON value of the
    wrong shape (a list, or an entry that is not an object) or a file that is
    not UTF-8 makes it raise instead, which is the same corrupt manifest.
    """
    try:
        data, err = ops.read_manifest(manifest_path)
    except HELPER_ERRORS as e:
        return None, f"Manifest cannot be read: {type(e).__name__}: {e}"
    if err:
        return None, err
    if not isinstance(data, dict) or not isinstance(data.get("exports", {}), dict):
        return None, "Manifest is not an object with an `exports` object"
    return data, None


def roster(skills_folder: str, forge_folder: str, only: str | None = None) -> tuple[dict, int]:
    """The `skills` result and its exit code."""
    ops, err = _load(MANIFEST_OPS)
    if ops is None:
        return {"status": "error", "code": "helper-missing", "error": err}, 1
    manifest_path = Path(skills_folder) / MANIFEST_FILE
    data, err = _read_manifest(ops, manifest_path)
    if err:
        return {"status": "error", "code": "manifest-corrupt", "error": err, "path": str(manifest_path)}, 1
    exports = data.get("exports", {})

    inventory, inventory_error = _load(INVENTORY)
    symlink, _ = _load(ACTIVE_SYMLINK)
    drafts, not_offered = [], []
    if inventory is not None:
        try:
            scan = inventory.scan_inventory(skills_folder, forge_data_folder=forge_folder)
        except HELPER_ERRORS as e:
            scan = {"status": "error", "error": f"the inventory scan failed: {type(e).__name__}: {e}"}
        if scan.get("status") == "ok":
            for found in scan["skills"]:
                if found.get("skf_skill") and found["name"] not in exports:
                    drafts.append(found["name"])
            errors = {found["name"]: found.get("errors", []) for found in scan["skills"]}
            not_offered = [{"name": name, "errors": errors.get(name, [])}
                           for name in scan.get("not_skf_output", []) if name not in exports]
        elif scan.get("code") != "DIR_NOT_FOUND":  # a missing folder holds no skill
            inventory, inventory_error = None, scan.get("error", "the inventory scan failed")

    names = sorted(exports) + sorted(drafts)
    listed = [n for n in names if n == only] if only is not None else names
    try:
        skills = [_skill(name, exports.get(name), ops, manifest_path, inventory, skills_folder, forge_folder,
                         symlink) for name in listed]
    except HELPER_ERRORS as e:
        if inventory is None:
            raise
        # A resolve that fails is a scan that failed: the manifest skills alone, as without the helper.
        inventory, inventory_error = None, f"the inventory resolve failed: {type(e).__name__}: {e}"
        drafts, not_offered = [], []
        names = sorted(exports)
        listed = [n for n in names if n == only] if only is not None else names
        skills = [_skill(name, exports.get(name), ops, manifest_path, None, skills_folder, forge_folder, symlink)
                  for name in listed]
    return {
        "status": "ok",
        "inventory": inventory is not None,
        "inventory_error": None if inventory is not None else inventory_error,
        "skills": skills,
        "not_offered": not_offered,
        "empty": not names,
    }, 0


def rows(skill: str, versions: list[str], context_files: list[str]) -> tuple[dict, int]:
    """The `rows` result and its exit code."""
    rebuild, err = _load(REBUILD)
    if rebuild is None:
        return {"status": "error", "code": "helper-missing", "error": err}, 1
    found, unchecked = [], []
    for path in context_files:
        content, err = rebuild.read_context_file(path)
        if err:
            if not rebuild.is_missing(err):
                unchecked.append({"file": path, "error": err})
            continue
        problem = rebuild.find_unclosed_begin(content)
        if problem:
            unchecked.append({"file": path, "error": f"malformed markers: {problem[1]}"})
            continue
        match = rebuild.find_managed_section(content)
        if not match:
            continue
        for row in rebuild.parse_managed_rows(match.group(2)):
            if row["skill_name"] == skill and (not versions or row["version"] in versions):
                found.append({"file": path, "version": row["version"]})
    return {"status": "ok", "skill": skill, "versions": versions or None, "rows": found,
            "unchecked": unchecked}, 0


def activation(raw: bytes) -> tuple[dict, int]:
    """The `activation` result for the resolver JSON `raw`, and its exit code."""
    try:
        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except ValueError as e:
        return {"status": "error", "code": "bad-input", "error": f"stdin is not JSON: {e}"}, 1
    if not isinstance(data, dict):
        return {"status": "error", "code": "bad-input", "error": "stdin is not a JSON object"}, 1
    found, value = False, None
    if "workflow" in data:
        table = data["workflow"]
        if not isinstance(table, dict):
            return {"status": "error", "code": "bad-input", "error": "`workflow` is not a JSON object"}, 1
        found, value = FORBID_KEY in table, table.get(FORBID_KEY)
    if not found and f"workflow.{FORBID_KEY}" in data:
        found, value = True, data[f"workflow.{FORBID_KEY}"]
    return {"status": "ok", "purge_forbidden": found and value != ""}, 0


def _failure(check: str, detail: str, manual_fix: str) -> dict:
    return {"check": check, "detail": detail, "manual_fix": manual_fix}


def _manifest_failures(ops, skills_folder: str, skill: str, mode: str, versions: list[str]) -> list[str]:
    """What the manifest left by the drop gets wrong, one line each (empty when it is as expected)."""
    manifest_path = Path(skills_folder) / MANIFEST_FILE
    data, err = _read_manifest(ops, manifest_path)
    if err:
        return [f"{manifest_path} cannot be read: {err}"]
    entry = data.get("exports", {}).get(skill)
    if not versions and mode == "purge":
        return [f"the manifest still has a `{skill}` entry"] if entry is not None else []
    if not isinstance(entry, dict):
        return [f"the manifest has no `{skill}` entry"]
    records = entry.get("versions") if isinstance(entry.get("versions"), dict) else {}
    problems = []
    for version in versions or list(records):
        record = records.get(version)
        status = record.get("status") if isinstance(record, dict) else None
        if record is None:
            problems.append(f"the manifest's `{skill}` entry has no {version}")
        elif status != "deprecated":
            problems.append(f"the manifest lists `{skill}` {version} as `{status}`, not `deprecated`")
    return problems


def verify(skills_folder: str, skill: str, mode: str, versions: list[str],
           context_files: list[str]) -> tuple[dict, int]:
    """The `verify` result and its exit code."""
    ops, err = _load(MANIFEST_OPS)
    if ops is None:
        return {"status": "error", "code": "helper-missing", "error": err}, 1
    manifest_fix = f"correct the `{skill}` entry of `{Path(skills_folder) / MANIFEST_FILE}` by hand"
    failures = [_failure("manifest", detail, manifest_fix)
                for detail in _manifest_failures(ops, skills_folder, skill, mode, versions)]
    if context_files:
        found, code = rows(skill, versions, context_files)
        if code != 0:
            return found, code
        failures += [_failure("context-rows", f"{row['file']} still lists `{skill}` v{row['version']}", EXPORT_FIX)
                     for row in found["rows"]]
        failures += [_failure("context-rows", f"{item['file']} could not be checked: {item['error']}", EXPORT_FIX)
                     for item in found["unchecked"]]
    return {"status": "ok", "failures": failures}, 0


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as JSON on stderr with exit 2, the subcommands included.

    A subcommand marked `intermixed` takes its positionals on both sides of
    its flags: before Python 3.12, a positional list that follows another
    positional stops at the first flag.
    """

    intermixed = False
    _parsing = False

    def parse_known_args(self, args=None, namespace=None):
        if not self.intermixed or self._parsing:
            return super().parse_known_args(args, namespace)
        self._parsing = True
        try:
            return self.parse_known_intermixed_args(args, namespace)
        finally:
            self._parsing = False

    def error(self, message: str) -> None:
        print(json.dumps({"status": "error", "error": f"usage error: {self.prog}: {message}"}), file=sys.stderr)
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        prog="drop-roster.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="op", required=True, metavar="{skills,rows,activation,verify}")

    p_skills = sub.add_parser("skills", help="the skills a drop can offer, with their versions")
    p_skills.add_argument("skills_folder", metavar="skills-folder", help="{skills_output_folder}")
    p_skills.add_argument("--forge-data-folder", required=True, help="{forge_data_folder}")
    p_skills.add_argument("--skill", help="list this skill only (the name the run was given)")

    p_rows = sub.add_parser("rows", help="the managed-section rows the context files hold for a skill")
    p_rows.add_argument("--skill", required=True, help="the skill whose rows to list")
    p_rows.add_argument("--version", action="append", default=[], dest="versions",
                        help="list the rows of this version only (repeatable)")
    p_rows.add_argument("context_files", nargs="+", metavar="context-file", help="a context file to read")

    sub.add_parser("activation", help="whether the headless-purge guard is on, from the resolver JSON on stdin")

    p_verify = sub.add_parser("verify", help="check the manifest and the context rows a drop left")
    p_verify.intermixed = True
    p_verify.add_argument("skills_folder", metavar="skills-folder", help="{skills_output_folder}")
    p_verify.add_argument("--skill", required=True, help="the dropped skill")
    p_verify.add_argument("--mode", required=True, choices=("deprecate", "purge"), help="{drop_mode}")
    p_verify.add_argument("--version", action="append", default=[], dest="versions",
                          help="a dropped version (repeatable); none for a whole-skill drop")
    p_verify.add_argument("context_files", nargs="*", metavar="context-file",
                          help="a context file the drop rebuilt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.op == "skills":
        result, code = roster(args.skills_folder, args.forge_data_folder, args.skill)
    elif args.op == "rows":
        result, code = rows(args.skill, args.versions, args.context_files)
    elif args.op == "activation":
        result, code = activation(sys.stdin.buffer.read())
    else:
        result, code = verify(args.skills_folder, args.skill, args.mode, args.versions, args.context_files)
    print(json.dumps(result, indent=2))
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a path may hold.
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
