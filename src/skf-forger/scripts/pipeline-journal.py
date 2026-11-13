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
           workflow's args. Prints the `steps`, each with its `skill` and
           `description`, and the `next` entry to run (below).
  step     Record the step the chain just finished: the first pending step,
           whose code must be --code. --envelope reads the envelope line the
           workflow printed on stdin, as pipeline-gate.py reads a result: the
           last line of the code's own envelope (ENVELOPES) wins, but every
           line of a CS (BATCHED), which prints one per brief of a `--batch`
           run, counts: the step completes only when every brief did, else it
           halts with the first halted brief's reason, and it hands on each
           brief's skill. A byte-order mark is dropped; an empty stdin halts the step
           `no-result`, only other workflows' lines `wrong-result`, and text
           it cannot read `result-unreadable`. After AN, TS, AS or VS it runs
           pipeline-gate.py's rules in process, with the next plan code and
           AN's plan `min`, and records the decision as --gate does. After
           AS it also hands the gate --forge-data-folder,
           --skills-output-folder, --sidecar and the skill AS audited (its
           bracket, else the journal's skill), so a CLEAN audit of a skill
           that is current skips `US TS EX`.
           After any other workflow it reads the line's `status` (SF's
           `skf_setup.status`, US's `skf_update.status`): a status
           COMPLETED_STATUSES lists completes the step, one HALT_REASONS
           names halts with its reason (CS `partial`: `zero-exports`, EX
           `dry-run`: `dry-run`), and any other status halts with the
           envelope's `halt_reason`, else the status and `: <error.reason>`
           when the envelope names one (no status: `no-status`). Whatever
           the step's status it records the value HANDOFF_FIELDS finds for
           the code's HANDOFFS name, which wins over a --set one, and the
           line's `result_path` and `report_path` as outputs; a completed
           step whose line names no such value halts `handoff-missing`.
           --gate reads the JSON pipeline-gate.py printed on stdin:
           `continue` records the step `completed`, `skip` also records
           `skipped`, with the gate's reason, each step it passes over, and
           `halt` records the step `halted` with the gate's reason (the
           journal is then `halted`). A skip names one code or several
           (`US TS EX`): the step right after this one must be its first
           (else `skip-mismatch`, and nothing is recorded); from that step
           on, the steps are matched to the skip's codes in their order,
           each code once, so a step is passed over while its code is the
           next one the skip names and its bracket is empty or names the
           gated step's skill (its bracket, else the journal's skill), and
           the first step that is not ends the pass (`AS[x] US EX TS` passes
           over US alone, `AS[x] US TS EX TS[y]` goes on with `TS[y]`,
           `AS[x] US TS[y] EX[y]` passes over US alone, and
           `AS[x] US[y] TS EX` over nothing). The gate's
           `handoff` is recorded too, on a halt as well: AS's `target_ref`
           when upstream moved, which a value given with --set does not
           replace. --status records a step with
           no envelope line to read: `completed`, or `halted` with --reason
           (`-` reads it on stdin; --gate and --envelope read stdin, so
           `--reason -` with them is a usage error).
           --set records a value the step hands the next, by its Data Flow
           name (a name given twice in one call holds a list): a CS, QS, SS
           or US that --gate or --status records completed must hand on
           `skill_name`, an AN or BS `brief_path`, an RA
           `architecture_doc_path`. --output records a result or report
           path the step's envelope names. Prints the step it `recorded`,
           the steps a gate `skipped` (a list, empty when none), the `gate`
           decision it recorded (null for a code with no gate), and the
           `next` entry, null after a halt or the last step.
  finish   Write the pipeline result from the journal to --result-dir:
           `pipeline-result-<YYYYMMDD-HHmmss>.json` (UTC; -2, -3 ... when a
           run already took that second's name), then its copy
           `pipeline-result-latest.json`, and print the next action the
           stop leaves (below). The run folder is deleted when nothing is
           left to resume (every step completed or skipped, or a halt no
           resume fixes) and kept otherwise. A --halt-reason with no halted
           step halts the first pending one; `--halt-reason -` reads the
           reason on stdin, and an empty one counts as no --halt-reason.
           A journal that cannot be saved
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
           An offer also prints the journal's `started_at` and `updated_at`
           (its last write): a chain the journal still records `running`
           (an `interrupted` offer) may still run in another session.
  reopen   Apply the offer the user accepted: the halted step is pending
           again (after AS CRITICAL the audit counts as done), a repair that
           is a workflow of its own joins the plan right before the step it
           repairs, and the first step to run takes the journal's skill as
           its target when it takes a skill and names none. The journal runs
           again. Prints the steps still to `run`, each with its `skill` and
           `description`, and the `next` entry, the first of them.
  discard  Delete a stopped chain's run folder, so its offer is made no more.

The next entry. `start`, `step` and `reopen` print the plan entry to run
next as `next`: its `index`, the step's fields, its code's `skill` and
`description` (parse-pipeline.py's SKILLS), and the `inputs` its workflow
runs with (resolve_inputs, from DATA_FLOW). Only the printed entry carries
these: the journal keeps the step shape above.

  {"index": 3, "code": "TS", "min": 90, "mode": null, "target": null,
   "flags": [], "status": "pending", "reason": null, "skill": "skf-test-skill",
   "description": "Cognitive completeness verification: quality gate before export",
   "inputs": {"skill_name": "hono", "threshold": 90}}

`inputs` holds the entry's bracket `target`; else each input DATA_FLOW
gives its code, from the run's `data` (several briefs reach CS as one
`batch` list), the journal's skill for `skill_name`, or the target of the
VS before it for RA's `architecture_doc_path`; else, for the plan's first
workflow, the parse's `args`. Then `target_ref` (US), `pin` (the first
workflow), `threshold` (TS's `min`), `auto` (mode `auto`) and `flags`,
each only when it has a value.

Next action. A chain interrupted mid-step (its journal still `running`),
or halted for a reason REPAIRS does not list, gets the offer `resume` at
the step it stopped on. A halt REPAIRS lists (a quality verdict, a skill
with no exports, or a step that named no value to hand on, which running
it again does not change) gets a `repair`, which the user makes first
unless it is a workflow of its own (USER_ACTIONS):

  halted on  reason                        repair                   picks up at
  TS         FAIL                          update-from-test-report  TS, after
                                           (US <skill> --from-test-report)
  TS         INCONCLUSIVE                  add-evidence             TS
  TS         pass-with-drift,
             workspace-drift               retest-at-pinned-commit  TS
  AS         CRITICAL                      review-drift-report      the step
                                                                    after AS
  VS         zero-coverage                 create-missing-skills    VS
  CS         zero-exports                  fix-brief-scope          CS
  AN         no-skillable-units,
             units-below-min, skipped      new-target               no resume
  AN         redirect                      update-existing-skill    no resume
  CS, QS,    handoff-missing               start-rest-by-hand       no resume
  SS, US,
  AN, BS, RA

`finish` and `resume` print it in one shape: `offer` (`resume`, `repair`,
or null when nothing is left to resume), `kind` (`interrupted`, `error` or
`quality`), `repair`, `user_action` (what the user does first, or null),
`route` (the next action in one line, such as `US hono --from-test-report,
then TS EX at the recorded threshold of 90`), `halted_on`, `resume_at` and
`threshold` (the TS `min` the rest of the plan carries). Every value is
null for a chain that nothing stopped. `resume` adds the journal's
`started_at` and `updated_at` beside these keys; `finish` does not.

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
  uv run scripts/pipeline-journal.py step --journal <file> --code CS --envelope <<'SKF_RESULT'
  SKF_CREATE_SKILL_RESULT_JSON: {"status": "success", "summary": {"skill_name": "hono"}, ...}
  SKF_RESULT
  uv run scripts/pipeline-journal.py step --journal <file> --code AS --forge-data-folder <dir> \\
      --skills-output-folder <dir> --sidecar <dir> --envelope <<'SKF_RESULT'
  SKF_AUDIT_RESULT_JSON: {"status": "success", "drift_score": "CLEAN", ...}
  SKF_RESULT
  uv run scripts/pipeline-journal.py step --journal <file> --code SF --status halted --reason - <<'SKF_REASON'
  <the line SF displayed>
  SKF_REASON
  uv run scripts/pipeline-journal.py step --journal <file> --code CS \\
      --status completed --set skill_name=hono
  uv run scripts/pipeline-journal.py step --journal <file> --code TS --gate <<'SKF_GATE'
  {"code": "TS", "decision": "halt", "reason": "FAIL", "skip": null, "message": "..."}
  SKF_GATE
  uv run scripts/pipeline-journal.py finish --journal <file> --result-dir <dir> --halt-reason - <<'SKF_REASON'
  <the reason the chain stopped with, or nothing>
  SKF_REASON
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
     step, a gate that cannot load (`gate-missing`), a halt with no
     reason, nothing to resume
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
GATE = Path(__file__).resolve().parent / "pipeline-gate.py"

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
# decision (--envelope runs the gate, --gate reads what it printed), not a
# status given by hand.
GATED = frozenset({"AN", "TS", "AS", "VS"})
# The value a completed step hands the next workflow, by its Data Flow name
# in pipeline-contracts.md. A resumed chain passes it on, and the offer's
# later-test and later-export checks look the skill up by it.
HANDOFFS = {"AN": "brief_path", "BS": "brief_path", "CS": "skill_name", "QS": "skill_name", "US": "skill_name",
            "SS": "skill_name", "RA": "architecture_doc_path"}
# Where each code's envelope holds the value HANDOFFS names, as keys from the
# envelope's top: the code's schema in src/shared/scripts/schemas/. AN's list
# records one brief as a string and several as a list, as --set records them.
HANDOFF_FIELDS = {
    "AN": ("brief_paths",),
    "BS": ("brief_path",),
    "CS": ("summary", "skill_name"),
    "QS": ("summary", "skill_name"),
    "US": ("skf_update", "skill_name"),
    "SS": ("skill_name",),
    "RA": ("refined_path",),
}
# The envelope's top-level paths a step records as its outputs.
OUTPUT_FIELDS = ("result_path", "report_path")
# The envelope line each workflow prints in headless mode, by code: each
# schema's title in src/shared/scripts/schemas/ (pipeline-gate.py's
# ENVELOPES for the gated codes).
ENVELOPES = {
    "SF": "SKF_SETUP_RESULT_JSON",
    "AN": "SKF_ANALYZE_RESULT_JSON",
    "BS": "SKF_BRIEF_RESULT_JSON",
    "CS": "SKF_CREATE_SKILL_RESULT_JSON",
    "QS": "SKF_QUICK_SKILL_RESULT_JSON",
    "SS": "SKF_STACK_RESULT_JSON",
    "US": "SKF_UPDATE_RESULT_JSON",
    "AS": "SKF_AUDIT_RESULT_JSON",
    "VS": "SKF_VERIFY_STACK_RESULT_JSON",
    "RA": "SKF_REFINE_ARCHITECTURE_RESULT_JSON",
    "TS": "SKF_TEST_RESULT_JSON",
    "EX": "SKF_EXPORT_RESULT_JSON",
    "RS": "SKF_RENAME_SKILL_RESULT_JSON",
    "DS": "SKF_DROP_SKILL_RESULT_JSON",
}
# The object an envelope holds its fields in, as SF's and US's schemas wrap
# them; every other envelope holds them at its top.
PAYLOADS = {"SF": "skf_setup", "US": "skf_update"}
# The `status` values that complete a step with no gate, by code: `success`,
# and the successful exits the US schema names. Mirrors the Circuit Breakers
# intro in pipeline-contracts.md.
COMPLETED_STATUSES = {
    "SF": ("success",),
    "BS": ("success",),
    "CS": ("success",),
    "QS": ("success",),
    "SS": ("success",),
    "US": ("success", "no-changes", "detect-only", "dry-run"),
    "RA": ("success",),
    "EX": ("success",),
    "RS": ("success",),
    "DS": ("success",),
}
# A status that halts with a reason of its own, keyed (code, status): the CS
# and EX rows of the Circuit Breakers table in pipeline-contracts.md. Any
# other status halts with the envelope's halt_reason, else the status.
HALT_REASONS = {("CS", "partial"): "zero-exports", ("EX", "dry-run"): "dry-run"}
# The codes whose step reads every envelope line of its own: CS takes several briefs as one `--batch` run
# (resolve_inputs) and prints one line per brief, so a brief that failed is never hidden behind a later one.
BATCHED = frozenset({"CS"})
# An envelope line, as pipeline-gate.py finds one.
_ENVELOPE_RE = re.compile(r"(SKF_[A-Z0-9_]+_RESULT_JSON):\s*(\{.*\})\s*$")
# What a workflow takes from the one before it, keyed (from, to): one key per
# row of the Data Flow table in pipeline-contracts.md, each value the inputs
# the receiving code takes. resolve_inputs reads it for the entry to run next.
DATA_FLOW = {
    ("AN", "BS"): ("brief_path",),
    ("AN", "CS"): ("brief_path",),
    ("BS", "CS"): ("brief_path",),
    ("CS", "TS"): ("skill_name",),
    ("CS", "EX"): ("skill_name",),
    ("TS", "EX"): ("skill_name",),
    ("QS", "TS"): ("skill_name",),
    ("QS", "EX"): ("skill_name",),
    ("AS", "US"): ("skill_name", "target_ref"),
    ("US", "TS"): ("skill_name",),
    ("VS", "RA"): ("architecture_doc_path",),
    ("RA", "SS"): ("architecture_doc_path",),
    ("SS", "TS"): ("skill_name",),
    ("SS", "EX"): ("skill_name",),
}

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
    ("CS", "zero-exports"): ("fix-brief-scope", "same"),
    ("AN", "no-skillable-units"): ("new-target", None),
    ("AN", "units-below-min"): ("new-target", None),
    ("AN", "skipped"): ("new-target", None),
    ("AN", "redirect"): ("update-existing-skill", None),
    # A step that completed but named no value to hand on: running it again names none either.
    **{(code, "handoff-missing"): ("start-rest-by-hand", None) for code in HANDOFFS},
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
    "fix-brief-scope": "fix the brief's scope.include or target_version so it reaches the package's public exports",
    "new-target": "start a new chain with another target, or with a scope hint",
    "update-existing-skill": "run US on the skill the target already has",
    "start-rest-by-hand": "start the steps left as a new chain, with the value the step made in the first one's "
                          "bracket (for example TS[<skill>] EX)",
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


def _named(step: dict, skills: dict) -> dict:
    """A step as printed: the persisted shape, then its code's `skill` and `description` (SKILLS)."""
    skill, description = skills.get(step["code"], (None, None))
    return {**step, "skill": skill, "description": description}


def _entry(journal: dict, index: int, *, skills: dict, inputs: bool = False) -> dict:
    """The plan entry at `index` as `start`, `step` and `reopen` print it; with `inputs`, the ones it runs with.

    Only the printed entry carries `skill`, `description` and `inputs`: the
    journal keeps each step in the persisted shape.
    """
    entry = {"index": index, **_named(journal["steps"][index], skills)}
    if inputs:
        entry["inputs"] = resolve_inputs(journal, index)
    return entry


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


def _takes(code: str) -> list[str]:
    """The inputs DATA_FLOW gives `code`, in table order, each once."""
    names: list[str] = []
    for (_, to), taken in DATA_FLOW.items():
        names += [n for n in taken if to == code and n not in names]
    return names


def _handed(journal: dict, index: int, name: str):
    """The value an earlier step left for the input `name` of the entry at `index`, or None.

    RA's `architecture_doc_path` is the document the VS before it was given;
    SS's is the refined one RA handed on, in `data`.
    """
    if name == "architecture_doc_path" and journal["steps"][index]["code"] == "RA":
        vs = next((s for s in reversed(journal["steps"][:index]) if s["code"] == "VS"), None)
        return None if vs is None else vs.get("target")
    held = journal["data"].get(name)
    if name == "skill_name" and held in (None, "", []):
        return _skill_name(journal)
    return held


def resolve_inputs(journal: dict, index: int) -> dict:
    """The inputs the workflow of the entry at `index` runs with, resolved from the journal.

    Its bracket `target`; else each input DATA_FLOW gives its code, from the
    run's `data` (a `brief_path` list goes to CS as one `batch`), the
    journal's skill, or VS's document for RA; else, for the plan's first
    workflow (the first entry other than SF), the parse's `args` but `pin`.
    Then `target_ref` (US), `pin` (the first workflow), `threshold` (TS's
    `min`), `auto` (mode `auto`) and `flags`. A key with no value is left out.
    """
    steps = journal["steps"]
    step, args = steps[index], journal["args"]
    first = next((i for i, s in enumerate(steps) if s["code"] != "SF"), None) == index
    takes = _takes(step["code"])
    inputs: dict = {}
    if step.get("target") is not None:
        inputs["target"] = step["target"]
    else:
        for name in takes:
            if name == "target_ref":
                continue
            value = _handed(journal, index, name)
            if value in (None, "", []):
                continue
            if name == "brief_path" and step["code"] == "CS" and isinstance(value, list):
                inputs["batch"] = value
            else:
                inputs[name] = value
        if not inputs and first:
            inputs.update((k, v) for k, v in args.items() if k != "pin")
    if "target_ref" in takes and journal["data"].get("target_ref"):
        inputs["target_ref"] = journal["data"]["target_ref"]
    if first and args.get("pin"):
        inputs["pin"] = args["pin"]
    if step["code"] == "TS" and step.get("min") is not None:
        inputs["threshold"] = step["min"]
    if step.get("mode") == "auto":
        inputs["auto"] = True
    if step.get("flags"):
        inputs["flags"] = list(step["flags"])
    return inputs


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


def _load_sibling(name: str, path: Path, error: str):
    """Load a script that ships in this script's folder, when a call needs it (never at import)."""
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError("no import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError) as e:
        raise JournalError(error, f"{path.name} cannot be loaded from {path.parent}: {e}") from None
    return module


def _load_parser():
    """Load parse-pipeline.py, which ships in this script's folder."""
    return _load_sibling("skf_parse_pipeline", PARSER, "parser-missing")


def _load_gate():
    """Load pipeline-gate.py, which ships in this script's folder: `step --envelope` runs its rules."""
    return _load_sibling("skf_pipeline_gate", GATE, "gate-missing")


def _read_stdin() -> str:
    # A Windows console reads cp1252: the arrows, paths and gate messages need UTF-8.
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    return sys.stdin.read()


def _read_result_text() -> str | None:
    """The envelope text on stdin, a byte-order mark dropped, or None when it is not UTF-8."""
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8-sig", errors="strict")
        text = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return None
    return text[1:] if text.startswith("\ufeff") else text


def cmd_start(args) -> dict:
    raw = _read_stdin().strip()
    if not raw:
        raise JournalError("no-invocation", "No invocation on stdin: pass the whole pipeline invocation.")
    parser = _load_parser()
    parsed = parser.parse_pipeline(raw)
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
            "alias": journal["alias"], "args": journal["args"],
            "steps": [_named(s, parser.SKILLS) for s in journal["steps"]],
            "next": _entry(journal, 0, skills=parser.SKILLS, inputs=True)}


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
    return _checked_decision(value, code)


def _checked_decision(value, code: str) -> dict:
    """`value` when it is a gate decision for `code` that names what its decision needs."""
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


def _gate_handoff(decision: dict) -> dict:
    """The values the gate's `handoff` names (AS's `target_ref`), each a lower-case name and a non-empty string."""
    handoff = decision.get("handoff")
    if not isinstance(handoff, dict):
        return {}
    return {name: value.strip() for name, value in handoff.items()
            if isinstance(name, str) and _NAME_RE.match(name) and isinstance(value, str) and value.strip()}


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _at(value, keys: tuple):
    """The value under `keys`, one object key after another, or None."""
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def read_envelope(code: str, text: str | None) -> tuple[list[dict], str | None]:
    """(results, problem) for the text a step printed, as pipeline-gate.py's read_result reads it.

    The last envelope line of `code`'s own workflow wins, but a BATCHED
    code's lines each count, in the order printed (one per brief). Envelope
    lines of other workflows alone are `wrong-result`; with no envelope line
    at all, the whole text must be one JSON object. Empty text is
    `no-result`, and text that is not UTF-8 (None) or not those objects
    `result-unreadable`.
    """
    if text is None:
        return [], "result-unreadable"
    if not text.strip():
        return [], "no-result"
    found = [m for m in map(_ENVELOPE_RE.search, text.splitlines()) if m]
    own = [m.group(2) for m in found if m.group(1) == ENVELOPES.get(code)]
    if found and not own:
        return [], "wrong-result"
    try:
        values = [json.loads(raw) for raw in (own if code in BATCHED else own[-1:]) or [text]]
    except ValueError:
        return [], "result-unreadable"
    return (values, None) if all(isinstance(v, dict) for v in values) else ([], "result-unreadable")


def envelope_outcome(code: str, result: dict) -> tuple[str, str | None]:
    """The status a step with no gate records from its envelope, and its halt reason (None when it completed)."""
    payload = result.get(PAYLOADS[code]) if code in PAYLOADS else result
    payload = payload if isinstance(payload, dict) else {}
    status = _text(payload.get("status"))
    if status is None:
        return "halted", "no-status"
    key = status.lower()
    if key in COMPLETED_STATUSES.get(code, ("success",)):
        return "completed", None
    if (code, key) in HALT_REASONS:
        return "halted", HALT_REASONS[(code, key)]
    named = _text(payload.get("halt_reason"))
    if named:
        return "halted", named
    detail = _text(_at(payload, ("error", "reason")))
    return "halted", f"{status}: {detail}" if detail else status


def envelopes_outcome(code: str, results: list[dict]) -> tuple[str, str | None]:
    """The status a step with no gate records from its envelope lines: the first that halts, else completed."""
    for result in results:
        status, reason = envelope_outcome(code, result)
        if status == "halted":
            return status, reason
    return "completed", None


def envelope_values(code: str, results: list[dict]) -> tuple[dict, list[str]]:
    """The handoff value the envelope lines name, by its HANDOFFS name, and their output paths.

    One value is a string and several a list, each once: AN's briefs, or the skill of each brief of a CS batch.
    """
    items: list[str] = []
    outputs: list[str] = []
    for result in results:
        value = _at(result, HANDOFF_FIELDS[code]) if code in HANDOFF_FIELDS else None
        for item in value if isinstance(value, list) else [value]:
            if _text(item) and _text(item) not in items:
                items.append(_text(item))
        outputs += [p for p in (_text(result.get(name)) for name in OUTPUT_FIELDS) if p]
    values = {HANDOFFS[code]: items[0] if len(items) == 1 else items} if items else {}
    return values, outputs


def _decided(decision: dict, steps: list, index: int, code: str,
             skill: str | None) -> tuple[str, str | None, list[int], str | None]:
    """The status and reason a gate decision records, and the steps a skip passes over with its reason.

    A skip names one code or several (`US TS EX`): the step right after the
    gated one must be its first; from it on, the steps are matched to the
    skip's codes in their order, each code once. A step is passed over while
    its code is the next one the skip names and its `target` is empty or
    names `skill`, the gated step's skill, so the first step that is not
    (another code, or another skill's step) ends the pass.
    """
    status = "halted" if decision["decision"] == "halt" else "completed"
    reason = decision["reason"].strip() if status == "halted" else None
    if decision["decision"] != "skip":
        return status, reason, [], None
    codes = decision["skip"].upper().split()
    first = index + 1
    following = steps[first]["code"] if first < len(steps) else None
    if following != codes[0]:
        raise JournalError("skip-mismatch", f"The gate passes over {decision['skip'].strip()}, but the step after "
                                            f"{code} is {following or 'none'}.")
    skipped = first
    for want in codes:
        step = steps[skipped] if skipped < len(steps) else None
        if (step is not None and step["code"] == want and step["status"] == "pending"
                and step.get("target") in (None, "", skill)):
            skipped += 1
        else:
            break
    return status, reason, list(range(first, skipped)), decision["reason"].strip()


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
    skipped: list[int] = []
    skip_reason = decision = None
    found: dict = {}
    outputs: list[str] = []
    # The skill the gated step works on: its own bracket, else the journal's skill. AS's gate reads it to skip
    # `US TS EX` of a skill that is current, and a skip passes over only the steps of that skill.
    gated = steps[index].get("target")
    skill = gated.strip() if isinstance(gated, str) and gated.strip() else _skill_name(journal)
    if args.envelope:
        text = _read_result_text()
        results, problem = read_envelope(args.code, text)
        if args.code in GATED:
            gate = _load_gate()  # before anything is recorded: a gate that cannot load records nothing
            plan_min = steps[index]["min"]
            minimum = plan_min if args.code == "AN" and isinstance(plan_min, int) else 1
            next_code = steps[index + 1]["code"] if index + 1 < len(steps) else None
            on_disk = {"forge_data_folder": args.forge_data_folder, "skills_output_folder": args.skills_output_folder,
                       "sidecar": args.sidecar, "skill": skill} if args.code == "AS" else {}
            decision = _checked_decision(gate.gate(args.code, text, next_code=next_code, minimum=minimum, **on_disk),
                                         args.code)
        else:
            status, reason = ("halted", problem) if problem else envelopes_outcome(args.code, results)
        found, outputs = envelope_values(args.code, results)
    elif args.gate:
        decision = _gate_decision(_read_stdin(), args.code)
    else:
        status = args.status
        given = _read_stdin() if args.reason == "-" else args.reason
        reason = ((given or "").strip() or None) if status == "halted" else None
        if status == "completed" and args.code in GATED:
            raise JournalError("gate-required", f"{args.code} has a gate: record it with --envelope and the "
                                                "envelope line it printed on stdin.")
        if status == "halted" and reason is None:
            raise JournalError("reason-missing", "A halted step needs --reason: the workflow's halt reason.")
    gate_handoff: dict = {}
    if decision is not None:
        status, reason, skipped, skip_reason = _decided(decision, steps, index, args.code, skill)
        gate_handoff = _gate_handoff(decision)
    # The envelope is the step's own record, so its values win over one typed with --set.
    values = {**_set_values(args.set or []), **found, **gate_handoff}
    need = HANDOFFS.get(args.code)
    if status == "completed" and need and need not in values:
        if not args.envelope:
            raise JournalError("handoff-missing", f"A completed {args.code} hands `{need}` to the next workflow: "
                                                  f"pass --set \"{need}=<value>\".")
        # The next workflow would start without its input.
        status, reason, skipped, skip_reason = "halted", "handoff-missing", [], None
    steps[index].update(status=status, reason=reason)
    for passed in skipped:
        steps[passed].update(status="skipped", reason=skip_reason)
    journal["data"].update(values)
    paths = list(dict.fromkeys([*outputs, *(args.output or [])]))
    journal["outputs"].extend({"code": args.code, "path": p} for p in paths)
    if status == "halted":
        journal["status"] = "halted"
    journal["updated_at"] = _stamp(_now())
    _save(path, journal)
    following = None if status == "halted" else _first(steps, "pending")
    # The step is saved: a parser that no longer loads loses nothing the chain ran.
    nxt = None if following is None else _entry(journal, following, skills=_load_parser().SKILLS, inputs=True)
    return {"status": "ok", "journal": str(path), "recorded": _indexed(steps, index),
            "skipped": [_indexed(steps, passed) for passed in skipped],
            "gate": decision, "next": nxt, "data": journal["data"]}


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
    given = _read_stdin() if args.halt_reason == "-" else args.halt_reason
    halt_reason = (given or "").strip() or None  # an empty heredoc is no --halt-reason
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
        # When the chain started and the journal's last write: an `interrupted` chain may still run elsewhere.
        "started_at": journal.get("started_at"),
        "updated_at": journal.get("updated_at"),
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
    skills = _load_parser().SKILLS  # before anything changes: a reopen that fails leaves the offer as it was
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
    run = [i for i in range(at, len(steps)) if steps[i]["status"] == "pending"]
    return {"status": "ok", "journal": str(path), "offer": offer["offer"], "repair": offer["repair"],
            "alias": journal.get("alias"), "skill_name": skill,
            "run": [_entry(journal, i, skills=skills) for i in run],
            "next": _entry(journal, run[0], skills=skills, inputs=True) if run else None,
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
    how.add_argument("--envelope", action="store_true",
                     help="Read the envelope line the workflow printed on stdin and record the step from it: the "
                          "gate's rules for AN, TS, AS and VS, the envelope's status for the others.")
    how.add_argument("--gate", action="store_true",
                     help="Read the JSON pipeline-gate.py printed for the step on stdin and record its decision.")
    how.add_argument("--status", choices=STATUS_CHOICES, help="How a step with no envelope line to read ended.")
    step.add_argument("--reason", help="The halt reason, with --status halted; '-' reads it on stdin.")
    step.add_argument("--set", action="append", metavar="NAME=VALUE",
                      help="A value the step hands the next, by its Data Flow name (skill_name, brief_path, "
                           "architecture_doc_path); an envelope's value wins over it.")
    step.add_argument("--output", action="append", metavar="PATH",
                      help="A result or report path the step's envelope names.")
    step.add_argument("--forge-data-folder",
                      help="With --envelope after AS: the forge data folder (test and audit records), which the gate "
                           "reads with the next two and the journal's skill to skip `US TS EX` of a skill that is "
                           "current; each of those codes passes over the step it matches, in that order, while that "
                           "step works on the same skill.")
    step.add_argument("--skills-output-folder", help="With --envelope after AS: the skills output folder.")
    step.add_argument("--sidecar", help="With --envelope after AS: the forger's sidecar folder (forge-tier.yaml, "
                                        "preferences.yaml).")
    step.set_defaults(func=cmd_step, usage_error=step.error)

    finish = sub.add_parser("finish", help="Write the pipeline result; delete the run folder when nothing is left.")
    finish.add_argument("--result-dir", required=True, help="The folder of the pipeline result files (the sidecar).")
    finish.add_argument("--journal", help="The run's journal; omitted for a chain that stopped before it started.")
    finish.add_argument("--halt-reason", help="Why the chain stopped, when no step call recorded it; '-' reads it on "
                                              "stdin, where an empty text is no reason.")
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
    if args.command == "step" and args.reason == "-" and args.status is None:
        args.usage_error("argument --reason: '-' reads the reason on stdin, which --envelope and --gate read too: "
                         "give it with --status halted")
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
