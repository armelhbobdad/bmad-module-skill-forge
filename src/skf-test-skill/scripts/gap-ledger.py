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
         [--stale <file>] [--provenance <file>] [--skill-dir <dir>]
         [--metadata <path>] [--served <family>]...
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
            --numerator, --stale, --provenance, --skill-dir, --metadata.
            Barrel branch: each `missing` name is a Medium `missing-export`
            gap `Missing export: {name}`, or a Medium `missing-type` gap
            `Missing type: {name}` when the --signatures result lists it in
            `missingTypes`; its Source is the file and line the --surface
            result's `exports[]` records for it, else `{meta}`. Each `stale`
            name the --stale result (classify-stale) marks `fabricated` is a
            Critical `fabricated-signature` gap `Fabricated signature:
            {name}` at its `source` (one with no `source` is INVALID_INPUT,
            never a lesser gap). One whose `defined_at` (where the source
            declares it) is a Python or TS/JS `file:line` is a documented
            extra when its name has no dot and the --surface result was
            built from an extraction that read the whole scope (an
            `extraction` object, not `no-ast-grep`, `truncated` or
            `fallback.needed`: only such an extraction fills
            `excluded.outsideScope`, the names a brief scoped out) and its
            `excluded.outsideScope` list does not list
            it: an Info `observation` gap `Documented extra: {name}` at
            `defined_at`. With no `defined_at`, a homonym (its `declared_in`
            lists several declaring files) is one too, with --skill-dir,
            when the skill's `[AST:path:L<n>]` and `[SRC:path:L<n>]`
            citations on the lines of SKILL.md and references/**/*.md that
            name it (outside the citations), or on the next non-blank line
            after one, cite exactly one of those files: the gap
            is at that file's `declared_in` item, and two cited or none
            leave it Medium. The documented extra's issue names the line
            that documents it (with --skill-dir) and its remediation asks no
            change (update-skill never routes it) and says whether signature
            scoring compared its documented signature (a name the
            --signatures result lists in `comparedNames`). `excluded` is
            read once a stale name that is not fabricated needs it, and a
            malformed one is then INVALID_INPUT. Any other is a Medium `stale-documentation` gap
            `Stale documentation: {name}` at the first line of SKILL.md,
            then of references/*.md in path order, that writes the name
            (validate-inventory.py's match, with --skill-dir), else
            `SKILL.md`. Scalar and stack branches: a
            `missingCount` above 0 is one Medium `missing-export` gap
            `{missingCount} of {denominator} exports not documented` at
            `{meta}`, except that a scalar count taken from the verified
            numerator (`numeratorSource` `verified`) is replaced by one
            `Missing export: {name}` gap per --numerator `absent` name, at
            the first --provenance entry of that name, else `{meta}`.
            Every per-name gap carries `export`.
  guards    --input load-coverage-inputs.py's surface result; --metadata.
            `guards.deflation.fires` is a Medium `metadata-drift` gap at
            `{meta}` (else the result's `inputs.metadata`), and
            `guards.inflation.fires` a Medium `denominator-inflation` gap at
            the result's `inputs.brief` (else `skill-brief.yaml`), whose
            remediation recommends `stats.effective_denominator` when
            `guards.umbrella.umbrella` is true, else `scope.tier_a_include`.
            `guards.staleScope.fires` is one Medium `brief-scope-stale` gap
            at that brief, whose issue names each `unmatchedInclude` glob
            and each `restored` name with its file.
  numerator --input verify-declared-numerator.py's result; --metadata.
            `inflated` true is a High `numerator-inflation` gap at `{meta}`
            whose issue lists the `absent` names.
  metadata-coherence
            --input check-metadata-coherence.py's result; --metadata. Each
            `findings[]` entry, titled as it is and with its `detail` as the
            issue, at `{meta}`: Medium is a Medium `metadata-drift` gap, Info
            an Info `multi-denominator` gap.
  provenance-line
            --input skf-verify-provenance-completeness.py verify's result.
            Each `stale[]` item whose reason is `line-not-definition`, at
            its `{source_file}:{source_line}` with `export`: a Low
            `provenance-line` gap `Provenance line is not the definition of
            {export_name}` when `definition_lines` holds a line, else an Info
            `provenance-unverified` gap `Provenance line not verified for
            {export_name}`. Its other items are not gaps here.
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
      then by id. Each entry names its category as `{group} ({category})`,
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
import posixpath
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
    "provenance-line": ("Coverage", "a provenance line that is not the definition of its export"),
    "provenance-unverified": ("Coverage", "a provenance line the line-check rules could not verify"),
    "metadata-drift": ("Coverage", "export counts in the metadata that diverge from each other"),
    "denominator-inflation": ("Coverage", "a scope include union larger than the provenance map"),
    "brief-scope-stale": ("Coverage", "a scope.include glob in the brief that matches no source file"),
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
    "split-body-mismatch": ("Coherence", "SKILL.md and a references/ file that disagree about an export"),
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

# The Remediation Summary's Estimated Effort column, per severity.
EFFORT = {
    "Critical": "Read the source code and write or correct the documentation",
    "High": "Read the source code and write or correct the documentation",
    "Medium": "Add type definitions, interface docs or the missing section",
    "Low": "Add examples or metadata",
    "Info": "Optional improvements, no action required",
}

_ID_RE = re.compile(r"^GAP-(\d{3,})$")
_STAGE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_RUN_ID_FROM_NAME = re.compile(r"^test-findings-(.+)\.json$")


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
    release, unless a waiter has it open.
    """
    timeout = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    lock_path = path.with_name(path.name + ".skf-lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout

    def refuse() -> LedgerError:
        return LedgerError("LEDGER_LOCKED", f"another append held {lock_path} for more than {timeout:g} s")

    while True:
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
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
        {"surface", "signatures", "numerator", "stale", "provenance", "skill_dir", "metadata"}
    ),
    "guards": frozenset({"metadata"}),
    "numerator": frozenset({"metadata"}),
    "metadata-coherence": frozenset({"metadata"}),
    "provenance-line": frozenset(),
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
    documented-name match the stale-documentation Source uses)."""
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


def _documenting_line(skill_dir: Path, name: str) -> str | None:
    """The first line of SKILL.md, then of references/*.md in path order,
    that writes `name` (validate-inventory.py's match), as `file:line`."""
    pattern = _sibling("validate-inventory.py").name_pattern(name)
    refs = skill_dir / "references"
    files = [skill_dir / "SKILL.md"] + (sorted(refs.glob("*.md")) if refs.is_dir() else [])
    for path in files:
        try:
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.split("\n"), start=1):
            if pattern.search(line):
                return f"{path.relative_to(skill_dir).as_posix()}:{number}"
    return None


def _outside_scope(surface: dict | None) -> set[str] | None:
    """The names a surface result's `excluded.outsideScope` lists (defined in
    a file the brief scopes out). None with no surface, no such list, or a
    surface built without an extraction (no `extraction` object) or from
    one that did not read the whole scope (a `no-ast-grep` status, a
    `truncated` run, or `fallback.needed`): only an extraction fills that
    list, so the names a brief scoped out are then unknown."""
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
    return {row["name"] for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str)}


# The extensions classify-stale reads a `defined_at` in.
# Keep identical to PYTHON_EXTENSIONS | TSJS_EXTENSIONS in skf-verify-provenance-completeness.py.
_DEFINED_AT_EXTENSIONS = frozenset({".py", ".pyi", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"})
# classify-stale's `defined_at`: a Python or TS/JS file and a line.
_DEFINED_AT_RE = re.compile(
    r"^.+(?:" + "|".join(re.escape(e) for e in sorted(_DEFINED_AT_EXTENSIONS)) + r"):[1-9]\d*$", re.IGNORECASE)


# A source citation the skill writes, `[AST:path:L12]`, `[SRC:path:L12-34]` or `[SRC:path:L12-L34]` (one with no
# `:L<n>` part is ignored). Groups: prefix, path, first line, the `L` of a range's end, the range's end.
# Keep identical to _SKILL_CITATION_RE in skf-verify-provenance-completeness.py.
_SKILL_CITATION_RE = re.compile(
    r"\[(AST|SRC):([^\[\]\n]+?):L(\d+)(?:-(L?)(\d+))?\]"
)
# Any bracketed citation (`[AST:...]`, `[SRC:...]`, `[EXT:...]`): a line names a documented name outside them.
_ANY_CITATION_RE = re.compile(r"\[[A-Z]+:[^\[\]\n]*\]")


def _cited_path(path: str) -> str:
    """A cited or `declared_in` path as both compare: forward slashes, no `./`."""
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


def _skill_cited_files(skill_dir: Path, name: str) -> set[str]:
    """The files the skill's `[AST:]` and `[SRC:]` citations name on a line of
    SKILL.md or references/**/*.md that writes `name` outside its citations
    (validate-inventory.py's match), or on the next non-blank line (a
    heading, then its citation)."""
    pattern = _sibling("validate-inventory.py").name_pattern(name)
    cited: set[str] = set()
    for path in skill_markdown_files(skill_dir):
        try:
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        lines = text.split("\n")
        for number, line in enumerate(lines):
            if not pattern.search(_ANY_CITATION_RE.sub(" ", line)):
                continue
            following = next((ln for ln in lines[number + 1:] if ln.strip()), "")
            for cited_line in (line, following):
                cited.update(_cited_path(m.group(2)) for m in _SKILL_CITATION_RE.finditer(cited_line))
    return cited


def _documented_extra_at(name: str, item: dict, outside: set[str] | None,
                         skill_dir: str | None = None) -> tuple[str, int] | None:
    """Where the source declares a stale name that is a documented extra, given
    a surface built from an extraction whose `excluded.outsideScope` does not
    list the name: (the item's `defined_at`, 0), or, with no `defined_at`,
    (the one `declared_in` item whose file the skill cites on a line that
    names it, the number of files `declared_in` lists) when it lists several.
    None for anything else, which stays a Medium gap: no `defined_at` and no
    single cited declaring file (two or more cited, none, or no --skill-dir),
    a `defined_at` or `declared_in` item not a Python or TS/JS `file:line`, a
    dotted name, no surface or one without an extraction, or a name a brief
    scoped out."""
    if outside is None or name in outside or "." in name:
        return None
    defined_at = item.get("defined_at")
    if defined_at is not None:
        if not isinstance(defined_at, str) or not _DEFINED_AT_RE.match(defined_at):
            return None
        return defined_at, 0
    declared_in = item.get("declared_in")
    if not skill_dir or not isinstance(declared_in, list) or not all(
            isinstance(d, str) and _DEFINED_AT_RE.match(d) for d in declared_in):
        return None
    by_file = {_cited_path(d.rsplit(":", 1)[0]): d for d in declared_in}
    if len(by_file) < 2:
        return None
    cited = _skill_cited_files(Path(skill_dir), name)
    chosen = [d for f, d in sorted(by_file.items()) if f in cited]
    return (chosen[0], len(by_file)) if len(chosen) == 1 else None


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


def from_coverage(cov: object, surface: object = None, signatures: object = None, numerator: object = None,
                  stale: object = None, provenance: object = None, skill_dir: str | None = None,
                  metadata: str | None = None) -> list[dict]:
    """reconcile-coverage.py's result: missing and stale names, or the missing count."""
    cov = _object(cov, "--input (reconcile-coverage.py)", "branch")
    meta = metadata or _DEFAULT_METADATA
    branch = cov["branch"]
    records: list[dict] = []
    if branch == "enumerated":
        types: set[str] = set()
        # the names whose documented signature signature scoring compared
        scored: set[str] = set()
        if signatures is not None:
            signatures = _object(signatures, "--signatures (score-signatures.py)", "missingTypes")
            types = set(_names(signatures, "missingTypes", "--signatures"))
            scored = set(_names(signatures, "comparedNames", "--signatures"))
        if surface is not None:
            surface = _object(surface, "--surface (load-coverage-inputs.py surface)", "exports")
        where = _surface_sources(surface)
        # `excluded` is read once a stale name may be a documented extra
        outside: set[str] | None = None
        outside_read = False
        for name in _names(cov, "missing", "--input"):
            records.append(_missing_export(name, where.get(name), meta, "type" if name in types else "export"))
        classified: dict[str, dict] = {}
        if stale is not None:
            if not isinstance(stale, list):
                raise AdapterError("--stale is not classify-stale JSON (a list)")
            classified = {i["name"]: i for i in stale if isinstance(i, dict) and isinstance(i.get("name"), str)}
        for name in _names(cov, "stale", "--input"):
            item = classified.get(name) or {}
            cited = item.get("source")
            if item.get("fabricated") is True:
                if not isinstance(cited, str) or not cited:
                    # a Critical gap needs the line it cites: never downgrade it
                    raise AdapterError(f"--stale: {name!r} is fabricated with no source")
                records.append(_gap(
                    "Critical", "fabricated-signature", f"Fabricated signature: {name}", cited,
                    f"Remove `{name}` from SKILL.md and references/, or correct it to the export the source "
                    f"defines: no file its provenance cites defines it (`{cited}`).",
                    issue=f"SKILL.md documents `{name}`, which the source API surface lacks and the cited "
                          "file does not define",
                    export=name))
                continue
            if not outside_read:
                outside, outside_read = _outside_scope(surface), True
            extra = _documented_extra_at(name, item, outside, skill_dir)
            doc = _documenting_line(Path(skill_dir), name) if skill_dir else None
            if extra:
                declared, among = extra
                # a homonym: the one declaring file the skill's own citations name
                picked = (f"; of the {among} files that declare it, the skill cites only "
                          f"`{declared.rsplit(':', 1)[0]}`") if among else ""
                # never routed: update-skill leaves an `observation` alone. Signature scoring compares a
                # documented signature of a name on the surface's records (a nested sub-package's) alone.
                checked = ("Signature scoring compares its documented signature with the surface's record of it."
                           if name in scored else
                           "Its documented signature was not checked against that declaration.")
                records.append(_gap(
                    "Info", "observation", f"Documented extra: {name}", declared,
                    f"No change: `{name}` is a documented extra, a name the source still declares at "
                    f"`{declared}` outside the enumerated surface, and its documentation stays. {checked}",
                    issue=f"{f'`{doc}`' if doc else 'the skill'} documents `{name}`, which the enumerated source API "
                          f"surface lacks and the source still declares{picked}",
                    export=name))
                continue
            records.append(_gap(
                "Medium", "stale-documentation", f"Stale documentation: {name}", doc or "SKILL.md",
                f"Check `{name}` against the source and update or remove its documentation at "
                f"{doc or 'SKILL.md'}: the enumerated source surface does not export it.",
                issue=f"SKILL.md documents `{name}`, which the enumerated source API surface lacks",
                export=name))
    elif branch in ("scalar", "stack"):
        if branch == "scalar" and cov.get("numeratorSource") == "verified":
            if numerator is None:
                raise AdapterError("the scalar count used the verified numerator: pass its result with "
                                   "--numerator")
            absent = _names(_object(numerator, "--numerator (verify-declared-numerator.py)", "absent"),
                            "absent", "--numerator")
            where = _provenance_sources(_object(provenance, "--provenance (provenance map)", "entries")
                                        if provenance is not None else None)
            records += [_missing_export(name, where.get(name), meta) for name in absent]
        else:
            missing, denominator = _count(cov.get("missingCount")), _count(cov.get("denominator"))
            if missing:
                records.append(_gap(
                    "Medium", "missing-export", f"{missing} of {denominator} exports not documented", meta,
                    f"Find the {missing} exports the denominator counts that SKILL.md and references/ do not "
                    f"name (`{meta}` lists the exports) and document each with its signature.",
                    issue=f"SKILL.md and references/ name {cov.get('documented')} of the {denominator} exports "
                          f"the {branch} denominator counts"))
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
    deflation = guards.get("deflation") or {}
    if deflation.get("fires") is True:
        records.append(_gap(
            "Medium", "metadata-drift",
            "denominator deflation: effective_denominator below source public surface without tier_a_include",
            meta,
            f"Set `stats.effective_denominator` in `{meta}` to the public surface the source re-derives, or "
            "add `scope.tier_a_include` to the brief to name the authored tier the smaller count measures.",
            issue=f"the re-derived surface counts {deflation.get('rederived')} exports, "
                  f"{deflation.get('pct')}% above `stats.effective_denominator` "
                  f"({deflation.get('effectiveDenominator')}), and the brief has no `scope.tier_a_include`"))
    inflation = guards.get("inflation") or {}
    if inflation.get("fires") is True:
        if (guards.get("umbrella") or {}).get("umbrella") is True:
            fix = (f"Set `stats.effective_denominator` in `{meta}` to the authored surface: the root barrel "
                   "is an umbrella of re-exports, so a `scope.tier_a_include` glob would still count them.")
        else:
            fix = (f"Add `scope.tier_a_include` to `{brief}`, listing the files of the authored surface, so "
                   "the denominator counts it instead of the coarse `scope.include` union.")
        records.append(_gap(
            "Medium", "denominator-inflation",
            "denominator inflation: coarse scope.include union exceeds authored surface", brief, fix,
            issue=f"the `scope.include` union counts {inflation.get('scopeIncludeUnion')} exports, "
                  f"{inflation.get('pct')}% above the {inflation.get('provenanceEntries')} provenance entries, "
                  "and the brief has no `scope.tier_a_include`"))
    stale = guards.get("staleScope") or {}
    if stale.get("fires") is True:
        label = "--input (load-coverage-inputs.py surface): guards.staleScope"
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
        records.append(_gap(
            "Medium", "brief-scope-stale", "stale brief scope: scope.include globs match no source file", brief,
            f"Edit `scope.include` in `{brief}` by hand so each glob matches the files it meant in this version "
            "of the source (update-skill does not rewrite an include glob), and add to `scope.exclude` any "
            "restored file the brief meant to leave out.",
            issue=f"{unmatched}; {back}"))
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
        f"Document the absent exports in SKILL.md, or set `stats.exports_documented` in `{meta}` to the "
        f"{verified} exports the skill documents.",
        issue=f"`stats.exports_documented` equals the denominator, and these declared exports are absent "
              f"from SKILL.md and references/: {_code(absent)}")]


def from_metadata_coherence(result: object, metadata: str | None = None) -> list[dict]:
    """check-metadata-coherence.py's findings: count drift and multi-denominator notes."""
    result = _object(result, "--input (check-metadata-coherence.py)", "findings")
    meta = metadata or _DEFAULT_METADATA
    records: list[dict] = []
    for index, finding in enumerate(_list(result, "findings", "--input")):
        if not isinstance(finding, dict) or not isinstance(finding.get("title"), str):
            raise AdapterError(f"--input: findings[{index}] has no title")
        detail = finding.get("detail") if isinstance(finding.get("detail"), str) else None
        if finding.get("severity") == "Medium":
            records.append(_gap(
                "Medium", "metadata-drift", finding["title"], meta,
                f"Recount the exports and correct the diverging counts in `{meta}`; update-skill applies it as "
                "a metadata update.",
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


def from_provenance_line(result: object) -> list[dict]:
    """verify's `line-not-definition` items: provenance line gaps."""
    result = _object(result, "--input (skf-verify-provenance-completeness.py verify)", "stale")
    records: list[dict] = []
    for item in _list(result, "stale", "--input"):
        if not isinstance(item, dict) or item.get("reason") != "line-not-definition":
            continue
        name, file, line = item.get("export_name"), item.get("source_file"), item.get("source_line")
        defs = [n for n in item.get("definition_lines") or [] if _count(n) is not None]
        where = f"{file}:{line}"
        if defs:
            lines = ", ".join(str(n) for n in defs)
            records.append(_gap(
                "Low", "provenance-line", f"Provenance line is not the definition of {name}", where,
                f"Set the provenance `source_line` of `{name}` in `{file}` to its definition line ({lines}) "
                "and move its citations to that line; update-skill `--from-test-report` applies this when the "
                "file defines it on one line.",
                issue=f"the provenance map records `{name}` at `{where}`, which is not the line that defines "
                      f"it; the lines that define it are {lines}.",
                export=name))
        else:
            records.append(_gap(
                "Info", "provenance-unverified", f"Provenance line not verified for {name}", where,
                f"Open `{file}` and confirm that line {line} defines `{name}`; if another line does, set the "
                "provenance `source_line` to it.",
                issue=f"the line-check rules found no definition line for `{name}` in `{file}`; check by hand",
                export=name))
    return records


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
                 for o in ("surface", "signatures", "numerator", "stale", "provenance")}
        return from_coverage(data, skill_dir=args.skill_dir, metadata=args.metadata, **files)
    if kind == "guards":
        return from_guards(data, args.metadata)
    if kind == "numerator":
        return from_numerator(data, args.metadata)
    if kind == "metadata-coherence":
        return from_metadata_coherence(data, args.metadata)
    if kind == "provenance-line":
        return from_provenance_line(data)
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
        effort = EFFORT[severity] if counts[severity] else "None"
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
    p.add_argument("--stale", help="coverage: classify-stale's result (fabricated signatures, documented extras)")
    p.add_argument("--provenance", help="coverage: the provenance map (an absent name's Source)")
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
