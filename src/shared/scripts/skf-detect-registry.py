# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Detect Registry: a component library's files, its demo files and its
component registry, listed, counted and scored for create-skill step 3d.

create-skill's component-library extraction (references/component-extraction.md)
leaves demo and example files out before it extracts, and reads the
component registry, an array of entries such as `{id, name, category}`, as
the library's primary API surface. Listing the files in the brief's scope,
counting the demo files per pattern, scoring each registry candidate by its
entries and fields and listing the registry's entries is fixed work, and the
score alone decides whether a headless run uses a candidate, so this helper
does all of it. The step keeps the user's confirmation and the judgment on
whether a borderline candidate really is the registry.

CLI:
  uv run skf-detect-registry.py demo (--source-root <dir> | --files-from <list>) \\
      [--brief <skill-brief.yaml>] [--pattern GLOB]... [--files-to <file>] \\
      [--kept-to <file>]
  uv run skf-detect-registry.py registry --files-from <list> --source-root <dir>
  uv run skf-detect-registry.py registry --source-root <dir> --path <file> [--entries]
  uv run skf-detect-registry.py registry --files-from <list> --candidates-only

--files-from reads a file list: one path per line, relative to the source
root, or a JSON list of paths; `-` reads it from stdin. A list that opens
with `[` but is not a JSON list of strings is read line by line (a Next.js
route such as `[slug]/page.tsx` can come first).

demo
----
Which files. --source-root lists the files under it: those git lists there
(tracked, and untracked but not ignored), or every file when it is not in a
git work tree, leaving out hidden entries and symbolic links, as
skf-extract-public-api.py --mode full lists a tree. --files-from takes the
paths a list names instead (a remote repository's tree listing). --brief
keeps those its scope.include globs match (every file when it has none) and
no scope.exclude glob does: the step's filtered file list. --files-to writes
that list, and --kept-to the files of it no demo pattern matches, each as a
JSON list, which --files-from here and skf-extract-public-api.py's
--files-from both read whatever the paths hold.

Which patterns. Without --pattern, the auto-detected patterns (DEMO_FOLDERS
as `**/<folder>/**`, DEMO_FILE_PATTERNS as `**/<pattern>`) are tried and
only those that match a file are reported. With --pattern (the brief's
`scope.demo_patterns`, or the patterns the user gave), each is reported,
matched or not, and `also_matched` reports the auto-detected patterns that
match a file the given ones leave in. A given pattern is read as a glob,
with two shorthands: a name ending in `/` with no other `/` is a folder at
any depth (`examples/` is `**/examples/**`), and a pattern with no `/` is a
file name at any depth (`*.stories.*` is `**/*.stories.*`). Globs follow
skf-resolve-authoritative-files.py's rules (the sibling in this folder):
`**` spans any number of path segments, none included, and `*` and `?` stay
inside one.

  {
    "mode": "auto" | "given",
    "files_listed": N,    # the files --source-root or --files-from gave
    "files_scanned": N,   # those in --brief's scope
    "patterns": [{"pattern": "<glob>", "files": N,
                  "sample": ["<path>", ...]}, ...],   # up to 3 paths each
    "excluded": N,        # files at least one pattern matches
    "directories": N,     # distinct folders holding them
    "kept": N,
    "also_matched": [{"pattern", "files", "sample"}, ...],  # with --pattern
    "files_file": "<path>" | null,
    "kept_file": "<path>" | null
  }

registry
--------
The candidates are the listed files named, in priority order (`rule`):
  1  registry.ts, registry.tsx or registry.js, in any folder
  2  components.ts or components.tsx in a registry/, catalog/ or components/
     folder
  3  index.ts or index.tsx in a registry/ or catalog/ folder
With --path, the one file it names is the only candidate (a brief's
`scope.registry_path`, or a path the user gave), listed or not.

Each candidate is read from --source-root, and its largest array of object
literals is taken as the registry: its entries are the object literals it
holds, and `fields` counts, for each key, the entries that have it (a
spread such as `...base` and a computed key such as `[key]: value` add no
key). The score, out of 9:
  +3  every entry has `id`
  +2  every entry has `name` or every entry has `component`
  +2  every entry has `category` or every entry has `tags`
  +1  the file's folder is registry/ or catalog/
  +1  20 or more entries
A candidate qualifies with 10 or more entries and a score of 5 or more.
`selected` is the qualifying candidate with the highest score (then the
lower rule, then the path), and `headless_accept` is true when its score is
7 or more: the score a headless run accepts a candidate at without asking.
With --path, the file is selected whatever its score, and headless_accept
is true, unless it cannot be read or lies outside --source-root: then its
`error` says why, selected is null and headless_accept false.

The parse is lexical, for JavaScript and TypeScript (JSX included): strings,
template literals, comments and regular expression literals are skipped,
and brackets are matched. A file it cannot read is listed with its `error`
and no entries.

  {
    "explicit": bool,     # --path was given
    "candidates": [{"path", "rule": 0-3,   # 0: --path
                    "error": null | "<why it was not read>",
                    "array": {"name": "<binding or key>" | null,
                              "line": N, "annotation": "<type>" | null} | null,
                    "entry_count": N, "other_elements": N,
                    "fields": {"<key>": N, ...},
                    "score": N, "score_parts": {"id", "name_or_component",
                        "category_or_tags", "registry_folder",
                        "entries_20_plus"},
                    "qualifies": bool,
                    "sample": [{"line": N, "id"?, "name"?, "component"?,
                                "category"?, "tags"?}, ...],
                    "entries": [{"line": N, "keys": ["<key>", ...],
                                 "id"?, ..., "description"?}, ...]},
                   ...],          # entries: --entries, selected one only
    "selected": "<path>" | null,
    "headless_accept": bool
  }

`sample` holds the first 5 entries, each with the line of its `{` and the
SAMPLE_FIELDS it has: a string's text, a list of strings, or the value's
source (whitespace collapsed), cut at 80 characters. --entries adds
`entries` to the selected candidate: every entry, with the line of its
`{`, `keys` (every key it has, in order) and the ENTRY_FIELDS it has, in
full. The candidates are listed qualifying first, in the order `selected`
is picked from. --candidates-only prints the candidate paths the list
holds, one per line (LF, on Windows too), and reads no file: a caller
without a local tree fetches exactly those into a folder and passes it as
--source-root.

Exit codes:
  0  JSON (or, with --candidates-only, the paths) printed, a
     candidate-free list included
  2  usage error, or a file list, a brief or a folder that cannot be read
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import posixpath
import re
import sys
from pathlib import Path
from typing import NamedTuple

DEMO_FOLDERS = ("demo", "demos", "stories", "__stories__", "storybook", "examples", "example")
DEMO_FILE_PATTERNS = ("*.stories.*", "*.story.*", "*.example.*", "*.demo.*")
DEMO_SAMPLE = 3

# (rule, file names, folders the file must sit in; None for any folder)
REGISTRY_RULES = (
    (1, ("registry.ts", "registry.tsx", "registry.js"), None),
    (2, ("components.ts", "components.tsx"), ("registry", "catalog", "components")),
    (3, ("index.ts", "index.tsx"), ("registry", "catalog")),
)
REGISTRY_FOLDERS = ("registry", "catalog")
MIN_ENTRIES = 10
MIN_SCORE = 5
AUTO_ACCEPT_SCORE = 7
MANY_ENTRIES = 20
SAMPLE_SIZE = 5
SAMPLE_FIELDS = ("id", "name", "component", "category", "tags")
ENTRY_FIELDS = (*SAMPLE_FIELDS, "description")
VALUE_TEXT_LIMIT = 80

_SIBLINGS: dict[str, object] = {}


class UsageError(Exception):
    """An input the helper cannot use (exit 2)."""


# --------------------------------------------------------------------------
# File list
# --------------------------------------------------------------------------


def _norm(path: object) -> str:
    """A path as the helper compares it: forward slashes, no leading `./`."""
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _sibling(filename: str):
    """A helper beside this script, loaded once: skf-resolve-authoritative-files.py
    (the brief, its scope and the glob rules) and skf-source-tree.py (git
    without the caller's hooks, never one planted in the current folder)."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = Path(__file__).resolve().parent / filename
        name = "skf_" + filename.removeprefix("skf-").removesuffix(".py").replace("-", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise UsageError(f"cannot load {filename} beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[filename] = module
    return module


def _hidden(rel: str) -> bool:
    return any(part.startswith(".") for part in rel.split("/"))


def list_tree(root: Path) -> list[str]:
    """The files under `root` (see the demo section of the module docstring),
    as sorted POSIX paths relative to it: those git lists in a git work
    tree, else every file, as when git lists none."""
    listed: list[str] = []
    res = _sibling("skf-source-tree.py")._git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if res is not None and res[0] == 0:
        for raw in res[1].split(b"\0"):
            rel = os.fsdecode(raw).replace("\\", "/") if raw else ""
            if rel and (root / rel).is_file() and not (root / rel).is_symlink():
                listed.append(rel)
    if not listed:
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = sorted(d for d in dirnames
                                 if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d)))
            for name in filenames:
                if not name.startswith(".") and not os.path.islink(os.path.join(dirpath, name)):
                    listed.append(f"{rel_dir}/{name}" if rel_dir else name)
    return sorted(rel for rel in listed if not _hidden(rel))


def brief_scope(brief: str) -> tuple[list[str], list[str]]:
    """(scope.include, scope.exclude) of a skill brief, as globs."""
    resolver = _sibling("skf-resolve-authoritative-files.py")
    try:
        includes, excludes, _amendments = resolver.extract_scope(resolver.load_brief(Path(brief)))
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    return [g for g in map(_norm, includes) if g], [g for g in map(_norm, excludes) if g]


def in_scope(files: list[str], includes: list[str], excludes: list[str]) -> list[str]:
    """The files an include glob matches (every file when there is none) and no exclude glob does."""
    glob_match = _sibling("skf-resolve-authoritative-files.py").glob_match
    return [rel for rel in files
            if (not includes or any(glob_match(rel, g) for g in includes))
            and not any(glob_match(rel, g) for g in excludes)]


def read_file_list(source: str) -> list[str]:
    """The paths of a --files-from list (a file, or `-` for stdin), in order, each once."""
    if source == "-":
        text = sys.stdin.read()
    else:
        try:
            text = Path(source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UsageError(f"cannot read file list {source}: {exc}") from exc
    items: object = None
    if text.lstrip().startswith("["):
        try:
            items = json.loads(text)
        except ValueError:
            items = None
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        items = text.splitlines()
    return list(dict.fromkeys(rel for rel in (_norm(item) for item in items) if rel))


# --------------------------------------------------------------------------
# demo
# --------------------------------------------------------------------------


def auto_patterns() -> list[str]:
    """The auto-detected demo patterns, folders first, as globs."""
    return [f"**/{name}/**" for name in DEMO_FOLDERS] + [f"**/{pattern}" for pattern in DEMO_FILE_PATTERNS]


def normalize_pattern(pattern: str) -> str | None:
    """A given demo pattern as a glob (see the demo section of the module docstring)."""
    text = _norm(pattern)
    if not text:
        return None
    if text.endswith("/"):
        folder = text.rstrip("/")
        if not folder:
            return None
        return f"**/{folder}/**" if "/" not in folder else f"{folder}/**"
    return text if "/" in text else f"**/{text}"


def _matches(files: list[str], patterns: list[str]) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """(the files each pattern matches, the files any matches, the others)."""
    glob_match = _sibling("skf-resolve-authoritative-files.py").glob_match
    matches: dict[str, list[str]] = {p: [] for p in patterns}
    hit: list[str] = []
    missed: list[str] = []
    for rel in files:
        found = [p for p in patterns if glob_match(rel, p)]
        for p in found:
            matches[p].append(rel)
        (hit if found else missed).append(rel)
    return matches, hit, missed


def _report(matches: dict[str, list[str]], every: bool) -> list[dict]:
    return [{"pattern": p, "files": len(found), "sample": sorted(found)[:DEMO_SAMPLE]}
            for p, found in matches.items() if found or every]


def detect_demo(files: list[str], given: list[str] | None = None) -> tuple[dict, list[str]]:
    """(the demo result, the kept files) for a file list."""
    if given is None:
        patterns, mode = auto_patterns(), "auto"
    else:
        patterns = list(dict.fromkeys(p for p in (normalize_pattern(g) for g in given) if p))
        mode = "given"
    matches, excluded, kept = _matches(files, patterns)
    also = _report(_matches(kept, auto_patterns())[0], False) if mode == "given" else []
    result = {
        "mode": mode,
        "files_listed": len(files),
        "files_scanned": len(files),
        "patterns": _report(matches, mode == "given"),
        "excluded": len(excluded),
        "directories": len({posixpath.dirname(rel) for rel in excluded}),
        "kept": len(kept),
        "also_matched": also,
        "files_file": None,
        "kept_file": None,
    }
    return result, kept


# --------------------------------------------------------------------------
# registry: lexical scan
# --------------------------------------------------------------------------


class Token(NamedTuple):
    kind: str  # "punct", "str", "ident", "num", "other"
    text: str  # a string's text, else the token as written
    start: int
    end: int
    line: int


_IDENT_RE = re.compile(r"[A-Za-z_$À-￿][\w$À-￿]*")
_NUMBER_RE = re.compile(r"\d[\w.]*")
_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {")", "]", "}"}
# After one of these a `/` opens a regular expression literal, not a division.
_REGEX_KEYWORDS = frozenset({"return", "typeof", "case", "in", "of", "new", "delete", "void", "throw",
                             "instanceof", "yield", "await", "else", "do"})
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _quoted(src: str, i: int) -> tuple[str, int] | None:
    """(text, index after the closing quote) of the string opening at src[i], or None
    when the line ends first (an apostrophe in JSX text is no string)."""
    quote = src[i]
    out: list[str] = []
    j = i + 1
    while j < len(src):
        ch = src[j]
        if ch == "\\" and j + 1 < len(src):
            nxt = src[j + 1]
            if nxt == "\n":
                j += 2
                continue
            out.append(_ESCAPES.get(nxt, nxt))
            j += 2
            continue
        if ch == quote:
            return "".join(out), j + 1
        if ch == "\n":
            return None
        out.append(ch)
        j += 1
    return None


def _skip_template(src: str, i: int) -> int:
    """The index after the template literal opening at src[i] (a backtick),
    its `${ ... }` expressions included, however nested."""
    j = i + 1
    while j < len(src):
        ch = src[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "`":
            return j + 1
        if ch == "$" and src.startswith("${", j):
            j = _skip_expression(src, j + 2)
            continue
        j += 1
    return len(src)


def _skip_expression(src: str, j: int) -> int:
    """The index after the `}` that closes a template expression starting at src[j]."""
    depth = 0
    while j < len(src):
        ch = src[j]
        if ch in "'\"":
            quoted = _quoted(src, j)
            j = quoted[1] if quoted else j + 1
            continue
        if ch == "`":
            j = _skip_template(src, j)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                return j + 1
            depth -= 1
        j += 1
    return len(src)


def _regex_end(src: str, i: int) -> int | None:
    """The index after the regular expression literal opening at src[i], or None
    when the line ends first."""
    j = i + 1
    in_class = False
    while j < len(src):
        ch = src[j]
        if ch == "\n":
            return None
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            while j < len(src) and (src[j].isalnum() or src[j] == "_"):
                j += 1
            return j
        j += 1
    return None


def _regex_allowed(prev: Token | None) -> bool:
    """True when a `/` after `prev` opens a regular expression literal."""
    if prev is None:
        return True
    if prev.kind == "ident":
        return prev.text in _REGEX_KEYWORDS
    if prev.kind in ("str", "num"):
        return False
    return prev.text not in (")", "]", "}", "<")


def tokenize(src: str) -> list[Token]:
    """The tokens of a JavaScript or TypeScript source, comments left out."""
    tokens: list[Token] = []
    line_starts = [0] + [m.end() for m in re.finditer("\n", src)]

    def line_of(pos: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end == -1 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        start = i
        if ch in "'\"":
            quoted = _quoted(src, i)
            if quoted is None:
                tokens.append(Token("other", ch, start, i + 1, line_of(start)))
                i += 1
            else:
                tokens.append(Token("str", quoted[0], start, quoted[1], line_of(start)))
                i = quoted[1]
            continue
        if ch == "`":
            end = _skip_template(src, i)
            tokens.append(Token("str", src[i + 1:end - 1], start, end, line_of(start)))
            i = end
            continue
        if ch == "/" and _regex_allowed(tokens[-1] if tokens else None):
            end = _regex_end(src, i)
            if end is not None:
                tokens.append(Token("other", src[i:end], start, end, line_of(start)))
                i = end
                continue
        m = _IDENT_RE.match(src, i)
        if m:
            tokens.append(Token("ident", m.group(0), start, m.end(), line_of(start)))
            i = m.end()
            continue
        m = _NUMBER_RE.match(src, i)
        if m:
            tokens.append(Token("num", m.group(0), start, m.end(), line_of(start)))
            i = m.end()
            continue
        if src.startswith("...", i):
            tokens.append(Token("punct", "...", start, i + 3, line_of(start)))
            i += 3
            continue
        if src.startswith("=>", i):
            tokens.append(Token("punct", "=>", start, i + 2, line_of(start)))
            i += 2
            continue
        tokens.append(Token("punct", ch, start, i + 1, line_of(start)))
        i += 1
    return tokens


def match_brackets(tokens: list[Token]) -> dict[int, int]:
    """Index of each opening bracket -> index of its closing one (unmatched ones left out)."""
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for index, token in enumerate(tokens):
        if token.kind != "punct":
            continue
        if token.text in _OPENERS:
            stack.append(index)
        elif token.text in _CLOSERS:
            while stack:
                opener = stack.pop()
                if _OPENERS[tokens[opener].text] == token.text:
                    pairs[opener] = index
                    break
    return pairs


def _split(tokens: list[Token], pairs: dict[int, int], start: int, end: int) -> list[tuple[int, int]]:
    """The comma-separated parts of tokens[start:end] as (start, end) ranges, empty ones left out."""
    parts: list[tuple[int, int]] = []
    i = head = start
    while i < end:
        token = tokens[i]
        if token.kind == "punct" and token.text in _OPENERS and i in pairs:
            i = pairs[i] + 1
            continue
        if token.kind == "punct" and token.text == ",":
            if i > head:
                parts.append((head, i))
            head = i + 1
        i += 1
    if end > head:
        parts.append((head, end))
    return parts


def _source(src: str, tokens: list[Token], start: int, end: int) -> str:
    return " ".join(src[tokens[start].start:tokens[end - 1].end].split())


def _value(src: str, tokens: list[Token], start: int, end: int, pairs: dict[int, int]):
    """An entry value: a string's text, a list of strings, or the value's source."""
    if end - start == 1 and tokens[start].kind in ("str", "ident", "num"):
        return tokens[start].text
    if tokens[start].text == "[" and pairs.get(start) == end - 1:
        items = _split(tokens, pairs, start + 1, end - 1)
        if all(b - a == 1 and tokens[a].kind == "str" for a, b in items):
            return [tokens[a].text for a, _ in items]
    return _source(src, tokens, start, end)


def _cut(value):
    """A sample value: a text longer than VALUE_TEXT_LIMIT cut short."""
    if isinstance(value, str) and len(value) > VALUE_TEXT_LIMIT:
        return value[:VALUE_TEXT_LIMIT - 3] + "..."
    return value


def _object_entry(src: str, tokens: list[Token], pairs: dict[int, int], open_index: int) -> dict:
    """{keys, line, values} of the object literal whose `{` is tokens[open_index]."""
    keys: list[str] = []
    values: dict = {}
    for a, b in _split(tokens, pairs, open_index + 1, pairs[open_index]):
        first = tokens[a]
        if first.text == "...":
            continue
        key = None
        value_start = None
        if first.kind in ("ident", "str", "num"):
            nxt = tokens[a + 1] if a + 1 < b else None
            if nxt is None:
                key, value_start = first.text, a  # shorthand: `{ id, name }`
            elif nxt.text == ":":
                key, value_start = first.text, a + 2
            elif nxt.text in ("(", "<"):
                key = first.text  # a method
            elif first.kind == "ident" and first.text in ("get", "set", "async") and nxt.kind == "ident":
                key = nxt.text
        if key is None or key in keys:
            continue
        keys.append(key)
        if key in ENTRY_FIELDS and value_start is not None and value_start < b:
            values[key] = _value(src, tokens, value_start, b, pairs)
    return {"keys": keys, "line": tokens[open_index].line, "values": values}


def _binding(src: str, tokens: list[Token], open_index: int) -> tuple[str | None, str | None]:
    """(name, type annotation) of what the array at tokens[open_index] is bound to."""
    if open_index == 0:
        return None, None
    prev = tokens[open_index - 1]
    if prev.text == ":" and open_index >= 2 and tokens[open_index - 2].kind in ("ident", "str"):
        return tokens[open_index - 2].text, None  # `items: [` in an object
    if prev.text == "default" and open_index >= 2 and tokens[open_index - 2].text == "export":
        return "default", None
    if prev.text != "=":
        return None, None
    # Walk back over `name: Type =` to a declared name.
    i = open_index - 2
    colon = None
    depth = 0
    while i >= 0:
        token = tokens[i]
        if token.kind == "punct" and token.text in _CLOSERS:
            depth += 1
        elif token.kind == "punct" and token.text in _OPENERS:
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and token.text in (";", "=", ","):
            break
        elif depth == 0 and token.text == ":" and colon is None:
            colon = i
        elif depth == 0 and token.kind == "ident" and i > 0 and tokens[i - 1].text in ("const", "let", "var"):
            annotation = _source(src, tokens, colon + 1, open_index - 1) if colon is not None else None
            return token.text, annotation
        i -= 1
    if open_index >= 2 and tokens[open_index - 2].kind == "ident":  # `module.exports = [`
        j = open_index - 2
        while j >= 2 and tokens[j - 1].text == "." and tokens[j - 2].kind == "ident":
            j -= 2
        return _source(src, tokens, j, open_index - 1), None
    return None, None


def registry_arrays(src: str) -> list[dict]:
    """Every array literal of the source that holds object literals."""
    tokens = tokenize(src)
    pairs = match_brackets(tokens)
    arrays = []
    for open_index, close_index in sorted(pairs.items()):
        if tokens[open_index].text != "[":
            continue
        entries = []
        others = 0
        for a, b in _split(tokens, pairs, open_index + 1, close_index):
            if tokens[a].text == "{" and pairs.get(a) == b - 1:
                entries.append(_object_entry(src, tokens, pairs, a))
            else:
                others += 1
        if entries:
            name, annotation = _binding(src, tokens, open_index)
            arrays.append({"name": name, "line": tokens[open_index].line, "annotation": annotation,
                           "entries": entries, "other_elements": others})
    return arrays


# --------------------------------------------------------------------------
# registry: candidates and score
# --------------------------------------------------------------------------


def candidate_rule(rel: str) -> int | None:
    """The rule (1-3) a listed path is a registry candidate by, else None."""
    folder, name = posixpath.split(rel)
    parent = posixpath.basename(folder)
    for rule, names, folders in REGISTRY_RULES:
        if name in names and (folders is None or parent in folders):
            return rule
    return None


def score_candidate(rel: str, entry_count: int, fields: dict[str, int]) -> dict[str, int]:
    """The score parts of a candidate (see the registry section of the module docstring)."""
    everywhere = {key for key, count in fields.items() if entry_count and count == entry_count}
    return {
        "id": 3 if "id" in everywhere else 0,
        "name_or_component": 2 if everywhere & {"name", "component"} else 0,
        "category_or_tags": 2 if everywhere & {"category", "tags"} else 0,
        "registry_folder": 1 if posixpath.basename(posixpath.dirname(rel)) in REGISTRY_FOLDERS else 0,
        "entries_20_plus": 1 if entry_count >= MANY_ENTRIES else 0,
    }


def evaluate(root: Path, rel: str, rule: int, entries: bool = False) -> dict:
    """One candidate, read from root and scored; with `entries`, every entry listed."""
    result = {"path": rel, "rule": rule, "error": None, "array": None, "entry_count": 0,
              "other_elements": 0, "fields": {}, "score": 0, "score_parts": {}, "qualifies": False,
              "sample": []}
    target = root / rel
    try:
        if not target.resolve().is_relative_to(root.resolve()):
            raise OSError("the path leads outside --source-root")
        src = target.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        result["error"] = f"cannot read {rel}: {exc}"
        result["score_parts"] = score_candidate(rel, 0, {})
        result["score"] = sum(result["score_parts"].values())
        return result
    arrays = registry_arrays(src.replace("\r\n", "\n"))
    best = max(arrays, key=lambda a: len(a["entries"]), default=None)  # max keeps the first of a tie
    fields: dict[str, int] = {}
    if best is not None:
        for entry in best["entries"]:
            for key in entry["keys"]:
                fields[key] = fields.get(key, 0) + 1
        result["array"] = {"name": best["name"], "line": best["line"], "annotation": best["annotation"]}
        result["entry_count"] = len(best["entries"])
        result["other_elements"] = best["other_elements"]
        result["sample"] = [{"line": e["line"], **{k: _cut(v) for k, v in e["values"].items() if k in SAMPLE_FIELDS}}
                            for e in best["entries"][:SAMPLE_SIZE]]
        if entries:
            result["entries"] = [{"line": e["line"], "keys": e["keys"], **e["values"]} for e in best["entries"]]
    result["fields"] = dict(sorted(fields.items()))
    result["score_parts"] = score_candidate(rel, result["entry_count"], fields)
    result["score"] = sum(result["score_parts"].values())
    result["qualifies"] = result["entry_count"] >= MIN_ENTRIES and result["score"] >= MIN_SCORE
    return result


def detect_registry(root: Path, files: list[str], path: str | None = None, entries: bool = False) -> dict:
    """The registry result for a file list, or for the one file --path names;
    with `entries`, the selected candidate lists every entry."""
    if path is not None:
        candidate = evaluate(root, _norm(path), 0, entries)
        readable = candidate["error"] is None
        return {"explicit": True, "candidates": [candidate],
                "selected": candidate["path"] if readable else None, "headless_accept": readable}
    candidates = [evaluate(root, rel, rule) for rel in files if (rule := candidate_rule(rel)) is not None]
    candidates.sort(key=lambda c: (not c["qualifies"], -c["score"], c["rule"], c["path"]))
    selected = candidates[0] if candidates and candidates[0]["qualifies"] else None
    if selected is not None and entries:
        candidates[0] = selected = evaluate(root, selected["path"], selected["rule"], True)
    return {
        "explicit": False,
        "candidates": candidates,
        "selected": selected["path"] if selected else None,
        "headless_accept": bool(selected and selected["score"] >= AUTO_ACCEPT_SCORE),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-detect-registry.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="list the files in scope and count the files each demo pattern matches")
    files = demo.add_mutually_exclusive_group(required=True)
    files.add_argument("--source-root", metavar="DIR", help="list the files under this folder")
    files.add_argument("--files-from", metavar="FILE",
                       help="a file list: one path per line or a JSON list; - for stdin")
    demo.add_argument("--brief", metavar="FILE", help="keep the files in this skill brief's scope")
    demo.add_argument("--pattern", action="append", metavar="GLOB",
                      help="a demo pattern (the brief's scope.demo_patterns or the user's); repeatable")
    demo.add_argument("--files-to", metavar="FILE", help="write the files in scope here, as a JSON list")
    demo.add_argument("--kept-to", metavar="FILE", help="write the files no pattern matches here, as a JSON list")
    registry = sub.add_parser("registry", help="find and score the component registry candidates")
    registry.add_argument("--files-from", metavar="FILE",
                          help="the filtered file list: one path per line or a JSON list; - for stdin")
    registry.add_argument("--source-root", metavar="DIR", help="the folder the listed paths are relative to")
    registry.add_argument("--path", metavar="FILE", help="score this file only (relative to --source-root)")
    registry.add_argument("--candidates-only", action="store_true",
                          help="print the candidate paths, one per line, and read no file")
    registry.add_argument("--entries", action="store_true", help="list every entry of the selected candidate")
    return parser


def _write_list(target: str, paths: list[str]) -> None:
    try:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes((json.dumps(paths, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError as exc:
        raise UsageError(f"cannot write {target}: {exc}") from exc


def _run(args: argparse.Namespace) -> int:
    if args.command == "demo":
        if args.source_root is not None:
            if not Path(args.source_root).is_dir():
                raise UsageError(f"--source-root must name a folder, got {args.source_root!r}")
            listed = list_tree(Path(args.source_root))
        else:
            listed = read_file_list(args.files_from)
        files = in_scope(listed, *brief_scope(args.brief)) if args.brief else listed
        result, kept = detect_demo(files, args.pattern)
        result["files_listed"] = len(listed)
        for option, key, paths in ((args.files_to, "files_file", files), (args.kept_to, "kept_file", kept)):
            if option:
                _write_list(option, paths)
                result[key] = option
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.candidates_only:
        if not args.files_from:
            raise UsageError("--candidates-only needs --files-from")
        files = read_file_list(args.files_from)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="\n")  # a shell loop reads the lines: no CR on Windows
        sys.stdout.write("".join(rel + "\n" for rel in files if candidate_rule(rel) is not None))
        return 0
    if not args.source_root or not Path(args.source_root).is_dir():
        raise UsageError(f"--source-root must name a folder, got {args.source_root!r}")
    if args.path is None and not args.files_from:
        raise UsageError("registry needs --files-from, or --path for one file")
    files = read_file_list(args.files_from) if args.files_from and args.path is None else []
    print(json.dumps(detect_registry(Path(args.source_root), files, args.path, args.entries), ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _run(args)
    except UsageError as exc:
        sys.stderr.write(f"skf-detect-registry: {exc}\n")
        return 2


def _force_utf8(*streams) -> None:
    """Reconfigure stdin, stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every
    character of a path or a registry value the JSON carries, nor read a
    UTF-8 file list piped to stdin (reconfigured here, before the first
    read).
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
