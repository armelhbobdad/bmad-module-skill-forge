#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Skill Roster: the skills a workflow can offer, from one call.

  skills <skills-folder> --forge-data-folder <path>
      rename-skill's select.md section 2: every skill SKF generated in the
      skills folder, joined with the export manifest. It reads the
      manifest through skf-manifest-ops.py (which migrates a v1 manifest)
      and scans the folder with skf-skill-inventory.py, so no step filters,
      joins or counts the roster by hand, and the manifest itself never
      comes back.

`skills` holds each scanned skill whose `skf_skill` is true, in scan order
(by name): `version_count` is the number of version folders the scan found,
`active_version` the scan's value, and `in_manifest` says whether the
manifest's `exports` names the skill. A manifest name with no folder is not
listed. `manifest_exists` is true when `exports` lists at least one skill (a
missing manifest lists none), `not_skf_output` is the scan's list of the
folders that hold a skill SKF did not generate, and `empty` is true when
`skills` is empty. A missing skills folder lists nothing.

The `join` function returns the same result and its exit code, for a
caller that imports this script. Both shared scripts are read from this
script's own folder (shared/scripts/), where the installer puts them in an
installed project as in this checkout.

Output (stdout, one JSON object):

  {"status": "ok", "manifest_exists": bool, "empty": bool,
   "not_skf_output": [name, ...],
   "skills": [{"name", "version_count", "active_version", "in_manifest"}]}

Exit codes:
  0  status "ok"
  1  status "error", with a `code` and an `error`: manifest-corrupt (the
     export manifest does not parse, is not UTF-8 or is not an object
     whose `exports` is an object; `path` names it), helper-missing (a
     shared script this one reads cannot be loaded) or scan-failed (the
     inventory scan of the skills folder failed)
  2  usage error (JSON on stderr)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

SHARED_SCRIPTS = Path(__file__).resolve().parent
MANIFEST_OPS = "skf-manifest-ops.py"
INVENTORY = "skf-skill-inventory.py"
MANIFEST_FILE = ".export-manifest.json"
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


def join(skills_folder: str, forge_folder: str) -> tuple[dict, int]:
    """The `skills` result and its exit code: the manifest read and the scan, joined."""
    ops, err = _load(MANIFEST_OPS)
    if ops is None:
        return {"status": "error", "code": "helper-missing", "error": err}, 1
    manifest_path = Path(skills_folder) / MANIFEST_FILE
    data, err = _read_manifest(ops, manifest_path)
    if err:
        return {"status": "error", "code": "manifest-corrupt", "error": err, "path": str(manifest_path)}, 1
    exports = data.get("exports", {})

    inventory, err = _load(INVENTORY)
    if inventory is None:
        return {"status": "error", "code": "helper-missing", "error": err}, 1
    try:
        scan = inventory.scan_inventory(skills_folder, forge_data_folder=forge_folder)
    except HELPER_ERRORS as e:
        scan = {"status": "error", "error": f"the inventory scan failed: {type(e).__name__}: {e}"}
    if scan.get("status") == "ok":
        found, not_skf_output = scan["skills"], scan.get("not_skf_output", [])
    elif scan.get("code") == "DIR_NOT_FOUND":  # a missing folder holds no skill
        found, not_skf_output = [], []
    else:
        return {"status": "error", "code": "scan-failed",
                "error": scan.get("error") or "the inventory scan failed"}, 1

    skills = [{"name": entry["name"], "version_count": len(entry.get("versions", [])),
               "active_version": entry.get("active_version"), "in_manifest": entry["name"] in exports}
              for entry in found if entry.get("skf_skill")]
    return {
        "status": "ok",
        "manifest_exists": bool(exports),
        "empty": not skills,
        "not_skf_output": list(not_skf_output),
        "skills": skills,
    }, 0


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as JSON on stderr with exit 2, the subcommands included."""

    def error(self, message: str) -> None:
        print(json.dumps({"status": "error", "error": f"usage error: {self.prog}: {message}"}), file=sys.stderr)
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        prog="skf-skill-roster.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="op", required=True, metavar="{skills}")
    p_skills = sub.add_parser("skills", help="the skills SKF generated, joined with the export manifest")
    p_skills.add_argument("skills_folder", metavar="skills-folder", help="{skills_output_folder}")
    p_skills.add_argument("--forge-data-folder", required=True, help="{forge_data_folder}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result, code = join(args.skills_folder, args.forge_data_folder)
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
