#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Deterministic schema validation of the §1 subagent inventory JSON.

Structural validator for the SKF test-skill coverage step (coverage-check.md
§1a "Schema validation" block). test-skill is a quality gate, so it must not
trust subagent output blindly: before any downstream step consumes the
documented inventory, the shape is validated. That validation is pure
structural checking (strip wrapping fences, parse JSON, assert required keys
and types, assert each export entry is a dict with a non-empty `name` and a
`kind` drawn from a fixed enum and, when present, a `signature_form` of
`partial` or `full`, and no key outside the contract's ENTRY_KEYS (#1001: a
`usage` written for `usage_signature` would leave its form uncompared, so
it is refused), and assert each cross-check mismatch carries its fields
and one other side, in order), with exactly one correct pass/fail per input
and no interpretation of meaning. It is therefore script work, not prompt
work; the prompt reads this verdict and owns only the HALT decision.

A cross-check mismatch (coverage-check.md §1 compares the SKILL.md body
with each reference file, and two reference files the body does not settle)
carries `export`, `reference_file`, `reference_line` and `issue`, and the
other side of its pair: `skill_md_line` for the SKILL.md body, or
`other_file` and `other_line` for a second reference file, never both and
never neither (a JSON null counts as absent). Each file is a
`references/**/*.md` file of the package, normalized to its path relative
to the package with forward slashes (an absolute path counts only inside
--skill-package), and the inventory echoed back carries that path; each line
is a positive integer. A pair of references is written in one order,
(`other_file`, `other_line`) sorting before (`reference_file`,
`reference_line`) in codepoint order, so a rerun gives the gap one title and
the ledger records it once; one export documented twice in one reference is
a pair of its two lines. A violation of the other side names both shapes,
and one of the order names both places. Its `export` names an inventory
entry (#1033): an entry's `name`, a `method`'s bare one, or `{owner}.{name}`
for a `method` entry that gives an `owner` (mismatch_names). Any other
value, an empty string or a number among them, is a violation, since §5b
titles a split-body gap with it.

With --skill-package it also runs the ground-truth spot-check (coverage-check.md
§1a): it sorts the exports by name (a stable sort), samples the first, the
middle and the last (`min(3, exportsCount)` names, indices
`[0, len//2, len-1]`), and looks each sampled name up in the package's
SKILL.md and in every file the inventory's `references` list names, with
the documented-name match below. A sampled name none of them writes is a
fabricated export: the inventory is then invalid, each absent name is a
violation, and the prompt re-dispatches the subagent with them, as it does
for a schema violation. No grep runs in the prompt, so an export named
`$state` or `a.b` is never a shell variable or a regex.

With --floor it also checks the inventory against the floor
load-coverage-inputs.py floor wrote (#790): the names the skill documents in
a fixed form. A floor name is checked when one of its origins is SKILL.md
or a file the inventory's `references` lists (the spot-check's files; a
listed absolute path inside the --skill-package folder counts as its path
relative to it); a name only an unlisted reference writes is not. It is
kept when any inventory entry has that name, whatever its kind: kinds stay
the reader's. Each checked name not
kept is a violation naming its first checked origin, and the inventory is
invalid, as for a fabricated name, so the prompt re-dispatches the subagent
with the names it left out. A checked origin that carries a `signature`
(#888: the `params`, or for a usage form such as `new Client(opts)` the
`usage_signature`, and the `return_type` the skill writes there in a fixed
form) is carried when an entry of that name, whatever its kind, reads as it
does: each of those fields the signature pins non-blank gives the same
field_text (whitespace runs as one space, a list's items joined with `, `,
a null field as blank), and a `params` or `usage_signature` that opens with
the shared text the contract has several names' entries carry, then `; `,
carries the pinned one after it. The `params` of an entry whose `at` is
that origin also carries the pinned one when its members, cut at the
commas outside brackets and strings (score-signatures.py's `_split`, each
member as field_text gives it), hold each pinned member in the pinned
order, others before, among or after them (#1028): the whole list in the
skill's order the contract has an entry write when the skill puts an own
member before or among the shared ones. Elsewhere, or with no `at`, such a
longer list is another form of the name, which never carries the pin nor
counts as its copy. At the origin, so is one an entry labels
`signature_form` "partial" where the signature gives no label and whose
other members hold an ellipsis item (`...` or `…` alone): a second overload
the pinned place writes (#1043), labelled by its own `...`, whose label is
never refused as one added to the pin. Unlabelled, such a list is still the
pin's copy, the shared members spelled out, a `...` among them included
(#1028). A pinned `usage_signature` is carried only as given or after the
shared text and `; `. A field the signature leaves blank, and the entry's
other fields (its `usage_signature` beside a pinned `params`,
its `params` beside a pinned `usage_signature`), are not read, but for one:
a signature read from a column under a partial label (`Signature
(simplified)`, `Props (simplified)`, load-coverage-inputs.py's
FLOOR_PARTIAL_LABELS), or one whose parameter group holds an ellipsis item
(`...` or `…` alone, #1029), also gives `signature_form` "partial", and an entry
carries it only with that `signature_form` too. Such an origin is carried
only at its own place: by the entries of that name whose `at` is that
origin and that give its form, at least one, each with the label, while
each entry of that name with no `at` (none given, or a bad one dropped, as
below) that gives that form gives the label too: score-signatures.py would
keep an unlabelled twin at the origin, or an unlabelled copy that shows
no place, over the label. An unlabelled copy whose kept `at` is another
place (with --skill-package, a line that writes the name) stays valid. A
dropped label, such an unlabelled twin or copy, and a carrier elsewhere
or with no `at`, is then a violation, never the warning below. The label
of an origin whose signature gives none is the floor's too (#1029): an
entry of that name that gives its form with `signature_form` "partial",
at that origin or with no `at`, is a violation, while such a copy whose
kept `at` is another place stays valid.
Each checked origin no entry carries is a violation naming the origin and
its signature, for a name left out too, and the inventory is invalid: the
form is never overwritten, so the re-dispatched subagent copies it as
given.

An entry's optional `signature_form` says how the skill presents its
signature: `partial` only when the skill labels the form partial (a
simplified form, a key-parameter summary, a `...` that stands in for
omitted members, not rest or variadic syntax), `full` otherwise.
A JSON null counts as absent, and an absent one as `full`. Any other value
is a violation naming the entry. score-signatures.py reads it: an optional
member a partial form leaves out is an Info observation, not a wrong
signature.

An entry's list `params` (#1043) holds the members of one parameter list,
one per item, never one form per item: field_text joins its items with
`, ` into that list, and a place that writes several forms of a name (two
overloads in one row) gives each form an entry of its own at that same
`at`, which score-signatures.py compares on its own. A list of two or more
items is a violation naming the entry and those items when one item holds
several parameters (cut at each comma outside every bracket pair and
string, as score-signatures.py's _split cuts a form, into two or more
non-blank parts; a generic function type's type parameters, `<T, U>(`, and
a numpy docstring member's `, optional` marker cut nothing), when one
writes a whole form (a parameter group with at most a name before it,
`(a, b)` or `run(a, b)`), or when two give one name before their `:` or
`=`: its join would be one parameter list that matches none of its forms.
The violation says to give each form its own entry, or else to write each
member as an item or the whole list as one string. A one-item list, whose
join is its item, and an item that is no string are not read this way.

An entry's `at` (#918) is the place the skill writes its form,
"<path>:<line>": the file as the package names it, SKILL.md or a file the
inventory's `references` lists (normalized as a pair's file is, and left in
the entry that way), and the line the form starts on. Each entry whose
`params` or `usage_signature` score-signatures.py plan compares
(compared_form: no `method`, with a `params` or `usage_signature` list or
non-blank string, or a function's `params` string, `""` included) is asked
for one. A missing or bad `at` never makes the inventory invalid: a bad one
is dropped from its entry, so the inventory --output writes carries none,
and each is listed in `warnings`, naming the entry. Its form is then
compared as one whose citations name no declaration, as before #918. An
`at` (on any entry) is bad when it is no "<path>:<line>" with a line from
1 or names another file. With --skill-package it is bad too when its file
cannot be read, when its line is past the end, and when that line does not
write the entry's name outside its citations (the documented-name match)
and, for a line inside a fenced block (the fences load-coverage-inputs.py
floor reads, locate-export-segments.py's), neither does the block. With
--floor, a checked origin with a `signature` (one with no partial label;
a labelled one is placed as above) is placed when an entry that
carries it gives that origin as its `at`; when none does, the `at` of each
entry that carries it is bad unless it is a checked origin whose signature
that entry carries, and the origin is a warning of its own when each entry
that carries it keeps its `at` at another such origin (the citations there
are not read). A warning says its form is left unbound (UNBOUND) only when
it is, and at most once for an entry: a method's dropped `at` and an
origin's own warning do not. score-signatures.py plan reads the citations
of each form's place (form_citations) to compare it with the declaration
they name. A form that writes only a `return_type` gives no `at`, so it is
never bound: plan compares it as it compares a form whose citations name no
declaration.

The inventory's optional `undecided` (#1021) lists each reading the
inventory contract or signature-comparison-rules.md leaves open that the
inventory rests on: each item gives `export`, `rule` (the sentence that
leaves it open), `reading` (the reading taken) and `other_gap` (what the
other reading would give) as non-empty strings, and may give its place as
`at`, a non-empty string (undecided_violations). A value that is no list,
an item that is no object and a blank or missing field are warnings naming
the item, never violations (drop_undecided): the list grades nothing, so it
never makes an inventory invalid, and the malformed item, or a value that
is no list, is dropped; a null or no key is none. The inventory --output
writes keeps the rest of the list, reconcile-coverage.py carries it into
coverage.json and its render lists it under Borderline Calls. It changes
no entry or check.

Distinct from reconcile-coverage.py (coverage numerator arithmetic) and
compute-score.py (weight tables): this script only validates the *shape* of the
subagent inventory and, on success, echoes the fence-stripped parsed inventory
back, with the `crossChecked` count added once the spot-check ran, so the
prompt consumes it directly instead of re-parsing the raw response.
`crossChecked` (#920) is `{"count": <int>, "names": [<name>, ...]}`: each
inventory name, once, that two or more of the spot-check's files write
(cross_checked), the Exports Cross-Checked count coherence-check reports.
Only the validator writes it: one the response carries is replaced with
--skill-package and dropped without it. When a `cross_check_mismatches`
entry's `export` is not among `names` (one written `{owner}.{name}` counts
by its `method` entry's `name`), `crossChecked` also gives `uncounted`, one
`{"export", "reference_file", "why"}` item per such entry, and a warning
names each (#1067), never a violation: its two places are in one file, a
file of its pair is not one the inventory reads, or a file of its pair does
not write it (uncounted_mismatches). The Reference Consistency section
names each one beside the count, so a mismatch is never shown beside a
count that leaves it out with no word why.

It also reports each documented item's completeness, the docs-only Export
Coverage rule: an item (one name and kind) is complete when it has a
non-empty `description` and, for a function or a method, `params` (a string
or a list, empty when the function takes none) or a non-blank
`usage_signature` (#916: the contract records a call there whole; a list
with a non-blank usage), and a non-empty `return_type`. A missing
description makes an item incomplete; it never makes the inventory
invalid. reconcile-coverage.py's docsOnly branch scores with the same rule.

Shared helpers. The other coverage scripts load these from this file rather
than keep copies: `strip_fences` (score-signatures.py), `completeness`
(reconcile-coverage.py) and the documented-name match, `load_doc_text` and
`names_present` (reconcile-coverage.py, verify-declared-numerator.py,
load-coverage-inputs.py). A name is documented when SKILL.md or a .md file
directly in references/ writes it as a fixed string, case-sensitive, never
inside a longer identifier (the Export match rule of
skf-scan-skill-md-structure.py usage-scope): on a side where the name ends
in a letter, digit, `_` or `$`, the next character may not be one of those.
So `get` is found in `get(url)` but not in `target` or `getAll`. The form
helpers `field_text` and `form_key` are shared too: score-signatures.py
tells an entry's forms apart with them, and the floor check reads a floor
origin's `signature` with `field_text`.

The skill-citation scan is shared too: `_skill_cited_files` (with
`_cited_path`, `skill_markdown_files` and `_SKILL_CITATION_RE`) gives the
files the skill's `[AST:]` and `[SRC:]` citations name on a line of SKILL.md
or references/**/*.md that writes a name with the match above, or on the
next non-blank line. gap-ledger.py reads it to pick the declaration of a
stale homonym, score-signatures.py to plan a signature check at the
declaration the skill cites. A form's own citations are shared the same way
(#918): `form_citations` gives the citations of the form an `at` places, on
its line; on the next non-blank line, unless that line writes the name (it
is another place of the name) or, inside a fenced block, is a comment (it
heads the next declaration), and never after a table row outside a fenced
block, whose own citations are in its cells (the next row documents
another export); for a line
inside a fenced block, on the comment lines just above it in the block;
and, when the block holds no other place the inventory gives the name, on
the block's first non-blank line when it is a comment and on the first
non-blank line after its closing fence unless that line writes the name.
Each comes with the lines it covers (a citation with no `:L<n>` covers its
whole file), and `cites_declaration` says whether they name a declaration:
its file, at a line or in a range that holds a line of its span, from its
line to its last one (a citation of a function's body names it as one of
its `def` line does; score-signatures.py ends a span before the next
declaration the surface records in its file). score-signatures.py plan
binds a form to the one declaration of its name they name (with
`parse_at`, `compared_form` and `skill_markdown_by_path`), but, for a
name declared more than once, never by the citations of a place where the
inventory gives the name two forms that differ (a row that quotes another
declaration's form as a contrast): there each form is bound only by its
other places, if any.

CLI usage (mirrors reconcile-coverage.py):
  uv run validate-inventory.py --input <response file> [--output <inventory file>]
      [--skill-package <package folder>] [--floor <floor file>]
  uv run validate-inventory.py '<raw response>'                 # positional
  uv run validate-inventory.py --json-input '<raw response>'    # explicit flag
  echo '<raw response>' | uv run validate-inventory.py --stdin  # piped input

--input reads the raw response from a file (UTF-8): the coverage-check.md §1
subagent writes its response to the path it is given with the Write tool,
and the parent saves it there with the Write tool when the subagent returned
it instead or left the file absent or empty. coverage-check.md passes that
path, so a quote or an apostrophe in a description never meets a shell.
--output writes the validated inventory object to a file (UTF-8
JSON) when it is valid, for the steps that read it by path; an invalid
inventory removes a file left there by an earlier attempt. --skill-package
names the skill package under test (the folder that holds SKILL.md) and
adds the spot-check and the inventory's `crossChecked` count. --floor names
the floor file (UTF-8 JSON) and adds the floor check.

Input: the subagent's RAW response text (JSON, optionally wrapped in a markdown
code fence — a leading line of three backticks with an optional language tag and
a trailing line of three backticks are stripped before parsing).

Output (stdout, one object; with --output, whose file holds the inventory,
it leaves out `inventory` and `completeness` and gives `output` instead):
  {
    "valid": <bool>,             # true only when parse + every schema check pass
    "violations": [<str>, ...],  # human-readable failures; empty when valid
    "warnings": [<str>, ...],    # each missing or bad `at` (dropped), malformed `undecided`
                                 # item (dropped), floor origin no entry gives as its `at`,
                                 # or mismatch crossChecked leaves out, never a failure
    "rejectedCount": <int>,      # exports[] entries with no valid name or kind
    "exportsCount": <int>,       # len(exports) when parsed; 0 otherwise
    "inventory": {...} | null,   # fence-stripped parsed inventory when valid; null otherwise;
                                 # with --skill-package it carries
                                 # "crossChecked": {"count": <int>, "names": [<name>, ...]},
                                 # plus "uncounted": [{"export", "reference_file", "why"}]
                                 # when a mismatch's `export` is not among `names`
    "completeness": {            # present when valid
      "total": <int>,            # documented items, one per name and kind
      "complete": <int>,
      "incomplete": [{"name", "kind", "missing": ["description", "params", "return_type"]}]
    },
    "spotCheck": {               # with --skill-package, once the schema passed
      "sampled": [<name>, ...],  # the sampled names, in sample order
      "absent": [<name>, ...],   # the sampled names no file writes
      "files": [<path>, ...],    # the files read, relative to the package
      "unread": [<path>, ...]    # listed references that are missing,
    },                           # unreadable or outside the package
    "floor": {                   # with --floor, once the schema passed
      "names": <int>,            # the floor's names
      "checked": <int>,          # those with an origin in SKILL.md or a listed reference
      "absent": [<name>, ...]    # the checked names no inventory entry lists
    },
    "output": <path> | null      # with --output: the file written, null when invalid
  }

Exit codes:
  0  inventory valid (every sampled name found, every checked floor name
     kept and every checked floor signature carried; a missing or bad `at`
     is only a warning, but a labelled floor signature is carried only at
     its own place, and never unlabelled there or with no `at`, and an
     unlabelled one never labelled there or with no `at`)
  1  no input provided, the --input file cannot be read, the
     --skill-package folder holds no readable SKILL.md, or the --floor file
     cannot be read or is not a floor, a malformed `signature` among them
     (usage error)
  2  inventory invalid (parse failure, schema violation, an entry key the
     contract does not define among them, a sampled name
     absent, a floor name left out or a floor signature no entry carries,
     or a labelled one no entry at its place carries with its label, or
     that an entry there or with no `at` gives without it, or an unlabelled
     one an entry there or with no `at` gives with `signature_form`
     "partial";
     result JSON emitted)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import posixpath
import re
import sys
from collections.abc import Iterable
from pathlib import Path

# Fixed enum for exports[].kind — the constructs SKF documents across languages
# and skill types: JS/TS (function/class/type/constant/hook/interface/method),
# Rust public-API items (struct/enum/trait/macro, alongside the shared
# type/constant/function), and stack-composition scaffolds (adapter). Mirrors the
# enum documented in coverage-check.md §1a.
VALID_KINDS = (
    "function",
    "class",
    "type",
    "constant",
    "hook",
    "interface",
    "method",
    "struct",
    "enum",
    "trait",
    "macro",
    "adapter",
)

# The optional exports[].signature_form: `partial` only when the skill labels
# the documented form partial, else `full` (or the key left out).
SIGNATURE_FORMS = ("partial", "full")

REQUIRED_MISMATCH_FIELDS = (
    "export",
    "reference_file",
    "reference_line",
    "issue",
)

# The other side of a cross-check pair, exactly one of these shapes: the
# SKILL.md body's line, or a second reference file and its line.
BODY_SIDE = ("skill_md_line",)
REFERENCE_SIDE = ("other_file", "other_line")
OTHER_SIDE_SHAPES = (
    "`skill_md_line` (the SKILL.md body) or `other_file` and `other_line` "
    "(a second reference file)"
)

# The fields each `undecided` item (#1021) gives as a non-empty string: the name a reading the rules leave open
# concerns, the rule that leaves it open, the reading taken and what the other reading would give. Its place, `at`,
# is optional.
UNDECIDED_FIELDS = ("export", "rule", "reading", "other_gap")

# Kinds whose documented item also needs its parameters and return type to
# be complete (the docs-only Export Coverage rule).
SIGNATURE_KINDS = ("function", "method")

# An entry's signature fields, the ones form_key reads (score-signatures.py reads them from here).
SIGNATURE_FIELDS = ("params", "return_type", "usage_signature")

# The keys an exports[] entry may carry, the contract's (inventory-contract.md lists them in this order). Any
# other is a violation naming the entry (#1001): score-signatures.py reads only SIGNATURE_FIELDS, so a `usage`
# written for `usage_signature` would leave the documented form uncompared.
ENTRY_KEYS = (
    "name",
    "kind",
    "description",
    "params",
    "return_type",
    "usage_signature",
    "signature_form",
    "at",
    "owner",
    "methods",
    "properties",
    "fields",
)

# The fields of a floor origin's `signature` (#888), each a string, and the
# ones the floor check compares with an entry's: `return_type` and either
# `params` (a complete form or a props or parameter cell) or `usage_signature`
# (a usage form, such as `new Client(opts)`).
FLOOR_SIGNATURE_FIELDS = ("params", "usage_signature", "return_type")

# The label a floor origin's `signature` may also give (#888), its key and its
# one value: the partial label of the Signature, Props, Params or Parameters
# column it was read from, or of an ellipsis item in its parameter group
# (#1029), which the entry at that origin copies; an origin with none gives
# its entries none there.
FLOOR_LABEL_FIELD, FLOOR_LABEL = "signature_form", "partial"
# A member that is an ellipsis item alone (score-signatures.py's ELLIPSES): a `params` an entry labels partial at an
# unlabelled pin's place, longer than the pin by members that hold one, is another form, never the pin's copy
# (_another_form, #1043).
ELLIPSIS_ITEMS = ("...", "…")

# Characters that continue an identifier in the languages SKF documents
# (`$` for JS/TS names such as `$state`).
IDENT_CHARS = r"\w$"
_IDENT_RE = re.compile(f"[{IDENT_CHARS}]")

_FENCE_OPEN = re.compile(r"^```[A-Za-z0-9_-]*$")
_FENCE_CLOSE = re.compile(r"^```$")


def strip_fences(text):
    """Remove a wrapping markdown code fence, matching coverage-check.md §1a step 1.

    When the first non-empty line is three backticks (optionally with a language
    tag) and the last non-empty line is three backticks, drop those two lines.
    Otherwise return the text unchanged.
    """
    lines = text.split("\n")
    non_empty_idx = [i for i, ln in enumerate(lines) if ln.strip()]
    if len(non_empty_idx) < 2:
        return text
    first, last = non_empty_idx[0], non_empty_idx[-1]
    if _FENCE_OPEN.match(lines[first].strip()) and _FENCE_CLOSE.match(lines[last].strip()):
        kept = [ln for i, ln in enumerate(lines) if i != first and i != last]
        return "\n".join(kept)
    return text


# --- Documented-name match --------------------------------------------------


def name_pattern(name):
    """Regex for `name` as a fixed string that is never part of a longer identifier.

    The guard only applies on a side where the name itself ends in an
    identifier character, so `.then` still matches inside `promise.then` and
    `Type::method` matches as written.
    """
    body = re.escape(name)
    if _IDENT_RE.match(name[0]):
        body = f"(?<![{IDENT_CHARS}])" + body
    if _IDENT_RE.match(name[-1]):
        body += f"(?![{IDENT_CHARS}])"
    return re.compile(body)


def load_doc_text(skill_package_path):
    """Concatenate SKILL.md ∪ references/*.md text for name lookups.

    Deterministic: references are read in sorted order, a references/
    subfolder does not count. Reads as UTF-8 so non-ASCII exports do not
    mojibake on Windows (cp1252 default).
    """
    root = Path(skill_package_path)
    parts = []
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        parts.append(skill_md.read_text(encoding="utf-8"))
    refs_dir = root / "references"
    if refs_dir.is_dir():
        for ref in sorted(refs_dir.glob("*.md")):
            parts.append(ref.read_text(encoding="utf-8"))
    return "\n".join(parts)


def names_present(names, doc_text):
    """Return the sorted, de-duplicated set of `names` the doc text writes."""
    present = {n for n in names if isinstance(n, str) and n and name_pattern(n).search(doc_text)}
    return sorted(present)


# --- Skill citations ----------------------------------------------------------

# A source citation the skill writes, `[AST:path:L12]`, `[SRC:path:L12-34]` or `[SRC:path:L12-L34]` (one with no
# `:L<n>` part is ignored). Groups: prefix, path, first line, the `L` of a range's end, the range's end.
# Keep identical to _SKILL_CITATION_RE in skf-verify-provenance-completeness.py.
_SKILL_CITATION_RE = re.compile(
    r"\[(AST|SRC):([^\[\]\n]+?):L(\d+)(?:-(L?)(\d+))?\]"
)
# Any bracketed citation (`[AST:...]`, `[SRC:...]`, `[EXT:...]`): a line names a documented name outside them.
_ANY_CITATION_RE = re.compile(r"\[[A-Z]+:[^\[\]\n]*\]")


def _cited_path(path: str) -> str:
    """A cited, `declared_in` or surface path as each compares: forward slashes, no `./`."""
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return posixpath.normpath(path) if path else path


def skill_markdown_files(skill_dir: Path) -> list[Path]:
    """`SKILL.md` then every `references/**/*.md`, in a stable order.
    Keep identical to skill_markdown_files in skf-verify-provenance-completeness.py."""
    files: list[Path] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        files.append(skill_md)
    refs = skill_dir / "references"
    if refs.is_dir():
        files.extend(sorted(p for p in refs.rglob("*.md") if p.is_file()))
    return files


def skill_markdown_by_path(skill_dir: Path) -> dict[str, list[str]]:
    """{the path of each file skill_markdown_files lists, relative to
    `skill_dir` with forward slashes: its lines} (an unreadable one is left
    out), read once for every name or form the citation scan looks up."""
    texts: dict[str, list[str]] = {}
    for path in skill_markdown_files(skill_dir):
        try:
            texts[path.relative_to(skill_dir).as_posix()] = (
                path.read_bytes().decode("utf-8-sig", errors="replace").split("\n"))
        except OSError:
            continue
    return texts


def skill_markdown_lines(skill_dir: Path) -> list[list[str]]:
    """The lines of each file skill_markdown_files lists (an unreadable one is
    left out), read once for every name _skill_cited_files looks up."""
    return list(skill_markdown_by_path(skill_dir).values())


def _skill_cited_files(skill_dir: Path, name: str, texts: list[list[str]] | None = None) -> set[str]:
    """The files the skill's `[AST:]` and `[SRC:]` citations name on a line of
    SKILL.md or references/**/*.md that writes `name` outside its citations
    (the documented-name match), or on the next non-blank line (a heading,
    then its citation). `texts`, skill_markdown_lines(skill_dir) read once,
    spares a caller that looks up many names reading the files again."""
    pattern = name_pattern(name)
    cited: set[str] = set()
    for lines in skill_markdown_lines(skill_dir) if texts is None else texts:
        for number, line in enumerate(lines):
            if not pattern.search(_ANY_CITATION_RE.sub(" ", line)):
                continue
            following = next((ln for ln in lines[number + 1:] if ln.strip()), "")
            for cited_line in (line, following):
                cited.update(_cited_path(m.group(2)) for m in _SKILL_CITATION_RE.finditer(cited_line))
    return cited


# --- A form's place and its own citations (#918) -------------------------------

# An entry's `at`: the place the skill writes its form, "<path>:<line>", the line from 1.
_AT_RE = re.compile(r"(.+):([1-9][0-9]*)")
# A source citation as a form's own citation reads it: one with no `:L<n>` part too, which names every declaration
# in its file. Groups as _SKILL_CITATION_RE's, the line ones absent for no line.
_FORM_CITATION_RE = re.compile(r"\[(AST|SRC):([^\[\]\n]+?)(?::L(\d+)(?:-(L?)(\d+))?)?\]")
# A comment's opening marker: `//`, `#`, `/*`, `--`, `<!--` or `;`. Keep identical to COMMENT_MARKER_RE in
# load-coverage-inputs.py, which reads a fenced block the same way (the floor's `declaration` form).
_COMMENT_MARKER_RE = re.compile(r"[ \t]*(?://+|#+|/\*+|--|<!--|;+)")

_SEGMENTS_MODULE = None


def _segments():
    """locate-export-segments.py beside this script: the fence model the floor reads a skill with."""
    global _SEGMENTS_MODULE
    if _SEGMENTS_MODULE is None:
        sibling = Path(__file__).resolve().parent / "locate-export-segments.py"
        spec = importlib.util.spec_from_file_location("skf_validate_inventory_segments", sibling)
        if spec is None or spec.loader is None or not sibling.is_file():
            raise ImportError(f"locate-export-segments.py not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SEGMENTS_MODULE = module
    return _SEGMENTS_MODULE


_SCORER_MODULE = None


def _scorer():
    """score-signatures.py beside this script, for its `_split`, which cuts a parameter list at the commas outside
    every bracket pair and string: _carries reads a pinned `params` with it (#1028), and the list `params` check
    reads each item with it (#1043). score-signatures.py loads this file only from a call, and `_split` makes
    none, so the two never load each other in a loop."""
    global _SCORER_MODULE
    if _SCORER_MODULE is None:
        sibling = Path(__file__).resolve().parent / "score-signatures.py"
        spec = importlib.util.spec_from_file_location("skf_validate_inventory_scorer", sibling)
        if spec is None or spec.loader is None or not sibling.is_file():
            raise ImportError(f"score-signatures.py not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SCORER_MODULE = module
    return _SCORER_MODULE


def compared_form(entry: dict) -> bool:
    """Whether score-signatures.py plan compares a form the entry's `params`
    or `usage_signature` writes, so the entry carries `at`: an entry that is
    no `method` whose `params` or `usage_signature` is a list or a non-blank
    string, or, for a function, whose `params` is a string (`""`, the form
    of one that takes none). plan also compares a form that writes only a
    `return_type`; that one carries no `at`, so it is never bound."""
    if entry.get("kind") == "method":
        return False
    if entry.get("kind") in SIGNATURE_KINDS and isinstance(entry.get("params"), str):
        return True
    return any(isinstance(entry.get(f), list) or (isinstance(entry.get(f), str) and bool(entry[f].strip()))
               for f in ("params", "usage_signature"))


def parse_at(value: object) -> tuple[str, int] | None:
    """An entry's `at` as (its path, _cited_path, its line), None when it is
    no "<path>:<line>" with a line from 1."""
    m = _AT_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if m is None or not m.group(1).strip():
        return None
    return _cited_path(m.group(1)), int(m.group(2))


def _fence_holding(lines: list[str], index: int) -> tuple[int, int] | None:
    """(its opening fence, its closing fence) of the fenced block whose body
    holds line `index` (from 0), as the floor reads fences
    (locate-export-segments.py's _fenced_blocks past the frontmatter, an
    unclosed block running to the end); None for a line outside every body,
    a fence included."""
    segments = _segments()
    blocks, _ = segments._fenced_blocks(lines, segments._frontmatter_end(lines))
    return next(((opening, closing) for opening, closing, _ in blocks if opening < index < closing), None)


def _first_filled(lines: list[str], start: int) -> str:
    return next((ln for ln in lines[start:] if ln.strip()), "")


def _writes(pattern, line):
    """Whether `line` writes the name `pattern` matches outside its citations (the documented-name match)."""
    return bool(pattern.search(_ANY_CITATION_RE.sub(" ", line)))


def form_citations(lines: list[str], line: int, name: str,
                   others: Iterable[int] = ()) -> set[tuple[str, int | None, int | None]]:
    """The own citations of the form of `name` a skill file writes at `line`
    (from 1, its `at`), from that file's `lines`; `others` are the lines of
    the other places the inventory gives `name` in that file. They are the
    `[AST:]` and `[SRC:]` citations:

    - on that line;
    - on the next non-blank line, unless that line writes `name` outside
      its citations (another place of the name, whose citations are its
      own) or, inside a fenced block, is a comment (it heads the next
      declaration), and never after a table row outside a fenced block
      (locate-export-segments.py's TABLE_ROW_RE, the floor's row), whose
      own citations are in its cells: the next row documents another
      export, and a line after the table is the table's;
    - for a line inside a fenced block (_fence_holding), on the comment
      lines just above it in the block, its own heading;
    - and, when no line of `others` is in that block's body (a block that
      holds two places of the name gives neither its block-wide
      citations), on the block's first non-blank line when it is a comment,
      and on the first non-blank line after its closing fence unless that
      line writes `name`.

    Each is (its file, _cited_path; the first line it covers; the last):
    `:L12` covers line 12, `:L12-34` and `:L12-L34` lines 12 to 34, and a
    citation with no `:L<n>` part gives (its file, None, None), every
    declaration in its file."""
    index = line - 1
    if not 0 <= index < len(lines):
        return set()
    pattern = name_pattern(name)
    fence = _fence_holding(lines, index)
    places = [lines[index]]
    following = _first_filled(lines, index + 1)
    row = fence is None and _segments().TABLE_ROW_RE.match(lines[index])
    if not row and not _writes(pattern, following) and not (fence is not None and _COMMENT_MARKER_RE.match(following)):
        places.append(following)
    if fence is not None:
        opening, closing = fence
        above = index - 1
        while above > opening and _COMMENT_MARKER_RE.match(lines[above]):
            places.append(lines[above])
            above -= 1
        if not any(opening < other - 1 < closing for other in others if other != line):
            heading = _first_filled(lines[opening + 1:closing], 0)
            if _COMMENT_MARKER_RE.match(heading):
                places.append(heading)
            after = _first_filled(lines, closing + 1)
            if not _writes(pattern, after):
                places.append(after)
    cited: set[tuple[str, int | None, int | None]] = set()
    for text in places:
        for m in _FORM_CITATION_RE.finditer(text):
            if m.group(3) is None:
                cited.add((_cited_path(m.group(2)), None, None))
            else:
                first, last = int(m.group(3)), int(m.group(5) or m.group(3))
                cited.add((_cited_path(m.group(2)), min(first, last), max(first, last)))
    return cited


def cites_declaration(citations: set[tuple[str, int | None, int | None]], file: str, line: object,
                      end: int | None = None) -> bool:
    """Whether one of `citations` (form_citations) names the declaration at
    `file` and `line`: it cites that file (both read by _cited_path) with no
    line, or at a line or in a range that holds a line of its span, from
    `line` to `end` (its last line; None for `line` alone). A citation of
    the body names the function as its `def` line does, and a range over
    two declarations names each one it holds a line of."""
    path = _cited_path(file)
    if not _is_line(line):
        return any(cited == path and first is None for cited, first, _ in citations)
    last_line = line if end is None or end < line else end
    return any(cited == path and (first is None or (first <= last_line and line <= last))
               for cited, first, last in citations)


# --- Spot-check -------------------------------------------------------------


def sample_names(exports):
    """The names the spot-check samples: first, middle and last after a stable sort by name.

    >>> sample_names([{"name": n} for n in ("d", "a", "c", "b", "e")])
    ['a', 'c', 'e']
    >>> sample_names([{"name": "b"}, {"name": "a"}])
    ['a', 'b']
    >>> sample_names([])
    []
    """
    named = sorted((e["name"] for e in exports or []
                    if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]))
    picks = []
    for index in (0, len(named) // 2, len(named) - 1):
        if named and named[index] not in picks:
            picks.append(named[index])
    return picks


class PackageError(Exception):
    """The --skill-package folder holds no readable SKILL.md: exit 1."""


def _inside(path, root):
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _package_texts(inventory, skill_package_path):
    """Read the files the inventory reads, for spot_check and cross_checked.

    The file set is the package's SKILL.md plus each `references` entry,
    resolved against the package (a split-body skill documents some exports
    only in a reference file), a listed spelling read once. A listed file
    that is missing, unreadable or resolves outside the package is not read
    and is named in `unread`. Returns `(read, unread)`: `read` holds
    `(spelling, resolved path, text)` for each file read, SKILL.md first.
    Raises PackageError when SKILL.md cannot be read.
    """
    root = Path(skill_package_path)
    real_root = os.path.realpath(root)
    skill_md = root / "SKILL.md"
    try:
        read = [("SKILL.md", os.path.realpath(skill_md), skill_md.read_bytes().decode("utf-8-sig"))]
    except (OSError, UnicodeDecodeError) as exc:
        raise PackageError(f"cannot read {skill_md.as_posix()}: {exc}") from exc
    unread = []
    listed = inventory.get("references")
    for ref in listed if isinstance(listed, list) else []:
        if not isinstance(ref, str) or not ref.strip() or ref in unread or any(ref == r[0] for r in read):
            continue
        target = os.path.realpath(root / ref)
        try:
            if not _inside(target, real_root):
                raise OSError("outside the package")
            read.append((ref, target, Path(target).read_bytes().decode("utf-8-sig")))
        except (OSError, UnicodeDecodeError):
            unread.append(ref)
    return read, unread


def spot_check(inventory, skill_package_path, texts=None):
    """Look the sampled export names up in SKILL.md and the inventory's references.

    The files are _package_texts's (`texts`, its result, when the caller
    read them already): `files` names each one read as the inventory spells
    it, `unread` each listed one that is missing, unreadable or resolves
    outside the package.
    """
    read, unread = texts if texts is not None else _package_texts(inventory, skill_package_path)
    doc_text = "\n".join(text for _, _, text in read)
    sampled = sample_names(inventory.get("exports"))
    found = set(names_present(sampled, doc_text))
    return {
        "sampled": sampled,
        "absent": [name for name in sampled if name not in found],
        "files": [spelling for spelling, _, _ in read],
        "unread": unread,
    }


def cross_checked(exports, texts):
    """The inventory's names that two or more of the files it reads write (#920).

    `texts` is _package_texts's `read`, the spot-check's files. A file
    counts once, by its resolved path, so a reference listed under two
    spellings (`references/a.md`, `./references/a.md`), or SKILL.md listed
    again, is one file. A file writes a name when names_present finds it
    outside its citations, so a mention in prose counts, and a name counts
    once however many entries give it (a homonym). Returns `{"count": <int>,
    "names": [<name>, ...]}`, the names sorted; coherence-check reports the
    count as Exports Cross-Checked.
    """
    names = {entry["name"] for entry in exports
             if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"]}
    found = _names_written(names, texts).values()
    crossed = sorted(name for name in names if sum(name in written for written in found) >= 2)
    return {"count": len(crossed), "names": crossed}


def _names_written(names, texts):
    """The `names` each file of `texts` (_package_texts's `read`) writes outside its citations (names_present), the
    match cross_checked counts by: a dict of each file once, by its resolved path (os.path.normcase), to a set."""
    by_path = {}
    for _, path, text in texts:
        by_path.setdefault(os.path.normcase(path), text)
    return {path: set(names_present(names, _ANY_CITATION_RE.sub(" ", text))) for path, text in by_path.items()}


def _joined(paths):
    """`paths` in backticks, two joined with `and`."""
    return " and ".join(f"`{path}`" for path in paths)


def uncounted_mismatches(cross, exports, texts, names, skill_package_path):
    """The cross_check_mismatches entries the Exports Cross-Checked count leaves out (#1067), with why.

    `cross` is the inventory's mismatch list, each entry checked
    (mismatch_violations, so its files are the package's paths), `texts`
    _package_texts's `read` and `names` cross_checked's `names`. An entry is
    counted when `names` holds its `export`, or the `name` of the `method`
    entry it names as `{owner}.{name}` (_spellings). For one that is not,
    the reason is the first that applies to its pair's two files, the other
    side's (`SKILL.md` for `skill_md_line`, else `other_file`) and then
    `reference_file`: both resolve to one path (cross_checked counts a file
    once); a file is not one `texts` holds (`references` does not list it,
    or it cannot be read); or a file does not write it, by cross_checked's
    match (_names_written). A pair of two lines of one file, or one naming
    a reference the inventory does not read, passes the schema, so this is
    never a violation. Returns `(index, item)` pairs in list order, each
    item `{"export", "reference_file", "why"}`.
    """
    root = Path(skill_package_path)
    written = _names_written({e["name"] for e in exports if _spellings(e)}, texts)
    uncounted = []
    for idx, entry in enumerate(cross):
        export = entry["export"]
        stands_for = {e["name"] for e in exports if export in _spellings(e)}
        if not stands_for.isdisjoint(names):
            continue
        files = ["SKILL.md" if entry.get("skill_md_line") is not None else entry["other_file"],
                 entry["reference_file"]]
        paths = [os.path.normcase(os.path.realpath(root / file)) for file in files]
        unread = [file for file, path in zip(files, paths) if path not in written]
        if paths[0] == paths[1]:
            why = (f"its two places are in one file, `{entry['reference_file']}`, and the count takes only a name "
                   "two or more files write")
        elif len(unread) == 1:
            why = (f"{_joined(unread)} is not a file the inventory reads (`references` does not list it, or it "
                   "cannot be read)")
        elif unread:
            why = (f"{_joined(unread)} are not files the inventory reads (`references` does not list them, or they "
                   "cannot be read)")
        else:
            silent = [file for file, path in zip(files, paths) if stands_for.isdisjoint(written[path])]
            if len(silent) == 1:
                why = f"{_joined(silent)} does not write it"
            elif silent:
                why = f"{_joined(silent)} do not write it"
            else:
                why = "fewer than two of the files the inventory reads write it"
        uncounted.append((idx, {"export": export, "reference_file": entry["reference_file"], "why": why}))
    return uncounted


# --- Signature forms ----------------------------------------------------------


def field_text(value: object) -> str:
    """A signature field as one text: a list's items joined with `, `, whitespace runs as one space, "" for null."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(v if isinstance(v, str) else json.dumps(v, sort_keys=True) for v in value)
    return " ".join(value.split()) if isinstance(value, str) else json.dumps(value, sort_keys=True)


def form_key(fields: dict) -> tuple:
    """What a form says, for telling two entries apart (field_text), a
    null, blank or empty key read as absent, and the `signature_form` label
    left out (score-signatures.py's documented_forms keeps the full one)."""
    return tuple((f, field_text(fields[f])) for f in SIGNATURE_FIELDS if f in fields and field_text(fields[f]))


# A type-parameter list that opens a generic function type (`fn: <T, U>(x: T) => U`), closed just before the
# parameter group it opens. No name comes before its `<`, so _levels reads it as an operator and its commas would
# cut the member (_parameter_members masks them).
TYPE_PARAMETERS_RE = re.compile(r"<[^<>]*(?:<[^<>]*>[^<>]*)*>(?=\s*\()")
# A numpy docstring-style member (`timeout : float, optional`, `n : int, default 5`) and the marker after its type,
# which follows a comma and is no parameter of its own.
NUMPY_MEMBER_RE = re.compile(r"\s*\*{0,2}[A-Za-z_]\w*\s+:\s")
NUMPY_MARKER_RE = re.compile(r",\s*(?:optional|default\b.*)\s*$", re.IGNORECASE | re.S)
# The name a member gives before its `:`, `?:` or `=` (`fn: LifespanFn`, `...rest: T[]`, `**kw = None`); a `::`
# (`std::string s`) or `==` gives none.
MEMBER_NAME_RE = re.compile(r"\s*(?:\.\.\.|\*{1,2})?([A-Za-z_$][\w$]*)\s*\??\s*(?::(?!:)|=(?!=))")
# The text before a whole form's parameter group: none, or a name with its receiver and type parameters (`actions`,
# `client.get`, `run<T>`). `func` and `fn` open a function type instead (Go's `func(int)`), and a return follows the
# group after `->`, `=>`, `→` or `:`.
FORM_HEAD_RE = re.compile(r"(?:[A-Za-z_$][\w$.]*(?:<[^()]*>)?)?")
FUNCTION_TYPE_HEADS = ("func", "fn")
FORM_RETURN_RE = re.compile(r"->|=>|→|:")
# A Rust lifetime after a `&`, a `+` or a `<` (`&'a str`, `impl Tr + 'a`, `Foo<'a>`): an item that writes one is cut
# as a `.rs` form is, so its `'` opens no string, while a quote anywhere else still does (`Omit<P, 'a,b'>`).
RUST_LIFETIME_RE = re.compile(r"(?:&|\+\s*|<)'[A-Za-z_]\w*(?=[\s,>+)]|$)")


def _extension(text: str) -> str:
    """The extension _split and _group read an item as: `.rs` when it writes a Rust lifetime (RUST_LIFETIME_RE),
    else none."""
    return ".rs" if RUST_LIFETIME_RE.search(text) else ""


def _parameter_members(text: str) -> list[str]:
    """The members `text` writes as a parameter list: cut at each comma outside every bracket pair and string, as
    score-signatures.py cuts one (_split, which reads a Rust lifetime's `'`, as in `&'a str`, as no quote:
    _extension), each stripped, the blank ones dropped. `handlerMap: Record<T, string>`, `sep: str = ", "`,
    `options: { a?: string, b: number }`, a generic function type (`fn: <T, U>(x: T) => U`, TYPE_PARAMETERS_RE) and
    a numpy docstring-style member with its marker (`timeout : float, optional`) are one member each."""
    if NUMPY_MEMBER_RE.match(text):
        while (marker := NUMPY_MARKER_RE.search(text)) is not None:
            text = text[:marker.start()]
    text = TYPE_PARAMETERS_RE.sub(lambda m: m.group(0).replace(",", " "), text)
    return [part.strip() for part in _scorer()._split(text, ",", _extension(text)) if part.strip()]


def _whole_form(text: str) -> bool:
    """Whether a list `params` item writes a whole form, not one member: a parameter group that spans it, with at most
    a name right before it (FORM_HEAD_RE) and nothing or a return after it (`(a: int, b: int)`, `actions(...h: T[])`,
    `run(a) -> int`). A member whose own type is a function type (`cb: (x: T) => void`, Go's `func(int)`) is none,
    and so is a Google docstring-style member, whose name a space parts from its group (`timeout (float, optional)`)."""
    text = text.strip()
    group = _scorer()._group(text, _extension(text))
    if group is None:
        return False
    head, tail = text[:group[0]], text[group[1] + 1:].strip()
    return (FORM_HEAD_RE.fullmatch(head) is not None and head not in FUNCTION_TYPE_HEADS
            and (not tail or FORM_RETURN_RE.match(tail) is not None))


def params_violations(idx: int, entry: dict) -> list[str]:
    """A list `params` holds the members of one parameter list, one per item, and field_text joins its items into
    that list with `, `, so a place that writes several forms of a name (two overloads in one row) gives each form an
    entry of its own at that same `at` (#1043). A list of two or more string items reads as one form per item, whose
    join matches none of them, when one item holds several parameters (_parameter_members), when one writes a whole
    form (_whole_form), or when two give one name before their `:`, `?:` or `=` (MEMBER_NAME_RE; `_` aside, which
    Rust and Go let a list repeat), since no parameter list names a parameter twice: one violation naming the entry
    and each such item, and saying what to write instead, the whole list as one string included. A one-item list,
    whose join is its item, and an item that is no string are not read."""
    params = entry.get("params")
    if not isinstance(params, list) or len(params) < 2:
        return []
    texts = [item for item in params if isinstance(item, str)]
    several = [item for item in texts if len(_parameter_members(item)) > 1]
    whole = [item for item in texts if item not in several and _whole_form(item)]
    named = [(m.group(1), item) for item in texts if (m := MEMBER_NAME_RE.match(item)) and m.group(1) != "_"]
    twice = [name for i, (name, _) in enumerate(named) if name not in [n for n, _ in named[:i]]
             and sum(n == name for n, _ in named) > 1]

    def listed(items: list[str]) -> str:
        return ", ".join(json.dumps(item, ensure_ascii=False) for item in items)

    problems = []
    if several:
        problems.append(f"item {listed(several)} holds several parameters" if len(several) == 1
                        else f"items {listed(several)} hold several parameters")
    if whole:
        problems.append(f"item {listed(whole)} writes a whole form" if len(whole) == 1
                        else f"items {listed(whole)} write whole forms")
    for name in twice:
        problems.append(f"items {listed([item for n, item in named if n == name])} each name `{name}`")
    if not problems:
        return []
    return [(f"exports[{idx}] (`{entry['name']}`): the `params` {'; '.join(problems)}, but a list `params` is "
             "one parameter list, one member per item, its items joined into it: when each item is a form of its own "
             "(an overload), give each form its own entry with that same `at`; otherwise write each member as an "
             "item of its own, or the whole list as one string")]


# --- Floor ------------------------------------------------------------------


class FloorError(Exception):
    """The --floor file cannot be read or is not a floor: exit 1."""


def _is_signature(value):
    """A floor origin's `signature`: an object of the string `return_type` and exactly one of the string `params` and
    a non-blank string `usage_signature` (a usage form, #888), and optionally `signature_form` "partial" (a column's
    partial label, #888); any other key or value is not one."""
    if not isinstance(value, dict):
        return False
    form = set(value) - {FLOOR_LABEL_FIELD, "return_type"}
    return ("return_type" in value and len(form) == 1 and form <= set(FLOOR_SIGNATURE_FIELDS)
            and all(isinstance(value[f], str) for f in form | {"return_type"})
            and (form != {"usage_signature"} or bool(value["usage_signature"].strip()))
            and value.get(FLOOR_LABEL_FIELD, FLOOR_LABEL) == FLOOR_LABEL)


def _is_origin(origin):
    return (isinstance(origin, dict) and isinstance(origin.get("file"), str) and bool(origin["file"])
            and isinstance(origin.get("line"), int) and not isinstance(origin["line"], bool)
            and isinstance(origin.get("form"), str)
            and ("signature" not in origin or _is_signature(origin["signature"])))


def read_floor(path):
    """The floor load-coverage-inputs.py floor wrote to `path`, its shape checked."""
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise FloorError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FloorError(f"{path} is not JSON: {exc.msg}") from exc
    names = data.get("names") if isinstance(data, dict) else None
    if not isinstance(names, list) or not all(
            isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
            and isinstance(item.get("origins"), list) and all(_is_origin(o) for o in item["origins"])
            for item in names):
        raise FloorError(f"{path} is not a floor: `names` must give each name's `name` and `origins` "
                         "(each a file, a line and a form, and an optional `signature` of the string "
                         "`return_type` and either the string `params` or a non-blank string `usage_signature`, "
                         "and an optional `signature_form` \"partial\")")
    return data


def _listed_path(ref, skill_package_path):
    """A listed reference as a floor origin names it: relative to the package, forward slashes. An absolute
    path inside the package is made relative to it (it needs the package to be)."""
    if skill_package_path is not None and os.path.isabs(ref):
        target, root = os.path.realpath(ref), os.path.realpath(skill_package_path)
        if _inside(target, root):
            return Path(os.path.relpath(target, root)).as_posix()
    return _cited_path(ref)


def _members(text):
    """A parameter list's members, each as field_text gives it, cut at the commas outside every bracket pair and
    string (score-signatures.py's _split, so `Dict[str, int]` stays one member), an empty last one dropped."""
    members = [field_text(member) for member in _scorer()._split(text, ",")]
    return members[:-1] if members and not members[-1] else members


def _others(given, wanted):
    """The members of the `params` text `given` besides the members of `wanted`, which it holds in their order, the
    others before, among or after them, or None when it does not hold them so."""
    rest, others = iter(_members(given)), []
    for member in _members(wanted):
        for item in rest:
            if item == member:
                break
            others.append(item)
        else:
            return None
    return others + list(rest)


def _holds_in_order(given, wanted):
    """Whether the `params` text `given` holds each member of `wanted` in its order, other members before, among
    or after them (#1028: the whole list the contract has an entry write when the skill puts a name's own member
    before or among the members it states once for several names, a `...` among those included)."""
    return _others(given, wanted) is not None


def _another_form(entry, signature, place):
    """Whether an entry that carries an unlabelled floor origin's signature at its `place` (_carries) is another
    form the place writes, never the pin's copy (#1043): its `at` is that place, it gives `signature_form`
    "partial", which the signature does not, and its `params` is longer than the pinned one by members that hold an
    ellipsis item (`...` or `…` alone), as a row's second overload (`run(task: Task)` or `run(task: Task, ...)`)
    labelled by its own `...` is. It neither carries the pin nor has its label refused as one added to it, while an
    unlabelled such list is the pin's copy, the shared members spelled out with a `...` among them (#1028), and a
    labelled longer list with no `...` there is the pin's form, its label refused (#1029)."""
    if FLOOR_LABEL_FIELD in signature or entry.get(FLOOR_LABEL_FIELD) != FLOOR_LABEL:
        return False
    if parse_at(entry.get("at")) != place or "params" not in signature:
        return False
    others = _others(field_text(entry.get("params")), field_text(signature["params"]))
    return others is not None and any(item in ELLIPSIS_ITEMS for item in others)


def _carries(entry, signature, place):
    """Whether an entry carries a floor origin's signature: each field the signature gives (`params` or
    `usage_signature`, and `return_type`) and pins non-blank has the same field_text there, a `params` or
    `usage_signature` that opens with members the skill states once for several names (the contract's shared text,
    then `; `) included, and, for an entry whose `at` is the origin's `place` (parse_at), a `params` whose members
    hold the pinned ones in their order among others (_holds_in_order, #1028): a longer list elsewhere or with no
    `at` is another form of the name, which neither carries the pin nor stands in for its copy; and, when it gives
    the partial label (#888), the entry's `signature_form` is that label too. floor_check also sets aside, at an
    unlabelled pin, a labelled longer list a `...` makes longer (_another_form, #1043)."""
    if FLOOR_LABEL_FIELD in signature and entry.get(FLOOR_LABEL_FIELD) != signature[FLOOR_LABEL_FIELD]:
        return False
    here = parse_at(entry.get("at")) == place
    for field in FLOOR_SIGNATURE_FIELDS:
        if field not in signature:
            continue
        wanted, given = field_text(signature[field]), field_text(entry.get(field))
        if wanted and given != wanted and not (field != "return_type" and given.endswith("; " + wanted)) and not (
                here and field == "params" and _holds_in_order(given, wanted)):
            return False
    return True


def _origin_signature(origin):
    """A floor origin's signature, the fields it gives (#888: `params` or `usage_signature`, and `return_type`) and
    its label only when it gives one."""
    return {f: origin["signature"][f] for f in FLOOR_SIGNATURE_FIELDS + (FLOOR_LABEL_FIELD,)
            if f in origin["signature"]}


def floor_check(inventory, floor, skill_package_path=None):
    """The floor names and signatures the inventory leaves out: (the `floor` result, its violations, its warnings).

    A floor name is checked when one of its origins is SKILL.md or a file
    the inventory's `references` lists (the spot-check's files, an absolute
    path inside `skill_package_path` matched by its path relative to it),
    and kept when any inventory entry has that name, whatever its kind. A
    name left out is a violation naming its first checked origin. Then each
    checked origin with a `signature` is carried when an entry of that name,
    whatever its kind, gives the same field_text to each field the
    signature pins non-blank (its `params` or, for a usage form, its
    `usage_signature`, and its `return_type`; a blank pinned `return_type`
    leaves the entry's free; a `params` or `usage_signature` may open with
    shared text and `; `, and the `params` of an entry whose `at` is that
    origin may hold the pinned members in their order among others,
    _carries); one no entry carries is a violation
    naming the origin and the signature, for a name left out too. A carried
    origin is placed when an entry that carries it gives that origin as its
    `at` (parse_at; #918). When none does, the `at` of each entry that
    carries it is dropped with a warning (_drop), unless it is a checked
    origin whose signature that entry carries. When none is dropped and each
    still has an `at`, a place at another such origin, the origin is a
    warning of its own: the citations there are not read. An entry left with
    no `at` has a warning already when its form is compared, so the origin
    adds none. A misplaced form never makes the inventory invalid, except
    one whose signature gives the partial label (#888): it is placed only by
    the entries of that name whose `at` is that origin and that give its
    form, at least one and each with its `signature_form`, while each entry
    of that name with no `at` (none given, or a bad one at_warnings or
    place_warnings dropped first) that gives that form gives the label too.
    It is otherwise one violation, a carrier elsewhere or with no `at`, an
    unlabelled twin there and an unlabelled copy with no `at` included; an
    unlabelled copy whose `at` is another place (with the package, a line
    that writes the name) stays valid. An origin whose signature gives no
    label is refused the same way when an entry of that name that gives its
    form there or with no `at` gives `signature_form` "partial" (#1029): one
    violation, while a labelled copy whose `at` is another place stays
    valid, and a second overload its place writes, labelled by its own
    `...`, is no copy of it (_another_form, #1043).
    """
    listed = inventory.get("references")
    files = {"SKILL.md"} | {_listed_path(ref, skill_package_path)
                            for ref in (listed if isinstance(listed, list) else [])
                            if isinstance(ref, str) and ref.strip()}
    entries = [(idx, e) for idx, e in enumerate(inventory.get("exports") or []) if isinstance(e, dict)]
    kept = {e.get("name") for _, e in entries}
    names = floor.get("names") or []
    checked, absent, violations, warnings, signed = 0, [], [], [], []
    for item in names:
        origins = [o for o in item["origins"] if _cited_path(o["file"]) in files]
        if not origins:
            continue
        checked += 1
        name = item["name"]
        signed += [(name, o) for o in origins if "signature" in o]
        if name in kept:
            continue
        absent.append(name)
        where = f"{origins[0]['file']}:{origins[0]['line']} ({origins[0]['form']})"
        violations.append(f"floor: `{name}` is documented at {where}, but no inventory entry lists it")

    def carried(entry):
        """The checked origins of the entry's name whose signature it carries, (path, line) as parse_at gives."""
        places = [((_cited_path(o["file"]), o["line"]), o) for n, o in signed if n == entry.get("name")]
        return {place for place, o in places if _carries(entry, _origin_signature(o), place)}

    for name, origin in signed:
        signature = _origin_signature(origin)
        place = (_cited_path(origin["file"]), origin["line"])
        pinned = (f"floor: `{name}` is documented at {origin['file']}:{origin['line']} ({origin['form']}) with the "
                  f"signature {json.dumps(signature, ensure_ascii=False)}")
        at = json.dumps(f"{place[0]}:{place[1]}")
        if FLOOR_LABEL_FIELD in signature:
            # A labelled pin (#888) is placed only at its own `at`: the entries of the name there that give its form
            # are at least one, and each of them and each one with no `at` (a bad one is dropped by now) gives its
            # label, so no unlabelled twin, nor a copy that shows no place, is the form score-signatures.py keeps. A
            # copy whose `at` is another place is compared there.
            form = {f: signature[f] for f in FLOOR_SIGNATURE_FIELDS if f in signature}
            copies = [e for _, e in entries if e.get("name") == name and _carries(e, form, place)]
            here = [e for e in copies if parse_at(e.get("at")) == place]
            if not here or not all(_carries(e, signature, place) for e in copies
                                   if e.get("at") is None or parse_at(e["at"]) == place):
                violations.append(f"{pinned}, but no inventory entry of that name at that place carries it, or one "
                                  f"gives its form without its `signature_form` there or with no `at`; copy it as "
                                  f"given, with `at` {at}")
            continue
        # A second overload the pinned place writes, labelled by its own `...`, is another form (#1043): it neither
        # carries the pin nor has its label refused, while an unlabelled list a `...` makes longer is still the pin's
        # copy, the shared members spelled out (#1028).
        carriers = [(idx, e) for idx, e in entries if e.get("name") == name and _carries(e, signature, place)
                    and not _another_form(e, signature, place)]
        if any(e.get(FLOOR_LABEL_FIELD) == FLOOR_LABEL and (e.get("at") is None or parse_at(e["at"]) == place)
               for _, e in carriers):
            # An unlabelled pin's label is the floor's too (#1029): an entry that gives its form there or with no
            # `at` (a bad one is dropped by now) and labels it partial would turn a left-out optional parameter's
            # Critical into Info where the skill gives no label. A labelled copy whose `at` is another place is
            # compared there.
            violations.append(f"{pinned}, but an inventory entry of that name gives its form with `signature_form` "
                              f"\"partial\" there or with no `at`, a label the floor does not pin; copy it as given, "
                              f"without that label, with `at` {at}")
            continue
        if any(parse_at(e.get("at")) == place for _, e in carriers):
            continue
        if not carriers:
            violations.append(f"{pinned}, but no inventory entry of that name carries it; copy it as given, "
                              f"with `at` {at}")
            continue
        dropped = [_drop(e, f"{pinned}, but exports[{idx}], which carries it, gives `at` {json.dumps(e['at'])}")
                   for idx, e in carriers
                   if parse_at(e.get("at")) is not None and parse_at(e["at"]) not in carried(e)]
        if dropped:
            warnings += dropped
        elif all(e.get("at") is not None for _, e in carriers):
            warnings.append(f"{pinned}, but no inventory entry that carries it gives `at` {at}, so the citations "
                            "there are not read")
    return {"names": len(names), "checked": checked, "absent": absent}, violations, warnings


# --- Completeness -------------------------------------------------------------


def _filled(value):
    return isinstance(value, str) and bool(value.strip())


def missing_fields(entry):
    """The fields a documented item lacks to be complete (docs-only rule)."""
    missing = []
    if not _filled(entry.get("description")):
        missing.append("description")
    if entry.get("kind") in SIGNATURE_KINDS:
        usage = entry.get("usage_signature")
        if not isinstance(entry.get("params"), (str, list)) and not any(
                map(_filled, usage if isinstance(usage, list) else [usage])):
            missing.append("params")
        if not _filled(entry.get("return_type")):
            missing.append("return_type")
    return missing


def completeness(exports):
    """Count complete documented items: one item per name and kind.

    An item the inventory lists twice is complete when either entry is.
    Entries without a string name or a known kind are not items.
    """
    items = {}
    for entry in exports or []:
        if not isinstance(entry, dict):
            continue
        name, kind = entry.get("name"), entry.get("kind")
        if not (isinstance(name, str) and name) or kind not in VALID_KINDS:
            continue
        missing = missing_fields(entry)
        key = (name, kind)
        if key not in items or not missing:
            items[key] = missing
    incomplete = [{"name": name, "kind": kind, "missing": missing}
                  for (name, kind), missing in items.items() if missing]
    return {
        "total": len(items),
        "complete": len(items) - len(incomplete),
        "incomplete": incomplete,
    }


# --- Validation ---------------------------------------------------------------


def _reference_path(value, skill_package_path=None):
    """A pair's file as the package names it (`_listed_path`: relative, forward slashes, no `./`), or None when
    it is no `references/**/*.md` file of the package: empty, not a string, `SKILL.md`, another file, or an
    absolute path outside the package (or with no package to make it relative to)."""
    if not isinstance(value, str) or not value.strip():
        return None
    path = _listed_path(value.strip(), skill_package_path)
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "references" or ".." in parts or not parts[-1].endswith(".md") \
            or parts[-1] == ".md":
        return None
    return path


def _is_line(value):
    """A line number: a positive integer, never a bool or a string."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _spellings(entry):
    """The spellings a mismatch's `export` may name one entry by (mismatch_names): its non-empty string `name`,
    and `{owner}.{name}` for a `method` entry whose `owner` is a non-empty string; none for an entry with no
    such `name`."""
    if not (isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"]):
        return ()
    if entry.get("kind") == "method" and isinstance(entry.get("owner"), str) and entry["owner"]:
        return entry["name"], f"{entry['owner']}.{entry['name']}"
    return (entry["name"],)


def mismatch_names(exports):
    """The spellings a mismatch's `export` may take (#1033): each entry's non-empty string `name`, and
    `{owner}.{name}` for a `method` entry whose `owner` is a non-empty string. The contract asks for the bare
    `name`, the one `crossChecked` lists; the qualified one is accepted so a reader that writes it is not refused."""
    return {spelling for entry in exports for spelling in _spellings(entry)}


def mismatch_violations(idx, entry, skill_package_path=None, names=None):
    """The violations of one cross_check_mismatches entry (an object).

    A required field left out; an `export` that is not a non-empty string
    or, given `names` (mismatch_names), not one of them (#1033: §5b titles a
    split-body gap with it); a `reference_file` or `other_file` that is no
    `references/**/*.md` path of the package; a line that is no positive
    integer; an other side that is not exactly one shape, `skill_md_line` or
    both of `other_file` and `other_line` (a JSON null counts as absent); or a
    pair of references out of order: (`other_file`, `other_line`) must sort
    before (`reference_file`, `reference_line`) in codepoint order, so the pair
    has one title. Each path is checked, and left in the entry, as the package
    names it, relative and with forward slashes.
    """
    where = f"cross_check_mismatches[{idx}]"
    violations = []
    missing = [f for f in REQUIRED_MISMATCH_FIELDS if f not in entry]
    if missing:
        violations.append(f"{where} missing field(s): {', '.join(missing)}")
    if "export" in entry:
        export = entry["export"]
        if not (isinstance(export, str) and export) or (names is not None and export not in names):
            violations.append(f"{where}: `export` must name an inventory entry, by its `name` (a `method`'s bare "
                              "`name`, or `{owner}.{name}` for one that gives an `owner`), "
                              f"not {json.dumps(export)}")
    ref = None
    if "reference_file" in entry:
        ref = _reference_path(entry["reference_file"], skill_package_path)
        if ref is None:
            violations.append(f"{where}: `reference_file` must be a `references/*.md` file of the skill package, "
                              f"not {json.dumps(entry['reference_file'])}")
        else:
            entry["reference_file"] = ref
    lines_ok = True
    for field in ("reference_line",) + BODY_SIDE + REFERENCE_SIDE[1:]:
        given = entry.get(field) is not None or (field == "reference_line" and field in entry)
        if given and not _is_line(entry[field]):
            lines_ok = False
            violations.append(f"{where}: `{field}` must be a line number (a positive integer), "
                              f"not {json.dumps(entry[field])}")
    body = [f for f in BODY_SIDE if entry.get(f) is not None]
    reference = [f for f in REFERENCE_SIDE if entry.get(f) is not None]
    if body and reference:
        violations.append(f"{where} gives two other sides: give one, {OTHER_SIDE_SHAPES}")
        return violations
    if not body and not reference:
        violations.append(f"{where} missing its other side: give {OTHER_SIDE_SHAPES}")
        return violations
    if body:
        return violations
    absent = [f for f in REFERENCE_SIDE if f not in reference]
    if absent:
        violations.append(f"{where} missing field(s): {', '.join(absent)}; its other side is "
                          f"{OTHER_SIDE_SHAPES}")
        return violations
    other = _reference_path(entry["other_file"], skill_package_path)
    if other is None:
        violations.append(f"{where}: `other_file` must be a `references/*.md` file of the skill package, "
                          f"not {json.dumps(entry['other_file'])}")
        return violations
    entry["other_file"] = other
    if ref is None or not lines_ok or "reference_line" not in entry:
        return violations
    first, last = (other, entry["other_line"]), (ref, entry["reference_line"])
    if not first < last:
        relation = "names the same line as" if first == last else "sorts after"
        violations.append(
            f"{where}: `other_file` {json.dumps(other)} at `other_line` {first[1]} {relation} "
            f"`reference_file` {json.dumps(ref)} at `reference_line` {last[1]}: a pair of references gives the "
            "one that sorts first in codepoint order, by path and then line, as `other_file` and `other_line`, "
            "and the one that sorts last as `reference_file` and `reference_line`"
        )
    return violations


def undecided_violations(value, source=""):
    """The violations of an optional `undecided` list (#1021): each reading the
    inventory contract or signature-comparison-rules.md leaves open that an
    inventory, or a signature judge's result, rests on. Absent or null is
    none; otherwise it is a list of objects, each giving `export`, `rule`,
    `reading` and `other_gap` as non-empty strings and, when it gives one, an
    `at` that is a non-empty string. `source` names where the list is read
    (drop_undecided turns each into a warning, never a violation).

    >>> undecided_violations(None), undecided_violations([])
    ([], [])
    >>> undecided_violations([{"export": "x", "rule": "r", "reading": "a", "other_gap": "g", "at": None}])
    []
    >>> undecided_violations([3, {"export": "x", "rule": " ", "reading": "a", "other_gap": "g"}], "s.txt")
    ['s.txt.undecided[0] is not an object', 's.txt.undecided[1]: `rule` must be a non-empty string']
    """
    if value is None:
        return []
    if not isinstance(value, list):
        prefix = f"{source}: " if source else ""
        return [f"{prefix}`undecided` must be a list when present (may be empty), not {json.dumps(value)}"]
    violations = []
    for idx, item in enumerate(value):
        where = f"{source}.undecided[{idx}]" if source else f"undecided[{idx}]"
        if not isinstance(item, dict):
            violations.append(f"{where} is not an object")
            continue
        for field in UNDECIDED_FIELDS:
            if not (isinstance(item.get(field), str) and item[field].strip()):
                violations.append(f"{where}: `{field}` must be a non-empty string")
        if item.get("at") is not None and not (isinstance(item["at"], str) and item["at"].strip()):
            violations.append(f"{where}: `at` must be a non-empty string when present, not {json.dumps(item['at'])}")
    return violations


def drop_undecided(holder, source=""):
    """Each problem of `holder`'s optional `undecided` list (undecided_violations) as a warning, never a violation
    (#1021): the list grades nothing, so a malformed one never makes an inventory or a judge's result invalid, never
    sends a reader or judge back and never halts a run. Each item with a problem is dropped from the list, the
    well-formed ones kept in order, and a value that is no list is dropped from `holder`.

    >>> holder = {"undecided": [{"export": "x", "rule": "r", "reading": "a", "other_gap": "g"}, 3]}
    >>> drop_undecided(holder), [item["export"] for item in holder["undecided"]]
    (['undecided[1] is not an object; the item is dropped'], ['x'])
    >>> holder = {"undecided": "none"}
    >>> drop_undecided(holder), holder
    (['`undecided` must be a list when present (may be empty), not "none"; the list is dropped'], {})
    """
    value = holder.get("undecided")
    problems = undecided_violations(value, source)
    if not problems:
        return []
    if not isinstance(value, list):
        del holder["undecided"]
        return [f"{problem}; the list is dropped" for problem in problems]
    holder["undecided"] = [item for item in value if not undecided_violations([item])]
    return [f"{problem}; the item is dropped" for problem in problems]


def _read_files(inventory, skill_package_path=None):
    """The files the inventory reads, as an `at` names them: `SKILL.md` and
    each `references` entry, _listed_path (relative to the package, forward
    slashes)."""
    listed = inventory.get("references")
    return {"SKILL.md"} | {_listed_path(ref, skill_package_path)
                           for ref in (listed if isinstance(listed, list) else [])
                           if isinstance(ref, str) and ref.strip()}


# What a missing or dropped `at` leaves its entry's form (#918): plan binds it to no declaration, as before #918.
UNBOUND = "the form is compared as one whose citations name no declaration"


def _drop(entry, why):
    """Drop the entry's bad `at` (#918) and return its warning: `why`, then what the drop leaves (UNBOUND, for an
    entry that carries a compared form)."""
    del entry["at"]
    return f"{why}; it is dropped and {UNBOUND}" if compared_form(entry) else f"{why}; it is dropped"


def at_warnings(idx, entry, files, skill_package_path=None):
    """The warnings of one named entry's `at` (#918), never a violation: an
    entry that carries a compared form (compared_form) and no `at` (a JSON
    null removed), or an `at` (on any entry) that is no "<path>:<line>" with
    a line from 1, or whose path is no file of `files` (_read_files), which
    is dropped (_drop). A good `at` is left in the entry as the package
    names it, "<path>:<line>" (_listed_path)."""
    where = f"exports[{idx}] (`{entry['name']}`)"
    value = entry.get("at")
    if value is None:
        entry.pop("at", None)
        return [f"{where} carries a form but no `at`, so {UNBOUND}"] if compared_form(entry) else []
    m = _AT_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if m is None or not m.group(1).strip():
        return [_drop(entry, f"{where}: `at` must be \"<path>:<line>\", a file of the package and a line from 1 "
                             f"(\"SKILL.md:42\"), not {json.dumps(value)}")]
    path = _listed_path(m.group(1).strip(), skill_package_path)
    if path not in files:
        return [_drop(entry, f"{where}: `at` names {json.dumps(path)}, no file the inventory reads: SKILL.md or a "
                             "file `references` lists")]
    entry["at"] = f"{path}:{int(m.group(2))}"
    return []


def place_warnings(inventory, skill_package_path):
    """With the package: each entry's `at` (one at_warnings kept) is a line
    of its file that writes the entry's name outside its citations, or, for
    a line inside a fenced block (_fence_holding), one of a block that
    writes it. A file that cannot be read (missing, unreadable or outside
    the package), a line past its end and a line that does not write the
    name each drop the `at` with a warning naming the entry (_drop)."""
    root = Path(skill_package_path)
    real_root = os.path.realpath(root)
    read: dict[str, list[str] | None] = {}
    warnings = []
    for idx, entry in enumerate(inventory.get("exports") or []):
        if not isinstance(entry, dict) or entry.get("at") is None:
            continue
        path, line = parse_at(entry["at"])
        if path not in read:
            target = os.path.realpath(root / path)
            try:
                if not _inside(target, real_root):
                    raise OSError("outside the package")
                read[path] = _segments()._split_lines(Path(target).read_bytes().decode("utf-8-sig"))
            except (OSError, UnicodeDecodeError):
                read[path] = None
        lines, name = read[path], entry["name"]
        where = f"exports[{idx}] (`{name}`): `at` {json.dumps(entry['at'])}"
        if lines is None:
            warnings.append(_drop(entry, f"{where} names a file that cannot be read"))
            continue
        if line > len(lines):
            warnings.append(_drop(entry, f"{where} is past the end of {path} ({len(lines)} lines)"))
            continue
        pattern = name_pattern(name)
        if _writes(pattern, lines[line - 1]):
            continue
        fence = _fence_holding(lines, line - 1)
        if fence is not None and any(_writes(pattern, ln) for ln in lines[fence[0] + 1:fence[1]]):
            continue
        held = ", nor does the fenced block that holds it" if fence is not None else ""
        warnings.append(_drop(entry, f"{where} is a line that does not write `{name}`{held}"))
    return warnings


def validate_inventory(raw, skill_package_path=None, floor=None):
    """Structural validation of the subagent inventory response, then the spot-check and the floor check.

    `raw` is the raw response text. Returns the result dict documented in the
    module docstring. With `skill_package_path`, an inventory that passed the
    schema is spot-checked against the package (spot_check), given its
    `crossChecked` count (cross_checked), with `uncounted` and a warning for
    each mismatch the count leaves out (uncounted_mismatches, #1067), and
    each `at` is looked up there (place_warnings); a `crossChecked` the
    response carries never survives.
    With `floor` (read_floor's object),
    it is checked against the floor (floor_check). A missing or bad `at` is
    a warning, the bad one dropped, never a violation (#918).
    Deterministic: identical input yields an identical verdict.
    """
    violations, warnings = [], []
    inner = strip_fences(raw)
    try:
        data = json.loads(inner)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "violations": [f"subagent response not valid JSON: {exc.msg}"],
            "warnings": [],
            "rejectedCount": 0,
            "exportsCount": 0,
            "inventory": None,
        }

    if not isinstance(data, dict):
        return {
            "valid": False,
            "violations": ["subagent response is not a JSON object"],
            "warnings": [],
            "rejectedCount": 0,
            "exportsCount": 0,
            "inventory": None,
        }
    # The validator alone writes `crossChecked` (#920): a reader's never survives.
    data.pop("crossChecked", None)

    exports = data.get("exports")
    if not isinstance(exports, list):
        violations.append(
            "missing/typo: `exports` must be present and a list"
        )
        exports = []

    cross = data.get("cross_check_mismatches")
    if not isinstance(cross, list):
        violations.append(
            "missing/typo: `cross_check_mismatches` must be present and a list (may be empty)"
        )
        cross = []

    # Per-entry export validation — count rejections.
    rejected = 0
    for idx, entry in enumerate(exports):
        if not isinstance(entry, dict):
            rejected += 1
            continue
        name = entry.get("name")
        kind = entry.get("kind")
        if not (isinstance(name, str) and name):
            rejected += 1
            continue
        if kind not in VALID_KINDS:
            rejected += 1
            continue
        # A list `params` is one parameter list, one member per item (#1043).
        violations.extend(params_violations(idx, entry))
    if rejected > 0:
        subject = "entry does" if rejected == 1 else "entries do"
        violations.append(
            f"{rejected} exports[] {subject} not match schema "
            f"(each needs a non-empty string `name` and a `kind` in "
            f"{{{', '.join(VALID_KINDS)}}})"
        )

    # The optional signature_form names one of two forms, or is left out.
    for idx, entry in enumerate(exports):
        if isinstance(entry, dict) and entry.get("signature_form") is not None \
                and entry["signature_form"] not in SIGNATURE_FORMS:
            label = f" (`{entry['name']}`)" if isinstance(entry.get("name"), str) and entry["name"] else ""
            violations.append(
                f"exports[{idx}]{label}: `signature_form` must be `partial` or `full` when present, "
                f"not {json.dumps(entry['signature_form'])}"
            )

    # An entry carries only the contract's keys (#1001), whatever their values: each entry with another is a
    # violation naming those keys, in the entry's order, and the contract's.
    entry_keys = ", ".join(f"`{k}`" for k in ENTRY_KEYS[:-1]) + f" and `{ENTRY_KEYS[-1]}`"
    for idx, entry in enumerate(exports):
        unknown = [f"`{k}`" for k in entry if k not in ENTRY_KEYS] if isinstance(entry, dict) else []
        if unknown:
            label = f" (`{entry['name']}`)" if isinstance(entry.get("name"), str) and entry["name"] else ""
            named = unknown[0] if len(unknown) == 1 else ", ".join(unknown[:-1]) + f" and {unknown[-1]}"
            verb = "is not a key" if len(unknown) == 1 else "are not keys"
            violations.append(
                f"exports[{idx}]{label}: {named} {verb} the contract defines; an entry carries only {entry_keys}"
            )

    # Each entry that carries a compared form is asked for its place, `at`, in a file the inventory reads (#918):
    # one missing or bad is a warning, the bad one dropped.
    files = _read_files(data, skill_package_path)
    for idx, entry in enumerate(exports):
        if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"]:
            warnings.extend(at_warnings(idx, entry, files, skill_package_path))

    # Each cross-check mismatch carries its fields and one other side of its
    # pair, a pair of references in order, and an `export` naming an entry (#1033).
    names = mismatch_names(exports)
    for idx, entry in enumerate(cross):
        if not isinstance(entry, dict):
            violations.append(f"cross_check_mismatches[{idx}] is not an object")
            continue
        violations.extend(mismatch_violations(idx, entry, skill_package_path, names))

    # Each reading the rules leave open (#1021) names its export, rule, reading and other gap; the inventory keeps
    # the list for reconcile-coverage.py to carry to the report. It grades nothing, so a malformed item is a warning
    # and is dropped, never a reason to refuse the inventory.
    warnings.extend(drop_undecided(data))

    schema_valid = not violations
    checked = None
    if schema_valid and skill_package_path is not None:
        texts = _package_texts(data, skill_package_path)
        checked = spot_check(data, skill_package_path, texts)
        for name in checked["absent"]:
            violations.append(
                f"spot-check: `{name}` is listed as an export, but SKILL.md and the "
                f"listed reference files never write it"
            )
        # In the inventory object, so the --output file carries it.
        data["crossChecked"] = cross_checked(exports, texts[0])
        # A mismatch the count leaves out (#1067) is named with why, in the inventory, so the Reference
        # Consistency section can say so beside the count, and warned about, never refused.
        uncounted = uncounted_mismatches(cross, exports, texts[0], data["crossChecked"]["names"], skill_package_path)
        if uncounted:
            data["crossChecked"]["uncounted"] = [item for _, item in uncounted]
            warnings.extend(f"cross_check_mismatches[{idx}] (`{item['export']}`): Exports Cross-Checked does not "
                            f"count it, since {item['why']}" for idx, item in uncounted)
        warnings.extend(place_warnings(data, skill_package_path))
    floor_result = None
    if schema_valid and floor is not None:
        floor_result, floor_violations, floor_warnings = floor_check(data, floor, skill_package_path)
        violations.extend(floor_violations)
        warnings.extend(floor_warnings)

    valid = not violations
    result = {
        "valid": valid,
        "violations": violations,
        "warnings": warnings,
        "rejectedCount": rejected,
        "exportsCount": len(exports),
        "inventory": data if valid else None,
    }
    if valid:
        result["completeness"] = completeness(exports)
    if checked is not None:
        result["spotCheck"] = checked
    if floor_result is not None:
        result["floor"] = floor_result
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="validate-inventory",
        description=(
            "Deterministic schema validation of the §1 subagent inventory JSON "
            "(coverage-check.md §1a). Strips wrapping fences, parses, and asserts "
            "the required-keys/types/enum/mismatch-field contract, then with "
            "--skill-package spot-checks sampled names against the package and --floor checks it "
            "keeps the floor's names, returning "
            "{valid, violations, warnings, rejectedCount, exportsCount, inventory, completeness, spotCheck, floor} "
            "(with --output, `output` in place of inventory and completeness)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "raw_input",
        nargs="?",
        help="Raw subagent response as a positional argument.",
    )
    src.add_argument(
        "--json-input",
        dest="raw_input_flag",
        help="Raw subagent response passed via flag (overrides positional).",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the raw subagent response from stdin.",
    )
    src.add_argument(
        "--input",
        dest="input_file",
        metavar="PATH",
        help="Read the raw subagent response from this file (UTF-8).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write the validated inventory to this file when it is valid, and print the result without it.",
    )
    parser.add_argument(
        "--skill-package",
        metavar="DIR",
        help="Spot-check sampled names against this package's SKILL.md and listed references, "
        "and add their crossChecked count to the inventory, with each cross_check_mismatches entry "
        "the count leaves out and why (crossChecked.uncounted, also a warning).",
    )
    parser.add_argument(
        "--floor",
        metavar="PATH",
        help="Check the inventory keeps the names and signatures of this load-coverage-inputs.py floor file.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.input_file is not None:
        return Path(args.input_file).read_bytes().decode("utf-8-sig")
    if args.raw_input_flag is not None:
        return args.raw_input_flag
    if args.raw_input is not None:
        return args.raw_input
    return ""


def write_json(path, payload):
    """Write `payload` as indented UTF-8 JSON with a final newline."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        raw = _resolve_input(args)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read --input {args.input_file}: {exc}", file=sys.stderr)
        return 1
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print(
            "error: no input provided (positional arg, --json-input, --stdin or --input)",
            file=sys.stderr,
        )
        return 1

    try:
        floor = read_floor(args.floor) if args.floor is not None else None
    except FloorError as exc:
        print(f"error: --floor: {exc}", file=sys.stderr)
        return 1
    try:
        result = validate_inventory(raw, args.skill_package, floor)
    except PackageError as exc:
        print(f"error: --skill-package: {exc}", file=sys.stderr)
        return 1
    if args.output:
        if result["valid"]:
            write_json(args.output, result["inventory"])
        else:
            Path(args.output).unlink(missing_ok=True)
        # The step reads the inventory from the file, and no step reads its completeness on stdout, so stdout keeps
        # the verdict and the checks and names the file, null when none was written (#1040).
        result = {key: value for key, value in result.items() if key not in ("inventory", "completeness")}
        result["output"] = args.output if result["valid"] else None
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 2


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    raise SystemExit(main())
