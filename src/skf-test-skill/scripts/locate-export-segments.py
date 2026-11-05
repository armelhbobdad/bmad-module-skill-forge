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
  `receiver` is the expression before the name and its accessor
  (`client.api` in `client.api.fetchData(`), null when none stands there,
  as the blanked code holds it: whitespace beside an accessor, a bracket or
  a comma dropped, any other run cut to one space, and a non-null `!!` or
  `!` dropped.

A method given with its `owner` (the class or namespace the skill documents
it on) is called only on that owner. A receiver names an owner when its
last member, or the callee of its last call, is the owner's last part, in
any case (`client.messages` names `Messages`), and, when both have several
parts, the owner's parts are the receiver's last ones (`other_lib.agents`
does not name `cognee.agents`). A trailing `new` is dropped
(`UuidGenerator::new()`, Ruby's `UuidGenerator.new`), and so are an
owner's type parameters (`Repository` for `Repository<T>`). Each match of
the method's name is classed by its receiver (`receiverMatch`):

- "owner": the receiver names the owner (`cognee.agents.get(`,
  `coco.App(...).update(`).
- "bound": the receiver is one identifier whose last binding on a line
  before the call, in the same fenced block, is to the owner. Only a
  constructor-like form binds: `x = Owner(...)`, `x = await Owner(...)`,
  `x = new Owner(...)`, `x = Owner::new(...)`, `x = Owner.new`,
  `x := Owner{`, an annotation `x: Owner`, `with Owner(...) as x`, a Java-
  or C#-style `Owner x =` and Go's `var x Owner` or `var x *Owner`. Any
  other assignment (`agent = await cognee.agents.create(n)`, the result of
  a member call) binds the identifier to nothing, and an assignment in an
  argument list (`f(gen=UuidGenerator())`) is no binding.
- "other": the receiver names, or its binding is to, another owner the
  input lists. It is no call of the method, only counted
  (`otherReceiverCount`).
- "unknown": no receiver (`get(...)`: an import or an implicit `this` may
  tie it, the text does not), or any other one (`settings.get(`,
  `self.gen.next_uuid(`). The call cannot be tied to the owner, so it goes
  to `unverifiedCalls[]`, never to calls[].

A method no call is tied to is in `notCalled[]`, written `owner.name`, and
its unverified calls in `notCalledUnverified[]`. A declaration is an owned
method's only on its owner or a variable bound to it, inside the body of
its class (`class UuidGenerator:` ... `def next_uuid(self)`), or on a Go
receiver of its type (`func (g *UuidGenerator) next_uuid(`): neither
`cognee.config.get(key: str)` nor a free `def get(` is `agents.get`'s. Its
descriptions that name the owner come first, before the cap. A name given
without an owner is matched on any receiver, and its calls carry a null
`receiverMatch`.

A call is `awaited` when `await` stands before it (through its receiver:
`await client.fetchData(...)`), `.await` or `?.await` follows it (Rust), an asynchronous
loop or context manager consumes it (`async for row in stream(...)`, `async
with session(...)`, `for await (const row of stream(...))`), or it sits in
the arguments of a call that is itself awaited or is an event-loop runner
(`await Promise.all([fetchData(a)])`, `asyncio.run(fetch_data())`), without
crossing into a function body. `chainedMember` names the member read or
called on its result right after it (`then`, `catch`, `join`, `get`), else
null: whether that waits for the result is the caller's call.

`awaitedVia` says how an awaited call is awaited, null when it is not:

- "direct": the await applies to the call itself (`directlyAwaited`):
  `.await` follows it, or `await` stands before it with nothing applied to
  its result (`await client.fetchData(...)`) but a member that waits for an
  awaitable (`then`, `catch`, `finally`, `ConfigureAwait`), or it alone
  fills the groups that `await` stands before (`await ((fetchData(x)))`,
  `await (fetchData(x) as T)`) and nothing follows them but the end of the
  statement, of a list or of a bracket.
- "chain": the await applies to an expression the call starts or sits in:
  a member, subscript or call applied to its result
  (`await use_context(e).embed(t)`, `await fetchData(x)[0]`) or a group
  around it (`await (fetchData(x) or other())`).
- "consumer": an asynchronous loop or context manager consumes it.
- "argument" or "runner": it sits in the arguments of an awaited call, or of
  an event-loop runner; `enclosingCallee` names that callee, whitespace
  removed (`asyncio.gather`, `Promise.all`, `asyncio.run`), else null.

A backslash continuation counts as whitespace throughout.

Name match: the name as a fixed string, case-sensitive, never inside a
longer identifier (the Export match rule of skf-scan-skill-md-structure.py
usage-scope). A qualified name (`client.fetch`, `Store::load`) matches only
as written, except that a declaration also matches its last part
(`def fetch(`): a declaration never carries the qualifier.

Annotated parameters: in a block tagged Python, the JavaScript family,
Kotlin or Scala, an argument list that holds an annotated parameter
(`name: Type`; `name?: Type` in the JavaScript family; `*args: T`,
`...rest: T`) is a signature, with or without a receiver:
`get(key: str, reveal_secrets: bool = False)`. A lambda argument (`lambda
a, b: a + b`), a walrus (`x := 1`), a ternary (`dev ? 'x' : y`), `::`,
Kotlin's `object : T` and Scala's `xs: _*` and `_: T` stay calls. Swift, C# and Dart write named arguments that way
(`f(id: 1)`), so their blocks, and untagged ones, keep these calls.

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
    "methods": [{"name": "get", "owner": "agents"}],  # optional: each method with its owner
    "owners": ["agents", "config"],               # optional: the classes and namespaces the skill documents
    "skillPackagePath": "/path/to/skill"          # holds SKILL.md and references/
  }

Each method's owner is one of the owners. A `methods` item without a
non-empty string `name` and `owner` is skipped. An owner applies only to a
plain name: a qualified one (`agents.get`) is matched as written, as in
`names`.

or the files: --inventory <file> --skill-dir <dir>. --inventory reads the
validated inventory validate-inventory.py wrote (its --output), so no name
is copied by hand:

- names: each entry whose kind is `function`, or `method` with no
  non-empty string `owner`.
- methods: each other `method` entry, with its `owner`, and each string
  item of the `methods` list of a class, interface, struct, trait or type
  entry, owned by that entry (no other kind's list is read). An item names
  the identifier before its first `(` (the last part of a qualified one),
  else its leading identifier, once its leading `.` or `#`, its decorators
  (`@property`, `@lru_cache(maxsize=1)`), a Go receiver
  (`func (c *Client)`) and its modifier words (`async`, `static`, `def`
  ...) are dropped. A dunder (`__init__`), an item that starts with
  `await` and one of modifiers only (`async`) name no method.
- owners: the name of each class, struct, interface, trait, type, enum or
  adapter entry, and each method's owner.

Output (stdout, one object):
  {
    "skillPackagePath": "...",
    "files": ["SKILL.md", "references/api.md"],  # read, in this order
    "exports": [                                  # each name with at least one call, in input order
      {
        "name": "fetchData",
        "descriptionCount": 3,                    # all found; descriptions[] holds the first 12
        "descriptions": [{"file", "line", "endLine", "kind", "section", "header", "text", "truncated"}],
        "owner": null,                            # a method's owner, null for a name
        "calls": [{"file", "line", "fence", "language", "receiver", "receiverMatch", "awaited",
                   "directlyAwaited", "awaitedVia", "enclosingCallee", "chainedMember", "text"}],
        "callCount": 2,
        "awaitedCount": 1,                        # calls whose `awaited` is true
        "directlyAwaitedCount": 1,                # calls whose `directlyAwaited` is true
        "unverifiedCalls": [],                    # a method's calls on an "unknown" receiver, as calls[]
        "otherReceiverCount": 0                   # a method's matches on an "other" receiver
      }
    ],
    "notCalled": ["parseConfig", "agents.get"],   # names, and owner.method, no example calls
    "notCalledUnverified": [{"name": "get", "owner": "agents", "unverifiedCalls": [...]}],  # their unverified calls
    "summary": {"names": N, "called": N, "notCalled": N}  # names: the names and methods, deduplicated
  }
  or {"error": ..., "code": "INVALID_INPUT"} on a schema violation.

`kind` is "heading", "table-row", "list-item", "paragraph" or "signature".
Lines are 1-based; `fence` is the line of the call's opening fence.

CLI usage (mirrors verify-declared-numerator.py):
  uv run locate-export-segments.py --inventory <file> --skill-dir <dir>
  uv run locate-export-segments.py '<JSON>'                  # positional
  uv run locate-export-segments.py --json-input '<JSON>'     # explicit flag
  cat input.json | uv run locate-export-segments.py --stdin  # piped input

Exit codes:
  0  segments emitted
  1  no input / input could not be parsed as JSON, or an --inventory file that cannot be read
  2  input parsed but schema invalid (error object emitted as JSON)
"""

from __future__ import annotations

import argparse
import bisect
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
# Whitespace, a Python backslash continuation included; LINE_SPACE stays on its line.
SPACE = r"(?:\s|\\\n)*"
LINE_SPACE = r"(?:[ \t]|\\\n)*"
AFTER_CALL_RE = re.compile(f"{SPACE}[?!]?\\.{SPACE}((?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*)")
AWAIT_BEFORE_RE = re.compile(f"(?<![{IDENT_CHARS}])await$")
AWAIT_AFTER_RE = re.compile(f"{SPACE}\\??\\.{SPACE}await(?![{IDENT_CHARS}])")
# A subscript or call applied to a call's result: `f(x)[0]`, `f(x)(y)`, `f(x)?.[0]`, `f(x)!(y)`.
APPLIED_RE = re.compile(f"{LINE_SPACE}(?:\\?\\.|!)?[\\[(]")
# What may close a group that holds only the call (`(f(x) as T)`, `(f(x)!)`), and what may follow
# the outermost group: the end of the statement, of a list or of a bracket.
GROUP_TAIL_RE = re.compile(f"{SPACE}(?:!|as(?![{IDENT_CHARS}])[^()]*)?{SPACE}")
GROUP_END_RE = re.compile(f"{LINE_SPACE}(?:[;,)\\]}}]|\\Z|\\n\\s*(?:[^\\s.?\\[(]|\\Z))")
# Members whose call waits for an awaitable: under `await`, the export returns one.
WAIT_MEMBERS = frozenset({"then", "catch", "finally", "ConfigureAwait"})
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
# Languages where no call's argument is `name: ...`, so an argument list that
# holds one declares the name. Swift, C# and Dart write named arguments that
# way, and untagged code can be any of them.
ANNOTATED_PARAMS = JS_FAMILY | frozenset({"python", "py", "python3", "kotlin", "kt", "kts", "scala"})
# An annotated parameter: `name: Type`, `*args: T`, `...rest: T`, and `name?: T` (group 2, the `?` right
# before the `:`) in the JavaScript family, where no `?:` operator exists. Not `::`, nor a walrus `:=`, nor a
# ternary (`dev ? 'x' : y`).
ANNOTATED_PARAM_RE = re.compile(
    f"\\s*(?:\\*{{1,2}}|\\.\\.\\.)?((?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*)(?:(\\?)|\\s*):(?![:=])(.*)", re.S)
# A Python lambda's parameters, which hold commas: `lambda a, b:`.
LAMBDA_PARAMS_RE = re.compile(f"(?<![{IDENT_CHARS}])lambda(?![{IDENT_CHARS}])[^:]*:")
PYTHON = frozenset({"python", "py", "python3"})
# The accessors between a receiver and the member it holds, longest first.
ACCESSORS = ("?.", "!.", "::", "->", ".")
IDENTIFIER_RE = re.compile(f"(?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*")

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

# Receivers and the bindings that tie them to an owner.
IDENT = f"(?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*"
TYPE_PATH = f"{IDENT}(?:(?:\\.|::){IDENT})*"
GENERIC = r"(?:[ \t]*<[^<>()\n]*(?:<[^<>()\n]*>[^<>()\n]*)*>)?"
SEGMENT_HEAD_RE = re.compile(f"({IDENT}){GENERIC}")
# `x = ...` or `x := ...`, not `==`, `=>` or `=~`.
ASSIGN_RE = re.compile(f"(?<![{IDENT_CHARS}.])({IDENT})[ \\t]*(?::=|=(?![=>~]))\\s*")
RHS_RE = re.compile(f"(?:await\\s+)?(new\\s+)?(?:&[ \\t]*(?:mut\\s+)?)?({TYPE_PATH}){GENERIC}[ \\t]*([({{]?)")
# A member, subscript or call applied to a new object (`.await` is no member).
AFTER_CONSTRUCTOR_RE = re.compile(f"[ \\t]*(?:\\?\\.|!\\.|\\.(?!await(?![{IDENT_CHARS}]))|::|->|\\[|\\()")
ANNOTATION_RE = re.compile(f"(?<![{IDENT_CHARS}.])({IDENT})\\??[ \\t]*:[ \\t]*(?:&[ \\t]*(?:mut[ \\t]+)?|\\*)?"
                           f"({TYPE_PATH})(?![{IDENT_CHARS}(.:])")
TYPED_BINDING_RE = re.compile(f"(?<![{IDENT_CHARS}.])({TYPE_PATH}){GENERIC}(?:\\[\\])*[ \\t]+({IDENT})[ \\t]*"
                              f"(?:=(?![=>~])|;)")
GO_VAR_RE = re.compile(f"(?<![{IDENT_CHARS}.])var[ \\t]+({IDENT})[ \\t]+\\*?({TYPE_PATH})(?![{IDENT_CHARS}(.:])")
WITH_AS_RE = re.compile(f"\\)[ \\t]*as[ \\t]+({IDENT})(?![{IDENT_CHARS}])")
CALLEE_END_RE = re.compile(f"({TYPE_PATH}){GENERIC}[ \\t]*$")
# Words that stand where TYPED_BINDING_RE reads a type: `const x = ...`, `return x;`.
BINDING_WORDS = DECLARATION_WORDS | EXPRESSION_WORDS | frozenset({
    "var", "let", "const", "val", "auto", "mut", "dim", "my", "local", "global", "nonlocal",
})
# A class-like body: `class Agents`, `impl Store`, `impl<T> Trait for Store<T>`, Go's `type Client struct`.
CLASS_RE = re.compile(
    f"(?<![{IDENT_CHARS}.])(?:(?:class|struct|interface|trait|object|protocol|record|enum|extension)[ \\t]+"
    f"|impl{GENERIC}[ \\t]+(?:{TYPE_PATH}{GENERIC}[ \\t]+for[ \\t]+)?)({TYPE_PATH})"
    f"|(?<![{IDENT_CHARS}.])type[ \\t]+({IDENT})[ \\t]+(?:struct|interface)(?![{IDENT_CHARS}])")
BRACE_BODY_RE = re.compile(r"[^{};\n]*(?:\n[ \t]*)?\{")
GO_RECEIVER_TAIL_RE = re.compile(
    f"func[ \\t]*\\([ \\t]*(?:{IDENT}[ \\t]+)?\\*?({TYPE_PATH}){GENERIC}(?:\\[[^\\]]*\\])?[ \\t]*\\)[ \\t]*$")


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
    """Back over whitespace, a Python backslash continuation included."""
    while i > 0 and (text[i - 1] in " \t\n" or (text[i - 1] == "\\" and text.startswith("\n", i))):
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
        while k > 0 and text[k - 1] == "!":
            k -= 1  # Kotlin's `!!` before the accessor: `gen!!.next_uuid()`
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


def _receiver(text, chain, name_start):
    """The expression before the member at `name_start`, without its accessor: `cognee.agents` in
    `cognee.agents.get(`; None when the name has no receiver. Whitespace (a line break in a fluent chain, a
    blanked string) is dropped beside an accessor, a bracket or a comma, and cut to one space elsewhere."""
    k = _skip_space_back(text, name_start)
    accessor = next((a for a in ACCESSORS if text.endswith(a, chain, k)), None)
    if accessor is None:
        return None
    receiver = re.sub(r"(?:\s|\\\n)+", " ", text[chain:k - len(accessor)]).strip()
    receiver = re.sub(r" ?(\?\.|!\.|::|->|[.,()\[\]]) ?", r"\1", receiver)
    receiver = re.sub(r"!+(?=\?\.|\.|::|->|$)", "", receiver)  # a non-null assertion: `gen!!`, `client!`
    return receiver or None


def _owner_display(owner):
    """An owner as the output names it: its type parameters dropped (`Repository` for `Repository<T>`)."""
    owner = owner.strip()
    while (bare := re.sub(r"<[^<>]*>", "", owner)) != owner:
        owner = bare
    return re.sub(r"\[[^\[\]]*\]$", "", owner).strip()


def _type_parts(path):
    """The parts of a dotted or `::` path, lower case, a trailing `new` dropped (`Owner::new`, Ruby's
    `Owner.new`); None for an empty path."""
    parts = tuple(p.lower() for p in re.split(r"\.|::|#|->", path) if p)
    if len(parts) > 1 and parts[-1] == "new":
        parts = parts[:-1]
    return parts or None


def _segment_name(segment):
    """The identifier of one member of a receiver, plain or called once (`App` in `App(x)`), else None."""
    m = SEGMENT_HEAD_RE.match(segment)
    if not m:
        return None
    rest = segment[m.end():]
    if not rest or (rest.startswith("(") and _matching_close(rest, 0) == len(rest) - 1):
        return m.group(1).lower()
    return None


def _receiver_parts(receiver):
    """The member names of a receiver, lower case, None for a member that is no plain or once-called name:
    ("coco", "app") for `coco.App(...)`, (None, "agents") for `get()[0].agents`; a trailing `new` dropped."""
    segments, depth, start, i = [], 0, 0, 0
    while i < len(receiver):
        c = receiver[i]
        if c in BRACKETS:
            depth += 1
        elif c in CLOSERS:
            depth -= 1
        elif depth == 0 and (accessor := next((a for a in ACCESSORS if receiver.startswith(a, i)), None)):
            segments.append(receiver[start:i])
            i += len(accessor)
            start = i
            continue
        i += 1
    segments.append(receiver[start:])
    parts = tuple(_segment_name(s) for s in segments)
    return parts[:-1] if len(parts) > 1 and parts[-1] == "new" else parts


def _ties(parts, owner_parts):
    """True when a receiver or a bound type names the owner: the last parts agree, case-insensitively, and when
    both have several parts the owner's are the receiver's last ones (`other_lib.agents` is not `cognee.agents`)."""
    if not parts or parts[-1] is None or parts[-1] != owner_parts[-1]:
        return False
    if len(parts) > 1 and len(owner_parts) > 1:
        return parts[-len(owner_parts):] == owner_parts
    return True


class _Owners:
    """Every owner of the input, looked up by its last part."""

    def __init__(self, owners):
        self.parts = {o: p for o in owners if (p := _type_parts(o))}
        self.by_last = {}
        for owner, parts in self.parts.items():
            self.by_last.setdefault(parts[-1], []).append(owner)

    def tied(self, parts):
        """The owners `parts` names."""
        if not parts or parts[-1] is None:
            return frozenset()
        return frozenset(o for o in self.by_last.get(parts[-1], ()) if _ties(parts, self.parts[o]))


def _constructed(text, pos):
    """The parts of the type a constructor-like right-hand side at `pos` builds: `Owner(...)`, `await Owner(...)`,
    `new Owner(...)`, `Owner::new(...)`, `Owner.new`, `Owner{`; None for anything else, a member call's result
    (`cognee.agents.create(n)` builds a `create`, never an `agents`) or a member of the new object included."""
    m = RHS_RE.match(text, pos)
    if not m:
        return None
    new, path, follow = m.group(1), m.group(2), m.group(3)
    if follow == "(":
        close = _matching_close(text, m.end() - 1)
        if close is not None and AFTER_CONSTRUCTOR_RE.match(text, close + 1):
            return None  # `Owner().build()`: the object a member returns
        return _type_parts(path)
    if follow == "{" or new:
        return _type_parts(path)
    raw = re.split(r"\.|::", path)
    return _type_parts(path) if len(raw) > 1 and raw[-1] == "new" else None


def _bindings(text):
    """{identifier: ([row, ...], [type parts or None, ...])} of a block, in text order: each line that binds an
    identifier to a type, and each plain assignment (to None, so a later `x = make()` ends an earlier binding).

    A binding is `x = Owner(...)` (see _constructed), an annotation `x: Owner`, `with Owner(...) as x`, a
    Java- or C#-style `Owner x =` and Go's `var x Owner` or `var x *Owner`. An assignment inside an argument
    list (`f(gen=UuidGenerator())`) binds nothing.
    """
    found = {}
    for m in ASSIGN_RE.finditer(text):
        before = _skip_space_back(text, m.start())
        if before > 0 and text[before - 1] in "(,":
            continue  # a keyword argument or a parameter default
        found[m.start(1)] = (m.group(1), _constructed(text, m.end()))
    for m in TYPED_BINDING_RE.finditer(text):
        if m.group(1) not in BINDING_WORDS:
            found[m.start(2)] = (m.group(2), _type_parts(m.group(1)))
    for regex in (ANNOTATION_RE, GO_VAR_RE):
        for m in regex.finditer(text):
            found[m.start(1)] = (m.group(1), _type_parts(m.group(2)))
    for m in WITH_AS_RE.finditer(text):
        opened = _matching_open(text, m.start())
        callee = CALLEE_END_RE.search(text, max(0, opened - 300), opened) if opened is not None else None
        if callee:
            found[m.start(1)] = (m.group(1), _type_parts(callee.group(1)))
    starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]
    by_name = {}
    for pos in sorted(found):
        name, parts = found[pos]
        rows, types = by_name.setdefault(name, ([], []))
        rows.append(bisect.bisect_right(starts, pos) - 1)
        types.append(parts)
    return by_name


def _class_spans(text):
    """(start, end, class parts) of each class-like body in a block: braces, else indentation (Python, Ruby)."""
    spans = []
    for m in CLASS_RE.finditer(text):
        name = m.group(1) or m.group(2)
        brace = BRACE_BODY_RE.match(text, m.end())
        if brace:
            close = _matching_close(text, brace.end() - 1)
            spans.append((brace.end() - 1, len(text) if close is None else close, _type_parts(name)))
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        indent = len(text[line_start:m.start()]) - len(text[line_start:m.start()].lstrip(" \t"))
        end, pos = len(text), text.find("\n", m.end())
        while pos != -1:
            nxt = text.find("\n", pos + 1)
            line = text[pos + 1:nxt if nxt != -1 else len(text)]
            if line.strip() and len(line) - len(line.lstrip(" \t")) <= indent:
                end = pos + 1
                break
            pos = nxt
        spans.append((m.end(), end, _type_parts(name)))
    return spans


class _Block:
    """One fenced block's receivers, read once: its bindings and class bodies, built on first use."""

    def __init__(self, text, owners):
        self.text, self.owners = text, owners
        self._bindings = self._spans = None

    def ties(self, match):
        """(via a binding, the owners the receiver of `match` names), cached on the match."""
        if "ties" not in match:
            receiver, ties = match["receiver"], (False, frozenset())
            if receiver is not None:
                rows, types, last = (), (), -1
                if IDENTIFIER_RE.fullmatch(receiver):
                    if self._bindings is None:
                        self._bindings = _bindings(self.text)
                    rows, types = self._bindings.get(receiver, ((), ()))
                    last = bisect.bisect_left(rows, match["row"]) - 1  # the last binding on a line before the call
                if last >= 0:
                    ties = (True, self.owners.tied(types[last]))
                else:
                    ties = (False, self.owners.tied(_receiver_parts(receiver)))
            match["ties"] = ties
        return match["ties"]

    def receiver_match(self, match, owner):
        """"owner", "bound", "other" or "unknown": how the receiver of `match` ties it to `owner`."""
        if match["receiver"] is None:
            return "unknown"  # a bare call: an import or an implicit `this` may tie it, the text does not
        via_binding, tied = self.ties(match)
        if owner in tied:
            return "bound" if via_binding else "owner"
        return "other" if tied else "unknown"

    def declares(self, match, owner, kind):
        """True when the declaration at `match` is `owner`'s: on its receiver, in its class body, or on a Go
        receiver of its type (`func (g *UuidGenerator) next_uuid(`)."""
        if match["receiver"] is not None:
            return kind in ("owner", "bound")
        owner_parts = self.owners.parts.get(owner)
        go = GO_RECEIVER_TAIL_RE.search(self.text, match["line_start"], match["chain"])
        if go:
            return _ties(_type_parts(go.group(1)), owner_parts)
        if self._spans is None:
            self._spans = _class_spans(self.text)
        inside = [s for s in self._spans if s[0] <= match["name_start"] < s[1]]
        return bool(inside) and _ties(max(inside, key=lambda s: s[0])[2], owner_parts)  # the innermost body


def _await_before(text, start):
    """True when `await` stands right before the expression that starts at `start`."""
    return bool(AWAIT_BEFORE_RE.search(text, 0, _skip_space_back(text, start)))


def _awaited_at(text, start):
    """True when `await` stands right before the expression that starts at `start`, or an
    asynchronous loop or context manager consumes it."""
    if _await_before(text, start):
        return True
    return bool(ASYNC_CONSUMER_RE.search(text[text.rfind("\n", 0, start) + 1:start]))


def _grouped_await(text, chain, close):
    """True for `await (call(...))` and `await ((call(...) as T))`: the call alone fills each group
    around it (a trailing `as T` or `!` allowed), `await` stands before the outermost one, and
    nothing but the end of the statement, of a list or of a bracket follows it."""
    start, end = chain, close
    while end is not None:
        group = _skip_space_back(text, start) - 1
        if group < 0 or text[group] != "(":
            return False
        end_group = _matching_close(text, group)
        if end_group is None or not GROUP_TAIL_RE.fullmatch(text, end + 1, end_group):
            return False
        if _await_before(text, group):
            return bool(GROUP_END_RE.match(text, end_group + 1))
        start, end = group, end_group
    return False


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
    """How a call or group around the expression at `start` awaits it, within one function body.

    ("runner", callee) for a runner it is an argument of, ("argument", callee) for an awaited or
    consumed call it is an argument of, ("chain", None) for an awaited group around it and
    ("consumer", None) for a consumed one; None when nothing around it awaits it.
    """
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
                callee = None
                if word and word.group(1) not in EXPRESSION_WORDS:
                    expr = _chain_start(text, word.start())
                    callee = re.sub(r"(?:\s|\\\n)+", "", text[expr:k])
                    if _is_runner(callee):
                        return "runner", callee
                else:
                    expr = i  # a grouping `(`: `await (fetch())`
                close = _matching_close(text, i)
                awaits = _await_before(text, expr) or (close is not None and AWAIT_AFTER_RE.match(text, close + 1))
                if awaits or _awaited_at(text, expr):
                    return ("argument", callee) if callee else ("chain" if awaits else "consumer", None)
                i = expr
    return None


def _how_awaited(text, chain, close):
    """(awaitedVia, enclosingCallee, chainedMember) of the call whose expression starts at `chain`
    and whose argument list closes at `close`."""
    before = _await_before(text, chain)
    member = AFTER_CALL_RE.match(text, close + 1) if close is not None else None
    chained = member.group(1) if member else None
    if close is not None and AWAIT_AFTER_RE.match(text, close + 1):
        return "direct", None, None
    if member or (close is not None and APPLIED_RE.match(text, close + 1)):
        if before:
            return ("direct" if chained in WAIT_MEMBERS else "chain"), None, chained
    elif before or _grouped_await(text, chain, close):
        return "direct", None, None
    if _awaited_at(text, chain):
        return "consumer", None, chained
    via, callee = _enclosing_awaits(text, chain) or (None, None)
    return via, callee, chained


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


def _top_level_args(args):
    """The arguments of an argument list's text, split at the commas outside any bracket."""
    parts, depth, start = [], 0, 0
    for i, c in enumerate(args):
        if c in BRACKETS:
            depth += 1
        elif c in CLOSERS:
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(args[start:i])
            start = i + 1
    parts.append(args[start:])
    return parts


def _annotated(args, language):
    """True when an argument is an annotated parameter (`key: str`): no call's argument is, in `language`."""
    if language in PYTHON:
        args = LAMBDA_PARAMS_RE.sub("lambda:", args)  # `key=lambda k, v: v` is one argument
    for arg in _top_level_args(args):
        m = ANNOTATED_PARAM_RE.match(arg)
        if not m or m.group(1) == "lambda" or (m.group(2) and language not in JS_FAMILY):
            continue
        if language in ("kotlin", "kt", "kts") and m.group(1) == "object":
            continue  # Kotlin's anonymous object argument: `f(object : Listener { ... })`
        if language == "scala" and (m.group(1) == "_" or m.group(3).strip() == "_*"):
            continue  # Scala's typed placeholder `f(_: Int)`, and `f(xs: _*)` passing a sequence as varargs
        return True
    return False


def _is_declaration(text, line_start, chain, name_start, paren, close, language):
    """True when the name at name_start is declared there, not called."""
    if close is not None and language in ANNOTATED_PARAMS and _annotated(text[paren + 1:close], language):
        return True  # a signature listing: `get(key: str, reveal_secrets: bool = False)`
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


def _matches(text, call_re, declaration_res, language):
    """Each match of a name in a block, read once: where it stands, its receiver, and whether it declares the
    name (`declaration`) or is a call (`call`: the last part of a qualified name counts only as a declaration)."""
    seen, found = set(), []
    for regex in (call_re, *declaration_res):
        for m in regex.finditer(text):
            name_start, paren = m.start(), m.end() - 1
            if name_start in seen:
                continue
            seen.add(name_start)
            close = _matching_close(text, paren)
            chain = _chain_start(text, name_start)
            line_start = text.rfind("\n", 0, name_start) + 1
            declaration = _is_declaration(text, line_start, chain, name_start, paren, close, language)
            if declaration or regex is call_re:
                found.append({"name_start": name_start, "close": close, "chain": chain, "line_start": line_start,
                              "row": text.count("\n", 0, name_start), "receiver": _receiver(text, chain, name_start),
                              "declaration": declaration})
    return found


def scan_block(rel, lines, opening, closing, info, names, keys_by_name, owners):
    """{key: {"calls": [...], "unverified": [...], "other": N, "signatures": [...]}} for one fenced block.

    `names` maps each name to (its call regex, the regexes of the other forms
    a declaration of it may take), `keys_by_name` each name to its keys,
    (owner or None, name), and `owners` indexes every owner. A key without an
    owner takes every call and declaration. An owned key takes the calls on
    its owner or on a variable the block binds to it, lists those on an
    "unknown" receiver in `unverified`, counts those on an "other" one, and
    takes a declaration on its owner, in its class body or on a Go receiver
    of its type.
    """
    language = _language(info)
    found = {key: {"calls": [], "unverified": [], "other": 0, "signatures": []}
             for keys in keys_by_name.values() for key in keys}
    if language in DATA_LANGUAGES:
        return found
    body = lines[opening + 1:closing]
    text = mask_code("\n".join(body), language)
    block = _Block(text, owners)

    def call(match, receiver_match):
        if "await" not in match:
            match["await"] = _how_awaited(text, match["chain"], match["close"])
        via, callee, chained = match["await"]
        row = match["row"]
        return {
            "file": rel, "line": opening + row + 2, "fence": opening + 1, "language": language or None,
            "receiver": match["receiver"], "receiverMatch": receiver_match,
            "awaited": via is not None, "directlyAwaited": via == "direct", "awaitedVia": via,
            "enclosingCallee": callee, "chainedMember": chained,
            "text": _cap(body[row].strip(), LINE_TEXT_CAP)[0],
        }

    for name, (call_re, declaration_res) in names.items():
        for match in _matches(text, call_re, declaration_res, language):
            signature = {"line": opening + match["row"] + 2, "text": body[match["row"]].strip()}
            for key in keys_by_name[name]:
                owner = key[0]
                got = found[key]
                if owner is None:
                    if match["declaration"]:
                        got["signatures"].append(signature)
                    else:
                        got["calls"].append(call(match, None))
                    continue
                kind = block.receiver_match(match, owner)
                if match["declaration"]:
                    if block.declares(match, owner, kind):
                        got["signatures"].append(signature)
                elif kind == "other":
                    got["other"] += 1
                else:
                    got["unverified" if kind == "unknown" else "calls"].append(call(match, kind))
    return found


# --------------------------------------------------------------------------
# Locate
# --------------------------------------------------------------------------


def _validate(inp):
    if not isinstance(inp, dict):
        return "Input must be a JSON object"
    if not isinstance(inp.get("names"), list):
        return "names must be a list of export names"
    if inp.get("methods") is not None and not isinstance(inp["methods"], list):
        return "methods must be a list of {name, owner} objects when given"
    if inp.get("owners") is not None and not isinstance(inp["owners"], list):
        return "owners must be a list of class and namespace names when given"
    path = inp.get("skillPackagePath")
    if not isinstance(path, str) or not path:
        return "skillPackagePath is required: the folder that holds SKILL.md and references/"
    if not Path(path).is_dir():
        return f"skillPackagePath is not a folder: {path}"
    return None


def _keys(inp):
    """(owner or None, name) for each name and each method of the input, in input order, deduplicated.

    An owner applies only to a plain name: a qualified one (`agents.get`) is matched as written."""
    keys = [(None, n) for n in inp["names"] if isinstance(n, str) and n.strip()]
    for item in inp.get("methods") or []:
        if not isinstance(item, dict):
            continue
        name, owner = item.get("name"), item.get("owner")
        if not (isinstance(name, str) and name.strip() and isinstance(owner, str) and owner.strip()):
            continue
        name, owner = name.strip(), _owner_display(owner)
        if _last_part(name):
            keys.append((None, name))
        elif _type_parts(owner):
            keys.append((owner, name))
    return list(dict.fromkeys(keys))


def _owner_first(descriptions, owner):
    """An owned method's descriptions, those that name its owner (`agents` for `cognee.agents`, any case) first."""
    if owner is None:
        return descriptions
    names_owner = re.compile(_bounded(_last_part(owner) or owner).pattern, re.I)
    return sorted(descriptions, key=lambda d: not names_owner.search(d["text"]))


def locate(inp):
    """Pure location over SKILL.md and references/**/*.md under skillPackagePath."""
    err = _validate(inp)
    if err:
        return make_error(err)
    keys = _keys(inp)
    owners = _Owners(dict.fromkeys(
        [d for o in inp.get("owners") or [] if isinstance(o, str) and (d := _owner_display(o))]
        + [owner for owner, _ in keys if owner is not None]))
    names = list(dict.fromkeys(name for _, name in keys))
    bounded = {name: _bounded(name) for name in names}
    patterns = {name: (_call_pattern(name), [_call_pattern(p)] if (p := _last_part(name)) else [])
                for name in names}
    keys_by_name = {name: [key for key in keys if key[1] == name] for name in names}
    files = skill_files(inp["skillPackagePath"])
    descriptions = {key: [] for key in keys}
    calls = {key: [] for key in keys}
    unverified = {key: [] for key in keys}
    other = dict.fromkeys(keys, 0)
    for rel, lines in files:
        start = _frontmatter_end(lines)
        fenced, code = _fenced_blocks(lines, start)
        headings, blocks = _prose(lines, start, code)
        prose = {name: describe(rel, lines, code, headings, blocks, bounded[name]) for name in names}
        per_file = {key: list(prose[key[1]]) for key in keys}
        for opening, closing, info in fenced:
            for key, got in scan_block(rel, lines, opening, closing, info, patterns, keys_by_name, owners).items():
                calls[key] += got["calls"]
                unverified[key] += got["unverified"]
                other[key] += got["other"]
                per_file[key] += [_entry(rel, s["line"], s["line"], "signature",
                                         _heading_path(headings, s["line"] - 1), None, s["text"], LINE_TEXT_CAP)
                                  for s in got["signatures"]]
        for key in keys:
            descriptions[key] += sorted(per_file[key], key=lambda e: e["line"])
    exports = [{
        "name": name,
        "owner": owner,
        "descriptionCount": len(descriptions[(owner, name)]),
        "descriptions": _owner_first(descriptions[(owner, name)], owner)[:MAX_DESCRIPTIONS],
        "calls": calls[(owner, name)],
        "callCount": len(calls[(owner, name)]),
        "awaitedCount": sum(1 for c in calls[(owner, name)] if c["awaited"]),
        "directlyAwaitedCount": sum(1 for c in calls[(owner, name)] if c["directlyAwaited"]),
        "unverifiedCalls": unverified[(owner, name)],
        "otherReceiverCount": other[(owner, name)],
    } for owner, name in keys if calls[(owner, name)]]
    # A method with only unverified calls is not called: §2.5's async rule cites a first call. Its unverified
    # calls still reach the output, in notCalledUnverified.
    not_called = [f"{owner}.{name}" if owner else name for owner, name in keys if not calls[(owner, name)]]
    not_called_unverified = [{"name": name, "owner": owner, "unverifiedCalls": unverified[(owner, name)]}
                             for owner, name in keys if not calls[(owner, name)] and unverified[(owner, name)]]
    return {
        "skillPackagePath": inp["skillPackagePath"],
        "files": [rel for rel, _ in files],
        "exports": exports,
        "notCalled": not_called,
        "notCalledUnverified": not_called_unverified,
        "summary": {"names": len(keys), "called": len(exports), "notCalled": len(not_called)},
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
    src.add_argument("--inventory", metavar="PATH",
                     help="the validated inventory file: its functions and methods, and the `methods` of each "
                          "class, interface, struct, trait or type entry tied to it (needs --skill-dir)")
    parser.add_argument("--skill-dir", metavar="DIR", help="with --inventory: the skill package")
    return parser


# The inventory kinds §2.5 checks: the ones a caller awaits or calls. The
# `methods` items of a class, interface, struct, trait or type entry
# (METHOD_LIST_KINDS, and no other kind's) are checked too, each tied to its
# entry.
CALLABLE_KINDS = ("function", "method")
METHOD_LIST_KINDS = ("class", "interface", "struct", "trait", "type")
# The kinds a method can be documented on: a receiver that names one is that owner's.
OWNER_KINDS = ("class", "struct", "interface", "trait", "type", "enum", "adapter")
# Words a `methods` item may write before the method's name: `async next_uuid(dep=None)`.
METHOD_MODIFIERS = DECLARATION_WORDS | {"classmethod", "staticmethod"}
MODIFIER_RE = re.compile(f"((?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*)\\s+(?=[{IDENT_CHARS}*\\[])")
DECORATOR_RE = re.compile(f"@{TYPE_PATH}")
GO_RECEIVER_ITEM_RE = re.compile(r"^func[ \t]*\([^()]*\)[ \t]*")
QUALIFIED = f"(?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*(?:(?:\\.|::|#)(?:[^\\W\\d]|\\$)[{IDENT_CHARS}]*)*"
METHOD_CALLEE_RE = re.compile(
    f"(?<![{IDENT_CHARS}.:#])({QUALIFIED})[ \\t]*(?:<[^<>()\\n]*(?:<[^<>()\\n]*>[^<>()\\n]*)*>)?[ \\t]*\\(")
METHOD_LEAD_RE = re.compile(f"({QUALIFIED})")
AWAIT_LEAD_RE = re.compile(f"await(?![{IDENT_CHARS}])")
DUNDER_RE = re.compile(r"__\w+__")


def _method_name(item):
    """The method a class entry's `methods` item names, as the skill writes it (`async next_uuid(self) -> UUID`
    gives `next_uuid`), or None: a dunder (`__init__`), an item that starts with `await`, and one that holds
    only modifiers (`async`, `async *[Symbol.asyncIterator]()`) name no method."""
    text = item.strip().lstrip(".#")
    while (m := DECORATOR_RE.match(text)):  # `@property name`, `@lru_cache(maxsize=1) compute(x)`
        end = m.end()
        if text.startswith("(", end):
            close = _matching_close(text, end)
            if close is None:
                return None
            end = close + 1
        text = text[end:].lstrip()
    text = GO_RECEIVER_ITEM_RE.sub("", text, count=1)  # `func (c *Client) Fetch(ctx) error`
    while (m := MODIFIER_RE.match(text)) and m.group(1) in METHOD_MODIFIERS:
        text = text[m.end():].lstrip("*")  # `async *stream()`, a generator
    if AWAIT_LEAD_RE.match(text):
        return None
    m = METHOD_CALLEE_RE.search(text)
    if not m:
        m = METHOD_LEAD_RE.match(text)
        if not m or m.group(1) in METHOD_MODIFIERS:
            return None
    name = _last_part(m.group(1)) or m.group(1)
    return None if DUNDER_RE.fullmatch(name) else name


def inventory_input(path, skill_dir):
    """The JSON input for the functions and methods of a validated inventory file.

    `names`: each `function` entry, and each `method` entry with no non-empty
    string `owner`. `methods`: each other `method` entry with its owner, and
    each method the `methods` list of a class, interface, struct, trait or
    type entry names, owned by that entry. `owners`: each class-like entry and
    each method's owner.
    """
    data = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("inventory"), dict):
        data = data["inventory"]  # validate-inventory.py's whole result
    exports = data.get("exports") if isinstance(data, dict) else None
    if not isinstance(exports, list):
        raise ValueError(f"--inventory {path} holds no `exports` list")
    names, methods, owners = [], [], []
    for entry in exports:
        if not (isinstance(entry, dict) and isinstance(entry.get("name"), str)):
            continue
        name, kind, owner = entry["name"], entry.get("kind"), entry.get("owner")
        if kind == "method" and isinstance(owner, str) and owner.strip():
            methods.append({"name": name, "owner": owner})
            owners.append(owner)
        elif kind in CALLABLE_KINDS:
            names.append(name)
        if kind in OWNER_KINDS:
            owners.append(name)
        listed = entry["methods"] if kind in METHOD_LIST_KINDS and isinstance(entry.get("methods"), list) else []
        for method in filter(None, (_method_name(item) for item in listed if isinstance(item, str))):
            methods.append({"name": method, "owner": name})
            owners.append(name)
    return {"names": names, "methods": methods, "owners": list(dict.fromkeys(owners)), "skillPackagePath": skill_dir}


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
    if args.inventory is not None:
        if not args.skill_dir:
            parser.error("--inventory needs --skill-dir")
        try:
            data = inventory_input(args.inventory, args.skill_dir)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"error: cannot read --inventory {args.inventory}: {exc}", file=sys.stderr)
            return 1
        result = locate(data)
        print(json.dumps(result, indent=2))
        return 2 if result.get("code") == "INVALID_INPUT" else 0
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
