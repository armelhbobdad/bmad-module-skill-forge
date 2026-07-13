#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Validate Rename Name — deterministic new-name gate for skf-rename-skill.

select.md §5 accepts a proposed new skill name and must decide four things, each
with one correct answer for a given (name, filesystem, manifest) state:

  format     — matches the module's canonical kebab-case rule
               ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ (same regex as
               skf-validate-output.py / skf-validate-brief-inputs.py)
  length     — 1..64 characters (agentskills.io spec)
  identity   — differs from the current name (nothing to rename otherwise)
  collision  — does NOT already exist as a manifest `exports` key, a top-level
               directory under the skills output folder, or a top-level
               directory under the forge data folder

Doing this in the prompt is a set-membership computation across three sources
plus a regex match — deterministic, so it lives here and the prompt keeps only
the interactive re-ask / halt decision. Checks run in the select.md §5 order and
`first_failure` names the first failing one so the caller maps it to the right
halt (`input-invalid`/exit 2 for format/length/identity, `name-collision`/exit 5
for collision).

`interrupted_rename` fires the select.md §5 recovery fingerprint: the new name
collides only on disk (not in the manifest) AND both old-name directories still
exist — the signature of a rename interrupted between copy and delete-old, which
the caller surfaces as a named cleanup path instead of a dead-end collision.

Output (stdout, always JSON):
  {status, valid, old_name, new_name, first_failure, checks{...},
   interrupted_rename, regex}

Exit codes:
  0  valid (all checks pass)
  2  invalid (at least one check failed; see first_failure / checks)
  1  operation error (bad args)

CLI example:
  python3 skf-validate-rename-name.py --old-name rename --new-name rename-skill \
      --skills-output-folder /out --forge-data-folder /forge
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NAME_REGEX = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
MIN_LEN = 1
MAX_LEN = 64


def load_exports(manifest_path: Path) -> tuple[set[str], str | None]:
    """Return (export skill-name keys, error). Missing manifest -> empty set."""
    if not manifest_path.is_file():
        return set(), None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        # select.md §2 halts before §5 on a malformed manifest, so treat an
        # unreadable file here as "no exports" rather than crashing the gate.
        return set(), f"{type(e).__name__}: {e}"
    exports = data.get("exports", {}) if isinstance(data, dict) else {}
    return set(exports.keys()) if isinstance(exports, dict) else set(), None


def validate_name(
    old_name: str,
    new_name: str,
    skills_output_folder: str,
    forge_data_folder: str,
    manifest_path: str | None = None,
) -> dict:
    skills_dir = Path(skills_output_folder)
    forge_dir = Path(forge_data_folder)
    manifest = Path(manifest_path) if manifest_path else skills_dir / ".export-manifest.json"

    export_keys, manifest_error = load_exports(manifest)

    fmt_ok = re.match(NAME_REGEX, new_name) is not None
    length = len(new_name)
    len_ok = MIN_LEN <= length <= MAX_LEN
    identity_ok = new_name != old_name

    locations: list[dict] = []
    if new_name in export_keys:
        locations.append({"kind": "manifest.exports", "path": str(manifest)})
    if (skills_dir / new_name).is_dir():
        locations.append({"kind": "skills_output_folder", "path": str(skills_dir / new_name)})
    if (forge_dir / new_name).is_dir():
        locations.append({"kind": "forge_data_folder", "path": str(forge_dir / new_name)})
    collision_ok = len(locations) == 0

    # Recovery fingerprint: collides on disk only (not manifest) and both
    # old-name directories still exist -> stranded partial rename, not a genuine
    # clash.
    collides_on_disk_only = (
        not collision_ok
        and all(loc["kind"] != "manifest.exports" for loc in locations)
    )
    interrupted_rename = bool(
        collides_on_disk_only
        and (skills_dir / old_name).is_dir()
        and (forge_dir / old_name).is_dir()
    )

    checks = {
        "format": {"ok": fmt_ok},
        "length": {"ok": len_ok, "length": length},
        "identity": {"ok": identity_ok},
        "collision": {"ok": collision_ok, "locations": locations},
    }

    first_failure = None
    for name in ("format", "length", "identity", "collision"):
        if not checks[name]["ok"]:
            first_failure = name
            break

    result = {
        "status": "ok",
        "valid": first_failure is None,
        "old_name": old_name,
        "new_name": new_name,
        "first_failure": first_failure,
        "checks": checks,
        "interrupted_rename": interrupted_rename,
        "regex": NAME_REGEX,
    }
    if manifest_error:
        result["manifest_error"] = manifest_error
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a proposed rename target name.")
    parser.add_argument("--old-name", required=True)
    parser.add_argument("--new-name", required=True)
    parser.add_argument("--skills-output-folder", required=True)
    parser.add_argument("--forge-data-folder", required=True)
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args(argv)

    result = validate_name(
        args.old_name,
        args.new_name,
        args.skills_output_folder,
        args.forge_data_folder,
        args.manifest,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
