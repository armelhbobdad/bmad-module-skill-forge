# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Campaign Parse Manifest — deterministic parse of a --manifest target list.

step-01 (Setup) seeds a headless campaign's targets from a plain-text manifest.
Parsing that format by hand risks silently dropping a malformed line — exactly
the kind of mechanical, all-or-nothing work that belongs in a script. This
parser is the single source of truth for the format documented in SKILL.md
"On Activation".

Format (one target per line):

    name,repo_url,tier,pin[;dep1,dep2,...]

- `pin` may be empty (latest): `name,repo_url,tier,`  or  `name,repo_url,tier`
- a trailing `;`-segment lists depends_on names (comma-separated)
- blank lines and lines starting with `#` are skipped
- `tier` must be `A` or `B`

CLI:
  uv run campaign-parse-manifest.py <path/to/manifest.txt>
  cat manifest.txt | uv run campaign-parse-manifest.py -

Output (JSON on stdout):
  {"targets": [{"name","repo_url","tier","pin","depends_on"}], "errors": [{"line","message"}]}

Exit codes:
  0  parsed cleanly (no errors)
  1  one or more malformed lines (errors[] populated; targets[] omits bad lines)
  2  file error (not found / unreadable)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def parse_manifest_text(text: str) -> Dict[str, Any]:
    targets: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    seen: set = set()

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        body, sep, deps_part = line.partition(";")
        fields = [f.strip() for f in body.split(",")]
        if len(fields) < 3:
            errors.append({"line": lineno, "message": f"expected `name,repo_url,tier[,pin]`, got {len(fields)} field(s)"})
            continue

        name, repo_url, tier = fields[0], fields[1], fields[2]
        pin = fields[3] if len(fields) >= 4 and fields[3] != "" else None

        if not name:
            errors.append({"line": lineno, "message": "empty `name`"})
            continue
        if not repo_url:
            errors.append({"line": lineno, "message": f"`{name}` has empty `repo_url`"})
            continue
        if tier not in ("A", "B"):
            errors.append({"line": lineno, "message": f"`{name}` has invalid tier `{tier}` (must be A or B)"})
            continue
        if name in seen:
            errors.append({"line": lineno, "message": f"duplicate target name `{name}`"})
            continue
        seen.add(name)

        depends_on = [d.strip() for d in deps_part.split(",") if d.strip()] if sep else []

        targets.append(
            {"name": name, "repo_url": repo_url, "tier": tier, "pin": pin, "depends_on": depends_on}
        )

    return {"targets": targets, "errors": errors}


def run(path: str) -> int:
    if path == "-":
        text = sys.stdin.read()
    else:
        p = Path(path)
        if not p.is_file():
            json.dump({"error": f"Manifest not found: {path}", "code": "MANIFEST_NOT_FOUND"}, sys.stderr)
            sys.stderr.write("\n")
            return 2
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            json.dump({"error": f"Manifest unreadable: {exc}", "code": "MANIFEST_READ_ERROR"}, sys.stderr)
            sys.stderr.write("\n")
            return 2

    result = parse_manifest_text(text)
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 1 if result["errors"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-parse-manifest",
        description="Parse a --manifest target list into structured targets.",
    )
    parser.add_argument("path", help="path to manifest text file, or `-` for stdin")
    args = parser.parse_args(argv)
    return run(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
