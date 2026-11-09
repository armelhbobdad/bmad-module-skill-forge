#!/usr/bin/env python3
"""Prose pins: every Test Skill signature judge compares by one rules file (#827, #835).

The signature judges used to compare "params: name, type, order, optionality;
and the return type" with no rule for a component, an annotation a form
leaves out or two spellings of one type, so `FC<P>` against
`(props: P) => JSX.Element`, a zero-argument entry against `-> None` or
`dict` against `dict[str, Any]` was Critical for one judge and a match for
another. The fallback per-file scan's subagents got only the overload rule
and none of the `difference` tags. These tests keep:
- `references/signature-comparison-rules.md`, a reference with no
  frontmatter and six sections: Reading a form, Components, Annotations,
  Equivalent spellings, Overload sets and Difference tags, the last two
  moved out of coverage-check.md §2, so each has one copy;
- each rule its sections state, and every `difference` value
  score-signatures.py accepts, defined in that file and only there
  (scoring-rules.md's Low and Info rows point at it), a return annotation
  the body contradicts included: a mismatch tagged
  `annotation-contradicted` with `evidence_line`, an Info observation
  coverage-check.md §2b's `score` checks against the local source;
- coverage-check.md binding the file as `{signatureRulesFile}` and naming it
  at each judge: §1's split-body cross-check and §2's judge, each given its
  absolute path, and the main-thread compare and §5b's split-body Source
  (the Split-Body Sources section of coverage-check-branches.md, #841),
  which load it; the fallback per-file scan of coverage-check-tiers.md gives
  its subagents the absolute path too, and neither repeats the overload rule
  or the tag definitions;
- coherence-check.md binding the file the same way and giving its contextual
  reference judge, whose `signature_match` is an `inaccurate-reference` gap,
  its absolute path;
- the split-body cross-check comparing a parameter's optionality only when
  both forms state it, the file (not coverage-check.md §1) saying what a form
  may leave out, each export's form read alone (#843), and forms attributed
  to two declarations of one name never compared with each other there
  (#927);
- the forms one file writes for one name as an overload set read there as
  one documented set, as a source's is, its own forms never compared with
  each other (#1017);
- a leading receiver one documented form writes and the other leaves out
  never compared there, since neither form is the source, by every
  receiver score-signatures.py drops, Rust's `&mut self` included (#1045);
- a partial label in a table's column header labelling each of its rows;
- a name written with empty parentheses in running text or a description
  cell (any cell but an export table's first cell and a call or signature
  column, by role) read as a mention, no form, in the contract and the
  rules alike, a heading or first cell `name()` staying a form (#887);
- a usage form read as what it writes, in the call-example rule, and a
  name documented in several forms compared with each form by its own
  rules, a mismatch reported for each form that does not match, on §2's
  path and the fallback scan's alike (#826); a component whose props live
  outside the source tree left uncompared (#837);
- a const annotated with a function type declaring that type's
  parameters, the arrow's destructuring that same parameter, so a form may
  write it either way, and a partial destructuring reading as no narrower
  type (#928);
- a call to a class compared with its constructor, an instance's call with
  its `__call__`, an alias's with its class's, a source's leading receiver
  never compared and a callee's `*args` and `**kwargs` taking any extra
  argument (#968);
- a declaration whose parameter list is written only in a package outside
  the source tree left uncompared and counted as matching, as such a
  component's props are (#925);
- a return written as names of values (`→ (nodes, edges)`) stating no
  return type, a type name written alone, lowercase ones included, still
  stating one (#930);
- a rest element in a component's destructured props form standing for
  every prop the form does not name, own or inherited, a rule of
  Components alone (#932);
- a form the check binds, whose own citations name one declaration of its
  name, compared with that declaration alone and reported there, in the
  rules file and §2, and the place, `at`, the contract has each form give
  (#918);
- Create Skill naming a component's Props interface as its contract, not
  `(props: XProps) => JSX.Element`;
- a call written with placeholder names, which the inventory contract
  records as a usage, read as a call, a bracketed argument optional, and an
  entry's `params` written as a list of bare names read as parameter names,
  whatever the names (#916).

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_SKILL = REPO_ROOT / "src" / "skf-test-skill"
REFS = TEST_SKILL / "references"
RULES = REFS / "signature-comparison-rules.md"
COVERAGE = REFS / "coverage-check.md"
COVERAGE_TIERS = REFS / "coverage-check-tiers.md"
COHERENCE = REFS / "coherence-check.md"
SCORING = REFS / "scoring-rules.md"
SCORE_SIGNATURES = TEST_SKILL / "scripts" / "score-signatures.py"
COMPONENT_EXTRACTION = REPO_ROOT / "src" / "skf-create-skill" / "references" / "component-extraction.md"
# Create Skill's props table, whose empty Default cells must never read a prop as required.
COMPILE_ASSEMBLY = REPO_ROOT / "src" / "skf-create-skill" / "assets" / "compile-assembly-rules.md"

SECTIONS = ["Reading a form", "Components", "Annotations", "Equivalent spellings", "Overload sets",
            "Difference tags"]
OVERLOAD_RULE = "is read through its implementation"
TAG_DEFINITION = "A mismatch carries `difference` when the two differ only in one of these ways"
ABSOLUTE_PATH = "the absolute path of `{signatureRulesFile}` (under `{skill-root}`)"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str | None) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    if end is None:
        return text[i:]
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    section = text[i:j]
    assert section.strip(), f"empty slice between {start!r} and {end!r}"
    return section


def _flow(text: str) -> str:
    """The text with each run of whitespace folded to one space, so a hard-wrapped sentence reads as one line."""
    return re.sub(r"\s+", " ", text)


def _section(name: str) -> str:
    """One `## ` section of the rules file, flowed."""
    i = SECTIONS.index(name)
    end = f"## {SECTIONS[i + 1]}" if i + 1 < len(SECTIONS) else None
    return _flow(_slice(_read(RULES), f"## {name}\n", end))


def _frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", _read(path), re.S)
    assert match, f"{path.name} has no frontmatter"
    return yaml.safe_load(match.group(1))


def _paragraph(text: str, opening: str) -> str:
    """The paragraph of `text` that starts with `opening`, flowed."""
    [paragraph] = [p for p in text.split("\n\n") if p.startswith(opening)]
    return _flow(paragraph)


def test_the_rules_file_is_a_reference_with_its_six_sections():
    """A reference the judges are given by path, not a step: no frontmatter, so no nextStepFile chains to it. Its
    opening names every judge that reads it."""
    text = _read(RULES)
    assert not text.startswith("---"), "a reference file, not a step file"
    assert re.findall(r"^## (.+)$", text, re.M) == SECTIONS
    assert "\u2014" not in text, "no em dash"
    opening = _flow(_slice(text, "# Signature Comparison Rules", "## Reading a form"))
    for judge in ("coverage-check.md §1's split-body cross-check", "its §2 judge (or the main thread in its place)",
                  "its §5b split-body Source (the Split-Body Sources section of coverage-check-branches.md)",
                  "coverage-check-tiers.md's fallback per-file scan",
                  "coherence-check.md §4's reference judge (its `signature_match`)"):
        assert judge in opening, judge


def test_a_form_claims_only_what_it_writes():
    """#835: optionality is stated only by a default, a `?` or an optional marker, never by a type: a list that states
    it for no member has its optionality uncompared, and once one member states it the unmarked ones claim to be
    required. A default's value is not compared. In the split-body cross-check an annotation either form leaves out
    is not compared. #1025: an entry with no `params` key and no usage form writes no parameter list, so it claims
    nothing about parameters, while a blank `params` claims the export takes none."""
    reading = _section("Reading a form")
    assert "A form claims only what it writes" in reading
    assert ("A type or a return type it does not write claims nothing (Annotations). An entry with no `params` key and "
            "no usage form writes no parameter list: it claims nothing about parameters, and only what it writes, such "
            "as its return type, is compared. `params: \"\"` or `[]` claims the export takes none.") in reading
    assert "The source's declaration decides" in reading
    assert "with one exception, a return annotation the body contradicts (Annotations)" in reading
    assert ("Optionality is stated only by a default, a `?` (on the name, or as `?:`) or an optional marker: "
            "`optional` in a docstring-style list, a Required column, a Default cell that gives a value. A type never "
            "states it, and an empty Default cell states nothing.") in reading
    assert ("A list of parameters or props, or a table, that states optionality for none of its members states none, "
            "and optionality is not compared: `connect(host: str, port: int)` matches "
            "`def connect(host: str, port: int = 5432)`.") in reading
    assert ("Once a list states optionality for any member, each member it writes with no mark, unless it is rest or "
            "variadic, claims to be required; a Default cell and a destructuring default mark only their own member "
            "(Components).") in reading
    assert "A default's value is not compared: it only marks its parameter optional." in reading
    assert "defaults" not in _section("Difference tags"), "a default's value is no fact `parameter-name` compares"


def test_a_form_that_opens_with_shared_text_writes_its_members():
    """6.0.0 release gate (oms-cognee): an inventory entry for one of several names a skill documents together
    carries the members they share, then `; `, then its own (inventory-contract.md). Reading a form says that form
    writes both, so a judge reads the shared members as part of it, before the name's own, and the required field
    the shared text states is no member the form leaves out. A reading rule only: no comparison rule changes."""
    reading = _section("Reading a form")
    assert ("A form that opens with text the skill states once for several names, then `; ` and the name's own "
            "members (inventory-contract.md), writes both: the members the shared text states are members that form "
            "writes, read before its own.") in reading
    assert reading.index("A default's value is not compared") < reading.index(
        "A form that opens with text the skill states once"), "after the paragraph on optionality"


def test_a_call_an_ellipsis_and_bare_names_claim_no_complete_list():
    """A replay of real skills' signature checks: call examples, an ellipsis and a list of bare names do not claim a
    complete parameter list, so an optional parameter they leave out is no difference, while a typed form still
    claims its list is complete (#834's `(date: Date) => string` stays `omitted-optional`). #916: an entry's `params`
    written as such a list names parameters whatever its names are, and a call expression comes as a usage, read as a
    call, so the judge reads each form by the field the inventory contract routes it to."""
    reading = _section("Reading a form")
    assert "Three kinds of form do not claim a complete parameter list:" in reading
    assert ("It is compared as a call: each argument it passes must exist, by position or by name, and every required "
            "parameter must be passed; an optional parameter it leaves out is no difference.") in reading
    assert ("An empty call `X()` written as a call example (in a heading, an export table's first cell, a call or "
            "signature column or a fenced example, never a mention) is one too, so it matches a source whose "
            "parameters are all optional.") in reading
    assert ("An ellipsis (`...` or `\u2026`) in a list stands for members it does not show and claims nothing about "
            "them") in reading
    assert "`(...)` and `(tasks, data, dataset, ...)` leave out no parameter." in reading
    assert ("A list of bare names, with no type, default or `?` (`connect(host, port)`, `({ themes, defaultTheme })`), "
            "names parameters without claiming the list is complete") in reading
    [bare] = [line for line in _read(RULES).splitlines() if line.startswith("- A list of bare names")]
    assert bare.endswith("an optional member it leaves out is no difference, a required one is a mismatch. An "
                         "entry's `params` written as such a list is read this way, whatever the names; a call "
                         "expression comes as a usage (inventory-contract.md) and is read as a call (above)."), bare
    assert ("A form that writes a type or a default for a parameter (`(date: Date) => string`) claims its list is "
            "complete: an optional parameter it leaves out is an `omitted-optional` difference") in reading
    assert "one it adds where the source has none is no difference: calls that follow the form are valid." in reading
    props = _section("Components")
    assert ("An optional own prop a typed props list or a table leaves out is an `omitted-optional` difference; one a "
            "list of bare names or a usage leaves out, and an optional inherited prop, is no difference.") in props


def test_a_caller_following_a_narrower_form_makes_a_valid_call():
    """A documented parameter type naming some of a union's members, a union of callables written as one callable
    returning a union, and a form taking the unions of an overload set's parameter types are no mismatch. #1023:
    Overload sets named only Python `@overload` stubs and TS bodiless signatures, so overloaded constructors and
    functions in Java, Kotlin, C# and C++, which the fallback per-file scan's judges read by this file, had no
    stated reading, and a correct `new Client("localhost", 8080)` compared with one constructor could be a Critical
    mismatch that blocks the hard gate. A name declared several times with no implementation they share is one set
    too, and a form matching any of its declarations is no mismatch."""
    annotations = _section("Annotations")
    assert ("A documented parameter type that names some of the members of the source's union is no mismatch, since a "
            "caller passing it makes a valid call") in annotations
    assert "a documented return type must cover every member the source can return." in annotations
    spellings = _section("Equivalent spellings")
    assert "`Callable[[A], X] | Callable[[A], Y]` and `(a: A) -> X | Y`" in spellings
    overloads = _section("Overload sets")
    languages = ("(overloaded constructors in Java, Kotlin, C# and C++, a Kotlin class's primary and secondary "
                 "constructors among them, and overloaded methods in those languages and functions in Kotlin and C++)")
    separate = ("A name declared several times with different parameter lists and no implementation they share "
                f"{languages} is one set too: a documented form that matches any of its declarations is no mismatch "
                "(`new Client(\"localhost\", 8080)` matches `Client(String host, int port)` beside "
                "`Client(String host)`).")
    assert separate in overloads, "#1023: other languages' overloads are one set"
    assert overloads.index(OVERLOAD_RULE) < overloads.index(separate), "after the stub rule, which stays as it is"
    assert _read(RULES).count("no implementation they share") == 1, "one copy"
    assert "the unions of the overloads' types" in overloads


def test_a_documented_overload_set_is_read_as_one_set():
    """#1017 (oms-cognee 1.6.2): Overload sets spoke only of a source declaration, so in the split-body cross-check a
    body form that defaults `dataset` and `format` could be compared with one documented `@overload` stub that
    requires both and fail on optionality, though it matches the implementation the same reference writes after its
    stubs. The forms one file writes for one name as an overload set are one documented set, read as a source's is:
    a form on the other side matching its implementation, a stub or the stubs' unions is no mismatch, and the set's
    own forms are never compared with each other."""
    overloads = _section("Overload sets")
    source = ("A declaration opening an overload set (Python `@overload` stubs, TS bodiless signatures) is read through "
              "its implementation")
    documented = ("In the split-body cross-check, the forms one file writes for one name as an overload set "
                  "(`@overload` stubs or TS bodiless signatures, and the implementation after them when the file "
                  "writes it) are one documented overload set, read as a source's is: a form on the other side that "
                  "matches its implementation, any of its stubs or, position by position, the unions of the stubs' "
                  "parameter types is no mismatch, so a form that defaults `format` matches a set whose stub requires "
                  "it and whose implementation defaults it.")
    own = "The set's own forms are compared neither with each other nor with its implementation."
    for sentence in (source, documented, own):
        assert sentence in overloads, sentence
    assert overloads.index(source) < overloads.index(documented) < overloads.index(own), "the source's rule comes first"
    assert _flow(_read(RULES)).count("one documented overload set") == 1, "one copy"


def test_a_usage_form_is_read_as_what_it_writes():
    """#826, deferred from #862: an entry whose only form is its `usage_signature` had no rule saying how it is read.
    The call-example rule, its one copy, reads a component usage as a list of bare names of the props it sets and a
    call as its arguments in order; a spread, children or `...args` can pass a required member; each usage of a list
    is a form of its own. #916 (oms-cocoindex): a call written with placeholder names, which the inventory contract
    records as a usage, is read the same way, its names arguments at their positions and never parameter names, and
    a bracketed argument is optional, so the call is compared with and without it. #1024: the rule said what a JSX
    spread or a TS/JS `...args` passes but not Python's `*items` or `**mapping`, so `Settings(**config)` read
    literally passed no required parameter, a Critical that blocks the hard gate. It now says what each unpacking
    passes, keeps the arguments written beside it compared, and the placeholder `*args` and `**kwargs` unpack the
    same way."""
    reading = _section("Reading a form")
    assert ("A component usage `<X a={x} b=\"y\" />` reads as a list of bare names of the props it sets, and a call "
            "`f(a, b)` as its arguments in order, each the parameter at its position (or, written `name=value`, the one "
            "it names).") in reading
    spread = ("A JSX spread (`{...props}`) or children can pass a required prop, and a call's `...args` a required "
              "parameter, so neither leaves one out.")
    assert spread in reading
    unpacking = ("A Python `*items` argument can pass every parameter a caller may pass by position from its position "
                 "on, and a `**mapping` argument every one a caller may pass by name, so neither leaves such a "
                 "parameter out (`Settings(**config)` matches `__init__(self, host, port)`), while the arguments the "
                 "call writes beside them are still compared (`Settings(**config, debug=True)` is a mismatch when the "
                 "constructor takes neither `debug` nor `**kwargs`); a `*items` never passes a keyword-only "
                 "parameter, nor a `**mapping` a positional-only one.")
    usage = ("An entry's `usage_signature` written as a usage is read this way, and each usage in a list of usages is "
             "compared as a form of its own, under its entry's `form` index.")
    assert usage in reading
    assert f"{spread} {unpacking} {usage}" in reading, "#1024: right after the spread sentence, before the usage rule"
    assert reading.count("`Settings(**config)`") == 1, "#1024: one copy of the unpacking rule"
    # score-signatures.py's parameter fact still refuses an unpacking, on the strict side, and its docstring says so
    assert ("a call's `*items` or `**mapping` argument (read as a `*args` or `**kwargs` the source must declare, so "
            "`Settings(**config)` against `__init__(self, host, port)` differs)") in _flow(_read(SCORE_SIGNATURES))
    assert reading.count("`usage_signature`") == 1, "one copy of the usage rule"
    # the bullet it extends, and the bare-names rule it reads by
    call = _paragraph(_read(RULES), "- A call or usage example passes values")
    assert "A component usage `<X a={x} b=\"y\" />` reads as a list of bare names" in call
    assert "A list of bare names, with no type, default or `?`" in reading
    placeholder = ("A call written with placeholder names (`await coco.mount([subpath,] process_fn, *args, "
                   "**kwargs)`), which the inventory contract records as a usage, is read the same way: its names "
                   "are arguments at their positions, never parameter names, its `*args` and `**kwargs` unpack as "
                   "above, and a bracketed argument (`[subpath,]`) "
                   "is optional, so the call is compared with and without it, each as a call.")
    assert f"under its entry's `form` index. {placeholder}" in call, "the call bullet's last sentence"
    [bullet] = [line for line in _read(RULES).splitlines() if line.startswith("- A call or usage example")]
    assert bullet.endswith(placeholder), bullet


def test_each_documented_form_of_a_name_is_compared_by_its_own_rules():
    """#826: a brief form in SKILL.md stood in for the full props list of a reference file. `plan` now offers the
    name's other forms as `alternatives` (the fallback scan's `documentedAlternatives`), and the judge compares the
    declaration with each by its own reading rules and reports a mismatch for each form that does not match, naming
    it in `form`, the index score-signatures.py checks and grades by; with `candidates`, at the closest one. §2 points
    its judge at the rule, and the fallback scan hands its subagents the alternatives."""
    reading = _section("Reading a form")
    assert ("A name the skill documents in several forms (a brief usage in SKILL.md, a full props list in a reference "
            "file) comes with `alternatives`: coverage-check.md §2's check lists them after its `documented` form, and "
            "the fallback per-file scan's `documentedAlternatives` holds them by name.") in reading
    assert ("Compare the declaration with each form the check offers, each by its own reading rules, and report a "
            "mismatch for each form that does not match, with its index as `form` (0 is `documented`, 1 the first "
            "alternative), its `documented_sig` written as that form and its `difference` tagged against it.") in reading
    assert ("With `candidates`, a form matches when it matches any candidate, and its mismatch is reported at the "
            "closest candidate.") in reading
    assert "only when none matches" not in reading and "differs from least" not in reading
    spec = importlib.util.spec_from_file_location("score_signatures", SCORE_SIGNATURES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check_result({"file": "a.ts", "signature_mismatches": [
        {"name": "x", "line": 1, "source_sig": "(a)", "documented_sig": "()", "issue": "i", "form": 1}]}, "r") == []
    section2 = _flow(_slice(_read(COVERAGE), "### 2. Analyze Source Code", "### 2b."))
    assert ("A check with `alternatives` (the other forms the skill documents for the name) is compared with each of "
            "them too, as `{signatureRulesFile}` says, each mismatch naming its form as `form`.") in section2
    section2b = _flow(_slice(_read(COVERAGE), "### 2b. Resolve the Denominator", "### 2c."))
    assert ("(for a name documented in several forms, each gap's title ends `(form {n} of {m})` and its Issue names "
            "that form)") in section2b
    scan = _flow(_slice(_read(COVERAGE_TIERS), "## Fallback Per-File Scan", "coverage-check.md §2b scores"))
    assert ("`plan` without `--surface` writes the map as `documentedSignatures`, and each name's other documented "
            "forms as `documentedAlternatives`:") in scan
    assert ("(under `{skill-root}`). It gets the `documentedAlternatives` map too, whose forms it compares as that "
            "file says.") in scan


def test_a_bound_form_is_compared_with_its_own_declaration_alone():
    """#918 (oms-cognee run_pipeline): every form of a name was compared with the declarations its entry points
    export, so the lightweight runner's correct forms were Critical against the orchestrator of the same name. The
    inventory gives each form its place, `at`, and `plan` binds a form whose own citations there name one
    declaration of the name to it: the rules file, which every judge reads, compares a bound form with that
    declaration alone and reports its mismatch there, §2 tells its judge where its own citations are read, and §2b
    says `score` records it there. The contract states the place, and its example, which validates, gives one to
    each entry with a form."""
    reading = _section("Reading a form")
    assert ("With `candidates`, a form matches when it matches any candidate, and its mismatch is reported at the "
            "closest candidate. A form the check binds (`bound`: its own citations name one declaration of the "
            "name) is compared with its bound declaration alone, and its mismatch is reported there, at that "
            "declaration's file and line, whatever the check's location and candidates.") in reading
    coverage = _read(COVERAGE)
    bound = _paragraph(coverage, "A check's `bound` lists each form")
    assert "of its `surface.json` `otherDeclarations`" in bound
    assert ("Its own citations are the `[AST:]` and `[SRC:]` citations `{validateInventoryScript}` reads at the "
            "inventory's `at`: on that line, after it unless it is a table row, and around its fenced block, as its "
            "`form_citations` says.") in bound
    # The full reading rule lives with the code that applies it, validate-inventory.py's docstring.
    rule = " ".join(_read(TEST_SKILL / "scripts" / "validate-inventory.py").split())
    assert ("`form_citations` gives the citations of the form an `at` places, on its line; on the next non-blank "
            "line, unless that line writes the name (it is another place of the name) or, inside a fenced block, is "
            "a comment (it heads the next declaration), and never after a table row outside a fenced block, whose "
            "own citations are in its cells (the next row documents another export); for a line inside a fenced "
            "block, on the comment lines just above it in the block; and, when the block holds no other place the "
            "inventory gives the name, on the block's first non-blank line when it is a comment and on the first "
            "non-blank line after its closing fence unless that line writes the name.") in rule
    assert ("A citation names a declaration when it cites the declaration's file at a line or in an `L` range that "
            "holds its line or a later one before the next declaration the surface records in its file; one with no "
            "line names every declaration in its file.") in bound
    assert bound.endswith("Compare a bound form with its bound declaration alone, read in full at its `file` and "
                          "`line` as above, whatever the check's `candidates`, and report its mismatch there, `file` "
                          "and `line` on the mismatch object."), bound
    section2b = _flow(_slice(coverage, "### 2b.", "### 2c."))
    assert ("A bound form's mismatch is recorded at its bound declaration, a judge that names another file listed "
            "in `warnings`; a bound declaration joins no name, set or count.") in section2b
    contract_text = _read(REFS / "inventory-contract.md")
    contract = _paragraph(contract_text, "The contract `validate-inventory.py` checks")
    assert ("An entry whose `params` or `usage_signature` the signature check compares (a list, a non-blank "
            "string, or a function's `params`, `\"\"` included), except a `method`, gives that place as `at`, "
            "`\"<path>:<line>\"`: its file as the package names it (`SKILL.md`, or a file `references` lists) and "
            "the line its form starts on, the table row, the heading, the prose line or, in a fenced block, the "
            "line the declaration or call starts on (a `def` or `class` line, not a decorator above it), never a "
            "fence.") in contract
    assert "a form that writes only a `return_type` gives no `at`" in contract
    assert ("when they name exactly one, at its line or below it, before the next declaration the surface records "
            "in its file (otherwise as it compares any form). For a name declared more than once, a place that writes "
            "two of its forms that differ (a row that documents one declaration's form and quotes another's as a "
            "contrast) gives none of them a citation, so each is bound only by its other places") in contract
    assert ("A missing or bad `at` (malformed, in another file, on a line that does not write the name, or not the "
            "place `inventory-floor.json` gives that form's `signature`) leaves its form unbound in the same way, and "
            "the validator lists it in its `warnings` instead of refusing the inventory.") in contract
    assert "has that form as its entry, with that place as its `at`, whatever its kind" in contract
    spec = importlib.util.spec_from_file_location("validate_inventory_contract_example",
                                                  TEST_SKILL / "scripts" / "validate-inventory.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    example = re.search(r"```json\n(.*?)\n```", contract_text, re.S).group(1)
    result = validator.validate_inventory(example)
    assert result["valid"] is True, result["violations"]
    entries = json.loads(example)["exports"]
    assert all("at" in e for e in entries if validator.compared_form(e)), entries


def test_a_component_whose_props_live_outside_the_source_is_checked_only_as_a_component():
    """#837: `const Tabs = TabsPrimitive.Root` aliases another package's component, whose props type the judge cannot
    read in the source tree: its props are left uncompared, and only that it is a component is checked."""
    components = _section("Components")
    assert ("A prop the form writes must exist on `P`, own or inherited. A component whose props type lives in a "
            "package outside the source tree (`const Tabs = TabsPrimitive.Root`) has its props left uncompared: only "
            "that it is a component is checked.") in components


def test_a_const_annotated_with_a_function_type_declares_that_type_s_parameters():
    """#928: storybook's builder-vite declares `export const start: ViteBuilder['start'] = async ({ startTime, ...
    }) =>`, and no rule said whether a form is compared with the arrow's destructuring or with the one parameter the
    type names, so `start(args: {...})` was a name difference for one judge and a match for another. The annotation
    wins: the const takes the type's parameters and the arrow's destructuring is that same parameter, so a form may
    write it either way (its types are still compared), and a destructuring that names some of the type's
    properties, in the arrow or in the form, reads as no narrower type. Difference tags keep a destructured property
    part of a type: such a form matches, so no tag applies."""
    reading = _section("Reading a form")
    declares = ("A const annotated with a function type declares that type's parameters: "
                "`export const build: ViteBuilder['build'] = async ({ options }) => ...` takes the one parameter "
                "`ViteBuilder['build']` names, and the arrow's destructuring is that same parameter.")
    narrower = ("A form may name it as the type does or destructure it as the arrow does, and a destructuring that "
                "names only some of the type's properties, in the arrow or in the form, does not read as a narrower "
                "type.")
    assert declares in reading
    assert narrower in reading
    assert reading.index("The source's declaration decides") < reading.index(declares) < reading.index(narrower) \
        < reading.index("In the split-body cross-check"), "after the declaration decides, before the split-body check"
    assert "a destructured property is part of a type)" in _section("Difference tags")


def test_a_declaration_typed_only_outside_the_source_tree_counts_as_matching():
    """#925: 67 of storybook's 181 signature checks were declarations whose parameter list is written only in another
    package's types: storybook/test's `fireEvent` and its siblings, destructured from a value cast to
    `typeof domTestingLibrary`, and `spyOn`, typed `typeof vitestSpyOn` (a #928 form whose type lives outside). A
    judge cannot read that list in the source tree, so, as with a component whose props type lives there (#837), its
    parameters, their optionality and its return are left uncompared and it counts as matching. The rule says
    "outside the source tree", as Components does, so a type from the tree's own packages (`ViteBuilder`) stays
    compared."""
    reading = _section("Reading a form")
    outside = ("A declaration whose parameter list is written only in a package outside the source tree (a binding "
               "destructured from a value cast to `typeof domTestingLibrary`, or "
               "`const spyOn: typeof vitestSpyOn = (...args) => ...`) has its parameters, their optionality and its "
               "return left uncompared and counts as matching, as a component whose props type lives there does "
               "(Components).")
    assert outside in reading
    assert reading.index("The source's declaration decides") < reading.index(outside) < reading.index(
        "In the split-body cross-check"), "after the declaration decides, before the split-body check"
    # the last sentence of #928's paragraph, so #928 names the list before this rule leaves it uncompared
    paragraph = _paragraph(_read(RULES), "A const annotated with a function type declares that type's parameters")
    assert paragraph.endswith(outside), paragraph
    assert "another package" not in paragraph, "the scope is the source tree, not the export's own package"
    # the component sentence it mirrors stays whole
    assert ("A component whose props type lives in a package outside the source tree (`const Tabs = "
            "TabsPrimitive.Root`) has its props left uncompared: only that it is a component is checked."
            ) in _section("Components")


def test_a_positional_caller_and_a_python_keyword_caller_are_read_as_they_call():
    """A left-out optional parameter before a written one shifts a positional caller, so it is a mismatch; Python's
    variadic names are never compared, and parameters after `*` are compared by name, not order."""
    reading = _section("Reading a form")
    assert ("In a language without keyword arguments (TS/JS, Go, Rust, Java, C, C++), leaving out an optional "
            "parameter that comes before one the form writes shifts the caller's positions: that is a mismatch, not "
            "`omitted-optional` (`slice(str, end?)` against `(str, start?, end?)`).") in reading
    assert ("The names of Python's `*args` and `**kwargs` are never compared (`**kwargs` against `**options` is no "
            "difference), and the parameters after `*` or `*args` are compared by name, not order.") in reading
    assert "A positional-only `/` or keyword-only `*` marker the form leaves out is not compared" in reading


def test_a_call_to_a_class_is_compared_with_its_constructor():
    """#968: no rule said what a call to a class, an instance or a class alias is compared with, that a leading `self`
    takes no argument, or what a callee's `*args` and `**kwargs` accept. Read as the call rule is written,
    `Mem0Source("x")` bound `"x"` to `self` and `Task(fn, max_chunk_size=512)` passed a keyword no parameter names, so
    a correct call could be a Critical mismatch that blocks the hard gate; oms-cognee's report (three such calls) and
    oms-cocoindex's (`fn = _FunctionDecorator()` called through `__call__`'s overloads, `Symbol = core.Symbol` over a
    stub's `__new__(cls, name: str)`) passed them on the judge's reading alone. A call to a class is compared with its
    constructor's parameters after `self`, a dataclass's, attrs class's, pydantic model's or NamedTuple's generated
    fields included (a pydantic model's keyword-only); an instance's with its `__call__`; an alias's with its class's.
    The receiver rule is score-signatures.py's, so both name one receiver set: the source's leading receiver is never
    compared and the form's own is dropped only when the source leads with one. A callee's `*args` or `**kwargs`
    takes any extra argument, and a constructor written only outside the source tree counts as matching (#925).
    #1023: a class in another language was compared with "the constructor it declares", one of them, and only
    Python's, TS/JS's and Go's variadics took extra arguments, so `new Command("ls", "-l", "-a")` against
    `Command(String name, String... args)` passed arguments that did not exist. Such a class is compared with every
    constructor it declares, as one overload set, and Java's, C#'s, Kotlin's, C's and C++'s variadics are named."""
    reading = _section("Reading a form")
    opening = "A call to a class is compared with its constructor"
    constructor = ("A call to a class is compared with its constructor: in Python, the parameters after `self` of the "
                   "`__init__` the class declares, else those after `cls` of its `__new__`, else its nearest base's in "
                   "method resolution order (`object`'s takes none); a dataclass, attrs class, pydantic model or "
                   "NamedTuple that declares no `__init__` with the fields it generates, in declaration order, base "
                   "fields first, a default marking a field optional, a field kept out of the constructor "
                   "(`init=False`, a `ClassVar`) none of them, and a pydantic model's keyword-only; a TS/JS class with "
                   "its `constructor(...)`, else its nearest base's; a class in another language with the constructors "
                   "it declares, read as Overload sets says.")
    form = "Any other form that documents a class is compared with that same constructor."
    component = "A component is compared by its props (Components), not its constructor."
    instance = ("A call to an instance is compared with its class's `__call__` (`fn = _FunctionDecorator()`, then "
                "`fn(memo=True)`), its overloads read as Overload sets says, and a name bound to a class with that "
                "class's constructor (`Symbol = core.Symbol`, whose stub declares `__new__(cls, name: str)`).")
    receivers = "(`self`, `cls`, `&self`, `&'a self`, `&mut self`, `mut self`, `this: T`)"
    receiver = (f"A leading receiver the source writes {receivers} is never compared, and a form's own leading "
                "receiver is dropped only when the source leads with one too: `(self, a)` against `def f(a)` is a "
                "mismatch.")
    variadics = ("An argument past the parameters a declaration takes by position exists when it takes `*args`, a "
                 "TS/JS `...args`, Go's `...T`, Java's `T...`, C#'s `params T[]`, Kotlin's `vararg` or a C or C++ "
                 "`...`, and a keyword no parameter names exists when it takes `**kwargs`, so "
                 "`Task(fn, max_chunk_size=512)` matches `__init__(self, executable, *args, **kwargs)`; a pass-through "
                 "`__init__(self, *args, **kwargs)` is compared as written, so any call matches it.")
    outside = ("A class whose constructor is written only in a package outside the source tree (one that declares none "
               "over another package's base, such as `Exception`, or that a metaclass from there builds) has its "
               "parameters left uncompared and counts as matching, as such a declaration does (below); a class "
               "with generated fields is still compared with them, and one whose bases declare no constructor "
               "before `object` takes none.")
    for sentence in (constructor, form, component, instance, receiver, variadics, outside):
        assert sentence in reading, sentence
    assert reading.index("The names of Python's") < reading.index(opening) \
        < reading.index("The source's declaration decides"), "after the variadic names, before the declaration decides"
    # right after the paragraph on Python's variadic names, and one copy
    rules = _read(RULES)
    paragraphs = rules.split("\n\n")
    [names] = [i for i, p in enumerate(paragraphs) if p.startswith("The names of Python's `*args` and `**kwargs`")]
    assert paragraphs[names + 1].startswith(opening), paragraphs[names + 1]
    assert rules.count("A call to a class is compared") == 1, "one copy"
    # the outside-tree rule it points at ("below") stays below it
    assert reading.index(outside) < reading.index(
        "A declaration whose parameter list is written only in a package outside the source tree")
    # the rules and the script name one receiver set
    assert receivers in _paragraph(rules, opening)
    assert receivers in _flow(_read(SCORE_SIGNATURES)), "score-signatures.py's docstring names the same receivers"


def test_the_split_body_cross_check_compares_what_both_forms_write():
    """#843: in the split-body cross-check no source says which parameter is required, so a parameter's
    optionality is compared only when both forms state it, and what a form may leave out is this file's rule:
    coverage-check.md §1 no longer allows only a form labelled partial to leave a member out, and a call or a list
    of bare names may too, except where that shifts a caller's positions. An ellipsis claims nothing, as everywhere,
    and each side's partial label is read from its own file, since the export's `signature_form` is one.
    #927: two same-named declarations are two exports, so forms attributed to different declarations of one name
    (their own citations at `at`, or §2's `bound`) are never compared with each other there.
    #1045 (oms-cognee 1.6.2): the receiver rule spoke only of a source, so `execute(args, kwargs,
    next_batch_size=None)` against `execute(self, args, kwargs, next_batch_size=None)` was a High mismatch for a reader
    taking `self` as a parameter the defaulting form leaves out, and no mismatch for one dropping it by analogy. Neither
    form is the source, so each form's own leading receiver is dropped before the two are compared."""
    reading = _section("Reading a form")
    assert ("In the split-body cross-check both forms are documented: each is read by these rules, a type, return "
            "type or type arguments one of them leaves out are not compared, and a parameter's optionality is "
            "compared only when both forms state it.") in reading
    # an ellipsis claims nothing, required members included, as Reading a form's ellipsis line says
    assert "An ellipsis claims nothing about the members it stands for, required ones included." in reading
    assert "`(...)` and `(tasks, data, dataset, ...)` leave out no parameter." in reading
    # each side's partial label is its own file's; the positional shift stays a mismatch
    assert ("A call, a list of bare names or a form its own file labels partial (each side's label is read from that "
            "side's file, not from the export's one `signature_form`) may leave out a parameter the other form does "
            "not state as required, unless leaving it out shifts a caller's positions (a language without keyword "
            "arguments, as above); any other form claims its list is complete, so leaving out a parameter the other "
            "writes is a mismatch (inventory-contract.md's examples).") in reading
    assert ("In a language without keyword arguments (TS/JS, Go, Rust, Java, C, C++), leaving out an optional "
            "parameter that comes before one the form writes shifts the caller's positions") in reading
    assert "A call, an ellipsis," not in reading
    assert "coverage-check.md §1 says which parameters a form may leave out" not in reading
    # the examples the paragraph cites: a typed form leaving out a parameter the other form writes
    contract = _read(REFS / "inventory-contract.md")
    assert ("SKILL.md shows (date: Date) => string, references/api-reference.md (date: Date, format?: string) => "
            "string") in contract
    assert ("references/api-reference.md shows (tasks: Task[], data: unknown) => void, references/pipelines.md "
            "(tasks: Task[]) => void") in contract
    # §1 defers to this file for what a form may leave out, and states no omission rule of its own
    section1 = _flow(_slice(_read(COVERAGE), "### 1. Extract Documented Exports", "#### 1a."))
    assert ("descriptions that contradict (brief against detailed is fine). That file alone says what a form may "
            "leave out.") in section1
    assert "labels partial that leaves out only optional members" not in section1
    assert "(name, type, order, optionality)" not in section1
    # #927: forms attributed to two declarations of one name are two exports, never compared with each other
    rules = _read(RULES)
    paragraph = _paragraph(rules, "In the split-body cross-check both forms are documented")
    homonyms = ("Forms of one name attributed to different declarations of it are two exports, never compared with "
                "each other in the split-body cross-check: their own citations, read at each form's inventory `at` as "
                "inventory-contract.md says, name two declarations, or coverage-check.md §2's `bound` binds them to "
                "two, a declaration being one of the name's surface records or one `surface.json` lists in "
                "`otherDeclarations` (each judge reads the signals it has).")
    each = ("Each is compared only with the forms attributed to its own declaration, a form attributed to neither is "
            "a mismatch only when it contradicts the forms of both, and §2 holds a bound form to its bound "
            "declaration alone and an unbound one to the check's candidates (below).")
    # the section 1 reader has no surface: its default is to compare as before unless the skill shows two things
    reader = ("A judge without the surface (coverage-check.md §1's reader) counts two declarations only when the two "
              "forms' own citations name two different files and the skill presents the forms as different things "
              "(another owner, module or import path); a citation of a re-export (a package `__init__` or index file "
              "the skill shows passing the name on) names no declaration, and when unsure the forms are compared as "
              "before.")
    for sentence in (homonyms, reader, each):
        assert sentence in paragraph, sentence
    assert paragraph.index(homonyms) < paragraph.index(reader) < paragraph.index(each), "the reader's default sits between"
    assert paragraph.endswith(each), "the #927 rule ends the split-body paragraph"
    assert rules.count("attributed to different declarations") == 1, "one copy"
    # #1017: forms one file writes as an overload set are read as one set, by the rule under Overload sets
    pointer = "The forms one file writes for one name as an overload set are read as one set, as Overload sets says."
    first = "and a parameter's optionality is compared only when both forms state it."
    assert pointer in paragraph, pointer
    assert paragraph.index(first) < paragraph.index(pointer) < paragraph.index(homonyms), "after the first sentence"
    # #1045: a receiver only one form writes is never compared, after the first sentence, by every receiver
    # score-signatures.py drops, Rust's `&mut self` and `mut self` too, since no script reads these two forms;
    # against the source, `(self, a)` and `def f(a)` still differ
    listed = ("self", "cls", "&self", "&'a self", "&mut self", "mut self", "this: T")
    receivers = "(" + ", ".join(f"`{r}`" for r in listed) + ")"
    receiver = (f"A leading receiver {receivers} that one form writes and the other leaves out is never compared: "
                "neither form is the source, so each form's own leading receiver is dropped before the two are "
                "compared.")
    assert receiver in paragraph, receiver
    assert paragraph.index(first) < paragraph.index(receiver) < paragraph.index(pointer), "after the first sentence"
    assert rules.count("neither form is the source") == 1, "one copy"
    source_rule = _paragraph(rules, "A call to a class is compared with its constructor")
    assert receivers in source_rule, "the source rule lists every receiver RECEIVER_RE drops, as the split-body rule does"
    spec = importlib.util.spec_from_file_location("score_signatures", SCORE_SIGNATURES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for item, extension in zip(listed, (".py", ".py", ".rs", ".rs", ".rs", ".rs", ".ts")):
        assert module._parameters(f"({item}, value)", extension)[0]["receiver"], f"{item} is a receiver the script drops"
    assert "`(self, a)` against `def f(a)` is a mismatch." in reading, "the source's rule is unchanged"
    # the `bound` rule it points at ("below") stays below it
    flowed = _flow(rules)
    assert flowed.index(each) < flowed.index("A form the check binds (`bound`")


def test_a_type_naming_some_of_the_other_form_s_union_agrees_in_the_split_body_cross_check():
    """#1015: Annotations' union rule speaks of the source's union, and the split-body cross-check has no source, so
    one judge carried it over and found a table's `list[str]` agreeing with a fenced `list[str] | None = None`
    while another raised a High `split-body-mismatch` on the same pair. The split-body paragraph now carries the
    rule over, in either direction, for a parameter type only: a return type keeps Annotations' own rule."""
    rules = _read(RULES)
    paragraph = _paragraph(rules, "In the split-body cross-check both forms are documented")
    union = ("A parameter type one form writes that names some of the members of the other form's union agrees with it, "
             "in either direction, as it does against the source (Annotations): `node_name: list[str]` matches "
             "`node_name: list[str] | None = None`.")
    assert union in paragraph
    # among the paragraph's type readings: after its first sentence, before the ellipsis and omission rules
    first = "and a parameter's optionality is compared only when both forms state it."
    ellipsis = "An ellipsis claims nothing about the members it stands for, required ones included."
    assert paragraph.index(first) < paragraph.index(union) < paragraph.index(ellipsis), "#1015: beside the type rule"
    assert _flow(rules).count("names some of the members of the other form's union") == 1, "one copy"
    # the Annotations rule it points at, which keeps the source's union and the return type's own rule
    annotations = _section("Annotations")
    assert ("A documented parameter type that names some of the members of the source's union is no mismatch, since a "
            "caller passing it makes a valid call") in annotations
    assert "a documented return type must cover every member the source can return." in annotations


def test_each_export_s_form_is_read_alone():
    """#843: GAP-105 read a bare-name list's parameters as required because every other row of its Key API Summary
    table wrote defaults. A form is one export's: the rows of other exports state nothing about it."""
    reading = _section("Reading a form")
    assert ("Each export's form is read alone: what the rows of other exports write, in the same table or file, "
            "states nothing about it, so `(action, sink, tracking_record, child_invalidation)` matches "
            "`child_invalidation: X | None = None` even when every other row of its table writes its defaults."
            ) in reading
    # the example holds by the file's own rules: a list of bare names states no optionality
    assert ("A list of bare names, with no type, default or `?` (`connect(host, port)`, `({ themes, defaultTheme })`), "
            "names parameters without claiming the list is complete") in reading


def test_a_component_is_compared_by_its_props():
    """#827: every spelling of a component's type is one contract, its props; its return type and wrapper are never
    compared. A function with several positional parameters is a function, whatever it returns."""
    components = _section("Components")
    # what counts as a component, in each framework
    assert ("A component is an export the source declares as one: a function that takes one props object (plus a "
            "`ref`, for `forwardRef`) and returns JSX, an element or `null`") in components
    for kind in ("a class component", "a `defineComponent` result or a Svelte component",
                 "React, Preact, Solid, Vue or Svelte",
                 "a Vue component's `props` option or `defineProps` type or runtime object",
                 "a Svelte component's props"):
        assert kind in components, kind
    assert ("A function with several positional parameters is a function, whatever it returns "
            "(`flexRender(Comp, props)`, `createPortal(children, container)`).") in components
    for form in ("`FC<P>`", "`React.FC<P>`", "`FunctionComponent<P>`", "`ComponentType<P>`",
                 "`(props: P) => JSX.Element`"):
        assert form in components, form
    assert "a `memo`, `forwardRef` or other higher-order component result over `P`" in components
    assert "are one contract, the props `P`: a component's return type and its wrapper are never compared" \
        in components


def test_a_component_s_own_props_are_written_in_its_package():
    """#827: own props are the members its package writes or computes; a type from another package's members are
    inherited. An inherited optional prop may be left out, a required one (a `Link`'s `href`) may not be left out of
    a full form. `| null | undefined`, an undeclared props type name and usage-example values are not compared."""
    components = _section("Components")
    assert ("A component's own props are the members written in its package: its interface or object type, object "
            "literals intersected into it, and members computed from its own code "
            "(`VariantProps<typeof buttonVariants>`).") in components
    assert ('Members of a type from another package (`React.ComponentProps<"button">`, `HTMLAttributes<...>`, '
            "`ComponentProps<typeof Link>`) are inherited, as are the `ref` a `forwardRef` result takes and the "
            "optional `children` of `PropsWithChildren<P>`. A prop the form writes must exist on `P`, own or "
            "inherited.") in components
    assert ("So is a required own prop it leaves out, and a required inherited one (a `Link`'s `href`) left out of a "
            "full form. An optional own prop a typed props list or a table leaves out is an `omitted-optional` "
            "difference; one a list of bare names or a usage leaves out, and an optional inherited prop, is no "
            "difference.") in components
    assert "`| null` and `| undefined` on an optional prop are no difference (`VariantProps` adds both)." in components
    assert ("A props type name the form writes that the source does not declare (`Button(props: ButtonProps)` against "
            "a source with no `ButtonProps`) is not compared by name, only the props the form lists.") in components
    assert "Values in a usage example (`variant=\"subtle\"`) are not compared." in components


def test_a_rest_element_in_a_props_form_stands_for_the_props_it_does_not_name():
    """#932: oh-my-skills' native-components.md copies the source's destructuring,
    `({ className, variant = "default", ...props }: NativeButtonProps)`, and no rule said what its rest stands for,
    so a judge could read the props it does not name (`asChild?`) as left out of a typed list. The rest stands for
    every prop of `P` the form does not name, own or inherited, required ones included, and its own name is no prop.
    A rule of Components alone: Reading a form gains no rest rule, and a typed props list with no rest still leaves
    out an optional own prop as `omitted-optional`."""
    components = _section("Components")
    rest = ("A rest element in a component's destructured props form "
            "(`({ className, variant = \"default\", ...props }: NativeButtonProps)`) stands for every prop of `P` the "
            "form does not name, own or inherited, required ones included, so the form leaves none of them out, and "
            "the rest's own name is not compared as a prop.")
    assert rest in components
    assert _flow(_read(RULES)).count(rest) == 1, "one copy, in Components"
    assert components.index("and an optional inherited prop, is no difference.") < components.index(rest) \
        < components.index("`| null` and `| undefined` on an optional prop"), "right after the props a form leaves out"
    assert not re.search(r"\brest (?:element|member|parameter)s?\b", _section("Reading a form"), re.I), \
        "not generalized to other destructured parameters"
    assert ("An optional own prop a typed props list or a table leaves out is an `omitted-optional` "
            "difference") in components


def test_a_props_list_states_optionality_only_with_a_mark():
    """#827: a props list that states no optionality has none compared; in an object type literal one `?` makes the
    unmarked members required; a table states it by a Required column, a `?` or a Default value, never by its Type
    column, and an empty Default cell (Create Skill's own props table) states nothing; a destructuring default marks
    only its own member."""
    components = _section("Components")
    assert ("A props list states optionality as Reading a form says: `({ of, meta, story })`, or a list of names, "
            "states none, and in an object type literal (`{ of?: X; meta: M }`) that states it for any member, each "
            "member written with no mark claims to be required.") in components
    assert ("A table states optionality by a Required column, a `?` on a prop's name or a Default cell that gives a "
            "value; its Type column states types, never optionality.") in components
    assert ("A Default cell with a value marks only its own row optional and an empty one states nothing, so Create "
            "Skill's `| Prop | Type | Default | Description |` table never reads a prop with an empty Default cell "
            "as required.") in components
    assert "| Prop | Type | Default | Description |" in _read(COMPILE_ASSEMBLY), "the table the rule names"
    assert ("A destructuring default (`({ of, meta = {} })`) likewise marks only its own member, and the others state "
            "no optionality.") in components


def test_an_annotation_a_form_leaves_out_is_not_compared():
    """#835: an untyped parameter is not compared on type, an unstated return (in any language's position), a
    source-unannotated type and type arguments the form leaves out are not compared, and a documented return type
    the body demonstrably returns, against a declared annotation that contradicts it, is a mismatch tagged
    `annotation-contradicted` with the body line as `evidence_line`, which `score` reports without blocking. Only a
    return type: a parameter's annotation always decides."""
    annotations = _section("Annotations")
    assert ("A parameter written without a type is not compared on type: its name and order are, and its optionality "
            "as Reading a form says.") in annotations
    assert "Bare `*args` matches `*args: P.args`, and `**kwargs` matches `**kwargs: P.kwargs`." in annotations
    # #1003: a parameter's or prop's type written as a description gets the reading a return's has, so a Type cell
    # such as `Pydantic BaseModel` or `Union (many)` has one reading for every judge. It closes the first bullet,
    # apart from the return bullets, as the parameter-side sentence there.
    described = ("A parameter's or prop's type written as a description is read as a return type is (below): a "
                 "description followed by a type (`Pydantic BaseModel`) states that type, and text that names no type "
                 "(`Union (many)`) states none, so it is not compared, as an unwritten type is not.")
    [untyped] = [line for line in _read(RULES).splitlines() if line.startswith("- A parameter written without a type")]
    assert untyped.endswith("`**kwargs: P.kwargs`. " + described), "#1003: on the parameter bullet"
    assert "A return type the form does not state is not compared." in annotations
    assert ("or in its language's own position (Go's result list after the parameters, the type before the name in C, "
            "C++ and Java)") in annotations
    assert "A blank `return_type` (`\"\"`) states none" in annotations
    assert "an entry with `params: \"\"` and no return type matches `def f() -> None`" in annotations
    assert "A type the source leaves unannotated, on a parameter or a return, is not compared" in annotations
    assert ("except that a TS/JS parameter with a literal default has that literal's type: `pageSize = 20` is a "
            "`number`, so `pageSize?: string` is a mismatch. An unannotated return stays uncompared.") in annotations
    assert "Type arguments the form leaves out are not compared: `dict` matches `dict[str, Any]`" in annotations
    assert "Type arguments it writes are" in annotations
    assert ("A documented return type that matches what the body demonstrably returns, where the declared annotation "
            "says otherwise, is a mismatch tagged `annotation-contradicted` with `evidence_line`, the body line that "
            "returns that value: the skill documents what callers get, and the contradiction is the source's, which "
            "`score` reports without blocking.") in annotations
    assert ("Against a declaration annotated `-> Callable[[], Callable[[], None]]` whose line 19 returns the function, "
            "`-> Callable[[], None]` is tagged with `evidence_line` 19.") in annotations
    assert ("Tag it only when you can name that line: a body line that starts with `return`, or the declaration line "
            "itself when its own expression body follows its parameters there (`=> expr`, a Python "
            "`def ...: return x`).") in annotations
    assert ("A Rust tail expression, a Kotlin or Scala expression body and a Ruby implicit return have no such line and "
            "cannot be tagged: there, as when you cannot name the line, the declaration decides.") in annotations
    # the judges with no `difference` field read the same case as agreeing
    assert ("A judge whose result has no `difference` field (coherence-check.md §4's `signature_match`, "
            "coverage-check.md §5b's split-body Source) reads such a documented return type, at a line it can name, as "
            "agreeing with the source: a match for `signature_match`, and for §5b a form that agrees with the "
            "source.") in annotations
    assert "It holds for a return type alone, never a parameter's annotation." in annotations
    assert "is no mismatch, even when the declared annotation says otherwise" not in annotations, "#835 follow-up"


def test_a_return_written_as_value_names_states_no_return_type():
    """#930: oms-cognee writes `→ (nodes, edges)` for a function declared `-> tuple[list[Node], list[EdgeData]]`, and
    the return-type bullet counts any text after an arrow as a stated return. Names of values state no return type,
    so no return is compared (the parameters still are). A type name written alone, lowercase ones included, stays a
    type, and "rather than types" keeps a parenthesized list of type names (`(str, int)`) a stated return. #957: a
    bracketed or braced list of value names states none too, while a single name, a list that writes a type among
    its names and a description followed by a type each state one, as score-signatures.py's _states_return reads
    them; the sentence is appended, so both earlier ones stay verbatim."""
    annotations = _section("Annotations")
    values = ("- A return written as names of values rather than types, a parenthesized list of names such as "
              "`→ (nodes, edges)` (after the arrow or in `return_type`), states no return type, so no return is "
              "compared.")
    assert values in annotations
    assert ("A type name written alone stays a type, lowercase ones included: `-> list` and `→ str` state one."
            ) in annotations
    assert ("A type name written alone stays a type, lowercase ones included: `-> list` and `→ str` state one. "
            "A bracketed or braced list of value names, such as `→ [state, setState]` or `=> { data, error }`, "
            "likewise states none, while a single name (`→ result`), a list that writes a type among its names "
            "(`(nodes: list[Node], edges)`) and a description followed by a type (`HTML str`) each state one."
            ) in annotations, "#957: appended to the bullet"
    assert annotations.index("A return type the form does not state is not compared.") < annotations.index(values) \
        < annotations.index("A type the source leaves unannotated"), "after the return-type bullet"
    lines = _read(RULES).splitlines()
    [i] = [n for n, line in enumerate(lines) if line.startswith("- A return type the form does not state")]
    assert lines[i + 1].startswith("- A return written as names of values rather than types,"), "the next bullet"
    assert lines[i + 1].endswith("and a description followed by a type (`HTML str`) each state one."), "#957: last"


def test_a_return_that_names_alternative_types_after_its_type_states_their_union():
    """#1042: oms-cognee writes `RememberResult (DryRunEstimate with dry_run=True, ...)` for a function declared
    `-> Union["RememberResult", "DryRunEstimate", "PresortReport", dict]`. Read as `RememberResult` with a described
    parenthetical, as `HTML str` is read, it leaves out three members, an untagged Critical; read as the union of
    every type it names, it is a match. Annotations now gives the union reading, the conditions naming no type, and
    keeps a type a parenthetical names for another reason a description. score-signatures.py's _states_return
    already reads such a return as a stated one, and the script never compares return types, so only prose changes.
    A bullet of its own, so the value-names bullet still ends on its `HTML str` clause. It names both bounds, so an
    alternative the source never returns is a mismatch for every judge, not only for one that reads past "(below)"."""
    annotations = _section("Annotations")
    alternatives = ("- A return written as a type followed by other types it names as alternatives, in a parenthetical "
                    "or a list, each with an optional condition (`RememberResult (DryRunEstimate with dry_run=True, "
                    "PresortReport with dry_run=\"presort\", or dict)`, `GraphSnapshot for \"pydantic\", ExportResult "
                    "for \"cogx\"`), states the union of every type it names, and the words that name no type "
                    "(`with dry_run=True`, `for \"pydantic\"`) state nothing: it matches the source's union when it "
                    "names every member and no other: a member it leaves out is a mismatch (below), and so is one the "
                    "source never returns. A type a parenthetical "
                    "names other than as an alternative (`Response (see Request)`) is description, so only the type "
                    "before it is stated.")
    assert alternatives in annotations
    lines = _read(RULES).splitlines()
    values = "- A return written as names of values rather than types,"
    [i] = [n for n, line in enumerate(lines) if line.startswith(values)]
    assert lines[i + 1] == alternatives, "#1042: right after the value-names bullet"
    assert lines[i + 2].startswith("- A type the source leaves unannotated"), "and before the unannotated-type bullet"
    assert _flow(_read(RULES)).count("other types it names as alternatives") == 1, "one copy"
    # the rule its "(below)" points at, and the description reading it sets apart, both stay
    assert "a documented return type must cover every member the source can return." in annotations
    assert "a description followed by a type (`HTML str`) each state one." in annotations


def test_two_spellings_of_one_type_are_no_mismatch():
    spellings = _section("Equivalent spellings")
    for spelling in ("`Optional[X]`, `Union[X, None]` and `X | None`", "`Union[A, B]` and `A | B`",
                     "a union's members in any order (`None | X`, `B | A`)",
                     "`typing`'s `List`, `Dict`, `Tuple`, `Set`, `FrozenSet` and `Type` and the builtins `list`, "
                     "`dict`, `tuple`, `set`, `frozenset` and `type`",
                     "`Array<T>` and `T[]`", "`ReadonlyArray<T>` and `readonly T[]`",
                     "A quoted forward reference and the name it quotes",
                     "A type alias the source declares and the type it names",
                     "`typing.`, `collections.abc.` or `React.` prefix",
                     "Type variables renamed consistently: `(a: T) -> T` against `(a: U) -> U`, but not "
                     "`(a: T, b: U)` against `(a: U, b: U)`",
                     "Type arguments the source leaves out are not compared either: the form's `dict[str, Any]` "
                     "matches the source's bare `dict`"):
        assert spelling in spellings, spelling
    # #999: the three prefixes are examples of a path, not the full set, so a type written through a module the
    # source imports names the declaration its bare name does, as score-signatures.py's _final_name reads it.
    assert ("- A name with or without the module or namespace path it is written through, such as a `typing.`, "
            "`collections.abc.` or `React.` prefix or a module or namespace the source imports under its own name or "
            "an alias, when both name one declaration: `React.ReactNode` and `ReactNode`; `environment.Environment`, "
            "after `from . import environment`, and `Environment`; `z.ZodType` and `ZodType`. Two declarations that "
            "only share a name stay two types.") in spellings
    assert "with or without its `typing.`" not in spellings, "#999: no closed list of three prefixes"
    # #1050: a type name has one reading for every judge. A form's name is the type the skill documents or the package
    # exports, a name the source writes is read in its file's scope, so a local alias that reuses the exported name is
    # read through the type it names; `source_sig` writes that type by its exported name, so the gap's remediation
    # never asks for the local spelling the form already copies. A local declaration that is no alias (a local
    # `interface Options` beside an exported `Options`) keeps its own name, and `source_sig` rewrites only an alias
    # that reuses a documented or exported name, so neither asks the form for the text it already writes.
    assert ("- A type alias the source declares and the type it names. A type name a form writes means the type the "
            "skill documents or the package exports under that name, and the source file's own declaration of it only "
            "when there is none, or when the file declares the name other than as an alias (a local "
            "`interface Options`). A name the source writes means the declaration in its file's scope, a local alias "
            "read through the type it names and an import alias as the type it imports: the documented "
            "`ThemesParameters['themes']` matches a return of the local "
            "`type ThemesParameters = Parameters['themes']`, declared over "
            "`import type { ThemesParameters as Parameters }`. When such an alias reuses a name the skill documents or "
            "the package exports, a mismatch's `source_sig` writes it as the type "
            "it names, by its exported name when it has one (`ThemesParameters['themes']`, not the local "
            "`ThemesParameters`), so the form the gap asks for matches the source.") in spellings
    # #1003: a Markdown Type cell cannot hold a bare `|`, so Create Skill's tables write a union with `/`; it spells
    # the union, as score-signatures.py's _type_key reads it, while a `/` alone in a parameter list stays the
    # positional-only marker Reading a form names.
    slash = ("- `A / B` written between types in one parameter's or prop's type and `A | B`, as a table's Type cell, "
             "where a bare `|` cannot stand, writes a union: `str / list[str] / None` and `str | list[str] | None`. "
             "A `/` written alone in a parameter list stays the positional-only marker (Reading a form).")
    assert slash in spellings
    lines = _read(RULES).splitlines()
    [i] = [n for n, line in enumerate(lines) if line.startswith("- `Optional[X]`, `Union[X, None]` and `X | None`")]
    assert lines[i + 1] == slash, "#1003: beside the other union spellings"
    assert "A positional-only `/` or keyword-only `*` marker" in _section("Reading a form"), "the marker it names"


def test_every_difference_the_script_accepts_is_defined_in_the_rules_file_alone():
    """The `difference` tags moved out of coverage-check.md §2 into the rules file, so the fallback scan's subagents
    get them too; §2 keeps one pointer, scoring-rules.md's Low and Info rows point at the file for what each tag
    means, and score-signatures.py's comment points at it. `annotation-contradicted` (#835 follow-up) is the one
    tag added since, defined there too."""
    spec = importlib.util.spec_from_file_location("score_signatures", SCORE_SIGNATURES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DIFFERENCES == ("parameter-name", "omitted-optional", "annotation-contradicted")
    tags = _section("Difference tags")
    for value in module.DIFFERENCES:
        assert f"`{value}`" in tags, value
    assert TAG_DEFINITION in tags
    assert ("`parameter-name` (only parameter names differ: types, order, optionality and return type equal; a "
            "destructured property is part of a type)") in tags
    # #1025: a form that writes no parameter list claims nothing about parameters, so its mismatch is tagged too
    assert ("`annotation-contradicted` (only the return type differs: `documented_sig` and `source_sig` write the same "
            "parameters, or the form writes no parameter list, and the body returns the documented type at the "
            "mismatch's `evidence_line`, as Annotations says)") in tags
    # #1023: every language's variadic parameter is optional, as a TS/JS rest parameter is
    assert ("A parameter or field with a default or a `?`, or a variadic parameter (a TS/JS rest parameter, a Python "
            "`*args` or `**kwargs`, Go's `...T`, Java's `T...`, C#'s `params T[]`, Kotlin's `vararg` or a C or C++ "
            "`...`), is optional") in tags
    assert "a Rust `Option<T>` field a struct literal still requires is not" in tags
    assert ("A renamed component prop is never `parameter-name`: callers set props by name, so it is a mismatch with "
            "no tag.") in tags
    assert "Tag it in any language and form: `score` (coverage-check.md §2b) checks the facts." in tags
    assert "The example in coverage-check.md §2, tagged `omitted-optional`, stays Critical against a full form." in tags
    for path in (COVERAGE, COVERAGE_TIERS, SCORING):
        assert TAG_DEFINITION not in _read(path), path.name
    section2 = _flow(_slice(_read(COVERAGE), "### 2. Analyze Source Code", "### 2b."))
    assert "Tag a mismatch's `difference` as `{signatureRulesFile}` says: `score` (§2b) checks the facts." in section2
    assert "references/signature-comparison-rules.md (Difference tags)" in _flow(_read(SCORE_SIGNATURES))
    rows = _read(SCORING).splitlines()
    [low] = [line for line in rows if line.startswith("| Low      | `signature-mismatch`")]
    [info] = [line for line in rows if line.startswith("| Info     | `observation`")]
    assert "tags `parameter-name` (defined in signature-comparison-rules.md, Difference tags)" in low
    assert "tags `omitted-optional` (defined in signature-comparison-rules.md, Difference tags)" in info
    assert "tags `annotation-contradicted` (defined in signature-comparison-rules.md, Difference tags)" in info
    assert "only parameter names differ" not in low
    assert "leaves out only members the source marks optional" not in info


def test_a_contradicted_return_annotation_is_a_visible_note_that_never_blocks():
    """#835 follow-up: a match on the body's return made no output, so the source's contradiction reached no report
    and a lenient judge could pass a real mismatch. The judge reports it tagged with `evidence_line`, §2b's `score`
    is given the local source to check that line, and scoring-rules.md's Info row names the observation, which asks
    for no change to the skill."""
    text = _read(COVERAGE)
    section2 = _flow(_slice(text, "### 2. Analyze Source Code", "### 2b."))
    assert ("One tagged `annotation-contradicted` also gives `evidence_line`, the body line that returns the documented "
            "type.") in section2
    section2b = _flow(_slice(text, "### 2b. Resolve the Denominator", "### 2c."))
    assert ("and `--source-root` whenever the source is local (State 1, Forge tier or above), under a drift override "
            "too, since the judges read that tree:") in section2b
    assert ("an Info `observation` titled `Annotation contradicted: {name}` (no change to the skill: report the "
            "annotation upstream) for an `annotation-contradicted` one whose facts check (a documented return type, "
            # #1025: as scoring-rules.md's Info row and the rules' Difference tags read it
            "the same parameters on both sides or a form with no parameter list, and an `evidence_line` between the "
            "declaration and the next one, whose line returns in the `--source-root` file)") in section2b
    [info] = [line for line in _read(SCORING).splitlines() if line.startswith("| Info     | `observation`")]
    # #1025: or its form writes no parameter list
    assert ("whose documented signature states a return type and writes the source's parameters (or its form writes "
            "no parameter list), and whose "
            "`evidence_line`, the body line that returns the documented type, comes after the declaration and before "
            "the next one and, with the local source, starts with `return` (or is a one-line declaration's own "
            "expression body)") in info
    assert ("`Annotation contradicted: {name}`, at the declaration, counted as matching in Signature Accuracy, with no "
            "change to the skill (the annotation is reported upstream)") in info
    [critical] = [line for line in _read(SCORING).splitlines() if line.startswith("| Critical | `signature-mismatch`")]
    assert "in any way but those the Low `signature-mismatch` row and the Info `observation` row grade" in critical


def test_every_coverage_check_judge_names_the_rules_file():
    """§1's split-body cross-check and §2's judge are given the rules file's absolute path (a subagent runs from the
    project root); the main-thread compare and §5b's split-body Source load it. The frontmatter binds it; the
    overload rule is no longer in the step, and the `candidates` sentence stays."""
    assert _frontmatter(COVERAGE)["signatureRulesFile"] == "references/signature-comparison-rules.md"
    assert (TEST_SKILL / _frontmatter(COVERAGE)["signatureRulesFile"]).resolve() == RULES.resolve()
    text = _read(COVERAGE)
    cross_check = _paragraph(text, "Delegate the reading of the skill under test to a subagent")
    assert ("and two reference files with each other only when the body does not settle them (it does not "
            "document the export, or agrees with both), by the rules of `{signatureRulesFile}`, whose absolute path "
            "(under `{skill-root}`) it is given: parameters, the return type, and descriptions that contradict"
            ) in cross_check
    judge = _paragraph(text, "For each `files[]` entry, delegate one subagent")
    assert f"delegate one subagent with its checks and {ABSOLUTE_PATH}." in judge
    assert "compares it with the check's `documented` signature by the rules of that file" in judge
    assert "(params: name, type, order, optionality; and the return type)" not in text
    main_thread = _paragraph(text, "Save each response to `{run_dir}/signatures-<n>.txt`")
    assert ("Without subagents, load `{signatureRulesFile}`, compare in the main thread by its rules and save the "
            "same JSON.") in main_thread
    # §5b's split-body Source loads it from the branch section §5b loads (#841)
    assert "follow its **Split-Body Sources** section" in _paragraph(text, "**A split-body mismatch's Source**")
    split_body = _flow(_read(REFS / "coverage-check-branches.md").split("\n## Split-Body Sources\n", 1)[1])
    assert ("load `{signatureRulesFile}` and set the two forms its `issue` gives against the export's declaration at "
            "the `file` and `line` `surface.json` gives, by its rules, when that one declaration decides") in split_body
    assert OVERLOAD_RULE not in text
    candidates = _paragraph(text, "A check with `candidates` reads each")
    assert candidates.endswith("and its `difference` tagged against it."), candidates


def test_a_partial_label_in_a_table_header_labels_each_row():
    """#827: oms-storybook's `Props (simplified)` column header labels every row of its table partial."""
    contract = _paragraph(_read(REFS / "inventory-contract.md"), "The contract `validate-inventory.py` checks")
    assert ("not rest or variadic syntax; a label in a table's column header, such as `Props (simplified)`, labels "
            "each of its rows) carries `signature_form: \"partial\"`") in contract


def test_an_empty_parenthesized_mention_is_no_form():
    """#887: oms-storybook's Purpose cell reads `instrument()` wraps functions. A reader that took the mention for an
    empty call recorded `params: ""`, and `instrument`, which takes a required parameter, got a Critical
    `signature-mismatch`. A name written with empty parentheses in running text or a description cell is a mention:
    the contract leaves `params` and `usage_signature` out for it, and the rules say, in a paragraph of their own
    before the forms that claim no complete parameter list, that it claims nothing. Both define a description cell by
    its column's role, the places #888 proposes to script, and keep a heading or an export table's first cell that
    writes `name()` a form, so a correct zero-argument signature there is still compared."""
    mention = "A name written with empty parentheses in running text or a description cell is a mention, not a form"
    cell = ("A description cell is any table cell but an export table's first cell and a cell whose column writes the "
            "call or signature, by its role (Signature, Props, Params, Parameters, Arguments, Usage, Syntax, Example "
            "and the like); a heading or an export table's first cell that writes `name()` is a form")
    contract_text = _read(REFS / "inventory-contract.md")
    contract = _paragraph(contract_text, "The contract `validate-inventory.py` checks")
    assert (f"{mention}: its entry leaves `params` and `usage_signature` out (a cell reading \"`instrument()` wraps "
            f"functions\"). {cell}, recorded as written.") in contract
    assert contract.index("and leaves a key out when the skill documents nothing for it.") < contract.index(
        mention), "after the rule for a key the skill documents nothing for"
    rules = _read(RULES)
    paragraph = _paragraph(rules, mention)
    assert paragraph == f"{mention}: it claims nothing and is not compared. {cell}, an empty call (below).", paragraph
    reading = _section("Reading a form")
    assert reading.index(paragraph) < reading.index("Three kinds of form do not claim a complete parameter list:"), \
        "before the forms that claim no complete parameter list, not inside the call-example rule"
    for text in (contract_text, rules):
        assert "\u2014" not in text and "\u2013" not in text, "no em or en dash"


def test_the_fallback_scan_compares_by_the_rules_file():
    """The fallback per-file scan's subagents get the rules file's absolute path, overload sets and `difference` tags
    included, in place of the overload rule alone; the tiers file reads coverage-check.md's bindings."""
    tiers = _read(COVERAGE_TIERS)
    assert "coverage-check.md's frontmatter bindings" in _flow(tiers), "so `{signatureRulesFile}` resolves here"
    scan = _flow(_slice(tiers, "## Fallback Per-File Scan", "coverage-check.md §2b scores"))
    assert f"gets that map with the file and {ABSOLUTE_PATH}." in scan
    assert "by the rules of that file (overload sets and `difference` tags included)" in scan
    assert "(params, return type)" not in scan
    assert OVERLOAD_RULE not in tiers and "Tell it the overload rule" not in tiers


def test_the_critical_row_reads_each_form_by_the_rules_file():
    [row] = [line for line in _read(SCORING).splitlines() if line.startswith("| Critical | `signature-mismatch`")]
    assert "Wrong signature" in row
    assert ("as signature-comparison-rules.md reads each form (a component by its props; an annotation either side "
            "leaves out is not compared)") in row


def test_create_skill_names_the_props_interface_as_a_component_contract():
    """#827: Create Skill no longer teaches the form Test Skill compared as Critical against `FC<P>`."""
    text = _flow(_read(COMPONENT_EXTRACTION))
    assert "always `(props: XProps) => JSX.Element`" not in text
    assert ("Do not document the function signature in detail (a component's contract is its Props interface: Test "
            "Skill compares the props a form writes, never its return type or wrapper).") in text


def test_the_coherence_judge_reads_the_rules_file():
    """A stack skill's `signature_match` is a High `inaccurate-reference` gap that blocks the gate, so the coherence
    check's contextual reference judge compares signatures by the rules file too: coherence-check.md binds it as
    coverage-check.md does, gives the judge its absolute path, and the main thread loads it in the judge's place."""
    assert _frontmatter(COHERENCE)["signatureRulesFile"] == _frontmatter(COVERAGE)["signatureRulesFile"]
    section4 = _slice(_read(COHERENCE), "### 4. Contextual Mode: Validate Each Reference", "### 5.")
    flowed = _flow(section4)
    assert f"to a subagent given {ABSOLUTE_PATH}, that, for each one:" in flowed
    assert ("- Signatures: a documented signature matches its declaration by the rules of `{signatureRulesFile}` "
            "(`signature_match`)") in flowed
    assert "If subagent unavailable, load `{signatureRulesFile}`, validate each reference in main thread by it" \
        in flowed
    [row] = [line for line in _read(SCORING).splitlines() if line.startswith("| High     | `inaccurate-reference`")]
    assert "a signature that differs" in row
