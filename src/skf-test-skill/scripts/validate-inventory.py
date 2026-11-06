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
`partial` or `full`, and assert each cross-check mismatch carries its fields
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
and one of the order names both places.

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
(#888: the `params` and `return_type` the skill writes there in a fixed
form) is carried when an entry of that name, whatever its kind, reads as it
does: each of `params` and `return_type` the signature pins non-blank gives
the same field_text (whitespace runs as one space, a list's items joined
with `, `, a null field as blank), and a `params` that opens with the shared
text the contract has several names' entries carry, then `; `, carries the
pinned one after it. A field the signature leaves blank, and the entry's
other fields, a `usage_signature` among them, are not read.
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

Distinct from reconcile-coverage.py (coverage numerator arithmetic) and
compute-score.py (weight tables): this script only validates the *shape* of the
subagent inventory and, on success, echoes the fence-stripped parsed inventory
back so the prompt consumes it directly instead of re-parsing the raw response.

It also reports each documented item's completeness, the docs-only Export
Coverage rule: an item (one name and kind) is complete when it has a
non-empty `description` and, for a function or a method, `params` (a string
or a list, empty when the function takes none) and a non-empty
`return_type`. A missing description makes an item incomplete; it never
makes the inventory invalid. reconcile-coverage.py's docsOnly branch scores
with the same rule.

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
declaration the skill cites.

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
adds the spot-check. --floor names the floor file (UTF-8 JSON) and adds the
floor check.

Input: the subagent's RAW response text (JSON, optionally wrapped in a markdown
code fence — a leading line of three backticks with an optional language tag and
a trailing line of three backticks are stripped before parsing).

Output (stdout, one object):
  {
    "valid": <bool>,             # true only when parse + every schema check pass
    "violations": [<str>, ...],  # human-readable failures; empty when valid
    "rejectedCount": <int>,      # exports[] entries with no valid name or kind
    "exportsCount": <int>,       # len(exports) when parsed; 0 otherwise
    "inventory": {...} | null,   # fence-stripped parsed inventory when valid; null otherwise
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
    }
  }

Exit codes:
  0  inventory valid (every sampled name found, every checked floor name
     kept and every checked floor signature carried)
  1  no input provided, the --input file cannot be read, the
     --skill-package folder holds no readable SKILL.md, or the --floor file
     cannot be read or is not a floor, a malformed `signature` among them
     (usage error)
  2  inventory invalid (parse failure, schema violation, a sampled name
     absent, a floor name left out or a floor signature no entry carries;
     result JSON emitted)
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
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

# Kinds whose documented item also needs its parameters and return type to
# be complete (the docs-only Export Coverage rule).
SIGNATURE_KINDS = ("function", "method")

# An entry's signature fields, the ones form_key reads (score-signatures.py reads them from here).
SIGNATURE_FIELDS = ("params", "return_type", "usage_signature")

# The fields of a floor origin's `signature` (#888), each a string, and the
# ones the floor check compares with an entry's.
FLOOR_SIGNATURE_FIELDS = ("params", "return_type")

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


def skill_markdown_lines(skill_dir: Path) -> list[list[str]]:
    """The lines of each file skill_markdown_files lists (an unreadable one is
    left out), read once for every name _skill_cited_files looks up."""
    texts: list[list[str]] = []
    for path in skill_markdown_files(skill_dir):
        try:
            texts.append(path.read_bytes().decode("utf-8-sig", errors="replace").split("\n"))
        except OSError:
            continue
    return texts


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


def spot_check(inventory, skill_package_path):
    """Look the sampled export names up in SKILL.md and the inventory's references.

    The file set is the package's SKILL.md plus each `references` entry,
    resolved against the package (a split-body skill documents some exports
    only in a reference file). A listed file that is missing, unreadable or
    resolves outside the package is not read and is named in `unread`.
    """
    root = Path(skill_package_path)
    real_root = os.path.realpath(root)
    try:
        texts = [(root / "SKILL.md").read_bytes().decode("utf-8-sig")]
    except (OSError, UnicodeDecodeError) as exc:
        raise PackageError(f"cannot read {(root / 'SKILL.md').as_posix()}: {exc}") from exc
    files, unread = ["SKILL.md"], []
    listed = inventory.get("references")
    for ref in listed if isinstance(listed, list) else []:
        if not isinstance(ref, str) or not ref.strip() or ref in files or ref in unread:
            continue
        target = os.path.realpath(root / ref)
        try:
            if not _inside(target, real_root):
                raise OSError("outside the package")
            texts.append(Path(target).read_bytes().decode("utf-8-sig"))
            files.append(ref)
        except (OSError, UnicodeDecodeError):
            unread.append(ref)
    doc_text = "\n".join(texts)
    sampled = sample_names(inventory.get("exports"))
    found = set(names_present(sampled, doc_text))
    return {
        "sampled": sampled,
        "absent": [name for name in sampled if name not in found],
        "files": files,
        "unread": unread,
    }


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


# --- Floor ------------------------------------------------------------------


class FloorError(Exception):
    """The --floor file cannot be read or is not a floor: exit 1."""


def _is_signature(value):
    """A floor origin's `signature`: an object of exactly the strings `params` and `return_type`."""
    return (isinstance(value, dict) and sorted(value) == sorted(FLOOR_SIGNATURE_FIELDS)
            and all(isinstance(value[f], str) for f in FLOOR_SIGNATURE_FIELDS))


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
                         "(each a file, a line and a form, and an optional `signature` of the strings "
                         "`params` and `return_type`)")
    return data


def _listed_path(ref, skill_package_path):
    """A listed reference as a floor origin names it: relative to the package, forward slashes. An absolute
    path inside the package is made relative to it (it needs the package to be)."""
    if skill_package_path is not None and os.path.isabs(ref):
        target, root = os.path.realpath(ref), os.path.realpath(skill_package_path)
        if _inside(target, root):
            return Path(os.path.relpath(target, root)).as_posix()
    return _cited_path(ref)


def _carries(entry, signature):
    """Whether an entry carries a floor origin's signature: each field it pins non-blank has the same field_text
    there, a `params` that opens with members the skill states once for several names (the contract's shared
    text, then `; `) included."""
    for field in FLOOR_SIGNATURE_FIELDS:
        wanted, given = field_text(signature[field]), field_text(entry.get(field))
        if wanted and given != wanted and not (field == "params" and given.endswith("; " + wanted)):
            return False
    return True


def floor_check(inventory, floor, skill_package_path=None):
    """The floor names and signatures the inventory leaves out: (the `floor` result, its violations).

    A floor name is checked when one of its origins is SKILL.md or a file
    the inventory's `references` lists (the spot-check's files, an absolute
    path inside `skill_package_path` matched by its path relative to it),
    and kept when any inventory entry has that name, whatever its kind. A
    name left out is a violation naming its first checked origin. Then each
    checked origin with a `signature` is carried when an entry of that name,
    whatever its kind, gives the same field_text to each field the
    signature pins non-blank (a blank pinned `return_type` leaves the
    entry's free; a `params` may open with shared text and `; `, _carries);
    one no entry carries is a violation naming the origin and the
    signature, for a name left out too.
    """
    listed = inventory.get("references")
    files = {"SKILL.md"} | {_listed_path(ref, skill_package_path)
                            for ref in (listed if isinstance(listed, list) else [])
                            if isinstance(ref, str) and ref.strip()}
    entries = [e for e in inventory.get("exports") or [] if isinstance(e, dict)]
    kept = {e.get("name") for e in entries}
    names = floor.get("names") or []
    checked, absent, violations, signed = 0, [], [], []
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
    for name, origin in signed:
        signature = {f: origin["signature"][f] for f in FLOOR_SIGNATURE_FIELDS}
        if any(_carries(e, signature) for e in entries if e.get("name") == name):
            continue
        where = f"{origin['file']}:{origin['line']} ({origin['form']})"
        violations.append(f"floor: `{name}` is documented at {where} with the signature "
                          f"{json.dumps(signature, ensure_ascii=False)}, but no inventory entry of that name "
                          "carries it; copy it as given")
    return {"names": len(names), "checked": checked, "absent": absent}, violations


# --- Completeness -------------------------------------------------------------


def _filled(value):
    return isinstance(value, str) and bool(value.strip())


def missing_fields(entry):
    """The fields a documented item lacks to be complete (docs-only rule)."""
    missing = []
    if not _filled(entry.get("description")):
        missing.append("description")
    if entry.get("kind") in SIGNATURE_KINDS:
        if not isinstance(entry.get("params"), (str, list)):
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


def mismatch_violations(idx, entry, skill_package_path=None):
    """The violations of one cross_check_mismatches entry (an object).

    A required field left out; a `reference_file` or `other_file` that is no
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


def validate_inventory(raw, skill_package_path=None, floor=None):
    """Structural validation of the subagent inventory response, then the spot-check and the floor check.

    `raw` is the raw response text. Returns the result dict documented in the
    module docstring. With `skill_package_path`, an inventory that passed the
    schema is spot-checked against the package (spot_check); with `floor`
    (read_floor's object), it is checked against the floor (floor_check).
    Deterministic: identical input yields an identical verdict.
    """
    violations = []
    inner = strip_fences(raw)
    try:
        data = json.loads(inner)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "violations": [f"subagent response not valid JSON: {exc.msg}"],
            "rejectedCount": 0,
            "exportsCount": 0,
            "inventory": None,
        }

    if not isinstance(data, dict):
        return {
            "valid": False,
            "violations": ["subagent response is not a JSON object"],
            "rejectedCount": 0,
            "exportsCount": 0,
            "inventory": None,
        }

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

    # Each cross-check mismatch carries its fields and one other side of its
    # pair, a pair of references in order.
    for idx, entry in enumerate(cross):
        if not isinstance(entry, dict):
            violations.append(f"cross_check_mismatches[{idx}] is not an object")
            continue
        violations.extend(mismatch_violations(idx, entry, skill_package_path))

    schema_valid = not violations
    checked = None
    if schema_valid and skill_package_path is not None:
        checked = spot_check(data, skill_package_path)
        for name in checked["absent"]:
            violations.append(
                f"spot-check: `{name}` is listed as an export, but SKILL.md and the "
                f"listed reference files never write it"
            )
    floor_result = None
    if schema_valid and floor is not None:
        floor_result, floor_violations = floor_check(data, floor, skill_package_path)
        violations.extend(floor_violations)

    valid = not violations
    result = {
        "valid": valid,
        "violations": violations,
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
            "{valid, violations, rejectedCount, exportsCount, inventory, completeness, spotCheck, floor}."
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
        help="Write the validated inventory to this file when it is valid.",
    )
    parser.add_argument(
        "--skill-package",
        metavar="DIR",
        help="Spot-check sampled names against this package's SKILL.md and listed references.",
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
