# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema>=4.0"]
# ///
"""SKF Quick Batch: the state of a --batch run, kept on disk.

A --batch run drives every target through its workflow's pipeline, one
after another, in one long session: each target of a skf-quick-skill batch
file, or each skill-brief.yaml of a skf-create-skill batch. This helper
keeps the batch's place and every target's outcome in the batch run
folder, not in the conversation, so a context compaction mid-batch loses
neither, and it computes the counts, the status and the exit code the
batch ends with.

CLI (--run-dir is the batch run folder: for skf-quick-skill the one SKILL.md
On Activation creates, {project-root}/_bmad-output/.skf-run/skf-quick-skill-<id>/;
for skf-create-skill the folder start --briefs names after its briefs,
<run-root>/skf-create-skill-batch-<hash>/, so a batch of the same briefs an
ended session left is found again, and a batch of other briefs is never
touched):

  uv run skf-quick-batch.py parse <file>
  uv run skf-quick-batch.py start <file> --run-dir <dir> [--fail-fast]
  uv run skf-quick-batch.py start --briefs <path>... --run-root <dir> [--fail-fast]
  uv run skf-quick-batch.py next --run-dir <dir>
  uv run skf-quick-batch.py record --run-dir <dir> --batch <n> [--target stderr]
  uv run skf-quick-batch.py summarize --run-dir <dir> --output-dir <dir> [--target stderr]

The batch file (UTF-8): one target per line. A blank line, and a line whose
first character after any spaces is `#`, is skipped. The first word of a
line is the target, kept whole: `cognee@0.5.0`, `requests==2.31.0` or
`https://github.com/foo/bar@2.1.0-beta` reach quick-skill's own target
parser (skf-resolve-package.py parse-target) as written, and it splits off
the version. Each later word is a modifier: `language=<lang>` sets the
target's language_hint and `scope=<path>` its scope_hint (the key in any
letter case, the value not empty, each at most once). A line with any other
word after its target is taken whole as the target, so step 1 cannot parse
it and that target fails on its own while the rest of the batch runs.

parse
  Prints {"targets": [{"batch", "target", "language_hint", "scope_hint"}]}:
  the file's targets numbered from 1, a hint null when the line sets none.

start
  Parses the file and writes the batch file, <run-dir>/batch.jsonl: a start
  line (status running, the workflow, the input file's absolute path,
  --fail-fast) and one line per target, status pending. Prints {"status":
  "running", "input_file", "fail_fast", "targets_total", "recorded",
  "resumed"}. When the run folder already holds a batch of the same input
  file, start changes nothing and reports it (resumed true, and the targets
  already recorded), so a start run twice, from any working folder, never
  loses an outcome. A batch of another file is refused. A file with no
  target starts a batch that summarize ends at once, status success.

start --briefs (skf-create-skill)
  The targets are skill-brief.yaml files: each path given is a brief, or a
  folder whose skill-brief.yaml files (under it at any depth, hidden folders
  left out, in path order) are briefs, each once, by its absolute path.
  The batch run folder is <run-root>/skf-create-skill-batch-<hash>, <hash>
  the first 12 hex digits of the SHA-256 of the brief paths, one per line:
  each set of briefs has its own. Every brief is checked with
  skf-validate-brief-schema.py, beside this script, before the first one
  compiles: a brief it refuses (brief-missing, brief-malformed or
  brief-invalid), and a brief whose `name` an earlier brief of the batch
  already has (brief-invalid: both would compile into one skill folder), is
  recorded at once as failed, with the exit code the skf-create-skill
  envelope schema maps its halt_reason to, and next never hands it out.
  Prints {"status": "running", "workflow", "batch_dir", "input_briefs",
  "fail_fast", "targets_total", "recorded", "resumed", "rejected":
  [{"batch", "target", "error_code", "message"}]}. When the folder holds an
  unfinished batch of the same briefs, start changes nothing and reports it
  (resumed true), so a batch a session ended mid-way goes on where it
  stopped; a batch that ended (summarized) gives way to the new one, its
  folder emptied first. No brief under the paths is refused. The pyyaml and
  jsonschema the header names are the brief validator's.

next
  Prints the next pending target, {"status": "next", "batch", "target",
  "language_hint", "scope_hint", "run_dir"}, where run_dir is the target's
  own run folder, created empty (a folder an earlier try of the target left
  is emptied first): <run-dir>/<run-dir name>-<batch>, and for a brief
  <run-dir>/skf-create-skill-batch-<YYYYMMDD-HHmmss>-<batch>, named after
  the batch's start, so the run_id the emitter stamps from it is the
  brief's own in every batch. It prints
  the target's start event on stderr, one line:
    {"batch":<n>,"target":"<target>","status":"start"}
  Prints {"status": "record", "batch"} when that folder already staged
  halt.json or result-context.json: the target ended but was never
  recorded (a compaction between its envelope and record), so record it
  instead of running it again. Prints {"status": "done",
  "fail_fast_triggered"} when no target is pending, or when --fail-fast was
  given and a target failed.

record
  Records how target <n> ended, read from what its run folder staged for
  the shared emitter: halt.json (a HARD HALT: status error, error_code its
  halt_reason, exit_code the code the workflow's envelope schema maps
  that reason to) or result-context.json (status success, exit_code 0,
  quality_score from its summary). The outcome line {"batch", "target",
  "status", "exit_code", "skill_package", "error_code", "quality_score"} is
  appended to batch.jsonl, and a target that succeeded has its run folder
  removed. Prints the target's end event, one line (on stderr under
  --target stderr, on stdout otherwise):
    {"batch":<n>,"target":"<target>","status":"done","exit":0}
    {"batch":<n>,"target":"<target>","status":"fail","exit":<code>,"error_code":"<reason>"}
  A target already recorded prints its event again and changes nothing.

summarize
  Ends the batch: every target recorded, or --fail-fast stopped it after a
  failure. It counts targets_total (the targets that ran), succeeded and
  failed; sets status (success when none failed, a batch with no target
  included; partial when some failed and some succeeded; failed when some
  failed and none succeeded), fail_fast_triggered (--fail-fast stopped the
  batch with targets left) and the exit code (0, else the highest exit
  code of a failed target); writes the summary, with the batch's
  input_file (skf-quick-skill) or input_briefs (skf-create-skill), to
  <output-dir>/<stem>-<YYYYMMDD-HHmmss>.json, <stem> quick-skill-batch or
  create-skill-batch (`-2`, `-3`, ... appended when another batch took
  that second), and its copy <stem>-latest.json; appends the final status
  line to batch.jsonl; and removes the batch run folder when no target failed and
  the summary was written (a halted target's run folder stays for a look).
  Prints the batch_summary event, one line (on stderr under --target
  stderr, on stdout otherwise): {"batch_summary": true, "targets_total",
  "succeeded", "failed", "status", "fail_fast_triggered", "exit_code",
  "summary_path"}, with "warnings" when a summary file could not be
  written. A batch already summarized prints its event again.

The batch file is one JSON object per line, so a write cut short spoils at
most its own line, which is skipped when read: the next write ends that
line first. A later outcome line for a target replaces an earlier one.

Every result and event is one line of ASCII JSON, with no space after a
`,` or `:`, so an event line is printed exactly as its format reads.

Exit codes (1 prints one JSON line on stderr, {"status": "error",
"message": ...}, and nothing on stdout; a refused start adds the
"halt_reason" the batch halts with, in its workflow's words: write-failure
(skf-create-skill: write-failed) when the batch file cannot be written, an
ended batch's folder cannot be emptied, or the briefs' folder holds an
unfinished batch of other briefs; for --briefs, brief-missing when
no brief is found and helper-missing when the validator cannot be loaded;
input-invalid otherwise):
  0  the result was printed
  1  a batch file that cannot be read or is not UTF-8, a run folder with no
     batch (start first) or with a batch of another file or of other
     briefs, a batch file that cannot be written, a --batch number the
     batch does not hold, a target whose run folder staged neither halt.json
     nor result-context.json, an unreadable staged payload, or a summarize
     while targets are still pending
  2  usage error (argparse)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

WORKFLOW = "skf-quick-skill"
CREATE_WORKFLOW = "skf-create-skill"
BATCH_FILE = "batch.jsonl"
HALT_PAYLOAD = "halt.json"
RESULT_PAYLOAD = "result-context.json"
SUMMARY_STEM = "quick-skill-batch"
SUMMARY_STEMS = {WORKFLOW: SUMMARY_STEM, CREATE_WORKFLOW: "create-skill-batch"}
MODIFIERS = {"language": "language_hint", "scope": "scope_hint"}
BRIEF_FILE = "skill-brief.yaml"
SCRIPTS = Path(__file__).resolve().parent
# Each workflow's envelope schema, whose emitter settings map each halt_reason
# to its exit code; the emitter derives the envelope's exit_code from it too.
SCHEMA_FILE = SCRIPTS / "schemas" / "skf-quick-skill-result-envelope.v1.json"
SCHEMA_FILES = {WORKFLOW: SCHEMA_FILE, CREATE_WORKFLOW: SCRIPTS / "schemas" / "skf-create-skill-result-envelope.v1.json"}
# The halt_reason a refused start gives, in each workflow's envelope words.
WRITE_FAILURE = {WORKFLOW: "write-failure", CREATE_WORKFLOW: "write-failed"}
VALIDATOR = SCRIPTS / "skf-validate-brief-schema.py"


class BatchError(Exception):
    """A refusal: exit 1, the message on stderr, with the halt_reason of a refused start."""

    def __init__(self, message: str, halt_reason: str | None = None) -> None:
        super().__init__(message)
        self.halt_reason = halt_reason


# ─── the batch file grammar ─────────────────────────────────────────────────


def _modifier(word: str) -> tuple[str, str] | None:
    """(hint key, value) of a `language=` or `scope=` word, else None."""
    key, sep, value = word.partition("=")
    field = MODIFIERS.get(key.lower()) if sep else None
    return (field, value) if field and value else None


def parse_line(line: str) -> dict | None:
    """The target a batch-file line names, or None for a blank or `#` line."""
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    words = text.split()
    hints = {"language_hint": None, "scope_hint": None}
    for word in words[1:]:
        found = _modifier(word)
        if found is None or hints[found[0]] is not None:
            # Not a modifier, or one given twice: the line is a target of its own.
            return {"target": text, "language_hint": None, "scope_hint": None}
        hints[found[0]] = found[1]
    return {"target": words[0], **hints}


def parse_text(text: str) -> list[dict]:
    """The numbered targets of a batch file's text."""
    targets = []
    for line in text.splitlines():
        entry = parse_line(line)
        if entry is not None:
            targets.append({"batch": len(targets) + 1, **entry})
    return targets


def read_batch_file(path: str) -> list[dict]:
    try:
        # utf-8-sig: a byte-order mark an editor wrote is no part of the first target.
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise BatchError(f"the batch file {path} is not UTF-8 text") from None
    except OSError as e:
        raise BatchError(f"the batch file {path} cannot be read: {e.strerror or e}") from None
    return parse_text(text)


# ─── the batch state ────────────────────────────────────────────────────────


def _utc(seconds: float) -> tuple[str, str]:
    """(ISO-8601 UTC timestamp, YYYYMMDD-HHmmss file stamp) of a Unix time."""
    parts = time.gmtime(seconds)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", parts), time.strftime("%Y%m%d-%H%M%S", parts)


def _append(run_dir: Path, entry: dict) -> None:
    """Append one line to batch.jsonl, first ending a last line a write cut short."""
    line = (json.dumps(entry, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    with open(run_dir / BATCH_FILE, "ab+") as fh:
        end = fh.seek(0, os.SEEK_END)
        if end:
            fh.seek(end - 1)
            if fh.read(1) != b"\n":
                line = b"\n" + line  # the torn line stays a line of its own, which load skips
        fh.write(line)


def load(run_dir: Path) -> dict:
    """The batch run folder's state: its start line, targets, outcomes and summary."""
    try:
        text = (run_dir / BATCH_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BatchError(f"no batch in {run_dir.as_posix()}: run start first") from None
    except (OSError, UnicodeDecodeError) as e:
        raise BatchError(f"the batch in {run_dir.as_posix()} cannot be read: {e}") from None
    state = {"start": None, "targets": {}, "results": {}, "summary": None}
    for line in text.split("\n"):
        try:
            entry = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            entry = None  # a write cut short
        if not isinstance(entry, dict):
            continue
        event = entry.get("event")
        if event == "start":
            state["start"] = entry
        elif event == "target" and isinstance(entry.get("batch"), int):
            state["targets"][entry["batch"]] = entry
        elif event == "result" and isinstance(entry.get("batch"), int):
            state["results"][entry["batch"]] = entry
        elif event == "summary":
            state["summary"] = entry
    if state["start"] is None:
        raise BatchError(f"the batch in {run_dir.as_posix()} has no start line: run start first")
    return state


def workflow(state: dict) -> str:
    """The workflow a batch runs: its start line's, skf-quick-skill for a batch older than the field."""
    name = state["start"].get("workflow")
    return name if name in SCHEMA_FILES else WORKFLOW


def pending(state: dict) -> list[dict]:
    return [state["targets"][n] for n in sorted(state["targets"]) if n not in state["results"]]


def _failed(state: dict) -> list[dict]:
    return [r for r in state["results"].values() if r.get("status") != "success"]


def _target_dir(run_dir: Path, number: int, started: dict | None = None) -> Path:
    """Target `number`'s run folder: named after the batch's start for a brief
    batch, whose folder name repeats for the same briefs."""
    batch_id = (started or {}).get("batch_id")
    if isinstance(batch_id, str) and batch_id:
        return run_dir / f"{CREATE_WORKFLOW}-{batch_id}-{number}"
    return run_dir / f"{run_dir.name}-{number}"


def brief_batch_dir(run_root: Path, briefs: list[str]) -> Path:
    """The batch run folder of a set of briefs: one per set, found again for the same set."""
    digest = hashlib.sha256("\n".join(briefs).encode("utf-8")).hexdigest()[:12]
    return run_root / f"{CREATE_WORKFLOW}-batch-{digest}"


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


# ─── subcommands ────────────────────────────────────────────────────────────


def cmd_parse(file: str) -> dict:
    return {"targets": read_batch_file(file)}


def expand_briefs(paths: list[str]) -> list[str]:
    """The briefs `paths` name, by absolute path with `/`, each once: a
    folder gives its skill-brief.yaml files at any depth (hidden folders
    left out) in path order, any other path is a brief itself."""
    found: list[str] = []
    for given in paths:
        root = Path(given)
        if root.is_dir():
            briefs = sorted((p for p in root.rglob(BRIEF_FILE) if p.is_file()
                             and not any(part.startswith(".") for part in p.relative_to(root).parts)),
                            key=lambda p: p.relative_to(root).as_posix())
        else:
            briefs = [root]
        for brief in briefs:
            absolute = Path(os.path.abspath(brief)).as_posix()
            if not any(_same_file(absolute, seen) for seen in found):
                found.append(absolute)
    return found


def _validator():
    """skf-validate-brief-schema.py, the sibling that checks a brief."""
    try:
        spec = importlib.util.spec_from_file_location("skf_validate_brief_schema", VALIDATOR)
        if spec is None or spec.loader is None:
            raise ImportError(VALIDATOR.as_posix())
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (ImportError, OSError) as e:
        raise BatchError(f"the brief validator cannot be loaded ({VALIDATOR.name} beside {Path(__file__).name}): "
                         f"{e}", "helper-missing") from None
    return module


def check_brief(validator, path: str) -> tuple[str | None, str | None, str | None]:
    """(halt_reason, message, None) of a brief the validator refuses, else (None, None, its name)."""
    file = Path(path)
    if not file.is_file():
        return "brief-missing", (f"Brief not found at `{path}`. Run [BS] Brief Skill to create one, or use [QS] "
                                 "Quick Skill for brief-less generation."), None
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return "brief-malformed", f"Brief validation failed: `{path}` cannot be read as UTF-8 text: {e}", None
    brief, error = validator.load_brief_text(text)
    if error is not None:
        return "brief-malformed", error, None
    result = validator.validate_brief(brief)
    if not result["valid"]:
        return "brief-invalid", result["errors"][0]["message"], None
    return None, None, brief.get("name")


def check_briefs(validator, briefs: list[str]) -> list[tuple[int, str, str | None, str | None]]:
    """(batch, brief, halt_reason, message) of every brief: refused by the
    validator, or by a name an earlier valid brief already has."""
    checked = []
    first: dict[str, str] = {}
    for n, brief in enumerate(briefs, start=1):
        reason, message, name = check_brief(validator, brief)
        if reason is None and isinstance(name, str) and name in first:
            reason, message = "brief-invalid", (f"Brief validation failed: `{brief}` has the name `{name}` of "
                                                f"`{first[name]}`, and both would compile into one skill folder. "
                                                "Give each brief its own name.")
        elif reason is None and isinstance(name, str):
            first[name] = brief
        checked.append((n, brief, reason, message))
    return checked


def _same_file(a, b) -> bool:
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def cmd_start(file: str, run_dir: Path, fail_fast: bool) -> dict:
    # The absolute path, so a start run again from another working folder finds the same batch.
    path = os.path.abspath(file)
    try:
        if (run_dir / BATCH_FILE).exists():
            state = load(run_dir)
            started = state["start"]
            if not _same_file(started.get("input_file"), path):
                raise BatchError(f"{run_dir.as_posix()} holds the batch of {started.get('input_file')}, "
                                 f"not {path}: give this batch a run folder of its own")
            return {"status": "running", "input_file": started.get("input_file"),
                    "fail_fast": bool(started.get("fail_fast")), "targets_total": len(state["targets"]),
                    "recorded": len(state["results"]), "resumed": True}
        targets = read_batch_file(path)
    except BatchError as e:
        raise BatchError(str(e), "input-invalid") from None
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        _append(run_dir, {"event": "start", "status": "running", "input_file": path,
                          "fail_fast": fail_fast, "started_at": _utc(time.time())[0]})
        for target in targets:
            _append(run_dir, {"event": "target", **target, "status": "pending"})
    except OSError as e:
        raise BatchError(f"the batch file cannot be written in {run_dir.as_posix()}: {e.strerror or e}",
                         "write-failure") from None
    return {"status": "running", "input_file": path, "fail_fast": fail_fast,
            "targets_total": len(targets), "recorded": 0, "resumed": False}


def cmd_start_briefs(paths: list[str], run_root: Path, fail_fast: bool) -> dict:
    briefs = expand_briefs(paths)
    if not briefs:
        raise BatchError(f"no {BRIEF_FILE} under {', '.join(paths)}", "brief-missing")
    run_dir = brief_batch_dir(run_root, briefs)
    if (run_dir / BATCH_FILE).exists():
        try:
            state = load(run_dir)
        except BatchError:
            state = None  # a batch file with no start line: nothing to resume
        if state is not None and state["summary"] is None:
            started = state["start"]
            if workflow(state) != CREATE_WORKFLOW or started.get("input_briefs") != briefs:
                raise BatchError(f"{run_dir.as_posix()} holds an unfinished batch of other briefs: "
                                 "finish or remove it first", WRITE_FAILURE[CREATE_WORKFLOW])
            return {"status": "running", "workflow": CREATE_WORKFLOW, "batch_dir": run_dir.as_posix(),
                    "input_briefs": briefs, "fail_fast": bool(started.get("fail_fast")),
                    "targets_total": len(state["targets"]), "recorded": len(state["results"]), "resumed": True,
                    "rejected": [{"batch": r["batch"], "target": r["target"], "error_code": r["error_code"],
                                  "message": r.get("message")}
                                 for _, r in sorted(state["results"].items()) if r.get("rejected")]}
    validator = _validator()
    codes = exit_codes(CREATE_WORKFLOW)
    checked = check_briefs(validator, briefs)
    timestamp, stamp = _utc(time.time())
    try:
        if run_dir.exists():
            _remove_tree(run_dir)  # an ended batch of these briefs gives way to this one
            if (run_dir / BATCH_FILE).exists():
                raise OSError(f"the ended batch's {BATCH_FILE} could not be removed")
        run_dir.mkdir(parents=True, exist_ok=True)
        _append(run_dir, {"event": "start", "status": "running", "workflow": CREATE_WORKFLOW,
                          "input_file": None, "input_briefs": briefs, "fail_fast": fail_fast,
                          "batch_id": f"batch-{stamp}", "started_at": timestamp})
        for n, brief, _, _ in checked:
            _append(run_dir, {"event": "target", "batch": n, "target": brief, "language_hint": None,
                              "scope_hint": None, "status": "pending"})
        rejected = []
        for n, brief, reason, message in checked:
            if reason is None:
                continue
            _append(run_dir, {"event": "result", "batch": n, "target": brief, "status": "error",
                              "exit_code": codes.get(reason, 2), "skill_package": None, "error_code": reason,
                              "quality_score": None, "rejected": True, "message": message})
            rejected.append({"batch": n, "target": brief, "error_code": reason, "message": message})
    except OSError as e:
        raise BatchError(f"the batch file cannot be written in {run_dir.as_posix()}: {e.strerror or e}",
                         WRITE_FAILURE[CREATE_WORKFLOW]) from None
    return {"status": "running", "workflow": CREATE_WORKFLOW, "batch_dir": run_dir.as_posix(), "input_briefs": briefs,
            "fail_fast": fail_fast, "targets_total": len(briefs), "recorded": len(rejected), "resumed": False,
            "rejected": rejected}


def _stop_early(state: dict) -> bool:
    return bool(state["start"].get("fail_fast")) and bool(_failed(state))


def cmd_next(run_dir: Path) -> dict:
    state = load(run_dir)
    left = pending(state)
    if state["summary"] is not None or not left or _stop_early(state):
        return {"status": "done", "fail_fast_triggered": _stop_early(state) and bool(left)}
    target = left[0]
    folder = _target_dir(run_dir, target["batch"], state["start"])
    if (folder / HALT_PAYLOAD).exists() or (folder / RESULT_PAYLOAD).exists():
        return {"status": "record", "batch": target["batch"]}  # it ended: record it, never run it twice
    try:
        if folder.exists():
            _remove_tree(folder)  # an earlier try of this target left it
        folder.mkdir(parents=True)
    except OSError as e:
        raise BatchError(f"the target's run folder {folder.as_posix()} cannot be created: "
                         f"{e.strerror or e}") from None
    return {"status": "next", "batch": target["batch"], "target": target["target"],
            "language_hint": target.get("language_hint"), "scope_hint": target.get("scope_hint"),
            "run_dir": folder.as_posix()}


def exit_codes(name: str = WORKFLOW) -> dict:
    """halt_reason -> exit code, from the workflow's envelope schema's emitter settings."""
    try:
        schema = json.loads(SCHEMA_FILES[name].read_text(encoding="utf-8"))
        codes = schema["$defs"]["skf-envelope"]["const"]["exit_codes"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return codes if isinstance(codes, dict) else {}


def _read_payload(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BatchError(f"{path.as_posix()} holds no JSON object: {e}") from None
    if not isinstance(payload, dict):
        raise BatchError(f"{path.as_posix()} holds no JSON object")
    return payload


def outcome(folder: Path, name: str = WORKFLOW) -> dict:
    """How the target whose run folder is `folder` ended, from its staged payload."""
    halt, result = folder / HALT_PAYLOAD, folder / RESULT_PAYLOAD
    if halt.exists():
        payload = _read_payload(halt)
        reason = payload.get("halt_reason")
        code = exit_codes(name).get(reason) if isinstance(reason, str) else None
        given = payload.get("exit_code")
        if code is None and isinstance(given, int) and not isinstance(given, bool):
            code = given
        if code is None:
            raise BatchError(f"{halt.as_posix()}: halt_reason {reason!r} maps to no exit code")
        package = payload.get("skill_package")
        return {"status": "error", "exit_code": code,
                "skill_package": package if isinstance(package, str) else None,
                "error_code": reason, "quality_score": None}
    if result.exists():
        payload = _read_payload(result)
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        score = summary.get("quality_score")
        package = payload.get("skill_package")
        return {"status": "success", "exit_code": 0,
                "skill_package": package if isinstance(package, str) else None, "error_code": None,
                "quality_score": score if isinstance(score, (int, float)) and not isinstance(score, bool) else None}
    raise BatchError(f"{folder.as_posix()} staged neither {HALT_PAYLOAD} nor {RESULT_PAYLOAD}: stage the "
                     f"payload the target ended with ({HALT_PAYLOAD} or {RESULT_PAYLOAD}) and record it again")


def start_event(handed_out: dict) -> dict:
    return {"batch": handed_out["batch"], "target": handed_out["target"], "status": "start"}


def end_event(entry: dict) -> dict:
    if entry["status"] == "success":
        return {"batch": entry["batch"], "target": entry["target"], "status": "done", "exit": 0}
    return {"batch": entry["batch"], "target": entry["target"], "status": "fail",
            "exit": entry["exit_code"], "error_code": entry["error_code"]}


def cmd_record(run_dir: Path, number: int) -> dict:
    state = load(run_dir)
    target = state["targets"].get(number)
    if target is None:
        raise BatchError(f"the batch in {run_dir.as_posix()} has no target {number}")
    known = state["results"].get(number)
    if known is not None:
        return end_event(known)  # next never hands a recorded target out again
    folder = _target_dir(run_dir, number, state["start"])
    entry = {"event": "result", "batch": number, "target": target["target"], **outcome(folder, workflow(state))}
    try:
        _append(run_dir, entry)
    except OSError as e:
        raise BatchError(f"the outcome cannot be recorded in {run_dir.as_posix()}: {e.strerror or e}") from None
    if entry["status"] == "success":
        _remove_tree(folder)  # a run folder is kept only for a halt
    return end_event(entry)


def _claim(folder: Path, stamp: str, stem: str = SUMMARY_STEM) -> Path:
    """Create the per-batch summary file, empty, under a name no batch holds yet."""
    for n in range(1, 1000):
        path = folder / (f"{stem}-{stamp}.json" if n == 1 else f"{stem}-{stamp}-{n}.json")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        return path
    raise OSError(f"no free file name for {stem}-{stamp}.json")


def _write_json(path: Path, value: dict) -> None:
    """Write `value` as indented JSON through a temporary file and one rename."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def summary_event(summary: dict) -> dict:
    event = {"batch_summary": True}
    for key in ("targets_total", "succeeded", "failed", "status", "fail_fast_triggered", "exit_code",
                "summary_path"):
        event[key] = summary.get(key)
    if summary.get("warnings"):
        event["warnings"] = summary["warnings"]
    return event


def cmd_summarize(run_dir: Path, output_dir: Path) -> dict:
    if not (run_dir / BATCH_FILE).exists() and not run_dir.exists():
        stem = SUMMARY_STEMS[CREATE_WORKFLOW if run_dir.name.startswith(f"{CREATE_WORKFLOW}-") else WORKFLOW]
        raise BatchError(f"no batch in {run_dir.as_posix()}: a batch whose targets all succeeded removes its "
                         f"run folder once summarized; its summary is "
                         f"{(output_dir / f'{stem}-latest.json').as_posix()}")
    state = load(run_dir)
    name = workflow(state)
    if state["summary"] is not None:
        return summary_event(state["summary"])
    left, stopped = pending(state), _stop_early(state)
    if left and not stopped:
        raise BatchError(f"{len(left)} target(s) of the batch are still pending: run next and finish "
                         "them before summarize")
    results = [state["results"][n] for n in sorted(state["results"])]
    failed = [r for r in results if r.get("status") != "success"]
    succeeded = len(results) - len(failed)
    status = "success" if not failed else ("partial" if succeeded else "failed")
    exit_code = max((r["exit_code"] for r in failed), default=0)
    timestamp, stamp = _utc(time.time())
    record = {
        "skill": name,
        "mode": "batch",
        "status": status,
        "timestamp": timestamp,
        **({"input_briefs": state["start"].get("input_briefs")} if name == CREATE_WORKFLOW
           else {"input_file": state["start"].get("input_file")}),
        "targets_total": len(results),
        "succeeded": succeeded,
        "failed": len(failed),
        "fail_fast_triggered": stopped and bool(left),
        "exit_code": exit_code,
        "results": [{key: r.get(key) for key in ("batch", "target", "status", "exit_code", "skill_package",
                                                 "error_code", "quality_score")} for r in results],
    }
    warnings, summary_path = [], None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        per_batch = _claim(output_dir, stamp, SUMMARY_STEMS[name])
        _write_json(per_batch, record)
        summary_path = per_batch.as_posix()
        _write_json(output_dir / f"{SUMMARY_STEMS[name]}-latest.json", record)
    except OSError as e:
        warnings.append(f"summary_write_failed: {output_dir.as_posix()}: {e.strerror or e}")
    final = {"event": "summary", **{k: v for k, v in record.items() if k != "results"},
             "summary_path": summary_path, "warnings": warnings}
    try:
        _append(run_dir, final)
    except OSError as e:
        warnings.append(f"batch_file_write_failed: {run_dir.as_posix()}: {e.strerror or e}")
    inside = output_dir.resolve().is_relative_to(run_dir.resolve())
    if not failed and summary_path is not None and not inside and run_dir.name.startswith(f"{name}-"):
        _remove_tree(run_dir)  # kept when a target halted, or when batch.jsonl is the only record
    return summary_event(final)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _error(error: BatchError) -> None:
    body = {"status": "error", "message": str(error)}
    if error.halt_reason:
        body["halt_reason"] = error.halt_reason
    print(json.dumps(body), file=sys.stderr)


def _line(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_parse = sub.add_parser("parse", help="print the batch file's numbered targets")
    p_parse.add_argument("file", help="the batch file")
    p_start = sub.add_parser("start", help="write the batch file, every target pending")
    p_start.add_argument("file", nargs="?", default=None, help="the batch file given to --batch (skf-quick-skill)")
    p_start.add_argument("--briefs", nargs="+", default=None, metavar="PATH",
                         help="skf-create-skill: the briefs, or folders of briefs, given to --batch")
    p_start.add_argument("--run-dir", default=None, help="the batch run folder (with the batch file)")
    p_start.add_argument("--run-root", default=None,
                         help="with --briefs: the folder the briefs' batch run folder is made in")
    p_start.add_argument("--fail-fast", action="store_true", help="end the batch at the first failed target")
    p_next = sub.add_parser("next", help="print the next pending target, create its run folder and print its "
                                         "start event on stderr")
    p_next.add_argument("--run-dir", required=True, help="the batch run folder")
    p_record = sub.add_parser("record", help="record how a target ended and print its end event")
    p_record.add_argument("--run-dir", required=True, help="the batch run folder")
    p_record.add_argument("--batch", type=int, required=True, help="the target's number, as next printed it")
    p_summary = sub.add_parser("summarize", help="write the batch summary and print the batch_summary event")
    p_summary.add_argument("--run-dir", required=True, help="the batch run folder")
    p_summary.add_argument("--output-dir", required=True, help="the folder the summary files go to")
    for p in (p_record, p_summary):
        p.add_argument("--target", choices=["stdout", "stderr"], default="stdout",
                       help="the stream the event line goes to (default: stdout)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "parse":
            out = cmd_parse(args.file)
        elif args.cmd == "start" and args.briefs is not None:
            if args.file is not None:
                raise BatchError("give start a batch file or --briefs, not both", "input-invalid")
            if args.run_root is None or args.run_dir is not None:
                raise BatchError("start --briefs takes --run-root, not --run-dir: the briefs name their batch "
                                 "run folder", "input-invalid")
            out = cmd_start_briefs(args.briefs, Path(args.run_root), args.fail_fast)
        elif args.cmd == "start":
            if args.file is None:
                raise BatchError("start needs the batch file, or --briefs", "input-invalid")
            if args.run_dir is None or args.run_root is not None:
                raise BatchError("start with a batch file takes --run-dir, not --run-root", "input-invalid")
            out = cmd_start(args.file, Path(args.run_dir), args.fail_fast)
        elif args.cmd == "next":
            out = cmd_next(Path(args.run_dir))
        elif args.cmd == "record":
            out = cmd_record(Path(args.run_dir), args.batch)
        else:
            out = cmd_summarize(Path(args.run_dir), Path(args.output_dir))
    except BatchError as e:
        _error(e)
        return 1
    if args.cmd == "next" and out["status"] == "next":
        print(_line(start_event(out)), file=sys.stderr)
    stream = sys.stderr if getattr(args, "target", "stdout") == "stderr" else sys.stdout
    print(_line(out), file=stream)
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
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
