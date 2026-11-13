# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Check Unit Records: write and check analyze-source's per-unit records.

Step 4 (map-and-detect.md section 2, through map-unit-exports.md) keeps one
JSON object per qualifying unit, the unit's export surface, as one file of a
folder. `from-extract` writes each one from the extractor's output, so the
model never copies the extractor's JSON into a record, and a subagent edits
it only where the extractor left something to read. The check reads them
all, so the parent neither copies a record, strips a markdown fence nor
checks the contract's keys by hand:

  uv run skf-check-unit-records.py from-extract --extract <file> --exit-code N
      --unit-name <name> --files-count N --language <language> --dir <folder>
  uv run skf-check-unit-records.py --dir <folder>

from-extract
------------
--extract is what skf-extract-public-api.py wrote for one unit, told apart
by its JSON: `mode` "full" is the recipe run (--mode full -o <file>); no
`mode` and an `exports` list (or an `_error`) is quick mode's parser
(--mode quick --all-sources > <file>). --exit-code is that run's exit code,
--files-count the unit's file count (its disqualification record's) and
--language the language detected for the unit. It writes
<folder>/<unit-name>.json (the folder created), every contract key in
order, with ccc_signals {"top_files": [], "available": false}:

  recipe run   exports_count <- counts.exports_public_api; api_surface <-
               the names of entry_point_diff.public[] (a namespace with a
               `members` list as its members' names, one with null
               `members` as its own name), each once, in order;
               export_pattern <- "<entry_points.status>: <type> <n>, ..."
               from aggregates.by_type (count descending, then type), with
               ", capped" when `truncated`; "ast-grep", "T1"; the run's own
               warnings, then a warning per
               extraction gap ("extraction gap: <name> at <file>:<line>",
               "<name> (no file)" without one), per file issue ("file issue:
               <file> (<issue>)") and per errors[] item ("ast-grep run
               incomplete: <reason> (<files> files, first <first_file>)").
  parser       exports_count <- the number of `exports`; api_surface <-
               their names, each once, in order; export_pattern <-
               "parser: <type> <n>, ..."; "parser", "T1"; the parser's
               warnings, less "no manifest content provided; metadata will
               be empty" (the record reads no package metadata).
  source-read  "source-read", "T1-low", exports_count 0, api_surface [],
               export_pattern "" (the reader fills them), with the run's
               warnings: a recipe run whose
               files_in_scope is 0, whose exit code is not 0 or 1 (3: no
               ast-grep) or whose --language has no recipe (any but python,
               javascript, typescript, rust and go), and a parser run whose
               exit code is not 0, that holds an `_error` or whose
               --all-sources found no source file (its warning says so).

It prints one JSON line:

  {"record": "<path written>", "strategy_used": "...", "exports_count": N,
   "to_read": [...]}

`to_read` is what is left to read by eye: on "ast-grep",
{"why": "extraction-gap", "name", "file", "line"} per
entry_point_diff.extraction_gaps[] row and {"why": "file-issue", "file",
"issue"} per file_issues[] item; on "source-read", {"why": "entry-point",
"file"} per entry_points.files[] item when the exit code is 3, the language
has a recipe and the run listed an entry point, else one
{"why": "unit-sources"}; on "parser", nothing.

Exit codes (from-extract):
  0  the record was written
  2  usage error, named on stderr, and nothing written: --exit-code 2 (the
     extractor's own input error: fix its call and run it again), an
     --extract that is missing, empty or neither output above, a
     --unit-name that is empty or holds `/`, `\\` or `..`, a negative
     --files-count, or a record that cannot be written

--dir
-----
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
  strategy_used   "ast-grep" | "parser" | "source-read"
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

Exit codes (--dir):
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

STRATEGIES = ("ast-grep", "parser", "source-read")
CONFIDENCES = ("T1", "T1-low")

# The languages skf-extract-public-api.py has ast-grep recipes for, as
# skf-detect-language.py names them.
RECIPE_LANGUAGES = ("python", "javascript", "typescript", "rust", "go")
# The warning quick mode gives when no manifest is read: the record reads no
# package metadata, so it is no warning there.
NO_MANIFEST_WARNING = "no manifest content provided; metadata will be empty"
# How quick mode's warning starts when --all-sources finds no source file of
# the language: the parser then read nothing of the unit.
ALL_SOURCES_FOUND_NONE = "--all-sources found no "


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


# --------------------------------------------------------------------------
# from-extract: a unit's record from the extractor's output
# --------------------------------------------------------------------------


class UsageError(Exception):
    """An input from-extract cannot use (exit 2, nothing written)."""


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _once(names: list[Any]) -> list[str]:
    """The string names, each once, in order."""
    return list(dict.fromkeys(name for name in names if isinstance(name, str) and name))


def _pattern(head: str, types: list[Any] | dict[str, Any], capped: bool = False) -> str:
    """`<head>: <type> <n>, ...`, count descending then type, from a list of
    each export's type or a {type: count} mapping."""
    counts: dict[str, int] = {}
    if isinstance(types, dict):
        counts = {str(t): n for t, n in types.items() if _is_count(n) and n}
    else:
        for t in types:
            counts[str(t)] = counts.get(str(t), 0) + 1
    parts = ", ".join(f"{t} {n}" for t, n in sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    text = f"{head}: {parts}" if parts else head
    return f"{text}, capped" if capped else text


def _public_names(public: list[Any]) -> list[str]:
    """entry_point_diff.public[] as names: a namespace with a `members`
    list as its members' names, one with null `members` as its own."""
    names: list[Any] = []
    for item in public:
        item = _dict(item)
        members = item.get("members")
        if isinstance(members, list):
            names += [_dict(member).get("name") for member in members]
        else:
            names.append(item.get("name"))
    return _once(names)


def _gap_warning(gap: dict) -> str:
    name, file, line = gap.get("name"), gap.get("file"), gap.get("line")
    if file is None:
        return f"extraction gap: {name} (no file)"
    return f"extraction gap: {name} at {file}:{line}" if line is not None else f"extraction gap: {name} at {file}"


def _source_read(warnings: list[str]) -> dict:
    return {"exports_count": 0, "export_pattern": "", "api_surface": [], "strategy_used": "source-read",
            "confidence": "T1-low", "warnings": warnings}


def _from_recipe_run(data: dict, exit_code: int, language: str) -> tuple[dict, list[dict]]:
    """The record fields and `to_read` of a --mode full output."""
    has_recipe = language in RECIPE_LANGUAGES
    run_warnings = _once(_list(data.get("warnings")))
    if data.get("files_in_scope") == 0 or exit_code not in (0, 1) or not has_recipe:
        entry_points = _dict(data.get("entry_points"))
        files = _once([_dict(item).get("file") for item in _list(entry_points.get("files"))])
        if exit_code == 3 and has_recipe and files:
            return _source_read(run_warnings), [{"why": "entry-point", "file": file} for file in files]
        return _source_read(run_warnings), [{"why": "unit-sources"}]
    diff = _dict(data.get("entry_point_diff"))
    gaps = [_dict(gap) for gap in _list(diff.get("extraction_gaps"))]
    issues = [_dict(issue) for issue in _list(data.get("file_issues"))]
    errors = [_dict(error) for error in _list(data.get("errors"))]
    count = _dict(data.get("counts")).get("exports_public_api")
    status = _dict(data.get("entry_points")).get("status") or "no-entry-point"
    fields = {
        "exports_count": count if _is_count(count) else 0,
        "export_pattern": _pattern(str(status), _dict(_dict(data.get("aggregates")).get("by_type")),
                                   data.get("truncated") is True),
        "api_surface": _public_names(_list(diff.get("public"))),
        "strategy_used": "ast-grep",
        "confidence": "T1",
        "warnings": run_warnings + [_gap_warning(gap) for gap in gaps]
        + [f"file issue: {issue.get('file')} ({issue.get('issue')})" for issue in issues]
        + [f"ast-grep run incomplete: {error.get('reason')} ({error.get('files')} files, first "
           f"{error.get('first_file')})" for error in errors],
    }
    to_read = ([{"why": "extraction-gap", "name": gap.get("name"), "file": gap.get("file"), "line": gap.get("line")}
                for gap in gaps]
               + [{"why": "file-issue", "file": issue.get("file"), "issue": issue.get("issue")} for issue in issues])
    return fields, to_read


def _from_parser(data: dict, exit_code: int) -> tuple[dict, list[dict]]:
    """The record fields and `to_read` of a --mode quick output."""
    warnings = [w for w in _once(_list(data.get("warnings"))) if w != NO_MANIFEST_WARNING]
    if exit_code != 0 or "_error" in data or any(w.startswith(ALL_SOURCES_FOUND_NONE) for w in warnings):
        return _source_read(warnings), [{"why": "unit-sources"}]
    exports = [_dict(export) for export in _list(data.get("exports"))]
    fields = {
        "exports_count": len(exports),
        "export_pattern": _pattern("parser", [export.get("type") for export in exports]),
        "api_surface": _once([export.get("name") for export in exports]),
        "strategy_used": "parser",
        "confidence": "T1",
        "warnings": warnings,
    }
    return fields, []


def _read_extract(path: Path) -> dict:
    """The extractor output at `path`, as a dict. Raises UsageError."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise UsageError(f"--extract {path.as_posix()} does not exist: the extraction wrote nothing") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read --extract {path.as_posix()}: {getattr(exc, 'strerror', None) or exc}") from exc
    if not text.strip():
        raise UsageError(f"--extract {path.as_posix()} is empty: the extraction wrote nothing")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--extract {path.as_posix()} is not JSON: {exc}") from exc
    if not isinstance(data, dict) or not (
        data.get("mode") == "full" or ("mode" not in data and (isinstance(data.get("exports"), list)
                                                                or "_error" in data))
    ):
        raise UsageError(f"--extract {path.as_posix()} is neither a --mode full output nor a --mode quick one")
    return data


def from_extract(extract: Path, exit_code: int, unit_name: str, files_count: int, language: str,
                 folder: Path) -> dict:
    """Write one unit's record from the extractor's output; returns the
    line to print. Raises UsageError before writing anything."""
    if exit_code == 2:
        raise UsageError("the extractor exited 2, an input error it names on stderr: fix its call and run it again")
    if not unit_name.strip() or "/" in unit_name or "\\" in unit_name or ".." in unit_name:
        raise UsageError(f"--unit-name must name one file of the folder (no /, \\ or ..): {unit_name!r}")
    if files_count < 0:
        raise UsageError(f"--files-count must be 0 or more: {files_count}")
    data = _read_extract(extract)
    language = language.strip().lower()
    if data.get("mode") == "full":
        fields, to_read = _from_recipe_run(data, exit_code, language)
    else:
        fields, to_read = _from_parser(data, exit_code)
    fields.update(unit_name=unit_name, files_count=files_count,
                  ccc_signals={"top_files": [], "available": False})
    record, problems = check_record({key: fields[key] for key in CONTRACT})
    record["warnings"] += [f"record: {problem}" for problem in problems]
    target = folder / f"{unit_name}.json"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot write {target.as_posix()}: {exc.strerror or exc}") from exc
    return {"record": target.as_posix(), "strategy_used": record["strategy_used"],
            "exports_count": record["exports_count"], "to_read": to_read}


def _from_extract_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-check-unit-records.py from-extract",
        description="Write one unit's record from skf-extract-public-api.py's output (map-unit-exports.md "
                    "section 2).",
    )
    parser.add_argument("--extract", required=True, metavar="FILE",
                        help="the extractor's output: a --mode full -o file or a --mode quick stdout")
    parser.add_argument("--exit-code", required=True, type=int, metavar="N", help="the extractor's exit code")
    parser.add_argument("--unit-name", required=True, metavar="NAME", help="the unit's name: the record's file name")
    parser.add_argument("--files-count", required=True, type=int, metavar="N",
                        help="the unit's file count (its disqualification record's files_count)")
    parser.add_argument("--language", required=True, metavar="LANG", help="the language detected for the unit")
    parser.add_argument("--dir", required=True, metavar="FOLDER", help="the folder the record is written to")
    args = parser.parse_args(argv)
    try:
        line = from_extract(Path(args.extract), args.exit_code, args.unit_name, args.files_count, args.language,
                            Path(args.dir))
    except UsageError as exc:
        print(f"skf-check-unit-records from-extract: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(line, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["from-extract"]:
        return _from_extract_main(argv[1:])
    parser = argparse.ArgumentParser(
        description="Check the per-unit records analyze-source's subagents return (step 4 section 2).",
        epilog="`skf-check-unit-records.py from-extract` writes one unit's record from skf-extract-public-api.py's "
               "output: `from-extract --help` lists its flags.",
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
