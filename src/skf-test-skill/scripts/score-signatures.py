#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Signature Accuracy and Type Coverage for SKF test-skill, from checked per-file results.

coverage-check.md section 2 compares each documented signature with the
source and section 2b scores two categories from the comparison: Signature
Accuracy and Type Coverage, 22% and 14% of a contextual score. Which
signature differs is a judgment, made by a subagent that reads the source;
everything after it has one answer per input and runs here: the list of
signatures to compare, the schema check of each subagent result, the two
ratios and the gap records of the wrong signatures.

  plan   the comparisons to make. For each documented export with a
         signature (an inventory entry of any kind but `method` that carries
         `params`, `return_type` or `usage_signature`; a function's `params`
         counts when empty, its form for one that takes none; a `constant`
         holding a component carries the form the skill writes as
         `usage_signature`, references/inventory-contract.md says, and a data
         constant none) in the signature universe, grouped by source file,
         with the line that defines it in the source, the documented
         signature (with the entry's `signature_form` when it has one; of
         several entries of one name, one that lists parameters or gives a
         usage form before one that does neither, then a full one before a
         partial one, then, of two full or two partial forms, one that lists
         parameters before one that gives only a usage form, else the first)
         and, as `alternatives`, the name's other distinct forms that list
         parameters or give a usage form, then those that list neither but
         state a return type (a `return_type` neither blank nor a list of
         value names, #914), in that order: the judge compares the
         declaration with each, by its own reading rules, and reports a
         mismatch for each form that does not match, naming it as `form`. A
         form that lists no member and states no return type is never an
         alternative, and two entries that say the same thing are one form
         (a `full` label and none, a list and its items joined with `, `,
         whitespace runs; of two that differ only by the partial label, the
         full one). The signature universe is the
         surface's `all` set plus every name on its export records, so the
         names of a Python sub-package load-coverage-inputs.py keeps out of
         `all` (excluded.nestedEntries) keep their checks. A check sits at the
         name's first surface record (one with a file before one with none
         or a blank one and, in one file, one with a line before one with
         none). A line-less record of a file another of the name's records
         gives a line, as _path reads both, is skipped (_lined_records), a
         `./src/a.py` one that sorts first by raw path beside `src/a.py` at a
         line included: it is never the check's record, never a candidate
         and never a declaration. For a name the surface records in more
         than one file, --skill-dir (the skill package) picks the record
         whose file the skill cites on a line that names it
         (validate-inventory.py's _skill_cited_files) when exactly one of
         those files is cited; otherwise the check stays at the first record
         and lists every record with a file, a skipped one aside, as
         `candidates` for the judge to read. With --skill-dir a form is also
         bound (#918) to the one
         declaration of its name its own citations name: the citations of
         the places the inventory's `at` gives its entries
         (validate-inventory.py's form_citations): on that line; on the
         next non-blank line, unless that line writes the name (another
         place of it) or, in a fenced block, is a comment (it heads the next
         declaration), and never after a table row, whose own citations are
         in its cells (the next row documents another export); in a fenced
         block, on
         the comment lines just above it; and, when the block holds no other
         place the inventory gives the name, on the block's first non-blank
         line when it is a comment and on the first non-blank line after its
         closing fence unless that line writes the name. A place where the
         inventory gives the name two forms that differ (a table row that
         documents one declaration's form and quotes another's as a
         contrast) gives none of them a citation: each is bound only by its
         other places, and a form written only there is compared as one with
         no own citation (_shared_places); two entries that say the same
         thing at one place are one form, as everywhere. A citation names a
         declaration when it cites its file with no line, or at a line or in
         an `L` range that holds a line of its span (cites_declaration):
         from its line to the line before the next declaration the surface
         records in its file, of any name, an other declaration included, or
         to the end of the file when none follows (_span_end). So a citation
         of a function's body names it, and a range over two declarations
         names both. The extraction records no declaration's last line, so a
         span runs past its body, over any helper the surface does not
         record, to the next declaration it does.
         The declarations are the name's surface records with a file, a
         skipped line-less one aside, and its `otherDeclarations` (one the
         extraction records in a file no record of the name names, such as a
         same-named function a lazy re-export passes on, which no entry point
         exports), each once per file and line. A form whose citations name
         exactly one is listed in the
         check's `bound` with its index and that declaration, and the judge
         compares it with that declaration alone, whatever the check's
         location and candidates; a form whose citations name none or two,
         and a form that writes only a `return_type` (it gives no `at`), is
         compared as before. An other declaration is never the planned
         record and never a candidate: it reaches the judge only as a bound
         form's declaration. With no form bound the plan is the one a
         surface without `otherDeclarations` gives. Also the whole
         documented-signature map, and each name's alternatives, for the
         fallback scan that has no surface lines yet.
  score  the categories. Reads every subagent result, checks its schema,
         and computes:
           Signature Accuracy = matching / compared * 100, where compared is
             the documented signatures of the signature universe (with a
             fallback scan's exports_found) and matching those no result
             names in a Critical mismatch: a wrong signature is wrong
             whichever set the denominator counts
           Type Coverage = documented types / total types * 100, where
             total types counts the names of the --surface-set set (the
             denominator set coverage-check section 2b picked) whose kind is
             a type kind (TYPE_KINDS: interface, type alias, enum and class,
             with a Rust struct counted as a class and a trait as an
             interface) and documented types those the inventory documents;
             a name the stale-scope guard restored (#913) or the extraction
             recorded with no kind, such as an extraction gap (#1020), whose
             kind the provenance map does not give is left out and named in
             `warnings`, in place of the warning that the surface has no type
         A category with nothing to compare scores 100 (nothing documented
         is wrong) and says so in `warnings`. Each signature mismatch of a
         compared name is graded (grade()) against the documented form its
         `form` names (0, or none, the check's `documented`; n its nth
         `alternatives` entry; an index past the name's forms is listed in
         `warnings` and graded against `documented`), by that form's own
         `signature_form`. With --plan the forms are the plan's (a name whose
         forms differ from the inventory's is listed in `warnings`). Each
         becomes a record in the gap ledger's record format (gap-ledger.py append --input reads
         --gaps-output). The judge's `difference` tag alone never lowers a
         grade: the script checks the fact each one rests on.
           Low `signature-mismatch`  `difference` "parameter-name" reported
             at a file the plan offered for the name (the file it sent the
             check to, or a candidate), when that file is of a language
             whose callers cannot pass an argument by its name
             (POSITIONAL_EXTENSIONS: TS/JS, Go, Rust, Java, C, C++; never
             Python, whose positional-only parameters the script cannot see,
             nor a Vue component, whose props callers set by name)
           Info `observation`, titled `Partial signature: {name}`
             `difference` "omitted-optional" on a documented signature whose
             inventory entry is `signature_form` "partial"
           Info `observation`, titled `Annotation contradicted: {name}`
             `difference` "annotation-contradicted" (the documented return
             type is the one the body returns, the declared annotation says
             otherwise) whose facts check: the documented entry states a
             return type (a `return_type`, or the return a `documented_sig`
             writes, that is neither blank nor a list of value names:
             _states_return); `documented_sig` and `source_sig` write the
             same parameters as signature-comparison-rules.md reads them
             (_parameter_difference, below), read from the form when it
             gives no usage form and lists no parameter (#1025): one with
             no `params` writes no parameter list and claims nothing about
             parameters, so this fact holds, and a blank `params` (`""` or
             `[]`) claims the export takes none, so `()` is compared with
             `source_sig`; `evidence_line` comes after the
             declaration line (of the name's surface records at the
             mismatch's file, the closest at or before the mismatch's
             `line`, else the first; with none, the mismatch's `line`) and
             before the next surface record in that file (a bound form's
             declaration line is its bound declaration's, and each bound
             declaration counts as a surface record there); and, with
             --source-root, that line of the file under it starts with
             `return`, or is the declaration line itself with its
             expression body after its parameters (an arrow function's
             `=> expr`, a Python `def ...: return x`). The parameters are
             read from each one's parameter group, past a decorator's, a Go
             receiver's or a C++ `operator()`'s group (a qualifier such as
             `noexcept(...)` after a group leaves it the parameter group),
             and compared by name and in order, by name alone after a `*`
             marker; by type wherever both write one, with the common
             Equivalent spellings (_type_key, which reads a type through a
             module or namespace path on one side only as the bare name it
             ends in, though it cannot see that both name one declaration),
             a documented type that names
             some members of the source's union included, and, in a TS/JS
             file, with a literal default's type for a source parameter
             that writes none; by optionality when the documented list
             states one for some member; and by the type parameters both
             write before the group. A list of bare names need not write an
             optional parameter (unless leaving it out shifts a caller's
             positions in a POSITIONAL_EXTENSIONS file), and one holding an
             ellipsis claims nothing about what it stands for. A keyword or
             name before the group, a default's value, a `*` or `/` marker,
             the names of `*args` and `**kwargs`, and a leading receiver the
             source writes (`self`, `cls`, `&self`, `&'a self`, `&mut self`,
             `mut self`, `this: T`) are never compared; the documented
             list's own receiver is dropped only when the source's list
             leads with one too, so a module-level
             function whose first parameter is named `self` or `cls` is read
             as a method. A signature with no group, on either side, is
             compared by the text before its return. Still refused, on the
             strict side, where the rules would read the two as one: type
             variables renamed consistently, a type alias against the type
             it names, a parameter type written as a description
             (`Pydantic BaseModel`, `Union (many)`, compared as its text),
             an overload set, a union of callables against one
             callable returning the union, a module path inside a type
             read as one text (a callable's arrow), a `typing.`,
             `collections.abc.` or `React.` prefix aside, or written with
             `::` (Rust's `std::path::PathBuf`), a call example's `name=value`
             (read as a default, so its list claims to be complete) or
             positional literal (`RecursiveSplitter(512)`, read as a name),
             a call's `*items` or `**mapping` argument (read as a `*args`
             or `**kwargs` the source must declare, so `Settings(**config)`
             against `__init__(self, host, port)` differs),
             two module paths to one declaration (`a.Foo` against `b.Foo`),
             a destructured parameter (compared as one name, so the order of
             its properties and the ones it leaves out count), a parameter
             in another language's order (Go's `id string`, C's `int n`,
             read as one name), and a `;`-joined text, read as written. Its
             remediation changes nothing in the skill: the annotation is
             reported upstream. A tagged mismatch whose facts do not check is
             graded as an untagged one, and `warnings` names the fact that
             failed
           Critical `signature-mismatch`  every other mismatch
         A mismatch's `file` (normalized: `/` separated, no `./`) is the file
         it is graded and recorded at (the gap's Source) when the plan
         offered that file for the name: the file of its check or one of the
         check's candidates, read from --plan, else every file the surface
         records for the name. Any other `file` is listed in `warnings`, and
         the result's `file` stands, as it does when there is none. A
         mismatch of a form the plan bound (`bound`, #918) is taken at its
         bound declaration's file and line instead, whatever file the judge
         names, and a judge that names another one (or none, from a group in
         another file) is listed in `warnings`; the declaration joins no
         name, set or count, and the gap's title and form index are the
         form's as for any other mismatch. Results
         that report one declaration (name, file and line) more than once
         keep its most severe grade: Critical, then Low, then Info. Of the
         mismatches of one unbound form of a check that offered several
         files, the least severe stands (the closest candidate), the first by
         file and line on a tie: one documented form, one gap. Each form's mismatch
         stands on its own (each usage of a `usage_signature` list too: the
         mismatch's `documented_sig` is part of the declaration's key), and
         a gap of a name with several forms names its form, counted from 1,
         in its title (`Signature mismatch: {name} (form n of m)`) and its
         Issue. For such a name the form's own label lowers a grade only when
         the mismatch's `documented_sig` is that form's text (whitespace runs
         as one, outer parentheses off, a list joined, a name or a dotted
         receiver before the parameters left off, and a blank or absent
         `params` read as `()` for a form with no usage form): otherwise the
         mismatch is graded against the form it quotes, which `warnings`
         names, or, when it quotes none, stays at the form its `form` names
         (that form's title, Issue and bound declaration, #919) and is graded
         as a full form, which `warnings` says when that form is not
         `documented` or is partial. A Low or an Info mismatch still counts
         as matching. A mismatch a result reports for any
         other name (one the skill does not document, or the surface lacks)
         is listed in `warnings` instead, and no gap.

Inputs, all files in the run folder:
  --inventory  the validated inventory validate-inventory.py wrote (--output)
  --surface    load-coverage-inputs.py surface output: `exports[]` (name,
               kind, file, line, signatureLine), the name `sets` and
               `otherDeclarations` (the same fields; a declaration plan may
               bind a form to, never a name it compares or counts);
               --surface-set picks the set (default "all") score's Type
               Coverage counts, while plan and Signature Accuracy compare
               the signature universe whichever set it picks
  --results    a subagent result, as the subagent returned it (a wrapping
               markdown fence is stripped), repeatable. One object, or a
               list of them:
                 {"file": "<source file>",
                  "exports_found": ["..."],     (fallback scan only)
                  "types_found": ["..."],       (fallback scan only)
                  "signature_mismatches": [
                    {"name", "line", "source_sig", "documented_sig", "issue",
                     "difference", "file", "evidence_line", "form"}]}
                                      (difference optional: one of
                                       DIFFERENCES, absent or null for none;
                                       file optional: the candidate the
                                       mismatch was found at, a non-empty
                                       string, absent or null for the
                                       result's `file`; evidence_line, the
                                       body line that returns the documented
                                       type, an integer from 1, required
                                       with "annotation-contradicted" and
                                       refused with any other difference;
                                       form optional: the index of the
                                       documented form the mismatch is
                                       reported for, an integer from 0
                                       (`documented`; n the check's nth
                                       `alternatives` entry), absent or null
                                       for 0)
  --skill-dir  plan only: the skill package under test (the folder that
               holds SKILL.md), whose citations pick the declaration of a
               name the surface records in several files, and bind each form
               whose own citations name one declaration of its name to it
  --plan       score only: the plan's output, whose checks name the files a
               mismatch of each name may be recorded at, and the declaration
               each bound form's mismatch is taken at
  --source-root  score only: the local source tree the judges read (a
               drifted workspace included), where an annotation-contradicted
               mismatch's `evidence_line` is checked in its file

Rounding is compute-score.py's (JS-compatible half-up, two decimals).

Usage:
  uv run score-signatures.py plan --inventory <file> [--surface <file>] [--skill-dir <dir>] [--output <file>]
  uv run score-signatures.py score --inventory <file> --surface <file> [--surface-set <set>] [--plan <file>] \\
      [--source-root <dir>] --results <file> [--results <file> ...] [--output <file>] [--gaps-output <file>]

Output (stdout; --output also writes it, --gaps-output writes the records;
plan with --output writes the plan and prints only its summary):
  plan:  {"compared": N, "files": [{"file", "checks": [{"name", "line",
          "signatureLine", "documented": {...}, "alternatives": [{...}]
          (only when the name has another form that lists members or
          states a return type),
          "candidates": [{"file", "line", "signatureLine"}] (only when the
          citation does not settle the declaration), "bound": [{"form",
          "file", "line", "signatureLine"}] (only when a form's own
          citations name one declaration of the name)}]}],
          "documentedSignatures": {...}, "documentedAlternatives": {name:
          [{...}], for each name with alternatives}}
         or, with --output, the summary {"compared": N, "files": the
         number of files[] entries, "checks": the number of checks,
         "documented": the number of documentedSignatures entries,
         "output": the --output path}
         `line` and `signatureLine` are null on a check, a candidate or a
         `bound` entry whose surface record has no line: a name read by eye
         alone in its file, whose per-file result lists names only, or a
         record with no file. The judge finds a declaration that has a file
         in that `file` and gives its mismatch the line it found there
         (#1022). A check whose record has no file sits under the `files[]`
         entry "", which names no file to read: a judge reads only its
         `bound` forms, each at its bound declaration.
  score: {"valid": true, "signatureAccuracy", "matchingSignatures",
          "totalDocumented", "comparedNames": [the names compared],
          "typeCoverage", "documentedTypes", "totalTypes",
          "missingTypes": [...], "mismatches": [{"name", "file", "line",
          "source_sig", "documented_sig", "issue", "difference" (null for
          none), "evidence_line" (with "annotation-contradicted" alone),
          "severity" (Critical, Low or Info)}], "gapRecords": [...],
          "warnings": [...]}
         or {"valid": false, "violations": [...]} when a result breaks the schema

Exit codes:
  0  the result was printed
  1  an input file cannot be read or is not the JSON it should be, the
     surface has no --surface-set set, the --skill-dir folder holds no
     readable SKILL.md, or the --source-root folder does not exist
  2  a subagent result breaks the schema (violations[] names each breach;
     nothing is written to --output or --gaps-output)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath

# Surface kinds that count toward total_types. A Rust struct is a class and a
# trait an interface; `type` is a type alias.
TYPE_KINDS = frozenset({"interface", "type", "enum", "class", "struct", "trait"})
MISMATCH_FIELDS = ("name", "line", "source_sig", "documented_sig", "issue")
# The optional `difference` a judge tags a mismatch with, defined in
# references/signature-comparison-rules.md (Difference tags): only the
# parameter names differ, only members the documented form leaves out that
# the source marks optional, or only a return annotation the body contradicts
# (the body returns the documented type at the mismatch's `evidence_line`).
DIFFERENCES = ("parameter-name", "omitted-optional", "annotation-contradicted")
CONTRADICTED = "annotation-contradicted"
# grade()'s default: an annotation-contradicted mismatch whose facts no one checked stays Critical.
UNCHECKED = "its facts were not checked"
# A body line that returns starts with the `return` keyword. The declaration
# line itself returns when its expression body follows its parameters: an
# arrow function assigned with `=` or `export default` (`=> expr`, not a
# `{` block), or a Python `def ...: return x`. A `type` alias's arrow is a type.
RETURN_START_RE = re.compile(r"return(?![\w$])")
ARROW_OPENER_RE = re.compile(r"(?:=|\bdefault)\s*(?:async\s*)?(?:<[^()]*>\s*)?\(")
ARROW_BODY_RE = re.compile(r"\s*(?::[^=]*)?=>\s*[^\s{]")
PYTHON_DEF_RE = re.compile(r"(?:async\s+)?def\s+\w+\s*\(")
PYTHON_BODY_RE = re.compile(r"\s*(?:->[^:]*)?:\s*return(?![\w$])")
TYPE_DECLARATION_RE = re.compile(r"(?:export\s+)?(?:declare\s+)?type\s")
# Where a signature's return type starts, with no parenthesized parameters.
RETURN_ARROW_RE = re.compile(r"->|=>|→")
# A name, or a dotted receiver and name, before a signature's parameter group (`run_pipeline(`, `coco.default_env(`):
# a mismatch's `documented_sig` may write it where the form writes only the parameters (_quotes).
LEADING_NAME_RE = re.compile(r"^[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*\s*(?=\()")
# The dotted receiver before a usage's called name (`coco.` in `coco.default_env()`): a mismatch's `documented_sig`
# may write the call without it (_quotes).
CALL_RECEIVER_RE = re.compile(r"^(?:[A-Za-z_$][\w$]*\s*\.\s*)+(?=[A-Za-z_$][\w$]*\s*\()")
# The prefixes a type is compared without, as signature-comparison-rules.md's Equivalent spellings reads a name
# with or without one: `typing.List[int]` is `List[int]`, `React.ReactNode` is `ReactNode`. They are dropped
# wherever they stand, in a type read as one text (a callable's arrow) too; any other module path is read only on
# a type's own name, against the bare name it ends in (_names_match).
TYPE_PREFIX_RE = re.compile(r"(?<![\w.$])(?:typing|collections\.abc|React)\.")
# The `typing` names Equivalent spellings reads as the builtins they alias.
TYPING_ALIASES = {"List": "list", "Dict": "dict", "Tuple": "tuple", "Set": "set", "FrozenSet": "frozenset",
                  "Type": "type"}
# A quoted forward reference (`"Node"`), read as the type it quotes.
FORWARD_REFERENCE_RE = re.compile(r"(['\"])([A-Za-z_][^'\"]*)\1")
# The name a type starts with, before its type arguments (`dict[str, Any]`, `Promise<T>`).
TYPE_NAME_RE = re.compile(r"[A-Za-z_$][\w.$]*")
# A type's name written through a module or namespace path (`environment.Environment`, `z.ZodType`), its final
# name the group: Equivalent spellings reads the name with or without the path (_final_name).
DOTTED_NAME_RE = re.compile(r"(?:[A-Za-z_$][\w$]*\.)+([A-Za-z_$][\w$]*)")
# A string written in single or double quotes, its text the second group (_value).
STRING_VALUE_RE = re.compile(r"(['\"])([^'\"]*)\1")
# A Rust lifetime's `'a`, followed by whitespace, `,`, `>`, `+`, `)` or the end (_lifetime says where it stands).
LIFETIME_RE = re.compile(r"'[A-Za-z_]\w*(?=[\s,>+)]|$)")
# Each closing bracket and the opening one it closes (_levels: a `>` closes only a `<`).
CLOSERS = {")": "(", "]": "[", "}": "{"}
OPENERS = {"(": ")", "[": "]", "{": "}", "<": ">"}
# A group a decorator or a Java annotation writes: the text before it ends with `@name`.
DECORATED_RE = re.compile(r"@[\w.$]+\s*$")
# What follows a prefix group: another `(` with no space between (C++ `operator()(int x)`), or a name and a `(`
# after whitespace (a Go receiver, `func (s *Server) Start(port int)`), the name no C or C++ qualifier that takes
# arguments after a parameter group (`f(int x) noexcept(true)`).
PREFIX_GROUP_RE = re.compile(r"\(|\s+(?!(?:noexcept|throw|__attribute__|requires|decltype)\b)[A-Za-z_$][\w$]*\s*\(")
# A receiver a method's parameter list may lead with: Python's `self` and `cls`, Rust's `self`, `&self`,
# `&mut self` and `mut self` (with a lifetime too, `&'a self`), and TS's `this: T` (_parameter_difference).
RECEIVER_RE = re.compile(r"self|cls|this|mut self|&(?:'\w+ )?(?:mut )?self")
# An ellipsis item, standing for parameters a form does not show (a TS/JS rest `...name` is none).
ELLIPSES = ("...", "…")
# The TS/JS source files, where a parameter with no type and a literal default has that literal's type.
TS_JS_EXTENSIONS = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"})
# A literal default's type (signature-comparison-rules.md, Annotations): a bigint, a number, a string or template
# literal, a boolean.
LITERAL_TYPES = (
    (re.compile(r"[-+]?(?:0[xob][\da-f_]+|\d[\d_]*)n", re.I), "bigint"),
    (re.compile(r"[-+]?(?:0[xob][\da-f_]+|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:e[-+]?\d+)?)", re.I), "number"),
    (re.compile(r"(['\"`]).*\1", re.S), "string"),
    (re.compile(r"true|false"), "boolean"),
)
# Source files of the languages with no keyword arguments, where a caller
# never writes a parameter's name: TS/JS, Go, Rust, Java, C and C++. Not
# Python, which has keyword arguments (the script cannot see which
# parameters a caller must pass by position), nor Kotlin, C#, Swift or
# Scala, which name arguments at the call, nor a Vue component, whose
# documented parameters are props callers set by name.
POSITIONAL_EXTENSIONS = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs",
                                   ".java", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"})
# The builtin type names that start lowercase, by the source files of their language: Python, TS/JS (and the
# script of a .vue, .svelte or .astro file), Go, Rust, the C family (Java, C, C++) and C#. A parenthesized,
# bracketed or braced list of lowercase names writes a return type when one of them is a type name of the file's
# language (`(str, int)`, Go's `(int, error)`, `[string, number]`), else names of values, which state none
# (signature-comparison-rules.md, Annotations; _states_return). A file of a language with no table, or none,
# checks the names of every table (ALL_LOWERCASE_TYPES).
LOWERCASE_TYPES = {extension: names for extensions, names in (
    ((".py", ".pyi"), frozenset({"str", "int", "float", "complex", "bool", "bytes", "bytearray", "memoryview", "list",
                                 "dict", "set", "frozenset", "tuple", "object", "type", "range", "slice"})),
    ((*TS_JS_EXTENSIONS, ".vue", ".svelte", ".astro"),
     frozenset({"string", "number", "boolean", "bigint", "symbol", "object", "any", "unknown", "never", "void",
                "undefined", "null"})),
    ((".go",), frozenset({"bool", "byte", "rune", "string", "error", "any", "comparable", "int", "int8", "int16",
                          "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64", "uintptr", "float32",
                          "float64", "complex64", "complex128"})),
    ((".rs",), frozenset({"bool", "char", "str", "i8", "i16", "i32", "i64", "i128", "isize", "u8", "u16", "u32",
                          "u64", "u128", "usize", "f32", "f64"})),
    ((".java", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"),
     frozenset({"int", "long", "short", "char", "float", "double", "void", "bool", "boolean", "byte", "string",
                "object"})),
    ((".cs",), frozenset({"bool", "byte", "sbyte", "char", "decimal", "double", "float", "int", "uint", "nint",
                          "nuint", "long", "ulong", "short", "ushort", "object", "string", "dynamic", "void"})),
) for extension in extensions}
ALL_LOWERCASE_TYPES = frozenset().union(*LOWERCASE_TYPES.values())
# A list of value names (_states_return): its brackets, and a bare name that starts lowercase.
VALUE_LIST_BRACKETS = {"(": ")", "[": "]", "{": "}"}
VALUE_NAME_RE = re.compile(r"[a-z][\w$]*", re.ASCII)
# The grades of a mismatch, most severe first: one declaration reported
# twice keeps the most severe.
GRADES = ("Critical", "Low", "Info")

_INVENTORY_MODULE = None


def _inventory():
    """validate-inventory.py beside this script: the fence rule lives there."""
    global _INVENTORY_MODULE
    if _INVENTORY_MODULE is None:
        sibling = Path(__file__).resolve().parent / "validate-inventory.py"
        spec = importlib.util.spec_from_file_location("skf_validate_inventory", sibling)
        if spec is None or spec.loader is None or not sibling.is_file():
            raise ImportError(f"validate-inventory.py not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _INVENTORY_MODULE = module
    return _INVENTORY_MODULE


class InputError(Exception):
    """An input file that cannot be read, or is not the JSON it should be."""


def round2(value: float) -> float:
    """Round to 2 decimals with JS-compatible half-up rounding (matches compute-score.py)."""
    return math.floor(value * 100 + 0.5) / 100


def _read_text(path: str, flag: str) -> str:
    try:
        return Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {flag} {path}: {exc}") from exc


def _read_json(path: str, flag: str):
    try:
        return json.loads(_read_text(path, flag))
    except json.JSONDecodeError as exc:
        raise InputError(f"{flag} {path} is not JSON: {exc.msg}") from exc


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def load_inventory(path: str) -> list[dict]:
    data = _read_json(path, "--inventory")
    if isinstance(data, dict) and isinstance(data.get("inventory"), dict):
        data = data["inventory"]  # validate-inventory.py's whole result
    if not isinstance(data, dict) or not isinstance(data.get("exports"), list):
        raise InputError(f"--inventory {path} holds no `exports` list")
    return [e for e in data["exports"] if isinstance(e, dict)]


def load_surface(path: str, surface_set: str) -> tuple[list[str], list[dict], list[str]]:
    """(the chosen name set, every surface export record, the `all` set)."""
    data = _read_json(path, "--surface")
    sets = data.get("sets") if isinstance(data, dict) else None

    def name_set(key: str) -> list[str]:
        names = sets.get(key) if isinstance(sets, dict) else None
        if not isinstance(names, list):
            raise InputError(f"--surface {path} has no name set `{key}`")
        return [n for n in names if isinstance(n, str) and n]

    exports = data.get("exports") if isinstance(data.get("exports"), list) else []
    return name_set(surface_set), [e for e in exports if isinstance(e, dict)], name_set("all")


def load_other_declarations(path: str) -> list[dict]:
    """The surface's `otherDeclarations` (#918): each declaration of a
    surface name, in a file none of its records names, that the extraction
    records and no entry point exports, which plan may bind a form to. Each
    one with a name and a file; [] when the surface has none (an older
    surface included) or writes null, which it does when no runner
    extraction looked for them (#1026)."""
    data = _read_json(path, "--surface")
    items = data.get("otherDeclarations") if isinstance(data, dict) else None
    return [d for d in (items if isinstance(items, list) else [])
            if isinstance(d, dict) and isinstance(d.get("name"), str) and d["name"] and _record_file(d)]


def load_plan(path: str) -> dict[str, list[str]]:
    """{name: the files plan offered its check at, the planned one first,
    then its candidates'} from plan's output."""
    data = _read_json(path, "--plan")
    groups = data.get("files") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        raise InputError(f"--plan {path} is not score-signatures.py plan output (no `files` list)")
    offered: dict[str, list[str]] = {}
    for group in groups:
        checks = group.get("checks") if isinstance(group, dict) else None
        for check in checks if isinstance(checks, list) else []:
            if not (isinstance(check, dict) and isinstance(check.get("name"), str)):
                continue
            files = [str(group.get("file") or "")]
            candidates = check.get("candidates")
            for candidate in candidates if isinstance(candidates, list) else []:
                file = candidate.get("file") if isinstance(candidate, dict) else None
                if isinstance(file, str) and file.strip() and file not in files:
                    files.append(file)
            offered[check["name"]] = files
    return offered


def load_plan_forms(path: str) -> dict[str, list[dict]]:
    """{name: the documented forms plan offered it, `documented` first, then
    its `alternatives`} from plan's output: its documentedSignatures and
    documentedAlternatives maps (the fallback scan's), then each check's."""
    data = _read_json(path, "--plan")
    data = data if isinstance(data, dict) else {}
    signatures, alternatives = data.get("documentedSignatures"), data.get("documentedAlternatives")
    alternatives = alternatives if isinstance(alternatives, dict) else {}
    pairs = [(n, d, alternatives.get(n)) for n, d in (signatures.items() if isinstance(signatures, dict) else [])]
    for group in data.get("files") if isinstance(data.get("files"), list) else []:
        checks = group.get("checks") if isinstance(group, dict) else None
        pairs += [(c.get("name"), c.get("documented"), c.get("alternatives"))
                  for c in (checks if isinstance(checks, list) else []) if isinstance(c, dict)]
    forms: dict[str, list[dict]] = {}
    for name, documented, others in pairs:
        if isinstance(name, str) and isinstance(documented, dict):
            forms[name] = [documented, *(f for f in (others if isinstance(others, list) else []) if isinstance(f, dict))]
    return forms


def load_plan_bound(path: str) -> dict[str, dict[int, dict]]:
    """{name: {form index: the declaration plan bound that form to, {"file",
    "line"}}} from each check's `bound` (#918); a name with none is left
    out, and so is an item with no form index or no file."""
    data = _read_json(path, "--plan")
    groups = data.get("files") if isinstance(data, dict) else None
    bound: dict[str, dict[int, dict]] = {}
    for group in groups if isinstance(groups, list) else []:
        checks = group.get("checks") if isinstance(group, dict) else None
        for check in checks if isinstance(checks, list) else []:
            items = check.get("bound") if isinstance(check, dict) and isinstance(check.get("name"), str) else None
            for item in items if isinstance(items, list) else []:
                form = item.get("form") if isinstance(item, dict) else None
                if isinstance(form, int) and not isinstance(form, bool) and form >= 0 and _record_file(item):
                    bound.setdefault(check["name"], {})[form] = {"file": _record_file(item), "line": item.get("line")}
    return bound


def check_result(item: object, where: str) -> list[str]:
    """The schema breaches of one per-file result object."""
    if not isinstance(item, dict):
        return [f"{where} is not a JSON object"]
    errors = []
    if not (isinstance(item.get("file"), str) and item["file"].strip()):
        errors.append(f"{where}: `file` must be a non-empty string")
    for key in ("exports_found", "types_found"):
        value = item.get(key)
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            errors.append(f"{where}: `{key}` must be a list of strings when present")
    mismatches = item.get("signature_mismatches")
    if not isinstance(mismatches, list):
        errors.append(f"{where}: `signature_mismatches` must be present and a list (may be empty)")
        return errors
    for i, entry in enumerate(mismatches):
        at = f"{where}.signature_mismatches[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{at} is not an object")
            continue
        missing = [f for f in MISMATCH_FIELDS if f not in entry]
        if missing:
            errors.append(f"{at} missing field(s): {', '.join(missing)}")
            continue
        line = entry["line"]
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            errors.append(f"{at}: `line` must be a line number (an integer from 1)")
        for field in ("name", "source_sig", "documented_sig", "issue"):
            if not (isinstance(entry[field], str) and entry[field].strip()):
                errors.append(f"{at}: `{field}` must be a non-empty string")
        if entry.get("difference") is not None and entry["difference"] not in DIFFERENCES:
            errors.append(f"{at}: `difference` must be one of {', '.join(DIFFERENCES)} when present, "
                          f"not {json.dumps(entry['difference'])}")
        # The body line that returns the documented type: the fact an annotation-contradicted mismatch rests on.
        evidence = entry.get("evidence_line")
        if entry.get("difference") == CONTRADICTED:
            if isinstance(evidence, bool) or not isinstance(evidence, int) or evidence < 1:
                errors.append(f"{at}: `evidence_line` must be a line number (an integer from 1) with `difference` "
                              f"{CONTRADICTED}, not {json.dumps(evidence)}")
        elif evidence is not None:
            errors.append(f"{at}: `evidence_line` is given only with `difference` {CONTRADICTED}, "
                          f"not {json.dumps(entry.get('difference'))}")
        # The candidate a mismatch was found at, when the plan handed the judge several.
        if entry.get("file") is not None and not (isinstance(entry["file"], str) and entry["file"].strip()):
            errors.append(f"{at}: `file` must be a non-empty string when present, not {json.dumps(entry['file'])}")
        # The documented form a mismatch is reported for, when the check offered `alternatives`.
        form = entry.get("form")
        if form is not None and (isinstance(form, bool) or not isinstance(form, int) or form < 0):
            errors.append(f"{at}: `form` must be an index (an integer from 0) when present, not {json.dumps(form)}")
    return errors


def parse_result_text(text: str, where: str) -> tuple[list[dict], list[str]]:
    """(the result objects, the schema breaches) of one subagent response."""
    inner = _inventory().strip_fences(text)
    try:
        data = json.loads(inner)
    except json.JSONDecodeError as exc:
        return [], [f"{where} is not valid JSON: {exc.msg}"]
    items = data if isinstance(data, list) else [data]
    errors = []
    for i, item in enumerate(items):
        errors += check_result(item, where if len(items) == 1 else f"{where}[{i}]")
    return ([] if errors else items), errors


def load_results(paths: list[str]) -> tuple[list[dict], list[str]]:
    """Every result object of the --results files, and every schema breach."""
    results, violations = [], []
    for path in paths:
        items, errors = parse_result_text(_read_text(path, "--results"), Path(path).name)
        results += items
        violations += errors
    return results, violations


# --------------------------------------------------------------------------
# Plan and score
# --------------------------------------------------------------------------


def _has_signature(entry: dict) -> bool:
    """`params`, `return_type` or `usage_signature` as a list or a non-blank
    string, or, for a kind the inventory contract gives `params`
    (validate-inventory.py's SIGNATURE_KINDS), an empty `params` string: the
    form of one that takes none."""
    if entry.get("kind") in _inventory().SIGNATURE_KINDS and isinstance(entry.get("params"), str):
        return True
    return any(
        isinstance(entry.get(f), list) or (isinstance(entry.get(f), str) and entry[f].strip())
        for f in _inventory().SIGNATURE_FIELDS
    )


def _partial(fields: dict) -> bool:
    return fields.get("signature_form") == "partial"


def _lists_params(fields: dict) -> bool:
    params = fields.get("params")
    return (isinstance(params, str) and bool(params.strip())) or (isinstance(params, list) and bool(params))


def _claims_none(fields: dict) -> bool:
    """A blank `params` (`""` or `[]`): the form claims the export takes none (#1025), where one with no `params`
    (absent or null) claims nothing about parameters."""
    return isinstance(fields.get("params"), (str, list)) and not _lists_params(fields)


def _gives_usage(fields: dict) -> bool:
    """A non-blank `usage_signature` string, or a list holding one."""
    usage = fields.get("usage_signature")
    return any(isinstance(u, str) and bool(u.strip()) for u in (usage if isinstance(usage, list) else [usage]))


def _lists_members(fields: dict) -> bool:
    """A non-blank `params` string or non-empty list, or a non-blank
    `usage_signature` string or a list holding one: an entry that says what
    the name takes (a component's usage form names its props even when its
    `params` is empty)."""
    return _lists_params(fields) or _gives_usage(fields)


def _gives_return(fields: dict) -> bool:
    """A `return_type` that states a return type (_states_return, in every
    language's reading: a list of value names such as `(nodes, edges)`, and
    a blank one, state none): an entry that says what the name gives back,
    even when it lists no member (#914)."""
    return _states_return(_field_text(fields.get("return_type")))


def _rank(fields: dict) -> tuple[bool, bool, bool]:
    """How one of several entries of a name ranks, lowest compared first."""
    return not _lists_members(fields), _partial(fields), not _lists_params(fields)


def _form(entry: dict) -> dict:
    """The documented signature fields of one inventory entry, with its `signature_form` when it has one."""
    fields = {f: entry[f] for f in _inventory().SIGNATURE_FIELDS if f in entry}
    if entry.get("signature_form") is not None:
        fields["signature_form"] = entry["signature_form"]
    return fields


def _field_text(value: object) -> str:
    """A signature field as one text (validate-inventory.py's field_text, which the floor check reads too): a
    list's items joined with `, `, whitespace runs as one space, "" for null."""
    return _inventory().field_text(value)


def _form_key(fields: dict) -> tuple:
    """What a form says, for telling two entries apart (validate-inventory.py's form_key, which the floor check
    reads too): a null, blank or empty key read as absent, and the `signature_form` label left out
    (documented_forms keeps the full one)."""
    return _inventory().form_key(fields)


def _forms_and_places(inventory: list[dict]) -> dict[str, list[tuple[dict, list[tuple[str, int]]]]]:
    """{name: [(each of documented_forms' forms, the places the entries
    that give it write it, from their `at`: (its path, its line))]}, in
    documented_forms' order. An entry with no good `at` adds no place."""
    entries: dict[str, list[tuple[dict, list[tuple[str, int]]]]] = {}
    for entry in inventory:
        name = entry.get("name")
        if entry.get("kind") == "method" or not (isinstance(name, str) and name) or not _has_signature(entry):
            continue
        forms, fields = entries.setdefault(name, []), _form(entry)
        place = _inventory().parse_at(entry.get("at"))
        places = [place] if place is not None else []
        same = next((i for i, (f, _) in enumerate(forms) if _form_key(f) == _form_key(fields)), None)
        if same is None:
            forms.append((fields, places))
        elif (_partial(forms[same][0]) and not _partial(fields)) or (
                _partial(forms[same][0]) == _partial(fields) and _claims_none(fields)
                and not _claims_none(forms[same][0])):
            # the stricter entry, in the inventory order it has, as the rank would have ordered it
            places = forms[same][1] + places
            del forms[same]
            forms.append((fields, places))
        else:
            forms[same][1].extend(places)
    out: dict[str, list[tuple[dict, list[tuple[str, int]]]]] = {}
    for name, forms in entries.items():
        # stable: of forms that rank alike, inventory order
        first, *others = sorted(forms, key=lambda form: _rank(form[0]))
        out[name] = [first, *(f for f in others if _lists_members(f[0]) or _gives_return(f[0]))]
    return out


def _shared_places(inventory: list[dict]) -> dict[str, set[tuple[str, int]]]:
    """{name: each place (parse_at's (path, line)) where the inventory's
    entries give the name two or more forms that differ (_form_key), such as a
    table row that documents one declaration's form and quotes another's as a
    contrast}. For a name declared more than once, the citations of such a
    place bind none of its forms (#918): they cannot say which form they are
    for (_bindings). Entries that say the same thing
    at one place are one form, so their place is not shared; a `method`, and
    an entry with no form, write no form of the name."""
    keys: dict[tuple[str, tuple[str, int]], set[tuple]] = {}
    for entry in inventory:
        name, place = entry.get("name"), _inventory().parse_at(entry.get("at"))
        if (entry.get("kind") == "method" or not (isinstance(name, str) and name) or place is None
                or not _has_signature(entry)):
            continue
        keys.setdefault((name, place), set()).add(_form_key(_form(entry)))
    shared: dict[str, set[tuple[str, int]]] = {}
    for (name, place), forms in keys.items():
        if len(forms) > 1:
            shared.setdefault(name, set()).add(place)
    return shared


def _places_by_name(inventory: list[dict]) -> dict[str, set[tuple[str, int]]]:
    """{name: every place the inventory gives it, (its path, its line) from
    an entry's good `at`}, a form plan drops (one that lists no member and
    states no return type, after another) and an entry with no form
    included; a `method` is no place of its name."""
    spots: dict[str, set[tuple[str, int]]] = {}
    for entry in inventory:
        name, place = entry.get("name"), _inventory().parse_at(entry.get("at"))
        if entry.get("kind") != "method" and isinstance(name, str) and name and place is not None:
            spots.setdefault(name, set()).add(place)
    return spots


def documented_forms(inventory: list[dict]) -> dict[str, list[dict]]:
    """{name: [its documented signature, *its alternatives]} for each
    documented export with a signature: its distinct forms (_form), ranked.
    Of several entries of one name, one that lists parameters or gives a
    usage form (_lists_members) is compared before one that does neither
    (empty or no `params` and no usage form: it never hides one that says
    what the name takes), then a full one (no `signature_form`, or `full`)
    before a partial one (a form the skill also gives in full is held to
    it), then, of two full or two partial forms, one that lists parameters
    is compared before one that gives only a usage form, else the first.
    The first is the documented signature; the others that list members or
    state a return type (_gives_return) follow it, in that order, as the
    alternatives the judge compares too (a skill that documents a name
    briefly in one place and in full in another, or a call example beside a
    form that states only what it returns, #914): one that lists no member
    ranks after every one that does, so it never changes the documented
    signature. A form that lists no member and states no return type is
    never an alternative. Two entries that say the same thing (_form_key)
    are one form; of two that differ only by the partial label, the full one
    (the stricter) stands, and of two that differ only by a blank `params`
    against none, the blank one, which claims the export takes none (#1025),
    so the grade never rests on which entry comes first."""
    return {name: [fields for fields, _ in forms] for name, forms in _forms_and_places(inventory).items()}


def documented_signatures(inventory: list[dict]) -> dict[str, dict]:
    """{name: its documented signature fields}: the first of its
    documented_forms, the one a check holds as `documented`."""
    return {name: forms[0] for name, forms in documented_forms(inventory).items()}


def documented_names(inventory: list[dict]) -> set[str]:
    return {e["name"] for e in inventory
            if isinstance(e.get("name"), str) and e["name"] and e.get("kind") != "method"}


def _record_file(record: dict) -> str:
    """A surface record's file, "" for none or a blank one."""
    file = str(record.get("file") or "")
    return file if file.strip() else ""


def _records_by_name(exports: list[dict]) -> dict[str, list[dict]]:
    """{name: its surface records}, by file then line: a record with no file
    last and, in one file, a record with a line before one with none, so a
    by-eye record stands in neither for the file an extraction names nor for
    the line it records there (#921; a file the two write differently, such
    as `./src/a.py` and `src/a.py`, is _lined_records's to settle)."""
    by_name: dict[str, list[dict]] = {}
    for record in sorted(exports, key=lambda r: (not _record_file(r), _record_file(r), not _is_line(r.get("line")),
                                                 r.get("line") if _is_line(r.get("line")) else 0)):
        name = record.get("name")
        if isinstance(name, str) and name:
            by_name.setdefault(name, []).append(record)
    return by_name


def _lined_records(records: list[dict]) -> list[dict]:
    """`records` (a name's surface records, never its `otherDeclarations`)
    less each one with a file and no line whose file, as _path reads both,
    holds another of them with a line (#921): after a `readByEye` rerun of
    `surface`, the extraction's record and a by-eye one with no line share
    a file, and the extraction's line wins there. A record with no file is
    kept (it sorts last), and so is a line-less record of a file none of
    `records` gives a line, which still stands in for that file."""
    lined = {_path(_record_file(r)) for r in records if _record_file(r) and _is_line(r.get("line"))}
    return [r for r in records
            if not _record_file(r) or _is_line(r.get("line")) or _path(_record_file(r)) not in lined]


def signature_universe(names: list[str], exports: list[dict]) -> set[str]:
    """The names whose documented signature is compared: the `all` set
    (`names`) plus every name on the surface's export records. A nested
    Python top's names leave `all` but keep their records, so a documented
    one still has its signature checked."""
    return set(names) | set(_records_by_name(exports))


def _path(file: str) -> str:
    """A path as a citation, a candidate and a surface record compare (validate-inventory.py's _cited_path)."""
    return _inventory()._cited_path(file)


def _candidate(record: dict) -> dict:
    """A surface record or an other declaration as a check names it: its file, line and signature line."""
    return {"file": _record_file(record), "line": record.get("line"), "signatureLine": record.get("signatureLine")}


def _check_at(name: str, records: list[dict], skill_dir: str | None,
              texts: list[list[str]] | None) -> tuple[dict, list[dict] | None]:
    """(the surface record the check of `name` is planned at, the candidates
    the judge reads, or None), of `records` less a line-less one of a file
    another of them gives a line (_lined_records, before the first record is
    picked: a `./` spelling of the file sorts first). One file among them:
    the first record. Several: the record whose file the skill cites on a
    line that names `name` when exactly one of them is cited (the first
    such record), else the first record, with every record that names a
    file as a candidate. `texts` is the skill's Markdown, read once
    (skill_markdown_lines)."""
    records = _lined_records(records)
    first = records[0] if records else {}
    filed = [r for r in records if _record_file(r)]
    if len(filed) < 2 or len({_path(_record_file(r)) for r in filed}) < 2:
        return first, None
    if skill_dir is not None:
        cited = {_path(_record_file(r)) for r in filed} & _inventory()._skill_cited_files(Path(skill_dir), name, texts)
        if len(cited) == 1:
            return next(r for r in filed if _path(_record_file(r)) in cited), None
    return first, [_candidate(r) for r in filed]


def _span_end(located: list[dict], file: str, line: object) -> int | None:
    """The last line of the declaration at `file` and `line`, for a citation
    of its body: the line before the next declaration `located` (the
    surface's records and its `otherDeclarations`, of every name) records in
    that file, or sys.maxsize when none follows it (it runs to the end of the
    file). The extraction records no declaration's last line, so the next
    declaration it records bounds it, as it bounds an annotation-contradicted
    `evidence_line` in score. None for a declaration with no line."""
    if not _is_line(line):
        return None
    following = _next_declaration(located, file, line)
    return sys.maxsize if following is None else max(line, following - 1)


def _bindings(name: str, records: list[dict], others: list[dict], places: list[list[tuple[str, int]]],
              every: set[tuple[str, int]], texts: dict[str, list[str]], shared: set[tuple[str, int]],
              located: list[dict]) -> list[dict]:
    """The forms of `name` bound to a declaration (#918): {"form": its index
    (0 `documented`, n the nth alternative), "file", "line",
    "signatureLine"} for each form whose own citations name exactly one of
    the name's declarations, its surface `records` with a file (less a
    line-less one of a file another of them gives a line, _lined_records)
    and its `others` (the surface's `otherDeclarations`), each once per file
    and line. A form's own citations are those of the places its entries write
    it (`places`, from their `at`), in the skill's Markdown `texts` by path,
    as validate-inventory.py's form_citations reads them, with the name's
    other places in that file (of `every` place the inventory gives it,
    _places_by_name) as those a fenced block's own citations must not be
    shared with; a place in `shared` (_shared_places: one that writes two
    forms of the name that differ) gives none when the name is declared more
    than once (in two files, or at two lines of one), so a form written only
    there is compared as one with no own citation. A name declared once
    keeps them: they can bind a form to no other declaration, and give the
    judge the line of the one there is. One names a declaration as
    cites_declaration says: its file, with no line, or at a line or in a
    range that holds a line of its span, from its line to the line before
    the next declaration `located` records in that file (_span_end). A form
    whose citations name none, or two, is bound to nothing."""
    inventory = _inventory()
    declarations, seen = [], set()
    for declaration in [r for r in _lined_records(records) if _record_file(r)] + others:
        key = (_path(_record_file(declaration)), declaration.get("line"))
        if key not in seen:
            seen.add(key)
            declarations.append(declaration)
    ends = [_span_end(located, _record_file(d), d.get("line")) for d in declarations]
    # declared once (one file, at most one line in it, a per-file record with no line beside it, one kept only when
    # no surface record there has a line): no other declaration a shared place's citation could bind a form to, so
    # its shared places still bind
    homonyms = (len({_path(_record_file(d)) for d in declarations}) > 1
                or sum(_is_line(d.get("line")) for d in declarations) > 1)
    bound = []
    for index, at in enumerate(places):
        citations = set()
        for path, line in at:
            if homonyms and (path, line) in shared:
                continue
            others_there = {other for where, other in every if where == path and other != line}
            citations |= inventory.form_citations(texts.get(path) or [], line, name, others_there)
        named = [d for d, end in zip(declarations, ends)
                 if inventory.cites_declaration(citations, _record_file(d), d.get("line"), end)]
        if len(named) == 1:
            bound.append({"form": index, **_candidate(named[0])})
    return bound


def plan(inventory: list[dict], names: list[str] | None, exports: list[dict], skill_dir: str | None = None,
         others: list[dict] | None = None) -> dict:
    """The comparisons over the signature universe of `names` (the `all`
    set) and `exports`; none without a surface (`names` None). `skill_dir`,
    the skill package, settles which declaration a name the surface records
    in several files is compared with (_check_at), and binds each form whose
    own citations name one declaration of the name, a surface record or one
    of `others` (the surface's `otherDeclarations`), to it (_bindings), a
    place that writes two of its forms that differ giving none of them a
    citation (_shared_places) when the name is declared more than once, and
    the next declaration `exports` or `others` records in a file ending the
    span of the one before it (_span_end). A
    name documented in several forms carries the others that list members
    or state a return type as `alternatives` (documented_forms)."""
    forms = _forms_and_places(inventory)
    spots = _places_by_name(inventory)
    shared = _shared_places(inventory)
    files: dict[str, list[dict]] = {}
    compared = 0
    if names is not None:
        by_name = _records_by_name(exports)
        others_by_name = _records_by_name(others or [])
        texts = _inventory().skill_markdown_by_path(Path(skill_dir)) if skill_dir is not None else None
        lines = list(texts.values()) if texts is not None else None
        for name in sorted(signature_universe(names, exports) & set(forms)):
            record, candidates = _check_at(name, by_name.get(name) or [], skill_dir, lines)
            compared += 1
            check = {
                "name": name,
                "line": record.get("line"),
                "signatureLine": record.get("signatureLine"),
                "documented": forms[name][0][0],
            }
            if len(forms[name]) > 1:
                check["alternatives"] = [fields for fields, _ in forms[name][1:]]
            if candidates:
                check["candidates"] = candidates
            bound = (_bindings(name, by_name.get(name) or [], others_by_name.get(name) or [],
                               [at for _, at in forms[name]], spots.get(name, set()), texts,
                               shared.get(name, set()), exports + (others or []))
                     if texts is not None else [])
            if bound:
                check["bound"] = bound
            files.setdefault(_record_file(record), []).append(check)
    named_forms = {name: [fields for fields, _ in fs] for name, fs in forms.items()}
    return {
        "compared": compared,
        "files": [{"file": f, "checks": checks} for f, checks in sorted(files.items())],
        "documentedSignatures": {name: fs[0] for name, fs in named_forms.items()},
        # The fallback scan's alternatives: a name's form n is its nth entry here, as in a check's `alternatives`.
        "documentedAlternatives": {name: fs[1:] for name, fs in named_forms.items() if len(fs) > 1},
    }


def _extension(file: str) -> str:
    """The lower-case extension of a source path, `/` or `\\` separated."""
    return PurePosixPath(file.replace("\\", "/")).suffix.lower()


def _offered_files(offered: dict[str, list[str]] | None, by_name: dict[str, list[dict]], name: str) -> list[str]:
    """The files a mismatch of `name` may be recorded at, the planned one
    first: the plan's check of `name` (its file, then its candidates') when
    `offered` (read from --plan) holds it, else every file the surface
    records for `name` ("" for a record with none); [] for a name the
    surface lacks (a fallback scan's exports_found name)."""
    if offered is not None and name in offered:
        return offered[name]
    files: list[str] = []
    for record in by_name.get(name) or []:
        if _record_file(record) not in files:
            files.append(_record_file(record))
    return files


def _is_offered_file(files: list[str], file: str) -> bool:
    """Whether `file` is one of `files` (_offered_files), however either writes its path."""
    return _path(file) in {_path(f) for f in files}


def _is_line(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _lines_in(exports: list[dict], file: str) -> list[int]:
    """The lines of the surface records in `file`, however either writes its path."""
    return [r["line"] for r in exports
            if _record_file(r) and _path(_record_file(r)) == _path(file) and _is_line(r.get("line"))]


def _declaration_line(by_name: dict[str, list[dict]], name: str, file: str, line: int) -> int:
    """The line `name` is declared at in `file`: of its surface records there
    (the plan's check, or the candidate it offered), the closest one at or
    before the mismatch's `line` (a name declared twice in one file), else
    the first; with none there, the mismatch's own `line`."""
    lines = _lines_in(by_name.get(name) or [], file)
    before = [at for at in lines if at <= line]
    return max(before) if before else min(lines, default=line)


def _next_declaration(exports: list[dict], file: str, line: int) -> int | None:
    """The line of the first surface record in `file` after `line` (a bound declaration included), None when there
    is none."""
    return min((at for at in _lines_in(exports, file) if at > line), default=None)


def _source_lines(source_root: str, file: str) -> list[str] | None:
    """The lines of `file` under `source_root`, None when it is no readable
    file there (a path that leaves the root included)."""
    root = Path(source_root).resolve()
    path = (root / file).resolve()
    try:
        path.relative_to(root)
        return path.read_bytes().decode("utf-8-sig", errors="replace").splitlines()
    except (ValueError, OSError):
        return None


def _after_parens(text: str, start: int) -> int:
    """The index past the `)` that closes the `(` at `start`, -1 when none does."""
    depth = 0
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i + 1
    return -1


def _string_end(text: str, start: int) -> int:
    """The index past the string literal whose quote is at `start`: up to the same quote not escaped, the end of
    `text` when none closes it."""
    quote, i = text[start], start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text[i] == quote:
            return i + 1
        else:
            i += 1
    return len(text)


def _lifetime(text: str, i: int, in_angle: bool, extension: str) -> bool:
    """Whether the `'` at `i` starts a Rust lifetime: only in a `.rs` file, `'ident` followed by whitespace, `,`,
    `>`, `+`, `)` or the end, coming after a `&` or a `+` (whitespace aside) or inside a `<...>` (`in_angle`), as
    in `&'a str`, `impl Tr + 'a` and `<'a>`. Any other `'` opens a string, so a TS `Omit<P, 'a,b'>` holds one."""
    return (extension == ".rs" and bool(LIFETIME_RE.match(text, i))
            and (in_angle or text[:i].rstrip()[-1:] in ("&", "+")))


def _opens(text: str, i: int, extension: str) -> bool:
    """Whether the `<` at `i` opens a pair: it follows a letter, a digit, `_`, `$`, `.`, `]` or `>` with no
    whitespace between (`Map<`, `f<T>`, `obj.get<T>`), and a `>` that is not part of `->` or `=>` closes it
    before the bracket pair around it closes or the text ends. Any other `<` is an operator (`x < y`, `1 << 20`,
    `x<3)`)."""
    if i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_$.]>"):
        return False
    depth, j = 0, i + 1
    while j < len(text):
        ch = text[j]
        if ch in "\"`" or (ch == "'" and not _lifetime(text, j, depth == 0, extension)):
            j = _string_end(text, j)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return False
            depth -= 1
        elif ch == ">" and depth == 0 and text[j - 1] not in "-=":
            return True
        j += 1
    return False


def _levels(text: str, extension: str = "") -> list[int | None]:
    """For each character of `text`, in a file of `extension`, the number of bracket pairs open around it, None
    inside a string literal (its quotes included). `(`, `[` and `{` open a pair, and a `<` opens one only when it
    follows a name, a `.`, a `]` or a `>` with no whitespace between and a `>` that is not part of `->` or `=>`
    closes it before the bracket pair around it closes or the text ends (_opens); any other `<` is an operator
    and nests nothing, so `(path, size=1 << 20, mode)` holds three parameters,
    `(a: boolean = x < y, b: Map<string, number>)` two, and `Map<string, number>` keeps its comma. An opening
    bracket and the one that closes it stand at the level outside them. A closing bracket closes the pair it
    matches and any `<` left open inside it, and a `>` closes only a `<`, never as part of `->` or `=>`. A `"`, a
    backquote or a `'` opens a string (_string_end), except the `'` of a Rust lifetime in a `.rs` file
    (_lifetime)."""
    levels: list[int | None] = []
    stack: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "\"`" or (ch == "'" and not _lifetime(text, i, bool(stack) and stack[-1] == "<", extension)):
            end = _string_end(text, i)
            levels.extend([None] * (end - i))
            i = end
            continue
        if ch in "([{" or (ch == "<" and _opens(text, i, extension)):
            levels.append(len(stack))
            stack.append(ch)
        elif ch in CLOSERS and CLOSERS[ch] in stack:
            while stack.pop() != CLOSERS[ch]:
                pass
            levels.append(len(stack))
        elif ch == ">" and stack and stack[-1] == "<" and text[i - 1:i] not in ("-", "="):
            stack.pop()
            levels.append(len(stack))
        else:
            levels.append(len(stack))
        i += 1
    return levels


def _split(text: str, separator: str, extension: str = "") -> list[str]:
    """`text` cut at each `separator` outside every bracket pair and string (_levels)."""
    levels = _levels(text, extension)
    cuts = [-1, *(i for i, ch in enumerate(text) if ch == separator and levels[i] == 0), len(text)]
    return [text[a + 1:b] for a, b in zip(cuts, cuts[1:])]


def _encloses(text: str, start: int, extension: str = "") -> bool:
    """Whether the bracket at `start` of `text` opens a pair that the last character of `text` closes."""
    levels = _levels(text, extension)
    return (OPENERS.get(text[start]) == text[-1] and levels[start] == 0 == levels[-1] and len(text) - start > 1
            and all(level is None or level > 0 for level in levels[start + 1:-1]))


def _group(text: str, extension: str = "") -> tuple[int, int] | None:
    """The indices of the `(` and the `)` of the parameter group of `text`: the first pair of parentheses outside
    every bracket pair and string (_levels), before any return arrow there, that is no prefix group. A prefix group
    is one a decorator or a Java annotation writes (the text before it ends with `@name`:
    `@lru_cache(maxsize=None) def f(x)`), one directly followed by another `(` (C++ `operator()(int x)`), or one
    followed, after whitespace, by a name and a `(` (a Go receiver, `func (s *Server) Start(port int)`), unless
    that name is a C or C++ qualifier (`noexcept`, `throw`, `__attribute__`, `requires`, `decltype`: `f(int x)
    noexcept(true)` keeps its group). A `(` after a space is no prefix either (Go's result list,
    `Start(port int) (int, error)`). So a keyword, a name or type parameters before the group are never part of
    it. None when there is no such group: no `(` comes before the return arrow (`make -> X`), or a group does not
    close."""
    levels = _levels(text, extension)
    i = 0
    while i < len(text):
        if levels[i] == 0 and RETURN_ARROW_RE.match(text, i):
            return None
        if text[i] == "(" and levels[i] == 0:
            end = next((j for j in range(i + 1, len(text)) if text[j] == ")" and levels[j] == 0), None)
            if end is None:
                return None
            if not (DECORATED_RE.search(text, 0, i) or PREFIX_GROUP_RE.match(text, end + 1)):
                return i, end
            i = end
        i += 1
    return None


def _signature_parts(sig: str, extension: str = "") -> tuple[str, str]:
    """(the text before the return, its whitespace runs read as one space; the return type it writes, "" for
    none) of a signature, in a file of `extension`. The return follows the parameter group (_group, the one
    _parameters reads), after a `->`, `=>`, `→` or `:`, or, with no group, the first such arrow. A `;` is read as
    any other character."""
    text = sig.strip()
    group = _group(text, extension)
    if group is None:
        arrow = RETURN_ARROW_RE.search(text)
        head, tail = (text[:arrow.start()], text[arrow.end():]) if arrow else (text, "")
    else:
        head, tail = text[:group[1] + 1], re.sub(r"^\s*(?:->|=>|→|:)", "", text[group[1] + 1:])
    return " ".join(head.split()), tail.strip().rstrip("{:").strip()


def _compact(text: str) -> str:
    """`text` with its whitespace runs read as one space, and none beside a character that is no letter, digit
    or `_`, so `{ title }` is `{title}` and `dict[str, Any]` is `dict[str,Any]`."""
    return re.sub(r"\s*([^\w\s])\s*", r"\1", " ".join(text.split()))


def _type_parameters(sig: str, extension: str = "") -> str:
    """The type parameters a signature writes between its name and its parameter group (`<T extends X>`, or
    Python's `[T: int]`), compacted and without a trailing comma; "" for none, or no group."""
    text = sig.strip()
    group = _group(text, extension)
    if group is None:
        return ""
    levels = _levels(text, extension)
    k = len(text[:group[0]].rstrip()) - 1
    if k < 1 or text[k] not in ">]" or levels[k] is None:
        return ""
    j = next((j for j in range(k - 1, -1, -1) if levels[j] is not None and levels[j] <= levels[k]), None)
    if j is None or OPENERS.get(text[j]) != text[k] or levels[j] != levels[k]:
        return ""
    return _compact(text[j + 1:k]).rstrip(",")


def _parameter(text: str, extension: str = "") -> dict:
    """One parameter as _parameters reads it, but for its "by_name" and "receiver": its name is the text before
    the `:` of its type and the `=` of its default (each outside every bracket pair and string; the `=` of `==`,
    `=>`, `<=`, `>=` or `!=` is no default), the whole text when it writes neither, so a parameter in another
    language's order (Go's `id string`) or a destructured one (`{ a, b }`) is read as one name."""
    levels = _levels(text, extension)
    at = next((i for i, ch in enumerate(text) if ch == "=" and levels[i] == 0
               and text[i + 1:i + 2] not in ("=", ">") and text[i - 1:i] not in ("=", "!", "<", ">")), None)
    head = text if at is None else text[:at]
    colon = next((i for i, ch in enumerate(head) if ch == ":" and levels[i] == 0), None)
    name = _compact(head if colon is None else head[:colon])
    optional = at is not None or name.endswith("?")
    name = name.rstrip("?")
    key = "**" if name.startswith("**") else "*" if name.startswith("*") else name
    return {"key": key, "name": name, "type": "" if colon is None else _compact(head[colon + 1:]),
            "default": None if at is None else text[at + 1:].strip(), "optional": optional,
            "variadic": key in ("*", "**") or (name.startswith("...") and name not in ELLIPSES),
            "ellipsis": name in ELLIPSES and colon is None and at is None}


def _parameters(sig: str, extension: str = "") -> list[dict] | None:
    """The parameters the group of `sig` writes (_group), in a file of `extension`, None when it has no group:
    the group split at its commas outside every bracket pair and string (_levels), so a comma inside a nested
    type, a callback's parameters or a default's string splits nothing, without a bare `*` or `/` marker. Each is
    {"key": its name (_parameter), `*` for any `*args` and `**` for any `**kwargs`, whose names are never
    compared; "name": its name as written; "type": the type it writes, compacted, "" for none; "default": the text
    of its default, None for none; "optional": whether a default or a `?` on its name marks it optional;
    "variadic": whether it is a `*args`, a `**kwargs` or a TS/JS rest `...name`; "ellipsis": whether it is an
    ellipsis item (`...`, `…`) standing for members it does not show; "by_name": whether it comes after a `*`
    marker, a bare `*` or a `*args`; "receiver": whether it is the group's first item and a receiver
    (RECEIVER_RE: `self`, `cls`, `&self`, `&mut self`, `mut self`, `this: T`), which _parameter_difference
    drops}. A `sig` that holds a `;` outside every bracket pair and string (shared text before a name's own
    members, an overload set or a usage list joined by `;`) has none either, so it is compared as text, read as
    written: its first group may be a call inside the shared text."""
    text = sig.strip()
    group = _group(text, extension)
    if group is None or len(_split(text, ";", extension)) > 1:
        return None
    params: list[dict] = []
    by_name = False
    for index, item in enumerate(_split(text[group[0] + 1:group[1]], ",", extension)):
        item = item.strip()
        if item in ("", "/"):
            continue
        if item == "*":
            by_name = True
            continue
        param = _parameter(item, extension)
        param.update(by_name=by_name, receiver=index == 0 and bool(RECEIVER_RE.fullmatch(param["name"])))
        by_name = by_name or param["key"] == "*"
        params.append(param)
    return params


def _type_key(text: str, extension: str = "", in_string: bool = False) -> frozenset:
    """A written type, in a file of `extension`, as signature-comparison-rules.md's Equivalent spellings commonly
    reads it: the set of its union's members (cut at each `|` outside every bracket pair and string, and at each
    `/` there, which a table's Type cell writes between types for a `|`: `str / None` is `str | None`; a `/` alone
    in a parameter list is the positional-only marker _parameters skips, and one in a quoted forward reference
    (`in_string`, at any depth) is part of its string), each (its
    base name, the keys of its type arguments, None when it writes none), so `Optional[X]`, `Union[X, None]` and
    `X | None` are one key, and so are `Union[A, B]`, `A | B` and `B | A`. A `typing.`, `collections.abc.` or
    `React.` prefix is dropped, a type's own name written through a module or namespace path matches the bare name
    it ends in (_names_match: `environment.Environment` and `Environment`, while two paths stay two names),
    `typing`'s `List`, `Dict`, `Tuple`, `Set`, `FrozenSet` and `Type` are the
    builtins they alias, a quoted forward reference is the type it quotes outside a TS/JS file (where a quoted
    type is a string literal type), `Array<T>` is `T[]`, `ReadonlyArray<T>` is `readonly T[]`, and a
    parenthesized type is the type inside. A type it reads no other way (a callable's arrow, a literal) is one
    member, its compacted text, and a Python `Literal[...]`'s arguments are values, each its text (_value). Type
    variables renamed consistently, a type alias against the type it names and a union of callables against one
    callable returning the union are different keys: the script cannot see them as one. It cannot see the imports
    either, so a path and the bare name it ends in match even when they name two declarations."""
    members: set = set()
    for part in _split(TYPE_PREFIX_RE.sub("", _compact(text)), "|", extension):
        for member in [part] if in_string else _split(part, "/", extension):
            members |= _member_keys(member.strip(), extension, in_string)
    return frozenset(members)


def _member_keys(text: str, extension: str = "", in_string: bool = False) -> frozenset:
    """The union members (_type_key) one part of a type with no `|` outside brackets stands for."""
    quoted = FORWARD_REFERENCE_RE.fullmatch(text) if extension not in TS_JS_EXTENSIONS else None
    if quoted:
        return _type_key(quoted.group(2), extension, True)
    if text.startswith("(") and _encloses(text, 0, extension):
        return _type_key(text[1:-1], extension, in_string)
    if text.endswith("[]") and len(text) > 2:
        inner = text[:-2].strip()
        if inner.startswith("readonly "):
            return frozenset({("ReadonlyArray", (_type_key(inner[len("readonly "):], extension, in_string),))})
        return frozenset({("Array", (_type_key(inner, extension, in_string),))})
    name = TYPE_NAME_RE.match(text)
    if name and name.end() == len(text):
        return frozenset({(_written_name(text), None)})
    if name and text[name.end()] in "[<" and _encloses(text, name.end(), extension):
        base = _written_name(name.group())
        # a `Literal[...]`'s arguments are values, never types: no path or forward reference is read in them
        values = _final_name(base) == "Literal" and extension not in TS_JS_EXTENSIONS
        args = tuple(frozenset({(_value(arg.strip()), None)}) if values else _type_key(arg, extension, in_string)
                     for arg in _split(text[name.end() + 1:-1], ",", extension) if arg.strip())
        if _final_name(base) == "Optional" and len(args) == 1:
            return args[0] | {("None", None)}
        if _final_name(base) == "Union" and args:
            return frozenset().union(*args)
        return frozenset({(base, args)})
    return frozenset({(text, None)})


def _written_name(name: str) -> str:
    """A type's name (TYPE_NAME_RE) as its key holds it: as written when a module or namespace path leads it, for
    _names_match to read, else with a `typing` alias read as the builtin it aliases (`List` is `list`)."""
    return name if "." in name else TYPING_ALIASES.get(name, name)


def _final_name(name: str) -> str:
    """A type's name (TYPE_NAME_RE) as Equivalent spellings reads it: by its final name when it is written
    through a module or namespace path (DOTTED_NAME_RE), so `environment.Environment` is `Environment` and
    `np.ndarray` is `ndarray`, then a `typing` alias read as the builtin it aliases (`t.List` is `list`)."""
    dotted = DOTTED_NAME_RE.fullmatch(name)
    final = dotted.group(1) if dotted else name
    return TYPING_ALIASES.get(final, final)


def _names_match(name: str, other: str) -> bool:
    """Whether two base names (_member_keys) are one type's, as Equivalent spellings reads a name with or without
    the module or namespace path it is written through: the same name, or a path on one side only and the bare
    name it ends in (_final_name: `environment.Environment` and `Environment`, `t.List` and `list`). Two different
    paths (`a.Foo` against `b.Foo`) are two names, on the strict side, since the script cannot see the imports
    that would say both name one declaration."""
    if name == other:
        return True
    return ("." in name) != ("." in other) and _final_name(name) == _final_name(other)


def _value(text: str) -> str:
    """A `Literal[...]` argument as a value: its text, a string written in either quote read as one (`'a'` and
    `"a"`), so a `.`, `/` or `|` inside a string is part of the value it writes."""
    string = STRING_VALUE_RE.fullmatch(text)
    return f"'{string.group(2)}'" if string else text


def _members_match(documented: tuple, source: tuple) -> bool:
    """Whether two union members (_type_key) are one type: one base name (_names_match) and, unless either side
    leaves its type arguments out (`dict` against `dict[str, Any]`, which compares the base alone), as many
    arguments, each pair one type (_types_match)."""
    (base, args), (other_base, other_args) = documented, source
    if not _names_match(base, other_base):
        return False
    if args is None or other_args is None:
        return True
    return len(args) == len(other_args) and all(_types_match(a, b) for a, b in zip(args, other_args))


def _types_match(documented: frozenset, source: frozenset, subset: bool = False) -> bool:
    """Whether every documented member is a source member (_members_match) and, unless `subset`, every source
    member a documented one. A parameter's own type is compared with `subset`: a documented type that names some
    of the members of the source's union is no difference, one that names a member the source lacks is."""
    if not all(any(_members_match(d, s) for s in source) for d in documented):
        return False
    return subset or all(any(_members_match(d, s) for d in documented) for s in source)


def _literal_type(default: str | None) -> str:
    """The type of a TS/JS literal default (LITERAL_TYPES: `number`, `string`, `boolean` or `bigint`), "" for any
    other default."""
    if default is None:
        return ""
    return next((name for pattern, name in LITERAL_TYPES if pattern.fullmatch(default)), "")


def _count(n: int) -> str:
    return f"{n} parameter" if n == 1 else f"{n} parameters"


def _pair_difference(documented: dict, source: dict, stated: bool, extension: str) -> str | None:
    """Why a documented parameter differs from the source parameter it pairs with, None when it does not: its
    type, where both write one (_types_match with `subset`), or, when the documented list states optionality for
    any member (`stated`), its optionality, a rest or variadic member's aside."""
    if documented["type"] and source["type"] and not _types_match(
            _type_key(documented["type"], extension), _type_key(source["type"], extension), subset=True):
        return (f"`{documented['name']}` is typed `{documented['type']}` in the documented list, "
                f"`{source['type']}` in the source")
    if stated and not documented["variadic"] and documented["optional"] != source["optional"]:
        def word(optional: bool) -> str:
            return "optional" if optional else "required"
        return (f"`{documented['name']}` is {word(documented['optional'])} in the documented list, "
                f"{word(source['optional'])} in the source")
    return None


def _complete_difference(documented: list[dict], source: list[dict], stated: bool, extension: str) -> str | None:
    """Why a documented list that claims to be complete (it writes a type, a default or a `?` for some member)
    differs from the source's, None when it does not: it must write as many parameters, paired in order up to the
    first that either list writes after a `*` marker and by name from there, each pair with one name and no
    _pair_difference."""
    if len(documented) != len(source):
        return f"the documented list writes {_count(len(documented))}, the source {_count(len(source))}"
    first = min(next((i for i, p in enumerate(params) if p["by_name"]), len(params)) for params in (documented, source))
    for n, (d, s) in enumerate(zip(documented[:first], source[:first]), 1):
        if d["key"] != s["key"]:
            return f"parameter {n} is `{d['name']}` in the documented list, `{s['name']}` in the source"
        reason = _pair_difference(d, s, stated, extension)
        if reason:
            return f"parameter {n}: {reason}"
    named = [{p["key"]: p for p in params[first:]} for params in (documented, source)]
    if any(len(keys) != len(documented) - first for keys in named):
        return "a parameter is written twice"
    for key, d in named[0].items():
        if key not in named[1]:
            return f"`{d['name']}`, written after a `*` marker, is not a source parameter"
        reason = _pair_difference(d, named[1][key], stated, extension)
        if reason:
            return reason
    return None


def _partial_difference(documented: list[dict], source: list[dict], stated: bool, bare: bool,
                        extension: str) -> str | None:
    """Why a documented list that does not claim to be complete differs from the source's, None when it does
    not: each member it writes must be a source parameter (`*args` and `**kwargs` by kind), in the source's order
    (a member after a `*` marker on either side by name alone), with no _pair_difference. A list of bare names
    (`bare`) must also leave out only optional source parameters (a default, a `?`, `*args`, `**kwargs`, a rest),
    and, in a file of a language without keyword arguments (POSITIONAL_EXTENSIONS), none before one it writes,
    which shifts a caller's positions. A list holding an ellipsis claims nothing about what it stands for."""
    used: list[int] = []
    last = -1
    for d in documented:
        at = next((i for i, s in enumerate(source) if i not in used and s["key"] == d["key"]), None)
        if at is None:
            return f"`{d['name']}` is not a source parameter"
        if not (d["by_name"] or source[at]["by_name"]):
            if at < last:
                return (f"`{d['name']}` comes before `{source[last]['name']}` in the source, after it in the "
                        "documented list")
            last = at
        used.append(at)
        reason = _pair_difference(d, source[at], stated, extension)
        if reason:
            return reason
    if not bare:
        return None
    for i, s in enumerate(source):
        if i in used:
            continue
        if not (s["optional"] or s["variadic"]):
            return f"the required source parameter `{s['name']}` is left out"
        later = min((j for j in used if j > i), default=None)
        if extension in POSITIONAL_EXTENSIONS and later is not None:
            return (f"the optional `{s['name']}`, left out before `{source[later]['name']}`, shifts a caller's "
                    f"positions in a `{extension}` file")
    return None


def _parameter_difference(documented_sig: str, source_sig: str, extension: str = "") -> str | None:
    """Why `documented_sig` and `source_sig` do not write the same parameters as signature-comparison-rules.md
    reads them in a file of `extension`, None when they do. When either has no parameter group (_parameters; a
    `;`-joined text has none), the texts before their returns (_signature_parts) are compared, and the reason says
    which side has none.
    Otherwise: the source's leading receiver is dropped, and the documented list's only when the source leads
    with one too, so a documented `(self, a)` against `def f(a)` differs; type parameters both write between the
    name and the group (_type_parameters) must be one text; in a TS/JS file (TS_JS_EXTENSIONS) a source parameter
    with no type and a literal default has that literal's type (_literal_type); a list of bare names (no type,
    default or `?` for any member) or one holding an ellipsis need not write every parameter
    (_partial_difference), and any other list claims to be complete (_complete_difference). A keyword or name
    before the group, a type only one side writes, a default's value, a `*` or `/` marker and the names of `*args`
    and `**kwargs` are never compared. The reason names the count, or the parameter (by position or by name) and
    the fact that differs: its name, its order, its type, its optionality, or the type parameters."""
    documented, source = _parameters(documented_sig, extension), _parameters(source_sig, extension)
    if documented is None or source is None:
        if _signature_parts(documented_sig, extension)[0] == _signature_parts(source_sig, extension)[0]:
            return None
        side = ("neither signature has a" if documented is None and source is None
                else "the documented signature has no" if documented is None else "the source signature has no")
        return f"{side} parameter group, so the texts before the return are compared"
    if source and source[0]["receiver"]:
        source = source[1:]
        if documented and documented[0]["receiver"]:
            documented = documented[1:]
    written, other = _type_parameters(documented_sig, extension), _type_parameters(source_sig, extension)
    if written and other and written != other:
        return f"the type parameters differ: documented `{written}`, source `{other}`"
    if extension in TS_JS_EXTENSIONS:
        source = [{**p, "type": _literal_type(p["default"])} if not p["type"] else p for p in source]
    stated = any(p["optional"] for p in documented if not p["variadic"])
    members = [p for p in documented if not p["ellipsis"]]
    bare = not any(p["type"] or p["optional"] for p in documented)
    if bare or len(members) < len(documented):
        return _partial_difference(members, source, stated, bare and len(members) == len(documented), extension)
    return _complete_difference(documented, source, stated, extension)


def _returns(lines: list[str], number: int, declaration_line: int) -> bool:
    """Whether line `number` (from 1) of `lines` returns: a line after the
    declaration whose text starts with the `return` keyword, or the
    declaration line itself when its own expression body follows its
    parameters there (an arrow function's `=> expr`, a Python
    `def ...: return x`). A type arrow, a callback parameter, a match arm, a
    string or a comment never does."""
    code = lines[number - 1].strip()
    if number != declaration_line:
        return bool(RETURN_START_RE.match(code))
    if TYPE_DECLARATION_RE.match(code):
        return False
    for opener, body in ((PYTHON_DEF_RE.match(code), PYTHON_BODY_RE), (ARROW_OPENER_RE.search(code), ARROW_BODY_RE)):
        end = _after_parens(code, opener.end() - 1) if opener else -1
        if end != -1 and body.match(code, end):
            return True
    return False


def _states_return(text: object, extension: str = "") -> bool:
    """Whether `text`, a `return_type` or the return a documented signature
    writes (_signature_parts), states a return type in a file of
    `extension`, as signature-comparison-rules.md (Annotations) reads it:
    not when it is blank or no text, nor when it is a parenthesized,
    bracketed or braced list of value names (`(nodes, edges)`,
    `[state, setState]`, `{ data, error }`), each item a bare name that
    starts lowercase and is no type name of the file's language
    (LOWERCASE_TYPES; every table for another language or ""). A single
    name (`result`), a list of types (`(str, int)`), a list that writes a
    type among its names and any other text state one."""
    if not isinstance(text, str) or not text.strip():
        return False
    text = text.strip()
    if VALUE_LIST_BRACKETS.get(text[0]) != text[-1]:
        return True
    types = LOWERCASE_TYPES.get(extension, ALL_LOWERCASE_TYPES)
    names = [item.strip() for item in text[1:-1].split(",")]
    return not all(VALUE_NAME_RE.fullmatch(name) and name not in types for name in names)


def contradiction_fact(entry: dict, documented: dict, file: str, declaration_line: int,
                       next_line: int | None = None, source_root: str | None = None) -> str | None:
    """The first fact an annotation-contradicted mismatch rests on that does
    not check, None when each does: the documented entry states a return
    type (a `return_type`, or the return a `documented_sig` writes, that is
    neither blank nor a list of value names: _states_return);
    `documented_sig` and `source_sig` write the same parameters, as the
    comparison rules read them in a file of `file`'s language
    (_parameter_difference, which compares the texts before the return when
    either has no parameter group), read from the form when it gives no
    usage form and lists no parameter (#1025): with no `params` (absent or
    null) it writes no parameter list and claims nothing about parameters,
    so the fact holds whatever `documented_sig` writes before its return,
    and a blank `params` (`""` or `[]`) claims the export takes none, so
    `()` is compared with `source_sig`; `evidence_line` comes
    after the declaration line and before `next_line`, the next surface
    record in the file; and, with `source_root`, that line of `file` under it
    returns (_returns), which alone lets the declaration line itself stand.
    A failed parameter fact quotes the text before each one's return
    (_signature_parts), then says why the two differ."""
    evidence = entry.get("evidence_line")
    extension = _extension(file)
    documented_params, documented_return = _signature_parts(entry["documented_sig"], extension)
    source_params, _ = _signature_parts(entry["source_sig"], extension)
    return_type = documented.get("return_type")
    if not _states_return(return_type, extension) and not _states_return(documented_return, extension):
        return "the documented signature states no return type"
    # A form that gives no usage form and lists no parameter says itself what it claims about parameters (#1025).
    params, usage = documented.get("params"), _gives_usage(documented)
    if params is None and not usage:
        difference = None
    elif _claims_none(documented) and not usage:
        documented_params = "()"
        difference = _parameter_difference(documented_params, entry["source_sig"], extension)
    else:
        difference = _parameter_difference(entry["documented_sig"], entry["source_sig"], extension)
    if difference is not None:
        return f"its parameters differ: documented `{documented_params}`, source `{source_params}`: {difference}"
    if not _is_line(evidence) or evidence < declaration_line:
        return f"evidence_line {json.dumps(evidence)} is before the declaration"
    if next_line is not None and evidence >= next_line:
        return f"evidence_line {evidence} is not before the next declaration in the file, at line {next_line}"
    if source_root is None:
        return None if evidence > declaration_line else (
            f"evidence_line {evidence} is the declaration line, which only --source-root can check")
    lines = _source_lines(source_root, file)
    if lines is None:
        return f"evidence_line {evidence} is in no readable file under --source-root"
    if evidence > len(lines):
        return f"evidence_line {evidence} is past the end of the file ({len(lines)} lines)"
    if not _returns(lines, evidence, declaration_line):
        if evidence == declaration_line:
            return f"evidence_line {evidence}, the declaration line, has no expression body after its parameters"
        return f"evidence_line {evidence} does not start with `return`"
    return None


def grade(difference: str | None, file: str, documented: dict, declared: str | None = None,
          contradiction: str | None = UNCHECKED) -> str:
    """The severity of one mismatch the result reports at `file`. The judge's
    `difference` lowers it only where the script confirms the fact it rests
    on: a parameter-name difference is Low when `declared`, the file the
    plan offered the check at (else `file`), is the mismatch's file and of a
    language with no keyword arguments; an omitted-optional difference on a
    form the inventory marks partial is Info; an annotation-contradicted
    difference is Info when `contradiction`, the fact contradiction_fact
    found failing, is None; every other mismatch is Critical."""
    if difference == "parameter-name":
        at = file if declared is None else declared
        if at.replace("\\", "/") == file.replace("\\", "/") and _extension(at) in POSITIONAL_EXTENSIONS:
            return "Low"
    if difference == "omitted-optional" and _partial(documented):
        return "Info"
    if difference == CONTRADICTED and contradiction is None:
        return "Info"
    return "Critical"


def _gap_record(m: dict) -> dict:
    name, where = m["name"], f"{m['file']}:{m['line']}"
    issue = f"documented `{m['documented_sig']}`, source `{m['source_sig']}`: {m['issue']}"
    remediation = (f"Update the documented signature of `{name}` from `{m['documented_sig']}` "
                   f"to `{m['source_sig']}`, the signature the source defines at `{where}`.")
    if m["severity"] == "Info" and m["difference"] == CONTRADICTED:
        body = f"{m['file']}:{m['evidence_line']}"
        return {
            "severity": "Info",
            "category": "observation",
            "title": f"Annotation contradicted: {name}",
            "source": where,
            "export": name,
            "issue": (f"the source annotates the return of `{name}` otherwise than the skill documents, and its "
                      f"body returns the documented type at `{body}`: {issue}"),
            "remediation": (f"No change to the skill: it documents what `{name}` returns, as `{body}` shows. "
                            f"Report the return annotation at `{where}` upstream, since the body contradicts it."),
        }
    if m["severity"] == "Info":
        return {
            "severity": "Info",
            "category": "observation",
            "title": f"Partial signature: {name}",
            "source": where,
            "export": name,
            "issue": (f"the skill labels its documented form of `{name}` partial, and it leaves out only "
                      f"members the source marks optional: {issue}"),
            "remediation": (f"No change: the documented form of `{name}` is labelled partial and leaves out "
                            f"only optional members of the signature the source defines at `{where}`."),
        }
    if m["severity"] == "Low":
        issue = (f"{issue} (only the parameter names differ, and a caller of a `{_extension(m['file'])}` "
                 "file passes its arguments by position)")
    return {
        "severity": m["severity"],
        "category": "signature-mismatch",
        "title": f"Signature mismatch: {name}",
        "source": where,
        "export": name,
        "issue": issue,
        "remediation": remediation,
    }


def _form_text(form: dict) -> str:
    """A documented form on one line: its usage form, else its parameters and return type (`-> R` alone for a form
    with no `params` that writes a return type)."""
    def text(value: object, sep: str = ", ") -> str:
        return sep.join(str(v) for v in value) if isinstance(value, list) else str(value)
    if _gives_usage(form):
        return text(form["usage_signature"], "; ")
    return_type = form.get("return_type")
    tail = f" -> {text(return_type)}" if isinstance(return_type, (str, list)) and text(return_type).strip() else ""
    params = form.get("params")
    if params is None and tail:
        return tail.lstrip()
    return f"({text('' if params is None else params)}){tail}"


def _sig_text(text: str) -> str:
    """A signature as a mismatch's `documented_sig` and a form compare: whitespace runs as one space, outer parentheses off."""
    text = " ".join(text.split())
    while text.startswith("(") and _after_parens(text, 0) == len(text):
        text = text[1:-1].strip()
    return text


def _quotes(documented_sig: str, form: dict) -> bool:
    """Whether `documented_sig` is the text of `form`: its parameters (a list joined; blank or absent, `()`, for a
    form with no usage form, so `()` never quotes a usage-only form), or one of its usages, whole or before the
    return type it writes, with or without a name or a dotted receiver before its parameter group
    (`run_pipeline(tasks, data)`, `coco.default_env()`: #919); a usage also reads without its dotted receiver, its
    name kept (`default_env()` quotes `coco.default_env()`)."""
    usage = form.get("usage_signature")
    usages = [" ".join(u.split()) for u in (usage if isinstance(usage, list) else [usage]) if isinstance(u, str)]
    texts = {_sig_text(t) for u in usages for t in (u, CALL_RECEIVER_RE.sub("", u, count=1))} - {""}
    params = _sig_text(_field_text(form.get("params")))
    if params or not _gives_usage(form):
        texts.add(params)
    head = _signature_parts(documented_sig)[0]
    named = LEADING_NAME_RE.sub("", head, count=1)
    return bool({_sig_text(documented_sig), _sig_text(head), _sig_text(named)} & texts)


def _form_gap_record(m: dict, index: int, forms: list[dict]) -> dict:
    """_gap_record's record. For a name with several forms its title and Issue name the documented form the mismatch
    concerns, counted from 1, so the ledger keeps one gap per form (its dedupe reads the title, never the Issue)."""
    record = _gap_record(m)
    if len(forms) > 1:
        record["title"] += f" (form {index + 1} of {len(forms)})"
        record["issue"] += f" (documented form {index + 1} of {len(forms)}: `{_form_text(forms[index])}`)"
    return record


def _form_index(name: str, entry: dict, forms: list[dict]) -> tuple[int, bool, list[str]]:
    """(the index of the documented form `entry`, a mismatch of `name`, is
    graded against, whether its label may lower the grade, the notes that
    say why the form or its grading is not the one its `form` names): an
    index past `forms` is `documented`; for a name with several forms, one
    whose text its `documented_sig` is not (_quotes) gives way to the form
    it quotes, else it stays (its title, Issue and bound declaration are
    that form's, #919) and its label lowers nothing: it is graded as a full
    form, with a note when it is not `documented` or is partial."""
    notes = []
    # the judge's own `form`, which a note names even when it is past `forms`
    index = named = entry.get("form") or 0
    if index >= len(forms):
        notes.append(f"a signature mismatch for `{name}` names `form` {index}, no form its check offered "
                     f"(0 to {len(forms) - 1}): graded against `documented`")
        index = 0
    if len(forms) > 1 and not _quotes(entry["documented_sig"], forms[index]):
        quoted = next((j for j, f in enumerate(forms) if _quotes(entry["documented_sig"], f)), None)
        if quoted is not None:
            notes.append(f"a signature mismatch for `{name}` names `form` {named}, whose text its "
                         f"`documented_sig` is not: graded against form {quoted}, the one it quotes")
            return quoted, True, notes
        if index != 0 or _partial(forms[index]):
            notes.append(f"a signature mismatch for `{name}` names `form` {named}, whose text its "
                         f"`documented_sig` is not, nor any other form's: graded against form {index} as a full form")
        return index, False, notes
    return index, True, notes


def score(inventory: list[dict], names: list[str], exports: list[dict], results: list[dict],
          type_names: list[str] | None = None, offered: dict[str, list[str]] | None = None,
          source_root: str | None = None, planned: dict[str, list[dict]] | None = None,
          bound: dict[str, dict[int, dict]] | None = None) -> dict:
    """The two categories: Signature Accuracy over the signature universe of
    `names` (the `all` set) and `exports`, Type Coverage over `type_names`
    when given, else over `names`. A fallback scan's exports_found join the
    universe, and `names` when no `type_names` is given. `offered` (read
    from --plan) names the files the plan offered each check at;
    `source_root` (--source-root) is the local tree an
    annotation-contradicted mismatch's `evidence_line` is checked in. A
    mismatch is graded against the documented form its `form` names: of
    documented_forms, or of `planned` (read from --plan) for a name it
    holds, with a warning where the two differ. `bound` (read from --plan,
    #918) gives the declaration each bound form of a name is compared with:
    that form's mismatch is taken at its file and line, with a warning when
    the judge names another file, and its line bounds the next declaration
    in that file as a surface record's does. A bound declaration joins no
    name, set or count."""
    bound = bound or {}
    by_name = _records_by_name(exports)
    # The declarations a line is located among: the surface's records, and each one a form is bound to (an other
    # declaration only through a binding).
    located = exports + [{"name": name, **at} for name, forms in bound.items() for at in forms.values()]
    # A fallback scan reports its own names and types.
    fallback_types = {n for r in results for n in r.get("types_found") or []}
    surface = set(names) | {n for r in results for n in r.get("exports_found") or []}
    documented = documented_names(inventory)
    forms = documented_forms(inventory)
    compared = (surface | signature_universe(names, exports)) & set(forms)
    warnings = []
    for name in sorted(set(forms) & set(planned or {})):
        if planned[name] != forms[name]:
            differ = (f"{len(planned[name])} documented form(s), not the {len(forms[name])} the inventory gives"
                      if len(planned[name]) != len(forms[name]) else "different forms than the inventory gives")
            warnings.append(f"`{name}`: the plan offered {differ}: graded against the plan's")
            forms[name] = planned[name]

    graded: dict[tuple, dict] = {}
    seen = set()
    for result in results:
        for entry in result["signature_mismatches"]:
            name = entry["name"]
            files = _offered_files(offered, by_name, name)
            # A mismatch found at one of a check's candidates names that file; any other file is not taken.
            named = entry.get("file")
            file = _path(named if named is not None and _is_offered_file(files, named) else result["file"])
            line = entry["line"]
            if name not in compared:
                if (name, file, line) not in seen:
                    warnings.append(f"{file}:{line}: a signature mismatch for "
                                    f"`{name}`, which is no documented signature on the source surface: "
                                    "not scored, no gap")
                seen.add((name, file, line))
                continue
            # The documented form the mismatch is reported for: 0 is `documented`, n the check's nth alternative.
            # A form's own label lowers a grade only for the form the mismatch quotes as `documented_sig`.
            index, quoted, notes = _form_index(name, entry, forms[name])
            # A bound form is compared with its bound declaration alone: its mismatch is taken there (#918).
            at = bound.get(name, {}).get(index)
            if at is not None:
                judged = _path(named if named is not None else result["file"])
                file, line = _path(at["file"]), at["line"] if _is_line(at["line"]) else line
                if judged != file:
                    warnings.append(f"{result['file']}:{entry['line']}: a signature mismatch for `{name}` names "
                                    f"`{judged}`, but its form {index} is bound to the declaration at "
                                    f"{file}:{line}: recorded there")
            elif named is not None and not _is_offered_file(files, named):
                warnings.append(f"{result['file']}:{entry['line']}: a signature mismatch for `{name}` names "
                                f"`{named}`, no file the plan offered its check at: recorded at "
                                "the result's file")
            for note in notes:
                if f"{file}:{line}: {note}" not in warnings:
                    warnings.append(f"{file}:{line}: {note}")
            form = forms[name][index]
            if not quoted:
                # A text that quotes no form never earns that form's partial label (#919).
                form = {f: v for f, v in form.items() if f != "signature_form"}
            # Each usage of a list is a form of its own: one key per documented text.
            key = (name, file, line, index, _sig_text(entry["documented_sig"]))
            difference = entry.get("difference")
            # Graded at the file only when the plan offered it (a bound form its declaration's): never Low at a
            # namesake it did not offer.
            if at is not None:
                declared = file
            else:
                declared = (file if _is_offered_file(files, file) else files[0]) if files else None
            # The facts of an annotation-contradicted mismatch, checked once and handed to grade().
            fact = None
            if difference == CONTRADICTED:
                at_line = line if at is not None else _declaration_line(by_name, name, file, line)
                fact = contradiction_fact(entry, form, file, at_line,
                                          _next_declaration(located, file, at_line), source_root)
                warning = (f"{file}:{at_line}: the mismatch for `{name}` is tagged {CONTRADICTED}, but {fact}: "
                           "graded as an untagged mismatch (Critical)")
                if fact is not None and warning not in warnings:
                    warnings.append(warning)
            severity = grade(difference, file, form, declared, fact)
            # Every entry is graded: one declaration reported twice against one form keeps its most severe grade.
            if key in graded and GRADES.index(graded[key]["severity"]) <= GRADES.index(severity):
                continue
            graded[key] = {"name": name, "file": file, "line": line,
                           "source_sig": entry["source_sig"], "documented_sig": entry["documented_sig"],
                           "issue": entry["issue"], "difference": difference, "severity": severity}
            if difference == CONTRADICTED:
                graded[key]["evidence_line"] = entry.get("evidence_line")
    # A check that offered several files keeps one mismatch per form, its least severe (the closest candidate);
    # a bound form was offered its one declaration. Each form's mismatch stands on its own.
    def order(item: tuple) -> tuple:
        (_, _, _, index, text), m = item
        return m["file"], m["line"], m["name"], index, text

    kept, closest = [], {}
    for key, m in sorted(graded.items(), key=order):
        bucket = (m["name"], key[3], key[4])
        single = key[3] in bound.get(m["name"], {}) or len(
            {_path(f) for f in _offered_files(offered, by_name, m["name"])}) < 2
        if single:
            kept.append((key, m))
        elif bucket not in closest or GRADES.index(m["severity"]) > GRADES.index(closest[bucket][1]["severity"]):
            closest[bucket] = (key, m)
    kept = sorted(kept + list(closest.values()), key=order)
    mismatches = [m for _, m in kept]

    # A Low or an Info mismatch is a caller-invisible difference: it still matches.
    wrong = {m["name"] for m in mismatches if m["severity"] == "Critical"}
    if compared:
        signature_accuracy = round2((len(compared) - len(wrong)) / len(compared) * 100)
    else:
        signature_accuracy = 100.0
        warnings.append("no documented signature is on the source surface: Signature Accuracy has "
                        "nothing to compare and scores 100")

    def kind_of(name: str) -> str | None:
        if name in fallback_types:
            return "type"
        return next((r.get("kind") for r in by_name.get(name, []) if r.get("kind")), None)

    pool = surface if type_names is None else set(type_names)
    types = {n for n in pool if kind_of(n) in TYPE_KINDS}
    # A name the stale-scope guard restored (#913) or the extraction recorded with no kind, such as an extraction gap
    # (#1020), may be a type when the provenance map gives it none at its file: Type Coverage leaves it out and names
    # it, never lowering the score. A per-file name outside its result's types_found is no type.
    kindless = sorted(n for n in pool - fallback_types if kind_of(n) is None
                      and any(r.get("origin") in ("restored", "extraction") for r in by_name.get(n, [])))
    documented_types = types & documented
    if types:
        type_coverage = round2(len(documented_types) / len(types) * 100)
    else:
        type_coverage = 100.0
    if kindless:
        warnings.append("Type Coverage leaves out each name the stale-scope guard restored or the extraction "
                        "recorded with no kind, such as an extraction gap (the provenance map, when one is given, "
                        "gives it no kind Type Coverage reads at its file): "
                        + ", ".join(f"`{n}`" for n in kindless))
    elif not types:
        warnings.append("the source surface has no interface, type alias, enum or class: Type "
                        "Coverage has nothing to cover and scores 100")

    return {
        "valid": True,
        "signatureAccuracy": signature_accuracy,
        "matchingSignatures": len(compared) - len(wrong),
        "totalDocumented": len(compared),
        "comparedNames": sorted(compared),
        "typeCoverage": type_coverage,
        "documentedTypes": len(documented_types),
        "totalTypes": len(types),
        "missingTypes": sorted(types - documented),
        "mismatches": mismatches,
        "gapRecords": [_form_gap_record(m, key[3], forms[m["name"]]) for key, m in kept],
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write_json(path: str, payload) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _cmd_plan(args: argparse.Namespace) -> tuple[dict, int]:
    inventory = load_inventory(args.inventory)
    names, exports, others = (None, [], [])
    if args.surface is not None:
        _, exports, names = load_surface(args.surface, args.surface_set)
        others = load_other_declarations(args.surface)
    if args.skill_dir is not None:
        if not args.skill_dir.strip():
            raise InputError("--skill-dir is empty: pass the skill package (the folder that holds SKILL.md)")
        _read_text(str(Path(args.skill_dir) / "SKILL.md"), "--skill-dir")
    out = plan(inventory, names, exports, args.skill_dir, others)
    if args.output:
        _write_json(args.output, out)
        # The step reads the plan from the file, so stdout gives only its counts and the path (#1018).
        return {"compared": out["compared"], "files": len(out["files"]),
                "checks": sum(len(group["checks"]) for group in out["files"]),
                "documented": len(out["documentedSignatures"]), "output": args.output}, 0
    return out, 0


def _cmd_score(args: argparse.Namespace) -> tuple[dict, int]:
    if args.source_root is not None and not (args.source_root.strip() and Path(args.source_root).is_dir()):
        raise InputError(f"--source-root {args.source_root!r} is no folder: pass the local source tree the judges read")
    inventory = load_inventory(args.inventory)
    chosen, exports, names = load_surface(args.surface, args.surface_set)
    results, violations = load_results(args.results or [])
    if violations:
        for path in (args.output, args.gaps_output):
            if path:
                Path(path).unlink(missing_ok=True)
        return {"valid": False, "violations": violations}, 2
    offered = load_plan(args.plan) if args.plan is not None else None
    planned = load_plan_forms(args.plan) if args.plan is not None else None
    bound = load_plan_bound(args.plan) if args.plan is not None else None
    out = score(inventory, names, exports, results, None if args.surface_set == "all" else chosen, offered,
                args.source_root, planned, bound)
    if args.output:
        _write_json(args.output, out)
    if args.gaps_output:
        _write_json(args.gaps_output, out["gapRecords"])
    return out, 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="score-signatures",
        description="Signature Accuracy and Type Coverage from schema-checked per-file results.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="the signature comparisons for the subagents to make")
    p.add_argument("--inventory", required=True, help="the validated inventory file")
    p.add_argument("--surface", help="load-coverage-inputs.py surface output")
    p.add_argument("--surface-set", default="all",
                   help="a surface name set, which must exist (default: all); the plan compares the signature "
                        "universe whichever set it names")
    p.add_argument("--skill-dir", help="the skill package under test: its citations pick the declaration of a name "
                                       "the surface records in several files, and bind each form whose own "
                                       "citations name one declaration of its name to it")
    p.add_argument("--output", help="write the plan to this file and print only its summary")
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("score", help="the two category scores and the mismatch gap records")
    p.add_argument("--inventory", required=True, help="the validated inventory file")
    p.add_argument("--surface", required=True, help="load-coverage-inputs.py surface output")
    p.add_argument("--surface-set", default="all",
                   help="the surface name set Type Coverage counts (default: all)")
    p.add_argument("--plan", help="the plan's output: the files each check offered a mismatch at, and the "
                                  "declaration each bound form's mismatch is taken at")
    p.add_argument("--source-root", help="the local source tree the judges read: an annotation-contradicted "
                                         "mismatch's evidence_line must start with `return` there, or be the "
                                         "declaration line with its expression body")
    p.add_argument("--results", action="append", help="a subagent result file (repeatable)")
    p.add_argument("--output", help="also write the scores to this file")
    p.add_argument("--gaps-output", help="write the gap ledger records to this file")
    p.set_defaults(func=_cmd_score)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        out, code = args.func(args)
    except (InputError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return code


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
    sys.exit(main())
