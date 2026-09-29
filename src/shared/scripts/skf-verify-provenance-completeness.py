#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Verify Provenance Completeness — deterministic Check D for update-skill.

`skf-update-skill/references/validate.md §2 Check D (Provenance Completeness)`
previously asked the model to perform three deterministic set/citation
operations by eye, against in-context data:

  1. **Completeness** — verify every documented export has a provenance-map
     entry (metadata `exports[]` \\ provenance `entries[].export_name`).
  2. **Orphans** — flag provenance entries whose export was removed
     (provenance `entries[].export_name` \\ metadata `exports[]`).
  3. **Stale citations** — flag entries whose `source_file:source_line`
     no longer resolves (file gone, or line past end of file), or whose
     line is not a line that defines the export (`line-not-definition`).
  4. **Citation prefixes** (only with `--skill-dir`): flag each `[AST:]` /
     `[SRC:]` citation in the skill's markdown whose prefix disagrees with
     the provenance entry it cites, or an `[AST:]` citation in a skill whose
     map holds no ast-grep entry at all.
  5. **Node kinds** (only with `--check-node-kinds`): flag each ast-grep
     entry whose `ast_node_type` is not a node kind ast-grep knows for the
     entry's language.

An LLM set-diff can silently pass a dropped or orphaned entry, and eyeballing
whether a cited line still exists is not something the model can do reliably.
Both inputs are machine-readable — `metadata.json` (`exports[]`, a list of
export-name strings) and `provenance-map.json` (`entries[]` with
`export_name` / `source_file` / `source_line`, plus an optional
`reexport_map` for stack-skill barrel renames) are written by
`write.md` §2 and §3. This script diffs the two sets and re-checks the
citations exactly, so Check D consumes JSON rather than computing it.

Timing: this runs **post-write** (`write.md` §6), after `metadata.json`
(§2) and `provenance-map.json` (§3) are on disk. `validate.md` Check D
defers here — the provenance map does not exist yet at validate time.
create-skill runs it too, at validate §7a against the staged package (with
`--skill-dir` and `--check-node-kinds`, as update-skill write.md §6a does),
and test-skill at coverage-check §4c (line check only).

Determinism:
  - Set operations are pure over the two JSON inputs.
  - Citation resolution reads the source tree at `source_root` (from the
    provenance map, or `--source-root`). When no source root resolves on
    disk, the stale check is SKIPPED (`summary.stale_check` reports it) and
    only completeness + orphan diffs run — those need no source tree. Same
    input tree → same output.

Stack-skill canonicalization: a provenance entry's `export_name` may be the
internal name of a barrel-renamed export (e.g. `_Impl` re-exported as
`Public`). Names are canonicalized through `reexport_map`
(`{internal: public}`) before the set-diff, mirroring
`skf-load-provenance.extract_reexport_map`, so an internal-named entry does
not read as a missing public export nor as an orphan.

Definition lines: after a citation resolves (the file exists and the line
is in range, so the older reasons win), the line must define the entry's
export. NAME is the raw `export_name` (not canonicalized); for a dotted
name (`App.update`) it is the last segment. The rules follow the
`source_file` extension:

  - Python (`.py`, `.pyi`): the `def` / `async def` / `class NAME` line
    itself (a decorator line above it does not count); an assignment
    binding NAME (`NAME =`, `NAME: T =`, annotation-only `NAME: T`, a
    target list `A, NAME = ...`, a chain `A = NAME = ...`, PEP 695
    `type NAME =`); an import that binds NAME (`import NAME`,
    `import X as NAME`, `from X import NAME`, `from X import Y as NAME`),
    including NAME on its own line inside a parenthesized or
    backslash-continued import. These count only on a line where a
    statement begins (the stdlib tokenizer says so), so a docstring line,
    a keyword argument or a parameter never matches; a file that does not
    tokenize is matched line by line. A `from X import *` line counts only
    when no other line of the file defines NAME (a re-export the
    extraction could not trace is cited at its star import).
  - TS/JS (`.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`): a
    `function` (or `function*`), `class`, `interface`, `type`, `enum`,
    `namespace`, `const`, `let` or `var` declaration of NAME, with any of
    `export`, `default`, `async`, `declare`, `abstract`;
    `export import NAME =`; `export * as NAME from`; `export default NAME`;
    an `export { ... }` list whose exposed name is NAME; CommonJS
    `exports.NAME =`, `module.exports.NAME =`, or NAME as a key or
    shorthand inside `module.exports = { ... }`. A list or object spanning
    several lines counts on the line where NAME appears. For a dotted
    name, an indented class member declaring NAME (method, property or
    accessor, with any of `public`, `private`, `protected`, `static`,
    `readonly`, `async`, `abstract`, `override`, `declare`, `get`, `set`)
    also counts. An indented `NAME(...)` with no modifier, followed by `;`
    or another expression rather than a body `{` or a return type `:`, is
    a call, not a member; an indented `NAME: ...` or `NAME = ...` ending
    with `,` is an object-literal entry or a destructuring default.
    Comments never match: `//` to the end of the line and `/* ... */`
    across lines are removed first, outside '...', "..." and `...` strings,
    and brackets inside a string do not count toward a `module.exports`
    object's depth. Strings are followed within one line only, so a
    template literal spanning lines can hide or expose a comment marker.

Indentation: for a dotted name every match counts. For an undotted name,
matches at any indentation count, but when the file has a column-0 match
the indented ones are dropped, so a local shadow never outranks the
module-level definition. A line inside a multi-line import, export list
or `module.exports` object takes the column of the line its statement
starts on. When the recorded line is itself an indented match that this
rule dropped (a method recorded under an undotted name beside a
module-level function of the same name), the finding lists the recorded
line too, so it carries several lines and no caller auto-moves it.

Entries in other files, and entries whose `export_type` is `module` or
`package` (case-insensitive; neither has a definition line), are skipped
and counted in `summary.line_check_skipped`. A `line-not-definition` item
lists every defining line in the file in `definition_lines`. An empty list
means the rules found no definition line, which may be a shape they do not
cover: the entry is unverified, not gone, and no caller auto-fixes it.

Citation check (`--skill-dir DIR`, which must hold a `SKILL.md`): scans
`DIR/SKILL.md` and `DIR/references/**/*.md` for `[AST:path:Ln]` /
`[SRC:path:Ln]`, ranges `Ln-m` / `Ln-Lm` included (the first line counts);
a citation with no line is ignored. A citation matches an entry when its
normalized path equals `source_file` and its line equals `source_line`.
`summary.skill_citations_matched` counts the citations that matched an
entry: 0 with citations scanned means the skill cites paths under another
root. Reasons, one per citation:

  - `prefix-mismatch`: the matched entry's `extraction_method` implies the
    other prefix (`ast-grep` / `ast_bridge` give AST, `source-read` /
    `source_reading` give SRC). It wins over the reason below.
  - `ast-without-ast-grep`: an `[AST:]` citation in a skill whose map has
    no `ast-grep` or `ast_bridge` entry, raised only when every entry with
    a source line carries a known `extraction_method` (a missing or
    unknown method may hide an ast-grep entry).

When several entries share the cited line, the citation is a
`prefix-mismatch` only when none of them implies its prefix. An
`extraction_method` that is not a string reads as unknown (it implies no
prefix). Unmatched citations are not findings unless the second reason
applies.

Node-kind check (`--check-node-kinds`): ast-grep's JSON output never
reports the kind of the node a rule matched, so an entry's `ast_node_type`
is copied from the recipe that matched it, and nothing else proves it is a
real kind. For each entry whose `extraction_method` is `ast-grep` or
`ast_bridge` and whose `ast_node_type` is a non-blank string, the
`source_file` extension picks an ast-grep language (`.py` / `.pyi` python,
`.ts` / `.mts` / `.cts` typescript, `.tsx` tsx, `.js` / `.jsx` / `.mjs` /
`.cjs` javascript, `.rs` rust, `.go` go, `.java` java, `.kt` / `.kts`
kotlin, `.cs` csharp, `.rb` ruby, `.swift` swift, `.php` php); an entry in
any other file is skipped and counted in `summary.node_kind_check_skipped`.
Reasons, one per entry:

  - `error-kind`: the kind is `ERROR`, the node tree-sitter makes of code
    it cannot parse. ast-grep accepts it in a rule, so it is not asked.
  - `invalid-kind`: the kind is not shaped like a kind
    (`[A-Za-z_][A-Za-z0-9_]*`, so no whitespace or shell characters reach
    ast-grep), judged without ast-grep; or ast-grep rejected it (its error
    names an invalid kind).

Those two are judged whatever the ast-grep lookup finds. Every other kind is
asked once per distinct (language, kind): `ast-grep scan --config
<sgconfig.yml> --inline-rules <rule> --stdin` with a rule matching only that
kind, over an empty stdin, from a temporary folder holding a minimal
sgconfig.yml that `--config` names (so no other sgconfig.yml is read).
ast-grep parses the rule before reading input and rejects a kind the
language's grammar lacks. Before that, ast-grep is asked about a kind no
grammar has; unless it rejects it, its answers cannot be read and the check
is `skipped-unrecognized-ast-grep`. When no `ast-grep` executable resolves
(the CWD-shim guard applies), the check is `skipped-no-ast-grep`. With no
kind left to ask, ast-grep is not looked up and the check is `checked`.

An ast-grep failure that does not name the kind proves nothing about it: the
entry is listed in `node_kinds_unchecked[]`, not as a finding, with reason
`ast-grep-error`, `ast-grep-timeout` (after the first timeout the remaining
kinds are not asked) or `temp-folder-error` (the temporary folder could not
be made or written). Without the flag the output keeps its shape: there are
no `node_kinds` / `node_kinds_unchecked` keys, and the one key added is
`summary.node_kind_check: "not-requested"`.

Subcommand:
  verify --metadata <metadata.json> --provenance <provenance-map.json>
         [--source-root <path>] [--skill-dir <dir>] [--check-node-kinds]
         [-o <out.json>]

    Emit JSON:
      {
        "status": "pass" | "findings",
        "missing":  ["<export documented but not in provenance>", ...],
        "orphaned": ["<provenance entry with no documented export>", ...],
        "stale": [
          {"export_name": "<raw entry name>",
           "source_file": "<rel path>",
           "source_line": <int|null>,
           "reason": "file-missing" | "line-out-of-bounds" | "line-invalid"
                     | "line-not-definition",
           "definition_lines": [<int>, ...]},   # line-not-definition only
          ...
        ],
        "citations": [
          {"file": "<markdown path relative to --skill-dir>",
           "line": <int>,                  # line of the markdown file
           "citation": "[AST:<path>:L<n>]",
           "prefix": "AST" | "SRC",
           "cited_file": "<path as written>",
           "cited_line": <int>,
           "reason": "prefix-mismatch" | "ast-without-ast-grep",
           "expected_prefix": "AST" | "SRC",
           "export_name": "<matched entry name>" | null},
          ...
        ],
        "node_kinds": [                    # --check-node-kinds only
          {"export_name": "<raw entry name>" | null,
           "entry_index": <int>,           # position in entries[]
           "source_file": "<rel path>",
           "source_line": <as recorded>,
           "ast_node_type": "<recorded kind>",
           "language": "<ast-grep language>",
           "reason": "invalid-kind" | "error-kind"},
          ...
        ],
        "node_kinds_unchecked": [          # --check-node-kinds only
          {... the same keys ...,
           "reason": "ast-grep-error" | "ast-grep-timeout"
                     | "temp-folder-error"},
          ...
        ],
        "summary": {
          "exports_checked":  <int>,   # documented exports (metadata)
          "entries_checked":  <int>,   # provenance entries with export_name
          "missing_count":    <int>,
          "orphaned_count":   <int>,
          "stale_count":      <int>,
          "citations_checked": <int>,  # entries whose citation was resolved
          "line_check_skipped": <int>, # resolved entries with no line rule
          "stale_check": "checked" | "skipped-no-source-root",
          "skill_citations_scanned": <int>,  # [AST:]/[SRC:] with a line
          "skill_citations_matched": <int>,  # of those, citing an entry
          "citation_findings_count": <int>,
          "citation_check": "checked" | "skipped-no-skill-dir",
          "node_kind_check": "checked" | "skipped-no-ast-grep"
                             | "skipped-unrecognized-ast-grep"
                             | "not-requested",
          # the four below appear with --check-node-kinds only
          "node_kinds_checked": <int>,       # entries judged, ERROR included
          "node_kind_check_skipped": <int>,  # entries in an unmapped file
          "node_kind_check_errors": <int>,   # len(node_kinds_unchecked)
          "node_kind_findings_count": <int>
        }
      }

    `missing` / `orphaned` are sorted, deduplicated public names.
    `stale` is sorted by (export_name, source_file).
    `citations` is sorted by (file, line, column).
    `node_kinds` / `node_kinds_unchecked` are sorted by (export_name,
    source_file, entry_index).

CLI examples:
  uv run skf-verify-provenance-completeness.py verify \\
      --metadata {skill_package}/metadata.json \\
      --provenance {forge_version}/provenance-map.json \\
      --source-root {source_root} \\
      --skill-dir {skill_package} \\
      --check-node-kinds

Exit codes:
  0  verification ran and found nothing (status "pass")
  1  verification ran and found missing / orphaned / stale entries,
     citation findings or node-kind findings (status "findings");
     advisory: the caller decides how to surface it
  2  error (input file not found, --skill-dir not found, not a directory
     or without a SKILL.md, malformed JSON, invalid structure, or any
     unexpected failure while verifying, such as an unreadable file); one
     line on stderr and no JSON
"""

from __future__ import annotations

import argparse
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path


STALE_FILE_MISSING = "file-missing"
STALE_LINE_OOB = "line-out-of-bounds"
STALE_LINE_INVALID = "line-invalid"
STALE_LINE_NOT_DEFINITION = "line-not-definition"

CITATION_PREFIX_MISMATCH = "prefix-mismatch"
CITATION_AST_WITHOUT_AST_GREP = "ast-without-ast-grep"

PYTHON_EXTENSIONS = frozenset({".py", ".pyi"})
TSJS_EXTENSIONS = frozenset(
    {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
)
# export_type values that name a whole module or package: no definition line.
NO_DEFINITION_EXPORT_TYPES = frozenset({"module", "package"})

# extraction_method -> the citation prefix it implies
METHOD_PREFIX = {
    "ast-grep": "AST",
    "ast_bridge": "AST",
    "source-read": "SRC",
    "source_reading": "SRC",
}
AST_METHODS = frozenset({"ast-grep", "ast_bridge"})
# Every extraction_method SKF writes (the same list skf-render-metadata-stats
# checks labels against).
KNOWN_METHODS = frozenset(
    {
        "ast-grep",
        "source-read",
        "ast_bridge",
        "source_reading",
        "qmd_bridge",
        "compose-from-skill",
    }
)

NODE_KIND_INVALID = "invalid-kind"
NODE_KIND_ERROR = "error-kind"
# Why an entry's kind went unjudged (node_kinds_unchecked[].reason).
UNCHECKED_AST_GREP_ERROR = "ast-grep-error"
UNCHECKED_TIMEOUT = "ast-grep-timeout"
UNCHECKED_TEMP_FOLDER = "temp-folder-error"
# The node tree-sitter makes of code it cannot parse. ast-grep accepts it as
# a kind, but no recipe declares it, so an entry recording it guessed.
ERROR_NODE_KIND = "ERROR"
# Every named node kind of a grammar ast-grep ships has this shape. Anything
# else is judged without ast-grep: ast-grep trims surrounding whitespace, and
# `& | % ^` would reach cmd.exe through an npm `.cmd` shim on Windows.
NODE_KIND_SHAPE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A kind no grammar has. ast-grep must reject it before its answers are read.
BOGUS_NODE_KIND = "skf_no_such_node_kind"
# An explicit, valid sgconfig.yml, so no sgconfig.yml in the temporary
# folder's ancestors is read.
MINIMAL_SGCONFIG = "ruleDirs: []\n"
# source_file extension -> the ast-grep language whose grammar names its kinds
AST_GREP_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".swift": "swift",
    ".php": "php",
}
NODE_KIND_TIMEOUT_SEC = 20  # per ast-grep call; each parses one tiny rule


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------


def load_json_object(path: Path, label: str) -> dict:
    """Read a JSON file and require a top-level object. Raises ValueError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {label} {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{label} {path} must be a JSON object at top level; "
            f"got {type(data).__name__}"
        )
    return data


# --------------------------------------------------------------------------
# Extraction / canonicalization
# --------------------------------------------------------------------------


def extract_export_names(metadata: dict) -> list[str]:
    """Pull documented export names from metadata.exports.

    `exports` is a list of export-name strings (per the skill templates).
    Defensively also accept dict items carrying `name` / `export_name`.
    Non-string / unnamed items are skipped. Order preserved; caller dedupes.
    """
    names: list[str] = []
    exports = metadata.get("exports")
    if not isinstance(exports, list):
        return names
    for item in exports:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            nm = item.get("name") or item.get("export_name")
            if isinstance(nm, str) and nm:
                names.append(nm)
    return names


def extract_reexport_map(prov: dict) -> dict[str, str]:
    """Build the `{internal: public}` re-export map.

    Mirrors `skf-load-provenance.extract_reexport_map`: top-level
    `reexport_map` is authoritative; per-entry `reexported_as` fills gaps.
    Non-string keys/values skipped.
    """
    out: dict[str, str] = {}
    top = prov.get("reexport_map")
    if isinstance(top, dict):
        for k, v in top.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    entries = prov.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            internal = entry.get("export_name")
            public = entry.get("reexported_as")
            if isinstance(internal, str) and isinstance(public, str):
                out.setdefault(internal, public)
    return out


def canon(name: str, reexport_map: dict[str, str]) -> str:
    """Canonicalize an export name to its public form via reexport_map.

    Idempotent for names that are not internal (public names are not keys).
    """
    return reexport_map.get(name, name)


def provenance_entry_names(prov: dict) -> list[str]:
    """Raw `export_name` of every well-formed provenance entry (order kept)."""
    names: list[str] = []
    entries = prov.get("entries")
    if not isinstance(entries, list):
        return names
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nm = entry.get("export_name")
        if isinstance(nm, str) and nm:
            names.append(nm)
    return names


# --------------------------------------------------------------------------
# Citation resolution
# --------------------------------------------------------------------------


def _coerce_line(value: object) -> int | None | str:
    """Return an int line number, None (tolerated), or a sentinel str for
    an un-coercible non-null value (reported as line-invalid)."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass — a boolean line number is nonsense
        return "invalid"
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return "invalid"
    return "invalid"


def check_citation(
    source_file: object, source_line: object, source_root: Path
) -> str | None:
    """Resolve a single `source_file:source_line` citation under source_root.

    Returns a stale reason (one of the STALE_* constants) when the citation
    does not resolve, or None when it is valid OR tolerated.

    Tolerated (returns None): source_file missing/empty, or source_line null
    or empty — `unknown`-outcome entries legitimately carry null citations
    (write.md §3), so an absent citation is not "stale".
    """
    if not isinstance(source_file, str) or not source_file.strip():
        return None
    line = _coerce_line(source_line)
    if line is None:
        return None
    if isinstance(line, str):  # sentinel for un-coercible non-null value
        return STALE_LINE_INVALID

    rel = source_file.strip().replace("\\", "/")
    target = (source_root / rel).resolve()
    if not target.is_file():
        return STALE_FILE_MISSING

    if line < 1:
        return STALE_LINE_OOB
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            line_count = sum(1 for _ in fh)
    except OSError:
        return STALE_FILE_MISSING
    if line > line_count:
        return STALE_LINE_OOB
    return None


# --------------------------------------------------------------------------
# Definition lines
# --------------------------------------------------------------------------

_PY_FROM_IMPORT_RE = re.compile(r"^\s*from\s+[\w.]+\s+import\s+(.*)$")
_PY_IMPORT_RE = re.compile(r"^\s*import\s+(.*)$")
_PY_IMPORT_ITEM_RE = re.compile(r"^([\w.]+)(?:\s+as\s+(\w+))?$")
_PY_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
# `A = value`, `A = B = value`: every name left of an `=` that is not `==`.
_PY_ASSIGN_CHAIN_RE = re.compile(r"^\s*((?:[A-Za-z_]\w*\s*=(?!=)\s*)+)")
# `A, B = value`, `(A, *B) = value`, `A, = value`.
_PY_TARGET_LIST_RE = re.compile(
    r"^\s*[(\[]?\s*"
    r"(\*?[A-Za-z_]\w*\s*,(?:\s*\*?[A-Za-z_]\w*\s*,)*(?:\s*\*?[A-Za-z_]\w*)?)"
    r"\s*[)\]]?\s*=(?!=)"
)
# Tokens that never begin a statement.
_PY_LAYOUT_TOKENS = frozenset(
    {
        tokenize.NL,
        tokenize.COMMENT,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.ENCODING,
    }
)

_JS_MODIFIERS = r"(?:(?:export|default|async|declare|abstract)\s+)*"
_JS_KINDS = (
    r"(?:function(?:\s*\*\s*|\s+)"
    r"|(?:class|interface|type|enum|namespace|let|var)\s+"
    r"|const\s+(?:enum\s+)?)"
)
_JS_MEMBER_MODIFIERS = (
    r"(?:(?:public|private|protected|static|readonly|async|abstract"
    r"|override|declare|get|set)\s+)*"
)
_JS_EXPORT_LIST_RE = re.compile(r"^\s*export\s+(?:type\s+)?\{(.*)$")
_JS_EXPORT_ITEM_RE = re.compile(
    r"^(?:type\s+)?([\w$]+)(?:\s+as\s+([\w$]+))?$"
)
_JS_MODULE_EXPORTS_OBJECT_RE = re.compile(r"^\s*module\.exports\s*=\s*\{(.*)$")


def definition_name(export_name: str) -> str:
    """The name a definition line must carry: the last segment of a dotted
    export name (`App.update` -> `update`), else the name itself."""
    return export_name.rsplit(".", 1)[-1]


def _read_lines(path: Path) -> list[str] | None:
    """Read a text file as lines numbered like `check_citation` counts them
    (universal newlines; a UTF-8 BOM is dropped so it never hides line 1).
    None when the file cannot be read."""
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            return [ln.rstrip("\n") for ln in fh]
    except OSError:
        return None


def _is_column_0(text: str) -> bool:
    """True when a line starts at column 0 (no leading whitespace)."""
    return not text[:1].isspace()


def _py_statement_starts(lines: list[str]) -> set[int] | None:
    """Line numbers on which a Python statement begins.

    Uses the stdlib tokenizer, so a line inside a string or inside brackets
    (a docstring, a keyword argument, a dict entry, a parameter on its own
    line) never reads as a definition. None when the file does not tokenize:
    every line is then a candidate.
    """
    starts: set[int] = set()
    at_start = True
    readline = io.StringIO("\n".join(lines) + "\n").readline
    try:
        for tok in tokenize.generate_tokens(readline):
            if tok.type == tokenize.NEWLINE:
                at_start = True
            elif tok.type in _PY_LAYOUT_TOKENS:
                continue
            elif at_start:
                starts.add(tok.start[0])
                at_start = False
    except (tokenize.TokenError, SyntaxError, ValueError):
        return None
    return starts


def _js_code_lines(lines: list[str]) -> list[str]:
    """Each TS/JS line with its comments removed: `//` to the end of the
    line, and `/* ... */` across lines, both only outside a '...', "..." or
    `...` string. A string is followed within its line only: a template
    literal that spans lines is not tracked, so each line starts outside
    any string. A backslash outside a string escapes the next character, so
    a regex literal such as `/\\/*/` opens no comment."""
    out: list[str] = []
    in_block = False
    for text in lines:
        buf: list[str] = []
        quote: str | None = None
        i, n = 0, len(text)
        while i < n:
            if in_block:
                end = text.find("*/", i)
                if end < 0:
                    break
                in_block = False
                buf.append(" ")
                i = end + 2
                continue
            ch = text[i]
            if ch == "\\" and i + 1 < n:
                buf.append(text[i : i + 2])
                i += 2
                continue
            if quote is not None:
                if ch == quote:
                    quote = None
            elif ch in "'\"`":
                quote = ch
            elif text.startswith("//", i):
                break
            elif text.startswith("/*", i):
                in_block = True
                i += 2
                continue
            buf.append(ch)
            i += 1
        out.append("".join(buf).rstrip())
    return out


class _SourceCache:
    """Source lines, Python statement starts and TS/JS comment-free lines,
    read once per file."""

    def __init__(self) -> None:
        self._lines: dict[Path, list[str] | None] = {}
        self._starts: dict[Path, set[int] | None] = {}
        self._js_code: dict[Path, list[str]] = {}

    def lines(self, path: Path) -> list[str] | None:
        if path not in self._lines:
            self._lines[path] = _read_lines(path)
        return self._lines[path]

    def py_statement_starts(self, path: Path, lines: list[str]) -> set[int] | None:
        if path not in self._starts:
            self._starts[path] = _py_statement_starts(lines)
        return self._starts[path]

    def js_code_lines(self, path: Path, lines: list[str]) -> list[str]:
        if path not in self._js_code:
            self._js_code[path] = _js_code_lines(lines)
        return self._js_code[path]


def _py_import_binds(items: str, name: str, from_import: bool) -> bool:
    """True when an import item list binds `name`."""
    items = items.split("#", 1)[0]
    for raw in items.replace("(", " ").replace(")", " ").replace("\\", " ").split(","):
        m = _PY_IMPORT_ITEM_RE.match(raw.strip())
        if not m:
            continue
        target, alias = m.group(1), m.group(2)
        if alias is not None:
            bound = alias
        elif from_import:
            bound = target
        else:
            bound = target.split(".", 1)[0]  # `import a.b` binds `a`
        if bound == name:
            return True
    return False


def _py_assigned_names(code: str) -> set[str]:
    """Names an assignment statement binds (`A = B = v`, `A, *B = v`)."""
    names: set[str] = set()
    m = _PY_ASSIGN_CHAIN_RE.match(code)
    if m:
        names.update(_PY_IDENT_RE.findall(m.group(1)))
    m = _PY_TARGET_LIST_RE.match(code)
    if m:
        names.update(_PY_IDENT_RE.findall(m.group(1)))
    return names


def _python_definition_lines(
    lines: list[str], name: str, starts: set[int] | None
) -> list[tuple[int, bool]]:
    """(line, at column 0) for every line that defines `name`.

    A line inside a parenthesized or backslash-continued import takes the
    column of the line the import statement starts on. A `from X import *`
    line counts only when no other line defines `name` (a re-export the
    extraction could not trace further is cited at its star import).
    """
    esc = re.escape(name)
    decl = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{esc}(?!\w)")
    annotated = re.compile(rf"^\s*{esc}\s*:(?!=)")
    type_alias = re.compile(rf"^\s*type\s+{esc}\s*(?:\[[^\]]*\]\s*)?=(?!=)")
    found: list[tuple[int, bool]] = []
    star_imports: list[tuple[int, bool]] = []
    # An import statement that continues on the next line:
    # (closing mark "paren" or "backslash", column 0, from-import).
    cont: tuple[str, bool, bool] | None = None
    for number, text in enumerate(lines, start=1):
        code = text.split("#", 1)[0]
        if cont is not None:
            mark, top, from_import = cont
            if mark == "paren":
                if ")" in code:
                    code = code.split(")", 1)[0]
                    cont = None
            else:
                stripped = code.rstrip()
                if stripped.endswith("\\"):
                    code = stripped[:-1]
                else:
                    cont = None
            if _py_import_binds(code, name, from_import):
                found.append((number, top))
            continue
        if starts is not None and number not in starts:
            continue
        top = _is_column_0(text)
        if (
            decl.match(code)
            or annotated.match(code)
            or type_alias.match(code)
            or name in _py_assigned_names(code)
        ):
            found.append((number, top))
            continue
        m = _PY_FROM_IMPORT_RE.match(code)
        from_import = m is not None
        if m is None:
            m = _PY_IMPORT_RE.match(code)
        if m is None:
            continue
        rest = m.group(1)
        if from_import and rest.strip() == "*":
            star_imports.append((number, top))
            continue
        if from_import and rest.lstrip().startswith("(") and ")" not in rest:
            cont = ("paren", top, True)
        elif rest.rstrip().endswith("\\"):
            cont = ("backslash", top, from_import)
            rest = rest.rstrip()[:-1]
        if _py_import_binds(rest, name, from_import):
            found.append((number, top))
    return found or star_imports


def _js_export_list_binds(items: str, name: str) -> bool:
    """True when an `export { ... }` item list exposes `name`."""
    for raw in items.split(","):
        m = _JS_EXPORT_ITEM_RE.match(raw.strip())
        if m and (m.group(2) or m.group(1)) == name:
            return True
    return False


def _js_depth1_pieces(text: str, depth: int) -> tuple[int, list[str]]:
    """Split the text of a `module.exports = { ... }` object into its
    top-level pieces (the text between commas at depth 1).

    Returns the bracket depth after `text` (0 once the object closed) and
    the pieces. An opening bracket at depth 1 stays in its piece, so a
    method shorthand `name(` and a key `name: {` keep their marker. Brackets
    and commas inside a string on the line are not counted.
    """
    pieces: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    escaped = False
    for ch in text:
        if quote is not None:
            # text inside a string: kept in its piece, never counted
            if depth == 1:
                buf.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
            if depth == 1:
                buf.append(ch)
        elif ch in "([{":
            if depth == 1:
                buf.append(ch)
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1:
            if ch == ",":
                pieces.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
    pieces.append("".join(buf))
    return depth, pieces


def _js_paren_tail_is_call(after_open: str) -> bool:
    """For `name(` on an indented line: True when the text after the
    parameters says a call, not a method (`name(x);`). A method's
    parameters are followed by its body `{` or a return type `:`, or they
    continue on the next line."""
    depth = 1
    for i, ch in enumerate(after_open):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                rest = after_open[i + 1 :].strip()
                return not (rest == "" or rest[0] in "{:")
    return False


def _tsjs_definition_lines(
    lines: list[str], code_lines: list[str], name: str, dotted: bool
) -> list[tuple[int, bool]]:
    """(line, at column 0) for every line that defines `name`.

    `code_lines` are `lines` with comments removed (`_js_code_lines`), so a
    JSDoc line or a commented-out declaration never matches. A line inside
    a multi-line `export { ... }` list or `module.exports = { ... }` object
    takes the column of the line the statement starts on. Class members
    count only for a dotted export name.
    """
    esc = re.escape(name)
    end = r"(?![\w$])"
    statements = (
        re.compile(rf"^\s*{_JS_MODIFIERS}{_JS_KINDS}{esc}{end}"),
        re.compile(rf"^\s*export\s+import\s+(?:type\s+)?{esc}\s*=(?![=>])"),
        re.compile(rf"^\s*export\s+(?:type\s+)?\*\s+as\s+{esc}\s+from{end}"),
        re.compile(rf"^\s*export\s+default\s+{esc}\s*;?\s*$"),
        re.compile(rf"^\s*(?:module\.)?exports\.{esc}\s*=(?![=>])"),
    )
    object_key = re.compile(
        rf"^\s*(?:(?:async|get|set)\s+|\*\s*)*(?:(['\"]){esc}\1|{esc}{end})"
        rf"\s*(?:[:(]|$)"
    )
    member = re.compile(
        rf"^\s+(?P<mods>{_JS_MEMBER_MODIFIERS})(?:\*\s*)?{esc}{end}\s*[?!]?\s*"
        rf"(?:<[^>]*>\s*)?(?P<tail>[(:=;]|$)"
    )
    found: list[tuple[int, bool]] = []
    # A statement that continues on the next line:
    # ("list" or "object", column 0, bracket depth of an object).
    cont: tuple[str, bool, int] | None = None
    for number, (text, code) in enumerate(zip(lines, code_lines), start=1):
        if cont is not None:
            kind, top, depth = cont
            if kind == "list":
                if "}" in code:
                    code = code.split("}", 1)[0]
                    cont = None
                hit = _js_export_list_binds(code, name)
            else:
                depth, pieces = _js_depth1_pieces(code, depth)
                cont = ("object", top, depth) if depth > 0 else None
                hit = any(object_key.match(p) for p in pieces)
            if hit:
                found.append((number, top))
            continue
        top = _is_column_0(text)
        if any(p.match(code) for p in statements):
            found.append((number, top))
            continue
        m = _JS_EXPORT_LIST_RE.match(code)
        if m:
            rest = m.group(1)
            if "}" in rest:
                rest = rest.split("}", 1)[0]
            else:
                cont = ("list", top, 0)
            if _js_export_list_binds(rest, name):
                found.append((number, top))
            continue
        m = _JS_MODULE_EXPORTS_OBJECT_RE.match(code)
        if m:
            depth, pieces = _js_depth1_pieces(m.group(1), 1)
            if depth > 0:
                cont = ("object", top, depth)
            if any(object_key.match(p) for p in pieces):
                found.append((number, top))
            continue
        if not dotted:
            continue
        m = member.match(code)
        if not m:
            continue
        tail = m.group("tail")
        if tail == "(":
            if not m.group("mods") and _js_paren_tail_is_call(code[m.end():]):
                continue
        elif code.endswith(","):
            continue  # an object-literal entry or a destructuring default
        elif tail == "=" and code[m.end() : m.end() + 1] in ("=", ">"):
            continue
        found.append((number, top))
    return found


def _prefer_module_level(found: list[tuple[int, bool]], dotted: bool) -> list[int]:
    """The definition lines to report. For an undotted name, a column-0
    match drops the indented ones, so a local shadow never outranks the
    module-level definition; a dotted name keeps every match."""
    if not dotted:
        top = [n for n, at_column_0 in found if at_column_0]
        if top:
            return sorted(set(top))
    return sorted({n for n, _ in found})


def line_rule_applies(source_file: str, export_type: object) -> bool:
    """True when the definition-line rules cover this entry: a Python or
    TS/JS file, and an export that is not a whole module or package."""
    if isinstance(export_type, str) and (
        export_type.strip().lower() in NO_DEFINITION_EXPORT_TYPES
    ):
        return False
    suffix = Path(source_file.strip().replace("\\", "/")).suffix.lower()
    return suffix in PYTHON_EXTENSIONS or suffix in TSJS_EXTENSIONS


def _definition_matches(
    source_file: str,
    export_name: str,
    source_root: Path,
    cache: _SourceCache | None = None,
) -> tuple[list[int], set[int]] | None:
    """(definition lines to report, every matching line) for an export.

    The first item applies the column-0 rule; the second keeps the indented
    matches that rule dropped. None when the file's extension has no
    definition rule or the file cannot be read.
    """
    rel = source_file.strip().replace("\\", "/")
    suffix = Path(rel).suffix.lower()
    if suffix not in PYTHON_EXTENSIONS and suffix not in TSJS_EXTENSIONS:
        return None
    cache = cache if cache is not None else _SourceCache()
    path = (source_root / rel).resolve()
    lines = cache.lines(path)
    if lines is None:
        return None
    name = definition_name(export_name)
    if not name:
        return [], set()
    dotted = "." in export_name
    if suffix in PYTHON_EXTENSIONS:
        starts = cache.py_statement_starts(path, lines)
        found = _python_definition_lines(lines, name, starts)
    else:
        code_lines = cache.js_code_lines(path, lines)
        found = _tsjs_definition_lines(lines, code_lines, name, dotted)
    return _prefer_module_level(found, dotted), {n for n, _ in found}


def find_definition_lines(
    source_file: str,
    export_name: str,
    source_root: Path,
    cache: _SourceCache | None = None,
) -> list[int] | None:
    """Every line of `source_file` that defines `export_name`, in order,
    after the column-0 rule.

    Returns None when the file's extension has no definition rule or the
    file cannot be read.
    """
    matches = _definition_matches(source_file, export_name, source_root, cache)
    return None if matches is None else matches[0]


# --------------------------------------------------------------------------
# Skill citations ([AST:] / [SRC:] prefixes)
# --------------------------------------------------------------------------

# `[AST:path:L12]`, `[SRC:path:L12-34]`, `[SRC:path:L12-L34]`. A citation
# with no `:L<n>` part does not match and is ignored.
_SKILL_CITATION_RE = re.compile(
    r"\[(AST|SRC):([^\[\]\n]+?):L(\d+)(?:-L?\d+)?\]"
)


def normalize_path(path: str) -> str:
    """Normalize a cited or recorded source path for comparison."""
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return posixpath.normpath(p) if p else p


def skill_markdown_files(skill_dir: Path) -> list[Path]:
    """`SKILL.md` then every `references/**/*.md`, in a stable order."""
    files: list[Path] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        files.append(skill_md)
    refs = skill_dir / "references"
    if refs.is_dir():
        files.extend(sorted(p for p in refs.rglob("*.md") if p.is_file()))
    return files


def scan_skill_citations(skill_dir: Path) -> list[dict]:
    """Every `[AST:]` / `[SRC:]` citation with a line, in file order."""
    found: list[dict] = []
    for md in skill_markdown_files(skill_dir):
        rel = md.relative_to(skill_dir).as_posix()
        lines = _read_lines(md) or []
        for number, text in enumerate(lines, start=1):
            for m in _SKILL_CITATION_RE.finditer(text):
                found.append(
                    {
                        "file": rel,
                        "line": number,
                        "column": m.start() + 1,
                        "citation": m.group(0),
                        "prefix": m.group(1),
                        "cited_file": m.group(2).strip(),
                        "cited_line": int(m.group(3)),
                    }
                )
    return found


def _extraction_method(entry: dict) -> str | None:
    """The entry's `extraction_method`, or None when it is not a string
    (a list or object there reads as an unknown method, never a crash)."""
    method = entry.get("extraction_method")
    return method if isinstance(method, str) else None


def check_skill_citations(
    prov: dict, skill_dir: Path
) -> tuple[list[dict], int, int]:
    """Compare each skill citation's prefix with the entry it cites.

    Returns (findings, citations_scanned, citations_matched): a citation is
    matched when its path and line name at least one provenance entry.
    """
    entries = prov.get("entries")
    entries = entries if isinstance(entries, list) else []
    by_location: dict[tuple[str, int], list[dict]] = {}
    has_ast_entry = False
    # `ast-without-ast-grep` needs proof that no entry came from ast-grep:
    # every entry with a source line must carry a known method.
    methods_known = True
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        method = _extraction_method(entry)
        if method in AST_METHODS:
            has_ast_entry = True
        sf = entry.get("source_file")
        line = _coerce_line(entry.get("source_line"))
        if not isinstance(sf, str) or not sf.strip() or not isinstance(line, int):
            continue
        if method not in KNOWN_METHODS:
            methods_known = False
        by_location.setdefault((normalize_path(sf), line), []).append(entry)

    scanned = sorted(
        scan_skill_citations(skill_dir),
        key=lambda c: (c["file"], c["line"], c["column"]),
    )
    findings: list[dict] = []
    matched_count = 0
    for cit in scanned:
        prefix = cit["prefix"]
        other = "SRC" if prefix == "AST" else "AST"
        matched = by_location.get(
            (normalize_path(cit["cited_file"]), cit["cited_line"]), []
        )
        if matched:
            matched_count += 1
        implied = [(METHOD_PREFIX.get(_extraction_method(e)), e) for e in matched]
        agrees = any(p == prefix for p, _ in implied)
        mismatch = next((e for p, e in implied if p == other), None)
        reason = None
        export_name = None
        if not agrees and mismatch is not None:
            reason = CITATION_PREFIX_MISMATCH
            export_name = mismatch.get("export_name")
        elif prefix == "AST" and not has_ast_entry and methods_known:
            reason = CITATION_AST_WITHOUT_AST_GREP
            if matched:
                export_name = matched[0].get("export_name")
        if reason is None:
            continue
        item = {k: v for k, v in cit.items() if k != "column"}
        item.update(
            {
                "reason": reason,
                "expected_prefix": other,
                "export_name": export_name
                if isinstance(export_name, str) and export_name
                else None,
            }
        )
        findings.append(item)
    return findings, len(scanned), matched_count


# --------------------------------------------------------------------------
# Node kinds (--check-node-kinds)
# --------------------------------------------------------------------------


def _resolve_outside_cwd(command: str) -> str | None:
    """shutil.which with a CWD-shim guard. Returns the resolved path or None.

    shutil.which on Windows searches the current directory ahead of PATH,
    and CWD here may be a repository SKF does not control: a bare-name
    lookup resolving into CWD would execute a planted shim (e.g.
    ast-grep.cmd). Such a resolution is treated as not-found. Explicit
    paths supplied by callers (containing a separator) are honored as-is.
    Keep the code identical to the sibling guards in
    skf-merge-ccc-exclusions.py, skf-detect-tools.py,
    skf-qmd-classify-collections.py, skf-ccc-git-hygiene.py,
    skf-source-tree.py and skf-tessl-review.py
    (test/test-skf-verify-provenance-completeness.py pins it against
    skf-merge-ccc-exclusions.py).
    """
    resolved = shutil.which(command)
    if resolved is None:
        return None
    if os.sep in command or (os.altsep and os.altsep in command):
        return resolved
    resolved_dir = os.path.dirname(resolved)
    if resolved_dir:
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
        if os.path.normcase(os.path.abspath(resolved_dir)) == cwd:
            return None
    return resolved


def ast_grep_language(source_file: object) -> str | None:
    """The ast-grep language for `source_file`'s extension, or None."""
    if not isinstance(source_file, str) or not source_file.strip():
        return None
    ext = posixpath.splitext(normalize_path(source_file))[1].lower()
    return AST_GREP_LANGUAGES.get(ext)


def ast_grep_judges_kind(exe: str, language: str, kind: str, folder: str) -> str:
    """Ask ast-grep whether `kind` is a node kind of `language`.

    Runs one rule that matches only `kind` over an empty stdin: ast-grep
    parses the rule before it reads input and rejects a kind the grammar
    does not have. Returns "valid", "invalid" (the rule was rejected and the
    error names an invalid kind), "timeout", or "unknown" (a failed spawn or
    any other error, which proves nothing about the kind). `folder` holds
    the minimal sgconfig.yml passed with `--config` and is the working
    folder, so no other sgconfig.yml is read. The rule is JSON, which YAML
    reads as a flow mapping.
    """
    rule = json.dumps(
        {"id": "skf-node-kind", "language": language, "rule": {"kind": kind}}
    )
    config = os.path.join(folder, "sgconfig.yml")
    try:
        result = subprocess.run(
            [exe, "scan", "--config", config, "--inline-rules", rule, "--stdin"],
            input="",
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=NODE_KIND_TIMEOUT_SEC,
            cwd=folder,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode == 0:
        return "valid"
    if "invalid kind" in (result.stderr or "").lower():
        return "invalid"
    return "unknown"


def _judge_kinds(
    exe: str, pairs: list[tuple[str, str]]
) -> tuple[str, dict[tuple[str, str], str]]:
    """Ask ast-grep about each (language, kind) pair, in order.

    Returns (node_kind_check, verdicts): each verdict is "valid", "invalid"
    or the reason the pair went unjudged. ast-grep is first asked about a
    kind no grammar has; unless it answers "invalid", its answers cannot be
    read and the check is "skipped-unrecognized-ast-grep" with no verdicts.
    After one timeout the remaining pairs are not asked. When the temporary
    folder cannot be made or written, the pairs not yet asked go unjudged.
    """
    verdicts: dict[tuple[str, str], str] = {}
    try:
        with tempfile.TemporaryDirectory(
            prefix="skf-node-kind-", ignore_cleanup_errors=True
        ) as folder:
            with open(
                os.path.join(folder, "sgconfig.yml"), "w", encoding="utf-8"
            ) as fh:
                fh.write(MINIMAL_SGCONFIG)
            calibration = ast_grep_judges_kind(
                exe, pairs[0][0], BOGUS_NODE_KIND, folder
            )
            if calibration != "invalid":
                return "skipped-unrecognized-ast-grep", {}
            timed_out = False
            for language, kind in pairs:
                if timed_out:
                    verdicts[(language, kind)] = UNCHECKED_TIMEOUT
                    continue
                verdict = ast_grep_judges_kind(exe, language, kind, folder)
                if verdict == "timeout":
                    timed_out = True
                    verdict = UNCHECKED_TIMEOUT
                elif verdict == "unknown":
                    verdict = UNCHECKED_AST_GREP_ERROR
                verdicts[(language, kind)] = verdict
    except OSError:
        for pair in pairs:
            verdicts.setdefault(pair, UNCHECKED_TEMP_FOLDER)
    return "checked", verdicts


def _node_kind_item(
    index: int, entry: dict, kind: str, language: str, reason: str
) -> dict:
    name = entry.get("export_name")
    return {
        "export_name": name if isinstance(name, str) and name else None,
        "entry_index": index,
        "source_file": entry.get("source_file"),
        "source_line": entry.get("source_line"),
        "ast_node_type": kind,
        "language": language,
        "reason": reason,
    }


def check_node_kinds(prov: dict) -> tuple[list[dict], list[dict], dict]:
    """Check each ast-grep entry's `ast_node_type` against ast-grep itself.

    Returns (findings, unchecked, summary fields). `ERROR` and a kind that
    is not kind-shaped are judged without ast-grep, whatever the binary
    lookup finds; every other kind is asked once per (language, kind).
    """
    entries = prov.get("entries")
    entries = entries if isinstance(entries, list) else []
    findings: list[dict] = []
    unchecked: list[dict] = []
    pending: list[tuple[int, dict, str, str]] = []
    judged = 0
    skipped = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if _extraction_method(entry) not in AST_METHODS:
            continue
        kind = entry.get("ast_node_type")
        if not isinstance(kind, str) or not kind.strip():
            continue
        language = ast_grep_language(entry.get("source_file"))
        if language is None:
            skipped += 1
            continue
        if kind == ERROR_NODE_KIND:
            reason = NODE_KIND_ERROR
        elif not NODE_KIND_SHAPE.fullmatch(kind):
            reason = NODE_KIND_INVALID
        else:
            pending.append((index, entry, language, kind))
            continue
        judged += 1
        findings.append(_node_kind_item(index, entry, kind, language, reason))

    check = "checked"
    if pending:
        exe = _resolve_outside_cwd("ast-grep")
        if exe is None:
            check = "skipped-no-ast-grep"
        else:
            pairs = sorted({(lang, kind) for _, _, lang, kind in pending})
            check, verdicts = _judge_kinds(exe, pairs)
            if check == "checked":
                for index, entry, language, kind in pending:
                    verdict = verdicts[(language, kind)]
                    item = _node_kind_item(index, entry, kind, language, verdict)
                    if verdict == "valid":
                        judged += 1
                    elif verdict == "invalid":
                        judged += 1
                        item["reason"] = NODE_KIND_INVALID
                        findings.append(item)
                    else:
                        unchecked.append(item)

    def order(item: dict) -> tuple:
        return (item["export_name"] or "", str(item["source_file"]),
                item["entry_index"])

    findings.sort(key=order)
    unchecked.sort(key=order)
    summary = {
        "node_kind_check": check,
        "node_kinds_checked": judged,
        "node_kind_check_skipped": skipped,
        "node_kind_check_errors": len(unchecked),
        "node_kind_findings_count": len(findings),
    }
    return findings, unchecked, summary


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def resolve_source_root(prov: dict, override: str | None) -> Path | None:
    """Pick the source root for citation resolution.

    `--source-root` override wins; otherwise the provenance map's top-level
    `source_root`. Returns None when neither resolves to an on-disk dir.
    """
    candidate: str | None = None
    if override:
        candidate = override
    else:
        sr = prov.get("source_root")
        if isinstance(sr, str) and sr:
            candidate = sr
    if not candidate:
        return None
    root = Path(candidate)
    return root if root.is_dir() else None


def verify(
    metadata: dict,
    prov: dict,
    source_root: Path | None,
    skill_dir: Path | None = None,
    check_kinds: bool = False,
) -> dict:
    """Compute the completeness / orphan / stale / citation / node-kind
    report."""
    reexport_map = extract_reexport_map(prov)

    documented = extract_export_names(metadata)
    documented_canon = {canon(n, reexport_map) for n in documented}

    raw_entry_names = provenance_entry_names(prov)
    entry_canon = {canon(n, reexport_map) for n in raw_entry_names}

    missing = sorted(documented_canon - entry_canon)
    orphaned = sorted(entry_canon - documented_canon)

    stale: list[dict] = []
    citations_checked = 0
    line_check_skipped = 0
    if source_root is not None:
        cache = _SourceCache()
        entries = prov.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("export_name")
                if not isinstance(name, str) or not name:
                    continue
                sf = entry.get("source_file")
                sl = entry.get("source_line")
                line = _coerce_line(sl)
                # Only count a resolvable (non-null) citation as "checked".
                if isinstance(sf, str) and sf.strip() and line is not None:
                    citations_checked += 1
                reason = check_citation(sf, sl, source_root)
                item = {
                    "export_name": name,
                    "source_file": sf if isinstance(sf, str) else None,
                    "source_line": sl if isinstance(sl, int)
                    and not isinstance(sl, bool) else sl,
                }
                if reason is not None:
                    item["reason"] = reason
                    stale.append(item)
                    continue
                # The citation resolves (or is tolerated): check that the
                # line defines the export. A tolerated null or blank
                # citation has no line to check and is not counted.
                if (
                    not isinstance(sf, str)
                    or not sf.strip()
                    or not isinstance(line, int)
                ):
                    continue
                if not line_rule_applies(sf, entry.get("export_type")):
                    line_check_skipped += 1
                    continue
                matches = _definition_matches(sf, name, source_root, cache)
                if matches is None:
                    line_check_skipped += 1
                    continue
                defs, every = matches
                if line not in defs:
                    if line in every:
                        # The recorded line is an indented match the
                        # column-0 rule dropped: keep it, so the finding
                        # lists several lines and nobody auto-moves it.
                        defs = sorted(set(defs) | {line})
                    item["reason"] = STALE_LINE_NOT_DEFINITION
                    item["definition_lines"] = defs
                    stale.append(item)
        stale.sort(key=lambda s: (s["export_name"], s.get("source_file") or ""))

    citations: list[dict] = []
    skill_citations_scanned = 0
    skill_citations_matched = 0
    if skill_dir is not None:
        citations, skill_citations_scanned, skill_citations_matched = (
            check_skill_citations(prov, skill_dir)
        )

    node_kinds: list[dict] = []
    node_kinds_unchecked: list[dict] = []
    kind_summary: dict = {"node_kind_check": "not-requested"}
    if check_kinds:
        node_kinds, node_kinds_unchecked, kind_summary = check_node_kinds(prov)

    status = (
        "pass"
        if not (missing or orphaned or stale or citations or node_kinds)
        else "findings"
    )
    result: dict = {
        "status": status,
        "missing": missing,
        "orphaned": orphaned,
        "stale": stale,
        "citations": citations,
    }
    if check_kinds:
        result["node_kinds"] = node_kinds
        result["node_kinds_unchecked"] = node_kinds_unchecked
    result["summary"] = {
        "exports_checked": len(documented_canon),
        "entries_checked": len(raw_entry_names),
        "missing_count": len(missing),
        "orphaned_count": len(orphaned),
        "stale_count": len(stale),
        "citations_checked": citations_checked,
        "line_check_skipped": line_check_skipped,
        "stale_check": "checked"
        if source_root is not None
        else "skipped-no-source-root",
        "skill_citations_scanned": skill_citations_scanned,
        "skill_citations_matched": skill_citations_matched,
        "citation_findings_count": len(citations),
        "citation_check": "checked"
        if skill_dir is not None
        else "skipped-no-skill-dir",
        **kind_summary,
    }
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    meta_path = Path(args.metadata)
    prov_path = Path(args.provenance)
    if not meta_path.is_file():
        print(f"error: metadata not found: {meta_path}", file=sys.stderr)
        return 2
    if not prov_path.is_file():
        print(f"error: provenance map not found: {prov_path}", file=sys.stderr)
        return 2
    try:
        metadata = load_json_object(meta_path, "metadata")
        prov = load_json_object(prov_path, "provenance map")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    skill_dir: Path | None = None
    if args.skill_dir is not None:
        skill_dir = Path(args.skill_dir)
        if not skill_dir.exists():
            print(f"error: skill dir not found: {skill_dir}", file=sys.stderr)
            return 2
        if not skill_dir.is_dir():
            print(
                f"error: skill dir is not a directory: {skill_dir}",
                file=sys.stderr,
            )
            return 2
        if not (skill_dir / "SKILL.md").is_file():
            print(
                f"error: skill dir has no SKILL.md: {skill_dir}", file=sys.stderr
            )
            return 2

    source_root = resolve_source_root(prov, args.source_root)
    if args.verbose:
        if source_root is None:
            print(
                "verbose: no source root resolved — skipping stale-citation "
                "check (completeness + orphan diffs only)",
                file=sys.stderr,
            )
        else:
            print(f"verbose: resolving citations under {source_root}", file=sys.stderr)

    try:
        result = verify(
            metadata, prov, source_root, skill_dir, args.check_node_kinds
        )
    except Exception as exc:  # noqa: BLE001 - exit 2, never read as findings
        detail = " ".join(str(exc).split())
        print(
            f"error: verification failed: {type(exc).__name__}: {detail}",
            file=sys.stderr,
        )
        return 2

    out_text = json.dumps(result, indent=2) + "\n"
    if args.output and args.output != "-":
        Path(args.output).write_text(out_text, encoding="utf-8")
    else:
        sys.stdout.write(out_text)

    return 0 if result["status"] == "pass" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-verify-provenance-completeness",
        description=(
            "Cross-reference documented exports (metadata.json) against "
            "provenance-map entries: completeness, orphans, stale or "
            "non-definition file:line citations, (with --skill-dir) "
            "citation prefixes and (with --check-node-kinds) ast-grep node "
            "kinds, emitting findings as JSON."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "verify",
        help=(
            "emit provenance completeness / orphan / stale-citation / "
            "citation-prefix / node-kind findings"
        ),
    )
    p.add_argument("--metadata", required=True, help="path to metadata.json")
    p.add_argument(
        "--provenance", required=True, help="path to provenance-map.json"
    )
    p.add_argument(
        "--source-root",
        default=None,
        help=(
            "source tree root for citation resolution; overrides the "
            "provenance map's source_root. Stale check is skipped when no "
            "root resolves on disk."
        ),
    )
    p.add_argument(
        "--skill-dir",
        default=None,
        help=(
            "skill package folder holding a SKILL.md; scans it and "
            "references/**/*.md for [AST:]/[SRC:] citations and checks each "
            "prefix against the provenance entry it cites. Citation check is "
            "skipped when absent."
        ),
    )
    p.add_argument(
        "--check-node-kinds",
        action="store_true",
        help=(
            "ask the ast-grep CLI whether each ast-grep entry's ast_node_type "
            "is a node kind of its file's language; skipped when ast-grep is "
            "not found."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="write JSON to this file instead of stdout ('-' for stdout)",
    )
    p.add_argument(
        "--verbose", action="store_true", help="diagnostics to stderr"
    )
    p.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
