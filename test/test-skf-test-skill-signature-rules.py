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
  may leave out, and each export's form read alone (#843);
- a partial label in a table's column header labelling each of its rows;
- a usage form read as what it writes, in the call-example rule, and a
  name documented in several forms compared with each form by its own
  rules, a mismatch reported for each form that does not match, on §2's
  path and the fallback scan's alike (#826); a component whose props live
  outside the source tree left uncompared (#837);
- Create Skill naming a component's Props interface as its contract, not
  `(props: XProps) => JSX.Element`.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import importlib.util
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
    is not compared."""
    reading = _section("Reading a form")
    assert "A form claims only what it writes" in reading
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


def test_a_call_an_ellipsis_and_bare_names_claim_no_complete_list():
    """A replay of real skills' signature checks: call examples, an ellipsis and a list of bare names do not claim a
    complete parameter list, so an optional parameter they leave out is no difference, while a typed form still
    claims its list is complete (#834's `(date: Date) => string` stays `omitted-optional`)."""
    reading = _section("Reading a form")
    assert "Three kinds of form do not claim a complete parameter list:" in reading
    assert ("It is compared as a call: each argument it passes must exist, by position or by name, and every required "
            "parameter must be passed; an optional parameter it leaves out is no difference.") in reading
    assert "An empty call `X()` is one too, so it matches a source whose parameters are all optional." in reading
    assert ("An ellipsis (`...` or `\u2026`) in a list stands for members it does not show and claims nothing about "
            "them") in reading
    assert "`(...)` and `(tasks, data, dataset, ...)` leave out no parameter." in reading
    assert ("A list of bare names, with no type, default or `?` (`connect(host, port)`, `({ themes, defaultTheme })`), "
            "names parameters without claiming the list is complete") in reading
    assert ("A form that writes a type or a default for a parameter (`(date: Date) => string`) claims its list is "
            "complete: an optional parameter it leaves out is an `omitted-optional` difference") in reading
    assert "one it adds where the source has none is no difference: calls that follow the form are valid." in reading
    props = _section("Components")
    assert ("An optional own prop a typed props list or a table leaves out is an `omitted-optional` difference; one a "
            "list of bare names or a usage leaves out, and an optional inherited prop, is no difference.") in props


def test_a_caller_following_a_narrower_form_makes_a_valid_call():
    """A documented parameter type naming some of a union's members, a union of callables written as one callable
    returning a union, and a form taking the unions of an overload set's parameter types are no mismatch."""
    annotations = _section("Annotations")
    assert ("A documented parameter type that names some of the members of the source's union is no mismatch, since a "
            "caller passing it makes a valid call") in annotations
    assert "a documented return type must cover every member the source can return." in annotations
    spellings = _section("Equivalent spellings")
    assert "`Callable[[A], X] | Callable[[A], Y]` and `(a: A) -> X | Y`" in spellings
    overloads = _section("Overload sets")
    assert "the unions of the overloads' types" in overloads


def test_a_usage_form_is_read_as_what_it_writes():
    """#826, deferred from #862: an entry whose only form is its `usage_signature` had no rule saying how it is read.
    The call-example rule, its one copy, reads a component usage as a list of bare names of the props it sets and a
    call as its arguments in order; a spread, children or `...args` can pass a required member; each usage of a list
    is a form of its own."""
    reading = _section("Reading a form")
    assert ("A component usage `<X a={x} b=\"y\" />` reads as a list of bare names of the props it sets, and a call "
            "`f(a, b)` as its arguments in order, each the parameter at its position (or, written `name=value`, the one "
            "it names).") in reading
    assert ("A JSX spread (`{...props}`) or children can pass a required prop, and a call's `...args` a required "
            "parameter, so neither leaves one out.") in reading
    assert ("An entry's `usage_signature` written as a usage is read this way, and each usage in a list of usages is "
            "compared as a form of its own, under its entry's `form` index.") in reading
    assert reading.count("`usage_signature`") == 1, "one copy of the usage rule"
    # the bullet it extends, and the bare-names rule it reads by
    call = _paragraph(_read(RULES), "- A call or usage example passes values")
    assert "A component usage `<X a={x} b=\"y\" />` reads as a list of bare names" in call
    assert "A list of bare names, with no type, default or `?`" in reading


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


def test_a_component_whose_props_live_outside_the_source_is_checked_only_as_a_component():
    """#837: `const Tabs = TabsPrimitive.Root` aliases another package's component, whose props type the judge cannot
    read in the source tree: its props are left uncompared, and only that it is a component is checked."""
    components = _section("Components")
    assert ("A prop the form writes must exist on `P`, own or inherited. A component whose props type lives in a "
            "package outside the source tree (`const Tabs = TabsPrimitive.Root`) has its props left uncompared: only "
            "that it is a component is checked.") in components


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


def test_the_split_body_cross_check_compares_what_both_forms_write():
    """#843: in the split-body cross-check no source says which parameter is required, so a parameter's
    optionality is compared only when both forms state it, and what a form may leave out is this file's rule:
    coverage-check.md §1 no longer allows only a form labelled partial to leave a member out, and a call or a list
    of bare names may too, except where that shifts a caller's positions. An ellipsis claims nothing, as everywhere,
    and each side's partial label is read from its own file, since the export's `signature_form` is one."""
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
    assert ("`annotation-contradicted` (only the return type differs: `documented_sig` and `source_sig` write the same "
            "parameters, and the body returns the documented type at the mismatch's `evidence_line`, as Annotations "
            "says)") in tags
    assert ("A parameter or field with a default or a `?`, a TS/JS rest parameter, or a Python `*args` or "
            "`**kwargs`, is optional") in tags
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
            "the same parameters on both sides, and an `evidence_line` between the declaration and the next one, whose "
            "line returns in the `--source-root` file)") in section2b
    [info] = [line for line in _read(SCORING).splitlines() if line.startswith("| Info     | `observation`")]
    assert ("whose documented signature states a return type and writes the source's parameters, and whose "
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
