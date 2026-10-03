# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Check Unit Records: check the per-unit records analyze-source's subagents return.

Step 4 (map-and-detect.md section 2) hands each qualifying unit to a
subagent, which writes one JSON object, the unit's export surface, as one
file of a folder and returns only its path. This script reads them all, so
the parent neither copies a record, strips a markdown fence nor checks the
contract's keys by hand:

  uv run skf-check-unit-records.py --dir <folder>

Each regular file of the folder is one reply, read in file-name order. A
wrapping markdown fence (```json ... ```) is dropped, and so is any text
around the outermost {...} when the reply does not parse as it is. The
object is then checked against the return contract:

  unit_name       non-empty string
  files_count     integer >= 0
  exports_count   integer >= 0
  export_pattern  string
  api_surface     list of strings
  ccc_signals     {"top_files": list, "available": bool}
  strategy_used   "ast-grep" | "source-read"
  confidence      "T1" | "T1-low"
  warnings        list of strings

A key that is missing or of the wrong type takes its empty value (0, "",
[], the empty object, false, "source-read", "T1-low"), and a problem names
it: the record is degraded, not dropped. A key the contract does not name is
kept as it came.

Output (JSON on stdout):

  {
    "records":    [{...one per reply that holds a JSON object...}],
    "problems":   [{"file": "<name>", "unit_name": "<name>|null",
                    "problem": "<what was wrong>"}],
    "unreadable": ["<name of a file that holds no JSON object>", ...],
    "warnings":   ["<unit_name>: <one of the record's own warnings>", ...]
  }

A reply in `unreadable` gave no record: the parent analyzes that unit in
the main thread instead.

Exit codes:
  0  the folder was read (whatever the replies held)
  2  usage error: the folder is missing or cannot be read
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

FENCE_RE = re.compile(r"\A```[A-Za-z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?```\Z", re.S)

STRATEGIES = ("ast-grep", "source-read")
CONFIDENCES = ("T1", "T1-low")


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_object_of(value: Any, keys: dict[str, Any]) -> bool:
    return isinstance(value, dict) and all(check(value.get(key)) for key, check in keys.items())


# The return contract: each key, the check its value must pass, and the
# empty value a missing or wrong-typed one takes.
CONTRACT: dict[str, tuple[Any, Any]] = {
    "unit_name": (lambda v: isinstance(v, str) and bool(v.strip()), None),
    "files_count": (_is_count, 0),
    "exports_count": (_is_count, 0),
    "export_pattern": (lambda v: isinstance(v, str), ""),
    "api_surface": (_is_str_list, []),
    "ccc_signals": (
        lambda v: _is_object_of(v, {"top_files": lambda x: isinstance(x, list),
                                    "available": lambda x: isinstance(x, bool)}),
        {"top_files": [], "available": False},
    ),
    "strategy_used": (lambda v: v in STRATEGIES, "source-read"),
    "confidence": (lambda v: v in CONFIDENCES, "T1-low"),
    "warnings": (_is_str_list, []),
}


def parse_reply(text: str) -> dict | None:
    """The JSON object a reply holds, its wrapping fence and surrounding text
    dropped, or None when it holds none."""
    body = text.lstrip("\ufeff").strip()
    fenced = FENCE_RE.match(body)
    if fenced:
        body = fenced.group(1).strip()
    for candidate in (body, body[body.find("{"):body.rfind("}") + 1] if "{" in body else ""):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def check_record(record: dict) -> tuple[dict, list[str]]:
    """The record with every contract key present, and its problems."""
    checked = dict(record)
    problems = []
    for key, (check, empty) in CONTRACT.items():
        if key not in record:
            problems.append(f"missing key {key}")
        elif not check(record[key]):
            problems.append(f"key {key} has the wrong type or value: {json.dumps(record[key])[:80]}")
        else:
            continue
        checked[key] = json.loads(json.dumps(empty))
    return checked, problems


def check_folder(folder: Path) -> dict:
    out: dict[str, list] = {"records": [], "problems": [], "unreadable": [], "warnings": []}
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            text = ""
        record = parse_reply(text)
        if record is None:
            out["unreadable"].append(path.name)
            continue
        checked, problems = check_record(record)
        unit = checked["unit_name"]
        out["records"].append(checked)
        out["problems"] += [{"file": path.name, "unit_name": unit, "problem": p} for p in problems]
        out["warnings"] += [f"{unit or path.name}: {w}" for w in checked["warnings"]]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the per-unit records analyze-source's subagents return (step 4 section 2).",
    )
    parser.add_argument("--dir", required=True, help="The folder that holds one saved reply per unit.")
    args = parser.parse_args(argv)
    folder = Path(args.dir)
    if not folder.is_dir():
        print(f"skf-check-unit-records: {folder.as_posix()} is not a folder", file=sys.stderr)
        return 2
    try:
        result = check_folder(folder)
    except OSError as exc:
        print(f"skf-check-unit-records: cannot read {folder.as_posix()}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
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
