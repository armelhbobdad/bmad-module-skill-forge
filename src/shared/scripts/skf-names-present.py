# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Names Present: the provenance entries whose export name a skill package never writes.

skf-test-skill credits a provenance entry toward a stack's Export Coverage
only when the package writes its `export_name`: reconcile-coverage.py
(`load_doc_text`, `names_present`) joins the text of `SKILL.md` and of each
`.md` file directly in `references/` (sorted, read as UTF-8, no subfolder)
and looks for the name in it as a fixed string, case-sensitive, never inside
a longer identifier: on a side where the name ends in a letter, digit, `_`
or `$`, the next character may not be one of those, so `get` is not found in
`target` or `getAll` (skf-test-skill's validate-inventory.py keeps that
rule; NAME_CHARS here must stay the same). A name holding
`::` (an impl-block method, `Type::method`) rolls up under its type and is
never looked up, and an entry with no name is no cited contract.
create-stack-skill (generate-output section 8) runs this helper on a
compose-mode map before the commit, so a stack never commits a name
skf-test-skill will not credit. The rule here is the scorer's:
test/test-skf-stack-step-rules.py runs both on the same package.

Usage:
  uv run skf-names-present.py --provenance <provenance-map.json> \\
      --skill-dir <dir> [--drop-absent]

Output (stdout):
  {
    "checked": <int>,           # entries whose export_name was looked up
    "skipped": <int>,           # entries with a `::` name or no name
    "absent": [                 # in entries[] order
      {"entry_index": <int>, "export_name": "<name>",
       "source_library": "<library>" | null},
      ...
    ],
    "dropped": [...],           # --drop-absent: the absent entries removed
    "provenance_written": <bool>
  }

--drop-absent removes every absent entry from the map and rewrites it
through skf-atomic-write.py beside this script (JSON indented by two
spaces, non-ASCII kept, a final newline). `absent[]` still lists what the
lookup found, and `dropped[]` repeats it. `entry_index` is the position in
the map as it was read.

Exit codes:
  0  no entry is absent, or --drop-absent removed every absent entry
  1  an entry is absent (absent[] lists it)
  2  usage, file, JSON or write error (one line on stderr, no JSON)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ATOMIC_WRITE_HELPER = "skf-atomic-write.py"
ATOMIC_WRITE_TIMEOUT_SEC = 60
METHOD_SEPARATOR = "::"
# Characters that continue an identifier in the languages SKF documents (`$`
# for JS/TS names such as `$state`): skf-test-skill's IDENT_CHARS.
NAME_CHARS = r"\w$"
_NAME_CHAR_RE = re.compile(f"[{NAME_CHARS}]")


def load_doc_text(skill_dir: Path) -> str:
    """The text skf-test-skill looks names up in: SKILL.md, then each .md file
    directly in references/ in sorted order, joined by newlines. Raises
    OSError, or UnicodeDecodeError for a file that is not UTF-8."""
    parts = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        parts.append(skill_md.read_text(encoding="utf-8"))
    refs = skill_dir / "references"
    if refs.is_dir():
        for ref in sorted(refs.glob("*.md")):
            parts.append(ref.read_text(encoding="utf-8"))
    return "\n".join(parts)


def name_written(name: str, doc_text: str) -> bool:
    """True when `doc_text` holds `name` as skf-test-skill's scorer finds it."""
    body = re.escape(name)
    if _NAME_CHAR_RE.match(name[0]):
        body = f"(?<![{NAME_CHARS}])" + body
    if _NAME_CHAR_RE.match(name[-1]):
        body += f"(?![{NAME_CHARS}])"
    return re.search(body, doc_text) is not None


def looked_up_name(entry: object) -> str | None:
    """The name skf-test-skill looks up for an entry, or None when it looks
    up none: no string name, or a `Type::method` name."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("export_name")
    if not isinstance(name, str) or not name or METHOD_SEPARATOR in name:
        return None
    return name


def find_absent(entries: list, doc_text: str) -> tuple[int, list[dict]]:
    """(entries looked up, the absent ones in entries[] order)."""
    checked, absent = 0, []
    for index, entry in enumerate(entries):
        name = looked_up_name(entry)
        if name is None:
            continue
        checked += 1
        if not name_written(name, doc_text):
            library = entry.get("source_library")
            absent.append({
                "entry_index": index,
                "export_name": name,
                "source_library": library if isinstance(library, str) else None,
            })
    return checked, absent


def atomic_write(target: Path, data: bytes) -> None:
    """Write `data` to `target` through skf-atomic-write.py beside this
    script. Raises OSError when the helper is missing or fails."""
    helper = Path(__file__).resolve().parent / ATOMIC_WRITE_HELPER
    if not helper.is_file():
        raise OSError(f"{ATOMIC_WRITE_HELPER} not found beside {Path(__file__).name}; nothing written")
    try:
        result = subprocess.run(
            [sys.executable, str(helper), "write", "--target", str(target)],
            input=data,
            capture_output=True,
            timeout=ATOMIC_WRITE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError(f"atomic write of {target} failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise OSError(f"atomic write of {target} failed: {detail}")


def _fail(message: str) -> int:
    print(f"error: {' '.join(message.split())}", file=sys.stderr)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-names-present",
        description=(
            "List the provenance entries whose export_name the skill package "
            "never writes, by skf-test-skill's Export Coverage rule "
            "(SKILL.md and references/*.md, case-sensitive substring, `::` "
            "names skipped); with --drop-absent, remove them from the map."
        ),
    )
    parser.add_argument("--provenance", required=True, help="path to provenance-map.json")
    parser.add_argument(
        "--skill-dir",
        required=True,
        help="skill package folder holding the SKILL.md and references/ to search",
    )
    parser.add_argument(
        "--drop-absent",
        action="store_true",
        help="remove every absent entry and rewrite the map through skf-atomic-write.py",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    prov_path = Path(args.provenance)
    skill_dir = Path(args.skill_dir)
    if not prov_path.is_file():
        return _fail(f"provenance map not found: {prov_path}")
    # A wrong folder would read every name as absent, and --drop-absent
    # would then empty the map: require the package's SKILL.md.
    if not (skill_dir / "SKILL.md").is_file():
        return _fail(f"skill dir has no SKILL.md: {skill_dir}")
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail(f"cannot read the provenance map {prov_path}: {exc}")
    entries = prov.get("entries") if isinstance(prov, dict) else None
    if not isinstance(entries, list):
        return _fail(f"the provenance map {prov_path} has no entries[] list")
    try:
        doc_text = load_doc_text(skill_dir)
    except (OSError, ValueError) as exc:
        return _fail(f"cannot read the skill package {skill_dir}: {exc}")

    checked, absent = find_absent(entries, doc_text)
    dropped: list[dict] = []
    if args.drop_absent and absent:
        gone = {item["entry_index"] for item in absent}
        prov["entries"] = [entry for index, entry in enumerate(entries) if index not in gone]
        data = (json.dumps(prov, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            atomic_write(prov_path, data)
        except OSError as exc:
            return _fail(str(exc))
        dropped = absent

    result = {
        "checked": checked,
        "skipped": len(entries) - checked,
        "absent": absent,
        "dropped": dropped,
        "provenance_written": bool(dropped),
    }
    # ASCII escapes: a Windows console's code page cannot encode every name.
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if not absent or dropped else 1


if __name__ == "__main__":
    sys.exit(main())
