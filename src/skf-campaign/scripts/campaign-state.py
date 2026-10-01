# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema>=4.0"]
# ///
"""Campaign State: every write to _campaign-state.yaml, and the resume point.

The campaign's progress lives in one YAML file that must survive a session
dying at any moment. The step files used to re-type the whole file on every
change: copy it to .bak, edit it in memory, type a timestamp with no clock to
read, write it back, and check it only when the next step loaded it. A bad
write for one skill was then copied over the last good .bak by the next
write, and resume found both files invalid. This script owns every write, so
the step files name an operation and its inputs and never touch the YAML.

Each write operation, in this order:

  1. reads the state and validates it (campaign-validate-state.py's schema
     check, date-time fields included): an invalid state is never rotated
     into .bak, and nothing is written (exit 3);
  2. applies the operation, sets `campaign.current_stage` when --stage is
     given, and stamps `campaign.last_updated` (and any started_at or
     completed_at the operation sets) from the system clock, in UTC;
  3. validates the result: a change that would make the state invalid is
     refused and nothing is written (exit 3);
  4. copies the primary it read, which validated, to the .bak beside it,
     then writes the new state; each file is written to a temporary file
     and renamed over the old one, so a crash leaves the old file or the
     new one, never half of one.

Operations:

  init              Create the state (step-01). Reads the parsed targets
                    (campaign-parse-manifest.py's JSON output, a file or `-`
                    for stdin) and settles the quality gate through
                    campaign-quality-gate.py's check (a brief's
                    quality_gate wins when --brief-file names one). Refuses
                    a state file or backup that already exists.
  set-stage         Write current_stage alone: a stage's final write when it
                    records nothing else.
  set-skill         Set the status, quality_score, skill_path or brief_path
                    of one or more skills (--skill repeats). `active` stamps
                    started_at when it is not set yet (an interrupted run
                    keeps its start); `completed` stamps completed_at;
                    `pending` (a reset for a re-run) clears both.
  apply-plan        Write the execution order and the cycle flag that
                    campaign-deps.py --compute gives for the state (step-02);
                    refuses a plan the stages cannot follow (exit 4).
  apply-pins        Write the resolved pins from campaign-validate-pins.py's
                    output (step-03); refuses output with an invalid pin
                    (exit 5).
  apply-provenance  Write each commit SHA from campaign-provenance.py's
                    output (step-04); refuses output with an inaccessible
                    repository (exit 6).
  apply-batch       The Tier B batch (step-06), from the line-to-skill map
                    campaign-render-batch.py wrote: --start marks the map's
                    skipped_by_directive skills `skipped` and its batched
                    skills `active`; --results-file records the joined
                    results (campaign-render-batch.py --record output);
                    --no-results fails every batched skill.
  append-workarounds
                    Append entries to one skill's workarounds_applied; an
                    entry it already holds is not added twice.
  set-campaign      Write campaign-level fields: the architecture document
                    path, and the capstone, verification or refinement
                    summary read from the sub-skill's result envelope line
                    (a file or `-`; the line's SKF_*_RESULT_JSON: prefix is
                    optional). A success envelope is recorded; an error
                    envelope, or --no-capstone and the like, records null.
                    A recorded verification also sets capstone.verified.
  recover           Copy a .bak that validates over the primary (step-resume).
  archive           Move the state, its .bak and the brief, each one that
                    exists, into archive/<campaign name>-<UTC stamp>/ beside
                    the state (SKILL.md's overwrite), so step-01's init can
                    start a new campaign. The name comes from the state, else
                    the .bak, else "campaign"; an existing folder is refused.
  log               Append one typed entry to the decision log: decision (an
                    operator's choice), auto (a default a headless run took)
                    or event (a failure, a recovery, a skip), stamped from
                    the clock. The log is append-only.
  halt-payload      Print the payload of a HARD HALT's error envelope for
                    skf-emit-result-envelope.py emit-halt (read-only): the
                    phase, the halt reason, the halt message read from stdin,
                    the completed and failed counts of the state (0 when it
                    cannot be read) and the decision log beside it (null
                    before the campaign workspace exists).
  resume            Compute the resume point (read-only): the stage and step
                    file to chain to, from the state and --from.

Resume rule. Without --from: an active skill resumes its own stage (Tier A
at stage 4, the skill loop; Tier B at stage 5, the batch, whose script
batches the active skills an interrupted batch left), with no +1; otherwise
the next stage is current_stage + 1, because current_stage is the highest
completed stage, capped at 10 (the report stage reruns, never a stage 11).
The campaign is complete when current_stage is 10 and no skill is pending or
active. With --from: an unknown skill is an error; a pending or active skill
resumes its tier's stage; a completed, failed or skipped one needs the
operator's choice (needs_choice), unless --next takes the next pending or
active skill after it in the execution order (complete when there is none).

CLI:
  uv run campaign-state.py init --state-file <p> --targets-file <p|-> --name <name> \\
      --hard <value> --soft-target <N> --soft-fallback <N> [--brief-file <p>] \\
      [--directive-path <p>] [--architecture-doc-path <p>]
  uv run campaign-state.py set-stage --state-file <p> --stage <N>
  uv run campaign-state.py set-skill --state-file <p> --skill <name> [--skill <name> ...] \\
      [--status <status>] [--quality-score <N>] [--skill-path <p>] [--brief-path <p>] [--stage <N>]
  uv run campaign-state.py apply-plan --state-file <p> [--stage <N>]
  uv run campaign-state.py apply-pins --state-file <p> --results-file <p|-> [--stage <N>]
  uv run campaign-state.py apply-provenance --state-file <p> --results-file <p|-> [--stage <N>]
  uv run campaign-state.py apply-batch --state-file <p> --map-file <p> \\
      (--start | --results-file <p|-> | --no-results) [--stage <N>]
  uv run campaign-state.py append-workarounds --state-file <p> --skill <name> \\
      --entry <text> [--entry <text> ...] [--stage <N>]
  uv run campaign-state.py set-campaign --state-file <p> [--architecture-doc-path <p>] \\
      [--capstone <p|-> | --no-capstone] [--verification <p|-> | --no-verification] \\
      [--refinement <p|-> | --no-refinement] [--stage <N>]
  uv run campaign-state.py recover --state-file <p>
  uv run campaign-state.py archive --state-file <p> --brief-file <p>
  uv run campaign-state.py log --log-file <p> --type <decision|auto|event> --text <entry>
  uv run campaign-state.py halt-payload --state-file <p> --phase <slug> --halt-reason <class> < <message>
  uv run campaign-state.py resume --state-file <p> [--from <skill>] [--next]

The backup is always <state-file>.bak.

Output (one JSON object on stdout):
  writes:   {"op", "state_file", "backup_file", "backup_rotated",
             "last_updated", "current_stage", "changed": [...]} plus the
             operation's own keys (apply-batch: "activated", "skipped",
             "completed", "failed"; set-campaign: "recorded", "not_recorded")
  recover:  {"op", "state_file", "backup_file", "recovered", "last_updated",
             "current_stage"}
  archive:  {"op", "archive_dir", "moved": [...]}
  log:      {"op", "log_file", "entry"}
  halt-payload:
            {"phase", "reason", "halt_reason", "skills_completed",
             "skills_failed", "decision_log"}
  resume:   {"complete", "stage", "step_file", "reason", "skill",
             "needs_choice", "from_status", "active_other"}
Errors: {"error", "code", "errors": [...]} on stderr.

Exit codes (each is the campaign's HALT code for the same class):
  0  written, recovered, archived, logged or computed
  2  invalid input: a missing or unreadable input file, an unknown skill,
     output from another script that holds an error, a gate the gate script
     rejects, a state that init would overwrite, or an archive folder that
     exists
  3  invalid state: the state is missing, malformed or fails the schema, or
     the change would make it fail (nothing written)
  4  apply-plan: a plan the stages cannot follow (circular-deps)
  5  apply-pins: an invalid pin (invalid-pin)
  6  apply-provenance: an inaccessible repository (inaccessible-repo)
  9  recover: the backup is missing or fails validation too
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

HERE = Path(__file__).resolve().parent
VALIDATE_SCRIPT = HERE / "campaign-validate-state.py"
DEPS_SCRIPT = HERE / "campaign-deps.py"
GATE_SCRIPT = HERE / "campaign-quality-gate.py"
STATUSES = ("pending", "active", "completed", "failed", "skipped")
SETTLED = ("completed", "failed", "skipped")
OPEN = ("pending", "active")
LOG_TYPES = ("decision", "auto", "event")
FINAL_STAGE = 10
# Stage N runs step-(N+1); SKILL.md's Stages table.
STEP_FILES = {
    0: "step-01-setup.md",
    1: "step-02-strategy.md",
    2: "step-03-pins.md",
    3: "step-04-provenance.md",
    4: "step-05-skill-loop.md",
    5: "step-06-batch.md",
    6: "step-07-capstone.md",
    7: "step-08-verify.md",
    8: "step-09-refine.md",
    9: "step-10-export.md",
    10: "step-11-maintenance.md",
}
TIER_STAGE = {"A": 4, "B": 5}
DECISION_LOG = "_campaign-decision-log.md"
EXIT_INPUT = 2
EXIT_STATE = 3
EXIT_CIRCULAR = 4
EXIT_PIN = 5
EXIT_REPO = 6
EXIT_NO_BACKUP = 9
_IS_WINDOWS = os.name == "nt"
_REPLACE_WAIT_SECONDS = 5.0
_REPLACE_POLL_SECONDS = 0.05
_modules: dict[str, Any] = {}


class StateError(Exception):
    """A failure reported as {"error", "code", "errors"} on stderr with its exit code."""

    def __init__(self, exit_code: int, code: str, message: str, errors: list | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.errors = errors or []


def _module(path: Path) -> Any:
    """A sibling script, loaded once."""
    key = path.name
    if key not in _modules:
        spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules[key] = module
    return _modules[key]


def now() -> str:
    """The clock's time in UTC, as ISO-8601 with its offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Reading, validating and writing the state
# --------------------------------------------------------------------------


def _schema() -> dict:
    validator = _module(VALIDATE_SCRIPT)
    return json.loads(validator.DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validation_errors(state: Any) -> list[dict]:
    """campaign-validate-state.py's errors for a state already loaded."""
    if not isinstance(state, dict):
        return [{"field": "(root)", "message": "State root must be a mapping"}]
    return _module(VALIDATE_SCRIPT).validate_state(state, _schema())["errors"]


def read_state(path: Path) -> tuple[dict, bytes]:
    """The state and its bytes; StateError (exit 3) unless it validates."""
    if not path.is_file():
        raise StateError(EXIT_STATE, "state-missing", f"State not found at `{path.as_posix()}`.")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StateError(EXIT_STATE, "state-malformed", f"State unreadable: {exc}") from exc
    state, problem = _module(VALIDATE_SCRIPT)._load_yaml_text(text)
    if problem is not None:
        raise StateError(EXIT_STATE, "state-malformed", problem)
    errors = validation_errors(state)
    if errors:
        raise StateError(EXIT_STATE, "state-invalid", "The state fails validation: nothing was written.", errors)
    return state, raw


def dump_state(state: dict) -> bytes:
    text = yaml.safe_dump(state, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return text.encode("utf-8")


def _replace(source: Path, target: Path) -> None:
    """os.replace, retried on Windows while a reader holds either file open."""
    deadline = time.monotonic() + _REPLACE_WAIT_SECONDS
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_POLL_SECONDS)


def write_atomic(path: Path, data: bytes) -> None:
    """Write a temporary file beside path, then rename it over path.

    A reader holding the file open on Windows makes the rename fail with
    PermissionError for a moment, so the rename is retried there.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{secrets.token_hex(4)}.skf-tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o644)
    try:
        with open(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def backup_path(state_file: Path) -> Path:
    return state_file.with_name(state_file.name + ".bak")


def _set_stage(state: dict, stage: int | None, changed: list[str]) -> None:
    if stage is None:
        return
    state["campaign"]["current_stage"] = stage
    changed.append(f"campaign.current_stage={stage}")


def mutate(
    state_file: str,
    op: str,
    change: Callable[[dict, str, list[str]], dict | None],
    stage: int | None = None,
) -> dict:
    """Read, validate, change, stamp, validate again, rotate .bak, write.

    `change(state, stamp, changed)` edits the state in place, appends a short
    description of each change to `changed`, and may return extra output
    keys. It raises StateError to refuse the operation before anything is
    written.
    """
    path = Path(state_file)
    state, raw = read_state(path)
    new_state = copy.deepcopy(state)
    stamp = now()
    changed: list[str] = []
    extra = change(new_state, stamp, changed) or {}
    _set_stage(new_state, stage, changed)
    new_state["campaign"]["last_updated"] = stamp
    errors = validation_errors(new_state)
    if errors:
        raise StateError(EXIT_STATE, "state-change-invalid",
                         "The change would make the state invalid: nothing was written.", errors)
    bak = backup_path(path)
    write_atomic(bak, raw)
    write_atomic(path, dump_state(new_state))
    return {
        "op": op,
        "state_file": path.as_posix(),
        "backup_file": bak.as_posix(),
        "backup_rotated": True,
        "last_updated": stamp,
        "current_stage": new_state["campaign"]["current_stage"],
        "changed": changed,
        **extra,
    }


# --------------------------------------------------------------------------
# Input files
# --------------------------------------------------------------------------


def read_text(source: str, label: str) -> str:
    """A file's text, or stdin's for `-`, in the encoding it was written in.

    A shell redirect on Windows PowerShell writes UTF-16 with a byte-order
    mark, so one is honoured.
    """
    try:
        raw = sys.stdin.buffer.read() if source == "-" else Path(source).read_bytes()
    except OSError as exc:
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} unreadable: {exc}") from exc
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} is not UTF-8 text: {exc}") from exc


def read_json(source: str, label: str) -> dict:
    text = read_text(source, label)
    if not text.strip():
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} is empty")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} is not a JSON object")
    return data


def read_envelope(source: str, label: str) -> dict:
    """A sub-skill's result envelope: the last SKF_*_RESULT_JSON line, or bare JSON."""
    text = read_text(source, label)
    lines = [line for line in text.splitlines() if "_RESULT_JSON:" in line and "SKF_" in line]
    payload = lines[-1].split("_RESULT_JSON:", 1)[1].strip() if lines else text.strip()
    if not payload:
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} holds no result envelope")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} is not a result envelope: {exc}") from exc
    if not isinstance(data, dict):
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} is not a JSON object")
    return data


def _skills_by_name(state: dict) -> dict[str, dict]:
    return {s["name"]: s for s in state.get("skills", [])}


def _known(state: dict, names: list[str]) -> dict[str, dict]:
    skills = _skills_by_name(state)
    unknown = [n for n in names if n not in skills]
    if unknown:
        raise StateError(EXIT_INPUT, "unknown-skill",
                         f"Unknown skill(s): {', '.join(unknown)}. Known skills: {', '.join(skills)}.")
    return skills


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


def op_init(args: argparse.Namespace) -> dict:
    path = Path(args.state_file)
    bak = backup_path(path)
    for existing in (path, bak):
        if existing.exists():
            raise StateError(EXIT_INPUT, "state-exists",
                             f"`{existing.as_posix()}` already exists: archive the campaign before starting a new one.")
    parsed = read_json(args.targets_file, "Targets")
    if parsed.get("errors"):
        raise StateError(EXIT_INPUT, "targets-invalid", "The targets hold errors: fix them and parse again.",
                         list(parsed["errors"]))
    targets = parsed.get("targets")
    if not isinstance(targets, list) or not targets:
        raise StateError(EXIT_INPUT, "no-targets", "A campaign needs at least one target.")

    gate_module = _module(GATE_SCRIPT)
    try:
        brief = gate_module._load_brief(args.brief_file) if args.brief_file else None
        gate = gate_module.check(args.hard, args.soft_target, args.soft_fallback, brief)
    except gate_module.GateError as exc:
        raise StateError(EXIT_INPUT, exc.code, str(exc), list(exc.extra.get("errors", []))) from exc

    stamp = now()
    campaign: dict[str, Any] = {
        "name": args.name,
        "started_at": stamp,
        "last_updated": stamp,
        "current_stage": 0,
    }
    if args.directive_path:
        campaign["directive_path"] = args.directive_path
    if args.architecture_doc_path:
        campaign["architecture_doc_path"] = args.architecture_doc_path
    campaign["quality_gate"] = {key: gate[key] for key in ("hard", "soft_target", "soft_fallback")}

    skills = []
    for target in targets:
        if not isinstance(target, dict) or not target.get("name"):
            raise StateError(EXIT_INPUT, "targets-invalid", "A target has no name: parse the targets again.")
        skills.append({
            "name": target["name"],
            "status": "pending",
            "depends_on": list(target.get("depends_on") or []),
            "tier": target.get("tier") or "A",
            "pin": target.get("pin"),
            "brief_path": None,
            "skill_path": None,
            "quality_score": None,
            "workarounds_applied": [],
            "started_at": None,
            "completed_at": None,
            "commit_sha": None,
        })
    state = {
        "campaign": campaign,
        "skills": skills,
        "dependency_graph": {"execution_order": [], "circular_deps_detected": False},
    }
    errors = validation_errors(state)
    if errors:
        raise StateError(EXIT_STATE, "state-change-invalid",
                         "The new state would be invalid: nothing was written.", errors)
    write_atomic(path, dump_state(state))
    return {
        "op": "init",
        "state_file": path.as_posix(),
        "backup_file": bak.as_posix(),
        "backup_rotated": False,
        "last_updated": stamp,
        "current_stage": 0,
        "changed": [f"skills={len(skills)}", "campaign.quality_gate"],
        "quality_gate": campaign["quality_gate"],
    }


def op_set_stage(args: argparse.Namespace) -> dict:
    return mutate(args.state_file, "set-stage", lambda state, stamp, changed: None, args.stage)


def op_set_skill(args: argparse.Namespace) -> dict:
    def change(state: dict, stamp: str, changed: list[str]) -> None:
        skills = _known(state, args.skill)
        for name in args.skill:
            skill = skills[name]
            if args.status is not None:
                skill["status"] = args.status
                changed.append(f"{name}.status={args.status}")
                if args.status == "active" and not skill.get("started_at"):
                    skill["started_at"] = stamp
                    changed.append(f"{name}.started_at")
                elif args.status == "completed":
                    skill["completed_at"] = stamp
                    changed.append(f"{name}.completed_at")
                elif args.status == "pending":
                    skill["started_at"] = None
                    skill["completed_at"] = None
            for field in ("quality_score", "skill_path", "brief_path"):
                value = getattr(args, field)
                if value is not None:
                    skill[field] = value
                    changed.append(f"{name}.{field}")

    return mutate(args.state_file, "set-skill", change, args.stage)


def computed_plan(state_file: str) -> list[str]:
    """campaign-deps.py --compute's execution order for the state file.

    StateError (exit 4) when the graph cannot be followed: a cycle, a
    dangling depends_on name or a Tier A skill on a Tier B one.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = _module(DEPS_SCRIPT).compute(state_file)
    if rc == 0:
        return json.loads(out.getvalue())["execution_order"]
    details = [line for line in (out.getvalue() + err.getvalue()).splitlines() if line.strip()]
    raise StateError(EXIT_CIRCULAR, "plan-unorderable",
                     "The dependency graph cannot be followed: campaign-deps.py --compute says why.", details)


def op_apply_plan(args: argparse.Namespace) -> dict:
    def change(state: dict, stamp: str, changed: list[str]) -> dict:
        order = computed_plan(args.state_file)
        state["dependency_graph"] = {"execution_order": order, "circular_deps_detected": False}
        changed.append("dependency_graph.execution_order")
        return {"execution_order": order}

    return mutate(args.state_file, "apply-plan", change, args.stage)


def _results(source: str, label: str) -> list[dict]:
    data = read_json(source, label)
    results = data.get("results")
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        raise StateError(EXIT_INPUT, "input-unreadable", f"{label} holds no results[] list")
    return results


def op_apply_pins(args: argparse.Namespace) -> dict:
    results = _results(args.results_file, "Pin results")
    invalid = [r.get("name") for r in results if r.get("status") not in ("valid", "resolved")]
    if invalid:
        raise StateError(EXIT_PIN, "invalid-pin", f"Invalid pin(s): {', '.join(map(str, invalid))}: nothing was written.")

    def change(state: dict, stamp: str, changed: list[str]) -> None:
        skills = _known(state, [r.get("name") for r in results])
        for result in results:
            ref = result.get("resolved_ref")
            skill = skills[result["name"]]
            if ref and ref != skill.get("pin"):
                skill["pin"] = ref
                changed.append(f"{result['name']}.pin={ref}")

    return mutate(args.state_file, "apply-pins", change, args.stage)


def op_apply_provenance(args: argparse.Namespace) -> dict:
    results = _results(args.results_file, "Provenance results")
    inaccessible = [r.get("name") for r in results if r.get("status") != "accessible" or not r.get("commit_sha")]
    if inaccessible:
        raise StateError(EXIT_REPO, "inaccessible-repo",
                         f"Inaccessible repositories: {', '.join(map(str, inaccessible))}: nothing was written.")

    def change(state: dict, stamp: str, changed: list[str]) -> None:
        skills = _known(state, [r.get("name") for r in results])
        for result in results:
            skills[result["name"]]["commit_sha"] = result["commit_sha"]
            changed.append(f"{result['name']}.commit_sha")

    return mutate(args.state_file, "apply-provenance", change, args.stage)


def op_apply_batch(args: argparse.Namespace) -> dict:
    batch_map = read_json(args.map_file, "Batch map")
    lines = batch_map.get("lines")
    if not isinstance(lines, list):
        raise StateError(EXIT_INPUT, "input-unreadable", "Batch map holds no lines[] list")
    batched = [entry.get("skill") for entry in lines if isinstance(entry, dict)]
    skipped = [e for e in batch_map.get("skipped_by_directive") or [] if isinstance(e, dict)]
    rows: list[dict] = []
    if args.results_file:
        rows = _results(args.results_file, "Batch results")
        unmapped = [r.get("skill") for r in rows if r.get("skill") not in batched]
        if unmapped:
            raise StateError(EXIT_INPUT, "input-unreadable",
                             f"Batch results name skills the map does not: {', '.join(map(str, unmapped))}")

    def change(state: dict, stamp: str, changed: list[str]) -> dict:
        skills = _known(state, batched + [e.get("name") for e in skipped])
        out: dict[str, list] = {"activated": [], "skipped": [], "completed": [], "failed": []}
        if args.start:
            for entry in skipped:
                skills[entry["name"]]["status"] = "skipped"
                out["skipped"].append({"name": entry["name"], "reason": entry.get("reason")})
            for name in batched:
                skill = skills[name]
                skill["status"] = "active"
                if not skill.get("started_at"):
                    skill["started_at"] = stamp
                out["activated"].append(name)
        elif args.no_results:
            for name in batched:
                skills[name]["status"] = "failed"
                out["failed"].append({"skill": name, "error_code": "no-batch-result"})
        else:
            for row in rows:
                skill = skills[row["skill"]]
                if row.get("status") == "completed":
                    skill["status"] = "completed"
                    skill["completed_at"] = stamp
                    skill["quality_score"] = row.get("quality_score")
                    skill["skill_path"] = row.get("skill_path")
                    out["completed"].append(row["skill"])
                else:
                    skill["status"] = "failed"
                    out["failed"].append({"skill": row["skill"], "error_code": row.get("error_code")})
        for key, values in out.items():
            if values:
                changed.append(f"{key}={len(values)}")
        return out

    return mutate(args.state_file, "apply-batch", change, args.stage)


def op_append_workarounds(args: argparse.Namespace) -> dict:
    def change(state: dict, stamp: str, changed: list[str]) -> dict:
        skill = _known(state, [args.skill])[args.skill]
        held = skill.setdefault("workarounds_applied", [])
        added = []
        for entry in args.entry:
            if entry.strip() and entry not in held:
                held.append(entry)
                added.append(entry)
        changed.append(f"{args.skill}.workarounds_applied+{len(added)}")
        return {"added": added}

    return mutate(args.state_file, "append-workarounds", change, args.stage)


def _capstone(envelope: dict, stamp: str) -> dict | None:
    if envelope.get("status") != "success":
        return None
    return {
        "skill_path": envelope.get("skill_package"),
        "quality_score": envelope.get("quality_score"),
        "verified": None,
        "completed_at": stamp,
    }


def _verification(envelope: dict, stamp: str) -> dict | None:
    if envelope.get("status") != "success" or envelope.get("exit_code", 0) != 0:
        return None
    return {key: envelope.get(key) for key in
            ("report_path", "overall_verdict", "coverage_percentage", "recommendation_count")}


def _refinement(envelope: dict, stamp: str) -> dict | None:
    if envelope.get("status") != "success" or envelope.get("exit_code", 0) != 0:
        return None
    return {key: envelope.get(key) for key in ("refined_path", "gap_count", "issue_count", "improvement_count")}


SUMMARIES = (("capstone", _capstone), ("verification", _verification), ("refinement", _refinement))


def op_set_campaign(args: argparse.Namespace) -> dict:
    envelopes = {}
    for field, _build in SUMMARIES:
        source = getattr(args, field)
        if source is not None:
            envelopes[field] = read_envelope(source, f"The {field} envelope")

    def change(state: dict, stamp: str, changed: list[str]) -> dict:
        campaign = state["campaign"]
        recorded, not_recorded = [], []
        if args.architecture_doc_path:
            campaign["architecture_doc_path"] = args.architecture_doc_path
            changed.append("campaign.architecture_doc_path")
        for field, build in SUMMARIES:
            if field in envelopes:
                envelope = envelopes[field]
                value = build(envelope, stamp)
                if value is None:
                    not_recorded.append({"field": field, "status": envelope.get("status"),
                                         "halt_reason": envelope.get("halt_reason"),
                                         "exit_code": envelope.get("exit_code")})
                else:
                    recorded.append(field)
            elif getattr(args, f"no_{field}"):
                value = None
                not_recorded.append({"field": field, "status": None, "halt_reason": None, "exit_code": None})
            else:
                continue
            campaign[field] = value
            changed.append(f"campaign.{field}")
            if field == "verification" and isinstance(campaign.get("capstone"), dict):
                verdict = (value or {}).get("overall_verdict")
                campaign["capstone"]["verified"] = None if value is None else verdict == "FEASIBLE"
                changed.append("campaign.capstone.verified")
        return {"recorded": recorded, "not_recorded": not_recorded}

    return mutate(args.state_file, "set-campaign", change, args.stage)


def op_recover(args: argparse.Namespace) -> dict:
    path = Path(args.state_file)
    bak = backup_path(path)
    try:
        state, raw = read_state(bak)
    except StateError as exc:
        raise StateError(EXIT_NO_BACKUP, "corrupt-state",
                         f"No usable backup at `{bak.as_posix()}`: {exc}", exc.errors) from exc
    write_atomic(path, raw)
    return {
        "op": "recover",
        "state_file": path.as_posix(),
        "backup_file": bak.as_posix(),
        "recovered": True,
        "last_updated": state["campaign"]["last_updated"],
        "current_stage": state["campaign"]["current_stage"],
    }


def _loose_state(path: Path) -> dict | None:
    """The state as YAML, unvalidated: what an archive or a halt can still read."""
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _campaign_name(path: Path) -> str | None:
    campaign = (_loose_state(path) or {}).get("campaign")
    name = campaign.get("name") if isinstance(campaign, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def op_archive(args: argparse.Namespace) -> dict:
    path = Path(args.state_file)
    bak = backup_path(path)
    sources = [p for p in (path, bak, Path(args.brief_file)) if p.is_file()]
    if not sources:
        raise StateError(EXIT_INPUT, "nothing-to-archive", "No campaign state, backup or brief to archive.")
    name = _campaign_name(path) or _campaign_name(bak) or "campaign"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "campaign"
    # No colon in a folder name: Windows refuses one.
    stamp = now().replace("+00:00", "Z").replace(":", "")
    folder = path.parent / "archive" / f"{slug}-{stamp}"
    if folder.exists():
        raise StateError(EXIT_INPUT, "archive-exists", f"`{folder.as_posix()}` already exists: nothing was moved.")
    folder.mkdir(parents=True)
    moved = []
    for source in sources:
        target = folder / source.name
        _replace(source, target)
        moved.append(target.as_posix())
    return {"op": "archive", "archive_dir": folder.as_posix(), "moved": moved}


def op_log(args: argparse.Namespace) -> dict:
    text = " ".join(args.text.split())
    if not text:
        raise StateError(EXIT_INPUT, "input-unreadable", "The log entry is empty")
    entry = f"- {now()} ({args.type}) {text}"
    path = Path(args.log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(entry + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return {"op": "log", "log_file": path.as_posix(), "entry": entry}


def op_halt_payload(args: argparse.Namespace) -> dict:
    path = Path(args.state_file)
    reason = " ".join(read_text("-", "The halt message").split())
    if not reason:
        raise StateError(EXIT_INPUT, "input-unreadable", "The halt message is empty")
    skills = (_loose_state(path) or {}).get("skills")
    skills = [s for s in skills if isinstance(s, dict)] if isinstance(skills, list) else []
    return {
        "phase": args.phase,
        "reason": reason,
        "halt_reason": args.halt_reason,
        "skills_completed": sum(1 for s in skills if s.get("status") == "completed"),
        "skills_failed": sum(1 for s in skills if s.get("status") == "failed"),
        "decision_log": (path.parent / DECISION_LOG).as_posix() if path.parent.is_dir() else None,
    }


def resume_point(state: dict, from_skill: str | None = None, take_next: bool = False) -> dict:
    """Where a resumed campaign continues (see the module docstring)."""
    campaign = state["campaign"]
    skills = state.get("skills", [])
    by_name = _skills_by_name(state)
    result: dict[str, Any] = {
        "complete": False, "stage": None, "step_file": None, "reason": None, "skill": None,
        "needs_choice": False, "from_status": None, "active_other": None,
    }

    def route(stage: int, reason: str, skill: str | None = None) -> dict:
        result.update(stage=stage, step_file=STEP_FILES[stage], reason=reason, skill=skill)
        return result

    if from_skill is not None:
        if from_skill not in by_name:
            raise StateError(EXIT_INPUT, "unknown-skill",
                             f"Unknown skill '{from_skill}'. Known skills: {', '.join(by_name)}.")
        target = by_name[from_skill]
        result["from_status"] = target["status"]
        active = [s["name"] for s in skills if s["status"] == "active" and s["name"] != from_skill]
        result["active_other"] = active[0] if active else None
        if target["status"] in OPEN:
            return route(TIER_STAGE[target["tier"]], "from-skill", from_skill)
        if not take_next:
            result.update(needs_choice=True, skill=from_skill)
            return result
        order = state["dependency_graph"].get("execution_order") or [s["name"] for s in skills]
        after = order[order.index(from_skill) + 1:] if from_skill in order else []
        for name in after:
            skill = by_name.get(name)
            if skill is not None and skill["status"] in OPEN:
                return route(TIER_STAGE[skill["tier"]], "from-next", name)
        result.update(complete=True, reason="nothing-after-from")
        return result

    active = [s for s in skills if s["status"] == "active"]
    if active:
        first = min(active, key=lambda s: TIER_STAGE[s["tier"]])
        return route(TIER_STAGE[first["tier"]], "active-skill", first["name"])
    current = campaign["current_stage"]
    if current >= FINAL_STAGE and not any(s["status"] in OPEN for s in skills):
        result.update(complete=True, reason="complete")
        return result
    if current >= FINAL_STAGE:
        return route(FINAL_STAGE, "terminal-cap")
    return route(current + 1, "next-stage")


def op_resume(args: argparse.Namespace) -> dict:
    state, _raw = read_state(Path(args.state_file))
    if args.next and args.from_skill is None:
        raise StateError(EXIT_INPUT, "input-invalid", "--next needs --from")
    return resume_point(state, args.from_skill, args.next)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _stage(value: str) -> int:
    stage = int(value)
    if not 0 <= stage <= FINAL_STAGE:
        raise argparse.ArgumentTypeError(f"a stage is 0 to {FINAL_STAGE}")
    return stage


def _score(value: str) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campaign-state",
        description="Write _campaign-state.yaml (validated before and after, .bak rotated from a valid "
        "primary, timestamps from the clock, atomic) and compute the resume point.",
    )
    sub = parser.add_subparsers(dest="op", required=True)

    def command(name: str, help_text: str, stage: str | None = "optional") -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        if name != "log":
            p.add_argument("--state-file", required=True, help="path to _campaign-state.yaml")
        if stage is not None:
            p.add_argument("--stage", type=_stage, required=stage == "required",
                           help="write campaign.current_stage (0 to 10) in the same write")
        return p

    p = command("init", "create the state from parsed targets (step-01)", stage=None)
    p.add_argument("--targets-file", required=True, help="campaign-parse-manifest.py output, or - for stdin")
    p.add_argument("--name", required=True, help="campaign name")
    p.add_argument("--hard", required=True, help="quality_gate_hard")
    p.add_argument("--soft-target", required=True, help="quality_gate_soft_target")
    p.add_argument("--soft-fallback", required=True, help="quality_gate_soft_fallback")
    p.add_argument("--brief-file", help="campaign brief whose quality_gate wins over the values above")
    p.add_argument("--directive-path", help="campaign directive file")
    p.add_argument("--architecture-doc-path", help="architecture document for verify and refine")

    command("set-stage", "write campaign.current_stage", stage="required")

    p = command("set-skill", "set fields of one or more skills")
    p.add_argument("--skill", action="append", required=True, help="skill name (repeat for several)")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--quality-score", type=_score)
    p.add_argument("--skill-path")
    p.add_argument("--brief-path")

    command("apply-plan", "write the execution order campaign-deps.py computes (step-02)")

    p = command("apply-pins", "write resolved pins (step-03)")
    p.add_argument("--results-file", required=True, help="campaign-validate-pins.py output, or -")

    p = command("apply-provenance", "write commit SHAs (step-04)")
    p.add_argument("--results-file", required=True, help="campaign-provenance.py output, or -")

    p = command("apply-batch", "record the Tier B batch (step-06)")
    p.add_argument("--map-file", required=True, help="the line-to-skill map campaign-render-batch.py wrote")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start", action="store_true", help="mark skipped and batched skills before the batch")
    mode.add_argument("--results-file", help="campaign-render-batch.py --record output, or -")
    mode.add_argument("--no-results", action="store_true", help="fail every batched skill")

    p = command("append-workarounds", "append entries to a skill's workarounds_applied")
    p.add_argument("--skill", required=True)
    p.add_argument("--entry", action="append", required=True, help="one entry (repeat for several)")

    p = command("set-campaign", "write campaign-level fields")
    p.add_argument("--architecture-doc-path")
    for field, _build in SUMMARIES:
        group = p.add_mutually_exclusive_group()
        group.add_argument(f"--{field}", help=f"the {field} sub-skill's result envelope line, a file or -")
        group.add_argument(f"--no-{field}", action="store_true", help=f"record campaign.{field} as null")

    command("recover", "copy a valid .bak over the primary", stage=None)

    p = command("archive", "move the state, its .bak and the brief into archive/ (overwrite)", stage=None)
    p.add_argument("--brief-file", required=True, help="path to campaign-brief.yaml")

    p = command("log", "append a typed entry to the decision log", stage=None)
    p.add_argument("--log-file", required=True, help="path to _campaign-decision-log.md")
    p.add_argument("--type", required=True, choices=LOG_TYPES)
    p.add_argument("--text", required=True)

    p = command("halt-payload", "print a HARD HALT's emit-halt payload; the message on stdin", stage=None)
    p.add_argument("--phase", required=True, help="the kebab slug of the step that halts")
    p.add_argument("--halt-reason", required=True, help="the Exit Codes meaning, such as circular-deps")

    p = command("resume", "compute the resume point (read-only)", stage=None)
    p.add_argument("--from", dest="from_skill", help="resume at this skill")
    p.add_argument("--next", action="store_true", help="with --from at a finished skill: take the next open one")
    return parser


OPERATIONS = {
    "init": op_init,
    "set-stage": op_set_stage,
    "set-skill": op_set_skill,
    "apply-plan": op_apply_plan,
    "apply-pins": op_apply_pins,
    "apply-provenance": op_apply_provenance,
    "apply-batch": op_apply_batch,
    "append-workarounds": op_append_workarounds,
    "set-campaign": op_set_campaign,
    "recover": op_recover,
    "archive": op_archive,
    "log": op_log,
    "halt-payload": op_halt_payload,
    "resume": op_resume,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = OPERATIONS[args.op](args)
    except StateError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": exc.code, "errors": exc.errors}) + "\n")
        return exc.exit_code
    except OSError as exc:
        sys.stderr.write(json.dumps({"error": f"Write failed: {exc}", "code": "write-failed", "errors": []}) + "\n")
        return EXIT_INPUT
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the streams to UTF-8, keeping each one's error handler.

    A Windows console pipes them as cp1252, which cannot print every
    character a path or a log entry may hold.
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
