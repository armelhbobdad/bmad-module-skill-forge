#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""SKF Validate Rename Name — deterministic new-name gate for skf-rename-skill.

select.md §5 accepts a proposed new skill name and must decide four things, each
with one correct answer for a given (name, filesystem, manifest) state:

  format     — matches the module's canonical kebab-case rule
               ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ (same regex as
               skf-validate-output.py / skf-validate-brief-inputs.py)
  length     — 1..64 characters (agentskills.io spec)
  identity   — differs from the current name (nothing to rename otherwise)
  collision  — does NOT already exist (a folder, a file or a link, even a
               broken one) as a manifest `exports` key, a top-level entry
               under the skills output folder or the forge data folder, and
               is not `improvement-queue`, SKF's own forge folder (location
               kind `reserved`)

Doing this in the prompt is a set-membership computation across three sources
plus a regex match — deterministic, so it lives here and the prompt keeps only
the interactive re-ask / halt decision. Checks run in the select.md §5 order and
`first_failure` names the first failing one so the caller maps it to the right
halt (`input-invalid`/exit 2 for format/length/identity, `name-collision`/exit 5
for collision).

`interrupted_rename` fires the select.md §5 recovery fingerprint. A rename's
copy creates the new skill folder first, and a new forge folder only from an
old one. So the new name collides only on disk (not in the manifest, not on a
reserved name), at least under the skills output folder, while the old skill
folder still exists, and under the forge data folder only when the old skill
has a forge folder too — the signature of a rename interrupted between copy
and delete-old, which the caller surfaces as a named cleanup path instead of a
dead-end collision. The new skill folder must also hold nothing a copy of the
old one could not: every entry in it exists in the old folder, of the same
kind, with only each version's package renamed. A forge-only collision
(another tool's folder with the new name), or a module's own skill or another
tool's folder at the new name, is a genuine clash.

`interrupted_after_rekey` fires the recovery for a rename that stopped after
it re-keyed the export manifest, before it deleted the old folders: the new
name is a manifest key and the old name no longer is, both skill folders are
plain folders, and the old one holds nothing the new one lacks (every entry
in it exists in the new folder, of the same kind, with only each version's
package renamed). The new name is then the skill, and the old folders are
what that run left. `leftover_folders` lists them for the caller to name:
the old skill folder and, when that rename moved the forge folder (the old
and new forge folders are plain folders and the old one holds nothing the
new one lacks), the old forge folder. It is empty when the fingerprint does
not fire.

Output (stdout, always JSON):
  {status, valid, old_name, new_name, first_failure, checks{...},
   interrupted_rename, interrupted_after_rekey, leftover_folders, regex}

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
import os
import re
import sys
from pathlib import Path

NAME_REGEX = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
# Keep identical to FORGE_GROUP_DIRS in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
FORGE_GROUP_DIRS = frozenset({"_campaign", "improvement-queue"})
MIN_LEN = 1
MAX_LEN = 64
# OS clutter that a copy can gain without the rename writing it.
CLUTTER = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


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


# Keep identical to _is_link_or_junction in skf-skill-inventory.py
# (test/test-skf-skill-inventory.py pins the copies).
def _is_link_or_junction(p: Path) -> bool:
    """True for POSIX symlinks AND Windows junctions/symlinks.

    `Path.is_symlink()` is False for Windows junctions; os.readlink succeeds
    for both symlinks and junctions (since CPython 3.8 on Windows). A regular
    directory raises OSError on readlink, which is the signal we want to
    refuse replacement. On Windows, any other reparse point (a cloud-sync
    placeholder, a deduplicated file, an app execution alias) raises
    ValueError: it does not redirect to another path, so it is not a link.
    """
    if p.is_symlink():
        return True
    if not p.exists() and not p.is_symlink():
        return False
    try:
        os.readlink(p)
        return True
    except (OSError, ValueError):
        return False


def _within(new: Path, old: Path, depth: int, old_name: str, new_name: str) -> bool:
    """True when every entry under `new` also exists under `old`, of the same kind.

    Depth 0 is the skill folder, depth 1 a version folder: there the renamed
    package `{new_name}` stands for `{old_name}`. OS clutter and `.skf-`
    names (the rename's own staging and link swaps) are ignored. A link or
    junction matches only a link or junction.
    """
    try:
        children = list(new.iterdir())
    except OSError:
        return False
    for child in children:
        name = child.name
        if name in CLUTTER or ".skf-" in name:
            continue
        counterpart = old / (old_name if depth == 1 and name == new_name else name)
        child_link, counterpart_link = _is_link_or_junction(child), _is_link_or_junction(counterpart)
        if child_link or counterpart_link:
            if not (child_link and counterpart_link):
                return False
        elif child.is_dir():
            if not counterpart.is_dir() or not _within(child, counterpart, depth + 1, old_name, new_name):
                return False
        elif not counterpart.is_file():
            return False
    return True


def _looks_like_a_copy(skills_dir: Path, old_name: str, new_name: str) -> bool:
    """True when `{skills_dir}/{new_name}` could be a rename's copy of `{old_name}`.

    The copy takes the old skill folder as it is, then renames each version's
    `{old_name}/` package to `{new_name}/` and rewrites files in place, so it
    never holds an entry the old folder lacks. A module's own skill (a root
    `SKILL.md`) or another tool's folder with the new name does.
    """
    new, old = skills_dir / new_name, skills_dir / old_name
    if (_is_link_or_junction(new) or not new.is_dir()
            or _is_link_or_junction(old) or not old.is_dir()):
        return False
    return _within(new, old, 0, old_name, new_name)


def _copied_whole(old: Path, new: Path, old_name: str, new_name: str) -> bool:
    """True when both are plain folders and `old` holds nothing `new` lacks.

    _within with the two folders swapped: every entry under the old folder
    exists under the new one, of the same kind, where a version's
    `{old_name}/` package stands for its renamed `{new_name}/`.
    """
    if (_is_link_or_junction(old) or not old.is_dir()
            or _is_link_or_junction(new) or not new.is_dir()):
        return False
    return _within(old, new, 0, new_name, old_name)


def _rekeyed_leftovers(skills_dir: Path, forge_dir: Path, old_name: str, new_name: str,
                       export_keys: set[str]) -> list[str]:
    """The old folders a rename left when it stopped after re-keying the manifest.

    Empty unless the manifest names the new skill and no longer the old one,
    and the old skill folder holds nothing the new one lacks. The old forge
    folder is listed only when the rename moved it: its copy under the new
    name exists, and it holds nothing that copy lacks. When both settings
    name one folder, the skill folder is the forge folder, listed once.
    """
    if new_name not in export_keys or old_name in export_keys:
        return []
    if not _copied_whole(skills_dir / old_name, skills_dir / new_name, old_name, new_name):
        return []
    leftovers = [str(skills_dir / old_name)]
    if (os.path.realpath(forge_dir) != os.path.realpath(skills_dir)
            and _copied_whole(forge_dir / old_name, forge_dir / new_name, old_name, new_name)):
        leftovers.append(str(forge_dir / old_name))
    return leftovers


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
    if os.path.lexists(skills_dir / new_name):
        locations.append({"kind": "skills_output_folder", "path": str(skills_dir / new_name)})
    if os.path.lexists(forge_dir / new_name):
        locations.append({"kind": "forge_data_folder", "path": str(forge_dir / new_name)})
    if new_name in FORGE_GROUP_DIRS:
        locations.append({"kind": "reserved", "path": str(forge_dir / new_name)})
    collision_ok = len(locations) == 0

    # Recovery fingerprint: a rename's copy creates the new skill folder
    # first, and a new forge folder only from an old one. So a stranded
    # partial rename collides on disk only (not in the manifest, not on a
    # reserved name), at least in the skills folder, where the new folder
    # holds nothing a copy of the old skill folder could not, and at the
    # forge folder only when the old skill has one.
    kinds = {loc["kind"] for loc in locations}
    interrupted_rename = bool(
        not collision_ok
        and not kinds & {"manifest.exports", "reserved"}
        and "skills_output_folder" in kinds
        and _looks_like_a_copy(skills_dir, old_name, new_name)
        and ("forge_data_folder" not in kinds or (forge_dir / old_name).is_dir())
    )
    # Recovery fingerprint after the commit point: the manifest already names
    # the new skill, so the new name is taken for good, and the old folders are
    # what the rename left before it deleted them.
    leftover_folders = [] if collision_ok or "reserved" in kinds else _rekeyed_leftovers(
        skills_dir, forge_dir, old_name, new_name, export_keys)

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
        "interrupted_after_rekey": bool(leftover_folders),
        "leftover_folders": leftover_folders,
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
