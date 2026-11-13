# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Render Stack Metadata: a stack's export labels, library tiers, pair tiers, metadata.json fields, provenance entries, reference files, evidence report and context snippet.

create-stack-skill relabels its code-mode export records and sets each
library's tier from them (parallel-extract section 3a), gives each
integration the tier of its pair (detect-integrations section 3), finds the
hub libraries and the library order (detect-integrations section 4,
compile-stack sections 3 and 4), writes the counted and ranked fields of
metadata.json (generate-output section 6) and writes the provenance map from
the run's files in either mode: its entries, its integrations, each with the
detection method of its qualifier, and, in compose mode, its constituents
(generate-output section 7). It also renders the Library Reference Index
(compile-stack section 6), writes the fixed parts of each reference and pair
file (generate-output sections 3 and 4), writes the context snippet, trimmed
to its token budget (generate-output section 5), and writes the evidence
report (generate-output section 8b), so the step writes only their prose.
This helper holds those rules once, so no step file restates them, and
skf-validate-output.py --skill-type stack recomputes the dominant tier with
dominant_tier here.

Rules:
  Tiers, from the strongest: T1, T1-low, T2, T3.

  library_tier(records)
      A code-mode library is T1 when it has export records and every one
      names extraction_method ast_bridge (an ast-grep rule matched it), and
      T1-low otherwise: one export read by eye, or none recorded at all.

  combine_pair_tier(a, b, mode)
      An integration takes the weaker of its two libraries' tiers, one rule
      in code mode and compose mode: T1 + T1 is T1; T1 + T1-low and
      T1-low + T1-low are T1-low; T1 + T2, T1-low + T2 and T2 + T2 are T2; a
      pair with a T3 member is T3. A T2 member lowers the pair like any
      other tier: its temporal annotations never keep a stronger one.
      `mode` must name a mode, and both modes take this rule.

  dominant_tier(distribution)
      The tier of the largest bin of a confidence_distribution. A tie goes
      to the weaker tier, so the tier never overstates confidence, and a
      distribution with no positive bin (no library) reads T1-low. This is
      the stack's confidence_tier.

  confidence_distribution
      Each library once, in the bin of its tier, so the four bins sum to
      library_count. The evidence report bins the provenance entries
      instead (skf-render-metadata-stats.py).

  source_authority
      The lowest authority among the libraries: official, then community,
      then internal, so a community and an internal library give internal.
      A library that records none counts as community, so a constituent
      without one never lifts a stack to official, and a code-mode stack,
      whose libraries are dependencies rather than skills with an
      authority, is community.

  detection_method(mode, qualifier)
      A bundle pair's `qualifier` says how step 5 found it, and gives the
      provenance map's detection_method by a fixed table for each mode:
        code     grep-co-import                   co-import grep
        compose  architecture-co-mention          architecture_co_mention
                 constituent-documented-contract  constituent_documented_contract
                 inferred-shared-domain           inferred_from_shared_domain
      A missing qualifier, an unknown one or one of the other mode is an
      input error. A detection_method a bundle pair still holds is
      ignored: this table is its only source.

  hubs and library_order
      A library's degree is its number of distinct partners among the
      pairs. library_order lists every library by degree, the highest
      first, then by file_count, the highest first, in code mode (a
      library without one counts 0) or by tier, the strongest first, in
      compose mode, then by name (case-folded, then as written). hubs
      holds each library of degree 3 or more as {library, partners}, in
      library_order order, its partners sorted by name the same way.

  relabel(records)
      The label check is skf-render-metadata-stats.py's, run beside this
      script on the records as its stack shape: each violation's field
      takes the `expected` value the check gives, never the reverse, and the
      check runs again until it passes. Three violations name no value to
      copy, so the rule here sets one: an unknown or missing
      extraction_method becomes its canonical spelling when it is a known
      method in another case, and source_reading otherwise, since nothing
      shows an ast-grep rule matched it; an ast-grep record with no node
      kind becomes ast_bridge, the stack's name for that tool, which pairs
      with no kind; and a record with no valid signature_source takes T1
      when an ast-grep rule matched it (ast_bridge or ast-grep) and T1-low
      otherwise.

  snippet trim
      While the snippet's tokens, len(text)//4 as skf-validate-output.py and
      skf-count-tokens.py count them, exceed --budget (120 unless given),
      `snippet` applies the next stage, in this order: gotchas (drop the
      gotchas line), stack-versions (strip every @version), stack-top-8
      (keep the first 8 libraries) and integrations-top-5 (keep the first 5
      pairs), each cut list ending `, ...+{N} more`. A stage that would not
      shorten the snippet (a 9th library or 6th pair shorter than its
      `...+1 more`) is skipped and not listed, and the IMPORTANT line is
      never trimmed. over_budget is true when the snippet is still above
      the budget after the last stage.

Input (--input <json-file-or-'-'>, where '-' reads stdin):
  {
    "mode": "code" | "compose",
    "libraries": [
      {"name": "<library>",
       "confidence": "T1|T1-low|T2|T3",          # per_library_extractions[].confidence
       "source_authority": "official|community|internal",   # optional
       "file_count": N},                          # optional: the step 3 import count
      ...
    ],
    "integrations": [{"a": "<library>", "b": "<library>"}, ...]   # optional
  }
  Tier, mode, authority and qualifier tokens compare case-insensitively and
  are printed in their canonical spelling. Each library is named once, each
  pair names two different libraries of `libraries`, once in either order,
  and a file_count is a whole number.

Or the extraction bundle (--bundle <json-file>, never stdin, in place of
--input), which gives pair-tiers and metadata the same data: its mode, one
library per per_library_extractions[] entry (its `library` as the name,
with its confidence, source_authority and file_count) and the pairs of its
integrations[] ({a, b}, other keys ignored). pair-tiers on a code-mode
bundle takes the pairs from --pairs <json-file-or-'-'> instead, a JSON array
of {a, b} (other keys ignored), because step 5 tiers its pairs before it
writes them; a compose-mode bundle refuses --pairs, and so does --input. An
error in the bundle names its field.

Export records (--records <json-file>, or '-' for library-tiers): the
file parallel-extract section 3a writes and relabels,
  {"entries": [{"source_library": "<library>",
                "extraction_method": "ast_bridge|source_reading", ...}, ...]}
and, for library-tiers, --libraries, the stack's libraries, comma-separated.
Every record names one of them; a library with no record is T1-low.

Subcommands:
  relabel     relabels the records against the label check, rewrites the
              file atomically when a label changed (parallel-extract
              section 3a), and prints each relabeled export and the
              records' label counts (one per record, by signature_source):
                {"relabeled": [{"entry_index": I, "export_name": "<name>",
                                "source_library": "<library>",
                                "changes": [{"field": "<field>",
                                             "from": <old>, "to": <new>}]}, ...],
                 "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
                 "coherence": {"ok": true, "violations": []}}
              A removed ast_node_type shows "to": null.
  library-tiers
              each library's tier, in the order --libraries gives
              (parallel-extract section 3a):
                {"libraries": [{"name": "<library>", "tier": "T1|T1-low",
                                "export_count": N, "ast_bridge_count": M}, ...]}
  pair-tiers  the tier of each integration (detect-integrations section 3):
                {"mode": "<mode>",
                 "integrations": [{"a": "<a>", "b": "<b>", "tier": "<tier>"}, ...]}
  metadata    the computed fields of metadata.json (generate-output section
              6), with the libraries and pairs in the order given, then the
              hub libraries and the library order (detect-integrations
              section 4, compile-stack sections 3 and 4):
                {"mode": "<mode>",
                 "library_count": N,
                 "integration_count": M,
                 "libraries": ["<library>", ...],
                 "integration_pairs": [["<a>", "<b>"], ...],
                 "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
                 "confidence_tier": "<dominant tier>",
                 "source_authority": "<authority>",
                 "integrations": [{"a": "<a>", "b": "<b>", "tier": "<tier>"}, ...],
                 "hubs": [{"library": "<library>", "partners": ["<library>", ...]}, ...],
                 "library_order": ["<library>", ...]}
  provenance  writes provenance-map.json to --target atomically
              (generate-output section 7), in the mode the extraction
              bundle --bundle names: the object --input holds (the map's
              provenance_version, skill_name, skill_type, source_repo,
              source_commit, source_ref and generated_at) with `entries` set
              to the records' entries (as they stand in code mode) and
              `integrations` built
              from the bundle, one per pair of its `integrations`: libraries
              [a, b], pattern_type from its type, detection_method from its
              qualifier (see detection_method above), co_import_files and
              confidence from its tier. Each replaces the field of that name
              the input holds.
              code mode takes --pairs, the skf-pair-intersect.py result
              (detect-integrations section 1): a pair's co_import_files are
              the files of its entry there, {path, line_a, line_b}, matched
              on the two libraries in either order (line_a and line_b swap
              when the bundle names the pair the other way round); a bundle
              pair with no entry is an input error.
              compose mode takes --inventory, step 4's
              skf-enumerate-stack-skills.py result, --skills-root and
              --project-root. Each entry takes its constituent's tier, the
              confidence of the per_library_extractions[] entry whose library
              is its source_library, as its confidence and signature_source,
              and extraction_method compose-from-skill (an entry naming no
              library of the bundle is an input error), so the records hold
              only the cited fields. Its co_import_files are [], and it adds
              `constituents`, one per per_library_extractions[] entry in its
              order: skill_name its library, skill_path the folder
              {skills-root}/{skill_dir} relative to the project root with a
              trailing slash (absolute when no relative path reaches it; a
              folder that does not exist is an input error), its version,
              composed_at the input's generated_at, and metadata_hash copied
              from the inventory's `skills[]` entry whose name is its
              skill_dir, never computed. It prints
                {"target": "<path>", "entry_count": N, "integration_count": M}
              with "constituent_count": K added in compose mode.
  references  the Library Reference Index (compile-stack section 6) and, with
              --out, the fixed parts of each reference and pair file
              (generate-output sections 3 and 4), from the extraction bundle
              --bundle, whose mode --mode must name, and, in code mode, the
              records --records and, with --out, --pairs (a compose-mode
              bundle refuses both). It writes, in the bundled template's form,
              {out}/{library}.md for each library: its title, `**Version:**`
              (`unknown` when it has none), `**Import count:** {file_count}
              files` (0 when it has none; compose mode: `**Export count:** {n}
              exports`), `**Confidence:**` its tier, `## Key Exports` (each
              record of the library in records order, `name(params) ->
              return_type` in a code span, `(params)` for a function or class
              and the return type for a function, then *its type* and
              (source_file:source_line); compose mode: each `exports` name, its
              `signatures` entry when there is one, then [from skill:
              {library}]) and, only when its `temporal` holds an item,
              `## Migration & Deprecation`, each deprecated_exports,
              migration_notes and version_warnings item as written, in that
              order; and {out}/integrations/{a}-{b}.md for each pair: its
              title, `**Type:**`, `**Co-import files:**` (its intersection_count
              in --pairs, the pair matched in either order; 0 in compose mode),
              `**Confidence:** {tier} ({qualifier})`, in compose mode with
              [composed] ([inferred from shared domain] for that qualifier) and
              [VS: Risky] or [VS: Blocked] for those pair verdicts, and `## Key
              Files` (its key_files; compose mode: its evidence lines, its
              reference line and, when its vs is set, `VS overall: {overall}`
              and `VS pair: {pair}`). An empty list writes `none recorded`,
              and each value is written on one line, its whitespace runs, a
              newline included, as one space.
              Each part the step writes is a marker line
              `<!-- skf:fill {slot} -->`: usage-patterns and common-imports in
              a library file, integration-pattern and usage-convention in a
              pair file. It creates the folders a name such as @scope/pkg
              needs, and refuses a name that would land outside --out
              (absolute, or with a `\\` or a `..` part) or two files on one
              path. It prints
                {"mode": "<mode>",
                 "index": {"header": ["<table head>", "<separator>"],
                           "rows": [{"library": "<library>",
                                     "inline": "<row, [ref](references/{name}.md)>",
                                     "catalog": "<row, [ref]({name}.md)>"}, ...]},
                 "written": [{"path": "<relative to --out>",
                              "placeholders": ["<slot>", ...]}, ...]}
              the rows in library_order, compose mode naming Export Count in
              place of Imports, each row's Key Exports the first five export
              names in code spans, then `, +N more`; "written" is [] without
              --out.
  evidence-report
              writes evidence-report.md to --target atomically (generate-output
              section 8b): the libraries of --bundle in library_order (status,
              version, tier, file_count or, in compose mode, the number of its
              exports, the entries of the map --provenance whose
              source_library it is, the number of its usage_patterns and of
              its temporal items, its warnings), its failed[], each pair (its
              type, its Confidence label as `references` writes it and its
              co-import file count from --pairs, which code mode needs and
              compose mode refuses), each warning and each decision of the run
              sink in --run-dir on one line (warnings.jsonl and
              headless-decisions.jsonl, read by skf-emit-result-envelope.py's
              rules: a line that is not a non-empty JSON string or object is
              named as sink_line_unreadable, a missing file is none, and a
              missing folder an input error), the scope gate's dropped libraries and
              prior_kept included, and the map entries binned by
              signature_source with skf-render-metadata-stats.py --shape stack
              beside this script, or "not computed: {reason}" when that helper
              is missing or the map cannot be read. It prints
                {"target": "<path>", "library_count": N, "failed_count": F,
                 "integration_count": M, "warning_count": W, "decision_count": D,
                 "confidence_distribution": {"t1": 0, ...} or null}
  snippet     writes context-snippet.md to --target atomically (generate-output
              section 5), in the bundled template's form, from the extraction
              bundle --bundle and its pairs' co-import file counts in --pairs,
              which code mode needs and compose mode refuses:
                [{stack-name} v{version}]|root: skills/{stack-name}/
                the template's |IMPORTANT: line for {stack-name}
                |stack: each library as {name}@{version} ({name} with no
                        version), by file_count (compose mode: its number of
                        exports), the highest first, then by name
                |integrations: each pair as {a}+{b}, by its intersection_count
                        in --pairs (0 in compose mode), the highest first, ties
                        in bundle order; `none` with no pair
                |gotchas: the --gotchas text (a file, or '-' for stdin) on one
                        line, each whitespace run as one space; no line when
                        it is blank or not given
              and trims it by the snippet trim rule above. --stack-name and
              --version are non-empty with no whitespace, and --budget is a
              positive whole number. It prints
                {"target": "<path>", "tokens": N,
                 "trims_applied": ["<stage>", ...], "over_budget": false}

CLI:
  uv run skf-render-stack-metadata.py relabel --records export-records.json
  uv run skf-render-stack-metadata.py library-tiers --records export-records.json --libraries "react,zod"
  uv run skf-render-stack-metadata.py pair-tiers --input -
  uv run skf-render-stack-metadata.py pair-tiers --bundle extraction-bundle.json --pairs -
  uv run skf-render-stack-metadata.py metadata --input stack.json
  uv run skf-render-stack-metadata.py metadata --bundle extraction-bundle.json
  uv run skf-render-stack-metadata.py provenance --records export-records.json --bundle extraction-bundle.json \\
      --pairs pair-intersect.json --input - --target provenance-map.json
  uv run skf-render-stack-metadata.py provenance --records compose-entries.json --bundle extraction-bundle.json \\
      --inventory stack-inventory.json --skills-root skills --project-root . --input - --target provenance-map.json
  uv run skf-render-stack-metadata.py references --mode code --bundle extraction-bundle.json \\
      --records export-records.json --pairs pair-intersect.json --out references
  uv run skf-render-stack-metadata.py references --mode compose --bundle extraction-bundle.json
  uv run skf-render-stack-metadata.py evidence-report --bundle extraction-bundle.json --run-dir run \\
      --provenance provenance-map.json --pairs pair-intersect.json --target evidence-report.md
  uv run skf-render-stack-metadata.py snippet --bundle extraction-bundle.json --pairs pair-intersect.json \\
      --stack-name acme-stack --version 1.2.0 --gotchas - --target context-snippet.md < snippet-gotchas.txt

Exit codes:
  0  the JSON is printed (relabel: the records pass the label check)
  1  relabel only: a violation no rule fixes is left; the JSON lists it in
     coherence.violations, and the file holds every label that was fixed
  2  a usage, read, write or input error, or skf-render-metadata-stats.py
     missing beside this script for relabel: one line on stderr, no JSON,
     nothing written
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import math
import os
import re
import secrets
import sys
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

# Tiers from the strongest to the weakest: T1-low is weaker than T1, T2 than
# T1-low, T3 than T2.
TIERS = ("T1", "T1-low", "T2", "T3")
MODES = ("code", "compose")
# The extraction_method of an export an ast-grep rule matched: the only one
# that keeps a code-mode library at T1.
AST_METHOD = "ast_bridge"
# The extraction_method of every compose-mode entry: copied from a constituent skill.
COMPOSE_METHOD = "compose-from-skill"
# The provenance map's detection_method of a pair, by the bundle's mode and the
# pair's qualifier (how step 5 found it): the only source of the method.
DETECTION_METHODS = {
    "code": {"grep-co-import": "co-import grep"},
    "compose": {
        "architecture-co-mention": "architecture_co_mention",
        "constituent-documented-contract": "constituent_documented_contract",
        "inferred-shared-domain": "inferred_from_shared_domain",
    },
}
# The degree (distinct partners) from which a library is a hub.
HUB_DEGREE = 3
# Authorities from the highest to the lowest.
AUTHORITIES = ("official", "community", "internal")
# The authority of a library that records none.
DEFAULT_AUTHORITY = "community"

# The confidence_distribution bins of metadata.json, from the strongest tier
# to the weakest. dominant_tier reads them in this order and lets a later bin
# win a tie, so a tie resolves toward the weaker tier.
_DISTRIBUTION_BINS = (("t1", "T1"), ("t1_low", "T1-low"), ("t2", "T2"), ("t3", "T3"))

# The tier of a distribution that records no evidence (the conservative default).
_NO_EVIDENCE_TIER = "T1-low"

# The label check relabel runs: skf-render-metadata-stats.py beside this
# script (src/shared/scripts/ and _bmad/skf/shared/scripts/ alike).
_STATS_HELPER = "skf-render-metadata-stats.py"
# The stats helper's shape for a stack's records.
_STATS_SHAPE = "stack"
# The method a record takes when nothing shows an ast-grep rule matched it.
_READ_BY_EYE_METHOD = "source_reading"
# The extraction_method values that name an ast-grep match, and the label a
# record of each kind takes when it has no valid signature_source.
_AST_METHODS = ("ast_bridge", "ast-grep")
# The violation field of a record: provenance.entries[<index>].<field>.
_RECORD_FIELD_RE = re.compile(r"^provenance\.entries\[(\d+)\]\.(\w+)$")
# The `expected` value of an ast-grep record's missing node kind.
_NODE_KIND_EXPECTED = "non-null"
# Relabeling passes before relabel reports what is left: each pass fixes
# every violation it finds, so two or three passes settle every record.
_RELABEL_PASSES = 5
# Windows refuses to replace a file another process holds open, and a virus
# scanner or the search indexer may open a just-written file for a moment:
# _write_atomic retries the rename there for up to this long before failing.
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.02


class InputError(ValueError):
    """An input the caller must fix: exit 2 with one line on stderr."""


class WriteError(OSError):
    """A file that could not be written: exit 2 with one line on stderr."""


def _token(value, allowed: tuple[str, ...], what: str) -> str:
    """`value` in its canonical spelling from `allowed`, compared case-insensitively."""
    if isinstance(value, str):
        for token in allowed:
            if value.strip().lower() == token.lower():
                return token
    raise InputError(f"{what} must be one of {', '.join(allowed)}; got {value!r}")


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def library_tier(methods: list[str]) -> str:
    """A code-mode library's tier from the extraction_method of each of its export records.

    T1 when there is at least one record and every one is ast_bridge, T1-low
    otherwise: an export read by eye, or no export recorded, never earns T1.
    """
    return "T1" if methods and all(method == AST_METHOD for method in methods) else "T1-low"


def combine_pair_tier(a: str, b: str, mode: str) -> str:
    """The tier of an integration between a library of tier `a` and one of tier `b`.

    The weaker of the two, in both modes. Raises InputError on an unknown tier
    or mode.
    """
    _token(mode, MODES, "mode")
    return max(_token(a, TIERS, "tier"), _token(b, TIERS, "tier"), key=TIERS.index)


# Keep identical to _bin_count and dominant_tier in skf-enumerate-stack-skills.py
# (test/test-skf-render-stack-metadata.py pins the copies).
def _bin_count(value):
    """A confidence_distribution bin's count: a positive finite number, else 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return value if value > 0 else 0


def dominant_tier(distribution) -> str:
    """The tier of the largest bin of a metadata.json confidence_distribution.

    The bins are read from the strongest tier to the weakest and a later bin
    wins a tie, so a tie resolves toward the weaker tier (T1-low over T1, T2
    over T1-low, T3 over T2) and the tier never overstates confidence. A bin
    counts only when it holds a positive number. T1-low when none does: the
    distribution is absent, not an object or all zero.
    """
    tier, best = _NO_EVIDENCE_TIER, 0
    if isinstance(distribution, dict):
        for key, bin_tier in _DISTRIBUTION_BINS:
            count = _bin_count(distribution.get(key))
            if count and count >= best:
                tier, best = bin_tier, count
    return tier


def library_distribution(tiers: list[str]) -> dict[str, int]:
    """confidence_distribution with each library once, in the bin of its tier."""
    bin_of = {tier: key for key, tier in _DISTRIBUTION_BINS}
    distribution = {key: 0 for key, _ in _DISTRIBUTION_BINS}
    for tier in tiers:
        distribution[bin_of[tier]] += 1
    return distribution


def lowest_authority(authorities: list[str | None]) -> str:
    """The lowest of the authorities, a library that records none (None)
    counting as DEFAULT_AUTHORITY; DEFAULT_AUTHORITY for no library."""
    return max((authority or DEFAULT_AUTHORITY for authority in authorities),
               key=AUTHORITIES.index, default=DEFAULT_AUTHORITY)


def detection_method(mode: str, qualifier, where: str) -> str:
    """The provenance detection_method of a pair of a `mode` bundle that step 5
    found as `qualifier`, from DETECTION_METHODS.

    Raises InputError on a qualifier outside that mode's table (missing,
    unknown, or the other mode's), naming `{where}.qualifier`.
    """
    table = DETECTION_METHODS[_token(mode, MODES, "mode")]
    return table[_token(qualifier, tuple(table), f"{where}.qualifier (a {mode}-mode pair)")]


def _name_key(name: str) -> tuple[str, str]:
    """The sort key of a library name: case-folded, then as written."""
    return name.casefold(), name


def _partners(libraries: list[dict], pairs: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Each library's distinct partners among the pairs."""
    partners: dict[str, set[str]] = {library["name"]: set() for library in libraries}
    for a, b in pairs:
        partners[a].add(b)
        partners[b].add(a)
    return partners


def library_order(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> list[str]:
    """Every library, by degree (distinct partners), the highest first; then
    by file_count, the highest first, in code mode (none counting 0) or by
    tier, the strongest first, in compose mode; then by name."""
    partners = _partners(libraries, pairs)

    def key(library: dict) -> tuple:
        if mode == "code":
            second = -(library.get("file_count") or 0)
        else:
            second = TIERS.index(library["confidence"])
        return (-len(partners[library["name"]]), second, *_name_key(library["name"]))

    return [library["name"] for library in sorted(libraries, key=key)]


def stack_hubs(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> list[dict]:
    """Each library of HUB_DEGREE partners or more, as {library, partners}, in
    library_order order, its partners sorted by name."""
    partners = _partners(libraries, pairs)
    return [{"library": name, "partners": sorted(partners[name], key=_name_key)}
            for name in library_order(mode, libraries, pairs) if len(partners[name]) >= HUB_DEGREE]


# --------------------------------------------------------------------------
# Input and projections
# --------------------------------------------------------------------------


def _parse_libraries(raw, owner: str, field: str, name_key: str) -> list[dict]:
    """The libraries of `raw`: the input's `libraries` (named by `name`) or the
    bundle's per_library_extractions (named by `library`). `owner` and `field`
    name them in an error. Raises InputError."""
    if not isinstance(raw, list):
        raise InputError(f"{owner}`{field}` must be an array of {{{name_key}, confidence}} objects")
    libraries: list[dict] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        where = f"{owner}{field}[{i}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object with `{name_key}` and `confidence`; got {item!r}")
        name = item.get(name_key)
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{where}.{name_key} must be a non-empty string; got {name!r}")
        if name in seen:
            raise InputError(f"{where}.{name_key}: library {name!r} is listed twice")
        tier = _token(item.get("confidence"), TIERS, f"{where}.confidence")
        authority = item.get("source_authority")
        if authority is not None:
            authority = _token(authority, AUTHORITIES, f"{where}.source_authority")
        file_count = item.get("file_count")
        if "file_count" in item and (isinstance(file_count, bool) or not isinstance(file_count, int)
                                     or file_count < 0):
            raise InputError(f"{where}.file_count must be a whole number; got {file_count!r}")
        seen.add(name)
        libraries.append({"name": name, "confidence": tier, "source_authority": authority,
                          "file_count": file_count})
    return libraries


def _parse_pairs(raw, names: set[str], owner: str, field: str) -> list[tuple[str, str]]:
    """The pairs of `raw`, an array of {a, b} objects naming two different
    libraries of `names`, each pair once in either order. `owner` and `field`
    name them in an error. Raises InputError."""
    if not isinstance(raw, list):
        raise InputError(f"{owner}`{field}` must be an array of {{a, b}} objects")
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()
    for i, item in enumerate(raw):
        where = f"{owner}{field}[{i}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object with `a` and `b`; got {item!r}")
        a, b = item.get("a"), item.get("b")
        for side, name in (("a", a), ("b", b)):
            if not isinstance(name, str) or name not in names:
                raise InputError(f"{where}.{side} {name!r} is not one of the libraries")
        if a == b:
            raise InputError(f"{where} pairs {a!r} with itself")
        key = frozenset((a, b))
        if key in seen:
            raise InputError(f"{where}: the pair {a!r} + {b!r} is listed twice")
        seen.add(key)
        pairs.append((a, b))
    return pairs


def parse_stack(data) -> tuple[str, list[dict], list[tuple[str, str]]]:
    """(mode, libraries, pairs) from the input JSON. Raises InputError."""
    if not isinstance(data, dict):
        raise InputError(f"the input must be a JSON object; got {type(data).__name__}")
    mode = _token(data.get("mode"), MODES, "mode")
    libraries = _parse_libraries(data.get("libraries"), "", "libraries", "name")
    names = {library["name"] for library in libraries}
    return mode, libraries, _parse_pairs(data.get("integrations", []), names, "", "integrations")


def bundle_stack(bundle, pairs=None) -> tuple[str, list[dict], list[tuple[str, str]]]:
    """(mode, libraries, pairs) from the extraction bundle, as parse_stack
    gives them from the input: a library per per_library_extractions[] entry
    and the pairs of its integrations[], or `pairs` (the parsed --pairs
    array) when given. Raises InputError naming the bundle field."""
    mode = bundle_mode(bundle)
    libraries = _parse_libraries(bundle.get("per_library_extractions"), "the bundle's ",
                                 "per_library_extractions", "library")
    names = {library["name"] for library in libraries}
    if pairs is None:
        return mode, libraries, _parse_pairs(bundle.get("integrations", []), names, "the bundle's ", "integrations")
    return mode, libraries, _parse_pairs(pairs, names, "", "--pairs")


def parse_library_names(value: str) -> list[str]:
    """The comma-separated --libraries list, each name once. Raises InputError."""
    names = [name.strip() for name in value.split(",") if name.strip()]
    if not names:
        raise InputError("--libraries must name at least one library")
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise InputError(f"library {name!r} is listed twice in --libraries")
        seen.add(name)
    return names


def library_tiers(data, names: list[str]) -> list[dict]:
    """Each library of `names` with its tier and record counts, from the export records.

    `data` is the parsed records file, {"entries": [...]}. Raises InputError
    on a record that names no library, or one --libraries does not list.
    """
    methods: dict[str, list[str]] = {name: [] for name in names}
    for i, record in enumerate(parse_records(data)):
        where = f"entries[{i}]"
        library = record.get("source_library")
        if not isinstance(library, str) or library not in methods:
            raise InputError(f"{where}.source_library {library!r} is not one of --libraries")
        method = record.get("extraction_method")
        methods[library].append(method.strip().lower() if isinstance(method, str) else "")
    return [
        {"name": name, "tier": library_tier(found), "export_count": len(found),
         "ast_bridge_count": sum(method == AST_METHOD for method in found)}
        for name, found in methods.items()
    ]


def parse_records(data) -> list[dict]:
    """The `entries` of an export records file, each an object. Raises InputError."""
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise InputError("the export records must be a JSON object with an `entries` array")
    for i, record in enumerate(data["entries"]):
        if not isinstance(record, dict):
            raise InputError(f"entries[{i}] must be an object; got {record!r}")
    return data["entries"]


# --------------------------------------------------------------------------
# Relabeling
# --------------------------------------------------------------------------


def _load_stats_rules():
    """skf-render-metadata-stats.py beside this script, as a module. Raises ImportError."""
    path = Path(__file__).resolve().parent / _STATS_HELPER
    if not path.is_file():
        raise ImportError(f"{_STATS_HELPER} not found beside {Path(__file__).name}: no label check can run")
    spec = importlib.util.spec_from_file_location("skf_render_metadata_stats_rules", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{_STATS_HELPER} beside {Path(__file__).name} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as exc:
        raise ImportError(f"{_STATS_HELPER} beside {Path(__file__).name} cannot be loaded: {exc}") from exc
    return module


def label_check(stats, entries: list[dict]) -> tuple[dict, dict]:
    """(confidence_distribution, coherence) of the stats helper's stack check on the records."""
    prov = {"entries": entries}
    derived = stats.derive_stats(prov, {}, _STATS_SHAPE)
    return derived["confidence_distribution"], stats.coherence_compute(derived, prov)


def _set(changes: dict, entries: list[dict], index: int, field: str, value) -> None:
    """Set (or, for None on ast_node_type, remove) one field of a record and note the change."""
    record = entries[index]
    old = record.get(field)
    if field == "ast_node_type" and value is None:
        record.pop(field, None)
    else:
        record[field] = value
    changes.setdefault(index, []).append({"field": field, "from": old, "to": value})


def _known_method(value, known: tuple[str, ...]) -> str | None:
    """`value` as a known extraction_method in its canonical spelling, or None."""
    if isinstance(value, str):
        token = value.strip().lower()
        if token in known:
            return token
    return None


def relabel_pass(stats, entries: list[dict], violations: list[dict], changes: dict) -> bool:
    """Apply one fix per violation to the records in place. True when a label changed."""
    changed = False
    for violation in violations:
        field = violation.get("field")
        if field == "confidence_distribution":
            # Records with no valid signature_source: each takes the label its method implies.
            for index, record in enumerate(entries):
                signature = record.get("signature_source")
                if isinstance(signature, str) and signature.strip().upper() in stats._SIG_MAP:
                    continue
                method = _known_method(record.get("extraction_method"), _AST_METHODS)
                _set(changes, entries, index, "signature_source", "T1" if method else "T1-low")
                changed = True
            continue
        match = _RECORD_FIELD_RE.match(field) if isinstance(field, str) else None
        if match is None:
            continue  # no rule for it: it stays in coherence.violations
        index, name = int(match.group(1)), match.group(2)
        expected = violation.get("expected")
        if name == "extraction_method":
            method = _known_method(entries[index].get("extraction_method"), stats._KNOWN_METHODS)
            _set(changes, entries, index, name, method or _READ_BY_EYE_METHOD)
        elif name == "ast_node_type" and expected == _NODE_KIND_EXPECTED:
            _set(changes, entries, index, "extraction_method", _AST_METHODS[0])
        else:
            _set(changes, entries, index, name, expected)
        changed = True
    return changed


def relabel(stats, entries: list[dict]) -> tuple[list[dict], dict, dict]:
    """Relabel the records in place until they pass the label check.

    Returns (relabeled, confidence_distribution, coherence), `relabeled`
    holding each changed record once, in entries[] order, with its changes.
    """
    changes: dict[int, list[dict]] = {}
    for _ in range(_RELABEL_PASSES):
        _distribution, coherence = label_check(stats, entries)
        if coherence["ok"] or not relabel_pass(stats, entries, coherence["violations"], changes):
            break
    distribution, coherence = label_check(stats, entries)
    relabeled = [
        {"entry_index": index, "export_name": entries[index].get("export_name"),
         "source_library": entries[index].get("source_library"), "changes": found}
        for index, found in sorted(changes.items())
    ]
    return relabeled, distribution, coherence


# --------------------------------------------------------------------------
# Provenance map
# --------------------------------------------------------------------------


def bundle_mode(bundle) -> str:
    """The extraction bundle's `mode`, code or compose. Raises InputError."""
    if not isinstance(bundle, dict):
        raise InputError(f"the extraction bundle must be a JSON object; got {type(bundle).__name__}")
    return _token(bundle.get("mode"), MODES, "the bundle's mode")


def pair_files(data) -> dict[frozenset[str], tuple[str, list[dict]]]:
    """Each pair of a skf-pair-intersect.py result, keyed by its two libraries:
    its `a` and its co-import files, each {path, line_a, line_b}.

    Raises InputError on a result with no `pairs` array, or a pair that names
    no two libraries or whose files are not {path, ...} objects.
    """
    if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
        raise InputError("the pair-intersect result (--pairs) must be a JSON object with a `pairs` array")
    out: dict[frozenset[str], tuple[str, list[dict]]] = {}
    for i, pair in enumerate(data["pairs"]):
        where = f"the pair-intersect result's pairs[{i}]"
        if not isinstance(pair, dict):
            raise InputError(f"{where} must be an object; got {pair!r}")
        for key in ("a", "b"):
            if not isinstance(pair.get(key), str) or not pair[key].strip():
                raise InputError(f"{where}.{key} must be a non-empty string; got {pair.get(key)!r}")
        files = pair.get("files")
        if not isinstance(files, list) or not all(
            isinstance(item, dict) and isinstance(item.get("path"), str) for item in files
        ):
            raise InputError(f"{where}.files must be an array of {{path, line_a, line_b}} objects")
        out[frozenset((pair["a"], pair["b"]))] = (pair["a"], files)
    return out


def _co_import_files(a: str, found: tuple[str, list[dict]]) -> list[dict]:
    """A pair's co-import files with `line_a` the line that imports `a`: the
    pair-intersect files as they stand, or with the two lines swapped when
    that result names the pair the other way round."""
    first, files = found
    if first == a:
        return files
    return [dict(item, line_a=item.get("line_b"), line_b=item.get("line_a")) for item in files]


def bundle_integrations(bundle, pairs: dict | None = None) -> list[dict]:
    """The provenance map's integrations[] from the extraction bundle's, in its order.

    Each bundle pair {a, b, type, tier, qualifier, ...} gives {libraries:
    [a, b], pattern_type, detection_method, co_import_files, confidence}, its
    detection_method the one detection_method gives the bundle's mode and the
    pair's qualifier (a detection_method the pair holds is ignored). With
    `pairs` (code mode, from pair_files) its co-import files are its entry's
    there; without (compose mode) they are []. Raises InputError on a bundle
    with no mode or no `integrations` array, a pair missing one of those
    fields, a qualifier outside its mode's table, or a code-mode pair `pairs`
    has no entry for.
    """
    mode = bundle_mode(bundle)
    if not isinstance(bundle.get("integrations"), list):
        raise InputError("the extraction bundle must have an `integrations` array")
    out = []
    for i, pair in enumerate(bundle["integrations"]):
        where = f"the bundle's integrations[{i}]"
        if not isinstance(pair, dict):
            raise InputError(f"{where} must be an object; got {pair!r}")
        for key in ("a", "b", "type"):
            if not isinstance(pair.get(key), str) or not pair[key].strip():
                raise InputError(f"{where}.{key} must be a non-empty string; got {pair.get(key)!r}")
        method = detection_method(mode, pair.get("qualifier"), where)
        co_import_files: list[dict] = []
        if pairs is not None:
            found = pairs.get(frozenset((pair["a"], pair["b"])))
            if found is None:
                raise InputError(
                    f"{where} ({pair['a']} + {pair['b']}) has no entry in the pair-intersect result (--pairs)")
            co_import_files = _co_import_files(pair["a"], found)
        out.append({
            "libraries": [pair["a"], pair["b"]],
            "pattern_type": pair["type"],
            "detection_method": method,
            "co_import_files": co_import_files,
            "confidence": _token(pair.get("tier"), TIERS, f"{where}.tier"),
        })
    return out


def inventory_hashes(data) -> dict[str, str]:
    """Each skill's metadata_hash in a skf-enumerate-stack-skills.py result, by name.

    Raises InputError on a result with no `skills` array. A skill without a
    string hash is left out, so a constituent naming it is refused.
    """
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise InputError("the stack inventory (--inventory) must be a JSON object with a `skills` array")
    return {
        skill["name"]: skill["metadata_hash"]
        for skill in data["skills"]
        if isinstance(skill, dict) and isinstance(skill.get("name"), str)
        and isinstance(skill.get("metadata_hash"), str) and skill["metadata_hash"].strip()
    }


def _skill_path(skills_root: str, skill_dir: str, project_root: str) -> str:
    """The skill's folder, {skills_root}/{skill_dir}, relative to the project
    root, forward-slash, with a trailing slash; absolute when no relative
    path reaches it (another drive on Windows)."""
    folder = os.path.abspath(os.path.join(skills_root, skill_dir))
    try:
        path = os.path.relpath(folder, os.path.abspath(project_root))
    except ValueError:
        path = folder
    return Path(path).as_posix().rstrip("/") + "/"


def compose_constituents(bundle, hashes: dict[str, str], skills_root: str, project_root: str,
                         composed_at) -> list[dict]:
    """The compose-mode map's constituents[], one per per_library_extractions[] entry, in its order.

    skill_name is the entry's library, skill_path its skill folder (see
    _skill_path), version its version, composed_at the map's generated_at
    and metadata_hash the hash step 4's inventory recorded for its skill_dir,
    copied, never computed. Raises InputError on a missing field, a skill
    folder that does not exist, or a skill_dir the inventory does not hold.
    """
    if not isinstance(composed_at, str) or not composed_at.strip():
        raise InputError(f"compose mode takes composed_at from the input's generated_at, "
                         f"a non-empty string; got {composed_at!r}")
    entries = bundle.get("per_library_extractions")
    if not isinstance(entries, list):
        raise InputError("the extraction bundle must have a `per_library_extractions` array")
    out = []
    for i, entry in enumerate(entries):
        where = f"the bundle's per_library_extractions[{i}]"
        if not isinstance(entry, dict):
            raise InputError(f"{where} must be an object; got {entry!r}")
        for key in ("library", "skill_dir"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise InputError(f"{where}.{key} must be a non-empty string; got {entry.get(key)!r}")
        skill_dir, version = entry["skill_dir"], entry.get("version")
        if skill_dir in (".", "..") or "/" in skill_dir or "\\" in skill_dir:
            raise InputError(f"{where}.skill_dir must be a folder name; got {skill_dir!r}")
        if version is not None and not isinstance(version, str):
            raise InputError(f"{where}.version must be a string or null; got {version!r}")
        if not os.path.isdir(os.path.join(skills_root, skill_dir)):
            raise InputError(f"{where}: no skill folder {skill_dir!r} under --skills-root {skills_root}")
        if skill_dir not in hashes:
            raise InputError(f"{where}: the stack inventory (--inventory) holds no metadata_hash for {skill_dir!r}")
        out.append({
            "skill_name": entry["library"],
            "skill_path": _skill_path(skills_root, skill_dir, project_root),
            "version": version,
            "composed_at": composed_at,
            "metadata_hash": hashes[skill_dir],
        })
    return out


def compose_entries(bundle, entries: list[dict]) -> list[dict]:
    """The compose-mode map's entries: each record with confidence and
    signature_source set to its constituent's tier, the confidence of the
    per_library_extractions[] entry whose library is its source_library, and
    extraction_method set to COMPOSE_METHOD.

    Raises InputError on a record naming no library of the bundle, or a
    constituent whose confidence is not a tier.
    """
    tiers: dict[str, tuple[object, str]] = {}
    for i, entry in enumerate(bundle.get("per_library_extractions") or []):
        if isinstance(entry, dict) and isinstance(entry.get("library"), str):
            tiers[entry["library"]] = (entry.get("confidence"),
                                       f"the bundle's per_library_extractions[{i}].confidence")
    out = []
    for i, record in enumerate(entries):
        library = record.get("source_library")
        if not isinstance(library, str) or library not in tiers:
            raise InputError(f"entries[{i}].source_library {library!r} is not a library of the bundle's "
                             f"per_library_extractions")
        value, where = tiers[library]
        tier = _token(value, TIERS, where)
        out.append(dict(record, confidence=tier, extraction_method=COMPOSE_METHOD, signature_source=tier))
    return out


def provenance_map(base, entries: list[dict], integrations: list[dict] | None = None,
                   constituents: list[dict] | None = None) -> dict:
    """The provenance map: `base` with `entries` set to the records and, when
    given, `integrations` set to the bundle's and `constituents` to the
    compose-mode constituents.

    The entries take the place of any `entries` in `base`, or go before its
    `integrations` (the schema's order), or last; the given integrations and
    constituents take the place of any in `base`, or go last, in that order.
    Raises InputError when `base` is not an object.
    """
    if not isinstance(base, dict):
        raise InputError(f"the provenance map input must be a JSON object; got {type(base).__name__}")
    fields = dict(base)
    if integrations is not None:
        fields["integrations"] = integrations
    if constituents is not None:
        fields["constituents"] = constituents
    out: dict = {}
    for key, value in fields.items():
        if key == "entries" or (key == "integrations" and "entries" not in fields):
            out["entries"] = entries
            if key == "entries":
                continue
        out[key] = value
    out.setdefault("entries", entries)
    return out


def pair_tiers(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> list[dict]:
    """Each pair with the tier combine_pair_tier gives it."""
    tier = {library["name"]: library["confidence"] for library in libraries}
    return [{"a": a, "b": b, "tier": combine_pair_tier(tier[a], tier[b], mode)} for a, b in pairs]


def stack_metadata(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> dict:
    """The computed fields of a stack's metadata.json, then its hubs and library order."""
    distribution = library_distribution([library["confidence"] for library in libraries])
    return {
        "mode": mode,
        "library_count": len(libraries),
        "integration_count": len(pairs),
        "libraries": [library["name"] for library in libraries],
        "integration_pairs": [[a, b] for a, b in pairs],
        "confidence_distribution": distribution,
        "confidence_tier": dominant_tier(distribution),
        "source_authority": lowest_authority([library["source_authority"] for library in libraries]),
        "integrations": pair_tiers(mode, libraries, pairs),
        "hubs": stack_hubs(mode, libraries, pairs),
        "library_order": library_order(mode, libraries, pairs),
    }


# --------------------------------------------------------------------------
# Reference files, the Library Reference Index and the evidence report
# --------------------------------------------------------------------------

# A part of a reference or pair file the step writes: one marker line per slot.
FILL_MARKER = "<!-- skf:fill {slot} -->"
LIBRARY_SLOTS = ("usage-patterns", "common-imports")
PAIR_SLOTS = ("integration-pattern", "usage-convention")
# The lists of a library's `temporal`, in the order its Migration & Deprecation section writes them.
TEMPORAL_LISTS = ("deprecated_exports", "migration_notes", "version_warnings")
# The export names a Library Reference Index row shows before `, +N more`.
INDEX_EXPORTS = 5
# What a Key Exports or Key Files section with no item, or an index row with no export, writes.
NONE_RECORDED = "none recorded"
# The Library Reference Index head of each mode, as the stack template writes it.
INDEX_HEADER = {
    "code": ("| Library | Imports | Key Exports | Confidence | Reference |",
             "|---------|---------|-------------|------------|-----------|"),
    "compose": ("| Library | Export Count | Key Exports | Confidence | Reference |",
                "|---------|--------------|-------------|------------|-----------|"),
}
# The compose qualifier whose label takes `[inferred from shared domain]` in
# place of `[composed]`, and the [VS] pair verdicts that annotate a label.
_INFERRED_QUALIFIER = "inferred-shared-domain"
_VS_FLAGGED = ("Risky", "Blocked")
# The run sink create-stack-skill records its decisions and warnings in, read
# by the rules of skf-emit-result-envelope.py's read_sink.
SINK_DECISIONS = "headless-decisions.jsonl"
SINK_WARNINGS = "warnings.jsonl"
# The title of an evidence report whose map names no skill.
_REPORT_FALLBACK_TITLE = "Stack"


def _marker(slot: str) -> str:
    return FILL_MARKER.format(slot=slot)


def _string_list(value, where: str) -> list[str]:
    """`value`, an array of strings, or [] when it is absent (null). Raises InputError."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InputError(f"{where} must be an array of strings; got {value!r}")
    return value


def _optional_string(value, where: str) -> str | None:
    """`value` stripped, or None when it is absent, null or blank. Raises InputError on a non-string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError(f"{where} must be a string or null; got {value!r}")
    return value.strip() or None


def _code_span(text: str) -> str:
    """`text` as a Markdown code span, its fence longer than any backtick run inside."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _flat(text: str) -> str:
    """`text` on one line: each whitespace run, a newline included, as one space."""
    return " ".join(text.split())


def _cell(text: str) -> str:
    """`text` as one Markdown table cell: whitespace runs as one space, `|` escaped."""
    return _flat(text).replace("|", "\\|")


def library_details(bundle, mode: str) -> dict[str, dict]:
    """What each library's reference file and evidence report row take from its
    per_library_extractions[] entry, by library: version (None when absent),
    status, file_count (0 when absent), usage_patterns, warnings, the items of
    its `temporal` lists in TEMPORAL_LISTS order and, in compose mode, its
    `exports` and the non-empty string `signatures`. Takes a bundle
    bundle_stack has read. Raises InputError naming the field."""
    out: dict[str, dict] = {}
    for i, entry in enumerate(bundle["per_library_extractions"]):
        where = f"the bundle's per_library_extractions[{i}]"
        temporal = entry.get("temporal")
        if temporal is None:
            temporal = {}
        if not isinstance(temporal, dict):
            raise InputError(f"{where}.temporal must be an object; got {temporal!r}")
        detail = {
            "version": _optional_string(entry.get("version"), f"{where}.version"),
            "status": _optional_string(entry.get("status"), f"{where}.status"),
            "file_count": entry.get("file_count") or 0,
            "usage_patterns": _string_list(entry.get("usage_patterns"), f"{where}.usage_patterns"),
            "warnings": _string_list(entry.get("warnings"), f"{where}.warnings"),
            "temporal": [item for name in TEMPORAL_LISTS
                         for item in _string_list(temporal.get(name), f"{where}.temporal.{name}")],
        }
        if mode == "compose":
            signatures = entry.get("signatures")
            if signatures is None:
                signatures = {}
            if not isinstance(signatures, dict):
                raise InputError(f"{where}.signatures must be an object; got {signatures!r}")
            detail["exports"] = list(dict.fromkeys(_string_list(entry.get("exports"), f"{where}.exports")))
            detail["signatures"] = {name: value.strip() for name, value in signatures.items()
                                    if isinstance(value, str) and value.strip()}
        out[entry["library"]] = detail
    return out


def library_records(entries: list[dict], names: list[str]) -> dict[str, list[dict]]:
    """The export records of each library of `names`, in records order. Raises
    InputError on a record that names no library of the bundle or holds a
    field of the wrong type."""
    found: dict[str, list[dict]] = {name: [] for name in names}
    for i, record in enumerate(entries):
        where = f"entries[{i}]"
        library = record.get("source_library")
        if not isinstance(library, str) or library not in found:
            raise InputError(f"{where}.source_library {library!r} is not a library of the bundle's "
                             f"per_library_extractions")
        name = record.get("export_name")
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{where}.export_name must be a non-empty string; got {name!r}")
        for field in ("export_type", "return_type", "source_file"):
            _optional_string(record.get(field), f"{where}.{field}")
        _string_list(record.get("params"), f"{where}.params")
        line = record.get("source_line")
        if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            raise InputError(f"{where}.source_line must be a whole number or null; got {line!r}")
        found[library].append(record)
    return found


def export_line(record: dict) -> str:
    """A code-mode Key Exports line: the export's name, `(params)` for a
    function or class and ` -> {return_type}` for a function, in a code span,
    then its type in italics and its `(source_file:source_line)`."""
    kind = _optional_string(record.get("export_type"), "export_type")
    signature = record["export_name"].strip()
    if kind and kind.lower() in ("function", "class"):
        signature += "(" + ", ".join(record.get("params") or []) + ")"
    return_type = _optional_string(record.get("return_type"), "return_type")
    if kind and kind.lower() == "function" and return_type:
        signature += f" -> {return_type}"
    line = f"- {_code_span(_flat(signature))}"
    if kind:
        line += f" *{_flat(kind)}*"
    source = _optional_string(record.get("source_file"), "source_file")
    if source:
        number = record.get("source_line")
        line += f" ({_flat(source)}:{number})" if isinstance(number, int) else f" ({_flat(source)})"
    return line


def compose_export_line(name: str, signatures: dict[str, str], library: str) -> str:
    """A compose-mode Key Exports line: the export's signature, or its name, then its constituent."""
    return f"- {_code_span(_flat(signatures.get(name, name)))} [from skill: {library}]"


def pair_counts(data) -> dict[frozenset[str], int]:
    """Each pair's `intersection_count` in a skf-pair-intersect.py result, keyed
    by its two libraries. Raises InputError on a result pair_files refuses or a
    count that is not a whole number."""
    pair_files(data)
    counts: dict[frozenset[str], int] = {}
    for i, pair in enumerate(data["pairs"]):
        count = pair.get("intersection_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise InputError(f"the pair-intersect result's pairs[{i}].intersection_count must be a whole number; "
                             f"got {count!r}")
        counts[frozenset((pair["a"], pair["b"]))] = count
    return counts


def bundle_pairs(bundle, mode: str, counts: dict[frozenset[str], int] | None = None) -> list[dict]:
    """The bundle's integrations[], in its order, as the pair files and the
    evidence report write them: a, b, type, tier, qualifier (canonical),
    description, key_files, evidence, reference, vs ({overall, pair} or None)
    and co_import_files, its pair's intersection_count in `counts` in code mode
    (None without `counts`) and 0 in compose mode. Takes a bundle bundle_stack
    has read. Raises InputError naming the field, or a code-mode pair `counts`
    has no entry for."""
    out = []
    for i, pair in enumerate(bundle.get("integrations", [])):
        where = f"the bundle's integrations[{i}]"
        if not isinstance(pair.get("type"), str) or not pair["type"].strip():
            raise InputError(f"{where}.type must be a non-empty string; got {pair.get('type')!r}")
        detection_method(mode, pair.get("qualifier"), where)
        qualifier = _token(pair.get("qualifier"), tuple(DETECTION_METHODS[mode]), f"{where}.qualifier")
        vs = pair.get("vs")
        if vs is not None:
            if not isinstance(vs, dict) or not all(isinstance(vs.get(key), str) and vs[key].strip()
                                                   for key in ("overall", "pair")):
                raise InputError(f"{where}.vs must be null or an object with string `overall` and `pair`; got {vs!r}")
            verdict = vs["pair"].strip()
            vs = {"overall": vs["overall"].strip(),
                  "pair": next((flag for flag in _VS_FLAGGED if flag.lower() == verdict.lower()), verdict)}
        co_import_files: int | None = 0
        if mode == "code":
            co_import_files = None
            if counts is not None:
                co_import_files = counts.get(frozenset((pair["a"], pair["b"])))
                if co_import_files is None:
                    raise InputError(f"{where} ({pair['a']} + {pair['b']}) has no entry in the pair-intersect "
                                     f"result (--pairs)")
        out.append({
            "a": pair["a"], "b": pair["b"], "type": pair["type"].strip(),
            "tier": _token(pair.get("tier"), TIERS, f"{where}.tier"),
            "qualifier": qualifier,
            "description": _optional_string(pair.get("description"), f"{where}.description"),
            "key_files": _string_list(pair.get("key_files"), f"{where}.key_files"),
            "evidence": _string_list(pair.get("evidence"), f"{where}.evidence"),
            "reference": _optional_string(pair.get("reference"), f"{where}.reference"),
            "vs": vs,
            "co_import_files": co_import_files,
        })
    return out


def pair_label(mode: str, pair: dict) -> str:
    """A pair's Confidence label: `{tier} ({qualifier})`, in compose mode with
    `[composed]` (`[inferred from shared domain]` for that qualifier) and a
    `[VS: Risky]` or `[VS: Blocked]` annotation for those pair verdicts."""
    label = f"{pair['tier']} ({pair['qualifier']})"
    if mode == "compose":
        label += " [inferred from shared domain]" if pair["qualifier"] == _INFERRED_QUALIFIER else " [composed]"
        if pair["vs"] is not None and pair["vs"]["pair"] in _VS_FLAGGED:
            label += f" [VS: {pair['vs']['pair']}]"
    return label


def library_file(mode: str, name: str, tier: str, detail: dict, records: list[dict] | None) -> str:
    """A library's references/{name}.md: the header, Key Exports and, when its
    `temporal` holds an item, Migration & Deprecation, with a marker line for
    each part the step writes (LIBRARY_SLOTS)."""
    if mode == "code":
        count = f"**Import count:** {detail['file_count']} files"
        exports = [export_line(record) for record in records or []]
    else:
        count = f"**Export count:** {len(detail['exports'])} exports"
        exports = [compose_export_line(export, detail["signatures"], name) for export in detail["exports"]]
    lines = [f"# {name} Reference", "", f"**Version:** {_flat(detail['version'] or 'unknown')}", count,
             f"**Confidence:** {tier}", "", "## Key Exports", "", *(exports or [NONE_RECORDED]), "",
             "## Usage Patterns", "", _marker("usage-patterns"), ""]
    if detail["temporal"]:
        lines += ["## Migration & Deprecation", "", *(f"- {_flat(item)}" for item in detail["temporal"]), ""]
    lines += ["## Common Imports", "", _marker("common-imports")]
    return "\n".join(lines) + "\n"


def pair_file(mode: str, pair: dict) -> str:
    """A pair's references/integrations/{a}-{b}.md: the header and Key Files
    (code mode: its key_files; compose mode: its evidence and reference lines
    and, with a [VS] verdict, its VS lines), with a marker line for each part
    the step writes (PAIR_SLOTS)."""
    if mode == "code":
        key_files = list(pair["key_files"])
    else:
        key_files = [*pair["evidence"], *([pair["reference"]] if pair["reference"] else [])]
        if pair["vs"] is not None:
            key_files += [f"VS overall: {pair['vs']['overall']}", f"VS pair: {pair['vs']['pair']}"]
    lines = [f"# {pair['a']} + {pair['b']} Integration", "", f"**Type:** {_flat(pair['type'])}",
             f"**Co-import files:** {pair['co_import_files'] or 0}", f"**Confidence:** {pair_label(mode, pair)}", "",
             "## Integration Pattern", "", _marker("integration-pattern"), "",
             "## Key Files", "", *([f"- {_flat(item)}" for item in key_files] or [NONE_RECORDED]), "",
             "## Usage Convention", "", _marker("usage-convention")]
    return "\n".join(lines) + "\n"


def index_row(name: str, count: int, tier: str, exports: list[str], link: str) -> str:
    """A Library Reference Index row: the first INDEX_EXPORTS export names in
    code spans, then `, +N more`."""
    names = list(dict.fromkeys(exports))
    shown = ", ".join(_code_span(export) for export in names[:INDEX_EXPORTS]) or NONE_RECORDED
    if len(names) > INDEX_EXPORTS:
        shown += f", +{len(names) - INDEX_EXPORTS} more"
    return f"| {_cell(name)} | {count} | {_cell(shown)} | {tier} | [ref]({link}) |"


def _check_name(name: str, where: str) -> None:
    """Refuse a name whose `{name}.md` would land outside --out: an absolute
    one, one with a `\\`, a NUL or an empty, `.` or `..` part."""
    if ("\\" in name or "\0" in name or PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise InputError(f"{where} {name!r} would write outside --out: a name is relative, with no `\\`, "
                         f"no empty part and no `.` or `..` part")


def reference_files(mode: str, libraries: list[dict], details: dict[str, dict],
                    records: dict[str, list[dict]] | None, pairs: list[dict]) -> list[tuple[str, str, list[str]]]:
    """(path relative to --out, text, slots) of each library file, then each
    pair file. Raises InputError on a name that would escape --out, or two
    files that would land on one path (compared case-folded, as a Windows or
    macOS file system does)."""
    files = []
    for i, library in enumerate(libraries):
        name = library["name"]
        _check_name(name, f"the bundle's per_library_extractions[{i}].library")
        files.append((f"{name}.md", library_file(mode, name, library["confidence"], details[name],
                                                 None if records is None else records[name]), list(LIBRARY_SLOTS)))
    for pair in pairs:
        files.append((f"integrations/{pair['a']}-{pair['b']}.md", pair_file(mode, pair), list(PAIR_SLOTS)))
    seen: dict[str, str] = {}
    for path, _text, _slots in files:
        key = path.casefold()
        if key in seen:
            raise InputError(f"two files would be written to one path: {seen[key]!r} and {path!r}")
        seen[key] = path
    return files


def _write_files(out: Path, files: list[tuple[str, str, list[str]]]) -> None:
    """Write each file under `out`, creating its folders. Raises WriteError
    after removing what this call wrote and the folders it created."""
    written: list[Path] = []
    created: list[Path] = []
    try:
        for relative, text, _slots in files:
            path = out.joinpath(*relative.split("/"))
            missing, folder = [], path.parent
            while not folder.exists():
                missing.append(folder)
                if folder.parent == folder:
                    break
                folder = folder.parent
            created.extend(reversed(missing))
            _write_text_atomic(path, text)
            written.append(path)
    except WriteError:
        for path in written:
            with contextlib.suppress(OSError):
                path.unlink()
        for folder in reversed(created):
            with contextlib.suppress(OSError):
                folder.rmdir()
        raise


def references(mode: str, libraries: list[dict], pairs_of_order: list[tuple[str, str]], details: dict[str, dict],
               records: dict[str, list[dict]] | None) -> dict:
    """The Library Reference Index of the stack: its head and one row per
    library in library_order, each in its inline and its catalog form."""
    tiers = {library["name"]: library["confidence"] for library in libraries}
    rows = []
    for name in library_order(mode, libraries, pairs_of_order):
        detail = details[name]
        if mode == "code":
            count = detail["file_count"]
            exports = [record["export_name"].strip() for record in (records or {}).get(name, [])]
        else:
            count, exports = len(detail["exports"]), detail["exports"]
        rows.append({
            "library": name,
            "inline": index_row(name, count, tiers[name], exports, f"references/{name}.md"),
            "catalog": index_row(name, count, tiers[name], exports, f"{name}.md"),
        })
    return {"header": list(INDEX_HEADER[mode]), "rows": rows}


def bundle_failed(bundle) -> list[dict]:
    """The bundle's failed[], each {library, reason}; [] when absent. Raises InputError."""
    failed = bundle.get("failed")
    if failed is None:
        return []
    if not isinstance(failed, list):
        raise InputError("the bundle's `failed` must be an array of {library, reason} objects")
    out = []
    for i, item in enumerate(failed):
        where = f"the bundle's failed[{i}]"
        if not isinstance(item, dict) or not isinstance(item.get("library"), str) or not item["library"].strip():
            raise InputError(f"{where} must be an object with a non-empty string `library`; got {item!r}")
        out.append({"library": item["library"],
                    "reason": _optional_string(item.get("reason"), f"{where}.reason") or "no reason recorded"})
    return out


# Keep the rules identical to skf-emit-result-envelope.py's read_sink (a test
# runs both on one sink), so the report lists what the envelope carries.
def read_sink(run_dir: Path) -> tuple[list[dict], list[str], dict[str, list[str]]]:
    """(decisions, warnings, problems by sink file) of a run folder, by the
    rules of skf-emit-result-envelope.py's read_sink: lines end at a newline
    only, a decision is a non-empty JSON object and a warning a non-empty JSON
    string, and any other line, such as a write cut short, is named in
    problems as `sink_line_unreadable: <file>:<line>`. A missing file holds
    nothing."""
    decisions: list[dict] = []
    warnings: list[str] = []
    problems: dict[str, list[str]] = {SINK_DECISIONS: [], SINK_WARNINGS: []}
    for name, kind in ((SINK_DECISIONS, dict), (SINK_WARNINGS, str)):
        try:
            text = (run_dir / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError) as exc:
            problems[name].append(f"sink_line_unreadable: {name}: {exc}")
            continue
        for number, line in enumerate(text.split("\n"), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                value = None
            if not isinstance(value, kind) or not value:
                problems[name].append(f"sink_line_unreadable: {name}:{number}")
            elif kind is dict:
                decisions.append(value)
            else:
                warnings.append(value.strip())
    return decisions, warnings, problems


def _read_map(path: str) -> tuple[dict | None, str | None]:
    """(the provenance map, None), or (None, why it cannot be read)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read the provenance map {path}: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"the provenance map {path} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"the provenance map {path} is not a JSON object"
    return data, None


def map_distribution(prov: dict | None, reason: str | None) -> tuple[dict | None, str | None]:
    """(the map entries' confidence_distribution by signature_source, None), as
    skf-render-metadata-stats.py --shape stack bins them, or (None, why not)."""
    if prov is None:
        return None, reason
    try:
        stats = _load_stats_rules()
        return stats.derive_stats(prov, {}, _STATS_SHAPE)["confidence_distribution"], None
    except ImportError as exc:
        return None, str(exc)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return None, f"{_STATS_HELPER} cannot bin the map: {exc}"


def _value(value) -> str:
    """A sink value as text on one line: a string as it stands, anything else as JSON."""
    return _flat(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


def decision_line(decision: dict) -> str:
    """An Auto-Decisions line: the gate, the action taken and why, then the
    scope gate's dropped libraries and prior_kept when its evidence holds them."""
    line = (f"- {_code_span(_value(decision.get('gate')))}: {_value(decision.get('taken_action'))} "
            f"({_value(decision.get('reason'))})")
    evidence = decision.get("evidence")
    if isinstance(evidence, dict):
        if "dropped" in evidence:
            dropped = evidence["dropped"] if isinstance(evidence["dropped"], list) else [evidence["dropped"]]
            names = [f"{_value(item.get('library'))} ({_value(item.get('reason'))})" if isinstance(item, dict)
                     else _value(item) for item in dropped]
            line += f"; dropped: {', '.join(names) or 'none'}"
        if "prior_kept" in evidence:
            kept = evidence["prior_kept"] if isinstance(evidence["prior_kept"], list) else [evidence["prior_kept"]]
            line += f"; prior_kept: {', '.join(_value(item) for item in kept) or 'none'}"
    return line


def evidence_report(mode: str, libraries: list[dict], pairs_of_order: list[tuple[str, str]],
                    details: dict[str, dict], failed: list[dict], pairs: list[dict], prov: dict | None,
                    sink: tuple[list[dict], list[str], dict[str, list[str]]],
                    distribution: dict | None, reason: str | None) -> str:
    """evidence-report.md: the libraries (failed[] included), the pairs, the
    run's warnings and auto-decisions, and the map entries per tier."""
    decisions, warnings, problems = sink
    skill_name = prov.get("skill_name") if prov is not None else None
    title = _flat(skill_name) if isinstance(skill_name, str) and skill_name.strip() else _REPORT_FALLBACK_TITLE
    entries = prov.get("entries") if prov is not None else None
    map_counts: dict[str, int] | None = None
    if prov is not None:
        map_counts = {}
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("source_library"), str):
                map_counts[entry["source_library"]] = map_counts.get(entry["source_library"], 0) + 1
    tiers = {library["name"]: library["confidence"] for library in libraries}
    lines = [f"# {title} Evidence Report", "",
             f"**Mode:** {mode} | **Libraries:** {len(libraries)} extracted, {len(failed)} failed | "
             f"**Integration pairs:** {len(pairs)}", "", "## Libraries", ""]
    if libraries:
        lines += [f"| Library | Status | Version | Tier | {'Imports' if mode == 'code' else 'Exports'} | Map entries "
                  f"| Usage patterns | T2 items | Warnings |",
                  "|---------|--------|---------|------|---------|-------------|----------------"
                  "|----------|----------|"]
        for name in library_order(mode, libraries, pairs_of_order):
            detail = details[name]
            count = detail["file_count"] if mode == "code" else len(detail["exports"])
            in_map = "n/a" if map_counts is None else str(map_counts.get(name, 0))
            cells = [name, detail["status"] or "n/a", detail["version"] or "unknown", tiers[name], str(count), in_map,
                     str(len(detail["usage_patterns"])), str(len(detail["temporal"])),
                     "; ".join(detail["warnings"]) or "none"]
            lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    else:
        lines.append("none")
    failures = "; ".join(f"{item['library']}: {item['reason']}" for item in failed) or "none"
    lines += ["", f"**Failed:** {' '.join(failures.split())}", "", "## Integrations", ""]
    if pairs:
        lines += ["| Pair | Type | Confidence | Co-import files |", "|------|------|------------|-----------------|"]
        for pair in pairs:
            cells = [f"{pair['a']} + {pair['b']}", pair["type"], pair_label(mode, pair),
                     str(pair["co_import_files"] or 0)]
            lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    else:
        lines.append("none")
    lines += ["", "## Warnings", ""]
    warning_lines = [f"- {_flat(warning)}" for warning in warnings]
    warning_lines += [f"- {_flat(problem)}" for problem in problems[SINK_WARNINGS]]
    lines += warning_lines or ["none"]
    lines += ["", "## Auto-Decisions", ""]
    decision_lines = [decision_line(decision) for decision in decisions]
    decision_lines += [f"- {_flat(problem)}" for problem in problems[SINK_DECISIONS]]
    lines += decision_lines or ["none"]
    lines += ["", "## Confidence Distribution", ""]
    head = "Provenance entries by `signature_source` (`metadata.json` counts libraries): "
    if distribution is None:
        lines.append(f"{head}not computed: {' '.join(str(reason).split())}")
    else:
        lines.append(head + ", ".join(f"{tier}: {distribution.get(key, 0)}" for key, tier in _DISTRIBUTION_BINS))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Context snippet (generate-output section 5)
# --------------------------------------------------------------------------

# The token budget of the snippet, in len(text)//4 tokens, when --budget names none.
SNIPPET_BUDGET = 120
# The trim stages, in the order the cascade applies them while the snippet is
# above its budget.
SNIPPET_TRIMS = ("gotchas", "stack-versions", "stack-top-8", "integrations-top-5")
# How many libraries stack-top-8 and pairs integrations-top-5 keep.
SNIPPET_STACK_KEEP = 8
SNIPPET_PAIRS_KEEP = 5
# The template's IMPORTANT line, never trimmed. The dash is the template's own
# character, written as an escape.
SNIPPET_IMPORTANT = ("|IMPORTANT: {stack_name} \u2014 read SKILL.md before writing integration code. "
                     "Do NOT rely on training data.")
# The stack or integrations line of a stack with no library or no pair.
SNIPPET_NONE = "none"


def snippet_tokens(text: str) -> int:
    """The snippet's token estimate: len(text)//4, as skf-validate-output.py and skf-count-tokens.py count it."""
    return len(text) // 4


def snippet_stack(mode: str, libraries: list[dict], details: dict[str, dict]) -> list[tuple[str, str | None]]:
    """Each library as (name, version), by file_count (compose mode: its number
    of distinct exports), the highest first, then by name. The version is on
    one line, as a reference file's **Version:** line writes it."""
    def count(name: str) -> int:
        detail = details[name]
        return detail["file_count"] if mode == "code" else len(detail["exports"])

    names = sorted((library["name"] for library in libraries), key=lambda name: (-count(name), *_name_key(name)))
    return [(name, details[name]["version"] and _flat(details[name]["version"])) for name in names]


def snippet_pairs(pairs: list[dict]) -> list[str]:
    """Each pair as `{a}+{b}`, by its co-import file count (0 in compose mode),
    the highest first, ties in bundle order."""
    ranked = sorted(pairs, key=lambda pair: -(pair["co_import_files"] or 0))
    return [f"{pair['a']}+{pair['b']}" for pair in ranked]


def _cut(items: list[str], keep: int) -> list[str]:
    """The first `keep` items, then `...+{N} more` for the N cut."""
    if len(items) <= keep:
        return items
    return [*items[:keep], f"...+{len(items) - keep} more"]


def snippet_text(stack_name: str, version: str, stack: list[tuple[str, str | None]], pairs: list[str],
                 gotchas: str | None, trims: list[str]) -> str:
    """context-snippet.md in the bundled template's form, with the trim stages
    `trims` applied."""
    keep_versions = "stack-versions" not in trims
    names = [f"{name}@{library_version}" if keep_versions and library_version else name
             for name, library_version in stack]
    if "stack-top-8" in trims:
        names = _cut(names, SNIPPET_STACK_KEEP)
    if "integrations-top-5" in trims:
        pairs = _cut(pairs, SNIPPET_PAIRS_KEEP)
    lines = [f"[{stack_name} v{version}]|root: skills/{stack_name}/",
             SNIPPET_IMPORTANT.format(stack_name=stack_name),
             "|stack: " + (", ".join(names) or SNIPPET_NONE),
             "|integrations: " + (", ".join(pairs) or SNIPPET_NONE)]
    if gotchas and "gotchas" not in trims:
        lines.append(f"|gotchas: {gotchas}")
    return "\n".join(lines) + "\n"


def trim_snippet(stack_name: str, version: str, stack: list[tuple[str, str | None]], pairs: list[str],
                 gotchas: str | None, budget: int) -> tuple[str, list[str]]:
    """The snippet and the trim stages applied: while it is above `budget`,
    the next stage of SNIPPET_TRIMS, a stage that does not shorten it skipped."""
    trims: list[str] = []
    text = snippet_text(stack_name, version, stack, pairs, gotchas, trims)
    for stage in SNIPPET_TRIMS:
        if snippet_tokens(text) <= budget:
            break
        trimmed = snippet_text(stack_name, version, stack, pairs, gotchas, [*trims, stage])
        if len(trimmed) < len(text):
            trims.append(stage)
            text = trimmed
    return text, trims


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_input(source: str):
    """The parsed JSON of a file path, or of stdin for '-'. Raises InputError."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read the input {source}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"the input {source} is not valid JSON: {exc}") from exc


def _write_atomic(path: Path, data: dict) -> None:
    """Write `data` as JSON to `path` atomically. Raises WriteError, leaving
    `path` as it was."""
    _write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _write_text_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` as UTF-8, `\\n` line ends on every OS, atomically:
    a temp file of its own beside it, then a rename. Raises WriteError,
    leaving `path` as it was."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.skf-tmp")
    payload = text.encode("utf-8")
    # O_EXCL: never write into another writer's temp file. O_BINARY (Windows
    # only; 0 elsewhere) keeps the \n line ends.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, flags, 0o644)
    except OSError as exc:
        raise WriteError(f"cannot write {path}: {exc.strerror or exc}") from exc
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
                time.sleep(_REPLACE_POLL_SECONDS)
    except BaseException as exc:
        with contextlib.suppress(OSError):
            tmp.unlink()
        if isinstance(exc, OSError):
            raise WriteError(f"cannot write {path}: {exc.strerror or exc}") from exc
        raise


def _records_file(value: str, command: str, flag: str = "--records") -> str:
    """The path a command reads from a file, never stdin (--records, or --bundle)."""
    if value == "-":
        raise InputError(f"{command} reads {flag} from a file, not stdin")
    return value


def _cmd_relabel(args: argparse.Namespace) -> tuple[dict, int]:
    stats = _load_stats_rules()
    data = _read_input(_records_file(args.records, "relabel"))
    entries = parse_records(data)
    relabeled, distribution, coherence = relabel(stats, entries)
    if relabeled:
        _write_atomic(Path(args.records), data)
    result = {"relabeled": relabeled, "confidence_distribution": distribution, "coherence": coherence}
    return result, 0 if coherence["ok"] else 1


def _cmd_library_tiers(args: argparse.Namespace) -> dict:
    names = parse_library_names(args.libraries)
    return {"libraries": library_tiers(_read_input(args.records), names)}


def _stack(args: argparse.Namespace, command: str) -> tuple[str, list[dict], list[tuple[str, str]]]:
    """(mode, libraries, pairs) from --input, or from --bundle and, for
    pair-tiers on a code-mode bundle, --pairs. Raises InputError."""
    pairs_source = getattr(args, "pairs", None)
    if args.input is not None:
        if pairs_source is not None:
            raise InputError("--pairs goes with --bundle; the --input JSON holds its own integrations")
        return parse_stack(_read_input(args.input))
    bundle = _read_input(_records_file(args.bundle, command, "--bundle"))
    pairs = None
    if command == "pair-tiers":
        mode = bundle_mode(bundle)
        if mode == "code" and pairs_source is None:
            raise InputError("a code-mode bundle needs --pairs, the qualifying pairs as a JSON array of {a, b}")
        if mode == "compose" and pairs_source is not None:
            raise InputError("--pairs is for a code-mode bundle; this bundle's mode is compose")
        if pairs_source is not None:
            pairs = _read_input(pairs_source)
    return bundle_stack(bundle, pairs)


def _cmd_pair_tiers(args: argparse.Namespace) -> dict:
    mode, libraries, pairs = _stack(args, "pair-tiers")
    return {"mode": mode, "integrations": pair_tiers(mode, libraries, pairs)}


def _cmd_metadata(args: argparse.Namespace) -> dict:
    return stack_metadata(*_stack(args, "metadata"))


def _cmd_provenance(args: argparse.Namespace) -> dict:
    entries = parse_records(_read_input(_records_file(args.records, "provenance")))
    bundle = _read_input(_records_file(args.bundle, "provenance", "--bundle"))
    mode = bundle_mode(bundle)
    compose_flags = {"--inventory": args.inventory, "--skills-root": args.skills_root,
                     "--project-root": args.project_root}
    if mode == "code":
        given = [flag for flag, value in compose_flags.items() if value is not None]
        if given:
            raise InputError(f"{', '.join(given)} is for a compose-mode bundle; this bundle's mode is code")
        if args.pairs is None:
            raise InputError("a code-mode bundle needs --pairs, the skf-pair-intersect.py result")
        pairs = pair_files(_read_input(_records_file(args.pairs, "provenance", "--pairs")))
    elif args.pairs is not None:
        raise InputError("--pairs is for a code-mode bundle; this bundle's mode is compose")
    else:
        missing = [flag for flag, value in compose_flags.items() if value is None]
        if missing:
            raise InputError(f"a compose-mode bundle needs {', '.join(missing)}")
        pairs = None
    base = _read_input(args.input)
    if not isinstance(base, dict):
        raise InputError(f"the provenance map input must be a JSON object; got {type(base).__name__}")
    integrations = bundle_integrations(bundle, pairs)
    constituents = None
    if mode == "compose":
        hashes = inventory_hashes(_read_input(_records_file(args.inventory, "provenance", "--inventory")))
        constituents = compose_constituents(bundle, hashes, args.skills_root, args.project_root,
                                            base.get("generated_at"))
        entries = compose_entries(bundle, entries)
    target = Path(args.target)
    _write_atomic(target, provenance_map(base, entries, integrations, constituents))
    result = {"target": str(target), "entry_count": len(entries), "integration_count": len(integrations)}
    if constituents is not None:
        result["constituent_count"] = len(constituents)
    return result


def _cmd_references(args: argparse.Namespace) -> dict:
    bundle = _read_input(_records_file(args.bundle, "references", "--bundle"))
    mode = bundle_mode(bundle)
    if args.mode != mode:
        raise InputError(f"--mode is {args.mode}, but the bundle's mode is {mode}")
    if mode == "compose":
        given = [flag for flag, value in (("--records", args.records), ("--pairs", args.pairs)) if value is not None]
        if given:
            raise InputError(f"{' and '.join(given)} is for a code-mode bundle; this bundle's mode is compose")
    elif args.records is None:
        raise InputError("a code-mode bundle needs --records, the export records each library's key exports come from")
    elif args.out is not None and args.pairs is None:
        raise InputError("--out on a code-mode bundle needs --pairs, the skf-pair-intersect.py result that holds "
                         "each pair's co-import file count")
    _mode, libraries, pairs_of_order = bundle_stack(bundle)
    details = library_details(bundle, mode)
    records = None
    if mode == "code":
        records = library_records(parse_records(_read_input(_records_file(args.records, "references"))),
                                  [library["name"] for library in libraries])
    counts = None
    if args.pairs is not None:
        counts = pair_counts(_read_input(_records_file(args.pairs, "references", "--pairs")))
    pairs = bundle_pairs(bundle, mode, counts)
    result = {"mode": mode, "index": references(mode, libraries, pairs_of_order, details, records), "written": []}
    if args.out is not None:
        files = reference_files(mode, libraries, details, records, pairs)
        _write_files(Path(args.out), files)
        result["written"] = [{"path": path, "placeholders": slots} for path, _text, slots in files]
    return result


def _cmd_evidence_report(args: argparse.Namespace) -> dict:
    bundle = _read_input(_records_file(args.bundle, "evidence-report", "--bundle"))
    mode = bundle_mode(bundle)
    if mode == "code" and args.pairs is None:
        raise InputError("a code-mode bundle needs --pairs, the skf-pair-intersect.py result that holds each "
                         "pair's co-import file count")
    if mode == "compose" and args.pairs is not None:
        raise InputError("--pairs is for a code-mode bundle; this bundle's mode is compose")
    _mode, libraries, pairs_of_order = bundle_stack(bundle)
    details = library_details(bundle, mode)
    failed = bundle_failed(bundle)
    counts = None
    if args.pairs is not None:
        counts = pair_counts(_read_input(_records_file(args.pairs, "evidence-report", "--pairs")))
    pairs = bundle_pairs(bundle, mode, counts)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise InputError(f"--run-dir {args.run_dir} is not a folder")
    sink = read_sink(run_dir)
    prov, reason = _read_map(args.provenance)
    distribution, reason = map_distribution(prov, reason)
    target = Path(args.target)
    _write_text_atomic(target, evidence_report(mode, libraries, pairs_of_order, details, failed, pairs, prov, sink,
                                               distribution, reason))
    return {"target": str(target), "library_count": len(libraries), "failed_count": len(failed),
            "integration_count": len(pairs), "warning_count": len(sink[1]), "decision_count": len(sink[0]),
            "confidence_distribution": distribution}


def _read_text(source: str, what: str) -> str:
    """The text of a file path, or of stdin for '-'. Raises InputError."""
    try:
        return sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {what} {source}: {exc}") from exc


def _snippet_word(value: str, flag: str) -> str:
    """A --stack-name or --version value: non-empty, with no whitespace. Raises InputError."""
    if not value or any(char.isspace() for char in value):
        raise InputError(f"{flag} must be a non-empty value with no whitespace; got {value!r}")
    return value


def _budget(value: str) -> int:
    """The --budget value: a positive whole number. Raises InputError."""
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        raise InputError(f"--budget must be a positive whole number; got {value!r}")
    return int(value)


def _cmd_snippet(args: argparse.Namespace) -> dict:
    stack_name = _snippet_word(args.stack_name, "--stack-name")
    version = _snippet_word(args.version, "--version")
    budget = _budget(args.budget)
    bundle = _read_input(_records_file(args.bundle, "snippet", "--bundle"))
    mode = bundle_mode(bundle)
    if mode == "code" and args.pairs is None:
        raise InputError("a code-mode bundle needs --pairs, the skf-pair-intersect.py result that holds each "
                         "pair's co-import file count")
    if mode == "compose" and args.pairs is not None:
        raise InputError("--pairs is for a code-mode bundle; this bundle's mode is compose")
    _mode, libraries, _pairs = bundle_stack(bundle)
    details = library_details(bundle, mode)
    counts = None
    if args.pairs is not None:
        counts = pair_counts(_read_input(_records_file(args.pairs, "snippet", "--pairs")))
    pairs = snippet_pairs(bundle_pairs(bundle, mode, counts))
    gotchas = None
    if args.gotchas is not None:
        gotchas = _flat(_read_text(args.gotchas, "the gotchas")) or None
    text, trims = trim_snippet(stack_name, version, snippet_stack(mode, libraries, details), pairs, gotchas, budget)
    target = Path(args.target)
    _write_text_atomic(target, text)
    tokens = snippet_tokens(text)
    return {"target": str(target), "tokens": tokens, "trims_applied": trims, "over_budget": tokens > budget}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-render-stack-metadata",
        description=(
            "Relabel a code-mode stack's export records against the label check of "
            "skf-render-metadata-stats.py, compute its library tiers (T1 only when an "
            "ast-grep rule matched every export), its pair tiers (the weaker of the "
            "two libraries' tiers, in both modes) and the counted and ranked fields "
            "of its metadata.json: counts, libraries, integration_pairs, "
            "confidence_distribution (each library once), confidence_tier (the "
            "dominant tier) and source_authority (the lowest, community for a "
            "library that records none), with its hub libraries and library "
            "order, and write its provenance map from the records, the extraction "
            "bundle (each pair's detection_method from its qualifier) and, in code "
            "mode, the pair-intersect result or, in compose mode, the stack inventory, "
            "the fixed parts of its reference and pair files with their Library "
            "Reference Index rows, its evidence report and its context snippet, "
            "trimmed to a token budget."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    text = ("relabel the export records against the label check, rewrite the file when a "
            "label changed, and print the relabeled exports and the label counts as JSON")
    command = sub.add_parser("relabel", help=text, description=text)
    command.add_argument(
        "--records", required=True, help="path to the export records JSON ({entries: [...]}), rewritten in place")
    command.set_defaults(func=_cmd_relabel)
    text = "print each library's tier from its checked export records as JSON"
    command = sub.add_parser("library-tiers", help=text, description=text)
    command.add_argument(
        "--records",
        required=True,
        help="path to the export records JSON ({entries: [...]}), or '-' for stdin",
    )
    command.add_argument(
        "--libraries",
        required=True,
        help="the stack's libraries, comma-separated; a library with no record is T1-low",
    )
    command.set_defaults(func=_cmd_library_tiers)
    for name, func, text, bundle_help in (
        ("pair-tiers", _cmd_pair_tiers, "print the tier of each integration pair as JSON",
         "path to the extraction bundle JSON: its mode, the libraries of its per_library_extractions[] and, "
         "in compose mode, the pairs of its integrations[]"),
        ("metadata", _cmd_metadata,
         "print the computed metadata.json fields of the stack, its hubs and its library order as JSON",
         "path to the extraction bundle JSON: its mode, the libraries of its per_library_extractions[] and "
         "the pairs of its integrations[]"),
    ):
        command = sub.add_parser(name, help=text, description=text)
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--input",
            help="path to the stack JSON ({mode, libraries, integrations}), or '-' for stdin",
        )
        source.add_argument("--bundle", help=bundle_help)
        if name == "pair-tiers":
            command.add_argument(
                "--pairs",
                help="with a code-mode --bundle: path to the qualifying pairs, a JSON array of {a, b}, "
                     "or '-' for stdin",
            )
        command.set_defaults(func=func)
    text = ("write provenance-map.json from the run's files: its entries and integrations, "
            "and its constituents in compose mode")
    command = sub.add_parser("provenance", help=text, description=text)
    command.add_argument("--records", required=True, help="path to the export records JSON ({entries: [...]})")
    command.add_argument(
        "--bundle", required=True,
        help="path to the extraction bundle JSON, whose mode and integrations[] the map takes")
    command.add_argument(
        "--pairs", help="code mode: path to the skf-pair-intersect.py result, which holds each pair's co-import files")
    command.add_argument(
        "--inventory",
        help="compose mode: path to step 4's skf-enumerate-stack-skills.py result, which holds each metadata_hash")
    command.add_argument("--skills-root", help="compose mode: the skills output folder that holds each constituent")
    command.add_argument("--project-root", help="compose mode: the project root each skill_path is relative to")
    command.add_argument(
        "--input",
        required=True,
        help="path to the map's other fields as JSON (an object), or '-' for stdin",
    )
    command.add_argument("--target", required=True, help="the provenance-map.json to write")
    command.set_defaults(func=_cmd_provenance)
    text = ("print the Library Reference Index rows and, with --out, write the fixed parts of each "
            "per-library and pair reference file, a marker line for each part the step writes")
    command = sub.add_parser("references", help=text, description=text)
    command.add_argument("--mode", required=True, choices=MODES, help="the run's mode, which the bundle's must match")
    command.add_argument("--bundle", required=True, help="path to the extraction bundle JSON")
    command.add_argument(
        "--records", help="code mode: path to the export records JSON ({entries: [...]}), each library's key exports")
    command.add_argument(
        "--pairs", help="code mode, needed with --out: path to the skf-pair-intersect.py result, which holds each "
                        "pair's intersection_count")
    command.add_argument(
        "--out", help="the package's references/ folder to write {library}.md and integrations/{a}-{b}.md into; "
                      "without it nothing is written")
    command.set_defaults(func=_cmd_references)
    text = ("write evidence-report.md from the extraction bundle, the run sink and the provenance map, "
            "atomically")
    command = sub.add_parser("evidence-report", help=text, description=text)
    command.add_argument("--bundle", required=True, help="path to the extraction bundle JSON")
    command.add_argument(
        "--run-dir", required=True, help="the run folder that holds warnings.jsonl and headless-decisions.jsonl")
    command.add_argument(
        "--provenance", required=True, help="path to the provenance-map.json whose entries the report bins by tier")
    command.add_argument(
        "--pairs", help="code mode: path to the skf-pair-intersect.py result, which holds each pair's "
                        "intersection_count")
    command.add_argument("--target", required=True, help="the evidence-report.md to write")
    command.set_defaults(func=_cmd_evidence_report)
    text = ("write context-snippet.md from the extraction bundle in the bundled template's form, trimmed while "
            "its len(text)//4 tokens exceed --budget, atomically")
    command = sub.add_parser("snippet", help=text, description=text)
    command.add_argument("--bundle", required=True, help="path to the extraction bundle JSON")
    command.add_argument(
        "--pairs", help="code mode: path to the skf-pair-intersect.py result, which holds each pair's "
                        "intersection_count")
    command.add_argument("--stack-name", required=True, help="the stack's name, for the root and IMPORTANT lines")
    command.add_argument("--version", required=True, help="the stack's version, for the root line")
    command.add_argument(
        "--gotchas", help="the gotchas line's text: a file, or '-' for stdin; without it, or with a blank text, "
                          "the snippet has no gotchas line")
    command.add_argument(
        "--budget", default=str(SNIPPET_BUDGET),
        help=f"the token budget, a positive whole number (default {SNIPPET_BUDGET})")
    command.add_argument("--target", required=True, help="the context-snippet.md to write")
    command.set_defaults(func=_cmd_snippet)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except (InputError, ImportError, WriteError) as exc:
        print(f"error: {' '.join(str(exc).split())}", file=sys.stderr)
        return 2
    result, code = result if isinstance(result, tuple) else (result, 0)
    # ASCII escapes: a Windows console's code page cannot encode every name.
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure the standard streams to UTF-8, keeping each one's error handler.

    A Windows console pipes them as cp1252, which cannot carry every character
    a library name or an error message may hold. stdin is reconfigured before
    its first read, so `--input -` reads the UTF-8 JSON a step pipes.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
