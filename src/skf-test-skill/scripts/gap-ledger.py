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

  append --ledger <path> --stage <stage> [--input <file>]
      Read records from <file>, or from stdin without --input: a JSON array,
      one record object, or {"records": [...]}. An empty array records the
      stage with no findings. Every record is validated first and nothing is
      written unless all are valid. A record equal to one already in the
      ledger (same severity, category, title, source and export) is not
      added again, so a stage that runs twice leaves one copy. Creates the
      ledger when it does not exist.
      Appends may overlap (parallel tool calls): each holds an exclusive
      lock on <ledger>.skf-lock from its read to its write, and another
      append waits for it (up to 30 s, then LEDGER_LOCKED), so no record an
      append reported is lost. The write is atomic: a temp file of its own
      beside the ledger, then a rename. The lock file is removed afterwards.
      Output: {"status": "ok", "ledger", "stage", "appended": [ids],
               "duplicates": [ids], "record_count"}

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
    "stale-documentation": ("Coverage", "documentation for an export the source no longer has"),
    "missing-type": ("Coverage", "a type or interface the skill does not document"),
    "provenance-completeness": ("Coverage", "an export the skill documents that the provenance map lacks"),
    "provenance-line": ("Coverage", "a provenance line that is not the definition of its export"),
    "provenance-unverified": ("Coverage", "a provenance line the line-check rules could not verify"),
    "metadata-drift": ("Coverage", "export counts in the metadata that diverge from each other"),
    "denominator-inflation": ("Coverage", "a scope include union larger than the provenance map"),
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
    "observation": ("Structural", "a style suggestion or another non-blocking observation"),
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


def _cmd_append(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    if not _STAGE_RE.match(args.stage):
        _emit(_error("INVALID_INPUT", f"--stage must be a lowercase slug, got '{args.stage}'"))
        return 2
    try:
        text = Path(args.input).read_text(encoding="utf-8-sig") if args.input else sys.stdin.read()
        # A byte order mark on stdin (a Windows editor or shell) is not JSON.
        raw_records = parse_input(text.removeprefix("\ufeff"))
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

    p = sub.add_parser("append", help="append records from stdin or --input")
    p.add_argument("--ledger", required=True, help="{forge_version}/test-findings-{run_id}.json")
    p.add_argument("--stage", required=True, help="the stage appending, e.g. coverage-check")
    p.add_argument("--input", help="a JSON file with the records (default: stdin)")
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
