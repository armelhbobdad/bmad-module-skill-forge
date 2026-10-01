#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The forger's pipeline journal: a chain's state on disk, and its resume.

Pipeline Mode (references/pipeline-mode.md) keeps a chain's state in a
journal rather than only in the conversation, so a closed session, a killed
terminal or a compacted context loses nothing, and a later activation picks
the chain up at the step it stopped on, with the plan the first parse
produced: its alias, bracket values and arguments. Re-parsing only the codes
still pending dropped the alias (forge-auto's TS[min:90] fell back to the
default threshold) and warned about prerequisites the chain had already run.
Which step a chain stopped on, what a gate's decision records, what a halt
offers, and the pipeline result's name and shape each have one correct
answer, so they run here, not in the prompt.

The journal is `pipeline-journal.json` in the run's own folder,
`<run-root>/skf-forger-<run_id>/`, under the run root every SKF workflow
keeps its run state in (`{project-root}/_bmad-output/.skf-run`). `run_id` is
the UTC time the chain started and a random suffix, so the folder names sort
by start time. `src/shared/references/pipeline-contracts.md` (Pipeline State)
describes its fields. Each step entry keeps one shape, in the journal and in
the pipeline result alike:

  {"code": "TS", "min": 90, "mode": null, "target": null, "flags": [],
   "status": "pending" | "completed" | "skipped" | "halted", "reason": null}

Subcommands:

  start    Read the whole invocation on stdin, parse it with
           parse-pipeline.py (beside this script), and create the run folder
           and its journal: every step pending, the alias, the first
           workflow's args.
  step     Record the step the chain just finished: the first pending step,
           whose code must be --code. After AN, TS, AS or VS, --gate reads
           the JSON pipeline-gate.py printed on stdin: `continue` records
           the step `completed`, `skip` also records the next step, the one
           the gate passes over, `skipped`, and `halt` records the step
           `halted` with the gate's reason (the journal is then `halted`).
           Any other workflow, or a gate that printed no JSON, takes
           --status `completed`, or `halted` with --reason. --set records a
           value the step hands the next, by its Data Flow name (a name
           given twice in one call holds a list): a completed CS, QS or US
           must hand on `skill_name`, a completed AN or BS `brief_path`.
           --output records a result or report path the step's envelope
           names.
  finish   Write the pipeline result from the journal to --result-dir:
           `pipeline-result-<YYYYMMDD-HHmmss>.json` (UTC; -2, -3 ... when a
           run already took that second's name), then its copy
           `pipeline-result-latest.json`, and print the next action the
           stop leaves (below). The run folder is deleted when nothing is
           left to resume (every step completed or skipped, or a halt no
           resume fixes) and kept otherwise. A --halt-reason with no halted
           step halts the first pending one. A journal that cannot be saved
           or read still gets its result, with a warning, unless its run
           already has one. Without --journal it records a chain that
           stopped before its journal started (at its parse, or a `start`
           that failed): --halt-reason and no step.
  resume   The offer a new activation makes, from the newest journal under
           --run-root. No offer when no journal is left, when a later chain
           recorded a result with a step in it (any record in --result-dir,
           the per-run ones included), when the journal's skill was tested
           (--forge-data-folder) or exported (--skills-output-folder) after
           the journal's last write, or when its halt has nothing to resume.
  reopen   Apply the offer the user accepted: the halted step is pending
           again (after AS CRITICAL the audit counts as done), a repair that
           is a workflow of its own joins the plan right before the step it
           repairs, and the first step to run takes the journal's skill as
           its target when it takes a skill and names none. The journal runs
           again. Prints the steps still to run.
  discard  Delete a stopped chain's run folder, so its offer is made no more.

Next action. A chain interrupted mid-step (its journal still `running`),
or halted by anything but a quality verdict, gets the offer `resume` at the
step it stopped on. A quality halt gets a `repair` (REPAIRS below), which
the user makes first unless it is a workflow of its own (USER_ACTIONS):

  halted on  reason                        repair                   picks up at
  TS         FAIL                          update-from-test-report  TS, after
                                           (US <skill> --from-test-report)
  TS         INCONCLUSIVE                  add-evidence             TS
  TS         pass-with-drift,
             workspace-drift               retest-at-pinned-commit  TS
  AS         CRITICAL                      review-drift-report      the step
                                                                    after AS
  VS         zero-coverage                 create-missing-skills    VS
  AN         no-skillable-units,
             units-below-min, skipped      new-target               no resume
  AN         redirect                      update-existing-skill    no resume

`finish` and `resume` print it in one shape: `offer` (`resume`, `repair`,
or null when nothing is left to resume), `kind` (`interrupted`, `error` or
`quality`), `repair`, `user_action` (what the user does first, or null),
`route` (the next action in one line, such as `US hono --from-test-report,
then TS EX at the recorded threshold of 90`), `halted_on`, `resume_at` and
`threshold` (the TS `min` the rest of the plan carries). Every value is
null for a chain that nothing stopped.

The journal's skill is the handoff `skill_name`, else the alias argument of
that name (`forge`, `maintain`), else the bracket name of a TS, EX, US or AS
step. It counts as tested after the journal when one of its
`skf-test-skill-result-latest.json` records (flat, or in a version folder)
started later than the journal's `updated_at`: the UTC time that leads its
`runId`, which the run took from the clock, or its `timestamp` when it has
no run id. It counts as exported after it when its export manifest entry
records a later `last_exported` day, or that same day with the manifest's
`updated_at` later (the chain's own EX excepted). The manifest dates an
export by its day only, and any skill's export moves its `updated_at`, so
a same-day export of another skill after the journal counts too.

Shared formats. The run id is skf-run-lock.py's (`new_run_id`), and the
per-run record's name with its -2, -3 suffix is the shared emitter's
(skf-emit-result-envelope.py `_claim_result_path`). This script ships with
the forger and loads no shared script, so it keeps its own copy of both;
test/test-skf-pipeline-journal.py checks that they name the same files for
the same clock.

CLI usage (from the skf-forger skill root):
  uv run scripts/pipeline-journal.py start --run-root <dir> <<'SKF_PIPELINE'
  forge-auto https://github.com/honojs/hono --pin v4.6.0
  SKF_PIPELINE
  uv run scripts/pipeline-journal.py step --journal <file> --code CS \\
      --status completed --set skill_name=hono
  uv run scripts/pipeline-journal.py step --journal <file> --code TS --gate <<'SKF_GATE'
  {"code": "TS", "decision": "halt", "reason": "FAIL", "skip": null, "message": "..."}
  SKF_GATE
  uv run scripts/pipeline-journal.py finish --journal <file> --result-dir <dir> \\
      [--halt-reason <reason>]
  uv run scripts/pipeline-journal.py finish --result-dir <dir> --halt-reason <reason>
  uv run scripts/pipeline-journal.py resume --run-root <dir> --result-dir <dir> \\
      [--forge-data-folder <dir>] [--skills-output-folder <dir>]
  uv run scripts/pipeline-journal.py reopen --journal <file>
  uv run scripts/pipeline-journal.py discard --journal <file>

Output (stdout): one JSON object. `status` is `ok` (start, step, finish,
reopen, discard), `offer` or `none` (resume), or `error`, with `error`
naming the problem, `message` saying it in one line, and `retry` true when
the call itself lacked what the message names (a handoff value, a reason,
the gate's decision): the same call with it goes through.

Exit codes:
  0  done: read `status`
  1  error: the journal or a folder cannot be read or written, the
     invocation does not parse to a runnable plan, a step out of order or
     without the value it hands on, a gate decision that does not fit the
     step, a halt with no reason, nothing to resume
  2  usage error (argparse: usage on stderr, no JSON)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PARSER = Path(__file__).resolve().parent / "parse-pipeline.py"

JOURNAL = "pipeline-journal.json"
RUN_PREFIX = "skf-forger-"
RESULT_STEM = "pipeline-result"
TEST_RESULT = "skf-test-skill-result-latest.json"
EXPORT_MANIFEST = ".export-manifest.json"
JOURNAL_VERSION = 1

STEP_STATUSES = ("pending", "completed", "skipped", "halted")
STATUS_CHOICES = ("completed", "halted")  # what `step --status` records; a skip comes from a gate
DECISIONS = ("continue", "skip", "halt")  # pipeline-gate.py's `decision`

RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
FILE_STAMP_FORMAT = "%Y%m%d-%H%M%S"
_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
_RUN_TIME_RE = re.compile(r"^(\d{8}T\d{6}Z)")
_FILE_STAMP_RE = re.compile(r"^\d{8}-\d{6}$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# The codes pipeline-gate.py decides for: their step records the gate's
# decision (--gate), not a status given by hand.
GATED = frozenset({"AN", "TS", "AS", "VS"})
# The value a completed step hands the next workflow, by its Data Flow name
# in pipeline-contracts.md. A resumed chain passes it on, and the offer's
# later-test and later-export checks look the skill up by it.
HANDOFFS = {"AN": "brief_path", "BS": "brief_path", "CS": "skill_name", "QS": "skill_name", "US": "skill_name"}

# A quality halt, keyed by the halted code and its reason (lower case, `-`
# for `_`): the repair the offer names, and where the chain picks up again
# ("same" re-runs the halted step, "next" the one after it, None: no resume).
# Mirrors the Repair Routes table in pipeline-contracts.md. Any other halt is
# an error the user fixes, and the chain re-runs the step that halted.
REPAIRS = {
    ("TS", "fail"): ("update-from-test-report", "same"),
    ("TS", "inconclusive"): ("add-evidence", "same"),
    ("TS", "pass-with-drift"): ("retest-at-pinned-commit", "same"),
    ("TS", "workspace-drift"): ("retest-at-pinned-commit", "same"),
    ("AS", "critical"): ("review-drift-report", "next"),
    ("VS", "zero-coverage"): ("create-missing-skills", "same"),
    ("AN", "no-skillable-units"): ("new-target", None),
    ("AN", "units-below-min"): ("new-target", None),
    ("AN", "skipped"): ("new-target", None),
    ("AN", "redirect"): ("update-existing-skill", None),
}
# A repair that is a workflow of its own: it joins the plan right before the
# step it repairs, with the journal's skill as its target.
REPAIR_STEPS = {"update-from-test-report": ("US", ("--from-test-report",))}
# What the user does before a repair picks the chain up again, or instead of
# a resume when there is none (None: the chain runs the repair itself). The
# Repair Routes table in pipeline-contracts.md shows the same texts.
USER_ACTIONS = {
    "update-from-test-report": None,
    "add-evidence": "add evidence: install skill-check, or move up a tier (the tier's tools, then SF)",
    "retest-at-pinned-commit": "put the source back at the commit the skill pins",
    "review-drift-report": "review the drift report",
    "create-missing-skills": "create skills for the architecture's technologies (for example forge-quick <package>)",
    "new-target": "start a new chain with another target, or with a scope hint",
    "update-existing-skill": "run US on the skill the target already has",
}
# The codes whose bracket target is a skill name (CS's names a brief, QS's a
# package or URL).
SKILL_TARGET_CODES = frozenset({"TS", "EX", "US", "AS"})
# The keys of the next action `finish` and `resume` print.
NEXT_ACTION_KEYS = ("offer", "kind", "repair", "user_action", "route", "halted_on", "resume_at", "threshold")
# The errors a call causes by lacking something its message names: the same
# call with it goes through, so a chain need not stop on them.
RETRYABLE = frozenset({"bad-value", "gate-unreadable", "gate-mismatch", "gate-required", "reason-missing",
                       "handoff-missing", "unfinished"})


class JournalError(Exception):
    """A request the journal cannot serve: printed as a `status: error` object."""

    def __init__(self, error: str, message: str):
        super().__init__(message)
        self.error = error
        self.message = message


# --------------------------------------------------------------------------
# Time, run ids and files
# --------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(t: datetime) -> str:
    return t.strftime(TIME_FORMAT)


def new_run_id(now: datetime | None = None) -> str:
    """A run id: the UTC time and 8 random hex characters (skf-run-lock.py's format)."""
    return f"{(now or _now()).strftime(RUN_ID_FORMAT)}-{secrets.token_hex(4)}"


def _file_stamp(run_id: str) -> str:
    """A run id's start time as a result file stamp (YYYYMMDD-HHmmss), or "" for another shape."""
    return f"{run_id[:8]}-{run_id[9:15]}" if _RUN_ID_RE.match(run_id) else ""


def parse_time(value) -> datetime | None:
    """A UTC time from an ISO-8601 time or a run id's leading stamp, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    m = _RUN_TIME_RE.match(text)
    try:
        if m:
            return datetime.strptime(m.group(1), RUN_ID_FORMAT).replace(tzinfo=timezone.utc)
        t = datetime.fromisoformat(text)
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _read_json(path: Path):
    """The JSON value in `path`, or None when it is missing or not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _write_json(path: Path, value) -> None:
    """Write `value` as indented JSON through a temporary file and one rename.

    newline="\\n" keeps LF endings on Windows too.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}-{secrets.token_hex(2)}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _save(path: Path, journal: dict) -> None:
    try:
        _write_json(path, journal)
    except OSError as e:
        raise JournalError("write-failed", f"The journal {path} cannot be written: {e.strerror or e}") from None


def _is_journal(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("run_id"), str)
        and isinstance(value.get("data"), dict)
        and isinstance(value.get("steps"), list)
        and all(
            isinstance(s, dict) and isinstance(s.get("code"), str) and s.get("status") in STEP_STATUSES
            for s in value["steps"]
        )
    )


def load_journal(path: Path) -> dict:
    journal = _read_json(path)
    if not _is_journal(journal):
        raise JournalError("journal-unreadable", f"{path} is missing, not JSON, or not a pipeline journal.")
    for key, empty in (("args", {}), ("outputs", []), ("history", [])):
        if not isinstance(journal.get(key), type(empty)):
            journal[key] = empty
    return journal


def _folder_run_id(path: Path) -> str | None:
    """The run id the name of the journal's folder carries, or None for any other file or folder."""
    name = path.parent.name
    run_id = name[len(RUN_PREFIX):] if name.startswith(RUN_PREFIX) else ""
    return run_id if path.name == JOURNAL and _RUN_ID_RE.match(run_id) else None


def _delete_run_folder(path: Path, run_id: str) -> str | None:
    """Delete the run folder of the journal at `path`; a warning when it is not deleted.

    Only the journal's own folder, `skf-forger-<run_id>/`, is ever deleted:
    a journal given from anywhere else leaves its folder in place.
    """
    folder = path.parent
    if path.name != JOURNAL or folder.name != f"{RUN_PREFIX}{run_id}":
        return f"run_dir_not_deleted: {folder.as_posix()}: not the journal's run folder"
    try:
        shutil.rmtree(folder)
    except FileNotFoundError:
        pass
    except OSError as e:
        return f"run_dir_not_deleted: {folder.as_posix()}: {e.strerror or e}"
    return None


# --------------------------------------------------------------------------
# Steps and offers
# --------------------------------------------------------------------------


def _step_entry(code: str, min_n=None, mode=None, target=None, flags=()) -> dict:
    return {"code": code, "min": min_n, "mode": mode, "target": target,
            "flags": list(flags), "status": "pending", "reason": None}


def _first(steps: list, status: str) -> int | None:
    return next((i for i, s in enumerate(steps) if s["status"] == status), None)


def _indexed(steps: list, index: int) -> dict:
    return {"index": index, **steps[index]}


def _reason_key(reason) -> str:
    return str(reason or "").strip().lower().replace("_", "-")


def _repair_rule(step: dict) -> tuple[str, str | None] | None:
    return REPAIRS.get((step["code"].upper(), _reason_key(step.get("reason"))))


def offer_for(journal: dict) -> dict | None:
    """What a stopped chain offers, from its journal alone; None: nothing to resume.

    {"offer": "resume" | "repair", "kind": "interrupted" | "error" | "quality",
     "repair": <REPAIRS key> | None, "halted_on": <index>, "resume_at": <index>}
    """
    steps = journal["steps"]
    halted = _first(steps, "halted")
    if halted is None:
        pending = _first(steps, "pending")
        if pending is None:
            return None
        return {"offer": "resume", "kind": "interrupted", "repair": None, "halted_on": pending, "resume_at": pending}
    rule = _repair_rule(steps[halted])
    if rule is None:
        return {"offer": "resume", "kind": "error", "repair": None, "halted_on": halted, "resume_at": halted}
    repair, pickup = rule
    if pickup is None:
        return None
    resume_at = halted + 1 if pickup == "next" else halted
    if resume_at >= len(steps):
        return None
    return {"offer": "repair", "kind": "quality", "repair": repair, "halted_on": halted, "resume_at": resume_at}


def pipeline_status(steps: list) -> str:
    """success: nothing halted; partial: a halt after a completed step; failed: before any."""
    if _first(steps, "halted") is None:
        return "success"
    return "partial" if _first(steps, "completed") is not None else "failed"


def _skill_name(journal: dict) -> str | None:
    """The skill the chain works on, or None while no step has named it."""
    candidates = [journal["data"].get("skill_name"), journal["args"].get("skill_name")]
    candidates += [s.get("target") for s in journal["steps"] if s["code"] in SKILL_TARGET_CODES]
    for value in candidates:
        if isinstance(value, list):
            value = next((v for v in value if isinstance(v, str) and v.strip()), None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _threshold(steps: list, start: int) -> int | None:
    """The TS `min` the rest of the plan carries: the recorded threshold."""
    return next((s["min"] for s in steps[start:] if s["code"] == "TS" and s["min"] is not None), None)


def _halted_on(steps: list, index: int) -> dict:
    return {"index": index, "code": steps[index]["code"], "reason": steps[index]["reason"]}


def next_action(journal: dict) -> dict:
    """The next action a stopped chain leaves, in NEXT_ACTION_KEYS; every value None when nothing stopped it."""
    steps = journal["steps"]
    action = dict.fromkeys(NEXT_ACTION_KEYS)
    offer = offer_for(journal)
    if offer is None:
        halted = _first(steps, "halted")
        rule = None if halted is None else _repair_rule(steps[halted])
        if rule is None:
            return action
        user = USER_ACTIONS.get(rule[0])
        action.update(kind="quality", repair=rule[0], user_action=user,
                      route=f"no resume: {user}" if user else "no resume", halted_on=_halted_on(steps, halted))
        return action
    at, repair = offer["resume_at"], offer["repair"]
    user = USER_ACTIONS.get(repair) if repair else None
    run = " ".join(s["code"] for s in steps[at:])
    if repair in REPAIR_STEPS:
        code, flags = REPAIR_STEPS[repair]
        route = f"{' '.join([code, _skill_name(journal) or '<skill>', *flags])}, then {run}"
    elif user:
        route = f"{user}, then {run}"
    else:
        route = f"resume at {steps[at]['code']}: {run}"
    threshold = _threshold(steps, at)
    if threshold is not None:
        route += f" at the recorded threshold of {threshold}"
    action.update(offer=offer["offer"], kind=offer["kind"], repair=repair, user_action=user, route=route,
                  halted_on=_halted_on(steps, offer["halted_on"]),
                  resume_at={"index": at, "code": steps[at]["code"]}, threshold=threshold)
    return action


# --------------------------------------------------------------------------
# Did the user move on? (resume)
# --------------------------------------------------------------------------


def _record_time(path: Path) -> datetime | None:
    """When a test run started: its clock-stamped run id, else its `timestamp`."""
    record = _read_json(path)
    if not isinstance(record, dict):
        return None
    return parse_time(record.get("runId")) or parse_time(record.get("run_id")) or parse_time(record.get("timestamp"))


def tested_after(forge_data_folder: Path, skill: str, since: datetime) -> bool:
    """A test result record of `skill`, flat or in a version folder, later than `since`."""
    base = forge_data_folder / skill
    try:
        records = [base / TEST_RESULT, *sorted(base.glob(f"*/{TEST_RESULT}"))]
    except OSError:
        return False
    return any(path.is_file() and (when := _record_time(path)) is not None and when > since for path in records)


def exported_after(skills_output_folder: Path, skill: str, since: datetime) -> bool:
    """An export of `skill` later than `since`: a later day, or that day with a later manifest write.

    `last_exported` holds a day only; the manifest's `updated_at` tells the
    time of its last write, whichever skill it was for, so a same-day export
    of another skill after `since` counts too.
    """
    manifest = _read_json(skills_output_folder / EXPORT_MANIFEST)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("exports"), dict):
        return False
    entry = manifest["exports"].get(skill)
    if not isinstance(entry, dict):
        return False
    versions = entry.get("versions")
    if isinstance(versions, dict):
        days = [r.get("last_exported") for r in versions.values() if isinstance(r, dict)]
    else:  # a v1 entry lists its versions; the manifest's own time dates them
        days = [manifest.get("updated_at")] if isinstance(versions, list) else []
    written = parse_time(manifest.get("updated_at"))
    since_day = since.date().isoformat()
    for day in days:
        if not isinstance(day, str) or len(day) < 10:
            continue
        day = day[:10]
        if day > since_day or (day == since_day and written is not None and written > since):
            return True
    return False


def _records(result_dir: Path, since: str = ""):
    """Each pipeline result record in `result_dir` as (path, record), newest first.

    The -latest copy comes first. A per-run record whose file stamp is
    older than `since` (a file stamp) is passed over without being read.
    """
    try:
        paths = sorted(result_dir.glob(f"{RESULT_STEM}-*.json"), key=lambda p: p.name, reverse=True)
    except OSError:
        return
    for path in paths:
        stamp = path.name[len(RESULT_STEM) + 1:][:15]
        if since and _FILE_STAMP_RE.match(stamp) and stamp < since:
            continue
        record = _read_json(path)
        if isinstance(record, dict):
            yield path, record


def _later_result(result_dir: Path, run_id: str) -> str | None:
    """The run id of a later chain's pipeline result that recorded a step, else None.

    A record with no step, such as a parse halt's, supersedes no journal,
    but its copy replaces `pipeline-result-latest.json`: the per-run records
    are read too. One named before the journal's chain started is older.
    """
    for _, record in _records(result_dir, _file_stamp(run_id)):
        later = record.get("run_id")
        summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
        steps = summary.get("steps")
        if isinstance(later, str) and _RUN_ID_RE.match(later) and later > run_id and isinstance(steps, list) and steps:
            return later
    return None


def _recorded(result_dir: Path, run_id: str) -> dict | None:
    """The pipeline result already written for `run_id`, else None."""
    return next((record for _, record in _records(result_dir, _file_stamp(run_id))
                 if record.get("run_id") == run_id), None)


def _newest_journal(run_root: Path, warnings: list) -> tuple[Path, dict] | None:
    """The newest readable journal under `run_root`; an unreadable one is named in `warnings`."""
    try:
        folders = sorted((p for p in run_root.glob(f"{RUN_PREFIX}*") if p.is_dir()), key=lambda p: p.name, reverse=True)
    except OSError:
        return None
    for folder in folders:
        path = folder / JOURNAL
        try:
            return path, load_journal(path)
        except JournalError:
            warnings.append(f"journal_unreadable: {path.as_posix()}")
    return None


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------


def _load_parser():
    """Load parse-pipeline.py, which ships in this script's folder."""
    try:
        spec = importlib.util.spec_from_file_location("skf_parse_pipeline", PARSER)
        if spec is None or spec.loader is None:
            raise ImportError("no import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError) as e:
        raise JournalError("parser-missing", f"parse-pipeline.py cannot be loaded from {PARSER.parent}: {e}") from None
    return module


def _read_stdin() -> str:
    # A Windows console reads cp1252: the arrows, paths and gate messages need UTF-8.
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    return sys.stdin.read()


def cmd_start(args) -> dict:
    raw = _read_stdin().strip()
    if not raw:
        raise JournalError("no-invocation", "No invocation on stdin: pass the whole pipeline invocation.")
    parsed = _load_parser().parse_pipeline(raw)
    if parsed["removed_alias"] or not parsed["valid"]:
        raise JournalError("not-runnable", "The invocation does not parse to a runnable plan: "
                                           "step 1 halts on it before any journal starts.")
    now = _now()
    run_id = new_run_id(now)
    run_dir = Path(args.run_root) / f"{RUN_PREFIX}{run_id}"
    try:
        run_dir.mkdir(parents=True)
    except OSError as e:
        raise JournalError("write-failed", f"The run folder {run_dir} cannot be created: {e.strerror or e}") from None
    journal = {
        "journal_version": JOURNAL_VERSION,
        "run_id": run_id,
        "status": "running",
        "started_at": _stamp(now),
        "updated_at": _stamp(now),
        "invocation": raw,
        "alias": parsed["alias"],
        "args": parsed["args"],
        "steps": [_step_entry(p["code"], p["min"], p["mode"], p["target"]) for p in parsed["plan"]],
        "data": {},
        "outputs": [],
        "history": [],
    }
    path = run_dir / JOURNAL
    _save(path, journal)
    return {"status": "ok", "run_id": run_id, "run_dir": str(run_dir), "journal": str(path),
            "alias": journal["alias"], "args": journal["args"], "steps": journal["steps"]}


def _set_values(pairs: list[str]) -> dict:
    """`name=value` pairs; a name given twice holds a list, in order."""
    values: dict = {}
    for pair in pairs:
        name, eq, value = pair.partition("=")
        name, value = name.strip(), value.strip()
        if not eq or not _NAME_RE.match(name) or not value:
            raise JournalError("bad-value", f"--set takes <name>=<value> with a lower-case name: {pair!r}")
        if name in values:
            held = values[name]
            values[name] = [*held, value] if isinstance(held, list) else [held, value]
        else:
            values[name] = value
    return values


def _gate_decision(text: str, code: str) -> dict:
    """The decision pipeline-gate.py printed for `code`, read from `text`."""
    text = text.strip()
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        try:
            value = json.loads(text[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            value = None
    if not isinstance(value, dict) or value.get("decision") not in DECISIONS:
        raise JournalError("gate-unreadable", "--gate reads the JSON object pipeline-gate.py printed, with its "
                                              "`decision`, on stdin.")
    if str(value.get("code") or "").strip().upper() != code:
        raise JournalError("gate-mismatch", f"The gate decided for {value.get('code')!r}, not {code}.")
    named = {"continue": (), "skip": ("reason", "skip"), "halt": ("reason",)}[value["decision"]]
    for key in named:
        if not (isinstance(value.get(key), str) and value[key].strip()):
            raise JournalError("gate-unreadable", f"The gate's {value['decision']} decision names no `{key}`.")
    return value


def cmd_step(args) -> dict:
    path = Path(args.journal)
    journal = load_journal(path)
    if journal.get("status") != "running":
        raise JournalError("not-running", f"The journal is {journal.get('status')}, not running: reopen it before "
                                          "recording a step.")
    steps = journal["steps"]
    index = _first(steps, "pending")
    if index is None:
        raise JournalError("no-step-pending", "Every step of the journal is already recorded.")
    if steps[index]["code"] != args.code:
        raise JournalError("out-of-order", f"The next step in the journal is {steps[index]['code']} "
                                           f"(step {index + 1}), not {args.code}.")
    skipped = skip_reason = None
    if args.gate:
        decision = _gate_decision(_read_stdin(), args.code)
        status = "halted" if decision["decision"] == "halt" else "completed"
        reason = decision["reason"].strip() if status == "halted" else None
        if decision["decision"] == "skip":
            skipped, skip_reason = index + 1, decision["reason"].strip()
            following = steps[skipped]["code"] if skipped < len(steps) else None
            if following != decision["skip"].strip().upper():
                raise JournalError("skip-mismatch", f"The gate passes over {decision['skip']}, but the step after "
                                                    f"{args.code} is {following or 'none'}.")
    else:
        status = args.status
        reason = ((args.reason or "").strip() or None) if status == "halted" else None
        if status == "completed" and args.code in GATED:
            raise JournalError("gate-required", f"{args.code} has a gate: record its decision with --gate and the "
                                                "JSON pipeline-gate.py printed on stdin.")
        if status == "halted" and reason is None:
            raise JournalError("reason-missing", "A halted step needs --reason: the workflow's halt reason.")
    values = _set_values(args.set or [])
    need = HANDOFFS.get(args.code)
    if status == "completed" and need and need not in values:
        raise JournalError("handoff-missing", f"A completed {args.code} hands `{need}` to the next workflow: "
                                              f"pass --set \"{need}=<value>\".")
    steps[index].update(status=status, reason=reason)
    if skipped is not None:
        steps[skipped].update(status="skipped", reason=skip_reason)
    journal["data"].update(values)
    journal["outputs"].extend({"code": args.code, "path": p} for p in args.output or [])
    if status == "halted":
        journal["status"] = "halted"
    journal["updated_at"] = _stamp(_now())
    _save(path, journal)
    following = None if status == "halted" else _first(steps, "pending")
    return {"status": "ok", "journal": str(path), "recorded": _indexed(steps, index),
            "skipped": None if skipped is None else _indexed(steps, skipped),
            "next": None if following is None else _indexed(steps, following), "data": journal["data"]}


def _claim_result_path(result_dir: Path, stamp: str) -> Path:
    """Create the per-run record, empty, under a name no run holds yet (-2, -3 ... on a clash)."""
    for n in range(1, 1000):
        path = result_dir / (f"{RESULT_STEM}-{stamp}.json" if n == 1 else f"{RESULT_STEM}-{stamp}-{n}.json")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return path
    raise OSError(f"no free file name for {RESULT_STEM}-{stamp}.json")


def _write_result(result_dir: Path, record: dict, now: datetime) -> tuple[Path, Path]:
    try:
        result_dir.mkdir(parents=True, exist_ok=True)
        per_run = _claim_result_path(result_dir, now.strftime(FILE_STAMP_FORMAT))
        _write_json(per_run, record)
        latest = result_dir / f"{RESULT_STEM}-latest.json"
        _write_json(latest, record)
    except OSError as e:
        raise JournalError("write-failed", f"The pipeline result cannot be written to {result_dir}: "
                                           f"{e.strerror or e}") from None
    return per_run, latest


def result_record(*, run_id: str, now: datetime, alias, steps: list, outputs: list,
                  halt: str | None = None, warnings=()) -> dict:
    """The pipeline result in output-contract-schema.md's shape, with the steps in `summary`.

    `halt` is the reason of a chain recorded with no step: one that stopped
    before its journal started, or whose journal is lost. Its status is
    `failed`. `warnings` are what `finish` could not do.
    """
    halted = _first(steps, "halted")
    if halt is not None:
        status, halt_reason = "failed", halt
    else:
        status, halt_reason = pipeline_status(steps), None if halted is None else steps[halted]["reason"]
    return {
        "skill": "skf-forger",
        "status": status,
        "timestamp": _stamp(now),
        "run_id": run_id,
        "outputs": [{"type": "report", "path": o["path"]} for o in outputs if isinstance(o, dict) and o.get("path")],
        "summary": {
            "status": status,
            "halt_reason": halt_reason,
            "alias": alias,
            "steps": [dict(s) for s in steps],
        },
        "headless_decisions": [],
        "warnings": list(warnings),
    }


def _finished(record: dict, per_run: Path, latest: Path, kept: bool, action: dict, warnings: list) -> dict:
    result = {"status": "ok", "pipeline_status": record["status"], "halt_reason": record["summary"]["halt_reason"],
              "result_path": str(per_run), "latest_path": str(latest), "run_dir_kept": kept, **action}
    if warnings:
        result["warnings"] = warnings
    return result


def _finish_with_no_step(result_dir: Path, run_id: str, now: datetime, reason: str, warnings: list,
                         kept: bool = False) -> dict:
    record = result_record(run_id=run_id, now=now, alias=None, steps=[], outputs=[], halt=reason, warnings=warnings)
    per_run, latest = _write_result(result_dir, record, now)
    return _finished(record, per_run, latest, kept, dict.fromkeys(NEXT_ACTION_KEYS), warnings)


def cmd_finish(args) -> dict:
    now = _now()
    result_dir = Path(args.result_dir)
    halt_reason = (args.halt_reason or "").strip() or None
    if args.journal is None:
        if halt_reason is None:
            raise JournalError("reason-missing", "Without --journal, finish records a chain that stopped before its "
                                                 "journal started: pass --halt-reason.")
        return _finish_with_no_step(result_dir, new_run_id(now), now, halt_reason, [])
    path = Path(args.journal)
    try:
        journal = load_journal(path)
    except JournalError:
        # The chain's state is lost, but its stop is still recorded: the
        # latest result must never stay the previous run's.
        run_id = _folder_run_id(path)
        if run_id is not None and _recorded(result_dir, run_id) is not None:
            raise JournalError("already-finished", f"The pipeline result of run {run_id} is already written.") from None
        lost = [f"journal_unreadable: {path.as_posix()}"]
        kept = run_id is not None and path.parent.is_dir()
        return _finish_with_no_step(result_dir, run_id or new_run_id(now), now, halt_reason or "journal-unreadable",
                                    lost, kept)
    warnings: list = []
    steps = journal["steps"]
    if _first(steps, "halted") is None and (pending := _first(steps, "pending")) is not None:
        if halt_reason is None:
            raise JournalError("unfinished", f"Step {pending + 1} ({steps[pending]['code']}) is still pending and no "
                                             "step halted: record the step that stopped, or pass --halt-reason.")
        steps[pending].update(status="halted", reason=halt_reason)
        journal["status"] = "halted"
        journal["updated_at"] = _stamp(now)
        try:
            _save(path, journal)
        except JournalError as e:
            warnings.append(f"journal_not_saved: {e.message}")
    action = next_action(journal)
    record = result_record(run_id=journal["run_id"], now=now, alias=journal.get("alias"),
                           steps=steps, outputs=journal["outputs"], warnings=warnings)
    per_run, latest = _write_result(result_dir, record, now)
    kept = action["offer"] is not None
    if not kept:
        problem = _delete_run_folder(path, journal["run_id"])
        if problem:
            kept = True
            warnings.append(problem)
            record["warnings"] = list(warnings)
            try:
                _write_json(per_run, record)
                _write_json(latest, record)
            except OSError:
                pass  # the record stands without it; the output below still names the warning
    return _finished(record, per_run, latest, kept, action, warnings)


def _no_offer(why: str, message: str, warnings: list, journal: Path | None = None) -> dict:
    result = {"status": "none", "why": why, "message": message, "journal": None if journal is None else str(journal)}
    if warnings:
        result["warnings"] = warnings
    return result


def cmd_resume(args) -> dict:
    warnings: list = []
    found = _newest_journal(Path(args.run_root), warnings)
    if found is None:
        return _no_offer("no-journal", "No stopped pipeline left a journal.", warnings)
    path, journal = found
    later = _later_result(Path(args.result_dir), journal["run_id"])
    if later:
        return _no_offer("later-pipeline", f"A later pipeline ({later}) recorded its result.", warnings, path)
    action = next_action(journal)
    if action["offer"] is None:
        return _no_offer("nothing-to-resume", "The journal's chain has nothing left to resume.", warnings, path)
    skill = _skill_name(journal)
    since = parse_time(journal.get("updated_at"))
    if skill and since:
        ran_ex = any(s["code"] == "EX" and s["status"] == "completed" for s in journal["steps"])
        if args.forge_data_folder and tested_after(Path(args.forge_data_folder), skill, since):
            return _no_offer("tested-after", f"{skill} was tested after the journal's last write.", warnings, path)
        if args.skills_output_folder and not ran_ex and exported_after(Path(args.skills_output_folder), skill, since):
            return _no_offer("exported-after", f"{skill} was exported after the journal's last write.", warnings, path)
    steps = journal["steps"]
    at = action["resume_at"]["index"]
    result = {
        "status": "offer",
        **action,
        "run_id": journal["run_id"],
        "journal": str(path),
        "invocation": journal.get("invocation"),
        "alias": journal.get("alias"),
        "skill_name": skill,
        "remaining": [_indexed(steps, i) for i in range(at, len(steps))],
        "args": journal["args"],
        "data": journal["data"],
    }
    if warnings:
        result["warnings"] = warnings
    return result


def cmd_reopen(args) -> dict:
    path = Path(args.journal)
    journal = load_journal(path)
    offer = offer_for(journal)
    if offer is None:
        raise JournalError("nothing-to-resume", "The journal's chain has nothing left to resume.")
    steps = journal["steps"]
    now = _stamp(_now())
    halted, at = offer["halted_on"], offer["resume_at"]
    if offer["kind"] != "interrupted":
        step = steps[halted]
        journal["history"].append({"code": step["code"], "reason": step["reason"], "repair": offer["repair"], "at": now})
        if at == halted:
            step.update(status="pending", reason=None)
        else:
            step["status"] = "completed"  # AS CRITICAL: the review stands in for the audit's go-ahead
    skill = _skill_name(journal)
    if offer["repair"] in REPAIR_STEPS:
        code, flags = REPAIR_STEPS[offer["repair"]]
        steps.insert(at, _step_entry(code, target=skill, flags=flags))
    first = steps[at]
    if first["code"] in SKILL_TARGET_CODES and first["target"] is None and skill:
        first["target"] = skill  # no step before it hands the skill on in this run
    journal["status"] = "running"
    journal["updated_at"] = now
    _save(path, journal)
    return {"status": "ok", "journal": str(path), "offer": offer["offer"], "repair": offer["repair"],
            "alias": journal.get("alias"), "skill_name": skill,
            "run": [_indexed(steps, i) for i in range(at, len(steps)) if steps[i]["status"] == "pending"],
            "args": journal["args"], "data": journal["data"]}


def cmd_discard(args) -> dict:
    path = Path(args.journal)
    try:
        run_id = load_journal(path)["run_id"]
    except JournalError:
        run_id = _folder_run_id(path)  # a journal that no longer loads can still be discarded
        if run_id is None:
            raise
    problem = _delete_run_folder(path, run_id)
    if problem:
        raise JournalError("not-deleted", problem)
    return {"status": "ok", "journal": str(path), "run_dir": str(path.parent), "deleted": True}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline-journal",
        description=(
            "The forger's pipeline journal (references/pipeline-mode.md): start it from the "
            "invocation, record each step, write the pipeline result, and work out the resume "
            "or repair offer a stopped chain leaves."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Parse the invocation on stdin and create the run folder and its journal.")
    start.add_argument("--run-root", required=True, help="The folder that holds the runs' folders.")
    start.set_defaults(func=cmd_start)

    step = sub.add_parser("step", help="Record the step the chain just finished.")
    step.add_argument("--journal", required=True, help="The journal `start` created.")
    step.add_argument("--code", required=True, type=str.upper, help="The code of the step that finished.")
    how = step.add_mutually_exclusive_group(required=True)
    how.add_argument("--gate", action="store_true",
                     help="Read the JSON pipeline-gate.py printed for the step on stdin and record its decision.")
    how.add_argument("--status", choices=STATUS_CHOICES, help="How a step with no gate decision ended.")
    step.add_argument("--reason", help="The halt reason, with --status halted.")
    step.add_argument("--set", action="append", metavar="NAME=VALUE",
                      help="A value the step hands the next, by its Data Flow name (skill_name, brief_path).")
    step.add_argument("--output", action="append", metavar="PATH",
                      help="A result or report path the step's envelope names.")
    step.set_defaults(func=cmd_step)

    finish = sub.add_parser("finish", help="Write the pipeline result; delete the run folder when nothing is left.")
    finish.add_argument("--result-dir", required=True, help="The folder of the pipeline result files (the sidecar).")
    finish.add_argument("--journal", help="The run's journal; omitted for a chain that stopped before it started.")
    finish.add_argument("--halt-reason", help="Why the chain stopped, when no step call recorded it.")
    finish.set_defaults(func=cmd_finish)

    resume = sub.add_parser("resume", help="The resume or repair offer the newest journal leaves.")
    resume.add_argument("--run-root", required=True, help="The folder that holds the runs' folders.")
    resume.add_argument("--result-dir", required=True, help="The folder of the pipeline result files (the sidecar).")
    resume.add_argument("--forge-data-folder", help="Where test results live: a later test drops the offer.")
    resume.add_argument("--skills-output-folder", help="Where the export manifest lives: a later export drops the offer.")
    resume.set_defaults(func=cmd_resume)

    reopen = sub.add_parser("reopen", help="Apply the accepted offer and print the steps still to run.")
    reopen.add_argument("--journal", required=True, help="The journal `resume` named.")
    reopen.set_defaults(func=cmd_reopen)

    discard = sub.add_parser("discard", help="Delete a stopped chain's run folder, so its offer is made no more.")
    discard.add_argument("--journal", required=True, help="The journal the offer named.")
    discard.set_defaults(func=cmd_discard)
    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the output streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except JournalError as e:
        print(json.dumps({"status": "error", "error": e.error, "message": e.message, "retry": e.error in RETRYABLE},
                         indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
