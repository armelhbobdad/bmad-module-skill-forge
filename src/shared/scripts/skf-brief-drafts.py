# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema>=4.0"]
# ///
"""SKF Brief Drafts: find the in-progress draft or the finished briefs that
cover a Brief Skill target.

Brief Skill's step 1 runs this right after the target is validated, to
offer a returning user the draft an earlier run saved for the same target,
then a finished brief to revise. The match is done here, not by eye, so a
target written another way still finds its draft: a trailing slash, a
`.git` suffix, the letter case of a GitHub owner or host, `owner/repo`,
`git@github.com:owner/repo` or a relative local path.

CLI (the target is read from stdin, so a target holding quotes or `$`
reaches it unchanged):

  uv run skf-brief-drafts.py find --forge-data <folder> < target
  uv run skf-brief-drafts.py briefs --forge-data <folder> < target

How a target is compared. Both the target and each stored value are read
with skf-resolve-package.py's parse_target(text, local_first=True), loaded
from this folder, and reduced to one key:

  github      "github:" and the owner/repo, in lower case (a ref, a
              subfolder, a version pin, `.git` and a trailing slash dropped)
  local-path  "path:" and the absolute path, `~` expanded, relative to the
              working folder, in the platform's letter case
              (os.path.normcase); a `file://` prefix is dropped
  an http or https URL, or a host and path with no scheme
              "https://" (http names the same page) and the host in lower
              case, then the path without a trailing slash and the query;
              the fragment is dropped
  anything else
              the text as read, without surrounding whitespace

find
----
Globs <folder>/*/.brief-draft.json. A draft whose folder also holds a
skill-brief.yaml is skipped (that brief is finished; `briefs` lists it),
and so is a file that cannot be read, is not JSON or is not a JSON object.
A draft matches when its `target_repo` has the target's key, or, for a
docs-only draft (`source_type` docs-only), the `url` of any `doc_urls`
entry does: a source draft's supplemental doc URLs, and a URL only in
`intent` or `description`, never match. Prints the newest match (latest
mtime, then the folder name in order), or null:

  {"name": "<folder name>", "path": "<folder>/<name>/.brief-draft.json",
   "mtime": "YYYY-MM-DDTHH:MM:SSZ" (UTC), "holds_scope": true | false}

holds_scope is true when the draft's `scope` is an object: step 3 wrote
it, so a resume goes to step 4.

briefs
------
Globs <folder>/*/skill-brief.yaml and reads each with
skf-validate-brief-schema.py's load_brief_text, loaded from this folder,
so a brief SKF 1.x closed with a trailing `---` is read as the validator
reads it. A file that cannot be read or parsed, or is not a mapping, is
skipped. A brief matches when its `source_repo` has the target's key, or,
for a docs-only brief, the `url` of any `doc_urls` entry does. Prints every
match, newest first (the same order as find), or []:

  [{"name": "<folder name>", "path": "<folder>/<name>/skill-brief.yaml",
    "mtime": "YYYY-MM-DDTHH:MM:SSZ"}, ...]

The brief is not validated here: the step that revises one validates it.

A --forge-data folder that does not exist holds no draft and no brief.

Exit codes:
  0  printed the result (null and [] included)
  2  an empty target ({"error": "..."} on stderr), or a bad argument
     (argparse's usage message on stderr)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOLVE_PACKAGE = HERE / "skf-resolve-package.py"
VALIDATE_BRIEF = HERE / "skf-validate-brief-schema.py"
DRAFT_FILE = ".brief-draft.json"
BRIEF_FILE = "skill-brief.yaml"

_SIBLINGS: dict[str, object] = {}


def _load(path: Path):
    """A sibling script loaded by its path, once. Loaded when a command runs, so --help needs no dependency."""
    module = _SIBLINGS.get(path.name)
    if module is None:
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[path.name] = module
    return module


def target_key(text) -> str | None:
    """The key a target is compared on (see the module docstring), or None for an empty or non-text value."""
    if not isinstance(text, str) or not text.strip():
        return None
    parsed = _load(RESOLVE_PACKAGE).parse_target(text, local_first=True)
    if parsed["kind"] == "github":
        return f"github:{parsed['owner'].lower()}/{parsed['repo'].lower()}"
    if parsed["kind"] == "local-path":
        return "path:" + os.path.normcase(os.path.abspath(os.path.expanduser(parsed["path"])))
    raw = parsed["input"] or text.strip()
    try:
        split = urllib.parse.urlsplit(f"https://{raw}" if parsed["kind"] == "other-host" and "://" not in raw
                                      else raw)
    except ValueError:
        return raw
    if split.scheme.lower() in ("http", "https") and split.netloc:
        key = f"https://{split.netloc.lower()}{split.path.rstrip('/')}"
        return f"{key}?{split.query}" if split.query else key
    return raw


def _keys(record: dict, target_field: str) -> set[str]:
    """The keys of a stored target and, for a docs-only record, of each doc URL entry's `url`."""
    values = [record.get(target_field)]
    doc_urls = record.get("doc_urls")
    if record.get("source_type") == "docs-only" and isinstance(doc_urls, list):
        values += [entry.get("url") for entry in doc_urls if isinstance(entry, dict)]
    return {key for key in map(target_key, values) if key is not None}


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _utc(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _newest_first(found: list[tuple[float, str, dict]]) -> list[dict]:
    return [entry for _, _, entry in sorted(found, key=lambda item: (-item[0], item[1]))]


def find_draft(forge: Path, key: str) -> dict | None:
    """The newest live draft for `key` under `forge`, or None."""
    found = []
    for path in forge.glob(f"*/{DRAFT_FILE}"):
        folder = path.parent
        if (folder / BRIEF_FILE).exists():
            continue
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if not isinstance(draft, dict) or key not in _keys(draft, "target_repo"):
            continue
        mtime = _mtime(path)
        if mtime is None:
            continue
        found.append((mtime, folder.name, {"name": folder.name, "path": str(path), "mtime": _utc(mtime),
                                           "holds_scope": isinstance(draft.get("scope"), dict)}))
    newest = _newest_first(found)
    return newest[0] if newest else None


def find_briefs(forge: Path, key: str) -> list[dict]:
    """Every finished brief for `key` under `forge`, newest first."""
    load_brief_text = None
    found = []
    for path in forge.glob(f"*/{BRIEF_FILE}"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if load_brief_text is None:
            load_brief_text = _load(VALIDATE_BRIEF).load_brief_text
        try:
            brief, error = load_brief_text(text)
        except Exception:  # noqa: BLE001 - a brief this reader cannot parse is skipped, never fatal
            continue
        if error is not None or not isinstance(brief, dict):
            continue
        if key not in _keys(brief, "source_repo"):
            continue
        mtime = _mtime(path)
        if mtime is None:
            continue
        found.append((mtime, path.parent.name, {"name": path.parent.name, "path": str(path), "mtime": _utc(mtime)}))
    return _newest_first(found)


def _read_stdin() -> str:
    """stdin as UTF-8, whatever the locale's code page (cp1252 on Windows)."""
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        return stream.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-brief-drafts",
        description="Find the in-progress draft, or the finished briefs, that cover a Brief Skill target "
                    "(read from stdin).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, text in (("find", "print the newest draft for the target in a folder with no finished brief, "
                                "or null"),
                       ("briefs", "print the finished briefs for the target, newest first, or []")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--forge-data", required=True, help="the forge data folder that holds one folder "
                                                                 "per skill")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    key = target_key(_read_stdin())
    if key is None:
        print(json.dumps({"error": "no target on stdin"}), file=sys.stderr)
        return 2
    forge = Path(args.forge_data)
    if args.cmd == "find":
        result = find_draft(forge, key) if forge.is_dir() else None
    else:
        result = find_briefs(forge, key) if forge.is_dir() else []
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
