#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Locate where a skill describes each export, each example call to it, and whether the call awaits it.

coherence-check.md §2.5 (naive mode) raises a High finding when a skill
describes an export as async and its examples never await it, or describes
it as sync and an example awaits it. What a description asserts about an
export is the model's call, never a keyword's: "`readFileSync` is the sync
counterpart of the async `readFile`" holds the word `async` and says that
`readFileSync` is sync. This script does only the part with one correct
answer per input and judges no meaning. For each export name it lists:

- descriptions[]: where SKILL.md and references/**/*.md describe the
  export, outside the frontmatter, fenced code and HTML comments: a heading
  that names it (bare or in code), with the prose of its section, and each
  table row, list item or paragraph that names it in an inline code span.
  Within a section whose heading names the export, nothing else is listed
  for that export: the section text holds it. Each line of fenced code
  that declares the export (`def`, `function`, `fn`, a typed declaration,
  a signature line) is listed too, as kind "signature". An entry carries
  the headings above it (`section`), a table row its table's header row
  (`header`), and its text, cut at a fixed length (`truncated`).
- calls[]: each call to the export in fenced code: the name, as a whole
  identifier, followed by `(` (a generic `<...>` or a `::` may stand
  between), with any receiver before it (`client.fetchData(`), and not a
  declaration. Comments and string literals are blanked first in the
  languages this script knows by the fence's info string; a block tagged
  as data or output (`json`, `yaml`, `text`, `console` ...) holds none.

A call is `awaited` when `await` stands before it (through its receiver:
`await client.fetchData(...)`), `.await` follows it (Rust), an asynchronous
loop or context manager consumes it (`async for row in stream(...)`, `async
with session(...)`, `for await (const row of stream(...))`), or it sits in
the arguments of a call that is itself awaited or is an event-loop runner
(`await Promise.all([fetchData(a)])`, `asyncio.run(fetch_data())`), without
crossing into a function body. `chainedMember` names the member read or
called on its result right after it (`then`, `catch`, `join`, `get`), else
null: whether that waits for the result is the caller's call.

Name match: the name as a fixed string, case-sensitive, never inside a
longer identifier (the Export match rule of skf-scan-skill-md-structure.py
usage-scope). A qualified name (`client.fetch`, `Store::load`) matches only
as written, except that a declaration also matches its last part
(`def fetch(`): a declaration never carries the qualifier.

Line model: UTF-8 with a leading byte order mark dropped, split on `\\n`
(a `\\r\\n` pair loses its `\\r`), so each `line` matches `grep -n`. The
frontmatter is a leading `---` ... `---` block. A fence opens on three or
more backticks or tildes (any indent) and closes on the same character
repeated at least as often with nothing after it; an unclosed fence runs to
the end of the file. A heading is an ATX heading (at most three spaces of
indent); its section runs to the next heading of the same or a higher level.

Input (one JSON object):
  {
    "names": ["fetchData", "Client.fetch", ...],  # the §1 inventory's function and method names
    "skillPackagePath": "/path/to/skill"          # holds SKILL.md and references/
  }

Output (stdout, one object):
  {
    "skillPackagePath": "...",
    "files": ["SKILL.md", "references/api.md"],  # read, in this order
    "exports": [                                  # each name with at least one call, in input order
      {
        "name": "fetchData",
        "descriptionCount": 3,                    # all found; descriptions[] holds the first 12
        "descriptions": [{"file", "line", "endLine", "kind", "section", "header", "text", "truncated"}],
        "calls": [{"file", "line", "fence", "language", "awaited", "chainedMember", "text"}],
        "callCount": 2,
        "awaitedCount": 1
      }
    ],
    "notCalled": ["parseConfig"],                 # names no example calls
    "summary": {"names": N, "called": N, "notCalled": N}
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

`kind` is "heading", "table-row", "list-item", "paragraph" or "signature".
Lines are 1-based; `fence` is the line of the call's opening fence.

CLI usage (mirrors verify-declared-numerator.py):
  uv run locate-export-segments.py '<JSON>'                  # positional
  uv run locate-export-segments.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run locate-export-segments.py --stdin  # piped input

Exit codes:
  0  segments emitted
  1  no input / input could not be parsed as JSON
  2  input parsed but schema invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_DESCRIPTIONS = 12
TEXT_CAP = 600
SECTION_TEXT_CAP = 1200
LINE_TEXT_CAP = 200
SECTION_PATH_CAP = 200

# The identifier characters of skf-scan-skill-md-structure.py's Export match
# (its _IDENT_CHARS): any Unicode letter, digit or `_`, and `$`.
IDENT_CHARS = r"\w$"
IDENT_RE = re.compile(f"[{IDENT_CHARS}]")
WORD_BEFORE_RE = re.compile(f"([{IDENT_CHARS}]+)$")

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
CLOSING_HASHES_RE = re.compile(r"(?:^|[ \t]+)#+$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])(?:[ \t]+|$)")
TABLE_ROW_RE = re.compile(r"^\s*\|")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
GENERIC_OR_PATH = r"(?:[ \t]*::)?(?:[ \t]*<[^<>()\n]*(?:<[^<>()\n]*>[^<>()\n]*)*>)?"
AFTER_CALL_RE = re.compile(f"\\s*\\??\\.\\s*((?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*)")
AWAIT_BEFORE_RE = re.compile(f"(?<![{IDENT_CHARS}])await$")
AWAIT_AFTER_RE = re.compile(f"\\s*\\.\\s*await(?![{IDENT_CHARS}])")
# An expression an asynchronous loop or context manager consumes: `async for
# x in NAME(...)`, `async with NAME(...)`, `for await (const x of NAME(...))`,
# `await foreach (var x in NAME(...))`. Matched against its line up to it.
ASYNC_CONSUMER_RE = re.compile(
    f"(?<![{IDENT_CHARS}])(?:async[ \\t]+for[ \\t].*[ \\t]in|async[ \\t]+with(?:[ \\t].*,)?"
    f"|for[ \\t]+await[ \\t]*\\(.*[ \\t]of|await[ \\t]+foreach[ \\t]*\\(.*[ \\t]in)[ \\t]*$")

# Info strings of blocks that hold data or output, never calls.
DATA_LANGUAGES = frozenset({
    "json", "jsonc", "json5", "yaml", "yml", "toml", "ini", "xml", "csv", "tsv", "text", "txt",
    "plaintext", "plain", "mermaid", "markdown", "md", "log", "output", "diff", "console",
})
# Comment and string syntax by info string. Code under an unknown or missing
# info string is read as written.
HASH_COMMENTS = frozenset({
    "python", "py", "python3", "ruby", "rb", "sh", "bash", "shell", "zsh", "fish", "r", "perl", "pl",
    "elixir", "ex", "exs", "coffee", "coffeescript", "julia", "jl", "powershell", "ps1", "pwsh",
})
JS_FAMILY = frozenset({"js", "javascript", "jsx", "mjs", "cjs", "ts", "typescript", "tsx", "mts", "cts",
                       "vue", "svelte"})
C_FAMILY = frozenset({"java", "cs", "csharp", "c#", "c", "h", "cpp", "c++", "cc", "hpp", "dart", "php"})
SLASH_COMMENTS = JS_FAMILY | C_FAMILY | frozenset({
    "rust", "rs", "go", "golang", "kotlin", "kt", "kts", "swift", "scala", "groovy", "zig",
})
# `'` opens a string here; elsewhere it opens a character literal or a Rust
# lifetime, both read as written.
SINGLE_QUOTE_STRINGS = HASH_COMMENTS | JS_FAMILY | frozenset({"php", "dart", "groovy"})
TEMPLATE_STRINGS = JS_FAMILY | frozenset({"go", "golang"})
TRIPLE_QUOTES = {
    "python": ('"""', "'''"), "py": ('"""', "'''"), "python3": ('"""', "'''"),
    "kotlin": ('"""',), "kt": ('"""',), "kts": ('"""',), "swift": ('"""',), "scala": ('"""',),
    "java": ('"""',), "groovy": ('"""', "'''"), "dart": ('"""', "'''"), "julia": ('"""',), "jl": ('"""',),
}
# Languages where `Type name(...)` declares `name`: a word other than an
# expression word right before the name is a return type there. Untagged
# code reads the same way, since it is most often a signature.
TYPED_DECLARATIONS = C_FAMILY | frozenset({"groovy", ""})
# A `{` after a call at the start of a line opens a method body here; in
# Kotlin, Swift or Ruby it can be a trailing closure of a call.
BRACE_DECLARATIONS = JS_FAMILY | C_FAMILY

# A word right before the name that declares it.
DECLARATION_WORDS = frozenset({
    "def", "function", "fn", "func", "fun", "sub", "macro", "class", "interface", "struct", "enum",
    "trait", "type", "record", "object", "protocol", "actor", "typealias", "impl",
    "async", "static", "public", "private", "protected", "internal", "override", "abstract", "virtual",
    "readonly", "get", "set", "export", "default", "pub", "unsafe", "extern", "inline", "final", "open",
    "suspend", "operator", "infix", "tailrec", "external", "native", "synchronized", "sealed", "data",
})
# A word that can stand right before a call, and before a `(` that only groups.
EXPRESSION_WORDS = frozenset({
    "await", "return", "yield", "throw", "raise", "new", "else", "in", "of", "case", "typeof", "void",
    "delete", "not", "and", "or", "is", "if", "elif", "while", "until", "unless", "assert", "print",
    "from", "do", "then", "go", "defer", "try", "when", "with", "lambda", "puts", "echo", "instanceof",
    "as", "match", "loop", "del", "move", "ref", "box", "using", "lock",
})
# Callees that run the coroutine they are given until it completes: any
# `run_until_complete` or `block_on`, and `run` of these event loops.
RUNNERS = frozenset({"run_until_complete", "block_on"})
RUN_OWNERS = frozenset({"asyncio", "trio", "anyio"})
BRACKETS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = {v: k for k, v in BRACKETS.items()}


def make_error(message):
    return {"error": message, "code": "INVALID_INPUT"}


def _cap(text, cap):
    return (text[:cap], True) if len(text) > cap else (text, False)


# --------------------------------------------------------------------------
# Reading the skill
# --------------------------------------------------------------------------


def _split_lines(text):
    """Split on newlines only, so line numbers match `grep -n`."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def skill_files(root):
    """(relative POSIX path, lines) of SKILL.md, then of each references/**/*.md in path order."""
    root = Path(root)
    paths = [root / "SKILL.md"] if (root / "SKILL.md").is_file() else []
    refs = root / "references"
    if refs.is_dir():
        paths += sorted((p for p in refs.rglob("*.md") if p.is_file()),
                        key=lambda p: p.relative_to(root).as_posix())
    return [(p.relative_to(root).as_posix(), _split_lines(p.read_bytes().decode("utf-8-sig", errors="replace")))
            for p in paths]


def _frontmatter_end(lines):
    """Index of the first body line, past a leading `---` ... `---` block."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def _fenced_blocks(lines, start):
    """(opening fence, closing fence, info string) of each fenced block, and a per-line code flag.

    An unclosed fence runs to the end of the file (its closing index is
    len(lines)). A backtick line whose info string holds a backtick is
    inline code, not a fence.
    """
    blocks, code = [], [False] * len(lines)
    fence = None
    for i in range(start, len(lines)):
        m = FENCE_RE.match(lines[i])
        if fence is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = (m.group(1)[0], len(m.group(1)), i, m.group(2).strip())
                code[i] = True
            continue
        code[i] = True
        if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not m.group(2).strip():
            blocks.append((fence[2], i, fence[3]))
            fence = None
    if fence is not None:
        blocks.append((fence[2], len(lines), fence[3]))
    return blocks, code


def _language(info):
    """The info string's first word, lower case: `ts title="x"` and `{.ts}` give `ts`."""
    words = info.split()
    return words[0].strip("{}").lstrip(".").lower() if words else ""


def _inline_code(line):
    """The text of each inline code span: a backtick run closed by an equal run."""
    spans, i, n = [], 0, len(line)
    while i < n:
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run, k, close = j - i, j, -1
        while k < n:
            if line[k] != "`":
                k += 1
                continue
            m = k
            while m < n and line[m] == "`":
                m += 1
            if m - k == run:
                close = k
                break
            k = m
        if close == -1:
            i = j
            continue
        spans.append(line[j:close])
        i = close + run
    return spans


def _bounded(name):
    """Regex for `name` as a fixed string never inside a longer identifier."""
    body = re.escape(name)
    if IDENT_RE.match(name[0]):
        body = f"(?<![{IDENT_CHARS}])" + body
    if IDENT_RE.match(name[-1]):
        body += f"(?![{IDENT_CHARS}])"
    return re.compile(body)


def _call_pattern(name):
    return re.compile(_bounded(name).pattern + GENERIC_OR_PATH + r"[ \t]*\(")


def _last_part(name):
    """`fetch` for `client.fetch` or `Store::fetch`; None for a plain name."""
    part = re.split(r"\.|::|#|->", name)[-1]
    return part if part and part != name else None


# --------------------------------------------------------------------------
# Descriptions in prose
# --------------------------------------------------------------------------


def _prose(lines, start, code):
    """Headings and prose blocks outside the frontmatter, fenced code and HTML comments.

    A heading is (index, level, text, headings above it). A block is a
    table row, a list item (with its continuation lines) or a paragraph:
    {kind, start, end (inclusive), path (headings above it), header (a
    table row's header row), code (the text of its inline code spans)}.
    """
    headings, blocks = [], []
    stack = []
    current = None
    header = None
    in_comment = False

    def close():
        nonlocal current
        if current is not None:
            blocks.append(current)
            current = None

    def block(kind, i, path, table_header=None):
        return {"kind": kind, "start": i, "end": i, "path": path, "header": table_header,
                "code": "\n".join(_inline_code(lines[i]))}

    for i in range(start, len(lines)):
        line, stripped = lines[i], lines[i].strip()
        if code[i] or not stripped:
            close()
            header = None
            continue
        if in_comment:
            in_comment = "-->" not in line
            continue
        if stripped.startswith("<!--"):
            close()
            in_comment = "-->" not in stripped[4:]
            continue
        m = HEADING_RE.match(line)
        if m:
            close()
            header = None
            level = len(m.group(1))
            text = CLOSING_HASHES_RE.sub("", m.group(2) or "").strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            headings.append((i, level, text, [t for _, t in stack]))
            stack.append((level, text))
            continue
        path = [t for _, t in stack]
        if TABLE_ROW_RE.match(line):
            close()
            if TABLE_SEPARATOR_RE.match(line):
                continue
            blocks.append(block("table-row", i, path, header))
            header = header or stripped
            continue
        header = None
        if LIST_ITEM_RE.match(line):
            close()
            current = block("list-item", i, path)
        elif current is None:
            current = block("paragraph", i, path)
        else:
            current["end"] = i
            current["code"] += "\n" + "\n".join(_inline_code(line))
    close()
    return headings, blocks


def _heading_path(headings, index):
    """The headings above line `index`, outermost first."""
    path = []
    for idx, _, text, above in headings:
        if idx >= index:
            break
        path = above + [text]
    return path


def _section_end(headings, pos, total):
    """Exclusive end of the section of headings[pos]."""
    level = headings[pos][1]
    for idx, lvl, _, _ in headings[pos + 1:]:
        if lvl <= level:
            return idx
    return total


def _entry(rel, line, end_line, kind, path, header, text, cap):
    text, truncated = _cap(text, cap)
    return {"file": rel, "line": line, "endLine": end_line, "kind": kind,
            "section": _cap(" > ".join(path), SECTION_PATH_CAP)[0], "header": header,
            "text": text, "truncated": truncated}


def describe(rel, lines, code, headings, blocks, pattern):
    """The heading, table-row, list-item and paragraph entries of one file for one export."""
    found, covered = [], []
    for pos, (idx, _, text, above) in enumerate(headings):
        if any(a <= idx < b for a, b in covered) or not pattern.search(text):
            continue
        end = _section_end(headings, pos, len(lines))
        covered.append((idx, end))
        body = [lines[i].strip() for i in range(idx + 1, end)
                if not code[i] and lines[i].strip() and not HEADING_RE.match(lines[i])
                and not lines[i].strip().startswith("<!--") and not TABLE_SEPARATOR_RE.match(lines[i])]
        found.append(_entry(rel, idx + 1, end, "heading", above, None, " ".join([text] + body), SECTION_TEXT_CAP))
    for block in blocks:
        if any(a <= block["start"] < b for a, b in covered) or not pattern.search(block["code"]):
            continue
        text = " ".join(lines[i].strip() for i in range(block["start"], block["end"] + 1))
        found.append(_entry(rel, block["start"] + 1, block["end"] + 1, block["kind"], block["path"],
                            block["header"], text, TEXT_CAP))
    return found


# --------------------------------------------------------------------------
# Calls and declarations in fenced code
# --------------------------------------------------------------------------


def mask_code(code, language):
    """The code with comments and string literals blanked, every offset and newline kept.

    Only a language this script knows is masked: code under an unknown or
    missing info string is returned as written.
    """
    hash_comments = language in HASH_COMMENTS
    slash_comments = language in SLASH_COMMENTS
    if not (hash_comments or slash_comments):
        return code
    quotes = {'"'}
    if language in SINGLE_QUOTE_STRINGS:
        quotes.add("'")
    if language in TEMPLATE_STRINGS:
        quotes.add("`")
    triples = TRIPLE_QUOTES.get(language, ())
    out, n, i = list(code), len(code), 0
    while i < n:
        c = code[i]
        triple = next((t for t in triples if code.startswith(t, i)), None)
        if (hash_comments and c == "#") or (slash_comments and code.startswith("//", i)):
            j = code.find("\n", i)
            j = n if j == -1 else j
        elif slash_comments and code.startswith("/*", i):
            j = code.find("*/", i + 2)
            j = n if j == -1 else j + 2
        elif triple:
            j = code.find(triple, i + 3)
            j = n if j == -1 else j + 3
        elif c in quotes:
            j = i + 1
            while j < n and code[j] != c and (c == "`" or code[j] != "\n"):
                j += 2 if code[j] == "\\" else 1
            j = min(j + 1, n)
        else:
            i += 1
            continue
        for k in range(i, j):
            if out[k] != "\n":
                out[k] = " "
        i = j
    return "".join(out)


def _matching_close(text, open_idx):
    stack = []
    for i in range(open_idx, len(text)):
        c = text[i]
        if c in BRACKETS:
            stack.append(c)
        elif c in CLOSERS:
            if not stack or stack.pop() != CLOSERS[c]:
                return None
            if not stack:
                return i
    return None


def _matching_open(text, close_idx):
    stack = []
    for i in range(close_idx, -1, -1):
        c = text[i]
        if c in CLOSERS:
            stack.append(c)
        elif c in BRACKETS:
            if not stack or stack.pop() != BRACKETS[c]:
                return None
            if not stack:
                return i
    return None


def _skip_space_back(text, i):
    while i > 0 and text[i - 1] in " \t\n":
        i -= 1
    return i


def _chain_start(text, pos):
    """Start of the expression whose last member starts at `pos`: `client.api.` in `client.api.name`."""
    i = pos
    while True:
        k = _skip_space_back(text, i)
        accessor = next((a for a in ("?.", "!.", "::", "->", ".") if text.endswith(a, 0, k)), None)
        if accessor is None:
            return i
        k = _skip_space_back(text, k - len(accessor))
        start = k
        while start > 0 and text[start - 1] in ")]":
            opened = _matching_open(text, start - 1)
            if opened is None:
                break
            start = opened
        word = WORD_BEFORE_RE.search(text, 0, start)
        if word:
            start = word.start()
        if start == k:
            return i
        i = start


def _awaited_at(text, start):
    """True when `await` stands right before the expression that starts at `start`, or an
    asynchronous loop or context manager consumes it."""
    if AWAIT_BEFORE_RE.search(text, 0, _skip_space_back(text, start)):
        return True
    return bool(ASYNC_CONSUMER_RE.search(text[text.rfind("\n", 0, start) + 1:start]))


def _is_runner(callee):
    """True for `asyncio.run`, `loop.run_until_complete`, `rt.block_on` and the like."""
    parts = [p for p in re.split(r"\.|::", callee) if p]
    if not parts:
        return False
    if parts[-1] == "run":
        return len(parts) >= 2 and parts[-2] in RUN_OWNERS
    return parts[-1] in RUNNERS


def _opens_body(text, brace_idx):
    """True when the `{` at brace_idx opens a function or statement body, not an object literal."""
    k = _skip_space_back(text, brace_idx)
    return k > 0 and (text[k - 1] in ")>" or bool(IDENT_RE.match(text[k - 1])))


def _enclosing_awaits(text, start):
    """True when a call around the expression at `start` is awaited or runs it, within one function body."""
    i, depth = start, 0
    while i > 0:
        i -= 1
        c = text[i]
        if c in CLOSERS:
            depth += 1
        elif c in BRACKETS:
            if depth:
                depth -= 1
            elif c == "{" and _opens_body(text, i):
                return False
            elif c == "(":
                k = _skip_space_back(text, i)
                word = WORD_BEFORE_RE.search(text, 0, k)
                if word and word.group(1) not in EXPRESSION_WORDS:
                    expr = _chain_start(text, word.start())
                    if _is_runner(re.sub(r"\s+", "", text[expr:k])):
                        return True
                else:
                    expr = i  # a grouping `(`: `await (fetch())`
                close = _matching_close(text, i)
                if _awaited_at(text, expr) or (close is not None and AWAIT_AFTER_RE.match(text, close + 1)):
                    return True
                i = expr
    return False


def _closes_generic(tail):
    """True when `tail` ends in a generic type such as `Task<Data>`."""
    depth = 0
    for i in range(len(tail) - 1, -1, -1):
        c = tail[i]
        if c == ">":
            depth += 1
        elif c == "<":
            depth -= 1
            if depth == 0:
                return i > 0 and bool(IDENT_RE.match(tail[i - 1]))
        elif c in "()=;{}":
            return False
    return False


def _is_declaration(text, line_start, chain, name_start, close, language):
    """True when the name at name_start is declared there, not called."""
    tail = text[line_start:chain].rstrip(" \t")
    if chain == name_start and tail:
        word = WORD_BEFORE_RE.search(tail)
        w = word.group(1) if word else ""
        if w in DECLARATION_WORDS:
            return True
        if tail.endswith("*") and tail[:-1].rstrip(" \t").endswith("function"):
            return True  # `function* name(`
        if language in TYPED_DECLARATIONS:
            if w and (w not in EXPRESSION_WORDS or w == "void"):
                return True  # a return type: `Data name(`, `void name(`
            if tail.endswith("[]") or (tail.endswith(">") and not tail.endswith(("=>", "->"))
                                       and _closes_generic(tail)):
                return True  # `int[] name(`, `Task<Data> name(`
        if tail.endswith(")"):
            opened = _matching_open(text, line_start + len(tail) - 1)
            if opened is not None and text[line_start:opened].rstrip().endswith("func"):
                return True  # Go: `func (c *Client) Name(`
    if not tail and close is not None:
        after = text[close + 1:].lstrip(" \t")
        if after.startswith("->") or (after.startswith(":") and not after.startswith(("::", ":="))):
            return True  # a signature: `name(url: string): Data`, `name(url) -> Data`
        if after.startswith("{") and language in BRACE_DECLARATIONS:
            return True  # a method body: `name(url) {`
    return False


def scan_block(rel, lines, opening, closing, info, patterns):
    """{name: {"calls": [...], "signatures": [...]}} for one fenced block.

    `patterns` maps each name to (its call regex, the regexes of the other
    forms a declaration of it may take).
    """
    language = _language(info)
    found = {name: {"calls": [], "signatures": []} for name in patterns}
    if language in DATA_LANGUAGES:
        return found
    body = lines[opening + 1:closing]
    text = mask_code("\n".join(body), language)
    for name, (call_re, declaration_res) in patterns.items():
        seen = set()
        for regex in (call_re, *declaration_res):
            for m in regex.finditer(text):
                name_start, paren = m.start(), m.end() - 1
                if name_start in seen:
                    continue
                seen.add(name_start)
                close = _matching_close(text, paren)
                chain = _chain_start(text, name_start)
                line_start = text.rfind("\n", 0, name_start) + 1
                row = text.count("\n", 0, name_start)
                if _is_declaration(text, line_start, chain, name_start, close, language):
                    found[name]["signatures"].append({"line": opening + row + 2, "text": body[row].strip()})
                    continue
                if regex is not call_re:
                    continue  # the last part of a qualified name counts only as a declaration
                awaited, chained = _awaited_at(text, chain), None
                if close is not None:
                    if AWAIT_AFTER_RE.match(text, close + 1):
                        awaited = True
                    elif member := AFTER_CALL_RE.match(text, close + 1):
                        chained = member.group(1)
                found[name]["calls"].append({
                    "file": rel, "line": opening + row + 2, "fence": opening + 1, "language": language or None,
                    "awaited": awaited or _enclosing_awaits(text, chain), "chainedMember": chained,
                    "text": _cap(body[row].strip(), LINE_TEXT_CAP)[0],
                })
    return found


# --------------------------------------------------------------------------
# Locate
# --------------------------------------------------------------------------


def _validate(inp):
    if not isinstance(inp, dict):
        return "Input must be a JSON object"
    if not isinstance(inp.get("names"), list):
        return "names must be a list of export names"
    path = inp.get("skillPackagePath")
    if not isinstance(path, str) or not path:
        return "skillPackagePath is required: the folder that holds SKILL.md and references/"
    if not Path(path).is_dir():
        return f"skillPackagePath is not a folder: {path}"
    return None


def locate(inp):
    """Pure location over SKILL.md and references/**/*.md under skillPackagePath."""
    err = _validate(inp)
    if err:
        return make_error(err)
    names = list(dict.fromkeys(n for n in inp["names"] if isinstance(n, str) and n.strip()))
    bounded = {name: _bounded(name) for name in names}
    patterns = {name: (_call_pattern(name), [_call_pattern(p)] if (p := _last_part(name)) else [])
                for name in names}
    files = skill_files(inp["skillPackagePath"])
    descriptions = {name: [] for name in names}
    calls = {name: [] for name in names}
    for rel, lines in files:
        start = _frontmatter_end(lines)
        fenced, code = _fenced_blocks(lines, start)
        headings, blocks = _prose(lines, start, code)
        per_file = {name: describe(rel, lines, code, headings, blocks, bounded[name]) for name in names}
        for opening, closing, info in fenced:
            for name, got in scan_block(rel, lines, opening, closing, info, patterns).items():
                calls[name] += got["calls"]
                per_file[name] += [_entry(rel, s["line"], s["line"], "signature",
                                          _heading_path(headings, s["line"] - 1), None, s["text"], LINE_TEXT_CAP)
                                   for s in got["signatures"]]
        for name in names:
            descriptions[name] += sorted(per_file[name], key=lambda e: e["line"])
    exports = [{
        "name": name,
        "descriptionCount": len(descriptions[name]),
        "descriptions": descriptions[name][:MAX_DESCRIPTIONS],
        "calls": calls[name],
        "callCount": len(calls[name]),
        "awaitedCount": sum(1 for c in calls[name] if c["awaited"]),
    } for name in names if calls[name]]
    not_called = [name for name in names if not calls[name]]
    return {
        "skillPackagePath": inp["skillPackagePath"],
        "files": [rel for rel, _ in files],
        "exports": exports,
        "notCalled": not_called,
        "summary": {"names": len(names), "called": len(exports), "notCalled": len(not_called)},
    }


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="locate-export-segments",
        description=(
            "Locate where a skill describes each export and each example call to it, and "
            "whether the call awaits it (coherence-check.md §2.5). It judges no meaning: the "
            "caller decides what each description asserts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run locate-export-segments.py "
            "'{\"names\":[\"fetchData\"],\"skillPackagePath\":\"/path/to/skill\"}'"
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("json_input", nargs="?",
                     help="JSON object as a positional argument (single-quote it on the shell).")
    src.add_argument("--json-input", dest="json_input_flag",
                     help="JSON object passed via flag (overrides positional).")
    src.add_argument("--stdin", action="store_true", help="Read the JSON object from stdin.")
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print("error: no input provided (positional arg, --json-input, or --stdin)", file=sys.stderr)
        return 1
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
        return 1
    result = locate(data)
    print(json.dumps(result, indent=2))
    return 2 if result.get("code") == "INVALID_INPUT" else 0


if __name__ == "__main__":
    sys.exit(main())
