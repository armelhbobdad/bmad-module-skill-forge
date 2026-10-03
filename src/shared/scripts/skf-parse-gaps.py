# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Parse Gaps: read a test report's gaps as JSON for update-skill.

skf-update-skill's gap-driven mode (`--from-test-report`) turns each gap of a
test report into a change-manifest entry: its severity, category, source
citation, remediation text and the source paths the remediation names.
Reading them by eye from the Gap Report, extracting paths by file extension
and checking that a path stays inside the source tree is fiddly work that
drifts between runs. This helper does it once.

Where the gaps come from:

  1. The gap ledger, when there is one: `test-findings-{run_id}.json` beside
     the report (the run id is the report's `runId` frontmatter, else the one
     in its file name), or the file --ledger names. test-skill's stages write
     it (gap-ledger.py) and the Gap Report is rendered from it. A ledger
     whose `schema_version` is not 1 is refused (LEDGER_INVALID) rather than
     read with the wrong field meanings.
  2. Otherwise the rendered `## Gap Report` section of the report, for
     reports written before the ledger existed: each `### GAP-{NNN}: {title}`
     entry with its `**Severity:**`, `**Category:**`, `**Source:**`,
     `**Export:**`, `**Issue:**` and `**Remediation:**` lines. Every
     `## Gap Report` section is read, so a report that holds the section
     twice (a placeholder and an appended copy) still yields its gaps; an id
     seen twice is kept once.

Subcommands:

  parse [--report <test-report.md>] [--ledger <test-findings.json>]
        [--source-root <dir>] [--ext <extension> ...]
        [--provenance-map <provenance-map.json>]

  paths --source-root <dir> [--ext <extension> ...]
        [--provenance-map <provenance-map.json>] <path> [<path> ...]

  match --provenance-map <provenance-map.json> --name <export>
        [--citation <file:line>]

  translate --gaps <parse's output> --provenance-map <provenance-map.json>
            [--judgments <answers.json>] [--read-only dry-run|detect-only]
            [--date YYYY-MM-DD] -o <change-manifest.json>

  `parse`: at least one of --report and --ledger. --ext (repeatable, `kt`
  or `.vue`) adds a source file extension to the list below, and
  --provenance-map adds the extension of each file its entries[]
  source_file values name, for a skill whose source holds files of another
  language, and each gap's `map_match` (see "Map match" below). Output
  (stdout):

  {
    "status": "ok",
    "read_from": "ledger" | "gap-report",
    "report_path": "<path>" | null,
    "ledger_path": "<path>" | null,
    "source_root": "<real path>" | null,
    "gap_count": N,
    "counts": {"Critical": n, "High": n, "Medium": n, "Low": n, "Info": n},
    "gaps": [                                  # Critical first, then by id
      {
        "id": "GAP-001",
        "title": "...",
        "severity": "Critical" | ... | null,  # null: unreadable in the report
        "category": "<slug>" | null,          # null: a report older than the ledger
        "category_group": "Coverage" | ... | null,
        "source": "<Source text>" | null,
        "source_citation": {"file": "...", "line": N} | null,
        "export": "<name>" | null,
        "issue": "..." | null,
        "remediation": "..." | null,
        "remediation_paths": ["..."],         # path tokens as the remediation writes them
        "resolved_paths": ["..."],            # with --source-root only
        "rejected_paths": [{"path", "reason"}], # with --source-root only
        "map_match": {...} | null             # with --provenance-map only
      }
    ],
    "resolved_files": ["..."],                 # with --source-root only
    "warnings": ["..."]
  }

`source_citation` is set only when the whole Source is a `file:line` pair
(`file:line-line`, `file:line:col` and `file#Lline` read the same).

Map match (update-skill gap-driven.md §4's lookup of a gap's export in the
provenance map): for a gap with an `export` (null for one with none),

  {"status": "found" | "ambiguous" | "not-found",
   "entry": {"source_file", "source_line", "export_type"} | null,
   "candidates": [{"source_file", "source_line", "export_type"}, ...]}

`candidates` holds every entries[] row whose export_name is the export, in
the map's order. With a `source_citation`, only the rows whose source_file
is the citation's file count (both compared stripped, with backslashes read
as `/` and no leading `./`), and of several such rows the one whose
source_line is the citation's line. Without one, every candidate counts.
One row left is `found` (its `entry`), several are `ambiguous` (a spot-check
of the wrong one would move another export's line) and none is `not-found`.
`match` prints {"status": "ok", "name", "citation", "map_match"} for a name
a step takes from somewhere other than a gap's `export`, its citation given
as `file:line`.

`remediation_paths` holds, in order and once each, every token of the
Remediation text that names a source file (`.ts`, `.tsx`, `.js`, `.jsx`,
`.mjs`, `.cjs`, `.py`, `.rs`, `.go`, `.java`, `.kt`, `.kts`, `.cs`,
`.swift`, `.php`, `.rb`, `.c`, `.h`, `.cpp` and each --ext, with any
`:line` suffix dropped), every glob (`src/**/*.ts`), every token that ends
in `/`, and every code span that is a single path with a `/` and no file
extension (`` `packages/core/src` ``). A path may hold framework route
names such as `app/(shop)/[slug]/page.tsx`, `[id=integer]` or
`routes/posts.$slug.tsx`: each `(` and `[` must close within its own
folder name, which keeps code such as `Math.floor(x/2)` out. A Markdown
link `[text](target)` is read as its text and its target. URLs, scoped
package names (`@scope/name`), files with other extensions and, outside a
code span, a library name such as `Node.js` are not paths.

With --source-root, each path is also resolved under that folder:
a file is kept, a directory expands to the source files under it (not
under `.git`, `node_modules`, `__pycache__` or another folder starting
with `.`), and a glob expands under the root. Only `*` and `?` make a
path a glob: `**` spans folders, `*` and `?` stay within one name and
skip names that start with `.`, and `[` `]` are plain characters (a route
folder, not a character class). The glob walk follows no link and leaves
out `.git`, `node_modules`, `__pycache__` and folders starting with `.`
unless the glob names them; a folder the glob matches expands like a
directory. `resolved_paths` holds the files, relative to the root with
`/` separators and deduplicated (a link inside the root that points
inside it counts as its target). A path is rejected, with its reason in
`rejected_paths`, when it leaves the root (`outside-root`, also a glob
whose fixed folders do), when a link takes it outside
(`symlink-outside-root`), when it does not exist (`not-found`) or when a
directory or glob holds no file (`no-match`). `resolved_files` is the
union over all gaps, each file once.

`paths` resolves the paths it is given (each relative to the root, a
`:line` suffix dropped) the same way, for a path a step names itself
rather than a remediation text: {"status": "ok", "source_root",
"resolved_paths", "rejected_paths"}.

Translate (update-skill gap-driven.md §1): `translate` turns the gaps
`parse` wrote (--gaps) into the change manifest, written to -o as
{"mode": "gap-driven", "entries": [...]}. Each gap is routed by its
`category` through CHANGE_CATEGORIES (gap-driven.md §1's table), never by
its severity; a category the table does not hold is not routed. Each
entry, in this key order:

  name                      the gap's `export`, else the answered `name`
  gap_id, category          the gap's `id`, its `category` (else the
                            answered one), `severity`
  severity
  source_citation           the gap's, left out when it is null or names a
                            line inside the skill package (`SKILL.md` or a
                            `references/*.md` file, under any folder)
  remediation_paths, resolved_paths, rejected_paths
                            the gap's ([] when parse had no --source-root);
                            a `provenance-completeness` gap with no
                            resolved path takes its resolved_paths from the
                            root check of the source file it cites (its
                            out-of-package citation, else the answered
                            `source_file`) under parse's source root, and
                            adds that check's refusals to its own
                            rejected_paths
  change_category           the table's, or DELETED_EXPORT for a rescope
  remediation               the gap's text, verbatim
  provenance_completeness   true, for a `provenance-completeness` gap only
  rescope                   for a rescope only: {"amendment": {path,
                            action: "excluded", category:
                            "scope-expansion", reason (the remediation),
                            date, workflow: "skf-update-skill"},
                            "exclude": path}
  map_match                 the `match` lookup of `name` with the kept
                            citation (null without a name)

A rescope (rule R1) is a `missing-export` or `missing-type` gap answered
`rescope: true`. Its path is the answered `source_file`, else the file of
its map entry when `map_match` is `found`, else its citation's file.

What it cannot decide it asks for. While any gap needs an answer it writes
nothing and prints {"status": "needs-judgment", "needs_judgment":
[{"gap_id", "title", "category", "issue", "remediation", "needs": [...]}]},
the gap's own text to judge from, each need one of:

  category     a gap with none (a report older than the ledger)
  name         an export-bearing gap with no `export` (with `category`:
               any gap with neither)
  rescope      a `missing-export` or `missing-type` gap whose remediation
               a person or a model wrote: any text but the one gap-ledger.py
               generates for a missing export or type (`Document ... in
               SKILL.md: ...`, `Find the N exports ...`), which names no
               removal; whether it does is rule R1's judgment
  source_file  a rescope whose path is unknown, or a
               `provenance-completeness` gap with no path to scan

--judgments answers them: a JSON object keyed by gap id, each value an
object of `category` (a slug, or null: not routed), `name` (a string, or
null: not routed), `rescope` (true or false; given for any `missing-export`
or `missing-type` gap, it is honoured) and `source_file` (a path relative
to the source root, or null). Other keys are left for gap-records. With
every need answered it writes the manifest and prints {"status":
"written", "output", "gap_count", "not_routed": [{"id", "title",
"category"}], "warnings": [...]}. `warnings` holds parse's warnings as
`test-report: <warning>`, `test-report: not routed: <id> (<category>)` for
each gap not routed, and, with --read-only, `proposed-amendment: excluded
<path> (scope-expansion); not written: --<mode>` for each rescope.

Exit codes:
  0  the gaps (possibly none), the paths or the match were printed; the
     manifest was written, or the answers it needs were printed
  1  the report or ledger is missing or unreadable, or an option value is
     unusable (no --report or --ledger, a --source-root that is not a
     folder, an --ext that is not a file extension, a --provenance-map
     that cannot be read as a JSON object, a --citation that is no
     `file:line`, a --gaps file that is not parse's output, a --judgments
     answer of the wrong type, an -o that cannot be written)
  2  usage error (argparse: a missing or unknown argument, usage on stderr,
     no JSON)

Errors print {"status": "error", "code", "error"} on stdout, with the codes
REPORT_MISSING, LEDGER_MISSING, LEDGER_INVALID and INVALID_INPUT.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SEVERITIES = ("Critical", "High", "Medium", "Low", "Info")
_SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
LEDGER_SCHEMA_VERSION = 1  # gap-ledger.py SCHEMA_VERSION

# The extraction languages (skf-detect-language.py _EXTENSION_TO_LANGUAGE)
# plus C and C++; --ext adds more.
SOURCE_EXTENSIONS = (
    "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "rs", "go", "java",
    "kt", "kts", "cs", "swift", "php", "rb", "c", "h", "cpp",
)
_SOURCE_SUFFIXES = frozenset(f".{ext}" for ext in SOURCE_EXTENSIONS)
_EXT_ARG = re.compile(r"\.?([A-Za-z][A-Za-z0-9]*)")  # an --ext value, whole
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__"})

_RUN_ID_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_RUN_ID_IN_NAME = re.compile(r"(\d{8}T\d{6}Z(?:-[A-Za-z0-9]+)*)\.md$")
_ID_RE = re.compile(r"^GAP-(\d+)$")

# Gap Report markdown.
_GAP_REPORT_H2 = re.compile(r"^##\s+Gap Report\s*$")
_SECTION_END = re.compile(r"^#{1,2}\s")
_HEADING = re.compile(r"^#{1,6}\s")
_GAP_HEADING = re.compile(
    r"^#{2,6}\s+(?:\*\*)?(GAP-\d+)(?:\*\*)?\s*(?:[:.\u2013\u2014-]\s*)?(.*?)\s*$"
)
_FIELD = re.compile(
    r"^\s*(?:[-*]\s+)?\*\*(severity|category|source|export|issue|remediation)\s*(?::\*\*|\*\*\s*:)\s*(.*)$",
    re.IGNORECASE,
)
_MULTILINE_FIELDS = frozenset({"issue", "remediation"})
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_CATEGORY_WITH_GROUP = re.compile(r"^([A-Za-z][A-Za-z &/-]*?)\s*\(\s*`?([a-z][a-z0-9-]*)`?\s*\)$")
_CATEGORY_SLUG = re.compile(r"^[a-z][a-z0-9-]*$")

# Paths in remediation text. ( ) [ ] $ = + @ appear in framework route
# names: app/(shop)/[slug]/page.tsx, [id=integer], posts.$slug.tsx, @modal.
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_LINE_SUFFIX = re.compile(r"(?::\d+(?:[-:]\d+)*|#L\d+(?:-L?\d+)?)$")
_PATH_TOKEN = re.compile(r"^[\w./*?\[\]()$=@+~-]+$")
_GLOB_CHARS = re.compile(r"[*?]")
_WORD_BREAK = re.compile(r"\s+|\]\(")  # `](` joins a Markdown link's text to its target
_CLOSER = {"(": ")", "[": "]"}
_EXTENSION = re.compile(r"\.([A-Za-z][A-Za-z0-9]*)$")
_CITATION = re.compile(r"^(?P<file>[^\s`]+?)(?::(?P<line>\d+)(?:[-:]\d+)?|#L(?P<hline>\d+)(?:-L?\d+)?)$")
# Outside a code span, a bare `Name.js` with no folder is a library name
# (Node.js, Vue.js, D3.js), not a file.
_PRODUCT_NAME = re.compile(r"^(?:[A-Z][\w-]*|node|vue|next|nuxt|express|react|angular|ember|d3|three|chart|p5)\.js$")


class ParseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# Small readers
# --------------------------------------------------------------------------


def read_frontmatter(text: str) -> dict[str, str]:
    """Top-level scalar keys of a `---` frontmatter block, quotes removed."""
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if m:
            value = m.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            out[m.group(1)] = value
    return {}


def strip_frontmatter(text: str) -> str:
    lines = text.lstrip("\ufeff").splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return "\n".join(lines)


def normalize_severity(value: object) -> str | None:
    """The first severity word in a value, in title case.

    >>> normalize_severity("**critical** (blocking)"), normalize_severity("n/a")
    ('Critical', None)
    """
    if not isinstance(value, str):
        return None
    m = re.search(r"\b(critical|high|medium|low|info)\b", value, re.IGNORECASE)
    return m.group(1).capitalize() if m else None


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        value = value.strip("`").strip()
    return value


def source_citation(source: object) -> dict | None:
    """{file, line} when the whole Source is a file:line pair.

    >>> source_citation("`src/utils.ts:42`")
    {'file': 'src/utils.ts', 'line': 42}
    >>> source_citation("src/a.py#L10-L12")
    {'file': 'src/a.py', 'line': 10}
    >>> source_citation("@storybook/addon-docs control primitives") is None
    True
    """
    if not isinstance(source, str):
        return None
    text = _unquote(source)
    if "://" in text:
        return None
    m = _CITATION.match(text)
    if not m:
        return None
    return {"file": m.group("file"), "line": int(m.group("line") or m.group("hline"))}


def parse_category(value: str | None) -> tuple[str | None, str | None]:
    """(category slug, group) from a Category line.

    >>> parse_category("Coverage (missing-export)")
    ('missing-export', 'Coverage')
    >>> parse_category("Coherence")
    (None, 'Coherence')
    >>> parse_category("broken-reference")
    ('broken-reference', None)
    """
    if not value:
        return None, None
    text = _unquote(value)
    m = _CATEGORY_WITH_GROUP.match(text)
    if m:
        return m.group(2), m.group(1).strip()
    if _CATEGORY_SLUG.match(text):
        return text, None
    return None, text or None


# --------------------------------------------------------------------------
# Paths in remediation text
# --------------------------------------------------------------------------


def _brackets_close_per_name(token: str) -> bool:
    """True when each `/`-separated name closes the ( and [ it opens, and `=`
    sits only inside [ ]: route names such as `(shop)`, `[[...slug]]` or
    `[id=integer]`, not code such as `Math.floor(x/2)` or `key=value`.

    >>> [_brackets_close_per_name(t) for t in ("app/(shop)/[id=int]/page.tsx", "Math.floor(x/2)", "a=b/c.ts")]
    [True, False, False]
    """
    for name in token.split("/"):
        expected: list[str] = []
        for ch in name:
            if ch in _CLOSER:
                expected.append(_CLOSER[ch])
            elif ch in ")]":
                if not expected or expected.pop() != ch:
                    return False
            elif ch == "=" and "]" not in expected:
                return False
        if expected:
            return False
    return True


def _wraps(word: str, opener: str) -> bool:
    """True when the bracket that opens `word` is the one that ends it: `(src/a.ts)`."""
    if not word.startswith(opener) or not word.endswith(_CLOSER[opener]):
        return False
    depth = 0
    for index, ch in enumerate(word):
        if ch == opener:
            depth += 1
        elif ch == _CLOSER[opener]:
            depth -= 1
            if depth == 0:
                return index == len(word) - 1
    return False


def _trim_word(word: str) -> str:
    """A word of prose without the punctuation around it.

    A bracket the word closes itself stays, so a route folder keeps it:
    `(shop)/page.tsx` keeps its `(`, `(see` and `src/a.ts),` lose theirs.

    >>> [_trim_word(w) for w in ("(src/a.ts),", "app/(shop)/page.tsx).", "[slug]/page.tsx", "(see", "a.ts?")]
    ['src/a.ts', 'app/(shop)/page.tsx', '[slug]/page.tsx', 'see', 'a.ts']
    """
    while True:
        before = word
        word = word.lstrip("{<'\"").rstrip("}>'\",;!.:")
        if word.endswith("?") and not _GLOB_CHARS.search(word[:-1]):
            word = word[:-1]
        for opener, closer in _CLOSER.items():
            if _wraps(word, opener):
                word = word[1:-1]
            if word.startswith(opener) and word.count(opener) > word.count(closer):
                word = word[1:]
            if word.endswith(closer) and word.count(closer) > word.count(opener):
                word = word[:-1]
        if word == before:
            return word


def _path_kind(token: str, in_code: bool, suffixes: frozenset[str]) -> str | None:
    """'file', 'dir' or 'glob' when a token names a source path, else None."""
    token = _LINE_SUFFIX.sub("", token)
    if not token or "://" in token or not _PATH_TOKEN.match(token):
        return None
    if not re.search(r"[A-Za-z*]", token) or not _brackets_close_per_name(token):
        return None
    ext = _EXTENSION.search(token)
    if token.startswith("@") and not (ext and f".{ext.group(1)}" in suffixes):
        return None
    if _GLOB_CHARS.search(token):
        return "glob" if "/" in token or "*" in token else None
    if token.endswith("/"):
        return "dir"
    if ext:
        if f".{ext.group(1)}" not in suffixes:
            return None
        if not in_code and "/" not in token and _PRODUCT_NAME.match(token):
            return None
        return "file"
    if in_code and "/" in token and token.strip("./"):
        return "dir"
    return None


def remediation_paths(text: str | None, suffixes: frozenset[str] = _SOURCE_SUFFIXES) -> list[str]:
    """Path tokens of a remediation text, in order, each once.

    >>> remediation_paths("Update `SKILL.md` line 78 to match source at `src/utils.ts:42`.")
    ['src/utils.ts']
    >>> remediation_paths("Scan packages/core/src/ and `src/**/*.tsx`; see references/api.md and/or https://x.io/a.ts")
    ['packages/core/src/', 'src/**/*.tsx']
    >>> remediation_paths("Re-extract from `packages/hooks` (not `@scope/pkg`), as Node.js resolves lib/index.js.")
    ['packages/hooks', 'lib/index.js']
    >>> remediation_paths("Read app/(shop)/[slug]/page.tsx, `routes/posts.$slug.tsx` (see [Store](src/Store.kt)).")
    ['app/(shop)/[slug]/page.tsx', 'routes/posts.$slug.tsx', 'src/Store.kt']
    """
    if not text:
        return []
    found: list[str] = []

    def add(token: str, in_code: bool) -> None:
        if _path_kind(token, in_code, suffixes):
            path = _LINE_SUFFIX.sub("", token)
            if path not in found:
                found.append(path)

    def add_words(bare: str) -> None:
        for word in _WORD_BREAK.split(bare):
            word = _trim_word(word)
            if word:
                add(word, False)

    position = 0
    for m in _CODE_SPAN.finditer(text):
        add_words(text[position:m.start()])
        span = m.group(2).strip()
        if span and not any(c.isspace() for c in span):
            add(span, True)
        position = m.end()
    add_words(text[position:])
    return found


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _source_files_under(folder: Path, suffixes: frozenset[str]) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if Path(name).suffix in suffixes:
                out.append(Path(dirpath) / name)
    return out


def _glob_regex(pattern: str, base: str = "") -> re.Pattern[str]:
    """A glob over `/` paths as a regex, below the folder `base` (taken as written).

    `**` as a whole name spans any number of folders; `*` and `?` stay within
    one name and, as in glob, skip a name that starts with `.`; every other
    character is literal, `[` and `]` included, so `app/[slug]/*.tsx` names
    the route folder instead of a character class.

    >>> [bool(_glob_regex("**/*.ts", "src").fullmatch(p)) for p in ("src/a.ts", "src/x/y/a.ts", "src/.a.ts", "lib/a.ts")]
    [True, True, False, False]
    >>> bool(_glob_regex("app/[slug]/*.tsx").fullmatch("app/[slug]/page.tsx"))
    True
    """
    name = r"(?!\.)[^/]+"
    parts: list[str] = [re.escape(f"{base}/")] if base else []
    names = pattern.split("/")
    for index, part in enumerate(names):
        last = index == len(names) - 1
        if part == "**":
            parts.append(f"{name}(?:/{name})*" if last else f"(?:{name}/)*")
            continue
        regex = r"(?!\.)" if part[:1] in ("*", "?") else ""
        for ch in part:
            regex += "[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch)
        parts.append(regex if last else regex + "/")
    return re.compile("".join(parts), re.IGNORECASE if os.name == "nt" else 0)


def _glob_walk(start: Path, root: Path, pattern: str, dirs_only: bool) -> list[str]:
    """Paths under `start` that match `pattern`, relative to `root`, sorted.

    A walk that follows no link (a link in a folder is listed, never entered)
    and never enters `.git`, `node_modules`, `__pycache__` or a folder
    starting with `.`, unless the pattern names it. Without `**` it goes no
    deeper than the pattern has names below `start`.
    """
    base = start.relative_to(root).as_posix()
    regex = _glob_regex(pattern, "" if base == "." else base)
    names = pattern.split("/")
    named = {n for n in names if not _GLOB_CHARS.search(n)}
    depth_limit = None if "**" in names else len(names)
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames if (d not in SKIP_DIRS and not d.startswith(".")) or d in named
        )
        for entry in (dirnames if dirs_only else dirnames + filenames):
            rel = (here / entry).relative_to(root).as_posix()
            if regex.fullmatch(rel):
                found.append(rel)
        if depth_limit is not None and len(here.relative_to(start).parts) + 1 >= depth_limit:
            dirnames[:] = []
    return sorted(found)


def resolve_paths(
    tokens: list[str], root: Path, suffixes: frozenset[str] = _SOURCE_SUFFIXES
) -> tuple[list[str], list[dict]]:
    """Resolve path tokens under a real root: (files relative to it, rejected)."""
    resolved: list[str] = []
    rejected: list[dict] = []
    refusals = 0  # every rejection, counted before the dedupe

    def keep(real: Path) -> None:
        rel = real.relative_to(root).as_posix()
        if rel not in resolved:
            resolved.append(rel)

    def reject(shown: str, reason: str) -> None:
        nonlocal refusals
        refusals += 1
        entry = {"path": shown, "reason": reason}
        if entry not in rejected:
            rejected.append(entry)

    def check(lexical_text: str, shown: str) -> Path | None:
        lexical = Path(os.path.normpath(os.path.join(root, lexical_text)))
        if not _inside(lexical, root):
            reject(shown, "outside-root")
            return None
        real = Path(os.path.realpath(lexical))
        if not _inside(real, root):
            reject(shown, "symlink-outside-root")
            return None
        return real

    def take(real: Path) -> int:
        """Keep a file, or the source files under a folder; return how many."""
        if real.is_file():
            keep(real)
            return 1
        if real.is_dir():
            kept = 0
            for file in _source_files_under(real, suffixes):
                inner = check(str(file), file.relative_to(root).as_posix())
                if inner is not None and inner.is_file():
                    keep(inner)
                    kept += 1
            return kept
        return 0

    def take_glob(token: str) -> int:
        """Keep what a glob matches under the root; return how many files."""
        names = token.rstrip("/").split("/")
        first = next(i for i, name in enumerate(names) if _GLOB_CHARS.search(name))
        # The folders before the first wildcard are fixed: a glob they take
        # out of the root is refused whole, and nothing outside is listed.
        start = check("/".join(names[:first]) or ".", token)
        if start is None or not start.is_dir():
            return 0
        kept = 0
        for rel in _glob_walk(start, root, "/".join(names[first:]), token.endswith("/")):
            real = check(rel, rel)
            if real is not None:
                kept += take(real)
        return kept

    for token in tokens:
        refusals_before = refusals
        if _GLOB_CHARS.search(token):
            kept = take_glob(token)
        else:
            real = check(token, token)
            if real is None:
                continue
            if not real.exists():
                reject(token, "not-found")
                continue
            kept = take(real)
        # A path whose every file was rejected already says why.
        if kept == 0 and refusals == refusals_before:
            reject(token, "no-match")
    return resolved, rejected


# --------------------------------------------------------------------------
# Gap sources
# --------------------------------------------------------------------------


def _gap(
    *,
    gid: str,
    title: str,
    severity: str | None,
    category: str | None,
    group: str | None,
    source: str | None,
    export: str | None,
    issue: str | None,
    remediation: str | None,
) -> dict:
    """One gap; parse_gaps() adds its `remediation_paths`."""
    return {
        "id": gid,
        "title": title,
        "severity": severity,
        "category": category,
        "category_group": group,
        "source": source,
        "source_citation": source_citation(source),
        "export": export,
        "issue": issue,
        "remediation": remediation,
    }


def gaps_from_ledger(path: Path) -> list[dict]:
    """The gaps of a ledger file. Raises ParseError."""
    if not path.is_file():
        raise ParseError("LEDGER_MISSING", f"no ledger at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("LEDGER_INVALID", f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("LEDGER_INVALID", f"{path} is not a JSON object")
    version = data.get("schema_version")
    if version is not None and version != LEDGER_SCHEMA_VERSION:
        raise ParseError(
            "LEDGER_INVALID",
            f"{path} has schema_version {version!r}; this helper reads version {LEDGER_SCHEMA_VERSION}",
        )
    records = data.get("records")
    if not isinstance(records, list):
        raise ParseError("LEDGER_INVALID", f"{path} has no records list")
    gaps: list[dict] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ParseError("LEDGER_INVALID", f"record {index} of {path} has no id")
        severity = record.get("severity")
        if severity not in SEVERITIES:
            raise ParseError("LEDGER_INVALID", f"{record['id']} has an unknown severity {severity!r}")

        def text(key: str) -> str | None:
            value = record.get(key)
            return value if isinstance(value, str) and value else None

        gaps.append(
            _gap(
                gid=record["id"],
                title=text("title") or "",
                severity=severity,
                category=text("category"),
                group=text("group"),
                source=text("source"),
                export=text("export"),
                issue=text("issue"),
                remediation=text("remediation"),
            )
        )
    return gaps


def gaps_from_markdown(text: str) -> tuple[list[dict], list[str]]:
    """The GAP entries of every `## Gap Report` section. Returns (gaps, warnings)."""
    lines = strip_frontmatter(text).splitlines()
    gaps: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    sections = 0
    in_section = in_fence = False
    current: dict | None = None
    field: str | None = None

    def close() -> None:
        nonlocal current, field
        if current is not None:
            gid = current["id"]
            if gid in seen:
                warnings.append(f"{gid} appears more than once; the first entry is kept")
            else:
                seen.add(gid)
                values = {k: "\n".join(v).strip() or None for k, v in current["fields"].items()}
                category, group = parse_category(values.get("category"))
                severity = normalize_severity(values.get("severity"))
                if severity is None:
                    warnings.append(f"{gid} has no readable severity")
                source = values.get("source")
                gaps.append(
                    _gap(
                        gid=gid,
                        title=current["title"],
                        severity=severity,
                        category=category,
                        group=group,
                        source=_unquote(source) if source else None,
                        export=_unquote(values["export"]) if values.get("export") else None,
                        issue=values.get("issue"),
                        remediation=values.get("remediation"),
                    )
                )
        current, field = None, None

    for line in lines:
        if in_fence:
            if _FENCE.match(line):
                in_fence = False
            if current is not None and field in _MULTILINE_FIELDS:
                current["fields"][field].append(line)
            continue
        if _FENCE.match(line):
            in_fence = True
            if current is not None and field in _MULTILINE_FIELDS:
                current["fields"][field].append(line)
            continue
        if _SECTION_END.match(line):
            close()
            in_section = bool(_GAP_REPORT_H2.match(line))
            sections += in_section
            continue
        if not in_section:
            continue
        if _HEADING.match(line):
            close()
            m = _GAP_HEADING.match(line)
            if m:
                current = {"id": m.group(1), "title": m.group(2).strip().strip("*").strip(), "fields": {}}
            continue
        if current is None:
            continue
        m = _FIELD.match(line)
        if m:
            field = m.group(1).lower()
            current["fields"][field] = [m.group(2)]
            continue
        if _RULE.match(line):
            field = None
            continue
        if field in _MULTILINE_FIELDS:
            current["fields"][field].append(line)
    close()
    if sections == 0:
        warnings.append("the report has no ## Gap Report section")
    elif not gaps:
        warnings.append("the Gap Report section holds no GAP entries")
    return gaps, warnings


def _gap_order(gap: dict) -> tuple[int, int]:
    m = _ID_RE.match(gap["id"])
    return (_SEVERITY_RANK.get(gap["severity"], len(SEVERITIES)), int(m.group(1)) if m else 0)


def sibling_ledger(report: Path, text: str) -> Path | None:
    """`test-findings-{run_id}.json` beside the report, when the run id is known."""
    run_id = read_frontmatter(text).get("runId") or ""
    if not run_id:
        m = _RUN_ID_IN_NAME.search(report.name)
        run_id = m.group(1) if m else ""
    if not _RUN_ID_SAFE.match(run_id):
        return None
    return report.parent / f"test-findings-{run_id}.json"


def _norm_file(path: object) -> str | None:
    """A file as the lookup compares it: stripped, backslashes read as `/`, no leading `./`."""
    if not isinstance(path, str) or not path.strip():
        return None
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _line_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def map_match(entries: list, name: str, citation: dict | None) -> dict:
    """The provenance map entry an export names, keyed on its citation (see "Map match" in the module docstring)."""
    def view(entry: dict) -> dict:
        return {key: entry.get(key) for key in ("source_file", "source_line", "export_type")}

    named = [e for e in entries if isinstance(e, dict) and isinstance(e.get("export_name"), str)
             and e["export_name"].strip() == name.strip()]
    left = named
    if citation:
        cited = _norm_file(citation.get("file"))
        left = [e for e in named if _norm_file(e.get("source_file")) == cited]
        line = _line_number(citation.get("line"))
        if len(left) > 1 and line is not None:
            left = [e for e in left if _line_number(e.get("source_line")) == line] or left
    status = "found" if len(left) == 1 else "ambiguous" if left else "not-found"
    return {"status": status, "entry": view(left[0]) if status == "found" else None,
            "candidates": [view(e) for e in named]}


def parse_gaps(
    report: Path | None,
    ledger: Path | None,
    source_root: Path | None,
    extensions: tuple[str, ...] | list[str] = (),
    map_entries: list | None = None,
) -> dict:
    """Read the gaps and build the output object. Raises ParseError.

    `extensions` (without the dot) add to SOURCE_EXTENSIONS. With
    `map_entries` (a provenance map's entries[]), each gap gets its
    `map_match`, null for a gap with no `export`.
    """
    suffixes = _SOURCE_SUFFIXES | {f".{ext}" for ext in extensions}
    warnings: list[str] = []
    text = None
    if report is not None:
        if not report.is_file():
            raise ParseError("REPORT_MISSING", f"no test report at {report}")
        try:
            text = report.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ParseError("REPORT_MISSING", f"cannot read {report}: {exc}") from exc
        if ledger is None:
            candidate = sibling_ledger(report, text)
            if candidate is not None and candidate.is_file():
                ledger = candidate
    if ledger is not None:
        gaps = gaps_from_ledger(ledger)
        read_from = "ledger"
    else:
        gaps, warnings = gaps_from_markdown(text or "")
        read_from = "gap-report"
    gaps.sort(key=_gap_order)
    counts = {s: 0 for s in SEVERITIES}
    for gap in gaps:
        gap["remediation_paths"] = remediation_paths(gap["remediation"], suffixes)
        if gap["severity"] in counts:
            counts[gap["severity"]] += 1
        if map_entries is not None:
            gap["map_match"] = map_match(map_entries, gap["export"], gap["source_citation"]) \
                if gap["export"] and gap["export"].strip() else None
    out = {
        "status": "ok",
        "read_from": read_from,
        "report_path": str(report) if report is not None else None,
        "ledger_path": str(ledger) if ledger is not None else None,
        "source_root": None,
        "gap_count": len(gaps),
        "counts": counts,
        "gaps": gaps,
        "warnings": warnings,
    }
    if source_root is not None:
        root = Path(os.path.realpath(source_root))
        union: list[str] = []
        for gap in gaps:
            resolved, rejected = resolve_paths(gap["remediation_paths"], root, suffixes)
            gap["resolved_paths"] = resolved
            gap["rejected_paths"] = rejected
            union.extend(p for p in resolved if p not in union)
        out["source_root"] = str(root)
        out["resolved_files"] = union
    return out


# --------------------------------------------------------------------------
# Translate (update-skill gap-driven.md §1)
# --------------------------------------------------------------------------

# gap-driven.md §1's table: each ledger category the repair routes, and the
# change category it takes. Any other category is not routed.
CHANGE_CATEGORIES = {
    "missing-export": "NEW_EXPORT",
    "missing-type": "NEW_EXPORT",
    "provenance-completeness": "NEW_EXPORT",
    "signature-mismatch": "MODIFIED_EXPORT",
    "fabricated-signature": "MODIFIED_EXPORT",
    "stale-documentation": "MODIFIED_EXPORT",
    "provenance-line": "MOVED_EXPORT",
    "split-body-mismatch": "STRUCTURAL_FIX",
    "structural": "STRUCTURAL_FIX",
    "broken-reference": "STRUCTURAL_FIX",
    "inaccurate-reference": "STRUCTURAL_FIX",
    "reference-escape": "STRUCTURAL_FIX",
    "integration-pattern": "STRUCTURAL_FIX",
    "migration-section": "STRUCTURAL_FIX",
    "scripts-assets": "STRUCTURAL_FIX",
    "metadata-drift": "metadata update",
    "metadata": "metadata update",
}
EXPORT_CATEGORIES = ("NEW_EXPORT", "MODIFIED_EXPORT", "MOVED_EXPORT", "DELETED_EXPORT")
RESCOPE_CATEGORIES = ("missing-export", "missing-type")  # rule R1
COMPLETENESS = "provenance-completeness"  # rule R3
READ_ONLY_MODES = ("dry-run", "detect-only")
# The remediation gap-ledger.py generates for a missing export or type (_missing_export, and the count gap of
# the scalar and stack branches). No person wrote it, so it names no removal (rule R1); any other text may.
_LEDGER_REMEDIATION = re.compile(
    r"Document (?:the type )?`[^`\n]+` in SKILL\.md: (?:read its definition at `[^`\n]+`"
    r"|find its definition in the source \(`[^`\n]+` lists it\)) and "
    r"(?:add its signature, its purpose and a usage example|list its fields or members)\."
    r"|Find the \d+ exports the denominator counts that SKILL\.md and references/ do not name "
    r"\(`[^`\n]+` lists the exports\) and document each with its signature\."
)
# A citation of generated markdown: the skill's SKILL.md or a references/*.md file.
_PACKAGE_FILE = re.compile(r"(?:^|/)(?:SKILL\.md|references/[^/]+\.md)$")
# The answers translate reads, with the JSON types each takes.
_ANSWER_TYPES = {"category": (str, type(None)), "name": (str, type(None)), "rescope": (bool,),
                 "source_file": (str, type(None))}
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0


def in_skill_package(citation: dict | None) -> bool:
    """True when a citation names a line of generated markdown, not source.

    >>> [in_skill_package({"file": f, "line": 1}) for f in ("SKILL.md", "{skill_package}/references/api.md", "src/a.ts")]
    [True, True, False]
    """
    path = _norm_file(citation.get("file")) if isinstance(citation, dict) else None
    return bool(path and _PACKAGE_FILE.search(path))


def written_remediation(text: object) -> bool:
    """True when a remediation is text a person or a model wrote, not the text gap-ledger.py generates for a
    missing export or type: only such text can name the removal rule R1 asks about.

    >>> [written_remediation(t) for t in ("Document `x` in SKILL.md: read its definition at `src/a.ts` and add "
    ...     "its signature, its purpose and a usage example.", "x is internal: drop it from the surface.", None)]
    [False, True, False]
    """
    return isinstance(text, str) and bool(text.strip()) and not _LEDGER_REMEDIATION.fullmatch(text.strip())


def load_judgments(path: Path) -> dict:
    """The answers of a --judgments file, keyed by gap id. Raises ParseError (INVALID_INPUT)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("INVALID_INPUT", f"cannot read --judgments {path}: {exc}") from exc
    if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
        raise ParseError("INVALID_INPUT", f"--judgments {path} must map each gap id to an object of answers")
    for gid, answers in data.items():
        for key, types in _ANSWER_TYPES.items():
            if key in answers and not isinstance(answers[key], types):
                raise ParseError("INVALID_INPUT", f"--judgments {path}: {gid}'s `{key}` has the wrong type")
    return data


def _answer_text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _answer_path(value: object) -> str | None:
    text = _norm_file(value)
    return text.rstrip("/") or None if text else None


def translate_gaps(parsed: dict, map_entries: list, judgments: dict, *, read_only: str | None = None,
                   today: str = "") -> tuple[dict | None, dict]:
    """(the change manifest, or None while a gap needs an answer; the summary). See "Translate" in the module
    docstring."""
    root_text = parsed.get("source_root")
    root = Path(root_text) if isinstance(root_text, str) and Path(root_text).is_dir() else None
    suffixes = _SOURCE_SUFFIXES | {f".{ext}" for ext in map_extensions(map_entries)}
    warnings = [f"test-report: {w}" for w in parsed.get("warnings") or [] if isinstance(w, str)]
    needs: list[dict] = []
    entries: list[dict] = []
    not_routed: list[dict] = []

    def skip(gap: dict, category: str | None) -> None:
        not_routed.append({"id": gap["id"], "title": gap.get("title"), "category": category})
        warnings.append(f"test-report: not routed: {gap['id']} ({category or 'no category'})")

    def ask(gap: dict, category: str | None, want: list[str]) -> None:
        needs.append({"gap_id": gap["id"], "title": gap.get("title"), "category": category,
                      "issue": gap.get("issue"), "remediation": gap.get("remediation"), "needs": want})

    for gap in parsed["gaps"]:
        answers = judgments.get(gap["id"]) or {}
        want: list[str] = []
        export = _answer_text(gap.get("export"))
        category = gap.get("category") or None
        if category is None and "category" in answers:
            category = _answer_text(answers["category"])
        elif category is None:
            want.append("category")
            if export is None and "name" not in answers:
                want.append("name")
            ask(gap, None, want)
            continue
        change = CHANGE_CATEGORIES.get(category or "")
        if change is None:
            skip(gap, category)
            continue
        name = export or _answer_text(answers.get("name"))
        if change in EXPORT_CATEGORIES and name is None:
            if "name" in answers:  # answered null: no export to repair
                skip(gap, category)
            else:
                ask(gap, category, ["name"])
            continue
        citation = gap.get("source_citation")
        if in_skill_package(citation):
            citation = None
        match = map_match(map_entries, name, citation) if name else None
        rescope = False
        if category in RESCOPE_CATEGORIES:
            if "rescope" in answers:
                rescope = answers["rescope"]
            elif written_remediation(gap.get("remediation")):
                want.append("rescope")
        exclude = None
        if rescope:
            exclude = _answer_path(answers.get("source_file"))
            if exclude is None and match and match["status"] == "found":
                exclude = _answer_path(match["entry"]["source_file"])
            if exclude is None and citation:
                exclude = _answer_path(citation["file"])
            if exclude is None and "source_file" not in answers:
                want.append("source_file")
            elif exclude is None:
                warnings.append(f"test-report: {gap['id']}: no source file to exclude, so it is documented, not "
                                f"rescoped")
                rescope = False
        resolved = list(gap.get("resolved_paths") or [])
        rejected = list(gap.get("rejected_paths") or [])
        if category == COMPLETENESS and not resolved and root is not None:
            cited = _answer_path(citation["file"]) if citation else None
            if cited is None and "source_file" in answers:
                cited = _answer_path(answers["source_file"])
            elif cited is None:
                want.append("source_file")
            if cited is not None:
                resolved, refused = resolve_paths([_LINE_SUFFIX.sub("", cited)], root, suffixes)
                rejected += refused
        if want:
            ask(gap, category, want)
            continue
        entry = {"name": name, "gap_id": gap["id"], "category": category, "severity": gap.get("severity")}
        if citation:
            entry["source_citation"] = citation
        entry["remediation_paths"] = list(gap.get("remediation_paths") or [])
        entry["resolved_paths"] = resolved
        entry["rejected_paths"] = rejected
        entry["change_category"] = "DELETED_EXPORT" if rescope else change
        entry["remediation"] = gap.get("remediation")
        if category == COMPLETENESS:
            entry["provenance_completeness"] = True
        if rescope:
            entry["rescope"] = {
                "amendment": {"path": exclude, "action": "excluded", "category": "scope-expansion",
                              "reason": gap.get("remediation") or gap.get("title") or "", "date": today,
                              "workflow": "skf-update-skill"},
                "exclude": exclude,
            }
            if read_only:
                warnings.append(f"proposed-amendment: excluded {exclude} (scope-expansion); not written: "
                                f"--{read_only}")
        entry["map_match"] = match
        entries.append(entry)
    if needs:
        return None, {"status": "needs-judgment", "needs_judgment": needs}
    return {"mode": "gap-driven", "entries": entries}, {
        "status": "written", "gap_count": len(entries), "not_routed": not_routed, "warnings": warnings}


def write_json_atomic(path: Path, value) -> None:
    """Write `value` as indented JSON through a temporary file beside `path` and one rename (retried on Windows,
    where a scanner may hold the target open for a moment)."""
    tmp = path.with_name(f".{path.name}.skf-{os.getpid()}-tmp")
    try:
        tmp.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if not _IS_WINDOWS or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def map_entries_of(path: Path) -> list:
    """A provenance map's entries[] ([] when it has none). Raises ParseError (INVALID_INPUT)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("INVALID_INPUT", f"cannot read --provenance-map {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("INVALID_INPUT", f"--provenance-map {path} is not a JSON object")
    return data.get("entries") if isinstance(data.get("entries"), list) else []


def map_extensions(entries: list) -> list[str]:
    """The extension (no dot) of each file a provenance map's entries[]
    source_file values name."""
    found: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("source_file"), str):
            m = _EXTENSION.search(entry["source_file"].strip())
            if m and m.group(1) not in found:
                found.append(m.group(1))
    return found


def _options(args: argparse.Namespace) -> tuple[Path | None, list[str], list | None]:
    """(--source-root, the extensions --ext and --provenance-map add, the
    map's entries or None). Raises ParseError (INVALID_INPUT)."""
    root = None
    if args.source_root is not None:
        root = Path(args.source_root)
        if not root.is_dir():
            raise ParseError("INVALID_INPUT", f"--source-root is not a folder: {root}")
    extensions: list[str] = []
    for value in args.ext:
        m = _EXT_ARG.fullmatch(value)
        if not m:
            raise ParseError("INVALID_INPUT", f"--ext takes a file extension such as kt or .vue, got {value!r}")
        extensions.append(m.group(1))
    entries = None
    if args.provenance_map is not None:
        entries = map_entries_of(Path(args.provenance_map))
        extensions += map_extensions(entries)
    return root, extensions, entries


def _cmd_paths(args: argparse.Namespace) -> int:
    try:
        root, extensions, _ = _options(args)
    except ParseError as exc:
        _emit({"status": "error", "code": exc.code, "error": str(exc)})
        return 1
    real = Path(os.path.realpath(root))
    suffixes = _SOURCE_SUFFIXES | {f".{ext}" for ext in extensions}
    tokens = [_LINE_SUFFIX.sub("", path.strip()) for path in args.path if path.strip()]
    resolved, rejected = resolve_paths(tokens, real, suffixes)
    _emit({"status": "ok", "source_root": str(real), "resolved_paths": resolved, "rejected_paths": rejected})
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    if args.report is None and args.ledger is None:
        _emit({"status": "error", "code": "INVALID_INPUT", "error": "give --report, --ledger or both"})
        return 1
    try:
        root, extensions, entries = _options(args)
    except ParseError as exc:
        _emit({"status": "error", "code": exc.code, "error": str(exc)})
        return 1
    try:
        out = parse_gaps(
            Path(args.report) if args.report else None,
            Path(args.ledger) if args.ledger else None,
            root,
            extensions,
            entries,
        )
    except ParseError as exc:
        _emit({"status": "error", "code": exc.code, "error": str(exc)})
        return 1
    _emit(out)
    return 0


def _cmd_match(args: argparse.Namespace) -> int:
    citation = source_citation(args.citation) if args.citation is not None else None
    try:
        if args.citation is not None and citation is None:
            raise ParseError("INVALID_INPUT", f"--citation takes a file:line pair, got {args.citation!r}")
        if not args.name.strip():
            raise ParseError("INVALID_INPUT", "--name is empty")
        entries = map_entries_of(Path(args.provenance_map))
    except ParseError as exc:
        _emit({"status": "error", "code": exc.code, "error": str(exc)})
        return 1
    _emit({"status": "ok", "name": args.name, "citation": citation,
           "map_match": map_match(entries, args.name, citation)})
    return 0


def _parsed_gaps(path: Path) -> dict:
    """parse's output in a --gaps file. Raises ParseError (INVALID_INPUT)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("INVALID_INPUT", f"cannot read --gaps {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("status") != "ok" or not isinstance(data.get("gaps"), list) \
            or not all(isinstance(g, dict) and isinstance(g.get("id"), str) for g in data["gaps"]):
        raise ParseError("INVALID_INPUT", f"--gaps {path} is not the output of a parse that succeeded")
    return data


def _cmd_translate(args: argparse.Namespace) -> int:
    try:
        if args.date is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise ParseError("INVALID_INPUT", f"--date takes YYYY-MM-DD, got {args.date!r}")
        parsed = _parsed_gaps(Path(args.gaps))
        entries = map_entries_of(Path(args.provenance_map))
        judgments = load_judgments(Path(args.judgments)) if args.judgments else {}
        manifest, summary = translate_gaps(
            parsed, entries, judgments, read_only=args.read_only,
            today=args.date or datetime.now(timezone.utc).date().isoformat())
        if manifest is not None:
            try:
                write_json_atomic(Path(args.output), manifest)
            except OSError as exc:
                raise ParseError("INVALID_INPUT", f"cannot write {args.output}: {exc}") from exc
            summary = {"status": summary["status"], "output": args.output,
                       **{k: v for k, v in summary.items() if k != "status"}}
    except ParseError as exc:
        _emit({"status": "error", "code": exc.code, "error": str(exc)})
        return 1
    _emit(summary)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-parse-gaps",
        description="Read a test report's gaps (ledger first, Gap Report otherwise) as JSON.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("parse", help="print the gaps as JSON")
    p.add_argument("--report", help="the test report (test-report-{skill}-{run_id}.md)")
    p.add_argument("--ledger", help="the gap ledger, when not the one beside the report")
    p.add_argument("--source-root", help="resolve remediation paths under this folder")
    p.set_defaults(func=_cmd_parse)

    q = sub.add_parser("paths", help="resolve given paths under the source root")
    q.add_argument("--source-root", required=True, help="resolve the paths under this folder")
    q.add_argument("path", nargs="+", help="a path relative to the source root (a :line suffix is dropped)")
    q.set_defaults(func=_cmd_paths)

    m = sub.add_parser("match", help="find an export in the provenance map, as a gap's map_match does")
    m.add_argument("--provenance-map", required=True, help="the provenance map to look the export up in")
    m.add_argument("--name", required=True, help="the export's name")
    m.add_argument("--citation", help="the export's source citation, file:line")
    m.set_defaults(func=_cmd_match)

    t = sub.add_parser("translate", help="write update-skill's gap-driven change manifest from parse's gaps")
    t.add_argument("--gaps", required=True, help="the output of parse")
    t.add_argument("--provenance-map", required=True, help="the provenance map each entry's map_match reads")
    t.add_argument("--judgments", help="the answers to its needs_judgment[], keyed by gap id")
    t.add_argument("--read-only", choices=READ_ONLY_MODES,
                   help="the read-only flag of the run: each rescope is a proposed amendment")
    t.add_argument("--date", help="the date of a rescope's amendment, YYYY-MM-DD (default: today, UTC)")
    t.add_argument("-o", "--output", required=True, help="where to write the change manifest")
    t.set_defaults(func=_cmd_translate)

    for parser_ in (p, q):
        parser_.add_argument(
            "--ext",
            action="append",
            default=[],
            help="another source file extension, e.g. kt or .vue (repeatable)",
        )
        parser_.add_argument(
            "--provenance-map",
            help="add the extension of each file this provenance map's entries[] name",
        )

    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdout)
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
