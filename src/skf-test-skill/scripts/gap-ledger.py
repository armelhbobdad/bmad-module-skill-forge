#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF test-skill gap ledger: one typed JSON record per finding.

test-skill's hard gate (step-hard-gate.md) must see every Critical and High
finding before scoring, and update-skill must read every gap with its source
and remediation after a FAIL. Markdown written by the model serves neither:
the coverage section holds tables and counts, the coherence formats carry no
severity, and the Gap Entry Format was applied only in the report step, after
the gate. This script keeps the findings in a JSON ledger instead. Each stage
appends the gaps it finds, classified against the Gap Severity table in
scoring-rules.md when they are written; hard-gate.py counts the blocking ones,
and the Gap Report is rendered from the same records on every path.

Ledger file: `{forge_version}/test-findings-{run_id}.json`

  {
    "schema_version": 1,
    "run_id": "<run id from the file name>" | null,
    "stages": ["coverage-check", "coherence-check", ...],
    "records": [
      {
        "id": "GAP-001",               # assigned here, in append order
        "severity": "Critical" | "High" | "Medium" | "Low" | "Info",
        "category": "<slug from CATEGORIES>",
        "group": "Coverage" | "Coherence" | "Structural" | "Discovery" | "External",
        "title": "<one line>",
        "source": "<file:line or a section reference>",
        "remediation": "<exact action that fixes the gap>",
        "issue": "<what is wrong>",    # optional
        "export": "<export name>",     # optional
        "stage": "<the stage that appended it>"
      }
    ]
  }

`stages` lists every stage that appended, even with no records, so the gate
can tell a stage that found nothing from a stage that never ran. `group` is
derived from the category; callers never supply `id`, `group` or `stage`.

Subcommands:

  append --ledger <path> --stage <stage> [--input <file>]...
      Read records from each <file> in turn, or from stdin without --input:
      a JSON array, one record object, or {"records": [...]}. An empty array
      records the stage with no findings. Every record is validated first
      and nothing is written unless all are valid. A record equal to one
      already in the ledger (same severity, category, title, source and
      export) is not added again, so a stage that runs twice leaves one
      copy. Creates the ledger when it does not exist.
      Appends may overlap (parallel tool calls): each holds an exclusive
      lock on <ledger>.skf-lock from its read to its write, and another
      append waits for it (up to 30 s, then LEDGER_LOCKED), so no record an
      append reported is lost. The write is atomic: a temp file of its own
      beside the ledger, then a rename. The lock file is removed afterwards.
      Output: {"status": "ok", "ledger", "stage", "appended": [ids],
               "duplicates": [ids], "record_count"}

  append --ledger <path> --stage <stage> --from <kind> --input <file>...
         [--surface <file>] [--signatures <file>] [--numerator <file>]
         [--stale <file>] [--provenance <file>] [--inventory <file>]
         [--skill-dir <dir>] [--metadata <path>] [--served <family>]...
      Build the records from the result file a script wrote (see Adapters
      below) instead of reading them, then append them as above, with the
      same output. A gap a script finds is recorded with a fixed title,
      Source, `export` and remediation, so a rerun dedupes it. Each kind
      reads one --input (structure reads one or more) and only the options
      its entry names; any other option, or a file that does not hold the
      result its kind reads, is INVALID_INPUT and nothing is written.

Adapters (--from), each record classified by its Gap Severity row
(scoring-rules.md). `{meta}` is --metadata, the metadata.json path a record
cites (never read; default `metadata.json`):

  coverage  --input reconcile-coverage.py's result; --surface, --signatures,
            --numerator, --stale, --provenance, --inventory, --skill-dir,
            --metadata.
            Barrel branch: each `missing` name is a Medium `missing-export`
            gap `Missing export: {name}`, or a Medium `missing-type` gap
            `Missing type: {name}` when the --signatures result lists it in
            `missingTypes`; its Source is the file and line the --surface
            result's `exports[]` records for it, else `{meta}`. When the
            --surface result's `guards.inflation.fires`, its
            `denominator.surfaceSet` is `scope.include` and its
            `denominator.clause` is one whose ladder has a tier A rung
            (stratified-scope, multi-entry), the `missing` names are
            instead one Medium `denominator-inflation` gap `undocumented
            names in the inflated scope.include union` at its
            `inputs.brief` (else `skill-brief.yaml`), beside the guards
            kind's gap at that brief: its issue gives the union's size
            (`guards.inflation.scopeIncludeUnion`) and lists the first 50
            names, each marked a type when the --signatures result lists
            it in `missingTypes` and with the file and line `exports[]`
            records for it, then how many more, and its remediation
            corrects the denominator as the guard's gap says, then re-runs
            Test Skill. Each `stale`
            name the --stale result (classify-stale) marks `fabricated` is a
            Critical `fabricated-signature` gap `Fabricated signature:
            {name}` at its `source` (one with no `source` is INVALID_INPUT,
            never a lesser gap), unless one of its `entries` cites the line
            of an `unresolvedStars` star (below, #1070), which reads it as
            not fabricated. One whose `defined_at` (where the source
            declares it) is a Python or TS/JS `file:line` is a documented
            extra when its name has no dot and the --surface result was
            built from an extraction that read the whole scope (an
            `extraction` object, not `no-ast-grep`, `truncated` or
            `fallback.needed`: only such an extraction fills
            `excluded.outsideScope`, the names a brief scoped out) and its
            `excluded.outsideScope` list does not list it (a row of a
            namespace's member named like its namespace, whose `namespace`
            is its `name`, #969, does not count unless its `file` is the
            one the gap would be at): an Info `observation` gap
            `Documented extra: {name}` at `defined_at`. With no
            `defined_at`, a homonym (its `declared_in`
            lists several declaring files) is one too, with --skill-dir,
            when its forms' own citations (at their inventory `at`), else the
            skill's on lines naming it, cite exactly one of those files: the
            gap is at that file's `declared_in` item. Its forms' own are the
            `[AST:]` and `[SRC:]` citations validate-inventory.py's
            form_citations gives the form at each --inventory `at` of an
            entry of the name that is no `method` (one with no `:L<n>` part
            included), with the name's other places in that file, as
            score-signatures.py's plan reads them, read first since a
            line that writes the name only as a type argument of another
            export cites that export's file (#1077); the issue then names
            the forms that cite it ("its form at ... cites only", "its
            forms at ... and ... cite only"). The skill's, read
            when those cite no single file between them or there is no such
            `at` (the issue then says "the skill cites only"), are its
            `[AST:path:L<n>]` and `[SRC:path:L<n>]`
            citations on the lines of SKILL.md and references/**/*.md that
            name it (outside the citations), or on the next non-blank line
            after one that is not a table row outside a fenced block (a
            row's own citations are in its cells, the next row documents
            another export, #1066), read with the forms' own, which that
            scan misses after a closing fence, on a comment line above or
            with no `:L<n>`, so forms citing two of the files keep it
            Medium. A package
            `<dir>/NAME/__init__.py` cited with only modules named NAME
            directly in its folder (`<dir>/NAME/NAME.py` or `.pyi`) counts,
            in either reading, as that one file, the package `<dir>.NAME`
            resolves to (#1012); any other two cited, or none, in both
            readings leave it Medium. The documented
            extra's remediation asks no
            change (update-skill never routes it) and says whether signature
            scoring compared its documented signature (a name the
            --signatures result lists in `comparedNames`). `excluded` is
            read once a stale name that is not fabricated (one a map
            entry's star lifts included) needs it, and a
            malformed one is then INVALID_INPUT. Any other is a Medium `stale-documentation` gap
            `Stale documentation: {name}` at the line that documents the
            name (with --skill-dir), else `SKILL.md`. That line is the
            first that writes it as an export, the first tier that holds
            the name winning: (1) its first origin in the documented
            inventory's floor (load-coverage-inputs.py floor); (2) a
            heading, or the first cell of a table whose header's first
            cell names exports (floor's table headers, a compound
            `Component / Props` one included), whose text is the
            name or holds a code span floor reads as the name, or whose
            text or code span, cut as floor cuts a name, is a module path
            whose last segment is the name
            (`cognee.run_migrations()` for `run_migrations`, #1041); (3) a
            line whose inline code span is the name, the name directly
            followed by `(`, or a usage form that calls it (an assignment,
            `await`, `new` or a module path, then the name directly followed
            by `(`: `await cognee.add(data)`, #1041); (4) a line whose
            code span, cut at a call's `(`, is a module path whose last
            segment is the name, `cognee.exceptions` for `exceptions`
            (#1011), a module path being a dotted path of plain identifiers
            whose first segment is a module the skill's fenced code imports
            (`import cognee`, `from cognee.x import y`, `import a.b as c`,
            `import * as ns from`), never a receiver's or a type's path
            (`client.connect(url)`, `Client.connect`); (5) a column-0
            declaration of it in a fenced
            block of a language floor's `_declared_names` reads (JS/TS,
            Python, Rust, Go), cited or not, so a def an example writes
            under the name is cited only when nothing above documents it;
            (6) a line of a fenced block that holds the name as a whole
            quoted string (`"name"` or `'name'`), such as an `__all__` item.
            Tiers 2 to 6 read SKILL.md, then every .md file under
            references/, subfolders included, in path order, outside the
            frontmatter (2 to 4 outside fenced code and HTML comments, 5
            and 6 inside a fence outside an HTML comment and a data block
            (json, yaml...)); within a tier the first file, then its lowest
            line, wins. A bare word, a span that holds the name among other
            words (`uitripled add`), or a quoted string outside a fence or
            holding other words too (`"add x"`) documents nothing, and so
            does a sentence of a heading or a prose block that says the
            skill does not cover a name (`out of scope for this skill` or
            `not covered here`, any case, outside its code spans): none of
            its spans or text keys tiers 2 to 4. A sentence ends at `.`,
            `!` or `?` before whitespace, or at a table row's
            unescaped `|`, never inside a code span, and runs across a
            block's lines, so the line's other sentences and the row's other
            cells still document a name (#1080). With no
            such line, or without --skill-dir, the line that documents it
            is the first `at` the --inventory result (validate-inventory.py,
            which keeps an `at` only on a line that writes the name) gives
            an entry of the name that is no `method`: SKILL.md's, then the
            first file in path order, then its lowest line (#1006). With
            none, the Source is `SKILL.md`. Each such `at` of the name is
            also one of a homonym's forms, whose own citations pick its
            declaring file first (#1077).
            An --inventory that is no object
            with an `exports` list is INVALID_INPUT.
            Floor's InputError (no SKILL.md, or a top-level file it cannot
            read or decode) leaves tier 1 empty, and a skill file that
            cannot be read leaves tiers 2 to 6 empty. One whose
            `excluded.outsideScope` row says the brief scopes its file out
            (`excludeGlob`, the `scope.exclude` glob that matches it, or
            `outsideInclude`, no `scope.include` glob covering it), unless
            that row is a namespace's member named like its namespace (its
            `namespace` is its `name`, #969) whose `file` is not the one a
            documented extra's gap would be at, has its own issue, naming the
            entry point and the file and line, and remediation: to keep the
            documentation, narrow that exclude glob (a removal needs a
            `demoted-exclude` amendment) or widen `scope.include`, else
            remove it. A row the
            brief does not explain keeps the wording above. Any other with
            no `defined_at` (every name without --stale), with --skill-dir,
            whose skill citations on a line naming it (as a homonym's
            fallback reads them) cite a file the --surface result's
            `unresolvedStars` lists
            (an `export *` from another package no script resolves, #1005),
            or, with or without --skill-dir, one of whose `entries` has a
            `star` (the module classify-stale read in the `export *` at its
            cited line) that a star of its file (as citations compare it)
            names, matched by file and module and never by line (#1070),
            is an Info `observation` gap `Not checked by script: {name}
            (another package's export *)` (so that the Deep tier's
            `Not checked by script: {name}`, which score-signatures.py
            records from a signature judge's `doc_errors`, stays its own
            gap) at
            the line that documents the name, else `SKILL.md`: its issue and
            remediation name each such statement and its file, and each
            star an entry cites that no skill citation gives, as `its
            provenance map cites it at` the statement, at the entry's file
            and line, and the
            remediation asks no change unless that package lacks the name.
            A skill citation alone never lifts a fabricated name.
            A missing or malformed `unresolvedStars` counts as empty. Every
            stale name's issue (fabricated, documented extra, not checked,
            stale documentation or scoped out) opens with the line that
            documents it, as
            `file:line` (with --skill-dir or --inventory), else with `the
            skill`, whatever its Source. Scalar and stack branches: a
            `missingCount` above 0 is one Medium `missing-export` gap
            `{missingCount} of {denominator} exports not documented` at
            `{meta}`, except that a scalar count taken from the verified
            numerator (`numeratorSource` `verified`) is replaced by one
            `Missing export: {name}` gap per --numerator `absent` name, at
            the first --provenance entry of that name, else `{meta}`. A
            scalar result that counts its set (`numeratorSource` `surface`)
            records the `missing` names it lists in place of the count gap,
            as the barrel branch does (the inflated-union summary gap
            under the same gate included), and, when `missingCount` exceeds
            them, one Medium `missing-export` gap `{residual} of
            {denominator} exports not documented beyond the {surfaceSet}
            set` at `{meta}`. A scalar result with `staleApplicable` true
            records its `stale` names as the barrel branch does. Every
            per-name gap carries `export`.
  guards    --input load-coverage-inputs.py's surface result; --metadata.
            `guards.deflation.fires` is a Medium `metadata-drift` gap at
            `{meta}` (else the result's `inputs.metadata`): on the
            `tier_a_include` basis (`guards.deflation.basis`) titled
            `denominator drift: ...`, giving the tier A count, the pct and
            the stored count, asking to recount by re-running Create Skill
            (which stores the runner's count only when
            `effective_denominator_decision.store` holds and `scope.notes`
            documents the stratification, and otherwise drops the stored
            count) and naming what `denominator` counts until then (its
            `surfaceSet`, or the stored count on the scalar branch); else
            `denominator deflation: ...`. `guards.inflation.fires` is a
            Medium `denominator-inflation` gap at the result's
            `inputs.brief` (else `skill-brief.yaml`), whose remediation adds
            or edits `scope.tier_a_include`, listing the files rather than
            the root barrel when `guards.umbrella.umbrella` is true. When
            both fire on the `scope.include` basis, both remediations name
            that one fix and say the `scope.include` union is itself
            inflated. No remediation sets `stats.effective_denominator` by
            hand, which Update Skill's recount drops.
            `guards.staleScope.fires` is one Medium `brief-scope-stale` gap
            at that brief, whose issue names each `unmatchedInclude` glob,
            each `restored` name with its file and each
            `unmatchedTierAInclude` glob. Its remediation asks to fix the
            stale globs and, when a name was restored, says a restored name
            stays only while an include glob matches no file, so each file
            defining one, listed once, takes a `scope.include` glob to keep
            its exports or a `scope.exclude` glob to leave them out (#1009).
            The `scope.include`-basis
            deflation gap and the inflation gap say the brief has no
            `scope.tier_a_include` when `guards.tierAInclude` lists no glob,
            that no glob matches a file when each is an
            `unmatchedTierAInclude` glob, and else that no glob counts a
            public name (a surface without
            `guards.tierAInclude` reads the `unmatchedTierAInclude` globs
            alone). A stored `stats.effective_denominator` of 0 (`pct`
            null) is written as a count against 0, not a percentage, and
            its fix re-runs Create Skill to count it again.
  numerator --input verify-declared-numerator.py's result; --metadata.
            `inflated` true is a High `numerator-inflation` gap at `{meta}`
            whose issue lists the `absent` names.
  metadata-coherence
            --input check-metadata-coherence.py's result; --metadata. Each
            `findings[]` entry, titled as it is and with its `detail` as the
            issue, at `{meta}`: Medium is a Medium `metadata-drift` gap, Info
            an Info `multi-denominator` gap. A `metadata-drift` gap whose
            title names the documented surface explains the `Type::method`
            entries its counts differ by; a barrel one sends the fix to
            Create Skill, which rebuilds `exports[]` from the source.
  provenance-line
            --input skf-verify-provenance-completeness.py verify's result;
            --stale.
            Each `stale[]` item, at its `{source_file}:{source_line}` with
            `export`, by `reason`: `line-not-definition` is a Low
            `provenance-line` gap `Provenance line is not the definition of
            {export_name}` when `definition_lines` holds a line, else an Info
            `provenance-unverified` gap `Provenance line not verified for
            {export_name}`, and its issue names the base of a `folded_to`
            variant. When the --stale result (classify-stale) marks
            `{export_name}` `aliased` with a `file:line` `defined_at`, that
            Info gap's issue and remediation name the alias at `defined_at`,
            and the remediation asks first to record the rename if no other
            entry already has its `export_name` (`export_name` the item's
            `renames`, else "a name a cited file declares", `reexported_as`
            the export), else to cite the alias, moving the citations either
            way; when `renames` is `default`, which the map keys on
            `export_name` and so holds once, it asks only to cite the alias.
            Else, when an entry of `{export_name}` in the --stale result has
            a `star` (the module of the `export *` at its cited line, #1070)
            that is no relative or absolute path and its file and line are
            the item's, that Info gap's issue and remediation say the line
            passes on that package's names, so no line of the file defines
            it, and ask no change unless that package lacks the name.
            A --stale result that is not a list is INVALID_INPUT.
            `file-missing` is a Low `provenance-line`
            gap `Provenance file is missing for {export_name}`;
            `line-out-of-bounds` a Low `provenance-line` gap `Provenance line
            is out of range for {export_name}`; `line-invalid` an Info
            `provenance-unverified` gap `Provenance line not verified for
            {export_name}` at `{source_file}` alone. Its `missing`,
            `orphaned` and `citations` are not gaps here, and no record is
            appended for an export the ledger already records as a
            `fabricated-signature` gap.
  coherence --input aggregate-coherence.py's result. Each
            `invalidReferences[]` entry at `SKILL.md:{line}`, by `status`:
            `missing` is a Critical `broken-reference` gap, `inaccurate` a
            High `inaccurate-reference` gap (its `issues` as the issue) and
            `escapes` a High `reference-escape` gap naming its `canonical`
            path.
  structure --input one or more skf-scan-skill-md-structure.py results,
            each told apart by its keys; --served. A `scan --required-sections`
            result: each family not `satisfied` is a High `structural` gap
            `naive-coherence: missing required section: {family}`, unless
            --served names it (another heading serves it: the caller's
            judgment) or it is `description` and `frontmatter_description`
            is true. A `scan` result: unbalanced fences are a High
            `structural` gap, and each bare opening fence and each
            `table_drift` row a Medium `structural` gap at `SKILL.md:{line}`.
            A `usage-scope` result: each `zero_usage` export is a Medium
            `structural` gap with `export`. A `scan` or `reference-check`
            result whose `scripts_assets.missing` is true is a Medium
            `scripts-assets` gap. The titles are coherence-check.md's
            `naive-coherence:` texts; a `reference-check` result (contextual
            mode) titles its gap `coherence:` instead.

  render --ledger <path> [--heading]
      Print the Gap Report body in Markdown on stdout: the totals, the
      Remediation Summary table and one Gap Entry per record, Critical first,
      then by id. A summary row's Estimated Effort lists each category of
      its gaps, in the order its first gap comes, as `{category} ({count}):
      {action}` (ACTIONS), or `None` for a row with no gap (#1047).
      Each entry names its category as `{group} ({category})`,
      which skf-parse-gaps.py reads back for a report whose ledger is gone.
      --heading adds the `## Gap Report` line. With no records the body says
      no gaps were found.

  summary --ledger <path>
      Output: {"status": "ok", "ledger", "run_id", "stages", "total",
               "counts": {severity: n}, "blocking", "non_blocking",
               "by_category": {category: n}}

A Critical or High record blocks only when a stage before the hard gate
appended it. The report stage appends after the gate (the discovery test),
so render and summary count its Critical and High records as non-blocking:
render lists them on a line of their own, after the hard gate.

  categories
      Output the category vocabulary and the severities:
      {"status": "ok", "severities": [...],
       "categories": [{"category", "group", "description"}]}

Exit codes:
  0  the result was printed
  1  the ledger is missing, unreadable, not a valid ledger, held by another
     append past the wait, or not writable
  2  the input records are invalid (nothing was written), or a usage error
     (argparse: a missing or unknown argument, usage on stderr, no JSON)

Errors print {"status": "error", "code", "error", ...} on stdout, except for
render, which prints it on stderr so a redirected Gap Report stays clean. The
codes: LEDGER_MISSING, LEDGER_INVALID, LEDGER_LOCKED, WRITE_FAILED (exit 1),
INVALID_INPUT and INVALID_RECORD (exit 2, with `errors: [{index, error}]`).
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import importlib.util
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

SCHEMA_VERSION = 1

# How long an append waits for another append's lock before LEDGER_LOCKED.
# An append holds it for milliseconds; the wait covers a burst of parallel
# tool calls, not a writer that hangs.
LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02
# Windows refuses to replace a file another process holds open, and a virus
# scanner or the search indexer may open a just-written ledger for a moment:
# save_ledger retries the rename there for up to this long before failing.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0

SEVERITIES = ("Critical", "High", "Medium", "Low", "Info")
BLOCKING = frozenset({"Critical", "High"})
_SEVERITY_BY_LOWER = {s.lower(): s for s in SEVERITIES}
# Stages that append after the hard gate decided (report.md records the
# discovery test there): a Critical or High gap they record blocked nothing.
POST_GATE_STAGES = frozenset({"report"})

# Category slug -> (group, what the category covers). update-skill routes a
# gap on its category, not its severity, so the slugs are a closed set: a typo
# fails the append instead of reaching update-skill as an unknown category.
CATEGORIES: dict[str, tuple[str, str]] = {
    "missing-export": ("Coverage", "an exported function or class the skill does not document"),
    "signature-mismatch": ("Coverage", "a documented signature that differs from the source"),
    "fabricated-signature": ("Coverage", "a documented export that is absent at the cited source line"),
    "stale-documentation": ("Coverage", "documentation for an export the enumerated source surface lacks"),
    "missing-type": ("Coverage", "a type or interface the skill does not document"),
    "provenance-completeness": ("Coverage", "an export the skill documents that the provenance map lacks"),
    "provenance-line": (
        "Coverage",
        "a provenance line that is not the definition of its export, or a citation whose file or line the source "
        "lacks",
    ),
    "provenance-unverified": (
        "Coverage", "a provenance line the line-check rules could not verify, or one that is not a line number"),
    "metadata-drift": ("Coverage", "export counts in the metadata that diverge from each other"),
    "denominator-inflation": ("Coverage", "a scope include union larger than the provenance map"),
    "brief-scope-stale": (
        "Coverage", "a scope.include or scope.tier_a_include glob in the brief that matches no source file"),
    "numerator-inflation": (
        "Coverage",
        "a documented count equal to the denominator while declared exports are absent from the skill",
    ),
    "multi-denominator": ("Coverage", "barrel and documented-surface counts that diverge by design"),
    "migration-section": ("Coverage", "a migration section that disagrees with the annotation data"),
    "broken-reference": ("Coherence", "a reference whose target does not exist"),
    "inaccurate-reference": ("Coherence", "a reference whose target exists but does not match it"),
    "reference-escape": (
        "Coherence",
        "a reference whose real path leaves the skill, its source and, for a stack, the skills folder",
    ),
    "integration-pattern": ("Coherence", "an integration pattern that is incomplete"),
    "split-body-mismatch": (
        "Coherence",
        "two files of the skill (SKILL.md or a references/ file) that disagree about an export",
    ),
    "scripts-assets": ("Coherence", "a Scripts & Assets section that is missing or names a missing file"),
    "scripts-assets-provenance": ("Coherence", "a script or asset file without a provenance entry"),
    "structural": (
        "Structural",
        "a section, code fence, table or usage example in SKILL.md that is missing or wrong",
    ),
    "metadata": ("Structural", "missing optional metadata or examples"),
    "observation": ("Structural", "a style suggestion, a documented extra or another non-blocking observation"),
    "discovery": ("Discovery", "a discovery test that misrouted prompts or did not run"),
    "description": ("Discovery", "a description whose triggers need optimizing"),
    "external-validator": ("External", "a skill-check diagnostic or a Tessl Review suggestion"),
}

REQUIRED_FIELDS = ("severity", "category", "title", "source", "remediation")
OPTIONAL_FIELDS = ("issue", "export")
ASSIGNED_FIELDS = ("id", "group", "stage")

# The Remediation Summary's Estimated Effort column, per category: what a gap of each category asks, worded to fit
# every remediation of that category and update-skill's routing of it (gap-driven.md). Severity does not decide the
# fix, so a row lists the categories of its gaps, each with its count and action, joined with `; `, which no action
# holds (#1047).
ACTIONS = {
    "missing-export": "document each export from its definition in the source",
    "signature-mismatch": "update each documented signature to the one the source defines",
    "fabricated-signature": "remove each name from the skill, or correct it to the export the source defines",
    "stale-documentation": "check each name against the source and the brief's scope, then update or remove its "
                           "documentation or fix the scope (Update Skill does not repair it)",
    "missing-type": "document each type, with its fields or members, from the source",
    "provenance-completeness": "add a provenance map entry for each documented export the map lacks",
    "provenance-line": "point each provenance entry at the file and line that define its export, and move its "
                       "citations there",
    "provenance-unverified": "check by hand which line defines each export, then correct its provenance entry as "
                             "its remediation says",
    "metadata-drift": "re-run Create Skill or edit the brief's scope, as each remediation says (counts that differ "
                      "only by `Type::method` entries need no fix, and a hand edit of the counts does not hold)",
    "denominator-inflation": "list the files of the authored surface in the brief's `scope.tier_a_include`, as each "
                             "remediation says",
    "brief-scope-stale": "edit the brief's stale scope globs by hand so each matches the files it meant, and add a "
                         "`scope.include` glob over each restored file the skill documents (a `scope.exclude` one "
                         "for each it leaves out), as each remediation says (Update Skill does not rewrite them)",
    "numerator-inflation": "document the absent exports in SKILL.md or references/, reading each from the source",
    "multi-denominator": "none, since the barrel and the documented surface measure different sets by design",
    "migration-section": "make SKILL.md's migration section match the T2-future annotation data, as each "
                         "remediation says",
    "broken-reference": "point each reference at a target that exists, or remove it",
    "inaccurate-reference": "correct each reference so it matches its target",
    "reference-escape": "point each reference inside the skill package or its source tree, or remove it",
    "integration-pattern": "add to each integration pattern the evidence its issue names as missing",
    "split-body-mismatch": "correct the file each Source names so both files document the export alike, or, where "
                           "the two forms document different declarations, add beside each form the citation and "
                           "the module or owner its remediation names",
    "scripts-assets": "add or correct SKILL.md's Scripts & Assets section so it lists each file in `scripts/` and "
                      "`assets/`",
    "scripts-assets-provenance": "add each file's row to the provenance map's `file_entries`, or remove the file "
                                 "from the skill",
    "structural": "fix each section, code fence, table row or usage example as its remediation says",
    "metadata": "add the missing optional metadata or examples",
    "observation": "apply each only when you agree, as its remediation says, since it is advisory (a documented "
                   "extra needs no change)",
    "discovery": "add to the description the trigger phrases each remediation names, or run the skipped discovery "
                 "test as its remediation says",
    "description": "edit the SKILL.md frontmatter description as each gap suggests",
    "external-validator": "apply each skill-check diagnostic or Tessl Review suggestion to SKILL.md as its "
                          "remediation says",
}

_ID_RE = re.compile(r"^GAP-(\d{3,})$")
_STAGE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_RUN_ID_FROM_NAME = re.compile(r"^test-findings-(.+)\.json$")
# A whole quoted string, `"name"` or `'name'`. The lookahead lets matches overlap, so an apostrophe earlier on the
# line (`don't 'add'`) does not swallow the next string; the text between two strings is a harmless extra key.
_QUOTED_RE = re.compile(r"""(?=(["'])([^"'\n]+)\1)""")
# A dotted path of plain identifiers (`cognee.exceptions`), its last segment group 1 (#1011).
_MODULE_PATH_RE = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.([A-Za-z_$][\w$]*)")
# A plain identifier directly followed by `(`, group 1: the name a usage form calls after its prefix (#1041).
_CALLED_RE = re.compile(r"([A-Za-z_$][\w$]*)\(")
# The dotted path a usage prefix ends with (`cognee.` in `await cognee.`), its first segment group 1.
_RECEIVER_RE = re.compile(r"([A-Za-z_$][\w$]*)\.(?:[A-Za-z_$][\w$]*\.)*$")
# A fenced line that imports a module under a name: Python's `import a.b [as c], d` (group 1) and `from a.b import`
# (group 2, `a` the root; a relative import binds none), JS/TS's `import * as ns from` (group 3). A dotted path
# qualifies a name only when its first segment is such a module, never a receiver or a type (`client.`, `Client.`).
_IMPORT_RE = re.compile(
    r"\s*(?:import\s+([A-Za-z_][\w.]*(?:\s+as\s+[A-Za-z_]\w*)?(?:\s*,\s*[A-Za-z_][\w.]*(?:\s+as\s+[A-Za-z_]\w*)?)*)"
    r"\s*;?\s*$|from\s+([A-Za-z_]\w*)[\w.]*\s+import\b|import\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from\b)")
# A sentence's tokens (#1080): an inline code span, group 1 its backtick run, closed by an equal run on its line as
# locate-export-segments.py's `_inline_code` reads one, so its dots and bars end nothing; `.`, `!` or `?` before
# whitespace or the end, which ends a sentence; or an unescaped `|`, which ends one in a table row.
_SENTENCE_TOKEN_RE = re.compile(r"(?<!`)(`++)(?!`)[^\n]*?(?<!`)\1(?!`)|[.!?](?=\s|\Z)|(?<!\\)\|")
# What a sentence says, outside its code spans, when the skill does not cover the names it holds
# (inventory-contract.md), in any case and with any whitespace between the words, as whole words that a letter or
# digit, never an emphasis `_`, would join to another (#1080).
_NOT_COVERED_RE = re.compile(r"(?<![^\W_])(?:out\s+of\s+scope\s+for\s+this\s+skill|not\s+covered\s+here)(?![^\W_])",
                             re.IGNORECASE)


class LedgerError(Exception):
    """A ledger that is missing, unreadable or malformed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


def _one_line(value: str) -> str:
    return " ".join(value.split())


def normalize_record(raw: object) -> tuple[dict | None, str | None]:
    """Validate one input record. Returns (record, None) or (None, error).

    >>> rec, err = normalize_record({"severity": "high", "category": "broken-reference",
    ...     "title": " Broken  link ", "source": "SKILL.md:12", "remediation": "Fix it."})
    >>> (rec["severity"], rec["title"], err)
    ('High', 'Broken link', None)
    >>> normalize_record({"severity": "Severe"})[1]
    "missing required field 'category'"
    """
    if not isinstance(raw, dict):
        return None, f"a record must be a JSON object, got {type(raw).__name__}"
    for key in ASSIGNED_FIELDS:
        if key in raw:
            return None, f"'{key}' is assigned by the ledger; leave it out"
    unknown = sorted(set(raw) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    if unknown:
        return None, f"unknown field(s): {', '.join(unknown)}"
    for key in REQUIRED_FIELDS:
        if key not in raw:
            return None, f"missing required field '{key}'"
        if not isinstance(raw[key], str):
            return None, f"'{key}' must be a string"
    for key in OPTIONAL_FIELDS:
        if raw.get(key) is not None and not isinstance(raw[key], str):
            return None, f"'{key}' must be a string or null"
    severity = _SEVERITY_BY_LOWER.get(raw["severity"].strip().lower())
    if severity is None:
        return None, (
            f"unknown severity '{raw['severity']}' (expected one of {', '.join(SEVERITIES)})"
        )
    category = raw["category"].strip()
    if category not in CATEGORIES:
        return None, f"unknown category '{category}' (run the categories subcommand for the list)"
    record = {
        "severity": severity,
        "category": category,
        "group": CATEGORIES[category][0],
        "title": _one_line(raw["title"]),
        "source": _one_line(raw["source"]),
        "remediation": raw["remediation"].strip(),
    }
    for key in ("title", "source", "remediation"):
        if not record[key]:
            return None, f"'{key}' must not be empty"
    issue = (raw.get("issue") or "").strip()
    if issue:
        record["issue"] = issue
    export = _one_line(raw.get("export") or "")
    if export:
        record["export"] = export
    return record, None


def _dedupe_key(record: dict) -> tuple[str, str, str, str, str | None]:
    """What makes two records the same gap. The export is part of it: two
    missing exports can share a generic title and a barrel Source."""
    return (
        record["severity"],
        record["category"],
        record["title"],
        record["source"],
        record.get("export") or None,
    )


def _id_number(record: dict) -> int:
    m = _ID_RE.match(record.get("id", ""))
    return int(m.group(1)) if m else 0


def ordered(records: list[dict]) -> list[dict]:
    """Records by severity (Critical first), then by id."""
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(records, key=lambda r: (rank[r["severity"]], _id_number(r)))


def count_by_severity(records: list[dict]) -> dict[str, int]:
    counts = {s: 0 for s in SEVERITIES}
    for record in records:
        counts[record["severity"]] += 1
    return counts


def is_blocking(record: dict) -> bool:
    """A Critical or High gap that a stage before the hard gate recorded.

    >>> is_blocking({"severity": "High", "stage": "coherence-check"})
    True
    >>> is_blocking({"severity": "High", "stage": "report"})
    False
    """
    return record["severity"] in BLOCKING and record.get("stage") not in POST_GATE_STAGES


# --------------------------------------------------------------------------
# Ledger file
# --------------------------------------------------------------------------


def new_ledger(path: Path) -> dict:
    m = _RUN_ID_FROM_NAME.match(path.name)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": m.group(1) if m else None,
        "stages": [],
        "records": [],
    }


def validate_ledger(data: object) -> None:
    """Raise LedgerError unless `data` is a well-formed ledger."""
    if not isinstance(data, dict):
        raise LedgerError("LEDGER_INVALID", "the ledger must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError(
            "LEDGER_INVALID",
            f"unsupported schema_version {data.get('schema_version')!r} (expected {SCHEMA_VERSION})",
        )
    stages = data.get("stages")
    if not isinstance(stages, list) or not all(isinstance(s, str) for s in stages):
        raise LedgerError("LEDGER_INVALID", "'stages' must be a list of strings")
    records = data.get("records")
    if not isinstance(records, list):
        raise LedgerError("LEDGER_INVALID", "'records' must be a list")
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise LedgerError("LEDGER_INVALID", f"record {index} is not an object")
        rid = record.get("id")
        if not isinstance(rid, str) or not _ID_RE.match(rid):
            raise LedgerError("LEDGER_INVALID", f"record {index} has no valid id")
        if rid in seen:
            raise LedgerError("LEDGER_INVALID", f"duplicate id {rid}")
        seen.add(rid)
        if record.get("severity") not in SEVERITIES:
            raise LedgerError("LEDGER_INVALID", f"{rid} has an unknown severity")
        if record.get("category") not in CATEGORIES:
            raise LedgerError("LEDGER_INVALID", f"{rid} has an unknown category")
        for key in ("title", "source", "remediation"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise LedgerError("LEDGER_INVALID", f"{rid} has no {key}")
        for key in OPTIONAL_FIELDS:
            if record.get(key) is not None and not isinstance(record[key], str):
                raise LedgerError("LEDGER_INVALID", f"{rid} has a {key} that is not a string")


def load_ledger(path: Path) -> dict:
    """Read and validate a ledger. Raises LedgerError."""
    if not path.is_file():
        raise LedgerError("LEDGER_MISSING", f"no ledger at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerError("LEDGER_INVALID", f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError("LEDGER_INVALID", f"{path} is not valid JSON: {exc}") from exc
    validate_ledger(data)
    return data


def save_ledger(path: Path, data: dict) -> None:
    """Write the ledger atomically: a temp file of its own beside it, then a
    rename. Call it under ledger_lock() so no other append runs between the
    read and this write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.skf-tmp")
    payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    # O_EXCL: never write into another writer's temp file. O_BINARY (Windows
    # only; 0 elsewhere) keeps the \n line ends.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o644)
    try:
        with open(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if not _IS_WINDOWS or time.monotonic() >= deadline:
                    raise
                time.sleep(_LOCK_POLL_SECONDS)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _try_lock(fd: int) -> bool:
    """Lock fd exclusively without waiting; False while another process holds it."""
    try:
        if os.name == "nt":
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EDEADLK):
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    with contextlib.suppress(OSError):
        if os.name == "nt":
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)


def _names_open_file(fd: int, path: Path) -> bool:
    """True when `path` still names the file open as `fd`."""
    try:
        return os.path.samestat(os.fstat(fd), os.stat(path))
    except OSError:
        return False


@contextlib.contextmanager
def ledger_lock(path: Path, timeout: float | None = None):
    """Hold the exclusive append lock on `<ledger>.skf-lock`.

    The same fcntl / msvcrt lock as skf-atomic-write.py flip-link, but this
    one waits: up to `timeout` seconds (LOCK_TIMEOUT_SECONDS), then it raises
    LedgerError LEDGER_LOCKED. The lock dies with its process, so a crashed
    append leaves nothing to clean up. The lock file is removed on release.
    On POSIX that happens while the lock is still held, and a waiter checks
    that the file it locked is still the one at the path: otherwise a waiter
    on the removed file and a newcomer on a new one would both get a lock.
    Windows removes no file that is open, so there the file goes after the
    release, unless a waiter has it open. While the removal is under way (the
    remover's own delete handle is open, or a virus scanner's or the search
    indexer's), Windows refuses a new open of the file with PermissionError:
    an append takes that for a held lock and tries again until the same
    deadline, then raises LEDGER_LOCKED naming the last refusal. A refusal
    with a folder at the path, or with nothing there on an immediate second
    try, is a lasting denial and is raised as is.
    """
    timeout = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    lock_path = path.with_name(path.name + ".skf-lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout

    def refuse(cause: OSError | None = None) -> LedgerError:
        message = f"another append held {lock_path} for more than {timeout:g} s"
        if cause is not None:
            message += f" (last open refused: {cause})"
        return LedgerError("LEDGER_LOCKED", message)

    vanished = False
    while True:
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
        except PermissionError as exc:
            # Windows refuses to open a file whose removal is pending. A folder
            # at the path, or nothing there twice running (once can be the
            # removal ending just now), is a lasting denial: raise it.
            if not _IS_WINDOWS or os.path.isdir(lock_path):
                raise
            if not os.path.lexists(lock_path):
                if vanished:
                    raise
                vanished = True
                continue
            vanished = False
            if time.monotonic() >= deadline:
                raise refuse(exc) from exc
            time.sleep(_LOCK_POLL_SECONDS)
            continue
        try:
            while not _try_lock(fd):
                if time.monotonic() >= deadline:
                    raise refuse()
                time.sleep(_LOCK_POLL_SECONDS)
            if os.name == "nt" or _names_open_file(fd, lock_path):
                break
            _unlock(fd)
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)
        if time.monotonic() >= deadline:
            raise refuse()
    try:
        yield
    finally:
        if os.name != "nt":
            with contextlib.suppress(OSError):
                lock_path.unlink()
        _unlock(fd)
        os.close(fd)
        if os.name == "nt":
            with contextlib.suppress(OSError):
                lock_path.unlink()


def append_records(ledger: dict, stage: str, records: list[dict]) -> tuple[list[str], list[str]]:
    """Append validated records in place. Returns (appended ids, duplicate ids)."""
    existing = {_dedupe_key(r): r["id"] for r in ledger["records"]}
    next_number = max((_id_number(r) for r in ledger["records"]), default=0) + 1
    appended: list[str] = []
    duplicates: list[str] = []
    for record in records:
        key = _dedupe_key(record)
        if key in existing:
            duplicates.append(existing[key])
            continue
        rid = f"GAP-{next_number:03d}"
        next_number += 1
        ledger["records"].append({"id": rid, **record, "stage": stage})
        existing[key] = rid
        appended.append(rid)
    if stage not in ledger["stages"]:
        ledger["stages"].append(stage)
    return appended, duplicates


def parse_input(text: str) -> list:
    """The records an append reads: an array, one object or {"records": [...]}."""
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if set(data) == {"records"}:
            if not isinstance(data["records"], list):
                raise ValueError("'records' must be a list")
            return data["records"]
        return [data]
    raise ValueError("input must be a JSON array or object")


# --------------------------------------------------------------------------
# Adapters: a script's result file -> records (append --from)
# --------------------------------------------------------------------------


class AdapterError(Exception):
    """A --from input that does not hold the result its kind reads."""


FAMILIES = ("description", "usage", "api_surface")
# The options (argparse dests) each kind reads, besides --input. A kind
# refuses any other, so a call that passes a file it would ignore fails.
ADAPTER_OPTIONS: dict[str, frozenset[str]] = {
    "coverage": frozenset(
        {"surface", "signatures", "numerator", "stale", "provenance", "inventory", "skill_dir", "metadata"}
    ),
    "guards": frozenset({"metadata"}),
    "numerator": frozenset({"metadata"}),
    "metadata-coherence": frozenset({"metadata"}),
    "provenance-line": frozenset({"stale"}),
    "coherence": frozenset(),
    "structure": frozenset({"served"}),
}
ALL_ADAPTER_OPTIONS = frozenset().union(*ADAPTER_OPTIONS.values())
_DEFAULT_METADATA = "metadata.json"
_DEFAULT_BRIEF = "skill-brief.yaml"
# The remediation of a missing required section: the SKF template heading
# that serves the family.
_SECTION_FIX = {
    "description": (
        "Add a `## Overview` section to SKILL.md that says what the library does and when "
        "to use it, or a non-empty `description` to its frontmatter."
    ),
    "usage": (
        "Add a `## Quick Start` section to SKILL.md with a runnable example of the "
        "library's most common calls."
    ),
    "api_surface": (
        "Add a `## Key API Summary` section to SKILL.md that lists the library's exports "
        "with their purpose."
    ),
}

_SIBLINGS: dict[str, object] = {}


def _sibling(filename: str):
    """A script beside this one, loaded once: validate-inventory.py (the
    skill-citation scan the homonym pick reads), load-coverage-inputs.py
    (the documented inventory's floor, and its fence and table readers)
    and locate-export-segments.py (the skill's files and line model), the
    last two for the line that documents a stale name, and
    load-coverage-inputs.py's `STAR_SPECIFIER_RE` for the module of an
    `unresolvedStars` statement, with or without --skill-dir (#1070)."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = Path(__file__).resolve().parent / filename
        spec = importlib.util.spec_from_file_location("skf_" + filename[:-3].replace("-", "_"), path)
        if spec is None or spec.loader is None or not path.is_file():
            raise AdapterError(f"{filename} not found beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[filename] = module
    return module


def read_result(path: str, flag: str):
    """The JSON a script wrote. Raises AdapterError."""
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise AdapterError(f"cannot read {flag} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AdapterError(f"{flag} {path} is not JSON: {exc.msg}") from exc


def _object(data: object, label: str, *keys: str) -> dict:
    """`data` as the object a script writes, with each of `keys`."""
    if not isinstance(data, dict) or any(key not in data for key in keys):
        needs = ", ".join(f"'{key}'" for key in keys)
        raise AdapterError(f"{label} is not that script's result: it needs an object with {needs}")
    return data


def _list(data: dict, key: str, label: str) -> list:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError(f"{label}: '{key}' must be a list")
    return value


def _names(data: dict, key: str, label: str) -> list[str]:
    return [n for n in _list(data, key, label) if isinstance(n, str) and n]


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _code(names: list[str]) -> str:
    return ", ".join(f"`{n}`" for n in names)


def _gap(severity: str, category: str, title: str, source: str, remediation: str,
         issue: str | None = None, export: str | None = None) -> dict:
    record = {"severity": severity, "category": category, "title": title, "source": source,
              "remediation": remediation}
    if issue:
        record["issue"] = issue
    if export:
        record["export"] = export
    return record


def _surface_sources(surface: dict | None) -> dict[str, str]:
    """name -> `file:line` (or `file`) from a surface result's `exports[]`:
    the first record with a file, one with a line preferred."""
    sources: dict[str, tuple[bool, str]] = {}
    for rec in (surface or {}).get("exports") or []:
        if not isinstance(rec, dict) or not isinstance(rec.get("name"), str):
            continue
        file = rec.get("file")
        if not isinstance(file, str) or not file:
            continue
        line = _count(rec.get("line"))
        where = (line is not None, f"{file}:{line}" if line is not None else file)
        known = sources.get(rec["name"])
        if known is None or (where[0] and not known[0]):
            sources[rec["name"]] = where
    return {name: where for name, (_, where) in sources.items()}


def _provenance_sources(provenance: dict | None) -> dict[str, str]:
    """export_name -> `source_file:source_line` of its first provenance entry."""
    sources: dict[str, str] = {}
    for entry in (provenance or {}).get("entries") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("export_name"), str):
            continue
        file = entry.get("source_file")
        if entry["export_name"] in sources or not isinstance(file, str) or not file:
            continue
        line = _count(entry.get("source_line"))
        sources[entry["export_name"]] = f"{file}:{line}" if line is not None else file
    return sources


def _module_path_name(text: str, roots: frozenset[str]) -> str | None:
    """The last segment of the dotted path of plain identifiers `text` writes once floor's `_floor_name` cuts are
    made, a leading `new ` and everything from the first `(`, `<` or `[` (`run_migrations` for
    `cognee.run_migrations()`, #1041), when the path's first segment is one of the modules the skill imports
    (`roots`, `_module_roots`); None for any other text, an array type (`pkg.Foo[]`) or a path through a receiver or
    a type (`client.connect`, `Client.connect`) among them."""
    text = text.strip()
    if text.startswith("new "):
        text = text[4:]
    cut = re.match(r"([^(<\[]*)(\[\s*\])?", text)
    module = None if cut.group(2) else _MODULE_PATH_RE.fullmatch(cut.group(1).strip())
    return module.group(1) if module and cut.group(1).strip().split(".", 1)[0] in roots else None


def _module_roots(files: list[tuple[str, list[str]]], segments, coverage) -> frozenset[str]:
    """The names the skill's fenced code imports a module under (`_IMPORT_RE`): `cognee` for `import cognee` or
    `from cognee.x import y`, `c` and `a` for `import a.b as c`, `ns` for `import * as ns from 'x'`. Read from every
    fence `_documenting_lines` reads (not one in an HTML comment or a data block), comments and strings masked,
    never the frontmatter."""
    roots: set[str] = set()
    for _rel, lines in files:
        start = segments._frontmatter_end(lines)
        blocks, code = segments._fenced_blocks(lines, start)
        comments = coverage._html_comment_lines(lines, start, code)
        for opening, closing, info in blocks:
            language = segments._language(info)
            if opening in comments or language in segments.DATA_LANGUAGES:
                continue
            for line in segments.mask_code("\n".join(lines[opening + 1:closing]), language).split("\n"):
                match = _IMPORT_RE.match(line)
                if match and match.group(1):
                    for part in match.group(1).split(","):
                        module, *alias = re.split(r"\s+as\s+", part.strip())
                        roots.update([module.split(".", 1)[0], *alias])
                elif match:
                    roots.add(match.group(2) or match.group(3))
    return frozenset(roots)


def _without_not_covered(text: str, row: bool = False) -> str:
    """`text` with each sentence that says the skill does not cover a name (`_NOT_COVERED_RE`, read outside its code
    spans) blanked, each of its characters a space but a newline, so lines keep their numbers and none of its spans
    or text keys a name (#1080). A sentence ends at `.`, `!` or `?` before whitespace or the end, blanked with it,
    or, in a table row (`row`), at an unescaped `|`, which stays so the row keeps its cells; never inside a code
    span (`_SENTENCE_TOKEN_RE`), and it runs across the lines of `text`."""
    kept, outside, start = list(text), list(text), 0

    def blank(end: int) -> None:
        if _NOT_COVERED_RE.search("".join(outside[start:end])):
            kept[start:end] = [" " if char != "\n" else char for char in text[start:end]]

    for token in _SENTENCE_TOKEN_RE.finditer(text):
        if token.group(1):
            # a code span: its words never say the phrase
            outside[token.start():token.end()] = "`" * (token.end() - token.start())
        elif token.group() != "|":
            blank(token.end())
            start = token.end()
        elif row:
            blank(token.start())
            start = token.end()
    blank(len(text))
    return "".join(kept)


def _documenting_lines(skill_dir: Path) -> dict[str, str]:
    """name -> the `file:line` that documents it as an export, the first tier
    that holds the name winning:

      1. its first origin in the documented inventory's floor
         (load-coverage-inputs.py `floor`: SKILL.md and the top-level
         references/*.md);
      2. a heading, or the first cell of a table whose header's first cell
         names exports (floor's `_floor_table_header`: `Functions`, `Queries`,
         `Component / Props`), whose stripped text is the name
         or holds a code span floor's `_floor_name` reads as the name, or
         whose text or code span, once `_floor_name`'s cuts are made, is a
         module path whose last segment is the name
         (`cognee.run_migrations()` for `run_migrations`, #1041);
      3. a line whose inline code span, stripped, is the name, the name
         directly followed by `(`, or a usage form that calls it: floor's
         `USAGE_PREFIX_RE` prefix (an assignment, `await`, `new` or a module
         path), not empty, then the name directly followed by `(`
         (`await cognee.add(data)`, `x = get(key)`, #1041);
      4. a line whose inline code span, stripped and cut at a call's `(`, is
         a module path whose last segment is the name, `cognee.exceptions`
         for `exceptions` (#1011);
      5. a column-0 public declaration of it in a fenced code block (floor's
         `_declared_names`), cited or not, so a def an example writes under
         the name (a connector author's own `mount_table_target`) is cited
         only when nothing above documents it;
      6. a raw (unmasked) line of a fenced code block that holds the name as a
         whole quoted string (`"name"` or `'name'`), such as an `__all__`
         item; it only replaces the bare `SKILL.md` fallback.

    Tiers 2 to 6 read SKILL.md, then every .md file under references/,
    subfolders included, in path order (locate-export-segments.py
    `skill_files`), never the frontmatter: tiers 2 to 4 outside fenced code
    and HTML comments, tiers 5 and 6 inside a fence outside an HTML comment
    and a data block (json, yaml...). Within a tier the first file, then its
    lowest line, wins. A bare word, a span that holds the name among other
    words (`uitripled add`), or a quoted string outside a fence or holding
    other words too (`"add x"`) documents nothing, and so does a sentence of a
    heading or a prose block that says the skill does not cover a name (`out
    of scope for this skill` or `not covered here`, any case, outside its code
    spans): `_without_not_covered` blanks it before tiers 2 to 4 read the
    text, a sentence ending at `.`, `!` or `?` before whitespace or at a table
    row's unescaped `|`, never inside a code span, and running across a
    block's lines (#1080). A module path is a dotted
    path of plain identifiers whose first segment is a module the skill's
    fenced code imports (`_module_roots`), so a receiver's or a type's path
    (`client.connect(url)`, `Client.connect`, `store.state`) documents
    nothing. An input a tier cannot
    read is skipped: floor's InputError (no SKILL.md, a file that is not
    UTF-8) leaves tier 1 empty, an unreadable file tiers 2 to 6."""
    coverage = _sibling("load-coverage-inputs.py")
    segments = _sibling("locate-export-segments.py")
    # In merge order: floor, heading or export-table cell, code span, module path, fenced declaration, quoted string.
    tiers: list[dict[str, str]] = [{}, {}, {}, {}, {}, {}]
    try:
        for entry in coverage.floor(str(skill_dir))["names"]:
            origin = entry["origins"][0]
            tiers[0].setdefault(entry["name"], f"{origin['file']}:{origin['line']}")
    except coverage.InputError:
        pass
    try:
        files = segments.skill_files(skill_dir)
    except OSError:
        files = []
    # the modules a dotted path may start with: never a receiver or a type the skill names
    roots = _module_roots(files, segments, coverage)
    # floor's fence filter: a fence in an HTML comment or a data block declares and quotes nothing, and a Svelte
    # block's `export let` is a component prop. Unlike floor, an unheaded fence counts; a Svelte, shell or untagged
    # fence's quoted strings count too.
    js_family = segments.JS_FAMILY - {"svelte"}
    for rel, lines in files:
        start = segments._frontmatter_end(lines)
        blocks, code = segments._fenced_blocks(lines, start)
        comments = coverage._html_comment_lines(lines, start, code)
        for opening, closing, info in blocks:
            language = segments._language(info)
            if opening in comments or language in segments.DATA_LANGUAGES:
                continue
            raw = lines[opening + 1:closing]
            masked = segments.mask_code("\n".join(raw), language).split("\n")
            for offset, declared in coverage._declared_names(masked, language, js_family):
                tiers[4].setdefault(declared, f"{rel}:{opening + offset + 2}")
            for offset, line in enumerate(raw):
                for match in _QUOTED_RE.finditer(line):
                    tiers[5].setdefault(match.group(2), f"{rel}:{opening + offset + 2}")
        headings, prose = segments._prose(lines, start, code)
        # a sentence saying the skill does not cover a name keys nothing in tiers 2 to 4 (#1080): each heading and
        # each prose block, its lines joined, is read with such sentences blanked
        shaped = [(index, _without_not_covered(text)) for index, _level, text, _above in headings]
        written = list(shaped)
        for block in prose:
            row = block["kind"] == "table-row"
            kept = _without_not_covered("\n".join(lines[block["start"]:block["end"] + 1]), row).split("\n")
            written += list(enumerate(kept, block["start"]))
            if row and block["header"] is not None:
                if coverage._floor_table_header(coverage._cells(block["header"])[0]):
                    shaped.append((block["start"], coverage._cells(kept[0])[0]))
        for index, text in sorted(shaped):
            # its text, or a code span, that is a module path keys the path's last segment too (#1041)
            spans = [coverage._floor_name(span) or _module_path_name(span, roots)
                     for span in segments._inline_code(text)]
            for key in [text.strip(), _module_path_name(text, roots)] + spans:
                if key:
                    tiers[1].setdefault(key, f"{rel}:{index + 1}")
        for index, text in sorted(written):
            for span in map(str.strip, segments._inline_code(text)):
                # a usage form keys the name it calls after an assignment, `await`, `new` or a module (#1041)
                prefix = coverage.USAGE_PREFIX_RE.match(span)
                receiver = _RECEIVER_RE.search(prefix.group())
                called = (_CALLED_RE.match(span, prefix.end())
                          if prefix.group() and (receiver is None or receiver.group(1) in roots) else None)
                for key in (span, span.split("(", 1)[0] if "(" in span else None, called and called.group(1)):
                    if key:
                        tiers[2].setdefault(key, f"{rel}:{index + 1}")
        # a module path keys its last segment: each code span (#1011); a heading's or export cell's is tier 2's
        paths = [(index, span) for index, text in written for span in segments._inline_code(text)]
        for index, text in sorted(paths):
            path = text.strip().split("(", 1)[0]
            module = _MODULE_PATH_RE.fullmatch(path)
            if module and path.split(".", 1)[0] in roots:
                tiers[3].setdefault(module.group(1), f"{rel}:{index + 1}")
    found: dict[str, str] = {}
    for tier in tiers:
        for key, line in tier.items():
            found.setdefault(key, line)
    return found


def _documenting_line(skill_dir: Path, name: str) -> str | None:
    """The `file:line` that documents `name` as an export in the skill at
    `skill_dir` (`_documenting_lines`), else None."""
    return _documenting_lines(skill_dir).get(name)


def _inventory_forms(inventory: object) -> dict[str, list[tuple[str, int]]]:
    """name -> every (path, line) `at` the --inventory result (validate-inventory.py's, which with --skill-package
    keeps only an `at` whose line writes the name) gives an entry of that name that is no `method`, each once:
    SKILL.md's first, then the files in path order, then their lines, as `_documenting_lines` orders its tiers
    (#1006). They are the places of its forms, whose own citations pick a homonym's declaring file (#1077). An
    entry with no `at`, or one that is no "<path>:<line>", gives none. An inventory that is no object with an
    `exports` list raises AdapterError."""
    if inventory is None:
        return {}
    exports = _list(_object(inventory, "--inventory (validate-inventory.py)", "exports"), "exports", "--inventory")
    parse_at = _sibling("validate-inventory.py").parse_at
    places: dict[str, set[tuple[str, int]]] = {}
    for entry in exports:
        if not isinstance(entry, dict) or entry.get("kind") == "method" or not isinstance(entry.get("name"), str):
            continue
        at = parse_at(entry.get("at"))
        if at is not None:
            places.setdefault(entry["name"], set()).add(at)
    return {name: sorted(spots, key=lambda at: (at[0] != "SKILL.md", *at)) for name, spots in places.items()}


def _inventory_places(forms: dict[str, list[tuple[str, int]]]) -> dict[str, str]:
    """name -> the first `at` of its `_inventory_forms`: SKILL.md's, then the first file in path order, then its
    lowest line (#1006)."""
    return {name: f"{path}:{line}" for name, [(path, line), *_] in forms.items()}


def _documents(doc: str | None, name: str) -> str:
    """The subject of a stale name's Issue: the line that documents it, else the skill."""
    return f"{f'`{doc}`' if doc else 'the skill'} documents `{name}`"


def _scoped_out_by(row: dict) -> bool:
    """Whether an `excluded.outsideScope` row says the brief scopes its file
    out: a file, with the `scope.exclude` glob that matches it
    (`excludeGlob`) or no `scope.include` glob covering it
    (`outsideInclude`)."""
    return (isinstance(row.get("file"), str) and bool(row["file"])
            and ((isinstance(row.get("excludeGlob"), str) and bool(row["excludeGlob"]))
                 or row.get("outsideInclude") is True))


def _outside_scope(surface: dict | None, stale: dict[str, dict] | None = None, skill_dir: str | None = None,
                   forms: dict[str, list[tuple[str, int]]] | None = None) -> dict[str, dict] | None:
    """The names a surface result's `excluded.outsideScope` lists (defined in
    a file out of scope), each with its row: the first the brief explains
    (`_scoped_out_by`), else the first with a file, else its first. None
    with no surface, no such list, or a surface built without an extraction
    (no `extraction` object) or from one that did not read the whole scope
    (a `no-ast-grep` status, a `truncated` run, or `fallback.needed`): only
    an extraction fills that list, so the names a brief scoped out are then
    unknown. A namespace's member that has the namespace's own name (its
    `namespace` is its `name`, #969), such as a function a submodule
    imports from a file out of scope, is no row here: the documented name
    is the submodule, which no brief scoped out, while another row of the
    name still lists it. It stays when its `file` is the one the classified
    stale item of its name (`stale`) says the source declares it in, where
    `_documented_extra_at` would put the gap, given the places of the
    name's forms (`forms`, `_inventory_forms`): that name is the member."""
    excluded = (surface or {}).get("excluded")
    if excluded is None:
        return None
    if not isinstance(excluded, dict):
        raise AdapterError("--surface: 'excluded' must be an object")
    rows = excluded.get("outsideScope")
    if rows is None:
        return None
    if not isinstance(rows, list):
        raise AdapterError("--surface: 'excluded.outsideScope' must be a list")
    extraction = (surface or {}).get("extraction")
    if not isinstance(extraction, dict):
        return None
    fallback = extraction.get("fallback")
    if (extraction.get("status") == "no-ast-grep" or extraction.get("truncated")
            or (isinstance(fallback, dict) and fallback.get("needed"))):
        return None
    def rank(row: dict) -> tuple[bool, bool]:
        return _scoped_out_by(row), isinstance(row.get("file"), str) and bool(row["file"])

    outside: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            if (isinstance(row.get("namespace"), str) and row["namespace"] and row["namespace"] == row["name"]
                    and not _declared_in_file(row, (stale or {}).get(row["name"]) or {}, skill_dir,
                                              (forms or {}).get(row["name"]))):
                continue  # the member, not the module the skill documents by that name
            known = outside.get(row["name"])
            if known is None or rank(row) > rank(known):
                outside[row["name"]] = row
    return outside


def _declared_in_file(row: dict, item: dict, skill_dir: str | None,
                      forms: list[tuple[str, int]] | None = None) -> bool:
    """Whether a stale item says the source declares its name in an
    `excluded.outsideScope` row's file: its `defined_at`, or its one cited
    `declared_in` item (its forms' own citations at their inventory `at`
    first, #1077), the place `_documented_extra_at` reads whatever the
    brief scopes out (an empty `outside`)."""
    extra = _documented_extra_at(row["name"], item, {}, skill_dir, forms)
    if not extra or not isinstance(row.get("file"), str) or not row["file"]:
        return False
    cited_path = _sibling("validate-inventory.py")._cited_path
    return cited_path(extra[0].rsplit(":", 1)[0]) == cited_path(row["file"])


# The extensions classify-stale reads a `defined_at` in.
# Keep identical to PYTHON_EXTENSIONS | TSJS_EXTENSIONS in skf-verify-provenance-completeness.py.
_DEFINED_AT_EXTENSIONS = frozenset({".py", ".pyi", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"})
# classify-stale's `defined_at`: a Python or TS/JS file and a line.
_DEFINED_AT_RE = re.compile(
    r"^.+(?:" + "|".join(re.escape(e) for e in sorted(_DEFINED_AT_EXTENSIONS)) + r"):[1-9]\d*$", re.IGNORECASE)


def _documented_extra_at(name: str, item: dict, outside: dict[str, dict] | None, skill_dir: str | None = None,
                         forms: list[tuple[str, int]] | None = None) -> tuple[str, int, list[str], list[str]] | None:
    """Where the source declares a stale name that is a documented extra, given
    a surface built from an extraction whose `excluded.outsideScope` does not
    list the name: (the item's `defined_at`, 0, [], []), or, with no
    `defined_at`, when `declared_in` lists several files, the one
    `declared_in` item whose file its forms' own citations (at their
    inventory `at`), else the skill's on lines naming it, cite. Its forms'
    own are every `[AST:]` and `[SRC:]` citation validate-inventory.py's
    form_citations gives the form at each of `forms` (_inventory_forms: a
    (path, line) in a SKILL.md or references/**/*.md file), with the name's
    other places in that file, as score-signatures.py's _bindings reads
    them, one with no `:L<n>` part included: a line that writes the name
    only as a type argument of another export cites that export's file
    (#1077), and every form counts, so one form never hides another's
    citation of a second declaring file. The skill's are the ones
    validate-inventory.py's _skill_cited_files reads on a line that names it,
    read when its forms' own cite no single file between them: no `forms`,
    none in a skill file, or forms citing none of those files or two. They
    are read with the forms' own, which that line scan misses after a
    closing fence, on a comment line above the declaration or with no
    `:L<n>`, so forms citing two files keep the Medium and the skill's lines
    decide only for forms citing none of them. That
    pick is (the item, the number of files `declared_in` lists, [], each
    form's "<path>:<line>" that cites the picked file, or [] for the
    skill's). Cited items that are only a
    package `<dir>/NAME/__init__.py` and modules named NAME directly in its
    folder (`<dir>/NAME/NAME.py` or `.pyi`) count, in either reading, as
    that one file, the package the import path `<dir>.NAME` resolves to
    (#1012): (its item, the count, those modules' items, the forms or []).
    None for anything else, which stays a Medium gap: no `defined_at` and no
    single cited declaring file (two or more cited that are not such a
    package and its modules, or none, in both readings, or no --skill-dir),
    a `defined_at` or `declared_in` item not a Python or TS/JS `file:line`, a
    dotted name, no surface or one without an extraction, or a name a brief
    scoped out (a namespace's member named like its namespace scopes out
    nothing: `_outside_scope` drops its row, #969, unless its file is the
    one this returns)."""
    if outside is None or name in outside or "." in name:
        return None
    defined_at = item.get("defined_at")
    if defined_at is not None:
        if not isinstance(defined_at, str) or not _DEFINED_AT_RE.match(defined_at):
            return None
        return defined_at, 0, [], []
    declared_in = item.get("declared_in")
    if not skill_dir or not isinstance(declared_in, list) or not all(
            isinstance(d, str) and _DEFINED_AT_RE.match(d) for d in declared_in):
        return None
    # validate-inventory.py's form and skill-citation scans, which score-signatures.py's plan reads too.
    citations = _sibling("validate-inventory.py")
    by_file = {citations._cited_path(d.rsplit(":", 1)[0]): d for d in declared_in}
    if len(by_file) < 2:
        return None
    texts = citations.skill_markdown_by_path(Path(skill_dir))
    # its forms' own citations first: a line naming it as another export's type argument cites that export (#1077);
    # each form reads the name's other places in its file, as score-signatures.py's _bindings does
    own: dict[str, set[str]] = {}
    for path, line in forms or []:
        others = {other for where, other in forms if where == path and other != line}
        own[f"{path}:{line}"] = {cited for cited, _, _ in citations.form_citations(
            texts.get(path) or [], line, name, others)}
    picked = _one_cited_file(name, by_file, set().union(*own.values()))
    if picked:
        files = {citations._cited_path(d.rsplit(":", 1)[0]) for d in (picked[0], *picked[2])}
        return (*picked, [at for at, cited in own.items() if cited & files])
    # the skill's lines with the forms' own, which a line scan misses (after a fence, a comment above, no `:L<n>`):
    # forms citing two files never leave one for the skill's lines to pick
    skill = citations._skill_cited_files(Path(skill_dir), name, list(texts.values()))
    picked = _one_cited_file(name, by_file, skill | set().union(*own.values()))
    return (*picked, []) if picked else None


def _one_cited_file(name: str, by_file: dict[str, str], cited: set[str]) -> tuple[str, int, list[str]] | None:
    """The one item of a homonym's declaring files (`by_file`: each file, _cited_path, to its `declared_in` item)
    among the `cited` files: (its item, the number of files, []), or, for cited files that are only a package
    `<dir>/NAME/__init__.py` and modules named NAME directly in its folder, (the package's item, the number, those
    modules' items) (#1012). None for none, or any other two."""
    chosen = [f for f in sorted(by_file) if f in cited]
    if len(chosen) == 1:
        return by_file[chosen[0]], len(by_file), []
    # a package and modules of its own name directly in its folder: the one module `<dir>.NAME` (#1012)
    packages = [f for f in chosen if f == f"{name}/__init__.py" or f.endswith(f"/{name}/__init__.py")]
    if len(packages) != 1:
        return None
    folder = packages[0][:-len("__init__.py")]
    modules = [f for f in chosen if f != packages[0]]
    if not modules or any(f not in (f"{folder}{name}.py", f"{folder}{name}.pyi") for f in modules):
        return None
    return by_file[packages[0]], len(by_file), [by_file[f] for f in modules]


def _missing_export(name: str, where: str | None, meta: str, kind: str = "export") -> dict:
    if where:
        read = f"read its definition at `{where}`"
    else:
        read = f"find its definition in the source (`{meta}` lists it)"
    if kind == "type":
        return _gap("Medium", "missing-type", f"Missing type: {name}", where or meta,
                    f"Document the type `{name}` in SKILL.md: {read} and list its fields or members.",
                    issue=f"the type `{name}` is on the source API surface, and the skill does not document it",
                    export=name)
    return _gap("Medium", "missing-export", f"Missing export: {name}", where or meta,
                f"Document `{name}` in SKILL.md: {read} and add its signature, its purpose and a usage "
                "example.",
                issue=f"`{name}` is on the source API surface, and SKILL.md and references/ do not document it",
                export=name)


def _brief_of(surface: dict | None) -> str:
    """The brief a surface result read: its `inputs.brief`, else skill-brief.yaml."""
    inputs = (surface or {}).get("inputs")
    brief = inputs.get("brief") if isinstance(inputs, dict) else None
    return brief if isinstance(brief, str) and brief else _DEFAULT_BRIEF


# The most names the issue of the inflated-union summary gap lists (#795).
_INFLATED_NAMES_LISTED = 50
# The clauses whose ladder has a tier A rung, so that a brief's `scope.tier_a_include` corrects the
# denominator an inflated `scope.include` union gave them (#795).
# Keep identical to the CLAUSE_LADDERS clauses with a `tier_a_include` rung in load-coverage-inputs.py.
_TIER_A_CLAUSES = frozenset({"stratified-scope", "multi-entry"})


def _inflated_union(surface: dict | None) -> bool:
    """Whether the barrel branch counts an inflated `scope.include` union a
    tier A list corrects: the surface's inflation guard fires, its
    `denominator.surfaceSet` is `scope.include` and its `denominator.clause`
    has a tier A rung. A set the surface lacked (`absentSet`) counted `all`
    in its place, and the specific-modules and empty-barrel clauses count
    `scope.include` whatever tier A list the brief has: each name there
    stays its own gap."""
    guards = (surface or {}).get("guards")
    inflation = guards.get("inflation") if isinstance(guards, dict) else None
    denominator = (surface or {}).get("denominator")
    return (isinstance(inflation, dict) and inflation.get("fires") is True and isinstance(denominator, dict)
            and denominator.get("surfaceSet") == "scope.include" and denominator.get("clause") in _TIER_A_CLAUSES)


def _inflated_union_gap(names: list[str], where: dict[str, str], types: set[str], brief: str,
                        union: object) -> dict:
    """One gap at the brief for the names an inflated `scope.include` union
    counts and the skill does not document, in place of a gap per name: the
    union sweeps in infrastructure, so most of them belong to no authored
    surface (#795). It sits beside the guard's own `denominator-inflation`
    gap at that brief, whose fix it defers to."""
    def label(name: str) -> str:
        notes = (["a type"] if name in types else []) + ([f"`{where[name]}`"] if where.get(name) else [])
        return f"`{name}` ({', '.join(notes)})" if notes else f"`{name}`"

    listed = [label(n) for n in names[:_INFLATED_NAMES_LISTED]]
    more = len(names) - len(listed)
    named = ", ".join(listed) + (f", and {more} more" if more else "")
    size = f" ({union} names)" if _count(union) is not None else ""
    return _gap(
        "Medium", "denominator-inflation", "undocumented names in the inflated scope.include union", brief,
        f"Correct the denominator first, as the denominator-inflation gap for `{brief}` says; then re-run Test "
        "Skill, and the names the corrected denominator counts that the skill does not document come back as gaps.",
        issue=f"the inflation guard fired: the `scope.include` union the denominator counts{size} sweeps in names "
              f"outside the authored surface, and SKILL.md and references/ do not document {len(names)} of them: "
              f"{named}")


def _scoped_out_gap(name: str, row: dict, doc: str | None, brief: str) -> dict:
    """The Medium `stale-documentation` gap of a documented name an entry
    point exports from a file the brief scopes out (#796): its row names
    the `scope.exclude` glob that matches the file, or says no
    `scope.include` glob covers it, or both."""
    file, line, entry = row["file"], _count(row.get("line")), row.get("entry")
    at = f"{file}:{line}" if line else file
    glob = row.get("excludeGlob") if isinstance(row.get("excludeGlob"), str) and row.get("excludeGlob") else None
    uncovered = row.get("outsideInclude") is True
    causes = (["no `scope.include` glob covers that file"] if uncovered else []) + (
        [f"its `scope.exclude` glob `{glob}` matches {'it' if uncovered else 'that file'}"] if glob else [])
    fixes = (["widen `scope.include` to cover that file"] if uncovered else []) + (
        [f"narrow `{glob}` so it no longer matches that file (to remove the glob instead, record a `demoted-exclude` "
         "scope-expansion amendment in the brief)"] if glob else [])
    who = f"the entry point `{entry}`" if isinstance(entry, str) and entry else "an entry point"
    return _gap(
        "Medium", "stale-documentation", f"Stale documentation: {name}", doc or "SKILL.md",
        f"Decide whether `{name}` belongs on the surface: `{brief}` scopes out `{at}`, where it is defined, since "
        f"{' and '.join(causes)}. To keep its documentation, {' and '.join(fixes)}; else remove the documentation "
        f"of `{name}` at {doc or 'SKILL.md'}.",
        issue=f"{_documents(doc, name)}, which {who} exports and `{at}` defines, a file `{brief}` scopes out "
              "(`excluded.outsideScope`)",
        export=name)


def _star_files(surface: dict | None) -> dict[str, list[dict]]:
    """{a file as citations compare it: the `export *` statements from another package it holds} from the
    --surface result's `unresolvedStars` (#1005). A missing list (an older surface) or a malformed one, and an
    item with no file or statement, give none: a list no script checks never halts a run."""
    stars = (surface or {}).get("unresolvedStars")
    cited_path = _sibling("validate-inventory.py")._cited_path
    held: dict[str, list[dict]] = {}
    for star in stars if isinstance(stars, list) else []:
        if (isinstance(star, dict) and isinstance(star.get("file"), str) and star["file"].strip()
                and isinstance(star.get("statement"), str) and star["statement"].strip()):
            held.setdefault(cited_path(star["file"]), []).append(star)
    return held


def _star_entries(item: dict) -> list[dict]:
    """The `entries` of a classified stale item that cite an `export *` line (#1070): each with a `star`, the
    module classify-stale read in the `export *` or `export type *` at its cited line, and a `source_file`, both
    non-empty strings. A missing or malformed `entries` or `star` gives none."""
    entries = item.get("entries")
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("star"), str) and e["star"]
            and isinstance(e.get("source_file"), str) and e["source_file"].strip()
            ] if isinstance(entries, list) else []


def _entry_line(value: object) -> int | None:
    """A map entry's `source_line` as classify-stale reads it (`_coerce_line`): a number, or a string `int()`
    reads, above 0."""
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            return None
    line = _count(value)
    return line if line is not None and line > 0 else None


def _entry_stars(entries: list[dict], stars: dict[str, list[dict]]) -> list[dict]:
    """The `unresolvedStars` statements whose own line one of `entries` (`_star_entries`) cites (#1070): a star of
    the entry's file (as citations compare it, `_star_files`) whose statement names the entry's module, matched
    by file and module and never by line, as load-coverage-inputs.py tells two stars apart (the runner's stars
    carry no line). Each is given as {the statement, the entry's file and line}, the line classify-stale read,
    once."""
    if not entries or not stars:
        return []
    cited_path = _sibling("validate-inventory.py")._cited_path
    specifier = _sibling("load-coverage-inputs.py").STAR_SPECIFIER_RE
    found: list[dict] = []
    for entry in entries:
        for star in stars.get(cited_path(entry["source_file"]), []):
            named = specifier.search(star["statement"])
            if named and named.group(2) == entry["star"]:
                at = {"file": entry["source_file"].strip(), "line": _entry_line(entry.get("source_line")),
                      "statement": star["statement"]}
                if at not in found:
                    found.append(at)
    return found


def _unchecked_star_gap(name: str, stars: list[dict], doc: str | None, mapped: list[dict] | None = None) -> dict:
    """The Info `observation` of a stale name with no `defined_at` that the skill cites at a file holding an
    `export *` from another package (#1005, `stars`): no script reads that package, so the surface cannot hold
    the names it passes on, and the name may well be one of them. Its title is not the Deep tier's
    `Not checked by script: {name}` score-signatures.py records from a signature judge's `doc_errors`, which the
    ledger would read as the same gap at the same line. `mapped` are the stars the name's provenance map
    entries cite at their own lines (#1070, `_entry_stars`) that `stars` does not hold: the issue and
    remediation name them too, at each entry's file and line, since an entry's star, never a skill citation,
    is what reads a fabricated name as not fabricated."""
    def at(group: list[dict]) -> str:
        placed = [(s, _count(s.get("line"))) for s in group]
        return " and ".join(f"`{s['statement']}` (`{s['file']}{f':{line}' if line else ''}`)" for s, line in placed)

    passes = "passes" if len(mapped or []) == 1 else "pass"
    if not stars:
        return _gap(
            "Info", "observation", f"Not checked by script: {name} (another package's export *)", doc or "SKILL.md",
            f"No change unless the other package does not export `{name}`: its provenance map cites it at "
            f"{at(mapped)}, which {passes} on that package's names, and no script reads them, so check by hand that "
            f"the package exports `{name}`.",
            issue=f"{_documents(doc, name)}, which the enumerated source API surface lacks; its provenance map "
                  f"cites it at {at(mapped)}, which {passes} on another package's names and which no script resolves",
            export=name)
    entries = f" its provenance map cites it at {at(mapped)}, which {passes} on that package's names," if mapped else ""
    issue_entries = (f", and its provenance map cites it at {at(mapped)}, which {passes} on another package's names "
                     "and which no script resolves" if mapped else "")
    return _gap(
        "Info", "observation", f"Not checked by script: {name} (another package's export *)", doc or "SKILL.md",
        f"No change unless the other package does not export `{name}`: a file the skill cites passes on that "
        f"package's names through {at(stars)},{entries} and no script reads them, so check by hand that the package "
        f"exports `{name}`.",
        issue=f"{_documents(doc, name)}, which the enumerated source API surface lacks; a file the skill cites "
              f"passes on another package's names through {at(stars)}, which no script resolves{issue_entries}",
        export=name)


def _named_inputs(surface: object, signatures: object) -> tuple[dict | None, set[str], set[str]]:
    """The --surface result, the names --signatures lists in `missingTypes` and the names whose documented
    signature it compared (`comparedNames`), for a result that names its missing and stale exports."""
    types: set[str] = set()
    scored: set[str] = set()
    if signatures is not None:
        signatures = _object(signatures, "--signatures (score-signatures.py)", "missingTypes")
        types = set(_names(signatures, "missingTypes", "--signatures"))
        scored = set(_names(signatures, "comparedNames", "--signatures"))
    if surface is not None:
        surface = _object(surface, "--surface (load-coverage-inputs.py surface)", "exports")
    return surface, types, scored


def _missing_gaps(cov: dict, surface: dict | None, types: set[str], meta: str) -> list[dict]:
    """One gap per `missing` name, at the file and line the surface records for it, or, when the surface counts
    an inflated `scope.include` union a tier A list corrects (`_inflated_union`), one summary gap at the brief in
    their place (#795)."""
    where = _surface_sources(surface)
    missing = _names(cov, "missing", "--input")
    if missing and _inflated_union(surface):
        union = ((surface.get("guards") or {}).get("inflation") or {}).get("scopeIncludeUnion")
        return [_inflated_union_gap(missing, where, types, _brief_of(surface), union)]
    return [_missing_export(name, where.get(name), meta, "type" if name in types else "export") for name in missing]


def _stale_gaps(cov: dict, surface: dict | None, stale: object, scored: set[str],
                skill_dir: str | None, inventory: object = None) -> list[dict]:
    """One gap per `stale` name: fabricated, a documented extra, not checked by script (cited at a file whose
    `export *` from another package no script resolves, #1005, or whose provenance map entry cites such a star's
    own line, `_entry_stars`, which a fabricated name then is not, #1070), or stale documentation (with its own
    wording for a name defined in a file the brief scopes out, #796). A name no line documents (`_documenting_lines`)
    is documented at its first inventory place (`_inventory_places`, #1006), else by the skill. Each of its
    inventory places is a form whose own citations pick a homonym's declaring file first (`_documented_extra_at`,
    #1077)."""
    records: list[dict] = []
    # `excluded` is read once a stale name may be a documented extra
    outside: dict[str, dict] | None = None
    outside_read = False
    # the files holding another package's `export *`, and the skill's lines, read once a name may need them
    stars: dict[str, list[dict]] | None = None
    texts: list[list[str]] | None = None
    classified: dict[str, dict] = {}
    if stale is not None:
        if not isinstance(stale, list):
            raise AdapterError("--stale is not classify-stale JSON (a list)")
        classified = {i["name"]: i for i in stale if isinstance(i, dict) and isinstance(i.get("name"), str)}
    names = _names(cov, "stale", "--input")
    # the lines that document each name, read once for every stale name
    documenting = _documenting_lines(Path(skill_dir)) if skill_dir and names else {}
    # the validated inventory's places of each name's forms (#1077), the first that of a name no line documents
    # as an export (#1006)
    forms = _inventory_forms(inventory)
    placed = _inventory_places(forms)
    for name in names:
        item = classified.get(name) or {}
        cited = item.get("source")
        doc = documenting.get(name) or placed.get(name)
        # the stars whose own line a map entry of the name cites (#1070), read like those stars
        starred = _star_entries(item)
        if starred and stars is None:
            stars = _star_files(surface)
        mapped = _entry_stars(starred, stars or {})
        if item.get("fabricated") is True and not mapped:
            if not isinstance(cited, str) or not cited:
                # a Critical gap needs the line it cites: never downgrade it
                raise AdapterError(f"--stale: {name!r} is fabricated with no source")
            records.append(_gap(
                "Critical", "fabricated-signature", f"Fabricated signature: {name}", cited,
                f"Remove `{name}` from SKILL.md and references/, or correct it to the export the source "
                f"defines: no file its provenance cites defines it (`{cited}`).",
                issue=f"{_documents(doc, name)}, which the source API surface lacks and the cited file does "
                      "not define",
                export=name))
            continue
        if not outside_read:
            outside, outside_read = _outside_scope(surface, classified, skill_dir, forms), True
        extra = _documented_extra_at(name, item, outside, skill_dir, forms.get(name))
        if extra:
            declared, among, modules, named = extra
            # a homonym: the one declaring file its forms' own citations name (#1077), else the skill's
            who = ("the skill cites" if not named else f"its form at `{named[0]}` cites" if len(named) == 1 else
                   f"its forms at {' and '.join(f'`{at}`' for at in named)} cite")
            picked = (f"; of the {among} files that declare it, {who} only "
                      f"`{declared.rsplit(':', 1)[0]}`") if among else ""
            if modules:
                # a package cited with its same-named module, #1012
                same_named = " and ".join(f"`{m.rsplit(':', 1)[0]}`" for m in modules)
                picked = (f"; of the {among} files that declare it, {who} only the package "
                          f"`{declared.rsplit(':', 1)[0]}` and its same-named module {same_named}, so the gap is at "
                          "the package")
            # never routed: update-skill leaves an `observation` alone. Signature scoring compares a
            # documented signature of a name on the surface's records (a nested sub-package's) or on its
            # internal declarations (a documented extra's) alone.
            checked = ("Signature scoring compares its documented signature with its declaration in the source."
                       if name in scored else
                       "Its documented signature was not checked against that declaration.")
            records.append(_gap(
                "Info", "observation", f"Documented extra: {name}", declared,
                f"No change: `{name}` is a documented extra, a name the source still declares at "
                f"`{declared}` outside the enumerated surface, and its documentation stays. {checked}",
                issue=f"{_documents(doc, name)}, which the enumerated source API surface lacks and the source "
                      f"still declares{picked}",
                export=name))
            continue
        if outside is not None and name in outside and _scoped_out_by(outside[name]):
            # an entry point exports it from a file the brief scopes out (#796)
            records.append(_scoped_out_gap(name, outside[name], doc, _brief_of(surface)))
            continue
        if item.get("defined_at") is None:
            # no file declares it, and the skill cites a file that passes on another package's names (#1005), or
            # its provenance map cites such a star's own line (#1070)
            through: list[dict] = []
            if skill_dir:
                citations = _sibling("validate-inventory.py")
                if stars is None:
                    stars = _star_files(surface)
                if texts is None:
                    texts = citations.skill_markdown_lines(Path(skill_dir)) if stars else []
                cited = citations._skill_cited_files(Path(skill_dir), name, texts) if stars else set()
                through = [s for f in sorted(cited) for s in stars.get(f, [])]
            if through or mapped:
                # the stars a map entry cites that no skill citation gives are named too: they, not a citation,
                # are what lifts a fabricated name (#1070)
                cited_path = _sibling("validate-inventory.py")._cited_path
                given = {(cited_path(s["file"]), s["statement"]) for s in through}
                records.append(_unchecked_star_gap(
                    name, through, doc, [s for s in mapped if (cited_path(s["file"]), s["statement"]) not in given]))
                continue
        records.append(_gap(
            "Medium", "stale-documentation", f"Stale documentation: {name}", doc or "SKILL.md",
            f"Check `{name}` against the source and update or remove its documentation at "
            f"{doc or 'SKILL.md'}: the enumerated source surface does not export it.",
            issue=f"{_documents(doc, name)}, which the enumerated source API surface lacks",
            export=name))
    return records


def _residual_gap(cov: dict, meta: str) -> list[dict]:
    """A counted set's residual: the exports the stored count counts beyond the names the set lists, one gap
    when `missingCount` exceeds the listed `missing` names."""
    listed = len(_names(cov, "missing", "--input"))
    missing, denominator = _count(cov.get("missingCount")), _count(cov.get("denominator"))
    residual = (missing or 0) - listed
    if residual <= 0:
        return []
    set_name = cov.get("surfaceSet") if isinstance(cov.get("surfaceSet"), str) else "named"
    size = _count(cov.get("surfaceSetSize"))
    names = f"{size} names" if size is not None else "names"
    return [_gap(
        "Medium", "missing-export", f"{residual} of {denominator} exports not documented beyond the {set_name} set",
        meta,
        f"Find the {residual} exports the stored count (`stats.effective_denominator`) counts beyond the {names} "
        f"of the `{set_name}` set (`{meta}` lists the exports) and document each with its signature; a stale "
        "stored count is recounted by re-running Create Skill.",
        issue=f"of the {denominator} exports the stored count counts, {missing} are not documented: the "
              f"`{set_name}` set names {listed} of them, and the other {residual} are exports the count holds "
              "beyond the set's names")]


def from_coverage(cov: object, surface: object = None, signatures: object = None, numerator: object = None,
                  stale: object = None, provenance: object = None, skill_dir: str | None = None,
                  metadata: str | None = None, inventory: object = None) -> list[dict]:
    """reconcile-coverage.py's result: missing and stale names, or the missing count."""
    cov = _object(cov, "--input (reconcile-coverage.py)", "branch")
    meta = metadata or _DEFAULT_METADATA
    branch = cov["branch"]
    records: list[dict] = []
    if branch == "enumerated":
        surface, types, scored = _named_inputs(surface, signatures)
        records += _missing_gaps(cov, surface, types, meta)
        records += _stale_gaps(cov, surface, stale, scored, skill_dir, inventory)
    elif branch in ("scalar", "stack"):
        # A scalar result that counts its set lists its missing names, and one on a surface read from the
        # source its stale names: each is recorded as the barrel branch's are.
        counted = branch == "scalar" and cov.get("numeratorSource") == "surface"
        stale_named = branch == "scalar" and cov.get("staleApplicable") is True
        if counted or stale_named:
            surface, types, scored = _named_inputs(surface, signatures)
        if branch == "scalar" and cov.get("numeratorSource") == "verified":
            if numerator is None:
                raise AdapterError("the scalar count used the verified numerator: pass its result with "
                                   "--numerator")
            absent = _names(_object(numerator, "--numerator (verify-declared-numerator.py)", "absent"),
                            "absent", "--numerator")
            where = _provenance_sources(_object(provenance, "--provenance (provenance map)", "entries")
                                        if provenance is not None else None)
            records += [_missing_export(name, where.get(name), meta) for name in absent]
        elif counted:
            records += _missing_gaps(cov, surface, types, meta)
            records += _residual_gap(cov, meta)
        else:
            missing, denominator = _count(cov.get("missingCount")), _count(cov.get("denominator"))
            if missing:
                records.append(_gap(
                    "Medium", "missing-export", f"{missing} of {denominator} exports not documented", meta,
                    f"Find the {missing} exports the denominator counts that SKILL.md and references/ do not "
                    f"name (`{meta}` lists the exports) and document each with its signature.",
                    issue=f"SKILL.md and references/ name {cov.get('documented')} of the {denominator} exports "
                          f"the {branch} denominator counts"))
        if stale_named:
            records += _stale_gaps(cov, surface, stale, scored, skill_dir, inventory)
    elif branch != "docsOnly":
        raise AdapterError(f"--input (reconcile-coverage.py): unknown branch {branch!r}")
    return records


def from_guards(surface: object, metadata: str | None = None) -> list[dict]:
    """load-coverage-inputs.py surface's deflation, inflation and stale-scope guards."""
    surface = _object(surface, "--input (load-coverage-inputs.py surface)", "guards", "inputs")
    guards = surface["guards"]
    if guards is None:
        return []
    if not isinstance(guards, dict):
        raise AdapterError("--input (load-coverage-inputs.py surface): 'guards' must be an object or null")
    inputs = surface["inputs"] if isinstance(surface["inputs"], dict) else {}
    meta = metadata or inputs.get("metadata") or _DEFAULT_METADATA
    brief = inputs.get("brief") or _DEFAULT_BRIEF
    records: list[dict] = []
    stale = guards.get("staleScope") or {}
    label = "--input (load-coverage-inputs.py surface): guards.staleScope"
    # A tier A glob that matches no file counts no name, and so does one that
    # matches only excluded files or files that define no name: when the
    # guards fire, the brief has no tier A glob, or none of its globs counts a
    # name. `tierAInclude` (the brief's tier A globs) is absent from a surface
    # older than #712, where only the stale globs say the brief has some.
    tier_a_globs = _names(stale, "unmatchedTierAInclude", label)
    brief_tier_a = list(dict.fromkeys(
        _names(guards, "tierAInclude", "--input (load-coverage-inputs.py surface): guards") + tier_a_globs))
    if not brief_tier_a:
        no_tier_a = "the brief has no `scope.tier_a_include`"
    elif set(brief_tier_a) <= set(tier_a_globs):
        no_tier_a = "no `scope.tier_a_include` glob in the brief matches a file"
    else:
        no_tier_a = "no `scope.tier_a_include` glob in the brief counts a public name"
    deflation = guards.get("deflation") or {}
    inflation = guards.get("inflation") or {}
    stored = _count(deflation.get("effectiveDenominator")) or 0
    # No remediation sets `stats.effective_denominator` by hand: Update Skill's recount drops such a value (#803).
    # Both guards on the scope.include union name one fix, the brief's tier A list (#788).
    both = (deflation.get("fires") is True and inflation.get("fires") is True
            and deflation.get("basis") != "tier_a_include")
    # On an umbrella barrel the names are re-exports, each counted at the file that defines it, never the barrel.
    umbrella = (" rather than the root barrel, an umbrella of re-exports"
                if (guards.get("umbrella") or {}).get("umbrella") is True else "")
    verb = (f"Edit `scope.tier_a_include` in `{brief}` so its globs list" if brief_tier_a
            else f"Add `scope.tier_a_include` to `{brief}`, listing")
    # Only Create Skill always writes metadata.json, and it stores the runner's count only under this rule.
    stores = ("when `effective_denominator_decision.store` holds and the brief's `scope.notes` documents the "
              "stratification, and otherwise drops the stored count")
    joint = (f"{verb} the files that define the authored names{umbrella}: the `scope.include` union is itself "
             "inflated, so neither it nor the smaller stored count measures the authored surface. Then re-run "
             f"Create Skill to recount `stats.effective_denominator` in `{meta}` from the tier A set: it stores "
             f"that count {stores}.")
    if deflation.get("fires") is True and deflation.get("basis") == "tier_a_include":
        # A stored count the brief's tier A set disagrees with, either way: stale, so count it again (#813).
        pct = deflation.get("pct")
        if pct is None:  # a stored 0: no percentage against it
            against = f" against a `stats.effective_denominator` of {stored}"
        else:
            below = isinstance(pct, (int, float)) and pct < 0
            against = (f", {-pct if below else pct}% {'below' if below else 'above'} `stats.effective_denominator` "
                       f"({deflation.get('effectiveDenominator')})")
        # Until then: the set the denominator actually counts (a ladder with no tier A rung counts scope.include),
        # or, on an incomplete extraction's tier A set below the stored count, the stored count.
        denominator = surface.get("denominator") if isinstance(surface.get("denominator"), dict) else {}
        extraction = surface.get("extraction") if isinstance(surface.get("extraction"), dict) else {}
        if denominator.get("branch") == "scalar":
            until = " Until then the stored count stays the denominator" + (
                ": the extraction is incomplete, so the tier A set can miss names." if extraction.get("status")
                == "incomplete" else ".")
        elif isinstance(denominator.get("surfaceSet"), str):
            until = f" Until then Test Skill counts the `{denominator['surfaceSet']}` set as the denominator."
        else:
            until = ""
        records.append(_gap(
            "Medium", "metadata-drift",
            "denominator drift: effective_denominator disagrees with the brief's tier_a_include set", meta,
            f"Re-run Create Skill to recount `stats.effective_denominator` in `{meta}`: it stores the runner's count "
            f"of the brief's `scope.tier_a_include` set {stores}.{until}",
            issue=f"the brief's `scope.tier_a_include` set counts {deflation.get('rederived')} exports{against}"))
    elif deflation.get("fires") is True:
        if deflation.get("pct") is None:  # a stored 0: no percentage above it
            above = f" against a `stats.effective_denominator` of {stored}"
        else:
            above = (f", {deflation.get('pct')}% above `stats.effective_denominator` "
                     f"({deflation.get('effectiveDenominator')})")
        if both:
            fix = joint
        elif deflation.get("pct") is None:  # a 0 measures no tier: count it again
            first = ("Edit `scope.tier_a_include` in the brief so its globs match the files that define the "
                     "authored tier" if brief_tier_a else "Check `scope.include` in the brief")
            fix = (f"{first}, then re-run Create Skill so `stats.effective_denominator` in `{meta}` is counted "
                   "again.")
        elif brief_tier_a:
            fix = (f"Re-run Create Skill to recount `stats.effective_denominator` in `{meta}` from the public surface "
                   f"the source re-derives (it stores that count {stores}), or edit `scope.tier_a_include` in the "
                   "brief so its globs match the files of the authored tier the smaller count measures.")
        else:
            fix = (f"Re-run Create Skill to recount `stats.effective_denominator` in `{meta}` from the public surface "
                   f"the source re-derives (it stores that count {stores}), or add `scope.tier_a_include` to the "
                   "brief to name the authored tier the smaller count measures.")
        records.append(_gap(
            "Medium", "metadata-drift",
            "denominator deflation: effective_denominator below source public surface without tier_a_include",
            meta, fix,
            issue=f"the re-derived surface counts {deflation.get('rederived')} exports{above}, and {no_tier_a}"))
    if inflation.get("fires") is True:
        if both:
            fix = joint
        elif brief_tier_a:
            fix = (f"Edit `scope.tier_a_include` in `{brief}` so its globs match the files of the authored "
                   f"surface{umbrella}: the denominator then counts it instead of the coarse `scope.include` union.")
        else:
            fix = (f"Add `scope.tier_a_include` to `{brief}`, listing the files of the authored surface{umbrella}, "
                   "so the denominator counts it instead of the coarse `scope.include` union.")
        records.append(_gap(
            "Medium", "denominator-inflation",
            "denominator inflation: coarse scope.include union exceeds authored surface", brief, fix,
            issue=f"the `scope.include` union counts {inflation.get('scopeIncludeUnion')} exports, "
                  f"{inflation.get('pct')}% above the {inflation.get('provenanceEntries')} provenance entries, "
                  f"and {no_tier_a}"))
    if stale.get("fires") is True:
        globs = _names(stale, "unmatchedInclude", label)
        restored = sorted({(r["name"], r["file"] if isinstance(r.get("file"), str) else "")
                           for r in _list(stale, "restored", label)
                           if isinstance(r, dict) and isinstance(r.get("name"), str) and r["name"]})
        names = ", ".join(f"`{name}` in `{file}`" if file else f"`{name}`" for name, file in restored)
        if len(globs) == 1:
            unmatched = f"the `scope.include` glob {_code(globs)} matches no file in the source tested"
        else:
            unmatched = f"the `scope.include` globs {_code(globs)} match no file in the source tested"
        if not restored:
            back = "no root export was restored"
        elif len(restored) == 1:
            back = f"the `all` set restores 1 root export, defined in a file no include glob covers: {names}"
        else:
            back = (f"the `all` set restores {len(restored)} root exports, defined in files no include glob "
                    f"covers: {names}")
        if len(tier_a_globs) == 1:
            tier_a = (f"the `scope.tier_a_include` glob {_code(tier_a_globs)} matches no file in the source "
                      "tested, so it counts no name")
        else:
            tier_a = (f"the `scope.tier_a_include` globs {_code(tier_a_globs)} match no file in the source "
                      "tested, so they count no name")
        # A restored name stays only while an include glob matches no file, so once the globs match, its file
        # needs an include glob to keep it, or an exclude glob to leave it out (#1009).
        files = sorted({file for _, file in restored if file})
        defining = f" ({_code(files)})" if files else ""
        kept = (" A restored export stays on the surface only while an include glob matches no file, so for each "
                f"file that defines one{defining} add a `scope.include` glob that covers it when the skill "
                "documents its exports, or a `scope.exclude` glob when the skill leaves them out.") if restored else ""
        if not tier_a_globs:  # the include globs alone, as #677 wrote the gap
            lists, rewrite, clauses = ["scope.include"], "an include glob", [unmatched, back]
        elif not globs:  # no include glob is stale, so nothing was restored
            lists, rewrite, clauses, kept = ["scope.tier_a_include"], "a tier A glob", [tier_a], ""
        else:
            lists = ["scope.include", "scope.tier_a_include"]
            rewrite, clauses = "an include or tier A glob", [unmatched, back, tier_a]
        edit = " and ".join(f"`{key}`" for key in lists)
        records.append(_gap(
            "Medium", "brief-scope-stale", f"stale brief scope: {' and '.join(lists)} globs match no source file",
            brief,
            f"Edit {edit} in `{brief}` by hand so each glob matches the files it meant in this version of the "
            f"source (update-skill does not rewrite {rewrite}).{kept}",
            issue="; ".join(clauses)))
    return records


def from_numerator(numerator: object, metadata: str | None = None) -> list[dict]:
    """verify-declared-numerator.py's result: the numerator inflation gap."""
    numerator = _object(numerator, "--input (verify-declared-numerator.py)", "inflated")
    if numerator["inflated"] is not True:
        return []
    meta = metadata or _DEFAULT_METADATA
    declared, verified = _count(numerator.get("declared")) or 0, _count(numerator.get("verified")) or 0
    absent = _names(numerator, "absent", "--input")
    return [_gap(
        "High", "numerator-inflation",
        f"numerator inflation: {declared - verified} of {declared} declared exports absent from "
        "SKILL.md/references",
        meta,
        f"Document the absent exports in SKILL.md or references/: the skill documents {verified} of its "
        f"{declared} declared exports.",
        issue=f"a declared count (`stats.exports_documented`, or the provenance map's distinct entry names) "
              f"equals `stats.effective_denominator`, and these declared exports are absent from SKILL.md and "
              f"references/: {_code(absent)}")]


def from_metadata_coherence(result: object, metadata: str | None = None) -> list[dict]:
    """check-metadata-coherence.py's findings: count drift and multi-denominator notes."""
    result = _object(result, "--input (check-metadata-coherence.py)", "findings")
    meta = metadata or _DEFAULT_METADATA
    records: list[dict] = []
    for index, finding in enumerate(_list(result, "findings", "--input")):
        if not isinstance(finding, dict) or not isinstance(finding.get("title"), str):
            raise AdapterError(f"--input: findings[{index}] has no title")
        detail = finding.get("detail") if isinstance(finding.get("detail"), str) else None
        if finding.get("severity") == "Medium" and "documented-surface" in finding["title"]:
            # `stats.exports_documented` and the confidence_distribution sum count every provenance entry, while
            # the named-export count leaves out `Type::method` entries: a re-run reproduces that difference
            records.append(_gap(
                "Medium", "metadata-drift", finding["title"], meta,
                f"No count in `{meta}` needs a fix when `stats.exports_documented` and the `confidence_distribution` "
                "sum agree: both count every provenance map entry, while the named-export count leaves out the "
                "`Type::method` entries, so the counts differ by the methods the skill documents. When those two "
                "disagree, Update Skill or Create Skill recounts both from the provenance map the next time it "
                "writes the skill; a hand edit does not hold.",
                issue=detail))
        elif finding.get("severity") == "Medium":
            records.append(_gap(
                "Medium", "metadata-drift", finding["title"], meta,
                f"Re-run Create Skill, which rebuilds `exports[]` and `stats.exports_public_api` in `{meta}` from "
                "the source. Update Skill does not repair this drift: each time it writes the skill it recounts "
                "`stats.exports_public_api` from the source and keeps `exports[]`, adding or dropping only the "
                "names its provenance map changes, so a metadata patch does not hold.",
                issue=detail))
        elif finding.get("severity") == "Info":
            records.append(_gap(
                "Info", "multi-denominator", finding["title"], meta,
                "No action required: the barrel and the documented surface measure different sets by design, "
                "and the report records both counts.",
                issue=detail))
        else:
            raise AdapterError(f"--input: findings[{index}] has severity {finding.get('severity')!r}, "
                               "neither Medium nor Info")
    return records


def _aliased_items(stale: object) -> dict[str, dict]:
    """name -> its classify-stale item (`--stale`) when it is `aliased` with a `file:line` `defined_at`: a rename
    elsewhere declares the name, so a provenance line gap of it names the alias. Raises AdapterError, as the
    coverage adapter does, when the result is not a list."""
    if stale is None:
        return {}
    if not isinstance(stale, list):
        raise AdapterError("--stale is not classify-stale JSON (a list)")
    return {i["name"]: i for i in stale
            if isinstance(i, dict) and isinstance(i.get("name"), str) and i.get("reason") == "aliased"
            and isinstance(i.get("defined_at"), str) and i["defined_at"].rpartition(":")[0]
            and i["defined_at"].rpartition(":")[2].isdigit()}


def _star_lines(stale: object) -> dict[tuple[str, str, int | None], str]:
    """(name, an entry's file as citations compare it, its line, `_entry_line`) -> the module of the `export *`
    or `export type *` at that line, for each entry of a classify-stale item (`--stale`) with a `star`
    (`_star_entries`, #1070) that names another package: a module that is no relative or absolute path. A
    missing or malformed result gives none (`_aliased_items` refuses one that is no list)."""
    found: dict[tuple[str, str, int | None], str] = {}
    for item in stale if isinstance(stale, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        for entry in _star_entries(item):
            if not entry["star"].startswith((".", "/")):
                cited_path = _sibling("validate-inventory.py")._cited_path
                key = (item["name"], cited_path(entry["source_file"]), _entry_line(entry.get("source_line")))
                found.setdefault(key, entry["star"])
    return found


def _alias_fix(name: str, file: str, item: dict) -> str:
    """The remediation of an unverified provenance line of a name classify-stale found `aliased` (`item`): record
    the rename if no other entry already has its `export_name`, else cite the alias. The map keys on
    `export_name`, so it holds one `default` entry at most (a barrel of `export { default as X }` lines renames
    several): a rename of `default` takes the alias alone. It never says which cited file declares the renamed
    name: any checked entry's may."""
    alias, local = item["defined_at"], item.get("renames")
    alias_file, _, alias_line = alias.rpartition(":")
    named = isinstance(local, str) and bool(local)
    renamed = f"`{local}`" if named else "a name a cited file declares"
    of = f"{renamed}, which a cited file declares" if named else renamed
    head = (f"`{name}` is an alias of {of}; the source declares the alias at `{alias}`, and no line of `{file}` "
            f"defines `{name}`. ")
    cite = (f"the alias: set `source_file` to `{alias_file}` and `source_line` to `{alias_line}`, and move the "
            f"citations of `{name}` there.")
    if local == "default":
        return f"{head}Cite {cite}"
    guard = f"`export_name` {renamed}" if named else "that name as its `export_name`"
    return (f"{head}If no other entry already has {guard}, record the rename in this provenance entry: set "
            f"`export_name` to {renamed}, add `reexported_as` `{name}`, cite the line that declares {renamed} and "
            f"move the citations of `{name}` to that line. Or cite {cite}")


def from_provenance_line(result: object, stale: object = None) -> list[dict]:
    """verify's `stale[]` items: provenance line gaps, one per citation that does not resolve or is not the
    definition line. `stale` (classify-stale's result, `--stale`, or None) gives the names a rename declares: an
    unverified line of one names the alias and, unless the name it renames is `default`, how to record the rename
    (#911). It also gives the entries at another package's `export *` line (`_star_lines`): an unverified line
    of one says the line passes on that package's names and asks no change unless it lacks the name, as the
    coverage call's observation of it does (#1070)."""
    result = _object(result, "--input (skf-verify-provenance-completeness.py verify)", "stale")
    aliased = _aliased_items(stale)
    starred = _star_lines(stale)
    records: list[dict] = []
    for item in _list(result, "stale", "--input"):
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        name, file, line = item.get("export_name"), item.get("source_file"), item.get("source_line")
        where = f"{file}:{line}"
        if reason == "file-missing":
            records.append(_gap(
                "Low", "provenance-line", f"Provenance file is missing for {name}", where,
                f"Set the provenance `source_file` and `source_line` of `{name}` to the file and line that define "
                "it in the pinned source, and move its citations there. update-skill `--from-test-report` does not "
                "repair this: it leaves the entry unchanged, with a warning that names the file.",
                issue=f"the provenance map records `{name}` at `{where}`, but the pinned source has no readable "
                      f"file `{file}`; the export may live in another file, such as one with another extension.",
                export=name))
            continue
        if reason == "line-out-of-bounds":
            records.append(_gap(
                "Low", "provenance-line", f"Provenance line is out of range for {name}", where,
                f"Set the provenance `source_line` of `{name}` in `{file}` to the line that defines it and move "
                "its citations to that line; update-skill `--from-test-report` applies this when the file defines "
                "it on one line.",
                issue=f"the provenance map records `{name}` at `{where}`, which is not a line of `{file}` (past "
                      "its end, or below 1).",
                export=name))
            continue
        if reason == "line-invalid":  # no line number to cite: the Source is the file alone
            records.append(_gap(
                "Info", "provenance-unverified", f"Provenance line not verified for {name}", f"{file}",
                f"Set the provenance `source_line` of `{name}` in `{file}` to the number of the line that defines "
                "it.",
                issue=f"the provenance map records `{name}` in `{file}` at line `{line}`, which is not a line "
                      "number, so no rule could check it; check by hand",
                export=name))
            continue
        if reason != "line-not-definition":
            continue
        defs = [n for n in item.get("definition_lines") or [] if _count(n) is not None]
        base = item.get("folded_to") if isinstance(item.get("folded_to"), str) and item.get("folded_to") else None
        # a bookkeeping variant the file never names was checked against its base (#847)
        folded = f" `{name}` is a bookkeeping variant `{file}` never names, checked against its base `{base}`." \
            if base else ""
        if defs:
            lines = ", ".join(str(n) for n in defs)
            records.append(_gap(
                "Low", "provenance-line", f"Provenance line is not the definition of {name}", where,
                f"Set the provenance `source_line` of `{name}` in `{file}` to its definition line ({lines}) "
                "and move its citations to that line; update-skill `--from-test-report` applies this when the "
                "file defines it on one line.",
                issue=f"the provenance map records `{name}` at `{where}`, which is not the line that defines "
                      f"it; the lines that define it are {lines}.{folded}",
                export=name))
        else:
            alias = aliased[name] if isinstance(name, str) and name in aliased else None
            # an entry at another package's `export *` line: no line of its file can define the name (#1070)
            star = None if alias or not starred or not isinstance(file, str) else starred.get(
                (name, _sibling("validate-inventory.py")._cited_path(file), _entry_line(line)))
            fix = _alias_fix(name, file, alias) if alias else (
                f"No change unless `{star}` does not export `{name}`: line {line} of `{file}` is an `export *` "
                f"from that package, which passes on its names, so no line of `{file}` defines `{name}`, and no "
                f"script reads them; check by hand that `{star}` exports `{name}`." if star else
                f"Open `{file}` and confirm that line {line} defines `{base or name}`; if another line does, set "
                "the provenance `source_line` to it.")
            issue = (f"no line of `{file}` defines `{name}`: the source declares it only as the alias at "
                     f"`{alias['defined_at']}`" if alias else
                     f"line {line} of `{file}` is an `export *` from `{star}`, another package whose names no "
                     f"script reads, so no line of `{file}` defines `{name}`; check by hand" if star else
                     f"the line-check rules found no definition line for `{name}` in `{file}`; check by hand")
            records.append(_gap(
                "Info", "provenance-unverified", f"Provenance line not verified for {name}", where, fix,
                issue=issue + (f".{folded}" if folded else ""),
                export=name))
    return records


def without_fabricated(ledger: dict, records: list[dict]) -> list[dict]:
    """`--from provenance-line`'s records but those of an export the ledger already records as a
    `fabricated-signature` gap: coverage-check §5b appends that record first, and an export the source no longer
    holds takes no provenance line fix."""
    fabricated = {r.get("export") for r in ledger["records"] if r.get("category") == "fabricated-signature"}
    return [r for r in records if not r.get("export") or r.get("export") not in fabricated]


def from_coherence(result: object) -> list[dict]:
    """aggregate-coherence.py's invalid references."""
    result = _object(result, "--input (aggregate-coherence.py)", "invalidReferences")
    records: list[dict] = []
    for index, ref in enumerate(_list(result, "invalidReferences", "--input")):
        if not isinstance(ref, dict):
            raise AdapterError(f"--input: invalidReferences[{index}] is not an object")
        target, line = ref.get("target"), _count(ref.get("line"))
        where = f"SKILL.md:{line}" if line is not None else "SKILL.md"
        status = ref.get("status")
        if status == "missing":
            records.append(_gap(
                "Critical", "broken-reference", f"coherence: broken reference: {target}", where,
                f"Point the reference to `{target}` at {where} at a target that exists, or remove it: "
                "nothing exists at its target.",
                issue="; ".join(i for i in ref.get("issues") or [] if isinstance(i, str)) or None))
        elif status == "inaccurate":
            issues = "; ".join(i for i in ref.get("issues") or [] if isinstance(i, str))
            records.append(_gap(
                "High", "inaccurate-reference", f"coherence: inaccurate reference: {target}", where,
                f"Correct the reference to `{target}` at {where} so it matches its target"
                + (f": {issues}." if issues else "."),
                issue=issues or None))
        elif status == "escapes":
            canonical = ref.get("canonical")
            records.append(_gap(
                "High", "reference-escape",
                f"coherence: reference escapes skill/source sandbox: {target} → {canonical}", where,
                f"Point the reference to `{target}` at {where} inside the skill package or its source tree, "
                f"or remove it: it resolves to `{canonical}`."))
        else:
            raise AdapterError(f"--input: invalidReferences[{index}] has an unknown status {status!r}")
    return records


def _structure_shape(data: object) -> str | None:
    """Which skf-scan-skill-md-structure.py result `data` is."""
    if not isinstance(data, dict):
        return None
    if all(isinstance(data.get(f), dict) and "satisfied" in data[f] for f in FAMILIES):
        return "required-sections"
    if "zero_usage" in data:
        return "usage-scope"
    if "unbalanced_fences" in data:
        return "scan"
    if "references" in data and "counts" in data:
        return "reference-check"
    return None


def _scripts_assets_gap(data: dict, prefix: str) -> list[dict]:
    section = data.get("scripts_assets")
    if not isinstance(section, dict) or section.get("missing") is not True:
        return []
    folders = [f for f in section.get("folders") or [] if isinstance(f, str)]
    named = " and ".join(f"`{f}/`" for f in folders) or "`scripts/` and `assets/`"
    return [_gap(
        "Medium", "scripts-assets",
        f"{prefix}: scripts/assets directory exists but Scripts & Assets section missing", "SKILL.md",
        f"Add a `## Scripts & Assets` section to SKILL.md that lists each file in {named} with its purpose.")]


def from_structure(results: list[object], served: list[str] | None = None) -> list[dict]:
    """skf-scan-skill-md-structure.py results: the naive structural gaps, and
    the Scripts & Assets gap of either mode."""
    served_set = set(served or [])
    records: list[dict] = []
    for index, data in enumerate(results):
        shape = _structure_shape(data)
        if shape is None:
            raise AdapterError(f"--input #{index + 1} is not a scan, scan --required-sections, usage-scope or "
                               "reference-check result")
        if shape == "required-sections":
            for family in FAMILIES:
                entry = data[family]
                if entry.get("satisfied") is True or family in served_set:
                    continue
                if family == "description" and data.get("frontmatter_description") is True:
                    continue
                tried = [t for t in entry.get("tried") or [] if isinstance(t, str)]
                records.append(_gap(
                    "High", "structural", f"naive-coherence: missing required section: {family}", "SKILL.md",
                    _SECTION_FIX[family],
                    issue=f"no heading of SKILL.md serves the {family} family (synonyms tried: "
                          f"{', '.join(tried)})"))
        elif shape == "scan":
            if data.get("unbalanced_fences") is True:
                records.append(_gap(
                    "High", "structural", "naive-coherence: unbalanced code fence (unclosed block)", "SKILL.md",
                    "Close the code block SKILL.md leaves open with a fence line of three backticks.",
                    issue=f"SKILL.md has {data.get('fence_count')} fence lines, so one block is never closed"))
            for fence in _list(data, "bare_opening_fences", "--input"):
                line = _count(fence.get("line")) if isinstance(fence, dict) else None
                records.append(_gap(
                    "Medium", "structural",
                    f"naive-coherence: opening code fence at line {line} missing language tag",
                    f"SKILL.md:{line}",
                    f"Add a language tag (such as `bash` or `python`) to the opening fence at SKILL.md line "
                    f"{line}."))
            for row in _list(data, "table_drift", "--input"):
                if not isinstance(row, dict):
                    continue
                line, expected = _count(row.get("line")), _count(row.get("expected_cols"))
                where = f"section `{row['section']}`: " if row.get("section") else ""
                records.append(_gap(
                    "Medium", "structural",
                    f"naive-coherence: table row at line {line} has {row.get('actual_cols')} columns; "
                    f"header has {expected}",
                    f"SKILL.md:{line}",
                    f"Give the row at SKILL.md line {line} the {expected} columns its header has (write a pipe "
                    "inside a cell as `\\|`).",
                    issue=f"{where}{row.get('row')}" if row.get("row") else None))
            records += _scripts_assets_gap(data, "naive-coherence")
        elif shape == "usage-scope":
            for export in _list(data, "zero_usage", "--input"):
                if not isinstance(export, dict) or not isinstance(export.get("name"), str):
                    continue
                name, kind = export["name"], export.get("kind") or "export"
                records.append(_gap(
                    "Medium", "structural",
                    f"naive-coherence: exported {kind} `{name}` is not referenced in any usage-family "
                    "section or reference file",
                    "SKILL.md",
                    f"Add an example that calls `{name}` to SKILL.md's usage section (or to a references/ file "
                    "for a split body).",
                    export=name))
        else:
            records += _scripts_assets_gap(data, "coherence")
    return records


def build_records(args: argparse.Namespace) -> list[dict]:
    """The records `append --from` appends. Raises AdapterError."""
    kind = args.adapter
    stray = sorted(o for o in ALL_ADAPTER_OPTIONS - ADAPTER_OPTIONS[kind] if getattr(args, o) is not None)
    if stray:
        flags = ", ".join("--" + o.replace("_", "-") for o in stray)
        raise AdapterError(f"--from {kind} does not read {flags}")
    inputs = args.input or []
    if not inputs or (kind != "structure" and len(inputs) > 1):
        wanted = "one or more --input files" if kind == "structure" else "one --input file"
        raise AdapterError(f"--from {kind} reads {wanted}")
    if kind == "structure":
        return from_structure([read_result(p, "--input") for p in inputs], args.served)
    data = read_result(inputs[0], "--input")
    if kind == "coverage":
        files = {o: read_result(getattr(args, o), "--" + o) if getattr(args, o) is not None else None
                 for o in ("surface", "signatures", "numerator", "stale", "provenance", "inventory")}
        return from_coverage(data, skill_dir=args.skill_dir, metadata=args.metadata, **files)
    if kind == "guards":
        return from_guards(data, args.metadata)
    if kind == "numerator":
        return from_numerator(data, args.metadata)
    if kind == "metadata-coherence":
        return from_metadata_coherence(data, args.metadata)
    if kind == "provenance-line":
        stale = read_result(args.stale, "--stale") if args.stale is not None else None
        return from_provenance_line(data, stale)
    return from_coherence(data)


# --------------------------------------------------------------------------
# Gap Report
# --------------------------------------------------------------------------


def render_gap_report(ledger: dict, heading: bool = False) -> str:
    """The Gap Report section body, from the ledger (report.md §4c writes it)."""
    records = ordered(ledger["records"])
    counts = count_by_severity(records)
    blocking = sum(1 for r in records if is_blocking(r))
    after_gate = counts["Critical"] + counts["High"] - blocking
    lines: list[str] = []
    if heading:
        lines += ["## Gap Report", ""]
    lines += [
        f"**Total Gaps:** {len(records)}",
        f"**Blocking (Critical + High):** {blocking}",
        f"**Non-blocking (Medium + Low + Info):** {len(records) - blocking - after_gate}",
    ]
    if after_gate:
        lines.append(f"**Found after the hard gate (Critical + High, non-blocking):** {after_gate}")
    lines.append("")
    if not records:
        lines += ["No gaps found.", ""]
        return "\n".join(lines)
    lines += [
        "### Remediation Summary",
        "",
        "| Severity | Count | Estimated Effort |",
        "|----------|-------|------------------|",
    ]
    for severity in SEVERITIES:
        # each category of the row's gaps, in the order its first gap comes (#1047)
        by_category: dict[str, int] = {}
        for gap in records:
            if gap["severity"] == severity:
                by_category[gap["category"]] = by_category.get(gap["category"], 0) + 1
        effort = "; ".join(f"{c} ({n}): {ACTIONS[c]}" for c, n in by_category.items()) or "None"
        lines.append(f"| {severity} | {counts[severity]} | {effort} |")
    lines += [f"| **Total** | **{len(records)}** | |", ""]
    for record in records:
        lines += [
            f"### {record['id']}: {record['title']}",
            "",
            f"**Severity:** {record['severity']}",
            # The group comes from the category, as at append time: a ledger
            # written by hand may lack it.
            f"**Category:** {CATEGORIES[record['category']][0]} ({record['category']})",
            f"**Source:** {record['source']}",
        ]
        if record.get("export"):
            lines.append(f"**Export:** {record['export']}")
        lines.append("")
        if record.get("issue"):
            lines += [f"**Issue:** {record['issue']}", ""]
        lines += [f"**Remediation:** {record['remediation']}", ""]
    return "\n".join(lines)


def summarize(path: Path, ledger: dict) -> dict:
    records = ledger["records"]
    counts = count_by_severity(records)
    by_category: dict[str, int] = {}
    for record in records:
        by_category[record["category"]] = by_category.get(record["category"], 0) + 1
    blocking = sum(1 for r in records if is_blocking(r))
    return {
        "status": "ok",
        "ledger": str(path),
        "run_id": ledger.get("run_id"),
        "stages": list(ledger["stages"]),
        "total": len(records),
        "counts": counts,
        "blocking": blocking,
        "non_blocking": len(records) - blocking,
        "by_category": dict(sorted(by_category.items())),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _emit(payload: dict, stream=None) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def _error(code: str, message: str, **extra) -> dict:
    return {"status": "error", "code": code, "error": message, **extra}


def _read_records(args: argparse.Namespace) -> list:
    """The records an append reads: built by --from, else from each --input
    file in turn, else from stdin. Raises AdapterError, OSError or ValueError."""
    if args.adapter:
        return build_records(args)
    given = sorted(o for o in ALL_ADAPTER_OPTIONS if getattr(args, o) is not None)
    if given:
        flags = ", ".join("--" + o.replace("_", "-") for o in given)
        raise AdapterError(f"{flags} work only with --from")
    if not args.input:
        # A byte order mark on stdin (a Windows editor or shell) is not JSON.
        return parse_input(sys.stdin.read().removeprefix("\ufeff"))
    records: list = []
    for path in args.input:
        records += parse_input(Path(path).read_text(encoding="utf-8-sig"))
    return records


def _cmd_append(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    if not _STAGE_RE.match(args.stage):
        _emit(_error("INVALID_INPUT", f"--stage must be a lowercase slug, got '{args.stage}'"))
        return 2
    try:
        raw_records = _read_records(args)
    except AdapterError as exc:
        _emit(_error("INVALID_INPUT", str(exc)))
        return 2
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        # json.JSONDecodeError is a ValueError.
        _emit(_error("INVALID_INPUT", f"cannot read the records: {exc}"))
        return 2
    records: list[dict] = []
    errors: list[dict] = []
    for index, raw in enumerate(raw_records):
        record, err = normalize_record(raw)
        if err:
            errors.append({"index": index, "error": err})
        else:
            records.append(record)
    if errors:
        _emit(_error("INVALID_RECORD", f"{len(errors)} invalid record(s); nothing was written", errors=errors))
        return 2
    try:
        # Read, append and write as one step: an append that overlaps this
        # one waits here instead of writing over the records it adds.
        with ledger_lock(path):
            ledger = load_ledger(path) if path.exists() else new_ledger(path)
            if args.adapter == "provenance-line":
                records = without_fabricated(ledger, records)
            appended, duplicates = append_records(ledger, args.stage, records)
            save_ledger(path, ledger)
    except LedgerError as exc:
        _emit(_error(exc.code, str(exc)))
        return 1
    except OSError as exc:
        _emit(_error("WRITE_FAILED", f"cannot write {path}: {exc}"))
        return 1
    _emit(
        {
            "status": "ok",
            "ledger": str(path),
            "stage": args.stage,
            "appended": appended,
            "duplicates": duplicates,
            "record_count": len(ledger["records"]),
        }
    )
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    try:
        ledger = load_ledger(path)
    except LedgerError as exc:
        _emit(_error(exc.code, str(exc)), stream=sys.stderr)
        return 1
    sys.stdout.write(render_gap_report(ledger, heading=args.heading))
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    try:
        ledger = load_ledger(path)
    except LedgerError as exc:
        _emit(_error(exc.code, str(exc)))
        return 1
    _emit(summarize(path, ledger))
    return 0


def _cmd_categories(args: argparse.Namespace) -> int:
    _emit(
        {
            "status": "ok",
            "severities": list(SEVERITIES),
            "categories": [
                {"category": slug, "group": group, "description": description}
                for slug, (group, description) in CATEGORIES.items()
            ],
        }
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gap-ledger",
        description="Append, render and summarize the test-skill gap ledger.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("append", help="append records from stdin, --input or a script's result (--from)")
    p.add_argument("--ledger", required=True, help="{forge_version}/test-findings-{run_id}.json")
    p.add_argument("--stage", required=True, help="the stage appending, e.g. coverage-check")
    p.add_argument("--input", action="append",
                   help="a JSON file with the records (default: stdin); with --from, the script result to read "
                        "(structure takes it more than once)")
    p.add_argument("--from", dest="adapter", choices=tuple(ADAPTER_OPTIONS),
                   help="build the records from the --input result of a script (see the docstring's Adapters)")
    p.add_argument("--surface", help="coverage: load-coverage-inputs.py surface's result (Sources, kinds, "
                                     "the names outside scope)")
    p.add_argument("--signatures", help="coverage: score-signatures.py score's result (missingTypes)")
    p.add_argument("--numerator", help="coverage: verify-declared-numerator.py's result (absent names)")
    p.add_argument("--stale", help="coverage: classify-stale's result (fabricated signatures, documented extras, "
                                   "map entries at an `export *` line); provenance-line: the same (the names a "
                                   "rename declares, the entries at another package's `export *` line)")
    p.add_argument("--provenance", help="coverage: the provenance map (an absent name's Source)")
    p.add_argument("--inventory", help="coverage: validate-inventory.py's inventory (the `at` of a stale name no "
                                       "line documents, and of each of a homonym's forms, whose own citations pick "
                                       "its declaring file)")
    p.add_argument("--skill-dir", help="coverage: the skill package (a stale name's documenting line)")
    p.add_argument("--metadata", help="the metadata.json path a record cites as its Source (not read)")
    p.add_argument("--served", action="append", choices=FAMILIES,
                   help="structure: a family another heading serves (the caller's judgment); repeatable")
    p.set_defaults(func=_cmd_append)

    p = sub.add_parser("render", help="print the Gap Report in Markdown")
    p.add_argument("--ledger", required=True)
    p.add_argument("--heading", action="store_true", help="start with the ## Gap Report line")
    p.set_defaults(func=_cmd_render)

    p = sub.add_parser("summary", help="counts by severity and category")
    p.add_argument("--ledger", required=True)
    p.set_defaults(func=_cmd_summary)

    p = sub.add_parser("categories", help="list the category vocabulary")
    p.set_defaults(func=_cmd_categories)

    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON and Markdown streams to UTF-8.

    A default Windows console uses cp1252, which cannot carry a non-ASCII
    title or remediation. Keeps each stream's error handler; skips test
    doubles without reconfigure(). For stdin this must run before the read.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
