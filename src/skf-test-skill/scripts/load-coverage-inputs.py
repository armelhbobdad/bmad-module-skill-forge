#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF test-skill coverage inputs: the counts, name sets and candidates coverage-check reads.

coverage-check.md decides whether a bookkeeping variant is a real export,
and makes the judgments the denominator clause needs where no file holds
them (--pattern-reference-intent, and --curated-subset and --barrel where
the extraction does not say); the clause, everything it counts, folds or
unions on the way runs here, so no count is made by hand. Four subcommands, each
reading files and writing one JSON object:

  census    docs-only detection. Counts the citations SKILL.md and each .md
            file directly in references/ write, by form: `[EXT:` against
            the local forms `[AST:`, `[SRC:` and a stack's `[from skill:`
            (`[QMD:` and `[DOC:` are counted and decide nothing). A skill is
            docs-only when it cites `[EXT:` and no local form.

  floor     the documented inventory's floor (#790): every name SKILL.md
            and each .md file directly in references/ (a subfolder is not
            read) write in a fixed form, which validate-inventory.py --floor
            refuses an inventory for leaving out. No kind is mapped, and a
            signature is read only where the place writes it in a fixed
            form (Signatures, below). A name is a plain
            identifier (`[A-Za-z_$][\\w$]*`) once a leading `new ` and
            everything from the first `(`, `<` or `[` are cut, so
            `Meta<T>`, `App[P, R]`, `fetch(url): Promise<T>` and
            `new Client(opts)` give `Meta`, `App`, `fetch` and `Client`;
            an empty `[]` at the cut (a TS array type, `Foo[]`) gives
            none. A dotted or `::` name gives none, so a
            namespace-style skill such as zod (`z.object`) gets no table
            floor. The forms, read outside the frontmatter and HTML
            comments (a table row or heading inside fenced code gives none):
              table-row    each inline code span in the first cell of a
                           table row (cells split on an unescaped `|`)
                           whose header row's first cell is, in any case,
                           singular or plural and bare or wrapped in `**`
                           or `__`, Export, Symbol, Function, Class,
                           Interface, Type, Hook, Component, Helper,
                           Constant, Enum, API or Query, or is parts split
                           at `/`, each read the same way, whose first is
                           one of those words and each other one of them
                           or Props, Params or Parameters
                           (`Component / Props`, `Function/Type`; #1004).
                           A Name, Method, Prop, Param, Import or Subpath
                           table gives none, and so does a `Prop / Type`
                           or `Symbol / keyword` one. The
                           row's Kind cell, as written, is the name's
                           `kindLabel`: the skill's own label, never mapped
                           to a kind (the first in origin order when two
                           rows label the name differently; null with no
                           Kind column)
              heading      an ATX heading whose whole text is one code
                           span, as in ``### `Meta<T>` `` (a heading with
                           other words, ``## Testing with `mount` ``, gives
                           none)
              declaration  a column-0 public declaration in a fenced block
                           whose first non-blank line is a comment (`//`,
                           `#`, `/* */`, `--`, `<!-- -->` or `;`) holding an
                           `[AST:` or `[SRC:` citation, or naming a path one
                           such citation of the skill names (its `:12`,
                           `:L12` or `:12-30` left out). A citation counts
                           only with its `:L<n>` (`[AST:src/a.ts:L12]`, not
                           `[AST:src/a.ts]`), and one on the line above the
                           fence heads nothing. Comments and strings are
                           masked first. TS/JS (not Svelte, whose `export
                           let` is a prop): `export` then `function`,
                           `const`, `let`, `var`, `class`, `interface`,
                           `type` or `enum` (`declare`, `abstract` and
                           `async` may come between), or `export default
                           function` or `class` with a name; Python: `def`,
                           `async def` or `class`, a name not starting with
                           `_`; Rust: a `pub` (not `pub(crate)`) `fn`,
                           `struct`, `enum`, `trait`, `type`, `const` or
                           `static`, and a `macro_rules!` under
                           `#[macro_export]`; Go: `func`, `type`, `var` or
                           `const` with a capitalized name, each name of a
                           `type (`, `var (` or `const (` group too. A
                           block in another language, an untagged one or a
                           data block (json, yaml, text...) gives none.
            Signatures (#888): an origin whose place writes the name's
            signature in a fixed form that is surely complete also carries
            it as `signature`, which validate-inventory.py --floor refuses
            an inventory for changing; any other place pins nothing, since
            a wrong pin would be forced into the inventory. A signature is
            two strings, each one's whitespace runs read as one space,
            {"params", "return_type"} for a complete form or a Props cell
            (below) and {"usage_signature", "return_type"} for a usage form
            (and `signature_form` "partial" under a header's partial
            label or for an ellipsis item, below). `params` is the text
            inside the parameter group
            (score-signatures.py's _group: the first pair of parentheses
            outside every bracket pair and string), and `return_type` the
            type written after it (score-signatures.py's _signature_parts),
            "" for none. A form that writes neither (`f()`,
            `useQuery<T>()`) gives none, so an empty call claims no form. A
            span (a table cell's or a heading's) is complete when it is the
            name (or no name, as a Signature cell's `(x: A) => B`), its type
            parameters, one parameter group, then nothing or a return
            separator (`->`, `=>`, `→` or `:`) and the return, with nothing
            else: `useQuery(key).data`, `f(a) / f(a, b)`, a trailing
            comment, a `;` or `,` outside the return's brackets, an
            unclosed bracket, `Meta<T>` (no group) and `new Client(opts)`
            give none. A span that is no complete form is a usage form when
            it writes, before the name's complete form, at least one of, in
            this order, an assignment (`x =`, `const { data } =`), `await`,
            `new` and a receiver or module path (`cognee.`): its
            `usage_signature` is the span through the parameter group, its
            `return_type` the return after it (`await run(a, b):
            Promise<R>` gives `await run(a, b)` and `Promise<R>`); or when
            it is one self-closing JSX element of the name that sets a prop
            (`<Canvas of={X} />`), its `return_type` "". An empty call
            (`new Client()`) and a prop-less element (`<Canvas />`) give
            none. By form:
              table-row    a row whose first cell names one name (a row
                           naming several gives none), each cell's `\\|`
                           read as `|`: the leading code span of its
                           Signature or Signatures cell, a header split
                           at `/` with a part that is one included
                           (`Signature / Purpose`, `Props / Signature`;
                           #1030), else, when that
                           span writes no parameter group (`Typed<X>`),
                           the one span of its first cell that gives the
                           name (another export's span there, as in
                           `fetch` (same as `http.request(opts)`), gives
                           nothing), each a complete form, else a usage
                           form. A Signature span with a group that is
                           neither (`client.get(k).data`, `f(a) //
                           overload`) gives none, so a shorter first-cell
                           call never stands in for it, and so does such a
                           first-cell span (`useData(key).data`). Only
                           then a Props, Params or Parameters cell, when
                           the whole cell is one code span (trailing prose
                           or several spans leave it the reader's): a
                           complete form (`(a, b)` gives `a, b`), else a
                           usage form, else none when it writes a
                           parameter group or opens a JSX element, or when
                           it only names a type or writes a placeholder
                           (`ButtonProps`, `ComponentProps<typeof Link>`,
                           `None`, `-`), else the span whole
                           as `params` with `return_type` ""
                           (`TitleProps = { of?: Of }`, `key: string`),
                           kept as written. A Signature, Props, Params
                           or Parameters header may give one partial
                           label in parentheses after its word, any case:
                           `Signature (simplified)`, `Props (simplified)`,
                           `(partial)`, `(key parameters)` or
                           `(key params)`. The form its cell gives then
                           also carries `signature_form` "partial", so the
                           label is the script's, not the reader's; the
                           first-cell form never does, as the label heads
                           that column only; a compound Signature header
                           reads its Signature part's label
                           (`Signature (simplified) / Purpose`). Any other
                           text after the word (`Signature (TypeScript)`),
                           a compound header with no Signature part
                           (`Props / Usage`, `Props / Type`) and an
                           Arguments, Args, Usage, Syntax or Example
                           header leave the column unread: its form stays
                           the reader's.
              heading      its code span, a complete form, else a usage
                           form (`new Client(opts)`: a name is cut as
                           above, so no other usage names one there)
              declaration  a function's (`function`, `def`, `fn` or Go's
                           `func` before its name; a `const` holding an
                           arrow gives none): its lines as one, as
                           skf-extract-public-api.py's
                           _declaration_signature joins them (a parameter
                           list split over lines joined, line comments
                           left out), the body cut off first, at the first
                           `:` (Python) or `{`, `;` or ` where ` (any other
                           language) outside every bracket pair and string
                           after the parameter group, a `{` directly after
                           a TS return `:` opening the return type
                           (`(): { a: T } {` returns `{ a: T }`). None for
                           one with anything but type parameters between
                           its name and the group (a Go `func(...)`
                           return), one whose opener follows, or whose
                           uncut text ends with, `interface`, `struct`,
                           `is`, `keyof`, `|`, `&`, `?`, `:`, `\\`, `=>` or
                           `->` (the opener or the line end is inside the
                           return type: Go's `interface{}`, a TS `asserts
                           x is {...}`, `() => {...}` or conditional type,
                           `): Promise<A> |`), or one whose brackets or
                           strings do not all close.
            Whatever its form, a signature whose parameter group (its
            `params`, or the group its `usage_signature` writes) holds an
            ellipsis item, a member that is `...` or `…` alone as
            score-signatures.py's _parameter reads one (a rest `...args`,
            a `*args` and a default `x=...` are none), also carries
            `signature_form` "partial" (#1029): the contract counts that
            `...` as the skill's partial label, so it is the script's too,
            and validate-inventory.py --floor refuses the label an entry
            adds where the signature gives none. A form written only in
            prose is never read: it stays the
            reader's. Each origin keeps the first signature its place
            writes.
            Output: {"files": [...], "names": [{"name", "kindLabel",
            "origins": [{"file", "line", "form", "signature"?}]}],
            "summary": {"names", "byForm"}}, names sorted, each one's
            origins in file order then line, `signature` only on an origin
            that has one, `byForm` counting the origins of each form; the
            same skill gives the same bytes.

  metadata  the metadata.json and provenance-map counts. Cluster A
            (`stats.exports_public_api`, the `exports[]` length) and Cluster
            B (`stats.exports_documented`, the provenance entry names, the
            `confidence_distribution`) under the keys
            check-metadata-coherence.py reads; the provenance named exports
            (`::` impl-block methods left out); the inflation signature
            (`stats.exports_documented` equals `stats.effective_denominator`,
            or, for a map with a named entry and no `::` entry, its distinct
            entry names do: the stored count counts each name once, the map
            holds a name passed on from two files twice)
            with the declared names verify-declared-numerator.py looks up
            (the `exports[]` names, else the provenance named exports); and,
            for a stack, its composition surface: the distinct provenance
            named exports when the map has entries, else each library and
            each integration pair (`{a} + {b}`, as the stack's Library Pair
            Integrations heading writes it), as reconcile-coverage.py's
            stack branch takes them.

  surface   the enumerated source surface, from every input given (their
            union):
              --extraction  skf-extract-public-api.py --mode full output:
                            the names in entry_point_diff.public, each
                            other in-scope definition of one
                            (entry_point_diff.other_definitions, #830) a
                            record of its own at its file, a
                            namespace with a `members` list given as its
                            members (the names its module passes on, each
                            at its file, once with a public name of the
                            same name and file), less the outside_scope
                            names (defined in a file out of scope), which
                            `excluded.outsideScope` lists with their file,
                            line and entry point and, for a namespace's
                            member, the namespace (`namespace`) and, when
                            the brief scopes the file out, why: the
                            scope.exclude glob that matches it
                            (`excludeGlob`) or no scope.include glob
                            covering it
                            (`outsideInclude`); exports[] only gives each name's
                            kind, line and signature line (a local export
                            list's item: its binding's declaration_line and
                            declaration_signature_line, when the extractor
                            records them), looked up by the
                            name its defining file gives it (an aliased
                            re-export's `local`) and that file.
                            extraction_gaps are listed with their file and
                            line in `extractionGaps`, which
                            reconcile-coverage.py's render lists (#1048), and
                            the runner's warnings join `warnings`. A Python
                            top __init__.py inside the folder of another top
                            that exports a public name (a sub-package
                            behind a folder with no __init__.py) is no
                            barrel, unless scope.include or tier_a_include
                            lists its file: its names leave `all`, `root`
                            and the umbrella ratio and are listed in
                            `excluded.nestedEntries`, but keep their records
                            (so the scope.include and tier_a_include sets)
                            and their outside_scope and extraction_gaps
                            rows. When the runner lists an
                            include glob that matches no file
                            (scope.unmatched_include: a brief older than the
                            source), each outside_scope name a root entry
                            point exports is restored, with the file and
                            line of its outside_scope row, when no include,
                            exclude or declined scope-expansion amendment
                            (latest action skipped or demoted-include, from
                            --brief) matches its file; no recipe reads its
                            file, so its kind is the one --provenance gives
                            the name at that file (PROVENANCE_KINDS), else
                            none, as is the kind of a name exports[] gives
                            none at its file, such as an extraction_gaps
                            name (#1020). A tier_a_include glob
                            the runner lists as matching no file
                            (scope.unmatched_tier_a_include, [] when the key
                            is absent) counts no name. An extraction the
                            per-file scan replaces (extraction.fallback.needed)
                            gives no name and no set: only its scope, its
                            stale globs and its `extraction` object, so the
                            fallback scan passes it beside its results.
              --quick       skf-extract-public-api.py --mode quick output,
                            each name at its defined_in (the file that
                            defines it), else at its source_file
              --per-file    a subagent's per-file result (exports_found and
                            types_found), schema-checked as
                            score-signatures.py checks it
              --fallback-scan
                            the --per-file results are the fallback
                            per-file scan's, each at the file that defines
                            its names (a Quick-tier or State 4 result is at
                            its entry file): as with an extraction, no
                            tier_a_include set is no tier A list
              --name        a name read by eye whose file is not known
              --provenance  the provenance entries' named exports (State 2),
                            and the kinds of restored names and of names
                            exports[] gives no kind at their file
              --metadata    the metadata.json exports[] names (States 2, 3)
            A surface read from the source (--extraction, --quick or
            --per-file) takes no name from --provenance and --metadata:
            they are the baselines of the candidates and guards, and the
            map gives a kind only to a restored name or one exports[] gives
            none at its file, such as an extraction gap. Without
            one, with --provenance and --metadata both, `state2` gives the
            provenance count, the metadata count and their union count,
            which compute-score.py turns into the State 2 divergence. --fold
            folds the bookkeeping variants among the provenance and metadata
            names to their base name (`X_def`, `X_exact`, `a11y_X`, and
            `<prefix>X` for each --fold-prefix when `X` is itself a name)
            unless --keep names the variant as a real export, and
            `canonical` gives the provenance map's fold summary; a map
            whose distinct named exports number
            `stats.effective_denominator` (--metadata) is already canonical
            and is not folded (`canonical.skipped`), and `residual` is the
            canonical count less that stored count. --brief gives the
            skill brief's scope, scope type, language and scope-expansion
            amendments; an extraction's recorded scope wins over its scope.

Name sets (surface `sets`, each sorted): `all` (the union above, less a
nested Python top's names);
`scope.include` and `tier_a_include` when the scope has those globs and a
record names a file: the names with a file (any of the name's records: an
extraction's definition file, each other in-scope definition's included,
the quick output's defined_in, else its source_file, a per-file result's
file, a provenance entry's source_file) that matches a glob of the list
and no scope.exclude glob,
and for `tier_a_include` a scope.include glob too when the scope has one,
so a name with no file is in `all` only and a restored name is in no
tier_a_include set (a tier_a_include glob an extraction lists as matching
no file is left out of the list, and so is one whose folder or file
differs from every scope.include glob's before any `*` or `?`, such as
`gen/**` beside `src/**`, and so is one a scope.exclude glob covers
segment by segment, such as `src/gen/**` or `src/gen/extra.ts` beside an
exclude of `src/gen/**`; a list that counts no name, each glob left out
or matching only excluded files, files scope.include leaves out or files
no record names, gives no tier_a_include set); and, from an
extraction only, `subpaths` (the names a non-root `exports` map subpath
without `*` reaches) and `root` (the names the root entry points reach),
each through the entry point of any of the name's definitions.
reconcile-coverage.py and score-signatures.py --surface-set pick one.

Other declarations (surface `otherDeclarations`, #918): for each name with
a record (a nested Python top's included), each declaration of the name
the extraction's exports[] holds (under the name, or under the name an
aliased record's defining file gives it, `local`, as the record lookup
reads it; a re-export row declares nothing) in a file none of the name's
records names and no scope.exclude glob matches, as {name, kind, file,
line, signatureLine}, its file with forward slashes and no leading `./`,
its line and signature line taken as a record's are; sorted, each
declaration once however its path is written, and [] with none; null
with no extraction or with one the per-file scan replaces, which looks for
none, so null means never looked for (#1026). Such a declaration is a
same-named function no entry point exports, as cognee's lightweight
`run_pipeline`, which a lazy `__getattr__` passes on beside the
orchestrator a namespace exports. They are no records: they join no set,
no count and no guard. score-signatures.py plan reads them, binding a
documented form to one when the form's own citations name it and no other
declaration of the name, and so does test-skill's Split-Body Sources
(coverage-check-branches.md), which lets one declaration settle a
split-body pair only on a list.

Candidates and guards (with an extraction, --brief or --metadata): each
set's count, the metadata `stats.effective_denominator` (--metadata), and
the extractor's own effective_denominator and its basis; for the
Denominator annotations, `tierAIncludeFiles` and `scopeIncludeFiles` (the
distinct files the set's names sit at: the files that define them when
each name sits at its defining file) and `subpathEntries` (an extraction's
distinct in-scope non-root, non-wildcard subpaths, each package's subpath
once however many files it names), each null when its set is absent.
Both guards run
only on a surface read from the source. The deflation guard compares a
re-derived set with `stats.effective_denominator` and names it in `basis`.
It is the tier_a_include set (`tier_a_include`) when the clause's ladder
holds a stored count (stratified-scope, specific-modules, multi-entry), the
surface has that set and each name sits at the file that defines it (a
runner extraction, --fallback-scan, or quick output whose every name
carries its defined_in, with no --per-file or --name beside it): it fires
when the stored count differs from the set by more than DEFLATION_PCT
either way, since Create Skill stores the runner's tier A count. Otherwise
it is the scope.include set (`scope.include`, else `all` when the surface
has no scope.include set), firing above DEFLATION_PCT when there is no tier
A list (with an extraction or --fallback-scan, no tier_a_include set;
otherwise no tier_a_include glob left in the list, since a name read by eye
at Quick tier or State 4, and a quick name with no defined_in, carries its
entry file, not the file that defines it). A stored 0 is deflation, not a
denominator (`pct` null), and fires under its basis's condition when any
name is re-derived. The inflation guard compares the scope.include set
with the provenance entry count (--provenance) and fires above
INFLATION_PCT when there is no tier A list, as the scope.include basis
reads it; `guards.tierAInclude` lists the scope's
tier_a_include globs ([] when it has none) for gap-ledger.py's wording;
the umbrella ratio (an
extraction only) is the share of the root entry points' names that are
re-exports (a namespace with `members` counting as its members there
too, each a re-export, and an other in-scope definition left out), and
above UMBRELLA_RATIO the barrel is an
umbrella; the
stale-scope guard (an extraction with scope.include or tier_a_include only)
fires when the runner lists an include or tier_a_include glob that matches
no file, and lists those globs (`unmatchedInclude`,
`unmatchedTierAInclude`) and the names restored for the include globs, each
with its file and line (`restored`). Globs follow
skf-extract-public-api.py: `**` spans any number of path segments, none
included, and `*` and `?` stay inside one.

Denominator (surface `denominator`): the Source API Surface Definition's
clause (source-access-protocol.md), the branch reconcile-coverage.py takes
and the set it and score-signatures.py --surface-set read: {clause, branch,
surfaceSet, ladderStep, absentSet, rebuild, barrel, setCounted}.
`setCounted` (null off the scalar branch) says whether the scalar branch
counts its `surfaceSet` as the numerator's set: true only for a scope set
(not `all`) whose every name sits at the file that defines it, as the
deflation guard's tier A basis requires (a runner extraction, the fallback
scan, quick output whose every name carries its defined_in), read whole (an
extraction neither `incomplete` nor truncated); otherwise the scalar branch
keeps its looked-up numerator. The inputs: the scope
type (the brief's, else the extraction's, else metadata.json's
`scope_type`), metadata.json's `skill_type` and `stats.effective_denominator`,
the extraction's `arms`, the deflation guard, and:
  monorepo  --monorepo (the workspace layout skf-detect-workspaces.py
            found), or the extraction's `arms.monorepo`.
  curated   the extraction's `counts.curated_subset` (the rule Create Skill
            stores the count by), else --curated-subset (the workflow's
            judgment that a monorepo's scope.include lists a curated subset).
  barrel    (`barrel`: "barrel", "empty-barrel", "no-entry-point" or null)
            a complete extraction's `entry_points.status`; for one the
            per-file scan replaces, "no-entry-point" when it read a file in
            scope and found no entry point (`entry_points.files` empty), as
            a complete run says; a quick output's (an export is a barrel,
            none and no warning an empty one); else --barrel (`barrel`,
            `empty` or `none`, what the workflow read); else null.
  --pattern-reference-intent  the workflow's judgment that scope.notes
            flags pattern-reference intent.
The first clause that applies:
  stack             skill_type stack: branch `stack`, no set.
  pattern-reference not a monorepo, no non-empty barrel, a scope type other
                    than specific-modules, component-library, docs-only and
                    reference-app, not public-api with a multi-subpath
                    `exports` map, and either the intent flag or no entry
                    point at all with no such map: the tier_a_include set,
                    else `all` with `rebuild` `provenance-fold` on a surface
                    read from the source (build it again from the provenance
                    map alone, folded), `all` on one that is not.
  empty-barrel      an empty barrel: the scope.include set.
  stratified-scope  --monorepo and --curated-subset, not full-library.
  specific-modules  scope type specific-modules, not --monorepo.
  multi-entry       arms.multi_subpath_exports, not --monorepo, a
                    full-library or public-api scope.
  standard-barrel   any other: the `all` set.
The last three walk a ladder, `ladderStep` naming the rung taken: rung 1,
`stats.effective_denominator` when metadata.json has one above 0 (a stored
0 is no denominator), is the `scalar` branch, whose `surfaceSet` (the set score-signatures.py scores) is
tier_a_include, else scope.include, else all, unless the deflation guard
fires: then the barrel branch over tier_a_include when the ladder has that
rung (stratified-scope, multi-entry) and the surface has the set, else over
scope.include (when the inflation guard fires too, that union is itself
inflated, and both gaps ask for the brief's tier A list, never a stored
count set by hand). On an incomplete extraction, which can miss tier A
names, a tier A set below the stored count fires the guard and leaves the
scalar branch. The next rungs are sets,
each taken when the surface has it, the last taken in any case:
tier_a_include then scope.include (stratified-scope), scope.include
(specific-modules), tier_a_include then subpaths (multi-entry). A set the
surface lacks is counted as `all`, and `absentSet` names it.

Fallback verdict: `extraction.fallback.needed` is true when the extractor
found no ast-grep (`no-ast-grep`), read no file in scope, read files only
in languages it has no recipe for (`files_without_recipes` and no export),
or found files no recipe reads while the skill's language (the --brief
`language`, else the metadata.json `language`) is not one RECIPE_LANGUAGES
holds, so the per-file scan has to run instead. A run keeps its exports
whatever its status; `extraction.readByEye` lists the files to read by eye,
at any status: each file the runner could not parse or decode (a
`syntax-errors` or `not-utf8` file issue) and, on an `incomplete` run, each
file a failed call names. `extraction.unread` lists the files nobody can
read (a `missing` or `unreadable` file issue); a `no-recipes` file, such as
a stylesheet, holds nothing to read and is in neither list.

Usage:
  uv run load-coverage-inputs.py census --skill-dir <dir> [--output <file>]
  uv run load-coverage-inputs.py floor --skill-dir <dir> [--output <file>]
  uv run load-coverage-inputs.py metadata --metadata <metadata.json> \\
      [--provenance <provenance-map.json>] [--output <file>]
  uv run load-coverage-inputs.py surface [--extraction <file>] [--quick <file>]... \\
      [--per-file <file>]... [--fallback-scan] [--name <name>]... [--provenance <file>] \\
      [--metadata <file>] [--brief <skill-brief.yaml>] [--fold] [--fold-prefix <prefix>]... \\
      [--keep <name>]... [--monorepo] [--pattern-reference-intent] [--curated-subset] \\
      [--barrel barrel|empty|none] [--output <file>]

Stdout: the result. With --output the file holds it, and stdout is a
summary that gives each field under the file's key and names the file
(#1040):
  census    {"docsOnly", "localCitations", "output"}
  floor     {"summary", "output"}
  metadata  {"skillType", "inflationSignature", "stack": {"basis",
            "denominator"} or null, "output"}
  surface   {"exports": the number of records, "denominator",
            "extraction": {"readByEye", "unread", "fallback"} or null,
            "extractionGaps": the gaps, whose files and lines the step
            reads by eye, "output"}

Exit codes:
  0  the result was printed, or written to --output and its summary printed
  1  an input file is missing, unreadable or not the JSON (or the YAML
     brief) it should be, or the --skill-dir holds no SKILL.md or a skill
     file that is not UTF-8 (one line on stderr)
  2  a per-file result breaks the schema: {"valid": false, "violations":
     [...]} names each breach and nothing is written to --output; or a
     usage error (argparse)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import posixpath
import re
import sys
from pathlib import Path

DEFLATION_PCT = 25
INFLATION_PCT = 25
UMBRELLA_RATIO = 0.5
METHOD_SEPARATOR = "::"
CITATION_FORMS = {
    "EXT": "[EXT:",
    "AST": "[AST:",
    "SRC": "[SRC:",
    "from skill": "[from skill:",
    "QMD": "[QMD:",
    "DOC": "[DOC:",
}
LOCAL_FORMS = ("AST", "SRC", "from skill")
# floor: the forms a documented name takes, in the order an origin on one line sorts by.
FLOOR_FORMS = ("table-row", "heading", "declaration")
# The header words (lower case, singular or plural) of a table whose first column names exports: its first header
# cell is one, or parts split at `/` whose first is one and each other one or a FLOOR_PROPS_HEADERS word, as
# `Component / Props` is and `Prop / Type` and `Symbol / keyword` are not (_floor_table_header, #1004).
FLOOR_TABLE_HEADERS = frozenset({
    "export", "exports", "symbol", "symbols", "function", "functions", "class", "classes", "interface", "interfaces",
    "type", "types", "hook", "hooks", "component", "components", "helper", "helpers", "constant", "constants",
    "enum", "enums", "api", "apis", "query", "queries"})
# The header words (as _header_label reads them, a partial label cut) of a floor table's column that writes the row's
# signature (#888): its header is one, or has a part split at `/` that is one, as `Signature / Purpose` and
# `Props / Signature` do (_signature_column, #1030); a header with any other text after the word, such as
# `Signature (TypeScript)`, is not one, and neither is an Arguments, Args, Usage, Syntax or Example header.
FLOOR_SIGNATURE_HEADERS = frozenset({"signature", "signatures"})
# The header words (as _header_label reads them, a partial label cut) of a floor table's column that writes the row's
# props or parameters (#888): its cell is read only when it is exactly one code span, and only after the Signature
# and first-cell forms; the whole header is the word, so a `Props / Usage`, `Props / Type` or `Key params` header
# is not one (#1030: the whole-span read would pin a type alias or a constant's value there).
FLOOR_PROPS_HEADERS = frozenset({"props", "params", "parameters"})
# The partial labels (lower case, whitespace runs as one space) a header may give in parentheses after its word, as
# `Signature (simplified)` and `Props (simplified)` do (#888): each form read from that Signature, Props, Params or
# Parameters column is partial, so an optional parameter it leaves out is Info, not Critical, and the floor pins the
# label with the form, as it does for a form whose parameter group holds an ellipsis item (_ellipsis_labelled, #1029).
FLOOR_PARTIAL_LABELS = frozenset({"simplified", "partial", "key parameters", "key params"})
# What a usage form writes before its name's complete form (#888), each part optional, in this order: an assignment
# (`x =`, `a, b =`, `const { data } =`, `let [a, b] =`), `await`, `new`, and a receiver or module path (`cognee.`,
# `client.messages.`).
USAGE_PREFIX_RE = re.compile(
    r"(?:(?:(?:const|let|var)\s+)?(?:[A-Za-z_$][\w$]*(?:\s*,\s*[A-Za-z_$][\w$]*)*"
    r"|\{(?:[^{}]|\{[^{}]*\})*\}|\[(?:[^\[\]]|\[[^\[\]]*\])*\])\s*=(?![=>])\s*)?"
    r"(?:await\s+)?(?:new\s+)?(?:[A-Za-z_$][\w$]*\.)*")
# A span that opens a JSX element (`<Canvas`), which a Props, Params or Parameters cell writes as a usage, not as
# the row's props.
ELEMENT_OPEN_RE = re.compile(r"<[A-Za-z_$]")
# A Props, Params or Parameters span that only names a type or writes a placeholder, not the row's props or
# parameters (`ButtonProps`, `ComponentProps<typeof Link>`, `None`, `-`): a lone dash, or one identifier or dotted
# path, then at most one `<...>` type-argument list (group 1, which _type_parameters_only reads).
TYPE_ONLY_RE = re.compile(r"[-\u2013\u2014]|[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\s*(<.*>)?")
# A complete form's name, before its type parameters and parameter group (group 1, absent for none).
SPAN_NAME_RE = re.compile(r"\s*([A-Za-z_$][\w$]*)?\s*")
# What a complete form writes after its parameter group before its return: `->`, `=>`, `→` or `:` (not `::`).
RETURN_SEPARATOR_RE = re.compile(r"\s*(?:->|=>|→|:(?!:))")
# A declaration that gets a form: a function keyword before its name, on its masked line.
FUNCTION_KEYWORD_RE = re.compile(r"(?<![\w$])(?:function|def|fn|func)(?![\w$])")
# After a declaration's parameter group: the `:` a TS return type follows (a `{` right after it opens the type, not
# the body), and a Rust `where` clause, which the body comes after.
RETURN_COLON_RE = re.compile(r"\s*:\s*")
WHERE_CLAUSE_RE = re.compile(r"\s+where(?![\w$])")
# A declaration's text that ends in the middle of its return type: a body opener after one of these is part of that
# type, cut short (Go's `interface{}` and `struct{...}`, a TS union, intersection, `asserts x is {...}`, `keyof {...}`,
# conditional or function type), and so is a declaration that ends with one (`): Promise<A> |`, Python's `\`).
OPENER_IN_TYPE_RE = re.compile(r"(?:(?<![\w$])(?:interface|struct|is|keyof)|[|&?:\\]|=>|->)\s*$")
# A header cell wrapped in `**` or `__` (group 2 its text).
EMPHASIS_RE = re.compile(r"(\*\*|__)(.+)\1")
PLAIN_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][\w$]*")
TABLE_CELL_RE = re.compile(r"(?<!\\)\|")
# A comment's opening marker: `//`, `#`, `/*`, `--`, `<!--` or `;`.
COMMENT_MARKER_RE = re.compile(r"[ \t]*(?://+|#+|/\*+|--|<!--|;+)")
# A cited path's line suffix: `:12`, `:L12`, `:12-30` or `:L12-L30`.
LINE_SUFFIX_RE = re.compile(r":L?\d+(?:-L?\d+)?$")
PYTHON_LANGUAGES = frozenset({"python", "py", "python3"})
RUST_LANGUAGES = frozenset({"rust", "rs"})
GO_LANGUAGES = frozenset({"go", "golang"})
# Column-0 public declarations (group 1 the name), matched on the block with comments and strings masked.
JS_DECLARATION_RE = re.compile(
    r"export\s+(?:default\s+(?:abstract\s+)?(?:async\s+)?(?:function(?:\s*\*\s*|\s+)|class\s+)"
    r"|(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function(?:\s*\*\s*|\s+)|const\s+enum\s+|const\s+|let\s+|var\s+|class\s+|interface\s+|type\s+|enum\s+))"
    r"(?!(?:extends|implements)(?![\w$]))([A-Za-z_$][\w$]*)")
PYTHON_DECLARATION_RE = re.compile(r"(?:async\s+def|def|class)\s+([A-Za-z_]\w*)")
RUST_DECLARATION_RE = re.compile(
    r"pub\s+(?:(?:async|unsafe|const|extern)\s+)*(?:fn|struct|enum|trait|type|const|static)\s+(?:mut\s+)?"
    r"([A-Za-z_]\w*)")
RUST_MACRO_EXPORT_RE = re.compile(r"#\[macro_export\]")
RUST_MACRO_RE = re.compile(r"(?:#\[[^\]]*\][ \t]*)*macro_rules![ \t]*([A-Za-z_]\w*)")
# Go: a single declaration (group 1 its keyword, group 2 its names) or a group's opening line (group 1).
GO_DECLARATION_RE = re.compile(r"(func|type|var|const)[ \t]+([A-Za-z_]\w*(?:[ \t]*,[ \t]*[A-Za-z_]\w*)*)")
GO_GROUP_RE = re.compile(r"(type|var|const)[ \t]*\([ \t]*$")
GO_GROUP_NAMES_RE = re.compile(r"[ \t]+([A-Za-z_]\w*(?:[ \t]*,[ \t]*[A-Za-z_]\w*)*)")
# Bookkeeping variants folded to their base name, in rule order.
FOLD_SUFFIXES = ("_def", "_exact")
FOLD_PREFIX = "a11y_"
ROOT_SUBPATHS = (None, ".")
# The latest action of a scope-expansion amendment that keeps its path out of scope.
DECLINED_ACTIONS = ("skipped", "demoted-include")
# The rungs each laddered clause tries in order, `scalar` being stats.effective_denominator.
CLAUSE_LADDERS = {
    "stratified-scope": ("scalar", "tier_a_include", "scope.include"),
    "specific-modules": ("scalar", "scope.include"),
    "multi-entry": ("scalar", "tier_a_include", "subpaths"),
}
# --barrel: what the workflow read of the entry points, where surface cannot tell -> the extractor's status.
BARREL_FLAG = {"barrel": "barrel", "empty": "empty-barrel", "none": "no-entry-point"}
# The scope types the pattern-reference clause never applies to (a reference app's brief carries its own
# pattern-surface denominator).
NOT_PATTERN_REFERENCE = frozenset({"specific-modules", "component-library", "docs-only", "reference-app"})
# The languages skf-extract-public-api.py's recipes read (its LANGUAGE_FAMILIES).
RECIPE_LANGUAGES = frozenset({"python", "rust", "go", "golang", "typescript", "ts", "tsx", "javascript", "js",
                              "jsx", "vue"})


class InputError(Exception):
    """An input file that cannot be used."""


class SchemaError(Exception):
    """Per-file results that break the schema: `violations` names each breach."""

    def __init__(self, violations: list[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


_SIBLINGS: dict[str, object] = {}
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"


def _sibling(filename: str, folder: Path | None = None):
    """A script beside this one, loaded once: validate-inventory.py (the doc
    text, and the skill citations floor reads), locate-export-segments.py
    (the line model floor reads the skill with) and score-signatures.py (the
    per-file result schema); or, with
    `folder`, one in that folder: SHARED_SCRIPTS'
    skf-resolve-authoritative-files.py (a skill brief's YAML)."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = (folder or Path(__file__).resolve().parent) / filename
        spec = importlib.util.spec_from_file_location("skf_" + filename[:-3].replace("-", "_"), path)
        if spec is None or spec.loader is None or not path.is_file():
            where = f"in {folder}" if folder else f"beside {Path(__file__).name}"
            raise InputError(f"{filename} not found {where}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[filename] = module
    return module


def round2(value: float) -> float:
    """Round to 2 decimals with JS-compatible half-up rounding (matches compute-score.py)."""
    return math.floor(value * 100 + 0.5) / 100


def _read_json(path: str, flag: str):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {flag} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"{flag} {path} is not JSON: {exc.msg}") from exc


def _object(path: str, flag: str) -> dict:
    data = _read_json(path, flag)
    if not isinstance(data, dict):
        raise InputError(f"{flag} {path} is not a JSON object")
    return data


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _export_name(item) -> str | None:
    """The name of a metadata exports[] item: a string, or an object's name."""
    if isinstance(item, str):
        return item or None
    if isinstance(item, dict):
        for key in ("name", "export_name"):
            if isinstance(item.get(key), str) and item[key]:
                return item[key]
    return None


def _entries(provenance: dict | None) -> list[dict]:
    entries = provenance.get("entries") if isinstance(provenance, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _entry_names(provenance: dict | None) -> list[str]:
    return [e["export_name"] for e in _entries(provenance)
            if isinstance(e.get("export_name"), str) and e["export_name"]]


# --------------------------------------------------------------------------
# census
# --------------------------------------------------------------------------


def census(skill_dir: str) -> dict:
    root = Path(skill_dir)
    if not (root / "SKILL.md").is_file():
        raise InputError(f"--skill-dir {skill_dir} holds no SKILL.md")
    try:
        text = _sibling("validate-inventory.py").load_doc_text(skill_dir)
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read the skill text under {skill_dir}: {exc}") from exc
    counts = {form: text.count(marker) for form, marker in CITATION_FORMS.items()}
    local = sum(counts[form] for form in LOCAL_FORMS)
    refs = root / "references"
    files = ["SKILL.md"] + ([f"references/{p.name}" for p in sorted(refs.glob("*.md"))] if refs.is_dir() else [])
    return {
        "citations": counts,
        "localCitations": local,
        "docsOnly": counts["EXT"] > 0 and local == 0,
        "files": files,
    }


# --------------------------------------------------------------------------
# floor
# --------------------------------------------------------------------------


def _floor_name(text: str) -> str | None:
    """The plain identifier `text` writes once a leading `new ` and everything from the first `(`, `<` or `[` are
    cut; None for any other text, a dotted or `::` name and an array type (`Foo[]`, an empty `[]` at the cut)
    among them."""
    text = text.strip()
    if text.startswith("new "):
        text = text[4:]
    cut = re.match(r"([^(<\[]*)(\[\s*\])?", text)
    if cut.group(2):
        return None
    text = cut.group(1).strip()
    return text if PLAIN_IDENTIFIER_RE.fullmatch(text) else None


def _header_word(cell: str) -> str:
    """A header cell's word, lower case, unwrapped from `**` or `__`."""
    m = EMPHASIS_RE.fullmatch(cell)
    return (m.group(2) if m else cell).strip().lower()


def _header_parts(cell: str) -> list[str]:
    """A header cell's word (_header_word) split at each `/`, each part stripped and read as _header_word reads a
    cell: `Component / Props`, `**Function/Type**` and `**Component** / Props` give two parts, a cell with no `/`
    its one word."""
    return [_header_word(part.strip()) for part in _header_word(cell).split("/")]


def _floor_table_header(cell: str) -> bool:
    """Whether a table's first header cell names exports, so the floor reads that table's first column (#1004): its
    first part (_header_parts) is one of FLOOR_TABLE_HEADERS and each other part one of them or of
    FLOOR_PROPS_HEADERS. `Functions`, `Queries`, `Component / Props` and `Function/Type` do; `Name`, `Prop / Type`,
    `Props / Component` and `Symbol / keyword` do not."""
    first, *rest = _header_parts(cell)
    return first in FLOOR_TABLE_HEADERS and all(part in FLOOR_TABLE_HEADERS | FLOOR_PROPS_HEADERS for part in rest)


def _header_label(cell: str) -> tuple[str, bool]:
    """A header cell's word as _header_word reads it, and whether it carries a partial label (#888): one of
    FLOOR_PARTIAL_LABELS in parentheses after the word (`Signature (simplified)`, `**Signatures (Key
    Parameters)**`), any case, whitespace runs inside them as one space, the label then cut from the word. Any other
    text after the word (`Signature (TypeScript)`) stays in it, so that column is read as before."""
    word = _header_word(cell)
    if word.endswith(")"):
        head, opened, label = word[:-1].rpartition("(")
        if opened and " ".join(label.split()) in FLOOR_PARTIAL_LABELS:
            return head.rstrip(), True
    return word, False


def _cells(row: str) -> list[str]:
    """A table row's cells, split on each unescaped `|`, each stripped."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.strip() for cell in TABLE_CELL_RE.split(row)]


def _whole_span(text: str, segments) -> str | None:
    """The code span `text` is, when the whole of it is one; else None."""
    spans = segments._inline_code(text)
    if len(spans) != 1:
        return None
    run = len(text) - len(text.lstrip("`"))
    return spans[0] if text == "`" * run + spans[0] + "`" * run else None


def _comment_text(line: str) -> str | None:
    """A comment line's text, its markers stripped (`// x`, `# x`, `/* x */`, `-- x`, `<!-- x -->`, `; x`);
    None for a line that is no comment. Linear in the line's length."""
    m = COMMENT_MARKER_RE.match(line)
    if not m:
        return None
    text = line[m.end():].strip()
    if text.endswith("-->"):
        text = text[:-3]
    elif text.endswith("*/"):
        text = text[:-2].rstrip("*")
    return text.strip()


def _headed(lines: list[str], opening: int, closing: int, cited: set[str], inventory) -> bool:
    """Whether a source citation heads the fenced block opening at `opening`: its first non-blank line is a
    comment holding a citation, or naming a path the skill cites (a `:12`, `:L12` or `:12-30` suffix left
    out). A citation on the line above the fence heads nothing."""
    first = next((lines[i] for i in range(opening + 1, closing) if lines[i].strip()), None)
    text = _comment_text(first) if first is not None else None
    if not text:
        return False
    if inventory._SKILL_CITATION_RE.search(text):
        return True
    suffix = LINE_SUFFIX_RE.search(text)
    path = text[:suffix.start()] if suffix else text
    return bool(path) and not any(c.isspace() for c in path) and inventory._cited_path(path) in cited


def _html_comment_lines(lines: list[str], start: int, code: list[bool]) -> set[int]:
    """The lines inside an HTML comment, the fenced lines it holds included, read as _prose reads one: a line
    outside fenced code that starts `<!--` opens it, the next such line holding `-->` closes it."""
    inside, open_ = set(), False
    for i in range(start, len(lines)):
        if open_:
            inside.add(i)
            open_ = code[i] or "-->" not in lines[i]
        elif not code[i] and lines[i].strip().startswith("<!--"):
            inside.add(i)
            open_ = "-->" not in lines[i].strip()[4:]
    return inside


def _names(text: str) -> list[str]:
    return [name.strip() for name in text.split(",")]


def _declared_names(lines: list[str], language: str, js_family) -> list[tuple[int, str]]:
    """(offset, name) of each column-0 public declaration in a block's masked lines, by its language."""
    found: list[tuple[int, str]] = []
    if language in js_family:
        found = [(i, m.group(1)) for i, line in enumerate(lines) if (m := JS_DECLARATION_RE.match(line))]
    elif language in PYTHON_LANGUAGES:
        found = [(i, m.group(1)) for i, line in enumerate(lines)
                 if (m := PYTHON_DECLARATION_RE.match(line)) and not m.group(1).startswith("_")]
    elif language in RUST_LANGUAGES:
        exported = False  # a `#[macro_export]` above, with only blank or attribute lines between
        for i, line in enumerate(lines):
            if m := RUST_DECLARATION_RE.match(line):
                found.append((i, m.group(1)))
            exported = exported or bool(RUST_MACRO_EXPORT_RE.match(line))
            macro = RUST_MACRO_RE.match(line)
            if macro and exported:
                found.append((i, macro.group(1)))
            if macro or (line.strip() and not line.startswith("#[")):
                exported = False
    elif language in GO_LANGUAGES:
        group, depth = False, 0  # inside a `type (`, `var (` or `const (` group, and its bracket depth there
        for i, line in enumerate(lines):
            if group:
                if depth == 0 and line.lstrip().startswith(")"):
                    group = False
                    continue
                if depth == 0 and (m := GO_GROUP_NAMES_RE.match(line)):
                    found += [(i, name) for name in _names(m.group(1)) if name[0].isupper()]
                depth = max(0, depth + sum(map(line.count, "{([")) - sum(map(line.count, "})]")))
            elif GO_GROUP_RE.match(line):
                group, depth = True, 0
            elif m := GO_DECLARATION_RE.match(line):
                found += [(i, name) for name in _names(m.group(2)) if name[0].isupper()]
    return found


def _form(text: str, group: tuple[int, int], extension: str = "") -> dict | None:
    """{"params", "return_type"} of a form whose parameter group is `group`, whitespace runs read as one space: the
    text inside the group, and the return after it (score-signatures.py's _signature_parts), "" for none; None for a
    form that writes neither (`f()`)."""
    form = {"params": " ".join(text[group[0] + 1:group[1]].split()),
            "return_type": " ".join(_sibling("score-signatures.py")._signature_parts(text, extension)[1].split())}
    return form if form["params"] or form["return_type"] else None


def _type_parameters_only(text: str) -> bool:
    """Whether `text` is empty or one `<...>` or `[...]` pair, the type parameters a form writes before its group."""
    text = text.strip()
    if not text:
        return True
    if text[0] not in "<[" or text[-1] != {"<": ">", "[": "]"}[text[0]]:
        return False
    depth = 0
    for i, ch in enumerate(text):
        if ch in "<[(":
            depth += 1
        elif ch in ">])" and not (ch == ">" and text[i - 1:i] in ("-", "=")):
            depth -= 1
            if depth == 0 and i != len(text) - 1:
                return False
    return depth == 0


def _call_form(span: str, name: str | None) -> dict | None:
    """The signature a span writes when it is a complete form (_form): `name` or no name (a Signature cell's
    `(x: A) => B`), its type parameters, one parameter group (score-signatures.py's _group), then nothing, or a
    return separator (`->`, `=>`, `→` or `:`) and the return, with nothing else: no other text after the group
    (`useQuery(key).data`, `f(a) / f(a, b)`, a trailing comment), no `;`, `,`, `#`, `//` or `/*` in the return
    outside its brackets and strings, and every bracket and string closed. None for any other span, a constructor
    call (`new Client(opts)`) and a span with no parameter group (`Meta<T>`) among them."""
    scorer = _sibling("score-signatures.py")
    text = span.strip()
    group = scorer._group(text)
    if group is None or text.startswith("new ") or scorer._levels(text + " ")[-1] != 0:
        return None
    head = SPAN_NAME_RE.match(text, 0, group[0])
    if head.group(1) not in (None, name) or not _type_parameters_only(text[head.end():group[0]]):
        return None
    tail = text[group[1] + 1:]
    separator = RETURN_SEPARATOR_RE.match(tail)
    returned = tail[separator.end():] if separator else ""
    if (separator is None and tail.strip()) or (separator is not None and not returned.strip()):
        return None
    levels = scorer._levels(returned)
    if any(levels[i] == 0 and (ch in ";,#" or returned.startswith(("//", "/*"), i)) for i, ch in enumerate(returned)):
        return None
    return _form(text, group)


def _element_form(text: str, name: str) -> dict | None:
    """{"usage_signature", "return_type"} of a span that is one self-closing JSX element of `name` setting at least
    one prop (`<Canvas of={X} />`): the element, whitespace runs as one space, and ""; None for any other span, a
    prop-less `<Canvas />`, an element with children, two elements and an unclosed brace or string among them."""
    head = re.match(rf"<{re.escape(name)}\s+", text)
    if head is None or not text.endswith("/>") or not text[head.end():-2].strip():
        return None
    depth, quote = 0, None  # brace depth, and the quote a string is open on
    for ch in text[head.end():-2]:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'`":
            quote = ch
        elif ch in "{}":
            depth += 1 if ch == "{" else -1
            if depth < 0:
                return None
        elif depth == 0 and ch in "<>/":
            return None
    return None if depth or quote else {"usage_signature": " ".join(text.split()), "return_type": ""}


def _usage_form(span: str, name: str) -> dict | None:
    """The signature a span writes as a usage of `name` (#888), whitespace runs as one space: at least one of, in this
    order, an assignment (`x =`, `const { data } =`), `await`, `new` and a receiver or module path (`cognee.`), then
    `name`'s complete form (_call_form): {"usage_signature": the span through the parameter group, "return_type": the
    return after it, "" for none}; or one JSX element of `name` that sets a prop (_element_form). None for any other
    span, an empty call (`new Client()`) and a prop-less element (`<Canvas />`) among them."""
    text = span.strip()
    if text.startswith("<"):
        return _element_form(text, name)
    prefix = USAGE_PREFIX_RE.match(text)
    rest = text[prefix.end():]
    if not prefix.group() or not re.match(rf"{re.escape(name)}(?![\w$])", rest):
        return None
    form = _call_form(rest, name)
    if form is None:
        return None
    group = _sibling("score-signatures.py")._group(rest)
    return {"usage_signature": " ".join(text[:prefix.end() + group[1] + 1].split()), "return_type": form["return_type"]}


def _span_form(span: str, name: str | None) -> dict | None:
    """The signature a span writes: its complete form (_call_form), else its usage form (_usage_form)."""
    return _call_form(span, name) or (_usage_form(span, name) if name else None)


def _labelled(form: dict | None, partial: bool) -> dict | None:
    """`form`, with `signature_form` "partial" when its column's header gives a partial label (#888)."""
    return {**form, "signature_form": "partial"} if form and partial else form


def _ellipsis_labelled(signature: dict | None, extension: str = "") -> dict | None:
    """`signature`, with `signature_form` "partial" when its parameter group holds an ellipsis item (#1029): a member,
    cut at the commas outside every bracket pair and string (score-signatures.py's _split), that score-signatures.py's
    _parameter reads as one, `...` or `…` alone, so a rest `...args`, a `*args` and a default `x=...` are none. The
    group is the whole `params`, or the one a `usage_signature` writes (score-signatures.py's _group). The contract
    counts such a `...` as the skill's partial label, so the floor pins it with the form, at every origin."""
    if not signature:
        return signature
    scorer = _sibling("score-signatures.py")
    text = signature.get("params")
    if text is None:
        group = scorer._group(signature["usage_signature"], extension)
        text = signature["usage_signature"][group[0] + 1:group[1]] if group else ""
    items = scorer._split(text, ",", extension)
    return _labelled(signature, any(scorer._parameter(item.strip(), extension)["ellipsis"] for item in items))


def _column(labels: list[tuple[str, bool]], words: frozenset) -> tuple[int | None, bool]:
    """The first header cell whose word (_header_label) is one of `words`, and its partial label; (None, False) for
    none."""
    return next(((i, labelled) for i, (word, labelled) in enumerate(labels) if word in words), (None, False))


def _signature_column(header: list[str]) -> tuple[int | None, bool]:
    """The first header cell with a part (_header_parts) whose word, as _header_label reads that part, is one of
    FLOOR_SIGNATURE_HEADERS, and that part's partial label (#1030): `Signature`, `Signature / Purpose`,
    `Props / Signature` and `Signature (simplified) / Purpose`, labelled, are one; `Signature (TypeScript)`,
    `Props / Usage` and `Usage` are not. (None, False) for none."""
    parts = ((i, _header_label(part)) for i, cell in enumerate(header) for part in _header_parts(cell))
    return next(((i, labelled) for i, (word, labelled) in parts if word in FLOOR_SIGNATURE_HEADERS), (None, False))


def _leading_span(cell: str) -> str | None:
    """The code span a table cell opens with, None when it opens with none."""
    run = len(cell) - len(cell.lstrip("`"))
    spans = _sibling("locate-export-segments.py")._inline_code(cell) if run else []
    return spans[0] if spans and cell.startswith("`" * run + spans[0] + "`" * run) else None


def _row_form(header: list[str], row: list[str]) -> dict | None:
    """The signature a floor table's row writes for the one name its first cell names (a row naming several gives
    none), each cell's `\\|` read as `|`: the leading code span of its Signature or Signatures cell, a header with a
    part split at `/` that is one included (`Signature / Purpose`, `Props / Signature`; _signature_column, #1030),
    else, when that span writes no parameter group, the one span of its first cell that gives that name (another
    export's span there gives nothing), each a complete form (_call_form), else a usage form (_usage_form, #888). A
    Signature span with a group that is neither gives none, and so does such a first-cell span. Only then its Props,
    Params or Parameters cell, its whole header the word (`Props / Usage` and `Props / Type` are none), when the
    whole cell is one code span (trailing prose or several spans leave it the reader's): a complete
    form, else a usage form, else none when it writes a parameter group or opens a JSX element, or when it only names
    a type or writes a placeholder (`ButtonProps`, `ComponentProps<typeof Link>`, `None`, `-`), else the span whole as
    `params`, `return_type` "", kept as written. A Signature, Props, Params or Parameters header may carry a partial
    label (_header_label, #888): the form its cell gives then also gives `signature_form` "partial", the first-cell
    form never. An Arguments, Args, Usage, Syntax or Example cell is never read: its form stays the reader's."""
    segments = _sibling("locate-export-segments.py")
    scorer = _sibling("score-signatures.py")
    names = {name for name in map(_floor_name, segments._inline_code(row[0])) if name}
    if len(names) != 1:
        return None
    [name] = names
    cells = [cell.replace("\\|", "|") for cell in row]
    labels = [_header_label(cell) for cell in header]
    at, partial = _signature_column(header)
    span = _leading_span(cells[at]) if at is not None and at < len(cells) else None
    if span is not None and (form := _span_form(span, name)):
        return _labelled(form, partial)
    if span is not None and scorer._group(span.strip()) is not None:
        return None  # the cell writes a call the floor cannot pin: a shorter first-cell form would hide it
    own = [span for span in segments._inline_code(cells[0]) if _floor_name(span) == name]
    if len(own) == 1 and (form := _span_form(own[0], name)):
        return form
    if any(scorer._group(span.strip()) is not None for span in own):
        return None  # the first cell writes a call the floor cannot pin: the Props cell would stand in for it
    at, partial = _column(labels, FLOOR_PROPS_HEADERS)
    span = _whole_span(cells[at], segments) if at is not None and at < len(cells) else None
    if span is None:
        return None
    if form := _span_form(span, name):
        return _labelled(form, partial)
    if scorer._group(span.strip()) is not None or ELEMENT_OPEN_RE.match(span.strip()) or not span.strip():
        return None
    if (only := TYPE_ONLY_RE.fullmatch(span.strip())) and _type_parameters_only(only.group(1) or ""):
        return None  # the span names a type or writes a placeholder, no props or parameters
    return _labelled({"params": " ".join(span.split()), "return_type": ""}, partial)


def _function_declaration(line: str, language: str, js_family) -> int | None:
    """Where the name ends on a block's masked line, one _declared_names reads, that declares a function (`function`,
    `def`, `fn` or Go's `func` before its name); None for a line that declares no function."""
    if language in js_family:
        m, at = JS_DECLARATION_RE.match(line), 1
    elif language in PYTHON_LANGUAGES:
        m, at = PYTHON_DECLARATION_RE.match(line), 1
    elif language in RUST_LANGUAGES:
        m, at = RUST_DECLARATION_RE.match(line), 1
    elif language in GO_LANGUAGES:
        m, at = GO_DECLARATION_RE.match(line), 2
    else:
        return False
    return m.end(at) if m and FUNCTION_KEYWORD_RE.search(line, 0, m.start(at)) else None


def _declaration_form(rows: list[str], offset: int, language: str, name_end: int) -> dict | None:
    """The signature the function declaration at `offset` of a block's unmasked `rows` writes: the declaration on one
    line (skf-extract-public-api.py's _declaration_signature: a parameter list split over lines joined, line comments
    left out), its body cut at the first `:` (Python) or `{`, `;` or ` where ` (any other language) outside every
    bracket pair and string after the parameter group, a `{` directly after a TS return `:` opening the return type,
    then read as _form reads it. None when anything but type parameters sits between the name's end (`name_end`,
    the masked line's offset, which masking keeps) and the group (a Go `func(...)` return read as the group), when
    the opener follows, or the uncut text ends with, `interface`, `struct`, `is`, `keyof`, `|`, `&`, `?`, `:`, `\\`,
    `=>` or `->` (it is inside the return type: Go's `interface{}`, a TS `asserts x is {...}`, `() => {...}` or
    conditional type, a line that ends mid-type), or a bracket or string it opens does not close."""
    scorer = _sibling("score-signatures.py")
    extractor = _sibling("skf-extract-public-api.py", SHARED_SCRIPTS)
    python, rust = language in PYTHON_LANGUAGES, language in RUST_LANGUAGES
    extension = ".rs" if rust else ""
    text = extractor._declaration_signature(rows, offset, "python" if python else "rust" if rust else language)
    group = scorer._group(text, extension)
    if group is None or not _type_parameters_only(text[name_end:group[0]]):
        return None
    levels = scorer._levels(text, extension)
    for i in range(group[1] + 1, len(text)):
        if levels[i] != 0:
            continue
        if python:
            body = text[i] == ":"
        else:
            body = (text[i] == ";" or bool(WHERE_CLAUSE_RE.match(text, i))
                    or (text[i] == "{" and not RETURN_COLON_RE.fullmatch(text, group[1] + 1, i)))
        if body:
            if OPENER_IN_TYPE_RE.search(text, 0, i):
                return None
            text = text[:i]
            break
    else:
        if OPENER_IN_TYPE_RE.search(text):
            return None
    if scorer._levels(text + " ", extension)[-1] != 0:
        return None
    return _form(text, group, extension)


def floor(skill_dir: str) -> dict:
    """The names the skill documents in a fixed form, each with its origins (see the module docstring)."""
    root = Path(skill_dir)
    if not (root / "SKILL.md").is_file():
        raise InputError(f"--skill-dir {skill_dir} holds no SKILL.md")
    segments = _sibling("locate-export-segments.py")
    inventory = _sibling("validate-inventory.py")
    refs = root / "references"
    files = ["SKILL.md"] + ([f"references/{p.name}" for p in sorted(refs.glob("*.md")) if p.is_file()]
                           if refs.is_dir() else [])
    texts = []
    for rel in files:
        try:
            texts.append(segments._split_lines((root / rel).read_bytes().decode("utf-8-sig")))
        except (OSError, UnicodeDecodeError) as exc:
            raise InputError(f"cannot read {rel} under {skill_dir}: {exc}") from exc
    cited = {inventory._cited_path(m.group(2))
             for lines in texts for line in lines for m in inventory._SKILL_CITATION_RE.finditer(line)}

    found: dict[str, set[tuple[int, int, str, str | None]]] = {}
    signatures: dict[tuple[str, int, int, str], dict] = {}  # the first per (name, file, line, form), in span order

    def add(name: str | None, file_index: int, index: int, form: str, label: str | None = None,
            signature: dict | None = None, extension: str = "") -> None:
        if name:
            found.setdefault(name, set()).add((file_index, index + 1, form, label))
            if signature is not None:
                signatures.setdefault((name, file_index, index + 1, form), _ellipsis_labelled(signature, extension))

    js_family = segments.JS_FAMILY - {"svelte"}  # a Svelte block's `export let` is a component prop
    for file_index, lines in enumerate(texts):
        start = segments._frontmatter_end(lines)
        blocks, code = segments._fenced_blocks(lines, start)
        headings, prose = segments._prose(lines, start, code)
        for block in prose:
            if block["kind"] != "table-row" or block["header"] is None:
                continue
            header = _cells(block["header"])
            if not _floor_table_header(header[0]):
                continue
            row = _cells(lines[block["start"]])
            kind_at = next((i for i, cell in enumerate(header) if _header_word(cell) == "kind"), None)
            label = row[kind_at] if kind_at is not None and kind_at < len(row) and row[kind_at] else None
            signature = _row_form(header, row)
            for span in segments._inline_code(row[0]):
                add(_floor_name(span), file_index, block["start"], "table-row", label, signature)
        for index, _level, text, _above in headings:
            span = _whole_span(text, segments)
            if span is not None:
                add(_floor_name(span), file_index, index, "heading", None, _span_form(span, _floor_name(span)))
        comments = _html_comment_lines(lines, start, code)
        for opening, closing, info in blocks:
            language = segments._language(info)
            if (opening in comments or language in segments.DATA_LANGUAGES
                    or not _headed(lines, opening, closing, cited, inventory)):
                continue
            masked = segments.mask_code("\n".join(lines[opening + 1:closing]), language).split("\n")
            for offset, name in _declared_names(masked, language, js_family):
                name_end = _function_declaration(masked[offset], language, js_family)
                signature = (_declaration_form(lines[opening + 1:closing], offset, language, name_end)
                             if name_end is not None else None)
                add(name, file_index, opening + 1 + offset, "declaration", None, signature,
                    ".rs" if language in RUST_LANGUAGES else "")

    names = []
    by_form = dict.fromkeys(FLOOR_FORMS, 0)
    for name in sorted(found):
        origins = sorted(found[name], key=lambda o: (o[0], o[1], FLOOR_FORMS.index(o[2]), o[3] or ""))
        seen, kept = set(), []
        for file_index, line, form, _label in origins:
            if (file_index, line, form) not in seen:
                seen.add((file_index, line, form))
                origin = {"file": files[file_index], "line": line, "form": form}
                if (name, file_index, line, form) in signatures:
                    origin["signature"] = signatures[(name, file_index, line, form)]
                kept.append(origin)
                by_form[form] += 1
        label = next((o[3] for o in origins if o[2] == "table-row" and o[3]), None)
        names.append({"name": name, "kindLabel": label, "origins": kept})
    return {"files": files, "names": names, "summary": {"names": len(names), "byForm": by_form}}


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------


def _pair_name(pair) -> str | None:
    if isinstance(pair, str):
        return pair or None
    if isinstance(pair, (list, tuple)) and len(pair) == 2 and all(isinstance(p, str) and p for p in pair):
        return f"{pair[0]} + {pair[1]}"
    if isinstance(pair, dict) and all(isinstance(pair.get(k), str) and pair[k] for k in ("a", "b")):
        return f"{pair['a']} + {pair['b']}"
    return None


def _library_name(lib) -> str | None:
    if isinstance(lib, str):
        return lib or None
    if isinstance(lib, dict) and isinstance(lib.get("name"), str) and lib["name"]:
        return lib["name"]
    return None


def metadata_inputs(meta: dict, provenance: dict | None) -> dict:
    stats = meta.get("stats") if isinstance(meta.get("stats"), dict) else {}
    exports = meta.get("exports")
    names = [n for n in (_export_name(e) for e in exports) if n] if isinstance(exports, list) else []
    entry_names = _entry_names(provenance) if provenance is not None else None
    named = sorted({n for n in entry_names or [] if METHOD_SEPARATOR not in n})
    dist = stats.get("confidence_distribution")
    if not isinstance(dist, dict):
        dist = meta.get("confidence_distribution") if isinstance(meta.get("confidence_distribution"), dict) else None
    if dist is not None:
        dist = {tier: dist[tier] for tier in ("t1", "t1_low", "t2", "t3") if _count(dist.get(tier)) is not None}
    documented = _count(stats.get("exports_documented"))
    effective = _count(stats.get("effective_denominator"))
    skill_type = meta.get("skill_type") if isinstance(meta.get("skill_type"), str) else None

    stack = None
    if skill_type == "stack":
        if named:
            stack = {"basis": "provenance", "denominator": len(named), "compositionNames": named}
        else:
            libraries = [n for n in (_library_name(lib) for lib in meta.get("libraries") or []) if n]
            pairs = [n for n in (_pair_name(p) for p in meta.get("integration_pairs") or []) if n]
            stack = {"basis": "composition", "denominator": len(libraries) + len(pairs),
                     "compositionNames": libraries + pairs}

    return {
        "skillType": skill_type,
        "scopeType": meta.get("scope_type") if isinstance(meta.get("scope_type"), str) else None,
        "clusterA": {
            "exports_public_api": _count(stats.get("exports_public_api")),
            "exports_length": len(exports) if isinstance(exports, list) else None,
        },
        "clusterB": {"exports_documented": documented},
        "provenanceExportNames": entry_names,
        "confidenceDistribution": dist or None,
        "namedExports": {"count": len(named), "names": named} if entry_names is not None else None,
        "effectiveDenominator": effective,
        # The stored count counts each name once, while the map (so stats.exports_documented) holds an entry for
        # each name and file: a name the entry points pass on from two files is two entries, one name. Only a map
        # with no `::` entry takes that arm: the stored count holds no method, so a map with methods could match it
        # only by chance, and its methods would stand in for an undocumented name.
        "inflationSignature": effective is not None and (
            documented == effective or (bool(entry_names) and not any(METHOD_SEPARATOR in n for n in entry_names)
                                        and len(set(entry_names)) == effective)),
        "declaredNames": sorted(set(names)) if names else named,
        "stack": stack,
    }


# --------------------------------------------------------------------------
# surface
# --------------------------------------------------------------------------


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_match(rel_path: str, pattern: str) -> bool:
    """skf-resolve-authoritative-files.py's glob rule, which the extractor applies."""
    compiled = _GLOB_CACHE.get(pattern)
    if compiled is None:
        parts = pattern.split("/")
        out: list[str] = []
        for i, part in enumerate(parts):
            if part == "**":
                out.append("(?:.*/)?" if i + 1 < len(parts) else ".*")
                continue
            out.append("".join("[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch) for ch in part))
            if i + 1 < len(parts):
                out.append("/")
        compiled = re.compile("^" + "".join(out) + "$")
        _GLOB_CACHE[pattern] = compiled
    return bool(compiled.match(rel_path))


def _norm(path) -> str:
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _record(name, kind, file, line, signature_line, origin) -> dict:
    return {"name": name, "kind": kind, "file": file, "line": line, "signatureLine": signature_line,
            "origin": origin}


# A provenance map's export_type, read case-insensitively, as the kind of a restored name (#913) or a name exports[]
# gives no kind at its file, such as an extraction gap (#1020): the type kinds
# score-signatures.py's Type Coverage counts (a dataclass, NamedTuple or TypedDict is a class, a Protocol an
# interface, a type alias a type), and `function` and `const`, which are no type (a TypeVar is no type). The
# function kinds a map records by eye, `async_function`, `decorator` and a React `component`, are `function`
# (#1032): no recipe gives such a name a kind, so a class component a map labels `component` reads as one too. Any
# other export_type (`re-export`, `module`, `decorator_namespace`, ...) gives no kind.
PROVENANCE_KINDS = {
    **dict.fromkeys(("class", "dataclass", "namedtuple", "typeddict"), "class"),
    **dict.fromkeys(("protocol", "interface"), "interface"),
    "enum": "enum",
    **dict.fromkeys(("type", "type_alias"), "type"),
    "struct": "struct",
    "trait": "trait",
    **dict.fromkeys(("function", "method", "staticmethod", "classmethod", "async_function", "decorator",
                     "component"), "function"),
    **dict.fromkeys(("const", "constant", "variable", "sentinel", "typevar"), "const"),
}


def _provenance_kinds(records: list[dict], provenance: dict | None) -> None:
    """Give each restored or extraction record with no kind and a file (a
    name the stale-scope guard restored, or one exports[] gives no kind at
    its file, such as an extraction gap, #1020) the kind PROVENANCE_KINDS
    reads from the first provenance entry, in map order, with its name and
    its file (both paths `_norm`ed) and a known kind; no other record
    changes."""
    entries = _entries(provenance)
    for record in records:
        if record["origin"] not in ("restored", "extraction") or record["kind"] or not record["file"]:
            continue
        file = _norm(record["file"])
        record["kind"] = next(
            (kind for e in entries
             if e.get("export_name") == record["name"] and _norm(e.get("source_file")) == file
             and (kind := PROVENANCE_KINDS.get(str(e.get("export_type")).strip().lower()))), None)


def _globs(value) -> list[str]:
    return [g for g in (_norm(v) for v in value if isinstance(v, str)) if g] if isinstance(value, list) else []


def _scope(include, exclude, tier_a_include) -> dict:
    return {"include": _globs(include), "exclude": _globs(exclude), "tier_a_include": _globs(tier_a_include)}


def read_brief(path: str) -> dict:
    """A skill brief's scope globs, scope type and language, the fields skf-extract-public-api.py reads, and the
    latest action of each scope-expansion amendment by its path (`amendments`), a legacy headless skip
    read as a deferral as skf-resolve-authoritative-files.py reads it."""
    try:
        import yaml  # --brief only; `uv run` installs it from the header
    except ImportError as exc:
        raise InputError("--brief is read with PyYAML: run the script with `uv run`") from exc
    resolver = _sibling("skf-resolve-authoritative-files.py", SHARED_SCRIPTS)
    try:
        data = resolver.parse_brief_yaml(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read --brief {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise InputError(f"--brief {path} is not valid YAML: {' '.join(str(exc).split())}") from exc
    if not isinstance(data, dict):
        raise InputError(f"--brief {path} is not a YAML mapping")
    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    amendments: dict[str, str] = {}
    for amend in scope.get("amendments") if isinstance(scope.get("amendments"), list) else []:
        if isinstance(amend, dict) and amend.get("category") == "scope-expansion":
            amended = _norm(amend["path"]) if isinstance(amend.get("path"), str) else ""
            action = resolver._amendment_action(amend)
            if amended and action is not None:
                amendments[amended] = action
    return {"scope": _scope(scope.get("include"), scope.get("exclude"), scope.get("tier_a_include")),
            "type": scope.get("type") if isinstance(scope.get("type"), str) else None,
            "language": data.get("language") if isinstance(data.get("language"), str) else None,
            "amendments": amendments}


def matching(records: list[dict], globs: list[str], excludes: list[str]) -> list[str]:
    """The names whose record names a file one of `globs` matches and no exclude glob does."""
    return sorted({r["name"] for r in records if r.get("file")
                   and any(glob_match(_norm(r["file"]), g) for g in globs)
                   and not any(glob_match(_norm(r["file"]), g) for g in excludes)})


def matching_files(records: list[dict], globs: list[str], excludes: list[str]) -> list[str]:
    """The distinct files `matching` takes its names from: each record's file one of `globs` matches and no
    exclude glob does."""
    return sorted({r["file"] for r in records if r.get("file")
                   and any(glob_match(_norm(r["file"]), g) for g in globs)
                   and not any(glob_match(_norm(r["file"]), g) for g in excludes)})


def _apart(a: str, b: str) -> bool:
    """True when, before either has a `*` or `?`, the two globs spell a different segment at the same
    place, so no file can match both. Any other pair counts as overlapping, even one no file can match
    both of (`src` beside `src/index.ts`), so this never parts two that can share a file."""
    for x, y in zip(a.split("/"), b.split("/")):
        if any(c in x or c in y for c in "*?"):
            return False
        if x != y:
            return True
    return False


def _inside(a: str, b: str) -> bool:
    """True when glob `b` matches every path glob `a` can match: segment by segment each of `b`'s is
    `**`, the same as `a`'s, or `*` beside one of `a`'s that is not `**`, and `a` has as many segments
    as `b`, or more when `b` ends in `**`. Any other pair counts as not inside, even one where `b`
    does cover `a` (`gen/**` in `**/gen/**`), so this never drops a glob that can count a name."""
    xs, ys = a.split("/"), b.split("/")
    if len(xs) < len(ys) or (len(xs) > len(ys) and ys[-1] != "**"):
        return False
    return all(y == "**" or x == y or (y == "*" and x != "**") for x, y in zip(xs, ys))


def _nested_tops(entry_files: list[dict], named: set[str], exporting: set[str]) -> dict[str, str]:
    """{top: the outermost top whose folder holds it} for each Python top
    __init__.py inside the folder of another top that `exporting` lists (one
    that exports at least one public name), a sub-package behind a folder
    with no __init__.py, unless `named` lists its file. A top that exports
    nothing (a stray __init__.py at the source root, say) nests no other."""
    tops = sorted({e["file"] for e in entry_files
                   if e.get("language") == "python" and isinstance(e.get("file"), str) and e["file"]})
    nested = {}
    for top in tops:
        folder = posixpath.dirname(top)
        outer = [o for o in tops if o != top and o in exporting
                 and (not posixpath.dirname(o) or folder.startswith(posixpath.dirname(o) + "/"))]
        if outer and _norm(top) not in named:
            nested[top] = min(outer, key=lambda o: (o.count("/"), o))
    return nested


def _members_in_place(public: list[dict]) -> list[dict]:
    """The public names, a namespace item with a `members` list (the names
    its module passes on, `pkg.sub.name`) given as its members, each with
    the namespace's entry and language and `via: namespace`. A member whose
    name and file another public name, or an earlier member, has is left
    out; a namespace whose members the runner could not read (null), or one
    from a runner that lists none, stays itself."""
    expanded = [p for p in public if not (p.get("via") == "namespace" and isinstance(p.get("members"), list))]
    seen = {(p["name"], p.get("file")) for p in expanded}
    for item in public:
        if item.get("via") != "namespace" or not isinstance(item.get("members"), list):
            continue
        for member in item["members"]:
            if not isinstance(member, dict) or not isinstance(member.get("name"), str) or not member["name"]:
                continue
            key = (member["name"], member.get("file"))
            if key in seen:
                continue
            seen.add(key)
            expanded.append({"name": member["name"], "language": item.get("language"), "entry": item.get("entry"),
                             "via": "namespace", "local": member.get("local"), "file": member.get("file"),
                             "line": member.get("line")})
    return expanded


def _declared_at(row: dict) -> tuple:
    """(line, signature line) of an extraction's exports[] row, as a record
    takes them: a local `export { ... }` list's item at the declaration it
    names (#836), its `declaration_line` and `declaration_signature_line`
    (both from that one pair), when it has that line; else its own
    `source_line` and `signature_line`."""
    if isinstance(row.get("declaration_line"), int):
        return row["declaration_line"], row.get("declaration_signature_line")
    return row.get("source_line"), row.get("signature_line")


OTHER_DECLARATION_KEYS = ("name", "kind", "file", "line", "signatureLine")


def other_declarations(records: list[dict], declarations: list[dict], aliases: dict[str, set[str]],
                       excludes: list[str]) -> list[dict]:
    """The other declarations of the surface names (#918): for each name
    `records` holds, each of `declarations` (an extraction's exports[] rows,
    a re-export left out) recorded under the name, or under a name an
    aliased record's defining file gives it (`aliases`), in a file no
    record of the name names and no exclude glob matches, as {name, kind,
    file, line, signatureLine}, the file normalised (_norm), sorted, each
    declaration once however its path is written. They are no records:
    score-signatures.py plan and test-skill's Split-Body Sources read them."""
    files: dict[str, set[str]] = {}
    for record in records:
        files.setdefault(record["name"], set()).update([_norm(record["file"])] if record.get("file") else [])
    by_export: dict[str, list[dict]] = {}
    for declaration in declarations:
        by_export.setdefault(declaration["exportName"], []).append(declaration)
    found = set()
    for name, own in files.items():
        for looked in {name} | aliases.get(name, set()):
            for d in by_export.get(looked, []):
                path = _norm(d["file"])
                if path in own or any(glob_match(path, g) for g in excludes):
                    continue
                line = d["line"] if isinstance(d["line"], int) and not isinstance(d["line"], bool) else None
                found.add((name, d["kind"] if isinstance(d["kind"], str) else None, path, line,
                           d["signatureLine"] if isinstance(d["signatureLine"], str) else None))
    ordered = sorted(found, key=lambda t: (t[0], t[2], t[3] or 0, t[1] or "", t[4] or ""))
    return [dict(zip(OTHER_DECLARATION_KEYS, t)) for t in ordered]


# The runner's file issues for a file it could not open at all: no one can read it by eye either.
UNREADABLE_ISSUES = frozenset({"missing", "unreadable"})


def _extraction_summary(data: dict, language: str | None) -> dict:
    """The surface's `extraction` object: the runner's status and counts,
    the files to read by eye, the files no one can read and the fallback
    verdict."""
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    arms = data.get("arms") if isinstance(data.get("arms"), dict) else {}
    entry_points = data.get("entry_points") if isinstance(data.get("entry_points"), dict) else {}
    without = data.get("files_without_recipes") if isinstance(data.get("files_without_recipes"), dict) else {}
    status = data.get("status")
    reason = None
    if status == "no-ast-grep":
        reason = "no ast-grep the runner can run"
    elif not data.get("files_in_scope"):
        reason = "no file in scope"
    elif without and not data.get("exports"):
        reason = f"no recipe reads the files in scope ({', '.join(sorted(without))})"
    elif without and language and language.strip().lower() not in RECIPE_LANGUAGES:
        reason = (f"no recipe reads the skill's language, {language} "
                  f"({', '.join(sorted(without))} in scope)")
    errors = [e for e in data.get("errors") or [] if isinstance(e, dict)]
    issues = [i for i in data.get("file_issues") or [] if isinstance(i, dict) and i.get("file")]
    # A file missing from disk or one the runner could not open is no file to read by eye.
    unread = sorted({str(i["file"]) for i in issues if i.get("issue") in UNREADABLE_ISSUES})
    read_by_eye = sorted({str(i["file"]) for i in issues
                          if i.get("issue") != "no-recipes" and i.get("issue") not in UNREADABLE_ISSUES}
                         | {str(e["first_file"]) for e in errors if e.get("first_file")}
                         | {str(f) for e in errors if isinstance(e.get("unread"), list) for f in e["unread"] if f})
    return {
        "status": status,
        "filesInScope": data.get("files_in_scope"),
        "truncated": data.get("truncated"),
        "effectiveDenominator": _count(counts.get("effective_denominator")),
        "effectiveDenominatorBasis": counts.get("effective_denominator_basis"),
        "exportsPublicApi": _count(counts.get("exports_public_api")),
        "arms": arms,
        "curatedSubset": counts.get("curated_subset") if isinstance(counts.get("curated_subset"), bool) else None,
        "entryPointStatus": entry_points.get("status"),
        # A run that read a file in scope and found no entry point says so whether or not ast-grep ran.
        "entryPointsFound": (bool(entry_points["files"]) if isinstance(entry_points.get("files"), list)
                             and data.get("files_in_scope") else None),
        "readByEye": read_by_eye,
        "unread": unread,
        "fallback": {"needed": reason is not None, "reason": reason},
    }


NO_UMBRELLA = {"entries": [], "names": 0, "reexported": 0, "ratio": None, "umbrella": False}


def _outside_row(row: dict, scope: dict) -> dict:
    """An outside_scope row as `excluded.outsideScope` lists it: its name,
    file, line and entry point, and why the brief scopes the file out when
    it does (#796): `excludeGlob`, the first scope.exclude glob that matches
    the file, and `outsideInclude`, true when scope.include has globs and
    none matches it. Neither (null and false) when the brief does not
    explain it, such as a file no recipe reads or no file at all. A
    namespace's member also keeps the namespace it came through
    (`namespace`, #969) when the row gives it as a non-empty string, and
    no such key otherwise."""
    file = row.get("file") if isinstance(row.get("file"), str) and row.get("file") else None
    path = _norm(file) if file else None
    out = {"name": row.get("name"), "file": file, "line": row.get("line"), "entry": row.get("entry"),
           "excludeGlob": next((g for g in scope["exclude"] if glob_match(path, g)), None) if path else None,
           "outsideInclude": bool(path and scope["include"]
                                  and not any(glob_match(path, g) for g in scope["include"]))}
    if isinstance(row.get("namespace"), str) and row["namespace"]:
        out["namespace"] = row["namespace"]
    return out


def from_extraction(data: dict, language: str | None = None, brief: dict | None = None) -> dict:
    """The public surface of an extraction, less what lies outside scope,
    plus the root exports a stale scope.include glob left out. A nested
    Python top's records come apart (`nestedRecords`): they count in the
    scope sets, not in `all`. An extraction the per-file scan replaces
    (`extraction.fallback.needed`) gives only its scope, its stale globs and
    its `extraction` object: no name and no set."""
    if data.get("mode") != "full":
        raise InputError("--extraction is not skf-extract-public-api.py --mode full output")

    # The scope: the one the extractor recorded, else the brief's.
    recorded = data.get("scope") if isinstance(data.get("scope"), dict) else {}
    scope = _scope(recorded.get("include"), recorded.get("exclude"), recorded.get("tier_a_include"))
    if not any(scope.values()) and brief is not None:
        scope = brief["scope"]
    unmatched = _globs(recorded.get("unmatched_include"))
    # A tier A glob that matches no file: the runner's list, never re-matched here.
    unmatched_tier_a = _globs(recorded.get("unmatched_tier_a_include"))
    extraction = _extraction_summary(data, language)
    if extraction["fallback"]["needed"]:
        return {"records": [], "nestedRecords": [], "declarations": [], "aliases": {}, "sets": {}, "outside": [],
                "nested": [],
                "staleScope": {"unmatchedInclude": unmatched, "unmatchedTierAInclude": unmatched_tier_a,
                               "restored": []},
                "gaps": [], "scope": scope, "scopeType": recorded.get("type"), "umbrella": dict(NO_UMBRELLA),
                "subpathEntries": None, "extraction": extraction}

    diff = data.get("entry_point_diff") if isinstance(data.get("entry_point_diff"), dict) else {}
    # Each in-scope definition of a public name is a record of its own (#830): the runner's other
    # definitions join the public rows, so a set holds a name when any of its files matches, and
    # the signature plan reads every declaration.
    rows = {key: [p for p in diff.get(key) or [] if isinstance(p, dict) and isinstance(p.get("name"), str)]
            for key in ("public", "other_definitions")}
    public = _members_in_place(rows["public"] + rows["other_definitions"])
    outside = [o for o in diff.get("outside_scope") or [] if isinstance(o, dict)]
    gaps = [g for g in diff.get("extraction_gaps") or [] if isinstance(g, dict)]

    entry_points = data.get("entry_points") if isinstance(data.get("entry_points"), dict) else {}
    entry_files = [e for e in entry_points.get("files") or [] if isinstance(e, dict)]
    # A Python top nested in another that exports a name is no barrel: its
    # names leave `all`, `root` and the umbrella ratio, and keep their
    # records (so the scope sets a specific-modules or stratified brief
    # counts) and their outside_scope and extraction_gaps rows.
    nested = _nested_tops(entry_files, set(scope["include"]) | set(scope["tier_a_include"]),
                          {p.get("entry") for p in rows["public"]})
    nested_names = {top: sorted({p["name"] for p in public if p.get("entry") == top}) for top in nested}

    subpath_files = {e.get("file") for e in entry_files
                     if e.get("subpath") not in ROOT_SUBPATHS and "*" not in str(e.get("subpath"))}
    root_files = {e.get("file") for e in entry_files if e.get("subpath") in ROOT_SUBPATHS} - set(nested)
    # The distinct in-scope subpaths of those (a package's subpath once, however many files its conditions
    # name), for the multi-entry annotation.
    subpath_entries = {(e.get("package"), e.get("subpath")) for e in entry_files
                       if e.get("subpath") not in ROOT_SUBPATHS and "*" not in str(e.get("subpath"))
                       and e.get("in_scope") is not False}

    # A scope.include glob that matches no file: the brief predates the
    # source, so a root export defined in a file no glob covers comes back,
    # unless the brief excludes or declined that file.
    declined = [path for path, action in ((brief or {}).get("amendments") or {}).items()
                if action in DECLINED_ACTIONS]
    restored = [o for o in outside if unmatched and o.get("entry") in root_files
                and isinstance(o.get("name"), str) and isinstance(o.get("file"), str) and o["file"]
                and not any(glob_match(_norm(o["file"]), g)
                            for g in scope["include"] + scope["exclude"] + declined)]
    restored_at = {(o["name"], o["file"]): o.get("line") for o in restored}
    outside = [o for o in outside if (o.get("name"), o.get("file")) not in restored_at]

    outside_keys = {(o.get("name"), o.get("file")) for o in outside}
    index = {(e.get("export_name"), e.get("source_file")): e
             for e in data.get("exports") or [] if isinstance(e, dict)}
    records, nested_records = [], []
    # The names an aliased record's defining file gives it, for the other declarations (#918).
    aliases: dict[str, set[str]] = {}
    for info in public:
        name, file = info["name"], info.get("file")
        if (name, file) in outside_keys:
            continue
        if (name, file) in restored_at:
            # No recipe reads a file out of scope, so its kind is unknown: the
            # name carries the file and line of its outside_scope row.
            records.append(_record(name, None, file, restored_at[(name, file)], None, "restored"))
            continue
        # An aliased re-export (`export { Options as Config }`) is recorded
        # under the name its defining file gives it, `local`.
        local = info.get("local")
        if isinstance(local, str) and local and local != name:
            aliases.setdefault(name, set()).add(local)
        found = index.get((local or name, file)) or index.get((name, file))
        kind = found.get("export_type") if found else None
        line, signature_line = _declared_at(found) if found else (info.get("line"), None)
        (nested_records if info.get("entry") in nested else records).append(
            _record(name, None if kind == "re-export" else kind, file, line, signature_line, "extraction"))

    # Every declaration exports[] records, a re-export row left out (it declares nothing): the other
    # declarations of a surface name come from these (#918).
    declarations = []
    for e in data.get("exports") or []:
        if not isinstance(e, dict) or e.get("export_type") == "re-export":
            continue
        name, file = e.get("export_name"), e.get("source_file")
        if isinstance(name, str) and name and isinstance(file, str) and file.strip():
            line, signature_line = _declared_at(e)
            declarations.append({"exportName": name, "kind": e.get("export_type"), "file": file, "line": line,
                                 "signatureLine": signature_line})

    # The umbrella ratio reads the public rows alone: an other definition is no root barrel name there.
    root_names = [p for p in _members_in_place(rows["public"]) if p.get("entry") in root_files]
    reexported = [p for p in root_names if p.get("via") not in (None, "declaration")]

    sets = {}
    if subpath_files:
        sets["subpaths"] = sorted({p["name"] for p in public if p.get("entry") in subpath_files})
    if root_files:
        sets["root"] = sorted({p["name"] for p in public if p.get("entry") in root_files})

    return {
        "records": records,
        "nestedRecords": nested_records,
        "declarations": declarations,
        "aliases": aliases,
        "sets": sets,
        "outside": [_outside_row(o, scope) for o in outside],
        "nested": [{"entry": top, "within": nested[top], "names": nested_names[top]} for top in sorted(nested)],
        "staleScope": {"unmatchedInclude": unmatched, "unmatchedTierAInclude": unmatched_tier_a,
                       "restored": [{"name": o["name"], "file": o["file"], "line": o.get("line")}
                                    for o in sorted(restored, key=lambda o: (o["name"], o["file"]))]},
        "gaps": [{"name": g.get("name"), "file": g.get("file"), "line": g.get("line")} for g in gaps],
        "scope": scope,
        "scopeType": recorded.get("type") if isinstance(recorded.get("type"), str) else None,
        "umbrella": {
            "entries": sorted(f for f in root_files if f),
            "names": len(root_names),
            "reexported": len(reexported),
            "ratio": round2(len(reexported) / len(root_names)) if root_names else None,
            "umbrella": bool(root_names) and len(reexported) / len(root_names) > UMBRELLA_RATIO,
        },
        # The in-scope subpaths the `subpaths` set reads (None when there is no such set).
        "subpathEntries": len(subpath_entries) if subpath_files else None,
        "extraction": extraction,
    }


def from_quick(data: dict) -> list[dict]:
    exports = data.get("exports")
    if not isinstance(exports, list):
        raise InputError("--quick is not skf-extract-public-api.py --mode quick output (no exports list)")
    return [_record(e["name"], e.get("type"), e.get("defined_in") or e.get("source_file"), None, None, "quick")
            for e in exports if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]]


def from_per_file(path: str) -> tuple[list[dict], list[str]]:
    """(the records of one per-file result, its schema breaches)."""
    scorer = _sibling("score-signatures.py")
    try:
        text = Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read --per-file {path}: {exc}") from exc
    results, errors = scorer.parse_result_text(text, Path(path).name)
    if errors:
        return [], errors
    records = []
    for result in results:
        types = set(result.get("types_found") or [])
        for name in sorted(set(result.get("exports_found") or []) | types):
            if name:
                records.append(_record(name, "type" if name in types else None, result["file"], None, None,
                                       "per-file"))
    return records, []


def fold_names(names: list[str], prefixes: list[str], keep: set[str],
               tallied: set[str] | None = None) -> tuple[dict[str, str], dict]:
    """({variant: base}, the fold tally of `tallied`, else of every name) under the canonicalization rules."""
    present = set(names)
    variants: dict[str, str] = {}
    tally = {"_def": 0, "_exact": 0, FOLD_PREFIX: 0, "other": 0}
    for name in sorted(present):
        if name in keep:
            continue
        rule, base = None, None
        for suffix in FOLD_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                rule, base = suffix, name[: -len(suffix)]
                break
        if rule is None and name.startswith(FOLD_PREFIX) and len(name) > len(FOLD_PREFIX):
            rule, base = FOLD_PREFIX, name[len(FOLD_PREFIX):]
        if rule is None:
            for prefix in prefixes:
                if prefix and name.startswith(prefix) and name[len(prefix):] in present:
                    rule, base = "other", name[len(prefix):]
                    break
        if rule is not None:
            variants[name] = base
            if tallied is None or name in tallied:
                tally[rule] += 1
    return variants, tally


def _over(clause: str, sets: dict, name: str, step: int | None, rebuild: str | None = None) -> dict:
    """The barrel branch over set `name`, the `all` set when the surface lacks it."""
    present = name in sets
    return {"clause": clause, "branch": "barrel", "surfaceSet": name if present else "all", "ladderStep": step,
            "absentSet": None if present else name, "rebuild": rebuild}


def pick_denominator(sets: dict, stats_eff: int | None, deflation_fires: bool, barrel: str | None, arms: dict,
                     scope_type: str | None, skill_type: str | None, monorepo: bool, pattern_reference: bool,
                     curated: bool, source_read: bool, set_trusted: bool = False) -> dict:
    """The Source API Surface Definition's clause for a skill, with the branch
    and the name set reconcile-coverage.py and score-signatures.py read, the
    entry points' state it was picked by and, on the scalar branch, whether
    it counts that set (`set_trusted`: each name at its defining file, read
    whole; see "Denominator" above)."""
    picked = _pick(sets, stats_eff, deflation_fires, barrel, arms, scope_type, skill_type, monorepo,
                   pattern_reference, curated, source_read)
    counted = (set_trusted and picked["surfaceSet"] not in (None, "all")) if picked["branch"] == "scalar" else None
    return {**picked, "barrel": barrel, "setCounted": counted}


def _pick(sets: dict, stats_eff: int | None, deflation_fires: bool, barrel: str | None, arms: dict,
          scope_type: str | None, skill_type: str | None, monorepo: bool, pattern_reference: bool,
          curated: bool, source_read: bool) -> dict:
    if skill_type == "stack":
        return {"clause": "stack", "branch": "stack", "surfaceSet": None, "ladderStep": None, "absentSet": None,
                "rebuild": None}
    multi = bool(arms.get("multi_subpath_exports"))
    if (not monorepo and barrel != "barrel" and scope_type not in NOT_PATTERN_REFERENCE
            and not (multi and scope_type == "public-api")
            and (pattern_reference or (barrel == "no-entry-point" and not multi))):
        if "tier_a_include" in sets:
            return _over("pattern-reference", sets, "tier_a_include", None)
        # The canonicalized provenance map: a surface read from the source is built again from the map alone.
        return _over("pattern-reference", sets, "all", None, "provenance-fold" if source_read else None)
    if barrel == "empty-barrel":
        return _over("empty-barrel", sets, "scope.include", None)
    if monorepo and curated and scope_type != "full-library":
        clause = "stratified-scope"
    elif scope_type == "specific-modules" and not monorepo:
        clause = "specific-modules"
    elif multi and not monorepo and scope_type in ("full-library", "public-api"):
        clause = "multi-entry"
    else:
        return _over("standard-barrel", sets, "all", None)
    ladder = CLAUSE_LADDERS[clause]
    for step, rung in enumerate(ladder, 1):
        if rung != "scalar":
            if rung in sets or step == len(ladder):
                return _over(clause, sets, rung, step)
        elif stats_eff:
            # A stored 0 is no denominator: the next rung.
            if deflation_fires:
                # The ladder's tier A rung when it has one and the surface has the set, else scope.include.
                rung = "tier_a_include" if "tier_a_include" in ladder and "tier_a_include" in sets else "scope.include"
                return _over(clause, sets, rung, step)
            scored = next((name for name in ("tier_a_include", "scope.include") if name in sets), "all")
            return {"clause": clause, "branch": "scalar", "surfaceSet": scored, "ladderStep": step,
                    "absentSet": None, "rebuild": None}
    raise AssertionError(f"the {clause} ladder ends on a set")


def surface(args: argparse.Namespace) -> dict:
    records: list[dict] = []
    sets: dict[str, list[str]] = {}
    warnings: list[str] = []
    out: dict = {"candidates": None, "guards": None, "denominator": None, "state2": None, "canonical": None,
                 "extraction": None, "extractionGaps": [], "excluded": {"outsideScope": [], "nestedEntries": []}}

    meta = _object(args.metadata, "--metadata") if args.metadata else None
    provenance = _object(args.provenance, "--provenance") if args.provenance else None
    brief = read_brief(args.brief) if args.brief else None
    language = (brief or {}).get("language")
    if not language and meta is not None and isinstance(meta.get("language"), str):
        language = meta["language"]
    stats = meta.get("stats") if isinstance(meta, dict) and isinstance(meta.get("stats"), dict) else {}
    stats_eff = _count(stats.get("effective_denominator"))

    extracted = None
    if args.extraction:
        data = _object(args.extraction, "--extraction")
        extracted = from_extraction(data, language, brief)
        records += extracted["records"]
        sets.update(extracted["sets"])
        out["extraction"] = extracted["extraction"]
        out["extractionGaps"] = extracted["gaps"]
        out["excluded"] = {"outsideScope": extracted["outside"], "nestedEntries": extracted["nested"]}
        warnings += [f"{Path(args.extraction).name}: {w}" for w in data.get("warnings") or [] if isinstance(w, str)]
    quick_outputs = []
    for path in args.quick or []:
        data = _object(path, "--quick")
        quick_outputs.append(data)
        records += from_quick(data)
        warnings += [f"{Path(path).name}: {w}" for w in data.get("warnings") or [] if isinstance(w, str)]
    violations: list[str] = []
    for path in args.per_file or []:
        found, errors = from_per_file(path)
        records += found
        violations += errors
    if violations:
        raise SchemaError(violations)
    records += [_record(name, None, None, None, None, "by-eye") for name in args.name or [] if name]

    # A surface read from the source takes no name from the provenance map or
    # metadata.json: they are only the baselines of the candidates and guards.
    source_read = extracted is not None or bool(args.quick) or bool(args.per_file)
    if not source_read and (provenance is not None or meta is not None):
        named = [e for e in _entries(provenance)
                 if isinstance(e.get("export_name"), str) and e["export_name"]
                 and METHOD_SEPARATOR not in e["export_name"]]
        prov_names = sorted({e["export_name"] for e in named})
        exports = meta.get("exports") if meta is not None else None
        meta_names = sorted({n for n in (_export_name(e) for e in exports) if n}) if isinstance(exports, list) else []
        base_of: dict[str, str] = {}
        # A map whose raw count is the stored effective_denominator is already canonical: no fold.
        skipped = bool(args.fold) and provenance is not None and stats_eff == len(prov_names)
        if args.fold:
            # One fold over both lists, so a variant folded out of the map
            # never comes back through metadata.json.
            base_of, tally = fold_names(sorted(set(prov_names) | set(meta_names)), args.fold_prefix or [],
                                        set(args.keep or []), tallied=set(prov_names))
            if skipped:
                base_of, tally = {}, dict.fromkeys(tally, 0)
            if provenance is not None:
                canonical = sorted({base_of.get(n, n) for n in prov_names})
                out["canonical"] = {
                    "raw": len(prov_names),
                    "canonical": len(canonical),
                    "folded": tally,
                    "variants": {n: base_of[n] for n in prov_names if n in base_of},
                    "skipped": skipped,
                    "residual": None if stats_eff is None else len(canonical) - stats_eff,
                    "summary": (f"Provenance-map canonicalization: {len(prov_names)} raw entries → "
                                f"{len(canonical)} canonical bases ({len(prov_names) - len(canonical)} "
                                f"bookkeeping variants folded: _def×{tally['_def']}, _exact×{tally['_exact']}, "
                                f"a11y_×{tally[FOLD_PREFIX]}, other×{tally['other']})"
                                + (": the raw count equals `stats.effective_denominator`, so the map is already "
                                   "canonical" if skipped else "")),
                }
        seen = set()
        for e in named:
            name = base_of.get(e["export_name"], e["export_name"])
            if name in seen:
                continue
            seen.add(name)
            records.append(_record(name, e.get("export_type"), e.get("source_file"), e.get("source_line"),
                                   None, "provenance"))
        meta_bases = sorted({base_of.get(n, n) for n in meta_names})
        records += [_record(n, None, None, None, None, "metadata") for n in meta_bases]
        if seen and meta_bases:
            out["state2"] = {
                "provenanceCount": len(seen),
                "metadataCount": len(meta_bases),
                "unionCount": len(seen | set(meta_bases)),
                "metadataOnly": sorted(set(meta_bases) - seen),
            }

    sets["all"] = sorted({r["name"] for r in records})
    # A nested Python top's records count in the scope sets, never in `all`.
    records += extracted["nestedRecords"] if extracted is not None else []
    # A restored name, or one exports[] gives no kind at its file such as an extraction gap, takes its kind from the
    # provenance map at its file (#913, #1020): no set, count or guard changes.
    if provenance is not None:
        _provenance_kinds(records, provenance)
    records.sort(key=lambda r: (r["name"], str(r["file"] or ""), r["origin"]))

    # The scope: the one the extractor recorded, else the brief's.
    scope = extracted["scope"] if extracted is not None and any(extracted["scope"].values()) else None
    if scope is None:
        scope = brief["scope"] if brief is not None else _scope(None, None, None)
    # Each other declaration of a surface name (#918), for the signature plan alone: no record, set or count. Only
    # a runner extraction looks for them, so with no extraction, or one the per-file scan replaces, the list is
    # null (never looked for), not [] (none found), and the split-body Source settles no pair on it (#1026).
    others = (other_declarations(records, extracted["declarations"], extracted["aliases"], scope["exclude"])
              if extracted is not None and not extracted["extraction"]["fallback"]["needed"] else None)
    # A tier A glob the runner lists as matching no file counts no name, and
    # so does one whose folder or file differs from every scope.include
    # glob's before any `*` or `?` (`gen/**` beside `src/**`) or one a
    # scope.exclude glob covers segment by segment (`src/gen/**` beside an
    # exclude of `src/gen/**`), whatever the tree holds: the set comes from
    # the other globs, over the names whose file a scope.include glob matches
    # too (any file with none), so a restored name is in no set. A tier A
    # list that counts no name (every glob stale, or matching only excluded
    # files, files scope.include leaves out or files that define no name)
    # narrows nothing: there is no set.
    stale_tier_a = set(extracted["staleScope"]["unmatchedTierAInclude"]) if extracted is not None else set()
    tier_a = [g for g in scope["tier_a_include"] if g not in stale_tier_a
              and not (scope["include"] and all(_apart(g, i) for i in scope["include"]))
              and not any(_inside(g, e) for e in scope["exclude"])]
    filed = [r for r in records if r["file"]]
    # The files each scope set's names sit at, for the Denominator annotations' file counts.
    set_files: dict[str, list[str]] = {}
    if filed and scope["include"]:
        sets["scope.include"] = matching(filed, scope["include"], scope["exclude"])
        set_files["scope.include"] = matching_files(filed, scope["include"], scope["exclude"])
    in_include = [r for r in filed if not scope["include"]
                  or any(glob_match(_norm(r["file"]), g) for g in scope["include"])]
    tier_a_names = matching(in_include, tier_a, scope["exclude"]) if tier_a else []
    if tier_a_names:
        sets["tier_a_include"] = tier_a_names
        set_files["tier_a_include"] = matching_files(in_include, tier_a, scope["exclude"])

    # The clause: an extraction's entry-point status (one the per-file scan replaces says only that it found no
    # entry point), else a quick output's (an export is a barrel; none, and no warning, an empty one), else what
    # the workflow read (--barrel).
    barrel = None
    summary = extracted["extraction"] if extracted is not None else None
    if summary is not None and not summary["fallback"]["needed"]:
        barrel = summary["entryPointStatus"]
    elif summary is not None and summary["entryPointsFound"] is False:
        barrel = "no-entry-point"
    elif quick_outputs:
        barrel = "barrel" if any(q["exports"] for q in quick_outputs) else (
            None if any(q.get("warnings") for q in quick_outputs) else "empty-barrel")
    if barrel is None and args.barrel:
        barrel = BARREL_FLAG[args.barrel]
    recorded_type = extracted["scopeType"] if extracted is not None else None
    meta_type = meta.get("scope_type") if isinstance(meta, dict) and isinstance(meta.get("scope_type"), str) else None
    arms = summary["arms"] if summary is not None else {}
    # The extraction's verdict, the rule Create Skill stores the count by, else the workflow's judgment.
    curated = summary["curatedSubset"] if summary is not None and summary["curatedSubset"] is not None \
        else bool(args.curated_subset)
    scope_type = (brief or {}).get("type") or recorded_type or meta_type
    skill_type = meta.get("skill_type") if isinstance(meta, dict) else None
    monorepo = bool(args.monorepo or arms.get("monorepo"))
    # The clause alone (no stored count, no guard): only a clause whose ladder holds a stored count measures it
    # against the tier A set.
    clause = _pick(sets, None, False, barrel, arms, scope_type, skill_type, monorepo,
                   bool(args.pattern_reference_intent), curated, source_read)["clause"]
    swap = False
    # Each name sits at the file that defines it (a runner extraction, the fallback scan, quick output whose every
    # name carries its defined_in); a name read by eye, or a quick name with no defined_in, sits at its entry file.
    runner = extracted is not None and not extracted["extraction"]["fallback"]["needed"]
    quick_traced = (bool(quick_outputs) and not args.per_file and not args.name
                    and all(isinstance(e.get("defined_in"), str) and e["defined_in"]
                            for q in quick_outputs for e in q["exports"] if isinstance(e, dict)))
    defining = runner or bool(args.fallback_scan) or quick_traced
    # The scalar branch counts its scope set only from such names read whole: an incomplete or truncated
    # extraction can miss names (#791, #792).
    whole = summary is None or (summary["status"] != "incomplete" and not summary["truncated"])

    if extracted is not None or brief is not None or meta is not None:
        include_union = len(sets["scope.include"]) if "scope.include" in sets else len(sets["all"])
        extraction = extracted["extraction"] if extracted is not None else {}
        out["candidates"] = {
            "statsEffectiveDenominator": stats_eff,
            "tierAIncludeUnion": len(sets["tier_a_include"]) if "tier_a_include" in sets else None,
            "scopeIncludeUnion": len(sets["scope.include"]) if "scope.include" in sets else None,
            "tierAIncludeFiles": len(set_files["tier_a_include"]) if "tier_a_include" in sets else None,
            "scopeIncludeFiles": len(set_files["scope.include"]) if "scope.include" in sets else None,
            "subpathUnion": len(sets["subpaths"]) if "subpaths" in sets else None,
            "subpathEntries": extracted["subpathEntries"] if extracted is not None else None,
            "rootBarrel": len(sets["root"]) if "root" in sets else None,
            "extractorEffectiveDenominator": extraction.get("effectiveDenominator"),
            "extractorBasis": extraction.get("effectiveDenominatorBasis"),
        }
        # With an extraction or the fallback scan's results (each at the file
        # that defines its names), no tier A set is no tier A list; otherwise
        # the globs left in the list decide (a name read by eye at Quick tier
        # or State 4, and a quick name with no defined_in, carries its entry
        # file, not the file that defines it).
        no_tier_a = ("tier_a_include" not in sets if extracted is not None or args.fallback_scan
                     else not tier_a)
        # A clause whose ladder holds a stored count checks it against the tier A set, both ways, when each name
        # sits at the file that defines it (a runner extraction, the fallback scan, quick output whose every name
        # carries its defined_in): Create Skill stores the runner's tier A count, so one beyond the threshold is
        # stale (#813). A name read by eye, or a quick name with no defined_in, sits at its entry file.
        tier_a_basis = defining and clause in CLAUSE_LADDERS and "tier_a_include" in sets
        rederived = len(sets["tier_a_include"]) if tier_a_basis else include_union
        basis = "tier_a_include" if tier_a_basis else "scope.include" if "scope.include" in sets else "all"
        deflation = {"applicable": source_read and stats_eff is not None, "basis": basis,
                     "effectiveDenominator": stats_eff, "rederived": rederived if source_read else None, "pct": None,
                     "fires": False}
        if deflation["applicable"] and stats_eff:
            deflation["pct"] = round2((rederived - stats_eff) / stats_eff * 100)
            deflation["fires"] = (abs(deflation["pct"]) > DEFLATION_PCT if tier_a_basis
                                  else no_tier_a and deflation["pct"] > DEFLATION_PCT)
        elif deflation["applicable"]:
            # A stored 0 is deflation, not a denominator, once a name is re-derived.
            deflation["fires"] = (tier_a_basis or no_tier_a) and rederived > 0
        # An incomplete extraction can miss tier A names: a tier A set below the stored count is drift to report,
        # not a denominator to take.
        incomplete = runner and extracted["extraction"]["status"] == "incomplete"
        swap = deflation["fires"] and not (incomplete and tier_a_basis and (deflation["pct"] or 0) < 0)
        entry_count = len(_entries(provenance)) if provenance is not None else 0
        inflation = {"applicable": source_read and no_tier_a and bool(scope["include"]) and entry_count > 0,
                     "scopeIncludeUnion": include_union if scope["include"] else None,
                     "provenanceEntries": entry_count if provenance is not None else None,
                     "pct": None, "fires": False}
        if inflation["applicable"]:
            inflation["pct"] = round2((include_union - entry_count) / entry_count * 100)
            inflation["fires"] = inflation["pct"] > INFLATION_PCT
        stale_scope = {"applicable": extracted is not None and bool(scope["include"] or scope["tier_a_include"]),
                       "fires": False, "unmatchedInclude": [], "unmatchedTierAInclude": [], "restored": []}
        if stale_scope["applicable"]:
            stale_scope.update(extracted["staleScope"])
            stale_scope["fires"] = bool(stale_scope["unmatchedInclude"] or stale_scope["unmatchedTierAInclude"])
        out["guards"] = {
            "deflation": deflation,
            "inflation": inflation,
            "staleScope": stale_scope,
            "tierAInclude": list(scope["tier_a_include"]),
            "umbrella": extracted["umbrella"] if extracted is not None else dict(NO_UMBRELLA),
            "thresholds": {"deflationPct": DEFLATION_PCT, "inflationPct": INFLATION_PCT,
                           "umbrellaRatio": UMBRELLA_RATIO},
        }

    out["denominator"] = pick_denominator(sets, stats_eff, swap, barrel, arms, scope_type, skill_type, monorepo,
                                          bool(args.pattern_reference_intent), curated, source_read,
                                          defining and whole)

    return {
        "inputs": {
            "extraction": args.extraction, "quick": args.quick or [], "perFile": args.per_file or [],
            "names": args.name or [], "provenance": args.provenance, "metadata": args.metadata,
            "brief": args.brief, "fold": bool(args.fold),
        },
        "exports": records,
        "otherDeclarations": others,
        "sets": sets,
        **out,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_census(args: argparse.Namespace) -> dict:
    return census(args.skill_dir)


def _cmd_floor(args: argparse.Namespace) -> dict:
    return floor(args.skill_dir)


def _cmd_metadata(args: argparse.Namespace) -> dict:
    meta = _object(args.metadata, "--metadata")
    provenance = _object(args.provenance, "--provenance") if args.provenance else None
    return metadata_inputs(meta, provenance)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load-coverage-inputs",
        description="The counts, name sets and denominator candidates coverage-check reads, from files.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("census", help="count the citation forms: is the skill docs-only?")
    p.add_argument("--skill-dir", required=True, help="the skill package: SKILL.md and references/")
    p.add_argument("--output", help="write the result to this file and print only its summary")
    p.set_defaults(func=_cmd_census)

    p = sub.add_parser("floor", help="the names the skill documents in a fixed form, which the inventory keeps")
    p.add_argument("--skill-dir", required=True, help="the skill package: SKILL.md and references/")
    p.add_argument("--output", help="write the result to this file and print only its summary")
    p.set_defaults(func=_cmd_floor)

    p = sub.add_parser("metadata", help="the metadata.json and provenance-map counts")
    p.add_argument("--metadata", required=True, help="the skill's metadata.json")
    p.add_argument("--provenance", help="the provenance map, when there is one")
    p.add_argument("--output", help="write the result to this file and print only its summary")
    p.set_defaults(func=_cmd_metadata)

    p = sub.add_parser("surface", help="the enumerated source surface, its name sets and candidates")
    p.add_argument("--extraction", help="skf-extract-public-api.py --mode full output")
    p.add_argument("--quick", action="append", help="skf-extract-public-api.py --mode quick output (repeatable)")
    p.add_argument("--per-file", action="append", help="a subagent per-file result (repeatable)")
    p.add_argument("--fallback-scan", action="store_true",
                   help="the --per-file results are the fallback scan's, each at the file that defines its "
                        "names: as with --extraction, no tier_a_include set is no tier A list, so the deflation "
                        "and inflation guards run; without either, a tier_a_include glob keeps them off unless "
                        "its folder or file differs from every scope.include glob's before any wildcard "
                        "(gen/** beside src/**) or a scope.exclude glob covers it segment by segment "
                        "(src/gen/** beside an exclude of src/gen/**)")
    p.add_argument("--name", action="append", help="a name read by eye whose file is not known (repeatable)")
    p.add_argument("--provenance", help="the provenance map: its named exports")
    p.add_argument("--metadata", help="metadata.json: its exports[] names, stats and language")
    p.add_argument("--brief", help="the skill brief: its scope globs and language")
    p.add_argument("--fold", action="store_true", help="fold the provenance and metadata bookkeeping variants")
    p.add_argument("--fold-prefix", action="append", help="a renderer prefix to fold (repeatable)")
    p.add_argument("--keep", action="append", help="a variant that is a real export (repeatable)")
    p.add_argument("--monorepo", action="store_true",
                   help="the source is a monorepo (skf-detect-workspaces.py's is_monorepo)")
    p.add_argument("--pattern-reference-intent", action="store_true",
                   help="the brief's scope.notes flags pattern-reference intent (your judgment)")
    p.add_argument("--curated-subset", action="store_true",
                   help="with --monorepo: the brief's scope.include lists a curated subset rather than the full "
                        "workspace (your judgment; an extraction's counts.curated_subset wins)")
    p.add_argument("--barrel", choices=tuple(BARREL_FLAG),
                   help="the entry points as you read them, where no extraction or quick output tells: none (no "
                        "barrel file at any recognized entry-point path), empty (the primary one exports nothing) "
                        "or barrel")
    p.add_argument("--output", help="write the result to this file and print only its summary")
    p.set_defaults(func=surface)
    return parser


def _summary(cmd: str, result: dict, output: str) -> dict:
    """What a subcommand prints when --output holds its result: the fields the step decides on, under the keys the
    file gives them (a list as its length, a stack without its names), and the file's path as `output`. The surface's
    extractionGaps stay a list: coverage-check §2 reads each gap's file and line from the JSON it has in hand."""
    if cmd == "census":
        summary = {"docsOnly": result["docsOnly"], "localCitations": result["localCitations"]}
    elif cmd == "floor":
        summary = {"summary": result["summary"]}
    elif cmd == "metadata":
        stack = result["stack"]
        summary = {"skillType": result["skillType"], "inflationSignature": result["inflationSignature"],
                   "stack": {"basis": stack["basis"], "denominator": stack["denominator"]} if stack else None}
    else:
        extraction = result["extraction"]
        summary = {"exports": len(result["exports"]), "denominator": result["denominator"],
                   "extraction": ({key: extraction[key] for key in ("readByEye", "unread", "fallback")}
                                  if extraction else None),
                   "extractionGaps": result["extractionGaps"]}
    return {**summary, "output": output}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except SchemaError as exc:
        if args.output:
            Path(args.output).unlink(missing_ok=True)
        print(json.dumps({"valid": False, "violations": exc.violations}, indent=2))
        return 2
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        # The step reads the result from the file, so stdout gives only its summary and the path (#1040).
        result = _summary(args.cmd, result, args.output)
    print(json.dumps(result, indent=2))
    return 0


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
